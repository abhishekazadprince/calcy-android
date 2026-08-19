"""calcode_sync_graph_renderer_v1.py -- exact Python port of
calcode_sync_graph_renderer_v1.c / calcode_sync_graph_renderer_v1.h.

Original: pure-math world<->screen coordinate transform for the 2D
graph view (margins, world-space domain, screen-space pixel rect), plus
a convenience lookup that maps a sample index in a `CalcodeSyncGraphV1`
straight to its screen position. No GL/drawing calls -- this is
exactly the kind of "positioning logic, no GL calls" file the project
has already separated out elsewhere (see `calcode_opengl_table_overlay_v1`
and `calcode_opengl2d_camera_v1` in `00_STATUS_AND_PLAN.md`'s
GL-coupling section).

PORT STATUS -- fully portable, only depends on the already-verified
`calcode_synchronized_analysis_v1.py`. NOT YET diffed against a
compiled C binary in this session; a Python-only behavioral harness
is included (`harness_sync_graph_renderer.py`).

PORT NOTES:

- `calcode_sync_graph_screen_to_world_v1`'s `double *x, double *y`
  out-params become a Python return of `(ok, x, y)` in place of the
  C's write-through pointers, following the same pattern already used
  for other multi-output C functions in this project (e.g.
  `calcode_standard_form_compile_v3`'s `(ok, out_system, error)`
  return in `calcode_standard_form_editor_v3.py`).
- The world<->screen transform intentionally flips the Y axis
  (`p->y = bottom - v * (bottom - top)`) because screen Y grows
  downward while mathematical Y grows upward -- preserved exactly,
  comment included.
- `calcode_sync_graph_screen_configure_v1` re-inits the screen first
  (resetting margins to their defaults) before setting the new
  width/height/domain, exactly mirroring the C's call to
  `calcode_sync_graph_screen_init_v1(s)` at the top of the function --
  this means a previously-customized margin is silently reset on every
  reconfigure, which is the original's real behavior, not a port bug.
- `calcode_sync_graph_world_to_screen_v1` rejects non-finite `x`/`y`
  via `isfinite()`; Python's `math.isfinite()` is the direct
  equivalent.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from calcy.app.synchronized_analysis_v1 import CalcodeSyncGraphV1


class CalcodeSyncGraphScreenV1:
    """typedef struct CalcodeSyncGraphScreenV1 { ... }"""
    __slots__ = (
        "width", "height",
        "margin_left", "margin_right", "margin_top", "margin_bottom",
        "x_min", "x_max", "y_min", "y_max",
        "valid",
    )

    def __init__(self):
        self.width = 0
        self.height = 0
        self.margin_left = 0
        self.margin_right = 0
        self.margin_top = 0
        self.margin_bottom = 0
        self.x_min = 0.0
        self.x_max = 0.0
        self.y_min = 0.0
        self.y_max = 0.0
        self.valid = 0


class CalcodeSyncScreenPointV1:
    """typedef struct CalcodeSyncScreenPointV1 { double x; double y; }"""
    __slots__ = ("x", "y")

    def __init__(self):
        self.x = 0.0
        self.y = 0.0


def calcode_sync_graph_screen_init_v1(s: Optional[CalcodeSyncGraphScreenV1]) -> None:
    """void calcode_sync_graph_screen_init_v1(CalcodeSyncGraphScreenV1 *screen);"""
    if s is None:
        return

    # memset(s, 0, sizeof(*s));
    s.width = 0
    s.height = 0
    s.margin_left = 0
    s.margin_right = 0
    s.margin_top = 0
    s.margin_bottom = 0
    s.x_min = 0.0
    s.x_max = 0.0
    s.y_min = 0.0
    s.y_max = 0.0
    s.valid = 0

    s.margin_left = 70
    s.margin_right = 25
    s.margin_top = 25
    s.margin_bottom = 55


def calcode_sync_graph_screen_configure_v1(
    s: Optional[CalcodeSyncGraphScreenV1],
    width: int,
    height: int,
    g: Optional[CalcodeSyncGraphV1],
) -> int:
    """int calcode_sync_graph_screen_configure_v1(...);"""
    if s is None or g is None or not g.valid or width <= 0 or height <= 0:
        return 0

    calcode_sync_graph_screen_init_v1(s)

    s.width = width
    s.height = height

    s.x_min = g.x_min
    s.x_max = g.x_max
    s.y_min = g.y_min
    s.y_max = g.y_max

    s.valid = 1

    return 1


def calcode_sync_graph_world_to_screen_v1(
    s: Optional[CalcodeSyncGraphScreenV1],
    x: float,
    y: float,
    p: Optional[CalcodeSyncScreenPointV1],
) -> int:
    """int calcode_sync_graph_world_to_screen_v1(...);"""
    if s is None or not s.valid or p is None or not math.isfinite(x) or not math.isfinite(y):
        return 0

    left = float(s.margin_left)
    right = float(s.width - s.margin_right)
    top = float(s.margin_top)
    bottom = float(s.height - s.margin_bottom)

    dx = s.x_max - s.x_min
    dy = s.y_max - s.y_min

    if dx <= 0.0 or dy <= 0.0:
        return 0

    u = (x - s.x_min) / dx
    v = (y - s.y_min) / dy

    p.x = left + u * (right - left)

    # Screen y grows downward, mathematical y grows upward.
    p.y = bottom - v * (bottom - top)

    return 1


def calcode_sync_graph_screen_to_world_v1(
    s: Optional[CalcodeSyncGraphScreenV1],
    sx: float,
    sy: float,
) -> Tuple[int, float, float]:
    """int calcode_sync_graph_screen_to_world_v1(const CalcodeSyncGraphScreenV1 *screen,
        double sx, double sy, double *x, double *y);
    Python signature: returns (ok, x, y) in place of the C's `double *x, *y`
    out-params."""
    x = 0.0
    y = 0.0

    if s is None or not s.valid:
        return 0, x, y

    left = float(s.margin_left)
    right = float(s.width - s.margin_right)
    top = float(s.margin_top)
    bottom = float(s.height - s.margin_bottom)

    dx = s.x_max - s.x_min
    dy = s.y_max - s.y_min

    if right <= left or bottom <= top or dx <= 0.0 or dy <= 0.0:
        return 0, x, y

    u = (sx - left) / (right - left)
    v = (bottom - sy) / (bottom - top)

    x = s.x_min + u * dx
    y = s.y_min + v * dy

    return 1, x, y


def calcode_sync_graph_sample_screen_v1(
    s: Optional[CalcodeSyncGraphScreenV1],
    g: Optional[CalcodeSyncGraphV1],
    sample_index: int,
    p: Optional[CalcodeSyncScreenPointV1],
) -> int:
    """int calcode_sync_graph_sample_screen_v1(...);"""
    if (s is None or g is None or p is None or not g.valid
            or sample_index < 0 or sample_index >= g.point_count):
        return 0

    pt = g.points[sample_index]
    return calcode_sync_graph_world_to_screen_v1(s, pt.x, pt.y, p)
