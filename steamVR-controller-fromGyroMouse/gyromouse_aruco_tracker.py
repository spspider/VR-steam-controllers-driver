#!/usr/bin/env python3
"""
GyroMouse + ArUco Tracker
Читает данные от гироскопической мыши и отслеживает позицию через ArUco маркер
Отправляет данные по UDP на порт 5555 для драйвера SteamVR
"""

import socket
import struct
import time
import math
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
import threading

# Попробуем импортировать библиотеки для чтения данных мыши
try:
    import hid  # pip install hidapi
    HID_AVAILABLE = True
except ImportError:
    HID_AVAILABLE = False
    print("Warning: hidapi not available, using simulation mode")

class ArUcoTracker:
    """Отслеживание позиции через ArUco маркер"""
    def __init__(self, marker_id=0, camera_index=0):
        self.marker_id = marker_id
        self.camera = cv2.VideoCapture(camera_index)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # ArUco словарь и детектор
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.aruco_params = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
        
        # Калибровка камеры (примерные значения, замените на свои!)
        self.camera_matrix = np.array([
            [800, 0, 320],
            [0, 800, 240],
            [0, 0, 1]
        ], dtype=float)
        self.dist_coeffs = np.zeros((4, 1))
        
        # Размер маркера в метрах (например, 0.05м = 5см)
        self.marker_size = 0.05
        
        # Последняя известная позиция
        self.last_position = np.array([-0.2, 1.0, -0.5])
        self.position_lock = threading.Lock()
        self.tracking_active = False
        
    def update_position(self):
        """Обновить позицию из камеры"""
        ret, frame = self.camera.read()
        if not ret:
            return False
        
        # Детектируем ArUco маркеры
        corners, ids, rejected = self.detector.detectMarkers(frame)
        
        if ids is not None and self.marker_id in ids:
            # Находим индекс нашего маркера
            idx = np.where(ids == self.marker_id)[0][0]
            
            # Оцениваем позу маркера
            rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
                [corners[idx]], self.marker_size, 
                self.camera_matrix, self.dist_coeffs
            )
            
            # Преобразуем в систему координат SteamVR
            # OpenCV: X-право, Y-вниз, Z-от камеры
            # SteamVR: X-право, Y-вверх, Z-назад (к игроку)
            tvec = tvecs[0][0]
            position = np.array([
                tvec[0],   # X остается
                -tvec[1],  # Y инвертируем (вниз -> вверх)
                -tvec[2]   # Z инвертируем (от камеры -> к игроку)
            ])
            
            with self.position_lock:
                self.last_position = position
                self.tracking_active = True
            
            # Рисуем маркер для визуализации
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            cv2.drawFrameAxes(frame, self.camera_matrix, self.dist_coeffs, 
                            rvecs[0], tvecs[0], 0.03)
            
            return True
        else:
            with self.position_lock:
                self.tracking_active = False
        
        # Показываем кадр
        cv2.imshow('ArUco Tracking', frame)
        cv2.waitKey(1)
        
        return False
    
    def get_position(self):
        """Получить последнюю известную позицию"""
        with self.position_lock:
            return self.last_position.copy(), self.tracking_active
    
    def close(self):
        self.camera.release()
        cv2.destroyAllWindows()


class GyroMouseReader:
    """Чтение данных от гироскопической мыши"""
    # change to this: HID\VID_2389&PID_00A8&REV_0200&MI_00 (SteamVR Controller)
    def __init__(self, vendor_id=0x2389, product_id=0x00a8): 
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.device = None
        self.current_rotation = Rotation.from_quat([0, 0, 0, 1])  # w, x, y, z
        self.rotation_lock = threading.Lock()
        
        if HID_AVAILABLE:
            self.open_device()
        else:
            print("Using simulated gyro data")
    
    def open_device(self):
        """Открыть HID устройство"""
        try:
            self.device = hid.device()
            self.device.open(self.vendor_id, self.product_id)
            self.device.set_nonblocking(True)
            print(f"Opened HID device {self.vendor_id:04x}:{self.product_id:04x}")
            return True
        except Exception as e:
            print(f"Failed to open HID device: {e}")
            self.device = None
            return False
    
    def read_gyro_data(self):
        """Прочитать данные гироскопа"""
        if self.device:
            try:
                data = self.device.read(64)
                if data:
                    # Парсим данные гироскопа (формат зависит от устройства!)
                    # Это пример - замените на реальный формат вашей мыши
                    gyro_x = struct.unpack('<h', bytes(data[10:12]))[0] / 32768.0 * 500  # градусов/сек
                    gyro_y = struct.unpack('<h', bytes(data[12:14]))[0] / 32768.0 * 500
                    gyro_z = struct.unpack('<h', bytes(data[14:16]))[0] / 32768.0 * 500
                    
                    return gyro_x, gyro_y, gyro_z, True
            except Exception as e:
                pass
        
        # Если нет устройства - симулируем вращение
        t = time.time()
        return (
            math.sin(t * 0.5) * 10,  # градусов/сек
            math.cos(t * 0.3) * 10,
            math.sin(t * 0.2) * 5,
            False
        )
    
    def update_rotation(self, dt):
        """Обновить ротацию из гироскопа"""
        gyro_x, gyro_y, gyro_z, real_data = self.read_gyro_data()
        
        # Интегрируем угловую скорость
        angle = math.sqrt(gyro_x**2 + gyro_y**2 + gyro_z**2)
        if angle > 0.001:
            axis = np.array([gyro_x, gyro_y, gyro_z]) / angle
            delta_rot = Rotation.from_rotvec(axis * math.radians(angle) * dt)
            
            with self.rotation_lock:
                self.current_rotation = delta_rot * self.current_rotation
        
        return gyro_x, gyro_y, gyro_z
    
    def get_quaternion(self):
        """Получить текущий кватернион"""
        with self.rotation_lock:
            quat = self.current_rotation.as_quat()  # [x, y, z, w]
            return quat[3], quat[0], quat[1], quat[2]  # w, x, y, z
    
    def close(self):
        if self.device:
            self.device.close()


class GyroMouseUDPSender:
    """Отправка данных по UDP"""
    def __init__(self, host='127.0.0.1', port=5556):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_number = 0
    
    def calculate_checksum(self, data):
        return sum(data) & 0xFF
    
    def send_data(self, quat, position, gyro, buttons):
        """Отправить данные контроллера"""
        # Формат: controller_id(1) + packet_num(4) + quat(16) + pos(12) + gyro(12) + buttons(2) + checksum(1)
        data = struct.pack('<BI4f3f3fHB',
            0,                          # controller_id (0 = гироскопическая мышь)
            self.packet_number,         # packet_number
            quat[0], quat[1], quat[2], quat[3],  # quat w,x,y,z
            position[0], position[1], position[2],  # pos x,y,z
            gyro[0], gyro[1], gyro[2],  # gyro x,y,z
            buttons,                    # buttons
            0                           # checksum placeholder
        )
        
        # Добавляем контрольную сумму
        checksum = self.calculate_checksum(data[:-1])
        data = data[:-1] + struct.pack('B', checksum)
        
        self.sock.sendto(data, (self.host, self.port))
        self.packet_number += 1


def main():
    print("=" * 60)
    print("GyroMouse + ArUco Tracker for SteamVR")
    print("=" * 60)
    print()
    print("Instructions:")
    print("1. Place ArUco marker (ID=0) in view of camera")
    print("2. The marker position will be used as controller position")
    print("3. Gyro mouse orientation will control rotation")
    print("4. Press Ctrl+C to stop")
    print()
    
    # Создаем компоненты
    aruco_tracker = ArUcoTracker(marker_id=0, camera_index=0)
    gyro_reader = GyroMouseReader(vendor_id=0x2389, product_id=0x00a8)
    udp_sender = GyroMouseUDPSender()
    
    # Поток для обновления ArUco позиции
    def aruco_update_thread():
        while running:
            aruco_tracker.update_position()
            time.sleep(0.033)  # 30 FPS
    
    running = True
    aruco_thread = threading.Thread(target=aruco_update_thread, daemon=True)
    aruco_thread.start()
    
    try:
        last_time = time.time()
        
        while True:
            now = time.time()
            dt = now - last_time
            last_time = now
            
            # Обновляем ротацию из гироскопа
            gyro_x, gyro_y, gyro_z = gyro_reader.update_rotation(dt)
            quat = gyro_reader.get_quaternion()
            
            # Получаем позицию из ArUco
            position, tracking = aruco_tracker.get_position()
            
            # Кнопки мыши (здесь всегда 0, можно добавить чтение реальных кнопок)
            buttons = 0
            
            # Отправляем данные
            udp_sender.send_data(quat, position, (gyro_x, gyro_y, gyro_z), buttons)
            
            # Выводим статус
            if udp_sender.packet_number % 100 == 0:
                status = "TRACKING" if tracking else "LOST"
                print(f"Packet {udp_sender.packet_number}: [{status}] "
                      f"Pos({position[0]:.2f}, {position[1]:.2f}, {position[2]:.2f}) "
                      f"Quat({quat[0]:.2f}, {quat[1]:.2f}, {quat[2]:.2f}, {quat[3]:.2f})")
            
            time.sleep(0.016)  # ~60 FPS
    
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        running = False
        aruco_tracker.close()
        gyro_reader.close()
        print("Done!")


if __name__ == "__main__":
    main()