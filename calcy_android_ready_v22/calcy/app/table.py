"""calcode_table.py -- exact Python port of calcode_table.c / calcode_table.h.

Original: builds the high-precision numerical table view over a solved
ODESolution -- a fixed number of evenly spaced rows in [x0, x1], each
row's value obtained via calcode_interpolate_state, plus a full-
precision (%.17g) CSV writer. This is the "long highly precision
numerical table" view: one row per sample, one column per requested
state, written at full double precision so nothing is lost going to
disk/display.

PORT NOTES: `t->x` / `t->value` (malloc'd C arrays) become Python
lists. `calcode_table_write_csv`'s `FILE *fp` becomes any Python
file-like object opened in text mode; C's `fprintf`/`ferror` become
`.write()` + a try/except (mirrors the "check ferror after writing"
pattern -- if the write raises, treat it as `!ferror(fp)` == failure).
"""

from __future__ import annotations

from typing import List, Optional, TextIO

from calcy.core.interpolate import calcode_interpolate_state
from calcy.core.odesolution import ODESolution


class CalcodeTable:
    """typedef struct CalcodeTable {
        int rows;
        int columns;
        double *x;
        double *value;
        int state;
    } CalcodeTable;
    """

    __slots__ = ("rows", "columns", "x", "value", "state")

    def __init__(self) -> None:
        self.rows = 0
        self.columns = 0
        self.x: List[float] = []
        self.value: List[float] = []
        self.state = 0


def calcode_table_init(t: Optional[CalcodeTable]) -> None:
    """void calcode_table_init(CalcodeTable *table);  memset(t, 0, sizeof(*t));"""
    if t is None:
        return
    t.rows = 0
    t.columns = 0
    t.x = []
    t.value = []
    t.state = 0


def calcode_table_free(t: Optional[CalcodeTable]) -> None:
    """void calcode_table_free(CalcodeTable *table);

    free(t->x); free(t->value); calcode_table_init(t);
    No-op malloc-free in Python; kept for literal call-site parity.
    """
    if t is None:
        return
    calcode_table_init(t)


def calcode_table_build(
    s: Optional[ODESolution],
    state: int,
    x0: float,
    x1: float,
    rows: int,
    t: Optional[CalcodeTable],
) -> int:
    """int calcode_table_build(const ODESolution *solution, int state,
                                double x0, double x1, int rows,
                                CalcodeTable *table);"""
    if (
        s is None
        or t is None
        or not s.ok
        or state < 0
        or state >= s.neqns
        or rows < 2
        or x1 <= x0
    ):
        return 0

    calcode_table_free(t)
    calcode_table_init(t)

    t.x = [0.0] * rows
    t.value = [0.0] * rows

    t.rows = rows
    t.columns = 2
    t.state = state

    value_box = [0.0]
    for i in range(rows):
        f = float(i) / float(rows - 1)

        t.x[i] = x0 + f * (x1 - x0)

        if not calcode_interpolate_state(s, state, t.x[i], value_box):
            calcode_table_free(t)
            return 0
        t.value[i] = value_box[0]

    return 1


def calcode_table_write_csv(t: Optional[CalcodeTable], fp: Optional[TextIO]) -> int:
    """int calcode_table_write_csv(const CalcodeTable *table, FILE *fp);

    fprintf(fp, "row,x,y%d\\n", t->state + 1);
    then one "%d,%.17g,%.17g\\n" line per row. Returns !ferror(fp);
    a write exception here is treated the same as ferror(fp) != 0.
    """
    if t is None or fp is None or t.rows <= 0:
        return 0

    try:
        fp.write(f"row,x,y{t.state + 1}\n")
        for i in range(t.rows):
            fp.write(f"{i},{t.x[i]:.17g},{t.value[i]:.17g}\n")
    except OSError:
        return 0

    return 1
