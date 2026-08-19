"""calcode_problem.py -- exact Python port of calcode_problem.c / calcode_problem.h.

Original: a persistent mathematical problem description -- the object
that will eventually sit behind File->New / File->Open / File->Save and
the graphical equation editor. Deliberately separate from
CalcodeExperiment:

     CalcodeProblem    = description
     CalcodeExperiment = compiled + solved instance

PORT NOTES:

- `problem->notes[2048]` (a fixed char buffer never touched by any
  function in this file) becomes a plain Python string, initialized to
  "" by memset(0) semantics -- there is no setter in the original C
  either, so this port adds none.

- `experiment->model = problem->model;` is a full C struct copy (every
  fixed array copied by value). Python object references don't do that,
  so `calcode_problem_to_experiment` uses `_copy_model()` to reproduce
  the same by-value semantics -- otherwise the experiment and problem
  would end up aliasing the same CalcodeModel, which the original never
  does.
"""

from __future__ import annotations

from typing import Optional, Tuple

from calcy.core.model import (
    CALCODE_ERROR_MAX,
    CalcodeExperiment,
    CalcodeModel,
    calcode_experiment_init,
    calcode_model_init,
    calcode_model_set_domain,
    calcode_model_set_initial,
    calcode_model_set_parameter,
    calcode_model_set_rhs,
    calcode_model_set_solver,
    calcode_model_validate,
)

# #define CALCODE_PROBLEM_FORMAT_VERSION 1
CALCODE_PROBLEM_FORMAT_VERSION = 1


def _copy_model(dst: CalcodeModel, src: CalcodeModel) -> None:
    """Reproduce C's `dst->model = src->model;` full struct-copy semantics
    (every field copied by value, including the fixed arrays)."""
    dst.name = src.name
    dst.neqns = src.neqns
    dst.nparams = src.nparams
    dst.rhs = list(src.rhs)
    dst.y0 = list(src.y0)
    dst.k = list(src.k)
    dst.x0 = src.x0
    dst.x1 = src.x1
    dst.h0 = src.h0
    dst.tol = src.tol
    dst.hmin = src.hmin
    dst.hmax = src.hmax
    dst.max_steps = src.max_steps
    dst.geometry = src.geometry
    dst.geometry_x = src.geometry_x
    dst.geometry_y = src.geometry_y
    dst.geometry_z = src.geometry_z
    dst.particle_count = src.particle_count


class CalcodeProblem:
    """typedef struct CalcodeProblem { ... } CalcodeProblem; (see
    calcode_problem.h)."""
    __slots__ = ("format_version", "model", "notes", "revision")

    def __init__(self):
        # Mirrors memset(problem, 0, sizeof(*problem)) followed by the
        # explicit defaults calcode_problem_init sets; every C call site
        # goes through calcode_problem_init before use, same as here.
        self.format_version = 0
        self.model = CalcodeModel()
        self.notes = ""
        self.revision = 0


def calcode_problem_init(problem: Optional[CalcodeProblem], name: Optional[str],
                          neqns: int, nparams: int) -> None:
    """void calcode_problem_init(CalcodeProblem *problem, const char *name,
                                  int neqns, int nparams);"""
    if problem is None:
        return

    problem.format_version = CALCODE_PROBLEM_FORMAT_VERSION
    problem.model = CalcodeModel()
    problem.notes = ""

    calcode_model_init(problem.model, name, neqns, nparams)

    problem.revision = 1


def calcode_problem_touch(problem: Optional[CalcodeProblem]) -> None:
    """void calcode_problem_touch(CalcodeProblem *problem);"""
    if problem is None:
        return

    problem.revision += 1

    # C's `unsigned long` wraps to 0; Python ints don't, so this branch is
    # dead code in this port, kept only for line-for-line parity with the
    # original's overflow guard.
    if problem.revision == 0:
        problem.revision = 1


def calcode_problem_set_rhs(problem: Optional[CalcodeProblem],
                             equation: int, rhs: Optional[str]) -> int:
    """int calcode_problem_set_rhs(CalcodeProblem *problem, int equation, const char *rhs);"""
    if problem is None:
        return 0

    if not calcode_model_set_rhs(problem.model, equation, rhs):
        return 0

    calcode_problem_touch(problem)
    return 1


def calcode_problem_set_initial(problem: Optional[CalcodeProblem],
                                 state: int, value: float) -> int:
    """int calcode_problem_set_initial(CalcodeProblem *problem, int state, double value);"""
    if problem is None:
        return 0

    if not calcode_model_set_initial(problem.model, state, value):
        return 0

    calcode_problem_touch(problem)
    return 1


def calcode_problem_set_parameter(problem: Optional[CalcodeProblem],
                                   parameter: int, value: float) -> int:
    """int calcode_problem_set_parameter(CalcodeProblem *problem, int parameter, double value);"""
    if problem is None:
        return 0

    if not calcode_model_set_parameter(problem.model, parameter, value):
        return 0

    calcode_problem_touch(problem)
    return 1


def calcode_problem_set_domain(problem: Optional[CalcodeProblem],
                                x0: float, x1: float) -> int:
    """int calcode_problem_set_domain(CalcodeProblem *problem, double x0, double x1);"""
    if problem is None:
        return 0

    if not calcode_model_set_domain(problem.model, x0, x1):
        return 0

    calcode_problem_touch(problem)
    return 1


def calcode_problem_set_solver(problem: Optional[CalcodeProblem], h0: float, tol: float,
                                hmin: float, hmax: float, max_steps: int) -> int:
    """int calcode_problem_set_solver(CalcodeProblem *problem, double h0, double tol,
                                       double hmin, double hmax, int max_steps);"""
    if problem is None:
        return 0

    if not calcode_model_set_solver(problem.model, h0, tol, hmin, hmax, max_steps):
        return 0

    calcode_problem_touch(problem)
    return 1


def calcode_problem_validate(problem: Optional[CalcodeProblem],
                              error_len: int = CALCODE_ERROR_MAX) -> Tuple[int, str]:
    """int calcode_problem_validate(const CalcodeProblem *problem, char *error, int error_len);
    Returns (ok, message) -- see calcode_model.py's PORT NOTES for why."""
    if problem is None:
        if error_len > 0:
            return 0, "problem is NULL"
        return 0, ""

    if problem.format_version != CALCODE_PROBLEM_FORMAT_VERSION:
        if error_len > 0:
            return 0, f"unsupported problem format version {problem.format_version}"
        return 0, ""

    return calcode_model_validate(problem.model, error_len)


def calcode_problem_to_experiment(problem: Optional[CalcodeProblem],
                                   experiment: Optional[CalcodeExperiment]) -> int:
    """int calcode_problem_to_experiment(const CalcodeProblem *problem,
                                          CalcodeExperiment *experiment);"""
    if problem is None or experiment is None:
        return 0

    ok, error = calcode_problem_validate(problem, CALCODE_ERROR_MAX)

    if not ok:
        calcode_experiment_init(experiment)
        experiment.error = error[: CALCODE_ERROR_MAX - 1]
        return 0

    calcode_experiment_init(experiment)

    # Copy the mathematical description. Compilation is intentionally
    # deferred so the caller can inspect/edit the problem before solving.
    _copy_model(experiment.model, problem.model)

    return 1
