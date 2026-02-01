#!/usr/bin/env python3
"""
Module webcam_aruco_source.py
Webcam-based ArUco tracking source for VR controllers

This module provides ArUco marker tracking using a webcam as an alternative/supplement
to the Android UDP source. It detects markers in real-time and provides position and
orientation data in the same format as the Android app.

Key features:
- Configurable camera index and resolution
- Real-time ArUco marker detection (IDs 0, 1, 2 for LEFT, RIGHT, HMD)
- Camera calibration support (intrinsic matrix and distortion coefficients)
- Thread-safe data access
- Optional debug visualization window
- Automatic marker size configuration
"""
import cv2
import numpy as np
import threading
import time
from typing import Optional, Callable, Dict, Tuple, List
from scipy.spatial.transform import Rotation
from data_structures import ControllerData


class WebcamArucoSource:
    """
    Webcam-based ArUco marker tracking source
    
    Detects ArUco markers (DICT_4X4_50) and provides position/orientation data
    for VR controllers. Runs in a separate thread to avoid blocking the main loop.
    """
    
    def __init__(self, 
                 camera_index: int = 0,
                 resolution: Tuple[int, int] = (640, 480),
                 marker_size: float = 0.05,
                 show_debug_window: bool = True,
                 log_callback: Optional[Callable] = None):
        """
        Initialize webcam ArUco tracking source
        
        Args:
            camera_index: OpenCV camera device index (0 for default camera)
            resolution: Camera resolution (width, height) in pixels
            marker_size: Physical size of ArUco markers in meters (e.g., 0.05 = 5cm)
            show_debug_window: Whether to show live camera feed with detected markers
            log_callback: Optional callback for logging messages (message, level)
        """
        self.camera_index = camera_index
        self.resolution = resolution
        self.marker_size = marker_size
        self.show_debug_window = show_debug_window
        self.log_callback = log_callback
        
        # Camera and ArUco detector (initialized in start())
        self.camera: Optional[cv2.VideoCapture] = None
        self.aruco_dict = None
        self.aruco_params = None
        self.detector = None
        
        # Camera calibration parameters
        # These are approximate values - for better accuracy, perform camera calibration
        # using OpenCV's calibrateCamera() with a checkerboard pattern
        width, height = resolution
        focal_length = width * 1.2  # Rough estimate based on typical webcam FOV
        self.camera_matrix = np.array([
            [focal_length, 0, width / 2],
            [0, focal_length, height / 2],
            [0, 0, 1]
        ], dtype=np.float64)
        self.dist_coeffs = np.zeros((4, 1), dtype=np.float64)  # Assume no distortion
        
        # Thread control
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        
        # Detected marker data (controller_id -> data dict)
        # Each entry contains: position, quaternion, timestamp, tracking_status
        self.marker_data: Dict[int, dict] = {
            0: self._create_empty_marker_data(),  # LEFT
            1: self._create_empty_marker_data(),  # RIGHT
            2: self._create_empty_marker_data(),  # HMD
        }
        
        # Statistics
        self.frame_count = 0
        self.detection_count = 0
        self.last_fps_time = time.time()
        self.current_fps = 0.0
    
    def _create_empty_marker_data(self) -> dict:
        """Create empty marker data structure"""
        return {
            'position': [0.0, 0.0, 0.0],
            'quaternion': [1.0, 0.0, 0.0, 0.0],  # [W, X, Y, Z]
            'timestamp': 0.0,
            'tracking': False
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log message via callback if available"""
        if self.log_callback:
            self.log_callback(message, level)
    
    def set_camera_calibration(self, camera_matrix: np.ndarray, dist_coeffs: np.ndarray):
        """
        Set camera intrinsic calibration parameters
        
        Args:
            camera_matrix: 3x3 camera matrix (focal lengths and principal point)
            dist_coeffs: Distortion coefficients (k1, k2, p1, p2, [k3])
        """
        self.camera_matrix = camera_matrix.astype(np.float64)
        self.dist_coeffs = dist_coeffs.astype(np.float64)
        self.log(f"Camera calibration updated: fx={camera_matrix[0,0]:.1f}, fy={camera_matrix[1,1]:.1f}")
    
    def start(self) -> bool:
        """
        Start the webcam capture and ArUco detection thread
        
        Returns:
            True if successfully started, False otherwise
        """
        if self.running:
            self.log("Webcam source already running", "WARN")
            return False
        
        try:
            # Initialize camera
            self.camera = cv2.VideoCapture(self.camera_index)
            if not self.camera.isOpened():
                self.log(f"Failed to open camera {self.camera_index}", "ERROR")
                return False
            
            # Set camera resolution
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            
            # Get actual resolution (may differ from requested)
            actual_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.log(f"Camera opened: {actual_width}x{actual_height}")
            
            # Initialize ArUco detector
            self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            self.aruco_params = cv2.aruco.DetectorParameters()
            
            # Configure detector parameters for speed and reliability
            # These settings prioritize detection speed while maintaining reasonable accuracy
            self.aruco_params.adaptiveThreshWinSizeMin = 3
            self.aruco_params.adaptiveThreshWinSizeMax = 23
            self.aruco_params.adaptiveThreshWinSizeStep = 10
            self.aruco_params.minMarkerPerimeterRate = 0.03
            self.aruco_params.maxMarkerPerimeterRate = 4.0
            self.aruco_params.polygonalApproxAccuracyRate = 0.05
            self.aruco_params.minCornerDistanceRate = 0.05
            self.aruco_params.minDistanceToBorder = 3
            self.aruco_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_NONE  # Speed boost
            self.aruco_params.errorCorrectionRate = 0.6
            
            self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
            
            # Start detection thread
            self.running = True
            self.thread = threading.Thread(target=self._detection_loop, daemon=True)
            self.thread.start()
            
            self.log("✅ Webcam ArUco source started successfully")
            return True
            
        except Exception as e:
            self.log(f"Failed to start webcam source: {e}", "ERROR")
            if self.camera:
                self.camera.release()
                self.camera = None
            return False
    
    def stop(self):
        """Stop the webcam capture and detection thread"""
        if not self.running:
            return
        
        self.running = False
        
        # Wait for thread to finish
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
        
        # Release camera
        if self.camera:
            self.camera.release()
            self.camera = None
        
        # Close debug window if open
        if self.show_debug_window:
            cv2.destroyAllWindows()
        
        self.log("Webcam ArUco source stopped")
    
    def _detection_loop(self):
        """
        Main detection loop running in separate thread
        Continuously captures frames, detects markers, and updates marker data
        """
        self.log("ArUco detection loop started")
        
        while self.running:
            try:
                # Capture frame
                ret, frame = self.camera.read()
                if not ret:
                    self.log("Failed to read camera frame", "WARN")
                    time.sleep(0.1)
                    continue
                
                self.frame_count += 1
                
                # Detect ArUco markers
                corners, ids, rejected = self.detector.detectMarkers(frame)
                
                # Reset tracking status for all controllers
                with self.lock:
                    for controller_id in self.marker_data:
                        self.marker_data[controller_id]['tracking'] = False
                
                # Process detected markers
                if ids is not None:
                    for i, marker_id in enumerate(ids.flatten()):
                        # Only process markers for known controllers (0, 1, 2)
                        if marker_id not in [0, 1, 2]:
                            continue
                        
                        # Estimate pose using solvePnP
                        position, quaternion, rvec, tvec = self._estimate_marker_pose(corners[i])
                        
                        if position is not None and quaternion is not None:
                            # Update marker data
                            with self.lock:
                                self.marker_data[marker_id] = {
                                    'position': position,
                                    'quaternion': quaternion,
                                    'timestamp': time.time(),
                                    'tracking': True
                                }
                            
                            self.detection_count += 1
                            
                            # Draw marker for visualization
                            if self.show_debug_window:
                                cv2.drawFrameAxes(frame, self.camera_matrix, self.dist_coeffs, 
                                    rvec, tvec, 0.03)
                    
                    # Draw all detected markers
                    if self.show_debug_window:
                        cv2.aruco.drawDetectedMarkers(frame, corners, ids)
                
                # Show debug window
                if self.show_debug_window:
                    self._draw_debug_info(frame)
                    cv2.imshow('Webcam ArUco Tracking', frame)
                    
                    # Check for key press (ESC to close window)
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27:  # ESC
                        self.log("Debug window closed by user")
                        self.show_debug_window = False
                        cv2.destroyAllWindows()
                
                # Update FPS calculation
                current_time = time.time()
                if current_time - self.last_fps_time >= 1.0:
                    self.current_fps = self.frame_count / (current_time - self.last_fps_time)
                    self.frame_count = 0
                    self.last_fps_time = current_time
                
                # Small sleep to prevent CPU overload (target ~30 FPS)
                time.sleep(0.001)
                
            except Exception as e:
                self.log(f"Error in detection loop: {e}", "ERROR")
                time.sleep(0.1)
        
        self.log("ArUco detection loop stopped")
    
    def _estimate_marker_pose(self, marker_corners) -> Tuple[Optional[List[float]], Optional[List[float]], Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Estimate 6DOF pose of ArUco marker using solvePnP
        
        Args:
            marker_corners: 4 corner points of detected marker in image coordinates
            
        Returns:
            Tuple of (position [X, Y, Z], quaternion [W, X, Y, Z], rvec, tvec) or (None, None, None, None) if estimation fails
        """
        try:
            # Define 3D coordinates of marker corners in marker's coordinate system
            # Marker is assumed to be square and flat (Z=0)
            half_size = self.marker_size / 2
            obj_points = np.array([
                [-half_size,  half_size, 0],  # Top-left
                [ half_size,  half_size, 0],  # Top-right
                [ half_size, -half_size, 0],  # Bottom-right
                [-half_size, -half_size, 0]   # Bottom-left
            ], dtype=np.float32)
            
            # Image coordinates of marker corners
            img_points = marker_corners[0].astype(np.float32)
            
            # Solve PnP to get rotation vector and translation vector
            success, rvec, tvec = cv2.solvePnP(
                obj_points, img_points,
                self.camera_matrix, self.dist_coeffs,
                flags=cv2.SOLVEPNP_IPPE_SQUARE  # Fast and accurate for square markers
            )
            
            if not success:
                return None, None, None, None
            
            # Convert translation vector to position in VR coordinate system
            # OpenCV camera coordinates: X right, Y down, Z forward (away from camera)
            # VR coordinates: X right, Y up, Z backward (toward user)
            # Transform: X stays, Y inverts, Z inverts
            position = [
                float(tvec[0][0]),   # X: right (same)
                float(-tvec[1][0]),  # Y: up (invert down->up)
                float(-tvec[2][0])   # Z: toward user (invert away->toward)
            ]
            
            # Convert rotation vector to quaternion
            # First convert rvec to rotation matrix, then to quaternion
            rot_mat, _ = cv2.Rodrigues(rvec)
            
            # Use scipy for robust rotation conversion
            rotation = Rotation.from_matrix(rot_mat)
            quat_xyzw = rotation.as_quat()  # Returns [X, Y, Z, W]
            
            # Convert to [W, X, Y, Z] format used throughout the system
            quaternion = [
                float(quat_xyzw[3]),  # W
                float(quat_xyzw[0]),  # X
                float(quat_xyzw[1]),  # Y
                float(quat_xyzw[2])   # Z
            ]
            
            return position, quaternion, rvec, tvec
            
        except Exception as e:
            self.log(f"Pose estimation error: {e}", "ERROR")
            return None, None, None, None
    
    def _draw_debug_info(self, frame):
        """Draw debug information overlay on camera frame"""
        height, width = frame.shape[:2]
        
        # Semi-transparent overlay for better text readability
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (width, 140), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)
        
        # Title
        cv2.putText(frame, "Webcam ArUco Tracking", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # FPS
        cv2.putText(frame, f"FPS: {self.current_fps:.1f}", (10, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Tracking status for each controller
        device_names = {0: "LEFT", 1: "RIGHT", 2: "HMD"}
        y_offset = 75
        
        with self.lock:
            for controller_id in [0, 1, 2]:
                data = self.marker_data[controller_id]
                name = device_names[controller_id]
                
                if data['tracking']:
                    pos = data['position']
                    color = (0, 255, 0)  # Green
                    status_text = f"{name}: TRACKING  Pos({pos[0]:+.3f}, {pos[1]:+.3f}, {pos[2]:+.3f})"
                else:
                    color = (0, 0, 255)  # Red
                    status_text = f"{name}: NOT VISIBLE"
                
                cv2.putText(frame, status_text, (10, y_offset),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
                y_offset += 20
        
        # Instructions
        cv2.putText(frame, "Press ESC to close window", (10, height - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    
    def get_marker_data(self, controller_id: int) -> Optional[dict]:
        """
        Get latest marker data for a specific controller
        
        Args:
            controller_id: Controller ID (0=LEFT, 1=RIGHT, 2=HMD)
            
        Returns:
            Dictionary with 'position', 'quaternion', 'timestamp', 'tracking' keys,
            or None if controller_id is invalid
        """
        if controller_id not in self.marker_data:
            return None
        
        with self.lock:
            # Return a copy to avoid race conditions
            return self.marker_data[controller_id].copy()
    
    def update_controller_data(self, controller: ControllerData, max_age: float = 0.5) -> bool:
        """
        Update ControllerData object with latest marker data from webcam
        
        This method populates the aruco_position and aruco_quaternion fields
        in the same way the Android UDP receiver does, allowing the calibration
        system to work identically regardless of source.
        
        Args:
            controller: ControllerData object to update
            max_age: Maximum age in seconds for marker data to be considered valid
            
        Returns:
            True if data was updated, False if no fresh data available
        """
        data = self.get_marker_data(controller.controller_id)
        
        if not data or not data['tracking']:
            return False
        
        # Check if data is fresh enough
        age = time.time() - data['timestamp']
        if age > max_age:
            return False
        
        # Update ArUco data fields (same as Android UDP source)
        controller.aruco_position = data['position']
        controller.aruco_quaternion = data['quaternion']
        controller.aruco_last_update = data['timestamp']
        
        # Mark source as webcam with camera index for debugging
        controller.source = f"webcam:cam{self.camera_index}"
        
        return True
    
    def is_running(self) -> bool:
        """Check if webcam source is currently running"""
        return self.running
    
    def get_fps(self) -> float:
        """Get current frames per second"""
        return self.current_fps
    
    def get_stats(self) -> dict:
        """
        Get tracking statistics
        
        Returns:
            Dictionary with frame_count, detection_count, fps
        """
        return {
            'frame_count': self.frame_count,
            'detection_count': self.detection_count,
            'fps': self.current_fps
        }