"""calcode_opengl2d_camera_v1.py -- exact Python port of
calcode_opengl2d_camera_v1.c / calcode_opengl2d_camera_v1.h.

Original: pure zoom/pan/reset math for the 2D view camera, plus
`apply_v1` which writes the resulting center/scale onto a
`CalcodeOpenGL2DBackendV1`'s `view` sub-struct. No GL calls in this
file itself -- confirmed by direct inspection of the real
`calcode_opengl2d_camera_v1.c` (grep for `gl[A-Z]`/`GLFW`/`GLuint`
returns zero hits). `calcode_opengl2d_apply_v1` only reads/writes
plain-data fields (`backend.valid`, `backend.view.*`, `backend.scene`)
on the backend struct -- it never calls into `calcode_opengl2d_backend_v1`'s
own (GL-coupled) functions, so only the backend's plain-data struct
shape is needed here, not the real GL-coupled backend module. Depends
on the already-verified `calcode_graph_scene_v1` for the scene bounds
used by `reset_v1`.

PORT STATUS: harness-verified bit-exact against a compiled `gcc -O2`
build of the real C, diffed field-by-field
(`verification_harnesses/harness_opengl2d_camera.c/.py`).
"""

from __future__ import annotations

import math
from typing import Optional

from calcy.graph.graph_scene_v1 import CalcodeGraphSceneV1


class CalcodeOpenGL2DViewV1:
    __slots__ = (
        "center_x", "center_y",
        "scale_x", "scale_y",
        "viewport_width", "viewport_height",
        "aspect",
        "initialized",
    )

    def __init__(self) -> None:
        self.center_x = 0.0
        self.center_y = 0.0
        self.scale_x = 0.0
        self.scale_y = 0.0
        self.viewport_width = 0
        self.viewport_height = 0
        self.aspect = 0.0
        self.initialized = 0


class CalcodeOpenGL2DBackendV1:
    """Plain-data shape only -- the real struct also carries a GL-coupled
    `style` sub-struct and a `diagnostic` buffer that `camera_apply_v1`
    never touches; those are omitted here since they're irrelevant to
    this module's bit-exact behavior."""

    __slots__ = ("valid", "view", "scene")

    def __init__(self) -> None:
        self.valid = 0
        self.view = CalcodeOpenGL2DViewV1()
        self.scene: Optional[CalcodeGraphSceneV1] = None


class CalcodeOpenGL2DCameraV1:
    __slots__ = (
        "center_x", "center_y",
        "zoom",
        "min_zoom", "max_zoom",
        "initialized",
    )

    def __init__(self) -> None:
        self.center_x = 0.0
        self.center_y = 0.0
        self.zoom = 0.0
        self.min_zoom = 0.0
        self.max_zoom = 0.0
        self.initialized = 0


def calcode_opengl2d_camera_init_v1(
    camera: Optional[CalcodeOpenGL2DCameraV1],
) -> None:
    if camera is None:
        return

    camera.center_x = 0.0
    camera.center_y = 0.0
    camera.zoom = 1.0
    camera.min_zoom = 0.05
    camera.max_zoom = 1000.0
    camera.initialized = 0


def calcode_opengl2d_camera_reset_v1(
    camera: Optional[CalcodeOpenGL2DCameraV1],
    scene: Optional[CalcodeGraphSceneV1],
) -> None:
    if camera is None or scene is None or not scene.valid:
        return

    calcode_opengl2d_camera_init_v1(camera)

    camera.center_x = 0.5 * (scene.x_min + scene.x_max)
    camera.center_y = 0.5 * (scene.y_min + scene.y_max)

    camera.initialized = 1


def calcode_opengl2d_camera_zoom_v1(
    camera: Optional[CalcodeOpenGL2DCameraV1],
    factor: float,
) -> int:
    if (
        camera is None
        or not camera.initialized
        or not math.isfinite(factor)
        or factor <= 0.0
    ):
        return 0

    camera.zoom *= factor

    if camera.zoom < camera.min_zoom:
        camera.zoom = camera.min_zoom

    if camera.zoom > camera.max_zoom:
        camera.zoom = camera.max_zoom

    return 1


def calcode_opengl2d_camera_pan_v1(
    camera: Optional[CalcodeOpenGL2DCameraV1],
    dx: float,
    dy: float,
) -> int:
    if (
        camera is None
        or not camera.initialized
        or not math.isfinite(dx)
        or not math.isfinite(dy)
    ):
        return 0

    camera.center_x += dx
    camera.center_y += dy

    return 1


def calcode_opengl2d_camera_apply_v1(
    backend: Optional[CalcodeOpenGL2DBackendV1],
    camera: Optional[CalcodeOpenGL2DCameraV1],
) -> int:
    if backend is None or camera is None or not camera.initialized:
        return 0

    if not backend.valid:
        return 0

    # The backend's scale is world-to-normalized-view scale.
    # Increasing zoom therefore increases the scale.
    backend.view.center_x = camera.center_x
    backend.view.center_y = camera.center_y

    if backend.scene is None:
        return 0

    width = backend.scene.x_max - backend.scene.x_min
    height = backend.scene.y_max - backend.scene.y_min

    if abs(width) < 1e-30:
        width = 1.0

    if abs(height) < 1e-30:
        height = 1.0

    backend.view.scale_x = 2.0 * camera.zoom / width
    backend.view.scale_y = 2.0 * camera.zoom / height

    return 1
