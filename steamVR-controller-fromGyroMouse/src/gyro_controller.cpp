#include "gyro_controller.h"
#include "openvr_driver.h"
#include <cstring>

GyroMouseController::GyroMouseController(vr::ETrackedControllerRole role, uint8_t controller_id)
    : role_(role), controller_id_(controller_id), is_active_(false)
{
    // Set serial number based on role
    serial_number_ = (role == vr::TrackedControllerRole_LeftHand) ? 
        "GYROMOUSE_LEFT_001" : "GYROMOUSE_RIGHT_001";

    // Initialize pose
    memset(&pose_, 0, sizeof(pose_));
    pose_.poseIsValid = true;
    pose_.result = vr::TrackingResult_Running_OK;
    pose_.deviceIsConnected = true;
    pose_.qWorldFromDriverRotation.w = 1.0;
    pose_.qDriverFromHeadRotation.w = 1.0;
    pose_.qRotation.w = 1.0;

    // Set initial position
    if (role == vr::TrackedControllerRole_LeftHand) {
        pose_.vecPosition[0] = -0.3;  // Left
        pose_.vecPosition[1] = 0.0;   // Center height
        pose_.vecPosition[2] = -0.5;  // Forward
    } else {
        pose_.vecPosition[0] = 0.3;   // Right
        pose_.vecPosition[1] = 0.0;   // Center height
        pose_.vecPosition[2] = -0.5;  // Forward
    }

    last_update_ = std::chrono::steady_clock::now();
}

vr::EVRInitError GyroMouseController::Activate(uint32_t unObjectId)
{
    device_index_ = unObjectId;
    is_active_ = true;

    vr::PropertyContainerHandle_t container = vr::VRProperties()->TrackedDeviceToPropertyContainer(device_index_);

    // Set device properties
    vr::VRProperties()->SetStringProperty(container, vr::Prop_ModelNumber_String, "GyroMouse Controller");
    vr::VRProperties()->SetStringProperty(container, vr::Prop_SerialNumber_String, serial_number_.c_str());
    vr::VRProperties()->SetStringProperty(container, vr::Prop_ManufacturerName_String, "GyroMouse Inc");
    vr::VRProperties()->SetInt32Property(container, vr::Prop_ControllerRoleHint_Int32, role_);
    vr::VRProperties()->SetStringProperty(container, vr::Prop_InputProfilePath_String, "{gyromouse}/input/gyromouse_profile.json");

    // Create input components
    vr::VRDriverInput()->CreateBooleanComponent(container, "/input/system/click", &system_button_);
    vr::VRDriverInput()->CreateBooleanComponent(container, "/input/application_menu/click", &menu_button_);
    vr::VRDriverInput()->CreateBooleanComponent(container, "/input/grip/click", &grip_button_);
    vr::VRDriverInput()->CreateBooleanComponent(container, "/input/trigger/click", &trigger_button_);
    vr::VRDriverInput()->CreateHapticComponent(container, "/output/haptic", &haptic_);

    // Start pose update thread
    pose_thread_ = std::thread(&GyroMouseController::PoseUpdateThread, this);

    return vr::VRInitError_None;
}

void GyroMouseController::Deactivate()
{
    if (is_active_.exchange(false)) {
        pose_thread_.join();
    }
    device_index_ = vr::k_unTrackedDeviceIndexInvalid;
}

void GyroMouseController::EnterStandby() {}

void* GyroMouseController::GetComponent(const char* pchComponentNameAndVersion)
{
    return nullptr;
}

void GyroMouseController::DebugRequest(const char* pchRequest, char* pchResponseBuffer, uint32_t unResponseBufferSize)
{
    if (unResponseBufferSize >= 1) {
        pchResponseBuffer[0] = 0;
    }
}

vr::DriverPose_t GyroMouseController::GetPose()
{
    std::lock_guard<std::mutex> lock(pose_mutex_);
    return pose_;
}

const std::string& GyroMouseController::GetSerialNumber() const
{
    return serial_number_;
}

void GyroMouseController::RunFrame()
{
    // Update input states (for now, just set to false)
    vr::VRDriverInput()->UpdateBooleanComponent(system_button_, false, 0);
    vr::VRDriverInput()->UpdateBooleanComponent(menu_button_, false, 0);
    vr::VRDriverInput()->UpdateBooleanComponent(grip_button_, false, 0);
    vr::VRDriverInput()->UpdateBooleanComponent(trigger_button_, false, 0);
}

void GyroMouseController::ProcessEvent(const vr::VREvent_t& event)
{
    // Handle haptic events
    if (event.eventType == vr::VREvent_Input_HapticVibration) {
        if (event.data.hapticVibration.componentHandle == haptic_) {
            // Handle haptic feedback
        }
    }
}

void GyroMouseController::UpdateFromMouse(const MouseControllerData& data)
{
    if (data.controller_id != controller_id_) {
        return;
    }

    std::lock_guard<std::mutex> lock(pose_mutex_);
    
    // Update orientation from gyro data
    pose_.qRotation.w = data.quat_w;
    pose_.qRotation.x = data.quat_x;
    pose_.qRotation.y = data.quat_y;
    pose_.qRotation.z = data.quat_z;

    // Update angular velocity
    pose_.vecAngularVelocity[0] = data.gyro_x;
    pose_.vecAngularVelocity[1] = data.gyro_y;
    pose_.vecAngularVelocity[2] = data.gyro_z;

    pose_.poseIsValid = true;
    pose_.deviceIsConnected = true;
    pose_.result = vr::TrackingResult_Running_OK;

    last_update_ = std::chrono::steady_clock::now();
}

void GyroMouseController::PoseUpdateThread()
{
    while (is_active_) {
        // Check connection timeout
        auto now = std::chrono::steady_clock::now();
        auto time_since_update = std::chrono::duration_cast<std::chrono::seconds>(now - last_update_).count();
        
        {
            std::lock_guard<std::mutex> lock(pose_mutex_);
            if (time_since_update > 2) {
                pose_.deviceIsConnected = false;
                pose_.poseIsValid = false;
            } else {
                pose_.deviceIsConnected = true;
                pose_.poseIsValid = true;
            }
        }

        // Update pose in SteamVR
        vr::VRServerDriverHost()->TrackedDevicePoseUpdated(device_index_, GetPose(), sizeof(vr::DriverPose_t));

        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
}