"""calcode_split_view_frame_v1.py -- exact Python port of
calcode_split_view_frame_v1.c / calcode_split_view_frame_v1.h.

Original: snapshots a compositor's current viewport layout into a
lightweight per-frame struct (for the render loop to read without
touching the compositor's mutable drag state), plus a point-in-view
hit test against that snapshot. No GL. Depends only on the already-
verified `calcode_split_view_compositor_v1`. Part of section 4 of
`REMAINING_PYTHON_PORT_WORK.md`.

PORT STATUS: harness-verified bit-exact against a compiled `gcc -O2`
build of the real C, diffed field-by-field
(`verification_harnesses/harness_split_view_frame.c/.py`).
"""

from __future__ import annotations

from typing import Optional

from calcy.graph.split_view_compositor_v1 import (
    CalcodeViewportV1,
    CalcodeViewKindV1,
    CalcodeSplitViewCompositorV1,
    calcode_split_view_compositor_viewport_v1,
)


class CalcodeSplitViewFrameV1:
    __slots__ = (
        "frame_width", "frame_height",
        "graph", "scene", "table",
        "graph_active", "scene_active", "table_active",
        "valid",
    )

    def __init__(self) -> None:
        self.frame_width = 0
        self.frame_height = 0
        self.graph = CalcodeViewportV1()
        self.scene = CalcodeViewportV1()
        self.table = CalcodeViewportV1()
        self.graph_active = 0
        self.scene_active = 0
        self.table_active = 0
        self.valid = 0


def calcode_split_view_frame_begin_v1(
    f: Optional[CalcodeSplitViewFrameV1],
    c: Optional[CalcodeSplitViewCompositorV1],
) -> int:
    if f is None or c is None or not c.valid:
        return 0

    f.frame_width = 0
    f.frame_height = 0
    f.graph = CalcodeViewportV1()
    f.scene = CalcodeViewportV1()
    f.table = CalcodeViewportV1()
    f.graph_active = 0
    f.scene_active = 0
    f.table_active = 0
    f.valid = 0

    f.frame_width = c.layout.window_width
    f.frame_height = c.layout.window_height

    if not calcode_split_view_compositor_viewport_v1(
        c, CalcodeViewKindV1.CALCODE_VIEW_GRAPH_2D_V1, f.graph
    ):
        return 0

    if not calcode_split_view_compositor_viewport_v1(
        c, CalcodeViewKindV1.CALCODE_VIEW_SCENE_3D_V1, f.scene
    ):
        return 0

    if not calcode_split_view_compositor_viewport_v1(
        c, CalcodeViewKindV1.CALCODE_VIEW_TABLE_V1, f.table
    ):
        return 0

    f.graph_active = f.graph.visible
    f.scene_active = f.scene.visible
    f.table_active = f.table.visible

    f.valid = 1

    return 1


def _inside(v: Optional[CalcodeViewportV1], x: float, y: float) -> int:
    if v is None or not v.visible:
        return 0

    return int(
        x >= v.x and y >= v.y and x < v.x + v.width and y < v.y + v.height
    )


def calcode_split_view_frame_contains_v1(
    f: Optional[CalcodeSplitViewFrameV1],
    view: CalcodeViewKindV1,
    x: float,
    y: float,
) -> int:
    if f is None or not f.valid:
        return 0

    if view == CalcodeViewKindV1.CALCODE_VIEW_GRAPH_2D_V1:
        return _inside(f.graph, x, y)

    if view == CalcodeViewKindV1.CALCODE_VIEW_SCENE_3D_V1:
        return _inside(f.scene, x, y)

    if view == CalcodeViewKindV1.CALCODE_VIEW_TABLE_V1:
        return _inside(f.table, x, y)

    return 0
