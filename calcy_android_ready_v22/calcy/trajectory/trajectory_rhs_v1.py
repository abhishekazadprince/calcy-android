"""calcode_trajectory_rhs_v1.py -- exact Python port of
calcode_trajectory_rhs_v1.c / calcode_trajectory_rhs_v1.h.

Original: a fixed-step forward-Euler sampler that drives a
`CalcodeStateRhsV1` from an initial `CalcodeStateRhsContextV1` and
records the resulting `(time, state)` trajectory into flat
caller-allocated arrays. This is the group-3 "trajectory generation"
leaf that everything downstream (3D geometry/blob/trail/scene) reads
from.

PORT NOTES:

- `times`/`states` (C's `double *`, heap-allocated by
  `calcode_trajectory_rhs_allocate_v1`) are modeled as flat Python
  lists, exactly like the sibling `calcode_trajectory_stats_v1.py`
  port models `CalcodeTrajectoryModelV1.state`: `states` is a single
  flat list of length `steps * state_dimension`, row-major
  (`states[i * state_dimension + j]`), reproduced via the same
  `_state_at_v1(t, index)` helper the C uses (`t->states +
  index*state_dimension`), which here returns the row's starting flat
  index rather than a pointer.
- `calcode_trajectory_rhs_free_v1` sets `times`/`states` to `None`
  (C's `free` + `= NULL`) and resets `steps`, `state_dimension`,
  `generated` to 0 -- matching that the C's `free_v1` does NOT touch
  `diagnostic`, `t0`, `t1`, or `dt` (only `allocate_v1` calls
  `free_v1` first, and `init_v1` does the full `memset` reset
  separately).
- `calcode_trajectory_rhs_allocate_v1` validates `t` is present,
  `state_dimension > 0`, and `steps >= 2` (note: `>= 2`, not `> 0` --
  a trajectory needs at least two samples). It always calls
  `free_v1` first (matching the C's unconditional free-before-
  realloc), then allocates two zero-filled flat lists. Since Python
  list allocation cannot practically fail the way C's `calloc` can,
  the "allocation failed" diagnostic/failure path is preserved in
  source form (see the C behavior note below) but is unreachable in
  this port -- documented rather than silently dropped.
- `calcode_trajectory_rhs_sample_euler_v1` validates, in this exact
  order: `t`/`rhs`/`initial_context` non-None; `rhs.valid`;
  `t.state_dimension == rhs.dimension` (exact equality, not `>=`);
  `t.times`/`t.states` both present; `t.steps >= 2`;
  `initial_context.state` present. `t.generated` is reset to 0 up
  front (matching the C, so a failed re-sample leaves `generated`
  cleared even if a previous sample had succeeded).
- The first row is seeded directly from `initial_context.state`/`.t`
  (bypassing the RHS entirely for sample 0, matching the C).
  `context` is a **shallow copy** of `initial_context` (C's `context
  = *initial_context;`, a struct copy) so that `context.parameters`
  aliases the same list as `initial_context.parameters` -- mutating
  `context.t`/`context.state` on the copy never touches the caller's
  `initial_context`, exactly like the C only overwrites the copy's
  `.t`/`.state` fields, matching the C where `parameters` is an
  in-place fixed array member (copied by value in C, but this port
  keeps parity by not mutating `context.parameters` anywhere in this
  function either -- only `.t` and `.state` are ever reassigned).
- Per step `i` in `[0, steps - 1)`: evaluate the RHS at
  `(t.times[i], state_at(i))` into a reusable `derivative` buffer via
  `calcode_state_rhs_eval_v1`; on failure, set the diagnostic and
  return 0 immediately (matching the C, which does not restore
  `generated`). `h = t.dt` is re-read from `t` on every iteration
  (not cached once before the loop), matching the C exactly, so a
  caller mutating `t.dt` from a re-entrant callback mid-loop -- while
  not something this port's harness exercises -- would be honored
  the same way the C honors it. `h == 0.0` is checked with exact
  float equality (not a tolerance), matching the C's `if (h == 0.0)`.
- `next[j] = current[j] + h * derivative[j]` and `times[i+1] =
  times[i] + h` are computed in that exact order per the C.
- On full success: `generated = 1`, `diagnostic` cleared to `""`
  (C's `t->diagnostic[0] = '\\0'`).
"""

from __future__ import annotations

from typing import List, Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.symbolic.state_rhs_v1 import (
    CalcodeStateRhsV1,
    CalcodeStateRhsContextV1,
    calcode_state_rhs_eval_v1,
)


class CalcodeTrajectoryRhsV1:
    """typedef struct CalcodeTrajectoryRhsV1 { ... } CalcodeTrajectoryRhsV1."""
    __slots__ = (
        "rhs", "t0", "t1", "dt", "steps",
        "times", "states", "state_dimension", "generated", "diagnostic",
    )

    def __init__(self):
        self.rhs = CalcodeStateRhsV1()
        self.t0 = 0.0
        self.t1 = 0.0
        self.dt = 0.0
        self.steps = 0
        self.times: Optional[List[float]] = None
        self.states: Optional[List[float]] = None
        self.state_dimension = 0
        self.generated = 0
        self.diagnostic = ""


def _diagnostic(t: Optional[CalcodeTrajectoryRhsV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(CalcodeTrajectoryRhsV1 *t, const char *message);"""
    if t is None:
        return
    text = message if message else "trajectory error"
    t.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_trajectory_rhs_init_v1(t: Optional[CalcodeTrajectoryRhsV1]) -> None:
    """void calcode_trajectory_rhs_init_v1(CalcodeTrajectoryRhsV1 *trajectory);"""
    if t is None:
        return

    t.rhs = CalcodeStateRhsV1()
    t.t0 = 0.0
    t.t1 = 0.0
    t.dt = 0.0
    t.steps = 0
    t.times = None
    t.states = None
    t.state_dimension = 0
    t.generated = 0
    t.diagnostic = ""


def calcode_trajectory_rhs_free_v1(t: Optional[CalcodeTrajectoryRhsV1]) -> None:
    """void calcode_trajectory_rhs_free_v1(CalcodeTrajectoryRhsV1 *trajectory);"""
    if t is None:
        return

    t.times = None
    t.states = None

    t.steps = 0
    t.state_dimension = 0
    t.generated = 0


def calcode_trajectory_rhs_allocate_v1(
    t: Optional[CalcodeTrajectoryRhsV1],
    state_dimension: int,
    steps: int,
) -> int:
    """int calcode_trajectory_rhs_allocate_v1(CalcodeTrajectoryRhsV1 *trajectory,
    int state_dimension, int steps);"""
    if t is None or state_dimension <= 0 or steps < 2:
        return 0

    calcode_trajectory_rhs_free_v1(t)

    t.times = [0.0] * steps
    t.states = [0.0] * (steps * state_dimension)

    # C's calloc-failure path (frees, sets an "allocation failed"
    # diagnostic, returns 0) is unreachable here -- Python list
    # allocation of this size does not fail in practice -- but is
    # kept documented per the port method rather than silently
    # dropped.

    t.steps = steps
    t.state_dimension = state_dimension

    return 1


def _state_at_v1(t: CalcodeTrajectoryRhsV1, index: int) -> int:
    """static double *state_at_v1(CalcodeTrajectoryRhsV1 *t, int index);
    Returns the row's starting flat index into t.states (row-major),
    in place of the C's raw pointer arithmetic."""
    return index * t.state_dimension


def calcode_trajectory_rhs_sample_euler_v1(
    t: Optional[CalcodeTrajectoryRhsV1],
    rhs: Optional[CalcodeStateRhsV1],
    initial_context: Optional[CalcodeStateRhsContextV1],
) -> int:
    """int calcode_trajectory_rhs_sample_euler_v1(CalcodeTrajectoryRhsV1 *trajectory,
    const CalcodeStateRhsV1 *rhs, const CalcodeStateRhsContextV1 *initial_context);"""
    if t is None or rhs is None or initial_context is None:
        return 0

    if not rhs.valid:
        return 0

    if t.state_dimension != rhs.dimension:
        return 0

    if t.times is None or t.states is None:
        return 0

    if t.steps < 2:
        return 0

    if initial_context.state is None:
        return 0

    t.generated = 0

    first = _state_at_v1(t, 0)

    for j in range(t.state_dimension):
        t.states[first + j] = initial_context.state[j]

    t.times[0] = initial_context.t

    context = CalcodeStateRhsContextV1()
    context.t = initial_context.t
    context.state = initial_context.state
    context.state_dimension = initial_context.state_dimension
    context.parameters = initial_context.parameters
    context.parameter_count = initial_context.parameter_count

    derivative = [0.0] * t.state_dimension

    for i in range(t.steps - 1):

        current = _state_at_v1(t, i)
        nxt = _state_at_v1(t, i + 1)

        context.t = t.times[i]
        context.state = t.states[current: current + t.state_dimension]

        if not calcode_state_rhs_eval_v1(rhs, context, derivative):
            _diagnostic(t, "state RHS evaluation failed")
            return 0

        h = t.dt

        if h == 0.0:
            _diagnostic(t, "trajectory dt is zero")
            return 0

        for j in range(t.state_dimension):
            t.states[nxt + j] = t.states[current + j] + h * derivative[j]

        t.times[i + 1] = t.times[i] + h

    t.generated = 1
    t.diagnostic = ""

    return 1
