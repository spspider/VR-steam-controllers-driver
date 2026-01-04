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

// Структура данных от одного контроллера Arduino
#pragma pack(push, 1)
struct ControllerData {
    uint8_t controller_id;      // 0 = левый, 1 = правый
    uint32_t packet_number;     // Номер пакета
    float quat_w, quat_x, quat_y, quat_z;  // Кватернион
    float accel_x, accel_y, accel_z;       // Ускорение
    float gyro_x, gyro_y, gyro_z;          // Угловая скорость
    uint16_t buttons;           // Флаги кнопок
    uint8_t trigger;            // Значение триггера
    uint8_t checksum;           // Контрольная сумма
};
#pragma pack(pop)

static_assert(sizeof(ControllerData) == 49, "ControllerData size mismatch!");

class CVController : public vr::ITrackedDeviceServerDriver {
public:
    CVController(vr::ETrackedControllerRole role, uint8_t expected_id);
    virtual ~CVController() = default;
    
    // ITrackedDeviceServerDriver methods
    virtual vr::EVRInitError Activate(uint32_t unObjectId) override;
    virtual void Deactivate() override;
    virtual void EnterStandby() override;
    virtual void* GetComponent(const char* pchComponentNameAndVersion) override;
    virtual void DebugRequest(const char* pchRequest, char* pchResponseBuffer, uint32_t unResponseBufferSize) override;
    virtual vr::DriverPose_t GetPose() override;
    
    // Custom methods
    void UpdateFromArduino(const ControllerData& data);
    void CheckConnection();
    
private:
    void UpdateButtonState(uint16_t buttons, uint8_t trigger);
    
    vr::ETrackedControllerRole m_role;
    uint8_t m_expectedControllerId;
    vr::TrackedDeviceIndex_t m_unObjectId;
    vr::PropertyContainerHandle_t m_ulPropertyContainer;
    
    std::mutex m_poseMutex;
    vr::DriverPose_t m_pose;
    
    std::mutex m_buttonMutex;
    vr::VRControllerState_t m_controllerState;
    
    std::chrono::steady_clock::time_point m_lastUpdateTime;
};

class NetworkClient {
public:
    NetworkClient(uint16_t port = 5555);
    ~NetworkClient();
    
    bool Start();
    void Stop();
    bool Receive(ControllerData& data);
    
private:
    bool VerifyChecksum(const ControllerData& data);
    
    uint16_t m_port;
    void* m_socket;
    std::atomic<bool> m_running;
};