"""calcode_coordinate_transform_v1.py -- exact Python port of
calcode_coordinate_transform_v1.c / calcode_coordinate_transform_v1.h.

Original: linear min/max -> min/max remap (source projection bounds
into a fixed [-1, 1] target viewport per axis) built from a completed
`CalcodeCoordinateProjectionV1`'s `x_min/x_max/y_min/y_max/z_min/z_max`
(i.e. meant to be called after `calcode_projection_bounds_v1`).

PORT NOTES:

- `map_v1`'s degenerate-width guard (`fabs(source_max - source_min)
  <= 1e-30` -> the midpoint of the *target* range, not the source)
  is reproduced exactly, including the threshold constant and using
  `abs` (Python's `abs` on a float is `fabs`).
- `calcode_coordinate_transform_from_projection_v1` requires `p.valid`
  in addition to both args being non-None (the C's `!t || !p ||
  !p->valid`) -- an *unbuilt* projection (never had one of the
  `calcode_projection_*_v1` constructors called, so `valid=0`) is
  rejected even if its bounds fields happen to be numerically present
  from a stale/reused struct. On success it copies the six source
  bounds from `p` verbatim and hardcodes the target viewport to
  `[-1, 1]` on every axis (per the C's own comment: a fixed
  "default mathematical viewport" the renderer can remap further
  without touching the projection) -- reproduced with the same
  literal `-1.0`/`1.0` values, not derived from anything.
- `x_v1`/`y_v1`/`z_v1` each return the input `value` unchanged (not
  0.0, not an error sentinel) when `t` is None or `not t.valid` --
  reproduced exactly; this is the C's actual fallback-to-identity
  behavior for an unconfigured transform, not a bug to "fix".
- `point_v1` requires `t`/`source`/`target` all non-None and
  `t.valid`, then writes all three of `target.x/y/z` via the three
  single-axis functions above (so on `t.valid == 0` it returns 0
  *without* touching `target` at all, rather than falling through to
  the identity behavior the single-axis functions have on their own
  -- the guard is stricter here than in the single-axis calls, and
  that asymmetry is real C behavior, reproduced as-is).
"""

from __future__ import annotations

from typing import Optional

from calcy.trajectory.coordinate_projection_v1 import (
    CalcodeCoordinateProjectionV1,
    CalcodeProjectedPointV1,
)


class CalcodeCoordinateTransformV1:
    """typedef struct CalcodeCoordinateTransformV1 { ... } CalcodeCoordinateTransformV1."""
    __slots__ = (
        "valid",
        "source_x_min", "source_x_max",
        "source_y_min", "source_y_max",
        "source_z_min", "source_z_max",
        "target_x_min", "target_x_max",
        "target_y_min", "target_y_max",
        "target_z_min", "target_z_max",
        "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.source_x_min = 0.0
        self.source_x_max = 0.0
        self.source_y_min = 0.0
        self.source_y_max = 0.0
        self.source_z_min = 0.0
        self.source_z_max = 0.0
        self.target_x_min = 0.0
        self.target_x_max = 0.0
        self.target_y_min = 0.0
        self.target_y_max = 0.0
        self.target_z_min = 0.0
        self.target_z_max = 0.0
        self.diagnostic = ""


def _map(value: float, source_min: float, source_max: float, target_min: float, target_max: float) -> float:
    """static double map_v1(double value, double source_min, double source_max,
    double target_min, double target_max);"""
    width = source_max - source_min

    if abs(width) <= 1e-30:
        return 0.5 * (target_min + target_max)

    u = (value - source_min) / width

    return target_min + u * (target_max - target_min)


def calcode_coordinate_transform_init_v1(t: Optional[CalcodeCoordinateTransformV1]) -> None:
    """void calcode_coordinate_transform_init_v1(CalcodeCoordinateTransformV1 *transform);"""
    if t is None:
        return

    t.valid = 0
    t.source_x_min = 0.0
    t.source_x_max = 0.0
    t.source_y_min = 0.0
    t.source_y_max = 0.0
    t.source_z_min = 0.0
    t.source_z_max = 0.0
    t.target_x_min = 0.0
    t.target_x_max = 0.0
    t.target_y_min = 0.0
    t.target_y_max = 0.0
    t.target_z_min = 0.0
    t.target_z_max = 0.0
    t.diagnostic = ""


def calcode_coordinate_transform_from_projection_v1(
    t: Optional[CalcodeCoordinateTransformV1], p: Optional[CalcodeCoordinateProjectionV1]
) -> int:
    """int calcode_coordinate_transform_from_projection_v1(
    CalcodeCoordinateTransformV1 *transform, const CalcodeCoordinateProjectionV1 *projection);"""
    if t is None or p is None or not p.valid:
        return 0

    calcode_coordinate_transform_init_v1(t)

    t.source_x_min = p.x_min
    t.source_x_max = p.x_max

    t.source_y_min = p.y_min
    t.source_y_max = p.y_max

    t.source_z_min = p.z_min
    t.source_z_max = p.z_max

    # Default mathematical viewport.
    #
    # The rendering system can later choose pixel, world, camera or
    # normalized device coordinates without changing the projection itself.
    t.target_x_min = -1.0
    t.target_x_max = 1.0

    t.target_y_min = -1.0
    t.target_y_max = 1.0

    t.target_z_min = -1.0
    t.target_z_max = 1.0

    t.valid = 1

    return 1


def calcode_coordinate_transform_x_v1(t: Optional[CalcodeCoordinateTransformV1], value: float) -> float:
    """double calcode_coordinate_transform_x_v1(const CalcodeCoordinateTransformV1 *transform,
    double value);"""
    if t is None or not t.valid:
        return value

    return _map(value, t.source_x_min, t.source_x_max, t.target_x_min, t.target_x_max)


def calcode_coordinate_transform_y_v1(t: Optional[CalcodeCoordinateTransformV1], value: float) -> float:
    """double calcode_coordinate_transform_y_v1(const CalcodeCoordinateTransformV1 *transform,
    double value);"""
    if t is None or not t.valid:
        return value

    return _map(value, t.source_y_min, t.source_y_max, t.target_y_min, t.target_y_max)


def calcode_coordinate_transform_z_v1(t: Optional[CalcodeCoordinateTransformV1], value: float) -> float:
    """double calcode_coordinate_transform_z_v1(const CalcodeCoordinateTransformV1 *transform,
    double value);"""
    if t is None or not t.valid:
        return value

    return _map(value, t.source_z_min, t.source_z_max, t.target_z_min, t.target_z_max)


def calcode_coordinate_transform_point_v1(
    t: Optional[CalcodeCoordinateTransformV1],
    source: Optional[CalcodeProjectedPointV1],
    target: Optional[CalcodeProjectedPointV1],
) -> int:
    """int calcode_coordinate_transform_point_v1(const CalcodeCoordinateTransformV1 *transform,
    const CalcodeProjectedPointV1 *source, CalcodeProjectedPointV1 *target);"""
    if t is None or source is None or target is None or not t.valid:
        return 0

    target.x = calcode_coordinate_transform_x_v1(t, source.x)
    target.y = calcode_coordinate_transform_y_v1(t, source.y)
    target.z = calcode_coordinate_transform_z_v1(t, source.z)

    return 1
