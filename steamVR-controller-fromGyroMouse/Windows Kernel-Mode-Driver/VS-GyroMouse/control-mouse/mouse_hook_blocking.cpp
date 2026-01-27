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
#include <atomic>

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
HHOOK g_mouseHook = nullptr;
std::atomic<bool> g_capturing(true);
std::atomic<LONG> g_lastRawX(0);
std::atomic<LONG> g_lastRawY(0);
std::atomic<ULONGLONG> g_lastRawTime(0);

struct MouseDevice {
    std::wstring name;
    std::wstring path;
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

// Low-Level Mouse Hook для блокировки событий
LRESULT CALLBACK LowLevelMouseProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode >= 0 && wParam == WM_MOUSEMOVE) {
        ULONGLONG currentTime = GetTickCount64();
        ULONGLONG lastTime = g_lastRawTime.load();
        
        // Если событие произошло в течение 10ms после Raw Input события
        // от нашей целевой мыши, блокируем его
        if (currentTime - lastTime < 10) {
            // Это скорее всего событие от нашей гиро-мыши
            return 1; // Блокируем
        }
    }
    
    return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
}

// Перечислить все мыши
std::vector<MouseDevice> EnumerateMice() {
    std::vector<MouseDevice> devices;
    UINT numDevices = 0;
    
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
        
        if (!GetVidPidFromPath(devicePath, device.vendorId, device.productId)) {
            device.vendorId = 0;
            device.productId = 0;
        }
        
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
                
                // Сохраняем время и координаты для hook'а
                g_lastRawX = (LONG)mouse.lLastX;
                g_lastRawY = (LONG)mouse.lLastY;
                g_lastRawTime = GetTickCount64();
                
                // Отправляем данные по UDP
                char udpBuffer[64];
                int len = sprintf_s(udpBuffer, sizeof(udpBuffer),
                    "MOUSE:%d,%d,%u,%llu",
                    (int)mouse.lLastX,
                    (int)mouse.lLastY,
                    (mouse.ulButtons & RI_MOUSE_BUTTON_1_DOWN) ? 1 :
                    (mouse.ulButtons & RI_MOUSE_BUTTON_2_DOWN) ? 2 : 0,
                    g_lastRawTime.load());
                
                sendto(g_socket, udpBuffer, len, 0,
                    (sockaddr*)&g_serverAddr, sizeof(g_serverAddr));
                
                if (mouse.lLastX != 0 || mouse.lLastY != 0) {
                    std::cout << "Gyro mouse: X=" << mouse.lLastX << " Y=" << mouse.lLastY << std::endl;
                }
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

// Загрузить VID/PID из конфига
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

// Сохранить выбор в конфиг
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
    std::cout << "=== GyroMouse Capture with Blocking ===" << std::endl;
    std::cout << "This will BLOCK the selected gyro mouse from moving cursor" << std::endl;
    std::cout << "Sending data to UDP port " << UDP_PORT << std::endl << std::endl;
    
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
        
        std::cout << "\nEnter the number of the GYRO mouse to capture and block: ";
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
    
    std::wcout << L"\nSelected gyro mouse: " << selectedMouse.name << std::endl;
    if (selectedMouse.vendorId != 0) {
        std::wcout << L"VID=" << std::hex << std::uppercase << selectedMouse.vendorId 
                  << L" PID=" << selectedMouse.productId << std::dec << std::endl;
    }
    
    std::cout << "\nThis mouse will be BLOCKED from controlling cursor." << std::endl;
    std::cout << "Other mice will work normally.\n" << std::endl;
    
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
    
    // Зарегистрировать Raw Input
    RAWINPUTDEVICE rid;
    rid.usUsagePage = 0x01;
    rid.usUsage = 0x02;
    rid.dwFlags = RIDEV_INPUTSINK;
    rid.hwndTarget = g_hwnd;
    
    if (!RegisterRawInputDevices(&rid, 1, sizeof(RAWINPUTDEVICE))) {
        std::cerr << "Failed to register raw input device" << std::endl;
        return 1;
    }
    
    // Установить Low-Level Mouse Hook для блокировки
    g_mouseHook = SetWindowsHookEx(WH_MOUSE_LL, LowLevelMouseProc, 
                                   GetModuleHandle(nullptr), 0);
    if (!g_mouseHook) {
        std::cerr << "Failed to install mouse hook" << std::endl;
        std::cerr << "Error: " << GetLastError() << std::endl;
        return 1;
    }
    
    std::cout << "Capture and blocking active!" << std::endl;
    std::cout << "Move gyro mouse - cursor should NOT move" << std::endl;
    std::cout << "Regular mouse should work normally" << std::endl;
    std::cout << "Press Ctrl+C to exit\n" << std::endl;
    
    // Основной цикл сообщений
    MSG msg;
    while (GetMessage(&msg, nullptr, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    
    // Очистка
    if (g_mouseHook) {
        UnhookWindowsHookEx(g_mouseHook);
    }
    closesocket(g_socket);
    WSACleanup();
    
    return 0;
}