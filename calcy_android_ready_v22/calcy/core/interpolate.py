"""calcode_interpolate.py -- exact Python port of calcode_interpolate.c / .h.

Original: binary-search location + linear interpolation against an
ODESolution's recorded (accepted) grid, plus a fixed-count resampler
built on top of it.

PORT NOTES:

- C's required `double *value` / `double *a` output pointers become
  1-element mutable list "boxes" (same convention as `x`/`y` in
  odesys.py -- write through `box[0]`), since they're never NULL in the
  original's call sites.

- C's *optional* `double *b` / `double *c` output pointers (checked with
  `if (b)` / `if (c)` before writing) become `Optional[List[float]]`:
  pass `None` for "I don't want this value" (mirrors passing NULL),
  or a 1-element list to receive it (mirrors passing a real pointer).
"""

from __future__ import annotations

from typing import List, Optional

from calcy.core.series import (
    CalcodeSeries,
    CalcodeSeriesKind,
    calcode_series_free,
    calcode_series_init,
)
from calcy.core.odesolution import ODESolution


class CalcodeInterpolation:
    """typedef struct CalcodeInterpolation { ... } CalcodeInterpolation;"""
    __slots__ = ("ok", "left", "right", "x", "fraction")

    def __init__(self):
        self.ok = 0
        self.left = -1
        self.right = -1
        self.x = 0.0
        self.fraction = 0.0


def calcode_interpolate_locate(s: Optional[ODESolution], x: float,
                                r: Optional[CalcodeInterpolation]) -> int:
    """int calcode_interpolate_locate(const ODESolution *solution, double x,
                                       CalcodeInterpolation *result);
    Binary search for the bracketing pair of recorded grid points."""
    if s is None or r is None or not s.ok or s.npts < 2:
        return 0

    r.ok = 0
    r.left = -1
    r.right = -1
    r.x = 0.0
    r.fraction = 0.0

    if x < s.x[0] or x > s.x[s.npts - 1]:
        return 0

    if x == s.x[0]:
        r.left = r.right = 0
        r.x = x
        r.fraction = 0.0
        r.ok = 1
        return 1

    if x == s.x[s.npts - 1]:
        r.left = r.right = s.npts - 1
        r.x = x
        r.fraction = 0.0
        r.ok = 1
        return 1

    lo = 0
    hi = s.npts - 1

    while hi - lo > 1:
        mid = lo + (hi - lo) // 2

        if s.x[mid] <= x:
            lo = mid
        else:
            hi = mid

    dx = s.x[hi] - s.x[lo]
    if dx == 0.0:
        return 0

    r.left = lo
    r.right = hi
    r.x = x
    r.fraction = (x - s.x[lo]) / dx
    r.ok = 1

    return 1


def calcode_interpolate_state(s: Optional[ODESolution], state: int, x: float,
                               value: List[float]) -> int:
    """int calcode_interpolate_state(const ODESolution *solution, int state,
                                      double x, double *value);
    `value` is a required 1-element output box; write through value[0]."""
    if value is None or s is None or not s.ok or state < 0 or state >= s.neqns:
        return 0

    p = CalcodeInterpolation()

    if not calcode_interpolate_locate(s, x, p):
        return 0

    if p.left == p.right:
        value[0] = s.y[state][p.left]
        return 1

    value[0] = s.y[state][p.left] + p.fraction * (s.y[state][p.right] - s.y[state][p.left])
    return 1


def calcode_interpolate_series(s: Optional[CalcodeSeries], x: float,
                                a: Optional[List[float]],
                                b: Optional[List[float]] = None,
                                c: Optional[List[float]] = None) -> int:
    """int calcode_interpolate_series(const CalcodeSeries *series, double x,
                                       double *a, double *b, double *c);
    `a` is a required 1-element output box; `b`/`c` are optional --
    pass None for a C NULL pointer, or a 1-element list to receive it."""
    if s is None or s.count < 2 or a is None:
        return 0

    if x < s.x[0] or x > s.x[s.count - 1]:
        return 0

    lo = 0
    hi = s.count - 1

    if x == s.x[hi]:
        a[0] = s.a[hi] if s.a else 0.0
        if b is not None:
            b[0] = s.b[hi] if s.b else 0.0
        if c is not None:
            c[0] = s.c[hi] if s.c else 0.0
        return 1

    while hi - lo > 1:
        mid = lo + (hi - lo) // 2
        if s.x[mid] <= x:
            lo = mid
        else:
            hi = mid

    dx = s.x[hi] - s.x[lo]
    if dx == 0.0:
        return 0

    f = (x - s.x[lo]) / dx

    a[0] = s.a[lo] + f * (s.a[hi] - s.a[lo])

    if b is not None and s.b:
        b[0] = s.b[lo] + f * (s.b[hi] - s.b[lo])

    if c is not None and s.c:
        c[0] = s.c[lo] + f * (s.c[hi] - s.c[lo])

    return 1


def calcode_resample_state(s: Optional[ODESolution], state: int, x0: float, x1: float,
                            count: int, out: Optional[CalcodeSeries]) -> int:
    """int calcode_resample_state(const ODESolution *solution, int state,
                                   double x0, double x1, int count,
                                   CalcodeSeries *series);
    Resamples a single state onto a uniform grid of `count` points over
    [x0, x1] via calcode_interpolate_state."""
    if (s is None or out is None or not s.ok or
            state < 0 or state >= s.neqns or
            count < 2 or x1 <= x0):
        return 0

    calcode_series_free(out)
    calcode_series_init(out)

    out.kind = CalcodeSeriesKind.STATE
    out.components = 1
    out.state_x = state
    out.count = count

    out.x = [0.0] * count
    out.a = [0.0] * count

    value_box = [0.0]

    for i in range(count):
        f = float(i) / float(count - 1)
        x = x0 + f * (x1 - x0)

        if not calcode_interpolate_state(s, state, x, value_box):
            calcode_series_free(out)
            return 0

        out.a[i] = value_box[0]
        out.x[i] = x

    out.xmin = x0
    out.xmax = x1
    out.amin = out.amax = out.a[0]

    for i in range(1, count):
        if out.a[i] < out.amin:
            out.amin = out.a[i]
        if out.a[i] > out.amax:
            out.amax = out.a[i]

    return 1
