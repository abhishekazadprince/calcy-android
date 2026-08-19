"""calcode_camera.py -- exact Python port of calcode_camera.c / calcode_camera.h.

Original: orbit-camera state (azimuth/elevation/distance around a target
point) with no GL/rendering calls of its own -- purely the math consumed
by the (excluded, machine-dependent) GL scene layer when it eventually
applies a look-at transform. Kept fully portable.

PORT NOTES:

- `calcode_camera_orbit` normalizes azimuth into [0, 360) with the same
  while-loop wrap the C uses (not a single modulo), and clamps elevation
  to [-89.5, 89.5] to avoid the poles, exactly as commented in the C.

- `calcode_camera_zoom` is a no-op if `factor <= 0.0` (guard preserved
  literally, including the boundary at exactly 0.0).

- `calcode_camera_eye` returns `None` (mirrors the C's `if (!x||!y||!z)
  return;` guard leaving outputs untouched) when any output pointer is
  unavailable; here that's modeled as returning `None` instead of a
  tuple, since Python has no out-parameters.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple


def _clamp(x: float, lo: float, hi: float) -> float:
    """static double clamp(double x, double lo, double hi);"""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


class CalcodeCamera:
    """typedef struct CalcodeCamera { ... } CalcodeCamera; (see calcode_camera.h)."""
    __slots__ = (
        "azimuth", "elevation", "distance",
        "target_x", "target_y", "target_z",
        "min_distance", "max_distance",
    )

    def __init__(self):
        # Mirrors memset(c, 0, sizeof(*c)); every call site goes through
        # calcode_camera_init before use, same as the C.
        self.azimuth = 0.0
        self.elevation = 0.0
        self.distance = 0.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0
        self.min_distance = 0.0
        self.max_distance = 0.0


def calcode_camera_init(c: Optional[CalcodeCamera]) -> None:
    """void calcode_camera_init(CalcodeCamera *camera);"""
    if c is None:
        return

    c.azimuth = 45.0
    c.elevation = 25.0
    c.distance = 6.0

    c.target_x = 0.0
    c.target_y = 0.0
    c.target_z = 0.0

    c.min_distance = 0.05
    c.max_distance = 100000.0


def calcode_camera_orbit(c: Optional[CalcodeCamera], da: float, de: float) -> None:
    """void calcode_camera_orbit(CalcodeCamera *camera, double delta_azimuth, double delta_elevation);"""
    if c is None:
        return

    c.azimuth += da
    c.elevation += de

    while c.azimuth >= 360.0:
        c.azimuth -= 360.0

    while c.azimuth < 0.0:
        c.azimuth += 360.0

    # Avoid the exact poles. This keeps the camera's local "up" direction
    # well-defined for the future OpenGL look-at transform.
    c.elevation = _clamp(c.elevation, -89.5, 89.5)


def calcode_camera_zoom(c: Optional[CalcodeCamera], factor: float) -> None:
    """void calcode_camera_zoom(CalcodeCamera *camera, double factor);"""
    if c is None or factor <= 0.0:
        return

    c.distance *= factor
    c.distance = _clamp(c.distance, c.min_distance, c.max_distance)


def calcode_camera_set_target(c: Optional[CalcodeCamera], x: float, y: float, z: float) -> None:
    """void calcode_camera_set_target(CalcodeCamera *camera, double x, double y, double z);"""
    if c is None:
        return

    c.target_x = x
    c.target_y = y
    c.target_z = z


def calcode_camera_eye(c: Optional[CalcodeCamera]) -> Optional[Tuple[float, float, float]]:
    """void calcode_camera_eye(const CalcodeCamera *camera, double *x, double *y, double *z);

    Returns None where the C would leave the (unavailable) output
    pointers untouched; otherwise returns (x, y, z).
    """
    if c is None:
        return None

    pi = 3.14159265358979323846
    a = c.azimuth * pi / 180.0
    e = c.elevation * pi / 180.0

    ce = math.cos(e)

    x = c.target_x + c.distance * ce * math.cos(a)
    y = c.target_y + c.distance * ce * math.sin(a)
    z = c.target_z + c.distance * math.sin(e)

    return (x, y, z)
