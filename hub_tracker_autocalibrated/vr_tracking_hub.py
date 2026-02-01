#!/usr/bin/env python3
"""
Enhanced VR Tracking Hub v5.0 - Multi-Source Support

Major improvements in v5.0:
  ✨ NEW: Webcam ArUco tracking source support
  ✨ NEW: Flexible source selection (Android UDP, Webcam, or Both)
  ✨ NEW: Automatic fallback between sources
  ✨ NEW: Per-controller source priority
  ✨ Unified calibration system works with any source
  ✨ Real-time source monitoring and statistics
  
Source modes:
  - Android Only: Traditional UDP from phone app
  - Webcam Only: Computer webcam ArUco tracking
  - Both (Hybrid): Use both sources with priority/fallback logic
  
The calibration system is source-agnostic - all sources provide data in the
same format (aruco_position, aruco_quaternion) so calibration works identically.
"""
import os
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
from typing import Dict, Optional

# Import core modules
from data_structures import ControllerData, CalibrationData
from network import NetworkHandler
from calibration import CalibrationManager, CalibrationDialog
from auto_calibration import AutoCalibrationWizard
from utilities import quaternion_conjugate, normalize_quaternion

# Import webcam source
from webcam_aruco_source import WebcamArucoSource


class SourceMode:
    """Available source modes for ArUco tracking"""
    ANDROID_ONLY = "android_only"
    WEBCAM_ONLY = "webcam_only"
    BOTH = "both"  # Use both sources with priority logic


class VRTrackingHub:
    """
    Enhanced VR Tracking Hub with multi-source support
    
    Manages multiple input sources for ArUco marker tracking:
    1. Android UDP (port 5554) - Phone camera over network
    2. Webcam - Local computer camera
    3. Hybrid - Both sources with automatic fallback
    
    All sources feed into the same calibration pipeline and output
    to SteamVR driver (port 5555).
    """
    
    CONFIG_FILE = "vr_config.json"
    
    def __init__(self):
        """Initialize all components of the tracking system"""
        # Controller data (0=LEFT, 1=RIGHT, 2=HMD)
        self.controllers = {
            0: ControllerData(0),
            1: ControllerData(1),
            2: ControllerData(2)
        }
        
        # Calibration data for each controller
        self.calibrations = {
            0: CalibrationData(),
            1: CalibrationData(),
            2: CalibrationData()
        }
        
        # Network handler (Android UDP)
        self.network = NetworkHandler(log_callback=self.log)
        
        # Webcam ArUco source
        self.webcam_source: Optional[WebcamArucoSource] = None
        
        # Source configuration
        self.source_mode = SourceMode.ANDROID_ONLY  # Default to Android for backward compatibility
        self.webcam_camera_index = 0
        self.webcam_resolution = (640, 480)
        self.webcam_marker_size = 0.05  # 5cm markers
        self.webcam_show_debug = True
        
        # Per-controller source priority (only used in BOTH mode)
        # Format: {controller_id: "android" or "webcam"}
        # If source fails, automatically falls back to the other
        self.source_priority = {
            0: "android",  # LEFT prefers Android
            1: "android",  # RIGHT prefers Android
            2: "webcam"    # HMD prefers Webcam
        }
        
        # Thread control
        self.running = False
        self.threads = []
        
        # Statistics
        self.stats = {
            'android_packets': 0,
            'steamvr_packets': 0,
            'webcam_frames': 0,
            'webcam_detections': 0,
            'errors': 0
        }
        
        # GUI elements
        self.root: Optional[tk.Tk] = None
        self.log_widget: Optional[scrolledtext.ScrolledText] = None
        self.controller_labels = {}
        self.stats_label: Optional[ttk.Label] = None
        self.start_btn: Optional[ttk.Button] = None
        self.stop_btn: Optional[ttk.Button] = None
        self.source_mode_var: Optional[tk.StringVar] = None
        
        # Load configuration
        self.load_config()
    
    def log(self, message: str, level: str = "INFO"):
        """
        Log messages to console and GUI
        
        Args:
            message: Message text
            level: Log level (INFO, WARN, ERROR)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        # Console output
        print(log_line.strip())
        
        # GUI output
        if self.log_widget:
            self.log_widget.insert(tk.END, log_line)
            self.log_widget.see(tk.END)
    
    def load_config(self):
        """Load calibration and source settings from JSON file"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Load calibration for each controller
                for cid in [0, 1, 2]:
                    cid_str = str(cid)
                    if cid_str in config:
                        cal_data = config[cid_str]
                        cal = self.calibrations[cid]
                        
                        cal.position_offset = cal_data.get('position_offset', [0.0, 0.0, 0.0])
                        cal.position_scale = cal_data.get('position_scale', [1.0, 1.0, 1.0])
                        cal.axis_invert = cal_data.get('axis_invert', [False, False, False])
                        cal.rotation_invert = cal_data.get('rotation_invert', [False, False, False])
                        cal.rotation_offset_quat = cal_data.get('rotation_offset_quat', [1.0, 0.0, 0.0, 0.0])
                        cal.calibration_reference_position = cal_data.get('calibration_reference_position', [0.0, 0.0, 0.0])
                        cal.calibration_reference_rotation = cal_data.get('calibration_reference_rotation', [1.0, 0.0, 0.0, 0.0])
                
                # Load source configuration (new in v5.0)
                if 'source_config' in config:
                    src_cfg = config['source_config']
                    self.source_mode = src_cfg.get('mode', SourceMode.ANDROID_ONLY)
                    self.webcam_camera_index = src_cfg.get('webcam_camera_index', 0)
                    self.webcam_resolution = tuple(src_cfg.get('webcam_resolution', [640, 480]))
                    self.webcam_marker_size = src_cfg.get('webcam_marker_size', 0.05)
                    self.webcam_show_debug = src_cfg.get('webcam_show_debug', True)
                    self.source_priority = src_cfg.get('source_priority', {0: "android", 1: "android", 2: "webcam"})
                    # Convert string keys back to int
                    self.source_priority = {int(k): v for k, v in self.source_priority.items()}
                
                self.log(f"✅ Config loaded from {self.CONFIG_FILE}")
            except Exception as e:
                self.log(f"❌ Error loading config: {e}", "ERROR")
    
    def save_config(self):
        """Save all calibration and source settings to JSON file"""
        try:
            config = {}
            
            # Save calibration for each controller
            for cid in [0, 1, 2]:
                cal = self.calibrations[cid]
                config[str(cid)] = {
                    'position_offset': cal.position_offset,
                    'position_scale': cal.position_scale,
                    'axis_invert': cal.axis_invert,
                    'rotation_invert': cal.rotation_invert,
                    'rotation_offset_quat': cal.rotation_offset_quat,
                    'calibration_reference_position': cal.calibration_reference_position,
                    'calibration_reference_rotation': cal.calibration_reference_rotation
                }
            
            # Save source configuration (new in v5.0)
            config['source_config'] = {
                'mode': self.source_mode,
                'webcam_camera_index': self.webcam_camera_index,
                'webcam_resolution': list(self.webcam_resolution),
                'webcam_marker_size': self.webcam_marker_size,
                'webcam_show_debug': self.webcam_show_debug,
                'source_priority': self.source_priority
            }
            
            # Write to file
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.log(f"💾 Config saved to {self.CONFIG_FILE}")
        except Exception as e:
            self.log(f"❌ Error saving config: {e}", "ERROR")
    
    def start(self):
        """Start all tracking sources and processing threads"""
        if self.running:
            self.log("System already running", "WARN")
            return
        
        self.running = True
        self.threads = []
        
        # Start sources based on mode
        if self.source_mode in [SourceMode.ANDROID_ONLY, SourceMode.BOTH]:
            # Start Android UDP receiver
            thread = threading.Thread(target=self.start_android_receiver, daemon=True)
            thread.start()
            self.threads.append(thread)
        
        if self.source_mode in [SourceMode.WEBCAM_ONLY, SourceMode.BOTH]:
            # Start webcam source
            self.webcam_source = WebcamArucoSource(
                camera_index=self.webcam_camera_index,
                resolution=self.webcam_resolution,
                marker_size=self.webcam_marker_size,
                show_debug_window=self.webcam_show_debug,
                log_callback=self.log
            )
            if not self.webcam_source.start():
                self.log("Failed to start webcam source", "ERROR")
                self.webcam_source = None
            else:
                # Start webcam data update thread
                thread = threading.Thread(target=self.webcam_update_loop, daemon=True)
                thread.start()
                self.threads.append(thread)
        
        # Start SteamVR sender
        if not self.network.setup_steamvr_sender():
            self.log("Failed to start SteamVR sender", "ERROR")
            self.stop()
            return
        
        thread = threading.Thread(target=self.steamvr_sender_loop, daemon=True)
        thread.start()
        self.threads.append(thread)
        
        self.log(f"✅ System started in {self.source_mode.upper()} mode")
    
    def stop(self):
        """Stop all threads and sources"""
        if not self.running:
            return
        
        self.running = False
        self.log("Stopping system...")
        
        # Stop webcam source if running
        if self.webcam_source:
            self.webcam_source.stop()
            self.webcam_source = None
        
        # Close network sockets
        self.network.close()
        
        # Wait for threads
        for thread in self.threads:
            thread.join(timeout=1.0)
        
        self.threads = []
        self.log("✅ System stopped")
    
    def start_android_receiver(self):
        """
        Thread: Receive and process data from Android UDP source
        Updates controller aruco_position and aruco_quaternion fields
        """
        if not self.network.setup_android_receiver():
            return
        
        self.log("Android receiver started")
        
        while self.running:
            result = self.network.receive_from_android()
            if not result:
                continue
            
            data, addr = result
            parsed = self.network.parse_aruco_packet(data)
            
            if not parsed:
                self.stats['errors'] += 1
                continue
            
            cid = parsed['controller_id']
            if cid not in self.controllers:
                continue
            
            controller = self.controllers[cid]
            
            # Update ArUco marker data from Android
            controller.aruco_position = parsed['marker_position']
            controller.aruco_quaternion = parsed['marker_quaternion']
            controller.aruco_last_update = time.time()
            
            # Update other sensor data
            controller.gyro = parsed['gyro']
            controller.buttons = parsed['buttons']
            controller.trigger = parsed['trigger']
            controller.packet_number = parsed['packet_number']
            controller.last_update = time.time()
            controller.source = f"android:{addr[0]}"
            
            self.stats['android_packets'] += 1
        
        self.log("Android receiver stopped")
    
    def webcam_update_loop(self):
        """
        Thread: Update controller data from webcam source
        Runs at ~60 Hz to keep data fresh
        """
        self.log("Webcam update loop started")
        
        while self.running and self.webcam_source:
            try:
                # Update each controller with webcam data
                for cid in [0, 1, 2]:
                    controller = self.controllers[cid]
                    
                    # In BOTH mode, respect source priority
                    if self.source_mode == SourceMode.BOTH:
                        # Only update from webcam if:
                        # 1. Webcam is preferred source for this controller, OR
                        # 2. Preferred source (Android) has no fresh data
                        preferred = self.source_priority.get(cid, "android")
                        
                        if preferred == "android":
                            # Android is preferred - only use webcam if Android data is stale
                            if controller.has_aruco(timeout=0.5):
                                continue  # Android data is fresh, skip webcam
                        # If preferred is "webcam" or Android data is stale, use webcam below
                    
                    # Update from webcam
                    if self.webcam_source.update_controller_data(controller, max_age=0.5):
                        # Data was updated
                        pass
                
                # Update statistics
                if self.webcam_source:
                    stats = self.webcam_source.get_stats()
                    self.stats['webcam_frames'] = stats['frame_count']
                    self.stats['webcam_detections'] = stats['detection_count']
                
                time.sleep(0.016)  # ~60 Hz
                
            except Exception as e:
                self.log(f"Webcam update error: {e}", "ERROR")
                time.sleep(0.1)
        
        self.log("Webcam update loop stopped")
    
    def steamvr_sender_loop(self):
        """
        Thread: Send calibrated data to SteamVR driver
        Applies calibration and sends at ~90 Hz
        """
        self.log("SteamVR sender started")
        
        while self.running:
            try:
                for cid in [0, 1, 2]:
                    controller = self.controllers[cid]
                    calibration = self.calibrations[cid]
                    
                    # Apply calibration to ArUco data
                    CalibrationManager.apply_calibration(controller, calibration)
                    
                    # Send to SteamVR
                    if self.network.send_to_steamvr(controller):
                        self.stats['steamvr_packets'] += 1
                
                time.sleep(0.011)  # ~90 Hz
                
            except Exception as e:
                self.log(f"SteamVR sender error: {e}", "ERROR")
                time.sleep(0.1)
        
        self.log("SteamVR sender stopped")
    
    # ─────────────────────────────────────────────────────────────────────
    # Calibration methods (unchanged from v4.0)
    # ─────────────────────────────────────────────────────────────────────
    
    def open_auto_calibration(self, controller_id: int):
        """Open automatic calibration wizard"""
        if not self.root:
            return
        
        wizard = AutoCalibrationWizard(
            controller_id=controller_id,
            controller=self.controllers[controller_id],
            calibration=self.calibrations[controller_id],
            parent=self.root,
            log_callback=self.log
        )
        wizard.run()
        self.save_config()
    
    def open_manual_calibration(self, controller_id: int):
        """Open manual calibration dialog"""
        if not self.root:
            return
        
        dialog = CalibrationDialog(
            controller_id=controller_id,
            calibration=self.calibrations[controller_id],
            controller=self.controllers[controller_id],
            apply_callback=lambda: None  # Calibration is applied in real-time
        )
        dialog.create_dialog(self.root)
    
    def calibrate_rotation(self, controller_id: int):
        """Quick rotation calibration - set current orientation as identity"""
        device_names = ["LEFT", "RIGHT", "HMD"]
        controller = self.controllers[controller_id]
        
        if not controller.has_aruco():
            messagebox.showwarning(
                "No Data",
                f"{device_names[controller_id]}: Marker not visible. Cannot calibrate rotation."
            )
            return
        
        # Store current rotation as reference
        self.calibrations[controller_id].rotation_offset_quat = controller.aruco_quaternion.copy()
        self.calibrations[controller_id].calibration_reference_rotation = controller.aruco_quaternion.copy()
        
        self.log(f"✅ {device_names[controller_id]}: Rotation calibration completed")
        self.save_config()
    
    def reset_calibration(self, controller_id: int):
        """Reset calibration to defaults"""
        device_names = ["LEFT", "RIGHT", "HMD"]
        
        if messagebox.askyesno(
            "Reset Calibration",
            f"Reset all calibration for {device_names[controller_id]} to default values?"
        ):
            self.calibrations[controller_id] = CalibrationData()
            self.log(f"🔄 {device_names[controller_id]}: Calibration reset")
            self.save_config()
    
    # ─────────────────────────────────────────────────────────────────────
    # GUI
    # ─────────────────────────────────────────────────────────────────────
    
    def create_gui(self):
        """Create main GUI window with source selection"""
        self.root = tk.Tk()
        self.root.title("VR Tracking Hub v5.0 - Multi-Source Support")
        self.root.geometry("1400x900")
        
        # ═══ SOURCE SELECTION SECTION ═══
        source_frame = ttk.LabelFrame(self.root, text="Source Configuration", padding=10)
        source_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Source mode selection
        mode_frame = ttk.Frame(source_frame)
        mode_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(mode_frame, text="Tracking Source:", font=("", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        self.source_mode_var = tk.StringVar(value=self.source_mode)
        
        ttk.Radiobutton(mode_frame, text="📱 Android UDP Only", 
                       variable=self.source_mode_var, value=SourceMode.ANDROID_ONLY,
                       command=self.on_source_mode_changed).pack(side=tk.LEFT, padx=10)
        
        ttk.Radiobutton(mode_frame, text="📷 Webcam Only", 
                       variable=self.source_mode_var, value=SourceMode.WEBCAM_ONLY,
                       command=self.on_source_mode_changed).pack(side=tk.LEFT, padx=10)
        
        ttk.Radiobutton(mode_frame, text="🔄 Both (Hybrid)", 
                       variable=self.source_mode_var, value=SourceMode.BOTH,
                       command=self.on_source_mode_changed).pack(side=tk.LEFT, padx=10)
        
        # Webcam settings
        webcam_settings_frame = ttk.Frame(source_frame)
        webcam_settings_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(webcam_settings_frame, text="Webcam Settings:").pack(side=tk.LEFT, padx=5)
        ttk.Label(webcam_settings_frame, text="Camera Index:").pack(side=tk.LEFT, padx=5)
        
        self.webcam_index_var = tk.StringVar(value=str(self.webcam_camera_index))
        ttk.Entry(webcam_settings_frame, textvariable=self.webcam_index_var, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(webcam_settings_frame, text="Marker Size (m):").pack(side=tk.LEFT, padx=5)
        self.marker_size_var = tk.StringVar(value=str(self.webcam_marker_size))
        ttk.Entry(webcam_settings_frame, textvariable=self.marker_size_var, width=8).pack(side=tk.LEFT, padx=5)
        
        self.debug_window_var = tk.BooleanVar(value=self.webcam_show_debug)
        ttk.Checkbutton(webcam_settings_frame, text="Show Debug Window", 
                       variable=self.debug_window_var).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(webcam_settings_frame, text="💾 Apply Settings", 
                  command=self.apply_webcam_settings).pack(side=tk.LEFT, padx=10)
        
        # ═══ CONTROLLERS SECTION ═══
        controllers_frame = ttk.LabelFrame(self.root, text="Controllers & Calibration", padding=10)
        controllers_frame.pack(fill=tk.X, padx=10, pady=5)
        
        device_names = ["LEFT Controller", "RIGHT Controller", "HMD (Head)"]
        
        for i, name in enumerate(device_names):
            frame = ttk.Frame(controllers_frame)
            frame.pack(fill=tk.X, pady=5)
            
            # Device name
            ttk.Label(frame, text=name, width=18, font=("", 10, "bold")).pack(side=tk.LEFT)
            
            # Activity status
            status_label = ttk.Label(frame, text="Inactive", foreground="red", width=12)
            status_label.pack(side=tk.LEFT, padx=3)
            
            # Source indicator
            source_label = ttk.Label(frame, text="Source: N/A", width=18, font=("Courier", 9))
            source_label.pack(side=tk.LEFT, padx=3)
            
            # Current position
            pos_label = ttk.Label(frame, text="Pos: N/A", width=30, font=("Courier", 9))
            pos_label.pack(side=tk.LEFT, padx=3)
            
            # Calibration buttons
            ttk.Button(frame, text="🤖 Auto-Cal", width=11,
                      command=lambda cid=i: self.open_auto_calibration(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="⚙️ Manual", width=11,
                      command=lambda cid=i: self.open_manual_calibration(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="🔄 Cal Rot", width=11,
                      command=lambda cid=i: self.calibrate_rotation(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="❌ Reset", width=9,
                      command=lambda cid=i: self.reset_calibration(cid)).pack(side=tk.LEFT, padx=2)
            
            self.controller_labels[i] = {
                'status': status_label,
                'source': source_label,
                'position': pos_label
            }
        
        # ═══ STATISTICS SECTION ═══
        stats_frame = ttk.LabelFrame(self.root, text="Statistics", padding=10)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.stats_label = ttk.Label(stats_frame, text="", font=("Courier", 10))
        self.stats_label.pack()
        
        # ═══ CONTROL BUTTONS ═══
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.start_btn = ttk.Button(control_frame, text="▶️ Start", 
                                     command=self.start, width=15)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="⏹️ Stop", 
                                    command=self.stop, state=tk.DISABLED, width=15)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="💾 Save Config", 
                  command=self.save_config, width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="🗑️ Clear Log", 
                  command=self.clear_log, width=15).pack(side=tk.LEFT, padx=5)
        
        # ═══ LOG AREA ═══
        log_frame = ttk.LabelFrame(self.root, text="Event Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=20, 
                                                     font=("Courier", 9), wrap=tk.WORD)
        self.log_widget.pack(fill=tk.BOTH, expand=True)
        
        # Start periodic GUI update
        self.update_gui()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Auto-save config
        self.auto_save_config()
    
    def on_source_mode_changed(self):
        """Handle source mode radio button change"""
        new_mode = self.source_mode_var.get()
        
        if self.running:
            messagebox.showinfo(
                "Restart Required",
                "Source mode changed. Please stop and restart the system for changes to take effect."
            )
        
        self.source_mode = new_mode
        self.save_config()
        self.log(f"Source mode changed to: {new_mode.upper()}")
    
    def apply_webcam_settings(self):
        """Apply webcam settings from GUI"""
        try:
            self.webcam_camera_index = int(self.webcam_index_var.get())
            self.webcam_marker_size = float(self.marker_size_var.get())
            self.webcam_show_debug = self.debug_window_var.get()
            
            self.save_config()
            self.log("✅ Webcam settings applied")
            
            if self.running:
                messagebox.showinfo(
                    "Restart Required",
                    "Webcam settings changed. Please stop and restart the system for changes to take effect."
                )
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers for camera index and marker size.")
    
    def update_gui(self):
        """Periodic GUI update (every 100ms)"""
        if not self.root:
            return
        
        # Update controller status
        for cid, labels in self.controller_labels.items():
            controller = self.controllers[cid]
            
            if controller.is_active():
                labels['status'].config(text="Active", foreground="green")
                labels['source'].config(text=f"Source: {controller.source}")
                pos = controller.position
                labels['position'].config(
                    text=f"Pos: ({pos[0]:+.3f}, {pos[1]:+.3f}, {pos[2]:+.3f})"
                )
            else:
                labels['status'].config(text="Inactive", foreground="red")
                labels['source'].config(text="Source: N/A")
                labels['position'].config(text="Pos: N/A")
        
        # Update statistics
        webcam_fps = self.webcam_source.get_fps() if self.webcam_source else 0.0
        stats_text = (
            f"Android: {self.stats['android_packets']:,} pkts | "
            f"Webcam: {self.stats['webcam_detections']:,} detections @ {webcam_fps:.1f} FPS | "
            f"SteamVR: {self.stats['steamvr_packets']:,} pkts | "
            f"Errors: {self.stats['errors']}"
        )
        self.stats_label.config(text=stats_text)
        
        # Update button states
        if self.running:
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
        
        # Schedule next update
        self.root.after(100, self.update_gui)
    
    def clear_log(self):
        """Clear log text"""
        if self.log_widget:
            self.log_widget.delete('1.0', tk.END)
    
    def auto_save_config(self):
        """Auto-save configuration every 30 seconds"""
        if self.root:
            self.save_config()
            self.root.after(30000, self.auto_save_config)
    
    def on_closing(self):
        """Handle application closing"""
        self.save_config()
        self.stop()
        if self.root:
            self.root.destroy()
    
    def run(self):
        """Start application with GUI"""
        self.create_gui()
        
        # Welcome messages
        self.log("=" * 80)
        self.log("VR Tracking Hub v5.0 - Multi-Source Support")
        self.log("=" * 80)
        self.log("")
        self.log("📋 Quick Start:")
        self.log("   1. Select tracking source: Android UDP, Webcam, or Both")
        self.log("   2. Configure webcam settings if using webcam source")
        self.log("   3. Press '▶️ Start' to begin tracking")
        self.log("   4. Use '🤖 Auto-Cal' for automatic calibration")
        self.log("")
        self.log(f"📁 Config file: {self.CONFIG_FILE}")
        self.log(f"📡 Current source mode: {self.source_mode.upper()}")
        self.log("")
        
        # Start main loop
        self.root.mainloop()


if __name__ == "__main__":
    """Program entry point"""
    print("=" * 80)
    print("VR Tracking Hub v5.0 - Multi-Source ArUco Tracking System")
    print("=" * 80)
    print()
    
    hub = VRTrackingHub()
    
    try:
        hub.run()
    except KeyboardInterrupt:
        print("\nUser interrupt...")
        hub.stop()
    except Exception as e:
        print(f"Critical error: {e}")
        import traceback
        traceback.print_exc()