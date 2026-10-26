"""Time-series and distribution panels."""

import numpy as np
from matplotlib.offsetbox import AnchoredOffsetbox, TextArea, VPacker
from matplotlib.patches import Patch, Rectangle

from .base import (SND_COLORS, by_run, font_size, panel_legend, run_color,
                   run_style, several_runs)

def _lines(ax, d, spec, fs):
    """Time-series panel: one line per (series, run).  Series in other units get
    their own y axis on the right.  One series (from one run of a figure with
    several_runs, or from several runs): colour = run's; several series: colour =
    series', line style = run's (with several_runs, or from several runs)."""
    ents = spec.get("series", [])
    n = int(d.get("nlines", 0))
    es = {int(d[f"S{j}_e"]) for j in range(n)}
    rs = {int(d[f"S{j}_r"]) for j in range(n)}
    multi = len(rs) > 1 or several_runs(spec)
    one_series = len(es) == 1 and multi  # (coloured by run)
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
        color = run_color(spec, k) if one_series else e.get("color", "k")
        ls = "-" if one_series or not multi else run_style(spec, k)
        t, v = d[f"S{j}_t"], d[f"S{j}_v"]
        ext = series_extremes(t, v, mark, ts)
        label = str(d[f"S{j}_label"])
        if ts.get("mark_legend") and ext:
            label = f"{label} ({'; '.join(f'{w} {y:.3g} at {x:g} min' for w, x, y in ext)})"
        h, = axes[key].plot(t, v, color=color, ls=ls,
                            lw=float(e.get("lw", 1.5)), marker=e.get("marker") or None,
                            ms=3, label=label)
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
    if ts.get("legend", True) and (len(handles) > 1 or (ts.get("mark_legend") and mark)):
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
    """Colour of each distribution of panel data d: its own, else its run's when each
    of the panel's distributions comes from another run (by_run), else the next of SND_COLORS."""
    ents = spec.get("dists", [])
    n = int(d.get("ndist", 0))
    es = [ents[int(d[f"D{j}_e"])] if int(d[f"D{j}_e"]) < len(ents) else {} for j in range(n)]
    runs = [int(e.get("run", 0)) for e in es]
    rc = by_run(spec, runs)
    return [e.get("color") or (run_color(spec, k) if rc else SND_COLORS[j % len(SND_COLORS)])
            for j, (e, k) in enumerate(zip(es, runs))]


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
        if o.get("legend", True) and (n > 1 or (keys and not in_box)):
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
