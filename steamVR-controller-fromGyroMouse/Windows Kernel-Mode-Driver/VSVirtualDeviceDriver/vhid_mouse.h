#ifndef VHID_MOUSE_H
#define VHID_MOUSE_H

#include <ntddk.h>
#include <wdf.h>
#include <hidport.h>
#include <vhf.h>

#define VHID_MOUSE_POOL_TAG 'VHID'

// IOCTL для отправки данных мыши из user-mode
#define IOCTL_VHID_SEND_MOUSE_DATA \
    CTL_CODE(FILE_DEVICE_UNKNOWN, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)

// Структура для передачи данных мыши
typedef struct _VHID_MOUSE_DATA {
    CHAR DeltaX;
    CHAR DeltaY;
    UCHAR ButtonFlags;
} VHID_MOUSE_DATA, * PVHID_MOUSE_DATA;

// Контекст устройства
typedef struct _VHID_MOUSE_CONTEXT {
    WDFDEVICE Device;
    WDFQUEUE DefaultQueue;
    VHFHANDLE VhfHandle;
    BOOLEAN MouseActive;
} VHID_MOUSE_CONTEXT, * PVHID_MOUSE_CONTEXT;

WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(VHID_MOUSE_CONTEXT, GetVhidMouseContext)

// Структура HID Input Report
typedef struct _VHID_MOUSE_INPUT_REPORT {
    UCHAR ButtonFlags;
    CHAR DeltaX;
    CHAR DeltaY;
} VHID_MOUSE_INPUT_REPORT, * PVHID_MOUSE_INPUT_REPORT;

// Function declarations
DRIVER_INITIALIZE DriverEntry;
EVT_WDF_DRIVER_DEVICE_ADD VhidMouseEvtDeviceAdd;
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL VhidMouseEvtIoDeviceControl;

NTSTATUS
VhidMouseCreateDevice(
    _Inout_ PWDFDEVICE_INIT DeviceInit
);

#endif // VHID_MOUSE_H
