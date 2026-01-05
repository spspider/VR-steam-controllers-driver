// src/driver.h
#pragma once

#include <openvr_driver.h>
#include <string>
#include <memory>
#include <thread>
#include <atomic>
#include <mutex>
#include <array>
#include <chrono>
#include <iostream>
#include <cstring>

// Структура данных от гироскопической мыши через UDP
#pragma pack(push, 1)
struct MouseControllerData {
    uint8_t controller_id;      // 0 = левый контроллер (гиромышь)
    uint32_t packet_number;     // Номер пакета
    float quat_w, quat_x, quat_y, quat_z;  // Кватернион из гироскопа
    float pos_x, pos_y, pos_z;  // Позиция из ArUco tracking
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

    // ITrackedDeviceServerDriver методы
    virtual vr::EVRInitError Activate(uint32_t unObjectId) override;
    virtual void Deactivate() override;
    virtual void EnterStandby() override;
    virtual void* GetComponent(const char* pchComponentNameAndVersion) override;
    virtual void DebugRequest(const char* pchRequest, char* pchResponseBuffer, uint32_t unResponseBufferSize) override;
    virtual vr::DriverPose_t GetPose() override;

    // Наши методы
    void UpdateFromMouse(const MouseControllerData& data);
    void CheckConnection();
    void RunFrame(); // КРИТИЧЕСКИ ВАЖНО!

private:
    void UpdateButtonState(uint16_t buttons);

    vr::ETrackedControllerRole m_role;
    uint8_t m_expectedControllerId;
    vr::TrackedDeviceIndex_t m_unObjectId;
    vr::PropertyContainerHandle_t m_ulPropertyContainer;

    std::mutex m_poseMutex;
    vr::DriverPose_t m_pose;

    // Хендлы компонентов ввода
    vr::VRInputComponentHandle_t m_inputComponentHandles[4];
    // [0] = trigger (левая кнопка мыши)
    // [1] = grip (правая кнопка мыши)
    // [2] = application_menu (средняя кнопка)
    // [3] = system (боковая кнопка)

    std::chrono::steady_clock::time_point m_lastUpdateTime;
};

class MouseInputClient {
public:
    MouseInputClient(uint16_t port = 5555);
    ~MouseInputClient();

    bool Start();
    void Stop();
    bool Receive(MouseControllerData& data);

private:
    bool VerifyChecksum(const MouseControllerData& data);

    uint16_t m_port;
    void* m_socket;
    std::atomic<bool> m_running;
};