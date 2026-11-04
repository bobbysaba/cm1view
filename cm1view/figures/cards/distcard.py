"""The card of one distribution of a distribution figure, and the row of one
annotation."""

import panel as pn

from ...core import dist
from .. import draw as figdraw
from ...viewer.numinput import FloatInput
from .base import (
    _hex, _f, _num, _grid, _hint, _fold, ANN_KINDS, ANN_FIELDS, _BTN, _chk, TimeCard,
    LINE_STYLES, _panel_tok, _panels_loose, card_buttons, field_widget, label_widget,
    look_widgets, panel_tag, panel_widget, region_recipe, region_widgets, show_region,
    vertical_recipe, vertical_widgets, where_grid,
)


DIST_VMODES = {"At a height": "height", "Layer (every level)": "layer",
               "Every level (whole depth)": "all"}
DIST_PLOTS = {"Histogram": "hist", "Box plot": "box", "Violin": "violin",
              "Cumulative (ECDF)": "ecdf"}
DIST_NORMS = {"Count": "count", "PDF (density)": "pdf", "Fraction": "frac"}
DIST_HSTYLES = {"Filled outline": "stepfilled", "Outline": "step", "Bars": "bar"}
DIST_CUM = {"At or below x": "below", "Above x (exceedance)": "above"}
DIST_BAR_LABELS = {"None": "", "Count": "count", "Percent of the sample": "percent",
                   "Value (as the count axis)": "axis"}
DIST_STATS_AT = {"In the legend (box plots: under the boxes)": "legend",
                 "In a box in the panel": "box"}
DIST_WHIS = {"1.5 × IQR (Tukey)": "tukey", "Min – max": "range", "5th – 95th percentile": "p5",
             "1st – 99th percentile": "p1"}


class DistCard(TimeCard):
    """One distribution of a distribution figure: run, time, a dist recipe (field,
    height, layer or whole depth, region, value limits), look and panel."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.w = w = {}
        card_buttons(self, "Remove the distribution", dup=True)
        self._run_time_widgets()
        w["field"] = field_widget(F, r["field"])
        vertical_widgets(w, r, DIST_VMODES, "height")
        region_widgets(self, r)
        w["lo"] = FloatInput(  # (0 is a limit here, not blank)
            name="Only values from", value=r.get("lo"), placeholder="all", width=120,
            description="Keep values at or above this (blank: no limit), e.g. 1 m/s for "
                        "updrafts")
        w["hi"] = FloatInput(name="to", value=r.get("hi"), placeholder="all",
                                        width=90)
        w["label"] = label_widget(ent)
        look_widgets(w, ent, auto=True)
        w["panel"] = panel_widget(ent)
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k not in ("run", "panel"):
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: (self._show(), ed._fit_grid(), ed.request()), "value")
        self.title = pn.pane.HTML("<b>Distribution</b>", margin=(6, 4, 0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [where_grid(self, w["run"], (w["time"], 2), w["hold"]),
             _grid((w["field"], 2), w["vmode"], w["z"], w["z0"],
                   w["z1"], w["region"], w["radius"], w["offx"], w["offy"], w["lo"], w["hi"],
                   w["auto_color"], w["color"], (w["label"], 3)),
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
        show_region(w)
        w["color"].visible = not w["auto_color"].value
        d = self.ed.fields[w["field"].value]
        self.title.object = (f"<b>Distribution</b> · {d.label} · {self._when()} · panel "
                             f"{panel_tag(w)}")

    def recipe(self):
        w, d = self.w, self.ed.fields[self.w["field"].value]
        return dist.normalize(dict(
            field=d.name, vmode="2d" if d.ndim == 2 else w["vmode"].value,
            **vertical_recipe(w), **region_recipe(self),
            lo=_num(w["lo"].value), hi=_num(w["hi"].value)))

    def collect(self):
        return dict(self._entry(), recipe=self.recipe())


class AnnotationRow:
    """One annotation: text, marker, arrow, line, box or circle in one panel or all, or
    an entry of its own in their legends ("legend")."""

    def __init__(self, ed, a):
        self.ed = ed
        self.w = w = {}
        w["kind"] = pn.widgets.Select(name="Kind", options=ANN_KINDS, value=a.get("kind", "text"),
                                      width=130)
        w["panel"] = self._panel_widget(a)
        w["coords"] = pn.widgets.Select(name="Position in", options={
            "Axis units (km, min)": "data", "Panel fraction (0–1)": "axes"},
            value=a.get("coords", "data"), width=170)
        for k, lab in (("x", "x"), ("y", "y"), ("x2", "x to"), ("y2", "y to"),
                       ("r", "Radius")):
            w[k] = _f(lab, float(a.get(k, 0.0 if k != "r" else 1.0)), 80, step=0.5)
        w["text"] = pn.widgets.TextInput(name="Text", value=a.get("text", ""), width=150)
        w["size"] = _f("Size", float(a.get("size") or 10.0), 70, step=1)
        w["lw"] = _f("Line width", float(a.get("lw", 1.5)), 90, step=0.25)
        w["ls"] = pn.widgets.Select(name="Line style", options=LINE_STYLES,
                                    value=a.get("ls", "-" if a.get("kind") not in
                                                ("vline", "hline") else "--"), width=90)
        w["marker"] = pn.widgets.Select(name="Marker", options={
            "×": "x", "+": "+", "●": ".", "○": "o", "□": "s", "★": "*", "▲": "^"},
            value=a.get("marker", "x"), width=80)
        w["look"] = pn.widgets.Select(name="Looks like", options={
            "Line": "line", "Marker": "marker", "Line and marker": "both",
            "Filled box": "patch"}, value=a.get("look", "line"), width=130)
        w["alpha"] = _f("Opacity", float(a.get("alpha", 1.0)), 80, step=0.1)
        w["bold"] = _chk("Bold", a.get("bold", False))
        w["color"] = pn.widgets.ColorPicker(name="Colour", value=_hex(a.get("color", "k")),
                                            width=70)
        self.rm = pn.widgets.Button(name="✕", description="Remove", **_BTN)
        for k, x in w.items():
            x.param.watch(lambda e: self._changed(), "value")
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self.panel, self.body = _fold([self.title, pn.Spacer(), self.rm], [_grid(*w.values())])
        self._show()

    def _panel_widget(self, a):
        return pn.widgets.TextInput(name="Panels (blank: all)", width=120,
                                    value=panels_text(a.get("panel", -1)),
                                    placeholder="all, or a, c-d")

    def _panels(self):
        """The annotation's "panel", as the panels widget has it."""
        return parse_panels(self.w["panel"].value)

    def _where(self):
        """The panels it is in, in words."""
        p = self._panels()
        ps = [p] if isinstance(p, int) else p
        return "every panel" if p == -1 else \
            ("panels " if len(ps) > 1 else "panel ") + \
            ", ".join(figdraw.panel_letter(q, "{a}") for q in ps)

    def _show(self):
        w = self.w
        use = ANN_FIELDS[w["kind"].value]
        for k, x in w.items():
            if k not in ("kind", "panel", "color"):
                x.visible = k in use
        if w["kind"].value == "legend":  # (what its look draws)
            look = w["look"].value
            w["marker"].visible = look in ("marker", "both")
            w["ls"].visible = look != "marker"
            w["alpha"].visible = look == "patch"
        kind = next(k for k, v in ANN_KINDS.items() if v == w["kind"].value)
        txt = f" “{w['text'].value}”" if "text" in use and w["text"].value else ""
        self.title.object = f"<b>{kind}</b>{txt} · {self._where()}"

    def _changed(self):
        self._show()
        self.ed.request()

    def collect(self):
        w = self.w
        a = dict(kind=w["kind"].value, panel=self._panels(), color=w["color"].value)
        for k in ANN_FIELDS[a["kind"]]:
            v = w[k].value
            a[k] = float(v or 0.0) if isinstance(w[k], pn.widgets.FloatInput) else v
        return a


def parse_panels(text):
    """An annotation's "panel" from the Panels box (letters or numbers from 1): -1 (blank,
    "all" or 0: every panel), one panel index, or a sorted list of them ("a, c-d" and
    "1, 3-4" -> [0, 2, 3]); what is not a panel or a range of them is left out."""
    toks = str(text or "").replace(",", " ").split()
    if any(int(n) <= 0 for t in toks for n in t.split("-") if n.isdigit()):
        return -1
    ps = _panels_loose(text)
    return -1 if not ps else ps[0] if len(ps) == 1 else ps


def panels_text(p):
    """The Panels box's text of an annotation's "panel" (the inverse of parse_panels)."""
    ps = sorted(int(q) for q in p) if isinstance(p, (list, tuple)) else [int(p)]
    if not ps or -1 in ps:
        return ""
    out, i = [], 0
    while i < len(ps):  # runs of consecutive panels as ranges
        j = i
        while j + 1 < len(ps) and ps[j + 1] == ps[j] + 1:
            j += 1
        out.append(_panel_tok(ps[i]) if j == i else f"{_panel_tok(ps[i])}-{_panel_tok(ps[j])}")
        i = j + 1
    return ", ".join(out)
