#!/usr/bin/env python3
"""
Complete VR System Simulator - Controllers + HMD
Simulates controller position and rotation WITHOUT any hardware.
- Controllers orbit around the player in a circle pattern
- HMD (player/head) moves forward/back and side-to-side
- Full 3D motion for immersive testing
"""
import socket
import struct
import time
import math

class CompleteVRSimulator:
    def __init__(self, host='127.0.0.1', port=5555):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_numbers = {0: 0, 1: 0, 2: 0}  # Separate packet numbers for each device
    
    def calculate_checksum(self, data):
        return sum(data) & 0xFF
    
    def pack_device_data(self, device_id, quat, position, gyro, buttons=0, trigger=0):
        """
        Pack device data (controller or HMD)
        NOTE: 'accel' fields contain POSITION data!
        
        device_id:
            0 = LEFT controller
            1 = RIGHT controller
            2 = HMD (player/head)
        """
        data = struct.pack('<BI4f3f3fHBB', 
            device_id,                              # uint8_t (0=left, 1=right, 2=HMD)
            self.packet_numbers[device_id],         # uint32_t packet number
            quat[0], quat[1], quat[2], quat[3],    # 4 floats (w,x,y,z) quaternion
            position[0], position[1], position[2],  # 3 floats - POSITION (X, Y, Z in meters)
            gyro[0], gyro[1], gyro[2],             # 3 floats - gyroscope/angular velocity
            buttons,                                # uint16_t button bitmask
            trigger,                                # uint8_t trigger value (0-255)
            0                                       # checksum placeholder uint8_t
        )
        
        # Calculate and add checksum
        checksum = self.calculate_checksum(data[:-1])
        data = data[:-1] + struct.pack('B', checksum)
        
        self.packet_numbers[device_id] += 1
        return data
    
    def get_hmd_data(self, t):
        """
        Generate simulated HMD (player/head) position and orientation.
        
        Motion pattern:
        - Forward/back movement (Z axis)
        - Side-to-side strafe (X axis)
        - Vertical movement (Y axis) - up/down
        - Slow head rotation (yaw)
        """
        # HMD position (meters)
        # Start at center (0, 1.6, 0) = eye level height
        
        # Forward/back motion - walk forward and back
        # Period: 8 seconds (4 sec forward, 4 sec back)
        z_motion = math.sin(t * 0.25) * 0.5  # ±0.5 meters forward/back
        
        # Side-to-side strafe - sway left and right
        # Period: 6 seconds
        x_motion = math.sin(t * 0.3) * 0.3   # ±0.3 meters left/right
        
        # Vertical bob - slight up/down motion like walking
        # Period: 2 seconds, amplitude: ±0.1 meters
        y_base = 1.6  # Eye level height (160cm)
        y_motion = y_base + math.sin(t * 1.5) * 0.1
        
        # HMD position
        position = [
            x_motion,           # X - side to side
            y_motion,           # Y - up/down with walking bob
            z_motion            # Z - forward/back
        ]
        
        # HMD orientation - slight rotation, looking around
        # Yaw - turn left/right slowly
        yaw = math.sin(t * 0.2) * 0.3  # ±0.3 radians (±17 degrees)
        
        # Pitch - look up/down slightly (like normal head movement while walking)
        pitch = math.sin(t * 0.15) * 0.1  # ±0.1 radians (±5 degrees)
        
        # Roll - slight tilt
        roll = 0.0
        
        # Convert Euler angles to quaternion
        quat = self.euler_to_quaternion(yaw, pitch, roll)
        
        # HMD gyroscope (angular velocity in rad/s)
        gyro = [
            0.0,                        # X - pitch velocity
            math.cos(t * 0.2) * 0.1,  # Y - yaw velocity (looking around)
            0.0                         # Z - roll velocity
        ]
        
        return quat, position, gyro
    
    def get_controller_data(self, controller_id, t):
        """
        Generate simulated controller position and rotation.
        Controllers orbit around the player in a circle pattern.
        """
        # Different orbit parameters for each controller
        if controller_id == 0:  # Left controller
            orbit_radius = 0.3      # 30cm from center
            orbit_speed = 0.5       # Slow orbit
            base_angle = 0          # Start on left
        else:  # Right controller (controller_id == 1)
            orbit_radius = 0.3      # 30cm from center
            orbit_speed = 0.5       # Slow orbit
            base_angle = math.pi    # Start on right (opposite side)
        
        # Calculate orbit position around the player
        angle = t * orbit_speed + base_angle
        
        # Position in 3D space relative to player (meters)
        # Controllers orbit around player's center point
        position = [
            math.cos(angle) * orbit_radius,         # X - circular motion left/right
            1.2 + math.sin(t * 0.3) * 0.1,         # Y - chest height with slight bob
            -0.5 + math.sin(angle) * orbit_radius   # Z - forward/back with orbit
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
            orbit_speed,                    # Y - yaw rotation speed (orbiting)
            0.0                             # Z - no roll rotation
        ]
        
        # Simulate button presses (cycle through buttons every 3 seconds)
        buttons = 0
        button_cycle = int(t / 3) % 5
        if button_cycle == 0:
            buttons |= 0x01  # Trigger click
        elif button_cycle == 1:
            buttons |= 0x02  # Grip click
        elif button_cycle == 2:
            buttons |= 0x04  # Application menu
        elif button_cycle == 3:
            buttons |= 0x08  # System button
        # button_cycle == 4: no buttons pressed
        
        # Simulate trigger pull (sine wave 0-255)
        trigger = int((math.sin(t * 0.5) + 1) * 127.5)
        
        return quat, position, gyro, buttons, trigger
    
    def euler_to_quaternion(self, yaw, pitch, roll):
        """Convert Euler angles (radians) to quaternion (w, x, y, z)"""
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
    
    def run(self):
        print("=" * 80)
        print(" " * 20 + "Complete VR System Simulator")
        print("=" * 80)
        print(f"Host: {self.host}:{self.port}")
        print()
        print("Simulated Motion:")
        print("  ┌─ HMD (Player/Head) - Device ID 2")
        print("  │  ├─ Position: Moves forward/back (±0.5m), left/right (±0.3m)")
        print("  │  ├─ Height: Eye level (~1.6m) with walking bob (±0.1m)")
        print("  │  └─ Rotation: Looks around (yaw ±17°, pitch ±5°)")
        print("  │")
        print("  ├─ LEFT Controller - Device ID 0")
        print("  │  ├─ Position: Orbits around player (30cm radius)")
        print("  │  ├─ Height: Chest level (~1.2m)")
        print("  │  └─ Rotation: Faces orbit direction")
        print("  │")
        print("  └─ RIGHT Controller - Device ID 1")
        print("     ├─ Position: Orbits around player (30cm radius, opposite side)")
        print("     ├─ Height: Chest level (~1.2m)")
        print("     └─ Rotation: Faces orbit direction")
        print()
        print("Button simulation: Cycles through trigger, grip, menu, system every 3 sec")
        print()
        print("Press Ctrl+C to stop")
        print("=" * 80)
        print()
        
        try:
            start_time = time.time()
            last_print = 0
            packet_count = 0
            
            while True:
                current_time = time.time() - start_time
                
                # ===== SEND HMD DATA =====
                hmd_quat, hmd_pos, hmd_gyro = self.get_hmd_data(current_time)
                packet = self.pack_device_data(2, hmd_quat, hmd_pos, hmd_gyro, buttons=0, trigger=0)
                self.sock.sendto(packet, (self.host, self.port))
                packet_count += 1
                
                # ===== SEND LEFT CONTROLLER =====
                left_quat, left_pos, left_gyro, left_btn, left_trg = self.get_controller_data(0, current_time)
                packet = self.pack_device_data(0, left_quat, left_pos, left_gyro, left_btn, left_trg)
                self.sock.sendto(packet, (self.host, self.port))
                packet_count += 1
                
                # ===== SEND RIGHT CONTROLLER =====
                right_quat, right_pos, right_gyro, right_btn, right_trg = self.get_controller_data(1, current_time)
                packet = self.pack_device_data(1, right_quat, right_pos, right_gyro, right_btn, right_trg)
                self.sock.sendto(packet, (self.host, self.port))
                packet_count += 1
                
                # Print status every 2 seconds
                if current_time - last_print >= 2.0:
                    print(f"[{current_time:7.1f}s] Packets sent: {packet_count} (Rate: {packet_count/(current_time+0.001):.0f} pkt/sec)")
                    print(f"  ├─ HMD    : Pos({hmd_pos[0]:+.3f}, {hmd_pos[1]:+.3f}, {hmd_pos[2]:+.3f}) "
                          f"Quat({hmd_quat[0]:+.3f}, {hmd_quat[1]:+.3f}, {hmd_quat[2]:+.3f}, {hmd_quat[3]:+.3f})")
                    print(f"  ├─ LEFT   : Pos({left_pos[0]:+.3f}, {left_pos[1]:+.3f}, {left_pos[2]:+.3f}) "
                          f"Buttons:0x{left_btn:02X} Trigger:{left_trg:3d}")
                    print(f"  └─ RIGHT  : Pos({right_pos[0]:+.3f}, {right_pos[1]:+.3f}, {right_pos[2]:+.3f}) "
                          f"Buttons:0x{right_btn:02X} Trigger:{right_trg:3d}")
                    print()
                    last_print = current_time
                
                time.sleep(0.016)  # ~60 FPS (16.6ms per frame)
                
        except KeyboardInterrupt:
            print("\n" + "=" * 80)
            print(f"Stopped. Total packets sent: {packet_count}")
            print("=" * 80)
        finally:
            self.sock.close()


if __name__ == "__main__":
    import sys
    
    # Parse command line arguments
    host = "127.0.0.1"
    port = 5555
    
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    print()
    simulator = CompleteVRSimulator(host, port)
    simulator.run()