#!/usr/bin/env python3
import socket
import struct
import time
import math

class SimpleControllerSimulator:
    def __init__(self, host='127.0.0.1', port=5555):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_number = 0
    
    def calculate_checksum(self, data):
        return sum(data) & 0xFF
    
    def pack_controller_data(self, controller_id, quat, accel, gyro, buttons, trigger):
        # Pack data according to ControllerData struct (49 bytes)
        data = struct.pack('<BI4f3f3fHBB', 
            controller_id,      # uint8_t
            self.packet_number, # uint32_t
            quat[0], quat[1], quat[2], quat[3],  # 4 floats (w,x,y,z)
            accel[0], accel[1], accel[2],        # 3 floats
            gyro[0], gyro[1], gyro[2],           # 3 floats
            buttons,            # uint16_t
            trigger,            # uint8_t
            0                   # checksum placeholder uint8_t
        )
        
        # Calculate and add checksum
        checksum = self.calculate_checksum(data[:-1])
        data = data[:-1] + struct.pack('B', checksum)
        
        self.packet_number += 1
        return data
    
    def get_simulated_data(self, controller_id, t):
        # Create rotating motion for demo
        angle = t * 0.3 + (controller_id * math.pi)  # Different phase for each controller
        
        # Quaternion rotation around Y axis
        quat = [
            math.cos(angle/2),  # w
            0.0,                # x
            math.sin(angle/2),  # y
            0.0                 # z
        ]
        
        # Simulate accelerometer with some movement
        accel = [
            math.sin(t * 0.5) * 2.0,  # X acceleration
            math.cos(t * 0.3) * 1.0,  # Y acceleration
            9.81 + math.sin(t) * 0.5  # Z with gravity + variation
        ]
        
        # Simulate gyroscope
        gyro = [
            math.sin(t * 0.2) * 0.1,  # X angular velocity
            0.3,                      # Y angular velocity (constant rotation)
            math.cos(t * 0.4) * 0.05  # Z angular velocity
        ]
        
        # Simulate button presses (cycle through buttons)
        buttons = 0
        button_cycle = int(t * 0.5) % 8  # Change every 2 seconds
        if button_cycle < 4:
            buttons |= (1 << button_cycle)
        
        # Simulate trigger (sine wave 0-255)
        trigger = int((math.sin(t * 0.8) + 1) * 127.5)
        
        return quat, accel, gyro, buttons, trigger
    
    def run(self):
        print(f"Starting simple controller simulator on {self.host}:{self.port}")
        print("Simulating 2 controllers with rotating motion and button presses")
        print("Press Ctrl+C to stop")
        
        try:
            start_time = time.time()
            while True:
                current_time = time.time() - start_time
                
                # Send data for both controllers
                for controller_id in [0, 1]:  # Left and right controllers
                    quat, accel, gyro, buttons, trigger = self.get_simulated_data(controller_id, current_time)
                    packet = self.pack_controller_data(controller_id, quat, accel, gyro, buttons, trigger)
                    self.sock.sendto(packet, (self.host, self.port))
                
                print(f"Packet {self.packet_number-1}: Controllers active, time: {current_time:.1f}s")
                time.sleep(0.016)  # ~60 FPS
                
        except KeyboardInterrupt:
            print("\nStopping simulator...")
        finally:
            self.sock.close()

if __name__ == "__main__":
    simulator = SimpleControllerSimulator()
    simulator.run()