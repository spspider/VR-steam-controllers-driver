#!/usr/bin/env python3
"""
Simple Controller Simulator
Simulates controller position and rotation without any hardware.
Controllers orbit around you in a circle pattern.
"""
import socket
import struct
import time
import math

class SimpleControllerSimulator:
    def __init__(self, host='127.0.0.1', port=5555):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_numbers = {0: 0, 1: 0}  # Separate packet numbers for each controller
    
    def calculate_checksum(self, data):
        return sum(data) & 0xFF
    
    def pack_controller_data(self, controller_id, quat, position, gyro, buttons, trigger):
        """
        Pack controller data. NOTE: 'accel' fields contain POSITION data!
        """
        data = struct.pack('<BI4f3f3fHBB', 
            controller_id,                              # uint8_t
            self.packet_numbers[controller_id],         # uint32_t
            quat[0], quat[1], quat[2], quat[3],        # 4 floats (w,x,y,z)
            position[0], position[1], position[2],      # 3 floats - POSITION (in accel fields)
            gyro[0], gyro[1], gyro[2],                 # 3 floats - gyroscope
            buttons,                                    # uint16_t
            trigger,                                    # uint8_t
            0                                           # checksum placeholder uint8_t
        )
        
        # Calculate and add checksum
        checksum = self.calculate_checksum(data[:-1])
        data = data[:-1] + struct.pack('B', checksum)
        
        self.packet_numbers[controller_id] += 1
        return data
    
    def get_simulated_data(self, controller_id, t):
        """
        Generate simulated position and rotation for a controller.
        Controllers orbit in a circle pattern at chest height.
        """
        # Different orbit parameters for each controller
        if controller_id == 0:  # Left controller
            orbit_radius = 0.3      # 30cm from center
            orbit_speed = 0.5       # Slow orbit
            base_angle = 0          # Start on left
        else:  # Right controller
            orbit_radius = 0.3      # 30cm from center
            orbit_speed = 0.5       # Slow orbit
            base_angle = math.pi    # Start on right
        
        # Calculate orbit position
        angle = t * orbit_speed + base_angle
        
        # Position in 3D space (meters)
        # X: left(-) to right(+)
        # Y: down(-) to up(+) 
        # Z: away(-) to close(+)
        position = [
            math.cos(angle) * orbit_radius,     # X - circular motion
            1.2 + math.sin(t * 0.3) * 0.1,     # Y - chest height with slight bob
            -0.5 + math.sin(angle) * orbit_radius  # Z - forward/back with orbit
        ]
        
        # Quaternion - rotate to face the direction of movement
        # Rotating around Y axis (yaw)
        rot_angle = angle + math.pi / 2  # Face direction of travel
        quat = [
            math.cos(rot_angle / 2),    # w
            0.0,                        # x
            math.sin(rot_angle / 2),    # y
            0.0                         # z
        ]
        
        # Gyroscope - angular velocity (rad/s)
        gyro = [
            0.0,                            # X - no pitch rotation
            orbit_speed,                    # Y - yaw rotation speed
            0.0                             # Z - no roll rotation
        ]
        
        # Simulate button presses (cycle through buttons every 3 seconds)
        buttons = 0
        button_cycle = int(t / 3) % 5
        if button_cycle == 0:
            buttons |= 0x01  # Trigger
        elif button_cycle == 1:
            buttons |= 0x02  # Grip
        elif button_cycle == 2:
            buttons |= 0x04  # Menu
        elif button_cycle == 3:
            buttons |= 0x08  # System
        # button_cycle == 4: no buttons pressed
        
        # Simulate trigger pull (sine wave 0-255)
        trigger = int((math.sin(t * 0.5) + 1) * 127.5)
        
        return quat, position, gyro, buttons, trigger
    
    def run(self):
        print("=" * 60)
        print("Simple Controller Simulator - Position Based")
        print("=" * 60)
        print(f"Sending to: {self.host}:{self.port}")
        print()
        print("Simulation:")
        print("  - 2 controllers orbiting in a circle")
        print("  - At chest height (~1.2m)")
        print("  - Radius: 30cm from center")
        print("  - Slow rotation with button presses")
        print()
        print("Press Ctrl+C to stop")
        print("=" * 60)
        print()
        
        try:
            start_time = time.time()
            last_print = 0
            
            while True:
                current_time = time.time() - start_time
                
                # Send data for both controllers
                for controller_id in [0, 1]:  # Left (0) and Right (1) controllers
                    quat, position, gyro, buttons, trigger = self.get_simulated_data(controller_id, current_time)
                    packet = self.pack_controller_data(controller_id, quat, position, gyro, buttons, trigger)
                    self.sock.sendto(packet, (self.host, self.port))
                
                # Print status every second
                if current_time - last_print >= 1.0:
                    left_quat, left_pos, _, left_buttons, left_trigger = self.get_simulated_data(0, current_time)
                    right_quat, right_pos, _, right_buttons, right_trigger = self.get_simulated_data(1, current_time)
                    
                    print(f"[{current_time:6.1f}s] LEFT : Pos({left_pos[0]:+.3f}, {left_pos[1]:+.3f}, {left_pos[2]:+.3f}) "
                          f"Quat({left_quat[0]:+.3f}, {left_quat[1]:+.3f}, {left_quat[2]:+.3f}, {left_quat[3]:+.3f}) "
                          f"Buttons:0x{left_buttons:02X} Trigger:{left_trigger:3d}")
                    print(f"[{current_time:6.1f}s] RIGHT: Pos({right_pos[0]:+.3f}, {right_pos[1]:+.3f}, {right_pos[2]:+.3f}) "
                          f"Quat({right_quat[0]:+.3f}, {right_quat[1]:+.3f}, {right_quat[2]:+.3f}, {right_quat[3]:+.3f}) "
                          f"Buttons:0x{right_buttons:02X} Trigger:{right_trigger:3d}")
                    print()
                    last_print = current_time
                
                time.sleep(0.016)  # ~60 FPS
                
        except KeyboardInterrupt:
            print("\n" + "=" * 60)
            print("Stopping simulator...")
            print("=" * 60)
        finally:
            self.sock.close()

if __name__ == "__main__":
    simulator = SimpleControllerSimulator()
    simulator.run()