"""calcode_sync_opengl2d_bridge_v1.py -- Python port of the PORTABLE
subset of calcode_sync_opengl2d_bridge_v1.c / calcode_sync_opengl2d_bridge_v1.h.

This file was NOT on the original 50-file remaining-work list (it's
one of the GL/Win32-coupled files the scope note explicitly excludes:
its `draw_v1` is gated behind `#ifdef _WIN32` and issues real GL calls).
It surfaced as a dependency gap while porting `calcode_graph_cursor_bridge_v1`,
which takes a `CalcodeSyncOpenGL2DBridgeV1 *graph` parameter and calls
its `pick_v1` function -- exactly the kind of "positioning logic, no
GL calls" extraction already done for `calcode_opengl_table_overlay_v1`
and `calcode_opengl2d_camera_v1`.

Reading the real C top to bottom: the struct itself
(`CalcodeSyncOpenGL2DBridgeV1`) contains NO GL types at all -- only
plain `int`/`double`/`char[]` fields plus a `CalcodeSyncGraphScreenV1`.
`<windows.h>` is included only under `#ifdef _WIN32` and nothing in
the struct or in `init_v1`/`configure_v1`/`set_viewport_v1`/`pick_v1`
references it. Every actual `gl*()` call lives inside `draw_grid_v1`,
`draw_axes_v1`, `draw_curve_v1`, `draw_cursor_v1` (all `static`, all
gated `#ifdef _WIN32`) and `calcode_sync_opengl2d_bridge_draw_v1`
itself, which on a non-Windows build is literally
`(void)b; (void)a; return 0;` -- i.e. draw_v1 is ALREADY a portable
no-op outside Windows in the real C.

PORTED (bit-for-bit intent, verified via harness_graph_cursor_bridge):
- `CalcodeSyncOpenGL2DBridgeV1` struct
- `calcode_sync_opengl2d_bridge_init_v1`
- `calcode_sync_opengl2d_bridge_configure_v1`
- `calcode_sync_opengl2d_bridge_set_viewport_v1`
- `calcode_sync_opengl2d_bridge_pick_v1` -- the nearest-trajectory-point
  pick logic `calcode_graph_cursor_bridge_v1` needs. Pure math: converts
  a screen pixel to world coordinates via the already-verified
  `calcode_sync_graph_screen_to_world_v1`, then does a linear nearest-
  neighbor search over `analysis.graph.points` in world space (O(n),
  matches the C's own comment that this is intentionally not yet a
  screen-space spatial index).

NOT PORTED (drawing-only, matches the real non-Windows behavior exactly):
- `draw_grid_v1`, `draw_axes_v1`, `draw_curve_v1`, `draw_cursor_v1` --
  `static`, GL-only, `#ifdef _WIN32`-gated in the C.
- `calcode_sync_opengl2d_bridge_draw_v1` -- ported as a stub that always
  returns 0, reproducing the real C's own non-Windows `#else` branch
  verbatim (`(void)b; (void)a; return 0;`). This is not an approximation;
  it is literally what the real function compiles to outside Windows.

PORT NOTES:

- `pick_v1`'s C signature returns sample index / world x / world y
  through `int *sample_index, double *world_x, double *world_y`
  out-params; the Python signature returns `(ok, sample_index, world_x, world_y)`
  in the same tuple-return pattern used throughout this project for
  multi-output C functions.
- The C's `local_y = (double)b->height - screen_y - (double)b->viewport_y`
  (note: NOT `b->viewport_height`, and NOT the same flip used by
  `world_x_from_screen`'s `b->height - 1.0`) is reproduced exactly as
  written, not "fixed" or unified with the other helper.
- Nearest-point tie-breaking: the C uses strict `<` (`if (d2 < best_distance)`)
  so on an exact tie the FIRST point (lowest index) wins, since later
  equal-or-worse candidates never replace it. Reproduced with the same
  strict `<`.
- `best_distance` starts at `HUGE_VAL` (`math.inf` in Python).
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from calcy.app.synchronized_analysis_v1 import CalcodeSyncAnalysisV1
from calcy.app.sync_graph_renderer_v1 import (
    CalcodeSyncGraphScreenV1,
    calcode_sync_graph_screen_init_v1,
    calcode_sync_graph_screen_configure_v1,
    calcode_sync_graph_screen_to_world_v1,
)


class CalcodeSyncOpenGL2DBridgeV1:
    """typedef struct CalcodeSyncOpenGL2DBridgeV1 { ... }"""
    __slots__ = (
        "valid", "width", "height",
        "viewport_x", "viewport_y", "viewport_width", "viewport_height",
        "show_axes", "show_grid", "show_curve", "show_cursor", "show_labels",
        "line_width", "cursor_radius",
        "screen",
        "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.width = 0
        self.height = 0
        self.viewport_x = 0
        self.viewport_y = 0
        self.viewport_width = 0
        self.viewport_height = 0
        self.show_axes = 0
        self.show_grid = 0
        self.show_curve = 0
        self.show_cursor = 0
        self.show_labels = 0
        self.line_width = 0.0
        self.cursor_radius = 0.0
        self.screen = CalcodeSyncGraphScreenV1()
        self.diagnostic = ""


def _set_diag(b: Optional[CalcodeSyncOpenGL2DBridgeV1], message: Optional[str]) -> None:
    """static void set_diag(...);"""
    if b is None:
        return
    b.diagnostic = message if message is not None else "2D OpenGL error"


def calcode_sync_opengl2d_bridge_init_v1(b: Optional[CalcodeSyncOpenGL2DBridgeV1]) -> None:
    """void calcode_sync_opengl2d_bridge_init_v1(CalcodeSyncOpenGL2DBridgeV1 *bridge);"""
    if b is None:
        return

    # memset(b, 0, sizeof(*b));
    b.valid = 0
    b.width = 0
    b.height = 0
    b.viewport_x = 0
    b.viewport_y = 0
    b.viewport_width = 0
    b.viewport_height = 0
    b.show_axes = 0
    b.show_grid = 0
    b.show_curve = 0
    b.show_cursor = 0
    b.show_labels = 0
    b.line_width = 0.0
    b.cursor_radius = 0.0
    b.screen = CalcodeSyncGraphScreenV1()
    b.diagnostic = ""

    b.show_axes = 1
    b.show_grid = 1
    b.show_curve = 1
    b.show_cursor = 1
    b.show_labels = 1

    b.line_width = 1.5
    b.cursor_radius = 5.0

    calcode_sync_graph_screen_init_v1(b.screen)


def calcode_sync_opengl2d_bridge_configure_v1(
    b: Optional[CalcodeSyncOpenGL2DBridgeV1],
    width: int,
    height: int,
    graph,
) -> int:
    """int calcode_sync_opengl2d_bridge_configure_v1(...);"""
    if b is None or graph is None or not graph.valid or width <= 0 or height <= 0:
        return 0

    calcode_sync_opengl2d_bridge_init_v1(b)

    b.width = width
    b.height = height

    b.viewport_x = 0
    b.viewport_y = 0
    b.viewport_width = width
    b.viewport_height = height

    if not calcode_sync_graph_screen_configure_v1(b.screen, width, height, graph):
        _set_diag(b, "unable to configure graph screen")
        return 0

    b.valid = 1
    return 1


def calcode_sync_opengl2d_bridge_set_viewport_v1(
    b: Optional[CalcodeSyncOpenGL2DBridgeV1],
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    """void calcode_sync_opengl2d_bridge_set_viewport_v1(...);"""
    if b is None:
        return

    if width <= 0 or height <= 0:
        return

    b.viewport_x = x
    b.viewport_y = y
    b.viewport_width = width
    b.viewport_height = height

    if b.valid:
        # Preserve the mathematical graph bounds while changing only the
        # pixel dimensions of the local viewport.
        b.screen.width = width
        b.screen.height = height


def calcode_sync_opengl2d_bridge_draw_v1(
    b: Optional[CalcodeSyncOpenGL2DBridgeV1],
    a: Optional[CalcodeSyncAnalysisV1],
) -> int:
    """int calcode_sync_opengl2d_bridge_draw_v1(...);
    Reproduces the real C's non-_WIN32 `#else` branch exactly:
    `(void)b; (void)a; return 0;` -- this is not a Python-side
    simplification, it is the function's actual behavior on any
    non-Windows build of the real C."""
    return 0


def calcode_sync_opengl2d_bridge_pick_v1(
    b: Optional[CalcodeSyncOpenGL2DBridgeV1],
    a: Optional[CalcodeSyncAnalysisV1],
    screen_x: float,
    screen_y: float,
) -> Tuple[int, int, float, float]:
    """int calcode_sync_opengl2d_bridge_pick_v1(const CalcodeSyncOpenGL2DBridgeV1 *bridge,
        const CalcodeSyncAnalysisV1 *analysis, double screen_x, double screen_y,
        int *sample_index, double *world_x, double *world_y);
    Python signature: returns (ok, sample_index, world_x, world_y) in place
    of the C's three out-params."""
    sample_index = -1
    world_x = 0.0
    world_y = 0.0

    if (b is None or not b.valid or a is None or not a.valid
            or not a.graph.valid):
        return 0, sample_index, world_x, world_y

    # Convert global window coordinates into graph-local coordinates.
    local_x = screen_x - float(b.viewport_x)
    local_y = float(b.height) - screen_y - float(b.viewport_y)

    ok, wx, wy = calcode_sync_graph_screen_to_world_v1(b.screen, local_x, local_y)
    if not ok:
        return 0, sample_index, world_x, world_y

    best = -1
    best_distance = math.inf

    # Nearest-trajectory-point picking is intentionally done in world
    # coordinates. A later renderer can replace this with a screen-space
    # spatial index for large trajectories.
    for i in range(a.graph.point_count):
        dx = a.graph.points[i].x - wx
        dy = a.graph.points[i].y - wy
        d2 = dx * dx + dy * dy

        if d2 < best_distance:
            best_distance = d2
            best = i

    if best < 0:
        return 0, sample_index, world_x, world_y

    sample_index = best
    world_x = a.graph.points[best].x
    world_y = a.graph.points[best].y

    return 1, sample_index, world_x, world_y
