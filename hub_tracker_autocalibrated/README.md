# VR Tracking Hub - Центральный хаб для трекинга VR контроллеров

## Описание

Python приложение-хаб, которое объединяет данные от нескольких источников трекинга и отправляет их в SteamVR драйвер.

### Поддерживаемые источники данных:

1. **Android телефоны с ArUco маркерами** (несколько устройств)
   - Порт: 5554
   - Маркер ID 0 = левый контроллер
   - Маркер ID 1 = правый контроллер
   - Маркер ID 2 = HMD (шлем)

2. **Гироскопические мыши** (до 2 устройств)
   - Порт: 5556
   - Кнопка 1 (левая) = левый контроллер
   - Кнопка 2 (правая) = правый контроллер

3. **Веб-камера с ArUco маркерами** (опционально)
   - Будет добавлено в будущем

### Выход:
- **SteamVR драйвер**: порт 5555

---

## Установка

### Требования:
```bash
pip install numpy tkinter
```

### Структура портов:

```
┌─────────────────────────────────────────┐
│         VR Tracking Hub (Python)        │
│                                         │
│  Входы:                                 │
│  ├─ Android (port 5554)                 │
│  └─ Gyro Mouse (port 5556)              │
│                                         │
│  Выход:                                 │
│  └─ SteamVR Driver (port 5555)          │
└─────────────────────────────────────────┘
```

---

## Настройка Android приложения

### 1. Обновите файл `ControllerUDPSender.kt`:

Замените строку порта:
```kotlin
private val hubPort: Int = 5554  // Отправка на хаб вместо драйвера
```

### 2. В `MainActivity.kt` обновите подключение:

```kotlin
connectButton.setOnClickListener {
    val ip = ipAddressInput.text.toString()
    if (ip.isNotEmpty()) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                udpSender?.close()
                udpSender = ControllerUDPSender(ip, 5554)  // Подключение к хабу
                isConnected = true

                runOnUiThread {
                    Toast.makeText(this@MainActivity, 
                        "Connected to VR Hub at $ip:5554", 
                        Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    Toast.makeText(this@MainActivity, 
                        "Hub connection failed: ${e.message}", 
                        Toast.LENGTH_SHORT).show()
                }
            }
        }
    }
}
```

### 3. ArUco маркеры для Android:

- **ID 0**: Левый контроллер (прикрепите к одному телефону)
- **ID 1**: Правый контроллер (прикрепите к другому телефону)
- **ID 2**: HMD шлем (опционально, для трекинга головы)

Генерация маркеров:
```python
import cv2
import cv2.aruco as aruco

# Генерация словаря
dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)

# Генерация маркеров ID 0, 1, 2
for marker_id in [0, 1, 2]:
    marker_image = aruco.generateImageMarker(dictionary, marker_id, 200)
    cv2.imwrite(f'aruco_marker_{marker_id}.png', marker_image)
    print(f"Generated marker ID {marker_id}")

print("Распечатайте маркеры и наклейте на телефоны/шлем")
```

---

## Настройка гироскопических мышей

### Для работы двух мышей одновременно:

1. **Запустите два экземпляра `mouse_hook.exe`**

2. **Первый экземпляр** (для левого контроллера):
   - Выберите первую гиромышь
   - Используйте левую кнопку мыши как trigger

3. **Второй экземпляр** (для правого контроллера):
   - Выберите вторую гиромышь
   - Используйте правую кнопку мыши как trigger

### Изменение в mouse_hook.cpp для поддержки выбора контроллера:

Добавьте в начало main():
```cpp
int main() {
    std::cout << "Select controller type:\n";
    std::cout << "0 - Left controller (use left button)\n";
    std::cout << "1 - Right controller (use right button)\n";
    int controllerType = 0;
    std::cin >> controllerType;
    
    // ... остальной код
    
    // В WndProc при отправке данных:
    char udpBuffer[64];
    int len = sprintf_s(udpBuffer, sizeof(udpBuffer),
        "MOUSE:%d,%d,%u,%llu,%d",  // Добавлен controller_type в конец
        (int)mouse.lLastX,
        (int)mouse.lLastY,
        (mouse.ulButtons & RI_MOUSE_BUTTON_1_DOWN) ? 1 :
        (mouse.ulButtons & RI_MOUSE_BUTTON_2_DOWN) ? 2 : 0,
        GetTickCount64(),
        controllerType);  // Передаем тип контроллера
```

---

## Запуск системы

### Порядок запуска:

1. **Запустите SteamVR драйвер** (если еще не запущен)

2. **Запустите VR Tracking Hub**:
   ```bash
   python vr_tracking_hub.py
   ```

3. **Нажмите "Start Hub"** в GUI

4. **Подключите источники данных**:
   - Запустите Android приложения на телефонах
   - Введите IP вашего ПК и нажмите "Connect"
   - Запустите mouse_hook.exe для гиромышей

5. **Калибровка**:
   - Поместите контроллер в желаемую начальную позицию
   - Нажмите "Calibrate" для соответствующего контроллера в хабе

---

## Использование GUI хаба

### Основное окно:

```
╔════════════════════════════════════════════════╗
║         VR Tracking Hub                        ║
╠════════════════════════════════════════════════╣
║  Controllers Status:                           ║
║  ┌───────────────────────────────────────┐    ║
║  │ LEFT Controller    [Active]            │    ║
║  │ Pos: (0.15, 0.20, -0.50)               │    ║
║  │ Source: android:192.168.1.100          │    ║
║  │ [Calibrate] [Reset]                    │    ║
║  ├───────────────────────────────────────┤    ║
║  │ RIGHT Controller   [Active]            │    ║
║  │ Pos: (-0.15, 0.20, -0.50)              │    ║
║  │ Source: gyromouse:127.0.0.1            │    ║
║  │ [Calibrate] [Reset]                    │    ║
║  ├───────────────────────────────────────┤    ║
║  │ HMD (Head)        [Inactive]           │    ║
║  │ Pos: N/A                               │    ║
║  │ Source: none                           │    ║
║  │ [Calibrate] [Reset]                    │    ║
║  └───────────────────────────────────────┘    ║
╠════════════════════════════════════════════════╣
║  Statistics:                                   ║
║  Android: 15,420 | Gyro: 8,234 | SteamVR: 23,654║
║  Errors: 0                                     ║
╠════════════════════════════════════════════════╣
║  [Start Hub] [Stop Hub] [Clear Log]            ║
╠════════════════════════════════════════════════╣
║  Log:                                          ║
║  [10:23:45.123] [INFO] Hub started            ║
║  [10:23:45.456] [INFO] LEFT from 192.168.1.100║
║  [10:23:45.789] [INFO] Calibrated LEFT        ║
╚════════════════════════════════════════════════╝
```

---

## Калибровка

### Автоматическая калибровка позиции:

1. Установите контроллер в желаемую "нулевую" позицию
2. Нажмите кнопку "Calibrate" для этого контроллера
3. Текущая позиция будет установлена как (0, 0, 0)

### Сброс калибровки:

- Нажмите "Reset" для сброса калибровки к значениям по умолчанию

---

## Использование ArUco маркера для HMD (шлема)

### ДА, можно использовать ArUco маркер для трекинга головы!

**Преимущества:**
- Дешевый полный трекинг 6DoF
- Не требует дополнительных датчиков

**Как это сделать:**

1. **Распечатайте маркер ID 2** (для HMD):
   ```python
   import cv2
   import cv2.aruco as aruco
   
   dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
   marker_image = aruco.generateImageMarker(dictionary, 2, 200)
   cv2.imwrite('aruco_hmd_marker.png', marker_image)
   ```

2. **Прикрепите маркер к шлему**:
   - Разместите маркер сверху или сбоку шлема
   - Убедитесь, что камера может его видеть

3. **Настройте Android приложение**:
   - Используйте третий телефон с камерой
   - Или модифицируйте код для отправки данных HMD

4. **В SteamVR драйвере добавьте HMD устройство**:

```cpp
// В driver.h добавьте класс для HMD
class CVHeadset : public ITrackedDeviceServerDriver {
    // Аналогично CVController, но для HMD
    // TrackedDeviceClass_HMD вместо TrackedDeviceClass_Controller
};

// В main.cpp:
virtual vr::EVRInitError Init(vr::IVRDriverContext* pDriverContext) override {
    // ... существующий код
    
    // Добавить HMD
    m_headset = std::make_unique<CVHeadset>();
    bool hmdAdded = VRServerDriverHost()->TrackedDeviceAdded(
        "CV_HMD", 
        TrackedDeviceClass_HMD, 
        m_headset.get());
    
    // ...
}

// В NetworkThread обрабатывать controller_id == 2
if (data.controller_id == 2 && m_headset) {
    m_headset->UpdateFromNetwork(data);
}
```

---

## Troubleshooting

### Проблема: Контроллеры не видны в SteamVR

**Решение:**
1. Убедитесь, что хаб получает данные (проверьте лог)
2. Проверьте, что SteamVR драйвер запущен
3. Проверьте firewall - порт 5555 должен быть открыт

### Проблема: Android не подключается к хабу

**Решение:**
1. Убедитесь, что телефон и ПК в одной сети
2. Проверьте IP адрес ПК: `ipconfig` (Windows) или `ifconfig` (Linux)
3. Проверьте firewall - порт 5554 должен быть открыт

### Проблема: Гиромышь не отправляет данные

**Решение:**
1. Проверьте, что mouse_hook.exe запущен с правами администратора
2. Убедитесь, что порт 5556 открыт
3. Проверьте выбор правильной мыши в конфиге

### Проблема: Позиция контроллера неправильная

**Решение:**
1. Выполните калибровку через GUI хаба
2. Проверьте параметры камеры в ArUcoTransform.kt
3. Убедитесь, что маркер хорошо виден камере

---

## Расширенная конфигурация

### Изменение частоты отправки в SteamVR:

В `vr_tracking_hub.py`:
```python
# По умолчанию 90 Hz
time.sleep(1.0 / 90.0)

# Для 120 Hz:
time.sleep(1.0 / 120.0)
```

### Настройка чувствительности гиромыши:

В `vr_tracking_hub.py` в методе `process_gyro_mouse_packet`:
```python
# По умолчанию
sensitivity = 0.001

# Увеличить чувствительность:
sensitivity = 0.002

# Уменьшить чувствительность:
sensitivity = 0.0005
```

---

## Лицензия

MIT License

## Поддержка

При возникновении проблем создайте issue с:
- Логом из хаба
- Версией SteamVR
- Описанием проблемы

---

**Примечание:** Для лучшего трекинга убедитесь, что маркеры хорошо освещены и видны камере без препятствий.