package com.example.aruco_code

import android.util.Log
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Sends controller and HMD data to VR Tracking Hub (Python)
 * Hub will then forward data to SteamVR driver
 *
 * Protocol: 49 bytes total
 * - controller_id: 1 byte (0=left, 1=right, 2=HMD)
 * - packet_number: 4 bytes (uint32)
 * - quaternion: 16 bytes (4 floats: w, x, y, z)
 * - position: 12 bytes (3 floats: x, y, z)
 * - gyro: 12 bytes (3 floats: x, y, z)
 * - buttons: 2 bytes (uint16)
 * - trigger: 1 byte (uint8)
 * - checksum: 1 byte (uint8)
 */
class ControllerUDPSender(
    private val serverIp: String,
    private val hubPort: Int = 5554  // VR Tracking Hub port
) {
    private val socket = DatagramSocket()
    private val serverAddress = InetAddress.getByName(serverIp)

    // Packet counters for each device
    private val packetNumbers = mutableMapOf(
        0 to 0L,  // Left controller
        1 to 0L,  // Right controller
        2 to 0L   // HMD
    )

    private val deviceNames = mapOf(
        0 to "LEFT",
        1 to "RIGHT",
        2 to "HMD"
    )

    /**
     * Send controller/HMD pose data to VR Tracking Hub
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

            // 1. Controller/HMD ID (1 byte)
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

            // 4. Position (12 bytes) - x, y, z in meters
            buffer.putFloat(position[0])  // X
            buffer.putFloat(position[1])  // Y
            buffer.putFloat(position[2])  // Z

            // 5. Gyroscope/Angular velocity (12 bytes)
            buffer.putFloat(gyro[0])
            buffer.putFloat(gyro[1])
            buffer.putFloat(gyro[2])

            // 6. Buttons (2 bytes)
            buffer.putShort(buttons.toShort())

            // 7. Trigger (1 byte)
            buffer.put(trigger.toByte())

            // 8. Checksum (1 byte) - sum of all previous bytes modulo 256
            val dataBytes = buffer.array()
            val checksum = calculateChecksum(dataBytes, 48)
            buffer.put(checksum)

            // Send packet to hub
            val packet = DatagramPacket(
                dataBytes,
                dataBytes.size,
                serverAddress,
                hubPort
            )
            socket.send(packet)

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
     * Get packet count for a device
     */
    fun getPacketCount(controllerId: Int): Long {
        return packetNumbers[controllerId] ?: 0L
    }

    /**
     * Reset packet counter for a device
     */
    fun resetPacketCounter(controllerId: Int) {
        packetNumbers[controllerId] = 0L
    }

    /**
     * Close the socket
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