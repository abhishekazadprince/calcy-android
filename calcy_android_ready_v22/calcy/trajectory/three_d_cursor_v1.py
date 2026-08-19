"""calcode_3d_cursor_v1.py -- exact Python port of
calcode_3d_cursor_v1.c / calcode_3d_cursor_v1.h.

Original: represents "the currently selected trajectory sample" in 3D
-- position (projected), time, and a copy of the full state vector
(capped at `CALCODE_RK4_MAX_STATE_V1`). Can be built either from a
trajectory+projection pair directly, or (more conservatively) purely
from geometry already baked into a `Calcode3DSceneV1`.

PORT NOTES:

- `calcode_3d_cursor_at_v1`: rejects None trajectory/projection/cursor
  up front; only *then* calls `init_v1`. Rejects
  `not trajectory.valid`, `not projection.valid`, or an out-of-range
  `sample_index` with a diagnostic and returns 0 (cursor stays
  freshly-initialized, not further touched). Projects the sample;
  on projection failure, a *different* diagnostic and 0. Copies
  `state_dimension` clamped to `CALCODE_RK4_MAX_STATE_V1` (matching
  the C's post-hoc clamp, not a pre-check), then copies that many
  state components from `calcode_trajectory_model_state_at_v1` --
  reproduced returning `0` with **no diagnostic message set** if that
  lookup fails (the C falls through the guard-free `if (!state) return
  0;`, leaving whatever diagnostic was set by the *previous* init call,
  i.e. empty), exactly as written, not "fixed" to add one.
- `calcode_3d_cursor_set_from_scene_v1`: intentionally conservative
  (per the C's own comment) -- recovers only a geometric point, not
  time/state, by finding the scene's first `POLYLINE` primitive and
  indexing into it directly. Rejects `sample_index < 0` or an index at
  or past the polyline's `vertex_count` with a bare `0` (no
  diagnostic set for either -- reproduced as-is).
"""

from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.trajectory.three_d_scene_v1 import (
    Calcode3DVertexV1,
    CALCODE_3D_PRIMITIVE_POLYLINE_V1,
    calcode_3d_scene_vertex_v1,
)

CALCODE_RK4_MAX_STATE_V1 = 64


class Calcode3DCursorV1:
    __slots__ = (
        "valid", "sample_index", "time", "position",
        "state_dimension", "state", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.sample_index = 0
        self.time = 0.0
        self.position = Calcode3DVertexV1()
        self.state_dimension = 0
        self.state = [0.0] * CALCODE_RK4_MAX_STATE_V1
        self.diagnostic = ""


def _diagnostic(c: Optional[Calcode3DCursorV1], message: Optional[str]) -> None:
    if c is None:
        return
    text = message if message else "3D cursor error"
    c.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_3d_cursor_init_v1(c: Optional[Calcode3DCursorV1]) -> None:
    if c is None:
        return
    c.valid = 0
    c.sample_index = -1
    c.time = 0.0
    c.position = Calcode3DVertexV1()
    c.state_dimension = 0
    c.state = [0.0] * CALCODE_RK4_MAX_STATE_V1
    c.diagnostic = ""


def calcode_3d_cursor_at_v1(c, trajectory, projection, sample_index: int) -> int:
    if c is None or trajectory is None or projection is None:
        return 0

    from calcy.trajectory.coordinate_projection_v1 import (
        calcode_projection_point_v1,
        CalcodeProjectedPointV1,
    )
    from calcy.trajectory.trajectory_model_v1 import calcode_trajectory_model_state_at_v1

    calcode_3d_cursor_init_v1(c)

    if (
        not trajectory.valid
        or not projection.valid
        or sample_index < 0
        or sample_index >= trajectory.sample_count
    ):
        _diagnostic(c, "invalid 3D cursor sample")
        return 0

    projected = CalcodeProjectedPointV1()
    if not calcode_projection_point_v1(projection, trajectory, sample_index, projected):
        _diagnostic(c, "unable to project 3D cursor")
        return 0

    c.sample_index = sample_index
    c.time = trajectory.time[sample_index]

    c.position.x = projected.x
    c.position.y = projected.y
    c.position.z = projected.z

    c.state_dimension = trajectory.state_dimension
    if c.state_dimension > CALCODE_RK4_MAX_STATE_V1:
        c.state_dimension = CALCODE_RK4_MAX_STATE_V1

    state = calcode_trajectory_model_state_at_v1(trajectory, sample_index)
    if state is None:
        return 0

    for i in range(c.state_dimension):
        c.state[i] = state[i]

    c.valid = 1
    c.diagnostic = ""

    return 1


def calcode_3d_cursor_set_from_scene_v1(c, scene, sample_index: int) -> int:
    if c is None or scene is None or not scene.valid:
        return 0

    calcode_3d_cursor_init_v1(c)

    if sample_index < 0:
        return 0

    trajectory_vertex_count = 0

    for i in range(scene.primitive_count):
        p = scene.primitives[i]
        if p.kind == CALCODE_3D_PRIMITIVE_POLYLINE_V1:
            trajectory_vertex_count = p.vertex_count
            break

    if sample_index >= trajectory_vertex_count:
        return 0

    for i in range(scene.primitive_count):
        p = scene.primitives[i]
        if p.kind == CALCODE_3D_PRIMITIVE_POLYLINE_V1:
            v = calcode_3d_scene_vertex_v1(scene, p.first_vertex + sample_index)
            if v is None:
                return 0

            c.sample_index = sample_index
            c.position = v
            c.valid = 1

            return 1

    return 0
