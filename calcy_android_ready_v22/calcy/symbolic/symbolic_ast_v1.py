"""calcode_symbolic_ast_v1.py -- exact Python port of
calcode_symbolic_ast_v1.c / calcode_symbolic_ast_v1.h.

Original: the leaf-most module of the symbolic ODE input pipeline -- a
fixed-capacity arena of AST nodes (numbers, identifiers, unary/binary
ops, function calls, derivatives), addressed by integer index rather
than pointer. Every other symbolic-pipeline module builds on this one;
it has zero includes of its own besides <string.h> in the C.

PORT NOTES:

- The 1024-node fixed capacity (`CALCODE_AST_MAX_NODES_V1`) is preserved
  exactly, including the C's saturating-arena behavior: once
  `count >= 1024`, every node-creating function returns -1 forever
  after (`new_node_v1`'s guard), rather than growing a Python list
  without bound. This is deliberate -- the arena size is part of the
  original module's contract, and callers upstream may rely on -1
  meaning "arena exhausted."
- `name[CALCODE_AST_MAX_NAME_V1]` (`char name[64]`) is modeled as a
  plain Python `str`, but write sites replicate the C's
  `strncpy(..., 63); name[63] = '\\0'` truncate-to-63-chars-plus-NUL
  behavior via a slice to 63 characters, so a name longer than the C
  buffer truncates identically on both sides.
- `CalcodeAstNodeV1.left`/`.right` default to -1 (not 0), matching
  `new_node_v1` setting both explicitly after the zero-memset --  0 is
  a valid node index, so -1 is the real "no child" sentinel.
- `calcode_ast_get_v1` returns `None` for out-of-range/negative index
  or a NULL arena, mirroring the C's `NULL` return (Python has no
  const-pointer distinction, so the returned node here is the same
  mutable object as stored in the arena, same as the C returning a
  pointer into it).
- `calcode_ast_set_root_v1` silently no-ops if `root` is out of
  `[0, count)`, exactly as the C's `if (root >= 0 && root < a->count)`
  guard -- it does not raise or clamp.
"""

from __future__ import annotations

from enum import IntEnum
from typing import List, Optional

CALCODE_AST_MAX_NODES_V1 = 1024
CALCODE_AST_MAX_NAME_V1 = 64


class CalcodeAstKindV1(IntEnum):
    """typedef enum CalcodeAstKindV1 { ... } CalcodeAstKindV1;"""
    CALCODE_AST_NUMBER_V1 = 0
    CALCODE_AST_IDENTIFIER_V1 = 1
    CALCODE_AST_ADD_V1 = 2
    CALCODE_AST_SUB_V1 = 3
    CALCODE_AST_MUL_V1 = 4
    CALCODE_AST_DIV_V1 = 5
    CALCODE_AST_POW_V1 = 6
    CALCODE_AST_NEG_V1 = 7
    CALCODE_AST_FUNCTION_V1 = 8
    CALCODE_AST_DERIVATIVE_V1 = 9


class CalcodeAstNodeV1:
    """typedef struct CalcodeAstNodeV1 { ... } CalcodeAstNodeV1."""
    __slots__ = (
        "kind", "left", "right", "number", "name",
        "order", "source_begin", "source_end",
    )

    def __init__(self):
        # Mirrors memset(&a->nodes[i], 0, sizeof(...)) in new_node_v1,
        # followed by that function's explicit left=-1, right=-1.
        self.kind = CalcodeAstKindV1.CALCODE_AST_NUMBER_V1
        self.left = -1
        self.right = -1
        self.number = 0.0
        self.name = ""
        self.order = 0
        self.source_begin = 0
        self.source_end = 0


class CalcodeAstArenaV1:
    """typedef struct CalcodeAstArenaV1 { ... } CalcodeAstArenaV1."""
    __slots__ = ("nodes", "count", "root")

    def __init__(self):
        self.nodes: List[CalcodeAstNodeV1] = []
        self.count = 0
        self.root = 0


def _new_node(a: Optional[CalcodeAstArenaV1]) -> int:
    """static int new_node_v1(CalcodeAstArenaV1 *a);"""
    if a is None or a.count >= CALCODE_AST_MAX_NODES_V1:
        return -1

    i = a.count
    a.count += 1
    node = CalcodeAstNodeV1()
    a.nodes.append(node)
    return i


def calcode_ast_init_v1(a: Optional[CalcodeAstArenaV1]) -> None:
    """void calcode_ast_init_v1(CalcodeAstArenaV1 *arena);"""
    if a is None:
        return

    a.nodes = []
    a.count = 0
    a.root = -1


def calcode_ast_number_v1(
    a: Optional[CalcodeAstArenaV1], value: float, begin: int, end: int
) -> int:
    """int calcode_ast_number_v1(CalcodeAstArenaV1 *arena, double value, int begin, int end);"""
    i = _new_node(a)
    if i < 0:
        return -1

    a.nodes[i].kind = CalcodeAstKindV1.CALCODE_AST_NUMBER_V1
    a.nodes[i].number = value
    a.nodes[i].source_begin = begin
    a.nodes[i].source_end = end
    return i


def calcode_ast_identifier_v1(
    a: Optional[CalcodeAstArenaV1], name: Optional[str], begin: int, end: int
) -> int:
    """int calcode_ast_identifier_v1(CalcodeAstArenaV1 *arena, const char *name, int begin, int end);"""
    if name is None:
        return -1

    i = _new_node(a)
    if i < 0:
        return -1

    a.nodes[i].kind = CalcodeAstKindV1.CALCODE_AST_IDENTIFIER_V1
    a.nodes[i].name = name[: CALCODE_AST_MAX_NAME_V1 - 1]
    a.nodes[i].source_begin = begin
    a.nodes[i].source_end = end
    return i


def calcode_ast_unary_v1(
    a: Optional[CalcodeAstArenaV1],
    kind: CalcodeAstKindV1,
    child: int,
    begin: int,
    end: int,
) -> int:
    """int calcode_ast_unary_v1(CalcodeAstArenaV1 *arena, CalcodeAstKindV1 kind, int child, int begin, int end);"""
    if child < 0:
        return -1

    i = _new_node(a)
    if i < 0:
        return -1

    a.nodes[i].kind = kind
    a.nodes[i].left = child
    a.nodes[i].source_begin = begin
    a.nodes[i].source_end = end
    return i


def calcode_ast_binary_v1(
    a: Optional[CalcodeAstArenaV1],
    kind: CalcodeAstKindV1,
    left: int,
    right: int,
    begin: int,
    end: int,
) -> int:
    """int calcode_ast_binary_v1(CalcodeAstArenaV1 *arena, CalcodeAstKindV1 kind, int left, int right, int begin, int end);"""
    if left < 0 or right < 0:
        return -1

    i = _new_node(a)
    if i < 0:
        return -1

    a.nodes[i].kind = kind
    a.nodes[i].left = left
    a.nodes[i].right = right
    a.nodes[i].source_begin = begin
    a.nodes[i].source_end = end
    return i


def calcode_ast_function_v1(
    a: Optional[CalcodeAstArenaV1],
    name: Optional[str],
    argument: int,
    begin: int,
    end: int,
) -> int:
    """int calcode_ast_function_v1(CalcodeAstArenaV1 *arena, const char *name, int argument, int begin, int end);"""
    if name is None or argument < 0:
        return -1

    i = _new_node(a)
    if i < 0:
        return -1

    a.nodes[i].kind = CalcodeAstKindV1.CALCODE_AST_FUNCTION_V1
    a.nodes[i].left = argument
    a.nodes[i].name = name[: CALCODE_AST_MAX_NAME_V1 - 1]
    a.nodes[i].source_begin = begin
    a.nodes[i].source_end = end
    return i


def calcode_ast_derivative_v1(
    a: Optional[CalcodeAstArenaV1], child: int, order: int, begin: int, end: int
) -> int:
    """int calcode_ast_derivative_v1(CalcodeAstArenaV1 *arena, int child, int order, int begin, int end);"""
    if child < 0 or order <= 0:
        return -1

    i = _new_node(a)
    if i < 0:
        return -1

    a.nodes[i].kind = CalcodeAstKindV1.CALCODE_AST_DERIVATIVE_V1
    a.nodes[i].left = child
    a.nodes[i].order = order
    a.nodes[i].source_begin = begin
    a.nodes[i].source_end = end
    return i


def calcode_ast_get_v1(
    a: Optional[CalcodeAstArenaV1], index: int
) -> Optional[CalcodeAstNodeV1]:
    """const CalcodeAstNodeV1 *calcode_ast_get_v1(const CalcodeAstArenaV1 *arena, int index);"""
    if a is None or index < 0 or index >= a.count:
        return None
    return a.nodes[index]


def calcode_ast_set_root_v1(a: Optional[CalcodeAstArenaV1], root: int) -> None:
    """void calcode_ast_set_root_v1(CalcodeAstArenaV1 *arena, int root);"""
    if a is None:
        return
    if 0 <= root < a.count:
        a.root = root
