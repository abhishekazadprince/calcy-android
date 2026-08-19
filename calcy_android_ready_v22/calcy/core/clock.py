"""calcode_clock.py -- exact Python port of calcode_clock.c / calcode_clock.h.

Original: a playback clock over a fixed [t0, t1] time domain (the domain
of an already-computed ODE solution). Drives play/pause/loop and
converts wall-clock deltas into simulation-time deltas via `speed`. The
clock never recomputes the solution -- it only selects a point on an
already-computed trajectory (see the comment preserved in
`calcode_clock_tick`).

PORT NOTES:

- `calcode_clock_init` swaps t0/t1 if passed reversed, exactly like the
  C (`if (t1 < t0) { swap }`).

- `calcode_clock_tick`'s loop-wraparound arithmetic uses a C
  `(long long)` cast, which truncates toward zero. The value being cast,
  `(c->t - c->t0) / span`, is always >= 0 here (this branch is only
  reached when `c->t > c->t1 >= c->t0`), so C's truncate-toward-zero and
  Python's `int()` truncate-toward-zero agree exactly -- no floor/int
  mismatch to work around.

- `c->last_wall_time == 0.0` as a "first tick" sentinel is reproduced
  literally (an exact float equality test, same as the C).
"""

from __future__ import annotations

from typing import Optional


def _clamp(x: float, lo: float, hi: float) -> float:
    """static double clamp(double x, double lo, double hi);"""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


class CalcodeClock:
    """typedef struct CalcodeClock { ... } CalcodeClock; (see calcode_clock.h)."""
    __slots__ = ("t", "t0", "t1", "speed", "playing", "loop", "last_wall_time")

    def __init__(self):
        # Mirrors memset(c, 0, sizeof(*c)); every call site goes through
        # calcode_clock_init before use, same as the C.
        self.t = 0.0
        self.t0 = 0.0
        self.t1 = 0.0
        self.speed = 0.0
        self.playing = 0
        self.loop = 0
        self.last_wall_time = 0.0


def calcode_clock_init(c: Optional[CalcodeClock], t0: float, t1: float) -> None:
    """void calcode_clock_init(CalcodeClock *c, double t0, double t1);"""
    if c is None:
        return

    if t1 < t0:
        t0, t1 = t1, t0

    c.t0 = t0
    c.t1 = t1
    c.t = t0

    c.speed = 1.0
    c.playing = 0
    c.loop = 1
    c.last_wall_time = 0.0


def calcode_clock_play(c: Optional[CalcodeClock]) -> None:
    """void calcode_clock_play(CalcodeClock *c);"""
    if c is None:
        return
    c.playing = 1


def calcode_clock_pause(c: Optional[CalcodeClock]) -> None:
    """void calcode_clock_pause(CalcodeClock *c);"""
    if c is None:
        return
    c.playing = 0


def calcode_clock_toggle(c: Optional[CalcodeClock]) -> None:
    """void calcode_clock_toggle(CalcodeClock *c);"""
    if c is None:
        return
    c.playing = 0 if c.playing else 1


def calcode_clock_reset(c: Optional[CalcodeClock]) -> None:
    """void calcode_clock_reset(CalcodeClock *c);"""
    if c is None:
        return
    c.t = c.t0
    c.playing = 0
    c.last_wall_time = 0.0


def calcode_clock_set_time(c: Optional[CalcodeClock], t: float) -> None:
    """void calcode_clock_set_time(CalcodeClock *c, double t);"""
    if c is None:
        return
    c.t = _clamp(t, c.t0, c.t1)


def calcode_clock_set_speed(c: Optional[CalcodeClock], speed: float) -> None:
    """void calcode_clock_set_speed(CalcodeClock *c, double speed);"""
    if c is None:
        return
    if speed < 0.0:
        speed = 0.0
    c.speed = speed


def calcode_clock_tick(c: Optional[CalcodeClock], wall_time: float) -> None:
    """void calcode_clock_tick(CalcodeClock *c, double wall_time);"""
    if c is None:
        return

    if c.last_wall_time == 0.0:
        c.last_wall_time = wall_time
        return

    dt = wall_time - c.last_wall_time
    c.last_wall_time = wall_time

    if not c.playing or dt <= 0.0:
        return

    # The numerical solution remains authoritative.
    # The clock only selects a point on that already computed trajectory.
    c.t += dt * c.speed

    if c.t > c.t1:
        if c.loop:
            span = c.t1 - c.t0
            if span > 0.0:
                c.t = c.t0 + (c.t - c.t0) - span * int((c.t - c.t0) / span)
            else:
                c.t = c.t1
        else:
            c.t = c.t1
            c.playing = 0


def calcode_clock_finished(c: Optional[CalcodeClock]) -> int:
    """int calcode_clock_finished(const CalcodeClock *c);"""
    if c is None:
        return 1
    return int((not c.loop) and c.t >= c.t1)
