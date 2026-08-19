"""calcode_live_controls_v1.py -- exact Python port of
calcode_live_controls_v1.c / calcode_live_controls_v1.h.

Original: the bottom control-strip widget (play/reset/step/solve buttons
plus a timeline slider and a speed slider) that drives the lab's clock
and solver. Pure layout/hit-testing math -- no GL/rendering calls of its
own, same as the C.

PORT NOTES:

- `CalcodeSliderV1` and `CalcodeLiveControlsV1` are ported as plain
  `__slots__` classes whose constructors zero every field, mirroring the
  C's `memset(c, 0, sizeof(*c))` at the top of `calcode_live_controls_init_v1`.
  Fields the C init function never explicitly re-touches after the memset
  (the hover_*/pressed_* flags, mouse_x/mouse_y, left_down, and
  pending_action) are therefore left at their zeroed constructor values
  here too, exactly as in the C.

- `int`-typed C fields (the hover/pressed/dragging/hovered/left_down
  flags) are stored as Python `int` 0/1, not `bool`, via explicit
  `int(...)` casts on every boolean expression -- matching the struct's
  declared C type and the convention used in `calcode_input.py`.

- `calcode_live_controls_time_from_mouse_v1` / `..._speed_from_mouse_v1`
  preserve the C's distinct NULL-guard defaults: 0.0 for time, 1.0 for
  speed (not a shared default).

- The "click anywhere on the track, not just the knob" extension in
  `mouse_move_v1` (the two `if (x >= px0 && ...)` blocks that force
  `hovered = 1` for the whole track rect, on top of the circular knob
  hit-test) is preserved exactly, including that it can only ever turn
  `hovered` on, never off, once the knob hit-test already ran.

- `calcode_live_controls_take_action_v1` implements a one-shot
  "pending action" ferry: it returns the current pending action and
  resets it to NONE in the same call, exactly as the C.

- `slider_value_v1` (used internally, and via the public
  `time_from_mouse_v1` / `speed_from_mouse_v1`) already clamps its
  result into `[minimum, maximum]` through `denormalize_v1`'s internal
  `clamp_v1(f, 0.0, 1.0)` -- callers do not need to (and the C does not)
  clamp again afterward.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional


class CalcodeLiveActionV1(IntEnum):
    """typedef enum CalcodeLiveActionV1 { ... } CalcodeLiveActionV1;"""
    CALCODE_LIVE_NONE_V1 = 0
    CALCODE_LIVE_PLAY_V1 = 1
    CALCODE_LIVE_PAUSE_V1 = 2
    CALCODE_LIVE_RESET_V1 = 3
    CALCODE_LIVE_STEP_FORWARD_V1 = 4
    CALCODE_LIVE_STEP_BACKWARD_V1 = 5
    CALCODE_LIVE_SPEED_DOWN_V1 = 6
    CALCODE_LIVE_SPEED_UP_V1 = 7
    CALCODE_LIVE_SOLVE_V1 = 8


class CalcodeSliderV1:
    """typedef struct CalcodeSliderV1 { ... } CalcodeSliderV1."""
    __slots__ = (
        "minimum", "maximum", "value",
        "px0", "px1",
        "py0", "py1",
        "knob_radius",
        "dragging", "hovered",
    )

    def __init__(self):
        self.minimum = 0.0
        self.maximum = 0.0
        self.value = 0.0
        self.px0 = 0.0
        self.px1 = 0.0
        self.py0 = 0.0
        self.py1 = 0.0
        self.knob_radius = 0.0
        self.dragging = 0
        self.hovered = 0


class CalcodeLiveControlsV1:
    """typedef struct CalcodeLiveControlsV1 { ... } CalcodeLiveControlsV1
    (see calcode_live_controls_v1.h)."""
    __slots__ = (
        "width", "height",
        "bottom", "control_height",
        "timeline", "speed",
        "hover_play", "hover_reset", "hover_step_back",
        "hover_step_forward", "hover_solve",
        "pressed_play", "pressed_reset", "pressed_step_back",
        "pressed_step_forward", "pressed_solve",
        "mouse_x", "mouse_y",
        "left_down",
        "selected_time", "selected_speed",
        "pending_action",
    )

    def __init__(self):
        # Mirrors memset(c, 0, sizeof(*c)); calcode_live_controls_init_v1
        # never re-touches most of these fields after the memset, so this
        # constructor is where their "always zero until first interaction"
        # behavior actually lives -- same as the C.
        self.width = 0
        self.height = 0
        self.bottom = 0.0
        self.control_height = 0.0
        self.timeline = CalcodeSliderV1()
        self.speed = CalcodeSliderV1()
        self.hover_play = 0
        self.hover_reset = 0
        self.hover_step_back = 0
        self.hover_step_forward = 0
        self.hover_solve = 0
        self.pressed_play = 0
        self.pressed_reset = 0
        self.pressed_step_back = 0
        self.pressed_step_forward = 0
        self.pressed_solve = 0
        self.mouse_x = 0.0
        self.mouse_y = 0.0
        self.left_down = 0
        self.selected_time = 0.0
        self.selected_speed = 0.0
        self.pending_action = CalcodeLiveActionV1.CALCODE_LIVE_NONE_V1


def _clamp(x: float, lo: float, hi: float) -> float:
    """static double clamp_v1(double x, double lo, double hi);"""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _normalize(x: float, lo: float, hi: float) -> float:
    """static double normalize_v1(double x, double lo, double hi);"""
    if hi <= lo:
        return 0.0
    return _clamp((x - lo) / (hi - lo), 0.0, 1.0)


def _denormalize(f: float, lo: float, hi: float) -> float:
    """static double denormalize_v1(double f, double lo, double hi);"""
    return lo + _clamp(f, 0.0, 1.0) * (hi - lo)


def _hit_rect(x: float, y: float, x0: float, y0: float, x1: float, y1: float) -> int:
    """static int hit_rect_v1(...);"""
    return int(x >= x0 and x <= x1 and y >= y0 and y <= y1)


def _hit_circle(x: float, y: float, cx: float, cy: float, radius: float) -> int:
    """static int hit_circle_v1(...);"""
    dx = x - cx
    dy = y - cy
    return int(dx * dx + dy * dy <= radius * radius)


def _slider_pixel(s: CalcodeSliderV1, value: float) -> float:
    """static double slider_pixel_v1(const CalcodeSliderV1 *s, double value);"""
    f = _normalize(value, s.minimum, s.maximum)
    return s.px0 + f * (s.px1 - s.px0)


def _slider_value(s: CalcodeSliderV1, px: float) -> float:
    """static double slider_value_v1(const CalcodeSliderV1 *s, double px);"""
    span = s.px1 - s.px0
    if span <= 0.0:
        return s.minimum
    return _denormalize((px - s.px0) / span, s.minimum, s.maximum)


def _make_layout(c: CalcodeLiveControlsV1) -> None:
    """static void make_layout_v1(CalcodeLiveControlsV1 *c);

    Bottom control strip:

        PLAY RESET < > SOLVE       TIME ----------------
                                             ^ knob

    A second thin slider is reserved for speed.
    """
    y = c.bottom

    timeline_left = 380.0
    timeline_right = float(c.width) - 25.0

    if timeline_right < timeline_left + 100.0:
        timeline_right = timeline_left + 100.0

    c.timeline.px0 = timeline_left
    c.timeline.px1 = timeline_right
    c.timeline.py0 = y + 12.0
    c.timeline.py1 = y + 25.0
    c.timeline.knob_radius = 7.0

    # Speed slider sits above the timeline in the right part of the strip.
    # It is deliberately independent of physical time.
    c.speed.px0 = timeline_left
    c.speed.px1 = timeline_right
    c.speed.py0 = y + 34.0
    c.speed.py1 = y + 43.0
    c.speed.knob_radius = 5.0


def calcode_live_controls_init_v1(c: Optional[CalcodeLiveControlsV1]) -> None:
    """void calcode_live_controls_init_v1(CalcodeLiveControlsV1 *controls);"""
    if c is None:
        return

    c.width = 1280
    c.height = 720

    c.bottom = 0.0
    c.control_height = 58.0

    c.timeline.minimum = 0.0
    c.timeline.maximum = 1.0
    c.timeline.value = 0.0

    c.speed.minimum = 0.1
    c.speed.maximum = 10.0
    c.speed.value = 1.0

    c.selected_time = 0.0
    c.selected_speed = 1.0

    _make_layout(c)


def calcode_live_controls_resize_v1(
    c: Optional[CalcodeLiveControlsV1], width: int, height: int
) -> None:
    """void calcode_live_controls_resize_v1(CalcodeLiveControlsV1 *controls, int width, int height);"""
    if c is None:
        return

    c.width = width if width > 1 else 1
    c.height = height if height > 1 else 1

    _make_layout(c)


def calcode_live_controls_set_time_domain_v1(
    c: Optional[CalcodeLiveControlsV1], t0: float, t1: float
) -> None:
    """void calcode_live_controls_set_time_domain_v1(CalcodeLiveControlsV1 *controls, double t0, double t1);"""
    if c is None:
        return

    if t1 < t0:
        t0, t1 = t1, t0

    if t1 == t0:
        t1 = t0 + 1.0

    c.timeline.minimum = t0
    c.timeline.maximum = t1

    c.timeline.value = _clamp(c.timeline.value, t0, t1)

    c.selected_time = c.timeline.value


def calcode_live_controls_set_time_v1(c: Optional[CalcodeLiveControlsV1], t: float) -> None:
    """void calcode_live_controls_set_time_v1(CalcodeLiveControlsV1 *controls, double t);"""
    if c is None:
        return

    c.timeline.value = _clamp(t, c.timeline.minimum, c.timeline.maximum)

    c.selected_time = c.timeline.value


def calcode_live_controls_set_speed_domain_v1(
    c: Optional[CalcodeLiveControlsV1], minimum: float, maximum: float
) -> None:
    """void calcode_live_controls_set_speed_domain_v1(CalcodeLiveControlsV1 *controls, double minimum, double maximum);"""
    if c is None:
        return

    if maximum < minimum:
        minimum, maximum = maximum, minimum

    if maximum == minimum:
        maximum = minimum + 1.0

    c.speed.minimum = minimum
    c.speed.maximum = maximum

    c.speed.value = _clamp(c.speed.value, minimum, maximum)

    c.selected_speed = c.speed.value


def calcode_live_controls_set_speed_v1(c: Optional[CalcodeLiveControlsV1], speed: float) -> None:
    """void calcode_live_controls_set_speed_v1(CalcodeLiveControlsV1 *controls, double speed);"""
    if c is None:
        return

    c.speed.value = _clamp(speed, c.speed.minimum, c.speed.maximum)

    c.selected_speed = c.speed.value


def calcode_live_controls_time_from_mouse_v1(
    c: Optional[CalcodeLiveControlsV1], x: float
) -> float:
    """double calcode_live_controls_time_from_mouse_v1(const CalcodeLiveControlsV1 *controls, double x);"""
    if c is None:
        return 0.0

    return _slider_value(c.timeline, x)


def calcode_live_controls_speed_from_mouse_v1(
    c: Optional[CalcodeLiveControlsV1], x: float
) -> float:
    """double calcode_live_controls_speed_from_mouse_v1(const CalcodeLiveControlsV1 *controls, double x);"""
    if c is None:
        return 1.0

    return _slider_value(c.speed, x)


def calcode_live_controls_mouse_move_v1(
    c: Optional[CalcodeLiveControlsV1], x: float, y: float
) -> None:
    """void calcode_live_controls_mouse_move_v1(CalcodeLiveControlsV1 *controls, double x, double y);"""
    if c is None:
        return

    c.mouse_x = x
    c.mouse_y = y

    c.hover_play = _hit_rect(x, y, 10.0, 7.0, 80.0, 35.0)
    c.hover_reset = _hit_rect(x, y, 88.0, 7.0, 158.0, 35.0)
    c.hover_step_back = _hit_rect(x, y, 166.0, 7.0, 204.0, 35.0)
    c.hover_step_forward = _hit_rect(x, y, 212.0, 7.0, 250.0, 35.0)
    c.hover_solve = _hit_rect(x, y, 258.0, 7.0, 330.0, 35.0)

    tcx = _slider_pixel(c.timeline, c.timeline.value)
    scx = _slider_pixel(c.speed, c.speed.value)

    c.timeline.hovered = _hit_circle(
        x, y, tcx, (c.timeline.py0 + c.timeline.py1) * 0.5, c.timeline.knob_radius + 5.0
    )

    c.speed.hovered = _hit_circle(
        x, y, scx, (c.speed.py0 + c.speed.py1) * 0.5, c.speed.knob_radius + 5.0
    )

    # Clicking anywhere on the track should also be useful, not only the
    # exact knob. This makes the time control behave like a scientific
    # coordinate ruler.
    if (
        x >= c.timeline.px0
        and x <= c.timeline.px1
        and y >= c.timeline.py0 - 8.0
        and y <= c.timeline.py1 + 8.0
    ):
        c.timeline.hovered = 1

    if (
        x >= c.speed.px0
        and x <= c.speed.px1
        and y >= c.speed.py0 - 8.0
        and y <= c.speed.py1 + 8.0
    ):
        c.speed.hovered = 1

    if c.timeline.dragging:
        c.timeline.value = calcode_live_controls_time_from_mouse_v1(c, x)
        c.selected_time = c.timeline.value

    if c.speed.dragging:
        c.speed.value = calcode_live_controls_speed_from_mouse_v1(c, x)
        c.selected_speed = c.speed.value


def calcode_live_controls_mouse_down_v1(
    c: Optional[CalcodeLiveControlsV1], x: float, y: float
) -> None:
    """void calcode_live_controls_mouse_down_v1(CalcodeLiveControlsV1 *controls, double x, double y);"""
    if c is None:
        return

    calcode_live_controls_mouse_move_v1(c, x, y)

    c.left_down = 1

    if c.timeline.hovered:
        c.timeline.dragging = 1
        c.timeline.value = calcode_live_controls_time_from_mouse_v1(c, x)
        c.selected_time = c.timeline.value
        return

    if c.speed.hovered:
        c.speed.dragging = 1
        c.speed.value = calcode_live_controls_speed_from_mouse_v1(c, x)
        c.selected_speed = c.speed.value
        return

    if c.hover_play:
        c.pressed_play = 1

    if c.hover_reset:
        c.pressed_reset = 1

    if c.hover_step_back:
        c.pressed_step_back = 1

    if c.hover_step_forward:
        c.pressed_step_forward = 1

    if c.hover_solve:
        c.pressed_solve = 1


def calcode_live_controls_mouse_up_v1(
    c: Optional[CalcodeLiveControlsV1], x: float, y: float
) -> None:
    """void calcode_live_controls_mouse_up_v1(CalcodeLiveControlsV1 *controls, double x, double y);"""
    if c is None:
        return

    calcode_live_controls_mouse_move_v1(c, x, y)

    c.left_down = 0

    c.timeline.dragging = 0
    c.speed.dragging = 0

    if c.pressed_play and c.hover_play:
        c.pending_action = CalcodeLiveActionV1.CALCODE_LIVE_PLAY_V1
    elif c.pressed_reset and c.hover_reset:
        c.pending_action = CalcodeLiveActionV1.CALCODE_LIVE_RESET_V1
    elif c.pressed_step_back and c.hover_step_back:
        c.pending_action = CalcodeLiveActionV1.CALCODE_LIVE_STEP_BACKWARD_V1
    elif c.pressed_step_forward and c.hover_step_forward:
        c.pending_action = CalcodeLiveActionV1.CALCODE_LIVE_STEP_FORWARD_V1
    elif c.pressed_solve and c.hover_solve:
        c.pending_action = CalcodeLiveActionV1.CALCODE_LIVE_SOLVE_V1

    c.pressed_play = 0
    c.pressed_reset = 0
    c.pressed_step_back = 0
    c.pressed_step_forward = 0
    c.pressed_solve = 0


def calcode_live_controls_take_action_v1(
    c: Optional[CalcodeLiveControlsV1],
) -> CalcodeLiveActionV1:
    """CalcodeLiveActionV1 calcode_live_controls_take_action_v1(CalcodeLiveControlsV1 *controls);"""
    if c is None:
        return CalcodeLiveActionV1.CALCODE_LIVE_NONE_V1

    action = c.pending_action
    c.pending_action = CalcodeLiveActionV1.CALCODE_LIVE_NONE_V1
    return action
