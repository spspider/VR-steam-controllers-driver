#!/usr/bin/env python3
"""
Главный файл vr_tracking_hub.py
VR Tracking Hub v4.0 - Система с автоматической калибровкой

Основные улучшения v4.0:
  ✨ НОВОЕ: Автоматическая калибровка через мастер-визард
  ✨ НОВОЕ: Модульная архитектура (разделение на файлы)
  ✨ Пошаговый процесс калибровки с инструкциями
  ✨ Автоматическое определение инверсии осей
  ✨ Автоматический расчет масштаба
  ✨ Сохранение настроек для тонкой подстройки

Модули:
  - data_structures.py: базовые классы данных
  - utilities.py: математические функции
  - network.py: UDP сетевое взаимодействие
  - calibration.py: применение калибровки и диалоги настройки
  - auto_calibration.py: мастер автоматической калибровки
  - vr_tracking_hub.py: главный класс и GUI (этот файл)
"""
import os
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
from typing import Dict, Optional

# Импорт наших модулей
from data_structures import ControllerData, CalibrationData
from network import NetworkHandler
from calibration import CalibrationManager, CalibrationDialog
from auto_calibration import AutoCalibrationWizard
from utilities import quaternion_conjugate, normalize_quaternion

class VRTrackingHub:
    """
    Главный класс VR трекинг хаба
    
    Отвечает за:
    1. Прием UDP пакетов от Android приложения (порт 5554)
    2. Применение калибровки к данным
    3. Отправку откалиброванных данных в SteamVR драйвер (порт 5555)
    4. Управление GUI и калибровкой
    5. Сохранение/загрузку конфигурации
    """
    
    CONFIG_FILE = "vr_config.json"
    
    def __init__(self):
        """Инициализация всех компонентов системы"""
        # Данные контроллеров (0=LEFT, 1=RIGHT, 2=HMD)
        self.controllers = {
            0: ControllerData(0),
            1: ControllerData(1),
            2: ControllerData(2)
        }
        
        # Калибровочные данные для каждого контроллера
        self.calibrations = {
            0: CalibrationData(),
            1: CalibrationData(),
            2: CalibrationData()
        }
        
        # Сетевой обработчик
        self.network = NetworkHandler(log_callback=self.log)
        
        # Потоки и состояние работы
        self.running = False
        self.threads = []
        
        # Статистика
        self.stats = {
            'android_packets': 0,
            'steamvr_packets': 0,
            'errors': 0
        }
        
        # GUI элементы
        self.root: Optional[tk.Tk] = None
        self.log_widget: Optional[scrolledtext.ScrolledText] = None
        self.controller_labels = {}
        self.stats_label: Optional[ttk.Label] = None
        self.start_btn: Optional[ttk.Button] = None
        self.stop_btn: Optional[ttk.Button] = None
        
        # Загрузка конфигурации
        self.load_config()
    
    def log(self, message: str, level: str = "INFO"):
        """
        Логирование сообщений в текстовый виджет
        
        Args:
            message: текст сообщения
            level: уровень (INFO, WARN, ERROR)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        # Вывод в консоль
        print(log_line.strip())
        
        # Вывод в GUI если доступен
        if self.log_widget:
            self.log_widget.insert(tk.END, log_line)
            self.log_widget.see(tk.END)
    
    def load_config(self):
        """
        Load calibration settings from JSON file
        Called on program startup
        """
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Load data for each controller
                for cid in [0, 1, 2]:
                    cid_str = str(cid)
                    if cid_str in config:
                        cal_data = config[cid_str]
                        cal = self.calibrations[cid]
                        
                        # Restore all calibration parameters
                        cal.position_offset = cal_data.get('position_offset', [0.0, 0.0, 0.0])
                        cal.position_scale = cal_data.get('position_scale', [1.0, 1.0, 1.0])
                        cal.axis_invert = cal_data.get('axis_invert', [False, False, False])
                        cal.rotation_offset_quat = cal_data.get('rotation_offset_quat', [1.0, 0.0, 0.0, 0.0])
                        cal.calibration_reference_position = cal_data.get('calibration_reference_position', [0.0, 0.0, 0.0])
                        cal.calibration_reference_rotation = cal_data.get('calibration_reference_rotation', [1.0, 0.0, 0.0, 0.0])
                
                self.log(f"✅ Config loaded from {self.CONFIG_FILE}")
            except Exception as e:
                self.log(f"❌ Error loading config: {e}", "ERROR")
    
    def save_config(self):
        """
        Save all calibration settings to JSON file
        Called automatically every 30 seconds and on program close
        """
        try:
            config = {}
            
            # Save data for each controller
            for cid in [0, 1, 2]:
                cal = self.calibrations[cid]
                config[str(cid)] = {
                    'position_offset': cal.position_offset,
                    'position_scale': cal.position_scale,
                    'axis_invert': cal.axis_invert,
                    'rotation_offset_quat': cal.rotation_offset_quat,
                    'calibration_reference_position': cal.calibration_reference_position,
                    'calibration_reference_rotation': cal.calibration_reference_rotation
                }
            
            # Write to file
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.log(f"💾 Config saved to {self.CONFIG_FILE}")
        except Exception as e:
            self.log(f"❌ Error saving config: {e}", "ERROR")
    
    def start_android_receiver(self):
        """
        Thread for receiving data from Android app
        Runs continuously while self.running == True
        """
        if not self.network.setup_android_receiver():
            return
        
        self.log("Android receiver started")
        
        while self.running:
            # Receive UDP packet
            result = self.network.receive_from_android()
            if not result:
                continue
            
            data, addr = result
            
            # Parse packet
            parsed = self.network.parse_aruco_packet(data)
            if not parsed:
                self.stats['errors'] += 1
                continue
            
            # Update controller data
            cid = parsed['controller_id']
            if cid not in self.controllers:
                continue
            
            controller = self.controllers[cid]
            
            # Update raw ArUco marker data
            controller.aruco_position = parsed['marker_position']
            controller.aruco_quaternion = parsed['marker_quaternion']
            controller.aruco_last_update = time.time()
            
            # Update general data
            controller.gyro = parsed['gyro']
            controller.buttons = parsed['buttons']
            controller.trigger = parsed['trigger']
            controller.packet_number = parsed['packet_number']
            controller.last_update = time.time()
            controller.source = f"android:{addr[0]}"
            
            # Apply calibration
            CalibrationManager.apply_calibration(controller, self.calibrations[cid])
            
            self.stats['android_packets'] += 1
            
            # Log every 100 packets to show calibration in action
            if parsed['packet_number'] % 100 == 0:
                ctrl_name = ["LEFT", "RIGHT", "HMD"][cid]
                raw = controller.aruco_position
                cal = controller.position
                self.log(f"{ctrl_name}: Raw({raw[0]:.3f},{raw[1]:.3f},{raw[2]:.3f}) "
                        f"→ Cal({cal[0]:.3f},{cal[1]:.3f},{cal[2]:.3f})")
    
    def start_steamvr_sender(self):
        """
        Thread for sending data to SteamVR driver
        Sends data at ~90 Hz frequency
        """
        if not self.network.setup_steamvr_sender():
            return
        
        self.log("SteamVR sender started")
        
        while self.running:
            # Send data for all active controllers
            for cid, controller in self.controllers.items():
                if controller.is_active(timeout=1.0):
                    if self.network.send_to_steamvr(controller):
                        self.stats['steamvr_packets'] += 1
            
            # Pause to maintain ~90 Hz frequency
            time.sleep(1.0 / 90.0)
    
    def start(self):
        """Start tracking system"""
        if self.running:
            self.log("⚠️ System already running", "WARN")
            return
        
        self.running = True
        self.log("🚀 Starting VR Tracking Hub...")
        
        # Start threads
        t1 = threading.Thread(target=self.start_android_receiver, daemon=True, name="AndroidReceiver")
        t2 = threading.Thread(target=self.start_steamvr_sender, daemon=True, name="SteamVRSender")
        
        t1.start()
        t2.start()
        
        self.threads = [t1, t2]
        self.log("✅ All threads started successfully")
    
    def stop(self):
        """Stop tracking system"""
        if not self.running:
            return
        
        self.log("🛑 Stopping VR Tracking Hub...")
        self.running = False
        
        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=2.0)
        
        # Close network sockets
        self.network.close()
        
        # Save configuration
        self.save_config()
        
        self.log("✅ System stopped")
    
    def open_auto_calibration(self, controller_id: int):
        """
        Open automatic calibration wizard
        
        Args:
            controller_id: Controller ID to calibrate
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
        
        # Start calibration wizard
        wizard = AutoCalibrationWizard(
            controller_id=controller_id,
            controller_data=self.controllers[controller_id],
            calibration_data=self.calibrations[controller_id],
            log_callback=self.log
        )
        wizard.start_wizard(self.root)
    
    def open_manual_calibration(self, controller_id: int):
        """
        Open manual fine-tuning calibration dialog
        
        Args:
            controller_id: Controller ID to configure
        """
        dialog = CalibrationDialog(
            controller_id=controller_id,
            calibration=self.calibrations[controller_id],
            controller=self.controllers[controller_id],
            apply_callback=self.save_config
        )
        dialog.create_dialog(self.root)
    
    def calibrate_rotation(self, controller_id: int):
        """
        Quick rotation calibration
        Saves current rotation as base (zero) rotation
        
        Args:
            controller_id: Controller ID
        """
        device_names = ["LEFT", "RIGHT", "HMD"]
        controller = self.controllers[controller_id]
        
        # Check data availability
        if not controller.has_aruco(timeout=1.0):
            messagebox.showerror(
                "Error",
                f"Marker {device_names[controller_id]} not visible!"
            )
            return
        
        # Save current rotation as base
        # Invert it so when applied we get identity quaternion
        self.calibrations[controller_id].rotation_offset_quat = quaternion_conjugate(
            controller.aruco_quaternion
        )
        
        self.log(f"✅ {device_names[controller_id]}: Rotation calibration completed")
        self.save_config()
    
    def reset_calibration(self, controller_id: int):
        """
        Reset all controller calibration to factory defaults
        
        Args:
            controller_id: Controller ID
        """
        device_names = ["LEFT", "RIGHT", "HMD"]
        
        if messagebox.askyesno(
            "Reset Calibration",
            f"Reset all calibration for {device_names[controller_id]} to default values?"
        ):
            self.calibrations[controller_id] = CalibrationData()
            self.log(f"🔄 {device_names[controller_id]}: Calibration reset")
            self.save_config()
    
    def create_gui(self):
        """
        Создание главного GUI окна
        
        Структура:
        ┌─ Секция контроллеров (статус + кнопки калибровки)
        ├─ Секция статистики (счетчики пакетов)
        ├─ Кнопки управления (Старт/Стоп/Сохранить)
        └─ Лог область (прокручиваемый текст событий)
        """
        self.root = tk.Tk()
        self.root.title("VR Tracking Hub v4.0 - Автоматическая калибровка")
        self.root.geometry("1300x850")
        
        # === CONTROLLERS SECTION ===
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
            
            # Current position
            pos_label = ttk.Label(frame, text="Pos: N/A", width=35, font=("Courier", 9))
            pos_label.pack(side=tk.LEFT, padx=3)
            
            # Calibration buttons
            # NEW: Auto-calibration wizard button
            ttk.Button(frame, text="🤖 Auto-Cal", width=12,
                      command=lambda cid=i: self.open_auto_calibration(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="⚙️ Manual", width=12,
                      command=lambda cid=i: self.open_manual_calibration(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="🔄 Cal Rot", width=12,
                      command=lambda cid=i: self.calibrate_rotation(cid)).pack(side=tk.LEFT, padx=2)
            
            ttk.Button(frame, text="❌ Reset", width=10,
                      command=lambda cid=i: self.reset_calibration(cid)).pack(side=tk.LEFT, padx=2)
            
            self.controller_labels[i] = {
                'status': status_label,
                'position': pos_label
            }
        
        # === STATISTICS SECTION ===
        stats_frame = ttk.LabelFrame(self.root, text="Statistics", padding=10)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.stats_label = ttk.Label(stats_frame, text="", font=("Courier", 10))
        self.stats_label.pack()
        
        # === CONTROL BUTTONS ===
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
        
        # === LOG AREA ===
        log_frame = ttk.LabelFrame(self.root, text="Event Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=25, 
                                                     font=("Courier", 9), wrap=tk.WORD)
        self.log_widget.pack(fill=tk.BOTH, expand=True)
        
        # Запуск периодического обновления GUI
        self.update_gui()
        
        # Обработка закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Автосохранение конфигурации
        self.auto_save_config()
    
    def update_gui(self):
        """
        Periodic GUI update (every 100ms)
        Updates controller status, positions and statistics
        """
        if not self.root:
            return
        
        # Update each controller status
        for cid, labels in self.controller_labels.items():
            controller = self.controllers[cid]
            
            if controller.is_active():
                labels['status'].config(text="Active", foreground="green")
                pos = controller.position
                labels['position'].config(
                    text=f"Pos: ({pos[0]:+.3f}, {pos[1]:+.3f}, {pos[2]:+.3f})"
                )
            else:
                labels['status'].config(text="Inactive", foreground="red")
                labels['position'].config(text="Pos: N/A")
        
        # Update statistics
        stats_text = (
            f"Android packets: {self.stats['android_packets']:,} | "
            f"SteamVR packets: {self.stats['steamvr_packets']:,} | "
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
        self.log("VR Tracking Hub v4.0 - Auto-Calibration System")
        self.log("=" * 80)
        self.log("")
        self.log("📋 Quick Start:")
        self.log("   1. Press '▶️ Start' button to start tracking system")
        self.log("   2. Press '🤖 Auto-Cal' for automatic controller calibration")
        self.log("   3. Follow calibration wizard instructions")
        self.log("   4. Use '⚙️ Manual' for fine-tuning if needed")
        self.log("")
        self.log(f"📁 Config file: {self.CONFIG_FILE}")
        self.log("")
        
        # Start main loop
        self.root.mainloop()


if __name__ == "__main__":
    """Program entry point"""
    print("=" * 80)
    print("VR Tracking Hub v4.0 - Auto-Calibration Controller System")
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