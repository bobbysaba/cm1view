"""Figure editor: what follows the Panels tab's choices: the fields of each panel, the
heights, the layout and what panels differ in, the size, the panel kind, the area
and automatic titles.

A mixin of the FigureEditor (figures/editor.py)."""

import numpy as np
import panel as pn

from .. import config
from . import draw as figdraw, spec as fg
from .cards import EXTEND, FIG_CMAPS, FIG_LOCS, LEVEL_MODES, LOCS, NONE, VARY, _f, _grid, _hint
from .times import _heights


PF_KEYS = ("field", "cmap", "vmin", "vmax", "mode", "z", "extend")  # (a new panel's: the fill's)


class FigurePanelOpts:
    """Reacting to the Panels tab: fields, heights, layout, size, kind, area."""

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
        field = self.vary.value == "field"
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
        n = int(self.rows.value or 1) * int(self.cols.value or 1)
        base = self._pf_base or self._pf_fill()
        new = {k: base.get(k) for k in PF_KEYS}
        rows = [self._pf_row(i, dict(new, **(fills[i] if i < len(fills) else {})))
                for i in range(n if self.vary.value == "field" else 0)]
        self.pf_rows = rows
        head = [_hint("The fill of each panel. The Layers tab adds what is drawn over it "
                      "(contours, vectors, another fill …).")] if rows else []
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
            field=pn.widgets.Select(name=f"Panel {figdraw.panel_letter(i, '{a}')}: field",
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
            self._hold = True
            try:
                r["cmap"].value = d["cmap"] if d["cmap"] in FIG_CMAPS else "viridis"
                r["vmin"].value, r["vmax"].value = d["vmin"], d["vmax"]
                r["cbar_label"].placeholder = d["units"]
            finally:
                self._hold = False
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
    def _on_heights(self, layout=False):
        """New panel heights: a grid with a cell for each (and no empty row)."""
        if self._hold:
            return
        try:
            n = len(_heights(self.pz.value))
        except ValueError:
            n = 0  # (the status line says what is wrong)
        r, c = int(self.rows.value or 1), int(self.cols.value or 1)
        if n and (r * c < n or r * c - n >= c):
            r, c = (1, n) if n <= 4 else (-(-n // 3), 3)
            hold, self._hold = self._hold, True
            try:
                self.rows.value, self.cols.value = r, c
            finally:
                self._hold = hold
            layout = True
        if layout:
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
        hold, self._hold = self._hold, True
        try:
            self.pz.value = ", ".join(f"{v:g}" for v in new)
        finally:
            self._hold = hold
        self._show_vary()
        self.request()

    def _show_storm(self):
        """The skew-T and hodograph sections of the panels' layout, the custom storm
        motion's u, v, the inset's place, the hodograph's view, and what only a full
        hodograph draws."""
        sk, lay = self.sk, self.sk["layout"].value
        self.skewt_sec.visible = lay != "hodo"
        self.hodo_sec.visible = lay != "skewt"
        sk["storm_u"].visible = sk["storm_v"].visible = sk["storm"].value == "custom"
        sk["inset_loc"].visible = sk["inset_size"].visible = lay == "inset"
        sk["hodo_max"].visible = sk["hodo_center"].value != "fit"
        sk["hodo_cu"].visible = sk["hodo_cv"].visible = sk["hodo_center"].value == "custom"
        sk["inset_x"].visible = sk["inset_y"].visible = \
            lay == "inset" and sk["inset_loc"].value == "custom"
        sk["hodo_key"].visible = sk["srh"].visible = lay in ("side", "hodo")

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
    def _on_layout(self, panels=None):
        """New grid of panels (panels: the {run, time_s} of each, for vary = custom)."""
        if self._hold:
            return
        field = self.vary.value == "field"
        self._pf_sync()
        self._show_vary()
        self._build_times()
        self._build_pf([self._pf_collect(r) for r in self.pf_rows])
        self._build_pc(panels or [])
        self._build_titles()
        if field and self.cb_mode.value == "shared":
            self.cb_mode.value = "each"
        self._fit_size()
        self.request()

    def _on_vary(self):
        """New panel arrangement."""
        if self._hold:
            return
        if self.kind.value == "th":
            self._th_grid()
            self._on_layout()
            return
        if self.vary.value == "height":
            self._on_heights(layout=True)
            return
        self._on_layout()

    def _show_vary(self):
        vary, kind = self.vary.value, self.kind.value
        maps = kind in ("plan", "xsec")
        self.vary.visible = maps
        self.times_sec.visible = maps
        self.times_sec.title = {
            "time": "Times (one per panel)", "field": "Time and fields",
            "height": "Time and heights",
            "custom": "Run and time of each panel"}.get(vary, "Times")
        self.tm_box.visible = self.tstep.visible = self.tfill.visible = \
            vary == "time"
        self.time1.visible = vary in ("field", "height")
        self.pz.visible = self.pz_mode.visible = vary == "height"
        self.pz.name = ("Model levels (k), one per panel" if self.pz_mode.value == "level"
                        else "Heights (km), one per panel")
        self.zl_on.visible = vary == "height" and maps
        self.pf_box.visible = vary == "field"
        self._pf_show()
        self.pc_box.visible = vary == "custom"
        self.runs_as.visible = kind == "th"
        self.grid_fill_sec.visible = maps
        self.run_sel.visible = (len(self.run_rows) > 1 or bool(self._other_runs())) and \
            vary in ("time", "field", "height") and maps
        opts = VARY if kind != "xsec" else {k: v for k, v in VARY.items() if v != "height"}
        if list(self.vary.options) != list(opts):  # (sections have no heights to vary)
            hold, self._hold = self._hold, True
            try:
                self.vary.options = opts
            finally:
                self._hold = hold
        self.plan_layers.visible = self.area_sec.visible = maps
        self.series_col.visible = self.ts_sec.visible = kind in ("th", "line")
        self.ts_sec.title = "Time and height axes" if kind == "th" else "Time and value axes"
        self.ts_zmin.visible = self.ts_zmax.visible = kind == "th"
        for w in (self.ts_ymin, self.ts_ymax, self.ts_zero, self.ts_legend, self.ts_legloc,
                  self.ts_legncol, self.ts_legframe, self.ts_mark, self.ts_mark_legend):
            w.visible = kind == "line"
        self.ext_sec.visible = kind in ("plan", "xsec", "th")
        self.snd_col.visible = kind == "sounding"
        self.dist_col.visible = kind == "dist"
        self._show_dist_opts()
        self.equal.visible = kind == "plan"
        for k in ("track", "line"):  # plan views only
            self.add_btns[k].visible = kind == "plan"
        for c in self.cards:
            c.show(kind)
            c._set_title()
        self._show_region()

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

    def _show_legend(self):
        """The legend settings the chosen place (a panel's axes or the figure) uses."""
        fig = self.lg_where.value == "figure"
        self.lg_panel.visible = not fig
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
        hold, self._hold = self._hold, True
        try:
            self.width.value, self.height.value = round(w, 2), round(h, 2)
        finally:
            self._hold = hold
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
            hold, self._hold = self._hold, True
            try:
                self.height.value = h
            finally:
                self._hold = hold

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
                "dist": 0.7}.get(s["kind"], 0.75)

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
            self._hold = True
            try:
                if kind == "xsec" and self.vary.value == "height":
                    self.vary.value = "time"
                if kind == "xsec":
                    self.xlabel.value = ("distance from storm (km)"
                                         if self.xs_mode.value == "storm" else "distance (km)")
                    self.ylabel.value = "height (km)"
                elif kind == "plan":
                    self.xlabel.value, self.ylabel.value = "x (km)", "y (km)"
                elif kind in ("th", "line"):
                    self.xlabel.value = "time (min)"
                    self.ylabel.value = "height (km)" if kind == "th" else ""
                    self.tl_on.value = False
                    if kind == "th":
                        self.runs_as.value = "cols"
                        self.cb_mode.value, self.cb_loc.value = "row", "right"
                    else:
                        self.cb_mode.value = "none"
                elif kind == "dist":
                    self.xlabel.value = self.ylabel.value = ""  # (the field's, the plot's)
                    self.cb_mode.value = "none"
                else:
                    self.xlabel.value, self.ylabel.value = "temperature (°C)", "pressure (hPa)"
                    self.cb_mode.value = "none"
            finally:
                self._hold = False
            if kind == "sounding" and not self.snd_cards:
                self.snd_cards = [self._snd_card(e) for e in self.tab_soundings()]
                if not self.snd_cards:
                    self._add_sounding()
            if kind == "dist" and not self.dist_cards:
                self.dist_cards = [self._dist_card(e) for e in self.tab_dists()]
                if not self.dist_cards:
                    self._add_dist()
            self._show_series()
            self._show_soundings()
            self._show_dists()
            self._auto_size = True
            if kind == "th":
                self._th_grid()
            else:
                self._fit_grid(reset=True)
            self._fit_size()
            self._show_vary()
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
        hold, self._hold = self._hold, True
        try:
            for w, v in zip((self.box_x0, self.box_x1, self.box_y0, self.box_y1),
                            self.spec["domain"]["box"]):
                w.value = v
        finally:
            self._hold = hold

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

    def _use_ab(self):
        pts = self.v.xs_pts
        if len(pts) != 2:
            self.xs_html.object = ('<div class="cv-status" style="color:#f87171">Draw a '
                                   'cross-section on the map first (Cross-section click '
                                   'mode, points A and B).</div>')
            return
        self.spec["xsec"] = dict(self.spec["xsec"], a=list(pts[0]), b=list(pts[1]))
        self.xs_mode.value = "fixed"
        self._show_region()
        self.request()

    def _show_region(self):
        """The plan-view area (plan views) and the section (sections, and plan views
        showing the section line)."""
        kind = self.kind.value
        line = any(c.type == "line" and c.w["on"].value for c in self.cards)
        self.area_plan.visible = kind == "plan"
        self.area_xs.visible = kind == "xsec" or (kind == "plan" and line)
        self.area_sec.title = "Section" if kind == "xsec" else (
            "Area and section line" if line else "Area")
        self.half.visible = self.dom.value == "storm"
        for w in (self.box_x0, self.box_x1, self.box_y0, self.box_y1):
            w.visible = self.dom.value == "box"
        if self.dom.value != "box":
            self.box_html.object = ""
        x = self.spec["xsec"]
        storm = self.xs_mode.value == "storm"
        for w in (self.xs_angle, self.xs_half, self.xs_offx, self.xs_offy):
            w.visible = storm
        self.xs_ab.visible = not storm
        self.xs_html.object = (
            '<div class="cv-hint">A ({:.1f}, {:.1f}) → B ({:.1f}, {:.1f}) km</div>'.format(
                *x["a"], *x["b"]) if not storm and x.get("a") else
            '<div class="cv-hint">Direction: 0° runs west → east, 90° south → north; the '
            'section is centred on the tracked storm (plus the offset).</div>' if storm else
            '<div class="cv-hint">Draw a section on the map (Section tool), then use its '
            'A–B.</div>')

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
        if s["kind"] in figdraw.ENTRIES:
            ents = s[figdraw.ENTRIES[s["kind"]]]
            ts = []
            for i in range(fg.npanels(s)):
                labs = [e.get("label", "") for e in ents if int(e.get("panel", 0)) == i]
                ts.append(" / ".join(dict.fromkeys(x for x in labs if x)) if s["kind"] == "line"
                          else "")
            self._set_titles(ts)
            return
        if s["vary"] == "field":
            ts = [self.fields[pf["field"]].label for pf in s["panel_fills"]]
        elif s["vary"] == "height":
            ts = [f"k = {int(round(z))}" if s.get("panel_zmode") == "level" else f"{z:g} km"
                  for z in s["panel_z"]]
        elif s["vary"] in ("grid", "custom"):
            ts = []
            for i in range(fg.npanels(s)):
                ref = fg.panel_ref(s, i)
                ts.append(s["runs"][ref[0]]["label"] if ref else "")
            self.rl_on.value = False  # the titles name the runs now
        else:
            fill = next((lay for lay in s["layers"] if lay["type"] == "fill"), None)
            ts = [self.fields[fill["field"]].label if fill and t is not None else ""
                  for t in s["times_s"]]
        self._set_titles(ts)
