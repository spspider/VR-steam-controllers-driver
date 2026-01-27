# Компиляция GyroMouse Filter Driver в Visual Studio 2022

## Шаг 1: Проверка установленных компонентов

### 1.1 Visual Studio 2022
Запустите **Visual Studio Installer** и убедитесь, что установлено:
- ✅ Desktop development with C++
- ✅ Windows SDK (10.0.22621.0 или новее)

### 1.2 Windows Driver Kit (WDK)
1. Скачайте: https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk
2. Установите **WDK for Windows 11, version 22H2** (или новее)
3. После установки проверьте путь:
   ```
   C:\Program Files (x86)\Windows Kits\10\Include\10.0.22621.0\km\
   ```

---

## Шаг 2: Создание проекта

### 2.1 Создать новый проект

1. Откройте **Visual Studio 2022**
2. **File → New → Project**
3. В поиске введите: **"driver"**
4. Выберите: **"Kernel Mode Driver, Empty (KMDF)"**
5. Нажмите **Next**

### 2.2 Настроить проект

- **Project name:** `GyroMouseFilter`
- **Location:** Выберите папку (например, `D:\MyProjects\`)
- **Solution name:** `GyroMouseFilter`
- Нажмите **Create**

---

## Шаг 3: Добавление файлов

### 3.1 Добавить driver.h

1. В **Solution Explorer** ПКМ на проекте `GyroMouseFilter`
2. **Add → New Item...**
3. Выберите **Header File (.h)**
4. Имя: `driver.h`
5. Нажмите **Add**
6. **Скопируйте весь код из артефакта driver.h**

### 3.2 Добавить driver.c

1. В **Solution Explorer** ПКМ на проекте
2. **Add → New Item...**
3. Выберите **C++ File (.cpp)**
4. Имя: `driver.c` (ВАЖНО: .c а не .cpp!)
5. Нажмите **Add**
6. **Скопируйте весь код из артефакта driver_simple.c** (упрощенная версия)

### 3.3 Добавить INF файл

1. В **Solution Explorer** ПКМ на проекте
2. **Add → New Item...**
3. Выберите **Text File (.txt)**
4. Имя: `gyromouse.inf`
5. Нажмите **Add**
6. **Скопируйте весь код из артефакта gyromouse.inf**
7. **ВАЖНО:** Отредактируйте строку с VID/PID:
   ```ini
   %GyroMouseFilter.DeviceDesc%=GyroMouseFilter_Device, HID\VID_046D&PID_C52B
   ```
   Замените `046D` и `C52B` на VID/PID вашей гиро-мыши!

---

## Шаг 4: Настройка проекта

### 4.1 Открыть свойства проекта

1. ПКМ на проекте `GyroMouseFilter`
2. **Properties**
3. Вверху выберите:
   - **Configuration:** `All Configurations`
   - **Platform:** `All Platforms`

### 4.2 Configuration Properties → General

Установите:
- **Target Platform:** `Desktop`
- **Platform Toolset:** `WindowsKernelModeDriver10.0`
- **Configuration Type:** `Driver`

### 4.3 Configuration Properties → Driver Settings

#### General:
- **Target OS Version:** `Windows 10 or higher`
- **Target Platform:** `Desktop`

#### Driver Model:
- **Type of driver:** `KMDF`
- **KMDF Version Major:** `1`
- **KMDF Version Minor:** `15` (или выше)

### 4.4 Configuration Properties → C/C++ → General

- **Warning Level:** `Level3 (/W3)`
- **Treat Warnings As Errors:** `No`

### 4.5 Configuration Properties → C/C++ → Preprocessor

**Preprocessor Definitions:** (проверьте, что есть эти макросы)
```
_WIN64
_AMD64_
AMD64
POOL_NX_OPTIN=1
```

### 4.6 Configuration Properties → Inf2Cat

- **Run Inf2Cat:** `Yes`
- **Use Local Time:** `Yes`

---

## Шаг 5: Компиляция

### 5.1 Выбрать конфигурацию

В верхней панели Visual Studio:
- **Configuration:** `Debug` (или `Release`)
- **Platform:** `x64`

### 5.2 Собрать решение

1. **Build → Build Solution** (или нажмите **F7**)
2. Дождитесь окончания сборки
3. Проверьте **Output** окно на наличие ошибок

### 5.3 Результат сборки

Если всё успешно, файлы будут в:
```
x64\Debug\
  ├── gyromouse.sys      (драйвер)
  ├── gyromouse.inf      (установочный файл)
  └── gyromouse.cat      (каталог)
```

---

## Возможные ошибки и решения

### ❌ Ошибка: "Cannot find WdfDriverCreate"

**Причина:** Неправильные настройки KMDF

**Решение:**
1. Project Properties → Driver Settings → Driver Model
2. Убедитесь: Type of driver = `KMDF`
3. KMDF Version Major = `1`, Minor = `15`

### ❌ Ошибка: "unresolved external symbol _WdfVersionBind"

**Причина:** Не подключены KMDF библиотеки

**Решение:**
1. Project Properties → Linker → Input → Additional Dependencies
2. Добавьте:
   ```
   $(DDK_LIB_PATH)ntoskrnl.lib
   $(DDK_LIB_PATH)hal.lib
   $(KMDF_LIB_PATH)\$(KMDF_VER_PATH)\WdfDriverEntry.lib
   $(KMDF_LIB_PATH)\$(KMDF_VER_PATH)\WdfLdr.lib
   ```

### ❌ Ошибка: "ntddmou.h: No such file or directory"

**Причина:** WDK не установлен или Visual Studio не видит его

**Решение:**
1. Переустановите WDK
2. Перезапустите Visual Studio
3. Project Properties → C/C++ → General → Additional Include Directories
4. Добавьте:
   ```
   $(DDK_INC_PATH)
   $(DDK_INC_PATH)\km
   ```

### ❌ Ошибка: "MOUSE_INPUT_DATA redefinition"

**Причина:** Использован старый driver.h с собственной структурой

**Решение:**
- Используйте обновленный `driver.h` из артефактов выше
- Убедитесь, что удалено ваше определение `MOUSE_INPUT_DATA`

### ❌ Ошибка INF: "Cannot specify [ClassInstall32]"

**Причина:** Использован старый INF файл

**Решение:**
- Используйте обновленный `gyromouse.inf` из артефактов выше
- Убедитесь, что удалена секция `[ClassInstall32]`

---

## Шаг 6: Тестовая подпись (для Debug)

### 6.1 Подписать драйвер

После успешной сборки, подпишите драйвер для тестирования:

```cmd
cd x64\Debug

makecert -r -pe -ss PrivateCertStore -n "CN=GyroMouseTest" GyroMouseTest.cer

signtool sign /v /s PrivateCertStore /n "GyroMouseTest" /t http://timestamp.digicert.com gyromouse.sys
```

### 6.2 Установить тестовый сертификат

```cmd
certmgr.exe /add GyroMouseTest.cer /s /r localMachine root
certmgr.exe /add GyroMouseTest.cer /s /r localMachine trustedpublisher
```

---

## Шаг 7: Проверка сборки

### 7.1 Проверить файлы

Убедитесь, что созданы файлы:
```
x64\Debug\gyromouse.sys    - размер ~10-20 KB
x64\Debug\gyromouse.inf    - текстовый файл
x64\Debug\gyromouse.cat    - каталог файлов
```

### 7.2 Проверить символы (PDB)

Должен быть создан:
```
x64\Debug\gyromouse.pdb    - для отладки
```

---

## Шаг 8: Установка драйвера

См. подробную инструкцию в `INSTALLATION.md`

Краткая версия:
```cmd
# Включить тестовый режим
bcdedit /set testsigning on

# Перезагрузка

# Установить драйвер
cd x64\Debug
pnputil /add-driver gyromouse.inf /install

# Обновить драйвер устройства через Device Manager
```

---

## Советы по отладке

### Использование DbgView

1. Скачайте DbgView: https://learn.microsoft.com/en-us/sysinternals/downloads/debugview
2. Запустите от администратора
3. Capture → Capture Kernel
4. В окне увидите сообщения `KdPrint()` из драйвера

### WinDbg для kernel debugging

Для серьезной отладки используйте WinDbg:
1. Настройте kernel debugging (network или serial)
2. Подключитесь к целевой машине
3. Установите breakpoint'ы в коде драйвера

---

## Чек-лист перед компиляцией

- ✅ WDK установлен
- ✅ Visual Studio 2022 установлена
- ✅ Проект создан из шаблона "KMDF Empty Driver"
- ✅ Добавлены файлы: driver.h, driver.c, gyromouse.inf
- ✅ В gyromouse.inf указан правильный VID/PID
- ✅ Configuration = Debug или Release
- ✅ Platform = x64
- ✅ Driver Settings: Type = KMDF
- ✅ Target Platform = Desktop

---

## Дополнительные ресурсы

- [WDK Documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/)
- [KMDF Samples](https://github.com/Microsoft/Windows-driver-samples)
- [Driver Development Guide](https://learn.microsoft.com/en-us/windows-hardware/drivers/gettingstarted/)

---

Если возникнут другие ошибки, пришлите **полный текст ошибки** из Output окна Visual Studio!