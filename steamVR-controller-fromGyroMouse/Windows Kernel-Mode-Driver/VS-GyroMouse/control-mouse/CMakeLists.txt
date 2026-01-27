cmake_minimum_required(VERSION 3.10)
project(GyroMouseCapture LANGUAGES CXX)

# Создать исполняемый файл
add_executable(gyro_capture test_driver.cpp)

# Включить поддержку UNICODE (ОБЯЗАТЕЛЬНО!)
target_compile_definitions(gyro_capture PRIVATE 
    UNICODE
    _UNICODE
)

# Подключить библиотеки
target_link_libraries(gyro_capture PRIVATE 
    user32 
    kernel32 
    ws2_32
    hid
    setupapi
)

# Настройки компилятора
target_compile_features(gyro_capture PRIVATE cxx_std_11)

# Для Windows - указать что это консольное приложение
if(WIN32)
    set_target_properties(gyro_capture PROPERTIES
        WIN32_EXECUTABLE FALSE
    )
endif()