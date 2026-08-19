"""calcode_graph_decimation_v1.py -- exact Python port of
calcode_graph_decimation_v1.c / calcode_graph_decimation_v1.h.

Original: builds a (possibly strided/decimated) polyline copy of a
CalcodeGraphModelV1's points, always keeping the final point even if
it doesn't land on the stride, for cheap graph rendering.

PORT NOTES:

- `calcode_graph_polyline_copy_v1` is just `stride_v1(p, g, 1)` --
  reproduced as a direct call-through, not reimplemented.
- `calcode_graph_polyline_stride_v1` computes `count = ceil(point_count
  / stride)` via the C's integer-division idiom `(point_count + stride
  - 1) / stride`, then bumps `count` by one more slot up front *if* the
  last sampled index (`(count-1)*stride`) won't land exactly on
  `point_count - 1` -- reproduced with the same pre-allocation sizing
  logic (Python's list is pre-sized to `count` via this same formula,
  not grown dynamically), so the allocation-failure path has no direct
  Python analogue but the *count* arithmetic itself is reproduced
  exactly for behavioral parity of `point_count` afterward.
- The main loop copies every `stride`-th point by (shallow, value)
  copy -- `CalcodeGraphPointV1` is a plain `(x, y)` pair, so a Python
  copy constructs a new point with the same `x`/`y` rather than
  aliasing the source object, matching the C struct-assignment-by-
  value semantics (`p->points[output++] = g->points[i];`).
- The final dedup/append check compares `x`/`y` by exact equality
  (`!=`) against the model's true last point -- reproduced with
  Python's `!=` on the floats (no epsilon), matching the C exactly:
  a stride that happens to land exactly on the last index does *not*
  get a duplicate appended, any other case does.
- Guard order preserved: `p`/`g` None, `g.valid` false, `g.points`
  empty, `stride <= 0` all short-circuit to 0 before any mutation of
  `p` -- `p` is left completely untouched on any of these, matching
  C's early `return 0` before `calcode_graph_polyline_free_v1(p)` is
  ever called.
"""

from __future__ import annotations

from typing import Optional

from calcy.symbolic.symbolic_parser_v1 import CALCODE_SYMBOLIC_MAX_ERROR_V1
from calcy.graph.graph_model_v1 import CalcodeGraphModelV1, CalcodeGraphPointV1


class CalcodeGraphPolylineV1:
    """typedef struct CalcodeGraphPolylineV1 { ... } CalcodeGraphPolylineV1."""
    __slots__ = ("valid", "point_count", "points", "diagnostic")

    def __init__(self):
        self.valid = 0
        self.point_count = 0
        self.points: list[CalcodeGraphPointV1] = []
        self.diagnostic = ""


def _diagnostic_v1(p: Optional[CalcodeGraphPolylineV1], message: Optional[str]) -> None:
    if p is None:
        return
    p.diagnostic = (message if message is not None else "graph polyline error")[
        :CALCODE_SYMBOLIC_MAX_ERROR_V1 - 1]


def calcode_graph_polyline_init_v1(p: Optional[CalcodeGraphPolylineV1]) -> None:
    if p is None:
        return
    p.valid = 0
    p.point_count = 0
    p.points = []
    p.diagnostic = ""


def calcode_graph_polyline_free_v1(p: Optional[CalcodeGraphPolylineV1]) -> None:
    if p is None:
        return
    p.points = []
    p.point_count = 0
    p.valid = 0


def calcode_graph_polyline_copy_v1(
        p: Optional[CalcodeGraphPolylineV1],
        g: Optional[CalcodeGraphModelV1]) -> int:
    return calcode_graph_polyline_stride_v1(p, g, 1)


def calcode_graph_polyline_stride_v1(
        p: Optional[CalcodeGraphPolylineV1],
        g: Optional[CalcodeGraphModelV1],
        stride: int) -> int:
    if (p is None or g is None or not g.valid or
            not g.points or stride <= 0):
        return 0

    calcode_graph_polyline_free_v1(p)
    calcode_graph_polyline_init_v1(p)

    count = (g.point_count + stride - 1) // stride

    if count <= 0:
        return 0

    # Always retain the final point. This is important for a plotted
    # trajectory whose last sample is not an exact multiple of stride.
    last = g.point_count - 1

    if (count - 1) * stride != last:
        count += 1

    points = [CalcodeGraphPointV1() for _ in range(count)]

    output = 0
    i = 0
    while i < g.point_count:
        src = g.points[i]
        points[output] = CalcodeGraphPointV1(src.x, src.y)
        output += 1
        i += stride

    last_model_point = g.points[g.point_count - 1]

    if (output == 0 or
            points[output - 1].x != last_model_point.x or
            points[output - 1].y != last_model_point.y):
        points[output] = CalcodeGraphPointV1(last_model_point.x, last_model_point.y)
        output += 1

    p.points = points[:output]
    p.point_count = output
    p.valid = 1

    return 1
