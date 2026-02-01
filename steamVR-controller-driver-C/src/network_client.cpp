// src/network_client.cpp
#include "driver.h"
#include <winsock2.h>
#include <ws2tcpip.h>
#include <iostream>
#include <chrono>

#pragma comment(lib, "ws2_32.lib")

NetworkClient::NetworkClient(uint16_t port) 
    : m_port(port), m_socket(reinterpret_cast<void*>(INVALID_SOCKET)), m_running(false) {}

NetworkClient::~NetworkClient() { 
    Stop(); 
}

bool NetworkClient::Start() {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        return false;
    }
    
    SOCKET socket = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (socket == INVALID_SOCKET) {
        return false;
    }
    
    m_socket = reinterpret_cast<void*>(socket);
    
    sockaddr_in serverAddr;
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(m_port);
    serverAddr.sin_addr.s_addr = INADDR_ANY;
    
    if (bind(socket, (sockaddr*)&serverAddr, sizeof(serverAddr)) == SOCKET_ERROR) {
        closesocket(socket);
        return false;
    }
    
    // Устанавливаем неблокирующий режим
    u_long mode = 1;
    ioctlsocket(socket, FIONBIO, &mode);
    
    m_running = true;
    return true;
}

void NetworkClient::Stop() {
    m_running = false;
    SOCKET socket = reinterpret_cast<SOCKET>(m_socket);
    if (socket != INVALID_SOCKET) {
        closesocket(socket);
        m_socket = reinterpret_cast<void*>(INVALID_SOCKET);
    }
    WSACleanup();
}

bool NetworkClient::Receive(ControllerData& data) {
    SOCKET socket = reinterpret_cast<SOCKET>(m_socket);
    if (socket == INVALID_SOCKET) return false;
    
    sockaddr_in clientAddr;
    int clientAddrSize = sizeof(clientAddr);
    
    int bytesReceived = recvfrom(socket, 
        (char*)&data, sizeof(ControllerData), 
        0, (sockaddr*)&clientAddr, &clientAddrSize);
    
    if (bytesReceived == SOCKET_ERROR) {
        return false;
    }
    
    if (bytesReceived == sizeof(ControllerData)) {
        // Проверяем контрольную сумму
        if (VerifyChecksum(data)) {
            return true;
        }
    }
    
    return false;
}

bool NetworkClient::VerifyChecksum(const ControllerData& data) {
    uint8_t sum = 0;
    const uint8_t* bytes = reinterpret_cast<const uint8_t*>(&data);
    
    // Суммируем все байты кроме checksum
    for (size_t i = 0; i < sizeof(ControllerData) - 1; i++) {
        sum += bytes[i];
    }
    
    return sum == data.checksum;
}