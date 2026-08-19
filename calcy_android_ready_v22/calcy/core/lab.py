"""calcode_lab.py -- exact Python port of calcode_lab.c / calcode_lab.h.

Original: the top-level "lab" object tying the whole experiment
together -- a CalcodeWorkspace (problem + solved experiment), a
CalcodeGLScene (view mode + camera + current-frame), a CalcodeClock
(playback over the solved time domain), and CalcodeInputState, plus
the selected curve/phase/trajectory state indices and a CalcodeViewData
built from the current solution.

PORT STATUS -- NOT YET HARNESS-VERIFIED.

Every other ported file in this project (camera, input, and everything
in 01_verified_python/) was checked by compiling the real .c against a
matched C/Python harness and diffing bit-for-bit. That wasn't possible
for this file: `calcode_lab.h` -> `calcode_workspace.h` ->
`calcode_problem_io.h` -> `calcode_model.h` -> `odesys.h` /
`odesolution.h`, and those three Calcauchy-core headers (and their
.c files) are not present anywhere in this session's four uploads --
only their compiled .obj build artifacts are. An earlier session
apparently did have them (see VERIFICATION_NOTE_ode_core.md, which
references compiling expr.c/odesys.c/odesolution.c directly), but they
weren't carried into this batch.

This port was produced by direct line-by-line reading of the real
`calcode_lab.c`/`calcode_lab.h`, reusing the exact same already-verified
Python modules (`calcode_workspace`, `calcode_clock`, `calcode_viewdata`)
the C originally called into. It should be correct, but per your own
stated method ("only mark a file done after a clean harness diff"),
this should NOT be checked off in 00_STATUS_AND_PLAN.md until that
verification actually happens -- send over expr.c/.h, odesys.c/.h,
odesolution.c/.h (or the whole Calcauchy source dir) and it can be
closed out the same way camera/input were.

PORT NOTES:

- `CalcodeLab.scene` is typed `CalcodeGLScene` from the PARTIAL
  `calcode_opengl_scene.py` (see that file's docstring) -- only the
  init/orbit/zoom/set_time subset calcode_lab.c actually touches.
  Nothing here depends on the excluded render/resize functions.

- `calcode_lab_shutdown` calls `calcode_experiment_free` directly on
  `lab.workspace.experiment`, exactly like the C (`calcode_lab.c`
  reaches through `workspace` rather than calling
  `calcode_workspace`'s own free -- there isn't one; the C's comment-free
  choice to free the experiment field directly is reproduced as-is,
  not "improved").

- Every function begins with the same `if (!lab) return;` / `return 0;`
  NULL-guard pattern as the C, modeled as `if lab is None: return`.
"""

from __future__ import annotations

from typing import Optional

from calcy.core.workspace import (
    CalcodeWorkspace,
    calcode_workspace_init,
    calcode_workspace_load,
    calcode_workspace_solve,
    calcode_workspace_is_solution_current,
)
from calcy.core.model import calcode_experiment_free
from calcy.core.opengl_scene import (
    CalcodeGLScene,
    CalcodeGLSceneMode,
    calcode_gl_scene_init,
    calcode_gl_scene_orbit,
    calcode_gl_scene_zoom,
)
from calcy.core.gl import calcode_gl_frame_set_current
from calcy.core.clock import (
    CalcodeClock,
    calcode_clock_init,
    calcode_clock_toggle,
    calcode_clock_reset,
    calcode_clock_set_time,
    calcode_clock_set_speed,
    calcode_clock_tick,
)
from calcy.core.input import CalcodeInputState, CalcodeInputAction, calcode_input_init
from calcy.core.viewdata import (
    CalcodeViewData,
    calcode_viewdata_init,
    calcode_viewdata_free,
    calcode_viewdata_build,
    calcode_viewdata_set_time,
)


def _update_current(lab: "CalcodeLab") -> None:
    """static void update_current(CalcodeLab *lab); (file-static in the C)"""
    if lab is None:
        return

    if calcode_viewdata_set_time(lab.view, lab.clock.t):
        calcode_gl_frame_set_current(
            lab.scene.frame,
            lab.clock.t,
            lab.view.current_a,
            lab.view.current_b,
            lab.view.current_c,
        )


class CalcodeLab:
    """typedef struct CalcodeLab { ... } CalcodeLab; (see calcode_lab.h)."""
    __slots__ = (
        "workspace", "scene", "clock", "input", "view",
        "initialized", "running",
        "curve_state", "phase_x", "phase_y",
        "trajectory_x", "trajectory_y", "trajectory_z",
    )

    def __init__(self):
        # Mirrors memset(lab, 0, sizeof(*lab)); every call site goes
        # through calcode_lab_init before use, same as the C. Fields
        # are given real objects (not None) so attribute access never
        # AttributeErrors even before calcode_lab_init runs, mirroring
        # the C's zero-initialized-in-place struct members.
        self.workspace = CalcodeWorkspace()
        self.scene = CalcodeGLScene()
        self.clock = CalcodeClock()
        self.input = CalcodeInputState()
        self.view = CalcodeViewData()

        self.initialized = 0
        self.running = 0

        self.curve_state = 0
        self.phase_x = 0
        self.phase_y = 0

        self.trajectory_x = 0
        self.trajectory_y = 0
        self.trajectory_z = 0


def calcode_lab_init(lab: Optional[CalcodeLab]) -> None:
    """void calcode_lab_init(CalcodeLab *lab);"""
    if lab is None:
        return

    lab.workspace = CalcodeWorkspace()
    lab.scene = CalcodeGLScene()
    lab.input = CalcodeInputState()
    lab.view = CalcodeViewData()
    lab.clock = CalcodeClock()

    calcode_workspace_init(lab.workspace)
    calcode_gl_scene_init(lab.scene)
    calcode_input_init(lab.input)
    calcode_viewdata_init(lab.view)

    calcode_clock_init(lab.clock, 0.0, 1.0)

    lab.curve_state = 0
    lab.phase_x = 0
    lab.phase_y = 1

    lab.trajectory_x = 0
    lab.trajectory_y = 1
    lab.trajectory_z = 0

    lab.initialized = 1
    lab.running = 1


def calcode_lab_shutdown(lab: Optional[CalcodeLab]) -> None:
    """void calcode_lab_shutdown(CalcodeLab *lab);"""
    if lab is None:
        return

    calcode_viewdata_free(lab.view)
    calcode_experiment_free(lab.workspace.experiment)

    lab.initialized = 0
    lab.running = 0


def calcode_lab_load(lab: Optional[CalcodeLab], filename: Optional[str]) -> int:
    """int calcode_lab_load(CalcodeLab *lab, const char *filename);"""
    if lab is None or not filename:
        return 0

    if not calcode_workspace_load(lab.workspace, filename):
        return 0

    return calcode_lab_solve(lab)


def calcode_lab_rebuild_view(lab: Optional[CalcodeLab]) -> int:
    """int calcode_lab_rebuild_view(CalcodeLab *lab);"""
    if lab is None or not calcode_workspace_is_solution_current(lab.workspace):
        return 0

    if not calcode_viewdata_build(
        lab.workspace.experiment.solution,
        lab.curve_state,
        lab.phase_x,
        lab.phase_y,
        lab.trajectory_x,
        lab.trajectory_y,
        lab.trajectory_z,
        lab.view,
    ):
        return 0

    calcode_clock_init(
        lab.clock,
        lab.workspace.problem.model.x0,
        lab.workspace.problem.model.x1,
    )

    lab.clock.loop = 1

    _update_current(lab)

    return 1


def calcode_lab_solve(lab: Optional[CalcodeLab]) -> int:
    """int calcode_lab_solve(CalcodeLab *lab);"""
    if lab is None:
        return 0

    if not calcode_workspace_solve(lab.workspace):
        return 0

    return calcode_lab_rebuild_view(lab)


def calcode_lab_tick(lab: Optional[CalcodeLab], wall_time: float) -> None:
    """void calcode_lab_tick(CalcodeLab *lab, double wall_time);"""
    if lab is None or not lab.running:
        return

    calcode_clock_tick(lab.clock, wall_time)

    _update_current(lab)


def calcode_lab_action(lab: Optional[CalcodeLab], action: CalcodeInputAction) -> None:
    """void calcode_lab_action(CalcodeLab *lab, CalcodeInputAction action);"""
    if lab is None:
        return

    A = CalcodeInputAction

    if action == A.CALCODE_INPUT_PLAY_PAUSE:
        calcode_clock_toggle(lab.clock)

    elif action == A.CALCODE_INPUT_RESET:
        calcode_clock_reset(lab.clock)

    elif action == A.CALCODE_INPUT_STEP_FORWARD:
        calcode_clock_set_time(
            lab.clock,
            lab.clock.t + 0.01 * (lab.clock.t1 - lab.clock.t0),
        )

    elif action == A.CALCODE_INPUT_STEP_BACKWARD:
        calcode_clock_set_time(
            lab.clock,
            lab.clock.t - 0.01 * (lab.clock.t1 - lab.clock.t0),
        )

    elif action == A.CALCODE_INPUT_SPEED_UP:
        calcode_clock_set_speed(lab.clock, lab.clock.speed * 2.0)

    elif action == A.CALCODE_INPUT_SPEED_DOWN:
        calcode_clock_set_speed(lab.clock, lab.clock.speed * 0.5)

    elif action == A.CALCODE_INPUT_CAMERA_LEFT:
        calcode_gl_scene_orbit(lab.scene, -5.0, 0.0)

    elif action == A.CALCODE_INPUT_CAMERA_RIGHT:
        calcode_gl_scene_orbit(lab.scene, 5.0, 0.0)

    elif action == A.CALCODE_INPUT_CAMERA_UP:
        calcode_gl_scene_orbit(lab.scene, 0.0, 5.0)

    elif action == A.CALCODE_INPUT_CAMERA_DOWN:
        calcode_gl_scene_orbit(lab.scene, 0.0, -5.0)

    elif action == A.CALCODE_INPUT_ZOOM_IN:
        calcode_gl_scene_zoom(lab.scene, 0.8)

    elif action == A.CALCODE_INPUT_ZOOM_OUT:
        calcode_gl_scene_zoom(lab.scene, 1.25)

    elif action == A.CALCODE_INPUT_GRAPH:
        lab.scene.mode = CalcodeGLSceneMode.CALCODE_SCENE_GRAPH

    elif action == A.CALCODE_INPUT_PHASE:
        lab.scene.mode = CalcodeGLSceneMode.CALCODE_SCENE_PHASE

    elif action == A.CALCODE_INPUT_3D:
        lab.scene.mode = CalcodeGLSceneMode.CALCODE_SCENE_3D

    elif action == A.CALCODE_INPUT_SPLIT:
        lab.scene.mode = CalcodeGLSceneMode.CALCODE_SCENE_SPLIT

    elif action == A.CALCODE_INPUT_QUIT:
        lab.running = 0

    # default: break; (no-op for CALCODE_INPUT_NONE and any other value)

    _update_current(lab)


def calcode_lab_mouse_drag(lab: Optional[CalcodeLab], dx: float, dy: float) -> None:
    """void calcode_lab_mouse_drag(CalcodeLab *lab, double dx, double dy);"""
    if lab is None:
        return

    calcode_gl_scene_orbit(lab.scene, dx * 0.5, -dy * 0.5)


def calcode_lab_mouse_wheel(lab: Optional[CalcodeLab], wheel: float) -> None:
    """void calcode_lab_mouse_wheel(CalcodeLab *lab, double wheel);"""
    if lab is None or wheel == 0.0:
        return

    if wheel > 0.0:
        calcode_gl_scene_zoom(lab.scene, 0.85)
    else:
        calcode_gl_scene_zoom(lab.scene, 1.18)
