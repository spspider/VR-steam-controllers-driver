package com.example.aruco_code

import android.util.Log
import org.opencv.calib3d.Calib3d
import org.opencv.core.*
import kotlin.math.*

/**
 * ArUcoTransform — converts raw ArUco corner detections into 6-DoF poses
 * suitable for sending to a SteamVR driver via UDP.
 *
 * Marker-id mapping (chosen arbitrarily; matches the printed markers):
 *   ID 0 → Left  controller
 *   ID 1 → Right controller
 *   ID 2 → HMD (head-mounted display)
 *
 * High-level pipeline per detected marker:
 *   1. Define the marker's 3-D corner coordinates in its own local frame
 *      (a flat square centred on the origin, lying in the Z=0 plane).
 *   2. Feed the 2-D image corners + 3-D model corners into OpenCV's solvePnP.
 *      solvePnP computes a rotation vector (Rodrigues) and a translation vector
 *      that map the 3-D model into the camera frame.
 *   3. Convert the translation vector to a position in metres.
 *   4. Convert the rotation vector (axis-angle) to a unit quaternion.
 *   5. Flip axes so the position/orientation match SteamVR's coordinate system.
 */
class ArUcoTransform {

    // ─── Camera intrinsics ───────────────────────────────────────────────────
    // These values MUST match your actual camera.  The defaults below assume a
    // 640×480 sensor with a ~60° horizontal FoV.
    //
    // fx, fy  = focal length in pixels.  For a 60° FoV on a 640-wide sensor:
    //             fx = width / (2 * tan(FoV/2)) ≈ 640 / (2 * tan(30°)) ≈ 554
    //           800 is used here as a rough starting point; measure with a
    //           checkerboard calibration for best accuracy.
    // cx, cy  = principal point (optical centre), usually near image centre.
    private val cameraMatrix = MatOfDouble(
        800.0, 0.0, 320.0,
        0.0, 800.0, 240.0,
        0.0, 0.0, 1.0
    )

    // Distortion coefficients [k1, k2, p1, p2].
    // All zeros = assume a perfect pinhole lens.  For a wide-angle lens (e.g. 90°+)
    // you SHOULD run OpenCV's calibrateCamera() with a checkerboard and plug the
    // real values here — barrel distortion will otherwise bias the PnP solution.
    private val distCoeffs = MatOfDouble(0.0, 0.0, 0.0, 0.0)

    // ─── Marker geometry ─────────────────────────────────────────────────────
    // Physical side length of the printed ArUco marker in metres.
    // 5 cm = 0.05 m.  If your printed markers are a different size, change this.
    private val markerSize = 0.05

    // ─── Pose output ─────────────────────────────────────────────────────────
    /**
     * Holds the estimated 6-DoF pose for one marker.
     * @param controllerId  Marker ID (0 = left, 1 = right, 2 = HMD).
     * @param position      [x, y, z] in metres, in SteamVR coordinate space.
     * @param quaternion    [w, x, y, z] unit quaternion, in SteamVR coordinate space.
     */
    data class ControllerPose(
        val controllerId: Int,
        val position: FloatArray,   // [x, y, z] metres
        val quaternion: FloatArray  // [w, x, y, z]
    )

    // ─── Main entry point ────────────────────────────────────────────────────
    /**
     * Estimates the 6-DoF pose of a single ArUco marker.
     *
     * @param corners  A Mat of shape (1, 4, 2) containing the four 2-D image
     *                 coordinates of the marker corners, as returned by the
     *                 OpenCV ArUco detector.
     * @param markerId The marker's numeric ID (must be 0, 1, or 2).
     * @return A ControllerPose, or null if PnP fails or the input is malformed.
     */
    fun estimatePose(corners: Mat, markerId: Int): ControllerPose? {
        try {
            Log.d("ArUcoTransform", "Marker $markerId — Mat size: ${corners.size()}, " +
                    "rows=${corners.rows()}, cols=${corners.cols()}, channels=${corners.channels()}")

            // ── Step 1: 3-D model points ─────────────────────────────────────
            // The marker is a square of side [markerSize] lying flat in the Z=0 plane.
            // Corner order MUST match the order OpenCV's detector returns:
            //   0 = top-left, 1 = top-right, 2 = bottom-right, 3 = bottom-left
            // (when the marker is viewed face-on with its "up" side at the top).
            val objectPoints = MatOfPoint3f(
                Point3(-markerSize / 2,  markerSize / 2, 0.0),   // top-left
                Point3( markerSize / 2,  markerSize / 2, 0.0),   // top-right
                Point3( markerSize / 2, -markerSize / 2, 0.0),   // bottom-right
                Point3(-markerSize / 2, -markerSize / 2, 0.0)    // bottom-left
            )

            // ── Step 2: Extract 2-D image corners from the Mat ──────────────
            // ArUco returns corners as a (1 × 4) Mat with 2 channels → 8 floats total.
            val numCorners = corners.cols()
            if (numCorners != 4) {
                Log.e("ArUcoTransform", "Expected 4 corners, got $numCorners")
                return null
            }

            val points = FloatArray(8)   // 4 corners × 2 (x, y)
            corners.get(0, 0, points)    // bulk read of all 8 floats

            val cornerPoints = arrayOf(
                Point(points[0].toDouble(), points[1].toDouble()),
                Point(points[2].toDouble(), points[3].toDouble()),
                Point(points[4].toDouble(), points[5].toDouble()),
                Point(points[6].toDouble(), points[7].toDouble())
            )

            val imagePoints = MatOfPoint2f()
            imagePoints.fromArray(*cornerPoints)

            Log.d("ArUcoTransform", "Marker $markerId — Corner 0: (${points[0]}, ${points[1]})")

            // ── Step 3: Solve PnP ────────────────────────────────────────────
            // solvePnP finds the rotation (rvec, Rodrigues axis-angle) and
            // translation (tvec) that project the 3-D model points onto the
            // observed 2-D image points, given the camera intrinsics.
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

            // ── Step 4: Extract translation (position) ──────────────────────
            val tvecArray = DoubleArray(3)
            tvec.get(0, 0, tvecArray)
            // tvecArray now holds [x, y, z] in the CAMERA coordinate frame:
            //   Camera X = right
            //   Camera Y = down
            //   Camera Z = forward (into the scene)

            // ── Step 5: Coordinate-system conversion (Camera → SteamVR) ──────
            // SteamVR uses a right-handed system:
            //   X = right   (same as camera)
            //   Y = up      (opposite of camera Y which points down)
            //   Z = backward (opposite of camera Z which points forward)
            // So we negate Y and Z.
            val position = floatArrayOf(
                tvecArray[0].toFloat(),    // X → X  (unchanged)
                -tvecArray[1].toFloat(),   // Y → -Y (down → up)
                -tvecArray[2].toFloat()    // Z → -Z (forward → backward)
            )

            // ── Step 6: Rotation vector → quaternion ─────────────────────────
            val quaternion = rotationVectorToQuaternion(rvec)

            Log.d("ArUcoTransform", "Marker $markerId — Pos: (${position[0]}, ${position[1]}, ${position[2]})")

            return ControllerPose(markerId, position, quaternion)

        } catch (e: Exception) {
            Log.e("ArUcoTransform", "Error estimating pose for marker $markerId: ${e.message}", e)
            return null
        }
    }

    // ─── Rotation vector → quaternion ────────────────────────────────────────
    /**
     * Converts an OpenCV Rodrigues rotation vector to a unit quaternion [w, x, y, z].
     *
     * A Rodrigues vector encodes a rotation as a 3-D vector whose:
     *   - direction = axis of rotation
     *   - magnitude = angle of rotation (in radians)
     *
     * The conversion to quaternion uses the half-angle identity:
     *   q = [cos(θ/2),  sin(θ/2) * axis]
     * where θ is the rotation angle and axis is the unit rotation axis.
     */
    private fun rotationVectorToQuaternion(rvec: Mat): FloatArray {
        val rvecArray = DoubleArray(3)
        rvec.get(0, 0, rvecArray)

        // θ = ||rvec||  (Euclidean norm = rotation angle in radians)
        val angle = sqrt(
            rvecArray[0] * rvecArray[0] +
            rvecArray[1] * rvecArray[1] +
            rvecArray[2] * rvecArray[2]
        )

        // If the angle is essentially zero the marker is not rotated
        if (angle < 1e-4) {
            return floatArrayOf(1f, 0f, 0f, 0f)   // identity quaternion [w=1, x=0, y=0, z=0]
        }

        // Normalise to get the unit rotation axis
        val axis = doubleArrayOf(
            rvecArray[0] / angle,
            rvecArray[1] / angle,
            rvecArray[2] / angle
        )

        // Apply half-angle formula
        val halfAngle = angle / 2.0
        val sinHalf = sin(halfAngle)

        return floatArrayOf(
            cos(halfAngle).toFloat(),            // w
            (axis[0] * sinHalf).toFloat(),       // x
            (axis[1] * sinHalf).toFloat(),       // y
            (axis[2] * sinHalf).toFloat()        // z
        )
    }

    // ─── Camera matrix helper ────────────────────────────────────────────────
    /**
     * Converts the stored MatOfDouble (convenience wrapper) into a plain 3×3
     * CV_64F Mat that solvePnP expects.
     * MatOfDouble's toArray() returns a flat DoubleArray; we fill the Mat row
     * by row.
     */
    private fun reshapeCameraMatrix(): Mat {
        val mat = Mat(3, 3, CvType.CV_64F)
        val data = cameraMatrix.toArray()
        mat.put(0, 0, data[0], data[1], data[2])
        mat.put(1, 0, data[3], data[4], data[5])
        mat.put(2, 0, data[6], data[7], data[8])
        return mat
    }
}