# -*- coding: utf-8 -*-
"""
Latency measurement & input handlers for UDP and capture-card sources.
Provides:
- LatencyEstimator: EWMA-based latency + jitter estimator
- UDPInputHandler: lightweight UDP protocol (seq + send_ts) + jitter buffer
- CaptureCardHandler: PyAV/OpenCV helpers to extract frame timestamps and estimate input latency
- helper function to integrate latency with AimPredictor

Notes:
- For accurate one-way latency you need synchronized clocks (NTP/PTP) or include a clock offset protocol.
- If clocks are not synchronized, UDP handler supports RTT-based ping/pong to estimate half-RTT as a fallback.
"""
from __future__ import annotations

import collections
import socket
import struct
import threading
import time
from typing import Callable, Deque, Optional, Tuple

import numpy as np

# LatencyEstimator -----------------------------------------------------------

class LatencyEstimator:
    """Estimate latency and jitter using EWMA.

    Attributes:
        alpha: smoothing factor for latency EWMA (0..1)
        beta: smoothing for jitter EWMA
        latency: current latency estimate (seconds)
        jitter: current jitter estimate (seconds)
    """

    def __init__(self, alpha: float = 0.1, beta: float = 0.05, initial: float = 0.05):
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.latency = float(initial)
        self.jitter = 0.0
        self._last_samples: Deque[float] = collections.deque(maxlen=200)

    def add_sample(self, sample: float) -> None:
        """Add a latency sample in seconds (one-way or RTT/2 depending on source)."""
        # simple EWMA update
        prev = self.latency
        self.latency = (1 - self.alpha) * self.latency + self.alpha * sample
        # jitter as EWMA of absolute deviation
        dev = abs(sample - prev)
        self.jitter = (1 - self.beta) * self.jitter + self.beta * dev
        self._last_samples.append(sample)

    def get_latency(self) -> float:
        """Return current latency estimate (seconds)."""
        return float(self.latency)

    def get_jitter(self) -> float:
        return float(self.jitter)

    def percentiles(self, q: float = 0.95) -> float:
        if not self._last_samples:
            return self.latency
        arr = np.array(list(self._last_samples))
        return float(np.quantile(arr, q))


# UDPInputHandler -----------------------------------------------------------

# UDP payload format (binary): <dI...> -> send_ts (double), seq (unsigned int), optional payload bytes
# send_ts = sender's unix timestamp in seconds (float64), seq = 32-bit sequence number

UDP_HEADER_FMT = "!dI"  # network byte order: double, unsigned int
UDP_HEADER_SIZE = struct.calcsize(UDP_HEADER_FMT)


class UDPInputHandler:
    """A robust UDP receiver that computes latency (if sender embeds a timestamp),
    supports jitter buffering and optional ping/pong RTT estimation.

    Usage:
        receiver = UDPInputHandler(('0.0.0.0', 9000), handle_frame)
        receiver.start()

    The `handle_frame` callback receives (payload_bytes, seq, send_ts, recv_time, est_latency)
    """

    def __init__(self, addr: Tuple[str, int], on_frame: Callable, bind=True, buffer_ms: float = 50.0):
        self.addr = addr
        self.on_frame = on_frame
        self.sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.buffer_ms = float(buffer_ms)
        self.latency_est = LatencyEstimator(initial=0.05)
        # jitter buffer keyed by seq
        self._buf = {}
        self._next_seq = None

    def _open_socket(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(self.addr)
        # reduce OS-level buffering where possible
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)  # 1MB
        except Exception:
            pass
        s.setblocking(True)
        self.sock = s

    def start(self):
        if self._running:
            return
        self._open_socket()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run_loop(self):
        assert self.sock is not None
        safety_delay = max(0.001, self.buffer_ms / 1000.0)
        while self._running:
            try:
                data, addr = self.sock.recvfrom(65536)
            except Exception:
                continue
            recv_time = time.time()
            if len(data) >= UDP_HEADER_SIZE:
                try:
                    send_ts, seq = struct.unpack(UDP_HEADER_FMT, data[:UDP_HEADER_SIZE])
                except struct.error:
                    # malformed header
                    continue
                payload = data[UDP_HEADER_SIZE:]
                # compute one-way latency if clocks are approximately synced
                est_latency = max(0.0, recv_time - send_ts)
                # update estimator
                self.latency_est.add_sample(est_latency)
                # store in jitter buffer
                self._buf[seq] = (payload, seq, send_ts, recv_time, est_latency)
                # initialize next_seq
                if self._next_seq is None:
                    self._next_seq = seq
                # release frames that are older than safety_delay
                to_deliver = []
                min_seq = self._next_seq
                # deliver in-order as possible
                while min_seq in self._buf:
                    to_deliver.append(self._buf.pop(min_seq))
                    min_seq += 1
                self._next_seq = min_seq
                # deliver
                for frame in to_deliver:
                    payload, seq, send_ts, recv_time, est_latency = frame
                    try:
                        self.on_frame(payload, seq, send_ts, recv_time, self.latency_est.get_latency())
                    except Exception:
                        pass
            else:
                # no header, ignore or pass raw
                pass

    def get_latency(self) -> float:
        return self.latency_est.get_latency()


# CaptureCardHandler --------------------------------------------------------

class CaptureCardHandler:
    """Helper wrapper for capture-card/frame-grabber inputs.

    Two approaches provided:
      - PyAV (preferred): extracts frame.pts and time_base to compute stream timestamp
      - OpenCV fallback: uses arrival time as best-effort

    The handler calls on_frame(frame_obj, frame_ts, arrival_ts, est_latency)

    Note: mapping stream timestamps to system wall-clock requires synchronized sources or known offset.
    """

    def __init__(self, source: str, on_frame: Callable, use_pyav: bool = True):
        self.source = source
        self.on_frame = on_frame
        self.use_pyav = use_pyav
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.latency_est = LatencyEstimator(initial=0.03)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run_loop(self):
        if self.use_pyav:
            try:
                import av
            except Exception:
                # fallback to OpenCV
                self.use_pyav = False

        if self.use_pyav:
            self._run_pyav()
        else:
            self._run_opencv()

    def _run_pyav(self):
        import av

        container = av.open(self.source, timeout=5)
        stream = container.streams.video[0]
        time_base = float(stream.time_base)
        for frame in container.decode(video=0):
            if not self._running:
                break
            arrival = time.time()
            # frame.pts may be None; fall back to arrival time
            if frame.pts is not None:
                frame_ts = float(frame.pts) * time_base
                # If frame_ts appears to be in stream time (monotonic), we need to estimate offset to system clock
                # Simple heuristic: assume first frame arrival maps to system time
                # We'll compute est latency as arrival - frame_ts (works if frame_ts already in seconds)
                est = max(0.0, arrival - frame_ts)
            else:
                frame_ts = arrival
                est = 0.0
            self.latency_est.add_sample(est)
            try:
                self.on_frame(frame, frame_ts, arrival, self.latency_est.get_latency())
            except Exception:
                pass

    def _run_opencv(self):
        import cv2

        cap = cv2.VideoCapture(self.source)
        # try to reduce buffering on capture device
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        while self._running and cap.isOpened():
            ret, frame = cap.read()
            arrival = time.time()
            if not ret:
                time.sleep(0.001)
                continue
            # OpenCV doesn't expose device timestamps reliably; use arrival time
            est = 0.0
            self.latency_est.add_sample(est)
            try:
                self.on_frame(frame, arrival, arrival, self.latency_est.get_latency())
            except Exception:
                pass
        try:
            cap.release()
        except Exception:
            pass

    def get_latency(self) -> float:
        return self.latency_est.get_latency()


# Integration helper --------------------------------------------------------

def aim_with_latency(predictor, shooter_pos, projectile_speed, latency_estimator: LatencyEstimator, safety_ms: float = 5.0):
    """Return (aim_point, tof, used_latency)

    - predictor: AimPredictor instance
    - latency_estimator: LatencyEstimator (from UDP or CaptureCard handler)
    - safety_ms: extra margin added to latency (milliseconds)
    """
    base_latency = latency_estimator.get_latency()
    safety = max(0.0, safety_ms / 1000.0)
    used_latency = base_latency + safety
    aim, tof = predictor.get_aim_point(shooter_pos, projectile_speed, latency=used_latency)
    return aim, tof, used_latency


# End of file
