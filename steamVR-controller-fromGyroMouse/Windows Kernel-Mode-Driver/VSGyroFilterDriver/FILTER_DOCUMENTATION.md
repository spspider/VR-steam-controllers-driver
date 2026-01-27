# GyroMouseFilter - Обновленный драйвер с фильтрацией позиции

## Обзор изменений

Драйвер был обновлен для добавления функциональности фильтрации позиции мыши. Теперь драйвер может:

1. **Фильтровать шум** - Игнорировать малые движения мыши (меньше порога)
2. **Сглаживать движение** - Применять экспоненциальное сглаживание к данным мыши
3. **Блокировать ввод** - Полностью блокировать движение мыши при необходимости
4. **Управлять параметрами** - Изменять параметры фильтрации через IOCTL команды

## Новые IOCTL команды

### IOCTL_GYRO_SET_BLOCK (0x800)
Полностью блокирует движение мыши.

**Параметры:**
- Input: BOOLEAN (TRUE = блокировать, FALSE = разблокировать)

**Пример:**
```c
BOOLEAN blockFlag = TRUE;
DeviceIoControl(hDevice, IOCTL_GYRO_SET_BLOCK, &blockFlag, sizeof(BOOLEAN), NULL, 0, &bytesReturned, NULL);
```

### IOCTL_GYRO_SET_FILTER (0x801)
Включает/отключает фильтрацию позиции.

**Параметры:**
- Input: BOOLEAN (TRUE = включить фильтрацию, FALSE = отключить)

**Пример:**
```c
BOOLEAN filterFlag = TRUE;
DeviceIoControl(hDevice, IOCTL_GYRO_SET_FILTER, &filterFlag, sizeof(BOOLEAN), NULL, 0, &bytesReturned, NULL);
```

### IOCTL_GYRO_SET_THRESHOLD (0x802)
Устанавливает порог фильтрации (минимальное движение для обработки).

**Параметры:**
- Input: ULONG (пороговое значение в пикселях, по умолчанию 5)

**Пример:**
```c
ULONG threshold = 10;
DeviceIoControl(hDevice, IOCTL_GYRO_SET_THRESHOLD, &threshold, sizeof(ULONG), NULL, 0, &bytesReturned, NULL);
```

### IOCTL_GYRO_GET_INFO (0x803)
Получает информацию об устройстве (VendorId, ProductId).

**Параметры:**
- Output: USHORT[2] (VendorId, ProductId)

**Пример:**
```c
USHORT info[2];
DeviceIoControl(hDevice, IOCTL_GYRO_GET_INFO, NULL, 0, info, sizeof(info), &bytesReturned, NULL);
```

## Алгоритм фильтрации

### 1. Фильтрация шума
Если абсолютное значение движения по X или Y меньше порога (по умолчанию 5 пикселей), движение игнорируется:

```
if (|deltaX| < threshold && |deltaY| < threshold) {
    deltaX = 0
    deltaY = 0
}
```

### 2. Сглаживание
Для движений больше порога применяется экспоненциальное сглаживание:

```
newX = (deltaX * 3 + lastX) / 4
newY = (deltaY * 3 + lastY) / 4
```

Это дает вес 75% новому значению и 25% предыдущему, обеспечивая плавное движение.

## Структура DEVICE_CONTEXT

```c
typedef struct _DEVICE_CONTEXT {
    WDFQUEUE DefaultQueue;          // Очередь для обработки запросов
    WDFIOTARGET IoTarget;           // Target для пересылки запросов
    BOOLEAN BlockInput;             // Флаг полной блокировки
    BOOLEAN FilterEnabled;          // Флаг включения фильтрации
    USHORT VendorId;                // ID производителя устройства
    USHORT ProductId;               // ID продукта устройства
    LONG LastX;                     // Последнее значение X для сглаживания
    LONG LastY;                     // Последнее значение Y для сглаживания
    ULONG FilterThreshold;          // Порог фильтрации (пиксели)
    PVOID VhfHandle;                // Handle для Virtual HID Framework
} DEVICE_CONTEXT;
```

## Поток обработки запроса

1. **Получение запроса** - Драйвер получает IOCTL запрос от user-mode приложения
2. **Обработка команды** - Проверяется тип IOCTL и выполняется соответствующее действие
3. **Пересылка вниз** - Запрос пересылается следующему драйверу в стеке
4. **Completion Routine** - При получении ответа вызывается completion routine
5. **Фильтрация данных** - Если включена фильтрация, применяются алгоритмы фильтрации
6. **Возврат результата** - Отфильтрованные данные возвращаются user-mode приложению

## Компиляция

Проект использует Windows Driver Kit (WDK) 10.0.19041.0 и требует:

- Visual Studio 2022 Professional
- Windows Driver Kit (WDK) 10.0.19041.0
- KMDF (Kernel-Mode Driver Framework)
- VHF (Virtual HID Framework) библиотека vhfkm.lib

### Команда компиляции

```cmd
cd /d "d:\MyDocuments\Programming\Projects_C\VR-Driver\steamVR-controller-fromGyroMouse\Windows Kernel-Mode-Driver\VSGyroFilterDriver\GyroFilterDriver"
"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"
msbuild GyroFilterDriver.sln /p:Configuration=Release /p:Platform=x64 /v:minimal
```

## Выходные файлы

После успешной компиляции файлы находятся в:
- **Драйвер**: `x64\Release\GyroFilterDriver.sys`
- **Каталог**: `x64\Release\GyroFilterDriver\gyrofilterdriver.cat`
- **INF файл**: `GyroFilterDriver.inf`

## Использование

### Установка драйвера

1. Скопировать файлы драйвера в безопасное место
2. Открыть Device Manager
3. Найти устройство мыши
4. Обновить драйвер, указав путь к файлам

### Управление из user-mode приложения

```c
#include <windows.h>
#include <stdio.h>

#define IOCTL_GYRO_SET_FILTER CTL_CODE(FILE_DEVICE_MOUSE, 0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_GYRO_SET_THRESHOLD CTL_CODE(FILE_DEVICE_MOUSE, 0x802, METHOD_BUFFERED, FILE_ANY_ACCESS)

int main() {
    HANDLE hDevice = CreateFileA("\\\\.\\GyroMouseFilter", GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    
    if (hDevice == INVALID_HANDLE_VALUE) {
        printf("Failed to open device\n");
        return 1;
    }

    // Включить фильтрацию
    BOOLEAN filterEnabled = TRUE;
    DWORD bytesReturned;
    DeviceIoControl(hDevice, IOCTL_GYRO_SET_FILTER, &filterEnabled, sizeof(BOOLEAN), NULL, 0, &bytesReturned, NULL);

    // Установить порог фильтрации
    ULONG threshold = 10;
    DeviceIoControl(hDevice, IOCTL_GYRO_SET_THRESHOLD, &threshold, sizeof(ULONG), NULL, 0, &bytesReturned, NULL);

    CloseHandle(hDevice);
    return 0;
}
```

## Отладка

Для просмотра отладочных сообщений используйте DebugView или WinDbg:

```
GyroMouseFilter: DriverEntry
GyroMouseFilter: EvtDeviceAdd
GyroMouseFilter: Device fully initialized
GyroMouseFilter: Filtered small movement X=2 Y=3
GyroMouseFilter: Filtered movement X=15 Y=12
```

## Известные ограничения

1. VHF интеграция в текущей версии не полностью реализована
2. Фильтрация работает только для стандартных MOUSE_INPUT_DATA структур
3. Требуется перезагрузка системы для установки/удаления драйвера

## Будущие улучшения

1. Полная интеграция с Virtual HID Framework для создания виртуального устройства
2. Поддержка калибровки гироскопа
3. Адаптивная фильтрация на основе скорости движения
4. Поддержка различных профилей фильтрации
5. Логирование данных для анализа
