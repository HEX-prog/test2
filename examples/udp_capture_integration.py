# -*- coding: utf-8 -*-
"""
Example that integrates UDPInputHandler and CaptureCardHandler with the AimPredictor.
Invoke with a real UDP sender that uses the header described in aim_prediction/latency.py,
or point source to a capture-card device (e.g. '/dev/video0' on Linux) when use_pyav=False.
"""
import time
import struct

from aim_prediction.predictor import AimPredictor
from aim_prediction.latency import UDPInputHandler, CaptureCardHandler, aim_with_latency


# sample UDP on_frame callback

def udp_on_frame(payload, seq, send_ts, recv_time, est_latency):
    # payload: could be serialized [x,y] floats in a simple format; for example: two floats
    if len(payload) >= 8 * 2:
        x, y = struct.unpack('!dd', payload[:16])
        # update predictor with measured target pos
        predictor.update([x, y], timestamp=recv_time)
        aim, tof, used_latency = aim_with_latency(predictor, shooter_pos, projectile_speed, udp_handler.latency_est)
        print(f"UDP frame seq={{seq}} pos=({x:.2f},{y:.2f}) recv_latency={{est_latency:.3f}}s used_latency={{used_latency:.3f}}s aim={{aim}} tof={{tof:.3f}}s")


# sample capture on_frame callback

def capture_on_frame(frame_obj, frame_ts, arrival_ts, est_latency):
    # frame_obj: PyAV frame or OpenCV image
    # here we simulate extracting a tracking measurement from the frame (user pipeline required)
    # for the example, we'll assume a placeholder measurement
    measurement = [10.0, 5.0]
    predictor.update(measurement, timestamp=arrival_ts)
    aim, tof, used_latency = aim_with_latency(predictor, shooter_pos, projectile_speed, cc_handler.latency_est)
    print(f"CAPTURE frame ts={{frame_ts:.3f}} arrival={{arrival_ts:.3f}} est_lat={{est_latency:.3f}} aim={{aim}} tof={{tof:.3f}}s")


if __name__ == '__main__':
    shooter_pos = [0.0, 0.0]
    projectile_speed = 30.0

    predictor = AimPredictor(dim=2, dt=1/60, process_var=0.2, meas_var=2.0)

    # UDP example
    udp_handler = UDPInputHandler(('0.0.0.0', 9000), udp_on_frame, buffer_ms=40.0)
    udp_handler.start()

    # Capture card example (use_pyav=True preferred if av installed)
    cc_handler = CaptureCardHandler('/dev/video0', capture_on_frame, use_pyav=False)
    # cc_handler.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        udp_handler.stop()
        cc_handler.stop()
