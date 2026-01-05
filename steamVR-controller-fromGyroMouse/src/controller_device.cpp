// src/controller_device.cpp
#include "driver.h"
#include <cmath>
#include <iostream>

using namespace vr;

GyroMouseController::GyroMouseController(vr::ETrackedControllerRole role, uint8_t expected_id)
    : m_role(role), m_expectedControllerId(expected_id),
      m_unObjectId(vr::k_unTrackedDeviceIndexInvalid), m_ulPropertyContainer(0) {

    memset(&m_pose, 0, sizeof(m_pose));
    m_pose.poseIsValid = true;
    m_pose.result = TrackingResult_Running_OK;
    m_pose.deviceIsConnected = true;

    m_pose.qWorldFromDriverRotation = {1, 0, 0, 0};
    m_pose.qDriverFromHeadRotation = {1, 0, 0, 0};

    // Начальная позиция (будет обновлена из ArUco)
    m_pose.vecPosition[0] = (role == TrackedControllerRole_LeftHand) ? -0.2f : 0.2f;
    m_pose.vecPosition[1] = 1.0f;
    m_pose.vecPosition[2] = -0.3f;

    m_pose.qRotation = {1, 0, 0, 0};

    m_lastUpdateTime = std::chrono::steady_clock::now();

    // Инициализируем хендлы компонентов ввода
    memset(m_inputComponentHandles, 0, sizeof(m_inputComponentHandles));
}

vr::EVRInitError GyroMouseController::Activate(uint32_t unObjectId) {
    VRDriverLog()->Log("GyroMouseController: Activate called!");

    m_unObjectId = unObjectId;
    m_ulPropertyContainer = VRProperties()->TrackedDeviceToPropertyContainer(unObjectId);

    // Основные свойства
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_ModelNumber_String, "GyroMouse_Controller_MK1");

    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_SerialNumber_String,
        m_role == TrackedControllerRole_LeftHand ? "GYROMOUSE_LEFT_001" : "GYROMOUSE_RIGHT_001");

    // Используем модель контроллера Vive как временную
    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_RenderModelName_String, "vr_controller_vive_1_5");

    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_ManufacturerName_String, "GyroMouse");

    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_TrackingSystemName_String, "gyromouse_aruco");

    VRProperties()->SetUint64Property(m_ulPropertyContainer,
        Prop_CurrentUniverseId_Uint64, 2);

    VRProperties()->SetInt32Property(m_ulPropertyContainer,
        Prop_ControllerRoleHint_Int32, m_role);

    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_ControllerType_String, "vive_controller");

    VRProperties()->SetStringProperty(m_ulPropertyContainer,
        Prop_InputProfilePath_String, "{gyromouse}/input/gyromouse_profile.json");

    VRProperties()->SetInt32Property(m_ulPropertyContainer,
        Prop_DeviceClass_Int32, TrackedDeviceClass_Controller);

    // Создаем компоненты ввода
    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer,
        "/input/trigger/click", &m_inputComponentHandles[0]);

    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer,
        "/input/grip/click", &m_inputComponentHandles[1]);

    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer,
        "/input/application_menu/click", &m_inputComponentHandles[2]);

    VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer,
        "/input/system/click", &m_inputComponentHandles[3]);

    VRDriverLog()->Log("GyroMouseController: Activate completed successfully!");
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
    return m_pose;
}

void GyroMouseController::RunFrame() {
    // КРИТИЧЕСКИ ВАЖНО! Отправляем обновления позы в SteamVR каждый кадр
    if (m_unObjectId != vr::k_unTrackedDeviceIndexInvalid) {
        std::lock_guard<std::mutex> lock(m_poseMutex);
        VRServerDriverHost()->TrackedDevicePoseUpdated(m_unObjectId, m_pose, sizeof(DriverPose_t));
    }
}

void GyroMouseController::UpdateFromMouse(const MouseControllerData& data) {
    if (data.controller_id != m_expectedControllerId) {
        return;
    }

    {
        std::lock_guard<std::mutex> lock(m_poseMutex);

        // Обновляем ориентацию из гироскопа мыши
        m_pose.qRotation.w = data.quat_w;
        m_pose.qRotation.x = data.quat_x;
        m_pose.qRotation.y = data.quat_y;
        m_pose.qRotation.z = data.quat_z;

        // ВАЖНО: Обновляем позицию из ArUco tracking
        m_pose.vecPosition[0] = data.pos_x;
        m_pose.vecPosition[1] = data.pos_y;
        m_pose.vecPosition[2] = data.pos_z;

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
    }
}

void GyroMouseController::UpdateButtonState(uint16_t buttons) {
    if (m_unObjectId == vr::k_unTrackedDeviceIndexInvalid) {
        return;
    }

    // Кнопки мыши:
    // 0x01 = левая кнопка (trigger)
    // 0x02 = правая кнопка (grip)
    // 0x04 = средняя кнопка (application menu)
    // 0x08 = боковая кнопка (system)

    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[0],
        (buttons & 0x01) != 0, 0);

    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[1],
        (buttons & 0x02) != 0, 0);

    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[2],
        (buttons & 0x04) != 0, 0);

    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[3],
        (buttons & 0x08) != 0, 0);
}