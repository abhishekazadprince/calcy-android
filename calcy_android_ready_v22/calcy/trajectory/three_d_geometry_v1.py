"""calcode_3d_geometry_v1.py -- exact Python port of
calcode_3d_geometry_v1.c / calcode_3d_geometry_v1.h.

Original: builds renderable triangle-mesh sphere geometry (vertex +
normal buffers plus a triangle index buffer) two ways -- a UV sphere
(latitude/longitude grid) and an icosphere (subdivided icosahedron) --
for use as the "blob" primitive in the 3D trajectory view. Pure
geometry math, no GL calls.

PORT NOTES:

- The header's `#include "calcode_3d_scene_v1.h"` pulls in the scene/
  coordinate-projection chain transitively, but the geometry `.c`
  itself never references anything from that chain (confirmed by full
  read of the C source) -- this port only imports what it actually
  uses (`CALCODE_SYMBOLIC_MAX_ERROR_V1` for the diagnostic buffer
  size), matching the file's real, not textual, dependencies.
- **Float32 fidelity is load-bearing here.** `Calcode3DGeometryVertexV1`
  stores `position`/`normal` as C `float[3]` (32-bit), not `double` --
  every write through `set_vertex_v1` truncates to float32 precision
  before storage, and `midpoint_vertex_v1` later reads those
  *already-truncated* float32 values back (implicitly widened to
  `double` for the midpoint arithmetic, with no additional precision
  gained). Reproduced via a `_f32()` helper (`struct.pack/unpack`
  round-trip) applied at every position/normal write, so values read
  back later carry the same float32 rounding the C's storage would
  have baked in -- this is *not* optional for bit-exactness on
  icosphere subdivision, where midpoints chain off previously-rounded
  vertices.
- `set_vertex_v1`: `length = sqrt(x*x+y*y+z*z)` in double precision;
  `length <= 1e-30` clamps to `1.0` (guards the degenerate zero-vector
  case, matching the C's `<=` not `<`). `position` is `_f32(x/y/z)`
  directly (the *unnormalized* input coordinates); `normal` is
  `_f32(x/length)` etc. (double-precision division, *then* truncated
  to float32) -- position and normal are independently rounded, not
  derived from each other.
- `calcode_3d_geometry_build_uv_sphere_v1`: unconditionally
  free-then-inits first (matching the C). Validates `radius` finite
  and `> 0.0`, `longitude_segments >= 3`, `latitude_segments >= 2` in
  one combined guard (same diagnostic for any failure, matching the
  C's single combined `if`). `vertex_count = (lat_segs+1)*(lon_segs+1)`,
  `triangle_count = lat_segs*lon_segs*2`, `index_count =
  triangle_count*3`. Python list allocation cannot fail the way C's
  `calloc` can, so that failure path is unreachable here (documented,
  same convention as prior ports). Latitude loop `phi` sweeps
  `[-pi/2, pi/2]` inclusive over `lat in [0, latitude_segments]`;
  longitude loop `theta` sweeps `[0, 2*pi]` inclusive over `lon in
  [0, longitude_segments]` (note: both loops are `<=`, producing a
  seam of duplicate vertices at `lon == longitude_segments`, exactly
  matching the C -- not deduplicated). Quad `(a,b,c,d)` -> two CCW
  triangles `(a,c,b)` and `(b,c,d)`, reproduced with the exact same
  index arithmetic and winding. Ends by setting `radius`/
  `longitude_segments`/`latitude_segments`/`valid=1`, then returns
  the result of `calcode_3d_geometry_validate_v1` (so a
  post-construction validation failure -- unreachable for this
  function's own output, but structurally identical to the C, which
  always re-validates rather than assuming its own construction is
  correct) is the function's actual return value, not a bare `1`.
- `calcode_3d_geometry_build_icosphere_v1`: same free-then-init and
  `radius`/`subdivision` validation pattern (`subdivision` must be in
  `[0, 5]`). Builds the 12 golden-ratio icosahedron vertices (each
  individually normalized to the unit sphere then scaled by `radius`
  via `set_vertex_v1`, so each is independently float32-rounded) and
  fixed 20 base triangles verbatim from the same table as the C, then
  applies `subdivision` rounds of triangle quadrisection: each
  triangle `(a,b,c)` contributes edge midpoints `ab`, `bc`, `ca` (via
  `midpoint_vertex_v1`, which *does not* deduplicate shared edge
  midpoints across adjacent triangles -- exactly matching the C, so
  the same geometric point gets re-added as a distinct vertex once
  per adjacent triangle that reaches it, matching real observed
  vertex-count growth) and 4 child triangles `(a,ab,ca)`, `(b,bc,ab)`,
  `(c,ca,bc)`, `(ab,bc,ca)`, in that exact order. `midpoint_vertex_v1`
  averages the two (already float32-rounded) endpoint positions in
  double precision, normalizes, and appends a new vertex via
  `set_vertex_v1` -- except when the summed length is `<= 1e-30`
  (antipodal points), in which case it returns endpoint `a` unchanged
  without adding a vertex, matching the C exactly. C's dynamic
  `realloc`-doubling growth for the vertex/triangle/index buffers is
  reproduced here as plain Python list `append`s -- capacity-growth
  bookkeeping has no effect on final values (only on the unreachable
  `realloc`-failure path, same convention as the UV-sphere `calloc`
  path above), so it is intentionally not replicated byte-for-byte.
  The C's dead, never-called `add_index_v1` static helper is not
  ported -- confirmed by grep against the real source that it has no
  call site anywhere in the file, so it has zero observable effect on
  behavior.
- `calcode_3d_geometry_validate_v1`: requires `geometry` present and
  `.valid`, non-empty `vertices`/`indices`, `vertex_count > 0`,
  `index_count > 0`, `triangle_count > 0`, `index_count ==
  triangle_count * 3`, and every index `< vertex_count` (reproduced
  with the same unsigned-comparison semantics -- indices here are
  always non-negative Python ints, so the C's `unsigned int >=
  (unsigned int)vertex_count` check degenerates to a plain `>=`).
"""

from __future__ import annotations

import math
import struct
from typing import List, Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1

CALCODE_PI_V1 = 3.141592653589793238462643383279502884


def _f32(x: float) -> float:
    """Round a Python float to the nearest IEEE-754 binary32 (C `float`)
    value, returned widened back to a Python double -- matching the
    C's `(float)x` cast followed by storage into a `float` struct
    member, and its later implicit widening back to `double` on read."""
    return struct.unpack('f', struct.pack('f', x))[0]


class Calcode3DGeometryVertexV1:
    """typedef struct Calcode3DGeometryVertexV1 { float position[3];
    float normal[3]; } Calcode3DGeometryVertexV1."""
    __slots__ = ("position", "normal")

    def __init__(self):
        self.position: List[float] = [0.0, 0.0, 0.0]
        self.normal: List[float] = [0.0, 0.0, 0.0]


class Calcode3DGeometryV1:
    """typedef struct Calcode3DGeometryV1 { ... } Calcode3DGeometryV1."""
    __slots__ = (
        "valid", "vertices", "indices", "vertex_count", "index_count",
        "triangle_count", "radius", "longitude_segments", "latitude_segments",
        "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.vertices: Optional[List[Calcode3DGeometryVertexV1]] = None
        self.indices: Optional[List[int]] = None
        self.vertex_count = 0
        self.index_count = 0
        self.triangle_count = 0
        self.radius = 0.0
        self.longitude_segments = 0
        self.latitude_segments = 0
        self.diagnostic = ""


def _diagnostic(g: Optional[Calcode3DGeometryV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(Calcode3DGeometryV1 *g, const char *message);"""
    if g is None:
        return
    text = message if message else "3D geometry error"
    g.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_3d_geometry_init_v1(g: Optional[Calcode3DGeometryV1]) -> None:
    """void calcode_3d_geometry_init_v1(Calcode3DGeometryV1 *geometry);"""
    if g is None:
        return

    g.valid = 0
    g.vertices = None
    g.indices = None
    g.vertex_count = 0
    g.index_count = 0
    g.triangle_count = 0
    g.radius = 0.0
    g.longitude_segments = 0
    g.latitude_segments = 0
    g.diagnostic = ""


def calcode_3d_geometry_free_v1(g: Optional[Calcode3DGeometryV1]) -> None:
    """void calcode_3d_geometry_free_v1(Calcode3DGeometryV1 *geometry);"""
    if g is None:
        return

    g.vertices = None
    g.indices = None

    g.vertex_count = 0
    g.index_count = 0
    g.triangle_count = 0
    g.valid = 0


def _set_vertex_v1(v: Optional[Calcode3DGeometryVertexV1], x: float, y: float, z: float) -> None:
    """static void set_vertex_v1(Calcode3DGeometryVertexV1 *v,
    double x, double y, double z);"""
    if v is None:
        return

    length = math.sqrt(x * x + y * y + z * z)

    if length <= 1e-30:
        length = 1.0

    v.position[0] = _f32(x)
    v.position[1] = _f32(y)
    v.position[2] = _f32(z)

    v.normal[0] = _f32(x / length)
    v.normal[1] = _f32(y / length)
    v.normal[2] = _f32(z / length)


def calcode_3d_geometry_build_uv_sphere_v1(
    g: Optional[Calcode3DGeometryV1],
    radius: float,
    longitude_segments: int,
    latitude_segments: int,
) -> int:
    """int calcode_3d_geometry_build_uv_sphere_v1(Calcode3DGeometryV1 *geometry,
    double radius, int longitude_segments, int latitude_segments);"""
    if g is None:
        return 0

    calcode_3d_geometry_free_v1(g)
    calcode_3d_geometry_init_v1(g)

    if (not math.isfinite(radius) or radius <= 0.0
            or longitude_segments < 3 or latitude_segments < 2):
        _diagnostic(g, "invalid UV sphere parameters")
        return 0

    vertex_count = (latitude_segments + 1) * (longitude_segments + 1)
    triangle_count = latitude_segments * longitude_segments * 2
    index_count = triangle_count * 3

    g.vertices = [Calcode3DGeometryVertexV1() for _ in range(vertex_count)]
    g.indices = [0] * index_count

    # C's calloc-failure path is unreachable here -- see PORT NOTES.

    v = 0

    for lat in range(latitude_segments + 1):
        phi = -0.5 * CALCODE_PI_V1 + CALCODE_PI_V1 * lat / latitude_segments

        cp = math.cos(phi)
        sp = math.sin(phi)

        for lon in range(longitude_segments + 1):
            theta = 2.0 * CALCODE_PI_V1 * lon / longitude_segments

            x = cp * math.cos(theta)
            y = sp
            z = cp * math.sin(theta)

            _set_vertex_v1(g.vertices[v], radius * x, radius * y, radius * z)
            v += 1

    index = 0

    for lat in range(latitude_segments):
        for lon in range(longitude_segments):
            a = lat * (longitude_segments + 1) + lon
            b = a + 1
            c = a + (longitude_segments + 1)
            d = c + 1

            # Counter-clockwise triangles when viewed from outside.
            g.indices[index] = a; index += 1
            g.indices[index] = c; index += 1
            g.indices[index] = b; index += 1

            g.indices[index] = b; index += 1
            g.indices[index] = c; index += 1
            g.indices[index] = d; index += 1

    g.vertex_count = vertex_count
    g.index_count = index_count
    g.triangle_count = triangle_count

    g.radius = radius
    g.longitude_segments = longitude_segments
    g.latitude_segments = latitude_segments

    g.valid = 1

    return calcode_3d_geometry_validate_v1(g)


def _add_icosphere_vertex_v1(
    vertices: List[Calcode3DGeometryVertexV1],
    radius: float,
    x: float,
    y: float,
    z: float,
) -> int:
    """static int add_icosphere_vertex_v1(Calcode3DGeometryVertexV1 **vertices,
    int *count, int *capacity, double radius, double x, double y, double z);
    Capacity/realloc bookkeeping collapses to a plain Python `append`
    -- see PORT NOTES. Always succeeds (Python list append does not
    fail the way C's `realloc` can), so this always returns the new
    vertex's index rather than -1."""
    v = Calcode3DGeometryVertexV1()
    _set_vertex_v1(v, radius * x, radius * y, radius * z)
    vertices.append(v)
    return len(vertices) - 1


class _TriangleV1:
    """typedef struct TriangleV1 { unsigned int a, b, c; } TriangleV1."""
    __slots__ = ("a", "b", "c")

    def __init__(self, a: int, b: int, c: int):
        self.a = a
        self.b = b
        self.c = c


def _midpoint_vertex_v1(
    vertices: List[Calcode3DGeometryVertexV1],
    radius: float,
    a: int,
    b: int,
) -> int:
    """static unsigned int midpoint_vertex_v1(Calcode3DGeometryVertexV1 **vertices,
    int *vertex_count, int *vertex_capacity, double radius,
    unsigned int a, unsigned int b);"""
    ax = vertices[a].position[0]
    ay = vertices[a].position[1]
    az = vertices[a].position[2]

    bx = vertices[b].position[0]
    by = vertices[b].position[1]
    bz = vertices[b].position[2]

    x = ax + bx
    y = ay + by
    z = az + bz

    length = math.sqrt(x * x + y * y + z * z)

    if length <= 1e-30:
        return a

    x /= length
    y /= length
    z /= length

    index = _add_icosphere_vertex_v1(vertices, radius, x, y, z)

    return a if index < 0 else index


def calcode_3d_geometry_build_icosphere_v1(
    g: Optional[Calcode3DGeometryV1],
    radius: float,
    subdivision: int,
) -> int:
    """int calcode_3d_geometry_build_icosphere_v1(Calcode3DGeometryV1 *geometry,
    double radius, int subdivision);"""
    if g is None:
        return 0

    calcode_3d_geometry_free_v1(g)
    calcode_3d_geometry_init_v1(g)

    if not math.isfinite(radius) or radius <= 0.0 or subdivision < 0 or subdivision > 5:
        _diagnostic(g, "invalid icosphere parameters")
        return 0

    # Start with an icosahedron. The golden ratio gives its standard
    # construction.
    phi = (1.0 + math.sqrt(5.0)) / 2.0

    base = [
        (-1, phi, 0), (1, phi, 0), (-1, -phi, 0), (1, -phi, 0),
        (0, -1, phi), (0, 1, phi), (0, -1, -phi), (0, 1, -phi),
        (phi, 0, -1), (phi, 0, 1), (-phi, 0, -1), (-phi, 0, 1),
    ]

    base_triangles = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]

    vertices: List[Calcode3DGeometryVertexV1] = []

    for i in range(12):
        x, y, z = base[i]
        length = math.sqrt(x * x + y * y + z * z)
        _add_icosphere_vertex_v1(vertices, radius, x / length, y / length, z / length)

    triangles: List[_TriangleV1] = [_TriangleV1(*t) for t in base_triangles]

    for level in range(subdivision):
        nxt: List[_TriangleV1] = []

        for tri in triangles:
            a, b, c = tri.a, tri.b, tri.c

            ab = _midpoint_vertex_v1(vertices, radius, a, b)
            bc = _midpoint_vertex_v1(vertices, radius, b, c)
            ca = _midpoint_vertex_v1(vertices, radius, c, a)

            nxt.append(_TriangleV1(a, ab, ca))
            nxt.append(_TriangleV1(b, bc, ab))
            nxt.append(_TriangleV1(c, ca, bc))
            nxt.append(_TriangleV1(ab, bc, ca))

        triangles = nxt

    g.vertices = vertices

    triangle_count = len(triangles)
    g.indices = [0] * (triangle_count * 3)

    for i in range(triangle_count):
        g.indices[3 * i + 0] = triangles[i].a
        g.indices[3 * i + 1] = triangles[i].b
        g.indices[3 * i + 2] = triangles[i].c

    g.vertex_count = len(vertices)
    g.triangle_count = triangle_count
    g.index_count = triangle_count * 3
    g.radius = radius
    g.longitude_segments = 0
    g.latitude_segments = 0
    g.valid = 1

    return calcode_3d_geometry_validate_v1(g)


def calcode_3d_geometry_validate_v1(g: Optional[Calcode3DGeometryV1]) -> int:
    """int calcode_3d_geometry_validate_v1(const Calcode3DGeometryV1 *geometry);"""
    if (g is None or not g.valid or not g.vertices or not g.indices
            or g.vertex_count <= 0 or g.index_count <= 0 or g.triangle_count <= 0):
        return 0

    if g.index_count != g.triangle_count * 3:
        return 0

    for i in range(g.index_count):
        if g.indices[i] >= g.vertex_count:
            return 0

    return 1
