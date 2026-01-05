cmake_minimum_required(VERSION 3.10)
project(gyromouse_driver)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Path to OpenVR SDK
set(OPENVR_SDK_PATH "openvr/")

include_directories(${OPENVR_SDK_PATH}/headers)
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/src)

link_directories(${OPENVR_SDK_PATH}/lib/win64)

# Create driver library
add_library(driver_gyromouse SHARED 
    src/main.cpp
    src/controller_device.cpp
    src/mouse_input_client.cpp
)

# Link OpenVR
target_link_libraries(driver_gyromouse openvr_api)

# On Windows link Winsock
if(WIN32)
    target_link_libraries(driver_gyromouse ws2_32)
endif()

# Build only - no file copying
# Use install_gyromouse.bat for installation