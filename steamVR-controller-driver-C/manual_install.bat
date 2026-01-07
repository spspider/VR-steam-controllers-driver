
@echo off
echo ========================================
echo CVDriver Manual Installation Script
echo ========================================
echo.

REM Checking administrator rights
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [ERROR] Administrator rights required!
    echo Run this script as Administrator!
    pause
    exit /b 1
)

echo [INFO] Closing SteamVR...
taskkill /F /IM vrserver.exe 2>nul
taskkill /F /IM vrmonitor.exe 2>nul
taskkill /F /IM vrdashboard.exe 2>nul
timeout /t 2 >nul

set STEAMVR_PATH=C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver
set PROJECT_PATH=%~dp0

echo [INFO] Creating folder structure...
mkdir "%STEAMVR_PATH%\bin\win64" 2>nul
mkdir "%STEAMVR_PATH%\resources\input" 2>nul

echo [INFO] Copying driver DLL...
copy /Y "%PROJECT_PATH%build\Release\driver_cvdriver.dll" "%STEAMVR_PATH%\bin\win64\"
if %errorLevel% NEQ 0 (
    echo [ERROR] Failed to copy driver_cvdriver.dll
    pause
    exit /b 1
)

echo [INFO] Copying OpenVR API DLL...
copy /Y "%PROJECT_PATH%openvr\bin\win64\openvr_api.dll" "%STEAMVR_PATH%\bin\win64\"
if %errorLevel% NEQ 0 (
    echo [ERROR] Failed to copy openvr_api.dll
    pause
    exit /b 1
)

echo [INFO] Copying driver manifest...
copy /Y "%PROJECT_PATH%resources\driver.vrdrivermanifest" "%STEAMVR_PATH%\resources\"
if %errorLevel% NEQ 0 (
    echo [ERROR] Failed to copy driver.vrdrivermanifest
    pause
    exit /b 1
)

echo [INFO] Copying input profile...
copy /Y "%PROJECT_PATH%resources\input\cvcontroller_profile.json" "%STEAMVR_PATH%\resources\input\"
if %errorLevel% NEQ 0 (
    echo [ERROR] Failed to copy cvcontroller_profile.json
    pause
    exit /b 1
)

echo.
echo ========================================
echo [SUCCESS] Installation completed!
echo ========================================
echo.
echo Files installed in:
echo %STEAMVR_PATH%
echo.
echo Now you can run:
echo 1. simple_simulator.py
echo 2. SteamVR
echo.
pause
``
