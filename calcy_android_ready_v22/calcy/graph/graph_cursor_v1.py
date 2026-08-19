"""calcode_graph_cursor_v1.py -- exact Python port of
calcode_graph_cursor_v1.c / calcode_graph_cursor_v1.h.

Original: builds a graph cursor at a given trajectory sample index --
its projected (x, y) position, timestamp, and a copy of the full state
vector at that sample (capped to CALCODE_RK4_MAX_STATE_V1).

Depends only on calcode_graph_model_v1.h (which pulls in
calcode_coordinate_projection_v1.h, which pulls in
calcode_trajectory_model_v1.h) plus CALCODE_RK4_MAX_STATE_V1
(calcode_rk4_integrator_v1.h) -- all already ported/verified.

PORT NOTES:

- `calcode_graph_cursor_at_v1` calls `init_v1()` unconditionally right
  after the initial NULL guard, exactly matching the C's call order --
  reproduced as-is, so any prior cursor content is dropped before the
  validity/bounds guards that can still fail.
- The state-dimension cap (`state_dimension > CALCODE_RK4_MAX_STATE_V1`
  clamps down to the max) is applied *before* the state-copy loop uses
  it as the loop bound, reproduced in the same order.
- If `calcode_trajectory_model_state_at_v1` returns NULL, the C returns
  0 WITHOUT calling `diagnostic_v1` -- i.e. `c->diagnostic` is left at
  whatever `init_v1()` set it to (empty string), not overwritten with
  an error message. This is reproduced exactly (no diagnostic call on
  that specific failure path) even though it looks like an omission in
  the original.
"""

from __future__ import annotations

from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.trajectory.trajectory_model_v1 import (
    CalcodeTrajectoryModelV1,
    calcode_trajectory_model_state_at_v1,
)
from calcy.trajectory.coordinate_projection_v1 import (
    CalcodeCoordinateProjectionV1,
    CalcodeProjectedPointV1,
    calcode_projection_point_v1,
)
from calcy.numerical.rk4_integrator_v1 import CALCODE_RK4_MAX_STATE_V1


class CalcodeGraphCursorV1:
    """typedef struct CalcodeGraphCursorV1 { ... } CalcodeGraphCursorV1."""
    __slots__ = (
        "valid", "sample_index", "x", "y", "time",
        "state_dimension", "state", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.sample_index = 0
        self.x = 0.0
        self.y = 0.0
        self.time = 0.0
        self.state_dimension = 0
        self.state = [0.0] * CALCODE_RK4_MAX_STATE_V1
        self.diagnostic = ""


def _diagnostic(c: Optional[CalcodeGraphCursorV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(...);"""
    if c is None:
        return
    text = message if message is not None else "graph cursor error"
    c.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_graph_cursor_init_v1(c: Optional[CalcodeGraphCursorV1]) -> None:
    """void calcode_graph_cursor_init_v1(CalcodeGraphCursorV1 *cursor);"""
    if c is None:
        return

    c.valid = 0
    c.sample_index = -1
    c.x = 0.0
    c.y = 0.0
    c.time = 0.0
    c.state_dimension = 0
    c.state = [0.0] * CALCODE_RK4_MAX_STATE_V1
    c.diagnostic = ""


def calcode_graph_cursor_at_v1(
    c: Optional[CalcodeGraphCursorV1],
    t: Optional[CalcodeTrajectoryModelV1],
    p: Optional[CalcodeCoordinateProjectionV1],
    sample_index: int,
) -> int:
    """int calcode_graph_cursor_at_v1(CalcodeGraphCursorV1 *cursor, const CalcodeTrajectoryModelV1 *trajectory, const CalcodeCoordinateProjectionV1 *projection, int sample_index);"""
    if c is None or t is None or p is None:
        return 0

    calcode_graph_cursor_init_v1(c)

    if not t.valid or not p.valid or sample_index < 0 or sample_index >= t.sample_count:
        _diagnostic(c, "cursor sample or source is invalid")
        return 0

    point = CalcodeProjectedPointV1()

    if not calcode_projection_point_v1(p, t, sample_index, point):
        _diagnostic(c, "unable to project cursor sample")
        return 0

    c.sample_index = sample_index
    c.x = point.x
    c.y = point.y
    c.time = t.time[sample_index]

    c.state_dimension = t.state_dimension

    if c.state_dimension > CALCODE_RK4_MAX_STATE_V1:
        c.state_dimension = CALCODE_RK4_MAX_STATE_V1

    state = calcode_trajectory_model_state_at_v1(t, sample_index)

    if state is None:
        return 0

    for i in range(c.state_dimension):
        c.state[i] = state[i]

    c.valid = 1
    c.diagnostic = ""

    return 1
