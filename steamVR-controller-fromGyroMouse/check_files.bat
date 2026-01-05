@echo off
echo ========================================
echo GyroMouse Driver Installation Check
echo ========================================
echo.

set PROJECT_PATH=%~dp0

echo [INFO] Checking build files...
if not exist "%PROJECT_PATH%build\Release\driver_gyromouse.dll" (
    echo [ERROR] Driver DLL not found!
    echo Path: %PROJECT_PATH%build\Release\driver_gyromouse.dll
    pause
    exit /b 1
) else (
    echo [OK] Driver DLL found
)

if not exist "%PROJECT_PATH%openvr\bin\win64\openvr_api.dll" (
    echo [ERROR] OpenVR API DLL not found!
    pause
    exit /b 1
) else (
    echo [OK] OpenVR API DLL found
)

if not exist "%PROJECT_PATH%resources\driver.vrdrivermanifest" (
    echo [ERROR] Driver manifest not found!
    pause
    exit /b 1
) else (
    echo [OK] Driver manifest found
)

if not exist "%PROJECT_PATH%resources\input\gyromouse_profile.json" (
    echo [ERROR] Input profile not found!
    pause
    exit /b 1
) else (
    echo [OK] Input profile found
)

if not exist "%PROJECT_PATH%resources\input\gyromouse_bindings.json" (
    echo [ERROR] Input bindings not found!
    pause
    exit /b 1
) else (
    echo [OK] Input bindings found
)

if not exist "%PROJECT_PATH%resources\settings\default.vrsettings" (
    echo [ERROR] Settings file not found!
    pause
    exit /b 1
) else (
    echo [OK] Settings file found
)

echo.
echo [SUCCESS] All files ready for installation!
echo.
echo Next step: Run install_gyromouse.bat as Administrator
echo.
pause