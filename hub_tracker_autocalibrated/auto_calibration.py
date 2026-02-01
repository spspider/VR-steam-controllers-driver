#!/usr/bin/env python3
"""
Module auto_calibration.py
Automatic calibration via coordinate-frame measurement.

─── WHY THIS EXISTS ───────────────────────────────────────────────────────
The phone camera is never perfectly perpendicular to the markers.
It looks at them at some arbitrary angle.  ArUco therefore reports
positions and orientations in a skewed frame:  "marker +X" is not
"world right", "marker +Y" is not "world up", etc.

If we just pass those raw values straight to SteamVR the virtual hand
drifts sideways when you move up, spins on multiple axes when you
only rotate in one plane, etc.

─── WHAT WE DO ─────────────────────────────────────────────────────────────
We ask the user to move in two known, real-world directions
(RIGHT and UP) and record where the marker ends up each time.
From those two displacement vectors we reconstruct the full
orthonormal frame that the marker is actually living in, build
the rotation matrix that corrects it, and store the resulting
quaternion as  rotation_offset_quat.

At runtime  apply_calibration()  rotates every position delta AND
every orientation quaternion by  rotation_offset_quat  before
sending to SteamVR.

─── WIZARD STEPS ───────────────────────────────────────────────────────────
  Step 1 — ORIGIN
      Hold controller in front of you, marker visible.  Press Next.
      →  P0 is recorded.

  Step 2 — MOVE RIGHT  (30 cm)
      Slide the controller to the right, keeping the same height.
      A live distance readout shows how far you've moved.
      Press Next when close to 30 cm.
      →  P1 is recorded.  right_axis = normalise(P1 − P0).

  Step 3 — MOVE UP  (30 cm from P1)
      From wherever you are now, move the controller straight up.
      Press Next when close to 30 cm.
      →  P2 is recorded.
      →  raw_up = P2 − P1
      →  Gram-Schmidt: up_axis = raw_up − (raw_up · right_axis) * right_axis, then normalise.
         (This removes any accidental sideways drift, so the frame stays orthogonal.)
      →  forward_axis = cross(right_axis, up_axis)

  Step 4 — COMPUTE & SAVE
      Rotation matrix R (rows = right, up, forward axes).
      R is converted to a quaternion and saved as rotation_offset_quat.
      axis_invert is cleared (rotation handles everything).
      position_scale is set to [1, 1, 1].
      reference_position is set to P0.
      position_offset stays at whatever the user had (or [0, 1, 0] default).
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, List

from data_structures import ControllerData, CalibrationData
from utilities import (
    vector_subtract, normalize_vector, cross_product,
    dot_product, vector_length, vector_multiply, vector_add,
    rotation_matrix_to_quaternion, calculate_distance
)


# Target movement distance in metres (user should move roughly this far)
TARGET_DISTANCE = 0.30          # 30 cm
DISTANCE_TOLERANCE_LO = 0.20   # warn if less than 20 cm
DISTANCE_TOLERANCE_HI = 0.45   # warn if more than 45 cm


class AutoCalibrationWizard:

    # ── wizard page IDs ────────────────────────────────────────────────
    PAGE_ORIGIN   = 0   # place controller, record P0
    PAGE_RIGHT    = 1   # move right, record P1
    PAGE_UP       = 2   # move up, record P2
    PAGE_RESULTS  = 3   # show computed values, close

    def __init__(self,
                 controller_id: int,
                 controller_data: ControllerData,
                 calibration_data: CalibrationData,
                 log_callback: Optional[Callable] = None):
        self.controller_id    = controller_id
        self.controller_data  = controller_data
        self.calibration_data = calibration_data
        self.log              = log_callback or (lambda *a, **kw: None)

        # Recorded positions (filled as wizard progresses)
        self.P0: Optional[List[float]] = None   # origin position
        self.Q0: Optional[List[float]] = None   # origin quaternion  ← the marker's "rest" orientation.
                                                 #   ArUco reports a non-identity quaternion even when
                                                 #   the marker is lying flat and still, because the
                                                 #   marker's own axes are not aligned with the camera.
                                                 #   We record it here so that at runtime we can compute
                                                 #   *relative* rotation (how much the marker has turned
                                                 #   since this moment) and then re-express that relative
                                                 #   rotation in world-frame axes via conjugation.
        self.P1: Optional[List[float]] = None   # after moving right
        self.P2: Optional[List[float]] = None   # after moving up

        # Current page
        self.page = self.PAGE_ORIGIN

        # GUI refs
        self.window:       Optional[tk.Toplevel] = None
        self.instr_label:  Optional[tk.Label]    = None
        self.pos_label:    Optional[tk.Label]    = None
        self.dist_label:   Optional[tk.Label]    = None   # live distance indicator
        self.next_btn:     Optional[ttk.Button]  = None

    # ── helpers ────────────────────────────────────────────────────────

    def _device_name(self) -> str:
        return ["LEFT", "RIGHT", "HMD"][self.controller_id]

    def _marker_ok(self) -> bool:
        return self.controller_data.has_aruco(timeout=1.0)

    def _current_pos(self) -> Optional[List[float]]:
        if self._marker_ok():
            return list(self.controller_data.aruco_position)
        return None

    # ── reference position for live distance display ──────────────────
    # During PAGE_RIGHT  we measure distance from P0.
    # During PAGE_UP     we measure distance from P1.
    def _distance_reference(self) -> Optional[List[float]]:
        if self.page == self.PAGE_RIGHT:
            return self.P0
        if self.page == self.PAGE_UP:
            return self.P1
        return None

    # ── GUI creation ───────────────────────────────────────────────────

    def start_wizard(self, parent: tk.Tk):
        self.window = tk.Toplevel(parent)
        self.window.title(f"Auto Calibration — {self._device_name()}")
        self.window.geometry("580x440")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        # Title
        ttk.Label(self.window,
                  text=f"Calibration Wizard — {self._device_name()}",
                  font=("", 14, "bold")).pack(pady=(12, 4))

        # Instruction text (large, wrapping)
        instr_frame = ttk.LabelFrame(self.window, text="Instructions", padding=12)
        instr_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self.instr_label = tk.Label(instr_frame, text="",
                                    font=("", 10), justify=tk.LEFT, wraplength=530,
                                    anchor="nw")
        self.instr_label.pack(fill=tk.BOTH, expand=True)

        # Live position + distance bar
        info_frame = ttk.LabelFrame(self.window, text="Live", padding=8)
        info_frame.pack(fill=tk.X, padx=10, pady=4)

        self.pos_label  = tk.Label(info_frame, text="Waiting for marker…",
                                   font=("Courier", 10))
        self.pos_label.pack(anchor=tk.W)

        self.dist_label = tk.Label(info_frame, text="",
                                   font=("Courier", 10, "bold"))
        self.dist_label.pack(anchor=tk.W)

        # Buttons
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=tk.X, padx=10, pady=(4, 10))

        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.LEFT)
        self.next_btn = ttk.Button(btn_frame, text="Next →", command=self._next)
        self.next_btn.pack(side=tk.RIGHT)

        # Show first page and start the update loop
        self._show_page()
        self._tick()

        self.log(f"Auto-calibration wizard started for {self._device_name()}")

    # ── page content ───────────────────────────────────────────────────

    def _show_page(self):
        texts = {
            self.PAGE_ORIGIN: (
                "STEP 1 — ORIGIN POSITION\n\n"
                "Hold the controller in front of you at a comfortable distance.\n"
                "Make sure the marker is visible (green position below).\n\n"
                "Keep it steady, then press Next."
            ),
            self.PAGE_RIGHT: (
                f"STEP 2 — MOVE RIGHT  (~{TARGET_DISTANCE*100:.0f} cm)\n\n"
                "Slide the controller to the RIGHT, keeping the same height\n"
                "and depth.  Watch the distance readout — it should reach\n"
                f"~{TARGET_DISTANCE*100:.0f} cm before you press Next.\n\n"
                "A ruler or measuring tape helps, but not required."
            ),
            self.PAGE_UP: (
                f"STEP 3 — MOVE UP  (~{TARGET_DISTANCE*100:.0f} cm)\n\n"
                "From where you are now, move the controller straight UP.\n"
                "Try not to move sideways — the math will correct small\n"
                "drift automatically (Gram-Schmidt).\n\n"
                "Watch the distance readout, then press Next."
            ),
            self.PAGE_RESULTS: ""   # filled dynamically after compute
        }
        if self.page in texts:
            self.instr_label.config(text=texts[self.page])

        # Button label
        if self.page == self.PAGE_RESULTS:
            self.next_btn.config(text="Close ✓")
        else:
            self.next_btn.config(text="Next →")

    # ── periodic UI refresh (100 ms) ───────────────────────────────────

    def _tick(self):
        if not self.window or not self.window.winfo_exists():
            return

        pos = self._current_pos()

        # Position readout
        if pos:
            self.pos_label.config(
                text=f"Pos:  X {pos[0]:+.4f}   Y {pos[1]:+.4f}   Z {pos[2]:+.4f}",
                foreground="green")
        else:
            self.pos_label.config(text="⚠  Marker not visible!", foreground="red")

        # Distance readout (only on movement pages)
        ref = self._distance_reference()
        if pos and ref:
            dist = calculate_distance(ref, pos)
            color = "green" if DISTANCE_TOLERANCE_LO <= dist <= DISTANCE_TOLERANCE_HI else "orange"
            self.dist_label.config(
                text=f"Dist: {dist*100:+6.1f} cm   (target ~{TARGET_DISTANCE*100:.0f} cm)",
                foreground=color)
        else:
            self.dist_label.config(text="")

        self.window.after(100, self._tick)

    # ── navigation ─────────────────────────────────────────────────────

    def _next(self):
        if self.page == self.PAGE_ORIGIN:
            self._record_origin()
        elif self.page == self.PAGE_RIGHT:
            self._record_right()
        elif self.page == self.PAGE_UP:
            self._record_up_and_compute()
        elif self.page == self.PAGE_RESULTS:
            self.window.destroy()
            return

    # ── step implementations ───────────────────────────────────────────

    def _record_origin(self):
        """PAGE_ORIGIN → PAGE_RIGHT"""
        pos = self._current_pos()
        if not pos:
            messagebox.showerror("Error", "Marker not visible.  Make sure the camera sees it.")
            return

        # Also check that we have a valid quaternion
        if not self.controller_data.aruco_quaternion:
            messagebox.showerror("Error", "No orientation data yet.  Wait a moment and try again.")
            return

        self.P0 = pos
        # Record the marker's orientation right now.  This is the "zero rotation" reference.
        # At runtime:  relative = current_aruco_quat * conj(Q0)
        # tells us how much the marker has rotated since this moment.
        self.Q0 = list(self.controller_data.aruco_quaternion)

        self.log(f"  P0 (origin) = ({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})")
        self.log(f"  Q0 (rest)   = [{self.Q0[0]:.4f}, {self.Q0[1]:.4f}, {self.Q0[2]:.4f}, {self.Q0[3]:.4f}]")

        self.page = self.PAGE_RIGHT
        self._show_page()

    def _record_right(self):
        """PAGE_RIGHT → PAGE_UP"""
        pos = self._current_pos()
        if not pos:
            messagebox.showerror("Error", "Marker not visible.")
            return

        dist = calculate_distance(self.P0, pos)
        if dist < DISTANCE_TOLERANCE_LO:
            messagebox.showwarning("Too close",
                f"You've only moved {dist*100:.1f} cm.  "
                f"Move at least {DISTANCE_TOLERANCE_LO*100:.0f} cm to the right.")
            return

        self.P1 = pos
        self.log(f"  P1 (right)  = ({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})  "
                 f"dist = {dist*100:.1f} cm")

        self.page = self.PAGE_UP
        self._show_page()

    def _record_up_and_compute(self):
        """PAGE_UP → compute rotation → PAGE_RESULTS"""
        pos = self._current_pos()
        if not pos:
            messagebox.showerror("Error", "Marker not visible.")
            return

        dist = calculate_distance(self.P1, pos)
        if dist < DISTANCE_TOLERANCE_LO:
            messagebox.showwarning("Too close",
                f"You've only moved {dist*100:.1f} cm up.  "
                f"Move at least {DISTANCE_TOLERANCE_LO*100:.0f} cm.")
            return

        self.P2 = pos
        self.log(f"  P2 (up)     = ({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})  "
                 f"dist = {dist*100:.1f} cm")

        # ── build the orthonormal frame ────────────────────────────────
        #
        # right_axis   = direction the marker moved when we went RIGHT
        # raw_up       = direction the marker moved when we went UP
        # up_axis      = raw_up with the right-component removed (Gram-Schmidt)
        #                so the two axes are perfectly orthogonal even if the
        #                user drifted sideways a bit.
        # forward_axis = cross(right, up)  — completes a right-handed frame
        #
        right_raw  = vector_subtract(self.P1, self.P0)
        right_axis = normalize_vector(right_raw)

        raw_up     = vector_subtract(self.P2, self.P1)

        # Gram-Schmidt: remove the component of raw_up that is parallel to right_axis
        proj_onto_right = dot_product(raw_up, right_axis)
        up_orthogonal   = vector_subtract(raw_up,
                                          vector_multiply(right_axis, proj_onto_right))
        up_axis = normalize_vector(up_orthogonal)

        forward_axis = cross_product(right_axis, up_axis)
        # forward_axis is already unit length because right and up are orthonormal

        # ── build rotation matrix ──────────────────────────────────────
        #
        # R transforms a vector from marker-space into VR-world-space.
        # Row 0 (right_axis) projects onto world +X
        # Row 1 (up_axis)    projects onto world +Y
        # Row 2 (forward_axis) projects onto world +Z
        #
        # For any marker-space vector v:
        #   world = R * v  ≡  [dot(v, right), dot(v, up), dot(v, forward)]
        #
        R = [
            list(right_axis),
            list(up_axis),
            list(forward_axis)
        ]

        # Convert to quaternion — this is what we store and use at runtime
        rot_quat = rotation_matrix_to_quaternion(R)

        # ── store calibration results ──────────────────────────────────
        self.calibration_data.rotation_offset_quat           = rot_quat
        self.calibration_data.calibration_reference_position = list(self.P0)
        self.calibration_data.axis_invert                    = [False, False, False]
        self.calibration_data.position_scale                 = [1.0, 1.0, 1.0]

        # Save the marker's rest quaternion recorded at P0.
        #
        # WHY THIS IS NEEDED (and why tilts / extra rotation steps are NOT):
        #
        # The RIGHT + UP movements give us a full orthonormal basis for position.
        # That same basis (rot_quat) can re-express any vector from camera-space
        # to world-space.  For position that's all we need.
        #
        # For orientation it's different.  A rotation lives in a *different* space
        # than a vector — you can't just multiply rot_quat * aruco_quat and get
        # a world-frame rotation.  What you CAN do is:
        #
        #   1.  Compute the RELATIVE rotation since the marker was at rest:
        #           relative = aruco_quat * conj(Q0)
        #       This gives "how much has the marker turned since calibration",
        #       expressed in camera-frame axes.
        #
        #   2.  Re-express that relative rotation in world-frame axes via
        #       conjugation (similarity transform):
        #           world = rot_quat * relative * conj(rot_quat)
        #       Conjugation changes the axes a rotation is expressed around
        #       without changing the rotation itself.
        #
        # When the marker hasn't moved:  relative = identity → world = identity.  ✓
        # When it spins CW on the table: relative = rotation around camera-Z
        #   → world = rotation around world-forward.  ✓
        # When rot_quat = identity AND Q0 = identity (no cal done at all):
        #   relative = aruco_quat, world = aruco_quat  → same as original pass-through.  ✓
        #
        # Tilting the marker left/right/forward/back would NOT add any information:
        # the three world axes are already fully determined by right_axis, up_axis,
        # and forward_axis = cross(right, up).  The only missing piece was Q0.
        self.calibration_data.calibration_reference_rotation = list(self.Q0)

        # Keep existing offset, or default to head-height if it's all zeros
        if self.calibration_data.position_offset == [0.0, 0.0, 0.0]:
            self.calibration_data.position_offset = [0.0, 1.0, 0.0]

        self.log(f"  Rotation quaternion [W,X,Y,Z] = "
                 f"[{rot_quat[0]:.4f}, {rot_quat[1]:.4f}, {rot_quat[2]:.4f}, {rot_quat[3]:.4f}]")
        self.log(f"  right_axis  = ({right_axis[0]:+.3f}, {right_axis[1]:+.3f}, {right_axis[2]:+.3f})")
        self.log(f"  up_axis     = ({up_axis[0]:+.3f}, {up_axis[1]:+.3f}, {up_axis[2]:+.3f})")
        self.log(f"  forward_axis= ({forward_axis[0]:+.3f}, {forward_axis[1]:+.3f}, {forward_axis[2]:+.3f})")
        self.log("  ✓ Calibration saved.")

        # ── show results page ──────────────────────────────────────────
        self.page = self.PAGE_RESULTS
        self.instr_label.config(text=(
            "✓  CALIBRATION COMPLETE\n\n"
            f"Rotation quaternion stored: [{rot_quat[0]:.4f}, {rot_quat[1]:.4f}, "
            f"{rot_quat[2]:.4f}, {rot_quat[3]:.4f}]\n\n"
            f"right  = ({right_axis[0]:+.3f}, {right_axis[1]:+.3f}, {right_axis[2]:+.3f})\n"
            f"up     = ({up_axis[0]:+.3f}, {up_axis[1]:+.3f}, {up_axis[2]:+.3f})\n"
            f"forward= ({forward_axis[0]:+.3f}, {forward_axis[1]:+.3f}, {forward_axis[2]:+.3f})\n\n"
            "The rotation is now applied to both position and orientation.\n"
            "Use ⚙️ Manual for fine-tuning offset / scale if needed."
        ))
        self._show_page()

    # ── cancel ─────────────────────────────────────────────────────────

    def _cancel(self):
        if messagebox.askyesno("Cancel calibration",
                               "Discard calibration and close?"):
            self.log("  Calibration cancelled.")
            self.window.destroy()