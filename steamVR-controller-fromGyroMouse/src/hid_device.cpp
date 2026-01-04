// src/hid_device.cpp
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "hid_device.h"
#include <setupapi.h>
#include <winioctl.h>
#include <hidsdi.h>
#include <hidpi.h>
#include <cstring>

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "hid.lib")

// ВАЖНО: Эти константы определяют конкретное устройство
// VID_2389 & PID_00A8 - гироскопическая мышь
// Это устройство будет захвачено драйвером в монопольном режиме
// После захвата устройство перестанет работать как обычная мышь в Windows

HIDDevice::HIDDevice(uint16_t vendor_id, uint16_t product_id)
    : m_vendorId(vendor_id), m_productId(product_id), 
      m_deviceHandle(nullptr), m_isOpen(false) {}

HIDDevice::~HIDDevice() {
    Close();
}

bool HIDDevice::Open() {
    GUID hidGuid;
    HidD_GetHidGuid(&hidGuid);
    
    HDEVINFO deviceInfo = SetupDiGetClassDevs(
        &hidGuid,
        nullptr,
        nullptr,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    );
    
    if (deviceInfo == INVALID_HANDLE_VALUE) {
        return false;
    }
    
    SP_DEVICE_INTERFACE_DATA deviceInterfaceData;
    deviceInterfaceData.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA);
    
    // Перебираем все HID устройства
    for (DWORD i = 0; SetupDiEnumDeviceInterfaces(
        deviceInfo, nullptr, &hidGuid, i, &deviceInterfaceData); ++i) {
        
        DWORD requiredSize = 0;
        SetupDiGetDeviceInterfaceDetail(
            deviceInfo, &deviceInterfaceData, nullptr, 0, &requiredSize, nullptr);
        
        PSP_DEVICE_INTERFACE_DETAIL_DATA deviceInterfaceDetailData =
            (PSP_DEVICE_INTERFACE_DETAIL_DATA)malloc(requiredSize);
        
        if (!deviceInterfaceDetailData) {
            continue;
        }
        
        deviceInterfaceDetailData->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA);
        
        if (!SetupDiGetDeviceInterfaceDetail(
            deviceInfo, &deviceInterfaceData, deviceInterfaceDetailData,
            requiredSize, &requiredSize, nullptr)) {
            free(deviceInterfaceDetailData);
            continue;
        }
        
        // Открываем устройство в монопольном режиме (без FILE_SHARE_*)
        // ВАЖНО: Это предотвращает использование устройства как обычной мыши
        HANDLE deviceHandle = CreateFileA(
            deviceInterfaceDetailData->DevicePath,
            GENERIC_READ | GENERIC_WRITE,
            0,  // Монопольный режим - без FILE_SHARE_READ | FILE_SHARE_WRITE
            nullptr,
            OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED,
            nullptr
        );
        
        free(deviceInterfaceDetailData);
        
        if (deviceHandle == INVALID_HANDLE_VALUE) {
            continue;
        }
        
        // Получаем атрибуты устройства
        HIDD_ATTRIBUTES attributes;
        attributes.Size = sizeof(HIDD_ATTRIBUTES);
        
        if (!HidD_GetAttributes(deviceHandle, &attributes)) {
            CloseHandle(deviceHandle);
            continue;
        }
        
        // ВАЖНО: Проверяем VID и PID
        // VID_2389 & PID_00A8 - это наша гироскопическая мышь (левый контроллер)
        if (attributes.VendorID == m_vendorId && attributes.ProductID == m_productId) {
            m_deviceHandle = deviceHandle;
            m_isOpen = true;
            SetupDiDestroyDeviceInfoList(deviceInfo);
            return true;
        }
        
        CloseHandle(deviceHandle);
    }
    
    SetupDiDestroyDeviceInfoList(deviceInfo);
    return false;
}

void HIDDevice::Close() {
    if (m_deviceHandle != nullptr) {
        CloseHandle((HANDLE)m_deviceHandle);
        m_deviceHandle = nullptr;
        m_isOpen = false;
    }
}

bool HIDDevice::Read(uint8_t* buffer, size_t buffer_size, size_t& bytes_read) {
    if (!m_isOpen || m_deviceHandle == nullptr) {
        return false;
    }
    
    DWORD bytesRead = 0;
    if (!ReadFile(m_deviceHandle, buffer, (DWORD)buffer_size, &bytesRead, nullptr)) {
        return false;
    }
    
    bytes_read = bytesRead;
    return true;
}
