package com.example.aruco_code

import android.util.Log
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * ControllerUDPSender — packs pose data into a fixed-length binary UDP packet
 * and sends it to the VR Tracking Hub (a Python process on the PC).
 *
 * The Hub receives these packets and forwards them to a custom SteamVR driver
 * that exposes virtual controllers / HMD devices.
 *
 * ── Packet layout (49 bytes, little-endian) ──────────────────────────────────
 *
 *   Offset  Size   Type      Field
 *   ──────  ────   ────      ─────
 *     0       1    uint8     controller_id   (0=left, 1=right, 2=HMD)
 *     1       4    uint32    packet_number   (monotonically increasing per device)
 *     5      16    4×float   quaternion      [w, x, y, z]  — orientation
 *    21      12    3×float   position        [x, y, z]     — metres, SteamVR coords
 *    33      12    3×float   gyro            [x, y, z]     — angular velocity (rad/s)
 *                                            (currently always zeros — reserved)
 *    45       2    uint16    buttons         — bitmask of physical buttons
 *                                            (currently always 0 — reserved)
 *    47       1    uint8     trigger         — trigger axis 0-255
 *                                            (currently always 0 — reserved)
 *    48       1    uint8     checksum        — (sum of bytes 0..47) & 0xFF
 *   ────────────────────────────────────────────────────────────────────────────
 *   Total:  49 bytes
 *
 * The Hub uses the checksum to detect corrupted or truncated packets.  If the
 * recomputed checksum does not match, the packet is silently dropped.
 *
 * Little-endian byte order is used because most modern PCs (x86) are
 * little-endian, so the Hub can memcpy floats directly into C structs on the
 * Windows side without byte-swapping.
 */
class ControllerUDPSender(
    private val serverIp: String,
    private val hubPort: Int = 5554   // must match the Hub's listen port
) {
    // UDP is connectionless — DatagramSocket just binds a local ephemeral port.
    // All sends go to the single (serverAddress, hubPort) destination.
    private val socket = DatagramSocket()
    private val serverAddress = InetAddress.getByName(serverIp)

    // Per-device monotonically increasing counter.
    // The Hub uses this to detect dropped or out-of-order packets.
    private val packetNumbers = mutableMapOf(
        0 to 0L,   // Left controller
        1 to 0L,   // Right controller
        2 to 0L    // HMD
    )

    // Human-readable names for logging
    private val deviceNames = mapOf(
        0 to "LEFT",
        1 to "RIGHT",
        2 to "HMD"
    )

    /**
     * Packs one pose update and sends it as a single UDP datagram.
     *
     * @param controllerId  Device id (0, 1, or 2).
     * @param quaternion    Orientation as [w, x, y, z] unit quaternion.
     * @param position      Position as [x, y, z] in metres (SteamVR frame).
     * @param gyro          Angular velocity [x, y, z] in rad/s.  Defaults to zeros.
     * @param buttons       Button bitmask.  Defaults to 0 (no buttons pressed).
     * @param trigger       Trigger axis value 0-255.  Defaults to 0.
     */
    fun sendControllerData(
        controllerId: Int,
        quaternion: FloatArray,   // [w, x, y, z]
        position: FloatArray,     // [x, y, z] metres
        gyro: FloatArray = floatArrayOf(0f, 0f, 0f),
        buttons: Int = 0,
        trigger: Int = 0
    ) {
        try {
            // Allocate exactly 49 bytes in little-endian order
            val buffer = ByteBuffer.allocate(49).order(ByteOrder.LITTLE_ENDIAN)

            // ── Field 1: controller_id (1 byte) ──────────────────────────────
            buffer.put(controllerId.toByte())

            // ── Field 2: packet_number (4 bytes, uint32) ─────────────────────
            // We store as Long to avoid signed-int overflow after ~2 billion packets,
            // but only the lower 32 bits are written into the packet.
            val packetNum = packetNumbers[controllerId] ?: 0L
            buffer.putInt(packetNum.toInt())
            packetNumbers[controllerId] = packetNum + 1

            // ── Field 3: quaternion (16 bytes = 4 × float32) ─────────────────
            buffer.putFloat(quaternion[0])   // w
            buffer.putFloat(quaternion[1])   // x
            buffer.putFloat(quaternion[2])   // y
            buffer.putFloat(quaternion[3])   // z

            // ── Field 4: position (12 bytes = 3 × float32) ───────────────────
            buffer.putFloat(position[0])     // X
            buffer.putFloat(position[1])     // Y
            buffer.putFloat(position[2])     // Z

            // ── Field 5: gyro (12 bytes = 3 × float32) ───────────────────────
            // Reserved for future IMU fusion.  Always zero for now.
            buffer.putFloat(gyro[0])
            buffer.putFloat(gyro[1])
            buffer.putFloat(gyro[2])

            // ── Field 6: buttons (2 bytes, uint16) ───────────────────────────
            buffer.putShort(buttons.toShort())

            // ── Field 7: trigger (1 byte, uint8) ─────────────────────────────
            buffer.put(trigger.toByte())

            // ── Field 8: checksum (1 byte) ───────────────────────────────────
            // Simple sum of all preceding 48 bytes, taken modulo 256.
            // Cheap to compute and cheap for the Hub to verify.
            val dataBytes = buffer.array()
            val checksum = calculateChecksum(dataBytes, 48)
            buffer.put(checksum)

            // ── Transmit ─────────────────────────────────────────────────────
            // DatagramPacket wraps the byte array + destination.  socket.send()
            // does a single syscall; no fragmentation at this size.
            val packet = DatagramPacket(
                dataBytes,
                dataBytes.size,
                serverAddress,
                hubPort
            )
            socket.send(packet)

            // Debug log (only visible with logcat filter "ControllerUDPSender")
            val deviceName = deviceNames[controllerId] ?: "UNKNOWN"
            Log.d("ControllerUDPSender", "$deviceName #${packetNum}: " +
                    "Pos(${position[0]}, ${position[1]}, ${position[2]}) " +
                    "Quat(${quaternion[0]}, ${quaternion[1]}, ${quaternion[2]}, ${quaternion[3]})")

        } catch (e: Exception) {
            Log.e("ControllerUDPSender", "Error sending controller data: ${e.message}")
            e.printStackTrace()
        }
    }

    /**
     * Computes the checksum over [length] bytes of [data].
     * Algorithm: sum every byte (treated as unsigned 0-255), then take & 0xFF.
     * This is intentionally simple — it is not a CRC, just a basic sanity check.
     */
    private fun calculateChecksum(data: ByteArray, length: Int): Byte {
        var sum = 0
        for (i in 0 until length) {
            // Kotlin Bytes are signed (-128..127); mask with 0xFF to get 0..255
            sum += data[i].toInt() and 0xFF
        }
        return (sum and 0xFF).toByte()
    }

    /** Returns how many packets have been sent for the given device so far. */
    fun getPacketCount(controllerId: Int): Long = packetNumbers[controllerId] ?: 0L

    /** Resets the packet counter for one device back to zero. */
    fun resetPacketCounter(controllerId: Int) {
        packetNumbers[controllerId] = 0L
    }

    /**
     * Closes the underlying UDP socket.
     * After this call, sendControllerData() will throw.  This object should not
     * be reused — create a new ControllerUDPSender if you need to send again.
     */
    fun close() {
        try {
            socket.close()
            Log.i("ControllerUDPSender", "Socket closed")
        } catch (e: Exception) {
            Log.e("ControllerUDPSender", "Error closing socket: ${e.message}")
        }
    }
}