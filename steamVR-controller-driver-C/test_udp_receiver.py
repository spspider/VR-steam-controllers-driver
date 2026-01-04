#!/usr/bin/env python3
import socket
import struct

# Test UDP receiver to verify simulator is working
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('127.0.0.1', 5556))  # Different port to avoid conflict
sock.settimeout(1.0)

print("UDP test receiver listening on port 5556...")
print("Run: python simple_simulator.py and change port to 5556 to test")

try:
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            print(f"Received {len(data)} bytes from {addr}")
            if len(data) == 49:
                # Unpack ControllerData
                unpacked = struct.unpack('<BI4f3f3fHBB', data)
                controller_id = unpacked[0]
                packet_num = unpacked[1]
                print(f"Controller {controller_id}, packet {packet_num}")
            else:
                print(f"Wrong packet size: {len(data)} (expected 49)")
        except socket.timeout:
            print("No data received in 1 second...")
except KeyboardInterrupt:
    print("Stopping...")
finally:
    sock.close()