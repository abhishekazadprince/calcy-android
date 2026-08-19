"""calcode_graph_cursor_motion_v1.py -- Python port of
calcode_graph_cursor_motion_v1.c / calcode_graph_cursor_motion_v1.h.

Drag/hover motion state machine layered on top of
`calcode_graph_cursor_bridge_v1`'s pick contract: `begin` starts a drag
(and immediately performs a pick), `move` re-picks only while dragging
and skips work entirely when the pointer hasn't moved, `end` simply
clears the dragging flag (state otherwise untouched, matching the C).

PORT NOTES:

- `move_v1`'s early-out `if (local_x == motion->last_x && local_y ==
  motion->last_y) return 1;` is reproduced exactly: on a no-op move the
  function returns success without touching `motion->result` or
  `selection_changed` at all -- not even resetting `selection_changed`
  to 0.
- `begin_v1` always calls `motion_init_v1` first (full reset, including
  `sample_index = -1`), then only sets `dragging`/`last_x`/`last_y`/
  `selection_changed`/`sample_index` if the pick succeeds; the C leaves
  `motion->result` as the zeroed struct from init on pick failure,
  reproduced here the same way since `_clear_result_v1`-equivalent
  state is what `CalcodeGraphCursorResultV1()` already is.
- `motion.diagnostic` on `begin_v1` failure copies `bridge->diagnostic`
  if the bridge pointer itself is non-null, else the literal string
  "graph cursor bridge unavailable" -- reproduced with the same
  null-check-first ordering (not `bridge.diagnostic if bridge else ...`
  collapsed some other way).
"""

from __future__ import annotations

from typing import Optional

from calcy.app.synchronized_analysis_v1 import CalcodeSyncAnalysisV1
from calcy.graph.sync_opengl2d_bridge_v1 import CalcodeSyncOpenGL2DBridgeV1
from calcy.graph.graph_cursor_bridge_v1 import (
    CalcodeGraphCursorBridgeV1,
    CalcodeGraphCursorResultV1,
    calcode_graph_cursor_bridge_pick_v1,
)


class CalcodeGraphCursorMotionV1:
    """typedef struct CalcodeGraphCursorMotionV1 { ... }"""
    __slots__ = (
        "dragging", "last_x", "last_y",
        "selection_changed", "sample_index",
        "result",
        "diagnostic",
    )

    def __init__(self) -> None:
        self.dragging = 0
        self.last_x = 0
        self.last_y = 0
        self.selection_changed = 0
        self.sample_index = -1
        self.result = CalcodeGraphCursorResultV1()
        self.diagnostic = ""


def _zero_result() -> CalcodeGraphCursorResultV1:
    """A raw `memset(&result, 0, sizeof(result))` -- NOT the same as the
    bridge's `clear_result_v1()`, which additionally sets sample_index,
    left_sample and right_sample to -1. `motion_init_v1` in the real C
    only memsets the whole `CalcodeGraphCursorMotionV1` (which zeroes
    `result` along with everything else) and then separately writes
    `motion->result.sample_index = -1` -- it does NOT touch
    `left_sample`/`right_sample`, which are therefore left at 0, not -1.
    This distinction is reproduced exactly (see the bit-exact diff
    against the C harness that caught this)."""
    r = CalcodeGraphCursorResultV1()
    r.sample_index = 0
    r.left_sample = 0
    r.right_sample = 0
    return r


def calcode_graph_cursor_motion_init_v1(motion: Optional[CalcodeGraphCursorMotionV1]) -> None:
    """void calcode_graph_cursor_motion_init_v1(CalcodeGraphCursorMotionV1 *motion);"""
    if motion is None:
        return

    # memset(motion, 0, sizeof(*motion));
    motion.dragging = 0
    motion.last_x = 0
    motion.last_y = 0
    motion.selection_changed = 0
    motion.sample_index = 0
    motion.result = _zero_result()
    motion.diagnostic = ""

    motion.sample_index = -1
    motion.result.sample_index = -1


def calcode_graph_cursor_motion_begin_v1(
    motion: Optional[CalcodeGraphCursorMotionV1],
    bridge: Optional[CalcodeGraphCursorBridgeV1],
    graph: Optional[CalcodeSyncOpenGL2DBridgeV1],
    analysis: Optional[CalcodeSyncAnalysisV1],
    local_x: int,
    local_y: int,
) -> int:
    """int calcode_graph_cursor_motion_begin_v1(...);"""
    if motion is None:
        return 0

    calcode_graph_cursor_motion_init_v1(motion)

    result = calcode_graph_cursor_bridge_pick_v1(bridge, graph, analysis, local_x, local_y)
    if result is None:
        motion.diagnostic = bridge.diagnostic if bridge is not None else "graph cursor bridge unavailable"
        return 0

    motion.result = result
    motion.dragging = 1
    motion.last_x = local_x
    motion.last_y = local_y
    motion.selection_changed = 1
    motion.sample_index = motion.result.sample_index

    return 1


def calcode_graph_cursor_motion_move_v1(
    motion: Optional[CalcodeGraphCursorMotionV1],
    bridge: Optional[CalcodeGraphCursorBridgeV1],
    graph: Optional[CalcodeSyncOpenGL2DBridgeV1],
    analysis: Optional[CalcodeSyncAnalysisV1],
    local_x: int,
    local_y: int,
) -> int:
    """int calcode_graph_cursor_motion_move_v1(...);"""
    if motion is None or not motion.dragging:
        return 0

    if local_x == motion.last_x and local_y == motion.last_y:
        return 1

    result = calcode_graph_cursor_bridge_pick_v1(bridge, graph, analysis, local_x, local_y)
    if result is None:
        return 0

    motion.last_x = local_x
    motion.last_y = local_y

    if result.sample_index != motion.sample_index:
        motion.selection_changed = 1
        motion.sample_index = result.sample_index
    else:
        motion.selection_changed = 0

    motion.result = result

    return 1


def calcode_graph_cursor_motion_end_v1(motion: Optional[CalcodeGraphCursorMotionV1]) -> None:
    """void calcode_graph_cursor_motion_end_v1(CalcodeGraphCursorMotionV1 *motion);"""
    if motion is None:
        return

    motion.dragging = 0
