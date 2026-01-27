poweshell

cmd /k "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"


# Виртуальное HID-устройство мыши - Правильная реализация

## Основные особенности

### 1. Тип драйвера
- **Не фильтр** - создаёт новое устройство
- **PDO (Physical Device Object)** - виртуальное устройство
- **KMDF** - Windows Driver Framework

### 2. Структура проекта

```
VSVirtualDeviceDriver/
├── vhid_mouse.c          # Основная реализация
├── vhid_mouse.h          # Заголовки
├── GyroMouse.inf         # Конфигурация
├── VSVirtualDeviceDriver.vcxproj
└── VSVirtualDeviceDriver.sln
```

### 3. Ключевые компоненты

#### DriverEntry
- Инициализирует WDF драйвер
- Регистрирует callback для добавления устройств

#### EvtDeviceAdd
- Вызывается при подключении устройства
- Создаёт PDO (виртуальное устройство)

#### HID Report Descriptor
- Определяет структуру данных мыши
- Включает: кнопки (3 бита), X (8 бит), Y (8 бит)

### 4. Важные моменты

#### Инициализация устройства
```c
WdfPdoInitAllocate(WdfDriverWdmGetDriverObject(Driver));
WdfDeviceCreate(&deviceInit, &deviceAttributes, &device);
```

#### HID Descriptor
```c
HidDescriptor->bLength = sizeof(HID_DESCRIPTOR);
HidDescriptor->bDescriptorType = HID_HID_DESCRIPTOR_TYPE;
HidDescriptor->bcdHID = HID_REVISION;
HidDescriptor->bNumDescriptors = 1;
```

#### Report Descriptor (HID)
- 0x05, 0x01 = Usage Page (Generic Desktop)
- 0x09, 0x02 = Usage (Mouse)
- 0xA1, 0x01 = Collection (Application)
- Кнопки: 3 бита (левая, правая, средняя)
- X, Y: по 8 бит (относительное движение)

### 5. Компиляция

1. Откройте `VSVirtualDeviceDriver.sln` в Visual Studio 2022
2. Выберите: **Release** конфигурацию и **x64** платформу
3. Нажмите: **Build** → **Build Solution** (Ctrl+Shift+B)
4. Результат: `VSVirtualDeviceDriver.sys` в папке `x64\Release\`

### 6. Установка

```cmd
REM Включить режим тестирования
bcdedit /set testsigning on

REM Перезагрузиться

REM Установить драйвер
pnputil /add-driver GyroMouse.inf /install
```

### 7. Проверка

```cmd
REM Открыть Device Manager
devmgmt.msc

REM Найти "GyroMouse Virtual HID Device" в разделе "Human Interface Devices"
```

## Ссылки на примеры

- **Microsoft HID Minidriver Sample**: https://github.com/microsoft/Windows-driver-samples/tree/main/hid
- **KMDF Mouse Driver**: https://github.com/microsoft/Windows-driver-samples/tree/main/input/moufiltr
- **Virtual HID Device**: https://github.com/nefarius/ViGEmBus

## Следующие шаги

1. Добавить функции для отправки данных мыши
2. Создать user-mode приложение для управления
3. Интегрировать с системой отслеживания (Arduino/мобильный телефон)
4. Добавить поддержку кнопок и триггеров

## Отладка

Используйте DebugView для просмотра логов:
```
KdPrint(("VhidMouse: Message\n"));
```

Скачайте DebugView: https://learn.microsoft.com/en-us/sysinternals/downloads/debugview
