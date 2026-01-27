#include <windows.h>
#include <stdio.h>

#define IOCTL_GYRO_SET_BLOCK CTL_CODE(FILE_DEVICE_MOUSE, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)

int main(int argc, char* argv[])
{
    HANDLE hDevice;
    BOOLEAN blockFlag;
    DWORD bytesReturned;
    BOOLEAN success;

    if (argc < 2) {
        printf("Usage: test_driver.exe [on|off]\n");
        printf("  on  - Block mouse input\n");
        printf("  off - Allow mouse input\n");
        return 1;
    }

    // Определить флаг блокировки
    if (strcmp(argv[1], "on") == 0) {
        blockFlag = TRUE;
        printf("Setting: BLOCK mouse input\n");
    }
    else if (strcmp(argv[1], "off") == 0) {
        blockFlag = FALSE;
        printf("Setting: ALLOW mouse input\n");
    }
    else {
        printf("Invalid argument. Use 'on' or 'off'\n");
        return 1;
    }

    // Открыть устройство
    hDevice = CreateFileA("\\\\.\\GyroMouseFilter",
        GENERIC_READ | GENERIC_WRITE,
        0,
        NULL,
        OPEN_EXISTING,
        0,
        NULL);

    if (hDevice == INVALID_HANDLE_VALUE) {
        printf("ERROR: Cannot open device. Make sure driver is installed.\n");
        printf("Error code: %lu\n", GetLastError());
        return 1;
    }

    printf("Device opened successfully\n");

    // Отправить команду
    success = DeviceIoControl(hDevice,
        IOCTL_GYRO_SET_BLOCK,
        &blockFlag,
        sizeof(BOOLEAN),
        NULL,
        0,
        &bytesReturned,
        NULL);

    if (success) {
        printf("SUCCESS: Command sent to driver\n");
    }
    else {
        printf("ERROR: Failed to send command\n");
        printf("Error code: %lu\n", GetLastError());
    }

    CloseHandle(hDevice);
    return success ? 0 : 1;
}
