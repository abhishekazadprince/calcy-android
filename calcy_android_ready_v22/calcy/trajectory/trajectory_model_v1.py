"""calcode_trajectory_model_v1.py -- exact Python port of
calcode_trajectory_model_v1.c / calcode_trajectory_model_v1.h.

Original: the shared trajectory data model that group-3/4/5 consumers
read from -- it copies a completed `CalcodeRk4ResultV1` (times/states)
into an independently-owned model, along with the equation metadata
(title, source text, variable names, derivative order, parameter
names/values) recovered from the `CalcodeStateRhsV1`'s generator ->
source_relation chain, plus a small free-form metadata key/value store.

PORT NOTES:

- `time`/`state` are the C's heap `double *` buffers (`malloc`'d,
  `state` row-major as `sample_count * state_dimension`). Reproduced
  here as plain Python lists (`state` kept flat, same row-major
  indexing) rather than nested lists, matching
  `calcode_trajectory_model_state_at_v1`'s pointer arithmetic exactly.
  `None` whenever the model is freshly init'd/freed or a build failed.
- `calcode_trajectory_model_from_result_v1` unconditionally calls
  free_v1 then init_v1 first (matching the C's unconditional reset
  before validation), then validates in this exact order:
  result/rhs/context non-None; `result.success` and
  `result.times`/`.states` non-None; `rhs.valid` and
  `rhs.dimension > 0`; `result.state_dimension == rhs.dimension`;
  `result.steps_completed >= 1`. Each failure sets a diagnostic and
  returns 0 -- reproduced with the same message text and order.
- The relation-derived fields (`source_equation`,
  `independent_variable`, `dependent_variable`, `derivative_order`,
  `parameter_names`) are only populated `if relation:` -- i.e. only
  when `rhs.generator` and `rhs.generator.source_relation` are both
  set, exactly like the C's `rhs->generator ?
  rhs->generator->source_relation : NULL` followed by an `if
  (relation)` guard. When there's no relation, those fields stay at
  their init_v1 defaults and `parameter_count` stays 0. Truncation
  uses the same `CALCODE_AST_MAX_NAME_V1 - 1` / `-1`-sized limits as
  the C's `strncpy` calls.
- Per the C's comment, `parameter_values[i]` is seeded to 0.0 from the
  relation loop (symbolic names only, no numeric value yet), then a
  second loop resolves the actual numeric value from `context`'s
  parameter array by name match -- reproduced as two separate passes
  in the same order, including the C's `if (context.parameter_count <
  m.parameter_count): m.parameter_count = context.parameter_count`
  clamp *before* the resolution loop (so if the context has fewer
  bound parameters than the relation named, the extra trailing
  relation-only parameter names/values are silently dropped from the
  model, not just left unresolved).
- `t0`/`t1` are read directly from `result.times[0]` and
  `result.times[steps_completed - 1]`. `dt_nominal` is only set `if
  result.steps_completed >= 2` -- with exactly one sample it stays at
  its init_v1 default (0.0), matching the C leaving that struct field
  memset-zeroed.
- On success the C ends by writing two fixed metadata entries
  (`"integrator" -> "RK4"`, `"representation" -> "shared trajectory"`)
  via the same `metadata_v1` upsert function used for user metadata,
  then clears `diagnostic`. Reproduced in the same order, after
  `valid = 1` is set (so a caller reading `model.valid` inside a
  metadata callback -- there isn't one in the real C, but for
  faithfulness -- would already see it set, exactly as in the C).
- `calcode_trajectory_model_metadata_v1` is an upsert keyed by exact
  name match: an existing entry's value is overwritten in place
  (truncated to `value[128]`'s C size); otherwise a new entry is
  appended if `metadata_count < CALCODE_TRAJECTORY_MAX_METADATA_V1`
  (32), else it fails (returns 0) -- reproduced exactly, including
  rejecting a `None`/empty `name` or a `None` `value`.
- `calcode_trajectory_model_state_at_v1` returns the row slice
  `state[sample_index * state_dimension : (sample_index + 1) *
  state_dimension]` (a fresh Python list, standing in for the C's
  `&state[...]` pointer-into-buffer -- read-only access is
  observably identical) after the same `valid`/`state is
  not None`/`0 <= sample_index < sample_count` guard the C performs;
  `None` (C's `NULL`) on any guard failure.
- `calcode_trajectory_model_sample_v1` requires `time`/`state` output
  args to be provided and `state_capacity >= state_dimension` (the
  C's `double *state` output buffer with a caller-declared capacity is
  modeled as a caller-supplied Python list of that capacity; only the
  first `state_dimension` entries are ever written, matching the C's
  `memcpy` of exactly `state_dimension` doubles) -- reproduced with
  the same guard order, including re-deriving the source row via
  `state_at_v1` (so its own guards apply a second time, matching the
  C calling the same helper internally).
"""

from __future__ import annotations

from typing import List, Optional

from calcy.symbolic.symbolic_ast_v1 import CALCODE_AST_MAX_NAME_V1
from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.symbolic.state_rhs_v1 import (
    CalcodeStateRhsV1,
    CalcodeStateRhsContextV1,
    CALCODE_STATE_RHS_MAX_PARAMETERS_V1,
)
from calcy.numerical.rk4_integrator_v1 import CalcodeRk4ResultV1

CALCODE_TRAJECTORY_TITLE_V1 = 128
CALCODE_TRAJECTORY_SOURCE_V1 = 512
CALCODE_TRAJECTORY_MAX_METADATA_V1 = 32


class CalcodeTrajectoryMetadataV1:
    """typedef struct CalcodeTrajectoryMetadataV1 { ... } CalcodeTrajectoryMetadataV1."""
    __slots__ = ("name", "value")

    def __init__(self, name: str = "", value: str = ""):
        self.name = name
        self.value = value


class CalcodeTrajectoryModelV1:
    """typedef struct CalcodeTrajectoryModelV1 { ... } CalcodeTrajectoryModelV1."""
    __slots__ = (
        "valid", "title", "source_equation",
        "independent_variable", "dependent_variable",
        "derivative_order", "state_dimension", "sample_count",
        "time", "state",
        "metadata", "metadata_count",
        "parameter_values", "parameter_names", "parameter_count",
        "t0", "t1", "dt_nominal", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.title = ""
        self.source_equation = ""
        self.independent_variable = ""
        self.dependent_variable = ""
        self.derivative_order = 0
        self.state_dimension = 0
        self.sample_count = 0
        self.time: Optional[List[float]] = None
        self.state: Optional[List[float]] = None
        self.metadata: List[CalcodeTrajectoryMetadataV1] = []
        self.metadata_count = 0
        self.parameter_values = [0.0] * CALCODE_STATE_RHS_MAX_PARAMETERS_V1
        self.parameter_names = [""] * CALCODE_STATE_RHS_MAX_PARAMETERS_V1
        self.parameter_count = 0
        self.t0 = 0.0
        self.t1 = 0.0
        self.dt_nominal = 0.0
        self.diagnostic = ""


def _diagnostic(m: Optional[CalcodeTrajectoryModelV1], message: Optional[str]) -> None:
    """static void diagnostic_v1(CalcodeTrajectoryModelV1 *m, const char *message);"""
    if m is None:
        return
    text = message if message else "trajectory model error"
    m.diagnostic = text[: CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_trajectory_model_init_v1(m: Optional[CalcodeTrajectoryModelV1]) -> None:
    """void calcode_trajectory_model_init_v1(CalcodeTrajectoryModelV1 *model);"""
    if m is None:
        return

    m.valid = 0
    m.title = ""
    m.source_equation = ""
    m.independent_variable = ""
    m.dependent_variable = ""
    m.derivative_order = 0
    m.state_dimension = 0
    m.sample_count = 0
    m.time = None
    m.state = None
    m.metadata = []
    m.metadata_count = 0
    m.parameter_values = [0.0] * CALCODE_STATE_RHS_MAX_PARAMETERS_V1
    m.parameter_names = [""] * CALCODE_STATE_RHS_MAX_PARAMETERS_V1
    m.parameter_count = 0
    m.t0 = 0.0
    m.t1 = 0.0
    m.dt_nominal = 0.0
    m.diagnostic = ""


def calcode_trajectory_model_free_v1(m: Optional[CalcodeTrajectoryModelV1]) -> None:
    """void calcode_trajectory_model_free_v1(CalcodeTrajectoryModelV1 *model);"""
    if m is None:
        return

    m.time = None
    m.state = None

    m.sample_count = 0
    m.state_dimension = 0
    m.valid = 0


def calcode_trajectory_model_set_title_v1(
    m: Optional[CalcodeTrajectoryModelV1], title: Optional[str]
) -> int:
    """int calcode_trajectory_model_set_title_v1(CalcodeTrajectoryModelV1 *model,
    const char *title);"""
    if m is None or title is None:
        return 0

    m.title = title[: CALCODE_TRAJECTORY_TITLE_V1 - 1]

    return 1


def calcode_trajectory_model_metadata_v1(
    m: Optional[CalcodeTrajectoryModelV1], name: Optional[str], value: Optional[str]
) -> int:
    """int calcode_trajectory_model_metadata_v1(CalcodeTrajectoryModelV1 *model,
    const char *name, const char *value);"""
    if m is None or not name or value is None:
        return 0

    for i in range(m.metadata_count):
        if m.metadata[i].name == name:
            m.metadata[i].value = value[: 128 - 1]
            return 1

    if m.metadata_count >= CALCODE_TRAJECTORY_MAX_METADATA_V1:
        return 0

    entry = CalcodeTrajectoryMetadataV1(
        name[: 64 - 1],
        value[: 128 - 1],
    )
    m.metadata.append(entry)
    m.metadata_count += 1

    return 1


def calcode_trajectory_model_from_result_v1(
    m: Optional[CalcodeTrajectoryModelV1],
    result: Optional[CalcodeRk4ResultV1],
    rhs: Optional[CalcodeStateRhsV1],
    context: Optional[CalcodeStateRhsContextV1],
) -> int:
    """int calcode_trajectory_model_from_result_v1(CalcodeTrajectoryModelV1 *model,
    const CalcodeRk4ResultV1 *result, const CalcodeStateRhsV1 *rhs,
    const CalcodeStateRhsContextV1 *context);"""
    if m is None or result is None or rhs is None or context is None:
        return 0

    calcode_trajectory_model_free_v1(m)
    calcode_trajectory_model_init_v1(m)

    if not result.success or result.times is None or result.states is None:
        _diagnostic(m, "RK4 result does not contain a stored trajectory")
        return 0

    if not rhs.valid or rhs.dimension <= 0:
        _diagnostic(m, "state RHS is invalid")
        return 0

    if result.state_dimension != rhs.dimension:
        _diagnostic(m, "trajectory and RHS dimensions differ")
        return 0

    if result.steps_completed < 1:
        _diagnostic(m, "trajectory contains no samples")
        return 0

    m.sample_count = result.steps_completed
    m.state_dimension = result.state_dimension

    # C: malloc failure path -- unreachable in Python (list allocation
    # doesn't fail the same way), so that branch is not modeled.

    m.time = list(result.times[: m.sample_count])
    m.state = list(result.states[: m.sample_count * m.state_dimension])

    relation = None
    if rhs.generator is not None:
        relation = rhs.generator.source_relation

    if relation is not None:
        m.source_equation = relation.source[: CALCODE_TRAJECTORY_SOURCE_V1 - 1]
        m.independent_variable = relation.independent_variable[
            : CALCODE_AST_MAX_NAME_V1 - 1
        ]
        m.dependent_variable = relation.dependent_variable[
            : CALCODE_AST_MAX_NAME_V1 - 1
        ]

        m.derivative_order = relation.derivative_order

        i = 0
        while i < relation.parameter_count and i < CALCODE_STATE_RHS_MAX_PARAMETERS_V1:
            m.parameter_names[i] = relation.parameters[i][: CALCODE_AST_MAX_NAME_V1 - 1]

            # The relation only stores symbolic parameter names. Their
            # numerical values are recovered from the runtime context.
            m.parameter_values[i] = 0.0

            i += 1

        m.parameter_count = relation.parameter_count

    if context.parameter_count < m.parameter_count:
        m.parameter_count = context.parameter_count

    for i in range(m.parameter_count):
        for j in range(context.parameter_count):
            if m.parameter_names[i] == context.parameters[j].name:
                m.parameter_values[i] = context.parameters[j].value
                break

    m.t0 = result.times[0]
    m.t1 = result.times[result.steps_completed - 1]

    if result.steps_completed >= 2:
        m.dt_nominal = result.times[1] - result.times[0]

    m.valid = 1

    calcode_trajectory_model_metadata_v1(m, "integrator", "RK4")
    calcode_trajectory_model_metadata_v1(m, "representation", "shared trajectory")

    m.diagnostic = ""

    return 1


def calcode_trajectory_model_state_at_v1(
    m: Optional[CalcodeTrajectoryModelV1], sample_index: int
) -> Optional[List[float]]:
    """const double *calcode_trajectory_model_state_at_v1(
    const CalcodeTrajectoryModelV1 *model, int sample_index);"""
    if (
        m is None
        or not m.valid
        or m.state is None
        or sample_index < 0
        or sample_index >= m.sample_count
    ):
        return None

    base = sample_index * m.state_dimension
    return m.state[base : base + m.state_dimension]


def calcode_trajectory_model_sample_v1(
    m: Optional[CalcodeTrajectoryModelV1],
    sample_index: int,
    time_out: Optional[List[float]],
    state_out: Optional[List[float]],
    state_capacity: int,
) -> int:
    """int calcode_trajectory_model_sample_v1(const CalcodeTrajectoryModelV1 *model,
    int sample_index, double *time, double *state, int state_capacity);

    `time_out` is modeled as a single-element list (out-param): on
    success `time_out[0]` is set to the sample's time, matching the
    C's `*time = ...`.
    """
    if m is None or not m.valid or m.time is None or m.state is None:
        return 0

    if sample_index < 0 or sample_index >= m.sample_count:
        return 0

    if time_out is None or state_out is None or state_capacity < m.state_dimension:
        return 0

    time_out[0] = m.time[sample_index]

    src = calcode_trajectory_model_state_at_v1(m, sample_index)

    if src is None:
        return 0

    for j in range(m.state_dimension):
        state_out[j] = src[j]

    return 1
