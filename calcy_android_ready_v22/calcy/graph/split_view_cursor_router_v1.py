"""calcode_split_view_cursor_router_v1.py -- exact Python port of
calcode_split_view_cursor_router_v1.c / calcode_split_view_cursor_router_v1.h.

Original: routes a graph-pick or table-row-pick interaction event into a
CalcodeCursorRouteResultV1, using the synchronized analysis layer to move
the shared cursor and read back the resulting sample's world coordinates
for the graph's configured x/y columns. Part of section 4 ("Numerical
Table & Unified Cross-View Sync") of REMAINING_PYTHON_PORT_WORK.md.

Depends on: calcode_split_view_compositor_v1 (CalcodeViewKindV1 enum only),
calcode_synchronized_analysis_v1 (CalcodeSyncAnalysisV1 and friends).

PORT STATUS: harness-verified bit-exact against a compiled `gcc -O2` build
of the real C, diffed field-by-field
(verification_harnesses/harness_split_view_cursor_router.c/.py).
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional

from calcy.graph.split_view_compositor_v1 import CalcodeViewKindV1
from calcy.app.synchronized_analysis_v1 import (
    CalcodeSyncAnalysisV1,
    calcode_sync_analysis_set_index_v1,
    calcode_sync_analysis_current_sample_v1,
)


class CalcodeCursorRouteActionV1(IntEnum):
    CALCODE_CURSOR_ROUTE_NONE_V1 = 0
    CALCODE_CURSOR_ROUTE_SELECT_SAMPLE_V1 = 1
    CALCODE_CURSOR_ROUTE_SELECT_TIME_V1 = 2
    CALCODE_CURSOR_ROUTE_VIEW_ONLY_V1 = 3


class CalcodeCursorRouteResultV1:
    __slots__ = (
        "handled",
        "action",
        "source_view",
        "sample_index",
        "requested_time",
        "world_x",
        "world_y",
        "diagnostic",
    )

    def __init__(self) -> None:
        self.handled = 0
        self.action = CalcodeCursorRouteActionV1.CALCODE_CURSOR_ROUTE_NONE_V1
        self.source_view = CalcodeViewKindV1.CALCODE_VIEW_NONE_V1
        self.sample_index = 0
        self.requested_time = 0.0
        self.world_x = 0.0
        self.world_y = 0.0
        self.diagnostic = ""


def calcode_split_view_route_result_init_v1(
    r: Optional[CalcodeCursorRouteResultV1],
) -> None:
    if r is None:
        return

    r.handled = 0
    r.action = CalcodeCursorRouteActionV1.CALCODE_CURSOR_ROUTE_NONE_V1
    r.source_view = CalcodeViewKindV1.CALCODE_VIEW_NONE_V1
    r.sample_index = 0
    r.requested_time = 0.0
    r.world_x = 0.0
    r.world_y = 0.0
    r.diagnostic = ""


def calcode_split_view_route_graph_pick_v1(
    r: Optional[CalcodeCursorRouteResultV1],
    a: Optional[CalcodeSyncAnalysisV1],
    sample_index: int,
) -> int:
    if r is None or a is None or not a.valid:
        return 0

    calcode_split_view_route_result_init_v1(r)

    if not calcode_sync_analysis_set_index_v1(a, sample_index):
        r.diagnostic = "graph sample index rejected"
        return 0

    s = calcode_sync_analysis_current_sample_v1(a)

    if s is None:
        return 0

    r.handled = 1
    r.action = CalcodeCursorRouteActionV1.CALCODE_CURSOR_ROUTE_SELECT_SAMPLE_V1
    r.source_view = CalcodeViewKindV1.CALCODE_VIEW_GRAPH_2D_V1
    r.sample_index = sample_index
    r.requested_time = a.cursor.requested_time

    if 0 <= a.graph.x_column < s.state_dimension:
        r.world_x = s.state[a.graph.x_column]

    if 0 <= a.graph.y_column < s.state_dimension:
        r.world_y = s.state[a.graph.y_column]

    return 1


def calcode_split_view_route_table_row_v1(
    r: Optional[CalcodeCursorRouteResultV1],
    a: Optional[CalcodeSyncAnalysisV1],
    row: int,
) -> int:
    if r is None or a is None or not a.valid:
        return 0

    calcode_split_view_route_result_init_v1(r)

    if not calcode_sync_analysis_set_index_v1(a, row):
        r.diagnostic = "table row rejected"
        return 0

    s = calcode_sync_analysis_current_sample_v1(a)

    if s is None:
        return 0

    r.handled = 1
    r.action = CalcodeCursorRouteActionV1.CALCODE_CURSOR_ROUTE_SELECT_SAMPLE_V1
    r.source_view = CalcodeViewKindV1.CALCODE_VIEW_TABLE_V1
    r.sample_index = row
    r.requested_time = s.t

    if 0 <= a.graph.x_column < s.state_dimension:
        r.world_x = s.state[a.graph.x_column]

    if 0 <= a.graph.y_column < s.state_dimension:
        r.world_y = s.state[a.graph.y_column]

    return 1
