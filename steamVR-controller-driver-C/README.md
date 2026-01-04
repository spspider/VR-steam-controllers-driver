# CVDriver Setup Guide

## Project Structure

Create the following folder structure:

```
cvdriver/
├── src/
│   ├── driver.h
│   ├── main.cpp
│   ├── controller_device.cpp
│   └── network_client.cpp
├── resources/
│   ├── driver.vrdrivermanifest
│   └── input/
│       └── cvcontroller_profile.json
├── openvr/
│   ├── headers/
│   ├── lib/win64/
│   └── bin/win64/
├── CMakeLists.txt
└── simple_simulator.py
```

## Step-by-Step Installation

### 1. Download OpenVR SDK

1. Download OpenVR from: https://github.com/ValveSoftware/openvr
2. Extract it to `cvdriver/openvr/`
3. Ensure you have:
   - `openvr/headers/openvr_driver.h`
   - `openvr/lib/win64/openvr_api.lib`
   - `openvr/bin/win64/openvr_api.dll`

### 2. Build the Driver

```bash
mkdir build
cd build
cmake ..
cmake --build . --config Release
```

This will automatically:
- Compile the driver
- Copy files to `C:/Program Files (x86)/Steam/steamapps/common/SteamVR/drivers/cvdriver/`

### 3. Verify Installation

Check that these files exist:
```
SteamVR/drivers/cvdriver/
├── bin/win64/
│   ├── driver_cvdriver.dll
│   └── openvr_api.dll
└── resources/
    ├── driver.vrdrivermanifest
    └── input/
        └── cvcontroller_profile.json
```

### 4. Enable the Driver in SteamVR

**Option A: Manual Registration**
1. Open `SteamVR Settings` → `Developer`
2. Click `Add Driver`
3. Navigate to `C:/Program Files (x86)/Steam/steamapps/common/SteamVR/drivers/cvdriver`
4. Select the folder

**Option B: Edit steamvr.vrsettings**
1. Close SteamVR completely
2. Open: `C:/Program Files (x86)/Steam/config/steamvr.vrsettings`
3. Add to the file:
```json
{
  "driver_cvdriver": {
    "enable": true,
    "blocked_by_safe_mode": false
  },
  "steamvr": {
    "activateMultipleDrivers": true
  }
}
```

### 5. Test with Simulator

1. Install Python 3 if you don't have it
2. Run the simulator:
```bash
python simple_simulator.py
```

3. Start SteamVR
4. Check SteamVR System → Devices - you should see two controllers appear!

### 6. Check Logs

If controllers don't appear, check logs:
```
C:/Program Files (x86)/Steam/logs/vrserver.txt
```

Look for:
- `CVDriver v2.1 INIT START`
- `Controllers registered successfully`
- `Network client started on port 5555`
- `Received 1000 packets`

## Troubleshooting

### Controllers appear gray/inactive
- **Fixed!** The new code includes `RunFrame()` which pushes pose updates every frame
- Verify the simulator is running and sending data
- Check that firewall isn't blocking port 5555

### Controllers don't show up at all
1. Make sure `driver.vrdrivermanifest` is in the resources folder
2. Verify the driver is enabled in SteamVR settings
3. Try restarting SteamVR completely (close all SteamVR processes)
4. Check if other drivers are conflicting

### Buttons don't work
- The input profile should be automatically loaded
- Try binding controls in SteamVR Settings → Controllers → Manage Controller Bindings

### Network data not received
- Check Windows Firewall settings for UDP port 5555
- Verify simulator is sending to 127.0.0.1:5555
- Check vrserver logs for "Network client started"

## Key Changes Made

1. **Added `RunFrame()` method** - This pushes pose updates to SteamVR every frame (was missing!)
2. **Proper input component creation** - Using VRDriverInput API correctly
3. **Fixed property setup** - Added all required controller properties
4. **Better error handling** - More detailed logging
5. **Input profile** - Created proper JSON profile for controller bindings

## Using with ALVR

To use these controllers with ALVR:
1. Make sure ALVR is installed and working
2. The controllers should appear automatically in VR
3. ALVR will handle the HMD tracking
4. Your custom controllers will handle hand tracking

## Testing Movement

The simulator creates rotating motion and button presses:
- Controllers rotate around Y axis
- Buttons cycle every 2 seconds
- Trigger values oscillate
- Position updates based on accelerometer simulation

You should see the controllers moving in SteamVR's device view!

## Next Steps

1. Replace the simulator with your real Arduino code
2. Adjust the quaternion mapping if the rotation feels wrong
3. Calibrate the accelerometer data for position tracking
4. Add more button inputs if needed
5. Create custom render models (optional)


# Установите C++ инструменты для VS Code
# Установите CMake
# Скачайте OpenVR SDK с GitHub: https://github.com/ValveSoftware/openvr

rm -r build/*
mkdir build && cd build
clear;cmake .. -G "Visual Studio 17 2022" -A x64; cmake --build . --config Release


4. Создайте файл настроек:
Путь: C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver\resources\settings\default.vrsettings
json{
   "driver_cvdriver": {
      "enable": true,
      "blocked_by_safe_mode": false
   }
}
5. Добавьте драйвер в openvrpaths.vrpath:
Откройте: C:\Users\<ВашеИмя>\AppData\Local\openvr\openvrpaths.vrpath
Добавьте:
json{
  "external_drivers": [
    "C:\\Program Files (x86)\\Steam\\steamapps\\common\\SteamVR\\drivers\\cvdriver"
  ]
}