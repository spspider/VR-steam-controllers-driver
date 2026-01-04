cmake_minimum_required(VERSION 3.10)
project(gyromouse_driver)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /EHsc /W0")

# Путь к OpenVR SDK
set(OPENVR_SDK_PATH "openvr/")

include_directories(${OPENVR_SDK_PATH}/headers)
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/src)


link_directories(${OPENVR_SDK_PATH}/lib/win64)

# Создаем библиотеку драйвера
add_library(driver_gyromouse SHARED 
    src/main.cpp
    src/device_provider.cpp
    src/gyro_controller.cpp
)

# Линкуем OpenVR
target_link_libraries(driver_gyromouse openvr_api)

# На Windows нужно подключить Winsock и HID API
if(WIN32)
    target_link_libraries(driver_gyromouse ws2_32 setupapi hid)
endif()

# === ЛОКАЛЬНЫЙ ПУТЬ для тестирования ===
# Копируем в папку dist в проекте
set(DRIVER_DIST_PATH "${CMAKE_SOURCE_DIR}/dist/gyromouse")

# Создание структуры директорий
add_custom_command(TARGET driver_gyromouse PRE_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "${DRIVER_DIST_PATH}/bin/win64"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${DRIVER_DIST_PATH}/resources"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${DRIVER_DIST_PATH}/resources/input"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${DRIVER_DIST_PATH}/resources/rendermodels"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${DRIVER_DIST_PATH}/resources/rendermodels/gyromouse_controller"
    COMMENT "Creating driver directory structure"
)

# === Копирование DLL ===
add_custom_command(TARGET driver_gyromouse POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        "$<TARGET_FILE:driver_gyromouse>"
        "${DRIVER_DIST_PATH}/bin/win64/"
    COMMENT "Copying DLL to dist folder"
)

# === Копирование driver.vrdrivermanifest ===
add_custom_command(TARGET driver_gyromouse POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        "${CMAKE_SOURCE_DIR}/resources/driver.vrdrivermanifest"
        "${DRIVER_DIST_PATH}/"
    COMMENT "Copying driver manifest"
)

# === Копирование input профиля ===
add_custom_command(TARGET driver_gyromouse POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        "${CMAKE_SOURCE_DIR}/resources/input/gyromouse_profile.json"
        "${DRIVER_DIST_PATH}/resources/input/"
    COMMENT "Copying input profile"
)

# Создание простой OBJ модели для тестирования
add_custom_command(TARGET driver_gyromouse POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Creating OBJ model file"
    COMMENT "Creating simple OBJ model"
)

# Создаем OBJ файл через file(WRITE)
file(WRITE "${CMAKE_SOURCE_DIR}/dist/gyromouse/resources/rendermodels/gyromouse_controller/gyromouse_controller.obj"
"# Simple cube model for testing
v -0.05 -0.05 -0.05
v 0.05 -0.05 -0.05
v -0.05 0.05 -0.05
v 0.05 0.05 -0.05
v -0.05 -0.05 0.05
v 0.05 -0.05 0.05
v -0.05 0.05 0.05
v 0.05 0.05 0.05
f 1 2 3
f 3 2 4
f 5 6 7
f 7 6 8
f 1 2 5
f 5 2 6
f 3 4 7
f 7 4 8
f 2 4 6
f 6 4 8
f 1 3 5
f 5 3 7
")

# === Опционально: скрипт для копирования в SteamVR (требует админских прав) ===
if(WIN32)
    add_custom_target(copy_to_steamvr
        COMMAND powershell -Command 
            "if (Test-Path 'C:/Program Files (x86)/Steam/steamapps/common/SteamVR/drivers/gyromouse') {
                Remove-Item -Recurse -Force 'C:/Program Files (x86)/Steam/steamapps/common/SteamVR/drivers/gyromouse'
            }"
        COMMAND powershell -Command 
            "Copy-Item -Recurse '${DRIVER_DIST_PATH}' 'C:/Program Files (x86)/Steam/steamapps/common/SteamVR/drivers/'"
        COMMENT "Copying driver to SteamVR (requires admin rights)"
        DEPENDS driver_gyromouse
    )
endif()