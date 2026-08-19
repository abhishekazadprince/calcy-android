"""calcode_standard_form_editor_v3.py -- exact Python port of
calcode_standard_form_editor_v3.c / calcode_standard_form_editor_v3.h.

Original: the editable "standard form" representation of the ODE
system as entered by the user -- a list of equations
(`y_i' = f_i(x, y1..yN, k1..kN)`) and parameters, plus a domain and
integrator-settings block, plus a small cursor/field-selection state
machine for a text-editor UI. This module is deliberately
solver-independent at the data-model level: `ODESys` (from
`odesys.py`) remains the sole authority for mathematical compilation;
this file only performs syntactic/identifier-level validation itself
and defers everything else to a probe compile.

PORT STATUS -- HARNESS-VERIFIED 2026-08-16 against a compiled C binary
built from the real `calcode_standard_form_editor_v3.c`/`.h` +
`odesys.c`/`.h` + `expr.c`/`.h` (all uploaded this session). See
`harness_standard_form_editor.c` / `harness_standard_form_editor.py`
in this package: both harnesses exercise every public entry point
(add/remove/set equation & parameter, domain/integrator setters with
good and bad inputs, validate() success and every distinct failure
branch, compile() success/failure, cursor state machine, add-at-
capacity). `c_output_standard_form_editor.txt` and
`py_output_standard_form_editor.txt` diff to zero (the only line-level
difference was `(nil)` vs `None` in the C harness's own printf
formatting of a null pointer, not a behavioral difference in the
ported code).

PORT NOTES:

- Fixed-size C arrays (`equations[CALCODE_STD_MAX_EQNS]`,
  `parameters[CALCODE_STD_MAX_PARAMS]`) become Python lists
  pre-allocated to the same fixed length in `__init__`/`_reset`, so
  that `renumber_equations_v3`/`renumber_parameters_v3` -- which the
  C walks over the *entire* fixed-size array, not just the active
  prefix -- can be ported with the identical full-array loop rather
  than silently narrowing it to `equation_count`.
- `calcode_standard_form_add_equation_v3`/`..._add_parameter_v3`
  return the C `int i` (the new index) on success and C `0` on
  failure. Note the same latent ambiguity as the C itself: index `0`
  (the very first equation/parameter successfully added) is
  indistinguishable from a failure return by call sites that only
  check truthiness -- reproduced as-is, not "fixed", since fixing it
  would change the public return-value contract.
- `calcode_standard_form_validate_v3`'s ODESys probe-compile: the C
  calls `odesys_compile(...)` returning `NULL` + an `errbuf`; the
  Python `odesys_compile` instead raises `ODESysError` (see
  `odesys.py`'s own port notes). This port catches that exception and
  formats the identical `"ODE compiler: %s"` message from
  `str(exception)`, preserving the C's user-visible error text.
- `char *`/`const char *` return values that can be C `NULL` (no
  underlying storage) become Python `None`.
- Every public entry point begins with the same NULL/guard-clause
  pattern as the C (`if (!m) return 0;`, etc.), translated to
  `if m is None: return 0`.
- `unsigned long long revision` fields have no natural overflow limit
  in this port (Python ints are unbounded) -- the C's 64-bit wraparound
  behavior is not reproduced since no code path in this file or its
  callers relies on wraparound; this mirrors how `calcode_clock.py`
  and other already-ported files treat wide integer counters.
"""

from __future__ import annotations

from typing import List, Optional

from calcy.core.odesys import ODESys, ODESysError, odesys_compile, odesys_free

CALCODE_STD_MAX_EQNS = 16    # ODESYS_MAX_EQNS
CALCODE_STD_MAX_PARAMS = 16  # ODESYS_MAX_PARAMS
CALCODE_STD_RHS_LEN = 256
CALCODE_STD_NAME_LEN = 64
CALCODE_STD_ERROR_LEN = 512


class CalcodeStandardFormFieldV3:
    """enum CalcodeStandardFormFieldV3"""
    CALCODE_STD_FIELD_NONE_V3 = 0
    CALCODE_STD_FIELD_RHS_V3 = 1
    CALCODE_STD_FIELD_INITIAL_V3 = 2
    CALCODE_STD_FIELD_PARAMETER_V3 = 3
    CALCODE_STD_FIELD_X0_V3 = 4
    CALCODE_STD_FIELD_XEND_V3 = 5
    CALCODE_STD_FIELD_H0_V3 = 6
    CALCODE_STD_FIELD_TOLERANCE_V3 = 7


def _truncate(s: str, capacity: int) -> str:
    """Mirrors snprintf(dst, capacity, "%s", src) truncation to
    capacity-1 chars + NUL (capacity itself never stored as data)."""
    if capacity <= 0:
        return ""
    return s[: capacity - 1]


class CalcodeStandardEquationV3:
    """typedef struct CalcodeStandardEquationV3 { ... }"""
    __slots__ = ("active", "name", "rhs", "initial_value", "equation_number", "error")

    def __init__(self):
        self.active = 0
        self.name = ""
        self.rhs = ""
        self.initial_value = 0.0
        self.equation_number = 0
        self.error = ""


class CalcodeStandardParameterV3:
    """typedef struct CalcodeStandardParameterV3 { ... }"""
    __slots__ = ("active", "name", "value", "parameter_number")

    def __init__(self):
        self.active = 0
        self.name = ""
        self.value = 0.0
        self.parameter_number = 0


class CalcodeStandardFormModelV3:
    """typedef struct CalcodeStandardFormModelV3 { ... }"""
    __slots__ = (
        "valid", "equation_count", "parameter_count",
        "equations", "parameters",
        "x0", "x_end", "h0", "tolerance", "h_min", "h_max", "max_steps",
        "revision", "validated_revision",
        "validation_ok", "validation_error",
    )

    def __init__(self):
        self.valid = 0
        self.equation_count = 0
        self.parameter_count = 0
        self.equations: List[CalcodeStandardEquationV3] = [
            CalcodeStandardEquationV3() for _ in range(CALCODE_STD_MAX_EQNS)
        ]
        self.parameters: List[CalcodeStandardParameterV3] = [
            CalcodeStandardParameterV3() for _ in range(CALCODE_STD_MAX_PARAMS)
        ]
        self.x0 = 0.0
        self.x_end = 0.0
        self.h0 = 0.0
        self.tolerance = 0.0
        self.h_min = 0.0
        self.h_max = 0.0
        self.max_steps = 0
        self.revision = 0
        self.validated_revision = 0
        self.validation_ok = 0
        self.validation_error = ""


class CalcodeStandardFormCursorV3:
    """typedef struct CalcodeStandardFormCursorV3 { ... }"""
    __slots__ = ("equation", "parameter", "field", "character", "editing")

    def __init__(self):
        self.equation = 0
        self.parameter = 0
        self.field = 0
        self.character = 0
        self.editing = 0


def _mark_changed_v3(m: CalcodeStandardFormModelV3) -> None:
    """static void mark_changed_v3(CalcodeStandardFormModelV3 *m);"""
    if m is None:
        return
    m.revision += 1
    m.validation_ok = 0
    m.validated_revision = 0
    m.validation_error = ""


def _renumber_equations_v3(m: CalcodeStandardFormModelV3) -> None:
    """static void renumber_equations_v3(CalcodeStandardFormModelV3 *m);"""
    for i in range(CALCODE_STD_MAX_EQNS):
        if i < m.equation_count:
            m.equations[i].active = 1
            m.equations[i].equation_number = i + 1
        else:
            m.equations[i].active = 0
            m.equations[i].equation_number = 0


def _renumber_parameters_v3(m: CalcodeStandardFormModelV3) -> None:
    """static void renumber_parameters_v3(CalcodeStandardFormModelV3 *m);"""
    for i in range(CALCODE_STD_MAX_PARAMS):
        if i < m.parameter_count:
            m.parameters[i].active = 1
            m.parameters[i].parameter_number = i + 1
        else:
            m.parameters[i].active = 0
            m.parameters[i].parameter_number = 0


def calcode_standard_form_model_init_v3(m: Optional[CalcodeStandardFormModelV3]) -> None:
    """void calcode_standard_form_model_init_v3(CalcodeStandardFormModelV3 *model);"""
    if m is None:
        return

    # memset(m, 0, sizeof(*m));
    m.valid = 0
    m.equation_count = 0
    m.parameter_count = 0
    m.equations = [CalcodeStandardEquationV3() for _ in range(CALCODE_STD_MAX_EQNS)]
    m.parameters = [CalcodeStandardParameterV3() for _ in range(CALCODE_STD_MAX_PARAMS)]
    m.x0 = 0.0
    m.x_end = 0.0
    m.h0 = 0.0
    m.tolerance = 0.0
    m.h_min = 0.0
    m.h_max = 0.0
    m.max_steps = 0
    m.revision = 0
    m.validated_revision = 0
    m.validation_ok = 0
    m.validation_error = ""

    m.x0 = 0.0
    m.x_end = 10.0

    m.h0 = 0.01
    m.tolerance = 1e-7
    m.h_min = 1e-10
    m.h_max = 0.1
    m.max_steps = 100000

    m.revision = 1

    _renumber_equations_v3(m)
    _renumber_parameters_v3(m)

    m.valid = 1


def calcode_standard_form_add_equation_v3(
    m: Optional[CalcodeStandardFormModelV3],
    name: Optional[str],
    rhs: Optional[str],
    initial_value: float,
) -> int:
    """int calcode_standard_form_add_equation_v3(...);"""
    if m is None or not m.valid or m.equation_count >= CALCODE_STD_MAX_EQNS:
        return 0

    i = m.equation_count
    eq = m.equations[i]

    # memset(eq, 0, sizeof(*eq));
    eq.active = 0
    eq.name = ""
    eq.rhs = ""
    eq.initial_value = 0.0
    eq.equation_number = 0
    eq.error = ""

    eq.active = 1

    eq.name = _truncate((name if (name and name[0:1]) else "y"), CALCODE_STD_NAME_LEN)
    eq.rhs = _truncate((rhs if rhs is not None else "0"), CALCODE_STD_RHS_LEN)

    eq.initial_value = initial_value

    m.equation_count += 1

    _renumber_equations_v3(m)
    _mark_changed_v3(m)

    return i


def calcode_standard_form_remove_equation_v3(
    m: Optional[CalcodeStandardFormModelV3],
    equation_index: int,
) -> int:
    """int calcode_standard_form_remove_equation_v3(...);"""
    if (m is None or not m.valid or equation_index < 0
            or equation_index >= m.equation_count):
        return 0

    for i in range(equation_index, m.equation_count - 1):
        m.equations[i] = m.equations[i + 1]

    m.equations[m.equation_count - 1] = CalcodeStandardEquationV3()

    m.equation_count -= 1

    _renumber_equations_v3(m)
    _mark_changed_v3(m)

    return 1


def calcode_standard_form_set_equation_v3(
    m: Optional[CalcodeStandardFormModelV3],
    equation_index: int,
    name: Optional[str],
    rhs: Optional[str],
    initial_value: float,
) -> int:
    """int calcode_standard_form_set_equation_v3(...);"""
    if (m is None or not m.valid or equation_index < 0
            or equation_index >= m.equation_count):
        return 0

    eq = m.equations[equation_index]

    if name is not None:
        eq.name = _truncate(name, CALCODE_STD_NAME_LEN)

    if rhs is not None:
        eq.rhs = _truncate(rhs, CALCODE_STD_RHS_LEN)

    eq.initial_value = initial_value

    _mark_changed_v3(m)

    return 1


def calcode_standard_form_add_parameter_v3(
    m: Optional[CalcodeStandardFormModelV3],
    name: Optional[str],
    value: float,
) -> int:
    """int calcode_standard_form_add_parameter_v3(...);"""
    if m is None or not m.valid or m.parameter_count >= CALCODE_STD_MAX_PARAMS:
        return 0

    i = m.parameter_count
    p = m.parameters[i]

    # memset(p, 0, sizeof(*p));
    p.active = 0
    p.name = ""
    p.value = 0.0
    p.parameter_number = 0

    p.active = 1

    p.name = _truncate((name if (name and name[0:1]) else "k"), CALCODE_STD_NAME_LEN)

    p.value = value

    m.parameter_count += 1

    _renumber_parameters_v3(m)
    _mark_changed_v3(m)

    return i


def calcode_standard_form_remove_parameter_v3(
    m: Optional[CalcodeStandardFormModelV3],
    parameter_index: int,
) -> int:
    """int calcode_standard_form_remove_parameter_v3(...);"""
    if (m is None or not m.valid or parameter_index < 0
            or parameter_index >= m.parameter_count):
        return 0

    for i in range(parameter_index, m.parameter_count - 1):
        m.parameters[i] = m.parameters[i + 1]

    m.parameters[m.parameter_count - 1] = CalcodeStandardParameterV3()

    m.parameter_count -= 1

    _renumber_parameters_v3(m)
    _mark_changed_v3(m)

    return 1


def calcode_standard_form_set_parameter_v3(
    m: Optional[CalcodeStandardFormModelV3],
    parameter_index: int,
    name: Optional[str],
    value: float,
) -> int:
    """int calcode_standard_form_set_parameter_v3(...);"""
    if (m is None or not m.valid or parameter_index < 0
            or parameter_index >= m.parameter_count):
        return 0

    p = m.parameters[parameter_index]

    if name is not None:
        p.name = _truncate(name, CALCODE_STD_NAME_LEN)

    p.value = value

    _mark_changed_v3(m)

    return 1


def calcode_standard_form_set_domain_v3(
    m: Optional[CalcodeStandardFormModelV3],
    x0: float,
    x_end: float,
) -> int:
    """int calcode_standard_form_set_domain_v3(...);"""
    if m is None or not m.valid or not (x_end > x0):
        return 0

    m.x0 = x0
    m.x_end = x_end

    _mark_changed_v3(m)

    return 1


def calcode_standard_form_set_integrator_v3(
    m: Optional[CalcodeStandardFormModelV3],
    h0: float,
    tolerance: float,
    h_min: float,
    h_max: float,
    max_steps: int,
) -> int:
    """int calcode_standard_form_set_integrator_v3(...);"""
    if (m is None or not m.valid or not (h0 > 0.0) or not (tolerance > 0.0)
            or not (h_min > 0.0) or not (h_max >= h_min) or max_steps <= 0):
        return 0

    m.h0 = h0
    m.tolerance = tolerance
    m.h_min = h_min
    m.h_max = h_max
    m.max_steps = max_steps

    _mark_changed_v3(m)

    return 1


def _valid_identifier_v3(s: Optional[str]) -> int:
    """static int valid_identifier_v3(const char *s);"""
    if not s:
        return 0

    c0 = s[0]
    if not (c0.isalpha() and c0.isascii() or c0 == "_"):
        return 0

    for c in s[1:]:
        if not ((c.isalnum() and c.isascii()) or c == "_"):
            return 0

    return 1


def _duplicate_equation_name_v3(m: CalcodeStandardFormModelV3, index: int) -> int:
    """static int duplicate_equation_name_v3(...);"""
    for j in range(index):
        if m.equations[j].name == m.equations[index].name:
            return 1
    return 0


def _duplicate_parameter_name_v3(m: CalcodeStandardFormModelV3, index: int) -> int:
    """static int duplicate_parameter_name_v3(...);"""
    for j in range(index):
        if m.parameters[j].name == m.parameters[index].name:
            return 1
    return 0


def _blank_v3(s: Optional[str]) -> int:
    """static int blank_v3(const char *s);"""
    if s is None:
        return 1
    for c in s:
        if not c.isspace():
            return 0
    return 1


def calcode_standard_form_validate_v3(m: Optional[CalcodeStandardFormModelV3]) -> int:
    """int calcode_standard_form_validate_v3(CalcodeStandardFormModelV3 *model);"""
    if m is None or not m.valid:
        return 0

    m.validation_ok = 0
    m.validation_error = ""

    if m.equation_count <= 0:
        m.validation_error = "standard form contains no equations"
        return 0

    if m.equation_count > CALCODE_STD_MAX_EQNS:
        m.validation_error = "equation count exceeds ODESys limit"
        return 0

    if m.parameter_count > CALCODE_STD_MAX_PARAMS:
        m.validation_error = "parameter count exceeds ODESys limit"
        return 0

    if not (m.x_end > m.x0):
        m.validation_error = "domain requires xEnd > x0"
        return 0

    for i in range(m.equation_count):
        eq = m.equations[i]

        if not _valid_identifier_v3(eq.name):
            m.validation_error = _truncate(
                f"equation {i + 1} has invalid variable name '{eq.name}'",
                CALCODE_STD_ERROR_LEN)
            return 0

        if _duplicate_equation_name_v3(m, i):
            m.validation_error = _truncate(
                f"duplicate equation variable '{eq.name}'", CALCODE_STD_ERROR_LEN)
            return 0

        if _blank_v3(eq.rhs):
            m.validation_error = f"equation {i + 1} has an empty RHS"
            return 0

    for i in range(m.parameter_count):
        p = m.parameters[i]

        if not _valid_identifier_v3(p.name):
            m.validation_error = _truncate(
                f"parameter {i + 1} has invalid name '{p.name}'", CALCODE_STD_ERROR_LEN)
            return 0

        if _duplicate_parameter_name_v3(m, i):
            m.validation_error = _truncate(
                f"duplicate parameter name '{p.name}'", CALCODE_STD_ERROR_LEN)
            return 0

    # ODESys is the authoritative parser/compiler. We perform a
    # compile-only validation here instead of implementing a second
    # expression grammar that could disagree with the real solver.
    rhs_list = [m.equations[i].rhs for i in range(m.equation_count)]

    try:
        probe = odesys_compile(rhs_list, m.equation_count, m.parameter_count)
    except ODESysError as compile_error:
        m.validation_error = _truncate(f"ODE compiler: {compile_error}", CALCODE_STD_ERROR_LEN)
        return 0

    odesys_free(probe)

    m.validation_ok = 1
    m.validated_revision = m.revision

    return 1


def calcode_standard_form_compile_v3(
    m: Optional[CalcodeStandardFormModelV3],
):
    """int calcode_standard_form_compile_v3(const CalcodeStandardFormModelV3 *model,
        ODESys **out_system, char *error, size_t error_capacity);

    Python signature: returns (ok: int, out_system: Optional[ODESys], error: str)
    in place of the C's (out_system, error) out-params, since Python has
    no pointer out-params. Callers should unpack all three, mirroring the
    C call site's `*out_system` / `error` reads after the call.
    """
    out_system: Optional[ODESys] = None
    error = ""

    if m is None or not m.valid:
        return 0, out_system, error

    rhs_list = [m.equations[i].rhs for i in range(m.equation_count)]

    try:
        out_system = odesys_compile(rhs_list, m.equation_count, m.parameter_count)
    except ODESysError as e:
        out_system = None
        error = str(e)
        return 0, out_system, error

    return 1, out_system, error


def calcode_standard_form_equation_text_v3(
    m: Optional[CalcodeStandardFormModelV3],
    equation_index: int,
) -> Optional[str]:
    """const char *calcode_standard_form_equation_text_v3(...);"""
    if m is None or equation_index < 0 or equation_index >= m.equation_count:
        return None
    return m.equations[equation_index].rhs


def calcode_standard_form_parameter_name_v3(
    m: Optional[CalcodeStandardFormModelV3],
    parameter_index: int,
) -> Optional[str]:
    """const char *calcode_standard_form_parameter_name_v3(...);"""
    if m is None or parameter_index < 0 or parameter_index >= m.parameter_count:
        return None
    return m.parameters[parameter_index].name


def calcode_standard_form_cursor_init_v3(cursor: Optional[CalcodeStandardFormCursorV3]) -> None:
    """void calcode_standard_form_cursor_init_v3(CalcodeStandardFormCursorV3 *cursor);"""
    if cursor is None:
        return

    # memset(cursor, 0, sizeof(*cursor));
    cursor.equation = 0
    cursor.parameter = 0
    cursor.field = 0
    cursor.character = 0
    cursor.editing = 0

    cursor.equation = 0
    cursor.parameter = 0
    cursor.field = CalcodeStandardFormFieldV3.CALCODE_STD_FIELD_RHS_V3


def calcode_standard_form_cursor_select_equation_v3(
    cursor: Optional[CalcodeStandardFormCursorV3],
    m: Optional[CalcodeStandardFormModelV3],
    equation_index: int,
) -> int:
    """int calcode_standard_form_cursor_select_equation_v3(...);"""
    if (cursor is None or m is None or equation_index < 0
            or equation_index >= m.equation_count):
        return 0

    cursor.equation = equation_index
    cursor.field = CalcodeStandardFormFieldV3.CALCODE_STD_FIELD_RHS_V3
    cursor.character = 0

    return 1


def calcode_standard_form_cursor_select_parameter_v3(
    cursor: Optional[CalcodeStandardFormCursorV3],
    m: Optional[CalcodeStandardFormModelV3],
    parameter_index: int,
) -> int:
    """int calcode_standard_form_cursor_select_parameter_v3(...);"""
    if (cursor is None or m is None or parameter_index < 0
            or parameter_index >= m.parameter_count):
        return 0

    cursor.parameter = parameter_index
    cursor.field = CalcodeStandardFormFieldV3.CALCODE_STD_FIELD_PARAMETER_V3
    cursor.character = 0

    return 1


def calcode_standard_form_cursor_begin_edit_v3(
    cursor: Optional[CalcodeStandardFormCursorV3],
    field: int,
) -> int:
    """int calcode_standard_form_cursor_begin_edit_v3(...);"""
    if cursor is None or field == CalcodeStandardFormFieldV3.CALCODE_STD_FIELD_NONE_V3:
        return 0

    cursor.field = field
    cursor.editing = 1
    cursor.character = 0

    return 1


def calcode_standard_form_cursor_end_edit_v3(cursor: Optional[CalcodeStandardFormCursorV3]) -> int:
    """int calcode_standard_form_cursor_end_edit_v3(CalcodeStandardFormCursorV3 *cursor);"""
    if cursor is None:
        return 0

    cursor.editing = 0

    return 1
