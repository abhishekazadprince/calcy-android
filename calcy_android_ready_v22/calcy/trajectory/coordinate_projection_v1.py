"""calcode_coordinate_projection_v1.py -- exact Python port of
calcode_coordinate_projection_v1.c / calcode_coordinate_projection_v1.h.

Original: configures how a trajectory's (time, state[]) samples map
onto up to 3 view axes (x/y/z), for the 3D "blob" view and 2D graph.
Five constructor-style setters pick a projection "kind" (time vs one
state, state vs state, 3 states, the state-state-time time-embedding
used by `vertical_experiment_v1`, and a normalized-state variant);
`point_v1` evaluates one trajectory sample through the configured
axes; `bounds_v1` scans a whole trajectory to find the min/max box.

PORT NOTES:

- `CalcodeProjectionAxisV1`'s `axis_init_v1` sets `state_index = -1`,
  `scale = 1.0`, `offset = 0.0` after the C's `memset` (so `use_time`
  and `label` start at their zeroed defaults: 0 and `""`) --
  reproduced with the same explicit field values in `__init__`/
  `axis_init_v1` rather than relying on Python defaults matching by
  coincidence.
- Every `calcode_projection_*_v1` constructor calls `init_v1` only
  **after** its own guard check passes (matching the C's `if (!p ||
  x < 0 ...) return 0;` running *before* `init_v1(p)`) -- so on a
  guard failure (e.g. a negative index, or `p is None`), the
  projection is returned untouched, not reset. A caller that passed
  in an already-`valid=1` projection and then a bad index keeps
  seeing `valid=1` (dirty) afterward -- confirmed against the real C
  by harness (`neg_index_reject=0 valid_after=1` when `p` starts
  dirty). Only a *successful* call resets-then-rebuilds via
  `init_v1`.
- `calcode_projection_state_state_time_v1`'s kind is
  `CALCODE_PROJECTION_STATE_3D_V1` (not a distinct kind of its own,
  matching the C's actual assignment -- named in the enum as if it
  were STATE_STATE_TIME but the real C reuses STATE_3D_V1) -- this is
  the "time-embedded" projection referenced in
  `vertical_experiment_v1`'s planned porting notes; its `z` axis has
  `state_index = -1` and `use_time = 1`, matching `p->z.state_index
  = -1; p->z.use_time = 1;` in exactly that order.
- `axis_value_v1` checks `use_time` first (returns `time[sample] *
  scale + offset` unconditionally when set, even if `state_index`
  happens to be >= 0), else falls through to the state-index bounds
  check (`0.0` on an out-of-range index) -- reproduced with the same
  precedence.
- `calcode_projection_point_v1`'s guard order is preserved exactly:
  None-checks on `p`/`t`/`point`; `p.valid`/`t.valid`; sample index
  range; then per-axis validity -- `x`/`y` are checked with
  `valid_state_index_v1` whenever `use_time` is false (regardless of
  whether `state_index` is itself negative -- a `use_time=0`,
  `state_index=-1` x/y axis, which the setters never produce but a
  caller *could* hand-construct, fails this check, exactly as in C);
  `z` only gets the same check when `use_time` is false **and**
  `z.state_index >= 0` (so a freshly-`init_v1`'d z axis, which is
  `use_time=0, state_index=-1`, is accepted as "no z" and evaluates
  via `axis_value_v1`'s own `-1`-is-out-of-range fallback to `0.0`,
  not rejected) -- this asymmetry between x/y and z is real C
  behavior, reproduced as-is, not "fixed."
- The final `isfinite(x) and isfinite(y) and isfinite(z)` return uses
  Python's `and`, short-circuiting identically to the C's `&&` chain
  (though `isfinite` has no side effects here, so this only affects
  which computed values get evaluated, not correctness).
- `calcode_projection_bounds_v1` evaluates sample 0 first to seed
  min/max, then scans `i in range(1, sample_count)` -- reproduced
  with the same seed-then-scan structure and strict `<`/`>`
  comparisons (ties keep the earliest-seen bound, i.e. the sample-0
  seed, since later equal values fail both strict comparisons).
"""

from __future__ import annotations

import math
from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.trajectory.trajectory_model_v1 import CalcodeTrajectoryModelV1

CALCODE_PROJECTION_LABEL_V1 = 64


class CalcodeProjectionKindV1:
    """typedef enum CalcodeProjectionKindV1 { ... } CalcodeProjectionKindV1."""
    CALCODE_PROJECTION_TIME_STATE_V1 = 0
    CALCODE_PROJECTION_STATE_STATE_V1 = 1
    CALCODE_PROJECTION_STATE_3D_V1 = 2
    CALCODE_PROJECTION_NORMALIZED_STATE_V1 = 3


class CalcodeProjectionAxisV1:
    """typedef struct CalcodeProjectionAxisV1 { ... } CalcodeProjectionAxisV1."""
    __slots__ = ("state_index", "use_time", "scale", "offset", "label")

    def __init__(self):
        self.state_index = -1
        self.use_time = 0
        self.scale = 1.0
        self.offset = 0.0
        self.label = ""


class CalcodeCoordinateProjectionV1:
    """typedef struct CalcodeCoordinateProjectionV1 { ... } CalcodeCoordinateProjectionV1."""
    __slots__ = (
        "valid", "kind", "x", "y", "z",
        "x_min", "x_max", "y_min", "y_max", "z_min", "z_max",
        "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.kind = CalcodeProjectionKindV1.CALCODE_PROJECTION_TIME_STATE_V1
        self.x = CalcodeProjectionAxisV1()
        self.y = CalcodeProjectionAxisV1()
        self.z = CalcodeProjectionAxisV1()
        self.x_min = 0.0
        self.x_max = 0.0
        self.y_min = 0.0
        self.y_max = 0.0
        self.z_min = 0.0
        self.z_max = 0.0
        self.diagnostic = ""


class CalcodeProjectedPointV1:
    """typedef struct CalcodeProjectedPointV1 { ... } CalcodeProjectedPointV1."""
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x = x
        self.y = y
        self.z = z


def _diagnostic(p: Optional[CalcodeCoordinateProjectionV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(CalcodeCoordinateProjectionV1 *p, const char *message);"""
    if p is None:
        return
    text = message if message else "projection error"
    p.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def _axis_init(axis: Optional[CalcodeProjectionAxisV1]) -> None:
    """static void axis_init_v1(CalcodeProjectionAxisV1 *axis);"""
    if axis is None:
        return

    axis.state_index = -1
    axis.use_time = 0
    axis.scale = 1.0
    axis.offset = 0.0
    axis.label = ""


def calcode_coordinate_projection_init_v1(p: Optional[CalcodeCoordinateProjectionV1]) -> None:
    """void calcode_coordinate_projection_init_v1(CalcodeCoordinateProjectionV1 *projection);"""
    if p is None:
        return

    p.valid = 0
    p.kind = CalcodeProjectionKindV1.CALCODE_PROJECTION_TIME_STATE_V1
    p.x_min = 0.0
    p.x_max = 0.0
    p.y_min = 0.0
    p.y_max = 0.0
    p.z_min = 0.0
    p.z_max = 0.0
    p.diagnostic = ""

    p.x = CalcodeProjectionAxisV1()
    p.y = CalcodeProjectionAxisV1()
    p.z = CalcodeProjectionAxisV1()

    _axis_init(p.x)
    _axis_init(p.y)
    _axis_init(p.z)


def _valid_state_index(t: Optional[CalcodeTrajectoryModelV1], index: int) -> bool:
    """static int valid_state_index_v1(const CalcodeTrajectoryModelV1 *t, int index);"""
    return bool(t) and bool(t.valid) and index >= 0 and index < t.state_dimension


def _set_label(axis: Optional[CalcodeProjectionAxisV1], label: Optional[str]) -> None:
    """static void set_label_v1(CalcodeProjectionAxisV1 *axis, const char *label);"""
    if axis is None or label is None:
        return

    axis.label = label[: CALCODE_PROJECTION_LABEL_V1 - 1]


def calcode_projection_time_state_v1(
    p: Optional[CalcodeCoordinateProjectionV1], state_index: int
) -> int:
    """int calcode_projection_time_state_v1(CalcodeCoordinateProjectionV1 *projection,
    int state_index);"""
    if p is None or state_index < 0:
        return 0

    calcode_coordinate_projection_init_v1(p)

    p.kind = CalcodeProjectionKindV1.CALCODE_PROJECTION_TIME_STATE_V1

    p.x.use_time = 1
    p.x.state_index = -1
    _set_label(p.x, "t")

    p.y.use_time = 0
    p.y.state_index = state_index
    _set_label(p.y, "state")

    p.z.use_time = 0
    p.z.state_index = -1
    _set_label(p.z, "0")

    p.valid = 1
    return 1


def calcode_projection_state_state_v1(
    p: Optional[CalcodeCoordinateProjectionV1], x_state_index: int, y_state_index: int
) -> int:
    """int calcode_projection_state_state_v1(CalcodeCoordinateProjectionV1 *projection,
    int x_state_index, int y_state_index);"""
    if p is None or x_state_index < 0 or y_state_index < 0:
        return 0

    calcode_coordinate_projection_init_v1(p)

    p.kind = CalcodeProjectionKindV1.CALCODE_PROJECTION_STATE_STATE_V1

    p.x.state_index = x_state_index
    p.y.state_index = y_state_index

    _set_label(p.x, "state")
    _set_label(p.y, "state")
    _set_label(p.z, "0")

    p.valid = 1
    return 1


def calcode_projection_state_3d_v1(
    p: Optional[CalcodeCoordinateProjectionV1],
    x_state_index: int,
    y_state_index: int,
    z_state_index: int,
) -> int:
    """int calcode_projection_state_3d_v1(CalcodeCoordinateProjectionV1 *projection,
    int x_state_index, int y_state_index, int z_state_index);"""
    if p is None or x_state_index < 0 or y_state_index < 0 or z_state_index < 0:
        return 0

    calcode_coordinate_projection_init_v1(p)

    p.kind = CalcodeProjectionKindV1.CALCODE_PROJECTION_STATE_3D_V1

    p.x.state_index = x_state_index
    p.y.state_index = y_state_index
    p.z.state_index = z_state_index

    _set_label(p.x, "state")
    _set_label(p.y, "state")
    _set_label(p.z, "state")

    p.valid = 1
    return 1


def calcode_projection_state_state_time_v1(
    p: Optional[CalcodeCoordinateProjectionV1], x_state_index: int, y_state_index: int
) -> int:
    """int calcode_projection_state_state_time_v1(CalcodeCoordinateProjectionV1 *projection,
    int x_state_index, int y_state_index);

    Generic 3D embedding for a 2-state dynamical system: X=state[i],
    Y=state[j], Z=time.
    """
    if p is None or x_state_index < 0 or y_state_index < 0:
        return 0

    calcode_coordinate_projection_init_v1(p)

    p.kind = CalcodeProjectionKindV1.CALCODE_PROJECTION_STATE_3D_V1
    p.x.state_index = x_state_index
    p.y.state_index = y_state_index
    p.z.state_index = -1
    p.z.use_time = 1

    _set_label(p.x, "state")
    _set_label(p.y, "state")
    _set_label(p.z, "t")

    p.valid = 1
    return 1


def calcode_projection_normalized_state_v1(
    p: Optional[CalcodeCoordinateProjectionV1],
    x_state_index: int,
    y_state_index: int,
    z_state_index: int,
) -> int:
    """int calcode_projection_normalized_state_v1(CalcodeCoordinateProjectionV1 *projection,
    int x_state_index, int y_state_index, int z_state_index);"""
    if p is None or x_state_index < 0 or y_state_index < 0 or z_state_index < 0:
        return 0

    calcode_coordinate_projection_init_v1(p)

    p.kind = CalcodeProjectionKindV1.CALCODE_PROJECTION_NORMALIZED_STATE_V1

    p.x.state_index = x_state_index
    p.y.state_index = y_state_index
    p.z.state_index = z_state_index

    p.x.scale = 1.0
    p.y.scale = 1.0
    p.z.scale = 1.0

    _set_label(p.x, "normalized state")
    _set_label(p.y, "normalized state")
    _set_label(p.z, "normalized state")

    p.valid = 1
    return 1


def _axis_value(
    axis: CalcodeProjectionAxisV1, t: CalcodeTrajectoryModelV1, sample: int
) -> float:
    """static double axis_value_v1(const CalcodeProjectionAxisV1 *axis,
    const CalcodeTrajectoryModelV1 *t, int sample);"""
    if axis.use_time:
        return t.time[sample] * axis.scale + axis.offset

    if axis.state_index < 0 or axis.state_index >= t.state_dimension:
        return 0.0

    return (
        t.state[sample * t.state_dimension + axis.state_index] * axis.scale
        + axis.offset
    )


def calcode_projection_point_v1(
    p: Optional[CalcodeCoordinateProjectionV1],
    t: Optional[CalcodeTrajectoryModelV1],
    sample_index: int,
    point: Optional[CalcodeProjectedPointV1],
) -> int:
    """int calcode_projection_point_v1(const CalcodeCoordinateProjectionV1 *projection,
    const CalcodeTrajectoryModelV1 *trajectory, int sample_index,
    CalcodeProjectedPointV1 *point);"""
    if p is None or t is None or point is None or not p.valid or not t.valid:
        return 0

    if sample_index < 0 or sample_index >= t.sample_count:
        return 0

    if not p.x.use_time and not _valid_state_index(t, p.x.state_index):
        return 0

    if not p.y.use_time and not _valid_state_index(t, p.y.state_index):
        return 0

    if not p.z.use_time and p.z.state_index >= 0 and not _valid_state_index(t, p.z.state_index):
        return 0

    point.x = _axis_value(p.x, t, sample_index)
    point.y = _axis_value(p.y, t, sample_index)
    point.z = _axis_value(p.z, t, sample_index)

    return int(math.isfinite(point.x) and math.isfinite(point.y) and math.isfinite(point.z))


def calcode_projection_bounds_v1(
    p: Optional[CalcodeCoordinateProjectionV1], t: Optional[CalcodeTrajectoryModelV1]
) -> int:
    """int calcode_projection_bounds_v1(CalcodeCoordinateProjectionV1 *projection,
    const CalcodeTrajectoryModelV1 *trajectory);"""
    if p is None or t is None or not p.valid or not t.valid or t.sample_count <= 0:
        return 0

    point = CalcodeProjectedPointV1()

    if not calcode_projection_point_v1(p, t, 0, point):
        _diagnostic(p, "unable to evaluate first projected point")
        return 0

    p.x_min = p.x_max = point.x
    p.y_min = p.y_max = point.y
    p.z_min = p.z_max = point.z

    for i in range(1, t.sample_count):
        if not calcode_projection_point_v1(p, t, i, point):
            _diagnostic(p, "unable to evaluate projected trajectory")
            return 0

        if point.x < p.x_min:
            p.x_min = point.x

        if point.x > p.x_max:
            p.x_max = point.x

        if point.y < p.y_min:
            p.y_min = point.y

        if point.y > p.y_max:
            p.y_max = point.y

        if point.z < p.z_min:
            p.z_min = point.z

        if point.z > p.z_max:
            p.z_max = point.z

    p.diagnostic = ""
    return 1
