// src/hmd_device_position.cpp
#include "driver.h"

using namespace vr;

CVHeadset::CVHeadset() : m_unObjectId(k_unTrackedDeviceIndexInvalid) {
    m_sSerialNumber = "CV_HMD_001";
    m_sModelNumber = "CV HMD v1.0";
    
    memset(&m_pose, 0, sizeof(m_pose));
    m_pose.poseIsValid = false;
    m_pose.result = TrackingResult_Uninitialized;
    m_pose.deviceIsConnected = false;
    
    m_pose.qRotation.w = 1.0;
    m_pose.qRotation.x = 0.0;
    m_pose.qRotation.y = 0.0;
    m_pose.qRotation.z = 0.0;
    
    m_pose.vecPosition[0] = 0.0;
    m_pose.vecPosition[1] = 1.6;
    m_pose.vecPosition[2] = 0.0;
    
    m_lastUpdateTime = std::chrono::steady_clock::now();
}

vr::EVRInitError CVHeadset::Activate(uint32_t unObjectId) {
    m_unObjectId = unObjectId;
    PropertyContainerHandle_t props = VRProperties()->TrackedDeviceToPropertyContainer(m_unObjectId);
    
    VRProperties()->SetStringProperty(props, Prop_TrackingSystemName_String, "cvtracking");
    VRProperties()->SetStringProperty(props, Prop_ModelNumber_String, m_sModelNumber.c_str());
    VRProperties()->SetStringProperty(props, Prop_SerialNumber_String, m_sSerialNumber.c_str());
    VRProperties()->SetStringProperty(props, Prop_RenderModelName_String, "generic_hmd");
    
    VRProperties()->SetBoolProperty(props, Prop_WillDriftInYaw_Bool, false);
    VRProperties()->SetBoolProperty(props, Prop_DeviceIsWireless_Bool, true);
    VRProperties()->SetBoolProperty(props, Prop_DeviceIsCharging_Bool, false);
    VRProperties()->SetFloatProperty(props, Prop_DeviceBatteryPercentage_Float, 1.0f);
    
    VRProperties()->SetFloatProperty(props, Prop_UserIpdMeters_Float, 0.063f);
    VRProperties()->SetFloatProperty(props, Prop_UserHeadToEyeDepthMeters_Float, 0.015f);
    VRProperties()->SetFloatProperty(props, Prop_DisplayFrequency_Float, 90.0f);
    VRProperties()->SetFloatProperty(props, Prop_SecondsFromVsyncToPhotons_Float, 0.011f);
    
    VRDriverLog()->Log("CVHeadset: HMD activated successfully");
    return VRInitError_None;
}

void CVHeadset::Deactivate() {
    m_unObjectId = k_unTrackedDeviceIndexInvalid;
}

void CVHeadset::EnterStandby() {}

void* CVHeadset::GetComponent(const char* pchComponentNameAndVersion) {
    return nullptr;
}

void CVHeadset::DebugRequest(const char* pchRequest, char* pchResponseBuffer, uint32_t unResponseBufferSize) {
    if (unResponseBufferSize >= 1) {
        pchResponseBuffer[0] = 0;
    }
}

vr::DriverPose_t CVHeadset::GetPose() {
    std::lock_guard<std::mutex> lock(m_poseMutex);
    return m_pose;
}

void CVHeadset::UpdateFromNetwork(const ControllerData& data) {
    if (data.controller_id != 2) {
        return;
    }
    
    {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        
        // Обновляем ориентацию (получаем от ALVR)
        m_pose.qRotation.w = data.quat_w;
        m_pose.qRotation.x = data.quat_x;
        m_pose.qRotation.y = data.quat_y;
        m_pose.qRotation.z = data.quat_z;
        
        // Обновляем позицию в мировом пространстве (X, Y, Z)
        // accel_x/y/z содержит координаты позиции, полученные от Hub
        m_pose.vecPosition[0] = data.accel_x;
        m_pose.vecPosition[1] = data.accel_y;
        m_pose.vecPosition[2] = data.accel_z;
        
        // Обновляем угловую скорость из гироскопа
        m_pose.vecAngularVelocity[0] = data.gyro_x;
        m_pose.vecAngularVelocity[1] = data.gyro_y;
        m_pose.vecAngularVelocity[2] = data.gyro_z;
        
        // Обнуляем линейную скорость (используем прямое позиционирование)
        m_pose.vecVelocity[0] = 0.0;
        m_pose.vecVelocity[1] = 0.0;
        m_pose.vecVelocity[2] = 0.0;
        
        m_pose.poseIsValid = true;
        m_pose.result = TrackingResult_Running_OK;
        m_pose.deviceIsConnected = true;
        
        m_lastUpdateTime = std::chrono::steady_clock::now();
        
        // ОТЛАДОЧНЫЙ ВЫВОД каждые 100 обновлений
        static int updateCounter = 0;
        updateCounter++;
        if (updateCounter % 100 == 0) {
            char logMsg[512];
            snprintf(logMsg, sizeof(logMsg), 
                "CVHeadset: Pos(%.3f, %.3f, %.3f) Quat(%.3f, %.3f, %.3f, %.3f)",
                m_pose.vecPosition[0], m_pose.vecPosition[1], m_pose.vecPosition[2],
                m_pose.qRotation.w, m_pose.qRotation.x, m_pose.qRotation.y, m_pose.qRotation.z);
            VRDriverLog()->Log(logMsg);
        }
    }
}

void CVHeadset::CheckConnection() {
    auto now = std::chrono::steady_clock::now();
    float time_since_update = std::chrono::duration<float>(now - m_lastUpdateTime).count();
    
    if (time_since_update > 1.0f) {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        m_pose.deviceIsConnected = false;
        m_pose.poseIsValid = false;
    }
}

void CVHeadset::RunFrame() {
    // КРИТИЧЕСКИ ВАЖНО! Отправляем обновления позы в SteamVR каждый кадр
    if (m_unObjectId != k_unTrackedDeviceIndexInvalid) {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        VRServerDriverHost()->TrackedDevicePoseUpdated(m_unObjectId, m_pose, sizeof(DriverPose_t));
    }
}