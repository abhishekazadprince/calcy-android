
from __future__ import annotations

import math

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.uix.popup import Popup
from pathlib import Path
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem

from android_app.controller import CalcyController, PRESETS
from android_app.graph import PlotWidget, Trajectory3DWidget


class CalcyApp(App):
    title = "Calcy"

    def build(self):
        self.controller = CalcyController()
        self._table_buttons = []
        root = BoxLayout(orientation="vertical", padding=(dp(6), dp(0)), spacing=dp(4))
        root.add_widget(self._header())

        self.tabs = TabbedPanel(
            do_default_tab=False,
            tab_width=dp(110),
            tab_height=dp(50),
            size_hint_y=1,
        )
        self.tabs.add_widget(self._editor_tab())
        self.tabs.add_widget(self._graph_tab())
        self.tabs.add_widget(self._table_tab())
        self.tabs.add_widget(self._analysis_tab())
        self.tabs.add_widget(self._three_d_tab())
        root.add_widget(self.tabs)

        self.status = Label(
            text="Ready — load a preset or enter an ODE",
            size_hint_y=None,
            height=dp(42),
            halign="center",
        )
        root.add_widget(self.status)
        self._load_preset("SHM")
        return root

    def _header(self):
        """Spacious Calcy home header.

        Keep the original visual hierarchy: a large black breathing space,
        bold CALCY title, and only the most important model launchers visible.
        The full preset library lives behind the MODELS dropdown.
        """
        outer = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(104),
            padding=(dp(8), dp(10)),
            spacing=dp(10),
        )

        title_area = AnchorLayout(size_hint_x=0.38)
        title_area.add_widget(Label(
            text="CALCY",
            font_size="34sp",
            bold=True,
            color=(0.98, 0.98, 0.98, 1),
            size_hint=(None, None),
            size=(dp(220), dp(72)),
        ))
        outer.add_widget(title_area)

        model_bar = BoxLayout(
            orientation="horizontal",
            size_hint_x=0.62,
            spacing=dp(6),
        )

        custom = Button(text="CUSTOM ODE", size_hint_x=None, width=dp(112))
        custom.bind(on_release=self._new_custom_ode)
        model_bar.add_widget(custom)

        for name, width in (("SHM", 78), ("Pendulum", 102)):
            b = Button(text=name, size_hint_x=None, width=dp(width))
            b.bind(on_release=lambda _b, n=name: self._load_preset(n))
            model_bar.add_widget(b)

        # Keep the header uncluttered. All other built-in models are exposed
        # through the same compact dropdown pattern used by Graph controls.
        self.model_spinner = Spinner(
            text="MODELS ▾",
            values=tuple(PRESETS.keys()),
            size_hint_x=None,
            width=dp(118),
        )
        self.model_spinner.bind(text=self._model_menu_changed)
        model_bar.add_widget(self.model_spinner)

        help_btn = Button(text="HELP", size_hint_x=None, width=dp(68))
        help_btn.bind(on_release=self._show_help)
        model_bar.add_widget(help_btn)

        outer.add_widget(model_bar)
        return outer

    def _model_menu_changed(self, _spinner, value):
        if value in PRESETS:
            self._load_preset(value)
            # Keep the launcher itself labelled as a menu rather than turning
            # it into a permanent model-selection field.
            self.model_spinner.text = "MODELS ▾"

    def _new_custom_ode(self, *_args):
        if not hasattr(self, "fields"):
            return
        defaults = {"name": "Custom ODE", "rhs": "", "initial": "", "parameters": "",
                    "x0": "0", "x1": "10", "h0": "0.01", "tol": "1e-7"}
        for key, value in defaults.items():
            self.fields[key].text = value
        self._active_preset = None
        self.status.text = "Custom ODE editor ready — enter any first-order ODE system symbolically"
        self.tabs.switch_to(self.tabs.tab_list[0])

    def _editor_tab(self):
        tab = TabbedPanelItem(text="Solve")
        scroll = ScrollView()
        grid = GridLayout(cols=2, spacing=dp(6), padding=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        self.fields = {}

        fields = [
            ("Name", "name", False, 42),
            ("RHS — symbolic ODE system (semicolon separated)", "rhs", True, 82),
            ("Initial values", "initial", True, 60),
            ("Parameters", "parameters", True, 60),
            ("x0", "x0", False, 42),
            ("x1", "x1", False, 42),
            ("Initial step", "h0", False, 42),
            ("Tolerance", "tol", False, 42),
        ]
        defaults = {"h0": "0.01", "tol": "1e-7"}

        for label, key, multi, height in fields:
            grid.add_widget(Label(text=label, size_hint_y=None, height=dp(height), halign="left"))
            ti = TextInput(
                text=defaults.get(key, ""),
                multiline=multi,
                size_hint_y=None,
                height=dp(height),
            )
            self.fields[key] = ti
            grid.add_widget(ti)

        solve = Button(text="SOLVE", size_hint_y=None, height=dp(54))
        solve.bind(on_release=self._solve)
        grid.add_widget(Label(text=""))
        grid.add_widget(solve)

        hint = Label(
            text="Enter any first-order system symbolically.\n"
                 "Example: y2; -k1*k1*y1    |    Parameters: k1=1, k2=2\n"
                 "The same numerical trajectory drives Graph, Table, Analysis and 3D.",
            size_hint_y=None,
            height=dp(78),
            halign="left",
        )
        grid.add_widget(Label(text=""))
        grid.add_widget(hint)

        grid.add_widget(Label(text="COMMON MODELS", size_hint_y=None, height=dp(36)))
        model_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(5))
        for name in ("Damped SHM", "Two Body", "Ballistic", "Brusselator"): 
            b = Button(text=name)
            b.bind(on_release=lambda _b, n=name: self._load_preset(n))
            model_row.add_widget(b)
        grid.add_widget(Label(text=""))
        grid.add_widget(model_row)
        scroll.add_widget(grid)
        tab.content = scroll
        return tab

    def _graph_tab(self):
        tab = TabbedPanelItem(text="Graph")
        box = BoxLayout(orientation="vertical")
        controls = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(5))
        controls.add_widget(Label(text="View:", size_hint_x=None, width=dp(45)))
        self.graph_mode = Spinner(
            text="Time series",
            values=("Time series", "All states", "Phase portrait", "Derivative"),
            size_hint_x=None, width=dp(125),
        )
        self.graph_mode.bind(text=self._graph_mode_changed)
        controls.add_widget(self.graph_mode)
        controls.add_widget(Label(text="State:", size_hint_x=None, width=dp(45)))
        self.state_spinner = Spinner(text="y1", values=("y1",), size_hint_x=None, width=dp(75))
        self.state_spinner.bind(text=self._state_changed)
        controls.add_widget(self.state_spinner)

        reset_view = Button(text="RESET VIEW", size_hint_x=None, width=dp(105))
        reset_view.bind(on_release=lambda *_: self.plot.reset_view())
        controls.add_widget(reset_view)
        box.add_widget(controls)
        self.plot = PlotWidget(on_cursor=self._cursor_selected)
        box.add_widget(self.plot)
        tab.content = box
        return tab

    def _table_tab(self):
        tab = TabbedPanelItem(text="Table")
        self.table_scroll = ScrollView()
        self.table_grid = GridLayout(cols=1, spacing=dp(1), padding=dp(4), size_hint_y=None)
        self.table_grid.bind(minimum_height=self.table_grid.setter("height"))
        self.table_scroll.add_widget(self.table_grid)
        box = BoxLayout(orientation="vertical")
        exports = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
        txt = Button(text="EXPORT TXT")
        txt.bind(on_release=self._export_table_txt)
        pdf = Button(text="EXPORT PDF")
        pdf.bind(on_release=self._export_table_pdf)
        exports.add_widget(txt)
        exports.add_widget(pdf)
        box.add_widget(exports)
        box.add_widget(self.table_scroll)
        tab.content = box
        return tab

    def _analysis_tab(self):
        tab = TabbedPanelItem(text="Analysis")
        scroll = ScrollView()
        self.analysis_label = Label(text="No solution yet.", halign="left", valign="top",
                                    size_hint_y=None, padding=(dp(12), dp(12)))
        self.analysis_label.bind(texture_size=lambda w, size: setattr(w, "height", size[1] + dp(24)))
        scroll.add_widget(self.analysis_label)
        tab.content = scroll
        return tab

    def _three_d_tab(self):
        tab = TabbedPanelItem(text="3D")
        box = BoxLayout(orientation="vertical")

        # Minimal 3D controls. The proven V6 phase-space architecture is
        # preserved; only essential controls are exposed here.
        controls = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))

        self.play3d = Button(text="PLAY", size_hint_x=None, width=dp(76))
        self.play3d.bind(on_release=self._toggle_3d_play)
        controls.add_widget(self.play3d)

        reset3d = Button(text="RESET", size_hint_x=None, width=dp(72))
        reset3d.bind(on_release=lambda *_: self._reset_3d())
        controls.add_widget(reset3d)

        self.trail3d = ToggleButton(
            text="TRAIL: ON", state="down", size_hint_x=None, width=dp(96)
        )
        self.trail3d.bind(on_release=self._trail_changed)
        controls.add_widget(self.trail3d)

        self.axes3d = ToggleButton(
            text="AXES: ON", state="down", size_hint_x=None, width=dp(88)
        )
        self.axes3d.bind(on_release=self._axes_changed)
        controls.add_widget(self.axes3d)

        controls.add_widget(Label(text="Speed", size_hint_x=None, width=dp(42)))
        self.speed3d = Spinner(
            text="1x",
            values=("0.25x", "0.5x", "1x", "2x", "5x", "10x", "20x"),
            size_hint_x=None, width=dp(72),
        )
        self.speed3d.bind(text=self._speed_changed)
        controls.add_widget(self.speed3d)

        controls.add_widget(Label(text="Sphere", size_hint_x=None, width=dp(52)))
        self.sphere3d = Spinner(
            text="7", values=("4", "6", "7", "9", "12", "16", "20", "28"),
            size_hint_x=None, width=dp(58),
        )
        self.sphere3d.bind(text=self._sphere_changed)
        controls.add_widget(self.sphere3d)
        box.add_widget(controls)

        self.three_d = Trajectory3DWidget(on_cursor=self._cursor_selected)
        box.add_widget(self.three_d)
        tab.content = box
        return tab

    def _toggle_3d_play(self, *_args):
        self.three_d.toggle_play()
        self.play3d.text = "PAUSE" if self.three_d.playing else "PLAY"

    def _reset_3d(self, *_args):
        self.three_d.reset_animation()
        self.play3d.text = "PLAY"

    def _trail_changed(self, button):
        self.three_d.trail_enabled = button.state == "down"
        button.text = "TRAIL: ON" if button.state == "down" else "TRAIL: OFF"
        self.three_d._redraw()

    def _speed_changed(self, _spinner, value):
        try:
            self.three_d.set_animation_speed(float(value.rstrip("x")))
        except ValueError:
            pass

    def _axes_changed(self, button):
        enabled = button.state == "down"
        button.text = "AXES: ON" if enabled else "AXES: OFF"
        self.three_d.set_axes_enabled(enabled)

    def _sphere_changed(self, _spinner, value):
        try:
            self.three_d.set_ball_size(float(value))
        except (TypeError, ValueError):
            pass

    def _load_preset(self, name):
        p = PRESETS[name]
        self._active_preset = name
        if not hasattr(self, "fields"):
            return
        for key, value in p.items():
            if key in self.fields:
                self.fields[key].text = value
        self.status.text = f"Preset loaded: {name}"

    @staticmethod
    def _numeric_text(field, default: str, label: str) -> str:
        """Return a valid numeric field value and repair accidental blanks."""
        value = field.text.strip()
        if not value:
            value = default
            field.text = value
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number: {value!r}") from exc
        if not math.isfinite(number):
            raise ValueError(f"{label} must be finite")
        return value

    def _solve(self, *_args):
        try:
            import math
            f = self.fields
            # Never let an empty TextInput reach float(). This also repairs
            # old layouts where the lower fields could visually lose their
            # default text after scrolling/rebuilding.
            x0_text = self._numeric_text(f["x0"], "0", "x0")
            x1_text = self._numeric_text(f["x1"], "20", "x1")
            h0_text = self._numeric_text(f["h0"], "0.01", "Initial step")
            tol_text = self._numeric_text(f["tol"], "1e-7", "Tolerance")

            if float(x1_text) <= float(x0_text):
                raise ValueError("x1 must be greater than x0")
            if float(h0_text) <= 0:
                raise ValueError("Initial step must be > 0")
            if float(tol_text) <= 0:
                raise ValueError("Tolerance must be > 0")

            result = self.controller.solve(
                f["name"].text.strip(),
                f["rhs"].text.strip(),
                f["initial"].text.strip(),
                f["parameters"].text.strip(),
                float(x0_text),
                float(x1_text),
                float(h0_text),
                float(tol_text),
            )

            self.plot.set_data(result["times"], result["states"])
            if self._active_preset in ("Two Body", "Ballistic"):
                self.three_d.set_coordinate_mode("physical_xy")
            else:
                self.three_d.set_coordinate_mode("auto")
            self.three_d.set_data(result["times"], result["states"])

            names = tuple(f"y{i+1}" for i in range(result["neqns"]))
            self.state_spinner.values = names
            self.state_spinner.text = names[0]
            self.graph_mode.text = "Time series"
            self.plot.set_mode("Time series")

            self._refresh_table()
            self._refresh_analysis()
            self.status.text = (
                f"Solved: {result['name']} — "
                f"{result['npts']} samples, {result['neqns']} states"
            )
            self.tabs.switch_to(self.tabs.tab_list[1])
        except Exception as exc:
            self.status.text = f"ERROR: {exc}"

    def _state_changed(self, _spinner, value):
        if value.startswith("y"):
            try:
                self.plot.set_state(int(value[1:]) - 1)
            except ValueError:
                pass

    def _graph_mode_changed(self, _spinner, value):
        if hasattr(self, "plot"):
            self.plot.set_mode(value)

    def _refresh_table(self):
        self.table_grid.clear_widgets()
        self._table_buttons.clear()
        times, states = self.controller.times, self.controller.states
        if not times:
            self.table_grid.add_widget(Label(text="Solve a problem first.", size_hint_y=None, height=dp(40)))
            return

        header = "sample     t                 " + "       ".join(f"y{i+1}" for i in range(len(states)))
        self.table_grid.add_widget(
            Label(text=header, size_hint_y=None, height=dp(30), halign="left")
        )

        stride = max(1, len(times) // 100)
        indices = list(range(0, len(times), stride))
        if indices[-1] != len(times) - 1:
            indices.append(len(times) - 1)

        for i in indices:
            vals = "   ".join(f"{s[i]: .8g}" for s in states)
            b = Button(
                text=f"{i:5d}   {times[i]: .9g}   {vals}",
                size_hint_y=None,
                height=dp(32),
                halign="left",
            )
            b.bind(on_release=lambda _b, idx=i: self._cursor_selected(idx))
            self.table_grid.add_widget(b)
            self._table_buttons.append((i, b))

    def _cursor_selected(self, index: int):
        if index < 0 or index >= len(self.controller.times):
            return
        self.plot.cursor_index = index
        self.three_d.cursor_index = index
        self._highlight_table(index)
        t = self.controller.times[index]
        state = [s[index] for s in self.controller.states]
        self.status.text = (
            f"Cursor: sample {index}   t={t:.9g}   "
            + "   ".join(f"y{i+1}={v:.9g}" for i, v in enumerate(state))
        )

    def _highlight_table(self, index: int):
        for idx, button in self._table_buttons:
            button.opacity = 1.0 if idx == index else 0.78

    def _refresh_analysis(self):
        t, states = self.controller.times, self.controller.states
        if not t:
            self.analysis_label.text = "No solution yet."
            return
        import math
        lines = [
            "NUMERICAL ANALYSIS",
            "=" * 48,
            f"Samples: {len(t)}",
            f"States: {len(states)}",
            f"Domain: {t[0]:.9g} → {t[-1]:.9g}",
            f"Span: {t[-1] - t[0]:.9g}",
            f"Mean step: {(t[-1]-t[0])/max(len(t)-1,1):.9g}",
            "",
        ]
        for i, y in enumerate(states, 1):
            mean = sum(y) / len(y)
            rms = math.sqrt(sum(v*v for v in y) / len(y))
            zero = sum(1 for a, b in zip(y, y[1:]) if (a <= 0 < b) or (a >= 0 > b))
            lines.append(f"y{i}")
            lines.append(f"  min={min(y):.9g}   max={max(y):.9g}   range={max(y)-min(y):.9g}")
            lines.append(f"  mean={mean:.9g}  RMS={rms:.9g}  final={y[-1]:.9g}")
            lines.append(f"  zero crossings≈{zero}")
            lines.append("")
        if len(states) >= 2:
            lines += ["Phase-space diagnostics", "  x = y1, y = y2"]
        if len(states) >= 3:
            lines.append("  3D trajectory = (y1, y2, y3)")
        self.analysis_label.text = "\n".join(lines)

    def _show_help(self, *_args):
        """Show the bundled, pre-rendered manual pages.

        IMPORTANT: Help must never depend on Pillow/RAQM at runtime.  The
        Hindi manual pages are rendered once during packaging with a proper
        Indic shaper and shipped as PNGs.  Kivy only displays pixels here.
        This keeps Help completely isolated from the numerical solver and
        avoids platform-dependent Devanagari shaping failures.
        """
        from kivy.uix.image import Image as KivyImage

        manual_dir = Path(__file__).resolve().parent / "assets" / "manual"
        page_files = sorted(manual_dir.glob("help_*.png"))
        if not page_files:
            self.status.text = "Help unavailable: bundled manual pages are missing"
            return

        body = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(8))
        pages = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))

        # The source PNGs are portrait A4-like pages.  Each page keeps its
        # aspect ratio and is scaled to the available popup width.
        page_ratio = 1754.0 / 1240.0
        for page_file in page_files:
            page = KivyImage(
                source=str(page_file),
                size_hint_y=None,
                allow_stretch=True,
                keep_ratio=True,
            )
            page.height = max(dp(500), page.width * page_ratio)
            page.bind(width=lambda w, *_args, r=page_ratio:
                      setattr(w, "height", max(dp(500), w.width * r)))
            pages.add_widget(page)

        def resize_pages(*_args):
            # Width is the inner width of the ScrollView; use the same width
            # for every manual page so the text remains crisp and readable.
            width = max(dp(300), scroll.width - dp(4))
            for page in pages.children:
                page.width = width
                page.height = width * page_ratio
            pages.height = sum(p.height for p in pages.children) + dp(10) * max(0, len(pages.children)-1)

        scroll.bind(size=resize_pages)
        scroll.add_widget(pages)
        body.add_widget(scroll)

        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        txt = Button(text="DOWNLOAD TXT")
        pdf = Button(text="DOWNLOAD PDF")
        close = Button(text="CLOSE")
        txt.bind(on_release=lambda *_: self._export_manual_txt())
        pdf.bind(on_release=lambda *_: self._export_manual_pdf())
        close.bind(on_release=lambda *_: popup.dismiss())
        actions.add_widget(txt)
        actions.add_widget(pdf)
        actions.add_widget(close)
        body.add_widget(actions)

        popup = Popup(
            title="Calcy Help & User Manual",
            content=body,
            size_hint=(0.94, 0.92),
            auto_dismiss=True,
        )
        popup.open()
        resize_pages()

    def _export_manual_txt(self, *_args):
        source = Path(__file__).resolve().parent / "assets" / "manual" / "calcy_user_manual.txt"
        if not source.exists():
            self.status.text = "User manual TXT is missing from the application"
            return
        payload = source.read_bytes()
        android_uri = self._android_download("calcy_user_manual.txt", payload, "text/plain")
        if android_uri:
            self.status.text = "User manual exported to Download/Calcy/calcy_user_manual.txt"
            return
        path = Path(self.user_data_dir) / "calcy_user_manual.txt"
        path.write_bytes(payload)
        self.status.text = f"User manual exported: {path}"

    def _export_manual_pdf(self, *_args):
        # Use the packaged PDF generated with the same correctly shaped manual
        # pages shown in Help.  No Pillow/RAQM dependency is needed at runtime.
        source = Path(__file__).resolve().parent / "assets" / "manual" / "calcy_user_manual.pdf"
        if not source.exists():
            self.status.text = "User manual PDF is missing from the application"
            return
        payload = source.read_bytes()
        android_uri = self._android_download("calcy_user_manual.pdf", payload, "application/pdf")
        if android_uri:
            self.status.text = "User manual exported to Download/Calcy/calcy_user_manual.pdf"
            return
        path = Path(self.user_data_dir) / "calcy_user_manual.pdf"
        path.write_bytes(payload)
        self.status.text = f"User manual exported: {path}"

    def _table_rows_text(self):
        t, states = self.controller.times, self.controller.states
        if not t:
            return ""
        lines = ["Calcy numerical table", "name: " + self.controller.name, "",
                 "sample\tt\t" + "\t".join(f"y{i+1}" for i in range(len(states)))]
        for i, xv in enumerate(t):
            lines.append(str(i) + "\t" + f"{xv:.12g}" + "\t" + "\t".join(f"{s[i]:.12g}" for s in states))
        return "\n".join(lines) + "\n"

    def _android_download(self, filename, payload, mime_type):
        """Write an export into the user's Android Download/Calcy folder.

        MediaStore is used on modern Android so no broad storage permission is
        required. On desktop this returns None and the normal local path is used.
        """
        import sys
        if "android" not in sys.platform:
            return None
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            MediaStore = autoclass("android.provider.MediaStore")
            ContentValues = autoclass("android.content.ContentValues")
            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()
            values = ContentValues()
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, filename)
            values.put(MediaStore.MediaColumns.MIME_TYPE, mime_type)
            values.put(MediaStore.MediaColumns.RELATIVE_PATH, "Download/Calcy")
            uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            if uri is None:
                return None
            stream = resolver.openOutputStream(uri)
            stream.write(payload)
            stream.close()
            return str(uri.toString())
        except Exception:
            return None

    def _export_table_txt(self, *_args):
        if not self.controller.times:
            self.status.text = "Solve a problem first."
            return
        payload = self._table_rows_text().encode("utf-8")
        android_uri = self._android_download("calcy_table.txt", payload, "text/plain")
        if android_uri:
            self.status.text = "Table exported to Download/Calcy/calcy_table.txt"
            return
        from pathlib import Path
        path = Path(self.user_data_dir) / "calcy_table.txt"
        path.write_bytes(payload)
        self.status.text = f"Table exported: {path}"

    def _export_table_pdf(self, *_args):
        if not self.controller.times:
            self.status.text = "Solve a problem first."
            return
        lines = self._table_rows_text().splitlines()
        # Small dependency-free PDF writer: the table is wrapped into pages.
        # It intentionally uses ASCII text so it remains portable on Android.
        lines_per_page = 52
        pages = [lines[i:i+lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[]]
        objects = []
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        page_ids = []
        next_id = 3 + 2 * len(pages)
        font_id = next_id
        objects.append(b"<< /Type /Pages /Kids [" + b" ".join(f"{3+2*i} 0 R".encode() for i in range(len(pages))) + b"] /Count " + str(len(pages)).encode() + b" >>")
        for i, chunk in enumerate(pages):
            pid = 3 + 2*i
            cid = pid + 1
            page_ids.append(pid)
            stream = ["BT", "/F1 8 Tf", "36 806 Td", "10 TL"]
            for line in chunk:
                safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                stream.append(f"({safe[:145]}) Tj T*")
            stream.append("ET")
            data = "\n".join(stream).encode("latin-1", "replace")
            objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {cid} 0 R >>".encode())
            objects.append(b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for n, obj in enumerate(objects, 1):
            offsets.append(len(out))
            out.extend(f"{n} 0 obj\n".encode()); out.extend(obj); out.extend(b"\nendobj\n")
        xref = len(out)
        out.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
        for off in offsets[1:]: out.extend(f"{off:010d} 00000 n \n".encode())
        out.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        android_uri = self._android_download("calcy_table.pdf", bytes(out), "application/pdf")
        if android_uri:
            self.status.text = "PDF exported to Download/Calcy/calcy_table.pdf"
            return
        from pathlib import Path
        path = Path(self.user_data_dir) / "calcy_table.pdf"
        path.write_bytes(out)
        self.status.text = f"PDF exported: {path}"


if __name__ == "__main__":
    CalcyApp().run()
