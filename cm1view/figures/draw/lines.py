"""Time-series, distribution, vertical profile, joint distribution and azimuthal mean
panels."""

import numpy as np
from matplotlib.colors import LogNorm, Normalize
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnchoredOffsetbox, TextArea, VPacker
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import MaxNLocator

from .base import (SND_COLORS, by_run, colormap, entry_colors, font_size, panel_legend,
                   run_color, run_style, _levels)

def _lines(ax, d, spec, fs):
    """Time-series panel: one line per (series, run).  Series in other units get
    their own y axis on the right.  A series of one run: its own colour and line
    style.  A series of several runs: alone in the panel, a line per run in the run's
    colour and the series' line style; with other series, the series' colour and a
    line style per run.  An ensemble (S<n>_ens): its band shaded and centre drawn in
    the series' colour and line style, its members (S<n>_mem) thin and pale ("faint")
    or as other lines ("full")."""
    ents = spec.get("series", [])
    n = int(d.get("nlines", 0))
    es = {int(d[f"S{j}_e"]) for j in range(n)}
    nr = len(spec.get("runs") or [])
    ts = spec.get("ts", {})
    mark = ts.get("mark") or ""
    axes, items, handles = {}, {}, []
    for j in range(n):
        e = ents[int(d[f"S{j}_e"])]
        k = int(d[f"S{j}_r"])
        units = e.get("units", "")
        key = ("right", units) if e.get("axis") == "right" else units
        if key not in axes:
            if not axes:
                axes[key] = ax
            else:
                tw = ax.twinx()
                extra = sum(a is not ax for a in axes.values())
                if extra:  # a third axis and more: further out on the right
                    tw.spines["right"].set_position(("axes", 1.0 + 0.16 * extra))
                axes[key] = tw
        ens, faint = f"S{j}_ens" in d, f"S{j}_mem" in d and \
            e.get("ens_members", "faint") == "faint"
        color, ls = e.get("color", "k"), e.get("ls") or "-"
        rs = [] if e.get("source") == "table" else e.get("runs")  # (your own data: no run)
        if not ens and (rs is None and nr > 1 or rs is not None and len(rs) > 1):
            if len(es) == 1:  # (several runs, alone: a colour per run)
                color = run_color(spec, k)
            else:
                ls = run_style(spec, k)
        t, v = d[f"S{j}_t"], d[f"S{j}_v"]
        ext = [] if faint else series_extremes(t, v, mark, ts)
        label = str(d[f"S{j}_label"])
        if ts.get("mark_legend") and ext:
            label = f"{label} ({'; '.join(f'{w} {y:.3g} at {x:g} min' for w, x, y in ext)})"
        lw = float(e.get("lw", 1.5))
        if faint:  # (an ensemble's member: thin and pale, not in the legend)
            axes[key].plot(t, v, color=color, ls=ls, lw=0.6 * lw, alpha=0.4, zorder=1.5)
            items.setdefault(key, []).append((e, e.get("color", "k")))
            continue
        if ens:
            a = float(e.get("ens_alpha", 0.25))
            axes[key].fill_between(t, d[f"S{j}_lo"], d[f"S{j}_hi"], color=color, alpha=a,
                                   lw=0, zorder=1.2)
        h, = axes[key].plot(t, v, color=color, ls=ls, lw=lw,
                            marker=e.get("marker") or None, ms=3, label=label)
        if ens:  # (the legend's entry: the band with its centre's colour as the edge)
            h = Patch(facecolor=color, alpha=float(e.get("ens_alpha", 0.25)) + 0.15,
                      edgecolor=color, lw=lw, label=label)
        for w, x, y in ext:
            axes[key].plot(x, y, "o", ms=4, color=color, zorder=4)
            axes[key].annotate(f"{y:.3g}", (x, y), xytext=(0, 4 if w == "max" else -4),
                               textcoords="offset points", ha="center",
                               va="bottom" if w == "max" else "top", color=color,
                               fontsize=fs * 0.8, annotation_clip=True)
        handles.append(h)
        items.setdefault(key, []).append((e, color))
    for key, its in items.items():
        a = axes[key]
        a.set_ylabel("; ".join(dict.fromkeys(e.get("ylabel") or e.get("units", "")
                                             for e, _ in its)))
        if len(axes) > 1 and len({c for _, c in its}) == 1:  # axis coloured like its line
            a.yaxis.label.set_color(its[0][1])
            a.tick_params(axis="y", colors=its[0][1])
    lo, hi = ts.get("ymin"), ts.get("ymax")  # the left axis's range (blank: the data's)
    if lo not in (None, "") or hi not in (None, ""):
        ax.set_ylim(None if lo in (None, "") else float(lo), None if hi in (None, "") else float(hi))
    if ts.get("zero_line"):
        ax.axhline(0.0, color="0.6", lw=0.6, zorder=0)
    if ts.get("legend", True) and (len(handles) > 1 or (ts.get("mark_legend") and mark)
                                   or spec.get("_legend_extra")):
        panel_legend(ax, handles, ts, spec, "best", False)


def series_extremes(t, v, mark, ts=None):
    """[("max" / "min", time, value)] of a line over the plotted times (ts tmin, tmax
    in minutes; blank: all): mark "max", "min" or "both" ("" : none)."""
    if mark not in ("max", "min", "both"):
        return []
    t, v = np.asarray(t, dtype=float), np.asarray(v, dtype=float)
    ok = np.isfinite(t) & np.isfinite(v)
    ts = ts or {}
    for k, cmp in (("tmin", np.greater_equal), ("tmax", np.less_equal)):
        if ts.get(k) not in (None, ""):
            ok &= cmp(t, float(ts[k]))
    if not ok.any():
        return []
    i = np.flatnonzero(ok)
    out = []
    if mark in ("max", "both"):
        j = i[np.argmax(v[i])]
        out.append(("max", float(t[j]), float(v[j])))
    if mark in ("min", "both"):
        j = i[np.argmin(v[i])]
        out.append(("min", float(t[j]), float(v[j])))
    return out


DIST_PROBS = (0.0, 0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 0.999, 1.0)
DIST_NORM_LABEL = {"count": "count", "pdf": "probability density", "frac": "fraction"}


def dist_span(lo, hi):
    """The range of a summary's fine histogram: its minimum to maximum (one value:
    ± 0.5 around it)."""
    return (lo, hi) if hi > lo else (lo - 0.5, lo + 0.5)


def dist_of(d, n):
    """Summary n of distribution panel data d (as dist.summarize gives it)."""
    s = [float(v) for v in np.asarray(d[f"D{n}_s"], dtype=float).ravel()]
    return dict(n=s[0], mean=s[1], std=s[2], lo=s[3], hi=s[4], wlo=s[5], whi=s[6],
                q=np.asarray(d[f"D{n}_q"], dtype=float), h=np.asarray(d[f"D{n}_h"], dtype=float))


def dist_arrays(st, n):
    """The panel arrays of summary st as distribution n (dist_of reads them back)."""
    return {f"D{n}_s": np.array([st[k] for k in ("n", "mean", "std", "lo", "hi", "wlo", "whi")],
                                dtype=float),
            f"D{n}_q": np.asarray(st["q"], dtype=float), f"D{n}_h": np.asarray(st["h"])}


def dist_q(st, p):
    """Quantile p (one of DIST_PROBS) of summary st."""
    return float(st["q"][DIST_PROBS.index(p)])


def _fine_edges(st):
    lo, hi = dist_span(st["lo"], st["hi"])
    return np.linspace(lo, hi, len(st["h"]) + 1)


def dist_edges(sts, bins=50, width=None, lo=None, hi=None):
    """Bin edges shared by summaries sts: from lo to hi (None: the smallest minimum,
    the largest maximum), `width` wide (None: `bins` bins)."""
    los = [s["lo"] for s in sts if s["n"]]
    his = [s["hi"] for s in sts if s["n"]]
    a = float(lo) if lo is not None else min(los, default=0.0)
    b = float(hi) if hi is not None else max(his, default=1.0)
    if not b > a:
        a, b = dist_span(a, a)
    if width is not None and float(width) > 0:
        k = max(1, min(2000, int(np.ceil((b - a) / float(width) - 1e-9))))
        return a + float(width) * np.arange(k + 1)
    return np.linspace(a, b, max(1, int(bins or 50)) + 1)


def dist_hist(st, edges, norm="count"):
    """Histogram of summary st in bins `edges`: counts, "pdf" (density: the whole
    sample integrates to 1, so values outside the bins count too) or "frac" (fraction
    of the whole sample per bin)."""
    fe = _fine_edges(st)
    v, _ = np.histogram(0.5 * (fe[:-1] + fe[1:]), bins=edges, weights=st["h"])
    if norm == "pdf":
        return v / (max(st["n"], 1.0) * np.diff(edges))
    if norm == "frac":
        return v / max(st["n"], 1.0)
    return v


def dist_cdf(st, above=False):
    """(x, fraction of the sample at or below x), or above x."""
    x = _fine_edges(st)
    y = np.concatenate([[0.0], np.cumsum(st["h"])]) / max(st["n"], 1.0)
    return x, (np.clip(1.0 - y, 0.0, 1.0) if above else y)


def dist_kde(st, npts=256):
    """(x, density) of summary st, minimum to maximum: its fine histogram smoothed
    with a Gaussian kernel of Silverman's bandwidth (at least a grid step)."""
    lo, hi = dist_span(st["lo"], st["hi"])
    edges = np.linspace(lo, hi, npts + 1)
    v = dist_hist(st, edges)
    dx = edges[1] - edges[0]
    iqr = dist_q(st, 0.75) - dist_q(st, 0.25)
    sig = min(st["std"], iqr / 1.34) if iqr > 0 else st["std"]
    s = max(0.9 * (sig or dx) * max(st["n"], 1.0) ** -0.2 / dx, 0.5)  # (grid steps)
    k = np.arange(-min(int(np.ceil(4 * s)), npts - 1), min(int(np.ceil(4 * s)), npts - 1) + 1)
    ker = np.exp(-0.5 * (k / s) ** 2)
    dens = np.convolve(v, ker / ker.sum(), mode="same") / (max(st["n"], 1.0) * dx)
    return 0.5 * (edges[:-1] + edges[1:]), dens


def dist_whiskers(st, how="tukey"):
    """Whisker ends of a box: "tukey" (the furthest values within 1.5 IQR of the box),
    "range" (min, max), "p5" (5th, 95th percentile) or "p1" (1st, 99th)."""
    if how == "range":
        return st["lo"], st["hi"]
    if how in ("p5", "p1"):
        p = 0.05 if how == "p5" else 0.01
        return dist_q(st, p), dist_q(st, round(1.0 - p, 3))
    return st["wlo"], st["whi"]


DIST_STATS = {"n": "n", "mean": "mean", "sd": "sd", "median": "median", "iqr": "IQR",
              "min": "min", "max": "max", "p5_95": "5–95 %", "p1_99": "1–99 %"}


def dist_stat_keys(o):
    """The statistics dist options o show (DIST_STATS keys, in that order); an older
    spec's stats=True: mean, sd and n."""
    v = o.get("stats")
    if v is True:
        return ["mean", "sd", "n"]
    if not v:
        return []
    v = [v] if isinstance(v, str) else list(v)
    return [k for k in v if k in DIST_STATS]


def dist_stats_text(st, keys):
    """Statistics `keys` of summary st as text: "mean 3.2, sd 1.1, n = 1,234"."""
    def q(p):
        return dist_q(st, p)

    out = []
    for k in keys:
        if k == "n":
            out.append(f"n = {st['n']:,.0f}")
        elif k == "iqr":
            out.append(f"IQR {q(0.75) - q(0.25):.3g}")
        elif k in ("p5_95", "p1_99"):
            a, b = (0.05, 0.95) if k == "p5_95" else (0.01, 0.99)
            out.append(f"{DIST_STATS[k]} {q(a):.3g} to {q(b):.3g}")
        else:
            v = {"mean": st["mean"], "sd": st["std"], "median": q(0.5), "min": st["lo"],
                 "max": st["hi"]}[k]
            out.append(f"{DIST_STATS[k]} {v:.3g}")
    return ", ".join(out)


def _stats_box(ax, lines, colors, loc, fs):
    """Lines of text in a corner of the panel, each in its colour, on a white box."""
    box = VPacker(children=[TextArea(t, textprops=dict(color=c, size=fs))
                            for t, c in zip(lines, colors)], align="left", pad=0, sep=2)
    at = AnchoredOffsetbox(loc=loc, child=box, pad=0.3, borderpad=0.5, frameon=True)
    at.patch.set(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.85)
    at.set_in_layout(False)
    ax.add_artist(at)


def _bar_labels(ax, st, v, edges, how, color, fs):
    """Each non-empty bin's count, percentage of the whole sample, or value (as the
    y axis has it: how "axis") above its bar."""
    c = dist_hist(st, edges)
    vert = len(v) > 20
    for x, y, k in zip(0.5 * (edges[:-1] + edges[1:]), v, c):
        if not k > 0 or not np.isfinite(y):
            continue
        txt = (f"{k:,.0f}" if how == "count" or (how == "axis" and y == k) else
               f"{100.0 * k / max(st['n'], 1.0):.2g}%" if how == "percent" else f"{y:.3g}")
        ax.annotate(txt, (x, y), xytext=(0, 2), textcoords="offset points", ha="center",
                    va="bottom", rotation=90 if vert else 0, color=color, fontsize=fs,
                    annotation_clip=True)


def dist_colors(spec, d):
    """Colour of each distribution of panel data d (entry_colors)."""
    return entry_colors(spec, d, "dists", "ndist", "D")


def _dists(ax, d, spec, fs):
    """Distribution panel: spec["dist"]["plot"] hist (in common bins), ecdf, box or
    violin (one per distribution, side by side)."""
    o = spec.get("dist", {})
    n = int(d.get("ndist", 0))
    sts = [dist_of(d, j) for j in range(n)]
    cols = dist_colors(spec, d)
    labels = [str(d.get(f"D{j}_label", "")) for j in range(n)]
    keys = dist_stat_keys(o)
    in_box = bool(keys) and o.get("stats_at", "legend") == "box"
    if keys and not in_box:
        labels = [f"{lab} ({dist_stats_text(s, keys)})".lstrip() for lab, s in zip(labels, sts)]
    if in_box:
        _stats_box(ax, [f"{lab}: {dist_stats_text(s, keys)}" if lab and n > 1 else
                        dist_stats_text(s, keys) for lab, s in zip(labels, sts)],
                   cols if n > 1 else ["0.15"], o.get("stats_loc", "upper right"),
                   font_size(spec, "legend"))

    def num(k):
        v = o.get(k)
        return None if v in (None, "") else float(v)

    kind, lw = o.get("plot", "hist"), float(o.get("lw", 1.5))
    alpha = float(o.get("alpha", 0.35))
    vlo, vhi = num("xmin"), num("xmax")
    vlab = "; ".join(dict.fromkeys(str(d[f"D{j}_xl"]) for j in range(n) if d.get(f"D{j}_xl")))
    handles = []
    if kind in ("hist", "ecdf"):
        if kind == "hist":
            edges = dist_edges(sts, o.get("bins", 50), num("width"), vlo, vhi)
            norm, style = o.get("norm", "count"), o.get("hstyle", "stepfilled")
            bl, top = o.get("bar_labels") or "", 0.0
            for st, c, lab in zip(sts, cols, labels):
                v = dist_hist(st, edges, norm)
                if bl:
                    _bar_labels(ax, st, v, edges, bl, c if n > 1 else "0.15", fs * 0.7)
                    top = max(top, float(np.nanmax(v, initial=0.0)))
                if style == "bar":
                    ax.bar(edges[:-1], v, width=np.diff(edges), align="edge", color=c,
                           alpha=1.0 if n == 1 else alpha, edgecolor="white", lw=0.4)
                    handles.append(Patch(facecolor=c, alpha=1.0 if n == 1 else alpha,
                                         label=lab))
                    continue
                if style == "stepfilled":
                    ax.stairs(v, edges, fill=True, color=c, alpha=alpha, lw=0)
                h = ax.stairs(v, edges, color=c, lw=lw, label=lab)
                handles.append(Patch(facecolor=c, alpha=alpha, edgecolor=c, label=lab)
                               if style == "stepfilled" else h)
            ax.set_xlim(edges[0], edges[-1])
            ylab = DIST_NORM_LABEL.get(norm, "count")
        else:
            above = o.get("cum", "below") == "above"
            for st, c, lab in zip(sts, cols, labels):
                x, y = dist_cdf(st, above)
                h, = ax.plot(x, y, color=c, lw=lw, label=lab)
                handles.append(h)
            ax.set_xlim(vlo, vhi)
            ylab = "fraction above" if above else "cumulative fraction"
        if o.get("logy"):
            ax.set_yscale("log")
        if num("ymin") is not None or num("ymax") is not None:
            ax.set_ylim(num("ymin"), num("ymax"))
        elif kind == "hist" and not o.get("logy"):
            ax.set_ylim(bottom=0.0)
            if bl and top > 0:  # (room for the labels above the highest bar)
                ax.set_ylim(top=top * (1.25 if len(edges) > 21 else 1.1))
        if o.get("zero_line"):
            ax.axvline(0.0, color="0.6", lw=0.6, zorder=0)
        ax.set_xlabel(vlab)
        ax.set_ylabel(ylab)
        if o.get("legend", True) and (n > 1 or (keys and not in_box)
                                      or spec.get("_legend_extra")):
            panel_legend(ax, handles, o, spec, "best", False)
        return
    horiz = bool(o.get("horizontal"))
    # ("width" is the histogram bin width, None for automatic)
    w = float(o.get("box_width") or (0.6 if kind == "box" else 0.8))

    def seg(p0, p1, v0, v1, **kw):  # a line from (place, value) to (place, value)
        if horiz:
            ax.plot([v0, v1], [p0, p1], **kw)
        else:
            ax.plot([p0, p1], [v0, v1], **kw)

    for p, (st, c) in enumerate(zip(sts, cols), start=1):
        q1, med, q3 = (dist_q(st, k) for k in (0.25, 0.5, 0.75))
        if kind == "violin":
            x, dens = dist_kde(st)
            dd = dens / max(dens.max(), 1e-300) * w / 2
            (ax.fill_between if horiz else ax.fill_betweenx)(
                x, p - dd, p + dd, facecolor=c, alpha=alpha, edgecolor=c, lw=lw * 0.6)
            lo, hi = dist_whiskers(st, o.get("whis", "tukey"))
            seg(p, p, lo, hi, color="0.15", lw=lw * 0.6, solid_capstyle="butt")
            seg(p, p, q1, q3, color="0.15", lw=lw * 3.0, solid_capstyle="butt")
            mx, my = (med, p) if horiz else (p, med)
            ax.plot(mx, my, "o", ms=lw * 2.5, mfc="white", mec="0.15", mew=0.6)
        else:
            lo, hi = dist_whiskers(st, o.get("whis", "tukey"))
            xy, wh = ((q1, p - w / 2), (q3 - q1, w)) if horiz else ((p - w / 2, q1), (w, q3 - q1))
            ax.add_patch(Rectangle(xy, *wh, facecolor=c, alpha=alpha, edgecolor="none"))
            ax.add_patch(Rectangle(xy, *wh, facecolor="none", edgecolor=c, lw=lw))
            seg(p - w / 2, p + w / 2, med, med, color=c, lw=lw * 1.6, solid_capstyle="butt")
            for a, b in ((q1, lo), (q3, hi)):
                seg(p, p, a, b, color=c, lw=lw)
                seg(p - w / 5, p + w / 5, b, b, color=c, lw=lw)
        if o.get("means", True):
            mx, my = (st["mean"], p) if horiz else (p, st["mean"])
            ax.plot(mx, my, "D", ms=lw * 2.6, mfc="white", mec=c, mew=lw * 0.7, zorder=4)
    pos = list(range(1, n + 1))
    (ax.set_yticks if horiz else ax.set_xticks)(pos, labels)
    (ax.set_ylim if horiz else ax.set_xlim)(0.5, n + 0.5)
    if vlo is not None or vhi is not None:
        (ax.set_xlim if horiz else ax.set_ylim)(vlo, vhi)
    if o.get("logy"):
        (ax.set_xscale if horiz else ax.set_yscale)("symlog" if any(
            s["lo"] <= 0 for s in sts) else "log")
    if o.get("zero_line"):
        (ax.axvline if horiz else ax.axhline)(0.0, color="0.6", lw=0.6, zorder=0)
    (ax.set_xlabel if horiz else ax.set_ylabel)(vlab)
    (ax.set_ylabel if horiz else ax.set_xlabel)("")


def profile_colors(spec, d):
    """(colour, line style) of each profile line of panel data d.  Colour: its
    profile's own, else its run's when each of the panel's lines comes from another run
    (by_run), else the next of SND_COLORS for each profile.  A profile of several runs
    not coloured by run: a line style per run.  An ensemble's band and members: their
    profile's colour; your own data: its own colour."""
    ents = spec.get("profiles", [])
    n = int(d.get("nprof", 0))
    es = [int(d[f"P{j}_e"]) for j in range(n)]
    runs = [int(d[f"P{j}_r"]) for j in range(n)]
    ent = [ents[e] if e < len(ents) else {} for e in es]
    plain = [j for j in range(n) if f"P{j}_ens" not in d and f"P{j}_mem" not in d
             and ent[j].get("source") != "table"]
    rc = by_run(spec, [runs[j] for j in plain])
    order = list(dict.fromkeys(es))
    several = {e for e in es if es.count(e) > 1}
    out = []
    for j in range(n):
        e, x = es[j], ent[j]
        mine = x.get("color") or SND_COLORS[order.index(e) % len(SND_COLORS)]
        ls = x.get("ls") or "-"
        if j not in plain:
            out.append((mine, ls))
        elif x.get("color"):
            out.append((mine, run_style(spec, runs[j]) if e in several and not rc else ls))
        elif rc:
            out.append((run_color(spec, runs[j]), ls))
        else:
            out.append((mine, run_style(spec, runs[j]) if e in several else ls))
    return out


def _profiles(ax, d, spec, fs):
    """Vertical profile panel: one line per profile and run, value (x) against height
    (y); an ensemble's band shaded and centre drawn in its profile's colour, its runs
    thin and pale ("faint") or as other lines; spec["prof"]: the axes' ranges, a zero
    line and the legend."""
    o = spec.get("prof", {})
    ents = spec.get("profiles", [])
    n = int(d.get("nprof", 0))
    looks = profile_colors(spec, d)

    def num(k):
        v = o.get(k)
        return None if v in (None, "") else float(v)

    handles, zlo, zhi = [], np.inf, -np.inf
    for j in range(n):
        e = ents[int(d[f"P{j}_e"])] if int(d[f"P{j}_e"]) < len(ents) else {}
        z, v = np.asarray(d[f"P{j}_z"]), np.asarray(d[f"P{j}_v"])
        color, ls = looks[j]
        lw, label = float(e.get("lw") or 1.5), str(d.get(f"P{j}_label", ""))
        if f"P{j}_mem" in d and e.get("ens_members", "faint") == "faint":
            ax.plot(v, z, color=color, ls=ls, lw=0.6 * lw, alpha=0.4, zorder=1.5)
        elif f"P{j}_ens" in d:
            a = float(e.get("ens_alpha", 0.25))
            ax.fill_betweenx(z, d[f"P{j}_lo"], d[f"P{j}_hi"], color=color, alpha=a, lw=0,
                             zorder=1.2)
            ax.plot(v, z, color=color, ls=ls, lw=lw)
            handles.append(Patch(facecolor=color, alpha=a + 0.15, edgecolor=color, lw=lw,
                                 label=label))
        else:
            h, = ax.plot(v, z, color=color, ls=ls, lw=lw, marker=e.get("marker") or None,
                         ms=3, label=label)
            handles.append(h)
        r = e.get("recipe") or {}  # (the layer asked for, not only the levels' centres)
        if z.size:
            top = float(z[-1]) + (0.5 * float(z[-1] - z[-2]) if z.size > 1 else 0.0)
            zlo = min(zlo, max(0.0, min(float(r.get("z0", z[0])), float(z[0]))))
            zhi = max(zhi, float(z[-1]), min(float(r.get("z1", top)), top))
    if np.isfinite(zlo):
        zhi = zhi if zhi > zlo else zlo + 1.0
        ax.set_ylim(zlo if num("zmin") is None else num("zmin"),
                    zhi if num("zmax") is None else num("zmax"))
    if num("xmin") is not None or num("xmax") is not None:
        ax.set_xlim(num("xmin"), num("xmax"))
    if o.get("zero_line"):
        ax.axvline(0.0, color="0.6", lw=0.6, zorder=0)
    ax.set_xlabel("; ".join(dict.fromkeys(str(d[f"P{j}_xl"]) for j in range(n)
                                          if d.get(f"P{j}_xl"))))
    if o.get("legend", True) and (len(handles) > 1 or spec.get("_legend_extra")):
        panel_legend(ax, handles, o, spec, "best", False)


JOINT_STATS = {"n": "n", "r": "r", "r2": "r²", "fit": "fit", "means": "means"}


def joint_of(d, n):
    """Summary n of joint distribution panel data d (as joint.summarize gives it)."""
    s = [float(v) for v in np.asarray(d[f"J{n}_s"], dtype=float).ravel()]
    p = np.asarray(d[f"J{n}_p"], dtype=float).reshape(2, -1)
    return dict(n=s[0], mx=s[1], my=s[2], sx=s[3], sy=s[4], r=s[5], xlo=s[6], xhi=s[7],
                ylo=s[8], yhi=s[9], h=np.asarray(d[f"J{n}_h"], dtype=float), px=p[0], py=p[1])


def joint_arrays(st, n):
    """The panel arrays of summary st as joint distribution n (joint_of reads them
    back)."""
    keys = ("n", "mx", "my", "sx", "sy", "r", "xlo", "xhi", "ylo", "yhi")
    return {f"J{n}_s": np.array([st[k] for k in keys], dtype=float),
            f"J{n}_h": np.asarray(st["h"], dtype=np.int32),
            f"J{n}_p": np.vstack([st["px"], st["py"]]).astype(np.float32)}


def joint_edges(sts, bins=60, xlo=None, xhi=None, ylo=None, yhi=None):
    """x and y bin edges shared by summaries sts: `bins` bins each, from the given
    limits (None: the smallest minimum, the largest maximum)."""
    out = []
    for lo, hi, a_k, b_k in ((xlo, xhi, "xlo", "xhi"), (ylo, yhi, "ylo", "yhi")):
        a = float(lo) if lo is not None else min((s[a_k] for s in sts if s["n"]), default=0.0)
        b = float(hi) if hi is not None else max((s[b_k] for s in sts if s["n"]), default=1.0)
        if not b > a:
            a, b = dist_span(a, a)
        out.append(np.linspace(a, b, max(1, int(bins or 60)) + 1))
    return out


def _overlap(f, e):
    """(fine bins, coarse bins): the share of each fine bin (edges f) inside each
    coarse bin (edges e), so a fine bin split by a coarse edge is shared out."""
    lo = np.maximum(f[:-1, None], e[None, :-1])
    hi = np.minimum(f[1:, None], e[None, 1:])
    return np.clip(hi - lo, 0.0, None) / np.diff(f)[:, None]


def joint_hist(st, ex, ey, norm="count"):
    """2D histogram (x along the first axis) of summary st in bins ex, ey: counts,
    "pdf" (density: the whole sample integrates to 1) or "frac" (fraction of the whole
    sample per bin), from its fine histogram."""
    h = st["h"]
    fx = np.linspace(*dist_span(st["xlo"], st["xhi"]), h.shape[0] + 1)
    fy = np.linspace(*dist_span(st["ylo"], st["yhi"]), h.shape[1] + 1)
    v = _overlap(fx, ex).T @ np.asarray(h, dtype=float) @ _overlap(fy, ey)
    if norm == "pdf":
        return v / (max(st["n"], 1.0) * np.outer(np.diff(ex), np.diff(ey)))
    if norm == "frac":
        return v / max(st["n"], 1.0)
    return v


def joint_levels(H, pcts):
    """[(value, p)] of 2D histogram H: the values whose contours enclose the fractions
    p of pcts (in %) of what it counts (the densest bins first), by increasing value;
    [] for an empty H."""
    v = np.sort(np.asarray(H, dtype=float).ravel())[::-1]
    tot = v.sum()
    if not tot > 0:
        return []
    c = np.cumsum(v) / tot
    out = {}
    for p in sorted(pcts):  # (two at one value: the smaller p names it)
        lv = float(v[min(np.searchsorted(c, p / 100.0), v.size - 1)])
        if 0 < p < 100 and lv > 0:
            out.setdefault(lv, p)
    return sorted(out.items())


def joint_pcts(text):
    """The percentages of a contour list ("50, 90"), 0 < p < 100, from the largest."""
    out = []
    for tok in str(text or "").replace(",", " ").split():
        try:
            p = float(tok.rstrip("%"))
        except ValueError:
            continue
        if 0 < p < 100:
            out.append(p)
    return sorted(set(out), reverse=True)


def joint_stats_text(st, keys):
    """'n 12,345, r 0.82, fit y = 0.5x + 1.2' of summary st for keys (JOINT_STATS)."""
    out = []
    for k in keys:
        r = st["r"]
        if k == "n":
            out.append(f"n {st['n']:,.0f}")
        elif k == "r":
            out.append(f"r {r:.2f}" if np.isfinite(r) else "r –")
        elif k == "r2":
            out.append(f"r² {r * r:.2f}" if np.isfinite(r) else "r² –")
        elif k == "fit" and np.isfinite(r):
            a = r * st["sy"] / st["sx"]
            b = st["my"] - a * st["mx"]
            out.append(f"y = {a:.3g}x {'−' if b < 0 else '+'} {abs(b):.3g}")
        elif k == "means":
            out.append(f"means {st['mx']:.3g}, {st['my']:.3g}")
    return ", ".join(out)


def joint_colors(spec, d):
    """Colour of each joint distribution of panel data d (entry_colors)."""
    return entry_colors(spec, d, "joints", "njoint", "J", data_runs=True)


def _joints(ax, d, spec, fs):
    """Joint distribution panel: spec["joint"]["plot"] "hist" (the first one's 2D
    histogram as shading, the others as density contours), "scatter" (a random pick of
    each one's pairs) or "contour" (density contours of each), x field against y field;
    contours enclose the given percentages of the pairs.  Fit lines, a 1:1 line and the
    statistics (of every pair) as asked."""
    o = spec.get("joint", {})
    n = int(d.get("njoint", 0))
    sts = [joint_of(d, j) for j in range(n)]
    cols = joint_colors(spec, d)
    labels = [str(d.get(f"J{j}_label", "")) for j in range(n)]

    def num(k):
        v = o.get(k)
        return None if v in (None, "") else float(v)

    kind, norm = o.get("plot", "hist"), o.get("norm", "count")
    lw, alpha = float(o.get("lw", 1.2)), float(o.get("alpha", 0.5))
    ex, ey = joint_edges(sts, o.get("bins", 60), num("xmin"), num("xmax"), num("ymin"),
                         num("ymax"))
    xc, yc = 0.5 * (ex[:-1] + ex[1:]), 0.5 * (ey[:-1] + ey[1:])
    pcts = joint_pcts(o.get("pcts", "50, 90"))
    handles = []
    for j, (st, c, lab) in enumerate(zip(sts, cols, labels)):
        H = joint_hist(st, ex, ey, norm)
        if kind == "hist" and j == 0:
            Hm = np.ma.masked_less_equal(H, 0.0)
            cm = colormap(o.get("cmap") or "viridis", bool(o.get("reverse")))
            pos = H[H > 0]
            if o.get("log") and pos.size and pos.max() > pos.min():
                nm = LogNorm(vmin=float(pos.min()), vmax=float(pos.max()))
            else:
                nm = Normalize(vmin=0.0, vmax=float(H.max()) or 1.0)
            m = ax.pcolormesh(ex, ey, Hm.T, cmap=cm, norm=nm, rasterized=True)
            if o.get("colorbar", True):
                cb = ax.figure.colorbar(m, ax=ax, pad=0.02, fraction=0.06, aspect=30)
                cb.set_label(DIST_NORM_LABEL.get(norm, "count"))
                cb.ax.tick_params(labelsize=fs * 0.8)
            handles.append(Patch(facecolor=cm(0.6), label=lab))
            line_c = "k"
        elif kind == "scatter":
            ax.plot(st["px"], st["py"], ".", color=c, ms=float(o.get("ms", 2.0)), alpha=alpha,
                    mew=0, rasterized=True)
            handles.append(Line2D([], [], ls="", marker="o", color=c, ms=5, label=lab))
            line_c = c
        else:
            handles.append(Line2D([], [], color=c, lw=lw, label=lab))
            line_c = c
        contours = kind == "contour" or (kind == "hist" and j > 0) or o.get("contours")
        if contours and pcts:
            lv = joint_levels(H, pcts)
            if lv:
                cs = ax.contour(xc, yc, H.T, levels=[v for v, _ in lv], colors=[line_c],
                                linewidths=lw)
                if o.get("contour_labels", True):
                    at = dict(lv)
                    ax.clabel(cs, fontsize=fs * 0.7, fmt=lambda v, at=at:
                              f"{at[min(at, key=lambda k: abs(k - v))]:g}%")
        if o.get("fit") and np.isfinite(st["r"]):
            a = st["r"] * st["sy"] / st["sx"]
            ax.plot(ex[[0, -1]], st["my"] + a * (ex[[0, -1]] - st["mx"]), color=line_c,
                    lw=lw, ls="--")
    ax.set_xlim(ex[0], ex[-1])
    ax.set_ylim(ey[0], ey[-1])
    if o.get("one_one"):
        lo, hi = max(ex[0], ey[0]), min(ex[-1], ey[-1])
        if hi > lo:
            ax.plot([lo, hi], [lo, hi], color="0.5", lw=0.8, ls=":", zorder=1)
    if o.get("zero_line"):
        ax.axvline(0.0, color="0.6", lw=0.6, zorder=0)
        ax.axhline(0.0, color="0.6", lw=0.6, zorder=0)
    keys = [k for k in (o.get("stats") or []) if k in JOINT_STATS]
    if keys:
        _stats_box(ax, [f"{lab}: {joint_stats_text(s, keys)}" if lab and n > 1 else
                        joint_stats_text(s, keys) for lab, s in zip(labels, sts)],
                   cols if n > 1 else ["0.15"], o.get("stats_loc", "upper left"),
                   font_size(spec, "legend"))
    ax.set_xlabel("; ".join(dict.fromkeys(str(d[f"J{j}_xl"]) for j in range(n)
                                          if d.get(f"J{j}_xl"))))
    ax.set_ylabel("; ".join(dict.fromkeys(str(d[f"J{j}_yl"]) for j in range(n)
                                          if d.get(f"J{j}_yl"))))
    if o.get("legend", True) and (n > 1 or spec.get("_legend_extra")):
        panel_legend(ax, handles, o, spec, "best", False)


def azim_edges(c):
    """Cell edges of bin or level centres c (the ends half a step beyond; radii from
    0)."""
    c = np.asarray(c, dtype=np.float64)
    if c.size < 2:
        return np.array([c[0] - 0.5, c[0] + 0.5]) if c.size else np.array([0.0, 1.0])
    mid = 0.5 * (c[1:] + c[:-1])
    return np.concatenate([[c[0] - (mid[0] - c[0])], mid, [c[-1] + (c[-1] - mid[-1])]])


def azim_range(v, o, diverging):
    """(vmin, vmax) of the shading: spec["azim"]'s, else the data's (symmetric about 0
    for a diverging field whose values have both signs)."""
    fin = np.asarray(v)[np.isfinite(v)]
    lo, hi = (float(fin.min()), float(fin.max())) if fin.size else (0.0, 1.0)
    if diverging and lo < 0 < hi:
        lo, hi = -max(-lo, hi), max(-lo, hi)
    lo = lo if o.get("vmin") in (None, "") else float(o["vmin"])
    hi = hi if o.get("vmax") in (None, "") else float(o["vmax"])
    return (lo, hi) if hi > lo else (lo, lo + 1.0)


def azim_levels(v, text, n=8):
    """Contour levels: `text` ('10, 20' or '-6:6:2'), else about n from the data."""
    lv = _levels(text) if str(text or "").strip() else []
    if lv:
        return lv
    fin = np.asarray(v)[np.isfinite(v)]
    if not fin.size or fin.max() <= fin.min():
        return []
    return [float(x) for x in MaxNLocator(n).tick_values(fin.min(), fin.max())
            if fin.min() < x < fin.max() and x != 0.0]


def _azims(ax, d, spec, fs):
    """Azimuthal mean panel, radius (x) against height (y): the first one shaded
    (spec["azim"]: grid cells or filled contours, colormap (blank: the field's), range,
    colorbar), the others as labelled contour lines in their colours (negative ones
    dashed)."""
    o = spec.get("azim", {})
    ents = spec.get("azims", [])
    n = int(d.get("nazim", 0))

    def num(k):
        v = o.get(k)
        return None if v in (None, "") else float(v)

    handles, rhi, zlo, zhi = [], 0.0, np.inf, -np.inf
    for j in range(n):
        e = ents[int(d[f"A{j}_e"])] if int(d[f"A{j}_e"]) < len(ents) else {}
        x, z, v = (np.asarray(d[f"A{j}_{k}"]) for k in ("x", "z", "v"))
        xe, ze = azim_edges(x), azim_edges(z)
        rhi, zlo, zhi = max(rhi, xe[-1]), min(zlo, max(0.0, ze[0])), max(zhi, ze[-1])
        lab = str(d.get(f"A{j}_label", ""))
        if j == 0:
            cm = colormap(o.get("cmap") or str(d.get("A0_cm") or "viridis"),
                          bool(o.get("reverse")))
            lo, hi = azim_range(v, o, bool(int(d.get("A0_div", 0))))
            vm = np.ma.masked_invalid(v)
            if o.get("plot", "mesh") == "filled" and x.size > 1 and z.size > 1:
                lv = np.linspace(lo, hi, max(2, int(o.get("nlevels") or 15)) + 1)
                m = ax.contourf(x, z, vm, lv, cmap=cm, extend="both")
            else:
                m = ax.pcolormesh(xe, ze, vm, cmap=cm, vmin=lo, vmax=hi, rasterized=True)
            if o.get("colorbar", True):
                cb = ax.figure.colorbar(m, ax=ax, pad=0.02, fraction=0.06, aspect=30)
                cb.set_label(o.get("cbar_label") or str(d.get("A0_cl", "")))
                cb.ax.tick_params(labelsize=fs * 0.8)
            handles.append(Patch(facecolor=cm(0.7), label=lab))
            continue
        c = e.get("color") or SND_COLORS[(j - 1) % len(SND_COLORS)]
        lw = float(e.get("lw") or 1.0)
        lv = azim_levels(v, e.get("levels", ""))
        if lv and x.size > 1 and z.size > 1:
            cs = ax.contour(x, z, np.ma.masked_invalid(v), lv, colors=[c], linewidths=lw,
                            linestyles=["dashed" if t < 0 else "solid" for t in lv])
            if o.get("clabels", True):
                ax.clabel(cs, fmt="%g", fontsize=fs * 0.7)
        handles.append(Line2D([], [], color=c, lw=lw, label=lab))
    if np.isfinite(zlo):
        ax.set_xlim(0.0 if num("rmin") is None else num("rmin"),
                    rhi if num("rmax") is None else num("rmax"))
        ax.set_ylim(zlo if num("zmin") is None else num("zmin"),
                    zhi if num("zmax") is None else num("zmax"))
    ax.set_xlabel("Radius (km)")
    ax.set_ylabel("Height (km)")
    if o.get("legend", True) and (n > 1 or spec.get("_legend_extra")):
        panel_legend(ax, handles, o, spec, "best", False)
