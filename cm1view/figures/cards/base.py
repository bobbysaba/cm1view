"""Figure editor cards: the choices and constants, and small widget helpers."""

import math
import re

import panel as pn
from matplotlib import font_manager
from matplotlib.colors import to_hex

from .. import draw as figdraw
from ...core.fields import CMAPS
from ...viewer.numinput import FloatInput
from ...theme import GRID, PANEL, RAISED, TEXT


PYART_CMAPS = ["HomeyerRainbow", "ChaseSpectral", "NWSRef", "NWSVel", "LangRainbow12",
               "SpectralExtended", "Carbone42", "Theodore16", "BuDRd18"]
FIG_CMAPS = list(dict.fromkeys(PYART_CMAPS + CMAPS + [
    "Greys", "gray_r", "Blues", "Reds", "Purples", "PuOr", "RdBu", "bwr", "jet"]))
LOCS = ["upper left", "upper right", "lower left", "lower right", "upper center",
        "lower center", "center left", "center right"]
FIG_LOCS = ["outside right center", "outside right upper", "outside left center",
            "outside lower center", "outside upper center"]  # (a figure legend's, beside the panels)
LABEL_LOCS = LOCS + ["above left", "above right"]  # panel letters, times, run names
MARK_EXTREMES = {"None": "", "Maximum": "max", "Minimum": "min", "Both": "both"}
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
HATCHES = {"Solid": "", "Hatching /": "///", "Hatching \\": "\\\\\\", "Cross-hatching": "xxx",
           "Stippling": "..", "Dense stippling": "...", "Circles": "oo"}  # (shade layers)
VARY = {"Time (one run)": "time", "Field (one run, one time)": "field",
        "Height (one run, one time)": "height",
        "Each panel: own run & time": "custom"}
LETTERS = {"a": "{a}", "(a)": "({a})", "a)": "{a})", "A": "{A}", "(A)": "({A})"}
TYPE_LABEL = {"fill": "Fill", "contour": "Contours", "shade": "Shading", "vectors": "Vectors",
              "track": "Storm track", "line": "Section line", "sector": "Sector"}
REDUCE = {"One time (off)": "", "Maximum (swath)": "max", "Minimum": "min", "Mean": "mean",
          "Sum": "sum", "Storm-following mean (composite)": "composite"}
GRIDS = {"Say so (ask)": "ask", "Interpolate onto this layer's grid": "interp",
         "Refuse": "refuse"}
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
    return FloatInput(name=name, value=value, width=width, **kw)


def _auto(name, value=None, **kw):
    """A number that may be left blank (automatic)."""
    v = None if value in (None, "", 0) else float(value)
    return FloatInput(name=name, value=v, placeholder="auto", width=90, **kw)


def _num(v):
    """A blank-able number for the spec (None when blank)."""
    return None if v in (None, "") else float(v)


def _xy(text):
    """An "x, y" text as [x, y] for the spec (None unless two numbers)."""
    v = re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", str(text or ""))
    return [float(v[0]), float(v[1])] if len(v) == 2 else None


def _xy_text(v):
    """[x, y] as the text of an "x, y" box (blank: none)."""
    return f"{v[0]:g}, {v[1]:g}" if v else ""


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


def _checks(*groups, title="Show", n=2):
    """The on / off settings of a section or card as one list of checkboxes at its foot:
    groups are checkboxes, or (heading, [checkboxes]) for a list in parts (e.g. the
    hodograph's storm motions, one box each).  Hidden boxes leave no gap; a part, or the
    list, hides when all its boxes are hidden."""
    loose = [g for g in groups if not isinstance(g, tuple)]
    groups = ([("", loose)] if loose else []) + [g for g in groups if isinstance(g, tuple)]
    parts = []
    for head, bs in groups:
        for b in bs:
            b.width, b.sizing_mode, b.margin = None, "stretch_width", (2, 6, 2, 6)
        grid = pn.Column(*bs, sizing_mode="stretch_width", margin=0, styles={
            "display": "grid", "grid-template-columns": f"repeat({n}, minmax(0, 1fr))",
            "column-gap": "2px"})
        part = pn.Column(_label(head), grid, margin=(2, 0, 0, 12),
                         sizing_mode="stretch_width") if head else grid
        parts.append((part, bs))
    col = pn.Column(_label(title, strong=True), *[p for p, _ in parts],
                    sizing_mode="stretch_width", margin=(6, 0, 2, 0),
                    styles={"border-top": f"1px solid {GRID}", "padding-top": "2px"})

    def show(*e):
        for part, bs in parts:
            part.visible = any(b.visible for b in bs)
        col.visible = any(p.visible for p, _ in parts)
    for _, bs in parts:
        for b in bs:
            b.param.watch(show, "visible")
    show()
    return col


def _label(text, strong=False):
    t = f"<b>{text}</b>" if strong else text
    return pn.pane.HTML(f'<div class="cv-hint">{t}</div>', margin=(4, 4, 0, 4),
                        sizing_mode="stretch_width")


def _section(title, *objs, collapsed=True):
    """A collapsible section of the editor, closed until clicked."""
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


def _near(opts, ts):
    """The value of opts nearest model time ts ("": None, or no times)."""
    vals = [v for v in opts.values() if v != ""]
    return "" if ts is None or not vals else min(vals, key=lambda v: abs(v - float(ts)))


def _nice(a):
    """a rounded to 1, 2 or 5 times a power of ten (at least that large)."""
    a = abs(float(a)) or 1.0
    p = 10.0 ** math.floor(math.log10(a))
    return float(next(m * p for m in (1, 2, 5, 10) if m * p >= a - 1e-9))


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
AZ_REFS = {"Storm motion (0: ahead, 90: right)": "motion", "Grid north (0: north, 90: east)":
           "north"}
AZ_CENTERS = {"Tracked storm (offset, km)": "track", "Point (model x, y km)": "point"}
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
