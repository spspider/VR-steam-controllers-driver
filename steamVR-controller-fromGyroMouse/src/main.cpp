// src/main.cpp
#include "driver.h"
#include <thread>
#include <vector>
#include <iostream>
#include <memory>
#include <sstream>

using namespace vr;

class GyroMouseDriver : public IServerTrackedDeviceProvider {
public:
    GyroMouseDriver() : m_mouseInputClient(nullptr) {}

    virtual ~GyroMouseDriver() {
        Cleanup();
    }

    virtual vr::EVRInitError Init(vr::IVRDriverContext* pDriverContext) override {
        VR_INIT_SERVER_DRIVER_CONTEXT(pDriverContext);

        VRDriverLog()->Log("=== GyroMouse Driver v1.0 INIT START ===");

        // Создаем только ОДИН контроллер (гироскопическая мышь)
        m_gyroController = std::make_unique<GyroMouseController>(
            TrackedControllerRole_LeftHand, 0);

        // Регистрируем контроллер в SteamVR
        bool added = VRServerDriverHost()->TrackedDeviceAdded(
            "GyroMouse_Controller",
            TrackedDeviceClass_Controller,
            m_gyroController.get());

        if (!added) {
            VRDriverLog()->Log("GyroMouse: Failed to add controller!");
            return VRInitError_Init_Internal;
        }

        VRDriverLog()->Log("GyroMouse: Controller registered successfully");

        // Запускаем клиент для получения данных по UDP
        m_mouseInputClient = std::make_unique<MouseInputClient>(5556);
        if (!m_mouseInputClient->Start()) {
            VRDriverLog()->Log("GyroMouse: Failed to start UDP client!");
            return VRInitError_Init_Internal;
        }

        VRDriverLog()->Log("GyroMouse: UDP client started on port 5556");

        // Запускаем поток для получения данных
        m_running = true;
        m_networkThread = std::thread(&GyroMouseDriver::NetworkThread, this);

        VRDriverLog()->Log("=== GyroMouse Driver v1.0 INIT SUCCESS ===");
        return VRInitError_None;
    }

    virtual void Cleanup() override {
        VRDriverLog()->Log("GyroMouse: Cleaning up...");

        m_running = false;
        if (m_networkThread.joinable()) {
            m_networkThread.join();
        }

        if (m_mouseInputClient) {
            m_mouseInputClient->Stop();
            m_mouseInputClient.reset();
        }

        VRDriverLog()->Log("GyroMouse: Cleanup complete");
    }

    virtual const char* const* GetInterfaceVersions() override {
        return k_InterfaceVersions;
    }

    virtual void RunFrame() override {
        // КРИТИЧЕСКИ ВАЖНО: Обновляем позу каждый кадр
        if (m_gyroController) {
            m_gyroController->CheckConnection();
            m_gyroController->RunFrame();
        }
    }

    virtual bool ShouldBlockStandbyMode() override { return false; }
    virtual void EnterStandby() override {}
    virtual void LeaveStandby() override {}

private:
    void NetworkThread() {
        VRDriverLog()->Log("GyroMouse: Network thread started, waiting for data on port 5556...");

        int logCounter = 0;
        MouseControllerData data;

        while (m_running) {
            if (m_mouseInputClient && m_mouseInputClient->Receive(data)) {
                // Логируем каждые 1000 пакетов
                if (logCounter % 1000 == 0) {
                    char logMsg[256];
                    snprintf(logMsg, sizeof(logMsg),
                        "GyroMouse: Packet %u - Pos(%.2f,%.2f,%.2f) Quat(%.2f,%.2f,%.2f,%.2f)",
                        data.packet_number,
                        data.pos_x, data.pos_y, data.pos_z,
                        data.quat_w, data.quat_x, data.quat_y, data.quat_z);
                    VRDriverLog()->Log(logMsg);
                }
                logCounter++;

                // Обновляем контроллер
                if (data.controller_id == 0 && m_gyroController) {
                    m_gyroController->UpdateFromMouse(data);
                }
            }

            // Небольшая задержка чтобы не нагружать CPU
            std::this_thread::sleep_for(std::chrono::microseconds(100));
        }

        VRDriverLog()->Log("GyroMouse: Network thread stopped.");
    }

    std::unique_ptr<GyroMouseController> m_gyroController;
    std::unique_ptr<MouseInputClient> m_mouseInputClient;
    std::thread m_networkThread;
    std::atomic<bool> m_running{false};
};

// Глобальный экземпляр драйвера
GyroMouseDriver g_driver;

extern "C" __declspec(dllexport) void* HmdDriverFactory(
    const char* pInterfaceName, int* pReturnCode) {

    if (strcmp(pInterfaceName, IServerTrackedDeviceProvider_Version) == 0) {
        if (pReturnCode) *pReturnCode = VRInitError_None;
        return &g_driver;
    }

    if (pReturnCode) {
        *pReturnCode = VRInitError_Init_InterfaceNotFound;
    }
    return nullptr;
}