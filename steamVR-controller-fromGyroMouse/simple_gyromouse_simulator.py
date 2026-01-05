#!/usr/bin/env python3
"""
Простой симулятор гироскопической мыши БЕЗ камеры
Для тестирования драйвера перед подключением реального железа
"""

import socket
import struct
import time
import math

class GyroMouseSimulator:
    def __init__(self, host='127.0.0.1', port=5556):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_number = 0
    
    def calculate_checksum(self, data):
        return sum(data) & 0xFF
    
    def pack_data(self, quat, position, gyro, buttons):
        """Упаковать данные контроллера"""
        # Формат: controller_id(1) + packet_num(4) + quat(16) + pos(12) + gyro(12) + buttons(2) + checksum(1)
        # Всего: 48 байт (соответствует MouseControllerData)
        data = struct.pack('<BI4f3f3fHB',
            0,                          # controller_id
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
        
        self.packet_number += 1
        return data
    
    def simulate_movement(self, t):
        """Симулировать движение контроллера"""
        # Вращение вокруг Y оси
        angle = t * 0.3
        quat = [
            math.cos(angle/2),  # w
            0.0,                # x
            math.sin(angle/2),  # y
            0.0                 # z
        ]
        
        # Позиция - движение по кругу
        radius = 0.3
        position = [
            math.sin(t * 0.5) * radius,      # X - влево-вправо
            1.0 + math.sin(t * 0.8) * 0.1,   # Y - вверх-вниз
            -0.5 + math.cos(t * 0.5) * radius  # Z - вперед-назад
        ]
        
        # Угловая скорость (градусы/сек)
        gyro = [
            math.sin(t * 0.2) * 10,  # X
            30.0,                    # Y - постоянное вращение
            math.cos(t * 0.4) * 5    # Z
        ]
        
        # Кнопки - мигают
        buttons = 0
        if int(t) % 2 == 0:
            buttons |= 0x01  # Левая кнопка
        if int(t * 2) % 3 == 0:
            buttons |= 0x02  # Правая кнопка
        
        return quat, position, gyro, buttons
    
    def run(self):
        print("=" * 60)
        print("GyroMouse Simulator (without camera)")
        print("=" * 60)
        print(f"Sending data to {self.host}:{self.port}")
        print("Simulating rotating gyro mouse movement")
        print("Press Ctrl+C to stop")
        print()
        
        try:
            start_time = time.time()
            
            while True:
                t = time.time() - start_time
                
                # Симулируем движение
                quat, position, gyro, buttons = self.simulate_movement(t)
                
                # Упаковываем и отправляем данные
                packet = self.pack_data(quat, position, gyro, buttons)
                self.sock.sendto(packet, (self.host, self.port))
                
                # Логируем каждые 100 пакетов
                if self.packet_number % 100 == 0:
                    print(f"Packet {self.packet_number}: "
                          f"Pos({position[0]:6.2f}, {position[1]:6.2f}, {position[2]:6.2f}) "
                          f"Quat({quat[0]:.2f}, {quat[1]:.2f}, {quat[2]:.2f}, {quat[3]:.2f})")
                
                time.sleep(0.016)  # ~60 FPS
        
        except KeyboardInterrupt:
            print("\nStopping simulator...")
        finally:
            self.sock.close()
            print("Done!")


if __name__ == "__main__":
    simulator = GyroMouseSimulator()
    simulator.run()