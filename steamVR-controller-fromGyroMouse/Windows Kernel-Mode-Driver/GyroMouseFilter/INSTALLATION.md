# Установка GyroMouse Filter Driver

## Требования

1. **Windows Driver Kit (WDK) 10**
   - Скачайте: https://docs.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk
   
2. **Visual Studio 2022** (Community Edition или выше)
   - С компонентами для C++ разработки
   
3. **Права администратора**

4. **Тестовый режим Windows** (для неподписанных драйверов)

---

## Шаг 1: Узнать VID/PID вашей гироскопической мыши

### Способ 1: Через Диспетчер устройств

1. Подключите гиро-мышь
2. Откройте **Диспетчер устройств** (Win+X → Device Manager)
3. Разверните раздел **"Мыши и иные указывающие устройства"**
4. Найдите вашу гиро-мышь, ПКМ → **Свойства**
5. Вкладка **"Сведения"** → Свойство: **"ИД оборудования"**
6. Вы увидите строку типа: `HID\VID_046D&PID_C52B`
7. Запишите значения VID и PID (например: VID=046D, PID=C52B)

### Способ 2: Автоматически

```powershell
# PowerShell скрипт для поиска HID мышей
Get-PnpDevice -Class Mouse | Where-Object {$_.Status -eq "OK"} | ForEach-Object {
    $_.InstanceId
}
```

---

## Шаг 2: Подготовка окружения

### 2.1 Включить тестовый режим (Test Signing)

**ВНИМАНИЕ:** Это снижает безопасность системы. Используйте только для разработки!

```cmd
# Запустите CMD от имени администратора
bcdedit /set testsigning on
bcdedit /set nointegritychecks on
```

**Перезагрузите компьютер.**

После перезагрузки в правом нижнем углу появится надпись "Test Mode".

### 2.2 Отключить Driver Signature Enforcement (опционально)

При загрузке Windows:
1. Shift + Перезагрузка
2. Troubleshoot → Advanced Options → Startup Settings → Restart
3. Нажмите F7 для "Disable driver signature enforcement"

---

## Шаг 3: Компиляция драйвера

### 3.1 Создать Visual Studio проект

1. Откройте **Visual Studio 2022**
2. File → New → Project
3. Выберите **"Kernel Mode Driver, Empty (KMDF)"**
4. Имя проекта: `GyroMouseFilter`

### 3.2 Добавить файлы

1. Скопируйте `driver.c` и `driver.h` в папку проекта
2. В Solution Explorer добавьте их: Add → Existing Item
3. Скопируйте `gyromouse.inf` в папку проекта

### 3.3 Настроить проект

**Properties → Driver Settings:**
- Target OS Version: Windows 10
- Target Platform: Desktop

**Properties → Inf2Cat:**
- Run Inf2Cat: Yes

**Properties → C/C++ → General:**
- Warning Level: Level3 (/W3)

### 3.4 Изменить INF файл

Откройте `gyromouse.inf` и замените строку:

```ini
%GyroMouseFilter.DeviceDesc%=GyroMouseFilter_Device, HID\VID_YOUR_VID&PID_YOUR_PID
```

На ваши значения VID/PID, например:

```ini
%GyroMouseFilter.DeviceDesc%=GyroMouseFilter_Device, HID\VID_046D&PID_C52B
```

### 3.5 Скомпилировать

1. Build → Configuration Manager
2. Active solution configuration: **Debug** или **Release**
3. Active solution platform: **x64** (для 64-bit Windows)
4. Build → Build Solution (F7)

Результат будет в: `x64\Debug\` или `x64\Release\`

Файлы:
- `gyromouse.sys` - драйвер
- `gyromouse.inf` - установочный файл
- `gyromouse.cat` - каталог

---

## Шаг 4: Установка драйвера

### Вариант А: Через Диспетчер устройств (рекомендуется)

1. Откройте **Диспетчер устройств** от имени администратора
2. Найдите вашу гиро-мышь в разделе **"Мыши..."**
3. ПКМ → **"Обновить драйвер"**
4. **"Выполнить поиск драйверов на этом компьютере"**
5. **"Выбрать драйвер из списка доступных драйверов"**
6. **"Установить с диска..."**
7. Укажите путь к папке с `gyromouse.inf`
8. Выберите **"GyroMouse Filter Driver"**
9. Подтвердите установку (может появиться предупреждение о неподписанном драйвере)

### Вариант Б: Через командную строку

```cmd
# От имени администратора
cd C:\Path\To\Your\x64\Debug

# Установить драйвер
pnputil /add-driver gyromouse.inf /install

# Проверить установку
pnputil /enum-drivers
```

### Вариант В: Через devcon (WDK)

```cmd
# devcon находится в C:\Program Files (x86)\Windows Kits\10\Tools\x64\
devcon install gyromouse.inf "HID\VID_046D&PID_C52B"
```

---

## Шаг 5: Проверка установки

### 5.1 В Диспетчере устройств

1. Найдите вашу мышь
2. ПКМ → Свойства → Вкладка "Драйвер"
3. Должно быть: **"GyroMouse Filter Driver"** или **"Gyroscopic Mouse Filter Driver"**

### 5.2 Через командную строку

```cmd
# Проверить загруженные драйверы
sc query GyroMouseFilter

# Логи драйвера (через DebugView или WinDbg)
```

### 5.3 Логи

Скачайте **DebugView** (Sysinternals):
- https://docs.microsoft.com/en-us/sysinternals/downloads/debugview

Запустите DebugView от имени администратора, вы увидите сообщения:
```
GyroMouseFilter: DriverEntry
GyroMouseFilter: EvtDeviceAdd
GyroMouseFilter: Device created successfully
```

---

## Шаг 6: Компиляция User-mode приложения

### 6.1 Создать проект

```bash
mkdir userapp
cd userapp
# Скопировать control.cpp
```

### 6.2 CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.10)
project(GyroMouseControl)

add_executable(control control.cpp)
target_link_libraries(control setupapi hid)
```

### 6.3 Скомпилировать

```bash
mkdir build
cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

---

## Шаг 7: Использование

### 7.1 Запустить control.exe

```cmd
# От имени администратора!
cd Release
control.exe
```

### 7.2 Использование

```
Available HID mice with filter driver:

[0] Logitech Gaming Mouse (VID=046D PID=C52B)
[1] Gyro Air Mouse X1 (VID=1234 PID=5678)

Enter the number of the gyro mouse to BLOCK: 1

Selected: Gyro Air Mouse X1
VID=1234 PID=5678

Commands:
  1 - Enable blocking (gyro mouse will be blocked)
  0 - Disable blocking (gyro mouse will work normally)
  q - Quit

> 1
SUCCESS: Gyro mouse is now BLOCKED from Windows input.
Move the mouse - cursor should NOT move.
```

---

## Отладка

### Если драйвер не загружается:

1. **Проверьте тестовый режим:**
   ```cmd
   bcdedit /enum | findstr /i "testsigning"
   # Должно быть: testsigning Yes
   ```

2. **Проверьте логи установки:**
   ```cmd
   C:\Windows\INF\setupapi.dev.log
   ```

3. **Используйте WinDbg для отладки:**
   - Kernel debugging over network или serial

4. **Проверьте VID/PID:**
   - Убедитесь, что в INF указаны правильные значения

### Если драйвер установлен, но не работает:

1. **Проверьте, что драйвер загружен:**
   ```cmd
   sc query GyroMouseFilter
   ```

2. **Проверьте Device Manager:**
   - Есть ли желтый треугольник на устройстве?

3. **Проверьте логи в DebugView**

---

## Удаление драйвера

### Через Диспетчер устройств:

1. ПКМ на устройстве → Удалить устройство
2. Отметить "Удалить драйвер"

### Через командную строку:

```cmd
# Удалить драйвер
pnputil /delete-driver oem##.inf /uninstall

# Остановить сервис
sc stop GyroMouseFilter
sc delete GyroMouseFilter
```

### Отключить тестовый режим:

```cmd
bcdedit /set testsigning off
bcdedit /set nointegritychecks off
```

**Перезагрузите компьютер.**

---

## Важные замечания

⚠️ **БЕЗОПАСНОСТЬ:**
- Тестовый режим снижает безопасность Windows
- Используйте только для разработки/тестирования
- Для production нужна подпись драйвера от Microsoft (EV сертификат)

⚠️ **СОВМЕСТИМОСТЬ:**
- Драйвер работает только с Windows 10/11 (64-bit)
- Требуется точное совпадение VID/PID

⚠️ **ПРОИЗВОДИТЕЛЬНОСТЬ:**
- Фильтр-драйвер добавляет минимальную задержку (~1ms)
- Не влияет на другие мыши

---

## Следующие шаги

После успешной установки вы можете:

1. **Интегрировать с UDP отправкой:**
   - Модифицировать драйвер для отправки данных через shared memory
   - User-mode приложение читает и отправляет по UDP

2. **Добавить GUI:**
   - Создать Windows Forms или WPF приложение для управления

3. **Подписать драйвер:**
   - Получить EV сертификат
   - Пройти WHQL тестирование
   - Опубликовать через Windows Update

---

## Полезные ссылки

- [Windows Driver Kit Documentation](https://docs.microsoft.com/en-us/windows-hardware/drivers/)
- [KMDF Documentation](https://docs.microsoft.com/en-us/windows-hardware/drivers/wdf/)
- [HID over USB](https://docs.microsoft.com/en-us/windows-hardware/drivers/hid/)
- [Driver Signing](https://docs.microsoft.com/en-us/windows-hardware/drivers/install/driver-signing)