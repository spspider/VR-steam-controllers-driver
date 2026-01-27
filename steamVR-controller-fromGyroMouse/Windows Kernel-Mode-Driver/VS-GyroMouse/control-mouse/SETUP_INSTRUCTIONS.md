# Инструкция по сборке и установке GyroMouse Driver

## Часть 1: Подготовка окружения

### Шаг 1: Установка необходимых компонентов

1. **Visual Studio 2022 Community** (бесплатно)
   - Скачайте с https://visualstudio.microsoft.com/downloads/
   - При установке выберите: "Desktop development with C++"
   - Убедитесь, что установлены:
     - MSVC v143 (или новее)
     - Windows 10/11 SDK

2. **Windows Driver Kit (WDK) 11**
   - Скачайте с https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk
   - Установите версию, совместимую с вашей ОС
   - Это даст вам необходимые заголовки и библиотеки для разработки драйверов

3. **Windows SDK** (если не установлен с VS)
   - Скачайте с https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/

### Шаг 2: Проверка установки

Откройте Command Prompt и выполните:
```cmd
where msbuild
where cl.exe
```

Если команды не найдены, добавьте пути в PATH:
- `C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin`
- `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.3x.xxxxx\bin\Hostx64\x64`

---

## Часть 2: Сборка драйвера

### Шаг 1: Откройте проект в Visual Studio

1. Запустите Visual Studio 2022
2. Откройте файл: `VS-GyroMouse\GyroMouse\GyroMouse.sln`

### Шаг 2: Настройка проекта

1. В Solution Explorer найдите проект `GyroMouse`
2. Нажмите правой кнопкой → Properties
3. Проверьте:
   - **Configuration**: Release (или Debug для тестирования)
   - **Platform**: x64 (для 64-битной Windows)
   - **Driver Settings**:
     - Target OS Version: Windows 10 или выше
     - KMDF Version: 1.15 или выше

### Шаг 3: Сборка

1. В меню выберите: **Build** → **Build Solution** (или Ctrl+Shift+B)
2. Ждите завершения сборки
3. Проверьте Output окно на ошибки

**Результат**: Файл `gyromouse.sys` будет создан в папке:
```
VS-GyroMouse\GyroMouse\GyroMouse\x64\Release\
```

---

## Часть 3: Подготовка к установке

### Шаг 1: Создайте папку для драйвера

```cmd
mkdir "C:\GyroMouseDriver"
```

### Шаг 2: Скопируйте файлы

Скопируйте в `C:\GyroMouseDriver\`:
- `gyromouse.sys` (из папки сборки)
- `GyroMouse.inf` (из папки проекта)
- `gyromouse.cat` (если есть, или создайте пустой файл)

### Шаг 3: Подпишите драйвер (для тестирования)

Для тестирования на Windows 10/11 нужна подпись. Используйте тестовый сертификат:

```cmd
cd C:\GyroMouseDriver

REM Создайте тестовый сертификат (один раз)
makecert -r -pe -ss PrivateCertStore -n "CN=GyroMouseTest" GyroMouseTest.cer

REM Подпишите драйвер
signtool sign /f GyroMouseTest.pfx /fd sha256 gyromouse.sys
```

Если `signtool` не найден, используйте полный путь:
```cmd
"C:\Program Files (x86)\Windows Kits\10\bin\10.0.xxxxx.0\x64\signtool.exe"
```

---

## Часть 4: Установка драйвера

### Способ 1: Через Device Manager (рекомендуется для тестирования)

1. **Включите режим тестирования Windows**:
   ```cmd
   bcdedit /set testsigning on
   ```
   Перезагрузитесь.

2. **Подключите устройство мыши** (которое хотите фильтровать)

3. Откройте **Device Manager** (devmgmt.msc)

4. Найдите вашу мышь в разделе "Mice and other pointing devices"

5. Нажмите правой кнопкой → **Update driver**

6. Выберите **Browse my computer for driver software**

7. Укажите путь: `C:\GyroMouseDriver\`

8. Нажмите **Next** и следуйте инструкциям

### Способ 2: Через командную строку (для автоматизации)

```cmd
REM Запустите как Administrator
cd C:\GyroMouseDriver
pnputil /add-driver GyroMouse.inf /install
```

---

## Часть 5: Проверка установки

### Шаг 1: Проверьте в Device Manager

1. Откройте Device Manager (devmgmt.msc)
2. Найдите "Gyroscopic Mouse Filter Driver v1" в разделе "Mice and other pointing devices"
3. Если есть жёлтый восклицательный знак — есть проблема с подписью или конфигурацией

### Шаг 2: Проверьте логи драйвера

Используйте DebugView для просмотра логов:

1. Скачайте DebugView с https://learn.microsoft.com/en-us/sysinternals/downloads/debugview
2. Запустите как Administrator
3. Фильтр: `GyroMouseFilter`
4. Подвигайте мышь — должны появиться логи

---

## Часть 6: Тестирование

### Тест 1: Проверка блокировки мыши

1. Установите драйвер
2. Подвигайте мышь — она должна быть заблокирована (не двигается)
3. Кнопки мыши также должны быть заблокированы

### Тест 2: Управление через программу

Используйте `mouse_hook_blocking.cpp` для отправки команд драйверу:

```cpp
// Отправить команду на блокировку
HANDLE hDevice = CreateFileA("\\\\.\\GyroMouseFilter", 
    GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);

BOOLEAN blockFlag = TRUE;
DWORD bytesReturned;
DeviceIoControl(hDevice, IOCTL_GYRO_SET_BLOCK, 
    &blockFlag, sizeof(BOOLEAN), NULL, 0, &bytesReturned, NULL);

CloseHandle(hDevice);
```

---

## Часть 7: Отключение режима тестирования (после тестирования)

```cmd
bcdedit /set testsigning off
```

Перезагрузитесь.

---

## Решение проблем

### Проблема: "Driver signature verification failed"

**Решение:**
1. Убедитесь, что включен режим тестирования: `bcdedit /query testsigning`
2. Если выключен, включите: `bcdedit /set testsigning on`
3. Перезагрузитесь

### Проблема: "Device not found in Device Manager"

**Решение:**
1. Проверьте VID/PID в GyroMouse.inf — должны совпадать с вашей мышью
2. Используйте Device Manager для просмотра VID/PID:
   - Правой кнопкой на устройстве → Properties
   - Вкладка Details → Hardware IDs
3. Обновите GyroMouse.inf с правильными VID/PID

### Проблема: "Драйвер не блокирует мышь"

**Решение:**
1. Проверьте логи в DebugView
2. Убедитесь, что `BlockInput = TRUE` в коде
3. Перезагрузитесь после установки

---

## Полезные команды

```cmd
REM Просмотр установленных драйверов
pnputil /enum-drivers

REM Удаление драйвера
pnputil /delete-driver GyroMouse.inf /uninstall

REM Просмотр логов системы
eventvwr.msc

REM Просмотр логов драйвера
Get-WinEvent -LogName System | Where-Object {$_.ProviderName -like "*GyroMouse*"}
```

---

## Если Вариант A не работает

Переходите на **Вариант B** (виртуальное HID-устройство). Дайте знать, и я помогу с реализацией.
