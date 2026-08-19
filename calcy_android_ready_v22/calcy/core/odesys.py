"""odesys.py -- exact Python port of odesys.c / odesys.h.

Original: compiles a system of N first-order ODEs (Calcauchy's "standard
form": y1'..yN' = f_i(x, y1..yN, k1..kN)) and steps it forward with an
adaptive RK4, generalizing sim_vdp.c's step-doubling scheme from a
hardcoded 2D state to N dimensions. Built on top of expr.py, mirroring the
original's layering on expr.c/expr.h.

PORT NOTES:

- C has no pointers in Python, so wherever the original signature takes a
  `double *x` or `double *y` as an in/out scalar/vector parameter, this
  port takes a Python list and mutates it in place:
    * `y` (the state vector) was already a pointer to an array in C, so a
      Python list of floats is a direct, natural translation -- mutated
      in place exactly as C did.
    * `x` (a single double, passed as `double *x` so the callee can advance
      it) is represented here as a 1-element list acting as a mutable box;
      read/write it via `x[0]`, not as a plain float.
  This mirrors the exact call-site semantics of the C code (the caller's
  x/y are visibly updated after the call) without pretending Python has
  pointers.

- odesys_compile returning NULL + errbuf becomes raising ODESysError with
  the identical message text (including the "y%d': %s" wrapping around an
  underlying ExprError from expr.py, exactly as the C source formats it).

- odesys_free is a no-op (Python GC), kept only for literal call-site
  parity with code translated from C that still calls it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from calcy.core.expr import Expr, ExprError, expr_compile, expr_eval, expr_free

# #define ODESYS_MAX_EQNS   16
# #define ODESYS_MAX_PARAMS 16
ODESYS_MAX_EQNS = 16
ODESYS_MAX_PARAMS = 16

# #define ODESYS_VARNAME_LEN 8  (kept only as documentation; Python strings
# have no fixed-length buffer, so this constant has no code effect here.)
ODESYS_VARNAME_LEN = 8
ODESYS_MAX_VARS = 1 + ODESYS_MAX_EQNS + ODESYS_MAX_PARAMS


class ODESysError(Exception):
    """Raised in place of C's odesys_compile returning NULL + errbuf."""
    pass


class ODESys:
    """struct ODESys { Expr *eqns[ODESYS_MAX_EQNS]; int neqns; int nparams;
    int nvars; };"""
    __slots__ = ("eqns", "neqns", "nparams", "nvars")

    def __init__(self):
        self.eqns: List[Optional[Expr]] = []
        self.neqns: int = 0
        self.nparams: int = 0
        self.nvars: int = 0


def odesys_neqns(sys: ODESys) -> int:
    return sys.neqns


def odesys_nparams(sys: ODESys) -> int:
    return sys.nparams


def odesys_compile(rhs: Sequence[str], neqns: int, nparams: int) -> ODESys:
    """ODESys *odesys_compile(const char *rhs[], int neqns, int nparams,
                               char *errbuf, int errbuf_len);
    Raises ODESysError instead of returning NULL + errbuf."""
    if neqns <= 0 or neqns > ODESYS_MAX_EQNS:
        raise ODESysError(f"neqns={neqns} out of range (1..{ODESYS_MAX_EQNS})")
    if nparams < 0 or nparams > ODESYS_MAX_PARAMS:
        raise ODESysError(f"nparams={nparams} out of range (0..{ODESYS_MAX_PARAMS})")

    nvars = 1 + neqns + nparams
    varnames: List[str] = ["x"]
    for i in range(neqns):
        varnames.append(f"y{i + 1}")
    for i in range(nparams):
        varnames.append(f"k{i + 1}")

    sys = ODESys()
    sys.neqns = neqns
    sys.nparams = nparams
    sys.nvars = nvars
    sys.eqns = [None] * neqns

    for i in range(neqns):
        try:
            e = expr_compile(rhs[i], varnames, nvars)
        except ExprError as localerr:
            # matches: snprintf(errbuf, errbuf_len, "y%d': %s", i + 1, localerr);
            for j in range(i):
                expr_free(sys.eqns[j])
            raise ODESysError(f"y{i + 1}': {localerr}") from localerr
        sys.eqns[i] = e
    return sys


def odesys_free(sys: Optional[ODESys]) -> None:
    """No-op in Python; kept for literal call-site parity."""
    if sys is None:
        return
    for i in range(sys.neqns):
        expr_free(sys.eqns[i])


def odesys_eval(sys: ODESys, x: float, y: Sequence[float],
                 k: Optional[Sequence[float]], dydx: List[float]) -> None:
    """void odesys_eval(const ODESys *sys, double x, const double *y,
                         const double *k, double *dydx);
    dydx is a pre-sized list of length >= sys.neqns, mutated in place
    (this is the C function's one true output pointer parameter)."""
    values = [0.0] * sys.nvars
    values[0] = x
    for i in range(sys.neqns):
        values[1 + i] = y[i]
    for i in range(sys.nparams):
        values[1 + sys.neqns + i] = k[i]

    for i in range(sys.neqns):
        v = expr_eval(sys.eqns[i], values)
        dydx[i] = v if math.isfinite(v) else 0.0


@dataclass
class ODEStepper:
    """typedef struct ODEStepper { double h; double tol; double hmin, hmax; }
    ODEStepper;"""
    h: float = 0.0
    tol: float = 0.0
    hmin: float = 0.0
    hmax: float = 0.0


def odestepper_init(st: ODEStepper, h0: float, tol: float,
                     hmin: float, hmax: float) -> None:
    st.h = h0
    st.tol = tol
    st.hmin = hmin
    st.hmax = hmax


def _rk4_full(sys: ODESys, x: float, y: Sequence[float],
              k: Optional[Sequence[float]], h: float, yout: List[float]) -> None:
    """static void rk4_full(...): one classical RK4 step of size h over the
    whole state vector, generalizing sim_vdp.c::rk4_step from a hardcoded
    (y,y') pair to N components."""
    n = sys.neqns
    k1 = [0.0] * n
    k2 = [0.0] * n
    k3 = [0.0] * n
    k4 = [0.0] * n
    tmp = [0.0] * n

    odesys_eval(sys, x, y, k, k1)
    for i in range(n):
        tmp[i] = y[i] + h / 2.0 * k1[i]
    odesys_eval(sys, x + h / 2.0, tmp, k, k2)
    for i in range(n):
        tmp[i] = y[i] + h / 2.0 * k2[i]
    odesys_eval(sys, x + h / 2.0, tmp, k, k3)
    for i in range(n):
        tmp[i] = y[i] + h * k3[i]
    odesys_eval(sys, x + h, tmp, k, k4)
    for i in range(n):
        yout[i] = y[i] + h / 6.0 * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])


def odesys_adaptive_step(sys: ODESys, x: List[float], y: List[float],
                          k: Optional[Sequence[float]], st: ODEStepper) -> int:
    """int odesys_adaptive_step(const ODESys *sys, double *x, double *y,
                                 const double *k, ODEStepper *st);
    Step-doubling adaptive control (one full-h RK4 step vs two half-h RK4
    steps, compared), generalizing sim_vdp.c::adaptive_step to N dims.

    `x` is a 1-element mutable box (see module docstring); `y` is mutated
    in place. Returns 1 if the step was accepted (x[0]/y updated), 0 if
    rejected (only st.h shrunk) -- exactly as the C function does."""
    n = sys.neqns
    y_full = [0.0] * n
    y_half1 = [0.0] * n
    y_half2 = [0.0] * n

    _rk4_full(sys, x[0], y, k, st.h, y_full)
    _rk4_full(sys, x[0], y, k, st.h / 2.0, y_half1)
    _rk4_full(sys, x[0] + st.h / 2.0, y_half1, k, st.h / 2.0, y_half2)

    err = 0.0
    for i in range(n):
        err += abs(y_half2[i] - y_full[i])

    if err < st.tol or st.h <= st.hmin:
        for i in range(n):
            y[i] = y_half2[i]
        x[0] += st.h

        factor = math.pow(st.tol / err, 0.2) if err > 1e-14 else 2.0
        if factor > 2.0:
            factor = 2.0
        if factor < 0.5:
            factor = 0.5
        st.h *= factor
        if st.h > st.hmax:
            st.h = st.hmax
        if st.h < st.hmin:
            st.h = st.hmin
        return 1
    else:
        st.h *= 0.5
        if st.h < st.hmin:
            st.h = st.hmin
        return 0
