"""calcode_symbolic_parser_v1.py -- exact Python port of
calcode_symbolic_parser_v1.c / calcode_symbolic_parser_v1.h.

Original: recursive-descent parser that turns a source string into an
AST rooted in a CalcodeAstArenaV1 (calcode_symbolic_ast_v1). Grammar
(lowest to highest precedence):

    expression := term (('+' | '-') term)*
    term       := power (('*' | '/') power)*
    power      := unary ('^' power)?  ("'" )*      (right-assoc pow,
                                                      then postfix
                                                      derivative order)
    unary      := '-' unary | '+' unary | primary
    primary    := NUMBER
                | IDENTIFIER ('(' expression ')')?    (function call)
                | '(' expression ')'

Only the single import (calcode_symbolic_ast_v1) needed -- no other
project headers.

PORT NOTES:

- `source[2048]` is modeled as a plain Python `str`, but
  `calcode_symbolic_parse_v1` reproduces the C's
  `strncpy(..., 2047); source[2047] = '\\0'` truncation via a slice to
  2047 characters before parsing begins, so an over-long source string
  truncates identically on both sides (and any lexing differences that
  would follow from a truncated vs. untruncated source are preserved).
- `error_message[256]` built by `snprintf(..., "%s at character %d", ...)`
  is reproduced with an equivalent Python f-string; since no message
  text used in this module is anywhere near 256 chars, no truncation
  path is exercised, but the same `%s at character %d` layout is kept.
- `set_error_v1`'s "first error wins" behavior (`if (!p || p->error) return;`)
  is preserved exactly -- once `error` is set, subsequent calls are no-ops.
- Token `text[64]` truncates identifiers to 63 chars + implicit NUL,
  exactly like the C's `if (n < 63) text[n++] = ...` loop -- reproduced
  by only appending characters while the running length is < 63 (the
  lexer still *advances position* past the full identifier, it just
  stops writing further copied characters into `text`, matching the C).
- `parse_power_v1`'s use of `p->arena.nodes[left].source_begin` (a raw
  array index into the arena rather than `calcode_ast_get_v1`, which
  would bounds-check) is reproduced the same un-bounds-checked way via
  `p.arena.nodes[left]` -- this is safe here because `left`/`right`
  always come from indices this same parse just created and never taken
  from user-controlled data.
- No use of `calcode_ast_get_v1` in the ported logic, exactly as the C.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional

from calcy.symbolic.symbolic_ast_v1 import (
    CalcodeAstArenaV1,
    CalcodeAstKindV1,
    calcode_ast_init_v1,
    calcode_ast_number_v1,
    calcode_ast_identifier_v1,
    calcode_ast_unary_v1,
    calcode_ast_binary_v1,
    calcode_ast_function_v1,
    calcode_ast_derivative_v1,
    calcode_ast_set_root_v1,
)

CALCODE_SYMBOLIC_MAX_SOURCE_V1 = 2048
CALCODE_SYMBOLIC_MAX_ERROR_V1 = 256


class CalcodeSymbolicTokenKindV1(IntEnum):
    """typedef enum CalcodeSymbolicTokenKindV1 { ... } CalcodeSymbolicTokenKindV1;"""
    CALCODE_TOKEN_END_V1 = 0
    CALCODE_TOKEN_NUMBER_V1 = 1
    CALCODE_TOKEN_IDENTIFIER_V1 = 2
    CALCODE_TOKEN_PLUS_V1 = 3
    CALCODE_TOKEN_MINUS_V1 = 4
    CALCODE_TOKEN_STAR_V1 = 5
    CALCODE_TOKEN_SLASH_V1 = 6
    CALCODE_TOKEN_CARET_V1 = 7
    CALCODE_TOKEN_LPAREN_V1 = 8
    CALCODE_TOKEN_RPAREN_V1 = 9
    CALCODE_TOKEN_EQUALS_V1 = 10
    CALCODE_TOKEN_APOSTROPHE_V1 = 11


class CalcodeSymbolicTokenV1:
    """typedef struct CalcodeSymbolicTokenV1 { ... } CalcodeSymbolicTokenV1."""
    __slots__ = ("kind", "number", "text", "begin", "end")

    def __init__(self):
        self.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_END_V1
        self.number = 0.0
        self.text = ""
        self.begin = 0
        self.end = 0


class CalcodeSymbolicParserV1:
    """typedef struct CalcodeSymbolicParserV1 { ... } CalcodeSymbolicParserV1."""
    __slots__ = (
        "source", "current", "position", "error", "error_message", "arena",
    )

    def __init__(self):
        self.source = ""
        self.current = CalcodeSymbolicTokenV1()
        self.position = 0
        self.error = 0
        self.error_message = ""
        self.arena = CalcodeAstArenaV1()


def _is_space(c: str) -> bool:
    """isspace((unsigned char)c) -- C locale whitespace."""
    return c in (" ", "\t", "\n", "\v", "\f", "\r")


def _is_digit(c: str) -> bool:
    return "0" <= c <= "9"


def _is_alpha(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z")


def _is_alnum(c: str) -> bool:
    return _is_alpha(c) or _is_digit(c)


def _char_at(s: str, i: int) -> str:
    """s[i], or '\\0' past the end -- mirrors reading a NUL-terminated
    C buffer past the logical string content."""
    return s[i] if 0 <= i < len(s) else "\0"


def _set_error(p: CalcodeSymbolicParserV1, msg: Optional[str], position: int) -> None:
    """static void set_error_v1(...); -- first error wins."""
    if p is None or p.error:
        return
    p.error = 1
    text = f"{msg if msg is not None else 'syntax error'} at character {position}"
    p.error_message = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def _next_token(p: CalcodeSymbolicParserV1) -> None:
    """static void next_token_v1(CalcodeSymbolicParserV1 *p);"""
    if p is None:
        return

    while _is_space(_char_at(p.source, p.position)):
        p.position += 1

    begin = p.position
    c = _char_at(p.source, p.position)

    p.current = CalcodeSymbolicTokenV1()
    p.current.begin = begin
    p.current.end = begin

    if c == "\0":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_END_V1
        return

    if _is_digit(c) or c == ".":
        # Mirrors strtod(p->source + p->position, &end) called at a
        # position already known to start with a digit or '.' (the
        # dispatch condition above), so no leading-sign handling is
        # needed here -- strtod never sees a sign at this call site.
        j = p.position
        while _is_digit(_char_at(p.source, j)):
            j += 1
        if _char_at(p.source, j) == ".":
            j += 1
            while _is_digit(_char_at(p.source, j)):
                j += 1
        mantissa_end = j
        if _char_at(p.source, j) in ("e", "E"):
            k = j + 1
            if _char_at(p.source, k) in ("+", "-"):
                k += 1
            if _is_digit(_char_at(p.source, k)):
                k += 1
                while _is_digit(_char_at(p.source, k)):
                    k += 1
                mantissa_end = k

        text = p.source[p.position:mantissa_end]
        # strtod-equivalent: if nothing beyond an optional sign/dot was
        # actually consumed as a digit, this is not a valid number.
        has_digit = any(_is_digit(ch) for ch in text)

        if not has_digit:
            _set_error(p, "invalid number", begin)
            return

        value = float(text)
        p.position = mantissa_end
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_NUMBER_V1
        p.current.number = value
        p.current.end = p.position
        return

    if _is_alpha(c) or c == "_":
        n = 0
        buf = []
        while _is_alnum(_char_at(p.source, p.position)) or _char_at(p.source, p.position) == "_":
            if n < 63:
                buf.append(_char_at(p.source, p.position))
                n += 1
            p.position += 1

        p.current.text = "".join(buf)
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_IDENTIFIER_V1
        p.current.end = p.position
        return

    p.position += 1
    p.current.end = p.position

    if c == "+":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_PLUS_V1
    elif c == "-":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_MINUS_V1
    elif c == "*":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_STAR_V1
    elif c == "/":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_SLASH_V1
    elif c == "^":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_CARET_V1
    elif c == "(":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_LPAREN_V1
    elif c == ")":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_RPAREN_V1
    elif c == "=":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_EQUALS_V1
    elif c == "'":
        p.current.kind = CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_APOSTROPHE_V1
    else:
        _set_error(p, "unknown character", begin)


def _accept(p: CalcodeSymbolicParserV1, kind: CalcodeSymbolicTokenKindV1) -> int:
    """static int accept_v1(...);"""
    if p.current.kind == kind:
        _next_token(p)
        return 1
    return 0


def _parse_primary(p: CalcodeSymbolicParserV1) -> int:
    """static int parse_primary_v1(CalcodeSymbolicParserV1 *p);"""
    if p.error:
        return -1

    t = p.current

    if _accept(p, CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_NUMBER_V1):
        return calcode_ast_number_v1(p.arena, t.number, t.begin, t.end)

    if t.kind == CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_IDENTIFIER_V1:
        _next_token(p)

        if _accept(p, CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_LPAREN_V1):
            arg = _parse_expression(p)

            if not _accept(p, CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_RPAREN_V1):
                _set_error(p, "expected ')'", p.current.begin)
                return -1

            return calcode_ast_function_v1(p.arena, t.text, arg, t.begin, p.current.end)

        return calcode_ast_identifier_v1(p.arena, t.text, t.begin, t.end)

    if _accept(p, CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_LPAREN_V1):
        x = _parse_expression(p)

        if not _accept(p, CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_RPAREN_V1):
            _set_error(p, "expected ')'", p.current.begin)
            return -1
        return x

    _set_error(p, "expected expression", p.current.begin)
    return -1


def _parse_unary(p: CalcodeSymbolicParserV1) -> int:
    """static int parse_unary_v1(CalcodeSymbolicParserV1 *p);"""
    if _accept(p, CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_MINUS_V1):
        begin = p.current.begin - 1
        child = _parse_unary(p)
        if child < 0:
            return -1

        return calcode_ast_unary_v1(
            p.arena, CalcodeAstKindV1.CALCODE_AST_NEG_V1, child,
            begin, p.arena.nodes[child].source_end,
        )

    if _accept(p, CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_PLUS_V1):
        return _parse_unary(p)

    return _parse_primary(p)


def _parse_power(p: CalcodeSymbolicParserV1) -> int:
    """static int parse_power_v1(CalcodeSymbolicParserV1 *p);"""
    left = _parse_unary(p)
    if p.error:
        return -1

    if _accept(p, CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_CARET_V1):
        right = _parse_power(p)
        if right < 0:
            return -1

        left = calcode_ast_binary_v1(
            p.arena, CalcodeAstKindV1.CALCODE_AST_POW_V1,
            left, right,
            p.arena.nodes[left].source_begin,
            p.arena.nodes[right].source_end,
        )

    order = 0
    while _accept(p, CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_APOSTROPHE_V1):
        order += 1

    if order > 0:
        begin = p.arena.nodes[left].source_begin
        end = p.arena.nodes[left].source_end + order

        left = calcode_ast_derivative_v1(p.arena, left, order, begin, end)

    return left


def _parse_term(p: CalcodeSymbolicParserV1) -> int:
    """static int parse_term_v1(CalcodeSymbolicParserV1 *p);"""
    left = _parse_power(p)

    while not p.error and p.current.kind in (
        CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_STAR_V1,
        CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_SLASH_V1,
    ):
        op = p.current.kind
        _next_token(p)

        right = _parse_power(p)
        if right < 0:
            return -1

        left = calcode_ast_binary_v1(
            p.arena,
            CalcodeAstKindV1.CALCODE_AST_MUL_V1
            if op == CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_STAR_V1
            else CalcodeAstKindV1.CALCODE_AST_DIV_V1,
            left, right,
            p.arena.nodes[left].source_begin,
            p.arena.nodes[right].source_end,
        )

    return left


def _parse_expression(p: CalcodeSymbolicParserV1) -> int:
    """static int parse_expression_v1(CalcodeSymbolicParserV1 *p);"""
    left = _parse_term(p)

    while not p.error and p.current.kind in (
        CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_PLUS_V1,
        CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_MINUS_V1,
    ):
        op = p.current.kind
        _next_token(p)

        right = _parse_term(p)
        if right < 0:
            return -1

        left = calcode_ast_binary_v1(
            p.arena,
            CalcodeAstKindV1.CALCODE_AST_ADD_V1
            if op == CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_PLUS_V1
            else CalcodeAstKindV1.CALCODE_AST_SUB_V1,
            left, right,
            p.arena.nodes[left].source_begin,
            p.arena.nodes[right].source_end,
        )

    return left


def calcode_symbolic_parser_init_v1(p: Optional[CalcodeSymbolicParserV1]) -> None:
    """void calcode_symbolic_parser_init_v1(CalcodeSymbolicParserV1 *parser);"""
    if p is None:
        return
    p.source = ""
    p.current = CalcodeSymbolicTokenV1()
    p.position = 0
    p.error = 0
    p.error_message = ""
    p.arena = CalcodeAstArenaV1()
    calcode_ast_init_v1(p.arena)


def calcode_symbolic_parse_v1(
    p: Optional[CalcodeSymbolicParserV1], source: Optional[str]
) -> int:
    """int calcode_symbolic_parse_v1(CalcodeSymbolicParserV1 *parser, const char *source);"""
    if p is None or source is None:
        return 0

    calcode_symbolic_parser_init_v1(p)

    p.source = source[: CALCODE_SYMBOLIC_MAX_SOURCE_V1 - 1]

    p.position = 0
    _next_token(p)

    root = _parse_expression(p)

    if p.error:
        return 0

    if p.current.kind != CalcodeSymbolicTokenKindV1.CALCODE_TOKEN_END_V1:
        _set_error(p, "unexpected token", p.current.begin)
        return 0

    if root < 0:
        return 0

    calcode_ast_set_root_v1(p.arena, root)
    return 1


def calcode_symbolic_error_v1(p: Optional[CalcodeSymbolicParserV1]) -> str:
    """const char *calcode_symbolic_error_v1(const CalcodeSymbolicParserV1 *parser);"""
    if p is None:
        return "no parser"
    return p.error_message if p.error else ""


def calcode_symbolic_ast_v1(
    p: Optional[CalcodeSymbolicParserV1],
) -> Optional[CalcodeAstArenaV1]:
    """const CalcodeAstArenaV1 *calcode_symbolic_ast_v1(const CalcodeSymbolicParserV1 *parser);"""
    return p.arena if p is not None else None
