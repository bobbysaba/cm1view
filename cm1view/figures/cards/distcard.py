"""The card of one distribution of a distribution figure, and the row of one
annotation (Annotate tab)."""

import panel as pn

from ...core import dist
from .. import draw as figdraw
from ...viewer.numinput import FloatInput
from .base import (
    _hex, _f, _num, _grid, _hint, _fold, SER_REGIONS, ANN_KINDS, ANN_FIELDS, _BTN, _chk,
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
        w["lo"] = FloatInput(  # (0 is a limit here, not blank)
            name="Only values from", value=r.get("lo"), placeholder="all", width=120,
            description="Keep values at or above this (blank: no limit), e.g. 1 m/s for "
                        "updrafts")
        w["hi"] = FloatInput(name="to", value=r.get("hi"), placeholder="all",
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
        w["panel"] = pn.widgets.TextInput(name="Panels (blank: all)", width=120,
                                          value=panels_text(a.get("panel", -1)),
                                          placeholder="all, or 1, 3-4")
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
        p = parse_panels(w["panel"].value)
        ps = [p] if isinstance(p, int) else p
        where = "every panel" if p == -1 else \
            ("panels " if len(ps) > 1 else "panel ") + \
            ", ".join(figdraw.panel_letter(q, "{a}") for q in ps)
        txt = f" “{w['text'].value}”" if "text" in use and w["text"].value else ""
        self.title.object = f"<b>{kind}</b>{txt} · {where}"

    def _changed(self):
        self._show()
        self.ed.request()

    def collect(self):
        w = self.w
        a = dict(kind=w["kind"].value, panel=parse_panels(w["panel"].value),
                 color=w["color"].value)
        for k in ANN_FIELDS[a["kind"]]:
            v = w[k].value
            a[k] = float(v or 0.0) if isinstance(w[k], pn.widgets.FloatInput) else v
        return a


def parse_panels(text):
    """An annotation's "panel" from the Panels box (panels counted from 1): -1 (blank,
    "all" or 0: every panel), one panel index, or a sorted list of them ("1, 3-4" ->
    [0, 2, 3]); what is not a number or a range is left out."""
    ps = set()
    for tok in str(text or "").replace(",", " ").split():
        lo, _, hi = tok.partition("-")
        try:
            lo, hi = int(lo), int(hi or lo)
        except ValueError:
            continue
        ps.update(range(min(lo, hi), max(lo, hi) + 1))
    if not ps or min(ps) <= 0:
        return -1
    ps = sorted(q - 1 for q in ps)
    return ps[0] if len(ps) == 1 else ps


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
        out.append(f"{ps[i] + 1}" if j == i else f"{ps[i] + 1}-{ps[j] + 1}")
        i = j + 1
    return ", ".join(out)
