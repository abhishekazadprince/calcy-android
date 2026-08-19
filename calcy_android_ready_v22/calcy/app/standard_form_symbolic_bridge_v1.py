"""standard_form_symbolic_bridge.py -- NEW INTEGRATION CODE, NOT a C port.

Closes the second gap from the architecture review: connects
`app/standard_form_editor_v3.py` (where the user edits equations) to the
symbolic AST pipeline (`symbolic/` -> `numerical/rk4_integrator_v1.py` ->
`trajectory/trajectory_model_v1.py`), which previously had no producer
feeding it from any editor at all.

IMPORTANT STRUCTURAL LIMIT (found by reading the real code, not assumed):

`symbolic_relation_v1.calcode_symbolic_relation_analyze_v1` parses exactly
ONE equation with exactly ONE '=' and determines a single dependent
variable + derivative order from its left-hand side (see
`_find_dependent_derivative`). `first_order_system_v1` then expands that
one relation into a companion-form state vector

    x0 = y, x1 = y', ..., x(n-1) = y^(n-1)

This means the symbolic spine can only represent a SINGLE higher-order
ODE reduced to first-order form -- it has no way to represent a genuinely
coupled multi-equation system where more than one equation carries real
(non-shift) dynamics.

`standard_form_editor_v3`'s presets split into exactly these two buckets:

  REDUCIBLE (single order-n ODE in companion form -- this bridge handles
  them): SHM, damped SHM, pendulum, Van der Pol, Duffing.

  NOT REDUCIBLE (genuinely coupled systems -- structurally out of scope
  for the symbolic spine as currently ported, not a gap this bridge can
  close): Lorenz, Brusselator, the two-body problem, ballistics (2 real
  second-order equations, not 1).

`calcode_symbolic_source_from_standard_form_v1` detects which bucket a
given model falls into and returns None for the second bucket rather than
guessing -- see its docstring.

STATUS: not harness-verified against any C source, because there is none
to verify against (this bridge doesn't exist in the original C app as far
as this port set shows). Cross-checked instead by running both spines
(legacy odesys/expr vs this symbolic path) on the SAME preset and
diffing the resulting trajectories -- see integration_test.py.
"""

from __future__ import annotations

import re
from typing import List, Optional

from calcy.app.standard_form_editor_v3 import CalcodeStandardFormModelV3

from calcy.symbolic.symbolic_relation_v1 import (
    CalcodeSymbolicRelationV1,
    calcode_symbolic_relation_analyze_v1,
)
from calcy.symbolic.first_order_system_v1 import (
    CalcodeFirstOrderSystemV1,
    calcode_first_order_system_build_v1,
)
from calcy.symbolic.rhs_generator_v1 import (
    CalcodeRhsGeneratorV1,
    calcode_rhs_generator_build_v1,
)
from calcy.symbolic.state_rhs_v1 import (
    CalcodeStateRhsV1,
    CalcodeStateRhsContextV1,
    calcode_state_rhs_build_v1,
    calcode_state_rhs_context_init_v1,
    calcode_state_rhs_parameter_v1,
)
from calcy.numerical.rk4_integrator_v1 import (
    CalcodeRk4ConfigV1,
    CalcodeRk4IntegratorV1,
    CalcodeRk4ResultV1,
    calcode_rk4_integrator_configure_v1,
    calcode_rk4_integrate_v1,
)
from calcy.trajectory.trajectory_model_v1 import (
    CalcodeTrajectoryModelV1,
    calcode_trajectory_model_from_result_v1,
)

_Y_TOKEN = re.compile(r"\by(\d+)\b")
_X_TOKEN = re.compile(r"\bx\b")


def calcode_symbolic_source_from_standard_form_v1(
    m: Optional[CalcodeStandardFormModelV3],
) -> Optional[str]:
    """Return a CALCODE symbolic-relation source string ("y''...' = <rhs>")
    equivalent to `m`, or None if `m` isn't in companion form.

    Detection: every equation except the last must be a pure shift
    (`y{i}' rhs == "y{i+1}"` exactly, matching what `odesys_compile`'s
    generic `y1..yN` naming produces for a companion-form system). Only
    the last equation may carry real dynamics.
    """
    if m is None or not m.valid or m.equation_count < 1:
        return None

    n = m.equation_count

    for i in range(n - 1):
        expected = f"y{i + 2}"
        if m.equations[i].rhs.strip() != expected:
            return None  # genuinely coupled -- not representable here

    final_rhs = m.equations[n - 1].rhs

    # Editor convention (odesys/expr): x independent, y1..yN state,
    # k1..kN parameters. Symbolic spine convention: t independent
    # (hardcoded, see symbolic_relation_v1.py), y/y_1/y_2../y_N state
    # aliases (see state_rhs_v1._bind_state_symbols), kN unchanged.
    text = _Y_TOKEN.sub(lambda mo: f"y_{mo.group(1)}", final_rhs)
    text = _X_TOKEN.sub("t", text)

    lhs = "y" + ("'" * n)
    return f"{lhs} = {text}"


def calcode_trajectory_model_from_standard_form_v1(
    model_out: Optional[CalcodeTrajectoryModelV1],
    editor_model: Optional[CalcodeStandardFormModelV3],
    initial_state: Optional[List[float]],
    parameter_values: Optional[List[float]],
    dt: float,
    steps: int,
) -> int:
    """Solve a companion-form standard_form_editor_v3 model through the
    symbolic AST spine end to end and populate `model_out`.

    Returns 0 (with `model_out.diagnostic` set) if `editor_model` isn't
    in companion form, or on any failure along the chain -- same
    int-return convention as every builder in this package.
    """
    if model_out is None or editor_model is None:
        return 0

    source = calcode_symbolic_source_from_standard_form_v1(editor_model)
    if source is None:
        model_out.diagnostic = (
            "model is not a single reducible higher-order ODE "
            "(coupled multi-equation systems aren't representable "
            "by the symbolic spine -- see module docstring)"
        )
        return 0

    relation = CalcodeSymbolicRelationV1()
    if not calcode_symbolic_relation_analyze_v1(relation, source):
        model_out.diagnostic = f"symbolic relation analyze failed: {relation.diagnostic}"
        return 0

    system = CalcodeFirstOrderSystemV1()
    if not calcode_first_order_system_build_v1(system, relation):
        model_out.diagnostic = f"first-order system build failed: {system.diagnostic}"
        return 0

    generator = CalcodeRhsGeneratorV1()
    if not calcode_rhs_generator_build_v1(generator, relation, system):
        model_out.diagnostic = f"RHS generator build failed: {generator.diagnostic}"
        return 0

    state_rhs = CalcodeStateRhsV1()
    if not calcode_state_rhs_build_v1(state_rhs, generator):
        model_out.diagnostic = f"state RHS build failed: {state_rhs.diagnostic}"
        return 0

    integrator = CalcodeRk4IntegratorV1()
    config = CalcodeRk4ConfigV1(
        t0=editor_model.x0, t1=editor_model.x_end, dt=dt, steps=steps,
        store_trajectory=1,
    )
    if not calcode_rk4_integrator_configure_v1(integrator, state_rhs, config):
        model_out.diagnostic = f"RK4 configure failed: {integrator.diagnostic}"
        return 0

    context = CalcodeStateRhsContextV1()
    calcode_state_rhs_context_init_v1(context)
    context.state = list(initial_state) if initial_state else []
    context.state_dimension = state_rhs.dimension

    for i in range(editor_model.parameter_count):
        name = editor_model.parameters[i].name
        value = parameter_values[i] if parameter_values and i < len(parameter_values) else 0.0
        calcode_state_rhs_parameter_v1(context, name, value)

    result = CalcodeRk4ResultV1()
    if not calcode_rk4_integrate_v1(integrator, context, result):
        model_out.diagnostic = f"RK4 integration failed: {integrator.diagnostic}"
        return 0

    if not calcode_trajectory_model_from_result_v1(model_out, result, state_rhs, context):
        return 0  # model_out.diagnostic already set by from_result_v1

    return 1
