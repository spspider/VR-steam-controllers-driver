#!/usr/bin/env python3
"""
Debug Receiver for ArUco Controller Data
Intercepts UDP packets on port 5555 and displays position/rotation data
Prints detailed info every 30 packets for each controller
"""

import socket
import struct
import time
from collections import defaultdict

class ControllerDebugReceiver:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.sock.settimeout(1.0)
        
        # Packet counters for each controller
        self.packet_counts = defaultdict(int)
        self.last_data = {}
        
    def verify_checksum(self, data):
        """Verify packet checksum"""
        if len(data) != 49:
            return False
        
        checksum = sum(data[:-1]) & 0xFF
        return checksum == data[-1]
    
    def parse_packet(self, data):
        """Parse ControllerData struct (49 bytes)"""
        if len(data) != 49:
            return None
        
        try:
            # Unpack the binary data
            # Format: <BI4f3f3fHBB
            unpacked = struct.unpack('<BI4f3f3fHBB', data)
            
            return {
                'controller_id': unpacked[0],
                'packet_number': unpacked[1],
                'quat_w': unpacked[2],
                'quat_x': unpacked[3],
                'quat_y': unpacked[4],
                'quat_z': unpacked[5],
                'pos_x': unpacked[6],    # In "accel" fields
                'pos_y': unpacked[7],
                'pos_z': unpacked[8],
                'gyro_x': unpacked[9],
                'gyro_y': unpacked[10],
                'gyro_z': unpacked[11],
                'buttons': unpacked[12],
                'trigger': unpacked[13],
                'checksum': unpacked[14]
            }
        except Exception as e:
            print(f"Error parsing packet: {e}")
            return None
    
    def format_controller_data(self, data):
        """Format controller data for display"""
        controller_name = "LEFT " if data['controller_id'] == 0 else "RIGHT"
        
        return (f"{controller_name} Controller (ID={data['controller_id']}) "
                f"Packet #{data['packet_number']}\n"
                f"  Position (m):    X:{data['pos_x']:+.4f}  Y:{data['pos_y']:+.4f}  Z:{data['pos_z']:+.4f}\n"
                f"  Quaternion:      W:{data['quat_w']:+.4f}  X:{data['quat_x']:+.4f}  "
                f"Y:{data['quat_y']:+.4f}  Z:{data['quat_z']:+.4f}\n"
                f"  Gyro (rad/s):    X:{data['gyro_x']:+.4f}  Y:{data['gyro_y']:+.4f}  Z:{data['gyro_z']:+.4f}\n"
                f"  Buttons: 0x{data['buttons']:04X}  Trigger: {data['trigger']}")
    
    def print_status_line(self, data):
        """Print a compact status line"""
        controller_name = "L" if data['controller_id'] == 0 else "R"
        print(f"[{controller_name}] #{data['packet_number']:6d}  "
              f"Pos({data['pos_x']:+.3f}, {data['pos_y']:+.3f}, {data['pos_z']:+.3f})  "
              f"Quat({data['quat_w']:+.3f}, {data['quat_x']:+.3f}, "
              f"{data['quat_y']:+.3f}, {data['quat_z']:+.3f})", end="\r")
    
    def run(self):
        print("=" * 80)
        print("ArUco Controller Debug Receiver")
        print("=" * 80)
        print(f"Listening on {self.host}:{self.port}")
        print("Waiting for controller data...")
        print()
        print("Legend:")
        print("  [L] = Left Controller (ID=0)")
        print("  [R] = Right Controller (ID=1)")
        print("=" * 80)
        print()
        
        try:
            while True:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    
                    # Verify checksum
                    if not self.verify_checksum(data):
                        print(f"\n⚠ Invalid checksum from {addr}")
                        continue
                    
                    # Parse packet
                    parsed = self.parse_packet(data)
                    if not parsed:
                        continue
                    
                    controller_id = parsed['controller_id']
                    self.packet_counts[controller_id] += 1
                    self.last_data[controller_id] = parsed
                    
                    # Print detailed info every 30 packets
                    if self.packet_counts[controller_id] % 30 == 0:
                        print()
                        print("─" * 80)
                        print(self.format_controller_data(parsed))
                        print("─" * 80)
                        print()
                    else:
                        # Print compact status
                        self.print_status_line(parsed)
                
                except socket.timeout:
                    # Check if we have data and print summary
                    if self.last_data:
                        print()
                        print(f"\n⏸ Waiting for data... (Last: ", end="")
                        for cid, data in self.last_data.items():
                            name = "LEFT" if cid == 0 else "RIGHT"
                            print(f"{name}@{data['packet_number']}", end=" ")
                        print(")")
                    continue
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("Shutting down...")
            self.print_summary()
            print("=" * 80)
        finally:
            self.sock.close()
    
    def print_summary(self):
        """Print summary of received data"""
        print("\nReceived Packets Summary:")
        if not self.packet_counts:
            print("  No packets received")
            return
        
        for controller_id, count in sorted(self.packet_counts.items()):
            name = "LEFT " if controller_id == 0 else "RIGHT"
            print(f"  {name} Controller (ID={controller_id}): {count} packets")
            
            if controller_id in self.last_data:
                data = self.last_data[controller_id]
                print(f"    Last position: ({data['pos_x']:.3f}, {data['pos_y']:.3f}, {data['pos_z']:.3f})")
                print(f"    Last quaternion: ({data['quat_w']:.3f}, {data['quat_x']:.3f}, "
                      f"{data['quat_y']:.3f}, {data['quat_z']:.3f})")


def main():
    receiver = ControllerDebugReceiver()
    receiver.run()


if __name__ == "__main__":
    main()