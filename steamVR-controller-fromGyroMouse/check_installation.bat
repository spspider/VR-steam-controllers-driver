@echo off
setlocal enabledelayedexpansion

echo ========================================
echo GyroMouse Driver Installation Check
echo ========================================
echo.

set STEAMVR_PATH=C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\gyromouse
set OPENVR_PATH=%LOCALAPPDATA%\openvr\openvrpaths.vrpath
set ALL_OK=1

REM ============================================
REM 1. Проверка файлов драйвера
REM ============================================
echo [1/6] Проверка файлов драйвера...
echo.

echo   [1.1] driver_gyromouse.dll...
if exist "%STEAMVR_PATH%\bin\win64\driver_gyromouse.dll" (
    echo   [OK] Найден
) else (
    echo   [FAIL] НЕ НАЙДЕН!
    set ALL_OK=0
)

echo   [1.2] openvr_api.dll...
if exist "%STEAMVR_PATH%\bin\win64\openvr_api.dll" (
    echo   [OK] Найден
) else (
    echo   [FAIL] НЕ НАЙДЕН!
    set ALL_OK=0
)

echo   [1.3] driver.vrdrivermanifest...
if exist "%STEAMVR_PATH%\driver.vrdrivermanifest" (
    echo   [OK] Найден
) else (
    echo   [FAIL] НЕ НАЙДЕН!
    set ALL_OK=0
)

echo   [1.4] gyromouse_profile.json...
if exist "%STEAMVR_PATH%\resources\input\gyromouse_profile.json" (
    echo   [OK] Найден
) else (
    echo   [FAIL] НЕ НАЙДЕН!
    set ALL_OK=0
)

echo   [1.5] default.vrsettings...
if exist "%STEAMVR_PATH%\resources\settings\default.vrsettings" (
    echo   [OK] Найден
) else (
    echo   [WARNING] НЕ НАЙДЕН (опционально)
)

echo.

REM ============================================
REM 2. Проверка регистрации в OpenVR
REM ============================================
echo [2/6] Проверка регистрации в OpenVR...
echo.

if exist "%OPENVR_PATH%" (
    echo   [OK] openvrpaths.vrpath найден
    findstr /C:"gyromouse" "%OPENVR_PATH%" >nul
    if !errorlevel! EQU 0 (
        echo   [OK] gyromouse зарегистрирован в OpenVR
    ) else (
        echo   [FAIL] gyromouse НЕ зарегистрирован в OpenVR!
        echo   [FIX] Добавьте в %OPENVR_PATH%:
        echo         "C:\\Program Files (x86)\\Steam\\steamapps\\common\\SteamVR\\drivers\\gyromouse"
        set ALL_OK=0
    )
) else (
    echo   [FAIL] openvrpaths.vrpath НЕ НАЙДЕН!
    set ALL_OK=0
)

echo.

REM ============================================
REM 3. Проверка процессов SteamVR
REM ============================================
echo [3/6] Проверка процессов SteamVR...
echo.

tasklist /FI "IMAGENAME eq vrserver.exe" 2>NUL | find /I /N "vrserver.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo   [WARNING] SteamVR запущен
    echo   [INFO] Для обновления драйвера нужно закрыть SteamVR
) else (
    echo   [OK] SteamVR не запущен
)

echo.

REM ============================================
REM 4. Проверка Python зависимостей
REM ============================================
echo [4/6] Проверка Python зависимостей...
echo.

python --version >nul 2>&1
if %errorlevel% EQU 0 (
    echo   [OK] Python установлен
    
    REM Проверяем библиотеки
    python -c "import cv2" >nul 2>&1
    if !errorlevel! EQU 0 (
        echo   [OK] opencv-python установлен
    ) else (
        echo   [WARNING] opencv-python НЕ установлен
        echo   [FIX] pip install opencv-python opencv-contrib-python
    )
    
    python -c "import numpy" >nul 2>&1
    if !errorlevel! EQU 0 (
        echo   [OK] numpy установлен
    ) else (
        echo   [WARNING] numpy НЕ установлен
        echo   [FIX] pip install numpy
    )
) else (
    echo   [WARNING] Python не найден
    echo   [INFO] Python нужен для tracker скриптов
)

echo.

REM ============================================
REM 5. Проверка портов
REM ============================================
echo [5/6] Проверка портов...
echo.

netstat -an | findstr ":5555" >nul
if %errorlevel% EQU 0 (
    echo   [WARNING] Порт 5555 уже используется
    echo   [INFO] Убедитесь что это ваш tracker скрипт
) else (
    echo   [OK] Порт 5555 свободен
)

echo.

REM ============================================
REM 6. Размер файлов
REM ============================================
echo [6/6] Информация о файлах...
echo.

if exist "%STEAMVR_PATH%\bin\win64\driver_gyromouse.dll" (
    for %%A in ("%STEAMVR_PATH%\bin\win64\