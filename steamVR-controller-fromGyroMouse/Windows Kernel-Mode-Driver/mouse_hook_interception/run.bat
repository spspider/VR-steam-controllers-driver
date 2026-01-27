@echo off
echo ========================================
echo   Gyro Mouse Blocker - Quick Start
echo ========================================
echo.

REM Проверка прав администратора
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Running as Administrator
) else (
    echo [ERROR] This script must be run as Administrator!
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

REM Проверка драйвера Interception
echo.
echo Checking Interception driver...
sc query interception | find "RUNNING" >nul
if %errorLevel% == 0 (
    echo [OK] Interception driver is running
) else (
    echo [WARNING] Interception driver is not running!
    echo.
    echo Installing driver...
    cd Interception\command line installer
    install-interception.exe /install
    cd ..\..
    echo.
    echo Please restart your computer and run this script again.
    pause
    exit /b 1
)

REM Проверка сборки
echo.
if exist "build\mouse_hook.exe" (
    echo [OK] Program already built
) else (
    echo [INFO] Building program...
    if not exist "build" mkdir build
    cd build
    cmake .. -G "MinGW Makefiles"
    cmake --build .
    cd ..
)

REM Запуск программы
echo.
echo ========================================
echo Starting mouse_hook.exe...
echo ========================================
echo.
cd build
mouse_hook.exe
cd ..

echo.
echo Program exited.
pause