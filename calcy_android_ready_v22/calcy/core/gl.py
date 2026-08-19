"""calcode_gl.py -- PARTIAL Python port of calcode_gl.c / calcode_gl.h.

This is NOT a full port. `calcode_gl.c` is one of the files already
flagged genuinely GL-coupled in 00_STATUS_AND_PLAN.md (real `<GL/gl.h>`
/ `<GL/glu.h>` calls throughout `draw_*`/`apply_camera`) and stays
excluded -- the real rendering layer is a separate design task for
whenever a Python front end is built, per the scope note in
REMAINING_PYTHON_PORT_WORK.md.

What IS ported here is the narrow subset of that same file with zero GL
calls, needed because `calcode_lab.c` touches them directly:

- `calcode_gl_style_default` -- pure struct-default init
- `calcode_gl_frame_init` -- pure struct-default init
- `calcode_gl_frame_set_current` -- pure field assignment

Verified by direct line-by-line reading of the real `calcode_gl.c`
against the port below (each ported function reproduced verbatim from
its C body). NOT harness-diffed against a compiled C binary in this
session -- `calcode_gl.c` transitively includes `odesys.h` /
`odesolution.h` (Calcauchy core headers), which aren't present in this
upload set (only their `.obj` build artifacts are). Ask Ayush for
`expr.c/.h`, `odesys.c/.h`, `odesolution.c/.h` to close that gap with
the same compiled-harness method used for calcode_camera / calcode_input.

Deliberately NOT ported here (still real GL, still excluded):
`calcode_gl_frame_from_series`, all `calcode_gl_draw_*`,
`calcode_gl_apply_camera`.
"""

from __future__ import annotations

from typing import Optional


class CalcodeGLStyle:
    """typedef struct CalcodeGLStyle { ... } CalcodeGLStyle;"""
    __slots__ = (
        "axis_width", "curve_width", "trajectory_width", "particle_radius",
        "draw_axes", "draw_grid", "draw_origin", "draw_trajectory",
        "draw_particle", "draw_phase",
    )

    def __init__(self):
        self.axis_width = 0.0
        self.curve_width = 0.0
        self.trajectory_width = 0.0
        self.particle_radius = 0.0
        self.draw_axes = 0
        self.draw_grid = 0
        self.draw_origin = 0
        self.draw_trajectory = 0
        self.draw_particle = 0
        self.draw_phase = 0


class CalcodeGLFrame:
    """typedef struct CalcodeGLFrame { ... } CalcodeGLFrame."""
    __slots__ = (
        "width", "height",
        "world_xmin", "world_xmax",
        "world_ymin", "world_ymax",
        "world_zmin", "world_zmax",
        "current_x", "current_a", "current_b", "current_c",
        "has_current",
    )

    def __init__(self):
        self.width = 0
        self.height = 0
        self.world_xmin = 0.0
        self.world_xmax = 0.0
        self.world_ymin = 0.0
        self.world_ymax = 0.0
        self.world_zmin = 0.0
        self.world_zmax = 0.0
        self.current_x = 0.0
        self.current_a = 0.0
        self.current_b = 0.0
        self.current_c = 0.0
        self.has_current = 0


def calcode_gl_style_default(s: Optional[CalcodeGLStyle]) -> None:
    """void calcode_gl_style_default(CalcodeGLStyle *style);"""
    if s is None:
        return

    s.axis_width = 1.5
    s.curve_width = 2.0
    s.trajectory_width = 2.0
    s.particle_radius = 0.04

    s.draw_axes = 1
    s.draw_grid = 1
    s.draw_origin = 1
    s.draw_trajectory = 1
    s.draw_particle = 1
    s.draw_phase = 1


def calcode_gl_frame_init(f: Optional[CalcodeGLFrame]) -> None:
    """void calcode_gl_frame_init(CalcodeGLFrame *frame);"""
    if f is None:
        return

    f.width = 800
    f.height = 600

    f.world_xmin = -1.0
    f.world_xmax = 1.0
    f.world_ymin = -1.0
    f.world_ymax = 1.0
    f.world_zmin = -1.0
    f.world_zmax = 1.0

    f.current_x = 0.0
    f.current_a = 0.0
    f.current_b = 0.0
    f.current_c = 0.0
    f.has_current = 0


def calcode_gl_frame_set_current(
    f: Optional[CalcodeGLFrame], x: float, a: float, b: float, c: float
) -> None:
    """void calcode_gl_frame_set_current(CalcodeGLFrame *frame, double x, double a, double b, double c);"""
    if f is None:
        return

    f.current_x = x
    f.current_a = a
    f.current_b = b
    f.current_c = c
    f.has_current = 1
