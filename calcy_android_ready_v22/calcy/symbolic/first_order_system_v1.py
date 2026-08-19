"""calcode_first_order_system_v1.py -- exact Python port of
calcode_first_order_system_v1.c / calcode_first_order_system_v1.h.

Original: given an already-analyzed `CalcodeSymbolicRelationV1` of order
n (e.g. `y'' = F(...)` has order 2), builds the *structural* mapping to
a canonical first-order state vector:

    x0 = y, x1 = y', x2 = y'', ..., x(n-1) = y^(n-1)

so that the numerical system becomes

    x0' = x1
    x1' = x2
    ...
    x(n-1)' = F(...)

v1 only builds this structural mapping -- it deliberately does not
invent RHS expressions for the intermediate states (x0' = x1 etc.);
only the last state's RHS root is set, taken directly from the source
relation's `rhs_root`. Downstream code (rhs_generator_v1) is what turns
this structural description into an actual callable RHS function.

PORT NOTES:

- `s->source` in the C is a `const CalcodeSymbolicRelationV1 *` --
  reproduced as a direct reference to the same Python relation object
  passed in (Python has no separate pointer/value distinction, so this
  mirrors the C's "does not own a second symbolic copy" comment
  exactly: no fields are copied out of the relation's arena).
- `calcode_first_order_system_init_v1` fully resets the struct
  (mirroring the C's `memset`) and then explicitly sets every
  `rhs_root[i]` to -1, matching the C's post-memset loop (a memset
  alone would leave 0, not -1 -- a valid arena index -- as the C is
  careful to override).
- `state[i].name` uses `"%s_%d" % (dependent_variable, i + 1)`,
  reproducing the C's `snprintf(..., "%s_%d", ...)` format exactly
  (1-indexed suffix despite `derivative_order` itself being 0-indexed).
  The result is truncated to the `char name[64]` capacity the same way
  as elsewhere in this port (slice to 63 chars); in practice this only
  matters for pathologically long `dependent_variable` names, since the
  numeric suffix is small.
- Capacity check uses `CALCODE_FIRST_ORDER_MAX_STATE_V1` (16) against
  the relation's `derivative_order` directly, exactly as the C (not
  against the number of states actually built, since those are always
  equal in this v1 structural-only build).
- Every early-return failure path runs
  `calcode_first_order_system_init_v1` first (called at the very top of
  `calcode_first_order_system_build_v1`), so a failed build leaves
  `valid == False`, an empty state list, and every `rhs_root` entry at
  -1, matching the C's `memset`-then-populate pattern.
"""

from __future__ import annotations

from typing import List, Optional

from calcy.symbolic.symbolic_ast_v1 import CALCODE_AST_MAX_NAME_V1
from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.symbolic.symbolic_relation_v1 import CalcodeSymbolicRelationV1

CALCODE_FIRST_ORDER_MAX_STATE_V1 = 16


class CalcodeFirstOrderStateV1:
    """typedef struct CalcodeFirstOrderStateV1 { ... } CalcodeFirstOrderStateV1."""
    __slots__ = ("name", "derivative_order", "source_relation_order")

    def __init__(self):
        self.name = ""
        self.derivative_order = 0
        self.source_relation_order = 0


class CalcodeFirstOrderSystemV1:
    """typedef struct CalcodeFirstOrderSystemV1 { ... } CalcodeFirstOrderSystemV1."""
    __slots__ = (
        "valid", "state_dimension", "source_order",
        "independent_variable", "dependent_variable",
        "state", "rhs_root", "source", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.state_dimension = 0
        self.source_order = 0
        self.independent_variable = ""
        self.dependent_variable = ""
        self.state: List[CalcodeFirstOrderStateV1] = []
        self.rhs_root: List[int] = [-1] * CALCODE_FIRST_ORDER_MAX_STATE_V1
        self.source: Optional[CalcodeSymbolicRelationV1] = None
        self.diagnostic = ""


def _diagnostic(s: Optional[CalcodeFirstOrderSystemV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(CalcodeFirstOrderSystemV1 *s, const char *message);"""
    if s is None:
        return
    text = message if message else "invalid system"
    s.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_first_order_system_init_v1(s: Optional[CalcodeFirstOrderSystemV1]) -> None:
    """void calcode_first_order_system_init_v1(CalcodeFirstOrderSystemV1 *system);"""
    if s is None:
        return

    s.valid = 0
    s.state_dimension = 0
    s.source_order = 0
    s.independent_variable = ""
    s.dependent_variable = ""
    s.state = []
    s.rhs_root = [-1] * CALCODE_FIRST_ORDER_MAX_STATE_V1
    s.source = None
    s.diagnostic = ""


def calcode_first_order_system_build_v1(
    s: Optional[CalcodeFirstOrderSystemV1],
    r: Optional[CalcodeSymbolicRelationV1],
) -> int:
    """int calcode_first_order_system_build_v1(CalcodeFirstOrderSystemV1 *system,
    const CalcodeSymbolicRelationV1 *relation);"""
    if s is None or r is None:
        return 0

    calcode_first_order_system_init_v1(s)

    if not r.valid:
        _diagnostic(s, "source symbolic relation is invalid")
        return 0

    if r.derivative_order <= 0:
        _diagnostic(s, "relation has no positive derivative order")
        return 0

    if r.derivative_order > CALCODE_FIRST_ORDER_MAX_STATE_V1:
        _diagnostic(s, "derivative order exceeds state capacity")
        return 0

    s.source = r

    s.independent_variable = r.independent_variable[: CALCODE_AST_MAX_NAME_V1 - 1]
    s.dependent_variable = r.dependent_variable[: CALCODE_AST_MAX_NAME_V1 - 1]

    s.source_order = r.derivative_order
    s.state_dimension = r.derivative_order

    # Canonical state definition:
    #
    # x0 = y
    # x1 = y'
    # x2 = y''
    # ...
    # x(n-1) = y^(n-1)
    #
    # For the explicit highest derivative y^(n)=F(...),
    # the numerical system becomes
    #
    # x0' = x1
    # x1' = x2
    # ...
    # x(n-1)' = F
    #
    # v1 stores only the structural mapping. It deliberately does not
    # invent RHS expressions for the intermediate states yet.
    s.state = []
    for i in range(s.state_dimension):
        state = CalcodeFirstOrderStateV1()
        state.name = f"{r.dependent_variable}_{i + 1}"[: CALCODE_AST_MAX_NAME_V1 - 1]
        state.derivative_order = i
        state.source_relation_order = r.derivative_order

        s.state.append(state)
        s.rhs_root[i] = -1

    # Only the final state derivative can be mapped directly to the RHS
    # without algebraic rearrangement.
    #
    # For y^(n) = RHS:
    #
    #   x(n-1)' = RHS
    #
    # The earlier derivatives are structural shifts.
    s.rhs_root[s.state_dimension - 1] = r.rhs_root

    s.valid = 1
    s.diagnostic = ""

    return 1
