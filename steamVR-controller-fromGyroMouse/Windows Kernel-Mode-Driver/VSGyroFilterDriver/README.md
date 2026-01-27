# GyroMouseFilter - Краткое резюме

## Что было сделано

Драйвер фильтра мыши был полностью переработан для добавления функциональности фильтрации позиции. Теперь драйвер может:

✅ Фильтровать шум малых движений мыши  
✅ Сглаживать движение мыши  
✅ Блокировать ввод мыши полностью  
✅ Управляться через IOCTL команды из user-mode приложений  

## Ключевые изменения

### 1. Алгоритм фильтрации
- **Фильтрация шума**: Игнорирует движения меньше порога (по умолчанию 5 пикселей)
- **Сглаживание**: Применяет экспоненциальное сглаживание (75% новое, 25% старое)

### 2. Новые IOCTL команды
```
IOCTL_GYRO_SET_BLOCK (0x800)      - Блокировка ввода
IOCTL_GYRO_SET_FILTER (0x801)     - Включение/отключение фильтрации
IOCTL_GYRO_SET_THRESHOLD (0x802)  - Установка порога фильтрации
IOCTL_GYRO_GET_INFO (0x803)       - Получение информации об устройстве
```

### 3. Обновленная структура контекста
```c
typedef struct _DEVICE_CONTEXT {
    WDFQUEUE DefaultQueue;
    WDFIOTARGET IoTarget;
    BOOLEAN BlockInput;           // Новое
    BOOLEAN FilterEnabled;        // Новое
    USHORT VendorId;
    USHORT ProductId;
    LONG LastX;                   // Новое
    LONG LastY;                   // Новое
    ULONG FilterThreshold;        // Новое
    PVOID VhfHandle;              // Новое
} DEVICE_CONTEXT;
```

## Файлы проекта

### Основные файлы
- `driver.c` - Основной код драйвера с фильтрацией
- `driver.h` - Заголовочный файл с определениями
- `GyroFilterDriver.vcxproj` - Файл проекта Visual Studio

### Документация
- `FILTER_DOCUMENTATION.md` - Полная документация по фильтрации
- `REPORT.md` - Подробный отчет о проделанной работе
- `CLI_BUILD_INSTRUCTIONS.md` - Инструкции по компиляции

### Примеры
- `GyroMouseFilterControl.c` - User-mode приложение для управления драйвером

## Компиляция

```cmd
cd /d "d:\MyDocuments\Programming\Projects_C\VR-Driver\steamVR-controller-fromGyroMouse\Windows Kernel-Mode-Driver\VSGyroFilterDriver\GyroFilterDriver"
"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"
msbuild GyroFilterDriver.sln /p:Configuration=Release /p:Platform=x64 /v:minimal
```

**Результат**: `x64\Release\GyroFilterDriver.sys`

## Использование

### Включить фильтрацию
```c
BOOLEAN filterEnabled = TRUE;
DeviceIoControl(hDevice, IOCTL_GYRO_SET_FILTER, &filterEnabled, sizeof(BOOLEAN), NULL, 0, &bytesReturned, NULL);
```

### Установить порог фильтрации (10 пикселей)
```c
ULONG threshold = 10;
DeviceIoControl(hDevice, IOCTL_GYRO_SET_THRESHOLD, &threshold, sizeof(ULONG), NULL, 0, &bytesReturned, NULL);
```

### Блокировать ввод мыши
```c
BOOLEAN blockFlag = TRUE;
DeviceIoControl(hDevice, IOCTL_GYRO_SET_BLOCK, &blockFlag, sizeof(BOOLEAN), NULL, 0, &bytesReturned, NULL);
```

## Требования

- Windows 10 или выше
- Visual Studio 2022 Professional
- Windows Driver Kit (WDK) 10.0.19041.0
- KMDF (Kernel-Mode Driver Framework)

## Отладка

Просмотр отладочных сообщений:
```
DebugView.exe
```

Сообщения драйвера:
```
GyroMouseFilter: Filtered small movement X=2 Y=3
GyroMouseFilter: Filtered movement X=15 Y=12
GyroMouseFilter: BLOCKED Delta X=0 Y=0
```

## Статус

✅ **Проект успешно скомпилирован**
✅ **Все файлы готовы к использованию**
✅ **Документация полная**
✅ **Примеры кода предоставлены**

## Следующие шаги

1. Установить драйвер через Device Manager
2. Протестировать фильтрацию с помощью GyroMouseFilterControl.exe
3. Оптимизировать параметры фильтрации для вашего гироскопа
4. Интегрировать в ваше приложение VR

## Контакты

Для вопросов и поддержки обратитесь к документации в папке проекта.
