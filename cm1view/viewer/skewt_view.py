"""The live skew-T and hodograph drawn in the browser (Bokeh): the figures, their
background lines and their glyphs are built once; a new sounding sends only its
profiles (in skewed coordinates) and the style of the lines.  Zoom, pan, hover and
saving are Bokeh's own tools.  The Figure workspace and saved SVGs keep the
matplotlib drawing (core.sounding_plot), which this follows in look.

Split in two so the work stays off the page's thread: payload() (numpy only, in a
worker) and SkewTView.apply(payload) (setting the Bokeh models, on the page's thread)."""

from functools import lru_cache

import numpy as np
import panel as pn
from bokeh.models import (
    BoxZoomTool, ColumnDataSource, CustomJS, CustomJSTicker, CustomJSTickFormatter,
    FixedTicker, HoverTool, LabelSet, Legend, LegendItem, PanTool, Range1d, ResetTool,
    SaveTool, Span, WheelZoomTool,
)
from bokeh.plotting import figure

from ..core import sounding_plot as sp
from ..theme import ACCENT, BG, GRID, MUTED, TEXT
from .ui import _bokeh, style_fig

P0 = 1050.0  # pressure (hPa) at which the skewed x is the temperature itself
SKEW = 55.0  # °C of skew per decade of pressure (isotherms at ~45° in the usual panel)
NS = 4  # soundings drawn at most (compared together)
# matplotlib's line styles (sounding_plot.LINESTYLES) as Bokeh dash patterns (px)
DASHES = [[], [7, 4], [2, 3], [9, 3, 2, 3]]
PARCEL_DASH = [6, 3]
ISOBARS = [1000, 900, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100]


def skewed(T, p):
    """x on the skew-T of temperature T (°C) at pressure p (hPa)."""
    return np.asarray(T, float) + SKEW * np.log10(P0 / np.asarray(p, float))


def _nan_join(lines):
    """[(x, y), ...] -> one x and one y array with NaN between the lines."""
    xs, ys = [], []
    for x, y in lines:
        xs += [np.asarray(x, float), [np.nan]]
        ys += [np.asarray(y, float), [np.nan]]
    return (np.concatenate(xs), np.concatenate(ys)) if xs else (np.zeros(0), np.zeros(0))


@lru_cache(maxsize=1)
def guide_lines():
    """Skew-T background in skewed coordinates, {name: (x, y)}: isotherms, dry and moist
    adiabats, mixing-ratio lines (one NaN-separated line each)."""
    p = np.geomspace(1100.0, 50.0, 80)
    iso = _nan_join([(skewed([t, t], [1100.0, 50.0]), [1100.0, 50.0])
                     for t in range(-160, 61, 10)])
    dry = _nan_join([(skewed(th * (p / 1000.0) ** 0.2857 - 273.15, p), p)
                     for th in range(230, 481, 10)])
    pm = np.geomspace(1000.0, 100.0, 50)
    try:
        import metpy.calc as mc
        from metpy.units import units
        t0 = np.arange(-20.0, 41.0, 4.0)
        tm = mc.moist_lapse(pm * units.hPa, t0 * units.degC).m_as("degC")
        tm = np.atleast_2d(tm)
        moist = _nan_join([(skewed(row, pm), pm) for row in tm])
    except Exception:  # noqa: BLE001  (metpy missing or changed: no moist adiabats)
        moist = _nan_join([])
    pw = np.geomspace(1050.0, 600.0, 12)
    mix = []
    for w in (0.4, 1, 2, 4, 7, 10, 16, 24):
        e = pw * w / (622.0 + w)
        lne = np.log(e / 6.112)
        mix.append((skewed(243.5 * lne / (17.67 - lne), pw), pw))
    return dict(iso=iso, dry=dry, moist=moist, mix=_nan_join(mix))


# ------------------------------------------------------------------ browser side
# x ticks: temperatures along the bottom edge (the skew shifts them with the
# pressure there), at a step that suits the width shown
TICKS_JS = """
const pb = yr.start, off = skew * Math.log10(p0 / pb);
const t0 = cb_data.start - off, t1 = cb_data.end - off, span = Math.abs(t1 - t0);
const step = span > 120 ? 20 : span > 50 ? 10 : span > 20 ? 5 : span > 8 ? 2 : 1;
const out = [];
for (let t = Math.ceil(Math.min(t0, t1) / step) * step; t <= Math.max(t0, t1); t += step)
  out.push(t + off);
return out;
"""
TICKFMT_JS = """
const off = skew * Math.log10(p0 / yr.start);
return (Math.round((tick - off) * 10) / 10).toString();
"""

# a range fitted to fit.data (x0, x1, y0, y1) unless the person zoomed or panned away
# from the last fit (then kept, and only the reset view follows) and its key (e.g. the
# wind units) is the same; with eq, equal x and y scale at the frame's shape (the
# hodograph)
FIT_JS = """
const w = fig.inner_width, h = fig.inner_height, d = fit.data;
if (!(w > 0 && h > 0) || !d.x0 || !d.x0.length) return;
let x0 = d.x0[0], x1 = d.x1[0], y0 = d.y0[0], y1 = d.y1[0];
if (![x0, x1, y0, y1].every(Number.isFinite)) return;
const xr = fig.x_range, yr = fig.y_range;
if (eq) {
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const s = Math.max((x1 - x0) / w, (y1 - y0) / h);
  x0 = cx - s * w / 2; x1 = cx + s * w / 2; y0 = cy - s * h / 2; y1 = cy + s * h / 2;
}
const last = xr.tags.length === 5 && xr.tags[4] === d.key[0] ? xr.tags : null;
const near = (a, b) => Math.abs(a - b) <= 1e-6 * Math.max(1, Math.abs(a), Math.abs(b));
const kept = last && !(near(xr.start, last[0]) && near(xr.end, last[1])
                       && near(yr.start, last[2]) && near(yr.end, last[3]));
if (!kept) {
  xr.setv({start: x0, end: x1, reset_start: x0, reset_end: x1});
  yr.setv({start: y0, end: y1, reset_start: y0, reset_end: y1});
} else {
  if (eq) {  // (a resized frame: the same centre and scale, the frame's shape)
    const cx = (xr.start + xr.end) / 2, cy = (yr.start + yr.end) / 2;
    const s = Math.max(Math.abs(xr.end - xr.start) / w, Math.abs(yr.end - yr.start) / h);
    xr.setv({start: cx - s * w / 2, end: cx + s * w / 2});
    yr.setv({start: cy - s * h / 2, end: cy + s * h / 2});
  }
  xr.setv({reset_start: x0, reset_end: x1});
  yr.setv({reset_start: y0, reset_end: y1});
}
xr.tags = [x0, x1, y0, y1, d.key[0]];  // the fit: a view unlike it was zoomed to
"""

# wind barbs and level labels in screen space (their shape does not change with the
# zoom): from the profiles in `bin` (p, u, v in kt, x position as a fraction of the
# width, colour) and the marks in `lin`, rebuilt on every view change
OVERLAY_JS = """
const W = fig.inner_width, H = fig.inner_height;
if (!(W > 0 && H > 0)) return;
const xr = fig.x_range, yr = fig.y_range;
const l0 = Math.log10(yr.start), dl = Math.log10(yr.end) - l0;
const X = (fx) => xr.start + fx * (xr.end - xr.start);
const PX = (px) => xr.start + px / W * (xr.end - xr.start);       // px from the left
const P = (py) => Math.pow(10, l0 + py / H * dl);                  // px from the bottom
const PY = (p) => (Math.log10(p) - l0) / dl * H;
const pb = Math.max(yr.start, yr.end), pt = Math.min(yr.start, yr.end);
const inview = (p) => Number.isFinite(p) && p >= pt && p <= pb;
const bx = [], by = [], bc = [], fx = [], fy = [], fc = [];
const L = 24, F = 10, gap = 3.6, pw = 5;
const b = bin.data;
for (let s = 0; s < (b.p || []).length; s++) {
  const p = b.p[s], u = b.u[s], v = b.v[s], col = b.color[s], x0 = b.xloc[s] * W;
  const step = Math.log(pb / pt) / 36;
  let last = Infinity;
  for (let k = 0; k < p.length; k++) {
    if (!inview(p[k]) || !Number.isFinite(u[k]) || !Number.isFinite(v[k])) continue;
    if (last - Math.log(p[k]) < step) continue;
    last = Math.log(p[k]);
    const spd = Math.hypot(u[k], v[k]);
    const y0 = PY(p[k]);
    if (spd < 2.5) {  // calm: a small ring
      const cx = [], cy = [];
      for (let a = 0; a <= 12; a++) {
        cx.push(PX(x0 + 3 * Math.cos(a * Math.PI / 6)));
        cy.push(P(y0 + 3 * Math.sin(a * Math.PI / 6)));
      }
      bx.push(cx); by.push(cy); bc.push(col);
      continue;
    }
    const dx = -u[k] / spd, dy = -v[k] / spd;  // along the staff, toward the wind's source
    const nx = dy, ny = -dx;                   // the feathers' side
    const at = (s_, n_) => [x0 + dx * s_ + nx * n_ + dx * 0.3 * n_,
                            y0 + dy * s_ + ny * n_ + dy * 0.3 * n_];
    bx.push([PX(x0), PX(x0 + dx * L)]); by.push([P(y0), P(y0 + dy * L)]); bc.push(col);
    let r = Math.round(spd / 5) * 5, s_ = L;
    const n50 = Math.floor(r / 50); r -= 50 * n50;
    const n10 = Math.floor(r / 10); r -= 10 * n10;
    for (let i = 0; i < n50; i++) {
      const a = [x0 + dx * s_, y0 + dy * s_], c = [x0 + dx * (s_ - pw), y0 + dy * (s_ - pw)];
      const tip = [a[0] + nx * F, a[1] + ny * F];
      fx.push([a[0], tip[0], c[0]].map(PX)); fy.push([a[1], tip[1], c[1]].map(P));
      fc.push(col);
      s_ -= pw + 1.5;
    }
    if (n50 && !n10 && !r) s_ += 1.5;
    for (let i = 0; i < n10; i++) {
      const e = at(s_, F);
      bx.push([PX(x0 + dx * s_), PX(e[0])]); by.push([P(y0 + dy * s_), P(e[1])]);
      bc.push(col);
      s_ -= gap;
    }
    if (r >= 5) {
      if (!n50 && !n10) s_ -= gap;
      const e = at(s_, F / 2);
      bx.push([PX(x0 + dx * s_), PX(e[0])]); by.push([P(y0 + dy * s_), P(e[1])]);
      bc.push(col);
    }
  }
}
bout.data = {xs: bx, ys: by, color: bc};
fout.data = {xs: fx, ys: fy, color: fc};
const lx = [], ly = [], lt = [], lc = [], sx0 = [], sx1 = [], sy = [], sc = [];
const m = lin.data;
for (let i = 0; i < (m.p || []).length; i++) {
  const p = m.kind[i] === 'top' ? P(H - 2) : m.p[i];
  if (!inview(p)) continue;
  if (m.kind[i] === 'mark') {
    sx0.push(X(0.77)); sx1.push(X(0.81)); sy.push(p); sc.push(m.color[i]);
    lx.push(X(0.815));
  } else lx.push(X(m.fx[i]));
  ly.push(p); lt.push(m.text[i]); lc.push(m.color[i]);
}
lout.data = {x: lx, y: ly, text: lt, color: lc};
sout.data = {x0: sx0, x1: sx1, y: sy, color: sc};
"""


# ------------------------------------------------------------------ payload (numpy)
def _f(a):
    return np.asarray(a, dtype=float)


def _empty_slot():
    return {k: [] for k in ("p", "xt", "xtd", "xtp", "T", "Td", "Tp", "z", "rh", "th",
                            "the", "qv", "label")}


def payload(items, base=None, parcel="ml", units="m/s", style="lines", look=None):
    """Everything the figures need for these soundings ((label, colour, result) from
    thermo.analyze; at most NS), as plain arrays and styles: see SkewTView.apply."""
    lk = sp._st(look)
    wf = sp._wfac(units)
    items = list(items)[:NS]
    single = len(items) == 1
    by_color = style == "colors" and not single
    out = dict(slots=[], styles=[], units=units, single=single, by_color=by_color)
    tmin, tmax = 1e9, -1e9
    barbs, marks, hodo, hpts = [], [], [], []
    hb = dict(xs=[], ys=[], color=[], slot=[])
    sm = dict(x=[], y=[], color=[])
    rml = dict(x=[], y=[], text=[], color=[])
    dots = dict(xs=[], ys=[])
    hh = dict(x=[], y=[], color=[])
    hlab = dict(x=[], y=[], text=[])
    allu, allv = [], []
    htop_km = lk["hodo_top"]
    for n, (label, color, r) in enumerate(items):
        pr = r["prof"]
        p = _f(pr["p"]) / 100.0
        T, Td = _f(pr["T"]) - 273.15, _f(pr["Td"]) - 273.15
        par = r.get(parcel) or {}
        Tp = _f(par.get("T", np.full(p.shape, np.nan))) - 273.15
        z = _f(pr["z"]) / 1000.0
        good = p > 300
        if good.any():
            tmin = min(tmin, np.nanmin(Td[good]))
        tmax = max(tmax, np.nanmax(T))
        out["slots"].append(dict(
            p=p, xt=skewed(T, p), xtd=skewed(Td, p), xtp=skewed(Tp, p), T=T, Td=Td, Tp=Tp,
            z=z, rh=_f(pr["rh"]), th=_f(pr["th"]), the=_f(pr["the"]), qv=_f(pr["qv"]) * 1e3,
            label=[label] * p.size))
        if by_color:
            ct, ctd, dt, dtd = color, color, [], [6, 3]
        else:
            ct, ctd, dt, dtd = lk["t_color"], lk["td_color"], DASHES[n], DASHES[n]
        out["styles"].append(dict(
            t_color=ct, td_color=ctd, t_dash=dt, td_dash=dtd, lw=lk["lw"],
            p_color=color if by_color else lk["parcel_color"],
            p_lw=lk["parcel_lw"] * (1.0 if n == 0 else 0.77), p_alpha=0.9 if n == 0 else 0.6,
            p_dash=PARCEL_DASH if (single or by_color) else DASHES[n], label=label))
        if n == 0:
            ok = np.isfinite(Tp) & np.isfinite(T)
            xt, xtp = skewed(T, p), skewed(Tp, p)
            pos = np.where(ok & (Tp > T), xtp, xt)
            neg = np.where(ok & (Tp < T) & (p > 500), xtp, xt)
            out["shade"] = dict(y=p, x1=xt, pos=np.where(np.isfinite(pos), pos, xt),
                                neg=np.where(np.isfinite(neg), neg, xt))
            for key, name in (("lcl_z", "LCL"), ("lfc_z", "LFC"), ("el_z", "EL")):
                zk = par.get(key, np.nan)
                if zk is not None and np.isfinite(zk):
                    pk = float(np.exp(np.interp(zk, pr["z"], np.log(p))))
                    marks.append(("mark", pk, 0.815, name, ACCENT))
            for zk in (1, 3, 6, 9, 12):
                if zk * 1000 < pr["z"][-1]:
                    pk = float(np.exp(np.interp(zk * 1000.0, pr["z"], np.log(p))))
                    marks.append(("km", pk, 0.012, f"{zk} km", MUTED))
        xloc = 0.96 - 0.05 * n
        bc = color if by_color else TEXT
        if lk["barbs"]:
            barbs.append(dict(p=p, u=_f(pr["u"]) * sp.KT, v=_f(pr["v"]) * sp.KT, xloc=xloc,
                              color=bc))
            if not single:
                marks.append(("top", np.nan, xloc - 0.012, label.split(" ")[0], bc))

        # hodograph
        kin = r["kin"]
        u, v = _f(pr["u"]) * wf, _f(pr["v"]) * wf
        s = z <= htop_km
        allu += list(u[s]) + [kin["rm"][0] * wf, kin["lm"][0] * wf]
        allv += list(v[s]) + [kin["rm"][1] * wf, kin["lm"][1] * wf]
        if by_color:
            hb["xs"].append(u[s]), hb["ys"].append(v[s])
            hb["color"].append(color), hb["slot"].append(n)
        else:
            for z0, z1, c in sp.HODO_BANDS:
                if z0 >= htop_km:
                    continue
                z1 = min(z1, htop_km)
                sel = (z >= z0) & (z <= z1)
                if sel.sum() > 1:
                    zz = np.concatenate(([z0], z[sel], [z1]))
                    hb["xs"].append(np.interp(zz, z, u)), hb["ys"].append(np.interp(zz, z, v))
                    hb["color"].append(c), hb["slot"].append(n)
        for zk in sp.hodo_heights(lk["hodo_heights"]):
            if zk <= htop_km and z[0] <= zk <= z[-1]:
                uk, vk = float(np.interp(zk, z, u)), float(np.interp(zk, z, v))
                hh["x"].append(uk), hh["y"].append(vk)
                hh["color"].append(color if by_color else TEXT)
                if n == 0:
                    hlab["x"].append(uk), hlab["y"].append(vk), hlab["text"].append(f"{zk:g}")
        rm, lm, c = (np.array(kin[k], float) * wf for k in ("rm", "lm", "storm"))
        mc = color if by_color else TEXT
        tag = "" if single else label.split(" ")[0]
        for pos_, name in ((rm, "RM"), (lm, "LM")):
            if np.all(np.isfinite(pos_)):
                rml["x"].append(pos_[0]), rml["y"].append(pos_[1])
                rml["text"].append(f"{name}{tag}"), rml["color"].append(mc)
        if np.all(np.isfinite(c)):
            sm["x"].append(c[0]), sm["y"].append(c[1])
            sm["color"].append(color if by_color else ACCENT)
            if n == 0:
                z5 = float(np.interp(0.5, z, u)), float(np.interp(0.5, z, v))
                dots["xs"] += [[c[0], u[0]], [u[0], z5[0]]]
                dots["ys"] += [[c[1], v[0]], [v[0], z5[1]]]
        sel = z <= htop_km + 1.0
        dirs = (270.0 - np.degrees(np.arctan2(v[sel], u[sel]))) % 360.0
        hpts.append(dict(u=u[sel], v=v[sel], z=z[sel], spd=np.hypot(u[sel], v[sel]),
                         dir=dirs, label=[label] * int(sel.sum())))

    if base is not None:
        bp = base["prof"]
        p = _f(bp["p"]) / 100.0
        out["base"] = dict(p=p, xt=skewed(_f(bp["T"]) - 273.15, p),
                           xtd=skewed(_f(bp["Td"]) - 273.15, p))
        s = _f(bp["z"]) <= htop_km * 1000.0
        out["hbase"] = dict(x=_f(bp["u"])[s] * wf, y=_f(bp["v"])[s] * wf)
    out["base_color"] = lk["base_color"]

    # skew-T view: temperatures along the bottom, pressures
    lo = lk["tmin"] if lk["tmin"] is not None else max(-45, np.floor(tmin / 10) * 10 - 5)
    hi = lk["tmax"] if lk["tmax"] is not None else min(55, np.ceil(tmax / 10) * 10 + 10)
    if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
        lo, hi = -40.0, 50.0
    out["skew_fit"] = (float(lo), float(hi), P0, float(lk["ptop"]))
    out["barbs"] = barbs
    out["marks"] = marks
    out["title"] = f"Skew-T  ·  {dict(sb='SB', ml='ML', mu='MU')[parcel]} parcel"
    out["shade_on"] = bool(lk["shade"])
    out["guides"] = bool(lk["guides"])

    # hodograph view, rings
    allu, allv = np.array(allu, float), np.array(allv, float)
    ok = np.isfinite(allu) & np.isfinite(allv)
    allu, allv = (allu[ok], allv[ok]) if ok.any() else (np.zeros(1), np.zeros(1))
    ring = lk["ring"] or (10.0 if units == "m/s" else 20.0)
    rmax = max(np.hypot(allu, allv).max(), ring) * 1.1
    cu, cv = 0.5 * (allu.max() + allu.min()), 0.5 * (allv.max() + allv.min())
    half = max(allu.max() - allu.min(), allv.max() - allv.min()) * 0.6 + ring * 0.5
    rr = np.arange(ring, rmax + ring, ring)
    out["rings"] = dict(x=np.zeros(rr.size), y=np.zeros(rr.size), r=rr,
                        lx=rr * 0.7071, ly=-rr * 0.7071, text=[f"{v:.0f}" for v in rr])
    out["hodo_fit"] = (cu - half, cu + half, cv - half, cv + half)
    out["hbands"], out["hheights"], out["hlabels"] = hb, hh, hlab
    out["storm"], out["rmlm"], out["dots"] = sm, rml, dots
    out["hpts"] = hpts
    out["hodo_lw"] = lk["hodo_lw"]
    out["band_labels"] = [(f"{a}–{min(b, htop_km):g} km", c) for a, b, c in sp.HODO_BANDS
                          if a < htop_km]
    return out


# ------------------------------------------------------------------ the figures
def _cell(pane, flex):
    """A pane in a box of its own for the flex row (the pane's own element takes no part
    in the layout, so a flex style on it does nothing)."""
    return pn.Column(pane, margin=0, sizing_mode="stretch_width",
                     styles={"flex": flex, "min-width": "0"})


def _quiet(r):
    """A renderer that keeps its look when something is selected (no tap tool here)."""
    r.nonselection_glyph = r.glyph
    r.selection_glyph = r.glyph
    return r


class SkewTView:
    """One skew-T + hodograph pair on the page (the tabs comparison style has one per
    sounding).  .panel is what goes on the page; apply(payload(...)) shows soundings."""

    def __init__(self, height=430):
        self._skew(height)
        self._hodo(height)
        self.panel = pn.FlexBox(
            _cell(_bokeh(self.sfig, sizing_mode="stretch_width", height=height),
                  "1.35 1 360px"),
            _cell(_bokeh(self.hfig, sizing_mode="stretch_width", height=height),
                  "1 1 280px"),
            flex_wrap="wrap", gap="0px 6px", sizing_mode="stretch_width")

    # ---------------------------------------------------------------- skew-T
    def _skew(self, height):
        yr = Range1d(P0, 100.0)
        xr = Range1d(-40.0, 50.0)
        f = figure(y_axis_type="log", x_range=xr, y_range=yr, height=height,
                   sizing_mode="stretch_width", tools="", toolbar_location="above",
                   x_axis_label="Temperature (°C)", y_axis_label="Pressure (hPa)",
                   title="Skew-T")
        style_fig(f)
        f.toolbar.autohide = True
        f.title.text_color = TEXT
        f.title.text_font_style = "normal"
        f.xgrid.visible = False  # (vertical lines are not isotherms here)
        f.yaxis.ticker = FixedTicker(ticks=ISOBARS)
        f.yaxis.formatter = CustomJSTickFormatter(code="return tick.toFixed(0);")
        args = dict(yr=yr, skew=SKEW, p0=P0)
        f.xaxis.ticker = CustomJSTicker(major_code=TICKS_JS, args=args)
        f.xaxis.formatter = CustomJSTickFormatter(code=TICKFMT_JS, args=args)
        g = guide_lines()
        _quiet(f.line(*g["iso"], color=GRID, line_width=0.6, alpha=0.8))  # (the grid)
        self.guides = [  # (switched off with the guides setting)
            _quiet(f.line(*g["dry"], color="#c2410c", line_width=0.7, alpha=0.3)),
            _quiet(f.line(*g["moist"], color="#15803d", line_width=0.7, alpha=0.3)),
            _quiet(f.line(*g["mix"], color="#0e7490", line_width=0.7, alpha=0.4)),
        ]
        _quiet(f.line(skewed([0, 0], [1100, 50]), [1100, 50], color="#60a5fa",
                      line_width=0.8, alpha=0.5, line_dash="dashed"))

        self.shade = ColumnDataSource(dict(y=[], x1=[], pos=[], neg=[]))
        self.shade_r = [
            _quiet(f.harea(x1="x1", x2="pos", y="y", source=self.shade, fill_color="#f87171",
                           fill_alpha=0.18)),
            _quiet(f.harea(x1="x1", x2="neg", y="y", source=self.shade, fill_color="#60a5fa",
                           fill_alpha=0.12)),
        ]
        self.base = ColumnDataSource(dict(p=[], xt=[], xtd=[]))
        self.base_r = [
            _quiet(f.line("xt", "p", source=self.base, line_width=1.2, line_dash="dashed",
                          alpha=0.9, color=MUTED)),
            _quiet(f.line("xtd", "p", source=self.base, line_width=1.2, line_dash="dotted",
                          alpha=0.9, color=MUTED)),
        ]
        self.src, self.t_r, self.td_r, self.p_r = [], [], [], []
        for _ in range(NS):
            s = ColumnDataSource(_empty_slot())
            self.src.append(s)
            self.p_r.append(_quiet(f.line("xtp", "p", source=s)))
            self.td_r.append(_quiet(f.line("xtd", "p", source=s)))
            self.t_r.append(_quiet(f.line("xt", "p", source=s)))

        # barbs and level labels: drawn in the browser (OVERLAY_JS)
        self.barb_in = ColumnDataSource(dict(p=[], u=[], v=[], xloc=[], color=[]))
        self.mark_in = ColumnDataSource(dict(p=[], fx=[], text=[], color=[], kind=[]))
        bout = ColumnDataSource(dict(xs=[], ys=[], color=[]))
        fout = ColumnDataSource(dict(xs=[], ys=[], color=[]))
        lout = ColumnDataSource(dict(x=[], y=[], text=[], color=[]))
        sout = ColumnDataSource(dict(x0=[], x1=[], y=[], color=[]))
        _quiet(f.multi_line("xs", "ys", source=bout, color="color", line_width=0.9))
        _quiet(f.patches("xs", "ys", source=fout, color="color", line_width=0.5))
        _quiet(f.segment("x0", "y", "x1", "y", source=sout, color="color", line_width=1.5))
        f.add_layout(LabelSet(x="x", y="y", text="text", source=lout, text_color="color",
                              text_font_size="11px", text_baseline="middle"))
        ov = CustomJS(args=dict(fig=f, bin=self.barb_in, lin=self.mark_in, bout=bout,
                                fout=fout, lout=lout, sout=sout), code=OVERLAY_JS)
        for obj, attr in ((xr, "start"), (xr, "end"), (yr, "start"), (yr, "end"),
                          (f, "inner_width"), (f, "inner_height"), (self.barb_in, "data"),
                          (self.mark_in, "data")):
            obj.js_on_change(attr, ov)

        self.skew_fit = ColumnDataSource(dict(x0=[], x1=[], y0=[], y1=[], key=[]))
        fit = CustomJS(args=dict(fig=f, fit=self.skew_fit, eq=False), code=FIT_JS)
        for obj, attr in ((f, "inner_width"), (f, "inner_height"), (self.skew_fit, "data")):
            obj.js_on_change(attr, fit)

        hover = HoverTool(renderers=self.t_r, mode="hline", tooltips=(
            '<div style="font-size:11px"><b>@label</b><br>'
            "p @p{0} hPa · z @z{0.00} km<br>T @T{0.0} · Td @Td{0.0} · parcel @Tp{0.0} °C<br>"
            "RH @rh{0} % · θ @th{0.0} · θe @the{0.0} K · qv @qv{0.0} g/kg</div>"))
        f.add_tools(PanTool(), BoxZoomTool(), WheelZoomTool(), ResetTool(), SaveTool(),
                    hover)
        f.toolbar.active_scroll = None
        self.legend = Legend(items=[], location="bottom_left", background_fill_color=BG,
                             background_fill_alpha=0.88, border_line_color=GRID,
                             label_text_color=TEXT, label_text_font_size="11px",
                             visible=False)
        f.add_layout(self.legend)
        self.sfig = f

    # ---------------------------------------------------------------- hodograph
    def _hodo(self, height):
        f = figure(x_range=Range1d(-20, 20), y_range=Range1d(-20, 20), height=height,
                   sizing_mode="stretch_width", tools="", toolbar_location="above",
                   x_axis_label="u (m/s)", y_axis_label="v (m/s)",
                   title="Hodograph (ground-relative)")
        style_fig(f)
        f.toolbar.autohide = True
        f.title.text_color = TEXT
        f.title.text_font_style = "normal"
        f.grid.visible = False
        f.add_layout(Span(location=0, dimension="width", line_color=GRID, line_width=0.8))
        f.add_layout(Span(location=0, dimension="height", line_color=GRID, line_width=0.8))
        self.rings = ColumnDataSource(dict(x=[], y=[], r=[], lx=[], ly=[], text=[]))
        _quiet(f.circle("x", "y", radius="r", source=self.rings, fill_color=None,
                        line_color=GRID, line_width=0.8))
        f.add_layout(LabelSet(x="lx", y="ly", text="text", source=self.rings,
                              text_color=MUTED, text_font_size="10px", text_align="center",
                              text_baseline="middle"))
        self.hbase = ColumnDataSource(dict(x=[], y=[]))
        self.hbase_r = _quiet(f.line("x", "y", source=self.hbase, line_width=1.2,
                                     line_dash="dashed", color=MUTED))
        self.hb, self.hb_r = [], []
        for n in range(NS):
            s = ColumnDataSource(dict(xs=[], ys=[], color=[]))
            self.hb.append(s)
            self.hb_r.append(_quiet(f.multi_line("xs", "ys", source=s, color="color")))
        self.dots = ColumnDataSource(dict(xs=[], ys=[]))
        _quiet(f.multi_line("xs", "ys", source=self.dots, color=ACCENT, line_width=0.9,
                            line_dash="dotted"))
        self.hh = ColumnDataSource(dict(x=[], y=[], color=[]))
        _quiet(f.scatter("x", "y", source=self.hh, size=7, fill_color="color",
                         line_color=BG, line_width=0.6))
        self.hlab = ColumnDataSource(dict(x=[], y=[], text=[]))
        f.add_layout(LabelSet(x="x", y="y", text="text", source=self.hlab, x_offset=5,
                              y_offset=3, text_color=MUTED, text_font_size="10px"))
        self.rmlm = ColumnDataSource(dict(x=[], y=[], text=[], color=[]))
        f.add_layout(LabelSet(x="x", y="y", text="text", source=self.rmlm,
                              text_color="color", text_font_size="11px",
                              text_font_style="bold", text_align="center",
                              text_baseline="middle"))
        self.storm = ColumnDataSource(dict(x=[], y=[], color=[]))
        _quiet(f.scatter("x", "y", source=self.storm, size=13, fill_color=None,
                         line_color="color", line_width=1.6))
        self.hpts = ColumnDataSource(dict(u=[], v=[], z=[], spd=[], dir=[], label=[]))
        pts = _quiet(f.scatter("u", "v", source=self.hpts, size=9, alpha=0))
        self.hfit = ColumnDataSource(dict(x0=[], x1=[], y0=[], y1=[], key=[]))
        fit = CustomJS(args=dict(fig=f, fit=self.hfit, eq=True), code=FIT_JS)
        for obj, attr in ((f, "inner_width"), (f, "inner_height"), (self.hfit, "data")):
            obj.js_on_change(attr, fit)
        hover = HoverTool(renderers=[pts], tooltips=(
            '<div style="font-size:11px"><b>@label</b><br>z @z{0.00} km<br>'
            "@dir{000}° / @spd{0.0} · u @u{0.0} · v @v{0.0}</div>"))
        f.add_tools(PanTool(), BoxZoomTool(match_aspect=True), WheelZoomTool(), ResetTool(),
                    SaveTool(), hover)
        f.toolbar.active_scroll = None
        # legend: height bands, storm motion, which dash is which sounding
        # (stand-ins with one point off the plot: an empty renderer gets no swatch)
        nan = [np.nan]
        self.band_dummy = [_quiet(f.line(nan, nan, line_width=1.0)) for _ in sp.HODO_BANDS]
        self.storm_dummy = _quiet(f.scatter(nan, nan, size=10, fill_color=None,
                                            line_color=ACCENT, line_width=1.6))
        self.snd_dummy = [_quiet(f.line(nan, nan, color=TEXT, line_dash=DASHES[n]))
                          for n in range(NS)]
        self.hlegend = Legend(items=[], location="top_left", background_fill_color=BG,
                              background_fill_alpha=0.88, border_line_color=GRID,
                              label_text_color=TEXT, label_text_font_size="10px",
                              glyph_height=12, label_height=12, spacing=0, padding=6)
        f.add_layout(self.hlegend)
        self.hfig = f

    # ---------------------------------------------------------------- update
    def apply(self, d):
        """Show a payload() (on the page's thread)."""
        self.sfig.title.text = d["title"]
        for r in self.guides:
            r.visible = d["guides"]
        for n in range(NS):
            if n < len(d["slots"]):
                self.src[n].data = d["slots"][n]
                st = d["styles"][n]
                for r, c, dash, lw in ((self.t_r[n], st["t_color"], st["t_dash"], st["lw"]),
                                       (self.td_r[n], st["td_color"], st["td_dash"], st["lw"])):
                    r.glyph.update(line_color=c, line_dash=dash, line_width=lw)
                    r.visible = True
                self.p_r[n].glyph.update(line_color=st["p_color"], line_width=st["p_lw"],
                                         line_alpha=st["p_alpha"], line_dash=st["p_dash"])
                self.p_r[n].visible = True
            else:
                for r in (self.t_r[n], self.td_r[n], self.p_r[n]):
                    r.visible = False
                self.src[n].data = _empty_slot()
        sh = d.get("shade")
        self.shade.data = sh if sh else dict(y=[], x1=[], pos=[], neg=[])
        for r in self.shade_r:
            r.visible = d["shade_on"]
        b = d.get("base")
        self.base.data = b if b else dict(p=[], xt=[], xtd=[])
        for r in self.base_r:
            r.glyph.line_color = d["base_color"]
            r.visible = b is not None
        self.barb_in.data = dict(p=[x["p"] for x in d["barbs"]], u=[x["u"] for x in d["barbs"]],
                                 v=[x["v"] for x in d["barbs"]],
                                 xloc=[x["xloc"] for x in d["barbs"]],
                                 color=[x["color"] for x in d["barbs"]])
        m = d["marks"]
        self.mark_in.data = dict(kind=[x[0] for x in m], p=[x[1] for x in m],
                                 fx=[x[2] for x in m], text=[x[3] for x in m],
                                 color=[x[4] for x in m])
        x0, x1, y0, y1 = d["skew_fit"]
        self.skew_fit.data = dict(x0=[x0], x1=[x1], y0=[y0], y1=[y1], key=["skew"])
        items = []
        if not d["single"] or b is not None:
            for n, st in enumerate(d["styles"]):
                items.append(LegendItem(label=st["label"], renderers=[self.t_r[n]]))
            if b is not None:
                items.append(LegendItem(label="Base state", renderers=[self.base_r[0]]))
        self.legend.items = items
        self.legend.visible = bool(items)

        # hodograph
        u = d["units"]
        self.hfig.xaxis.axis_label, self.hfig.yaxis.axis_label = f"u ({u})", f"v ({u})"
        self.rings.data = d["rings"]
        hb = d["hbands"]
        for n in range(NS):
            sel = [i for i, s in enumerate(hb["slot"]) if s == n]
            self.hb[n].data = dict(xs=[hb["xs"][i] for i in sel], ys=[hb["ys"][i] for i in sel],
                                   color=[hb["color"][i] for i in sel])
            self.hb_r[n].glyph.update(
                line_width=d["hodo_lw"] * (0.92 if d["by_color"] else 1.0 if n == 0 else 0.83),
                line_dash=[] if d["by_color"] else DASHES[n])
        self.hh.data = d["hheights"]
        self.hlab.data = d["hlabels"]
        self.rmlm.data = d["rmlm"]
        self.storm.data = d["storm"]
        self.dots.data = d["dots"]
        hb_ = d.get("hbase")
        self.hbase.data = hb_ if hb_ else dict(x=[], y=[])
        self.hbase_r.glyph.line_color = d["base_color"]
        self.hbase_r.visible = hb_ is not None
        hp = d["hpts"]
        cols = {k: np.concatenate([h[k] for h in hp]) if hp else []
                for k in ("u", "v", "z", "spd", "dir")}
        self.hpts.data = dict(cols, label=[x for h in hp for x in h["label"]])
        x0, x1, y0, y1 = d["hodo_fit"]
        self.hfit.data = dict(x0=[x0], x1=[x1], y0=[y0], y1=[y1], key=[u])
        litems = []
        if not d["by_color"]:
            for r, (label, c) in zip(self.band_dummy, d["band_labels"]):
                r.glyph.update(line_color=c, line_width=d["hodo_lw"])
                litems.append(LegendItem(label=label, renderers=[r]))
            litems.append(LegendItem(label="Storm motion", renderers=[self.storm_dummy]))
            if not d["single"]:
                litems += [LegendItem(label=st["label"], renderers=[self.snd_dummy[n]])
                           for n, st in enumerate(d["styles"])]
        self.hlegend.items = litems
        self.hlegend.visible = bool(litems)
