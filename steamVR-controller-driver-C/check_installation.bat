@echo off
echo ========================================
echo CVDriver Installation Check
echo ========================================
echo.

set STEAMVR_PATH=C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver

echo Проверяем наличие файлов...
echo.

set ALL_OK=1

echo [1/4] Проверка driver DLL...
if exist "%STEAMVR_PATH%\bin\win64\driver_cvdriver.dll" (
    echo [OK] driver_cvdriver.dll найден
) else (
    echo [FAIL] driver_cvdriver.dll НЕ НАЙДЕН!
    set ALL_OK=0
)

echo [2/4] Проверка OpenVR API DLL...
if exist "%STEAMVR_PATH%\bin\win64\openvr_api.dll" (
    echo [OK] openvr_api.dll найден
) else (
    echo [FAIL] openvr_api.dll НЕ НАЙДЕН!
    set ALL_OK=0
)

echo [3/4] Проверка driver manifest...
if exist "%STEAMVR_PATH%\resources\driver.vrdrivermanifest" (
    echo [OK] driver.vrdrivermanifest найден
) else (
    echo [FAIL] driver.vrdrivermanifest НЕ НАЙДЕН!
    set ALL_OK=0
)

echo [4/4] Проверка input profile...
if exist "%STEAMVR_PATH%\resources\input\cvcontroller_profile.json" (
    echo [OK] cvcontroller_profile.json найден
) else (
    echo [FAIL] cvcontroller_profile.json НЕ НАЙДЕН!
    set ALL_OK=0
)

echo.
echo ========================================
if %ALL_OK%==1 (
    echo [SUCCESS] Все файлы на месте!
    echo Драйвер готов к использованию.
) else (
    echo [FAIL] Некоторые файлы отсутствуют!
    echo Запустите manual_install.bat от имени администратора.
)
echo ========================================
echo.

echo Содержимое папки драйвера:
echo.
dir /S "%STEAMVR_PATH%"

echo.
pause