#include "device_provider.h"
#include "openvr_driver.h"

vr::EVRInitError GyroMouseDeviceProvider::Init(vr::IVRDriverContext* pDriverContext)
{
    VR_INIT_SERVER_DRIVER_CONTEXT(pDriverContext);

    // Create controllers
    left_controller_ = std::make_unique<GyroMouseController>(vr::TrackedControllerRole_LeftHand, 0);
    right_controller_ = std::make_unique<GyroMouseController>(vr::TrackedControllerRole_RightHand, 1);

    // Add to SteamVR
    if (!vr::VRServerDriverHost()->TrackedDeviceAdded(
        left_controller_->GetSerialNumber().c_str(),
        vr::TrackedDeviceClass_Controller,
        left_controller_.get()))
    {
        return vr::VRInitError_Driver_Unknown;
    }

    if (!vr::VRServerDriverHost()->TrackedDeviceAdded(
        right_controller_->GetSerialNumber().c_str(),
        vr::TrackedDeviceClass_Controller,
        right_controller_.get()))
    {
        return vr::VRInitError_Driver_Unknown;
    }

    return vr::VRInitError_None;
}

const char* const* GyroMouseDeviceProvider::GetInterfaceVersions()
{
    return vr::k_InterfaceVersions;
}

void GyroMouseDeviceProvider::RunFrame()
{
    if (left_controller_) {
        left_controller_->RunFrame();
    }
    if (right_controller_) {
        right_controller_->RunFrame();
    }

    vr::VREvent_t event{};
    while (vr::VRServerDriverHost()->PollNextEvent(&event, sizeof(vr::VREvent_t))) {
        if (left_controller_) {
            left_controller_->ProcessEvent(event);
        }
        if (right_controller_) {
            right_controller_->ProcessEvent(event);
        }
    }
}

bool GyroMouseDeviceProvider::ShouldBlockStandbyMode()
{
    return false;
}

void GyroMouseDeviceProvider::EnterStandby() {}

void GyroMouseDeviceProvider::LeaveStandby() {}

void GyroMouseDeviceProvider::Cleanup()
{
    left_controller_ = nullptr;
    right_controller_ = nullptr;
}