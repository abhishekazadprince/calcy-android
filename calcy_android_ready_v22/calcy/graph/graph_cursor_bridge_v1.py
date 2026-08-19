"""calcode_graph_cursor_bridge_v1.py -- Python port of
calcode_graph_cursor_bridge_v1.c / calcode_graph_cursor_bridge_v1.h.

Graph -> mathematical cursor bridge. The graph is treated as an
observation of the trajectory, not as an independent simulation. A
pointer position is converted into a trajectory sample through the
existing graph picking contract (`calcode_sync_opengl2d_bridge_pick_v1`)
and then written into the common synchronized analysis cursor.

Optional interpolation metadata is returned separately. The current
synchronized state remains an exact stored sample (`interpolated` is
always 0 in this file -- reproduced exactly as the C leaves it, the C
never sets it to anything else either).

PORT NOTES:

- `calcode_graph_cursor_bridge_configure_v1`'s threshold-normalization
  logic is reproduced exactly, including its slightly unusual first
  branch: `if (max_pick_distance_squared < 0.0 && !isnan(...))` sets the
  threshold to the sentinel -1.0 (this is a no-op vs. what init_v1
  already set, since init_v1 always sets -1.0 first). Any NaN threshold
  falls through to the `isfinite` check, which is false for NaN, so NaN
  is rejected via the diagnostic/return-0 path. Any finite non-negative
  value is accepted as-is. `+inf`/`-inf` are also rejected by `isfinite`.
- `calcode_graph_cursor_bridge_pick_v1` and `_select_sample_v1` both
  populate a local result struct and only commit it to `bridge->last`
  and the caller's `result` out-param on success -- ported the same way
  via a fresh `CalcodeGraphCursorResultV1` returned only on success.
- Out-params (`CalcodeGraphCursorResultV1 *result`) become an
  `Optional[CalcodeGraphCursorResultV1]` return value: `None` on
  failure, populated instance on success (matching the C's convention
  that `*result` is only ever written when the function returns 1).
"""

from __future__ import annotations

import math
from typing import Optional

from calcy.app.synchronized_analysis_v1 import (
    CalcodeSyncAnalysisV1,
    calcode_sync_analysis_set_index_v1,
)
from calcy.graph.sync_opengl2d_bridge_v1 import (
    CalcodeSyncOpenGL2DBridgeV1,
    calcode_sync_opengl2d_bridge_pick_v1,
)


class CalcodeGraphCursorResultV1:
    """typedef struct CalcodeGraphCursorResultV1 { ... }"""
    __slots__ = (
        "valid", "picked", "sample_index",
        "interpolated", "left_sample", "right_sample",
        "requested_x", "requested_y",
        "sample_x", "sample_y",
        "distance_squared",
        "requested_time", "sample_time",
        "diagnostic",
    )

    def __init__(self) -> None:
        self.valid = 0
        self.picked = 0
        self.sample_index = -1
        self.interpolated = 0
        self.left_sample = -1
        self.right_sample = -1
        self.requested_x = 0.0
        self.requested_y = 0.0
        self.sample_x = 0.0
        self.sample_y = 0.0
        self.distance_squared = 0.0
        self.requested_time = 0.0
        self.sample_time = 0.0
        self.diagnostic = ""


class CalcodeGraphCursorBridgeV1:
    """typedef struct CalcodeGraphCursorBridgeV1 { ... }"""
    __slots__ = (
        "valid",
        "prefer_interpolation", "update_table_selection",
        "max_pick_distance_squared",
        "last",
        "diagnostic",
    )

    def __init__(self) -> None:
        self.valid = 0
        self.prefer_interpolation = 0
        self.update_table_selection = 0
        self.max_pick_distance_squared = 0.0
        self.last = CalcodeGraphCursorResultV1()
        self.diagnostic = ""


def _diagnostic_v1(bridge: Optional[CalcodeGraphCursorBridgeV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(...);"""
    if bridge is None:
        return
    bridge.diagnostic = message if message is not None else "graph cursor bridge error"


def _clear_result_v1() -> CalcodeGraphCursorResultV1:
    """static void clear_result_v1(CalcodeGraphCursorResultV1 *result);
    (returns a freshly-cleared result instead of mutating in place)"""
    return CalcodeGraphCursorResultV1()


def calcode_graph_cursor_bridge_init_v1(bridge: Optional[CalcodeGraphCursorBridgeV1]) -> None:
    """void calcode_graph_cursor_bridge_init_v1(CalcodeGraphCursorBridgeV1 *bridge);"""
    if bridge is None:
        return

    bridge.valid = 0
    bridge.prefer_interpolation = 0
    bridge.update_table_selection = 0
    bridge.max_pick_distance_squared = 0.0
    bridge.last = _clear_result_v1()
    bridge.diagnostic = ""

    bridge.prefer_interpolation = 0
    bridge.update_table_selection = 1

    # Negative means "no explicit threshold".
    bridge.max_pick_distance_squared = -1.0


def calcode_graph_cursor_bridge_configure_v1(
    bridge: Optional[CalcodeGraphCursorBridgeV1],
    max_pick_distance_squared: float,
    prefer_interpolation: int,
    update_table_selection: int,
) -> int:
    """int calcode_graph_cursor_bridge_configure_v1(...);"""
    if bridge is None:
        return 0

    calcode_graph_cursor_bridge_init_v1(bridge)

    if max_pick_distance_squared < 0.0 and not math.isnan(max_pick_distance_squared):
        bridge.max_pick_distance_squared = -1.0
    elif math.isfinite(max_pick_distance_squared):
        bridge.max_pick_distance_squared = max_pick_distance_squared
    else:
        _diagnostic_v1(bridge, "invalid graph pick threshold")
        return 0

    bridge.prefer_interpolation = 1 if prefer_interpolation else 0
    bridge.update_table_selection = 1 if update_table_selection else 0
    bridge.valid = 1

    return 1


def calcode_graph_cursor_bridge_select_sample_v1(
    bridge: Optional[CalcodeGraphCursorBridgeV1],
    analysis: Optional[CalcodeSyncAnalysisV1],
    sample_index: int,
) -> Optional[CalcodeGraphCursorResultV1]:
    """int calcode_graph_cursor_bridge_select_sample_v1(..., CalcodeGraphCursorResultV1 *result);
    Python: returns the populated result on success, None on failure
    (matching the C's `*result` only being written on return 1)."""
    if bridge is None or not bridge.valid or analysis is None or not analysis.valid:
        if bridge is not None:
            _diagnostic_v1(bridge, "invalid graph cursor selection input")
        return None

    if sample_index < 0 or sample_index >= analysis.trajectory.sample_count:
        _diagnostic_v1(bridge, "sample index outside trajectory")
        return None

    local = _clear_result_v1()

    sample = analysis.trajectory.samples[sample_index]

    local.valid = 1
    local.picked = 1
    local.sample_index = sample_index

    local.sample_time = sample.t
    local.requested_time = sample.t

    if analysis.trajectory.state_dimension > 0:
        local.sample_x = sample.state[0]

    if analysis.trajectory.state_dimension > 1:
        local.sample_y = sample.state[1]

    if not calcode_sync_analysis_set_index_v1(analysis, sample_index):
        _diagnostic_v1(bridge, "synchronized analysis rejected sample")
        return None

    bridge.last = local

    return local


def calcode_graph_cursor_bridge_pick_v1(
    bridge: Optional[CalcodeGraphCursorBridgeV1],
    graph: Optional[CalcodeSyncOpenGL2DBridgeV1],
    analysis: Optional[CalcodeSyncAnalysisV1],
    local_x: int,
    local_y: int,
) -> Optional[CalcodeGraphCursorResultV1]:
    """int calcode_graph_cursor_bridge_pick_v1(..., CalcodeGraphCursorResultV1 *result);
    Python: returns the populated result on success, None on failure."""
    if (bridge is None or not bridge.valid or graph is None
            or analysis is None or not analysis.valid):
        if bridge is not None:
            _diagnostic_v1(bridge, "invalid graph pick input")
        return None

    local = _clear_result_v1()

    # The graph bridge remains the authority for converting a local pixel
    # position into a mathematical trajectory pick. This avoids duplicating
    # graph scaling and coordinate transformation here.
    ok, sample_index, requested_x, requested_y = calcode_sync_opengl2d_bridge_pick_v1(
        graph, analysis, local_x, local_y
    )
    if not ok:
        _diagnostic_v1(bridge, "graph bridge could not pick trajectory")
        return None

    if sample_index < 0 or sample_index >= analysis.trajectory.sample_count:
        _diagnostic_v1(bridge, "graph bridge returned invalid sample")
        return None

    sample = analysis.trajectory.samples[sample_index]

    sx = 0.0
    sy = 0.0

    if analysis.trajectory.state_dimension > 0:
        sx = sample.state[0]

    if analysis.trajectory.state_dimension > 1:
        sy = sample.state[1]

    dx = requested_x - sx
    dy = requested_y - sy

    distance_squared = dx * dx + dy * dy

    if (bridge.max_pick_distance_squared >= 0.0
            and distance_squared > bridge.max_pick_distance_squared):
        _diagnostic_v1(bridge, "nearest trajectory sample exceeds pick threshold")
        return None

    local.valid = 1
    local.picked = 1
    local.sample_index = sample_index

    local.requested_x = requested_x
    local.requested_y = requested_y

    local.sample_x = sx
    local.sample_y = sy

    local.distance_squared = distance_squared

    local.sample_time = sample.t
    local.requested_time = sample.t

    # Exact-sample synchronization is the default.
    #
    # Interpolation is deliberately represented as metadata rather than
    # silently changing the common cursor to a synthetic sample. This keeps
    # the trajectory index and numerical table row exact.
    local.interpolated = 0

    if not calcode_sync_analysis_set_index_v1(analysis, sample_index):
        _diagnostic_v1(bridge, "failed to update common cursor")
        return None

    bridge.last = local

    return local
