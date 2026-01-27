# GyroMouse Virtual HID Device - Инструкция установки

## Что изменилось

Вместо фильтра реальной мыши, теперь создаётся **виртуальное HID-устройство**, которое полностью независимо от реальной мыши.

## Сборка

1. Откройте `GyroMouse.sln` в Visual Studio 2022
2. Build → Build Solution (Ctrl+Shift+B)
3. Результат: `gyromouse.sys` в папке `x64\Release\`

## Установка

### Шаг 1: Включите режим тестирования

```cmd
bcdedit /set testsigning on
```

Перезагрузитесь.

### Шаг 2: Создайте папку для драйвера

```cmd
mkdir C:\GyroMouseDriver
```

### Шаг 3: Скопируйте файлы

Скопируйте в `C:\GyroMouseDriver\`:
- `gyromouse.sys` (из папки сборки)
- `GyroMouse.inf` (из папки проекта)

### Шаг 4: Установите драйвер

Откройте Command Prompt **как Administrator** и выполните:

```cmd
cd C:\GyroMouseDriver
pnputil /add-driver GyroMouse.inf /install
```

Или через Device Manager:
1. Откройте Device Manager (devmgmt.msc)
2. Action → Add legacy hardware
3. Выберите "Install the hardware that I manually select from a list"
4. Выберите "Human Interface Devices"
5. Нажмите "Have Disk"
6. Укажите путь `C:\GyroMouseDriver\`
7. Выберите "GyroMouse Virtual HID Device"
8. Нажмите "Next" и "Finish"

### Шаг 5: Проверьте установку

1. Откройте Device Manager (devmgmt.msc)
2. Найдите "GyroMouse Virtual HID Device" в разделе "Human Interface Devices"
3. Если нет ошибок - всё ОК

## Тестирование

### Компилируйте тестовую программу

```cmd
cd control-mouse
cl /W3 test_mouse.cpp /link setupapi.lib hid.lib
```

### Отправьте данные мыши

```cmd
REM Движение вправо на 10 пикселей, левая кнопка нажата
test_mouse.exe 10 0 1

REM Движение влево на 5 пикселей, правая кнопка нажата
test_mouse.exe -5 0 2

REM Движение вверх на 20 пикселей, обе кнопки нажаты
test_mouse.exe 0 -20 3
```

## Удаление

```cmd
pnputil /delete-driver GyroMouse.inf /uninstall
```

Или через Device Manager:
1. Найдите "GyroMouse Virtual HID Device"
2. Правой кнопкой → Uninstall device
3. Отметьте "Delete the driver software for this device"
4. Нажмите "Uninstall"

## Отключение режима тестирования

```cmd
bcdedit /set testsigning off
```

Перезагрузитесь.

## Решение проблем

### Проблема: "Device not found"

1. Проверьте, что драйвер установлен в Device Manager
2. Перезагрузитесь
3. Попробуйте переустановить драйвер

### Проблема: "WriteFile failed"

1. Убедитесь, что устройство видно в Device Manager
2. Проверьте права доступа (запустите как Administrator)
3. Проверьте логи в DebugView

### Проблема: "Driver signature verification failed"

1. Убедитесь, что включен режим тестирования: `bcdedit /query testsigning`
2. Если выключен, включите: `bcdedit /set testsigning on`
3. Перезагрузитесь

## Архитектура

```
GyroMouse Virtual HID Device
├── driver.c - основной драйвер
├── driver.h - заголовки
├── GyroMouse.inf - конфигурация
└── test_mouse.cpp - тестовая программа
```

## Следующие шаги

1. Расширьте `test_mouse.cpp` для отправки данных с гироскопа
2. Добавьте поддержку кнопок и триггеров
3. Интегрируйте с вашей системой отслеживания (Arduino/мобильный телефон)
