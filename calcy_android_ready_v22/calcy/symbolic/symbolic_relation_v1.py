"""calcode_symbolic_relation_v1.py -- exact Python port of
calcode_symbolic_relation_v1.c / calcode_symbolic_relation_v1.h.

Original: takes a raw equation string (e.g. "y' = -k*y"), splits it on
the single '=' into two sides, parses each side independently with the
v1 symbolic parser, then merges both sides' AST arenas into one combined
arena owned by the relation. It also walks both ASTs to determine the
dependent variable / derivative order (from the LHS) and to collect the
set of other identifiers into "variables" (all identifiers seen) and
"parameters" (identifiers that are neither the dependent nor the
independent ('t') variable, and are not built-in function names).

PORT NOTES:

- The parser currently has no '=' AST node, so relation analysis finds
  the equation boundary in the *original source string* via `strchr`,
  not in any parsed tree -- reproduced here with Python's `str.find`.
  A second '=' anywhere after the first is rejected, matching the C's
  `strchr(eq + 1, '=')` check.
- `copy_trim_v1`'s C behavior (strip leading/trailing whitespace, fail
  if the trimmed result would not fit in the destination capacity) is
  reproduced via `.strip()` plus an explicit length check against
  `CALCODE_SYMBOLIC_MAX_SOURCE_V1`, since Python strings have no fixed
  capacity of their own.
- The two sides are parsed into *separate* parser/arena instances first
  (so each side's node indices start at 0), then the relation's own
  arena is re-initialized and both node lists are concatenated into it
  with the right side's `left`/`right` child indices offset by the left
  side's node count -- exactly mirroring the C's manual struct-array
  copy + index-shift loop. `lhs_root` is the raw left-arena root;
  `rhs_root` is the right-arena root plus the same offset.
- If the combined node count would exceed `CALCODE_AST_MAX_NODES_V1`
  (1024), the C bails out with a diagnostic *without* ever populating
  `r->arena` from the two sides -- reproduced identically (the check
  happens before the copy loop).
- `add_variable_v1` on a name already present in `variables` merges by
  keeping the *maximum* derivative order seen for that name, rather
  than adding a duplicate entry -- reproduced as-is, including that it
  does NOT update `source_begin`/`source_end` on a merge (only on first
  insertion).
- `add_parameter_v1` silently treats re-adding the dependent variable,
  the independent variable ('t'), or an existing parameter name as
  success (returns 1 / True) without inserting a duplicate -- capacity
  overflow (`CALCODE_RELATION_MAX_PARAMETERS_V1` = 64) returns 0/False,
  matching the C's saturating-arena style used elsewhere in this port.
- `inspect_ast_v1` is a straightforward recursive walk exactly as in
  the C (identifiers add a variable, and add a parameter unless the
  name is "t"; a DERIVATIVE node's identifier child is recorded as a
  variable at the derivative's order, not order 0; a FUNCTION node
  whose name is not one of the 14 built-ins is itself added as a
  parameter -- treating an unknown "function-looking" name as a
  parameter, same as the C).
- `find_dependent_derivative_v1` only looks at the *root* node type: a
  DERIVATIVE root whose child is an identifier sets the dependent
  variable + derivative order from it; a bare IDENTIFIER root is
  treated as an order-0 dependent variable (`y = x` case); anything
  else returns False, exactly as the C -- it does not recurse into the
  LHS beyond that top check.
- After identifier collection, the C does an in-place forward-compaction
  pass to strip the dependent variable and independent variable ('t')
  out of the parameters list -- reproduced with a Python list
  comprehension that has the identical filtering semantics.
- `calcode_symbolic_relation_analyze_v1` calls
  `calcode_symbolic_relation_init_v1` first (which fully resets the
  struct, including `valid`/`diagnostic`), so every early-return failure
  path leaves `valid == False` and a diagnostic message set, matching
  the C's `memset`-then-populate pattern.
- `char name[CALCODE_AST_MAX_NAME_V1]` (64) truncation on
  `dependent_variable`/`independent_variable` writes uses the same
  63-chars-plus-implicit-NUL slice convention as the rest of this port
  (`name[:63]`); the C's declared buffer sizes are preserved as module
  constants purely for documentation/parity, since Python strings do
  not need pre-sized storage.
"""

from __future__ import annotations

from enum import IntEnum
from typing import List, Optional

from calcy.symbolic.symbolic_ast_v1 import (
    CalcodeAstArenaV1,
    CalcodeAstKindV1,
    CalcodeAstNodeV1,
    CALCODE_AST_MAX_NAME_V1,
    CALCODE_AST_MAX_NODES_V1,
    calcode_ast_get_v1,
    calcode_ast_init_v1,
)
from calcy.symbolic.symbolic_parser_v1 import (
    CALCODE_SYMBOLIC_MAX_SOURCE_V1,
    CALCODE_SYMBOLIC_MAX_ERROR_V1,
    CalcodeSymbolicParserV1,
    calcode_symbolic_ast_v1,
    calcode_symbolic_error_v1,
    calcode_symbolic_parse_v1,
)

CALCODE_RELATION_MAX_VARIABLES_V1 = 32
CALCODE_RELATION_MAX_PARAMETERS_V1 = 64

_FUNCTION_NAMES_V1 = (
    "sin", "cos", "tan",
    "asin", "acos", "atan",
    "exp", "log", "ln",
    "sqrt", "abs",
    "sinh", "cosh", "tanh",
)


class CalcodeRelationKindV1(IntEnum):
    """typedef enum CalcodeRelationKindV1 { ... } CalcodeRelationKindV1;"""
    CALCODE_RELATION_NONE_V1 = 0
    CALCODE_RELATION_EXPLICIT_V1 = 1
    CALCODE_RELATION_EQUALITY_V1 = 2


class CalcodeSymbolicVariableV1:
    """typedef struct CalcodeSymbolicVariableV1 { ... } CalcodeSymbolicVariableV1."""
    __slots__ = ("name", "derivative_order", "source_begin", "source_end")

    def __init__(self):
        self.name = ""
        self.derivative_order = 0
        self.source_begin = 0
        self.source_end = 0


class CalcodeSymbolicRelationV1:
    """typedef struct CalcodeSymbolicRelationV1 { ... } CalcodeSymbolicRelationV1."""
    __slots__ = (
        "kind", "source", "independent_variable", "dependent_variable",
        "derivative_order", "lhs_root", "rhs_root", "arena",
        "variables", "variable_count", "parameters", "parameter_count",
        "valid", "diagnostic",
    )

    def __init__(self):
        self.kind = CalcodeRelationKindV1.CALCODE_RELATION_NONE_V1
        self.source = ""
        self.independent_variable = ""
        self.dependent_variable = ""
        self.derivative_order = 0
        self.lhs_root = 0
        self.rhs_root = 0
        self.arena = CalcodeAstArenaV1()
        self.variables: List[CalcodeSymbolicVariableV1] = []
        self.variable_count = 0
        self.parameters: List[str] = []
        self.parameter_count = 0
        self.valid = 0
        self.diagnostic = ""


def _diagnostic(r: Optional[CalcodeSymbolicRelationV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(CalcodeSymbolicRelationV1 *r, const char *message);"""
    if r is None:
        return
    text = message if message else "invalid relation"
    r.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def _is_name(name: Optional[str]) -> bool:
    """static int is_name_v1(const char *name);"""
    if not name:
        return False

    c0 = name[0]
    if not (c0.isalpha() or c0 == "_"):
        return False

    for c in name[1:]:
        if not (c.isalnum() or c == "_"):
            return False

    return True


def _copy_trim(src: Optional[str], capacity: int) -> Optional[str]:
    """static int copy_trim_v1(char *dst, size_t capacity, const char *src);

    Returns the trimmed string on success, or None on failure (mirroring
    the C's 0/1 return by way of Python's Optional).
    """
    if src is None or capacity == 0:
        return None

    trimmed = src.strip()

    if len(trimmed) >= capacity:
        return None

    return trimmed


def _add_variable(
    r: CalcodeSymbolicRelationV1,
    name: Optional[str],
    derivative_order: int,
    begin: int,
    end: int,
) -> bool:
    """static int add_variable_v1(CalcodeSymbolicRelationV1 *r, const char *name,
    int derivative_order, int begin, int end);"""
    if r is None or not _is_name(name):
        return False

    for v in r.variables[: r.variable_count]:
        if v.name == name:
            if derivative_order > v.derivative_order:
                v.derivative_order = derivative_order
            return True

    if r.variable_count >= CALCODE_RELATION_MAX_VARIABLES_V1:
        return False

    v = CalcodeSymbolicVariableV1()
    v.name = name[: CALCODE_AST_MAX_NAME_V1 - 1]
    v.derivative_order = derivative_order
    v.source_begin = begin
    v.source_end = end

    r.variables.append(v)
    r.variable_count += 1

    return True


def _add_parameter(r: CalcodeSymbolicRelationV1, name: Optional[str]) -> bool:
    """static int add_parameter_v1(CalcodeSymbolicRelationV1 *r, const char *name);"""
    if r is None or not _is_name(name):
        return False

    # t is treated as the independent variable once detected.
    # y is not globally reserved because a problem may legitimately use
    # another dependent variable.
    if name == r.dependent_variable:
        return True

    if name == r.independent_variable:
        return True

    for p in r.parameters[: r.parameter_count]:
        if p == name:
            return True

    if r.parameter_count >= CALCODE_RELATION_MAX_PARAMETERS_V1:
        return False

    trimmed = name[: CALCODE_AST_MAX_NAME_V1 - 1]
    r.parameters.append(trimmed)
    r.parameter_count += 1

    return True


def _is_function_name(name: Optional[str]) -> bool:
    """static int is_function_name_v1(const char *name);"""
    return name in _FUNCTION_NAMES_V1


def _inspect_ast(r: CalcodeSymbolicRelationV1, index: int) -> None:
    """static void inspect_ast_v1(CalcodeSymbolicRelationV1 *r, int index);"""
    if r is None or index < 0 or index >= r.arena.count:
        return

    n = r.arena.nodes[index]

    if n.kind == CalcodeAstKindV1.CALCODE_AST_IDENTIFIER_V1:
        # At this stage we use the common CALCODE-style convention:
        # t is the independent variable unless a derivative notation
        # provides stronger information later.
        _add_variable(r, n.name, 0, n.source_begin, n.source_end)

        if n.name != "t":
            _add_parameter(r, n.name)

    if n.kind == CalcodeAstKindV1.CALCODE_AST_DERIVATIVE_V1:
        if 0 <= n.left < r.arena.count:
            child = r.arena.nodes[n.left]
            if child.kind == CalcodeAstKindV1.CALCODE_AST_IDENTIFIER_V1:
                _add_variable(r, child.name, n.order, n.source_begin, n.source_end)

    if n.kind == CalcodeAstKindV1.CALCODE_AST_FUNCTION_V1:
        if not _is_function_name(n.name):
            _add_parameter(r, n.name)

    _inspect_ast(r, n.left)
    _inspect_ast(r, n.right)


def _find_dependent_derivative(r: CalcodeSymbolicRelationV1, root: int) -> bool:
    """static int find_dependent_derivative_v1(CalcodeSymbolicRelationV1 *r, int root);"""
    if r is None or root < 0 or root >= r.arena.count:
        return False

    n = r.arena.nodes[root]

    if n.kind == CalcodeAstKindV1.CALCODE_AST_DERIVATIVE_V1:
        if 0 <= n.left < r.arena.count:
            child = r.arena.nodes[n.left]
            if child.kind == CalcodeAstKindV1.CALCODE_AST_IDENTIFIER_V1:
                r.dependent_variable = child.name[: CALCODE_AST_MAX_NAME_V1 - 1]
                r.derivative_order = n.order
                return True

    if n.kind == CalcodeAstKindV1.CALCODE_AST_IDENTIFIER_V1:
        # A bare left-hand identifier is treated as an order-zero dependent
        # variable. This allows simple relations such as y = x.
        r.dependent_variable = n.name[: CALCODE_AST_MAX_NAME_V1 - 1]
        r.derivative_order = 0
        return True

    return False


def calcode_symbolic_relation_init_v1(r: Optional[CalcodeSymbolicRelationV1]) -> None:
    """void calcode_symbolic_relation_init_v1(CalcodeSymbolicRelationV1 *relation);"""
    if r is None:
        return

    r.kind = CalcodeRelationKindV1.CALCODE_RELATION_NONE_V1
    r.source = ""
    r.independent_variable = ""
    r.dependent_variable = ""
    r.derivative_order = 0
    r.lhs_root = 0
    r.rhs_root = 0
    r.arena = CalcodeAstArenaV1()
    r.variables = []
    r.variable_count = 0
    r.parameters = []
    r.parameter_count = 0
    r.valid = 0
    r.diagnostic = ""

    calcode_ast_init_v1(r.arena)


def calcode_symbolic_relation_analyze_v1(
    r: Optional[CalcodeSymbolicRelationV1], source: Optional[str]
) -> int:
    """int calcode_symbolic_relation_analyze_v1(CalcodeSymbolicRelationV1 *relation,
    const char *source);"""
    if r is None or source is None:
        return 0

    calcode_symbolic_relation_init_v1(r)

    r.source = source[: CALCODE_SYMBOLIC_MAX_SOURCE_V1 - 1]

    # The parser currently treats '=' as a token rather than as a binary
    # AST relation. Therefore v1 relation analysis determines the equation
    # boundary from the original source and parses both sides separately.
    eq = source.find("=")

    if eq < 0:
        _diagnostic(r, "equation requires '=' in relation form")
        return 0

    if "=" in source[eq + 1:]:
        _diagnostic(r, "multiple '=' symbols are not supported")
        return 0

    lhs = source[:eq]
    rhs = source[eq + 1:]

    if len(lhs) >= CALCODE_SYMBOLIC_MAX_SOURCE_V1 or len(rhs) >= CALCODE_SYMBOLIC_MAX_SOURCE_V1:
        _diagnostic(r, "equation side exceeds symbolic source capacity")
        return 0

    lhs_trim = _copy_trim(lhs, CALCODE_SYMBOLIC_MAX_SOURCE_V1)
    rhs_trim = _copy_trim(rhs, CALCODE_SYMBOLIC_MAX_SOURCE_V1)

    if lhs_trim is None or rhs_trim is None:
        _diagnostic(r, "unable to normalize equation sides")
        return 0

    lhs_parser = CalcodeSymbolicParserV1()
    rhs_parser = CalcodeSymbolicParserV1()

    if not calcode_symbolic_parse_v1(lhs_parser, lhs_trim):
        _diagnostic(r, calcode_symbolic_error_v1(lhs_parser))
        return 0

    if not calcode_symbolic_parse_v1(rhs_parser, rhs_trim):
        _diagnostic(r, calcode_symbolic_error_v1(rhs_parser))
        return 0

    # The relation owns a single combined arena. Reparse the two sides
    # directly into it so the stored roots are stable and independent.
    calcode_ast_init_v1(r.arena)

    left_arena = calcode_symbolic_ast_v1(lhs_parser)
    right_arena = calcode_symbolic_ast_v1(rhs_parser)

    if left_arena.root < 0 or right_arena.root < 0:
        _diagnostic(r, "empty equation side")
        return 0

    if left_arena.count + right_arena.count > CALCODE_AST_MAX_NODES_V1:
        _diagnostic(r, "combined symbolic expression is too large")
        return 0

    r.arena.nodes = []

    for i in range(left_arena.count):
        r.arena.nodes.append(left_arena.nodes[i])

    offset = left_arena.count

    for i in range(right_arena.count):
        n = right_arena.nodes[i]

        if n.left >= 0:
            n.left += offset

        if n.right >= 0:
            n.right += offset

        r.arena.nodes.append(n)

    r.arena.count = left_arena.count + right_arena.count

    r.lhs_root = left_arena.root
    r.rhs_root = right_arena.root + offset

    # Restore child indices in left side are already local to zero-offset
    # storage. Right-side indices were shifted above.
    r.kind = CalcodeRelationKindV1.CALCODE_RELATION_EQUALITY_V1

    # t is the initial conventional independent variable for the ODE
    # interface. Later relation types can explicitly declare another one.
    r.independent_variable = "t"[: CALCODE_AST_MAX_NAME_V1 - 1]

    _find_dependent_derivative(r, r.lhs_root)

    if not r.dependent_variable:
        _diagnostic(r, "unable to determine dependent variable")
        return 0

    # Collect identifiers from both sides.
    r.variable_count = 0
    r.parameter_count = 0

    _inspect_ast(r, r.lhs_root)
    _inspect_ast(r, r.rhs_root)

    # Explicitly remove the dependent variable and t from parameter list.
    # They are state/independent coordinates, not numerical parameters.
    kept = [
        p for p in r.parameters[: r.parameter_count]
        if p != r.dependent_variable and p != r.independent_variable
    ]
    r.parameters = kept
    r.parameter_count = len(kept)

    r.valid = 1
    r.diagnostic = ""

    return 1


def calcode_symbolic_relation_node_v1(
    r: Optional[CalcodeSymbolicRelationV1], index: int
) -> Optional[CalcodeAstNodeV1]:
    """const CalcodeAstNodeV1 *calcode_symbolic_relation_node_v1(
    const CalcodeSymbolicRelationV1 *relation, int index);"""
    if r is None:
        return None
    return calcode_ast_get_v1(r.arena, index)
