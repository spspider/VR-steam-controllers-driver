# GyroMouse Kernel-Mode Filter Driver

Kernel-mode фильтр-драйвер для полной блокировки конкретной HID мыши от Windows, позволяя перехватывать её данные для других целей (например, VR контроллер).

## Что это делает?

- ✅ Блокирует **только выбранную** гиро-мышь от управления курсором Windows
- ✅ Все другие мыши работают нормально
- ✅ Позволяет перехватывать Raw данные для отправки по UDP/сети
- ✅ Работает на уровне ядра (kernel-mode) - самый надежный способ

## Быстрый старт

### Шаг 1: Узнать VID/PID вашей мыши

```powershell
# PowerShell от администратора
Get-PnpDevice -Class Mouse | Where-Object {$_.Status -eq "OK"}
```

Или в Диспетчере устройств:
- Найдите вашу мышь → Свойства → Сведения → ИД оборудования
- Например: `HID\VID_046D&PID_C52B` (VID=046D, PID=C52B)

### Шаг 2: Включить тестовый режим

```cmd
:: CMD от администратора
bcdedit /set testsigning on
```

**Перезагрузите компьютер!**

### Шаг 3: Подготовить окружение

**Установите:**
1. Visual Studio 2022 Community
2. Windows Driver Kit (WDK) 10
3. Windows SDK

### Шаг 4: Скомпилировать драйвер

1. Откройте Visual Studio 2022
2. Создайте проект: **Kernel Mode Driver, Empty (KMDF)**
3. Добавьте файлы: `driver.c`, `driver.h`
4. Скопируйте `gyromouse.inf`
5. **Важно:** Отредактируйте `gyromouse.inf`:
   ```ini
   ; Замените YOUR_VID и YOUR_PID на ваши значения!
   %GyroMouseFilter.DeviceDesc%=GyroMouseFilter_Device, HID\VID_046D&PID_C52B
   ```
6. Build → Build Solution (F7)

### Шаг 5: Установить драйвер

**Диспетчер устройств:**
1. Найдите вашу гиро-мышь
2. ПКМ → Обновить драйвер → Выполнить поиск на этом компьютере
3. Выбрать драйвер из списка → Установить с диска
4. Укажите путь к `gyromouse.inf`

**Или через командную строку:**
```cmd
cd x64\Debug
pnputil /add-driver gyromouse.inf /install
```

### Шаг 6: Скомпилировать control.exe

```bash
cd userapp
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

### Шаг 7: Использование

```cmd
:: От администратора!
cd Release
control.exe
```

Выберите вашу гиро-мышь и нажмите `1` для блокировки.

## Структура проекта

```
GyroMouseFilter/
├── driver/
│   ├── driver.c          # Основной код драйвера
│   ├── driver.h          # Заголовки
│   └── gyromouse.inf     # Установочный файл
├── userapp/
│   ├── control.cpp       # User-mode управление
│   └── CMakeLists.txt
├── INSTALLATION.md       # Подробная инструкция
└── README.md             # Этот файл
```

## Как это работает?

```
User Application (control.exe)
        ↓ IOCTL
Kernel Filter Driver (gyromouse.sys)
        ↓ Filters HID data
HID Mouse Class Driver
        ↓
HID Transport (USB/Bluetooth)
        ↓
Physical Mouse Device
```

1. **Драйвер** встраивается в стек HID устройства как фильтр
2. Перехватывает все данные от мыши
3. При включенной блокировке - обнуляет данные (курсор не двигается)
4. User-mode приложение управляет блокировкой через IOCTL

## Отладка

**Посмотреть логи драйвера:**
1. Скачайте DebugView (Sysinternals)
2. Запустите от администратора
3. Увидите сообщения типа:
   ```
   GyroMouseFilter: DriverEntry
   GyroMouseFilter: Device created successfully
   GyroMouseFilter: BLOCKED Mouse Delta X=5 Y=-3
   ```

**Проверить установку:**
```cmd
sc query GyroMouseFilter
pnputil /enum-drivers | findstr gyromouse
```

## Интеграция с UDP (следующий шаг)

После блокировки мыши данные можно отправлять:

1. **Shared Memory:** Драйвер → User-mode app → UDP
2. **Named Pipe:** Kernel → User space
3. **WFP (Windows Filtering Platform):** Прямо из ядра

Пример интеграции в `driver.c`:
```c
// В completion routine вместо обнуления:
if (deviceContext->BlockInput) {
    // Сохранить в shared memory для user-mode
    WriteToSharedMemory(mouseData);
    
    // Обнулить для Windows
    RtlZeroMemory(mouseData, sizeof(MOUSE_INPUT_DATA));
}
```

## Удаление

```cmd
:: Через Device Manager удалить драйвер

:: Или командная строка
pnputil /delete-driver oem##.inf /uninstall
sc delete GyroMouseFilter

:: Отключить тестовый режим
bcdedit /set testsigning off
```

**Перезагрузка!**

## Предупреждения

⚠️ **Тестовый режим снижает безопасность Windows**
- Используйте только для разработки
- Для production нужна подпись драйвера

⚠️ **Права администратора обязательны**

⚠️ **Совместимость:**
- Windows 10/11 x64 only
- Требуется точный VID/PID

## FAQ

**Q: Курсор всё равно двигается?**
A: Проверьте, что драйвер установлен именно на вашу мышь в Device Manager.

**Q: Driver не загружается?**
A: Убедитесь что testsigning включен и перезагрузились.

**Q: Как подписать для production?**
A: Нужен EV сертификат и WHQL тестирование от Microsoft.

**Q: Можно ли блокировать несколько мышей?**
A: Да, установите драйвер на каждую отдельно с разными VID/PID в INF.

## Лицензия

MIT License - используйте как хотите, но без гарантий.

## Поддержка

Для вопросов смотрите [INSTALLATION.md](INSTALLATION.md) с подробными инструкциями.