#!/usr/bin/env python3
"""
Test Android Connection
Simple script to verify Android app can reach your PC on port 5555.
Run this on your PC before testing with the Android app.
"""

import socket
import struct
import time
import sys

def get_local_ip():
    """Get local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "Unknown"

def test_udp_server():
    """Test UDP server on port 5555"""
    host = '0.0.0.0'
    port = 5555
    
    print("=" * 70)
    print("Android Connection Test - UDP Server")
    print("=" * 70)
    print()
    print(f"Your PC's IP address: {get_local_ip()}")
    print(f"Listening on: {host}:{port}")
    print()
    print("Instructions:")
    print("1. Note your PC's IP address above")
    print("2. Open Android app")
    print("3. Enter IP address in app")
    print("4. Click 'Connect' button")
    print("5. Point camera at ArUco marker (ID 0 or 1)")
    print()
    print("This script will show any packets received...")
    print("Press Ctrl+C to stop")
    print("=" * 70)
    print()
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        sock.settimeout(1.0)
        
        packets_received = 0
        start_time = time.time()
        last_print = start_time
        
        print("Waiting for packets from Android app...")
        
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                packets_received += 1
                
                # Parse basic info
                if len(data) >= 5:
                    controller_id = data[0]
                    packet_num = struct.unpack('<I', data[1:5])[0]
                    
                    current_time = time.time()
                    
                    # Print every packet for the first 10, then every second
                    if packets_received <= 10 or (current_time - last_print) >= 1.0:
                        controller_name = "LEFT" if controller_id == 0 else "RIGHT"
                        print(f"✓ Packet #{packets_received}: {controller_name} controller (ID={controller_id}) "
                              f"from {addr[0]}:{addr[1]} | Size: {len(data)} bytes | "
                              f"Packet number: {packet_num}")
                        last_print = current_time
                        
                        if packets_received == 10:
                            print("\n(Now showing summary every second...)\n")
                    
                    # Summary every 10 seconds
                    if packets_received % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = packets_received / elapsed
                        print(f"\n--- {packets_received} packets received in {elapsed:.1f}s ({rate:.1f} pkt/s) ---\n")
                
            except socket.timeout:
                current_time = time.time()
                if packets_received == 0 and (current_time - start_time) > 10:
                    print("\nNo packets received yet. Check:")
                    print("  1. Android device is on same WiFi network")
                    print("  2. IP address in app is correct")
                    print("  3. Firewall allows UDP port 5555")
                    print("  4. App says 'Connected' in green")
                    print()
                continue
                
    except KeyboardInterrupt:
        print("\n\nStopping...")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        elapsed = time.time() - start_time
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Runtime: {elapsed:.1f} seconds")
        print(f