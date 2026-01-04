#pragma once

#define NOMINMAX
#define WIN32_LEAN_AND_MEAN

#include <string>
#include <memory>
#include <atomic>
#include <cstdint>

// ВАЖНО: Здесь указывается конкретное HID устройство гироскопической мыши
// VID (Vendor ID): 0x2389
// PID (Product ID): 0x00A8
// Это устройство будет захвачено драйвером и использовано как левый контроллер
// Устройство перестанет работать как обычная мышь в Windows

class HIDDevice {
public:
    // Конструктор с явным указанием VID/PID
    // VID_2389 & PID_00A8 - гироскопическая мышь (левый контроллер)
    HIDDevice(uint16_t vendor_id = 0x2389, uint16_t product_id = 0x00A8);
    ~HIDDevice();
    
    // Открыть устройство по VID/PID
    bool Open();
    
    // Закрыть устройство
    void Close();
    
    // Прочитать данные с устройства
    bool Read(uint8_t* buffer, size_t buffer_size, size_t& bytes_read);
    
    // Проверить, открыто ли устройство
    bool IsOpen() const { return m_deviceHandle != nullptr; }
    
private:
    uint16_t m_vendorId;      // VID: 0x2389
    uint16_t m_productId;     // PID: 0x00A8
    void* m_deviceHandle;     // Указатель на HID устройство
    std::atomic<bool> m_isOpen;
};
