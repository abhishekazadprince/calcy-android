"""calcode_3d_animation_v1.py -- exact Python port of
calcode_3d_animation_v1.c / calcode_3d_animation_v1.h.

Original: a sample-index-stepping playback controller (forward,
reverse, loop, ping-pong) driving which trajectory sample the 3D
cursor/blob currently represents. Deliberately advances by whole
samples rather than interpolating continuously (see the C's own
comment, reproduced below).

PORT NOTES:

- `configure_v1` validates `playback_rate` (finite, `> 0.0`) and
  `mode` (must be one of the 4 enum values) *before* calling
  `init_v1` -- a rejected call leaves the animation untouched.
- `step_v1`: no-op success (`return 1`) if not currently playing.
  `magnitude = dt * playback_rate`; `steps = floor(magnitude)`,
  floored up to at least `1` (so even a tiny `dt` always advances by
  at least one sample while playing) -- reproduced with Python's
  `math.floor` (matching C's `floor()` including its float/double
  promotion behavior for this expression, which is already all
  `double`).
  For each of `steps` iterations: try to advance `sample_index` by
  `direction` (`+1`/`-1`); if that lands in range, just do it and
  `continue`. Otherwise dispatch on `mode`:
  - FORWARD: clamp to last sample, stop playing.
  - REVERSE: clamp to sample 0, stop playing.
  - LOOP: wrap to 0 (forward) or last sample (reverse); keep playing.
  - PINGPONG: flip `direction`, snap to the *new* direction's start
    (0 if now forward, last sample if now reverse); keep playing.
  - default (unreachable via the validated enum): stop playing.
  After the mode dispatch, the loop breaks early **only** if playback
  just stopped **and** the mode is neither LOOP nor PINGPONG --
  reproduced with that exact double condition, not simplified (LOOP/
  PINGPONG never actually reach here with `playing=0` in practice, but
  the guard is reproduced verbatim rather than assumed dead).
- `apply_cursor_v1`: thin pass-through to
  `calcode_3d_cursor_at_v1(cursor, trajectory, projection,
  animation.sample_index)`, after None/valid checks on the animation
  itself (not on trajectory/projection/cursor beyond non-None, that
  validation lives inside `cursor_at_v1`).
"""

import math
from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1

CALCODE_3D_PLAY_FORWARD_V1 = 0
CALCODE_3D_PLAY_REVERSE_V1 = 1
CALCODE_3D_PLAY_LOOP_V1 = 2
CALCODE_3D_PLAY_PINGPONG_V1 = 3


class Calcode3DAnimationV1:
    __slots__ = (
        "valid", "playback_rate", "time",
        "sample_index", "direction", "playing", "mode",
        "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.playback_rate = 0.0
        self.time = 0.0
        self.sample_index = 0
        self.direction = 0
        self.playing = 0
        self.mode = CALCODE_3D_PLAY_FORWARD_V1
        self.diagnostic = ""


def _diagnostic(a: Optional[Calcode3DAnimationV1], message: Optional[str]) -> None:
    if a is None:
        return
    text = message if message else "3D animation error"
    a.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_3d_animation_init_v1(a: Optional[Calcode3DAnimationV1]) -> None:
    if a is None:
        return

    a.valid = 0
    a.time = 0.0
    a.sample_index = 0
    a.playing = 0
    a.diagnostic = ""

    a.playback_rate = 1.0
    a.direction = 1
    a.mode = CALCODE_3D_PLAY_FORWARD_V1


def calcode_3d_animation_configure_v1(a, playback_rate: float, mode: int) -> int:
    if a is None or not math.isfinite(playback_rate) or playback_rate <= 0.0:
        return 0

    if mode < CALCODE_3D_PLAY_FORWARD_V1 or mode > CALCODE_3D_PLAY_PINGPONG_V1:
        return 0

    calcode_3d_animation_init_v1(a)

    a.playback_rate = playback_rate
    a.mode = mode
    a.valid = 1

    return 1


def calcode_3d_animation_start_v1(a) -> int:
    if a is None or not a.valid:
        return 0
    a.playing = 1
    return 1


def calcode_3d_animation_stop_v1(a) -> None:
    if a is None:
        return
    a.playing = 0


def calcode_3d_animation_seek_sample_v1(a, sample_index: int, sample_count: int) -> int:
    if (
        a is None
        or not a.valid
        or sample_count <= 0
        or sample_index < 0
        or sample_index >= sample_count
    ):
        return 0

    a.sample_index = sample_index

    return 1


def calcode_3d_animation_step_v1(a, sample_count: int, dt: float) -> int:
    if (
        a is None
        or not a.valid
        or sample_count <= 0
        or not math.isfinite(dt)
        or dt < 0.0
    ):
        return 0

    if not a.playing:
        return 1

    magnitude = dt * a.playback_rate

    steps = int(math.floor(magnitude))
    if steps < 1:
        steps = 1

    direction = 1 if a.direction >= 0 else -1

    for _ in range(steps):
        next_ = a.sample_index + direction

        if 0 <= next_ < sample_count:
            a.sample_index = next_
            continue

        if a.mode == CALCODE_3D_PLAY_FORWARD_V1:
            a.sample_index = sample_count - 1
            a.playing = 0

        elif a.mode == CALCODE_3D_PLAY_REVERSE_V1:
            a.sample_index = 0
            a.playing = 0

        elif a.mode == CALCODE_3D_PLAY_LOOP_V1:
            if direction > 0:
                a.sample_index = 0
            else:
                a.sample_index = sample_count - 1

        elif a.mode == CALCODE_3D_PLAY_PINGPONG_V1:
            a.direction = -direction
            a.sample_index = 0 if a.direction > 0 else sample_count - 1

        else:
            a.playing = 0

        if (
            not a.playing
            and a.mode != CALCODE_3D_PLAY_LOOP_V1
            and a.mode != CALCODE_3D_PLAY_PINGPONG_V1
        ):
            break

    return 1


def calcode_3d_animation_apply_cursor_v1(a, trajectory, projection, cursor) -> int:
    if a is None or not a.valid or trajectory is None or projection is None or cursor is None:
        return 0

    from calcy.trajectory.three_d_cursor_v1 import calcode_3d_cursor_at_v1

    return calcode_3d_cursor_at_v1(cursor, trajectory, projection, a.sample_index)
