#!/usr/bin/env python3
"""
Module calibration.py
Runtime calibration application + manual fine-tune dialog.
"""
from typing import Optional, Callable
import tkinter as tk
from tkinter import ttk, messagebox

from data_structures import ControllerData, CalibrationData
from utilities import (
    quaternion_multiply, quaternion_conjugate, normalize_quaternion,
    rotate_vector_by_quaternion,
    vector_subtract, vector_add, vector_multiply,
    apply_axis_inversion
)


class CalibrationManager:
    """
    Applies the full calibration pipeline to each incoming data frame.
    """

    @staticmethod
    def apply_calibration(controller: ControllerData,
                          calibration: CalibrationData) -> ControllerData:
        """
        Transform raw ArUco data into VR-world coordinates.

        Pipeline (position):
          1.  relative  = raw_pos − reference_pos       (move origin to calibration point)
          2.  rotated   = rotate(relative, rot_quat)    (align marker frame → world frame)
          3.  inverted  = apply per-axis inversion       (fine-tune sign if needed)
          4.  scaled    = inverted × per-axis scale      (fine-tune magnification)
          5.  final     = scaled + offset                (shift into desired VR location)

        Pipeline (orientation):
          relative = aruco_quat × conj(rest_quat)                    (rotation since calibration, camera axes)
          world    = rot_quat × relative × conj(rot_quat)           (same rotation, world axes)

        When rot_quat and rest_quat are both identity (no auto-cal done)
        the orientation reduces to  world = aruco_quat  — same as original.
        """
        if not controller.has_aruco():
            return controller

        # ── 1. Relative position (subtract calibration origin) ──────────
        relative = vector_subtract(controller.aruco_position,
                                   calibration.calibration_reference_position)

        # ── 2. Rotate from marker-space into VR-world-space ─────────────
        # rotation_offset_quat was computed by auto_calibration from the
        # orthonormal frame the user established during the wizard.
        # When it is identity this is a no-op.
        rotated = rotate_vector_by_quaternion(relative,
                                              calibration.rotation_offset_quat)

        # ── 3. Per-axis inversion (manual fine-tune knob) ───────────────
        inverted = apply_axis_inversion(rotated, calibration.axis_invert)

        # ── 4. Per-axis scale (manual fine-tune knob) ───────────────────
        scaled = vector_multiply(inverted, calibration.position_scale)

        # ── 5. Offset (final VR-space position) ─────────────────────────
        controller.position = vector_add(scaled, calibration.position_offset)

        # ── Orientation ─────────────────────────────────────────────────
        #
        # We cannot just do  rot_quat * aruco_quat.  That would mix two
        # different frames and produce garbage when the marker rotates.
        #
        # Correct approach — two-step conjugation:
        #
        #   Step A — RELATIVE rotation (how much has the marker turned
        #            since the calibration moment, in camera-frame axes):
        #               relative = aruco_quat * conj(rest_quat)
        #            When the marker hasn't moved this is identity.
        #
        #   Step B — re-express that relative rotation in world-frame axes
        #            using a similarity transform (conjugation):
        #               world = rot_quat * relative * conj(rot_quat)
        #            This changes which axes the rotation is "around"
        #            without changing the rotation amount.
        #            e.g. if relative is "45° around camera-Z" and
        #            camera-Z maps to world [0, 0.5, 0.866], then world
        #            is "45° around [0, 0.5, 0.866]".
        #
        # Backward compatibility:
        #   If no auto-cal has been run, both rot_quat and rest_quat are
        #   identity [1,0,0,0].  Then relative = aruco_quat and
        #   world = aruco_quat — identical to the original pass-through.
        #
        if controller.aruco_quaternion:
            rest_quat = calibration.calibration_reference_rotation
            rot_quat  = calibration.rotation_offset_quat

            # Step A: relative rotation since rest (in camera frame)
            relative = quaternion_multiply(controller.aruco_quaternion,
                                           quaternion_conjugate(rest_quat))

            # Step B: conjugation — rotate the axis into world frame
            world = quaternion_multiply(
                quaternion_multiply(rot_quat, relative),
                quaternion_conjugate(rot_quat)
            )

            controller.quaternion = normalize_quaternion(world)

        return controller


# ---------------------------------------------------------------------------
# Manual fine-tune dialog  (offset / scale / invert sliders)
# ---------------------------------------------------------------------------

class CalibrationDialog:
    """
    GUI dialog for manual fine-tuning after auto-calibration.
    Changes are applied in real-time so you see the effect immediately.
    """

    def __init__(self, controller_id: int, calibration: CalibrationData,
                 controller: ControllerData,
                 apply_callback: Optional[Callable] = None):
        self.controller_id    = controller_id
        self.calibration      = calibration
        self.controller       = controller
        self.apply_callback   = apply_callback
        self.window: Optional[tk.Toplevel] = None

        self.offset_sliders = []
        self.scale_sliders  = []
        self.invert_checks  = []

    def create_dialog(self, parent: tk.Tk):
        device_names = ["LEFT Controller", "RIGHT Controller", "HMD"]

        self.window = tk.Toplevel(parent)
        self.window.title(f"Manual Calibration — {device_names[self.controller_id]}")
        self.window.geometry("600x720")
        self.window.transient(parent)

        main = ttk.Frame(self.window)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ── Offset ────────────────────────────────────────────────────
        off_frame = ttk.LabelFrame(main, text="Position Offset", padding=10)
        off_frame.pack(fill=tk.X, pady=5)
        ttk.Label(off_frame, text="Shifts the controller in VR space (metres)").pack(anchor=tk.W)

        for i, axis in enumerate("XYZ"):
            row = ttk.Frame(off_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{axis}:", width=3).pack(side=tk.LEFT)

            sl = tk.Scale(row, from_=-2.0, to=2.0, resolution=0.01,
                          orient=tk.HORIZONTAL, length=300,
                          command=lambda v, idx=i: self._on_offset(idx, float(v)))
            sl.set(self.calibration.position_offset[i])
            sl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            lbl = ttk.Label(row, text=f"{self.calibration.position_offset[i]:+.2f} m", width=8)
            lbl.pack(side=tk.LEFT)
            self.offset_sliders.append((sl, lbl))

        # ── Scale ─────────────────────────────────────────────────────
        sc_frame = ttk.LabelFrame(main, text="Position Scale", padding=10)
        sc_frame.pack(fill=tk.X, pady=5)
        ttk.Label(sc_frame, text="Stretches / compresses movement per axis").pack(anchor=tk.W)

        for i, axis in enumerate("XYZ"):
            row = ttk.Frame(sc_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{axis}:", width=3).pack(side=tk.LEFT)

            sl = tk.Scale(row, from_=0.1, to=3.0, resolution=0.01,
                          orient=tk.HORIZONTAL, length=300,
                          command=lambda v, idx=i: self._on_scale(idx, float(v)))
            sl.set(self.calibration.position_scale[i])
            sl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            lbl = ttk.Label(row, text=f"{self.calibration.position_scale[i]:.2f}×", width=8)
            lbl.pack(side=tk.LEFT)
            self.scale_sliders.append((sl, lbl))

        # ── Invert ────────────────────────────────────────────────────
        inv_frame = ttk.LabelFrame(main, text="Axis Invert (fine-tune)", padding=10)
        inv_frame.pack(fill=tk.X, pady=5)
        ttk.Label(inv_frame, text="Flip an axis if movement direction is wrong after auto-cal").pack(anchor=tk.W)

        inv_row = ttk.Frame(inv_frame)
        inv_row.pack(fill=tk.X, pady=4)
        for i, axis in enumerate("XYZ"):
            var = tk.BooleanVar(value=self.calibration.axis_invert[i])
            ttk.Checkbutton(inv_row, text=f"Invert {axis}", variable=var,
                            command=lambda idx=i, v=var: self._on_invert(idx, v)
                            ).pack(side=tk.LEFT, padx=16)
            self.invert_checks.append(var)

        # ── Live position info ────────────────────────────────────────
        info_frame = ttk.LabelFrame(main, text="Live Position", padding=10)
        info_frame.pack(fill=tk.X, pady=5)
        self.pos_info = ttk.Label(info_frame, text="", font=("Courier", 9))
        self.pos_info.pack()

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = ttk.Frame(main)
        btn_row.pack(fill=tk.X, pady=8)
        ttk.Button(btn_row, text="✓ Apply & Close", command=self._apply_close).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="↺ Reset Defaults", command=self._reset).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="✕ Cancel", command=self.window.destroy).pack(side=tk.RIGHT, padx=4)

        self._refresh_info()

    # ── slider callbacks ──────────────────────────────────────────────

    def _on_offset(self, i, val):
        self.calibration.position_offset[i] = val
        self.offset_sliders[i][1].config(text=f"{val:+.2f} m")
        if self.apply_callback:
            self.apply_callback()

    def _on_scale(self, i, val):
        self.calibration.position_scale[i] = val
        self.scale_sliders[i][1].config(text=f"{val:.2f}×")
        if self.apply_callback:
            self.apply_callback()

    def _on_invert(self, i, var):
        self.calibration.axis_invert[i] = var.get()
        if self.apply_callback:
            self.apply_callback()

    # ── live info refresh (100 ms) ────────────────────────────────────

    def _refresh_info(self):
        if not self.window or not self.window.winfo_exists():
            return
        if self.controller.has_aruco():
            r = self.controller.aruco_position
            c = self.controller.position
            self.pos_info.config(
                text=f"Raw:  ({r[0]:+.3f}, {r[1]:+.3f}, {r[2]:+.3f})\n"
                     f"Cal:  ({c[0]:+.3f}, {c[1]:+.3f}, {c[2]:+.3f})",
                foreground="green")
        else:
            self.pos_info.config(text="Marker not visible", foreground="red")
        self.window.after(100, self._refresh_info)

    # ── buttons ───────────────────────────────────────────────────────

    def _reset(self):
        if messagebox.askyesno("Reset", "Reset offset / scale / invert to defaults?"):
            self.calibration.position_offset = [0.0, 0.0, 0.0]
            self.calibration.position_scale  = [1.0, 1.0, 1.0]
            self.calibration.axis_invert     = [False, False, False]
            for i in range(3):
                self.offset_sliders[i][0].set(0.0)
                self.scale_sliders[i][0].set(1.0)
                self.invert_checks[i].set(False)
            if self.apply_callback:
                self.apply_callback()

    def _apply_close(self):
        if self.apply_callback:
            self.apply_callback()
        self.window.destroy()