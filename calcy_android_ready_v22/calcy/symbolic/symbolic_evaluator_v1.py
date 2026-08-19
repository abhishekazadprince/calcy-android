"""calcode_symbolic_evaluator_v1.py -- exact Python port of
calcode_symbolic_evaluator_v1.c / calcode_symbolic_evaluator_v1.h.

Original: numerically evaluates a CalcodeAstArenaV1 tree given a set of
named variable bindings, with a small table of built-in math functions
and the intrinsic constants `pi`/`PI`/`e`. Only project include is
calcode_symbolic_ast_v1.h.

PORT NOTES:

- `bindings[64]` fixed-capacity array is modeled as a plain Python
  list, but `calcode_symbolic_evaluator_bind_v1` reproduces the C's
  exact capacity guard (`binding_count >= 64` rejects a *new* name,
  while rebinding an existing name always succeeds regardless of
  count) rather than relying on the list simply not growing further.
- `name[CALCODE_AST_MAX_NAME_V1]` (64) truncation on bind uses the same
  63-char slice convention as the AST/parser ports.
- `error_v1`'s "first error wins" behavior is preserved. This only
  matters *within* a single `eval_v1` call, since `eval_v1` resets
  `error`/`diagnostic` at the start of every call, matching the C.
- **`*value`-write fidelity**: the C's `eval_node_v1(..., double *value)`
  does NOT write `*value` on every failure path -- e.g. "invalid AST
  node", "unbound symbolic identifier", "division by zero", the two
  domain-error branches, "unknown symbolic function", the derivative
  node, and the default/unsupported case all call `error_v1` and
  `return 0` WITHOUT touching `*value`. But `CALCODE_AST_POW_V1` and
  every function-table success branch always write `*value` (even a
  non-finite one) before the final `return isfinite(*value);` -- so a
  caller can see a real `inf`/`nan` result alongside a `0` return code
  there, but must not assume anything was written for the other
  failure paths. This port reproduces that exactly via an explicit
  1-element list out-parameter (`out`) that is only assigned at the
  same points the C assigns `*value`/`left`/`right`, mirrored at every
  recursion level (each recursive call gets its own fresh local
  out-slot, exactly like the C's local `double left, right;`).
- `pow(left, right)` in C returns `inf`/`nan` for domain edge cases
  instead of raising, unlike Python's `**`/`math.pow`; `_safe_pow`
  below reproduces the C `pow()` classification for the edge cases that
  differ (negative base with non-integer exponent -> nan, 0 raised to
  a negative exponent -> inf). glibc's `pow()` additionally returns a
  **negatively-signed** NaN (`-nan` under `%.17g`) for the negative-
  base/non-integer-exponent case specifically (confirmed against the
  real C harness output), which `_safe_pow` reproduces via
  `math.copysign(math.nan, -1.0)` rather than plain `math.nan` --
  domain-error NaNs from `asin`/`acos` out-of-range inputs are
  positively signed in glibc and are left as plain `math.nan`.
"""

from __future__ import annotations

import math
from typing import List, Optional

from calcy.symbolic.symbolic_ast_v1 import CalcodeAstArenaV1, CalcodeAstKindV1

CALCODE_EVAL_MAX_BINDINGS_V1 = 64
CALCODE_AST_MAX_NAME_V1 = 64


class CalcodeEvalBindingV1:
    """typedef struct CalcodeEvalBindingV1 { ... } CalcodeEvalBindingV1."""
    __slots__ = ("name", "value")

    def __init__(self, name: str = "", value: float = 0.0):
        self.name = name
        self.value = value


class CalcodeSymbolicEvaluatorV1:
    """typedef struct CalcodeSymbolicEvaluatorV1 { ... } CalcodeSymbolicEvaluatorV1."""
    __slots__ = ("bindings", "binding_count", "error", "diagnostic")

    def __init__(self):
        self.bindings: List[CalcodeEvalBindingV1] = []
        self.binding_count = 0
        self.error = 0
        self.diagnostic = ""


def _error(e: Optional[CalcodeSymbolicEvaluatorV1], message: Optional[str]) -> None:
    """static void error_v1(...); -- first error wins."""
    if e is None or e.error:
        return
    e.error = 1
    text = message if message is not None else "symbolic evaluation error"
    e.diagnostic = text[:255]


def calcode_symbolic_evaluator_init_v1(e: Optional[CalcodeSymbolicEvaluatorV1]) -> None:
    """void calcode_symbolic_evaluator_init_v1(CalcodeSymbolicEvaluatorV1 *evaluator);"""
    if e is None:
        return
    e.bindings = []
    e.binding_count = 0
    e.error = 0
    e.diagnostic = ""


def calcode_symbolic_evaluator_bind_v1(
    e: Optional[CalcodeSymbolicEvaluatorV1], name: Optional[str], value: float
) -> int:
    """int calcode_symbolic_evaluator_bind_v1(CalcodeSymbolicEvaluatorV1 *evaluator, const char *name, double value);"""
    if e is None or not name:
        return 0

    for i in range(e.binding_count):
        if e.bindings[i].name == name:
            e.bindings[i].value = value
            return 1

    if e.binding_count >= CALCODE_EVAL_MAX_BINDINGS_V1:
        return 0

    truncated = name[: CALCODE_AST_MAX_NAME_V1 - 1]
    if len(e.bindings) <= e.binding_count:
        e.bindings.append(CalcodeEvalBindingV1())
    e.bindings[e.binding_count].name = truncated
    e.bindings[e.binding_count].value = value
    e.binding_count += 1

    return 1


def _lookup(
    e: Optional[CalcodeSymbolicEvaluatorV1], name: Optional[str]
) -> Optional[float]:
    """static int lookup_v1(...); -- returns the value or None if not found."""
    if e is None or not name:
        return None

    for i in range(e.binding_count):
        if e.bindings[i].name == name:
            return e.bindings[i].value

    return None


def _safe_pow(left: float, right: float) -> float:
    """Mirrors C's pow(left, right) domain classification, since
    Python's ** / math.pow raise where C's pow() returns inf/nan."""
    try:
        if left == 0.0 and right < 0.0:
            return math.inf
        if left < 0.0 and not float(right).is_integer():
            return math.copysign(math.nan, -1.0)
        return math.pow(left, right)
    except (ValueError, OverflowError):
        return math.inf
    except ZeroDivisionError:
        return math.inf


def _eval_node(
    e: CalcodeSymbolicEvaluatorV1, a: Optional[CalcodeAstArenaV1],
    index: int, out: List[float],
) -> int:
    """static int eval_node_v1(..., double *value); -- `out` stands in
    for `*value`: assigned only at the same points the C assigns it."""
    if a is None or index < 0 or index >= a.count:
        _error(e, "invalid AST node")
        return 0

    n = a.nodes[index]

    if n.kind == CalcodeAstKindV1.CALCODE_AST_NUMBER_V1:
        out[0] = n.number
        return 1

    if n.kind == CalcodeAstKindV1.CALCODE_AST_IDENTIFIER_V1:
        looked_up = _lookup(e, n.name)
        if looked_up is not None:
            out[0] = looked_up
            return 1

        if n.name in ("pi", "PI"):
            out[0] = math.acos(-1.0)
            return 1

        if n.name == "e":
            out[0] = math.exp(1.0)
            return 1

        _error(e, "unbound symbolic identifier")
        return 0

    if n.kind == CalcodeAstKindV1.CALCODE_AST_NEG_V1:
        left = [0.0]
        if not _eval_node(e, a, n.left, left):
            return 0
        out[0] = -left[0]
        return 1

    if n.kind in (
        CalcodeAstKindV1.CALCODE_AST_ADD_V1,
        CalcodeAstKindV1.CALCODE_AST_SUB_V1,
        CalcodeAstKindV1.CALCODE_AST_MUL_V1,
        CalcodeAstKindV1.CALCODE_AST_DIV_V1,
        CalcodeAstKindV1.CALCODE_AST_POW_V1,
    ):
        left = [0.0]
        right = [0.0]
        if not _eval_node(e, a, n.left, left):
            return 0
        if not _eval_node(e, a, n.right, right):
            return 0

        if n.kind == CalcodeAstKindV1.CALCODE_AST_ADD_V1:
            out[0] = left[0] + right[0]
            return 1
        if n.kind == CalcodeAstKindV1.CALCODE_AST_SUB_V1:
            out[0] = left[0] - right[0]
            return 1
        if n.kind == CalcodeAstKindV1.CALCODE_AST_MUL_V1:
            out[0] = left[0] * right[0]
            return 1
        if n.kind == CalcodeAstKindV1.CALCODE_AST_DIV_V1:
            if right[0] == 0.0:
                _error(e, "division by zero")
                return 0
            out[0] = left[0] / right[0]
            return 1
        if n.kind == CalcodeAstKindV1.CALCODE_AST_POW_V1:
            out[0] = _safe_pow(left[0], right[0])
            return 1 if math.isfinite(out[0]) else 0

    if n.kind == CalcodeAstKindV1.CALCODE_AST_FUNCTION_V1:
        left = [0.0]
        if not _eval_node(e, a, n.left, left):
            return 0
        arg = left[0]
        name = n.name

        if name == "sin":
            out[0] = math.sin(arg)
        elif name == "cos":
            out[0] = math.cos(arg)
        elif name == "tan":
            out[0] = math.tan(arg)
        elif name == "exp":
            try:
                out[0] = math.exp(arg)
            except OverflowError:
                out[0] = math.inf
        elif name in ("log", "ln"):
            if arg <= 0.0:
                _error(e, "logarithm domain error")
                return 0
            out[0] = math.log(arg)
        elif name == "sqrt":
            if arg < 0.0:
                _error(e, "square-root domain error")
                return 0
            out[0] = math.sqrt(arg)
        elif name == "abs":
            out[0] = math.fabs(arg)
        elif name == "asin":
            out[0] = math.asin(arg) if -1.0 <= arg <= 1.0 else math.nan
        elif name == "acos":
            out[0] = math.acos(arg) if -1.0 <= arg <= 1.0 else math.nan
        elif name == "atan":
            out[0] = math.atan(arg)
        elif name == "sinh":
            try:
                out[0] = math.sinh(arg)
            except OverflowError:
                out[0] = math.inf if arg > 0 else -math.inf
        elif name == "cosh":
            try:
                out[0] = math.cosh(arg)
            except OverflowError:
                out[0] = math.inf
        elif name == "tanh":
            out[0] = math.tanh(arg)
        else:
            _error(e, "unknown symbolic function")
            return 0

        return 1 if math.isfinite(out[0]) else 0

    if n.kind == CalcodeAstKindV1.CALCODE_AST_DERIVATIVE_V1:
        _error(e, "derivative node cannot be numerically evaluated directly")
        return 0

    _error(e, "unsupported symbolic node")
    return 0


def calcode_symbolic_evaluator_eval_v1(
    e: Optional[CalcodeSymbolicEvaluatorV1],
    a: Optional[CalcodeAstArenaV1],
    root: int,
    value: List[float],
) -> int:
    """int calcode_symbolic_evaluator_eval_v1(CalcodeSymbolicEvaluatorV1 *evaluator, const CalcodeAstArenaV1 *arena, int root, double *value);

    `value` is a 1-element list standing in for the C's `double *value`
    out-parameter -- see the module docstring for exactly when it is
    and isn't written, matching the C byte-for-byte.
    """
    if e is None or a is None or not value:
        return 0

    e.error = 0
    e.diagnostic = ""

    return _eval_node(e, a, root, value)
