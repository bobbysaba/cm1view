"""Figure workspace: build a publication figure from panels and layers, preview it at
its final size, and export the image, a stand-alone script, the data and the spec."""

import base64
import io
import json
import os
import time as _time
import traceback
from collections import OrderedDict
from functools import partial

import numpy as np
import panel as pn
from matplotlib.colors import to_hex

from . import figdraw, figure as fg, render, series as ser, track as trk
from .fields import CMAPS
from .theme import GRID

PYART_CMAPS = ["HomeyerRainbow", "ChaseSpectral", "NWSRef", "NWSVel", "LangRainbow12",
               "SpectralExtended", "Carbone42", "Theodore16", "BuDRd18"]
FIG_CMAPS = list(dict.fromkeys(PYART_CMAPS + CMAPS + [
    "Greys", "gray_r", "Blues", "Reds", "Purples", "PuOr", "RdBu", "bwr", "jet"]))
LOCS = ["upper left", "upper right", "lower left", "lower right", "upper center",
        "lower center", "center left", "center right"]
LEVEL_MODES = {"Height (km AGL)": "height", "Model level (k)": "level",
               "Column max": "colmax", "Column min": "colmin"}
FONTS = ["sans-serif", "DejaVu Sans", "Liberation Sans", "Liberation Serif", "STIXGeneral",
         "Source Sans Pro", "Roboto", "Open Sans", "Noto Sans", "DejaVu Serif", "serif"]
FRAMES = {"Ground-relative": "ground", "Grid-relative": "grid", "Storm-relative": "storm"}
LETTERS = {"a": "{a}", "(a)": "({a})", "a)": "{a})", "A": "{A}", "(A)": "({A})"}
TYPE_LABEL = {"fill": "Fill", "contour": "Contours", "shade": "Shading", "vectors": "Vectors",
              "track": "Storm track", "line": "Section line"}
CARD = {"border": f"1px solid {GRID}", "border-radius": "8px", "padding": "2px 6px 6px 6px",
        "margin": "4px 0"}


def _hex(c, default="#000000"):
    try:
        return to_hex(c)
    except (ValueError, TypeError):
        return default


def _f(name, value, width=90, **kw):
    return pn.widgets.FloatInput(name=name, value=value, width=width, **kw)


def _row(*objs):
    return pn.FlexBox(*objs, flex_wrap="wrap", align_items="flex-end", gap="0 6px",
                      sizing_mode="stretch_width")


class LayerCard:
    """Widgets of one layer; collect() -> the layer dict."""

    def __init__(self, ed, lay):
        self.ed, self.type = ed, lay["type"]
        F, g = ed.F, ed.F.groups()
        self.lay = dict(lay)
        self.w = w = {}
        w["on"] = pn.widgets.Checkbox(value=lay.get("on", True), width=20, margin=(8, 2, 0, 4))
        btn = dict(width=32, height=28, margin=(2, 1), button_type="default",
                   button_style="outline")
        self.up = pn.widgets.Button(name="↑", description="Draw earlier (below)", **btn)
        self.down = pn.widgets.Button(name="↓", description="Draw later (on top)", **btn)
        self.rm = pn.widgets.Button(name="✕", description="Remove the layer", **btn)
        t = self.type
        if t in ("fill", "contour", "shade"):
            w["field"] = pn.widgets.Select(name="Field", groups=g, value=lay["field"],
                                           width=220)
            w["mode"] = pn.widgets.Select(name="Level", options=LEVEL_MODES,
                                          value=lay.get("mode", "height"), width=130)
            w["z"] = _f("km / k", lay.get("z", 1.0), 80, step=0.25)
        if t == "fill":
            w["cmap"] = pn.widgets.Select(name="Colormap", options=FIG_CMAPS,
                                          value=lay["cmap"] if lay["cmap"] in FIG_CMAPS
                                          else "viridis", width=150)
            w["reverse"] = pn.widgets.Checkbox(name="Reverse", value=lay.get("reverse", False),
                                               margin=(5, 6, 12, 6))
            w["white_first"] = pn.widgets.Checkbox(name="White first",
                                                   value=lay.get("white_first", False),
                                                   margin=(5, 6, 12, 6))
            w["vmin"] = _f("Min", lay["vmin"])
            w["vmax"] = _f("Max", lay["vmax"])
            w["nlevels"] = pn.widgets.IntInput(name="Steps (0 = smooth)",
                                               value=int(lay.get("nlevels") or 0), start=0,
                                               end=60, width=120)
            w["style"] = pn.widgets.Select(name="Draw as", options={
                "Grid cells": "mesh", "Filled contours": "contourf"},
                value=lay.get("style", "mesh"), width=130)
            w["mask_below"] = pn.widgets.TextInput(
                name="Blank where ≤", value="" if lay.get("mask_below") is None
                else f"{lay['mask_below']:g}", width=100, placeholder="off")
            w["extend"] = pn.widgets.Select(name="Colorbar ends", options=[
                "neither", "max", "min", "both"], value=lay.get("extend", "neither"),
                width=110)
            w["field"].param.watch(self._on_fill_field, "value")
        if t == "contour":
            w["levels"] = pn.widgets.TextInput(name="Levels (e.g. 10, 20 or -6:6:2)",
                                               value=str(lay["levels"]), width=200)
            w["neg_dashed"] = pn.widgets.Checkbox(name="Dash negative",
                                                  value=lay.get("neg_dashed", True),
                                                  margin=(5, 6, 12, 6))
            w["clabel"] = pn.widgets.Checkbox(name="Label lines", value=lay.get("clabel", False),
                                              margin=(5, 6, 12, 6))
        if t == "shade":
            w["threshold"] = _f("Threshold", lay["threshold"])
            w["above"] = pn.widgets.Select(name="Shade", options={"Above": True, "Below": False},
                                           value=lay.get("above", True), width=90)
            w["alpha"] = _f("Opacity", lay.get("alpha", 0.6), 80, step=0.1, start=0, end=1)
            w["outline_on"] = pn.widgets.Checkbox(name="Outline", value=bool(lay.get("outline")),
                                                  margin=(5, 6, 12, 6))
            w["outline"] = pn.widgets.ColorPicker(name="Outline color",
                                                  value=_hex(lay.get("outline") or "magenta"),
                                                  width=90)
        if t == "vectors":
            w["z"] = _f("Height (km)", lay.get("z", 0.0), 90, step=0.25)
            w["spacing"] = _f("Spacing (km)", lay.get("spacing", 2.0), 100, step=0.25)
            w["zspacing"] = _f("Vertical spacing (km)", lay.get("zspacing", 0.5), 140,
                               step=0.1)
            w["frame"] = pn.widgets.Select(name="Frame", options=FRAMES,
                                           value=lay.get("frame", "ground"), width=140)
            w["scale"] = _f("Scale (larger = shorter)", lay.get("scale", 250.0), 160, step=25)
            w["width"] = _f("Arrow width", lay.get("width", 0.002), 100, step=0.0005)
            w["key"] = _f("Key arrow (m/s, 0 = none)", lay.get("key", 0.0), 170, step=5)
        if t in ("contour", "shade", "vectors", "track", "line"):
            w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(lay.get("color", "k")),
                                                width=70)
        if t in ("contour", "shade", "track", "line"):
            w["lw"] = _f("Line width", lay.get("lw", 1.0), 90, step=0.25)
        if t == "track":
            w["ls"] = pn.widgets.Select(name="Style", options={"solid": "-", "dashed": "--",
                                                               "dotted": ":"},
                                        value=lay.get("ls", "-"), width=90)
            w["marker"] = pn.widgets.Checkbox(name="Mark the panel time",
                                              value=lay.get("marker", True), margin=(5, 6, 12, 6))
        if t == "line":
            w["labels"] = pn.widgets.TextInput(name="End labels", value=lay.get("labels", ""),
                                               width=110)
        if t in ("contour", "shade", "track", "line"):
            w["legend"] = pn.widgets.TextInput(name="Legend text (blank: none)",
                                               value=lay.get("legend", ""), width=200)
        for k, x in w.items():
            if k != "field" or t != "fill":
                x.param.watch(lambda e: ed.request(), "value")
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self._set_title()
        body = [x for k, x in w.items() if k != "on"]
        self.panel = pn.Column(
            pn.Row(w["on"], self.title, pn.Spacer(), self.up, self.down, self.rm, margin=0,
                   sizing_mode="stretch_width"),
            _row(*body), styles=CARD, sizing_mode="stretch_width", margin=(2, 0))

    def _set_title(self):
        t = self.type
        sub = ""
        if "field" in self.w:
            d = self.ed.F[self.w["field"].value]
            sub = f" · {d.label}"
        self.title.object = f"<b>{TYPE_LABEL[t]}</b>{sub}"

    def _on_fill_field(self, ev):
        """New fill field: its default colours, range and units."""
        d = fg.layer_defaults("fill", self.ed.F, ev.new)
        self.lay["units"] = d["units"]
        self.ed._hold = True
        try:
            for k in ("cmap", "vmin", "vmax", "extend"):
                self.w[k].value = d[k] if k != "cmap" or d[k] in FIG_CMAPS else "viridis"
            self.w["mask_below"].value = "" if d["mask_below"] is None else f"{d['mask_below']:g}"
        finally:
            self.ed._hold = False
        self._set_title()
        self.ed.request()

    def collect(self):
        w, lay = self.w, dict(self.lay)
        for k, x in w.items():
            if k in ("outline_on",):
                continue
            lay[k] = x.value
        if self.type == "fill":
            mb = str(w["mask_below"].value).strip()
            try:
                lay["mask_below"] = float(mb) if mb else None
            except ValueError:
                lay["mask_below"] = None
            lay["units"] = self.ed.F[lay["field"]].units
        if self.type == "shade":
            lay["outline"] = w["outline"].value if w["outline_on"].value else ""
        if "field" in w:
            self._set_title()
        return lay


class FigureEditor:
    def __init__(self, viewer):
        self.v = viewer
        self.run, self.F = viewer.run, viewer.F
        self.cache = OrderedDict()  # data key -> panel arrays
        self._hold = False  # widgets being set from a spec: no re-render per widget
        self._req = 0
        self.cards = []
        self._build()
        self.set_spec(self._default())

    # ------------------------------------------------------------ widgets
    def _build(self):
        run = self.run
        topts = {f"{run.time_label(t)}  ({run.times[t] / 60:.0f} min)": t
                 for t in range(len(run.times))}
        self.start_map = pn.widgets.Button(name="From map view", button_type="primary",
                                           button_style="outline", height=32)
        self.start_xs = pn.widgets.Button(name="From cross-section", button_type="primary",
                                          button_style="outline", height=32)
        self.start_def = pn.widgets.Button(name="Default grid",
                                           button_type="light", button_style="outline",
                                           height=32)
        # layout
        self.kind = pn.widgets.Select(name="Panels show", options={
            "Plan views": "plan", "Vertical cross-sections": "xsec"}, width=190)
        self.vary = pn.widgets.Select(name="Panels differ in", options={
            "Time (same layers)": "time", "Field (one time)": "field"}, width=170)
        self.rows = pn.widgets.IntInput(name="Rows", start=1, end=8, width=70)
        self.cols = pn.widgets.IntInput(name="Columns", start=1, end=8, width=80)
        self.width = _f("Width (in)", 8.0, 90, step=0.25, start=1.0)
        self.height = _f("Height (in)", 6.0, 90, step=0.25, start=1.0)
        self.times = pn.widgets.MultiChoice(name="Times (one per panel, in order)",
                                            options=topts, sizing_mode="stretch_width")
        self.tstep = pn.widgets.IntInput(name="every … outputs", value=5, start=1, width=110)
        self.tfill = pn.widgets.Button(name="Fill from shown time", height=32,
                                       button_type="light", button_style="outline")
        self.time1 = pn.widgets.Select(name="Time", options=topts, width=220)
        self.pf_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.pf_rows = []
        self.suptitle = pn.widgets.TextInput(name="Figure title (blank: none)", width=300)
        self.titles = pn.widgets.TextAreaInput(name="Panel titles (one line per panel)",
                                               height=90, sizing_mode="stretch_width")
        self.auto_titles = pn.widgets.Button(name="Titles from fields / times", height=32,
                                             button_type="light", button_style="outline")
        # region
        self.dom = pn.widgets.Select(name="Plan-view area", options={
            "Centred on tracked storm": "storm", "Fixed box (map view)": "box",
            "Whole domain": "full"}, width=210)
        self.half = _f("Half-width (km)", 12.5, 110, step=0.5, start=0.5)
        self.box_btn = pn.widgets.Button(name="Use current map view", height=32,
                                         button_type="light", button_style="outline")
        self.box_html = pn.pane.HTML(margin=(8, 4))
        self.coords = pn.widgets.Select(name="Axis coordinates", options={
            "Model grid x, y": "grid", "Relative to the storm": "storm"}, width=190)
        self.xs_mode = pn.widgets.Select(name="Section", options={
            "Through tracked storm": "storm", "Fixed A–B from the map": "fixed"}, width=200)
        self.xs_angle = _f("Direction (° from east)", 0.0, 150, step=15)
        self.xs_half = _f("Half-length (km)", 10.0, 120, step=1, start=0.5)
        self.xs_offx = _f("Offset x (km)", 0.0, 100, step=0.5)
        self.xs_offy = _f("Offset y (km)", 0.0, 100, step=0.5)
        self.xs_top = _f("Top (km)", 6.0, 90, step=0.5, start=0.5)
        self.xs_ab = pn.widgets.Button(name="Use map A–B", height=32, button_type="light",
                                       button_style="outline")
        self.xs_html = pn.pane.HTML(margin=(8, 4))
        # layers
        self.layer_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.add_btns = {k: pn.widgets.Button(name=f"+ {TYPE_LABEL[k]}", height=30,
                                              button_type="light", button_style="outline",
                                              margin=(4, 2))
                         for k in TYPE_LABEL}
        # text & axes
        self.font = pn.widgets.Select(name="Font", options=FONTS, width=160)
        self.fsize = _f("Size (pt)", 10.0, 80, step=0.5, start=4)
        self.xlabel = pn.widgets.TextInput(name="x label", width=170)
        self.ylabel = pn.widgets.TextInput(name="y label", width=170)
        self.ticklabels = pn.widgets.Select(name="Tick labels", options={
            "All panels": "all", "Outer panels": "outer", "None": "none"}, width=130)
        self.ticks = pn.widgets.Checkbox(name="Tick marks", margin=(5, 6, 12, 6))
        self.minor = pn.widgets.Checkbox(name="Minor ticks", margin=(5, 6, 12, 6))
        self.equal = pn.widgets.Checkbox(name="Equal x/y scale (plan)", margin=(5, 6, 12, 6))
        self.let_on = pn.widgets.Checkbox(name="Panel letters", margin=(5, 6, 12, 6))
        self.let_fmt = pn.widgets.Select(name="Style", options=LETTERS, width=80)
        self.let_loc = pn.widgets.Select(name="Where", options=LOCS, width=130)
        self.let_size = _f("Size", 12.0, 70, step=1)
        self.let_bold = pn.widgets.Checkbox(name="Bold", margin=(5, 6, 12, 6))
        self.tl_on = pn.widgets.Checkbox(name="Time label", margin=(5, 6, 12, 6))
        self.tl_fmt = pn.widgets.TextInput(name="Text ({min}, {s}, {hms})", width=180)
        self.tl_loc = pn.widgets.Select(name="Where", options=LOCS, width=130)
        self.tl_size = _f("Size", 12.0, 70, step=1)
        self.tl_bold = pn.widgets.Checkbox(name="Bold", margin=(5, 6, 12, 6))
        self.tl_t0 = _f("Minutes counted from", 0.0, 150, step=10,
                        description="Time zero for {min}, in model minutes (e.g. the "
                                    "initiation time)")
        self.cb_mode = pn.widgets.Select(name="Colorbar", options={
            "One shared": "shared", "One per panel": "each", "None": "none"}, width=130)
        self.cb_orient = pn.widgets.Select(name="Orientation", options=[
            "horizontal", "vertical"], width=120)
        self.cb_label = pn.widgets.TextInput(name="Label (blank: units)", width=160)
        self.cb_shrink = _f("Length (fraction)", 0.7, 120, step=0.05, start=0.1, end=1.0)
        self.cb_ticks = pn.widgets.TextInput(name="Ticks (blank: auto)", width=150,
                                             placeholder="0:60:10")
        self.lg_loc = pn.widgets.Select(name="Legend", options=LOCS, width=130)
        self.lg_panel = pn.widgets.IntInput(name="in panel", start=1, end=64, width=80)
        # export
        parts = run.path.rstrip("/").split("/")[-2:]
        self.path = pn.widgets.TextInput(
            name="Save as (path on the server, no extension)",
            value=os.path.join(os.getcwd(), "_".join(parts) + "_figure"),
            sizing_mode="stretch_width", min_width=280)
        self.fmt = pn.widgets.Select(name="Format", options={
            "PNG": "png", "PDF (vector + raster fields)": "pdf", "SVG": "svg", "EPS": "eps",
            "TIFF": "tiff"}, width=210)
        self.dpi = pn.widgets.IntInput(name="DPI", start=50, end=1200, step=25, width=90)
        self.tight = pn.widgets.Checkbox(name="Trim white space", margin=(5, 6, 12, 6))
        self.bg = pn.widgets.Select(name="Background", options={"White": "white",
                                                                "Transparent": "none"},
                                    width=120)
        self.save_img = pn.widgets.Button(name="Save image", button_type="primary", height=32)
        self.save_all = pn.widgets.Button(
            name="Save image + script + data", button_type="primary", button_style="outline",
            height=32, description="Also writes <name>.py (redraws the figure without the "
                                   "viewer), <name>_data.npz and <name>_spec.json")
        self.dl = pn.widgets.FileDownload(callback=self._download, filename="figure.png",
                                          label="Download image", button_type="primary",
                                          button_style="outline", height=32)
        self.spec_path = pn.widgets.TextInput(name="Load a saved spec (.json)",
                                              sizing_mode="stretch_width", min_width=280)
        self.load_btn = pn.widgets.Button(name="Load", button_type="light",
                                          button_style="outline", height=32)
        self.msg = pn.pane.HTML(sizing_mode="stretch_width")
        # preview
        self.auto = pn.widgets.Checkbox(name="Update automatically", value=True,
                                        margin=(10, 8, 0, 8))
        self.update = pn.widgets.Button(name="Update preview", icon="refresh", height=32,
                                        button_type="primary", button_style="outline")
        self.status = pn.pane.HTML(sizing_mode="stretch_width")
        self.image = pn.pane.HTML(sizing_mode="stretch_width", margin=(4, 8))

        tabs = pn.Tabs(
            ("Layout", pn.Column(
                _row(self.kind, self.vary, self.rows, self.cols, self.width, self.height),
                self.times, _row(self.tstep, self.tfill, self.time1), self.pf_box,
                self.suptitle, self.titles, self.auto_titles)),
            ("Region", pn.Column(
                _row(self.dom, self.half, self.box_btn), self.box_html, _row(self.coords),
                pn.pane.HTML('<div class="cv-hint">Cross-sections:</div>', margin=(8, 4, 0, 4)),
                _row(self.xs_mode, self.xs_angle, self.xs_half, self.xs_offx, self.xs_offy,
                     self.xs_top, self.xs_ab), self.xs_html)),
            ("Layers", pn.Column(_row(*self.add_btns.values()), self.layer_box)),
            ("Text & axes", pn.Column(
                _row(self.font, self.fsize, self.xlabel, self.ylabel),
                _row(self.ticklabels, self.ticks, self.minor, self.equal),
                _row(self.let_on, self.let_fmt, self.let_loc, self.let_size, self.let_bold),
                _row(self.tl_on, self.tl_fmt, self.tl_loc, self.tl_size, self.tl_bold,
                     self.tl_t0),
                _row(self.cb_mode, self.cb_orient, self.cb_label, self.cb_shrink,
                     self.cb_ticks),
                _row(self.lg_loc, self.lg_panel))),
            ("Export", pn.Column(
                self.path, _row(self.fmt, self.dpi, self.tight, self.bg),
                _row(self.save_img, self.save_all, self.dl),
                _row(self.spec_path, self.load_btn), self.msg)),
            dynamic=False, sizing_mode="stretch_width")
        self.editor = pn.Column(
            pn.pane.HTML('<div class="cv-hint">Start from</div>', margin=(6, 4, 0, 4)),
            _row(self.start_map, self.start_xs, self.start_def), tabs,
            scroll=True, sizing_mode="stretch_height", width=560,
            styles={"border-left": f"1px solid {GRID}", "padding": "0 8px"})
        self.preview = pn.Column(
            _row(self.update, self.auto), self.status, self.image, scroll=True,
            sizing_mode="stretch_both", styles={"min-width": "0"})
        self.panel = pn.Row(self.preview, self.editor, sizing_mode="stretch_both", margin=0)
        self._wire()

    def _wire(self):
        rq = lambda *e: self.request()  # noqa: E731
        for w in (self.kind, self.width, self.height, self.times, self.time1, self.suptitle,
                  self.titles, self.half, self.coords, self.xs_mode, self.xs_angle,
                  self.xs_half, self.xs_offx, self.xs_offy, self.xs_top, self.font,
                  self.fsize, self.xlabel, self.ylabel, self.ticklabels, self.ticks,
                  self.minor, self.equal, self.let_on, self.let_fmt, self.let_loc,
                  self.let_size, self.let_bold, self.tl_on, self.tl_fmt, self.tl_loc,
                  self.tl_size, self.tl_bold, self.tl_t0, self.cb_mode, self.cb_orient,
                  self.cb_label, self.cb_shrink, self.cb_ticks, self.lg_loc, self.lg_panel,
                  self.bg):
            w.param.watch(rq, "value")
        for w in (self.vary, self.rows, self.cols):
            w.param.watch(lambda e: self._on_layout(), "value")
        self.kind.param.watch(lambda e: self._on_kind(), "value")
        self.dom.param.watch(self._on_dom, "value")
        self.box_btn.on_click(lambda e: self._use_view())
        self.xs_ab.on_click(lambda e: self._use_ab())
        self.tfill.on_click(lambda e: self._fill_times())
        self.auto_titles.on_click(lambda e: self._auto_titles())
        for k, b in self.add_btns.items():
            b.on_click(partial(self._add_layer, k))
        self.start_map.on_click(lambda e: self.from_map())
        self.start_xs.on_click(lambda e: self.from_xsec())
        self.start_def.on_click(lambda e: self.set_spec(self._default()))
        self.update.on_click(lambda e: self.request(force=True, delay=False))
        self.save_img.on_click(lambda e: self._save(False))
        self.save_all.on_click(lambda e: self._save(True))
        self.load_btn.on_click(lambda e: self._load_spec())
        for w in (self.fmt, self.path):
            w.param.watch(lambda e: self._set_dl_name(), "value")

    # ------------------------------------------------------------ spec <-> widgets
    def set_spec(self, spec):
        """Show `spec` in the widgets (one re-render at the end)."""
        self.spec = spec
        self._hold = True
        try:
            s = spec
            self.kind.value, self.vary.value = s["kind"], s["vary"]
            self.rows.value, self.cols.value = int(s["rows"]), int(s["cols"])
            self.width.value, self.height.value = float(s["size"][0]), float(s["size"][1])
            self.times.value = [int(t) for t in s["times"]]
            self.time1.value = int(s["time"])
            self.suptitle.value = s.get("suptitle", "")
            self.titles.value = "\n".join(s.get("titles", []))
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
            f = s.get("font", {})
            self.font.value = f.get("family", "sans-serif") if f.get("family") in FONTS \
                else "sans-serif"
            self.fsize.value = float(f.get("size", 10))
            L = s["letters"]
            self.let_on.value, self.let_loc.value = L.get("on", True), L.get("loc", "upper left")
            self.let_fmt.value = L.get("fmt", "{a}") if L.get("fmt") in LETTERS.values() \
                else "{a}"
            self.let_size.value, self.let_bold.value = float(L.get("size", 12)), \
                L.get("bold", True)
            T = s["time_label"]
            self.tl_on.value, self.tl_fmt.value = T.get("on", True), T.get("fmt", "")
            self.tl_loc.value, self.tl_size.value = T.get("loc", "lower right"), \
                float(T.get("size", 12))
            self.tl_bold.value, self.tl_t0.value = T.get("bold", True), float(T.get("t0_min", 0))
            c = s["colorbar"]
            self.cb_mode.value, self.cb_orient.value = c.get("mode", "shared"), \
                c.get("orientation", "horizontal")
            self.cb_label.value, self.cb_shrink.value = c.get("label", ""), \
                float(c.get("shrink", 0.7))
            self.cb_ticks.value = c.get("ticks", "")
            lg = s.get("legend", {})
            self.lg_loc.value, self.lg_panel.value = lg.get("loc", "upper right"), \
                int(lg.get("panel", 0)) + 1
            e = s.get("export", {})
            self.fmt.value, self.dpi.value = e.get("format", "png"), int(e.get("dpi", 250))
            self.tight.value = e.get("tight", True)
            self.bg.value = s.get("background", "white")
            self._build_cards(s["layers"])
            self._build_pf(s.get("panel_fills", []))
        finally:
            self._hold = False
        self._show_region()
        self._on_kind(render_=False)
        self._set_dl_name()
        self.request(delay=False)

    def collect(self):
        """The spec of the current widget values."""
        s = dict(self.spec)
        s.update(
            kind=self.kind.value, vary=self.vary.value, rows=int(self.rows.value or 1),
            cols=int(self.cols.value or 1),
            size=[float(self.width.value or 8), float(self.height.value or 6)],
            times=[int(t) for t in self.times.value], time=int(self.time1.value),
            layers=[c.collect() for c in self.cards],
            panel_fills=[self._pf_collect(r) for r in self.pf_rows],
            suptitle=self.suptitle.value,
            titles=self.titles.value.split("\n") if self.titles.value.strip() else [],
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
                         minor=self.minor.value, equal=self.equal.value)
        s["font"] = dict(family=self.font.value, size=float(self.fsize.value or 10))
        s["letters"] = dict(on=self.let_on.value, fmt=self.let_fmt.value, loc=self.let_loc.value,
                            size=float(self.let_size.value or 12), bold=self.let_bold.value)
        s["time_label"] = dict(on=self.tl_on.value, fmt=self.tl_fmt.value or "t = {min:g} min",
                               loc=self.tl_loc.value, size=float(self.tl_size.value or 12),
                               bold=self.tl_bold.value, t0_min=float(self.tl_t0.value or 0))
        s["colorbar"] = dict(s["colorbar"], mode=self.cb_mode.value,
                             orientation=self.cb_orient.value, label=self.cb_label.value,
                             shrink=float(self.cb_shrink.value or 0.7), ticks=self.cb_ticks.value)
        s["legend"] = dict(s.get("legend", {}), loc=self.lg_loc.value,
                           panel=max(0, int(self.lg_panel.value or 1) - 1))
        s["export"] = dict(format=self.fmt.value, dpi=int(self.dpi.value or 250),
                           tight=self.tight.value)
        self.spec = s
        return s

    # ------------------------------------------------------------ layers
    def _build_cards(self, layers):
        self.cards = [self._card(lay) for lay in layers]
        self._show_cards()

    def _card(self, lay):
        c = LayerCard(self, lay)
        c.up.on_click(lambda e: self._move(c, -1))
        c.down.on_click(lambda e: self._move(c, 1))
        c.rm.on_click(lambda e: self._remove(c))
        return c

    def _show_cards(self):
        self.layer_box.objects = [c.panel for c in self.cards] or [pn.pane.HTML(
            '<div class="cv-empty">No layers: add one above.</div>')]

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
        head = [pn.pane.HTML('<div class="cv-hint">Fill of each panel (replaces the first '
                             'fill layer):</div>', margin=(6, 4, 0, 4))] if rows else []
        self.pf_box.objects = head + [r["panel"] for r in rows]

    def _pf_row(self, i, pf):
        F = self.F
        r = dict(
            field=pn.widgets.Select(name=f"{figdraw.panel_letter(i, '{a}')}: field",
                                    groups=F.groups(), value=pf["field"], width=210),
            cmap=pn.widgets.Select(name="Colormap", options=FIG_CMAPS,
                                   value=pf["cmap"] if pf["cmap"] in FIG_CMAPS else "viridis",
                                   width=140),
            vmin=_f("Min", float(pf["vmin"]), 80), vmax=_f("Max", float(pf["vmax"]), 80))

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
        r["panel"] = _row(r["field"], r["cmap"], r["vmin"], r["vmax"])
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
        self.times.visible = self.tstep.visible = self.tfill.visible = not field
        self.time1.visible = field
        self._build_pf([self._pf_collect(r) for r in self.pf_rows])
        if field and self.cb_mode.value == "shared":
            self.cb_mode.value = "each"
        self.request()

    def _on_kind(self, render_=True):
        xsec = self.kind.value == "xsec"
        self.equal.visible = not xsec
        if render_ and not self._hold:
            self._hold = True
            try:
                if xsec:
                    self.xlabel.value = ("distance from storm (km)"
                                         if self.xs_mode.value == "storm" else "distance (km)")
                    self.ylabel.value = "height (km)"
                else:
                    self.xlabel.value, self.ylabel.value = "x (km)", "y (km)"
            finally:
                self._hold = False
            self.request()
        field = self.vary.value == "field"
        self.times.visible = self.tstep.visible = self.tfill.visible = not field
        self.time1.visible = field

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
        b = self.spec["domain"].get("box")
        self.half.visible = self.dom.value == "storm"
        self.box_html.object = ('<div class="cv-hint">Box x {:.1f} – {:.1f}, y {:.1f} – {:.1f} '
                                'km</div>'.format(*b) if b and self.dom.value == "box" else "")
        x = self.spec["xsec"]
        self.xs_html.object = (
            '<div class="cv-hint">A ({:.1f}, {:.1f}) → B ({:.1f}, {:.1f}) km</div>'.format(
                *x["a"], *x["b"]) if self.xs_mode.value == "fixed" and x.get("a") else
            '<div class="cv-hint">Direction: 0° runs west → east, 90° south → north; the '
            'section is centred on the tracked storm (plus the offset).</div>')

    def _fill_times(self):
        n = int(self.rows.value or 1) * int(self.cols.value or 1)
        step, t0, nt = int(self.tstep.value or 1), self.v.t, len(self.run.times)
        self.times.value = [t for t in (t0 + step * k for k in range(n)) if t < nt]

    def _auto_titles(self):
        s = self.collect()
        if s["vary"] == "field":
            ts = [self.F[pf["field"]].label for pf in s["panel_fills"]]
        else:
            fill = next((lay for lay in s["layers"] if lay["type"] == "fill"), None)
            ts = [self.F[fill["field"]].label if fill else "" for _ in s["times"]]
        self.titles.value = "\n".join(ts)

    # ------------------------------------------------------------ start from
    def _default(self):
        """2 x 3 grid in time from the shown time: centred on the storm when there is a
        track, else the whole domain."""
        s = fg.default_spec(self.run, self.F, self.v.t)
        if not self.v.fixes:
            s["domain"] = dict(s["domain"], mode="full")
        return s

    def from_map(self):
        """A one-panel figure of what the map shows (field, levels, contours, winds,
        view), at the shown time."""
        v, F, t = self.v, self.F, self.v.t
        sp = v._map_spec()
        f = sp["fill"]
        fill = fg.layer_defaults("fill", F, f["var"], f["level"])
        fill.update(mode=f["mode"] if f["mode"] in LEVEL_MODES.values() else "height",
                    cmap=f["cmap"], reverse=f["rev"])
        try:  # the range the map shows
            a = F.plane(f["var"], t, fill["mode"], f["level"], storm=sp["fstorm"])
            lo, hi = F.auto_range(f["var"], a) if f["auto"] else (f["vmin"], f["vmax"])
            fill.update(vmin=round(float(lo), 6), vmax=round(float(hi), 6))
        except Exception:  # noqa: BLE001
            pass
        layers = [fill]
        for o in sp["ov"]:
            if not o["on"]:
                continue
            lay = fg.layer_defaults("contour", F, o["var"], o["level"])
            try:
                a = F.plane(o["var"], t, o["mode"], o["level"], storm=sp["fstorm"])
                lo, hi = F.auto_range(o["var"], a)
                lv = render.parse_levels(o["levels"], lo, hi)
                lay["levels"] = ", ".join(f"{x:g}" for x in lv)
            except Exception:  # noqa: BLE001
                pass
            lay.update(mode=o["mode"], color=_dark(o["color"]), lw=0.75 * float(o["width"]),
                       neg_dashed=o["negdash"])
            layers.append(lay)
        if sp["vec"]["on"]:
            lay = fg.layer_defaults("vectors", F)
            lay.update(z=sp["vec"]["level"], frame=sp["vec"]["frame"],
                       color=_dark(sp["vec"]["color"]))
            layers.append(lay)
        s = fg.default_spec(self.run, F, t)
        s.update(rows=1, cols=1, size=[5.0, 4.5], times=[t], time=t, layers=layers,
                 vary="time", kind="plan")
        s["domain"] = dict(s["domain"], mode="box", box=[float(x) for x in v.view])
        s["colorbar"] = dict(s["colorbar"], mode="each", orientation="vertical", shrink=0.9)
        s["axes"] = dict(s["axes"], ticklabels="all")
        self.set_spec(s)

    def from_xsec(self):
        v, F, t = self.v, self.F, self.v.t
        if len(v.xs_pts) != 2:
            self._msg("Draw a cross-section on the map first (Cross-section click mode).", True)
            return
        fill = fg.layer_defaults("fill", F, v.xs_fill.value)
        fill.update(cmap=v.xs_cmap.value, reverse=v.xs_rev.value)
        if not v.xs_auto.value:
            fill.update(vmin=float(v.xs_min.value), vmax=float(v.xs_max.value))
        layers = [fill]
        if v.xs_cont.value:
            lay = fg.layer_defaults("contour", F, v.xs_cont.value)
            lay.update(levels=v.xs_levels.value or "10, 20", color=_dark(v.xs_ccolor.value),
                       neg_dashed=v.xs_negdash.value)
            layers.append(lay)
        if v.xs_vecs.value:
            lay = fg.layer_defaults("vectors", F)
            lay.update(frame=v.xs_vframe.value, spacing=0.75, scale=400.0, width=0.0015)
            layers.append(lay)
        s = fg.default_spec(self.run, F, t)
        s.update(kind="xsec", rows=1, cols=1, size=[7.0, 3.5], times=[t], time=t,
                 layers=layers)
        s["xsec"] = dict(s["xsec"], mode="fixed", a=list(v.xs_pts[0]), b=list(v.xs_pts[1]),
                         ztop=float(v.xs_ztop.value))
        s["axes"] = dict(s["axes"], xlabel="distance (km)", ylabel="height (km)",
                         ticklabels="all")
        s["colorbar"] = dict(s["colorbar"], mode="each", orientation="vertical", shrink=0.9)
        self.set_spec(s)

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
            spec = self.collect()
        except Exception as e:  # noqa: BLE001
            self._status(f"Incomplete settings: {e}", True)
            return
        self.v.gen["fig"] += 1
        g = self.v.gen["fig"]
        self._status('<span class="busy">● Rendering…</span>')
        self.v.pools["fig"].submit(self._job, g, spec)

    def _context(self):
        run, fx = self.run, dict(self.v.fixes)
        centers = ser.track_centers(fx, len(run.times))
        return fx, centers

    def panel_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of the spec, from the cache where possible."""
        run, F = self.run, self.F
        fx, centers = self._context()
        track_sig = json.dumps(sorted((t, round(f["x"], 4), round(f["y"], 4))
                                      for t, f in fx.items()))
        data = {}
        n = fg.npanels(spec)
        for i in range(n):
            if cancelled and cancelled():
                return None
            t = fg.panel_time(spec, i)
            c = centers.get(t)
            key = fg.data_key(spec, i, c)
            if any(lay["type"] == "track" for lay in spec["layers"]):
                key += track_sig
            d = self.cache.get(key)
            if d is None:
                if progress:
                    progress(i, n)
                storm = self.v._field_storm(t)[0]
                d = fg.extract(run, F, spec, i, c, fx, storm)
                self.cache[key] = d
                while len(self.cache) > 60:
                    self.cache.popitem(last=False)
            else:
                self.cache.move_to_end(key)
            data[i] = d
        return data

    def _job(self, g, spec):
        t0 = _time.time()

        def cancelled():
            return g != self.v.gen["fig"]

        def progress(i, n):
            self.v._schedule(partial(self._status, f'<span class="busy">● Reading panel '
                                                   f'{i + 1}/{n}…</span>'))

        try:
            data = self.panel_data(spec, progress, cancelled)
            if data is None:
                return
            fig = figdraw.draw(spec, data)
            dpi = min(float(spec["export"]["dpi"]), 1100.0 / max(spec["size"][0], 0.5))
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor(),
                        bbox_inches="tight" if spec["export"].get("tight", True) else None)
            png = base64.b64encode(buf.getvalue()).decode()
            miss = [i for i, d in data.items() if d.get("missing")]
            note = (f"{len(data)} panel{'s' if len(data) != 1 else ''} · "
                    f"{spec['size'][0]:g} × {spec['size'][1]:g} in · preview at {dpi:.0f} dpi"
                    f" · {_time.time() - t0:.1f} s")
            if miss:
                note += (f" · no data in panel{'s' if len(miss) > 1 else ''} "
                         + ", ".join(figdraw.panel_letter(i, "{a}") for i in miss))
                storm = (spec["kind"] == "plan" and spec["domain"]["mode"] == "storm") or \
                    (spec["kind"] == "xsec" and spec["xsec"]["mode"] == "storm")
                if storm and not self.v.fixes:
                    note += (" · storm-centred panels need a track: follow the storm in "
                             "the <b>Track</b> tab (Map), or pick another area in "
                             "<b>Region</b>")
            self.v._schedule(partial(self._apply, g, png, note))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.v._schedule(partial(self._status, f"Could not draw: {e}", True))

    def _apply(self, g, png, note):
        if g != self.v.gen["fig"]:
            return
        self.image.object = (f'<img src="data:image/png;base64,{png}" style="max-width:100%;'
                             f'height:auto;display:block;margin:auto;'
                             f'box-shadow:0 4px 18px rgba(0,0,0,.5)">')
        self._status(note)

    def _status(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.status.object = f'<div class="cv-status"{col}>{html}</div>'

    def _msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.msg.object = f'<div class="cv-status"{col}>{html}</div>'

    # ------------------------------------------------------------ export
    def _set_dl_name(self):
        self.dl.filename = f"{os.path.basename(self.path.value) or 'figure'}.{self.fmt.value}"

    def _save(self, bundle):
        spec = self.collect()
        self._msg('<span class="busy">● Saving…</span>')
        self.v.pools["fig"].submit(self._save_job, spec, bundle)

    def _save_job(self, spec, bundle):
        try:
            data = self.panel_data(spec)
            base = self.path.value
            if bundle:
                out = fg.save_bundle(spec, data, base, self.run)
                html = "Saved " + ", ".join(f"<code>{p}</code>" for p in out.values())
            else:
                base = os.path.splitext(base)[0] if base.lower().endswith(
                    "." + spec["export"]["format"]) else base
                p = fg.save_image(spec, data, f"{base}.{spec['export']['format']}")
                html = f"Saved <code>{p}</code>"
            self.v._schedule(partial(self._msg, html))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.v._schedule(partial(self._msg, f"Could not save: {e}", True))

    def _download(self):
        spec = self.collect()
        data = self.panel_data(spec)
        fig = figdraw.draw(spec, data)
        buf = io.BytesIO()
        fig.savefig(buf, format=spec["export"]["format"], dpi=spec["export"]["dpi"],
                    bbox_inches="tight" if spec["export"].get("tight", True) else None,
                    facecolor=fig.get_facecolor())
        buf.seek(0)
        return buf

    def _load_spec(self):
        path = self.spec_path.value.strip()
        try:
            spec = fg.load_spec(path)
        except (OSError, ValueError) as e:
            self._msg(f"Could not load <code>{path}</code>: {e}", True)
            return
        base = fg.default_spec(self.run, self.F, self.v.t)
        for k, val in spec.items():  # keys added in later versions keep their defaults
            base[k] = dict(base[k], **val) if isinstance(base.get(k), dict) else val
        bad = [lay.get("field") for lay in base["layers"]
               if lay.get("field") and lay["field"] not in self.F]
        if bad:
            self._msg("This run has no field " + ", ".join(bad), True)
            return
        nt = len(self.run.times)
        base["times"] = [t for t in base["times"] if t < nt]
        base["time"] = min(int(base["time"]), nt - 1)
        self.set_spec(base)
        self._msg(f"Loaded <code>{path}</code>")


def _dark(color):
    """Light colours chosen for the dark map turn black on a white figure."""
    try:
        r, g, b = (int(color.lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))
    except (ValueError, AttributeError):
        return "#000000"
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 180 else color
