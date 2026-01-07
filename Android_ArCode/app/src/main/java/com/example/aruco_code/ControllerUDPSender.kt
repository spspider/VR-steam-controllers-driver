package com.example.aruco_code

import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Sends controller data to SteamVR driver using the exact same protocol as Python aruco_tracker.py
 *
 * Protocol: 49 bytes total
 * - controller_id: 1 byte (0=left, 1=right)
 * - packet_number: 4 bytes (uint32)
 * - quaternion: 16 bytes (4 floats: w, x, y, z)
 * - position: 12 bytes (3 floats: x, y, z) - sent in "accel" fields
 * - gyro: 12 bytes (3 floats: x, y, z)
 * - buttons: 2 bytes (uint16)
 * - trigger: 1 byte (uint8)
 * - checksum: 1 byte (uint8)
 */
class ControllerUDPSender(
    private val serverIp: String,
    private val serverPort: Int = 5555
) {
    private val socket = DatagramSocket()
    private val serverAddress = InetAddress.getByName(serverIp)

    // Packet counters for each controller
    private val packetNumbers = mutableMapOf(
        0 to 0L,  // Left controller
        1 to 0L   // Right controller
    )

    /**
     * Send controller pose data to SteamVR driver
     */
    fun sendControllerData(
        controllerId: Int,
        quaternion: FloatArray,  // [w, x, y, z]
        position: FloatArray,    // [x, y, z] in meters
        gyro: FloatArray = floatArrayOf(0f, 0f, 0f),
        buttons: Int = 0,
        trigger: Int = 0
    ) {
        try {
            val buffer = ByteBuffer.allocate(49).order(ByteOrder.LITTLE_ENDIAN)

            // 1. Controller ID (1 byte)
            buffer.put(controllerId.toByte())

            // 2. Packet number (4 bytes)
            val packetNum = packetNumbers[controllerId] ?: 0L
            buffer.putInt(packetNum.toInt())
            packetNumbers[controllerId] = packetNum + 1

            // 3. Quaternion (16 bytes) - w, x, y, z
            buffer.putFloat(quaternion[0])  // w
            buffer.putFloat(quaternion[1])  // x
            buffer.putFloat(quaternion[2])  // y
            buffer.putFloat(quaternion[3])  // z

            // 4. Position (12 bytes) - sent as "accel" fields
            // IMPORTANT: This is position data, not acceleration!
            buffer.putFloat(position[0])  // X
            buffer.putFloat(position[1])  // Y
            buffer.putFloat(position[2])  // Z

            // 5. Gyroscope (12 bytes)
            buffer.putFloat(gyro[0])
            buffer.putFloat(gyro[1])
            buffer.putFloat(gyro[2])

            // 6. Buttons (2 bytes)
            buffer.putShort(buttons.toShort())

            // 7. Trigger (1 byte)
            buffer.put(trigger.toByte())

            // 8. Checksum (1 byte) - sum of all previous bytes
            val dataBytes = buffer.array()
            val checksum = calculateChecksum(dataBytes, 48)
            buffer.put(checksum)

            // Send packet
            val packet = DatagramPacket(
                dataBytes,
                dataBytes.size,
                serverAddress,
                serverPort
            )
            socket.send(packet)

        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    /**
     * Calculate checksum (sum of bytes & 0xFF)
     */
    private fun calculateChecksum(data: ByteArray, length: Int): Byte {
        var sum = 0
        for (i in 0 until length) {
            sum += data[i].toInt() and 0xFF
        }
        return (sum and 0xFF).toByte()
    }

    /**
     * Get packet count for a controller
     */
    fun getPacketCount(controllerId: Int): Long {
        return packetNumbers[controllerId] ?: 0L
    }

    /**
     * Close the socket
     */
    fun close() {
        socket.close()
    }
}