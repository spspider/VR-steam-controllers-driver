# Button Mapping Guide for CVDriver

## Current Button Implementation

### Button Bit Mapping (uint16_t buttons)
```cpp
// Current implementation in UpdateButtonState()
Bit 0 (0x01): Trigger Click    -> /input/trigger/click
Bit 1 (0x02): Grip Button      -> /input/grip/click  
Bit 2 (0x04): Menu Button      -> /input/application_menu/click
Bit 3 (0x08): System Button    -> /input/system/click
Bits 4-15: Available for expansion
```

### Analog Inputs
```cpp
uint8_t trigger (0-255) -> /input/trigger/value (0.0-1.0)
```

## Adding New Buttons

### Step 1: Update Input Profile
Edit `resources/input/cvcontroller_profile.json`:

```json
{
  "input_source": {
    "/input/trackpad": {
      "type": "trackpad",
      "binding_image_point": [150, 80],
      "order": 5
    },
    "/input/a": {
      "type": "button", 
      "binding_image_point": [200, 50],
      "order": 6
    },
    "/input/b": {
      "type": "button",
      "binding_image_point": [200, 90], 
      "order": 7
    }
  }
}
```

### Step 2: Update Driver Header
Add to `src/driver.h`:

```cpp
class CVController {
private:
    // Expand input component handles array
    vr::VRInputComponentHandle_t m_inputComponentHandles[10]; 
    // [0-4] = existing buttons
    // [5] = trackpad_click
    // [6] = trackpad_x  
    // [7] = trackpad_y
    // [8] = button_a
    // [9] = button_b
};
```

### Step 3: Update Controller Implementation
Add to `CVController::Activate()`:

```cpp
// Trackpad components
VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, 
    "/input/trackpad/click", &m_inputComponentHandles[5]);
VRDriverInput()->CreateScalarComponent(m_ulPropertyContainer, 
    "/input/trackpad/x", &m_inputComponentHandles[6], 
    VRScalarType_Absolute, VRScalarUnits_NormalizedTwoSided);
VRDriverInput()->CreateScalarComponent(m_ulPropertyContainer, 
    "/input/trackpad/y", &m_inputComponentHandles[7], 
    VRScalarType_Absolute, VRScalarUnits_NormalizedTwoSided);

// Additional buttons
VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, 
    "/input/a/click", &m_inputComponentHandles[8]);
VRDriverInput()->CreateBooleanComponent(m_ulPropertyContainer, 
    "/input/b/click", &m_inputComponentHandles[9]);
```

### Step 4: Update Button State Handler
Expand `UpdateButtonState()`:

```cpp
void CVController::UpdateButtonState(uint16_t buttons, uint8_t trigger, 
                                   float trackpad_x = 0.0f, float trackpad_y = 0.0f) {
    // Existing buttons (bits 0-3)
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[0], 
        (buttons & 0x01) != 0, 0);
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[1], 
        (buttons & 0x02) != 0, 0);
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[2], 
        (buttons & 0x04) != 0, 0);
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[3], 
        (buttons & 0x08) != 0, 0);
    
    // New buttons (bits 4-7)
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[5], 
        (buttons & 0x10) != 0, 0); // Trackpad click
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[8], 
        (buttons & 0x20) != 0, 0); // Button A
    VRDriverInput()->UpdateBooleanComponent(m_inputComponentHandles[9], 
        (buttons & 0x40) != 0, 0); // Button B
    
    // Analog values
    VRDriverInput()->UpdateScalarComponent(m_inputComponentHandles[4], 
        trigger / 255.0f, 0);
    VRDriverInput()->UpdateScalarComponent(m_inputComponentHandles[6], 
        trackpad_x, 0);
    VRDriverInput()->UpdateScalarComponent(m_inputComponentHandles[7], 
        trackpad_y, 0);
}
```

## Standard SteamVR Input Paths

### Buttons
- `/input/trigger/click` - Trigger as button
- `/input/grip/click` - Side grip button  
- `/input/application_menu/click` - Menu button
- `/input/system/click` - System button
- `/input/a/click` - A button
- `/input/b/click` - B button
- `/input/x/click` - X button  
- `/input/y/click` - Y button

### Analog Inputs
- `/input/trigger/value` - Trigger analog (0.0-1.0)
- `/input/trackpad/x` - Trackpad X (-1.0 to 1.0)
- `/input/trackpad/y` - Trackpad Y (-1.0 to 1.0)
- `/input/joystick/x` - Joystick X (-1.0 to 1.0)
- `/input/joystick/y` - Joystick Y (-1.0 to 1.0)

### Special Inputs
- `/input/trackpad/click` - Trackpad press
- `/input/trackpad/touch` - Trackpad touch
- `/input/joystick/click` - Joystick press
- `/output/haptic` - Haptic feedback

## Data Protocol Extension

### Current ControllerData Structure
```cpp
struct ControllerData {
    uint8_t controller_id;      // 0=left, 1=right, 2=HMD
    uint32_t packet_number;     // Sequence number
    float quat_w, quat_x, quat_y, quat_z;  // Orientation
    float accel_x, accel_y, accel_z;       // Position
    float gyro_x, gyro_y, gyro_z;          // Angular velocity
    uint16_t buttons;           // Button bitmask (16 buttons max)
    uint8_t trigger;            // Trigger value (0-255)
    uint8_t checksum;           // Data integrity
};
```

### Extended Structure (if needed)
```cpp
struct ExtendedControllerData {
    uint8_t controller_id;
    uint32_t packet_number;
    float quat_w, quat_x, quat_y, quat_z;
    float accel_x, accel_y, accel_z;
    float gyro_x, gyro_y, gyro_z;
    uint16_t buttons;           // 16 buttons
    uint8_t trigger;            // Trigger (0-255)
    int8_t trackpad_x;          // Trackpad X (-127 to 127)
    int8_t trackpad_y;          // Trackpad Y (-127 to 127)
    uint8_t checksum;
};
```

## Testing New Buttons

1. **Update simulator**: Modify `simple_simulator.py` to send new button data
2. **Test in SteamVR**: Check SteamVR Settings → Controllers → Manage Controllers
3. **Verify bindings**: Ensure buttons appear in SteamVR binding interface
4. **Test applications**: Verify buttons work in VR applications

## Common Issues

1. **Buttons not appearing**: Check input profile JSON syntax
2. **Buttons not responding**: Verify component handle creation and updates
3. **Wrong button mapping**: Check bit positions in UpdateButtonState()
4. **SteamVR not recognizing**: Restart SteamVR after driver changes