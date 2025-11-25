import cv2

def list_cameras():
    i = 0
    camera_found = False
    while True:
        # Try common Windows backends in order; fall back to default.
        preferred_backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        for backend in preferred_backends:
            cap = cv2.VideoCapture(i, backend)
            if cap.isOpened():
                break
            cap.release()
        
        if not cap.isOpened():
            cap.release()
            # If we fail to open 5 consecutive indices, assume no more cameras
            # This is a heuristic to prevent infinite loops if no cameras are found at higher indices
            if i > 5 and not any(cv2.VideoCapture(i - j, backend).isOpened() for j in range(1, 5) for backend in preferred_backends):
                break
            i += 1
            continue

        camera_found = True
        print(f"Found camera at index {i}")
        # Optionally, get some properties
        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"  Resolution: {int(width)}x{int(height)}, FPS: {int(fps)}")
        cap.release()
        i += 1

    if not camera_found:
        print("No cameras found. Please ensure your capture card is connected and drivers are installed.")

if __name__ == "__main__":
    list_cameras()
