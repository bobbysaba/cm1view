"""Parcels: the Parcels panel (choosing parcels, named sets, saving and loading them,
a plot of their values) and their trajectories on the map, the cross-section and in
the 3D view, with heads at the shown time; a set's trajectories exported to netCDF or
CSV (core/parcels.py, export_set; in the "pexp" pool, with progress and Stop).

Parcels are chosen on the map at one parcel time (the shown time or the first one): a
click picks those within a radius, a dragged box those inside it; a height range,
a value range of a parcel variable and a cap apply to both (core/parcels.py, select).
Each choice is a named set, drawn in its own colour or coloured by a parcel variable;
trajectories over all parcel times, up to the shown time or the last minutes of it,
and heads where the parcels are at the shown time (between parcel times: interpolated).
On the cross-section: the parcels within a distance of its line, projected onto it
(the parts of their tails near it, or the whole tails of those near it now), at the
section's own time.  In the 3D view: their tails and heads inside the 3D region, at the
scene's time.  Tails can be seen from a frame moving with the tracked storm or at a set
motion (core/parcels.py, frame_shift), the same as the grid at the time drawn.  The
plot: a variable over the parcel times (each parcel, the mean or median, a band), two
variables against each other at the shown time, or the picked set's w budget (rates or
integrated since the set's time).
Selections and trajectory reads run in the "par" pool.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import os
import time as _time
import traceback
from collections import OrderedDict
from functools import partial

import numpy as np
import panel as pn
from bokeh.models import (ColorBar, ColumnDataSource, HoverTool, Legend, LegendItem,
                          LinearColorMapper, Span)
from bokeh.plotting import figure
from bokeh.transform import transform

from .. import config
from ..core import export as ex, parcels as P, series as ser
from ..core.fields import palette
from ..core.volume3d import floor_colorscale
from ..theme import BG, GRID, MUTED, TEXT
from .numinput import FloatInput
from .ui import _bokeh, _html, style_fig

SET_COLORS = ("#f472b6", "#a3e635", "#38bdf8", "#fb923c", "#c084fc", "#facc15")
MAX_SEGMENTS = 200_000  # per redraw: longer windows are drawn at every n-th parcel time
MAX_3D_POINTS = 300_000  # in the 3D view, likewise
MAX_PLOT_LINES = 300  # per set on the plot: every n-th parcel beyond that
EMPTY_SEG = dict(x0=[], y0=[], x1=[], y1=[], color=[], val=[])
EMPTY_HEAD = dict(x=[], y=[], z=[], color=[], val=[], pid=[], set=[])
BUDGET_COLORS = {"dwdt": TEXT, "b": "#f87171", "vpg": "#60a5fa", "wres": MUTED}
BANDS = {"No band": "", "Min to max": "minmax", "10–90th percentile": "p10p90",
         "25–75th percentile": "p25p75", "Mean ± 1 sd": "sd"}


class ParcelsPanel:
    pf = None  # the run's ParcelFile (None: no parcel output)
    _par_key = None  # what the drawn trajectories show (redrawn only when it changes)
    _par_xs_t = None  # model time (s) of the cross-section shown
    _par_xs_key = _par_3d_key = _pp_key = None  # (likewise, on the section, in 3D, plot)
    _par_busy = None  # (gen, names) of the trajectory read under way
    _pexp_built = False  # (the export row's widgets are made when it first opens)
    _pexp_auto = None  # the export path last filled in (replaced while not edited)

    def _build_parcels(self):
        self.pf = P.for_run(self.run, self.F)
        self.psets = OrderedDict()  # name -> dict(set=ParcelSet, color=)
        self._par_n = 0
        pf = self.pf
        run_motion = (self.run.umove, self.run.vmove)
        pvars = {} if pf is None else {
            f"{n} ({pf.units(n)})" if pf.units(n) else n: n for n in pf.vars
            if n not in ("mtime",)}
        self.par_pick = pn.widgets.RadioButtonGroup(
            options={"Click a point": "Parcels", "Drag a box": "Parcel box"},
            value="Parcels", button_type="primary", button_style="outline",
            margin=(5, 10, 8, 4), description="What a click on the map chooses")
        self.par_radius = FloatInput(name="Radius (km)", value=2.0, start=0.01, step=0.5,
                                     width=90, description="A click picks the parcels "
                                                           "this close to it (horizontally)")
        self.par_z0 = FloatInput(name="From z (km)", value=None, start=0.0, step=0.25,
                                 width=90, description="Only parcels at or above this "
                                                       "height (above sea level); empty: any")
        self.par_z1 = FloatInput(name="To z (km)", value=None, start=0.0, step=0.25,
                                 width=90, description="Only parcels at or below this "
                                                       "height; empty: any")
        self.par_at = pn.widgets.Select(
            name="Choose at", options={"Shown time": "now", "First parcel time": "first"},
            value="now", width=140,
            description="The parcel time the choice is made at: the one nearest the shown "
                        "time, or the first (where parcels are seeded)")
        self.par_var = pn.widgets.Select(name="Where", options={"(any value)": ""} | pvars,
                                         value="", width=150,
                                         description="Only parcels whose value of this "
                                                     "variable is in Min–Max")
        self.par_vmin = FloatInput(name="Min", value=None, width=80, visible=False)
        self.par_vmax = FloatInput(name="Max", value=None, width=80, visible=False)
        self.par_cap = pn.widgets.IntInput(name="At most", value=2000, start=1, step=500,
                                           width=90, description="Keep at most this many "
                                                                 "of the parcels chosen")
        self.par_sample = pn.widgets.Select(
            name="Keeping", options={"Every n-th": "stride", "A random sample": "random"},
            value="stride", width=140)
        self.par_status = _html()
        self.par_list = pn.widgets.Select(name="Sets", options=[], width=220)
        self.par_remove = pn.widgets.Button(name="Remove", icon="trash", button_type="light",
                                            height=32, margin=(5, 4), disabled=True)
        self.par_rename = pn.widgets.TextInput(name="Name", width=160, disabled=True)
        self.par_save = pn.widgets.Button(
            name="Save set", icon="device-floppy", button_type="primary",
            button_style="outline", height=32, margin=(5, 4), disabled=True,
            description="Save the set's parcels under the run's exports folder (parcels/)")
        self.par_export = pn.widgets.Button(
            name="Export set", icon="file-export", button_type="light",
            button_style="outline", height=32, margin=(5, 4), disabled=True,
            description="Write the set's trajectories (positions and values at every "
                        "parcel time) to netCDF or CSV")
        self.par_exp_box = pn.Column(visible=False, margin=0, sizing_mode="stretch_width")
        self.par_saved = pn.widgets.Select(name="Saved sets", options={}, width=200)
        self.par_load = pn.widgets.Button(name="Load", icon="folder-open",
                                          button_type="primary", button_style="outline",
                                          height=32, margin=(5, 4))
        self.par_color = pn.widgets.Select(
            name="Colour by", groups=P.var_choices(pf, {"Set colour": ""}),
            value="z" if "z" in pvars.values() else "", width=150,
            description="A variable of the parcel output, or a 3D field sampled at the "
                        "parcels (between 3D outputs: interpolated in time)")
        self.par_cmap = pn.widgets.Select(name="Colormap", value="viridis", width=120,
                                          options=["viridis", "plasma", "turbo",
                                                   "RdBu_r", "coolwarm", "magma"])
        self.par_window = pn.widgets.Select(
            name="Tails", options={"All parcel times": "all", "Up to the shown time": "until",
                                   "Last minutes": "last", "None (heads only)": "none"},
            value="until", width=170)
        self.par_minutes = FloatInput(name="Minutes", value=10.0, start=0.0, step=5.0,
                                      width=80, visible=False)
        self.par_heads = pn.widgets.Checkbox(name="Heads at the shown time", value=True,
                                             margin=(5, 10, 14, 10))
        self.par_interp = pn.widgets.Checkbox(
            name="Between parcel times: interpolate", value=True, margin=(5, 10, 14, 10))
        self.par_width = FloatInput(name="Line width", value=1.0, start=0.2, step=0.2,
                                    width=80)
        self.par_frame = pn.widgets.Select(
            name="Seen from", value="grid", width=190,
            options={"The grid (as the map)": "grid", "Moving with the tracked storm": "track",
                     "Moving at a motion": "motion"},
            description="Tails relative to the storm: each point moved back by how far the "
                        "storm went between its time and the shown time (the heads stay "
                        "where they are now)")
        self.par_fu = FloatInput(name="u (m/s)", value=run_motion[0], width=80, visible=False,
                                 description="Ground-relative motion of the frame")
        self.par_fv = FloatInput(name="v (m/s)", value=run_motion[1], width=80, visible=False,
                                 description="Ground-relative motion of the frame")
        self.par_alpha = pn.widgets.FloatSlider(name="Opacity", start=0.1, end=1.0,
                                                step=0.05, value=0.7, width=120)
        # on the cross-section and in the 3D view
        self.par_xs_within = FloatInput(
            name="Section ± (km)", value=1.0, start=0.0, step=0.5, width=100,
            description="On the cross-section: the parcels at most this far from its line, "
                        "drawn where they project onto it")
        self.par_xs_tails = pn.widgets.Select(
            name="Tails on the section", value="near", width=210,
            options={"Their parts near it": "near", "Whole, of parcels near it now": "whole"})
        self.par_3d = pn.widgets.Checkbox(name="In the 3D view", value=True,
                                          margin=(5, 10, 14, 10))
        # the plot
        names = list(pvars.values())
        kinds = {"Over time": "time", "Two variables now": "scatter"}
        if pf is not None and pf.has_budget():
            kinds["w budget"] = "budget"
        self.par_plot_kind = pn.widgets.RadioButtonGroup(
            options=kinds, value="time", button_type="primary", button_style="outline",
            margin=(5, 10, 8, 4))
        self.par_plot_y = pn.widgets.Select(
            name="Plot", groups=P.var_choices(pf), width=150,
            value=next((n for n in ("w", "z") if n in names), names[0] if names else None))
        self.par_plot_x = pn.widgets.Select(
            name="Against", groups=P.var_choices(pf), width=150, visible=False,
            value=next((n for n in ("th", "b", "z") if n in names), names[0] if names
                       else None))
        self.par_plot_each = pn.widgets.Checkbox(name="Each parcel", value=True,
                                                 margin=(5, 10, 14, 10))
        self.par_plot_mid = pn.widgets.Select(
            name="Centre", options={"Mean": "mean", "Median": "median", "None": ""},
            value="mean", width=100)
        self.par_plot_band = pn.widgets.Select(name="Band", options=BANDS, value="p10p90",
                                               width=160)
        self.par_plot_int = pn.widgets.Checkbox(
            name="Integrated since the set's time", value=False, visible=False,
            margin=(5, 10, 14, 10))
        self.par_info = _html(self._par_info())
        self._par_glyphs()
        self._par_plot_fig()
        self._par_saved_options()
        self.par_var.param.watch(self._on_par_var, "value")
        self.par_window.param.watch(self._on_par_window, "value")
        self.par_frame.param.watch(self._on_par_frame, "value")
        self.par_pick.param.watch(
            lambda e: self.mode.set(e.new) if self.mode.value in ("Parcels", "Parcel box")
            else None, "value")
        for w in (self.par_color, self.par_cmap, self.par_heads, self.par_interp,
                  self.par_minutes, self.par_width, self.par_xs_within, self.par_xs_tails,
                  self.par_fu, self.par_fv,
                  self.par_3d, self.par_plot_y, self.par_plot_x, self.par_plot_each,
                  self.par_plot_mid, self.par_plot_band, self.par_plot_int):
            w.param.watch(lambda e: self._par_redraw(), "value")
        self.par_plot_kind.param.watch(self._on_par_plot_kind, "value")
        self.par_alpha.param.watch(lambda e: self._par_redraw(), "value_throttled")
        self.par_list.param.watch(self._on_par_pick, "value")
        self.par_remove.on_click(lambda e: self._par_drop(self.par_list.value))
        self.par_rename.param.watch(self._on_par_rename, "value")
        self.par_save.on_click(self._on_par_save)
        self.par_load.on_click(self._on_par_load)
        self.par_export.on_click(self._on_par_export)

    def _par_layout(self):
        """The Parcels tab."""
        return pn.Column(
            _html('<div class="cv-hint">Click the map to choose the parcels near a point, '
                  'or drag a box. The height range, the value range and the cap apply to '
                  'both. Each choice becomes a set.</div>', sizing_mode="stretch_width"),
            pn.FlexBox(self.par_pick, self.par_radius, self.par_z0, self.par_z1,
                       self.par_at, self.par_var, self.par_vmin, self.par_vmax,
                       self.par_cap, self.par_sample, flex_wrap="wrap",
                       align_items="flex-end", gap="0 4px", sizing_mode="stretch_width"),
            self.par_status,
            pn.FlexBox(self.par_list, self.par_rename, self.par_remove, self.par_save,
                       self.par_export, self.par_saved, self.par_load, flex_wrap="wrap",
                       align_items="flex-end", gap="0 4px", sizing_mode="stretch_width",
                       styles={"border-top": f"1px solid {GRID}"}),
            self.par_exp_box,
            pn.FlexBox(self.par_color, self.par_cmap, self.par_window, self.par_minutes,
                       self.par_width, self.par_alpha, self.par_heads, self.par_interp,
                       self.par_frame, self.par_fu, self.par_fv, flex_wrap="wrap",
                       align_items="flex-end", gap="0 4px", sizing_mode="stretch_width",
                       styles={"border-top": f"1px solid {GRID}"}),
            pn.FlexBox(self.par_xs_within, self.par_xs_tails, self.par_3d,
                       flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                       sizing_mode="stretch_width"),
            self.par_info,
            pn.FlexBox(self.par_plot_kind, self.par_plot_y, self.par_plot_x,
                       self.par_plot_each, self.par_plot_mid, self.par_plot_band,
                       self.par_plot_int, flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                       sizing_mode="stretch_width",
                       styles={"border-top": f"1px solid {GRID}"}),
            self.par_plot, scroll="y-auto", sizing_mode="stretch_both")

    def _par_info(self, now=""):
        pf = self.pf
        if pf is None:
            return ('<div class="cv-hint">This run has no parcel output (files named like '
                    'the <code>parcel_glob</code> setting, cm1out_pdata*.nc).</div>')
        run = self.run
        t0, t1 = pf.times[0], pf.times[-1]
        dt = np.median(np.diff(pf.times)) if pf.nt > 1 else 0.0
        files = f" in {len(pf.paths)} files" if len(pf.paths) > 1 else ""
        lab = lambda s: f"{int(s) // 3600}:{int(s) % 3600 // 60:02d}:{int(s) % 60:02d}"  # noqa: E731
        inside = int(((run.times >= t0 - 0.5) & (run.times <= t1 + 0.5)).sum())
        return (f'<div class="cv-hint">{pf.n:,} parcels{files}, {pf.nt} times '
                f'{lab(t0)}–{lab(t1)} (every {dt:g} s); {inside} of the {len(run.times)} 3D '
                f'outputs fall in that span.{now}</div>')

    # ------------------------------------------------------------------ glyphs
    def _par_glyphs(self):
        fig = self.fig
        self.par_mapper = LinearColorMapper(palette=palette("viridis"), low=0, high=1)
        self.par_seg_src = ColumnDataSource(dict(EMPTY_SEG))
        self.par_seg = fig.segment("x0", "y0", "x1", "y1", source=self.par_seg_src,
                                   line_color="color", line_width=1.0, line_alpha=0.7)
        self.par_head_src = ColumnDataSource(dict(EMPTY_HEAD))
        self.par_head = fig.scatter("x", "y", source=self.par_head_src, size=6,
                                    fill_color="color", line_color=BG, line_width=0.5)
        fig.add_tools(HoverTool(renderers=[self.par_head], tooltips=[
            ("parcel", "@set #@pid"), ("z", "@z{0.000} km"), ("value", "@val{0.000}")]))
        self.par_cbar = ColorBar(color_mapper=self.par_mapper, width=10, padding=6,
                                 title="", title_text_color=MUTED,
                                 title_text_font_size="11px", title_text_font_style="normal",
                                 background_fill_color=BG, major_label_text_color=MUTED,
                                 major_tick_line_color=None, bar_line_color=None,
                                 visible=False)
        fig.add_layout(self.par_cbar, "right")
        # on the cross-section: s along it, z (km)
        xf = self.xs_fig
        self.par_xs_src = ColumnDataSource(dict(EMPTY_SEG))
        self.par_xs_seg = xf.segment("x0", "y0", "x1", "y1", source=self.par_xs_src,
                                     line_color="color", line_width=1.0, line_alpha=0.7)
        self.par_xs_head_src = ColumnDataSource(dict(EMPTY_HEAD))
        self.par_xs_head = xf.scatter("x", "y", source=self.par_xs_head_src, size=6,
                                      fill_color="color", line_color=BG, line_width=0.5)
        xf.add_tools(HoverTool(renderers=[self.par_xs_head], tooltips=[
            ("parcel", "@set #@pid"), ("z", "@z{0.000} km"), ("value", "@val{0.000}")]))

    def _par_plot_fig(self):
        """The plot under the panel: lines over time (each parcel, centre, band) or a
        scatter of two variables at the shown time."""
        fig = figure(sizing_mode="stretch_width", height=300, x_axis_label="time (min)",
                     tools="pan,wheel_zoom,box_zoom,reset,save", y_axis_label="")
        style_fig(fig)
        fig.toolbar.autohide = True
        self.pp_band = ColumnDataSource(dict(xs=[], ys=[], color=[]))
        fig.patches("xs", "ys", source=self.pp_band, fill_color="color", fill_alpha=0.2,
                    line_color=None)
        self.pp_each = ColumnDataSource(dict(xs=[], ys=[], color=[]))
        fig.multi_line("xs", "ys", source=self.pp_each, line_color="color", line_alpha=0.25,
                       line_width=1.0)
        self.pp_mid = ColumnDataSource(dict(xs=[], ys=[], color=[], name=[]))
        mid = fig.multi_line("xs", "ys", source=self.pp_mid, line_color="color",
                             line_width=2.5)
        self.pp_scat = ColumnDataSource(dict(x=[], y=[], color=[], pid=[], set=[]))
        sc = fig.scatter("x", "y", source=self.pp_scat, size=4, fill_color="color",
                         fill_alpha=0.7, line_color=None)
        fig.add_tools(HoverTool(renderers=[mid], tooltips=[("", "@name")]),
                      HoverTool(renderers=[sc], tooltips=[("parcel", "@set #@pid"),
                                                          ("x, y", "@x{0.000}, @y{0.000}")]))
        self.pp_bud, self.pp_bud_items = {}, {}  # (the w budget: a line per term)
        for name, col in BUDGET_COLORS.items():
            src = self.pp_bud[name] = ColumnDataSource(dict(x=[], y=[]))
            ln = fig.line("x", "y", source=src, line_color=col, line_width=2.5,
                          line_dash="dashed" if name == "wres" else "solid")
            self.pp_bud_items[name] = LegendItem(label=name, renderers=[ln])
        fig.add_layout(Legend(items=list(self.pp_bud_items.values()), visible=False, location="top_left",
                              click_policy="hide", background_fill_color=BG,
                              background_fill_alpha=0.75, border_line_color=GRID,
                              label_text_color=TEXT, label_text_font_size="11px",
                              spacing=0, padding=4))
        self.pp_now = Span(location=float(self.run.times[self.t]) / 60.0, dimension="height",
                           line_color="#fbbf24", line_width=1.5, line_alpha=0.7)
        fig.add_layout(self.pp_now)
        self.pp_fig = fig
        # a fixed height the column can't squeeze: the plot shows up after the panel was
        # laid out, and shrunk to the room left it was cut off rather than scrolled to
        self.par_plot = _bokeh(fig, sizing_mode="stretch_width", height=300,
                               styles={"flex": "0 0 auto"}, visible=self.pf is not None)

    # ------------------------------------------------------------------ choosing
    def _on_par_var(self, ev):
        self.par_vmin.visible = self.par_vmax.visible = bool(ev.new)

    def _on_par_plot_kind(self, ev):
        self._par_plot_opts()
        self._par_redraw()

    def _par_plot_opts(self):
        kind = self.par_plot_kind.value
        self.par_plot_x.visible = kind == "scatter"
        self.par_plot_y.visible = kind != "budget"
        self.par_plot_each.visible = kind == "time"
        self.par_plot_mid.visible = self.par_plot_band.visible = kind in ("time", "budget")
        self.par_plot_int.visible = kind == "budget"

    def _on_par_frame(self, ev):
        """A set motion starts from the soundings' storm motion (while not typed in)."""
        motion = ev.new == "motion"
        self.par_fu.visible = self.par_fv.visible = motion
        if motion and (self.par_fu.value, self.par_fv.value) == (self.run.umove,
                                                                  self.run.vmove):
            try:
                u, v = self._storm_motion()
                self.par_fu.value, self.par_fv.value = round(float(u), 2), round(float(v), 2)
            except Exception:  # noqa: BLE001  (no sounding storm motion: keep umove, vmove)
                pass
        if self._pexp_built:
            self._pexp_update()
        self._par_redraw()

    def _par_frame_key(self):
        """What the moving frame depends on besides its reference time."""
        f = self.par_frame.value
        if f == "motion":
            return (f, self.par_fu.value, self.par_fv.value)
        if f == "track":
            return (f, tuple((t, fx["x"], fx["y"]) for t, fx in sorted(self.fixes.items())))
        return (f,)

    def _par_moving(self, tr, t):
        """Trajectories tr seen from the chosen frame, the same as the grid at time t."""
        f = self.par_frame.value
        if f == "grid":
            return tr
        shift = P.frame_shift(self.pf, self.run, t, f,
                              (self.par_fu.value or 0.0, self.par_fv.value or 0.0),
                              self.fixes)
        return P.moving(tr, shift)

    def _on_par_window(self, ev):
        self.par_minutes.visible = ev.new == "last"
        self._par_redraw()

    def _par_rule(self):
        z0, z1 = self.par_z0.value, self.par_z1.value
        rule = dict(cap=int(self.par_cap.value or 0), sample=self.par_sample.value,
                    t=None if self.par_at.value == "first" else float(self.run.times[self.t]))
        if z0 is not None or z1 is not None:
            rule["z"] = [-1e9 if z0 is None else z0, 1e9 if z1 is None else z1]
        if self.par_var.value and (self.par_vmin.value is not None
                                   or self.par_vmax.value is not None):
            rule["where"] = [dict(var=self.par_var.value, min=self.par_vmin.value,
                                  max=self.par_vmax.value)]
        return rule

    def _par_choose(self, x=None, y=None, box=None):
        """Choose parcels near (x, y) km (within the radius) or in box (x0, x1, y0, y1)."""
        if self.pf is None:
            return
        rule = self._par_rule()
        if box is not None:
            x0, x1, y0, y1 = box
            rule["box"] = [min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)]
        else:
            rule["near"] = [x, y, float(self.par_radius.value or 1.0)]
        self._par_n += 1
        self._show_panel(True, 5)
        self.request_parcels(rule, f"set {self._par_n}")

    def request_parcels(self, rule, name, color=None):
        """Select (in the par pool), read the trajectories, then add the set."""
        self.gen["par"] += 1
        g = self.gen["par"]
        self.par_status.object = '<div class="cv-status"><span class="busy">Choosing parcels…</span></div>'
        self.pools["par"].submit(self._par_job, rule, name, color, g)

    def _par_job(self, rule, name, color, g):
        try:
            ps = P.select(self.pf, rule, name)
            names = self._par_names()
            self.pf.trajectories(ps, names, self._par_progress(ps, names))
            res = ps
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        self._schedule(partial(self._par_add, res, color, g))

    def _par_progress(self, ps, names):
        """progress(done, total) for sampling 3D fields along the set's trajectories."""
        what = ", ".join(self.pf.long_name(n) for n in names if P.grid_field(n))
        if not what:
            return None

        def show(done, total):
            self._schedule(lambda: setattr(self.par_status, "object", (
                f'<div class="cv-status"><span class="busy">{ps.name}: sampling {what} at '
                f'the parcels, 3D output {done} of {total}…</span></div>')))
        return show

    def _par_failed(self, e):
        self.par_status.object = (f'<div class="cv-status" style="color:#f87171">'
                                  f'Could not read the parcels\' values: {e}</div>')

    def _par_names(self):
        """The trajectory variables drawn: positions, the colour and the plotted ones."""
        extra = [self.par_color.value, self.par_plot_y.value]
        if self.par_plot_kind.value == "scatter":
            extra.append(self.par_plot_x.value)
        elif self.par_plot_kind.value == "budget":
            extra += list(P.BUDGET_NEEDS) + list(P.BUDGET)
        return P.POS + tuple(dict.fromkeys(n for n in extra if n and n not in P.POS))

    def _par_add(self, ps, color=None, g=None):
        if g is not None and g != self.gen["par"]:
            return
        if isinstance(ps, Exception):
            self.par_status.object = (f'<div class="cv-status" style="color:#f87171">'
                                      f'Could not choose parcels: {ps}</div>')
            return
        t = ps.rule.get("t")
        when = "" if t is None else f" at t = {t:g} s"
        if not len(ps):
            self.par_status.object = (f'<div class="cv-status">No parcels there{when}.</div>')
            return
        name = ps.name
        while name in self.psets:
            name += "′"
        ps.name = name
        color = color or SET_COLORS[(len(self.psets)) % len(SET_COLORS)]
        self.psets[name] = dict(set=ps, color=color)
        capped = f" (of {ps.matched:,})" if ps.matched > len(ps) else ""
        self.par_status.object = (f'<div class="cv-status"><b style="color:{color}">{name}'
                                  f'</b>: {len(ps):,} parcels{capped}{when}.</div>')
        self._par_list_options(name)
        self._par_redraw()
        self._update_items()

    def _par_list_options(self, value=None):
        names = list(self.psets)
        self.par_list.options = names
        self.par_list.value = value if value in names else (names[-1] if names else None)
        none = not names
        self.par_remove.disabled = self.par_save.disabled = self.par_rename.disabled = none
        self.par_export.disabled = none
        if none:
            self.par_rename.value = ""
            self.par_exp_box.visible = False
        elif self._pexp_built:
            self._pexp_path_auto()

    def _on_par_pick(self, ev):
        if ev.new:
            self.par_rename.value = ev.new
            if self.par_plot_kind.value == "budget":
                self._par_redraw()
            if self._pexp_built:
                self._pexp_path_auto()
                self._pexp_update()

    def _on_par_rename(self, ev):
        old, new = self.par_list.value, (ev.new or "").strip()
        if not old or not new or new == old or new in self.psets:
            return
        self.psets = OrderedDict((new if k == old else k, v) for k, v in self.psets.items())
        self.psets[new]["set"].name = new
        self._par_list_options(new)
        self._par_key = None
        self._par_redraw()
        self._update_items()

    def _par_drop(self, name):
        if name in self.psets:
            del self.psets[name]
            self._par_list_options()
            self._par_redraw()
            self._update_items()

    def _par_clear(self):
        self.psets.clear()
        self._par_list_options()
        self._par_redraw()
        self._update_items()

    # ------------------------------------------------------------------ files
    def _par_saved_options(self):
        if self.pf is None:
            return
        opts = {os.path.basename(p)[:-4]: p for p in P.list_sets(self.run.path)}
        self.par_saved.options = opts
        self.par_load.disabled = not opts

    def _on_par_save(self, ev):
        e = self.psets.get(self.par_list.value)
        if e is None:
            return
        path = P.set_path(self.run.path, e["set"].name)
        self.confirm.ask([path], partial(self._par_save, e["set"]))

    def _par_save(self, ps):
        try:
            path = P.save_set(self.run.path, ps)
        except OSError as e:
            self.par_status.object = (f'<div class="cv-status" style="color:#f87171">Could '
                                      f'not save: {e}</div>')
            return
        self.par_status.object = f'<div class="cv-status">Saved to <code>{path}</code></div>'
        self._par_saved_options()

    def _on_par_load(self, ev):
        path = self.par_saved.value
        if not path:
            return
        try:
            ps = P.ParcelSet.load(path)
        except (OSError, ValueError, KeyError) as e:
            self.par_status.object = (f'<div class="cv-status" style="color:#f87171">Could '
                                      f'not load: {e}</div>')
            return
        if len(ps.ids) and ps.ids[-1] >= self.pf.n:
            self.par_status.object = ('<div class="cv-status" style="color:#f87171">That set '
                                      'is from parcel output with more parcels.</div>')
            return
        self._show_panel(True, 5)
        self.gen["par"] += 1
        g = self.gen["par"]

        def job():
            try:
                names = self._par_names()
                self.pf.trajectories(ps, names, self._par_progress(ps, names))
                res = ps
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                res = e
            self._schedule(partial(self._par_add, res, None, g))
        self.pools["par"].submit(job)

    # ------------------------------------------------------------------ drawing
    # ------------------------------------------------------------------ export
    def _on_par_export(self, ev):
        """Show (building it the first time) or hide the export row."""
        if not self._pexp_built:
            self._pexp_widgets()
        self.par_exp_box.visible = not self.par_exp_box.visible
        if self.par_exp_box.visible:
            self._pexp_path_auto()
            self._pexp_update()

    def _pexp_widgets(self):
        self._pexp_built = True
        pf = self.pf
        opts = {}
        for group in P.var_choices(pf).values():
            opts.update(group)
        self.pexp_vars = pn.widgets.MultiChoice(
            name="Variables (x, y, z always)", options=opts, width=520,
            value=[n for n in pf.vars if n not in P.EXPORT_SKIP + P.POS],
            search_option_limit=60,
            description="Variables of the parcel output, or 3D fields sampled at the "
                        "parcels (sampling reads each 3D output once)")
        self.pexp_fmt = pn.widgets.Select(
            name="Format", options={"netCDF (.nc)": ".nc", "CSV (.csv)": ".csv"},
            value=".nc", width=120,
            description="netCDF: (time, parcel) arrays, as CM1 writes them; CSV: one row "
                        "per parcel and time")
        self.pexp_times = pn.widgets.Select(
            name="Times", value="all", width=200,
            options={"All parcel times": "all", "Up to the shown time": "until",
                     "Last minutes (as the tails)": "last"})
        self.pexp_every = pn.widgets.IntInput(name="Every n-th", value=1, start=1, width=90)
        self.pexp_path = pn.widgets.TextInput(name="File", width=520)
        self.pexp_zip = pn.widgets.Checkbox(name="Compress (netCDF)", value=True,
                                            margin=(5, 10, 14, 10))
        self.pexp_sr = pn.widgets.Checkbox(
            name="Also x_sr, y_sr (as the tails are seen)", value=True,
            margin=(5, 10, 14, 10))  # (x, y in the tails' frame, equal to them now)
        self.pexp_go = pn.widgets.Button(name="Write", icon="file-export",
                                         button_type="primary", height=32, margin=(5, 4))
        self.pexp_stop = pn.widgets.Button(name="Stop", icon="player-stop",
                                           button_type="light", height=32, margin=(5, 4),
                                           disabled=True)
        self.pexp_note = _html()
        for w in (self.pexp_vars, self.pexp_times, self.pexp_every, self.pexp_sr):
            w.param.watch(lambda e: self._pexp_update(), "value")
        self.pexp_fmt.param.watch(lambda e: (self._pexp_path_auto(), self._pexp_update()),
                                  "value")
        self.pexp_go.on_click(self._on_pexp_go)
        self.pexp_stop.on_click(lambda e: self._pexp_cancel())
        self.par_exp_box.objects = [
            pn.FlexBox(self.pexp_vars, self.pexp_fmt, self.pexp_times, self.pexp_every,
                       self.pexp_path, self.pexp_zip, self.pexp_sr, self.pexp_go,
                       self.pexp_stop,
                       flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                       sizing_mode="stretch_width"),
            self.pexp_note]

    def _pexp_path_auto(self):
        """The default file of the chosen set and format, unless one was typed."""
        e = self.psets.get(self.par_list.value)
        if e is None:
            return
        auto = P.export_path(self.run.path, e["set"], self.pexp_fmt.value)
        if not self.pexp_path.value or self.pexp_path.value == self._pexp_auto:
            self.pexp_path.value = auto
        self._pexp_auto = auto

    def _pexp_plan(self):
        """(set, variables, parcel time indices) of the export, or raises ValueError."""
        e = self.psets.get(self.par_list.value)
        if e is None:
            raise ValueError("no set chosen")
        mode = self.pexp_times.value
        sl = self.pf.window(float(self.run.times[self.t]), mode, self.par_minutes.value)
        ti = np.arange(sl.start, sl.stop, max(1, int(self.pexp_every.value or 1)))
        if not len(ti):
            raise ValueError("no parcel times up to the shown time")
        return e["set"], P.export_names(self.pf, self.pexp_vars.value), ti

    def _pexp_frame(self):
        """(shift, frame text) of the x_sr, y_sr columns, or (None, "")."""
        f = self.par_frame.value
        if f == "grid" or not self.pexp_sr.value:
            return None, ""
        ts = float(self.run.times[self.t])
        motion = (self.par_fu.value or 0.0, self.par_fv.value or 0.0)
        shift = P.frame_shift(self.pf, self.run, ts, f, motion, self.fixes)
        return (None, "") if shift is None else \
            (shift, f"{P.frame_label(f, motion)}, the same as x, y at {ts:g} s")

    def _pexp_update(self):
        if self._pexp_built:
            self.pexp_sr.visible = self.par_frame.value != "grid"
        if not self.pexp_go.disabled:  # (not while one is being written)
            try:
                ps, names, ti = self._pexp_plan()
            except ValueError as e:
                self._pexp_msg(str(e), error=True)
                return
            fmt = "CSV" if self.pexp_fmt.value == ".csv" else "netCDF"
            sr = self._pexp_frame()[0] is not None
            self._pexp_msg(f"{ps.name}: {len(ps):,} parcels × {len(ti)} parcel times × "
                           f"{len(names) + 2 * sr} variables, about "
                           f"{ex.size_text(P.export_bytes(ps, names + ["x"] * 2 * sr, len(ti), fmt))}"
                           + (" before compression" if fmt == "netCDF" else ""))

    def _pexp_msg(self, msg, error=False):
        style = ' style="color:#f87171"' if error else ""
        self.pexp_note.object = f'<div class="cv-status"{style}>{msg}</div>'

    def _on_pexp_go(self, ev):
        try:
            ps, names, ti = self._pexp_plan()
            path = config.expand(self.pexp_path.value.strip()) or \
                P.export_path(self.run.path, ps, self.pexp_fmt.value)
            if not path.endswith(tuple(P.EXPORT_FORMATS)):
                path += self.pexp_fmt.value
            P.export_format(path)
        except ValueError as e:
            self._pexp_msg(str(e), error=True)
            return
        self.confirm.ask([path], partial(self._pexp_start, ps, names, ti, path))

    def _pexp_start(self, ps, names, ti, path):
        self.gen["pexp"] += 1
        g = self.gen["pexp"]
        self.pexp_go.disabled, self.pexp_stop.disabled = True, False
        self._pexp_msg(f'<span class="busy">● Writing {ps.name}…</span>')
        self.pools["pexp"].submit(self._pexp_job, g, ps, names, ti, path,
                                  self.pexp_zip.value, *self._pexp_frame())

    def _pexp_job(self, g, ps, names, ti, path, compress, shift=None, frame=""):
        t0, last = _time.time(), [0.0]

        def progress(done, total, what):
            if _time.time() - last[0] >= 1.0 or done == total:
                last[0] = _time.time()
                self._schedule(partial(self._pexp_progress, g, f"{done}/{total} · {what}"
                                       f" · {_time.time() - t0:.0f} s"))
        sampling = self._par_progress(ps, names)
        try:
            if sampling is not None:  # (3D fields at the parcels: sampled first)
                self.pf.trajectories(ps, names, sampling)
            r = P.export_set(self.pf, ps, path, names, ti, compress, progress,
                             lambda: g != self.gen["pexp"], shift, frame)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._schedule(partial(self._pexp_finish, f"Export error: {e}", True))
            return
        msg = ("Stopped: nothing written." if r["cancelled"] else
               f"Saved <code>{r['path']}</code> · {r['parcels']:,} parcels × {r['times']} "
               f"times · {_time.time() - t0:.0f} s")
        self._schedule(partial(self._pexp_finish, msg, False))

    def _pexp_progress(self, g, what):
        if g == self.gen["pexp"]:
            self._pexp_msg(f'<span class="busy">● Writing… {what}</span>')

    def _pexp_finish(self, msg, error):
        self.par_status.object = ""
        self._pexp_msg(msg, error)
        self.pexp_go.disabled, self.pexp_stop.disabled = False, True

    def _pexp_cancel(self):
        self.gen["pexp"] += 1  # (the job stops after the variable it is on)
        self.pexp_stop.disabled = True
        self._pexp_msg('<span class="busy">● Stopping…</span>')

    def _par_redraw(self):
        """Trajectories (when what they show changed) and heads at the shown time."""
        if self.pf is None:
            return
        cvar = self.par_color.value
        names = self._par_names()
        missing = [e["set"] for e in self.psets.values() if not self.pf.ready(e["set"], names)]
        if missing:  # read first (in the pool: from the cache or the files), then redraw
            g = self.gen["par"]
            if self._par_busy == (g, tuple(names)):
                return  # (already being read)
            self._par_busy = (g, tuple(names))

            def job():
                try:
                    for ps in missing:
                        self.pf.trajectories(ps, names, self._par_progress(ps, names))
                except Exception as e:  # noqa: BLE001
                    traceback.print_exc()
                    self._schedule(partial(self._par_failed, e))
                    return
                finally:
                    self._par_busy = None

                def done():
                    if g == self.gen["par"]:
                        self.par_status.object = ""
                        self._par_redraw()
                self._schedule(done)
            self.pools["par"].submit(job)
            return
        pf, run = self.pf, self.run
        ts = float(run.times[self.t])
        per = P.period(run)
        mode = self.par_window.value
        sl = slice(0, 0) if mode == "none" else pf.window(ts, mode, self.par_minutes.value)
        trajs = [(name, e, pf.trajectories(e["set"], names)) for name, e in self.psets.items()]
        seen = [(name, e, self._par_moving(tr, ts)) for name, e, tr in trajs]
        vals = [tr[cvar] for _, _, tr in trajs] if cvar else []
        if vals:
            lo, hi = P.value_range(vals)
            self.par_mapper.update(palette=palette(self.par_cmap.value), low=lo, high=hi)
            self.par_cbar.title = pf.title(cvar) if P.grid_field(cvar) else \
                f"parcel {pf.title(cvar)}"
        self.par_cbar.visible = bool(vals)
        color = transform("val", self.par_mapper) if cvar else "color"
        for r in (self.par_seg, self.par_xs_seg):
            r.glyph.line_color = color
            r.glyph.line_width = float(self.par_width.value or 1.0)
            r.glyph.line_alpha = float(self.par_alpha.value)
        self.par_head.glyph.fill_color = self.par_xs_head.glyph.fill_color = color
        frame = self._par_frame_key()
        key = (tuple((n, e["set"].key, e["color"]) for n, e in self.psets.items()), cvar,
               sl.start, sl.stop, self.par_cmap.value, frame, ts if frame[0] != "grid" else None)
        if key != self._par_key:
            self._par_key = key
            self.par_seg_src.data = _segments(seen, sl, cvar, per)
        heads = dict(EMPTY_HEAD)
        if self.par_heads.value and trajs:
            parts = []
            for name, e, tr in seen:
                x, y, z = P.heads(pf, tr, ts, self.par_interp.value, per)
                v = P.at_time(pf, tr[cvar], ts, self.par_interp.value) if cvar else z
                ok = np.isfinite(x) & np.isfinite(y)
                parts.append(dict(x=x[ok], y=y[ok], z=z[ok], val=v[ok],
                                  color=np.full(ok.sum(), e["color"]),
                                  pid=e["set"].ids[ok], set=np.full(ok.sum(), name)))
            heads = {k: np.concatenate([p[k] for p in parts]) for k in EMPTY_HEAD}
        self.par_head_src.data = heads
        self._par_xs(trajs)
        self._par_3d(trajs)
        self._par_plot(trajs, ts)
        self._par_note()

    def _par_note(self):
        """The time note under the panel: which parcel time the heads are at."""
        if self.pf is None:
            return
        if not self.psets:
            self.par_info.object = self._par_info()
            return
        ts = float(self.run.times[self.t])
        b = self.pf.bracket(ts)
        if b is None:
            txt = "no parcel output at the shown time"
        elif b[0] == b[1]:
            txt = f"heads at parcel time {self.pf.times[b[0]]:g} s"
        elif self.par_interp.value:
            txt = (f"heads between parcel times {self.pf.times[b[0]]:g} and "
                   f"{self.pf.times[b[1]]:g} s")
        else:
            txt = f"heads at parcel time {self.pf.times[b[0]]:g} s (the one before)"
        f = self.par_frame.value
        if f == "track" and len(self.fixes) < 2:
            txt += "; no track of two fixes or more yet, so tails as on the grid"
        elif f != "grid":
            txt += "; tails " + P.frame_label(f, (self.par_fu.value or 0.0,
                                                  self.par_fv.value or 0.0))
        self.par_info.object = self._par_info(f" Now: {txt}.")

    # ------------------------------------------------------------------ cross-section
    def _par_look_key(self):
        """What every drawing of the trajectories depends on besides the time."""
        return (tuple((n, e["set"].key, e["color"]) for n, e in self.psets.items()),
                self.par_color.value, self.par_cmap.value, self.par_window.value,
                self.par_minutes.value, self.par_heads.value, self.par_interp.value,
                self._par_frame_key())

    def _par_xs(self, trajs):
        """The parcels within ± the distance of the section's line, projected onto it,
        at the section's time: heads, and the parts of their tails near it (or whole)."""
        t = self._par_xs_t
        if len(self.xs_pts) != 2 or t is None or not trajs:
            if self._par_xs_key is not None:
                self._par_xs_key = None
                self.par_xs_src.data, self.par_xs_head_src.data = dict(EMPTY_SEG), \
                    dict(EMPTY_HEAD)
            return
        A, B = self.xs_pts
        w = float(self.par_xs_within.value or 0.0)
        key = (self._par_look_key(), tuple(self.xs_pts), t, w, self.par_xs_tails.value)
        if key == self._par_xs_key:
            return
        self._par_xs_key = key
        pf, per, cvar = self.pf, P.period(self.run), self.par_color.value
        L = float(np.hypot(B[0] - A[0], B[1] - A[1]))
        mode = self.par_window.value
        sl = slice(0, 0) if mode == "none" else pf.window(t, mode, self.par_minutes.value)
        idx = P.thin_times(sl, sum(len(e["set"]) for _, e, _ in trajs), MAX_SEGMENTS)
        whole = self.par_xs_tails.value == "whole"

        def inside(s, d):
            return np.isfinite(s) & (np.abs(d) <= w) & (s >= 0.0) & (s <= L)

        segs, hds = {k: [] for k in EMPTY_SEG}, []
        for name, e, tr in trajs:
            tr = self._par_moving(tr, t)
            hx, hy, hz = P.heads(pf, tr, t, self.par_interp.value, per)
            hs, hd = P.section_xy(hx, hy, A, B)
            near = inside(hs, hd)
            if self.par_heads.value:
                v = P.at_time(pf, tr[cvar], t, self.par_interp.value) if cvar else hz
                hds.append(dict(x=hs[near], y=hz[near], z=hz[near], val=v[near],
                                color=np.full(int(near.sum()), e["color"]),
                                pid=e["set"].ids[near], set=np.full(int(near.sum()), name)))
            if len(idx) < 2:
                continue
            x, y, z = tr["x"][idx], tr["y"][idx], tr["z"][idx]
            S, D = P.section_xy(x, y, A, B)
            ok = P.joined(x, y, per) & np.isfinite(z[:-1]) & np.isfinite(z[1:])
            if whole:
                ok &= near[None, :]
            else:
                into = inside(S, D)
                ok &= into[:-1] & into[1:]
            v = tr[cvar][idx] if cvar else z
            for k, a in (("x0", S[:-1]), ("x1", S[1:]), ("y0", z[:-1]), ("y1", z[1:]),
                         ("val", 0.5 * (v[:-1] + v[1:]))):
                segs[k].append(a[ok])
            segs["color"].append(np.full(int(ok.sum()), e["color"]))
        self.par_xs_src.data = ({k: np.concatenate(v) for k, v in segs.items()}
                                if segs["x0"] else dict(EMPTY_SEG))
        self.par_xs_head_src.data = ({k: np.concatenate([h[k] for h in hds])
                                      for k in EMPTY_HEAD} if hds else dict(EMPTY_HEAD))

    # ------------------------------------------------------------------ 3D view
    def _par_3d_traces(self, fig):
        """Empty parcel traces in a new 3D scene (filled by _par_3d, then restyled)."""
        if self.pf is None:
            return
        import plotly.graph_objects as go
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="lines", meta="parcels",
                                   connectgaps=False, line=dict(width=3), hoverinfo="skip",
                                   name="Parcels", showlegend=False))
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="markers", meta="parcelheads",
                                   marker=dict(size=3, line=dict(color=BG, width=0.5)),
                                   hovertemplate="%{customdata}<br>z %{z:.2f} km"
                                                 "<extra></extra>",
                                   name="Parcel heads", showlegend=False))
        self._par_3d_key = None

    def _par_3d(self, trajs):
        """Tails and heads inside the 3D region at the scene's time."""
        _, lines = self._trace("parcels")
        _, hd = self._trace("parcelheads")
        s3 = self._s3
        if lines is None or hd is None or s3 is None:
            return
        show = bool(self.par_3d.value and trajs)
        key = (self._par_look_key(), s3["t"], s3.get("box"), s3.get("ztop"), show,
               self.par_width.value, self.par_alpha.value,
               self.par_mapper.low, self.par_mapper.high)
        if key == self._par_3d_key:
            return
        self._par_3d_key = key
        if not show:
            lines.update(x=[], y=[], z=[])
            hd.update(x=[], y=[], z=[], customdata=[])
            return
        pf, run, per, cvar = self.pf, self.run, P.period(self.run), self.par_color.value
        t = float(run.times[s3["t"]])
        x0, x1, y0, y1 = s3["box"]
        ztop = float(s3["ztop"])
        mode = self.par_window.value
        sl = slice(0, 0) if mode == "none" else pf.window(t, mode, self.par_minutes.value)
        idx = P.thin_times(sl, sum(len(e["set"]) for _, e, _ in trajs), MAX_3D_POINTS)
        colors = [e["color"] for _, e, _ in trajs]

        def out(x, y, z):
            return ~((np.minimum(x0, x1) <= x) & (x <= np.maximum(x0, x1))
                     & (np.minimum(y0, y1) <= y) & (y <= np.maximum(y0, y1)) & (z <= ztop))

        parts, heads = [], []
        for k, (name, e, tr) in enumerate(trajs):
            tr = self._par_moving(tr, t)
            if len(idx) >= 2:
                c = tr[cvar][idx] if cvar else np.full((len(idx), len(e["set"])), k,
                                                       np.float32)
                pl = P.polylines(dict(x=tr["x"][idx], y=tr["y"][idx], z=tr["z"][idx], c=c),
                                 per=per)
                bad = out(pl["x"], pl["y"], pl["z"])
                for a in ("x", "y", "z"):
                    pl[a][bad] = np.nan
                parts.append(pl)
            if self.par_heads.value:
                hx, hy, hz = P.heads(pf, tr, t, self.par_interp.value, per)
                v = P.at_time(pf, tr[cvar], t, self.par_interp.value) if cvar \
                    else np.full(len(hx), k, np.float32)
                ok = np.isfinite(hx) & np.isfinite(hz) & ~out(hx, hy, hz)
                heads.append((hx[ok], hy[ok], hz[ok], v[ok],
                              [f"{name} #{i}" for i in e["set"].ids[ok]]))
        if cvar:
            scale = dict(colorscale=floor_colorscale(self.par_cmap.value),
                         cmin=self.par_mapper.low, cmax=self.par_mapper.high)
        else:
            n = len(colors)
            scale = dict(colorscale=[[f, c] for k, c in enumerate(colors)
                                     for f in (k / n, (k + 1) / n)],
                         cmin=-0.5, cmax=n - 0.5)
        bar = dict(showscale=bool(cvar), colorbar=dict(
            title=dict(text=self.par_cbar.title if cvar else "", font=dict(color=MUTED, size=11)),
            thickness=12, len=0.5, x=0.0, xanchor="left", y=0.5,
            tickfont=dict(color=MUTED, size=10), outlinewidth=0))

        def cat(k, src):
            return np.concatenate([p[k] for p in src]) if src else np.zeros(0)
        c = np.nan_to_num(cat("c", parts), nan=float(scale["cmin"]))
        lines.update(x=cat("x", parts), y=cat("y", parts), z=cat("z", parts),
                     opacity=float(self.par_alpha.value),
                     line=dict(color=c, width=2 * float(self.par_width.value or 1.0),
                               **scale, **bar))
        hcol = [np.concatenate([h[i] for h in heads]) if heads else np.zeros(0)
                for i in range(4)]
        hd.update(x=hcol[0], y=hcol[1], z=hcol[2],
                  customdata=[s for h in heads for s in h[4]],
                  marker=dict(color=np.nan_to_num(hcol[3], nan=float(scale["cmin"])),
                              **scale))

    # ------------------------------------------------------------------ the plot
    def _par_plot(self, trajs, ts):
        """A variable over the parcel times (each parcel, centre, band) per set, or two
        variables against each other at the shown time."""
        pf, fig = self.pf, self.pp_fig
        self.par_plot.visible = bool(trajs)
        kind, yv = self.par_plot_kind.value, self.par_plot_y.value
        self.pp_now.location = ts / 60.0
        self.pp_now.visible = kind == "time"
        budget = kind == "budget"
        self.pp_fig.legend[0].visible = budget and bool(trajs)
        if not budget or not trajs:
            for src in self.pp_bud.values():
                src.data = dict(x=[], y=[])
        if not trajs or not (yv or budget):
            self._pp_key = None
            for src in (self.pp_band, self.pp_each, self.pp_mid, self.pp_scat):
                src.data = {k: [] for k in src.data}
            return
        if budget:
            self._par_budget(trajs)
            return

        label = pf.title
        fig.yaxis.axis_label = label(yv)
        if kind == "scatter":
            self._pp_key = None
            xv, per = self.par_plot_x.value, P.period(self.run)
            fig.xaxis.axis_label = label(xv)
            parts = []
            for name, e, tr in trajs:
                a = _value_at(pf, tr, xv, ts, self.par_interp.value, per)
                b = _value_at(pf, tr, yv, ts, self.par_interp.value, per)
                ok = np.isfinite(a) & np.isfinite(b)
                parts.append(dict(x=a[ok], y=b[ok], color=np.full(int(ok.sum()), e["color"]),
                                  pid=e["set"].ids[ok], set=np.full(int(ok.sum()), name)))
            self.pp_scat.data = {k: np.concatenate([p[k] for p in parts])
                                 for k in self.pp_scat.data}
            for src in (self.pp_band, self.pp_each, self.pp_mid):
                src.data = {k: [] for k in src.data}
            return
        key = (tuple((n, e["set"].key, e["color"]) for n, e in self.psets.items()), yv,
               self.par_plot_each.value, self.par_plot_mid.value, self.par_plot_band.value)
        if key == self._pp_key:
            return
        self._pp_key = key
        fig.xaxis.axis_label = "time (min)"
        tm = pf.times / 60.0
        each = dict(xs=[], ys=[], color=[])
        mid = dict(xs=[], ys=[], color=[], name=[])
        band = dict(xs=[], ys=[], color=[])
        how, centre = self.par_plot_band.value, self.par_plot_mid.value
        for name, e, tr in trajs:
            a = tr[yv]
            if self.par_plot_each.value:
                cols = range(0, a.shape[1], max(1, int(np.ceil(a.shape[1] / MAX_PLOT_LINES))))
                each["xs"] += [tm] * len(cols)
                each["ys"] += [a[:, j] for j in cols]
                each["color"] += [e["color"]] * len(cols)
            if not (how or centre) or a.shape[1] < 2:
                continue
            c, lo, hi = ser.band(a.T, how or "minmax", centre)
            if centre:
                mid["xs"].append(tm)
                mid["ys"].append(c)
                mid["color"].append(e["color"])
                mid["name"].append(f"{name}: {centre}")
            if how:
                for xs, ys in _band_polys(tm, lo, hi):
                    band["xs"].append(xs)
                    band["ys"].append(ys)
                    band["color"].append(e["color"])
        self.pp_each.data, self.pp_mid.data, self.pp_band.data = each, mid, band
        self.pp_scat.data = {k: [] for k in self.pp_scat.data}

    def _par_budget(self, trajs):
        """The w budget of the set picked in Sets (else the last): the centre of each
        term over its parcels, a band if chosen; integrated: Δw and the time integrals
        of b, vpg and the rest since the set was chosen."""
        pf, fig = self.pf, self.pp_fig
        name = self.par_list.value if self.par_list.value in self.psets else trajs[-1][0]
        e, tr = next((e, tr) for n, e, tr in trajs if n == name)
        how, centre = self.par_plot_band.value, self.par_plot_mid.value or "mean"
        integ = self.par_plot_int.value
        key = ("budget", name, e["set"].key, how, centre, integ)
        if key == self._pp_key:
            return
        self._pp_key = key
        fig.xaxis.axis_label = "time (min)"
        u = pf.units("dwdt")
        fig.yaxis.axis_label = (f"{name}: w budget, integrated ({pf.units('w')})" if integ
                                else f"{name}: w budget ({u})")
        tm = pf.times / 60.0
        i0 = P.ref_index(pf, e["set"].rule)
        band = dict(xs=[], ys=[], color=[])
        for term, src in self.pp_bud.items():
            a = tr["w"] if integ and term == "dwdt" else tr[term]
            if integ:
                a = P.since(pf.times, a, i0, "delta" if term == "dwdt" else "int")
            c, lo, hi = ser.band(np.asarray(a, dtype=np.float64).T, how or "minmax", centre)
            src.data = dict(x=tm, y=c)
            lab = P.var_label(term)
            if integ:
                lab = "Δw" if term == "dwdt" else f"∫ ({lab}) dt" if " " in lab \
                    else f"∫ {lab} dt"
            self.pp_bud_items[term].label = lab
            if how and a.shape[1] > 1:
                for xs, ys in _band_polys(tm, lo, hi):
                    band["xs"].append(xs)
                    band["ys"].append(ys)
                    band["color"].append(BUDGET_COLORS[term])
        self.pp_band.data = band
        for src in (self.pp_each, self.pp_mid, self.pp_scat):
            src.data = {k: [] for k in src.data}

    # ------------------------------------------------------------------ session
    def _par_state(self):
        return dict(sets=[dict(name=n, color=e["color"], rule=e["set"].rule,
                               ids=None if e["set"].rule else e["set"].ids.tolist())
                          for n, e in self.psets.items()],
                    look=dict(color=self.par_color.value, cmap=self.par_cmap.value,
                              window=self.par_window.value, minutes=self.par_minutes.value,
                              heads=self.par_heads.value, interp=self.par_interp.value,
                              frame=self.par_frame.value, frame_u=self.par_fu.value,
                              frame_v=self.par_fv.value, width=self.par_width.value, alpha=self.par_alpha.value,
                              xs_within=self.par_xs_within.value,
                              xs_tails=self.par_xs_tails.value, in3d=self.par_3d.value,
                              plot=self.par_plot_kind.value, plot_y=self.par_plot_y.value,
                              plot_x=self.par_plot_x.value, each=self.par_plot_each.value,
                              mid=self.par_plot_mid.value, band=self.par_plot_band.value,
                              plot_int=self.par_plot_int.value))

    def _put_parcels(self, pr, put):
        if not pr or self.pf is None:
            return
        look = pr.get("look", {})
        for k, w in (("color", self.par_color), ("cmap", self.par_cmap),
                     ("window", self.par_window), ("minutes", self.par_minutes),
                     ("heads", self.par_heads), ("interp", self.par_interp),
                     ("frame_u", self.par_fu), ("frame_v", self.par_fv),
                     ("frame", self.par_frame), ("width", self.par_width), ("alpha", self.par_alpha),
                     ("xs_within", self.par_xs_within), ("xs_tails", self.par_xs_tails),
                     ("in3d", self.par_3d), ("plot", self.par_plot_kind),
                     ("plot_y", self.par_plot_y), ("plot_x", self.par_plot_x),
                     ("each", self.par_plot_each), ("mid", self.par_plot_mid),
                     ("band", self.par_plot_band), ("plot_int", self.par_plot_int)):
            put(w, look.get(k), f"parcel {k}")
        self.psets.clear()
        self._par_list_options()
        items = pr.get("sets") or []
        if not items:
            self._par_redraw()
            return
        self.gen["par"] += 1
        g = self.gen["par"]

        def job():
            out = []
            for it in items:
                try:
                    if it.get("rule"):
                        ps = P.select(self.pf, it["rule"], it["name"])
                    else:
                        ps = P.ParcelSet(it.get("ids") or [], it["name"])
                    names = self._par_names()
                    self.pf.trajectories(ps, names, self._par_progress(ps, names))
                    out.append((ps, it.get("color")))
                except Exception:  # noqa: BLE001
                    traceback.print_exc()

            def apply():
                if g != self.gen["par"]:
                    return
                for ps, col in out:
                    self._par_add(ps, col)
            self._schedule(apply)
        self.pools["par"].submit(job)


def _value_at(pf, tr, name, t, interp, per):
    """Variable `name` of trajectories tr at model time t (x, y: wrap-aware)."""
    axis = {"x": 0, "y": 1}.get(name)
    return P.at_time(pf, tr[name], t, interp, (per or (None, None))[axis]
                     if axis is not None else None)


def _band_polys(t, lo, hi):
    """[(xs, ys)] polygons of a band lo..hi over t, one per stretch where it is there."""
    ok = np.isfinite(lo) & np.isfinite(hi)
    edges = np.flatnonzero(np.diff(np.concatenate([[0], ok.astype(np.int8), [0]])))
    return [(np.concatenate([t[a:b], t[a:b][::-1]]), np.concatenate([hi[a:b], lo[a:b][::-1]]))
            for a, b in zip(edges[::2], edges[1::2]) if b - a > 1]


def _segments(trajs, sl, cvar, per):
    """Segment glyph data for the trajectories over parcel times sl: no segment across a
    gap (NaN) or a wrap across a periodic boundary; at most MAX_SEGMENTS (every n-th
    parcel time beyond that)."""
    idx = P.thin_times(sl, sum(len(e["set"]) for _, e, _ in trajs), MAX_SEGMENTS)
    if len(idx) < 2:
        return dict(EMPTY_SEG)
    out = {k: [] for k in EMPTY_SEG}
    for name, e, tr in trajs:
        x, y = tr["x"][idx], tr["y"][idx]
        ok = P.joined(x, y, per)
        v = tr[cvar][idx] if cvar else tr["z"][idx]
        for k, a in (("x0", x[:-1]), ("x1", x[1:]), ("y0", y[:-1]), ("y1", y[1:]),
                     ("val", 0.5 * (v[:-1] + v[1:]))):
            out[k].append(a[ok])
        out["color"].append(np.full(int(ok.sum()), e["color"]))
    if not out["x0"]:
        return dict(EMPTY_SEG)
    return {k: np.concatenate(v) for k, v in out.items()}
