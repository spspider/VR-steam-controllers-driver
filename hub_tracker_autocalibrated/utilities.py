#!/usr/bin/env python3
"""
Module utilities.py
Math utilities: quaternions, vectors, rotation matrices.
"""
import math
from typing import List


# ---------------------------------------------------------------------------
# Quaternion operations  [W, X, Y, Z] convention throughout
# ---------------------------------------------------------------------------

def quaternion_multiply(q1: List[float], q2: List[float]) -> List[float]:
    """
    Hamilton product q1 * q2.
    Represents: first apply q2, then apply q1.
    """
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return [
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2
    ]

def quaternion_conjugate(q: List[float]) -> List[float]:
    """Inverse rotation: [W, X, Y, Z] → [W, -X, -Y, -Z]"""
    return [q[0], -q[1], -q[2], -q[3]]

def normalize_quaternion(q: List[float]) -> List[float]:
    """Normalize to unit length. Returns identity if zero-length."""
    mag = math.sqrt(sum(x*x for x in q))
    if mag < 1e-9:
        return [1.0, 0.0, 0.0, 0.0]
    return [x / mag for x in q]

def rotate_vector_by_quaternion(v: List[float], q: List[float]) -> List[float]:
    """
    Rotate vector v by quaternion q.
    Formula: v' = q * [0, v] * conj(q)
    """
    v_quat = [0.0, v[0], v[1], v[2]]
    temp   = quaternion_multiply(q, v_quat)
    result = quaternion_multiply(temp, quaternion_conjugate(q))
    return [result[1], result[2], result[3]]


# ---------------------------------------------------------------------------
# Vector operations
# ---------------------------------------------------------------------------

def vector_subtract(v1: List[float], v2: List[float]) -> List[float]:
    return [v1[0]-v2[0], v1[1]-v2[1], v1[2]-v2[2]]

def vector_add(v1: List[float], v2: List[float]) -> List[float]:
    return [v1[0]+v2[0], v1[1]+v2[1], v1[2]+v2[2]]

def vector_multiply(v: List[float], s) -> List[float]:
    """Component-wise multiply by scalar or per-axis scale vector."""
    if isinstance(s, (int, float)):
        return [v[0]*s, v[1]*s, v[2]*s]
    return [v[0]*s[0], v[1]*s[1], v[2]*s[2]]

def dot_product(a: List[float], b: List[float]) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def cross_product(a: List[float], b: List[float]) -> List[float]:
    return [
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0]
    ]

def vector_length(v: List[float]) -> float:
    return math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2])

def normalize_vector(v: List[float]) -> List[float]:
    """Unit vector. Returns [1,0,0] if zero-length."""
    mag = vector_length(v)
    if mag < 1e-9:
        return [1.0, 0.0, 0.0]
    return [v[0]/mag, v[1]/mag, v[2]/mag]

def calculate_distance(pos1: List[float], pos2: List[float]) -> float:
    return vector_length(vector_subtract(pos2, pos1))

def apply_axis_inversion(v: List[float], invert: List[bool]) -> List[float]:
    return [
        -v[0] if invert[0] else v[0],
        -v[1] if invert[1] else v[1],
        -v[2] if invert[2] else v[2]
    ]


# ---------------------------------------------------------------------------
# Rotation matrix ↔ quaternion
# ---------------------------------------------------------------------------

def rotation_matrix_to_quaternion(R: List[List[float]]) -> List[float]:
    """
    Convert a 3×3 rotation matrix to a unit quaternion [W, X, Y, Z].

    R is row-major: R[row][col].
    Uses Shepperd's method — numerically stable for all rotations.

    Verified: identity matrix → [1,0,0,0],
              90° around Y   → [0.707, 0, 0.707, 0].
    """
    # Shepperd's method picks the largest diagonal element to avoid
    # division by near-zero values.
    trace = R[0][0] + R[1][1] + R[2][2]

    if trace > 0:
        s = 2.0 * math.sqrt(trace + 1.0)
        w = 0.25 * s
        x = (R[2][1] - R[1][2]) / s
        y = (R[0][2] - R[2][0]) / s
        z = (R[1][0] - R[0][1]) / s
    elif R[0][0] > R[1][1] and R[0][0] > R[2][2]:
        s = 2.0 * math.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2])
        w = (R[2][1] - R[1][2]) / s
        x = 0.25 * s
        y = (R[0][1] + R[1][0]) / s
        z = (R[0][2] + R[2][0]) / s
    elif R[1][1] > R[2][2]:
        s = 2.0 * math.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2])
        w = (R[0][2] - R[2][0]) / s
        x = (R[0][1] + R[1][0]) / s
        y = 0.25 * s
        z = (R[1][2] + R[2][1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1])
        w = (R[1][0] - R[0][1]) / s
        x = (R[0][2] + R[2][0]) / s
        y = (R[1][2] + R[2][1]) / s
        z = 0.25 * s

    return normalize_quaternion([w, x, y, z])