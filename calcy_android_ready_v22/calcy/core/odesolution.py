"""odesolution.py -- exact Python port of odesolution.c / odesolution.h.

Original: the "one in-memory solution buffer" concept -- batch-solves a
compiled ODESys once (odesys_adaptive_step in a loop, same double-precision
track as odesys.py) and records every accepted step, rather than stepping
live once per frame the way sim_vdp.c does -- the views need a fixed
trajectory to browse/scrub/table-scroll through, not a moving target.

PORT NOTES: same in/out-parameter convention as odesys.py -- `sol` (the
ODESolution) is mutated in place by odesolution_run, exactly as the C
function writes through its `ODESolution *sol` pointer.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from calcy.core.odesys import (
    ODESYS_MAX_EQNS,
    ODESys,
    ODEStepper,
    odestepper_init,
    odesys_adaptive_step,
    odesys_neqns,
)

# #define ODESOL_MAXPTS 4000
ODESOL_MAXPTS = 4000


class ODESolution:
    """typedef struct ODESolution {
        double x[ODESOL_MAXPTS];
        double y[ODESYS_MAX_EQNS][ODESOL_MAXPTS];
        int npts;
        int neqns;
        int ok;
    } ODESolution;

    Fixed-size buffers preallocated up front, matching the C struct's
    "fixed cap, no malloc" layout exactly (rather than growing a Python
    list dynamically), so `npts`/`ODESOL_MAXPTS` capacity semantics stay
    identical to the original.
    """
    __slots__ = ("x", "y", "npts", "neqns", "ok")

    def __init__(self):
        self.x: List[float] = [0.0] * ODESOL_MAXPTS
        self.y: List[List[float]] = [[0.0] * ODESOL_MAXPTS for _ in range(ODESYS_MAX_EQNS)]
        self.npts: int = 0
        self.neqns: int = 0
        self.ok: int = 0


def odesolution_run(sol: ODESolution, sys: ODESys,
                     x0: float, xEnd: float, y0: Sequence[float],
                     k: Optional[Sequence[float]], h0: float, tol: float,
                     hmin: float, hmax: float, maxSteps: int) -> None:
    """void odesolution_run(ODESolution *sol, const ODESys *sys,
                             double x0, double xEnd, const double *y0,
                             const double *k, double h0, double tol,
                             double hmin, double hmax, int maxSteps);

    Records one row per accepted step (plus the initial point at row 0)
    until x reaches xEnd, the buffer fills (ODESOL_MAXPTS), or maxSteps
    total step *attempts* (accepted or rejected) are exhausted -- the same
    defensive cap as the original, guarding against a pathological system
    (e.g. genuine finite-time blowup) grinding h down toward hmin forever.

    On return: sol.npts and sol.ok are always valid, even on a
    degenerate/failed run (sol.ok will just be 0). Does not take ownership
    of sys -- caller compiles/frees it separately, and may reuse the same
    sys across multiple odesolution_run calls (e.g. one per parameter
    sweep).
    """
    sol.neqns = odesys_neqns(sys)
    sol.npts = 0
    sol.ok = 0
    if sol.neqns <= 0 or sol.neqns > ODESYS_MAX_EQNS:
        return

    y = list(y0[:sol.neqns])
    x = [x0]  # mutable box, mirrors C's `double x` advanced via &x

    sol.x[0] = x[0]
    for i in range(sol.neqns):
        sol.y[i][0] = y[i]
    sol.npts = 1

    # Degenerate/backwards range: nothing to integrate, but the single
    # initial point above is still a valid (if trivial) result -- ok stays
    # 0 since npts==1 doesn't count as "a trajectory" for the views below
    # (a 1-point report/graph/3D frame isn't useful to browse).
    if xEnd <= x0:
        return

    st = ODEStepper()
    odestepper_init(st, h0, tol, hmin, hmax)

    steps = 0
    while x[0] < xEnd and sol.npts < ODESOL_MAXPTS and steps < maxSteps:
        # Clamp the final step so the buffer's last row lands exactly on
        # xEnd rather than overshooting it -- matters for views that plot
        # against a known x-range.
        if st.h > xEnd - x[0]:
            st.h = xEnd - x[0]
        if st.h < hmin:
            st.h = hmin

        accepted = odesys_adaptive_step(sys, x, y, k, st)
        steps += 1
        if accepted:
            sol.x[sol.npts] = x[0]
            for i in range(sol.neqns):
                sol.y[i][sol.npts] = y[i]
            sol.npts += 1

    sol.ok = 1 if sol.npts > 1 else 0
