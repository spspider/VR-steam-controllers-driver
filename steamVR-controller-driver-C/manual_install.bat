@echo off
echo ========================================
echo CVDriver Manual Installation Script
echo ========================================
echo.

REM Проверяем права администратора
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [ERROR] Нужны права администратора!
    echo Запустите этот скрипт от имени администратора!
    pause
    exit /b 1
)

echo [INFO] Закрываем SteamVR...
taskkill /F /IM vrserver.exe 2>nul
taskkill /F /IM vrmonitor.exe 2>nul
taskkill /F /IM vrdashboard.exe 2>nul
timeout /t 2 >nul

set STEAMVR_PATH=C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver
set PROJECT_PATH=%~dp0

echo [INFO] Создаём структуру папок...
mkdir "%STEAMVR_PATH%\bin\win64" 2>nul
mkdir "%STEAMVR_PATH%\resources\input" 2>nul

echo [INFO] Копируем driver DLL...
copy /Y "%PROJECT_PATH%build\Release\driver_cvdriver.dll" "%STEAMVR_PATH%\bin\win64\"
if %errorLevel% NEQ 0 (
    echo [ERROR] Не удалось скопировать driver_cvdriver.dll
    pause
    exit /b 1
)

echo [INFO] Копируем OpenVR API DLL...
copy /Y "%PROJECT_PATH%openvr\bin\win64\openvr_api.dll" "%STEAMVR_PATH%\bin\win64\"
if %errorLevel% NEQ 0 (
    echo [ERROR] Не удалось скопировать openvr_api.dll
    pause
    exit /b 1
)

echo [INFO] Копируем driver manifest...
copy /Y "%PROJECT_PATH%resources\driver.vrdrivermanifest" "%STEAMVR_PATH%\resources\"
if %errorLevel% NEQ 0 (
    echo [ERROR] Не удалось скопировать driver.vrdrivermanifest
    pause
    exit /b 1
)

echo [INFO] Копируем input profile...
copy /Y "%PROJECT_PATH%resources\input\cvcontroller_profile.json" "%STEAMVR_PATH%\resources\input\"
if %errorLevel% NEQ 0 (
    echo [ERROR] Не удалось скопировать cvcontroller_profile.json
    pause
    exit /b 1
)

echo.
echo ========================================
echo [SUCCESS] Установка завершена!
echo ========================================
echo.
echo Файлы установлены в:
echo %STEAMVR_PATH%
echo.
echo Теперь можно запустить:
echo 1. simple_simulator.py
echo 2. SteamVR
echo.
pause