"""Figure editor: the widgets the shell's settings are copied from (settings.py names one for each
row; looks.make_widget clones it), and what saving needs.  None of these is on the page.

A mixin of the FigureEditor (figures/editor.py)."""

import os

import panel as pn

from .. import config
from . import draw as figdraw
from .cards import (
    DIST_BAR_LABELS, DIST_CUM, DIST_HSTYLES, DIST_NORMS, DIST_PLOTS, DIST_STATS_AT, DIST_WHIS,
    FIG_CMAPS, JOINT_PLOTS, LOCS, MARK_EXTREMES, SND_LAYOUTS, STORM_MOTIONS, TBL_COMPARE,
    TBL_DECIMALS, TBL_LAYOUTS, _auto, _chk, _f, cmap_select,
)

SND_ORDER = ("sbcape", "sbcin", "sblcl", "mlcape", "mlcin", "mllcl", "mllfc", "mucape",
             "mucin", "shear250", "shear500", "shear01", "shear03", "shear06", "srh250", "srh500", "srh1", "srh3", "esrh",
             "stp_fixed", "stp_eff", "scp")  # (the table choices as the Sounding tab lists them)


class FigureWidgets:
    """The widgets settings are copied from."""

    def _build_panel_widgets(self):
        """The figure's title, a plan view's area and a section's axes; how runs line up."""
        self.suptitle = pn.widgets.TextInput(name="Figure title (blank: none)",
                                             sizing_mode="stretch_width")
        self.dom = pn.widgets.Select(name="Plan-view area", options={
            "Follow the tracked storm": "storm", "Fixed box": "box",
            "Whole domain": "full"},
            description="Follow the tracked storm: the panel stays centred on the storm track "
                        "loaded for the run, moving with it from time to time. Fixed box: the "
                        "same x and y at every time.")
        self.half = _f("Half-width (km)", 12.5, step=0.5, start=0.5)
        self.box_x0 = _f("x min (km)", None, step=0.5)
        self.box_x1 = _f("x max (km)", None, step=0.5)
        self.box_y0 = _f("y min (km)", None, step=0.5)
        self.box_y1 = _f("y max (km)", None, step=0.5)
        self.coords = pn.widgets.Select(name="Axis coordinates", options={
            "Model grid x, y": "grid", "Relative to the storm": "storm"})
        self.xs_top = _f("Top (km)", 6.0, step=0.5, start=0.5)
        self.xs_coords = pn.widgets.Select(
            name="x–z, y–z x axis", options={"From the storm": "storm",
                                             "Model grid x, y": "grid"},
            description="The x axis of x–z and y–z sections through the storm: x (or y) "
                        "from the storm's, or the model's. Fixed ones: the model's; angled "
                        "and A–B ones: the distance along them")
        self.time_match = pn.widgets.Select(
            name="Line runs up by", width=240, value="time",
            options={"Time since each run's time zero": "time", "Output number": "output"},
            description="Time since time zero: a run's output at the same time since its time "
                        "zero. Output number: the nth output of each run, whatever its model "
                        "time; times are labelled with the first run's, and past a shorter "
                        "run's end its panels are blank")

    def _build_layer_widgets(self):
        """What the panels of each kind share: soundings, distributions, profiles, joint
        distributions, azimuthal means, tables, time axes."""
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
        sk.update(hd)  # (one dict for the spec)
        sk["table"] = pn.widgets.MultiChoice(
            name="Parameter table under each panel (blank: none)",
            options={f"{h} ({u})" if u else h: k for k, h, u in
                     sorted(figdraw.SND_PARAMS, key=lambda p: SND_ORDER.index(p[0]))})
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
        po = self.po = dict(
            xmin=_auto("Values from"), xmax=_auto("Values to"),
            zmin=_auto("Axis from (km)", description="Blank: the profiles' layer"),
            zmax=_auto("Axis to (km)", description="Blank: the profiles' layer"),
            zero_line=_chk("Zero line", False), mark_edited=_chk("Mark edited lines", True))
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
        to = self.to = dict(
            layout=pn.widgets.Select(name="Set out as", options=TBL_LAYOUTS, width=300),
            compare=pn.widgets.Select(name="Show", options=TBL_COMPARE, width=220),
            decimals=pn.widgets.Select(name="Decimals", options=TBL_DECIMALS, value=-1, width=100))
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
        self.ex_what = pn.widgets.Select(name="Show", value="both", options={
            k: v for k, v in MARK_EXTREMES.items() if v})
        self.ex_loc = pn.widgets.Select(name="Text at", options=LOCS, value="upper center")
        self.ex_marker = _chk("Mark where (+ max, × min)", True)
        self.ex_box = _chk("White box", True)

    def _build_more(self):
        """The contour key, the figure's own code, and where the figure is saved."""
        run = self.run
        self.ck_on = _chk("Contour key (nested circles)", False)
        self.ck_label = pn.widgets.TextInput(name="Name in the middle", value="w")
        self.ck_x = _f("x (figure 0–1)", 0.01, step=0.01)
        self.ck_y = _f("y (figure 0–1)", 0.01, step=0.01)
        self.ck_size = _f("Size (0–1)", 0.1, step=0.01)
        self.ck_fs = _f("Font (pt)", 10.0, step=1)
        self.ck_frame = _chk("Frame", True)
        self.code_on = _chk("Run the code", False)
        self.code = pn.widgets.CodeEditor(
            value="", language="python", theme="tomorrow_night", height=220,
            sizing_mode="stretch_width", on_keyup=False, indent=4, soft_tabs=True,
            print_margin=False)
        self._fig_dir = config.figures_dir(run.path)  # followed while the box is in it
        self.path = pn.widgets.TextInput(
            name="Save as (folder/name on the server, no extension)",
            value=os.path.join(self._fig_dir, "figure"), sizing_mode="stretch_width")
        self.fmt = pn.widgets.Select(name="Format", options={
            "PNG": "png", "PDF": "pdf", "SVG": "svg", "EPS": "eps", "TIFF": "tiff"},
            width=90, description="PDF, SVG and EPS keep text and lines as vectors (fields "
                                  "are embedded as images at the DPI)")
        self.dpi = pn.widgets.IntInput(name="DPI", start=50, end=1200, step=50, width=80)
        self.save_more = pn.widgets.Checkbox(name="Also the script and data")
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
        self.msg = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8))
