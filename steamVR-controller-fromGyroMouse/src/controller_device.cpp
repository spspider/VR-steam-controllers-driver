// src/controller_device.cpp
#include "driver.h"
#include <cmath>
#include <iostream>
#include <chrono>
#include <mutex>

using namespace vr;

GyroMouseController::GyroMouseController(vr::ETrackedControllerRole role, uint8_t expected_id)
    : m_role(role), m_expectedControllerId(expected_id),
      m_unObjectId(vr::k_unTrackedDeviceIndexInvalid), m_ulPropertyContainer(vr::k_ulInvalidPropertyContainer) {

    memset(&m_pose, 0, sizeof(m_pose));
    m_pose.poseIsValid = true;
    m_pose.result = TrackingResult_Running_OK;
    m_pose.deviceIsConnected = true;
    m_pose.willDriftInYaw = false;
    m_pose.shouldApplyHeadModel = false;
    
    // ВАЖНО: Устанавливаем тип устройства
    m_pose.deviceIsConnected = true;
    m_pose.qWorldFromDriverRotation = {1, 0, 0, 0};
    m_pose.qDriverFromHeadRotation = {1, 0, 0, 0};

    // Фиксированная позиция перед игроком
    // SteamVR использует правую систему координат:
    // X - вправо, Y - вверх, Z - вперед
    if (role == TrackedControllerRole_LeftHand) {
        m_pose.vecPosition[0] = -0.3f;  // Левее (отрицательное X)
        m_pose.vecPosition[1] = 0.0f;   // На уровне пояса
        m_pose.vecPosition[2] = -0.5f;  // Перед игроком (отрицательное Z в SteamVR)
    } else {
        m_pose.vecPosition[0] = 0.3f;   // Правее (положительное X)
        m_pose.vecPosition[1] = 0.0f;   // На уровне пояса
        m_pose.vecPosition[2] = -0.5f;  // Перед игроком
    }

    m_pose.qRotation = {1, 0, 0, 0};  // Без вращения
    
    // Устанавливаем скорость и угловую скорость в 0
    m_pose.vecVelocity[0] = 0;
    m_pose.vecVelocity[1] = 0;
    m_pose.vecVelocity[2] = 0;
    
    m_pose.vecAngularVelocity[0] = 0;
    m_pose.vecAngularVelocity[1] = 0;
    m_pose.vecAngularVelocity[2] = 0;

    m_lastUpdateTime = std::chrono::steady_clock::now();
}

vr::EVRInitError GyroMouseController::Activate(uint32_t unObjectId) {
    VRDriverLog()->Log("GyroMouseController: Activate called for controller");

    m_unObjectId = unObjectId;
    m_ulPropertyContainer = VRProperties()->TrackedDeviceToPropertyContainer(unObjectId);

    // Устанавливаем обязательные свойства
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_ModelNumber_String, "GyroMouse_Controller_MK1");
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_RenderModelName_String, "{gyromouse}/rendermodels/gyromouse_controller");
    
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_TrackingSystemName_String, "gyromouse");
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_ManufacturerName_String, "GyroMouse Inc");
    
    // Устанавливаем серийный номер в зависимости от роли
    if (m_role == TrackedControllerRole_LeftHand) {
        VRProperties()->SetStringProperty(m_ulPropertyContainer,
            Prop_SerialNumber_String, "GYROMOUSE_LEFT_001");
    } else {
        VRProperties()->SetStringProperty(m_ulPropertyContainer,
            Prop_SerialNumber_String, "GYROMOUSE_RIGHT_001");
    }

    VRProperties()->SetUint64Property(m_ulPropertyContainer,
        Prop_CurrentUniverseId_Uint64, 2);

    VRProperties()->SetInt32Property(m_ulPropertyContainer,
        Prop_ControllerRoleHint_Int32, m_role);

    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_ControllerType_String, "gyromousecontroller");

    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_InputProfilePath_String, "{gyromouse}/input/gyromouse_profile.json");

    // ВАЖНО: Регистрируем компоненты ввода
    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, "/input/system/click", &m_components.systemButton);
    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, "/input/application_menu/click", &m_components.applicationMenu);
    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, "/input/grip/click", &m_components.grip);
    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, "/input/trigger/click", &m_components.trigger);
    
    // Создаем компонент для трекинга позы
    VRDriverInput()->CreateSkeletonComponent(m_ulPropertyContainer, 
        "/input/skeleton/left", 
        "/skeleton/hand/left", 
        "/skeleton/hand/left", 
        vr::VRSkeletalTracking_Partial,
        nullptr, 0, 
        &m_components.skeleton);

    VRDriverLog()->Log("GyroMouseController: Activate completed for controller");
    return VRInitError_None;
}

void GyroMouseController::Deactivate() {
    m_unObjectId = vr::k_unTrackedDeviceIndexInvalid;
}

void GyroMouseController::EnterStandby() {}

void* GyroMouseController::GetComponent(const char* pchComponentNameAndVersion) {
    return nullptr;
}

void GyroMouseController::DebugRequest(const char* pchRequest, char* pchResponseBuffer,
                         uint32_t unResponseBufferSize) {
    if (unResponseBufferSize >= 1) {
        pchResponseBuffer[0] = 0;
    }
}

vr::DriverPose_t GyroMouseController::GetPose() {
    std::lock_guard<std::mutex> lock(m_poseMutex);
    
    // Обновляем временную метку
    auto now = std::chrono::steady_clock::now();
    auto duration = now.time_since_epoch();
    auto nanoseconds = std::chrono::duration_cast<std::chrono::nanoseconds>(duration);
    m_pose.poseTimeOffset = 0; // Используем текущее время
    
    return m_pose;
}

void GyroMouseController::UpdateFromMouse(const MouseControllerData& data) {
    if (data.controller_id != m_expectedControllerId) {
        return;
    }

    {
        std::lock_guard<std::mutex> lock(m_poseMutex);

        // Обновляем ориентацию из гироскопа
        m_pose.qRotation.w = data.quat_w;
        m_pose.qRotation.x = data.quat_x;
        m_pose.qRotation.y = data.quat_y;
        m_pose.qRotation.z = data.quat_z;

        // Позиция остается фиксированной для дебага
        // Обновляем угловую скорость
        m_pose.vecAngularVelocity[0] = data.gyro_x;
        m_pose.vecAngularVelocity[1] = data.gyro_y;
        m_pose.vecAngularVelocity[2] = data.gyro_z;

        m_pose.poseIsValid = true;
        m_pose.result = TrackingResult_Running_OK;
        m_pose.deviceIsConnected = true;

        m_lastUpdateTime = std::chrono::steady_clock::now();
    }

    // Обновляем состояние кнопок
    UpdateButtonState(data.buttons);
}

void GyroMouseController::CheckConnection() {
    auto now = std::chrono::steady_clock::now();
    float time_since_update = std::chrono::duration<float>(now - m_lastUpdateTime).count();

    if (time_since_update > 1.0f) {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        m_pose.deviceIsConnected = false;
        m_pose.poseIsValid = false;
    } else {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        m_pose.deviceIsConnected = true;
        m_pose.poseIsValid = true;
    }
}

void GyroMouseController::UpdateButtonState(uint16_t buttons) {
    // Обновляем состояние кнопок через VRDriverInput
    if (m_components.systemButton != vr::k_ulInvalidInputComponentHandle) {
        VRDriverInput()->UpdateBooleanComponent(m_components.systemButton, (buttons & 0x08) != 0, 0);
    }
    
    if (m_components.applicationMenu != vr::k_ulInvalidInputComponentHandle) {
        VRDriverInput()->UpdateBooleanComponent(m_components.applicationMenu, (buttons & 0x04) != 0, 0);
    }
    
    if (m_components.grip != vr::k_ulInvalidInputComponentHandle) {
        VRDriverInput()->UpdateBooleanComponent(m_components.grip, (buttons & 0x02) != 0, 0);
    }
    
    if (m_components.trigger != vr::k_ulInvalidInputComponentHandle) {
        VRDriverInput()->UpdateBooleanComponent(m_components.trigger, (buttons & 0x01) != 0, 0);
    }
}