"""calcode_cursor_consistency_v1.py -- exact Python port of
calcode_cursor_consistency_v1.c / calcode_cursor_consistency_v1.h.

Original: cross-checks the table's selected row and the 3D scene's
current sample index against the synchronized analysis's own common
cursor, producing a small diagnostic report -- part of the "click
table or graph and everything updates" unified-view consistency
layer described in section 4 of `REMAINING_PYTHON_PORT_WORK.md`.

PORT STATUS -- harness-verified bit-exact against a compiled `gcc -O2`
build of the real C (verification_harnesses/harness_cursor_consistency.c/.py),
diffed field-by-field across 12 cases covering NULL report, NULL
analysis, invalid analysis, invalid cursor, full consistency, table-only/
scene-only/both mismatches, negative ("not applicable") indices on
either or both sides, and analysis_index itself being -1. Zero diff.

PORT NOTES:

- `table_selected_row` / `scene_sample_index` are plain `int`
  parameters in the C (not pointers), so they translate directly to
  Python `int` parameters -- no mutable-box wrapping needed.
- `report->analysis_index` is set to `-1` both as the initial
  "unknown" sentinel (before `analysis`/`analysis->valid` is checked)
  and again, distinctly, when `analysis->cursor.valid` is false --
  reproduced as the same literal `-1` in both places, matching the
  C's two separate assignments rather than collapsing them into one.
- `mismatch_count` only increments for `table_selected_row`/
  `scene_sample_index` values that are `>= 0` -- a negative value
  (e.g. "no selection") is treated as "not applicable", not as a
  mismatch. Reproduced exactly.
"""

from __future__ import annotations

from typing import Optional

from calcy.app.synchronized_analysis_v1 import CalcodeSyncAnalysisV1


class CalcodeCursorConsistencyReportV1:
    """typedef struct CalcodeCursorConsistencyReportV1 { ... }"""
    __slots__ = (
        "valid", "consistent",
        "analysis_index", "table_index", "scene_index",
        "mismatch_count", "diagnostic",
    )

    def __init__(self):
        self.valid = 0
        self.consistent = 0
        self.analysis_index = 0
        self.table_index = 0
        self.scene_index = 0
        self.mismatch_count = 0
        self.diagnostic = ""


def calcode_cursor_consistency_check_v1(
    analysis: Optional[CalcodeSyncAnalysisV1],
    table_selected_row: int,
    scene_sample_index: int,
    report: Optional[CalcodeCursorConsistencyReportV1],
) -> int:
    """int calcode_cursor_consistency_check_v1(const CalcodeSyncAnalysisV1 *analysis,
        int table_selected_row, int scene_sample_index,
        CalcodeCursorConsistencyReportV1 *report);"""
    if report is None:
        return 0

    # memset(report, 0, sizeof(*report));
    report.valid = 0
    report.consistent = 0
    report.analysis_index = 0
    report.table_index = 0
    report.scene_index = 0
    report.mismatch_count = 0
    report.diagnostic = ""

    report.analysis_index = -1
    report.table_index = table_selected_row
    report.scene_index = scene_sample_index

    if analysis is None or not analysis.valid:
        report.diagnostic = "analysis is invalid"
        return 0

    report.analysis_index = (
        analysis.cursor.sample_index if analysis.cursor.valid else -1
    )

    if not analysis.cursor.valid:
        report.diagnostic = "common cursor is invalid"
        return 0

    if table_selected_row >= 0 and table_selected_row != report.analysis_index:
        report.mismatch_count += 1

    if scene_sample_index >= 0 and scene_sample_index != report.analysis_index:
        report.mismatch_count += 1

    report.consistent = 1 if report.mismatch_count == 0 else 0

    report.valid = 1

    if report.consistent:
        report.diagnostic = f"all supplied views reference sample {report.analysis_index}"
    else:
        report.diagnostic = (
            f"cursor mismatch: analysis={report.analysis_index} "
            f"table={report.table_index} scene={report.scene_index}"
        )

    return 1
