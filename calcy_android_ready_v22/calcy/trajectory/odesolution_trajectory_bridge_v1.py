"""calcode_odesolution_trajectory_bridge_v1.py -- exact Python port of
calcode_odesolution_trajectory_bridge_v1.c / .h.

Original: converts Calcauchy's canonical `ODESolution` storage
(`x[i]`, `y[state_dimension][i]`) into the CALCODE shared trajectory
representation (`CalcodeTrajectoryModelV1`: `time[i]`,
`state[i*state_dimension + j]`). A pure representation-conversion
adapter -- it does not integrate, solve, or modify the `ODESolution`.

PORT NOTES:

- Unconditionally calls `calcode_trajectory_model_free_v1` then
  `calcode_trajectory_model_init_v1` first, matching the C's
  unconditional destination reset before validation (same convention
  as `calcode_trajectory_model_from_result_v1`).
- Validates, in this exact order: `model`/`solution` non-None;
  `solution.ok`; `solution.npts >= 2`; `solution.npts <=
  ODESOL_MAXPTS`; `solution.neqns` in `(0, ODESYS_MAX_EQNS]`. Each
  failure sets the same diagnostic text and returns 0.
- `model.time`/`model.state` are Python lists standing in for the
  C's `malloc`'d buffers; since Python list allocation of this size
  cannot practically fail, the C's "unable to allocate" failure path
  is unreachable here (documented, not silently dropped -- same
  convention used in the sibling `calcode_trajectory_rhs_v1.py` port
  for its own allocate function).
- The conversion loop reproduces `solution.y[j][i] ->
  model.state[i*neqns + j]` (a transpose from Calcauchy's
  column-major-by-equation layout to CALCODE's row-major-by-sample
  layout) exactly, iterating `i` outer / `j` inner as the C does.
- `t0`/`t1` are read from `model.time[0]` /
  `model.time[sample_count - 1]`; `dt_nominal` is set from
  `time[1] - time[0]` -- guarded by `sample_count >= 2`, which is
  always true here since `npts < 2` was already rejected above
  (reproduced anyway, matching the C's redundant-but-present check).
- On success, three fixed metadata entries are written via
  `calcode_trajectory_model_metadata_v1`, in this order:
  `"integrator" -> "Calcauchy ODESolution"`, `"representation" ->
  "shared trajectory"`, `"state_layout" -> "row-major
  [sample][state]"` -- deliberately *not* inventing any
  equation/variable/parameter semantics, matching the C's comment
  and behavior (title/source_equation/independent_variable/
  dependent_variable/derivative_order/parameter_* all stay at their
  init_v1 defaults).
- `valid = 1` and `diagnostic` cleared to `""` at the very end,
  matching the C's `model->diagnostic[0] = '\\0';` placement after
  `model->valid = 1;`.
"""

from __future__ import annotations

from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.trajectory.trajectory_model_v1 import (
    CalcodeTrajectoryModelV1,
    calcode_trajectory_model_init_v1,
    calcode_trajectory_model_free_v1,
    calcode_trajectory_model_metadata_v1,
)
from calcy.core.odesolution import ODESolution, ODESOL_MAXPTS
from calcy.core.odesys import ODESYS_MAX_EQNS


def _diagnostic(model: Optional[CalcodeTrajectoryModelV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(CalcodeTrajectoryModelV1 *model, const char *message);"""
    if model is None:
        return
    text = message if message else "ODESolution trajectory bridge error"
    model.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_trajectory_model_from_odesolution_v1(
    model: Optional[CalcodeTrajectoryModelV1],
    solution: Optional[ODESolution],
) -> int:
    """int calcode_trajectory_model_from_odesolution_v1(CalcodeTrajectoryModelV1 *model,
    const ODESolution *solution);"""
    if model is None or solution is None:
        return 0

    calcode_trajectory_model_free_v1(model)
    calcode_trajectory_model_init_v1(model)

    if not solution.ok:
        _diagnostic(model, "Calcauchy ODESolution is not marked usable")
        return 0

    if solution.npts < 2:
        _diagnostic(model, "Calcauchy ODESolution contains fewer than two samples")
        return 0

    if solution.npts > ODESOL_MAXPTS:
        _diagnostic(model, "Calcauchy ODESolution exceeds storage capacity")
        return 0

    if solution.neqns <= 0 or solution.neqns > ODESYS_MAX_EQNS:
        _diagnostic(model, "Calcauchy ODESolution has an invalid state dimension")
        return 0

    model.sample_count = solution.npts
    model.state_dimension = solution.neqns

    model.time = [0.0] * model.sample_count
    model.state = [0.0] * (model.sample_count * model.state_dimension)

    # C's malloc-failure path (frees, sets an "unable to allocate"
    # diagnostic, returns 0) is unreachable here -- see PORT NOTES.

    for i in range(solution.npts):
        model.time[i] = solution.x[i]

        for j in range(solution.neqns):
            model.state[i * solution.neqns + j] = solution.y[j][i]

    model.t0 = model.time[0]
    model.t1 = model.time[model.sample_count - 1]

    if model.sample_count >= 2:
        model.dt_nominal = model.time[1] - model.time[0]

    calcode_trajectory_model_metadata_v1(model, "integrator", "Calcauchy ODESolution")
    calcode_trajectory_model_metadata_v1(model, "representation", "shared trajectory")
    calcode_trajectory_model_metadata_v1(model, "state_layout", "row-major [sample][state]")

    model.valid = 1
    model.diagnostic = ""

    return 1
