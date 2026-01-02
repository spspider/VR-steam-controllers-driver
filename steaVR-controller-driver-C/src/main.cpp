// src/main.cpp
#include "driver.h"
#include <thread>
#include <vector>
#include <iostream>
#include <memory>
#include <sstream>

using namespace vr;

class CVDriver : public IServerTrackedDeviceProvider {
public:
    CVDriver() : m_networkClient(nullptr) {}
    
    virtual ~CVDriver() {
        Cleanup();
    }
    
    // ==== IServerTrackedDeviceProvider ====
    virtual vr::EVRInitError Init(vr::IVRDriverContext* pDriverContext) override {
        VR_INIT_SERVER_DRIVER_CONTEXT(pDriverContext);
        
        VRDriverLog()->Log("=== CVDriver v2.0 INIT START ===");
        
        // Создаем контроллеры
        m_leftController = std::make_unique<CVController>(
            TrackedControllerRole_LeftHand, 0);
        m_rightController = std::make_unique<CVController>(
            TrackedControllerRole_RightHand, 1);
        
        // Регистрируем контроллеры в SteamVR
        VRServerDriverHost()->TrackedDeviceAdded(
            "CV_Controller_Left", 
            TrackedDeviceClass_Controller, 
            m_leftController.get());
        
        VRServerDriverHost()->TrackedDeviceAdded(
            "CV_Controller_Right", 
            TrackedDeviceClass_Controller, 
            m_rightController.get());
        
        // Запускаем сетевой клиент
        m_networkClient = std::make_unique<NetworkClient>(5555);
        if (!m_networkClient->Start()) {
            VRDriverLog()->Log("CVDriver: Failed to start network client!");
            return VRInitError_Init_Internal;
        }
        
        // Запускаем поток для получения данных
        m_running = true;
        m_networkThread = std::thread(&CVDriver::NetworkThread, this);
        
        VRDriverLog()->Log("=== CVDriver v2.0 INIT SUCCESS ===");
        return VRInitError_None;
    }
    
    virtual void Cleanup() override {
        VRDriverLog()->Log("CVDriver: Cleaning up...");
        
        m_running = false;
        if (m_networkThread.joinable()) {
            m_networkThread.join();
        }
        
        if (m_networkClient) {
            m_networkClient->Stop();
            m_networkClient.reset();
        }
    }
    
    virtual const char* const* GetInterfaceVersions() override {
        return k_InterfaceVersions;
    }
    
    virtual void RunFrame() override {
        // Вызывается каждый кадр SteamVR
        if (m_leftController) m_leftController->CheckConnection();
        if (m_rightController) m_rightController->CheckConnection();
    }
    
    virtual bool ShouldBlockStandbyMode() override { return false; }
    virtual void EnterStandby() override {}
    virtual void LeaveStandby() override {}
    
private:
    void NetworkThread() {
        VRDriverLog()->Log("CVDriver: Network thread started, waiting for data on port 5555...");
        
        int logCounter = 0;
        ControllerData data;
        
        while (m_running) {
            if (m_networkClient && m_networkClient->Receive(data)) {
                // Логируем только каждые 1000 пакетов
                if (logCounter % 1000 == 0) {
                    char logMsg[256];
                    sprintf_s(logMsg, "CVDriver: Received 1000 packets, last: controller %d, packet %u", 
                             (int)data.controller_id, data.packet_number);
                    VRDriverLog()->Log(logMsg);
                }
                logCounter++;
                
                // Обновляем соответствующий контроллер
                if (data.controller_id == 0 && m_leftController) {
                    m_leftController->UpdateFromArduino(data);
                } 
                else if (data.controller_id == 1 && m_rightController) {
                    m_rightController->UpdateFromArduino(data);
                }
            }
            
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        
        VRDriverLog()->Log("CVDriver: Network thread stopped.");
    }
    
    std::unique_ptr<CVController> m_leftController;
    std::unique_ptr<CVController> m_rightController;
    std::unique_ptr<NetworkClient> m_networkClient;
    std::thread m_networkThread;
    std::atomic<bool> m_running{false};
};

// Глобальные переменные для экспорта функций
CVDriver g_driver;

extern "C" __declspec(dllexport) void* HmdDriverFactory(
    const char* pInterfaceName, int* pReturnCode) {
    
    if (strcmp(pInterfaceName, IServerTrackedDeviceProvider_Version) == 0) {
        return &g_driver;
    }
    
    if (strcmp(pInterfaceName, vr::IServerTrackedDeviceProvider_Version) == 0) {
        return &g_driver;
    }
    
    if (pReturnCode) {
        *pReturnCode = vr::VRInitError_Init_InterfaceNotFound;
    }
    return nullptr;
}