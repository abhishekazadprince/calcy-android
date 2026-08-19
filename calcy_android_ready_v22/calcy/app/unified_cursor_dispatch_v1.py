"""calcode_unified_cursor_dispatch_v1.py -- Python port of
calcode_unified_cursor_dispatch_v1.c / calcode_unified_cursor_dispatch_v1.h.

CALCODE unified cursor event dispatcher. This module is the event-level
adapter between a native window system and the mathematical observation
state. It deliberately does not render anything.

Event flow:

    native mouse event
         |
         v
    view hit-test
         |
         +---- graph -> mathematical cursor
         |
         +---- table -> mathematical cursor
         |
         +---- scene -> camera interaction

The mathematical cursor remains the single source of truth.

PORT NOTES:

- `CalcodeUnifiedCursorCallbacksV1`'s C function pointers
  (`on_cursor_changed`, `on_scene_cursor_changed`,
  `on_table_cursor_changed`, `on_pointer_capture_changed`) become plain
  optional Python callables with the same positional arguments minus
  the trailing `void *user_data`, since Python closures make an
  explicit user-data parameter unnecessary; a `user_data` attribute is
  still kept on the callbacks object for parity/pass-through in case a
  caller wants it, but it is never required to be used by the
  callables themselves.
- `notify_cursor_v1` is a static helper; ported as a module-level
  "private" function (leading underscore) exactly as with every other
  file in this project.
- `scene_pick_sample_v1`'s nearest-point search uses a starting
  `best_d2 = 12.0 * 12.0` (a 12-pixel screen-space pick radius) and its
  tie-break condition `fabs(d2 - best_d2) < 1e-9 && depth < 0.0` is
  reproduced exactly, including that `depth` here is the *camera-space*
  depth from `calcode_opengl3d_camera_project_point_v1` for the
  candidate currently being examined (not the depth of the current
  best) -- this is what the C itself does, not a port simplification.
- The Win32-mouse-is-top-origin / OpenGL-is-bottom-origin flip
  (`top_y = viewport_height - sy`) is reproduced exactly as a comment
  and as code, even though this file has no direct Win32/GL calls
  itself -- it's just describing the coordinate convention the caller
  is expected to use for `event.local_x`/`local_y`.
- All of `pointer_down_v1`/`move_v1`/`up_v1`/`wheel_v1` return C `int`
  0/1; kept as Python `int` (not `bool`) throughout for consistency
  with every other file in this project's boolean-as-int convention.
- `d->event_serial` is a C `unsigned long long`; Python `int` has
  unbounded width so no wraparound behavior is reproduced (matching
  every other counter field ported so far -- none of the harnesses
  drive it anywhere near 2**64 anyway).
"""

from __future__ import annotations

import math
from typing import Callable, Optional

from calcy.app.synchronized_analysis_v1 import (
    CalcodeSyncAnalysisV1,
    calcode_sync_analysis_set_index_v1,
)
from calcy.graph.sync_opengl2d_bridge_v1 import CalcodeSyncOpenGL2DBridgeV1
from calcy.graph.graph_cursor_bridge_v1 import (
    CalcodeGraphCursorBridgeV1,
    CalcodeGraphCursorResultV1,
)
from calcy.graph.graph_cursor_motion_v1 import (
    CalcodeGraphCursorMotionV1,
    calcode_graph_cursor_motion_init_v1,
    calcode_graph_cursor_motion_begin_v1,
    calcode_graph_cursor_motion_move_v1,
    calcode_graph_cursor_motion_end_v1,
)
from calcy.app.cursor_consistency_v1 import (
    CalcodeCursorConsistencyReportV1,
    calcode_cursor_consistency_check_v1,
)
from calcy.graph.opengl3d_camera_v1 import (
    CalcodeOpenGL3DCameraV1,
    calcode_opengl3d_camera_orbit_v1,
    calcode_opengl3d_camera_zoom_v1,
    calcode_opengl3d_camera_project_point_v1,
)
from calcy.trajectory.coordinate_projection_v1 import (
    CalcodeCoordinateProjectionV1,
    CalcodeProjectedPointV1,
    calcode_projection_point_v1,
)
from calcy.trajectory.trajectory_model_v1 import CalcodeTrajectoryModelV1


CALCODE_POINTER_NONE_V1 = 0
CALCODE_POINTER_GRAPH_V1 = 1
CALCODE_POINTER_TABLE_V1 = 2
CALCODE_POINTER_SCENE_V1 = 3

CALCODE_POINTER_BUTTON_NONE_V1 = 0
CALCODE_POINTER_BUTTON_LEFT_V1 = 1
CALCODE_POINTER_BUTTON_MIDDLE_V1 = 2
CALCODE_POINTER_BUTTON_RIGHT_V1 = 3


class CalcodeUnifiedCursorEventV1:
    """typedef struct CalcodeUnifiedCursorEventV1 { ... }"""
    __slots__ = (
        "x", "y", "local_x", "local_y", "wheel_delta",
        "pressed", "released", "button", "view",
    )

    def __init__(self) -> None:
        self.x = 0
        self.y = 0
        self.local_x = 0
        self.local_y = 0
        self.wheel_delta = 0
        self.pressed = 0
        self.released = 0
        self.button = CALCODE_POINTER_BUTTON_NONE_V1
        self.view = CALCODE_POINTER_NONE_V1


class CalcodeUnifiedCursorCallbacksV1:
    """typedef struct CalcodeUnifiedCursorCallbacksV1 { ... }
    Function pointers become optional Python callables (see module
    docstring); `user_data` is kept for parity but not required."""
    __slots__ = (
        "on_cursor_changed",
        "on_scene_cursor_changed",
        "on_table_cursor_changed",
        "on_pointer_capture_changed",
        "user_data",
    )

    def __init__(self) -> None:
        self.on_cursor_changed: Optional[Callable] = None
        self.on_scene_cursor_changed: Optional[Callable] = None
        self.on_table_cursor_changed: Optional[Callable] = None
        self.on_pointer_capture_changed: Optional[Callable] = None
        self.user_data = None


class CalcodeUnifiedCursorDispatchV1:
    """typedef struct CalcodeUnifiedCursorDispatchV1 { ... }"""
    __slots__ = (
        "valid",
        "graph_bridge", "graph_motion",
        "graph", "analysis",
        "scene_camera", "scene_projection", "scene_trajectory",
        "scene_dragging", "scene_moved", "scene_last_x", "scene_last_y",
        "active_view", "active_button",
        "pointer_captured",
        "table_selected_row", "scene_sample_index",
        "event_serial",
        "last_graph_result",
        "last_consistency",
        "diagnostic",
    )

    def __init__(self) -> None:
        self.valid = 0
        self.graph_bridge: Optional[CalcodeGraphCursorBridgeV1] = None
        self.graph_motion = CalcodeGraphCursorMotionV1()
        self.graph: Optional[CalcodeSyncOpenGL2DBridgeV1] = None
        self.analysis: Optional[CalcodeSyncAnalysisV1] = None
        self.scene_camera: Optional[CalcodeOpenGL3DCameraV1] = None
        self.scene_projection: Optional[CalcodeCoordinateProjectionV1] = None
        self.scene_trajectory: Optional[CalcodeTrajectoryModelV1] = None
        self.scene_dragging = 0
        self.scene_moved = 0
        self.scene_last_x = 0
        self.scene_last_y = 0
        self.active_view = 0
        self.active_button = 0
        self.pointer_captured = 0
        self.table_selected_row = 0
        self.scene_sample_index = 0
        self.event_serial = 0
        self.last_graph_result = CalcodeGraphCursorResultV1()
        self.last_consistency = CalcodeCursorConsistencyReportV1()
        self.diagnostic = ""


def _diagnostic_v1(d: Optional[CalcodeUnifiedCursorDispatchV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(...);"""
    if d is None:
        return
    d.diagnostic = message if message is not None else "unified cursor dispatch error"


def _notify_cursor_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1],
    callbacks: Optional[CalcodeUnifiedCursorCallbacksV1],
) -> None:
    """static void notify_cursor_v1(...);"""
    if (d is None or callbacks is None or callbacks.on_cursor_changed is None
            or d.analysis is None or not d.analysis.cursor.valid):
        return

    i = d.analysis.cursor.sample_index

    if i < 0 or i >= d.analysis.trajectory.sample_count:
        return

    sample = d.analysis.trajectory.samples[i]

    callbacks.on_cursor_changed(
        i, sample.t, sample.state, d.analysis.trajectory.state_dimension, callbacks.user_data)

    if callbacks.on_scene_cursor_changed is not None:
        callbacks.on_scene_cursor_changed(i, callbacks.user_data)

    if callbacks.on_table_cursor_changed is not None:
        callbacks.on_table_cursor_changed(i, callbacks.user_data)


def calcode_unified_cursor_dispatch_init_v1(d: Optional[CalcodeUnifiedCursorDispatchV1]) -> None:
    """void calcode_unified_cursor_dispatch_init_v1(CalcodeUnifiedCursorDispatchV1 *dispatch);"""
    if d is None:
        return

    # memset(d, 0, sizeof(*d));
    d.valid = 0
    d.graph_bridge = None
    d.graph_motion = CalcodeGraphCursorMotionV1()
    d.graph = None
    d.analysis = None
    d.scene_camera = None
    d.scene_projection = None
    d.scene_trajectory = None
    d.scene_dragging = 0
    d.scene_moved = 0
    d.scene_last_x = 0
    d.scene_last_y = 0
    d.active_view = 0
    d.active_button = 0
    d.pointer_captured = 0
    d.table_selected_row = 0
    d.scene_sample_index = 0
    d.event_serial = 0
    d.last_graph_result = CalcodeGraphCursorResultV1()
    d.last_consistency = CalcodeCursorConsistencyReportV1()
    d.diagnostic = ""

    calcode_graph_cursor_motion_init_v1(d.graph_motion)

    d.active_view = CALCODE_POINTER_NONE_V1
    d.active_button = CALCODE_POINTER_BUTTON_NONE_V1

    d.table_selected_row = -1
    d.scene_sample_index = -1


def calcode_unified_cursor_dispatch_configure_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1],
    graph_bridge: Optional[CalcodeGraphCursorBridgeV1],
    graph: Optional[CalcodeSyncOpenGL2DBridgeV1],
    analysis: Optional[CalcodeSyncAnalysisV1],
) -> int:
    """int calcode_unified_cursor_dispatch_configure_v1(...);"""
    if (d is None or graph_bridge is None or graph is None or analysis is None
            or not analysis.valid or not graph_bridge.valid):
        return 0

    calcode_unified_cursor_dispatch_init_v1(d)

    d.graph_bridge = graph_bridge
    d.graph = graph
    d.analysis = analysis

    d.valid = 1

    return 1


def calcode_unified_cursor_dispatch_set_table_row_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1], row: int
) -> None:
    """void calcode_unified_cursor_dispatch_set_table_row_v1(...);"""
    if d is None:
        return
    d.table_selected_row = row


def calcode_unified_cursor_dispatch_set_scene_sample_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1], sample_index: int
) -> None:
    """void calcode_unified_cursor_dispatch_set_scene_sample_v1(...);"""
    if d is None:
        return
    d.scene_sample_index = sample_index


def calcode_unified_cursor_dispatch_set_scene_camera_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1], camera: Optional[CalcodeOpenGL3DCameraV1]
) -> None:
    """void calcode_unified_cursor_dispatch_set_scene_camera_v1(...);"""
    if d is None:
        return
    d.scene_camera = camera


def calcode_unified_cursor_dispatch_set_scene_projection_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1],
    projection: Optional[CalcodeCoordinateProjectionV1],
) -> None:
    """void calcode_unified_cursor_dispatch_set_scene_projection_v1(...);"""
    if d is None:
        return
    d.scene_projection = projection


def calcode_unified_cursor_dispatch_set_scene_trajectory_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1],
    trajectory: Optional[CalcodeTrajectoryModelV1],
) -> None:
    """void calcode_unified_cursor_dispatch_set_scene_trajectory_v1(...);"""
    if d is None:
        return
    d.scene_trajectory = trajectory


def _scene_pick_sample_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1], local_x: int, local_y: int
) -> int:
    """static int scene_pick_sample_v1(...);"""
    if (d is None or d.analysis is None or not d.analysis.valid
            or d.scene_camera is None or not d.scene_camera.valid
            or d.scene_projection is None or not d.scene_projection.valid
            or d.scene_trajectory is None or not d.scene_trajectory.valid):
        return 0

    best = -1
    best_d2 = 12.0 * 12.0

    for i in range(d.analysis.trajectory.sample_count):
        p = CalcodeProjectedPointV1()
        if not calcode_projection_point_v1(d.scene_projection, d.scene_trajectory, i, p):
            continue

        ok, sx, sy, depth = calcode_opengl3d_camera_project_point_v1(
            d.scene_camera, p.x, p.y, p.z
        )
        if not ok:
            continue

        # Win32 mouse coordinates are top-origin; OpenGL projection is
        # bottom-origin.
        top_y = float(d.scene_camera.viewport_height) - sy

        if (sx < -12.0
                or sx > float(d.scene_camera.viewport_width) + 12.0
                or top_y < -12.0
                or top_y > float(d.scene_camera.viewport_height) + 12.0):
            continue

        dx = sx - float(local_x)
        dy = top_y - float(local_y)
        d2 = dx * dx + dy * dy

        # Prefer the nearer projected trajectory point when screen-space
        # distances tie.
        if d2 < best_d2 or (abs(d2 - best_d2) < 1e-9 and depth < 0.0):
            best_d2 = d2
            best = i

    if best < 0:
        return 0

    return calcode_sync_analysis_set_index_v1(d.analysis, best)


def calcode_unified_cursor_dispatch_pointer_down_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1],
    event: Optional[CalcodeUnifiedCursorEventV1],
    callbacks: Optional[CalcodeUnifiedCursorCallbacksV1],
) -> int:
    """int calcode_unified_cursor_dispatch_pointer_down_v1(...);"""
    if d is None or not d.valid or event is None:
        return 0

    d.event_serial += 1

    d.active_view = event.view
    d.active_button = event.button

    if event.view == CALCODE_POINTER_GRAPH_V1 and event.button == CALCODE_POINTER_BUTTON_LEFT_V1:
        if not calcode_graph_cursor_motion_begin_v1(
                d.graph_motion, d.graph_bridge, d.graph, d.analysis, event.local_x, event.local_y):
            _diagnostic_v1(
                d,
                d.graph_bridge.diagnostic if d.graph_bridge is not None else "graph cursor begin failed",
            )
            return 0

        d.pointer_captured = 1

        if callbacks is not None and callbacks.on_pointer_capture_changed is not None:
            callbacks.on_pointer_capture_changed(1, callbacks.user_data)

        d.last_graph_result = d.graph_motion.result

        _notify_cursor_v1(d, callbacks)

        calcode_unified_cursor_dispatch_check_consistency_v1(d)

        return 1

    if event.view == CALCODE_POINTER_SCENE_V1 and (
            event.button == CALCODE_POINTER_BUTTON_LEFT_V1
            or event.button == CALCODE_POINTER_BUTTON_RIGHT_V1):
        d.pointer_captured = 1
        d.scene_dragging = 1
        d.scene_moved = 0
        d.scene_last_x = event.local_x
        d.scene_last_y = event.local_y

        if callbacks is not None and callbacks.on_pointer_capture_changed is not None:
            callbacks.on_pointer_capture_changed(1, callbacks.user_data)

        return 1

    # Table selection is still committed by the observation layer.
    return 0


def calcode_unified_cursor_dispatch_pointer_move_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1],
    event: Optional[CalcodeUnifiedCursorEventV1],
    callbacks: Optional[CalcodeUnifiedCursorCallbacksV1],
) -> int:
    """int calcode_unified_cursor_dispatch_pointer_move_v1(...);"""
    if d is None or not d.valid or event is None:
        return 0

    d.event_serial += 1

    if not d.pointer_captured:
        return 0

    if d.active_view == CALCODE_POINTER_GRAPH_V1:
        if not calcode_graph_cursor_motion_move_v1(
                d.graph_motion, d.graph_bridge, d.graph, d.analysis, event.local_x, event.local_y):
            return 0

        d.last_graph_result = d.graph_motion.result

        if d.graph_motion.selection_changed:
            _notify_cursor_v1(d, callbacks)
            calcode_unified_cursor_dispatch_check_consistency_v1(d)
        return 1

    if d.active_view == CALCODE_POINTER_SCENE_V1 and d.scene_camera is not None and d.scene_camera.valid:
        dx = event.local_x - d.scene_last_x
        dy = event.local_y - d.scene_last_y
        if dx != 0 or dy != 0:
            d.scene_moved = 1

        if d.active_button == CALCODE_POINTER_BUTTON_LEFT_V1:
            if not calcode_opengl3d_camera_orbit_v1(d.scene_camera, 0.35 * float(dx), 0.35 * float(dy)):
                return 0
        elif d.active_button == CALCODE_POINTER_BUTTON_RIGHT_V1:
            factor = math.exp(0.01 * float(dy))
            if not calcode_opengl3d_camera_zoom_v1(d.scene_camera, factor):
                return 0

        d.scene_last_x = event.local_x
        d.scene_last_y = event.local_y
        return 1

    return 0


def calcode_unified_cursor_dispatch_pointer_up_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1],
    event: Optional[CalcodeUnifiedCursorEventV1],
    callbacks: Optional[CalcodeUnifiedCursorCallbacksV1],
) -> int:
    """int calcode_unified_cursor_dispatch_pointer_up_v1(...);"""
    if d is None or not d.valid:
        return 0

    d.event_serial += 1

    if not d.pointer_captured:
        return 0

    handled = 1

    if d.active_view == CALCODE_POINTER_GRAPH_V1:
        calcode_graph_cursor_motion_end_v1(d.graph_motion)
    elif d.active_view == CALCODE_POINTER_SCENE_V1:
        if not d.scene_moved and d.active_button == CALCODE_POINTER_BUTTON_LEFT_V1 and event is not None:
            if _scene_pick_sample_v1(d, event.local_x, event.local_y):
                _notify_cursor_v1(d, callbacks)
                calcode_unified_cursor_dispatch_check_consistency_v1(d)
        d.scene_dragging = 0
        d.scene_moved = 0

    d.pointer_captured = 0

    if callbacks is not None and callbacks.on_pointer_capture_changed is not None:
        callbacks.on_pointer_capture_changed(0, callbacks.user_data)

    d.active_view = CALCODE_POINTER_NONE_V1
    d.active_button = CALCODE_POINTER_BUTTON_NONE_V1

    return handled


def calcode_unified_cursor_dispatch_pointer_wheel_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1], event: Optional[CalcodeUnifiedCursorEventV1]
) -> int:
    """int calcode_unified_cursor_dispatch_pointer_wheel_v1(...);"""
    if d is None or not d.valid or event is None:
        return 0

    if event.view != CALCODE_POINTER_SCENE_V1 or d.scene_camera is None or not d.scene_camera.valid:
        return 0

    delta = event.wheel_delta
    if delta == 0:
        return 1

    factor = math.exp(-0.12 * (float(delta) / 120.0))
    return calcode_opengl3d_camera_zoom_v1(d.scene_camera, factor)


def calcode_unified_cursor_dispatch_check_consistency_v1(
    d: Optional[CalcodeUnifiedCursorDispatchV1],
) -> int:
    """int calcode_unified_cursor_dispatch_check_consistency_v1(...);"""
    if d is None or not d.valid or d.analysis is None:
        return 0

    return calcode_cursor_consistency_check_v1(
        d.analysis, d.table_selected_row, d.scene_sample_index, d.last_consistency
    )
