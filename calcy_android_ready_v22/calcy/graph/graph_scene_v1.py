"""calcode_graph_scene_v1.py -- exact Python port of
calcode_graph_scene_v1.c / calcode_graph_scene_v1.h.

Original: turns a `CalcodeGraphModelV1` (axes + points) into a flat list
of drawable primitives (lines, a polyline, points, text) plus a shared
vertex array -- deliberately close to what a future OpenGL renderer
would consume (a vertex buffer + index ranges).

PORT NOTES:

- `CALCODE_GRAPH_SCENE_MAX_PRIMITIVES_V1` (4096) and
  `CALCODE_GRAPH_SCENE_MAX_TEXT_V1` (128) are reproduced as module
  constants. The C primitive array is a fixed-size
  `CalcodeGraphScenePrimitiveV1[4096]` with `add_primitive_v1` refusing
  to add past that cap; reproduced with a Python list plus the same
  explicit `>= CALCODE_GRAPH_SCENE_MAX_PRIMITIVES_V1` guard (so the
  failure mode -- returning 0/`False` once the cap is hit -- matches,
  even though a Python list has no real fixed capacity).
- The C's `vertices` array is a single `calloc(capacity, ...)` sized
  from `point_count + 2*(x_ticks + y_ticks) + 16` up front, with
  `add_vertex_v1` writing at `vertex_count` and incrementing it
  in-place (no bounds check in the C -- it trusts the capacity
  pre-computation). Reproduced with a plain Python list appended to by
  `_add_vertex_v1`, which mirrors the "no bounds check" behavior
  faithfully: if a future caller ever fed a model whose tick/point
  counts disagreed with what was used to size `capacity`, the C would
  overrun the buffer (undefined behavior); this port instead just
  keeps appending, which is the closest same-inputs-same-outputs
  behavior achievable in Python without reproducing UB.
- `calcode_graph_scene_build_v1` calls `free_v1()` then `init_v1()`
  unconditionally at the top, exactly matching the C's call order --
  reproduced as-is, before the guard checks that can still fail.
- `build_axes_v1`'s "x-axis at y=0 if the range straddles zero, else at
  the y-minimum" rule (and the mirrored rule for the y-axis) is
  reproduced with the identical `<=`/`>=` boundary conditions.
- `build_ticks_and_labels_v1` returns early (success, no-op) when
  `labels_enabled` is false -- reproduced as an early `return 1`-style
  `True` before any vertex/primitive is added, exactly as in C.
- Tick marks are drawn as short line segments spanning 1% of the
  *other* axis's range, centered on the tick line position (which is
  the axis line's position, not necessarily zero) -- reproduced with
  the exact same `0.01 * (max - min)` half-width and the same
  `y_tick`/`x_tick` values used for both the tick geometry and the
  axis-label anchor points.
- `build_curve_v1` returns failure (0/`False`) when
  `g.point_count <= 0`, which the C reads as a hard error inside
  `build_v1`'s `goto failure` -- but `build_v1` itself already
  rejects `point_count <= 0` earlier via its own top-level guard, so
  in practice `build_curve_v1`'s own `point_count <= 0` branch is
  dead code reachable only if `curve_enabled` code ran after some
  hypothetical future guard relaxation. Reproduced as literal dead
  code for structural fidelity, not simplified away.
- `build_title_v1` is a no-op success (`return 1`/`True`) both when
  `labels_enabled` is false and when the model's `title` is empty --
  reproduced as two separate early-return checks in the same order.
- `calcode_graph_scene_build_v1`'s vertex-array allocation-failure
  path (`calloc` returning NULL) has no direct Python equivalent (a
  Python list never fails to "allocate" for any capacity this project
  would plausibly hit) -- the diagnostic string and failure path are
  kept in the source as an explicit unreachable branch comment rather
  than silently dropped, per the project's "say so explicitly" rule
  for branches that cannot be reached from the public Python API.
- `calcode_graph_scene_primitive_v1` / `_vertex_v1` bounds checks
  (`!valid`, negative index, index >= count) are reproduced with the
  same guard order, returning `None` in place of C's `NULL`.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.graph.graph_model_v1 import CalcodeGraphModelV1

CALCODE_GRAPH_SCENE_MAX_PRIMITIVES_V1 = 4096
CALCODE_GRAPH_SCENE_MAX_TEXT_V1 = 128


class CalcodeGraphPrimitiveKindV1(IntEnum):
    """typedef enum CalcodeGraphPrimitiveKindV1 { ... }."""
    CALCODE_GRAPH_PRIMITIVE_LINE_V1 = 0
    CALCODE_GRAPH_PRIMITIVE_POLYLINE_V1 = 1
    CALCODE_GRAPH_PRIMITIVE_POINT_V1 = 2
    CALCODE_GRAPH_PRIMITIVE_TEXT_V1 = 3


class CalcodeGraphSceneVertexV1:
    """typedef struct CalcodeGraphSceneVertexV1 { ... }."""
    __slots__ = ("x", "y")

    def __init__(self, x: float = 0.0, y: float = 0.0):
        self.x = x
        self.y = y


class CalcodeGraphScenePrimitiveV1:
    """typedef struct CalcodeGraphScenePrimitiveV1 { ... }."""
    __slots__ = ("kind", "first_vertex", "vertex_count", "x", "y", "text")

    def __init__(self):
        self.kind = CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_LINE_V1
        self.first_vertex = 0
        self.vertex_count = 0
        self.x = 0.0
        self.y = 0.0
        self.text = ""


class CalcodeGraphSceneV1:
    """typedef struct CalcodeGraphSceneV1 { ... }."""
    __slots__ = (
        "valid", "x_min", "x_max", "y_min", "y_max",
        "vertex_count", "vertices",
        "primitive_count", "primitives",
        "grid_enabled", "axes_enabled", "curve_enabled", "labels_enabled",
        "title", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.x_min = 0.0
        self.x_max = 0.0
        self.y_min = 0.0
        self.y_max = 0.0
        self.vertex_count = 0
        self.vertices: list[CalcodeGraphSceneVertexV1] = []
        self.primitive_count = 0
        self.primitives: list[CalcodeGraphScenePrimitiveV1] = []
        self.grid_enabled = 1
        self.axes_enabled = 1
        self.curve_enabled = 1
        self.labels_enabled = 1
        self.title = ""
        self.diagnostic = ""


def _diagnostic_v1(s: Optional[CalcodeGraphSceneV1], message: Optional[str]) -> None:
    if s is None:
        return
    s.diagnostic = (message if message is not None else "graph scene error")[
        :CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_graph_scene_init_v1(s: Optional[CalcodeGraphSceneV1]) -> None:
    if s is None:
        return
    s.valid = 0
    s.x_min = 0.0
    s.x_max = 0.0
    s.y_min = 0.0
    s.y_max = 0.0
    s.vertex_count = 0
    s.vertices = []
    s.primitive_count = 0
    s.primitives = []
    s.title = ""
    s.diagnostic = ""

    s.grid_enabled = 1
    s.axes_enabled = 1
    s.curve_enabled = 1
    s.labels_enabled = 1


def calcode_graph_scene_free_v1(s: Optional[CalcodeGraphSceneV1]) -> None:
    if s is None:
        return
    s.vertices = []
    s.vertex_count = 0
    s.primitive_count = 0
    s.valid = 0


def calcode_graph_scene_set_options_v1(
        s: Optional[CalcodeGraphSceneV1],
        grid_enabled: int,
        axes_enabled: int,
        curve_enabled: int,
        labels_enabled: int) -> int:
    if s is None:
        return 0

    s.grid_enabled = 1 if grid_enabled else 0
    s.axes_enabled = 1 if axes_enabled else 0
    s.curve_enabled = 1 if curve_enabled else 0
    s.labels_enabled = 1 if labels_enabled else 0

    return 1


def _add_primitive_v1(
        s: Optional[CalcodeGraphSceneV1],
        kind: CalcodeGraphPrimitiveKindV1,
        first_vertex: int,
        vertex_count: int,
        x: float,
        y: float,
        text: Optional[str]) -> int:
    if s is None or s.primitive_count >= CALCODE_GRAPH_SCENE_MAX_PRIMITIVES_V1:
        return 0

    p = CalcodeGraphScenePrimitiveV1()
    p.kind = kind
    p.first_vertex = first_vertex
    p.vertex_count = vertex_count
    p.x = x
    p.y = y

    if text is not None:
        p.text = text[:CALCODE_GRAPH_SCENE_MAX_TEXT_V1 - 1]

    s.primitives.append(p)
    s.primitive_count += 1

    return 1


def _add_vertex_v1(s: Optional[CalcodeGraphSceneV1], x: float, y: float) -> int:
    if s is None:
        return -1

    s.vertices.append(CalcodeGraphSceneVertexV1(x, y))
    index = s.vertex_count
    s.vertex_count += 1
    return index


def _build_grid_v1(s: Optional[CalcodeGraphSceneV1],
                    g: Optional[CalcodeGraphModelV1]) -> int:
    if s is None or g is None:
        return 0

    # Vertical grid lines.
    for i in range(g.x_axis.tick_count):
        x = g.x_axis.ticks[i].value

        first = _add_vertex_v1(s, x, g.y_axis.minimum)
        _add_vertex_v1(s, x, g.y_axis.maximum)

        if not _add_primitive_v1(
                s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_LINE_V1,
                first, 2, 0.0, 0.0, None):
            return 0

    # Horizontal grid lines.
    for i in range(g.y_axis.tick_count):
        y = g.y_axis.ticks[i].value

        first = _add_vertex_v1(s, g.x_axis.minimum, y)
        _add_vertex_v1(s, g.x_axis.maximum, y)

        if not _add_primitive_v1(
                s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_LINE_V1,
                first, 2, 0.0, 0.0, None):
            return 0

    return 1


def _build_axes_v1(s: Optional[CalcodeGraphSceneV1],
                    g: Optional[CalcodeGraphModelV1]) -> int:
    if s is None or g is None:
        return 0

    # x-axis is drawn at y=0 when zero lies inside the graph.
    # Otherwise it is drawn along the lower boundary.
    y_axis = 0.0 if (g.y_axis.minimum <= 0.0 and g.y_axis.maximum >= 0.0) \
        else g.y_axis.minimum

    first = _add_vertex_v1(s, g.x_axis.minimum, y_axis)
    _add_vertex_v1(s, g.x_axis.maximum, y_axis)

    if not _add_primitive_v1(
            s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_LINE_V1,
            first, 2, 0.0, 0.0, None):
        return 0

    # y-axis.
    x_axis = 0.0 if (g.x_axis.minimum <= 0.0 and g.x_axis.maximum >= 0.0) \
        else g.x_axis.minimum

    first = _add_vertex_v1(s, x_axis, g.y_axis.minimum)
    _add_vertex_v1(s, x_axis, g.y_axis.maximum)

    return _add_primitive_v1(
        s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_LINE_V1,
        first, 2, 0.0, 0.0, None)


def _build_ticks_and_labels_v1(s: Optional[CalcodeGraphSceneV1],
                                g: Optional[CalcodeGraphModelV1]) -> int:
    if s is None or g is None:
        return 0

    if not s.labels_enabled:
        return 1

    # Tick marks and text are represented as independent scene primitives.
    # A renderer can choose typography, orientation and alignment.
    y_tick = 0.0 if (g.y_axis.minimum <= 0.0 and g.y_axis.maximum >= 0.0) \
        else g.y_axis.minimum

    for i in range(g.x_axis.tick_count):
        x = g.x_axis.ticks[i].value

        first = _add_vertex_v1(
            s, x, y_tick - 0.01 * (g.y_axis.maximum - g.y_axis.minimum))
        _add_vertex_v1(
            s, x, y_tick + 0.01 * (g.y_axis.maximum - g.y_axis.minimum))

        if not _add_primitive_v1(
                s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_LINE_V1,
                first, 2, 0.0, 0.0, None):
            return 0

        if not _add_primitive_v1(
                s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_TEXT_V1,
                -1, 0, x, y_tick, g.x_axis.ticks[i].label):
            return 0

    x_tick = 0.0 if (g.x_axis.minimum <= 0.0 and g.x_axis.maximum >= 0.0) \
        else g.x_axis.minimum

    for i in range(g.y_axis.tick_count):
        y = g.y_axis.ticks[i].value

        first = _add_vertex_v1(
            s, x_tick - 0.01 * (g.x_axis.maximum - g.x_axis.minimum), y)
        _add_vertex_v1(
            s, x_tick + 0.01 * (g.x_axis.maximum - g.x_axis.minimum), y)

        if not _add_primitive_v1(
                s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_LINE_V1,
                first, 2, 0.0, 0.0, None):
            return 0

        if not _add_primitive_v1(
                s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_TEXT_V1,
                -1, 0, x_tick, y, g.y_axis.ticks[i].label):
            return 0

    if g.x_axis.label:
        if not _add_primitive_v1(
                s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_TEXT_V1,
                -1, 0, g.x_axis.maximum, y_tick, g.x_axis.label):
            return 0

    if g.y_axis.label:
        if not _add_primitive_v1(
                s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_TEXT_V1,
                -1, 0, x_tick, g.y_axis.maximum, g.y_axis.label):
            return 0

    return 1


def _build_curve_v1(s: Optional[CalcodeGraphSceneV1],
                     g: Optional[CalcodeGraphModelV1]) -> int:
    if s is None or g is None or g.point_count <= 0:
        return 0

    first = s.vertex_count

    for i in range(g.point_count):
        if _add_vertex_v1(s, g.points[i].x, g.points[i].y) < 0:
            return 0

    return _add_primitive_v1(
        s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_POLYLINE_V1,
        first, g.point_count, 0.0, 0.0, None)


def _build_title_v1(s: Optional[CalcodeGraphSceneV1],
                     g: Optional[CalcodeGraphModelV1]) -> int:
    if s is None or g is None or not s.labels_enabled:
        return 1

    if not g.title:
        return 1

    return _add_primitive_v1(
        s, CalcodeGraphPrimitiveKindV1.CALCODE_GRAPH_PRIMITIVE_TEXT_V1,
        -1, 0,
        0.5 * (g.x_axis.minimum + g.x_axis.maximum),
        g.y_axis.maximum,
        g.title)


def calcode_graph_scene_build_v1(
        s: Optional[CalcodeGraphSceneV1],
        g: Optional[CalcodeGraphModelV1]) -> int:
    if s is None or g is None:
        return 0

    calcode_graph_scene_free_v1(s)
    calcode_graph_scene_init_v1(s)

    if not g.valid or not g.points or g.point_count <= 0:
        _diagnostic_v1(s, "graph model is invalid or empty")
        return 0

    # One vertex array is allocated for the complete scene in the C
    # original (`capacity = point_count + 2*(x_ticks + y_ticks) + 16`).
    # A Python list needs no upfront sizing; `_add_vertex_v1` simply
    # appends, which is the faithful same-inputs-same-outputs behavior
    # (see PORT NOTES on the calloc-failure branch below, which is
    # unreachable here and kept only as a documented comment).
    #
    # calloc-failure branch (unreachable from the public Python API):
    #   if allocation failed: _diagnostic_v1(s, "unable to allocate
    #   graph scene vertices"); return 0

    s.x_min = g.x_axis.minimum
    s.x_max = g.x_axis.maximum
    s.y_min = g.y_axis.minimum
    s.y_max = g.y_axis.maximum

    if s.grid_enabled and not _build_grid_v1(s, g):
        calcode_graph_scene_free_v1(s)
        _diagnostic_v1(s, "unable to construct graph scene")
        return 0

    if s.axes_enabled and not _build_axes_v1(s, g):
        calcode_graph_scene_free_v1(s)
        _diagnostic_v1(s, "unable to construct graph scene")
        return 0

    if not _build_ticks_and_labels_v1(s, g):
        calcode_graph_scene_free_v1(s)
        _diagnostic_v1(s, "unable to construct graph scene")
        return 0

    if s.curve_enabled and not _build_curve_v1(s, g):
        calcode_graph_scene_free_v1(s)
        _diagnostic_v1(s, "unable to construct graph scene")
        return 0

    if not _build_title_v1(s, g):
        calcode_graph_scene_free_v1(s)
        _diagnostic_v1(s, "unable to construct graph scene")
        return 0

    s.title = g.title[:127]

    s.valid = 1
    s.diagnostic = ""

    return 1


def calcode_graph_scene_primitive_v1(
        s: Optional[CalcodeGraphSceneV1], index: int) -> Optional[CalcodeGraphScenePrimitiveV1]:
    if s is None or not s.valid or index < 0 or index >= s.primitive_count:
        return None
    return s.primitives[index]


def calcode_graph_scene_vertex_v1(
        s: Optional[CalcodeGraphSceneV1], index: int) -> Optional[CalcodeGraphSceneVertexV1]:
    if (s is None or not s.valid or not s.vertices or
            index < 0 or index >= s.vertex_count):
        return None
    return s.vertices[index]
