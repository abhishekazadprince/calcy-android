"""calcode_numerical_table_ascii_v1.py -- exact Python port of
calcode_numerical_table_ascii_v1.c / calcode_numerical_table_ascii_v1.h.

Original: renders a `CalcodeNumericalTableV1` (layout/selection state)
against a `CalcodeSyncAnalysisV1`'s row data as a plain ASCII table to
stdout -- a fallback/debug view independent of any GL rendering.

PORT NOTES:

- `calcode_numerical_table_print_v1`'s guard (`!t`, `!t->valid`, `!a`,
  `!a->valid`) is reproduced with the same order; the function is a
  void no-op on failure in the C, and Python's version returns `None`
  the same way (no return value is ever consulted by callers).
- Header/column printing loop only counts *visible* columns (checked
  per-column, not by a separate precomputed count) -- reproduced with
  the same per-iteration `if not visible: continue` pattern rather
  than pre-filtering the column list, so the iteration order and any
  future side effects added to the loop body would still match.
- The header underline row prints one `"----------------"` (16 dashes)
  per visible column with no trailing formatting -- reproduced
  literally, including that it does NOT match the 16-character `%16s`
  width of a right-aligned column header exactly by coincidence of the
  same literal width (both are independently hardcoded to 16 in the
  C, not derived from each other) -- preserved as two separate
  hardcoded 16s rather than refactored into one shared constant.
- The row range clamps `end = min(start + visible_rows, a.table.row_count)`
  but never clamps `start` itself (e.g. a negative or out-of-range
  `visible_start` set directly on the table struct would produce an
  empty or reversed-looking range in C's `for` loop, which simply
  wouldn't execute) -- reproduced with Python's `range(start, end)`,
  which has the identical empty-if-`start >= end` behavior.
- Row values are read from the flat `a.table.values` array via
  `row * a.table.column_count + c` -- reproduced with the identical
  flat-index arithmetic against the Python list rather than any
  2D-indexing convenience, to keep the indexing bug-for-bug identical
  if `t.column_count` and `a.table.column_count` were ever to
  disagree (the C indexes with the *analysis* table's column_count,
  not the display table's own `column_count` -- reproduced exactly,
  not "fixed" to use `t.column_count` even though that might look more
  consistent).
- `calcode_numerical_table_format_value_v1` is reused unchanged from
  the already-ported `calcode_numerical_table_v1` module for
  per-cell formatting, exactly as the C calls the sibling function
  from the same header family.
- The selection marker (`>` for the selected row, a literal space
  otherwise) and the trailing summary line's `end - 1` vs. `start`
  fallback when the range is empty are reproduced with the same
  ternary-equivalent logic.
- This function prints directly (matches the C's direct `printf` to
  stdout); it has no return value to port.
"""

from __future__ import annotations

from typing import Optional

from calcy.numerical.numerical_table_v1 import (
    CalcodeNumericalTableV1,
    calcode_numerical_table_format_value_v1,
)
from calcy.app.synchronized_analysis_v1 import CalcodeSyncAnalysisV1


def calcode_numerical_table_print_v1(
        t: Optional[CalcodeNumericalTableV1],
        a: Optional[CalcodeSyncAnalysisV1]) -> None:
    if t is None or not t.valid or a is None or not a.valid:
        return

    print()
    print("=" * 60)
    print(" %s" % t.title)
    print("=" * 60)

    header = ""
    for c in range(t.column_count):
        if not t.columns[c].visible:
            continue
        header += "%16s" % t.columns[c].title
    print(header)

    underline = ""
    for c in range(t.column_count):
        if t.columns[c].visible:
            underline += "-" * 16
    print(underline)

    start = t.visible_start
    end = start + t.visible_rows

    if end > a.table.row_count:
        end = a.table.row_count

    for row in range(start, end):
        line = ">" if row == t.selected_row else " "

        for c in range(t.column_count):
            if not t.columns[c].visible:
                continue

            value = a.table.values[row * a.table.column_count + c]

            buffer = [""]
            calcode_numerical_table_format_value_v1(t, c, value, 96, buffer)

            line += "%16s" % buffer[0]

        print(line)

    print()
    print("rows %d..%d of %d | selected=%d" % (
        start,
        end - 1 if end > start else start,
        a.table.row_count,
        t.selected_row))
