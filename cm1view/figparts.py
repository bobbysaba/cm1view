"""Figure editor pieces: choices and constants, small widget helpers, and the cards
for layers, series, soundings, distributions and annotations."""

import panel as pn
from matplotlib import font_manager
from matplotlib.colors import to_hex

from . import dist, figdraw, figure as fg, series as ser
from .fields import CMAPS
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
        "Height (one run, one time)": "height",
        "Run × time grid": "grid", "Each panel: own run & time": "custom"}
LETTERS = {"a": "{a}", "(a)": "({a})", "a)": "{a})", "A": "{A}", "(A)": "({A})"}
TYPE_LABEL = {"fill": "Fill", "contour": "Contours", "shade": "Shading", "vectors": "Vectors",
              "track": "Storm track", "line": "Section line"}
EXTEND = {"Auto (where the data pass the range)": "auto", "None": "neither",
          "Max end": "max", "Min end": "min", "Both ends": "both"}
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
        F, g = ed.fields, ed.fields.groups()
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
        if t in ("fill", "contour", "shade", "vectors"):
            w["z_fixed"] = _chk("Own height (not the panel's)", lay.get("z_fixed", False))
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
            w["run_color"] = _chk("Run's colour", lay.get("run_color", False))
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
            return [_grid((w["field"], 2), w["mode"], w["z"], w["z_fixed"], w["style"],
                          w["mask_below"]),
                    _grid(w["cmap"], w["reverse"], w["white_first"], w["vmin"], w["vmax"],
                          w["nlevels"], w["scale"], w["extend"], w["alpha"],
                          (w["cbar_label"], 3), (w["panels"], 3))]
        if t == "contour":
            return [_grid((w["field"], 2), w["mode"], w["z"], w["z_fixed"], (w["levels"], 2),
                          w["color"],
                          w["lw"], w["neg_dashed"], w["clabel"], w["clabel_size"],
                          w["clabel_fmt"], (w["legend"], 3), (w["panels"], 3))]
        if t == "shade":
            return [_grid((w["field"], 2), w["mode"], w["z"], w["z_fixed"], w["threshold"],
                          w["above"],
                          w["color"], w["alpha"], w["outline_on"], w["outline"], w["lw"],
                          (w["legend"], 3), (w["panels"], 3))]
        if t == "vectors":
            return [_grid(w["style"], w["frame"], w["color"], w["z"], w["z_fixed"], w["spacing"],
                          w["zspacing"], w["scale"], w["width"], w["key"], w["density"],
                          w["slw"], w["arrowsize"], (w["panels"], 3))]
        if t == "track":
            return [_grid(w["run_color"], w["color"], w["lw"], w["ls"], w["marker"],
                          (w["legend"], 3), (w["panels"], 3))]
        return [_grid(w["color"], w["lw"], w["labels"], (w["legend"], 3), (w["panels"], 3))]

    def show(self, kind):
        """Only the settings that matter for this layer in `kind` panels (a section
        samples the fields along the section, at every height)."""
        w, t, xs = self.w, self.type, kind == "xsec"
        by_z = self.ed.vary.value == "height" and not xs  # panels at their own heights
        if "mode" in w:
            m = w["mode"].value
            w["mode"].visible = not xs
            w["z_fixed"].visible = by_z and m == "height"
            w["z"].visible = not xs and m in ("height", "level") and (
                m == "level" or not by_z or w["z_fixed"].value)
            w["z"].name = "Model level (k)" if m == "level" else "Height (km)"
        if t == "vectors":
            st = w["style"].value == "streamlines"
            for k in ("density", "slw", "arrowsize"):
                w[k].visible = st
            for k in ("scale", "width", "key"):
                w[k].visible = not st
            w["z_fixed"].visible = by_z
            w["z"].visible = not xs and (not by_z or w["z_fixed"].value)
            w["spacing"].visible = not st
            w["spacing"].name = "Spacing along (km)" if xs else "Spacing (km)"
            w["zspacing"].visible = xs and not st
        if t == "shade":
            w["outline"].visible = w["lw"].visible = w["outline_on"].value
        if t == "track":  # (each panel's run's colour: Panels → Runs)
            w["color"].visible = not w["run_color"].value
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
            d = self.ed.fields[w["field"].value]
            sub = f" · {d.label}"
            m = w["mode"].value
            if self.ed.kind.value != "xsec":
                z = w["z"].value or 0
                own = self.ed.vary.value == "height" and not w["z_fixed"].value
                sub += {"height": " · the panel's height" if own else f" · {z:g} km",
                        "level": f" · k = {z:g}",
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
        d = fg.layer_defaults("fill", self.ed.fields, ev.new)
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
            lay["units"] = self.ed.fields[lay["field"]].units
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
SND_LAYOUTS = {"Skew-T with a hodograph inset": "inset",
               "Skew-T and hodograph side by side": "side", "Skew-T only": "skewt",
               "Hodograph only": "hodo"}
SND_WHERE = {"Storm (offset, km)": "trk", "Point (model x, y km)": "pt",
             "Domain mean": "mean"}
STORM_MOTIONS = {"Bunkers right mover": "rm", "Bunkers left mover": "lm",
                 "0–6 km mean wind": "mean", "Custom (u, v)": "custom"}
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
        F, r = ed.fields, ent["recipe"]
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
            "auto", "neither", "max", "min", "both"], value=ent.get("extend", "neither"),
            width=110)
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
        w["runs"] = pn.widgets.MultiChoice(name="Runs (blank: all)",
                                           options=ed._series_run_opts(),
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
        w["runs"].param.watch(self._on_runs, "value")
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
        w, two = self.w, self.ed.fields[self.w["field"].value].ndim == 2
        lay = w["vmode"].value == "layer"
        w["vmode"].visible = not two
        w["z"].visible = not two and not lay
        w["z0"].visible = w["z1"].visible = not two and lay
        trkr = w["region"].value == "track"
        w["radius"].visible = w["offx"].visible = w["offy"].visible = trkr
        w["pct"].visible = w["reduce"].value == "pct"
        self.th_row.visible = kind == "th"
        self.line_row.visible = kind == "line"

    def _on_runs(self, ev):
        """A run not in the figure picked (its path): add it to the figure, and keep
        it picked here."""
        new = [v for v in ev.new if isinstance(v, str)]
        if self.ed._hold or not new:
            return
        keep = [v for v in ev.new if not isinstance(v, str)]
        for p in new:
            k = self.ed._add_run(p, grid=False)
            if k is not None:
                keep.append(k)
        hold, self.ed._hold = self.ed._hold, True
        try:
            self.w["runs"].value = sorted(set(keep))
        finally:
            self.ed._hold = hold
        self.ed._series_changed()

    def _set_title(self):
        d = self.ed.fields[self.w["field"].value]
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
        d = self.ed.fields[self.w["field"].value]
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
        e = fg.series_defaults(self.ed.fields, self.recipe())
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
        w, d = self.w, self.ed.fields[self.w["field"].value]
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
        e["runs"] = sorted(int(k) for k in w["runs"].value if not isinstance(k, str)) or None
        e["base_units"] = self.ed.fields[e["recipe"]["field"]].units
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
        w["run"] = pn.widgets.Select(name="Run", value=k, width=170, **ed._run_choices(names))
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
        w["auto_color"] = _chk("Automatic colour", not ent.get("color"))
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(ent.get("color") or "k"),
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
            [_grid(w["run"], (w["time"], 2), w["kind"], w["x"], w["y"], w["avg"],
                   w["auto_color"], w["color"], w["panel"], (w["label"], 3)),
             _hint("Automatic colour: the run's colour (<b>Panels → Runs</b>) when each "
                   "sounding of the panel is from another run, else the next colour.")])
        self._show()

    def _show(self):
        w = self.w
        w["x"].visible = w["y"].visible = w["avg"].visible = w["kind"].value != "mean"
        w["color"].visible = not w["auto_color"].value
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
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
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
                    color="" if w["auto_color"].value else w["color"].value,
                    where=dict(kind=w["kind"].value, x=float(w["x"].value or 0.0),
                               y=float(w["y"].value or 0.0),
                               avg=float(w["avg"].value or 0.0)))


DIST_VMODES = {"At a height": "height", "Layer (every level)": "layer",
               "Every level (whole depth)": "all"}
DIST_PLOTS = {"Histogram": "hist", "Box plot": "box", "Violin": "violin",
              "Cumulative (ECDF)": "ecdf"}
DIST_NORMS = {"Count": "count", "PDF (density)": "pdf", "Fraction": "frac"}
DIST_HSTYLES = {"Filled outline": "stepfilled", "Outline": "step", "Bars": "bar"}
DIST_CUM = {"At or below x": "below", "Above x (exceedance)": "above"}
DIST_WHIS = {"1.5 × IQR (Tukey)": "tukey", "Min – max": "range", "5th – 95th percentile": "p5",
             "1st – 99th percentile": "p1"}


class DistCard:
    """One distribution of a distribution figure: run, time, a dist recipe (field,
    height, layer or whole depth, region, value limits), look and panel."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.box = r.get("box")
        self.w = w = {}
        self.rm = pn.widgets.Button(name="✕", description="Remove the distribution", **_BTN)
        names = ed._run_names()
        k = int(ent.get("run", 0)) if int(ent.get("run", 0)) in names.values() else 0
        w["run"] = pn.widgets.Select(name="Run", value=k, width=170, **ed._run_choices(names))
        opts = ed._time_opts(k)
        w["time"] = pn.widgets.Select(name="Time", options=opts, width=210,
                                      value=ed._nearest(opts, ent.get("time_s")))
        field = r["field"] if r["field"] in F else next(iter(F.defs))
        w["field"] = pn.widgets.Select(name="Field", groups=F.groups(), value=field, width=210)
        w["vmode"] = pn.widgets.Select(name="Vertical", options=DIST_VMODES, width=170,
                                       value=r["vmode"] if r["vmode"] in DIST_VMODES.values()
                                       else "height")
        w["z"] = _f("Height (km)", float(r.get("z", 1.0)), 90, step=0.25)
        w["z0"] = _f("Bottom (km)", float(r.get("z0", 0.0)), 90, step=0.5)
        w["z1"] = _f("Top (km)", float(r.get("z1", 10.0)), 80, step=0.5)
        w["region"] = pn.widgets.Select(name="Region", options=SER_REGIONS, value=r["region"],
                                        width=180)
        w["radius"] = _f("Radius (km)", float(r.get("radius", 5.0)), 90, step=0.5)
        off = r.get("offset") or (0.0, 0.0)
        w["offx"] = _f("Offset x (km)", float(off[0]), 100, step=1.0)
        w["offy"] = _f("Offset y (km)", float(off[1]), 100, step=1.0)
        w["lo"] = pn.widgets.FloatInput(  # (0 is a limit here, not blank)
            name="Only values from", value=r.get("lo"), placeholder="all", width=120,
            description="Keep values at or above this (blank: no limit), e.g. 1 m/s for "
                        "updrafts")
        w["hi"] = pn.widgets.FloatInput(name="to", value=r.get("hi"), placeholder="all",
                                        width=90)
        w["label"] = pn.widgets.TextInput(name="Legend text (blank: automatic)",
                                          value=ent.get("label", ""), width=220)
        w["auto_color"] = _chk("Automatic colour", not ent.get("color"))
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(ent.get("color") or "k"),
                                            width=70)
        w["panel"] = pn.widgets.IntInput(name="Panel", start=1, end=64, width=70,
                                         value=int(ent.get("panel", 0)) + 1)
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k not in ("run", "panel"):
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: (self._show(), ed._fit_grid(), ed.request()), "value")
        self.title = pn.pane.HTML("<b>Distribution</b>", margin=(6, 4, 0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [_grid(w["run"], (w["time"], 2), (w["field"], 2), w["vmode"], w["z"], w["z0"],
                   w["z1"], w["region"], w["radius"], w["offx"], w["offy"], w["lo"], w["hi"],
                   w["auto_color"], w["color"], w["panel"], (w["label"], 3)),
             _hint("Every value of the field in the region at that time. Around the storm: "
                   "a disc around each run's track. Automatic colour: the run's colour when "
                   "each distribution of the panel is from another run, else the next "
                   "colour.")])
        self._show()

    def _show(self):
        w, two = self.w, self.ed.fields[self.w["field"].value].ndim == 2
        mode = w["vmode"].value
        w["vmode"].visible = not two
        w["z"].visible = not two and mode == "height"
        w["z0"].visible = w["z1"].visible = not two and mode == "layer"
        trk = w["region"].value == "track"
        w["radius"].visible = w["offx"].visible = w["offy"].visible = trk
        w["color"].visible = not w["auto_color"].value
        d = self.ed.fields[w["field"].value]
        when = next((k for k, v in w["time"].options.items() if v == w["time"].value), "")
        self.title.object = (f"<b>Distribution</b> · {d.label} · "
                             f"{when.split('(')[-1].rstrip(')')} · panel {w['panel'].value}")

    def _changed(self):
        if self.w["region"].value == "box" and self.box is None:
            self.box = [float(v) for v in self.ed.v.view]
        self._show()
        self.ed.request()

    def _on_run(self, ev):
        if self.ed._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
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

    def recipe(self):
        w, d = self.w, self.ed.fields[self.w["field"].value]
        return dist.normalize(dict(
            field=d.name, vmode="2d" if d.ndim == 2 else w["vmode"].value,
            z=w["z"].value or 0.0, z0=w["z0"].value or 0.0, z1=w["z1"].value or 0.0,
            region=w["region"].value, radius=w["radius"].value or 5.0,
            offset=(w["offx"].value or 0.0, w["offy"].value or 0.0),
            box=self.box or [float(v) for v in self.ed.v.view],
            lo=_num(w["lo"].value), hi=_num(w["hi"].value)))

    def collect(self):
        w = self.w
        return dict(run=int(w["run"].value or 0), time_s=float(w["time"].value or 0.0),
                    panel=max(0, int(w["panel"].value or 1) - 1), label=w["label"].value,
                    color="" if w["auto_color"].value else w["color"].value,
                    recipe=self.recipe())


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
