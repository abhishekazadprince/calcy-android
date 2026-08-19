from __future__ import annotations

from typing import Dict, List, Tuple

from calcy.core.problem import (
    CalcodeProblem,
    calcode_problem_init,
    calcode_problem_set_rhs,
    calcode_problem_set_initial,
    calcode_problem_set_parameter,
    calcode_problem_set_domain,
    calcode_problem_set_solver,
    calcode_problem_to_experiment,
)
from calcy.core.model import CalcodeExperiment, calcode_experiment_solve


class CalcyController:
    """Thin Android-facing adapter around the existing Calcy numerical core."""

    def __init__(self) -> None:
        self.experiment = CalcodeExperiment()
        self.last_error = ""
        self.times: List[float] = []
        self.states: List[List[float]] = []
        self.name = ""

    @staticmethod
    def _parse_floats(text: str, expected: int | None = None) -> List[float]:
        if not text.strip():
            values: List[float] = []
        else:
            values = [float(x.strip()) for x in text.replace(";", ",").split(",") if x.strip()]
        if expected is not None and len(values) != expected:
            raise ValueError(f"Expected {expected} values, got {len(values)}")
        return values

    def solve(
        self,
        name: str,
        rhs_text: str,
        initial_text: str,
        parameter_text: str,
        x0: float,
        x1: float,
        h0: float = 0.01,
        tolerance: float = 1e-7,
    ) -> Dict[str, object]:
        """Solve a system entered as semicolon-separated RHS expressions.

        Example: ``y2; -k1*k1*y1`` with initials ``0,1`` and ``k1=1``.
        """
        try:
            rhs = [s.strip() for s in rhs_text.replace("\n", ";").split(";") if s.strip()]
            if not rhs:
                raise ValueError("Enter at least one RHS expression")
            initials = self._parse_floats(initial_text, len(rhs))
            parameters: Dict[str, float] = {}
            if parameter_text.strip():
                for item in parameter_text.replace(";", ",").split(","):
                    item = item.strip()
                    if not item:
                        continue
                    if "=" not in item:
                        raise ValueError("Parameters must look like k1=1, k2=2")
                    key, value = item.split("=", 1)
                    parameters[key.strip()] = float(value.strip())

            problem = CalcodeProblem()
            calcode_problem_init(problem, name or "Calcy Experiment", len(rhs), len(parameters))
            for i, expression in enumerate(rhs):
                if not calcode_problem_set_rhs(problem, i, expression):
                    raise ValueError(f"Invalid RHS for equation {i + 1}")
            for i, value in enumerate(initials):
                if not calcode_problem_set_initial(problem, i, value):
                    raise ValueError(f"Invalid initial value y{i + 1}")
            for i, value in enumerate(parameters.values()):
                if not calcode_problem_set_parameter(problem, i, value):
                    raise ValueError(f"Invalid parameter value k{i + 1}")
            if not calcode_problem_set_domain(problem, float(x0), float(x1)):
                raise ValueError("Require x1 > x0 and finite domain values")

            span = max(abs(float(x1) - float(x0)), 1e-9)
            safe_h0 = max(min(abs(float(h0)), span / 10.0), 1e-8)
            if not calcode_problem_set_solver(problem, safe_h0, max(float(tolerance), 1e-12), 1e-10, max(safe_h0 * 10.0, 1e-6), 1_000_000):
                raise ValueError("Invalid solver settings")

            experiment = CalcodeExperiment()
            if not calcode_problem_to_experiment(problem, experiment):
                raise ValueError(experiment.error or "Could not create experiment")
            if not calcode_experiment_solve(experiment):
                raise ValueError(experiment.error or "Numerical integration failed")

            sol = experiment.solution
            if not sol.ok or sol.npts < 2:
                raise ValueError("Solver returned fewer than two usable samples")

            self.experiment = experiment
            self.name = name or "Calcy Experiment"
            self.last_error = ""
            self.times = list(sol.x[: sol.npts])
            self.states = [list(sol.y[j][: sol.npts]) for j in range(sol.neqns)]
            return {
                "name": self.name,
                "npts": sol.npts,
                "neqns": sol.neqns,
                "times": self.times,
                "states": self.states,
                "parameters": parameters,
            }
        except Exception as exc:
            self.last_error = str(exc)
            self.times = []
            self.states = []
            raise


PRESETS: Dict[str, Dict[str, str]] = {
    "SHM": {
        "name": "Simple Harmonic Motion",
        "rhs": "y2; -k1*k1*y1",
        "initial": "0, 1",
        "parameters": "k1=1",
        "x0": "0",
        "x1": "20",
        "h0": "0.01",
        "tol": "1e-7",
    },
    "Pendulum": {
        "name": "Nonlinear Pendulum",
        "rhs": "y2; -k1*sin(y1)",
        "initial": "1.2, 0",
        "parameters": "k1=1",
        "x0": "0",
        "x1": "30",
        "h0": "0.005",
        "tol": "1e-7",
    },
    "Lorenz": {
        "name": "Lorenz System",
        "rhs": "k1*(y2-y1); y1*(k2-y3)-y2; y1*y2-k3*y3",
        "initial": "1, 1, 1",
        "parameters": "k1=10, k2=28, k3=2.6666666667",
        "x0": "0",
        "x1": "40",
        "h0": "0.002",
        "tol": "1e-7",
    },
    "Van der Pol": {
        "name": "Van der Pol",
        "rhs": "y2; k1*(1-y1*y1)*y2-y1",
        "initial": "2, 0",
        "parameters": "k1=2",
        "x0": "0",
        "x1": "20",
        "h0": "0.005",
        "tol": "1e-7",
    },
    "Damped SHM": {
        "name": "Damped Simple Harmonic Motion",
        "rhs": "y2; -k1*k1*y1-k2*y2",
        "initial": "1, 0",
        "parameters": "k1=1, k2=0.12",
        "x0": "0",
        "x1": "30",
        "h0": "0.01",
        "tol": "1e-7",
    },
    "Two Body": {
        "name": "Planar Two Body",
        "rhs": "y2; -k1*y1/(y1*y1+y3*y3)^1.5; y4; -k1*y3/(y1*y1+y3*y3)^1.5",
        "initial": "1, 0, 0, 1",
        "parameters": "k1=1",
        "x0": "0",
        "x1": "20",
        "h0": "0.001",
        "tol": "1e-7",
    },
    "Brusselator": {
        "name": "Brusselator Reaction System",
        "rhs": "k1+y1*y1*y2-(k2+1)*y1; k2*y1-y1*y1*y2",
        "initial": "1, 4.2665",
        "parameters": "k1=2, k2=8.533",
        "x0": "0",
        "x1": "30",
        "h0": "0.005",
        "tol": "1e-7",
    },
    "Ballistic": {
        "name": "Ballistics with Quadratic Drag",
        "rhs": "y2; -k1*sqrt(y2*y2+y4*y4)*y2; y4; -k2-k1*sqrt(y2*y2+y4*y4)*y4",
        "initial": "0, 20, 0, 20",
        "parameters": "k1=0.01, k2=9.81",
        "x0": "0",
        "x1": "5",
        "h0": "0.001",
        "tol": "1e-7",
    },
}
