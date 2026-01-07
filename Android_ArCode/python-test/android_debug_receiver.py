#!/usr/bin/env python3
"""
Android ArUco Debug Receiver
Intercepts data sent from Android app to verify correct protocol format.
Listens on port 5555 (same as SteamVR driver).
"""

import socket
import struct
import time
import signal
import sys

class AndroidDebugReceiver:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)
        self.sock.bind((host, port))
        self.running = True
        
        # Statistics
        self.packet_counts = {0: 0, 1: 0}  # Left and Right controllers
        self.total_packets = 0
        self.error_count = 0
        self.start_time = time.time()
        
        print("=" * 70)
        print("Android ArUco Debug Receiver")
        print("=" * 70)
        print(f"Listening on {host}:{port}")
        print("Waiting for data from Android app...")
        print("Press Ctrl+C to stop")
        print("=" * 70)
        print()
        
        # Setup Ctrl+C handler
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        print("\n\nReceived Ctrl+C, shutting down...")
        self.running = False
    
    def verify_checksum(self, data):
        """Verify packet checksum"""
        if len(data) != 49:
            return False
        
        checksum_calculated = sum(data[:-1]) & 0xFF
        checksum_received = data[-1]
        
        return checksum_calculated == checksum_received
    
    def parse_packet(self, data):
        """Parse controller data packet (49 bytes)"""
        try:
            # Unpack according to protocol
            # Format: <BI4f3f3fHBB
            # < = little endian
            # B = uint8 (controller_id)
            # I = uint32 (packet_number)
            # 4f = 4 floats (quaternion w,x,y,z)
            # 3f = 3 floats (position x,y,z)
            # 3f = 3 floats (gyro x,y,z)
            # H = uint16 (buttons)
            # B = uint8 (trigger)
            # B = uint8 (checksum)
            
            unpacked = struct.unpack('<BI4f3f3fHBB', data)
            
            return {
                'controller_id': unpacked[0],
                'packet_number': unpacked[1],
                'quat_w': unpacked[2],
                'quat_x': unpacked[3],
                'quat_y': unpacked[4],
                'quat_z': unpacked[5],
                'pos_x': unpacked[6],
                'pos_y': unpacked[7],
                'pos_z': unpacked[8],
                'gyro_x': unpacked[9],
                'gyro_y': unpacked[10],
                'gyro_z': unpacked[11],
                'buttons': unpacked[12],
                'trigger': unpacked[13],
                'checksum': unpacked[14]
            }
        except struct.error as e:
            return None
    
    def start(self):
        """Start receiving and processing packets"""
        last_detailed_log = {0: 0, 1: 0}  # Track when we last logged details per controller
        
        try:
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    
                    # Check packet size
                    if len(data) != 49:
                        print(f"ERROR: Invalid packet size {len(data)} bytes (expected 49)")
                        self.error_count += 1
                        continue
                    
                    # Verify checksum
                    if not self.verify_checksum(data):
                        print(f"ERROR: Checksum mismatch")
                        self.error_count += 1
                        continue
                    
                    # Parse packet
                    packet = self.parse_packet(data)
                    if packet is None:
                        print(f"ERROR: Failed to parse packet")
                        self.error_count += 1
                        continue
                    
                    controller_id = packet['controller_id']
                    
                    # Update statistics
                    self.total_packets += 1
                    if controller_id in self.packet_counts:
                        self.packet_counts[controller_id] += 1
                    
                    # Log every 30 packets per controller
                    if self.packet_counts[controller_id] % 30 == 0:
                        self.log_detailed(packet, addr)
                        last_detailed_log[controller_id] = self.packet_counts[controller_id]
                    else:
                        # Just print a dot for each packet
                        controller_name = "L" if controller_id == 0 else "R"
                        print(f"{controller_name}", end="", flush=True)
                    
                    # Print summary every 100 total packets
                    if self.total_packets % 100 == 0:
                        self.print_summary()
                        
                except socket.timeout:
                    continue
                    
        except Exception as e:
            print(f"\nReceiver error: {e}")
        finally:
            print("\n")
            self.print_final_summary()
            print("Closing receiver...")
            self.sock.close()
    
    def log_detailed(self, packet, addr):
        """Log detailed packet information"""
        controller_name = "LEFT " if packet['controller_id'] == 0 else "RIGHT"
        
        print(f"\n{'=' * 70}")
        print(f"[{controller_name}] Packet #{packet['packet_number']:6d} from {addr[0]}:{addr[1]}")
        print(f"{'=' * 70}")
        print(f"Position (m):")
        print(f"  X: {packet['pos_x']:+.4f}")
        print(f"  Y: {packet['pos_y']:+.4f}")
        print(f"  Z: {packet['pos_z']:+.4f}")
        print(f"Quaternion (w,x,y,z):")
        print(f"  W: {packet['quat_w']:+.4f}")
        print(f"  X: {packet['quat_x']:+.4f}")
        print(f"  Y: {packet['quat_y']:+.4f}")
        print(f"  Z: {packet['quat_z']:+.4f}")
        print(f"Gyro (rad/s): ({packet['gyro_x']:+.3f}, {packet['gyro_y']:+.3f}, {packet['gyro_z']:+.3f})")
        print(f"Buttons: 0x{packet['buttons']:04X}  Trigger: {packet['trigger']:3d}")
        print(f"Checksum: 0x{packet['checksum']:02X}")
        print()
    
    def print_summary(self):
        """Print packet statistics"""
        elapsed = time.time() - self.start_time
        left_count = self.packet_counts.get(0, 0)
        right_count = self.packet_counts.get(1, 0)
        
        print(f"\n--- Summary @ {elapsed:.1f}s ---")
        print(f"Total: {self.total_packets} packets | "
              f"LEFT: {left_count} | RIGHT: {right_count} | "
              f"Errors: {self.error_count}")
        print()
    
    def print_final_summary(self):
        """Print final statistics"""
        elapsed = time.time() - self.start_time
        left_count = self.packet_counts.get(0, 0)
        right_count = self.packet_counts.get(1, 0)
        
        print("=" * 70)
        print("FINAL STATISTICS")
        print("=" * 70)
        print(f"Runtime: {elapsed:.2f} seconds")
        print(f"Total packets received: {self.total_packets}")
        print(f"  LEFT controller (ID=0): {left_count} packets")
        print(f"  RIGHT controller (ID=1): {right_count} packets")
        print(f"Errors: {self.error_count}")
        if elapsed > 0:
            print(f"Average rate: {self.total_packets / elapsed:.1f} packets/sec")
        print("=" * 70)


def main():
    receiver = AndroidDebugReceiver(host='0.0.0.0', port=5555)
    receiver.start()


if __name__ == "__main__":
    main()