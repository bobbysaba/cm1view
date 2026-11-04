"""Figure editor cards: the choices and constants, small widget helpers, and the parts that
several cards share (buttons, region, heights, look, colours, ensemble)."""

import json
import math
import re
from contextlib import contextmanager

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
              "track": "Storm track", "line": "Section line", "sector": "Sector",
              "parcels": "Parcels"}
PAR_TAILS = {"Up to the panel time": "until", "All parcel times": "all",
             "Last minutes": "last", "None (heads only)": "none"}
PAR_MOVING = {"The grid": "grid", "Moving with the tracked storm": "track",
              "Moving at a motion": "motion"}
PAR_XS_TAILS = {"Their parts near it": "near", "Whole, of parcels near it now": "whole"}
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


_GRID_N = [3]  # (columns of a _grid unless it says)


@contextmanager
def grid_columns(n):
    """The cards built meanwhile lay their settings out in n columns (a narrower pane)."""
    _GRID_N.append(n)
    try:
        yield
    finally:
        _GRID_N.pop()


def _grid(*objs, n=None):
    """Widgets in n equal columns (a CSS grid), each filling its cell; (widget, k)
    spans k columns.  Everything sits on the cell's bottom line, so checkboxes and
    buttons line up with the input boxes beside them; hidden widgets leave no gap."""
    n = _GRID_N[-1] if n is None else n
    items = []
    for o in objs:
        o, span = o if isinstance(o, tuple) else (o, 1)
        span = min(span, n)
        o.width = None
        o.sizing_mode = "stretch_width"
        st = {"align-self": "end"}
        if span > 1:
            st["grid-column"] = f"span {span}"
        o.styles = dict(o.styles or {}, **st)
        if isinstance(o, pn.widgets.Checkbox):
            o.margin = (5, 6, 12, 6)
        items.append(o)
    # (inside a plain column: bokeh hides with a ":host {display: none}" stylesheet,
    # which the grid's inline display would override, so .visible = False did nothing)
    return pn.Column(_cells(items, n), sizing_mode="stretch_width", margin=0)


def _cells(objs, n):
    """A column laid out as n equal grid columns, holding those of objs that are shown (a
    hidden one is not sent to the browser).  Panel puts an invisible scroll button among a
    Column's children, and a widget shown later lands after it: in a grid the button takes
    a cell, which left a hole in the options, so it is taken out of the layout."""
    grid = pn.Column(*objs, sizing_mode="stretch_width", margin=0,
                     stylesheets=[".scroll-button { display: none !important; }"], styles={
                         "display": "grid", "column-gap": "2px",
                         "grid-template-columns": f"repeat({n}, minmax(0, 1fr))"})
    _follow_shown(grid, objs)
    return grid


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
        grid = _cells(bs, n)
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


HINT_SHORT = 120  # (characters of a hint shown whole; a longer one folds after its first sentence)


def _hint_html(text):
    """A hint's HTML: a long one is its first sentence, which opens to show the rest (in
    the browser alone: no widgets, no round trip)."""
    if len(re.sub(r"<[^>]+>", "", text)) > HINT_SHORT:
        depth = 0  # (not inside a tag such as <code>a. b</code>)
        for m in re.finditer(r"<(/?)[a-zA-Z][^>]*>|(?<!e\.g)(?<!i\.e)\.\s+(?=\S)", text):
            if m.group(0).startswith("<"):
                depth += -1 if m.group(1) else 1
            elif depth == 0:
                return (f'<details class="cv-hint"><summary>{text[:m.start() + 1]}</summary>'
                        f'{text[m.end():]}</details>')
    return f'<div class="cv-hint">{text}</div>'


def _hint(text, margin=(4, 4, 2, 4)):
    return pn.pane.HTML(_hint_html(text), margin=margin, sizing_mode="stretch_width")


def _when(chk, *objs):
    """objs are shown while the checkbox chk is ticked."""
    def show(*e):
        for o in objs:
            o.visible = bool(chk.value)
    chk.param.watch(show, "value")
    show()


def _when_shown(chk, *objs):
    """objs are shown while the checkbox chk is ticked and itself shown."""
    def show(*e):
        for o in objs:
            o.visible = bool(chk.visible and chk.value)
    chk.param.watch(show, ["value", "visible"])
    show()


def _retired(w):
    """A setting that has a better home now, kept for the saved figures that use it: w is
    shown only while it is not zero (set to 0 it goes, and stays gone)."""
    def show(*e):
        w.visible = bool(w.value)
    w.param.watch(show, "value")
    show()
    return w


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


def set_folded(card, folded):
    """Fold or unfold a _fold card, as its chevron does."""
    if card.body.visible == folded:
        card.panel.objects[0].objects[0].clicks += 1


def _plain(x):
    """x as JSON would give it back (lists for tuples; 1 and 1.0 compare equal)."""
    return json.loads(json.dumps(x, default=float))


def _read_card(card):
    """What card collects, plainly; None when its settings are incomplete."""
    try:
        return _plain(card.collect())
    except Exception:  # noqa: BLE001  (undo must not stop at a half-typed card)
        return None


def kept_cards(old, ents, make, same=True, load=None):
    """Undo's cards for entries ents, from the cards shown (old).  A card already showing
    its entry stays as it is, wherever it was (with same: nothing else it lists has
    changed, such as the runs).  The others take the folding of the card that was in
    their place; load(card, entry, folded), if given, reuses a card of that place and says
    whether it could, else make(entry) builds one."""
    free = set(range(len(old)))
    out = [None] * len(ents)
    if same:
        read = [_read_card(c) for c in old]
        wanted = [_plain(e) for e in ents]
        if len(old) == len(ents):  # (nothing added or removed: each in its place first)
            for j, p in enumerate(wanted):
                if read[j] == p:
                    out[j] = old[j]
                    free.discard(j)
        at = 0  # (then the next card in order: alike cards keep their order)
        for j, p in enumerate(wanted):
            if out[j] is None:
                k = next((k for k in sorted(free, key=lambda k: (k < at, k))
                          if read[k] == p), None)
                if k is not None:
                    out[j] = old[k]
                    free.discard(k)
                    at = k + 1
    for j, e in enumerate(ents):
        if out[j] is not None:
            continue
        near = old[j] if j < len(old) else None
        folded = near is not None and not near.body.visible
        if load is not None and j in free and load(near, e, folded):
            out[j] = near
            free.discard(j)
        else:
            out[j] = make(e)
            set_folded(out[j], folded)
    return out


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


def _panel_tok(i):
    """Panel i (from 0) as typed: its letter (past z, where letters repeat: its number)."""
    return figdraw.panel_letter(int(i), "{a}") if int(i) < 26 else str(int(i) + 1)


def _panels_text(panels):
    return ", ".join(_panel_tok(i) for i in panels or [])


def _panels_loose(text):
    """Like _panels_parse, also split by spaces, leaving out what is not a panel."""
    out = set()
    for tok in str(text or "").replace(",", " ").split():
        try:
            out.update(_panels_parse(tok))
        except ValueError:
            continue
    return sorted(out)


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
SER_OPS = {"None": "", "d/dz (per m)": "ddz", "d/dt (per s)": "ddt"}
MARKERS = {"none": "", "dots": "o", "squares": "s", "triangles": "^"}
LINE_STYLES = {"Solid": "-", "Dashed": "--", "Dotted": ":", "Dash-dot": "-."}
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


# ------------------------------------------------------------ parts that cards share
ENS_BANDS = {"Off": "", "Min to max": "minmax", "10–90th percentile": "p10p90",
             "25–75th percentile": "p25p75", "Mean ± 1 sd": "sd"}
ENS_MIDS = {"Mean": "mean", "Median": "median", "None": ""}
ENS_MEMBERS = {"Faint": "faint", "Hidden": "hidden", "As other lines": "full"}


def known_cmap(name):
    """name if the Colormap lists offer it, else viridis."""
    return name if name in FIG_CMAPS else "viridis"


def cmap_select(value="viridis"):
    return pn.widgets.Select(name="Colormap", options=FIG_CMAPS, value=known_cmap(value))


def card_buttons(card, remove, moves=False, dup=False, per_run=""):
    """A card's buttons: card.rm (tooltip `remove`), with moves card.up and card.down, with
    dup card.dup, and with per_run (its tooltip) card.per_run."""
    card.rm = pn.widgets.Button(name="✕", description=remove, **_BTN)
    if moves:
        card.up = pn.widgets.Button(name="↑", description="Earlier in the list", **_BTN)
        card.down = pn.widgets.Button(name="↓", description="Later in the list", **_BTN)
    plain = dict(height=32, button_type="light", button_style="outline")
    if dup:
        card.dup = pn.widgets.Button(name="Duplicate", **plain,
                                     description="A copy of this card in a new panel")
    if per_run:
        card.per_run = pn.widgets.Button(name="One per run", description=per_run, **plain)


def run_widget(ed, ent):
    """The Run list of a card of one run: entry ent's, if the figure has it."""
    names = ed._run_names()
    k = int(ent.get("run") or 0)
    return pn.widgets.Select(name="Run", value=k if k in names.values() else 0, width=170,
                             **ed._run_choices(names))


PANEL_CHOICES = {  # (a grid has at most 8 × 8 cells; letters repeat past z, as drawn)
    figdraw.panel_letter(i, "{a}") if i < 26 else f'{figdraw.panel_letter(i, "{a}")} ({i + 1})':
    i + 1 for i in range(64)}


def panel_select(name="Panel", value=1, width=70):
    """A list of the panels by letter; its value is counted from 1."""
    return pn.widgets.Select(name=name, options=PANEL_CHOICES, width=width,
                             value=min(max(int(value), 1), 64))


def panel_widget(ent):
    """The Panel list of a card (counted from 1; the spec's from 0: panel_index)."""
    return panel_select(value=int(ent.get("panel") or 0) + 1)


def panel_index(w):
    return max(0, int(w["panel"].value or 1) - 1)


def panel_tag(w):
    """The letter of a card's panel."""
    return figdraw.panel_letter(panel_index(w), "{a}")


def where_grid(card, *objs):
    """The first row of a card: objs (its run, time ...), its Panel and its buttons."""
    return _grid(*objs, card.w["panel"], *[b for b in (getattr(card, "dup", None),
                                                       getattr(card, "per_run", None)) if b])


def label_widget(ent, name="Legend text (blank: automatic)", default=""):
    return pn.widgets.TextInput(name=name, value=ent.get("label", default), width=220)


def field_widget(F, name, label="Field"):
    """A Field list, at field `name` if there is such a field (else the first)."""
    return pn.widgets.Select(name=label, groups=F.groups(), width=210,
                             value=name if name in F else next(iter(F.defs)))


def layer_widgets(w, r):
    """The layer a recipe r reads: Read from, Read to."""
    w["z0"] = _f("Read from (km)", float(r.get("z0", 0.0)), 90, step=0.5)
    w["z1"] = _f("Read to (km)", float(r.get("z1", 10.0)), 80, step=0.5)


def vertical_widgets(w, r, modes, other):
    """Where a recipe r reads: Vertical (modes; other: when r's is not one of them),
    its Height and its layer."""
    w["vmode"] = pn.widgets.Select(name="Vertical", options=modes, width=170,
                                   value=r["vmode"] if r["vmode"] in modes.values() else other)
    w["z"] = _f("Height (km)", float(r.get("z", 1.0)), 90, step=0.25)
    layer_widgets(w, r)


def vertical_recipe(w):
    """A recipe's heights, of those the card has."""
    return {k: w[k].value or 0.0 for k in ("z", "z0", "z1") if k in w}


def region_widgets(card, r):
    """The region of a recipe r: Region, with its radius and offset around the storm; a
    fixed box is kept in card.box (keep_box)."""
    w = card.w
    card.box = r.get("box")
    w["region"] = pn.widgets.Select(name="Region", options=SER_REGIONS, value=r["region"],
                                    width=180)
    w["radius"] = _f("Radius (km)", float(r.get("radius", 5.0)), 90, step=0.5)
    off = r.get("offset") or (0.0, 0.0)
    w["offx"] = _f("Offset x (km)", float(off[0]), 100, step=1.0)
    w["offy"] = _f("Offset y (km)", float(off[1]), 100, step=1.0)


def show_region(w):
    w["radius"].visible = w["offx"].visible = w["offy"].visible = w["region"].value == "track"


def keep_box(card):
    """A fixed box starts as the map's view."""
    r = card.w.get("region")
    if r is not None and r.value == "box" and card.box is None:
        card.box = [float(v) for v in card.ed.v.view]


def region_recipe(card):
    w = card.w
    return dict(region=w["region"].value, radius=w["radius"].value or 5.0,
                offset=(w["offx"].value or 0.0, w["offy"].value or 0.0),
                box=card.box or [float(v) for v in card.ed.v.view])


def reduce_widgets(w, r):
    w["reduce"] = pn.widgets.Select(name="Reduce", options=SER_REDUCE, value=r["reduce"],
                                    width=120)
    w["pct"] = _f("Percentile", float(r.get("pct", 99.0)), 90, step=0.5)


def reduce_recipe(w):
    return dict(reduce=w["reduce"].value,
                pct=w["pct"].value if w["pct"].value is not None else 99.0)


def look_widgets(w, ent, auto=False, ls=None, lw=None, marker=False, axis=False):
    """How an entry ent draws: Colour, with auto Automatic colour, with ls (the choices)
    Line style, with lw (a default) Line width, then Markers and the y axis."""
    if auto:
        w["auto_color"] = _chk("Automatic colour", not ent.get("color"))
    w["color"] = pn.widgets.ColorPicker(name="Colour", value=_hex(ent.get("color") or "k"),
                                        width=70)
    if ls:
        w["ls"] = pn.widgets.Select(name="Line style", options=ls, width=100,
                                    value=ent.get("ls") if ent.get("ls") in ls.values()
                                    else next(iter(ls.values())))
    if lw:
        w["lw"] = _f("Line width", float(ent.get("lw") or lw), 90, step=0.25)
    if marker:
        w["marker"] = pn.widgets.Select(name="Markers", options=MARKERS,
                                        value=ent.get("marker", ""), width=100)
    if axis:
        w["axis"] = pn.widgets.Select(name="y axis", options={"By units": "auto",
                                                              "Own axis (right)": "right"},
                                      value=ent.get("axis", "auto"), width=140)
        w["ylabel"] = pn.widgets.TextInput(name="Axis label (blank: units)",
                                           value=ent.get("ylabel", ""), width=180)


def look_values(w, lw=1.5):
    """The spec's keys of look_widgets (lw: a blank Line width's)."""
    auto = "auto_color" in w and w["auto_color"].value
    v = dict(color="" if auto else w["color"].value,
             **{k: w[k].value for k in ("ls", "marker", "axis", "ylabel") if k in w})
    if "lw" in w:
        v["lw"] = float(w["lw"].value or lw)
    return v


def color_widgets(w, ent):
    """A shaded entry's colours and colorbar (a fill layer, a time-height series)."""
    w["cmap"] = cmap_select(ent["cmap"])
    w["reverse"] = _chk("Reverse", ent.get("reverse", False))
    w["white_first"] = _chk("Start from white", ent.get("white_first", False))
    w["vmin"] = _f("Min", ent["vmin"])
    w["vmax"] = _f("Max", ent["vmax"])
    w["nlevels"] = pn.widgets.IntInput(name="Colour steps (0: smooth)", start=0, end=60,
                                       value=int(ent.get("nlevels") or 0))
    w["extend"] = pn.widgets.Select(name="Colorbar arrows", options=EXTEND,
                                    value=ent.get("extend", "neither"))
    w["cbar_label"] = pn.widgets.TextInput(
        name="Colorbar label (blank: Style's, else units)", value=ent.get("cbar_label", "") or "",
        placeholder=ent.get("units", ""),
        description="Sets the colorbar of this panel. Panels sharing a colorbar: the first "
                    "label among them")
    w["cbar_ticks"] = pn.widgets.TextInput(
        name="Colorbar ticks (blank: Style's, else auto)",
        value=ent.get("cbar_ticks", "") or "", placeholder="0:60:10")


def band_opacity(ent):
    return _f("Band opacity", float(ent.get("ens_alpha", 0.25)), 100, step=0.05, start=0.0,
              end=1.0)


def ens_widgets(w, ent):
    """An ensemble band over a card's runs."""
    w["ens"] = pn.widgets.Select(name="Ensemble of its runs", options=ENS_BANDS,
                                 value=ent.get("ens", ""), width=170)
    w["ens_mid"] = pn.widgets.Select(name="Centre line", options=ENS_MIDS,
                                     value=ent.get("ens_mid", "mean"), width=100)
    w["ens_members"] = pn.widgets.Select(name="Runs' own lines", options=ENS_MEMBERS,
                                         value=ent.get("ens_members", "faint"), width=130)
    w["ens_alpha"] = band_opacity(ent)


def show_ens(w, several):
    w["ens"].visible = several
    for k in ("ens_mid", "ens_members", "ens_alpha"):
        w[k].visible = several and bool(w["ens"].value)


def ens_values(w):
    a = w["ens_alpha"].value
    return dict(ens=w["ens"].value, ens_mid=w["ens_mid"].value,
                ens_members=w["ens_members"].value, ens_alpha=float(a if a is not None else 0.25))


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


def wanted_time(card, key, opts, dt):
    """The time (s) card wants in its list w[key] of outputs opts after moving by dt s:
    what it wanted before while that still shows, else what it shows."""
    wants = card.__dict__.setdefault("_want", {})
    cur, want = float(card.w[key].value), wants.get(key)
    if want is None or card.ed._nearest(opts, want) != cur:
        want = cur
    wants[key] = want + dt
    return wants[key]


def hold_value(w):
    """The spec's key of a card's "Keep this time in animations" (only when ticked)."""
    return {"time_lock": True} if w["hold"].value else {}


class TimeCard:
    """The run and time of a card of one entry (a sounding, distribution, joint
    distribution, azimuthal mean or profile), and its time window when it has a "to"
    time (w["time1"])."""

    @staticmethod
    def _to_opts(opts):
        return {"— (this time only)": ONE_TIME} | dict(opts)

    def _run_time_widgets(self, to=None, about=""):
        """The Run list (w["run"], of one run) and its Time lists (see _time_widgets)."""
        self.w["run"] = run_widget(self.ed, self.ent)
        self._time_widgets(self.ed._time_opts(self.w["run"].value), to, about)

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
        w["hold"] = _chk("Keep this time in animations", bool(ent.get("time_lock")))

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
        return short("time") + (f" to {short('time1')}" if self._t1() is not None else "") \
            + (" (kept)" if self.w["hold"].value else "")

    def _time_run(self):
        """The run whose outputs the Time lists offer."""
        return int(self.w["run"].value or 0)

    def move_time(self, dt):
        """The card's times moved by dt s (a run's time zero changed), to the nearest
        outputs; what it wants is kept apart from what they show, so small steps add up."""
        o = self.ed._time_opts(self._time_run())
        t1 = self._t1()
        with held(self.ed):
            self.w["time"].value = self.ed._nearest(o, wanted_time(self, "time", o, dt))
            if t1 is not None:
                self.w["time1"].value = self.ed._nearest(o, wanted_time(self, "time1", o, dt))
        self._show()

    def _set_times(self, k, k0=None):
        """The Time lists offer run k's outputs: the nearest to the times shown, or with
        k0 (the run they were of) to the same time since each run's time zero."""
        o = self.ed._time_opts(k)
        cur, cur1 = self.w["time"].value, self._t1()
        if k0 is not None and cur is not None:
            cur = self.ed._moved_time(cur, k0, k)
            cur1 = None if cur1 is None else self.ed._moved_time(cur1, k0, k)
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
        self._set_times(ev.new, ev.old if isinstance(ev.old, int) else None)
        self._show()
        self.ed.request()

    def _changed(self):
        keep_box(self)
        self._show()
        self.ed.request()

    def _entry(self, lw=1.5):
        """The spec entry's keys every such card has (run, time, panel, label, its look;
        lw: a blank Line width's)."""
        w = self.w
        e = dict(run=int(w["run"].value or 0), time_s=float(w["time"].value or 0.0))
        if "time1" in w:
            e["time_s1"] = self._t1()
        return dict(e, panel=panel_index(w), label=w["label"].value, **look_values(w, lw),
                    **hold_value(w))
