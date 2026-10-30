"""Figure editor cards: the choices and constants, and small widget helpers."""

import math
import re

import panel as pn
from matplotlib import font_manager
from matplotlib.colors import to_hex

from .. import draw as figdraw
from ...core.fields import CMAPS, DERIVS, deriv_options, split_deriv
from ...viewer.numinput import FloatInput
from ...theme import GRID, PANEL, RAISED, TEXT
from ...viewer.ui import held


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
GRID_DIMS = {"— (fill row by row)": "none", "Runs": "runs", "Sections": "sections",
             "Times": "times", "Fields": "fields", "Heights": "heights"}  # (rows / columns)
QUICK_VARY = {"Time": "times", "Field (one time)": "fields", "Height (one time)": "heights",
              "Run (one time)": "runs",
              "Nothing (alike panels)": "none"}  # (the quick start: panels fill the grid)
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
    grid = pn.Column(*items, sizing_mode="stretch_width", margin=0, styles={
        "display": "grid", "grid-template-columns": f"repeat({n}, minmax(0, 1fr))",
        "column-gap": "2px"})
    _follow_shown(grid, items)  # (a hidden widget is not sent to the browser)
    # (inside a plain column: bokeh hides with a ":host {display: none}" stylesheet,
    # which the grid's inline display would override, so .visible = False did nothing)
    return pn.Column(grid, sizing_mode="stretch_width", margin=0)


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
        _follow_shown(grid, bs)
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
    """A collapsible section of the editor, closed until clicked: its contents are sent
    to the browser the first time it is opened (and kept)."""
    card = pn.Card(*([] if collapsed else objs), title=title, collapsed=collapsed,
                   **SECTION)
    if collapsed:
        def opened(e):
            if not e.new and not card.objects:
                card.objects = list(objs)
        card.param.watch(opened, "collapsed")
    return card


def _keep_shown(col, objs):
    """col holds those of objs that are visible: a hidden one is left out (its widgets
    are not sent to the browser) until it is shown again."""
    keep = [o for o in objs if o.visible]
    if [id(o) for o in keep] != [id(o) for o in col.objects]:
        col.objects = keep


LOAD = ("groups", "options", "disabled_options", "name", "placeholder", "start", "end")


def _load_widgets(w, src):
    """Widgets w (a dict) take the settings and values of src's (a card of the same kind
    built for other settings, never shown): a card the browser has shows them."""
    for k, x in src.items():
        y = w[k]
        upd = {p: getattr(x, p) for p in LOAD
               if p in x.param and getattr(x, p) != getattr(y, p)}
        if "groups" in upd:  # (a grouped list: its groups make the options)
            upd.pop("options", None)
        y.param.update(**upd, value=x.value)


def _follow_shown(col, objs):
    """_keep_shown(col, objs) now and whenever one of objs is shown or hidden."""
    objs = list(objs)
    for o in objs:
        o.param.watch(lambda e: _keep_shown(col, objs), "visible")
    _keep_shown(col, objs)


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
    `body` (only in the card while shown).  Returns (card, body column)."""
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
    _follow_shown(card, card.objects)
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
             "Circle": "circle", "Legend entry": "legend"}
ANN_FIELDS = {  # widgets each kind uses (besides kind, panel, colour, remove)
    "text": ("coords", "x", "y", "text", "size", "bold"),
    "marker": ("coords", "x", "y", "marker", "size", "lw", "text", "bold"),
    "arrow": ("coords", "x", "y", "x2", "y2", "text", "size", "lw", "bold"),
    "line": ("coords", "x", "y", "x2", "y2", "lw", "ls"),
    "vline": ("x", "lw", "ls", "text", "bold"),
    "hline": ("y", "lw", "ls", "text", "bold"),
    "box": ("coords", "x", "y", "x2", "y2", "lw", "ls"),
    "circle": ("coords", "x", "y", "r", "lw", "ls"),
    "legend": ("text", "look", "lw", "ls", "marker", "alpha"),  # (no place: in the legend)
}
_BTN = dict(width=32, height=28, margin=(2, 1), button_type="default", button_style="outline")


def _chk(name, value):
    return pn.widgets.Checkbox(name=name, value=bool(value), margin=(5, 6, 12, 6))


def _deriv_opts(F, base):
    """{label: op} of a Derivative select beside Field `base` (a 2D field: no ∂/∂z)."""
    return deriv_options(F[base]) if base in F else {"None": ""} | \
        {v: k for k, v in DERIVS.items()}


def _deriv_pair(F, name, width=210, first=None):
    """(Field, Derivative) selects of field name `name` (fields.deriv_name), the
    Derivative following the Field's options; fields.deriv_name(deriv, field) is the
    name picked."""
    op, base = split_deriv(name)
    if base not in F:
        op, base = "", first or next(iter(F.defs))
    field = pn.widgets.Select(name="Field", groups=F.groups(), value=base, width=width)
    opts = _deriv_opts(F, base)
    deriv = pn.widgets.Select(
        name="Derivative", options=opts, value=op if op in opts.values() else "", width=100,
        description="A derivative of the field (per km), taken before the reduction: ∂/∂z "
                    "on the model levels, ∂/∂x, ∂/∂y or the horizontal gradient's size")

    def follow(ev):  # (registered first: other watchers of the Field see valid options)
        o = _deriv_opts(F, ev.new)
        if o != deriv.options:
            v = deriv.value
            deriv.options = o
            deriv.value = v if v in o.values() else ""

    field.param.watch(follow, "value")
    return field, deriv



# ------------------------------------------------------------ runs and times of a card
ONE_TIME = -1.0  # (the "to" time of an entry at one time)


def _take_new_runs(ed, box, picked):
    """Runs picked in a Runs box `box` that are not in the figure (their paths): add
    them to the figure and keep them picked (as their indices)."""
    new = [v for v in picked if isinstance(v, str)]
    if not new:
        return
    keep = [v for v in picked if not isinstance(v, str)]
    for p in new:
        k = ed._add_run(p, grid=False)
        if k is not None:
            keep.append(k)
    with held(ed):
        box.value = sorted(set(keep))


class TimeCard:
    """The run and time of a card of one entry (a sounding, distribution, joint
    distribution, azimuthal mean or profile), and its time window when it has a "to"
    time (w["time1"])."""

    @staticmethod
    def _to_opts(opts):
        return {"— (this time only)": ONE_TIME} | dict(opts)

    def _time_widgets(self, opts, to=None, about=""):
        """The Time list (w["time"], from the entry's time_s) of choices opts, and with
        a `to` label the time window's end (w["time1"], from time_s1; about: its
        tooltip)."""
        ed, ent, w = self.ed, self.ent, self.w
        w["time"] = pn.widgets.Select(name="Time", options=opts, width=210,
                                      value=ed._nearest(opts, ent.get("time_s")))
        if to:
            t1 = ent.get("time_s1")
            w["time1"] = pn.widgets.Select(
                name=to, options=self._to_opts(opts), width=210, description=about,
                value=ONE_TIME if t1 is None else ed._nearest(opts, t1))

    def _t1(self):
        """The end of the time window (None: one time)."""
        if "time1" not in self.w:
            return None
        t0, t1 = self.w["time"].value, self.w["time1"].value
        return None if t1 in (None, ONE_TIME) or t0 is None or float(t1) <= float(t0) \
            else float(t1)

    def _when(self):
        """The time (or window) as the title shows it: '1:30:00 to 1:45:00'."""
        def short(k):
            w = self.w[k]
            label = next((n for n, v in w.options.items() if v == w.value), "")
            return label.split("(")[-1].rstrip(")")
        return short("time") + (f" to {short('time1')}" if self._t1() is not None else "")

    def _set_times(self, k):
        """The Time lists offer run k's outputs (the nearest to the times shown)."""
        o = self.ed._time_opts(k)
        cur, cur1 = self.w["time"].value, self._t1()
        with held(self.ed):
            self.w["time"].options = o
            self.w["time"].value = self.ed._nearest(o, cur)
            if "time1" in self.w:
                self.w["time1"].options = self._to_opts(o)
                self.w["time1"].value = ONE_TIME if cur1 is None else \
                    self.ed._nearest(o, cur1)

    def _on_run(self, ev):
        if self.ed._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
            return
        self._set_times(ev.new)
        self._show()
        self.ed.request()

    def _changed(self):
        r = self.w.get("region")
        if r is not None and r.value == "box" and self.box is None:
            self.box = [float(v) for v in self.ed.v.view]
        self._show()
        self.ed.request()

    def _entry(self):
        """The spec entry's keys every such card has (run, time, panel, label, colour)."""
        w = self.w
        e = dict(run=int(w["run"].value or 0), time_s=float(w["time"].value or 0.0))
        if "time1" in w:
            e["time_s1"] = self._t1()
        return dict(e, panel=max(0, int(w["panel"].value or 1) - 1), label=w["label"].value,
                    color="" if w["auto_color"].value else w["color"].value)
