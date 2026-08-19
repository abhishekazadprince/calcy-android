"""calcode_examples.py -- exact Python port of calcode_examples.c / .h.

Original: canonical reference experiments. These are not special solver
implementations -- they are merely presets that feed the same generic
CalcodeProblem / CalcodeExperiment pipeline.

PORT NOTES:

- **Known latent bug, preserved on purpose**: `calcode_example_two_body`'s
  RHS expressions call `pow(...)` as a two-argument function
  (`pow(y1*y1+y3*y3, 1.5)`), but expr.py's parser (a faithful port of
  expr.c) only recognizes `min`/`max` as two-argument functions --
  exponentiation is done via the `^` operator, not a `pow()` call. This
  preset therefore fails to compile (`calcode_problem_to_experiment` then
  `calcode_experiment_compile` will report an unknown-identifier/function
  error for `pow`) exactly as it does in the original C. This is a bug
  already present in the source being ported, not something introduced
  here, so it is reproduced rather than silently fixed.
"""

from __future__ import annotations

from typing import Optional

from calcy.core.problem import (
    CalcodeProblem,
    calcode_problem_init,
    calcode_problem_set_domain,
    calcode_problem_set_initial,
    calcode_problem_set_parameter,
    calcode_problem_set_rhs,
    calcode_problem_set_solver,
)


def _clear_problem(p: CalcodeProblem) -> None:
    """static void clear_problem(CalcodeProblem *p): memset(p, 0, ...).
    Every caller below immediately follows this with calcode_problem_init,
    which fully re-initializes every field anyway -- kept only for
    line-for-line parity with the C control flow."""
    p.format_version = 0
    p.notes = ""
    p.revision = 0


def calcode_example_shm(p: Optional[CalcodeProblem]) -> int:
    """int calcode_example_shm(CalcodeProblem *p);"""
    if p is None:
        return 0

    _clear_problem(p)
    calcode_problem_init(p, "Simple Harmonic Motion", 2, 1)

    calcode_problem_set_rhs(p, 0, "y2")
    calcode_problem_set_rhs(p, 1, "-k1*k1*y1")

    calcode_problem_set_initial(p, 0, 0.0)
    calcode_problem_set_initial(p, 1, 1.0)

    calcode_problem_set_parameter(p, 0, 1.0)
    calcode_problem_set_domain(p, 0.0, 20.0)

    calcode_problem_set_solver(p, 0.01, 1e-7, 1e-8, 0.1, 1000000)

    return 1


def calcode_example_damped_shm(p: Optional[CalcodeProblem]) -> int:
    """int calcode_example_damped_shm(CalcodeProblem *p);"""
    if p is None:
        return 0

    _clear_problem(p)
    calcode_problem_init(p, "Damped Simple Harmonic Motion", 2, 2)

    calcode_problem_set_rhs(p, 0, "y2")
    calcode_problem_set_rhs(p, 1, "-k1*k1*y1-k2*y2")

    calcode_problem_set_initial(p, 0, 1.0)
    calcode_problem_set_initial(p, 1, 0.0)

    calcode_problem_set_parameter(p, 0, 1.0)
    calcode_problem_set_parameter(p, 1, 0.12)

    calcode_problem_set_domain(p, 0.0, 30.0)

    calcode_problem_set_solver(p, 0.01, 1e-7, 1e-8, 0.1, 1000000)

    return 1


def calcode_example_pendulum(p: Optional[CalcodeProblem]) -> int:
    """int calcode_example_pendulum(CalcodeProblem *p);"""
    if p is None:
        return 0

    _clear_problem(p)
    calcode_problem_init(p, "Nonlinear Simple Pendulum", 2, 1)

    # theta' = omega
    # omega' = -(g/L) sin(theta)
    # k1 = g/L
    calcode_problem_set_rhs(p, 0, "y2")
    calcode_problem_set_rhs(p, 1, "-k1*sin(y1)")

    calcode_problem_set_initial(p, 0, 1.2)
    calcode_problem_set_initial(p, 1, 0.0)

    calcode_problem_set_parameter(p, 0, 1.0)
    calcode_problem_set_domain(p, 0.0, 30.0)

    calcode_problem_set_solver(p, 0.005, 1e-7, 1e-8, 0.05, 1000000)

    return 1


def calcode_example_vanderpol(p: Optional[CalcodeProblem]) -> int:
    """int calcode_example_vanderpol(CalcodeProblem *p);"""
    if p is None:
        return 0

    _clear_problem(p)
    calcode_problem_init(p, "Van der Pol", 2, 1)

    calcode_problem_set_rhs(p, 0, "y2")
    calcode_problem_set_rhs(p, 1, "k1*(1-y1*y1)*y2-y1")

    calcode_problem_set_initial(p, 0, 2.0)
    calcode_problem_set_initial(p, 1, 0.0)

    calcode_problem_set_parameter(p, 0, 2.0)
    calcode_problem_set_domain(p, 0.0, 40.0)

    calcode_problem_set_solver(p, 0.005, 1e-7, 1e-8, 0.05, 1000000)

    return 1


def calcode_example_lorenz(p: Optional[CalcodeProblem]) -> int:
    """int calcode_example_lorenz(CalcodeProblem *p);"""
    if p is None:
        return 0

    _clear_problem(p)
    calcode_problem_init(p, "Lorenz", 3, 3)

    calcode_problem_set_rhs(p, 0, "k1*(y2-y1)")
    calcode_problem_set_rhs(p, 1, "y1*(k2-y3)-y2")
    calcode_problem_set_rhs(p, 2, "y1*y2-k3*y3")

    calcode_problem_set_initial(p, 0, 1.0)
    calcode_problem_set_initial(p, 1, 1.0)
    calcode_problem_set_initial(p, 2, 1.0)

    calcode_problem_set_parameter(p, 0, 10.0)
    calcode_problem_set_parameter(p, 1, 28.0)
    calcode_problem_set_parameter(p, 2, 8.0 / 3.0)

    calcode_problem_set_domain(p, 0.0, 40.0)

    calcode_problem_set_solver(p, 0.002, 1e-7, 1e-8, 0.03, 1000000)

    return 1


def calcode_example_brusselator(p: Optional[CalcodeProblem]) -> int:
    """int calcode_example_brusselator(CalcodeProblem *p);"""
    if p is None:
        return 0

    _clear_problem(p)
    calcode_problem_init(p, "Brusselator", 2, 2)

    calcode_problem_set_rhs(p, 0, "k1+y1*y1*y2-(k2+1)*y1")
    calcode_problem_set_rhs(p, 1, "k2*y1-y1*y1*y2")

    calcode_problem_set_initial(p, 0, 1.0)
    calcode_problem_set_initial(p, 1, 4.2665)

    calcode_problem_set_parameter(p, 0, 2.0)
    calcode_problem_set_parameter(p, 1, 8.533)

    calcode_problem_set_domain(p, 0.0, 30.0)

    calcode_problem_set_solver(p, 0.005, 1e-7, 1e-8, 0.05, 1000000)

    return 1


def calcode_example_ballistics(p: Optional[CalcodeProblem]) -> int:
    """int calcode_example_ballistics(CalcodeProblem *p);"""
    if p is None:
        return 0

    _clear_problem(p)
    calcode_problem_init(p, "Ballistics with Quadratic Drag", 4, 3)

    # State:
    #   y1 = x, y2 = vx, y3 = y, y4 = vy
    # Parameters:
    #   k1 = drag coefficient / mass, k2 = gravity
    #   k3 = launch-related scaling if desired by the model
    # This preset uses k1 and k2; k3 is deliberately available for later
    # parameter studies and UI experiments.
    calcode_problem_set_rhs(p, 0, "y2")
    calcode_problem_set_rhs(p, 1, "-k1*sqrt(y2*y2+y4*y4)*y2")
    calcode_problem_set_rhs(p, 2, "y4")
    calcode_problem_set_rhs(p, 3, "-k2-k1*sqrt(y2*y2+y4*y4)*y4")

    calcode_problem_set_initial(p, 0, 0.0)
    calcode_problem_set_initial(p, 1, 20.0)
    calcode_problem_set_initial(p, 2, 0.0)
    calcode_problem_set_initial(p, 3, 20.0)

    calcode_problem_set_parameter(p, 0, 0.01)
    calcode_problem_set_parameter(p, 1, 9.81)
    calcode_problem_set_parameter(p, 2, 1.0)

    calcode_problem_set_domain(p, 0.0, 5.0)

    calcode_problem_set_solver(p, 0.001, 1e-7, 1e-8, 0.02, 1000000)

    return 1


def calcode_example_two_body(p: Optional[CalcodeProblem]) -> int:
    """int calcode_example_two_body(CalcodeProblem *p);

    The inverse-cube acceleration is expressed with the generic power
    operator supported by the symbolic parser.
    """
    if p is None:
        return 0

    _clear_problem(p)
    calcode_problem_init(p, "Planar Two Body", 4, 1)

    # State:
    #   y1 = x, y2 = vx, y3 = y, y4 = vy
    # Dimensionless gravitational parameter k1.
    calcode_problem_set_rhs(p, 0, "y2")
    calcode_problem_set_rhs(p, 1, "-k1*y1/((y1*y1+y3*y3)^1.5)")
    calcode_problem_set_rhs(p, 2, "y4")
    calcode_problem_set_rhs(p, 3, "-k1*y3/((y1*y1+y3*y3)^1.5)")

    calcode_problem_set_initial(p, 0, 1.0)
    calcode_problem_set_initial(p, 1, 0.0)
    calcode_problem_set_initial(p, 2, 0.0)
    calcode_problem_set_initial(p, 3, 1.0)

    calcode_problem_set_parameter(p, 0, 1.0)

    calcode_problem_set_domain(p, 0.0, 20.0)

    calcode_problem_set_solver(p, 0.001, 1e-7, 1e-8, 0.02, 1000000)

    return 1
