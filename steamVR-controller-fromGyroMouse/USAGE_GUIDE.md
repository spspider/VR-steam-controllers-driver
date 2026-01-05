# GyroMouse VR Controller System

This system converts a gyroscopic mouse into a VR controller for SteamVR using ALVR.

## Quick Start

### 1. Build and Install Driver

```bash
# Build the driver
cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release

# Install (run as Administrator)
cd ..
install_gyromouse.bat
```

### 2. Test with Simple Mouse Tracking

```bash
# Test basic mouse movement tracking
python simple_mouse_tracker.py
```

This will track your mouse cursor and convert it to VR controller movement. Move your mouse around the screen to see the controller move in VR.

### 3. Generate ArUco Markers (Optional)

```bash
# Generate ArUco markers for position calibration
python generate_aruco_markers.py
```

Print the generated markers and attach them to your controllers for precise position tracking.

## System Components

### 1. Driver (`driver_gyromouse.dll`)
- Receives UDP data on port 5556
- Creates VR controller in SteamVR
- Handles position, rotation, and button input

### 2. Tracking Scripts

#### `simple_mouse_tracker.py` - Basic mouse tracking
- Tracks mouse cursor position
- Converts to VR controller position and rotation
- Good for initial testing

#### `simple_gyromouse_simulator.py` - Rotating simulation
- Sends simulated rotating controller data
- Useful for testing driver functionality

#### `enhanced_gyromouse_tracker.py` - Full system
- Mouse cursor tracking for position
- Real gyroscope data (if available)
- ArUco marker calibration
- Most complete solution

#### `gyromouse_aruco_tracker.py` - Original ArUco system
- ArUco marker position tracking
- Gyroscope rotation
- Camera-based position detection

## ArUco Marker System

### Marker IDs:
- **ID 0**: Left hand controller (your gyro mouse)
- **ID 1**: Right hand controller (second device)

### Setup:
1. Generate markers: `python generate_aruco_markers.py`
2. Print markers at 5cm x 5cm size
3. Attach ID=0 marker to your gyro mouse
4. Place markers in camera view
5. Run tracker with camera enabled

## Your Gyro Mouse

**Device**: HID\VID_2389&PID_00A8&REV_0200&MI_00

The system can work in multiple modes:
1. **Simulation mode**: No real gyro data, uses mathematical simulation
2. **Mouse tracking mode**: Uses cursor position for controller position
3. **HID mode**: Reads real gyroscope data from your mouse (requires hidapi)
4. **ArUco mode**: Uses camera tracking for precise position

## Configuration

### Port Configuration
- Driver listens on: **UDP port 5556**
- Change in `src/main.cpp` and tracking scripts if needed

### Sensitivity Settings
- Mouse sensitivity: Adjust in `simple_mouse_tracker.py`
- ArUco marker size: 5cm (adjust in tracking scripts)

## Troubleshooting

### Driver not loading
1. Check SteamVR logs for errors
2. Ensure driver is in correct folder
3. Verify openvrpaths.vrpath includes driver path
4. Run install_gyromouse.bat as Administrator

### No controller movement
1. Check if tracking script is sending data
2. Verify UDP port 5556 is not blocked
3. Test with simple_gyromouse_simulator.py first

### ArUco tracking not working
1. Install OpenCV: `pip install opencv-python`
2. Ensure camera is working
3. Print markers at correct size (5cm)
4. Good lighting conditions

## Dependencies

### Required for basic functionality:
- Windows 10/11
- SteamVR
- Python 3.7+

### Optional for enhanced features:
```bash
pip install opencv-python      # ArUco tracking
pip install hidapi            # Real gyro data
pip install pywin32           # Windows mouse API
pip install scipy            # Rotation calculations
pip install numpy            # Math operations
```

## File Structure

```
steamVR-controller-fromGyroMouse/
├── src/                      # C++ driver source
├── resources/               # Driver resources
├── build/                   # Build output
├── simple_mouse_tracker.py  # Basic mouse tracking
├── enhanced_gyromouse_tracker.py  # Full system
├── generate_aruco_markers.py     # Marker generation
├── install_gyromouse.bat    # Installation script
└── README.md               # This file
```

## Usage Tips

1. **Start Simple**: Begin with `simple_mouse_tracker.py` to verify basic functionality
2. **Calibration**: Use ArUco markers for precise position calibration
3. **Sensitivity**: Adjust mouse sensitivity for comfortable movement range
4. **Multiple Controllers**: Use different marker IDs for left/right hands
5. **Performance**: 60 FPS tracking provides smooth VR experience

## ALVR Integration

This system works with ALVR for wireless VR:
1. Install ALVR on PC
2. Install ALVR client on VR headset
3. This driver provides controller input
4. ALVR handles video streaming

The controller will appear in SteamVR and work with ALVR-streamed applications.