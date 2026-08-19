"""calcode_problem_io.py -- exact Python port of calcode_problem_io.c / .h.

Original: a compact text (key=value) file format for CalcodeProblem, used
by calcode_problem_save/load and, at a lower level,
calcode_problem_write/read against an already-open stream.

PORT NOTES:

- `FILE*` becomes a Python text file object; `calcode_problem_write` /
  `calcode_problem_read` take one directly, exactly like the C functions.

- `char *error, int error_len` output-buffer pairs become `(ok, message)`
  return tuples everywhere, per the convention established in
  calcode_model.py / calcode_problem.py.

- `strtol`/`strtoul`/`strtod` are approximated with regex-anchored parses
  (`_pi`/`_pu`/`_pd`) rather than bit-for-bit reproducing libc's overflow
  (`errno`) and locale edge cases. For any value an actual saved problem
  file would contain, behavior is identical; only pathological inputs
  (values overflowing a C `long`, `inf`/`nan` literals, exotic locales)
  could theoretically differ. Flagging this rather than silently claiming
  full fidelity there.

- `sscanf(k, "rhs%d", &i) == 1` is a *prefix* match -- it succeeds (and
  ignores trailing garbage) as long as `k` starts with "rhs" followed by
  digits. This port preserves that exact prefix-match looseness for
  `rhs%d` / `y0_%d` / `k%d` via `re.match(...)` (no trailing `$` anchor)
  rather than "fixing" it into a stricter full match.

- **Preserved bug, not fixed**: `calcode_problem_write`'s `notes_lines`
  count (`nl = count of '\\n' in notes, +1 if notes non-empty`) does not
  always equal the number of `note=` records the same function actually
  emits. Whenever `notes` ends with a trailing `\\n`, the count is one
  too high (the emission loop stops as soon as the remainder is empty,
  without emitting a final blank record) -- so a problem saved with
  trailing-newline notes will fail to reload with "notes_lines does not
  match note records". This is a genuine latent bug in the original C,
  reproduced here exactly rather than silently corrected, matching the
  "no losing anything, exact conversion" brief.
"""

from __future__ import annotations

import re
from typing import IO, Optional, Tuple

from calcy.core.model import (
    CALCODE_ERROR_MAX,
    CALCODE_EXPR_MAX,
    CALCODE_NAME_MAX,
    CalcodeGeometryKind,
    ODESYS_MAX_EQNS,
    ODESYS_MAX_PARAMS,
    _cstr,
)
from calcy.core.problem import (
    CALCODE_PROBLEM_FORMAT_VERSION,
    CalcodeProblem,
    calcode_problem_validate,
)

# #define CALCODE_FILE_MAGIC "CALCODE-PROBLEM"
# #define CALCODE_FILE_VERSION 1
CALCODE_FILE_MAGIC = "CALCODE-PROBLEM"
CALCODE_FILE_VERSION = 1

# char notes[2048]; from calcode_problem.h
CALCODE_NOTES_MAX = 2048

_INT_RE = re.compile(r"\s*[+-]?\d+")
_FLOAT_RE = re.compile(r"\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_RHS_RE = re.compile(r"rhs(\d+)")
_Y0_RE = re.compile(r"y0_(\d+)")
_K_RE = re.compile(r"k(\d+)")


def _g17(x: float) -> str:
    """Mimic C's `%.17g` formatting used throughout calcode_problem_write."""
    return "%.17g" % x


def _pi(s: Optional[str]) -> Optional[int]:
    """static int pi(const char *s, int *o): strtol base 10, full-string
    match after trimming trailing whitespace. Returns None on failure
    (C's return 0)."""
    if not s:
        return None
    m = _INT_RE.match(s)
    if not m:
        return None
    if s[m.end():].strip():
        return None
    try:
        return int(m.group())
    except ValueError:
        return None


def _pu(s: Optional[str]) -> Optional[int]:
    """static int pu(const char *s, unsigned long *o): strtoul base 10."""
    if not s:
        return None
    m = _INT_RE.match(s)
    if not m:
        return None
    if s[m.end():].strip():
        return None
    try:
        v = int(m.group())
    except ValueError:
        return None
    return v if v >= 0 else None


def _pd(s: Optional[str]) -> Optional[float]:
    """static int pd(const char *s, double *o): strtod."""
    if not s:
        return None
    m = _FLOAT_RE.match(s)
    if not m:
        return None
    if s[m.end():].strip():
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _trim(s: str) -> str:
    """static char *trim(char *s): trims ASCII whitespace from both ends."""
    return s.strip()


def _kv(s: str) -> Tuple[int, Optional[str], Optional[str]]:
    """static int kv(char *s, char **k, char **v): splits "key = value" on
    the first '='. Returns (status, key, value); status 1 = success,
    0 = blank/comment/empty-key-or-value, -1 = no '=' found."""
    s = _trim(s)
    if not s or s[0] == "#":
        return 0, None, None
    idx = s.find("=")
    if idx < 0:
        return -1, None, None
    k = _trim(s[:idx])
    v = _trim(s[idx + 1:])
    if k and v:
        return 1, k, v
    return 0, k, v


def _zero_model():
    """Reproduce `memset(&problem->model, 0, sizeof(problem->model))` --
    a raw all-zero CalcodeModel, distinct from calcode_model_reset()'s
    non-zero defaults. calcode_problem_read intentionally starts here so
    that a field missing from the file stays 0 (and later fails
    calcode_problem_validate), never silently inheriting reset()'s
    defaults."""
    from calcy.core.model import CalcodeModel

    m = CalcodeModel.__new__(CalcodeModel)
    m.name = ""
    m.neqns = 0
    m.nparams = 0
    m.rhs = ["" for _ in range(ODESYS_MAX_EQNS)]
    m.y0 = [0.0] * ODESYS_MAX_EQNS
    m.k = [0.0] * ODESYS_MAX_PARAMS
    m.x0 = 0.0
    m.x1 = 0.0
    m.h0 = 0.0
    m.tol = 0.0
    m.hmin = 0.0
    m.hmax = 0.0
    m.max_steps = 0
    m.geometry = CalcodeGeometryKind.NONE
    m.geometry_x = 0
    m.geometry_y = 0
    m.geometry_z = 0
    m.particle_count = 0
    return m


def calcode_problem_write(fp: Optional[IO[str]], problem: Optional[CalcodeProblem],
                           error_len: int = CALCODE_ERROR_MAX) -> Tuple[int, str]:
    """int calcode_problem_write(FILE *fp, const CalcodeProblem *p, char *e, int n);"""
    if fp is None or problem is None:
        return 0, _cstr("NULL stream or problem", error_len)

    ok, msg = calcode_problem_validate(problem, error_len)
    if not ok:
        return 0, msg

    m = problem.model
    try:
        fp.write("# CALCODE native mathematical problem\n")
        fp.write(f"{CALCODE_FILE_MAGIC}\n")
        fp.write(f"version={CALCODE_FILE_VERSION}\n")
        fp.write(f"problem_format={problem.format_version}\n")
        fp.write(f"revision={problem.revision}\n")
        fp.write(f"name={m.name}\n")
        fp.write(f"neqns={m.neqns}\n")
        fp.write(f"nparams={m.nparams}\n")
        fp.write(f"x0={_g17(m.x0)}\n")
        fp.write(f"x1={_g17(m.x1)}\n")
        fp.write(f"h0={_g17(m.h0)}\n")
        fp.write(f"tol={_g17(m.tol)}\n")
        fp.write(f"hmin={_g17(m.hmin)}\n")
        fp.write(f"hmax={_g17(m.hmax)}\n")
        fp.write(f"max_steps={m.max_steps}\n")
        fp.write(f"geometry={int(m.geometry)}\n")
        fp.write(f"geometry_x={m.geometry_x}\n")
        fp.write(f"geometry_y={m.geometry_y}\n")
        fp.write(f"geometry_z={m.geometry_z}\n")
        fp.write(f"particle_count={m.particle_count}\n")

        for i in range(m.neqns):
            fp.write(f"rhs{i + 1}={m.rhs[i]}\n")
            fp.write(f"y0_{i + 1}={_g17(m.y0[i])}\n")
        for i in range(m.nparams):
            fp.write(f"k{i + 1}={_g17(m.k[i])}\n")

        # Preserved bug -- see module docstring.
        nl = problem.notes.count("\n")
        if problem.notes:
            nl += 1
        fp.write(f"notes_lines={nl}\n")

        if problem.notes:
            s = problem.notes
            while s:
                idx = s.find("\n")
                if idx == -1:
                    fp.write(f"note={s}\n")
                    break
                fp.write(f"note={s[:idx]}\n")
                s = s[idx + 1:]

        fp.write("END\n")
    except OSError:
        return 0, _cstr("write error", error_len)

    return 1, ""


def _assign(problem: CalcodeProblem, k: str, v: str, nl: int, ns: int) -> Tuple[int, int, int]:
    """static int assign(CalcodeProblem *p, const char *k, const char *v,
                          int *nl, int *ns); Returns (ok, nl, ns) since
    Python has no `int *` out-params."""
    m = problem.model

    if k == "problem_format":
        pv = _pi(v)
        if pv is None:
            return 0, nl, ns
        problem.format_version = pv
        return 1, nl, ns
    if k == "revision":
        pv = _pu(v)
        if pv is None:
            return 0, nl, ns
        problem.revision = pv
        return 1, nl, ns
    if k == "name":
        m.name = _cstr(v, CALCODE_NAME_MAX)
        return 1, nl, ns
    if k == "neqns":
        pv = _pi(v)
        if pv is None:
            return 0, nl, ns
        m.neqns = pv
        return 1, nl, ns
    if k == "nparams":
        pv = _pi(v)
        if pv is None:
            return 0, nl, ns
        m.nparams = pv
        return 1, nl, ns
    if k in ("x0", "x1", "h0", "tol", "hmin", "hmax"):
        pv = _pd(v)
        if pv is None:
            return 0, nl, ns
        setattr(m, k, pv)
        return 1, nl, ns
    if k == "max_steps":
        pv = _pi(v)
        if pv is None:
            return 0, nl, ns
        m.max_steps = pv
        return 1, nl, ns
    if k == "geometry":
        pv = _pi(v)
        if pv is None:
            return 0, nl, ns
        # C does an unchecked `(CalcodeGeometryKind)i` cast; mirror that
        # by accepting any int, not just defined enum members.
        try:
            m.geometry = CalcodeGeometryKind(pv)
        except ValueError:
            m.geometry = pv
        return 1, nl, ns
    if k in ("geometry_x", "geometry_y", "geometry_z", "particle_count"):
        pv = _pi(v)
        if pv is None:
            return 0, nl, ns
        setattr(m, k, pv)
        return 1, nl, ns
    if k == "notes_lines":
        pv = _pi(v)
        if pv is None:
            return 0, nl, ns
        return 1, pv, ns
    if k == "note":
        cap = CALCODE_NOTES_MAX
        notes = problem.notes
        u = len(notes)
        r = cap - u
        if u and r > 1:
            notes = notes + "\n"
            u = len(notes)
            r = cap - u
        if r > 1:
            notes = notes + v[: r - 1]
        problem.notes = notes
        return 1, nl, ns + 1

    match = _RHS_RE.match(k)
    if match:
        i = int(match.group(1))
        if i < 1 or i > ODESYS_MAX_EQNS:
            return 0, nl, ns
        m.rhs[i - 1] = _cstr(v, CALCODE_EXPR_MAX)
        return 1, nl, ns

    match = _Y0_RE.match(k)
    if match:
        i = int(match.group(1))
        if i < 1 or i > ODESYS_MAX_EQNS:
            return 0, nl, ns
        pv = _pd(v)
        if pv is None:
            return 0, nl, ns
        m.y0[i - 1] = pv
        return 1, nl, ns

    match = _K_RE.match(k)
    if match:
        i = int(match.group(1))
        if i < 1 or i > ODESYS_MAX_PARAMS:
            return 0, nl, ns
        pv = _pd(v)
        if pv is None:
            return 0, nl, ns
        m.k[i - 1] = pv
        return 1, nl, ns

    return 0, nl, ns


def calcode_problem_read(fp: Optional[IO[str]], problem: Optional[CalcodeProblem],
                          error_len: int = CALCODE_ERROR_MAX) -> Tuple[int, str]:
    """int calcode_problem_read(FILE *fp, CalcodeProblem *p, char *e, int n);
    Mutates `problem` in place, exactly as the C function writes through
    its `CalcodeProblem *p` pointer."""
    if fp is None or problem is None:
        return 0, _cstr("NULL stream or problem", error_len)

    problem.model = _zero_model()
    problem.notes = ""
    problem.revision = 0
    problem.format_version = CALCODE_PROBLEM_FORMAT_VERSION

    magic = False
    end = False
    ver = 0
    nl = 0
    ns = 0

    try:
        for raw_line in fp:
            s = _trim(raw_line)
            if not s or s[0] == "#":
                continue

            if not magic:
                if s == CALCODE_FILE_MAGIC:
                    magic = True
                    continue
                return 0, _cstr("not a CALCODE problem file", error_len)

            if s == "END":
                end = True
                break

            status, k, v = _kv(s)
            if status <= 0:
                return 0, _cstr("malformed problem-file line", error_len)

            if k == "version":
                pv = _pi(v)
                if pv is None:
                    return 0, _cstr("invalid file version", error_len)
                ver = pv
                continue

            ok, nl, ns = _assign(problem, k, v, nl, ns)
            if not ok:
                return 0, _cstr(f"invalid or unknown key: {k}", error_len)
    except OSError:
        return 0, _cstr("read error", error_len)

    if not magic or not end:
        return 0, _cstr("incomplete CALCODE problem file", error_len)
    if ver != CALCODE_FILE_VERSION:
        return 0, _cstr("unsupported CALCODE problem-file version", error_len)
    if ns != nl:
        return 0, _cstr("notes_lines does not match note records", error_len)

    return calcode_problem_validate(problem, error_len)


def calcode_problem_save(problem: Optional[CalcodeProblem], filename: Optional[str],
                          error_len: int = CALCODE_ERROR_MAX) -> Tuple[int, str]:
    """int calcode_problem_save(const CalcodeProblem *p, const char *f, char *e, int n);"""
    if not filename:
        return 0, _cstr("empty filename", error_len)

    try:
        fp = open(filename, "w", newline="\n")
    except OSError:
        return 0, _cstr("cannot open file for writing", error_len)

    ok, msg = calcode_problem_write(fp, problem, error_len)
    close_failed = False
    try:
        fp.close()
    except OSError:
        close_failed = True

    if close_failed and ok:
        return 0, _cstr("close failed after write", error_len)
    return ok, msg


def calcode_problem_load(problem: Optional[CalcodeProblem], filename: Optional[str],
                          error_len: int = CALCODE_ERROR_MAX) -> Tuple[int, str]:
    """int calcode_problem_load(CalcodeProblem *p, const char *f, char *e, int n);"""
    if not filename:
        return 0, _cstr("empty filename", error_len)

    try:
        fp = open(filename, "r")
    except OSError:
        return 0, _cstr("cannot open file for reading", error_len)

    ok, msg = calcode_problem_read(fp, problem, error_len)
    close_failed = False
    try:
        fp.close()
    except OSError:
        close_failed = True

    if close_failed and ok:
        return 0, _cstr("close failed after read", error_len)
    return ok, msg
