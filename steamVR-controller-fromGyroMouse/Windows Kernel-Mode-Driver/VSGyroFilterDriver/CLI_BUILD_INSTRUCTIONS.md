# Инструкция для работы с CLI компиляции драйвера

## Быстрый старт

### 1. Открыть PowerShell с правами администратора

```powershell
powershell
```

### 2. Инициализировать переменные окружения Visual Studio

```cmd
cmd /k "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"
```

### 3. Перейти в директорию проекта

```cmd
cd /d "d:\MyDocuments\Programming\Projects_C\VR-Driver\steamVR-controller-fromGyroMouse\Windows Kernel-Mode-Driver\VSGyroFilterDriver\GyroFilterDriver"
```

### 4. Скомпилировать проект

```cmd
msbuild GyroFilterDriver.sln /p:Configuration=Release /p:Platform=x64 /v:minimal
```

## Полная команда в одну строку

```cmd
cd /d "d:\MyDocuments\Programming\Projects_C\VR-Driver\steamVR-controller-fromGyroMouse\Windows Kernel-Mode-Driver\VSGyroFilterDriver\GyroFilterDriver" && "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat" && msbuild GyroFilterDriver.sln /p:Configuration=Release /p:Platform=x64 /v:minimal
```

## Результат компиляции

После успешной компиляции файлы находятся в:
- **Драйвер**: `x64\Release\GyroFilterDriver.sys`
- **INF файл**: `GyroFilterDriver.inf`

## Параметры msbuild

- `/p:Configuration=Release` - конфигурация Release (оптимизированная)
- `/p:Platform=x64` - платформа x64
- `/v:minimal` - минимальный вывод (можно изменить на `/v:normal` или `/v:detailed`)

## Очистка проекта

```cmd
msbuild GyroFilterDriver.sln /p:Configuration=Release /p:Platform=x64 /t:Clean
```

## Отладка компиляции

Если нужна подробная информация об ошибках:

```cmd
msbuild GyroFilterDriver.sln /p:Configuration=Release /p:Platform=x64 /v:detailed
```
