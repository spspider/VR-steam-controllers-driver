package com.example.aruco_code

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.*
import android.hardware.camera2.*
import android.media.Image
import android.media.ImageReader
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.util.Size
import android.view.Surface
import android.view.TextureView
import android.view.WindowManager
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import org.opencv.android.OpenCVLoader
import org.opencv.android.Utils
import org.opencv.core.*
import org.opencv.imgproc.Imgproc
import org.opencv.objdetect.ArucoDetector
import org.opencv.objdetect.Dictionary
import org.opencv.objdetect.Objdetect
import java.io.ByteArrayOutputStream

/**
 * MainActivity — entry point of the ArUco-marker tracker.
 *
 * Data flow:
 *   Camera2 YUV_420_888 frame
 *     → yuv420ToBitmap()          (YUV → NV21 → JPEG → Bitmap, kept for simplicity)
 *     → Bitmap → OpenCV gray Mat
 *     → ArucoDetector.detectMarkers()
 *     → ArUcoTransform.estimatePose()   (solvePnP → position + quaternion)
 *     → ControllerUDPSender.sendControllerData()  (49-byte UDP packet to VR Hub)
 *
 * Camera selection:
 *   On startup we enumerate all back-facing cameras via CameraManager.
 *   Each camera is offered in a Spinner.  Switching the spinner closes the
 *   current camera session and re-opens the newly selected camera.
 *
 * Preview aspect-ratio fix:
 *   TextureView does NOT auto-scale to match the camera's aspect ratio.
 *   After the capture session is configured we know the actual image size,
 *   so we apply an android:layoutWidth / layoutHeight via LayoutParams AND a
 *   Matrix transform that preserves the aspect ratio while keeping the view
 *   centred inside its constraint bounds.  This eliminates the "stretched
 *   edges" artefact.
 *
 * Resolution choice (640×480 / 800×600 / 1280×720):
 *   ArUco detection is CPU-bound on Android.  720 p gives a good balance:
 *   markers are still large enough to detect reliably even at a distance,
 *   while the frame rate stays high (typically 25-30 fps on mid-range SoCs).
 *   Going higher (e.g. 1080 p) would roughly double the gray-conversion +
 *   detection workload with little accuracy gain for markers that are
 *   ≥ 5 cm and held within ~1-2 m.
 */
class MainActivity : AppCompatActivity() {

    // ─── UI references ───────────────────────────────────────────────────────
    private lateinit var textureView: TextureView
    private lateinit var logTextView: TextView
    private lateinit var statusTextView: TextView
    private lateinit var ipAddressInput: EditText
    private lateinit var connectButton: Button
    private lateinit var exitButton: Button
    private lateinit var cameraSpinner: Spinner

    // ─── Camera2 state ───────────────────────────────────────────────────────
    private var cameraDevice: CameraDevice? = null
    private var cameraCaptureSession: CameraCaptureSession? = null
    private var imageReader: ImageReader? = null
    private var backgroundHandler: Handler? = null
    private var backgroundThread: HandlerThread? = null

    // Currently selected camera id (index into cameraIdList)
    private var selectedCameraId: String? = null
    // Actual image dimensions chosen for the ImageReader (needed for aspect-ratio fix)
    private var currentImageSize: Size? = null

    // ─── ArUco / UDP ─────────────────────────────────────────────────────────
    private lateinit var detector: ArucoDetector
    private lateinit var dictionary: Dictionary
    private lateinit var arUcoTransform: ArUcoTransform

    private var udpSender: ControllerUDPSender? = null
    private var isConnected = false

    // ─── Logging / stats ─────────────────────────────────────────────────────
    private val logMessages = mutableListOf<String>()
    private var frameCounter = 0
    // Cumulative detection count per marker id (0 = left, 1 = right, 2 = HMD)
    private val markerCounts = mutableMapOf<Int, Int>()

    // Last known pose per marker — could be used for smoothing / hold-last
    private val lastPositions = mutableMapOf<Int, FloatArray>()
    private val lastQuaternions = mutableMapOf<Int, FloatArray>()

    // ─── Permissions ─────────────────────────────────────────────────────────
    private val requiredPermissions = arrayOf(
        Manifest.permission.CAMERA,
        Manifest.permission.INTERNET
    )
    private val REQUEST_CODE_PERMISSIONS = 10

    // ─── Logging helper ──────────────────────────────────────────────────────
    /**
     * Appends a timestamped message to the on-screen log.
     * Only the last 15 lines are kept to avoid memory growth.
     * Also refreshes the status bar with frame / marker counters.
     */
    private fun addLogMessage(message: String) {
        logMessages.add("${System.currentTimeMillis() % 10000}: $message")
        if (logMessages.size > 15) logMessages.removeAt(0)
        runOnUiThread {
            logTextView.text = logMessages.joinToString("\n")

            val totalMarkers = markerCounts.values.sum()
            val leftCount = markerCounts[0] ?: 0
            val rightCount = markerCounts[1] ?: 0
            val hmdCount = markerCounts[2] ?: 0

            statusTextView.text = "Frames: $frameCounter | Markers: $totalMarkers " +
                    "(L:$leftCount R:$rightCount H:$hmdCount)"
        }
    }

    // ─── Permission helpers ──────────────────────────────────────────────────
    private fun checkPermissions(): Boolean =
        requiredPermissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }

    private fun requestPermissions() {
        ActivityCompat.requestPermissions(this, requiredPermissions, REQUEST_CODE_PERMISSIONS)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_CODE_PERMISSIONS) {
            if (grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
                // Permissions granted — populate the camera list and open the first one
                populateCameraSpinner()
            } else {
                Toast.makeText(this, "Permissions not granted", Toast.LENGTH_LONG).show()
                finish()
            }
        }
    }

    // ─── Lifecycle ───────────────────────────────────────────────────────────
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // OpenCV native library must be loaded before any Mat / detector usage
        if (!OpenCVLoader.initLocal()) {
            Log.e("MainActivity", "OpenCV initialization failed!")
            Toast.makeText(this, "OpenCV initialization failed!", Toast.LENGTH_LONG).show()
            return
        }

        setContentView(R.layout.activity_main)

        // Bind UI widgets by id
        textureView = findViewById(R.id.texture_view)
        logTextView = findViewById(R.id.logTextView)
        statusTextView = findViewById(R.id.statusTextView)
        ipAddressInput = findViewById(R.id.ipAddress)
        connectButton = findViewById(R.id.connectButton)
        exitButton = findViewById(R.id.exitButton)
        cameraSpinner = findViewById(R.id.cameraSpinner)

        ipAddressInput.setText("192.168.1.199")
        addLogMessage("App started — OpenCV loaded")

        // ── ArUco detector init ──────────────────────────────────────────────
        // DICT_4X4_50 supports marker ids 0-49.  We only use 0, 1, 2.
        // The "4x4" means each marker has a 4×4 bit payload — small and fast to decode.
        try {
            dictionary = Objdetect.getPredefinedDictionary(Objdetect.DICT_4X4_50)
            detector = ArucoDetector(dictionary)
            arUcoTransform = ArUcoTransform()
            addLogMessage("ArUco detector ready (DICT_4X4_50)")
        } catch (e: Exception) {
            Log.e("MainActivity", "ArUco init error: ${e.message}")
            addLogMessage("ArUco init failed: ${e.message}")
        }

        // ── Connect button ───────────────────────────────────────────────────
        // Creates the UDP sender on a background thread (DNS resolution may block).
        // UDP is connectionless so "connect" here just stores the target address.
        connectButton.setOnClickListener {
            val ip = ipAddressInput.text.toString()
            if (ip.isNotEmpty()) {
                CoroutineScope(Dispatchers.IO).launch {
                    try {
                        udpSender?.close()
                        udpSender = ControllerUDPSender(ip, 5554)
                        isConnected = true

                        runOnUiThread {
                            Toast.makeText(this@MainActivity, "Connected to VR Hub at $ip:5554", Toast.LENGTH_SHORT).show()
                            addLogMessage("Connected to VR Tracking Hub at $ip:5554")
                            connectButton.text = "Connected to Hub"
                            connectButton.isEnabled = false
                        }
                    } catch (e: Exception) {
                        runOnUiThread {
                            Toast.makeText(this@MainActivity, "Connection failed: ${e.message}", Toast.LENGTH_SHORT).show()
                            addLogMessage("Hub connection failed")
                        }
                    }
                }
            }
        }

        // ── Exit button ──────────────────────────────────────────────────────
        // Graceful shutdown: close camera, stop threads, close UDP socket, then finish().
        exitButton.setOnClickListener {
            addLogMessage("Exiting...")
            shutdownAndExit()
        }

        // ── Camera spinner ───────────────────────────────────────────────────
        // Selection change → close current camera → open newly selected one.
        cameraSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: android.view.View?, position: Int, id: Long) {
                val newCameraId = cameraIdList[position]
                // Skip re-open if the user re-selected the same camera
                if (newCameraId == selectedCameraId) return
                selectedCameraId = newCameraId
                addLogMessage("Switched to camera: $newCameraId")
                // Close current session/device before opening a new one
                closeCamera()
                openCamera(textureView.width, textureView.height)
            }

            override fun onNothingSelected(parent: AdapterView<*>) {}
        }

        // Keep screen on while app is running (important for continuous tracking)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // ── Permissions check ────────────────────────────────────────────────
        if (checkPermissions()) {
            populateCameraSpinner()
        } else {
            requestPermissions()
        }
    }

    // ─── Camera enumeration ──────────────────────────────────────────────────
    /**
     * Holds the raw camera-id strings returned by CameraManager in the same
     * order as the Spinner items.  Index in this list == Spinner position.
     */
    private var cameraIdList: List<String> = emptyList()

    /**
     * Enumerates all back-facing cameras, builds human-readable labels
     * (e.g. "Camera 0 — back (wide)"), and populates the Spinner.
     * After populating, opens the first camera automatically.
     */
    private fun populateCameraSpinner() {
        val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val ids = cameraManager.cameraIdList.toList()
        cameraIdList = ids

        // Build label list with FOV info where available
        val labels = ids.mapIndexed { index, id ->
            try {
                val characteristics = cameraManager.getCameraCharacteristics(id)
                val facing = characteristics.get(CameraCharacteristics.LENS_FACING)
                val facingStr = when (facing) {
                    CameraCharacteristics.LENS_FACING_BACK -> "back"
                    CameraCharacteristics.LENS_FACING_FRONT -> "front"
                    CameraCharacteristics.LENS_FACING_EXTERNAL -> "external"
                    else -> "unknown"
                }

                // Calculate approximate FoV from focal length if available
                val focalLengths = characteristics.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)
                val sensorSize = characteristics.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)
                val fovStr = if (focalLengths != null && focalLengths.isNotEmpty() && sensorSize != null) {
                    val focalLength = focalLengths[0]
                    val diagonalMm = Math.sqrt((sensorSize.width * sensorSize.width + sensorSize.height * sensorSize.height).toDouble())
                    val fovDegrees = 2 * Math.toDegrees(Math.atan(diagonalMm / (2 * focalLength)))
                    "FoV ${"%.1f".format(fovDegrees)}°"
                } else "FoV ?"

                "Camera $index — $facingStr ($fovStr)"
            } catch (e: Exception) {
                "Camera $index (id=$id)"
            }
        }

        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, labels)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        cameraSpinner.adapter = adapter

        // Pick the first camera as default and open it
        if (ids.isNotEmpty()) {
            selectedCameraId = ids[0]
            // Trigger open — spinner position is already 0
            startBackgroundThread()
            if (textureView.isAvailable) {
                openCamera(textureView.width, textureView.height)
            } else {
                // TextureView not ready yet — wait for its surface
                textureView.surfaceTextureListener = object : TextureView.SurfaceTextureListener {
                    override fun onSurfaceTextureAvailable(
                        surface: android.graphics.SurfaceTexture,
                        width: Int,
                        height: Int
                    ) {
                        openCamera(width, height)
                    }
                    override fun onSurfaceTextureSizeChanged(
                        surface: android.graphics.SurfaceTexture, width: Int, height: Int
                    ) {}
                    override fun onSurfaceTextureDestroyed(
                        surface: android.graphics.SurfaceTexture
                    ): Boolean = true
                    override fun onSurfaceTextureUpdated(
                        surface: android.graphics.SurfaceTexture
                    ) {}
                }
            }
        }
    }

    // ─── Background thread for Camera2 callbacks ────────────────────────────
    private fun startBackgroundThread() {
        // Camera2 requires a looper for its asynchronous callbacks.
        // We create a dedicated HandlerThread so we never block the main thread.
        if (backgroundThread != null) return  // already running
        backgroundThread = HandlerThread("CameraBackground")
        backgroundThread?.start()
        backgroundHandler = Handler(backgroundThread!!.looper)
    }

    private fun stopBackgroundThread() {
        backgroundThread?.quitSafely()
        try {
            backgroundThread?.join()
            backgroundThread = null
            backgroundHandler = null
        } catch (e: InterruptedException) {
            Log.e("MainActivity", "Error stopping background thread", e)
        }
    }

    // ─── Camera open / session ───────────────────────────────────────────────
    /**
     * Opens the camera identified by [selectedCameraId].
     * Steps:
     *   1. Query supported YUV_420_888 output sizes.
     *   2. Pick the best size via chooseOptimalSize().
     *   3. Create an ImageReader at that size (this is what feeds processImage()).
     *   4. Open the CameraDevice — on success, create the capture session.
     */
    private fun openCamera(width: Int, height: Int) {
        val cameraId = selectedCameraId ?: return
        try {
            val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            val characteristics = cameraManager.getCameraCharacteristics(cameraId)
            val streamConfigMap = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)

            val imageDimension: Size = if (streamConfigMap != null) {
                chooseOptimalSize(
                    streamConfigMap.getOutputSizes(ImageFormat.YUV_420_888),
                    width, height
                )
            } else {
                Size(640, 480)
            }
            // Remember for aspect-ratio correction after session is configured
            currentImageSize = imageDimension

            // ImageReader queue size = 2: one frame can be processed while the next
            // is being captured.  Larger queues would increase latency.
            imageReader = ImageReader.newInstance(
                imageDimension.width,
                imageDimension.height,
                ImageFormat.YUV_420_888,
                2
            )
            // Each new image is handed to processImage() on the background thread
            imageReader!!.setOnImageAvailableListener({ reader ->
                val image = reader.acquireLatestImage()
                if (image != null) {
                    processImage(image)
                }
            }, backgroundHandler)

            if (ActivityCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                != PackageManager.PERMISSION_GRANTED
            ) return

            cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                override fun onOpened(camera: CameraDevice) {
                    cameraDevice = camera
                    addLogMessage("Camera opened: $cameraId (${imageDimension.width}×${imageDimension.height})")
                    createCameraPreviewSession()
                }
                override fun onDisconnected(camera: CameraDevice) {
                    camera.close()
                    cameraDevice = null
                }
                override fun onError(camera: CameraDevice, error: Int) {
                    camera.close()
                    cameraDevice = null
                    addLogMessage("Camera error: $error")
                }
            }, backgroundHandler)

        } catch (e: Exception) {
            Log.e("MainActivity", "Error opening camera", e)
            addLogMessage("Camera error: ${e.message}")
        }
    }

    /**
     * Picks the best output resolution for ArUco detection.
     *
     * Priority list (descending quality / ascending cost):
     *   1280×720 – best for detection accuracy; still fast enough on most devices.
     *   800×600  – good fallback for older / weaker SoCs.
     *   640×480  – minimum acceptable; markers must be large in the frame.
     *
     * If none of the preferred sizes are available, we take the largest size
     * that fits within 1280×720; if even that fails, we use whatever the camera
     * reports first.
     */
    private fun chooseOptimalSize(choices: Array<Size>, width: Int, height: Int): Size {
        val preferredSizes = listOf(
            Size(1280, 720),   // best accuracy for ArUco
            Size(800, 600),
            Size(640, 480)
        )

        for (preferredSize in preferredSizes) {
            for (size in choices) {
                if (size.width == preferredSize.width && size.height == preferredSize.height) {
                    return size
                }
            }
        }

        return choices.firstOrNull { it.width <= 1280 && it.height <= 720 } ?: choices[0]
    }

    /**
     * Creates the CameraCaptureSession with two surfaces:
     *   - The TextureView surface (for on-screen preview).
     *   - The ImageReader surface (for per-frame ArUco processing).
     *
     * Once configured, we apply the aspect-ratio matrix to the TextureView
     * so the preview fills its view without stretching.
     */
    private fun createCameraPreviewSession() {
        try {
            val texture = textureView.surfaceTexture ?: return
            val surface = Surface(texture)
            val targets = listOfNotNull(surface, imageReader?.surface)

            cameraDevice?.createCaptureSession(
                targets,
                object : CameraCaptureSession.StateCallback() {
                    override fun onConfigured(session: CameraCaptureSession) {
                        cameraCaptureSession = session
                        addLogMessage("Camera session configured")
                        // Fix aspect-ratio BEFORE starting the repeating request
                        fixPreviewAspectRatio()
                        startPreview()
                    }
                    override fun onConfigureFailed(session: CameraCaptureSession) {
                        addLogMessage("Camera session failed")
                    }
                },
                null
            )

        } catch (e: Exception) {
            Log.e("MainActivity", "Error creating preview session", e)
            addLogMessage("Session error: ${e.message}")
        }
    }

    /**
     * Applies a transformation matrix to the TextureView so that the camera
     * image is displayed with its correct aspect ratio, centred in the view,
     * without any stretching.
     *
     * How it works:
     *   TextureView always renders its content stretched to fill its layout
     *   bounds.  We counter that by scaling one axis down by the ratio of the
     *   camera's aspect to the view's aspect.  The resulting image is letterboxed
     *   (or pillarboxed) inside the view.
     *
     * Called once after the capture session is configured, and again whenever
     * the view size changes (e.g. rotation).
     */
    private fun fixPreviewAspectRatio() {
        val imageSize = currentImageSize ?: return
        runOnUiThread {
            val viewWidth = textureView.width.toFloat()
            val viewHeight = textureView.height.toFloat()
            if (viewWidth == 0f || viewHeight == 0f) return@runOnUiThread

            // Swap dimensions for 90° rotated camera
            val imageAspect = imageSize.height.toFloat() / imageSize.width.toFloat()
            val viewAspect = viewWidth / viewHeight

            val matrix = Matrix()
            // matrix.postRotate(90f, viewWidth / 2f, viewHeight / 2f)

            if (imageAspect > viewAspect) {
                val scaleX = viewAspect / imageAspect
                matrix.postScale(scaleX, 1.0f, viewWidth / 2f, viewHeight / 2f)
            } else {
                val scaleY = imageAspect / viewAspect
                matrix.postScale(1.0f, scaleY, viewWidth / 2f, viewHeight / 2f)
            }

            textureView.setTransform(matrix)
        }
    }

    /**
     * Starts the repeating capture request.
     * CONTROL_AF_MODE_CONTINUOUS_PICTURE keeps the lens focused continuously,
     * which is important for ArUco markers at varying distances.
     */
    private fun startPreview() {
        try {
            val captureRequestBuilder = cameraDevice?.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW) ?: return
            captureRequestBuilder.addTarget(Surface(textureView.surfaceTexture))
            imageReader?.surface?.let { captureRequestBuilder.addTarget(it) }

            captureRequestBuilder.set(
                CaptureRequest.CONTROL_AF_MODE,
                CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE
            )

            cameraCaptureSession?.setRepeatingRequest(
                captureRequestBuilder.build(),
                null,
                backgroundHandler
            )

        } catch (e: Exception) {
            Log.e("MainActivity", "Error starting preview", e)
            addLogMessage("Preview error: ${e.message}")
        }
    }

    // ─── Image processing pipeline ───────────────────────────────────────────
    /**
     * Entry point for every captured frame.
     * Converts the Camera2 YUV Image to a grayscale OpenCV Mat, then hands it
     * to the ArUco detector.
     *
     * The YUV→Bitmap path uses the standard NV21 trick:
     *   YUV_420_888 planes (Y, U, V) are rearranged into NV21 byte order
     *   (Y plane, then interleaved V-U), wrapped in a YuvImage, and compressed
     *   to JPEG so that BitmapFactory can decode it.  This avoids needing a
     *   custom pixel converter while staying reasonably fast.
     */
    private fun processImage(image: Image?) {
        if (image == null) return
        frameCounter++

        try {
            val bitmap = yuv420ToBitmap(image)
            if (bitmap != null) {
                // Convert Bitmap → RGBA Mat → Gray Mat
                val rgbaMat = Mat(bitmap.height, bitmap.width, CvType.CV_8UC4)
                Utils.bitmapToMat(bitmap, rgbaMat)

                val grayMat = Mat()
                Imgproc.cvtColor(rgbaMat, grayMat, Imgproc.COLOR_RGBA2GRAY)

                detectArUcoMarkers(grayMat)

                // Release native memory explicitly — the GC cannot track OpenCV Mats
                bitmap.recycle()
                rgbaMat.release()
                grayMat.release()
            }
        } catch (e: Exception) {
            Log.e("MainActivity", "Error processing image", e)
        } finally {
            // MUST close the Image or the ImageReader will run out of buffers
            image.close()
        }
    }

    /**
     * Converts a Camera2 YUV_420_888 Image to an Android Bitmap.
     *
     * YUV_420_888 has three planes:
     *   plane[0] = Y  (luminance, one byte per pixel)
     *   plane[1] = U  (chrominance)
     *   plane[2] = V  (chrominance)
     *
     * NV21 layout expected by YuvImage:
     *   [Y bytes][V bytes interleaved with U bytes]
     * So we copy: Y → V → U into the output array.
     */
    private fun yuv420ToBitmap(image: Image): Bitmap? {
        try {
            val planes = image.planes
            val yBuffer = planes[0].buffer
            val uBuffer = planes[1].buffer
            val vBuffer = planes[2].buffer

            val ySize = yBuffer.remaining()
            val uSize = uBuffer.remaining()
            val vSize = vBuffer.remaining()

            val nv21 = ByteArray(ySize + uSize + vSize)

            yBuffer.get(nv21, 0, ySize)
            // NV21 interleaves V then U after the Y plane
            vBuffer.get(nv21, ySize, vSize)
            uBuffer.get(nv21, ySize + vSize, uSize)

            val yuvImage = android.graphics.YuvImage(
                nv21,
                ImageFormat.NV21,
                image.width,
                image.height,
                null
            )

            val outputStream = ByteArrayOutputStream()
            // Quality 100 to avoid JPEG artifacts affecting marker edges
            yuvImage.compressToJpeg(
                android.graphics.Rect(0, 0, image.width, image.height),
                100,
                outputStream
            )

            return BitmapFactory.decodeByteArray(outputStream.toByteArray(), 0, outputStream.size())

        } catch (e: Exception) {
            Log.e("MainActivity", "Error converting YUV", e)
            return null
        }
    }

    // ─── ArUco marker detection ──────────────────────────────────────────────
    /**
     * Runs the ArUco detector on a single grayscale frame.
     *
     * For every detected marker whose id is 0, 1, or 2:
     *   1. estimatePose() solves PnP to get the 3-D pose.
     *   2. If connected, the pose is sent via UDP to the VR Tracking Hub.
     *   3. Every 30 detections we log the pose to keep the log readable.
     */
    private fun detectArUcoMarkers(grayMat: Mat) {
        if (!::detector.isInitialized) return

        try {
            val corners = ArrayList<Mat>()
            val ids = Mat()

            detector.detectMarkers(grayMat, corners, ids)

            val markerCount = corners.size

            if (markerCount > 0 && !ids.empty()) {
                for (i in 0 until markerCount) {
                    val idArray = IntArray(1)
                    ids.get(i, 0, idArray)
                    val markerId = idArray[0]

                    // We only care about IDs 0 (left controller), 1 (right), 2 (HMD)
                    if (markerId < 0 || markerId > 2) continue

                    markerCounts[markerId] = (markerCounts[markerId] ?: 0) + 1

                    // Estimate 6-DoF pose from the four corner points
                    val pose = arUcoTransform.estimatePose(corners[i], markerId)

                    if (pose != null && isConnected && udpSender != null) {
                        lastPositions[markerId] = pose.position
                        lastQuaternions[markerId] = pose.quaternion

                        // Send the 49-byte UDP packet to the VR Tracking Hub
                        udpSender?.sendControllerData(
                            controllerId = pose.controllerId,
                            quaternion = pose.quaternion,
                            position = pose.position
                        )

                        // Log every 30th detection to avoid flooding the UI
                        if (markerCounts[markerId]!! % 30 == 0) {
                            val markerName = when (markerId) {
                                0 -> "LEFT"
                                1 -> "RIGHT"
                                2 -> "HMD"
                                else -> "UNKNOWN"
                            }
                            addLogMessage(
                                "$markerName #${markerCounts[markerId]}: " +
                                        "Pos(${pose.position[0].format(2)}, " +
                                        "${pose.position[1].format(2)}, " +
                                        "${pose.position[2].format(2)}) " +
                                        "Quat(${pose.quaternion[0].format(2)})"
                            )
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("MainActivity", "ArUco detection error", e)
        }
    }

    private fun Float.format(digits: Int) = "%.${digits}f".format(this)

    // ─── Camera teardown ─────────────────────────────────────────────────────
    /**
     * Closes the capture session and the camera device.
     * Safe to call multiple times (guards against null).
     */
    private fun closeCamera() {
        cameraCaptureSession?.close()
        cameraCaptureSession = null
        cameraDevice?.close()
        cameraDevice = null
        imageReader?.close()
        imageReader = null
    }

    // ─── Graceful shutdown ───────────────────────────────────────────────────
    /**
     * Stops everything in the correct order and exits the activity.
     * Order matters:
     *   1. Close camera (stops producing frames).
     *   2. Stop background thread (no more callbacks).
     *   3. Close UDP socket (flushes any pending send).
     *   4. Clear keep-screen-on flag.
     *   5. finish() — Android lifecycle teardown.
     */
    private fun shutdownAndExit() {
        closeCamera()
        stopBackgroundThread()
        udpSender?.close()
        udpSender = null
        isConnected = false
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        finish()
    }

    // ─── Lifecycle hooks ─────────────────────────────────────────────────────
    override fun onPause() {
        super.onPause()
        // Could pause camera here if desired; currently we keep running
    }

    override fun onResume() {
        super.onResume()
    }

    override fun onDestroy() {
        super.onDestroy()
        // Safety net: clean up even if shutdownAndExit() was not called
        closeCamera()
        stopBackgroundThread()
        udpSender?.close()
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
}