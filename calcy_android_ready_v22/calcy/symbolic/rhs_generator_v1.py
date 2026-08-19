"""calcode_rhs_generator_v1.py -- exact Python port of
calcode_rhs_generator_v1.c / calcode_rhs_generator_v1.h.

Original: given an already-built `CalcodeFirstOrderSystemV1` (and its
source `CalcodeSymbolicRelationV1`), generates one "canonical equation"
per state: for every state but the last, a structural SHIFT equation
(x_i' = x_(i+1), no AST needed -- the state mapping itself defines it);
for the last state, an RHS equation that keeps the original symbolic
RHS AST root from the relation (the actual bridge to numerical
evaluation). Each equation also carries a human-readable label and the
source span it corresponds to, for diagnostics/UI display.

PORT NOTES:

- `system->source != relation` (C pointer-identity check) is
  reproduced as Python `is not` identity comparison -- this is
  deliberately an identity check, not an equality/value check, exactly
  matching the C's raw pointer comparison. A `CalcodeFirstOrderSystemV1`
  built from a *different* (even structurally identical) relation
  object must fail this check, same as in C.
- `calcode_rhs_generator_init_v1` fully resets the struct and then, for
  every one of the 16 fixed equation slots, sets `rhs_root = -1` and
  `state_index = i` -- reproduced as an explicit post-reset loop
  building all 16 `CalcodeCanonicalEquationV1` slots up front (mirroring
  the C's fixed-size array + memset-then-override pattern), not just
  the `dimension` slots that end up populated by a later build.
- `make_shift_label_v1`'s two label formats
  (`"{dep}_{i+1}' = {dep}_{i+2}"` for a shift row, `"{dep}_{i+1}' = RHS"`
  for the final row) are reproduced with the same 1-indexed state
  numbering as the C's `%d` args (`state_index + 1` / `+ 2`), and
  truncated to the C's `char equation_label[128]` capacity via a slice
  to 127 characters.
- For a SHIFT row, `source_begin`/`source_end` are taken from the
  relation's *LHS* root node (not the RHS) -- reproduced exactly,
  including that this happens for every shift row, not just the first.
- For the final RHS row, `source_begin`/`source_end` are only set if
  `relation.rhs_root` is a valid in-range arena index; otherwise they
  stay at their init default of 0 (from the struct reset), matching
  the C's guarded `if` with no `else` branch.
- `eq->state_name` truncates to `CALCODE_AST_MAX_NAME_V1` (64) via the
  same 63-char slice convention used throughout this port.
- `calcode_rhs_generator_equation_v1` returns `None` for a NULL/invalid
  generator or an out-of-`[0, dimension)` index, matching the C's NULL
  return -- and, like the arena's `calcode_ast_get_v1`, the returned
  object is the same mutable instance stored in `equations`, not a copy
  (the C returns a `const` pointer into the same array).
"""

from __future__ import annotations

from enum import IntEnum
from typing import List, Optional

from calcy.symbolic.symbolic_ast_v1 import CALCODE_AST_MAX_NAME_V1
from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.symbolic.symbolic_relation_v1 import CalcodeSymbolicRelationV1
from calcy.symbolic.first_order_system_v1 import (
    CALCODE_FIRST_ORDER_MAX_STATE_V1,
    CalcodeFirstOrderSystemV1,
)

CALCODE_EQUATION_LABEL_MAX_V1 = 128


class CalcodeCanonicalEquationKindV1(IntEnum):
    """typedef enum CalcodeCanonicalEquationKindV1 { ... } CalcodeCanonicalEquationKindV1."""
    CALCODE_CANONICAL_SHIFT_V1 = 0
    CALCODE_CANONICAL_RHS_V1 = 1


class CalcodeCanonicalEquationV1:
    """typedef struct CalcodeCanonicalEquationV1 { ... } CalcodeCanonicalEquationV1."""
    __slots__ = (
        "kind", "state_index", "lhs_derivative_order", "rhs_root",
        "state_name", "equation_label", "source_begin", "source_end",
    )

    def __init__(self):
        self.kind = CalcodeCanonicalEquationKindV1.CALCODE_CANONICAL_SHIFT_V1
        self.state_index = 0
        self.lhs_derivative_order = 0
        self.rhs_root = -1
        self.state_name = ""
        self.equation_label = ""
        self.source_begin = 0
        self.source_end = 0


class CalcodeRhsGeneratorV1:
    """typedef struct CalcodeRhsGeneratorV1 { ... } CalcodeRhsGeneratorV1."""
    __slots__ = (
        "valid", "dimension", "equations",
        "source_relation", "source_system", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.dimension = 0
        self.equations: List[CalcodeCanonicalEquationV1] = []
        self.source_relation: Optional[CalcodeSymbolicRelationV1] = None
        self.source_system: Optional[CalcodeFirstOrderSystemV1] = None
        self.diagnostic = ""


def _diagnostic(g: Optional[CalcodeRhsGeneratorV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(CalcodeRhsGeneratorV1 *g, const char *message);"""
    if g is None:
        return
    text = message if message else "invalid RHS generator state"
    g.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_rhs_generator_init_v1(g: Optional[CalcodeRhsGeneratorV1]) -> None:
    """void calcode_rhs_generator_init_v1(CalcodeRhsGeneratorV1 *generator);"""
    if g is None:
        return

    g.valid = 0
    g.dimension = 0
    g.source_relation = None
    g.source_system = None
    g.diagnostic = ""

    g.equations = []
    for i in range(CALCODE_FIRST_ORDER_MAX_STATE_V1):
        eq = CalcodeCanonicalEquationV1()
        eq.rhs_root = -1
        eq.state_index = i
        g.equations.append(eq)


def _make_shift_label(
    eq: CalcodeCanonicalEquationV1,
    state_index: int,
    dimension: int,
    dependent: Optional[str],
) -> None:
    """static void make_shift_label_v1(CalcodeCanonicalEquationV1 *eq,
    int state_index, int dimension, const char *dependent);"""
    if eq is None or not dependent:
        return

    if state_index < dimension - 1:
        label = f"{dependent}_{state_index + 1}' = {dependent}_{state_index + 2}"
    else:
        label = f"{dependent}_{state_index + 1}' = RHS"

    eq.equation_label = label[: CALCODE_EQUATION_LABEL_MAX_V1 - 1]


def calcode_rhs_generator_build_v1(
    g: Optional[CalcodeRhsGeneratorV1],
    relation: Optional[CalcodeSymbolicRelationV1],
    system: Optional[CalcodeFirstOrderSystemV1],
) -> int:
    """int calcode_rhs_generator_build_v1(CalcodeRhsGeneratorV1 *generator,
    const CalcodeSymbolicRelationV1 *relation,
    const CalcodeFirstOrderSystemV1 *system);"""
    if g is None or relation is None or system is None:
        return 0

    calcode_rhs_generator_init_v1(g)

    if not relation.valid:
        _diagnostic(g, "symbolic relation is invalid")
        return 0

    if not system.valid:
        _diagnostic(g, "first-order system is invalid")
        return 0

    if system.source is not relation:
        _diagnostic(g, "system does not reference supplied symbolic relation")
        return 0

    if system.state_dimension <= 0 or system.state_dimension > CALCODE_FIRST_ORDER_MAX_STATE_V1:
        _diagnostic(g, "invalid state dimension")
        return 0

    g.dimension = system.state_dimension
    g.source_relation = relation
    g.source_system = system

    for i in range(g.dimension):
        eq = g.equations[i]

        eq.state_index = i
        eq.lhs_derivative_order = i + 1

        eq.state_name = system.state[i].name[: CALCODE_AST_MAX_NAME_V1 - 1]

        _make_shift_label(eq, i, g.dimension, system.dependent_variable)

        if i < g.dimension - 1:
            # Structural shift:
            #
            # x_i' = x_(i+1)
            #
            # No copied AST is necessary because the state mapping already
            # defines the relationship.
            eq.kind = CalcodeCanonicalEquationKindV1.CALCODE_CANONICAL_SHIFT_V1
            eq.rhs_root = -1

            lhs_node = relation.arena.nodes[relation.lhs_root]
            eq.source_begin = lhs_node.source_begin
            eq.source_end = lhs_node.source_end

        else:
            # Highest derivative:
            #
            # x_n' = F(...)
            #
            # Keep the original RHS AST root. This is the critical bridge
            # between symbolic mathematics and later numerical evaluation.
            eq.kind = CalcodeCanonicalEquationKindV1.CALCODE_CANONICAL_RHS_V1
            eq.rhs_root = relation.rhs_root

            if 0 <= relation.rhs_root < relation.arena.count:
                rhs_node = relation.arena.nodes[relation.rhs_root]
                eq.source_begin = rhs_node.source_begin
                eq.source_end = rhs_node.source_end

    g.valid = 1
    g.diagnostic = ""

    return 1


def calcode_rhs_generator_equation_v1(
    g: Optional[CalcodeRhsGeneratorV1], state_index: int
) -> Optional[CalcodeCanonicalEquationV1]:
    """const CalcodeCanonicalEquationV1 *calcode_rhs_generator_equation_v1(
    const CalcodeRhsGeneratorV1 *generator, int state_index);"""
    if g is None or not g.valid or state_index < 0 or state_index >= g.dimension:
        return None

    return g.equations[state_index]
