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

### Шаг 2: Установите драйвер вручную

1. Сохраните `manual_install.bat` в корень проекта
2. **Запустите от имени администратора** (правой кнопкой → "Запуск от имени администратора")
3. Скрипт автоматически скопирует все файлы

### Шаг 3: Проверьте установку

1. Запустите `check_installation.bat`
2. Убедитесь что все 4 файла на месте:
   - ✅ `driver_cvdriver.dll`
   - ✅ `openvr_api.dll`
   - ✅ `driver.vrdrivermanifest`
   - ✅ `cvcontroller_profile.json`

### Шаг 4: Зарегистрируйте драйвер в SteamVR

**Метод 1: Через openvrpaths.vrpath (РЕКОМЕНДУЕТСЯ)**

1. Откройте файл:
   ```
   C:\Users\<ВашеИмя>\AppData\Local\openvr\openvrpaths.vrpath
   ```

2. Добавьте путь к драйверу в секцию `external_drivers`:
   ```json
   {
     "external_drivers": [
       "C:\\Program Files (x86)\\Steam\\steamapps\\common\\SteamVR\\drivers\\cvdriver"
     ]
   }
   ```

**Метод 2: Через vrpathreg (если есть)**

```bash
"C:\Program Files (x86)\Steam\steamapps\common\SteamVR\bin\win64\vrpathreg.exe" adddriver "C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver"
```

### Шаг 5: Создайте default.vrsettings

Создайте файл:
```
C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver\resources\settings\default.vrsettings
```

Содержимое:
```json
{
   "driver_cvdriver": {
      "enable": true,
      "blocked_by_safe_mode": false
   }
}
```

### Шаг 6: Запустите симулятор

```bash
python simple_simulator.py
```

Вы должны увидеть:
```
Starting simple controller simulator on 127.0.0.1:5555
Simulating 2 controllers with rotating motion and button presses
Packet 0: Controllers active, time: 0.0s
Packet 2: Controllers active, time: 0.0s
```

### Шаг 7: Запустите SteamVR

1. Запустите SteamVR
2. Откройте **SteamVR Status** (значок в трее)
3. Нажмите на **☰** → **Devices** → **Manage Vive Controllers**
4. Вы должны увидеть **2 контроллера** - CV_Controller_Left и CV_Controller_Right

## Проверка логов

Если контроллеры не появились, проверьте логи:

```
C:\Program Files (x86)\Steam\logs\vrserver.txt
```

Ищите строки:
```
[CVDriver] === CVDriver v2.1 INIT START ===
[CVDriver] Controllers registered successfully
[CVDriver] Network client started on port 5555
[CVDriver] Packet 1000 from controller 0 - Quat(...)
```

## Отладка проблем

### Проблема: "Driver not loaded"

**Решение:**
1. Проверьте что `driver.vrdrivermanifest` находится в `resources/`
2. Проверьте `openvrpaths.vrpath` - путь должен быть правильным
3. Перезапустите SteamVR

### Проблема: Контроллеры серые/неактивные

**Решение:**
1. Убедитесь что симулятор запущен и отправляет данные
2. Проверьте что порт 5555 не заблокирован фаерволом
3. Посмотрите логи - должны быть сообщения о получении пакетов

### Проблема: Контроллеры не двигаются

**Решение:**
1. Код должен быть обновлен - проверьте что есть метод `RunFrame()`
2. В логах должны быть сообщения каждые 1000 пакетов
3. Попробуйте перезапустить SteamVR

### Проблема: Firewall блокирует порт 5555

**Решение:**
```powershell
# Запустите PowerShell от имени администратора
New-NetFirewallRule -DisplayName "CVDriver UDP 5555" -Direction Inbound -Protocol UDP -LocalPort 5555 -Action Allow
```

## Структура папки драйвера

После установки структура должна быть такой:

```
C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\cvdriver\
├── bin\
│   └── win64\
│       ├── driver_cvdriver.dll         ← Ваш драйвер
│       └── openvr_api.dll              ← OpenVR API
└── resources\
    ├── driver.vrdrivermanifest         ← Манифест драйвера
    ├── input\
    │   └── cvcontroller_profile.json   ← Профиль ввода
    └── settings\
        └── default.vrsettings          ← Настройки (опционально)
```

## Следующие шаги

После успешной установки:

1. ✅ Контроллеры должны появиться в SteamVR
2. ✅ Они должны вращаться (симулятор)
3. ✅ Кнопки должны мигать (симулятор)
4. ✅ В логах должны быть сообщения о получении данных

Теперь можно:
- Подключить реальный Arduino контроллер
- Настроить калибровку
- Добавить больше кнопок
- Создать свою 3D модель контроллера

## Полезные ссылки

- [OpenVR Driver Documentation](https://github.com/ValveSoftware/openvr/wiki/Driver-Documentation)
- [Simple OpenVR Driver Tutorial](https://github.com/terminal29/Simple-OpenVR-Driver-Tutorial)
- [OpenVR API Reference](https://github.com/ValveSoftware/openvr/wiki/API-Documentation)

## Отладка с Visual Studio

Для отладки драйвера в Visual Studio:

1. Установите **Microsoft Child Process Debugging Power Tool**
2. В свойствах проекта установите:
   - **Debugging → Command**: `C:\Program Files (x86)\Steam\steamapps\common\SteamVR\bin\win64\vrstartup.exe`
   - **Enable child process debugging**: Yes
   - **Child process to debug**: `vrserver.exe`
3. Теперь можно ставить точки останова в коде драйвера!

## Команды для быстрой переустановки

Создайте `reinstall.bat`:

```batch
@echo off
taskkill /F /IM vrserver.exe 2>nul
timeout /t 2 >nul
cd build
cmake --build . --config Release
cd ..
manual_install.bat
```

Это автоматизирует: остановку SteamVR → пересборку → установку.

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