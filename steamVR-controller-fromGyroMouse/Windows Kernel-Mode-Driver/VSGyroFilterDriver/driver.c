#include "driver.h"

#ifdef ALLOC_PRAGMA
#pragma alloc_text (INIT, DriverEntry)
#pragma alloc_text (PAGE, GyroMouseEvtDeviceAdd)
#pragma alloc_text (PAGE, GyroMouseCreateDevice)
#pragma alloc_text (PAGE, GyroMouseEvtVhfAsyncOperationComplete)
#endif

//
// DriverEntry - точка входа драйвера
//
NTSTATUS
DriverEntry(
    _In_ PDRIVER_OBJECT  DriverObject,
    _In_ PUNICODE_STRING RegistryPath
)
{
    WDF_DRIVER_CONFIG config;
    NTSTATUS status;

    KdPrint(("GyroMouseFilter: DriverEntry\n"));

    WDF_DRIVER_CONFIG_INIT(&config, GyroMouseEvtDeviceAdd);

    status = WdfDriverCreate(DriverObject,
        RegistryPath,
        WDF_NO_OBJECT_ATTRIBUTES,
        &config,
        WDF_NO_HANDLE);

    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: WdfDriverCreate failed 0x%x\n", status));
        return status;
    }

    KdPrint(("GyroMouseFilter: Driver loaded successfully\n"));
    return status;
}

//
// GyroMouseEvtDeviceAdd - создание нового устройства
//
NTSTATUS
GyroMouseEvtDeviceAdd(
    _In_    WDFDRIVER       Driver,
    _Inout_ PWDFDEVICE_INIT DeviceInit
)
{
    NTSTATUS status;

    UNREFERENCED_PARAMETER(Driver);

    PAGED_CODE();

    KdPrint(("GyroMouseFilter: EvtDeviceAdd\n"));

    // Установить фильтр
    WdfFdoInitSetFilter(DeviceInit);

    status = GyroMouseCreateDevice(DeviceInit);

    return status;
}

//
// GyroMouseCreateDevice - создание устройства и очереди
//
NTSTATUS
GyroMouseCreateDevice(
    _Inout_ PWDFDEVICE_INIT DeviceInit
)
{
    WDF_OBJECT_ATTRIBUTES deviceAttributes;
    PDEVICE_CONTEXT deviceContext;
    WDFDEVICE device;
    NTSTATUS status;
    WDF_IO_QUEUE_CONFIG queueConfig;

    PAGED_CODE();

    WDF_OBJECT_ATTRIBUTES_INIT_CONTEXT_TYPE(&deviceAttributes, DEVICE_CONTEXT);

    status = WdfDeviceCreate(&DeviceInit, &deviceAttributes, &device);

    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: WdfDeviceCreate failed 0x%x\n", status));
        return status;
    }

    deviceContext = GetDeviceContext(device);
    deviceContext->BlockInput = FALSE;
    deviceContext->FilterEnabled = TRUE;
    deviceContext->VendorId = 0;
    deviceContext->ProductId = 0;
    deviceContext->LastX = 0;
    deviceContext->LastY = 0;
    deviceContext->FilterThreshold = 5;

    // Создать I/O Target для пересылки запросов вниз по стеку
    WDF_OBJECT_ATTRIBUTES attributes;
    WDF_OBJECT_ATTRIBUTES_INIT(&attributes);
    attributes.ParentObject = device;

    status = WdfIoTargetCreate(device,
        &attributes,
        &deviceContext->IoTarget);

    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: WdfIoTargetCreate failed 0x%x\n", status));
        return status;
    }

    // Открыть target к следующему драйверу в стеке
    WDF_IO_TARGET_OPEN_PARAMS openParams;
    WDF_IO_TARGET_OPEN_PARAMS_INIT_EXISTING_DEVICE(&openParams,
        WdfDeviceWdmGetAttachedDevice(device));

    status = WdfIoTargetOpen(deviceContext->IoTarget, &openParams);

    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: WdfIoTargetOpen failed 0x%x\n", status));
        return status;
    }

    // Создать очередь для internal device control
    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&queueConfig, WdfIoQueueDispatchParallel);
    queueConfig.EvtIoInternalDeviceControl = GyroMouseEvtInternalDeviceControl;

    status = WdfIoQueueCreate(device,
        &queueConfig,
        WDF_NO_OBJECT_ATTRIBUTES,
        &deviceContext->DefaultQueue);

    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: WdfIoQueueCreate failed 0x%x\n", status));
        return status;
    }

    // Создать контрольное устройство для user-mode доступа
    status = GyroMouseCreateControlDevice(device, deviceContext);
    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: GyroMouseCreateControlDevice failed 0x%x\n", status));
        // Не критично, продолжаем работу
    }

    KdPrint(("GyroMouseFilter: Device fully initialized\n"));
    return status;
}

//
// Создание контрольного устройства
//
NTSTATUS
GyroMouseCreateControlDevice(
    _In_ WDFDEVICE FilterDevice,
    _In_ PDEVICE_CONTEXT FilterContext
)
{
    PWDFDEVICE_INIT deviceInit;
    WDFDEVICE controlDevice;
    WDF_OBJECT_ATTRIBUTES attributes;
    PCONTROL_DEVICE_CONTEXT controlContext;
    NTSTATUS status;
    UNICODE_STRING deviceName;
    UNICODE_STRING symbolicLinkName;

    PAGED_CODE();

    // Создать WDFDEVICE_INIT для контрольного устройства
    deviceInit = WdfControlDeviceInitAllocate(
        WdfDeviceGetDriver(FilterDevice),
        NULL);

    if (deviceInit == NULL) {
        KdPrint(("GyroMouseFilter: WdfControlDeviceInitAllocate failed\n"));
        return STATUS_INSUFFICIENT_RESOURCES;
    }

    // Установить имя устройства
    RtlInitUnicodeString(&deviceName, L"\\Device\\GyroMouseFilter");
    status = WdfDeviceInitAssignName(deviceInit, &deviceName);
    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: WdfDeviceInitAssignName failed 0x%x\n", status));
        WdfDeviceInitFree(deviceInit);
        return status;
    }

    // Инициализировать контекст
    WDF_OBJECT_ATTRIBUTES_INIT_CONTEXT_TYPE(&attributes, CONTROL_DEVICE_CONTEXT);
    attributes.ParentObject = FilterDevice;

    // Создать контрольное устройство
    status = WdfDeviceCreate(&deviceInit, &attributes, &controlDevice);
    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: WdfDeviceCreate for control device failed 0x%x\n", status));
        WdfDeviceInitFree(deviceInit);
        return status;
    }

    // Получить контекст контрольного устройства
    controlContext = GetControlDeviceContext(controlDevice);
    controlContext->FilterContext = FilterContext;

    // Создать очередь для контрольного устройства
    WDF_IO_QUEUE_CONFIG queueConfig;
    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&queueConfig, WdfIoQueueDispatchParallel);
    queueConfig.EvtIoDeviceControl = GyroMouseEvtDeviceControl;

    status = WdfIoQueueCreate(controlDevice,
        &queueConfig,
        WDF_NO_OBJECT_ATTRIBUTES,
        NULL);

    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: WdfIoQueueCreate for control device failed 0x%x\n", status));
        WdfObjectDelete(controlDevice);
        return status;
    }

    // Создать символическую ссылку
    RtlInitUnicodeString(&symbolicLinkName, L"\\DosDevices\\GyroMouseFilter");
    status = WdfDeviceCreateSymbolicLink(controlDevice, &symbolicLinkName);
    if (!NT_SUCCESS(status)) {
        KdPrint(("GyroMouseFilter: WdfDeviceCreateSymbolicLink failed 0x%x\n", status));
        WdfObjectDelete(controlDevice);
        return status;
    }

    // Установить устройство как контрольное
    WdfDeviceSetCharacteristics(controlDevice, FILE_DEVICE_SECURE_OPEN);
    WdfControlDeviceInitSetShutdownNotification(deviceInit, NULL, WdfDeviceShutdown);

    KdPrint(("GyroMouseFilter: Control device created successfully\n"));
    return STATUS_SUCCESS;
}

//
// Фильтрация данных мыши
//
VOID
GyroMouseFilterMouseData(
    _In_ PDEVICE_CONTEXT DeviceContext,
    _Inout_ PMOUSE_INPUT_DATA MouseData
)
{
    if (!DeviceContext->FilterEnabled || MouseData == NULL) {
        return;
    }

    LONG deltaX = MouseData->LastX;
    LONG deltaY = MouseData->LastY;

    if (abs(deltaX) < (LONG)DeviceContext->FilterThreshold &&
        abs(deltaY) < (LONG)DeviceContext->FilterThreshold) {
        MouseData->LastX = 0;
        MouseData->LastY = 0;
        KdPrint(("GyroMouseFilter: Filtered small movement X=%d Y=%d\n", deltaX, deltaY));
    }
    else {
        MouseData->LastX = (deltaX * 3 + DeviceContext->LastX) / 4;
        MouseData->LastY = (deltaY * 3 + DeviceContext->LastY) / 4;
        DeviceContext->LastX = MouseData->LastX;
        DeviceContext->LastY = MouseData->LastY;
        KdPrint(("GyroMouseFilter: Filtered movement X=%d Y=%d\n", MouseData->LastX, MouseData->LastY));
    }
}

//
// Completion routine для перехваченных запросов
//
VOID
GyroMouseRequestCompletionRoutine(
    _In_ WDFREQUEST Request,
    _In_ WDFIOTARGET Target,
    _In_ PWDF_REQUEST_COMPLETION_PARAMS Params,
    _In_ WDFCONTEXT Context
)
{
    PDEVICE_CONTEXT deviceContext = (PDEVICE_CONTEXT)Context;
    NTSTATUS status = Params->IoStatus.Status;

    UNREFERENCED_PARAMETER(Target);

    if (NT_SUCCESS(status)) {
        PVOID buffer = NULL;
        size_t bufferLength = 0;

        status = WdfRequestRetrieveOutputBuffer(Request,
            sizeof(MOUSE_INPUT_DATA),
            &buffer,
            &bufferLength);

        if (NT_SUCCESS(status) && buffer != NULL && bufferLength >= sizeof(MOUSE_INPUT_DATA)) {
            PMOUSE_INPUT_DATA mouseData = (PMOUSE_INPUT_DATA)buffer;
            ULONG numEntries = (ULONG)(bufferLength / sizeof(MOUSE_INPUT_DATA));

            for (ULONG i = 0; i < numEntries; i++) {
                PMOUSE_INPUT_DATA entry = &mouseData[i];

                if (deviceContext->BlockInput) {
                    entry->LastX = 0;
                    entry->LastY = 0;
                    KdPrint(("GyroMouseFilter: BLOCKED Delta X=%d Y=%d\n",
                        entry->LastX, entry->LastY));
                }
                else if (deviceContext->FilterEnabled) {
                    GyroMouseFilterMouseData(deviceContext, entry);
                }
            }
        }
    }

    WdfRequestComplete(Request, status);
}

//
// VHF Async Operation Complete
//
VOID
GyroMouseEvtVhfAsyncOperationComplete(
    _In_ PVHF_CONFIG VhfConfig,
    _In_ PVOID VhfContext,
    _In_ PVOID VhfOperationHandle,
    _In_ PHID_XFER_PACKET HidTransferPacket
)
{
    UNREFERENCED_PARAMETER(VhfConfig);
    UNREFERENCED_PARAMETER(VhfContext);
    UNREFERENCED_PARAMETER(VhfOperationHandle);
    UNREFERENCED_PARAMETER(HidTransferPacket);

    KdPrint(("GyroMouseFilter: VHF Async Operation Complete\n"));
}

//
// Обработка IOCTL команд для контрольного устройства
//
VOID
GyroMouseEvtDeviceControl(
    _In_ WDFQUEUE Queue,
    _In_ WDFREQUEST Request,
    _In_ size_t OutputBufferLength,
    _In_ size_t InputBufferLength,
    _In_ ULONG IoControlCode
)
{
    PCONTROL_DEVICE_CONTEXT controlContext;
    PDEVICE_CONTEXT deviceContext;
    NTSTATUS status = STATUS_SUCCESS;

    UNREFERENCED_PARAMETER(OutputBufferLength);
    UNREFERENCED_PARAMETER(InputBufferLength);

    controlContext = GetControlDeviceContext(WdfIoQueueGetDevice(Queue));
    deviceContext = controlContext->FilterContext;

    switch (IoControlCode) {

    case IOCTL_GYRO_SET_BLOCK: {
        BOOLEAN* blockFlag = NULL;
        size_t length = 0;

        status = WdfRequestRetrieveInputBuffer(Request,
            sizeof(BOOLEAN),
            (PVOID*)&blockFlag,
            &length);

        if (NT_SUCCESS(status) && blockFlag != NULL) {
            deviceContext->BlockInput = *blockFlag;
            KdPrint(("GyroMouseFilter: Block input set to %d\n",
                deviceContext->BlockInput));
        }

        WdfRequestComplete(Request, status);
        break;
    }

    case IOCTL_GYRO_SET_FILTER: {
        BOOLEAN* filterFlag = NULL;
        size_t length = 0;

        status = WdfRequestRetrieveInputBuffer(Request,
            sizeof(BOOLEAN),
            (PVOID*)&filterFlag,
            &length);

        if (NT_SUCCESS(status) && filterFlag != NULL) {
            deviceContext->FilterEnabled = *filterFlag;
            KdPrint(("GyroMouseFilter: Filter enabled set to %d\n",
                deviceContext->FilterEnabled));
        }

        WdfRequestComplete(Request, status);
        break;
    }

    case IOCTL_GYRO_SET_THRESHOLD: {
        PULONG threshold = NULL;
        size_t length = 0;

        status = WdfRequestRetrieveInputBuffer(Request,
            sizeof(ULONG),
            (PVOID*)&threshold,
            &length);

        if (NT_SUCCESS(status) && threshold != NULL) {
            deviceContext->FilterThreshold = *threshold;
            KdPrint(("GyroMouseFilter: Filter threshold set to %d\n",
                deviceContext->FilterThreshold));
        }

        WdfRequestComplete(Request, status);
        break;
    }

    case IOCTL_GYRO_GET_INFO: {
        PUSHORT info = NULL;
        size_t length = 0;

        status = WdfRequestRetrieveOutputBuffer(Request,
            sizeof(USHORT) * 2,
            (PVOID*)&info,
            &length);

        if (NT_SUCCESS(status) && info != NULL && length >= sizeof(USHORT) * 2) {
            info[0] = deviceContext->VendorId;
            info[1] = deviceContext->ProductId;
            WdfRequestSetInformation(Request, sizeof(USHORT) * 2);
        }
        else if (NT_SUCCESS(status)) {
            status = STATUS_BUFFER_TOO_SMALL;
        }

        WdfRequestComplete(Request, status);
        break;
    }

    default:
        WdfRequestComplete(Request, STATUS_INVALID_DEVICE_REQUEST);
        break;
    }
}

//
// GyroMouseEvtInternalDeviceControl - обработка IOCTL для фильтра
//
VOID
GyroMouseEvtInternalDeviceControl(
    _In_ WDFQUEUE Queue,
    _In_ WDFREQUEST Request,
    _In_ size_t OutputBufferLength,
    _In_ size_t InputBufferLength,
    _In_ ULONG IoControlCode
)
{
    PDEVICE_CONTEXT deviceContext;
    NTSTATUS status = STATUS_SUCCESS;
    BOOLEAN forwardRequest = TRUE;

    UNREFERENCED_PARAMETER(OutputBufferLength);
    UNREFERENCED_PARAMETER(InputBufferLength);

    deviceContext = GetDeviceContext(WdfIoQueueGetDevice(Queue));

    switch (IoControlCode) {

    case IOCTL_INTERNAL_MOUSE_CONNECT: {
        KdPrint(("GyroMouseFilter: IOCTL_INTERNAL_MOUSE_CONNECT\n"));
        break;
    }

    default:
        break;
    }

    if (forwardRequest) {
        WdfRequestFormatRequestUsingCurrentType(Request);

        WdfRequestSetCompletionRoutine(Request,
            GyroMouseRequestCompletionRoutine,
            deviceContext);

        if (!WdfRequestSend(Request, deviceContext->IoTarget, WDF_NO_SEND_OPTIONS)) {
            status = WdfRequestGetStatus(Request);
            KdPrint(("GyroMouseFilter: WdfRequestSend failed 0x%x\n", status));
            WdfRequestComplete(Request, status);
        }
    }
}
