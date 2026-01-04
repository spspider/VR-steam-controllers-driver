#pragma once

#include <memory>
#include "gyro_controller.h"
#include "openvr_driver.h"

class GyroMouseDeviceProvider : public vr::IServerTrackedDeviceProvider
{
public:
    vr::EVRInitError Init(vr::IVRDriverContext* pDriverContext) override;
    const char* const* GetInterfaceVersions() override;
    void RunFrame() override;
    bool ShouldBlockStandbyMode() override;
    void EnterStandby() override;
    void LeaveStandby() override;
    void Cleanup() override;

private:
    std::unique_ptr<GyroMouseController> left_controller_;
    std::unique_ptr<GyroMouseController> right_controller_;
};