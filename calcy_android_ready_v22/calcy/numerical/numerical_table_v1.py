"""calcode_numerical_table_v1.py -- exact Python port of
calcode_numerical_table_v1.c / calcode_numerical_table_v1.h.

Original: pure layout/interaction logic for the numerical table view --
column widths, visible-row windowing/scrolling, hit-testing, and value
formatting -- driven by a CalcodeSyncAnalysisV1. No rendering or OS calls.

PORT NOTES:

- `calcode_numerical_table_init_v1` reproduces the C's `memset(t, 0,
  sizeof(*t))` followed by explicit `row_height = 24`, `header_height =
  32`, `selected_row = hovered_row = -1`, and finally `valid = 0` --
  reproduced as an explicit field reset (not relying on Python's own
  "unset" defaults), preserving the exact same post-init field values,
  including the fact that `valid` is set to 0 *after* being implicitly
  zeroed by memset (a no-op in the C, reproduced as a literal
  redundant assignment here for structural fidelity).
- `calcode_numerical_table_configure_v1` calls `init_v1` unconditionally
  once the initial guard passes (mirroring the C's call order), so a
  previously configured table's state is dropped before the rest of
  the function runs.
- Column titles are copied via C's `snprintf(..., "%s", ...)` semantics,
  reproduced as Python string slicing to the format's max title length
  (64, matching `CalcodeTableColumnFormatV1.title[64]`).
- `clamp_v1` and `content_width_v1` are private (`static`) helpers in
  the C; ported as leading-underscore module-level functions to
  preserve their "not part of the public API" status. Note
  `content_width_v1` is declared in the C source but never actually
  called from any function in this file -- reproduced as dead code
  for structural fidelity, not invoked anywhere here either.
- The `visible_start` "jump near cursor" logic in `configure_v1`
  (`if selected_row >= visible_rows: visible_start = selected_row -
  visible_rows // 2`) is reproduced exactly, including that this branch
  does *not* clamp the resulting `visible_start` to `[0, max_start]`
  the way `resize_v1`/`scroll_rows_v1`/`set_selected_row_v1` do --
  matching the C, which has no such clamp here either (a can go
  negative or exceed the max on this particular path, on purpose).
- `calcode_numerical_table_column_x_v1` walks all visible columns
  before `column` to accumulate x-offset, exactly mirroring the C's
  linear scan (no cached/precomputed offsets).
- `calcode_numerical_table_hit_test_v1` reproduces the exact branch
  order: out-of-bounds check first, then header-row hit-test (which
  sets `hit.valid = 1` unconditionally once inside the header band,
  whether or not a column was hit), then row-band hit-test with the
  same "column loop breaks on first match, row is still valid even if
  no column matched" structure.
- `calcode_numerical_table_format_value_v1` reproduces C's
  `"%.*e"`/`"%.*g"` printf formatting via Python's equivalent `%`
  format specifiers with the same precision semantics.
"""

from __future__ import annotations

from typing import Optional

from calcy.app.synchronized_analysis_v1 import (
    CALCODE_SYNC_MAX_COLUMNS_V1,
    CalcodeSyncAnalysisV1,
)


class CalcodeTableColumnFormatV1:
    """typedef struct CalcodeTableColumnFormatV1 { ... } CalcodeTableColumnFormatV1."""
    __slots__ = ("visible", "width", "precision", "scientific", "title")

    def __init__(self):
        self.visible = 0
        self.width = 0
        self.precision = 0
        self.scientific = 0
        self.title = ""


class CalcodeNumericalTableV1:
    """typedef struct CalcodeNumericalTableV1 { ... } CalcodeNumericalTableV1."""
    __slots__ = ("valid", "width", "height", "row_height", "header_height",
                 "visible_start", "visible_rows", "selected_row",
                 "hovered_row", "first_column", "horizontal_offset",
                 "column_count", "columns", "title", "diagnostic")

    def __init__(self):
        self.valid = 0
        self.width = 0
        self.height = 0
        self.row_height = 0
        self.header_height = 0
        self.visible_start = 0
        self.visible_rows = 0
        self.selected_row = 0
        self.hovered_row = 0
        self.first_column = 0
        self.horizontal_offset = 0
        self.column_count = 0
        self.columns = [CalcodeTableColumnFormatV1()
                         for _ in range(CALCODE_SYNC_MAX_COLUMNS_V1)]
        self.title = ""
        self.diagnostic = ""


class CalcodeTableHitV1:
    """typedef struct CalcodeTableHitV1 { ... } CalcodeTableHitV1."""
    __slots__ = ("valid", "row", "column", "local_x", "local_y",
                 "on_header", "on_row", "on_column", "diagnostic")

    def __init__(self):
        self.valid = 0
        self.row = 0
        self.column = 0
        self.local_x = 0
        self.local_y = 0
        self.on_header = 0
        self.on_row = 0
        self.on_column = 0
        self.diagnostic = ""


def _clamp_v1(x: int, lo: int, hi: int) -> int:
    """static int clamp_v1(int x, int lo, int hi)"""
    if x < lo:
        return lo

    if x > hi:
        return hi

    return x


def _content_width_v1(t: CalcodeNumericalTableV1) -> int:
    """static int content_width_v1(const CalcodeNumericalTableV1 *t)
    (declared in the C source but never called from anywhere in this
    file -- reproduced here as unused dead code for structural fidelity)"""
    width = 0

    for i in range(t.column_count):
        if t.columns[i].visible:
            width += t.columns[i].width

    return width


def calcode_numerical_table_init_v1(t: CalcodeNumericalTableV1) -> None:
    """void calcode_numerical_table_init_v1(CalcodeNumericalTableV1 *t)"""
    if t is None:
        return

    t.valid = 0
    t.width = 0
    t.height = 0
    t.row_height = 0
    t.header_height = 0
    t.visible_start = 0
    t.visible_rows = 0
    t.selected_row = 0
    t.hovered_row = 0
    t.first_column = 0
    t.horizontal_offset = 0
    t.column_count = 0
    t.columns = [CalcodeTableColumnFormatV1()
                 for _ in range(CALCODE_SYNC_MAX_COLUMNS_V1)]
    t.title = ""
    t.diagnostic = ""

    t.row_height = 24
    t.header_height = 32

    t.selected_row = -1
    t.hovered_row = -1

    t.valid = 0


def calcode_numerical_table_configure_v1(
    t: CalcodeNumericalTableV1,
    a: Optional[CalcodeSyncAnalysisV1],
    width: int,
    height: int,
) -> int:
    """int calcode_numerical_table_configure_v1(CalcodeNumericalTableV1 *t,
    const CalcodeSyncAnalysisV1 *a, int width, int height)"""
    if (t is None or a is None or not a.valid or not a.table.valid or
            width <= 0 or height <= 0):
        return 0

    calcode_numerical_table_init_v1(t)

    t.width = width
    t.height = height

    t.column_count = a.table.column_count

    if t.column_count > CALCODE_SYNC_MAX_COLUMNS_V1:
        return 0

    for i in range(t.column_count):
        t.columns[i].visible = 1
        t.columns[i].width = 110 if i == 0 else 140
        t.columns[i].precision = 10
        t.columns[i].scientific = 0

        t.columns[i].title = a.table.column_names[i][:63]

    t.title = (a.trajectory.title if a.trajectory.title
               else "Numerical Table")[:127]

    t.visible_rows = (height - t.header_height) // t.row_height

    if t.visible_rows < 1:
        t.visible_rows = 1

    if t.visible_rows > a.table.row_count:
        t.visible_rows = a.table.row_count

    t.visible_start = 0

    if a.cursor.valid:
        t.selected_row = a.cursor.sample_index

    if t.selected_row >= t.visible_rows:
        t.visible_start = t.selected_row - t.visible_rows // 2

    t.valid = 1

    return 1


def calcode_numerical_table_resize_v1(
    t: CalcodeNumericalTableV1,
    a: Optional[CalcodeSyncAnalysisV1],
    width: int,
    height: int,
) -> int:
    """int calcode_numerical_table_resize_v1(CalcodeNumericalTableV1 *t,
    const CalcodeSyncAnalysisV1 *a, int width, int height)"""
    if (t is None or not t.valid or a is None or not a.valid or
            width <= 0 or height <= 0):
        return 0

    t.width = width
    t.height = height

    t.visible_rows = (height - t.header_height) // t.row_height

    if t.visible_rows < 1:
        t.visible_rows = 1

    if t.visible_rows > a.table.row_count:
        t.visible_rows = a.table.row_count

    max_start = a.table.row_count - t.visible_rows

    if max_start < 0:
        max_start = 0

    t.visible_start = _clamp_v1(t.visible_start, 0, max_start)

    return 1


def calcode_numerical_table_set_selected_row_v1(
    t: CalcodeNumericalTableV1,
    a: Optional[CalcodeSyncAnalysisV1],
    row: int,
) -> int:
    """int calcode_numerical_table_set_selected_row_v1(
    CalcodeNumericalTableV1 *t, const CalcodeSyncAnalysisV1 *a, int row)"""
    if (t is None or not t.valid or a is None or not a.valid or
            row < 0 or row >= a.table.row_count):
        return 0

    t.selected_row = row

    last_visible = t.visible_start + t.visible_rows - 1

    if row < t.visible_start:
        t.visible_start = row
    elif row > last_visible:
        t.visible_start = row - t.visible_rows + 1

    max_start = a.table.row_count - t.visible_rows

    if max_start < 0:
        max_start = 0

    t.visible_start = _clamp_v1(t.visible_start, 0, max_start)

    return 1


def calcode_numerical_table_scroll_rows_v1(
    t: CalcodeNumericalTableV1,
    a: Optional[CalcodeSyncAnalysisV1],
    delta: int,
) -> int:
    """int calcode_numerical_table_scroll_rows_v1(CalcodeNumericalTableV1 *t,
    const CalcodeSyncAnalysisV1 *a, int delta)"""
    if t is None or not t.valid or a is None or not a.valid:
        return 0

    max_start = a.table.row_count - t.visible_rows

    if max_start < 0:
        max_start = 0

    t.visible_start = _clamp_v1(t.visible_start + delta, 0, max_start)

    return 1


def calcode_numerical_table_visible_row_v1(
    t: CalcodeNumericalTableV1,
    visual_row: int,
    source_row_out: list,
) -> int:
    """int calcode_numerical_table_visible_row_v1(
    const CalcodeNumericalTableV1 *t, int visual_row, int *source_row)

    `source_row_out` is a 1-element list used as an output parameter in
    place of C's `int *source_row`."""
    if (t is None or not t.valid or source_row_out is None or
            visual_row < 0 or visual_row >= t.visible_rows):
        return 0

    source_row_out[0] = t.visible_start + visual_row

    return 1


def calcode_numerical_table_column_x_v1(
    t: CalcodeNumericalTableV1,
    column: int,
    x0_out: list,
    x1_out: list,
) -> int:
    """int calcode_numerical_table_column_x_v1(
    const CalcodeNumericalTableV1 *t, int column, int *x0, int *x1)

    `x0_out`/`x1_out` are 1-element lists used as output parameters in
    place of C's `int *x0, int *x1`."""
    if (t is None or not t.valid or x0_out is None or x1_out is None or
            column < 0 or column >= t.column_count or
            not t.columns[column].visible):
        return 0

    x = -t.horizontal_offset

    for i in range(column):
        if t.columns[i].visible:
            x += t.columns[i].width

    x0_out[0] = x
    x1_out[0] = x + t.columns[column].width

    return 1


def calcode_numerical_table_hit_test_v1(
    t: CalcodeNumericalTableV1,
    a: Optional[CalcodeSyncAnalysisV1],
    local_x: int,
    local_y: int,
    hit: CalcodeTableHitV1,
) -> int:
    """int calcode_numerical_table_hit_test_v1(
    const CalcodeNumericalTableV1 *t, const CalcodeSyncAnalysisV1 *a,
    int local_x, int local_y, CalcodeTableHitV1 *hit)"""
    if t is None or not t.valid or a is None or not a.valid or hit is None:
        return 0

    hit.valid = 0
    hit.row = 0
    hit.column = 0
    hit.local_x = 0
    hit.local_y = 0
    hit.on_header = 0
    hit.on_row = 0
    hit.on_column = 0
    hit.diagnostic = ""

    hit.row = -1
    hit.column = -1
    hit.local_x = local_x
    hit.local_y = local_y

    if local_x < 0 or local_x >= t.width or local_y < 0 or local_y >= t.height:
        return 0

    if local_y < t.header_height:
        hit.on_header = 1

        for c in range(t.column_count):
            x0 = [0]
            x1 = [0]

            if not calcode_numerical_table_column_x_v1(t, c, x0, x1):
                continue

            if local_x >= x0[0] and local_x < x1[0]:
                hit.column = c
                hit.on_column = 1
                hit.valid = 1
                return 1

        hit.valid = 1
        return 1

    visual_row = (local_y - t.header_height) // t.row_height

    if visual_row < 0 or visual_row >= t.visible_rows:
        return 0

    source_row = t.visible_start + visual_row

    if source_row < 0 or source_row >= a.table.row_count:
        return 0

    hit.row = source_row
    hit.on_row = 1

    for c in range(t.column_count):
        x0 = [0]
        x1 = [0]

        if not calcode_numerical_table_column_x_v1(t, c, x0, x1):
            continue

        if local_x >= x0[0] and local_x < x1[0]:
            hit.column = c
            hit.on_column = 1
            break

    hit.valid = 1

    return 1


def calcode_numerical_table_click_row_v1(
    t: CalcodeNumericalTableV1,
    a: Optional[CalcodeSyncAnalysisV1],
    local_x: int,
    local_y: int,
    row_out: list,
) -> int:
    """int calcode_numerical_table_click_row_v1(CalcodeNumericalTableV1 *t,
    const CalcodeSyncAnalysisV1 *a, int local_x, int local_y, int *row)

    `row_out` is a 1-element list used as an output parameter in place
    of C's `int *row`."""
    if t is None or a is None or row_out is None:
        return 0

    hit = CalcodeTableHitV1()

    if not calcode_numerical_table_hit_test_v1(t, a, local_x, local_y, hit):
        return 0

    if not hit.on_row or hit.row < 0:
        return 0

    if not calcode_numerical_table_set_selected_row_v1(t, a, hit.row):
        return 0

    row_out[0] = hit.row

    return 1


def calcode_numerical_table_format_value_v1(
    t: CalcodeNumericalTableV1,
    column: int,
    value: float,
    buffer_size: int,
    buffer_out: list,
) -> int:
    """int calcode_numerical_table_format_value_v1(
    const CalcodeNumericalTableV1 *t, int column, double value,
    char *buffer, int buffer_size)

    `buffer_out` is a 1-element list used as an output parameter in
    place of C's `char *buffer`, matching the output-parameter
    convention used by the other functions in this file
    (`column_x_v1`, `visible_row_v1`, `click_row_v1`). `buffer_size`
    is kept as a parameter for interface fidelity but has no effect
    on the produced string, since Python has no fixed-size buffer to
    truncate into (snprintf's truncation-to-buffer-size behavior has
    no observable counterpart here)."""
    if (t is None or not t.valid or buffer_out is None or buffer_size <= 0 or
            column < 0 or column >= t.column_count):
        return 0

    f = t.columns[column]

    if f.scientific:
        buffer_out[0] = "%.*e" % (f.precision, value)
    else:
        buffer_out[0] = "%.*g" % (f.precision, value)

    return 1
