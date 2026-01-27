#define WIN32_LEAN_AND_MEAN

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <iomanip>
#include <thread>
#include <atomic>

// Interception API
extern "C" {
    #include "interception.h"
}

#pragma comment(lib, "ws2_32.lib")

#define UDP_PORT 5556
#define HOST "127.0.0.1"
#define CONFIG_FILE "mouse_config.txt"

// Глобальные переменные
SOCKET g_socket;
sockaddr_in g_serverAddr;
std::atomic<bool> g_running(true);
InterceptionDevice g_targetDevice = 0;

struct MouseDeviceInfo {
    InterceptionDevice device;
    std::wstring hardwareId;
    std::wstring name;
};

// Инициализация UDP
bool InitUDP() {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        std::cerr << "Failed to initialize Winsock" << std::endl;
        return false;
    }
    
    g_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (g_socket == INVALID_SOCKET) {
        std::cerr << "Failed to create socket" << std::endl;
        WSACleanup();
        return false;
    }
    
    memset(&g_serverAddr, 0, sizeof(g_serverAddr));
    g_serverAddr.sin_family = AF_INET;
    g_serverAddr.sin_port = htons(UDP_PORT);
    inet_pton(AF_INET, HOST, &g_serverAddr.sin_addr);
    
    std::cout << "UDP initialized: " << HOST << ":" << UDP_PORT << std::endl;
    return true;
}

// Получить VID/PID из Hardware ID
bool GetVidPidFromHardwareId(const std::wstring& hwid, USHORT& vid, USHORT& pid) {
    size_t vidPos = hwid.find(L"VID_");
    size_t pidPos = hwid.find(L"PID_");
    
    if (vidPos == std::wstring::npos || pidPos == std::wstring::npos) {
        return false;
    }
    
    std::wstring vidStr = hwid.substr(vidPos + 4, 4);
    std::wstring pidStr = hwid.substr(pidPos + 4, 4);
    
    vid = (USHORT)std::wcstoul(vidStr.c_str(), nullptr, 16);
    pid = (USHORT)std::wcstoul(pidStr.c_str(), nullptr, 16);
    
    return true;
}

// Перечислить все мыши через Interception
std::vector<MouseDeviceInfo> EnumerateMice(InterceptionContext context) {
    std::vector<MouseDeviceInfo> devices;
    
    for (InterceptionDevice device = INTERCEPTION_MOUSE(0); 
         device <= INTERCEPTION_MOUSE(INTERCEPTION_MAX_MOUSE - 1); 
         device++) {
        
        wchar_t hardware_id[500];
        size_t length = interception_get_hardware_id(context, device, hardware_id, sizeof(hardware_id));
        
        if (length > 0 && length < sizeof(hardware_id)) {
            MouseDeviceInfo info;
            info.device = device;
            info.hardwareId = hardware_id;
            
            // Извлечь читаемое имя из Hardware ID
            std::wstring hwid_str(hardware_id);
            
            // Попытка извлечь имя устройства (обычно в конце строки)
            size_t lastSlash = hwid_str.find_last_of(L"\\");
            if (lastSlash != std::wstring::npos) {
                info.name = hwid_str.substr(lastSlash + 1);
            } else {
                info.name = L"Mouse Device";
            }
            
            devices.push_back(info);
            
            std::wcout << L"Found device " << device << L": " << hardware_id << std::endl;
        }
    }
    
    return devices;
}

// Загрузить конфигурацию
bool LoadConfig(InterceptionDevice& device) {
    std::ifstream file(CONFIG_FILE);
    if (!file.is_open()) {
        return false;
    }
    
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        
        if (line.find("DEVICE=") == 0) {
            int dev = std::stoi(line.substr(7));
            device = (InterceptionDevice)dev;
            file.close();
            return true;
        }
    }
    
    file.close();
    return false;
}

// Сохранить конфигурацию
void SaveConfig(InterceptionDevice device, const std::wstring& hardwareId) {
    std::ofstream file(CONFIG_FILE);
    if (file.is_open()) {
        file << "# Interception Device Configuration\n";
        file << "# Device ID for the gyro mouse\n";
        file << "DEVICE=" << device << "\n";
        file << "# Hardware ID: ";
        std::wcout.imbue(std::locale(""));
        for (wchar_t c : hardwareId) {
            file << (char)c;
        }
        file << "\n";
        file.close();
        std::cout << "Configuration saved to " << CONFIG_FILE << std::endl;
    }
}

// Отправить данные мыши по UDP
void SendMouseDataUDP(int deltaX, int deltaY, unsigned short buttons) {
    char buffer[64];
    int len = sprintf_s(buffer, sizeof(buffer),
        "MOUSE:%d,%d,%u,%llu",
        deltaX,
        deltaY,
        buttons,
        GetTickCount64());
    
    sendto(g_socket, buffer, len, 0,
        (sockaddr*)&g_serverAddr, sizeof(g_serverAddr));
}

// Основной цикл обработки событий
void ProcessEvents(InterceptionContext context) {
    InterceptionDevice device;
    InterceptionStroke stroke;
    
    std::cout << "\n=== Starting event loop ===" << std::endl;
    std::cout << "Target device: " << g_targetDevice << std::endl;
    std::cout << "Blocking enabled for gyro mouse" << std::endl;
    std::cout << "Other mice will work normally\n" << std::endl;
    
    ULONGLONG lastPrintTime = GetTickCount64();
    int blockedEvents = 0;
    int passedEvents = 0;
    
    while (g_running && interception_receive(context, device = interception_wait(context), &stroke, 1) > 0) {
        
        if (!interception_is_mouse(device)) {
            // Не мышь, пропускаем
            interception_send(context, device, &stroke, 1);
            continue;
        }
        
        InterceptionMouseStroke& mstroke = *(InterceptionMouseStroke*)&stroke;
        
        if (device == g_targetDevice) {
            // Это наша целевая гиро-мышь - БЛОКИРУЕМ и отправляем по UDP
            
            // Отправить данные по UDP
            unsigned short buttons = 0;
            if (mstroke.state & INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN) buttons = 1;
            if (mstroke.state & INTERCEPTION_MOUSE_RIGHT_BUTTON_DOWN) buttons = 2;
            
            if (mstroke.x != 0 || mstroke.y != 0) {
                SendMouseDataUDP(mstroke.x, mstroke.y, buttons);
                blockedEvents++;
                
                // Вывод в консоль (раз в секунду)
                if (GetTickCount64() - lastPrintTime > 1000) {
                    std::cout << "Stats: Blocked=" << blockedEvents 
                             << " Passed=" << passedEvents 
                             << " (Delta: X=" << mstroke.x << " Y=" << mstroke.y << ")"
                             << std::endl;
                    lastPrintTime = GetTickCount64();
                    blockedEvents = 0;
                    passedEvents = 0;
                }
            }
            
            // НЕ пересылаем событие в Windows - мышь заблокирована!
            // interception_send() НЕ вызываем!
            
        } else {
            // Это другая мышь - пересылаем в Windows как обычно
            interception_send(context, device, &stroke, 1);
            passedEvents++;
        }
    }
    
    std::cout << "\nEvent loop terminated" << std::endl;
}

// Обработчик Ctrl+C
BOOL WINAPI ConsoleHandler(DWORD signal) {
    if (signal == CTRL_C_EVENT || signal == CTRL_BREAK_EVENT) {
        std::cout << "\n\nShutting down..." << std::endl;
        g_running = false;
        return TRUE;
    }
    return FALSE;
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  Gyro Mouse Blocker (Interception)" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "UDP Target: " << HOST << ":" << UDP_PORT << "\n" << std::endl;
    
    // Проверка прав администратора
    BOOL isAdmin = FALSE;
    PSID adminGroup = NULL;
    SID_IDENTIFIER_AUTHORITY ntAuthority = SECURITY_NT_AUTHORITY;
    
    if (AllocateAndInitializeSid(&ntAuthority, 2, SECURITY_BUILTIN_DOMAIN_RID,
                                  DOMAIN_ALIAS_RID_ADMINS, 0, 0, 0, 0, 0, 0, &adminGroup)) {
        CheckTokenMembership(NULL, adminGroup, &isAdmin);
        FreeSid(adminGroup);
    }
    
    if (!isAdmin) {
        std::cerr << "ERROR: This program must be run as Administrator!" << std::endl;
        std::cerr << "Right-click and select 'Run as administrator'" << std::endl;
        system("pause");
        return 1;
    }
    
    // Инициализация UDP
    if (!InitUDP()) {
        return 1;
    }
    
    // Создать контекст Interception
    std::cout << "Initializing Interception driver..." << std::endl;
    InterceptionContext context = interception_create_context();
    
    if (!context) {
        std::cerr << "\nERROR: Failed to create Interception context!" << std::endl;
        std::cerr << "\nPossible reasons:" << std::endl;
        std::cerr << "1. Interception driver is not installed" << std::endl;
        std::cerr << "   Run: install-interception.exe /install" << std::endl;
        std::cerr << "2. Not running as Administrator" << std::endl;
        std::cerr << "3. Test signing is not enabled" << std::endl;
        std::cerr << "   Run: bcdedit /set testsigning on" << std::endl;
        std::cerr << "4. Need to restart after driver installation" << std::endl;
        system("pause");
        return 1;
    }
    
    std::cout << "Interception context created successfully!\n" << std::endl;
    
    // Перечислить все мыши
    std::cout << "Enumerating mouse devices..." << std::endl;
    std::vector<MouseDeviceInfo> mice = EnumerateMice(context);
    
    if (mice.empty()) {
        std::cerr << "No mouse devices found!" << std::endl;
        interception_destroy_context(context);
        return 1;
    }
    
    std::cout << "\nFound " << mice.size() << " mouse device(s)\n" << std::endl;
    
    // Попытка загрузить конфигурацию
    InterceptionDevice configDevice = 0;
    bool hasConfig = LoadConfig(configDevice);
    
    int selectedIndex = -1;
    
    if (hasConfig) {
        std::cout << "Found config file with DEVICE=" << configDevice << std::endl;
        
        // Проверить, существует ли это устройство
        for (size_t i = 0; i < mice.size(); i++) {
            if (mice[i].device == configDevice) {
                selectedIndex = (int)i;
                std::cout << "Found matching device:" << std::endl;
                std::wcout << L"  Device " << mice[i].device << L": " << mice[i].hardwareId << std::endl;
                break;
            }
        }
        
        if (selectedIndex == -1) {
            std::cout << "Device from config not found. Please select manually.\n" << std::endl;
        }
    }
    
    // Если не нашли в конфиге, показать список
    if (selectedIndex == -1) {
        std::cout << "Available mouse devices:" << std::endl;
        std::cout << "----------------------------------------" << std::endl;
        
        for (size_t i = 0; i < mice.size(); i++) {
            std::wcout << L"[" << i << L"] Device " << mice[i].device << std::endl;
            std::wcout << L"    Hardware ID: " << mice[i].hardwareId << std::endl;
            
            // Показать VID/PID если есть
            USHORT vid, pid;
            if (GetVidPidFromHardwareId(mice[i].hardwareId, vid, pid)) {
                std::wcout << L"    VID=" << std::hex << std::uppercase << std::setw(4) 
                          << std::setfill(L'0') << vid 
                          << L" PID=" << std::setw(4) << pid << std::dec << std::endl;
            }
            std::cout << std::endl;
        }
        
        std::cout << "Enter the number of the gyro mouse to BLOCK: ";
        std::cin >> selectedIndex;
        
        if (selectedIndex < 0 || selectedIndex >= (int)mice.size()) {
            std::cerr << "Invalid selection!" << std::endl;
            interception_destroy_context(context);
            return 1;
        }
        
        // Сохранить выбор
        SaveConfig(mice[selectedIndex].device, mice[selectedIndex].hardwareId);
    }
    
    // Установить целевое устройство
    g_targetDevice = mice[selectedIndex].device;
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "Configuration:" << std::endl;
    std::cout << "----------------------------------------" << std::endl;
    std::cout << "Target Device: " << g_targetDevice << std::endl;
    std::wcout << L"Hardware ID: " << mice[selectedIndex].hardwareId << std::endl;
    std::cout << "UDP Destination: " << HOST << ":" << UDP_PORT << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    std::cout << "This mouse will be BLOCKED from Windows." << std::endl;
    std::cout << "All other mice will work normally." << std::endl;
    std::cout << "Press Ctrl+C to exit.\n" << std::endl;
    
    // Установить фильтр для всех мышей
    interception_set_filter(context, interception_is_mouse, INTERCEPTION_FILTER_MOUSE_ALL);
    
    // Установить обработчик Ctrl+C
    SetConsoleCtrlHandler(ConsoleHandler, TRUE);
    
    // Запустить обработку событий
    ProcessEvents(context);
    
    // Очистка
    std::cout << "Cleaning up..." << std::endl;
    interception_destroy_context(context);
    closesocket(g_socket);
    WSACleanup();
    
    std::cout << "Goodbye!" << std::endl;
    return 0;
}