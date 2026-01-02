// src/controller_device.cpp
#include "driver.h"
#include <cmath>
#include <iostream>

using namespace vr;

CVController::CVController(vr::ETrackedControllerRole role, uint8_t expected_id)
    : m_role(role), m_expectedControllerId(expected_id),
      m_unObjectId(0), m_ulPropertyContainer(0) {
    
    memset(&m_pose, 0, sizeof(m_pose));
    m_pose.poseIsValid = true;
    m_pose.result = TrackingResult_Running_OK;
    m_pose.deviceIsConnected = true;
    
    m_pose.qWorldFromDriverRotation = {1, 0, 0, 0};
    m_pose.qDriverFromHeadRotation = {1, 0, 0, 0};
    
    // Начальная позиция (примерно на уровне груди)
    m_pose.vecPosition[0] = (role == TrackedControllerRole_LeftHand) ? -0.2f : 0.2f;
    m_pose.vecPosition[1] = 1.0f;
    m_pose.vecPosition[2] = -0.3f;
    
    m_pose.qRotation = {1, 0, 0, 0};
    
    m_lastUpdateTime = std::chrono::steady_clock::now();
}

vr::EVRInitError CVController::Activate(uint32_t unObjectId) {
    VRDriverLog()->Log("CVController: Activate called!");
    
    m_unObjectId = unObjectId;
    m_ulPropertyContainer = VRProperties()->TrackedDeviceToPropertyContainer(unObjectId);
    
    VRProperties()->SetStringProperty(m_ulPropertyContainer, 
        Prop_ModelNumber_String, "CV_Controller_MK1");
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_RenderModelName_String, 
        "{cvdriver}/rendermodels/cv_controller");
    
    VRProperties()->SetUint64Property(m_ulPropertyContainer, 
        Prop_CurrentUniverseId_Uint64, 2);
    
    VRProperties()->SetInt32Property(m_ulPropertyContainer, 
        Prop_ControllerRoleHint_Int32, m_role);
    
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_ControllerType_String, "cvcontroller");
    
    VRProperties()->SetStringProperty(m_ulPropertyContainer, 
        Prop_InputProfilePath_String, "{cvdriver}/input/cvcontroller_profile.json");
    
    VRDriverLog()->Log("CVController: Activate completed successfully!");
    return VRInitError_None;
}

void CVController::Deactivate() {
    m_unObjectId = 0;
}

void CVController::EnterStandby() {}

void* CVController::GetComponent(const char* pchComponentNameAndVersion) {
    if (strstr(pchComponentNameAndVersion, "IVRControllerComponent") != nullptr) {
        return static_cast<void*>(this);
    }
    return nullptr;
}

void CVController::DebugRequest(const char* pchRequest, char* pchResponseBuffer, 
                         uint32_t unResponseBufferSize) {
    if (unResponseBufferSize >= 1) {
        pchResponseBuffer[0] = 0;
    }
}

vr::DriverPose_t CVController::GetPose() {
    std::lock_guard<std::mutex> lock(m_poseMutex);
    return m_pose;
}

void CVController::UpdateFromArduino(const ControllerData& data) {
    if (data.controller_id != m_expectedControllerId) {
        return;
    }
    
    {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        
        m_pose.qRotation.w = data.quat_w;
        m_pose.qRotation.x = data.quat_x;
        m_pose.qRotation.y = data.quat_y;
        m_pose.qRotation.z = data.quat_z;
        
        static auto last_time = std::chrono::steady_clock::now();
        auto now = std::chrono::steady_clock::now();
        float dt = std::chrono::duration<float>(now - last_time).count();
        last_time = now;
        
        vr::HmdVector3d_t world_accel = {data.accel_x, data.accel_y, data.accel_z};
        
        m_pose.vecVelocity[0] += world_accel.v[0] * dt;
        m_pose.vecVelocity[1] += world_accel.v[1] * dt;
        m_pose.vecVelocity[2] += world_accel.v[2] * dt;
        
        m_pose.vecVelocity[0] *= 0.95f;
        m_pose.vecVelocity[1] *= 0.95f;
        m_pose.vecVelocity[2] *= 0.95f;
        
        m_pose.vecPosition[0] += m_pose.vecVelocity[0] * dt;
        m_pose.vecPosition[1] += m_pose.vecVelocity[1] * dt;
        m_pose.vecPosition[2] += m_pose.vecVelocity[2] * dt;
        
        m_pose.vecAngularVelocity[0] = data.gyro_x;
        m_pose.vecAngularVelocity[1] = data.gyro_y;
        m_pose.vecAngularVelocity[2] = data.gyro_z;
        
        m_pose.poseIsValid = true;
        m_pose.result = TrackingResult_Running_OK;
        m_pose.deviceIsConnected = true;
        
        m_lastUpdateTime = now;
    }
    
    {
        std::lock_guard<std::mutex> lock(m_buttonMutex);
        UpdateButtonState(data.buttons, data.trigger);
    }
}

void CVController::CheckConnection() {
    auto now = std::chrono::steady_clock::now();
    float time_since_update = std::chrono::duration<float>(now - m_lastUpdateTime).count();
    
    if (time_since_update > 1.0f) {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        m_pose.deviceIsConnected = false;
        m_pose.poseIsValid = false;
    }
}

void CVController::UpdateButtonState(uint16_t buttons, uint8_t trigger) {
    memset(&m_controllerState, 0, sizeof(m_controllerState));
    
    if (buttons & 0x01) {
        m_controllerState.ulButtonPressed |= ButtonMaskFromId(k_EButton_SteamVR_Trigger);
    }
    if (buttons & 0x02) {
        m_controllerState.ulButtonPressed |= ButtonMaskFromId(k_EButton_Grip);
    }
    if (buttons & 0x04) {
        m_controllerState.ulButtonPressed |= ButtonMaskFromId(k_EButton_ApplicationMenu);
    }
    if (buttons & 0x08) {
        m_controllerState.ulButtonPressed |= ButtonMaskFromId(k_EButton_System);
    }
    
    m_controllerState.rAxis[1].x = trigger / 255.0f;
    m_controllerState.rAxis[0].x = 0.0f;
    m_controllerState.rAxis[0].y = 0.0f;
    m_controllerState.rAxis[2].x = 0.0f;
    m_controllerState.rAxis[2].y = 0.0f;
}