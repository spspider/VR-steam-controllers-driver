// src/mouse_input_client.cpp
#include "driver.h"
#include <winsock2.h>
#include <ws2tcpip.h>
#include <iostream>
#include <chrono>

#pragma comment(lib, "ws2_32.lib")

MouseInputClient::MouseInputClient(uint16_t port)
    : m_port(port), m_socket(reinterpret_cast<void*>(INVALID_SOCKET)), m_running(false) {}

MouseInputClient::~MouseInputClient() {
    Stop();
}

bool MouseInputClient::Start() {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        return false;
    }

    SOCKET socket = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (socket == INVALID_SOCKET) {
        WSACleanup();
        return false;
    }

    m_socket = reinterpret_cast<void*>(socket);

    sockaddr_in serverAddr;
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(m_port);
    serverAddr.sin_addr.s_addr = INADDR_ANY;

    if (bind(socket, (sockaddr*)&serverAddr, sizeof(serverAddr)) == SOCKET_ERROR) {
        closesocket(socket);
        WSACleanup();
        return false;
    }

    // Установим неблокирующий режим
    u_long mode = 1;
    ioctlsocket(socket, FIONBIO, &mode);

    m_running = true;
    return true;
}

void MouseInputClient::Stop() {
    m_running = false;
    SOCKET socket = reinterpret_cast<SOCKET>(m_socket);
    if (socket != INVALID_SOCKET) {
        closesocket(socket);
        m_socket = reinterpret_cast<void*>(INVALID_SOCKET);
    }
    WSACleanup();
}

bool MouseInputClient::Receive(MouseControllerData& data) {
    SOCKET socket = reinterpret_cast<SOCKET>(m_socket);
    if (socket == INVALID_SOCKET) return false;

    sockaddr_in clientAddr;
    int clientAddrSize = sizeof(clientAddr);

    int bytesReceived = recvfrom(socket,
        (char*)&data, sizeof(MouseControllerData),
        0, (sockaddr*)&clientAddr, &clientAddrSize);

    if (bytesReceived == SOCKET_ERROR) {
        int error = WSAGetLastError();
        if (error != WSAEWOULDBLOCK) {
            return false;
        }
        return false;
    }

    if (bytesReceived == sizeof(MouseControllerData)) {
        // Проверяем контрольную сумму
        if (VerifyChecksum(data)) {
            return true;
        }
    }

    return false;
}

bool MouseInputClient::VerifyChecksum(const MouseControllerData& data) {
    uint8_t sum = 0;
    const uint8_t* bytes = reinterpret_cast<const uint8_t*>(&data);

    // Суммируем все байты кроме checksum
    for (size_t i = 0; i < sizeof(MouseControllerData) - 1; i++) {
        sum += bytes[i];
    }

    return sum == data.checksum;
}

// ВАЖНО: Этот метод захватывает конкретное HID устройство
// VID_2389 & PID_00A8 - гироскопическая мышь
// После захвата устройство перестанет работать как обычная мышь в Windows
// и будет использовано только как контроллер SteamVR
bool MouseInputClient::CaptureHIDDevice() {
    m_hidDevice = std::make_unique<HIDDevice>(0x2389, 0x00A8);
    return m_hidDevice->Open();
}