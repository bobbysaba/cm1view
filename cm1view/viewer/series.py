"""Series: a field reduced over a region at every time -- the panel, computing,
the line and time-height plots, and files.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import io
import os
import traceback
import warnings
from functools import partial

import numpy as np
import panel as pn
from bokeh.events import Tap
from bokeh.models import (
    ColorBar, ColumnDataSource, HoverTool, LinearColorMapper, LinearAxis, Range1d,
    Span,
)
from bokeh.plotting import figure
from bokeh.transform import transform

from .. import config
from ..core import series as ser
from ..core.fields import CMAPS, deriv_name, deriv_options, palette
from ..theme import BG, GRID, MUTED, POINT_COLORS, TEXT
from .numinput import FloatInput
from .ui import _bokeh, _html, _settings_toggle, style_fig, held


class SeriesPanel:
    _ser_hold = False

    def _build_series(self):
        """Series tab: one field reduced over a region at every output time."""
        run, F = self.run, self.F
        ztop = float(np.floor(run.z[-1] * 10) / 10)
        first = "thpert" if "thpert" in F else next(iter(F.defs))
        self.ser_field = pn.widgets.Select(name="Field", groups=F.groups(), value=first,
                                           width=230)
        self.ser_op = pn.widgets.Select(
            name="Derivative", options=deriv_options(F[first]), value="", width=90,
            description="A derivative of the field (per km), taken before the reduction: "
                        "∂/∂z on the model levels, ∂/∂x, ∂/∂y or the horizontal "
                        "gradient's size")
        self.ser_vmode = pn.widgets.Select(
            name="Vertical", options={"At a height": "height", "Layer (every level)": "layer"},
            value="height", width=150,
            description="Layer: the reduction is also kept at every model level in the "
                        "layer (time–height plot, sub-layers from the saved file)")
        self.ser_z = FloatInput(name="Height (km AGL)", value=1.0, step=0.25,
                                           start=0.0, end=ztop, width=110)
        self.ser_z0 = FloatInput(name="Bottom (km)", value=0.0, step=0.5,
                                            start=0.0, end=ztop, width=90, visible=False)
        self.ser_z1 = FloatInput(name="Top (km)", value=10.0, step=0.5,
                                            start=0.0, end=ztop, width=90, visible=False)
        self.ser_region = pn.widgets.Select(name="Region", options=self._ser_regions(),
                                            value="domain", width=180)
        self.ser_radius = FloatInput(name="Radius (km)", value=5.0, step=0.5,
                                                start=0.25, width=90, visible=False)
        self.ser_offx = FloatInput(
            name="Offset x (km)", value=0.0, step=1.0, width=90, visible=False,
            description="Centre the disc this far from the tracked storm (e.g. in the "
                        "inflow); x, y on the model grid")
        self.ser_offy = FloatInput(name="Offset y (km)", value=0.0, step=1.0,
                                              width=90, visible=False)
        self.ser_reduce = pn.widgets.Select(
            name="Reduce", options={"Minimum": "min", "Maximum": "max", "Mean": "mean",
                                    "Percentile": "pct"}, value="min", width=120)
        self.ser_pct = FloatInput(name="Percentile", value=99.0, step=0.5,
                                             start=0.0, end=100.0, width=90, visible=False)
        self.ser_go = pn.widgets.Button(name="Compute", button_type="primary", icon="chart-line",
                                        height=32, margin=(5, 4, 8, 10))
        self.ser_stop = pn.widgets.Button(name="Stop", button_type="danger",
                                          button_style="outline", height=32,
                                          margin=(5, 4, 8, 4), disabled=True)
        self.ser_status = _html(
            '<div class="cv-empty">Choose a field, height or layer, region and reduction, '
            'then <b>Compute</b>: every output time is processed (a few seconds for one '
            'height, about a minute for a deep layer). Results are cached, so the same '
            'recipe comes back instantly in a later session.</div>',
            sizing_mode="stretch_width")

        # computed series of this session: key -> dict(ds, recipe, color)
        self.series, self._ser_n = {}, 0
        self.ser_pick = pn.widgets.Select(name="Series", options={}, width=420,
                                          description="The series used by the time–height "
                                                      "view, Save and Remove")
        self.ser_view = pn.widgets.RadioButtonGroup(
            options={"Time series": "line", "Time–height": "th"}, value="line",
            button_type="primary", button_style="outline", height=32, margin=(18, 4, 4, 10),
            disabled=True)
        self.ser_remove = pn.widgets.Button(name="Remove", button_type="light",
                                            button_style="outline", height=32,
                                            margin=(18, 4, 4, 4), disabled=True)

        # plot settings: limits, a sub-layer of layer series and the time–height colours,
        # all applied to the computed result (no recompute)
        num = dict(value=None, placeholder="auto", width=90)
        self.ser_t0 = FloatInput(name="Time from (min)", **num)
        self.ser_t1 = FloatInput(name="to", **num)
        self.ser_y0 = FloatInput(name="y from", **num)
        self.ser_y1 = FloatInput(name="to", **num)
        self.ser_s0 = FloatInput(
            name="Sub-layer from (km)", **dict(num, width=150),
            description="Layer series: reduce over these heights only, from the values "
                        "kept at every level (min, max and mean; a percentile needs a "
                        "recompute)")
        self.ser_s1 = FloatInput(name="to", **num)
        self.ser_cmap = pn.widgets.Select(name="Colormap", options=["auto"] + CMAPS,
                                          value="auto", width=140)
        self.ser_crev = pn.widgets.Checkbox(name="Reverse", value=False,
                                            margin=(5, 10, 14, 10))
        self.ser_c0 = FloatInput(name="Colours from", **num)
        self.ser_c1 = FloatInput(name="to", **num)
        self.ser_auto = pn.widgets.Button(name="Auto limits", button_type="light",
                                          button_style="outline", height=32,
                                          margin=(18, 4, 4, 10))
        self.ser_lims = (self.ser_t0, self.ser_t1, self.ser_y0, self.ser_y1, self.ser_s0,
                         self.ser_s1, self.ser_c0, self.ser_c1)
        self.ser_set = pn.FlexBox(*self.ser_lims[:6], self.ser_cmap, self.ser_crev,
                                  self.ser_c0, self.ser_c1, self.ser_auto, flex_wrap="wrap",
                                  align_items="flex-end", gap="0 4px",
                                  sizing_mode="stretch_width",
                                  styles={"border-top": f"1px solid {GRID}"})
        self.ser_set_btn = _settings_toggle(self.ser_set)
        self.ser_set_btn.param.update(name="Plot", width=None, margin=(18, 4, 4, 4))

        fig = figure(sizing_mode="stretch_width", height=300, tools="pan,wheel_zoom,reset,save",
                     x_axis_label="time (min)", y_axis_label="")
        style_fig(fig)
        fig.toolbar.autohide = True
        fig.add_tools(HoverTool(tooltips=[("", "@name"), ("t", "@hms"),
                                          ("value", "@value{0.0000}"), ("at", "@where")]))
        self.ser_now = Span(location=run.times[self.t] / 60.0, dimension="height",
                            line_color="#fbbf24", line_width=1.5, line_alpha=0.7)
        fig.add_layout(self.ser_now)
        fig.on_event(Tap, self._on_ser_tap)
        self.ser_fig = fig
        self._ser_glyphs = []  # renderers of the line view

        th = figure(sizing_mode="stretch_width", height=300, tools="pan,wheel_zoom,reset,save",
                    x_axis_label="time (min)", y_axis_label="height (km AGL)")
        style_fig(th)
        th.toolbar.autohide = True
        self.ser_th_src = ColumnDataSource(dict(l=[], r=[], b=[], t=[], v=[], hms=[], z=[]))
        self.ser_th_map = LinearColorMapper(palette=palette("viridis"), low=0, high=1)
        q = th.quad(left="l", right="r", bottom="b", top="t", source=self.ser_th_src,
                    fill_color=transform("v", self.ser_th_map),
                    line_color=transform("v", self.ser_th_map), line_width=0.6)  # no seams
        th.add_tools(HoverTool(renderers=[q], tooltips=[("t", "@hms"), ("z", "@z{0.00} km"),
                                                       ("value", "@v{0.0000}")]))
        self.ser_th_bar = ColorBar(color_mapper=self.ser_th_map, width=12,
                                   background_fill_color=BG, major_label_text_color=MUTED)
        th.add_layout(self.ser_th_bar, "right")
        self.ser_th_now = Span(location=run.times[self.t] / 60.0, dimension="height",
                               line_color="#fbbf24", line_width=1.5, line_alpha=0.7)
        th.add_layout(self.ser_th_now)
        th.on_event(Tap, partial(self._on_ser_tap, height=True))
        self.ser_thfig = th
        self.ser_plot = _bokeh(fig, sizing_mode="stretch_width")  # or the th view

        self.ser_path = pn.widgets.TextInput(
            name="Save to / load from (on the server)",
            value=os.path.join(config.exports_dir(run.path, "series"), "series.nc"),
            sizing_mode="stretch_width", min_width=300)
        self.ser_fmt = pn.widgets.Select(
            name="Format", options={"netCDF (.nc)": ".nc", "CSV (.csv)": ".csv",
                                    "Text columns (.txt)": ".txt", "Pickle (.pkl)": ".pkl"},
            value=".nc", width=150,
            description="netCDF keeps everything, including per-level values of a layer; "
                        "CSV / text hold the series only; pickle loads into pandas")
        self.ser_save = pn.widgets.Button(name="Save", button_type="primary", height=32,
                                          margin=(5, 4, 8, 10), disabled=True)
        self.ser_dl = pn.widgets.FileDownload(
            callback=self._ser_download, filename="series.nc", label="Download",
            button_type="primary", button_style="outline", height=32, margin=(5, 4, 8, 4),
            disabled=True)
        self.ser_load = pn.widgets.Button(
            name="Load", button_type="primary", button_style="outline", height=32,
            margin=(5, 4, 8, 4), description="Read a saved series (.nc, .csv, .txt, .pkl) "
                                             "from the path")
        self.ser_file_msg = _html(sizing_mode="stretch_width")

        def vis(*e):
            d = F[self.ser_field.value]
            two = d.ndim == 2
            lay = self.ser_vmode.value == "layer"
            self.ser_vmode.visible = not two
            self.ser_z.visible = not two and not lay
            self.ser_z0.visible = self.ser_z1.visible = not two and lay
            trkr = self.ser_region.value == "track"
            self.ser_radius.visible = self.ser_offx.visible = self.ser_offy.visible = trkr
            self.ser_pct.visible = self.ser_reduce.value == "pct"

        def ops(e):  # (a 2D field has no ∂/∂z)
            opts = deriv_options(F[e.new])
            if opts != self.ser_op.options:
                v = self.ser_op.value
                self.ser_op.options = opts
                self.ser_op.value = v if v in opts.values() else ""

        self.ser_field.param.watch(ops, "value")
        for w in (self.ser_field, self.ser_vmode, self.ser_region, self.ser_reduce):
            w.param.watch(vis, "value")
        self.ser_go.on_click(self._on_ser_compute)
        self.ser_stop.on_click(lambda e: self._cancel_series())
        self.ser_pick.param.watch(lambda e: self._ser_select(), "value")
        self.ser_view.param.watch(lambda e: self._ser_draw(), "value")
        for w in self.ser_lims + (self.ser_cmap, self.ser_crev):
            w.param.watch(lambda e: self._ser_draw(), "value")

        def auto(e):
            with held(self, "_ser_hold"):
                for w in self.ser_lims:
                    w.value = None
                self.ser_cmap.value, self.ser_crev.value = "auto", False
            self._ser_draw()
        self.ser_auto.on_click(auto)
        self.ser_view.param.watch(lambda e: self._ser_set_vis(), "value")
        self._ser_set_vis()
        self.ser_remove.on_click(self._on_ser_remove)
        self.ser_fmt.param.watch(self._on_ser_fmt, "value")
        self.ser_path.param.watch(
            lambda e: setattr(self.ser_dl, "filename", os.path.basename(e.new) or "series"),
            "value")
        self.ser_save.on_click(self._on_ser_save)
        self.ser_load.on_click(self._on_ser_load)

    # ================================================================ time series
    def _ser_recipe(self):
        """The recipe of the Series form, normalized (None + message if incomplete)."""
        d = self.F[deriv_name(self.ser_op.value, self.ser_field.value)]
        r = dict(field=d.name, vmode="2d" if d.ndim == 2 else self.ser_vmode.value,
                 z=self.ser_z.value or 0.0, z0=self.ser_z0.value or 0.0,
                 z1=self.ser_z1.value or 0.0, reduce=self.ser_reduce.value,
                 pct=self.ser_pct.value if self.ser_pct.value is not None else 99.0,
                 radius=self.ser_radius.value or 5.0,
                 offset=(self.ser_offx.value or 0.0, self.ser_offy.value or 0.0))
        reg = self.ser_region.value
        if reg == "view":
            r.update(region="box", box=self.view)
        elif reg == "box3d":
            if self.box is None:
                return None, ("Draw a 3D region first (<b>3D box</b> tool on the map), "
                              "or choose another region")
            r.update(region="box", box=self.box)
        else:
            r["region"] = reg
        if reg == "track" and not self.fixes:
            return None, ("Track the storm first (<b>Track</b> tab), then compute around "
                          "it")
        return ser.normalize(r), ""

    def _ser_key(self, recipe, source=""):
        import json
        return json.dumps(recipe, sort_keys=True) + (f"|{source}" if source else "")

    def _ser_add(self, key, ds, recipe, loaded=""):
        """Register a series of this session (or refresh it) and make it the active one."""
        d = self.F[recipe["field"]] if recipe["field"] in self.F else None
        label = ser.describe(recipe, d.label if d else "", d.units if d else "")
        if loaded:
            label += f" — {os.path.basename(loaded)}"
        if key not in self.series:
            self.series[key] = dict(ds=ds, recipe=recipe, label=label, file=loaded or None,
                                    color=POINT_COLORS[self._ser_n % len(POINT_COLORS)]
                                    if self._ser_n < 4 else
                                    palette("Spectral_r", 12)[(3 * self._ser_n) % 12])
            self._ser_n += 1
        else:
            self.series[key]["ds"] = ds
        self.ser_pick.options = {v["label"]: k for k, v in self.series.items()}
        self._update_items()
        if self.ser_pick.value == key:
            self._ser_select()
        else:
            self.ser_pick.value = key
        self.ser_path.value = os.path.join(config.exports_dir(self.run.path, "series"),
                                           ser.short_name(recipe) + self.ser_fmt.value)

    def _on_ser_compute(self, ev):
        recipe, why = self._ser_recipe()
        if recipe is None:
            self.ser_status.object = f'<div class="cv-status" style="color:#f87171">{why}</div>'
            return
        run, d = self.run, self.F[recipe["field"]]
        centers = ser.track_centers(self.fixes, len(run.times)) \
            if recipe["region"] == "track" else None
        storm = {t: self._field_storm(t)[0] for t in range(len(run.times))} \
            if d.storm else None
        key = self._ser_key(recipe)
        if key in self.series:
            ds = self.series[key]["ds"]
            if centers is not None:
                ser.invalidate_moved(ds, recipe, centers)
        else:
            ds = ser.cached(run, recipe, d.label, d.units, centers)
        self._ser_add(key, ds, recipe)
        self.gen["ser"] += 1
        g = self.gen["ser"]
        todo = int(len(run.times) - ds["computed"].sum())
        self.ser_go.disabled, self.ser_stop.disabled = True, False
        self.ser_status.object = (f'<div class="cv-status"><span class="busy">● Computing '
                                  f'{todo} of {len(run.times)} times '
                                  f'({run.workers} reader{"s" if run.workers > 1 else ""})…'
                                  f'</span></div>')
        self.pools["ser"].submit(self._ser_job, g, key, recipe, ds, centers, storm)

    def _ser_job(self, g, key, recipe, ds, centers, storm):
        import time as _t
        run, t0, last = self.run, _t.time(), [0.0]

        def cancelled():
            return g != self.gen["ser"]

        def on_result(ds_, done, total):
            if cancelled() or (_t.time() - last[0] < 1.0 and done < total):
                return
            last[0] = _t.time()
            msg = (f'<div class="cv-status"><span class="busy">● Computing… {done}/{total} '
                   f'times · {_t.time() - t0:.0f} s</span></div>')
            self._schedule(partial(self._ser_progress, g, msg))

        try:
            ds, skipped = ser.compute(run, self.F, recipe, ds, centers, storm,
                                      on_result=on_result, cancelled=cancelled)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            msg = f'<div class="cv-status" style="color:#f87171">Series error: {e}</div>'
            self._schedule(partial(self._ser_finish, g, msg))
            return
        n = int(ds["computed"].sum())
        msg = (f'<div class="cv-status">{n} of {len(run.times)} times · '
               f'{_t.time() - t0:.0f} s{" · stopped" if cancelled() else ""}')
        if skipped:
            why = {}
            for t, r in skipped.items():
                why.setdefault(r, []).append(t)
            msg += " · not computed: " + "; ".join(
                f"{len(ts)} time{'s' if len(ts) > 1 else ''} ({r})" for r, ts in why.items())
        msg += "</div>"
        self._schedule(partial(self._ser_finish, g, msg, force=cancelled()))

    def _ser_progress(self, g, msg):
        if g == self.gen["ser"]:
            self.ser_status.object = msg
            self._ser_draw()

    def _ser_finish(self, g, msg, force=False):
        if g != self.gen["ser"] and not force:
            return
        self.ser_status.object = msg
        self._ser_draw()  # before Compute is enabled again: the plot is complete by then
        self.ser_go.disabled, self.ser_stop.disabled = False, True

    def _cancel_series(self):
        self.gen["ser"] += 1
        self.ser_go.disabled, self.ser_stop.disabled = False, True

    def _ser_select(self):
        s = self.series.get(self.ser_pick.value)
        has = s is not None
        self.ser_save.disabled = self.ser_dl.disabled = self.ser_remove.disabled = not has
        prof = has and "profile" in s["ds"]
        self.ser_view.disabled = not prof
        if not prof and self.ser_view.value != "line":
            self.ser_view.value = "line"  # redraws
            return
        self._ser_draw()

    @staticmethod
    def _num(w):
        v = w.value
        return None if v is None or not np.isfinite(v) else float(v)

    def _ser_values(self, s, ts):
        """Values of series s at times ts and a label suffix: the series itself, or for
        a layer series with a sub-layer set, its reduction over those heights."""
        ds = s["ds"]
        a, b = self._num(self.ser_s0), self._num(self.ser_s1)
        how = s["recipe"].get("reduce")
        if "profile" not in ds or (a is None and b is None) or how not in ("min", "max",
                                                                           "mean"):
            return ds["value"].values[ts], "", False
        z = np.asarray(ds["z"].values, dtype=float)
        sel = (z >= (a if a is not None else -np.inf)) & (z <= (b if b is not None else np.inf))
        if not sel.any():
            return np.full(len(ts), np.nan), " (no levels in the sub-layer)", True
        P = ds["profile"].values[ts][:, sel]
        f = {"min": np.nanmin, "max": np.nanmax, "mean": np.nanmean}[how]
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            v = f(P, axis=1) if P.size else np.full(len(ts), np.nan)
        return v, f" · {z[sel][0]:.2f}–{z[sel][-1]:.2f} km", True

    def _ser_set_vis(self):
        th = self.ser_view.value == "th"
        for w in (self.ser_cmap, self.ser_crev, self.ser_c0, self.ser_c1):
            w.visible = th
        self.ser_y0.name = "Height from (km)" if th else "y from"
        prof = any("profile" in v["ds"] for v in self.series.values())
        self.ser_s0.visible = self.ser_s1.visible = prof and not th

    def _ser_range(self, fig, which, lo, hi, data):
        """Fixed limits lo / hi (None: from the data) on a figure axis, or automatic
        ranges when neither is set."""
        from bokeh.models import DataRange1d
        cur = getattr(fig, which)
        if lo is None and hi is None:
            if not isinstance(cur, DataRange1d):
                setattr(fig, which, DataRange1d())
            return getattr(fig, which)
        d = np.asarray(data, dtype=float)
        d = d[np.isfinite(d)]
        dlo, dhi = (float(d.min()), float(d.max())) if d.size else (0.0, 1.0)
        lo, hi = (dlo if lo is None else lo), (dhi if hi is None else hi)
        if hi <= lo:
            hi = lo + (abs(lo) * 0.1 or 1.0)
        if isinstance(cur, Range1d):
            cur.update(start=lo, end=hi, reset_start=lo, reset_end=hi)
        else:
            setattr(fig, which, Range1d(lo, hi, reset_start=lo, reset_end=hi))
        return getattr(fig, which)

    def _ser_draw(self):
        from bokeh.models import DataRange1d, Legend, LegendItem, LinearAxis

        if self._ser_hold:
            return
        self._ser_set_vis()
        run, fig = self.run, self.ser_fig
        fig.renderers = [r for r in fig.renderers if r not in self._ser_glyphs]
        self._ser_glyphs = []
        # series in other units than the first get their own y axis on the right
        for ax in getattr(self, "_ser_axes", []):
            if ax in fig.right:
                fig.right.remove(ax)
        self._ser_axes = []
        order = list(dict.fromkeys(s["ds"]["value"].attrs.get("units", "")
                                   for s in self.series.values()))
        ranges = {u: "default" if n == 0 else f"u{n}" for n, u in enumerate(order)}
        fig.extra_y_ranges = {name: DataRange1d() for name in ranges.values()
                              if name != "default"}
        by_range = {name: [] for name in ranges.values()}
        items, all_t, left_v = [], [], []
        for key, s in self.series.items():
            ds = s["ds"]
            ok = ds["computed"].values == 1
            ts = np.flatnonzero(ok)
            v, suffix, sub = self._ser_values(s, ts)
            where = [("" if sub or not np.isfinite(x) else
                      f"({x:.1f}, {y:.1f}) km" + (f", {z:.2f} km AGL" if np.isfinite(z) else ""))
                     for x, y, z in zip(ds["x_km"].values[ts], ds["y_km"].values[ts],
                                        ds["z_km"].values[ts])]
            src = ColumnDataSource(dict(tmin=run.times[ts] / 60.0, value=v,
                                        hms=[run.time_label(t) for t in ts],
                                        name=[s["label"] + suffix] * len(ts), where=where))
            all_t += list(run.times[ts] / 60.0)
            act = key == self.ser_pick.value
            rng = ranges[ds["value"].attrs.get("units", "")]
            if rng == "default":
                left_v += list(v)
            ln = fig.line("tmin", "value", source=src, line_color=s["color"],
                          line_width=2.5 if act else 1.6, y_range_name=rng)
            pt = fig.scatter("tmin", "value", source=src, size=5 if act else 3,
                             color=s["color"], y_range_name=rng)
            self._ser_glyphs += [ln, pt]
            by_range[rng] += [ln, pt]
            items.append(LegendItem(label=s["label"] + suffix, renderers=[ln, pt]))
        if not fig.legend:
            # below the plot: a click on an entry (hide / show) is not a click on a time
            fig.add_layout(Legend(click_policy="hide", background_fill_color=BG,
                                  label_text_color=TEXT, label_text_font_size="11px",
                                  border_line_color=None, spacing=0, padding=4), "below")
        fig.legend[0].items = items
        fig.legend[0].visible = bool(items)
        self._ser_range(fig, "x_range", self._num(self.ser_t0), self._num(self.ser_t1), all_t)
        yr = self._ser_range(fig, "y_range", self._num(self.ser_y0), self._num(self.ser_y1),
                             left_v)
        if isinstance(yr, DataRange1d):
            yr.renderers = by_range.get("default", []) or "auto"
        for u, name in ranges.items():
            if name == "default":
                continue
            fig.extra_y_ranges[name].renderers = by_range[name]
            ax = LinearAxis(y_range_name=name, axis_label=u or "(no units)")
            for k in ("axis_label_text_color", "major_label_text_color", "axis_line_color",
                      "major_tick_line_color", "minor_tick_line_color"):
                setattr(ax, k, getattr(fig.yaxis[0], k))
            fig.add_layout(ax, "right")
            self._ser_axes.append(ax)
        fig.yaxis[0].axis_label = order[0] if order else ""
        s = self.series.get(self.ser_pick.value)
        th = (s is not None and "profile" in s["ds"] and self.ser_view.value == "th")
        if th:
            self._ser_draw_th(s)
        want = self.ser_thfig if th else fig
        if self.ser_plot.object is not want:
            self.ser_plot.object = want

    def _ser_draw_th(self, s):
        """Time–height quads of the active layer series (stretched grid: cell edges)."""
        run, ds, r = self.run, s["ds"], s["recipe"]
        ks = ser.levels(run, r)
        ts = np.flatnonzero(ds["computed"].values == 1)
        tm = run.times / 60.0
        te = np.concatenate([[tm[0] - 0.5 * (tm[1] - tm[0])], 0.5 * (tm[1:] + tm[:-1]),
                             [tm[-1] + 0.5 * (tm[-1] - tm[-2])]]) if len(tm) > 1 \
            else np.array([tm[0] - 1, tm[0] + 1])
        P = ds["profile"].values
        L, R, B, T, V, H, Z = [], [], [], [], [], [], []
        for t in ts:
            for n, k in enumerate(ks):
                L.append(te[t]), R.append(te[t + 1])
                B.append(run.zf[k]), T.append(run.zf[k + 1])
                V.append(P[t, n]), H.append(run.time_label(t)), Z.append(run.z[k])
        self.ser_th_src.data = dict(l=L, r=R, b=B, t=T, v=V, hms=H, z=Z)
        d = self.F[r["field"]] if r["field"] in self.F else None
        fin = np.asarray(V)[np.isfinite(V)] if V else np.array([])
        lo, hi = np.percentile(fin, [1, 99]) if fin.size else (0.0, 1.0)
        # diverging colours only when the values have both signs (max w: one sign)
        if d is not None and d.diverging and lo < -0.05 * hi and hi > -0.05 * lo:
            m = float(np.percentile(np.abs(fin), 99)) if fin.size else 1.0
            lo, hi, cmap = -(m or 1.0), (m or 1.0), "RdBu_r"
        else:
            lo, hi = (np.percentile(fin, [1, 99]) if fin.size else (0.0, 1.0))
            lo, hi = float(lo), float(hi if hi > lo else lo + 1.0)
            cmap = "viridis"
        if self.ser_cmap.value != "auto":
            cmap = self.ser_cmap.value
        c0, c1 = self._num(self.ser_c0), self._num(self.ser_c1)
        lo, hi = (lo if c0 is None else c0), (hi if c1 is None else c1)
        if hi <= lo:
            hi = lo + (abs(lo) * 0.1 or 1.0)
        pal = palette(cmap, reverse=self.ser_crev.value, lo=lo, hi=hi)
        self.ser_th_map.update(low=lo, high=hi, palette=pal)
        thf = self.ser_thfig
        self._ser_range(thf, "x_range", self._num(self.ser_t0), self._num(self.ser_t1),
                        L + R)
        self._ser_range(thf, "y_range", self._num(self.ser_y0), self._num(self.ser_y1),
                        B + T)
        self.ser_thfig.title.text = s["label"]
        self.ser_thfig.title.text_color = MUTED

    def _on_ser_tap(self, ev, height=False):
        """Click on a series plot (or the track's time series): show that time; on the
        time–height plot also move the map to the clicked height."""
        if ev.x is None:
            return
        if height and ev.y is not None and not self.fill_lvl.disabled:
            run, w = self.run, self.fill_lvl
            if self.fill_mode.value == "level":
                v = float(np.argmin(np.abs(run.z - ev.y)))
            else:
                v = float(np.clip(round(ev.y / 0.25) * 0.25, w.start, w.end))
            if v != w.value:
                w.value = v
        t = int(np.argmin(np.abs(self.run.times / 60.0 - ev.x)))
        if t != self.t:
            self.tslider.value = t
            self._refresh_panels()

    def _on_ser_remove(self, ev, key=None):
        self.series.pop(self.ser_pick.value if key is None else key, None)
        self.ser_pick.options = {v["label"]: k for k, v in self.series.items()}
        if self.ser_pick.value not in self.series:
            self.ser_pick.value = next(iter(self.series), None)
        self._ser_select()
        self._update_items()

    def _on_ser_fmt(self, ev):
        base, _ = os.path.splitext(self.ser_path.value)
        self.ser_path.value = base + ev.new

    def _ser_file_msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.ser_file_msg.object = f'<div class="cv-status"{col}>{html}</div>'

    def _on_ser_save(self, ev):
        s = self.series.get(self.ser_pick.value)
        if s is None:
            return
        path = config.expand(self.ser_path.value.strip())
        if not path:
            return
        if os.path.splitext(path)[1].lower() not in ser.FORMATS:
            path += self.ser_fmt.value
        self.confirm.ask([path], partial(self._save_series, s, path))

    def _save_series(self, s, path):
        try:
            path = ser.save(s["ds"], path)
        except (OSError, ValueError) as e:
            self._ser_file_msg(f"Could not save: {e}", err=True)
            return
        self._ser_file_msg(f"Saved to <code>{path}</code>")

    def _ser_download(self):
        import tempfile
        s = self.series.get(self.ser_pick.value)
        name = self.ser_dl.filename or "series.nc"
        if os.path.splitext(name)[1].lower() not in ser.FORMATS:
            name += self.ser_fmt.value
        with tempfile.TemporaryDirectory() as tmp:
            path = ser.save(s["ds"], os.path.join(tmp, os.path.basename(name)))
            with open(path, "rb") as f:
                return io.BytesIO(f.read())

    def _on_ser_load(self, ev):
        path = os.path.abspath(os.path.expanduser(self.ser_path.value))
        try:
            ds, recipe, note = ser.load(self.run, path, self.F)
        except (OSError, ValueError, KeyError) as e:
            self._ser_file_msg(f"Could not load <code>{path}</code>: {e}", err=True)
            return
        self._ser_add(self._ser_key(recipe, path), ds, recipe, loaded=path)
        self.ser_path.value = path
        warn = (" · pickle files can run code when loaded: open only your own"
                if path.lower().endswith(".pkl") else "")
        self._ser_file_msg(f"Loaded <code>{path}</code>"
                           + (f" · {note}" if note else "") + warn)
        self._show_panel(True, 3)
