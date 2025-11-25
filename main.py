import numpy as np
import time
import threading
from mouse import Mouse, is_button_pressed  # Use the thread-safe function
from capture import get_camera
from detection import load_model, perform_detection
from config import config
from windmouse_smooth import smooth_aimer
import os
import math
import cv2
import queue
import random
from NCAF import get_ncaf_controller

# --- Global state for aimbot control ---
_aimbot_running = False
_aimbot_thread = None
_capture_thread = None
_smooth_thread = None
fps = 0
frame_queue = queue.Queue(maxsize=1)
smooth_move_queue = queue.Queue(maxsize=10)  # Queue for smooth movements
makcu = None  # <-- Declare Mouse instance globally, will be initialized once
_last_trigger_time_ms = 0.0
_in_zone_since_ms = 0.0
_burst_count = 0  # Track current burst count for Mode 2
_burst_in_cooldown = False  # Track if Mode 2 is in cooldown phase

# --- Enhanced Silent Mode state ---
_silent_original_pos = None  # Store original mouse position

# --- RCS (Recoil Control System) state ---
_rcs_running = False
_rcs_thread = None
_last_left_click_state = False
_rcs_active = False
_rcs_start_time = 0
_last_rcs_x_time = 0  # Last time X compensation was applied
_last_rcs_y_time = 0  # Last time Y jitter was applied
_rcs_accumulated_x = 0.0  # Accumulated fractional X movement
_rcs_accumulated_y = 0.0  # Accumulated fractional Y movement
_silent_in_progress = False  # Flag to indicate silent mode operation in progress
_silent_last_activation = 0.0  # Timestamp of last silent activation

# --- Aimbot Y-axis tracking for RCS compensation ---
_aimbot_y_movement = 0.0  # Track Aimbot's Y-axis movement for RCS compensation
_aimbot_y_lock = threading.Lock()  # Lock for thread-safe access

def smooth_movement_loop():
    """
    Dedicated thread for executing smooth movements.
    This ensures movements are executed with precise timing.
    """
    global _aimbot_running, makcu
    print("[INFO] Smooth movement thread started")
    while _aimbot_running:
        try:
            # Get next movement from queue (blocking with timeout)
            move_data = smooth_move_queue.get(timeout=0.1)
            dx, dy, delay = move_data


            # Execute the movement
            makcu.move(dx, dy)

            # Wait for the specified delay
            if delay > 0:
                time.sleep(delay)

        except queue.Empty:
            # No movements in queue, continue
            continue
        except Exception as e:
            print(f"[ERROR] Smooth movement failed: {e}")
            time.sleep(0.01)

    print("[INFO] Smooth movement thread stopped")

def enhanced_silent_aim(target_x, target_y, screen_center_x, screen_center_y):
    """
    Enhanced Silent Mode: High-speed calculate distance to target, move to target, optionally fire, return to origin
    
    Args:
        target_x, target_y: Target position in screen coordinates
        screen_center_x, screen_center_y: Current screen center position
    """
    global _silent_original_pos, _silent_in_progress, _silent_last_activation
    
    # Fast cooldown check using perf_counter for better precision
    current_time = time.perf_counter()
    if current_time - _silent_last_activation < config.silent_cooldown:
        return False
    
    # Prevent multiple silent operations
    if _silent_in_progress:
        return False
    
    try:
        _silent_in_progress = True
        _silent_last_activation = current_time
        
        # Pre-calculate all movements for speed
        raw_dx = target_x - screen_center_x
        raw_dy = target_y - screen_center_y
        
        # Apply silent strength - use direct multiplication for speed
        dx = int(raw_dx * config.silent_strength)
        dy = int(raw_dy * config.silent_strength)
        
        # Apply mouse movement multiplier for speed control (separate X and Y)
        # Check if X-axis movement is enabled
        if getattr(config, 'mouse_movement_enabled_x', True):
            dx = int(dx * getattr(config, 'mouse_movement_multiplier_x', 1.0))
        else:
            dx = 0  # Disable X-axis movement
        
        # Check if Y-axis movement is enabled
        if getattr(config, 'mouse_movement_enabled_y', True):
            dy = int(dy * getattr(config, 'mouse_movement_multiplier_y', 1.0))
        else:
            dy = 0  # Disable Y-axis movement
        
        # Track Y-axis movement for RCS compensation
        global _aimbot_y_movement, _aimbot_y_lock
        with _aimbot_y_lock:
            _aimbot_y_movement = dy
        
        # Speed mode optimizations
        if config.silent_speed_mode:
            # ULTRA-FAST MODE: Skip all debug output and use optimized execution
            # Phase 1: Instant movement to target
            if dx | dy:  # Bitwise OR is faster than != 0 checks
                if config.silent_use_bezier:
                    # Ultra-fast bezier movement
                    makcu.move_bezier(dx, dy, config.silent_segments, config.silent_ctrl_x, config.silent_ctrl_y)
                else:
                    # Direct movement for maximum speed
                    makcu.move(dx, dy)
            
            # Phase 2: Lightning-fast auto fire sequence
            if config.silent_auto_fire:
                # Micro-sleep only if delay > 0
                config.silent_fire_delay > 0 and time.sleep(config.silent_fire_delay)
                makcu.click()
                config.silent_return_delay > 0 and time.sleep(config.silent_return_delay)
            else:
                # Instant return delay
                config.silent_return_delay > 0 and time.sleep(config.silent_return_delay)
            
            # Phase 3: Instant return to origin
            if dx | dy:
                if config.silent_use_bezier:
                    # Ultra-fast bezier return
                    makcu.move_bezier(-dx, -dy, config.silent_segments, config.silent_ctrl_x, config.silent_ctrl_y)
                else:
                    # Direct return for maximum speed
                    makcu.move(-dx, -dy)
        else:
            # STANDARD MODE: With debug output and normal execution
            if config.show_debug_text_info:
                distance = (dx*dx + dy*dy) ** 0.5  # Faster than math.sqrt
                print(f"[DEBUG] Enhanced Silent: Distance={distance:.1f}px, Movement=({dx}, {dy}), Strength={config.silent_strength:.3f}")
            
            # Phase 1: Movement to target
            if dx != 0 or dy != 0:
                if config.silent_use_bezier:
                    makcu.move_bezier(dx, dy, config.silent_segments, config.silent_ctrl_x, config.silent_ctrl_y)
                    if config.show_debug_text_info:
                        print(f"[DEBUG] Silent: Moved to target position using bezier curve")
                else:
                    makcu.move(dx, dy)
                    if config.show_debug_text_info:
                        print(f"[DEBUG] Silent: Moved to target position using direct movement")
            
            # Phase 2: Auto fire sequence
            if config.silent_auto_fire:
                if config.silent_fire_delay > 0:
                    time.sleep(config.silent_fire_delay)
                
                makcu.click()
                if config.show_debug_text_info:
                    print(f"[DEBUG] Silent: Auto fire executed")
                
                if config.silent_return_delay > 0:
                    time.sleep(config.silent_return_delay)
            else:
                if config.silent_return_delay > 0:
                    time.sleep(config.silent_return_delay)
            
            # Phase 3: Return to origin
            if dx != 0 or dy != 0:
                if config.silent_use_bezier:
                    makcu.move_bezier(-dx, -dy, config.silent_segments, config.silent_ctrl_x, config.silent_ctrl_y)
                    if config.show_debug_text_info:
                        print(f"[DEBUG] Silent: Returned to original position using bezier curve")
                else:
                    makcu.move(-dx, -dy)
                    if config.show_debug_text_info:
                        print(f"[DEBUG] Silent: Returned to original position using direct movement")
        
        return True
        
    except Exception as e:
        if config.show_debug_text_info:
            print(f"[ERROR] Enhanced silent aim error: {e}")
        return False
    finally:
        _silent_in_progress = False

def _now_ms():
    return time.perf_counter() * 1000.0

def get_crosshair_center():
    """
    Get the crosshair center position based on capture mode.
    For CaptureCard mode, calculates center based on cropped frame size, then applies center offset.
    
    Returns:
        tuple: (center_x, center_y) position
    """
    if config.capturer_mode.lower() == "capturecard":
        # For CaptureCard, the center should be based on the cropped frame size (range_x/y)
        # Get the actual crop dimensions
        range_x = int(getattr(config, "capture_range_x", 0))
        range_y = int(getattr(config, "capture_range_y", 0))
        if range_x <= 0:
            range_x = config.region_size
        if range_y <= 0:
            range_y = config.region_size
        
        # Default center is at the center of the cropped frame
        center_x = range_x / 2
        center_y = range_y / 2
        
        # Apply center offset to shift the FOV center from the default center
        center_x += int(getattr(config, "capture_center_offset_x", 0))
        center_y += int(getattr(config, "capture_center_offset_y", 0))
        
        return center_x, center_y
    elif config.capturer_mode.lower() == "mss":
        # For MSS mode, use fov_x_size/fov_y_size
        return config.fov_x_size / 2, config.fov_y_size / 2
    elif config.capturer_mode.lower() == "udp":
        return config.udp_width / 2, config.udp_height / 2
    else:  # NDI mode
        return config.ndi_width / 2, config.ndi_height / 2

def capture_loop():
    """PRODUCER: This loop runs on a dedicated CPU thread."""
    try:
        camera, _ = get_camera()
    except Exception as e:
        print(f"[ERROR] Failed to initialize camera: {e}")
        print(f"[ERROR] Please check your capture mode configuration (current: {config.capturer_mode})")
        if config.capturer_mode.lower() == "udp":
            print(f"[ERROR] UDP camera failed. Please ensure:")
            print(f"[ERROR]   1. UDP stream is running (e.g., OBS Studio)")
            print(f"[ERROR]   2. UDP IP is correct: {getattr(config, 'udp_ip', 'N/A')}")
            print(f"[ERROR]   3. UDP port is correct: {getattr(config, 'udp_port', 'N/A')}")
        # Wait a bit before exiting to allow error message to be seen
        import time
        time.sleep(2)
        return
    
    last_selected = None

    while _aimbot_running:
        try:
            try:
                config.ndi_sources = camera.list_sources()
            except Exception:
                config.ndi_sources = []

            if config.capturer_mode.lower() == "ndi":
                desired = config.ndi_selected_source

                if isinstance(desired, str) and desired in config.ndi_sources:
                    if (desired != last_selected) or not camera.connected:
                        camera.select_source(desired)
                        last_selected = desired

            image = camera.get_latest_frame()
            if image is not None:
                try:
                    frame_queue.put(image, block=False)
                except queue.Full:
                    try: frame_queue.get_nowait()
                    except queue.Empty: pass
                    try: frame_queue.put(image, block=False)
                    except queue.Full: pass

        except Exception as e:
            print(f"[ERROR] Capture loop failed: {e}")
            time.sleep(1)

    try:
        camera.stop()
    except Exception as e:
        print(f"[ERROR] Camera stop failed: {e}")
    print("[INFO] Capture loop stopped.")

def is_target_in_ncaf_range(x1, y1, x2, y2, radius):
    """
    Check if target bounding box intersects with NCAF circular radius range.
    Checks if the target's bounding box touches or intersects with the circular radius.
    
    Args:
        x1, y1, x2, y2: Target bounding box coordinates
        radius: NCAF radius (near_radius or snap_radius)
        
    Returns:
        bool: True if target bounding box intersects with the circular radius
    """
    # Get crosshair center based on capture mode (with center offset for CaptureCard)
    crosshair_center_x, crosshair_center_y = get_crosshair_center()
    
    # Find the closest point on the target bounding box to the circle center
    # Clamp the circle center coordinates to the bounding box boundaries
    closest_x = max(x1, min(crosshair_center_x, x2))
    closest_y = max(y1, min(crosshair_center_y, y2))
    
    # Calculate distance from the closest point to the circle center
    distance = math.hypot(closest_x - crosshair_center_x, closest_y - crosshair_center_y)
    
    # If the closest point is within or on the circle, the bounding box intersects with the circle
    return distance <= radius

def is_target_in_fov(x1, y1, x2, y2):
    """Check if target bounding box intersects with FOV (Field of View) area or NCAF range"""
    # If NCAF mode, check if target touches near_radius or snap_radius
    if config.mode == "ncaf":
        near_radius = float(getattr(config, 'ncaf_near_radius', 120.0))
        snap_radius = float(getattr(config, 'ncaf_snap_radius', 22.0))
        # Check if target bounding box touches either near_radius or snap_radius
        return (is_target_in_ncaf_range(x1, y1, x2, y2, near_radius) or 
                is_target_in_ncaf_range(x1, y1, x2, y2, snap_radius))
    
    # Original FOV check for other modes
    # Get FOV center with center offset applied for CaptureCard mode
    fov_center_x, fov_center_y = get_crosshair_center()
    fov_half_x = config.fov_x_size / 2
    fov_half_y = config.fov_y_size / 2
    
    # Calculate FOV rectangle bounds using separate X and Y dimensions
    fov_x1 = fov_center_x - fov_half_x
    fov_y1 = fov_center_y - fov_half_y
    fov_x2 = fov_center_x + fov_half_x
    fov_y2 = fov_center_y + fov_half_y
    
    # Check if target bounding box intersects with FOV rectangle
    # Two rectangles intersect if they overlap in both X and Y dimensions
    x_overlap = max(0, min(x2, fov_x2) - max(x1, fov_x1))
    y_overlap = max(0, min(y2, fov_y2) - max(y1, fov_y1))
    
    # If both overlaps are positive, the rectangles intersect
    return x_overlap > 0 and y_overlap > 0

def is_target_touching_boundary_mode2(x1, y1, x2, y2):
    """
    Mode 2: Check if target bounding box intersects with trigger boundary area.
    Uses rectangular boundary with separate X and Y ranges, similar to FOV X/Y size check.
    
    IMPORTANT: Mode 2 logic is simple:
    - Checks if target bounding box intersects with Range X and Y boundaries (like FOV check)
    - If intersection exists, target is considered "in range" for trigger
    - Does NOT consider Height Targeting or Deadzone
    - Only considers Delay and Cooldown for firing decision
    - Always uses Range X/Y regardless of aimbot mode (NCAF mode does not affect triggerbot)
    
    Args:
        x1, y1, x2, y2: Target bounding box coordinates
        
    Returns:
        bool: True if target bounding box intersects with the boundary area
    """
    # Get Mode 2 X/Y range from config (always use Range X/Y, not affected by aimbot mode)
    range_x = getattr(config, "trigger_mode2_range_x", 50.0)
    range_y = getattr(config, "trigger_mode2_range_y", 50.0)
    
    # Get crosshair center based on capture mode (with center offset for CaptureCard)
    crosshair_center_x, crosshair_center_y = get_crosshair_center()
    
    # Calculate rectangular boundary area around crosshair (similar to FOV calculation)
    boundary_x1 = crosshair_center_x - range_x
    boundary_y1 = crosshair_center_y - range_y
    boundary_x2 = crosshair_center_x + range_x
    boundary_y2 = crosshair_center_y + range_y
    
    # Check if target bounding box intersects with rectangular boundary area
    # This is the same logic as is_target_in_fov() - just using Range X/Y instead of FOV X/Y
    x_overlap = max(0, min(x2, boundary_x2) - max(x1, boundary_x1))
    y_overlap = max(0, min(y2, boundary_y2) - max(y1, boundary_y1))
    
    # If both overlaps are positive, the target intersects with the boundary (like FOV check)
    return x_overlap > 0 and y_overlap > 0

def get_target_selection_key(target):
    """
    Get sorting key for target selection.
    Priority: 1) Distance to screen center (closer = better), 2) Width (larger = better)
    
    Args:
        target: Target dictionary with 'dist', 'x1', 'x2' keys
        
    Returns:
        tuple: (distance, -width) for sorting (smaller is better)
    """
    dist = target.get('dist', float('inf'))
    width = target.get('x2', 0) - target.get('x1', 0)
    # Return (dist, -width) so min() will select closest, and if equal, widest
    return (dist, -width)

def process_mode2_trigger_logic(all_targets, delay_ms, cooldown_ms):
    """
    Independent Mode 2 trigger logic: boundary contact -> delay -> fire -> cooldown
    
    Mode 2 logic flow:
    1. Check if selected Target classes enter Trigger Range X and Y boundaries
    2. Consider Delay and Cooldown
    3. Decide whether to fire
    4. Does NOT consider Height Targeting or Deadzone
    
    Args:
        all_targets: List of detected targets (should be filtered by Target Classes)
        delay_ms: Delay before firing (ms)
        cooldown_ms: Cooldown after firing (ms)
        
    Returns:
        tuple: (should_fire, status_message, best_target)
    """
    global _in_zone_since_ms, _last_trigger_time_ms
    
    now = _now_ms()
    
    # Find targets that touch the boundary
    boundary_targets = []
    for target in all_targets:
        if is_target_touching_boundary_mode2(target['x1'], target['y1'], target['x2'], target['y2']):
            boundary_targets.append(target)
    
    # If no targets touching boundary, reset timing
    if not boundary_targets:
        _in_zone_since_ms = 0.0
        return False, "NO_TARGETS", None
    
    # Use NCAF target selection if mode is ncaf
    if config.mode == "ncaf":
        try:
            ctrl = get_ncaf_controller()
            ctrl.set_tracker_params(getattr(config, 'ncaf_iou_threshold', 0.5), int(getattr(config, 'ncaf_max_ttl', 8)))
            ctrl.update_tracking(boundary_targets)
            
            # Get crosshair center for NCAF selection
            if config.capturer_mode.lower() in ["mss", "capturecard"]:
                crosshair_center_x = config.fov_x_size / 2
                crosshair_center_y = config.fov_y_size / 2
            elif config.capturer_mode.lower() == "udp":
                crosshair_center_x = config.udp_width / 2
                crosshair_center_y = config.udp_height / 2
            else:
                crosshair_center_x = config.ndi_width / 2
                crosshair_center_y = config.ndi_height / 2
            
            # Use NCAF's choose_target_center to select target center
            target_center = ctrl.choose_target_center(boundary_targets, crosshair_center_x, crosshair_center_y)
            
            if target_center:
                # Find the target that contains or is closest to the chosen center
                target_cx, target_cy = target_center
                best_target = None
                min_dist = float('inf')
                
                for t in boundary_targets:
                    # Check if center is within target bbox
                    if (t['x1'] <= target_cx <= t['x2'] and 
                        t['y1'] <= target_cy <= t['y2']):
                        best_target = t
                        break
                    # Otherwise find closest target center to chosen center
                    t_cx = 0.5 * (t['x1'] + t['x2'])
                    t_cy = 0.5 * (t['y1'] + t['y2'])
                    dist = math.hypot(t_cx - target_cx, t_cy - target_cy)
                    if dist < min_dist:
                        min_dist = dist
                        best_target = t
            else:
                # Fallback to distance-based selection
                best_target = min(boundary_targets, key=get_target_selection_key)
        except Exception as e:
            print(f"[WARN] NCAF target selection failed in trigger logic: {e}, falling back to distance-based")
            best_target = min(boundary_targets, key=get_target_selection_key)
    else:
        # Select best target (closest to screen center, if equal distance then widest)
        best_target = min(boundary_targets, key=get_target_selection_key)
    
    # Check if in cooldown phase
    cooldown_ok = (now - _last_trigger_time_ms) >= cooldown_ms
    
    if not cooldown_ok:
        # In cooldown phase
        cooldown_remaining = cooldown_ms - (now - _last_trigger_time_ms)
        return False, f"COOLDOWN ({cooldown_remaining:.0f}ms)", best_target
    
    # Not in cooldown - start delay phase
    if _in_zone_since_ms == 0.0:
        _in_zone_since_ms = now
        return False, "WAITING", best_target
    
    time_in_zone = now - _in_zone_since_ms
    linger_ok = time_in_zone >= delay_ms
    
    if linger_ok:
        # Ready to fire
        return True, "FIRING", best_target
    else:
        # Still waiting
        return False, f"WAITING ({time_in_zone:.0f}/{delay_ms}ms)", best_target

def calculate_height_target_position(x1, y1, x2, y2, target_type=None):
    """
    Calculate the target position based on height targeting settings.
    Height Targeting does NOT consider Head targets - always uses center for Head.
    
    Args:
        x1, y1, x2, y2: Target bounding box coordinates
        target_type: Target type ('head', 'player', etc.). If 'head', always use center.
        
    Returns:
        tuple: (target_x, target_y) - calculated target position
    """
    # Calculate center X (always use center for X)
    target_x = (x1 + x2) / 2
    
    # Height Targeting does NOT consider Head targets - always use center for Head
    if target_type == 'head':
        # For Head targets, always use center Y position (Height Targeting does not apply)
        target_y = (y1 + y2) / 2
        return target_x, target_y
    
    # Check if height targeting is enabled
    if not getattr(config, 'height_targeting_enabled', True):
        # If height targeting is disabled, use center Y position
        target_y = (y1 + y2) / 2
    else:
        # Calculate target Y based on height setting
        target_height = config.target_height  # 0.1 = bottom, 1.0 = top
        
        # Linear interpolation between bottom and top of bounding box
        # y1 is top of box, y2 is bottom of box (screen coordinates)
        target_y = y1 + (y2 - y1) * (1.0 - target_height)
    
    return target_x, target_y

def calculate_x_center_target_position(x1, y1, x2, y2, crosshair_x, target_type=None):
    """
    Calculate the target position with X-axis center targeting and tolerance.
    Height Targeting does NOT consider Head targets.
    
    Args:
        x1, y1, x2, y2: Target bounding box coordinates
        crosshair_x: Current crosshair X position
        target_type: Target type ('head', 'player', etc.). If 'head', Height Targeting does not apply.
        
    Returns:
        tuple: (target_x, target_y) - calculated target position
    """
    # Start with standard height-based targeting (does not consider Head)
    target_x, target_y = calculate_height_target_position(x1, y1, x2, y2, target_type)
    
    # Apply X-center targeting if enabled
    if config.x_center_targeting_enabled:
        # Calculate ultra-precise center X of the player using float precision
        player_center_x = (float(x1) + float(x2)) / 2.0
        
        # If tolerance is 0%, always aim at exact center with maximum precision
        if config.x_center_tolerance_percent == 0.0:  # Exact zero tolerance - aim at exact center
            target_x = player_center_x
            print(f"[DEBUG] X-center targeting: tolerance=0%, aiming at exact center x={player_center_x:.1f}")
        else:
            # Calculate player bounding box width with precision
            player_width = float(x2) - float(x1)
            
            # Calculate tolerance zone as percentage of player width
            tolerance_pixels = (config.x_center_tolerance_percent / 100.0) * player_width
            
            # Check if crosshair is within tolerance zone of player center
            distance_from_center = abs(float(crosshair_x) - player_center_x)
            
            if distance_from_center <= tolerance_pixels:
                # Within tolerance zone - aim at player X center with precision
                target_x = player_center_x
            else:
                # Outside tolerance zone - use precise calculation toward center
                if float(crosshair_x) < player_center_x:
                    # Crosshair is left of center, aim toward left edge of tolerance zone
                    target_x = player_center_x - tolerance_pixels
                else:
                    # Crosshair is right of center, aim toward right edge of tolerance zone
                    target_x = player_center_x + tolerance_pixels
    else:
        # When X-center targeting is disabled, use center X position
        target_x = (float(x1) + float(x2)) / 2.0
    
    return target_x, target_y

def is_crosshair_at_target_boundary(crosshair_x, crosshair_y, target_x1, target_y1, target_x2, target_y2):
    """
    Check if the crosshair is at or touching the target boundary.
    Used when height targeting is disabled to stop Y movement when crosshair touches target.
    
    Args:
        crosshair_x, crosshair_y: Current crosshair position
        target_x1, target_y1, target_x2, target_y2: Target bounding box coordinates
        
    Returns:
        bool: True if crosshair is at target boundary (should stop Y movement)
    """
    # Check if crosshair is within target bounds (touching or inside)
    return (target_x1 <= crosshair_x <= target_x2 and 
            target_y1 <= crosshair_y <= target_y2)

def is_in_x_center_boundary(crosshair_x, crosshair_y, target_x1, target_y1, target_x2, target_y2):
    """
    Check if the current crosshair position is within the X-center boundary.
    Similar to height deadzone but for X-axis center targeting.
    
    Args:
        crosshair_x, crosshair_y: Current crosshair position
        target_x1, target_y1, target_x2, target_y2: Target bounding box coordinates
        
    Returns:
        bool: True if within X-center boundary (should stop X movement)
    """
    # Check if X-center targeting is enabled first
    if not getattr(config, 'x_center_targeting_enabled', False):
        return False
    
    # Calculate tolerance percentage
    tolerance_percent = getattr(config, 'x_center_tolerance_percent', 10.0)
    
    # Special case: if tolerance is 0, check if crosshair is at exact center
    if tolerance_percent == 0.0:
        # Calculate target center
        target_center_x = (target_x1 + target_x2) / 2.0
        # Apply user-defined X offset (pixels)
        target_center_x += getattr(config, 'x_center_offset_px', 0)
        
        # Check if crosshair is at the exact center (within 1 pixel tolerance for precision)
        is_at_center = (abs(crosshair_x - target_center_x) <= 1.0 and 
                       target_y1 <= crosshair_y <= target_y2)
        
        if is_at_center:
            print(f"[DEBUG] X-center boundary: crosshair at exact center (tolerance=0%, center_x={target_center_x:.1f})")
        
        return is_at_center
    
    # Normal case: use tolerance percentage
    # Calculate target width
    target_width = target_x2 - target_x1
    
    # Calculate tolerance in pixels
    tolerance_px = (tolerance_percent / 100.0) * target_width
    
    # Expand target bounds by tolerance (crosshair must be this many pixels inside)
    inner_x1 = target_x1 + tolerance_px
    inner_x2 = target_x2 - tolerance_px
    # Shift inner window by user-defined X offset (pixels)
    offset_px = getattr(config, 'x_center_offset_px', 0)
    inner_x1 += offset_px
    inner_x2 += offset_px
    
    # Check if crosshair is within the inner boundary (with tolerance)
    is_within_boundary = (inner_x1 <= crosshair_x <= inner_x2 and 
                         target_y1 <= crosshair_y <= target_y2)
    
    if is_within_boundary:
        print(f"[DEBUG] X-center boundary: crosshair within boundary (tolerance={tolerance_percent:.1f}% = {tolerance_px:.1f}px)")
    
    return is_within_boundary

def is_in_height_deadzone(current_y, target_y, box_height, box_width=None):
    """
    Check if the current crosshair Y position is within the height deadzone.
    Deadzone is calculated relative to Target Height position:
    - Deadzone Max: Target Height Y-axis upwards
    - Deadzone Min: Target Height Y-axis downwards
    
    Args:
        current_y: Current crosshair Y position
        target_y: Target Y position (Target Height)
        box_height: Height of the target bounding box
        
    Returns:
        bool: True if in deadzone (should only move X-axis)
    """
    # Check if height targeting is enabled first
    if not getattr(config, 'height_targeting_enabled', True):
        return False
    
    if not config.height_deadzone_enabled:
        return False
    
    # Calculate deadzone bounds relative to Target Height
    # Target Height is the center of the deadzone
    deadzone_center = target_y
    
    # Calculate base deadzone range based on box height
    # Deadzone Max is upwards from Target Height
    # Deadzone Min is downwards from Target Height
    base_deadzone_max = config.height_deadzone_max * box_height  # Upwards from center
    base_deadzone_min = config.height_deadzone_min * box_height  # Downwards from center

    # Dynamic scaling: wider box (closer) -> lower offset; narrower (farther) -> higher offset
    # Use a simple inverse scale around a nominal width of 200px
    nominal_width = 200.0
    if box_width is None or box_width <= 0:
        scale = 1.0
    else:
        scale = nominal_width / float(box_width)
        # Clamp scaling to reasonable bounds
        scale = max(0.5, min(2.0, scale))

    # Apply scale and cap by head ratio (max fraction of box height)
    HEAD_RATIO_CAP = 0.235
    max_cap = HEAD_RATIO_CAP * box_height
    deadzone_max_offset = min(base_deadzone_max * scale, max_cap)
    deadzone_min_offset = min(base_deadzone_min * scale, max_cap)
    
    # Calculate deadzone boundaries
    deadzone_max_y = deadzone_center - deadzone_max_offset  # Upwards (smaller Y values)
    deadzone_min_y = deadzone_center + deadzone_min_offset  # Downwards (larger Y values)
    
    # Apply tolerance for "full entry" - crosshair must be this many pixels inside the deadzone
    tolerance = config.height_deadzone_tolerance
    deadzone_inner_max = deadzone_max_y + tolerance  # Inner boundary (closer to center)
    deadzone_inner_min = deadzone_min_y - tolerance  # Inner boundary (closer to center)
    
    # Check if current Y is within deadzone (with tolerance)
    # Handle both cases: normal (max_y < min_y) and inverted (min_y < max_y)
    if deadzone_max_y <= deadzone_min_y:
        # Normal case: Max is above Min
        is_within_deadzone = deadzone_inner_max <= current_y <= deadzone_inner_min
        is_touching_edge = deadzone_max_y <= current_y <= deadzone_min_y
    else:
        # Inverted case: Min is above Max (Min > Max values)
        is_within_deadzone = deadzone_inner_min <= current_y <= deadzone_inner_max
        is_touching_edge = deadzone_min_y <= current_y <= deadzone_max_y
    
    if is_within_deadzone:
        print(f"[DEBUG] In deadzone: current_y={current_y:.1f}, deadzone_bounds=[{deadzone_max_y:.1f}, {deadzone_min_y:.1f}], inner_bounds=[{deadzone_inner_max:.1f}, {deadzone_inner_min:.1f}]")
    elif is_touching_edge:
        print(f"[DEBUG] Touching deadzone edge: current_y={current_y:.1f}, tolerance={tolerance:.1f}px needed")
    
    return is_within_deadzone

def detection_and_aim_loop():
    """CONSUMER: This loop runs on the main aimbot thread, utilizing the GPU."""
    global _aimbot_running, fps, makcu, _aimbot_y_movement, _aimbot_y_lock, _rcs_active
    model, class_names = load_model(config.model_path)
    
    # Check if model loaded successfully
    if model is None:
        error_msg = getattr(config, "model_load_error", "Unknown error")
        print(f"[ERROR] Failed to load model: {error_msg}")
        print(f"[ERROR] Model path: {config.model_path}")
        print(f"[ERROR] Please check if the model file exists and is valid.")
        print(f"[ERROR] Aimbot thread will exit.")
        return
    
    # makcu is already initialized in start_aimbot

    frame_count = 0
    start_time = time.perf_counter()  # Use a more precise clock
    debug_window_moved = False  # Track if debug window has been moved

    while _aimbot_running:
        try:
            image = frame_queue.get(timeout=1)
        except queue.Empty:
            print("[WARN] Frame queue is empty. Capture thread may have stalled.")
            continue
        # Get crosshair center position (with center offset for CaptureCard)
        crosshair_center_x, crosshair_center_y = get_crosshair_center()
        
        if config.capturer_mode.lower() == "capturecard":
            # For CaptureCard, region is the cropped frame itself (no additional offset needed)
            region_left = 0
            region_top = 0
            crosshair_x = crosshair_center_x
            crosshair_y = crosshair_center_y
        elif config.capturer_mode.lower() == "mss":
            region_left = (config.screen_width - config.fov_x_size) // 2
            region_top  = (config.screen_height - config.fov_y_size) // 2
            crosshair_x = region_left + crosshair_center_x
            crosshair_y = region_top + crosshair_center_y
        elif config.capturer_mode.lower() == "udp":
            # For UDP, region is the UDP frame itself
            region_left = 0
            region_top = 0
            crosshair_x = crosshair_center_x
            crosshair_y = crosshair_center_y
        else:  # NDI mode
            region_left = (config.main_pc_width - config.ndi_width) // 2
            region_top  = (config.main_pc_height - config.ndi_height) // 2
            crosshair_x = region_left + crosshair_center_x
            crosshair_y = region_top + crosshair_center_y
        if config.button_mask:
            Mouse.mask_manager_tick(selected_idx=config.selected_mouse_button, aimbot_running=is_aimbot_running())
            Mouse.mask_manager_tick(selected_idx=config.trigger_button, aimbot_running=is_aimbot_running())
        else:
            Mouse.mask_manager_tick(selected_idx=config.selected_mouse_button, aimbot_running=False)
            Mouse.mask_manager_tick(selected_idx=config.trigger_button, aimbot_running=False)

        
        all_targets = []
        debug_image = image.copy() if config.show_debug_window else None
        detected_classes = set()  # Track what classes are being detected

        results = perform_detection(model, image)

        # --- Target Processing Logic ---
        if results:
            for result in results:
                if result.boxes is None: continue
                for box in result.boxes:
                    coords = [val.item() for val in box.xyxy[0]]
                    if any(math.isnan(c) for c in coords):
                        print("[WARN] Skipping box with NaN coords:", coords)
                        continue

                    x1, y1, x2, y2 = [int(c) for c in coords]
                    conf = float(box.conf[0].item())
                    cls = int(box.cls[0].item())
                    class_name = class_names.get(cls, f"class_{cls}")

                    # Debug: Track all detected classes
                    detected_classes.add(class_name)
                    
                    # Debug: Log all detected classes for Head Only debugging
                    if getattr(config, "trigger_head_only", False):
                        head_label = getattr(config, "custom_head_label", None)
                        if head_label and str(head_label).lower() != "none":
                            # Check if this class might be a head target
                            class_name_str = str(class_name)
                            head_label_str = str(head_label)
                            if (class_name_str == head_label_str or 
                                (len(head_label_str) > 1 and not head_label_str.isdigit() and 
                                 head_label_str.lower() in class_name_str.lower())):
                                print(f"[DEBUG] Potential head target detected: class='{class_name}', conf={conf:.2f}, cls={cls}")



                    # Check if this detection should be a target
                    is_target = False
                    target_type = "unknown"

                    # Per-class confidence threshold (fallback to global)
                    class_name_str = str(class_name)
                    per_class_map = getattr(config, "class_confidence", {}) or {}
                    try:
                        threshold = float(per_class_map.get(class_name_str, config.conf))
                    except Exception:
                        threshold = float(config.conf)
                    if conf < threshold:
                        # Below threshold: skip further processing of this box
                        continue

                    # Handle both string class names and numeric IDs
                    player_label = config.custom_player_label
                    head_label = config.custom_head_label

                    # Convert to string for comparison if needed
                    class_name_str = str(class_name)
                    player_label_str = str(player_label) if player_label is not None else None
                    head_label_str = str(head_label) if head_label is not None else None

                    # IMPORTANT: Check head first if head_label is set, to ensure head targets are correctly identified
                    # This is critical for Head Only functionality
                    # Head targets should be checked BEFORE player targets to avoid being misclassified
                    target_type = None
                    is_target = False
                    
                    # First, check if this is a head target (priority check for Head Only)
                    if head_label_str:
                        # Check exact match first
                        if class_name_str == head_label_str or str(cls) == head_label_str:
                            is_target = True
                            target_type = "head"
                            print(f"[DEBUG] Head target detected: '{class_name}' matches Head Class '{head_label_str}'")
                        # Check partial match
                        elif len(head_label_str) > 1 and not head_label_str.isdigit():
                            if head_label_str.lower() in class_name_str.lower():
                                is_target = True
                                target_type = "head"
                                print(f"[DEBUG] Head target detected (partial): '{class_name}' contains '{head_label_str}'")
                    
                    # Then check if this is a player target (only if not already identified as head)
                    if not is_target:
                        # Multi-select support: if a list of player classes is configured, prefer it
                        selected_players = getattr(config, "selected_player_classes", []) or []
                        if selected_players:
                            selected_set = set(str(s) for s in selected_players)
                            if class_name_str in selected_set or str(cls) in selected_set:
                                is_target = True
                                target_type = "player"
                        # Check for exact matches (both string and numeric) when no multi-select configured
                        elif class_name_str == player_label_str:
                            is_target = True
                            target_type = "player"
                        # Also check if the class ID matches directly
                        elif str(cls) == player_label_str:
                            is_target = True
                            target_type = "player"
                        # Fallback: partial string matching for text classes
                        elif player_label_str and len(player_label_str) > 1:  # Only for non-numeric
                            if not player_label_str.isdigit() and player_label_str.lower() in class_name_str.lower():
                                is_target = True
                                target_type = "player"
                                print(f"[DEBUG] Partial match for player: '{class_name}' contains '{player_label}'")

                    if is_target:
                        center_x = (x1 + x2) / 2
                        center_y = (y1 + y2) / 2

                        # Adjust for headshot
                        if target_type == "player":
                            center_x = (x1 + x2) / 2
                            center_y = y1 + config.player_y_offset

                        # Calculate distance from crosshair (with center offset for CaptureCard)
                        crosshair_x, crosshair_y = get_crosshair_center()
                        dist = math.hypot(center_x - crosshair_x, center_y - crosshair_y)
                        all_targets.append({
                            'dist': dist, 
                            'center_x': center_x, 
                            'center_y': center_y,
                            'x1': x1,
                            'y1': y1,
                            'x2': x2,
                            'y2': y2,
                            'type': target_type,
                            'class': class_name,
                            'class_name': class_name,
                            'conf': conf
                        })

                        

                    # Draw debug boxes
                    if debug_image is not None:
                        if is_target:
                            # Check if this target intersects with FOV
                            intersects_fov = is_target_in_fov(x1, y1, x2, y2)
                            
                            # Green for player, red for head (bright if in FOV, dim if outside)
                            if target_type == "player":
                                color = (0, 255, 0) if intersects_fov else (0, 128, 0)
                            else:
                                color = (0, 0, 255) if intersects_fov else (0, 0, 128)
                            thickness = 3
                        else:
                            # Yellow for non-targets
                            color = (0, 255, 255)
                            thickness = 1

                        cv2.rectangle(debug_image, (x1, y1), (x2, y2), color, thickness)

                        # Label with class name and confidence
                        label = f"{class_name} {conf:.2f}"
                        if is_target:
                            label += f" [{target_type.upper()}]"
                            # Add FOV status to label
                            if is_target_in_fov(x1, y1, x2, y2):
                                label += " [IN-FOV]"

                        cv2.putText(debug_image, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        
                        # Draw height targeting visualization
                        if is_target and debug_image is not None:
                            # Calculate target position based on height setting and X-center targeting
                            # Height Targeting does NOT consider Head targets
                            # Use target_type variable that's already defined in this scope
                            crosshair_x, _ = get_crosshair_center()
                            target_x, target_y = calculate_x_center_target_position(x1, y1, x2, y2, crosshair_x, target_type)
                            
                            # Draw target point (red circle)
                            cv2.circle(debug_image, (int(target_x), int(target_y)), 4, (0, 0, 255), -1)
                            
                            # Draw height deadzone if enabled
                            if getattr(config, 'height_targeting_enabled', True) and config.height_deadzone_enabled:
                                box_height = y2 - y1
                                box_width = x2 - x1

                                # Dynamic offsets with scaling and head ratio cap
                                nominal_width = 200.0
                                scale = nominal_width / float(box_width) if box_width > 0 else 1.0
                                scale = max(0.5, min(2.0, scale))
                                HEAD_RATIO_CAP = 0.235
                                max_cap = HEAD_RATIO_CAP * box_height
                                base_max = config.height_deadzone_max * box_height
                                base_min = config.height_deadzone_min * box_height
                                deadzone_max_offset = min(base_max * scale, max_cap)
                                deadzone_min_offset = min(base_min * scale, max_cap)

                                # Calculate deadzone boundaries
                                deadzone_max_y = target_y - deadzone_max_offset  # Upwards (smaller Y values)
                                deadzone_min_y = target_y + deadzone_min_offset  # Downwards (larger Y values)

                                # Calculate inner bounds for "full entry"
                                tolerance = config.height_deadzone_tolerance
                                deadzone_inner_max = deadzone_max_y + tolerance  # Inner boundary (closer to center)
                                deadzone_inner_min = deadzone_min_y - tolerance  # Inner boundary (closer to center)
                                
                                # Draw outer deadzone (touching range) - light yellow
                                overlay1 = debug_image.copy()
                                if deadzone_max_y <= deadzone_min_y:
                                    # Normal case: Max is above Min
                                    cv2.rectangle(overlay1, (x1, int(deadzone_max_y)), (x2, int(deadzone_min_y)), (0, 255, 255), -1)
                                else:
                                    # Inverted case: Min is above Max
                                    cv2.rectangle(overlay1, (x1, int(deadzone_min_y)), (x2, int(deadzone_max_y)), (0, 255, 255), -1)
                                cv2.addWeighted(debug_image, 0.85, overlay1, 0.15, 0, debug_image)
                                
                                # Draw inner deadzone (full entry range) - brighter yellow
                                if deadzone_max_y <= deadzone_min_y:
                                    # Normal case
                                    if deadzone_inner_max < deadzone_inner_min:  # Only draw if tolerance doesn't exceed deadzone size
                                        overlay2 = debug_image.copy()
                                        cv2.rectangle(overlay2, (x1, int(deadzone_inner_max)), (x2, int(deadzone_inner_min)), (0, 255, 255), -1)
                                        cv2.addWeighted(debug_image, 0.7, overlay2, 0.3, 0, debug_image)
                                else:
                                    # Inverted case
                                    if deadzone_inner_min < deadzone_inner_max:  # Only draw if tolerance doesn't exceed deadzone size
                                        overlay2 = debug_image.copy()
                                        cv2.rectangle(overlay2, (x1, int(deadzone_inner_min)), (x2, int(deadzone_inner_max)), (0, 255, 255), -1)
                                        cv2.addWeighted(debug_image, 0.7, overlay2, 0.3, 0, debug_image)
                                
                                # Draw deadzone borders
                                cv2.line(debug_image, (x1, int(deadzone_max_y)), (x2, int(deadzone_max_y)), (0, 255, 255), 2)
                                cv2.line(debug_image, (x1, int(deadzone_min_y)), (x2, int(deadzone_min_y)), (0, 255, 255), 2)
                                
                                # Draw inner borders (full entry bounds) with different style
                                if deadzone_max_y <= deadzone_min_y:
                                    # Normal case
                                    if deadzone_inner_max < deadzone_inner_min:
                                        cv2.line(debug_image, (x1, int(deadzone_inner_max)), (x2, int(deadzone_inner_max)), (0, 200, 255), 1)
                                        cv2.line(debug_image, (x1, int(deadzone_inner_min)), (x2, int(deadzone_inner_min)), (0, 200, 255), 1)
                                else:
                                    # Inverted case
                                    if deadzone_inner_min < deadzone_inner_max:
                                        cv2.line(debug_image, (x1, int(deadzone_inner_min)), (x2, int(deadzone_inner_min)), (0, 200, 255), 1)
                                        cv2.line(debug_image, (x1, int(deadzone_inner_max)), (x2, int(deadzone_inner_max)), (0, 200, 255), 1)

        # --- Target Selection and Aiming (Only when button is held) ---
        button_held = is_button_pressed(config.selected_mouse_button)
        if all_targets and button_held:
            # Filter out Head targets for Normal/Bezier/Silent/Smooth modes (only consider Target classes)
            # NCAF mode can consider all targets including Head
            if config.mode in ["normal", "bezier", "silent", "smooth"]:
                # Exclude Head targets for these modes - only consider Target classes
                aimbot_targets = [t for t in all_targets if t.get('type') != 'head']
                # If no non-head targets available, fall back to all targets
                if not aimbot_targets:
                    aimbot_targets = all_targets
            else:
                # NCAF mode can consider all targets
                aimbot_targets = all_targets
            
            # Use NCAF target selection if mode is ncaf
            if config.mode == "ncaf":
                try:
                    ctrl = get_ncaf_controller()
                    ctrl.set_tracker_params(getattr(config, 'ncaf_iou_threshold', 0.5), int(getattr(config, 'ncaf_max_ttl', 8)))
                    ctrl.update_tracking(aimbot_targets)
                    
                    # Filter targets within FOV for NCAF selection
                    fov_targets = [t for t in aimbot_targets if is_target_in_fov(t['x1'], t['y1'], t['x2'], t['y2'])]
                    
                    if fov_targets:
                        # Use NCAF's choose_target_center to select target center
                        target_center = ctrl.choose_target_center(fov_targets, crosshair_x, crosshair_y)
                        
                        if target_center:
                            # Find the target that contains or is closest to the chosen center
                            target_cx, target_cy = target_center
                            best_target = None
                            min_dist = float('inf')
                            
                            for t in fov_targets:
                                # Check if center is within target bbox
                                if (t['x1'] <= target_cx <= t['x2'] and 
                                    t['y1'] <= target_cy <= t['y2']):
                                    best_target = t
                                    break
                                # Otherwise find closest target center to chosen center
                                t_cx = 0.5 * (t['x1'] + t['x2'])
                                t_cy = 0.5 * (t['y1'] + t['y2'])
                                dist = math.hypot(t_cx - target_cx, t_cy - target_cy)
                                if dist < min_dist:
                                    min_dist = dist
                                    best_target = t
                        else:
                            # Fallback to distance-based selection
                            best_target = min(fov_targets, key=lambda t: t['dist'])
                    else:
                        # No targets in FOV, use distance-based selection from filtered targets
                        best_target = min(aimbot_targets, key=lambda t: t['dist'])
                except Exception as e:
                    print(f"[WARN] NCAF target selection failed: {e}, falling back to distance-based")
                    best_target = min(aimbot_targets, key=lambda t: t['dist'])
            else:
                # Use distance-based selection for other modes (exclude Head targets)
                best_target = min(aimbot_targets, key=lambda t: t['dist'])

            # Check if the best target is within FOV before moving mouse
            if is_target_in_fov(best_target['x1'], best_target['y1'], best_target['x2'], best_target['y2']):
                # Use height targeting system and X-center targeting to calculate precise target position
                # For CaptureCard and UDP, coordinates are already in the frame coordinate system
                # For MSS and NDI, we need to convert to region coordinates
                if config.capturer_mode.lower() in ["capturecard", "udp"]:
                    # Already in frame coordinates, no conversion needed
                    target_x, target_y = calculate_x_center_target_position(
                        best_target['x1'], best_target['y1'], 
                        best_target['x2'], best_target['y2'],
                        crosshair_x,  # crosshair_x is already in frame coordinates
                        best_target.get('type', None)
                    )
                    target_screen_x = target_x
                    target_screen_y = target_y
                else:
                    # For MSS and NDI, convert to region coordinates
                    target_x, target_y = calculate_x_center_target_position(
                        best_target['x1'], best_target['y1'], 
                        best_target['x2'], best_target['y2'],
                        crosshair_x - region_left,  # Convert crosshair position to region coordinates
                        best_target.get('type', None)
                    )
                    target_screen_x = region_left + target_x
                    target_screen_y = region_top + target_y
                
                # Apply user-defined X offset to target position (applies to all modes)
                x_offset = float(getattr(config, 'x_center_offset_px', 0))
                target_screen_x += x_offset

                dx = target_screen_x - crosshair_x
                dy = target_screen_y - crosshair_y
                
                # Height Targeting does NOT consider Head targets
                target_type = best_target.get('type', None)
                
                # Check if height targeting is disabled and crosshair is at target boundary
                if not getattr(config, 'height_targeting_enabled', True) or target_type == 'head':
                    # When height targeting is disabled OR target is Head, stop Y movement if crosshair touches target
                    # For CaptureCard and UDP, coordinates are already in frame coordinates
                    if config.capturer_mode.lower() in ["capturecard", "udp"]:
                        target_x1, target_y1 = best_target['x1'], best_target['y1']
                        target_x2, target_y2 = best_target['x2'], best_target['y2']
                    else:
                        target_x1 = best_target['x1'] + region_left
                        target_y1 = best_target['y1'] + region_top
                        target_x2 = best_target['x2'] + region_left
                        target_y2 = best_target['y2'] + region_top
                    
                    if is_crosshair_at_target_boundary(crosshair_x, crosshair_y, 
                                                      target_x1, target_y1,
                                                      target_x2, target_y2):
                        dy = 0
                        if target_type == 'head':
                            print(f"[DEBUG] Head target - Height targeting does not apply, Y movement stopped: dx={dx:.1f}")
                        else:
                            print(f"[DEBUG] Height targeting disabled - crosshair at target boundary, Y movement stopped: dx={dx:.1f}")
                    else:
                        if target_type == 'head':
                            print(f"[DEBUG] Head target - Height targeting does not apply, normal movement: dx={dx:.1f}, dy={dy:.1f}")
                        else:
                            print(f"[DEBUG] Height targeting disabled - normal movement: dx={dx:.1f}, dy={dy:.1f}")
                else:
                    # Height targeting enabled - use existing deadzone logic (only for non-Head targets)
                    box_height = best_target['y2'] - best_target['y1']
                    box_width = best_target['x2'] - best_target['x1']
                    # For CaptureCard and UDP, coordinates are already in frame coordinates
                    if config.capturer_mode.lower() in ["capturecard", "udp"]:
                        current_y = crosshair_y
                    else:
                        current_y = crosshair_y - region_top
                    target_relative_y = target_y
                    
                    if is_in_height_deadzone(current_y, target_relative_y, box_height, box_width=box_width):
                        # In deadzone: only move X-axis, set Y movement to zero
                        dy = 0
                        print(f"[DEBUG] In height deadzone - X only movement: dx={dx:.1f}")
                    else:
                        print(f"[DEBUG] Normal movement: dx={dx:.1f}, dy={dy:.1f}")
                
                # Check X-center targeting behavior
                if getattr(config, 'x_center_targeting_enabled', False):
                    # When X-center targeting is enabled, stop X movement if crosshair is within boundary
                    # For CaptureCard and UDP, coordinates are already in frame coordinates
                    if config.capturer_mode.lower() in ["capturecard", "udp"]:
                        target_x1, target_y1 = best_target['x1'], best_target['y1']
                        target_x2, target_y2 = best_target['x2'], best_target['y2']
                    else:
                        target_x1 = best_target['x1'] + region_left
                        target_y1 = best_target['y1'] + region_top
                        target_x2 = best_target['x2'] + region_left
                        target_y2 = best_target['y2'] + region_top
                    
                    if is_in_x_center_boundary(crosshair_x, crosshair_y, 
                                               target_x1, target_y1,
                                               target_x2, target_y2):
                        dx = 0
                        print(f"[DEBUG] X-center targeting enabled - crosshair within boundary, X movement stopped: dy={dy:.1f}")
                    else:
                        print(f"[DEBUG] X-center targeting enabled - crosshair outside boundary, normal movement: dx={dx:.1f}, dy={dy:.1f}")
                else:
                    # When X-center targeting is disabled, stop X movement if crosshair touches target
                    # For CaptureCard and UDP, coordinates are already in frame coordinates
                    if config.capturer_mode.lower() in ["capturecard", "udp"]:
                        target_x1, target_y1 = best_target['x1'], best_target['y1']
                        target_x2, target_y2 = best_target['x2'], best_target['y2']
                    else:
                        target_x1 = best_target['x1'] + region_left
                        target_y1 = best_target['y1'] + region_top
                        target_x2 = best_target['x2'] + region_left
                        target_y2 = best_target['y2'] + region_top
                    
                    if is_crosshair_at_target_boundary(crosshair_x, crosshair_y, 
                                                      target_x1, target_y1,
                                                      target_x2, target_y2):
                        dx = 0
                        print(f"[DEBUG] X-center targeting disabled - crosshair at target boundary, X movement stopped: dy={dy:.1f}")
                    else:
                        print(f"[DEBUG] X-center targeting disabled - normal movement: dx={dx:.1f}, dy={dy:.1f}")

                # Apply NCAF movement if selected mode (tracking already updated during target selection)
                if config.mode == "ncaf":
                    try:
                        ctrl = get_ncaf_controller()
                        # X offset is already applied earlier for all modes
                        nc_dx, nc_dy = ctrl.compute_ncaf_delta(
                            dx, dy,
                            float(getattr(config, 'ncaf_near_radius', 120.0)),
                            float(getattr(config, 'ncaf_snap_radius', 22.0)),
                            float(getattr(config, 'ncaf_alpha', 1.30)),
                            float(getattr(config, 'ncaf_snap_boost', 1.25)),
                            float(getattr(config, 'ncaf_max_step', 35.0)),
                        )
                        dx, dy = nc_dx, nc_dy
                        # Respect X-center boundary: stop X if inside boundary
                        if getattr(config, 'x_center_targeting_enabled', False):
                            # For CaptureCard and UDP, coordinates are already in frame coordinates
                            if config.capturer_mode.lower() in ["capturecard", "udp"]:
                                target_x1, target_y1 = best_target['x1'], best_target['y1']
                                target_x2, target_y2 = best_target['x2'], best_target['y2']
                            else:
                                target_x1 = best_target['x1'] + region_left
                                target_y1 = best_target['y1'] + region_top
                                target_x2 = best_target['x2'] + region_left
                                target_y2 = best_target['y2'] + region_top
                            
                            if is_in_x_center_boundary(crosshair_x, crosshair_y,
                                                       target_x1, target_y1,
                                                       target_x2, target_y2):
                                dx = 0
                    except Exception as e:
                        print(f"[WARN] NCAF movement calculation failed: {e}")

                # Apply im-game-sensitivity scaling
                sens = config.in_game_sens
                distance = 1.07437623 * math.pow(sens, -0.9936827126)
                # Apply distance scaling
                dx *= distance
                dy *= distance
                
                # Check if RCS disable Y-axis is enabled and RCS is actually active (shooting)
                if getattr(config, 'rcs_disable_y_axis', False) and _rcs_active:
                    # If RCS is actually active (pressing left button) and disable Y-axis is enabled, stop Y-axis movement
                    dy = 0
                    print(f"[DEBUG] RCS disable Y-axis: Aimbot Y movement stopped (RCS active)")
                
                # Apply mouse movement multiplier for speed control
                # Apply X-axis movement multiplier if enabled
                if getattr(config, 'mouse_movement_enabled_x', True):
                    dx *= getattr(config, 'mouse_movement_multiplier_x', 1.0)
                else:
                    dx = 0  # Disable X-axis movement
                
                # Apply Y-axis movement multiplier if enabled
                if getattr(config, 'mouse_movement_enabled_y', True):
                    dy *= getattr(config, 'mouse_movement_multiplier_y', 1.0)
                else:
                    dy = 0  # Disable Y-axis movement

                # Track Aimbot Y-axis movement for RCS compensation
                global _aimbot_y_movement, _aimbot_y_lock
                with _aimbot_y_lock:
                    _aimbot_y_movement = dy  # Store current Y movement for RCS to use
               
                if config.mode == "normal":
                    # Apply x,y speeds scaling
                    dx *= config.normal_x_speed
                    dy *= config.normal_y_speed
                    makcu.move(dx, dy)
                    # Update tracked Y movement after scaling
                    with _aimbot_y_lock:
                        _aimbot_y_movement = dy
                elif config.mode == "bezier":
                    makcu.move_bezier(dx, dy, config.bezier_segments, config.bezier_ctrl_x, config.bezier_ctrl_y)
                    # Update tracked Y movement
                    with _aimbot_y_lock:
                        _aimbot_y_movement = dy
                elif config.mode == "silent":
                    # Enhanced Silent Mode: calculate target position and execute silent aim
                    # Get screen center coordinates (current crosshair position)
                    screen_center_x = crosshair_x
                    screen_center_y = crosshair_y
                    
                    # Enhanced Silent Mode uses target position, not relative movement
                    # X offset is already applied to target_screen_x earlier
                    enhanced_silent_aim(target_screen_x, target_screen_y, screen_center_x, screen_center_y)
                    # Note: enhanced_silent_aim handles its own movement, Y tracking is done inside
                elif config.mode == "smooth":
                    # Use smooth aiming with WindMouse algorithm
                    
                    path = smooth_aimer.calculate_smooth_path(dx, dy, config)

                    # Add all movements to the smooth movement queue
                    movements_added = 0
                    total_smooth_dy = 0
                    for move_dx, move_dy, delay in path:
                        if not smooth_move_queue.full():
                            smooth_move_queue.put((move_dx, move_dy, delay))
                            movements_added += 1
                            total_smooth_dy += move_dy
                            if movements_added <= 5:  # Only print first few to avoid spam
                                print(f"[DEBUG] Added movement: ({move_dx}, {move_dy}) with delay {delay:.3f}")
                        else:
                            # If queue is full, clear it and add this movement
                            print("[DEBUG] Queue full, clearing and adding movement")
                            try:
                                while not smooth_move_queue.empty():
                                    smooth_move_queue.get_nowait()
                            except queue.Empty:
                                pass
                            smooth_move_queue.put((move_dx, move_dy, delay))
                            total_smooth_dy += move_dy
                            movements_added += 1
                            break

                    print(f"[DEBUG] Added {movements_added} movements to queue")
                    # Update tracked Y movement with total smooth movement
                    with _aimbot_y_lock:
                        _aimbot_y_movement = total_smooth_dy if total_smooth_dy != 0 else dy

                    # Fallback: if no smooth movements generated, use direct movement
                    if len(path) == 0:
                        print("[DEBUG] No smooth path generated, using direct movement")
                        makcu.move(dx, dy)
                        with _aimbot_y_lock:
                            _aimbot_y_movement = dy
                elif config.mode == "ncaf":
                    # Direct device move after NCAF delta
                    makcu.move(dx, dy)
                    # Update tracked Y movement
                    with _aimbot_y_lock:
                        _aimbot_y_movement = dy
            # else: target is outside FOV, don't move mouse

        elif all_targets and config.always_on_aim:
            # Filter out Head targets for Normal/Bezier/Silent/Smooth modes (only consider Target classes)
            # NCAF mode can consider all targets including Head
            if config.mode in ["normal", "bezier", "silent", "smooth"]:
                # Exclude Head targets for these modes - only consider Target classes
                aimbot_targets = [t for t in all_targets if t.get('type') != 'head']
                # If no non-head targets available, fall back to all targets
                if not aimbot_targets:
                    aimbot_targets = all_targets
            else:
                # NCAF mode can consider all targets
                aimbot_targets = all_targets
            
            # Use NCAF target selection if mode is ncaf
            if config.mode == "ncaf":
                try:
                    ctrl = get_ncaf_controller()
                    ctrl.set_tracker_params(getattr(config, 'ncaf_iou_threshold', 0.5), int(getattr(config, 'ncaf_max_ttl', 8)))
                    ctrl.update_tracking(aimbot_targets)
                    
                    # Filter targets within FOV for NCAF selection
                    fov_targets = [t for t in aimbot_targets if is_target_in_fov(t['x1'], t['y1'], t['x2'], t['y2'])]
                    
                    if fov_targets:
                        # Use NCAF's choose_target_center to select target center
                        target_center = ctrl.choose_target_center(fov_targets, crosshair_x, crosshair_y)
                        
                        if target_center:
                            # Find the target that contains or is closest to the chosen center
                            target_cx, target_cy = target_center
                            best_target = None
                            min_dist = float('inf')
                            
                            for t in fov_targets:
                                # Check if center is within target bbox
                                if (t['x1'] <= target_cx <= t['x2'] and 
                                    t['y1'] <= target_cy <= t['y2']):
                                    best_target = t
                                    break
                                # Otherwise find closest target center to chosen center
                                t_cx = 0.5 * (t['x1'] + t['x2'])
                                t_cy = 0.5 * (t['y1'] + t['y2'])
                                dist = math.hypot(t_cx - target_cx, t_cy - target_cy)
                                if dist < min_dist:
                                    min_dist = dist
                                    best_target = t
                        else:
                            # Fallback to distance-based selection
                            best_target = min(fov_targets, key=lambda t: t['dist'])
                    else:
                        # No targets in FOV, use distance-based selection from filtered targets
                        best_target = min(aimbot_targets, key=lambda t: t['dist'])
                except Exception as e:
                    print(f"[WARN] NCAF target selection failed in always_on mode: {e}, falling back to distance-based")
                    best_target = min(aimbot_targets, key=lambda t: t['dist'])
            else:
                # Use distance-based selection for other modes (exclude Head targets)
                best_target = min(aimbot_targets, key=lambda t: t['dist'])

            # Check if the best target is within FOV before moving mouse
            if is_target_in_fov(best_target['x1'], best_target['y1'], best_target['x2'], best_target['y2']):
                # Use height targeting system and X-center targeting to calculate precise target position
                # Height Targeting does NOT consider Head targets
                target_type = best_target.get('type', None)
                
                # For CaptureCard and UDP, coordinates are already in the frame coordinate system
                # For MSS and NDI, we need to convert to region coordinates
                if config.capturer_mode.lower() in ["capturecard", "udp"]:
                    # Already in frame coordinates, no conversion needed
                    target_x, target_y = calculate_x_center_target_position(
                        best_target['x1'], best_target['y1'], 
                        best_target['x2'], best_target['y2'],
                        crosshair_x,  # crosshair_x is already in frame coordinates
                        target_type
                    )
                    target_screen_x = target_x
                    target_screen_y = target_y
                else:
                    # For MSS and NDI, convert to region coordinates
                    target_x, target_y = calculate_x_center_target_position(
                        best_target['x1'], best_target['y1'], 
                        best_target['x2'], best_target['y2'],
                        crosshair_x - region_left,  # Convert crosshair position to region coordinates
                        target_type
                    )
                    target_screen_x = region_left + target_x
                    target_screen_y = region_top + target_y
                
                # Apply user-defined X offset to target position (applies to all modes)
                x_offset = float(getattr(config, 'x_center_offset_px', 0))
                target_screen_x += x_offset

                # Calculate movement: both target and crosshair are in the same coordinate system
                dx = target_screen_x - crosshair_x
                dy = target_screen_y - crosshair_y
                
                # Height Targeting does NOT consider Head targets
                # Check if height targeting is disabled and crosshair is at target boundary
                if not getattr(config, 'height_targeting_enabled', True) or target_type == 'head':
                    # When height targeting is disabled OR target is Head, stop Y movement if crosshair touches target
                    # For CaptureCard and UDP, coordinates are already in frame coordinates
                    if config.capturer_mode.lower() in ["capturecard", "udp"]:
                        target_x1, target_y1 = best_target['x1'], best_target['y1']
                        target_x2, target_y2 = best_target['x2'], best_target['y2']
                    else:
                        target_x1 = best_target['x1'] + region_left
                        target_y1 = best_target['y1'] + region_top
                        target_x2 = best_target['x2'] + region_left
                        target_y2 = best_target['y2'] + region_top
                    
                    if is_crosshair_at_target_boundary(crosshair_x, crosshair_y, 
                                                      target_x1, target_y1,
                                                      target_x2, target_y2):
                        dy = 0
                        if target_type == 'head':
                            print(f"[DEBUG] Always-on mode - Head target - Height targeting does not apply, Y movement stopped: dx={dx:.1f}")
                        else:
                            print(f"[DEBUG] Always-on mode - height targeting disabled, crosshair at target boundary, Y movement stopped: dx={dx:.1f}")
                    else:
                        if target_type == 'head':
                            print(f"[DEBUG] Always-on mode - Head target - Height targeting does not apply, normal movement: dx={dx:.1f}, dy={dy:.1f}")
                        else:
                            print(f"[DEBUG] Always-on mode - height targeting disabled, normal movement: dx={dx:.1f}, dy={dy:.1f}")
                else:
                    # Height targeting enabled - use existing deadzone logic (only for non-Head targets)
                    box_height = best_target['y2'] - best_target['y1']
                    box_width = best_target['x2'] - best_target['x1']
                    # For CaptureCard and UDP, coordinates are already in frame coordinates
                    if config.capturer_mode.lower() in ["capturecard", "udp"]:
                        current_y = crosshair_y
                    else:
                        current_y = crosshair_y - region_top
                    target_relative_y = target_y
                    
                    if is_in_height_deadzone(current_y, target_relative_y, box_height, box_width=box_width):
                        # In deadzone: only move X-axis, set Y movement to zero
                        dy = 0
                        print(f"[DEBUG] Always-on mode in height deadzone - X only movement: dx={dx:.1f}")
                    else:
                        print(f"[DEBUG] Always-on mode normal movement: dx={dx:.1f}, dy={dy:.1f}")
                
                # Check X-center targeting behavior (Always-on mode)
                if getattr(config, 'x_center_targeting_enabled', False):
                    # When X-center targeting is enabled, stop X movement if crosshair is within boundary
                    # For CaptureCard and UDP, coordinates are already in frame coordinates
                    if config.capturer_mode.lower() in ["capturecard", "udp"]:
                        target_x1, target_y1 = best_target['x1'], best_target['y1']
                        target_x2, target_y2 = best_target['x2'], best_target['y2']
                    else:
                        target_x1 = best_target['x1'] + region_left
                        target_y1 = best_target['y1'] + region_top
                        target_x2 = best_target['x2'] + region_left
                        target_y2 = best_target['y2'] + region_top
                    
                    if is_in_x_center_boundary(crosshair_x, crosshair_y, 
                                               target_x1, target_y1,
                                               target_x2, target_y2):
                        dx = 0
                        print(f"[DEBUG] Always-on mode - X-center targeting enabled, crosshair within boundary, X movement stopped: dy={dy:.1f}")
                    else:
                        print(f"[DEBUG] Always-on mode - X-center targeting enabled, crosshair outside boundary, normal movement: dx={dx:.1f}, dy={dy:.1f}")
                else:
                    # When X-center targeting is disabled, stop X movement if crosshair touches target
                    # For CaptureCard and UDP, coordinates are already in frame coordinates
                    if config.capturer_mode.lower() in ["capturecard", "udp"]:
                        target_x1, target_y1 = best_target['x1'], best_target['y1']
                        target_x2, target_y2 = best_target['x2'], best_target['y2']
                    else:
                        target_x1 = best_target['x1'] + region_left
                        target_y1 = best_target['y1'] + region_top
                        target_x2 = best_target['x2'] + region_left
                        target_y2 = best_target['y2'] + region_top
                    
                    if is_crosshair_at_target_boundary(crosshair_x, crosshair_y, 
                                                      target_x1, target_y1,
                                                      target_x2, target_y2):
                        dx = 0
                        print(f"[DEBUG] Always-on mode - X-center targeting disabled, crosshair at target boundary, X movement stopped: dy={dy:.1f}")
                    else:
                        print(f"[DEBUG] Always-on mode - X-center targeting disabled, normal movement: dx={dx:.1f}, dy={dy:.1f}")

                # Apply im-game-sensitivity scaling
                sens = config.in_game_sens
                distance = 1.07437623 * math.pow(sens, -0.9936827126)
                # Apply distance scaling
                dx *= distance
                dy *= distance
                
                # Check if RCS disable Y-axis is enabled and RCS is actually active (shooting)
                if getattr(config, 'rcs_disable_y_axis', False) and _rcs_active:
                    # If RCS is actually active (pressing left button) and disable Y-axis is enabled, stop Y-axis movement
                    dy = 0
                    print(f"[DEBUG] RCS disable Y-axis (always_on): Aimbot Y movement stopped (RCS active)")
                
                # Apply mouse movement multiplier for speed control
                # Apply X-axis movement multiplier if enabled
                if getattr(config, 'mouse_movement_enabled_x', True):
                    dx *= getattr(config, 'mouse_movement_multiplier_x', 1.0)
                else:
                    dx = 0  # Disable X-axis movement
                
                # Apply Y-axis movement multiplier if enabled
                if getattr(config, 'mouse_movement_enabled_y', True):
                    dy *= getattr(config, 'mouse_movement_multiplier_y', 1.0)
                else:
                    dy = 0  # Disable Y-axis movement

                # Track Aimbot Y-axis movement for RCS compensation (always_on mode)
                with _aimbot_y_lock:
                    _aimbot_y_movement = dy  # Store current Y movement for RCS to use

                # Apply NCAF movement if selected mode (tracking already updated during target selection)
                if config.mode == "ncaf":
                    try:
                        ctrl = get_ncaf_controller()
                        # X offset is already applied earlier for all modes
                        nc_dx, nc_dy = ctrl.compute_ncaf_delta(
                            dx, dy,
                            float(getattr(config, 'ncaf_near_radius', 120.0)),
                            float(getattr(config, 'ncaf_snap_radius', 22.0)),
                            float(getattr(config, 'ncaf_alpha', 1.30)),
                            float(getattr(config, 'ncaf_snap_boost', 1.25)),
                            float(getattr(config, 'ncaf_max_step', 35.0)),
                        )
                        dx, dy = nc_dx, nc_dy
                        # Update tracked Y movement after NCAF
                        with _aimbot_y_lock:
                            _aimbot_y_movement = dy
                        # Respect X-center boundary: stop X if inside boundary
                        if getattr(config, 'x_center_targeting_enabled', False):
                            # For CaptureCard and UDP, coordinates are already in frame coordinates
                            if config.capturer_mode.lower() in ["capturecard", "udp"]:
                                target_x1, target_y1 = best_target['x1'], best_target['y1']
                                target_x2, target_y2 = best_target['x2'], best_target['y2']
                            else:
                                target_x1 = best_target['x1'] + region_left
                                target_y1 = best_target['y1'] + region_top
                                target_x2 = best_target['x2'] + region_left
                                target_y2 = best_target['y2'] + region_top
                            
                            if is_in_x_center_boundary(crosshair_x, crosshair_y,
                                                       target_x1, target_y1,
                                                       target_x2, target_y2):
                                dx = 0
                    except Exception as e:
                        print(f"[WARN] NCAF movement calculation failed in always_on mode: {e}")

               
                if config.mode == "normal":
                    # Apply x,y speeds scaling
                    dx *= config.normal_x_speed
                    dy *= config.normal_y_speed
                    makcu.move(dx, dy)
                    # Update tracked Y movement after scaling
                    with _aimbot_y_lock:
                        _aimbot_y_movement = dy
                elif config.mode == "bezier":
                    makcu.move_bezier(dx, dy, config.bezier_segments, config.bezier_ctrl_x, config.bezier_ctrl_y)
                    # Update tracked Y movement
                    with _aimbot_y_lock:
                        _aimbot_y_movement = dy
                elif config.mode == "silent":
                    makcu.move_bezier(dx, dy, config.silent_segments, config.silent_ctrl_x, config.silent_ctrl_y)
                    # Update tracked Y movement
                    with _aimbot_y_lock:
                        _aimbot_y_movement = dy
                elif config.mode == "smooth":
                    # Use smooth aiming with WindMouse algorithm
                    
                    path = smooth_aimer.calculate_smooth_path(dx, dy, config)

                    # Add all movements to the smooth movement queue
                    movements_added = 0
                    total_smooth_dy = 0
                    for move_dx, move_dy, delay in path:
                        if not smooth_move_queue.full():
                            smooth_move_queue.put((move_dx, move_dy, delay))
                            movements_added += 1
                            if movements_added <= 5:  # Only print first few to avoid spam
                                print(f"[DEBUG] Added movement: ({move_dx}, {move_dy}) with delay {delay:.3f}")
                        else:
                            # If queue is full, clear it and add this movement
                            print("[DEBUG] Queue full, clearing and adding movement")
                            try:
                                while not smooth_move_queue.empty():
                                    smooth_move_queue.get_nowait()
                            except queue.Empty:
                                pass
                            smooth_move_queue.put((move_dx, move_dy, delay))
                            movements_added += 1
                            break

                    print(f"[DEBUG] Added {movements_added} movements to queue")
                    # Update tracked Y movement with total smooth movement
                    with _aimbot_y_lock:
                        _aimbot_y_movement = total_smooth_dy if total_smooth_dy != 0 else dy

                    # Fallback: if no smooth movements generated, use direct movement
                    if len(path) == 0:
                        print("[DEBUG] No smooth path generated, using direct movement")
                        makcu.move(dx, dy)
                        with _aimbot_y_lock:
                            _aimbot_y_movement = dy
                elif config.mode == "ncaf":
                    # Direct device move after NCAF delta (already applied above)
                    makcu.move(dx, dy)
                    # Update tracked Y movement
                    with _aimbot_y_lock:
                        _aimbot_y_movement = dy
            # else: target is outside FOV, don't move mouse
        else:
            # Reset fatigue when not aiming
            smooth_aimer.reset_fatigue()
        
        # --- HSV Color Detection Function ---
        def detect_color_in_region(frame, center_x, center_y, radius, h_min, h_max, s_min, s_max, v_min, v_max):
            """Detect if specified HSV color range exists in circular region around center point"""
            try:
                if frame is None:
                    return False
                
                # Convert BGR to HSV
                hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                
                # Define circular region
                mask = np.zeros(hsv_frame.shape[:2], dtype=np.uint8)
                cv2.circle(mask, (int(center_x), int(center_y)), radius, 255, -1)
                
                # Create HSV range mask
                lower_hsv = np.array([h_min, s_min, v_min])
                upper_hsv = np.array([h_max, s_max, v_max])
                hsv_mask = cv2.inRange(hsv_frame, lower_hsv, upper_hsv)
                
                # Combine circular region with HSV range
                combined_mask = cv2.bitwise_and(mask, hsv_mask)
                
                # Count pixels that match the color criteria
                matching_pixels = cv2.countNonZero(combined_mask)
                total_pixels = cv2.countNonZero(mask)
                
                # Return True if at least 10% of the region matches the color
                if total_pixels > 0:
                    color_ratio = matching_pixels / total_pixels
                    return color_ratio >= 0.1  # 10% threshold for color detection
                
                return False
            except Exception as e:
                print(f"[ERROR] Color detection failed: {e}")
                return False
        
        # --- Enhanced Triggerbot Logic ---
        triggerbot_candidates = []
        triggerbot_status = "INACTIVE"
        best_trigger_target = None
        
        try:
            if getattr(config, "trigger_enabled", False):
                trigger_active = bool(getattr(config, "trigger_always_on", False))
                if not trigger_active:
                    # respect dedicated trigger hotkey
                    trigger_btn_idx = int(getattr(config, "trigger_button", 0))
                    trigger_active = is_button_pressed(trigger_btn_idx)

                # only evaluate when active
                if trigger_active and all_targets:
                    min_conf = float(getattr(config, "trigger_min_conf", 0.35))
                    radius_px = int(getattr(config, "trigger_radius_px", 8))
                    delay_ms = int(getattr(config, "trigger_delay_ms", 30) * random.uniform(0.8, 1.2))
                    cooldown_ms = int(getattr(config, "trigger_cooldown_ms", 120) * random.uniform(0.8, 1.2))

                    # Get trigger mode from config (1=distance based, 2=range detection, 3=color detection)
                    trigger_mode = getattr(config, "trigger_mode", 1)
                    
                    # Declare global variables for triggerbot timing
                    global _in_zone_since_ms, _last_trigger_time_ms, _burst_count, _burst_in_cooldown
                    
                    # ============================================
                    # Head Only 邏輯判斷
                    # ============================================
                    trigger_head_only = bool(getattr(config, "trigger_head_only", False))
                    head_class_selected = True  # 默認允許處理
                    has_head_target = True      # 默認允許處理
                    
                    # ============================================
                    # 情況 1: Head Only = false
                    # ============================================
                    if not trigger_head_only:
                        # 跳過所有 Head Only 檢查
                        head_class_selected = True
                        has_head_target = True
                    # ============================================
                    # 情況 2: Head Only = true
                    # ============================================
                    else:
                        # Step 1: 檢查 Head Class 是否選擇
                        head_label = getattr(config, "custom_head_label", None)
                        if not head_label or str(head_label).lower() == "none":
                            # Head Class 未選擇 → 跳過所有處理
                            head_class_selected = False
                            triggerbot_status = "HEAD_ONLY_NO_HEAD_CLASS_SELECTED"
                            best_trigger_target = None
                            print(f"[DEBUG] Head Only: Head Class not selected in Head Class dropdown")
                        else:
                            # Head Class 已選擇 → 繼續 Step 2
                            head_class_selected = True
                            print(f"[DEBUG] Head Only: Head Class '{head_label}' is selected, checking for Head targets...")
                            
                            # Step 2: 檢查是否檢測到 Head 目標（僅當 Head Class 已選擇時）
                            # Head Only = true 時：
                            # - 如果只有 player 但沒有 head → 不射擊
                            # - 如果有 player 且其中有 head → 射擊（可以處理所有目標，包括 player 和 head）
                            has_head_target = False
                            head_target_count = 0
                            all_target_types = []
                            all_target_classes = []
                            for target in all_targets:
                                target_type = target.get('type', 'unknown')
                                class_name = target.get('class_name', 'Unknown')
                                all_target_types.append(f"{class_name}({target_type})")
                                all_target_classes.append(class_name)
                                if target_type == 'head':
                                    has_head_target = True
                                    head_target_count += 1
                            
                            # 檢查是否有類別名稱匹配 Head Class（即使 type 不是 'head'）
                            # 這可能是因為目標檢測邏輯優先匹配 player，導致 head 目標被標記為 player
                            head_class_matched = False
                            if not has_head_target:
                                for target in all_targets:
                                    class_name = target.get('class_name', '')
                                    # 檢查類別名稱是否匹配 Head Class（精確匹配或部分匹配）
                                    if head_label and (class_name == head_label or 
                                                      (len(head_label) > 1 and not head_label.isdigit() and 
                                                       head_label.lower() in class_name.lower())):
                                        head_class_matched = True
                                        print(f"[DEBUG] Head Only: Found target with class '{class_name}' matching Head Class '{head_label}', but type is '{target.get('type', 'unknown')}'")
                                        break
                            
                            if not has_head_target and not head_class_matched:
                                # 未檢測到 Head 目標 → 跳過所有處理
                                triggerbot_status = "HEAD_ONLY_NO_HEAD_TARGET"
                                best_trigger_target = None
                                print(f"[DEBUG] Head Only: Head Class '{head_label}' is selected, but no Head target detected")
                                print(f"[DEBUG] Head Only: Total targets: {len(all_targets)}, Target types: {', '.join(all_target_types[:5])}")
                                print(f"[DEBUG] Head Only: All class names: {', '.join(set(all_target_classes))}")
                            elif head_class_matched:
                                # 檢測到類別名稱匹配 Head Class 的目標（即使 type 不是 'head'）
                                # 這種情況下，我們應該允許觸發
                                has_head_target = True
                                print(f"[DEBUG] Head Only: Head Class '{head_label}' matched in target classes, allowing triggerbot to fire")
                                print(f"[DEBUG] Head Only: Will process all targets (including player and head), Total targets: {len(all_targets)}")
                            else:
                                # 檢測到 Head 目標 → 允許觸發，可以處理所有目標（包括 player 和 head）
                                print(f"[DEBUG] Head Only: Head Class '{head_label}' is selected, {head_target_count} Head target(s) detected, allowing triggerbot to fire")
                                print(f"[DEBUG] Head Only: Will process all targets (including player and head), Total targets: {len(all_targets)}")
                    
                    # 只有當 Head Only 檢查通過時才處理目標
                    if not head_class_selected or not has_head_target:
                        # Head Only 檢查未通過，跳過所有處理
                        if trigger_head_only:
                            if not head_class_selected:
                                print(f"[DEBUG] Head Only: Skipping all processing - Head Class not selected")
                            elif not has_head_target:
                                print(f"[DEBUG] Head Only: Skipping all processing - No Head target detected")
                        pass
                    else:
                        # Head Only 檢查通過，繼續處理目標
                        if trigger_head_only:
                            print(f"[DEBUG] Head Only: All checks passed, processing all targets (total: {len(all_targets)})")
                        
                        # Enhanced candidate filtering
                        for target in all_targets:
                            # Check if target is within FOV (more accurate than just distance)
                            if not is_target_in_fov(target['x1'], target['y1'], target['x2'], target['y2']):
                                continue
                                
                            # Check confidence threshold (skip for Mode 2 and Mode 3)
                            if trigger_mode not in [2, 3] and target['conf'] < min_conf:
                                continue
                            
                            # Calculate distance for both modes
                            center_x, center_y = target['center_x'], target['center_y']
                            # Use crosshair center with center offset for CaptureCard
                            crosshair_x, crosshair_y = get_crosshair_center()
                            crosshair_dist = math.hypot(center_x - crosshair_x, center_y - crosshair_y)
                            
                            # Mode-specific filtering
                            if trigger_mode == 2:
                                # Mode 2: Use independent boundary contact detection
                                # Skip the old distance-based logic - will be handled by process_mode2_trigger_logic
                                continue
                            elif trigger_mode == 3:
                                # Mode 3: Color-based trigger (HSV detection)
                                color_radius = int(getattr(config, "trigger_color_radius_px", 20))
                                if crosshair_dist <= color_radius:
                                    # Get HSV parameters
                                    h_min = int(getattr(config, "trigger_hsv_h_min", 0))
                                    h_max = int(getattr(config, "trigger_hsv_h_max", 179))
                                    s_min = int(getattr(config, "trigger_hsv_s_min", 0))
                                    s_max = int(getattr(config, "trigger_hsv_s_max", 255))
                                    v_min = int(getattr(config, "trigger_hsv_v_min", 0))
                                    v_max = int(getattr(config, "trigger_hsv_v_max", 255))
                                    
                                    # Check for color in region around crosshair center
                                    if config.capturer_mode.lower() in ["mss", "capturecard"]:
                                        crosshair_center_x = config.fov_x_size / 2
                                        crosshair_center_y = config.fov_y_size / 2
                                    elif config.capturer_mode.lower() == "udp":
                                        crosshair_center_x = config.udp_width / 2
                                        crosshair_center_y = config.udp_height / 2
                                    else:
                                        crosshair_center_x = config.ndi_width / 2
                                        crosshair_center_y = config.ndi_height / 2
                                    
                                    if detect_color_in_region(image, crosshair_center_x, crosshair_center_y, color_radius, h_min, h_max, s_min, s_max, v_min, v_max):
                                        # Color detected, use distance as score (closer = better)
                                        target_score = 1.0 - (crosshair_dist / color_radius)
                                        triggerbot_candidates.append({
                                            'target': target,
                                            'distance': crosshair_dist,
                                            'score': target_score
                                        })
                            else:
                                # Mode 1: Distance-based trigger (original behavior)
                                if crosshair_dist <= radius_px:
                                    # Add scoring system for better target selection
                                    target_score = target['conf'] * (1.0 - (crosshair_dist / radius_px))
                                    triggerbot_candidates.append({
                                        'target': target,
                                        'distance': crosshair_dist,
                                        'score': target_score
                                    })

                        # Handle Mode 2 with independent logic (only if Head Only check passes)
                        if trigger_mode == 2:
                            # Mode 2: 使用 Target Classes 選擇的目標（不是 Head Class）
                            # Head Only 檢查只是用來判斷是否允許 Triggerbot 觸發
                            # 一旦通過 Head Only 檢查，Mode 2 應該使用所有在 Target Classes 中選擇的目標
                            # all_targets 已經包含了所有在 Target Classes 中選擇的目標（包括 player 和 head）
                            mode2_targets = all_targets
                            
                            # Use independent Mode 2 trigger logic
                            # process_mode2_trigger_logic 會檢查這些目標是否在 Range X/Y 範圍內
                            should_fire, triggerbot_status, best_trigger_target = process_mode2_trigger_logic(mode2_targets, delay_ms, cooldown_ms)
                            
                            if should_fire and best_trigger_target:
                                try:
                                    # Fire at target
                                    makcu.click()
                                    target_class = best_trigger_target.get('class_name', 'Unknown')
                                    print(f"[TRIGGERBOT MODE2] Fired at target '{target_class}' with {best_trigger_target['conf']:.2f} confidence")
                                    _last_trigger_time_ms = _now_ms()
                                    _in_zone_since_ms = 0.0  # Reset delay for next cycle
                                    triggerbot_status = "ENTERING COOLDOWN"
                                except Exception as e:
                                    print(f"[WARN] Trigger click failed: {e}")
                                    # Reset timing even on failure to prevent stuck state
                                    _last_trigger_time_ms = _now_ms()
                                    _in_zone_since_ms = 0.0
                        elif trigger_mode == 3:
                            # Mode 3: Color-based trigger with custom delay and cooldown
                            # Select best target based on score (confidence + proximity)
                            if triggerbot_candidates:
                                best_candidate = max(triggerbot_candidates, key=lambda c: c['score'])
                                best_trigger_target = best_candidate['target']
                                
                                now = _now_ms()
                            
                                color_delay_ms = int(getattr(config, "trigger_color_delay_ms", 50) * random.uniform(0.8, 1.2))
                                color_cooldown_ms = int(getattr(config, "trigger_color_cooldown_ms", 200) * random.uniform(0.8, 1.2))
                                
                                if _in_zone_since_ms == 0.0:
                                    _in_zone_since_ms = now
                                    triggerbot_status = "COLOR DETECTED"

                                time_in_zone = now - _in_zone_since_ms
                                linger_ok = time_in_zone >= color_delay_ms
                                cooldown_ok = (now - _last_trigger_time_ms) >= color_cooldown_ms

                                if linger_ok and cooldown_ok:
                                    triggerbot_status = "FIRING"
                                    try:
                                        # Fire on color detection
                                        makcu.click()
                                        print(f"[TRIGGERBOT MODE3] Fired on color detection")
                                        _last_trigger_time_ms = now
                                        _in_zone_since_ms = 0.0  # Reset for next cycle to enter cooldown
                                    except Exception as e:
                                        print(f"[WARN] Trigger click failed: {e}")
                                        # Reset timing even on failure to prevent stuck state
                                        _last_trigger_time_ms = now
                                        _in_zone_since_ms = 0.0
                                else:
                                    if not linger_ok:
                                        triggerbot_status = f"COLOR WAITING ({time_in_zone:.0f}/{color_delay_ms}ms)"
                                    elif not cooldown_ok:
                                        cooldown_remaining = color_cooldown_ms - (now - _last_trigger_time_ms)
                                        triggerbot_status = f"COLOR COOLDOWN ({cooldown_remaining:.0f}ms)"
                            else:
                                # Mode 3: No color detected
                                _in_zone_since_ms = 0.0
                                triggerbot_status = "NO_COLOR"
                        else:
                            # Mode 1: Distance-based trigger with delay + cooldown
                            # Select best target based on score (confidence + proximity)
                            if triggerbot_candidates:
                                best_candidate = max(triggerbot_candidates, key=lambda c: c['score'])
                                best_trigger_target = best_candidate['target']
                                
                                now = _now_ms()
                                
                                if _in_zone_since_ms == 0.0:
                                    _in_zone_since_ms = now
                                    triggerbot_status = "TARGETING"

                                time_in_zone = now - _in_zone_since_ms
                                linger_ok = time_in_zone >= delay_ms
                                cooldown_ok = (now - _last_trigger_time_ms) >= cooldown_ms

                                if linger_ok and cooldown_ok:
                                    triggerbot_status = "FIRING"
                                    try:
                                        # Single click via MAKCU
                                        makcu.click()
                                        print(f"[TRIGGERBOT MODE1] Fired at target with {best_trigger_target['conf']:.2f} confidence")
                                        _last_trigger_time_ms = now
                                        _in_zone_since_ms = 0.0  # Reset for next cycle to enter cooldown
                                    except Exception as e:
                                        print(f"[WARN] Trigger click failed: {e}")
                                        # Reset timing even on failure to prevent stuck state
                                        _last_trigger_time_ms = now
                                        _in_zone_since_ms = 0.0
                                else:
                                    if not linger_ok:
                                        triggerbot_status = f"WAITING ({time_in_zone:.0f}/{delay_ms}ms)"
                                    elif not cooldown_ok:
                                        cooldown_remaining = cooldown_ms - (now - _last_trigger_time_ms)
                                        triggerbot_status = f"COOLDOWN ({cooldown_remaining:.0f}ms)"
                            else:
                                # Mode 1: No targets in range
                                _in_zone_since_ms = 0.0
                                triggerbot_status = "NO_TARGETS"
                else:
                    _in_zone_since_ms = 0.0
                    if trigger_active:
                        triggerbot_status = "ACTIVE"
                    else:
                        triggerbot_status = "STANDBY"
        except Exception as e:
            print(f"[ERROR] Triggerbot block: {e}")
            triggerbot_status = "ERROR"

            
        # --- Debug Window Display ---
        if debug_image is not None:
            # Add text overlays only if text info is enabled
            if config.show_debug_text_info:
                button_held = is_button_pressed(config.selected_mouse_button)
                status_text = f"Button {config.selected_mouse_button}: {'HELD' if button_held else 'released'}"
                color = (0, 255, 0) if button_held else (0, 0, 255)
                cv2.putText(debug_image, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                target_text = f"Targets: {len(all_targets)} | Detected: {len(detected_classes)} classes"
                cv2.putText(debug_image, target_text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                # Display selected classes (multi-select aware)
                if getattr(config, "selected_player_classes", []) and len(config.selected_player_classes) > 0:
                    players_text = ", ".join(config.selected_player_classes[:5])
                    extra = "" if len(config.selected_player_classes) <= 5 else f" (+{len(config.selected_player_classes)-5})"
                    settings_text = f"Looking for: [{players_text}{extra}], '{config.custom_head_label}'"
                else:
                    settings_text = f"Looking for: '{config.custom_player_label}', '{config.custom_head_label}'"
                cv2.putText(debug_image, settings_text, (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

                mode_text = f"Mode: {config.mode.upper()}"
                cv2.putText(debug_image, mode_text, (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

                # FOV Size information and target status (hidden when NCAF debug is on)
                if not (config.mode == "ncaf" and getattr(config, 'ncaf_show_debug', False)):
                    fov_text = f"FOV Size: {config.fov_x_size}x{config.fov_y_size}"
                    cv2.putText(debug_image, fov_text, (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    # Show FOV target status
                    if all_targets:
                        best_target = min(all_targets, key=lambda t: t['dist'])
                        is_in_fov = is_target_in_fov(best_target['x1'], best_target['y1'], best_target['x2'], best_target['y2'])
                        fov_status_text = f"Target in FOV: {'YES' if is_in_fov else 'NO'}"
                        fov_status_color = (0, 255, 0) if is_in_fov else (0, 0, 255)
                        cv2.putText(debug_image, fov_status_text, (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, fov_status_color, 2)
            
            # Enhanced Triggerbot status display (only if text info is enabled)
            if config.show_debug_text_info and getattr(config, "trigger_enabled", False):
                # Main status line
                trigger_radius = getattr(config, "trigger_radius_px", 8)
                trigger_status_text = f"Triggerbot: {triggerbot_status} ({trigger_radius}px)"
                
                # Color based on status
                status_colors = {
                    "INACTIVE": (128, 128, 128),    # Gray
                    "STANDBY": (255, 255, 0),       # Yellow  
                    "ACTIVE": (0, 255, 0),          # Green
                    "TARGETING": (255, 165, 0),     # Orange
                    "WAITING": (255, 255, 0),       # Yellow
                    "COOLDOWN": (255, 0, 0),        # Red
                    "FIRING": (0, 255, 0),          # Bright Green
                    "NO_TARGETS": (128, 128, 255),  # Light Blue
                    "ERROR": (255, 0, 255)          # Magenta
                }
                status_color = status_colors.get(triggerbot_status.split()[0], (255, 0, 255))
                cv2.putText(debug_image, trigger_status_text, (10, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
                
                # Additional info line
                if len(triggerbot_candidates) > 0:
                    candidates_text = f"Candidates: {len(triggerbot_candidates)}"
                    if best_trigger_target:
                        candidates_text += f" | Best: {best_trigger_target['conf']:.2f} conf"
                    cv2.putText(debug_image, candidates_text, (10, 230), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                
                # Control info
                trigger_always_on = getattr(config, "trigger_always_on", False)
                if trigger_always_on:
                    control_text = "[ALWAYS ON]"
                else:
                    trigger_btn = getattr(config, "trigger_button", 0)
                    btn_names = ["Left", "Right", "Middle", "Side4", "Side5"]
                    btn_name = btn_names[trigger_btn] if trigger_btn < len(btn_names) else f"Btn{trigger_btn}"
                    control_text = f"[Key: {btn_name}]"
                cv2.putText(debug_image, control_text, (300, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 2)
            elif config.show_debug_text_info:
                trigger_status_text = "Triggerbot: DISABLED"
                cv2.putText(debug_image, trigger_status_text, (10, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (128, 128, 128), 2)

            # Additional text info (only if text info is enabled)
            if config.show_debug_text_info:
                if config.mode == "smooth":
                    queue_text = f"Smooth Queue: {smooth_move_queue.qsize()}/10"
                    cv2.putText(debug_image, queue_text, (10, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

                if detected_classes:
                    classes_text = f"Classes: {', '.join(sorted(detected_classes))}"
                    cv2.putText(debug_image, classes_text, (10, debug_image.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            # Draw crosshair
            if config.mode == "ncaf":
                # Skip FOV rectangle drawing when NCAF mode is active (use NCAF radius instead)
                # Get crosshair center for marker (with center offset for CaptureCard)
                center_x, center_y = get_crosshair_center()
                center = (int(center_x), int(center_y))
            elif config.capturer_mode.lower() in ["mss", "capturecard"]:
                # Get crosshair center with center offset applied for CaptureCard
                center_x, center_y = get_crosshair_center()
                center = (int(center_x), int(center_y))
                
                # Draw FOV rectangle (capture area visualization) using separate X/Y dimensions
                fov_half_x = config.fov_x_size // 2
                fov_half_y = config.fov_y_size // 2
                
                # Calculate FOV rectangle coordinates centered on crosshair (with offset applied)
                fov_x1 = max(0, int(center_x - fov_half_x))
                fov_y1 = max(0, int(center_y - fov_half_y))
                fov_x2 = int(center_x + fov_half_x)
                fov_y2 = int(center_y + fov_half_y)
                
                # Draw FOV rectangle outline
                cv2.rectangle(debug_image, (fov_x1, fov_y1), (fov_x2, fov_y2), (0, 255, 255), 2)
                
                # Draw corner indicators for better visibility
                corner_size = 10
                # Top-left corner
                cv2.line(debug_image, (fov_x1, fov_y1), (fov_x1 + corner_size, fov_y1), (0, 255, 255), 3)
                cv2.line(debug_image, (fov_x1, fov_y1), (fov_x1, fov_y1 + corner_size), (0, 255, 255), 3)
                # Top-right corner
                cv2.line(debug_image, (fov_x2, fov_y1), (fov_x2 - corner_size, fov_y1), (0, 255, 255), 3)
                cv2.line(debug_image, (fov_x2, fov_y1), (fov_x2, fov_y1 + corner_size), (0, 255, 255), 3)
                # Bottom-left corner
                cv2.line(debug_image, (fov_x1, fov_y2), (fov_x1 + corner_size, fov_y2), (0, 255, 255), 3)
                cv2.line(debug_image, (fov_x1, fov_y2), (fov_x1, fov_y2 - corner_size), (0, 255, 255), 3)
                # Bottom-right corner
                cv2.line(debug_image, (fov_x2, fov_y2), (fov_x2 - corner_size, fov_y2), (0, 255, 255), 3)
                cv2.line(debug_image, (fov_x2, fov_y2), (fov_x2, fov_y2 - corner_size), (0, 255, 255), 3)
            elif config.capturer_mode.lower() == "udp":
                # Get crosshair center with get_crosshair_center() for consistency
                center_x, center_y = get_crosshair_center()
                center = (int(center_x), int(center_y))
                
                # Draw FOV rectangle for UDP mode using FOV X/Y size
                fov_half_x = config.fov_x_size // 2
                fov_half_y = config.fov_y_size // 2
                
                # Calculate FOV rectangle coordinates centered on crosshair
                fov_x1 = max(0, int(center_x - fov_half_x))
                fov_y1 = max(0, int(center_y - fov_half_y))
                fov_x2 = int(center_x + fov_half_x)
                fov_y2 = int(center_y + fov_half_y)
                
                # Draw FOV rectangle outline
                cv2.rectangle(debug_image, (fov_x1, fov_y1), (fov_x2, fov_y2), (0, 255, 255), 2)
                
                # Draw corner indicators for better visibility
                corner_size = 10
                # Top-left corner
                cv2.line(debug_image, (fov_x1, fov_y1), (fov_x1 + corner_size, fov_y1), (0, 255, 255), 3)
                cv2.line(debug_image, (fov_x1, fov_y1), (fov_x1, fov_y1 + corner_size), (0, 255, 255), 3)
                # Top-right corner
                cv2.line(debug_image, (fov_x2, fov_y1), (fov_x2 - corner_size, fov_y1), (0, 255, 255), 3)
                cv2.line(debug_image, (fov_x2, fov_y1), (fov_x2, fov_y1 + corner_size), (0, 255, 255), 3)
                # Bottom-left corner
                cv2.line(debug_image, (fov_x1, fov_y2), (fov_x1 + corner_size, fov_y2), (0, 255, 255), 3)
                cv2.line(debug_image, (fov_x1, fov_y2), (fov_x1, fov_y2 - corner_size), (0, 255, 255), 3)
                # Bottom-right corner
                cv2.line(debug_image, (fov_x2, fov_y2), (fov_x2 - corner_size, fov_y2), (0, 255, 255), 3)
                cv2.line(debug_image, (fov_x2, fov_y2), (fov_x2, fov_y2 - corner_size), (0, 255, 255), 3)
            else:
                # For NDI mode, draw FOV rectangle based on the actual capture dimensions
                center = (config.ndi_width // 2, config.ndi_height // 2)
                img_height, img_width = debug_image.shape[:2]
                img_center_x, img_center_y = img_width // 2, img_height // 2
                
                # Use the actual FOV size in relation to the captured area with separate X/Y dimensions
                fov_half_x = config.fov_x_size // 2
                fov_half_y = config.fov_y_size // 2
                fov_x1 = max(0, img_center_x - fov_half_x)
                fov_y1 = max(0, img_center_y - fov_half_y)
                fov_x2 = min(img_width, img_center_x + fov_half_x)
                fov_y2 = min(img_height, img_center_y + fov_half_y)
                
                # Draw FOV rectangle outline
                cv2.rectangle(debug_image, (fov_x1, fov_y1), (fov_x2, fov_y2), (0, 255, 255), 2)

            cv2.drawMarker(debug_image, center, (255, 255, 255), cv2.MARKER_CROSS, 20, 2)
            
            # Draw Enhanced Triggerbot visualization
            if getattr(config, "trigger_enabled", False):
                trigger_mode = getattr(config, "trigger_mode", 1)
                
                # Color based on triggerbot status
                if triggerbot_status == "FIRING":
                    trigger_color = (0, 255, 0)      # Bright Green when firing
                elif triggerbot_status == "TARGETING":
                    trigger_color = (255, 165, 0)    # Orange when targeting
                elif triggerbot_status.startswith("WAITING"):
                    trigger_color = (255, 255, 0)    # Yellow when waiting
                elif triggerbot_status.startswith("COOLDOWN"):
                    trigger_color = (255, 0, 0)      # Red during cooldown
                else:
                    trigger_color = (255, 0, 255)    # Default magenta
                
                if trigger_mode == 2:
                    # Mode 2: Rectangle with X/Y ranges (always use Range X/Y, not affected by aimbot mode)
                    range_x = getattr(config, "trigger_mode2_range_x", 50.0)
                    range_y = getattr(config, "trigger_mode2_range_y", 50.0)
                    
                    # Draw rectangular boundary
                    rect_x1 = int(center[0] - range_x)
                    rect_y1 = int(center[1] - range_y)
                    rect_x2 = int(center[0] + range_x)
                    rect_y2 = int(center[1] + range_y)
                    
                    cv2.rectangle(debug_image, (rect_x1, rect_y1), (rect_x2, rect_y2), trigger_color, 2)
                    
                    # Add triggerbot center marker
                    cv2.circle(debug_image, center, 2, trigger_color, -1)
                    
                    # Add triggerbot label with status
                    trigger_label = f"Trigger: {range_x:.1f}x{range_y:.1f} [{triggerbot_status}]"
                    label_y_offset = int(range_y) + 20
                    cv2.putText(debug_image, trigger_label, (int(center[0] - 80), int(center[1] + label_y_offset)), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, trigger_color, 2)
                else:
                    # Mode 1 and Mode 3: Circle visualization
                    trigger_radius = getattr(config, "trigger_radius_px", 8)
                    
                    # Main trigger circle
                    cv2.circle(debug_image, center, trigger_radius, trigger_color, 2)
                    
                    # Add triggerbot center marker
                    cv2.circle(debug_image, center, 2, trigger_color, -1)
                    
                    # Add triggerbot label with status
                    trigger_label = f"Trigger: {trigger_radius}px [{triggerbot_status}]"
                    cv2.putText(debug_image, trigger_label, (center[0] - 80, center[1] + trigger_radius + 20), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, trigger_color, 2)
                
                # Highlight triggerbot candidates
                for i, candidate in enumerate(triggerbot_candidates):
                    target = candidate['target']
                    x1, y1, x2, y2 = int(target['x1']), int(target['y1']), int(target['x2']), int(target['y2'])
                    
                    # Different colors for different candidates
                    if target == best_trigger_target:
                        candidate_color = (0, 255, 0)    # Green for best target
                        thickness = 3
                    else:
                        candidate_color = (255, 255, 0)  # Yellow for other candidates
                        thickness = 2
                    
                    # Draw candidate highlight
                    cv2.rectangle(debug_image, (x1-2, y1-2), (x2+2, y2+2), candidate_color, thickness)
                    
                    # Add score label
                    score_text = f"Score: {candidate['score']:.2f}"
                    cv2.putText(debug_image, score_text, (x1, y2 + 15), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, candidate_color, 1)
                
                # Draw line to best target if available
                if best_trigger_target:
                    target_center = (int(best_trigger_target['center_x']), int(best_trigger_target['center_y']))
                    cv2.line(debug_image, center, target_center, (0, 255, 0), 1)

            # Show window in center of screen
            win_name = "AI Debug"
            # Draw NCAF debug radii if enabled
            try:
                if config.mode == "ncaf" and getattr(config, 'ncaf_show_debug', False):
                    near_r = int(float(getattr(config, 'ncaf_near_radius', 120.0)))
                    snap_r = int(float(getattr(config, 'ncaf_snap_radius', 22.0)))
                    # Determine center in debug_image coordinates (match FOV drawing logic)
                    if config.capturer_mode.lower() in ["mss", "capturecard"]:
                        center_x = int(config.fov_x_size // 2)
                        center_y = int(config.fov_y_size // 2)
                    elif config.capturer_mode.lower() == "udp":
                        center_x = int(max(1, getattr(config, 'udp_width', 0)) // 2)
                        center_y = int(max(1, getattr(config, 'udp_height', 0)) // 2)
                    else:
                        # Fallback to image center
                        h, w = debug_image.shape[:2]
                        center_x, center_y = w // 2, h // 2
                    cv2.circle(debug_image, (center_x, center_y), near_r, (0, 255, 0), 1)
                    cv2.circle(debug_image, (center_x, center_y), snap_r, (255, 0, 255), 1)
            except Exception:
                pass
            cv2.imshow(win_name, debug_image)

            # Calculate center position
            if not debug_window_moved:
                screen_w, screen_h = config.screen_width, config.screen_height
                win_w, win_h = debug_image.shape[1], debug_image.shape[0]
                x = (screen_w - win_w) // 2
                y = (screen_h - win_h) // 2
                cv2.moveWindow(win_name, x, y)
                debug_window_moved = True 
            
            # Handle window events and check if window was closed
            key = cv2.waitKey(1) & 0xFF
            
            # ESC key closes debug window
            if key == 27:  # ESC key
                config.show_debug_window = False
                print("[INFO] Debug window closed via ESC key")
                break
            
            # Check if window was closed by user (safer method)
            try:
                # Only check window property, avoid multiple detection methods
                window_property = cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE)
                if window_property < 0:  # Window was closed
                    config.show_debug_window = False
                    print("[INFO] Debug window closed by user")
                    break
            except Exception:
                # If we can't check the window property, assume it's closed
                config.show_debug_window = False
                print("[INFO] Debug window closed (property check failed)")
                break


        # --- FPS Calculation ---
        frame_count += 1
        elapsed = time.perf_counter() - start_time
        if elapsed > 1.0:
            fps = frame_count / elapsed
            start_time = time.perf_counter()
            frame_count = 0
    
    # Cleanup debug window when detection loop ends
    if config.show_debug_window:
        try:
            cv2.destroyWindow("AI Debug")
            print("[INFO] Debug window cleaned up safely")
        except Exception as e:
            print(f"[WARN] Debug window cleanup warning: {e}")
        finally:
            config.show_debug_window = False

def start_aimbot():
    global _aimbot_running, _aimbot_thread, _capture_thread, _smooth_thread, _rcs_running, _rcs_thread, makcu
    global _last_trigger_time_ms, _in_zone_since_ms, _burst_count, _burst_in_cooldown
    _last_trigger_time_ms = 0.0
    _in_zone_since_ms = 0.0
    _burst_count = 0
    _burst_in_cooldown = False
    if _aimbot_running:
        return
    try:
        if makcu is None:  # <-- Initialize only once
            Mouse.cleanup()
            makcu=Mouse()
    except Exception as e:
        print(f"[ERROR] Failed to cleanup Mouse instance: {e}")

    _aimbot_running = True
    _rcs_running = True
    
    # Start capture thread
    _capture_thread = threading.Thread(target=capture_loop, daemon=True)
    _capture_thread.start()

    # Start smooth movement thread (for smooth mode)
    _smooth_thread = threading.Thread(target=smooth_movement_loop, daemon=True)
    _smooth_thread.start()

    # Start RCS thread
    _rcs_thread = threading.Thread(target=rcs_loop, daemon=True)
    _rcs_thread.start()

    # Start main detection thread
    _aimbot_thread = threading.Thread(target=detection_and_aim_loop, daemon=True)
    _aimbot_thread.start()

    button_names = ["Left", "Right", "Middle", "Side 4", "Side 5"]
    button_name = button_names[config.selected_mouse_button] if config.selected_mouse_button < len(button_names) else f"Button {config.selected_mouse_button}"
    print(f"[INFO] Aimbot started in {config.mode} mode. Hold {button_name} button to aim.")

def stop_aimbot():
    global _aimbot_running, _rcs_running, _last_trigger_time_ms, _in_zone_since_ms, _burst_count, _burst_in_cooldown
    global _silent_original_pos, _silent_in_progress, _silent_last_activation
    global _last_left_click_state, _rcs_active, _rcs_start_time, _last_rcs_x_time, _last_rcs_y_time
    global _rcs_accumulated_x, _rcs_accumulated_y
    _aimbot_running = False
    _rcs_running = False
    _last_trigger_time_ms = 0.0
    _in_zone_since_ms = 0.0
    _burst_count = 0
    _burst_in_cooldown = False
    
    # Reset Enhanced Silent Mode state
    _silent_original_pos = None
    _silent_in_progress = False
    _silent_last_activation = 0.0
    
    # Reset RCS state
    _last_left_click_state = False
    _rcs_active = False
    _rcs_start_time = 0
    _last_rcs_x_time = 0
    _last_rcs_y_time = 0
    _rcs_accumulated_x = 0.0
    _rcs_accumulated_y = 0.0
    Mouse.mask_manager_tick(selected_idx=config.selected_mouse_button, aimbot_running=False)
    Mouse.mask_manager_tick(selected_idx=config.trigger_button, aimbot_running=False)
    try:
        if makcu is None:  # <-- Initialize only once
            Mouse.cleanup()
    except Exception as e:
        print(f"[ERROR] Failed to cleanup Mouse instance: {e}")
    # Clear the smooth movement queue
    try:
        while not smooth_move_queue.empty():
            smooth_move_queue.get_nowait()
    except queue.Empty:
        pass

    # Set flag to false to let detection thread handle window cleanup
    config.show_debug_window = False
    
    # Small delay to allow detection thread to cleanup windows
    time.sleep(0.1)
    
    # Final cleanup attempt (failsafe)
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass  # Ignore errors if window was already closed
    
    print("[INFO] Aimbot stopped.")

def is_aimbot_running():
    return _aimbot_running

# Rest of the utility functions remain the same
def reload_model(path=None):
    if path is None: path = config.model_path
    return load_model(path)

def get_model_classes(path=None):
    if path is None: path = config.model_path
    _, class_names = load_model(path)
    return [class_names[i] for i in sorted(class_names.keys())]

def get_model_size(path=None):
    if path is None: path = config.model_path
    try:
        return f"{os.path.getsize(path) / (1024*1024):.2f} MB"
    except Exception:
        return "?"

def rcs_loop():
    """
    RCS (Recoil Control System) loop that monitors mouse button states
    and applies recoil compensation when shooting.
    
    Supports two modes:
    - Simple mode: Original RCS behavior with configurable strength/delay
    - Game mode: Loads recoil patterns from recoil_data/{game}/{weapon}.txt files
    """
    global _rcs_running, _last_left_click_state, _rcs_active, _rcs_start_time, makcu
    global _last_rcs_x_time, _last_rcs_y_time, _rcs_accumulated_x, _rcs_accumulated_y
    from recoil_loader import load_recoil_data
    
    print("[INFO] RCS thread started")
    
    # Game mode variables
    _rcs_recoil_data = []
    _rcs_current_bullet = 0
    _rcs_last_bullet_time = 0
    _rcs_last_game = ""
    _rcs_last_weapon = ""
    
    while _rcs_running:
        try:
            # Check if RCS is enabled in config
            if not config.rcs_enabled:
                time.sleep(0.01)  # Small delay when disabled
                continue
            
            # Monitor RCS key button and right mouse button (for ADS mode)
            rcs_button_idx = int(getattr(config, "rcs_button", 0))
            current_rcs_key_state = is_button_pressed(rcs_button_idx)
            current_right_click_state = is_button_pressed(1)  # Right mouse button for ADS
            
            # Determine if RCS should be active based on RCS key and ADS only setting
            should_activate_rcs = current_rcs_key_state
            if config.rcs_ads_only:
                # ADS only mode: require both RCS key and right mouse button to be held
                should_activate_rcs = current_rcs_key_state and current_right_click_state
            
            # Game mode: Load recoil data if game/weapon changed
            rcs_mode = getattr(config, "rcs_mode", "simple")
            if rcs_mode == "game":
                current_game = getattr(config, "rcs_game", "")
                current_weapon = getattr(config, "rcs_weapon", "")
                
                # Reload data if game/weapon changed or data is empty
                if current_game and current_weapon:
                    if (current_game != _rcs_last_game or 
                        current_weapon != _rcs_last_weapon or 
                        len(_rcs_recoil_data) == 0):
                        _rcs_recoil_data = load_recoil_data(current_game, current_weapon)
                        _rcs_last_game = current_game
                        _rcs_last_weapon = current_weapon
                        _rcs_current_bullet = 0
                        if _rcs_recoil_data:
                            print(f"[INFO] RCS loaded recoil data: {current_game}/{current_weapon} ({len(_rcs_recoil_data)} bullets)")
                            # Show first few patterns
                            preview = _rcs_recoil_data[:min(3, len(_rcs_recoil_data))]
                            print(f"[INFO] RCS preview: {preview}")
                        else:
                            print(f"[WARNING] RCS: No recoil data found for {current_game}/{current_weapon}")
            
            # Detect RCS activation (transition from False to True)
            if should_activate_rcs and not _rcs_active:
                # RCS started - begin recoil compensation
                _rcs_active = True
                current_time = time.time()
                _rcs_start_time = current_time
                _last_rcs_x_time = current_time  # Reset X timer
                _last_rcs_y_time = current_time  # Reset Y timer
                _rcs_accumulated_x = 0.0  # Reset accumulation
                _rcs_accumulated_y = 0.0  # Reset accumulation
                _rcs_current_bullet = 0  # Reset bullet counter for game mode
                _rcs_last_bullet_time = 0  # Reset bullet timer (use 0 to indicate first bullet)
                ads_status = " (ADS mode)" if config.rcs_ads_only else ""
                mode_status = f" ({rcs_mode} mode)" if rcs_mode == "game" else ""
                print(f"[DEBUG] RCS activated{ads_status}{mode_status} - recoil compensation started")
            
            # Detect RCS deactivation (transition from True to False)
            elif not should_activate_rcs and _rcs_active:
                # RCS ended - immediately stop recoil compensation and reset all state
                _rcs_active = False
                _rcs_current_bullet = 0  # Reset bullet counter
                _rcs_last_bullet_time = 0  # Reset bullet timer
                _rcs_accumulated_x = 0.0  # Clear accumulated X movement
                _rcs_accumulated_y = 0.0  # Clear accumulated Y movement
                _last_rcs_x_time = 0  # Reset X timer
                _last_rcs_y_time = 0  # Reset Y timer
                ads_status = " (ADS mode)" if config.rcs_ads_only else ""
                print(f"[DEBUG] RCS deactivated{ads_status} - recoil compensation stopped immediately")
            
            # Apply RCS when active and conditions are met
            if _rcs_active and should_activate_rcs:
                current_time = time.time()
                shooting_duration = current_time - _rcs_start_time
                
                # Track what movements to apply this cycle
                x_movement = 0
                y_movement = 0
                
                if rcs_mode == "game" and _rcs_recoil_data:
                    # Game mode: Use recoil data from file
                    # Apply current bullet's movement immediately when activated
                    # Then wait for delay before moving to next bullet
                    # Stop after all bullets are applied (no looping)
                    
                    if _rcs_current_bullet < len(_rcs_recoil_data):
                        delay_ms, dx, dy = _rcs_recoil_data[_rcs_current_bullet]
                        
                        # Get weapon-specific multipliers
                        multipliers = config.get_weapon_multipliers(current_game, current_weapon)
                        x_mult = multipliers.get('x_mult', 1.0)
                        y_mult = multipliers.get('y_mult', 1.0)
                        x_time_mult = multipliers.get('x_time_mult', 1.0)
                        y_time_mult = multipliers.get('y_time_mult', 1.0)
                        
                        # Apply time multipliers to delay
                        actual_delay = delay_ms * x_time_mult
                        
                        # Calculate time since last bullet (in milliseconds)
                        # If _rcs_last_bullet_time is 0, it means this is the first bullet
                        if _rcs_last_bullet_time == 0:
                            # First bullet: apply immediately
                            x_movement = dx * x_mult
                            y_movement = dy * y_mult
                            _rcs_current_bullet += 1
                            _rcs_last_bullet_time = current_time
                            print(f"[DEBUG] RCS game mode bullet 1: dx={x_movement:.2f}, dy={y_movement:.2f}, delay={actual_delay:.1f}ms (mult: x={x_mult:.2f}, y={y_mult:.2f}, t={x_time_mult:.2f})")
                        else:
                            # Calculate time since last bullet (in milliseconds)
                            time_since_last_bullet = (current_time - _rcs_last_bullet_time) * 1000.0
                            
                            if time_since_last_bullet >= actual_delay:
                                # Enough time has passed, apply next bullet's movement
                                x_movement = dx * x_mult
                                y_movement = dy * y_mult
                                _rcs_current_bullet += 1
                                _rcs_last_bullet_time = current_time
                                
                                if _rcs_current_bullet <= len(_rcs_recoil_data):
                                    print(f"[DEBUG] RCS game mode bullet {_rcs_current_bullet}: dx={x_movement:.2f}, dy={y_movement:.2f}, delay={actual_delay:.1f}ms")
                                else:
                                    print(f"[DEBUG] RCS game mode: All {len(_rcs_recoil_data)} bullets applied, stopping recoil compensation")
                    else:
                        # All bullets fired, stop applying movement
                        # No looping - just stop after all data is applied
                        pass
                
                else:
                    # Simple mode: Original RCS behavior
                    # Apply X-axis downward compensation after initial delay and at regular intervals
                    if shooting_duration >= config.rcs_x_delay:
                        # Check if enough time has passed since last X compensation
                        if current_time - _last_rcs_x_time >= config.rcs_x_delay:
                            # Apply X-axis compensation (downward movement) 
                            y_movement += config.rcs_x_strength  # Downward is positive Y
                            _last_rcs_x_time = current_time
                            print(f"[DEBUG] RCS X-compensation applied: dy={config.rcs_x_strength:.2f}")
                    
                    # Apply Y-axis random jitter if enabled and at separate intervals
                    if config.rcs_y_random_enabled and shooting_duration >= config.rcs_y_random_delay:
                        # Check if enough time has passed since last Y jitter
                        if current_time - _last_rcs_y_time >= config.rcs_y_random_delay:
                            # Generate random horizontal movement (left/right jitter)
                            x_jitter = random.uniform(-config.rcs_y_random_strength, config.rcs_y_random_strength)
                            x_movement += x_jitter
                            _last_rcs_y_time = current_time
                            print(f"[DEBUG] RCS Y-jitter applied: dx={x_jitter:.2f}")
                
                # Apply combined movement using accumulation for fractional values
                if x_movement != 0 or y_movement != 0:
                    # Get Aimbot's Y-axis movement for compensation
                    global _aimbot_y_movement, _aimbot_y_lock
                    aimbot_y = 0.0
                    with _aimbot_y_lock:
                        aimbot_y = _aimbot_y_movement
                    
                    # Calculate Y-axis compensation: RCS needs to move down (positive Y)
                    # If Aimbot is also moving down (positive Y), subtract it to avoid double movement
                    # If Aimbot is moving up (negative Y), RCS should move more to compensate
                    compensated_y_movement = y_movement
                    if aimbot_y != 0:
                        # If both are moving in the same direction (both positive or both negative), subtract
                        # If moving in opposite directions, add (they cancel each other)
                        if (y_movement > 0 and aimbot_y > 0) or (y_movement < 0 and aimbot_y < 0):
                            # Same direction: subtract Aimbot's movement from RCS movement
                            compensated_y_movement = y_movement - aimbot_y
                            print(f"[DEBUG] RCS Y compensation: RCS={y_movement:.2f}, Aimbot={aimbot_y:.2f}, Compensated={compensated_y_movement:.2f}")
                        elif (y_movement > 0 and aimbot_y < 0) or (y_movement < 0 and aimbot_y > 0):
                            # Opposite directions: add them (they work together)
                            compensated_y_movement = y_movement - aimbot_y  # Subtract because aimbot_y is negative when moving up
                            print(f"[DEBUG] RCS Y compensation: RCS={y_movement:.2f}, Aimbot={aimbot_y:.2f}, Compensated={compensated_y_movement:.2f}")
                    
                    # Accumulate fractional movements
                    _rcs_accumulated_x += x_movement
                    _rcs_accumulated_y += compensated_y_movement
                    
                    # Calculate integer movement to send
                    send_x = int(_rcs_accumulated_x)
                    send_y = int(_rcs_accumulated_y)
                    
                    # Subtract sent movement from accumulation
                    _rcs_accumulated_x -= send_x
                    _rcs_accumulated_y -= send_y
                    
                    # Send movement only if there's integer movement to send
                    if send_x != 0 or send_y != 0:
                        if makcu:
                            makcu.move(send_x, send_y)
                            print(f"[DEBUG] RCS sent movement: dx={send_x}, dy={send_y} (RCS raw: {y_movement:.2f}, Aimbot: {aimbot_y:.2f}, Compensated: {compensated_y_movement:.2f}, accumulated: {_rcs_accumulated_x:.3f}, {_rcs_accumulated_y:.3f})")
                    else:
                        print(f"[DEBUG] RCS accumulating: dx={x_movement:.2f}, dy={compensated_y_movement:.2f} (raw: {y_movement:.2f}, aimbot: {aimbot_y:.2f}, total: {_rcs_accumulated_x:.3f}, {_rcs_accumulated_y:.3f})")
            
            # Small delay to prevent excessive CPU usage
            time.sleep(0.001)  # 1ms delay for high precision
            
        except Exception as e:
            print(f"[ERROR] RCS loop error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(0.01)

__all__ = [
    'start_aimbot', 'stop_aimbot', 'is_aimbot_running', 'reload_model',
    'get_model_classes', 'get_model_size', 'fps'
]
