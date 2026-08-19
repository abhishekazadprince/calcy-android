"""custom_equation_bridge_v1.py -- NEW INTEGRATION CODE, NOT a C port.

Same symbolic-spine chain that `standard_form_symbolic_bridge_v1.py` drives
from an edited `CalcodeStandardFormModelV3`, exposed here directly from a
single raw equation string instead -- so a caller (e.g. an interactive CLI)
can accept "y'' = -k1*k1*y" typed by a user without first constructing the
companion-form editor equations by hand.

Reuses `symbolic_relation_v1.calcode_symbolic_relation_analyze_v1`'s own
apostrophe-derivative notation (see `symbolic_parser_v1._parse_power`),
so the accepted syntax is exactly: a single dependent variable name,
followed by that many `'` characters for the derivative order, `=`, and
an expression using that variable, `t`, and any named parameters.

Same structural limit as the standard-form bridge: only a single
higher-order ODE reducible to first-order companion form is representable
here (see that module's docstring) -- NOT a genuinely coupled
multi-equation system.

STATUS: not harness-verified against any C source (none exists to verify
against, same as standard_form_symbolic_bridge_v1.py) -- verified instead
by exercising the same underlying chain already cross-validated in
integration_test_symbolic.py.
"""

from __future__ import annotations

from typing import Dict, List, Optional

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


def calcode_trajectory_model_from_source_v1(
    model_out: Optional[CalcodeTrajectoryModelV1],
    source: str,
    t0: float,
    t1: float,
    initial_state: List[float],
    parameters: Optional[Dict[str, float]],
    steps: int,
) -> int:
    """Solve a single raw ODE relation string end to end through the
    symbolic AST spine and populate `model_out`.

    `initial_state` must have one entry per companion-form state
    component (i.e. `derivative_order` entries: y(t0), y'(t0), ...).
    `parameters` maps parameter name -> value for every named parameter
    that appears in `source` besides the dependent variable and `t`.

    Returns 0 (with `model_out.diagnostic` set) on any failure along the
    chain, same int-return convention as every builder in this package.
    """
    if model_out is None or not source:
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

    if len(initial_state) != state_rhs.dimension:
        model_out.diagnostic = (
            f"initial_state has {len(initial_state)} components, "
            f"equation needs {state_rhs.dimension} "
            f"(derivative order {relation.derivative_order})"
        )
        return 0

    dt = (t1 - t0) / (steps - 1) if steps > 1 else 0.0

    integrator = CalcodeRk4IntegratorV1()
    config = CalcodeRk4ConfigV1(t0=t0, t1=t1, dt=dt, steps=steps, store_trajectory=1)
    if not calcode_rk4_integrator_configure_v1(integrator, state_rhs, config):
        model_out.diagnostic = f"RK4 configure failed: {integrator.diagnostic}"
        return 0

    context = CalcodeStateRhsContextV1()
    calcode_state_rhs_context_init_v1(context)
    context.state = list(initial_state)
    context.state_dimension = state_rhs.dimension

    for name, value in (parameters or {}).items():
        calcode_state_rhs_parameter_v1(context, name, value)

    result = CalcodeRk4ResultV1()
    if not calcode_rk4_integrate_v1(integrator, context, result):
        model_out.diagnostic = f"RK4 integration failed: {integrator.diagnostic}"
        return 0

    if not calcode_trajectory_model_from_result_v1(model_out, result, state_rhs, context):
        return 0  # model_out.diagnostic already set by from_result_v1

    return 1
