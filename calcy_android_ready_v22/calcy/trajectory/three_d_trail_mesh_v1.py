"""calcode_3d_trail_mesh_v1.py -- exact Python port of
calcode_3d_trail_mesh_v1.c / calcode_3d_trail_mesh_v1.h.

Original: extrudes a `Calcode3DTrailGeometryV1` (a strided sequence of
position/tangent/width/arc-length samples) into a tube-shaped
triangle mesh -- one ring of `radial_segments` vertices per trail
sample, with a stable orthonormal frame chosen per-ring around each
sample's tangent so the ring doesn't twist unpredictably. Pure
geometry math, no GL calls.

PORT NOTES:

- `Calcode3DTrailMeshVertexV1.position/normal/tangent/arc_length` are
  C `float`; every write goes through `_f32()`.
- `choose_frame_v1`: picks a reference vector `(0,1,0)` normally, or
  `(1,0,0)` if `|tangent.y| > 0.9` (avoids picking a reference nearly
  parallel to T); `N = normalize(T x R)`, `B = normalize(T x N)` --
  reproduced with the exact same cross-product order and the `<= 1e-30
  -> (0,1,0)` degenerate fallback in `normalize_v1`.
- `radial_segments` clamped to `[3, 256]` (below 3 raised to 3, above
  256 lowered to 256 -- not rejected).
- Per-ring, each sample's stored tangent is renormalized (not assumed
  already unit-length) before building the frame -- reproduced.
- Ring vertex position: `source.position + width * (cos(theta)*N +
  sin(theta)*B)`, `theta = 2*pi*radial/radial_segments`, using the
  trail's already-float32 `source.position`/`width` (read back and
  widened to double for the arithmetic, then the result truncated to
  float32 again on store) -- reproduced by reading the already-`_f32`
  values straight out of the trail-geometry vertex (no re-truncation
  needed on read, only on write here).
- Index buffer: two CCW triangles per ring-quad, `(a, c, b)` and
  `(b, c, d)` where `a/b` are this ring's `(radial, radial+1 mod N)`
  and `c/d` are the next ring's -- reproduced with the exact same
  index arithmetic, including the `% radial_segments` wraparound on
  the *radial* index only (not the ring index -- rings never wrap).
- `vertex_count = rings * radial_segments`, `triangle_count = (rings -
  1) * radial_segments * 2`, `index_count = triangle_count * 3` --
  Python lists don't need the pre-sized `calloc`, so the only thing
  reproduced from that is the resulting counts (used by `validate_v1`
  and stored on the mesh), not an allocation-failure path (unreachable
  here, same convention as prior ports).
- `build_v1` always sets `mesh.valid = 1` before calling
  `validate_v1()` and returning *its* result (so a mesh that
  fails validation is left with `valid=1` but the function's return
  value is `0` -- a real, reproduced quirk, not "fixed").
"""

import math
import struct
from typing import List, Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1

CALCODE_PI_V1 = 3.141592653589793238462643383279502884


def _f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


class Calcode3DTrailMeshVertexV1:
    __slots__ = ("position", "normal", "tangent", "arc_length")

    def __init__(self):
        self.position = [0.0, 0.0, 0.0]
        self.normal = [0.0, 0.0, 0.0]
        self.tangent = [0.0, 0.0, 0.0]
        self.arc_length = 0.0


class Calcode3DTrailMeshV1:
    __slots__ = (
        "valid", "vertices", "indices",
        "vertex_count", "index_count", "triangle_count",
        "radial_segments", "width", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.vertices: Optional[List[Calcode3DTrailMeshVertexV1]] = None
        self.indices: Optional[List[int]] = None
        self.vertex_count = 0
        self.index_count = 0
        self.triangle_count = 0
        self.radial_segments = 0
        self.width = 0.0
        self.diagnostic = ""


def _diagnostic(m: Optional[Calcode3DTrailMeshV1], message: Optional[str]) -> None:
    if m is None:
        return
    text = message if message else "3D trail mesh error"
    m.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_3d_trail_mesh_init_v1(m: Optional[Calcode3DTrailMeshV1]) -> None:
    if m is None:
        return
    m.valid = 0
    m.vertices = None
    m.indices = None
    m.vertex_count = 0
    m.index_count = 0
    m.triangle_count = 0
    m.radial_segments = 0
    m.width = 0.0
    m.diagnostic = ""


def calcode_3d_trail_mesh_free_v1(m: Optional[Calcode3DTrailMeshV1]) -> None:
    if m is None:
        return
    m.vertices = None
    m.indices = None
    m.vertex_count = 0
    m.index_count = 0
    m.triangle_count = 0
    m.radial_segments = 0
    m.width = 0.0
    m.valid = 0


def _cross(ax, ay, az, bx, by, bz):
    return (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)


def _norm(x, y, z) -> float:
    return math.sqrt(x * x + y * y + z * z)


def _normalize(x, y, z):
    n = _norm(x, y, z)
    if n <= 1e-30:
        return (0.0, 1.0, 0.0)
    return (x / n, y / n, z / n)


def _choose_frame(tx, ty, tz):
    rx, ry, rz = 0.0, 1.0, 0.0

    ay = abs(ty)
    if ay > 0.9:
        rx, ry, rz = 1.0, 0.0, 0.0

    nx, ny, nz = _cross(tx, ty, tz, rx, ry, rz)
    nx, ny, nz = _normalize(nx, ny, nz)

    bx, by, bz = _cross(tx, ty, tz, nx, ny, nz)
    bx, by, bz = _normalize(bx, by, bz)

    return nx, ny, nz, bx, by, bz


def calcode_3d_trail_mesh_build_v1(
    mesh: Optional[Calcode3DTrailMeshV1],
    trail,
    radial_segments: int,
) -> int:
    if mesh is None:
        return 0

    calcode_3d_trail_mesh_free_v1(mesh)
    calcode_3d_trail_mesh_init_v1(mesh)

    if trail is None or not trail.valid or trail.vertex_count < 2:
        _diagnostic(mesh, "invalid trail geometry")
        return 0

    if radial_segments < 3:
        radial_segments = 3
    if radial_segments > 256:
        radial_segments = 256

    rings = trail.vertex_count
    vertex_count = rings * radial_segments
    triangle_count = (rings - 1) * radial_segments * 2
    index_count = triangle_count * 3

    vertices: List[Calcode3DTrailMeshVertexV1] = [
        Calcode3DTrailMeshVertexV1() for _ in range(vertex_count)
    ]
    indices: List[int] = [0] * index_count

    for ring in range(rings):
        source = trail.vertices[ring]

        tx, ty, tz = _normalize(
            source.tangent[0], source.tangent[1], source.tangent[2]
        )

        nx, ny, nz, bx, by, bz = _choose_frame(tx, ty, tz)

        for radial in range(radial_segments):
            theta = 2.0 * CALCODE_PI_V1 * radial / radial_segments

            c = math.cos(theta)
            s = math.sin(theta)

            radial_x = c * nx + s * bx
            radial_y = c * ny + s * by
            radial_z = c * nz + s * bz

            index = ring * radial_segments + radial

            v = vertices[index]
            v.position[0] = _f32(source.position[0] + trail.width * radial_x)
            v.position[1] = _f32(source.position[1] + trail.width * radial_y)
            v.position[2] = _f32(source.position[2] + trail.width * radial_z)

            v.normal[0] = _f32(radial_x)
            v.normal[1] = _f32(radial_y)
            v.normal[2] = _f32(radial_z)

            v.tangent[0] = _f32(tx)
            v.tangent[1] = _f32(ty)
            v.tangent[2] = _f32(tz)

            v.arc_length = _f32(source.arc_length)

    cursor = 0
    for ring in range(rings - 1):
        for radial in range(radial_segments):
            next_ = (radial + 1) % radial_segments

            a = ring * radial_segments + radial
            b = ring * radial_segments + next_
            c = (ring + 1) * radial_segments + radial
            d = (ring + 1) * radial_segments + next_

            indices[cursor] = a
            cursor += 1
            indices[cursor] = c
            cursor += 1
            indices[cursor] = b
            cursor += 1

            indices[cursor] = b
            cursor += 1
            indices[cursor] = c
            cursor += 1
            indices[cursor] = d
            cursor += 1

    mesh.vertices = vertices
    mesh.indices = indices
    mesh.vertex_count = vertex_count
    mesh.index_count = index_count
    mesh.triangle_count = triangle_count
    mesh.radial_segments = radial_segments
    mesh.width = trail.width
    mesh.valid = 1

    return calcode_3d_trail_mesh_validate_v1(mesh)


def calcode_3d_trail_mesh_validate_v1(mesh: Optional[Calcode3DTrailMeshV1]) -> int:
    if (
        mesh is None
        or not mesh.valid
        or mesh.vertices is None
        or mesh.indices is None
        or mesh.vertex_count < 2
        or mesh.triangle_count < 1
    ):
        return 0

    if mesh.index_count != mesh.triangle_count * 3:
        return 0

    for i in range(mesh.index_count):
        if mesh.indices[i] >= mesh.vertex_count:
            return 0

    for i in range(mesh.vertex_count):
        v = mesh.vertices[i]
        for j in range(3):
            if (
                not math.isfinite(v.position[j])
                or not math.isfinite(v.normal[j])
                or not math.isfinite(v.tangent[j])
            ):
                return 0
        if not math.isfinite(v.arc_length):
            return 0

    return 1
