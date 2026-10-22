"""Figure workspace: build a publication figure from panels and layers (from one run or
several, e.g. tornadic vs non-tornadic), preview it at its final size, and export the
image, a stand-alone script, the data and the spec.

The editor has five tabs: Panels (what the grid shows: kind, size, times, titles,
area, runs), Layers (what each panel draws), Style (fonts, axes, labels, colorbar,
legend, spacing), Annotate and Export.  Saving sits above the preview."""

import base64
import io
import json
import os
import struct
import time as _time
import traceback
from collections import OrderedDict
from functools import partial

import numpy as np
import panel as pn
from matplotlib import font_manager
from matplotlib.colors import to_hex

from . import config, figdraw, figure as fg, registry, render, series as ser, track as trk
from .fields import CMAPS, Fields
from .run import CM1Run, FileBusy, MissingAtTime
from .theme import GRID, PANEL, RAISED, TEXT

PYART_CMAPS = ["HomeyerRainbow", "ChaseSpectral", "NWSRef", "NWSVel", "LangRainbow12",
               "SpectralExtended", "Carbone42", "Theodore16", "BuDRd18"]
FIG_CMAPS = list(dict.fromkeys(PYART_CMAPS + CMAPS + [
    "Greys", "gray_r", "Blues", "Reds", "Purples", "PuOr", "RdBu", "bwr", "jet"]))
LOCS = ["upper left", "upper right", "lower left", "lower right", "upper center",
        "lower center", "center left", "center right"]
LABEL_LOCS = LOCS + ["above left", "above right"]  # panel letters, times, run names
LEVEL_MODES = {"Height (km AGL)": "height", "Model level (k)": "level",
               "Column max": "colmax", "Column min": "colmin"}
FONT_CHOICES = ["sans-serif", "serif", "DejaVu Sans", "Arial", "Helvetica", "Liberation Sans",
                "Nimbus Sans", "Source Sans Pro", "Roboto", "Open Sans", "Noto Sans",
                "DejaVu Serif", "Times New Roman", "Liberation Serif", "Nimbus Roman",
                "STIXGeneral", "Noto Serif"]


def _installed_fonts():
    """FONT_CHOICES matplotlib finds on this machine (the generic families always)."""
    try:
        have = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:  # noqa: BLE001
        have = set()
    return [f for f in FONT_CHOICES if f in ("sans-serif", "serif") or f in have]


FONTS = _installed_fonts()
MATH_FONTS = {"DejaVu Sans": "dejavusans", "Like the text font": "custom",
              "STIX Sans": "stixsans", "STIX (Times-like)": "stix",
              "Computer Modern (LaTeX)": "cm"}
FRAMES = {"Ground-relative": "ground", "Grid-relative": "grid", "Storm-relative": "storm"}
VARY = {"Time (one run)": "time", "Field (one run, one time)": "field",
        "Run × time grid": "grid", "Each panel: own run & time": "custom"}
LETTERS = {"a": "{a}", "(a)": "({a})", "a)": "{a})", "A": "{A}", "(A)": "({A})"}
TYPE_LABEL = {"fill": "Fill", "contour": "Contours", "shade": "Shading", "vectors": "Vectors",
              "track": "Storm track", "line": "Section line"}
EXTEND = {"None": "neither", "Max end": "max", "Min end": "min", "Both ends": "both"}
TICKDIR = {"Out": "out", "In": "in", "Across": "inout"}
CB_MODES = {"One for the figure": "shared", "One per row": "row", "One per column": "col",
            "One per panel": "each", "None": "none"}
CB_LOCS = {"Below": "bottom", "Right": "right", "Above": "top", "Left": "left"}
SIZE_PRESETS = {"Custom": "", "3.25 in wide (one journal column)": "3.25",
                "5 in wide": "5", "6.5 in wide (full page width)": "6.5", "7.5 in wide": "7.5",
                "Slide, 13.3 × 7.5 in": "13.333x7.5"}
NONE = -1  # an empty grid cell in the panel times
CARD = {"border": f"1px solid {GRID}", "border-radius": "8px", "padding": "2px 6px 6px 6px",
        "margin": "4px 0"}
SECTION = dict(sizing_mode="stretch_width", header_background=RAISED,
               active_header_background=RAISED, header_color=TEXT, margin=(4, 0),
               styles={"background": PANEL, "border": f"1px solid {GRID}",
                       "border-radius": "8px"})
GHOST = (".bk-btn { border-color: transparent !important; background-color: transparent "
         "!important; }")


def _hex(c, default="#000000"):
    try:
        return to_hex(c)
    except (ValueError, TypeError):
        return default


def _f(name, value, width=90, **kw):
    return pn.widgets.FloatInput(name=name, value=value, width=width, **kw)


def _auto(name, value=None, **kw):
    """A number that may be left blank (automatic)."""
    v = None if value in (None, "", 0) else float(value)
    return pn.widgets.FloatInput(name=name, value=v, placeholder="auto", width=90, **kw)


def _num(v):
    """A blank-able number for the spec (None when blank)."""
    return None if v in (None, "") else float(v)


def _row(*objs):
    return pn.FlexBox(*objs, flex_wrap="wrap", align_items="flex-end", gap="0 6px",
                      sizing_mode="stretch_width")


def _grid(*objs, n=3):
    """Widgets in n equal columns (a CSS grid), each filling its cell; (widget, k)
    spans k columns.  Everything sits on the cell's bottom line, so checkboxes and
    buttons line up with the input boxes beside them; hidden widgets leave no gap."""
    items = []
    for o in objs:
        o, span = o if isinstance(o, tuple) else (o, 1)
        o.width = None
        o.sizing_mode = "stretch_width"
        st = {"align-self": "end"}
        if span > 1:
            st["grid-column"] = f"span {span}"
        o.styles = dict(o.styles or {}, **st)
        if isinstance(o, pn.widgets.Checkbox):
            o.margin = (5, 6, 12, 6)
        items.append(o)
    return pn.Column(*items, sizing_mode="stretch_width", margin=0, styles={
        "display": "grid", "grid-template-columns": f"repeat({n}, minmax(0, 1fr))",
        "column-gap": "2px"})


def _section(title, *objs, collapsed=False):
    """A collapsible section of the editor."""
    return pn.Card(*objs, title=title, collapsed=collapsed, **SECTION)


def _hint(text, margin=(4, 4, 2, 4)):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=margin,
                        sizing_mode="stretch_width")


def _when(chk, *objs):
    """objs are shown while the checkbox chk is ticked."""
    def show(*e):
        for o in objs:
            o.visible = bool(chk.value)
    chk.param.watch(show, "value")
    show()


def _fold(head, body, collapsed=False):
    """A card: a header row (a chevron that shows / hides the body, then `head`) over
    `body`.  Returns (card, body column)."""
    col = pn.Column(*body, margin=0, sizing_mode="stretch_width", visible=not collapsed)
    chev = pn.widgets.Button(name="", icon="chevron-right" if collapsed else "chevron-down",
                             width=28, height=28, margin=(2, 0), button_type="light",
                             description="Show / hide the settings", stylesheets=[GHOST])

    def flip(e):
        col.visible = not col.visible
        chev.icon = "chevron-down" if col.visible else "chevron-right"

    chev.on_click(flip)
    card = pn.Column(pn.Row(chev, *head, margin=0, sizing_mode="stretch_width"), col,
                     styles=CARD, sizing_mode="stretch_width", margin=(2, 0))
    return card, col


class LayerCard:
    """Widgets of one layer (a card that folds away); collect() -> the layer dict."""

    def __init__(self, ed, lay, collapsed=False):
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
            w["field"] = pn.widgets.Select(name="Field", groups=g, value=lay["field"])
            w["mode"] = pn.widgets.Select(name="Level", options=LEVEL_MODES,
                                          value=lay.get("mode", "height"))
            w["z"] = _f("Height (km)", lay.get("z", 1.0), step=0.25)
        if t == "fill":
            w["cmap"] = pn.widgets.Select(name="Colormap", options=FIG_CMAPS,
                                          value=lay["cmap"] if lay["cmap"] in FIG_CMAPS
                                          else "viridis")
            w["reverse"] = pn.widgets.Checkbox(name="Reverse", value=lay.get("reverse", False))
            w["white_first"] = pn.widgets.Checkbox(
                name="Start from white", value=lay.get("white_first", False))
            w["vmin"] = _f("Min", lay["vmin"])
            w["vmax"] = _f("Max", lay["vmax"])
            w["nlevels"] = pn.widgets.IntInput(name="Color steps (0: smooth)",
                                               value=int(lay.get("nlevels") or 0), start=0,
                                               end=60)
            w["scale"] = pn.widgets.Select(name="Scale", options={"Linear": "linear",
                                                                  "Logarithmic": "log"},
                                           value=lay.get("scale", "linear"))
            w["extend"] = pn.widgets.Select(name="Colorbar arrows", options=EXTEND,
                                            value=lay.get("extend", "neither"))
            w["alpha"] = _f("Opacity (0–1)", float(lay.get("alpha", 1.0)), step=0.1, start=0.0,
                            end=1.0)
            w["style"] = pn.widgets.Select(name="Draw as", options={
                "Grid cells": "mesh", "Filled contours": "contourf"},
                value=lay.get("style", "mesh"))
            w["mask_below"] = pn.widgets.TextInput(
                name="Blank where ≤", value="" if lay.get("mask_below") is None
                else f"{lay['mask_below']:g}", placeholder="off")
            w["cbar_label"] = pn.widgets.TextInput(
                name="Colorbar label (blank: units)", value=lay.get("cbar_label", "") or "",
                placeholder=lay.get("units", ""))
            w["field"].param.watch(self._on_fill_field, "value")
        if t == "contour":
            w["levels"] = pn.widgets.TextInput(name="Levels (e.g. 10, 20 or -6:6:2)",
                                               value=str(lay["levels"]))
            w["neg_dashed"] = pn.widgets.Checkbox(name="Dash negative",
                                                  value=lay.get("neg_dashed", True))
            w["clabel"] = pn.widgets.Checkbox(name="Label the lines",
                                              value=lay.get("clabel", False))
            w["clabel_size"] = _f("Label size (pt)", float(lay.get("clabel_size") or 8.0),
                                  step=1, start=4)
            w["clabel_fmt"] = pn.widgets.TextInput(name="Label format",
                                                   value=lay.get("clabel_fmt") or "%g",
                                                   placeholder="%g")
        if t == "shade":
            w["threshold"] = _f("Threshold", lay["threshold"])
            w["above"] = pn.widgets.Select(name="Shade", options={"Above": True, "Below": False},
                                           value=lay.get("above", True))
            w["alpha"] = _f("Opacity (0–1)", lay.get("alpha", 0.6), step=0.1, start=0, end=1)
            w["outline_on"] = pn.widgets.Checkbox(name="Outline", value=bool(lay.get("outline")))
            w["outline"] = pn.widgets.ColorPicker(name="Outline color",
                                                  value=_hex(lay.get("outline") or "magenta"))
        if t == "vectors":
            w["style"] = pn.widgets.Select(name="Draw as", options={
                "Arrows": "arrows", "Streamlines": "streamlines"},
                value=lay.get("style", "arrows"))
            w["frame"] = pn.widgets.Select(name="Winds", options=FRAMES,
                                           value=lay.get("frame", "ground"))
            w["z"] = _f("Height (km)", lay.get("z", 0.0), step=0.25)
            w["spacing"] = _f("Spacing (km)", lay.get("spacing", 2.0), step=0.25)
            w["zspacing"] = _f("Vertical spacing (km)", lay.get("zspacing", 0.5), step=0.1)
            w["scale"] = _f("Scale (larger: shorter)", lay.get("scale", 250.0), step=25)
            w["width"] = _f("Arrow width", lay.get("width", 0.002), step=0.0005)
            w["key"] = _f("Key arrow (m/s, 0: none)", lay.get("key", 0.0), step=5)
            w["density"] = _f("Density", float(lay.get("density", 1.5)), step=0.25, start=0.25)
            w["slw"] = _f("Line width", float(lay.get("slw", 0.8)), step=0.1)
            w["arrowsize"] = _f("Arrow size", float(lay.get("arrowsize", 1.0)), step=0.25)
        if t in ("contour", "shade", "vectors", "track", "line"):
            w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(lay.get("color", "k")))
        if t in ("contour", "shade", "track", "line"):
            w["lw"] = _f("Outline width" if t == "shade" else "Line width", lay.get("lw", 1.0),
                         step=0.25)
        if t == "track":
            w["ls"] = pn.widgets.Select(name="Style", options={"solid": "-", "dashed": "--",
                                                               "dotted": ":"},
                                        value=lay.get("ls", "-"))
            w["marker"] = pn.widgets.Checkbox(name="Dot at the panel time",
                                              value=lay.get("marker", True))
        if t == "line":
            w["labels"] = pn.widgets.TextInput(name="End labels", value=lay.get("labels", ""))
        if t in ("contour", "shade", "track", "line"):
            w["legend"] = pn.widgets.TextInput(name="Legend entry (blank: none)",
                                               value=lay.get("legend", ""),
                                               placeholder="e.g. w = 10, 20 m s⁻¹")
        w["panels"] = pn.widgets.TextInput(
            name="In panels (blank: all)", value=_panels_text(lay.get("panels")),
            placeholder="e.g. a, c or 1-3",
            description="Draw this layer only in these panels (letters or numbers)")
        for k, x in w.items():
            if k != "field" or t != "fill":
                x.param.watch(lambda e: self._changed(), "value")
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self._set_title()
        self.panel, self.body = _fold([w["on"], self.title, pn.Spacer(), self.up, self.down,
                                       self.rm], self._layout(), collapsed)
        self.show(ed.kind.value)

    def _layout(self):
        w, t = self.w, self.type
        if t == "fill":
            return [_grid((w["field"], 2), w["mode"], w["z"], w["style"], w["mask_below"]),
                    _grid(w["cmap"], w["reverse"], w["white_first"], w["vmin"], w["vmax"],
                          w["nlevels"], w["scale"], w["extend"], w["alpha"],
                          (w["cbar_label"], 3), (w["panels"], 3))]
        if t == "contour":
            return [_grid((w["field"], 2), w["mode"], w["z"], (w["levels"], 2), w["color"],
                          w["lw"], w["neg_dashed"], w["clabel"], w["clabel_size"],
                          w["clabel_fmt"], (w["legend"], 3), (w["panels"], 3))]
        if t == "shade":
            return [_grid((w["field"], 2), w["mode"], w["z"], w["threshold"], w["above"],
                          w["color"], w["alpha"], w["outline_on"], w["outline"], w["lw"],
                          (w["legend"], 3), (w["panels"], 3))]
        if t == "vectors":
            return [_grid(w["style"], w["frame"], w["color"], w["z"], w["spacing"],
                          w["zspacing"], w["scale"], w["width"], w["key"], w["density"],
                          w["slw"], w["arrowsize"], (w["panels"], 3))]
        if t == "track":
            return [_grid(w["color"], w["lw"], w["ls"], w["marker"], (w["legend"], 2),
                          (w["panels"], 3))]
        return [_grid(w["color"], w["lw"], w["labels"], (w["legend"], 3), (w["panels"], 3))]

    def show(self, kind):
        """Only the settings that matter for this layer in `kind` panels (a section
        samples the fields along the section, at every height)."""
        w, t, xs = self.w, self.type, kind == "xsec"
        if "mode" in w:
            m = w["mode"].value
            w["mode"].visible = not xs
            w["z"].visible = not xs and m in ("height", "level")
            w["z"].name = "Model level (k)" if m == "level" else "Height (km)"
        if t == "vectors":
            st = w["style"].value == "streamlines"
            for k in ("density", "slw", "arrowsize"):
                w[k].visible = st
            for k in ("scale", "width", "key"):
                w[k].visible = not st
            w["z"].visible = not xs
            w["spacing"].visible = not st
            w["spacing"].name = "Spacing along (km)" if xs else "Spacing (km)"
            w["zspacing"].visible = xs and not st
        if t == "shade":
            w["outline"].visible = w["lw"].visible = w["outline_on"].value
        if t == "contour":
            w["clabel_size"].visible = w["clabel_fmt"].visible = w["clabel"].value
        if t == "fill":
            w["white_first"].visible = True

    def _changed(self):
        self.show(self.ed.kind.value)
        self._set_title()
        self.ed.request()

    def _set_title(self):
        t, w = self.type, self.w
        sub = ""
        if "field" in w:
            d = self.ed.F[w["field"].value]
            sub = f" · {d.label}"
            m = w["mode"].value
            if self.ed.kind.value != "xsec":
                z = w["z"].value or 0
                sub += {"height": f" · {z:g} km", "level": f" · k = {z:g}",
                        "colmax": " · column max", "colmin": " · column min"}.get(m, "")
        elif t == "vectors":
            sub = " · streamlines" if w["style"].value == "streamlines" else " · arrows"
        try:
            only = _panels_parse(w["panels"].value)
        except ValueError:  # (collect() reports it)
            only = []
        if only:
            sub += " · panel" + ("s " if len(only) > 1 else " ") + ", ".join(
                figdraw.panel_letter(i, "{a}") for i in only)
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
            self.w["cbar_label"].placeholder = d["units"]
        finally:
            self.ed._hold = False
        self._changed()

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
            lay["alpha"] = float(w["alpha"].value if w["alpha"].value is not None else 1.0)
        if self.type == "shade":
            lay["outline"] = w["outline"].value if w["outline_on"].value else ""
        lay["panels"] = _panels_parse(w["panels"].value)
        return lay


def _panels_parse(text):
    """'a, c' / '1, 3' / 'b-d' / '2-4' -> sorted 0-based panel indices ([]: every
    panel).  Raises ValueError on anything else."""
    out = set()
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip().lower()
        if not part:
            continue
        a, _, b = part.partition("-")
        ends = []
        for v in (a.strip(), (b or a).strip()):
            if v.isdigit() and int(v) > 0:
                ends.append(int(v) - 1)
            elif len(v) == 1 and v.isalpha():
                ends.append(ord(v) - ord("a"))
            else:
                raise ValueError(f"panels: {part!r} is not a panel letter or number")
        out.update(range(min(ends), max(ends) + 1))
    return sorted(out)


def _panels_text(panels):
    return ", ".join(figdraw.panel_letter(int(i), "{a}") for i in panels or [])


class FigureEditor:
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

    # ------------------------------------------------------------ runs
    def open_run(self, path):
        """(CM1Run, Fields) of the run in `path` (the viewer's own run, or one opened
        through the viewer's registry so its cache is shared)."""
        path = os.path.abspath(path)
        if path == self.run.path:
            return self.run, self.F
        reg = getattr(self.v, "reg", None)
        if reg is not None:
            return reg.get(path)
        if path not in self._opened:
            r = CM1Run(path, workers=self.run.workers, cache=self.run._vc)
            self._opened[path] = (r, Fields(r))
        return self._opened[path]

    def run_fixes(self, entry, run):
        """Track fixes {t: fix} of a spec["runs"] entry ({} without a track)."""
        tr = entry.get("track") or ""
        if tr == "viewer":
            return dict(self.v.fixes) if run is self.run else {}
        if not tr:
            return {}
        path = os.path.abspath(os.path.expanduser(os.path.expandvars(tr)))
        try:
            mt = os.path.getmtime(path)
            hit = self._tracks.get(path)
            if hit is None or hit[0] != mt or hit[1] != run.path:
                self._tracks[path] = (mt, run.path, trk.load(run, path))
            self._track_err.pop(path, None)
            return self._tracks[path][2]
        except Exception as e:  # noqa: BLE001
            self._track_err[path] = str(e)
            return {}

    def _build_runs(self, runs):
        self.run_rows = [self._run_row(e) for e in runs]
        self._show_runs()

    def _run_row(self, e):
        own = os.path.abspath(e["path"]) == self.run.path
        r = dict(path=os.path.abspath(e["path"]))
        r["label"] = pn.widgets.TextInput(name="Label", value=e.get("label", ""), width=130)
        r["tab"] = pn.widgets.Checkbox(name="Viewer's track", value=e.get("track") == "viewer",
                                       visible=own, margin=(5, 6, 12, 6))
        r["track"] = pn.widgets.TextInput(
            name="Track file (blank: none)", sizing_mode="stretch_width", min_width=200,
            value="" if e.get("track") == "viewer" else e.get("track", ""),
            disabled=e.get("track") == "viewer", placeholder="storm_tracks/<run>.csv")
        r["rm"] = pn.widgets.Button(name="✕", description="Remove the run", width=32, height=28,
                                    margin=(2, 1), button_type="default", button_style="outline")
        r["info"] = pn.pane.HTML(margin=(0, 4))
        r["head"] = pn.pane.HTML(margin=(6, 4, 0, 4))

        def on_label(ev):
            self._refresh_run_names()
            self.request()

        def on_track(ev):
            r["track"].disabled = r["tab"].value
            self._run_info(r)
            self.request()

        r["label"].param.watch(on_label, "value")
        r["tab"].param.watch(on_track, "value")
        r["track"].param.watch(on_track, "value")
        r["rm"].on_click(lambda ev: self._remove_run(r))
        r["panel"] = pn.Column(
            pn.Row(r["head"], pn.Spacer(), r["rm"], margin=0, sizing_mode="stretch_width"),
            _row(r["label"], r["tab"], r["track"]), r["info"], styles=CARD,
            sizing_mode="stretch_width", margin=(2, 0))
        self._run_info(r)
        return r

    def _run_entry(self, r):
        tr = "viewer" if r["tab"].visible and r["tab"].value else r["track"].value.strip()
        return dict(path=r["path"], label=r["label"].value, track=tr)

    def _runs_collect(self):
        return [self._run_entry(r) for r in self.run_rows]

    def _run_info(self, r):
        k = self.run_rows.index(r) if r in self.run_rows else len(self.run_rows)
        own = " (this viewer's run)" if r["path"] == self.run.path else ""
        r["head"].object = (f'<b>{k + 1}.</b> <code>{r["path"]}</code>'
                            f'<span class="cv-hint">{own}</span>')
        try:
            run, _ = self.open_run(r["path"])
        except Exception as e:  # noqa: BLE001
            r["info"].object = f'<div class="cv-status" style="color:#f87171">{e}</div>'
            return
        e = self._run_entry(r)
        fx = self.run_fixes(e, run)
        tr = e["track"]
        path = os.path.abspath(os.path.expanduser(tr)) if tr and tr != "viewer" else ""
        if path in self._track_err:
            tnote = f'<span style="color:#f87171">track: {self._track_err[path]}</span>'
        elif tr:
            tnote = f"track: {len(fx)} fix{'es' if len(fx) != 1 else ''}"
            if fx:
                ts = sorted(fx)
                tnote += f" ({run.times[ts[0]] / 60:g}–{run.times[ts[-1]] / 60:g} min)"
        else:
            tnote = "no track (storm-centred panels stay empty)"
        r["info"].object = (
            f'<div class="cv-hint">{len(run.times)} outputs, {run.times[0] / 60:g}–'
            f'{run.times[-1] / 60:g} min · {run.ni}×{run.nj}×{run.nk}, dx {run.dx:g} m · '
            f'{tnote}</div>')

    def _show_runs(self):
        for r in self.run_rows:
            r["rm"].visible = len(self.run_rows) > 1
            self._run_info(r)
        self.runs_box.objects = [r["panel"] for r in self.run_rows]
        self._refresh_run_names()
        self._sync_save_path()
        have = {r["path"] for r in self.run_rows}
        opts = {}
        for p in registry.sibling_runs(self.run.path) + registry.recent_runs():
            p = os.path.abspath(p)
            if p not in have:
                opts.setdefault("/".join(p.rstrip("/").split("/")[-2:]), p)
        self.add_sel.options = {"": ""} | opts

    def _run_names(self):
        return {f"{k + 1}. {r['label'].value or os.path.basename(r['path'])}": k
                for k, r in enumerate(self.run_rows)}

    def _refresh_run_names(self):
        names = self._run_names()
        hold, self._hold = self._hold, True
        try:
            v = self.run_sel.value
            self.run_sel.options = names
            self.run_sel.value = v if v in names.values() else 0
            for r in self.pc_rows:
                v = r["run"].value
                r["run"].options = names
                r["run"].value = v if v in names.values() else 0
            for c in self.snd_cards:
                v = c.w["run"].value
                c.w["run"].options = names
                c.w["run"].value = v if v in names.values() else 0
            for c in self.ser_cards:
                v = [k for k in c.w["runs"].value if k in names.values()]
                c.w["runs"].options = names
                c.w["runs"].value = v
        finally:
            self._hold = hold
        self.run_sel.visible = len(names) > 1 and self.vary.value in ("time", "field")

    def _add_run(self):
        path = os.path.abspath(os.path.expanduser(self.add_path.value.strip()))
        if not registry.is_run(path):
            self._runs_msg(f"No cm1out_*.nc files in <code>{path}</code>", True)
            return
        if path in {r["path"] for r in self.run_rows}:
            self._runs_msg("That run is already in the list.", True)
            return
        self._runs_msg('<span class="busy">● Opening…</span>')
        try:
            run, _ = self.open_run(path)
        except Exception as e:  # noqa: BLE001
            self._runs_msg(f"Could not open <code>{path}</code>: {e}", True)
            return
        self.run_rows.append(self._run_row(fg.run_entry(run)))
        self._show_runs()
        self.add_path.value = ""
        self._runs_msg(f"Added <code>{path}</code>")
        if self.vary.value == "time":  # a second run: compare them side by side
            self.vary.value = "grid"
        else:
            self._on_vary()

    def _remove_run(self, r):
        k = self.run_rows.index(r)
        self.run_rows.remove(r)
        self._hold = True
        try:
            if self.run_sel.value is not None and self.run_sel.value >= k:
                self.run_sel.value = max(0, self.run_sel.value - (self.run_sel.value > k))
            keep = []
            for p in self.pc_rows:
                if p["run"].value != k:
                    if p["run"].value > k:
                        p["run"].value -= 1
                    keep.append(p)
            self.pc_rows = keep
        finally:
            self._hold = False
        self._show_runs()
        self._on_vary()

    def _runs_msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.runs_msg.object = f'<div class="cv-status"{col}>{html}</div>'

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

    # ------------------------------------------------------------ start from
    def _default(self):
        """2 x 3 grid in time from the shown time: centred on the storm when there is a
        track, else the whole domain."""
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        if not self.v.fixes:
            s["domain"] = dict(s["domain"], mode="full")
        return s

    def _own_track(self):
        """Track of this run in a new figure: the Track tab's when it has one, else a
        storm_tracks file next to the run (the Track tab when there is neither)."""
        return "viewer" if self.v.fixes else (fg.find_track(self.run.path) or "viewer")

    def _keep_runs(self, s):
        """A new spec of this run keeps the runs already added (this run selected)."""
        s["runs"][0]["track"] = self._own_track()
        if self.run_rows:
            runs = self._runs_collect()
            paths = [r["path"] for r in runs]
            if self.run.path not in paths:
                runs.insert(0, fg.run_entry(self.run, "viewer"))
                paths.insert(0, self.run.path)
            s["runs"], s["run"] = runs, paths.index(self.run.path)
        return s

    def _times(self, s, times, t):
        s.update(times=list(times), time=t,
                 times_s=[float(self.run.times[k]) for k in times],
                 time_s=float(self.run.times[t]))
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
        s = self._keep_runs(fg.default_spec(self.run, F, t))
        self._times(s, [t], t)
        s.update(rows=1, cols=1, size=[5.0, 4.5], layers=layers, vary="time", kind="plan")
        s["domain"] = dict(s["domain"], mode="box", box=[float(x) for x in v.view])
        s["colorbar"] = dict(s["colorbar"], mode="each", orientation="vertical", shrink=0.9)
        s["axes"] = dict(s["axes"], ticklabels="all")
        self.set_spec(s)

    def from_xsec(self):
        v, F, t = self.v, self.F, self.v.t
        if len(v.xs_pts) != 2:
            self._msg("Draw a cross-section on the map first (Section tool).", True)
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
        s = self._keep_runs(fg.default_spec(self.run, F, t))
        self._times(s, [t], t)
        s.update(kind="xsec", rows=1, cols=1, size=[7.0, 3.5], layers=layers, vary="time")
        s["xsec"] = dict(s["xsec"], mode="fixed", a=list(v.xs_pts[0]), b=list(v.xs_pts[1]),
                         ztop=float(v.xs_ztop.value))
        s["axes"] = dict(s["axes"], xlabel="distance (km)", ylabel="height (km)",
                         ticklabels="all")
        s["colorbar"] = dict(s["colorbar"], mode="each", orientation="vertical", shrink=0.9)
        self.set_spec(s)

    # ------------------------------------------------------------ series cards
    def _ser_card(self, e):
        c = SeriesCard(self, e)
        c.up.on_click(lambda ev: self._move_ser(c, -1))
        c.down.on_click(lambda ev: self._move_ser(c, 1))
        c.rm.on_click(lambda ev: self._remove_ser(c))
        return c

    def _show_series(self):
        for c in self.ser_cards:
            c.show(self.kind.value)
        self.ser_box.objects = [c.panel for c in self.ser_cards] or [pn.pane.HTML(
            '<div class="cv-empty">No series: add one from the Series tool above, or a new '
            'one.</div>')]
        ss = getattr(self.v, "series", {}) or {}
        self.ser_from.options = {"": ""} | {v["label"]: k for k, v in ss.items()}

    def _series_changed(self):
        self._show_series()
        if self.kind.value == "th":
            self._th_grid()
        self._fit_grid()
        self.request()

    def _move_ser(self, c, d):
        i = self.ser_cards.index(c)
        j = min(max(i + d, 0), len(self.ser_cards) - 1)
        self.ser_cards[i], self.ser_cards[j] = self.ser_cards[j], self.ser_cards[i]
        self._series_changed()

    def _remove_ser(self, c):
        self.ser_cards.remove(c)
        self._series_changed()

    def _tab_series(self, key):
        """A spec["series"] entry of a series of the Series tab."""
        s = self.v.series[key]
        r = dict(s["recipe"])
        e = fg.series_defaults(self.F, r, len(self.ser_cards))
        e["panel"] = 0
        return e

    def _add_series_from_tab(self):
        key = self.ser_from.value
        if not key or key not in getattr(self.v, "series", {}):
            return
        self.ser_cards.append(self._ser_card(self._tab_series(key)))
        self._series_changed()

    def _new_recipe(self):
        """A recipe for a new series: max w in 0–10 km near the storm (whole domain
        without a track), as for updraft time-height plots."""
        f = "winterp" if "winterp" in self.F else next(iter(self.F.defs))
        track = bool(self.v.fixes) or any(r.get("track") for r in self._runs_collect())
        return ser.normalize(dict(field=f, vmode="layer", z0=0.0, z1=10.0,
                                  region="track" if track else "domain", radius=5.0,
                                  offset=(0.0, 0.0), reduce="max"))

    def _add_series(self):
        e = fg.series_defaults(self.F, self._new_recipe(), len(self.ser_cards))
        if self.kind.value == "line":
            e["panel"] = len({c.collect()["panel"] for c in self.ser_cards})
        self.ser_cards.append(self._ser_card(e))
        self._series_changed()

    def _fit_grid(self, reset=False):
        """Time-series / sounding figures: enough grid cells for the highest panel
        number of the cards and no empty rows (reset: a column of up to 3, else 2
        columns)."""
        kind = self.kind.value
        if kind not in ("line", "sounding"):
            return
        cards = self.ser_cards if kind == "line" else self.snd_cards
        n = 1 + max([max(0, int(c.w["panel"].value or 1) - 1) for c in cards] or [0])
        r, c = int(self.rows.value or 1), int(self.cols.value or 1)
        if reset:
            r, c = (n, 1) if n <= 3 else ((n + 1) // 2, 2)
        else:
            c = min(c, n)
            r = -(-n // c)
        if (r, c) != (self.rows.value, self.cols.value):
            hold, self._hold = self._hold, True
            try:
                self.rows.value, self.cols.value = r, c
            finally:
                self._hold = hold
            self._fit_size()
            self._build_titles()

    _auto_size = False  # the figure size follows the grid until it is set by hand

    def _fit_size(self):
        """A size for the grid (plan views and sections: the height for the width)."""
        kind, r, c = self.kind.value, int(self.rows.value or 1), int(self.cols.value or 1)
        if not self._auto_size:
            return
        if kind in ("plan", "xsec"):
            self._follow_size()
            return
        if kind == "th":
            w, h = 4.5 * c + 1.0, 2.8 * r + 0.6
        elif kind == "sounding":
            w, h = 5.0 * c + 0.5, 5.0 * r
        else:
            w, h = (7.0 if c == 1 else 6.0 * c), 3.0 * r + 0.5
        hold, self._hold = self._hold, True
        try:
            self.width.value, self.height.value = round(min(16.0, w), 2), round(min(16.0, h), 2)
            self.size_preset.value = ""
        finally:
            self._hold = hold

    def _size_by_hand(self):
        if not self._hold:
            self._auto_size = False
            hold, self._hold = self._hold, True
            try:
                self.size_preset.value = ""
            finally:
                self._hold = hold

    def _th_grid(self):
        """Time-height grid: a row (column) per series and a column (row) per run."""
        ne, nr = max(1, len(self.ser_cards)), max(1, len(self.run_rows))
        r, c = (ne, nr) if self.runs_as.value == "cols" else (nr, ne)
        if (self.rows.value, self.cols.value) != (r, c):
            hold, self._hold = self._hold, True
            try:
                self.rows.value, self.cols.value = r, c
            finally:
                self._hold = hold
            self._fit_size()
            self._build_titles()

    # ------------------------------------------------------------ sounding cards
    def _snd_card(self, e):
        c = SoundingCard(self, e)
        c.rm.on_click(lambda ev: self._remove_snd(c))
        return c

    def _show_soundings(self):
        self.snd_box.objects = [c.panel for c in self.snd_cards] or [pn.pane.HTML(
            '<div class="cv-empty">No soundings: add the map\'s, or a new one.'
            '</div>')]

    def _remove_snd(self, c):
        self.snd_cards.remove(c)
        self._show_soundings()
        self.request()

    def _own_index(self):
        paths = [r["path"] for r in self.run_rows]
        return paths.index(self.run.path) if self.run.path in paths else 0

    def tab_soundings(self):
        """spec["soundings"] entries of the Sounding tab's soundings (this run)."""
        out = []
        for n, (kind, where, tp) in enumerate(self.v.points):
            t = self.v.t if tp is None else tp
            if kind == "mean":
                wh = dict(kind="mean", x=0.0, y=0.0, avg=0.0)
            else:
                avg = (0.5 * (where[2] + where[3]) if len(where) == 4
                       else float(self.v.avg.value or 0.0) if hasattr(self.v, "avg") else 0.0)
                wh = dict(kind=kind, x=float(where[0]), y=float(where[1]), avg=float(avg))
            out.append(fg.sounding_defaults(self._own_index(), float(self.run.times[t]), wh,
                                            n + len(self.snd_cards)))
        return out

    def _add_tab_soundings(self):
        new = self.tab_soundings()
        if not new:
            self._msg("No soundings yet: click the map with the Sounding tool first, or "
                      "add one here.", True)
            return
        self.snd_cards += [self._snd_card(e) for e in new]
        self._show_soundings()
        self.request()

    def _add_sounding(self):
        e = fg.sounding_defaults(self._own_index(), float(self.run.times[self.v.t]),
                                 dict(kind="trk", x=0.0, y=0.0, avg=0.0), len(self.snd_cards))
        e["panel"] = len(self.snd_cards)
        self.snd_cards.append(self._snd_card(e))
        self._show_soundings()
        self._fit_grid()
        self.request()

    # ------------------------------------------------------------ annotations
    def _ann_row(self, a):
        r = AnnotationRow(self, a)
        r.rm.on_click(lambda ev: self._remove_ann(r))
        return r

    def _show_anns(self):
        self.ann_box.objects = [r.panel for r in self.ann_rows]

    def _add_annotation(self):
        kind = self.ann_kind.value
        # in the middle of the first drawn panel, so it shows (storm-centred panels in
        # grid km may not contain (0, 0)); no axis ranges yet: as panel fractions
        lims = self._lims.get(min(self._lims)) if self._lims else None
        if lims is None or self.kind.value == "sounding":
            coords, (x, y), dx, dy = "axes", (0.5, 0.5), 0.15, 0.15
        else:
            (x0, x1), (y0, y1) = lims
            coords, x, y = "data", 0.5 * (x0 + x1), 0.5 * (y0 + y1)
            dx, dy = 0.15 * (x1 - x0), 0.15 * (y1 - y0)
        r = min(abs(dx), abs(dy)) if coords == "data" else 0.15
        a = dict(kind=kind, panel=-1, coords=coords, x=round(x, 2), y=round(y, 2),
                 x2=round(x + dx, 2), y2=round(y + dy, 2), r=round(r, 2),
                 text="A" if kind == "text" else "",
                 color="#000000", size=10.0 if kind != "marker" else 8.0, lw=1.5,
                 ls="--" if kind in ("vline", "hline") else "-")
        self.ann_rows.append(self._ann_row(a))
        self._show_anns()
        self.request()

    def _remove_ann(self, r):
        self.ann_rows.remove(r)
        self._show_anns()
        self.request()

    # ------------------------------------------------------------ series data
    def _series_get(self, spec, k, e):
        """(run, dataset) of series e of spec for run k, or why not (a string).  Starts
        computing the missing times in the background (the preview updates as they come
        in)."""
        runs, ent = spec["runs"], spec["series"][e]
        try:
            run, F = self.open_run(runs[k]["path"])
        except Exception as ex:  # noqa: BLE001
            return f"could not open {runs[k]['path']}: {ex}"
        r = ent["recipe"]
        if r["field"] not in F:
            return f"this run has no {r['field']}"
        fx = self.run_fixes(runs[k], run)
        track = r["region"] == "track"
        if track and not fx:
            return "no storm track for this run (Runs tab)"
        centers = ser.track_centers(fx, len(run.times)) if track else None
        sig = json.dumps(sorted((t, round(f["x"], 4), round(f["y"], 4))
                                for t, f in fx.items())) if track else ""
        key = (run.path, json.dumps(r, sort_keys=True), sig)
        ds = self._ser_mem.get(key)
        if ds is None:
            d = F[r["field"]]
            ds = ser.cached(run, r, d.label, d.units, centers)
            self._ser_mem[key] = ds
        if key not in self._ser_state and int(ds["computed"].sum()) < len(run.times):
            self._ser_state[key] = "running"
            storm = ({t: fg.storm_motion(run, fx, t) for t in range(len(run.times))}
                     if F[r["field"]].storm else None)
            self.v.pools["figser"].submit(self._ser_compute, key, run, F, r, ds, centers, storm,
                                          f"{runs[k].get('label') or ''}: {ent.get('label', '')}")
        elif key not in self._ser_state:
            self._ser_state[key] = "done"
        return run, ds

    def _ser_compute(self, key, run, F, recipe, ds, centers, storm, what):
        g0, last = self.v.gen["figser"], [_time.time()]

        def on_result(ds_, done, total):
            self._ser_prog[key] = f"{what[:60]} {done}/{total}"
            if _time.time() - last[0] > 10 and done < total:  # partial preview
                last[0] = _time.time()
                self.v._schedule(partial(self.request, False, False))

        try:
            ser.compute(run, F, recipe, ds, centers, storm, on_result=on_result,
                        cancelled=lambda: self.v.gen["figser"] != g0)
            self._ser_state[key] = "done"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._ser_state[key] = f"error: {e}"
        self._ser_prog.pop(key, None)
        self.v._schedule(partial(self.request, False, False))

    def series_pending(self):
        return [v for k, v in self._ser_prog.items() if self._ser_state.get(k) == "running"] \
            or [""] * sum(v == "running" for v in self._ser_state.values())

    def _series_data(self, spec):
        got = {}

        def get(k, e):
            if (k, e) not in got:
                got[(k, e)] = self._series_get(spec, k, e)
            return None if isinstance(got[(k, e)], str) else got[(k, e)]

        data, multi = {}, len(spec["runs"]) > 1
        busy = bool(self.series_pending())
        for i in range(fg.npanels(spec)):
            if spec["kind"] == "th":
                ref = figdraw.series_ref(spec, i)
                if ref is None:
                    continue
                r = get(*ref)
                d = (dict(missing=got[ref]) if r is None else
                     fg.th_panel(r[0], r[1], spec["series"][ref[1]], spec))
                if multi:
                    d["run_label"] = spec["runs"][ref[0]].get("label", "")
            else:
                d = fg.line_panel(spec, i, get)
            if busy and d.get("missing") == "not computed yet":
                d["missing"] = "computing…"
            data[i] = d
        return fg.share_time_range(spec, data)

    def _sounding_data(self, spec, progress=None, cancelled=None):
        runs, ents = spec["runs"], spec.get("soundings", [])
        res, labels = {}, {}
        multi = len(runs) > 1

        def get(e):
            if e in res:
                return res[e]
            ent = ents[e]
            k = int(ent.get("run", 0))
            if k >= len(runs):
                res[e] = "no such run"
                return res[e]
            try:
                run, _ = self.open_run(runs[k]["path"])
                fx = self.run_fixes(runs[k], run)
                sig = json.dumps(sorted((t, round(f["x"], 4), round(f["y"], 4))
                                        for t, f in fx.items())) \
                    if ent["where"].get("kind") == "trk" else ""
                key = json.dumps([run.path, float(ent["time_s"]), ent["where"], sig],
                                 sort_keys=True)
                r = self.snd_cache.get(key)
                if r is None:
                    if progress:
                        progress(e, len(ents))
                    r = fg.sounding_column(run, ent, fx)
                    self.snd_cache[key] = r
                    while len(self.snd_cache) > 40:
                        self.snd_cache.popitem(last=False)
                labels[e] = fg.sounding_label(ent, runs[k].get("label", ""), run, multi)
            except (MissingAtTime, FileBusy) as ex:
                r = str(ex)
            except Exception as ex:  # noqa: BLE001
                traceback.print_exc()
                r = f"{type(ex).__name__}: {ex}"
            res[e] = r
            return r

        data = {}
        for i in range(fg.npanels(spec)):
            if cancelled and cancelled():
                return None
            data[i] = fg.sounding_panel(spec, i, get, lambda e: labels.get(e, ""))
        return data

    # ------------------------------------------------------------ start from series / soundings
    def from_series(self):
        """Time-height panels of the Series tab's layer series (the active one first),
        or time series when the active one is at one height; every run of the figure.
        Without series: the maximum updraft near the storm (edit it in Layers)."""
        ss = getattr(self.v, "series", {}) or {}
        if ss:
            act = self.v.ser_pick.value if self.v.ser_pick.value in ss else next(iter(ss))
            keys = [act] + [k for k in ss if k != act]
            th = "profile" in ss[act]["ds"]
            keys = [k for k in keys if ("profile" in ss[k]["ds"]) == th][:4 if th else 6]
            ents = [fg.series_defaults(self.F, dict(ss[k]["recipe"]), n)
                    for n, k in enumerate(keys)]
        else:
            th, ents = True, [fg.series_defaults(self.F, self._new_recipe())]
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        nr = len(s["runs"])
        s.update(kind="th" if th else "line", series=ents, runs_as="cols", vary="time",
                 layers=[lay for lay in s["layers"] if lay["type"] != "vectors"])
        s["axes"] = dict(s["axes"], xlabel="time (min)", ylabel="height (km)" if th else "",
                         ticklabels="outer", equal=False)
        s["time_label"] = dict(s["time_label"], on=False)
        s["letters"] = dict(s["letters"], loc="upper left")
        if th:
            s.update(rows=len(ents), cols=nr, size=[5.0 * nr + 1.0, 3.0 * len(ents) + 0.5])
            s["colorbar"] = dict(s["colorbar"], mode="row", orientation="vertical", shrink=1.0)
            s["titles"] = [f"{s['runs'][c]['label']} – {e['label']}" for e in ents
                           for c in range(nr)]
            s["run_label"] = dict(s["run_label"], on=False)
        else:
            s.update(rows=1, cols=1, size=[7.0, 3.5])
            s["colorbar"] = dict(s["colorbar"], mode="none")
        self.set_spec(s)

    def from_soundings(self):
        """Skew-T panels: the Sounding tab's soundings in one panel (or the storm's
        sounding at the shown time when there are none)."""
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        own = s["runs"][s["run"]]
        track = bool(self.run_fixes(own, self.run))
        snd = self.tab_soundings() or [fg.sounding_defaults(
            s["run"], float(self.run.times[self.v.t]),
            dict(kind="trk" if track else "mean", x=0.0, y=0.0, avg=0.0))]
        s.update(kind="sounding", soundings=snd, rows=1, cols=1, size=[5.5, 5.5],
                 vary="time")
        s["axes"] = dict(s["axes"], xlabel="temperature (°C)", ylabel="pressure (hPa)",
                         ticklabels="all", equal=False)
        s["colorbar"] = dict(s["colorbar"], mode="none")
        s["letters"] = dict(s["letters"], on=False)
        s["time_label"] = dict(s["time_label"], loc="lower left")
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

    # ------------------------------------------------------------ export
    def _set_dl_name(self):
        self.dl.filename = f"{os.path.basename(self.path.value) or 'figure'}.{self.fmt.value}"
        for b in (self.save_img, self.save_all):
            b.disabled = not self.path.value.strip()

    def _sync_save_path(self):
        """One run: <figures_dir>/<parent>_<run>/.  Several runs have no folder of their
        own: the last folder used for one, else the user must choose."""
        multi = len(self.run_rows) > 1
        if multi == getattr(self, "_multi", False):
            return
        self._multi = multi
        cur = config.expand(self.path.value.strip())
        name = os.path.basename(cur) or "figure"
        if multi and (not cur or os.path.dirname(cur) == self._fig_dir):
            last = config.state("last_multi_run_dir")
            self.path.value = os.path.join(last, name) if last else ""
        elif not multi and (not cur or os.path.dirname(cur) == config.expand(
                config.state("last_multi_run_dir"))):
            self.path.value = os.path.join(self._fig_dir, name)
        self.path.placeholder = ("Several runs: choose a folder and name, e.g. "
                                 "~/figures/tor_vs_ntor/refl" if multi else "")
        if multi and not self.path.value:
            self._msg("This figure shows several runs: choose a folder for it in "
                      "“Save as”.", True)

    def config_changed(self):
        new = config.figures_dir(self.run.path)
        cur = config.expand(self.path.value.strip())
        if cur and os.path.dirname(cur) == self._fig_dir:
            self.path.value = os.path.join(new, os.path.basename(cur))
        self._fig_dir = new

    def _save(self, bundle):
        spec = self.collect()
        base = config.expand(self.path.value.strip())
        if not base:
            self._msg("Choose where to save the figure (“Save as”).", True)
            return
        fmt = spec["export"]["format"]
        if bundle:
            paths = list(fg.bundle_paths(spec, base).values())
        else:
            base = os.path.splitext(base)[0] if base.lower().endswith("." + fmt) else base
            paths = [f"{base}.{fmt}"]

        def go():
            if len(spec.get("runs") or []) > 1:
                config.set_state("last_multi_run_dir", os.path.dirname(base))
            self._msg('<span class="busy">● Saving…</span>')
            self.v.pools["fig"].submit(self._save_job, spec, bundle, base)
        self.v.confirm.ask(paths, go)

    def _save_job(self, spec, bundle, base=None):
        if spec["kind"] in ("th", "line"):
            self.panel_data(spec)  # (starts computing what is missing)
            if self.series_pending():
                self.v._schedule(partial(self._msg, "The series are still being computed "
                                                    "(see the preview's status line): save "
                                                    "when they are done.", True))
                return
        try:
            data = self.panel_data(spec)
            base = base or config.expand(self.path.value.strip())
            fmt = spec["export"]["format"]
            if not bundle and base.lower().endswith("." + fmt):
                base = os.path.splitext(base)[0]
            if bundle:
                out = fg.save_bundle(spec, data, base, self.run)
                html = "Saved " + ", ".join(f"<code>{p}</code>" for p in out.values())
            else:
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
        figdraw.save(spec, fig, buf, format=spec["export"]["format"], **fg.save_kw(spec))
        buf.seek(0)
        return buf

    def _load_spec(self):
        """Open a saved figure: its _spec.json, or the image / script saved with it."""
        path = config.expand(self.spec_path.value.strip())
        if path and not path.lower().endswith(".json"):
            path = fg.bundle_paths({}, path)["spec"]
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
        if bad and len(base.get("runs") or spec.get("runs") or []) <= 1:
            self._msg("This run has no field " + ", ".join(bad), True)
            return
        if "runs" not in spec:  # a figure of one run: this viewer's run
            base["runs"] = [fg.run_entry(self.run, self._own_track())]
        nt = len(self.run.times)
        if "times_s" not in spec:
            base["times"] = [t for t in base["times"] if t is None or t < nt]
            base["time"] = min(int(base["time"]), nt - 1)
            base.pop("times_s"), base.pop("time_s")
        self.set_spec(base)
        self._msg(f"Loaded <code>{path}</code>")


def _dark(color):
    """Light colours chosen for the dark map turn black on a white figure."""
    try:
        r, g, b = (int(color.lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))
    except (ValueError, AttributeError):
        return "#000000"
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 180 else color


# ------------------------------------------------------------------ series / soundings
SER_REGIONS = {"Around tracked storm": "track", "Whole domain": "domain",
               "Fixed box (map view)": "box"}
SER_REDUCE = {"Maximum": "max", "Minimum": "min", "Mean": "mean", "Percentile": "pct"}
SER_OPS = {"Value": "", "d/dz (per m)": "ddz", "d/dt (per s)": "ddt"}
MARKERS = {"none": "", "dots": "o", "squares": "s", "triangles": "^"}
SND_WHERE = {"Storm (offset, km)": "trk", "Point (model x, y km)": "pt",
             "Domain mean": "mean"}
ANN_KINDS = {"Text": "text", "Marker": "marker", "Arrow": "arrow", "Line": "line",
             "Vertical line": "vline", "Horizontal line": "hline", "Box": "box",
             "Circle": "circle"}
ANN_FIELDS = {  # widgets each kind uses (besides kind, panel, colour, remove)
    "text": ("coords", "x", "y", "text", "size", "bold"),
    "marker": ("coords", "x", "y", "marker", "size", "lw", "text", "bold"),
    "arrow": ("coords", "x", "y", "x2", "y2", "text", "size", "lw", "bold"),
    "line": ("coords", "x", "y", "x2", "y2", "lw", "ls"),
    "vline": ("x", "lw", "ls", "text", "bold"),
    "hline": ("y", "lw", "ls", "text", "bold"),
    "box": ("coords", "x", "y", "x2", "y2", "lw", "ls"),
    "circle": ("coords", "x", "y", "r", "lw", "ls"),
}
_BTN = dict(width=32, height=28, margin=(2, 1), button_type="default", button_style="outline")


def _chk(name, value):
    return pn.widgets.Checkbox(name=name, value=bool(value), margin=(5, 6, 12, 6))


class SeriesCard:
    """One series of a time-height / time-series figure: a Series-tab recipe (field,
    level or layer, region, reduction), an optional derivative, and its look."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.F, ent["recipe"]
        self.box = r.get("box")
        self.w = w = {}
        self.up = pn.widgets.Button(name="↑", description="Earlier in the list", **_BTN)
        self.down = pn.widgets.Button(name="↓", description="Later in the list", **_BTN)
        self.rm = pn.widgets.Button(name="✕", description="Remove the series", **_BTN)
        field = r["field"] if r["field"] in F else next(iter(F.defs))
        w["field"] = pn.widgets.Select(name="Field", groups=F.groups(), value=field, width=210)
        w["vmode"] = pn.widgets.Select(name="Vertical", options={
            "Layer (every level)": "layer", "At a height": "height"},
            value="height" if r["vmode"] == "height" else "layer", width=150)
        w["z"] = _f("Height (km)", float(r.get("z", 1.0)), 90, step=0.25)
        w["z0"] = _f("Bottom (km)", float(r.get("z0", 0.0)), 90, step=0.5)
        w["z1"] = _f("Top (km)", float(r.get("z1", 10.0)), 80, step=0.5)
        w["region"] = pn.widgets.Select(name="Region", options=SER_REGIONS, value=r["region"],
                                        width=180)
        w["radius"] = _f("Radius (km)", float(r.get("radius", 5.0)), 90, step=0.5)
        off = r.get("offset", (0.0, 0.0))
        w["offx"] = _f("Offset x (km)", float(off[0]), 100, step=1.0)
        w["offy"] = _f("Offset y (km)", float(off[1]), 100, step=1.0)
        w["reduce"] = pn.widgets.Select(name="Reduce", options=SER_REDUCE, value=r["reduce"],
                                        width=120)
        w["pct"] = _f("Percentile", float(r.get("pct", 99.0)), 90, step=0.5)
        w["op"] = pn.widgets.Select(name="Plot", options=SER_OPS, value=ent.get("op", ""),
                                    width=130)
        w["label"] = pn.widgets.TextInput(name="Label (titles, legend)",
                                          value=ent.get("label", ""), width=300)
        # time-height look
        w["cmap"] = pn.widgets.Select(name="Colormap", options=FIG_CMAPS, width=150,
                                      value=ent["cmap"] if ent["cmap"] in FIG_CMAPS
                                      else "viridis")
        w["reverse"] = _chk("Reverse", ent.get("reverse", False))
        w["white_first"] = _chk("White first", ent.get("white_first", False))
        w["vmin"] = _f("Min", float(ent["vmin"]))
        w["vmax"] = _f("Max", float(ent["vmax"]))
        w["nlevels"] = pn.widgets.IntInput(name="Steps (0 = smooth)", start=0, end=60,
                                           value=int(ent.get("nlevels") or 0), width=120)
        w["extend"] = pn.widgets.Select(name="Colorbar ends", options=[
            "neither", "max", "min", "both"], value=ent.get("extend", "neither"), width=110)
        # time-series look
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(ent.get("color", "k")),
                                            width=70)
        w["lw"] = _f("Line width", float(ent.get("lw", 1.5)), 90, step=0.25)
        w["marker"] = pn.widgets.Select(name="Markers", options=MARKERS,
                                        value=ent.get("marker", ""), width=100)
        w["panel"] = pn.widgets.IntInput(name="Panel", start=1, end=64, width=70,
                                         value=int(ent.get("panel", 0)) + 1)
        w["axis"] = pn.widgets.Select(name="y axis", options={"By units": "auto",
                                                              "Own axis (right)": "right"},
                                      value=ent.get("axis", "auto"), width=140)
        w["runs"] = pn.widgets.MultiChoice(name="Runs (blank: all)", options=ed._run_names(),
                                           value=[int(k) for k in (ent.get("runs") or [])],
                                           width=260)
        w["ylabel"] = pn.widgets.TextInput(name="Axis label (blank: units)",
                                           value=ent.get("ylabel", ""), width=180)
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self.info = pn.pane.HTML(margin=(0, 4))
        recipe_keys = ("vmode", "z", "z0", "z1", "region", "radius", "offx", "offy", "reduce",
                       "pct")
        for k in recipe_keys:
            w[k].param.watch(lambda e: self._changed(), "value")
        for k, x in w.items():
            if k not in recipe_keys and k not in ("field", "panel"):
                x.param.watch(lambda e: ed.request(), "value")
        w["panel"].param.watch(lambda e: ed._series_changed(), "value")
        w["field"].param.watch(self._on_field, "value")
        w["op"].param.watch(lambda e: self._set_title(), "value")
        self.th_row = _grid(w["cmap"], w["reverse"], w["white_first"], w["vmin"], w["vmax"],
                            w["nlevels"], w["extend"])
        self.line_row = _grid(w["color"], w["lw"], w["marker"], w["panel"], w["axis"],
                              w["ylabel"], (w["runs"], 3))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.up, self.down, self.rm],
            [_grid((w["field"], 2), w["vmode"], w["z"], w["z0"], w["z1"], w["region"],
                   w["radius"], w["offx"], w["offy"], w["reduce"], w["pct"], w["op"],
                   (w["label"], 3)), self.th_row, self.line_row, self.info])
        self._set_title()
        self.show(ed.kind.value)

    def show(self, kind):
        w, two = self.w, self.ed.F[self.w["field"].value].ndim == 2
        lay = w["vmode"].value == "layer"
        w["vmode"].visible = not two
        w["z"].visible = not two and not lay
        w["z0"].visible = w["z1"].visible = not two and lay
        trkr = w["region"].value == "track"
        w["radius"].visible = w["offx"].visible = w["offy"].visible = trkr
        w["pct"].visible = w["reduce"].value == "pct"
        self.th_row.visible = kind == "th"
        self.line_row.visible = kind == "line"

    def _set_title(self):
        d = self.ed.F[self.w["field"].value]
        op = {"ddz": " · d/dz", "ddt": " · d/dt"}.get(self.w["op"].value, "")
        self.title.object = f"<b>Series</b> · {d.label}{op}"

    def _changed(self):
        if self.w["region"].value == "box" and self.box is None:
            self.box = [float(v) for v in self.ed.v.view]
        self.show(self.ed.kind.value)
        self._auto_label()
        self.ed.request()

    def _auto_label(self):
        """Keep an automatic label in step with the recipe (an edited one stays)."""
        old = self.ent.get("_auto", self.ent.get("label", ""))
        d = self.ed.F[self.w["field"].value]
        new = ser.describe(self.recipe(), d.label)
        if self.w["label"].value in ("", old):
            hold, self.ed._hold = self.ed._hold, True
            try:
                self.w["label"].value = new
            finally:
                self.ed._hold = hold
        self.ent["_auto"] = new

    def _on_field(self, ev):
        """New field: its colours and range."""
        e = fg.series_defaults(self.ed.F, self.recipe())
        self.ed._hold = True
        try:
            for k in ("vmin", "vmax", "extend", "white_first"):
                self.w[k].value = e[k]
            self.w["cmap"].value = e["cmap"] if e["cmap"] in FIG_CMAPS else "viridis"
        finally:
            self.ed._hold = False
        self._set_title()
        self._changed()

    def recipe(self):
        w, d = self.w, self.ed.F[self.w["field"].value]
        r = dict(field=d.name, vmode="2d" if d.ndim == 2 else w["vmode"].value,
                 z=w["z"].value or 0.0, z0=w["z0"].value or 0.0, z1=w["z1"].value or 0.0,
                 region=w["region"].value, radius=w["radius"].value or 5.0,
                 offset=(w["offx"].value or 0.0, w["offy"].value or 0.0),
                 reduce=w["reduce"].value,
                 pct=w["pct"].value if w["pct"].value is not None else 99.0,
                 box=self.box or [float(v) for v in self.ed.v.view])
        return ser.normalize(r)

    def collect(self):
        w, e = self.w, dict(self.ent)
        e.pop("_auto", None)
        e["recipe"] = self.recipe()
        for k in ("op", "label", "cmap", "reverse", "white_first", "nlevels", "extend",
                  "color", "marker", "axis", "ylabel"):
            e[k] = w[k].value
        e["vmin"], e["vmax"] = float(w["vmin"].value or 0.0), float(w["vmax"].value or 0.0)
        e["lw"] = float(w["lw"].value or 1.5)
        e["panel"] = max(0, int(w["panel"].value or 1) - 1)
        e["runs"] = sorted(int(k) for k in w["runs"].value) or None
        e["base_units"] = self.ed.F[e["recipe"]["field"]].units
        e["units"] = fg.op_units(e["base_units"], e["op"])
        return e


class SoundingCard:
    """One sounding of a sounding figure: run, time, where, look and panel."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        self.w = w = {}
        self.rm = pn.widgets.Button(name="✕", description="Remove the sounding", **_BTN)
        names = ed._run_names()
        k = int(ent.get("run", 0)) if int(ent.get("run", 0)) in names.values() else 0
        w["run"] = pn.widgets.Select(name="Run", options=names, value=k, width=170)
        opts = ed._time_opts(k)
        w["time"] = pn.widgets.Select(name="Time", options=opts, width=210,
                                      value=ed._nearest(opts, ent.get("time_s")))
        wh = ent.get("where", {})
        w["kind"] = pn.widgets.Select(name="Where", options=SND_WHERE,
                                      value=wh.get("kind", "trk"), width=180)
        w["x"] = _f("x (km)", float(wh.get("x", 0.0)), 80, step=1.0)
        w["y"] = _f("y (km)", float(wh.get("y", 0.0)), 80, step=1.0)
        w["avg"] = _f("Box width (km, 0: column)", float(wh.get("avg", 0.0)), 170, step=0.5,
                      start=0.0)
        w["label"] = pn.widgets.TextInput(name="Legend text (blank: automatic)",
                                          value=ent.get("label", ""), width=220)
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(ent.get("color", "k")),
                                            width=70)
        w["panel"] = pn.widgets.IntInput(name="Panel", start=1, end=64, width=70,
                                         value=int(ent.get("panel", 0)) + 1)
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k != "run":
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: ed._fit_grid(), "value")
        self.title = pn.pane.HTML("<b>Sounding</b>", margin=(6, 4, 0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [_grid(w["run"], (w["time"], 2), w["kind"], w["x"], w["y"], w["avg"], w["color"],
                   w["panel"], (w["label"], 3))])
        self._show()

    def _show(self):
        w = self.w
        w["x"].visible = w["y"].visible = w["avg"].visible = w["kind"].value != "mean"
        where = {"trk": "storm", "pt": "point", "mean": "domain mean"}[w["kind"].value]
        when = next((k for k, v in w["time"].options.items() if v == w["time"].value), "")
        self.title.object = (f"<b>Sounding</b> · {where} · {when.split('(')[-1].rstrip(')')} "
                             f"· panel {w['panel'].value}")

    def _changed(self):
        self._show()
        self.ed.request()

    def _on_run(self, ev):
        if self.ed._hold:
            return
        o = self.ed._time_opts(ev.new)
        cur = self.w["time"].value
        self.ed._hold = True
        try:
            self.w["time"].options = o
            self.w["time"].value = self.ed._nearest(o, cur)
        finally:
            self.ed._hold = False
        self.ed.request()

    def collect(self):
        w = self.w
        return dict(run=int(w["run"].value or 0), time_s=float(w["time"].value or 0.0),
                    panel=max(0, int(w["panel"].value or 1) - 1), label=w["label"].value,
                    color=w["color"].value,
                    where=dict(kind=w["kind"].value, x=float(w["x"].value or 0.0),
                               y=float(w["y"].value or 0.0),
                               avg=float(w["avg"].value or 0.0)))


class AnnotationRow:
    """One annotation: text, marker, arrow, line, box or circle in one panel or all."""

    def __init__(self, ed, a):
        self.ed = ed
        self.w = w = {}
        w["kind"] = pn.widgets.Select(name="Kind", options=ANN_KINDS, value=a.get("kind", "text"),
                                      width=130)
        w["panel"] = pn.widgets.IntInput(name="Panel (0: all)", start=0, end=64, width=100,
                                         value=int(a.get("panel", -1)) + 1)
        w["coords"] = pn.widgets.Select(name="Position in", options={
            "Axis units (km, min)": "data", "Panel fraction (0–1)": "axes"},
            value=a.get("coords", "data"), width=170)
        for k, lab in (("x", "x"), ("y", "y"), ("x2", "x to"), ("y2", "y to"),
                       ("r", "Radius")):
            w[k] = _f(lab, float(a.get(k, 0.0 if k != "r" else 1.0)), 80, step=0.5)
        w["text"] = pn.widgets.TextInput(name="Text", value=a.get("text", ""), width=150)
        w["size"] = _f("Size", float(a.get("size") or 10.0), 70, step=1)
        w["lw"] = _f("Line width", float(a.get("lw", 1.5)), 90, step=0.25)
        w["ls"] = pn.widgets.Select(name="Style", options={"solid": "-", "dashed": "--",
                                                           "dotted": ":"},
                                    value=a.get("ls", "-" if a.get("kind") not in
                                                ("vline", "hline") else "--"), width=90)
        w["marker"] = pn.widgets.Select(name="Marker", options={
            "×": "x", "+": "+", "●": ".", "○": "o", "□": "s", "★": "*", "▲": "^"},
            value=a.get("marker", "x"), width=80)
        w["bold"] = _chk("Bold", a.get("bold", False))
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(a.get("color", "k")),
                                            width=70)
        self.rm = pn.widgets.Button(name="✕", description="Remove", **_BTN)
        for k, x in w.items():
            x.param.watch(lambda e: self._changed(), "value")
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self.panel, self.body = _fold([self.title, pn.Spacer(), self.rm], [_grid(*w.values())])
        self._show()

    def _show(self):
        w = self.w
        use = ANN_FIELDS[w["kind"].value]
        for k, x in w.items():
            if k not in ("kind", "panel", "color"):
                x.visible = k in use
        kind = next(k for k, v in ANN_KINDS.items() if v == w["kind"].value)
        where = "every panel" if not w["panel"].value else \
            f"panel {figdraw.panel_letter(int(w['panel'].value) - 1, '{a}')}"
        txt = f" “{w['text'].value}”" if "text" in use and w["text"].value else ""
        self.title.object = f"<b>{kind}</b>{txt} · {where}"

    def _changed(self):
        self._show()
        self.ed.request()

    def collect(self):
        w = self.w
        a = dict(kind=w["kind"].value, panel=int(w["panel"].value or 0) - 1,
                 color=w["color"].value)
        for k in ANN_FIELDS[a["kind"]]:
            v = w[k].value
            a[k] = float(v or 0.0) if isinstance(w[k], pn.widgets.FloatInput) else v
        return a
