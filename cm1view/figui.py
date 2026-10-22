"""Figure workspace: build a publication figure from panels and layers (from one run or
several, e.g. tornadic vs non-tornadic), preview it at its final size, and export the
image, a stand-alone script, the data and the spec.

The editor has five tabs: Panels (what the grid shows: kind, size, times, titles,
area, runs), Layers (what each panel draws), Style (fonts, axes, labels, colorbar,
legend, spacing), Annotate and Export.  Saving sits above the preview.

The FigureEditor is here; its runs (figruns), sources and lists (figsources) and export
(figexport) are mixins, and the constants, helpers and cards are in figparts."""

import base64
import io
import json
import os
import struct
import time as _time
import traceback
from collections import OrderedDict
from functools import partial

import panel as pn

from . import config, figdraw, figure as fg, series as ser
from .theme import GRID
from .figparts import (
    ANN_KINDS, CB_LOCS, CB_MODES, FIG_CMAPS, FONTS, LABEL_LOCS, LETTERS, LOCS, MATH_FONTS,
    NONE, SIZE_PRESETS, TICKDIR, TYPE_LABEL, VARY, LayerCard, _auto, _chk, _f, _grid,
    _hint, _num, _row, _section, _when,
)
# the editor's feature groups, one module each
from .figexport import FigureExport
from .figruns import FigureRuns
from .figsources import FigureSources


class FigureEditor(FigureRuns, FigureSources, FigureExport):
    def __init__(self, viewer):
        self.v = viewer
        self.run, self.F = viewer.run, viewer.F
        self.cache = OrderedDict()  # data key -> panel arrays
        self._opened = {}  # run path -> (CM1Run, Fields) when the viewer has no registry
        self._tracks = {}  # track file -> (mtime, run path, fixes)
        self._track_err = {}  # track file -> error text
        self._hold = False  # widgets being set from a spec: no re-render per widget
        self._req = 0
        self.cards = []
        self.ser_cards, self.snd_cards, self.ann_rows = [], [], []
        self.tm_rows, self.title_ws = [], []
        # undo / redo: specs (JSON) before each change, and the ones undone
        self._hist, self._future, self._last, self._restoring = [], [], None, False
        self._png = None  # (width, height) px and dpi of the shown preview
        self._lims = {}  # panel -> (xlim, ylim) of the last preview, to place annotations
        # series of time-height / time-series figures: (run path, recipe, track) ->
        # dataset (filled in place while it is computed); state "running" / "done"
        self._ser_mem, self._ser_state, self._ser_prog = {}, {}, {}
        self.snd_cache = OrderedDict()  # sounding (run, time, where, track) -> analysis
        from concurrent.futures import ThreadPoolExecutor
        viewer.pools["figser"] = ThreadPoolExecutor(1, thread_name_prefix="cm1view-figser")
        viewer.gen["figser"] = 0
        self._build()
        self.set_spec(self._default())

    # ------------------------------------------------------------ widgets
    def _build(self):
        run = self.run
        self.topts = {f"{run.time_label(t)}  ({run.times[t] / 60:g} min)": t
                      for t in range(len(run.times))}
        # new figure from ...
        nb = dict(button_type="light", button_style="outline", height=30, margin=(2, 3))
        self.start_map = pn.widgets.Button(
            name="Map view", description="One panel of what the map shows now: its field, "
                                         "contours, winds and view", **nb)
        self.start_xs = pn.widgets.Button(
            name="Cross-section", description="One panel of the map's cross-section (draw "
                                              "one with the Section tool first)", **nb)
        self.start_ser = pn.widgets.Button(
            name="Series", description="Time–height panels (layer series) or time series of "
                                       "the series computed with the Series tool, for every "
                                       "run of the figure", **nb)
        self.start_snd = pn.widgets.Button(
            name="Soundings", description="Skew-T panels of the map's soundings (or the "
                                          "storm's inflow at the shown time)", **nb)
        self.start_def = pn.widgets.Button(
            name="Time grid", description="Plan views centred on the storm at several times "
                                          "from the shown time", **nb)
        ib = dict(name="", button_type="light", button_style="outline", width=36, height=32,
                  margin=(4, 2))
        self.undo_btn = pn.widgets.Button(icon="arrow-back-up", description="Undo", **ib)
        self.redo_btn = pn.widgets.Button(icon="arrow-forward-up", description="Redo", **ib)
        # ---- Panels: grid and size
        self.kind = pn.widgets.Select(name="Panels show", options={
            "Plan views": "plan", "Vertical cross-sections": "xsec",
            "Time–height (series)": "th", "Time series": "line", "Soundings": "sounding"})
        self.vary = pn.widgets.Select(name="Panels differ in", options=VARY)
        self.run_sel = pn.widgets.Select(name="Run", options={})
        self.runs_as = pn.widgets.Select(name="Runs are", options={
            "Rows": "rows", "Columns": "cols"})
        self.rows = pn.widgets.IntInput(name="Rows", start=1, end=8)
        self.cols = pn.widgets.IntInput(name="Columns", start=1, end=8)
        self.size_preset = pn.widgets.Select(name="Size", options=SIZE_PRESETS, value="")
        self.width = _f("Width (in)", 8.0, step=0.25, start=1.0)
        self.height = _f("Height (in)", 6.0, step=0.25, start=1.0)
        self.fit_btn = pn.widgets.Button(
            name="Fit height", height=32, button_type="light",
            button_style="outline", description="The height the panels need at this width "
                                                 "(with room for labels, titles and colorbars)")
        # ---- Panels: times, fields, run & time of each panel
        self.time1 = pn.widgets.Select(name="Time (every panel)", options=self.topts)
        self.tstep = pn.widgets.IntInput(name="Every … outputs", value=5, start=1)
        self.tfill = pn.widgets.Button(name="Fill from the shown time", height=32,
                                       button_type="light", button_style="outline")
        self.tm_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.pf_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.pf_rows = []
        self.pc_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.pc_rows = []
        # ---- Panels: titles
        self.suptitle = pn.widgets.TextInput(name="Figure title (blank: none)",
                                             sizing_mode="stretch_width")
        self.titles_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.auto_titles = pn.widgets.Button(name="Fill in from fields, times or runs",
                                             height=32, button_type="light",
                                             button_style="outline")
        self.clear_titles = pn.widgets.Button(name="Clear", height=32, button_type="light",
                                              button_style="outline")
        # ---- Panels: area
        self.dom = pn.widgets.Select(name="Plan-view area", options={
            "Centred on tracked storm": "storm", "Fixed box (map view)": "box",
            "Whole domain": "full"})
        self.half = _f("Half-width (km)", 12.5, step=0.5, start=0.5)
        self.box_btn = pn.widgets.Button(name="Use current map view", height=32,
                                         button_type="light", button_style="outline")
        self.box_html = pn.pane.HTML(margin=(2, 4))
        self.coords = pn.widgets.Select(name="Axis coordinates", options={
            "Model grid x, y": "grid", "Relative to the storm": "storm"})
        self.xs_mode = pn.widgets.Select(name="Section", options={
            "Through tracked storm": "storm", "Fixed A–B from the map": "fixed"})
        self.xs_angle = _f("Direction (° from east)", 0.0, step=15)
        self.xs_half = _f("Half-length (km)", 10.0, step=1, start=0.5)
        self.xs_offx = _f("Offset x (km)", 0.0, step=0.5)
        self.xs_offy = _f("Offset y (km)", 0.0, step=0.5)
        self.xs_top = _f("Top (km)", 6.0, step=0.5, start=0.5)
        self.xs_ab = pn.widgets.Button(name="Use map A–B", height=32, button_type="light",
                                       button_style="outline")
        self.xs_html = pn.pane.HTML(margin=(2, 4))
        # ---- Panels: runs
        self.runs_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.run_rows = []
        self.add_sel = pn.widgets.Select(name="Add a run (next to this one, or recent)",
                                         options={}, sizing_mode="stretch_width")
        self.add_path = pn.widgets.TextInput(name="… or its folder", placeholder="/path/to/run")
        self.add_btn = pn.widgets.Button(name="+ Add run", button_type="primary",
                                         button_style="outline", height=32)
        self.runs_msg = pn.pane.HTML(sizing_mode="stretch_width")
        # ---- Layers
        self.layer_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.add_btns = {k: pn.widgets.Button(name=f"+ {TYPE_LABEL[k]}", height=30,
                                              button_type="light", button_style="outline",
                                              margin=(4, 2))
                         for k in TYPE_LABEL}
        self.plan_layers = pn.Column(
            _hint("Layers are drawn in order, the last on top. Fold a layer away with its "
                  "arrow; untick it to hide it without removing it."),
            _row(*self.add_btns.values()), self.layer_box, sizing_mode="stretch_width",
            margin=0)
        # series (time-height and time-series panels)
        self.ser_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.ser_from = pn.widgets.Select(name="A series from the Series tool", options={})
        self.ser_add = pn.widgets.Button(name="+ Add", button_type="primary",
                                         button_style="outline", height=32)
        self.ser_new = pn.widgets.Button(name="+ New series", button_type="light",
                                         button_style="outline", height=32)
        self.series_col = pn.Column(
            _hint('Each series is computed for every run of the figure (<b>Panels → Runs</b>; '
                  'regions around the storm use each run’s track) and cached, like the Series '
                  'tool. Time–height panels: a row per series and a column per run. Time '
                  'series: series with the same <b>Panel</b> number share a panel; other units '
                  'get their own axis.'),
            _grid((self.ser_from, 2), self.ser_add, self.ser_new), self.ser_box,
            sizing_mode="stretch_width", margin=0)
        # soundings
        sk = self.sk = dict(
            pmax=_f("Bottom (hPa)", 1000.0, step=25), pmin=_f("Top (hPa)", 100.0, step=25),
            skew=_f("Skew", 35.0, step=5),
            tmin=_f("T left (°C)", -40.0, step=5), tmax=_f("T right (°C)", 50.0, step=5),
            lw=_f("Line width", 1.8, step=0.2),
            parcel=pn.widgets.Select(name="Parcel", options={
                "Mixed layer": "ml", "Surface": "sb", "Most unstable": "mu", "None": "none"}),
            params=_chk("CAPE / CIN in legend", True), legend=_chk("Legend (one sounding)", False),
            guides=_chk("Adiabats", True), barbs=_chk("Wind barbs", True),
            hodo=_chk("Hodograph", True), hodo_max=_f("Hodograph ± (m/s)", 40.0, step=5),
            hodo_top=_f("Hodograph top (km)", 9.0, step=1),
            legend_loc=pn.widgets.Select(name="Legend at", options=LOCS))
        self.snd_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.snd_tab = pn.widgets.Button(name="+ The map's soundings", height=32,
                                         button_type="primary", button_style="outline")
        self.snd_new = pn.widgets.Button(name="+ Sounding", button_type="light",
                                         button_style="outline", height=32)
        self.snd_col = pn.Column(
            _hint("Soundings with the same <b>Panel</b> number share a skew-T (colour = "
                  "sounding). Storm soundings follow each run’s track."),
            _row(self.snd_tab, self.snd_new), self.snd_box,
            _section("Skew-T and hodograph", _grid(*sk.values())),
            sizing_mode="stretch_width", margin=0)
        # time axes of time-height / time-series panels
        self.ts_tmin = pn.widgets.TextInput(name="From (min)", placeholder="data")
        self.ts_tmax = pn.widgets.TextInput(name="To (min)", placeholder="data")
        self.ts_zmin = _f("Bottom (km)", 0.0, step=0.5)
        self.ts_zmax = _f("Top (km)", 10.0, step=0.5)
        self.ts_ymin = _auto("y from (left axis)")
        self.ts_ymax = _auto("y to (left axis)")
        self.ts_legend = _chk("Legend", True)
        self.ts_legloc = pn.widgets.Select(name="Legend at", options=["best"] + LOCS)
        self.ts_zero = _chk("Zero line", False)
        # ---- Style: text
        self.font = pn.widgets.Select(name="Font", options=FONTS)
        self.math = pn.widgets.Select(name="Math & units font", options=MATH_FONTS,
                                      description="Font of $...$ text, e.g. m s$^{-1}$")
        self.fsize = _f("Base size (pt)", 10.0, step=0.5, start=4)
        self.fs_tick = _auto("Tick labels (pt)")
        self.fs_label = _auto("Axis labels (pt)")
        self.fs_title = _auto("Panel titles (pt)")
        self.fs_sup = _auto("Figure title (pt)")
        self.fs_legend = _auto("Legends (pt)")
        # axes and ticks
        self.xlabel = pn.widgets.TextInput(name="x label")
        self.ylabel = pn.widgets.TextInput(name="y label")
        self.ticklabels = pn.widgets.Select(name="Tick labels on", options={
            "All panels": "all", "Outer panels": "outer", "No panels": "none"})
        self.tickdir = pn.widgets.Select(name="Ticks point", options=TICKDIR)
        self.ticks = pn.widgets.Checkbox(name="Tick marks")
        self.minor = pn.widgets.Checkbox(name="Minor ticks")
        self.xstep = _auto("x tick every", start=0)
        self.ystep = _auto("y tick every", start=0)
        self.frame_lw = _f("Frame width (pt)", 0.8, step=0.1, start=0.1)
        self.grid = pn.widgets.Checkbox(name="Grid lines")
        self.grid_ls = pn.widgets.Select(name="Grid style", options={
            "dotted": ":", "dashed": "--", "solid": "-"})
        self.equal = pn.widgets.Checkbox(name="Equal x/y scale")
        self.title_loc = pn.widgets.Select(name="Panel titles at", options={
            "Centre": "center", "Left": "left", "Right": "right"})
        self.title_bold = pn.widgets.Checkbox(name="Bold titles")
        # panel labels
        self.let_on = pn.widgets.Checkbox(name="Panel letters")
        self.let_fmt = pn.widgets.Select(name="Style", options=LETTERS)
        self.let_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.let_size = _f("Size (pt)", 12.0, step=1)
        self.let_bold = pn.widgets.Checkbox(name="Bold")
        self.let_box = pn.widgets.Checkbox(name="White box")
        self.tl_on = pn.widgets.Checkbox(name="Time label")
        self.tl_fmt = pn.widgets.TextInput(name="Text", description="{min}: minutes, {s}: "
                                           "seconds, {hms}: h:mm:ss; e.g. t = {min:g} min")
        self.tl_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.tl_size = _f("Size (pt)", 12.0, step=1)
        self.tl_bold = pn.widgets.Checkbox(name="Bold")
        self.tl_box = pn.widgets.Checkbox(name="White box")
        self.tl_t0 = _f("Minutes counted from", 0.0, step=10,
                        description="Time zero for {min}, in model minutes (e.g. the "
                                    "initiation time)")
        self.rl_on = pn.widgets.Checkbox(name="Run name (several runs)")
        self.rl_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.rl_size = _f("Size (pt)", 12.0, step=1)
        self.rl_bold = pn.widgets.Checkbox(name="Bold")
        self.rl_box = pn.widgets.Checkbox(name="White box")
        # colorbar
        self.cb_mode = pn.widgets.Select(name="Colorbars", options=CB_MODES)
        self.cb_loc = pn.widgets.Select(name="Where", options=CB_LOCS)
        self.cb_label = pn.widgets.TextInput(
            name="Label (blank: layer's)", placeholder="e.g. w (m s$^{-1}$)",
            description="Replaces every colorbar's label; $…$ is math, e.g. m s$^{-1}$")
        self.cb_lbold = pn.widgets.Checkbox(name="Bold label")
        self.cb_lside = pn.widgets.Select(name="Label side", options={
            "Auto": "", "Above / left": "first", "Below / right": "second"})
        self.cb_fmt = pn.widgets.TextInput(name="Tick format (blank: auto)", placeholder="%g",
                                           description="e.g. %.1f, %d, %.0e")
        self.cb_ticks = pn.widgets.TextInput(name="Ticks (blank: auto)", placeholder="0:60:10")
        self.cb_shrink = _f("Length (0–1)", 0.7, step=0.05, start=0.1, end=1.0)
        self.cb_fraction = _f("Thickness (0–1)", 0.05, step=0.01, start=0.01, end=0.5)
        self.cb_pad = _f("Gap (0–1)", 0.02, step=0.01, start=0.0, end=0.5)
        self.cb_lsize = _auto("Label size (pt)")
        self.cb_tsize = _auto("Tick size (pt)")
        # legend
        self.lg_loc = pn.widgets.Select(name="Layer legend at", options=LOCS)
        self.lg_panel = pn.widgets.IntInput(name="In panel", start=1, end=64)
        self.lg_ncol = pn.widgets.IntInput(name="Columns", start=1, end=8, value=1)
        self.lg_frame = pn.widgets.Checkbox(name="Frame")
        # spacing
        self.sp_w = _f("Between columns", 0.02, step=0.01, start=0.0,
                       description="Extra space between panels, as a fraction of a panel")
        self.sp_h = _f("Between rows", 0.02, step=0.01, start=0.0)
        self.sp_wpad = _f("Around panels, x (in)", 0.04, step=0.01, start=0.0,
                          description="Padding around each panel and its labels (inches)")
        self.sp_hpad = _f("Around panels, y (in)", 0.04, step=0.01, start=0.0)
        # ---- Annotate: contour key and annotations
        self.ck_on = _chk("Contour key (nested circles)", False)
        self.ck_layer = pn.widgets.Select(name="Of layer", options={"First contours": -1})
        self.ck_label = pn.widgets.TextInput(name="Name in the middle", value="w")
        self.ck_x = _f("x (figure 0–1)", 0.01, step=0.01)
        self.ck_y = _f("y (figure 0–1)", 0.01, step=0.01)
        self.ck_size = _f("Size (0–1)", 0.1, step=0.01)
        self.ck_fs = _f("Font (pt)", 10.0, step=1)
        self.ck_frame = _chk("Frame", True)
        self.ann_kind = pn.widgets.Select(name="Add", options=ANN_KINDS)
        self.ann_add = pn.widgets.Button(name="+ Add", button_type="primary",
                                         button_style="outline", height=32)
        self.ann_box = pn.Column(sizing_mode="stretch_width", margin=0)
        # ---- Export (the bar above the preview, and the Export tab)
        self._fig_dir = config.figures_dir(run.path)  # followed while the box is in it
        self.path = pn.widgets.TextInput(
            name="Save as (folder/name on the server, no extension)",
            value=os.path.join(self._fig_dir, "figure"), min_width=240)
        self.fmt = pn.widgets.Select(name="Format", options={
            "PNG": "png", "PDF": "pdf", "SVG": "svg", "EPS": "eps", "TIFF": "tiff"},
            width=90, description="PDF, SVG and EPS keep text and lines as vectors (fields "
                                  "are embedded as images at the DPI)")
        self.dpi = pn.widgets.IntInput(name="DPI", start=50, end=1200, step=50, width=80)
        self.save_img = pn.widgets.Button(name="Save", icon="device-floppy",
                                          button_type="primary", height=32, margin=(5, 3),
                                          description="Save the image")
        self.save_all = pn.widgets.Button(
            name="+ script & data", button_type="primary", button_style="outline",
            height=32, margin=(5, 3),
            description="Also writes <name>.py (redraws the figure without the viewer) and, "
                        "in _src/, <name>_data.npz and <name>_spec.json")
        self.dl = pn.widgets.FileDownload(callback=self._download, filename="figure.png",
                                          label="Download", icon="download",
                                          button_type="primary", button_style="outline",
                                          height=32, margin=(5, 3))
        self.tight = pn.widgets.Checkbox(name="Trim white space")
        self.pad = _f("Margin when trimmed (in)", 0.05, step=0.01, start=0.0)
        self.bg = pn.widgets.Select(name="Background", options={"White": "white",
                                                                "Transparent": "none"})
        self.spec_path = pn.widgets.TextInput(name="A saved figure (_spec.json)",
                                              placeholder="…/_src/figure_spec.json")
        self.load_btn = pn.widgets.Button(name="Open", button_type="light",
                                          button_style="outline", height=32)
        self.msg = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8))
        # ---- preview
        self.auto = pn.widgets.Checkbox(name="Live", value=True, margin=(12, 8, 0, 8))
        self.update = pn.widgets.Button(name="Redraw", icon="refresh", height=32,
                                        button_type="primary", button_style="outline",
                                        margin=(4, 4))
        self.zoom = pn.widgets.RadioButtonGroup(
            options={"Fit": "fit", "Actual size": "actual"}, value="fit", height=32,
            margin=(4, 4), description="Actual size: as large as the printed figure "
                                       "(at 96 pixels per inch) to judge the font sizes")
        self.status = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8))
        self.image = pn.pane.HTML(sizing_mode="stretch_width", margin=(4, 8))

        # ---- the tabs
        self.grid_sec = _section(
            "Grid and size", _grid(self.kind, self.vary, self.run_sel, self.runs_as),
            _grid(self.rows, self.cols, self.fit_btn),
            _grid(self.size_preset, self.width, self.height),
            _hint("The height follows the panels (grid, colorbar, titles) until you type "
                  "a size; <b>Fit height</b> makes it follow again."))
        self.times_sec = _section("Times", _grid(self.time1, self.tstep, self.tfill),
                                  self.tm_box, self.pf_box, self.pc_box)
        self.titles_sec = _section("Titles", self.suptitle, self.titles_box,
                                   _row(self.auto_titles, self.clear_titles))
        self.area_plan = pn.Column(_grid(self.dom, self.half, self.box_btn, self.coords),
                                   self.box_html, margin=0, sizing_mode="stretch_width")
        self.area_xs = pn.Column(_grid(self.xs_mode, self.xs_angle, self.xs_half, self.xs_offx,
                                       self.xs_offy, self.xs_top, self.xs_ab),
                                 self.xs_html, margin=0, sizing_mode="stretch_width")
        self.area_sec = _section("Area", self.area_plan, self.area_xs)
        self.ts_sec = _section("Time and value axes", _grid(
            self.ts_tmin, self.ts_tmax, self.ts_zero, self.ts_zmin, self.ts_zmax, self.ts_ymin,
            self.ts_ymax, self.ts_legend, self.ts_legloc),
            _hint("Blank: the range of the data. Minutes are counted from <b>Style → Panel "
                  "labels → Minutes counted from</b>."))
        self.runs_sec = _section(
            "Runs", _hint("Runs the panels can come from (e.g. tornadic vs non-tornadic). Each "
                          "run has its own storm track, for storm-centred panels and "
                          "storm-relative fields: the viewer's track for this run, or a track "
                          "file (storm_tracks/*.csv is found automatically)."),
            self.runs_box, self.add_sel, _grid((self.add_path, 2), self.add_btn),
            self.runs_msg, collapsed=True)
        panels_tab = pn.Column(self.grid_sec, self.times_sec, self.titles_sec, self.area_sec,
                               self.ts_sec, self.runs_sec, sizing_mode="stretch_width")
        layers_tab = pn.Column(self.plan_layers, self.series_col, self.snd_col,
                               sizing_mode="stretch_width")
        let = _grid(self.let_fmt, self.let_loc, self.let_size, self.let_bold, self.let_box)
        tl = _grid((self.tl_fmt, 2), self.tl_loc, self.tl_size, self.tl_bold, self.tl_box)
        rl = _grid(self.rl_loc, self.rl_size, self.rl_bold, self.rl_box)
        _when(self.let_on, let)
        _when(self.tl_on, tl)
        _when(self.rl_on, rl)
        _when(self.grid, self.grid_ls)
        self.ck_opts = _grid(self.ck_layer, self.ck_label, self.ck_frame, self.ck_x, self.ck_y,
                             self.ck_size, self.ck_fs)
        _when(self.ck_on, self.ck_opts)
        self.cb_opts = _grid(self.cb_loc, self.cb_shrink, self.cb_fraction, (self.cb_label, 2),
                             self.cb_lbold, self.cb_lside, self.cb_lsize, self.cb_pad,
                             self.cb_ticks, self.cb_fmt, self.cb_tsize)
        style_tab = pn.Column(
            _section("Text", _grid(self.font, self.math, self.fsize, self.fs_tick,
                                   self.fs_label, self.fs_title, self.fs_sup, self.fs_legend),
                     _hint("Blank sizes follow the base size.")),
            _section("Axes and ticks", _grid(
                self.xlabel, self.ylabel, self.ticklabels, self.xstep, self.ystep,
                self.tickdir, self.ticks, self.minor, self.frame_lw, self.grid, self.grid_ls,
                self.equal, self.title_loc, self.title_bold),
                _hint("Labels take matplotlib math, e.g. <code>w (m s$^{-1}$)</code>. Tick "
                      "labels on outer panels only when the panels share their ranges.")),
            _section("Panel labels", self.let_on, let, self.tl_on, tl,
                     _grid(self.tl_t0), self.rl_on, rl),
            _section("Colorbar", _grid(self.cb_mode), self.cb_opts),
            _section("Legend", _grid(self.lg_loc, self.lg_panel, self.lg_ncol, self.lg_frame),
                     _hint("The legend lists layers with a legend entry (contours, shading, "
                           "track, section line).")),
            _section("Spacing", _grid(self.sp_w, self.sp_h, self.sp_wpad, self.sp_hpad),
                     collapsed=True),
            sizing_mode="stretch_width")
        annotate_tab = pn.Column(
            _section("Annotations", _hint(
                "Text, markers, arrows, lines and shapes in one panel (number) or all (0), in "
                "axis units (km; minutes and km or values for series) or panel fractions."),
                _grid(self.ann_kind, self.ann_add), self.ann_box),
            _section("Contour key", _hint(
                "Nested circles labelled with a contour layer's levels (a key for unlabelled "
                "contours), placed in figure fractions from the lower left."),
                self.ck_on, self.ck_opts),
            sizing_mode="stretch_width")
        export_tab = pn.Column(
            _section("Image", _grid(self.tight, self.pad, self.bg),
                     _hint("Save, the format and the DPI are above the preview. Publishers "
                           "usually ask for 300–600 DPI, or PDF / EPS for line art.")),
            _section("Open a saved figure", _hint(
                "<b>+ script & data</b> also writes a Python script that redraws the figure "
                "without the viewer, and the figure's spec: open the spec here to keep "
                "editing."), _grid((self.spec_path, 2), self.load_btn)),
            sizing_mode="stretch_width")
        self.tabs = pn.Tabs(("Panels", panels_tab), ("Layers", layers_tab), ("Style", style_tab),
                            ("Annotate", annotate_tab), ("Export", export_tab),
                            dynamic=False, sizing_mode="stretch_width")
        self.editor = pn.Column(
            _hint("New figure from", margin=(6, 4, 0, 4)),
            _row(self.start_map, self.start_xs, self.start_ser, self.start_snd, self.start_def),
            self.tabs, scroll="y-auto", sizing_mode="stretch_height", width=580,
            styles={"border-left": f"1px solid {GRID}", "padding": "0 8px",
                    "overflow-x": "hidden"})
        self.path.styles = {"flex": "1 1 300px"}
        save_bar = pn.FlexBox(self.path, self.fmt, self.dpi, self.save_img, self.save_all,
                              self.dl, flex_wrap="wrap", align_items="flex-end", gap="0 2px",
                              sizing_mode="stretch_width")
        view_bar = pn.Row(self.update, self.auto, self.undo_btn, self.redo_btn, self.zoom,
                          self.status, margin=0, sizing_mode="stretch_width")
        self.preview = pn.Column(
            save_bar, self.msg, view_bar, self.image, scroll="y-auto",
            sizing_mode="stretch_both", styles={"min-width": "0"})
        self.panel = pn.Row(self.preview, self.editor, sizing_mode="stretch_both", margin=0)
        self._wire()

    def _wire(self):
        rq = lambda *e: self.request()  # noqa: E731
        for w in (self.kind, self.width, self.height, self.time1, self.suptitle,
                  self.half, self.coords, self.xs_mode, self.xs_angle,
                  self.xs_half, self.xs_offx, self.xs_offy, self.xs_top, self.font, self.math,
                  self.fsize, self.fs_tick, self.fs_label, self.fs_title, self.fs_sup,
                  self.fs_legend, self.xlabel, self.ylabel, self.ticklabels, self.tickdir,
                  self.ticks, self.minor, self.xstep, self.ystep, self.frame_lw, self.grid,
                  self.grid_ls, self.equal, self.title_loc, self.title_bold,
                  self.let_on, self.let_fmt, self.let_loc, self.let_size, self.let_bold,
                  self.let_box, self.tl_on, self.tl_fmt, self.tl_loc, self.tl_size,
                  self.tl_bold, self.tl_box, self.tl_t0, self.rl_on, self.rl_loc,
                  self.rl_size, self.rl_bold, self.rl_box, self.cb_mode, self.cb_loc,
                  self.cb_label, self.cb_ticks, self.cb_shrink, self.cb_fraction, self.cb_pad,
                  self.cb_lsize, self.cb_tsize, self.cb_lbold, self.cb_lside, self.cb_fmt,
                  self.lg_loc, self.lg_panel, self.lg_ncol,
                  self.lg_frame, self.sp_w, self.sp_h, self.sp_wpad, self.sp_hpad,
                  self.bg, self.tight, self.pad, self.run_sel):
            w.param.watch(rq, "value")
        self.cb_mode.param.watch(lambda e: self._show_cbar(), "value")
        for w in (self.rows, self.cols):
            w.param.watch(lambda e: self._on_layout(), "value")
        self.vary.param.watch(lambda e: self._on_vary(), "value")
        self.runs_as.param.watch(lambda e: self._on_vary(), "value")
        self.size_preset.param.watch(self._on_preset, "value")
        self.fit_btn.on_click(lambda e: self._refit())
        self.add_btn.on_click(lambda e: self._add_run())
        self.add_sel.param.watch(lambda e: setattr(self.add_path, "value", e.new or ""), "value")
        self.kind.param.watch(lambda e: self._on_kind(), "value")
        self.dom.param.watch(self._on_dom, "value")
        self.box_btn.on_click(lambda e: self._use_view())
        self.xs_ab.on_click(lambda e: self._use_ab())
        self.tfill.on_click(lambda e: self._fill_times())
        self.auto_titles.on_click(lambda e: self._auto_titles())
        self.clear_titles.on_click(lambda e: self._set_titles([]))
        for k, b in self.add_btns.items():
            b.on_click(partial(self._add_layer, k))
        self.start_map.on_click(lambda e: self.from_map())
        self.start_xs.on_click(lambda e: self.from_xsec())
        self.start_def.on_click(lambda e: self.set_spec(self._default()))
        self.start_ser.on_click(lambda e: self.from_series())
        for w in (self.width, self.height):
            w.param.watch(lambda e: self._size_by_hand(), "value")
        self.start_snd.on_click(lambda e: self.from_soundings())
        self.ser_add.on_click(lambda e: self._add_series_from_tab())
        self.ser_new.on_click(lambda e: self._add_series())
        self.snd_tab.on_click(lambda e: self._add_tab_soundings())
        self.snd_new.on_click(lambda e: self._add_sounding())
        self.ann_add.on_click(lambda e: self._add_annotation())
        for w in (*self.sk.values(), self.ts_tmin, self.ts_tmax, self.ts_zmin, self.ts_zmax,
                  self.ts_ymin, self.ts_ymax,
                  self.ts_legend, self.ts_legloc, self.ts_zero, self.ck_on, self.ck_layer,
                  self.ck_label, self.ck_x, self.ck_y, self.ck_size, self.ck_fs,
                  self.ck_frame):
            w.param.watch(rq, "value")
        self.update.on_click(lambda e: self.request(force=True, delay=False))
        self.undo_btn.on_click(lambda e: self.undo())
        self.redo_btn.on_click(lambda e: self.redo())
        self.zoom.param.watch(lambda e: self._show_image(), "value")
        self.save_img.on_click(lambda e: self._save(False))
        self.save_all.on_click(lambda e: self._save(True))
        self.load_btn.on_click(lambda e: self._load_spec())
        for w in (self.fmt, self.path):
            w.param.watch(lambda e: self._set_dl_name(), "value")
        self.fmt.param.watch(rq, "value")
        self.dpi.param.watch(rq, "value")

    # ------------------------------------------------------------ spec <-> widgets
    def set_spec(self, spec):
        """Show `spec` in the widgets (one re-render at the end)."""
        self.spec = spec = fg.normalize(spec, self.run, self._own_track())
        self.msg.object = ""
        self._auto_size = bool(spec.get("size_auto", False))  # until set by hand
        self._hold = True
        try:
            s = spec
            self._build_runs(s["runs"])
            self.kind.value, self.vary.value = s["kind"], s["vary"]
            self.run_sel.value = min(int(s.get("run", 0)), len(s["runs"]) - 1)
            self.runs_as.value = s.get("runs_as", "rows")
            self.rows.value, self.cols.value = int(s["rows"]), int(s["cols"])
            self.width.value, self.height.value = float(s["size"][0]), float(s["size"][1])
            self.size_preset.value = ""
            t1 = fg.tindex(self.run, s["time_s"])
            self.time1.value = t1 if t1 is not None else self.v.t
            self.suptitle.value = s.get("suptitle", "")
            d = s["domain"]
            self.dom.value, self.half.value = d["mode"], float(d.get("half", 12.5))
            self.coords.value = s.get("coords", "grid")
            x = s["xsec"]
            self.xs_mode.value, self.xs_angle.value = x["mode"], float(x["angle"])
            self.xs_half.value, self.xs_top.value = float(x["half"]), float(x["ztop"])
            self.xs_offx.value, self.xs_offy.value = (float(v) for v in x["offset"])
            a = s["axes"]
            self.xlabel.value, self.ylabel.value = a.get("xlabel", ""), a.get("ylabel", "")
            self.ticklabels.value = a.get("ticklabels", "all")
            self.ticks.value, self.minor.value = a.get("ticks", True), a.get("minor", False)
            self.equal.value = a.get("equal", True)
            self.tickdir.value = a.get("tickdir", "out") if a.get("tickdir") in TICKDIR.values() \
                else "out"
            self.xstep.value, self.ystep.value = _num(a.get("xstep")), _num(a.get("ystep"))
            self.frame_lw.value = float(a.get("frame_lw") or 0.8)
            self.grid.value = bool(a.get("grid", False))
            self.grid_ls.value = a.get("grid_ls", ":")
            self.title_loc.value = a.get("title_loc", "center")
            self.title_bold.value = a.get("title_bold", True)
            f = s.get("font", {})
            self.font.value = f.get("family", "sans-serif") if f.get("family") in FONTS \
                else "sans-serif"
            self.math.value = f.get("math", "dejavusans") \
                if f.get("math") in MATH_FONTS.values() else "dejavusans"
            self.fsize.value = float(f.get("size", 10))
            for w, k in ((self.fs_tick, "tick"), (self.fs_label, "label"),
                         (self.fs_title, "title"), (self.fs_sup, "suptitle"),
                         (self.fs_legend, "legend")):
                w.value = _num(f.get(k)) or None
            L = s["letters"]
            self.let_on.value, self.let_loc.value = L.get("on", True), L.get("loc", "upper left")
            self.let_fmt.value = L.get("fmt", "{a}") if L.get("fmt") in LETTERS.values() \
                else "{a}"
            self.let_size.value, self.let_bold.value = float(L.get("size", 12)), \
                L.get("bold", True)
            self.let_box.value = bool(L.get("box", False))
            T = s["time_label"]
            self.tl_on.value, self.tl_fmt.value = T.get("on", True), T.get("fmt", "")
            self.tl_loc.value, self.tl_size.value = T.get("loc", "lower right"), \
                float(T.get("size", 12))
            self.tl_bold.value, self.tl_t0.value = T.get("bold", True), float(T.get("t0_min", 0))
            self.tl_box.value = bool(T.get("box", False))
            R = s.get("run_label", {})
            self.rl_on.value, self.rl_loc.value = R.get("on", True), R.get("loc", "upper left")
            self.rl_size.value, self.rl_bold.value = float(R.get("size", 12)), R.get("bold", True)
            self.rl_box.value = bool(R.get("box", False))
            c = s["colorbar"]
            self.cb_mode.value = c.get("mode", "shared")
            self.cb_loc.value = c.get("location") or (
                "bottom" if c.get("orientation", "horizontal" if c.get("mode", "shared")
                                  == "shared" else "vertical") == "horizontal" else "right")
            self.cb_label.value, self.cb_shrink.value = c.get("label", ""), \
                float(c.get("shrink", 0.7))
            self.cb_ticks.value = c.get("ticks", "")
            self.cb_fraction.value = float(c.get("fraction", 0.05))
            self.cb_pad.value = float(c.get("pad", 0.02))
            self.cb_lsize.value = _num(c.get("label_size")) or None
            self.cb_tsize.value = _num(c.get("tick_size")) or None
            self.cb_lbold.value = bool(c.get("label_bold", False))
            self.cb_lside.value = c.get("label_side", "")
            self.cb_fmt.value = c.get("tick_fmt", "")
            lg = s.get("legend", {})
            self.lg_loc.value, self.lg_panel.value = lg.get("loc", "upper right"), \
                int(lg.get("panel", 0)) + 1
            self.lg_ncol.value = int(lg.get("ncol", 1) or 1)
            self.lg_frame.value = lg.get("frame", True)
            sp = s.get("spacing", {})
            self.sp_w.value, self.sp_h.value = float(sp.get("wspace", 0.02)), \
                float(sp.get("hspace", 0.02))
            self.sp_wpad.value, self.sp_hpad.value = float(sp.get("w_pad", 0.04)), \
                float(sp.get("h_pad", 0.04))
            e = s.get("export", {})
            self.fmt.value, self.dpi.value = e.get("format", "png"), int(e.get("dpi", 250))
            self.tight.value = e.get("tight", True)
            self.pad.value = float(e.get("pad", 0.05))
            self.bg.value = s.get("background", "white")
            ts = s.get("ts", {})
            self.ts_tmin.value = "" if ts.get("tmin") in (None, "") else f"{float(ts['tmin']):g}"
            self.ts_tmax.value = "" if ts.get("tmax") in (None, "") else f"{float(ts['tmax']):g}"
            self.ts_zmin.value = float(ts.get("zmin") or 0.0)
            self.ts_zmax.value = float(ts.get("zmax") or 10.0)
            self.ts_legend.value, self.ts_zero.value = ts.get("legend", True), \
                ts.get("zero_line", False)
            self.ts_legloc.value = ts.get("legend_loc", "best")
            self.ts_ymin.value, self.ts_ymax.value = _num(ts.get("ymin")), _num(ts.get("ymax"))
            sk = s.get("skewt", {})
            for k, wdg in self.sk.items():
                if k in sk:
                    wdg.value = sk[k] if not isinstance(wdg, pn.widgets.FloatInput) \
                        else float(sk[k])
            ck = s.get("contour_key", {})
            self.ck_on.value, self.ck_label.value = ck.get("on", False), ck.get("label", "w")
            self.ck_x.value, self.ck_y.value = float(ck.get("x", 0.01)), float(ck.get("y", 0.01))
            self.ck_size.value, self.ck_fs.value = float(ck.get("size", 0.1)), \
                float(ck.get("fs", 10.0))
            self.ck_frame.value = ck.get("frame", True)
            self._build_cards(s["layers"])
            self.ck_layer.value = int(ck.get("layer", -1)) \
                if int(ck.get("layer", -1)) in self.ck_layer.options.values() else -1
            self._build_times([NONE if t is None else fg.tindex(self.run, t)
                               for t in s["times_s"]], extend=False)
            self._build_pf(s.get("panel_fills", []))
            self._build_pc(s.get("panels", []))
            self._build_titles(s.get("titles", []))
            self.ser_cards = [self._ser_card(e) for e in s.get("series", [])]
            self.snd_cards = [self._snd_card(e) for e in s.get("soundings", [])]
            self.ann_rows = [self._ann_row(a) for a in s.get("annotations", [])]
            self._show_series()
            self._show_soundings()
            self._show_anns()
        finally:
            self._hold = False
        self._show_region()
        self._on_kind(render_=False)
        self._show_vary()
        self._show_cbar()
        self._set_dl_name()
        self.request(delay=False)

    def collect(self):
        """The spec of the current widget values."""
        s = dict(self.spec)
        tv = self._time_values()
        while tv and tv[-1] == NONE:
            tv.pop()
        times = [None if t == NONE else int(t) for t in tv]
        titles = [w.value for w in self.title_ws]
        while titles and not titles[-1].strip():
            titles.pop()
        s.update(
            kind=self.kind.value, vary=self.vary.value, rows=int(self.rows.value or 1),
            cols=int(self.cols.value or 1),
            size=[float(self.width.value or 8), float(self.height.value or 6)],
            size_auto=bool(self._auto_size),
            times=times, time=int(self.time1.value),
            times_s=[None if t is None else float(self.run.times[t]) for t in times],
            time_s=float(self.run.times[int(self.time1.value)]),
            runs=self._runs_collect(), run=int(self.run_sel.value or 0),
            runs_as=self.runs_as.value,
            panels=[dict(run=int(r["run"].value), time_s=float(r["time"].value))
                    for r in self.pc_rows if r["time"].value is not None],
            layers=[c.collect() for c in self.cards],
            panel_fills=[self._pf_collect(r) for r in self.pf_rows],
            suptitle=self.suptitle.value, titles=titles,
            coords=self.coords.value, background=self.bg.value)
        s["domain"] = dict(s["domain"], mode=self.dom.value, half=float(self.half.value or 12.5))
        s["xsec"] = dict(s["xsec"], mode=self.xs_mode.value,
                         angle=float(self.xs_angle.value or 0.0),
                         half=float(self.xs_half.value or 10.0),
                         offset=[float(self.xs_offx.value or 0.0),
                                 float(self.xs_offy.value or 0.0)],
                         ztop=float(self.xs_top.value or 6.0))
        s["axes"] = dict(s["axes"], xlabel=self.xlabel.value, ylabel=self.ylabel.value,
                         ticklabels=self.ticklabels.value, ticks=self.ticks.value,
                         minor=self.minor.value, equal=self.equal.value,
                         tickdir=self.tickdir.value, xstep=_num(self.xstep.value),
                         ystep=_num(self.ystep.value),
                         frame_lw=float(self.frame_lw.value or 0.8), grid=self.grid.value,
                         grid_ls=self.grid_ls.value, title_loc=self.title_loc.value,
                         title_bold=self.title_bold.value)
        s["font"] = dict(family=self.font.value, size=float(self.fsize.value or 10),
                         math=self.math.value, tick=_num(self.fs_tick.value),
                         label=_num(self.fs_label.value), title=_num(self.fs_title.value),
                         suptitle=_num(self.fs_sup.value), legend=_num(self.fs_legend.value))
        s["letters"] = dict(on=self.let_on.value, fmt=self.let_fmt.value, loc=self.let_loc.value,
                            size=float(self.let_size.value or 12), bold=self.let_bold.value,
                            box=self.let_box.value)
        s["time_label"] = dict(on=self.tl_on.value, fmt=self.tl_fmt.value or "t = {min:g} min",
                               loc=self.tl_loc.value, size=float(self.tl_size.value or 12),
                               bold=self.tl_bold.value, box=self.tl_box.value,
                               t0_min=float(self.tl_t0.value or 0))
        s["run_label"] = dict(on=self.rl_on.value, loc=self.rl_loc.value,
                              size=float(self.rl_size.value or 12), bold=self.rl_bold.value,
                              box=self.rl_box.value)
        loc = self.cb_loc.value
        s["colorbar"] = dict(s["colorbar"], mode=self.cb_mode.value, location=loc,
                             orientation="horizontal" if loc in ("bottom", "top") else "vertical",
                             label=self.cb_label.value,
                             shrink=float(self.cb_shrink.value or 0.7), ticks=self.cb_ticks.value,
                             fraction=float(self.cb_fraction.value or 0.05),
                             pad=float(self.cb_pad.value or 0.0),
                             label_size=_num(self.cb_lsize.value),
                             tick_size=_num(self.cb_tsize.value),
                             label_bold=self.cb_lbold.value, label_side=self.cb_lside.value,
                             tick_fmt=self.cb_fmt.value.strip())
        s["legend"] = dict(s.get("legend", {}), loc=self.lg_loc.value,
                           panel=max(0, int(self.lg_panel.value or 1) - 1),
                           ncol=int(self.lg_ncol.value or 1), frame=self.lg_frame.value)
        s["spacing"] = dict(wspace=float(self.sp_w.value or 0.0),
                            hspace=float(self.sp_h.value or 0.0),
                            w_pad=float(self.sp_wpad.value or 0.0),
                            h_pad=float(self.sp_hpad.value or 0.0))
        s["export"] = dict(format=self.fmt.value, dpi=int(self.dpi.value or 250),
                           tight=self.tight.value, pad=float(self.pad.value or 0.0))

        def minutes(w):
            try:
                return float(w.value) if str(w.value).strip() else None
            except ValueError:
                return None

        s["series"] = [c.collect() for c in self.ser_cards]
        s["soundings"] = [c.collect() for c in self.snd_cards]
        s["annotations"] = [r.collect() for r in self.ann_rows]
        s["ts"] = dict(s.get("ts", {}), tmin=minutes(self.ts_tmin), tmax=minutes(self.ts_tmax),
                       zmin=float(self.ts_zmin.value or 0.0),
                       zmax=float(self.ts_zmax.value or 10.0), legend=self.ts_legend.value,
                       legend_loc=self.ts_legloc.value, zero_line=self.ts_zero.value,
                       ymin=_num(self.ts_ymin.value), ymax=_num(self.ts_ymax.value))
        s["skewt"] = dict(s.get("skewt", {}), **{
            k: (float(w.value or 0.0) if isinstance(w, pn.widgets.FloatInput) else w.value)
            for k, w in self.sk.items()})
        s["contour_key"] = dict(s.get("contour_key", {}), on=self.ck_on.value,
                                layer=int(self.ck_layer.value), label=self.ck_label.value,
                                x=float(self.ck_x.value or 0.0), y=float(self.ck_y.value or 0.0),
                                size=float(self.ck_size.value or 0.1),
                                fs=float(self.ck_fs.value or 10.0), frame=self.ck_frame.value)
        self.spec = s
        return s

    # ------------------------------------------------------------ undo / redo
    def _remember(self, spec):
        """Record a rendered spec: the one before it goes on the undo list."""
        j = json.dumps(spec, sort_keys=True, default=float)
        if self._restoring or self._last is None:
            self._restoring = False
        elif j != self._last:
            self._hist = (self._hist + [self._last])[-50:]
            self._future = []
        self._last = j
        self._show_history()

    def _show_history(self):
        self.undo_btn.disabled = not self._hist
        self.redo_btn.disabled = not self._future

    def undo(self):
        if not self._hist:
            return
        self._future.append(self._last)
        self._restore(self._hist.pop())

    def redo(self):
        if not self._future:
            return
        self._hist.append(self._last)
        self._restore(self._future.pop())

    def _restore(self, j):
        self._last, self._restoring = j, True
        self.set_spec(json.loads(j))
        if not self.auto.value:  # (no render to record it)
            self._remember(self.collect())

    # ------------------------------------------------------------ layers
    def _build_cards(self, layers):
        # a long list starts folded: the first layer open, the rest by their titles
        self.cards = [self._card(lay, collapsed=len(layers) > 2 and j > 0)
                      for j, lay in enumerate(layers)]
        self._show_cards()

    def _card(self, lay, collapsed=False):
        c = LayerCard(self, lay, collapsed)
        c.up.on_click(lambda e: self._move(c, -1))
        c.down.on_click(lambda e: self._move(c, 1))
        c.rm.on_click(lambda e: self._remove(c))
        return c

    def _show_cards(self):
        self.layer_box.objects = [c.panel for c in self.cards] or [pn.pane.HTML(
            '<div class="cv-empty">No layers: add one above.</div>')]
        self._show_region()
        opts = {"First contours": -1} | {
            f"{j + 1}. {self.F[c.w['field'].value].label}": j
            for j, c in enumerate(self.cards) if c.type == "contour"}
        v = self.ck_layer.value
        hold, self._hold = self._hold, True
        try:
            self.ck_layer.options = opts
            self.ck_layer.value = v if v in opts.values() else -1
        finally:
            self._hold = hold

    def _add_layer(self, kind, ev=None):
        F = self.F
        field = None
        if kind in ("fill", "contour", "shade"):
            field = {"fill": "dbz", "contour": "winterp", "shade": "winterp"}[kind]
            if field not in F:
                field = next(iter(F.defs))
        lay = fg.layer_defaults(kind, F, field, 1.0)
        if kind == "vectors" and self.kind.value == "xsec":
            lay.update(spacing=0.75, scale=400.0, width=0.0015)
        self.cards.append(self._card(lay))
        self._show_cards()
        self.request()

    def _move(self, c, d):
        i = self.cards.index(c)
        j = min(max(i + d, 0), len(self.cards) - 1)
        self.cards[i], self.cards[j] = self.cards[j], self.cards[i]
        self._show_cards()
        self.request()

    def _remove(self, c):
        self.cards.remove(c)
        self._show_cards()
        self.request()

    # ------------------------------------------------------------ panels: own run & time
    def _time_opts(self, k):
        try:
            run, _ = self.open_run(self.run_rows[k]["path"])
        except Exception:  # noqa: BLE001
            return {}
        return {f"{run.time_label(t)}  ({run.times[t] / 60:g} min)": float(run.times[t])
                for t in range(len(run.times))}

    def _build_pc(self, panels):
        n = int(self.rows.value or 1) * int(self.cols.value or 1)
        rows = []
        for i in range(n if self.vary.value == "custom" else 0):
            if i < len(panels):
                p = panels[i]
            elif self.pc_rows and i < len(self.pc_rows):
                p = dict(run=self.pc_rows[i]["run"].value, time_s=self.pc_rows[i]["time"].value)
            else:  # new panels: the runs in turn, at the shown time
                p = dict(run=i % max(1, len(self.run_rows)),
                         time_s=float(self.run.times[self.v.t]))
            rows.append(self._pc_row(i, p))
        self.pc_rows = rows
        self.pc_box.objects = [r["panel"] for r in rows]

    def _pc_row(self, i, p):
        names = self._run_names()
        k = int(p["run"]) if int(p["run"]) in names.values() else 0
        r = dict(run=pn.widgets.Select(name=f"Panel {figdraw.panel_letter(i, '{a}')}: run",
                                       options=names, value=k))
        opts = self._time_opts(k)
        ts = p.get("time_s")
        r["time"] = pn.widgets.Select(name="time", options=opts, value=self._nearest(opts, ts))

        def on_run(ev):
            if self._hold:
                return
            o = self._time_opts(ev.new)
            cur = r["time"].value
            self._hold = True
            try:
                r["time"].options = o
                r["time"].value = self._nearest(o, cur)
            finally:
                self._hold = False
            self.request()

        r["run"].param.watch(on_run, "value")
        r["time"].param.watch(lambda e: self.request(), "value")
        r["panel"] = _grid(r["run"], r["time"], n=2)
        return r

    @staticmethod
    def _nearest(opts, ts):
        vals = list(opts.values())
        if not vals:
            return None
        if ts is None:
            return vals[0]
        return min(vals, key=lambda v: abs(v - float(ts)))

    # ------------------------------------------------------------ panel times and titles
    def _slots(self):
        """How many times to choose: one per panel (panels in time), one per column
        (row) of a run x time grid, else none."""
        if self.kind.value not in ("plan", "xsec"):
            return 0
        r, c = int(self.rows.value or 1), int(self.cols.value or 1)
        if self.vary.value == "time":
            return r * c
        if self.vary.value == "grid":
            return c if self.runs_as.value == "rows" else r
        return 0

    def _time_values(self):
        """Output index of each time picker (NONE: an empty panel)."""
        return [w.value for w in self.tm_rows]

    def _build_times(self, values=None, extend=True):
        """A time picker per panel (per column / row of a run x time grid), keeping the
        chosen times.  Pickers added to a grid continue every `tstep` outputs (extend),
        or start empty."""
        vals = list(self._time_values() if values is None else values)
        nt, step = len(self.run.times), int(self.tstep.value or 1)
        n = self._slots()
        while len(vals) < n:
            last = next((v for v in reversed(vals) if v not in (None, NONE)), None)
            nxt = (self.v.t if last is None else last + step) if extend else NONE
            vals.append(nxt if nxt is not None and 0 <= nxt < nt else NONE)
        opts = {"— empty —": NONE} | self.topts
        grid = self.vary.value == "grid"
        rows = []
        for i in range(n):
            name = (f"{'Column' if self.runs_as.value == 'rows' else 'Row'} {i + 1}" if grid
                    else f"Panel {figdraw.panel_letter(i, '{a}')}")
            v = vals[i] if vals[i] in opts.values() else NONE
            w = pn.widgets.Select(name=name, options=opts, value=v)
            w.param.watch(lambda e: self.request(), "value")
            rows.append(w)
        self.tm_rows = rows
        self.tm_box.objects = [_grid(*rows)] if rows else []

    def _fill_times(self):
        """The time pickers from the shown time, every `tstep` outputs."""
        step, t0, nt = int(self.tstep.value or 1), self.v.t, len(self.run.times)
        hold, self._hold = self._hold, True
        try:
            for k, w in enumerate(self.tm_rows):
                t = t0 + step * k
                w.value = t if t < nt else NONE
        finally:
            self._hold = hold
        self.request()

    def _build_titles(self, titles=None):
        """A title box per grid cell, keeping what is typed."""
        vals = [w.value for w in self.title_ws] if titles is None else list(titles)
        n = int(self.rows.value or 1) * int(self.cols.value or 1)
        ws = []
        for i in range(n):
            w = pn.widgets.TextInput(name=f"Panel {figdraw.panel_letter(i, '{a}')}",
                                     value=vals[i] if i < len(vals) else "",
                                     placeholder="no title")
            w.param.watch(lambda e: self.request(), "value")
            ws.append(w)
        self.title_ws = ws
        self.titles_box.objects = [_grid(*ws)] if ws else []

    def _set_titles(self, titles):
        hold, self._hold = self._hold, True
        try:
            for i, w in enumerate(self.title_ws):
                w.value = titles[i] if i < len(titles) else ""
        finally:
            self._hold = hold
        self.request()

    # ------------------------------------------------------------ panel fields
    def _build_pf(self, fills):
        n = int(self.rows.value or 1) * int(self.cols.value or 1)
        base = next((c.collect() for c in self.cards if c.type == "fill"), None)
        rows = []
        for i in range(n if self.vary.value == "field" else 0):
            pf = fills[i] if i < len(fills) else None
            if pf is None:
                pf = {k: base[k] for k in ("field", "cmap", "vmin", "vmax")} if base else \
                    {k: v for k, v in fg.layer_defaults("fill", self.F, next(iter(self.F.defs)))
                     .items() if k in ("field", "cmap", "vmin", "vmax")}
            rows.append(self._pf_row(i, pf))
        self.pf_rows = rows
        head = [_hint("The fill of each panel (it replaces the first fill layer's field, "
                      "colours and range):")] if rows else []
        self.pf_box.objects = head + [r["panel"] for r in rows]

    def _pf_row(self, i, pf):
        F = self.F
        r = dict(
            field=pn.widgets.Select(name=f"Panel {figdraw.panel_letter(i, '{a}')}: field",
                                    groups=F.groups(), value=pf["field"]),
            cmap=pn.widgets.Select(name="Colormap", options=FIG_CMAPS,
                                   value=pf["cmap"] if pf["cmap"] in FIG_CMAPS else "viridis"),
            vmin=_f("Min", float(pf["vmin"])), vmax=_f("Max", float(pf["vmax"])))

        def on_field(ev):
            d = fg.layer_defaults("fill", F, ev.new)
            self._hold = True
            try:
                r["cmap"].value = d["cmap"] if d["cmap"] in FIG_CMAPS else "viridis"
                r["vmin"].value, r["vmax"].value = d["vmin"], d["vmax"]
            finally:
                self._hold = False
            self.request()

        r["field"].param.watch(on_field, "value")
        for k in ("cmap", "vmin", "vmax"):
            r[k].param.watch(lambda e: self.request(), "value")
        r["panel"] = _grid((r["field"], 2), r["cmap"], r["vmin"], r["vmax"], n=5)
        return r

    def _pf_collect(self, r):
        # the panel's own field defaults (blanking, colorbar ends) override the shared
        # fill layer's (e.g. reflectivity's "blank where <= 0")
        d = fg.layer_defaults("fill", self.F, r["field"].value)
        return dict(field=r["field"].value, cmap=r["cmap"].value, vmin=float(r["vmin"].value),
                    vmax=float(r["vmax"].value), units=d["units"],
                    mask_below=d["mask_below"], extend=d["extend"], white_first=False,
                    reverse=False)

    # ------------------------------------------------------------ events
    def _on_layout(self):
        if self._hold:
            return
        field = self.vary.value == "field"
        self._show_vary()
        self._build_times()
        self._build_pf([self._pf_collect(r) for r in self.pf_rows])
        self._build_pc([])
        self._build_titles()
        if field and self.cb_mode.value == "shared":
            self.cb_mode.value = "each"
        self._fit_size()
        self.request()

    def _on_vary(self):
        """New panel arrangement: a run x time grid gets one row (or column) per run
        and one column (row) per chosen time."""
        if self._hold:
            return
        if self.kind.value == "th":
            self._th_grid()
            self._on_layout()
            return
        if self.vary.value == "grid":
            chosen = [t for t in self._time_values() if t != NONE]
            nr, nt = len(self.run_rows), max(1, len(chosen))
            if nt == 1 and self.cols.value * self.rows.value > 1:
                nt = int(self.cols.value if self.runs_as.value == "rows" else self.rows.value)
            self._hold = True
            try:
                self.rows.value, self.cols.value = (nr, nt) if self.runs_as.value == "rows" \
                    else (nt, nr)
            finally:
                self._hold = False
            self._show_vary()
            self._build_times(chosen)
        self._on_layout()

    def _show_vary(self):
        vary, kind = self.vary.value, self.kind.value
        maps = kind in ("plan", "xsec")
        self.vary.visible = maps
        self.times_sec.visible = maps
        self.times_sec.title = {
            "time": "Times (one per panel)", "field": "Time and fields",
            "grid": "Times (one per " + ("column)" if self.runs_as.value == "rows" else "row)"),
            "custom": "Run and time of each panel"}.get(vary, "Times")
        self.tm_box.visible = self.tstep.visible = self.tfill.visible = \
            vary in ("time", "grid")
        self.time1.visible = vary == "field"
        self.pf_box.visible = vary == "field"
        self.pc_box.visible = vary == "custom"
        self.runs_as.visible = (vary == "grid" and maps) or kind == "th"
        self.run_sel.visible = len(self.run_rows) > 1 and vary in ("time", "field") and maps
        self.plan_layers.visible = self.area_sec.visible = maps
        self.series_col.visible = self.ts_sec.visible = kind in ("th", "line")
        self.ts_sec.title = "Time and height axes" if kind == "th" else "Time and value axes"
        self.ts_zmin.visible = self.ts_zmax.visible = kind == "th"
        for w in (self.ts_ymin, self.ts_ymax, self.ts_zero, self.ts_legend, self.ts_legloc):
            w.visible = kind == "line"
        self.snd_col.visible = kind == "sounding"
        self.equal.visible = kind == "plan"
        for k in ("track", "line"):  # plan views only
            self.add_btns[k].visible = kind == "plan"
        for c in self.cards:
            c.show(kind)
            c._set_title()
        self._show_region()

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
        return {"xsec": 0.5, "th": 0.55, "line": 0.45, "sounding": 1.0}.get(s["kind"], 0.75)

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
                else:
                    self.xlabel.value, self.ylabel.value = "temperature (°C)", "pressure (hPa)"
                    self.cb_mode.value = "none"
            finally:
                self._hold = False
            if kind in ("th", "line") and not self.ser_cards:
                ss = getattr(self.v, "series", {}) or {}
                keys = [k for k in ss if ("profile" in ss[k]["ds"]) == (kind == "th")]
                for k in keys[:3]:
                    self.ser_cards.append(self._ser_card(self._tab_series(k)))
                if not self.ser_cards:
                    self.ser_cards.append(self._ser_card(fg.series_defaults(
                        self.F, self._new_recipe())))
            if kind == "sounding" and not self.snd_cards:
                self.snd_cards = [self._snd_card(e) for e in self.tab_soundings()]
                if not self.snd_cards:
                    self._add_sounding()
            self._show_series()
            self._show_soundings()
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

    def _on_dom(self, ev):
        if ev.new == "box" and not self.spec["domain"].get("box"):
            self._use_view()
            return
        self._show_region()
        self.request()

    def _use_view(self):
        self.spec["domain"] = dict(self.spec["domain"], box=[float(v) for v in self.v.view])
        if self.dom.value != "box":
            self.dom.value = "box"  # (re-renders)
        self._show_region()
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
        b = self.spec["domain"].get("box")
        self.half.visible = self.dom.value == "storm"
        self.box_btn.visible = self.dom.value == "box"
        self.box_html.object = ('<div class="cv-hint">Box x {:.1f} – {:.1f}, y {:.1f} – {:.1f} '
                                'km</div>'.format(*b) if b and self.dom.value == "box" else "")
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
        if s["kind"] in ("line", "sounding"):
            ents = s["series" if s["kind"] == "line" else "soundings"]
            ts = []
            for i in range(fg.npanels(s)):
                labs = [e.get("label", "") for e in ents if int(e.get("panel", 0)) == i]
                ts.append(" / ".join(dict.fromkeys(x for x in labs if x)) if s["kind"] == "line"
                          else "")
            self._set_titles(ts)
            return
        if s["vary"] == "field":
            ts = [self.F[pf["field"]].label for pf in s["panel_fills"]]
        elif s["vary"] in ("grid", "custom"):
            ts = []
            for i in range(fg.npanels(s)):
                ref = fg.panel_ref(s, i)
                ts.append(s["runs"][ref[0]]["label"] if ref else "")
            self.rl_on.value = False  # the titles name the runs now
        else:
            fill = next((lay for lay in s["layers"] if lay["type"] == "fill"), None)
            ts = [self.F[fill["field"]].label if fill and t is not None else ""
                  for t in s["times"]]
        self._set_titles(ts)

    _auto_size = False  # the figure size follows the grid until it is set by hand

    # ------------------------------------------------------------ rendering
    def request(self, force=False, delay=True):
        """Re-render the preview (shortly: several quick changes give one render)."""
        if self._hold or not (force or self.auto.value):
            return
        self._req += 1
        n = self._req
        doc = self.v.doc
        if delay and doc is not None:
            doc.add_timeout_callback(partial(self._fire, n), 400)
        else:
            self._fire(n)

    def _fire(self, n):
        if n != self._req:
            return
        try:
            self._follow_size()
            spec = self.collect()
        except Exception as e:  # noqa: BLE001
            self._status(f"Incomplete settings: {e}", True)
            return
        self._remember(spec)
        self.v.gen["fig"] += 1
        g = self.v.gen["fig"]
        self._status('<span class="busy">● Rendering…</span>')
        self.v.pools["fig"].submit(self._job, g, spec)

    def panel_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of the spec, from the cache where possible."""
        if spec["kind"] in ("th", "line"):
            return self._series_data(spec)
        if spec["kind"] == "sounding":
            return self._sounding_data(spec, progress, cancelled)
        ctx = {}  # run index -> (run, Fields, fixes, centres, track signature)

        def context(k):
            if k not in ctx:
                e = spec["runs"][k]
                run, F = self.open_run(e["path"])
                fx = self.run_fixes(e, run)
                sig = json.dumps(sorted((t, round(f["x"], 4), round(f["y"], 4))
                                        for t, f in fx.items()))
                ctx[k] = (run, F, fx, ser.track_centers(fx, len(run.times)), sig)
            return ctx[k]

        multi = len(spec["runs"]) > 1
        data = {}
        n = fg.npanels(spec)
        for i in range(n):
            if cancelled and cancelled():
                return None
            ref = fg.panel_ref(spec, i)
            if ref is None:
                continue  # an empty cell of a run x time grid
            k, ts = ref
            entry = spec["runs"][k]
            try:
                run, F, fx, centers, sig = context(k)
            except Exception as e:  # noqa: BLE001
                data[i] = dict(time_s=ts, missing=f"could not open {entry['path']}: {e}")
                continue
            t = fg.tindex(run, ts)
            c = centers.get(t) if t is not None else None
            key = fg.data_key(spec, i, c, run.path)
            if any(lay["type"] == "track" for lay in spec["layers"]):
                key += sig
            d = self.cache.get(key)
            if d is None:
                if progress:
                    progress(i, n)
                storm = fg.storm_motion(run, fx, t) if t is not None else None
                d = fg.extract(run, F, spec, i, c, fx, storm)
                self.cache[key] = d
                while len(self.cache) > 60:
                    self.cache.popitem(last=False)
            else:
                self.cache.move_to_end(key)
            data[i] = dict(d, run_label=entry.get("label", "")) if multi else d
        return data

    def _job(self, g, spec):
        t0 = _time.time()

        def cancelled():
            return g != self.v.gen["fig"]

        def progress(i, n):
            what = "sounding" if spec["kind"] == "sounding" else "panel"
            self.v._schedule(partial(self._status, f'<span class="busy">● Reading {what} '
                                                   f'{i + 1}/{n}…</span>'))

        try:
            data = self.panel_data(spec, progress, cancelled)
            if data is None:
                return
            self._lims = {i: (d["xlim"], d["ylim"]) for i, d in data.items()
                          if "xlim" in d and "ylim" in d and not d.get("missing")}
            fig = figdraw.draw(spec, data)
            # sharp at the page's size, and on screen at 96 px per inch when actual size
            dpi = min(float(spec["export"]["dpi"]), max(1100.0 / max(spec["size"][0], 0.5),
                                                         192.0))
            buf = io.BytesIO()
            figdraw.save(spec, fig, buf, format="png", **fg.save_kw(spec, dpi))
            raw = buf.getvalue()
            wh = struct.unpack(">II", raw[16:24])  # the PNG header's width and height
            png = base64.b64encode(raw).decode()
            miss = [i for i, d in data.items() if d.get("missing")]
            w_in, h_in = wh[0] / dpi, wh[1] / dpi  # as saved (after trimming)
            note = (f"{len(data)} panel{'s' if len(data) != 1 else ''} · "
                    f"{w_in:.2f} × {h_in:.2f} in as saved "
                    f"({w_in * float(spec['export']['dpi']):.0f} × "
                    f"{h_in * float(spec['export']['dpi']):.0f} px at "
                    f"{spec['export']['dpi']} dpi) · {_time.time() - t0:.1f} s")
            pend = self.series_pending() if spec["kind"] in ("th", "line") else []
            if pend:
                note += (' · <span class="busy">● computing series '
                         + "; ".join(p for p in pend if p) + "</span>")
            if miss:
                note += (f" · no data in panel{'s' if len(miss) > 1 else ''} "
                         + ", ".join(figdraw.panel_letter(i, "{a}") for i in miss))
                storm = (spec["kind"] == "plan" and spec["domain"]["mode"] == "storm") or \
                    (spec["kind"] == "xsec" and spec["xsec"]["mode"] == "storm")
                if storm and any(not e.get("track") for e in spec["runs"]):
                    note += (" · storm-centred panels need a track for each run (see "
                             "<b>Runs</b>)")
                elif storm and not self.v.fixes and any(e.get("track") == "viewer"
                                                        for e in spec["runs"]):
                    note += (" · storm-centred panels need a track: follow the storm in "
                             "the <b>Track</b> tab (Map), or pick another area in "
                             "<b>Region</b>")
            self.v._schedule(partial(self._apply, g, png, note, (wh, dpi,
                                                                 spec.get("background"))))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.v._schedule(partial(self._status, f"Could not draw: {e}", True))

    def _apply(self, g, png, note, info=None):
        if g != self.v.gen["fig"]:
            return
        self._png = (png,) + tuple(info or ((None, None), 100.0, "white"))
        self._show_image()
        self._status(note)

    def _show_image(self):
        """The preview: the whole figure in view (within the width and the height left
        under the bars, no scrolling), or at its printed size (96 px per inch)."""
        if not self._png:
            return
        png, (w, h), dpi, bg = self._png
        # a transparent background shows as a checkerboard
        back = ("background:repeating-conic-gradient(#d4d4d4 0% 25%, #fff 0% 50%) 50% / "
                "16px 16px;" if bg == "none" else "")
        if self.zoom.value == "actual" and w:
            size = f"width:{w / dpi * 96:.0f}px;max-width:none;"
        else:
            size = "max-width:100%;max-height:calc(100vh - 230px);width:auto;height:auto;"
        self.image.object = (f'<img src="data:image/png;base64,{png}" style="{size}{back}'
                             f'display:block;margin:auto;'
                             f'box-shadow:0 4px 18px rgba(0,0,0,.5)">')

    def _status(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.status.object = f'<div class="cv-status"{col}>{html}</div>'

    def _msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.msg.object = f'<div class="cv-status"{col}>{html}</div>'
