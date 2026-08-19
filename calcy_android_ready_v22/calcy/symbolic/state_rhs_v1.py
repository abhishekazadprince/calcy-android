"""calcode_state_rhs_v1.py -- exact Python port of
calcode_state_rhs_v1.c / calcode_state_rhs_v1.h.

Original: given an already-built `CalcodeRhsGeneratorV1`, wraps it as a
numerical ODE right-hand side function suitable for an integrator: the
first `dimension - 1` state derivatives are the pure kinematic shift
`y_i' = y_(i+1)`, and the final derivative is the symbolic RHS
expression, numerically evaluated by binding the independent variable,
the dependent variable's canonical name, its per-state aliases
(`y_1`, `y_2`, ...), and any supplied parameters into a fresh
`CalcodeSymbolicEvaluatorV1` for every call.

PORT NOTES:

- `CalcodeStateRhsContextV1.state` is the C's `const double *state`
  (a caller-owned pointer into the current integrator state vector,
  not copied). Reproduced here as a plain Python sequence reference
  (list/tuple), never copied by this module either -- callers must
  keep `context.state` valid for the duration of an eval call, exactly
  as in C.
- `calcode_state_rhs_context_init_v1` resets `state` to `None` (C's
  NULL) and `state_dimension` to 0, matching the C's `memset`.
- `calcode_state_rhs_parameter_v1`'s "rebind if name already present,
  else append up to the fixed cap" logic mirrors
  `calcode_symbolic_evaluator_bind_v1`'s pattern exactly: an existing
  name is always updated regardless of the current count, and only a
  genuinely *new* name is rejected once
  `CALCODE_STATE_RHS_MAX_PARAMETERS_V1` (64) is reached.
- `calcode_state_rhs_build_v1` fully re-inits `rhs` first (matching the
  C's unconditional `calcode_state_rhs_init_v1(rhs)` at the top), then
  validates `generator->valid`, `generator->source_relation` +
  `generator->source_system` (both must be present), and
  `generator->dimension > 0`, in that exact order, writing the same
  diagnostic message for each failure path.
- `dependent_variable` / `independent_variable` are copied from
  `generator.source_system.dependent_variable` /
  `.independent_variable` with the same 63-char truncation convention
  used throughout this port (`CALCODE_AST_MAX_NAME_V1` - 1).
- `calcode_state_rhs_eval_v1` requires `context.state_dimension ==
  rhs.dimension` exactly (not just `>=`), matching the C's `!=` guard,
  and requires `context.state` to be non-NULL/non-empty.
- The derivative array is fully zeroed first (matching the C's
  init loop), then the shift rows `derivative[i] = state[i + 1]` are
  filled for `i` in `[0, dimension - 1)`, exactly like the C.
- The final-row lookup uses `calcode_rhs_generator_equation_v1` and
  bails out (returning 0, leaving the already-zeroed `derivative`
  array as the C does -- it never resets `derivative` again on this
  path) if the equation is missing or its `rhs_root` is negative.
- `bind_state_symbols_v1` binds, in this exact order: independent
  variable -> `context.t`, dependent variable -> `state[0]`, then each
  alias `f"{dependent}_{i+1}"` -> `state[i]` for `i` in
  `[0, state_dimension)` (note: alias `_1` therefore rebinds the same
  slot as the bare dependent-variable name, exactly duplicating the
  C's behavior), then every supplied parameter by name. Any bind
  failure aborts immediately (matching the C's early `return 0`).
- A fresh `CalcodeSymbolicEvaluatorV1` is created and initialized on
  every `eval_v1` call (matching the C's local, stack-allocated
  `CalcodeSymbolicEvaluatorV1 evaluator;` + explicit init), not reused
  across calls.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from calcy.symbolic.symbolic_ast_v1 import CALCODE_AST_MAX_NAME_V1
from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.symbolic.symbolic_evaluator_v1 import (
    CalcodeSymbolicEvaluatorV1,
    calcode_symbolic_evaluator_init_v1,
    calcode_symbolic_evaluator_bind_v1,
    calcode_symbolic_evaluator_eval_v1,
)
from calcy.symbolic.rhs_generator_v1 import (
    CalcodeRhsGeneratorV1,
    calcode_rhs_generator_equation_v1,
)

CALCODE_STATE_RHS_MAX_PARAMETERS_V1 = 64


class CalcodeStateRhsParameterV1:
    """typedef struct CalcodeStateRhsParameterV1 { ... } CalcodeStateRhsParameterV1."""
    __slots__ = ("name", "value")

    def __init__(self, name: str = "", value: float = 0.0):
        self.name = name
        self.value = value


class CalcodeStateRhsContextV1:
    """typedef struct CalcodeStateRhsContextV1 { ... } CalcodeStateRhsContextV1."""
    __slots__ = ("t", "state", "state_dimension", "parameters", "parameter_count")

    def __init__(self):
        self.t = 0.0
        self.state: Optional[Sequence[float]] = None
        self.state_dimension = 0
        self.parameters: List[CalcodeStateRhsParameterV1] = []
        self.parameter_count = 0


class CalcodeStateRhsV1:
    """typedef struct CalcodeStateRhsV1 { ... } CalcodeStateRhsV1."""
    __slots__ = (
        "valid", "dimension", "generator",
        "dependent_variable", "independent_variable", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.dimension = 0
        self.generator: Optional[CalcodeRhsGeneratorV1] = None
        self.dependent_variable = ""
        self.independent_variable = ""
        self.diagnostic = ""


def _diagnostic(rhs: Optional[CalcodeStateRhsV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(CalcodeStateRhsV1 *rhs, const char *message);"""
    if rhs is None:
        return
    text = message if message else "invalid state RHS"
    rhs.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_state_rhs_init_v1(rhs: Optional[CalcodeStateRhsV1]) -> None:
    """void calcode_state_rhs_init_v1(CalcodeStateRhsV1 *rhs);"""
    if rhs is None:
        return

    rhs.valid = 0
    rhs.dimension = 0
    rhs.generator = None
    rhs.dependent_variable = ""
    rhs.independent_variable = ""
    rhs.diagnostic = ""


def calcode_state_rhs_build_v1(
    rhs: Optional[CalcodeStateRhsV1],
    generator: Optional[CalcodeRhsGeneratorV1],
) -> int:
    """int calcode_state_rhs_build_v1(CalcodeStateRhsV1 *rhs,
    const CalcodeRhsGeneratorV1 *generator);"""
    if rhs is None or generator is None:
        return 0

    calcode_state_rhs_init_v1(rhs)

    if not generator.valid:
        _diagnostic(rhs, "RHS generator is invalid")
        return 0

    if generator.source_relation is None or generator.source_system is None:
        _diagnostic(rhs, "RHS generator has no symbolic source")
        return 0

    if generator.dimension <= 0:
        _diagnostic(rhs, "RHS dimension is zero")
        return 0

    rhs.generator = generator
    rhs.dimension = generator.dimension

    rhs.dependent_variable = generator.source_system.dependent_variable[
        : CALCODE_AST_MAX_NAME_V1 - 1
    ]
    rhs.independent_variable = generator.source_system.independent_variable[
        : CALCODE_AST_MAX_NAME_V1 - 1
    ]

    rhs.valid = 1
    rhs.diagnostic = ""

    return 1


def calcode_state_rhs_context_init_v1(context: Optional[CalcodeStateRhsContextV1]) -> None:
    """void calcode_state_rhs_context_init_v1(CalcodeStateRhsContextV1 *context);"""
    if context is None:
        return

    context.t = 0.0
    context.state = None
    context.state_dimension = 0
    context.parameters = []
    context.parameter_count = 0


def calcode_state_rhs_parameter_v1(
    context: Optional[CalcodeStateRhsContextV1], name: Optional[str], value: float
) -> int:
    """int calcode_state_rhs_parameter_v1(CalcodeStateRhsContextV1 *context,
    const char *name, double value);"""
    if context is None or not name:
        return 0

    for i in range(context.parameter_count):
        if context.parameters[i].name == name:
            context.parameters[i].value = value
            return 1

    if context.parameter_count >= CALCODE_STATE_RHS_MAX_PARAMETERS_V1:
        return 0

    truncated = name[: CALCODE_AST_MAX_NAME_V1 - 1]
    if len(context.parameters) <= context.parameter_count:
        context.parameters.append(CalcodeStateRhsParameterV1())
    context.parameters[context.parameter_count].name = truncated
    context.parameters[context.parameter_count].value = value
    context.parameter_count += 1

    return 1


def _bind_state_symbols(
    rhs: Optional[CalcodeStateRhsV1],
    context: Optional[CalcodeStateRhsContextV1],
    evaluator: CalcodeSymbolicEvaluatorV1,
) -> int:
    """static int bind_state_symbols_v1(const CalcodeStateRhsV1 *rhs,
    const CalcodeStateRhsContextV1 *context,
    CalcodeSymbolicEvaluatorV1 *evaluator);"""
    if rhs is None or context is None or evaluator is None:
        return 0

    if context.state_dimension <= 0 or context.state is None:
        return 0

    if not calcode_symbolic_evaluator_bind_v1(
        evaluator, rhs.independent_variable, context.t
    ):
        return 0

    if not calcode_symbolic_evaluator_bind_v1(
        evaluator, rhs.dependent_variable, context.state[0]
    ):
        return 0

    # State aliases are also supplied. These are useful for future explicit
    # equations involving y' and for generated canonical expressions.
    #
    # y_1 -> state[0]
    # y_2 -> state[1]
    # ...
    for i in range(context.state_dimension):
        alias = f"{rhs.dependent_variable}_{i + 1}"

        if not calcode_symbolic_evaluator_bind_v1(
            evaluator, alias, context.state[i]
        ):
            return 0

    for i in range(context.parameter_count):
        if not calcode_symbolic_evaluator_bind_v1(
            evaluator, context.parameters[i].name, context.parameters[i].value
        ):
            return 0

    return 1


def calcode_state_rhs_eval_v1(
    rhs: Optional[CalcodeStateRhsV1],
    context: Optional[CalcodeStateRhsContextV1],
    derivative: List[float],
) -> int:
    """int calcode_state_rhs_eval_v1(const CalcodeStateRhsV1 *rhs,
    const CalcodeStateRhsContextV1 *context, double *derivative);

    `derivative` is a caller-supplied, in-place mutated list standing
    in for the C's `double *derivative` out-parameter (of length at
    least `rhs.dimension`), matching the C byte-for-byte.
    """
    if rhs is None or context is None or derivative is None:
        return 0

    if not rhs.valid or rhs.generator is None or rhs.generator.source_relation is None:
        return 0

    if context.state_dimension != rhs.dimension:
        return 0

    if context.state is None:
        return 0

    for i in range(rhs.dimension):
        derivative[i] = 0.0

    # The first n-1 equations are pure kinematic shifts:
    #
    #     y_1' = y_2
    #     y_2' = y_3
    #     ...
    #
    # The final equation is the symbolic RHS:
    #
    #     y_n' = F(...)
    for i in range(rhs.dimension - 1):
        derivative[i] = context.state[i + 1]

    final_index = rhs.dimension - 1

    equation = calcode_rhs_generator_equation_v1(rhs.generator, final_index)

    if equation is None or equation.rhs_root < 0:
        return 0

    evaluator = CalcodeSymbolicEvaluatorV1()
    calcode_symbolic_evaluator_init_v1(evaluator)

    if not _bind_state_symbols(rhs, context, evaluator):
        return 0

    final_value = [0.0]

    if not calcode_symbolic_evaluator_eval_v1(
        evaluator,
        rhs.generator.source_relation.arena,
        equation.rhs_root,
        final_value,
    ):
        return 0

    derivative[final_index] = final_value[0]

    return 1
