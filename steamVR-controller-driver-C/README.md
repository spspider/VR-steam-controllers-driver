cvdriver/
├── src/
│   ├── main.cpp              # Точка входа драйвера
│   ├── network_client.cpp    # UDP клиент для получения данных от Arduino
│   ├── controller_device.cpp # Реализация виртуального контроллера
│   └── driver.h              # Заголовочные файлы
├── resources/
│   └── driver.vrdrivermanifest
├── drivers/
│   ├── left_controller/
│   │   └── controller.vrdrivermanifest
│   └── right_controller/
│       └── controller.vrdrivermanifest
└── input/
    └── cvcontroller_profile.json



# Установите C++ инструменты для VS Code
# Установите CMake
# Скачайте OpenVR SDK с GitHub: https://github.com/ValveSoftware/openvr

rm -r build/*
mkdir build && cd build
clear;cmake .. -G "Visual Studio 17 2022" -A x64; cmake --build . --config Release