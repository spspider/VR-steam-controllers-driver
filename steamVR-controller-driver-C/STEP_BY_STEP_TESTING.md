# Пошаговая инструкция для тестирования VR драйвера

## Шаг 1: Подготовка SteamVR

1. **Закройте SteamVR** полностью (если запущен)
2. **Включите Developer Mode**:
   - Откройте SteamVR Settings
   - Перейдите в Developer
   - Поставьте галочку "Enable Developer Mode"
   - Поставьте галочку "Enable Direct Mode" (если есть)

## Шаг 2: Запуск симулятора

```bash
cd d:\MyDocuments\Programming\Projects_C\VR-Driver
python simple_simulator.py
```

**Ожидаемый вывод:**
```
Starting simple controller simulator on 127.0.0.1:5555
Simulating 2 controllers with rotating motion and button presses
Press Ctrl+C to stop
Packet 1: Controllers active, time: 0.1s
Packet 2: Controllers active, time: 0.1s
```

**НЕ ЗАКРЫВАЙТЕ СИМУЛЯТОР!** Оставьте его работать.

## Шаг 3: Запуск SteamVR

1. **Запустите SteamVR** (симулятор должен работать!)
2. **Проверьте логи** в реальном времени:
   - Откройте `%LOCALAPPDATA%\openvr\vrserver.txt`
   - Или используйте команду: `tail -f "%LOCALAPPDATA%\openvr\vrserver.txt"`

**Ожидаемые логи:**
```
[Info] - Driver 'cvdriver' started activation of tracked device with serial number 'CV_Controller_Left'
[Info] - Driver 'cvdriver' started activation of tracked device with serial number 'CV_Controller_Right'
[Info] - Loaded server driver cvdriver
```

**БЕЗ предупреждения:** `Driver cvdriver has no suitable devices.`

## Шаг 4: Проверка контроллеров в SteamVR

### Метод 1: SteamVR Status Window
- Откройте окно статуса SteamVR
- Должны появиться 2 иконки контроллеров
- Зеленые = подключены, серые = отключены

### Метод 2: Developer Console
1. В SteamVR нажмите `Ctrl+Alt+Shift+D`
2. Введите команду: `status`
3. Найдите в списке ваши контроллеры

### Метод 3: SteamVR Settings
1. SteamVR Settings → Controllers
2. "Manage Controller Bindings"
3. Должны быть видны ваши контроллеры

## Шаг 5: Диагностика проблем

### Проблема: "Driver cvdriver has no suitable devices"

**Причины:**
1. Симулятор не запущен ДО запуска SteamVR
2. Порт 5555 заблокирован
3. Драйвер не получает данные

**Решение:**
```bash
# 1. Остановите SteamVR
# 2. Запустите симулятор
python simple_simulator.py

# 3. В другом терминале проверьте порт:
netstat -an | findstr :5555

# 4. Запустите SteamVR заново
```

### Проблема: Контроллеры появляются, но не двигаются

**Добавьте отладку в драйвер:**

```cpp
// В main.cpp, в NetworkThread():
if (m_networkClient && m_networkClient->Receive(data)) {
    std::cout << "Received data for controller " << (int)data.controller_id << std::endl;
    // ... остальной код
}
```

### Проблема: Контроллеры отключаются

**Проверьте:**
1. Симулятор работает непрерывно
2. Контрольные суммы правильные
3. Таймаут соединения (1 секунда в CheckConnection)

## Шаг 6: Дополнительные настройки SteamVR

### Включите null driver (для тестирования без HMD):
1. Найдите файл: `%LOCALAPPDATA%\openvr\openvrpaths.vrpath`
2. Добавьте в config:
```json
{
   "steamvr" : {
      "requireHmd" : false,
      "forcedDriver" : "null"
   }
}
```

### Или создайте файл конфигурации:
Создайте `%LOCALAPPDATA%\openvr\steamvr.vrsettings`:
```json
{
   "steamvr" : {
      "requireHmd" : false,
      "activateMultipleDrivers" : true
   }
}
```

## Шаг 7: Проверка работы

**Если все работает правильно:**
1. Симулятор отправляет пакеты каждые 16мс
2. В логах SteamVR нет предупреждений о "no suitable devices"
3. Контроллеры видны в SteamVR
4. Контроллеры двигаются/вращаются в VR пространстве

## Команды для отладки

```bash
# Проверить порт
netstat -an | findstr :5555

# Мониторить логи SteamVR
tail -f "%LOCALAPPDATA%\openvr\vrserver.txt"

# Проверить процессы SteamVR
tasklist | findstr vr

# Убить все процессы SteamVR
taskkill /f /im vrserver.exe
taskkill /f /im vrcompositor.exe
taskkill /f /im vrmonitor.exe
```

## Ожидаемый результат

При успешной работе вы увидите в VR пространстве два контроллера, которые:
- Вращаются по кругу
- Нажимают кнопки циклично
- Изменяют значение триггера
- Остаются подключенными пока работает симулятор