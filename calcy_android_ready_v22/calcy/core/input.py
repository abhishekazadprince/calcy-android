"""calcode_input.py -- exact Python port of calcode_input.c / calcode_input.h.

Original: the input-action enum and the raw mouse/modifier state struct
shared across the lab/scene layer. `calcode_input.c` itself has only two
trivial functions (init, clear_action); the enum and struct carry the
real content and are ported here as a Python IntEnum + dataclass-like
class to match the C's `typedef enum` / `typedef struct` 1:1.

PORT NOTES:

- Enum values are assigned explicitly to match the C's implicit
  0,1,2,... ordering starting at CALCODE_INPUT_NONE = 0, so any code
  that persists/compares the integer value stays compatible.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional


class CalcodeInputAction(IntEnum):
    """typedef enum CalcodeInputAction { ... } CalcodeInputAction;"""
    CALCODE_INPUT_NONE = 0

    CALCODE_INPUT_PLAY_PAUSE = 1
    CALCODE_INPUT_RESET = 2
    CALCODE_INPUT_STEP_FORWARD = 3
    CALCODE_INPUT_STEP_BACKWARD = 4

    CALCODE_INPUT_SPEED_UP = 5
    CALCODE_INPUT_SPEED_DOWN = 6

    CALCODE_INPUT_CAMERA_LEFT = 7
    CALCODE_INPUT_CAMERA_RIGHT = 8
    CALCODE_INPUT_CAMERA_UP = 9
    CALCODE_INPUT_CAMERA_DOWN = 10

    CALCODE_INPUT_ZOOM_IN = 11
    CALCODE_INPUT_ZOOM_OUT = 12

    CALCODE_INPUT_GRAPH = 13
    CALCODE_INPUT_PHASE = 14
    CALCODE_INPUT_3D = 15
    CALCODE_INPUT_SPLIT = 16

    CALCODE_INPUT_QUIT = 17


class CalcodeInputState:
    """typedef struct CalcodeInputState { ... } CalcodeInputState; (see calcode_input.h)."""
    __slots__ = (
        "mouse_left", "mouse_right",
        "mouse_x", "mouse_y",
        "drag_x", "drag_y",
        "shift", "ctrl", "alt",
        "action",
    )

    def __init__(self):
        # Mirrors memset(s, 0, sizeof(*s)) performed by calcode_input_init;
        # every call site goes through calcode_input_init before use,
        # same as the C.
        self.mouse_left = 0
        self.mouse_right = 0
        self.mouse_x = 0.0
        self.mouse_y = 0.0
        self.drag_x = 0.0
        self.drag_y = 0.0
        self.shift = 0
        self.ctrl = 0
        self.alt = 0
        self.action = CalcodeInputAction.CALCODE_INPUT_NONE


def calcode_input_init(s: Optional[CalcodeInputState]) -> None:
    """void calcode_input_init(CalcodeInputState *state);"""
    if s is None:
        return

    s.mouse_left = 0
    s.mouse_right = 0
    s.mouse_x = 0.0
    s.mouse_y = 0.0
    s.drag_x = 0.0
    s.drag_y = 0.0
    s.shift = 0
    s.ctrl = 0
    s.alt = 0
    s.action = CalcodeInputAction.CALCODE_INPUT_NONE


def calcode_input_clear_action(s: Optional[CalcodeInputState]) -> None:
    """void calcode_input_clear_action(CalcodeInputState *state);"""
    if s is None:
        return
    s.action = CalcodeInputAction.CALCODE_INPUT_NONE
