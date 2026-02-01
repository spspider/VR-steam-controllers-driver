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
#include <cmath>

#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "hid.lib")
#pragma comment(lib, "setupapi.lib")

#define HUB_PORT 5556
#define HUB_HOST "127.0.0.1"
#define CONFIG_FILE "mouse_config.txt"

SOCKET g_socket;
sockaddr_in g_hubAddr;
HWND g_hwnd;
HANDLE g_targetMouseHandle = nullptr;
bool g_capturing = true;
bool g_blockCursor = true;  // Блокировать курсор по умолчанию

// Параметры контроллера
int g_controllerId = 0;  // 0 = left, 1 = right
uint32_t g_packetNumber = 0;

// Интегрированная ориентация (из гироскопа)
struct Orientation {
    float yaw = 0.0f;
    float pitch = 0.0f;
    float roll = 0.0f;
    
    // Для вычисления скорости вращения
    ULONGLONG lastTime = 0;
    float lastYaw = 0.0f;
    float lastPitch = 0.0f;
    float lastRoll = 0.0f;
};

Orientation g_orientation;

// Виртуальная позиция мыши (для дополнительных данных)
struct VirtualMousePosition {
    float x = 0.0f;  // Нормализованная позиция -1.0 до 1.0
    float y = 0.0f;
    float screenX = 0.0f;  // Реальная позиция на экране
    float screenY = 0.0f;
};

VirtualMousePosition g_mousePos;

// Состояние кнопок
struct ButtonState {
    bool button1 = false;
    bool button2 = false;
    bool button3 = false;
    uint8_t trigger = 0;  // 0-255
};

ButtonState g_buttons;

struct MouseDevice {
    std::wstring name;
    std::wstring path;
    USHORT vendorId;
    USHORT productId;
    HANDLE handle;
};

// =================== КОНВЕРТАЦИЯ УГЛОВ В QUATERNION ===================

void EulerToQuaternion(float yaw, float pitch, float roll, float* quat) {
    // Конвертация Euler angles в quaternion (w, x, y, z)
    float cy = cosf(yaw * 0.5f);
    float sy = sinf(yaw * 0.5f);
    float cp = cosf(pitch * 0.5f);
    float sp = sinf(pitch * 0.5f);
    float cr = cosf(roll * 0.5f);
    float sr = sinf(roll * 0.5f);
    
    quat[0] = cr * cp * cy + sr * sp * sy;  // w
    quat[1] = sr * cp * cy - cr * sp * sy;  // x
    quat[2] = cr * sp * cy + sr * cp * sy;  // y
    quat[3] = cr * cp * sy - sr * sp * cy;  // z
}

// =================== ПОСТРОЕНИЕ ПАКЕТА ДЛЯ HUB ===================

std::vector<BYTE> BuildHubPacket() {
    /*
     * Расширенный протокол для Hub (65 байт):
     * 
     * Offset  Size  Type     Field
     * ------  ----  -------  ---------------------------
     * 0       1     uint8    controller_id (0=left, 1=right)
     * 1       4     uint32   packet_number
     * 5       16    float32  quaternion[4] (w, x, y, z)
     * 21      12    float32  position[3] (x, y, z) - пока 0,0,0
     * 33      12    float32  gyro[3] (angular velocity)
     * 45      2     uint16   buttons
     * 47      1     uint8    trigger
     * 48      8     float32  mouse_screen_pos[2] (x, y)
     * 56      8     float32  mouse_virtual_pos[2] (normalized)
     * 64      1     uint8    checksum
     */
    
    std::vector<BYTE> packet(65);
    size_t offset = 0;
    
    // 1. Controller ID
    packet[offset++] = (BYTE)g_controllerId;
    
    // 2. Packet number
    *reinterpret_cast<uint32_t*>(&packet[offset]) = g_packetNumber++;
    offset += 4;
    
    // 3. Quaternion (from Euler angles)
    float quat[4];
    EulerToQuaternion(g_orientation.yaw, g_orientation.pitch, g_orientation.roll, quat);
    
    for (int i = 0; i < 4; i++) {
        *reinterpret_cast<float*>(&packet[offset]) = quat[i];
        offset += 4;
    }
    
    // 4. Position (пока заполнено нулями, Hub вычислит позицию из ArUco)
    for (int i = 0; i < 3; i++) {
        *reinterpret_cast<float*>(&packet[offset]) = 0.0f;
        offset += 4;
    }
    
    // 5. Gyro (angular velocity) - вычисляем из изменения ориентации
    ULONGLONG now = GetTickCount64();
    float dt = (now - g_orientation.lastTime) / 1000.0f;  // в секундах
    
    if (dt > 0.001f && g_orientation.lastTime > 0) {
        float gyro_x = (g_orientation.pitch - g_orientation.lastPitch) / dt;
        float gyro_y = (g_orientation.yaw - g_orientation.lastYaw) / dt;
        float gyro_z = (g_orientation.roll - g_orientation.lastRoll) / dt;
        
        *reinterpret_cast<float*>(&packet[offset]) = gyro_x;
        offset += 4;
        *reinterpret_cast<float*>(&packet[offset]) = gyro_y;
        offset += 4;
        *reinterpret_cast<float*>(&packet[offset]) = gyro_z;
        offset += 4;
    } else {
        offset += 12;  // Пропустить gyro
    }
    
    g_orientation.lastTime = now;
    g_orientation.lastYaw = g_orientation.yaw;
    g_orientation.lastPitch = g_orientation.pitch;
    g_orientation.lastRoll = g_orientation.roll;
    
    // 6. Buttons (16 bit)
    uint16_t buttons = 0;
    if (g_buttons.button1) buttons |= 0x0001;
    if (g_buttons.button2) buttons |= 0x0002;
    if (g_buttons.button3) buttons |= 0x0004;
    
    *reinterpret_cast<uint16_t*>(&packet[offset]) = buttons;
    offset += 2;
    
    // 7. Trigger (0-255)
    packet[offset++] = g_buttons.trigger;
    
    // 8. Mouse screen position (абсолютная позиция на экране)
    *reinterpret_cast<float*>(&packet[offset]) = g_mousePos.screenX;
    offset += 4;
    *reinterpret_cast<float*>(&packet[offset]) = g_mousePos.screenY;
    offset += 4;
    
    // 9. Mouse virtual position (нормализованная -1 до 1)
    *reinterpret_cast<float*>(&packet[offset]) = g_mousePos.x;
    offset += 4;
    *reinterpret_cast<float*>(&packet[offset]) = g_mousePos.y;
    offset += 4;
    
    // 10. Checksum
    uint8_t checksum = 0;
    for (size_t i = 0; i < 64; i++) {
        checksum += packet[i];
    }
    packet[64] = checksum;
    
    return packet;
}

// =================== ПОЛУЧЕНИЕ VID/PID ===================

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

// =================== ПЕРЕЧИСЛЕНИЕ МЫШЕЙ ===================

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

// =================== ИНИЦИАЛИЗАЦИЯ UDP ===================

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
    
    memset(&g_hubAddr, 0, sizeof(g_hubAddr));
    g_hubAddr.sin_family = AF_INET;
    g_hubAddr.sin_port = htons(HUB_PORT);
    inet_pton(AF_INET, HUB_HOST, &g_hubAddr.sin_addr);
    
    return true;
}

// =================== БЛОКИРОВКА/РАЗБЛОКИРОВКА КУРСОРА ===================

void BlockCursor(bool block) {
    if (block) {
        // Скрыть курсор и заблокировать в центре экрана
        ShowCursor(FALSE);
        
        // Получить центр экрана
        int screenWidth = GetSystemMetrics(SM_CXSCREEN);
        int screenHeight = GetSystemMetrics(SM_CYSCREEN);
        
        RECT rect;
        rect.left = screenWidth / 2;
        rect.top = screenHeight / 2;
        rect.right = rect.left + 1;
        rect.bottom = rect.top + 1;
        
        ClipCursor(&rect);
        SetCursorPos(screenWidth / 2, screenHeight / 2);
        
        std::cout << "Cursor blocked (hidden and centered)" << std::endl;
    } else {
        // Разблокировать курсор
        ClipCursor(nullptr);
        ShowCursor(TRUE);
        
        std::cout << "Cursor unblocked" << std::endl;
    }
}

// =================== ОБРАБОТЧИК RAW INPUT ===================

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
                
                // Обработка кнопок
                if (mouse.ulButtons & RI_MOUSE_BUTTON_1_DOWN) g_buttons.button1 = true;
                if (mouse.ulButtons & RI_MOUSE_BUTTON_1_UP) g_buttons.button1 = false;
                if (mouse.ulButtons & RI_MOUSE_BUTTON_2_DOWN) g_buttons.button2 = true;
                if (mouse.ulButtons & RI_MOUSE_BUTTON_2_UP) g_buttons.button2 = false;
                if (mouse.ulButtons & RI_MOUSE_BUTTON_3_DOWN) g_buttons.button3 = true;
                if (mouse.ulButtons & RI_MOUSE_BUTTON_3_UP) g_buttons.button3 = false;
                
                // Триггер (используем кнопку 1 как аналоговый триггер)
                g_buttons.trigger = g_buttons.button1 ? 255 : 0;
                
                // Интегрировать движение мыши в ориентацию
                float sensitivity = 0.001f;  // Чувствительность (настраивается)
                
                int dx = mouse.lLastX;
                int dy = mouse.lLastY;
                
                g_orientation.yaw += dx * sensitivity;
                g_orientation.pitch += dy * sensitivity;
                
                // Ограничить pitch (не переворачиваться)
                const float maxPitch = 3.14159f / 2.0f;  // 90 градусов
                if (g_orientation.pitch > maxPitch) g_orientation.pitch = maxPitch;
                if (g_orientation.pitch < -maxPitch) g_orientation.pitch = -maxPitch;
                
                // Обновить виртуальную позицию мыши на экране
                POINT cursorPos;
                if (GetCursorPos(&cursorPos)) {
                    int screenWidth = GetSystemMetrics(SM_CXSCREEN);
                    int screenHeight = GetSystemMetrics(SM_CYSCREEN);
                    
                    g_mousePos.screenX = (float)cursorPos.x;
                    g_mousePos.screenY = (float)cursorPos.y;
                    
                    // Нормализовать (-1 до 1)
                    g_mousePos.x = (cursorPos.x - screenWidth / 2.0f) / (screenWidth / 2.0f);
                    g_mousePos.y = (cursorPos.y - screenHeight / 2.0f) / (screenHeight / 2.0f);
                }
                
                // Построить и отправить пакет в Hub
                std::vector<BYTE> packet = BuildHubPacket();
                sendto(g_socket, (const char*)packet.data(), (int)packet.size(), 0,
                    (sockaddr*)&g_hubAddr, sizeof(g_hubAddr));
                
                // Лог каждые 100 пакетов
                static int logCounter = 0;
                if (++logCounter % 100 == 0) {
                    std::cout << "Packet #" << g_packetNumber 
                              << " | Yaw: " << std::fixed << std::setprecision(2) << g_orientation.yaw
                              << " Pitch: " << g_orientation.pitch
                              << " | Buttons: " << (g_buttons.button1 ? "1" : "0")
                              << (g_buttons.button2 ? "2" : "0") << std::endl;
                }
            }
            break;
        }
        
        case WM_KEYDOWN: {
            // Горячие клавиши
            if (wParam == VK_F1) {
                // Toggle cursor blocking
                g_blockCursor = !g_blockCursor;
                BlockCursor(g_blockCursor);
            }
            else if (wParam == VK_F2) {
                // Reset orientation
                g_orientation.yaw = 0.0f;
                g_orientation.pitch = 0.0f;
                g_orientation.roll = 0.0f;
                std::cout << "Orientation reset!" << std::endl;
            }
            else if (wParam == VK_ESCAPE) {
                // Exit
                PostQuitMessage(0);
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

// =================== КОНФИГУРАЦИЯ ===================

bool LoadConfigFile(USHORT& vid, USHORT& pid, int& controllerId) {
    std::ifstream file(CONFIG_FILE);
    if (!file.is_open()) {
        return false;
    }
    
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        
        size_t vidPos = line.find("VID=");
        size_t pidPos = line.find("PID=");
        size_t ctrlPos = line.find("CONTROLLER=");
        
        if (vidPos != std::string::npos && pidPos != std::string::npos) {
            std::string vidStr = line.substr(vidPos + 4, 4);
            std::string pidStr = line.substr(pidPos + 4, 4);
            
            vid = (USHORT)std::stoul(vidStr, nullptr, 16);
            pid = (USHORT)std::stoul(pidStr, nullptr, 16);
            
            if (ctrlPos != std::string::npos) {
                std::string ctrlStr = line.substr(ctrlPos + 11, 1);
                controllerId = std::stoi(ctrlStr);
            }
            
            file.close();
            return true;
        }
    }
    
    file.close();
    return false;
}

void SaveConfigFile(USHORT vid, USHORT pid, int controllerId) {
    std::ofstream file(CONFIG_FILE);
    if (file.is_open()) {
        file << "# Mouse VID/PID and Controller ID configuration\n";
        file << "# Format: VID=XXXX PID=YYYY CONTROLLER=N\n";
        file << "# Controller: 0=Left, 1=Right\n";
        file << "VID=" << std::hex << std::uppercase << std::setw(4) << std::setfill('0') << vid;
        file << " PID=" << std::setw(4) << pid;
        file << " CONTROLLER=" << std::dec << controllerId << "\n";
        file.close();
        std::cout << "Configuration saved to " << CONFIG_FILE << std::endl;
    }
}

// =================== MAIN ===================

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  VR Gyro Mouse Controller v2.0" << std::endl;
    std::cout << "  Sending to Hub at " << HUB_HOST << ":" << HUB_PORT << std::endl;
    std::cout << "========================================" << std::endl << std::endl;
    
    if (!InitUDP()) {
        std::cerr << "Failed to initialize UDP!" << std::endl;
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
    int configCtrl = 0;
    bool hasConfig = LoadConfigFile(configVid, configPid, configCtrl);
    
    int selectedIndex = -1;
    
    if (hasConfig) {
        std::cout << "Found config: VID=" << std::hex << std::uppercase 
                  << configVid << " PID=" << configPid 
                  << " Controller=" << std::dec << configCtrl << std::endl;
        
        for (size_t i = 0; i < mice.size(); i++) {
            if (mice[i].vendorId == configVid && mice[i].productId == configPid) {
                selectedIndex = (int)i;
                g_controllerId = configCtrl;
                std::cout << "Found matching device!" << std::endl;
                break;
            }
        }
        
        if (selectedIndex == -1) {
            std::cout << "Device from config not found." << std::endl;
        }
    }
    
    // Если не нашли в конфиге, выбор вручную
    if (selectedIndex == -1) {
        std::cout << "\nAvailable mice:" << std::endl;
        for (size_t i = 0; i < mice.size(); i++) {
            std::wcout << L"[" << i << L"] " << mice[i].name;
            if (mice[i].vendorId != 0) {
                std::wcout << L" (VID=" << std::hex << std::uppercase 
                          << std::setw(4) << std::setfill(L'0') << mice[i].vendorId 
                          << L" PID=" << std::setw(4) << mice[i].productId << L")";
            }
            std::wcout << std::dec << std::endl;
        }
        
        std::cout << "\nEnter mouse number: ";
        std::cin >> selectedIndex;
        
        if (selectedIndex < 0 || selectedIndex >= (int)mice.size()) {
            std::cerr << "Invalid selection!" << std::endl;
            return 1;
        }
        
        // Выбор контроллера
        std::cout << "Select controller type:\n";
        std::cout << "  0 - Left controller\n";
        std::cout << "  1 - Right controller\n";
        std::cout << "Enter choice: ";
        std::cin >> g_controllerId;
        
        if (g_controllerId < 0 || g_controllerId > 1) {
            g_controllerId = 0;
        }
        
        // Сохранить выбор
        if (mice[selectedIndex].vendorId != 0) {
            SaveConfigFile(mice[selectedIndex].vendorId, 
                          mice[selectedIndex].productId, 
                          g_controllerId);
        }
    }
    
    MouseDevice& selectedMouse = mice[selectedIndex];
    g_targetMouseHandle = selectedMouse.handle;
    
    std::wcout << L"\nSelected: " << selectedMouse.name << std::endl;
    std::cout << "Controller: " << (g_controllerId == 0 ? "LEFT" : "RIGHT") << std::endl;
    
    // Создать окно для обработки сообщений
    WNDCLASSEX wc = {0};
    wc.cbSize = sizeof(WNDCLASSEX);
    wc.lpfnWndProc = WndProc;
    wc.hInstance = GetModuleHandle(nullptr);
    wc.lpszClassName = L"GyroMouseClass";
    
    if (!RegisterClassEx(&wc)) {
        std::cerr << "Failed to register window class!" << std::endl;
        return 1;
    }
    
    g_hwnd = CreateWindowEx(0, L"GyroMouseClass", L"VR Gyro Mouse", 0, 
                           0, 0, 0, 0, HWND_MESSAGE, nullptr, wc.hInstance, nullptr);
    
    if (!g_hwnd) {
        std::cerr << "Failed to create window!" << std::endl;
        return 1;
    }
    
    // Зарегистрировать Raw Input
    RAWINPUTDEVICE rid;
    rid.usUsagePage = 0x01;
    rid.usUsage = 0x02;
    rid.dwFlags = RIDEV_INPUTSINK | RIDEV_NOLEGACY;  // NOLEGACY блокирует системные сообщения мыши
    rid.hwndTarget = g_hwnd;
    
    if (!RegisterRawInputDevices(&rid, 1, sizeof(RAWINPUTDEVICE))) {
        std::cerr << "Failed to register raw input device!" << std::endl;
        return 1;
    }
    
    // Применить блокировку курсора
    BlockCursor(g_blockCursor);
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  HOTKEYS:" << std::endl;
    std::cout << "  F1  - Toggle cursor block" << std::endl;
    std::cout << "  F2  - Reset orientation" << std::endl;
    std::cout << "  ESC - Exit" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "\nCapture active! Move mouse to control VR controller..." << std::endl;
    
    // Основной цикл
    MSG msg;
    while (GetMessage(&msg, nullptr, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    
    // Очистка
    BlockCursor(false);  // Разблокировать курсор перед выходом
    closesocket(g_socket);
    WSACleanup();
    
    return 0;
}