# Input Latency: UDP and Capture Card - Guide

This document explains practical steps to measure, reduce and compensate input latency for two common input sources: UDP camera/tracking streams and capture cards.

1) Clock synchronization
- Accurate one-way latency measurement requires clocks on sender and receiver to be synchronized (NTP for soft sync, PTP for sub-ms in dedicated networks).
- If clocks are not synchronized, measure RTT (ping/pong) and use RTT/2 as an estimate. The provided UDP handler supports embedding a send timestamp in the payload.

2) UDP stream best practices
- Include: sequence number (uint32), send timestamp (float64) at the start of each packet.
- Sender example header (network byte order): struct.pack('!dI', send_ts, seq)
- Receiver should use an EWMA-based estimator to track one-way latency and jitter and feed that to the predictor.
- Use small payloads, increase UDP socket receive buffer, and tune network QoS to prioritise low latency traffic.
- Sender-side rate: keep consistent frame rate, avoid bursts.

3) Jitter buffering and reordering
- Use a small jitter buffer (e.g. 20-80 ms) to re-order late/out-of-order packets while keeping end-to-end latency low.
- Deliver frames in-order as soon as safe; drop excessively late frames.

4) Capture card best practices
- Prefer APIs that expose hardware timestamps (V4L2 on Linux gives timestamps via dqbuf). On Windows look for card driver SDKs.
- Use PyAV (FFmpeg) to access frame.pts and stream time_base where possible; map stream pts to system time using a measured offset (first frame arrival mapping heuristic) or PTP-synchronized devices.
- Reduce capture buffering in drivers (set buffer count to 1), disable camera-side buffering.
- Use hardware-accelerated capture pipelines (e.g. DirectShow / Media Foundation / GStreamer) with low-latency flags.

5) System & kernel tuning
- Use real-time thread priorities for receiver and processing threads (nice, sched_fifo) carefully.
- On Linux, reduce audio/video subsystem buffering and set NIC interrupts/coalescing for low-latency traffic.

6) Predictor integration
- Always feed predictor with an estimate of end-to-end input latency (network + capture + processing) via predictor.get_aim_point(..., latency=est)
- Add a small safety margin (5-20 ms) to the estimator to account for occasional jitter.

7) Diagnostics & metrics to collect
- One-way latency distribution (p0,p50,p95,p99), jitter, packet loss, reorder rate.
- Time from frame capture to aim command being issued.
- Hit rate / success metric in system tests.

8) Optional advanced measures
- Use PTP for tight clock sync.
- Hardware timestamping at NIC (SO_TIMESTAMPING) and capture card frame timestamps.
- Forward Error Correction (FEC) for lossy networks.
