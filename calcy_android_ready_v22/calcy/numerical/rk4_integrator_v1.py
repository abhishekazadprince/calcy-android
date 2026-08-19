"""calcode_rk4_integrator_v1.py -- exact Python port of
calcode_rk4_integrator_v1.c / calcode_rk4_integrator_v1.h.

Original: a classic fixed-step RK4 ODE integrator driven by a built
`CalcodeStateRhsV1`. `calcode_rk4_integrator_configure_v1` validates a
`CalcodeRk4ConfigV1` (time interval, step size, sample count) against
the RHS's dimension; `calcode_rk4_integrate_v1` then advances the
system from `config.t0` to `config.t1`, optionally recording every
sampled `(t, state)` pair into a `CalcodeRk4ResultV1`.

PORT NOTES:

- `CalcodeRk4ResultV1.times` / `.states` are the C's `double *` heap
  buffers (`calloc`'d flat arrays, `states` laid out as
  `steps * dimension` row-major). Reproduced here as plain Python
  lists (`times`: length `steps`; `states`: flat length
  `steps * dimension`, same row-major indexing via
  `states[step * dimension + j]`) rather than nested lists, so the
  indexing arithmetic matches `result_state_v1` exactly. Both are
  `None` (C's `NULL`) whenever `config.store_trajectory` is false or
  before allocation.
- `calcode_rk4_result_free_v1` resets `times`/`states` to `None` and
  `success`/`steps_completed`/`state_dimension` to 0, but -- matching
  the C exactly -- does **not** touch `final_time` or `diagnostic`.
- `CalcodeRk4IntegratorV1.k1`/`k2`/`k3`/`k4`/`work`/`initial` are the
  C's fixed `[CALCODE_RK4_MAX_STATE_V1]` (64) scratch arrays, of which
  only indices `[0, dimension)` are ever meaningfully read or written.
  Reproduced here as plain Python lists sized to `dimension` once
  `configure_v1` succeeds (rather than a fixed 64-slot buffer), which
  is observably identical since the C code itself never touches
  indices `>= dimension`.
- `calcode_rk4_integrator_configure_v1` fully re-inits `integrator`
  first (matching the C's unconditional
  `calcode_rk4_integrator_init_v1(i)`), then validates, in this exact
  order: `rhs.valid`; `0 < rhs.dimension <=
  CALCODE_RK4_MAX_STATE_V1`; `t0`/`t1`/`dt` all finite; `dt != 0.0`;
  direction consistency (`t1 > t0` requires `dt > 0`, `t1 < t0`
  requires `dt < 0` -- note `t1 == t0` passes both direction checks
  trivially, exactly as in C); `steps >= 2`. `integrator.config` is
  stored as an independent copy of the fields (mirroring the C's
  `i->config = *config;` struct-assignment -- later mutation of the
  caller's config object must not affect the configured integrator).
- `calcode_rk4_integrator_set_initial_state_v1` writes `initial[j]`
  one index at a time and returns 0 (with a diagnostic) on the first
  non-finite entry -- entries already written before that index stay
  written, exactly matching the C's early-return-mid-loop behavior
  (no rollback).
- `rhs_eval_v1`'s "copy `*base` into a local context, then override
  `t`/`state`/`state_dimension`" is reproduced by shallow-copying the
  `parameters` list reference (parameters are read-only during eval,
  so this is observably identical to the C's full struct-copy) rather
  than constructing a brand-new `CalcodeStateRhsContextV1` field by
  field from scratch every call.
- `rk4_step_v1`'s intermediate `work` array reuse (`k1` -> `work` ->
  `k2` -> `work` -> `k3` -> `work` -> `k4` -> final combine) and its
  final per-component `isfinite` check on the updated `state` (which
  aborts the whole step, discarding partial updates already written
  into `state` for lower indices -- exactly like the C, which returns
  0 mid-loop leaving `state` partially updated) are both reproduced
  as-is.
- `calcode_rk4_integrate_v1`'s "shorten the final step to land exactly
  on `t1`" logic and its epsilon-snap
  (`abs(t - t1) <= 1e-14 * (1 + abs(t1))` -> `t = t1`) are reproduced
  with the same operator precedence and short-circuit order as the C.
- On an RHS-evaluation failure mid-integration, the C sets a
  diagnostic and returns 0 -- `result.success` is therefore left at
  whatever `allocate_result_v1` left it (0, from either the full
  `result_free` reset or an untouched fresh `CalcodeRk4ResultV1`),
  and `result.times`/`.states` retain whatever partial trajectory was
  already written before the failing step. Reproduced exactly (no
  extra cleanup beyond what the C does).
"""

from __future__ import annotations

import math
from typing import List, Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.symbolic.state_rhs_v1 import (
    CalcodeStateRhsV1,
    CalcodeStateRhsContextV1,
    calcode_state_rhs_eval_v1,
)

CALCODE_RK4_MAX_STATE_V1 = 64


class CalcodeRk4ConfigV1:
    """typedef struct CalcodeRk4ConfigV1 { ... } CalcodeRk4ConfigV1."""
    __slots__ = ("t0", "t1", "dt", "steps", "store_trajectory")

    def __init__(
        self,
        t0: float = 0.0,
        t1: float = 0.0,
        dt: float = 0.0,
        steps: int = 0,
        store_trajectory: int = 0,
    ):
        self.t0 = t0
        self.t1 = t1
        self.dt = dt
        self.steps = steps
        self.store_trajectory = store_trajectory

    def _copy(self) -> "CalcodeRk4ConfigV1":
        return CalcodeRk4ConfigV1(
            self.t0, self.t1, self.dt, self.steps, self.store_trajectory
        )


class CalcodeRk4ResultV1:
    """typedef struct CalcodeRk4ResultV1 { ... } CalcodeRk4ResultV1."""
    __slots__ = (
        "success", "state_dimension", "steps_completed", "final_time",
        "times", "states", "diagnostic",
    )

    def __init__(self):
        self.success = 0
        self.state_dimension = 0
        self.steps_completed = 0
        self.final_time = 0.0
        self.times: Optional[List[float]] = None
        self.states: Optional[List[float]] = None
        self.diagnostic = ""


class CalcodeRk4IntegratorV1:
    """typedef struct CalcodeRk4IntegratorV1 { ... } CalcodeRk4IntegratorV1."""
    __slots__ = (
        "valid", "dimension", "config", "rhs",
        "k1", "k2", "k3", "k4", "work", "initial", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.dimension = 0
        self.config = CalcodeRk4ConfigV1()
        self.rhs: Optional[CalcodeStateRhsV1] = None
        self.k1: List[float] = []
        self.k2: List[float] = []
        self.k3: List[float] = []
        self.k4: List[float] = []
        self.work: List[float] = []
        self.initial: List[float] = []
        self.diagnostic = ""


def _diagnostic_i(i: Optional[CalcodeRk4IntegratorV1], message: Optional[str]) -> None:
    """static void diagnostic_i_v1(CalcodeRk4IntegratorV1 *i, const char *message);"""
    if i is None:
        return
    text = message if message else "RK4 integrator error"
    i.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def _diagnostic_r(r: Optional[CalcodeRk4ResultV1], message: Optional[str]) -> None:
    """static void diagnostic_r_v1(CalcodeRk4ResultV1 *r, const char *message);"""
    if r is None:
        return
    text = message if message else "RK4 result error"
    r.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_rk4_integrator_init_v1(i: Optional[CalcodeRk4IntegratorV1]) -> None:
    """void calcode_rk4_integrator_init_v1(CalcodeRk4IntegratorV1 *integrator);"""
    if i is None:
        return

    i.valid = 0
    i.dimension = 0
    i.config = CalcodeRk4ConfigV1()
    i.rhs = None
    i.k1 = []
    i.k2 = []
    i.k3 = []
    i.k4 = []
    i.work = []
    i.initial = []
    i.diagnostic = ""


def calcode_rk4_integrator_configure_v1(
    i: Optional[CalcodeRk4IntegratorV1],
    rhs: Optional[CalcodeStateRhsV1],
    config: Optional[CalcodeRk4ConfigV1],
) -> int:
    """int calcode_rk4_integrator_configure_v1(CalcodeRk4IntegratorV1 *integrator,
    const CalcodeStateRhsV1 *rhs, const CalcodeRk4ConfigV1 *config);"""
    if i is None or rhs is None or config is None:
        return 0

    calcode_rk4_integrator_init_v1(i)

    if not rhs.valid:
        _diagnostic_i(i, "state RHS is invalid")
        return 0

    if rhs.dimension <= 0 or rhs.dimension > CALCODE_RK4_MAX_STATE_V1:
        _diagnostic_i(i, "state dimension exceeds RK4 capacity")
        return 0

    if not (math.isfinite(config.t0) and math.isfinite(config.t1) and math.isfinite(config.dt)):
        _diagnostic_i(i, "non-finite integration configuration")
        return 0

    if config.dt == 0.0:
        _diagnostic_i(i, "RK4 step size cannot be zero")
        return 0

    if config.t1 > config.t0 and config.dt < 0.0:
        _diagnostic_i(i, "positive interval requires positive dt")
        return 0

    if config.t1 < config.t0 and config.dt > 0.0:
        _diagnostic_i(i, "backward interval requires negative dt")
        return 0

    if config.steps < 2:
        _diagnostic_i(i, "RK4 requires at least two trajectory samples")
        return 0

    i.rhs = rhs
    i.dimension = rhs.dimension
    i.config = config._copy()

    i.k1 = [0.0] * i.dimension
    i.k2 = [0.0] * i.dimension
    i.k3 = [0.0] * i.dimension
    i.k4 = [0.0] * i.dimension
    i.work = [0.0] * i.dimension
    i.initial = [0.0] * i.dimension

    i.valid = 1
    i.diagnostic = ""

    return 1


def calcode_rk4_integrator_set_initial_state_v1(
    i: Optional[CalcodeRk4IntegratorV1], state: Optional[List[float]]
) -> int:
    """int calcode_rk4_integrator_set_initial_state_v1(CalcodeRk4IntegratorV1 *integrator,
    const double *state);"""
    if i is None or not i.valid or state is None:
        return 0

    for j in range(i.dimension):
        if not math.isfinite(state[j]):
            _diagnostic_i(i, "initial state contains non-finite value")
            return 0

        i.initial[j] = state[j]

    return 1


def calcode_rk4_result_init_v1(r: Optional[CalcodeRk4ResultV1]) -> None:
    """void calcode_rk4_result_init_v1(CalcodeRk4ResultV1 *result);"""
    if r is None:
        return

    r.success = 0
    r.state_dimension = 0
    r.steps_completed = 0
    r.final_time = 0.0
    r.times = None
    r.states = None
    r.diagnostic = ""


def calcode_rk4_result_free_v1(r: Optional[CalcodeRk4ResultV1]) -> None:
    """void calcode_rk4_result_free_v1(CalcodeRk4ResultV1 *result);"""
    if r is None:
        return

    r.times = None
    r.states = None

    r.success = 0
    r.steps_completed = 0
    r.state_dimension = 0


def _allocate_result(
    i: Optional[CalcodeRk4IntegratorV1], r: Optional[CalcodeRk4ResultV1]
) -> int:
    """static int allocate_result_v1(CalcodeRk4IntegratorV1 *i, CalcodeRk4ResultV1 *r);"""
    if i is None or r is None:
        return 0

    calcode_rk4_result_free_v1(r)

    if not i.config.store_trajectory:
        r.state_dimension = i.dimension
        return 1

    n = i.config.steps
    d = i.dimension

    r.times = [0.0] * n
    r.states = [0.0] * (n * d)

    r.state_dimension = i.dimension

    return 1


def _rhs_eval(
    i: CalcodeRk4IntegratorV1,
    t: float,
    state: List[float],
    derivative: List[float],
    base: CalcodeStateRhsContextV1,
) -> int:
    """static int rhs_eval_v1(const CalcodeRk4IntegratorV1 *i, double t,
    const double *state, double *derivative, const CalcodeStateRhsContextV1 *base);"""
    c = CalcodeStateRhsContextV1()
    c.t = t
    c.state = state
    c.state_dimension = i.dimension
    c.parameters = base.parameters
    c.parameter_count = base.parameter_count

    return calcode_state_rhs_eval_v1(i.rhs, c, derivative)


def _rk4_step(
    i: CalcodeRk4IntegratorV1,
    t: float,
    h: float,
    state: List[float],
    base: CalcodeStateRhsContextV1,
) -> int:
    """static int rk4_step_v1(CalcodeRk4IntegratorV1 *i, double t, double h,
    double *state, const CalcodeStateRhsContextV1 *base);"""
    n = i.dimension

    if not _rhs_eval(i, t, state, i.k1, base):
        return 0

    for j in range(n):
        i.work[j] = state[j] + 0.5 * h * i.k1[j]

    if not _rhs_eval(i, t + 0.5 * h, i.work, i.k2, base):
        return 0

    for j in range(n):
        i.work[j] = state[j] + 0.5 * h * i.k2[j]

    if not _rhs_eval(i, t + 0.5 * h, i.work, i.k3, base):
        return 0

    for j in range(n):
        i.work[j] = state[j] + h * i.k3[j]

    if not _rhs_eval(i, t + h, i.work, i.k4, base):
        return 0

    for j in range(n):
        state[j] += (h / 6.0) * (
            i.k1[j] + 2.0 * i.k2[j] + 2.0 * i.k3[j] + i.k4[j]
        )

        if not math.isfinite(state[j]):
            return 0

    return 1


def calcode_rk4_integrate_v1(
    i: Optional[CalcodeRk4IntegratorV1],
    context: Optional[CalcodeStateRhsContextV1],
    result: Optional[CalcodeRk4ResultV1],
) -> int:
    """int calcode_rk4_integrate_v1(CalcodeRk4IntegratorV1 *integrator,
    const CalcodeStateRhsContextV1 *context, CalcodeRk4ResultV1 *result);"""
    if i is None or context is None or result is None:
        return 0

    if not i.valid or i.rhs is None:
        return 0

    if context.state is None:
        return 0

    if context.state_dimension != i.dimension:
        _diagnostic_i(i, "initial context dimension does not match RHS")
        return 0

    if not _allocate_result(i, result):
        return 0

    for j in range(i.dimension):
        i.initial[j] = context.state[j]

    t = i.config.t0
    h = i.config.dt

    state = [i.initial[j] for j in range(i.dimension)]

    if i.config.store_trajectory:
        result.times[0] = t

        for j in range(i.dimension):
            result.states[j] = state[j]

    result.steps_completed = 1

    for step in range(1, i.config.steps):
        # The configured dt is the requested nominal step. The final step
        # is shortened when t1 is not exactly reached by an integer number
        # of nominal steps.
        remaining = i.config.t1 - t

        actual_h = h

        if (h > 0.0 and remaining < h) or (h < 0.0 and remaining > h):
            actual_h = remaining

        if actual_h == 0.0:
            break

        if not _rk4_step(i, t, actual_h, state, context):
            _diagnostic_i(i, "RHS evaluation failed during RK4 integration")
            return 0

        t += actual_h

        # Avoid tiny floating-point drift around the requested endpoint.
        if abs(t - i.config.t1) <= 1e-14 * (1.0 + abs(i.config.t1)):
            t = i.config.t1

        if i.config.store_trajectory:
            result.times[step] = t

            base_idx = step * i.dimension
            for j in range(i.dimension):
                result.states[base_idx + j] = state[j]

        result.steps_completed = step + 1

        if t == i.config.t1:
            break

    result.final_time = t
    result.success = 1

    i.diagnostic = ""

    return 1
