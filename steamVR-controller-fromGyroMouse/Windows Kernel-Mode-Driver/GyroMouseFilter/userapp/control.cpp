#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <setupapi.h>
#include <hidsdi.h>
#include <iostream>
#include <vector>
#include <string>
#include <iomanip>

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "hid.lib")

#define IOCTL_GYRO_SET_BLOCK CTL_CODE(FILE_DEVICE_MOUSE, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_GYRO_GET_INFO  CTL_CODE(FILE_DEVICE_MOUSE, 0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)

struct MouseDevice {
    std::wstring path;
    std::wstring name;
    USHORT vendorId;
    USHORT productId;
    HANDLE handle;
};

// Получить VID/PID из пути устройства
bool GetVidPidFromPath(const std::wstring& path, USHORT& vid, USHORT& pid) {
    size_t vidPos = path.find(L"VID_");
    size_t pidPos = path.find(L"PID_");
    
    if (vidPos == std::wstring::npos || pidPos == std::wstring::npos) {
        return false;
    }
    
    std::wstring vidStr = path.substr(vidPos + 4, 4);
    std::wstring pidStr = path.substr(pidPos + 4, 4);
    
    vid = (USHORT)std::wcstoul(vidStr.c_str(), nullptr, 16);
    pid = (USHORT)std::wcstoul(pidStr.c_str(), nullptr, 16);
    
    return true;
}

// Перечислить все HID мыши
std::vector<MouseDevice> EnumerateHidMice() {
    std::vector<MouseDevice> devices;
    
    GUID hidGuid;
    HidD_GetHidGuid(&hidGuid);
    
    HDEVINFO deviceInfoSet = SetupDiGetClassDevs(&hidGuid,
                                                   NULL,
                                                   NULL,
                                                   DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    
    if (deviceInfoSet == INVALID_HANDLE_VALUE) {
        std::cerr << "Failed to get device info set" << std::endl;
        return devices;
    }
    
    SP_DEVICE_INTERFACE_DATA deviceInterfaceData;
    deviceInterfaceData.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA);
    
    for (DWORD i = 0; SetupDiEnumDeviceInterfaces(deviceInfoSet,
                                                    NULL,
                                                    &hidGuid,
                                                    i,
                                                    &deviceInterfaceData); i++) {
        
        DWORD requiredSize = 0;
        SetupDiGetDeviceInterfaceDetail(deviceInfoSet,
                                        &deviceInterfaceData,
                                        NULL,
                                        0,
                                        &requiredSize,
                                        NULL);
        
        if (requiredSize == 0) continue;
        
        PSP_DEVICE_INTERFACE_DETAIL_DATA detailData = 
            (PSP_DEVICE_INTERFACE_DETAIL_DATA)malloc(requiredSize);
        
        if (!detailData) continue;
        
        detailData->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA);
        
        if (!SetupDiGetDeviceInterfaceDetail(deviceInfoSet,
                                             &deviceInterfaceData,
                                             detailData,
                                             requiredSize,
                                             NULL,
                                             NULL)) {
            free(detailData);
            continue;
        }
        
        std::wstring devicePath = detailData->DevicePath;
        free(detailData);
        
        // Открыть устройство для получения информации
        HANDLE hDevice = CreateFile(devicePath.c_str(),
                                    GENERIC_READ | GENERIC_WRITE,
                                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                                    NULL,
                                    OPEN_EXISTING,
                                    0,
                                    NULL);
        
        if (hDevice == INVALID_HANDLE_VALUE) continue;
        
        // Получить атрибуты HID
        HIDD_ATTRIBUTES attributes;
        attributes.Size = sizeof(HIDD_ATTRIBUTES);
        
        if (!HidD_GetAttributes(hDevice, &attributes)) {
            CloseHandle(hDevice);
            continue;
        }
        
        // Проверить, является ли это мышью
        PHIDP_PREPARSED_DATA preparsedData;
        if (HidD_GetPreparsedData(hDevice, &preparsedData)) {
            HIDP_CAPS caps;
            if (HidP_GetCaps(preparsedData, &caps) == HIDP_STATUS_SUCCESS) {
                // Usage Page 1 = Generic Desktop, Usage 2 = Mouse
                if (caps.UsagePage == 1 && caps.Usage == 2) {
                    MouseDevice device;
                    device.path = devicePath;
                    device.vendorId = attributes.VendorID;
                    device.productId = attributes.ProductID;
                    device.handle = INVALID_HANDLE_VALUE; // Закроем позже
                    
                    // Получить имя продукта
                    WCHAR productString[256] = {0};
                    if (HidD_GetProductString(hDevice, productString, sizeof(productString))) {
                        device.name = productString;
                    } else {
                        device.name = L"Unknown Mouse";
                    }
                    
                    devices.push_back(device);
                }
            }
            HidD_FreePreparsedData(preparsedData);
        }
        
        CloseHandle(hDevice);
    }
    
    SetupDiDestroyDeviceInfoList(deviceInfoSet);
    return devices;
}

// Открыть устройство для отправки IOCTL
HANDLE OpenFilterDevice(const std::wstring& devicePath) {
    HANDLE hDevice = CreateFile(devicePath.c_str(),
                                GENERIC_READ | GENERIC_WRITE,
                                FILE_SHARE_READ | FILE_SHARE_WRITE,
                                NULL,
                                OPEN_EXISTING,
                                0,
                                NULL);
    
    if (hDevice == INVALID_HANDLE_VALUE) {
        DWORD error = GetLastError();
        std::wcerr << L"Failed to open device: " << devicePath << std::endl;
        std::wcerr << L"Error: " << error << std::endl;
    }
    
    return hDevice;
}

// Установить блокировку через драйвер
bool SetBlockingState(HANDLE hDevice, bool block) {
    DWORD bytesReturned;
    BOOLEAN blockFlag = block ? TRUE : FALSE;
    
    BOOL result = DeviceIoControl(hDevice,
                                  IOCTL_GYRO_SET_BLOCK,
                                  &blockFlag,
                                  sizeof(BOOLEAN),
                                  NULL,
                                  0,
                                  &bytesReturned,
                                  NULL);
    
    if (!result) {
        std::cerr << "DeviceIoControl failed with error: " << GetLastError() << std::endl;
        return false;
    }
    
    std::cout << "Blocking state set to: " << (block ? "ENABLED" : "DISABLED") << std::endl;
    return true;
}

int main() {
    std::cout << "=== GyroMouse Filter Control ===" << std::endl;
    std::cout << "This controls the kernel-mode filter driver" << std::endl << std::endl;
    
    // Перечислить все HID мыши
    std::vector<MouseDevice> mice = EnumerateHidMice();
    
    if (mice.empty()) {
        std::cerr << "No HID mice found!" << std::endl;
        return 1;
    }
    
    std::cout << "Available HID mice with filter driver:\n" << std::endl;
    for (size_t i = 0; i < mice.size(); i++) {
        std::wcout << L"[" << i << L"] " << mice[i].name;
        std::wcout << L" (VID=" << std::hex << std::uppercase << std::setw(4) << std::setfill(L'0')
                  << mice[i].vendorId << L" PID=" << std::setw(4) << mice[i].productId
                  << std::dec << L")" << std::endl;
        std::wcout << L"    Path: " << mice[i].path << std::endl;
    }
    
    std::cout << "\nEnter the number of the gyro mouse to BLOCK: ";
    int selectedIndex;
    std::cin >> selectedIndex;
    
    if (selectedIndex < 0 || selectedIndex >= (int)mice.size()) {
        std::cerr << "Invalid selection!" << std::endl;
        return 1;
    }
    
    MouseDevice& selectedMouse = mice[selectedIndex];
    
    std::wcout << L"\nSelected: " << selectedMouse.name << std::endl;
    std::wcout << L"VID=" << std::hex << std::uppercase << selectedMouse.vendorId
              << L" PID=" << selectedMouse.productId << std::dec << std::endl;
    
    // Открыть устройство
    HANDLE hDevice = OpenFilterDevice(selectedMouse.path);
    
    if (hDevice == INVALID_HANDLE_VALUE) {
        std::cerr << "\nERROR: Could not open device!" << std::endl;
        std::cerr << "Make sure the filter driver is installed for this device." << std::endl;
        std::cerr << "Run this program as Administrator." << std::endl;
        return 1;
    }
    
    std::cout << "\nDevice opened successfully!" << std::endl;
    std::cout << "Commands:" << std::endl;
    std::cout << "  1 - Enable blocking (gyro mouse will be blocked)" << std::endl;
    std::cout << "  0 - Disable blocking (gyro mouse will work normally)" << std::endl;
    std::cout << "  q - Quit" << std::endl;
    
    while (true) {
        std::cout << "\n> ";
        std::string cmd;
        std::cin >> cmd;
        
        if (cmd == "q" || cmd == "Q") {
            break;
        } else if (cmd == "1") {
            if (SetBlockingState(hDevice, true)) {
                std::cout << "SUCCESS: Gyro mouse is now BLOCKED from Windows input." << std::endl;
                std::cout << "Move the mouse - cursor should NOT move." << std::endl;
            }
        } else if (cmd == "0") {
            if (SetBlockingState(hDevice, false)) {
                std::cout << "SUCCESS: Gyro mouse blocking DISABLED." << std::endl;
                std::cout << "Mouse will work normally again." << std::endl;
            }
        } else {
            std::cout << "Unknown command. Use 1, 0, or q." << std::endl;
        }
    }
    
    // Перед выходом отключаем блокировку
    SetBlockingState(hDevice, false);
    CloseHandle(hDevice);
    
    std::cout << "\nExiting..." << std::endl;
    return 0;
}