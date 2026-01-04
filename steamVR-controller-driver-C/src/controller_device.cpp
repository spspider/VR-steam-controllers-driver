// src/controller_device.cpp
#include "driver.h"
#include <cmath>
#include <iostream>

using namespace vr;

CVController::CVController(vr::ETrackedControllerRole role, uint8_t expected_id)
    : m_role(role), m_expectedControllerId(expected_id),
      m_unObjectId(vr::k_unTrackedDeviceIndexInvalid), m_ulPropertyContainer(0) {
    
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
    
    // Инициализируем хендлы компонентов ввода
    memset(m_inputComponentHandles, 0, sizeof(m_inputComponentHandles));
}

vr::EVRInitError CVController::Activate(uint32_t unObjectId) {
    VRDriverLog()->Log("CVController: Activate called!");
    
    m_unObjectId = unObjectId;
    m_ulPropertyContainer = VRProperties()->TrackedDeviceToPropertyContainer(unObjectId);
    
    // Основные свойства
    VRProperties()->SetStringProperty(m_ulPropertyContainer, 
        Prop_ModelNumber_String, "CV_Controller_MK1");
    
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_SerialNumber_String, 
        m_role == TrackedControllerRole_LeftHand ? "CV_LEFT_001" : "CV_RIGHT_001");
    
    // Используем модель контроллера Vive как временную
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_RenderModelName_String, "vr_controller_vive_1_5");
    
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_ManufacturerName_String, "CVDriver");
    
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_TrackingSystemName_String, "cvtracking");
    
    VRProperties()->SetUint64Property(m_ulPropertyContainer, 
        Prop_CurrentUniverseId_Uint64, 2);
    
    VRProperties()->SetInt32Property(m_ulPropertyContainer, 
        Prop_ControllerRoleHint_Int32, m_role);
    
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_ControllerType_String, "vive_controller");
    
    VRProperties()->SetStringProperty(m_ulPropertyContainer, 
        Prop_InputProfilePath_String, "{cvdriver}/input/cvcontroller_profile.json");
    
    VRProperties()->SetInt32Property(m_ulPropertyContainer,
        Prop_DeviceClass_Int32, TrackedDeviceClass_Controller);
    
    VRProperties()->SetInt32Property(m_ulPropertyContainer,
        Prop_Axis0Type_Int32, k_eControllerAxis_TrackPad);
    
    VRProperties()->SetInt32Property(m_ulPropertyContainer,
        Prop_Axis1Type_Int32, k_eControllerAxis_Trigger);
    
    // Создаем компоненты ввода - ИСПРАВЛЕННЫЙ СИНТАКСИС
    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, 
        "/input/trigger/click", &m_inputComponentHandles[0]);
    
    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, 
        "/input/grip/click", &m_inputComponentHandles[1]);
    
    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, 
        "/input/application_menu/click", &m_inputComponentHandles[2]);
    
    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, 
        "/input/system/click", &m_inputComponentHandles[3]);
    
    VRDriverInput()->CreateScalarComponent(m_ulPropertyContainer, 
        "/input/trigger/value", &m_inputComponentHandles[4], 
        VRScalarType_Absolute, VRScalarUnits_NormalizedOneSided);
    
    VRDriverLog()->Log("CVController: Activate completed successfully!");
    return VRInitError_None;
}

void CVController::Deactivate() {
    m_unObjectId = vr::k_unTrackedDeviceIndexInvalid;
}

void CVController::EnterStandby() {}

void* CVController::GetComponent(const char* pchComponentNameAndVersion) {
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

void CVController::RunFrame() {
    // КРИТИЧЕСКИ ВАЖНО! Отправляем обновления позы в SteamVR каждый кадр
    if (m_unObjectId != vr::k_unTrackedDeviceIndexInvalid) {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        VRServerDriverHost()->TrackedDevicePoseUpdated(m_unObjectId, m_pose, sizeof(DriverPose_t));
    }
}

void CVController::UpdateFromArduino(const ControllerData& data) {
    if (data.controller_id != m_expectedControllerId) {
        return;
    }
    
    {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        
        // Обновляем ориентацию
        m_pose.qRotation.w = data.quat_w;
        m_pose.qRotation.x = data.quat_x;
        m_pose.qRotation.y = data.quat_y;
        m_pose.qRotation.z = data.quat_z;
        
        // Рассчитываем дельта-время
        static auto last_time = std::chrono::steady_clock::now();
        auto now = std::chrono::steady_clock::now();
        float dt = std::chrono::duration<float>(now - last_time).count();
        if (dt > 0.1f) dt = 0.016f; // Ограничиваем разумным значением
        last_time = now;
        
        // Обновляем ускорение и скорость
        vr::HmdVector3d_t world_accel = {data.accel_x, data.accel_y, data.accel_z};
        
        m_pose.vecVelocity[0] += world_accel.v[0] * dt;
        m_pose.vecVelocity[1] += world_accel.v[1] * dt;
        m_pose.vecVelocity[2] += world_accel.v[2] * dt;
        
        // Применяем затухание
        m_pose.vecVelocity[0] *= 0.95f;
        m_pose.vecVelocity[1] *= 0.95f;
        m_pose.vecVelocity[2] *= 0.95f;
        
        // Обновляем позицию
        m_pose.vecPosition[0] += m_pose.vecVelocity[0] * dt;
        m_pose.vecPosition[1] += m_pose.vecVelocity[1] * dt;
        m_pose.vecPosition[2] += m_pose.vecVelocity[2] * dt;
        
        // Обновляем угловую скорость
        m_pose.vecAngularVelocity[0] = data.gyro_x;
        m_pose.vecAngularVelocity[1] = data.gyro_y;
        m_pose.vecAngularVelocity[2] = data.gyro_z;
        
        m_pose.poseIsValid = true;
        m_pose.result = TrackingResult_Running_OK;
        m_pose.deviceIsConnected = true;
        
        m_lastUpdateTime = now;
    }
    
    // Обновляем состояние кнопок
    UpdateButtonState(data.buttons, data.trigger);
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
    if (m_unObjectId == vr::k_unTrackedDeviceIndexInvalid) {
        return;
    }
    
    // Обновляем клик триггера
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[0], 
        (buttons & 0x01) != 0, 0);
    
    // Обновляем grip
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[1], 
        (buttons & 0x02) != 0, 0);
    
    // Обновляем меню приложения
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[2], 
        (buttons & 0x04) != 0, 0);
    
    // Обновляем системную кнопку
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[3], 
        (buttons & 0x08) != 0, 0);
    
    // Обновляем аналоговое значение триггера
    VRDriverInput()->UpdateScalarComponent(m_inputComponentHandles[4], 
        trigger / 255.0f, 0);
}