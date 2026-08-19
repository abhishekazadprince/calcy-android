"""calcode_3d_blob_v1.py -- exact Python port of
calcode_3d_blob_v1.c / calcode_3d_blob_v1.h.

Original: the interactive "blob" instance (position, per-axis scale,
per-axis rotation, radius, and the sample index/time it currently
represents) built from a `Calcode3DCursorV1`. Pure state, no GL calls.

PORT NOTES:

- `calcode_3d_blob_instance_from_cursor_v1`: rejects None
  blob/cursor, an invalid cursor, or a non-finite/`<= 0.0` radius
  *before* calling `init_v1` (so a rejected call leaves the blob
  completely untouched, not reset) -- reproduced with the guard
  ordered ahead of the init call, matching every other constructor in
  this port family.
- `_set_scale_v1` / `_set_rotation_v1` both require `blob.valid`
  already set (i.e. only callable on a blob built from a cursor) and
  reject any non-finite component; scale additionally requires every
  component `> 0.0` (rotation has no such constraint, matching the
  C's actual guard, which omits a positivity check on rotation).
"""

import math
from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1


class Calcode3DBlobInstanceV1:
    __slots__ = (
        "valid",
        "x", "y", "z",
        "scale_x", "scale_y", "scale_z",
        "rotation_x", "rotation_y", "rotation_z",
        "radius",
        "sample_index", "time",
        "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.scale_x = 0.0
        self.scale_y = 0.0
        self.scale_z = 0.0
        self.rotation_x = 0.0
        self.rotation_y = 0.0
        self.rotation_z = 0.0
        self.radius = 0.0
        self.sample_index = 0
        self.time = 0.0
        self.diagnostic = ""


def _diagnostic(b: Optional[Calcode3DBlobInstanceV1], message: Optional[str]) -> None:
    if b is None:
        return
    text = message if message else "3D blob error"
    b.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_3d_blob_instance_init_v1(b: Optional[Calcode3DBlobInstanceV1]) -> None:
    if b is None:
        return

    b.valid = 0
    b.x = 0.0
    b.y = 0.0
    b.z = 0.0
    b.rotation_x = 0.0
    b.rotation_y = 0.0
    b.rotation_z = 0.0
    b.radius = 0.0
    b.time = 0.0
    b.diagnostic = ""

    b.scale_x = 1.0
    b.scale_y = 1.0
    b.scale_z = 1.0

    b.sample_index = -1


def calcode_3d_blob_instance_from_cursor_v1(b, c, radius: float) -> int:
    if (
        b is None
        or c is None
        or not c.valid
        or not math.isfinite(radius)
        or radius <= 0.0
    ):
        return 0

    calcode_3d_blob_instance_init_v1(b)

    b.x = c.position.x
    b.y = c.position.y
    b.z = c.position.z

    b.radius = radius

    b.sample_index = c.sample_index

    b.time = c.time

    b.valid = 1
    b.diagnostic = ""

    return 1


def calcode_3d_blob_instance_set_scale_v1(b, sx: float, sy: float, sz: float) -> int:
    if (
        b is None
        or not b.valid
        or not math.isfinite(sx)
        or not math.isfinite(sy)
        or not math.isfinite(sz)
        or sx <= 0.0
        or sy <= 0.0
        or sz <= 0.0
    ):
        return 0

    b.scale_x = sx
    b.scale_y = sy
    b.scale_z = sz

    return 1


def calcode_3d_blob_instance_set_rotation_v1(b, rx: float, ry: float, rz: float) -> int:
    if (
        b is None
        or not b.valid
        or not math.isfinite(rx)
        or not math.isfinite(ry)
        or not math.isfinite(rz)
    ):
        return 0

    b.rotation_x = rx
    b.rotation_y = ry
    b.rotation_z = rz

    return 1
