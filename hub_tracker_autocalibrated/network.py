#!/usr/bin/env python3
"""
Module network.py
UDP packet handling for VR tracking

Packet format (49 bytes) — used for BOTH directions (Android → Hub and Hub → SteamVR):
  [0]     controller_id   (uint8:  0=LEFT, 1=RIGHT, 2=HMD)
  [1:5]   packet_number   (uint32, little-endian)
  [5:21]  quaternion      (4 × float32 LE: W, X, Y, Z)
  [21:33] position        (3 × float32 LE: X, Y, Z)
  [33:45] gyro            (3 × float32 LE: X, Y, Z)
  [45:47] buttons         (uint16, little-endian)
  [47]    trigger         (uint8)
  [48]    checksum        (uint8: sum of bytes [0..47] & 0xFF)
"""
import socket
import struct
from typing import Optional, Callable
from data_structures import ControllerData


class NetworkHandler:
    """
    Handles all UDP network communication:
    - Receiving packets from Android app (port 5554)
    - Sending calibrated packets to SteamVR driver (port 5555)
    """

    def __init__(self, log_callback: Optional[Callable] = None):
        self.socket_android = None
        self.socket_steamvr = None
        # Store target address for sendto (no connect — matches original)
        self._steamvr_addr: Optional[tuple] = None
        self.log_callback = log_callback

    def log(self, message: str, level: str = "INFO"):
        if self.log_callback:
            self.log_callback(message, level)

    # -------------------------------------------------------------------------
    # Android receiver
    # -------------------------------------------------------------------------

    def setup_android_receiver(self, port: int = 5554) -> bool:
        """
        Create UDP socket for receiving data from Android app.
        Timeout set to 0.1s so the receive loop can check self.running frequently.
        """
        try:
            self.socket_android = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket_android.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket_android.bind(("0.0.0.0", port))
            self.socket_android.settimeout(0.1)  # 100 ms — matches original
            self.log(f"Android receiver started on port {port}")
            return True
        except Exception as e:
            self.log(f"Failed to start Android receiver: {e}", "ERROR")
            return False

    def receive_from_android(self) -> Optional[tuple]:
        """
        Receive one UDP packet from Android.
        Returns (data, addr) or None on timeout/error.
        """
        try:
            data, addr = self.socket_android.recvfrom(1024)
            return (data, addr)
        except socket.timeout:
            return None
        except Exception as e:
            self.log(f"Android receiver error: {e}", "ERROR")
            return None

    def parse_aruco_packet(self, data: bytes) -> Optional[dict]:
        """
        Parse 49-byte incoming packet from Android.
        Returns dict with unpacked fields, or None if size or checksum is wrong.
        """
        try:
            if len(data) != 49:
                return None

            # Verify checksum
            calculated_checksum = sum(data[:48]) & 0xFF
            if data[48] != calculated_checksum:
                return None

            # Unpack fields exactly as original does
            controller_id   = data[0]
            packet_number   = struct.unpack('<I', data[1:5])[0]
            quat            = list(struct.unpack('<4f', data[5:21]))   # [W, X, Y, Z]
            pos             = list(struct.unpack('<3f', data[21:33]))  # [X, Y, Z]
            gyro            = list(struct.unpack('<3f', data[33:45]))  # [X, Y, Z]
            buttons         = struct.unpack('<H', data[45:47])[0]
            trigger         = data[47]

            return {
                'controller_id':     controller_id,
                'packet_number':     packet_number,
                'marker_quaternion': quat,
                'marker_position':   pos,
                'gyro':              gyro,
                'buttons':           buttons,
                'trigger':           trigger,
            }

        except Exception as e:
            self.log(f"Error parsing packet: {e}", "ERROR")
            return None

    # -------------------------------------------------------------------------
    # SteamVR sender
    # -------------------------------------------------------------------------

    def setup_steamvr_sender(self, host: str = "127.0.0.1", port: int = 5555) -> bool:
        """
        Create UDP socket for sending data to SteamVR driver.
        Uses sendto() — no connect(), exactly like the original.
        """
        try:
            self.socket_steamvr = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._steamvr_addr = (host, port)
            self.log(f"SteamVR sender started, target {host}:{port}")
            return True
        except Exception as e:
            self.log(f"Failed to start SteamVR sender: {e}", "ERROR")
            return False

    def send_to_steamvr(self, controller: ControllerData) -> bool:
        """
        Build and send a 49-byte packet to the SteamVR driver.

        The packet layout is IDENTICAL to what Android sends — the driver
        expects this exact format. Checksum is computed and appended.

        This is a direct port of the original build_steamvr_packet().
        """
        try:
            packet = bytearray(49)

            # [0] controller_id
            packet[0] = controller.controller_id & 0xFF

            # [1:5] packet_number (uint32 LE)
            struct.pack_into('<I', packet, 1, controller.packet_number & 0xFFFFFFFF)

            # [5:21] quaternion [W, X, Y, Z] (4 × float32 LE)
            struct.pack_into('<4f', packet, 5, *controller.quaternion)

            # [21:33] position [X, Y, Z] (3 × float32 LE)
            struct.pack_into('<3f', packet, 21, *controller.position)

            # [33:45] gyro [X, Y, Z] (3 × float32 LE)
            struct.pack_into('<3f', packet, 33, *controller.gyro)

            # [45:47] buttons (uint16 LE)
            struct.pack_into('<H', packet, 45, controller.buttons & 0xFFFF)

            # [47] trigger (uint8)
            packet[47] = controller.trigger & 0xFF

            # [48] checksum
            packet[48] = sum(packet[:48]) & 0xFF

            # Send via sendto (unconnected UDP)
            self.socket_steamvr.sendto(bytes(packet), self._steamvr_addr)
            return True

        except Exception as e:
            self.log(f"SteamVR sender error: {e}", "ERROR")
            return False

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def close(self):
        """Close all sockets."""
        if self.socket_android:
            self.socket_android.close()
            self.socket_android = None
        if self.socket_steamvr:
            self.socket_steamvr.close()
            self.socket_steamvr = None