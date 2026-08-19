"""calcode_viewdata.py -- exact Python port of calcode_viewdata.c / .h.

Original: bundles the three CalcodeSeries a GUI typically needs at once
(time-series curve, 2D phase portrait, 3D trajectory) plus a "current
time" scrub cursor interpolated against the 3D trajectory series.
"""

from __future__ import annotations

from typing import Optional

from calcy.core.series import (
    CalcodeSeries,
    calcode_series_3d,
    calcode_series_free,
    calcode_series_init,
    calcode_series_phase,
    calcode_series_state,
)
from calcy.core.interpolate import calcode_interpolate_series
from calcy.core.odesolution import ODESolution


class CalcodeViewData:
    """typedef struct CalcodeViewData { ... } CalcodeViewData;"""
    __slots__ = (
        "curve", "phase", "trajectory",
        "current_x", "current_a", "current_b", "current_c",
        "has_current",
    )

    def __init__(self):
        calcode_viewdata_init(self)


def calcode_viewdata_init(v: Optional[CalcodeViewData]) -> None:
    """void calcode_viewdata_init(CalcodeViewData *view);"""
    if v is None:
        return

    v.curve = CalcodeSeries()
    v.phase = CalcodeSeries()
    v.trajectory = CalcodeSeries()
    calcode_series_init(v.curve)
    calcode_series_init(v.phase)
    calcode_series_init(v.trajectory)

    v.current_x = 0.0
    v.current_a = 0.0
    v.current_b = 0.0
    v.current_c = 0.0
    v.has_current = 0


def calcode_viewdata_free(v: Optional[CalcodeViewData]) -> None:
    """void calcode_viewdata_free(CalcodeViewData *view);"""
    if v is None:
        return

    calcode_series_free(v.curve)
    calcode_series_free(v.phase)
    calcode_series_free(v.trajectory)
    v.has_current = 0


def calcode_viewdata_build(s: Optional[ODESolution], curve_state: int,
                            phase_x: int, phase_y: int,
                            tx: int, ty: int, tz: int,
                            v: Optional[CalcodeViewData]) -> int:
    """int calcode_viewdata_build(const ODESolution *solution, int curve_state,
                                   int phase_x, int phase_y, int trajectory_x,
                                   int trajectory_y, int trajectory_z,
                                   CalcodeViewData *view);"""
    if s is None or v is None:
        return 0

    calcode_viewdata_free(v)
    calcode_viewdata_init(v)

    if not calcode_series_state(s, curve_state, v.curve):
        calcode_viewdata_free(v)
        return 0

    if not calcode_series_phase(s, phase_x, phase_y, v.phase):
        calcode_viewdata_free(v)
        return 0

    if not calcode_series_3d(s, tx, ty, tz, v.trajectory):
        calcode_viewdata_free(v)
        return 0

    return 1


def calcode_viewdata_set_time(v: Optional[CalcodeViewData], x: float) -> int:
    """int calcode_viewdata_set_time(CalcodeViewData *view, double x);"""
    if v is None:
        return 0

    a_box = [0.0]
    b_box = [0.0]
    c_box = [0.0]

    if not calcode_interpolate_series(v.trajectory, x, a_box, b_box, c_box):
        return 0

    v.current_x = x
    v.current_a = a_box[0]
    v.current_b = b_box[0]
    v.current_c = c_box[0]
    v.has_current = 1

    return 1
