# CVDriver Setup Guide

## Project Structure

Create the following folder structure:

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

### Step 2: Install the driver manually

1. Save `manual_install.bat` to the project root
2. Run it **as Administrator** (right‑click → “Run as administrator”)
3. The script will automatically copy all required files

### Step 3: Verify installation

1. Run `check_installation.bat`
2. Make sure all 4 files are present:
   - driver_cvdriver.dll
   - openvr_api.dll
   - driver.vrdrivermanifest
   - cvcontroller_profile.json

### Step 4: Register the driver in SteamVR

Method 1: Using openvrpaths.vrpath (RECOMMENDED)

1. Open the file:
   C:\Users\<YourName>\AppData\Local\openvr\openvrpaths.vrpath

2. Add the driver path to the `external_drivers` section:

   {
     "external_drivers": [
       "C:\\Program Files (x86)\\Steam\\steamapps\\common\\SteamVR\\drivers\\cvdriver"
     ]
   }

Method 2: Using vrpathreg (if available)

"C:\Program Files (x86)\Steam\steamapps\common\SteamVR\bin\win64\vrpathreg.exe" adddriver "C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver"

### Step 5: Create default.vrsettings

Create the file:
C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver\resources\settings\default.vrsettings

Contents:

{
   "driver_cvdriver": {
      "enable": true,
      "blocked_by_safe_mode": false
   }
}

### Step 6: Run the simulator

python simple_simulator.py

You should see:

Starting simple controller simulator on 127.0.0.1:5555
Simulating 2 controllers with rotating motion and button presses
Packet 0: Controllers active, time: 0.0s
Packet 2: Controllers active, time: 0.0s

### Step 7: Launch SteamVR

1. Start SteamVR
2. Open SteamVR Status (tray icon)
3. Click ☰ → Devices → Manage Vive Controllers
4. You should see 2 controllers — CV_Controller_Left and CV_Controller_Right

## Log checking

If the controllers do not appear, check the logs:

C:\Program Files (x86)\Steam\logs\vrserver.txt

Look for lines like:

[CVDriver] === CVDriver v2.1 INIT START ===
[CVDriver] Controllers registered successfully
[CVDriver] Network client started on port 5555
[CVDriver] Packet 1000 from controller 0 - Quat(...)

## Troubleshooting

### Problem: "Driver not loaded"

Solution:
1. Ensure driver.vrdrivermanifest is inside resources/
2. Check openvrpaths.vrpath — the path must be correct
3. Restart SteamVR

### Problem: Controllers are gray/inactive

Solution:
1. Make sure the simulator is running and sending data
2. Check that port 5555 is not blocked by the firewall
3. Check logs — there should be messages about receiving packets

### Problem: Controllers do not move

Solution:
1. Code must be updated — ensure RunFrame() exists
2. Logs should show messages every 1000 packets
3. Try restarting SteamVR

### Problem: Firewall blocks port 5555

Solution:

New-NetFirewallRule -DisplayName "CVDriver UDP 5555" -Direction Inbound -Protocol UDP -LocalPort 5555 -Action Allow

## Driver folder structure

After installation, the structure should look like this:

C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver\
├── bin\
│   └── win64\
│       ├── driver_cvdriver.dll
│       └── openvr_api.dll
└── resources\
    ├── driver.vrdrivermanifest
    ├── input\
    │   └── cvcontroller_profile.json
    └── settings\
        └── default.vrsettings

## Next steps

After successful installation:

1. Controllers should appear in SteamVR
2. They should rotate (simulator)
3. Buttons should blink (simulator)
4. Logs should show incoming data

Now you can:
- Connect a real Arduino controller
- Configure calibration
- Add more buttons
- Create your own 3D controller model

## Useful links

OpenVR Driver Documentation:
https://github.com/ValveSoftware/openvr/wiki/Driver-Documentation

Simple OpenVR Driver Tutorial:
https://github.com/terminal29/Simple-OpenVR-Driver-Tutorial

OpenVR API Reference:
https://github.com/ValveSoftware/openvr/wiki/API-Documentation

## Debugging with Visual Studio

To debug the driver in Visual Studio:

1. Install Microsoft Child Process Debugging Power Tool
2. In project properties set:
   Debugging → Command:
   C:\Program Files (x86)\Steam\steamapps\common\SteamVR\bin\win64\vrstartup.exe
   Enable child process debugging: Yes
   Child process to debug: vrserver.exe
3. Now you can set breakpoints inside the driver code!

## Quick reinstall commands

Create reinstall.bat:

(batch file content here)
