"""calcode_trajectory_stats_v1.py -- exact Python port of
calcode_trajectory_stats_v1.c / calcode_trajectory_stats_v1.h.

Original: per-component (min/max + their sample indices, mean, rms)
summary statistics computed over an entire `CalcodeTrajectoryModelV1`.
Used by the 3D/graph views for auto-scaling axes and ranges.

PORT NOTES:

- `components[CALCODE_RK4_MAX_STATE_V1]` (the C's fixed 64-slot
  array) is modeled as a Python list sized to
  `CALCODE_RK4_MAX_STATE_V1`, pre-filled with fresh
  `CalcodeTrajectoryComponentStatsV1()` instances by `init_v1` (C's
  `memset(s, 0, sizeof(*s))` zeroes every slot, not just the
  `dimension` ones that end up meaningfully written) -- only indices
  `[0, dimension)` are ever written by `compute_v1`, matching the C
  exactly.
- `compute_v1` unconditionally calls `init_v1` first (matching the
  C's unconditional reset before validation), then validates in this
  exact order: `stats`/`trajectory` non-None; `trajectory.valid`;
  `trajectory.state is not None`; `trajectory.sample_count > 0`;
  `trajectory.state_dimension > 0`; `trajectory.state_dimension <=
  CALCODE_RK4_MAX_STATE_V1` (64). Any failure sets the same
  diagnostic text and returns 0.
- Per-component min/max and their sample indices are seeded from
  sample 0 (`c.minimum = c.maximum = t.state[j]`, both indices 0),
  then updated with strict `<`/`>` comparisons while scanning
  `i in range(sample_count)` -- reproduced with the same strict
  inequalities (so on a tie, the *earliest* sample index is kept,
  matching the C's non-`<=`/`>=` comparisons).
- `mean`/`rms` use the same running `sum`/`square_sum` accumulation
  and final division by `sample_count` as the C (double-precision
  order of operations preserved: `sum += x` then `square_sum += x*x`
  per iteration, not e.g. `numpy` vectorized sums, so floating-point
  rounding matches bit-for-bit).
- The row-major flat-array indexing `t->state[i*dimension + j]` is
  reproduced identically for indexing into `trajectory.state`.
"""

from __future__ import annotations

import math
from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.numerical.rk4_integrator_v1 import CALCODE_RK4_MAX_STATE_V1
from calcy.trajectory.trajectory_model_v1 import CalcodeTrajectoryModelV1


class CalcodeTrajectoryComponentStatsV1:
    """typedef struct CalcodeTrajectoryComponentStatsV1 { ... }
    CalcodeTrajectoryComponentStatsV1."""
    __slots__ = ("minimum", "maximum", "mean", "rms", "minimum_index", "maximum_index")

    def __init__(self):
        self.minimum = 0.0
        self.maximum = 0.0
        self.mean = 0.0
        self.rms = 0.0
        self.minimum_index = 0
        self.maximum_index = 0


class CalcodeTrajectoryStatsV1:
    """typedef struct CalcodeTrajectoryStatsV1 { ... } CalcodeTrajectoryStatsV1."""
    __slots__ = ("valid", "sample_count", "dimension", "components", "diagnostic")

    def __init__(self):
        self.valid = 0
        self.sample_count = 0
        self.dimension = 0
        self.components = [
            CalcodeTrajectoryComponentStatsV1() for _ in range(CALCODE_RK4_MAX_STATE_V1)
        ]
        self.diagnostic = ""


def _diagnostic(s: Optional[CalcodeTrajectoryStatsV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(CalcodeTrajectoryStatsV1 *s, const char *message);"""
    if s is None:
        return
    text = message if message else "trajectory statistics error"
    s.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_trajectory_stats_init_v1(s: Optional[CalcodeTrajectoryStatsV1]) -> None:
    """void calcode_trajectory_stats_init_v1(CalcodeTrajectoryStatsV1 *stats);"""
    if s is None:
        return

    s.valid = 0
    s.sample_count = 0
    s.dimension = 0
    s.components = [
        CalcodeTrajectoryComponentStatsV1() for _ in range(CALCODE_RK4_MAX_STATE_V1)
    ]
    s.diagnostic = ""


def calcode_trajectory_stats_compute_v1(
    s: Optional[CalcodeTrajectoryStatsV1], t: Optional[CalcodeTrajectoryModelV1]
) -> int:
    """int calcode_trajectory_stats_compute_v1(CalcodeTrajectoryStatsV1 *stats,
    const CalcodeTrajectoryModelV1 *trajectory);"""
    if s is None or t is None:
        return 0

    calcode_trajectory_stats_init_v1(s)

    if (
        not t.valid
        or t.state is None
        or t.sample_count <= 0
        or t.state_dimension <= 0
        or t.state_dimension > CALCODE_RK4_MAX_STATE_V1
    ):
        _diagnostic(s, "invalid trajectory model")
        return 0

    s.sample_count = t.sample_count
    s.dimension = t.state_dimension

    for j in range(s.dimension):
        c = s.components[j]

        c.minimum = t.state[j]
        c.maximum = t.state[j]

        c.minimum_index = 0
        c.maximum_index = 0

        total = 0.0
        square_total = 0.0

        for i in range(s.sample_count):
            x = t.state[i * s.dimension + j]

            if x < c.minimum:
                c.minimum = x
                c.minimum_index = i

            if x > c.maximum:
                c.maximum = x
                c.maximum_index = i

            total += x
            square_total += x * x

        c.mean = total / float(s.sample_count)
        c.rms = math.sqrt(square_total / float(s.sample_count))

    s.valid = 1
    s.diagnostic = ""

    return 1
