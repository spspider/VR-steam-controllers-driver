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

            # Step C: per-axis rotation inversion (manual fine-tune).
            #
            # If the phone camera is mounted on the opposite side from what
            # auto-cal assumed, certain rotation axes come out with the wrong
            # sign.  Negating quaternion component X reverses rotation around
            # world-X, and likewise for Y and Z.  W (the cosine half-angle)
            # is never touched — that would change the rotation magnitude,
            # not its direction.
            #
            # When all flags are False this is a no-op (default).
            w, x, y, z = world
            if calibration.rotation_invert[0]:
                x = -x
            if calibration.rotation_invert[1]:
                y = -y
            if calibration.rotation_invert[2]:
                z = -z
            world = [w, x, y, z]

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
        self.rot_invert_checks = []   # rotation-axis inversion checkboxes

    def create_dialog(self, parent: tk.Tk):
        device_names = ["LEFT Controller", "RIGHT Controller", "HMD"]

        self.window = tk.Toplevel(parent)
        self.window.title(f"Manual Calibration — {device_names[self.controller_id]}")
        self.window.geometry("620x920")
        self.window.transient(parent)

        main = ttk.Frame(self.window)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ── Auto-Cal read-only info panel ─────────────────────────────────
        # Shows the values that auto-calibration computed (or defaults if
        # auto-cal was never run).  These are the SAME CalibrationData fields
        # that the runtime pipeline uses — displayed here so the user can
        # see what auto-cal produced and understand the context before
        # tweaking offset / scale / invert.
        #
        # The labels are stored in self._autocal_labels and refreshed every
        # 100 ms together with the live-position readout so they stay in sync
        # even if auto-cal is re-run while this dialog is open.
        acal_frame = ttk.LabelFrame(main, text="Auto-Calibration Values (read-only)", padding=10)
        acal_frame.pack(fill=tk.X, pady=5)
        ttk.Label(acal_frame,
                  text="Computed by the Auto-Cal wizard.  Run Auto-Cal again to update these.").pack(anchor=tk.W)

        self._autocal_labels = {}   # key → ttk.Label, refreshed in _refresh_info

        # rotation_offset_quat [W, X, Y, Z]
        row = ttk.Frame(acal_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Rotation quat [W,X,Y,Z]:", width=28, anchor="w").pack(side=tk.LEFT)
        self._autocal_labels['rot_quat'] = ttk.Label(row, text="", font=("Courier", 9))
        self._autocal_labels['rot_quat'].pack(side=tk.LEFT)

        # calibration_reference_position [X, Y, Z]
        row = ttk.Frame(acal_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Reference position [X,Y,Z]:", width=28, anchor="w").pack(side=tk.LEFT)
        self._autocal_labels['ref_pos'] = ttk.Label(row, text="", font=("Courier", 9))
        self._autocal_labels['ref_pos'].pack(side=tk.LEFT)

        # calibration_reference_rotation [W, X, Y, Z]  (Q0 — rest orientation)
        row = ttk.Frame(acal_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Reference rotation [W,X,Y,Z]:", width=28, anchor="w").pack(side=tk.LEFT)
        self._autocal_labels['ref_rot'] = ttk.Label(row, text="", font=("Courier", 9))
        self._autocal_labels['ref_rot'].pack(side=tk.LEFT)

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

        # ── Position Axis Invert ──────────────────────────────────────
        inv_frame = ttk.LabelFrame(main, text="Position Axis Invert", padding=10)
        inv_frame.pack(fill=tk.X, pady=5)
        ttk.Label(inv_frame, text="Flip a position axis if movement direction is wrong after auto-cal").pack(anchor=tk.W)

        inv_row = ttk.Frame(inv_frame)
        inv_row.pack(fill=tk.X, pady=4)
        for i, axis in enumerate("XYZ"):
            var = tk.BooleanVar(value=self.calibration.axis_invert[i])
            ttk.Checkbutton(inv_row, text=f"Invert {axis}", variable=var,
                            command=lambda idx=i, v=var: self._on_invert(idx, v)
                            ).pack(side=tk.LEFT, padx=16)
            self.invert_checks.append(var)

        # ── Rotation Axis Invert ──────────────────────────────────────
        # Separate section so it's visually distinct from position invert.
        # Each checkbox negates the corresponding quaternion component in the
        # final world-frame orientation.  See CalibrationData.rotation_invert
        # and CalibrationManager.apply_calibration() for the full explanation.
        rinv_frame = ttk.LabelFrame(main, text="Rotation Axis Invert", padding=10)
        rinv_frame.pack(fill=tk.X, pady=5)
        ttk.Label(rinv_frame,
                  text="Flip a rotation axis if the VR hand spins the wrong way.\n"
                       "Common fix: if CW marker rotation → CCW hand, enable the relevant axis here.").pack(anchor=tk.W)

        rinv_row = ttk.Frame(rinv_frame)
        rinv_row.pack(fill=tk.X, pady=4)
        for i, axis in enumerate("XYZ"):
            var = tk.BooleanVar(value=self.calibration.rotation_invert[i])
            ttk.Checkbutton(rinv_row, text=f"Invert rot {axis}", variable=var,
                            command=lambda idx=i, v=var: self._on_rot_invert(idx, v)
                            ).pack(side=tk.LEFT, padx=16)
            self.rot_invert_checks.append(var)

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

    def _on_rot_invert(self, i, var):
        # Write the checkbox state into the live CalibrationData so that
        # the next frame processed by apply_calibration() picks it up
        # immediately — no Apply button needed.
        self.calibration.rotation_invert[i] = var.get()
        if self.apply_callback:
            self.apply_callback()

    # ── live info refresh (100 ms) ────────────────────────────────────

    def _refresh_info(self):
        if not self.window or not self.window.winfo_exists():
            return

        # ── Refresh auto-cal read-only values ─────────────────────────
        # These read directly from self.calibration (the live object),
        # so they update automatically if Auto-Cal is re-run while this
        # dialog is open.
        q = self.calibration.rotation_offset_quat
        self._autocal_labels['rot_quat'].config(
            text=f"[{q[0]:+.4f}, {q[1]:+.4f}, {q[2]:+.4f}, {q[3]:+.4f}]")

        p = self.calibration.calibration_reference_position
        self._autocal_labels['ref_pos'].config(
            text=f"[{p[0]:+.4f}, {p[1]:+.4f}, {p[2]:+.4f}]")

        r = self.calibration.calibration_reference_rotation
        self._autocal_labels['ref_rot'].config(
            text=f"[{r[0]:+.4f}, {r[1]:+.4f}, {r[2]:+.4f}, {r[3]:+.4f}]")

        # ── Refresh live position readout ─────────────────────────────
        if self.controller.has_aruco():
            raw = self.controller.aruco_position
            cal = self.controller.position
            self.pos_info.config(
                text=f"Raw:  ({raw[0]:+.3f}, {raw[1]:+.3f}, {raw[2]:+.3f})\n"
                     f"Cal:  ({cal[0]:+.3f}, {cal[1]:+.3f}, {cal[2]:+.3f})",
                foreground="green")
        else:
            self.pos_info.config(text="Marker not visible", foreground="red")
        self.window.after(100, self._refresh_info)

    # ── buttons ───────────────────────────────────────────────────────

    def _reset(self):
        if messagebox.askyesno("Reset", "Reset offset / scale / invert to defaults?"):
            self.calibration.position_offset  = [0.0, 0.0, 0.0]
            self.calibration.position_scale   = [1.0, 1.0, 1.0]
            self.calibration.axis_invert      = [False, False, False]
            self.calibration.rotation_invert  = [False, False, False]
            for i in range(3):
                self.offset_sliders[i][0].set(0.0)
                self.scale_sliders[i][0].set(1.0)
                self.invert_checks[i].set(False)
                self.rot_invert_checks[i].set(False)
            if self.apply_callback:
                self.apply_callback()

    def _apply_close(self):
        if self.apply_callback:
            self.apply_callback()
        self.window.destroy()