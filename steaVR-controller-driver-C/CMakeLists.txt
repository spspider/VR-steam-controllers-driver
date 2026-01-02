cmake_minimum_required(VERSION 3.10)
project(cvdriver)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Путь к OpenVR SDK
set(OPENVR_SDK_PATH "openvr/")

include_directories(${OPENVR_SDK_PATH}/headers)
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/src)

link_directories(${OPENVR_SDK_PATH}/lib/win64)

# Создаем библиотеку драйвера
add_library(driver_cvdriver SHARED 
    src/main.cpp
    src/network_client.cpp
    src/controller_device.cpp
)

# Линкуем OpenVR
target_link_libraries(driver_cvdriver openvr_api)

# На Windows нужно подключить Winsock
if(WIN32)
    target_link_libraries(driver_cvdriver ws2_32)
endif()

# === Путь к SteamVR драйверу ===
set(STEAMVR_DRIVER_PATH 
    "C:/Program Files (x86)/Steam/steamapps/common/SteamVR/drivers/cvdriver"
)

# === Копирование DLL ===
add_custom_command(TARGET driver_cvdriver POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory
        "${STEAMVR_DRIVER_PATH}/bin/win64"
    COMMAND ${CMAKE_COMMAND} -E copy
        "$<TARGET_FILE:driver_cvdriver>"
        "${STEAMVR_DRIVER_PATH}/bin/win64/"
)

# === Копирование driver.vrdrivermanifest ===
add_custom_command(TARGET driver_cvdriver POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory
        "${STEAMVR_DRIVER_PATH}/resources"
    COMMAND ${CMAKE_COMMAND} -E copy
        "${CMAKE_CURRENT_SOURCE_DIR}/resources/driver.vrdrivermanifest"
        "${STEAMVR_DRIVER_PATH}/resources/"
)