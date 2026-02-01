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

// Структура данных от Arduino контроллера
#pragma pack(push, 1)
struct ControllerData {
    uint8_t controller_id;      // 0 = левый, 1 = правый, 2 = HMD
    uint32_t packet_number;     // Номер пакета
    float quat_w, quat_x, quat_y, quat_z;  // Кватернион
    float accel_x, accel_y, accel_z;       // ПОЗИЦИЯ (не ускорение!)
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
    
    // ITrackedDeviceServerDriver методы
    virtual vr::EVRInitError Activate(uint32_t unObjectId) override;
    virtual void Deactivate() override;
    virtual void EnterStandby() override;
    virtual void* GetComponent(const char* pchComponentNameAndVersion) override;
    virtual void DebugRequest(const char* pchRequest, char* pchResponseBuffer, uint32_t unResponseBufferSize) override;
    virtual vr::DriverPose_t GetPose() override;
    
    // Наши методы
    void UpdateFromArduino(const ControllerData& data);
    void CheckConnection();
    void RunFrame(); // КРИТИЧЕСКИ ВАЖНО: Отправляет обновления позы в SteamVR каждый кадр
    
private:
    void UpdateButtonState(uint16_t buttons, uint8_t trigger);
    
    vr::ETrackedControllerRole m_role;
    uint8_t m_expectedControllerId;
    vr::TrackedDeviceIndex_t m_unObjectId;
    vr::PropertyContainerHandle_t m_ulPropertyContainer;
    
    std::mutex m_poseMutex;
    vr::DriverPose_t m_pose;
    
    // Хендлы для компонентов ввода (кнопки, триггер и т.д.)
    vr::VRInputComponentHandle_t m_inputComponentHandles[5]; 
    // [0] = trigger_click
    // [1] = grip
    // [2] = application_menu
    // [3] = system
    // [4] = trigger_value (аналоговое значение)
    
    std::chrono::steady_clock::time_point m_lastUpdateTime;
};

class CVHeadset : public vr::ITrackedDeviceServerDriver {
public:
    CVHeadset();
    virtual ~CVHeadset() = default;
    
    // ITrackedDeviceServerDriver методы
    virtual vr::EVRInitError Activate(uint32_t unObjectId) override;
    virtual void Deactivate() override;
    virtual void EnterStandby() override;
    virtual void* GetComponent(const char* pchComponentNameAndVersion) override;
    virtual void DebugRequest(const char* pchRequest, char* pchResponseBuffer, uint32_t unResponseBufferSize) override;
    virtual vr::DriverPose_t GetPose() override;
    
    // Наши методы
    void UpdateFromNetwork(const ControllerData& data);
    void CheckConnection();
    void RunFrame();
    
private:
    vr::TrackedDeviceIndex_t m_unObjectId;
    std::string m_sSerialNumber;
    std::string m_sModelNumber;
    
    std::mutex m_poseMutex;
    vr::DriverPose_t m_pose;
    
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