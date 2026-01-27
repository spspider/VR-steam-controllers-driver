#include "vhid_mouse.h"

#ifdef ALLOC_PRAGMA
#pragma alloc_text (INIT, DriverEntry)
#pragma alloc_text (PAGE, VhidMouseEvtDeviceAdd)
#pragma alloc_text (PAGE, VhidMouseCreateDevice)
#endif

// HID Report Descriptor для мыши с 3 кнопками и относительным движением
static const UCHAR g_VhidMouseReportDescriptor[] = {
    0x05, 0x01,        // USAGE_PAGE (Generic Desktop)
    0x09, 0x02,        // USAGE (Mouse)
    0xA1, 0x01,        // COLLECTION (Application)
    0x09, 0x01,        //   USAGE (Pointer)
    0xA1, 0x00,        //   COLLECTION (Physical)
    0x05, 0x09,        //     USAGE_PAGE (Button)
    0x19, 0x01,        //     USAGE_MINIMUM (Button 1)
    0x29, 0x03,        //     USAGE_MAXIMUM (Button 3)
    0x15, 0x00,        //     LOGICAL_MINIMUM (0)
    0x25, 0x01,        //     LOGICAL_MAXIMUM (1)
    0x95, 0x03,        //     REPORT_COUNT (3)
    0x75, 0x01,        //     REPORT_SIZE (1)
    0x81, 0x02,        //     INPUT (Data,Var,Abs)
    0x95, 0x01,        //     REPORT_COUNT (1)
    0x75, 0x05,        //     REPORT_SIZE (5)
    0x81, 0x01,        //     INPUT (Cnst,Ary,Abs)
    0x05, 0x01,        //     USAGE_PAGE (Generic Desktop)
    0x09, 0x30,        //     USAGE (X)
    0x09, 0x31,        //     USAGE (Y)
    0x15, 0x81,        //     LOGICAL_MINIMUM (-127)
    0x25, 0x7F,        //     LOGICAL_MAXIMUM (127)
    0x75, 0x08,        //     REPORT_SIZE (8)
    0x95, 0x02,        //     REPORT_COUNT (2)
    0x81, 0x06,        //     INPUT (Data,Var,Rel)
    0xC0,              //   END_COLLECTION
    0xC0               // END_COLLECTION
};

// Forward declarations
VOID
VhidMouseEvtVhfReadyForNextReadReport(
    _In_ VHFHANDLE VhfHandle,
    _In_opt_ PVOID Context
);

VOID
VhidMouseEvtVhfAsyncOperationGetFeature(
    _In_ VHFHANDLE VhfHandle,
    _In_opt_ PVOID Context,
    _In_ PHID_XFER_PACKET HidTransferPacket
);

VOID
VhidMouseEvtVhfAsyncOperationSetFeature(
    _In_ VHFHANDLE VhfHandle,
    _In_opt_ PVOID Context,
    _In_ PHID_XFER_PACKET HidTransferPacket
);

//
// DriverEntry - точка входа драйвера
//
NTSTATUS
DriverEntry(
    _In_ PDRIVER_OBJECT DriverObject,
    _In_ PUNICODE_STRING RegistryPath
)
{
    WDF_DRIVER_CONFIG config;
    NTSTATUS status;

    KdPrint(("VhidMouse: DriverEntry\n"));

    WDF_DRIVER_CONFIG_INIT(&config, VhidMouseEvtDeviceAdd);

    status = WdfDriverCreate(DriverObject,
        RegistryPath,
        WDF_NO_OBJECT_ATTRIBUTES,
        &config,
        WDF_NO_HANDLE);

    if (!NT_SUCCESS(status)) {
        KdPrint(("VhidMouse: WdfDriverCreate failed 0x%x\n", status));
        return status;
    }

    KdPrint(("VhidMouse: Driver loaded successfully\n"));
    return status;
}

//
// VhidMouseEvtDeviceAdd - вызывается при добавлении устройства
//
NTSTATUS
VhidMouseEvtDeviceAdd(
    _In_ WDFDRIVER Driver,
    _Inout_ PWDFDEVICE_INIT DeviceInit
)
{
    UNREFERENCED_PARAMETER(Driver);

    PAGED_CODE();

    KdPrint(("VhidMouse: EvtDeviceAdd\n"));

    return VhidMouseCreateDevice(DeviceInit);
}

//
// VhidMouseCreateDevice - создание виртуального HID устройства
//
NTSTATUS
VhidMouseCreateDevice(
    _Inout_ PWDFDEVICE_INIT DeviceInit
)
{
    NTSTATUS status;
    WDFDEVICE device;
    PVHID_MOUSE_CONTEXT deviceContext;
    WDF_OBJECT_ATTRIBUTES deviceAttributes;
    WDF_IO_QUEUE_CONFIG queueConfig;
    VHF_CONFIG vhfConfig;
    VHFHANDLE vhfHandle;

    PAGED_CODE();

    // Создать атрибуты устройства с контекстом
    WDF_OBJECT_ATTRIBUTES_INIT_CONTEXT_TYPE(&deviceAttributes, VHID_MOUSE_CONTEXT);

    // Создать устройство
    status = WdfDeviceCreate(&DeviceInit, &deviceAttributes, &device);
    if (!NT_SUCCESS(status)) {
        KdPrint(("VhidMouse: WdfDeviceCreate failed 0x%x\n", status));
        return status;
    }

    // Получить контекст устройства
    deviceContext = GetVhidMouseContext(device);
    deviceContext->Device = device;
    deviceContext->MouseActive = FALSE;
    deviceContext->VhfHandle = NULL;

    // Создать очередь для IOCTL
    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&queueConfig, WdfIoQueueDispatchParallel);
    queueConfig.EvtIoDeviceControl = VhidMouseEvtIoDeviceControl;

    status = WdfIoQueueCreate(device,
        &queueConfig,
        WDF_NO_OBJECT_ATTRIBUTES,
        &deviceContext->DefaultQueue);

    if (!NT_SUCCESS(status)) {
        KdPrint(("VhidMouse: WdfIoQueueCreate failed 0x%x\n", status));
        return status;
    }

    // Инициализировать VHF конфигурацию
    RtlZeroMemory(&vhfConfig, sizeof(VHF_CONFIG));
    vhfConfig.Size = sizeof(VHF_CONFIG);
    vhfConfig.DeviceObject = WdfDeviceWdmGetDeviceObject(device);
    vhfConfig.ReportDescriptor = (PUCHAR)g_VhidMouseReportDescriptor;
    vhfConfig.ReportDescriptorLength = sizeof(g_VhidMouseReportDescriptor);
    vhfConfig.EvtVhfReadyForNextReadReport = VhidMouseEvtVhfReadyForNextReadReport;
    vhfConfig.EvtVhfAsyncOperationGetFeature = VhidMouseEvtVhfAsyncOperationGetFeature;
    vhfConfig.EvtVhfAsyncOperationSetFeature = VhidMouseEvtVhfAsyncOperationSetFeature;

    // Создать VHF устройство
    status = VhfCreate(&vhfConfig, &vhfHandle);
    if (!NT_SUCCESS(status)) {
        KdPrint(("VhidMouse: VhfCreate failed 0x%x\n", status));
        return status;
    }

    deviceContext->VhfHandle = vhfHandle;

    // Запустить VHF
    status = VhfStart(vhfHandle);
    if (!NT_SUCCESS(status)) {
        KdPrint(("VhidMouse: VhfStart failed 0x%x\n", status));
        VhfDelete(vhfHandle, FALSE);
        return status;
    }

    deviceContext->MouseActive = TRUE;

    KdPrint(("VhidMouse: Device created successfully\n"));
    return STATUS_SUCCESS;
}

//
// VhidMouseEvtVhfReadyForNextReadReport - VHF готов принять следующий отчет
//
VOID
VhidMouseEvtVhfReadyForNextReadReport(
    _In_ VHFHANDLE VhfHandle,
    _In_opt_ PVOID Context
)
{
    UNREFERENCED_PARAMETER(VhfHandle);
    UNREFERENCED_PARAMETER(Context);
}

//
// VhidMouseEvtVhfAsyncOperationGetFeature - получение feature report
//
VOID
VhidMouseEvtVhfAsyncOperationGetFeature(
    _In_ VHFHANDLE VhfHandle,
    _In_opt_ PVOID Context,
    _In_ PHID_XFER_PACKET HidTransferPacket
)
{
    UNREFERENCED_PARAMETER(VhfHandle);
    UNREFERENCED_PARAMETER(Context);
    UNREFERENCED_PARAMETER(HidTransferPacket);

    VhfAsyncOperationComplete(VhfHandle, STATUS_NOT_SUPPORTED);
}

//
// VhidMouseEvtVhfAsyncOperationSetFeature - установка feature report
//
VOID
VhidMouseEvtVhfAsyncOperationSetFeature(
    _In_ VHFHANDLE VhfHandle,
    _In_opt_ PVOID Context,
    _In_ PHID_XFER_PACKET HidTransferPacket
)
{
    UNREFERENCED_PARAMETER(VhfHandle);
    UNREFERENCED_PARAMETER(Context);
    UNREFERENCED_PARAMETER(HidTransferPacket);

    VhfAsyncOperationComplete(VhfHandle, STATUS_NOT_SUPPORTED);
}

//
// VhidMouseEvtIoDeviceControl - обработка IOCTL из user-mode
//
VOID
VhidMouseEvtIoDeviceControl(
    _In_ WDFQUEUE Queue,
    _In_ WDFREQUEST Request,
    _In_ size_t OutputBufferLength,
    _In_ size_t InputBufferLength,
    _In_ ULONG IoControlCode
)
{
    NTSTATUS status = STATUS_SUCCESS;
    PVHID_MOUSE_CONTEXT deviceContext;
    PVHID_MOUSE_DATA mouseData = NULL;
    size_t length = 0;

    UNREFERENCED_PARAMETER(OutputBufferLength);

    deviceContext = GetVhidMouseContext(WdfIoQueueGetDevice(Queue));

    switch (IoControlCode) {
    case IOCTL_VHID_SEND_MOUSE_DATA: {
        KdPrint(("VhidMouse: IOCTL_VHID_SEND_MOUSE_DATA\n"));

        // Проверить размер входного буфера
        if (InputBufferLength < sizeof(VHID_MOUSE_DATA)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        // Получить данные мыши
        status = WdfRequestRetrieveInputBuffer(Request,
            sizeof(VHID_MOUSE_DATA),
            (PVOID*)&mouseData,
            &length);

        if (!NT_SUCCESS(status) || mouseData == NULL) {
            KdPrint(("VhidMouse: Failed to retrieve input buffer 0x%x\n", status));
            break;
        }

        // Создать HID Input Report
        VHID_MOUSE_INPUT_REPORT inputReport;
        inputReport.ButtonFlags = mouseData->ButtonFlags;
        inputReport.DeltaX = mouseData->DeltaX;
        inputReport.DeltaY = mouseData->DeltaY;

        // Отправить отчет через VHF
        if (deviceContext->MouseActive && deviceContext->VhfHandle != NULL) {
            HID_XFER_PACKET packet;
            packet.reportId = 0;
            packet.reportBuffer = (PUCHAR)&inputReport;
            packet.reportBufferLen = sizeof(VHID_MOUSE_INPUT_REPORT);

            status = VhfReadReportSubmit(deviceContext->VhfHandle, &packet);

            if (NT_SUCCESS(status)) {
                KdPrint(("VhidMouse: Sent mouse data X=%d Y=%d Buttons=0x%x\n",
                    inputReport.DeltaX,
                    inputReport.DeltaY,
                    inputReport.ButtonFlags));
            }
            else {
                KdPrint(("VhidMouse: VhfReadReportSubmit failed 0x%x\n", status));
            }
        }
        else {
            status = STATUS_DEVICE_NOT_READY;
            KdPrint(("VhidMouse: Device not active\n"));
        }

        break;
    }

    default:
        status = STATUS_NOT_SUPPORTED;
        KdPrint(("VhidMouse: Unsupported IOCTL 0x%x\n", IoControlCode));
        break;
    }

    WdfRequestComplete(Request, status);
}
