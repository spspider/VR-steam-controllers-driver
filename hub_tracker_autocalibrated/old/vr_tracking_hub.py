#!/usr/bin/env python3
"""
VR Tracking Hub - Центральное приложение для объединения данных трекинга
Поддерживает:
- Android телефоны с ArUco маркерами (порт 5554)
- Гироскопические мыши (порт 5556)
- Веб-камеру с ArUco маркерами (опционально)
- Отправка данных в SteamVR драйвер (порт 5555)
"""

import socket
import struct
import threading
import time
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext
import math

# ======================== ПРОТОКОЛ ДАННЫХ ========================
# Протокол SteamVR драйвера (49 байт):
# - controller_id: 1 byte (0=left, 1=right, 2=HMD)
# - packet_number: 4 bytes (uint32)
# - quaternion: 16 bytes (4 floats: w, x, y, z)
# - position: 12 bytes (3 floats: x, y, z)
# - gyro: 12 bytes (3 floats: x, y, z)
# - buttons: 2 bytes (uint16)
# - trigger: 1 byte (uint8)
# - checksum: 1 byte (uint8)

@dataclass
class ControllerData:
    """Данные контроллера"""
    controller_id: int  # 0=left, 1=right, 2=HMD
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # x, y, z
    quaternion: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])  # w, x, y, z
    gyro: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    buttons: int = 0
    trigger: int = 0
    packet_number: int = 0
    last_update: float = 0.0
    source: str = "unknown"
    
    def is_active(self, timeout: float = 1.0) -> bool:
        """Проверка активности источника данных"""
        return (time.time() - self.last_update) < timeout


@dataclass
class CalibrationData:
    """Данные калибровки для каждого контроллера"""
    position_offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    position_scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    rotation_offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])


class VRTrackingHub:
    """Главный хаб для объединения всех источников трекинга"""
    
    def __init__(self):
        # Контроллеры: 0=left, 1=right, 2=HMD
        self.controllers: Dict[int, ControllerData] = {
            0: ControllerData(controller_id=0, source="none"),
            1: ControllerData(controller_id=1, source="none"),
            2: ControllerData(controller_id=2, source="none"),
        }
        
        # Калибровка
        self.calibrations: Dict[int, CalibrationData] = {
            0: CalibrationData(),
            1: CalibrationData(),
            2: CalibrationData(),
        }
        
        # Сокеты
        self.socket_android = None  # Прием от Android (5554)
        self.socket_gyro_mouse = None  # Прием от гиромыши (5556)
        self.socket_steamvr = None  # Отправка в SteamVR (5555)
        
        # Потоки
        self.running = False
        self.threads: List[threading.Thread] = []
        
        # Статистика
        self.stats = {
            'android_packets': 0,
            'gyro_packets': 0,
            'steamvr_packets': 0,
            'errors': 0,
        }
        
        # GUI
        self.root = None
        self.log_widget = None
        
    def log(self, message: str, level: str = "INFO"):
        """Логирование с выводом в GUI"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_msg = f"[{timestamp}] [{level}] {message}"
        print(log_msg)
        
        if self.log_widget:
            try:
                self.log_widget.insert(tk.END, log_msg + "\n")
                self.log_widget.see(tk.END)
                # Ограничить размер лога
                lines = int(self.log_widget.index('end-1c').split('.')[0])
                if lines > 1000:
                    self.log_widget.delete('1.0', '500.0')
            except:
                pass
    
    # =================== NETWORK RECEIVERS ===================
    
    def start_android_receiver(self, port: int = 5554):
        """Запуск приемника данных от Android приложений"""
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
        """Обработка пакета от Android (формат из вашего кода)"""
        try:
            # Протокол Android (49 байт):
            # controller_id(1) + packet_number(4) + quat(16) + pos(12) + gyro(12) + buttons(2) + trigger(1) + checksum(1)
            
            if len(data) != 49:
                self.log(f"Invalid Android packet size: {len(data)}", "WARN")
                return
            
            # Распаковка данных
            controller_id = data[0]
            packet_number = struct.unpack('<I', data[1:5])[0]
            
            # Quaternion (w, x, y, z)
            quat = struct.unpack('<4f', data[5:21])
            
            # Position (x, y, z) - отправляется как "accel" в протоколе
            pos = struct.unpack('<3f', data[21:33])
            
            # Gyro
            gyro = struct.unpack('<3f', data[33:45])
            
            # Buttons, trigger
            buttons = struct.unpack('<H', data[45:47])[0]
            trigger = data[47]
            
            # Checksum
            checksum = data[48]
            calculated_checksum = sum(data[:48]) & 0xFF
            
            if checksum != calculated_checksum:
                self.log(f"Checksum mismatch from {addr}", "WARN")
                return
            
            # Обновить данные контроллера
            if controller_id in self.controllers:
                controller = self.controllers[controller_id]
                controller.position = list(pos)
                controller.quaternion = list(quat)
                controller.gyro = list(gyro)
                controller.buttons = buttons
                controller.trigger = trigger
                controller.packet_number = packet_number
                controller.last_update = time.time()
                controller.source = f"android:{addr[0]}"
                
                self.stats['android_packets'] += 1
                
                # Логировать каждый 100-й пакет
                if packet_number % 100 == 0:
                    ctrl_name = ["LEFT", "RIGHT", "HMD"][controller_id]
                    self.log(f"{ctrl_name} from {addr[0]}: Pos({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})")
            
        except Exception as e:
            self.log(f"Error processing Android packet: {e}", "ERROR")
            self.stats['errors'] += 1
    
    def start_gyro_mouse_receiver(self, port: int = 5556):
        """Запуск приемника данных от гироскопических мышей"""
        try:
            self.socket_gyro_mouse = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket_gyro_mouse.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket_gyro_mouse.bind(('0.0.0.0', port))
            self.socket_gyro_mouse.settimeout(0.1)
            
            self.log(f"Gyro mouse receiver started on port {port}")
            
            # Состояние для интеграции движения мыши в позицию/ориентацию
            mouse_states = {
                0: {'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0, 'last_button': 0},
                1: {'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0, 'last_button': 0},
            }
            
            while self.running:
                try:
                    data, addr = self.socket_gyro_mouse.recvfrom(1024)
                    self.process_gyro_mouse_packet(data, addr, mouse_states)
                except socket.timeout:
                    continue
                except Exception as e:
                    self.log(f"Gyro mouse receiver error: {e}", "ERROR")
                    self.stats['errors'] += 1
                    
        except Exception as e:
            self.log(f"Failed to start gyro mouse receiver: {e}", "ERROR")
    
    def process_gyro_mouse_packet(self, data: bytes, addr: tuple, mouse_states: dict):
        """Обработка пакета от гироскопической мыши"""
        try:
            # Формат: "MOUSE:dx,dy,button,timestamp"
            message = data.decode('utf-8').strip()
            
            if not message.startswith("MOUSE:"):
                return
            
            parts = message[6:].split(',')
            if len(parts) != 4:
                return
            
            dx = int(parts[0])
            dy = int(parts[1])
            button = int(parts[2])
            timestamp = int(parts[3])
            
            # Определяем, какой контроллер (по кнопке или по настройке)
            # Пока используем button: 1=left, 2=right
            controller_id = 0 if button == 1 else 1
            
            if controller_id not in mouse_states:
                return
            
            state = mouse_states[controller_id]
            
            # Интегрируем движение мыши в углы (простая модель)
            sensitivity = 0.001  # Чувствительность
            state['yaw'] += dx * sensitivity
            state['pitch'] += dy * sensitivity
            
            # Ограничить pitch
            state['pitch'] = max(-math.pi/2, min(math.pi/2, state['pitch']))
            
            # Конвертировать Euler углы в quaternion
            quat = self.euler_to_quaternion(state['yaw'], state['pitch'], state['roll'])
            
            # Обновить контроллер
            controller = self.controllers[controller_id]
            controller.quaternion = quat
            controller.buttons = button
            controller.last_update = time.time()
            controller.source = f"gyromouse:{addr[0]}"
            
            self.stats['gyro_packets'] += 1
            
            # Логировать каждые 100 пакетов
            if self.stats['gyro_packets'] % 100 == 0:
                ctrl_name = ["LEFT", "RIGHT"][controller_id]
                self.log(f"{ctrl_name} gyromouse: Yaw={state['yaw']:.2f}, Pitch={state['pitch']:.2f}")
            
        except Exception as e:
            self.log(f"Error processing gyro mouse packet: {e}", "ERROR")
            self.stats['errors'] += 1
    
    def euler_to_quaternion(self, yaw: float, pitch: float, roll: float) -> List[float]:
        """Конвертация Euler углов в quaternion (w, x, y, z)"""
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)
        
        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy
        
        return [w, x, y, z]
    
    # =================== STEAMVR SENDER ===================
    
    def start_steamvr_sender(self, host: str = '127.0.0.1', port: int = 5555):
        """Запуск отправки данных в SteamVR драйвер"""
        try:
            self.socket_steamvr = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            self.log(f"SteamVR sender started, target {host}:{port}")
            
            while self.running:
                try:
                    # Отправляем данные для всех активных контроллеров
                    for controller_id, controller in self.controllers.items():
                        if controller.is_active():
                            # Применить калибровку
                            calibrated_pos = self.apply_calibration_position(
                                controller.position, 
                                self.calibrations[controller_id]
                            )
                            
                            # Собрать пакет
                            packet = self.build_steamvr_packet(
                                controller_id,
                                controller.quaternion,
                                calibrated_pos,
                                controller.gyro,
                                controller.buttons,
                                controller.trigger,
                                controller.packet_number
                            )
                            
                            # Отправить
                            self.socket_steamvr.sendto(packet, (host, port))
                            self.stats['steamvr_packets'] += 1
                    
                    # Отправка с частотой ~90 Hz (как у VR)
                    time.sleep(1.0 / 90.0)
                    
                except Exception as e:
                    self.log(f"SteamVR sender error: {e}", "ERROR")
                    self.stats['errors'] += 1
                    time.sleep(0.1)
                    
        except Exception as e:
            self.log(f"Failed to start SteamVR sender: {e}", "ERROR")
    
    def build_steamvr_packet(self, controller_id: int, quaternion: List[float], 
                            position: List[float], gyro: List[float],
                            buttons: int, trigger: int, packet_number: int) -> bytes:
        """Построение пакета для SteamVR драйвера (49 байт)"""
        packet = bytearray(49)
        
        # 1. Controller ID (1 byte)
        packet[0] = controller_id
        
        # 2. Packet number (4 bytes, little-endian)
        struct.pack_into('<I', packet, 1, packet_number & 0xFFFFFFFF)
        
        # 3. Quaternion (16 bytes: w, x, y, z)
        struct.pack_into('<4f', packet, 5, *quaternion)
        
        # 4. Position (12 bytes: x, y, z)
        struct.pack_into('<3f', packet, 21, *position)
        
        # 5. Gyro (12 bytes)
        struct.pack_into('<3f', packet, 33, *gyro)
        
        # 6. Buttons (2 bytes)
        struct.pack_into('<H', packet, 45, buttons & 0xFFFF)
        
        # 7. Trigger (1 byte)
        packet[47] = trigger & 0xFF
        
        # 8. Checksum (1 byte)
        checksum = sum(packet[:48]) & 0xFF
        packet[48] = checksum
        
        return bytes(packet)
    
    def apply_calibration_position(self, position: List[float], 
                                   calibration: CalibrationData) -> List[float]:
        """Применение калибровки к позиции"""
        return [
            (position[0] + calibration.position_offset[0]) * calibration.position_scale[0],
            (position[1] + calibration.position_offset[1]) * calibration.position_scale[1],
            (position[2] + calibration.position_offset[2]) * calibration.position_scale[2],
        ]
    
    # =================== CALIBRATION ===================
    
    def calibrate_controller(self, controller_id: int):
        """Калибровка контроллера - устанавливает текущую позицию как (0,0,0)"""
        if controller_id not in self.controllers:
            self.log(f"Invalid controller ID: {controller_id}", "ERROR")
            return
        
        controller = self.controllers[controller_id]
        if not controller.is_active():
            self.log(f"Controller {controller_id} is not active", "WARN")
            return
        
        # Установить offset как отрицательную текущую позицию
        calibration = self.calibrations[controller_id]
        calibration.position_offset = [
            -controller.position[0],
            -controller.position[1],
            -controller.position[2],
        ]
        
        ctrl_name = ["LEFT", "RIGHT", "HMD"][controller_id]
        self.log(f"Calibrated {ctrl_name} controller: offset = {calibration.position_offset}")
    
    def reset_calibration(self, controller_id: int):
        """Сброс калибровки"""
        if controller_id in self.calibrations:
            self.calibrations[controller_id] = CalibrationData()
            ctrl_name = ["LEFT", "RIGHT", "HMD"][controller_id]
            self.log(f"Reset calibration for {ctrl_name} controller")
    
    # =================== MAIN CONTROL ===================
    
    def start(self):
        """Запуск всех потоков"""
        if self.running:
            self.log("Hub already running", "WARN")
            return
        
        self.running = True
        self.log("Starting VR Tracking Hub...")
        
        # Запустить приемники
        t1 = threading.Thread(target=self.start_android_receiver, daemon=True)
        t2 = threading.Thread(target=self.start_gyro_mouse_receiver, daemon=True)
        t3 = threading.Thread(target=self.start_steamvr_sender, daemon=True)
        
        t1.start()
        t2.start()
        t3.start()
        
        self.threads = [t1, t2, t3]
        
        self.log("All threads started successfully")
    
    def stop(self):
        """Остановка всех потоков"""
        if not self.running:
            return
        
        self.log("Stopping VR Tracking Hub...")
        self.running = False
        
        # Подождать завершения потоков
        for thread in self.threads:
            thread.join(timeout=2.0)
        
        # Закрыть сокеты
        if self.socket_android:
            self.socket_android.close()
        if self.socket_gyro_mouse:
            self.socket_gyro_mouse.close()
        if self.socket_steamvr:
            self.socket_steamvr.close()
        
        self.log("Hub stopped")
    
    # =================== GUI ===================
    
    def create_gui(self):
        """Создание графического интерфейса"""
        self.root = tk.Tk()
        self.root.title("VR Tracking Hub")
        self.root.geometry("900x700")
        
        # Фрейм контроллеров
        controllers_frame = ttk.LabelFrame(self.root, text="Controllers Status", padding=10)
        controllers_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.controller_labels = {}
        for i, name in enumerate(["LEFT Controller", "RIGHT Controller", "HMD (Head)"]):
            frame = ttk.Frame(controllers_frame)
            frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(frame, text=name, width=20).pack(side=tk.LEFT)
            
            status_label = ttk.Label(frame, text="Inactive", foreground="red", width=15)
            status_label.pack(side=tk.LEFT, padx=5)
            
            pos_label = ttk.Label(frame, text="Pos: N/A", width=30)
            pos_label.pack(side=tk.LEFT, padx=5)
            
            source_label = ttk.Label(frame, text="Source: none", width=20)
            source_label.pack(side=tk.LEFT, padx=5)
            
            # Кнопки калибровки
            calib_btn = ttk.Button(frame, text="Calibrate", width=10,
                                  command=lambda cid=i: self.calibrate_controller(cid))
            calib_btn.pack(side=tk.LEFT, padx=2)
            
            reset_btn = ttk.Button(frame, text="Reset", width=8,
                                  command=lambda cid=i: self.reset_calibration(cid))
            reset_btn.pack(side=tk.LEFT, padx=2)
            
            self.controller_labels[i] = {
                'status': status_label,
                'position': pos_label,
                'source': source_label
            }
        
        # Статистика
        stats_frame = ttk.LabelFrame(self.root, text="Statistics", padding=10)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.stats_label = ttk.Label(stats_frame, text="", font=("Courier", 10))
        self.stats_label.pack()
        
        # Кнопки управления
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.start_btn = ttk.Button(control_frame, text="Start Hub", command=self.start)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="Stop Hub", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        
        # Лог
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=20, font=("Courier", 9))
        self.log_widget.pack(fill=tk.BOTH, expand=True)
        
        # Обновление GUI
        self.update_gui()
        
        # Обработчик закрытия
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def update_gui(self):
        """Обновление GUI"""
        if not self.root:
            return
        
        # Обновить статус контроллеров
        for controller_id, labels in self.controller_labels.items():
            controller = self.controllers[controller_id]
            
            if controller.is_active():
                labels['status'].config(text="Active", foreground="green")
                labels['position'].config(
                    text=f"Pos: ({controller.position[0]:.2f}, {controller.position[1]:.2f}, {controller.position[2]:.2f})"
                )
                labels['source'].config(text=f"Source: {controller.source}")
            else:
                labels['status'].config(text="Inactive", foreground="red")
                labels['position'].config(text="Pos: N/A")
                labels['source'].config(text="Source: none")
        
        # Обновить статистику
        stats_text = f"Android packets: {self.stats['android_packets']:,} | " \
                    f"Gyro packets: {self.stats['gyro_packets']:,} | " \
                    f"SteamVR packets: {self.stats['steamvr_packets']:,} | " \
                    f"Errors: {self.stats['errors']}"
        self.stats_label.config(text=stats_text)
        
        # Обновить кнопки
        if self.running:
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
        
        # Запланировать следующее обновление
        self.root.after(100, self.update_gui)
    
    def clear_log(self):
        """Очистка лога"""
        if self.log_widget:
            self.log_widget.delete('1.0', tk.END)
    
    def on_closing(self):
        """Обработка закрытия окна"""
        self.stop()
        self.root.destroy()
    
    def run_gui(self):
        """Запуск GUI"""
        self.create_gui()
        self.root.mainloop()


# =================== MAIN ===================

if __name__ == "__main__":
    print("=" * 60)
    print("VR Tracking Hub - Central controller tracking application")
    print("=" * 60)
    print()
    print("Supported inputs:")
    print("  - Android phones with ArUco markers (port 5554)")
    print("  - Gyroscopic mice (port 5556)")
    print("  - Webcam with ArUco markers (optional)")
    print()
    print("Output:")
    print("  - SteamVR driver (port 5555)")
    print()
    print("=" * 60)
    
    hub = VRTrackingHub()
    
    try:
        hub.run_gui()
    except KeyboardInterrupt:
        print("\nShutting down...")
        hub.stop()