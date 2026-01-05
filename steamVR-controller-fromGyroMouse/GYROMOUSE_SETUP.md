# GyroMouse + ArUco Tracking - Руководство по установке

## Что изменилось

✅ **УБРАН монопольный захват HID** - мышь продолжит работать в Windows!
✅ **Используется UDP архитектура** - та же что работает в первом проекте
✅ **Добавлен ArUco tracking** - позиция определяется через камеру
✅ **Python скрипт** - читает данные от мыши и отправляет по UDP

## Архитектура

```
[Гироскопическая мышь] --> [Python скрипт] --> [UDP 5555] --> [SteamVR Driver]
                                  ↑
                           [Камера + ArUco]
```

## Установка

### Шаг 1: Соберите драйвер

```bash
cd build
cmake ..
cmake --build . --config Release
```

Файлы будут скопированы в `dist/gyromouse/`

### Шаг 2: Установите в SteamVR

**Вариант A: Автоматически (требует админ прав)**
```bash
cmake --build . --target install_to_steamvr
```

**Вариант B: Вручную**
1. Скопируйте `dist/gyromouse` в:
   ```
   C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\
   ```

### Шаг 3: Зарегистрируйте драйвер

Добавьте в `C:\Users\<Имя>\AppData\Local\openvr\openvrpaths.vrpath`:

```json
{
  "external_drivers": [
    "C:\\Program Files (x86)\\Steam\\steamapps\\common\\SteamVR\\drivers\\gyromouse"
  ]
}
```

### Шаг 4: Установите Python зависимости

```bash
pip install opencv-python opencv-contrib-python scipy numpy hidapi
```

**Важно:** `opencv-contrib-python` нужен для ArUco маркеров!

### Шаг 5: Создайте ArUco маркер

Используйте онлайн генератор:
- https://chev.me/arucogen/
- Выберите: Dictionary 4x4, ID 0, Size 100mm
- Распечатайте и приклейте на жесткую поверхность

## Тестирование

### Тест 1: Без камеры (симулятор)

```bash
python simple_gyromouse_simulator.py
```

Запустите SteamVR - должен появиться контроллер, который двигается по кругу.

### Тест 2: С реальной мышью (без ArUco)

1. Узнайте VID:PID вашей мыши:
   ```bash
   # Windows Device Manager → Мышь → Свойства → Hardware IDs
   # Ищите VID_XXXX&PID_YYYY
   ```

2. Обновите в `gyromouse_aruco_tracker.py`:
   ```python
   gyro_reader = GyroMouseReader(vendor_id=0xВАШ_VID, product_id=0xВАШ_PID)
   ```

3. Запустите:
   ```bash
   python gyromouse_aruco_tracker.py
   ```

### Тест 3: С камерой + ArUco

1. Поместите ArUco маркер (ID=0) в поле зрения камеры
2. Запустите скрипт:
   ```bash
   python gyromouse_aruco_tracker.py
   ```
3. Вы увидите окно с камерой - маркер должен быть обведен
4. Двигайте маркер - контроллер в SteamVR будет следовать за ним!

## Калибровка камеры

Для точного tracking'а нужно откалибровать камеру:

### Способ 1: OpenCV калибровка

```python
import cv2
import numpy as np

# Используйте шахматную доску для калибровки
# https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html
```

### Способ 2: Ручная настройка

В `gyromouse_aruco_tracker.py` обновите:

```python
self.camera_matrix = np.array([
    [fx, 0, cx],   # fx - фокусное расстояние X, cx - центр X
    [0, fy, cy],   # fy - фокусное расстояние Y, cy - центр Y
    [0, 0, 1]
], dtype=float)
```

Примерные значения для веб-камеры 640x480:
- fx, fy = 800 (фокусное расстояние)
- cx = 320, cy = 240 (центр изображения)

## Маппинг кнопок мыши

По умолчанию:
- **Левая кнопка** → Trigger
- **Правая кнопка** → Grip
- **Средняя кнопка** → Application Menu
- **Боковая кнопка** → System Button

Чтобы изменить, отредактируйте в `controller_device.cpp`:

```cpp
void GyroMouseController::UpdateButtonState(uint16_t buttons) {
    // 0x01 = левая, 0x02 = правая, 0x04 = средняя, 0x08 = боковая
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[0],
        (buttons & 0x01) != 0, 0);  // Trigger = левая кнопка
    // ... и т.д.
}
```

## Устранение проблем

### Контроллер не появляется

1. Проверьте логи:
   ```
   C:\Program Files (x86)\Steam\logs\vrserver.txt
   ```
   Ищите строки: `GyroMouse Driver v1.0 INIT`

2. Убедитесь что скрипт запущен и отправляет данные

3. Проверьте firewall - порт 5555 должен быть открыт

### ArUco маркер не детектируется

1. Убедитесь что маркер хорошо освещен
2. Маркер должен быть ровным (на жесткой поверхности)
3. Попробуйте увеличить размер маркера
4. Проверьте что ID маркера = 0

### Мышь не читается

1. Проверьте что библиотека `hidapi` установлена
2. Узнайте правильный VID:PID через Device Manager
3. Если не работает - используйте симулятор для тестирования

### Tracking дергается

1. Откалибруйте камеру правильно
2. Увеличьте размер маркера
3. Уменьшите расстояние до камеры
4. Улучшите освещение

## Следующие шаги

1. ✅ Протестируйте с симулятором
2. ✅ Подключите реальную мышь
3. ✅ Настройте ArUco tracking
4. ✅ Откалибруйте камеру
5. ⚡ Наслаждайтесь VR!

## Дополнительно: Чтение реальных кнопок мыши

Чтобы читать кнопки мыши в Python, добавьте:

```python
from pynput import mouse

class MouseButtonReader:
    def __init__(self):
        self.buttons = 0
        self.listener = mouse.Listener(
            on_click=self.on_click,
            on_release=self.on_release)
        self.listener.start()
    
    def on_click(self, x, y, button, pressed):
        if button == mouse.Button.left:
            self.buttons |= 0x01
        elif button == mouse.Button.right:
            self.buttons |= 0x02
        elif button == mouse.Button.middle:
            self.buttons |= 0x04
    
    def on_release(self, x, y, button, pressed):
        if button == mouse.Button.left:
            self.buttons &= ~0x01
        elif button == mouse.Button.right:
            self.buttons &= ~0x02
        elif button == mouse.Button.middle:
            self.buttons &= ~0x04
    
    def get_buttons(self):
        return self.buttons
```

## Полезные ссылки

- [ArUco маркеры](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html)
- [Калибровка камеры](https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html)
- [OpenVR драйвер документация](https://github.com/ValveSoftware/openvr/wiki/Driver-Documentation)

---

**Примечание:** Если у вас возникли проблемы, сначала протестируйте с `simple_gyromouse_simulator.py` - он должен работать без реального железа!