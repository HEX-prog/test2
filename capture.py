import time
import numpy as np
import mss
import cv2
import dxcam
from config import config

# NDI imports
from cyndilib.wrapper.ndi_recv import RecvColorFormat, RecvBandwidth
from cyndilib.finder import Finder
from cyndilib.receiver import Receiver
from cyndilib.video_frame import VideoFrameSync
from cyndilib.audio_frame import AudioFrameSync

# UDP imports
from OBS_UDP import OBS_UDP_Receiver


def get_region():
    """Center capture region based on capture mode."""
    mode = config.capturer_mode.lower()
    
    if mode in ("capturecard", "capture_card"):
        base_w = int(getattr(config, "capture_width", getattr(config, "screen_width", 1920)))
        base_h = int(getattr(config, "capture_height", getattr(config, "screen_height", 1080)))
        
        # Use custom range if specified, otherwise use region_size
        range_x = int(getattr(config, "capture_range_x", 0))
        range_y = int(getattr(config, "capture_range_y", 0))
        if range_x <= 0:
            range_x = config.region_size
        if range_y <= 0:
            range_y = config.region_size
        
        # Get offsets
        offset_x = int(getattr(config, "capture_offset_x", 0))
        offset_y = int(getattr(config, "capture_offset_y", 0))
        
        # Calculate center position and apply offsets
        left = (base_w - range_x) // 2 + offset_x
        top = (base_h - range_y) // 2 + offset_y
        right = left + range_x
        bottom = top + range_y
        
        # Ensure region is within bounds
        left = max(0, min(left, base_w))
        top = max(0, min(top, base_h))
        right = max(left, min(right, base_w))
        bottom = max(top, min(bottom, base_h))
        
        return (left, top, right, bottom)
    else:
        base_w = config.screen_width
        base_h = config.screen_height
        
        left = (base_w - config.region_size) // 2
        top = (base_h - config.region_size) // 2
        right = left + config.region_size
        bottom = top + config.region_size
        return (left, top, right, bottom)


class MSSCamera:
    def __init__(self, region):
        self.region = region
        self.sct = mss.mss()
        self.monitor = {
            "top": region[1],
            "left": region[0],
            "width": region[2] - region[0],
            "height": region[3] - region[1],
        }
        self.running = True

    def get_latest_frame(self):
        img = np.array(self.sct.grab(self.monitor))
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return img

    def stop(self):
        self.running = False
        self.sct.close()


class NDICamera:
    def __init__(self):
        self.finder = Finder()
        self.finder.set_change_callback(self.on_finder_change)
        self.finder.open()

        self.receiver = Receiver(
            color_format=RecvColorFormat.RGBX_RGBA,
            bandwidth=RecvBandwidth.highest,
        )
        self.video_frame = VideoFrameSync()
        self.audio_frame = AudioFrameSync()
        self.receiver.frame_sync.set_video_frame(self.video_frame)
        self.receiver.frame_sync.set_audio_frame(self.audio_frame)

        # --------------------------------------------------------------

        self.available_sources = []     
        self.desired_source_name = None
        self._pending_index = None
        self._pending_connect = False
        self._last_connect_try = 0.0
        self._retry_interval = 0.5
        # ---------------------------------------------------------------

        self.connected = False
        self._source_name = None
        self._size_checked = False
        self._allowed_sizes = {128,160,192,224,256,288,320,352,384,416,448,480,512,544,576,608,640}

        # prime the initial list so select_source(0) works immediately
        try:
            self.available_sources = self.finder.get_source_names() or []
        except Exception:
            self.available_sources = []

    def select_source(self, name_or_index):
        # guard against early calls
        if self.available_sources is None:
            self.available_sources = []

        self._pending_connect = True
        if isinstance(name_or_index, int):
            self._pending_index = name_or_index
            if 0 <= name_or_index < len(self.available_sources):
                self.desired_source_name = self.available_sources[name_or_index]
            else:
                print(f"[NDI] Will connect to index {name_or_index} when sources are ready.")
                return
        else:
            self.desired_source_name = str(name_or_index)

        if self.desired_source_name in self.available_sources:
            self._try_connect_throttled()

    def on_finder_change(self):
        self.available_sources = self.finder.get_source_names() or []
        print("[NDI] Found sources:", self.available_sources)

        if self._pending_index is not None and 0 <= self._pending_index < len(self.available_sources):
            self.desired_source_name = self.available_sources[self._pending_index]

        if self._pending_connect and not self.connected and self.desired_source_name in self.available_sources:
            self._try_connect_throttled()

    def _try_connect_throttled(self):
        now = time.time()
        if now - self._last_connect_try < self._retry_interval:
            return
        self._last_connect_try = now
        if self.desired_source_name:
            self.connect_to_source(self.desired_source_name)


    def connect_to_source(self, source_name):
        source = self.finder.get_source(source_name)
        if not source:
            print(f"[NDI] Source '{source_name}' not available (get_source returned None).")
            return
        self.receiver.set_source(source)
        self._source_name = source.name
        print(f"[NDI] set_source -> {self._source_name}")
        for _ in range(200):
            if self.receiver.is_connected():
                self.connected = True
                self._pending_connect = False
                print("[NDI] Receiver reports CONNECTED.")
                break
            time.sleep(0.01)
        else:
            print("[NDI] Timeout: receiver never reported connected.")
            self.connected = False
        self._size_checked = False

    # ---- one-time size verdict logging ----
    def _log_size_verdict_once(self, w, h):
        if self._size_checked:
            return
        self._size_checked = True

        name = self._source_name or "NDI Source"
        if w == h and w in self._allowed_sizes:
            print(f"[NDI] Source {name}: {w}x{h} ✔ allowed (no resize).")
            return

        target = min(w, h)
        allowed = sorted(self._allowed_sizes)
        down = max((s for s in allowed if s <= target), default=None)
        up   = min((s for s in allowed if s >= target), default=None)
        if down is None and up is None:
            suggest = 640
        elif down is None:
            suggest = up
        elif up is None:
            suggest = down
        else:
            suggest = down if (target - down) <= (up - target) else up

        if w != h:
            print(
                f"[NDI][FOV WARNING] Source {name}: input {w}x{h} is not square. "
                f"Nearest allowed square: {suggest}x{suggest}. "
                f"Consider a center crop to {suggest}x{suggest} for stable colors & model sizing."
            )
        else:
            print(
                f"[NDI][FOV WARNING] Source {name}: {w}x{h} not in allowed set. "
                f"Nearest allowed: {suggest}x{suggest}. "
                f"Consider a center ROI of {suggest}x{suggest} to avoid interpolation artifacts."
            )
    def list_sources(self, refresh=True):
        """
        Return a list of NDI source names. If refresh=True, query the Finder.
        Never raises; always returns a list.
        """
        if refresh:
            try:
                self.available_sources = self.finder.get_source_names() or []
            except Exception:
                # keep whatever we had, but make sure it's a list
                self.available_sources = self.available_sources or []
        return list(self.available_sources)
    
    
    def maintain_connection(self):
        
        if self.connected and not self.receiver.is_connected():
            self.connected = False
            self._pending_connect = True
        # try reconnect if source is present
        if self._pending_connect and self.desired_source_name in self.available_sources:
            self._try_connect_throttled()

    def switch_source(self, name_or_index):
        self.connected = False
        self._pending_connect = True
        self.select_source(name_or_index)

    def get_latest_frame(self):
        if not self.receiver.is_connected():
            time.sleep(0.002)
            return None

        self.receiver.frame_sync.capture_video()
        if min(self.video_frame.xres, self.video_frame.yres) == 0:
            time.sleep(0.002)
            return None
        config.ndi_width, config.ndi_height = self.video_frame.xres, self.video_frame.yres

        # one-time verdict/log about resolution
        self._log_size_verdict_once(config.ndi_width, config.ndi_height)

        # Copy frame to own memory to avoid "cannot write with view active"
        frame = np.frombuffer(self.video_frame, dtype=np.uint8).copy()
        frame = frame.reshape((self.video_frame.yres, self.video_frame.xres, 4))
        frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)

        return frame

    def stop(self):
        try:
            # detach first so sender-side frees up immediately
            try: self.receiver.set_source(None)
            except Exception: pass
            self.finder.close()
        except Exception as e:
            print(f"[NDI] stop() error: {e}")





class DXGICamera:
    def __init__(self, region=None, target_fps=None):
        self.region = region
        self.camera = dxcam.create(output_idx=0, output_color="BGRA")  # stable default
        # Use config.target_fps if available, else fallback
        fps = int(getattr(config, "target_fps", 240) if target_fps is None else target_fps)
        self.camera.start(target_fps=fps)  # <-- start the capture thread here
        self.running = True

    def get_latest_frame(self):
        frame = self.camera.get_latest_frame()
        if frame is None:
            return None
        # Convert BGRA -> BGR once
        if frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        if self.region:
            x1, y1, x2, y2 = self.region
            frame = frame[y1:y2, x1:x2]
        return frame

    def stop(self):
        self.running = False
        try:
            self.camera.stop()
        except Exception:
            pass


class CaptureCardCamera:
    def __init__(self, region=None):
        # Get capture card parameters from config
        self.frame_width = int(getattr(config, "capture_width", 1920))
        self.frame_height = int(getattr(config, "capture_height", 1080))
        self.target_fps = float(getattr(config, "capture_fps", 240))
        self.device_index = int(getattr(config, "capture_device_index", 0))
        self.fourcc_pref = list(getattr(config, "capture_fourcc_preference", ["NV12", "YUY2", "MJPG"]))
        # Don't store static region - will be calculated dynamically in get_latest_frame
        self.cap = None
        self.running = True
        
        # Try different backends in order of preference
        preferred_backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        for backend in preferred_backends:
            self.cap = cv2.VideoCapture(self.device_index, backend)
            if self.cap.isOpened():
                # Set resolution and frame rate
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.frame_width))
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.frame_height))
                self.cap.set(cv2.CAP_PROP_FPS, float(self.target_fps))
                
                # Try to set preferred fourcc format
                for fourcc in self.fourcc_pref:
                    try:
                        fourcc_code = cv2.VideoWriter_fourcc(*fourcc)
                        self.cap.set(cv2.CAP_PROP_FOURCC, fourcc_code)
                        print(f"[CaptureCard] Set fourcc to {fourcc}")
                        break
                    except Exception as e:
                        print(f"[CaptureCard] Failed to set fourcc {fourcc}: {e}")
                        continue
                
                print(f"[CaptureCard] Successfully opened camera {self.device_index} with backend {backend}")
                print(f"[CaptureCard] Resolution: {self.frame_width}x{self.frame_height}, FPS: {self.target_fps}")
                break
            else:
                self.cap.release()
                self.cap = None
        
        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError(f"Failed to open capture card at device index {self.device_index}")

    def get_latest_frame(self):
        if not self.cap or not self.cap.isOpened():
            return None
        
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None
        
        # Dynamically calculate region based on current config values
        # This allows real-time updates when X/Y Range or Offset changes
        base_w = int(getattr(config, "capture_width", 1920))
        base_h = int(getattr(config, "capture_height", 1080))
        
        # Use custom range if specified, otherwise use region_size
        range_x = int(getattr(config, "capture_range_x", 0))
        range_y = int(getattr(config, "capture_range_y", 0))
        if range_x <= 0:
            range_x = config.region_size
        if range_y <= 0:
            range_y = config.region_size
        
        # Get offsets
        offset_x = int(getattr(config, "capture_offset_x", 0))
        offset_y = int(getattr(config, "capture_offset_y", 0))
        
        # Calculate center position and apply offsets
        left = (base_w - range_x) // 2 + offset_x
        top = (base_h - range_y) // 2 + offset_y
        right = left + range_x
        bottom = top + range_y
        
        # Ensure region is within bounds
        left = max(0, min(left, base_w))
        top = max(0, min(top, base_h))
        right = max(left, min(right, base_w))
        bottom = max(top, min(bottom, base_h))
        
        # Apply region cropping
        x1, y1, x2, y2 = left, top, right, bottom
        frame = frame[y1:y2, x1:x2]
        
        return frame

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None


class UDPCamera:
    def __init__(self, region=None):
        """
        Initialize UDP camera for receiving MJPEG stream from OBS Studio
        
        Args:
            region: Optional region tuple (left, top, right, bottom) for cropping
                   Note: For UDP mode, we typically get the full frame like NDI
        """
        self.region = region
        self.udp_receiver = None
        self.running = True
        self.last_valid_frame = None
        self.frame_retry_count = 0
        self.max_retries = 5
        
        # Get UDP parameters from config
        self.udp_ip = getattr(config, "udp_ip", "192.168.0.01")
        self.udp_port = int(getattr(config, "udp_port", 1234))
        
        # Initialize UDP receiver
        try:
            self.udp_receiver = OBS_UDP_Receiver(
                ip=self.udp_ip,
                port=self.udp_port,
                target_fps=60  # Default FPS, can be adjusted if needed
            )
            
            # Connect to UDP stream
            if not self.udp_receiver.connect():
                raise RuntimeError(f"Failed to connect to UDP stream at {self.udp_ip}:{self.udp_port}")
            
            print(f"[UDP] Successfully connected to {self.udp_ip}:{self.udp_port}")
            
        except Exception as e:
            print(f"[UDP] Error initializing UDP camera: {e}")
            raise RuntimeError(f"Failed to initialize UDP camera: {e}")

    def get_latest_frame(self):
        """
        Get the latest frame from UDP stream with robust error handling
        
        Returns:
            numpy.ndarray or None: Latest frame or None if no frame available
        """
        if not self.udp_receiver or not self.udp_receiver.is_connected:
            return self.last_valid_frame  # Return last valid frame if disconnected
        
        try:
            # Get current frame from UDP receiver
            frame = self.udp_receiver.get_current_frame()
            
            if frame is None:
                # If no new frame, return last valid frame to avoid empty frames
                return self.last_valid_frame
            
            # Validate frame dimensions and data
            if not self._validate_frame(frame):
                self.frame_retry_count += 1
                if self.frame_retry_count >= self.max_retries:
                    print(f"[UDP] Too many invalid frames, using last valid frame")
                    self.frame_retry_count = 0
                return self.last_valid_frame
            
            # Frame is valid, reset retry counter and store as last valid
            self.frame_retry_count = 0
            self.last_valid_frame = frame.copy()
            
            # Update UDP stream dimensions in config (like NDI does)
            config.udp_width, config.udp_height = frame.shape[1], frame.shape[0]
            
            # For UDP mode, we typically get the full frame like NDI
            # Only apply region cropping if specifically requested and frame is large enough
            if self.region and frame.shape[0] > 100 and frame.shape[1] > 100:
                try:
                    x1, y1, x2, y2 = self.region
                    # Ensure region is within frame bounds
                    x1 = max(0, min(x1, frame.shape[1]))
                    y1 = max(0, min(y1, frame.shape[0]))
                    x2 = max(x1, min(x2, frame.shape[1]))
                    y2 = max(y1, min(y2, frame.shape[0]))
                    
                    if x2 > x1 and y2 > y1:
                        frame = frame[y1:y2, x1:x2]
                except Exception as e:
                    print(f"[UDP] Error applying region crop: {e}")
                    # Return full frame if cropping fails
            
            return frame
            
        except Exception as e:
            print(f"[UDP] Error getting frame: {e}")
            # Return last valid frame on error to maintain stability
            return self.last_valid_frame

    def _validate_frame(self, frame):
        """
        Validate frame data to prevent processing errors
        
        Args:
            frame: Frame to validate
            
        Returns:
            bool: True if frame is valid, False otherwise
        """
        try:
            if frame is None:
                return False
            
            # Check if frame has valid shape
            if len(frame.shape) < 2:
                return False
            
            height, width = frame.shape[:2]
            
            # Check for reasonable dimensions
            if height <= 0 or width <= 0:
                return False
            
            # Check for minimum size (avoid tiny frames)
            if height < 10 or width < 10:
                return False
            
            # Check for maximum size (avoid corrupted huge frames)
            if height > 10000 or width > 10000:
                return False
            
            # Check if frame has valid data (not all zeros or all same value)
            if np.all(frame == 0) or np.all(frame == frame.flat[0]):
                return False
            
            return True
            
        except Exception as e:
            print(f"[UDP] Frame validation error: {e}")
            return False

    def stop(self):
        """Stop UDP camera and disconnect from stream"""
        self.running = False
        if self.udp_receiver:
            try:
                self.udp_receiver.disconnect()
                print("[UDP] Disconnected from UDP stream")
            except Exception as e:
                print(f"[UDP] Error during disconnect: {e}")
            finally:
                self.udp_receiver = None


def get_camera():
    """Factory function to return the right camera based on config."""
    if config.capturer_mode.lower() == "mss":
        region = get_region()
        cam = MSSCamera(region)
        return cam, region
    elif config.capturer_mode.lower() == "ndi":
        cam = NDICamera()
        return cam, None
    elif config.capturer_mode.lower() == "dxgi":
        region = get_region()
        cam = DXGICamera(region)
        return cam, region
    elif config.capturer_mode.lower() in ["capturecard", "capture_card"]:
        region = get_region()
        cam = CaptureCardCamera(region)
        return cam, region
    elif config.capturer_mode.lower() == "udp":
        # For UDP mode, get full frame like NDI (no region cropping)
        cam = UDPCamera(None)
        return cam, None
    else:
        raise ValueError(f"Unknown capturer_mode: {config.capturer_mode}")