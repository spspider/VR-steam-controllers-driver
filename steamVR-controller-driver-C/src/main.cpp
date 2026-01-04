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
    
    virtual vr::EVRInitError Init(vr::IVRDriverContext* pDriverContext) override {
        VR_INIT_SERVER_DRIVER_CONTEXT(pDriverContext);
        
        VRDriverLog()->Log("=== CVDriver v2.1 INIT START ===");
        
        // Create controllers
        m_leftController = std::make_unique<CVController>(
            TrackedControllerRole_LeftHand, 0);
        m_rightController = std::make_unique<CVController>(
            TrackedControllerRole_RightHand, 1);
        
        // Register controllers with SteamVR
        bool leftAdded = VRServerDriverHost()->TrackedDeviceAdded(
            "CV_Controller_Left", 
            TrackedDeviceClass_Controller, 
            m_leftController.get());
        
        bool rightAdded = VRServerDriverHost()->TrackedDeviceAdded(
            "CV_Controller_Right", 
            TrackedDeviceClass_Controller, 
            m_rightController.get());
        
        if (!leftAdded || !rightAdded) {
            VRDriverLog()->Log("CVDriver: Failed to add controllers!");
            return VRInitError_Init_Internal;
        }
        
        VRDriverLog()->Log("CVDriver: Controllers registered successfully");
        
        // Start network client
        m_networkClient = std::make_unique<NetworkClient>(5555);
        if (!m_networkClient->Start()) {
            VRDriverLog()->Log("CVDriver: Failed to start network client!");
            return VRInitError_Init_Internal;
        }
        
        VRDriverLog()->Log("CVDriver: Network client started on port 5555");
        
        // Start network thread
        m_running = true;
        m_networkThread = std::thread(&CVDriver::NetworkThread, this);
        
        VRDriverLog()->Log("=== CVDriver v2.1 INIT SUCCESS ===");
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
        
        VRDriverLog()->Log("CVDriver: Cleanup complete");
    }
    
    virtual const char* const* GetInterfaceVersions() override {
        return k_InterfaceVersions;
    }
    
    virtual void RunFrame() override {
        // CRITICAL: This is called every frame by SteamVR
        // We must update controller poses here!
        if (m_leftController) {
            m_leftController->CheckConnection();
            m_leftController->RunFrame();
        }
        
        if (m_rightController) {
            m_rightController->CheckConnection();
            m_rightController->RunFrame();
        }
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
                // Log every 1000 packets
                if (logCounter % 1000 == 0) {
                    char logMsg[256];
                    snprintf(logMsg, sizeof(logMsg), 
                        "CVDriver: Packet %u from controller %d - Quat(%.2f,%.2f,%.2f,%.2f)", 
                        data.packet_number, (int)data.controller_id,
                        data.quat_w, data.quat_x, data.quat_y, data.quat_z);
                    VRDriverLog()->Log(logMsg);
                }
                logCounter++;
                
                // Update corresponding controller
                if (data.controller_id == 0 && m_leftController) {
                    m_leftController->UpdateFromArduino(data);
                } 
                else if (data.controller_id == 1 && m_rightController) {
                    m_rightController->UpdateFromArduino(data);
                }
            }
            
            // Small sleep to avoid CPU spinning
            std::this_thread::sleep_for(std::chrono::microseconds(100));
        }
        
        VRDriverLog()->Log("CVDriver: Network thread stopped.");
    }
    
    std::unique_ptr<CVController> m_leftController;
    std::unique_ptr<CVController> m_rightController;
    std::unique_ptr<NetworkClient> m_networkClient;
    std::thread m_networkThread;
    std::atomic<bool> m_running{false};
};

// Global driver instance
CVDriver g_driver;

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