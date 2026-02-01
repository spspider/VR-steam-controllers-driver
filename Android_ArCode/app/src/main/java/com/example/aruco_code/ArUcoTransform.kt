package com.example.aruco_code

import android.util.Log
import org.opencv.calib3d.Calib3d
import org.opencv.core.*
import kotlin.math.*

/**
 * Transforms ArUco marker detection data into SteamVR controller pose data
 * Поддерживает:
 * - ID 0: Левый контроллер
 * - ID 1: Правый контроллер
 * - ID 2: HMD (шлем)
 */
class ArUcoTransform {

    // Camera calibration parameters (adjust these for your camera!)
    private val cameraMatrix = MatOfDouble(
        800.0, 0.0, 320.0,
        0.0, 800.0, 240.0,
        0.0, 0.0, 1.0
    )

    private val distCoeffs = MatOfDouble(0.0, 0.0, 0.0, 0.0)

    // Marker size in meters (5cm = 0.05m)
    private val markerSize = 0.05

    // Calibration data (отдельная для каждого маркера)
    data class Calibration(
        var positionOffsetX: Double = 0.0,
        var positionOffsetY: Double = 0.0,
        var positionOffsetZ: Double = 0.0,
        var positionScaleX: Double = 5.0,
        var positionScaleY: Double = 5.0,
        var positionScaleZ: Double = 5.0,
        var rotationOffsetX: Double = 0.0,
        var rotationOffsetY: Double = 0.0,
        var rotationOffsetZ: Double = 0.0
    )

    // Отдельная калибровка для каждого маркера
    private val calibrations = mutableMapOf(
        0 to Calibration(),  // LEFT controller
        1 to Calibration(),  // RIGHT controller
        2 to Calibration()   // HMD
    )

    /**
     * Controller pose data
     */
    data class ControllerPose(
        val controllerId: Int,
        val position: FloatArray,  // [x, y, z] in meters
        val quaternion: FloatArray // [w, x, y, z]
    )

    /**
     * Estimate pose from ArUco marker corners
     */
    fun estimatePose(corners: Mat, markerId: Int): ControllerPose? {
        try {
            // Log Mat dimensions for debugging
            Log.d("ArUcoTransform", "Marker $markerId - Mat size: ${corners.size()}, " +
                    "rows=${corners.rows()}, cols=${corners.cols()}, channels=${corners.channels()}")

            // Define 3D coordinates of marker corners (in marker's coordinate system)
            val objectPoints = MatOfPoint3f(
                Point3(-markerSize / 2, markerSize / 2, 0.0),
                Point3(markerSize / 2, markerSize / 2, 0.0),
                Point3(markerSize / 2, -markerSize / 2, 0.0),
                Point3(-markerSize / 2, -markerSize / 2, 0.0)
            )

            // ArUco detector returns corners as Mat with shape (1, 4) and 2 channels (x, y)
            // We need to extract all 4 corners
            val numCorners = corners.cols()  // Should be 4

            if (numCorners != 4) {
                Log.e("ArUcoTransform", "Expected 4 corners, got $numCorners")
                return null
            }

            // Extract corner points - corners is organized as (1, 4, 2)
            val points = FloatArray(8) // 4 corners * 2 coordinates (x, y)
            corners.get(0, 0, points)

            // Create Point array from the extracted data
            val cornerPoints = arrayOf(
                Point(points[0].toDouble(), points[1].toDouble()),
                Point(points[2].toDouble(), points[3].toDouble()),
                Point(points[4].toDouble(), points[5].toDouble()),
                Point(points[6].toDouble(), points[7].toDouble())
            )

            // Create MatOfPoint2f for solvePnP
            val imagePoints = MatOfPoint2f()
            imagePoints.fromArray(*cornerPoints)

            Log.d("ArUcoTransform", "Marker $markerId - Corner 0: (${points[0]}, ${points[1]})")

            // Solve PnP to get rotation and translation vectors
            val rvec = Mat()
            val tvec = Mat()
            val success = Calib3d.solvePnP(
                objectPoints,
                imagePoints,
                reshapeCameraMatrix(),
                distCoeffs,
                rvec,
                tvec
            )

            if (!success) {
                Log.e("ArUcoTransform", "solvePnP failed for marker $markerId")
                return null
            }

            // Convert translation vector to position
            val tvecArray = DoubleArray(3)
            tvec.get(0, 0, tvecArray)

            // Transform to SteamVR coordinate system
            // Camera: X=right, Y=down, Z=forward
            // SteamVR: X=right, Y=up, Z=backward
            var position = floatArrayOf(
                tvecArray[0].toFloat(),   // X stays the same
                -tvecArray[1].toFloat(),  // Y inverted (down -> up)
                -tvecArray[2].toFloat()   // Z inverted (forward -> backward)
            )

            // Convert rotation vector to quaternion
            val quaternion = rotationVectorToQuaternion(rvec)

            // Apply calibration
            position = applyCalibration(position, markerId)

            Log.d("ArUcoTransform", "Marker $markerId - Pos: (${position[0]}, ${position[1]}, ${position[2]})")

            return ControllerPose(markerId, position, quaternion)

        } catch (e: Exception) {
            Log.e("ArUcoTransform", "Error estimating pose for marker $markerId: ${e.message}", e)
            return null
        }
    }

    /**
     * Convert OpenCV rotation vector to quaternion
     */
    private fun rotationVectorToQuaternion(rvec: Mat): FloatArray {
        val rvecArray = DoubleArray(3)
        rvec.get(0, 0, rvecArray)

        // Calculate angle
        val angle = sqrt(
            rvecArray[0] * rvecArray[0] +
                    rvecArray[1] * rvecArray[1] +
                    rvecArray[2] * rvecArray[2]
        )

        if (angle < 0.0001) {
            // No rotation
            return floatArrayOf(1f, 0f, 0f, 0f) // w, x, y, z
        }

        // Normalize axis
        val axis = doubleArrayOf(
            rvecArray[0] / angle,
            rvecArray[1] / angle,
            rvecArray[2] / angle
        )

        // Convert to quaternion
        val halfAngle = angle / 2.0
        val sinHalfAngle = sin(halfAngle)

        return floatArrayOf(
            cos(halfAngle).toFloat(),           // w
            (axis[0] * sinHalfAngle).toFloat(), // x
            (axis[1] * sinHalfAngle).toFloat(), // y
            (axis[2] * sinHalfAngle).toFloat()  // z
        )
    }

    /**
     * Apply calibration to position (per-marker)
     */
    private fun applyCalibration(position: FloatArray, markerId: Int): FloatArray {
        val calib = calibrations[markerId] ?: calibrations[0]!!
        
        return floatArrayOf(
            (position[0] * calib.positionScaleX + calib.positionOffsetX).toFloat(),
            (position[1] * calib.positionScaleY + calib.positionOffsetY).toFloat(),
            (position[2] * calib.positionScaleZ + calib.positionOffsetZ).toFloat()
        )
    }

    /**
     * Reshape camera matrix from MatOfDouble to Mat for solvePnP
     */
    private fun reshapeCameraMatrix(): Mat {
        val mat = Mat(3, 3, CvType.CV_64F)
        val data = cameraMatrix.toArray()
        mat.put(0, 0, data[0], data[1], data[2])
        mat.put(1, 0, data[3], data[4], data[5])
        mat.put(2, 0, data[6], data[7], data[8])
        return mat
    }

    /**
     * Set calibration offset for specific marker (call when pressing calibrate button)
     */
    fun calibratePosition(currentPosition: FloatArray, markerId: Int) {
        val calib = calibrations[markerId] ?: return
        calib.positionOffsetX = -currentPosition[0].toDouble()
        calib.positionOffsetY = -currentPosition[1].toDouble()
        calib.positionOffsetZ = -currentPosition[2].toDouble()
        
        val markerName = when (markerId) {
            0 -> "LEFT"
            1 -> "RIGHT"
            2 -> "HMD"
            else -> "UNKNOWN"
        }
        Log.i("ArUcoTransform", "Calibrated $markerName at (${currentPosition[0]}, ${currentPosition[1]}, ${currentPosition[2]})")
    }

    /**
     * Reset calibration to defaults for all markers
     */
    fun resetCalibration() {
        calibrations.forEach { (_, calib) ->
            calib.positionOffsetX = 0.0
            calib.positionOffsetY = 0.0
            calib.positionOffsetZ = 0.0
            calib.positionScaleX = 5.0
            calib.positionScaleY = 5.0
            calib.positionScaleZ = 5.0
            calib.rotationOffsetX = 0.0
            calib.rotationOffsetY = 0.0
            calib.rotationOffsetZ = 0.0
        }
    }

    /**
     * Reset calibration for specific marker
     */
    fun resetCalibration(markerId: Int) {
        val calib = calibrations[markerId] ?: return
        calib.positionOffsetX = 0.0
        calib.positionOffsetY = 0.0
        calib.positionOffsetZ = 0.0
        calib.positionScaleX = 5.0
        calib.positionScaleY = 5.0
        calib.positionScaleZ = 5.0
        calib.rotationOffsetX = 0.0
        calib.rotationOffsetY = 0.0
        calib.rotationOffsetZ = 0.0
    }

    /**
     * Get current calibration as string for display
     */
    fun getCalibrationInfo(): String {
        return buildString {
            calibrations.forEach { (markerId, calib) ->
                val markerName = when (markerId) {
                    0 -> "LEFT"
                    1 -> "RIGHT"
                    2 -> "HMD"
                    else -> "UNKNOWN"
                }
                append("$markerName: ")
                append("Offset(${calib.positionOffsetX.format(2)}, ")
                append("${calib.positionOffsetY.format(2)}, ")
                append("${calib.positionOffsetZ.format(2)}) ")
                append("Scale(${calib.positionScaleX.format(2)}, ")
                append("${calib.positionScaleY.format(2)}, ")
                append("${calib.positionScaleZ.format(2)})\n")
            }
        }
    }

    /**
     * Get calibration for specific marker
     */
    fun getCalibrationInfo(markerId: Int): String {
        val calib = calibrations[markerId] ?: return "No calibration for marker $markerId"
        val markerName = when (markerId) {
            0 -> "LEFT"
            1 -> "RIGHT"
            2 -> "HMD"
            else -> "UNKNOWN"
        }
        return "$markerName: Offset(${calib.positionOffsetX.format(2)}, " +
                "${calib.positionOffsetY.format(2)}, " +
                "${calib.positionOffsetZ.format(2)}) " +
                "Scale(${calib.positionScaleX.format(2)}, " +
                "${calib.positionScaleY.format(2)}, " +
                "${calib.positionScaleZ.format(2)})"
    }

    private fun Double.format(digits: Int) = "%.${digits}f".format(this)
}