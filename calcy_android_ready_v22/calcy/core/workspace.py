"""calcode_workspace.py -- exact Python port of calcode_workspace.c /
calcode_workspace.h.

Original: the top-level UI-facing object -- one CalcodeProblem (what the
user is editing) plus one CalcodeExperiment (the compiled/solved
instance), a state machine over {EMPTY, EDITING, COMPILED, SOLVED,
ERROR}, and a one-line status message for the status bar.

PORT NOTES:

- `w->problem = p;` in `calcode_workspace_load` is a full C struct copy
  (the freshly-loaded CalcodeProblem overwrites the workspace's problem
  by value). Python assignment would instead alias `w.problem` to the
  local `p` object -- harmless here since `p` is never touched again
  after the assignment, so aliasing and copying are observationally
  identical. No `_copy_problem` helper is needed for that reason alone,
  but this port still does not reuse the old `w.problem` object, mirror-
  ing the C which discards the old value's storage rather than mutating
  it in place.

- `char message[CALCODE_WORKSPACE_MAX_MESSAGE]` (1024 bytes) is a fixed
  buffer filled via `snprintf(w->message, sizeof(w->message), "%s", s)`.
  Reused `_cstr()` from calcode_model.py reproduces the same truncation
  behavior for a plain Python string.

- `calcode_workspace_message` returns the literal C string
  "workspace is NULL" when passed NULL; kept verbatim since it's
  user/status-bar-visible text, not an internal error code.
"""

from __future__ import annotations

from typing import Optional

from calcy.core.model import (
    CALCODE_ERROR_MAX,
    CalcodeExperiment,
    _cstr,
    calcode_experiment_compile,
    calcode_experiment_error,
    calcode_experiment_free,
    calcode_experiment_init,
    calcode_experiment_is_solved,
    calcode_experiment_run,
)
from calcy.core.problem import (
    CalcodeProblem,
    calcode_problem_init,
    calcode_problem_set_initial,
    calcode_problem_set_parameter,
    calcode_problem_set_rhs,
    calcode_problem_to_experiment,
)
from calcy.core.problem_io import calcode_problem_load, calcode_problem_save

# #define CALCODE_WORKSPACE_MAX_MESSAGE 1024
CALCODE_WORKSPACE_MAX_MESSAGE = 1024

# typedef enum {CALCODE_WS_EMPTY=0,CALCODE_WS_EDITING,CALCODE_WS_COMPILED,
#               CALCODE_WS_SOLVED,CALCODE_WS_ERROR} CalcodeWorkspaceState;
CALCODE_WS_EMPTY = 0
CALCODE_WS_EDITING = 1
CALCODE_WS_COMPILED = 2
CALCODE_WS_SOLVED = 3
CALCODE_WS_ERROR = 4


class CalcodeWorkspace:
    """typedef struct CalcodeWorkspace { ... } CalcodeWorkspace; (see
    calcode_workspace.h)."""
    __slots__ = (
        "problem", "experiment", "state", "solved_revision",
        "selected_state", "selected_parameter",
        "graph_x0", "graph_x1",
        "camera_azimuth", "camera_elevation", "camera_distance",
        "message",
    )

    def __init__(self):
        # Mirrors `memset(w, 0, sizeof(*w))` -- every call site goes
        # through calcode_workspace_init before use, same as the C.
        self.problem = CalcodeProblem()
        self.experiment = CalcodeExperiment()
        self.state = CALCODE_WS_EMPTY
        self.solved_revision = 0
        self.selected_state = 0
        self.selected_parameter = 0
        self.graph_x0 = 0.0
        self.graph_x1 = 0.0
        self.camera_azimuth = 0.0
        self.camera_elevation = 0.0
        self.camera_distance = 0.0
        self.message = ""


def _msg(w: Optional[CalcodeWorkspace], s: Optional[str]) -> None:
    """static void msg(CalcodeWorkspace *w, const char *s);"""
    if w is None:
        return
    w.message = _cstr(s, CALCODE_WORKSPACE_MAX_MESSAGE)


def calcode_workspace_init(w: Optional[CalcodeWorkspace]) -> None:
    """void calcode_workspace_init(CalcodeWorkspace *w);"""
    if w is None:
        return

    w.problem = CalcodeProblem()
    w.experiment = CalcodeExperiment()
    calcode_problem_init(w.problem, "Untitled", 1, 0)
    calcode_experiment_init(w.experiment)

    w.state = CALCODE_WS_EDITING
    w.graph_x0 = w.problem.model.x0
    w.graph_x1 = w.problem.model.x1
    w.camera_azimuth = 45
    w.camera_elevation = 25
    w.camera_distance = 6

    _msg(w, "New CALCODE problem")


def calcode_workspace_new(w: Optional[CalcodeWorkspace], n: Optional[str],
                           ne: int, np_: int) -> None:
    """void calcode_workspace_new(CalcodeWorkspace *w, const char *n, int ne, int np);"""
    if w is None:
        return

    calcode_experiment_free(w.experiment)
    w.problem = CalcodeProblem()
    calcode_problem_init(w.problem, n if n else "Untitled", ne, np_)
    w.experiment = CalcodeExperiment()
    calcode_experiment_init(w.experiment)

    w.state = CALCODE_WS_EDITING
    w.solved_revision = 0
    w.selected_state = 0
    w.selected_parameter = 0
    w.graph_x0 = w.problem.model.x0
    w.graph_x1 = w.problem.model.x1

    _msg(w, "New CALCODE problem")


def calcode_workspace_load(w: Optional[CalcodeWorkspace], f: Optional[str]) -> int:
    """int calcode_workspace_load(CalcodeWorkspace *w, const char *f);"""
    if w is None or not f:
        return 0

    p = CalcodeProblem()
    ok, e = calcode_problem_load(p, f, CALCODE_ERROR_MAX)
    if not ok:
        w.state = CALCODE_WS_ERROR
        _msg(w, e)
        return 0

    calcode_experiment_free(w.experiment)
    w.problem = p
    w.experiment = CalcodeExperiment()
    calcode_experiment_init(w.experiment)

    w.state = CALCODE_WS_EDITING
    w.solved_revision = 0
    w.graph_x0 = p.model.x0
    w.graph_x1 = p.model.x1

    _msg(w, "Problem loaded")
    return 1


def calcode_workspace_save(w: Optional[CalcodeWorkspace], f: Optional[str]) -> int:
    """int calcode_workspace_save(CalcodeWorkspace *w, const char *f);"""
    if w is None or not f:
        return 0

    ok, e = calcode_problem_save(w.problem, f, CALCODE_ERROR_MAX)
    if not ok:
        w.state = CALCODE_WS_ERROR
        _msg(w, e)
        return 0

    _msg(w, "Problem saved")
    return 1


def calcode_workspace_compile(w: Optional[CalcodeWorkspace]) -> int:
    """int calcode_workspace_compile(CalcodeWorkspace *w);"""
    if w is None:
        return 0

    if not calcode_problem_to_experiment(w.problem, w.experiment):
        w.state = CALCODE_WS_ERROR
        _msg(w, calcode_experiment_error(w.experiment))
        return 0

    if not calcode_experiment_compile(w.experiment):
        w.state = CALCODE_WS_ERROR
        _msg(w, calcode_experiment_error(w.experiment))
        return 0

    w.state = CALCODE_WS_COMPILED
    _msg(w, "Equation system compiled")
    return 1


def calcode_workspace_solve(w: Optional[CalcodeWorkspace]) -> int:
    """int calcode_workspace_solve(CalcodeWorkspace *w);"""
    if w is None:
        return 0

    if not calcode_workspace_compile(w):
        return 0

    if not calcode_experiment_run(w.experiment):
        w.state = CALCODE_WS_ERROR
        _msg(w, calcode_experiment_error(w.experiment))
        return 0

    w.solved_revision = w.problem.revision
    w.state = CALCODE_WS_SOLVED
    w.graph_x0 = w.problem.model.x0
    w.graph_x1 = w.problem.model.x1

    _msg(w, "Numerical solution ready")
    return 1


def _edited(w: Optional[CalcodeWorkspace]) -> None:
    """static void edited(CalcodeWorkspace *w);"""
    if w is None:
        return
    calcode_experiment_free(w.experiment)
    w.state = CALCODE_WS_EDITING
    w.solved_revision = 0
    _msg(w, "Problem edited; solution is stale")


def calcode_workspace_set_rhs(w: Optional[CalcodeWorkspace], i: int,
                               s: Optional[str]) -> int:
    """int calcode_workspace_set_rhs(CalcodeWorkspace *w, int i, const char *s);"""
    if w is None or not calcode_problem_set_rhs(w.problem, i, s):
        return 0
    _edited(w)
    return 1


def calcode_workspace_set_parameter(w: Optional[CalcodeWorkspace], i: int,
                                     v: float) -> int:
    """int calcode_workspace_set_parameter(CalcodeWorkspace *w, int i, double v);"""
    if w is None or not calcode_problem_set_parameter(w.problem, i, v):
        return 0
    _edited(w)
    return 1


def calcode_workspace_set_initial(w: Optional[CalcodeWorkspace], i: int,
                                   v: float) -> int:
    """int calcode_workspace_set_initial(CalcodeWorkspace *w, int i, double v);"""
    if w is None or not calcode_problem_set_initial(w.problem, i, v):
        return 0
    _edited(w)
    return 1


def calcode_workspace_is_solution_current(w: Optional[CalcodeWorkspace]) -> int:
    """int calcode_workspace_is_solution_current(const CalcodeWorkspace *w);"""
    return int(
        w is not None
        and w.state == CALCODE_WS_SOLVED
        and w.solved_revision == w.problem.revision
        and calcode_experiment_is_solved(w.experiment)
    )


def calcode_workspace_select_state(w: Optional[CalcodeWorkspace], i: int) -> None:
    """void calcode_workspace_select_state(CalcodeWorkspace *w, int i);"""
    if w is not None and 0 <= i < w.problem.model.neqns:
        w.selected_state = i


def calcode_workspace_select_parameter(w: Optional[CalcodeWorkspace], i: int) -> None:
    """void calcode_workspace_select_parameter(CalcodeWorkspace *w, int i);"""
    if w is not None and 0 <= i < w.problem.model.nparams:
        w.selected_parameter = i


def calcode_workspace_message(w: Optional[CalcodeWorkspace]) -> str:
    """const char *calcode_workspace_message(const CalcodeWorkspace *w);"""
    return w.message if w is not None else "workspace is NULL"
