import os
import customtkinter as ctk
from tkinter import messagebox, simpledialog, colorchooser
from config import config
from mouse import Mouse,connect_to_makcu, test_move, switch_to_4m
import main
from main import (
    start_aimbot, stop_aimbot, is_aimbot_running,
    reload_model, get_model_classes, get_model_size
)
import glob
from gui_sections import *
from gui_callbacks import *
from gui_constants import NEON, BG, neon_button
from config_manager import ConfigManager

ctk.set_appearance_mode("dark")


class EventuriGUI(ctk.CTk, GUISections, GUICallbacks):
    def __init__(self):
        super().__init__()
        self.title("EVENTURI-AI for MAKCU")
        
        # Get screen dimensions for responsive design
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Set initial size (90% of screen)
        initial_width = int(screen_width * 0.9)
        initial_height = int(screen_height * 0.9)
        
        # Center the window
        x = (screen_width - initial_width) // 2
        y = (screen_height - initial_height) // 2
        
        self.geometry(f"{initial_width}x{initial_height}+{x}+{y}")
        self.configure(bg=BG)
        self.resizable(True, True)  # Allow resizing
        self.minsize(900, 700)  # Set minimum size
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Configure grid weights for responsiveness
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Initialize config manager
        self.config_manager = ConfigManager()
        
        # Internal state
        self._makcu_connected = False
        self._last_model = None
        self.error_text = ctk.StringVar(value="")
        self.aimbot_status = ctk.StringVar(value="Stopped")
        self.connection_status = ctk.StringVar(value="Disconnected")
        self.connection_color = ctk.StringVar(value="#b71c1c")
        self.model_name = ctk.StringVar(value=getattr(config, "model_path", os.path.join("models", "Click here to Load a model")))
        self.model_size = ctk.StringVar(value="")
        self.aim_humanize_var = ctk.BooleanVar(value=bool(getattr(config, "aim_humanization", 0)))
        self.debug_checkbox_var = ctk.BooleanVar(value=False)
        self.input_check_var = ctk.BooleanVar(value=False)
        self.aim_button_mask_var = ctk.BooleanVar(value=bool(getattr(config, "aim_button_mask", False)))
        self.trigger_button_mask_var = ctk.BooleanVar(value=bool(getattr(config, "trigger_button_mask", False)))
        self._building = True
        self.fps_var = ctk.StringVar(value="FPS: 0")
        self._updating_conf = False
        self._updating_imgsz = False
        self.always_on_var = ctk.BooleanVar(value=bool(getattr(config, "always_on_aim", False)))
        self.trigger_enabled_var   = ctk.BooleanVar(value=bool(getattr(config, "trigger_enabled", False)))
        self.trigger_always_on_var = ctk.BooleanVar(value=bool(getattr(config, "trigger_always_on", False)))
        self.trigger_head_only_var = ctk.BooleanVar(value=bool(getattr(config, "trigger_head_only", False)))
        
        # RCS (Recoil Control System) variables
        self.rcs_enabled_var = ctk.BooleanVar(value=bool(getattr(config, "rcs_enabled", False)))
        self.rcs_ads_only_var = ctk.BooleanVar(value=bool(getattr(config, "rcs_ads_only", False)))
        self.rcs_disable_y_axis_var = ctk.BooleanVar(value=bool(getattr(config, "rcs_disable_y_axis", False)))
        self.rcs_y_random_enabled_var = ctk.BooleanVar(value=bool(getattr(config, "rcs_y_random_enabled", False)))
        self.rcs_btn_var = ctk.IntVar(value=int(getattr(config, "rcs_button", 0)))
        self.trigger_btn_var       = ctk.IntVar(value=int(getattr(config, "trigger_button", 0)))
        self.current_config_name = ctk.StringVar(value="config_profile")


        # Build UI and initialize
        self.build_responsive_ui()
        self._building = False
        self.refresh_all()
        self.poll_fps()

        # Auto-connect on startup and start polling status
        self.on_connect()
        self.after(500, self._poll_connection_status)

        # Bind resize event
        self.bind("<Configure>", self.on_window_resize)

    def build_responsive_ui(self):
        """Build the responsive UI with proper scaling"""
        
        # Create main scrollable frame
        self.main_frame = ctk.CTkScrollableFrame(
            self, 
            fg_color=BG,
            scrollbar_button_color=NEON,
            scrollbar_button_hover_color="#d50000"
        )
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Configure main frame grid
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # --- STATUS BAR (Enhanced) ---
        self.build_status_bar()
        
        # Create two-column layout for larger screens
        self.content_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(1, weight=1)
        
        # Left column
        self.left_column = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.left_column.grid_columnconfigure(0, weight=1)
        
        # Right column  
        self.right_column = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.right_column.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.right_column.grid_columnconfigure(0, weight=1)
        
        # Build sections in columns
        self.build_left_column()
        self.build_right_column()
        
        # Footer
        self.build_footer()

    def build_status_bar(self):
        """Enhanced status bar with better visual indicators"""
        status_frame = ctk.CTkFrame(self.main_frame, fg_color="#1a1a1a", height=80)
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        status_frame.grid_columnconfigure(1, weight=1)
        status_frame.grid_propagate(False)
        
        # --- Connection status with visual indicator (left) ---
        conn_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        conn_frame.grid(row=0, column=0, sticky="nsw", padx=10, pady=0)
        conn_frame.grid_rowconfigure(0, weight=1)
        
        # Connection indicator circle
        self.conn_indicator = ctk.CTkFrame(
            conn_frame, width=10, height=10, corner_radius=5, fg_color="#b71c1c"
        )
        self.conn_indicator.grid(row=0, column=0, padx=(0, 8))
        self.conn_indicator.grid_propagate(False)
        
        conn_text_frame = ctk.CTkFrame(conn_frame, fg_color="transparent")
        conn_text_frame.grid(row=0, column=1)
        ctk.CTkLabel(
            conn_text_frame, 
            text="MAKCU Device", 
            font=("Segoe UI", 12, "bold"),
            text_color="#ccc"
        ).grid(row=0, column=0, sticky="w")
        self.conn_status_lbl = ctk.CTkLabel(
            conn_text_frame,
            textvariable=self.connection_status,
            font=("Segoe UI", 14, "bold"),
            text_color=self.connection_color.get()
        )
        self.conn_status_lbl.grid(row=1, column=0, sticky="w", pady=(0, 27))
        
        # --- Info panel (center/right) ---
        info_frame = ctk.CTkFrame(status_frame, fg_color="#2a2a2a", corner_radius=10)
        info_frame.grid(row=0, column=1, sticky="ew", padx=15, pady=10)
        info_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        # --- Aimbot status ---
        aimbot_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        aimbot_frame.grid(row=0, column=0, padx=10, pady=8, sticky="nsew")
        ctk.CTkLabel(aimbot_frame, text="Aimbot", font=("Segoe UI", 11), text_color="#ccc") \
            .grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(aimbot_frame, textvariable=self.aimbot_status, font=("Segoe UI", 13, "bold"), text_color=NEON) \
            .grid(row=1, column=0, sticky="w")
        
        # --- Model info ---
        model_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        model_frame.grid(row=0, column=1, padx=10, pady=8, sticky="nsew")
        ctk.CTkLabel(model_frame, text="AI Model", font=("Segoe UI", 11), text_color="#ccc") \
            .grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(model_frame, textvariable=self.model_name, font=("Segoe UI", 12, "bold"), text_color="#00bcd4") \
            .grid(row=1, column=0, sticky="w")
        ctk.CTkLabel(model_frame, textvariable=self.model_size, font=("Segoe UI", 10), text_color="#888") \
            .grid(row=2, column=0, sticky="w")
        
        # --- FPS ---
        fps_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        fps_frame.grid(row=0, column=2, padx=10, pady=8, sticky="nsew")
        ctk.CTkLabel(fps_frame, text="Performance", font=("Segoe UI", 11), text_color="#ccc") \
            .grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(fps_frame, textvariable=self.fps_var, font=("Segoe UI", 13, "bold"), text_color="#00e676") \
            .grid(row=1, column=0, sticky="w")
        
        # --- Error display (full width below status) ---
        self.error_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        self.error_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=15)
        self.error_lbl = ctk.CTkLabel(
            self.error_frame, 
            textvariable=self.error_text, 
            font=("Segoe UI", 11, "bold"),
            text_color=NEON,
            wraplength=800
        )
        self.error_lbl.grid(row=0, column=0, sticky="ew")
        self.error_frame.grid_columnconfigure(0, weight=1)

    def build_left_column(self):
        row = 0
        self.build_device_controls(self.left_column, row); row += 1
        # NEW:
        self.build_capture_controls(self.left_column, row); row += 1
        # Detection, Aim, Mode, Dynamic, etc. follow:
        self.build_detection_settings(self.left_column, row); row += 1
        self.build_aim_settings(self.left_column, row); row += 1
        self.build_rcs_settings(self.left_column, row); row += 1
        self.build_aimbot_mode(self.left_column, row); row += 1
        self.dynamic_frame = ctk.CTkFrame(self.left_column, fg_color=BG)
        self.dynamic_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        self.dynamic_frame.grid_columnconfigure(0, weight=1)

    def build_right_column(self):
        """Build right column content"""
        row = 0
        
        # Model Settings
        self.build_model_settings(self.right_column, row)
        row += 1
        
        # Class Selection
        self.build_class_selection(self.right_column, row)
        row += 1

        # Triggerbot section here
        self.build_triggerbot_settings(self.right_column, row); row += 1

        # Profile Controls
        self.build_profile_controls(self.right_column, row)
        row += 1
        
        # Main Controls
        self.build_main_controls(self.right_column, row)

    def build_device_controls(self, parent, row):
        """MAKCU device controls (top section)"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="🔌 Device Controls", font=("Segoe UI", 16, "bold"),
                    text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(15, 10), padx=15, sticky="w")

        self.connect_btn = neon_button(frame, text="Connect to MAKCU", command=self.on_connect, width=150, height=35)
        self.connect_btn.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")

        ctk.CTkButton(frame, text="Test Move", command=test_move, width=100, height=35,
                    fg_color="#333", hover_color="#555").grid(row=1, column=1, padx=10, pady=(0, 15), sticky="w")
        
        ctk.CTkButton(frame, text="Switch to 4M", command=self.on_switch_to_4m, width=100, height=35,
                    fg_color="#333", hover_color="#555").grid(row=1, column=2, padx=10, pady=(0, 15), sticky="w")
        
        self.input_check_checkbox = ctk.CTkCheckBox(
            frame, text="Input Monitor", variable=self.input_check_var,
            command=self.on_input_check_toggle, text_color="#fff"
        )
        self.input_check_checkbox.grid(row=1, column=3, padx=15, pady=(0, 15), sticky="w")

        self.aim_button_mask_switch = ctk.CTkSwitch(
            frame,
            text="Aim Button Masking",
            variable=self.aim_button_mask_var,
            command=self.on_aim_button_mask_toggle,
            text_color="#fff"
        )
        self.aim_button_mask_switch.grid(row=1, column=4, padx=15, pady=(0, 15), sticky="w")
        
        self.trigger_button_mask_switch = ctk.CTkSwitch(
            frame,
            text="Trigger Button Masking",
            variable=self.trigger_button_mask_var,
            command=self.on_trigger_button_mask_toggle,
            text_color="#fff"
        )
        self.trigger_button_mask_switch.grid(row=1, column=5, padx=15, pady=(0, 15), sticky="w")
        
        


    def build_capture_controls(self, parent, row):
        """Capture controls (bottom section): capture method + NDI source + toggles"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="📷 Capture Controls", font=("Segoe UI", 16, "bold"),
                    text_color="#00e676").grid(row=0, column=0, columnspan=4, pady=(15, 10), padx=15, sticky="w")

        # Capture Method
        ctk.CTkLabel(frame, text="Capture Method:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=1, column=0, sticky="w", padx=15)
        self.capture_mode_var = ctk.StringVar(value=config.capturer_mode.upper())
        self.capture_mode_menu = ctk.CTkOptionMenu(
            frame, values=["MSS", "NDI", "DXGI", "CaptureCard", "UDP"], variable=self.capture_mode_var,
            command=self.on_capture_mode_change, width=110
        )
        self.capture_mode_menu.grid(row=1, column=1, sticky="w", padx=(5, 15), pady=10)

        # --- NDI-only block (shown only when capture mode = NDI) ---
        self.ndi_block = ctk.CTkFrame(frame, fg_color="transparent")
        # we'll grid/place this in _update_ndi_controls_state()
        # internal grid for the block
        self.ndi_block.grid_columnconfigure(1, weight=1)

        # NDI Source dropdown (auto-refreshing)
        ctk.CTkLabel(self.ndi_block, text="NDI Source:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=0, column=0, sticky="w", padx=15)
        self.ndi_source_var = ctk.StringVar(value=self._initial_ndi_source_value())
        self.ndi_source_menu = ctk.CTkOptionMenu(
            self.ndi_block,
            values=self._ndi_menu_values(),
            variable=self.ndi_source_var,
            command=self.on_ndi_source_change,
            width=260
        )
        self.ndi_source_menu.grid(row=0, column=1, sticky="w", padx=(5, 15), pady=(0, 8))

        # Main PC Resolution (width × height)
        ctk.CTkLabel(self.ndi_block, text="Main PC Resolution:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=1, column=0, sticky="w", padx=15, pady=(0, 10))

        res_wrap = ctk.CTkFrame(self.ndi_block, fg_color="transparent")
        res_wrap.grid(row=1, column=1, sticky="w", padx=(5, 15), pady=(0, 10))

        self.main_res_w_entry = ctk.CTkEntry(res_wrap, width=90, justify="center")
        self.main_res_w_entry.pack(side="left")
        self.main_res_w_entry.insert(0, str(getattr(config, "main_pc_width", 1920)))

        ctk.CTkLabel(res_wrap, text=" × ", font=("Segoe UI", 14), text_color="#ffffff")\
            .pack(side="left", padx=6)

        self.main_res_h_entry = ctk.CTkEntry(res_wrap, width=90, justify="center")
        self.main_res_h_entry.pack(side="left")
        self.main_res_h_entry.insert(0, str(getattr(config, "main_pc_height", 1080)))

        def _commit_main_res(event=None):
            try:
                w = int(self.main_res_w_entry.get().strip())
                h = int(self.main_res_h_entry.get().strip())
                w = max(320, min(7680, w))
                h = max(240, min(4320, h))
                config.main_pc_width = w
                config.main_pc_height = h
                self.main_res_w_entry.delete(0, "end"); self.main_res_w_entry.insert(0, str(w))
                self.main_res_h_entry.delete(0, "end"); self.main_res_h_entry.insert(0, str(h))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.main_res_w_entry.delete(0, "end"); self.main_res_w_entry.insert(0, str(getattr(config, "main_pc_width", 1920)))
                self.main_res_h_entry.delete(0, "end"); self.main_res_h_entry.insert(0, str(getattr(config, "main_pc_height", 1080)))

        self.main_res_w_entry.bind("<Return>", _commit_main_res)
        self.main_res_h_entry.bind("<Return>", _commit_main_res)
        self.main_res_w_entry.bind("<FocusOut>", _commit_main_res)
        self.main_res_h_entry.bind("<FocusOut>", _commit_main_res)

        # Toggles
        self.debug_checkbox = ctk.CTkCheckBox(
            frame, text="Debug Window", variable=self.debug_checkbox_var,
            command=self.on_debug_toggle, text_color="#fff"
        )
        self.debug_checkbox.grid(row=4, column=0, sticky="w", padx=15, pady=(5, 8))
        
        # Text Info checkbox (only visible when debug window is enabled)
        self.debug_text_info_var = ctk.BooleanVar(value=config.show_debug_text_info)
        self.debug_text_info_checkbox = ctk.CTkCheckBox(
            frame, text="  ↳ Text Info", variable=self.debug_text_info_var,
            command=self.on_debug_text_info_toggle, text_color="#ccc",
            font=("Segoe UI", 11)
        )
        self.debug_text_info_checkbox.grid(row=5, column=0, sticky="w", padx=30, pady=(0, 15))

        # --- CaptureCard-only block (shown only when capture mode = CaptureCard) ---
        self.capturecard_block = ctk.CTkFrame(frame, fg_color="transparent")
        # we'll grid/place this in _update_capturecard_controls_state()
        # internal grid for the block
        self.capturecard_block.grid_columnconfigure(1, weight=1)
        self.capturecard_block.grid_columnconfigure(3, weight=1)

        # Row 0: Device Index | FourCC Format
        ctk.CTkLabel(self.capturecard_block, text="Device Index:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=0, column=0, sticky="w", padx=15)
        self.capturecard_device_var = ctk.StringVar(value=str(getattr(config, "capture_device_index", 0)))
        self.capturecard_device_entry = ctk.CTkEntry(
            self.capturecard_block, width=80, justify="center"
        )
        self.capturecard_device_entry.grid(row=0, column=1, sticky="w", padx=(5, 15), pady=(0, 8))
        self.capturecard_device_entry.insert(0, str(getattr(config, "capture_device_index", 0)))

        ctk.CTkLabel(self.capturecard_block, text="FourCC Format:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=0, column=2, sticky="w", padx=15, pady=(0, 8))
        self.capturecard_fourcc_var = ctk.StringVar(value=",".join(getattr(config, "capture_fourcc_preference", ["NV12", "YUY2", "MJPG"])))
        self.capturecard_fourcc_entry = ctk.CTkEntry(
            self.capturecard_block, width=120, justify="center"
        )
        self.capturecard_fourcc_entry.grid(row=0, column=3, sticky="w", padx=(5, 15), pady=(0, 8))
        self.capturecard_fourcc_entry.insert(0, ",".join(getattr(config, "capture_fourcc_preference", ["NV12", "YUY2", "MJPG"])))

        # Row 1: Resolution | Target FPS
        ctk.CTkLabel(self.capturecard_block, text="Resolution:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=1, column=0, sticky="w", padx=15, pady=(0, 10))

        res_wrap = ctk.CTkFrame(self.capturecard_block, fg_color="transparent")
        res_wrap.grid(row=1, column=1, sticky="w", padx=(5, 15), pady=(0, 10))

        self.capturecard_res_w_entry = ctk.CTkEntry(res_wrap, width=90, justify="center")
        self.capturecard_res_w_entry.pack(side="left")
        self.capturecard_res_w_entry.insert(0, str(getattr(config, "capture_width", 1920)))

        ctk.CTkLabel(res_wrap, text=" × ", font=("Segoe UI", 14), text_color="#ffffff")\
            .pack(side="left", padx=6)

        self.capturecard_res_h_entry = ctk.CTkEntry(res_wrap, width=90, justify="center")
        self.capturecard_res_h_entry.pack(side="left")
        self.capturecard_res_h_entry.insert(0, str(getattr(config, "capture_height", 1080)))

        ctk.CTkLabel(self.capturecard_block, text="Target FPS:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=1, column=2, sticky="w", padx=15, pady=(0, 10))
        self.capturecard_fps_var = ctk.StringVar(value=str(getattr(config, "capture_fps", 240)))
        self.capturecard_fps_entry = ctk.CTkEntry(
            self.capturecard_block, width=80, justify="center"
        )
        self.capturecard_fps_entry.grid(row=1, column=3, sticky="w", padx=(5, 15), pady=(0, 10))
        self.capturecard_fps_entry.insert(0, str(getattr(config, "capture_fps", 240)))

        # Row 2: X Range | Y Range
        ctk.CTkLabel(self.capturecard_block, text="X Range:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=2, column=0, sticky="w", padx=15, pady=(0, 10))
        self.capturecard_range_x_entry = ctk.CTkEntry(
            self.capturecard_block, width=80, justify="center"
        )
        self.capturecard_range_x_entry.grid(row=2, column=1, sticky="w", padx=(5, 15), pady=(0, 10))
        self.capturecard_range_x_entry.insert(0, str(getattr(config, "capture_range_x", 0)))

        ctk.CTkLabel(self.capturecard_block, text="Y Range:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=2, column=2, sticky="w", padx=15, pady=(0, 10))
        self.capturecard_range_y_entry = ctk.CTkEntry(
            self.capturecard_block, width=80, justify="center"
        )
        self.capturecard_range_y_entry.grid(row=2, column=3, sticky="w", padx=(5, 15), pady=(0, 10))
        self.capturecard_range_y_entry.insert(0, str(getattr(config, "capture_range_y", 0)))

        # Row 3: X Offset | Y Offset
        ctk.CTkLabel(self.capturecard_block, text="X Offset:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=3, column=0, sticky="w", padx=15, pady=(0, 10))
        self.capturecard_offset_x_entry = ctk.CTkEntry(
            self.capturecard_block, width=80, justify="center"
        )
        self.capturecard_offset_x_entry.grid(row=3, column=1, sticky="w", padx=(5, 15), pady=(0, 10))
        self.capturecard_offset_x_entry.insert(0, str(getattr(config, "capture_offset_x", 0)))

        ctk.CTkLabel(self.capturecard_block, text="Y Offset:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=3, column=2, sticky="w", padx=15, pady=(0, 10))
        self.capturecard_offset_y_entry = ctk.CTkEntry(
            self.capturecard_block, width=80, justify="center"
        )
        self.capturecard_offset_y_entry.grid(row=3, column=3, sticky="w", padx=(5, 15), pady=(0, 10))
        self.capturecard_offset_y_entry.insert(0, str(getattr(config, "capture_offset_y", 0)))

        # Row 4: Center X Offset | Center Y Offset
        ctk.CTkLabel(self.capturecard_block, text="Center X Offset:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=4, column=0, sticky="w", padx=15, pady=(0, 10))
        self.capturecard_center_offset_x_entry = ctk.CTkEntry(
            self.capturecard_block, width=80, justify="center"
        )
        self.capturecard_center_offset_x_entry.grid(row=4, column=1, sticky="w", padx=(5, 15), pady=(0, 10))
        self.capturecard_center_offset_x_entry.insert(0, str(getattr(config, "capture_center_offset_x", 0)))

        ctk.CTkLabel(self.capturecard_block, text="Center Y Offset:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=4, column=2, sticky="w", padx=15, pady=(0, 10))
        self.capturecard_center_offset_y_entry = ctk.CTkEntry(
            self.capturecard_block, width=80, justify="center"
        )
        self.capturecard_center_offset_y_entry.grid(row=4, column=3, sticky="w", padx=(5, 15), pady=(0, 10))
        self.capturecard_center_offset_y_entry.insert(0, str(getattr(config, "capture_center_offset_y", 0)))

        # Bind events for capture card controls
        def _commit_capturecard_device(event=None):
            try:
                device_idx = int(self.capturecard_device_entry.get().strip())
                device_idx = max(0, min(10, device_idx))  # Reasonable range
                config.capture_device_index = device_idx
                self.capturecard_device_entry.delete(0, "end")
                self.capturecard_device_entry.insert(0, str(device_idx))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.capturecard_device_entry.delete(0, "end")
                self.capturecard_device_entry.insert(0, str(getattr(config, "capture_device_index", 0)))

        def _commit_capturecard_res(event=None):
            try:
                w = int(self.capturecard_res_w_entry.get().strip())
                h = int(self.capturecard_res_h_entry.get().strip())
                w = max(320, min(7680, w))
                h = max(240, min(4320, h))
                config.capture_width = w
                config.capture_height = h
                self.capturecard_res_w_entry.delete(0, "end")
                self.capturecard_res_w_entry.insert(0, str(w))
                self.capturecard_res_h_entry.delete(0, "end")
                self.capturecard_res_h_entry.insert(0, str(h))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.capturecard_res_w_entry.delete(0, "end")
                self.capturecard_res_w_entry.insert(0, str(getattr(config, "capture_width", 1920)))
                self.capturecard_res_h_entry.delete(0, "end")
                self.capturecard_res_h_entry.insert(0, str(getattr(config, "capture_height", 1080)))

        def _commit_capturecard_fps(event=None):
            try:
                fps = float(self.capturecard_fps_entry.get().strip())
                fps = max(1, min(300, fps))  # Reasonable range
                config.capture_fps = fps
                self.capturecard_fps_entry.delete(0, "end")
                self.capturecard_fps_entry.insert(0, str(int(fps)))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.capturecard_fps_entry.delete(0, "end")
                self.capturecard_fps_entry.insert(0, str(getattr(config, "capture_fps", 240)))

        def _commit_capturecard_fourcc(event=None):
            try:
                fourcc_str = self.capturecard_fourcc_entry.get().strip()
                fourcc_list = [f.strip().upper() for f in fourcc_str.split(",") if f.strip()]
                if fourcc_list:
                    config.capture_fourcc_preference = fourcc_list
                    self.capturecard_fourcc_entry.delete(0, "end")
                    self.capturecard_fourcc_entry.insert(0, ",".join(fourcc_list))
                    if hasattr(config, "save") and callable(config.save):
                        config.save()
            except Exception:
                self.capturecard_fourcc_entry.delete(0, "end")
                self.capturecard_fourcc_entry.insert(0, ",".join(getattr(config, "capture_fourcc_preference", ["NV12", "YUY2", "MJPG"])))

        def _commit_capturecard_range_x(event=None):
            try:
                range_x = int(self.capturecard_range_x_entry.get().strip())
                range_x = max(0, min(10000, range_x))  # Reasonable range (0 = use region_size)
                config.capture_range_x = range_x
                
                # Output change information
                if range_x > 0:
                    print(f"[CaptureCard X Range] Changed to: {range_x} pixels")
                    print(f"[CaptureCard Crop Region] Width set to: {range_x} pixels (Real-time update)")
                else:
                    print(f"[CaptureCard X Range] Changed to: {range_x} (will use region_size: {config.region_size})")
                
                self.capturecard_range_x_entry.delete(0, "end")
                self.capturecard_range_x_entry.insert(0, str(range_x))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.capturecard_range_x_entry.delete(0, "end")
                self.capturecard_range_x_entry.insert(0, str(getattr(config, "capture_range_x", 0)))

        def _commit_capturecard_range_y(event=None):
            try:
                range_y = int(self.capturecard_range_y_entry.get().strip())
                range_y = max(0, min(10000, range_y))  # Reasonable range (0 = use region_size)
                config.capture_range_y = range_y
                
                # Output change information
                if range_y > 0:
                    print(f"[CaptureCard Y Range] Changed to: {range_y} pixels")
                    print(f"[CaptureCard Crop Region] Height set to: {range_y} pixels (Real-time update)")
                else:
                    print(f"[CaptureCard Y Range] Changed to: {range_y} (will use region_size: {config.region_size})")
                
                self.capturecard_range_y_entry.delete(0, "end")
                self.capturecard_range_y_entry.insert(0, str(range_y))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.capturecard_range_y_entry.delete(0, "end")
                self.capturecard_range_y_entry.insert(0, str(getattr(config, "capture_range_y", 0)))

        def _commit_capturecard_offset_x(event=None):
            try:
                offset_x = int(self.capturecard_offset_x_entry.get().strip())
                offset_x = max(-10000, min(10000, offset_x))  # Reasonable range (can be negative)
                config.capture_offset_x = offset_x
                self.capturecard_offset_x_entry.delete(0, "end")
                self.capturecard_offset_x_entry.insert(0, str(offset_x))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.capturecard_offset_x_entry.delete(0, "end")
                self.capturecard_offset_x_entry.insert(0, str(getattr(config, "capture_offset_x", 0)))

        def _commit_capturecard_offset_y(event=None):
            try:
                offset_y = int(self.capturecard_offset_y_entry.get().strip())
                offset_y = max(-10000, min(10000, offset_y))  # Reasonable range (can be negative)
                config.capture_offset_y = offset_y
                self.capturecard_offset_y_entry.delete(0, "end")
                self.capturecard_offset_y_entry.insert(0, str(offset_y))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.capturecard_offset_y_entry.delete(0, "end")
                self.capturecard_offset_y_entry.insert(0, str(getattr(config, "capture_offset_y", 0)))

        def _commit_capturecard_center_offset_x(event=None):
            try:
                center_offset_x = int(self.capturecard_center_offset_x_entry.get().strip())
                center_offset_x = max(-10000, min(10000, center_offset_x))  # Reasonable range (can be negative)
                config.capture_center_offset_x = center_offset_x
                print(f"[CaptureCard Center X Offset] Changed to: {center_offset_x} pixels")
                print(f"[FOV Center] X position offset by: {center_offset_x} pixels (Real-time update)")
                self.capturecard_center_offset_x_entry.delete(0, "end")
                self.capturecard_center_offset_x_entry.insert(0, str(center_offset_x))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.capturecard_center_offset_x_entry.delete(0, "end")
                self.capturecard_center_offset_x_entry.insert(0, str(getattr(config, "capture_center_offset_x", 0)))

        def _commit_capturecard_center_offset_y(event=None):
            try:
                center_offset_y = int(self.capturecard_center_offset_y_entry.get().strip())
                center_offset_y = max(-10000, min(10000, center_offset_y))  # Reasonable range (can be negative)
                config.capture_center_offset_y = center_offset_y
                print(f"[CaptureCard Center Y Offset] Changed to: {center_offset_y} pixels")
                print(f"[FOV Center] Y position offset by: {center_offset_y} pixels (Real-time update)")
                self.capturecard_center_offset_y_entry.delete(0, "end")
                self.capturecard_center_offset_y_entry.insert(0, str(center_offset_y))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.capturecard_center_offset_y_entry.delete(0, "end")
                self.capturecard_center_offset_y_entry.insert(0, str(getattr(config, "capture_center_offset_y", 0)))

        # Bind events
        self.capturecard_device_entry.bind("<Return>", _commit_capturecard_device)
        self.capturecard_device_entry.bind("<FocusOut>", _commit_capturecard_device)
        self.capturecard_res_w_entry.bind("<Return>", _commit_capturecard_res)
        self.capturecard_res_h_entry.bind("<Return>", _commit_capturecard_res)
        self.capturecard_res_w_entry.bind("<FocusOut>", _commit_capturecard_res)
        self.capturecard_res_h_entry.bind("<FocusOut>", _commit_capturecard_res)
        self.capturecard_fps_entry.bind("<Return>", _commit_capturecard_fps)
        self.capturecard_fps_entry.bind("<FocusOut>", _commit_capturecard_fps)
        self.capturecard_fourcc_entry.bind("<Return>", _commit_capturecard_fourcc)
        self.capturecard_fourcc_entry.bind("<FocusOut>", _commit_capturecard_fourcc)
        self.capturecard_range_x_entry.bind("<Return>", _commit_capturecard_range_x)
        self.capturecard_range_x_entry.bind("<FocusOut>", _commit_capturecard_range_x)
        self.capturecard_range_y_entry.bind("<Return>", _commit_capturecard_range_y)
        self.capturecard_range_y_entry.bind("<FocusOut>", _commit_capturecard_range_y)
        self.capturecard_offset_x_entry.bind("<Return>", _commit_capturecard_offset_x)
        self.capturecard_offset_x_entry.bind("<FocusOut>", _commit_capturecard_offset_x)
        self.capturecard_offset_y_entry.bind("<Return>", _commit_capturecard_offset_y)
        self.capturecard_offset_y_entry.bind("<FocusOut>", _commit_capturecard_offset_y)
        self.capturecard_center_offset_x_entry.bind("<Return>", _commit_capturecard_center_offset_x)
        self.capturecard_center_offset_x_entry.bind("<FocusOut>", _commit_capturecard_center_offset_x)
        self.capturecard_center_offset_y_entry.bind("<Return>", _commit_capturecard_center_offset_y)
        self.capturecard_center_offset_y_entry.bind("<FocusOut>", _commit_capturecard_center_offset_y)

        # --- UDP-only block (shown only when capture mode = UDP) ---
        self.udp_block = ctk.CTkFrame(frame, fg_color="transparent")
        # we'll grid/place this in _update_udp_controls_state()
        # internal grid for the block
        self.udp_block.grid_columnconfigure(1, weight=1)

        # UDP IP Address
        ctk.CTkLabel(self.udp_block, text="UDP IP:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=0, column=0, sticky="w", padx=15)
        self.udp_ip_var = ctk.StringVar(value=getattr(config, "udp_ip", "192.168.0.01"))
        self.udp_ip_entry = ctk.CTkEntry(
            self.udp_block, width=120, justify="center"
        )
        self.udp_ip_entry.grid(row=0, column=1, sticky="w", padx=(5, 15), pady=(0, 8))
        self.udp_ip_entry.insert(0, getattr(config, "udp_ip", "192.168.0.01"))

        # UDP Port
        ctk.CTkLabel(self.udp_block, text="UDP Port:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=1, column=0, sticky="w", padx=15, pady=(0, 10))
        self.udp_port_var = ctk.StringVar(value=str(getattr(config, "udp_port", 1234)))
        self.udp_port_entry = ctk.CTkEntry(
            self.udp_block, width=80, justify="center"
        )
        self.udp_port_entry.grid(row=1, column=1, sticky="w", padx=(5, 15), pady=(0, 10))
        self.udp_port_entry.insert(0, str(getattr(config, "udp_port", 1234)))

        # Bind events for UDP controls
        def _commit_udp_ip(event=None):
            try:
                ip = self.udp_ip_entry.get().strip()
                # Basic IP validation
                if ip and len(ip.split('.')) == 4:
                    config.udp_ip = ip
                    if hasattr(config, "save") and callable(config.save):
                        config.save()
                else:
                    self.udp_ip_entry.delete(0, "end")
                    self.udp_ip_entry.insert(0, getattr(config, "udp_ip", "192.168.0.01"))
            except Exception:
                self.udp_ip_entry.delete(0, "end")
                self.udp_ip_entry.insert(0, getattr(config, "udp_ip", "192.168.0.01"))

        def _commit_udp_port(event=None):
            try:
                port = int(self.udp_port_entry.get().strip())
                port = max(1024, min(65535, port))  # Reasonable range
                config.udp_port = port
                self.udp_port_entry.delete(0, "end")
                self.udp_port_entry.insert(0, str(port))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.udp_port_entry.delete(0, "end")
                self.udp_port_entry.insert(0, str(getattr(config, "udp_port", 1234)))

        # Bind events
        self.udp_ip_entry.bind("<Return>", _commit_udp_ip)
        self.udp_ip_entry.bind("<FocusOut>", _commit_udp_ip)
        self.udp_port_entry.bind("<Return>", _commit_udp_port)
        self.udp_port_entry.bind("<FocusOut>", _commit_udp_port)

        # Initial enable/disable state
        self._update_ndi_controls_state()
        self._update_capturecard_controls_state()
        self._update_udp_controls_state()

        # Start polling for source list updates
        self.after(1000, self._poll_ndi_sources)

    def _ndi_menu_values(self):
        # Show something friendly when empty
        return config.ndi_sources if config.ndi_sources else ["(no NDI sources found)"]

    def _initial_ndi_source_value(self):
        # If we have a persisted selection and it still exists, use it; else first
        sel = config.ndi_selected_source
        if isinstance(sel, str) and sel in config.ndi_sources:
            return sel
        # fallbacks
        return config.ndi_sources[0] if config.ndi_sources else "(no NDI sources found)"

    def _update_ndi_controls_state(self):
        is_ndi = (self.capture_mode_var.get().upper() == "NDI")

        # Show/hide the whole NDI block
        try:
            if is_ndi:
                self.ndi_block.grid(row=2, column=0, columnspan=2, sticky="ew")
            else:
                self.ndi_block.grid_remove()
        except Exception:
            pass

        # Enable/disable internal controls just in case
        try:
            state = "normal" if is_ndi else "disabled"
            self.ndi_source_menu.configure(state=state)
            self.main_res_w_entry.configure(state=state)
            self.main_res_h_entry.configure(state=state)
        except Exception:
            pass

        try:
            if is_ndi:
                self.debug_checkbox.grid_configure(row=4)
                self.debug_text_info_checkbox.grid_configure(row=5)
            else:
                # When not NDI mode, adjust based on other capture modes
                if self.capture_mode_var.get().upper() == "UDP":
                    self.debug_checkbox.grid_configure(row=3)
                    self.debug_text_info_checkbox.grid_configure(row=4)
                elif self.capture_mode_var.get().upper() == "CAPTURECARD":
                    self.debug_checkbox.grid_configure(row=6)
                    self.debug_text_info_checkbox.grid_configure(row=7)
                else:
                    self.debug_checkbox.grid_configure(row=2)
                    self.debug_text_info_checkbox.grid_configure(row=3)
        except Exception:
            pass

    def _update_capturecard_controls_state(self):
        is_capturecard = (self.capture_mode_var.get().upper() == "CAPTURECARD")

        # Show/hide the whole CaptureCard block
        try:
            if is_capturecard:
                self.capturecard_block.grid(row=2, column=0, columnspan=2, sticky="ew")
            else:
                self.capturecard_block.grid_remove()
        except Exception:
            pass

        # Enable/disable internal controls just in case
        try:
            state = "normal" if is_capturecard else "disabled"
            self.capturecard_device_entry.configure(state=state)
            self.capturecard_res_w_entry.configure(state=state)
            self.capturecard_res_h_entry.configure(state=state)
            self.capturecard_fps_entry.configure(state=state)
            self.capturecard_fourcc_entry.configure(state=state)
            self.capturecard_range_x_entry.configure(state=state)
            self.capturecard_range_y_entry.configure(state=state)
            self.capturecard_offset_x_entry.configure(state=state)
            self.capturecard_offset_y_entry.configure(state=state)
        except Exception:
            pass

        try:
            # Adjust debug checkbox position based on capture mode
            if is_capturecard:
                self.debug_checkbox.grid_configure(row=8)  # After capturecard controls (now 8 rows: 0-7)
                self.debug_text_info_checkbox.grid_configure(row=9)
            else:
                # When not CaptureCard mode, adjust based on other capture modes
                if self.capture_mode_var.get().upper() == "NDI":
                    self.debug_checkbox.grid_configure(row=4)
                    self.debug_text_info_checkbox.grid_configure(row=5)
                elif self.capture_mode_var.get().upper() == "UDP":
                    self.debug_checkbox.grid_configure(row=3)
                    self.debug_text_info_checkbox.grid_configure(row=4)
                else:
                    self.debug_checkbox.grid_configure(row=2)
                    self.debug_text_info_checkbox.grid_configure(row=3)
        except Exception:
            pass

    def _update_udp_controls_state(self):
        is_udp = (self.capture_mode_var.get().upper() == "UDP")

        # Show/hide the whole UDP block
        try:
            if is_udp:
                self.udp_block.grid(row=2, column=0, columnspan=2, sticky="ew")
            else:
                self.udp_block.grid_remove()
        except Exception:
            pass

        # Enable/disable internal controls just in case
        try:
            state = "normal" if is_udp else "disabled"
            self.udp_ip_entry.configure(state=state)
            self.udp_port_entry.configure(state=state)
        except Exception:
            pass

        try:
            # Adjust debug checkbox position based on capture mode
            if is_udp:
                self.debug_checkbox.grid_configure(row=3)  # After UDP controls (UDP only has 2 rows)
                self.debug_text_info_checkbox.grid_configure(row=4)  # Text info after debug checkbox
            else:
                # When not UDP mode, adjust based on other capture modes
                if self.capture_mode_var.get().upper() == "NDI":
                    self.debug_checkbox.grid_configure(row=4)
                    self.debug_text_info_checkbox.grid_configure(row=5)
                elif self.capture_mode_var.get().upper() == "CAPTURECARD":
                    self.debug_checkbox.grid_configure(row=6)
                    self.debug_text_info_checkbox.grid_configure(row=7)
                else:
                    self.debug_checkbox.grid_configure(row=2)  # Default position
                    self.debug_text_info_checkbox.grid_configure(row=3)
        except Exception:
            pass

    def _poll_ndi_sources(self):
        latest = list(config.ndi_sources) if isinstance(config.ndi_sources, list) else []

        # 1) Always push the latest values into the menu
        if not latest:
            latest = ["(Start Aimbot to find avalible NDI sources)"]

        try:
            self.ndi_source_menu.configure(values=latest)
        except Exception:
            # widget not ready yet, try again next tick
            self.after(1000, self._poll_ndi_sources)
            return

        # 2) Keep the selection sensible
        current = self.ndi_source_var.get()
        if current not in latest:
            if isinstance(config.ndi_selected_source, str) and config.ndi_selected_source in latest:
                choice = config.ndi_selected_source
            else:
                choice = latest[0]


            self.ndi_source_var.set(choice)
            try:
                self.ndi_source_menu.set(choice)
            except Exception:
                pass

            if self.capture_mode_var.get().upper() == "NDI" and not choice.startswith("("):
                config.ndi_selected_source = choice
                config.save()

        # 3) Reflect enable/disable based on mode
        self._update_ndi_controls_state()

        # tick again
        self.after(1000, self._poll_ndi_sources)
    
    
    def build_triggerbot_settings(self, parent, row):
        """Standalone Triggerbot section (right column)."""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="🧨 Triggerbot", font=("Segoe UI", 16, "bold"),
                    text_color="#00e676").grid(row=0, column=0, columnspan=2,
                                                pady=(15, 10), padx=15, sticky="w")

        # --- toggles
        toggles = ctk.CTkFrame(frame, fg_color="transparent")
        toggles.grid(row=1, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 10))
        toggles.grid_columnconfigure(1, weight=1)

        def _on_enabled_then_focus():
            self.on_trigger_enabled_toggle()
            if self.trigger_enabled_var.get():
                try:
                    self.tb_radius_entry.focus_set()
                    self.tb_radius_entry.select_range(0, "end")
                except Exception:
                    pass

        ctk.CTkSwitch(toggles, text="Enabled", text_color="#fff",
                    variable=self.trigger_enabled_var,
                    command=_on_enabled_then_focus).pack(side="left", padx=(0, 15))

        ctk.CTkSwitch(toggles, text="Always on", text_color="#fff",
                    variable=self.trigger_always_on_var,
                    command=self.on_trigger_always_on_toggle).pack(side="left", padx=(0, 15))
        
        # Head Only checkbox - only visible when Head Class is selected
        self.trigger_head_only_switch = ctk.CTkSwitch(toggles, text="Head Only", text_color="#fff",
                    variable=self.trigger_head_only_var,
                    command=self.on_trigger_head_only_toggle)
        self.trigger_head_only_switch.pack(side="left")
        self._update_trigger_head_only_visibility()

        # --- trigger mode row
        mode_row = ctk.CTkFrame(frame, fg_color="transparent")
        mode_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 10))
        mode_row.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(mode_row, text="Mode:", font=("Segoe UI", 12, "bold"),
                    text_color="#fff").grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        mode_menu = ctk.CTkOptionMenu(
            mode_row,
            values=["Mode 1 (Distance Based)", "Mode 2 (Range Detection)", "Mode 3 (Color Detection)"],
            command=self.on_trigger_mode_change,
            font=("Segoe UI", 12),
            text_color="#fff",
            fg_color="#2a2a2a",
            button_color=NEON,
            button_hover_color="#cc0030"
        )
        mode_menu.grid(row=0, column=1, sticky="w")
        
        # Set initial value
        current_mode = getattr(config, "trigger_mode", 1)
        if current_mode == 1:
            mode_menu.set("Mode 1 (Distance Based)")
        elif current_mode == 2:
            mode_menu.set("Mode 2 (Range Detection)")
        else:
            mode_menu.set("Mode 3 (Color Detection)")
        self.trigger_mode_menu = mode_menu

        # --- hotkey row
        ctk.CTkLabel(frame, text="Trigger Key:", font=("Segoe UI", 12, "bold"),
                    text_color="#fff").grid(row=3, column=0, sticky="w", padx=15, pady=(0, 8))
        btns = ctk.CTkFrame(frame, fg_color="transparent")
        btns.grid(row=3, column=1, sticky="w", padx=15, pady=(0, 8))
        for i, txt in enumerate(["Left", "Right", "Middle", "Side 4", "Side 5"]):
            ctk.CTkRadioButton(btns, text=txt, variable=self.trigger_btn_var, value=i,
                            command=self.update_trigger_button, text_color="#fff").pack(side="left", padx=8)

        # --- params
        params = ctk.CTkFrame(frame, fg_color="#2a2a2a", corner_radius=10)
        params.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 15))
        params.grid_columnconfigure((1,3,5,7), weight=1)

        # validators
        v_int   = self.register(lambda s: (s == "") or s.isdigit())
        def _is_float(s):
            if s == "" or s == ".": return True
            try: float(s); return True
            except: return False
        v_float = self.register(_is_float)
        
        def _is_mode2_range(s):
            if s == "" or s == ".": return True
            try: 
                val = float(s)
                return 0.5 <= val <= 1000.0
            except: return False
        v_mode2_range = self.register(_is_mode2_range)

        def _entry(parent, value, width=80, vcmd=None):
            e = ctk.CTkEntry(parent, width=width, justify="center",
                            font=("Segoe UI", 12, "bold"), text_color=NEON)
            e.insert(0, value)
            if vcmd is not None:
                # validate on keypress
                e.configure(validate="key", validatecommand=(vcmd, "%P"))
            return e

        self.tb_radius_label = ctk.CTkLabel(params, text="Radius(px)", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_radius_label.grid(row=0, column=0, padx=(10,6), pady=10, sticky="w")
        self.tb_radius_entry = _entry(params, str(getattr(config, "trigger_radius_px", 8)),
                                    vcmd=v_int);  self.tb_radius_entry.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(params, text="Delay(ms)", font=("Segoe UI", 12, "bold"),
                    text_color="#fff").grid(row=0, column=2, padx=(16,6), pady=10, sticky="w")
        self.tb_delay_entry  = _entry(params, str(getattr(config, "trigger_delay_ms", 30)),
                                    vcmd=v_int);  self.tb_delay_entry.grid(row=0, column=3, sticky="w")

        ctk.CTkLabel(params, text="Cooldown(ms)", font=("Segoe UI", 12, "bold"),
                    text_color="#fff").grid(row=0, column=4, padx=(16,6), pady=10, sticky="w")
        self.tb_cd_entry     = _entry(params, str(getattr(config, "trigger_cooldown_ms", 120)),
                                    vcmd=v_int); self.tb_cd_entry.grid(row=0, column=5, sticky="w")

        self.tb_conf_label = ctk.CTkLabel(params, text="Min conf", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_conf_label.grid(row=0, column=6, padx=(16,6), pady=10, sticky="w")
        self.tb_conf_entry   = _entry(params, f"{getattr(config, 'trigger_min_conf', 0.35):.2f}",
                                    vcmd=v_float); self.tb_conf_entry.grid(row=0, column=7, sticky="w")

        # Second row for Mode 2 specific settings
        # Mode 2 X/Y Range controls (only visible in Mode 2)
        self.tb_mode2_x_label = ctk.CTkLabel(params, text="Range X", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_mode2_x_label.grid(row=1, column=0, padx=(10,6), pady=10, sticky="w")
        self.tb_mode2_x_entry = _entry(params, f"{getattr(config, 'trigger_mode2_range_x', 50.0):.1f}",
                    vcmd=v_mode2_range);  self.tb_mode2_x_entry.grid(row=1, column=1, sticky="w")

        self.tb_mode2_y_label = ctk.CTkLabel(params, text="Range Y", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_mode2_y_label.grid(row=1, column=2, padx=(16,6), pady=10, sticky="w")
        self.tb_mode2_y_entry = _entry(params, f"{getattr(config, 'trigger_mode2_range_y', 50.0):.1f}",
                    vcmd=v_mode2_range);  self.tb_mode2_y_entry.grid(row=1, column=3, sticky="w")
        
        # Bind events for Mode 2 range entries
        self.tb_mode2_x_entry.bind("<Return>", self.on_mode2_x_entry_commit)
        self.tb_mode2_x_entry.bind("<FocusOut>", self.on_mode2_x_entry_commit)
        self.tb_mode2_y_entry.bind("<Return>", self.on_mode2_y_entry_commit)
        self.tb_mode2_y_entry.bind("<FocusOut>", self.on_mode2_y_entry_commit)
        
        # Third row for Mode 3 HSV settings (Color + Hue + Radius)
        # Color preview/picker for Mode 3
        self.tb_color_label = ctk.CTkLabel(params, text="Target Color", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_color_label.grid(row=2, column=0, padx=(10,6), pady=10, sticky="w")
        
        self.tb_color_preview = ctk.CTkButton(params, text="", width=60, height=20,
                                            fg_color=getattr(config, "trigger_hsv_color_hex", "#FFFF00"),
                                            hover_color=getattr(config, "trigger_hsv_color_hex", "#FFFF00"),
                                            command=self.pick_trigger_color)
        self.tb_color_preview.grid(row=2, column=1, sticky="w")

        # HSV H range
        self.tb_hsv_h_min_label = ctk.CTkLabel(params, text="H Min", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_hsv_h_min_label.grid(row=2, column=2, padx=(16,6), pady=10, sticky="w")
        self.tb_hsv_h_min_entry = _entry(params, str(getattr(config, "trigger_hsv_h_min", 0)),
                                    vcmd=v_int); self.tb_hsv_h_min_entry.grid(row=2, column=3, sticky="w")
        
        self.tb_hsv_h_max_label = ctk.CTkLabel(params, text="H Max", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_hsv_h_max_label.grid(row=2, column=4, padx=(16,6), pady=10, sticky="w")
        self.tb_hsv_h_max_entry = _entry(params, str(getattr(config, "trigger_hsv_h_max", 179)),
                                    vcmd=v_int); self.tb_hsv_h_max_entry.grid(row=2, column=5, sticky="w")

        # Color radius
        self.tb_color_radius_label = ctk.CTkLabel(params, text="Color Radius", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_color_radius_label.grid(row=2, column=6, padx=(16,6), pady=10, sticky="w")
        self.tb_color_radius_entry = _entry(params, str(getattr(config, "trigger_color_radius_px", 20)),
                                    vcmd=v_int); self.tb_color_radius_entry.grid(row=2, column=7, sticky="w")

        # Fourth row for HSV S & V range
        # HSV S range
        self.tb_hsv_s_min_label = ctk.CTkLabel(params, text="S Min", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_hsv_s_min_label.grid(row=3, column=0, padx=(10,6), pady=10, sticky="w")
        self.tb_hsv_s_min_entry = _entry(params, str(getattr(config, "trigger_hsv_s_min", 0)),
                                    vcmd=v_int); self.tb_hsv_s_min_entry.grid(row=3, column=1, sticky="w")
        
        self.tb_hsv_s_max_label = ctk.CTkLabel(params, text="S Max", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_hsv_s_max_label.grid(row=3, column=2, padx=(16,6), pady=10, sticky="w")
        self.tb_hsv_s_max_entry = _entry(params, str(getattr(config, "trigger_hsv_s_max", 255)),
                                    vcmd=v_int); self.tb_hsv_s_max_entry.grid(row=3, column=3, sticky="w")
        
        # HSV V range
        self.tb_hsv_v_min_label = ctk.CTkLabel(params, text="V Min", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_hsv_v_min_label.grid(row=3, column=4, padx=(16,6), pady=10, sticky="w")
        self.tb_hsv_v_min_entry = _entry(params, str(getattr(config, "trigger_hsv_v_min", 0)),
                                    vcmd=v_int); self.tb_hsv_v_min_entry.grid(row=3, column=5, sticky="w")
        
        self.tb_hsv_v_max_label = ctk.CTkLabel(params, text="V Max", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_hsv_v_max_label.grid(row=3, column=6, padx=(16,6), pady=10, sticky="w")
        self.tb_hsv_v_max_entry = _entry(params, str(getattr(config, "trigger_hsv_v_max", 255)),
                                    vcmd=v_int); self.tb_hsv_v_max_entry.grid(row=3, column=7, sticky="w")
                                    
        # Fifth row for Timings & Desc
        # Color delay
        self.tb_color_delay_label = ctk.CTkLabel(params, text="Color Delay", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_color_delay_label.grid(row=4, column=0, padx=(10,6), pady=10, sticky="w")
        self.tb_color_delay_entry = _entry(params, str(getattr(config, "trigger_color_delay_ms", 50)),
                                    vcmd=v_int); self.tb_color_delay_entry.grid(row=4, column=1, sticky="w")
        
        # Color cooldown
        self.tb_color_cooldown_label = ctk.CTkLabel(params, text="Color Cooldown", font=("Segoe UI", 12, "bold"),
                    text_color="#fff")
        self.tb_color_cooldown_label.grid(row=4, column=2, padx=(16,6), pady=10, sticky="w")
        self.tb_color_cooldown_entry = _entry(params, str(getattr(config, "trigger_color_cooldown_ms", 200)),
                                    vcmd=v_int); self.tb_color_cooldown_entry.grid(row=4, column=3, sticky="w")
        
        # Add description label for Mode 3
        ctk.CTkLabel(params, text="(Mode 3: HSV color detection)", font=("Segoe UI", 10),
                    text_color="#aaa").grid(row=4, column=4, columnspan=4, padx=(16,6), pady=10, sticky="w")

        def _commit_tb_numbers(event=None):
            try:
                # ints
                r  = int(self.tb_radius_entry.get() or 0)
                d  = int(self.tb_delay_entry.get() or 0)
                cd = int(self.tb_cd_entry.get() or 0)
                # float
                cf = float(self.tb_conf_entry.get() or 0.0)
                
                # Mode 3 HSV parameters
                h_min = int(self.tb_hsv_h_min_entry.get() or 0)
                h_max = int(self.tb_hsv_h_max_entry.get() or 179)
                s_min = int(self.tb_hsv_s_min_entry.get() or 0)
                s_max = int(self.tb_hsv_s_max_entry.get() or 255)
                v_min = int(self.tb_hsv_v_min_entry.get() or 0)
                v_max = int(self.tb_hsv_v_max_entry.get() or 255)
                cr = int(self.tb_color_radius_entry.get() or 20)
                c_delay = int(self.tb_color_delay_entry.get() or 50)
                c_cooldown = int(self.tb_color_cooldown_entry.get() or 200)

                # basic bounds
                r  = max(1, min(200, r))
                d  = max(0, min(1000, d))
                cd = max(0, min(2000, cd))
                cf = max(0.0, min(1.0, cf))
                
                # HSV bounds
                h_min = max(0, min(179, h_min))
                h_max = max(0, min(179, h_max))
                s_min = max(0, min(255, s_min))
                s_max = max(0, min(255, s_max))
                v_min = max(0, min(255, v_min))
                v_max = max(0, min(255, v_max))
                cr = max(1, min(100, cr))
                c_delay = max(0, min(1000, c_delay))
                c_cooldown = max(0, min(2000, c_cooldown))

                config.trigger_radius_px   = r
                config.trigger_delay_ms    = d
                config.trigger_cooldown_ms = cd
                config.trigger_min_conf    = cf
                
                # Mode 3 HSV settings
                config.trigger_hsv_h_min = h_min
                config.trigger_hsv_h_max = h_max
                config.trigger_hsv_s_min = s_min
                config.trigger_hsv_s_max = s_max
                config.trigger_hsv_v_min = v_min
                config.trigger_hsv_v_max = v_max
                config.trigger_color_radius_px = cr
                config.trigger_color_delay_ms = c_delay
                config.trigger_color_cooldown_ms = c_cooldown

                # normalize UI
                self.tb_radius_entry.delete(0, "end"); self.tb_radius_entry.insert(0, str(r))
                self.tb_delay_entry.delete(0, "end");  self.tb_delay_entry.insert(0, str(d))
                self.tb_cd_entry.delete(0, "end");     self.tb_cd_entry.insert(0, str(cd))
                self.tb_conf_entry.delete(0, "end");   self.tb_conf_entry.insert(0, f"{cf:.2f}")
                
                # Mode 3 HSV UI
                self.tb_hsv_h_min_entry.delete(0, "end"); self.tb_hsv_h_min_entry.insert(0, str(h_min))
                self.tb_hsv_h_max_entry.delete(0, "end"); self.tb_hsv_h_max_entry.insert(0, str(h_max))
                self.tb_hsv_s_min_entry.delete(0, "end"); self.tb_hsv_s_min_entry.insert(0, str(s_min))
                self.tb_hsv_s_max_entry.delete(0, "end"); self.tb_hsv_s_max_entry.insert(0, str(s_max))
                self.tb_hsv_v_min_entry.delete(0, "end"); self.tb_hsv_v_min_entry.insert(0, str(v_min))
                self.tb_hsv_v_max_entry.delete(0, "end"); self.tb_hsv_v_max_entry.insert(0, str(v_max))
                self.tb_color_radius_entry.delete(0, "end"); self.tb_color_radius_entry.insert(0, str(cr))
                self.tb_color_delay_entry.delete(0, "end"); self.tb_color_delay_entry.insert(0, str(c_delay))
                self.tb_color_cooldown_entry.delete(0, "end"); self.tb_color_cooldown_entry.insert(0, str(c_cooldown))

                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception as e:
                print(f"[WARN] Bad triggerbot param: {e}")
                # revert to config
                self.tb_radius_entry.delete(0,"end"); self.tb_radius_entry.insert(0, str(getattr(config, "trigger_radius_px", 8)))
                self.tb_delay_entry.delete(0,"end");  self.tb_delay_entry.insert(0, str(getattr(config, "trigger_delay_ms", 30)))
                self.tb_cd_entry.delete(0,"end");     self.tb_cd_entry.insert(0, str(getattr(config, "trigger_cooldown_ms", 120)))
                self.tb_conf_entry.delete(0,"end");   self.tb_conf_entry.insert(0, f"{getattr(config, 'trigger_min_conf', 0.35):.2f}")

        for w in (self.tb_radius_entry, self.tb_delay_entry, self.tb_cd_entry, self.tb_conf_entry,
                  self.tb_hsv_h_min_entry, self.tb_hsv_h_max_entry, self.tb_hsv_s_min_entry, self.tb_hsv_s_max_entry,
                  self.tb_hsv_v_min_entry, self.tb_hsv_v_max_entry, self.tb_color_radius_entry, self.tb_color_delay_entry,
                  self.tb_color_cooldown_entry):
            w.bind("<Return>", _commit_tb_numbers)
            w.bind("<FocusOut>", _commit_tb_numbers)

        # Initialize trigger head only checkbox visibility
        self._update_trigger_head_only_visibility()
        self._update_trigger_widgets_state()

    def build_detection_settings(self, parent, row):
        """Enhanced detection settings with better layout"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="🎯 Detection Settings", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        # Settings grid
        settings_frame = ctk.CTkFrame(frame, fg_color="transparent")
        settings_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        settings_frame.grid_columnconfigure(1, weight=1)

        
        # Resolution (row 1)
        ctk.CTkLabel(settings_frame, text="Model Image Size", font=("Segoe UI", 12, "bold"), text_color="#fff")\
            .grid(row=1, column=0, sticky="w", pady=5)

        self.imgsz_slider = ctk.CTkSlider(
            settings_frame, from_=128, to=1280, number_of_steps=36, command=self.update_imgsz
        )
        self.imgsz_slider.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.imgsz_slider.set(config.imgsz)

        # Manual entry (replaces the value label)
        self.imgsz_entry = ctk.CTkEntry(
            settings_frame, width=70, justify="center",
            font=("Segoe UI", 12, "bold"), text_color=NEON
        )
        self.imgsz_entry.grid(row=1, column=2, pady=5)
        self.imgsz_entry.insert(0, str(config.imgsz))

        # Commit on Enter or focus-out
        self.imgsz_entry.bind("<Return>", self.on_imgsz_entry_commit)
        self.imgsz_entry.bind("<FocusOut>", self.on_imgsz_entry_commit)
        
        # Max Detections
        ctk.CTkLabel(settings_frame, text="Max Detections", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=2, column=0, sticky="w", pady=5)
        self.max_detect_slider = ctk.CTkSlider(settings_frame, from_=1, to=100, number_of_steps=99, command=self.update_max_detect)
        self.max_detect_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.max_detect_label = ctk.CTkLabel(settings_frame, text=str(config.max_detect), font=("Segoe UI", 12, "bold"), text_color=NEON, width=50)
        self.max_detect_label.grid(row=2, column=2, pady=5)
        
        

    def build_aim_settings(self, parent, row):
        """Aim configuration settings"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="🎮 Aim Settings", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        settings_frame = ctk.CTkFrame(frame, fg_color="transparent")
        settings_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        settings_frame.grid_columnconfigure(1, weight=1)

        # Aim always on (toggle under Smoothing)
        self.always_on_switch = ctk.CTkSwitch(
            settings_frame,
            text="Aim always on",
            variable=self.always_on_var,
            command=self.on_always_on_toggle,
            text_color="#fff"
        )
        self.always_on_switch.grid(row=0, column=0, columnspan=3, sticky="w", pady=(8, 5))
        
        # FOV X Size
        ctk.CTkLabel(settings_frame, text="FOV X Size", font=("Segoe UI", 12, "bold"), text_color="#fff")\
            .grid(row=1, column=0, sticky="w", pady=5)

        self.fov_x_slider = ctk.CTkSlider(
            settings_frame, from_=20, to=500, command=self.update_fov_x, number_of_steps=180
        )
        self.fov_x_slider.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=5)

        self.fov_x_entry = ctk.CTkEntry(
            settings_frame, width=70, justify="center",
            font=("Segoe UI", 12, "bold"), text_color=NEON
        )
        self.fov_x_entry.grid(row=1, column=2, pady=5)
        self.fov_x_entry.insert(0, str(config.fov_x_size))
        self.fov_x_entry.bind("<Return>", self.on_fov_x_entry_commit)
        self.fov_x_entry.bind("<FocusOut>", self.on_fov_x_entry_commit)

        # FOV Y Size
        ctk.CTkLabel(settings_frame, text="FOV Y Size", font=("Segoe UI", 12, "bold"), text_color="#fff")\
            .grid(row=2, column=0, sticky="w", pady=5)

        self.fov_y_slider = ctk.CTkSlider(
            settings_frame, from_=20, to=500, command=self.update_fov_y, number_of_steps=180
        )
        self.fov_y_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=5)

        self.fov_y_entry = ctk.CTkEntry(
            settings_frame, width=70, justify="center",
            font=("Segoe UI", 12, "bold"), text_color=NEON
        )
        self.fov_y_entry.grid(row=2, column=2, pady=5)
        self.fov_y_entry.insert(0, str(config.fov_y_size))
        self.fov_y_entry.bind("<Return>", self.on_fov_y_entry_commit)
        self.fov_y_entry.bind("<FocusOut>", self.on_fov_y_entry_commit)

        # guard to avoid feedback loops
        self._updating_fov_x = False
        self._updating_fov_y = False

        # Player Y Offset
        ctk.CTkLabel(settings_frame, text="Y Offset", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=3, column=0, sticky="w", pady=5)
        self.offset_slider = ctk.CTkSlider(settings_frame, from_=0, to=20, command=self.update_offset, number_of_steps=20)
        self.offset_slider.grid(row=3, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.offset_value = ctk.CTkLabel(settings_frame, text=str(config.player_y_offset), font=("Segoe UI", 12, "bold"), text_color=NEON, width=50)
        self.offset_value.grid(row=3, column=2, pady=5)

        # X Offset for X-Center Targeting
        ctk.CTkLabel(settings_frame, text="X Offset", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=4, column=0, sticky="w", pady=5)
        self.x_offset_slider = ctk.CTkSlider(settings_frame, from_=-50, to=50, command=self.update_x_offset, number_of_steps=100)
        self.x_offset_slider.grid(row=4, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.x_offset_value = ctk.CTkLabel(settings_frame, text=str(getattr(config, 'x_center_offset_px', 0)), font=("Segoe UI", 12, "bold"), text_color=NEON, width=50)
        self.x_offset_value.grid(row=4, column=2, pady=5)
         
        # Sensitivity
        ctk.CTkLabel(settings_frame, text="Smoothing", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=5, column=0, sticky="w", pady=5)
        self.in_game_sens_slider = ctk.CTkSlider(settings_frame, from_=0.1, to=20, number_of_steps=199, command=self.update_in_game_sens)
        self.in_game_sens_slider.grid(row=5, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.in_game_sens_value = ctk.CTkLabel(settings_frame, text=f"{config.in_game_sens:.2f}", font=("Segoe UI", 12, "bold"), text_color=NEON, width=50)
        self.in_game_sens_value.grid(row=5, column=2, pady=5)

        
        # Height Targeting Section
        height_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=8)
        height_frame.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        height_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(height_frame, text="🎯 Height Targeting", font=("Segoe UI", 12, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(8, 5), padx=10, sticky="w")
        
        # Height Targeting Enable Toggle
        self.height_targeting_var = ctk.BooleanVar(value=config.height_targeting_enabled)
        self.height_targeting_switch = ctk.CTkSwitch(
            height_frame,
            text="Enable Height Targeting",
            variable=self.height_targeting_var,
            command=self.on_height_targeting_toggle,
            text_color="#fff"
        )
        self.height_targeting_switch.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 2))
        
        # Target Height
        ctk.CTkLabel(height_frame, text="Target Height", font=("Segoe UI", 11, "bold"), text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.target_height_slider = ctk.CTkSlider(height_frame, from_=0.100, to=1.000, number_of_steps=900, command=self.update_target_height)
        self.target_height_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.target_height_entry = ctk.CTkEntry(height_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.target_height_entry.grid(row=2, column=2, padx=10, pady=2)
        self.target_height_entry.insert(0, f"{config.target_height:.3f}")
        self.target_height_entry.bind("<Return>", self.on_target_height_entry_commit)
        self.target_height_entry.bind("<FocusOut>", self.on_target_height_entry_commit)
        
        # Deadzone Enable Toggle
        self.height_deadzone_var = ctk.BooleanVar(value=config.height_deadzone_enabled)
        self.height_deadzone_switch = ctk.CTkSwitch(
            height_frame,
            text="Height Deadzone",
            variable=self.height_deadzone_var,
            command=self.on_height_deadzone_toggle,
            text_color="#fff"
        )
        self.height_deadzone_switch.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 2))
        
        # Deadzone Range
        ctk.CTkLabel(height_frame, text="Deadzone Min", font=("Segoe UI", 11), text_color="#fff").grid(row=4, column=0, sticky="w", padx=10, pady=2)
        # Constrain by target class Y-axis lowest bound (head ratio upper bound is 0.235)
        self.deadzone_min_slider = ctk.CTkSlider(height_frame, from_=0.000, to=0.235, number_of_steps=235, command=self.update_deadzone_min)
        self.deadzone_min_slider.grid(row=4, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.deadzone_min_entry = ctk.CTkEntry(height_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.deadzone_min_entry.grid(row=4, column=2, padx=10, pady=2)
        self.deadzone_min_entry.insert(0, f"{min(config.height_deadzone_min, 0.235):.3f}")
        self.deadzone_min_entry.bind("<Return>", self.on_deadzone_min_entry_commit)
        self.deadzone_min_entry.bind("<FocusOut>", self.on_deadzone_min_entry_commit)
        
        ctk.CTkLabel(height_frame, text="Deadzone Max", font=("Segoe UI", 11), text_color="#fff").grid(row=5, column=0, sticky="w", padx=10, pady=2)
        # Constrain by target class Y-axis highest bound (head ratio cap 0.235)
        self.deadzone_max_slider = ctk.CTkSlider(height_frame, from_=0.000, to=0.235, number_of_steps=235, command=self.update_deadzone_max)
        self.deadzone_max_slider.grid(row=5, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.deadzone_max_entry = ctk.CTkEntry(height_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.deadzone_max_entry.grid(row=5, column=2, padx=10, pady=2)
        self.deadzone_max_entry.insert(0, f"{config.height_deadzone_max:.3f}")
        self.deadzone_max_entry.bind("<Return>", self.on_deadzone_max_entry_commit)
        self.deadzone_max_entry.bind("<FocusOut>", self.on_deadzone_max_entry_commit)
        
        # Deadzone Tolerance (Full Entry)
        ctk.CTkLabel(height_frame, text="Entry Tolerance", font=("Segoe UI", 11), text_color="#fff").grid(row=6, column=0, sticky="w", padx=10, pady=2)
        self.deadzone_tolerance_slider = ctk.CTkSlider(height_frame, from_=0.000, to=15.000, number_of_steps=1500, command=self.update_deadzone_tolerance)
        self.deadzone_tolerance_slider.grid(row=6, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.deadzone_tolerance_entry = ctk.CTkEntry(height_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.deadzone_tolerance_entry.grid(row=6, column=2, padx=10, pady=(2, 8))
        self.deadzone_tolerance_entry.insert(0, f"{config.height_deadzone_tolerance:.3f}")
        self.deadzone_tolerance_entry.bind("<Return>", self.on_deadzone_tolerance_entry_commit)
        self.deadzone_tolerance_entry.bind("<FocusOut>", self.on_deadzone_tolerance_entry_commit)
        
        # Deadzone description
        ctk.CTkLabel(height_frame, text="Deadzone: Max=upwards from Target Height, Min=downwards from Target Height (Min can be > Max)", 
                    font=("Segoe UI", 9), text_color="#aaa").grid(row=7, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 8))
        
        # X-Center Targeting Section
        x_center_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=8)
        x_center_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        x_center_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(x_center_frame, text="🎯 X-Center Targeting", font=("Segoe UI", 12, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(8, 5), padx=10, sticky="w")
        
        # X-Center Targeting Enable Toggle
        self.x_center_targeting_var = ctk.BooleanVar(value=config.x_center_targeting_enabled)
        self.x_center_targeting_switch = ctk.CTkSwitch(
            x_center_frame,
            text="X-Center Targeting",
            variable=self.x_center_targeting_var,
            command=self.on_x_center_targeting_toggle,
            text_color="#fff"
        )
        self.x_center_targeting_switch.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 2))
        
        # X-Center Tolerance Percentage
        ctk.CTkLabel(x_center_frame, text="Tolerance %", font=("Segoe UI", 11), text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.x_center_tolerance_slider = ctk.CTkSlider(x_center_frame, from_=0.0, to=50.0, number_of_steps=500, command=self.update_x_center_tolerance)
        self.x_center_tolerance_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.x_center_tolerance_entry = ctk.CTkEntry(x_center_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.x_center_tolerance_entry.grid(row=2, column=2, padx=10, pady=(2, 8))
        self.x_center_tolerance_entry.insert(0, f"{config.x_center_tolerance_percent:.1f}")
        self.x_center_tolerance_entry.bind("<Return>", self.on_x_center_tolerance_entry_commit)
        self.x_center_tolerance_entry.bind("<FocusOut>", self.on_x_center_tolerance_entry_commit)
        
        # Mouse Movement Multiplier Section
        mouse_multiplier_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=8)
        mouse_multiplier_frame.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        mouse_multiplier_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(mouse_multiplier_frame, text="🖱️ Mouse Movement", font=("Segoe UI", 12, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(8, 5), padx=10, sticky="w")
        
        # X-Axis Movement Multiplier
        ctk.CTkLabel(mouse_multiplier_frame, text="X-Axis Speed", font=("Segoe UI", 11), text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.mouse_multiplier_x_slider = ctk.CTkSlider(mouse_multiplier_frame, from_=0.0, to=5.0, number_of_steps=500, command=self.update_mouse_multiplier_x)
        self.mouse_multiplier_x_slider.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.mouse_multiplier_x_entry = ctk.CTkEntry(mouse_multiplier_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.mouse_multiplier_x_entry.grid(row=1, column=2, padx=10, pady=2)
        self.mouse_multiplier_x_entry.insert(0, f"{getattr(config, 'mouse_movement_multiplier_x', 1.0):.2f}")
        self.mouse_multiplier_x_entry.bind("<Return>", self.on_mouse_multiplier_x_entry_commit)
        self.mouse_multiplier_x_entry.bind("<FocusOut>", self.on_mouse_multiplier_x_entry_commit)
        
        # Y-Axis Movement Multiplier
        ctk.CTkLabel(mouse_multiplier_frame, text="Y-Axis Speed", font=("Segoe UI", 11), text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.mouse_multiplier_y_slider = ctk.CTkSlider(mouse_multiplier_frame, from_=0.0, to=5.0, number_of_steps=500, command=self.update_mouse_multiplier_y)
        self.mouse_multiplier_y_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.mouse_multiplier_y_entry = ctk.CTkEntry(mouse_multiplier_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.mouse_multiplier_y_entry.grid(row=2, column=2, padx=10, pady=2)
        self.mouse_multiplier_y_entry.insert(0, f"{getattr(config, 'mouse_movement_multiplier_y', 1.0):.2f}")
        self.mouse_multiplier_y_entry.bind("<Return>", self.on_mouse_multiplier_y_entry_commit)
        self.mouse_multiplier_y_entry.bind("<FocusOut>", self.on_mouse_multiplier_y_entry_commit)
        
        # X-Axis Movement Toggle
        self.mouse_movement_enabled_x_var = ctk.BooleanVar(value=getattr(config, 'mouse_movement_enabled_x', True))
        self.mouse_movement_enabled_x_switch = ctk.CTkSwitch(
            mouse_multiplier_frame, text="Enable X-Axis Movement", variable=self.mouse_movement_enabled_x_var,
            command=self.on_mouse_movement_enabled_x_toggle, text_color="#fff", font=("Segoe UI", 11)
        )
        self.mouse_movement_enabled_x_switch.grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(5, 2))
        
        # Y-Axis Movement Toggle
        self.mouse_movement_enabled_y_var = ctk.BooleanVar(value=getattr(config, 'mouse_movement_enabled_y', True))
        self.mouse_movement_enabled_y_switch = ctk.CTkSwitch(
            mouse_multiplier_frame, text="Enable Y-Axis Movement", variable=self.mouse_movement_enabled_y_var,
            command=self.on_mouse_movement_enabled_y_toggle, text_color="#fff", font=("Segoe UI", 11)
        )
        self.mouse_movement_enabled_y_switch.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 8))
        
        # Mouse Button Selection
        def _apply_x_offset_from_slider(event=None):
            try:
                val = int(round(float(self.x_offset_slider.get())))
                config.x_center_offset_px = val
                self.x_offset_value.configure(text=str(val))
                if hasattr(config, "save_async") and callable(config.save_async):
                    config.save_async()
                elif hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                pass

        aim_key_label = ctk.CTkLabel(settings_frame, text="Aim Key:", font=("Segoe UI", 12, "bold"), text_color="#fff")
        aim_key_label.grid(row=9, column=0, sticky="nw", pady=(10, 5))
        # Click label to apply current X Offset slider value to config (Aimbot X + x_offset)
        try:
            aim_key_label.bind("<Button-1>", _apply_x_offset_from_slider)
        except Exception:
            pass

        self.btn_var = ctk.IntVar(value=config.selected_mouse_button)
        btn_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        btn_frame.grid(row=9, column=1, columnspan=2, sticky="ew", pady=(10, 5))
        
        for i, txt in enumerate(["Left", "Right", "Middle", "Side 4", "Side 5"]):
            ctk.CTkRadioButton(btn_frame, text=txt, variable=self.btn_var, value=i, command=self.update_mouse_btn, text_color="#fff").pack(side="left", padx=8)

    def build_rcs_settings(self, parent, row):
        """Build RCS (Recoil Control System) settings section"""
        from recoil_loader import get_available_games, get_available_weapons
        
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a", corner_radius=8)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        # --- Header Section: Title & Main Enable Switch ---
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        header_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(header_frame, text="🎯 RCS (Recoil Control)", 
                    font=("Segoe UI", 16, "bold"), 
                    text_color="#00e676").grid(row=0, column=0, sticky="w")
        
        self.rcs_enabled_switch = ctk.CTkSwitch(
            header_frame,
            text="Enable RCS",
            variable=self.rcs_enabled_var,
            command=self.on_rcs_enabled_toggle,
            text_color="#fff"
        )
        self.rcs_enabled_switch.grid(row=0, column=1, sticky="e")
        
        # --- Options Section: ADS Only & Disable Y-Axis ---
        options_frame = ctk.CTkFrame(frame, fg_color="transparent")
        options_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 5))
        options_frame.grid_columnconfigure(0, weight=1)
        options_frame.grid_columnconfigure(1, weight=1)

        # ADS Only checkbox
        self.rcs_ads_only_checkbox = ctk.CTkCheckBox(
            options_frame,
            text="ADS Only",
            variable=self.rcs_ads_only_var,
            command=self.on_rcs_ads_only_toggle,
            text_color="#fff",
            font=("Segoe UI", 11)
        )
        self.rcs_ads_only_checkbox.grid(row=0, column=0, sticky="w", padx=(0, 5))
        
        # Disable Y-axis checkbox
        self.rcs_disable_y_axis_checkbox = ctk.CTkCheckBox(
            options_frame,
            text="Disable Aimbot Y",
            variable=self.rcs_disable_y_axis_var,
            command=self.on_rcs_disable_y_axis_toggle,
            text_color="#fff",
            font=("Segoe UI", 11)
        )
        self.rcs_disable_y_axis_checkbox.grid(row=0, column=1, sticky="w", padx=(5, 0))
        
        # --- Mode Selection Section ---
        mode_frame = ctk.CTkFrame(frame, fg_color="#2a2a2a", corner_radius=8)
        mode_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 5))
        mode_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(mode_frame, text="RCS Mode:", 
                    font=("Segoe UI", 12, "bold"), 
                    text_color="#fff").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        
        self.rcs_mode_var = ctk.StringVar(value=getattr(config, "rcs_mode", "simple"))
        mode_btn_frame = ctk.CTkFrame(mode_frame, fg_color="transparent")
        mode_btn_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        
        ctk.CTkRadioButton(mode_btn_frame, text="Simple", variable=self.rcs_mode_var, 
                          value="simple", command=self.on_rcs_mode_change, 
                          text_color="#fff").pack(side="left", padx=8)
        ctk.CTkRadioButton(mode_btn_frame, text="Game", variable=self.rcs_mode_var, 
                          value="game", command=self.on_rcs_mode_change, 
                          text_color="#fff").pack(side="left", padx=8)
        
        # --- Game Mode Settings ---
        self.game_frame = ctk.CTkFrame(frame, fg_color="#2a2a2a", corner_radius=8)
        self.game_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=(5, 5))
        self.game_frame.grid_columnconfigure(1, weight=1)
        
        # Game Selection
        ctk.CTkLabel(self.game_frame, text="Game:", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        
        games = get_available_games()
        self.rcs_game_var = ctk.StringVar(value=getattr(config, "rcs_game", games[0] if games else ""))
        self.rcs_game_menu = ctk.CTkOptionMenu(
            self.game_frame, 
            values=games if games else ["No games available"],
            variable=self.rcs_game_var,
            command=self.on_rcs_game_change
        )
        self.rcs_game_menu.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        
        # Weapon Selection
        ctk.CTkLabel(self.game_frame, text="Weapon:", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        
        selected_game = self.rcs_game_var.get()
        weapons = get_available_weapons(selected_game) if selected_game else []
        # Validate weapon exists in selected game
        saved_weapon = getattr(config, "rcs_weapon", "")
        if saved_weapon and weapons and saved_weapon in weapons:
            initial_weapon = saved_weapon
        else:
            initial_weapon = weapons[0] if weapons else ""
            # Update config if weapon doesn't exist in current game
            if saved_weapon and weapons and saved_weapon not in weapons:
                config.rcs_weapon = initial_weapon
        self.rcs_weapon_var = ctk.StringVar(value=initial_weapon)
        self.rcs_weapon_menu = ctk.CTkOptionMenu(
            self.game_frame, 
            values=weapons if weapons else ["No weapons available"],
            variable=self.rcs_weapon_var,
            command=self.on_rcs_weapon_change
        )
        self.rcs_weapon_menu.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        # Multipliers Frame
        multipliers_frame = ctk.CTkFrame(self.game_frame, fg_color="#1a1a1a", corner_radius=8)
        multipliers_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 10))
        multipliers_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(multipliers_frame, text="Multipliers", 
                    font=("Segoe UI", 12, "bold"), 
                    text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")
        
        # X-Axis Movement Multiplier
        ctk.CTkLabel(multipliers_frame, text="X Movement:", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.rcs_x_multiplier_slider = ctk.CTkSlider(multipliers_frame, from_=0.1, to=5.0, 
                                                     number_of_steps=490, command=self.update_rcs_x_multiplier)
        self.rcs_x_multiplier_slider.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.rcs_x_multiplier_entry = ctk.CTkEntry(multipliers_frame, width=60, justify="center", 
                                                   font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_x_multiplier_entry.grid(row=1, column=2, padx=10, pady=2)
        self.rcs_x_multiplier_entry.insert(0, f"{getattr(config, 'rcs_x_multiplier', 1.0):.2f}")
        self.rcs_x_multiplier_entry.bind("<Return>", self.on_rcs_x_multiplier_entry_commit)
        self.rcs_x_multiplier_entry.bind("<FocusOut>", self.on_rcs_x_multiplier_entry_commit)
        
        # Y-Axis Movement Multiplier
        ctk.CTkLabel(multipliers_frame, text="Y Movement:", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.rcs_y_multiplier_slider = ctk.CTkSlider(multipliers_frame, from_=0.1, to=5.0, 
                                                     number_of_steps=490, command=self.update_rcs_y_multiplier)
        self.rcs_y_multiplier_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.rcs_y_multiplier_entry = ctk.CTkEntry(multipliers_frame, width=60, justify="center", 
                                                   font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_y_multiplier_entry.grid(row=2, column=2, padx=10, pady=2)
        self.rcs_y_multiplier_entry.insert(0, f"{getattr(config, 'rcs_y_multiplier', 1.0):.2f}")
        self.rcs_y_multiplier_entry.bind("<Return>", self.on_rcs_y_multiplier_entry_commit)
        self.rcs_y_multiplier_entry.bind("<FocusOut>", self.on_rcs_y_multiplier_entry_commit)
        
        # X-Axis Time Multiplier
        ctk.CTkLabel(multipliers_frame, text="X Time:", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=3, column=0, sticky="w", padx=10, pady=2)
        self.rcs_x_time_multiplier_slider = ctk.CTkSlider(multipliers_frame, from_=0.1, to=5.0, 
                                                           number_of_steps=490, command=self.update_rcs_x_time_multiplier)
        self.rcs_x_time_multiplier_slider.grid(row=3, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.rcs_x_time_multiplier_entry = ctk.CTkEntry(multipliers_frame, width=60, justify="center", 
                                                        font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_x_time_multiplier_entry.grid(row=3, column=2, padx=10, pady=2)
        self.rcs_x_time_multiplier_entry.insert(0, f"{getattr(config, 'rcs_x_time_multiplier', 1.0):.2f}")
        self.rcs_x_time_multiplier_entry.bind("<Return>", self.on_rcs_x_time_multiplier_entry_commit)
        self.rcs_x_time_multiplier_entry.bind("<FocusOut>", self.on_rcs_x_time_multiplier_entry_commit)
        
        # Y-Axis Time Multiplier
        ctk.CTkLabel(multipliers_frame, text="Y Time:", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=4, column=0, sticky="w", padx=10, pady=(2, 10))
        self.rcs_y_time_multiplier_slider = ctk.CTkSlider(multipliers_frame, from_=0.1, to=5.0, 
                                                          number_of_steps=490, command=self.update_rcs_y_time_multiplier)
        self.rcs_y_time_multiplier_slider.grid(row=4, column=1, sticky="ew", padx=(10, 5), pady=(2, 10))
        self.rcs_y_time_multiplier_entry = ctk.CTkEntry(multipliers_frame, width=60, justify="center", 
                                                        font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_y_time_multiplier_entry.grid(row=4, column=2, padx=10, pady=(2, 10))
        self.rcs_y_time_multiplier_entry.insert(0, f"{getattr(config, 'rcs_y_time_multiplier', 1.0):.2f}")
        self.rcs_y_time_multiplier_entry.bind("<Return>", self.on_rcs_y_time_multiplier_entry_commit)
        self.rcs_y_time_multiplier_entry.bind("<FocusOut>", self.on_rcs_y_time_multiplier_entry_commit)
        
        # RCS Key selection for Game Mode
        rcs_key_label_game = ctk.CTkLabel(self.game_frame, text="RCS Key:", font=("Segoe UI", 12, "bold"), text_color="#fff")
        rcs_key_label_game.grid(row=3, column=0, sticky="nw", pady=(10, 10), padx=10)
        
        rcs_btn_frame_game = ctk.CTkFrame(self.game_frame, fg_color="transparent")
        rcs_btn_frame_game.grid(row=3, column=1, sticky="ew", pady=(10, 10), padx=10)
        
        for i, txt in enumerate(["Left", "Right", "Middle", "Side 4", "Side 5"]):
            ctk.CTkRadioButton(rcs_btn_frame_game, text=txt, variable=self.rcs_btn_var, value=i, command=self.update_rcs_btn, text_color="#fff").pack(side="left", padx=8)
        
        # --- Simple Mode Settings ---
        self.simple_frame = ctk.CTkFrame(frame, fg_color="#2a2a2a", corner_radius=8)
        self.simple_frame.grid(row=4, column=0, sticky="ew", padx=15, pady=(5, 15))
        self.simple_frame.grid_columnconfigure(1, weight=1)
        
        # X-Axis Recoil Compensation
        ctk.CTkLabel(self.simple_frame, text="🔽 X-Axis Compensation", 
                    font=("Segoe UI", 12, "bold"), 
                    text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")
        
        # X-Axis Strength
        ctk.CTkLabel(self.simple_frame, text="Strength", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.rcs_x_strength_slider = ctk.CTkSlider(self.simple_frame, from_=0.1, to=5.0, 
                                                  number_of_steps=490, command=self.update_rcs_x_strength)
        self.rcs_x_strength_slider.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.rcs_x_strength_entry = ctk.CTkEntry(self.simple_frame, width=60, justify="center", 
                                                font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_x_strength_entry.grid(row=1, column=2, padx=10, pady=2)
        self.rcs_x_strength_entry.insert(0, f"{config.rcs_x_strength:.2f}")
        self.rcs_x_strength_entry.bind("<Return>", self.on_rcs_x_strength_entry_commit)
        self.rcs_x_strength_entry.bind("<FocusOut>", self.on_rcs_x_strength_entry_commit)
        
        # X-Axis Delay
        ctk.CTkLabel(self.simple_frame, text="Delay (ms)", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.rcs_x_delay_slider = ctk.CTkSlider(self.simple_frame, from_=1, to=100, 
                                               number_of_steps=99, command=self.update_rcs_x_delay)
        self.rcs_x_delay_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.rcs_x_delay_entry = ctk.CTkEntry(self.simple_frame, width=60, justify="center", 
                                             font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_x_delay_entry.grid(row=2, column=2, padx=10, pady=2)
        self.rcs_x_delay_entry.insert(0, f"{int(config.rcs_x_delay * 1000)}")
        self.rcs_x_delay_entry.bind("<Return>", self.on_rcs_x_delay_entry_commit)
        self.rcs_x_delay_entry.bind("<FocusOut>", self.on_rcs_x_delay_entry_commit)
        
        # Y-Axis Random Jitter Section
        ctk.CTkLabel(self.simple_frame, text="↔️ Y-Axis Random Jitter", 
                    font=("Segoe UI", 12, "bold"), 
                    text_color="#00e676").grid(row=3, column=0, columnspan=3, pady=(15, 5), padx=10, sticky="w")
        
        # Y-Axis Random Enable
        self.rcs_y_random_switch = ctk.CTkSwitch(
            self.simple_frame,
            text="Enable Y-Axis Random Jitter",
            variable=self.rcs_y_random_enabled_var,
            command=self.on_rcs_y_random_toggle,
            text_color="#fff"
        )
        self.rcs_y_random_switch.grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 5))
        
        # Y-Axis Random Strength
        ctk.CTkLabel(self.simple_frame, text="Jitter Strength", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=5, column=0, sticky="w", padx=10, pady=2)
        self.rcs_y_strength_slider = ctk.CTkSlider(self.simple_frame, from_=0.1, to=3.0, 
                                                  number_of_steps=290, command=self.update_rcs_y_strength)
        self.rcs_y_strength_slider.grid(row=5, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.rcs_y_strength_entry = ctk.CTkEntry(self.simple_frame, width=60, justify="center", 
                                                font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_y_strength_entry.grid(row=5, column=2, padx=10, pady=2)
        self.rcs_y_strength_entry.insert(0, f"{config.rcs_y_random_strength:.2f}")
        self.rcs_y_strength_entry.bind("<Return>", self.on_rcs_y_strength_entry_commit)
        self.rcs_y_strength_entry.bind("<FocusOut>", self.on_rcs_y_strength_entry_commit)
        
        # Y-Axis Random Delay
        ctk.CTkLabel(self.simple_frame, text="Jitter Delay (ms)", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=6, column=0, sticky="w", padx=10, pady=(2, 10))
        self.rcs_y_delay_slider = ctk.CTkSlider(self.simple_frame, from_=1, to=100, 
                                               number_of_steps=99, command=self.update_rcs_y_delay)
        self.rcs_y_delay_slider.grid(row=6, column=1, sticky="ew", padx=(10, 5), pady=(2, 10))
        self.rcs_y_delay_entry = ctk.CTkEntry(self.simple_frame, width=60, justify="center", 
                                             font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_y_delay_entry.grid(row=6, column=2, padx=10, pady=(2, 10))
        self.rcs_y_delay_entry.insert(0, f"{int(config.rcs_y_random_delay * 1000)}")
        self.rcs_y_delay_entry.bind("<Return>", self.on_rcs_y_delay_entry_commit)
        self.rcs_y_delay_entry.bind("<FocusOut>", self.on_rcs_y_delay_entry_commit)
        
        # RCS Key selection
        rcs_key_label = ctk.CTkLabel(self.simple_frame, text="RCS Key:", font=("Segoe UI", 12, "bold"), text_color="#fff")
        rcs_key_label.grid(row=7, column=0, sticky="nw", pady=(10, 5), padx=10)
        
        rcs_btn_frame = ctk.CTkFrame(self.simple_frame, fg_color="transparent")
        rcs_btn_frame.grid(row=7, column=1, columnspan=2, sticky="ew", pady=(10, 5), padx=10)
        
        for i, txt in enumerate(["Left", "Right", "Middle", "Side 4", "Side 5"]):
            ctk.CTkRadioButton(rcs_btn_frame, text=txt, variable=self.rcs_btn_var, value=i, command=self.update_rcs_btn, text_color="#fff").pack(side="left", padx=8)
        
        # Initialize slider values
        self.rcs_x_strength_slider.set(config.rcs_x_strength)
        self.rcs_x_delay_slider.set(config.rcs_x_delay * 1000)  # Convert to ms
        self.rcs_y_strength_slider.set(config.rcs_y_random_strength)
        self.rcs_y_delay_slider.set(config.rcs_y_random_delay * 1000)  # Convert to ms
        self.rcs_x_multiplier_slider.set(getattr(config, 'rcs_x_multiplier', 1.0))
        self.rcs_y_multiplier_slider.set(getattr(config, 'rcs_y_multiplier', 1.0))
        self.rcs_x_time_multiplier_slider.set(getattr(config, 'rcs_x_time_multiplier', 1.0))
        self.rcs_y_time_multiplier_slider.set(getattr(config, 'rcs_y_time_multiplier', 1.0))
        
        # Update visibility based on mode
        self.update_rcs_mode_visibility()

    def build_aimbot_mode(self, parent, row):
        """Aimbot mode selection"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frame, text="⚡ Aimbot Mode", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        self.mode_var = ctk.StringVar(value=config.mode)
        mode_frame = ctk.CTkFrame(frame, fg_color="transparent")
        mode_frame.grid(row=1, column=0, padx=15, pady=(0, 15))
        
        for name in ["normal", "bezier", "silent", "smooth", "ncaf"]:
            ctk.CTkRadioButton(
                mode_frame, 
                text=name.title(), 
                variable=self.mode_var, 
                value=name, 
                command=self.update_mode, 
                text_color="#fff",
                font=("Segoe UI", 12, "bold")
            ).pack(side="left", padx=15)

    def build_model_settings(self, parent, row):
        """AI Model configuration"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="🤖 AI Model", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        model_controls = ctk.CTkFrame(frame, fg_color="transparent")
        model_controls.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        model_controls.grid_columnconfigure(0, weight=1)
        
        self.model_menu = ctk.CTkOptionMenu(model_controls, values=self.get_model_list(), command=self.select_model)
        self.model_menu.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        neon_button(model_controls, text="Reload", command=self.reload_model, width=80).grid(row=0, column=1)
        
        # Class display
        ctk.CTkLabel(frame, text="Available Classes:", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=2, column=0, sticky="w", padx=15, pady=(10, 5))
        
        self.class_listbox = ctk.CTkTextbox(frame, height=80, fg_color="#2a2a2a", text_color="#fff", font=("Segoe UI", 11))
        self.class_listbox.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 15))

    def build_class_selection(self, parent, row):
        """Target class selection"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(frame, text="🎯 Target Classes", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=2, pady=(15, 10), padx=15, sticky="w")
        
        ctk.CTkLabel(frame, text="🧩 Player Classes", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=1, column=0, sticky="nw", padx=15, pady=5)
        # Scrollable list of checkboxes + per-class confidence controls (restyled)
        self.player_class_list_frame = ctk.CTkScrollableFrame(
            frame,
            fg_color="#2a2a2a",
            corner_radius=8,
            border_width=1,
            border_color=NEON,
            height=240
        )
        self.player_class_list_frame.grid(row=1, column=1, sticky="nsew", padx=15, pady=6)
        self.player_class_vars = {}
        # Store widgets for per-class confidence
        self._class_conf_widgets = {}
        self._build_player_class_checklist()
        
        ctk.CTkLabel(frame, text="Head Class:", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=2, column=0, sticky="w", padx=15, pady=5)
        self.head_class_var = ctk.StringVar(value=config.custom_head_label or "None")
        self.head_class_menu = ctk.CTkOptionMenu(frame, values=["None"] + self.get_available_classes(), variable=self.head_class_var, command=self.set_head_class)
        self.head_class_menu.grid(row=2, column=1, sticky="ew", padx=15, pady=(5, 15))

    def build_profile_controls(self, parent, row):
        """Enhanced profile management with create, rename, and selection"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="💾 Profile Management", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        # Profile selection section
        selection_frame = ctk.CTkFrame(frame, fg_color="transparent")
        selection_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        selection_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(selection_frame, text="Current Profile:", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=0, column=0, sticky="w", pady=5)
        
        # Profile dropdown
        self.profile_var = ctk.StringVar(value="config_profile")
        self.profile_menu = ctk.CTkOptionMenu(
            selection_frame, 
            values=self.get_profile_list(), 
            variable=self.profile_var,
            command=self.on_profile_select,
            width=200
        )
        self.profile_menu.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Profile management buttons
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=15, pady=(0, 10))
        
        # First row of buttons
        btn_row1 = ctk.CTkFrame(btn_frame, fg_color="transparent")
        btn_row1.pack(fill="x", pady=(0, 5))
        
        neon_button(btn_row1, text="Create New", command=self.create_profile_dialog, width=100).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_row1, text="Rename", command=self.rename_profile_dialog, width=100, fg_color="#333").pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_row1, text="Delete", command=self.delete_profile_dialog, width=100, fg_color="#b71c1c").pack(side="left", padx=(0, 5))
        
        # Second row of buttons
        btn_row2 = ctk.CTkFrame(btn_frame, fg_color="transparent")
        btn_row2.pack(fill="x", pady=(0, 5))
        
        neon_button(btn_row2, text="Save Current", command=self.save_current_profile, width=100).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_row2, text="Load Selected", command=self.load_selected_profile, width=100, fg_color="#333").pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_row2, text="Reset Defaults", command=self.reset_defaults, width=100, fg_color="#333").pack(side="left")

    def build_main_controls(self, parent, row):
        """Main aimbot controls"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frame, text="🚀 Aimbot Controls", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=1, column=0, padx=15, pady=(0, 15))
        
        neon_button(btn_frame, text="🎯 START AIMBOT", command=self.start_aimbot, width=150, height=45, font=("Segoe UI", 14, "bold")).pack(side="left", padx=(0, 15))
        ctk.CTkButton(btn_frame, text="⏹ STOP", command=self.stop_aimbot, width=100, height=45, fg_color="#333", font=("Segoe UI", 14, "bold")).pack(side="left")

    def build_footer(self):
        """Footer with credits"""
        footer = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=40)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        footer.grid_propagate(False)
        
        ctk.CTkLabel(
            footer,
            text="Made with ♥ by Ahmo934 and Jealousyhaha for Makcu Community",
            font=("Segoe UI", 12, "bold"),
            text_color=NEON
        ).pack(expand=True)

    def on_window_resize(self, event):
        """Handle window resize events for responsive layout"""
        if event.widget == self:
            width = self.winfo_width()
            
            # Switch to single column layout on smaller screens
            if width < 1200:
                self.switch_to_single_column()
            else:
                self.switch_to_two_column()

    def switch_to_single_column(self):
        """Switch to single column layout for smaller screens"""
        if hasattr(self, '_is_single_column') and self._is_single_column:
            return
            
        self._is_single_column = True
        
        # Reconfigure content frame
        self.content_frame.grid_columnconfigure(1, weight=0)
        
        # Move right column content to left column
        for widget in self.right_column.winfo_children():
            widget.grid_forget()
        
        self.right_column.grid_forget()
        self.left_column.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0)

    def switch_to_two_column(self):
        """Switch to two column layout for larger screens"""
        if hasattr(self, '_is_single_column') and not self._is_single_column:
            return
            
        self._is_single_column = False
        
        # Reconfigure content frame
        self.content_frame.grid_columnconfigure(1, weight=1)
        
        # Restore two column layout
        self.left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.right_column.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        
        # Rebuild right column if needed
        if not self.right_column.winfo_children():
            self.build_right_column()

    def on_connect(self):
        """Enhanced connection with visual feedback"""
        Mouse.cleanup()  # Ensure mouse is clean before connecting
        if connect_to_makcu():
            config.makcu_connected = True
            config.makcu_status_msg = "Connected"
            self.connection_status.set("Connected")
            self.connection_color.set("#00FF00")
            self.conn_indicator.configure(fg_color="#00FF00")
            self.error_text.set("✅ MAKCU device connected successfully!")
        else:
            config.makcu_connected = False
            config.makcu_status_msg = "Connection Failed"
            self.connection_status.set("Disconnected")
            self.connection_color.set("#b71c1c")
            self.conn_indicator.configure(fg_color="#b71c1c")
            self.error_text.set("❌ Failed to connect to MAKCU device")
        
        self.conn_status_lbl.configure(text_color=self.connection_color.get())

    def on_switch_to_4m(self):
        """手動切換到 4M baud rate"""
        if not config.makcu_connected:
            self.error_text.set("❌ Please connect to MAKCU first!")
            return
        
        if switch_to_4m():
            self.error_text.set("✅ Successfully switched to 4M baud rate!")
            config.makcu_status_msg = "Connected (4M)"
        else:
            self.error_text.set("⚠️ Failed to switch to 4M, staying at current baud rate")

    def _poll_connection_status(self):
        """Enhanced status polling with visual updates"""
        if config.makcu_connected:
            self.connection_status.set("Connected")
            self.connection_color.set("#00FF00")
            self.conn_indicator.configure(fg_color="#00FF00")
        else:
            self.connection_status.set("Disconnected")
            self.connection_color.set("#b71c1c")
            self.conn_indicator.configure(fg_color="#b71c1c")
        
        self.conn_status_lbl.configure(text_color=self.connection_color.get())
        self.after(500, self._poll_connection_status)

    # Include all the callback methods from gui_callbacks.py
    def refresh_all(self):
        # Initialize FOV X and Y controls
        self.fov_x_slider.set(config.fov_x_size)
        self._set_entry_text(self.fov_x_entry, str(config.fov_x_size))
        self.fov_y_slider.set(config.fov_y_size)
        self._set_entry_text(self.fov_y_entry, str(config.fov_y_size))
        self.offset_slider.set(config.player_y_offset)
        self.offset_value.configure(text=str(config.player_y_offset))
        self.btn_var.set(config.selected_mouse_button)
        self.mode_var.set(config.mode)
        self.model_name.set(os.path.basename(config.model_path))
        self.model_menu.set(os.path.basename(config.model_path))
        self.model_size.set(get_model_size(config.model_path))
        self.aimbot_status.set("Running" if is_aimbot_running() else "Stopped")
        self.in_game_sens_slider.set(config.in_game_sens)
        self.in_game_sens_value.configure(text=f"{config.in_game_sens:.2f}")
        self.always_on_var.set(bool(getattr(config, "always_on_aim", False)))
        self.imgsz_slider.set(config.imgsz)
        self._set_entry_text(self.imgsz_entry, str(config.imgsz))
        self.max_detect_slider.set(config.max_detect)
        self.max_detect_label.configure(text=str(config.max_detect))
        
        # Height targeting controls
        try:
            # Update height targeting main toggle
            self.height_targeting_var.set(bool(getattr(config, "height_targeting_enabled", True)))
            self.target_height_slider.set(config.target_height)
            self._set_entry_text(self.target_height_entry, f"{config.target_height:.3f}")
            self.height_deadzone_var.set(bool(getattr(config, "height_deadzone_enabled", True)))
            self.deadzone_min_slider.set(config.height_deadzone_min)
            self._set_entry_text(self.deadzone_min_entry, f"{config.height_deadzone_min:.3f}")
            self.deadzone_max_slider.set(config.height_deadzone_max)
            self._set_entry_text(self.deadzone_max_entry, f"{config.height_deadzone_max:.3f}")
            self.deadzone_tolerance_slider.set(config.height_deadzone_tolerance)
            self._set_entry_text(self.deadzone_tolerance_entry, f"{config.height_deadzone_tolerance:.3f}")
            
            # Update control states based on height targeting toggle
            height_state = "normal" if config.height_targeting_enabled else "disabled"
            self.target_height_slider.configure(state=height_state)
            self.target_height_entry.configure(state=height_state)
            self.height_deadzone_switch.configure(state=height_state)
            
            # Update control states based on deadzone toggle (only if height targeting is enabled)
            deadzone_state = "normal" if (config.height_targeting_enabled and config.height_deadzone_enabled) else "disabled"
            self.deadzone_min_slider.configure(state=deadzone_state)
            self.deadzone_max_slider.configure(state=deadzone_state)
            self.deadzone_tolerance_slider.configure(state=deadzone_state)
            self.deadzone_min_entry.configure(state=deadzone_state)
            self.deadzone_max_entry.configure(state=deadzone_state)
            self.deadzone_tolerance_entry.configure(state=deadzone_state)
        except Exception:
            pass  # Height controls may not exist yet during initial setup
        
        # X-center targeting controls
        try:
            self.x_center_targeting_var.set(bool(getattr(config, "x_center_targeting_enabled", False)))
            self.x_center_tolerance_slider.set(config.x_center_tolerance_percent)
            self._set_entry_text(self.x_center_tolerance_entry, f"{config.x_center_tolerance_percent:.1f}")
            # Update control states based on X-center targeting toggle
            state = "normal" if config.x_center_targeting_enabled else "disabled"
            self.x_center_tolerance_slider.configure(state=state)
            self.x_center_tolerance_entry.configure(state=state)
        except Exception:
            pass  # X-center controls may not exist yet during initial setup
        
        # Mouse movement multiplier controls
        try:
            self.mouse_multiplier_slider.set(config.mouse_movement_multiplier)
            self._set_entry_text(self.mouse_multiplier_entry, f"{config.mouse_movement_multiplier:.2f}")
        except Exception:
            pass  # Mouse multiplier controls may not exist yet during initial setup
        
        # Mouse movement multiplier X and Y controls
        try:
            self.mouse_multiplier_x_slider.set(getattr(config, 'mouse_movement_multiplier_x', 1.0))
            self._set_entry_text(self.mouse_multiplier_x_entry, f"{getattr(config, 'mouse_movement_multiplier_x', 1.0):.2f}")
            self.mouse_multiplier_y_slider.set(getattr(config, 'mouse_movement_multiplier_y', 1.0))
            self._set_entry_text(self.mouse_multiplier_y_entry, f"{getattr(config, 'mouse_movement_multiplier_y', 1.0):.2f}")
        except Exception:
            pass  # Mouse multiplier X/Y controls may not exist yet during initial setup
        
        # Mouse movement enable/disable toggles
        try:
            self.mouse_movement_enabled_x_var.set(getattr(config, 'mouse_movement_enabled_x', True))
            self.mouse_movement_enabled_y_var.set(getattr(config, 'mouse_movement_enabled_y', True))
        except Exception:
            pass  # Mouse movement toggles may not exist yet during initial setup
        
        # RCS (Recoil Control System) controls
        try:
            self.rcs_enabled_var.set(bool(getattr(config, "rcs_enabled", False)))
            self.rcs_ads_only_var.set(bool(getattr(config, "rcs_ads_only", False)))
            self.rcs_disable_y_axis_var.set(bool(getattr(config, "rcs_disable_y_axis", False)))
            self.rcs_y_random_enabled_var.set(bool(getattr(config, "rcs_y_random_enabled", False)))
            self.rcs_btn_var.set(int(getattr(config, "rcs_button", 0)))
            
            # RCS mode
            if hasattr(self, 'rcs_mode_var'):
                self.rcs_mode_var.set(getattr(config, "rcs_mode", "simple"))
                self.update_rcs_mode_visibility()
            
            # RCS game/weapon
            if hasattr(self, 'rcs_game_var'):
                from recoil_loader import get_available_games, get_available_weapons
                games = get_available_games()
                selected_game = getattr(config, "rcs_game", games[0] if games else "")
                if selected_game and selected_game in games:
                    self.rcs_game_var.set(selected_game)
                    if hasattr(self, 'rcs_game_menu'):
                        self.rcs_game_menu.configure(values=games)
                    weapons = get_available_weapons(selected_game)
                    if hasattr(self, 'rcs_weapon_var'):
                        selected_weapon = getattr(config, "rcs_weapon", weapons[0] if weapons else "")
                        # Validate weapon exists in selected game
                        if selected_weapon and weapons and selected_weapon in weapons:
                            self.rcs_weapon_var.set(selected_weapon)
                        else:
                            # Weapon doesn't exist in current game, use first weapon
                            if weapons:
                                selected_weapon = weapons[0]
                                config.rcs_weapon = selected_weapon
                                self.rcs_weapon_var.set(selected_weapon)
                            else:
                                selected_weapon = ""
                                config.rcs_weapon = ""
                                self.rcs_weapon_var.set("")
                        if hasattr(self, 'rcs_weapon_menu'):
                            self.rcs_weapon_menu.configure(values=weapons)
            
            # RCS multipliers (load from weapon-specific settings)
            game = getattr(config, "rcs_game", "")
            weapon = getattr(config, "rcs_weapon", "")
            if game and weapon:
                multipliers = config.get_weapon_multipliers(game, weapon)
                if hasattr(self, 'rcs_x_multiplier_slider'):
                    self.rcs_x_multiplier_slider.set(multipliers['x_mult'])
                    self._set_entry_text(self.rcs_x_multiplier_entry, f"{multipliers['x_mult']:.2f}")
                if hasattr(self, 'rcs_y_multiplier_slider'):
                    self.rcs_y_multiplier_slider.set(multipliers['y_mult'])
                    self._set_entry_text(self.rcs_y_multiplier_entry, f"{multipliers['y_mult']:.2f}")
                if hasattr(self, 'rcs_x_time_multiplier_slider'):
                    self.rcs_x_time_multiplier_slider.set(multipliers['x_time_mult'])
                    self._set_entry_text(self.rcs_x_time_multiplier_entry, f"{multipliers['x_time_mult']:.2f}")
                if hasattr(self, 'rcs_y_time_multiplier_slider'):
                    self.rcs_y_time_multiplier_slider.set(multipliers['y_time_mult'])
                    self._set_entry_text(self.rcs_y_time_multiplier_entry, f"{multipliers['y_time_mult']:.2f}")
            else:
                # Fallback to default multipliers
                if hasattr(self, 'rcs_x_multiplier_slider'):
                    x_mult = getattr(config, 'rcs_x_multiplier', 1.0)
                    self.rcs_x_multiplier_slider.set(x_mult)
                    self._set_entry_text(self.rcs_x_multiplier_entry, f"{x_mult:.2f}")
                if hasattr(self, 'rcs_y_multiplier_slider'):
                    y_mult = getattr(config, 'rcs_y_multiplier', 1.0)
                    self.rcs_y_multiplier_slider.set(y_mult)
                    self._set_entry_text(self.rcs_y_multiplier_entry, f"{y_mult:.2f}")
                if hasattr(self, 'rcs_x_time_multiplier_slider'):
                    x_time_mult = getattr(config, 'rcs_x_time_multiplier', 1.0)
                    self.rcs_x_time_multiplier_slider.set(x_time_mult)
                    self._set_entry_text(self.rcs_x_time_multiplier_entry, f"{x_time_mult:.2f}")
                if hasattr(self, 'rcs_y_time_multiplier_slider'):
                    y_time_mult = getattr(config, 'rcs_y_time_multiplier', 1.0)
                    self.rcs_y_time_multiplier_slider.set(y_time_mult)
                    self._set_entry_text(self.rcs_y_time_multiplier_entry, f"{y_time_mult:.2f}")
            
            # RCS X-axis controls (simple mode)
            if hasattr(self, 'rcs_x_strength_slider'):
                self.rcs_x_strength_slider.set(config.rcs_x_strength)
                self._set_entry_text(self.rcs_x_strength_entry, f"{config.rcs_x_strength:.2f}")
                self.rcs_x_delay_slider.set(config.rcs_x_delay * 1000)  # Convert to ms
                self._set_entry_text(self.rcs_x_delay_entry, f"{int(config.rcs_x_delay * 1000)}")
            
            # RCS Y-axis controls (simple mode)
            if hasattr(self, 'rcs_y_strength_slider'):
                self.rcs_y_strength_slider.set(config.rcs_y_random_strength)
                self._set_entry_text(self.rcs_y_strength_entry, f"{config.rcs_y_random_strength:.2f}")
                self.rcs_y_delay_slider.set(config.rcs_y_random_delay * 1000)  # Convert to ms
                self._set_entry_text(self.rcs_y_delay_entry, f"{int(config.rcs_y_random_delay * 1000)}")
        except Exception as e:
            print(f"[WARNING] RCS controls refresh error: {e}")
            pass  # RCS controls may not exist yet during initial setup
        
        # Silent mode controls (if they exist)
        try:
            self.silent_strength_slider.set(config.silent_strength)
            self._set_entry_text(self.silent_strength_entry, f"{config.silent_strength:.3f}")
            self.silent_auto_fire_var.set(bool(getattr(config, "silent_auto_fire", False)))
            self.silent_speed_mode_var.set(bool(getattr(config, "silent_speed_mode", True)))
            self.silent_use_bezier_var.set(bool(getattr(config, "silent_use_bezier", False)))
            self.silent_fire_delay_slider.set(config.silent_fire_delay)
            self._set_entry_text(self.silent_fire_delay_entry, f"{config.silent_fire_delay:.3f}")
            self.silent_return_delay_slider.set(config.silent_return_delay)
            self._set_entry_text(self.silent_return_delay_entry, f"{config.silent_return_delay:.3f}")
            self._update_silent_controls_state()
        except Exception:
            pass  # Silent controls may not exist yet during initial setup
        
        self.load_class_list()
        self.update_dynamic_frame()
        self.debug_checkbox_var.set(config.show_debug_window)
        try:
            self.debug_text_info_var.set(bool(getattr(config, "show_debug_text_info", True)))
            self._update_debug_text_info_visibility()
        except Exception:
            pass  # Text info controls may not exist yet during initial setup
        self.input_check_var.set(False)
        # Ensure button masking values are properly loaded from config
        aim_mask_value = bool(getattr(config, "aim_button_mask", False))
        trigger_mask_value = bool(getattr(config, "trigger_button_mask", False))
        
        self.aim_button_mask_var.set(aim_mask_value)
        self.trigger_button_mask_var.set(trigger_mask_value)
        
        # Call the toggle callbacks to ensure functionality is properly initialized
        # This ensures the button masking actually works, not just the GUI state
        self.on_aim_button_mask_toggle()
        self.on_trigger_button_mask_toggle()
        
        self.capture_mode_var.set(config.capturer_mode.upper())
        self.capture_mode_menu.set(config.capturer_mode.upper())
        
        # Update UDP controls
        try:
            self.udp_ip_entry.delete(0, "end")
            self.udp_ip_entry.insert(0, getattr(config, "udp_ip", "192.168.0.01"))
            self.udp_port_entry.delete(0, "end")
            self.udp_port_entry.insert(0, str(getattr(config, "udp_port", 1234)))
        except Exception:
            pass
        
        self.trigger_enabled_var.set(bool(getattr(config, "trigger_enabled", False)))
        self.trigger_always_on_var.set(bool(getattr(config, "trigger_always_on", False)))
        self.trigger_head_only_var.set(bool(getattr(config, "trigger_head_only", False)))
        self.trigger_btn_var.set(int(getattr(config, "trigger_button", 0)))

        try:
            self.tb_radius_entry.delete(0,"end"); self.tb_radius_entry.insert(0, str(config.trigger_radius_px))
            self.tb_delay_entry.delete(0,"end");  self.tb_delay_entry.insert(0, str(config.trigger_delay_ms))
            self.tb_cd_entry.delete(0,"end");     self.tb_cd_entry.insert(0, str(config.trigger_cooldown_ms))
            self.tb_conf_entry.delete(0,"end");   self.tb_conf_entry.insert(0, f"{config.trigger_min_conf:.2f}")
            
            # Mode 3 HSV controls
            self.tb_hsv_h_min_entry.delete(0,"end"); self.tb_hsv_h_min_entry.insert(0, str(getattr(config, "trigger_hsv_h_min", 0)))
            self.tb_hsv_h_max_entry.delete(0,"end"); self.tb_hsv_h_max_entry.insert(0, str(getattr(config, "trigger_hsv_h_max", 179)))
            self.tb_hsv_s_min_entry.delete(0,"end"); self.tb_hsv_s_min_entry.insert(0, str(getattr(config, "trigger_hsv_s_min", 0)))
            self.tb_hsv_s_max_entry.delete(0,"end"); self.tb_hsv_s_max_entry.insert(0, str(getattr(config, "trigger_hsv_s_max", 255)))
            self.tb_hsv_v_min_entry.delete(0,"end"); self.tb_hsv_v_min_entry.insert(0, str(getattr(config, "trigger_hsv_v_min", 0)))
            self.tb_hsv_v_max_entry.delete(0,"end"); self.tb_hsv_v_max_entry.insert(0, str(getattr(config, "trigger_hsv_v_max", 255)))
            self.tb_color_radius_entry.delete(0,"end"); self.tb_color_radius_entry.insert(0, str(getattr(config, "trigger_color_radius_px", 20)))
            self.tb_color_delay_entry.delete(0,"end"); self.tb_color_delay_entry.insert(0, str(getattr(config, "trigger_color_delay_ms", 50)))
            self.tb_color_cooldown_entry.delete(0,"end"); self.tb_color_cooldown_entry.insert(0, str(getattr(config, "trigger_color_cooldown_ms", 200)))
            
            # Update trigger mode menu
            if hasattr(self, 'trigger_mode_menu'):
                current_mode = getattr(config, "trigger_mode", 1)
                if current_mode == 1:
                    mode_text = "Mode 1 (Distance Based)"
                elif current_mode == 2:
                    mode_text = "Mode 2 (Range Detection)"
                else:
                    mode_text = "Mode 3 (Color Detection)"
                self.trigger_mode_menu.set(mode_text)
            
            self._update_trigger_widgets_state()
            self._update_trigger_mode_ui()  # Update UI based on trigger mode
        except Exception:
            pass  

        # NDI source menu initial state
        try:
            self.ndi_source_menu.configure(values=self._ndi_menu_values())
            if isinstance(config.ndi_selected_source, str) and \
            config.ndi_selected_source in self._ndi_menu_values():
                self.ndi_source_var.set(config.ndi_selected_source)
            elif self._ndi_menu_values():
                self.ndi_source_var.set(self._ndi_menu_values()[0])
        except Exception:
            pass

        self._update_ndi_controls_state()
        self._update_capturecard_controls_state()

        # Main PC resolution entries
        try:
            self.main_res_w_entry.delete(0, "end"); self.main_res_w_entry.insert(0, str(config.main_pc_width))
            self.main_res_h_entry.delete(0, "end"); self.main_res_h_entry.insert(0, str(config.main_pc_height))
        except Exception:
            pass

        # CaptureCard control entries
        try:
            self.capturecard_device_entry.delete(0, "end")
            self.capturecard_device_entry.insert(0, str(getattr(config, "capture_device_index", 0)))
            self.capturecard_res_w_entry.delete(0, "end")
            self.capturecard_res_w_entry.insert(0, str(getattr(config, "capture_width", 1920)))
            self.capturecard_res_h_entry.delete(0, "end")
            self.capturecard_res_h_entry.insert(0, str(getattr(config, "capture_height", 1080)))
            self.capturecard_range_x_entry.delete(0, "end")
            self.capturecard_range_x_entry.insert(0, str(getattr(config, "capture_range_x", 0)))
            self.capturecard_range_y_entry.delete(0, "end")
            self.capturecard_range_y_entry.insert(0, str(getattr(config, "capture_range_y", 0)))
            self.capturecard_offset_x_entry.delete(0, "end")
            self.capturecard_offset_x_entry.insert(0, str(getattr(config, "capture_offset_x", 0)))
            self.capturecard_offset_y_entry.delete(0, "end")
            self.capturecard_offset_y_entry.insert(0, str(getattr(config, "capture_offset_y", 0)))
            self.capturecard_fps_entry.delete(0, "end")
            self.capturecard_fps_entry.insert(0, str(getattr(config, "capture_fps", 240)))
            self.capturecard_fourcc_entry.delete(0, "end")
            self.capturecard_fourcc_entry.insert(0, ",".join(getattr(config, "capture_fourcc_preference", ["NV12", "YUY2", "MJPG"])))
        except Exception:
            pass

        # Refresh profile list
        try:
            self.refresh_profile_list()
        except Exception:
            pass


    def on_capture_mode_change(self, value: str):
        m = {"MSS": "mss", "NDI": "ndi", "DXGI": "dxgi", "CAPTURECARD": "capturecard", "UDP": "udp"}  # <- add UDP key
        internal = m.get((value or "").upper(), "mss")
        if config.capturer_mode != internal:
            config.capturer_mode = internal
            self.error_text.set(f"🔁 Capture method set to: {value}")
            self._update_ndi_controls_state()
            self._update_capturecard_controls_state()
            self._update_udp_controls_state()
            # When switching to UDP, immediately load saved IP/Port into entries
            if internal == "udp":
                try:
                    self.udp_ip_entry.delete(0, "end"); self.udp_ip_entry.insert(0, getattr(config, "udp_ip", "192.168.0.01"))
                    self.udp_port_entry.delete(0, "end"); self.udp_port_entry.insert(0, str(getattr(config, "udp_port", 1234)))
                except Exception:
                    pass
            if is_aimbot_running():
                stop_aimbot(); start_aimbot()
            config.save()
        else:
            self._update_ndi_controls_state()
            self._update_capturecard_controls_state()
            self._update_udp_controls_state()

    def on_ndi_source_change(self, value: str):
        if self.capture_mode_var.get().upper() != "NDI":
            return
        if value and not value.startswith("("):
            config.ndi_selected_source = value
            self.ndi_source_var.set(value)
            try:
                self.ndi_source_menu.set(value)
            except Exception:
                pass
            self.error_text.set(f"🔁 NDI source: {value}")
            config.save()

    def update_fov_x(self, val):
        """Called by the FOV X slider."""
        if getattr(self, "_updating_fov_x", False):
            return
        self._apply_fov_x(int(round(val)), source="slider")

    def on_fov_x_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the FOV X entry."""
        try:
            val = int(self.fov_x_entry.get().strip())
        except Exception:
            # revert to current config if invalid
            self._set_entry_text(self.fov_x_entry, str(config.fov_x_size))
            return
        self._apply_fov_x(val, source="entry")

    def _apply_fov_x(self, value, source="code"):
        MIN_FOV, MAX_FOV = 20, 500
        value = max(MIN_FOV, min(MAX_FOV, int(value)))

        # prevent recursion loops
        self._updating_fov_x = True
        try:
            config.fov_x_size = value
            # Update backward compatibility field (use larger of X/Y)
            config.region_size = max(config.fov_x_size, config.fov_y_size)
            # keep slider and entry in sync
            if source != "slider":
                self.fov_x_slider.set(value)
            if source != "entry":
                self._set_entry_text(self.fov_x_entry, str(value))
        finally:
            self._updating_fov_x = False

    def update_fov_y(self, val):
        """Called by the FOV Y slider."""
        if getattr(self, "_updating_fov_y", False):
            return
        self._apply_fov_y(int(round(val)), source="slider")

    def on_fov_y_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the FOV Y entry."""
        try:
            val = int(self.fov_y_entry.get().strip())
        except Exception:
            # revert to current config if invalid
            self._set_entry_text(self.fov_y_entry, str(config.fov_y_size))
            return
        self._apply_fov_y(val, source="entry")

    def _apply_fov_y(self, value, source="code"):
        MIN_FOV, MAX_FOV = 20, 500
        value = max(MIN_FOV, min(MAX_FOV, int(value)))

        # prevent recursion loops
        self._updating_fov_y = True
        try:
            config.fov_y_size = value
            # Update backward compatibility field (use larger of X/Y)
            config.region_size = max(config.fov_x_size, config.fov_y_size)
            # keep slider and entry in sync
            if source != "slider":
                self.fov_y_slider.set(value)
            if source != "entry":
                self._set_entry_text(self.fov_y_entry, str(value))
        finally:
            self._updating_fov_y = False

    def on_trigger_enabled_toggle(self):
        config.trigger_enabled = bool(self.trigger_enabled_var.get())
        self._update_trigger_widgets_state()
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_enabled: {e}")

    def on_trigger_always_on_toggle(self):
        config.trigger_always_on = bool(self.trigger_always_on_var.get())
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_always_on: {e}")

    def _update_trigger_head_only_visibility(self):
        """Update visibility of Head Only checkbox based on Head Class selection."""
        if hasattr(self, 'trigger_head_only_switch'):
            head_class_selected = config.custom_head_label is not None and config.custom_head_label != "None"
            if head_class_selected:
                self.trigger_head_only_switch.pack(side="left", padx=(0, 0))
            else:
                self.trigger_head_only_switch.pack_forget()
                # If Head Class is not selected, disable trigger_head_only
                if self.trigger_head_only_var.get():
                    self.trigger_head_only_var.set(False)
                    config.trigger_head_only = False

    def _update_head_class_in_target_classes(self):
        """Head Only logic: Head Only only considers the Head Class selected in Head Class dropdown.
        It does NOT require Head class to be selected in Target Classes checkbox list."""
        # Head Only only checks if Head Class is selected in Head Class dropdown
        # It does NOT modify Target Classes selection
        pass  # No modification needed

    def on_trigger_head_only_toggle(self):
        """Handle trigger head only checkbox toggle."""
        config.trigger_head_only = bool(self.trigger_head_only_var.get())
        
        # Head Only logic: Head Only = true means triggerbot only works if Head class is in Target Classes
        # User must manually select Head class in Target Classes for Head Only to work
        # We don't modify Target Classes selection automatically
        self._update_head_class_in_target_classes()
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_head_only: {e}")

    def update_trigger_button(self):
        config.trigger_button = int(self.trigger_btn_var.get())
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_button: {e}")

    def on_trigger_mode_change(self, selected_value):
        """Handle trigger mode selection change"""
        try:
            if "Mode 1" in selected_value:
                config.trigger_mode = 1
                print("[INFO] Trigger mode set to Mode 1 (Distance Based)")
            elif "Mode 2" in selected_value:
                config.trigger_mode = 2
                print("[INFO] Trigger mode set to Mode 2 (Range Detection)")
            elif "Mode 3" in selected_value:
                config.trigger_mode = 3
                print("[INFO] Trigger mode set to Mode 3 (Color Detection)")
            
            # Update UI state based on mode
            self._update_trigger_mode_ui()
            
            # Save configuration
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_mode: {e}")

    def _update_trigger_mode_ui(self):
        """Update UI elements based on current trigger mode"""
        try:
            mode = getattr(config, "trigger_mode", 1)
            trigger_enabled = getattr(self, 'trigger_enabled_var', None)
            base_state = "normal" if (trigger_enabled and trigger_enabled.get()) else "disabled"
            
            # Both modes now support delay and cooldown settings
            if hasattr(self, 'tb_delay_entry'):
                self.tb_delay_entry.configure(state=base_state)
            if hasattr(self, 'tb_cd_entry'):
                self.tb_cd_entry.configure(state=base_state)
            
            # Radius is only relevant for Mode 1 and Mode 3 (not Mode 2)
            if hasattr(self, 'tb_radius_label') and hasattr(self, 'tb_radius_entry'):
                if mode == 2:
                    # Mode 2: Hide Radius controls (uses Range X/Y instead)
                    self.tb_radius_label.grid_remove()
                    self.tb_radius_entry.grid_remove()
                else:
                    # Mode 1 and Mode 3: Show Radius controls
                    self.tb_radius_label.grid()
                    self.tb_radius_entry.grid()
                    self.tb_radius_entry.configure(state=base_state)
            
            # Min conf is only relevant for Mode 1 (Distance Based)
            if hasattr(self, 'tb_conf_label') and hasattr(self, 'tb_conf_entry'):
                if mode == 1:
                    # Mode 1: Show Min conf controls
                    self.tb_conf_label.grid()
                    self.tb_conf_entry.grid()
                    self.tb_conf_entry.configure(state=base_state)
                else:
                    # Mode 2 and Mode 3: Hide Min conf controls (not used)
                    self.tb_conf_label.grid_remove()
                    self.tb_conf_entry.grid_remove()
            
            # Mode 2 X/Y Range controls are only relevant for Mode 2
            if hasattr(self, 'tb_mode2_x_label') and hasattr(self, 'tb_mode2_x_entry'):
                if mode == 2:
                    # Mode 2: Show X/Y Range controls
                    self.tb_mode2_x_label.grid()
                    self.tb_mode2_x_entry.grid()
                    self.tb_mode2_x_entry.configure(state=base_state)
                    self.tb_mode2_y_label.grid()
                    self.tb_mode2_y_entry.grid()
                    self.tb_mode2_y_entry.configure(state=base_state)
                else:
                    # Mode 1 and Mode 3: Hide X/Y Range controls
                    self.tb_mode2_x_label.grid_remove()
                    self.tb_mode2_x_entry.grid_remove()
                    self.tb_mode2_y_label.grid_remove()
                    self.tb_mode2_y_entry.grid_remove()
            
            
            # HSV controls are only relevant for Mode 3
            hsv_controls = [
                'tb_color_label', 'tb_color_preview',  # Color picker
                'tb_hsv_h_min_label', 'tb_hsv_h_min_entry',
                'tb_hsv_h_max_label', 'tb_hsv_h_max_entry',
                'tb_hsv_s_min_label', 'tb_hsv_s_min_entry',
                'tb_hsv_s_max_label', 'tb_hsv_s_max_entry',
                'tb_hsv_v_min_label', 'tb_hsv_v_min_entry',
                'tb_hsv_v_max_label', 'tb_hsv_v_max_entry',
                'tb_color_radius_label', 'tb_color_radius_entry',
                'tb_color_delay_label', 'tb_color_delay_entry',
                'tb_color_cooldown_label', 'tb_color_cooldown_entry'
            ]
            
            for control_name in hsv_controls:
                if hasattr(self, control_name):
                    control = getattr(self, control_name)
                    if mode == 3:
                        # Mode 3: Show HSV controls
                        control.grid()
                        if hasattr(control, 'configure') and 'entry' in control_name:
                            control.configure(state=base_state)
                    else:
                        # Mode 1 and Mode 2: Hide HSV controls
                        control.grid_remove()
        except Exception as e:
            print(f"[WARN] Failed to update trigger mode UI: {e}")

    def _update_trigger_widgets_state(self):
        state = "normal" if self.trigger_enabled_var.get() else "disabled"
        try:
            self.tb_radius_entry.configure(state=state)
            self.tb_conf_entry.configure(state=state)
            # Update trigger mode specific UI (handles delay and cooldown based on mode)
            self._update_trigger_mode_ui()
        except Exception:
            pass

    def update_offset(self, val):
        config.player_y_offset = int(round(val))
        self.offset_value.configure(text=str(config.player_y_offset))

    def update_x_offset(self, val):
        try:
            config.x_center_offset_px = int(round(float(val)))
            self.x_offset_value.configure(text=str(config.x_center_offset_px))
            # Prefer async save to avoid blocking GUI
            if hasattr(config, "save_async") and callable(config.save_async):
                config.save_async()
            elif hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            pass

    def update_mouse_btn(self):
        config.selected_mouse_button = self.btn_var.get()

    def update_rcs_btn(self):
        config.rcs_button = self.rcs_btn_var.get()

    def update_mode(self):
        config.mode = self.mode_var.get()
        self.update_dynamic_frame()

    # Removed global confidence UI and handlers; per-class confidence lives under AI Model section

    def _set_entry_text(self, entry, text):
        entry.delete(0, "end")
        entry.insert(0, text)

    def on_mode2_x_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the Mode 2 X range entry."""
        raw = self.tb_mode2_x_entry.get().strip()
        try:
            val = float(raw)
            if 0.5 <= val <= 1000.0:
                config.trigger_mode2_range_x = val
                self._set_entry_text(self.tb_mode2_x_entry, f"{val:.1f}")
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            else:
                self._set_entry_text(self.tb_mode2_x_entry, f"{config.trigger_mode2_range_x:.1f}")
        except ValueError:
            self._set_entry_text(self.tb_mode2_x_entry, f"{config.trigger_mode2_range_x:.1f}")

    def on_mode2_y_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the Mode 2 Y range entry."""
        raw = self.tb_mode2_y_entry.get().strip()
        try:
            val = float(raw)
            if 0.5 <= val <= 1000.0:
                config.trigger_mode2_range_y = val
                self._set_entry_text(self.tb_mode2_y_entry, f"{val:.1f}")
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            else:
                self._set_entry_text(self.tb_mode2_y_entry, f"{config.trigger_mode2_range_y:.1f}")
        except ValueError:
            self._set_entry_text(self.tb_mode2_y_entry, f"{config.trigger_mode2_range_y:.1f}")

    def pick_trigger_color(self):
        """Open color picker for trigger HSV color selection."""
        # Get current color or use default
        current_color = getattr(config, "trigger_hsv_color_hex", "#FFFF00")
        
        # Open color picker dialog
        color = colorchooser.askcolor(color=current_color, title="Select Target Color")
        
        if color[1]:  # color[1] is the hex string
            hex_color = color[1]
            rgb = color[0]  # RGB tuple (0-255)
            
            # Convert RGB to HSV
            import colorsys
            r, g, b = [x / 255.0 for x in rgb]
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            
            # Convert to OpenCV HSV range (H: 0-179, S: 0-255, V: 0-255)
            h_cv = int(h * 179)
            s_cv = int(s * 255)
            v_cv = int(v * 255)
            
            # Update config
            config.trigger_hsv_color_hex = hex_color
            config.trigger_hsv_h_min = max(0, h_cv - 10)
            config.trigger_hsv_h_max = min(179, h_cv + 10)
            config.trigger_hsv_s_min = max(0, s_cv - 50)
            config.trigger_hsv_s_max = min(255, s_cv + 50)
            config.trigger_hsv_v_min = max(0, v_cv - 50)
            config.trigger_hsv_v_max = min(255, v_cv + 50)
            
            # Update GUI
            if hasattr(self, 'tb_color_preview'):
                self.tb_color_preview.configure(fg_color=hex_color, hover_color=hex_color)
            if hasattr(self, 'tb_hsv_h_min_entry'):
                self._set_entry_text(self.tb_hsv_h_min_entry, str(config.trigger_hsv_h_min))
            if hasattr(self, 'tb_hsv_h_max_entry'):
                self._set_entry_text(self.tb_hsv_h_max_entry, str(config.trigger_hsv_h_max))
            if hasattr(self, 'tb_hsv_s_min_entry'):
                self._set_entry_text(self.tb_hsv_s_min_entry, str(config.trigger_hsv_s_min))
            if hasattr(self, 'tb_hsv_s_max_entry'):
                self._set_entry_text(self.tb_hsv_s_max_entry, str(config.trigger_hsv_s_max))
            if hasattr(self, 'tb_hsv_v_min_entry'):
                self._set_entry_text(self.tb_hsv_v_min_entry, str(config.trigger_hsv_v_min))
            if hasattr(self, 'tb_hsv_v_max_entry'):
                self._set_entry_text(self.tb_hsv_v_max_entry, str(config.trigger_hsv_v_max))
            
            # Save config
            if hasattr(config, "save") and callable(config.save):
                config.save()

    def update_imgsz(self, val):
        """Called by the slider."""
        if self._updating_imgsz:
            return
        self._apply_imgsz(int(round(float(val))), source="slider")

    def on_imgsz_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the entry."""
        raw = self.imgsz_entry.get().strip()
        try:
            val = int(raw)
        except Exception:
            # revert to current config if invalid
            self._set_entry_text(self.imgsz_entry, str(config.imgsz))
            return
        self._apply_imgsz(val, source="entry")

    def _snap_to_multiple(self, value, base=32):
        """Snap to nearest multiple of 'base' (YOLO-friendly)."""
        if base <= 1:
            return value
        down = (value // base) * base
        up = down + base
        # choose nearest; prefer 'up' on ties
        return up if (value - down) >= (up - value) else down

    def _apply_imgsz(self, value, source="code"):
        MIN_S, MAX_S = 128, 1280
        value = max(MIN_S, min(MAX_S, int(value)))
        value = self._snap_to_multiple(value, base=32)

        self._updating_imgsz = True
        try:
            config.imgsz = value
            # keep slider and entry in sync
            if source != "slider":
                self.imgsz_slider.set(value)
            if source != "entry":
                self._set_entry_text(self.imgsz_entry, str(value))
        finally:
            self._updating_imgsz = False

    def update_max_detect(self, val):
        val = int(round(float(val)))
        config.max_detect = val
        self.max_detect_label.configure(text=str(val))

    def on_always_on_toggle(self):
        value = bool(self.always_on_var.get())
        config.always_on_aim = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.always_on_aim: {e}")

    def on_rcs_enabled_toggle(self):
        """Handle RCS enable/disable toggle"""
        value = bool(self.rcs_enabled_var.get())
        config.rcs_enabled = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_enabled: {e}")
    
    def on_rcs_y_random_toggle(self):
        """Handle RCS Y-axis random jitter toggle"""
        value = bool(self.rcs_y_random_enabled_var.get())
        config.rcs_y_random_enabled = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_y_random_enabled: {e}")
    
    def on_rcs_ads_only_toggle(self):
        """Handle RCS ADS only toggle"""
        value = bool(self.rcs_ads_only_var.get())
        config.rcs_ads_only = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_ads_only: {e}")
    
    def on_rcs_disable_y_axis_toggle(self):
        """Handle RCS disable Y-axis toggle"""
        value = bool(self.rcs_disable_y_axis_var.get())
        config.rcs_disable_y_axis = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_disable_y_axis: {e}")

    def update_in_game_sens(self, val):
        config.in_game_sens = round(float(val), 2)
        self.in_game_sens_value.configure(text=f"{config.in_game_sens:.2f}")
    
    def update_target_height(self, val):
        """Update target height value (0.100=bottom, 1.000=top)"""
        if getattr(self, '_updating_target_height', False):
            return
        value = round(float(val), 3)
        config.target_height = value
        self._set_entry_text(self.target_height_entry, f"{value:.3f}")
    
    def on_target_height_entry_commit(self, event=None):
        """Handle target height entry input"""
        try:
            value = float(self.target_height_entry.get().strip())
            value = max(0.100, min(1.000, round(value, 3)))
            self._updating_target_height = True
            config.target_height = value
            self.target_height_slider.set(value)
            self._set_entry_text(self.target_height_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.target_height_entry, f"{config.target_height:.3f}")
        finally:
            self._updating_target_height = False
    
    def update_deadzone_min(self, val):
        """Update deadzone minimum value"""
        if getattr(self, '_updating_deadzone_min', False):
            return
        min_val = round(float(val), 3)
        # Clamp to detected class Y-axis lower bound (0.0) and upper bound cap (0.235)
        min_val = max(0.000, min(0.235, min_val))
        config.height_deadzone_min = min_val
        self._set_entry_text(self.deadzone_min_entry, f"{min_val:.3f}")
    
    def on_deadzone_min_entry_commit(self, event=None):
        """Handle deadzone min entry input"""
        try:
            value = float(self.deadzone_min_entry.get().strip())
            value = max(0.000, min(0.235, round(value, 3)))
            self._updating_deadzone_min = True
            config.height_deadzone_min = value
            self.deadzone_min_slider.set(value)
            self._set_entry_text(self.deadzone_min_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.deadzone_min_entry, f"{config.height_deadzone_min:.3f}")
        finally:
            self._updating_deadzone_min = False
    
    def update_deadzone_max(self, val):
        """Update deadzone maximum value"""
        if getattr(self, '_updating_deadzone_max', False):
            return
        max_val = round(float(val), 3)
        # Clamp to highest bound of target class head ratio (0.235)
        max_val = max(0.000, min(0.235, max_val))
        config.height_deadzone_max = max_val
        self._set_entry_text(self.deadzone_max_entry, f"{max_val:.3f}")
    
    def on_deadzone_max_entry_commit(self, event=None):
        """Handle deadzone max entry input"""
        try:
            value = float(self.deadzone_max_entry.get().strip())
            value = max(0.000, min(0.235, round(value, 3)))
            self._updating_deadzone_max = True
            config.height_deadzone_max = value
            self.deadzone_max_slider.set(value)
            self._set_entry_text(self.deadzone_max_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.deadzone_max_entry, f"{config.height_deadzone_max:.3f}")
        finally:
            self._updating_deadzone_max = False
    
    def update_deadzone_tolerance(self, val):
        """Update deadzone tolerance value (pixels for full entry)"""
        if getattr(self, '_updating_deadzone_tolerance', False):
            return
        value = round(float(val), 3)
        config.height_deadzone_tolerance = value
        self._set_entry_text(self.deadzone_tolerance_entry, f"{value:.3f}")
    
    def on_deadzone_tolerance_entry_commit(self, event=None):
        """Handle deadzone tolerance entry input"""
        try:
            value = float(self.deadzone_tolerance_entry.get().strip())
            value = max(0.000, min(15.000, round(value, 3)))
            self._updating_deadzone_tolerance = True
            config.height_deadzone_tolerance = value
            self.deadzone_tolerance_slider.set(value)
            self._set_entry_text(self.deadzone_tolerance_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.deadzone_tolerance_entry, f"{config.height_deadzone_tolerance:.3f}")
        finally:
            self._updating_deadzone_tolerance = False
    
    def on_height_targeting_toggle(self):
        """Toggle height targeting functionality"""
        config.height_targeting_enabled = bool(self.height_targeting_var.get())
        # Enable/disable all height targeting controls based on toggle
        state = "normal" if config.height_targeting_enabled else "disabled"
        try:
            # Disable/enable target height controls
            self.target_height_slider.configure(state=state)
            self.target_height_entry.configure(state=state)
            # Disable/enable deadzone controls
            self.height_deadzone_switch.configure(state=state)
            self.deadzone_min_slider.configure(state=state)
            self.deadzone_max_slider.configure(state=state)
            self.deadzone_tolerance_slider.configure(state=state)
            self.deadzone_min_entry.configure(state=state)
            self.deadzone_max_entry.configure(state=state)
            self.deadzone_tolerance_entry.configure(state=state)
        except Exception:
            pass
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_targeting_enabled: {e}")
    
    def on_height_deadzone_toggle(self):
        """Toggle height deadzone functionality"""
        config.height_deadzone_enabled = bool(self.height_deadzone_var.get())
        # Enable/disable deadzone controls based on toggle
        state = "normal" if config.height_deadzone_enabled else "disabled"
        try:
            self.deadzone_min_slider.configure(state=state)
            self.deadzone_max_slider.configure(state=state)
            self.deadzone_tolerance_slider.configure(state=state)
            self.deadzone_min_entry.configure(state=state)
            self.deadzone_max_entry.configure(state=state)
            self.deadzone_tolerance_entry.configure(state=state)
        except Exception:
            pass
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_deadzone_enabled: {e}")
    
    # --- X-Center Targeting Controls ---
    def on_x_center_targeting_toggle(self):
        """Toggle X-axis center targeting functionality"""
        config.x_center_targeting_enabled = bool(self.x_center_targeting_var.get())
        # Enable/disable X-center targeting controls based on toggle
        state = "normal" if config.x_center_targeting_enabled else "disabled"
        try:
            self.x_center_tolerance_slider.configure(state=state)
            self.x_center_tolerance_entry.configure(state=state)
        except Exception:
            pass
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save x_center_targeting_enabled: {e}")
    
    def update_x_center_tolerance(self, val):
        """Update X-center tolerance percentage value"""
        if getattr(self, '_updating_x_center_tolerance', False):
            return
        value = round(float(val), 1)
        config.x_center_tolerance_percent = value
        self._set_entry_text(self.x_center_tolerance_entry, f"{value:.1f}")
    
    def on_x_center_tolerance_entry_commit(self, event=None):
        """Handle X-center tolerance entry input"""
        try:
            value = float(self.x_center_tolerance_entry.get().strip())
            value = max(0.0, min(50.0, round(value, 1)))
            self._updating_x_center_tolerance = True
            config.x_center_tolerance_percent = value
            self.x_center_tolerance_slider.set(value)
            self._set_entry_text(self.x_center_tolerance_entry, f"{value:.1f}")
        except Exception:
            self._set_entry_text(self.x_center_tolerance_entry, f"{config.x_center_tolerance_percent:.1f}")
        finally:
            self._updating_x_center_tolerance = False
    
    # --- Mouse Movement Multiplier Controls ---
    def update_mouse_multiplier(self, val):
        """Update mouse movement multiplier value"""
        if getattr(self, '_updating_mouse_multiplier', False):
            return
        value = round(float(val), 2)
        config.mouse_movement_multiplier = value
        self._set_entry_text(self.mouse_multiplier_entry, f"{value:.2f}")

    def update_mouse_multiplier_x(self, val):
        """Update mouse movement multiplier X-axis value"""
        if getattr(self, '_updating_mouse_multiplier_x', False):
            return
        value = round(float(val), 2)
        config.mouse_movement_multiplier_x = value
        self._set_entry_text(self.mouse_multiplier_x_entry, f"{value:.2f}")

    def update_mouse_multiplier_y(self, val):
        """Update mouse movement multiplier Y-axis value"""
        if getattr(self, '_updating_mouse_multiplier_y', False):
            return
        value = round(float(val), 2)
        config.mouse_movement_multiplier_y = value
        self._set_entry_text(self.mouse_multiplier_y_entry, f"{value:.2f}")
    
    # RCS (Recoil Control System) Update Functions
    def update_rcs_x_strength(self, val):
        """Update RCS X-axis strength value"""
        if getattr(self, '_updating_rcs_x_strength', False):
            return
        value = round(float(val), 2)
        config.rcs_x_strength = value
        self._set_entry_text(self.rcs_x_strength_entry, f"{value:.2f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_x_strength: {e}")
    
    def update_rcs_x_delay(self, val):
        """Update RCS X-axis delay value (convert from ms to seconds)"""
        if getattr(self, '_updating_rcs_x_delay', False):
            return
        value_ms = int(round(float(val)))
        value_s = value_ms / 1000.0  # Convert to seconds
        config.rcs_x_delay = value_s
        self._set_entry_text(self.rcs_x_delay_entry, f"{value_ms}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_x_delay: {e}")
    
    def update_rcs_y_strength(self, val):
        """Update RCS Y-axis random strength value"""
        if getattr(self, '_updating_rcs_y_strength', False):
            return
        value = round(float(val), 2)
        config.rcs_y_random_strength = value
        self._set_entry_text(self.rcs_y_strength_entry, f"{value:.2f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_y_random_strength: {e}")
    
    def update_rcs_y_delay(self, val):
        """Update RCS Y-axis random delay value (convert from ms to seconds)"""
        if getattr(self, '_updating_rcs_y_delay', False):
            return
        value_ms = int(round(float(val)))
        value_s = value_ms / 1000.0  # Convert to seconds
        config.rcs_y_random_delay = value_s
        self._set_entry_text(self.rcs_y_delay_entry, f"{value_ms}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_y_random_delay: {e}")
    
    def on_mouse_multiplier_entry_commit(self, event=None):
        """Handle mouse movement multiplier entry input"""
        try:
            value = float(self.mouse_multiplier_entry.get().strip())
            value = max(0.1, min(5.0, round(value, 2)))
            self._updating_mouse_multiplier = True
            config.mouse_movement_multiplier = value
            self.mouse_multiplier_slider.set(value)
            self._set_entry_text(self.mouse_multiplier_entry, f"{value:.2f}")
        except Exception:
            self._set_entry_text(self.mouse_multiplier_entry, f"{config.mouse_movement_multiplier:.2f}")
        finally:
            self._updating_mouse_multiplier = False

    def on_mouse_multiplier_x_entry_commit(self, event=None):
        """Handle mouse movement multiplier X-axis entry input"""
        try:
            value = float(self.mouse_multiplier_x_entry.get().strip())
            value = max(0.0, min(5.0, round(value, 2)))
            self._updating_mouse_multiplier_x = True
            config.mouse_movement_multiplier_x = value
            self.mouse_multiplier_x_slider.set(value)
            self._set_entry_text(self.mouse_multiplier_x_entry, f"{value:.2f}")
        except Exception:
            self._set_entry_text(self.mouse_multiplier_x_entry, f"{getattr(config, 'mouse_movement_multiplier_x', 1.0):.2f}")
        finally:
            self._updating_mouse_multiplier_x = False

    def on_mouse_multiplier_y_entry_commit(self, event=None):
        """Handle mouse movement multiplier Y-axis entry input"""
        try:
            value = float(self.mouse_multiplier_y_entry.get().strip())
            value = max(0.0, min(5.0, round(value, 2)))
            self._updating_mouse_multiplier_y = True
            config.mouse_movement_multiplier_y = value
            self.mouse_multiplier_y_slider.set(value)
            self._set_entry_text(self.mouse_multiplier_y_entry, f"{value:.2f}")
        except Exception:
            self._set_entry_text(self.mouse_multiplier_y_entry, f"{getattr(config, 'mouse_movement_multiplier_y', 1.0):.2f}")
        finally:
            self._updating_mouse_multiplier_y = False

    def on_mouse_movement_enabled_x_toggle(self):
        """Handle X-axis movement enable/disable toggle"""
        config.mouse_movement_enabled_x = self.mouse_movement_enabled_x_var.get()
        if hasattr(config, "save") and callable(config.save):
            config.save()
        print(f"[INFO] X-axis movement {'enabled' if config.mouse_movement_enabled_x else 'disabled'}")

    def on_mouse_movement_enabled_y_toggle(self):
        """Handle Y-axis movement enable/disable toggle"""
        config.mouse_movement_enabled_y = self.mouse_movement_enabled_y_var.get()
        if hasattr(config, "save") and callable(config.save):
            config.save()
        print(f"[INFO] Y-axis movement {'enabled' if config.mouse_movement_enabled_y else 'disabled'}")
    
    # RCS Entry Commit Functions
    def on_rcs_x_strength_entry_commit(self, event=None):
        """Handle RCS X-axis strength entry input"""
        try:
            value = float(self.rcs_x_strength_entry.get().strip())
            value = max(0.1, min(5.0, round(value, 2)))
            self._updating_rcs_x_strength = True
            config.rcs_x_strength = value
            self.rcs_x_strength_slider.set(value)
            self._set_entry_text(self.rcs_x_strength_entry, f"{value:.2f}")
            # Save configuration
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            self._set_entry_text(self.rcs_x_strength_entry, f"{config.rcs_x_strength:.2f}")
        finally:
            self._updating_rcs_x_strength = False
    
    def on_rcs_x_delay_entry_commit(self, event=None):
        """Handle RCS X-axis delay entry input (convert from ms to seconds)"""
        try:
            value_ms = int(self.rcs_x_delay_entry.get().strip())
            value_ms = max(1, min(100, value_ms))
            value_s = value_ms / 1000.0  # Convert to seconds
            self._updating_rcs_x_delay = True
            config.rcs_x_delay = value_s
            self.rcs_x_delay_slider.set(value_ms)
            self._set_entry_text(self.rcs_x_delay_entry, f"{value_ms}")
            # Save configuration
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            self._set_entry_text(self.rcs_x_delay_entry, f"{int(config.rcs_x_delay * 1000)}")
        finally:
            self._updating_rcs_x_delay = False
    
    def on_rcs_y_strength_entry_commit(self, event=None):
        """Handle RCS Y-axis random strength entry input"""
        try:
            value = float(self.rcs_y_strength_entry.get().strip())
            value = max(0.1, min(3.0, round(value, 2)))
            self._updating_rcs_y_strength = True
            config.rcs_y_random_strength = value
            self.rcs_y_strength_slider.set(value)
            self._set_entry_text(self.rcs_y_strength_entry, f"{value:.2f}")
            # Save configuration
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            self._set_entry_text(self.rcs_y_strength_entry, f"{config.rcs_y_random_strength:.2f}")
        finally:
            self._updating_rcs_y_strength = False
    
    def on_rcs_y_delay_entry_commit(self, event=None):
        """Handle RCS Y-axis random delay entry input (convert from ms to seconds)"""
        try:
            value_ms = int(self.rcs_y_delay_entry.get().strip())
            value_ms = max(1, min(100, value_ms))
            value_s = value_ms / 1000.0  # Convert to seconds
            self._updating_rcs_y_delay = True
            config.rcs_y_random_delay = value_s
            self.rcs_y_delay_slider.set(value_ms)
            self._set_entry_text(self.rcs_y_delay_entry, f"{value_ms}")
            # Save configuration
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            self._set_entry_text(self.rcs_y_delay_entry, f"{int(config.rcs_y_random_delay * 1000)}")
        finally:
            self._updating_rcs_y_delay = False
    
    # --- RCS Game Mode Callbacks ---
    def on_rcs_mode_change(self):
        """Handle RCS mode change (simple/game)"""
        config.rcs_mode = self.rcs_mode_var.get()
        self.update_rcs_mode_visibility()
        if hasattr(config, "save") and callable(config.save):
            config.save()
    
    def update_rcs_mode_visibility(self):
        """Update visibility of RCS settings based on mode"""
        mode = getattr(self, 'rcs_mode_var', None)
        if mode is None:
            return
        
        is_game_mode = mode.get() == "game"
        
        # Show/hide game frame
        if hasattr(self, 'game_frame'):
            if is_game_mode:
                self.game_frame.grid()
            else:
                self.game_frame.grid_remove()
        
        # Show/hide simple frame
        if hasattr(self, 'simple_frame'):
            if not is_game_mode:
                self.simple_frame.grid()
            else:
                self.simple_frame.grid_remove()
    
    def on_rcs_game_change(self, game):
        """Handle game selection change"""
        from recoil_loader import get_available_weapons, load_recoil_data
        
        config.rcs_game = game
        weapons = get_available_weapons(game)
        
        if hasattr(self, 'rcs_weapon_menu'):
            self.rcs_weapon_menu.configure(values=weapons if weapons else ["No weapons available"])
            if weapons:
                self.rcs_weapon_var.set(weapons[0])
                config.rcs_weapon = weapons[0]
                # Load and preview the data
                data = load_recoil_data(game, weapons[0])
                print(f"[INFO] RCS: Loaded {len(data)} recoil patterns for {game}/{weapons[0]}")
                
                # Load weapon-specific multipliers
                multipliers = config.get_weapon_multipliers(game, weapons[0])
                if hasattr(self, 'rcs_x_multiplier_slider'):
                    self.rcs_x_multiplier_slider.set(multipliers['x_mult'])
                    self._set_entry_text(self.rcs_x_multiplier_entry, f"{multipliers['x_mult']:.2f}")
                if hasattr(self, 'rcs_y_multiplier_slider'):
                    self.rcs_y_multiplier_slider.set(multipliers['y_mult'])
                    self._set_entry_text(self.rcs_y_multiplier_entry, f"{multipliers['y_mult']:.2f}")
                if hasattr(self, 'rcs_x_time_multiplier_slider'):
                    self.rcs_x_time_multiplier_slider.set(multipliers['x_time_mult'])
                    self._set_entry_text(self.rcs_x_time_multiplier_entry, f"{multipliers['x_time_mult']:.2f}")
                if hasattr(self, 'rcs_y_time_multiplier_slider'):
                    self.rcs_y_time_multiplier_slider.set(multipliers['y_time_mult'])
                    self._set_entry_text(self.rcs_y_time_multiplier_entry, f"{multipliers['y_time_mult']:.2f}")
            else:
                self.rcs_weapon_var.set("")
                config.rcs_weapon = ""
        
        if hasattr(config, "save") and callable(config.save):
            config.save()
    
    def on_rcs_weapon_change(self, weapon):
        """Handle weapon selection change"""
        from recoil_loader import load_recoil_data
        
        config.rcs_weapon = weapon
        game = getattr(config, "rcs_game", "")
        
        # Load and preview the data
        if game and weapon:
            data = load_recoil_data(game, weapon)
            print(f"[INFO] RCS: Loaded {len(data)} recoil patterns for {game}/{weapon}")
            if data:
                # Show first few patterns as preview
                preview = data[:3]
                print(f"[INFO] RCS Preview (first 3): {preview}")
            
            # Load weapon-specific multipliers
            multipliers = config.get_weapon_multipliers(game, weapon)
            if hasattr(self, 'rcs_x_multiplier_slider'):
                self.rcs_x_multiplier_slider.set(multipliers['x_mult'])
                self._set_entry_text(self.rcs_x_multiplier_entry, f"{multipliers['x_mult']:.2f}")
            if hasattr(self, 'rcs_y_multiplier_slider'):
                self.rcs_y_multiplier_slider.set(multipliers['y_mult'])
                self._set_entry_text(self.rcs_y_multiplier_entry, f"{multipliers['y_mult']:.2f}")
            if hasattr(self, 'rcs_x_time_multiplier_slider'):
                self.rcs_x_time_multiplier_slider.set(multipliers['x_time_mult'])
                self._set_entry_text(self.rcs_x_time_multiplier_entry, f"{multipliers['x_time_mult']:.2f}")
            if hasattr(self, 'rcs_y_time_multiplier_slider'):
                self.rcs_y_time_multiplier_slider.set(multipliers['y_time_mult'])
                self._set_entry_text(self.rcs_y_time_multiplier_entry, f"{multipliers['y_time_mult']:.2f}")
        
        if hasattr(config, "save") and callable(config.save):
            config.save()
    
    def update_rcs_x_multiplier(self, val):
        """Update X-axis movement multiplier for current weapon"""
        if hasattr(self, '_updating_rcs_x_multiplier') and self._updating_rcs_x_multiplier:
            return
        value = round(float(val), 2)
        game = getattr(config, "rcs_game", "")
        weapon = getattr(config, "rcs_weapon", "")
        if game and weapon:
            config.set_weapon_multipliers(game, weapon, x_mult=value)
        else:
            config.rcs_x_multiplier = value  # Fallback to default
        self._set_entry_text(self.rcs_x_multiplier_entry, f"{value:.2f}")
        # Use async save to avoid blocking and prevent config reload issues
        if hasattr(config, "save_async") and callable(config.save_async):
            config.save_async()
        elif hasattr(config, "save") and callable(config.save):
            config.save()
    
    def update_rcs_y_multiplier(self, val):
        """Update Y-axis movement multiplier for current weapon"""
        if hasattr(self, '_updating_rcs_y_multiplier') and self._updating_rcs_y_multiplier:
            return
        value = round(float(val), 2)
        game = getattr(config, "rcs_game", "")
        weapon = getattr(config, "rcs_weapon", "")
        if game and weapon:
            config.set_weapon_multipliers(game, weapon, y_mult=value)
        else:
            config.rcs_y_multiplier = value  # Fallback to default
        self._set_entry_text(self.rcs_y_multiplier_entry, f"{value:.2f}")
        # Use async save to avoid blocking and prevent config reload issues
        if hasattr(config, "save_async") and callable(config.save_async):
            config.save_async()
        elif hasattr(config, "save") and callable(config.save):
            config.save()
    
    def update_rcs_x_time_multiplier(self, val):
        """Update X-axis time multiplier for current weapon"""
        if hasattr(self, '_updating_rcs_x_time_multiplier') and self._updating_rcs_x_time_multiplier:
            return
        value = round(float(val), 2)
        game = getattr(config, "rcs_game", "")
        weapon = getattr(config, "rcs_weapon", "")
        if game and weapon:
            config.set_weapon_multipliers(game, weapon, x_time_mult=value)
        else:
            config.rcs_x_time_multiplier = value  # Fallback to default
        self._set_entry_text(self.rcs_x_time_multiplier_entry, f"{value:.2f}")
        # Use async save to avoid blocking and prevent config reload issues
        if hasattr(config, "save_async") and callable(config.save_async):
            config.save_async()
        elif hasattr(config, "save") and callable(config.save):
            config.save()
    
    def update_rcs_y_time_multiplier(self, val):
        """Update Y-axis time multiplier for current weapon"""
        if hasattr(self, '_updating_rcs_y_time_multiplier') and self._updating_rcs_y_time_multiplier:
            return
        value = round(float(val), 2)
        game = getattr(config, "rcs_game", "")
        weapon = getattr(config, "rcs_weapon", "")
        if game and weapon:
            config.set_weapon_multipliers(game, weapon, y_time_mult=value)
        else:
            config.rcs_y_time_multiplier = value  # Fallback to default
        self._set_entry_text(self.rcs_y_time_multiplier_entry, f"{value:.2f}")
        # Use async save to avoid blocking and prevent config reload issues
        if hasattr(config, "save_async") and callable(config.save_async):
            config.save_async()
        elif hasattr(config, "save") and callable(config.save):
            config.save()
    
    def on_rcs_x_multiplier_entry_commit(self, event=None):
        """Handle X-axis movement multiplier entry input"""
        try:
            value = float(self.rcs_x_multiplier_entry.get().strip())
            value = max(0.1, min(5.0, value))
            self._updating_rcs_x_multiplier = True
            game = getattr(config, "rcs_game", "")
            weapon = getattr(config, "rcs_weapon", "")
            if game and weapon:
                config.set_weapon_multipliers(game, weapon, x_mult=value)
            else:
                config.rcs_x_multiplier = value  # Fallback to default
            self.rcs_x_multiplier_slider.set(value)
            self._set_entry_text(self.rcs_x_multiplier_entry, f"{value:.2f}")
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            game = getattr(config, "rcs_game", "")
            weapon = getattr(config, "rcs_weapon", "")
            if game and weapon:
                multipliers = config.get_weapon_multipliers(game, weapon)
                self._set_entry_text(self.rcs_x_multiplier_entry, f"{multipliers['x_mult']:.2f}")
            else:
                self._set_entry_text(self.rcs_x_multiplier_entry, f"{config.rcs_x_multiplier:.2f}")
        finally:
            self._updating_rcs_x_multiplier = False
    
    def on_rcs_y_multiplier_entry_commit(self, event=None):
        """Handle Y-axis movement multiplier entry input"""
        try:
            value = float(self.rcs_y_multiplier_entry.get().strip())
            value = max(0.1, min(5.0, value))
            self._updating_rcs_y_multiplier = True
            game = getattr(config, "rcs_game", "")
            weapon = getattr(config, "rcs_weapon", "")
            if game and weapon:
                config.set_weapon_multipliers(game, weapon, y_mult=value)
            else:
                config.rcs_y_multiplier = value  # Fallback to default
            self.rcs_y_multiplier_slider.set(value)
            self._set_entry_text(self.rcs_y_multiplier_entry, f"{value:.2f}")
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            game = getattr(config, "rcs_game", "")
            weapon = getattr(config, "rcs_weapon", "")
            if game and weapon:
                multipliers = config.get_weapon_multipliers(game, weapon)
                self._set_entry_text(self.rcs_y_multiplier_entry, f"{multipliers['y_mult']:.2f}")
            else:
                self._set_entry_text(self.rcs_y_multiplier_entry, f"{config.rcs_y_multiplier:.2f}")
        finally:
            self._updating_rcs_y_multiplier = False
    
    def on_rcs_x_time_multiplier_entry_commit(self, event=None):
        """Handle X-axis time multiplier entry input"""
        try:
            value = float(self.rcs_x_time_multiplier_entry.get().strip())
            value = max(0.1, min(5.0, value))
            self._updating_rcs_x_time_multiplier = True
            game = getattr(config, "rcs_game", "")
            weapon = getattr(config, "rcs_weapon", "")
            if game and weapon:
                config.set_weapon_multipliers(game, weapon, x_time_mult=value)
            else:
                config.rcs_x_time_multiplier = value  # Fallback to default
            self.rcs_x_time_multiplier_slider.set(value)
            self._set_entry_text(self.rcs_x_time_multiplier_entry, f"{value:.2f}")
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            game = getattr(config, "rcs_game", "")
            weapon = getattr(config, "rcs_weapon", "")
            if game and weapon:
                multipliers = config.get_weapon_multipliers(game, weapon)
                self._set_entry_text(self.rcs_x_time_multiplier_entry, f"{multipliers['x_time_mult']:.2f}")
            else:
                self._set_entry_text(self.rcs_x_time_multiplier_entry, f"{config.rcs_x_time_multiplier:.2f}")
        finally:
            self._updating_rcs_x_time_multiplier = False
    
    def on_rcs_y_time_multiplier_entry_commit(self, event=None):
        """Handle Y-axis time multiplier entry input"""
        try:
            value = float(self.rcs_y_time_multiplier_entry.get().strip())
            value = max(0.1, min(5.0, value))
            self._updating_rcs_y_time_multiplier = True
            game = getattr(config, "rcs_game", "")
            weapon = getattr(config, "rcs_weapon", "")
            if game and weapon:
                config.set_weapon_multipliers(game, weapon, y_time_mult=value)
            else:
                config.rcs_y_time_multiplier = value  # Fallback to default
            self.rcs_y_time_multiplier_slider.set(value)
            self._set_entry_text(self.rcs_y_time_multiplier_entry, f"{value:.2f}")
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            game = getattr(config, "rcs_game", "")
            weapon = getattr(config, "rcs_weapon", "")
            if game and weapon:
                multipliers = config.get_weapon_multipliers(game, weapon)
                self._set_entry_text(self.rcs_y_time_multiplier_entry, f"{multipliers['y_time_mult']:.2f}")
            else:
                self._set_entry_text(self.rcs_y_time_multiplier_entry, f"{config.rcs_y_time_multiplier:.2f}")
        finally:
            self._updating_rcs_y_time_multiplier = False
    
    # --- Silent Mode Enhanced Controls ---
    def update_silent_strength(self, val):
        """Update silent strength value"""
        if getattr(self, '_updating_silent_strength', False):
            return
        value = round(float(val), 3)
        config.silent_strength = value
        self._set_entry_text(self.silent_strength_entry, f"{value:.3f}")
    
    def on_silent_strength_entry_commit(self, event=None):
        """Handle silent strength entry input"""
        try:
            value = float(self.silent_strength_entry.get().strip())
            value = max(0.100, min(3.000, round(value, 3)))
            self._updating_silent_strength = True
            config.silent_strength = value
            self.silent_strength_slider.set(value)
            self._set_entry_text(self.silent_strength_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.silent_strength_entry, f"{config.silent_strength:.3f}")
        finally:
            self._updating_silent_strength = False
    
    def on_silent_auto_fire_toggle(self):
        """Toggle silent auto fire functionality"""
        config.silent_auto_fire = bool(self.silent_auto_fire_var.get())
        self._update_silent_controls_state()
        status = "enabled" if config.silent_auto_fire else "disabled"
        print(f"[INFO] Silent auto fire {status}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save silent_auto_fire: {e}")
    
    def on_silent_speed_mode_toggle(self):
        """Toggle silent speed mode for ultra-fast execution"""
        config.silent_speed_mode = bool(self.silent_speed_mode_var.get())
        status = "enabled" if config.silent_speed_mode else "disabled"
        print(f"[INFO] Silent speed mode {status}")
        
        # Auto-adjust timing for speed mode
        if config.silent_speed_mode:
            # Ultra-fast timing
            config.silent_fire_delay = 0.001
            config.silent_return_delay = 0.005
            config.silent_cooldown = 0.02
            print("[INFO] Speed mode: Ultra-fast timing applied")
        else:
            # Standard timing
            config.silent_fire_delay = 0.010
            config.silent_return_delay = 0.020
            config.silent_cooldown = 0.05
            print("[INFO] Speed mode: Standard timing restored")
        
        # Update GUI to reflect changes
        try:
            self.silent_fire_delay_slider.set(config.silent_fire_delay)
            self._set_entry_text(self.silent_fire_delay_entry, f"{config.silent_fire_delay:.3f}")
            self.silent_return_delay_slider.set(config.silent_return_delay)
            self._set_entry_text(self.silent_return_delay_entry, f"{config.silent_return_delay:.3f}")
        except Exception:
            pass
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save silent_speed_mode: {e}")
    
    def update_silent_fire_delay(self, val):
        """Update silent fire delay value"""
        if getattr(self, '_updating_silent_fire_delay', False):
            return
        value = round(float(val), 3)
        config.silent_fire_delay = value
        self._set_entry_text(self.silent_fire_delay_entry, f"{value:.3f}")
    
    def on_silent_fire_delay_entry_commit(self, event=None):
        """Handle silent fire delay entry input"""
        try:
            value = float(self.silent_fire_delay_entry.get().strip())
            value = max(0.000, min(0.200, round(value, 3)))
            self._updating_silent_fire_delay = True
            config.silent_fire_delay = value
            self.silent_fire_delay_slider.set(value)
            self._set_entry_text(self.silent_fire_delay_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.silent_fire_delay_entry, f"{config.silent_fire_delay:.3f}")
        finally:
            self._updating_silent_fire_delay = False
    
    def update_silent_return_delay(self, val):
        """Update silent return delay value"""
        if getattr(self, '_updating_silent_return_delay', False):
            return
        value = round(float(val), 3)
        config.silent_return_delay = value
        self._set_entry_text(self.silent_return_delay_entry, f"{value:.3f}")
    
    def on_silent_return_delay_entry_commit(self, event=None):
        """Handle silent return delay entry input"""
        try:
            value = float(self.silent_return_delay_entry.get().strip())
            value = max(0.000, min(0.500, round(value, 3)))
            self._updating_silent_return_delay = True
            config.silent_return_delay = value
            self.silent_return_delay_slider.set(value)
            self._set_entry_text(self.silent_return_delay_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.silent_return_delay_entry, f"{config.silent_return_delay:.3f}")
        finally:
            self._updating_silent_return_delay = False
    
    def on_silent_bezier_toggle(self):
        """Toggle silent bezier curve movement"""
        config.silent_use_bezier = bool(self.silent_use_bezier_var.get())
        status = "enabled" if config.silent_use_bezier else "disabled"
        print(f"[INFO] Silent bezier movement {status}")
        
        # Inform user about bezier curve vs direct movement
        if config.silent_use_bezier:
            print("[INFO] Using bezier curve for smoother movement (slightly slower)")
        else:
            print("[INFO] Using direct movement for maximum speed")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save silent_use_bezier: {e}")
    
    def _update_silent_controls_state(self):
        """Update silent controls based on auto fire setting"""
        try:
            state = "normal" if config.silent_auto_fire else "disabled"
            self.silent_fire_delay_slider.configure(state=state)
            self.silent_fire_delay_entry.configure(state=state)
        except Exception:
            pass

    def poll_fps(self):
        self.fps_var.set(f"FPS: {main.fps:.1f}")
        self.aimbot_status.set("Running" if is_aimbot_running() else "Stopped")
        self.after(200, self.poll_fps)

    def get_model_list(self):
        model_files = []
        for ext in ("pt", "onnx", "engine"):
            model_files.extend(glob.glob(f"models/*.{ext}"))
        return [os.path.basename(p) for p in model_files]

    def _detect_model_input_size(self, path):
        """Return square input size inferred from model (prefer ONNX actual input shape).
        Falls back to existing config.imgsz if detection fails.
        """
        try:
            if path.lower().endswith(".onnx"):
                try:
                    import onnxruntime as ort
                except Exception:
                    return int(config.imgsz)
                # Use CPU provider only to avoid GPU init
                sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
                inputs = sess.get_inputs()
                if not inputs:
                    return int(config.imgsz)
                shape = inputs[0].shape  # e.g., [1, 3, 640, 640]
                # Extract H, W from the last two dims if they are integers
                h = shape[-2]
                w = shape[-1]
                if isinstance(h, int) and isinstance(w, int) and h > 0 and w > 0:
                    size = max(h, w)
                else:
                    # If symbolic, try scan for first int dims
                    nums = [d for d in shape if isinstance(d, int)]
                    size = max(nums) if nums else int(config.imgsz)
                # Clamp and align to 32 as typical for YOLO-like models
                size = int(max(128, min(1280, size)))
                size = ((size + 31) // 32) * 32
                return size
            else:
                # Unsupported format for static shape detection; keep current
                return int(config.imgsz)
        except Exception:
            return int(config.imgsz)

    def select_model(self, val):
        path = os.path.join("models", val)
        if os.path.isfile(path):
            config.model_path = path
            self.model_name.set(os.path.basename(path))
            self.model_size.set(get_model_size(path))
            # Auto-detect model input size (from model graph when possible)
            try:
                detected = self._detect_model_input_size(path)
                self._updating_imgsz = True
                try:
                    config.imgsz = detected
                    self.imgsz_slider.set(detected)
                    self._set_entry_text(self.imgsz_entry, str(detected))
                    if hasattr(config, "save") and callable(config.save):
                        config.save()
                finally:
                    self._updating_imgsz = False
            except Exception:
                pass
            try:
                reload_model(path)
                self.load_class_list()
                self.error_text.set(f"✅ Model '{val}' loaded successfully")
            except Exception as e:
                self.error_text.set(f"❌ Failed to load model: {e}")
        else:
            self.error_text.set(f"❌ Model file not found: {path}")

    def reload_model(self):
        try:
            reload_model(config.model_path)
            self.load_class_list()
            self.error_text.set("✅ Model reloaded successfully")
        except Exception as e:
            self.error_text.set(f"❌ Failed to reload model: {e}")

    def load_class_list(self):
        try:
            classes = get_model_classes(config.model_path)
            self.available_classes = classes
            self.class_listbox.delete("0.0", "end")
            
            for i, c in enumerate(classes):
                display_text = f"Class {i}: {c}\n"
                self.class_listbox.insert("end", display_text)
            
            class_options = [str(c) for c in classes]
            self.head_class_menu.configure(values=["None"] + class_options)

            current_head = config.custom_head_label
            self.head_class_var.set(str(current_head) if current_head is not None else "None")

            # Rebuild multi-select checklist for players (with per-class confidence)
            self._build_player_class_checklist()
            
        except Exception as e:
            self.error_text.set(f"❌ Failed to load classes: {e}")

    def get_available_classes(self):
        classes = getattr(self, "available_classes", ["0", "1"])
        return [str(c) for c in classes]

    def set_head_class(self, val):
        if val == "None":
            config.custom_head_label = None
        else:
            config.custom_head_label = val
        print(f"[DEBUG] Head class set to: {config.custom_head_label}")
        # Update Head Only checkbox visibility when Head Class changes
        self._update_trigger_head_only_visibility()

    def set_player_class(self, val):
        config.custom_player_label = val
        print(f"[DEBUG] Player class set to: {config.custom_player_label}")

    def _build_player_class_checklist(self):
        """Build or rebuild the multi-select checklist for player classes."""
        # Clear existing
        for w in self.player_class_list_frame.winfo_children():
            w.destroy()
        self.player_class_vars.clear()
        self._class_conf_widgets.clear()

        classes = self.get_available_classes()
        # Preselected from config
        preselected = set(getattr(config, "selected_player_classes", []) or [])

        for idx, cls_name in enumerate(classes):
            row = idx
            container = ctk.CTkFrame(self.player_class_list_frame, fg_color="#2a2a2a")
            container.grid(row=row, column=0, sticky="ew", padx=5, pady=3)
            container.grid_columnconfigure(2, weight=1)

            # Checkbox for selecting class
            var = ctk.BooleanVar()
            var.set(cls_name in preselected)
            def make_cmd(name, v):
                return lambda: self._on_player_class_toggle(name, v.get())
            chk = ctk.CTkCheckBox(container, text=str(cls_name), variable=var, command=make_cmd(cls_name, var))
            chk.grid(row=0, column=0, sticky="w", padx=(8, 10), pady=6)
            self.player_class_vars[cls_name] = var

            # Slider for per-class confidence
            slider = ctk.CTkSlider(container, from_=0.05, to=0.95, number_of_steps=18)
            slider.grid(row=0, column=2, sticky="ew", padx=(0, 8))

            # Entry to show/edit precise value
            entry = ctk.CTkEntry(container, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
            entry.grid(row=0, column=3, padx=(0, 8))

            # Initial value from config map, fallback to global conf
            try:
                current = float((getattr(config, "class_confidence", {}) or {}).get(str(cls_name), config.conf))
            except Exception:
                current = float(config.conf)
            current = max(0.05, min(0.95, round(current, 2)))
            slider.set(current)
            self._set_entry_text(entry, f"{current:.2f}")

            def on_slider(val, name=cls_name, entry_ref=entry):
                v = round(float(val), 2)
                v = max(0.05, min(0.95, v))
                self._set_entry_text(entry_ref, f"{v:.2f}")
                self._set_class_conf(name, v)

            def on_entry_commit(event=None, name=cls_name, slider_ref=slider, entry_ref=entry):
                raw = entry_ref.get().strip()
                if raw.startswith("."):
                    raw = "0" + raw
                try:
                    v = round(float(raw), 2)
                except Exception:
                    v = current
                v = max(0.05, min(0.95, v))
                slider_ref.set(v)
                self._set_entry_text(entry_ref, f"{v:.2f}")
                self._set_class_conf(name, v)

            slider.configure(command=on_slider)
            entry.bind("<Return>", on_entry_commit)
            entry.bind("<FocusOut>", on_entry_commit)
            self._class_conf_widgets[cls_name] = (slider, entry)

    def _on_player_class_toggle(self, class_name: str, checked: bool):
        """Handle checkbox toggle and persist selection to config."""
        try:
            selected = set(getattr(config, "selected_player_classes", []) or [])
            if checked:
                selected.add(str(class_name))
            else:
                selected.discard(str(class_name))
            config.selected_player_classes = sorted(selected)
            # Optional: keep single label in sync for backward compatibility
            if not config.selected_player_classes:
                config.custom_player_label = "Select a Player Class"
            else:
                # Use first selected as representative
                config.custom_player_label = config.selected_player_classes[0]
            if hasattr(config, "save") and callable(config.save):
                config.save()
            print(f"[DEBUG] Selected player classes: {config.selected_player_classes}")
        except Exception as e:
            print(f"[WARN] Failed to update selected_player_classes: {e}")

    def _set_class_conf(self, class_name: str, value: float):
        try:
            if not hasattr(config, "class_confidence") or config.class_confidence is None:
                config.class_confidence = {}
            config.class_confidence[str(class_name)] = float(value)
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to set class confidence for '{class_name}': {e}")

    def update_dynamic_frame(self):
        for w in self.dynamic_frame.winfo_children():
            w.destroy()
        mode = config.mode
        if mode == "normal":
            self.add_speed_section("Normal", "normal_x_speed", "normal_y_speed")
        elif mode == "bezier":
            self.add_bezier_section("bezier_segments", "bezier_ctrl_x", "bezier_ctrl_y")
        elif mode == "silent":
            # Only add the Enhanced Silent section, no separate Bezier settings
            self.add_silent_section()
        elif mode == "smooth":
            self.add_smooth_section()
        elif mode == "ncaf":
            self.add_ncaf_section()

    def add_speed_section(self, label, min_key, max_key):
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#1a1a1a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(f, text=f"⚙️ {label} Aim Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")
        
        ctk.CTkLabel(f, text="X Speed:", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        x_slider = ctk.CTkSlider(f, from_=0.1, to=5.0, number_of_steps=490)  # 490 steps for 0.01 precision (4.9/0.01)
        x_slider.set(getattr(config, min_key))
        x_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
        x_entry = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        x_entry.grid(row=1, column=2, padx=10, pady=2)
        x_entry.insert(0, f"{getattr(config, min_key):.2f}")
        
        # Guard to prevent feedback loops
        _updating_x = False
        
        def update_x(val):
            nonlocal _updating_x
            if _updating_x:
                return
            val = round(float(val), 2)  # Round to 2 decimal places
            setattr(config, min_key, val)
            if not _updating_x:
                _updating_x = True
                x_entry.delete(0, "end")
                x_entry.insert(0, f"{val:.2f}")
                _updating_x = False
        
        def on_x_entry_commit(event=None):
            nonlocal _updating_x
            if _updating_x:
                return
            try:
                val = float(x_entry.get().strip())
                val = max(0.1, min(5.0, round(val, 2)))  # Clamp to valid range
                _updating_x = True
                setattr(config, min_key, val)
                x_slider.set(val)
                x_entry.delete(0, "end")
                x_entry.insert(0, f"{val:.2f}")
            except ValueError:
                # Reset to current config value on invalid input
                x_entry.delete(0, "end")
                x_entry.insert(0, f"{getattr(config, min_key):.2f}")
            finally:
                _updating_x = False
        
        x_slider.configure(command=update_x)
        x_entry.bind("<Return>", on_x_entry_commit)
        x_entry.bind("<FocusOut>", on_x_entry_commit)
        
        ctk.CTkLabel(f, text="Y Speed:", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=(2, 10))
        y_slider = ctk.CTkSlider(f, from_=0.1, to=5.0, number_of_steps=490)  # 490 steps for 0.01 precision (4.9/0.01)
        y_slider.set(getattr(config, max_key))
        y_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=(2, 10))
        y_entry = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        y_entry.grid(row=2, column=2, padx=10, pady=(2, 10))
        y_entry.insert(0, f"{getattr(config, max_key):.2f}")
        
        # Guard to prevent feedback loops
        _updating_y = False
        
        def update_y(val):
            nonlocal _updating_y
            if _updating_y:
                return
            val = round(float(val), 2)  # Round to 2 decimal places
            setattr(config, max_key, val)
            if not _updating_y:
                _updating_y = True
                y_entry.delete(0, "end")
                y_entry.insert(0, f"{val:.2f}")
                _updating_y = False
        
        def on_y_entry_commit(event=None):
            nonlocal _updating_y
            if _updating_y:
                return
            try:
                val = float(y_entry.get().strip())
                val = max(0.1, min(5.0, round(val, 2)))  # Clamp to valid range
                _updating_y = True
                setattr(config, max_key, val)
                y_slider.set(val)
                y_entry.delete(0, "end")
                y_entry.insert(0, f"{val:.2f}")
            except ValueError:
                # Reset to current config value on invalid input
                y_entry.delete(0, "end")
                y_entry.insert(0, f"{getattr(config, max_key):.2f}")
            finally:
                _updating_y = False
        
        y_slider.configure(command=update_y)
        y_entry.bind("<Return>", on_y_entry_commit)
        y_entry.bind("<FocusOut>", on_y_entry_commit)

    def add_bezier_section(self, seg_key, cx_key, cy_key):
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#1a1a1a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(f, text="🌀 Bezier Curve Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")
        
        ctk.CTkLabel(f, text="Segments:", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        seg_slider = ctk.CTkSlider(f, from_=0, to=20, number_of_steps=20, command=lambda v: setattr(config, seg_key, int(float(v))))
        seg_slider.set(getattr(config, seg_key))
        seg_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
        
        ctk.CTkLabel(f, text="Control X:", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        cx_slider = ctk.CTkSlider(f, from_=0, to=60, number_of_steps=60, command=lambda v: setattr(config, cx_key, int(float(v))))
        cx_slider.set(getattr(config, cx_key))
        cx_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=2)
        
        ctk.CTkLabel(f, text="Control Y:", text_color="#fff").grid(row=3, column=0, sticky="w", padx=10, pady=(2, 10))
        cy_slider = ctk.CTkSlider(f, from_=0, to=60, number_of_steps=60, command=lambda v: setattr(config, cy_key, int(float(v))))
        cy_slider.set(getattr(config, cy_key))
        cy_slider.grid(row=3, column=1, sticky="ew", padx=(5, 5), pady=(2, 10))

    def add_silent_section(self):
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#2a2a2a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(f, text="🤫 Silent Aim Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")
        
        # Traditional settings
        ctk.CTkLabel(f, text="Speed:", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        speed_slider = ctk.CTkSlider(f, from_=1, to=6, number_of_steps=5, command=lambda v: setattr(config, "silent_speed", int(float(v))))
        speed_slider.set(config.silent_speed)
        speed_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
        
        ctk.CTkLabel(f, text="Cooldown:", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        cooldown_slider = ctk.CTkSlider(f, from_=0.00, to=0.5, number_of_steps=50, command=lambda v: setattr(config, "silent_cooldown", float(v)))
        cooldown_slider.set(config.silent_cooldown)
        cooldown_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=2)
        
        # Enhanced Silent Mode
        ctk.CTkLabel(f, text="⚡ Enhanced Silent Mode", font=("Segoe UI", 12, "bold"), text_color="#ff073a").grid(row=3, column=0, columnspan=3, pady=(15, 5), padx=10, sticky="w")
        
        # Silent Strength
        ctk.CTkLabel(f, text="Silent Strength:", text_color="#fff").grid(row=4, column=0, sticky="w", padx=10, pady=2)
        self.silent_strength_slider = ctk.CTkSlider(f, from_=0.100, to=3.000, number_of_steps=2900, command=self.update_silent_strength)
        self.silent_strength_slider.set(config.silent_strength)
        self.silent_strength_slider.grid(row=4, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.silent_strength_entry = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.silent_strength_entry.grid(row=4, column=2, padx=10, pady=2)
        self.silent_strength_entry.insert(0, f"{config.silent_strength:.3f}")
        self.silent_strength_entry.bind("<Return>", self.on_silent_strength_entry_commit)
        self.silent_strength_entry.bind("<FocusOut>", self.on_silent_strength_entry_commit)
        
        # Auto Fire Toggle
        self.silent_auto_fire_var = ctk.BooleanVar(value=config.silent_auto_fire)
        self.silent_auto_fire_switch = ctk.CTkSwitch(
            f,
            text="Auto Fire",
            variable=self.silent_auto_fire_var,
            command=self.on_silent_auto_fire_toggle,
            text_color="#fff"
        )
        self.silent_auto_fire_switch.grid(row=5, column=0, sticky="w", padx=10, pady=(5, 2))
        
        # Speed Mode Toggle
        self.silent_speed_mode_var = ctk.BooleanVar(value=config.silent_speed_mode)
        self.silent_speed_mode_switch = ctk.CTkSwitch(
            f,
            text="⚡ Speed Mode",
            variable=self.silent_speed_mode_var,
            command=self.on_silent_speed_mode_toggle,
            text_color="#00ff00"
        )
        self.silent_speed_mode_switch.grid(row=5, column=1, columnspan=2, sticky="w", padx=10, pady=(5, 2))
        
        # Fire Delay
        ctk.CTkLabel(f, text="Fire Delay:", text_color="#fff").grid(row=6, column=0, sticky="w", padx=10, pady=2)
        self.silent_fire_delay_slider = ctk.CTkSlider(f, from_=0.000, to=0.200, number_of_steps=200, command=self.update_silent_fire_delay)
        self.silent_fire_delay_slider.set(config.silent_fire_delay)
        self.silent_fire_delay_slider.grid(row=6, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.silent_fire_delay_entry = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.silent_fire_delay_entry.grid(row=6, column=2, padx=10, pady=2)
        self.silent_fire_delay_entry.insert(0, f"{config.silent_fire_delay:.3f}")
        self.silent_fire_delay_entry.bind("<Return>", self.on_silent_fire_delay_entry_commit)
        self.silent_fire_delay_entry.bind("<FocusOut>", self.on_silent_fire_delay_entry_commit)
        
        # Return Delay
        ctk.CTkLabel(f, text="Return Delay:", text_color="#fff").grid(row=7, column=0, sticky="w", padx=10, pady=2)
        self.silent_return_delay_slider = ctk.CTkSlider(f, from_=0.000, to=0.500, number_of_steps=500, command=self.update_silent_return_delay)
        self.silent_return_delay_slider.set(config.silent_return_delay)
        self.silent_return_delay_slider.grid(row=7, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.silent_return_delay_entry = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.silent_return_delay_entry.grid(row=7, column=2, padx=10, pady=2)
        self.silent_return_delay_entry.insert(0, f"{config.silent_return_delay:.3f}")
        self.silent_return_delay_entry.bind("<Return>", self.on_silent_return_delay_entry_commit)
        self.silent_return_delay_entry.bind("<FocusOut>", self.on_silent_return_delay_entry_commit)
        
        # Bezier Curve Toggle
        self.silent_use_bezier_var = ctk.BooleanVar(value=config.silent_use_bezier)
        self.silent_use_bezier_switch = ctk.CTkSwitch(
            f,
            text="🌀 Use Bezier Curve",
            variable=self.silent_use_bezier_var,
            command=self.on_silent_bezier_toggle,
            text_color="#fff"
        )
        self.silent_use_bezier_switch.grid(row=8, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 10))
        
        # Update control states
        self._update_silent_controls_state()

    def add_smooth_section(self):
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#0a0a0a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)
        
        # Title
        ctk.CTkLabel(f, text="🌪️ WindMouse Smooth Aim", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 10), padx=10, sticky="w")
        
        # Core parameters
        params = [
            ("Gravity:", "smooth_gravity", 1, 20, 19),
            ("Wind:", "smooth_wind", 1, 20, 19),
            ("Close Speed:", "smooth_close_speed", 0.1, 1.0, 18),
            ("Far Speed:", "smooth_far_speed", 0.1, 1.0, 18),
            ("Reaction Time:", "smooth_reaction_max", 0.01, 0.3, 29),
            ("Max Step:", "smooth_max_step", 5, 50, 45)
        ]
        
        for i, (label, key, min_val, max_val, steps) in enumerate(params):
            ctk.CTkLabel(f, text=label, text_color="#fff", font=("Segoe UI", 11, "bold")).grid(row=i+1, column=0, sticky="w", padx=10, pady=2)
            
            slider = ctk.CTkSlider(f, from_=min_val, to=max_val, number_of_steps=steps)
            slider.set(getattr(config, key))
            slider.grid(row=i+1, column=1, sticky="ew", padx=(5, 5), pady=2)
            
            if "time" in key.lower():
                value_text = f"{getattr(config, key):.3f}s"
            elif "step" in key.lower():
                value_text = f"{getattr(config, key):.0f}px"
            else:
                value_text = f"{getattr(config, key):.2f}"
                
            value_label = ctk.CTkLabel(f, text=value_text, text_color=NEON, width=60, font=("Segoe UI", 11, "bold"))
            value_label.grid(row=i+1, column=2, padx=10, pady=2)
            
            def make_update_func(param_key, label_widget):
                def update_func(val):
                    setattr(config, param_key, float(val))
                    if "time" in param_key.lower():
                        text = f"{float(val):.3f}s"
                        if param_key == "smooth_reaction_max":
                            config.smooth_reaction_min = float(val) * 0.7
                    elif "step" in param_key.lower():
                        text = f"{float(val):.0f}px"
                    else:
                        text = f"{float(val):.2f}"
                    label_widget.configure(text=text)
                return update_func
            
            slider.configure(command=make_update_func(key, value_label))
        
        # Presets
        preset_frame = ctk.CTkFrame(f, fg_color="#1a1a1a", corner_radius=8)
        preset_frame.grid(row=len(params)+1, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 10))
        
        ctk.CTkLabel(preset_frame, text="Quick Presets:", font=("Segoe UI", 11, "bold"), text_color="#ccc").pack(pady=(8, 5))
        
        preset_buttons = ctk.CTkFrame(preset_frame, fg_color="transparent")
        preset_buttons.pack(pady=(0, 8))
        
        def apply_preset(preset_type):
            presets = {
                "human": (9.0, 3.0, 0.3, 0.7, 0.12, 12.0),
                "precise": (15.0, 1.5, 0.2, 0.5, 0.08, 8.0),
                "aggressive": (12.0, 5.0, 0.5, 0.9, 0.05, 20.0)
            }
            
            if preset_type in presets:
                values = presets[preset_type]
                config.smooth_gravity = values[0]
                config.smooth_wind = values[1]
                config.smooth_close_speed = values[2]
                config.smooth_far_speed = values[3]
                config.smooth_reaction_max = values[4]
                config.smooth_max_step = values[5]
                config.smooth_reaction_min = values[4] * 0.3
                
                # Refresh the UI
                self.update_dynamic_frame()
        
        for preset_name in ["human", "precise", "aggressive"]:
            ctk.CTkButton(
                preset_buttons, 
                text=preset_name.title(), 
                command=lambda p=preset_name: apply_preset(p), 
                width=90, 
                height=28
            ).pack(side="left", padx=3)

    def add_ncaf_section(self):
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#1a1a1a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text="⚙️ NCAF Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")

        def add_row(r, label, key, min_v, max_v, steps, fmt):
            ctk.CTkLabel(f, text=label, text_color="#fff").grid(row=r, column=0, sticky="w", padx=10, pady=2)
            s = ctk.CTkSlider(f, from_=min_v, to=max_v, number_of_steps=steps)
            s.set(float(getattr(config, key)))
            s.grid(row=r, column=1, sticky="ew", padx=(5, 5), pady=2)
            e = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
            e.grid(row=r, column=2, padx=10, pady=2)
            e.insert(0, (fmt % float(getattr(config, key))))

            def on_slide(val, k=key, entry=e, fstr=fmt, lo=min_v, hi=max_v):
                v = float(val)
                v = max(lo, min(hi, v))
                setattr(config, k, v)
                entry.delete(0, "end"); entry.insert(0, (fstr % v))
                if hasattr(config, 'save') and callable(config.save):
                    config.save()

            def on_commit(event=None, k=key, slider=s, entry=e, fstr=fmt, lo=min_v, hi=max_v):
                try:
                    v = float(entry.get().strip())
                except Exception:
                    v = float(getattr(config, k))
                v = max(lo, min(hi, v))
                setattr(config, k, v)
                slider.set(v)
                entry.delete(0, "end"); entry.insert(0, (fstr % v))
                if hasattr(config, 'save') and callable(config.save):
                    config.save()

            s.configure(command=on_slide)
            e.bind("<Return>", on_commit)
            e.bind("<FocusOut>", on_commit)

        add_row(1, "Near Radius (px):", "ncaf_near_radius", 10.0, 400.0, 390, "%.1f")
        add_row(2, "Snap Radius (px):", "ncaf_snap_radius", 0.0, 80.0, 80, "%.1f")
        add_row(3, "Alpha (curve):", "ncaf_alpha", 0.1, 3.0, 290, "%.2f")
        add_row(4, "Snap Boost:", "ncaf_snap_boost", 1.0, 2.0, 100, "%.2f")
        add_row(5, "Max Step (px):", "ncaf_max_step", 0.0, 80.0, 80, "%.1f")
        add_row(6, "Tracker IoU:", "ncaf_iou_threshold", 0.10, 0.90, 80, "%.2f")
        # TTL is integer
        ctk.CTkLabel(f, text="Tracker Max TTL:", text_color="#fff").grid(row=7, column=0, sticky="w", padx=10, pady=(2, 10))
        ttl_slider = ctk.CTkSlider(f, from_=1, to=30, number_of_steps=29)
        ttl_slider.set(int(getattr(config, 'ncaf_max_ttl', 8)))
        ttl_slider.grid(row=7, column=1, sticky="ew", padx=(5, 5), pady=(2, 10))
        ttl_entry = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        ttl_entry.grid(row=7, column=2, padx=10, pady=(2, 10))
        ttl_entry.insert(0, str(int(getattr(config, 'ncaf_max_ttl', 8))))

        def on_ttl_slide(val):
            try:
                v = int(round(float(val)))
            except Exception:
                v = int(getattr(config, 'ncaf_max_ttl', 8))
            v = max(1, min(30, v))
            config.ncaf_max_ttl = v
            ttl_entry.delete(0, "end"); ttl_entry.insert(0, str(v))
            if hasattr(config, 'save') and callable(config.save):
                config.save()

        def on_ttl_commit(event=None):
            try:
                v = int(round(float(ttl_entry.get().strip())))
            except Exception:
                v = int(getattr(config, 'ncaf_max_ttl', 8))
            v = max(1, min(30, v))
            config.ncaf_max_ttl = v
            ttl_slider.set(v)
            ttl_entry.delete(0, "end"); ttl_entry.insert(0, str(v))
            if hasattr(config, 'save') and callable(config.save):
                config.save()

        ttl_slider.configure(command=on_ttl_slide)
        ttl_entry.bind("<Return>", on_ttl_commit)
        ttl_entry.bind("<FocusOut>", on_ttl_commit)

        # Show in debug window checkbox
        show_var = ctk.BooleanVar(value=bool(getattr(config, 'ncaf_show_debug', False)))
        def on_toggle():
            try:
                config.ncaf_show_debug = bool(show_var.get())
                if hasattr(config, 'save') and callable(config.save):
                    config.save()
            except Exception:
                pass
        show_chk = ctk.CTkCheckBox(f, text="Show in debug window", variable=show_var, command=on_toggle, text_color="#fff")
        show_chk.grid(row=8, column=0, columnspan=3, sticky="w", padx=10, pady=(4, 8))

    def save_profile(self):
        config.save()
        self.error_text.set("✅ Profile saved successfully!")

    def load_profile(self):
        config.load()
        self.refresh_all()
        self.error_text.set("✅ Profile loaded successfully!")

    def reset_defaults(self):
        config.reset_to_defaults()
        self.refresh_all()
        self.error_text.set("✅ Settings reset to defaults!")

    def start_aimbot(self):
        start_aimbot()
        button_names = ["Left", "Right", "Middle", "Side 4", "Side 5"]
        button_name = button_names[config.selected_mouse_button] if config.selected_mouse_button < len(button_names) else f"Button {config.selected_mouse_button}"
        self.error_text.set(f"🎯 Aimbot started in {config.mode} mode! Hold {button_name} to aim.")

    def stop_aimbot(self):
        stop_aimbot()
        self.aimbot_status.set("Stopped")
        self.error_text.set("⏹ Aimbot stopped.")

    def on_close(self):
        print("[INFO] Application closing...")
        
        # Stop aimbot first
        stop_aimbot()
        
        # Additional OpenCV cleanup for safety
        try:
            import cv2
            cv2.destroyAllWindows()
            # Wait a bit for cleanup
            cv2.waitKey(1)
        except Exception as e:
            print(f"[WARN] Final OpenCV cleanup: {e}")
        
        # Destroy GUI
        self.destroy()

    def on_debug_toggle(self):
        config.show_debug_window = self.debug_checkbox_var.get()
        if not config.show_debug_window:
            # Just set the flag, let the detection thread handle window cleanup
            # to avoid thread synchronization issues with OpenCV
            print("[INFO] Debug window closing requested via GUI")
        else:
            # Start monitoring debug window status
            self.after(1000, self._check_debug_window_status)
        
        # Update text info checkbox visibility
        self._update_debug_text_info_visibility()
    
    def on_debug_text_info_toggle(self):
        """Toggle text information display in debug window"""
        config.show_debug_text_info = bool(self.debug_text_info_var.get())
        status = "enabled" if config.show_debug_text_info else "disabled"
        print(f"[INFO] Debug text info {status}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save debug_text_info: {e}")
    
    def _update_debug_text_info_visibility(self):
        """Show/hide text info checkbox based on debug window state"""
        try:
            if self.debug_checkbox_var.get():
                # Show text info checkbox when debug window is enabled
                self.debug_text_info_checkbox.grid()
            else:
                # Hide text info checkbox when debug window is disabled
                self.debug_text_info_checkbox.grid_remove()
        except Exception:
            pass
    
    def _check_debug_window_status(self):
        """Periodically check if debug window was closed externally"""
        try:
            if self.debug_checkbox_var.get() and not config.show_debug_window:
                # Debug window was closed externally, update GUI
                self.debug_checkbox_var.set(False)
                print("[INFO] Debug window status synced with GUI")
            elif self.debug_checkbox_var.get() and config.show_debug_window:
                # Continue monitoring if debug window is still supposed to be open
                self.after(1000, self._check_debug_window_status)
        except Exception as e:
            print(f"[WARN] Debug window status check error: {e}")
            # Stop monitoring on error
            pass

    def on_input_check_toggle(self):
        if self.input_check_var.get():
            self.show_input_check_window()
        else:
            self.hide_input_check_window()
    def on_aim_button_mask_toggle(self):
        value = bool(self.aim_button_mask_var.get())
        config.aim_button_mask = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.aim_button_mask: {e}")

    def on_trigger_button_mask_toggle(self):
        value = bool(self.trigger_button_mask_var.get())
        config.trigger_button_mask = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.trigger_button_mask: {e}")

    def show_input_check_window(self):
        if hasattr(self, 'input_check_window') and self.input_check_window is not None:
            return
        self.input_check_window = ctk.CTkToplevel(self)
        self.input_check_window.title("Button States Monitor")
        self.input_check_window.geometry("320x240")
        self.input_check_window.resizable(False, False)
        self.input_check_window.configure(fg_color="#181818")
        
        ctk.CTkLabel(self.input_check_window, text="🎮 Input Monitor", font=("Segoe UI", 16, "bold"), text_color="#00e676").pack(pady=(15, 10))
        
        self.input_check_labels = []
        for i in range(5):
            frame = ctk.CTkFrame(self.input_check_window, fg_color="transparent")
            frame.pack(pady=3, padx=20, fill="x")
            
            ctk.CTkLabel(frame, text=f"Button {i}:", font=("Segoe UI", 12, "bold"), text_color="#fff").pack(side="left")
            
            lbl = ctk.CTkLabel(frame, text="Released", font=("Segoe UI", 12, "bold"), text_color="#FF5555")
            lbl.pack(side="right")
            
            self.input_check_labels.append(lbl)
        
        self.update_input_check_window()
        self.input_check_window.protocol("WM_DELETE_WINDOW", self._on_input_check_close)

    def update_input_check_window(self):
        if not hasattr(self, 'input_check_window') or self.input_check_window is None:
            return
        
        from mouse import button_states, button_states_lock
        
        with button_states_lock:
            for i, lbl in enumerate(self.input_check_labels):
                state = button_states.get(i, False)
                color = "#00FF00" if state else "#FF5555"
                text = "PRESSED" if state else "Released"
                lbl.configure(text=text, text_color=color)
        
        self.after(50, self.update_input_check_window)

    def hide_input_check_window(self):
        if hasattr(self, 'input_check_window') and self.input_check_window:
            self.input_check_window.destroy()
            self.input_check_window = None

    def _on_input_check_close(self):
        self.input_check_var.set(False)
        self.hide_input_check_window()

    # Configuration Management Methods
    def get_profile_list(self):
        """Get list of available configuration profiles"""
        profiles = self.config_manager.get_config_files()
        if not profiles:
            profiles = ["config_profile"]  # Default profile
        return profiles

    def on_profile_select(self, selected_profile):
        """Handle profile selection from dropdown"""
        self.current_config_name.set(selected_profile)
        self.error_text.set(f"📁 Selected profile: {selected_profile}")

    def create_profile_dialog(self):
        """Show dialog to create a new profile"""
        dialog = ctk.CTkInputDialog(
            text="Enter new profile name:",
            title="Create New Profile"
        )
        new_name = dialog.get_input()
        
        if new_name and new_name.strip():
            new_name = new_name.strip()
            if self.config_manager.config_exists(new_name):
                self.error_text.set(f"❌ Profile '{new_name}' already exists!")
                return
            
            # Get current config data
            current_config = self.get_current_config_data()
            
            if self.config_manager.create_config(new_name, current_config):
                self.error_text.set(f"✅ Profile '{new_name}' created successfully!")
                self.refresh_profile_list()
                self.profile_var.set(new_name)
            else:
                self.error_text.set(f"❌ Failed to create profile '{new_name}'")

    def rename_profile_dialog(self):
        """Show dialog to rename current profile"""
        current_profile = self.profile_var.get()
        if not current_profile:
            self.error_text.set("❌ No profile selected to rename!")
            return
        
        dialog = ctk.CTkInputDialog(
            text=f"Enter new name for '{current_profile}':",
            title="Rename Profile"
        )
        new_name = dialog.get_input()
        
        if new_name and new_name.strip():
            new_name = new_name.strip()
            if new_name == current_profile:
                self.error_text.set("❌ New name is the same as current name!")
                return
            
            if self.config_manager.config_exists(new_name):
                self.error_text.set(f"❌ Profile '{new_name}' already exists!")
                return
            
            if self.config_manager.rename_config(current_profile, new_name):
                self.error_text.set(f"✅ Profile renamed from '{current_profile}' to '{new_name}'!")
                self.refresh_profile_list()
                self.profile_var.set(new_name)
            else:
                self.error_text.set(f"❌ Failed to rename profile!")

    def delete_profile_dialog(self):
        """Show confirmation dialog to delete profile"""
        current_profile = self.profile_var.get()
        if not current_profile:
            self.error_text.set("❌ No profile selected to delete!")
            return
        
        # Don't allow deleting the default profiles
        if current_profile in ["config_profile", "default"]:
            self.error_text.set("❌ Cannot delete the default profile!")
            return
        
        result = messagebox.askyesno(
            "Delete Profile",
            f"Are you sure you want to delete profile '{current_profile}'?\n\nThis action cannot be undone!",
            icon='warning'
        )
        
        if result:
            if self.config_manager.delete_config(current_profile):
                self.error_text.set(f"✅ Profile '{current_profile}' deleted successfully!")
                self.refresh_profile_list()
                # Switch to default profile
                self.profile_var.set("config_profile")
            else:
                self.error_text.set(f"❌ Failed to delete profile '{current_profile}'!")

    def save_current_profile(self):
        """Save current settings to the selected profile"""
        current_profile = self.profile_var.get()
        if not current_profile:
            self.error_text.set("❌ No profile selected!")
            return
        
        # Get current config data
        current_config = self.get_current_config_data()
        
        if self.config_manager.save_config(current_profile, current_config):
            self.error_text.set(f"✅ Settings saved to profile '{current_profile}'!")
        else:
            self.error_text.set(f"❌ Failed to save settings to profile '{current_profile}'!")

    def load_selected_profile(self):
        """Load settings from the selected profile"""
        current_profile = self.profile_var.get()
        if not current_profile:
            self.error_text.set("❌ No profile selected!")
            return
        
        # Load config data
        config_data = self.config_manager.load_config(current_profile)
        if not config_data:
            self.error_text.set(f"❌ Failed to load profile '{current_profile}'!")
            return
        
        # Apply loaded settings
        self.apply_config_data(config_data)
        self.error_text.set(f"✅ Profile '{current_profile}' loaded successfully!")

    def get_current_config_data(self):
        """Get current configuration data as dictionary"""
        config_data = {}
        
        # Get all config attributes
        for attr in dir(config):
            if not attr.startswith('_') and not callable(getattr(config, attr)):
                try:
                    config_data[attr] = getattr(config, attr)
                except:
                    pass
        
        return config_data

    def apply_config_data(self, config_data):
        """Apply configuration data to the config object"""
        for key, value in config_data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        # Refresh UI to reflect loaded settings
        self.refresh_all()
        
        # Update capture mode controls state to ensure UDP controls are properly shown/hidden
        # Call these in the correct order to avoid conflicts
        self._update_ndi_controls_state()
        self._update_capturecard_controls_state()
        self._update_udp_controls_state()
        
        # Ensure debug text info visibility is updated after all state changes
        # This is important to ensure the text info checkbox is properly shown/hidden
        try:
            self._update_debug_text_info_visibility()
        except Exception as e:
            print(f"[WARN] Failed to update debug text info visibility: {e}")

    def refresh_profile_list(self):
        """Refresh the profile dropdown list"""
        profiles = self.get_profile_list()
        self.profile_menu.configure(values=profiles)
        
        # Ensure current selection is still valid
        current = self.profile_var.get()
        if current not in profiles and profiles:
            self.profile_var.set(profiles[0])

    def save_profile(self):
        """Legacy method for backward compatibility"""
        self.save_current_profile()

    def load_profile(self):
        """Legacy method for backward compatibility"""
        self.load_selected_profile()


if __name__ == "__main__":
    app = EventuriGUI()
    app.mainloop()