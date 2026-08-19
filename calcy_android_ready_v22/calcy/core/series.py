"""calcode_series.py -- exact Python port of calcode_series.c / .h.

Original: extracts plottable series (single-state time series, 2D phase
portrait, 3D trajectory, numerical derivative) from an already-solved
ODESolution, plus a defensive deep-copy helper.

PORT NOTES:

- C's `double *x/a/b/c` heap arrays (`calloc`'d, `NULL` until allocated)
  become plain Python lists, `None` until "allocated" -- `alloc_arrays`
  in this port assigns fresh zero-filled lists instead of calling
  `calloc`, and always succeeds (Python lists don't have an OOM failure
  mode the way `calloc` does), so the `if (!s->x) return 0;` guards have
  no reachable failure branch here but are kept as dead code for
  structural parity.

- `calcode_series_free` calling `free()` on each buffer becomes simply
  dropping the references (Python GC); it still calls
  `calcode_series_init` afterward exactly as the C does, to reset
  `count`/`components`/`state_*` to their "empty" values.

- `calcode_series_copy`'s `CalcodeSeries tmp; ...; *dst = tmp;` (build a
  temporary, then struct-assign it over the destination) becomes
  building a local CalcodeSeries and reassigning `dst`'s fields from it
  field-by-field, since Python has no struct-assignment operator.
"""

from __future__ import annotations

from enum import IntEnum
from typing import List, Optional

from calcy.core.odesolution import ODESolution


class CalcodeSeriesKind(IntEnum):
    """enum CalcodeSeriesKind -- values match the C enum exactly."""
    STATE = 0
    PHASE = 1
    THREE_D = 2
    DERIVATIVE = 3
    ERROR = 4


class CalcodeSeries:
    """typedef struct CalcodeSeries { ... } CalcodeSeries;"""
    __slots__ = (
        "kind", "count", "components", "state_x", "state_y", "state_z",
        "x", "a", "b", "c",
        "xmin", "xmax", "amin", "amax", "bmin", "bmax", "cmin", "cmax",
    )

    def __init__(self):
        calcode_series_init(self)


def calcode_series_init(s: Optional[CalcodeSeries]) -> None:
    """void calcode_series_init(CalcodeSeries *series);"""
    if s is None:
        return

    s.kind = CalcodeSeriesKind.STATE  # matches memset(0) -> kind == 0
    s.count = 0
    s.components = 0
    s.state_x = -1
    s.state_y = -1
    s.state_z = -1

    s.x = None
    s.a = None
    s.b = None
    s.c = None

    s.xmin = 0.0
    s.xmax = 0.0
    s.amin = 0.0
    s.amax = 0.0
    s.bmin = 0.0
    s.bmax = 0.0
    s.cmin = 0.0
    s.cmax = 0.0


def calcode_series_free(s: Optional[CalcodeSeries]) -> None:
    """void calcode_series_free(CalcodeSeries *series);"""
    if s is None:
        return

    s.x = None
    s.a = None
    s.b = None
    s.c = None

    calcode_series_init(s)


def _alloc_arrays(s: CalcodeSeries, n: int, components: int) -> int:
    """static int alloc_arrays(CalcodeSeries *s, int n, int components);
    Python lists have no calloc-style OOM failure mode, so this always
    succeeds; the `return 0` branches are kept as dead code for
    structural parity with the C source."""
    s.x = [0.0] * n
    if s.x is None:
        return 0

    if components >= 1:
        s.a = [0.0] * n
        if s.a is None:
            return 0
    if components >= 2:
        s.b = [0.0] * n
        if s.b is None:
            return 0
    if components >= 3:
        s.c = [0.0] * n
        if s.c is None:
            return 0

    s.count = n
    s.components = components
    return 1


def _bounds(s: Optional[CalcodeSeries]) -> None:
    """static void bounds(CalcodeSeries *s);"""
    if s is None or s.count <= 0:
        return

    s.xmin = s.xmax = s.x[0]

    if s.components >= 1:
        s.amin = s.amax = s.a[0]
    if s.components >= 2:
        s.bmin = s.bmax = s.b[0]
    if s.components >= 3:
        s.cmin = s.cmax = s.c[0]

    for i in range(1, s.count):
        if s.x[i] < s.xmin:
            s.xmin = s.x[i]
        if s.x[i] > s.xmax:
            s.xmax = s.x[i]

        if s.components >= 1:
            if s.a[i] < s.amin:
                s.amin = s.a[i]
            if s.a[i] > s.amax:
                s.amax = s.a[i]
        if s.components >= 2:
            if s.b[i] < s.bmin:
                s.bmin = s.b[i]
            if s.b[i] > s.bmax:
                s.bmax = s.b[i]
        if s.components >= 3:
            if s.c[i] < s.cmin:
                s.cmin = s.c[i]
            if s.c[i] > s.cmax:
                s.cmax = s.c[i]


def _valid_state(s: Optional[ODESolution], state: int) -> bool:
    """static int valid_state(const ODESolution *s, int state);"""
    return bool(s and s.ok and s.npts > 0 and 0 <= state < s.neqns)


def calcode_series_state(s: Optional[ODESolution], state: int,
                          out: Optional[CalcodeSeries]) -> int:
    """int calcode_series_state(const ODESolution *solution, int state,
                                 CalcodeSeries *series);"""
    if out is None or not _valid_state(s, state):
        return 0

    calcode_series_free(out)
    calcode_series_init(out)

    if not _alloc_arrays(out, s.npts, 1):
        calcode_series_free(out)
        return 0

    out.kind = CalcodeSeriesKind.STATE
    out.state_x = state

    for i in range(s.npts):
        out.x[i] = s.x[i]
        out.a[i] = s.y[state][i]

    _bounds(out)
    return 1


def calcode_series_phase(s: Optional[ODESolution], xs: int, ys: int,
                          out: Optional[CalcodeSeries]) -> int:
    """int calcode_series_phase(const ODESolution *solution, int x_state,
                                 int y_state, CalcodeSeries *series);"""
    if out is None or not _valid_state(s, xs) or not _valid_state(s, ys):
        return 0

    calcode_series_free(out)
    calcode_series_init(out)

    if not _alloc_arrays(out, s.npts, 2):
        calcode_series_free(out)
        return 0

    out.kind = CalcodeSeriesKind.PHASE
    out.state_x = xs
    out.state_y = ys

    for i in range(s.npts):
        out.x[i] = s.x[i]
        out.a[i] = s.y[xs][i]
        out.b[i] = s.y[ys][i]

    _bounds(out)
    return 1


def calcode_series_3d(s: Optional[ODESolution], xs: int, ys: int, zs: int,
                       out: Optional[CalcodeSeries]) -> int:
    """int calcode_series_3d(const ODESolution *solution, int x_state,
                              int y_state, int z_state, CalcodeSeries *series);"""
    if (out is None or not _valid_state(s, xs) or
            not _valid_state(s, ys) or not _valid_state(s, zs)):
        return 0

    calcode_series_free(out)
    calcode_series_init(out)

    if not _alloc_arrays(out, s.npts, 3):
        calcode_series_free(out)
        return 0

    out.kind = CalcodeSeriesKind.THREE_D
    out.state_x = xs
    out.state_y = ys
    out.state_z = zs

    for i in range(s.npts):
        out.x[i] = s.x[i]
        out.a[i] = s.y[xs][i]
        out.b[i] = s.y[ys][i]
        out.c[i] = s.y[zs][i]

    _bounds(out)
    return 1


def calcode_series_derivative(s: Optional[ODESolution], state: int,
                               out: Optional[CalcodeSeries]) -> int:
    """int calcode_series_derivative(const ODESolution *solution, int state,
                                      CalcodeSeries *series);
    Central differences in the interior, one-sided at the endpoints."""
    if out is None or not _valid_state(s, state):
        return 0

    if s.npts < 2:
        return 0

    calcode_series_free(out)
    calcode_series_init(out)

    if not _alloc_arrays(out, s.npts, 1):
        calcode_series_free(out)
        return 0

    out.kind = CalcodeSeriesKind.DERIVATIVE
    out.state_x = state

    for i in range(s.npts):
        out.x[i] = s.x[i]

        if i == 0:
            dx = s.x[1] - s.x[0]
            out.a[i] = (s.y[state][1] - s.y[state][0]) / dx if dx != 0.0 else 0.0
        elif i == s.npts - 1:
            dx = s.x[i] - s.x[i - 1]
            out.a[i] = (s.y[state][i] - s.y[state][i - 1]) / dx if dx != 0.0 else 0.0
        else:
            dx = s.x[i + 1] - s.x[i - 1]
            out.a[i] = (s.y[state][i + 1] - s.y[state][i - 1]) / dx if dx != 0.0 else 0.0

    _bounds(out)
    return 1


def calcode_series_copy(src: Optional[CalcodeSeries], dst: Optional[CalcodeSeries]) -> int:
    """int calcode_series_copy(const CalcodeSeries *source,
                                CalcodeSeries *destination);"""
    if src is None or dst is None or src.count <= 0:
        return 0

    tmp = CalcodeSeries()  # calcode_series_init(&tmp) via __init__

    if not _alloc_arrays(tmp, src.count, src.components):
        calcode_series_free(tmp)
        return 0

    tmp.kind = src.kind
    tmp.state_x = src.state_x
    tmp.state_y = src.state_y
    tmp.state_z = src.state_z

    tmp.x = list(src.x[: src.count])
    if src.components >= 1:
        tmp.a = list(src.a[: src.count])
    if src.components >= 2:
        tmp.b = list(src.b[: src.count])
    if src.components >= 3:
        tmp.c = list(src.c[: src.count])

    _bounds(tmp)

    calcode_series_free(dst)
    # `*dst = tmp;` -- Python has no struct-assignment operator, so copy
    # every field from tmp onto dst instead of rebinding dst itself
    # (which the caller's reference wouldn't see).
    dst.kind = tmp.kind
    dst.count = tmp.count
    dst.components = tmp.components
    dst.state_x = tmp.state_x
    dst.state_y = tmp.state_y
    dst.state_z = tmp.state_z
    dst.x = tmp.x
    dst.a = tmp.a
    dst.b = tmp.b
    dst.c = tmp.c
    dst.xmin, dst.xmax = tmp.xmin, tmp.xmax
    dst.amin, dst.amax = tmp.amin, tmp.amax
    dst.bmin, dst.bmax = tmp.bmin, tmp.bmax
    dst.cmin, dst.cmax = tmp.cmin, tmp.cmax
    return 1
