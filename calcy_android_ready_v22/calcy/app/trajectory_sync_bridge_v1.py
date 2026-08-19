"""trajectory_sync_bridge.py -- NEW INTEGRATION CODE, NOT a C port.

Unlike every other module in this package, there is no
`calcode_trajectory_sync_bridge.c/.h` this file is ported from. It closes
a real gap identified while mapping the dependency graph: nothing in this
tree builds a `CalcodeSyncTrajectoryV1` (the object `app/synchronized_analysis_v1.py`
and everything downstream of it -- graph, table, cursor -- actually reads
from) out of a `CalcodeTrajectoryModelV1` (the object the trajectory/3D
pipeline and `odesolution_trajectory_bridge_v1.py` produce).

STATUS: not harness-verified against any C source, because there is none.
Written to the same conventions as the rest of the package (explicit
free-then-init before validating, int-return success/failure, truncate
strings to the same MAX_* caps the sync layer already uses) but should be
treated as ordinary new Python, not as a verified port, until it's been
reviewed against `STATUS_20260817.md` / the real C app to confirm this is
in fact how the two subsystems are meant to connect.

Only reads `model` (time/state/title); never mutates it.
"""

from __future__ import annotations

from typing import Optional

from calcy.app.synchronized_analysis_v1 import (
    CALCODE_SYNC_MAX_COLUMNS_V1,
    CALCODE_SYNC_MAX_LABEL_V1,
    CalcodeSyncTrajectoryV1,
    calcode_sync_trajectory_create_v1,
    calcode_sync_trajectory_free_v1,
    calcode_sync_trajectory_init_v1,
    calcode_sync_trajectory_set_sample_v1,
    calcode_sync_trajectory_set_state_name_v1,
)
from calcy.trajectory.trajectory_model_v1 import CalcodeTrajectoryModelV1


def calcode_sync_trajectory_from_trajectory_model_v1(
    t: Optional[CalcodeSyncTrajectoryV1],
    model: Optional[CalcodeTrajectoryModelV1],
) -> int:
    """Build `t` from an already-populated, valid `model`.

    Returns 1 on success, 0 on failure (mirrors every other builder in
    this package). On failure `t` is left freed/reset, not partially
    populated -- same convention as `calcode_sync_trajectory_create_v1`
    and friends.
    """
    if t is None or model is None:
        return 0

    calcode_sync_trajectory_free_v1(t)
    calcode_sync_trajectory_init_v1(t)

    if not model.valid:
        t.diagnostic = "trajectory model is not valid"
        return 0

    if model.state_dimension < 1 or model.state_dimension > CALCODE_SYNC_MAX_COLUMNS_V1:
        t.diagnostic = (
            f"trajectory model state_dimension {model.state_dimension} "
            f"exceeds sync trajectory's {CALCODE_SYNC_MAX_COLUMNS_V1}-column capacity"
        )
        return 0

    if model.time is None or model.state is None:
        t.diagnostic = "trajectory model has no sample data"
        return 0

    if not calcode_sync_trajectory_create_v1(t, model.sample_count, model.state_dimension):
        t.diagnostic = "unable to create sync trajectory from model dimensions"
        return 0

    dim = model.state_dimension
    for i in range(model.sample_count):
        row = model.state[i * dim: (i + 1) * dim]
        if not calcode_sync_trajectory_set_sample_v1(t, i, model.time[i], row):
            calcode_sync_trajectory_free_v1(t)
            t.diagnostic = f"non-finite sample at index {i}"
            return 0

    # TrajectoryModel doesn't always carry per-state names (e.g. the
    # ODESolution-derived route leaves them unset) -- only set the ones
    # that exist, and let calcode_sync_graph_build_v1's existing
    # "state[N]" fallback handle the rest, exactly as it already does.
    if hasattr(model, "dependent_variable") and model.state_dimension >= 1 and model.dependent_variable:
        calcode_sync_trajectory_set_state_name_v1(t, 0, model.dependent_variable)

    t.title = (model.title or "")[:CALCODE_SYNC_MAX_LABEL_V1 - 1]

    return 1
