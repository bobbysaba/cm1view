"""Figure editor: what follows the Panels tab's choices: what the rows and columns
step through (runs, sections, times, fields, heights), the fields of each, the
heights, the size, the panel kind, the area and automatic titles.

A mixin of the FigureEditor (figures/editor.py)."""

import json

import numpy as np
import panel as pn

from .. import config
from . import draw as figdraw, spec as fg
from .cards import (EXTEND, FIG_CMAPS, FIG_LOCS, GRID_DIMS, LEVEL_MODES, LOCS,
                    SectionCard, _f, _grid, _hint, _keep_shown)
from .times import _heights
from ..viewer.ui import held


PF_KEYS = ("field", "cmap", "vmin", "vmax", "mode", "z", "extend")  # (a new panel's: the fill's)
NOT_IN = {"plan": "sections", "xsec": "heights"}  # (a plan view has no section, a section
#                                                    every height)


class FigurePanelOpts:
    """Reacting to the Panels tab: grid, fields, heights, layout, size, kind, area."""

    # ------------------------------------------------------------ rows and columns
    def _axes(self):
        """(rows, columns): what each steps through (figdraw.grid_axes; "none" for
        panels other than plan views: sections have a card per panel)."""
        if self.kind.value != "plan":
            return "none", "none"
        return self.g_rows.value, self.g_cols.value

    def _uses(self, d):
        """Whether the rows or the columns step through d ("runs", "times", ...)."""
        return d != "none" and d in self._axes()

    def _dim_count(self, d):
        """How many steps of d the grid has room for: the rows (or columns) it is,
        or every panel when the other is "none"; 0 when the grid does not use it."""
        rd, cd = self._axes()
        r, c = int(self.rows.value or 1), int(self.cols.value or 1)
        if not self._uses(d):
            return 0
        if rd != "none" and cd != "none":
            return r if d == rd else c
        return r * c

    def _step_name(self, d, i):
        """The name of step i of d's list: its row, its column, or its panel."""
        rd, cd = self._axes()
        if rd != "none" and cd != "none":
            return f"{'Row' if d == rd else 'Column'} {i + 1}"
        return f"Panel {figdraw.panel_letter(i, '{a}')}"

    def _forced(self, d):
        """The number of steps of d its own list sets (runs picked, sections,
        heights typed), or None (times and fields: as many as the grid has room for)."""
        if d == "runs":
            return len(self._grid_runs())
        if d == "sections":
            return max(1, len(self.sec_cards))
        if d == "heights":
            try:
                return len(_heights(self.pz.value)) or None
            except ValueError:
                return None  # (the status line says what is wrong)
        return None

    def _fit_axes(self):
        """Rows and columns for the lists that set their own number: as many rows
        (columns) as runs, sections or heights; one list filling the grid row by row:
        a grid with a cell for each (and no empty row).  Those set so cannot be typed."""
        rd, cd = self._axes()
        r0, c0 = int(self.rows.value or 1), int(self.cols.value or 1)
        r, c = r0, c0
        both = rd != "none" and cd != "none"
        if both:
            r, c = self._forced(rd) or r, self._forced(cd) or c
        else:
            d = rd if rd != "none" else cd
            n = self._forced(d) if d != "none" else None
            if n and (r * c < n or r * c - n >= c):
                r, c = (1, n) if n <= 4 else (-(-n // 3), 3)
        r, c = min(r, 8), min(c, 8)
        if (r, c) != (r0, c0):
            with held(self):
                self.rows.value, self.cols.value = r, c
        self.rows.disabled = both and self._forced(rd) is not None
        self.cols.disabled = both and self._forced(cd) is not None

    def _valid_axes(self):
        """Rows and columns this kind of panel can step through (a plan view: no
        sections; a section: no heights; those become times, or none)."""
        bad = NOT_IN.get(self.kind.value)
        opts = {k: v for k, v in GRID_DIMS.items() if v != bad}
        r, c = self.g_rows.value, self.g_cols.value  # (before new options reset them)
        if r == bad:
            r = "times" if c != "times" else "none"
        if c == bad:
            c = "times" if r != "times" else "none"
        with held(self):
            for w, v in ((self.g_rows, r), (self.g_cols, c)):
                if list(w.options) != list(opts):
                    w.options = opts
                w.value = v

    def _on_axis(self, other, new):
        """Rows or columns now step through `new`: the other no longer does."""
        if self._hold:
            return
        if new != "none" and other.value == new:
            with held(self):
                other.value = "none"
        self._on_vary()
        typed = [w.value.strip() for w in self.title_ws + self.row_ws]
        was = getattr(self, "_auto_typed", None)  # (row labels go with the grid of two: what
        auto = not any(typed) or (was is not None  # is left of them still counts as written so)
                                  and set(x for x in typed if x) <= set(was))
        if "none" not in self._axes() and auto:  # (nothing typed, or what was written so)
            rl = self.rl_on.value
            self._auto_titles()  # (a grid of rows and columns: label them, as a start)
            self._auto_typed = [x for x in (w.value.strip() for w in self.title_ws
                                            + self.row_ws) if x]
            self._rl_auto = getattr(self, "_rl_auto", False) or (rl and not self.rl_on.value)
        elif "none" in self._axes() and getattr(self, "_auto_typed", None) is not None:
            if auto:  # (no longer a grid of two: its automatic labels go, run names back)
                self._set_titles([])
                if getattr(self, "_rl_auto", False):
                    self.rl_on.value = True
            self._auto_typed, self._rl_auto = None, False

    # ------------------------------------------------------------ panel fields
    def _pf_fill(self):
        """A new fill layer (reflectivity when the run has it)."""
        F = self.fields
        return fg.layer_defaults("fill", F, "dbz" if "dbz" in F else next(iter(F.defs)))

    def _pf_sync(self):
        """A 'field' figure's fill is set panel by panel here (Time and fields), so it is
        not a Layers card (the Layers tab adds what goes over it): going to 'field'
        takes the first fill card out of Layers, going back puts it back first, as
        panel a had it."""
        field = self._uses("fields")
        if field and self._pf_base is None:
            c = next((c for c in self.cards if c.type == "fill"), None)
            if c is not None:
                self.cards.remove(c)
            self._pf_base = c.collect() if c is not None else self._pf_fill()
        elif not field and self._pf_base is not None:
            pf = self._pf_collect(self.pf_rows[0]) if self.pf_rows else {}
            self.cards.insert(0, self._card(dict(self._pf_base, **pf)))
            self._pf_base = None
        else:
            return
        self._show_cards()

    def _build_pf(self, fills):
        n = self._dim_count("fields")
        base = self._pf_base or self._pf_fill()
        new = {k: base.get(k) for k in PF_KEYS}
        rows = [self._pf_row(i, dict(new, **(fills[i] if i < len(fills) else {})))
                for i in range(n)]
        self.pf_rows = rows
        head = [_hint("The fill of each panel (row, column). The Layers tab adds what is "
                      "drawn over it (contours, vectors, another fill …).")] if rows else []
        self.pf_box.objects = head + [r["panel"] for r in rows]
        self._pf_show()

    def _pf_show(self):
        """A section has no level or height to choose (it samples every height)."""
        xs = self.kind.value == "xsec"
        for r in self.pf_rows:
            m = r["mode"].value
            r["mode"].visible = not xs
            r["z"].visible = not xs and m in ("height", "level")
            r["z"].name = "Model level (k)" if m == "level" else "Height (km)"

    def _pf_row(self, i, pf):
        F = self.fields
        r = dict(
            field=pn.widgets.Select(name=f"{self._step_name('fields', i)}: field",
                                    groups=F.groups(), value=pf["field"]),
            cmap=pn.widgets.Select(name="Colormap", options=FIG_CMAPS,
                                   value=pf["cmap"] if pf["cmap"] in FIG_CMAPS else "viridis"),
            vmin=_f("Min", float(pf["vmin"])), vmax=_f("Max", float(pf["vmax"])),
            mode=pn.widgets.Select(name="Level", options=LEVEL_MODES,
                                   value=pf.get("mode") or "height"),
            z=_f("Height (km)", float(pf.get("z") or 1.0), step=0.25),
            extend=pn.widgets.Select(name="Colorbar arrows", options=EXTEND,
                                     value=pf.get("extend") or "auto"),
            cbar_label=pn.widgets.TextInput(name="Colorbar label (blank: units)",
                                            value=pf.get("cbar_label", "") or ""),
            cbar_ticks=pn.widgets.TextInput(name="Colorbar ticks (blank: auto)",
                                            value=pf.get("cbar_ticks", "") or "",
                                            placeholder="0:60:10"))

        def on_field(ev):
            d = fg.layer_defaults("fill", F, ev.new)
            with held(self):
                r["cmap"].value = d["cmap"] if d["cmap"] in FIG_CMAPS else "viridis"
                r["vmin"].value, r["vmax"].value = d["vmin"], d["vmax"]
                r["cbar_label"].placeholder = d["units"]
            self.request()

        r["field"].param.watch(on_field, "value")
        r["mode"].param.watch(lambda e: self._pf_show(), "value")
        for k in ("cmap", "vmin", "vmax", "mode", "z", "extend", "cbar_label", "cbar_ticks"):
            r[k].param.watch(lambda e: self.request(), "value")
        r["cbar_label"].placeholder = fg.layer_defaults("fill", F, pf["field"])["units"]
        r["panel"] = _grid((r["field"], 2), r["cmap"], r["vmin"], r["vmax"],
                           r["mode"], r["z"], r["extend"], (r["cbar_ticks"], 2),
                           (r["cbar_label"], 3), n=5)
        return r

    def _pf_collect(self, r):
        # the panel's own field defaults (blanking) override the shared fill layer's
        # (e.g. reflectivity's "blank where <= 0")
        d = fg.layer_defaults("fill", self.fields, r["field"].value)
        return dict(field=r["field"].value, cmap=r["cmap"].value, vmin=float(r["vmin"].value),
                    vmax=float(r["vmax"].value), mode=r["mode"].value,
                    z=float(r["z"].value or 0.0), units=d["units"],
                    mask_below=d["mask_below"], extend=r["extend"].value, white_first=False,
                    reverse=False, cbar_label=r["cbar_label"].value,
                    cbar_ticks=r["cbar_ticks"].value)

    # ------------------------------------------------------------ panel heights
    def _on_heights(self):
        """New panel heights: a row, column or cell for each (_fit_axes)."""
        if self._hold:
            return
        if self._uses("heights"):
            self._on_layout()
        else:
            self.request()

    def _on_zmode(self):
        """Panels at model levels instead of heights, or back: the panels' heights
        become the nearest levels of the panels' run (and back)."""
        if self._hold:
            return
        try:
            vals = _heights(self.pz.value)
        except ValueError:
            vals = []
        z = np.asarray(self._sel_run().z, dtype=float)  # (km, at the levels)
        if self.pz_mode.value == "level":
            new = [int(np.argmin(np.abs(z - v))) for v in vals]
        else:
            new = [round(float(z[min(max(int(round(v)), 0), z.size - 1)]), 2) for v in vals]
        with held(self):
            self.pz.value = ", ".join(f"{v:g}" for v in new)
        self._show_vary()
        self.request()

    def _show_storm(self):
        """The skew-T and hodograph sections of the panels' layout, the custom storm
        motion's u, v, the inset's place, the hodograph's view, and what only a full
        hodograph draws (with its key: the key's place, columns and frame)."""
        sk, lay = self.sk, self.sk["layout"].value
        self.skewt_sec.visible = lay != "hodo"
        self.hodo_sec.visible = lay != "skewt"
        sk["storm_u"].visible = sk["storm_v"].visible = sk["storm"].value == "custom"
        sk["inset_loc"].visible = sk["inset_size"].visible = lay == "inset"
        sk["hodo_max"].visible = sk["hodo_center"].value != "fit"
        sk["hodo_cu"].visible = sk["hodo_cv"].visible = sk["hodo_center"].value == "custom"
        sk["inset_x"].visible = sk["inset_y"].visible = \
            lay == "inset" and sk["inset_loc"].value == "custom"
        sk["hodo_heights"].visible = sk["hodo_labels"].value
        sk["hodo_key"].visible = sk["srh"].visible = lay in ("side", "hodo")
        for k in ("hodo_key_loc", "hodo_key_ncol", "hodo_key_frame"):
            sk[k].visible = lay in ("side", "hodo") and sk["hodo_key"].value

    def _sync_code(self, text):
        """The highlighted editor and the plain box hold the same code."""
        for w in (self.code, self.code_plain):
            if w.value != text:
                w.value = text

    def _show_code(self, save=False):
        plain = bool(self.code_box.value)
        self.code.visible, self.code_plain.visible = not plain, plain
        if save:  # (remembered for the next figures)
            config.set_state("figure_code_plain", "1" if plain else "")

    # ------------------------------------------------------------ events
    def _on_layout(self):
        """New grid of panels: rows and columns for the lists, then a picker per
        time and field."""
        if self._hold:
            return
        self._fit_axes()
        self._pf_sync()
        self._show_vary()
        self._build_times()
        self._build_pf([self._pf_collect(r) for r in self.pf_rows])
        self._build_titles()
        if self._uses("fields") and self.cb_mode.value == "shared":  # (a colorbar a field)
            rd, cd = self._axes()
            self.cb_mode.value = "row" if rd == "fields" and cd != "none" else \
                "col" if cd == "fields" and rd != "none" else "each"
        self._fit_size()
        self.request()

    def _on_vary(self):
        """New panel arrangement."""
        if self._hold:
            return
        self._on_layout()

    def _show_vary(self):
        """The Panels tab's lists for what the rows and columns step through."""
        kind = self.kind.value
        maps = kind in ("plan", "xsec")
        if kind == "plan":
            self._valid_axes()
        rd, cd = self._axes()
        both = rd != "none" and cd != "none"
        self.g_rows.visible = self.g_cols.visible = self.grid_hint.visible = kind == "plan"
        # (sections: each card's run and time; a 3D scene: the Time section's)
        self.times_sec.visible = kind in ("plan", "scene")
        self.xsec_col.visible = kind == "xsec"
        self.scene_col.visible = kind == "scene"
        for w in (self.rows, self.cols, self.fit_btn):  # (one 3D picture)
            w.visible = kind != "scene"
        times, runs = self._uses("times"), self._uses("runs")
        words = (["runs"] if runs else []) + ["times" if times else "time"] + \
            [d for d in ("fields", "heights") if self._uses(d)]
        title = ", ".join(words[:-1]) + " and " + words[-1] if len(words) > 1 else words[0]
        self.times_sec.title = title[0].upper() + title[1:]

        def per(d):  # (one per row / column / panel)
            return "row" if both and d == rd else "column" if both else "panel"
        self.tm_box.visible = self.tstep.visible = self.tfill.visible = times
        self.time1.visible = not times
        self.gg_runs.visible = runs
        self.gg_runs.name = f"Runs, one per {per('runs')}"
        hz = self._uses("heights")
        self.pz.visible = self.pz_mode.visible = hz
        self.pz.name = (f"Model levels (k), one per {per('heights')}"
                        if self.pz_mode.value == "level"
                        else f"Heights (km), one per {per('heights')}")
        self.zl_on.visible = hz and maps
        self.pf_box.visible = self._uses("fields")
        self._pf_show()
        self.run_sel.visible = (len(self.run_rows) > 1 or bool(self._other_runs())) and \
            not runs and kind in ("plan", "scene")
        self.plan_layers.visible = self.area_sec.visible = maps
        self.series_col.visible = self.ts_sec.visible = kind in ("th", "line")
        self.ts_sec.title = "Time and height axes" if kind == "th" else "Time and value axes"
        self.ts_zmin.visible = self.ts_zmax.visible = kind == "th"
        for w in (self.ts_ymin, self.ts_ymax, self.ts_zero, self.ts_legend, self.ts_legloc,
                  self.ts_legncol, self.ts_legframe, self.ts_mark, self.ts_mark_legend,
                  self.ts_mark_edited):
            w.visible = kind == "line"
        self.ext_sec.visible = kind in ("plan", "xsec", "th")
        if hasattr(self, "cb_sec"):  # (Style tab: no colorbar on lines and soundings)
            self.cb_sec.visible = kind not in ("line", "sounding", "dist", "profile", "scene")
        self.snd_col.visible = kind == "sounding"
        self.dist_col.visible = kind == "dist"
        self.prof_col.visible = kind == "profile"
        self.joint_col.visible = kind == "joint"
        self.azim_col.visible = kind == "azim"
        self._show_dist_opts()
        self._show_joint_opts()
        self.equal.visible = kind == "plan"
        for k in ("track", "line", "sector"):  # plan views only
            self.add_btns[k].visible = kind == "plan"
        for c in self.cards:
            c.show(kind)
            c._set_title()
        if hasattr(self, "runs_sec"):  # (series: the cards pick runs and tracks)
            self.runs_sec.visible = kind not in ("th", "line")
        self._show_sections()
        self._show_region()

    def _keep_tabs(self):
        """The Layers and Panels tabs hold only what is shown (the figure kind's columns
        and sections)."""
        if hasattr(self, "layers_tab"):
            _keep_shown(self.layers_tab, self.layers_all)
        if hasattr(self, "panels_tab"):
            _keep_shown(self.panels_tab, self.panels_all)
            _keep_shown(self.area_body, self.area_all)

    def _show_dist_opts(self):
        """The distribution plot settings the chosen kind of plot uses."""
        ds, plot = self.ds, self.ds["plot"].value
        hist, cum, boxy = plot == "hist", plot == "ecdf", plot in ("box", "violin")
        for k in ("norm", "bins", "width", "hstyle", "bar_labels"):
            ds[k].visible = hist
        ds["cum"].visible = cum
        ds["whis"].visible = ds["means"].visible = ds["horizontal"].visible = boxy
        ds["ymin"].visible = ds["ymax"].visible = not boxy
        ds["ymin"].name = "Fraction axis from" if cum else "Count axis from"
        ds["ymax"].name = "Fraction axis to" if cum else "Count axis to"
        for k in ("legend", "legend_loc", "legend_ncol", "legend_frame"):
            ds[k].visible = not boxy
        ds["stats_loc"].visible = ds["stats_at"].value == "box"

    def _show_joint_opts(self):
        """The joint distribution plot settings the chosen kind of plot uses."""
        jo, plot = self.jo, self.jo["plot"].value
        hist, scatter = plot == "hist", plot == "scatter"
        for k in ("norm", "cmap", "log", "reverse", "colorbar"):
            jo[k].visible = hist
        jo["ms"].visible = jo["alpha"].visible = scatter
        jo["contours"].visible = plot != "contour"

    def _show_legend(self):
        """The legend settings the chosen place (a panel's axes or the figure) uses."""
        fig = self.lg_where.value == "figure"
        self.lg_panel.visible = self.lg_own.visible = not fig
        self.lg_from.visible = fig
        self.lg_loc.options = LOCS + FIG_LOCS if fig else LOCS

    def _show_cbar(self):
        self.cb_opts.visible = self.cb_mode.value != "none"

    def _on_preset(self, ev):
        """A size preset: its width (the height keeps the figure's shape), or both."""
        if self._hold or not ev.new:
            return
        if "x" in ev.new:
            w, h = (float(v) for v in ev.new.split("x"))
        else:
            w = float(ev.new)
            s = self.collect()
            h = self.fit_height(dict(s, size=[w, s["size"][1]]))
        with held(self):
            self.width.value, self.height.value = round(w, 2), round(h, 2)
        self._auto_size = "x" not in ev.new  # a width: the height still follows
        self.request()

    def _refit(self):
        """Fit the height, and keep fitting it as the figure changes."""
        self._auto_size = True
        self._follow_size()
        self.request()

    def _follow_size(self):
        """Plan views and sections with an automatic size: the height for the width."""
        if not self._auto_size or self.kind.value not in ("plan", "xsec"):
            return
        h = self.fit_height()
        if abs(h - float(self.height.value or 0)) > 0.02:
            with held(self):
                self.height.value = h

    def _panel_shape(self, s):
        """Height / width of a panel's plotting area: the plan-view area at equal
        scale, else a usual shape for the kind of panel."""
        if s["kind"] == "plan" and s["axes"].get("equal", True):
            d, run = s["domain"], self.run
            if d["mode"] == "box" and d.get("box"):
                x0, x1, y0, y1 = d["box"]
            elif d["mode"] == "full":
                x0, x1, y0, y1 = run.xh[0], run.xh[-1], run.yh[0], run.yh[-1]
            else:
                return 1.0
            return abs(y1 - y0) / max(abs(x1 - x0), 1e-6)
        return {"xsec": 0.5, "th": 0.55, "line": 0.45, "sounding": 1.0,
                "dist": 0.7, "profile": 1.3, "joint": 0.85,
                "azim": 0.8, "scene": 0.8}.get(s["kind"], 0.75)

    def fit_height(self, s=None):
        """A figure height (in) that fits the panels at the figure's width: their shape
        plus room for tick labels, titles and colorbars (an estimate: the layout engine
        does the rest)."""
        s = s or self.collect()
        w, r, c = float(s["size"][0]), int(s["rows"]), int(s["cols"])
        line = float(s["font"].get("size", 10)) / 72.0  # a line of text (in)
        outer = s["axes"].get("ticklabels", "all") != "all"
        left, right, bottom, top = 4.5 * line, 0.15, 3.6 * line, 0.15
        gx, gy = (0.15, 0.15) if outer else (4.2 * line, 3.6 * line)
        if s.get("titles") or (s["letters"].get("on") and
                               str(s["letters"].get("loc", "")).startswith("above")):
            top += 1.6 * line
            gy += 1.6 * line
        if s.get("suptitle"):
            top += 2.2 * line
        if s.get("row_titles"):
            left += 1.6 * line
        cb = s["colorbar"]
        mode = cb.get("mode", "shared") if s["kind"] in ("plan", "xsec", "th") else "none"
        side = (cb.get("location") or ("bottom" if cb.get("orientation", "horizontal")
                                       == "horizontal" else "right")) in ("left", "right")
        if mode != "none":
            if side:
                right += 0.9
                gx += 0.9 if mode in ("each", "col") else 0.0
            else:
                bottom += 0.8
                gy += 0.8 if mode in ("each", "row") else 0.0
        pw = max(0.3, (w - left - right - (c - 1) * gx) / c)
        return round(max(1.0, bottom + top + r * pw * self._panel_shape(s) + (r - 1) * gy), 2)

    def _on_kind(self, render_=True):
        kind = self.kind.value
        if render_ and not self._hold:
            with held(self):
                self.xlabel.placeholder = ""
                if kind == "xsec":  # (blank: x, y or the distance, as each section runs)
                    self.xlabel.value, self.ylabel.value = "", "height (km)"
                    self.xlabel.placeholder = "blank: as each section runs"
                elif kind == "plan":
                    self.xlabel.value, self.ylabel.value = "x (km)", "y (km)"
                elif kind in ("th", "line"):
                    self.xlabel.value = "time (min)"
                    self.ylabel.value = "height (km)" if kind == "th" else ""
                    self.tl_on.value = False
                    if kind == "th":
                        self.cb_mode.value, self.cb_loc.value = "row", "right"
                    else:
                        self.cb_mode.value = "none"
                elif kind == "dist":
                    self.xlabel.value = self.ylabel.value = ""  # (the field's, the plot's)
                    self.cb_mode.value = "none"
                elif kind == "profile":
                    self.xlabel.value, self.ylabel.value = "", "height (km)"  # (x: the field's)
                    self.cb_mode.value = "none"
                elif kind in ("joint", "azim", "scene"):  # (the fields' / radius,
                    self.xlabel.value = self.ylabel.value = ""  # height; the panel's or
                    self.cb_mode.value = "none"  # the scene's own colorbars and axes)
                else:
                    self.xlabel.value, self.ylabel.value = "temperature (°C)", "pressure (hPa)"
                    self.cb_mode.value = "none"
            if kind == "sounding" and not self.snd_cards:
                self.snd_cards = [self._snd_card(e) for e in self.tab_soundings()]
                if not self.snd_cards:
                    self._add_sounding()
            if kind == "dist" and not self.dist_cards:
                self.dist_cards = [self._dist_card(e) for e in self.tab_dists()]
                if not self.dist_cards:
                    self._add_dist()
            if kind == "profile" and not self.prof_cards:
                self.prof_cards = [self._prof_card(e) for e in self.tab_profiles()]
                if not self.prof_cards:
                    self._add_profile()
            if kind == "joint" and not self.joint_cards:
                self._add_joint()
            if kind == "azim" and not self.azim_cards:
                self._add_azim()
            if kind == "scene" and not self.iso_rows:  # (a start: the 3D view's)
                self._scene_set(self.viewer_scene())
            grid = kind == "xsec" and (self._quick_xsec  # (the quick start: its own)
                                       or self._cards_from_grid())
            if kind == "th":  # (a card per panel: one run each)
                self._th_cards_from_line()
            elif kind == "line":  # (a series' cards: one card of their runs)
                self._line_cards_from_th()
            self._show_series()
            self._show_soundings()
            self._show_dists()
            self._show_profiles()
            self._show_joints()
            self._show_azims()
            self._auto_size = True
            self._fit_grid(reset=not grid)  # (cards from the plan views: their grid)
            self._fit_size()
            self._show_vary()
            self._fit_axes()
            self._build_times()
            self._build_titles()
            self._show_cbar()
            self.request()
        self._show_vary()
        if self._multi_part():
            self._show_parts()  # (the part's kind in its name)

    def _on_dom(self, ev):
        if ev.new == "box" and not self.spec["domain"].get("box"):
            self._set_box([float(v) for v in self.v.view])  # (a start: the map's view)
        self._show_region()
        self.request()

    def _set_box(self, box):
        """The fixed box [x0, x1, y0, y1] (grid km), in the spec and its fields."""
        self.spec["domain"] = dict(self.spec["domain"], box=[round(v, 2) for v in box])
        with held(self):
            for w, v in zip((self.box_x0, self.box_x1, self.box_y0, self.box_y1),
                            self.spec["domain"]["box"]):
                w.value = v

    def _on_box(self):
        if self._hold:
            return
        b = [w.value for w in (self.box_x0, self.box_x1, self.box_y0, self.box_y1)]
        ok = None not in b and b[1] > b[0] and b[3] > b[2]
        self.box_html.object = "" if ok else (
            '<div class="cv-status" style="color:#f87171">The box needs x max above '
            'x min and y max above y min.</div>')
        if ok:
            self.spec["domain"] = dict(self.spec["domain"], box=[float(v) for v in b])
            self.request()

    # ------------------------------------------------------------ sections
    def _sec_card(self, e):
        c = SectionCard(self, e)
        c.rm.on_click(lambda ev: self._remove_section(c))
        c.ab.on_click(lambda ev: self._use_ab(c))
        c.dup.on_click(lambda ev: self._dup_section(c))
        c.per_run.on_click(lambda ev: self._per_run_section(c))
        return c

    def _sec_cards(self, ents):
        """Section cards for entries ents: the cards there are, then the ones left over
        before (the browser may still have their widgets), show the first ones; new
        cards the rest."""
        old = self.sec_cards + [c for c in self._sec_spare if c not in self.sec_cards]
        for c, e in zip(old, ents):
            c.load(e)
        self._sec_spare = old[len(ents):][:12]
        return old[:len(ents)] + [self._sec_card(e) for e in ents[len(old):]]

    def _cards_from_grid(self):
        """Plan views become sections: their one section (or a new one) as a card for
        each panel of their grid, at its run and time (sections.to_cards); True if so
        (several sections: they are the cards, as they are)."""
        if len(self.sec_cards) > 1:
            return False
        s = self.collect()  # (kind "xsec" already: the plan views' grid back)
        g = (self.g_rows.value, self.g_cols.value)
        s.update(grid=dict(rows=g[0], cols=g[1],
                           runs=self._grid_runs() if "runs" in g else []),
                 sections=[fg.card_section(c.collect()) for c in self.sec_cards]
                 or [fg.section_defaults()])
        fg.to_cards(s)
        self.sec_cards = self._sec_cards(s["sections"])
        return True

    def _show_sections(self):
        """The section cards: a section figure's in Layers (one per panel), a plan
        view's (its Section line layer's) in Panels → Area."""
        runs = self._runs_collect() if self.run_rows else self.spec.get("runs") or []
        tracked = any(e.get("track") for e in runs)
        for c in self.sec_cards:
            c.rm.visible = len(self.sec_cards) > 1
            c.tracked(tracked)
        objs = [c.panel for c in self.sec_cards]
        box, other = (self.xsec_box, self.sec_box) if self.kind.value == "xsec" \
            else (self.sec_box, self.xsec_box)
        if list(other.objects):
            other.objects = []
        if list(box.objects) != objs:
            box.objects = objs

    def _free_panel(self, start=0):
        """The first panel number from `start` no section card is in."""
        used = {int(c.w["panel"].value or 1) - 1 for c in self.sec_cards}
        p = start
        while p in used:
            p += 1
        return p

    def _new_sections(self, ents, wide=False):
        """Cards for section entries ents, after the others (wide: a grid of one row
        widens for them)."""
        self.sec_cards += [self._sec_card(e) for e in ents]
        self._show_sections()
        self._show_region()
        self._fit_grid(wide=wide)
        self._build_titles()
        self.request()

    def _add_section(self):
        """A new section like the last (an x–z one's y–z twin, along the motion's across
        one, and back); in a section figure at its run and time, in a new panel."""
        last = self.sec_cards[-1].collect() if self.sec_cards else fg.section_defaults()
        swap = {"x": "y", "y": "x", "along": "across", "across": "along"}
        e = dict(last, label="", orient=swap.get(last["orient"], last["orient"]),
                 panel=self._free_panel())
        self._new_sections([e], wide=True)

    def _dup_section(self, c):
        """A copy of card c in a new panel."""
        self._new_sections([dict(c.collect(), panel=self._free_panel())], wide=True)

    def _per_run_section(self, c):
        """A copy of card c for each other run of the figure (one with the same
        section there already: skipped), down c's column: run j's in row j after c's
        (or the next free panel)."""
        s = c.collect()
        others = [k for k in self._run_names().values() if k != s["run"]]
        if not others:
            self._msg("The figure has one run: add others first (a card's <b>Run</b> list, "
                      "or <b>Layers → Runs used → + Add run</b>).", True)
            return
        have = {(x["run"], json.dumps(fg.card_section(x), sort_keys=True, default=float))
                for x in (y.collect() for y in self.sec_cards)}
        C = int(self.cols.value or 1)
        row, col = divmod(s["panel"], C)
        new, taken = [], {int(x.w["panel"].value or 1) - 1 for x in self.sec_cards}
        for j, k in enumerate(others):
            if (k, json.dumps(fg.card_section(s), sort_keys=True, default=float)) in have:
                continue
            p = (row + j + 1) * C + col
            while p in taken:
                p += 1
            taken.add(p)
            new.append(dict(s, run=k, panel=p))  # (its time: the run's nearest)
        if not new:
            self._msg("Every run has this section already.", True)
            return
        self._new_sections(new)

    def _remove_section(self, c):
        """Remove section c; panels showing a later one keep it (their index moves)."""
        k = self.sec_cards.index(c)
        self.sec_cards.remove(c)
        for e in self.edits.values():
            if e.get("section") is not None:
                n = int(e["section"])
                e["section"] = None if n == k else (n - 1 if n > k else n)
        self._show_sections()
        self._show_region()
        self._tree_sync(force=True)
        self._sections_changed()

    def _sections_changed(self):
        """Sections added or removed: a row or column of sections follows (a section
        figure: its grid)."""
        if self.kind.value == "xsec":
            self._fit_grid()
            self._build_titles()
            self.request()
        elif self._uses("sections"):
            self._on_layout()
        else:
            self.request()

    def _ab_card(self):
        """The first A–B section (the only section, or a new one, if there is none)."""
        c = next((c for c in self.sec_cards if c.w["orient"].value == "ab"), None)
        if c is None and len(self.sec_cards) == 1:
            c = self.sec_cards[0]
        if c is None:
            last = self.sec_cards[-1].collect() if self.sec_cards else {}
            c = self._sec_card(fg.section_defaults(
                orient="ab", pos="fixed", run=last.get("run", 0), time_s=last.get("time_s"),
                panel=self._free_panel()))
            self.sec_cards.append(c)
            self._show_sections()
            self._fit_grid(wide=True)
        return c

    def _use_ab(self, c=None):
        pts = self.v.xs_pts
        if len(pts) != 2:
            self._msg("Draw a cross-section on the map first (Cross-section click mode, "
                      "points A and B).", True)
            return
        (c or self._ab_card()).set_ab(pts[0], pts[1])
        self._show_region()
        self.request()

    def _show_region(self):
        """The plan-view area (plan views) and the section (sections, and plan views
        showing the section line)."""
        kind = self.kind.value
        line = any(c.type == "line" and c.w["on"].value for c in self.cards)
        self.area_plan.visible = kind == "plan"
        self.area_xs.visible = kind == "xsec" or (kind == "plan" and line)
        self.sec_box.visible = self.sec_add.visible = kind == "plan"  # (sections: Layers)
        self.area_sec.title = "Section heights and axis" if kind == "xsec" else (
            "Area and section line" if line else "Area")
        self.half.visible = self.dom.value == "storm"
        for w in (self.box_x0, self.box_x1, self.box_y0, self.box_y1):
            w.visible = self.dom.value == "box"
        if self.dom.value != "box":
            self.box_html.object = ""
        if kind == "xsec":
            text = ("The sections themselves, one card per panel: <b>Layers → "
                    "Sections</b>.")
        elif self._uses("sections"):
            rd, cd = self._axes()
            where = "row" if rd == "sections" and cd != "none" else \
                "column" if cd == "sections" and rd != "none" else "panel"
            text = (f"A {where} for each section, in this order (a panel can show another: "
                    "panel tree → <b>Section</b>).")
        elif len(self.sec_cards) > 1:
            text = ("Each section panel shows the first section; pick another for a panel "
                    "in the panel tree (<b>Section</b>), or make the sections the rows or "
                    "columns (<b>Grid and size</b>).")
        else:
            text = ""
        self.xs_html.object = f'<div class="cv-hint">{text}</div>' if text else ""
        self._keep_tabs()

    def _auto_titles(self):
        s = self.collect()
        if s["kind"] == "th":
            ts = []
            for i in range(fg.npanels(s)):
                ref = figdraw.series_ref(s, i)
                ts.append(f"{s['runs'][ref[0]]['label']} – {s['series'][ref[1]]['label']}"
                          if ref else "")
            self.rl_on.value = False
            self._set_titles(ts)
            return
        if figdraw.xsec_cards(s) is not None:  # (a card's label or section, and run)
            multi = len({int(c.get("run") or 0) for c in s["sections"]}) > 1
            ts = []
            for i in range(fg.npanels(s)):
                kc = figdraw.xsec_card(s, i)
                if kc is None:
                    ts.append("")
                    continue
                words = [kc[1].get("label") or fg.describe(kc[1])]
                if multi:
                    words.insert(0, s["runs"][int(kc[1].get("run") or 0)]["label"])
                ts.append(" – ".join(words))
            if multi:
                self.rl_on.value = False  # (the titles name the runs now)
            self._set_titles(ts)
            return
        if s["kind"] in figdraw.ENTRIES:
            ents = s[figdraw.ENTRIES[s["kind"]]]
            ts = []
            for i in range(fg.npanels(s)):
                labs = [e.get("label", "") for e in ents if int(e.get("panel", 0)) == i]
                ts.append(" / ".join(dict.fromkeys(x for x in labs if x)) if s["kind"] == "line"
                          else "")
            self._set_titles(ts)
            return
        rd, cd = self._axes()
        if "none" not in (rd, cd):  # column titles on the top row, row labels at the left
            if self._uses("runs"):
                self.rl_on.value = False  # the labels name the runs now
            self._set_titles([self._item_words(s, item, True) if item else ""
                              for item in figdraw.dim_items(s, cd)][:int(s["cols"])],
                             [self._item_words(s, item, True) if item else ""
                              for item in figdraw.dim_items(s, rd)][:int(s["rows"])])
            return
        fill = next((lay for lay in s["layers"] if lay["type"] == "fill"), None)
        ts = []
        for i in range(fg.npanels(s)):
            cell = figdraw.grid_cell(s, i)
            if cell is None or fg.panel_ref(s, i) is None:
                ts.append("")
                continue
            words = self._item_words(s, cell)
            if not words and fill:  # (panels in time: the field; the time is labelled)
                words = self.fields[fill["field"]].label
            ts.append(words)
        if self._uses("runs"):
            self.rl_on.value = False  # the titles name the runs now
        self._set_titles(ts)

    def _item_words(self, s, cell, times=False):
        """The title words of a grid cell's (or a row's or column's) run, section,
        field and height (and with `times`, alone, its time)."""
        secs = fg.sections(s)
        words = []
        if "run" in cell:
            words.append(s["runs"][int(cell["run"])]["label"])
        if "section" in cell:
            sec = secs[int(cell["section"])]
            words.append(sec.get("label") or fg.describe(sec))
        if cell.get("fill"):
            words.append(self.fields[cell["fill"]["field"]].label)
        if cell.get("z") is not None:
            z = float(cell["z"])
            words.append(f"k = {int(round(z))}" if s.get("panel_zmode") == "level"
                         else f"{z:g} km")
        if times and not words and cell.get("time_s") is not None:
            words.append(figdraw.time_text(float(cell["time_s"]), s["time_label"]))
        return " – ".join(words)
