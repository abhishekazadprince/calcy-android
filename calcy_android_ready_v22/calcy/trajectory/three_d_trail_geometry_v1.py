"""calcode_3d_trail_geometry_v1.py -- exact Python port of
calcode_3d_trail_geometry_v1.c / calcode_3d_trail_geometry_v1.h.

Original: decimates a trajectory (either directly, or from an
already-built `Calcode3DSceneV1` polyline primitive) into a strided
sequence of "trail" vertices carrying position, unit tangent, a
constant width, and cumulative arc length -- the geometry backing the
blob's trailing-path ribbon. Pure math, no GL calls.

PORT NOTES:

- `Calcode3DTrailVertexV1.position` / `.tangent` / `.width` /
  `.arc_length` are C `float` (32-bit), not `double`. Every write goes
  through `_f32()` (struct pack/unpack round-trip), and -- critically
  -- `arc` accumulation in both build functions reads the *previous*
  vertex's already-stored (float32-truncated) `position` back out to
  compute the next segment's distance, exactly like the C reading
  `vertices[out-1].position[0]` (a `float`, implicitly widened to
  `double` for the call). This float32-in/float32-out round trip is
  reproduced explicitly, not skipped.
- Decimation count formula reproduced exactly: start `count = 1`, add
  one for every `stride`-th index short of `sample_count`, then one
  more if `(sample_count - 1) % stride != 0` (ensures the final sample
  is always retained even off-stride). Python doesn't need the count
  for pre-allocation, but the *loop that decides which source indices
  are visited* is reproduced with the same stride-then-clamp-to-last
  logic, not just "every stride-th index" (the clamp step means the
  last two visited indices can be closer together than `stride`).
- `tangent_from_samples_v1` / the from-scene tangent: central
  difference between the previous and next projected/scene point
  (clamped to the current index at either boundary), normalized;
  `length <= 1e-30` (or no valid neighbor pair) falls back to
  `(0, 0, 1)` -- reproduced with the same `<=` threshold and fallback
  vector.
- `calcode_3d_trail_geometry_build_v1`: frees+inits first, validates
  trajectory/projection non-None+valid+`sample_count >= 2` and
  `stride` (clamped to `>= 1`, not rejected) and `width` (finite,
  `> 0.0`) each with their own diagnostic. On success, `valid = (out
  >= 2)`; if that's false the trail is explicitly freed and `0`
  returned (diagnostic set first) -- otherwise returns whatever
  `calcode_3d_trail_geometry_validate_v1` reports, not a bare `1`.
- `calcode_3d_trail_geometry_build_from_scene_v1`: same shape, but
  finds the scene's first `POLYLINE` primitive (rejecting if none or
  `< 2` vertices), and -- this is a real, reproduced asymmetry with
  `_build_v1` above -- does **not** free-and-return-0 when `out < 2`;
  it sets `valid = (out >= 2)` and unconditionally returns
  `validate_v1(trail)`, which will itself return `0` for `valid=0` but
  the trail buffer is left allocated rather than freed. Not "fixed"
  here.
- `calcode_3d_trail_geometry_validate_v1`: requires `valid`,
  non-empty vertices, `vertex_count >= 2`, a finite non-negative
  `total_length`, and then per-vertex: every position/tangent
  component finite, `width` finite and `> 0.0`, and `arc_length`
  finite and monotonically non-decreasing (`previous_arc` starts at
  `-1.0`, so a first `arc_length` of exactly `0.0` passes).
"""

import math
import struct
from typing import List, Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.trajectory.three_d_scene_v1 import CALCODE_3D_PRIMITIVE_POLYLINE_V1, calcode_3d_scene_vertex_v1


def _f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


class Calcode3DTrailVertexV1:
    __slots__ = ("position", "tangent", "width", "arc_length")

    def __init__(self):
        self.position = [0.0, 0.0, 0.0]
        self.tangent = [0.0, 0.0, 0.0]
        self.width = 0.0
        self.arc_length = 0.0


class Calcode3DTrailGeometryV1:
    __slots__ = (
        "valid", "vertices", "vertex_count",
        "total_length", "width",
        "source_sample_count", "decimated_sample_count",
        "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.vertices: Optional[List[Calcode3DTrailVertexV1]] = None
        self.vertex_count = 0
        self.total_length = 0.0
        self.width = 0.0
        self.source_sample_count = 0
        self.decimated_sample_count = 0
        self.diagnostic = ""


def _diagnostic(t: Optional[Calcode3DTrailGeometryV1], message: Optional[str]) -> None:
    if t is None:
        return
    text = message if message else "3D trail geometry error"
    t.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_3d_trail_geometry_init_v1(t: Optional[Calcode3DTrailGeometryV1]) -> None:
    if t is None:
        return
    t.valid = 0
    t.vertices = None
    t.vertex_count = 0
    t.total_length = 0.0
    t.width = 0.0
    t.source_sample_count = 0
    t.decimated_sample_count = 0
    t.diagnostic = ""


def calcode_3d_trail_geometry_free_v1(t: Optional[Calcode3DTrailGeometryV1]) -> None:
    if t is None:
        return
    t.vertices = None
    t.vertex_count = 0
    t.total_length = 0.0
    t.width = 0.0
    t.source_sample_count = 0
    t.decimated_sample_count = 0
    t.valid = 0


def _distance3(ax, ay, az, bx, by, bz) -> float:
    dx = bx - ax
    dy = by - ay
    dz = bz - az
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _projected_point(trajectory, projection, sample):
    from calcy.trajectory.coordinate_projection_v1 import (
        calcode_projection_point_v1,
        CalcodeProjectedPointV1,
    )
    if trajectory is None or projection is None:
        return None
    point = CalcodeProjectedPointV1()
    if not calcode_projection_point_v1(projection, trajectory, sample, point):
        return None
    return (point.x, point.y, point.z)


def _tangent_from_samples(trajectory, projection, index):
    previous = index - 1
    next_ = index + 1

    if previous < 0:
        previous = index
    if next_ >= trajectory.sample_count:
        next_ = index

    a = _projected_point(trajectory, projection, previous)
    b = _projected_point(trajectory, projection, next_)

    if a is None or b is None:
        return (0.0, 0.0, 1.0)

    dx = b[0] - a[0]
    dy = b[1] - a[1]
    dz = b[2] - a[2]

    length = math.sqrt(dx * dx + dy * dy + dz * dz)

    if length <= 1e-30:
        return (0.0, 0.0, 1.0)

    return (dx / length, dy / length, dz / length)


def calcode_3d_trail_geometry_build_v1(
    trail: Optional[Calcode3DTrailGeometryV1],
    trajectory,
    projection,
    stride: int,
    width: float,
) -> int:
    if trail is None:
        return 0

    calcode_3d_trail_geometry_free_v1(trail)
    calcode_3d_trail_geometry_init_v1(trail)

    if (
        trajectory is None
        or projection is None
        or not trajectory.valid
        or not projection.valid
        or trajectory.sample_count < 2
    ):
        _diagnostic(trail, "trajectory/projection is invalid or too short")
        return 0

    if stride < 1:
        stride = 1

    if not math.isfinite(width) or width <= 0.0:
        _diagnostic(trail, "trail width must be positive")
        return 0

    vertices: List[Calcode3DTrailVertexV1] = []
    out = 0
    source_index = 0
    arc = 0.0

    while True:
        point = _projected_point(trajectory, projection, source_index)
        if point is None:
            _diagnostic(trail, "unable to project trail sample")
            return 0
        x, y, z = point

        tx, ty, tz = _tangent_from_samples(trajectory, projection, source_index)

        if out > 0:
            prev = vertices[out - 1]
            arc += _distance3(
                prev.position[0], prev.position[1], prev.position[2], x, y, z
            )

        v = Calcode3DTrailVertexV1()
        v.position = [_f32(x), _f32(y), _f32(z)]
        v.tangent = [_f32(tx), _f32(ty), _f32(tz)]
        v.width = _f32(width)
        v.arc_length = _f32(arc)
        vertices.append(v)

        out += 1

        if source_index == trajectory.sample_count - 1:
            break

        source_index += stride

        if source_index >= trajectory.sample_count - 1:
            source_index = trajectory.sample_count - 1

    trail.vertices = vertices
    trail.vertex_count = out
    trail.total_length = arc
    trail.width = width
    trail.source_sample_count = trajectory.sample_count
    trail.decimated_sample_count = out
    trail.valid = 1 if out >= 2 else 0

    if not trail.valid:
        _diagnostic(trail, "trail contains fewer than two vertices")
        calcode_3d_trail_geometry_free_v1(trail)
        return 0

    return calcode_3d_trail_geometry_validate_v1(trail)


def calcode_3d_trail_geometry_build_from_scene_v1(
    trail: Optional[Calcode3DTrailGeometryV1],
    scene,
    stride: int,
    width: float,
) -> int:
    if trail is None:
        return 0

    calcode_3d_trail_geometry_free_v1(trail)
    calcode_3d_trail_geometry_init_v1(trail)

    if scene is None or not scene.valid or scene.vertices is None:
        _diagnostic(trail, "3D scene is invalid")
        return 0

    if stride < 1:
        stride = 1

    if not math.isfinite(width) or width <= 0.0:
        _diagnostic(trail, "trail width must be positive")
        return 0

    polyline = None
    for i in range(scene.primitive_count):
        if scene.primitives[i].kind == CALCODE_3D_PRIMITIVE_POLYLINE_V1:
            polyline = scene.primitives[i]
            break

    if polyline is None or polyline.vertex_count < 2:
        _diagnostic(trail, "3D scene contains no trajectory polyline")
        return 0

    source_count = polyline.vertex_count

    vertices: List[Calcode3DTrailVertexV1] = []
    out = 0
    source_index = 0
    arc = 0.0

    while True:
        scene_index = polyline.first_vertex + source_index
        v_src = calcode_3d_scene_vertex_v1(scene, scene_index)

        if v_src is None:
            _diagnostic(trail, "invalid trajectory vertex in scene")
            return 0

        tx, ty, tz = 0.0, 0.0, 1.0

        previous = source_index - 1
        next_ = source_index + 1

        if previous < 0:
            previous = source_index
        if next_ >= source_count:
            next_ = source_index

        a = calcode_3d_scene_vertex_v1(scene, polyline.first_vertex + previous)
        b = calcode_3d_scene_vertex_v1(scene, polyline.first_vertex + next_)

        if a is not None and b is not None:
            dx = b.x - a.x
            dy = b.y - a.y
            dz = b.z - a.z
            length = math.sqrt(dx * dx + dy * dy + dz * dz)
            if length > 1e-30:
                tx = dx / length
                ty = dy / length
                tz = dz / length

        if out > 0:
            prev = vertices[out - 1]
            arc += _distance3(
                prev.position[0], prev.position[1], prev.position[2],
                v_src.x, v_src.y, v_src.z,
            )

        v = Calcode3DTrailVertexV1()
        v.position = [_f32(v_src.x), _f32(v_src.y), _f32(v_src.z)]
        v.tangent = [_f32(tx), _f32(ty), _f32(tz)]
        v.width = _f32(width)
        v.arc_length = _f32(arc)
        vertices.append(v)

        out += 1

        if source_index == source_count - 1:
            break

        source_index += stride

        if source_index >= source_count - 1:
            source_index = source_count - 1

    trail.vertices = vertices
    trail.vertex_count = out
    trail.total_length = arc
    trail.width = width
    trail.source_sample_count = source_count
    trail.decimated_sample_count = out
    trail.valid = 1 if out >= 2 else 0

    return calcode_3d_trail_geometry_validate_v1(trail)


def calcode_3d_trail_geometry_validate_v1(trail: Optional[Calcode3DTrailGeometryV1]) -> int:
    if trail is None or not trail.valid or trail.vertices is None or trail.vertex_count < 2:
        return 0

    if not math.isfinite(trail.total_length) or trail.total_length < 0.0:
        return 0

    previous_arc = -1.0

    for i in range(trail.vertex_count):
        v = trail.vertices[i]

        for j in range(3):
            if not math.isfinite(v.position[j]) or not math.isfinite(v.tangent[j]):
                return 0

        if not math.isfinite(v.width) or v.width <= 0.0:
            return 0

        if not math.isfinite(v.arc_length) or v.arc_length < previous_arc:
            return 0

        previous_arc = v.arc_length

    return 1


def calcode_3d_trail_geometry_vertex_v1(trail: Optional[Calcode3DTrailGeometryV1], index: int):
    if trail is None or not trail.valid or index < 0 or index >= trail.vertex_count:
        return None
    return trail.vertices[index]
