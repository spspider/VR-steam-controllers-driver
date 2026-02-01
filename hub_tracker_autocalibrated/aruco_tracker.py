#!/usr/bin/env python3
"""
ArUco Tracker
Отслеживает позицию и ориентацию через ArUco маркер.
Отправляет данные по UDP на порт 5555 для драйвера SteamVR.
"""

import socket
import struct
import time
import math
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
import threading
import json
import os

class ArUcoTracker:
    """Отслеживание позиции и ориентации через ArUco маркер"""
    def __init__(self, camera_index=0):
        self.camera = cv2.VideoCapture(camera_index)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # ArUco словарь и детектор
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.aruco_params = cv2.aruco.DetectorParameters()
        # Настройка параметров для скорости
        self.aruco_params.adaptiveThreshWinSizeMin = 3
        self.aruco_params.adaptiveThreshWinSizeMax = 23
        self.aruco_params.adaptiveThreshWinSizeStep = 10
        self.aruco_params.adaptiveThreshConstant = 7
        self.aruco_params.minMarkerPerimeterRate = 0.03
        self.aruco_params.maxMarkerPerimeterRate = 4.0
        self.aruco_params.polygonalApproxAccuracyRate = 0.05
        self.aruco_params.minCornerDistanceRate = 0.05
        self.aruco_params.minDistanceToBorder = 3
        self.aruco_params.minMarkerDistanceRate = 0.05
        self.aruco_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_NONE  # Важно для скорости
        self.aruco_params.cornerRefinementWinSize = 5
        self.aruco_params.cornerRefinementMaxIterations = 30
        self.aruco_params.cornerRefinementMinAccuracy = 0.1
        self.aruco_params.markerBorderBits = 1
        self.aruco_params.perspectiveRemovePixelPerCell = 4
        self.aruco_params.perspectiveRemoveIgnoredMarginPerCell = 0.13
        self.aruco_params.maxErroneousBitsInBorderRate = 0.35
        self.aruco_params.errorCorrectionRate = 0.6
        self.aruco_params.useAruco3Detection = False
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
        
        # Калибровка
        self.calibration = self.load_calibration()
        
        # Последняя известная позиция и ориентация для обоих контроллеров
        self.controllers = {
            0: {  # Left controller
                'position': np.array([-0.2, 1.0, -0.5]),
                'quat': np.array([1, 0, 0, 0]),
                'tracking': False
            },
            1: {  # Right controller
                'position': np.array([0.2, 1.0, -0.5]),
                'quat': np.array([1, 0, 0, 0]),
                'tracking': False
            }
        }
        self.position_lock = threading.Lock()
        
    def load_calibration(self):
        """Загрузить калибровку из JSON"""
        try:
            with open('calibration.json', 'r') as f:
                return json.load(f)
        except:
            return {
                "position_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
                "position_scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                "rotation_offset": {"x": 0.0, "y": 0.0, "z": 0.0}
            }
    
    def apply_calibration(self, position, quat):
        """Применить калибровку к позиции и ориентации"""
        cal = self.calibration
        
        # Применяем масштаб и смещение позиции
        calibrated_pos = np.array([
            position[0] * cal["position_scale"]["x"] + cal["position_offset"]["x"],
            position[1] * cal["position_scale"]["y"] + cal["position_offset"]["y"],
            position[2] * cal["position_scale"]["z"] + cal["position_offset"]["z"]
        ])
        
        return calibrated_pos, quat
        
    def update_position(self):
        """Обновить позицию и ориентацию из камеры"""
        ret, frame = self.camera.read()
        if not ret:
            return False
        
        # Детектируем ArUco маркеры
        corners, ids, rejected = self.detector.detectMarkers(frame)
        
        # Обновляем статус трекинга для всех контроллеров
        with self.position_lock:
            for controller_id in self.controllers:
                self.controllers[controller_id]['tracking'] = False
        
        if ids is not None:
            for i, marker_id in enumerate(ids.flatten()):
                if marker_id in [0, 1]:  # Левый и правый контроллеры
                    obj_points = np.array([
                        [-self.marker_size/2, self.marker_size/2, 0],
                        [self.marker_size/2, self.marker_size/2, 0],
                        [self.marker_size/2, -self.marker_size/2, 0],
                        [-self.marker_size/2, -self.marker_size/2, 0]
                    ], dtype=np.float32)
                    img_points = corners[i][0].astype(np.float32)
                    retval, rvec, tvec = cv2.solvePnP(obj_points, img_points, self.camera_matrix, self.dist_coeffs)
                    
                    # Преобразуем в систему координат SteamVR
                    position = np.array([
                        float(tvec[0]),   # X остается
                        float(-tvec[1]),  # Y инвертируем (вниз -> вверх)
                        float(-tvec[2])   # Z инвертируем (от камеры -> к игроку)
                    ])
                    
                    # Получаем кватернион из rvec
                    rot = Rotation.from_rotvec(rvec.flatten())
                    quat = rot.as_quat()  # [x, y, z, w]
                    # Преобразуем в формат w, x, y, z
                    quat_wxyz = np.array([quat[3], quat[0], quat[1], quat[2]])
                    
                    # Применяем калибровку
                    position, quat_wxyz = self.apply_calibration(position, quat_wxyz)
                    
                    with self.position_lock:
                        self.controllers[marker_id]['position'] = position
                        self.controllers[marker_id]['quat'] = quat_wxyz
                        self.controllers[marker_id]['tracking'] = True
                    
                    # Рисуем маркер для визуализации
                    cv2.drawFrameAxes(frame, self.camera_matrix, self.dist_coeffs, 
                                    rvec, tvec, 0.03)
                    
                    # ОТЛАДОЧНАЯ ИНФОРМАЦИЯ НА ЭКРАНЕ
                    controller_name = "LEFT" if marker_id == 0 else "RIGHT"
                    text_y = 120 + (marker_id * 120)
                    
                    # Заголовок
                    cv2.putText(frame, f"{controller_name} Controller (ID={marker_id})", 
                               (10, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    
                    # Позиция
                    cv2.putText(frame, f"Position:", 
                               (10, text_y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    cv2.putText(frame, f"  X: {position[0]:+.3f}m", 
                               (10, text_y + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
                    cv2.putText(frame, f"  Y: {position[1]:+.3f}m", 
                               (10, text_y + 65), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
                    cv2.putText(frame, f"  Z: {position[2]:+.3f}m", 
                               (10, text_y + 85), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
                    
                    # Кватернион
                    cv2.putText(frame, f"Quaternion (w,x,y,z):", 
                               (10, text_y + 110), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                    cv2.putText(frame, f"  {quat_wxyz[0]:+.3f}, {quat_wxyz[1]:+.3f}, {quat_wxyz[2]:+.3f}, {quat_wxyz[3]:+.3f}", 
                               (10, text_y + 130), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 128, 0), 1)
            
            # Рисуем все обнаруженные маркеры
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        
        # Показываем кадр с кнопками управления
        self.draw_controls(frame)
        cv2.imshow('ArUco Tracking - Debug View', frame)
        key = cv2.waitKey(1) & 0xFF
        
        # Обработка клавиш
        if key == ord('c'):  # Калибровка
            self.calibrate_position()
        elif key == ord('r'):  # Сброс калибровки
            self.reset_calibration()
        
        return ids is not None and len(ids) > 0
    
    def draw_controls(self, frame):
        """Отобразить элементы управления на экране"""
        cv2.putText(frame, "Controls:", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, "C - Calibrate position", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, "R - Reset calibration", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Показываем текущие настройки
        cal = self.calibration
        cv2.putText(frame, f"Offset: X:{cal['position_offset']['x']:.2f} Y:{cal['position_offset']['y']:.2f} Z:{cal['position_offset']['z']:.2f}", 
                   (10, frame.shape[0] - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        cv2.putText(frame, f"Scale: X:{cal['position_scale']['x']:.2f} Y:{cal['position_scale']['y']:.2f} Z:{cal['position_scale']['z']:.2f}", 
                   (10, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    
    def calibrate_position(self):
        """Калибровка позиции - установить текущую позицию как центр"""
        with self.position_lock:
            for controller_id in [0, 1]:
                if self.controllers[controller_id]['tracking']:
                    pos = self.controllers[controller_id]['position']
                    # Устанавливаем смещение чтобы текущая позиция стала (0,0,0)
                    self.calibration['position_offset']['x'] = -float(pos[0])
                    self.calibration['position_offset']['y'] = -float(pos[1]) 
                    self.calibration['position_offset']['z'] = -float(pos[2])
                    self.save_calibration()
                    print(f"✓ Calibrated controller {controller_id} position to origin (0,0,0)")
                    print(f"  Previous position was: ({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f})")
                    break
    
    def reset_calibration(self):
        """Сбросить калибровку"""
        self.calibration = {
            "position_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
            "position_scale": {"x": 1.0, "y": 1.0, "z": 1.0},
            "rotation_offset": {"x": 0.0, "y": 0.0, "z": 0.0}
        }
        self.save_calibration()
        print("✓ Calibration reset to defaults")
    
    def save_calibration(self):
        """Сохранить калибровку в JSON"""
        with open('calibration.json', 'w') as f:
            json.dump(self.calibration, f, indent=2)
    
    def get_pose(self, controller_id):
        """Получить последнюю известную позицию и кватернион для контроллера"""
        with self.position_lock:
            controller = self.controllers[controller_id]
            return controller['position'].copy(), controller['quat'].copy(), controller['tracking']
    
    def close(self):
        self.camera.release()
        cv2.destroyAllWindows()


class UDPSender:
    """Отправка данных по UDP"""
    def __init__(self, host='127.0.0.1', port=5555):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_numbers = {0: 0, 1: 0}  # Отдельные номера пакетов для каждого контроллера
    
    def calculate_checksum(self, data):
        return sum(data) & 0xFF
    
    def send_data(self, controller_id, quat, accel, gyro, buttons, trigger):
        """Отправить данные контроллера"""
        # Формат: controller_id(1) + packet_num(4) + quat(16) + accel(12) + gyro(12) + buttons(2) + trigger(1) + checksum(1)
        data = struct.pack('<BI4f3f3fHBB',
            controller_id,              # uint8_t controller_id
            self.packet_numbers[controller_id],  # uint32_t packet_number
            float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3]),  # 4 floats quat (w,x,y,z)
            float(accel[0]), float(accel[1]), float(accel[2]),  # 3 floats - POSITION data (not acceleration!)
            float(gyro[0]), float(gyro[1]), float(gyro[2]),     # 3 floats gyro
            buttons,                    # uint16_t buttons
            trigger,                    # uint8_t trigger
            0                           # checksum placeholder
        )
        
        # Добавляем контрольную сумму
        checksum = self.calculate_checksum(data[:-1])
        data = data[:-1] + struct.pack('B', checksum)
        
        self.sock.sendto(data, (self.host, self.port))
        self.packet_numbers[controller_id] += 1


def main():
    print("=" * 60)
    print("ArUco Tracker for SteamVR - DEBUG VERSION")
    print("=" * 60)
    print()
    print("Instructions:")
    print("1. Place ArUco markers in view of camera:")
    print("   - ID=0 for LEFT controller")
    print("   - ID=1 for RIGHT controller")
    print("2. Press 'C' to calibrate position (set current as center)")
    print("3. Press 'R' to reset calibration")
    print("4. Press Ctrl+C to stop")
    print()
    print("NOTE: Position and Quaternion data shown on video feed")
    print()
    
    # Создаем компоненты
    aruco_tracker = ArUcoTracker(camera_index=0)
    udp_sender = UDPSender()
    
    # Поток для обновления ArUco позиции
    def aruco_update_thread():
        while running:
            aruco_tracker.update_position()
            time.sleep(0.033)  # 30 FPS
    
    running = True
    aruco_thread = threading.Thread(target=aruco_update_thread, daemon=True)
    aruco_thread.start()
    
    try:
        while True:
            # Отправляем данные для обоих контроллеров
            for controller_id in [0, 1]:  # Left and Right
                position, quat, tracking = aruco_tracker.get_pose(controller_id)
                
                # ВАЖНО: Передаем позицию через accel поля (именованные так исторически)
                accel = [float(position[0]), float(position[1]), float(position[2])]
                gyro = [0.0, 0.0, 0.0]  # Нет гироскопа
                buttons = 0
                trigger = 0
                
                udp_sender.send_data(controller_id, quat, accel, gyro, buttons, trigger)
                
                # Выводим статус каждые 100 пакетов
                if udp_sender.packet_numbers[controller_id] % 100 == 0:
                    status = "TRACKING" if tracking else "LOST"
                    controller_name = "LEFT " if controller_id == 0 else "RIGHT"
                    print(f"{controller_name} #{udp_sender.packet_numbers[controller_id]:6d}: [{status:8s}] "
                          f"Pos({float(position[0]):+.3f}, {float(position[1]):+.3f}, {float(position[2]):+.3f}) "
                          f"Quat({float(quat[0]):+.3f}, {float(quat[1]):+.3f}, {float(quat[2]):+.3f}, {float(quat[3]):+.3f})")
            
            time.sleep(0.016)  # ~60 FPS
    
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        running = False
        aruco_tracker.close()
        print("Done!")


if __name__ == "__main__":
    main()