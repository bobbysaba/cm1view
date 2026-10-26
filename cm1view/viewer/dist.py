"""Distribution: every value of a field over a region at one time -- the panel,
computing (dist.py) and the histogram, box, violin and cumulative plots, with a
table of statistics.  Several distributions (other fields, heights or times) are
drawn together; "Figure of these" opens them in the Figure workspace.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import json
import traceback
from functools import partial

import numpy as np
import panel as pn
from bokeh.models import ColumnDataSource, HoverTool
from bokeh.plotting import figure

from ..core import dist, series as ser
from ..figures import draw as figdraw
from .. import pdecomp
from ..core.fields import palette
from ..theme import GRID, MUTED, POINT_COLORS, TEXT
from .numinput import FloatInput
from .ui import _bokeh, _html, style_fig

DIST_PLOTS = {"Histogram": "hist", "Box": "box", "Violin": "violin", "Cumulative": "ecdf"}


class DistPanel:
    _dist_hold = False

    def _build_dist(self):
        """Distribution tab: one field over a region at the shown time."""
        run, F = self.run, self.F
        ztop = float(np.floor(run.z[-1] * 10) / 10)
        first = "winterp" if "winterp" in F else next(iter(F.defs))
        self.dist_field = pn.widgets.Select(name="Field", groups=F.groups(), value=first,
                                            width=230)
        self.dist_vmode = pn.widgets.Select(
            name="Vertical", options={"At a height": "height", "Layer (every level)": "layer",
                                      "Every level (whole depth)": "all"},
            value="height", width=170)
        self.dist_z = FloatInput(name="Height (km AGL)", value=1.0, step=0.25,
                                            start=0.0, end=ztop, width=110)
        self.dist_z0 = FloatInput(name="Bottom (km)", value=0.0, step=0.5,
                                             start=0.0, end=ztop, width=90, visible=False)
        self.dist_z1 = FloatInput(name="Top (km)", value=10.0, step=0.5,
                                             start=0.0, end=ztop, width=90, visible=False)
        self.dist_region = pn.widgets.Select(name="Region", options=self._ser_regions(),
                                             value="domain", width=180)
        self.dist_radius = FloatInput(name="Radius (km)", value=5.0, step=0.5,
                                                 start=0.25, width=90, visible=False)
        self.dist_offx = FloatInput(name="Offset x (km)", value=0.0, step=1.0,
                                               width=90, visible=False)
        self.dist_offy = FloatInput(name="Offset y (km)", value=0.0, step=1.0,
                                               width=90, visible=False)
        self.dist_lo = FloatInput(
            name="Only values from", value=None, placeholder="all", width=120,
            description="Keep values at or above this (blank: no limit), e.g. 1 m/s for "
                        "updrafts")
        self.dist_hi = FloatInput(name="to", value=None, placeholder="all",
                                             width=90)
        self.dist_go = pn.widgets.Button(name="Compute", button_type="primary",
                                         icon="chart-histogram", height=32,
                                         margin=(5, 4, 8, 10))
        self.dist_follow = pn.widgets.Checkbox(
            name="Follow the time slider", value=False, margin=(14, 10, 8, 10))
        self.dist_status = _html(
            '<div class="cv-empty">Choose a field, a height, layer or the whole depth, and '
            'a region, then <b>Compute</b>: every value there at the shown time. Compute '
            'again at other times, heights or fields to compare them in one plot.</div>',
            sizing_mode="stretch_width")

        # computed distributions: key -> dict(st (dist.summarize), recipe, t, label, color)
        self.dists, self._dist_n = {}, 0
        self.dist_pick = pn.widgets.Select(name="Distribution", options={}, width=380,
                                           description="The one Remove and Follow act on")
        self.dist_remove = pn.widgets.Button(name="Remove", button_type="light",
                                             button_style="outline", height=32,
                                             margin=(18, 4, 4, 4), disabled=True)
        self.dist_clear = pn.widgets.Button(name="Clear all", button_type="light",
                                            button_style="outline", height=32,
                                            margin=(18, 4, 4, 4), disabled=True)
        self.dist_to_fig = pn.widgets.Button(
            name="Figure of these", button_type="primary", button_style="outline",
            height=32, margin=(18, 4, 4, 10), disabled=True,
            description="A publication figure of these distributions, drawn as here "
                        "(Figure workspace)")

        # how they are drawn (from the summaries: no recompute)
        self.dist_kind = pn.widgets.RadioButtonGroup(
            options=DIST_PLOTS, value="hist", button_type="primary", button_style="outline",
            height=32, margin=(18, 4, 4, 4))
        self.dist_norm = pn.widgets.RadioButtonGroup(
            options={"Count": "count", "PDF": "pdf", "Fraction": "frac"}, value="count",
            button_type="primary", button_style="outline", height=32, margin=(18, 4, 4, 4),
            description="PDF: each distribution integrates to 1; fraction: of all its "
                        "values per bin")
        self.dist_bins = pn.widgets.IntInput(name="Bins", value=50, start=1, end=2000,
                                             width=80)
        self.dist_cum = pn.widgets.Select(name="Fraction", options={
            "At or below x": "below", "Above x": "above"}, value="below", width=130,
            visible=False)
        self.dist_whis = pn.widgets.Select(name="Whiskers", options={
            "1.5 × IQR": "tukey", "Min – max": "range", "5 – 95 %": "p5", "1 – 99 %": "p1"},
            value="tukey", width=120, visible=False)
        self.dist_logy = pn.widgets.Checkbox(name="Log scale", value=False,
                                             margin=(30, 10, 8, 10))
        num = dict(value=None, placeholder="auto", width=90)
        self.dist_x0 = FloatInput(name="Values from", **num)
        self.dist_x1 = FloatInput(name="to", **num)
        self.dist_plot = _bokeh(self._dist_empty(), sizing_mode="stretch_width")
        self.dist_table = _html(sizing_mode="stretch_width")

        def vis(*e):
            two = F[self.dist_field.value].ndim == 2
            mode = self.dist_vmode.value
            self.dist_vmode.visible = not two
            self.dist_z.visible = not two and mode == "height"
            self.dist_z0.visible = self.dist_z1.visible = not two and mode == "layer"
            trk = self.dist_region.value == "track"
            self.dist_radius.visible = self.dist_offx.visible = self.dist_offy.visible = trk

        for w in (self.dist_field, self.dist_vmode, self.dist_region):
            w.param.watch(vis, "value")
        self.dist_go.on_click(lambda e: self._dist_request())
        self.dist_remove.on_click(lambda e: self._dist_drop([self.dist_pick.value]))
        self.dist_clear.on_click(lambda e: self._dist_drop(list(self.dists)))
        self.dist_to_fig.on_click(self._on_dist_figure)
        self.dist_pick.param.watch(lambda e: self._dist_buttons(), "value")
        self.dist_kind.param.watch(lambda e: self._dist_opts(), "value")
        for w in (self.dist_kind, self.dist_norm, self.dist_bins, self.dist_cum,
                  self.dist_whis, self.dist_logy, self.dist_x0, self.dist_x1):
            w.param.watch(lambda e: self._dist_draw(), "value")

    def _dist_opts(self):
        k = self.dist_kind.value
        self.dist_norm.visible = self.dist_bins.visible = k == "hist"
        self.dist_cum.visible = k == "ecdf"
        self.dist_whis.visible = k in ("box", "violin")
        self.dist_logy.visible = k in ("hist", "ecdf")

    def dist_look(self):
        """spec["dist"] settings of the plot as shown (for a figure of these)."""
        return dict(plot=self.dist_kind.value, norm=self.dist_norm.value,
                    bins=int(self.dist_bins.value or 50), cum=self.dist_cum.value,
                    whis=self.dist_whis.value,
                    logy=bool(self.dist_logy.value) and self.dist_kind.value in ("hist", "ecdf"),
                    xmin=self._num(self.dist_x0), xmax=self._num(self.dist_x1))

    # ================================================================ computing
    def _dist_recipe(self):
        """The recipe of the form (None + why if it is incomplete)."""
        d = self.F[self.dist_field.value]
        r = dict(field=d.name, vmode="2d" if d.ndim == 2 else self.dist_vmode.value,
                 z=self.dist_z.value or 0.0, z0=self.dist_z0.value or 0.0,
                 z1=self.dist_z1.value or 0.0, radius=self.dist_radius.value or 5.0,
                 offset=(self.dist_offx.value or 0.0, self.dist_offy.value or 0.0),
                 lo=self._num(self.dist_lo), hi=self._num(self.dist_hi))
        reg = self.dist_region.value
        if reg == "view":
            r.update(region="box", box=self.view)
        elif reg == "box3d":
            if self.box is None:
                return None, ("Draw a 3D region first (<b>3D box</b> tool on the map), or "
                              "choose another region")
            r.update(region="box", box=self.box)
        else:
            r["region"] = reg
        if reg == "track" and not self.fixes:
            return None, "Track the storm first (<b>Track</b> tab), then use it here"
        return dist.normalize(r), ""

    def _dist_request(self, recipe=None, replace=None):
        """Compute a recipe (the form's) at the shown time; replace: the key of the
        distribution it takes the place of (following the time slider)."""
        if recipe is None:
            recipe, why = self._dist_recipe()
            if recipe is None:
                self.dist_status.object = (f'<div class="cv-status" style="color:#f87171">'
                                           f'{why}</div>')
                return
        t = self.t
        key = json.dumps(recipe, sort_keys=True) + f"|{t}"
        if key in self.dists:
            self._dist_set_pick(key)
            return
        center = None
        if recipe["region"] == "track":
            center = ser.track_centers(self.fixes, len(self.run.times)).get(t)
        storm = self._field_storm(t)[0] if self.F[recipe["field"]].storm else None
        self.gen["dist"] += 1
        g = self.gen["dist"]
        self.dist_go.disabled = True
        self.dist_status.object = ('<div class="cv-status"><span class="busy">● Reading '
                                   f'{self.F[recipe["field"]].label} at '
                                   f'{self.run.times[t] / 60:g} min…</span></div>')
        self.pools["dist"].submit(self._dist_job, g, recipe, t, storm, center, key, replace)

    def _dist_job(self, g, recipe, t, storm, center, key, replace):
        import time as _t
        t0 = _t.time()
        try:
            if pdecomp.is_pdecomp(self.F, recipe["field"]):
                pdecomp.source(self.run, t)  # file version tag, off the page thread
            st = dist.compute(self.run, self.F, recipe, t, storm, center)
            res = st if st["n"] else "no values in the region (or the value limits)"
        except ValueError as e:
            res = str(e)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = f"{type(e).__name__}: {e}"
        self._schedule(partial(self._dist_apply, g, res, recipe, t, key, replace,
                               _t.time() - t0))

    def _dist_apply(self, g, res, recipe, t, key, replace, secs):
        if g != self.gen["dist"]:
            return
        self.dist_go.disabled = False
        if isinstance(res, str):
            self.dist_status.object = (f'<div class="cv-status" style="color:#f87171">'
                                       f'No distribution: {res}</div>')
            return
        d = self.F[recipe["field"]]
        label = f"{dist.describe(recipe, d.label, d.units)} · {self.run.times[t] / 60:g} min"
        old = self.dists.get(replace) if replace else None
        if old is not None:  # (in its place and colour)
            items = [(key, dict(old, st=res, recipe=recipe, t=t, label=label))
                     if k == replace else (k, v) for k, v in self.dists.items()]
            self.dists = dict(items)
        else:
            n = self._dist_n
            self.dists[key] = dict(st=res, recipe=recipe, t=t, label=label,
                                   color=POINT_COLORS[n % len(POINT_COLORS)] if n < 4 else
                                   palette("Spectral_r", 12)[(3 * n) % 12])
            self._dist_n += 1
        self.dist_status.object = (f'<div class="cv-status">{res["n"]:,} values · '
                                   f'{secs:.1f} s</div>')
        self._dist_set_pick(key)

    def _dist_follow(self):
        """The time settled: the chosen distribution again at the shown time."""
        s = self.dists.get(self.dist_pick.value)
        if s is not None and s["t"] != self.t:
            self._dist_request(s["recipe"], replace=self.dist_pick.value)

    def _dist_set_pick(self, key):
        hold, self._dist_hold = self._dist_hold, True
        try:
            self.dist_pick.options = {v["label"]: k for k, v in self.dists.items()}
            self.dist_pick.value = key
        finally:
            self._dist_hold = hold
        self._dist_buttons()
        self._dist_draw()

    def _dist_drop(self, keys):
        for k in keys:
            self.dists.pop(k, None)
        self._dist_set_pick(next(reversed(self.dists), None) if self.dists else None)

    def _dist_buttons(self):
        has = bool(self.dists)
        self.dist_remove.disabled = self.dist_pick.value not in self.dists
        self.dist_clear.disabled = self.dist_to_fig.disabled = not has

    def _on_dist_figure(self, ev):
        self.workspace.value = "Figure"
        self.figed.from_dists()

    # ================================================================ drawing
    def _dist_empty(self, logy=False):
        fig = figure(sizing_mode="stretch_width", height=340, y_axis_type="log" if logy
                     else "linear", tools="pan,wheel_zoom,box_zoom,reset,save")
        style_fig(fig)
        fig.toolbar.autohide = True
        return fig

    def _dist_draw(self):
        if self._dist_hold:
            return
        self._dist_opts()
        kind = self.dist_kind.value
        items = list(self.dists.values())
        logy = bool(self.dist_logy.value) and kind in ("hist", "ecdf")
        fig = self._dist_empty(logy)
        self._dist_table(items)
        if not items:
            self.dist_plot.object = fig
            return
        sts = [s["st"] for s in items]
        vlo, vhi = self._num(self.dist_x0), self._num(self.dist_x1)
        units = list(dict.fromkeys(self.F[s["recipe"]["field"]].units for s in items
                                   if s["recipe"]["field"] in self.F))
        fields = list(dict.fromkeys(self.F[s["recipe"]["field"]].label for s in items
                                    if s["recipe"]["field"] in self.F))
        vlab = "; ".join(fields) + (f" ({', '.join(u for u in units if u)})"
                                    if any(units) else "")
        if kind in ("hist", "ecdf"):
            self._dist_lines(fig, items, sts, kind, logy, vlo, vhi)
            fig.xaxis.axis_label = vlab
        else:
            self._dist_boxes(fig, items, sts, kind, vlo, vhi)
            fig.yaxis.axis_label = vlab
        style_fig(fig)  # (the axis labels set above)
        self.dist_plot.object = fig

    def _dist_lines(self, fig, items, sts, kind, logy, vlo, vhi):
        """Histograms in common bins (a filled stair line each) or cumulative
        fractions."""
        norm = self.dist_norm.value
        if kind == "hist":
            edges = figdraw.dist_edges(sts, self.dist_bins.value or 50, None, vlo, vhi)
            quads = []
            for s in items:
                v = np.asarray(figdraw.dist_hist(s["st"], edges, norm), dtype=float)
                top = np.where(v > 0, v, np.nan) if logy else v
                bot = np.full_like(v, np.nan) if logy else np.zeros_like(v)
                if logy:  # (log axes: bars from just under the smallest value)
                    pos = v[v > 0]
                    bot[:] = pos.min() / 2 if pos.size else 1.0
                src = ColumnDataSource(dict(l=edges[:-1], r=edges[1:], top=top, bottom=bot,
                                            name=[s["label"]] * len(v)))
                quads.append(fig.quad(left="l", right="r", top="top", bottom="bottom",
                                      source=src, fill_color=s["color"], fill_alpha=0.22,
                                      line_color=None))
                fig.line(np.repeat(edges, 2)[1:-1], np.repeat(top, 2), color=s["color"],
                         line_width=1.8, legend_label=s["label"])
            fig.add_tools(HoverTool(renderers=quads, tooltips=[
                ("", "@name"), ("bin", "@l{0.0000} – @r{0.0000}"), ("value", "@top{0.0000}")]))
            fig.yaxis.axis_label = figdraw.DIST_NORM_LABEL[norm]
            fig.x_range.start, fig.x_range.end = float(edges[0]), float(edges[-1])
        else:
            above = self.dist_cum.value == "above"
            for s in items:
                x, y = figdraw.dist_cdf(s["st"], above)
                if logy:
                    y = np.where(y > 0, y, np.nan)
                fig.line(x, y, color=s["color"], line_width=1.8, legend_label=s["label"])
            fig.yaxis.axis_label = "fraction above" if above else "cumulative fraction"
            if vlo is not None:
                fig.x_range.start = vlo
            if vhi is not None:
                fig.x_range.end = vhi
        lg = fig.legend[0]
        lg.visible = len(items) > 1
        lg.update(location="top_right", background_fill_color="#111723",
                  background_fill_alpha=0.75, border_line_color=GRID,
                  label_text_color=TEXT, label_text_font_size="11px", click_policy="hide")

    def _dist_boxes(self, fig, items, sts, kind, vlo, vhi):
        """A box or violin per distribution, numbered as in the table."""
        whis = self.dist_whis.value
        hov = []
        for p, (s, st) in enumerate(zip(items, sts), start=1):
            c = s["color"]
            q1, med, q3 = (figdraw.dist_q(st, k) for k in (0.25, 0.5, 0.75))
            lo, hi = figdraw.dist_whiskers(st, whis)
            stats = dict(name=[s["label"]], med=[med], q1=[q1], q3=[q3], mean=[st["mean"]],
                         n=[st["n"]])
            if kind == "violin":
                x, dens = figdraw.dist_kde(st)
                dd = dens / max(dens.max(), 1e-300) * 0.4
                hov.append(fig.patch(np.concatenate([p - dd, (p + dd)[::-1]]),
                                     np.concatenate([x, x[::-1]]), fill_color=c,
                                     fill_alpha=0.35, line_color=c, line_width=1.2))
                fig.segment([p], [lo], [p], [hi], color=TEXT, line_width=1.2)
                fig.segment([p], [q1], [p], [q3], color=TEXT, line_width=5)
                fig.scatter([p], [med], size=7, fill_color="white", line_color="#111723")
            else:
                src = ColumnDataSource(dict(stats, l=[p - 0.3], r=[p + 0.3]))
                hov.append(fig.quad(left="l", right="r", bottom="q1", top="q3", source=src,
                                    fill_color=c, fill_alpha=0.3, line_color=c,
                                    line_width=1.5))
                fig.segment([p - 0.3], [med], [p + 0.3], [med], color=c, line_width=3)
                fig.segment([p, p], [q1, q3], [p, p], [lo, hi], color=c, line_width=1.5)
                fig.segment([p - 0.12] * 2, [lo, hi], [p + 0.12] * 2, [lo, hi], color=c,
                            line_width=1.5)
            fig.scatter([p], [st["mean"]], marker="diamond", size=10, fill_color="white",
                        line_color=c)
        if kind == "box":
            fig.add_tools(HoverTool(renderers=hov, tooltips=[
                ("", "@name"), ("median", "@med{0.0000}"), ("quartiles", "@q1{0.0000} – "
                                                                         "@q3{0.0000}"),
                ("mean", "@mean{0.0000}"), ("values", "@n{0,0}")]))
        n = len(items)
        fig.xaxis.ticker = list(range(1, n + 1))
        fig.xaxis.major_label_overrides = {p: str(p) for p in range(1, n + 1)}
        fig.x_range.start, fig.x_range.end = 0.4, n + 0.6
        fig.xgrid.grid_line_color = None
        if vlo is not None:
            fig.y_range.start = vlo
        if vhi is not None:
            fig.y_range.end = vhi

    def _dist_table(self, items):
        """Statistics of each distribution (the numbers of the box / violin plot)."""
        if not items:
            self.dist_table.object = ""
            return
        head = "".join(f"<th>{h}</th>" for h in ("", "#", "Distribution", "values", "mean",
                                                  "sd", "min", "1 %", "median", "99 %",
                                                  "max"))
        rows = []
        for p, s in enumerate(items, start=1):
            st = s["st"]
            vals = [st["mean"], st["std"], st["lo"], figdraw.dist_q(st, 0.01),
                    figdraw.dist_q(st, 0.5), figdraw.dist_q(st, 0.99), st["hi"]]
            rows.append(
                f'<tr><td><span style="display:inline-block;width:10px;height:10px;'
                f'border-radius:2px;background:{s["color"]}"></span></td><td>{p}</td>'
                f'<td style="text-align:left">{s["label"]}</td><td>{st["n"]:,}</td>'
                + "".join(f"<td>{v:.4g}</td>" for v in vals) + "</tr>")
        self.dist_table.object = (
            f'<table style="border-collapse:collapse;font-size:12px;color:{TEXT};'
            f'margin:6px 0;width:100%"><thead style="color:{MUTED}">{head}</thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            f'<style>td,th{{padding:2px 6px;text-align:right;border-bottom:1px solid {GRID}}}'
            f'</style>')
