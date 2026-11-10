"""The five profile panels under the skew-T, drawn in the browser (Bokeh) like the
skew-T (viewer.skewt_view): built once, a new sounding sends only the profile arrays
and the styles of the lines.  The panels share one height axis; zoom, pan, hover and
saving are Bokeh's own tools.

payload() (numpy only, in a worker) and ProfilesView.apply(payload) (on the page's
thread)."""

import numpy as np
import panel as pn
from bokeh.models import (
    BoxZoomTool, ColumnDataSource, CustomJS, HoverTool, Legend, LegendItem, PanTool,
    Range1d, ResetTool, SaveTool, WheelZoomTool,
)
from bokeh.plotting import figure

from ..core import sounding_plot as sp
from ..theme import ACCENT, BG, GRID, TEXT
from .skewt_view import DASHES, NS, _cell, _f, _quiet
from .ui import _bokeh, style_fig

PANELS = sp.PROFILE_PANELS
LINES = [  # (panel, name, source 'm' (mid-levels) or 'z', column, colour key, width factor)
    (0, "sr", "m", "sr", "main", 1.0),
    (1, "sh", "m", "sh", "main", 1.0),
    (2, "ws", "m", "ws", "ws", 1.0),
    (2, "wc", "m", "wc", "wc", 0.8),
    (3, "srh", "z", "srh", "main", 1.0),
    (4, "th", "z", "th", "th", 1.0),
    (4, "the", "z", "the", "the", 0.8),
]
QCOLS = ("main", "ws", "wc", "th", "the")

# one fit per panel (x) and one for the shared height axis (y): kept when the person
# zoomed or panned away from the last fit and the key (units, profile top) is unchanged
FIT_JS = """
const d = fit.data;
if (!d.x0 || !d.x0.length || !figs.every((f) => f.inner_width > 0 && f.inner_height > 0)) return;
const near = (a, b) => Math.abs(a - b) <= 1e-6 * Math.max(1, Math.abs(a), Math.abs(b));
const stale = (r, key) => !(r.tags.length === 3 && r.tags[2] === key);
const moved = (r) => !(near(r.start, r.tags[0]) && near(r.end, r.tags[1]));
const fitRange = (r, a, b, key) => {
  if (!Number.isFinite(a) || !Number.isFinite(b)) return;
  if (stale(r, key) || !moved(r)) r.setv({start: a, end: b, reset_start: a, reset_end: b});
  else r.setv({reset_start: a, reset_end: b});
  r.tags = [a, b, key];
};
const key = d.key[0];
fitRange(figs[0].y_range, d.y0[0], d.y1[0], key);
figs.forEach((f, i) => fitRange(f.x_range, d.x0[i], d.x1[i], key));
"""


def _slot(r):
    pf, pr = r["profiles"], r["prof"]
    zm, z = _f(pf["zm"]) / 1000.0, _f(pf["z"]) / 1000.0
    return zm, z, dict(sr=_f(pf["sr_speed"]), sh=_f(pf["shear"]) * 1e3,
                       ws=_f(pf["ws"]) * 1e3, wc=_f(pf["wc"]) * 1e3,
                       srh=_f(pf["cum_srh"]), th=_f(pr["th"]), the=_f(pr["the"]))


def payload(items, base=None, zmax=6.0, units="m/s", style="lines", look=None):
    """The data and styles of the panels for these soundings ((label, colour, result)
    from thermo.analyze; at most NS)."""
    lk = sp._st(look)
    wf = sp._wfac(units)
    items = list(items)[:NS]
    single = len(items) == 1
    by_color = style == "colors" and not single
    qcol = dict(main=ACCENT, ws=sp.QCOL["ws"], wc=sp.QCOL["wc"], th=lk["t_color"],
                the=lk["td_color"])
    out = dict(slots=[], styles=[], units=units, single=single, by_color=by_color,
               zmax=float(zmax), base=None)
    cols = [[] for _ in PANELS]  # (x, z) arrays per panel, for the x fit

    def slot(r, label):
        zm, z, c = _slot(r)
        c["sr"] = c["sr"] * wf
        m = dict(zm=zm, sr=c["sr"], sh=c["sh"], ws=c["ws"], wc=c["wc"], label=[label] * zm.size)
        zz = dict(z=z, srh=c["srh"], th=c["th"], the=c["the"], label=[label] * z.size)
        for (pn_, name, src, col, _, _) in LINES:
            cols[pn_].append((c[col], zm if src == "m" else z))
        return dict(m=m, z=zz)

    for n, (label, color, r) in enumerate(items):
        out["slots"].append(slot(r, label))
        if by_color:
            q = dict.fromkeys(QCOLS, color)
            da, db = [], [2, 3]
        else:
            q, da = qcol, DASHES[n]
            db = da
        out["styles"].append(dict(q=q, dash_a=da, dash_b=db, lw=lk["prof_lw"], label=label))
    if base is not None:
        out["base"] = slot(base, "Base state")
        out["base_style"] = dict(q=dict.fromkeys(QCOLS, lk["base_color"]), dash_a=[6, 4],
                                 dash_b=[2, 3], lw=1.2)
    # x from the heights in view, ignoring the lowest 100 m (surface-layer shear would
    # squash the rest)
    fit = dict(x0=[], x1=[], y0=[], y1=[], key=[])
    for pn_ in range(len(PANELS)):
        xs = []
        for x, z in cols[pn_]:
            s = (z <= zmax) & (z >= 0.1) & np.isfinite(x)
            if s.any() and x.size > 2:
                xs += [x[s].min(), x[s].max()]
        lo, hi = (min(xs), max(xs)) if xs else (0.0, 1.0)
        pad = 0.06 * (hi - lo or 1.0)
        fit["x0"].append(float(lo - pad)), fit["x1"].append(float(hi + pad))
        fit["y0"].append(0.0), fit["y1"].append(float(zmax))
        fit["key"].append(f"{units}|{zmax}")
    out["fit"] = fit
    out["qcol"] = qcol
    out["legend"] = dict(
        ws=(TEXT if by_color else qcol["ws"], "-"), wc=(TEXT if by_color else qcol["wc"],
                                                       ":" if by_color else "-"),
        th=(TEXT if by_color else qcol["th"], "-"), the=(TEXT if by_color else qcol["the"],
                                                         ":" if by_color else "-"))
    return out


def _empty(kind):
    cols = ("zm", "sr", "sh", "ws", "wc", "label") if kind == "m" else \
        ("z", "srh", "th", "the", "label")
    return {c: [] for c in cols}


class ProfilesView:
    """The five profile panels on the page.  .panel goes on the page; apply(payload(...))
    shows soundings."""

    def __init__(self, height=330):
        yr = Range1d(0.0, 6.0)
        self.figs = []
        for i, (title, xl) in enumerate(PANELS):
            f = figure(x_range=Range1d(0.0, 1.0), y_range=yr, height=height,
                       sizing_mode="stretch_width", tools="", toolbar_location="above",
                       x_axis_label=xl.format(units="m/s"), title=title,
                       y_axis_label="Height (km AGL)" if i == 0 else None)
            style_fig(f)
            f.toolbar.autohide = True
            f.title.text_color = TEXT
            f.title.text_font_style = "normal"
            f.title.text_font_size = "11px"
            f.xaxis.axis_label_text_font_size = "10px"
            f.min_border_left = 8 if i else 50
            f.min_border_right = 6
            if i:
                f.yaxis.visible = False
            self.figs.append(f)
        # lines: [slot n (the base state last)][name] -> renderer
        self.m = [ColumnDataSource(_empty("m")) for _ in range(NS + 1)]
        self.z = [ColumnDataSource(_empty("z")) for _ in range(NS + 1)]
        self.lines = []
        for n in range(NS + 1):
            row = {}
            for pn_, name, src, col, _, _ in LINES:
                s = (self.m if src == "m" else self.z)[n]
                row[name] = _quiet(self.figs[pn_].line(
                    col, "zm" if src == "m" else "z", source=s, line_width=1.8))
                row[name].visible = False
            self.lines.append(row)
        self._hover()
        self._legends()
        self.fit = ColumnDataSource(dict(x0=[], x1=[], y0=[], y1=[], key=[]))
        cb = CustomJS(args=dict(figs=self.figs, fit=self.fit), code=FIT_JS)
        for f in self.figs:
            f.js_on_change("inner_width", cb)
            f.js_on_change("inner_height", cb)
        self.fit.js_on_change("data", cb)
        self.panel = pn.FlexBox(
            *[_cell(_bokeh(f, sizing_mode="stretch_width", height=height),
                    "1.3 1 150px" if i == 0 else "1 1 120px")
              for i, f in enumerate(self.figs)],
            flex_wrap="wrap", gap="0px 2px", sizing_mode="stretch_width")

    def _hover(self):
        tips = [
            ("sr", "zm", "speed @sr{0.0}"),
            ("sh", "zm", "shear @sh{0.00}"),
            ("ws", "zm", "streamwise @ws{0.00} · crosswise @wc{0.00}"),
            ("srh", "z", "SRH @srh{0}"),
            ("th", "z", "θ @th{0.0} · θe @the{0.0} K"),
        ]
        for i, (name, zc, txt) in enumerate(tips):
            f = self.figs[i]
            hover = HoverTool(
                renderers=[self.lines[n][name] for n in range(NS + 1)], mode="hline",
                tooltips=f'<div style="font-size:11px"><b>@label</b><br>z @{zc}{{0.00}} km · '
                         f'{txt}</div>')
            f.add_tools(PanTool(), BoxZoomTool(), WheelZoomTool(), ResetTool(), SaveTool(),
                        hover)
            f.toolbar.active_scroll = None

    def _legends(self):
        nan = [np.nan]
        self.qdummy = {k: _quiet(self.figs[i].line(nan, nan, line_width=1.8))
                       for k, i in (("ws", 2), ("wc", 2), ("th", 4), ("the", 4))}
        kw = dict(background_fill_alpha=0.88, border_line_color=GRID,
                  label_text_color=TEXT, label_text_font_size="10px")
        for (a, b), i, loc in ((("ws", "wc"), 2, "top_right"), (("th", "the"), 4, "top_left")):
            names = dict(ws="streamwise", wc="crosswise", th="θ", the="θe")
            leg = Legend(items=[LegendItem(label=names[k], renderers=[self.qdummy[k]])
                                for k in (a, b)], location=loc, background_fill_color=BG,
                         **kw)
            self.figs[i].add_layout(leg)
        self.slegend = Legend(items=[], location="bottom_right", background_fill_color=BG,
                              **kw)
        self.figs[0].add_layout(self.slegend)

    def apply(self, d):
        """Show a payload() (on the page's thread)."""
        self.figs[0].xaxis.axis_label = PANELS[0][1].format(units=d["units"])
        keys = list(range(len(d["slots"])))
        sources = [(n, d["slots"][n], d["styles"][n]) for n in keys]
        if d["base"] is not None:
            sources.append((NS, d["base"], d["base_style"]))
        used = {n for n, _, _ in sources}
        for n, sl, st in sources:
            self.m[n].data, self.z[n].data = sl["m"], sl["z"]
            for _, name, _, _, ckey, wfac in LINES:
                r = self.lines[n][name]
                dash = st["dash_b"] if name in ("wc", "the") else st["dash_a"]
                r.glyph.update(line_color=st["q"][ckey], line_dash=dash,
                               line_width=st["lw"] * wfac)
                r.visible = True
        for n in range(NS + 1):
            if n not in used:
                for r in self.lines[n].values():
                    r.visible = False
                self.m[n].data, self.z[n].data = _empty("m"), _empty("z")
        for k, (c, ls) in d["legend"].items():
            self.qdummy[k].glyph.update(line_color=c, line_dash=[] if ls == "-" else [2, 3])
        items = []
        if not d["single"] or d["base"] is not None:
            for n, st in enumerate(d["styles"]):
                items.append(LegendItem(label=st["label"], renderers=[self.lines[n]["sr"]]))
            if d["base"] is not None:
                items.append(LegendItem(label="Base state", renderers=[self.lines[NS]["sr"]]))
        self.slegend.items = items
        self.slegend.visible = bool(items)
        self.fit.data = d["fit"]
