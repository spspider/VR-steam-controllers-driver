@echo off
echo ========================================
echo GyroMouse Driver Installation Script
echo ========================================
echo.

REM Check administrator rights
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [ERROR] Administrator rights required!
    echo Run this script as administrator!
    pause
    exit /b 1
)

echo [INFO] Closing SteamVR...
taskkill /F /IM vrserver.exe 2>nul
taskkill /F /IM vrmonitor.exe 2>nul
taskkill /F /IM vrdashboard.exe 2>nul
timeout /t 2 >nul

set STEAMVR_PATH=C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\gyromouse
set PROJECT_PATH=%~dp0

echo [INFO] Checking driver build...
if not exist "%PROJECT_PATH%build\Release\driver_gyromouse.dll" (
    echo [ERROR] Driver not built!
    echo Run first: cd build && cmake .. && cmake --build . --config Release
    pause
    exit /b 1
)

echo [INFO] Creating SteamVR folder...
if exist "%STEAMVR_PATH%" (
    echo [INFO] Removing old version...
    rmdir /S /Q "%STEAMVR_PATH%"
)
mkdir "%STEAMVR_PATH%" 2>nul
mkdir "%STEAMVR_PATH%\bin" 2>nul
mkdir "%STEAMVR_PATH%\bin\win64" 2>nul
mkdir "%STEAMVR_PATH%\resources" 2>nul
mkdir "%STEAMVR_PATH%\resources\input" 2>nul
mkdir "%STEAMVR_PATH%\resources\settings" 2>nul

echo [INFO] Copying driver files...

REM Copy main DLL
copy "%PROJECT_PATH%build\Release\driver_gyromouse.dll" "%STEAMVR_PATH%\bin\win64\" >nul
if %errorLevel% NEQ 0 (
    echo [ERROR] Failed to copy driver DLL!
    pause
    exit /b 1
)

REM Copy OpenVR API DLL
copy "%PROJECT_PATH%openvr\bin\win64\openvr_api.dll" "%STEAMVR_PATH%\bin\win64\" >nul
if %errorLevel% NEQ 0 (
    echo [ERROR] Failed to copy OpenVR API DLL!
    pause
    exit /b 1
)

REM Copy manifest to ROOT (not resources!)
copy "%PROJECT_PATH%resources\driver.vrdrivermanifest" "%STEAMVR_PATH%\" >nul
if %errorLevel% NEQ 0 (
    echo [ERROR] Failed to copy manifest!
    pause
    exit /b 1
)

REM Copy input files (both profile and bindings)
copy "%PROJECT_PATH%resources\input\*.json" "%STEAMVR_PATH%\resources\input\" >nul
if %errorLevel% NEQ 0 (
    echo [ERROR] Failed to copy input files!
    pause
    exit /b 1
)

REM Copy settings
copy "%PROJECT_PATH%resources\settings\*.vrsettings" "%STEAMVR_PATH%\resources\settings\" >nul
if %errorLevel% NEQ 0 (
    echo [ERROR] Failed to copy settings!
    pause
    exit /b 1
)

echo [INFO] Registering driver in OpenVR...
set OPENVR_PATH=%LOCALAPPDATA%\openvr\openvrpaths.vrpath

if not exist "%OPENVR_PATH%" (
    echo [WARNING] openvrpaths.vrpath not found, creating...
    mkdir "%LOCALAPPDATA%\openvr" 2>nul
    echo { "external_drivers": ["%STEAMVR_PATH:\=\\%"] } > "%OPENVR_PATH%"
) else (
    echo [INFO] Update openvrpaths.vrpath manually...
    echo.
    echo IMPORTANT: Add to %OPENVR_PATH%:
    echo.
    echo "external_drivers": [
    echo   "C:\\Program Files (x86)\\Steam\\steamapps\\common\\SteamVR\\drivers\\gyromouse"
    echo ]
    echo.
)

echo.
echo ========================================
echo [SUCCESS] Installation completed!
echo ========================================
echo.
echo Files installed to:
echo %STEAMVR_PATH%
echo.
echo Next steps:
echo 1. Check openvrpaths.vrpath manually
echo 2. Run: python simple_gyromouse_simulator.py
echo 3. Start SteamVR
echo.
pause