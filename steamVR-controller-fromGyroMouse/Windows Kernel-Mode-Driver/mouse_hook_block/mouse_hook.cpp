#define WIN32_LEAN_AND_MEAN

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <hidsdi.h>
#include <setupapi.h>
#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <iomanip>

#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "hid.lib")
#pragma comment(lib, "setupapi.lib")

#define UDP_PORT 5556
#define HOST "127.0.0.1"
#define CONFIG_FILE "mouse_config.txt"

SOCKET g_socket;
sockaddr_in g_serverAddr;
HWND g_hwnd;
HANDLE g_targetMouseHandle = nullptr;
bool g_capturing = true;

struct MouseDevice {
    std::wstring name;
    std::wstring path;
    USHORT vendorId;
    USHORT productId;
    HANDLE handle;
};

// Получить VID/PID из пути устройства
bool GetVidPidFromPath(const std::wstring& path, USHORT& vid, USHORT& pid) {
    // Формат: \\?\HID#VID_XXXX&PID_YYYY#...
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

// Перечислить все мыши
std::vector<MouseDevice> EnumerateMice() {
    std::vector<MouseDevice> devices;
    UINT numDevices = 0;
    
    // Получить количество устройств
    if (GetRawInputDeviceList(nullptr, &numDevices, sizeof(RAWINPUTDEVICELIST)) != 0) {
        return devices;
    }
    
    std::vector<RAWINPUTDEVICELIST> deviceList(numDevices);
    if (GetRawInputDeviceList(deviceList.data(), &numDevices, sizeof(RAWINPUTDEVICELIST)) == (UINT)-1) {
        return devices;
    }
    
    for (UINT i = 0; i < numDevices; i++) {
        if (deviceList[i].dwType != RIM_TYPEMOUSE) {
            continue;
        }
        
        UINT nameSize = 0;
        GetRawInputDeviceInfoW(deviceList[i].hDevice, RIDI_DEVICENAME, nullptr, &nameSize);
        
        if (nameSize == 0) continue;
        
        std::vector<WCHAR> nameBuf(nameSize);
        if (GetRawInputDeviceInfoW(deviceList[i].hDevice, RIDI_DEVICENAME, nameBuf.data(), &nameSize) == (UINT)-1) {
            continue;
        }
        
        std::wstring devicePath(nameBuf.data());
        
        MouseDevice device;
        device.path = devicePath;
        device.handle = deviceList[i].hDevice;
        
        // Получить VID/PID
        if (!GetVidPidFromPath(devicePath, device.vendorId, device.productId)) {
            device.vendorId = 0;
            device.productId = 0;
        }
        
        // Попытаться получить имя устройства
        HANDLE hDevice = CreateFileW(
            devicePath.c_str(),
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            nullptr,
            OPEN_EXISTING,
            0,
            nullptr
        );
        
        if (hDevice != INVALID_HANDLE_VALUE) {
            WCHAR productString[256] = {0};
            if (HidD_GetProductString(hDevice, productString, sizeof(productString))) {
                device.name = productString;
            }
            CloseHandle(hDevice);
        }
        
        if (device.name.empty()) {
            device.name = L"Unknown Mouse";
        }
        
        devices.push_back(device);
    }
    
    return devices;
}

// Инициализация UDP
bool InitUDP() {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        return false;
    }
    
    g_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (g_socket == INVALID_SOCKET) {
        WSACleanup();
        return false;
    }
    
    memset(&g_serverAddr, 0, sizeof(g_serverAddr));
    g_serverAddr.sin_family = AF_INET;
    g_serverAddr.sin_port = htons(UDP_PORT);
    inet_pton(AF_INET, HOST, &g_serverAddr.sin_addr);
    
    return true;
}

// Обработчик Raw Input
LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        case WM_INPUT: {
            if (!g_capturing) break;
            
            UINT size = 0;
            GetRawInputData((HRAWINPUT)lParam, RID_INPUT, nullptr, &size, sizeof(RAWINPUTHEADER));
            
            std::vector<BYTE> buffer(size);
            if (GetRawInputData((HRAWINPUT)lParam, RID_INPUT, buffer.data(), &size, sizeof(RAWINPUTHEADER)) != size) {
                break;
            }
            
            RAWINPUT* raw = (RAWINPUT*)buffer.data();
            
            // Проверяем, что это событие от нужной мыши
            if (raw->header.dwType == RIM_TYPEMOUSE && raw->header.hDevice == g_targetMouseHandle) {
                RAWMOUSE& mouse = raw->data.mouse;
                
                // Отправляем данные по UDP
                char udpBuffer[64];
                int len = sprintf_s(udpBuffer, sizeof(udpBuffer),
                    "MOUSE:%d,%d,%u,%llu",
                    (int)mouse.lLastX,
                    (int)mouse.lLastY,
                    (mouse.ulButtons & RI_MOUSE_BUTTON_1_DOWN) ? 1 :
                    (mouse.ulButtons & RI_MOUSE_BUTTON_2_DOWN) ? 2 : 0,
                    GetTickCount64());
                
                sendto(g_socket, udpBuffer, len, 0,
                    (sockaddr*)&g_serverAddr, sizeof(g_serverAddr));
                
                std::cout << "Mouse delta: X=" << mouse.lLastX << " Y=" << mouse.lLastY << std::endl;
            }
            break;
        }
        
        case WM_DESTROY:
            PostQuitMessage(0);
            break;
            
        default:
            return DefWindowProc(hwnd, msg, wParam, lParam);
    }
    return 0;
}

// Попытка загрузить VID/PID из конфиг-файла
bool LoadConfigFile(USHORT& vid, USHORT& pid) {
    std::ifstream file(CONFIG_FILE);
    if (!file.is_open()) {
        return false;
    }
    
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        
        size_t vidPos = line.find("VID=");
        size_t pidPos = line.find("PID=");
        
        if (vidPos != std::string::npos && pidPos != std::string::npos) {
            std::string vidStr = line.substr(vidPos + 4, 4);
            std::string pidStr = line.substr(pidPos + 4, 4);
            
            vid = (USHORT)std::stoul(vidStr, nullptr, 16);
            pid = (USHORT)std::stoul(pidStr, nullptr, 16);
            
            file.close();
            return true;
        }
    }
    
    file.close();
    return false;
}

// Сохранить выбор в конфиг-файл
void SaveConfigFile(USHORT vid, USHORT pid) {
    std::ofstream file(CONFIG_FILE);
    if (file.is_open()) {
        file << "# Mouse VID/PID configuration\n";
        file << "# Format: VID=XXXX PID=YYYY\n";
        file << "VID=" << std::hex << std::uppercase << std::setw(4) << std::setfill('0') << vid;
        file << " PID=" << std::hex << std::uppercase << std::setw(4) << std::setfill('0') << pid << "\n";
        file.close();
        std::cout << "Configuration saved to " << CONFIG_FILE << std::endl;
    }
}

int main() {
    std::cout << "=== Mouse Capture for Specific Device ===" << std::endl;
    std::cout << "Sending captured mouse data to UDP port " << UDP_PORT << std::endl << std::endl;
    
    if (!InitUDP()) {
        std::cerr << "Failed to initialize UDP" << std::endl;
        return 1;
    }
    
    // Перечислить все мыши
    std::vector<MouseDevice> mice = EnumerateMice();
    
    if (mice.empty()) {
        std::cerr << "No mice found!" << std::endl;
        return 1;
    }
    
    // Попытка загрузить из конфига
    USHORT configVid = 0, configPid = 0;
    bool hasConfig = LoadConfigFile(configVid, configPid);
    
    int selectedIndex = -1;
    
    if (hasConfig) {
        std::cout << "Found config file with VID=" << std::hex << std::uppercase 
                  << configVid << " PID=" << configPid << std::dec << std::endl;
        std::cout << "Looking for matching device..." << std::endl;
        
        for (size_t i = 0; i < mice.size(); i++) {
            if (mice[i].vendorId == configVid && mice[i].productId == configPid) {
                selectedIndex = (int)i;
                std::cout << "Found matching device: " << std::endl;
                std::wcout << L"  [" << i << L"] " << mice[i].name 
                          << L" (VID=" << std::hex << std::uppercase << mice[i].vendorId
                          << L" PID=" << mice[i].productId << L")" << std::dec << std::endl;
                break;
            }
        }
        
        if (selectedIndex == -1) {
            std::cout << "Device from config not found. Please select manually." << std::endl;
        }
    }
    
    // Если не нашли в конфиге, показываем список
    if (selectedIndex == -1) {
        std::cout << "\nAvailable mice:" << std::endl;
        for (size_t i = 0; i < mice.size(); i++) {
            std::wcout << L"[" << i << L"] " << mice[i].name;
            if (mice[i].vendorId != 0) {
                std::wcout << L" (VID=" << std::hex << std::uppercase << std::setw(4) << std::setfill(L'0') 
                          << mice[i].vendorId << L" PID=" << std::setw(4) << mice[i].productId 
                          << std::dec << L")";
            }
            std::wcout << std::endl;
        }
        
        std::cout << "\nEnter the number of the mouse to capture: ";
        std::cin >> selectedIndex;
        
        if (selectedIndex < 0 || selectedIndex >= (int)mice.size()) {
            std::cerr << "Invalid selection!" << std::endl;
            return 1;
        }
        
        // Сохранить выбор
        if (mice[selectedIndex].vendorId != 0) {
            SaveConfigFile(mice[selectedIndex].vendorId, mice[selectedIndex].productId);
        }
    }
    
    MouseDevice& selectedMouse = mice[selectedIndex];
    g_targetMouseHandle = selectedMouse.handle;
    
    std::wcout << L"\nSelected mouse: " << selectedMouse.name << std::endl;
    if (selectedMouse.vendorId != 0) {
        std::wcout << L"VID=" << std::hex << std::uppercase << selectedMouse.vendorId 
                  << L" PID=" << selectedMouse.productId << std::dec << std::endl;
    }
    
    // Создать скрытое окно для обработки сообщений
    WNDCLASSEX wc = {0};
    wc.cbSize = sizeof(WNDCLASSEX);
    wc.lpfnWndProc = WndProc;
    wc.hInstance = GetModuleHandle(nullptr);
    wc.lpszClassName = L"MouseCaptureClass";
    
    if (!RegisterClassEx(&wc)) {
        std::cerr << "Failed to register window class" << std::endl;
        return 1;
    }
    
    g_hwnd = CreateWindowEx(0, L"MouseCaptureClass", L"Mouse Capture", 0, 
                           0, 0, 0, 0, HWND_MESSAGE, nullptr, wc.hInstance, nullptr);
    
    if (!g_hwnd) {
        std::cerr << "Failed to create window" << std::endl;
        return 1;
    }
    
    // Зарегистрировать Raw Input для всех мышей (фильтрация будет в обработчике)
    RAWINPUTDEVICE rid;
    rid.usUsagePage = 0x01;  // Generic Desktop
    rid.usUsage = 0x02;      // Mouse
    rid.dwFlags = RIDEV_INPUTSINK | RIDEV_NOLEGACY; // NOLEGACY блокирует стандартные события мыши!
    rid.hwndTarget = g_hwnd;
    
    if (!RegisterRawInputDevices(&rid, 1, sizeof(RAWINPUTDEVICE))) {
        std::cerr << "Failed to register raw input device" << std::endl;
        return 1;
    }
    
    std::cout << "\nCapture active! Press Ctrl+C to exit." << std::endl;
    std::cout << "Move your gyro mouse to see data..." << std::endl;
    
    // Основной цикл сообщений
    MSG msg;
    while (GetMessage(&msg, nullptr, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    
    // Очистка
    closesocket(g_socket);
    WSACleanup();
    
    return 0;
}