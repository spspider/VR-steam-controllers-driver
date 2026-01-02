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
import android.util.SparseIntArray
import android.view.Surface
import android.view.TextureView
import android.view.ViewGroup
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
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.*
import kotlin.math.sqrt

class MainActivity : AppCompatActivity() {

    private lateinit var textureView: TextureView
    private lateinit var logTextView: TextView
    private lateinit var statusTextView: TextView
    private lateinit var ipAddress: EditText
    private lateinit var connectButton: Button

    private var cameraDevice: CameraDevice? = null
    private var cameraCaptureSession: CameraCaptureSession? = null
    private var imageReader: ImageReader? = null
    private var backgroundHandler: Handler? = null
    private var backgroundThread: HandlerThread? = null

    private lateinit var detector: ArucoDetector
    private lateinit var dictionary: Dictionary

    private val udpSocket = DatagramSocket()
    private var serverAddress: InetAddress? = null
    private val serverPort = 4242
    private var isConnected = false

    private val logMessages = mutableListOf<String>()
    private var frameCounter = 0
    private var markersDetected = 0
    private var processingEnabled = true

    // Ориентация устройства
    private val ORIENTATIONS = SparseIntArray().apply {
        append(Surface.ROTATION_0, 90)
        append(Surface.ROTATION_90, 0)
        append(Surface.ROTATION_180, 270)
        append(Surface.ROTATION_270, 180)
    }

    private fun addLogMessage(message: String) {
        logMessages.add("${System.currentTimeMillis() % 10000}: $message")
        if (logMessages.size > 10) logMessages.removeAt(0)
        runOnUiThread {
            logTextView.text = logMessages.joinToString("\n")
            statusTextView.text = "Frames: $frameCounter | Markers: $markersDetected"
        }
    }

    private val requiredPermissions = arrayOf(
        Manifest.permission.CAMERA,
        Manifest.permission.INTERNET
    )

    private val REQUEST_CODE_PERMISSIONS = 10

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

        // Проверяем OpenCV
        if (!OpenCVLoader.initLocal()) {
            Log.e("MainActivity", "OpenCV initialization failed!")
            Toast.makeText(this, "OpenCV initialization failed!", Toast.LENGTH_LONG).show()
            return
        }

        setContentView(R.layout.activity_main)

        // Инициализация UI
        textureView = findViewById(R.id.texture_view)
        logTextView = findViewById(R.id.logTextView)
        statusTextView = findViewById(R.id.statusTextView)
        ipAddress = findViewById(R.id.ipAddress)
        connectButton = findViewById(R.id.connectButton)

        // Устанавливаем дефолтный IP
        ipAddress.setText("192.168.1.199")
        addLogMessage("App started - OpenCV loaded")

        // Инициализация ArUco
        try {
            dictionary = Objdetect.getPredefinedDictionary(Objdetect.DICT_6X6_250)
            detector = ArucoDetector(dictionary)
            addLogMessage("ArUco detector ready for DICT_6X6_250")
        } catch (e: Exception) {
            Log.e("MainActivity", "ArUco init error: ${e.message}")
            addLogMessage("ArUco init failed: ${e.message}")
        }

        // Настройка кнопки подключения
        connectButton.setOnClickListener {
            val ip = ipAddress.text.toString()
            if (ip.isNotEmpty()) {
                CoroutineScope(Dispatchers.IO).launch {
                    try {
                        serverAddress = InetAddress.getByName(ip)
                        isConnected = true
                        runOnUiThread {
                            Toast.makeText(this@MainActivity, "Connected to $ip", Toast.LENGTH_SHORT).show()
                            addLogMessage("Connected to $ip")
                        }
                    } catch (e: Exception) {
                        runOnUiThread {
                            Toast.makeText(this@MainActivity, "Invalid IP", Toast.LENGTH_SHORT).show()
                            addLogMessage("Connection failed")
                        }
                    }
                }
            }
        }

        // Кнопка для включения/выключения обработки
        val toggleButton = Button(this).apply {
            text = "Toggle Processing"
            setOnClickListener {
                processingEnabled = !processingEnabled
                addLogMessage(if (processingEnabled) "Processing enabled" else "Processing disabled")
            }
        }
        addContentView(toggleButton, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ))

        // Проверяем и запрашиваем разрешения
        if (checkPermissions()) {
            initializeCamera()
        } else {
            requestPermissions()
        }
    }

    private fun initializeCamera() {
        startBackgroundThread()

        // Настраиваем TextureView
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

    private fun startBackgroundThread() {
        backgroundThread = HandlerThread("CameraBackground").also { it.start() }
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
        val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
        try {
            val cameraId = cameraManager.cameraIdList[0] // Используем заднюю камеру

            // Получаем характеристики камеры
            val characteristics = cameraManager.getCameraCharacteristics(cameraId)
            val map = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
                ?: throw RuntimeException("Cannot get available preview sizes")

            // Выбираем размер изображения
            val previewSize = chooseOptimalSize(map.getOutputSizes(SurfaceTexture::class.java), width, height)

            // Настраиваем ImageReader для получения кадров
            imageReader = ImageReader.newInstance(
                previewSize.width,
                previewSize.height,
                ImageFormat.YUV_420_888,
                2
            ).apply {
                setOnImageAvailableListener({ reader ->
                    processImage(reader.acquireLatestImage())
                }, backgroundHandler)
            }

            textureView.surfaceTexture?.setDefaultBufferSize(previewSize.width, previewSize.height)

            // Запрашиваем разрешение на использование камеры
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
                    addLogMessage("Camera opened: ${previewSize.width}x${previewSize.height}")
                    createCameraPreviewSession()
                }

                override fun onDisconnected(camera: CameraDevice) {
                    cameraDevice?.close()
                    cameraDevice = null
                }

                override fun onError(camera: CameraDevice, error: Int) {
                    cameraDevice?.close()
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
        // Выбираем размер 640x480 для быстрой обработки
        val targetSize = Size(640, 480)

        for (size in choices) {
            if (size.width == targetSize.width && size.height == targetSize.height) {
                return size
            }
        }

        // Если точного совпадения нет, выбираем первый доступный размер
        return choices.firstOrNull() ?: Size(640, 480)
    }

    private fun createCameraPreviewSession() {
        try {
            val texture = textureView.surfaceTexture
            texture?.setDefaultBufferSize(textureView.width, textureView.height)

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
                        addLogMessage("Camera session configuration failed")
                    }
                },
                null
            )

        } catch (e: Exception) {
            Log.e("MainActivity", "Error creating camera preview session", e)
            addLogMessage("Session error: ${e.message}")
        }
    }

    private fun startPreview() {
        try {
            val captureRequestBuilder = cameraDevice?.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
            captureRequestBuilder?.addTarget(Surface(textureView.surfaceTexture))
            imageReader?.surface?.let { captureRequestBuilder?.addTarget(it) }

            // Настраиваем автофокус
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
            Log.e("MainActivity", "Error starting camera preview", e)
            addLogMessage("Preview error: ${e.message}")
        }
    }

    private fun processImage(image: Image?) {
        if (!processingEnabled || image == null) {
            image?.close()
            return
        }

        frameCounter++

        try {
            // Конвертируем YUV_420_888 в Bitmap
            val bitmap = yuv420ToBitmap(image)

            if (bitmap != null) {
                // Конвертируем Bitmap в Mat
                val rgbaMat = Mat(bitmap.height, bitmap.width, CvType.CV_8UC4)
                Utils.bitmapToMat(bitmap, rgbaMat)

                // Конвертируем RGBA в GRAY для детекции
                val grayMat = Mat()
                Imgproc.cvtColor(rgbaMat, grayMat, Imgproc.COLOR_RGBA2GRAY)

                // Обнаружение ArUco маркеров
                detectArUcoMarkers(grayMat)

                bitmap.recycle()
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

            // Y plane
            yBuffer.get(nv21, 0, ySize)

            // V plane
            vBuffer.get(nv21, ySize, vSize)

            // U plane
            uBuffer.get(nv21, ySize + vSize, uSize)

            // Создаем YuvImage
            val yuvImage = android.graphics.YuvImage(
                nv21,
                ImageFormat.NV21,
                image.width,
                image.height,
                null
            )

            val outputStream = ByteArrayOutputStream()
            yuvImage.compressToJpeg(android.graphics.Rect(0, 0, image.width, image.height), 100, outputStream)
            val jpegData = outputStream.toByteArray()

            return BitmapFactory.decodeByteArray(jpegData, 0, jpegData.size)

        } catch (e: Exception) {
            Log.e("MainActivity", "Error converting YUV to Bitmap", e)
            return null
        }
    }

    private fun detectArUcoMarkers(grayMat: Mat) {
        if (!::detector.isInitialized) return

        try {
            val corners = ArrayList<Mat>()
            val ids = Mat()

            // Детектируем маркеры
            detector.detectMarkers(grayMat, corners, ids)

            val markerCount = corners.size
            markersDetected = markerCount

            if (markerCount > 0 && !ids.empty()) {
                // Обрабатываем каждый маркер
                for (i in 0 until markerCount) {
                    val cornerMat = corners[i]

                    // Получаем ID маркера
                    val idArray = IntArray(1)
                    ids.get(i, 0, idArray)
                    val id = idArray[0]

                    // Вычисляем центр маркера
                    val cornerData = FloatArray(8)
                    cornerMat.get(0, 0, cornerData)

                    val centerX = (cornerData[0] + cornerData[2] + cornerData[4] + cornerData[6]) / 4.0
                    val centerY = (cornerData[1] + cornerData[3] + cornerData[5] + cornerData[7]) / 4.0

                    // Вычисляем размер маркера
                    val width = sqrt(
                        (cornerData[2] - cornerData[0]) * (cornerData[2] - cornerData[0]) +
                                (cornerData[3] - cornerData[1]) * (cornerData[3] - cornerData[1])
                    )

                    // Оценка глубины
                    val z = 500.0 / width

                    // Отправляем данные
                    if (isConnected && serverAddress != null) {
                        sendUdpData(id, centerX, centerY, z)
                    }
                }

                // Логируем каждые 30 кадров
                if (frameCounter % 30 == 0) {
                    runOnUiThread {
                        addLogMessage("Detected $markerCount markers")
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("MainActivity", "ArUco detection error", e)
        }
    }

    private fun sendUdpData(id: Int, x: Double, y: Double, z: Double) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val data = "$id:${x.toInt()},${y.toInt()},${z.toInt()}".toByteArray()
                val packet = DatagramPacket(data, data.size, serverAddress, serverPort)
                udpSocket.send(packet)
            } catch (e: Exception) {
                // Игнорируем ошибки отправки
            }
        }
    }

    override fun onPause() {
        super.onPause()
        processingEnabled = false
        stopBackgroundThread()
        closeCamera()
    }

    override fun onResume() {
        super.onResume()
        processingEnabled = true
        if (textureView.isAvailable) {
            initializeCamera()
        }
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
        udpSocket.close()
    }
}