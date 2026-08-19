"""calcode_action_bridge_v1.py -- exact Python port of
calcode_action_bridge_v1.c / calcode_action_bridge_v1.h.

Original: dispatches user actions (parameter/equation changes) coming
from the live-controls layer and forwards them into CalcodeLab,
holding the `solve_after_parameter_change` / `solve_after_equation_change`
flags and a `step_fraction`. This is the file identified in the
2026-08-16 gap/regression analysis as real, CMake-referenced,
machine-independent code that had never been captured in either the
"already ported" or "remaining to port" tracking buckets before that
session -- see `gap_package/ANALYSIS_REPORT.md` section 4 and
`gap_package/missing_from_tracking/calcode_action_bridge_v1.c`/`.h`.

PORT STATUS -- NOT YET HARNESS-VERIFIED AGAINST A COMPILED C BINARY.

Same root cause as `calcode_lab.py`: `calcode_action_bridge_v1.h`
includes `calcode_lab.h`, which chains to `odesys.h`/`odesolution.h`,
whose `.c` sources are not present in any upload so far (only compiled
`.obj`/`.a` artifacts survive in the stage1 build tree). This port was
produced by direct line-by-line reading of the real
`calcode_action_bridge_v1.c`/`.h`, reusing the already-ported
`calcode_lab` and `calcode_live_controls_v1` Python modules the C
originally called into. A Python-only behavioral harness is included
(`harness_action_bridge.py`) exercising every action/branch against
the existing Python `calcode_lab`/`calcode_input`/`calcode_clock`
stack, but per the project's stated method this should not be marked
Done in `00_STATUS_AND_PLAN.md` until a real compiled-C diff is
possible -- send `expr.c/.h`, `odesys.c/.h`, `odesolution.c/.h` to
close this out the same way `calcode_lab` is blocked.

PORT NOTES:

- `calcode_action_bridge_init_v1` mirrors `memset(b, 0, sizeof(*b))`
  by resetting every field (lab=None, both solve flags, step_fraction)
  before assigning `lab` and the two literal defaults, exactly
  matching field order in the C.
- `solve_v1` is a private (`static`) helper in the C; kept as a
  module-private function here, not exported.
- The C's `CALCODE_LIVE_PAUSE_V1` branch is genuinely asymmetric: it
  only toggles PLAY_PAUSE if `lab->clock.playing` is already truthy
  (there's no direct "pause" input action in `CalcodeInputAction`,
  only a toggle) -- reproduced exactly, not "fixed" into a real pause.
- `calcode_action_bridge_action_v1`'s `default:` case is a no-op for
  `CALCODE_LIVE_NONE_V1` and any out-of-range value, same as the C's
  `switch` with no `default` body.
- Every public entry point begins with the same `if (!b) return;` /
  `if (!b || !b->lab) return;` NULL-guard pattern as the C.
"""

from __future__ import annotations

from typing import Optional

from calcy.core.lab import CalcodeLab, calcode_lab_action, calcode_lab_solve, calcode_lab_tick
from calcy.core.input import CalcodeInputAction
from calcy.core.live_controls_v1 import CalcodeLiveActionV1
from calcy.core.clock import calcode_clock_set_time


class CalcodeActionBridgeV1:
    """typedef struct CalcodeActionBridgeV1 { ... } CalcodeActionBridgeV1;"""
    __slots__ = ("lab", "solve_after_parameter_change", "solve_after_equation_change", "step_fraction")

    def __init__(self):
        self.lab: Optional[CalcodeLab] = None
        self.solve_after_parameter_change = 0
        self.solve_after_equation_change = 0
        self.step_fraction = 0.0


def calcode_action_bridge_init_v1(
    b: Optional[CalcodeActionBridgeV1],
    lab: Optional[CalcodeLab],
) -> None:
    """void calcode_action_bridge_init_v1(CalcodeActionBridgeV1 *b, CalcodeLab *lab);"""
    if b is None:
        return

    # memset(b, 0, sizeof(*b));
    b.lab = None
    b.solve_after_parameter_change = 0
    b.solve_after_equation_change = 0
    b.step_fraction = 0.0

    b.lab = lab

    b.solve_after_parameter_change = 1
    b.solve_after_equation_change = 1

    b.step_fraction = 0.01


def _solve_v1(b: CalcodeActionBridgeV1) -> None:
    """static void solve_v1(CalcodeActionBridgeV1 *b);"""
    if b is None or b.lab is None:
        return

    calcode_lab_solve(b.lab)


def calcode_action_bridge_action_v1(
    b: Optional[CalcodeActionBridgeV1],
    action: CalcodeLiveActionV1,
) -> None:
    """void calcode_action_bridge_action_v1(CalcodeActionBridgeV1 *b, CalcodeLiveActionV1 action);"""
    if b is None or b.lab is None:
        return

    A = CalcodeLiveActionV1
    I = CalcodeInputAction

    if action == A.CALCODE_LIVE_PLAY_V1:
        calcode_lab_action(b.lab, I.CALCODE_INPUT_PLAY_PAUSE)

    elif action == A.CALCODE_LIVE_PAUSE_V1:
        # The existing laboratory action is toggle-based. Pause is
        # therefore represented by PLAY/PAUSE at this boundary.
        if b.lab.clock.playing:
            calcode_lab_action(b.lab, I.CALCODE_INPUT_PLAY_PAUSE)

    elif action == A.CALCODE_LIVE_RESET_V1:
        calcode_lab_action(b.lab, I.CALCODE_INPUT_RESET)

    elif action == A.CALCODE_LIVE_STEP_FORWARD_V1:
        calcode_lab_action(b.lab, I.CALCODE_INPUT_STEP_FORWARD)

    elif action == A.CALCODE_LIVE_STEP_BACKWARD_V1:
        calcode_lab_action(b.lab, I.CALCODE_INPUT_STEP_BACKWARD)

    elif action == A.CALCODE_LIVE_SPEED_DOWN_V1:
        calcode_lab_action(b.lab, I.CALCODE_INPUT_SPEED_DOWN)

    elif action == A.CALCODE_LIVE_SPEED_UP_V1:
        calcode_lab_action(b.lab, I.CALCODE_INPUT_SPEED_UP)

    elif action == A.CALCODE_LIVE_SOLVE_V1:
        _solve_v1(b)

    # default: break; (no-op for CALCODE_LIVE_NONE_V1 and any other value)


def calcode_action_bridge_time_v1(
    b: Optional[CalcodeActionBridgeV1],
    time: float,
) -> None:
    """void calcode_action_bridge_time_v1(CalcodeActionBridgeV1 *b, double time);"""
    if b is None or b.lab is None:
        return

    calcode_clock_set_time(b.lab.clock, time)

    # No numerical integration occurs here. The clock selects a point
    # on the already computed trajectory.
    calcode_lab_tick(b.lab, b.lab.clock.last_wall_time)


def calcode_action_bridge_speed_v1(
    b: Optional[CalcodeActionBridgeV1],
    speed: float,
) -> None:
    """void calcode_action_bridge_speed_v1(CalcodeActionBridgeV1 *b, double speed);"""
    if b is None or b.lab is None:
        return

    b.lab.clock.speed = speed
