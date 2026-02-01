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

from data_structures import ControllerData, CalibrationData
from network import NetworkHandler
from calibration import CalibrationManager, CalibrationDialog
from auto_calibration import AutoCalibrationWizard
from utilities import quaternion_conjugate, normalize_quaternion
from webcam_aruco_source import WebcamArucoSource
from src.gamepad_controller import GamepadControllerManager



class SourceMode:
    """Available source modes for ArUco tracking"""
    ANDROID_ONLY = "android_only"
    WEBCAM_ONLY = "webcam_only"
    BOTH = "both"


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
        # Controller data shared by all sources (0=LEFT, 1=RIGHT, 2=HMD)
        self.controllers = {
            0: ControllerData(0),
            1: ControllerData(1),
            2: ControllerData(2)
        }
        
        # Android calibration data - applied when source is Android UDP
        # Each controller can have different calibration for Android camera perspective
        self.calibrations_android = {
            0: CalibrationData(),
            1: CalibrationData(),
            2: CalibrationData()
        }
        
        # Webcam calibration data - applied when source is webcam
        # Separate because webcam may be mounted at different angle/position than phone
        # This allows optimal calibration for each camera setup independently
        self.calibrations_webcam = {
            0: CalibrationData(),
            1: CalibrationData(),
            2: CalibrationData()
        }
        
        self.network = NetworkHandler(log_callback=self.log)
        self.webcam_source: Optional[WebcamArucoSource] = None
        
        self.source_mode = SourceMode.ANDROID_ONLY
        self.webcam_camera_index = 0
        self.webcam_resolution = (640, 480)
        self.webcam_show_debug = True
        
        # General settings - shared across all sources
        self.general_settings = {
            'marker_size': 0.05,              # Physical size of ArUco markers in meters (used by webcam)
            'left_controller_id': 0,          # ArUco marker ID for left controller (enables multi-player)
            'right_controller_id': 1,         # ArUco marker ID for right controller
            'hmd_controller_id': 2            # ArUco marker ID for HMD/headset
            # Future: allows tracking multiple players with different marker IDs
        }
        
        self.source_priority = {0: "android", 1: "android", 2: "webcam"}
        
        self.running = False
        self.threads = []
        
        self.stats = {
            'android_packets': 0,
            'steamvr_packets': 0,
            'webcam_frames': 0,
            'webcam_detections': 0,
            'errors': 0
        }
        
        self.root: Optional[tk.Tk] = None
        self.log_widget: Optional[scrolledtext.ScrolledText] = None
        self.controller_labels = {}
        self.stats_label: Optional[ttk.Label] = None
        self.start_btn: Optional[ttk.Button] = None
        self.stop_btn: Optional[ttk.Button] = None
        self.source_mode_var: Optional[tk.StringVar] = None
        self.gamepad_manager: Optional[GamepadControllerManager] = None
        
        self.load_config()
    
    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        print(log_line.strip())
        if self.log_widget:
            self.log_widget.insert(tk.END, log_line)
            self.log_widget.see(tk.END)
    
    def load_config(self):
        """
        Load calibration and configuration from JSON file
        
        Loads:
        - Android calibration (backward compatible with v4.0 files)
        - Webcam calibration (new in v5.0, defaults to identity if not present)
        - Source configuration
        - General settings
        """
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Load Android calibration (keys "0", "1", "2")
                for cid in [0, 1, 2]:
                    cid_str = str(cid)
                    if cid_str in config:
                        cal_data = config[cid_str]
                        cal = self.calibrations_android[cid]
                        cal.position_offset = cal_data.get('position_offset', [0.0, 0.0, 0.0])
                        cal.position_scale = cal_data.get('position_scale', [1.0, 1.0, 1.0])
                        cal.axis_invert = cal_data.get('axis_invert', [False, False, False])
                        cal.rotation_invert = cal_data.get('rotation_invert', [False, False, False])
                        cal.rotation_offset_quat = cal_data.get('rotation_offset_quat', [1.0, 0.0, 0.0, 0.0])
                        cal.calibration_reference_position = cal_data.get('calibration_reference_position', [0.0, 0.0, 0.0])
                        cal.calibration_reference_rotation = cal_data.get('calibration_reference_rotation', [1.0, 0.0, 0.0, 0.0])
                
                # Load Webcam calibration (new in v5.0, may not exist in older configs)
                if 'webcam_calibration' in config:
                    for cid in [0, 1, 2]:
                        cid_str = str(cid)
                        if cid_str in config['webcam_calibration']:
                            cal_data = config['webcam_calibration'][cid_str]
                            cal = self.calibrations_webcam[cid]
                            cal.position_offset = cal_data.get('position_offset', [0.0, 0.0, 0.0])
                            cal.position_scale = cal_data.get('position_scale', [1.0, 1.0, 1.0])
                            cal.axis_invert = cal_data.get('axis_invert', [False, False, False])
                            cal.rotation_invert = cal_data.get('rotation_invert', [False, False, False])
                            cal.rotation_offset_quat = cal_data.get('rotation_offset_quat', [1.0, 0.0, 0.0, 0.0])
                            cal.calibration_reference_position = cal_data.get('calibration_reference_position', [0.0, 0.0, 0.0])
                            cal.calibration_reference_rotation = cal_data.get('calibration_reference_rotation', [1.0, 0.0, 0.0, 0.0])
                
                # Load source configuration
                if 'source_config' in config:
                    src_cfg = config['source_config']
                    self.source_mode = src_cfg.get('mode', SourceMode.ANDROID_ONLY)
                    self.webcam_camera_index = src_cfg.get('webcam_camera_index', 0)
                    self.webcam_resolution = tuple(src_cfg.get('webcam_resolution', [640, 480]))
                    self.webcam_show_debug = src_cfg.get('webcam_show_debug', True)
                    self.source_priority = src_cfg.get('source_priority', {0: "android", 1: "android", 2: "webcam"})
                    self.source_priority = {int(k): v for k, v in self.source_priority.items()}
                
                # Load general settings (new in v5.0)
                if 'general_settings' in config:
                    self.general_settings.update(config['general_settings'])
                
                self.log(f"✅ Config loaded from {self.CONFIG_FILE}")
            except Exception as e:
                self.log(f"❌ Error loading config: {e}", "ERROR")
    
    def save_config(self):
        """
        Save all calibration and configuration to JSON file
        
        Stores:
        - Android calibration for each controller (backward compatible with v4.0)
        - Webcam calibration for each controller (new in v5.0)
        - Source configuration (mode, camera settings)
        - General settings (marker size, controller IDs)
        
        Called automatically every 30 seconds and when calibration changes
        """
        try:
            config = {}
            
            # Save Android calibration (keys "0", "1", "2" for backward compatibility)
            for cid in [0, 1, 2]:
                cal = self.calibrations_android[cid]
                config[str(cid)] = {
                    'position_offset': cal.position_offset,
                    'position_scale': cal.position_scale,
                    'axis_invert': cal.axis_invert,
                    'rotation_invert': cal.rotation_invert,
                    'rotation_offset_quat': cal.rotation_offset_quat,
                    'calibration_reference_position': cal.calibration_reference_position,
                    'calibration_reference_rotation': cal.calibration_reference_rotation
                }
            
            # Save Webcam calibration (new section in v5.0)
            config['webcam_calibration'] = {}
            for cid in [0, 1, 2]:
                cal = self.calibrations_webcam[cid]
                config['webcam_calibration'][str(cid)] = {
                    'position_offset': cal.position_offset,
                    'position_scale': cal.position_scale,
                    'axis_invert': cal.axis_invert,
                    'rotation_invert': cal.rotation_invert,
                    'rotation_offset_quat': cal.rotation_offset_quat,
                    'calibration_reference_position': cal.calibration_reference_position,
                    'calibration_reference_rotation': cal.calibration_reference_rotation
                }
            
            # Save source configuration
            config['source_config'] = {
                'mode': self.source_mode,
                'webcam_camera_index': self.webcam_camera_index,
                'webcam_resolution': list(self.webcam_resolution),
                'webcam_show_debug': self.webcam_show_debug,
                'source_priority': self.source_priority
            }
            
            # Save general settings (new in v5.0)
            config['general_settings'] = self.general_settings
            
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.log(f"💾 Config saved to {self.CONFIG_FILE}")
        except Exception as e:
            self.log(f"❌ Error saving config: {e}", "ERROR")
    
    def start(self):
        if self.running:
            self.log("System already running", "WARN")
            return
        
        self.running = True
        self.threads = []
        
        marker_size = self.general_settings.get('marker_size', 0.05)
        
        if self.source_mode in [SourceMode.ANDROID_ONLY, SourceMode.BOTH]:
            thread = threading.Thread(target=self.start_android_receiver, daemon=True)
            thread.start()
            self.threads.append(thread)
        
        if self.source_mode in [SourceMode.WEBCAM_ONLY, SourceMode.BOTH]:
            self.webcam_source = WebcamArucoSource(
                camera_index=self.webcam_camera_index,
                resolution=self.webcam_resolution,
                marker_size=marker_size,
                show_debug_window=self.webcam_show_debug,
                log_callback=self.log
            )
            if not self.webcam_source.start():
                self.log("Failed to start webcam source", "ERROR")
                self.webcam_source = None
            else:
                thread = threading.Thread(target=self.webcam_update_loop, daemon=True)
                thread.start()
                self.threads.append(thread)
        
        if not self.network.setup_steamvr_sender():
            self.log("Failed to start SteamVR sender", "ERROR")
            self.stop()
            return
        
        self.gamepad_manager.start()
        
        thread = threading.Thread(target=self.steamvr_sender_loop, daemon=True)
        thread.start()
        self.threads.append(thread)
        
        self.log(f"✅ System started in {self.source_mode.upper()} mode")
    
    def stop(self):
        if not self.running:
            return
        
        self.running = False
        self.log("Stopping system...")
        
        if self.webcam_source:
            self.webcam_source.stop()
            self.webcam_source = None
        
        self.gamepad_manager.stop()
        self.network.close()
        
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
        
        In BOTH (hybrid) mode, implements source priority logic:
        - Each controller has a preferred source (android or webcam)
        - If preferred source has fresh data (< 500ms old), use it
        - Otherwise fall back to the other source
        - This provides automatic redundancy and failover
        """
        self.log("Webcam update loop started")
        
        while self.running and self.webcam_source:
            try:
                # Update each controller with webcam data
                for cid in [0, 1, 2]:
                    controller = self.controllers[cid]
                    
                    # In BOTH mode, respect source priority
                    if self.source_mode == SourceMode.BOTH:
                        # Check if preferred source is Android
                        preferred = self.source_priority.get(cid, "android")
                        
                        if preferred == "android":
                            # Android is preferred - only use webcam if Android data is stale
                            if controller.has_aruco(timeout=0.5):
                                continue  # Android data is fresh, skip webcam update
                        # If preferred is "webcam" or Android data is stale, use webcam below
                    
                    # Update from webcam (will set controller.source to "webcam:camN")
                    if self.webcam_source.update_controller_data(controller, max_age=0.5):
                        pass  # Data updated successfully
                
                # Update webcam statistics for display
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
        
        Applies appropriate calibration based on data source:
        - If controller.source contains "webcam" -> use webcam calibration
        - Otherwise -> use Android calibration
        
        Merges gamepad button data for LEFT and RIGHT controllers.
        """
        self.log("SteamVR sender started")
        
        while self.running:
            try:
                for cid in [0, 1, 2]:
                    controller = self.controllers[cid]
                    
                    # Select appropriate calibration based on active source
                    if "webcam" in controller.source:
                        calibration = self.calibrations_webcam[cid]
                    else:
                        calibration = self.calibrations_android[cid]
                    
                    # Apply calibration and send to SteamVR
                    CalibrationManager.apply_calibration(controller, calibration)
                
                # Merge gamepad button data for LEFT and RIGHT controllers
                for cid in [0, 1]:
                    buttons, trigger = self.gamepad_manager.get_button_state(cid)
                    self.controllers[cid].buttons = buttons
                    self.controllers[cid].trigger = trigger
                
                # Send all controllers to SteamVR
                for cid in [0, 1, 2]:
                    if self.network.send_to_steamvr(self.controllers[cid]):
                        self.stats['steamvr_packets'] += 1
                
                time.sleep(0.011)  # ~90 Hz update rate
                
            except Exception as e:
                self.log(f"SteamVR sender error: {e}", "ERROR")
                time.sleep(0.1)
        
        self.log("SteamVR sender stopped")
    
    def open_auto_calibration_android(self, controller_id: int):
        """
        Open automatic calibration wizard for Android source
        
        This calibration is applied when controller data comes from Android UDP source.
        Separate from webcam calibration to allow different camera perspectives.
        """
        device_names = ["LEFT controller", "RIGHT controller", "HMD"]
        
        # Check system is running
        if not self.running:
            messagebox.showwarning(
                "Warning",
                "Start tracking system before calibration (press 'Start' button)"
            )
            return
        
        # Check controller is active
        if not self.controllers[controller_id].has_aruco(timeout=2.0):
            messagebox.showerror(
                "Error",
                f"ArUco marker for {device_names[controller_id]} not visible!\n"
                "Make sure camera can see the marker."
            )
            return
        
        # Start calibration wizard for Android source
        wizard = AutoCalibrationWizard(
            controller_id=controller_id,
            controller_data=self.controllers[controller_id],
            calibration_data=self.calibrations_android[controller_id],
            log_callback=self.log
        )
        wizard.start_wizard(self.root)
        self.save_config()
    
    def open_manual_calibration_android(self, controller_id: int):
        """
        Open manual fine-tuning calibration dialog for Android source
        
        Allows manual adjustment of offset, scale, and axis inversions
        for Android camera tracking.
        """
        dialog = CalibrationDialog(
            controller_id=controller_id,
            calibration=self.calibrations_android[controller_id],
            controller=self.controllers[controller_id],
            apply_callback=lambda: None
        )
        dialog.create_dialog(self.root)
    
    def open_auto_calibration_webcam(self, controller_id: int):
        """
        Open automatic calibration wizard for Webcam source
        
        This calibration is applied when controller data comes from webcam source.
        Separate from Android calibration because webcam may have different
        perspective and mounting position than phone camera.
        """
        device_names = ["LEFT controller", "RIGHT controller", "HMD"]
        
        # Check system is running
        if not self.running:
            messagebox.showwarning(
                "Warning",
                "Start tracking system before calibration (press 'Start' button)"
            )
            return
        
        # Check controller is active
        if not self.controllers[controller_id].has_aruco(timeout=2.0):
            messagebox.showerror(
                "Error",
                f"ArUco marker for {device_names[controller_id]} not visible!\n"
                "Make sure webcam can see the marker."
            )
            return
        
        # Start calibration wizard for Webcam source
        wizard = AutoCalibrationWizard(
            controller_id=controller_id,
            controller_data=self.controllers[controller_id],
            calibration_data=self.calibrations_webcam[controller_id],
            log_callback=self.log
        )
        wizard.start_wizard(self.root)
        self.save_config()
    
    def open_manual_calibration_webcam(self, controller_id: int):
        """
        Open manual fine-tuning calibration dialog for Webcam source
        
        Allows manual adjustment of offset, scale, and axis inversions
        for webcam tracking.
        """
        dialog = CalibrationDialog(
            controller_id=controller_id,
            calibration=self.calibrations_webcam[controller_id],
            controller=self.controllers[controller_id],
            apply_callback=lambda: None
        )
        dialog.create_dialog(self.root)
    
    def reset_calibration_android(self, controller_id: int):
        device_names = ["LEFT", "RIGHT", "HMD"]
        if messagebox.askyesno("Reset Android Calibration", 
                               f"Reset Android calibration for {device_names[controller_id]}?"):
            self.calibrations_android[controller_id] = CalibrationData()
            self.log(f"🔄 {device_names[controller_id]}: Android calibration reset")
            self.save_config()
    
    def reset_calibration_webcam(self, controller_id: int):
        device_names = ["LEFT", "RIGHT", "HMD"]
        if messagebox.askyesno("Reset Webcam Calibration", 
                               f"Reset Webcam calibration for {device_names[controller_id]}?"):
            self.calibrations_webcam[controller_id] = CalibrationData()
            self.log(f"🔄 {device_names[controller_id]}: Webcam calibration reset")
            self.save_config()
    
    def apply_general_settings(self):
        try:
            self.general_settings['marker_size'] = float(self.marker_size_var.get())
            self.general_settings['left_controller_id'] = int(self.left_id_var.get())
            self.general_settings['right_controller_id'] = int(self.right_id_var.get())
            self.general_settings['hmd_controller_id'] = int(self.hmd_id_var.get())
            
            self.save_config()
            self.log("✅ General settings applied")
            
            if self.running and self.webcam_source:
                messagebox.showinfo("Restart Required", 
                                  "Settings changed. Restart system for changes to take effect.")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers.")
    
    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("VR Tracking Hub v5.0 - Multi-Source")
        self.root.geometry("1400x950")
        
        general_frame = ttk.LabelFrame(self.root, text="General Settings", padding=10)
        general_frame.pack(fill=tk.X, padx=10, pady=5)
        
        settings_row = ttk.Frame(general_frame)
        settings_row.pack(fill=tk.X, pady=5)
        
        ttk.Label(settings_row, text="Marker Size (m):").pack(side=tk.LEFT, padx=5)
        self.marker_size_var = tk.StringVar(value=str(self.general_settings['marker_size']))
        ttk.Entry(settings_row, textvariable=self.marker_size_var, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(settings_row, text="Left ID:").pack(side=tk.LEFT, padx=5)
        self.left_id_var = tk.StringVar(value=str(self.general_settings['left_controller_id']))
        ttk.Entry(settings_row, textvariable=self.left_id_var, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(settings_row, text="Right ID:").pack(side=tk.LEFT, padx=5)
        self.right_id_var = tk.StringVar(value=str(self.general_settings['right_controller_id']))
        ttk.Entry(settings_row, textvariable=self.right_id_var, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(settings_row, text="HMD ID:").pack(side=tk.LEFT, padx=5)
        self.hmd_id_var = tk.StringVar(value=str(self.general_settings['hmd_controller_id']))
        ttk.Entry(settings_row, textvariable=self.hmd_id_var, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(settings_row, text="💾 Apply", command=self.apply_general_settings).pack(side=tk.LEFT, padx=10)
        
        source_frame = ttk.LabelFrame(self.root, text="Source Configuration", padding=10)
        source_frame.pack(fill=tk.X, padx=10, pady=5)
        
        mode_frame = ttk.Frame(source_frame)
        mode_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(mode_frame, text="Tracking Source:", font=("", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        self.source_mode_var = tk.StringVar(value=self.source_mode)
        
        ttk.Radiobutton(mode_frame, text="📱 Android UDP", 
                       variable=self.source_mode_var, value=SourceMode.ANDROID_ONLY,
                       command=self.on_source_mode_changed).pack(side=tk.LEFT, padx=10)
        
        ttk.Radiobutton(mode_frame, text="📷 Webcam", 
                       variable=self.source_mode_var, value=SourceMode.WEBCAM_ONLY,
                       command=self.on_source_mode_changed).pack(side=tk.LEFT, padx=10)
        
        ttk.Radiobutton(mode_frame, text="🔄 Both", 
                       variable=self.source_mode_var, value=SourceMode.BOTH,
                       command=self.on_source_mode_changed).pack(side=tk.LEFT, padx=10)
        
        webcam_settings_frame = ttk.Frame(source_frame)
        webcam_settings_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(webcam_settings_frame, text="Webcam:").pack(side=tk.LEFT, padx=5)
        ttk.Label(webcam_settings_frame, text="Camera Index:").pack(side=tk.LEFT, padx=5)
        
        self.webcam_index_var = tk.StringVar(value=str(self.webcam_camera_index))
        ttk.Entry(webcam_settings_frame, textvariable=self.webcam_index_var, width=5).pack(side=tk.LEFT, padx=5)
        
        self.debug_window_var = tk.BooleanVar(value=self.webcam_show_debug)
        ttk.Checkbutton(webcam_settings_frame, text="Show Debug Window", 
                       variable=self.debug_window_var).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(webcam_settings_frame, text="💾 Apply", 
                  command=self.apply_webcam_settings).pack(side=tk.LEFT, padx=10)
        
        controllers_frame = ttk.LabelFrame(self.root, text="Controllers - Android Calibration", padding=10)
        controllers_frame.pack(fill=tk.X, padx=10, pady=5)
        
        device_names = ["LEFT Controller", "RIGHT Controller", "HMD (Head)"]
        
        for i, name in enumerate(device_names):
            frame = ttk.Frame(controllers_frame)
            frame.pack(fill=tk.X, pady=3)
            
            ttk.Label(frame, text=name, width=18, font=("", 9, "bold")).pack(side=tk.LEFT)
            
            status_label = ttk.Label(frame, text="Inactive", foreground="red", width=10)
            status_label.pack(side=tk.LEFT, padx=3)
            
            source_label = ttk.Label(frame, text="Src: N/A", width=16, font=("Courier", 8))
            source_label.pack(side=tk.LEFT, padx=3)
            
            pos_label = ttk.Label(frame, text="Pos: N/A", width=28, font=("Courier", 8))
            pos_label.pack(side=tk.LEFT, padx=3)
            
            ttk.Button(frame, text="🤖 Auto", width=9,
                      command=lambda cid=i: self.open_auto_calibration_android(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="⚙️ Manual", width=9,
                      command=lambda cid=i: self.open_manual_calibration_android(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="❌ Reset", width=8,
                      command=lambda cid=i: self.reset_calibration_android(cid)).pack(side=tk.LEFT, padx=2)
            
            self.controller_labels[i] = {
                'status': status_label,
                'source': source_label,
                'position': pos_label
            }
        
        webcam_cal_frame = ttk.LabelFrame(self.root, text="Controllers - Webcam Calibration", padding=10)
        webcam_cal_frame.pack(fill=tk.X, padx=10, pady=5)
        
        for i, name in enumerate(device_names):
            frame = ttk.Frame(webcam_cal_frame)
            frame.pack(fill=tk.X, pady=3)
            
            ttk.Label(frame, text=name, width=18, font=("", 9, "bold")).pack(side=tk.LEFT)
            
            ttk.Button(frame, text="🤖 Auto", width=9,
                      command=lambda cid=i: self.open_auto_calibration_webcam(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="⚙️ Manual", width=9,
                      command=lambda cid=i: self.open_manual_calibration_webcam(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="❌ Reset", width=8,
                      command=lambda cid=i: self.reset_calibration_webcam(cid)).pack(side=tk.LEFT, padx=2)
        
        stats_frame = ttk.LabelFrame(self.root, text="Statistics", padding=10)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.stats_label = ttk.Label(stats_frame, text="", font=("Courier", 9))
        self.stats_label.pack()
        
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
        
        ttk.Button(control_frame, text="🎮 Gamepad Config", 
                  command=self.open_gamepad_config, width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="🗑️ Clear Log", 
                  command=self.clear_log, width=15).pack(side=tk.LEFT, padx=5)
        
        log_frame = ttk.LabelFrame(self.root, text="Event Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=15, 
                                                     font=("Courier", 9), wrap=tk.WORD)
        self.log_widget.pack(fill=tk.BOTH, expand=True)
        
        self.gamepad_manager = GamepadControllerManager(log_callback=self.log)
        
        self.update_gui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.auto_save_config()
    
    def on_source_mode_changed(self):
        new_mode = self.source_mode_var.get()
        if self.running:
            messagebox.showinfo("Restart Required", 
                              "Source mode changed. Stop and restart for changes to take effect.")
        self.source_mode = new_mode
        self.save_config()
        self.log(f"Source mode changed to: {new_mode.upper()}")
    
    def apply_webcam_settings(self):
        try:
            self.webcam_camera_index = int(self.webcam_index_var.get())
            self.webcam_show_debug = self.debug_window_var.get()
            self.save_config()
            self.log("✅ Webcam settings applied")
            if self.running:
                messagebox.showinfo("Restart Required", 
                                  "Webcam settings changed. Stop and restart for changes to take effect.")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid camera index.")
    
    def update_gui(self):
        """
        Periodic GUI update (every 100ms)
        Updates controller status, source info, and statistics
        """
        if not self.root:
            return
        
        # Update each controller status
        for cid, labels in self.controller_labels.items():
            controller = self.controllers[cid]
            
            if controller.is_active():
                labels['status'].config(text="Active", foreground="green")
                
                # Show source with calibration indicator
                # Format: "Src: android:192.168.1.5 [A-Cal]" or "Src: webcam:cam0 [W-Cal]"
                if "webcam" in controller.source:
                    cal_indicator = "[W-Cal]"  # Using Webcam Calibration
                else:
                    cal_indicator = "[A-Cal]"  # Using Android Calibration
                
                labels['source'].config(text=f"Src: {controller.source} {cal_indicator}")
                
                # Show position
                pos = controller.position
                labels['position'].config(text=f"Pos: ({pos[0]:+.3f}, {pos[1]:+.3f}, {pos[2]:+.3f})")
            else:
                labels['status'].config(text="Inactive", foreground="red")
                labels['source'].config(text="Src: N/A")
                labels['position'].config(text="Pos: N/A")
        
        # Update statistics
        webcam_fps = self.webcam_source.get_fps() if self.webcam_source else 0.0
        stats_text = (
            f"Android: {self.stats['android_packets']:,} pkts | "
            f"Webcam: {self.stats['webcam_detections']:,} det @ {webcam_fps:.1f} FPS | "
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
    
    def open_gamepad_config(self):
        """Open gamepad configuration GUI."""
        self.gamepad_manager.open_configuration_gui(self.root)
        self.log("🎮 Gamepad configuration window opened")
    
    def clear_log(self):
        if self.log_widget:
            self.log_widget.delete('1.0', tk.END)
    
    def auto_save_config(self):
        if self.root:
            self.save_config()
            self.root.after(30000, self.auto_save_config)
    
    def on_closing(self):
        self.save_config()
        self.stop()
        if self.root:
            self.root.destroy()
    
    def run(self):
        self.create_gui()
        self.log("=" * 80)
        self.log("VR Tracking Hub v5.0 - Multi-Source")
        self.log("=" * 80)
        self.log(f"Current mode: {self.source_mode.upper()}")
        self.log(f"Marker size: {self.general_settings['marker_size']}m")
        self.log("")
        self.root.mainloop()


if __name__ == "__main__":
    hub = VRTrackingHub()
    try:
        hub.run()
    except KeyboardInterrupt:
        hub.stop()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()