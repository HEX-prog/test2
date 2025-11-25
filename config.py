import os
import json
import threading
import ctypes
from ctypes import wintypes

# Structures
class RECT(ctypes.Structure):
    _fields_ = [
        ("left",   ctypes.c_long),
        ("top",    ctypes.c_long),
        ("right",  ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",   ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork",    RECT),
        ("dwFlags",   ctypes.c_ulong),
    ]

def get_foreground_monitor_resolution():
    # DPI awareness so we get actual pixels
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    user32 = ctypes.windll.user32
    monitor = user32.MonitorFromWindow(user32.GetForegroundWindow(), 2)  # MONITOR_DEFAULTTONEAREST = 2
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)

    if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
        w = mi.rcMonitor.right - mi.rcMonitor.left
        h = mi.rcMonitor.bottom - mi.rcMonitor.top
        return w, h
    else:
        # fallback to primary if anything fails
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

w, h = get_foreground_monitor_resolution()

class Config:
    def __init__(self):
        # --- General Settings ---
        self.region_size = 200  # Keep for backward compatibility
        self.fov_x_size = 200   # FOV X-axis size
        self.fov_y_size = 200   # FOV Y-axis size
        w, h = get_foreground_monitor_resolution()
        self.screen_width = w # Revert to original
        self.screen_height = h  # Revert to original
        self.player_y_offset = 5 # Offset for player detection
        self.capturer_mode = "NDI"  # Default to MSS mode
        self.always_on_aim = False
        
        # --- Height Targeting System ---
        self.height_targeting_enabled = True  # Enable height targeting system
        self.target_height = 0.700  # Target height on player (0.100=bottom, 1.000=top)
        self.height_deadzone_enabled = True  # Enable height deadzone
        self.height_deadzone_min = 0.600  # Lower bound of deadzone
        self.height_deadzone_max = 0.800  # Upper bound of deadzone
        self.height_deadzone_x_only = True  # Only move X-axis in deadzone
        self.height_deadzone_tolerance = 5.000  # Pixels of tolerance for full entry (higher = need to be deeper inside)
        self.main_pc_width = 1920  # Default width for main PC
        self.main_pc_height = 1080  # Default height for main PC
        
        # --- X-Axis Center Targeting ---
        self.x_center_targeting_enabled = True  # Enable X-axis center targeting
        self.x_center_tolerance_percent = 10.0   # Tolerance percentage for X-center targeting (0-50%)
        self.x_center_offset_px = 0             # X-axis offset in pixels for center targeting
        
        # --- Mouse Movement Multiplier ---
        self.mouse_movement_multiplier = 1.0     # Mouse movement speed multiplier (0.1-5.0) - kept for backward compatibility
        self.mouse_movement_multiplier_x = 1.0   # Mouse movement speed multiplier for X-axis (0.0-5.0)
        self.mouse_movement_multiplier_y = 1.0   # Mouse movement speed multiplier for Y-axis (0.0-5.0)
        self.mouse_movement_enabled_x = True     # Enable/disable X-axis movement (True/False)
        self.mouse_movement_enabled_y = True     # Enable/disable Y-axis movement (True/False)
        
        # --- RCS (Recoil Control System) ---
        self.rcs_enabled = False                 # Enable RCS functionality
        self.rcs_ads_only = False               # Enable RCS only when ADS (right mouse button held)
        self.rcs_disable_y_axis = False          # Disable Aimbot Y-axis movement when RCS is active
        self.rcs_button = getattr(self, "rcs_button", 0)  # 0..4 -> Left, Right, Middle, Side4, Side5
        self.rcs_x_strength = 1.0               # X-axis recoil compensation strength (0.1-5.0)
        self.rcs_x_delay = 0.010                # X-axis recoil compensation delay in seconds (0.001-0.100)
        self.rcs_y_random_enabled = False       # Enable Y-axis random jitter
        self.rcs_y_random_strength = 0.5        # Y-axis random jitter strength (0.1-3.0)
        self.rcs_y_random_delay = 0.020         # Y-axis random jitter delay in seconds (0.001-0.100)
        
        # --- RCS Game-based Mode ---
        self.rcs_mode = "simple"                # RCS mode: "simple" or "game"
        self.rcs_game = ""                       # Selected game name (e.g., "cs2", "apex", "rust")
        self.rcs_weapon = ""                     # Selected weapon name (e.g., "ak47", "R301")
        self.rcs_x_multiplier = 1.0             # X-axis movement multiplier (default, kept for backward compatibility)
        self.rcs_y_multiplier = 1.0             # Y-axis movement multiplier (default, kept for backward compatibility)
        self.rcs_x_time_multiplier = 1.0        # X-axis time multiplier (default, kept for backward compatibility)
        self.rcs_y_time_multiplier = 1.0        # Y-axis time multiplier (default, kept for backward compatibility)
        
        # --- Per-weapon RCS multipliers ---
        # Dictionary structure: {game: {weapon: {x_mult, y_mult, x_time_mult, y_time_mult}}}
        # Example: {"cs2": {"ak47": {"x_mult": 1.0, "y_mult": 1.0, "x_time_mult": 1.0, "y_time_mult": 1.0}}}
        if not hasattr(self, 'rcs_weapon_multipliers'):
            self.rcs_weapon_multipliers = {}
    
    def _ensure_default_attributes(self):
        """Ensure all default attributes exist after loading config"""
        # Ensure non-serializable objects exist
        if not hasattr(self, '_save_lock'):
            import threading
            self._save_lock = threading.Lock()
        if not hasattr(self, '_save_timer'):
            self._save_timer = None
        
        # List of critical attributes that must exist
        critical_attrs = {
            'model_path': os.path.join(self.models_dir if hasattr(self, 'models_dir') else 'models', "Click here to Load a model"),
            'models_dir': 'models',
            'aim_humanization': 0,
            'rcs_weapon_multipliers': {},
            'region_size': 200,
            'fov_x_size': 200,
            'fov_y_size': 200,
            'player_y_offset': 5,
            'capturer_mode': 'NDI',
            'always_on_aim': False,
            'rcs_enabled': False,
            'rcs_ads_only': False,
            'rcs_disable_y_axis': False,
            'rcs_button': 0,
            'rcs_mode': 'simple',
            'rcs_game': '',
            'rcs_weapon': '',
            'rcs_x_multiplier': 1.0,
            'rcs_y_multiplier': 1.0,
            'rcs_x_time_multiplier': 1.0,
            'rcs_y_time_multiplier': 1.0,
            'rcs_x_strength': 1.0,
            'rcs_x_delay': 0.010,
            'rcs_y_random_enabled': False,
            'rcs_y_random_strength': 0.5,
            'rcs_y_random_delay': 0.020,
            'selected_mouse_button': 3,
            'makcu_connected': False,
            'makcu_status_msg': 'Disconnected',
            'in_game_sens': 1.3,
            'button_mask': False,
            'mode': 'normal',
            'conf': 0.2,
            'imgsz': 640,
            'max_detect': 50,
            'selected_player_classes': [],
            'class_confidence': {},
            'ndi_selected_source': None,
            'ndi_width': 0,
            'ndi_height': 0,
            'ndi_sources': [],
            'show_debug_window': False,
            'show_debug_text_info': True,
            'custom_head_label': "Select a Head Class",
            'custom_player_label': "Select a Player Class",
            'normal_x_speed': 0.5,
            'normal_y_speed': 0.5,
            'bezier_segments': 8,
            'bezier_ctrl_x': 16,
            'bezier_ctrl_y': 16,
            'silent_segments': 7,
            'silent_ctrl_x': 18,
            'silent_ctrl_y': 18,
            'silent_speed': 3,
            'silent_cooldown': 0.05,
            'silent_strength': 1.0,
            'silent_auto_fire': False,
            'silent_fire_delay': 0.010,
            'silent_return_delay': 0.020,
            'silent_speed_mode': True,
            'silent_use_bezier': False,
            'smooth_gravity': 9.0,
            'smooth_wind': 3.0,
            'smooth_min_delay': 0.0,
            'smooth_max_delay': 0.002,
            'smooth_max_step': 40.0,
            'smooth_min_step': 2.0,
            'smooth_max_step_ratio': 0.20,
            'smooth_target_area_ratio': 0.06,
            'smooth_reaction_min': 0.05,
            'smooth_reaction_max': 0.21,
            'smooth_close_range': 35,
            'smooth_far_range': 250,
            'smooth_close_speed': 0.8,
            'smooth_far_speed': 1.0,
            'smooth_acceleration': 1.15,
            'smooth_deceleration': 1.05,
            'smooth_fatigue_effect': 1.2,
            'smooth_micro_corrections': 0,
            'ncaf_enabled': False,
            'ncaf_near_radius': 120.0,
            'ncaf_snap_radius': 22.0,
            'ncaf_alpha': 1.30,
            'ncaf_snap_boost': 1.25,
            'ncaf_max_step': 35.0,
            'ncaf_iou_threshold': 0.50,
            'ncaf_max_ttl': 8,
            'ncaf_show_debug': False,
            # Trigger Settings
            'trigger_enabled': False,
            'trigger_always_on': False,
            'trigger_button': 1,  # 0..4 -> Left, Right, Middle, Side4, Side5
            'trigger_mode': 1,  # 1=distance based, 2=range detection, 3=color detection
            'trigger_head_only': False,
            'trigger_radius_px': 8,
            'trigger_delay_ms': 30,
            'trigger_cooldown_ms': 120,
            'trigger_min_conf': 0.35,
            'trigger_burst_count': 3,
            'trigger_mode2_range_x': 50.0,
            'trigger_mode2_range_y': 50.0,
            'trigger_hsv_h_min': 0,
            'trigger_hsv_h_max': 179,
            'trigger_hsv_s_min': 0,
            'trigger_hsv_s_max': 255,
            'trigger_hsv_v_min': 0,
            'trigger_hsv_v_max': 255,
            'trigger_hsv_color_hex': '#a61fe0',
            'trigger_color_radius_px': 20,
            'trigger_color_delay_ms': 50,
            'trigger_color_cooldown_ms': 200,
            'aim_button_mask': False,
            'trigger_button_mask': False,
        }
        
        # Ensure all critical attributes exist
        for key, default_value in critical_attrs.items():
            if key not in self.__dict__:
                # Attribute doesn't exist, set to default
                self.__dict__[key] = default_value
            elif self.__dict__.get(key) is None and default_value is not None:
                # Attribute exists but is None, and default is not None, use default
                self.__dict__[key] = default_value
            # Special handling for dict/list types
            elif isinstance(default_value, dict) and isinstance(self.__dict__.get(key), dict):
                # Merge dictionaries, keeping loaded values but adding missing defaults
                for dk, dv in default_value.items():
                    if dk not in self.__dict__[key]:
                        self.__dict__[key][dk] = dv
            elif isinstance(default_value, list) and not isinstance(self.__dict__.get(key), list):
                # If loaded value is not a list but default is, use default
                self.__dict__[key] = default_value
    
    def get_weapon_multipliers(self, game: str, weapon: str) -> dict:
        """
        Get multipliers for a specific weapon
        Returns dict with keys: x_mult, y_mult, x_time_mult, y_time_mult
        """
        if not hasattr(self, 'rcs_weapon_multipliers') or not self.rcs_weapon_multipliers:
            self.rcs_weapon_multipliers = {}
        
        defaults = {
            'x_mult': 1.0,
            'y_mult': 1.0,
            'x_time_mult': 1.0,
            'y_time_mult': 1.0
        }
        
        if game in self.rcs_weapon_multipliers:
            if weapon in self.rcs_weapon_multipliers[game]:
                # Merge with defaults to ensure all keys exist
                result = defaults.copy()
                result.update(self.rcs_weapon_multipliers[game][weapon])
                return result
        
        return defaults
    
    def set_weapon_multipliers(self, game: str, weapon: str, x_mult: float = None, 
                               y_mult: float = None, x_time_mult: float = None, 
                               y_time_mult: float = None):
        """
        Set multipliers for a specific weapon
        Only updates provided values, preserves others
        """
        if not hasattr(self, 'rcs_weapon_multipliers') or not self.rcs_weapon_multipliers:
            self.rcs_weapon_multipliers = {}
        
        if game not in self.rcs_weapon_multipliers:
            self.rcs_weapon_multipliers[game] = {}
        
        if weapon not in self.rcs_weapon_multipliers[game]:
            self.rcs_weapon_multipliers[game][weapon] = {
                'x_mult': 1.0,
                'y_mult': 1.0,
                'x_time_mult': 1.0,
                'y_time_mult': 1.0
            }
        
        if x_mult is not None:
            self.rcs_weapon_multipliers[game][weapon]['x_mult'] = x_mult
        if y_mult is not None:
            self.rcs_weapon_multipliers[game][weapon]['y_mult'] = y_mult
        if x_time_mult is not None:
            self.rcs_weapon_multipliers[game][weapon]['x_time_mult'] = x_time_mult
        if y_time_mult is not None:
            self.rcs_weapon_multipliers[game][weapon]['y_time_mult'] = y_time_mult

        # --- Model and Detection ---
        self.models_dir = "models"
        self.model_path = os.path.join(self.models_dir, "Click here to Load a model")
        self.custom_player_label = "Select a Player Class"  
        self.custom_head_label = "Select a Head Class"  
        self.model_file_size = 0
        self.model_load_error = ""
        self.conf = 0.2
        self.imgsz = 640
        self.max_detect = 50
        
        # --- Multi-select target classes ---
        # List of player class names or numeric IDs to target; persisted in profile
        self.selected_player_classes = []
        
        # --- Per-class confidence thresholds ---
        # Mapping class_name (str) or class_id (str) -> confidence float [0.05, 0.95]
        self.class_confidence = {}
        
        # --- Mouse / MAKCU ---
        self.selected_mouse_button = 3   # Default to middle mouse button
        self.makcu_connected = False # Updated to reflect device type
        self.makcu_status_msg = "Disconnected"  # Updated to reflect device type
        self.aim_humanization = 0 # Default to no humanization
        self.in_game_sens = 1.3 # Default smoothing
        self.button_mask = False # Default to no button masking

        # --- Trigger Settings ---
        self.trigger_enabled         = getattr(self, "trigger_enabled", False)   # master on/off
        self.trigger_always_on       = getattr(self, "trigger_always_on", False) # fire even without holding key
        self.trigger_button          = getattr(self, "trigger_button", 1)        # 0..4 -> Left, Right, Middle, Side4, Side5
        self.trigger_mode            = getattr(self, "trigger_mode", 1)          # 1=distance based, 2=range detection, 3=color detection
        self.trigger_head_only       = getattr(self, "trigger_head_only", False)    # only trigger on head class detection

        self.trigger_radius_px       = getattr(self, "trigger_radius_px", 8)     # how close to crosshair (px) - Mode 1 only
        self.trigger_delay_ms        = getattr(self, "trigger_delay_ms", 30)     # delay before click
        self.trigger_cooldown_ms     = getattr(self, "trigger_cooldown_ms", 120) # time between clicks
        self.trigger_min_conf        = getattr(self, "trigger_min_conf", 0.35)   # min conf to shoot - Mode 1 only
        self.trigger_burst_count     = getattr(self, "trigger_burst_count", 3)   # shots before cooldown (Mode 2)
        
        # --- Mode 2 (Range Detection) Settings ---
        self.trigger_mode2_range_x   = getattr(self, "trigger_mode2_range_x", 50.0)   # X-axis detection range (0.5-1000)
        self.trigger_mode2_range_y   = getattr(self, "trigger_mode2_range_y", 50.0)   # Y-axis detection range (0.5-1000)
        
        # --- Mode 3 (Color) HSV Settings ---
        self.trigger_hsv_h_min       = getattr(self, "trigger_hsv_h_min", 0)     # HSV H minimum value
        self.trigger_hsv_h_max       = getattr(self, "trigger_hsv_h_max", 179)   # HSV H maximum value
        self.trigger_hsv_s_min       = getattr(self, "trigger_hsv_s_min", 0)     # HSV S minimum value
        self.trigger_hsv_s_max       = getattr(self, "trigger_hsv_s_max", 255)   # HSV S maximum value
        self.trigger_hsv_v_min       = getattr(self, "trigger_hsv_v_min", 0)     # HSV V minimum value
        self.trigger_hsv_v_max       = getattr(self, "trigger_hsv_v_max", 255)   # HSV V maximum value
        self.trigger_color_radius_px = getattr(self, "trigger_color_radius_px", 20) # color detection radius
        self.trigger_color_delay_ms  = getattr(self, "trigger_color_delay_ms", 50)  # color trigger delay
        self.trigger_color_cooldown_ms = getattr(self, "trigger_color_cooldown_ms", 200) # color trigger cooldown


        # --- Aimbot Mode ---
        self.mode = "normal"    
        self.aimbot_running = False
        self.aimbot_status_msg = "Stopped"

        # --- Normal Aim ---
        self.normal_x_speed = 0.5
        self.normal_y_speed = 0.5

        # --- Bezier Aim ---
        self.bezier_segments = 8
        self.bezier_ctrl_x = 16
        self.bezier_ctrl_y = 16

        # --- Silent Aim ---
        self.silent_segments = 7
        self.silent_ctrl_x = 18
        self.silent_ctrl_y = 18
        self.silent_speed = 3
        self.silent_cooldown = 0.05  # Reduced cooldown for faster activation
        
        # --- Enhanced Silent Mode ---
        self.silent_strength = 1.000  # Silent mode strength (0.100 = weak, 3.000 = over-reach)
        self.silent_auto_fire = False  # Auto fire when reaching target
        self.silent_fire_delay = 0.010  # Delay before firing (seconds) - Optimized for speed
        self.silent_return_delay = 0.020  # Delay before returning to origin (seconds) - Optimized for speed
        self.silent_speed_mode = True  # Enable ultra-fast speed optimizations
        self.silent_use_bezier = False  # Use bezier curve movement instead of direct movement

        # --- Smooth Aim (WindMouse) ---
        self.smooth_gravity = 9.0          # Gravitational pull towards target (1-20)
        self.smooth_wind = 3.0             # Wind randomness effect (1-20)  
        self.smooth_min_delay = 0.0      # Minimum delay between steps (seconds)
        self.smooth_max_delay = 0.002     # Maximum delay between steps (seconds)
        self.smooth_max_step = 40.0        # Maximum pixels per step
        self.smooth_min_step = 2.0         # Minimum pixels per step
        self.smooth_max_step_ratio = 0.20   # Max step as ratio of total distance
        self.smooth_target_area_ratio = 0.06  # Stop when within this ratio of distance
        
        # Human-like behavior settings
        self.smooth_reaction_min = 0.05    # Min reaction time to new targets (seconds)
        self.smooth_reaction_max = 0.21    # Max reaction time to new targets (seconds)
        self.smooth_close_range = 35       # Distance considered "close" (pixels)
        self.smooth_far_range = 250        # Distance considered "far" (pixels) 
        self.smooth_close_speed = 0.8      # Speed multiplier when close to target
        self.smooth_far_speed = 1.00        # Speed multiplier when far from target
        self.smooth_acceleration = 1.15     # Acceleration curve strength
        self.smooth_deceleration = 1.05     # Deceleration curve strength
        self.smooth_fatigue_effect = 1.2   # How much fatigue affects shakiness
        self.smooth_micro_corrections = 0  # Small random corrections (pixels)

        # --- Last error/status for GUI display
        self.last_error = ""
        self.last_info = ""

        # --- NCAF (Nonlinear Close-Aim with Focus) ---
        self.ncaf_enabled = False            # Whether NCAF mode is active (redundant with mode, kept for clarity)
        self.ncaf_near_radius = 120.0        # Pixels within which non-linear tapering starts
        self.ncaf_snap_radius = 22.0         # Inner snap radius in pixels
        self.ncaf_alpha = 1.30               # Exponent for speed falloff (alpha > 0)
        self.ncaf_snap_boost = 1.25          # Multiplier inside snap radius
        self.ncaf_max_step = 35.0            # Limit per-step movement (0 to disable)
        # Tracker params for ByteTrackLite
        self.ncaf_iou_threshold = 0.50       # IoU threshold for track matching
        self.ncaf_max_ttl = 8                # Frame TTL for tracks
        self.ncaf_show_debug = False         # Draw NCAF radii in debug window

        # --- Async save internals ---
        self._save_lock = threading.Lock()
        self._save_timer = None

        # --- Debug window toggle ---
        self.show_debug_window = False
        self.show_debug_text_info = True  # Show text information in debug window

        # --- Ndi Settings ---
        self.ndi_width = 0
        self.ndi_height = 0
        self.ndi_sources = []
        self.ndi_selected_source = None

        # --- Capture Card Settings ---
        self.capture_width = 1920              # Capture card resolution width
        self.capture_height = 1080             # Capture card resolution height
        self.capture_fps = 240                 # Target frame rate for capture card
        self.capture_device_index = 0          # Device index for capture card (0, 1, 2, etc.)
        self.capture_fourcc_preference = ["NV12", "YUY2", "MJPG"]  # Preferred fourcc formats in order
        self.capture_range_x = 0               # X-axis range (0 = use region_size, >0 = custom range)
        self.capture_range_y = 0               # Y-axis range (0 = use region_size, >0 = custom range)
        self.capture_offset_x = 0              # X-axis offset in pixels (can be negative) - offsets the crop region
        self.capture_offset_y = 0              # Y-axis offset in pixels (can be negative) - offsets the crop region
        self.capture_center_offset_x = 0       # X-axis center offset in pixels (can be negative) - offsets FOV center
        self.capture_center_offset_y = 0       # Y-axis center offset in pixels (can be negative) - offsets FOV center

        # --- UDP Settings ---
        self.udp_ip = "192.168.0.01"           # UDP stream IP address
        self.udp_port = 1234                   # UDP stream port number
        self.udp_width = 0                     # UDP stream width (set dynamically)
        self.udp_height = 0                    # UDP stream height (set dynamically)

    # -- Profile functions --
    def save(self, path="config_profile.json"):
        data = self.__dict__.copy()
        # Remove non-serializable objects (like threading.Lock, threading.Timer)
        non_serializable_keys = ['_save_lock', '_save_timer']
        for key in non_serializable_keys:
            data.pop(key, None)
        # Ensure rcs_weapon_multipliers is initialized if missing
        if 'rcs_weapon_multipliers' not in data:
            data['rcs_weapon_multipliers'] = {}
        with self._save_lock:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

    def _save_background(self, path="config_profile.json"):
        try:
            self.save(path)
        finally:
            self._save_timer = None

    def save_async(self, path="config_profile.json", delay: float = 0.2):
        """Debounced async save to avoid blocking GUI thread."""
        try:
            if self._save_timer is not None:
                try:
                    self._save_timer.cancel()
                except Exception:
                    pass
            self._save_timer = threading.Timer(delay, self._save_background, args=(path,))
            self._save_timer.daemon = True
            self._save_timer.start()
        except Exception:
            # Fallback to sync save if timer fails
            self.save(path)
    def load(self, path="config_profile.json"):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    # Store non-serializable objects before update
                    save_lock = getattr(self, '_save_lock', None)
                    save_timer = getattr(self, '_save_timer', None)
                    # Update with loaded data
                    self.__dict__.update(loaded_data)
                    # Restore non-serializable objects
                    if save_lock is not None:
                        self._save_lock = save_lock
                    if save_timer is not None:
                        self._save_timer = save_timer
                    # Ensure rcs_weapon_multipliers is initialized if missing
                    if 'rcs_weapon_multipliers' not in self.__dict__ or not self.rcs_weapon_multipliers:
                        self.rcs_weapon_multipliers = {}
            except json.JSONDecodeError as e:
                print(f"[WARNING] Failed to load config from {path}: {e}")
                print(f"[INFO] Using default configuration instead")
                # Don't try to load corrupted config, use defaults
            except Exception as e:
                print(f"[ERROR] Unexpected error loading config: {e}")
        # Always ensure all critical attributes exist (even if config file doesn't exist)
        self._ensure_default_attributes()
    def reset_to_defaults(self):
        self.__init__()

    # --- Utility ---
    def list_models(self):
        return [f for f in os.listdir(self.models_dir)
                if f.endswith(".engine")]

config = Config()
# Auto-load config if it exists and ensure all attributes are set
try:
    config.load()
except Exception as e:
    print(f"[WARNING] Failed to auto-load config: {e}")
    # Even if load fails, ensure all default attributes exist
    config._ensure_default_attributes()