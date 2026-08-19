
from __future__ import annotations

import math
from typing import Callable, Sequence

from kivy.graphics import Color, Line, Rectangle, Ellipse
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.widget import Widget


class PlotWidget(Widget):
    """Interactive scientific 2D trajectory plot.

    The widget consumes the already-solved Calcy trajectory. It never
    performs numerical integration itself.
    """
    cursor_index = NumericProperty(-1)

    def __init__(self, on_cursor: Callable[[int], None] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.on_cursor = on_cursor
        self.data_x: list[float] = []
        self.data_states: list[list[float]] = []
        self.active_state = 0
        self.mode = "Time series"

        # The graph is deliberately a navigable numerical plane.  These are
        # view parameters only; the solved samples are never changed.
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._zoom = 1.0
        self._touch_start = None
        self._last_touch = None
        self._active_touches = {}
        self._pinch_distance = None
        self._pinch_center = None

        self._state_colors = [
            (0.10, 0.75, 1.00, 1),
            (1.00, 0.45, 0.20, 1),
            (0.55, 1.00, 0.35, 1),
            (0.85, 0.45, 1.00, 1),
            (1.00, 0.85, 0.20, 1),
        ]
        self._info = Label(
            text="",
            size_hint=(None, None),
            size=(260, 52),
            font_size="13sp",
            color=(0.95, 0.97, 1, 1),
            halign="left",
            valign="top",
        )
        self.add_widget(self._info)
        self.bind(pos=self._redraw, size=self._redraw)
        self.bind(cursor_index=self._redraw)

    def set_data(self, x: Sequence[float], states: Sequence[Sequence[float]]) -> None:
        self.data_x = list(x)
        self.data_states = [list(s) for s in states]
        self.active_state = min(self.active_state, max(0, len(self.data_states) - 1))
        self._pan_x = self._pan_y = 0.0
        self._zoom = 1.0
        self.cursor_index = 0 if self.data_x else -1
        self._redraw()

    def set_state(self, index: int) -> None:
        if self.data_states:
            self.active_state = max(0, min(index, len(self.data_states) - 1))
            self._redraw()

    def set_mode(self, mode: str) -> None:
        allowed = {"Time series", "All states", "Phase portrait", "Derivative"}
        self.mode = mode if mode in allowed else "Time series"
        self._pan_x = self._pan_y = 0.0
        self._zoom = 1.0
        self._redraw()

    def _series_for_mode(self):
        if self.mode == "Phase portrait" and len(self.data_states) >= 2:
            return list(self.data_states[0]), list(self.data_states[1]), "y1", "y2"
        if self.mode == "Derivative" and self.data_states and self.data_x:
            y = self.data_states[self.active_state]
            d = []
            for i in range(len(y)):
                if i == 0:
                    dt = self.data_x[1] - self.data_x[0] if len(y) > 1 else 1.0
                    d.append((y[1] - y[0]) / max(dt, 1e-30) if len(y) > 1 else 0.0)
                elif i == len(y)-1:
                    dt = self.data_x[i] - self.data_x[i-1]
                    d.append((y[i] - y[i-1]) / max(dt, 1e-30))
                else:
                    dt = self.data_x[i+1] - self.data_x[i-1]
                    d.append((y[i+1] - y[i-1]) / max(dt, 1e-30))
            return list(self.data_x), d, "t", f"dy{self.active_state+1}/dt"
        if self.mode == "All states":
            return list(self.data_x), None, "t", "states"
        return list(self.data_x), list(self.data_states[self.active_state]) if self.data_states else [], "t", f"y{self.active_state+1}"

    def _bounds(self):
        if not self.data_x or not self.data_states:
            return 0.0, 1.0, -1.0, 1.0
        y = self.data_states[self.active_state]
        xmin, xmax = min(self.data_x), max(self.data_x)
        ymin, ymax = min(y), max(y)
        if math.isclose(xmin, xmax):
            xmin, xmax = xmin - 1.0, xmax + 1.0
        if math.isclose(ymin, ymax):
            pad = max(abs(ymin) * 0.1, 1.0)
        else:
            pad = (ymax - ymin) * 0.08
        return xmin, xmax, ymin - pad, ymax + pad

    def _view(self):
        if self.mode == "Phase portrait" and len(self.data_states) >= 2:
            xmin, xmax = min(self.data_states[0]), max(self.data_states[0])
            ymin, ymax = min(self.data_states[1]), max(self.data_states[1])
            if math.isclose(xmin, xmax): xmin, xmax = xmin-1, xmax+1
            if math.isclose(ymin, ymax): ymin, ymax = ymin-1, ymax+1
            px = max((xmax-xmin)*0.08, 1e-9); py = max((ymax-ymin)*0.08, 1e-9)
            return xmin-px, xmax+px, ymin-py, ymax+py
        if self.mode == "Derivative":
            x = self.data_x
            y = self._series_for_mode()[1] if x else []
            if not x or not y: return 0,1,-1,1
            xmin,xmax=min(x),max(x); ymin,ymax=min(y),max(y)
            pad=max((ymax-ymin)*0.08,1e-9)
            return xmin,xmax,ymin-pad,ymax+pad
        xmin, xmax, ymin, ymax = self._bounds()
        if self.mode == "All states" and self.data_states:
            vals=[v for series in self.data_states for v in series]
            ymin,ymax=min(vals),max(vals); pad=max((ymax-ymin)*0.08,1.0)
            ymin, ymax = ymin-pad, ymax+pad

        # Zoom is applied about the centre of the numerical view, while pan
        # moves that view without touching the underlying solution.
        cx, cy = (xmin + xmax) * 0.5, (ymin + ymax) * 0.5
        hx = (xmax - xmin) / (2.0 * self._zoom)
        hy = (ymax - ymin) / (2.0 * self._zoom)
        return (cx - hx + self._pan_x, cx + hx + self._pan_x,
                cy - hy + self._pan_y, cy + hy + self._pan_y)

    def reset_view(self) -> None:
        self._pan_x = self._pan_y = 0.0
        self._zoom = 1.0
        self._redraw()

    def _zoom_at(self, factor: float, screen_x: float, screen_y: float) -> None:
        if not self.data_x or not self.data_states:
            return
        old_view = self._view()
        ox0, ox1, oy0, oy1 = old_view
        fx = max(0.0, min(1.0, (screen_x - self.x) / max(self.width, 1.0)))
        fy = max(0.0, min(1.0, (screen_y - self.y) / max(self.height, 1.0)))
        world_x = ox0 + fx * (ox1 - ox0)
        world_y = oy0 + fy * (oy1 - oy0)

        new_zoom = max(0.01, min(500.0, self._zoom * factor))
        self._zoom = new_zoom

        # Keep the point below the pointer fixed while zooming.
        base = self._view()
        bx0, bx1, by0, by1 = base
        nx = bx0 + fx * (bx1 - bx0)
        ny = by0 + fy * (by1 - by0)
        self._pan_x += world_x - nx
        self._pan_y += world_y - ny
        self._redraw()

    def _redraw(self, *_args):
        self.canvas.clear()
        self._info.pos = (self.x + 10, self.top - 62)
        with self.canvas:
            Color(0.035, 0.045, 0.065, 1)
            Rectangle(pos=self.pos, size=self.size)
            if not self.data_x or not self.data_states or self.width < 30 or self.height < 30:
                return

            xmin, xmax, ymin, ymax = self._view()

            def sx(v):
                return self.x + (v - xmin) / max(xmax - xmin, 1e-30) * self.width

            def sy(v):
                return self.y + (v - ymin) / max(ymax - ymin, 1e-30) * self.height

            # scientific grid
            Color(0.18, 0.20, 0.25, 1)
            for frac in (0.0, .25, .5, .75, 1.0):
                yy = self.y + frac * self.height
                xx = self.x + frac * self.width
                Line(points=[self.x, yy, self.right, yy], width=0.7)
                Line(points=[xx, self.y, xx, self.top], width=0.7)

            # axes at x=0 and y=0 when visible
            Color(0.55, 0.58, 0.64, 1)
            if xmin <= 0 <= xmax:
                xx = sx(0)
                Line(points=[xx, self.y, xx, self.top], width=1.1)
            if ymin <= 0 <= ymax:
                yy = sy(0)
                Line(points=[self.x, yy, self.right, yy], width=1.1)

            # Plot according to the selected scientific view.
            if self.mode == "Phase portrait" and len(self.data_states) >= 2:
                pts = []
                for xv, yv in zip(self.data_states[0], self.data_states[1]):
                    pts.extend((sx(xv), sy(yv)))
                if len(pts) >= 4:
                    Color(0.10, 0.75, 1.00, 1)
                    Line(points=pts, width=2.2)
            elif self.mode == "Derivative":
                _, series, _, _ = self._series_for_mode()
                pts = []
                for xv, yv in zip(self.data_x, series or []):
                    if xmin <= xv <= xmax and ymin <= yv <= ymax:
                        pts.extend((sx(xv), sy(yv)))
                if len(pts) >= 4:
                    Color(0.55, 1.00, 0.35, 1)
                    Line(points=pts, width=2.0)
            else:
                selected = range(len(self.data_states)) if self.mode == "All states" else [self.active_state]
                for si in selected:
                    series = self.data_states[si]
                    if not series: continue
                    pts = []
                    for xv, yv in zip(self.data_x, series):
                        if xmin <= xv <= xmax and ymin <= yv <= ymax:
                            pts.extend((sx(xv), sy(yv)))
                    if len(pts) >= 4:
                        Color(*self._state_colors[si % len(self._state_colors)])
                        Line(points=pts, width=2.2 if si == self.active_state else 1.15)

            if 0 <= self.cursor_index < len(self.data_x):
                i = self.cursor_index
                xv = self.data_x[i]
                series = self.data_states[self.active_state]
                if i < len(series):
                    yv = series[i]
                    if self.mode == "Phase portrait" and len(self.data_states) >= 2:
                        plot_x, plot_y = self.data_states[0][i], self.data_states[1][i]
                        px, py = sx(plot_x), sy(plot_y)
                    else:
                        plot_x, plot_y = xv, yv
                        px, py = sx(plot_x), sy(plot_y)

                    Color(1.0, 0.78, 0.10, 1)
                    Line(circle=(px, py, 6), width=2)

                    # In time-series views the vertical cursor line is useful.
                    # In phase space it would be physically misleading.
                    if self.mode != "Phase portrait":
                        Line(points=[px, self.y, px, self.top], width=1)

                    if self.mode == "Phase portrait" and len(self.data_states) >= 2:
                        self._info.text = (
                            f"y1 = {self.data_states[0][i]:.8g}\n"
                            f"y2 = {self.data_states[1][i]:.8g}   sample = {i}"
                        )
                    elif self.mode == "Derivative":
                        self._info.text = f"t = {xv:.8g}\ndy{self.active_state+1}/dt = {yv:.8g}   sample = {i}"
                    else:
                        self._info.text = f"t = {xv:.8g}\ny{self.active_state+1} = {yv:.8g}   sample = {i}"
                else:
                    self._info.text = ""
            else:
                self._info.text = "Tap the curve to select a numerical sample."

    def _screen_to_world(self, screen_x: float, screen_y: float):
        xmin, xmax, ymin, ymax = self._view()
        fx = (screen_x - self.x) / max(self.width, 1.0)
        fy = (screen_y - self.y) / max(self.height, 1.0)
        return xmin + fx * (xmax - xmin), ymin + fy * (ymax - ymin)

    def _pick_x(self, screen_x: float, screen_y: float | None = None) -> int:
        if not self.data_x:
            return -1

        # In a phase portrait the cursor belongs to the (y1,y2) curve,
        # not to the screen's vertical projection of t.
        if self.mode == "Phase portrait" and len(self.data_states) >= 2 and screen_y is not None:
            wx, wy = self._screen_to_world(screen_x, screen_y)
            xmin, xmax, ymin, ymax = self._view()
            dx_scale = max(xmax - xmin, 1e-30) / max(self.width, 1.0)
            dy_scale = max(ymax - ymin, 1e-30) / max(self.height, 1.0)
            return min(
                range(len(self.data_x)),
                key=lambda i: ((self.data_states[0][i] - wx) / dx_scale) ** 2
                              + ((self.data_states[1][i] - wy) / dy_scale) ** 2
            )

        xmin, xmax, _, _ = self._view()
        frac = max(0.0, min(1.0, (screen_x - self.x) / max(self.width, 1.0)))
        target = xmin + frac * (xmax - xmin)
        return min(range(len(self.data_x)), key=lambda i: abs(self.data_x[i] - target))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)

        # Mouse wheel: zoom at the pointer. This is intentionally not limited
        # to a small fixed range; 0.01x ... 500x is useful for numerical work.
        if getattr(touch, "is_mouse_scrolling", False):
            factor = 1.22 if touch.button == "scrollup" else 1.0 / 1.22
            self._zoom_at(factor, touch.x, touch.y)
            return True

        self._active_touches[touch.uid] = touch.pos

        if len(self._active_touches) == 2:
            pts = list(self._active_touches.values())
            self._pinch_distance = math.hypot(pts[1][0]-pts[0][0], pts[1][1]-pts[0][1])
            self._pinch_center = ((pts[0][0]+pts[1][0])*0.5, (pts[0][1]+pts[1][1])*0.5)
            self._touch_start = None
            self._last_touch = None
            return True

        self._touch_start = touch.pos
        self._last_touch = touch.pos
        return True

    def on_touch_move(self, touch):
        if touch.uid not in self._active_touches:
            return super().on_touch_move(touch)

        self._active_touches[touch.uid] = touch.pos

        if len(self._active_touches) >= 2:
            pts = list(self._active_touches.values())[:2]
            dist = math.hypot(pts[1][0]-pts[0][0], pts[1][1]-pts[0][1])
            center = ((pts[0][0]+pts[1][0])*0.5, (pts[0][1]+pts[1][1])*0.5)

            if self._pinch_distance and self._pinch_distance > 1e-6:
                factor = dist / self._pinch_distance
                if abs(factor - 1.0) > 0.002:
                    self._zoom_at(max(0.25, min(4.0, factor)), center[0], center[1])
                    self._pinch_distance = dist

            # Two-finger translation pans the graph.
            if self._pinch_center is not None:
                dx = center[0] - self._pinch_center[0]
                dy = center[1] - self._pinch_center[1]
                xmin, xmax, ymin, ymax = self._view()
                self._pan_x -= dx / max(self.width, 1.0) * (xmax - xmin)
                self._pan_y -= dy / max(self.height, 1.0) * (ymax - ymin)
                self._pinch_center = center
                self._redraw()
            return True

        if self._touch_start is None:
            return super().on_touch_move(touch)

        dx = touch.x - self._last_touch[0]
        dy = touch.y - self._last_touch[1]
        self._last_touch = touch.pos
        xmin, xmax, ymin, ymax = self._view()
        self._pan_x -= dx / max(self.width, 1.0) * (xmax - xmin)
        self._pan_y -= dy / max(self.height, 1.0) * (ymax - ymin)
        self._redraw()
        return True

    def on_touch_up(self, touch):
        was_single = len(self._active_touches) == 1 and self._touch_start is not None
        start = self._touch_start
        self._active_touches.pop(touch.uid, None)

        if len(self._active_touches) == 0:
            self._pinch_distance = None
            self._pinch_center = None

        if was_single and start is not None:
            dx = touch.x - start[0]
            dy = touch.y - start[1]
            if abs(dx) < 8 and abs(dy) < 8 and self.data_x:
                idx = self._pick_x(touch.x, touch.y)
                self.cursor_index = idx
                if self.on_cursor:
                    self.on_cursor(idx)

        self._touch_start = self._last_touch = None
        self._redraw()
        return True

class Trajectory3DWidget(Widget):
    """Full-resolution 3D trajectory / phase-space renderer.

    Every numerical sample is retained. Camera interaction is a visualization
    operation only: it never changes the ODE solution. For planar two-state
    systems the default camera is normal to the (y1,y2) phase plane, so SHM
    with k1=1 is seen as its natural circular phase orbit rather than as an
    artificially flattened projection. Three-state systems retain an oblique
    default view.
    """

    cursor_index = NumericProperty(-1)
    playing = BooleanProperty(False)
    trail_enabled = BooleanProperty(True)
    axes_enabled = BooleanProperty(True)
    ball_size = NumericProperty(7.0)

    def __init__(self, on_cursor: Callable[[int], None] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.on_cursor = on_cursor
        self._clock_event = None
        self._animation_speed = 1.0
        self._animation_time = 0.0
        self._loop = True
        self._animation_started = False

        # User-controlled visual settings. Defaults preserve the V5 look.
        self.ball_size = 7.0
        self.axes_enabled = True
        # Full-resolution numerical data. Nothing is decimated here.
        self.data_x: list[float] = []
        self.states: list[list[float]] = []
        self._points_cache: list[tuple[float, float, float]] = []

        # Cached normalization and projection state.
        self._center = (0.0, 0.0, 0.0)
        self._scale = 1.0
        self._projected_cache: list[tuple[float, float, float] | None] = []
        self._projection_dirty = True
        self._last_projection_signature = None

        self.yaw = 0.0
        self.pitch = 0.0
        # A closer initial camera makes large phase portraits fill the
        # viewport without changing the underlying geometry.
        self.distance = 2.35
        self.coordinate_mode = "auto"

        self._touch_start = None
        self._last_touch = None

        self._info = Label(
            text="",
            size_hint=(None, None),
            size=(430, 58),
            font_size="13sp",
            color=(0.95, .97, 1, 1),
            halign="left",
            valign="top",
        )
        self.add_widget(self._info)

        self._sphere_texture = self._build_sphere_texture(96)

        self.bind(pos=self._on_view_changed, size=self._on_view_changed)

    @staticmethod
    def _build_sphere_texture(size: int = 96):
        """Create a small high-quality whitish-blue shaded sphere texture.

        This is only the visual current-state marker. It does not represent a
        physical particle and does not alter the numerical trajectory.
        """
        from kivy.graphics.texture import Texture

        size = max(32, int(size))
        cx = (size - 1) * 0.5
        cy = cx
        radius = (size - 2) * 0.5
        pixels = bytearray(size * size * 4)

        # Soft directional illumination: natural-looking pale blue/white.
        lx, ly, lz = -0.36, 0.42, 0.83
        ll = math.sqrt(lx * lx + ly * ly + lz * lz)
        lx, ly, lz = lx / ll, ly / ll, lz / ll

        for py in range(size):
            sy = (py - cy) / radius
            for px in range(size):
                sx = (px - cx) / radius
                rr = sx * sx + sy * sy
                k = (py * size + px) * 4
                if rr >= 1.0:
                    pixels[k:k+4] = bytes((0, 0, 0, 0))
                    continue

                nz = math.sqrt(max(0.0, 1.0 - rr))
                # Screen-space normal. Positive z is toward the viewer.
                nx, ny = sx, sy
                diffuse = max(0.0, nx * lx + ny * ly + nz * lz)
                # A compact specular highlight gives the dense billiard-ball
                # impression without a cartoon outline.
                hx, hy, hz = lx, ly, lz
                dot_h = max(0.0, nx * hx + ny * hy + nz * hz)
                spec = dot_h ** 34
                ambient = 0.34

                intensity = min(1.0, ambient + 0.70 * diffuse)
                # Pale blue-white body, slightly deeper blue toward the rim.
                r = min(255, int(182 + 73 * intensity + 24 * spec))
                g = min(255, int(211 + 44 * intensity + 30 * spec))
                b = min(255, int(232 + 23 * intensity + 23 * spec))

                # Very soft edge falloff, retaining a dense opaque center.
                edge = max(0.0, min(1.0, (1.0 - math.sqrt(rr)) * 7.0))
                alpha = int(255 * (0.82 + 0.18 * edge))
                pixels[k:k+4] = bytes((r, g, b, alpha))

        tex = Texture.create(size=(size, size), colorfmt="rgba", bufferfmt="ubyte")
        tex.blit_buffer(bytes(pixels), colorfmt="rgba", bufferfmt="ubyte")
        tex.wrap = "clamp_to_edge"
        tex.mag_filter = "linear"
        tex.min_filter = "linear"
        return tex

    def set_coordinate_mode(self, mode: str = "auto") -> None:
        """Select the semantic coordinate projection used by the 3D view.

        auto: 2-state systems are treated as phase-space (y1,y2,0);
        three-state systems use (y1,y2,y3).
        physical_xy: use (y1,y3,0), useful for the planar Two Body preset.
        """
        mode = str(mode or "auto").lower()
        self.coordinate_mode = mode if mode in {"auto", "phase", "physical_xy"} else "auto"
        self._rebuild_points()
        self._redraw()

    def _rebuild_points(self):
        n = len(self.data_x)
        if not n:
            self._points_cache = []
            self._recompute_bounds()
            self._mark_projection_dirty()
            return
        if self.coordinate_mode == "physical_xy" and len(self.states) >= 4:
            self._points_cache = [(self.states[0][i], self.states[2][i], 0.0) for i in range(n)]
        elif len(self.states) >= 3:
            self._points_cache = [(self.states[0][i], self.states[1][i], self.states[2][i]) for i in range(n)]
        elif len(self.states) >= 2:
            self._points_cache = [(self.states[0][i], self.states[1][i], 0.0) for i in range(n)]
        else:
            self._points_cache = [(self.states[0][i], 0.0, 0.0) for i in range(n)]
        self._recompute_bounds()
        self._mark_projection_dirty()

    @property
    def animation_speed(self) -> float:
        return self._animation_speed

    def set_animation_speed(self, speed: float) -> None:
        self._animation_speed = max(0.05, float(speed))

    def set_loop(self, enabled: bool) -> None:
        self._loop = bool(enabled)

    def set_ball_size(self, size: float) -> None:
        """Set the selected-state marker diameter without changing geometry."""
        try:
            value = float(size)
        except (TypeError, ValueError):
            return
        if not math.isfinite(value):
            return
        self.ball_size = max(3.0, min(32.0, value))
        self._redraw()

    def set_axes_enabled(self, enabled: bool) -> None:
        self.axes_enabled = bool(enabled)
        self._redraw()

    def toggle_trail(self) -> None:
        self.trail_enabled = not self.trail_enabled
        self._redraw()

    def play(self) -> None:
        if not self.data_x:
            return
        if self._clock_event is None:
            self._clock_event = Clock.schedule_interval(self._animation_tick, 1.0 / 60.0)
        self._animation_started = True
        self.playing = True

    def pause(self) -> None:
        self.playing = False
        if self._clock_event is not None:
            self._clock_event.cancel()
            self._clock_event = None

    def toggle_play(self) -> None:
        if self.playing:
            self.pause()
        else:
            self.play()

    def reset_animation(self) -> None:
        self.pause()
        if self.data_x:
            self._animation_time = self.data_x[0]
            self._animation_started = True
            self.cursor_index = 0
            if self.on_cursor:
                self.on_cursor(0)
        self._redraw()

    def _animation_tick(self, dt: float) -> None:
        if not self.playing or not self.data_x:
            return
        t0, t1 = self.data_x[0], self.data_x[-1]
        span = max(t1 - t0, 1e-12)
        self._animation_time += dt * self._animation_speed
        if self._animation_time > t1:
            if self._loop:
                self._animation_time = t0
            else:
                self._animation_time = t1
                self.pause()
        # Monotone time grids are produced by the solver; use binary search
        # so animation remains O(log N) even for very large trajectories.
        import bisect
        idx = bisect.bisect_left(self.data_x, self._animation_time)
        idx = max(0, min(idx, len(self.data_x) - 1))
        self.cursor_index = idx
        self._redraw()
        if self.on_cursor:
            self.on_cursor(idx)

    def set_data(self, x: Sequence[float], states: Sequence[Sequence[float]]) -> None:
        # Copy once. The original numerical trajectory remains untouched.
        self.data_x = list(x)
        self.states = [list(s) for s in states]

        n = len(self.data_x)
        # Full-resolution coordinate construction. No decimation.
        self._rebuild_points()

        self.cursor_index = 0 if self.data_x else -1
        self._animation_time = self.data_x[0] if self.data_x else 0.0
        self._animation_started = False

        # Face a planar state space directly so SHM is not needlessly
        # flattened. Genuine 3-state systems retain an oblique 3D view.
        if self.coordinate_mode == "physical_xy" or len(self.states) == 2:
            self.yaw, self.pitch = 0.0, 0.0
        else:
            self.yaw, self.pitch = 35.0, 22.0
        self.distance = 2.35

        self._mark_projection_dirty()
        self._redraw()

    def _recompute_bounds(self):
        pts = self._points_cache
        if not pts:
            self._center = (0.0, 0.0, 0.0)
            self._scale = 1.0
            return

        xmin = min(p[0] for p in pts)
        xmax = max(p[0] for p in pts)
        ymin = min(p[1] for p in pts)
        ymax = max(p[1] for p in pts)
        zmin = min(p[2] for p in pts)
        zmax = max(p[2] for p in pts)

        cx = 0.5 * (xmin + xmax)
        cy = 0.5 * (ymin + ymax)
        cz = 0.5 * (zmin + zmax)

        # Isotropic scientific scaling: one world unit has the same
        # geometric scale on X, Y and Z. This is intentionally based on
        # the full trajectory, not on a display subset.
        scale = max(
            0.5 * (xmax - xmin),
            0.5 * (ymax - ymin),
            0.5 * (zmax - zmin),
            1e-9,
        )

        self._center = (cx, cy, cz)
        self._scale = scale

    def _mark_projection_dirty(self):
        self._projection_dirty = True

    def _on_view_changed(self, *_args):
        self._mark_projection_dirty()
        self._redraw()

    def _project_point(self, p):
        cx, cy, cz = self._center
        scale = self._scale

        x = (p[0] - cx) / scale
        y = (p[1] - cy) / scale
        z = (p[2] - cz) / scale

        ya = math.radians(self.yaw)
        pi = math.radians(self.pitch)
        cyaw, syaw = math.cos(ya), math.sin(ya)
        cp, sp = math.cos(pi), math.sin(pi)

        # Orbit around Z, then pitch around camera-local X.
        xr = cyaw * x - syaw * y
        zr = syaw * x + cyaw * y
        yr = cp * zr + sp * z
        zr2 = -sp * zr + cp * z

        # Planar phase-space / physical-plane displays use an orthographic
        # projection. This preserves circles and ellipses as true geometric
        # shapes instead of introducing a perspective distortion that can make
        # SHM look artificially flattened. Genuine 3-state systems retain the
        # perspective renderer.
        if self.coordinate_mode in ("physical_xy",) or len(self.states) == 2:
            if self.distance <= 0.05:
                return None
            f = min(self.width, self.height) * 0.48 / self.distance
            depth = self.distance + zr2
            return self.center_x + xr * f, self.center_y + yr * f, depth

        depth = self.distance + zr2
        if depth <= 0.05:
            return None

        # Perspective projection for genuine 3-state geometry.
        f = min(self.width, self.height) * 0.78 / depth
        return self.center_x + xr * f, self.center_y + yr * f, depth

    def _rebuild_projection_cache(self):
        if not self._points_cache or self.width < 40 or self.height < 40:
            self._projected_cache = []
            self._projection_dirty = False
            return

        self._projected_cache = [
            self._project_point(p) for p in self._points_cache
        ]
        self._last_projection_signature = (
            self.width, self.height,
            self.yaw, self.pitch, self.distance,
            self._center, self._scale,
        )
        self._projection_dirty = False

    @property
    def center_x(self):
        return self.x + self.width * .5

    @property
    def center_y(self):
        return self.y + self.height * .5

    def _redraw(self, *_args):
        if self._projection_dirty:
            self._rebuild_projection_cache()

        self.canvas.clear()
        self._info.pos = (self.x + 10, self.top - 64)

        with self.canvas:
            Color(.035, .045, .065, 1)
            Rectangle(pos=self.pos, size=self.size)

            if not self._points_cache or self.width < 40 or self.height < 40:
                self._info.text = "Solve a system to display the 3D trajectory."
                return

            # Reference axes. They are a pure visualization layer and can
            # be hidden without changing coordinates, scaling, or trajectory.
            if self.axes_enabled:
                o = self._project_point((0.0, 0.0, 0.0))
                axis_len = self._scale
                ax = self._project_point((axis_len, 0.0, 0.0))
                ay = self._project_point((0.0, axis_len, 0.0))
                az = self._project_point((0.0, 0.0, axis_len))

                Color(.45, .48, .55, 1)
                if o and ax:
                    Line(points=[o[0], o[1], ax[0], ax[1]], width=1.1)
                if o and ay:
                    Line(points=[o[0], o[1], ay[0], ay[1]], width=1.1)
                if o and az:
                    Line(points=[o[0], o[1], az[0], az[1]], width=1.1)

            # Render either the full trajectory (static view) or the
            # dynamically accumulated trail. No numerical samples are ever
            # discarded; trail_enabled only controls what is visible.
            end = len(self._projected_cache) - 1
            if self._animation_started:
                end = min(end, max(0, self.cursor_index))
            flat = []
            if (self.trail_enabled or not self._animation_started):
                for q in self._projected_cache[:end + 1]:
                    if q is not None:
                        flat.extend((q[0], q[1]))
                if len(flat) >= 4:
                    Color(.10, .80, 1.0, 1)
                    Line(points=flat, width=1.45)

            if 0 <= self.cursor_index < len(self._projected_cache):
                q = self._projected_cache[self.cursor_index]
                if q is not None:
                    # The current-state marker is a dense shaded sphere.
                    # It is a locator for the numerical state, not a physical
                    # particle and never changes the phase-space trajectory.
                    diameter = max(4.0, float(self.ball_size) * 2.0)
                    Color(1.0, 1.0, 1.0, 1.0)
                    Ellipse(
                        texture=self._sphere_texture,
                        pos=(q[0] - diameter * 0.5, q[1] - diameter * 0.5),
                        size=(diameter, diameter),
                    )

                    p = self._points_cache[self.cursor_index]
                    mode = "PLAYING" if self.playing else "PAUSED"
                    trail = "ON" if self.trail_enabled else "OFF"
                    self._info.text = (
                        f"{mode}  •  trail {trail}  •  axes {'ON' if self.axes_enabled else 'OFF'}"
                        f"  •  ball {self.ball_size:g}   •  sample {self.cursor_index}   "
                        f"t = {self.data_x[self.cursor_index]:.9g}\n"
                        f"(y1,y2,y3) = "
                        f"({p[0]:.9g}, {p[1]:.9g}, {p[2]:.9g})"
                    )
                else:
                    self._info.text = "Selected sample is outside the current camera."
            else:
                self._info.text = "3D trajectory ready — press PLAY to animate."

    def _pick_nearest(self, screen_x: float, screen_y: float) -> int:
        best = -1
        best_d2 = float("inf")
        for i, q in enumerate(self._projected_cache):
            if q is None:
                continue
            d2 = (q[0] - screen_x) ** 2 + (q[1] - screen_y) ** 2
            if d2 < best_d2:
                best, best_d2 = i, d2

        threshold = max(16.0 ** 2, min(self.width, self.height) ** 2 * .02)
        return best if best >= 0 and best_d2 <= threshold else -1

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)

        if getattr(touch, "is_mouse_scrolling", False):
            self.distance *= 0.86 if touch.button == "scrollup" else 1.16
            self.distance = max(.55, min(30.0, self.distance))
            self._mark_projection_dirty()
            self._redraw()
            return True

        self._touch_start = touch.pos
        self._last_touch = touch.pos
        return True

    def on_touch_move(self, touch):
        if self._touch_start is None:
            return super().on_touch_move(touch)

        dx = touch.x - self._last_touch[0]
        dy = touch.y - self._last_touch[1]
        self._last_touch = touch.pos

        self.yaw += dx * .45
        self.pitch = max(-85.0, min(85.0, self.pitch + dy * .35))

        # Camera changed: recompute all full-resolution projected samples.
        self._mark_projection_dirty()
        self._redraw()
        return True

    def on_touch_up(self, touch):
        if self._touch_start is None:
            return super().on_touch_up(touch)

        dx = touch.x - self._touch_start[0]
        dy = touch.y - self._touch_start[1]

        if abs(dx) < 8 and abs(dy) < 8 and self._projected_cache:
            best = self._pick_nearest(touch.x, touch.y)
            if best >= 0:
                self.cursor_index = best
                if self.on_cursor:
                    self.on_cursor(best)

        self._touch_start = self._last_touch = None
        self._redraw()
        return True
