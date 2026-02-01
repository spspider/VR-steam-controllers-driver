#!/usr/bin/env python3
"""
Module: gamepad_controller.py
Game Controller Integration for VR Tracking Hub

This module provides complete integration of physical game controllers (joysticks/gamepads)
with the VR tracking system. It handles:
  1. Detection and selection of connected game controllers
  2. Assignment of controllers to VR hands (left/right)
  3. Customizable button mapping with GUI
  4. Real-time button state forwarding to SteamVR driver
  5. Persistent configuration saving/loading

ARCHITECTURE OVERVIEW:
┌─────────────────────────────────────────────────────────────────────┐
│                    GamepadControllerManager                         │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────────────┐ │
│  │ Pygame Init    │  │ Config Manager  │  │ Button State Tracker │ │
│  │ - Joystick     │  │ - JSON Load/Save│  │ - Per-controller     │ │
│  │ - Detection    │  │ - Button Maps   │  │ - Real-time polling  │ │
│  └────────────────┘  └─────────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    VR Tracking Hub Integration                      │
│  - Updates ControllerData.buttons (uint16 bitmask)                  │
│  - Updates ControllerData.trigger (uint8 0-255)                     │
│  - Sends to NetworkHandler → SteamVR Driver (port 5555)            │
└─────────────────────────────────────────────────────────────────────┘

BUTTON MAPPING SYSTEM:
Each physical gamepad button can be mapped to a VR controller button.
The mapping format in JSON:
{
  "left_controller": {
    "gamepad_index": 0,           # Which physical gamepad to use
    "button_map": {
      "0": "trigger_click",       # Button 0 → VR trigger click (bit 0)
      "1": "grip_click",          # Button 1 → VR grip click (bit 1)
      "2": "menu_click",          # Button 2 → VR menu (bit 2)
      "3": "system_click",        # Button 3 → VR system (bit 3)
      "4": "trackpad_click",      # Button 4 → VR trackpad (bit 4)
      "5": "button_a",            # Button 5 → VR button A (bit 5)
      "6": "button_b"             # Button 6 → VR button B (bit 6)
    },
    "axis_map": {
      "2": "trigger_value"        # Axis 2 → trigger analog value
    }
  },
  "right_controller": {
    "gamepad_index": 1,
    "button_map": { ... },
    "axis_map": { ... }
  }
}

VR BUTTON BIT MAPPING (matches CVDriver expectations):
  Bit 0 (0x01): Trigger Click
  Bit 1 (0x02): Grip Click
  Bit 2 (0x04): Menu Click
  Bit 3 (0x08): System Click
  Bit 4 (0x10): Trackpad Click
  Bit 5 (0x20): Button A
  Bit 6 (0x40): Button B
  Bit 7 (0x80): Button X
  Bit 8 (0x100): Button Y
  Bits 9-15: Reserved for future expansion

USAGE:
  # Initialize
  gamepad_mgr = GamepadControllerManager(log_callback=hub.log)
  
  # Start polling
  gamepad_mgr.start()
  
  # In main loop, update VR controller data
  buttons_left, trigger_left = gamepad_mgr.get_button_state(0)  # Left controller
  buttons_right, trigger_right = gamepad_mgr.get_button_state(1)  # Right controller
  
  controllers[0].buttons = buttons_left
  controllers[0].trigger = trigger_left
  controllers[1].buttons = buttons_right
  controllers[1].trigger = trigger_right
  
  # Open GUI for configuration
  gamepad_mgr.open_configuration_gui(parent_window)
"""

import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Dict, List, Optional, Callable, Tuple

try:
    import pygame
    import pygame.joystick
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


# VR button bit definitions (matches BUTTON_MAPPING_GUIDE.md)
VR_BUTTON_BITS = {
    'trigger_click': 0,      # Bit 0 (0x01)
    'grip_click': 1,         # Bit 1 (0x02)
    'menu_click': 2,         # Bit 2 (0x04)
    'system_click': 3,       # Bit 3 (0x08)
    'trackpad_click': 4,     # Bit 4 (0x10)
    'button_a': 5,           # Bit 5 (0x20)
    'button_b': 6,           # Bit 6 (0x40)
    'button_x': 7,           # Bit 7 (0x80)
    'button_y': 8,           # Bit 8 (0x100)
}

# Default button mappings for common gamepads (Xbox-style layout)
DEFAULT_BUTTON_MAP_XBOX = {
    '0': 'button_a',         # A button
    '1': 'button_b',         # B button
    '2': 'button_x',         # X button
    '3': 'button_y',         # Y button
    '4': 'grip_click',       # LB (Left Bumper)
    '5': 'trigger_click',    # RB (Right Bumper) - CRITICAL FIX: Maps to trigger CLICK (bit 0 in CVDriver)
    '6': 'menu_click',       # Back/Select
    '7': 'system_click',     # Start
    '8': 'trackpad_click',   # Left stick click
    '9': 'trackpad_click',   # Right stick click
}

DEFAULT_AXIS_MAP_XBOX = {
    '2': 'trigger_value',    # Right trigger (RT) axis - Maps analog value (0-255) to SteamVR driver
}


class GamepadControllerManager:
    """
    Manages physical gamepad integration with VR controllers.
    
    Responsibilities:
      - Initialize pygame joystick subsystem
      - Detect connected gamepads
      - Map physical buttons to VR button bits
      - Poll button/axis states in real-time
      - Provide button state to VR tracking hub
      - Save/load configuration from JSON
    """
    
    CONFIG_FILE = "gamepad_config.json"
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        """
        Initialize the gamepad controller manager.
        
        Args:
            log_callback: Function to call for logging messages (message, level)
        """
        self.log_callback = log_callback
        self.running = False
        self.poll_thread: Optional[threading.Thread] = None
        
        # Gamepad assignments: {vr_controller_id: gamepad_index}
        # vr_controller_id: 0=LEFT, 1=RIGHT
        self.gamepad_assignments = {
            0: None,  # Left VR controller
            1: None   # Right VR controller
        }
        
        # Button mappings: {vr_controller_id: {physical_button: vr_button_name}}
        self.button_maps = {
            0: {},  # Left controller button map
            1: {}   # Right controller button map
        }
        
        # Axis mappings: {vr_controller_id: {physical_axis: vr_axis_name}}
        self.axis_maps = {
            0: {},  # Left controller axis map
            1: {}   # Right controller axis map
        }
        
        # Current button states: {vr_controller_id: (buttons_bitmask, trigger_value)}
        self.button_states = {
            0: (0, 0),  # Left controller (buttons, trigger)
            1: (0, 0)   # Right controller (buttons, trigger)
        }
        
        # Pygame joystick objects
        self.joysticks: List[pygame.joystick.Joystick] = []
        
        # Check pygame availability
        if not PYGAME_AVAILABLE:
            self.log("ERROR: pygame not available. Install with: pip install pygame", "ERROR")
            return
        
        # Initialize pygame joystick subsystem
        try:
            pygame.init()
            pygame.joystick.init()
            self.log("✅ Pygame joystick subsystem initialized")
        except Exception as e:
            self.log(f"ERROR: Failed to initialize pygame: {e}", "ERROR")
            return
        
        # Load saved configuration
        self.load_config()
        
        # Detect connected joysticks
        self.refresh_joysticks()
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message via callback or print."""
        if self.log_callback:
            self.log_callback(message, level)
        else:
            print(f"[{level}] {message}")
    
    def refresh_joysticks(self):
        """
        Detect and initialize all connected joysticks.
        
        Called on startup and when user clicks "Refresh" in GUI.
        Each joystick is given an index (0, 1, 2...) which is used for assignment.
        """
        if not PYGAME_AVAILABLE:
            return
        
        # Clear existing joysticks
        for joy in self.joysticks:
            try:
                joy.quit()
            except:
                pass
        self.joysticks.clear()
        
        # Re-initialize joystick subsystem to detect new devices
        pygame.joystick.quit()
        pygame.joystick.init()
        
        # Get count of connected joysticks
        joystick_count = pygame.joystick.get_count()
        
        if joystick_count == 0:
            self.log("⚠️ No gamepads detected")
            return
        
        # Initialize each joystick
        for i in range(joystick_count):
            try:
                joy = pygame.joystick.Joystick(i)
                joy.init()
                self.joysticks.append(joy)
                
                name = joy.get_name()
                num_buttons = joy.get_numbuttons()
                num_axes = joy.get_numaxes()
                num_hats = joy.get_numhats()
                
                self.log(f"✅ Gamepad {i}: {name}")
                self.log(f"   Buttons: {num_buttons}, Axes: {num_axes}, Hats: {num_hats}")
                
            except Exception as e:
                self.log(f"ERROR: Failed to initialize joystick {i}: {e}", "ERROR")
        
        self.log(f"Total gamepads detected: {len(self.joysticks)}")
    
    def get_joystick_list(self) -> List[str]:
        """
        Get list of connected joystick names for GUI dropdown.
        
        Returns:
            List of strings like ["0: Xbox Controller", "1: PS4 Controller", ...]
        """
        result = ["None"]  # Option to unassign
        for i, joy in enumerate(self.joysticks):
            name = joy.get_name()
            result.append(f"{i}: {name}")
        return result
    
    def assign_gamepad(self, vr_controller_id: int, gamepad_index: Optional[int]):
        """
        Assign a physical gamepad to a VR controller.
        
        Args:
            vr_controller_id: 0=LEFT, 1=RIGHT
            gamepad_index: Index of physical gamepad, or None to unassign
        """
        if gamepad_index is not None and (gamepad_index < 0 or gamepad_index >= len(self.joysticks)):
            self.log(f"ERROR: Invalid gamepad index {gamepad_index}", "ERROR")
            return
        
        self.gamepad_assignments[vr_controller_id] = gamepad_index
        
        if gamepad_index is None:
            self.log(f"Gamepad unassigned from VR controller {vr_controller_id}")
        else:
            name = self.joysticks[gamepad_index].get_name()
            self.log(f"Gamepad {gamepad_index} ({name}) assigned to VR controller {vr_controller_id}")
        
        self.save_config()
    
    def set_button_mapping(self, vr_controller_id: int, physical_button: str, vr_button: str):
        """
        Map a physical button to a VR button.
        
        Args:
            vr_controller_id: 0=LEFT, 1=RIGHT
            physical_button: String button number like "0", "1", etc.
            vr_button: VR button name like "trigger_click", "grip_click", etc.
        """
        if vr_button not in VR_BUTTON_BITS and vr_button != 'none':
            self.log(f"ERROR: Unknown VR button '{vr_button}'", "ERROR")
            return
        
        if vr_button == 'none':
            # Remove mapping
            if physical_button in self.button_maps[vr_controller_id]:
                del self.button_maps[vr_controller_id][physical_button]
        else:
            self.button_maps[vr_controller_id][physical_button] = vr_button
        
        self.save_config()
    
    def set_axis_mapping(self, vr_controller_id: int, physical_axis: str, vr_axis: str):
        """
        Map a physical axis to a VR axis.
        
        Args:
            vr_controller_id: 0=LEFT, 1=RIGHT
            physical_axis: String axis number like "0", "1", etc.
            vr_axis: VR axis name like "trigger_value"
        """
        if vr_axis == 'none':
            # Remove mapping
            if physical_axis in self.axis_maps[vr_controller_id]:
                del self.axis_maps[vr_controller_id][physical_axis]
        else:
            self.axis_maps[vr_controller_id][physical_axis] = vr_axis
        
        self.save_config()
    
    def load_default_mappings(self, vr_controller_id: int):
        """
        Load default Xbox-style button mappings for a controller.
        
        Args:
            vr_controller_id: 0=LEFT, 1=RIGHT
        """
        self.button_maps[vr_controller_id] = DEFAULT_BUTTON_MAP_XBOX.copy()
        self.axis_maps[vr_controller_id] = DEFAULT_AXIS_MAP_XBOX.copy()
        self.log(f"Loaded default Xbox mappings for VR controller {vr_controller_id}")
        self.save_config()
    
    def start(self):
        """
        Start the gamepad polling thread.
        
        This thread runs at ~60Hz polling all assigned gamepads and updating button states.
        The VR tracking hub main loop can then read these states via get_button_state().
        """
        if not PYGAME_AVAILABLE:
            self.log("ERROR: Cannot start - pygame not available", "ERROR")
            return
        
        if self.running:
            self.log("Gamepad polling already running")
            return
        
        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()
        self.log("✅ Gamepad polling started")
    
    def stop(self):
        """Stop the gamepad polling thread."""
        if self.running:
            self.running = False
            if self.poll_thread:
                self.poll_thread.join(timeout=1.0)
            self.log("Gamepad polling stopped")
    
    def _poll_loop(self):
        """
        Main polling loop - runs in background thread.
        
        Continuously polls pygame events and updates button states for each VR controller.
        Runs at ~60Hz to match typical VR frame rate.
        """
        while self.running:
            try:
                # Process pygame events (required for joystick state updates)
                pygame.event.pump()
                
                # Update button states for each VR controller
                for vr_id in [0, 1]:
                    gamepad_idx = self.gamepad_assignments[vr_id]
                    
                    if gamepad_idx is None or gamepad_idx >= len(self.joysticks):
                        # No gamepad assigned or invalid index
                        self.button_states[vr_id] = (0, 0)
                        continue
                    
                    joystick = self.joysticks[gamepad_idx]
                    
                    # Build button bitmask by checking each mapped button
                    buttons_bitmask = 0
                    for phys_btn_str, vr_btn_name in self.button_maps[vr_id].items():
                        try:
                            phys_btn = int(phys_btn_str)
                            if phys_btn < joystick.get_numbuttons():
                                is_pressed = joystick.get_button(phys_btn)
                                if is_pressed:
                                    # Set the corresponding bit
                                    bit_position = VR_BUTTON_BITS[vr_btn_name]
                                    buttons_bitmask |= (1 << bit_position)
                        except (ValueError, KeyError, IndexError):
                            pass
                    
                    # Get trigger value from mapped axis
                    trigger_value = 0
                    for phys_axis_str, vr_axis_name in self.axis_maps[vr_id].items():
                        try:
                            if vr_axis_name == 'trigger_value':
                                phys_axis = int(phys_axis_str)
                                if phys_axis < joystick.get_numaxes():
                                    # Axis value is -1.0 to 1.0, convert to 0-255
                                    axis_val = joystick.get_axis(phys_axis)
                                    # Normalize to 0-255 (assuming trigger axis goes 0.0 to 1.0 or -1.0 to 1.0)
                                    trigger_value = int(max(0, min(255, (axis_val + 1.0) * 127.5)))
                        except (ValueError, KeyError, IndexError):
                            pass
                    
                    # Update state
                    self.button_states[vr_id] = (buttons_bitmask, trigger_value)
                
            except Exception as e:
                self.log(f"ERROR in gamepad poll loop: {e}", "ERROR")
            
            # Sleep to maintain ~60Hz polling rate
            time.sleep(1.0 / 60.0)
    
    def get_button_state(self, vr_controller_id: int) -> Tuple[int, int]:
        """
        Get current button state for a VR controller.
        
        Args:
            vr_controller_id: 0=LEFT, 1=RIGHT
        
        Returns:
            Tuple of (buttons_bitmask, trigger_value)
            - buttons_bitmask: uint16 with button bits set (0x0000 to 0xFFFF)
            - trigger_value: uint8 trigger analog value (0 to 255)
        """
        return self.button_states.get(vr_controller_id, (0, 0))
    
    def save_config(self):
        """
        Save current configuration to JSON file.
        
        Saves:
          - Gamepad assignments (which physical gamepad for each VR controller)
          - Button mappings (physical button → VR button)
          - Axis mappings (physical axis → VR axis)
        """
        config = {
            'left_controller': {
                'gamepad_index': self.gamepad_assignments[0],
                'button_map': self.button_maps[0],
                'axis_map': self.axis_maps[0]
            },
            'right_controller': {
                'gamepad_index': self.gamepad_assignments[1],
                'button_map': self.button_maps[1],
                'axis_map': self.axis_maps[1]
            }
        }
        
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            self.log(f"Configuration saved to {self.CONFIG_FILE}")
        except Exception as e:
            self.log(f"ERROR: Failed to save config: {e}", "ERROR")
    
    def load_config(self):
        """
        Load configuration from JSON file.
        
        If file doesn't exist, uses default values (no assignments, empty mappings).
        """
        if not os.path.exists(self.CONFIG_FILE):
            self.log(f"No config file found, using defaults")
            return
        
        try:
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Load left controller config
            if 'left_controller' in config:
                left_cfg = config['left_controller']
                self.gamepad_assignments[0] = left_cfg.get('gamepad_index', None)
                self.button_maps[0] = left_cfg.get('button_map', {})
                self.axis_maps[0] = left_cfg.get('axis_map', {})
            
            # Load right controller config
            if 'right_controller' in config:
                right_cfg = config['right_controller']
                self.gamepad_assignments[1] = right_cfg.get('gamepad_index', None)
                self.button_maps[1] = right_cfg.get('button_map', {})
                self.axis_maps[1] = right_cfg.get('axis_map', {})
            
            self.log(f"✅ Configuration loaded from {self.CONFIG_FILE}")
            
        except Exception as e:
            self.log(f"ERROR: Failed to load config: {e}", "ERROR")
    
    def open_configuration_gui(self, parent: Optional[tk.Tk] = None):
        """
        Open the gamepad configuration GUI window.
        
        This provides a user interface for:
          - Selecting which gamepad to assign to each VR controller
          - Mapping physical buttons to VR buttons
          - Testing button presses in real-time
          - Saving/loading configurations
        
        Args:
            parent: Parent tkinter window (optional)
        """
        GamepadConfigGUI(self, parent)


class GamepadConfigGUI:
    """
    GUI window for configuring gamepad button mappings.
    
    Layout:
    ┌─────────────────────────────────────────────────────┐
    │  Gamepad Configuration                              │
    ├─────────────────────────────────────────────────────┤
    │  LEFT Controller                                    │
    │    Gamepad: [Dropdown]  [Refresh] [Load Defaults]  │
    │                                                     │
    │    Button Mapping:                                  │
    │      Physical Button 0 → [VR Button Dropdown]      │
    │      Physical Button 1 → [VR Button Dropdown]      │
    │      ...                                            │
    │                                                     │
    │  RIGHT Controller                                   │
    │    Gamepad: [Dropdown]  [Refresh] [Load Defaults]  │
    │    Button Mapping: ...                              │
    │                                                     │
    │  Live Test Panel                                    │
    │    Shows real-time button presses                   │
    │                                                     │
    │  [Save] [Close]                                     │
    └─────────────────────────────────────────────────────┘
    """
    
    def __init__(self, manager: GamepadControllerManager, parent: Optional[tk.Tk] = None):
        """
        Initialize the configuration GUI.
        
        Args:
            manager: GamepadControllerManager instance
            parent: Parent window (creates new Toplevel if provided)
        """
        self.manager = manager
        
        # Create window
        if parent:
            self.window = tk.Toplevel(parent)
        else:
            self.window = tk.Tk()
        
        self.window.title("Gamepad Configuration")
        self.window.geometry("900x700")
        
        # Controller selection variables
        self.left_gamepad_var = tk.StringVar(value="None")
        self.right_gamepad_var = tk.StringVar(value="None")
        
        # Button mapping widgets storage
        self.left_button_vars: Dict[int, tk.StringVar] = {}
        self.right_button_vars: Dict[int, tk.StringVar] = {}
        self.left_axis_vars: Dict[int, tk.StringVar] = {}
        self.right_axis_vars: Dict[int, tk.StringVar] = {}
        
        # Build GUI
        self.create_widgets()
        
        # Load current assignments
        self.load_current_config()
        
        # Start live test updates
        self.update_live_test()
    
    def create_widgets(self):
        """Create all GUI widgets with proper scrolling for large configuration panels."""
        
        # Main container with tabs for LEFT and RIGHT controllers
        # Each tab contains scrollable content to prevent window overflow
        notebook = ttk.Notebook(self.window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create scrollable container for LEFT controller (fits all content with scroll if needed)
        left_outer = ttk.Frame(notebook)
        notebook.add(left_outer, text="LEFT Controller")
        
        left_canvas = tk.Canvas(left_outer, highlightthickness=0)
        left_scrollbar = ttk.Scrollbar(left_outer, orient="vertical", command=left_canvas.yview)
        left_frame = ttk.Frame(left_canvas)
        
        left_frame.bind(
            "<Configure>",
            lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        )
        
        left_canvas.create_window((0, 0), window=left_frame, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.create_controller_config(left_frame, 0, self.left_gamepad_var, 
                                      self.left_button_vars, self.left_axis_vars)
        
        # Create scrollable container for RIGHT controller
        right_outer = ttk.Frame(notebook)
        notebook.add(right_outer, text="RIGHT Controller")
        
        right_canvas = tk.Canvas(right_outer, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_outer, orient="vertical", command=right_canvas.yview)
        right_frame = ttk.Frame(right_canvas)
        
        right_frame.bind(
            "<Configure>",
            lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        )
        
        right_canvas.create_window((0, 0), window=right_frame, anchor="nw")
        right_canvas.configure(yscrollcommand=right_scrollbar.set)
        
        right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.create_controller_config(right_frame, 1, self.right_gamepad_var,
                                      self.right_button_vars, self.right_axis_vars)
        
        # Live test panel - shows real-time button state
        test_frame = ttk.LabelFrame(self.window, text="Live Test", padding=10)
        test_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.test_text = scrolledtext.ScrolledText(test_frame, height=6, font=("Courier", 9))
        self.test_text.pack(fill=tk.BOTH, expand=True)
        
        # Bottom control buttons - always visible
        btn_frame = ttk.Frame(self.window, padding=10)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # SAVE button - prominent on left side
        ttk.Button(btn_frame, text="💾 Save Configuration", 
                  command=self.save_and_close, width=25).pack(side=tk.LEFT, padx=5)
        
        # CLOSE button - secondary on right side
        ttk.Button(btn_frame, text="❌ Close Without Saving", 
                  command=self.window.destroy, width=25).pack(side=tk.RIGHT, padx=5)
    
    def create_controller_config(self, parent: ttk.Frame, vr_id: int, 
                                gamepad_var: tk.StringVar,
                                button_vars: Dict[int, tk.StringVar],
                                axis_vars: Dict[int, tk.StringVar]):
        """
        Create configuration widgets for one controller.
        
        Args:
            parent: Parent frame
            vr_id: VR controller ID (0=LEFT, 1=RIGHT)
            gamepad_var: StringVar for gamepad selection
            button_vars: Dictionary to store button mapping StringVars
            axis_vars: Dictionary to store axis mapping StringVars
        """
        # Gamepad selection
        sel_frame = ttk.LabelFrame(parent, text="Gamepad Selection", padding=10)
        sel_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(sel_frame, text="Select Gamepad:").pack(side=tk.LEFT, padx=5)
        
        gamepad_combo = ttk.Combobox(sel_frame, textvariable=gamepad_var, 
                                     values=self.manager.get_joystick_list(),
                                     state='readonly', width=40)
        gamepad_combo.pack(side=tk.LEFT, padx=5)
        gamepad_combo.bind('<<ComboboxSelected>>', 
                          lambda e: self.on_gamepad_selected(vr_id, gamepad_var))
        
        ttk.Button(sel_frame, text="🔄 Refresh", 
                  command=self.refresh_gamepads).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(sel_frame, text="📋 Load Defaults", 
                  command=lambda: self.load_defaults(vr_id)).pack(side=tk.LEFT, padx=5)
        
        # Button mapping section
        btn_map_frame = ttk.LabelFrame(parent, text="Button Mapping", padding=10)
        btn_map_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create scrollable frame for button mappings
        canvas = tk.Canvas(btn_map_frame, height=200)
        scrollbar = ttk.Scrollbar(btn_map_frame, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # VR button options
        vr_button_options = ['none'] + list(VR_BUTTON_BITS.keys())
        
        # Create mapping rows for buttons (0-15)
        ttk.Label(scroll_frame, text="Physical Button", font=("", 9, "bold")).grid(
            row=0, column=0, padx=5, pady=2, sticky=tk.W)
        ttk.Label(scroll_frame, text="→ VR Button", font=("", 9, "bold")).grid(
            row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        for btn_num in range(16):  # Support up to 16 buttons
            ttk.Label(scroll_frame, text=f"Button {btn_num}:").grid(
                row=btn_num+1, column=0, padx=5, pady=2, sticky=tk.W)
            
            var = tk.StringVar(value='none')
            combo = ttk.Combobox(scroll_frame, textvariable=var, 
                               values=vr_button_options, state='readonly', width=20)
            combo.grid(row=btn_num+1, column=1, padx=5, pady=2, sticky=tk.W)
            combo.bind('<<ComboboxSelected>>', 
                      lambda e, vid=vr_id, bn=btn_num, v=var: 
                      self.on_button_mapped(vid, bn, v))
            
            button_vars[btn_num] = var
        
        # Axis mapping section - scrollable like button mapping
        # Axis 2 should be mapped to 'trigger_value' which sends analog trigger (0-255) to SteamVR
        axis_frame = ttk.LabelFrame(parent, text="Axis Mapping", padding=10)
        axis_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create scrollable frame for axis mappings
        axis_canvas = tk.Canvas(axis_frame, height=150)
        axis_scrollbar = ttk.Scrollbar(axis_frame, orient="vertical", command=axis_canvas.yview)
        axis_scroll_frame = ttk.Frame(axis_canvas)
        
        axis_scroll_frame.bind(
            "<Configure>",
            lambda e: axis_canvas.configure(scrollregion=axis_canvas.bbox("all"))
        )
        
        axis_canvas.create_window((0, 0), window=axis_scroll_frame, anchor="nw")
        axis_canvas.configure(yscrollcommand=axis_scrollbar.set)
        
        axis_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        axis_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        vr_axis_options = ['none', 'trigger_value']
        
        ttk.Label(axis_scroll_frame, text="Physical Axis", font=("", 9, "bold")).grid(
            row=0, column=0, padx=5, pady=2, sticky=tk.W)
        ttk.Label(axis_scroll_frame, text="→ VR Axis", font=("", 9, "bold")).grid(
            row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        for axis_num in range(8):  # Support up to 8 axes
            ttk.Label(axis_scroll_frame, text=f"Axis {axis_num}:").grid(
                row=axis_num+1, column=0, padx=5, pady=2, sticky=tk.W)
            
            var = tk.StringVar(value='none')
            combo = ttk.Combobox(axis_scroll_frame, textvariable=var,
                               values=vr_axis_options, state='readonly', width=20)
            combo.grid(row=axis_num+1, column=1, padx=5, pady=2, sticky=tk.W)
            combo.bind('<<ComboboxSelected>>',
                      lambda e, vid=vr_id, an=axis_num, v=var:
                      self.on_axis_mapped(vid, an, v))
            
            axis_vars[axis_num] = var
    
    def refresh_gamepads(self):
        """Refresh the list of connected gamepads."""
        self.manager.refresh_joysticks()
        
        # Update dropdown lists
        joystick_list = self.manager.get_joystick_list()
        
        # Find combo boxes and update their values
        for child in self.window.winfo_children():
            if isinstance(child, ttk.Notebook):
                for tab in child.winfo_children():
                    for frame in tab.winfo_children():
                        if isinstance(frame, ttk.LabelFrame) and "Selection" in frame.cget('text'):
                            for widget in frame.winfo_children():
                                if isinstance(widget, ttk.Combobox):
                                    widget['values'] = joystick_list
    
    def load_current_config(self):
        """Load current configuration into GUI widgets."""
        # Set gamepad selections
        left_idx = self.manager.gamepad_assignments[0]
        right_idx = self.manager.gamepad_assignments[1]
        
        joystick_list = self.manager.get_joystick_list()
        
        if left_idx is not None and left_idx < len(self.manager.joysticks):
            self.left_gamepad_var.set(joystick_list[left_idx + 1])
        else:
            self.left_gamepad_var.set("None")
        
        if right_idx is not None and right_idx < len(self.manager.joysticks):
            self.right_gamepad_var.set(joystick_list[right_idx + 1])
        else:
            self.right_gamepad_var.set("None")
        
        # Set button mappings for LEFT
        for btn_num, var in self.left_button_vars.items():
            btn_str = str(btn_num)
            if btn_str in self.manager.button_maps[0]:
                var.set(self.manager.button_maps[0][btn_str])
            else:
                var.set('none')
        
        # Set button mappings for RIGHT
        for btn_num, var in self.right_button_vars.items():
            btn_str = str(btn_num)
            if btn_str in self.manager.button_maps[1]:
                var.set(self.manager.button_maps[1][btn_str])
            else:
                var.set('none')
        
        # Set axis mappings for LEFT
        for axis_num, var in self.left_axis_vars.items():
            axis_str = str(axis_num)
            if axis_str in self.manager.axis_maps[0]:
                var.set(self.manager.axis_maps[0][axis_str])
            else:
                var.set('none')
        
        # Set axis mappings for RIGHT
        for axis_num, var in self.right_axis_vars.items():
            axis_str = str(axis_num)
            if axis_str in self.manager.axis_maps[1]:
                var.set(self.manager.axis_maps[1][axis_str])
            else:
                var.set('none')
    
    def on_gamepad_selected(self, vr_id: int, gamepad_var: tk.StringVar):
        """Handle gamepad selection change."""
        selection = gamepad_var.get()
        
        if selection == "None":
            self.manager.assign_gamepad(vr_id, None)
        else:
            # Extract index from "0: Controller Name" format
            try:
                gamepad_idx = int(selection.split(':')[0])
                self.manager.assign_gamepad(vr_id, gamepad_idx)
            except (ValueError, IndexError):
                messagebox.showerror("Error", "Invalid gamepad selection")
    
    def on_button_mapped(self, vr_id: int, button_num: int, var: tk.StringVar):
        """Handle button mapping change."""
        vr_button = var.get()
        self.manager.set_button_mapping(vr_id, str(button_num), vr_button)
    
    def on_axis_mapped(self, vr_id: int, axis_num: int, var: tk.StringVar):
        """Handle axis mapping change."""
        vr_axis = var.get()
        self.manager.set_axis_mapping(vr_id, str(axis_num), vr_axis)
    
    def load_defaults(self, vr_id: int):
        """Load default Xbox-style mappings."""
        self.manager.load_default_mappings(vr_id)
        self.load_current_config()
        messagebox.showinfo("Success", "Default Xbox mappings loaded")
    
    def update_live_test(self):
        """Update the live test panel showing current button states."""
        if not self.window.winfo_exists():
            return
        
        try:
            # Get current button states
            left_buttons, left_trigger = self.manager.get_button_state(0)
            right_buttons, right_trigger = self.manager.get_button_state(1)
            
            # Format output
            lines = []
            lines.append("=== LIVE BUTTON TEST ===")
            lines.append("")
            lines.append(f"LEFT Controller  (Buttons: 0x{left_buttons:04X}, Trigger: {left_trigger})")
            
            # Show which buttons are pressed
            for vr_btn_name, bit_pos in VR_BUTTON_BITS.items():
                if left_buttons & (1 << bit_pos):
                    lines.append(f"  ✓ {vr_btn_name}")
            
            lines.append("")
            lines.append(f"RIGHT Controller (Buttons: 0x{right_buttons:04X}, Trigger: {right_trigger})")
            
            for vr_btn_name, bit_pos in VR_BUTTON_BITS.items():
                if right_buttons & (1 << bit_pos):
                    lines.append(f"  ✓ {vr_btn_name}")
            
            # Update text widget
            self.test_text.delete('1.0', tk.END)
            self.test_text.insert('1.0', '\n'.join(lines))
            
        except Exception as e:
            pass
        
        # Schedule next update (10 FPS is enough for display)
        self.window.after(100, self.update_live_test)
    
    def save_and_close(self):
        """Save configuration and close window."""
        self.manager.save_config()
        messagebox.showinfo("Success", "Configuration saved successfully")
        self.window.destroy()


# Example usage and testing
if __name__ == "__main__":
    """
    Standalone test of the gamepad controller system.
    
    This allows testing the gamepad integration without the full VR tracking hub.
    """
    
    def test_log(message: str, level: str = "INFO"):
        """Simple logging function for testing."""
        print(f"[{level}] {message}")
    
    # Create manager
    manager = GamepadControllerManager(log_callback=test_log)
    
    # Start polling
    manager.start()
    
    # Open configuration GUI
    manager.open_configuration_gui()
    
    # When GUI closes, stop polling
    manager.stop()
    
    print("\nTest complete. Check gamepad_config.json for saved configuration.")