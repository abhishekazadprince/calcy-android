"""calcode_opengl_scene.py -- PARTIAL Python port of
calcode_opengl_scene.c / calcode_opengl_scene.h.

Also NOT a full port, for the same reason as calcode_gl.py: this file
is already flagged genuinely GL-coupled (real `glViewport`/`glClear`/
draw calls in `calcode_gl_scene_resize` and `calcode_gl_scene_render`)
and stays excluded pending the separate Python rendering-layer design.

Ported here -- confirmed zero GL calls by reading the real source --
because `calcode_lab.c` calls them directly:

- `calcode_gl_scene_init`
- `calcode_gl_scene_orbit` (pure delegate to calcode_camera_orbit)
- `calcode_gl_scene_zoom` (pure delegate to calcode_camera_zoom)

`calcode_gl_scene_set_time` is also pure (single field assignment) and
included for completeness even though `calcode_lab.c` doesn't call it
directly.

Same verification caveat as calcode_gl.py: reproduced verbatim from the
real C by direct reading, not yet harness-diffed against a compiled
binary -- blocked on the missing odesys.h/expr.h/odesolution.h in this
upload set.

Deliberately NOT ported here (still real GL, still excluded):
`calcode_gl_scene_resize`, `calcode_gl_scene_render` and its
`render_graph`/`render_phase`/`render_3d`/`clear_frame` helpers.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional

from calcy.core.gl import CalcodeGLStyle, CalcodeGLFrame, calcode_gl_style_default, calcode_gl_frame_init
from calcy.core.camera import CalcodeCamera, calcode_camera_init, calcode_camera_orbit, calcode_camera_zoom


class CalcodeGLSceneMode(IntEnum):
    """typedef enum CalcodeGLSceneMode { ... } CalcodeGLSceneMode;"""
    CALCODE_SCENE_GRAPH = 0
    CALCODE_SCENE_PHASE = 1
    CALCODE_SCENE_3D = 2
    CALCODE_SCENE_SPLIT = 3


class CalcodeGLScene:
    """typedef struct CalcodeGLScene { ... } CalcodeGLScene.

    NOTE: only the fields calcode_lab.c actually reads/writes are
    meaningfully maintained here (mode, camera, frame). width/height/
    style/current_x are carried for struct fidelity but nothing in the
    ported subset renders or resizes with them.
    """
    __slots__ = ("mode", "style", "camera", "frame", "current_x", "width", "height")

    def __init__(self):
        # Mirrors memset(s, 0, sizeof(*s)); every call site goes
        # through calcode_gl_scene_init before use, same as the C.
        self.mode = CalcodeGLSceneMode.CALCODE_SCENE_GRAPH
        self.style = CalcodeGLStyle()
        self.camera = CalcodeCamera()
        self.frame = CalcodeGLFrame()
        self.current_x = 0.0
        self.width = 0
        self.height = 0


def calcode_gl_scene_init(s: Optional[CalcodeGLScene]) -> None:
    """void calcode_gl_scene_init(CalcodeGLScene *scene);"""
    if s is None:
        return

    s.mode = CalcodeGLSceneMode.CALCODE_SCENE_SPLIT

    s.style = CalcodeGLStyle()
    calcode_gl_style_default(s.style)

    s.camera = CalcodeCamera()
    calcode_camera_init(s.camera)

    s.frame = CalcodeGLFrame()
    calcode_gl_frame_init(s.frame)

    s.width = 1200
    s.height = 700


def calcode_gl_scene_set_time(s: Optional[CalcodeGLScene], x: float) -> None:
    """void calcode_gl_scene_set_time(CalcodeGLScene *scene, double x);"""
    if s is None:
        return
    s.current_x = x


def calcode_gl_scene_orbit(s: Optional[CalcodeGLScene], dx: float, dy: float) -> None:
    """void calcode_gl_scene_orbit(CalcodeGLScene *scene, double dx, double dy);"""
    if s is None:
        return
    calcode_camera_orbit(s.camera, dx, dy)


def calcode_gl_scene_zoom(s: Optional[CalcodeGLScene], factor: float) -> None:
    """void calcode_gl_scene_zoom(CalcodeGLScene *scene, double factor);"""
    if s is None:
        return
    calcode_camera_zoom(s.camera, factor)
