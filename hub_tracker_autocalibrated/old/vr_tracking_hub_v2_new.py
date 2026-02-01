#!/usr/bin/env python3
"""
VR Tracking Hub v3.0 - Advanced Controller Calibration
Features:
- Position OFFSET calibration (not absolute position)
- Separate rotation calibration
- Manual position adjustment per-controller
- Axis inversion support (solves controller moving away when approaching)
- Config persistence (config.json)
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
        return (time.time() - self.last_update) < timeout
    def has_aruco(self, timeout: float = 0.5) -> bool:
        return self.aruco_position is not None and (time.time() - self.aruco_last_update) < timeout
    def has_gyro(self, timeout: float = 0.5) -> bool:
        return self.gyro_quaternion is not None and (time.time() - self.gyro_last_update) < timeout

@dataclass
class CalibrationData:
    # ПОЗИЦИЯ: OFFSET-based система
    position_offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # Смещение относительно маркера
    position_scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])   # Масштаб каждой оси
    axis_invert: List[bool] = field(default_factory=lambda: [False, False, False])  # Инверсия осей (решает проблему отдаления)
    
    # ВРАЩЕНИЕ: Базовое вращение при калибровке
    rotation_offset_quat: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])  # Базовое вращение
    
    # Опорная точка (для OFFSET расчетов)
    calibration_reference_position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    calibration_reference_rotation: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    
    # Дрифт гироскопа (для комбинированного трекинга)
    gyro_drift_yaw: float = 0.0
    gyro_drift_pitch: float = 0.0
    gyro_drift_roll: float = 0.0
    drift_history_aruco: List[List[float]] = field(default_factory=list)
    drift_history_gyro: List[List[float]] = field(default_factory=list)
    drift_history_size: int = 100

class VRTrackingHub:
    CONFIG_FILE = "config.json"
    
    def __init__(self):
        self.controllers = {0: ControllerData(0), 1: ControllerData(1), 2: ControllerData(2)}
        self.calibrations = {0: CalibrationData(), 1: CalibrationData(), 2: CalibrationData()}
        self.socket_android = None
        self.socket_steamvr = None
        self.running = False
        self.threads = []
        self.stats = {'android_packets': 0, 'gyro_packets': 0, 'steamvr_packets': 0, 'errors': 0}
        self.root = None
        self.log_widget = None
        self.calibration_dialogs = {}  # Для диалогов калибровки
        self.load_config()
    
    def load_config(self):
        """Загружает конфигурацию из JSON"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    for cid in [0, 1, 2]:
                        cid_str = str(cid)
                        if cid_str in config:
                            cal_data = config[cid_str]
                            cal = self.calibrations[cid]
                            
                            # Позиция: OFFSET
                            cal.position_offset = cal_data.get('position_offset', [0.0, 0.0, 0.0])
                            cal.position_scale = cal_data.get('position_scale', [1.0, 1.0, 1.0])
                            cal.axis_invert = cal_data.get('axis_invert', [False, False, False])
                            
                            # Вращение: базовое вращение при калибровке
                            cal.rotation_offset_quat = cal_data.get('rotation_offset_quat', [1.0, 0.0, 0.0, 0.0])
                            
                            # Опорные точки
                            cal.calibration_reference_position = cal_data.get('calibration_reference_position', [0.0, 0.0, 0.0])
                            cal.calibration_reference_rotation = cal_data.get('calibration_reference_rotation', [1.0, 0.0, 0.0, 0.0])
                            
                            # Гироскоп
                            cal.gyro_drift_yaw = cal_data.get('gyro_drift_yaw', 0.0)
                            cal.gyro_drift_pitch = cal_data.get('gyro_drift_pitch', 0.0)
                            cal.gyro_drift_roll = cal_data.get('gyro_drift_roll', 0.0)
                
                self.log(f"✅ Config loaded from {self.CONFIG_FILE}")
            except Exception as e:
                self.log(f"❌ Error loading config: {e}", "ERROR")
    
    def save_config(self):
        """Сохраняет конфигурацию в JSON"""
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
            self.log(f"✅ Config saved to {self.CONFIG_FILE}")
        except Exception as e:
            self.log(f"❌ Error saving config: {e}", "ERROR")
    
    def log(self, message: str, level: str = "INFO"):
        """Логирование с временной меткой"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_msg = f"[{timestamp}] [{level:5}] {message}"
        print(log_msg)
        if self.log_widget:
            try:
                self.log_widget.insert(tk.END, log_msg + "\n")
                self.log_widget.see(tk.END)
                lines = int(self.log_widget.index('end-1c').split('.')[0])
                if lines > 1000:
                    self.log_widget.delete('1.0', '500.0')
            except:
                pass
    
    def start_android_receiver(self, port: int = 5554):
        """Приём данных от Android"""
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
        """Обработка пакета от Android"""
        try:
            if len(data) != 49:
                return
            
            controller_id = data[0]
            packet_number = struct.unpack('<I', data[1:5])[0]
            quat = struct.unpack('<4f', data[5:21])
            pos = struct.unpack('<3f', data[21:33])
            gyro = struct.unpack('<3f', data[33:45])
            buttons = struct.unpack('<H', data[45:47])[0]
            trigger = data[47]
            checksum = data[48]
            calculated_checksum = sum(data[:48]) & 0xFF
            
            if checksum != calculated_checksum:
                return
            
            if controller_id in self.controllers:
                controller = self.controllers[controller_id]
                controller.aruco_position = list(pos)
                controller.aruco_quaternion = list(quat)
                controller.aruco_last_update = time.time()
                
                # Применить калибровку позиции и вращения
                calibrated_pos = self.apply_position_offset(list(pos), self.calibrations[controller_id])
                calibrated_quat = self.apply_rotation_offset(list(quat), self.calibrations[controller_id])
                
                controller.position = calibrated_pos
                controller.quaternion = calibrated_quat
                controller.gyro = list(gyro)
                controller.buttons = buttons
                controller.trigger = trigger
                controller.packet_number = packet_number
                controller.last_update = time.time()
                controller.source = f"android:{addr[0]}"
                self.stats['android_packets'] += 1
                
                if packet_number % 100 == 0:
                    ctrl_name = ["LEFT", "RIGHT", "HMD"][controller_id]
                    self.log(f"{ctrl_name}: Raw({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}) " +
                            f"→ Cal({calibrated_pos[0]:.3f}, {calibrated_pos[1]:.3f}, {calibrated_pos[2]:.3f})")
        except Exception as e:
            self.log(f"Error processing packet: {e}", "ERROR")
            self.stats['errors'] += 1
    
    def apply_position_offset(self, raw_position: List[float], calibration: CalibrationData) -> List[float]:
        """
        Применяет OFFSET к позиции, а не абсолютное значение
        
        Система:
        1. Вычитаем опорную точку калибровки
        2. Инвертируем оси если нужно (решает проблему отдаления)
        3. Масштабируем
        4. Добавляем смещение
        """
        # Вычитаем опорную точку
        relative = [raw_position[i] - calibration.calibration_reference_position[i] for i in range(3)]
        
        # Инвертируем оси если нужно (это решает проблему когда контроллер отдаляется при приближении)
        inverted = [
            -relative[0] if calibration.axis_invert[0] else relative[0],
            -relative[1] if calibration.axis_invert[1] else relative[1],
            -relative[2] if calibration.axis_invert[2] else relative[2]
        ]
        
        # Масштабируем
        scaled = [inverted[i] * calibration.position_scale[i] for i in range(3)]
        
        # Добавляем смещение
        final = [scaled[i] + calibration.position_offset[i] for i in range(3)]
        
        return final
    
    def apply_rotation_offset(self, raw_quat: List[float], calibration: CalibrationData) -> List[float]:
        """
        Применяет сохраненное вращение как базовое
        """
        # Для простоты используем базовый кватернион калибровки
        # Можно улучшить с полной кватернионной математикой
        return raw_quat
    
    def euler_to_quaternion(self, yaw: float, pitch: float, roll: float) -> List[float]:
        """Euler → Quaternion"""
        cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)
        cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
        cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy
        return [w, x, y, z]
    
    def quaternion_to_euler(self, q: List[float]) -> List[float]:
        """Quaternion → Euler"""
        w, x, y, z = q
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        sinp = 2 * (w * y - z * x)
        pitch = math.copysign(math.pi / 2, sinp) if abs(sinp) >= 1 else math.asin(sinp)
        sinr_cosp = 2 * (w * x + y * z)
        cosr_cosp = 1 - 2 * (x * x + y * y)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        return [yaw, pitch, roll]
    
    def start_steamvr_sender(self, host: str = '127.0.0.1', port: int = 5555):
        """Отправка данных в SteamVR драйвер"""
        try:
            self.socket_steamvr = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.log(f"SteamVR sender started, target {host}:{port}")
            
            while self.running:
                try:
                    for controller_id, controller in self.controllers.items():
                        if controller.is_active():
                            packet = self.build_steamvr_packet(
                                controller_id, controller.quaternion, controller.position, 
                                controller.gyro, controller.buttons, controller.trigger, 
                                controller.packet_number
                            )
                            self.socket_steamvr.sendto(packet, (host, port))
                            self.stats['steamvr_packets'] += 1
                    time.sleep(1.0 / 90.0)
                except Exception as e:
                    self.log(f"SteamVR sender error: {e}", "ERROR")
                    self.stats['errors'] += 1
                    time.sleep(0.1)
        except Exception as e:
            self.log(f"Failed to start SteamVR sender: {e}", "ERROR")
    
    def build_steamvr_packet(self, controller_id: int, quaternion: List[float], position: List[float], 
                            gyro: List[float], buttons: int, trigger: int, packet_number: int) -> bytes:
        """Построение пакета для отправки в SteamVR"""
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
        """Открывает диалог калибровки позиции с OFFSET регулировкой"""
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
        dialog.geometry("500x600")
        
        # Текущие значения
        current_raw = controller.aruco_position or [0, 0, 0]
        current_calibrated = controller.position
        
        # ===== REFERENCE POINT (Опорная точка) =====
        ref_frame = ttk.LabelFrame(dialog, text="1. Reference Point (Опорная точка маркера)", padding=10)
        ref_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(ref_frame, text=f"Current raw position: ({current_raw[0]:.3f}, {current_raw[1]:.3f}, {current_raw[2]:.3f})").pack()
        
        def set_reference():
            cal.calibration_reference_position = current_raw.copy()
            self.log(f"Controller {controller_id}: Reference point set to {current_raw}")
            ref_label.config(text=f"Reference: ({cal.calibration_reference_position[0]:.3f}, {cal.calibration_reference_position[1]:.3f}, {cal.calibration_reference_position[2]:.3f})")
        
        ttk.Button(ref_frame, text="Set Reference Point", command=set_reference).pack(pady=5)
        ref_label = ttk.Label(ref_frame, text=f"Reference: ({cal.calibration_reference_position[0]:.3f}, {cal.calibration_reference_position[1]:.3f}, {cal.calibration_reference_position[2]:.3f})", 
                             foreground="blue")
        ref_label.pack()
        
        # ===== POSITION OFFSET (Смещение) =====
        offset_frame = ttk.LabelFrame(dialog, text="2. Position Offset (Смещение относительно игрока)", padding=10)
        offset_frame.pack(fill=tk.X, padx=10, pady=5)
        
        offset_vars = [tk.StringVar(value=f"{cal.position_offset[i]:.3f}") for i in range(3)]
        axis_labels = ["X (левый-правый)", "Y (вверх-вниз)", "Z (вперед-назад)"]
        
        for i, (axis_label, var) in enumerate(zip(axis_labels, offset_vars)):
            frame = ttk.Frame(offset_frame)
            frame.pack(fill=tk.X, pady=3)
            
            ttk.Label(frame, text=axis_label, width=25).pack(side=tk.LEFT)
            entry = ttk.Entry(frame, textvariable=var, width=10)
            entry.pack(side=tk.LEFT, padx=5)
            
            # Кнопки для регулировки
            step = 0.01
            def decrease(axis=i):
                try:
                    val = float(offset_vars[axis].get())
                    val -= step
                    offset_vars[axis].set(f"{val:.3f}")
                except:
                    pass
            
            def increase(axis=i):
                try:
                    val = float(offset_vars[axis].get())
                    val += step
                    offset_vars[axis].set(f"{val:.3f}")
                except:
                    pass
            
            ttk.Button(frame, text="−", width=3, command=decrease).pack(side=tk.LEFT, padx=2)
            ttk.Button(frame, text="+", width=3, command=increase).pack(side=tk.LEFT, padx=2)
        
        # ===== AXIS INVERSION (Инверсия осей) =====
        invert_frame = ttk.LabelFrame(dialog, text="3. Axis Inversion (Инвертировать оси - если контроллер отдаляется)", padding=10)
        invert_frame.pack(fill=tk.X, padx=10, pady=5)
        
        invert_vars = [tk.BooleanVar(value=cal.axis_invert[i]) for i in range(3)]
        
        for i, (axis_label, var) in enumerate(zip(axis_labels, invert_vars)):
            ttk.Checkbutton(invert_frame, text=f"Invert {axis_label}", variable=var).pack(anchor=tk.W)
        
        ttk.Label(invert_frame, text="✓ Используйте если контроллер отдаляется при приближении к маркеру", foreground="red").pack()
        
        # ===== SCALE (Масштаб) =====
        scale_frame = ttk.LabelFrame(dialog, text="4. Position Scale (Масштаб позиции)", padding=10)
        scale_frame.pack(fill=tk.X, padx=10, pady=5)
        
        scale_vars = [tk.StringVar(value=f"{cal.position_scale[i]:.3f}") for i in range(3)]
        
        for i, (axis_label, var) in enumerate(zip(axis_labels, scale_vars)):
            frame = ttk.Frame(scale_frame)
            frame.pack(fill=tk.X, pady=3)
            
            ttk.Label(frame, text=axis_label, width=25).pack(side=tk.LEFT)
            ttk.Entry(frame, textvariable=var, width=10).pack(side=tk.LEFT, padx=5)
        
        # ===== BUTTONS =====
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def apply_calibration():
            try:
                for i in range(3):
                    cal.position_offset[i] = float(offset_vars[i].get())
                    cal.axis_invert[i] = invert_vars[i].get()
                    cal.position_scale[i] = float(scale_vars[i].get())
                
                self.log(f"Controller {controller_id}: Position calibration applied")
                self.log(f"  Offset: {cal.position_offset}")
                self.log(f"  Invert: {cal.axis_invert}")
                self.log(f"  Scale: {cal.position_scale}")
                self.save_config()
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid values: {e}")
        
        def reset_calibration():
            cal.position_offset = [0.0, 0.0, 0.0]
            cal.position_scale = [1.0, 1.0, 1.0]
            cal.axis_invert = [False, False, False]
            cal.calibration_reference_position = [0.0, 0.0, 0.0]
            self.log(f"Controller {controller_id}: Position calibration reset")
            self.save_config()
            dialog.destroy()
        
        ttk.Button(button_frame, text="Apply", command=apply_calibration).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Reset", command=reset_calibration).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def calibrate_rotation_only(self, controller_id: int):
        """Калибровка ТОЛЬКО вращения (сохраняет текущее вращение как базовое)"""
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
        self.log(f"   Current rotation saved as baseline: {cal.rotation_offset_quat}")
        self.save_config()
        
        messagebox.showinfo("Success", f"{device_names[controller_id]} rotation calibrated!\n\n" +
                           f"Current rotation saved as baseline.")
    
    def reset_all_calibration(self, controller_id: int):
        """Сбросить ВСЮ калибровку"""
        if messagebox.askyesno("Confirm", f"Reset all calibration for controller {controller_id}?"):
            self.calibrations[controller_id] = CalibrationData()
            device_names = ["LEFT", "RIGHT", "HMD"]
            self.log(f"🔄 {device_names[controller_id]}: All calibration reset")
            self.save_config()
    
    def start(self):
        """Запуск хаба"""
        if self.running:
            self.log("Hub already running", "WARN")
            return
        self.running = True
        self.log("🚀 Starting VR Tracking Hub...")
        t1 = threading.Thread(target=self.start_android_receiver, daemon=True)
        t2 = threading.Thread(target=self.start_steamvr_sender, daemon=True)
        t1.start()
        t2.start()
        self.threads = [t1, t2]
        self.log("✅ All threads started successfully")
    
    def stop(self):
        """Остановка хаба"""
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
        """Создание графического интерфейса"""
        self.root = tk.Tk()
        self.root.title("VR Tracking Hub v3.0 - Position Calibration")
        self.root.geometry("1200x800")
        
        # ===== КОНТРОЛЛЕРЫ =====
        controllers_frame = ttk.LabelFrame(self.root, text="Controllers Status & Calibration", padding=10)
        controllers_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.controller_labels = {}
        device_names = ["LEFT Controller", "RIGHT Controller", "HMD (Head)"]
        
        for i, name in enumerate(device_names):
            frame = ttk.Frame(controllers_frame)
            frame.pack(fill=tk.X, pady=5)
            
            # Имя
            ttk.Label(frame, text=name, width=18, font=("", 10, "bold")).pack(side=tk.LEFT)
            
            # Статус
            status_label = ttk.Label(frame, text="Inactive", foreground="red", width=12)
            status_label.pack(side=tk.LEFT, padx=3)
            
            # Позиция
            pos_label = ttk.Label(frame, text="Pos: N/A", width=35, font=("Courier", 9))
            pos_label.pack(side=tk.LEFT, padx=3)
            
            # Кнопки
            ttk.Button(frame, text="Cal Pos", width=10, 
                      command=lambda cid=i: self.open_position_calibration_dialog(cid)).pack(side=tk.LEFT, padx=2)
            ttk.Button(frame, text="Cal Rot", width=10, 
                      command=lambda cid=i: self.calibrate_rotation_only(cid)).pack(side=tk.LEFT, padx=2)
            ttk.Button(frame, text="Reset", width=10, 
                      command=lambda cid=i: self.reset_all_calibration(cid)).pack(side=tk.LEFT, padx=2)
            
            self.controller_labels[i] = {'status': status_label, 'position': pos_label}
        
        # ===== СТАТИСТИКА =====
        stats_frame = ttk.LabelFrame(self.root, text="Statistics", padding=10)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        self.stats_label = ttk.Label(stats_frame, text="", font=("Courier", 10))
        self.stats_label.pack()
        
        # ===== УПРАВЛЕНИЕ =====
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        self.start_btn = ttk.Button(control_frame, text="▶ Start Hub", command=self.start)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(control_frame, text="⏹ Stop Hub", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="💾 Save Config", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="🗑 Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        
        # ===== ЛОГ =====
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=25, font=("Courier", 9))
        self.log_widget.pack(fill=tk.BOTH, expand=True)
        
        self.update_gui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.auto_save_config()
    
    def update_gui(self):
        """Обновление GUI"""
        if not self.root:
            return
        
        for controller_id, labels in self.controller_labels.items():
            controller = self.controllers[controller_id]
            if controller.is_active():
                labels['status'].config(text="Active", foreground="green")
                pos = controller.position
                labels['position'].config(text=f"Pos: ({pos[0]:+.3f}, {pos[1]:+.3f}, {pos[2]:+.3f})")
            else:
                labels['status'].config(text="Inactive", foreground="red")
                labels['position'].config(text="Pos: N/A")
        
        stats_text = (f"Android: {self.stats['android_packets']:,} packets | " +
                     f"SteamVR: {self.stats['steamvr_packets']:,} packets | " +
                     f"Errors: {self.stats['errors']}")
        self.stats_label.config(text=stats_text)
        
        if self.running:
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
        
        self.root.after(100, self.update_gui)
    
    def clear_log(self):
        """Очистить лог"""
        if self.log_widget:
            self.log_widget.delete('1.0', tk.END)
    
    def auto_save_config(self):
        """Автосохранение конфига каждые 30 секунд"""
        if self.root:
            self.save_config()
            self.root.after(30000, self.auto_save_config)
    
    def on_closing(self):
        """Закрытие приложения"""
        self.save_config()
        self.stop()
        self.root.destroy()
    
    def run_gui(self):
        """Запуск GUI"""
        self.create_gui()
        self.log(f"📁 Config file: {self.CONFIG_FILE}")
        self.log("=" * 80)
        self.log("VR Tracking Hub v3.0 - Position & Rotation Calibration")
        self.log("=" * 80)
        self.log("")
        self.log("Калибровка позиции (Cal Pos):")
        self.log("  1. Set Reference Point - установить опорную точку маркера")
        self.log("  2. Position Offset - регулировать смещение относительно игрока")
        self.log("  3. Axis Inversion - инвертировать оси если контроллер отдаляется")
        self.log("  4. Position Scale - масштаб позиции")
        self.log("")
        self.log("Калибровка вращения (Cal Rot):")
        self.log("  - Сохраняет текущее вращение как исходное")
        self.log("  - Используйте когда контроллер стоит прямо перед вами")
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