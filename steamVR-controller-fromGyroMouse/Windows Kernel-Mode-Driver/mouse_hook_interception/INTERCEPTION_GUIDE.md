# Gyro Mouse Blocker - Interception Edition

Блокировка конкретной гиро-мыши от Windows с отправкой данных по UDP для VR контроллера.

## 🚀 Быстрый старт (5 минут)

```bash
# 1. Включить тестовый режим (CMD от администратора)
bcdedit /set testsigning on
# Перезагрузка!

# 2. Установить драйвер Interception
cd Interception/command\ line\ installer
install-interception.exe /install
# Перезагрузка!

# 3. Собрать программу
mkdir build && cd build
cmake .. -G "MinGW Makefiles"
cmake --build .

# 4. Запустить от администратора
./mouse_hook.exe
```

---

Полное руководство по установке и использованию.

---

## Оглавление

1. [Установка драйвера Interception](#1-установка-драйвера-interception)
2. [Компиляция программы](#2-компиляция-программы)
3. [Первый запуск](#3-первый-запуск)
4. [Диагностика проблем](#4-диагностика-проблем)
5. [Дальнейшие шаги](#5-дальнейшие-шаги)

---

## 1. Установка драйвера Interception

### Шаг 1.1: Включить тестовый режим

```cmd
# Открыть CMD от имени администратора
bcdedit /set testsigning on
```

**Перезагрузите компьютер!**

### Шаг 1.2: Установить драйвер

```cmd
cd "D:\MyDocuments\Programming\Projects_C\VR-Driver\steamVR-controller-fromGyroMouse\Windows Kernel-Mode-Driver\mouse_hook_interception\Interception\command line installer"

install-interception.exe /install
```

Вы увидите:
```
Installing Interception...
Driver installed successfully.
Please restart your computer.
```

**Перезагрузите компьютер!**

### Шаг 1.3: Проверка установки

После перезагрузки проверьте:

```cmd
sc query interception
```

Должно быть:
```
STATE              : 4  RUNNING
```

---

## 2. Компиляция программы

### Шаг 2.1: Требования

- ✅ CMake (установлен)
- ✅ MinGW-w64 (у вас уже есть через MINGW64)
- ✅ Interception library (уже скачана)

### Шаг 2.2: Собрать проект

```bash
cd /d/MyDocuments/Programming/Projects_C/VR-Driver/steamVR-controller-fromGyroMouse/Windows\ Kernel-Mode-Driver/mouse_hook_interception

# Создать папку build
mkdir build
cd build

# Сгенерировать проект (MinGW)
cmake .. -G "MinGW Makefiles"

# Собрать
cmake --build .
```

Или с MSVC (если установлен):
```bash
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

### Шаг 2.3: Проверка результата

В папке `build/` должен появиться:
```
build/
├── mouse_hook.exe
└── interception.dll  (скопирована автоматически)
```

---

## 3. Первый запуск

### Шаг 3.1: Запуск от администратора

**ВАЖНО:** Программа ОБЯЗАТЕЛЬНО должна запускаться от администратора!

```bash
# В MINGW64 bash (от администратора)
cd build
./mouse_hook.exe
```

Или в Windows CMD:
```cmd
cd build
mouse_hook.exe
```

### Шаг 3.2: Выбор мыши

При первом запуске вы увидите список всех мышей:

```
========================================
  Gyro Mouse Blocker (Interception)
========================================
UDP Target: 127.0.0.1:5556

Initializing Interception driver...
Interception context created successfully!

Enumerating mouse devices...
Found device 11: \\?\HID#VID_046D&PID_C52B#...
Found device 12: \\?\HID#VID_093A&PID_2510#...
Found device 13: \\?\HID#VID_1234&PID_5678#...

Found 3 mouse device(s)

Available mouse devices:
----------------------------------------
[0] Device 11
    Hardware ID: HID\VID_046D&PID_C52B&REV_0001
    VID=046D PID=C52B

[1] Device 12
    Hardware ID: HID\VID_093A&PID_2510&REV_0100
    VID=093A PID=2510

[2] Device 13
    Hardware ID: HID\VID_1234&PID_5678&REV_0200
    VID=1234 PID=5678

Enter the number of the gyro mouse to BLOCK: _
```

**Введите номер вашей гиро-мыши** (например, `2`)

### Шаг 3.3: Работа программы

После выбора:

```
========================================
Configuration:
----------------------------------------
Target Device: 13
Hardware ID: HID\VID_1234&PID_5678&REV_0200
UDP Destination: 127.0.0.1:5556
========================================

This mouse will be BLOCKED from Windows.
All other mice will work normally.
Press Ctrl+C to exit.

=== Starting event loop ===
Target device: 13
Blocking enabled for gyro mouse
Other mice will work normally

Stats: Blocked=145 Passed=0 (Delta: X=5 Y=-3)
Stats: Blocked=128 Passed=0 (Delta: X=-2 Y=8)
```

**Теперь:**
- ✅ Гиро-мышь **НЕ ДВИГАЕТ** курсор
- ✅ Данные отправляются на `127.0.0.1:5556` по UDP
- ✅ Все другие мыши работают нормально

### Шаг 3.4: Конфигурация сохранена

Файл `mouse_config.txt` создан автоматически:
```
# Interception Device Configuration
# Device ID for the gyro mouse
DEVICE=13
# Hardware ID: HID\VID_1234&PID_5678&REV_0200
```

При следующем запуске программа автоматически найдёт это устройство.

---

## 4. Диагностика проблем

### ❌ Ошибка: "Failed to create Interception context"

**Причина:** Драйвер не установлен или не запущен

**Решение:**
```cmd
# Проверить статус драйвера
sc query interception

# Если не запущен:
sc start interception

# Если не установлен:
install-interception.exe /install
# Перезагрузка!
```

### ❌ Ошибка: "This program must be run as Administrator"

**Решение:**
- Windows CMD: Правой кнопкой → "Запуск от имени администратора"
- MINGW64: Запустить MinGW terminal от администратора

### ❌ Ошибка: "No mouse devices found"

**Причина:** Драйвер не видит мыши

**Решение:**
1. Проверьте, что драйвер запущен: `sc query interception`
2. Перезагрузите компьютер
3. Попробуйте запустить samples из Interception:
   ```cmd
   cd Interception\samples\x86
   identify.exe
   ```
   Должны показаться все устройства при движении мыши

### ❌ Курсор всё равно двигается

**Причина:** Неправильно выбрана мышь

**Решение:**
1. Удалите `mouse_config.txt`
2. Запустите программу снова
3. Внимательно выберите правильную мышь по VID/PID
4. Подвигайте только гиро-мышью и посмотрите на счётчик `Blocked=`

### ❌ Программа не компилируется

**Проверьте:**
```bash
# Версия CMake
cmake --version  # Должна быть >= 3.10

# Компилятор
g++ --version    # MinGW

# Пути в CMakeLists.txt
# Убедитесь что INTERCEPTION_DIR правильный
```

### 🔍 Тестирование UDP

Проверьте, что данные идут на UDP порт:

**Терминал 1:** Запустить mouse_hook.exe

**Терминал 2:** Слушать UDP порт
```bash
# Python
python -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(('127.0.0.1', 5556)); print('Listening on 5556...'); [print(s.recvfrom(1024)[0].decode()) for _ in iter(int, 1)]"
```

Или NetCat:
```bash
nc -ul 5556
```

Подвигайте гиро-мышью, должны появиться сообщения:
```
MOUSE:5,-3,0,1234567890
MOUSE:-2,8,0,1234567891
MOUSE:0,0,1,1234567892
```

Формат: `MOUSE:deltaX,deltaY,buttons,timestamp`

---

## 5. Дальнейшие шаги

### 5.1 Интеграция с VR контроллером

Теперь нужно создать программу, которая:
1. **Слушает UDP порт 5556**
2. **Преобразует данные мыши в позицию/вращение VR контроллера**
3. **Отправляет в SteamVR через OpenVR API**

Структура:
```
mouse_hook.exe (Interception)
    ↓ UDP 5556
steamvr_driver.exe
    ↓ OpenVR API
SteamVR
```

### 5.2 Создать SteamVR драйвер

Следующий шаг - написать SteamVR driver:

**Файлы:**
```
driver_gyromouse/
├── bin/
│   └── win64/
│       └── driver_gyromouse.dll
├── driver.vrdrivermanifest
└── resources/
    └── settings/
        └── default.vrsettings
```

**driver.vrdrivermanifest:**
```json
{
    "alwaysActivate": true,
    "name": "gyromouse",
    "directory": "",
    "resourceOnly": false,
    "hmd_presence": [""]
}
```

**Код драйвера** (C++):
- Слушать UDP 5556
- Преобразовать данные мыши в vr::TrackedDevicePose_t
- Регистрировать контроллер в SteamVR

### 5.3 Калибровка и настройка

Добавить:
- **Чувствительность** (sensitivity multiplier)
- **Dead zone** (игнорировать малые движения)
- **Smoothing** (сглаживание движений)
- **Button mapping** (кнопки мыши → кнопки контроллера)

### 5.4 GUI приложение

Создать простой GUI (Qt/WPF/wxWidgets):
- Выбор мыши
- Настройка параметров
- Визуализация движений
- Кнопки Start/Stop

### 5.5 Автозапуск

Добавить в автозагрузку Windows:
```cmd
# Создать ярлык в:
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```

---

## 6. Архитектура проекта

```
┌─────────────────────────────────────────────────┐
│          Physical Gyro Mouse                    │
└───────────────┬─────────────────────────────────┘
                │ USB HID
┌───────────────▼─────────────────────────────────┐
│     Interception Driver (Kernel Mode)           │
│  - Перехватывает события мыши                   │
│  - Блокирует передачу в Windows                 │
└───────────────┬─────────────────────────────────┘
                │ Interception API
┌───────────────▼─────────────────────────────────┐
│      mouse_hook.exe (User Mode)                 │
│  - Фильтрует события от целевой мыши            │
│  - Преобразует в UDP пакеты                     │
└───────────────┬─────────────────────────────────┘
                │ UDP 127.0.0.1:5556
┌───────────────▼─────────────────────────────────┐
│    steamvr_driver.dll (будущий этап)            │
│  - Получает UDP пакеты                          │
│  - Преобразует в позицию/вращение               │
│  - Отправляет в OpenVR                          │
└───────────────┬─────────────────────────────────┘
                │ OpenVR API
┌───────────────▼─────────────────────────────────┐
│               SteamVR                            │
└─────────────────────────────────────────────────┘
```

---

## 7. Полезные команды

### Управление драйвером
```cmd
# Проверить статус
sc query interception

# Запустить
sc start interception

# Остановить
sc stop interception

# Удалить
install-interception.exe /uninstall
```

### Отключить тестовый режим (после production)
```cmd
bcdedit /set testsigning off
# Перезагрузка
```

### Логирование
Добавить в mouse_hook.cpp:
```cpp
std::ofstream logFile("mouse_log.txt");
logFile << "X=" << mstroke.x << " Y=" << mstroke.y << std::endl;
```

---

## 8. Ресурсы

- [Interception GitHub](https://github.com/oblitum/Interception)
- [OpenVR SDK](https://github.com/ValveSoftware/openvr)
- [SteamVR Driver Documentation](https://github.com/ValveSoftware/openvr/wiki/Driver-Documentation)

---

## 9. Troubleshooting Checklist

Перед тем как задавать вопросы, проверьте:

- ✅ Драйвер Interception установлен: `sc query interception`
- ✅ Тестовый режим включен: `bcdedit | findstr testsigning`
- ✅ Программа запущена от администратора
- ✅ Файл `interception.dll` находится рядом с `mouse_hook.exe`
- ✅ Выбрана правильная мышь (проверить VID/PID)
- ✅ UDP порт 5556 не занят другой программой
- ✅ Перезагрузка после установки драйвера

---

Успехов с проектом! 🚀