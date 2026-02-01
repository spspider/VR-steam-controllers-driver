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
import java.util.*

class MainActivity : AppCompatActivity() {

    private lateinit var textureView: TextureView
    private lateinit var logTextView: TextView
    private lateinit var statusTextView: TextView
    private lateinit var ipAddressInput: EditText
    private lateinit var connectButton: Button
    private lateinit var calibrateButton: Button
    private lateinit var resetCalibButton: Button

    private var cameraDevice: CameraDevice? = null
    private var cameraCaptureSession: CameraCaptureSession? = null
    private var imageReader: ImageReader? = null
    private var backgroundHandler: Handler? = null
    private var backgroundThread: HandlerThread? = null
    private var cameraInitialized = false

    private lateinit var detector: ArucoDetector
    private lateinit var dictionary: Dictionary
    private lateinit var arUcoTransform: ArUcoTransform

    private var udpSender: ControllerUDPSender? = null
    private var isConnected = false

    private val logMessages = mutableListOf<String>()
    private var frameCounter = 0
    private val markerCounts = mutableMapOf<Int, Int>()  // Track detection count per marker

    // Отслеживание последних позиций для каждого маркера
    private val lastPositions = mutableMapOf<Int, FloatArray>()
    private val lastQuaternions = mutableMapOf<Int, FloatArray>()

    private val requiredPermissions = arrayOf(
        Manifest.permission.CAMERA,
        Manifest.permission.INTERNET
    )

    private val REQUEST_CODE_PERMISSIONS = 10

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

    private fun checkPermissions(): Boolean {
        return requiredPermissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
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
                initializeCamera()
            } else {
                Toast.makeText(this, "Permissions not granted", Toast.LENGTH_LONG).show()
                finish()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Check OpenCV
        if (!OpenCVLoader.initLocal()) {
            Log.e("MainActivity", "OpenCV initialization failed!")
            Toast.makeText(this, "OpenCV initialization failed!", Toast.LENGTH_LONG).show()
            return
        }

        setContentView(R.layout.activity_main)

        // Initialize UI elements
        textureView = findViewById(R.id.texture_view)
        logTextView = findViewById(R.id.logTextView)
        statusTextView = findViewById(R.id.statusTextView)
        ipAddressInput = findViewById(R.id.ipAddress)
        connectButton = findViewById(R.id.connectButton)
        calibrateButton = findViewById(R.id.calibrateButton)
        resetCalibButton = findViewById(R.id.resetCalibButton)

        // Set default IP (your PC's IP on local network)
        ipAddressInput.setText("192.168.1.199")
        addLogMessage("App started - OpenCV loaded")

        // Initialize ArUco detector
        try {
            dictionary = Objdetect.getPredefinedDictionary(Objdetect.DICT_4X4_50)
            detector = ArucoDetector(dictionary)
            arUcoTransform = ArUcoTransform()
            addLogMessage("ArUco detector ready (DICT_4X4_50)")
        } catch (e: Exception) {
            Log.e("MainActivity", "ArUco init error: ${e.message}")
            addLogMessage("ArUco init failed: ${e.message}")
        }

        // Connect button
        connectButton.setOnClickListener {
            val ip = ipAddressInput.text.toString()
            if (ip.isNotEmpty()) {
                CoroutineScope(Dispatchers.IO).launch {
                    try {
                        udpSender?.close()
                        udpSender = ControllerUDPSender(ip, 5554)  // Hub port
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

        // Calibrate button
        calibrateButton.setOnClickListener {
            // Calibration is done per-marker when detected
            addLogMessage("Calibration: Move marker to center, will auto-calibrate")
            Toast.makeText(this, "Move marker to center position", Toast.LENGTH_SHORT).show()
        }

        // Reset calibration button
        resetCalibButton.setOnClickListener {
            arUcoTransform.resetCalibration()
            addLogMessage("Calibration reset")
            Toast.makeText(this, "Calibration reset", Toast.LENGTH_SHORT).show()
        }

        // Keep screen on
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // Check and request permissions
        if (checkPermissions()) {
            initializeCamera()
        } else {
            requestPermissions()
        }
    }

    private fun initializeCamera() {
        if (cameraInitialized) return
        cameraInitialized = true

        startBackgroundThread()

        if (textureView.isAvailable) {
            openCamera(textureView.width, textureView.height)
        } else {
            textureView.surfaceTextureListener = object : TextureView.SurfaceTextureListener {
                override fun onSurfaceTextureAvailable(
                    surface: android.graphics.SurfaceTexture,
                    width: Int,
                    height: Int
                ) {
                    openCamera(width, height)
                }

                override fun onSurfaceTextureSizeChanged(
                    surface: android.graphics.SurfaceTexture,
                    width: Int,
                    height: Int
                ) {}

                override fun onSurfaceTextureDestroyed(surface: android.graphics.SurfaceTexture): Boolean {
                    return true
                }

                override fun onSurfaceTextureUpdated(surface: android.graphics.SurfaceTexture) {}
            }
        }
    }

    private fun startBackgroundThread() {
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

    private fun openCamera(width: Int, height: Int) {
        try {
            val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            val cameraId = cameraManager.cameraIdList[0]

            val characteristics = cameraManager.getCameraCharacteristics(cameraId)
            val streamConfigMap = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)

            val imageDimension: Size = if (streamConfigMap != null) {
                chooseOptimalSize(
                    streamConfigMap.getOutputSizes(ImageFormat.YUV_420_888),
                    width,
                    height
                )
            } else {
                Size(640, 480)
            }

            imageReader = ImageReader.newInstance(
                imageDimension.width,
                imageDimension.height,
                ImageFormat.YUV_420_888,
                2
            )
            imageReader!!.setOnImageAvailableListener({ reader ->
                val image = reader.acquireLatestImage()
                if (image != null) {
                    processImage(image)
                }
            }, backgroundHandler)

            if (ActivityCompat.checkSelfPermission(
                    this,
                    Manifest.permission.CAMERA
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                return
            }

            cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                override fun onOpened(camera: CameraDevice) {
                    cameraDevice = camera
                    addLogMessage("Camera opened")
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
            }, null)

        } catch (e: Exception) {
            Log.e("MainActivity", "Error opening camera", e)
            addLogMessage("Camera error: ${e.message}")
        }
    }

    private fun chooseOptimalSize(choices: Array<Size>, width: Int, height: Int): Size {
        val preferredSizes = listOf(
            Size(640, 480),
            Size(800, 600),
            Size(1280, 720)
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

    private fun createCameraPreviewSession() {
        try {
            val texture = textureView.surfaceTexture
            val surface = Surface(texture)
            val targets = listOf(surface, imageReader?.surface)

            cameraDevice?.createCaptureSession(
                targets,
                object : CameraCaptureSession.StateCallback() {
                    override fun onConfigured(session: CameraCaptureSession) {
                        cameraCaptureSession = session
                        addLogMessage("Camera session configured")
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

    private fun startPreview() {
        try {
            val captureRequestBuilder = cameraDevice?.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
            captureRequestBuilder?.addTarget(Surface(textureView.surfaceTexture))
            imageReader?.surface?.let { captureRequestBuilder?.addTarget(it) }

            captureRequestBuilder?.set(
                CaptureRequest.CONTROL_AF_MODE,
                CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE
            )

            cameraCaptureSession?.setRepeatingRequest(
                captureRequestBuilder?.build()!!,
                null,
                backgroundHandler
            )

        } catch (e: Exception) {
            Log.e("MainActivity", "Error starting preview", e)
            addLogMessage("Preview error: ${e.message}")
        }
    }

    private fun processImage(image: Image?) {
        if (image == null) return

        frameCounter++

        try {
            val bitmap = yuv420ToBitmap(image)

            if (bitmap != null) {
                val rgbaMat = Mat(bitmap.height, bitmap.width, CvType.CV_8UC4)
                Utils.bitmapToMat(bitmap, rgbaMat)

                val grayMat = Mat()
                Imgproc.cvtColor(rgbaMat, grayMat, Imgproc.COLOR_RGBA2GRAY)

                detectArUcoMarkers(grayMat)

                bitmap.recycle()
                rgbaMat.release()
                grayMat.release()
            }
        } catch (e: Exception) {
            Log.e("MainActivity", "Error processing image", e)
        } finally {
            image.close()
        }
    }

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
            yuvImage.compressToJpeg(
                android.graphics.Rect(0, 0, image.width, image.height),
                100,
                outputStream
            )
            val jpegData = outputStream.toByteArray()

            return BitmapFactory.decodeByteArray(jpegData, 0, jpegData.size)

        } catch (e: Exception) {
            Log.e("MainActivity", "Error converting YUV", e)
            return null
        }
    }

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

                    // Обрабатываем маркеры ID 0 (левый), 1 (правый), 2 (HMD)
                    if (markerId < 0 || markerId > 2) continue

                    // Отслеживаем количество обнаружений
                    markerCounts[markerId] = (markerCounts[markerId] ?: 0) + 1

                    // Оцениваем позу из углов
                    val pose = arUcoTransform.estimatePose(corners[i], markerId)

                    if (pose != null && isConnected && udpSender != null) {
                        // Сохраняем последнюю позицию/ориентацию
                        lastPositions[markerId] = pose.position
                        lastQuaternions[markerId] = pose.quaternion

                        // Отправляем в VR Hub
                        udpSender?.sendControllerData(
                            controllerId = pose.controllerId,
                            quaternion = pose.quaternion,
                            position = pose.position
                        )

                        // Логируем каждые 30 обнаружений
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

    override fun onPause() {
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
    }

    private fun closeCamera() {
        cameraCaptureSession?.close()
        cameraCaptureSession = null
        cameraDevice?.close()
        cameraDevice = null
        imageReader?.close()
        imageReader = null
    }

    override fun onDestroy() {
        super.onDestroy()
        closeCamera()
        stopBackgroundThread()
        udpSender?.close()
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
}