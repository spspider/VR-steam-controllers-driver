#!/usr/bin/env python3
"""
Example: Testing Webcam ArUco Source Independently

This script demonstrates how to use the WebcamArucoSource module
independently for testing and debugging. It shows:
- Basic setup and configuration
- Real-time marker tracking
- Data retrieval and display
- Performance monitoring

Useful for:
- Testing camera setup before integrating with VR hub
- Debugging marker detection issues
- Verifying camera calibration
- Testing different marker sizes and camera settings
"""
import sys
import time
from webcam_aruco_source import WebcamArucoSource


def main():
    print("=" * 70)
    print("Webcam ArUco Source - Standalone Test")
    print("=" * 70)
    print()
    print("This script tests the webcam ArUco tracking independently.")
    print("It will open your webcam and detect ArUco markers with IDs 0, 1, 2.")
    print()
    print("Setup:")
    print("  1. Print ArUco markers (DICT_4X4_50) with IDs 0, 1, 2")
    print("  2. Measure the marker size and update MARKER_SIZE below")
    print("  3. Place markers in view of your webcam")
    print("  4. Run this script")
    print()
    print("Controls:")
    print("  - ESC key in debug window to close window")
    print("  - Ctrl+C to stop the script")
    print()
    
    # ═══════════════════════════════════════════════════════════════════
    # CONFIGURATION - Adjust these values for your setup
    # ═══════════════════════════════════════════════════════════════════
    
    CAMERA_INDEX = 0          # 0 for default camera, 1 for second camera, etc.
    RESOLUTION = (640, 480)   # Camera resolution (width, height)
    MARKER_SIZE = 0.05        # Physical size of your ArUco markers in meters (e.g., 0.05 = 5cm)
    SHOW_DEBUG_WINDOW = True  # Show live camera feed with detected markers
    
    # ═══════════════════════════════════════════════════════════════════
    
    print(f"Configuration:")
    print(f"  Camera Index: {CAMERA_INDEX}")
    print(f"  Resolution: {RESOLUTION[0]}x{RESOLUTION[1]}")
    print(f"  Marker Size: {MARKER_SIZE}m ({MARKER_SIZE*100}cm)")
    print(f"  Debug Window: {SHOW_DEBUG_WINDOW}")
    print()
    
    # Simple logging callback
    def log_callback(message, level):
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    # Create webcam source
    print("Initializing webcam source...")
    webcam = WebcamArucoSource(
        camera_index=CAMERA_INDEX,
        resolution=RESOLUTION,
        marker_size=MARKER_SIZE,
        show_debug_window=SHOW_DEBUG_WINDOW,
        log_callback=log_callback
    )
    
    # Start tracking
    print("Starting ArUco detection...")
    if not webcam.start():
        print("ERROR: Failed to start webcam source!")
        print("Possible issues:")
        print("  - Camera is not connected or not accessible")
        print("  - Camera index is wrong (try changing CAMERA_INDEX)")
        print("  - Another application is using the camera")
        return 1
    
    print()
    print("✅ Webcam source started successfully!")
    print()
    print("Tracking markers... (Press Ctrl+C to stop)")
    print()
    print("-" * 70)
    
    try:
        last_report_time = time.time()
        report_interval = 2.0  # Report every 2 seconds
        
        while True:
            current_time = time.time()
            
            # Periodic status report
            if current_time - last_report_time >= report_interval:
                print()
                print(f"Status Report @ {time.strftime('%H:%M:%S')}")
                print("-" * 70)
                
                # Get tracking statistics
                stats = webcam.get_stats()
                print(f"FPS: {stats['fps']:.1f} | Frames: {stats['frame_count']} | Detections: {stats['detection_count']}")
                print()
                
                # Report status for each controller
                device_names = {0: "LEFT Controller", 1: "RIGHT Controller", 2: "HMD"}
                
                for controller_id in [0, 1, 2]:
                    data = webcam.get_marker_data(controller_id)
                    
                    if data and data['tracking']:
                        pos = data['position']
                        quat = data['quaternion']
                        age = current_time - data['timestamp']
                        
                        print(f"  {device_names[controller_id]:20s} [TRACKING]")
                        print(f"    Position:    ({pos[0]:+.3f}, {pos[1]:+.3f}, {pos[2]:+.3f}) m")
                        print(f"    Quaternion:  [{quat[0]:+.3f}, {quat[1]:+.3f}, {quat[2]:+.3f}, {quat[3]:+.3f}]")
                        print(f"    Data age:    {age*1000:.1f} ms")
                    else:
                        print(f"  {device_names[controller_id]:20s} [NOT VISIBLE]")
                
                print("-" * 70)
                last_report_time = current_time
            
            # Small sleep to prevent CPU overload
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print()
        print()
        print("Stopping...")
    
    finally:
        # Clean up
        webcam.stop()
        print()
        print("=" * 70)
        print("Final Statistics:")
        stats = webcam.get_stats()
        print(f"  Total Frames:     {stats['frame_count']}")
        print(f"  Total Detections: {stats['detection_count']}")
        print(f"  Average FPS:      {stats['fps']:.1f}")
        print("=" * 70)
        print()
        print("✅ Test completed successfully!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())