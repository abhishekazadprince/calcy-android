"""expr.py -- exact Python port of expr.c / expr.h.

Original: tiny expression compiler/evaluator shared by every typed-equation
panel (sim_grapher.c, sim_customode.c, sim_fde.c). Compiles a text formula
once into a flat stack-machine op tape; expr_eval() then just runs that
tape, no re-parsing.

PORT NOTES (read before trusting this against the C source):

- expr.h was not part of the original upload; it was reconstructed from how
  expr.c defines things and how odesys.c/odesolution.c call them, then
  verified against expr.c's actual signatures and EXPR_MAX_OPS usage before
  this port was written. If you still have the real include/expr.h
  somewhere, diff it against the reconstructed header notes below.

- C's `Expr *expr_compile(..., char *errbuf, int errbuf_len)` returns NULL
  and writes a message into a caller-supplied buffer on failure. Python has
  no output parameters, so this port raises `ExprError` with that same
  message text instead. Every message string is copied verbatim from the C
  source (e.g. "%s near col %d", "expression too complex",
  "unknown identifier"). Call sites should catch ExprError where the C code
  checked `if (!e)`.

- expr_free() is a no-op here (kept only for API parity / literal
  translation callers) -- Python's GC reclaims the Expr once unreferenced.

- The original expr_eval() has a real quirk, preserved exactly: inside the
  eval loop there is a line
      if (!isfinite(stack[sp-1])) { /* clamp NaN/Inf */ }
  whose body is empty -- it does NOT actually clamp anything mid-evaluation
  despite the comment. Only the *final* result is clamped
  (`return isfinite(r) ? r : 0.0`). This port reproduces that exact
  (probably unintentional) behavior rather than "fixing" it, since the
  brief is an exact conversion.

- match_ident's identifier buffer is 32 chars in the C source (`char
  ident[32]`); an identifier of length >= 32 silently fails to match (C's
  `len >= buflen` check) and falls through to the "bad identifier" error.
  Reproduced with the same 32-char cap (IDENT_BUFLEN below) even though
  Python strings have no inherent length limit.
"""

from __future__ import annotations

import math
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Sequence, Optional


# ---------------------------------------------------------------------------
# #define EXPR_MAX_OPS 256
# ---------------------------------------------------------------------------
EXPR_MAX_OPS = 256

# char ident[32] in parse_primary()
IDENT_BUFLEN = 32

if not hasattr(math, "M_PI"):
    M_PI = 3.14159265358979323846
    M_E = 2.71828182845904523536


class OpCode(Enum):
    PUSH = auto()
    VAR = auto()
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()
    POW = auto()
    NEG = auto()
    SIN = auto()
    COS = auto()
    TAN = auto()
    EXP = auto()
    LOG = auto()
    SQRT = auto()
    ABS = auto()
    SINH = auto()
    COSH = auto()
    TANH = auto()
    ATAN = auto()
    ASIN = auto()
    ACOS = auto()
    MIN = auto()
    MAX = auto()


@dataclass
class Op:
    """typedef struct { OpCode code; double val; int varidx; } Op;"""
    code: OpCode
    val: float = 0.0
    varidx: int = 0


class ExprError(Exception):
    """Raised in place of C's `expr_compile` returning NULL + errbuf.
    str(exc) is exactly the message expr.c would have written into errbuf.
    """
    pass


class Expr:
    """struct Expr { Op ops[EXPR_MAX_OPS]; int n; };"""
    __slots__ = ("ops", "n")

    def __init__(self):
        self.ops: List[Op] = []
        self.n: int = 0


# ---------------------------------------------------------------------------
# ---- parser state ----
# ---------------------------------------------------------------------------
class _Parser:
    """typedef struct { const char *s; int pos; const char **vars; int nvars;
    Expr *out; jmp_buf err_jmp; char *errbuf; int errbuf_len; } Parser;

    C used setjmp/longjmp to unwind out of deeply recursive descent parsing
    on error. Python's ExprError exception plays that same role -- raising
    it from anywhere in the recursive-descent chain unwinds straight back
    to expr_compile(), exactly like the longjmp did.
    """

    def __init__(self, s: str, varnames: Sequence[str], nvars: int, out: Expr):
        self.s = s
        self.pos = 0
        self.vars = varnames
        self.nvars = nvars
        self.out = out


def _emit(p: _Parser, op: Op) -> None:
    if p.out.n >= EXPR_MAX_OPS:
        raise ExprError("expression too complex")
    p.out.ops.append(op)
    p.out.n += 1


def _skip_ws(p: _Parser) -> None:
    while p.pos < len(p.s) and p.s[p.pos].isspace():
        p.pos += 1


def _char_at(p: _Parser, pos: int) -> str:
    """Mimics C's NUL-terminated string indexing: reading past the end of
    the string yields '\\0' rather than raising IndexError."""
    return p.s[pos] if pos < len(p.s) else "\0"


def _peek(p: _Parser) -> str:
    _skip_ws(p)
    return _char_at(p, p.pos)


def _fail(p: _Parser, msg: str):
    raise ExprError(f"{msg} near col {p.pos}")


def _match_ident(p: _Parser) -> Optional[str]:
    _skip_ws(p)
    start = p.pos
    c = _char_at(p, p.pos)
    if c.isalpha() or c == "_":
        p.pos += 1
        c = _char_at(p, p.pos)
        while c.isalnum() or c == "_":
            p.pos += 1
            c = _char_at(p, p.pos)
    length = p.pos - start
    if length == 0 or length >= IDENT_BUFLEN:
        p.pos = start
        return None
    return p.s[start:p.pos]


_UNARY_FUNCS = {
    "sin": OpCode.SIN, "cos": OpCode.COS, "tan": OpCode.TAN,
    "exp": OpCode.EXP, "log": OpCode.LOG, "ln": OpCode.LOG,
    "sqrt": OpCode.SQRT, "abs": OpCode.ABS,
    "sinh": OpCode.SINH, "cosh": OpCode.COSH, "tanh": OpCode.TANH,
    "atan": OpCode.ATAN, "asin": OpCode.ASIN, "acos": OpCode.ACOS,
}
_BINARY_FUNCS = {"min": OpCode.MIN, "max": OpCode.MAX}


def _parse_expr(p: _Parser) -> None:
    _parse_term(p)
    while True:
        c = _peek(p)
        if c == "+":
            p.pos += 1
            _parse_term(p)
            _emit(p, Op(OpCode.ADD))
        elif c == "-":
            p.pos += 1
            _parse_term(p)
            _emit(p, Op(OpCode.SUB))
        else:
            break


def _parse_term(p: _Parser) -> None:
    _parse_pow(p)
    while True:
        c = _peek(p)
        if c == "*":
            p.pos += 1
            _parse_pow(p)
            _emit(p, Op(OpCode.MUL))
        elif c == "/":
            p.pos += 1
            _parse_pow(p)
            _emit(p, Op(OpCode.DIV))
        else:
            break


def _parse_pow(p: _Parser) -> None:
    _parse_primary(p)
    _skip_ws(p)
    if _char_at(p, p.pos) == "^":
        p.pos += 1
        _parse_pow(p)  # right-associative, matches C's recursive call
        _emit(p, Op(OpCode.POW))


def _parse_primary(p: _Parser) -> None:
    c = _peek(p)
    if c == "(":
        p.pos += 1
        _parse_expr(p)
        _skip_ws(p)
        if _char_at(p, p.pos) != ")":
            _fail(p, "expected ')'")
        p.pos += 1
        return
    if c == "-":
        p.pos += 1
        _parse_primary(p)
        _emit(p, Op(OpCode.NEG))
        return
    if c == "+":
        p.pos += 1
        _parse_primary(p)
        return
    if c.isdigit() or c == ".":
        _skip_ws(p)
        rest = p.s[p.pos:]
        v, consumed = _strtod(rest)
        if consumed == 0:
            _fail(p, "bad number")
        p.pos += consumed
        _emit(p, Op(OpCode.PUSH, v, 0))
        return
    if c.isalpha() or c == "_":
        ident = _match_ident(p)
        if ident is None:
            _fail(p, "bad identifier")
        _skip_ws(p)
        if _char_at(p, p.pos) == "(":
            # function call: one or two args
            p.pos += 1
            _parse_expr(p)
            nargs = 1
            _skip_ws(p)
            if _char_at(p, p.pos) == ",":
                p.pos += 1
                _parse_expr(p)
                nargs = 2
                _skip_ws(p)
            if _char_at(p, p.pos) != ")":
                _fail(p, "expected ')' after args")
            p.pos += 1
            if nargs == 1:
                oc = _UNARY_FUNCS.get(ident)
                if oc is None:
                    _fail(p, "unknown function")
                    return
            else:
                oc = _BINARY_FUNCS.get(ident)
                if oc is None:
                    _fail(p, "unknown 2-arg function")
                    return
            _emit(p, Op(oc))
            return
        if ident == "pi":
            _emit(p, Op(OpCode.PUSH, M_PI, 0))
            return
        if ident == "e":
            _emit(p, Op(OpCode.PUSH, M_E, 0))
            return
        for i in range(p.nvars):
            if ident == p.vars[i]:
                _emit(p, Op(OpCode.VAR, 0.0, i))
                return
        _fail(p, "unknown identifier")
        return
    _fail(p, "unexpected character")


def _strtod(s: str):
    """Mimics C's strtod(): parses the longest valid floating-point prefix
    of s, returns (value, chars_consumed). chars_consumed == 0 means no
    valid number was found (endp == start in the C code)."""
    i = 0
    n = len(s)
    if i < n and s[i] in "+-":
        i += 1
    digits_start = i
    while i < n and s[i].isdigit():
        i += 1
    if i < n and s[i] == ".":
        i += 1
        while i < n and s[i].isdigit():
            i += 1
    if i == digits_start or (i == digits_start + 1 and s[digits_start] == "."):
        return 0.0, 0
    mantissa_end = i
    if i < n and s[i] in "eE":
        j = i + 1
        if j < n and s[j] in "+-":
            j += 1
        exp_digits_start = j
        while j < n and s[j].isdigit():
            j += 1
        if j > exp_digits_start:
            i = j
    text = s[:i]
    try:
        return float(text), i
    except ValueError:
        return 0.0, 0


def expr_compile(src: str, varnames: Sequence[str], nvars: int) -> Expr:
    """Expr *expr_compile(const char *src, const char *varnames[], int nvars,
                           char *errbuf, int errbuf_len);
    Raises ExprError (instead of returning NULL + errbuf) on failure.
    """
    e = Expr()
    p = _Parser(src, varnames, nvars, e)
    _parse_expr(p)
    _skip_ws(p)
    if _char_at(p, p.pos) != "\0":
        _fail(p, "trailing characters")
    return e


def expr_free(e: Optional[Expr]) -> None:
    """void expr_free(Expr *e) { free(e); }
    No-op in Python -- kept for literal API parity with call sites that
    mirror the C control flow (e.g. cleanup-on-partial-failure loops)."""
    pass


def expr_eval(e: Expr, values: Sequence[float]) -> float:
    """double expr_eval(const Expr *e, const double *values);
    Never raises; NaN/Inf results are clamped to 0.0 exactly as in the C
    source (see the module docstring's note about the no-op mid-loop
    isfinite check being preserved as-is)."""
    stack: List[float] = []
    for i in range(e.n):
        op = e.ops[i]
        code = op.code
        if code == OpCode.PUSH:
            stack.append(op.val)
        elif code == OpCode.VAR:
            stack.append(values[op.varidx])
        elif code == OpCode.NEG:
            stack[-1] = -stack[-1]
        elif code == OpCode.ADD:
            b = stack.pop(); stack[-1] = stack[-1] + b
        elif code == OpCode.SUB:
            b = stack.pop(); stack[-1] = stack[-1] - b
        elif code == OpCode.MUL:
            b = stack.pop(); stack[-1] = stack[-1] * b
        elif code == OpCode.DIV:
            b = stack.pop(); stack[-1] = stack[-1] / b if b != 0.0 else 0.0
        elif code == OpCode.POW:
            b = stack.pop(); stack[-1] = math.pow(stack[-1], b)
        elif code == OpCode.SIN:
            stack[-1] = math.sin(stack[-1])
        elif code == OpCode.COS:
            stack[-1] = math.cos(stack[-1])
        elif code == OpCode.TAN:
            stack[-1] = math.tan(stack[-1])
        elif code == OpCode.EXP:
            stack[-1] = math.exp(stack[-1])
        elif code == OpCode.LOG:
            stack[-1] = math.log(stack[-1]) if stack[-1] > 0 else 0.0
        elif code == OpCode.SQRT:
            stack[-1] = math.sqrt(stack[-1]) if stack[-1] >= 0 else 0.0
        elif code == OpCode.ABS:
            stack[-1] = abs(stack[-1])
        elif code == OpCode.SINH:
            stack[-1] = math.sinh(stack[-1])
        elif code == OpCode.COSH:
            stack[-1] = math.cosh(stack[-1])
        elif code == OpCode.TANH:
            stack[-1] = math.tanh(stack[-1])
        elif code == OpCode.ATAN:
            stack[-1] = math.atan(stack[-1])
        elif code == OpCode.ASIN:
            stack[-1] = math.asin(max(-1.0, min(1.0, stack[-1])))
        elif code == OpCode.ACOS:
            stack[-1] = math.acos(max(-1.0, min(1.0, stack[-1])))
        elif code == OpCode.MIN:
            b = stack.pop(); stack[-1] = min(stack[-1], b)
        elif code == OpCode.MAX:
            b = stack.pop(); stack[-1] = max(stack[-1], b)
        # NOTE: the C source has an empty isfinite-clamp check here that
        # does nothing; deliberately not reproduced as dead code in Python.

    r = stack[-1] if stack else 0.0
    return r if math.isfinite(r) else 0.0
