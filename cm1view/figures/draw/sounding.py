"""Sounding panels: skew-T, hodograph and parameter table."""

import numpy as np
import matplotlib
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.ticker import NullFormatter

from .base import (SND_COLORS, STORM_NAMES, SND_PARAMS, HODO_BANDS, KT, by_run, font_size,
                   panel_legend, run_color)

def _moist(T0, p):
    """Pseudo-adiabats: temperatures (deg C) along p (hPa, decreasing) from T0 (deg C,
    array) at p[0]."""
    Rd, cp, Lv, eps = 287.04, 1005.7, 2.501e6, 0.622

    def f(T, pp):
        es = 611.2 * np.exp(17.67 * (T - 273.15) / (T - 29.65))
        rs = eps * es / np.maximum(pp * 100.0 - es, 1.0)
        return (Rd * T + Lv * rs) / (cp + Lv * Lv * rs * eps / (Rd * T * T))

    T = np.asarray(T0, dtype=float) + 273.15
    out = [T]
    for a, b in zip(p[:-1], p[1:]):
        h = np.log(b / a)
        k1 = f(T, a)
        k2 = f(T + h * k1, b)
        T = T + 0.5 * h * (k1 + k2)
        out.append(T)
    return np.array(out) - 273.15


def sounding_layout(o):
    """The skewt options' layout (older specs: the "hodo" checkbox)."""
    lay = o.get("layout")
    if lay in ("inset", "side", "skewt", "hodo"):
        return lay
    return "inset" if o.get("hodo", True) else "skewt"


HODO_LS = ["-", (0, (5, 2.5)), (0, (1.2, 1.8)), (0, (7, 2, 1.5, 2))]  # a hodograph each
HODO_MARKS = ("rm", "lm", "mean")  # skewt keys hodo_rm, hodo_lm, hodo_mean


def hodo_marks(o):
    """The storm motions marked on the hodograph (older specs: one "hodo_kin" box)."""
    kin = o.get("hodo_kin", True)
    return tuple(k for k in HODO_MARKS if o.get(f"hodo_{k}", kin))


def sounding_colors(spec, d):
    """Colour of each sounding of panel data d: its own, else its run's when each of
    the panel's soundings comes from another run (by_run), else the next of SND_COLORS."""
    ents = spec.get("soundings", [])
    n = int(d.get("nsnd", 0))
    es = [ents[int(d[f"N{j}_e"])] if int(d[f"N{j}_e"]) < len(ents) else {} for j in range(n)]
    runs = [int(e.get("run", 0)) for e in es]
    rc = by_run(spec, runs)
    return [e.get("color") or (run_color(spec, k) if rc else SND_COLORS[j % len(SND_COLORS)])
            for j, (e, k) in enumerate(zip(es, runs))]


def _sounding(fig, ax, d, spec, fs):
    """A sounding panel in its layout; returns the axes the panel's labels go on (the
    skew-T, or the hodograph alone)."""
    o = spec.get("skewt", {})
    lay = sounding_layout(o)
    n = int(d.get("nsnd", 0))
    cols = sounding_colors(spec, d)
    keys = [k for k in (o.get("table") or []) if k in [p[0] for p in SND_PARAMS]]
    if keys and n:  # a row per sounding, under the panel
        gs = ax.get_subplotspec().subgridspec(
            2, 1, height_ratios=[1.0, float(o.get("table_height", 0.08)) * (n + 1.5)],
            hspace=0.02)
        ax.remove()
        ax, tx = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
        _param_table(tx, d, n, cols, keys, spec)
    if lay == "hodo":
        _hodo(ax, d, n, cols, o, fs, full=True)
        return ax
    if lay == "side":
        w = float(o.get("hodo_width", 0.62))  # hodograph width / skew-T width
        gs = ax.get_subplotspec().subgridspec(1, 2, width_ratios=[1.0, w], wspace=0.04)
        ax.remove()
        ax, hx = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
        _skewt(ax, d, spec, fs, cols, inset=False)
        _hodo(hx, d, n, cols, o, fs, full=True)
        return ax
    _skewt(ax, d, spec, fs, cols, inset=lay == "inset")
    return ax


def _param_table(tx, d, n, cols, keys, spec):
    """The chosen SND_PARAMS of the panel's soundings: a row each (named and coloured
    like its lines when there are several)."""
    tx.axis("off")
    idx = [[p[0] for p in SND_PARAMS].index(k) for k in keys]
    head = [SND_PARAMS[j][1] + (f"\n({SND_PARAMS[j][2]})" if SND_PARAMS[j][2] else "")
            for j in idx]

    def fmt(j, c):
        par = np.asarray(d[f"N{j}_par"], float)  # (older saved data: fewer values)
        v = par[c] if c < par.size else np.nan
        if not np.isfinite(v):
            return "–"
        if SND_PARAMS[c][0] in ("stp_eff", "stp_fixed", "scp"):
            return f"{v:.1f}"
        return f"{round(v)}"  # (not "-0")

    rows = [[fmt(j, c) for c in idx] for j in range(n)]
    names = None
    if n > 1:
        names = [str(d.get(f"N{j}_label", "")).split(" (")[0] or f"{j + 1}"
                 for j in range(n)]
    t = tx.table(cellText=rows, colLabels=head, rowLabels=names, loc="upper center",
                 cellLoc="center", edges="horizontal")
    t.auto_set_font_size(False)
    t.set_fontsize(font_size(spec, "legend"))
    t.scale(1.0, 1.25)
    for (r, c), cell in t.get_celld().items():
        cell.set_linewidth(0.5)
        if r == 0:
            cell.set_text_props(weight="bold")
            cell.set_height(cell.get_height() * 1.7)
        if c == -1 and r > 0:  # the sounding's colour
            cell.set_text_props(color=cols[r - 1], weight="bold", ha="right")


def _skewt(ax, d, spec, fs, cols, inset=True):
    """Skew-T log-p panel (plain axes: x = T + skew * ln(p_bottom / p)), with wind
    barbs at the right and an optional hodograph inset (skewt "inset_loc": a corner,
    auto: the top corner the traces cross least, or custom: its lower left at inset_x,
    inset_y; inset_size: its width; all fractions of the axes)."""
    o = spec.get("skewt", {})
    pb, pt = float(o.get("pmax", 1000.0)), float(o.get("pmin", 100.0))
    skew = float(o.get("skew", 35.0))

    def X(T, p):
        return np.asarray(T) + skew * np.log(pb / np.asarray(p))

    ax._cv_skew = (skew, pb)  # (annotations and clicks in temperature and pressure)
    ax.set_yscale("log")
    pp = np.geomspace(pb, pt, 80)
    if o.get("guides", True):
        for T0 in np.arange(-150, 60, 10):
            ax.plot(X(np.full_like(pp, T0), pp), pp, color="0.82" if T0 else "0.55",
                    lw=0.5, ls="-" if T0 else "--", zorder=0)
        for th in np.arange(240, 470, 10):
            ax.plot(X(th * (pp / 1000.0) ** 0.2857 - 273.15, pp), pp, color="#e7c9a3",
                    lw=0.5, zorder=0)
        Tm = _moist(np.arange(-20, 36, 4), pp)
        for k in range(Tm.shape[1]):
            ax.plot(X(Tm[:, k], pp), pp, color="#a7c7a3", lw=0.5, ls=(0, (4, 2)), zorder=0)
    n = int(d.get("nsnd", 0))
    many = n > 1
    handles = []
    for j in range(n):
        p, T, Td = d[f"N{j}_p"], d[f"N{j}_T"], d[f"N{j}_Td"]
        col = cols[j]
        lw = float(o.get("lw", 1.8))
        cT, cD, cP = (col, col, col) if many else ("#d62728", "#2ca02c", "k")
        h, = ax.plot(X(T, p), p, color=cT, lw=lw, label=str(d.get(f"N{j}_label", "")))
        ax.plot(X(Td, p), p, color=cD, lw=lw * (0.75 if many else 1.0),
                ls=(0, (5, 2)) if many else "-")
        Tp = d.get(f"N{j}_Tp")
        if Tp is not None and o.get("parcel", "ml") != "none":
            ax.plot(X(Tp, p), p, color=cP, lw=0.9, ls=(0, (1.5, 1.5)) if many else "--")
        handles.append(h)
    ax.set_ylim(pb, pt)
    ax.set_xlim(float(o.get("tmin", -40.0)), float(o.get("tmax", 50.0)))
    ticks = [v for v in (1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100)
             if pt <= v <= pb]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{v:g}" for v in ticks])
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    nbarb = (n if many else 1) if o.get("barbs", True) and n else 0
    if nbarb:
        x0, x1 = ax.get_xlim()
        for j in range(nbarb):
            p, u, v = d[f"N{j}_p"], d[f"N{j}_u"], d[f"N{j}_v"]
            sel, last = [], None
            for k in range(len(p)):  # every ~25 hPa
                if pt <= p[k] <= pb and (last is None or last - p[k] >= 25.0):
                    sel.append(k)
                    last = p[k]
            xb = x1 - (0.05 + 0.07 * j) * (x1 - x0)
            col = cols[j] if many else "k"
            # barbs are drawn in data x, which is skewed: put them on a vertical line
            ax.barbs(np.full(len(sel), xb), p[sel], u[sel] * KT, v[sel] * KT, length=5,
                     lw=0.6, color=col, clip_on=False)
    if inset and n:
        rect = o.get("hodo_rect")
        where = o.get("inset_loc") or "auto"
        w = float(o.get("inset_size") or 0.37)  # (axes fractions)
        h = w * 0.39 / 0.37
        if not rect and where == "custom":  # lower-left corner at inset_x, inset_y
            rect = [float(o.get("inset_x", 0.62)), float(o.get("inset_y", 0.6)), w, h]
        if not rect:  # a corner (the right ones left of the barbs, which they would hide)
            right = 0.99 if not nbarb else 0.985 - 0.07 * (nbarb + 0.6)
            corners = {"upper right": [right - w, 0.99 - h, w, h],
                       "upper left": [0.01, 0.99 - h, w, h]}
            lower = {"lower right": [right - w, 0.01, w, h], "lower left": [0.01, 0.01, w, h]}
            if where in lower:
                rect = lower[where]
            else:  # auto: the top corner the traces cross least
                if where not in corners:
                    legend = (many or o.get("legend", False)) and o.get("legend_loc",
                                                                        "upper left")
                    where = min(corners, key=lambda c: _crossed(
                        d, n, X, pb, pt, ax.get_xlim(), corners[c], legend == c))
                rect = corners[where]
        hx = ax.inset_axes([float(v) for v in rect])
        _hodo(hx, d, n, cols, o, fs, full=bool(o.get("hodo_full_inset", False)))
        # (equal aspect shrinks the box: keep it in its corner, custom: at x, y)
        hx.set_anchor({"upper right": "NE", "upper left": "NW", "lower right": "SE",
                       "lower left": "SW", "custom": "SW"}.get(where, "C"))
    if many or o.get("legend", False):
        panel_legend(ax, handles, o, spec, "upper left", True)


def _crossed(d, n, X, pb, pt, xlim, rect, legend):
    """How much of the panel's traces (T, Td) an inset at rect (axes fractions) would
    hide, plus a forfeit for the corner of the legend."""
    x0, y0, w, h = rect
    hit = total = 0
    for j in range(n):
        p = np.asarray(d[f"N{j}_p"], dtype=float)
        ok = (p > 0) & (p <= pb) & (p >= pt)
        fy = np.log(pb / p[ok]) / np.log(pb / pt)
        for key in ("T", "Td"):
            fx = (X(np.asarray(d[f"N{j}_{key}"], dtype=float)[ok], p[ok]) - xlim[0]) / \
                (xlim[1] - xlim[0])
            hit += int(np.sum((fx >= x0) & (fx <= x0 + w) & (fy >= y0) & (fy <= y0 + h)))
            total += fy.size
    return hit + (0.25 * total if legend else 0.0)


def _hodo_view(d, n, o, top, hm, srh):
    """The hodograph's centre (u, v) and half-width (m/s; the view is square): about
    the origin (hodo_center "origin"; ± hodo_max), about hodo_cu, hodo_cv ("custom";
    ± hodo_max), or ("fit") about what is drawn: the traces up to hodo_top, the storm
    motions and ring, with a margin, the half-width rounded up to 5 m/s."""
    how = o.get("hodo_center") or "origin"
    if how == "custom":
        return float(o.get("hodo_cu") or 0.0), float(o.get("hodo_cv") or 0.0), hm
    if how != "fit":
        return 0.0, 0.0, hm
    us, vs = [], []
    for j in range(n):
        z = np.asarray(d[f"N{j}_z"], dtype=float)
        us.append(np.asarray(d[f"N{j}_u"], dtype=float)[z <= top])
        vs.append(np.asarray(d[f"N{j}_v"], dtype=float)[z <= top])
        keys = hodo_marks(o) + (("storm",) if o.get("hodo_storm", True) or srh else ())
        for key in keys:
            if d.get(f"N{j}_{key}") is not None:
                cu, cv = (float(x) for x in d[f"N{j}_{key}"])
                us.append([cu])
                vs.append([cv])
    u, v = np.concatenate(us or [[]]), np.concatenate(vs or [[]])
    ok = np.isfinite(u) & np.isfinite(v)
    if not ok.any():
        return 0.0, 0.0, hm
    u, v = u[ok], v[ok]
    cu, cv = 0.5 * (u.min() + u.max()), 0.5 * (v.min() + v.max())
    half = 0.5 * max(u.max() - u.min(), v.max() - v.min()) * 1.15 + 2.0
    return cu, cv, max(5.0 * np.ceil(half / 5.0), 10.0)


def shared_hodo_half(items):
    """The largest half-width (m/s) of the hodograph views of items [(d, skewt options)]
    that draw a full hodograph (layout "side" or "hodo"); None when fewer than two do."""
    halves = []
    for d, o in items:
        if sounding_layout(o) in ("side", "hodo") and int(d.get("nsnd", 0)) \
                and not d.get("missing"):
            top = float(o.get("hodo_top", 9.0))
            halves.append(_hodo_view(d, int(d["nsnd"]), o, top, float(o.get("hodo_max", 40.0)),
                                     str(o.get("srh") or ""))[2])
    return max(halves) if len(halves) > 1 else None


def _hodo(hx, d, n, cols, o, fs, full=False):
    """Hodograph of the panel's soundings (one sounding: coloured by height bands).
    Bunkers right / left movers and the 0-6 km mean wind (hodo_marks), a ring at the
    storm motion of the SRH (hodo_storm; one sounding: with the storm-relative
    inflow and the 0-0.5 km shear, as the Sounding tab draws them), height labels
    along the trace (hodo_labels); full (a hodograph panel, not an inset): a key of
    the height bands (hodo_key) and SRH shading (srh "1" / "3": 0-1 / 0-3 km). The
    view: _hodo_view."""
    hx._cv_hodo = True
    many = n > 1
    hm = float(o.get("hodo_max", 40.0))
    top = float(o.get("hodo_top", 9.0))
    small = 0.55 if not full else 0.75
    storm = STORM_NAMES.get(o.get("storm", "rm"), "RM")
    ring = "#ea580c"
    if not full:
        hx.set_facecolor((1, 1, 1, 0.9))
    srh = str(o.get("srh") or "") if full else ""
    cu0, cv0, hm = _hodo_view(d, n, o, top, hm, srh)
    hm = max(hm, float(o.get("_hodo_half") or 0.0))  # (the figure's shared view)
    # rings out to the view's far corner, labelled off the view's side of the origin
    ang = np.arctan2(cv0, cu0) - np.pi / 4 if np.hypot(cu0, cv0) > 0.1 * hm else -np.pi / 4
    for r in np.arange(10.0, np.hypot(abs(cu0) + hm, abs(cv0) + hm) + 0.1, 10.0):
        hx.add_patch(Circle((0, 0), r, fill=False, ec="0.8", lw=0.5))
        hx.text(r * np.cos(ang), r * np.sin(ang), f"{r:g}", fontsize=fs * small,
                color="0.5", ha="left", va="top", clip_on=True)
    hx.axhline(0, color="0.7", lw=0.5)
    hx.axvline(0, color="0.7", lw=0.5)
    for j in range(n):
        u, v, z = d[f"N{j}_u"], d[f"N{j}_v"], d[f"N{j}_z"]
        col = cols[j] if many else "k"
        if srh in ("1", "3") and f"N{j}_storm" in d:  # the area swept from the storm motion
            sel = z <= float(srh)
            cx, cy = (float(c) for c in d[f"N{j}_storm"])
            hx.fill(np.r_[cx, u[sel]], np.r_[cy, v[sel]], color=col if many else "#e11d48",
                    alpha=0.18, lw=0, zorder=1)
            val = d.get(f"N{j}_srh{srh}")
            if val is not None and not many:
                hx.text(0.97, 0.03, f"0–{srh} km SRH {float(val):.0f} m$^2$ s$^{{-2}}$ "
                                    f"({storm})",
                        transform=hx.transAxes, ha="right", va="bottom",
                        fontsize=fs * small, color="0.25")
        ls = HODO_LS[j % len(HODO_LS)] if many else "-"
        for z0, z1, c in HODO_BANDS:  # the height colours, one line style a sounding
            if z0 >= top:
                break
            sel = (z >= z0) & (z <= min(z1, top))
            hx.plot(u[sel], v[sel], color=c, ls=ls, zorder=3,
                    lw=1.4 if many else (1.6 if not full else 2.0))
        if o.get("hodo_labels", True):  # heights along the trace
            placed = []
            for zk in (1, 3, 6, 9, 12):
                if zk <= top and z[0] <= zk <= z[-1]:
                    uk, vk = np.interp(zk, z, u), np.interp(zk, z, v)
                    hx.plot([uk], [vk], "o", ms=2.5 if not full else 3.5, color=col,
                            mfc="white", mew=0.8, zorder=4)
                    if many and j:
                        continue
                    # close to a label already there (a short hodograph): the other side
                    near = sum(np.hypot(uk - a, vk - b) < 0.1 * hm for a, b in placed)
                    if near < 2:
                        off, ha, va = ((3, 3), "left", "bottom") if not near else \
                            ((-3, -3), "right", "top")
                        hx.annotate(f"{zk}", (uk, vk), xytext=off, ha=ha, va=va,
                                    textcoords="offset points", fontsize=fs * small,
                                    color="0.2", zorder=5)
                    placed.append((uk, vk))
        shown = hodo_marks(o)  # Bunkers movers and the 0-6 km mean wind
        for key, mk, lab in (("rm", "o", "RM"), ("lm", "o", "LM"), ("mean", "s", "")):
            c = d.get(f"N{j}_{key}")
            if key not in shown or c is None:
                continue
            cu, cv = (float(x) for x in c)
            hx.plot([cu], [cv], marker=mk, ms=4 if key != "mean" else 3.5, ls="none",
                    color=col if many else ("#1d4ed8" if key == "rm" else
                                            "#7c3aed" if key == "lm" else "0.3"),
                    mfc="none" if key != "mean" else None, mew=1.1, zorder=6)
            if lab and (not many or j == 0):
                hx.annotate(lab, (cu, cv), xytext=(4, -9), textcoords="offset points",
                            fontsize=fs * small, color="0.2", zorder=6)
        if o.get("hodo_storm", True) and f"N{j}_storm" in d:
            cu, cv = (float(x) for x in d[f"N{j}_storm"])
            hx.plot([cu], [cv], marker="o", ms=8 if full else 6, ls="none", mfc="none",
                    mec=col if many else ring, mew=1.4, zorder=7)
            if not many:  # the critical angle: storm-relative inflow and 0-500 m shear
                u5, v5 = np.interp(0.5, z, u), np.interp(0.5, z, v)
                hx.plot([cu, u[0], u5], [cv, v[0], v5], color=ring, lw=0.8, ls=":",
                        zorder=5)
    hx.set_xlim(cu0 - hm, cu0 + hm)
    hx.set_ylim(cv0 - hm, cv0 + hm)
    hx.set_aspect("equal")
    hx.set_xticks([])
    hx.set_yticks([])
    hx.text(0.03, 0.97, "m s$^{-1}$", transform=hx.transAxes, fontsize=fs * (small + 0.05),
            va="top", color="0.4")
    if full and o.get("hodo_key", True):  # the height bands
        hs = [Line2D([], [], color=c, lw=2.0, label=f"{z0:g}–{min(z1, top):g} km")
              for z0, z1, c in HODO_BANDS if z0 < top]
        if o.get("hodo_storm", True):
            hs.append(Line2D([], [], marker="o", ms=6, mfc="none", mec=ring, mew=1.4, lw=0,
                             label=f"storm ({storm})"))
        if many:  # which line style is which sounding
            hs += [Line2D([], [], color="k", lw=1.4, ls=HODO_LS[j % len(HODO_LS)],
                          label=str(d.get(f"N{j}_label", "")) or f"{j + 1}")
                   for j in range(n)]
        hx.legend(handles=hs, loc="upper right", fontsize=fs * small, frameon=False,
                  handlelength=2.6 if many else 1.2, borderaxespad=0.3, labelspacing=0.25)
