"""calcode_ode_definition_v1.py -- exact Python port of
calcode_ode_definition_v1.c / calcode_ode_definition_v1.h.

Original: a text-format loader for the generic CALCODE ODE pipeline
("title = ...", "domain = a,b", "integrator = h0,tol,hmin,hmax,steps",
"param name = value", "state name = rhs | initial") plus four built-in
presets (SHM, Lorenz, Van der Pol, Duffing) that populate a
`CalcodeStandardFormModelV3` directly without going through the text
format at all.

PORT STATUS -- HARNESS-VERIFIED 2026-08-16 against a compiled C binary
built from the real `calcode_ode_definition_v1.c`/`.h` (+ the full
`calcode_standard_form_editor_v3`/`odesys`/`expr` chain beneath it).
See `harness_ode_definition.c` / `harness_ode_definition.py` in this
package: both harnesses exercise `load_v1` against real temp files
covering every parse branch (missing file, null args, a full valid
multi-line definition with comments/blank lines, missing '=', bad
domain with/without comma, bad integrator field count and bad
max_steps, bad param, blank state RHS, bad state initial value,
unknown key, no usable states) and `preset_v1` for all four presets
plus unknown-name and null-name. `c_output_ode_definition.txt` and
`py_output_ode_definition.txt` diff to exactly zero -- true bit-exact
match, including the preserved `< 0` never-true bug in the add-state/
add-param failure checks and the title-stashed-in-validation_error
quirk.

PORT NOTES -- PRESERVED HISTORICAL C BEHAVIOR (bugs included, not fixed):

- `calcode_ode_definition_load_v1`'s `parse_state_v1` and
  `parse_param_v1` check
  `calcode_standard_form_add_equation_v3(...) < 0` /
  `calcode_standard_form_add_parameter_v3(...) < 0` as their failure
  condition. But `calcode_standard_form_add_equation_v3`/
  `..._add_parameter_v3` (see `calcode_standard_form_editor_v3.py`)
  only ever return a non-negative index `i >= 0` on success or the
  literal `0` on failure -- **never a negative value**. So this
  `< 0` check can never be true, and a failed add (e.g. the model
  already being at `CALCODE_STD_MAX_EQNS`) silently falls through as
  if it had succeeded, rather than raising the "cannot add state"/
  "cannot add parameter" error the code appears to intend. This is a
  genuine latent bug in the original C, reproduced exactly here
  (`< 0`, not `== 0` or `<= 0`) per the project's stated goal of
  porting current behavior faithfully, not silently correcting it.
- The `title = ...` key has nowhere to go: `CalcodeStandardFormModelV3`
  (v3) has no title field, so the C stashes the title text directly
  into `model->validation_error` as a temporary holding place (with a
  comment acknowledging this), rather than storing it properly. That
  quirk is reproduced verbatim, not redirected to a "real" title
  attribute that doesn't exist on this struct.
- `fopen(path, "rb")` + `fgets` is reproduced as reading the file in
  text mode line-by-line; Python's universal-newline text mode gives
  equivalent line splitting for this line-oriented key/value format.
- Every `set_error_v1`/`snprintf(error, ...)` call is reproduced as
  setting a Python `error_box[0]` string (see the module-level note
  below on the out-param convention used for `char *error`).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from calcy.app.standard_form_editor_v3 import (
    CalcodeStandardFormModelV3,
    CALCODE_STD_MAX_EQNS,
    calcode_standard_form_model_init_v3,
    calcode_standard_form_add_equation_v3,
    calcode_standard_form_add_parameter_v3,
    calcode_standard_form_set_domain_v3,
    calcode_standard_form_set_integrator_v3,
)

CALCODE_ODE_TITLE_LEN_V1 = 128
CALCODE_ODE_PATH_LEN_V1 = 512

# NOTE ON OUT-PARAM CONVENTION: the C `char *error, size_t error_capacity`
# out-param pair is represented here as a single-element list
# `error_box = [""]`, mutated in place exactly like `x`/`y` mutable-box
# params in the already-ported `odesys.py`/`expr.py`. Callers should read
# `error_box[0]` after the call, mirroring the C call site reading `error`
# after the function returns. `error_capacity` itself has no Python
# equivalent effect (no fixed-size buffer to truncate into) and is not
# reproduced as a truncation limit here, matching how other already-ported
# files (e.g. `calcode_clock.py`) drop fixed-buffer-capacity truncation
# once there's no real buffer to overflow.


def _set_error_v1(error_box: Optional[List[str]], text: Optional[str]) -> None:
    """static void set_error_v1(char *error, size_t cap, const char *text);"""
    if error_box is None:
        return
    error_box[0] = text if text is not None else "ODE definition error"


def _trim_v1(s: str) -> str:
    """static char *trim_v1(char *s); -- strips leading/trailing whitespace."""
    return s.strip()


def _parse_double_v1(s: Optional[str]) -> Tuple[int, float]:
    """static int parse_double_v1(const char *s, double *out);
    Returns (ok, value)."""
    if s is None:
        return 0, 0.0
    # strtod-equivalent: parse the longest valid prefix, then require the
    # remainder (after trimming trailing whitespace) to be empty.
    stripped = s.strip()
    if stripped == "":
        return 0, 0.0
    try:
        # Python's float() already requires the *whole* trimmed string to
        # be a valid float (equivalent to strtod + trailing-whitespace-only
        # remainder), so this matches parse_double_v1's "no trailing junk"
        # requirement.
        v = float(stripped)
    except (ValueError, OverflowError):
        return 0, 0.0
    return 1, v


def _parse_domain_v1(m: CalcodeStandardFormModelV3, value: str) -> int:
    """static int parse_domain_v1(CalcodeStandardFormModelV3 *m, char *value);"""
    if "," not in value:
        return 0
    left, right = value.split(",", 1)
    ok_a, a = _parse_double_v1(_trim_v1(left))
    ok_b, b = _parse_double_v1(_trim_v1(right))
    if not ok_a or not ok_b:
        return 0
    return calcode_standard_form_set_domain_v3(m, a, b)


def _parse_integrator_v1(m: CalcodeStandardFormModelV3, value: str) -> int:
    """static int parse_integrator_v1(CalcodeStandardFormModelV3 *m, char *value);"""
    parts = value.split(",", 4)
    if len(parts) != 5:
        return 0

    ok0, h0 = _parse_double_v1(_trim_v1(parts[0]))
    ok1, tol = _parse_double_v1(_trim_v1(parts[1]))
    ok2, hmin = _parse_double_v1(_trim_v1(parts[2]))
    ok3, hmax = _parse_double_v1(_trim_v1(parts[3]))
    if not (ok0 and ok1 and ok2 and ok3):
        return 0

    last = _trim_v1(parts[4])
    try:
        # strtol(..., 10): base-10 integer parse, no trailing junk allowed
        # (matching the C's `*trim_v1(end) != '\0'` check).
        max_steps = int(last, 10)
    except ValueError:
        return 0

    return calcode_standard_form_set_integrator_v3(m, h0, tol, hmin, hmax, max_steps)


def _parse_named_value_v1(value: str) -> Tuple[int, str, str]:
    """static int parse_named_value_v1(char *value, char **name, char **rhs);
    Returns (ok, name, rhs). Not directly called by load_v1 in the
    original (state/param parsing route through key/value split earlier),
    kept for structural parity with the real C source."""
    if "=" not in value:
        return 0, "", ""
    left, right = value.split("=", 1)
    name = _trim_v1(left)
    rhs = _trim_v1(right)
    return (1 if (name != "" and rhs != "") else 0), name, rhs


def _parse_state_v1(
    m: CalcodeStandardFormModelV3,
    name: Optional[str],
    value: str,
    error_box: Optional[List[str]],
    line: int,
) -> int:
    """static int parse_state_v1(...);"""
    initial = 0.0

    if not name or value is None or value == "":
        if error_box is not None:
            error_box[0] = f"line {line}: state requires name = rhs"
        return 0

    if "|" in value:
        before, after = value.split("|", 1)
        ok, initial = _parse_double_v1(_trim_v1(after))
        if not ok:
            if error_box is not None:
                error_box[0] = f"line {line}: invalid state initial value"
            return 0
        value = before

    value = _trim_v1(value)

    # PRESERVED BUG: add_equation_v3 never returns < 0 (see module
    # docstring) -- this check can never trigger on a real failure.
    if value == "" or calcode_standard_form_add_equation_v3(m, name, value, initial) < 0:
        if error_box is not None:
            error_box[0] = f"line {line}: cannot add state '{name}'"
        return 0

    return 1


def _parse_param_v1(
    m: CalcodeStandardFormModelV3,
    name: Optional[str],
    value: Optional[str],
    error_box: Optional[List[str]],
    line: int,
) -> int:
    """static int parse_param_v1(...);"""
    ok, v = _parse_double_v1(_trim_v1(value)) if value is not None else (0, 0.0)

    if not name or value is None or not ok:
        if error_box is not None:
            error_box[0] = f"line {line}: parameter requires name = number"
        return 0

    # PRESERVED BUG: same never-negative return as parse_state_v1 above.
    if calcode_standard_form_add_parameter_v3(m, name, v) < 0:
        if error_box is not None:
            error_box[0] = f"line {line}: cannot add parameter '{name}'"
        return 0

    return 1


def calcode_ode_definition_load_v1(
    model: Optional[CalcodeStandardFormModelV3],
    path: Optional[str],
    error_box: Optional[List[str]] = None,
) -> int:
    """int calcode_ode_definition_load_v1(CalcodeStandardFormModelV3 *model,
        const char *path, char *error, size_t error_capacity);"""
    line_no = 0

    if model is None or path is None:
        _set_error_v1(error_box, "missing model or definition path")
        return 0

    try:
        fp = open(path, "r")
    except OSError:
        if error_box is not None:
            error_box[0] = f"cannot open ODE definition: {path}"
        return 0

    calcode_standard_form_model_init_v3(model)

    try:
        for raw_line in fp:
            line_no += 1
            line = _trim_v1(raw_line)
            if line == "" or line[0] == "#":
                continue

            # Strip a trailing comment, but leave '#' inside a future
            # string syntax alone; current definition syntax has no
            # quoted strings.
            if "#" in line:
                line = _trim_v1(line.split("#", 1)[0])
            if line == "":
                continue

            if "=" not in line:
                if error_box is not None:
                    error_box[0] = f"line {line_no}: expected key = value"
                return 0

            key_part, value_part = line.split("=", 1)
            key = _trim_v1(key_part)
            value = _trim_v1(value_part)

            if key == "title":
                # Title is stored later by the experiment; keep the text
                # in validation_error temporarily because the v3 model
                # has no title field.
                model.validation_error = value

            elif key == "domain":
                if not _parse_domain_v1(model, value):
                    if error_box is not None:
                        error_box[0] = f"line {line_no}: invalid domain"
                    return 0

            elif key == "integrator":
                if not _parse_integrator_v1(model, value):
                    if error_box is not None:
                        error_box[0] = f"line {line_no}: invalid integrator settings"
                    return 0

            elif key.startswith("param "):
                if not _parse_param_v1(model, _trim_v1(key[6:]), value, error_box, line_no):
                    return 0

            elif key.startswith("state "):
                if not _parse_state_v1(model, _trim_v1(key[6:]), value, error_box, line_no):
                    return 0

            else:
                if error_box is not None:
                    error_box[0] = f"line {line_no}: unknown key '{key}'"
                return 0
    finally:
        fp.close()

    if not model.valid:
        model.valid = 1

    if model.equation_count <= 0 or model.equation_count > CALCODE_STD_MAX_EQNS:
        _set_error_v1(error_box, "ODE definition has no usable states")
        return 0

    if not (model.x_end > model.x0):
        _set_error_v1(error_box, "ODE definition requires x_end > x0")
        return 0

    return 1


def _preset_shm_v1(m: CalcodeStandardFormModelV3) -> int:
    """static int preset_shm_v1(CalcodeStandardFormModelV3 *m);"""
    calcode_standard_form_model_init_v3(m)
    calcode_standard_form_add_parameter_v3(m, "omega2", 1.0)
    calcode_standard_form_add_equation_v3(m, "x", "v", 1.0)
    calcode_standard_form_add_equation_v3(m, "v", "-omega2*x", 0.0)
    calcode_standard_form_set_domain_v3(m, 0.0, 8.0 * 3.14159265358979323846)
    calcode_standard_form_set_integrator_v3(m, 0.01, 1e-7, 1e-7, 0.05, 100000)
    return 1


def _preset_lorenz_v1(m: CalcodeStandardFormModelV3) -> int:
    """static int preset_lorenz_v1(CalcodeStandardFormModelV3 *m);"""
    calcode_standard_form_model_init_v3(m)
    calcode_standard_form_add_parameter_v3(m, "sigma", 10.0)
    calcode_standard_form_add_parameter_v3(m, "rho", 28.0)
    calcode_standard_form_add_parameter_v3(m, "beta", 8.0 / 3.0)
    calcode_standard_form_add_equation_v3(m, "x", "sigma*(y-x)", 1.0)
    calcode_standard_form_add_equation_v3(m, "y", "x*(rho-z)-y", 1.0)
    calcode_standard_form_add_equation_v3(m, "z", "x*y-beta*z", 1.0)
    calcode_standard_form_set_domain_v3(m, 0.0, 40.0)
    calcode_standard_form_set_integrator_v3(m, 0.01, 1e-6, 1e-6, 0.05, 100000)
    return 1


def _preset_vdp_v1(m: CalcodeStandardFormModelV3) -> int:
    """static int preset_vdp_v1(CalcodeStandardFormModelV3 *m);"""
    calcode_standard_form_model_init_v3(m)
    calcode_standard_form_add_parameter_v3(m, "mu", 1.0)
    calcode_standard_form_add_equation_v3(m, "x", "v", 2.0)
    calcode_standard_form_add_equation_v3(m, "v", "mu*(1-x*x)*v-x", 0.0)
    calcode_standard_form_set_domain_v3(m, 0.0, 30.0)
    calcode_standard_form_set_integrator_v3(m, 0.01, 1e-6, 1e-6, 0.05, 100000)
    return 1


def _preset_duffing_v1(m: CalcodeStandardFormModelV3) -> int:
    """static int preset_duffing_v1(CalcodeStandardFormModelV3 *m);"""
    calcode_standard_form_model_init_v3(m)
    calcode_standard_form_add_parameter_v3(m, "delta", 0.2)
    calcode_standard_form_add_parameter_v3(m, "alpha", -1.0)
    calcode_standard_form_add_parameter_v3(m, "beta", 1.0)
    calcode_standard_form_add_parameter_v3(m, "gamma", 0.3)
    calcode_standard_form_add_parameter_v3(m, "omega", 1.2)
    calcode_standard_form_add_equation_v3(m, "x", "v", 0.1)
    calcode_standard_form_add_equation_v3(
        m, "v", "-delta*v-alpha*x-beta*x*x*x+gamma*cos(omega*x)", 0.0)
    calcode_standard_form_set_domain_v3(m, 0.0, 50.0)
    calcode_standard_form_set_integrator_v3(m, 0.01, 1e-6, 1e-6, 0.05, 100000)
    return 1


def calcode_ode_definition_preset_v1(
    model: Optional[CalcodeStandardFormModelV3],
    name: Optional[str],
    error_box: Optional[List[str]] = None,
) -> int:
    """int calcode_ode_definition_preset_v1(CalcodeStandardFormModelV3 *model,
        const char *name, char *error, size_t error_capacity);"""
    if model is None or name is None:
        _set_error_v1(error_box, "missing preset name")
        return 0

    if name == "shm" or name == "SHM":
        return _preset_shm_v1(model)
    if name == "lorenz" or name == "Lorenz":
        return _preset_lorenz_v1(model)
    if name == "vdp" or name == "vanderpol":
        return _preset_vdp_v1(model)
    if name == "duffing" or name == "Duffing":
        return _preset_duffing_v1(model)

    if error_box is not None:
        error_box[0] = f"unknown ODE preset '{name}'"
    return 0
