"""Figure editor: the widgets of the Panels, Layers, Annotate and File tabs, and Export.

A mixin of the FigureEditor (figures/editor.py)."""

import os
from contextlib import contextmanager

import panel as pn

from .. import config
from . import draw as figdraw
from ..theme import DIALOG_DARK
from ..viewer.picker import RunPicker
from .cards import (
    ANN_KINDS, DIST_BAR_LABELS, DIST_CUM, DIST_HSTYLES, DIST_NORMS, DIST_PLOTS,
    DIST_STATS_AT, DIST_WHIS, FIG_CMAPS, JOINT_PLOTS, LOCS, MARK_EXTREMES, SIZE_PRESETS,
    TBL_COMPARE, TBL_DECIMALS, TBL_LAYOUTS,
    SND_LAYOUTS, STORM_MOTIONS,
    TYPE_LABEL, GRID_DIMS, _auto, _checks, _chk, _f, _grid, _hint, _row, _section, _when,
    cmap_select,
)
from .kinds import KIND_LABELS
from .times import _tlabel

SND_ORDER = ("sbcape", "sbcin", "sblcl", "mlcape", "mlcin", "mllcl", "mllfc", "mucape",
             "mucin", "shear250", "shear500", "shear01", "shear03", "shear06", "srh250", "srh500", "srh1", "srh3", "esrh",
             "stp_fixed", "stp_eff", "scp")  # (the table choices as the Sounding tab lists them)
STORM_KEYS = ("storm", "storm_u", "storm_v")  # (the SRH of the table, legend and hodograph)


class FigureWidgets:
    """Builds the editor's widgets; FigureEditor._build puts them together."""

    @contextmanager
    def _redraws(self):
        """Widgets made in this block (attributes of the editor) redraw the preview when
        they change: FigureEditor._wire watches them."""
        before = set(vars(self))
        yield
        self._live_ws += [x for k, x in vars(self).items()
                          if k not in before and isinstance(x, pn.widgets.Widget)]

    def _build_panel_widgets(self):
        """Panels tab: grid and size, times, titles, area; and the runs (Layers tab)."""
        run = self.run
        # ---- Panels: grid and size
        with self._redraws():
            self.kind = pn.widgets.Select(name="Panels show", options=KIND_LABELS)
        # what the rows and the columns step through (plan views and sections)
        self.g_rows = pn.widgets.Select(name="Rows are", options=GRID_DIMS, value="none")
        self.g_cols = pn.widgets.Select(name="Columns are", options=GRID_DIMS, value="times")
        self.run_sel = pn.widgets.Select(name="Run (every panel)", options={})
        self.gg_runs = pn.widgets.MultiChoice(  # (a row or column of runs)
            name="Runs, in order", options={f"1. {os.path.basename(run.path)}": 0}, value=[0])
        self.grid_hint = _hint(
            "Rows and columns each step through runs, sections, times, fields or heights "
            "(e.g. runs down, sections across); the lists are below and under <b>Area</b>. "
            "With only one of them set its panels fill the grid row by row; with neither, "
            "every panel is alike (change one in the panel tree).")
        self.rows = pn.widgets.IntInput(name="Rows", start=1, end=8)
        self.cols = pn.widgets.IntInput(name="Columns", start=1, end=8)
        self.size_preset = pn.widgets.Select(name="Size", options=SIZE_PRESETS, value="")
        with self._redraws():
            self.width = _f("Width (in)", 8.0, step=0.25, start=1.0)
            self.height = _f("Height (in)", 6.0, step=0.25, start=1.0)
        self.fit_btn = pn.widgets.Button(
            name="Fit height", height=32, button_type="light",
            button_style="outline", description="The height the panels need at this width "
                                                 "(with room for labels, titles and colorbars)")
        # ---- Panels: times, fields, run & time of each panel
        with self._redraws():
            self.time1 = pn.widgets.Select(name="Time (every panel)", options={
                _tlabel(t): float(t) for t in run.times})
        self.tstep = pn.widgets.IntInput(name="Every … outputs", value=5, start=1)
        self.tfill = pn.widgets.Button(name="Fill from the shown time", height=32,
                                       button_type="light", button_style="outline")
        self.pz = pn.widgets.TextInput(name="Heights (km), one per panel", value="1, 3, 6",
                                       placeholder="e.g. 1, 3, 6",
                                       description="The layers at a height follow the "
                                                   "panel's (unless a layer keeps its own)")
        self.pz_mode = pn.widgets.Select(name="Panels at", options={
            "Heights (km AGL)": "height", "Model levels (k)": "level"})
        self.tm_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.pf_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.pf_cards = []
        # ---- Panels: titles
        with self._redraws():
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
            "Follow the tracked storm": "storm", "Fixed box": "box",
            "Whole domain": "full"},
            description="Follow the tracked storm: the panel stays centred on the storm track "
                        "loaded for the run, moving with it from time to time. Fixed box: the "
                        "same x and y at every time.")
        with self._redraws():
            self.half = _f("Half-width (km)", 12.5, step=0.5, start=0.5)
        self.box_x0 = _f("x min (km)", None, step=0.5)
        self.box_x1 = _f("x max (km)", None, step=0.5)
        self.box_y0 = _f("y min (km)", None, step=0.5)
        self.box_y1 = _f("y max (km)", None, step=0.5)
        self.box_html = pn.pane.HTML(margin=(2, 4))
        with self._redraws():
            self.coords = pn.widgets.Select(name="Axis coordinates", options={
                "Model grid x, y": "grid", "Relative to the storm": "storm"})
            self.xs_top = _f("Top (km)", 6.0, step=0.5, start=0.5)
            self.xs_coords = pn.widgets.Select(
                name="x–z, y–z x axis", options={"From the storm": "storm",
                                                 "Model grid x, y": "grid"},
                description="The x axis of x–z and y–z sections through the storm: x (or y) "
                            "from the storm's, or the model's. Fixed ones: the model's; angled "
                            "and A–B ones: the distance along them")
        self.xs_axes = _grid(self.xs_top, self.xs_coords)  # (where the section cards are)
        self.xs_axes_area = pn.Column(sizing_mode="stretch_width", margin=0)
        self.xs_axes_layers = pn.Column(sizing_mode="stretch_width", margin=0)
        self.sec_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.sec_add = pn.widgets.Button(name="+ Section", height=32, button_type="light",
                                         button_style="outline")
        self.xs_html = pn.pane.HTML(margin=(2, 4))
        # (a section figure's cards: Layers tab, one per panel)
        self.xsec_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.sec_new = pn.widgets.Button(name="+ Section", button_type="primary",
                                         button_style="outline", height=32)
        self.xsec_col = pn.Column(
            _hint("Each card is one panel: its run, time and cross-section (the layers "
                  "below are drawn in every section panel). <b>Duplicate</b> copies a card "
                  "into a new panel (e.g. an x–z card's y–z twin beside it); <b>One per "
                  "run</b> copies it down its column for each other run (runs × sections: "
                  "two cards and two clicks)."),
            self.xs_axes_layers, _row(self.sec_new), self.xsec_box,
            sizing_mode="stretch_width", margin=0)
        # ---- Layers: runs used
        self.runs_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.run_rows = []
        self.add_pick = RunPicker(run.path, on_open=lambda p: self._add_run(p),
                                  open_label="+ Add run", compact=True,
                                  exclude=lambda: [r["path"] for r in self.run_rows])
        self.add_path = self.add_pick.query  # (a folder typed or pasted there)
        self.runs_msg = pn.pane.HTML(sizing_mode="stretch_width")
        self.time_match = pn.widgets.Select(
            name="Line runs up by", width=240, value="time",
            options={"Time since each run's time zero": "time", "Output number": "output"},
            description="Time since time zero: a run's output at the same time since its time "
                        "zero. Output number: the nth output of each run, whatever its model "
                        "time; times are labelled with the first run's, and past a shorter "
                        "run's end its panels are blank")
        self.time_match.param.watch(self._on_time_match, "value")

    def _build_layer_widgets(self):
        """Layers tab: series, soundings, distributions, profiles and time axes."""
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
        self.ser_data = pn.widgets.Button(
            name="+ Your data", button_type="light", button_style="outline", height=32,
            description="A series of your own (observations, another model): paste "
                        "time and value columns or load a CSV file")
        self.ser_par = pn.widgets.Button(
            name="+ Parcels", button_type="light", button_style="outline", height=32,
            description="A variable of a parcel set over the parcel times (the viewer's "
                        "Parcels tab sets): its mean or median, a band, and parcels' own "
                        "lines")
        self.ser_wb = pn.widgets.MenuButton(
            name="+ w budget", button_type="light", button_style="outline", height=32,
            items=[("Rates: Dw/Dt, b, vpg, the rest", "rates"),
                   ("Integrated since the set's time: Δw, ∫b, ∫vpg, ∫rest", "int")])
        self.series_col = pn.Column(
            _hint('Each card picks its <b>Run</b> and <b>Panel</b>, like the sounding and '
                  'section cards; regions around the storm use each run’s track, and every '
                  'series is cached, like the Series tool. Time series: cards with the same '
                  'panel share a panel (other units get their own axis), and a card '
                  'can draw <b>All runs</b> or <b>Several runs…</b> (with an ensemble band). '
                  'Time–height: one card per panel; <b>One per run</b> copies a card down '
                  'its column for the other runs.  Time series: <b>+ Your data</b> draws points of '
                  'your own beside them, <b>+ Parcels</b> a parcel set\'s variable and '
                  '<b>+ w budget</b> its w budget.'),
            _grid((self.ser_from, 2), self.ser_add, self.ser_new, self.ser_data, self.ser_par,
                  self.ser_wb),
            self.ser_box,
            sizing_mode="stretch_width", margin=0)
        # soundings
        sk = self.sk = dict(
            pmax=_f("Bottom (hPa)", 1000.0, step=25), pmin=_f("Top (hPa)", 100.0, step=25),
            skew=_f("Skew", 35.0, step=5),
            tmin=_f("T left (°C)", -40.0, step=5), tmax=_f("T right (°C)", 50.0, step=5),
            lw=_f("Line width", 1.8, step=0.2),
            parcel=pn.widgets.Select(name="Parcel", options={
                "Mixed layer": "ml", "Surface": "sb", "Most unstable": "mu", "None": "none"}),
            params=_chk("CAPE / CIN in legend", True),
            guides=_chk("Adiabats", True), barbs=_chk("Wind barbs", True))
        hd = self.hd = dict(
            layout=pn.widgets.Select(name="Sounding layout", options=SND_LAYOUTS),
            hodo_center=pn.widgets.Select(name="Hodograph centred on", options={
                "The origin (0, 0)": "origin", "What is drawn (fit)": "fit",
                "Custom (u, v below)": "custom"}),
            hodo_max=_f("Hodograph ± (m/s)", 40.0, step=5,
                        description="Half the width of the (square) view"),
            hodo_cu=_f("Centre u (m/s)", 0.0, step=5),
            hodo_cv=_f("Centre v (m/s)", 0.0, step=5),
            hodo_top=_f("Hodograph top (km)", 9.0, step=1),
            hodo_rm=_chk("Bunkers right mover (RM)", True),
            hodo_lm=_chk("Bunkers left mover (LM)", True),
            hodo_mean=_chk("0–6 km mean wind", True),
            hodo_labels=_chk("Heights along the trace", True),
            hodo_heights=pn.widgets.TextInput(
                name="Heights marked (km)", value=figdraw.HODO_HEIGHTS,
                description="Along the trace, e.g. 0.5, 1, 3, 6 or 0:3:0.5 (start:stop:step)"),
            hodo_key=_chk("Key of the height colours", True),
            hodo_key_loc=pn.widgets.Select(name="Key at", options=LOCS, value="upper right"),
            hodo_key_ncol=pn.widgets.IntInput(name="Key columns", start=1, end=8, value=1),
            hodo_key_frame=_chk("Key frame", False),
            srh=pn.widgets.Select(name="SRH shading", options={
                "None": "", "0–1 km": "1", "0–3 km": "3"}),
            storm=pn.widgets.Select(name="Storm motion (SRH, ring)", options=STORM_MOTIONS),
            storm_u=_f("Storm u (m/s)", 0.0, step=1.0),
            storm_v=_f("Storm v (m/s)", 0.0, step=1.0),
            hodo_storm=_chk("Ring at the storm motion", True),
            inset_loc=pn.widgets.Select(name="Inset at", options={
                "Auto (clear of the traces)": "clear",
                "Auto, top corners only (older figures)": "auto", "Upper right": "upper right",
                "Upper left": "upper left", "Lower right": "lower right",
                "Lower left": "lower left", "Custom (x, y below)": "custom"}),
            inset_size=_f("Inset size", 0.37, step=0.01,
                          description="Width as a fraction of the skew-T's (0.37: the default)"),
            inset_x=_f("Inset x (left edge)", 0.62, step=0.01,
                       description="Fraction of the skew-T's width: 0 left, 1 right"),
            inset_y=_f("Inset y (bottom edge)", 0.6, step=0.01,
                       description="Fraction of the skew-T's height: 0 bottom, 1 top"))
        sk_shows = ("params", "guides", "barbs")
        sk_main = [w for k, w in sk.items() if k not in sk_shows]
        sk.update(hd)  # (one dict for the spec)
        sk["table"] = pn.widgets.MultiChoice(
            name="Parameter table under each panel (blank: none)",
            options={f"{h} ({u})" if u else h: k for k, h, u in
                     sorted(figdraw.SND_PARAMS, key=lambda p: SND_ORDER.index(p[0]))})
        self.snd_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.snd_tab = pn.widgets.Button(name="+ The map's soundings", height=32,
                                         button_type="primary", button_style="outline")
        self.snd_new = pn.widgets.Button(name="+ Sounding", button_type="light",
                                         button_style="outline", height=32)
        self.skewt_sec = _section("Skew-T", _grid(*sk_main),
                                  _checks(*[sk[k] for k in sk_shows]))
        self.hodo_sec = _section(
            "Hodograph",
            _grid(hd["hodo_center"], hd["hodo_max"], hd["hodo_top"], hd["hodo_cu"],
                  hd["hodo_cv"], hd["srh"]),
            _grid(hd["inset_loc"], hd["inset_size"], hd["inset_x"], hd["inset_y"]),
            _grid(hd["hodo_labels"], (hd["hodo_heights"], 2), hd["hodo_key"],
                  hd["hodo_key_loc"], hd["hodo_key_ncol"], hd["hodo_key_frame"]),
            _checks(("Storm motions", [hd["hodo_rm"], hd["hodo_lm"], hd["hodo_mean"],
                                       hd["hodo_storm"]])),
            _hint("The key and SRH shading are drawn in a hodograph of its own (side by "
                  "side, or the hodograph alone), not in an inset. The ring marks the "
                  "storm motion; with one sounding, dotted lines show the storm-relative "
                  "inflow and the 0–500 m shear (the critical angle), as in the Sounding "
                  "tab."))
        self.snd_col = pn.Column(
            _hint("Soundings with the same <b>Panel</b> share a skew-T (colour = "
                  "sounding). Storm soundings follow each run’s track."),
            _row(self.snd_tab, self.snd_new), self.snd_box,
            _section("Sounding panels", _grid(hd["layout"]), _grid((sk["table"], 3)),
                     _grid(*[hd[k] for k in STORM_KEYS]),
                     _hint("SRH (shading, legend, table) is relative to the chosen storm "
                           "motion; custom: ground-relative u, v.")),
            self.skewt_sec, self.hodo_sec,
            sizing_mode="stretch_width", margin=0)
        # distributions
        ds = self.ds = dict(
            plot=pn.widgets.Select(name="Draw as", options=DIST_PLOTS),
            norm=pn.widgets.Select(name="Histogram of", options=DIST_NORMS,
                                   description="PDF: the whole sample integrates to 1 (values "
                                               "outside the range count too); fraction: of "
                                               "the whole sample per bin"),
            bins=pn.widgets.IntInput(name="Bins", value=50, start=1, end=2000, width=90),
            width=_auto("Bin width", description="Blank: the number of bins"),
            hstyle=pn.widgets.Select(name="Bars as", options=DIST_HSTYLES),
            bar_labels=pn.widgets.Select(name="Bar labels", options=DIST_BAR_LABELS),
            cum=pn.widgets.Select(name="Fraction", options=DIST_CUM),
            whis=pn.widgets.Select(name="Whiskers", options=DIST_WHIS),
            xmin=_auto("Values from"), xmax=_auto("Values to"),
            ymin=_auto("Count axis from"), ymax=_auto("Count axis to"),
            logy=_chk("Log scale", False), means=_chk("Mean (diamond)", True),
            horizontal=_chk("Horizontal", False),
            zero_line=_chk("Zero line", False),
            alpha=_f("Fill opacity", 0.35, step=0.05, start=0.0, end=1.0),
            lw=_f("Line width", 1.5, step=0.25, start=0.0),
            stats=pn.widgets.MultiChoice(
                name="Statistics of each distribution (blank: none)",
                options={v: k for k, v in figdraw.DIST_STATS.items()}),
            stats_at=pn.widgets.Select(name="Statistics shown", options=DIST_STATS_AT),
            stats_loc=pn.widgets.Select(name="Box at", options=LOCS, value="upper right"))
        stat_keys = ("stats", "stats_at", "stats_loc")
        ds_shows = ("means", "zero_line", "logy", "horizontal")
        self.dist_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.dist_tab = pn.widgets.Button(name="+ The map's distributions", height=32,
                                          button_type="primary", button_style="outline")
        self.dist_new = pn.widgets.Button(name="+ Distribution", button_type="light",
                                          button_style="outline", height=32)
        self.dist_col = pn.Column(
            _hint("Distributions with the same <b>Panel</b> share a panel (colour = "
                  "distribution): e.g. one field at two times, or two runs."),
            _row(self.dist_tab, self.dist_new), self.dist_box,
            _section("Plot", _grid(*[w for k, w in ds.items()
                                     if k not in stat_keys + ds_shows]),
                     _checks(*[ds[k] for k in ds_shows]),
                     _hint("Values from / to: the value axis (histogram: the range of the "
                           "bins; blank: the data's, minimum to maximum). Count axis: the "
                           "histogram's or cumulative fraction's. The bins come from a "
                           "4000-bin histogram of every value, so changing them reads "
                           "nothing again.")),
            _section("Statistics", _grid((ds["stats"], 3), ds["stats_at"], ds["stats_loc"]),
                     _hint("From every value of each distribution (not only those in the "
                           "bins). Bar labels (histograms): percent of the whole sample.")),
            sizing_mode="stretch_width", margin=0)
        # vertical profiles
        po = self.po = dict(
            xmin=_auto("Values from"), xmax=_auto("Values to"),
            zmin=_auto("Axis from (km)", description="Blank: the profiles' layer"),
            zmax=_auto("Axis to (km)", description="Blank: the profiles' layer"),
            zero_line=_chk("Zero line", False), mark_edited=_chk("Mark edited lines", True))
        po_shows = ("zero_line", "mark_edited")
        self.prof_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.prof_tab = pn.widgets.Button(name="+ The Series tool's layer series", height=32,
                                          button_type="primary", button_style="outline")
        self.prof_new = pn.widgets.Button(name="+ Profile", button_type="light",
                                          button_style="outline", height=32)
        self.prof_data = pn.widgets.Button(
            name="+ Your data", button_type="light", button_style="outline", height=32,
            description="A profile of your own (a sounding, observations, another model): "
                        "paste height and value columns or load a CSV file")
        self.prof_col = pn.Column(
            _hint("Profiles with the same <b>Panel</b> share a panel (colour = "
                  "profile, or run): e.g. two runs, or one run at two times. A card can "
                  "draw <b>All runs</b> or <b>Several runs…</b> (with an ensemble band); "
                  "<b>+ Your data</b> draws a profile of your own beside them."),
            _row(self.prof_tab, self.prof_new, self.prof_data), self.prof_box,
            _section("Plot", _grid(*[w for k, w in po.items() if k not in po_shows]),
                     _checks(*[po[k] for k in po_shows]),
                     _hint("Values from / to and Axis from / to: the axes' ranges (blank: the "
                           "data's values and the profiles' layer).")),
            sizing_mode="stretch_width", margin=0)
        # joint distributions
        jo = self.jo = dict(
            plot=pn.widgets.Select(name="Draw as", options=JOINT_PLOTS),
            norm=pn.widgets.Select(name="Histogram of", options=DIST_NORMS,
                                   description="PDF: the whole sample integrates to 1; "
                                               "fraction: of the whole sample per bin"),
            bins=pn.widgets.IntInput(name="Bins (each axis)", value=60, start=2, end=200,
                                     width=90),
            cmap=cmap_select(),
            cbar_label=pn.widgets.TextInput(name="Colorbar label (blank: what it counts)",
                                            value=""),
            pcts=pn.widgets.TextInput(name="Contours enclosing (%)", value="50, 90",
                                      description="Each contour encloses this percentage "
                                                  "of the pairs, densest first"),
            ms=_f("Dot size", 2.0, step=0.5, start=0.5),
            alpha=_f("Dot opacity", 0.5, step=0.05, start=0.05, end=1.0),
            lw=_f("Line width", 1.2, step=0.25, start=0.25),
            xmin=_auto("x from"), xmax=_auto("x to"), ymin=_auto("y from"), ymax=_auto("y to"),
            stats=pn.widgets.MultiChoice(
                name="Statistics of each (blank: none)", value=["n", "r"],
                options={v: k for k, v in figdraw.JOINT_STATS.items()}),
            stats_loc=pn.widgets.Select(name="Box at", options=LOCS, value="upper left"),
            log=_chk("Log colours", True), reverse=_chk("Reverse", False),
            colorbar=_chk("Colorbar", True), contours=_chk("Contours over", False),
            contour_labels=_chk("Contour labels", True), fit=_chk("Fit line", False),
            one_one=_chk("1:1 line", False), zero_line=_chk("Zero lines", False))
        jo_shows = ("log", "reverse", "colorbar", "contours", "contour_labels", "fit",
                    "one_one", "zero_line")
        self.joint_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.joint_new = pn.widgets.Button(name="+ Joint distribution", button_type="light",
                                           button_style="outline", height=32)
        self.joint_col = pn.Column(
            _hint("Joint distributions with the same <b>Panel</b> share a panel "
                  "(colour = joint distribution, or run): e.g. two runs, or two times."),
            _row(self.joint_new), self.joint_box,
            _section("Plot", _grid(*[w for k, w in jo.items()
                                     if k not in jo_shows + ("stats", "stats_loc")]),
                     _checks(*[jo[k] for k in jo_shows]),
                     _hint("2D histogram: the panel's first joint distribution as shading "
                           "(the others as density contours in their colours). Scatter: "
                           "a random 5,000 pairs of each. x / y from / to: the axes and the "
                           "bins' range (blank: the data's). The bins come from a 200 × 200 "
                           "histogram of every pair, so changing them reads nothing again.")),
            _section("Statistics", _grid((jo["stats"], 3), jo["stats_loc"]),
                     _hint("From every pair: n, the Pearson correlation r (and r²), the "
                           "least-squares fit of y on x, and the means.")),
            sizing_mode="stretch_width", margin=0)
        # azimuthal means
        ao = self.ao = dict(
            plot=pn.widgets.Select(name="Shade as", options={"Grid cells": "mesh",
                                                             "Filled contours": "filled"}),
            cmap=pn.widgets.Select(name="Colormap", options={"The field's": ""} | {
                c: c for c in FIG_CMAPS}, value=""),
            nlevels=pn.widgets.IntInput(name="Colour steps", value=15, start=2, end=60,
                                        width=90),
            vmin=_auto("Min"), vmax=_auto("Max"),
            cbar_label=pn.widgets.TextInput(name="Colorbar label (blank: the field's)",
                                            value=""),
            rmin=_auto("Radius from (km)"), rmax=_auto("Radius to (km)"),
            zmin=_auto("Axis from (km)"), zmax=_auto("Axis to (km)"),
            reverse=_chk("Reverse", False), colorbar=_chk("Colorbar", True),
            clabels=_chk("Contour labels", True))
        ao_shows = ("reverse", "colorbar", "clabels")
        self.azim_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.azim_new = pn.widgets.Button(name="+ Azimuthal mean", button_type="light",
                                          button_style="outline", height=32)
        self.azim_col = pn.Column(
            _hint("Azimuthal means with the same <b>Panel</b> share a panel: the "
                  "first is shaded, the others drawn over it as contour lines (e.g. w "
                  "shaded with θ′ contours, or one run's against another's)."),
            _row(self.azim_new), self.azim_box,
            _section("Plot", _grid(*[w for k, w in ao.items() if k not in ao_shows]),
                     _checks(*[ao[k] for k in ao_shows]),
                     _hint("Min, Max: blank for the data's range (about 0 for a "
                           "diverging field). Radius and Axis from / to: the axes' ranges "
                           "(blank: the bins' and layer's).")),
            sizing_mode="stretch_width", margin=0)
        # tables
        to = self.to = dict(
            layout=pn.widgets.Select(name="Set out as", options=TBL_LAYOUTS, width=300),
            compare=pn.widgets.Select(name="Show", options=TBL_COMPARE, width=220),
            decimals=pn.widgets.Select(name="Decimals", options=TBL_DECIMALS, value=-1, width=100))
        self.table_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.table_new = pn.widgets.Button(name="+ Values", button_type="light",
                                           button_style="outline", height=32)
        self.table_col = pn.Column(
            _hint("A table's values come from these cards, each with its runs and times; cards "
                  "with the same <b>Panel</b> make one table."),
            _row(self.table_new), self.table_box,
            _section("Table", _grid((to["layout"], 2), to["compare"], to["decimals"]),
                     _hint("Differences: the first run's or first time's own values stay, and "
                           "the rest are shown less those, with their sign. Automatic decimals: "
                           "whole numbers for most sounding parameters, one for STP and SCP, "
                           "about three significant figures for statistics."),
                     collapsed=False),
            sizing_mode="stretch_width", margin=0)
        with self._redraws():
            # time axes of time-height / time-series panels
            self.ts_tmin = pn.widgets.TextInput(name="From (min)", placeholder="data")
            self.ts_tmax = pn.widgets.TextInput(name="To (min)", placeholder="data")
            self.ts_zmin = _f("Axis from (km)", 0.0, step=0.5)
            self.ts_zmax = _f("Axis to (km)", 10.0, step=0.5)
            self.ts_ymin = _auto("y from (left axis)")
            self.ts_ymax = _auto("y to (left axis)")
            self.ts_zero = _chk("Zero line", False)
            self.ts_mark = pn.widgets.Select(name="Mark each line's", options=MARK_EXTREMES)
            self.ts_mark_legend = _chk("Extremes in the legend", False)
            self.ts_mark_edited = _chk("Mark edited lines", True)
            # the maximum / minimum of a layer (plan, section and time-height panels)
            self.ex_on = _chk("Maximum / minimum", False)
            self.ex_layer = pn.widgets.Select(name="Of layer", options={"First fill": -1})
            self.ex_what = pn.widgets.Select(name="Show", value="both", options={
                k: v for k, v in MARK_EXTREMES.items() if v})
            self.ex_loc = pn.widgets.Select(name="Text at", options=LOCS, value="upper center")
            self.ex_marker = _chk("Mark where (+ max, × min)", True)
            self.ex_box = _chk("White box", True)
        self.series_col.append(_section(
            "Plot", _grid(
                self.ts_tmin, self.ts_tmax, self.ts_zmin, self.ts_zmax, self.ts_ymin,
                self.ts_ymax, self.ts_mark),
            _checks(self.ts_zero, self.ts_mark_legend, self.ts_mark_edited),
            _hint("Blank: the range of the data. Minutes count from each run's time zero "
                  "(<b>Runs used</b>). <b>Mark edited lines</b>: “(edited)” after the legend "
                  "label of a line with values changed by hand. For one time-series panel's "
                  "own y range, use the <b>Tree</b> tab.")))
        self.ex_opts = _grid(self.ex_layer, self.ex_what, self.ex_loc, self.ex_marker,
                             self.ex_box)
        _when(self.ex_on, self.ex_opts)
        self.ext_sec = _section(
            "Maximum and minimum", _grid((self.ex_on, 3)), self.ex_opts,
            _hint("Of the chosen layer (a fill, contours or shading; else the first fill) "
                  "over what each panel shows, in each panel."))

    def _build_more(self):
        """Annotate tab (annotations, own code), the contour key and the export widgets."""
        run = self.run
        # ---- contour key (Style tab) and annotations (Annotate tab)
        with self._redraws():
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
        # ---- Annotate: the figure's own code
        with self._redraws():
            self.code_on = _chk("Run the code", False)
        # highlighted (Ace, which the browser loads from a CDN), or a plain box that
        # needs nothing from the internet; both hold the same text
        self.code = pn.widgets.CodeEditor(
            value="", language="python", theme="tomorrow_night", height=220,
            sizing_mode="stretch_width", on_keyup=False, indent=4, soft_tabs=True,
            print_margin=False)
        self.code_plain = pn.widgets.TextAreaInput(
            name="Python, run after the figure is drawn", height=200,
            sizing_mode="stretch_width", visible=False,
            placeholder="e.g.\nax = axs[0]\nax.plot([-5, 5], [0, 0], 'w--', lw=1)\n"
                        "ax.text(0.5, 1.02, 'my note', transform=ax.transAxes)",
            stylesheets=["textarea { font-family: ui-monospace, Menlo, Consolas, monospace;"
                         " font-size: 12px; }"])
        self.code_box = _chk("Plain text box (if the highlighted editor stays blank, e.g. "
                             "without internet)", config.state("figure_code_plain") == "1")
        # ---- Saving (the Export dialog) and reopening (the File tab)
        self._fig_dir = config.figures_dir(run.path)  # followed while the box is in it
        self.path = pn.widgets.TextInput(
            name="Save as (folder/name on the server, no extension)",
            value=os.path.join(self._fig_dir, "figure"), sizing_mode="stretch_width")
        self.fmt = pn.widgets.Select(name="Format", options={
            "PNG": "png", "PDF": "pdf", "SVG": "svg", "EPS": "eps", "TIFF": "tiff"},
            width=90, description="PDF, SVG and EPS keep text and lines as vectors (fields "
                                  "are embedded as images at the DPI)")
        self.dpi = pn.widgets.IntInput(name="DPI", start=50, end=1200, step=50, width=80)
        self.exp_btn = pn.widgets.Button(name="Export", icon="device-floppy",
                                         button_type="primary", height=32, margin=(4, 4),
                                         description="Save or download the image")
        self.save_img = pn.widgets.Button(name="Save", icon="device-floppy",
                                          button_type="primary", height=32, margin=(5, 3),
                                          description="Save the image, and the figure's "
                                                      "settings to reopen it")
        self.save_more = pn.widgets.Checkbox(name="Also the script and data")
        self.dl = pn.widgets.FileDownload(callback=self._download, filename="figure.png",
                                          label="Download", icon="download",
                                          button_type="primary", button_style="outline",
                                          height=32, margin=(5, 3))
        with self._redraws():
            self.fit = pn.widgets.Select(
                name="Image size", options={"Trim white space": "trim",
                                            "Exact width, trim the height": "width",
                                            "Exact width and height": "full"},
                description="Trimming adds the margin around what is drawn, so the image can be "
                            "a little wider than the figure's width. Exact width is for a "
                            "journal column; exact width and height keeps all the white space.")
            self.pad = _f("Margin when trimmed (in)", 0.05, step=0.01, start=0.0)
            self.bg = pn.widgets.Select(name="Background", options={"White": "white",
                                                                    "Black": "black",
                                                                    "Transparent": "none"})
        self.saved_pick = pn.widgets.Select(
            name="Saved figures (in the Figures folder, ⚙ Settings)",
            description="This run's saved figures first, then the other folders of the "
                        "Figures setting. Picking one fills in the "
                        "path below.")
        self.spec_path = pn.widgets.TextInput(name="A saved figure (_spec.json)",
                                              placeholder="…/_src/figure_spec.json")
        self.load_btn = pn.widgets.Button(name="Open", button_type="light",
                                          button_style="outline", height=32)
        self.msg = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8))

    def _panels_tab(self):
        """The Panels tab's sections (and the parts and tree builders)."""
        self.grid_sec = _section(
            "Grid and size", _grid(self.kind, self.g_rows, self.g_cols),
            self.grid_hint, _grid(self.rows, self.cols, self.fit_btn),
            _grid(self.size_preset, self.width, self.height),
            _hint("The height follows the panels (grid, colorbar, titles) until you type "
                  "a size; <b>Fit height</b> makes it follow again."), collapsed=False)
        self.times_sec = _section("Times", _grid(self.run_sel, (self.gg_runs, 2)),
                                  _grid(self.time1, self.tstep, self.tfill),
                                  _grid(self.pz_mode, (self.pz, 2)), self.tm_box, self.pf_box)
        self.titles_sec = _section("Titles", self.suptitle, self.titles_box,
                                   _row(self.auto_titles, self.clear_titles))
        self.area_plan = pn.Column(_grid(self.dom, self.half, self.coords),
                                   _grid(self.box_x0, self.box_x1, self.box_y0, self.box_y1,
                                         n=2),
                                   self.box_html, margin=0, sizing_mode="stretch_width")
        self.area_xs = pn.Column(self.sec_box, _grid(self.sec_add), self.xs_axes_area,
                                 self.xs_html, margin=0, sizing_mode="stretch_width")
        self.area_body = pn.Column(self.area_plan, self.area_xs, margin=0,
                                   sizing_mode="stretch_width")
        self.area_sec = _section("Area", self.area_body)
        self.runs_sec = _section(
            "Runs used", _hint(
                "Each layer, section, sounding, distribution and series picks its run in its "
                "own <b>Run</b> list (a run not in the figure yet is added by picking it); a "
                "run nothing uses any more is dropped.  Here: each run's name, colour, time "
                "zero and storm track (for storm-centred panels and storm-relative fields and "
                "regions: the viewer's track for this run, or a track file; "
                "storm_tracks/*.csv is found automatically)."),
            self.time_match, self.runs_box,
            _hint("<b>Add a run</b> here if you want it before using it: your recent runs, "
                  "the runs next to this one and those under <b>Where your runs live</b> "
                  "(⚙ Settings). Type to filter, or paste a folder."),
            self.add_pick.body, self.runs_msg)
        self._build_combo()
        self._build_tree()
        # (the sections the figure kind uses only, and the area's: _keep_tabs)
        self.panels_all = [self.parts_sec, self.grid_sec, self.times_sec, self.titles_sec,
                           self.area_sec]
        self.area_all = [self.area_plan, self.area_xs]
        self.panels_tab = pn.Column(*self.panels_all, sizing_mode="stretch_width")
        return self.panels_tab

    def _build_export(self):
        """The Export dialog: where and how the image is saved."""
        self.exp_dlg = pn.Modal(
            pn.pane.HTML('<div class="cv-maptitle" style="font-size:16px"><b>Export the figure'
                         '</b></div>', margin=(0, 4)),
            self.path, _grid(self.fmt, self.dpi, self.bg), _grid(self.fit, self.pad),
            _hint("Publishers usually ask for 300–600 DPI, or PDF / EPS for line art."),
            self.save_more,
            _hint("The script (<code>scripts/&lt;name&gt;.py</code>) redraws the figure without "
                  "the viewer, from the data and drawing code it adds to <code>_src/</code>."),
            pn.Row(self.save_img, self.dl), width=640, margin=10,
            stylesheets=[DIALOG_DARK])
        self.exp_btn.on_click(lambda e: self.exp_dlg.show())
        self.fit.param.watch(lambda e: setattr(self.pad, "visible", e.new != "full"), "value")

    def _more_tabs(self):
        """The Annotate and File tabs."""
        annotate_tab = pn.Column(
            _section("Annotations", _hint(
                "Text, markers, arrows, lines and shapes in some panels or all, in "
                "axis units (km; minutes and km or values for series) or panel fractions."),
                _grid(self.ann_kind, self.ann_add), self.ann_box),
            _section("Your own code", _hint(
                "Python run after everything else is drawn, for what the editor has no "
                "setting for. It has <code>fig</code>, <code>axs</code> (the panels' axes: "
                "<code>axs[0]</code> is panel a), <code>data</code> (the panels' arrays), "
                "<code>spec</code>, <code>np</code> and <code>matplotlib</code>. It is saved "
                "with the figure and runs in its script too. An error stops the code, not "
                "the figure (the status line says where). The code is read when you "
                "click outside the box."), self.code_on, self.code, self.code_plain,
                self.code_box),
            sizing_mode="stretch_width")
        file_tab = pn.Column(
            self.anim_sec,
            _section("Open a saved figure", _hint(
                "Saving keeps the figure's settings in <code>_src/&lt;name&gt;_spec.json</code>, "
                "so you can keep editing it: pick it from the list, or give the path of its "
                "_spec.json (or its image or script)."), self.saved_pick,
                _grid((self.spec_path, 2), self.load_btn)),
            self.tpl_sec,
            sizing_mode="stretch_width")
        return annotate_tab, file_tab
