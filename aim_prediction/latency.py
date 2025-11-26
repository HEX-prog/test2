import cv2
import numpy as np

class LatencyCapture:
    def __init__(self):
        self.offset_mapping = {}

    def setup_windows_capture(self):
        # Use DirectShow backend for Windows
        self.capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.capture.isOpened():
            raise Exception("Could not open video device")

    def ewma_offset(self, new_value, alpha=0.5):
        if not self.offset_mapping:
            self.offset_mapping['ewma'] = new_value
        else:
            self.offset_mapping['ewma'] = (alpha * new_value) + ((1 - alpha) * self.offset_mapping['ewma'])
        return self.offset_mapping['ewma']

    def capture_frame(self):
        ret, frame = self.capture.read()
        if ret:
            # Process frame here
            pass
        else:
            raise Exception("Failed to capture frame")

    def release(self):
        self.capture.release()
        cv2.destroyAllWindows()