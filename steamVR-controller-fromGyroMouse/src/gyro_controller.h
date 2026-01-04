#pragma once

#include "openvr_driver.h"
#include <string>
#include <atomic>
#include <thread>
#include <chrono>
#include <mutex>

struct MouseControllerData {
    uint8_t controller_id;
    uint32_t packet_number;
    float quat_w, quat_x, quat_y, quat_z;
    float accel_x, accel_y, accel_z;
    float gyro_x, gyro_y, gyro_z;
    uint16_t buttons;
    uint8_t checksum;
};

class GyroMouseController : public vr::ITrackedDeviceServerDriver
{
public:
    GyroMouseController(vr::ETrackedControllerRole role, uint8_t controller_id);

    // ITrackedDeviceServerDriver interface
    vr::EVRInitError Activate(uint32_t unObjectId) override;
    void Deactivate() override;
    void EnterStandby() override;
    void* GetComponent(const char* pchComponentNameAndVersion) override;
    void DebugRequest(const char* pchRequest, char* pchResponseBuffer, uint32_t unResponseBufferSize) override;
    vr::DriverPose_t GetPose() override;

    // Custom methods
    const std::string& GetSerialNumber() const;
    void RunFrame();
    void ProcessEvent(const vr::VREvent_t& event);
    void UpdateFromMouse(const MouseControllerData& data);

private:
    void PoseUpdateThread();

    vr::ETrackedControllerRole role_;
    uint8_t controller_id_;
    std::string serial_number_;
    
    std::atomic<vr::TrackedDeviceIndex_t> device_index_;
    std::atomic<bool> is_active_;
    
    vr::DriverPose_t pose_;
    std::mutex pose_mutex_;
    
    // Input components
    vr::VRInputComponentHandle_t system_button_;
    vr::VRInputComponentHandle_t menu_button_;
    vr::VRInputComponentHandle_t grip_button_;
    vr::VRInputComponentHandle_t trigger_button_;
    vr::VRInputComponentHandle_t haptic_;
    
    std::thread pose_thread_;
    std::chrono::steady_clock::time_point last_update_;
};