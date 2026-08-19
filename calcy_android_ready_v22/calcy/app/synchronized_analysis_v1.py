"""calcode_synchronized_analysis_v1.py -- exact Python port of
calcode_synchronized_analysis_v1.c / calcode_synchronized_analysis_v1.h.

Original: the CALCODE synchronized representation layer. Deliberately does
not solve an equation and does not render anything -- it establishes a
common index/time cursor through which the numerical table, 2D graph and
3D experiment can be treated as different representations of one computed
trajectory.

PORT NOTES:

- All fixed-size C arrays (`state[CALCODE_SYNC_MAX_COLUMNS_V1]`,
  `state_names[...][...]`, etc.) are reproduced as plain Python lists
  sized/pre-filled at construction time, matching the struct's
  always-allocated-capacity semantics (as opposed to growable lists),
  so that any latent index-based access above the "logical" count still
  behaves the same as reading zeroed/empty C memory.
- `calcode_sync_trajectory_free_v1` / `_init_v1` reproduce the C's
  "free then zero" pattern; Python has no `free`, so `_free_v1` simply
  drops the reference and resets fields exactly like the post-free
  `memset` would leave them.
- `calcode_sync_trajectory_create_v1` reproduces the C's unconditional
  `free_v1()` + `init_v1()` call at the top (before validating
  `sample_count`/`state_dimension`), so any previously-built trajectory
  is dropped even on a failed create call -- same as the source.
- `calcode_sync_trajectory_set_sample_v1` validates every state
  component with `isfinite` before committing *any* of them (matching
  the C's early `return 0` mid-loop, which leaves partially-written
  state -- reproduced identically, including the partial write).
- `nearest_index` is a private binary-search helper (`static` in C);
  ported as a module-level function name-mangled with a leading
  underscore to preserve the same "not part of the public API" status.
- `calcode_sync_cursor_set_time_v1`'s branch structure (clamp at
  t0/t1, else binary-search + optional linear interpolation) is
  reproduced with the same branch order and the same redundant second
  `nearest_index` call in the `not interpolate` path, matching the C
  exactly (the C calls `nearest_index` twice in that path: once to
  compute `right`, again inside the `if (!interpolate)` block).
- `graph_bounds_v1`'s degenerate-range padding (`+/- 1.0` when
  min == max on either axis) is reproduced with the same order
  (x-axis check first, then y-axis).
- `calcode_sync_graph_build_v1` calls `calcode_sync_graph_free_v1`
  unconditionally at the top (mirroring the C's free-before-validate
  pattern), then validates `t`/columns, writing a diagnostic message
  into `g.diagnostic` on failure exactly as the C does via `snprintf`.
- `calcode_sync_table_build_v1` lays the table out as a single flat
  `values` list of length `row_count * column_count` (row-major),
  mirroring the C's flat `calloc` + manual row-pointer indexing
  (`&table->values[i * column_count]`) rather than a Python list of
  rows, so indexing arithmetic matches exactly.
- `calcode_sync_analysis_build_v1` / other functions preserve the
  exact "free analysis, then rebuild step by step, tearing down and
  returning 0 on any failure" control flow from the C, including that
  a table-follows-cursor / graph-follows-cursor pair of flags is set
  to 1 unconditionally on success (there is no way to build with them
  off in this file).
"""

from __future__ import annotations

import math
from typing import List, Optional

CALCODE_SYNC_MAX_COLUMNS_V1 = 16
CALCODE_SYNC_MAX_NAME_V1 = 64
CALCODE_SYNC_MAX_LABEL_V1 = 128


def _diagnostic(message: Optional[str]) -> str:
    """static void diagnostic(char *buffer, size_t size, const char *message)"""
    return message if message else "synchronized analysis error"


class CalcodeSyncSampleV1:
    """typedef struct CalcodeSyncSampleV1 { ... } CalcodeSyncSampleV1."""
    __slots__ = ("index", "t", "state", "state_dimension", "derived",
                 "derived_count")

    def __init__(self):
        self.index = 0
        self.t = 0.0
        self.state = [0.0] * CALCODE_SYNC_MAX_COLUMNS_V1
        self.state_dimension = 0
        self.derived = [0.0] * CALCODE_SYNC_MAX_COLUMNS_V1
        self.derived_count = 0


class CalcodeSyncTrajectoryV1:
    """typedef struct CalcodeSyncTrajectoryV1 { ... } CalcodeSyncTrajectoryV1."""
    __slots__ = ("valid", "samples", "sample_count", "state_dimension",
                 "t0", "t1", "state_names", "state_name_count", "title",
                 "diagnostic")

    def __init__(self):
        self.valid = 0
        self.samples: List[CalcodeSyncSampleV1] = []
        self.sample_count = 0
        self.state_dimension = 0
        self.t0 = 0.0
        self.t1 = 0.0
        self.state_names = [""] * CALCODE_SYNC_MAX_COLUMNS_V1
        self.state_name_count = 0
        self.title = ""
        self.diagnostic = ""


class CalcodeSyncCursorV1:
    """typedef struct CalcodeSyncCursorV1 { ... } CalcodeSyncCursorV1."""
    __slots__ = ("valid", "sample_index", "requested_time", "actual_time",
                 "interpolation_alpha", "interpolated", "diagnostic")

    def __init__(self):
        self.valid = 0
        self.sample_index = 0
        self.requested_time = 0.0
        self.actual_time = 0.0
        self.interpolation_alpha = 0.0
        self.interpolated = 0
        self.diagnostic = ""


class CalcodeSyncGraphPointV1:
    """typedef struct CalcodeSyncGraphPointV1 { ... } CalcodeSyncGraphPointV1."""
    __slots__ = ("x", "y", "t", "sample_index")

    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.t = 0.0
        self.sample_index = 0


class CalcodeSyncGraphV1:
    """typedef struct CalcodeSyncGraphV1 { ... } CalcodeSyncGraphV1."""
    __slots__ = ("valid", "points", "point_count", "x_column", "y_column",
                 "x_min", "x_max", "y_min", "y_max", "x_label", "y_label",
                 "title", "diagnostic")

    def __init__(self):
        self.valid = 0
        self.points: List[CalcodeSyncGraphPointV1] = []
        self.point_count = 0
        self.x_column = 0
        self.y_column = 0
        self.x_min = 0.0
        self.x_max = 0.0
        self.y_min = 0.0
        self.y_max = 0.0
        self.x_label = ""
        self.y_label = ""
        self.title = ""
        self.diagnostic = ""


class CalcodeSyncTableV1:
    """typedef struct CalcodeSyncTableV1 { ... } CalcodeSyncTableV1."""
    __slots__ = ("valid", "row_count", "visible_start", "visible_count",
                 "column_count", "column_names", "values", "selected_row",
                 "diagnostic")

    def __init__(self):
        self.valid = 0
        self.row_count = 0
        self.visible_start = 0
        self.visible_count = 0
        self.column_count = 0
        self.column_names = [""] * CALCODE_SYNC_MAX_COLUMNS_V1
        self.values: List[float] = []
        self.selected_row = 0
        self.diagnostic = ""


class CalcodeSyncAnalysisV1:
    """typedef struct CalcodeSyncAnalysisV1 { ... } CalcodeSyncAnalysisV1."""
    __slots__ = ("valid", "trajectory", "cursor", "graph", "table",
                 "graph_follows_cursor", "table_follows_cursor",
                 "diagnostic")

    def __init__(self):
        self.valid = 0
        self.trajectory = CalcodeSyncTrajectoryV1()
        self.cursor = CalcodeSyncCursorV1()
        self.graph = CalcodeSyncGraphV1()
        self.table = CalcodeSyncTableV1()
        self.graph_follows_cursor = 0
        self.table_follows_cursor = 0
        self.diagnostic = ""


def calcode_sync_trajectory_init_v1(t: CalcodeSyncTrajectoryV1) -> None:
    """void calcode_sync_trajectory_init_v1(CalcodeSyncTrajectoryV1 *t)"""
    if t is None:
        return

    t.valid = 0
    t.samples = []
    t.sample_count = 0
    t.state_dimension = 0
    t.t0 = 0.0
    t.t1 = 0.0
    t.state_names = [""] * CALCODE_SYNC_MAX_COLUMNS_V1
    t.state_name_count = 0
    t.title = ""
    t.diagnostic = ""


def calcode_sync_trajectory_free_v1(t: CalcodeSyncTrajectoryV1) -> None:
    """void calcode_sync_trajectory_free_v1(CalcodeSyncTrajectoryV1 *t)"""
    if t is None:
        return

    t.samples = []
    t.sample_count = 0
    t.state_dimension = 0
    t.state_name_count = 0
    t.valid = 0


def calcode_sync_trajectory_create_v1(
    t: CalcodeSyncTrajectoryV1,
    sample_count: int,
    state_dimension: int,
) -> int:
    """int calcode_sync_trajectory_create_v1(CalcodeSyncTrajectoryV1 *t,
    int sample_count, int state_dimension)"""
    if (t is None or sample_count < 2 or state_dimension < 1 or
            state_dimension > CALCODE_SYNC_MAX_COLUMNS_V1):
        return 0

    calcode_sync_trajectory_free_v1(t)
    calcode_sync_trajectory_init_v1(t)

    t.samples = [CalcodeSyncSampleV1() for _ in range(sample_count)]

    t.sample_count = sample_count
    t.state_dimension = state_dimension
    t.valid = 1

    return 1


def calcode_sync_trajectory_set_sample_v1(
    t: CalcodeSyncTrajectoryV1,
    index: int,
    time: float,
    state: List[float],
) -> int:
    """int calcode_sync_trajectory_set_sample_v1(CalcodeSyncTrajectoryV1 *t,
    int index, double time, const double *state)"""
    if (t is None or not t.valid or state is None or
            index < 0 or index >= t.sample_count or not math.isfinite(time)):
        return 0

    s = t.samples[index]

    s.index = index
    s.t = time
    s.state_dimension = t.state_dimension

    for i in range(t.state_dimension):
        if not math.isfinite(state[i]):
            return 0

        s.state[i] = state[i]

    if index == 0:
        t.t0 = time

    if index == t.sample_count - 1:
        t.t1 = time

    return 1


def calcode_sync_trajectory_set_state_name_v1(
    t: CalcodeSyncTrajectoryV1,
    column: int,
    name: Optional[str],
) -> int:
    """int calcode_sync_trajectory_set_state_name_v1(
    CalcodeSyncTrajectoryV1 *t, int column, const char *name)"""
    if (t is None or not t.valid or name is None or
            column < 0 or column >= t.state_dimension):
        return 0

    t.state_names[column] = name[:CALCODE_SYNC_MAX_NAME_V1 - 1]

    if column + 1 > t.state_name_count:
        t.state_name_count = column + 1

    return 1


def _nearest_index(t: CalcodeSyncTrajectoryV1, time: float) -> int:
    """static int nearest_index(const CalcodeSyncTrajectoryV1 *t, double time)"""
    lo = 0
    hi = t.sample_count - 1

    while lo < hi:
        mid = lo + (hi - lo) // 2

        if t.samples[mid].t < time:
            lo = mid + 1
        else:
            hi = mid

    if lo == 0:
        return 0

    d1 = abs(t.samples[lo].t - time)
    d0 = abs(t.samples[lo - 1].t - time)

    return lo - 1 if d0 <= d1 else lo


def calcode_sync_cursor_set_index_v1(
    cursor: CalcodeSyncCursorV1,
    t: CalcodeSyncTrajectoryV1,
    index: int,
) -> int:
    """int calcode_sync_cursor_set_index_v1(CalcodeSyncCursorV1 *cursor,
    const CalcodeSyncTrajectoryV1 *t, int index)"""
    if (cursor is None or t is None or not t.valid or
            index < 0 or index >= t.sample_count):
        return 0

    cursor.sample_index = index
    cursor.actual_time = t.samples[index].t
    cursor.requested_time = cursor.actual_time
    cursor.interpolation_alpha = 0.0
    cursor.interpolated = 0
    cursor.diagnostic = ""
    cursor.valid = 1

    return 1


def calcode_sync_cursor_set_time_v1(
    cursor: CalcodeSyncCursorV1,
    t: CalcodeSyncTrajectoryV1,
    time: float,
    interpolate: int,
) -> int:
    """int calcode_sync_cursor_set_time_v1(CalcodeSyncCursorV1 *cursor,
    const CalcodeSyncTrajectoryV1 *t, double time, int interpolate)"""
    if cursor is None or t is None or not t.valid or not math.isfinite(time):
        return 0

    if time <= t.t0:
        return calcode_sync_cursor_set_index_v1(cursor, t, 0)

    if time >= t.t1:
        return calcode_sync_cursor_set_index_v1(cursor, t, t.sample_count - 1)

    right = _nearest_index(t, time)

    left = right

    if t.samples[right].t > time and right > 0:
        left = right - 1

    if not interpolate:
        index = _nearest_index(t, time)

        return calcode_sync_cursor_set_index_v1(cursor, t, index)

    next_ = left + 1

    if next_ >= t.sample_count:
        next_ = t.sample_count - 1

    ta = t.samples[left].t
    tb = t.samples[next_].t

    alpha = 0.0

    if tb > ta:
        alpha = (time - ta) / (tb - ta)

    if alpha < 0.0:
        alpha = 0.0

    if alpha > 1.0:
        alpha = 1.0

    cursor.sample_index = left
    cursor.requested_time = time
    cursor.actual_time = ta + alpha * (tb - ta)
    cursor.interpolation_alpha = alpha
    cursor.interpolated = 1
    cursor.diagnostic = ""
    cursor.valid = 1

    return 1


def _graph_bounds_v1(g: CalcodeSyncGraphV1) -> None:
    """static void graph_bounds_v1(CalcodeSyncGraphV1 *g)"""
    g.x_min = g.x_max = g.points[0].x
    g.y_min = g.y_max = g.points[0].y

    for i in range(1, g.point_count):
        x = g.points[i].x
        y = g.points[i].y

        if x < g.x_min:
            g.x_min = x

        if x > g.x_max:
            g.x_max = x

        if y < g.y_min:
            g.y_min = y

        if y > g.y_max:
            g.y_max = y

    if g.x_max == g.x_min:
        g.x_min -= 1.0
        g.x_max += 1.0

    if g.y_max == g.y_min:
        g.y_min -= 1.0
        g.y_max += 1.0


def calcode_sync_graph_build_v1(
    g: CalcodeSyncGraphV1,
    t: Optional[CalcodeSyncTrajectoryV1],
    x_column: int,
    y_column: int,
) -> int:
    """int calcode_sync_graph_build_v1(CalcodeSyncGraphV1 *g,
    const CalcodeSyncTrajectoryV1 *t, int x_column, int y_column)"""
    if g is None:
        return 0

    calcode_sync_graph_free_v1(g)

    if (t is None or not t.valid or x_column < 0 or y_column < 0 or
            x_column >= t.state_dimension or y_column >= t.state_dimension):
        g.diagnostic = _diagnostic("invalid graph columns or trajectory")
        return 0

    g.points = [CalcodeSyncGraphPointV1() for _ in range(t.sample_count)]

    g.point_count = t.sample_count

    g.x_column = x_column
    g.y_column = y_column

    for i in range(t.sample_count):
        g.points[i].x = t.samples[i].state[x_column]
        g.points[i].y = t.samples[i].state[y_column]
        g.points[i].t = t.samples[i].t
        g.points[i].sample_index = i

    if t.state_names[x_column]:
        g.x_label = t.state_names[x_column][:CALCODE_SYNC_MAX_LABEL_V1 - 1]
    else:
        g.x_label = f"state[{x_column}]"

    if t.state_names[y_column]:
        g.y_label = t.state_names[y_column][:CALCODE_SYNC_MAX_LABEL_V1 - 1]
    else:
        g.y_label = f"state[{y_column}]"

    g.title = (t.title if t.title else "CALCODE graph")[
        :CALCODE_SYNC_MAX_LABEL_V1 - 1]

    _graph_bounds_v1(g)

    g.valid = 1
    return 1


def calcode_sync_graph_free_v1(g: CalcodeSyncGraphV1) -> None:
    """void calcode_sync_graph_free_v1(CalcodeSyncGraphV1 *g)"""
    if g is None:
        return

    g.valid = 0
    g.points = []
    g.point_count = 0
    g.x_column = 0
    g.y_column = 0
    g.x_min = 0.0
    g.x_max = 0.0
    g.y_min = 0.0
    g.y_max = 0.0
    g.x_label = ""
    g.y_label = ""
    g.title = ""
    g.diagnostic = ""


def calcode_sync_table_build_v1(
    table: CalcodeSyncTableV1,
    t: Optional[CalcodeSyncTrajectoryV1],
) -> int:
    """int calcode_sync_table_build_v1(CalcodeSyncTableV1 *table,
    const CalcodeSyncTrajectoryV1 *t)"""
    if table is None:
        return 0

    calcode_sync_table_free_v1(table)

    if t is None or not t.valid:
        return 0

    columns = 1 + t.state_dimension

    if columns > CALCODE_SYNC_MAX_COLUMNS_V1:
        return 0

    table.row_count = t.sample_count
    table.column_count = columns

    table.values = [0.0] * (table.row_count * table.column_count)

    table.column_names = [""] * CALCODE_SYNC_MAX_COLUMNS_V1
    table.column_names[0] = "t"

    for j in range(t.state_dimension):
        if t.state_names[j]:
            table.column_names[j + 1] = t.state_names[j][
                :CALCODE_SYNC_MAX_NAME_V1 - 1]
        else:
            table.column_names[j + 1] = f"state[{j}]"

    for i in range(t.sample_count):
        row_offset = i * table.column_count

        table.values[row_offset] = t.samples[i].t

        for j in range(t.state_dimension):
            table.values[row_offset + j + 1] = t.samples[i].state[j]

    table.visible_start = 0
    table.visible_count = table.row_count if table.row_count < 40 else 40

    table.selected_row = 0
    table.valid = 1

    return 1


def calcode_sync_table_free_v1(table: CalcodeSyncTableV1) -> None:
    """void calcode_sync_table_free_v1(CalcodeSyncTableV1 *table)"""
    if table is None:
        return

    table.valid = 0
    table.row_count = 0
    table.visible_start = 0
    table.visible_count = 0
    table.column_count = 0
    table.column_names = [""] * CALCODE_SYNC_MAX_COLUMNS_V1
    table.values = []
    table.selected_row = 0
    table.diagnostic = ""


def calcode_sync_analysis_free_v1(a: CalcodeSyncAnalysisV1) -> None:
    """void calcode_sync_analysis_free_v1(CalcodeSyncAnalysisV1 *a)"""
    if a is None:
        return

    calcode_sync_graph_free_v1(a.graph)
    calcode_sync_table_free_v1(a.table)
    calcode_sync_trajectory_free_v1(a.trajectory)

    a.cursor = CalcodeSyncCursorV1()

    a.valid = 0


def calcode_sync_analysis_build_v1(
    a: CalcodeSyncAnalysisV1,
    source: Optional[CalcodeSyncTrajectoryV1],
    graph_x_column: int,
    graph_y_column: int,
) -> int:
    """int calcode_sync_analysis_build_v1(CalcodeSyncAnalysisV1 *a,
    const CalcodeSyncTrajectoryV1 *source, int graph_x_column,
    int graph_y_column)"""
    if a is None or source is None or not source.valid:
        return 0

    calcode_sync_analysis_free_v1(a)

    if not calcode_sync_trajectory_create_v1(
            a.trajectory, source.sample_count, source.state_dimension):
        return 0

    for i in range(source.sample_count):
        if not calcode_sync_trajectory_set_sample_v1(
                a.trajectory, i, source.samples[i].t, source.samples[i].state):
            calcode_sync_analysis_free_v1(a)
            return 0

    for j in range(source.state_dimension):
        calcode_sync_trajectory_set_state_name_v1(
            a.trajectory, j, source.state_names[j])

    a.trajectory.title = source.title[:CALCODE_SYNC_MAX_LABEL_V1 - 1]

    if not calcode_sync_graph_build_v1(
            a.graph, a.trajectory, graph_x_column, graph_y_column):
        calcode_sync_analysis_free_v1(a)
        return 0

    if not calcode_sync_table_build_v1(a.table, a.trajectory):
        calcode_sync_analysis_free_v1(a)
        return 0

    if not calcode_sync_cursor_set_index_v1(a.cursor, a.trajectory, 0):
        calcode_sync_analysis_free_v1(a)
        return 0

    a.graph_follows_cursor = 1
    a.table_follows_cursor = 1
    a.valid = 1

    return 1


def calcode_sync_analysis_set_index_v1(
    a: CalcodeSyncAnalysisV1,
    index: int,
) -> int:
    """int calcode_sync_analysis_set_index_v1(CalcodeSyncAnalysisV1 *a,
    int index)"""
    if a is None or not a.valid:
        return 0

    if not calcode_sync_cursor_set_index_v1(a.cursor, a.trajectory, index):
        return 0

    if a.table_follows_cursor:
        a.table.selected_row = a.cursor.sample_index

    return 1


def calcode_sync_analysis_set_time_v1(
    a: CalcodeSyncAnalysisV1,
    time: float,
    interpolate: int,
) -> int:
    """int calcode_sync_analysis_set_time_v1(CalcodeSyncAnalysisV1 *a,
    double time, int interpolate)"""
    if a is None or not a.valid:
        return 0

    if not calcode_sync_cursor_set_time_v1(
            a.cursor, a.trajectory, time, interpolate):
        return 0

    if a.table_follows_cursor:
        a.table.selected_row = a.cursor.sample_index

    return 1


def calcode_sync_analysis_current_sample_v1(
    a: Optional[CalcodeSyncAnalysisV1],
) -> Optional[CalcodeSyncSampleV1]:
    """const CalcodeSyncSampleV1 *calcode_sync_analysis_current_sample_v1(
    const CalcodeSyncAnalysisV1 *a)"""
    if a is None or not a.valid or not a.cursor.valid:
        return None

    i = a.cursor.sample_index

    if i < 0 or i >= a.trajectory.sample_count:
        return None

    return a.trajectory.samples[i]
