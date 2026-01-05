#!/usr/bin/env python3
"""
Simple Mouse Movement Tracker for VR Controller
Tracks mouse cursor position and converts to VR controller movement
"""

import socket
import struct
import time
import math
import numpy as np

try:
    import win32gui
    import win32api
    WINDOWS_API_AVAILABLE = True
except ImportError:
    WINDOWS_API_AVAILABLE = False
    print("Warning: pywin32 not available, using simulation")

class SimpleMouseTracker:
    def __init__(self, host='127.0.0.1', port=5556):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_number = 0
        
        # Get screen dimensions
        if WINDOWS_API_AVAILABLE:
            self.screen_width = win32api.GetSystemMetrics(0)
            self.screen_height = win32api.GetSystemMetrics(1)
        else:
            self.screen_width = 1920
            self.screen_height = 1080
        
        self.center_x = self.screen_width // 2
        self.center_y = self.screen_height // 2
        
        print(f"Screen: {self.screen_width}x{self.screen_height}")
        print(f"Center: ({self.center_x}, {self.center_y})")
    
    def get_mouse_position(self):
        """Get current mouse position"""
        if WINDOWS_API_AVAILABLE:
            try:
                return win32gui.GetCursorPos()
            except:
                pass
        
        # Fallback simulation
        t = time.time()
        x = self.center_x + math.sin(t * 0.5) * 300
        y = self.center_y + math.cos(t * 0.3) * 200
        return int(x), int(y)
    
    def mouse_to_vr_position(self, mouse_x, mouse_y):
        """Convert mouse position to VR controller position"""
        # Normalize mouse position (-1 to 1)
        norm_x = (mouse_x - self.center_x) / (self.screen_width * 0.5)
        norm_y = (mouse_y - self.center_y) / (self.screen_height * 0.5)
        
        # Clamp to reasonable range
        norm_x = max(-1.0, min(1.0, norm_x))
        norm_y = max(-1.0, min(1.0, norm_y))
        
        # Convert to VR space\        # VR coordinates: X=left/right, Y=up/down, Z=forward/back
        vr_x = norm_x * 0.5  # ±0.5m left/right
        vr_y = 1.0 - norm_y * 0.3  # 0.7m to 1.3m height
        vr_z = -0.5 - norm_y * 0.3  # -0.2m to -0.8m forward/back
        
        return [vr_x, vr_y, vr_z]
    
    def create_rotation_from_mouse(self, mouse_x, mouse_y):
        """Create rotation quaternion from mouse position"""
        # Normalize mouse position
        norm_x = (mouse_x - self.center_x) / (self.screen_width * 0.5)
        norm_y = (mouse_y - self.center_y) / (self.screen_height * 0.5)
        
        # Create rotation angles (in radians)
        yaw = norm_x * 0.5    # Left/right rotation
        pitch = -norm_y * 0.3  # Up/down rotation
        roll = 0.0            # No roll from mouse
        
        # Convert to quaternion
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
    
    def send_controller_data(self, controller_id, quat, position, gyro, buttons):
        """Send controller data via UDP"""
        # Pack data according to MouseControllerData structure
        data = struct.pack('<BI4f3f3fHB',
            controller_id,
            self.packet_number,
            quat[0], quat[1], quat[2], quat[3],  # w, x, y, z
            position[0], position[1], position[2],
            gyro[0], gyro[1], gyro[2],
            buttons,
            0  # checksum placeholder
        )
        
        # Calculate checksum
        checksum = sum(data[:-1]) & 0xFF
        data = data[:-1] + struct.pack('B', checksum)
        
        self.sock.sendto(data, (self.host, self.port))
        self.packet_number += 1
    
    def run(self):
        print("=== Simple Mouse VR Controller ===")
        print("Move your mouse to control the VR controller")
        print("The controller will follow your mouse cursor")
        print("Press Ctrl+C to stop")
        print()
        
        try:
            while True:
                # Get mouse position
                mouse_x, mouse_y = self.get_mouse_position()
                
                # Convert to VR position and rotation
                position = self.mouse_to_vr_position(mouse_x, mouse_y)
                quat = self.create_rotation_from_mouse(mouse_x, mouse_y)
                
                # Simulate gyro data (could be real gyro data)
                t = time.time()
                gyro = [
                    math.sin(t * 0.7) * 5,   # X gyro
                    math.cos(t * 0.5) * 5,   # Y gyro
                    math.sin(t * 0.3) * 3    # Z gyro
                ]
                
                # No buttons pressed
                buttons = 0
                
                # Send data (controller_id=0 for left hand)
                self.send_controller_data(0, quat, position, gyro, buttons)
                
                # Status output every 2 seconds
                if self.packet_number % 120 == 0:
                    print(f"Mouse({mouse_x:4d}, {mouse_y:4d}) -> "
                          f"VR({position[0]:5.2f}, {position[1]:5.2f}, {position[2]:5.2f}) "
                          f"Rot({quat[0]:4.2f}, {quat[1]:4.2f}, {quat[2]:4.2f}, {quat[3]:4.2f})")
                
                time.sleep(0.016)  # ~60 FPS
        
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            self.sock.close()
            print("Done!")

def main():
    tracker = SimpleMouseTracker()
    tracker.run()

if __name__ == "__main__":
    main()