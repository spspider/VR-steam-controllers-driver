import socket
import struct
import time
import random

class ControllerData:
    def __init__(self, controller_id=0):
        self.controller_id = controller_id
        self.packet_number = 0
        self.quat_w, self.quat_x, self.quat_y, self.quat_z = 1.0, 0.0, 0.0, 0.0
        self.accel_x, self.accel_y, self.accel_z = 0.0, 9.8, 0.0
        self.gyro_x, self.gyro_y, self.gyro_z = 0.0, 0.0, 0.0
        self.buttons = 0
        self.trigger = 0
        self.checksum = 0
    
    def to_bytes(self):
        # Упаковываем структуру
        data = struct.pack('B I fffff fffff H B B',
            self.controller_id,
            self.packet_number,
            self.quat_w, self.quat_x, self.quat_y, self.quat_z,
            self.accel_x, self.accel_y, self.accel_z,
            self.gyro_x, self.gyro_y, self.gyro_z,
            self.buttons,
            self.trigger,
            self.checksum
        )
        
        # Вычисляем контрольную сумму (сумма всех байтов кроме checksum)
        self.checksum = sum(data[:-1]) & 0xFF
        
        # Переупаковываем с правильной контрольной суммой
        data = struct.pack('B I fffff fffff H B B',
            self.controller_id,
            self.packet_number,
            self.quat_w, self.quat_x, self.quat_y, self.quat_z,
            self.accel_x, self.accel_y, self.accel_z,
            self.gyro_x, self.gyro_y, self.gyro_z,
            self.buttons,
            self.trigger,
            self.checksum
        )
        
        return data

def send_test_data():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ('127.0.0.1', 5555)
    
    left_controller = ControllerData(0)
    right_controller = ControllerData(1)
    
    print("Sending test UDP packets to 127.0.0.1:5555")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            # Левый контроллер
            left_controller.packet_number += 1
            left_controller.quat_x = random.uniform(-0.1, 0.1)
            left_controller.quat_y = random.uniform(-0.1, 0.1)
            left_controller.buttons = 1 if random.random() > 0.5 else 0
            left_controller.trigger = random.randint(0, 255)
            
            sock.sendto(left_controller.to_bytes(), server_address)
            
            # Правый контроллер
            right_controller.packet_number += 1
            right_controller.quat_x = random.uniform(-0.1, 0.1)
            right_controller.quat_y = random.uniform(-0.1, 0.1)
            right_controller.buttons = 1 if random.random() > 0.5 else 0
            right_controller.trigger = random.randint(0, 255)
            
            sock.sendto(right_controller.to_bytes(), server_address)
            
            time.sleep(0.01)  # ~100 Hz
            
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        sock.close()

if __name__ == "__main__":
    send_test_data()