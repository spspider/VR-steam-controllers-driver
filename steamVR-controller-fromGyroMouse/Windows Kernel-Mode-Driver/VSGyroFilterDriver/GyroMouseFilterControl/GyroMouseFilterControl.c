#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

// IOCTL команды (должны совпадать с драйвером)
#define IOCTL_GYRO_SET_BLOCK     CTL_CODE(FILE_DEVICE_MOUSE, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_GYRO_SET_FILTER    CTL_CODE(FILE_DEVICE_MOUSE, 0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_GYRO_SET_THRESHOLD CTL_CODE(FILE_DEVICE_MOUSE, 0x802, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_GYRO_GET_INFO      CTL_CODE(FILE_DEVICE_MOUSE, 0x803, METHOD_BUFFERED, FILE_ANY_ACCESS)

void PrintUsage(const char* programName) {
    printf("Usage: %s <command> [parameters]\n\n", programName);
    printf("Commands:\n");
    printf("  enable-filter              - Enable mouse position filtering\n");
    printf("  disable-filter             - Disable mouse position filtering\n");
    printf("  set-threshold <value>      - Set filter threshold (pixels)\n");
    printf("  block-input                - Block all mouse input\n");
    printf("  unblock-input              - Unblock mouse input\n");
    printf("  get-info                   - Get device information\n");
    printf("\nExamples:\n");
    printf("  %s enable-filter\n", programName);
    printf("  %s set-threshold 10\n", programName);
    printf("  %s block-input\n", programName);
}

HANDLE OpenDevice() {
    // Try different device names
    const char* deviceNames[] = {
        "\\\\.\\GyroMouseFilter",
        "\\\\.\\GyroMouseFilter0",
        "\\\\.\\Global\\GyroMouseFilter"
    };

    for (int i = 0; i < sizeof(deviceNames) / sizeof(deviceNames[0]); i++) {
        HANDLE hDevice = CreateFileA(
            deviceNames[i],
            GENERIC_READ | GENERIC_WRITE,
            0,
            NULL,
            OPEN_EXISTING,
            0,
            NULL
        );

        if (hDevice != INVALID_HANDLE_VALUE) {
            printf("Successfully opened device: %s\n", deviceNames[i]);
            return hDevice;
        }
    }

    printf("Failed to open device. Make sure the driver is installed.\n");
    return INVALID_HANDLE_VALUE;
}

int EnableFilter(HANDLE hDevice) {
    BOOLEAN filterEnabled = TRUE;
    DWORD bytesReturned = 0;

    if (!DeviceIoControl(
        hDevice,
        IOCTL_GYRO_SET_FILTER,
        &filterEnabled,
        sizeof(BOOLEAN),
        NULL,
        0,
        &bytesReturned,
        NULL
    )) {
        printf("Error: Failed to enable filter (0x%x)\n", GetLastError());
        return 1;
    }

    printf("Filter enabled successfully\n");
    return 0;
}

int DisableFilter(HANDLE hDevice) {
    BOOLEAN filterEnabled = FALSE;
    DWORD bytesReturned = 0;

    if (!DeviceIoControl(
        hDevice,
        IOCTL_GYRO_SET_FILTER,
        &filterEnabled,
        sizeof(BOOLEAN),
        NULL,
        0,
        &bytesReturned,
        NULL
    )) {
        printf("Error: Failed to disable filter (0x%x)\n", GetLastError());
        return 1;
    }

    printf("Filter disabled successfully\n");
    return 0;
}

int SetThreshold(HANDLE hDevice, ULONG threshold) {
    DWORD bytesReturned = 0;

    if (!DeviceIoControl(
        hDevice,
        IOCTL_GYRO_SET_THRESHOLD,
        &threshold,
        sizeof(ULONG),
        NULL,
        0,
        &bytesReturned,
        NULL
    )) {
        printf("Error: Failed to set threshold (0x%x)\n", GetLastError());
        return 1;
    }

    printf("Filter threshold set to %lu pixels\n", threshold);
    return 0;
}

int BlockInput(HANDLE hDevice) {
    BOOLEAN blockFlag = TRUE;
    DWORD bytesReturned = 0;

    if (!DeviceIoControl(
        hDevice,
        IOCTL_GYRO_SET_BLOCK,
        &blockFlag,
        sizeof(BOOLEAN),
        NULL,
        0,
        &bytesReturned,
        NULL
    )) {
        printf("Error: Failed to block input (0x%x)\n", GetLastError());
        return 1;
    }

    printf("Mouse input blocked\n");
    return 0;
}

int UnblockInput(HANDLE hDevice) {
    BOOLEAN blockFlag = FALSE;
    DWORD bytesReturned = 0;

    if (!DeviceIoControl(
        hDevice,
        IOCTL_GYRO_SET_BLOCK,
        &blockFlag,
        sizeof(BOOLEAN),
        NULL,
        0,
        &bytesReturned,
        NULL
    )) {
        printf("Error: Failed to unblock input (0x%x)\n", GetLastError());
        return 1;
    }

    printf("Mouse input unblocked\n");
    return 0;
}

int GetInfo(HANDLE hDevice) {
    USHORT info[2] = { 0, 0 };
    DWORD bytesReturned = 0;

    if (!DeviceIoControl(
        hDevice,
        IOCTL_GYRO_GET_INFO,
        NULL,
        0,
        info,
        sizeof(info),
        &bytesReturned,
        NULL
    )) {
        printf("Error: Failed to get device info (0x%x)\n", GetLastError());
        return 1;
    }

    printf("Device Information:\n");
    printf("  Vendor ID:  0x%04X\n", info[0]);
    printf("  Product ID: 0x%04X\n", info[1]);
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        PrintUsage(argv[0]);
        return 1;
    }

    HANDLE hDevice = OpenDevice();
    if (hDevice == INVALID_HANDLE_VALUE) {
        return 1;
    }

    int result = 0;
    const char* command = argv[1];

    if (strcmp(command, "enable-filter") == 0) {
        result = EnableFilter(hDevice);
    }
    else if (strcmp(command, "disable-filter") == 0) {
        result = DisableFilter(hDevice);
    }
    else if (strcmp(command, "set-threshold") == 0) {
        if (argc < 3) {
            printf("Error: set-threshold requires a value\n");
            result = 1;
        }
        else {
            ULONG threshold = atol(argv[2]);
            result = SetThreshold(hDevice, threshold);
        }
    }
    else if (strcmp(command, "block-input") == 0) {
        result = BlockInput(hDevice);
    }
    else if (strcmp(command, "unblock-input") == 0) {
        result = UnblockInput(hDevice);
    }
    else if (strcmp(command, "get-info") == 0) {
        result = GetInfo(hDevice);
    }
    else {
        printf("Unknown command: %s\n", command);
        PrintUsage(argv[0]);
        result = 1;
    }

    CloseHandle(hDevice);
    return result;
}
