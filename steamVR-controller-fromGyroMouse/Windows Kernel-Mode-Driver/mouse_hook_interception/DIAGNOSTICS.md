# Диагностика и отладка

Полное руководство по решению проблем с Gyro Mouse Blocker.

---

## 🔍 Проверка системы

### 1. Проверить тестовый режим

```cmd
bcdedit | findstr testsigning
```

**Ожидается:**
```
testsigning             Yes
```

**Если нет:**
```cmd
bcdedit /set testsigning on
# Перезагрузка!
```

### 2. Проверить драйвер Interception

```cmd
sc query interception
```

**Ожидается:**
```
STATE              : 4  RUNNING
```

**Если не запущен:**
```cmd
sc start interception
```

**Если не установлен:**
```cmd
cd Interception\command line installer
install-interception.exe /install
# Перезагрузка!
```

### 3. Проверить права администратора

```cmd
net session
```

**Если ошибка "Access is denied"** - запустите CMD от администратора.

---

## 🧪 Тестирование компонентов

### Тест 1: Interception samples

Проверить, что драйвер работает:

```cmd
cd Interception\samples\x86
identify.exe
```

Подвигайте мышами и клавиатурой. Должны показываться устройства:
```
device 11: mouse
device 12: mouse
device 1: keyboard
```

**Если устройства не показываются:**
- Драйвер не работает
- Перезагрузите компьютер
- Переустановите драйвер

### Тест 2: Список устройств

```cmd
cd Interception\samples\x86
hardwareid.exe
```

Должен показать hardware ID всех устройств:
```
device 11: HID\VID_046D&PID_C52B&REV_0001
device 12: HID\VID_093A&PID_2510&REV_0100
```

### Тест 3: UDP порт

Проверить, что порт 5556 свободен:

```cmd
netstat -an | findstr 5556
```

**Если порт занят:**
```cmd
# Найти процесс
netstat -ano | findstr 5556

# Завершить процесс (PID из предыдущей команды)
taskkill /PID <PID> /F
```

---

## 📊 Логирование

### Включить подробное логирование

Добавьте в `mouse_hook.cpp` перед `main()`:

```cpp
#define VERBOSE_LOGGING 1

void LogToFile(const std::string& message) {
    static std::ofstream logFile("debug.log", std::ios::app);
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    logFile << std::ctime(&time) << ": " << message << std::endl;
}
```

Затем в нужных местах:
```cpp
LogToFile("Device " + std::to_string(device) + " event received");
```

Пересоберите проект:
```bash
cd build
cmake --build .
```

Лог будет в файле `debug.log`.

### Просмотр логов в реальном времени

**PowerShell:**
```powershell
Get-Content debug.log -Wait -Tail 20
```

**CMD:**
```cmd
powershell Get-Content debug.log -Wait -Tail 20
```

---

## 🐛 Типичные проблемы

### Проблема 1: "Failed to create Interception context"

**Диагностика:**
```cmd
# Проверить драйвер
sc query interception

# Проверить файлы драйвера
dir C:\Windows\System32\drivers\interception.sys

# Проверить статус в диспетчере устройств
devmgmt.msc
# → System devices → Interception Filter Driver
```

**Решение:**
1. Переустановить драйвер
2. Проверить тестовый режим
3. Перезагрузка

### Проблема 2: Программа видит мыши, но не блокирует

**Диагностика:**
```cpp
// Добавить в ProcessEvents():
std::cout << "Received event from device: " << device 
          << " (target: " << g_targetDevice << ")" << std::endl;
```

**Возможные причины:**
- Неправильно выбрано устройство
- Device ID изменился после перезагрузки
- Мышь подключена к другому порту

**Решение:**
```bash
# Удалить конфиг и выбрать заново
rm mouse_config.txt
./mouse_hook.exe
```

### Проблема 3: Курсор дергается/лагает

**Причина:** Другие программы тоже используют Interception

**Диагностика:**
```cmd
# Найти процессы, использующие interception.dll
tasklist /m interception.dll
```

**Решение:**
- Закрыть другие программы, использующие Interception
- Проверить автозагрузку

### Проблема 4: UDP данные не приходят

**Тест UDP приёмника:**

**Python (простой):**
```python
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('127.0.0.1', 5556))
print("Listening on 5556...")
while True:
    data, addr = s.recvfrom(1024)
    print(data.decode())
```

**NetCat:**
```bash
nc -ul 127.0.0.1 5556
```

**Wireshark:**
1. Запустить Wireshark
2. Фильтр: `udp.port == 5556`
3. Start capture
4. Двигать гиро-мышью
5. Должны появиться UDP пакеты

**Если пакеты не идут:**
- Проверить, что mouse_hook.exe запущен
- Проверить firewall (отключить временно)
- Проверить antivirus

### Проблема 5: Компиляция не работает

**MinGW ошибки:**
```bash
# Проверить установку MinGW
g++ --version
cmake --version

# Очистить build и пересобрать
rm -rf build
mkdir build
cd build
cmake .. -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Debug
cmake --build . --verbose
```

**MSVC ошибки:**
```cmd
# Использовать Visual Studio Developer Command Prompt
cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release -- /verbosity:detailed
```

---

## 📈 Производительность

### Измерить задержку

Добавить в `ProcessEvents()`:

```cpp
auto start = std::chrono::high_resolution_clock::now();

// ... обработка события ...

auto end = std::chrono::high_resolution_clock::now();
auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);

if (duration.count() > 1000) {  // > 1ms
    std::cout << "WARNING: High latency: " << duration.count() << "μs" << std::endl;
}
```

**Нормальная задержка:** < 500 μs

### Мониторинг системы

```cmd
# CPU usage
wmic cpu get loadpercentage

# Memory
wmic OS get FreePhysicalMemory

# Process info
wmic process where name="mouse_hook.exe" get ProcessId,ThreadCount,WorkingSetSize
```

---

## 🔧 Дополнительные инструменты

### DebugView (Sysinternals)

Для просмотра kernel-mode логов:

1. Скачать: https://learn.microsoft.com/en-us/sysinternals/downloads/debugview
2. Запустить от администратора
3. Capture → Capture Kernel
4. Увидите логи драйвера Interception

### Process Monitor (Sysinternals)

Для отслеживания I/O операций:

1. Скачать: https://learn.microsoft.com/en-us/sysinternals/downloads/procmon
2. Фильтр: Process Name is `mouse_hook.exe`
3. Увидите все файловые/сетевые операции

### USB View

Для просмотра USB устройств:

1. Скачать из WDK
2. Запустить UsbView.exe
3. Найти вашу гиро-мышь в дереве устройств
4. Проверить VID/PID

---

## 📝 Чек-лист при проблемах

Перед тем как искать помощь, проверьте:

1. ✅ Тестовый режим включен: `bcdedit | findstr testsigning`
2. ✅ Драйвер запущен: `sc query interception` → RUNNING
3. ✅ Права администратора: `net session` без ошибок
4. ✅ Файлы на месте:
   - `build/mouse_hook.exe`
   - `build/interception.dll`
5. ✅ Interception samples работают: `identify.exe` показывает устройства
6. ✅ UDP порт свободен: `netstat -an | findstr 5556`
7. ✅ Правильная мышь выбрана: проверить VID/PID
8. ✅ Перезагрузка после установки драйвера
9. ✅ Firewall не блокирует UDP
10. ✅ Antivirus не блокирует программу

---

## 🆘 Получение помощи

При запросе помощи предоставьте:

1. **Вывод команд:**
   ```cmd
   bcdedit | findstr testsigning
   sc query interception
   cmake --version
   g++ --version
   ```

2. **Лог программы:**
   ```
   Полный вывод mouse_hook.exe в консоль
   ```

3. **Список устройств:**
   ```cmd
   cd Interception\samples\x86
   hardwareid.exe
   ```

4. **Версия Windows:**
   ```cmd
   winver
   ```

5. **Описание проблемы:**
   - Что ожидали
   - Что произошло
   - Шаги для воспроизведения

---

**Удачи с отладкой!** 🔧