"""calcode_opengl3d_camera_v1.py -- exact Python port of the pure-math
subset of calcode_opengl3d_camera_v1.c / calcode_opengl3d_camera_v1.h.

Original: an orbit camera (target + distance/yaw/pitch) for the 3D
trajectory view. Configure/orbit/zoom/set_target mutate the camera;
project_point_v1 projects a world point into the camera's local
viewport (screen_y measured from the bottom, matching OpenGL).

PORT SCOPE: only the non-GL functions are ported --
`calcode_opengl3d_camera_init_v1`, `..._configure_v1`,
`..._set_viewport_v1`, `..._orbit_v1`, `..._zoom_v1`,
`..._set_target_v1`, and `..._project_point_v1`. The C's
`calcode_opengl3d_camera_apply_v1` (and its two static helpers
`perspective_v1` / `look_at_v1`) call directly into
`glMatrixMode`/`glLoadIdentity`/`glMultMatrixd`/`glTranslated` to
push a projection/modelview matrix onto the real GL matrix stack --
that is drawing code with no return value to verify and is
deliberately NOT ported here, matching the pattern already used for
`calcode_sync_opengl2d_bridge_v1`.

PORT NOTES (from harness diffing against the real .c):

- `configure_v1`'s guard runs entirely before touching `c`: any
  non-finite/out-of-range distance, yaw, pitch, fov, or near/far pair
  rejects with 0 and leaves the camera **untouched** (not reset) --
  reproduced by returning before calling `init_v1`.
- On success, `configure_v1` calls `init_v1(c)` first (so
  `viewport_width`/`viewport_height` reset to the 800x600 default and
  `target_x/y/z` reset to 0) and only *then* overwrites
  distance/yaw/pitch/fov/near/far and sets `valid = 1` -- so a
  `set_viewport_v1`/`set_target_v1` call made before a later
  `configure_v1` call is wiped out. Reproduced with the same
  init-then-overwrite order.
- `orbit_v1` and `zoom_v1` both require `valid` to already be 1 (a
  freshly-`init_v1`'d, never-`configure_v1`'d camera silently no-ops
  with rc=0) -- reproduced with the same guard.
- `orbit_v1` clamps pitch to [-89.0, 89.0] *after* adding delta_pitch
  (not delta_yaw) -- yaw is never wrapped or clamped, matching C.
- `zoom_v1` clamps distance to [1e-6, 1e12] after multiplying by
  `factor` -- confirmed against the real C for both directions
  (`zoom_clamp_low`/`zoom_clamp_high` in the harness).
- `project_point_v1` recomputes the eye position and the forward/
  side/up basis from scratch (same formula as `look_at_v1`, but
  without calling it, since that's the GL-coupled helper) --
  reproduced as an independent computation, not a call to a shared
  helper, matching the C's actual duplication.
- The camera-space `cz` is computed as `-(r . f)` where `f` points
  from eye toward target -- this means a world point sitting exactly
  *at the target* (or anywhere further from the eye along the
  viewing direction) yields a **negative** `cz` and is rejected by
  the `cz <= near_plane` guard; only points on the eye's own side of
  the local origin (behind the eye, by this sign convention) pass.
  Confirmed against the real C with the harness's `proj_center`
  (target itself, rc=0) vs `proj_eyeside_valid` (rc=1) cases -- this
  is the real C's behavior, reproduced exactly, not "fixed."
- `project_point_v1` requires `screen_x`/`screen_y` output slots but
  treats `depth` as optional (`if (depth) *depth = cz;`) -- the
  Python port mirrors this by returning `(rc, screen_x, screen_y,
  depth_or_None)` rather than by mutating pass-by-reference doubles,
  since Python has no analogous concept of an omitted output pointer;
  callers who don't need depth simply ignore the third return value.
- Final return is `isfinite(screen_x) and isfinite(screen_y)`,
  matching C's `&&` short-circuit exactly (no side effects either
  side, so this only matters for which branch is taken, not for any
  computed value).
- All angle math uses the same literal
  `3.141592653589793238462643383279502884` for pi as the C's
  `CALCODE_PI_V1` (not `math.pi`), to keep bit-identical rounding.
"""

import math

CALCODE_PI_V1 = 3.141592653589793238462643383279502884


class CalcodeOpenGL3DCameraV1:
    __slots__ = (
        "valid",
        "target_x", "target_y", "target_z",
        "distance",
        "yaw", "pitch",
        "field_of_view_degrees", "near_plane", "far_plane",
        "viewport_width", "viewport_height",
        "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0
        self.distance = 0.0
        self.yaw = 0.0
        self.pitch = 0.0
        self.field_of_view_degrees = 0.0
        self.near_plane = 0.0
        self.far_plane = 0.0
        self.viewport_width = 0
        self.viewport_height = 0
        self.diagnostic = ""


def calcode_opengl3d_camera_init_v1(c):
    if c is None:
        return

    c.valid = 0
    c.target_x = 0.0
    c.target_y = 0.0
    c.target_z = 0.0
    c.diagnostic = ""

    c.distance = 10.0
    c.yaw = 45.0
    c.pitch = 25.0

    c.field_of_view_degrees = 45.0
    c.near_plane = 0.01
    c.far_plane = 10000.0

    c.viewport_width = 800
    c.viewport_height = 600


def calcode_opengl3d_camera_configure_v1(
    c, distance, yaw, pitch, field_of_view_degrees, near_plane, far_plane
):
    if (
        c is None
        or not math.isfinite(distance)
        or distance <= 0.0
        or not math.isfinite(yaw)
        or not math.isfinite(pitch)
        or pitch <= -89.9
        or pitch >= 89.9
        or not math.isfinite(field_of_view_degrees)
        or field_of_view_degrees <= 1.0
        or field_of_view_degrees >= 179.0
        or not math.isfinite(near_plane)
        or near_plane <= 0.0
        or not math.isfinite(far_plane)
        or far_plane <= near_plane
    ):
        return 0

    calcode_opengl3d_camera_init_v1(c)

    c.distance = distance
    c.yaw = yaw
    c.pitch = pitch
    c.field_of_view_degrees = field_of_view_degrees
    c.near_plane = near_plane
    c.far_plane = far_plane
    c.valid = 1

    return 1


def calcode_opengl3d_camera_set_viewport_v1(c, width, height):
    if c is None or width <= 0 or height <= 0:
        return 0

    c.viewport_width = width
    c.viewport_height = height

    return 1


def calcode_opengl3d_camera_orbit_v1(c, delta_yaw, delta_pitch):
    if (
        c is None
        or not c.valid
        or not math.isfinite(delta_yaw)
        or not math.isfinite(delta_pitch)
    ):
        return 0

    c.yaw += delta_yaw
    c.pitch += delta_pitch

    if c.pitch > 89.0:
        c.pitch = 89.0

    if c.pitch < -89.0:
        c.pitch = -89.0

    return 1


def calcode_opengl3d_camera_zoom_v1(c, factor):
    if c is None or not c.valid or not math.isfinite(factor) or factor <= 0.0:
        return 0

    c.distance *= factor

    if c.distance < 1e-6:
        c.distance = 1e-6

    if c.distance > 1e12:
        c.distance = 1e12

    return 1


def calcode_opengl3d_camera_set_target_v1(c, x, y, z):
    if c is None or not math.isfinite(x) or not math.isfinite(y) or not math.isfinite(z):
        return 0

    c.target_x = x
    c.target_y = y
    c.target_z = z

    return 1


def calcode_opengl3d_camera_project_point_v1(c, world_x, world_y, world_z):
    """Returns (rc, screen_x, screen_y, depth). `depth` is None when rc
    is 0 (matching C leaving *depth untouched on early-return paths;
    callers must not read it unless rc is 1). `screen_x`/`screen_y`
    are likewise None on rc=0."""

    if (
        c is None
        or not c.valid
        or c.viewport_width <= 0
        or c.viewport_height <= 0
    ):
        return 0, None, None, None

    yaw = c.yaw * CALCODE_PI_V1 / 180.0
    pitch = c.pitch * CALCODE_PI_V1 / 180.0
    cp = math.cos(pitch)

    ex = c.target_x + c.distance * cp * math.cos(yaw)
    ey = c.target_y + c.distance * math.sin(pitch)
    ez = c.target_z + c.distance * cp * math.sin(yaw)

    fx = c.target_x - ex
    fy = c.target_y - ey
    fz = c.target_z - ez
    fn = math.sqrt(fx * fx + fy * fy + fz * fz)
    if fn <= 1e-30:
        return 0, None, None, None
    fx /= fn
    fy /= fn
    fz /= fn

    upx, upy, upz = 0.0, 1.0, 0.0
    sx = fy * upz - fz * upy
    sy = fz * upx - fx * upz
    sz = fx * upy - fy * upx
    sn = math.sqrt(sx * sx + sy * sy + sz * sz)
    if sn <= 1e-30:
        upx, upy, upz = 1.0, 0.0, 0.0
        sx = fy * upz - fz * upy
        sy = fz * upx - fx * upz
        sz = fx * upy - fy * upx
        sn = math.sqrt(sx * sx + sy * sy + sz * sz)
    if sn <= 1e-30:
        return 0, None, None, None
    sx /= sn
    sy /= sn
    sz /= sn

    ux = sy * fz - sz * fy
    uy = sz * fx - sx * fz
    uz = sx * fy - sy * fx

    rx = world_x - ex
    ry = world_y - ey
    rz = world_z - ez

    cx = rx * sx + ry * sy + rz * sz
    cy = rx * ux + ry * uy + rz * uz
    cz = -(rx * fx + ry * fy + rz * fz)

    if (
        not math.isfinite(cx)
        or not math.isfinite(cy)
        or not math.isfinite(cz)
        or cz <= c.near_plane
    ):
        return 0, None, None, None

    aspect = float(c.viewport_width) / float(c.viewport_height)
    tan_half = math.tan(0.5 * c.field_of_view_degrees * CALCODE_PI_V1 / 180.0)

    if (
        not math.isfinite(aspect)
        or aspect <= 0.0
        or not math.isfinite(tan_half)
        or tan_half <= 0.0
    ):
        return 0, None, None, None

    ndc_x = cx / (cz * tan_half * aspect)
    ndc_y = cy / (cz * tan_half)

    screen_x = 0.5 * (ndc_x + 1.0) * float(c.viewport_width)
    screen_y = 0.5 * (ndc_y + 1.0) * float(c.viewport_height)
    depth = cz

    rc = 1 if (math.isfinite(screen_x) and math.isfinite(screen_y)) else 0
    return rc, screen_x, screen_y, depth
