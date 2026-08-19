"""calcode_graph_model_v1.py -- exact Python port of
calcode_graph_model_v1.c / calcode_graph_model_v1.h.

Original: builds a 2D graph model (points + two labeled/ticked axes)
from a trajectory projected through a CalcodeCoordinateProjectionV1.
Also implements the "nice number" axis-tick algorithm (~8 ticks,
1/2/5-scaled step) shared by any axis-drawing code in the C original.

PORT NOTES:

- `calcode_graph_model_init_v1` zeroes the struct then sets
  `source_component_x = source_component_y = -1`, matching the C's
  `memset` + explicit `-1` assignment -- reproduced with explicit
  field defaults in `__init__`/`init_v1` rather than relying on
  Python's own falsy defaults.
- `calcode_graph_model_build_v1` calls `free_v1()` then `init_v1()`
  unconditionally at the top (even before validating `t`/`p`), exactly
  matching the C's call order -- reproduced as-is: any prior points
  list is dropped before the guard checks that can still fail.
- The z-axis comment/no-op branch (`p->z.state_index >= 0 ||
  p->z.use_time`) is preserved as a literal no-op (an empty `if`)
  for structural fidelity with the source, even though it has no
  observable effect.
- `build_axis_v1`'s degenerate-range branch (`fabs(maximum - minimum)
  <= 1e-30`) pads by `10%` of `|minimum|` when `|minimum| > 1.0`,
  else by a flat `1.0` -- reproduced with the exact same threshold
  and branch order, including evaluating on the *pre-swap* padded
  values (the min/max swap for `maximum < minimum` happens first,
  then the degenerate check runs on the already-ordered pair).
- Tick generation uses the same `for (v = first; v <= max + 0.5*step;
  v += step)` floating-point loop as the C, including the
  `count < CALCODE_GRAPH_MAX_TICKS_V1` cap -- reproduced with a
  `while` loop of identical bounds (Python has no C-style `for`),
  preserving the same float accumulation (no re-derivation via
  `range()`/`linspace` that would round differently).
- `format_tick_v1`'s four `step` bands (`>=1.0` -> `%.0f`, `>=0.1` ->
  `%.1f`, `>=0.01` -> `%.2f`, else `%.4g`) are reproduced with Python
  `%`-formatting against the same thresholds and in the same order.
- `calcode_graph_model_build_v1` allocates `points` via a Python list
  sized to `t.sample_count` up front (mirroring the C's `calloc`),
  and on any later failure calls `free_v1()` (clearing points/count/
  valid) before returning 0 -- same cleanup-then-fail pattern as C,
  reproduced call-for-call.
- `calcode_graph_model_point_v1`'s bounds check (`!valid`, no points,
  negative index, index >= point_count) is reproduced with the same
  guard order, returning `None` in place of C's `NULL`.
"""

from __future__ import annotations

import math
from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.trajectory.trajectory_model_v1 import CalcodeTrajectoryModelV1
from calcy.trajectory.coordinate_projection_v1 import (
    CalcodeCoordinateProjectionV1,
    CalcodeProjectedPointV1,
    calcode_projection_point_v1,
)

CALCODE_GRAPH_MAX_TICKS_V1 = 128
CALCODE_GRAPH_MAX_LABEL_V1 = 64


class CalcodeGraphTickV1:
    """typedef struct CalcodeGraphTickV1 { ... } CalcodeGraphTickV1."""
    __slots__ = ("value", "label")

    def __init__(self):
        self.value = 0.0
        self.label = ""


class CalcodeGraphAxisV1:
    """typedef struct CalcodeGraphAxisV1 { ... } CalcodeGraphAxisV1."""
    __slots__ = ("label", "minimum", "maximum", "tick_step",
                 "tick_count", "ticks")

    def __init__(self):
        self.label = ""
        self.minimum = 0.0
        self.maximum = 0.0
        self.tick_step = 0.0
        self.tick_count = 0
        self.ticks = [CalcodeGraphTickV1()
                       for _ in range(CALCODE_GRAPH_MAX_TICKS_V1)]


class CalcodeGraphPointV1:
    """typedef struct CalcodeGraphPointV1 { ... } CalcodeGraphPointV1."""
    __slots__ = ("x", "y")

    def __init__(self, x: float = 0.0, y: float = 0.0):
        self.x = x
        self.y = y


class CalcodeGraphModelV1:
    """typedef struct CalcodeGraphModelV1 { ... } CalcodeGraphModelV1."""
    __slots__ = (
        "valid", "x_axis", "y_axis", "point_count", "points",
        "source_component_x", "source_component_y", "source_uses_time_x",
        "title", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.x_axis = CalcodeGraphAxisV1()
        self.y_axis = CalcodeGraphAxisV1()
        self.point_count = 0
        self.points: list[CalcodeGraphPointV1] = []
        self.source_component_x = -1
        self.source_component_y = -1
        self.source_uses_time_x = 0
        self.title = ""
        self.diagnostic = ""


def _diagnostic_v1(g: Optional[CalcodeGraphModelV1], message: Optional[str]) -> None:
    if g is None:
        return
    g.diagnostic = (message if message is not None else "graph model error")[
        :CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_graph_model_init_v1(g: Optional[CalcodeGraphModelV1]) -> None:
    if g is None:
        return
    g.valid = 0
    g.x_axis = CalcodeGraphAxisV1()
    g.y_axis = CalcodeGraphAxisV1()
    g.point_count = 0
    g.points = []
    g.title = ""
    g.diagnostic = ""
    g.source_component_x = -1
    g.source_component_y = -1
    g.source_uses_time_x = 0


def calcode_graph_model_free_v1(g: Optional[CalcodeGraphModelV1]) -> None:
    if g is None:
        return
    g.points = []
    g.point_count = 0
    g.valid = 0


def calcode_graph_model_set_title_v1(g: Optional[CalcodeGraphModelV1],
                                      title: Optional[str]) -> int:
    if g is None or title is None:
        return 0
    g.title = title[:127]
    return 1


def _nice_number_v1(value: float, round_value: int) -> float:
    if value <= 0.0:
        return 1.0

    exponent = math.floor(math.log10(value))
    fraction = value / (10.0 ** exponent)

    if round_value:
        if fraction < 1.5:
            nice_fraction = 1.0
        elif fraction < 3.0:
            nice_fraction = 2.0
        elif fraction < 7.0:
            nice_fraction = 5.0
        else:
            nice_fraction = 10.0
    else:
        if fraction <= 1.0:
            nice_fraction = 1.0
        elif fraction <= 2.0:
            nice_fraction = 2.0
        elif fraction <= 5.0:
            nice_fraction = 5.0
        else:
            nice_fraction = 10.0

    return nice_fraction * (10.0 ** exponent)


def _choose_tick_step_v1(minimum: float, maximum: float) -> float:
    range_ = maximum - minimum
    if range_ <= 0.0:
        return 1.0
    rough = range_ / 8.0
    return _nice_number_v1(rough, 1)


def _format_tick_v1(value: float, step: float) -> str:
    if step >= 1.0:
        return "%.0f" % value
    elif step >= 0.1:
        return "%.1f" % value
    elif step >= 0.01:
        return "%.2f" % value
    else:
        return "%.4g" % value


def _build_axis_v1(axis: Optional[CalcodeGraphAxisV1], label: Optional[str],
                    minimum: float, maximum: float) -> int:
    if axis is None or not math.isfinite(minimum) or not math.isfinite(maximum):
        return 0

    new_axis = CalcodeGraphAxisV1()
    new_axis.label = (label if label is not None else "")[:CALCODE_GRAPH_MAX_LABEL_V1 - 1]

    if maximum < minimum:
        minimum, maximum = maximum, minimum

    if abs(maximum - minimum) <= 1e-30:
        pad = abs(minimum) * 0.1 if abs(minimum) > 1.0 else 1.0
        minimum -= pad
        maximum += pad

    step = _choose_tick_step_v1(minimum, maximum)
    first = math.ceil(minimum / step) * step

    count = 0
    value = first
    while value <= maximum + 0.5 * step and count < CALCODE_GRAPH_MAX_TICKS_V1:
        tick = new_axis.ticks[count]
        tick.value = value
        tick.label = _format_tick_v1(value, step)
        count += 1
        value += step

    new_axis.minimum = minimum
    new_axis.maximum = maximum
    new_axis.tick_step = step
    new_axis.tick_count = count

    axis.label = new_axis.label
    axis.minimum = new_axis.minimum
    axis.maximum = new_axis.maximum
    axis.tick_step = new_axis.tick_step
    axis.tick_count = new_axis.tick_count
    axis.ticks = new_axis.ticks

    return 1 if count > 0 else 0


def _projection_to_graph_point_v1(
        p: CalcodeCoordinateProjectionV1,
        t: CalcodeTrajectoryModelV1,
        index: int) -> Optional[CalcodeGraphPointV1]:
    projected = CalcodeProjectedPointV1()
    if not calcode_projection_point_v1(p, t, index, projected):
        return None
    return CalcodeGraphPointV1(projected.x, projected.y)


def calcode_graph_model_build_v1(
        g: Optional[CalcodeGraphModelV1],
        t: Optional[CalcodeTrajectoryModelV1],
        p: Optional[CalcodeCoordinateProjectionV1]) -> int:
    if g is None or t is None or p is None:
        return 0

    calcode_graph_model_free_v1(g)
    calcode_graph_model_init_v1(g)

    if not t.valid or t.sample_count <= 0:
        _diagnostic_v1(g, "trajectory is invalid or empty")
        return 0

    if not p.valid:
        _diagnostic_v1(g, "projection is invalid")
        return 0

    if p.z.state_index >= 0 or p.z.use_time:
        # A graph is two-dimensional. A projection with a nontrivial z
        # coordinate is still allowed mathematically, but this graph model
        # intentionally consumes only x and y.
        pass

    g.points = [CalcodeGraphPointV1() for _ in range(t.sample_count)]

    for i in range(t.sample_count):
        pt = _projection_to_graph_point_v1(p, t, i)
        if pt is None:
            calcode_graph_model_free_v1(g)
            _diagnostic_v1(g, "unable to project trajectory into graph")
            return 0
        g.points[i] = pt

    g.point_count = t.sample_count

    if not _build_axis_v1(g.x_axis, p.x.label, p.x_min, p.x_max):
        calcode_graph_model_free_v1(g)
        _diagnostic_v1(g, "unable to construct x axis")
        return 0

    if not _build_axis_v1(g.y_axis, p.y.label, p.y_min, p.y_max):
        calcode_graph_model_free_v1(g)
        _diagnostic_v1(g, "unable to construct y axis")
        return 0

    g.source_component_x = p.x.state_index
    g.source_component_y = p.y.state_index
    g.source_uses_time_x = p.x.use_time

    g.valid = 1
    g.diagnostic = ""

    return 1


def calcode_graph_model_point_v1(
        g: Optional[CalcodeGraphModelV1], index: int) -> Optional[CalcodeGraphPointV1]:
    if (g is None or not g.valid or not g.points or
            index < 0 or index >= g.point_count):
        return None
    return g.points[index]
