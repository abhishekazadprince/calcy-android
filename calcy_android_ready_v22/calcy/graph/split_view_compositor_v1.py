"""calcode_split_view_compositor_v1.py -- exact Python port of
calcode_split_view_compositor_v1.c / calcode_split_view_compositor_v1.h.

Original: pure layout/geometry/hit-test math for the 3-pane split view
(2D graph top-left, 3D scene top-right, table across the bottom) plus
divider-drag interaction state. No GL/rendering, no math solving --
part of section 4 ("Numerical Table & Unified Cross-View Sync") of
`REMAINING_PYTHON_PORT_WORK.md`. No calcode_* dependency.

PORT STATUS: harness-verified bit-exact against a compiled `gcc -O2`
build of the real C, diffed field-by-field
(`verification_harnesses/harness_split_view_compositor.c/.py`).

PORT NOTES:
- All arithmetic here is integer (window pixels), matching C's `int`
  semantics via Python's arbitrary-precision ints -- since the C never
  overflows 32-bit int at any window size used in the harness, no
  wraparound handling was needed.
- `int(x - divider_x)` truncation-toward-zero in C for a double
  difference: Python's `int()` on a float also truncates toward zero,
  matching C's `(int)` cast exactly (including negative values).
- `calcode_split_view_compositor_configure_v1` calls
  `calcode_split_view_compositor_init_v1` first (full reset), matching
  the C's re-init-then-configure sequencing exactly.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional


class CalcodeViewKindV1(IntEnum):
    CALCODE_VIEW_NONE_V1 = 0
    CALCODE_VIEW_GRAPH_2D_V1 = 1
    CALCODE_VIEW_SCENE_3D_V1 = 2
    CALCODE_VIEW_TABLE_V1 = 3


class CalcodeViewportV1:
    __slots__ = ("x", "y", "width", "height", "visible")

    def __init__(self) -> None:
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.visible = 0

    def copy_from(self, other: "CalcodeViewportV1") -> None:
        self.x = other.x
        self.y = other.y
        self.width = other.width
        self.height = other.height
        self.visible = other.visible

    def reset(self) -> None:
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.visible = 0


class CalcodeSplitViewLayoutV1:
    __slots__ = (
        "window_width", "window_height",
        "divider_x", "horizontal_divider_y",
        "top_height", "bottom_height",
        "graph_2d", "scene_3d", "table",
        "minimum_top_width", "minimum_bottom_height",
        "minimum_graph_width", "minimum_scene_width",
        "diagnostic", "valid",
    )

    def __init__(self) -> None:
        self.window_width = 0
        self.window_height = 0
        self.divider_x = 0
        self.horizontal_divider_y = 0
        self.top_height = 0
        self.bottom_height = 0
        self.graph_2d = CalcodeViewportV1()
        self.scene_3d = CalcodeViewportV1()
        self.table = CalcodeViewportV1()
        self.minimum_top_width = 0
        self.minimum_bottom_height = 0
        self.minimum_graph_width = 0
        self.minimum_scene_width = 0
        self.diagnostic = ""
        self.valid = 0

    def reset(self) -> None:
        self.window_width = 0
        self.window_height = 0
        self.divider_x = 0
        self.horizontal_divider_y = 0
        self.top_height = 0
        self.bottom_height = 0
        self.graph_2d.reset()
        self.scene_3d.reset()
        self.table.reset()
        self.minimum_top_width = 0
        self.minimum_bottom_height = 0
        self.minimum_graph_width = 0
        self.minimum_scene_width = 0
        self.diagnostic = ""
        self.valid = 0


class CalcodeSplitViewPointerV1:
    __slots__ = ("window_x", "window_y", "view", "local_x", "local_y", "inside")

    def __init__(self) -> None:
        self.window_x = 0.0
        self.window_y = 0.0
        self.view = CalcodeViewKindV1.CALCODE_VIEW_NONE_V1
        self.local_x = 0.0
        self.local_y = 0.0
        self.inside = 0


class CalcodeSplitViewCompositorV1:
    __slots__ = (
        "layout", "graph_ratio_percent", "table_height_percent",
        "dragging_vertical_divider", "dragging_horizontal_divider",
        "mouse_captured", "pointer_view", "diagnostic", "valid",
    )

    def __init__(self) -> None:
        self.layout = CalcodeSplitViewLayoutV1()
        self.graph_ratio_percent = 0
        self.table_height_percent = 0
        self.dragging_vertical_divider = 0
        self.dragging_horizontal_divider = 0
        self.mouse_captured = 0
        self.pointer_view = CalcodeViewKindV1.CALCODE_VIEW_NONE_V1
        self.diagnostic = ""
        self.valid = 0


def _clamp_int_v1(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _inside_v1(v: Optional[CalcodeViewportV1], x: float, y: float) -> bool:
    if v is None or not v.visible:
        return False
    return (
        x >= float(v.x)
        and x < float(v.x + v.width)
        and y >= float(v.y)
        and y < float(v.y + v.height)
    )


def _recompute_layout_v1(c: CalcodeSplitViewCompositorV1) -> None:
    l = c.layout

    w = l.window_width
    h = l.window_height

    divider_width = 4
    horizontal_divider = 4

    min_graph = 180
    min_scene = 180
    min_table = 100
    min_top = 220

    if w < min_graph + min_scene + divider_width:
        l.divider_x = w // 2
    else:
        available = w - divider_width
        l.divider_x = (available * c.graph_ratio_percent) // 100

    l.divider_x = _clamp_int_v1(
        l.divider_x, min_graph, w - min_scene - divider_width
    )

    l.top_height = h - (h * c.table_height_percent // 100)

    l.top_height = _clamp_int_v1(
        l.top_height, min_top, h - min_table - horizontal_divider
    )

    l.horizontal_divider_y = l.top_height

    l.bottom_height = h - l.top_height - horizontal_divider

    l.graph_2d.x = 0
    l.graph_2d.y = 0
    l.graph_2d.width = l.divider_x
    l.graph_2d.height = l.top_height
    l.graph_2d.visible = 1

    l.scene_3d.x = l.divider_x + divider_width
    l.scene_3d.y = 0
    l.scene_3d.width = w - l.scene_3d.x
    l.scene_3d.height = l.top_height
    l.scene_3d.visible = 1

    l.table.x = 0
    l.table.y = l.top_height + horizontal_divider
    l.table.width = w
    l.table.height = l.bottom_height
    l.table.visible = 1

    l.minimum_top_width = min_graph + min_scene
    l.minimum_bottom_height = min_table
    l.minimum_graph_width = min_graph
    l.minimum_scene_width = min_scene


def calcode_split_view_compositor_init_v1(
    c: Optional[CalcodeSplitViewCompositorV1],
) -> None:
    if c is None:
        return

    c.layout = CalcodeSplitViewLayoutV1()
    c.graph_ratio_percent = 50
    c.table_height_percent = 24
    c.dragging_vertical_divider = 0
    c.dragging_horizontal_divider = 0
    c.mouse_captured = 0
    c.pointer_view = CalcodeViewKindV1.CALCODE_VIEW_NONE_V1
    c.diagnostic = ""

    c.layout.valid = 0
    c.valid = 0


def calcode_split_view_compositor_configure_v1(
    c: Optional[CalcodeSplitViewCompositorV1],
    window_width: int,
    window_height: int,
) -> int:
    if c is None or window_width <= 0 or window_height <= 0:
        return 0

    calcode_split_view_compositor_init_v1(c)

    c.layout.window_width = window_width
    c.layout.window_height = window_height

    _recompute_layout_v1(c)

    c.layout.valid = 1
    c.valid = 1

    return 1


def calcode_split_view_compositor_resize_v1(
    c: Optional[CalcodeSplitViewCompositorV1],
    window_width: int,
    window_height: int,
) -> int:
    if c is None or not c.valid or window_width <= 0 or window_height <= 0:
        return 0

    c.layout.window_width = window_width
    c.layout.window_height = window_height

    _recompute_layout_v1(c)

    return 1


def calcode_split_view_compositor_set_graph_ratio_v1(
    c: Optional[CalcodeSplitViewCompositorV1],
    ratio_percent: int,
) -> int:
    if c is None or not c.valid:
        return 0

    c.graph_ratio_percent = _clamp_int_v1(ratio_percent, 20, 80)

    _recompute_layout_v1(c)

    return 1


def calcode_split_view_compositor_set_table_height_v1(
    c: Optional[CalcodeSplitViewCompositorV1],
    height_percent: int,
) -> int:
    if c is None or not c.valid:
        return 0

    c.table_height_percent = _clamp_int_v1(height_percent, 15, 45)

    _recompute_layout_v1(c)

    return 1


def calcode_split_view_compositor_hit_test_v1(
    l: Optional[CalcodeSplitViewLayoutV1],
    x: float,
    y: float,
    p: Optional[CalcodeSplitViewPointerV1],
) -> int:
    if l is None or not l.valid or p is None:
        return 0

    p.window_x = 0.0
    p.window_y = 0.0
    p.view = CalcodeViewKindV1.CALCODE_VIEW_NONE_V1
    p.local_x = 0.0
    p.local_y = 0.0
    p.inside = 0

    p.window_x = x
    p.window_y = y

    if _inside_v1(l.graph_2d, x, y):
        p.view = CalcodeViewKindV1.CALCODE_VIEW_GRAPH_2D_V1
        p.local_x = x - l.graph_2d.x
        p.local_y = y - l.graph_2d.y
        p.inside = 1
        return 1

    if _inside_v1(l.scene_3d, x, y):
        p.view = CalcodeViewKindV1.CALCODE_VIEW_SCENE_3D_V1
        p.local_x = x - l.scene_3d.x
        p.local_y = y - l.scene_3d.y
        p.inside = 1
        return 1

    if _inside_v1(l.table, x, y):
        p.view = CalcodeViewKindV1.CALCODE_VIEW_TABLE_V1
        p.local_x = x - l.table.x
        p.local_y = y - l.table.y
        p.inside = 1
        return 1

    p.view = CalcodeViewKindV1.CALCODE_VIEW_NONE_V1
    p.inside = 0

    return 1


def _c_int_cast(x: float) -> int:
    """Mirror C's (int) cast on a double: truncate toward zero."""
    import math
    return math.trunc(x)


def calcode_split_view_compositor_begin_divider_drag_v1(
    c: Optional[CalcodeSplitViewCompositorV1],
    x: float,
    y: float,
) -> int:
    if c is None or not c.valid:
        return 0

    tolerance = 8

    vertical_distance = _c_int_cast(x - float(c.layout.divider_x))
    if vertical_distance < 0:
        vertical_distance = -vertical_distance

    if vertical_distance <= tolerance and y < c.layout.top_height:
        c.dragging_vertical_divider = 1
        c.mouse_captured = 1
        return 1

    horizontal_distance = _c_int_cast(y - float(c.layout.horizontal_divider_y))
    if horizontal_distance < 0:
        horizontal_distance = -horizontal_distance

    if (
        horizontal_distance <= tolerance
        and x >= 0
        and x < c.layout.window_width
    ):
        c.dragging_horizontal_divider = 1
        c.mouse_captured = 1
        return 1

    return 0


def calcode_split_view_compositor_drag_v1(
    c: Optional[CalcodeSplitViewCompositorV1],
    x: float,
    y: float,
) -> int:
    if c is None or not c.valid or not c.mouse_captured:
        return 0

    if c.dragging_vertical_divider:
        available = c.layout.window_width
        if available <= 0:
            return 0

        ratio = _c_int_cast(100.0 * x / float(available))

        return calcode_split_view_compositor_set_graph_ratio_v1(c, ratio)

    if c.dragging_horizontal_divider:
        h = c.layout.window_height
        if h <= 0:
            return 0

        table_percent = _c_int_cast(100.0 * (float(h) - y) / float(h))

        return calcode_split_view_compositor_set_table_height_v1(
            c, table_percent
        )

    return 0


def calcode_split_view_compositor_end_drag_v1(
    c: Optional[CalcodeSplitViewCompositorV1],
) -> None:
    if c is None:
        return

    c.dragging_vertical_divider = 0
    c.dragging_horizontal_divider = 0
    c.mouse_captured = 0


def calcode_split_view_compositor_viewport_v1(
    c: Optional[CalcodeSplitViewCompositorV1],
    view: CalcodeViewKindV1,
    viewport: Optional[CalcodeViewportV1],
) -> int:
    if c is None or not c.valid or viewport is None:
        return 0

    if view == CalcodeViewKindV1.CALCODE_VIEW_GRAPH_2D_V1:
        viewport.copy_from(c.layout.graph_2d)
        return 1

    if view == CalcodeViewKindV1.CALCODE_VIEW_SCENE_3D_V1:
        viewport.copy_from(c.layout.scene_3d)
        return 1

    if view == CalcodeViewKindV1.CALCODE_VIEW_TABLE_V1:
        viewport.copy_from(c.layout.table)
        return 1

    viewport.reset()

    return 0
