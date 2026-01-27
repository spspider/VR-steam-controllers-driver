#include <windows.h>
#include <stdio.h>
#include <setupapi.h>
#include <hidsdi.h>

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "hid.lib")

typedef struct _MOUSE_INPUT_REPORT {
    UCHAR ButtonFlags;
    CHAR DeltaX;
    CHAR DeltaY;
} MOUSE_INPUT_REPORT, *PMOUSE_INPUT_REPORT;

int main(int argc, char* argv[])
{
    HDEVINFO deviceInfo;
    SP_DEVICE_INTERFACE_DATA deviceInterfaceData;
    PSP_DEVICE_INTERFACE_DETAIL_DATA deviceInterfaceDetailData;
    HANDLE deviceHandle;
    DWORD requiredSize;
    GUID hidGuid;
    MOUSE_INPUT_REPORT report;
    DWORD bytesWritten;

    if (argc < 4) {
        printf("Usage: test_mouse.exe <x> <y> <buttons>\n");
        printf("  x: -127 to 127 (delta X)\n");
        printf("  y: -127 to 127 (delta Y)\n");
        printf("  buttons: 0-7 (bit 0=left, bit 1=right, bit 2=middle)\n");
        return 1;
    }

    report.DeltaX = (CHAR)atoi(argv[1]);
    report.DeltaY = (CHAR)atoi(argv[2]);
    report.ButtonFlags = (UCHAR)atoi(argv[3]);

    HidD_GetHidGuid(&hidGuid);

    deviceInfo = SetupDiGetClassDevs(&hidGuid, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (deviceInfo == INVALID_HANDLE_VALUE) {
        printf("ERROR: SetupDiGetClassDevs failed\n");
        return 1;
    }

    deviceInterfaceData.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA);

    for (DWORD i = 0; SetupDiEnumDeviceInterfaces(deviceInfo, NULL, &hidGuid, i, &deviceInterfaceData); i++) {
        SetupDiGetDeviceInterfaceDetail(deviceInfo, &deviceInterfaceData, NULL, 0, &requiredSize, NULL);

        deviceInterfaceDetailData = (PSP_DEVICE_INTERFACE_DETAIL_DATA)malloc(requiredSize);
        deviceInterfaceDetailData->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA);

        if (!SetupDiGetDeviceInterfaceDetail(deviceInfo, &deviceInterfaceData, deviceInterfaceDetailData, requiredSize, &requiredSize, NULL)) {
            free(deviceInterfaceDetailData);
            continue;
        }

        deviceHandle = CreateFileA(deviceInterfaceDetailData->DevicePath, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);

        if (deviceHandle != INVALID_HANDLE_VALUE) {
            WCHAR productName[256];
            if (HidD_GetProductString(deviceHandle, productName, sizeof(productName))) {
                printf("Found device: %S\n", productName);

                if (wcsstr(productName, L"GyroMouse") != NULL) {
                    printf("Sending report: X=%d Y=%d Buttons=0x%02X\n", report.DeltaX, report.DeltaY, report.ButtonFlags);

                    if (WriteFile(deviceHandle, &report, sizeof(report), &bytesWritten, NULL)) {
                        printf("SUCCESS: Report sent\n");
                    }
                    else {
                        printf("ERROR: WriteFile failed\n");
                    }

                    CloseHandle(deviceHandle);
                    free(deviceInterfaceDetailData);
                    SetupDiDestroyDeviceInfoList(deviceInfo);
                    return 0;
                }
            }

            CloseHandle(deviceHandle);
        }

        free(deviceInterfaceDetailData);
    }

    printf("ERROR: GyroMouse device not found\n");
    SetupDiDestroyDeviceInfoList(deviceInfo);
    return 1;
}
