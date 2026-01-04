# VR Driver Testing Guide

## 1. Build and Install the Driver

```bash
cd build
cmake --build . --config Release
```

This will automatically copy files to SteamVR directory.

## 2. Verify Driver Installation

Check these files exist:
- `C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver\bin\win64\driver_cvdriver.dll`
- `C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver\resources\driver.vrdrivermanifest`

## 3. Start the Simulator

Run the Python simulator:
```bash
python simple_simulator.py
```

You should see output like:
```
Starting simple controller simulator on 127.0.0.1:5555
Simulating 2 controllers with rotating motion and button presses
Packet 1: Controllers active, time: 0.1s
```

## 4. Check SteamVR Logs

### Start SteamVR and check logs:
1. Open SteamVR
2. Go to SteamVR Settings → Developer → Enable Developer Mode
3. Check logs at: `%LOCALAPPDATA%\openvr\vrserver.txt`

### Look for these log entries:

**✅ GOOD - Driver loaded successfully:**
```
[Info] - Loaded server driver cvdriver (IServerTrackedDeviceProvider_004)
[Info] - Driver 'cvdriver' started activation of tracked device with serial number 'CV_Controller_Left'
[Info] - Driver 'cvdriver' started activation of tracked device with serial number 'CV_Controller_Right'
```

**❌ BAD - No devices found:**
```
[Warning] - Driver cvdriver has no suitable devices.
```

## 5. Verify Controllers in SteamVR

### Method 1: SteamVR Status Window
- Open SteamVR Status window
- You should see 2 controller icons (green = connected, gray = disconnected)
- Controllers should show as "CV_Controller_Left" and "CV_Controller_Right"

### Method 2: SteamVR Settings
1. Open SteamVR Settings
2. Go to "Controllers" tab
3. Click "Manage Controller Bindings"
4. You should see your controllers listed

### Method 3: Developer Console
1. In SteamVR, press `Ctrl+Alt+Shift+D` to open developer console
2. Type: `status`
3. Look for your controllers in the device list

## 6. Test Controller Tracking

With the simulator running:

1. **Position Tracking**: Controllers should appear in VR space and move
2. **Rotation Tracking**: Controllers should rotate as the simulator changes orientation
3. **Button Presses**: Watch for button press events in SteamVR
4. **Trigger**: Trigger values should change

## 7. Troubleshooting

### Problem: "Driver cvdriver has no suitable devices"
**Solution**: 
- Make sure the simulator is running BEFORE starting SteamVR
- Check that UDP port 5555 is not blocked by firewall
- Verify the driver is receiving data by adding debug prints

### Problem: Controllers appear but don't move
**Solution**:
- Check that `UpdateFromArduino()` is being called
- Verify quaternion values are normalized
- Check coordinate system (OpenVR uses different axes than some systems)

### Problem: Controllers disconnect after a few seconds
**Solution**:
- Ensure simulator is sending data continuously
- Check `CheckConnection()` timeout (currently 1 second)
- Verify packet checksums are correct

## 8. Advanced Testing

### Test with Real Joystick:
```bash
pip install pygame
python controller_simulator.py
```

### Monitor Network Traffic:
```bash
netstat -an | findstr :5555
```

### Debug Driver Output:
Add debug prints to your driver and check SteamVR logs.

## 9. Expected Behavior

When everything works correctly:
1. Start simulator → Controllers appear in SteamVR
2. Controllers rotate and move in VR space
3. Button presses are detected
4. Trigger values change
5. Controllers stay connected as long as simulator runs
6. Controllers disconnect when simulator stops

## 10. Next Steps

Once basic tracking works:
1. Improve position tracking algorithm
2. Add proper coordinate system transformations
3. Implement haptic feedback
4. Create proper input bindings
5. Add calibration system