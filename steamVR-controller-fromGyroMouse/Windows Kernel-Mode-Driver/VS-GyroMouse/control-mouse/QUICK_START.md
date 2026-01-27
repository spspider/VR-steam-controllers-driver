# Быстрый старт - GyroMouse Driver

## Что нужно установить (один раз)

1. **Visual Studio 2022 Community**
   - https://visualstudio.microsoft.com/downloads/
   - Выберите "Desktop development with C++"

2. **Windows Driver Kit (WDK) 11**
   - https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk
   - Выберите версию для вашей ОС

3. **Windows SDK** (если не установлен)
   - https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/

## Сборка драйвера

```cmd
REM 1. Откройте Visual Studio
REM 2. File → Open → Project/Solution
REM 3. Выберите: VS-GyroMouse\GyroMouse\GyroMouse.sln

REM 4. В Solution Explorer нажмите правой кнопкой на GyroMouse
REM 5. Properties → Configuration: Release, Platform: x64

REM 6. Build → Build Solution (Ctrl+Shift+B)

REM Результат: gyromouse.sys в папке x64\Release\
```

## Подготовка к установке

```cmd
REM 1. Создайте папку
mkdir C:\GyroMouseDriver

REM 2. Скопируйте туда:
REM    - gyromouse.sys (из папки сборки)
REM    - GyroMouse.inf (из папки проекта)

REM 3. Включите режим тестирования (один раз)
bcdedit /set testsigning on
REM Перезагрузитесь!
```

## Установка драйвера

```cmd
REM Способ 1: Через Device Manager
REM 1. Подключите мышь
REM 2. Откройте Device Manager (devmgmt.msc)
REM 3. Найдите мышь → правой кнопкой → Update driver
REM 4. Browse my computer → C:\GyroMouseDriver
REM 5. Next → Finish

REM Способ 2: Через командную строку (как Administrator)
cd C:\GyroMouseDriver
pnputil /add-driver GyroMouse.inf /install
```

## Проверка установки

```cmd
REM 1. Откройте Device Manager (devmgmt.msc)
REM 2. Найдите "Gyroscopic Mouse Filter Driver v1"
REM 3. Если нет жёлтого восклицательного знака - всё ОК

REM 2. Проверьте логи (скачайте DebugView)
REM    https://learn.microsoft.com/en-us/sysinternals/downloads/debugview
REM    Фильтр: GyroMouseFilter
REM    Подвигайте мышь - должны быть логи
```

## Тестирование

```cmd
REM Скомпилируйте test_driver.cpp в Visual Studio
REM Или используйте готовый exe

REM Блокировать мышь
test_driver.exe on

REM Разблокировать мышь
test_driver.exe off
```

## Если что-то не работает

```cmd
REM Проверьте VID/PID вашей мыши
REM Device Manager → Мышь → Properties → Details → Hardware IDs
REM Обновите GyroMouse.inf с правильными VID/PID

REM Удалить драйвер
pnputil /delete-driver GyroMouse.inf /uninstall

REM Отключить режим тестирования (после всех тестов)
bcdedit /set testsigning off
REM Перезагрузитесь!
```

## Важные файлы

- Драйвер: `VS-GyroMouse\GyroMouse\GyroMouse\driver.c`
- Конфиг: `VS-GyroMouse\GyroMouse\GyroMouse\GyroMouse.inf`
- Заголовок: `VS-GyroMouse\GyroMouse\GyroMouse\driver.h`
- Тест: `test_driver.cpp`
