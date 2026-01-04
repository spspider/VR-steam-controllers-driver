#pragma once

#define NOMINMAX
#define WIN32_LEAN_AND_MEAN

#include <openvr_driver.h>
#include "hid_device.h"
#include <string>
#include <memory>
#include <thread>
#include <atomic>
#include <mutex>
#include <array>
#include <chrono>
#include <iostream>
#include <cstring>

using namespace vr;

// Структура данных от гироскопической мыши
#pragma pack(push, 1)
struct MouseControllerData {
    uint8_t controller_id;      // 0 = левый, 1 = правый
    uint32_t packet_number;     // Номер пакета
    float quat_w, quat_x, quat_y, quat_z;  // Кватернион из гироскопа
    float accel_x, accel_y, accel_z;       // Ускорение
    float gyro_x, gyro_y, gyro_z;          // Угловая скорость
    uint16_t buttons;           // Флаги кнопок мыши
    uint8_t checksum;           // Контрольная сумма
};
#pragma pack(pop)

static_assert(sizeof(MouseControllerData) == 48, "MouseControllerData size mismatch!");

class GyroMouseController : public vr::ITrackedDeviceServerDriver {
public:
    GyroMouseController(vr::ETrackedControllerRole role, uint8_t expected_id);
    virtual ~GyroMouseController() = default;

    // ITrackedDeviceServerDriver methods
    virtual vr::EVRInitError Activate(uint32_t unObjectId) override;
    virtual void Deactivate() override;
    virtual void EnterStandby() override;
    virtual void* GetComponent(const char* pchComponentNameAndVersion) override;
    virtual void DebugRequest(const char* pchRequest, char* pchResponseBuffer, uint32_t unResponseBufferSize) override;
    virtual vr::DriverPose_t GetPose() override;

    // Custom methods
    void UpdateFromMouse(const MouseControllerData& data);
    void CheckConnection();

private:
    void UpdateButtonState(uint16_t buttons);

    vr::ETrackedControllerRole m_role;
    uint8_t m_expectedControllerId;
    vr::TrackedDeviceIndex_t m_unObjectId;
    vr::PropertyContainerHandle_t m_ulPropertyContainer;

    std::mutex m_poseMutex;
    vr::DriverPose_t m_pose;

    std::mutex m_buttonMutex;
    vr::VRControllerState_t m_controllerState;

    // Структура для хранения компонентов ввода
    struct InputComponents {
        vr::VRInputComponentHandle_t systemButton;
        vr::VRInputComponentHandle_t applicationMenu;
        vr::VRInputComponentHandle_t grip;
        vr::VRInputComponentHandle_t trigger;
        vr::VRInputComponentHandle_t skeleton;
    };
    
    InputComponents m_components;

    std::chrono::steady_clock::time_point m_lastUpdateTime;
};

class MouseInputClient {
public:
    // ВАЖНО: Здесь указывается конкретное HID устройство
    // VID_2389 & PID_00A8 - гироскопическая мышь (левый контроллер)
    // Это устройство будет захвачено и использовано как контроллер SteamVR
    MouseInputClient(uint16_t port = 5555);
    ~MouseInputClient();

    bool Start();
    void Stop();
    bool Receive(MouseControllerData& data);

    // Захватить HID устройство гироскопической мыши
    // VID: 0x2389, PID: 0x00A8
    bool CaptureHIDDevice();

private:
    bool VerifyChecksum(const MouseControllerData& data);

    uint16_t m_port;
    void* m_socket;
    std::atomic<bool> m_running;
    std::unique_ptr<HIDDevice> m_hidDevice;  // Гироскопическая мышь VID_2389 & PID_00A8
};