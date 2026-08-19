"""calcode_model.py -- exact Python port of calcode_model.c / calcode_model.h.

Original: the mathematical experiment is the central object of the program.

Canonical form:

         y' = f(x, y, k)
         y(x0) = y0

The model contains no GUI and no renderer. It is the common source for
symbolic compilation, numerical integration, report, graph, phase-space
analysis and 3D geometry. This is intentionally a coordinator around the
project's existing expr -> odesys -> odesolution pipeline (expr.py /
odesys.py / odesolution.py).

PORT NOTES:

- C's fixed-size char buffers (`char name[CALCODE_NAME_MAX]`,
  `char rhs[ODESYS_MAX_EQNS][CALCODE_EXPR_MAX]`, `char error[CALCODE_ERROR_MAX]`)
  become plain Python strings, but truncation on assignment is preserved
  via `_cstr()`, which mimics `snprintf(dst, cap, "%s", src)` exactly
  (keeps the first cap-1 characters). This matters because the original
  silently truncates over-length names/expressions/errors rather than
  erroring, and this port keeps that exact (mis)behavior.

- `int calcode_model_validate(const CalcodeModel *model, char *error,
  int error_len)` had `error`/`error_len` as an output buffer pair.
  Python has no output buffer, so `calcode_model_validate()` here returns
  `(ok, message)` instead -- `message` is truncated to `error_len` exactly
  as the C `snprintf` calls were, and is "" when `ok` is 1 (mirroring
  `error[0] = '\\0'` at the top of the C function).

- `odesys_compile` returning NULL + writing into an `errbuf` becomes
  raising `ODESysError` in odesys.py; `calcode_experiment_compile` here
  catches that exception and copies its message into `experiment.error`,
  which is exactly what the C code achieved by passing `experiment->error`
  directly as the `errbuf` argument.

- `odesys_free` is a no-op in odesys.py (Python GC); calls to it are kept
  here only for literal call-site parity with the C control flow.
"""

from __future__ import annotations

import math
from enum import IntEnum
from typing import List, Optional, Tuple

from calcy.core.odesys import (
    ODESYS_MAX_EQNS,
    ODESYS_MAX_PARAMS,
    ODESys,
    ODESysError,
    odesys_compile,
    odesys_free,
)
from calcy.core.odesolution import ODESolution, odesolution_run

# #define CALCODE_NAME_MAX  128
# #define CALCODE_EXPR_MAX  512
# #define CALCODE_ERROR_MAX 1024
CALCODE_NAME_MAX = 128
CALCODE_EXPR_MAX = 512
CALCODE_ERROR_MAX = 1024


class CalcodeGeometryKind(IntEnum):
    """enum CalcodeGeometryKind -- values match the C enum exactly."""
    NONE = 0
    TIME_SERIES = 1
    PARTICLE_2D = 2
    PARTICLE_3D = 3
    PHASE_SPACE = 4
    FIELD_1D = 5
    FIELD_2D = 6


def _cstr(s: Optional[str], cap: int) -> str:
    """Mimic `snprintf(dst, cap, "%s", s)` into a fixed `char dst[cap]`
    buffer: keeps at most `cap - 1` characters (room for the NUL the C
    buffer needs but Python strings don't)."""
    if s is None:
        s = ""
    if cap <= 0:
        return ""
    return s[: cap - 1]


def _finite_positive(x: float) -> bool:
    return math.isfinite(x) and x > 0.0


def _dimensions_ok(n: int, p: int) -> bool:
    return 1 <= n <= ODESYS_MAX_EQNS and 0 <= p <= ODESYS_MAX_PARAMS


def _clear_solution(sol: Optional[ODESolution]) -> None:
    """static void clear_solution(ODESolution *s): ODESolution is a
    fixed-capacity structure; clearing status/count is sufficient to make
    the old trajectory unusable (matches the C comment exactly)."""
    if sol is None:
        return
    sol.npts = 0
    sol.neqns = 0
    sol.ok = 0


class CalcodeModel:
    """typedef struct CalcodeModel { ... } CalcodeModel; (see
    calcode_model.h). Always starts life reset to the C struct's default
    state -- mirrors every C call site, which never leaves a CalcodeModel
    un-reset before use."""
    __slots__ = (
        "name", "neqns", "nparams", "rhs", "y0", "k",
        "x0", "x1", "h0", "tol", "hmin", "hmax", "max_steps",
        "geometry", "geometry_x", "geometry_y", "geometry_z",
        "particle_count",
    )

    def __init__(self):
        calcode_model_reset(self)


class CalcodeExperiment:
    """typedef struct CalcodeExperiment { ... } CalcodeExperiment; (see
    calcode_model.h)."""
    __slots__ = ("model", "system", "solution", "compiled", "generation", "error")

    def __init__(self):
        calcode_experiment_init(self)


# ---------------------------------------------------------------------------
# Model lifecycle
# ---------------------------------------------------------------------------

def calcode_model_reset(model: CalcodeModel) -> None:
    """void calcode_model_reset(CalcodeModel *model): memset(model, 0, ...)
    followed by the C function's explicit defaults."""
    if model is None:
        return

    model.name = ""
    model.neqns = 1
    model.nparams = 0
    model.rhs = ["" for _ in range(ODESYS_MAX_EQNS)]
    model.y0 = [0.0] * ODESYS_MAX_EQNS
    model.k = [0.0] * ODESYS_MAX_PARAMS

    model.x0 = 0.0
    model.x1 = 20.0

    model.h0 = 0.01
    model.tol = 1e-6
    model.hmin = 1e-8
    model.hmax = 0.1
    model.max_steps = 1000000

    model.geometry = CalcodeGeometryKind.TIME_SERIES
    model.geometry_x = 0
    model.geometry_y = 1
    model.geometry_z = 2
    model.particle_count = 1


def calcode_model_init(model: CalcodeModel, name: Optional[str],
                        neqns: int, nparams: int) -> None:
    """void calcode_model_init(CalcodeModel *model, const char *name,
                                int neqns, int nparams);"""
    if model is None:
        return

    calcode_model_reset(model)

    if not _dimensions_ok(neqns, nparams):
        # Keep a valid minimal model rather than creating an object whose
        # fixed arrays cannot represent its declared dimensions.
        return

    model.neqns = neqns
    model.nparams = nparams

    if name:
        model.name = _cstr(name, CALCODE_NAME_MAX)
    else:
        model.name = _cstr("Untitled", CALCODE_NAME_MAX)


def calcode_model_set_name(model: CalcodeModel, name: Optional[str]) -> int:
    """int calcode_model_set_name(CalcodeModel *model, const char *name);"""
    if not model or not name:
        return 0

    model.name = _cstr(name, CALCODE_NAME_MAX)
    return 1


def calcode_model_set_dimensions(model: CalcodeModel, neqns: int, nparams: int) -> int:
    """int calcode_model_set_dimensions(CalcodeModel *model, int neqns, int nparams);"""
    if not model or not _dimensions_ok(neqns, nparams):
        return 0

    model.neqns = neqns
    model.nparams = nparams

    # Values outside the new dimensions are retained in memory but are no
    # longer semantically part of the model. This makes dimension changes
    # non-destructive for an editor that temporarily changes the count.
    return 1


def calcode_model_set_rhs(model: CalcodeModel, equation: int, rhs: Optional[str]) -> int:
    """int calcode_model_set_rhs(CalcodeModel *model, int equation, const char *rhs);"""
    if not model or rhs is None:
        return 0

    if equation < 0 or equation >= model.neqns:
        return 0

    if not rhs:
        return 0

    model.rhs[equation] = _cstr(rhs, CALCODE_EXPR_MAX)
    return 1


def calcode_model_set_initial(model: CalcodeModel, state: int, value: float) -> int:
    """int calcode_model_set_initial(CalcodeModel *model, int state, double value);"""
    if not model or state < 0 or state >= model.neqns:
        return 0

    if not math.isfinite(value):
        return 0

    model.y0[state] = value
    return 1


def calcode_model_set_parameter(model: CalcodeModel, parameter: int, value: float) -> int:
    """int calcode_model_set_parameter(CalcodeModel *model, int parameter, double value);"""
    if not model or parameter < 0 or parameter >= model.nparams:
        return 0

    if not math.isfinite(value):
        return 0

    model.k[parameter] = value
    return 1


def calcode_model_set_domain(model: CalcodeModel, x0: float, x1: float) -> int:
    """int calcode_model_set_domain(CalcodeModel *model, double x0, double x1);"""
    if not model or not math.isfinite(x0) or not math.isfinite(x1):
        return 0

    if x1 <= x0:
        return 0

    model.x0 = x0
    model.x1 = x1
    return 1


def calcode_model_set_solver(model: CalcodeModel, h0: float, tol: float,
                              hmin: float, hmax: float, max_steps: int) -> int:
    """int calcode_model_set_solver(CalcodeModel *model, double h0, double tol,
                                     double hmin, double hmax, int max_steps);"""
    if not model:
        return 0

    if (not _finite_positive(h0) or not _finite_positive(tol) or
            not _finite_positive(hmin) or not _finite_positive(hmax) or
            max_steps <= 0):
        return 0

    if hmin > hmax:
        return 0

    model.h0 = h0
    model.tol = tol
    model.hmin = hmin
    model.hmax = hmax
    model.max_steps = max_steps
    return 1


def calcode_model_set_geometry(model: CalcodeModel, kind: "CalcodeGeometryKind",
                                x_state: int, y_state: int, z_state: int) -> int:
    """int calcode_model_set_geometry(CalcodeModel *model, CalcodeGeometryKind kind,
                                       int x_state, int y_state, int z_state);"""
    if not model:
        return 0

    if x_state < 0 or x_state >= model.neqns:
        return 0

    if kind in (CalcodeGeometryKind.PARTICLE_2D, CalcodeGeometryKind.PHASE_SPACE):
        if y_state < 0 or y_state >= model.neqns:
            return 0

    if kind == CalcodeGeometryKind.PARTICLE_3D:
        if (y_state < 0 or y_state >= model.neqns or
                z_state < 0 or z_state >= model.neqns):
            return 0

    model.geometry = kind
    model.geometry_x = x_state
    model.geometry_y = y_state
    model.geometry_z = z_state
    return 1


def calcode_model_validate(model: Optional[CalcodeModel],
                            error_len: int = CALCODE_ERROR_MAX) -> Tuple[int, str]:
    """int calcode_model_validate(const CalcodeModel *model, char *error, int error_len);
    Returns (ok, message) instead of writing through an output buffer --
    see the module docstring's PORT NOTES. `message` is "" when ok == 1."""
    if error_len <= 0:
        return 0, ""

    if model is None:
        return 0, _cstr("model is NULL", error_len)

    if not _dimensions_ok(model.neqns, model.nparams):
        return 0, _cstr(
            f"invalid dimensions: equations={model.neqns} parameters={model.nparams}",
            error_len)

    if not model.name:
        return 0, _cstr("model has no name", error_len)

    if (not math.isfinite(model.x0) or not math.isfinite(model.x1) or
            model.x1 <= model.x0):
        return 0, _cstr("invalid independent-variable range", error_len)

    if (not _finite_positive(model.h0) or not _finite_positive(model.tol) or
            not _finite_positive(model.hmin) or not _finite_positive(model.hmax) or
            model.hmin > model.hmax or model.max_steps <= 0):
        return 0, _cstr("invalid numerical controls", error_len)

    for i in range(model.neqns):
        if not model.rhs[i]:
            return 0, _cstr(f"missing RHS for y{i + 1}'", error_len)

        if not math.isfinite(model.y0[i]):
            return 0, _cstr(f"initial value y{i + 1} is not finite", error_len)

    for i in range(model.nparams):
        if not math.isfinite(model.k[i]):
            return 0, _cstr(f"parameter k{i + 1} is not finite", error_len)

    return 1, ""


# ---------------------------------------------------------------------------
# Experiment lifecycle
# ---------------------------------------------------------------------------

def calcode_experiment_init(experiment: CalcodeExperiment) -> None:
    """void calcode_experiment_init(CalcodeExperiment *experiment):
    memset(experiment, 0, ...); calcode_model_reset(&experiment->model);
    experiment->generation = 1;"""
    if experiment is None:
        return

    experiment.model = CalcodeModel()  # already reset by its own __init__
    experiment.system = None
    experiment.solution = ODESolution()  # already zeroed by its own __init__
    experiment.compiled = 0
    experiment.error = ""
    experiment.generation = 1


def _set_error(experiment: Optional[CalcodeExperiment], text: Optional[str]) -> None:
    """static void set_error(CalcodeExperiment *e, const char *text);"""
    if experiment is None:
        return

    if not text:
        text = "unknown error"

    experiment.error = _cstr(text, CALCODE_ERROR_MAX)


def calcode_experiment_invalidate_solution(experiment: Optional[CalcodeExperiment]) -> None:
    """void calcode_experiment_invalidate_solution(CalcodeExperiment *experiment);"""
    if experiment is None:
        return

    _clear_solution(experiment.solution)
    experiment.generation += 1


def calcode_experiment_compile(experiment: Optional[CalcodeExperiment]) -> int:
    """int calcode_experiment_compile(CalcodeExperiment *experiment);"""
    if experiment is None:
        return 0

    experiment.error = ""

    # If the symbolic model changes, the old compiled tape is no longer
    # authoritative.
    if experiment.system is not None:
        odesys_free(experiment.system)
        experiment.system = None

    experiment.compiled = 0
    _clear_solution(experiment.solution)

    ok, msg = calcode_model_validate(experiment.model, CALCODE_ERROR_MAX)
    if not ok:
        experiment.error = msg
        return 0

    rhs: List[str] = [experiment.model.rhs[i] for i in range(experiment.model.neqns)]

    try:
        experiment.system = odesys_compile(
            rhs, experiment.model.neqns, experiment.model.nparams)
    except ODESysError as exc:
        # Matches the C code passing experiment->error directly as
        # odesys_compile's errbuf.
        experiment.system = None
        experiment.compiled = 0
        _set_error(experiment, str(exc))
        return 0

    experiment.compiled = 1
    return 1


def calcode_experiment_run(experiment: Optional[CalcodeExperiment]) -> int:
    """int calcode_experiment_run(CalcodeExperiment *experiment);"""
    if experiment is None:
        return 0

    experiment.error = ""

    if not experiment.compiled or experiment.system is None:
        _set_error(experiment, "model has not been compiled")
        _clear_solution(experiment.solution)
        return 0

    # One integration. All later views consume this exact trajectory.
    odesolution_run(
        experiment.solution,
        experiment.system,
        experiment.model.x0,
        experiment.model.x1,
        experiment.model.y0,
        experiment.model.k,
        experiment.model.h0,
        experiment.model.tol,
        experiment.model.hmin,
        experiment.model.hmax,
        experiment.model.max_steps,
    )

    if not experiment.solution.ok:
        _set_error(experiment, "integration completed without a usable trajectory")
        return 0

    experiment.generation += 1
    return 1


def calcode_experiment_solve(experiment: Optional[CalcodeExperiment]) -> int:
    """int calcode_experiment_solve(CalcodeExperiment *experiment);"""
    if experiment is None:
        return 0

    if not experiment.compiled or experiment.system is None:
        if not calcode_experiment_compile(experiment):
            return 0

    return calcode_experiment_run(experiment)


def calcode_experiment_set_parameter(experiment: Optional[CalcodeExperiment],
                                      parameter: int, value: float) -> int:
    """int calcode_experiment_set_parameter(CalcodeExperiment *experiment,
                                             int parameter, double value);"""
    if experiment is None:
        return 0

    if not calcode_model_set_parameter(experiment.model, parameter, value):
        return 0

    # Parameters are runtime values in ODESys; changing them does not
    # require reparsing the RHS expressions.
    calcode_experiment_invalidate_solution(experiment)
    return 1


def calcode_experiment_set_initial(experiment: Optional[CalcodeExperiment],
                                    state: int, value: float) -> int:
    """int calcode_experiment_set_initial(CalcodeExperiment *experiment,
                                           int state, double value);"""
    if experiment is None:
        return 0

    if not calcode_model_set_initial(experiment.model, state, value):
        return 0

    calcode_experiment_invalidate_solution(experiment)
    return 1


def calcode_experiment_free(experiment: Optional[CalcodeExperiment]) -> None:
    """void calcode_experiment_free(CalcodeExperiment *experiment);"""
    if experiment is None:
        return

    if experiment.system is not None:
        odesys_free(experiment.system)
        experiment.system = None

    experiment.compiled = 0
    _clear_solution(experiment.solution)


# ---------------------------------------------------------------------------
# Convenience queries
# ---------------------------------------------------------------------------

def calcode_experiment_error(experiment: Optional[CalcodeExperiment]) -> str:
    """const char *calcode_experiment_error(const CalcodeExperiment *experiment);"""
    if experiment is None:
        return "experiment is NULL"

    return experiment.error


def calcode_experiment_is_compiled(experiment: Optional[CalcodeExperiment]) -> bool:
    """int calcode_experiment_is_compiled(const CalcodeExperiment *experiment);"""
    return bool(experiment and experiment.compiled and experiment.system is not None)


def calcode_experiment_is_solved(experiment: Optional[CalcodeExperiment]) -> bool:
    """int calcode_experiment_is_solved(const CalcodeExperiment *experiment);"""
    return bool(experiment and experiment.solution.ok and experiment.solution.npts > 1)
