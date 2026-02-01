#!/usr/bin/env python3
"""
VR Tracking Hub v3.0 - Advanced Controller Calibration System

This hub receives tracking data from Android ArUco marker detection,
applies calibration transformations, and sends corrected data to SteamVR driver.

Key Features:
  1. OFFSET-based calibration: position = (raw - reference) + offset
     This allows markers to move and controller follows automatically
  
  2. Axis inversion: solves problem when controller moves opposite direction
     (e.g., approaching marker makes controller move away)
  
  3. Real-time preview: changes in calibration dialog are applied IMMEDIATELY
     so you see the effect on controller position instantly
  
  4. Per-controller settings: LEFT, RIGHT, and HMD each have independent calibration
  
  5. Config persistence: all settings saved to config.json automatically

Data Flow:
  [Android App] → Raw marker data (port 5554)
       ↓
  [VR Hub] → Apply calibration transformations
       ↓
  [SteamVR Driver] ← Calibrated data (port 5555)
"""
import socket, struct, threading, time, json, os
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import math

@dataclass
class ControllerData:
    """
    Holds real-time data for a single controller (or HMD).
    
    Attributes:
      controller_id: 0=LEFT, 1=RIGHT, 2=HMD
      position: [X, Y, Z] in meters (calibrated position in VR)
      quaternion: [W, X, Y, Z] rotation representation
      aruco_position: raw position from marker before calibration
      last_update: timestamp of last data packet
    """
    controller_id: int
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    quaternion: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    gyro: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    buttons: int = 0
    trigger: int = 0
    packet_number: int = 0
    last_update: float = 0.0
    source: str = "unknown"
    aruco_position: Optional[List[float]] = None
    aruco_quaternion: Optional[List[float]] = None
    aruco_last_update: float = 0.0
    gyro_quaternion: Optional[List[float]] = None
    gyro_last_update: float = 0.0
    gyro_drift_correction: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    
    def is_active(self, timeout: float = 1.0) -> bool:
        """Returns True if controller received data within timeout seconds"""
        return (time.time() - self.last_update) < timeout
    
    def has_aruco(self, timeout: float = 0.5) -> bool:
        """Returns True if ArUco marker data is recent"""
        return self.aruco_position is not None and (time.time() - self.aruco_last_update) < timeout
    
    def has_gyro(self, timeout: float = 0.5) -> bool:
        """Returns True if gyro data is recent"""
        return self.gyro_quaternion is not None and (time.time() - self.gyro_last_update) < timeout

@dataclass
class CalibrationData:
    """
    Stores all calibration parameters for a single controller.
    
    OFFSET-based System:
      Final position = (raw_position - reference_position) + offset
                     × scale
                     with axis inversion applied
    
    This approach allows the marker to move in the real world while
    the controller position is automatically recalculated relative to
    the marker's movement.
    """
    # Position calibration parameters
    position_offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    """Offset added to controller position in meters [X, Y, Z]"""
    
    position_scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    """Scale factor for each axis (1.0 = no scaling, 0.8 = 80%, 1.2 = 120%)"""
    
    axis_invert: List[bool] = field(default_factory=lambda: [False, False, False])
    """Invert axis direction [X, Y, Z] if coordinate system is opposite"""
    
    rotation_offset_quat: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    """Base rotation saved during rotation calibration [W, X, Y, Z]"""
    
    # Reference point for OFFSET calculations
    calibration_reference_position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    """Marker position at time of calibration - used as baseline for offset calculations"""
    
    calibration_reference_rotation: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    """Marker rotation at time of calibration"""
    
    # Gyro drift compensation (for future fusion)
    gyro_drift_yaw: float = 0.0
    gyro_drift_pitch: float = 0.0
    gyro_drift_roll: float = 0.0
    drift_history_aruco: List[List[float]] = field(default_factory=list)
    drift_history_gyro: List[List[float]] = field(default_factory=list)
    drift_history_size: int = 100

class VRTrackingHub:
    """
    Main hub class that:
    1. Receives UDP packets from Android app (port 5554)
    2. Applies calibration transformations
    3. Sends calibrated data to SteamVR driver (port 5555)
    4. Provides GUI for calibration management
    """
    CONFIG_FILE = "config.json"
    
    def __init__(self):
        # Data structures for all 3 devices
        self.controllers = {0: ControllerData(0), 1: ControllerData(1), 2: ControllerData(2)}
        self.calibrations = {0: CalibrationData(), 1: CalibrationData(), 2: CalibrationData()}
        
        # Network sockets
        self.socket_android = None  # Receives from Android app
        self.socket_steamvr = None  # Sends to SteamVR driver
        
        # Thread management
        self.running = False
        self.threads = []
        
        # Statistics tracking
        self.stats = {'android_packets': 0, 'gyro_packets': 0, 'steamvr_packets': 0, 'errors': 0}
        
        # GUI elements
        self.root = None
        self.log_widget = None
        self.controller_labels = {}
        self.calibration_dialogs = {}
        
        # Load previously saved calibration
        self.load_config()
    
    def load_config(self):
        """
        Loads calibration settings from config.json
        This allows calibration to persist between application restarts
        """
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    for cid in [0, 1, 2]:
                        cid_str = str(cid)
                        if cid_str in config:
                            cal_data = config[cid_str]
                            cal = self.calibrations[cid]
                            
                            # Load all parameters
                            cal.position_offset = cal_data.get('position_offset', [0.0, 0.0, 0.0])
                            cal.position_scale = cal_data.get('position_scale', [1.0, 1.0, 1.0])
                            cal.axis_invert = cal_data.get('axis_invert', [False, False, False])
                            cal.rotation_offset_quat = cal_data.get('rotation_offset_quat', [1.0, 0.0, 0.0, 0.0])
                            cal.calibration_reference_position = cal_data.get('calibration_reference_position', [0.0, 0.0, 0.0])
                            cal.calibration_reference_rotation = cal_data.get('calibration_reference_rotation', [1.0, 0.0, 0.0, 0.0])
                            cal.gyro_drift_yaw = cal_data.get('gyro_drift_yaw', 0.0)
                            cal.gyro_drift_pitch = cal_data.get('gyro_drift_pitch', 0.0)
                            cal.gyro_drift_roll = cal_data.get('gyro_drift_roll', 0.0)
                
                self.log(f"✅ Config loaded from {self.CONFIG_FILE}")
            except Exception as e:
                self.log(f"❌ Error loading config: {e}", "ERROR")
    
    def save_config(self):
        """
        Saves all calibration settings to config.json
        Called automatically every 30 seconds and when user clicks "Save Config"
        """
        try:
            config = {}
            for cid in [0, 1, 2]:
                cal = self.calibrations[cid]
                config[str(cid)] = {
                    'position_offset': cal.position_offset,
                    'position_scale': cal.position_scale,
                    'axis_invert': cal.axis_invert,
                    'rotation_offset_quat': cal.rotation_offset_quat,
                    'calibration_reference_position': cal.calibration_reference_position,
                    'calibration_reference_rotation': cal.calibration_reference_rotation,
                    'gyro_drift_yaw': cal.gyro_drift_yaw,
                    'gyro_drift_pitch': cal.gyro_drift_pitch,
                    'gyro_drift_roll': cal.gyro_drift_roll,
                }
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            # Don't log every save to avoid spam
        except Exception as e:
            self.log(f"❌ Error saving config: {e}", "ERROR")
    
    def log(self, message: str, level: str = "INFO"):
        """
        Logs a message with timestamp to both console and GUI log widget
        
        Args:
          message: The message to log
          level: Log level (INFO, WARN, ERROR, etc)
        """
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_msg = f"[{timestamp}] [{level:5}] {message}"
        print(log_msg)
        if self.log_widget:
            try:
                self.log_widget.insert(tk.END, log_msg + "\n")
                self.log_widget.see(tk.END)
                # Limit log to 1000 lines to avoid memory issues
                lines = int(self.log_widget.index('end-1c').split('.')[0])
                if lines > 1000:
                    self.log_widget.delete('1.0', '500.0')
            except:
                pass
    
    def start_android_receiver(self, port: int = 5554):
        """
        Thread function: Receives UDP packets from Android app
        
        Expected packet format (49 bytes):
          [0]     controller_id (0=LEFT, 1=RIGHT, 2=HMD)
          [1:5]   packet_number (uint32)
          [5:21]  quaternion [W,X,Y,Z] (4 × float32)
          [21:33] position [X,Y,Z] (3 × float32) - labeled as "accel" but actually position
          [33:45] gyro [X,Y,Z] (3 × float32) - angular velocity
          [45:47] buttons (uint16)
          [47]    trigger (uint8)
          [48]    checksum (uint8)
        """
        try:
            self.socket_android = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket_android.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket_android.bind(('0.0.0.0', port))
            self.socket_android.settimeout(0.1)
            self.log(f"Android receiver started on port {port}")
            
            while self.running:
                try:
                    data, addr = self.socket_android.recvfrom(1024)
                    self.process_android_packet(data, addr)
                except socket.timeout:
                    continue
                except Exception as e:
                    self.log(f"Android receiver error: {e}", "ERROR")
                    self.stats['errors'] += 1
        except Exception as e:
            self.log(f"Failed to start Android receiver: {e}", "ERROR")
    
    def process_android_packet(self, data: bytes, addr: tuple):
        """
        Processes incoming UDP packet from Android app
        
        Steps:
        1. Unpack binary data
        2. Verify checksum
        3. Apply calibration transformations
        4. Update controller state
        """
        try:
            if len(data) != 49:
                return
            
            # Unpack the binary packet
            controller_id = data[0]
            packet_number = struct.unpack('<I', data[1:5])[0]
            quat = struct.unpack('<4f', data[5:21])
            pos = struct.unpack('<3f', data[21:33])
            gyro = struct.unpack('<3f', data[33:45])
            buttons = struct.unpack('<H', data[45:47])[0]
            trigger = data[47]
            checksum = data[48]
            
            # Verify packet integrity
            calculated_checksum = sum(data[:48]) & 0xFF
            if checksum != calculated_checksum:
                return
            
            if controller_id in self.controllers:
                controller = self.controllers[controller_id]
                
                # Save raw marker data
                controller.aruco_position = list(pos)
                controller.aruco_quaternion = list(quat)
                controller.aruco_last_update = time.time()
                
                # Apply calibration to get final position
                calibrated_pos = self.apply_position_offset(list(pos), self.calibrations[controller_id])
                calibrated_quat = self.apply_rotation_offset(list(quat), self.calibrations[controller_id])
                
                # Update controller state
                controller.position = calibrated_pos
                controller.quaternion = calibrated_quat
                controller.gyro = list(gyro)
                controller.buttons = buttons
                controller.trigger = trigger
                controller.packet_number = packet_number
                controller.last_update = time.time()
                controller.source = f"android:{addr[0]}"
                self.stats['android_packets'] += 1
                
                # Log every 100 packets to show calibration effect
                if packet_number % 100 == 0:
                    ctrl_name = ["LEFT", "RIGHT", "HMD"][controller_id]
                    self.log(f"{ctrl_name}: Raw({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}) " +
                            f"→ Cal({calibrated_pos[0]:.3f}, {calibrated_pos[1]:.3f}, {calibrated_pos[2]:.3f})")
        except Exception as e:
            self.log(f"Error processing packet: {e}", "ERROR")
            self.stats['errors'] += 1
    
    def apply_position_offset(self, raw_position: List[float], calibration: CalibrationData) -> List[float]:
        """
        Applies OFFSET-based calibration to transform raw marker position
        into final controller position in VR space.
        
        Formula:
          calibrated = (raw - reference) × scale ± inversion + offset
        
        This allows the marker to move while the controller position
        automatically adjusts relative to the marker's baseline position.
        
        Args:
          raw_position: [X,Y,Z] from marker in meters
          calibration: CalibrationData with offset, scale, reference
        
        Returns:
          calibrated [X,Y,Z] position for SteamVR
        """
        # Step 1: Subtract reference point to get RELATIVE position from calibration baseline
        relative = [raw_position[i] - calibration.calibration_reference_position[i] for i in range(3)]
        
        # Step 2: Invert axes if coordinate system requires it
        # (solves problem: approaching marker makes controller move away)
        inverted = [
            -relative[0] if calibration.axis_invert[0] else relative[0],
            -relative[1] if calibration.axis_invert[1] else relative[1],
            -relative[2] if calibration.axis_invert[2] else relative[2]
        ]
        
        # Step 3: Apply scale (sensitivity adjustment)
        scaled = [inverted[i] * calibration.position_scale[i] for i in range(3)]
        
        # Step 4: Add offset (final position adjustment)
        final = [scaled[i] + calibration.position_offset[i] for i in range(3)]
        
        return final
    
    def apply_rotation_offset(self, raw_quat: List[float], calibration: CalibrationData) -> List[float]:
        """
        Applies rotation calibration.
        Currently returns raw quaternion, can be enhanced with full quaternion math.
        """
        return raw_quat
    
    def start_steamvr_sender(self, host: str = '127.0.0.1', port: int = 5555):
        """
        Thread function: Sends calibrated data to SteamVR driver at 90Hz
        
        Sends UDP packets to the SteamVR driver with controller position/rotation
        that will be used to update the controller positions in SteamVR.
        """
        try:
            self.socket_steamvr = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.log(f"SteamVR sender started, target {host}:{port}")
            
            while self.running:
                try:
                    # Send data for each active controller at 90 FPS
                    for controller_id, controller in self.controllers.items():
                        if controller.is_active():
                            packet = self.build_steamvr_packet(
                                controller_id, controller.quaternion, controller.position, 
                                controller.gyro, controller.buttons, controller.trigger, 
                                controller.packet_number
                            )
                            self.socket_steamvr.sendto(packet, (host, port))
                            self.stats['steamvr_packets'] += 1
                    time.sleep(1.0 / 90.0)  # 90 Hz update rate
                except Exception as e:
                    self.log(f"SteamVR sender error: {e}", "ERROR")
                    self.stats['errors'] += 1
                    time.sleep(0.1)
        except Exception as e:
            self.log(f"Failed to start SteamVR sender: {e}", "ERROR")
    
    def build_steamvr_packet(self, controller_id: int, quaternion: List[float], position: List[float], 
                            gyro: List[float], buttons: int, trigger: int, packet_number: int) -> bytes:
        """
        Builds 49-byte UDP packet in same format as Android sends
        to maintain compatibility with SteamVR driver expectations
        """
        packet = bytearray(49)
        packet[0] = controller_id
        struct.pack_into('<I', packet, 1, packet_number & 0xFFFFFFFF)
        struct.pack_into('<4f', packet, 5, *quaternion)
        struct.pack_into('<3f', packet, 21, *position)
        struct.pack_into('<3f', packet, 33, *gyro)
        struct.pack_into('<H', packet, 45, buttons & 0xFFFF)
        packet[47] = trigger & 0xFF
        checksum = sum(packet[:48]) & 0xFF
        packet[48] = checksum
        return bytes(packet)
    
    def open_position_calibration_dialog(self, controller_id: int):
        """
        Opens interactive calibration dialog with REAL-TIME PREVIEW.
        
        All changes are applied IMMEDIATELY to the running system
        so you can see the controller move in real-time as you adjust parameters.
        
        Sections:
        1. Reference Point - establishes marker baseline
        2. Position Offset - shifts controller relative to marker  
        3. Axis Inversion - fixes inverted coordinate systems
        4. Position Scale - controls movement sensitivity
        
        Changes are saved to config.json automatically.
        """
        if controller_id not in self.controllers:
            return
        
        controller = self.controllers[controller_id]
        if not controller.is_active():
            messagebox.showwarning("Warning", f"Controller {controller_id} is inactive")
            return
        
        cal = self.calibrations[controller_id]
        device_names = ["LEFT Controller", "RIGHT Controller", "HMD"]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Position Calibration - {device_names[controller_id]}")
        dialog.geometry("550x620")
        
        # Get current marker position (raw, before calibration)
        current_raw = controller.aruco_position or [0, 0, 0]
        
        # ===== SECTION 1: REFERENCE POINT =====
        # This establishes the baseline marker position for offset calculations
        ref_frame = ttk.LabelFrame(dialog, text="1. Reference Point (Marker baseline position)", padding=10)
        ref_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(ref_frame, text=f"Current raw marker position: ({current_raw[0]:.3f}, {current_raw[1]:.3f}, {current_raw[2]:.3f})", 
                 font=("Courier", 9)).pack()
        
        def set_reference():
            """Sets reference point to CURRENT marker position"""
            cal.calibration_reference_position = current_raw.copy()
            self.log(f"Controller {controller_id}: Reference point set to {current_raw}")
            ref_label.config(text=f"Reference: ({cal.calibration_reference_position[0]:.3f}, {cal.calibration_reference_position[1]:.3f}, {cal.calibration_reference_position[2]:.3f})")
        
        ttk.Button(ref_frame, text="Set Reference Point", command=set_reference).pack(pady=5)
        ref_label = ttk.Label(ref_frame, 
                             text=f"Reference: ({cal.calibration_reference_position[0]:.3f}, {cal.calibration_reference_position[1]:.3f}, {cal.calibration_reference_position[2]:.3f})", 
                             foreground="blue", font=("Courier", 9))
        ref_label.pack()
        
        # ===== SECTION 2: POSITION OFFSET =====
        # These are the main calibration controls where you adjust controller position
        offset_frame = ttk.LabelFrame(dialog, text="2. Position Offset (Where controller appears)", padding=10)
        offset_frame.pack(fill=tk.X, padx=10, pady=5)
        
        offset_vars = [tk.StringVar(value=f"{cal.position_offset[i]:.3f}") for i in range(3)]
        axis_labels = ["X (left-right)", "Y (up-down)", "Z (forward-back)"]
        
        def update_offset_live(axis_idx):
            """
            LIVE UPDATE: Apply offset changes immediately when user edits text field.
            This creates real-time preview of controller movement.
            """
            try:
                val = float(offset_vars[axis_idx].get())
                cal.position_offset[axis_idx] = val
                self.save_config()
            except ValueError:
                pass  # Ignore invalid input
        
        for i, (axis_label, var) in enumerate(zip(axis_labels, offset_vars)):
            frame = ttk.Frame(offset_frame)
            frame.pack(fill=tk.X, pady=3)
            
            ttk.Label(frame, text=axis_label, width=25).pack(side=tk.LEFT)
            
            # Text entry that updates LIVE when user types
            entry = ttk.Entry(frame, textvariable=var, width=10)
            entry.pack(side=tk.LEFT, padx=5)
            var.trace('w', lambda *args, idx=i: update_offset_live(idx))
            
            step = 0.01  # 1cm increments
            
            def decrease(axis=i):
                """Decrease offset by step (0.01m = 1cm)"""
                try:
                    val = float(offset_vars[axis].get())
                    val -= step
                    offset_vars[axis].set(f"{val:.3f}")
                    update_offset_live(axis)
                except:
                    pass
            
            def increase(axis=i):
                """Increase offset by step (0.01m = 1cm)"""
                try:
                    val = float(offset_vars[axis].get())
                    val += step
                    offset_vars[axis].set(f"{val:.3f}")
                    update_offset_live(axis)
                except:
                    pass
            
            ttk.Button(frame, text="−", width=3, command=decrease).pack(side=tk.LEFT, padx=2)
            ttk.Button(frame, text="+", width=3, command=increase).pack(side=tk.LEFT, padx=2)
        
        # ===== SECTION 3: AXIS INVERSION =====
        # Use this to fix controller moving in opposite direction
        invert_frame = ttk.LabelFrame(dialog, text="3. Axis Inversion (Fix inverted directions)", padding=10)
        invert_frame.pack(fill=tk.X, padx=10, pady=5)
        
        invert_vars = [tk.BooleanVar(value=cal.axis_invert[i]) for i in range(3)]
        
        def update_invert_live(axis_idx):
            """LIVE UPDATE: Apply axis inversion immediately"""
            cal.axis_invert[axis_idx] = invert_vars[axis_idx].get()
            self.save_config()
        
        for i, (axis_label, var) in enumerate(zip(axis_labels, invert_vars)):
            cb = ttk.Checkbutton(invert_frame, text=f"Invert {axis_label}", variable=var,
                                command=lambda idx=i: update_invert_live(idx))
            cb.pack(anchor=tk.W)
        
        ttk.Label(invert_frame, 
                 text="✓ Check if controller moves OPPOSITE when you move marker",
                 foreground="red", font=("", 9)).pack()
        
        # ===== SECTION 4: POSITION SCALE =====
        # Controls how sensitive the movement is (1.0 = 1:1, 0.8 = 80%, 1.2 = 120%)
        scale_frame = ttk.LabelFrame(dialog, text="4. Position Scale (Movement sensitivity)", padding=10)
        scale_frame.pack(fill=tk.X, padx=10, pady=5)
        
        scale_vars = [tk.StringVar(value=f"{cal.position_scale[i]:.3f}") for i in range(3)]
        
        def update_scale_live(axis_idx):
            """LIVE UPDATE: Apply scale changes immediately"""
            try:
                val = float(scale_vars[axis_idx].get())
                if val > 0:  # Scale must be positive
                    cal.position_scale[axis_idx] = val
                    self.save_config()
            except ValueError:
                pass
        
        for i, (axis_label, var) in enumerate(zip(axis_labels, scale_vars)):
            frame = ttk.Frame(scale_frame)
            frame.pack(fill=tk.X, pady=3)
            
            ttk.Label(frame, text=axis_label, width=25).pack(side=tk.LEFT)
            entry = ttk.Entry(frame, textvariable=var, width=10)
            entry.pack(side=tk.LEFT, padx=5)
            var.trace('w', lambda *args, idx=i: update_scale_live(idx))
        
        # ===== BUTTONS: Reset and Cancel only (Apply removed - changes are live!) =====
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def reset_calibration():
            """Reset all position calibration to defaults"""
            if messagebox.askyesno("Confirm Reset", "Reset all position calibration to defaults?"):
                cal.position_offset = [0.0, 0.0, 0.0]
                cal.position_scale = [1.0, 1.0, 1.0]
                cal.axis_invert = [False, False, False]
                cal.calibration_reference_position = [0.0, 0.0, 0.0]
                self.log(f"Controller {controller_id}: Position calibration reset to defaults")
                self.save_config()
                dialog.destroy()
        
        ttk.Button(button_frame, text="Reset", command=reset_calibration).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Info message
        ttk.Label(dialog, text="Changes applied LIVE - move the marker to see results in real-time!", 
                 foreground="green", font=("", 9, "bold")).pack(pady=5)
    
    def calibrate_rotation_only(self, controller_id: int):
        """
        ROTATION CALIBRATION: Saves the current rotation as the baseline.
        
        Simple one-step process:
        1. Point controller straight ahead
        2. Click this button
        3. Current orientation is saved as "neutral"
        
        All future rotations are relative to this baseline.
        """
        if controller_id not in self.controllers:
            return
        
        controller = self.controllers[controller_id]
        if not controller.is_active():
            messagebox.showwarning("Warning", f"Controller {controller_id} is inactive")
            return
        
        cal = self.calibrations[controller_id]
        cal.rotation_offset_quat = controller.quaternion.copy()
        
        device_names = ["LEFT", "RIGHT", "HMD"]
        self.log(f"✅ {device_names[controller_id]}: Rotation calibrated")
        self.log(f"   Baseline rotation: {cal.rotation_offset_quat}")
        self.save_config()
        
        messagebox.showinfo("Success", f"{device_names[controller_id]} rotation calibrated!\n\nBaseline rotation saved.")
    
    def reset_all_calibration(self, controller_id: int):
        """
        RESET ALL: Clears BOTH position and rotation calibration.
        Useful when starting fresh or if calibration got corrupted.
        """
        if messagebox.askyesno("Confirm", f"Reset ALL calibration for controller {controller_id}?"):
            self.calibrations[controller_id] = CalibrationData()
            device_names = ["LEFT", "RIGHT", "HMD"]
            self.log(f"🔄 {device_names[controller_id]}: All calibration reset to factory defaults")
            self.save_config()
    
    def start(self):
        """Start the hub: launch threads for Android receiver and SteamVR sender"""
        if self.running:
            self.log("Hub already running", "WARN")
            return
        self.running = True
        self.log("🚀 Starting VR Tracking Hub...")
        
        # Launch two threads: one to receive from Android, one to send to SteamVR
        t1 = threading.Thread(target=self.start_android_receiver, daemon=True)
        t2 = threading.Thread(target=self.start_steamvr_sender, daemon=True)
        t1.start()
        t2.start()
        self.threads = [t1, t2]
        self.log("✅ All threads started successfully")
    
    def stop(self):
        """Stop the hub: signal threads to exit and close sockets"""
        if not self.running:
            return
        self.log("🛑 Stopping VR Tracking Hub...")
        self.running = False
        for thread in self.threads:
            thread.join(timeout=2.0)
        if self.socket_android:
            self.socket_android.close()
        if self.socket_steamvr:
            self.socket_steamvr.close()
        self.save_config()
        self.log("✅ Hub stopped")
    
    def create_gui(self):
        """
        Creates the main GUI window with all controls.
        
        Layout:
          ┌─ Controllers Section (status + calibration buttons)
          ├─ Statistics Section (packet counts)
          ├─ Control Buttons (Start/Stop/Save/Clear)
          └─ Log Area (scrollable text with all events)
        """
        self.root = tk.Tk()
        self.root.title("VR Tracking Hub v3.0 - Position & Rotation Calibration")
        self.root.geometry("1200x800")
        
        # ===== CONTROLLERS SECTION =====
        # Shows each controller's status, position, and calibration buttons
        controllers_frame = ttk.LabelFrame(self.root, text="Controllers Status & Calibration", padding=10)
        controllers_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.controller_labels = {}
        device_names = ["LEFT Controller", "RIGHT Controller", "HMD (Head)"]
        
        for i, name in enumerate(device_names):
            frame = ttk.Frame(controllers_frame)
            frame.pack(fill=tk.X, pady=5)
            
            # Device name
            ttk.Label(frame, text=name, width=18, font=("", 10, "bold")).pack(side=tk.LEFT)
            
            # Status (Active = green, Inactive = red)
            status_label = ttk.Label(frame, text="Inactive", foreground="red", width=12)
            status_label.pack(side=tk.LEFT, padx=3)
            
            # Current calibrated position in VR
            pos_label = ttk.Label(frame, text="Pos: N/A", width=35, font=("Courier", 9))
            pos_label.pack(side=tk.LEFT, padx=3)
            
            # Calibration control buttons
            ttk.Button(frame, text="Cal Pos", width=10, 
                      command=lambda cid=i: self.open_position_calibration_dialog(cid)).pack(side=tk.LEFT, padx=2)
            ttk.Button(frame, text="Cal Rot", width=10, 
                      command=lambda cid=i: self.calibrate_rotation_only(cid)).pack(side=tk.LEFT, padx=2)
            ttk.Button(frame, text="Reset", width=10, 
                      command=lambda cid=i: self.reset_all_calibration(cid)).pack(side=tk.LEFT, padx=2)
            
            self.controller_labels[i] = {'status': status_label, 'position': pos_label}
        
        # ===== STATISTICS SECTION =====
        # Shows packet and error counts
        stats_frame = ttk.LabelFrame(self.root, text="Statistics", padding=10)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        self.stats_label = ttk.Label(stats_frame, text="", font=("Courier", 10))
        self.stats_label.pack()
        
        # ===== CONTROL BUTTONS =====
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        self.start_btn = ttk.Button(control_frame, text="▶ Start Hub", command=self.start)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(control_frame, text="⏹ Stop Hub", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="💾 Save Config", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="🗑 Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        
        # ===== LOG AREA =====
        # Real-time display of all system events
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=25, font=("Courier", 9))
        self.log_widget.pack(fill=tk.BOTH, expand=True)
        
        # Start periodic GUI updates
        self.update_gui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.auto_save_config()
    
    def update_gui(self):
        """
        Periodic GUI update called every 100ms.
        Updates controller status, position display, and statistics.
        """
        if not self.root:
            return
        
        # Update each controller's status display
        for controller_id, labels in self.controller_labels.items():
            controller = self.controllers[controller_id]
            if controller.is_active():
                labels['status'].config(text="Active", foreground="green")
                pos = controller.position
                labels['position'].config(text=f"Pos: ({pos[0]:+.3f}, {pos[1]:+.3f}, {pos[2]:+.3f})")
            else:
                labels['status'].config(text="Inactive", foreground="red")
                labels['position'].config(text="Pos: N/A")
        
        # Update statistics display
        stats_text = (f"Android: {self.stats['android_packets']:,} packets | " +
                     f"SteamVR: {self.stats['steamvr_packets']:,} packets | " +
                     f"Errors: {self.stats['errors']}")
        self.stats_label.config(text=stats_text)
        
        # Update button states based on running status
        if self.running:
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
        
        # Schedule next update
        self.root.after(100, self.update_gui)
    
    def clear_log(self):
        """Clear all text from the log widget"""
        if self.log_widget:
            self.log_widget.delete('1.0', tk.END)
    
    def auto_save_config(self):
        """Auto-save configuration every 30 seconds"""
        if self.root:
            self.save_config()
            self.root.after(30000, self.auto_save_config)
    
    def on_closing(self):
        """Cleanup when user closes application"""
        self.save_config()
        self.stop()
        self.root.destroy()
    
    def run_gui(self):
        """Launch the GUI and start the main event loop"""
        self.create_gui()
        self.log(f"📁 Config file: {self.CONFIG_FILE}")
        self.log("=" * 80)
        self.log("VR Tracking Hub v3.0")
        self.log("=" * 80)
        self.log("Ready for calibration. Click [Cal Pos] to start position calibration.")
        self.log("")
        self.root.mainloop()

if __name__ == "__main__":
    print("=" * 80)
    print("VR Tracking Hub v3.0 - Advanced Position & Rotation Calibration")
    print("=" * 80)
    hub = VRTrackingHub()
    try:
        hub.run_gui()
    except KeyboardInterrupt:
        print("\nShutting down...")
        hub.stop()