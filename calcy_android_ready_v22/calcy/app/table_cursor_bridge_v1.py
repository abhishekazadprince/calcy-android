"""calcode_table_cursor_bridge_v1.py -- exact Python port of
calcode_table_cursor_bridge_v1.c / calcode_table_cursor_bridge_v1.h.

Original: the thin bridge that closes the loop table-row-click -> sync
cursor. Wraps a CalcodeNumericalTableV1 widget + a CalcodeSyncAnalysisV1
and, on `select_row`, drives the sync cursor to that row and mirrors the
resulting selection back onto the table widget's `selected_row`.

PORT NOTES: straightforward struct-holder + three functions, same
init/reset conventions as every other file in this layer.

PORT STATUS -- harness-verified bit-exact against a compiled `gcc -O2`
build of the real C (verification_harnesses/harness_table_cursor_bridge.c/.py),
using a real 6-sample trajectory/analysis/table built through the
actual `calcode_sync_analysis_build_v1`/`calcode_numerical_table_configure_v1`
calls. Covers NULL bridge/table/analysis at every entry point, an
invalid (unconfigured) table and an invalid analysis, a valid
configure, and select_row across a normal middle row, row 0, the last
valid row, an out-of-range row, a negative row, and a far out-of-range
row. Zero diff.
"""

from __future__ import annotations

from typing import Optional

from calcy.numerical.numerical_table_v1 import CalcodeNumericalTableV1
from calcy.app.synchronized_analysis_v1 import (
    CalcodeSyncAnalysisV1,
    calcode_sync_analysis_set_index_v1,
)


class CalcodeTableCursorBridgeV1:
    """typedef struct CalcodeTableCursorBridgeV1 {
        int valid;
        CalcodeNumericalTableV1 *table;
        CalcodeSyncAnalysisV1 *analysis;
        int last_row;
        char diagnostic[256];
    } CalcodeTableCursorBridgeV1;
    """

    __slots__ = ("valid", "table", "analysis", "last_row", "diagnostic")

    def __init__(self) -> None:
        self.valid = 0
        self.table: Optional[CalcodeNumericalTableV1] = None
        self.analysis: Optional[CalcodeSyncAnalysisV1] = None
        self.last_row = 0
        self.diagnostic = ""


def calcode_table_cursor_bridge_init_v1(b: Optional[CalcodeTableCursorBridgeV1]) -> None:
    """void calcode_table_cursor_bridge_init_v1(CalcodeTableCursorBridgeV1 *b);

    memset(b, 0, sizeof(*b)); b->last_row = -1;
    """
    if b is None:
        return

    b.valid = 0
    b.table = None
    b.analysis = None
    b.last_row = 0
    b.diagnostic = ""

    b.last_row = -1


def calcode_table_cursor_bridge_configure_v1(
    b: Optional[CalcodeTableCursorBridgeV1],
    table: Optional[CalcodeNumericalTableV1],
    analysis: Optional[CalcodeSyncAnalysisV1],
) -> int:
    """int calcode_table_cursor_bridge_configure_v1(CalcodeTableCursorBridgeV1 *b,
        CalcodeNumericalTableV1 *table, CalcodeSyncAnalysisV1 *analysis);"""
    if (
        b is None
        or table is None
        or analysis is None
        or not table.valid
        or not analysis.valid
    ):
        return 0

    calcode_table_cursor_bridge_init_v1(b)

    b.table = table
    b.analysis = analysis
    b.valid = 1

    return 1


def calcode_table_cursor_bridge_select_row_v1(
    b: Optional[CalcodeTableCursorBridgeV1], row: int
) -> int:
    """int calcode_table_cursor_bridge_select_row_v1(CalcodeTableCursorBridgeV1 *b,
        int row);"""
    if b is None or not b.valid or b.table is None or b.analysis is None:
        return 0

    if row < 0 or row >= b.analysis.trajectory.sample_count:
        b.diagnostic = f"table row {row} outside trajectory"
        return 0

    if not calcode_sync_analysis_set_index_v1(b.analysis, row):
        b.diagnostic = "analysis rejected table row"
        return 0

    b.table.selected_row = row
    b.last_row = row

    return 1
