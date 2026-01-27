#ifndef GYRO_MOUSE_FILTER_H
#define GYRO_MOUSE_FILTER_H

#include <ntddk.h>
#include <wdf.h>
#include <hidport.h>
#include <ntddmou.h>
#include <vhf.h>
#include <initguid.h>

#ifndef IOCTL_INTERNAL_MOUSE_CONNECT
#define IOCTL_INTERNAL_MOUSE_CONNECT \
    CTL_CODE(FILE_DEVICE_MOUSE, 0x0080, METHOD_NEITHER, FILE_ANY_ACCESS)
#endif

//
// Device context structure для фильтра
//
typedef struct _DEVICE_CONTEXT {
    WDFQUEUE DefaultQueue;
    WDFIOTARGET IoTarget;
    BOOLEAN BlockInput;
    BOOLEAN FilterEnabled;
    USHORT VendorId;
    USHORT ProductId;
    LONG LastX;
    LONG LastY;
    ULONG FilterThreshold;
    PVOID VhfHandle;
} DEVICE_CONTEXT, *PDEVICE_CONTEXT;

//
// Control device context structure
//
typedef struct _CONTROL_DEVICE_CONTEXT {
    PDEVICE_CONTEXT FilterContext;
} CONTROL_DEVICE_CONTEXT, *PCONTROL_DEVICE_CONTEXT;

WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(DEVICE_CONTEXT, GetDeviceContext)
WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(CONTROL_DEVICE_CONTEXT, GetControlDeviceContext)

//
// IOCTL для управления из user-mode
//
#define IOCTL_GYRO_SET_BLOCK     CTL_CODE(FILE_DEVICE_MOUSE, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_GYRO_SET_FILTER    CTL_CODE(FILE_DEVICE_MOUSE, 0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_GYRO_SET_THRESHOLD CTL_CODE(FILE_DEVICE_MOUSE, 0x802, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_GYRO_GET_INFO      CTL_CODE(FILE_DEVICE_MOUSE, 0x803, METHOD_BUFFERED, FILE_ANY_ACCESS)

//
// HID Report Descriptor
//
const UCHAR HID_REPORT_DESCRIPTOR[] = {
    0x05, 0x01, 0x09, 0x02, 0xa1, 0x01, 0x09, 0x01,
    0xa1, 0x00, 0x05, 0x09, 0x19, 0x01, 0x29, 0x03,
    0x15, 0x00, 0x25, 0x01, 0x75, 0x01, 0x95, 0x03,
    0x81, 0x02, 0x75, 0x05, 0x95, 0x01, 0x81, 0x03,
    0x05, 0x01, 0x09, 0x30, 0x09, 0x31, 0x15, 0x81,
    0x25, 0x7f, 0x75, 0x08, 0x95, 0x02, 0x81, 0x06,
    0xc0, 0xc0
};

//
// Function declarations
//
DRIVER_INITIALIZE DriverEntry;
EVT_WDF_DRIVER_DEVICE_ADD GyroMouseEvtDeviceAdd;
EVT_WDF_IO_QUEUE_IO_INTERNAL_DEVICE_CONTROL GyroMouseEvtInternalDeviceControl;
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL GyroMouseEvtDeviceControl;
EVT_WDF_REQUEST_COMPLETION_ROUTINE GyroMouseRequestCompletionRoutine;

NTSTATUS
GyroMouseCreateDevice(
    _Inout_ PWDFDEVICE_INIT DeviceInit
);

NTSTATUS
GyroMouseCreateControlDevice(
    _In_ WDFDEVICE FilterDevice,
    _In_ PDEVICE_CONTEXT FilterContext
);

VOID
GyroMouseFilterMouseData(
    _In_ PDEVICE_CONTEXT DeviceContext,
    _Inout_ PMOUSE_INPUT_DATA MouseData
);

VOID
GyroMouseEvtVhfAsyncOperationComplete(
    _In_ PVHF_CONFIG VhfConfig,
    _In_ PVOID VhfContext,
    _In_ PVOID VhfOperationHandle,
    _In_ PHID_XFER_PACKET HidTransferPacket
);

#endif // GYRO_MOUSE_FILTER_H
