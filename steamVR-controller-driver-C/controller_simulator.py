#!/usr/bin/env python3
import socket
import struct
import time
import math
import pygame
import sys

# ControllerData structure (49 bytes total)
# uint8_t controller_id, uint32_t packet_number, 4 floats quat, 3 floats accel, 3 floats gyro, uint16_t buttons, uint8_t trigger, uint8_t checksum

class ControllerSimulator:
    def __init__(self, host='127.0.0.1', port=5555):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_number = 0
        
        # Initialize pygame for joystick input
        pygame.init()
        pygame.joystick.init()
        
        self.joysticks = []
        for i in range(pygame.joystick.get_count()):
            joy = pygame.joystick.Joystick(i)
            joy.init()
            self.joysticks.append(joy)
            print(f"Found joystick {i}: {joy.get_name()}")
        
        if not self.joysticks:
            print("No joysticks found! Using keyboard simulation.")
            self.use_keyboard = True
        else:
            self.use_keyboard = False
    
    def calculate_checksum(self, data):
        return sum(data) & 0xFF
    
    def pack_controller_data(self, controller_id, quat, accel, gyro, buttons, trigger):
        # Pack data according to ControllerData struct
        data = struct.pack('<BI4f3f3fHBB', 
            controller_id,      # uint8_t
            self.packet_number, # uint32_t
            quat[0], quat[1], quat[2], quat[3],  # 4 floats (w,x,y,z)
            accel[0], accel[1], accel[2],        # 3 floats
            gyro[0], gyro[1], gyro[2],           # 3 floats
            buttons,            # uint16_t
            trigger,            # uint8_t
            0                   # checksum placeholder
        )
        
        # Calculate and add checksum
        checksum = self.calculate_checksum(data[:-1])
        data = data[:-1] + struct.pack('B', checksum)
        
        self.packet_number += 1
        return data
    
    def get_joystick_data(self, joy_index):
        if joy_index >= len(self.joysticks):
            return None
            
        joy = self.joysticks[joy_index]
        
        # Get orientation from joystick axes (simulate quaternion)
        x_axis = joy.get_axis(0) if joy.get_numaxes() > 0 else 0.0
        y_axis = joy.get_axis(1) if joy.get_numaxes() > 1 else 0.0
        z_axis = joy.get_axis(2) if joy.get_numaxes() > 2 else 0.0
        
        # Convert to quaternion (simplified)
        angle_x = x_axis * 0.5
        angle_y = y_axis * 0.5
        angle_z = z_axis * 0.5
        
        quat = [
            math.cos(angle_x/2) * math.cos(angle_y/2) * math.cos(angle_z/2),  # w
            math.sin(angle_x/2) * math.cos(angle_y/2) * math.cos(angle_z/2),  # x
            math.cos(angle_x/2) * math.sin(angle_y/2) * math.cos(angle_z/2),  # y
            math.cos(angle_x/2) * math.cos(angle_y/2) * math.sin(angle_z/2)   # z
        ]
        
        # Simulate accelerometer (based on movement)
        accel = [x_axis * 2.0, y_axis * 2.0, 9.81]  # Include gravity
        
        # Simulate gyroscope
        gyro = [x_axis * 0.1, y_axis * 0.1, z_axis * 0.1]
        
        # Get buttons
        buttons = 0
        for i in range(min(joy.get_numbuttons(), 16)):
            if joy.get_button(i):
                buttons |= (1 << i)
        
        # Get trigger (from axis or button)
        trigger = 0
        if joy.get_numaxes() > 3:
            trigger_val = (joy.get_axis(3) + 1.0) / 2.0  # Convert from -1,1 to 0,1
            trigger = int(trigger_val * 255)
        
        return quat, accel, gyro, buttons, trigger
    
    def get_keyboard_data(self, controller_id):
        # Simple keyboard simulation
        t = time.time()
        
        # Rotating quaternion for demo
        angle = t * 0.5
        quat = [math.cos(angle/2), 0, math.sin(angle/2), 0]
        
        # Simulate some movement
        accel = [math.sin(t), math.cos(t), 9.81]
        gyro = [0.1, 0.1, 0.1]
        
        # Simulate button presses
        buttons = int(t) % 4  # Cycle through first 4 buttons
        trigger = int((math.sin(t) + 1) * 127.5)  # 0-255
        
        return quat, accel, gyro, buttons, trigger
    
    def run(self):
        print(f"Starting controller simulator on {self.host}:{self.port}")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                pygame.event.pump()  # Process pygame events
                
                # Send data for left controller (ID 0)
                if self.use_keyboard or len(self.joysticks) == 0:
                    quat, accel, gyro, buttons, trigger = self.get_keyboard_data(0)
                else:
                    data = self.get_joystick_data(0)
                    if data:
                        quat, accel, gyro, buttons, trigger = data
                    else:
                        quat, accel, gyro, buttons, trigger = self.get_keyboard_data(0)
                
                packet = self.pack_controller_data(0, quat, accel, gyro, buttons, trigger)
                self.sock.sendto(packet, (self.host, self.port))
                
                # Send data for right controller (ID 1)
                if len(self.joysticks) > 1:
                    data = self.get_joystick_data(1)
                    if data:
                        quat, accel, gyro, buttons, trigger = data
                        packet = self.pack_controller_data(1, quat, accel, gyro, buttons, trigger)
                        self.sock.sendto(packet, (self.host, self.port))
                else:
                    # Use keyboard data with slight offset for right controller
                    quat, accel, gyro, buttons, trigger = self.get_keyboard_data(1)
                    quat[1] *= -1  # Mirror X rotation
                    packet = self.pack_controller_data(1, quat, accel, gyro, buttons, trigger)
                    self.sock.sendto(packet, (self.host, self.port))
                
                print(f"Sent packet {self.packet_number-1}, buttons: {buttons:04b}, trigger: {trigger}")
                time.sleep(0.016)  # ~60 FPS
                
        except KeyboardInterrupt:
            print("\nStopping simulator...")
        finally:
            self.sock.close()
            pygame.quit()

if __name__ == "__main__":
    simulator = ControllerSimulator()
    simulator.run()