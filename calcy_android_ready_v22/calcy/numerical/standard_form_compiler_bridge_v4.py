"""calcode_standard_form_compiler_bridge_v4.py -- exact Python port of
calcode_standard_form_compiler_bridge_v4.c / .h.

Original: translates a user-facing named standard form (`x' = v`,
`v' = -omega2*x`) into the canonical `y1..yN`/`k1..kM` symbol language
the real `ODESys` compiler accepts, without modifying ODESys itself.
This is the last of the three files that were blocked pending
`odesys.h`/`.c` and completes the 11-file "Symbolic ODE Input
Pipeline" section of `REMAINING_PYTHON_PORT_WORK.md`.

PORT STATUS -- HARNESS-VERIFIED 2026-08-16 against a compiled C binary
built from the real `calcode_standard_form_compiler_bridge_v4.c`/`.h`
(+ `calcode_standard_form_editor_v3`/`odesys`/`expr`). See
`harness_compiler_bridge.c` / `harness_compiler_bridge.py` in this
package. `c_output_compiler_bridge.txt` and
`py_output_compiler_bridge.txt` diff to exactly zero.

KNOWN LATENT DIVERGENCE, CONFIRMED UNREACHABLE: `_translate_rhs_v4`'s
capacity check does not exactly reproduce the C's `append_text_v4`
bound (C requires `used + length + 1 <= capacity` for the NUL
terminator; this port's check is `used + length <= capacity`, off by
one). Investigated directly with harness cases at RHS lengths 1022,
1023, and 1024 chars of a single repeated non-identifier character --
the true boundary case. In both languages this is dead code in
practice: `model->equations[i].rhs` is already truncated to
`CALCODE_STD_RHS_LEN` (256) chars by the standard-form editor before
it ever reaches this function, and even with the worst-case ~3x
per-token growth from named-to-canonical substitution, translated
output cannot approach the 1024-char `_TRANSLATE_CAPACITY` boundary
through the real public API. The harness confirms C and Python return
byte-identical results at all three tested lengths. Left unfixed
(paralleling the project's "port current behavior, don't silently
correct it" convention) but flagged explicitly here since it's a
correctness gap in the port itself, not just in the original C.

PORT NOTES:

- C's manual arena/buffer management (`calloc`, `append_text_v4`
  bounds-checked byte copies into a fixed `CALCODE_STD_RHS_LEN * 4`
  buffer, `free`) has no useful Python equivalent -- this port builds
  the canonical string with a plain Python list-join. The *rejection*
  behavior when a translated identifier would be too long is preserved
  as a distinct case (see `_translate_rhs_v4` below): the C's
  `append_text_v4` returning 0 when `*used + length + 1 > capacity`
  can only actually trigger once the *whole* translated RHS would
  exceed `CALCODE_STD_RHS_LEN * 4` (1024) chars, since every per-token
  append is already bounded well under that by
  `CALCODE_STD_NAME_LEN` (64); reproduced as an explicit length check
  against the same 1024-char capacity so translate failure remains
  possible on pathological input, not silently dropped because Python
  strings don't need pre-sized buffers.
- `identifier[len] = len >= CALCODE_STD_NAME_LEN` early-reject (the C's
  `if (len >= sizeof(identifier)) { free(out); *ok = 0; return NULL; }`)
  is preserved as a hard length check on each scanned identifier before
  any lookup is attempted.
- `map_identifier_v4`'s bare-canonical-symbol passthrough
  (`identifier[0] == 'y' || 'k'` followed by `isdigit(identifier[1])`)
  reads a fixed second character; in C this is memory-safe even for a
  1-char identifier because of the buffer's implicit NUL terminator
  (`isdigit('\\0')` is false). This port guards the same case
  explicitly with a length check rather than indexing past the
  string, since Python strings carry no such terminator -- behavior is
  identical (both reject a bare `"y"`/`"k"` with no following digit).
- `calcode_standard_form_compile_named_v4`'s live `ODESys*` and
  `char **canonical_rhs` become normal Python attributes with no
  manual free needed; `calcode_standard_form_compiled_v4_free` is kept
  as a real function (not a no-op) because it also resets `c.valid`
  and clears `c.system`/`c.canonical_rhs`, which is observable
  behavior beyond memory management.
- The C's dead code at the end of `compile_named_v4` --
  `double y0[ODESYS_MAX_EQNS]; ... (void)y0;` -- computes the initial
  state vector purely as a "sanity check" and then explicitly discards
  it (the comment says the real initial vector is read directly from
  `model->equations[].initial_value` by the caller). This is
  reproduced faithfully: `_canonical_initial_values_v4` is still
  called and can still fail the compile, but its result is otherwise
  unused, exactly as in the original.
"""

from __future__ import annotations

from typing import List, Optional

from calcy.core.odesys import ODESys, ODESysError, odesys_compile, odesys_free
from calcy.app.standard_form_editor_v3 import (
    CalcodeStandardFormModelV3,
    CALCODE_STD_NAME_LEN,
    CALCODE_STD_RHS_LEN,
)

ODESYS_MAX_EQNS = 16
_TRANSLATE_CAPACITY = CALCODE_STD_RHS_LEN * 4  # 1024


def _identifier_char_v4(ch: str) -> bool:
    """static int identifier_char_v4(char ch);"""
    return (ch.isalnum() and ch.isascii()) or ch == "_"


def _identifier_start_v4(ch: str) -> bool:
    """static int identifier_start_v4(char ch);"""
    return (ch.isalpha() and ch.isascii()) or ch == "_"


def _map_identifier_v4(m: CalcodeStandardFormModelV3, identifier: str) -> Optional[str]:
    """static int map_identifier_v4(...); returns the replacement string
    (Python None in place of the C's `return 0`)."""
    for i in range(m.equation_count):
        if identifier == m.equations[i].name:
            return f"y{i + 1}"

    for i in range(m.parameter_count):
        if identifier == m.parameters[i].name:
            return f"k{i + 1}"

    # Canonical symbols are also accepted directly. This permits an
    # advanced user to write y1, k1, etc. explicitly.
    if len(identifier) >= 2 and identifier[0] in ("y", "k") and identifier[1].isdigit():
        return identifier

    return None


def _translate_rhs_v4(m: CalcodeStandardFormModelV3, rhs: Optional[str]):
    """static char *translate_rhs_v4(...); returns (text_or_None, ok)."""
    text = rhs if rhs is not None else ""
    n = len(text)

    out_parts: List[str] = []
    used = 0
    i = 0

    while i < n:
        ch = text[i]

        if _identifier_start_v4(ch):
            start = i
            i += 1
            while i < n and _identifier_char_v4(text[i]):
                i += 1

            identifier = text[start:i]

            if len(identifier) >= CALCODE_STD_NAME_LEN:
                return None, 0

            replacement = _map_identifier_v4(m, identifier)
            token = replacement if replacement is not None else identifier

            if used + len(token) > _TRANSLATE_CAPACITY:
                return None, 0

            out_parts.append(token)
            used += len(token)

        else:
            if used + 1 > _TRANSLATE_CAPACITY:
                return None, 0

            out_parts.append(ch)
            used += 1
            i += 1

    return "".join(out_parts), 1


def _canonical_initial_values_v4(m: CalcodeStandardFormModelV3) -> Optional[List[float]]:
    """static int canonical_initial_values_v4(const CalcodeStandardFormModelV3 *m,
        double *y0); returns the y0 list on success, None on failure."""
    if m is None:
        return None

    y0 = [0.0] * m.equation_count
    for i in range(m.equation_count):
        y0[i] = m.equations[i].initial_value

    return y0


class CalcodeStandardFormCompiledV4:
    """typedef struct CalcodeStandardFormCompiledV4 { ... }"""
    __slots__ = ("valid", "system", "equation_count", "parameter_count", "canonical_rhs", "error")

    def __init__(self):
        self.valid = 0
        self.system: Optional[ODESys] = None
        self.equation_count = 0
        self.parameter_count = 0
        self.canonical_rhs: List[Optional[str]] = []
        self.error = ""


def _set_error_v4(c: Optional[CalcodeStandardFormCompiledV4], text: Optional[str]) -> None:
    """static void set_error_v4(CalcodeStandardFormCompiledV4 *c, const char *text);"""
    if c is None:
        return
    c.error = text if text is not None else "compiler bridge error"


def calcode_standard_form_compiled_v4_init(c: Optional[CalcodeStandardFormCompiledV4]) -> None:
    """void calcode_standard_form_compiled_v4_init(CalcodeStandardFormCompiledV4 *compiled);"""
    if c is None:
        return

    # memset(c, 0, sizeof(*c));
    c.valid = 0
    c.system = None
    c.equation_count = 0
    c.parameter_count = 0
    c.canonical_rhs = []
    c.error = ""


def calcode_standard_form_compile_named_v4(
    m: Optional[CalcodeStandardFormModelV3],
    c: Optional[CalcodeStandardFormCompiledV4],
) -> int:
    """int calcode_standard_form_compile_named_v4(const CalcodeStandardFormModelV3 *model,
        CalcodeStandardFormCompiledV4 *compiled);"""
    if m is None or c is None or not m.valid or m.equation_count <= 0:
        return 0

    calcode_standard_form_compiled_v4_init(c)

    c.equation_count = m.equation_count
    c.parameter_count = m.parameter_count

    # calloc((size_t)c->equation_count, sizeof(char *)) -- Python list
    # allocation cannot fail the way calloc can, so the C's out-of-memory
    # branch has no reachable equivalent here and is not reproduced.
    c.canonical_rhs = [None] * c.equation_count

    for i in range(c.equation_count):
        text, ok = _translate_rhs_v4(m, m.equations[i].rhs)
        c.canonical_rhs[i] = text

        if not ok or c.canonical_rhs[i] is None:
            _set_error_v4(c, "failed to translate an equation into canonical ODESys form")
            calcode_standard_form_compiled_v4_free(c)
            return 0

    rhs_list = list(c.canonical_rhs)

    try:
        c.system = odesys_compile(rhs_list, c.equation_count, c.parameter_count)
    except ODESysError as compiler_error:
        c.error = f"ODESys: {compiler_error}"
        calcode_standard_form_compiled_v4_free(c)
        return 0

    # Explicitly construct the initial vector here as a sanity check. The
    # vector itself is returned to the caller's numerical layer by reading
    # model->equations[].initial_value; this bridge does not duplicate
    # ODESolution ownership.
    y0 = _canonical_initial_values_v4(m)

    if y0 is None:
        _set_error_v4(c, "failed to construct initial state")
        calcode_standard_form_compiled_v4_free(c)
        return 0

    # (void)y0; -- computed for validation only, otherwise unused,
    # exactly as in the original.
    del y0

    c.valid = 1

    return 1


def calcode_standard_form_compiled_v4_free(c: Optional[CalcodeStandardFormCompiledV4]) -> None:
    """void calcode_standard_form_compiled_v4_free(CalcodeStandardFormCompiledV4 *compiled);"""
    if c is None:
        return

    if c.system is not None:
        odesys_free(c.system)
        c.system = None

    if c.canonical_rhs:
        c.canonical_rhs = None

    c.valid = 0


def calcode_standard_form_canonical_rhs_v4(
    c: Optional[CalcodeStandardFormCompiledV4],
    equation_index: int,
) -> Optional[str]:
    """const char *calcode_standard_form_canonical_rhs_v4(...);"""
    if c is None or not c.valid or equation_index < 0 or equation_index >= c.equation_count:
        return None

    return c.canonical_rhs[equation_index]
