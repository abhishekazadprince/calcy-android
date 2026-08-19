"""calcode_3d_scene_v1.py -- exact Python port of
calcode_3d_scene_v1.c / calcode_3d_scene_v1.h.

Original: assembles the full 3D scene (axes, trajectory polyline,
moving point, orbit) as a flat vertex buffer plus a list of
"primitives" (line/polyline/point/orbit) referencing ranges of that
buffer. Pure data assembly, no GL calls.

PORT NOTES:

- The C's vertex buffer is a fixed `calloc(capacity, ...)` where
  `capacity = sample_count + 16` (trajectory samples + 3 axis pairs +
  1 moving point + margin), and `add_vertex_v1` writes past the
  logical count with no bounds check of its own -- callers are
  trusted to stay within capacity. Python's list has no such fixed
  capacity, so `add_vertex_v1` here just appends; behavior for every
  in-bounds call is identical, and the only thing not reproduced is
  the theoretical C buffer-overrun a caller outside this file's own
  functions could trigger -- not reachable through this module's own
  API.
- `calcode_3d_scene_build_axes_v1` requires `s.vertices` to already be
  allocated (matches the C's `if (!s || !s->vertices) return 0;`) --
  ported as "vertices must not be None", set by `build_v1` before this
  is called.
- `calcode_3d_scene_build_v1`: always frees+inits first, then rejects
  an invalid/empty trajectory or invalid projection (setting the
  diagnostic on each). Copies the bounding box straight from the
  projection. If `z_max == z_min` (planar trajectory), pads it: `1.0`
  if the value is exactly `0.0`, else `0.1 * abs(z_max)`, with a
  `pad <= 0.0` fallback to `1.0` -- reproduced with the exact same
  branch order (including the redundant fallback, which the first
  branch already makes unreachable for finite input, exactly as in
  the C). Axes, trajectory polyline, and moving point are each built
  only if their `*_enabled` flag is set, `goto failure` on any partial
  failure (i.e. free the scene and report a generic "unable to
  construct" diagnostic, discarding whatever more specific diagnostic
  a sub-step may have set) -- reproduced as an explicit early-return
  path that mirrors the same discard.
- `calcode_3d_scene_add_moving_point_v1` / `_add_orbit_v1` both also
  require `s.vertices` to already exist (same guard as axes) --
  callers outside `build_v1` (e.g. re-adding a moving point after
  scene construction) must have a already-built scene.
- `calcode_3d_scene_primitive_v1` / `_vertex_v1` are read accessors
  that require `s.valid` (not just non-None) and an in-range index,
  returning `None` (C: `NULL`) otherwise -- reproduced as returning
  the object itself (not a copy) on success, matching the C's
  pointer-into-buffer semantics closely enough for read-only use.
"""

from typing import List, Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1

CALCODE_3D_SCENE_MAX_PRIMITIVES_V1 = 4096

CALCODE_3D_PRIMITIVE_LINE_V1 = 0
CALCODE_3D_PRIMITIVE_POLYLINE_V1 = 1
CALCODE_3D_PRIMITIVE_POINT_V1 = 2
CALCODE_3D_PRIMITIVE_ORBIT_V1 = 3


class Calcode3DVertexV1:
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x = x
        self.y = y
        self.z = z


class Calcode3DPrimitiveV1:
    __slots__ = ("kind", "first_vertex", "vertex_count", "point_size")

    def __init__(self):
        self.kind = CALCODE_3D_PRIMITIVE_LINE_V1
        self.first_vertex = 0
        self.vertex_count = 0
        self.point_size = 0.0


class Calcode3DSceneV1:
    __slots__ = (
        "valid",
        "x_min", "x_max", "y_min", "y_max", "z_min", "z_max",
        "vertex_count", "vertices",
        "primitive_count", "primitives",
        "axes_enabled", "trajectory_enabled",
        "moving_point_enabled", "orbit_enabled",
        "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.x_min = 0.0
        self.x_max = 0.0
        self.y_min = 0.0
        self.y_max = 0.0
        self.z_min = 0.0
        self.z_max = 0.0
        self.vertex_count = 0
        self.vertices: Optional[List[Calcode3DVertexV1]] = None
        self.primitive_count = 0
        self.primitives: List[Calcode3DPrimitiveV1] = []
        self.axes_enabled = 0
        self.trajectory_enabled = 0
        self.moving_point_enabled = 0
        self.orbit_enabled = 0
        self.diagnostic = ""


def _diagnostic(s: Optional[Calcode3DSceneV1], message: Optional[str]) -> None:
    if s is None:
        return
    text = message if message else "3D scene error"
    s.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_3d_scene_init_v1(s: Optional[Calcode3DSceneV1]) -> None:
    if s is None:
        return

    s.valid = 0
    s.x_min = 0.0
    s.x_max = 0.0
    s.y_min = 0.0
    s.y_max = 0.0
    s.z_min = 0.0
    s.z_max = 0.0
    s.vertex_count = 0
    s.vertices = None
    s.primitive_count = 0
    s.primitives = []
    s.diagnostic = ""

    s.axes_enabled = 1
    s.trajectory_enabled = 1
    s.moving_point_enabled = 1
    s.orbit_enabled = 0


def calcode_3d_scene_free_v1(s: Optional[Calcode3DSceneV1]) -> None:
    if s is None:
        return

    s.vertices = None
    s.vertex_count = 0
    s.primitive_count = 0
    s.valid = 0


def calcode_3d_scene_set_options_v1(
    s: Optional[Calcode3DSceneV1],
    axes_enabled: int,
    trajectory_enabled: int,
    moving_point_enabled: int,
    orbit_enabled: int,
) -> int:
    if s is None:
        return 0

    s.axes_enabled = 1 if axes_enabled else 0
    s.trajectory_enabled = 1 if trajectory_enabled else 0
    s.moving_point_enabled = 1 if moving_point_enabled else 0
    s.orbit_enabled = 1 if orbit_enabled else 0

    return 1


def _add_vertex(s: Optional[Calcode3DSceneV1], x: float, y: float, z: float) -> int:
    if s is None:
        return -1

    s.vertices.append(Calcode3DVertexV1(x, y, z))
    idx = s.vertex_count
    s.vertex_count += 1
    return idx


def _add_primitive(
    s: Optional[Calcode3DSceneV1],
    kind: int,
    first_vertex: int,
    vertex_count: int,
    point_size: float,
) -> int:
    if s is None or s.primitive_count >= CALCODE_3D_SCENE_MAX_PRIMITIVES_V1:
        return 0

    p = Calcode3DPrimitiveV1()
    p.kind = kind
    p.first_vertex = first_vertex
    p.vertex_count = vertex_count
    p.point_size = point_size

    s.primitives.append(p)
    s.primitive_count += 1

    return 1


def calcode_3d_scene_build_axes_v1(s: Optional[Calcode3DSceneV1]) -> int:
    if s is None or s.vertices is None:
        return 0

    # X axis
    first = _add_vertex(s, s.x_min, 0.0, 0.0)
    _add_vertex(s, s.x_max, 0.0, 0.0)
    if not _add_primitive(s, CALCODE_3D_PRIMITIVE_LINE_V1, first, 2, 1.0):
        return 0

    # Y axis
    first = _add_vertex(s, 0.0, s.y_min, 0.0)
    _add_vertex(s, 0.0, s.y_max, 0.0)
    if not _add_primitive(s, CALCODE_3D_PRIMITIVE_LINE_V1, first, 2, 1.0):
        return 0

    # Z axis
    first = _add_vertex(s, 0.0, 0.0, s.z_min)
    _add_vertex(s, 0.0, 0.0, s.z_max)

    return _add_primitive(s, CALCODE_3D_PRIMITIVE_LINE_V1, first, 2, 1.0)


def _build_trajectory(s, t, p) -> int:
    if s is None or t is None or p is None:
        return 0

    # Imported lazily to avoid a hard import-time dependency loop --
    # matches the C's real (transitive, header-only) coupling.
    from calcy.trajectory.coordinate_projection_v1 import (
        calcode_projection_point_v1,
        CalcodeProjectedPointV1,
    )

    first = s.vertex_count

    for i in range(t.sample_count):
        point = CalcodeProjectedPointV1()
        if not calcode_projection_point_v1(p, t, i, point):
            return 0
        _add_vertex(s, point.x, point.y, point.z)

    return _add_primitive(
        s, CALCODE_3D_PRIMITIVE_POLYLINE_V1, first, t.sample_count, 1.0
    )


def calcode_3d_scene_add_moving_point_v1(s, point) -> int:
    if s is None or point is None or s.vertices is None:
        return 0

    first = _add_vertex(s, point.x, point.y, point.z)

    return _add_primitive(s, CALCODE_3D_PRIMITIVE_POINT_V1, first, 1, 10.0)


def calcode_3d_scene_add_orbit_v1(s, points, count: int) -> int:
    if s is None or points is None or count <= 1 or s.vertices is None:
        return 0

    first = s.vertex_count

    for i in range(count):
        _add_vertex(s, points[i].x, points[i].y, points[i].z)

    return _add_primitive(s, CALCODE_3D_PRIMITIVE_ORBIT_V1, first, count, 1.0)


def calcode_3d_scene_build_v1(s, t, p) -> int:
    if s is None or t is None or p is None:
        return 0

    from calcy.trajectory.coordinate_projection_v1 import calcode_projection_point_v1, CalcodeProjectedPointV1

    calcode_3d_scene_free_v1(s)
    calcode_3d_scene_init_v1(s)

    if not t.valid or t.sample_count <= 0:
        _diagnostic(s, "trajectory is invalid or empty")
        return 0

    if not p.valid:
        _diagnostic(s, "projection is invalid")
        return 0

    # Python lists grow dynamically; no fixed capacity to allocate,
    # but we still start from an explicit empty list matching the
    # post-calloc state (all-zero vertex_count).
    s.vertices = []

    s.x_min = p.x_min
    s.x_max = p.x_max
    s.y_min = p.y_min
    s.y_max = p.y_max
    s.z_min = p.z_min
    s.z_max = p.z_max

    if s.z_max == s.z_min:
        if s.z_max == 0.0:
            pad = 1.0
        else:
            pad = 0.1 * (s.z_max if s.z_max > 0.0 else -s.z_max)

        if pad <= 0.0:
            pad = 1.0

        s.z_min -= pad
        s.z_max += pad

    def failure():
        calcode_3d_scene_free_v1(s)
        _diagnostic(s, "unable to construct 3D scene")
        return 0

    if s.axes_enabled and not calcode_3d_scene_build_axes_v1(s):
        return failure()

    if s.trajectory_enabled and not _build_trajectory(s, t, p):
        return failure()

    if s.moving_point_enabled:
        first = CalcodeProjectedPointV1()
        if not calcode_projection_point_v1(p, t, 0, first):
            return failure()
        if not calcode_3d_scene_add_moving_point_v1(s, first):
            return failure()

    s.valid = 1
    s.diagnostic = ""

    return 1


def calcode_3d_scene_primitive_v1(s, index: int):
    if s is None or not s.valid or index < 0 or index >= s.primitive_count:
        return None
    return s.primitives[index]


def calcode_3d_scene_vertex_v1(s, index: int):
    if (
        s is None
        or not s.valid
        or s.vertices is None
        or index < 0
        or index >= s.vertex_count
    ):
        return None
    return s.vertices[index]
