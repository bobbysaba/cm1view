"""Time-series and distribution panels."""

import numpy as np
from matplotlib.patches import Patch, Rectangle

from .base import SND_COLORS, font_size, run_color, run_style

def _lines(ax, d, spec, fs):
    """Time-series panel: one line per (series, run).  Series in other units get
    their own y axis on the right.  One series from several runs: colour = run's;
    several series: colour = series', line style = run's."""
    ents = spec.get("series", [])
    n = int(d.get("nlines", 0))
    es = {int(d[f"S{j}_e"]) for j in range(n)}
    rs = {int(d[f"S{j}_r"]) for j in range(n)}
    by_run = len(es) == 1 and len(rs) > 1
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
        color = run_color(spec, k) if by_run else e.get("color", "k")
        ls = "-" if by_run or len(rs) == 1 else run_style(spec, k)
        h, = axes[key].plot(d[f"S{j}_t"], d[f"S{j}_v"], color=color, ls=ls,
                            lw=float(e.get("lw", 1.5)), marker=e.get("marker") or None,
                            ms=3, label=str(d[f"S{j}_label"]))
        handles.append(h)
        items.setdefault(key, []).append((e, color))
    for key, its in items.items():
        a = axes[key]
        a.set_ylabel("; ".join(dict.fromkeys(e.get("ylabel") or e.get("units", "")
                                             for e, _ in its)))
        if len(axes) > 1 and len({c for _, c in its}) == 1:  # axis coloured like its line
            a.yaxis.label.set_color(its[0][1])
            a.tick_params(axis="y", colors=its[0][1])
    ts = spec.get("ts", {})
    lo, hi = ts.get("ymin"), ts.get("ymax")  # the left axis's range (blank: the data's)
    if lo not in (None, "") or hi not in (None, ""):
        ax.set_ylim(None if lo in (None, "") else float(lo), None if hi in (None, "") else float(hi))
    if ts.get("zero_line"):
        ax.axhline(0.0, color="0.6", lw=0.6, zorder=0)
    if ts.get("legend", True) and len(handles) > 1:
        ax.legend(handles=handles, loc=ts.get("legend_loc", "best"),
                  fontsize=font_size(spec, "legend"), frameon=False,
                  ncol=int(spec.get("legend", {}).get("ncol", 1) or 1))


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


def dist_colors(spec, d):
    """Colour of each distribution of panel data d: its own, else its run's when each
    of the panel's distributions comes from another run, else the next of SND_COLORS."""
    ents = spec.get("dists", [])
    n = int(d.get("ndist", 0))
    es = [ents[int(d[f"D{j}_e"])] if int(d[f"D{j}_e"]) < len(ents) else {} for j in range(n)]
    runs = [int(e.get("run", 0)) for e in es]
    by_run = n > 1 and len(set(runs)) == n
    return [e.get("color") or (run_color(spec, k) if by_run else SND_COLORS[j % len(SND_COLORS)])
            for j, (e, k) in enumerate(zip(es, runs))]


def _dists(ax, d, spec, fs):
    """Distribution panel: spec["dist"]["plot"] hist (in common bins), ecdf, box or
    violin (one per distribution, side by side)."""
    o = spec.get("dist", {})
    n = int(d.get("ndist", 0))
    sts = [dist_of(d, j) for j in range(n)]
    cols = dist_colors(spec, d)
    labels = [str(d.get(f"D{j}_label", "")) for j in range(n)]
    if o.get("stats"):
        labels = [f"{lab} (mean {s['mean']:.3g}, sd {s['std']:.3g}, n = {s['n']:,.0f})"
                  .lstrip() for lab, s in zip(labels, sts)]

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
            for st, c, lab in zip(sts, cols, labels):
                v = dist_hist(st, edges, norm)
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
        if o.get("zero_line"):
            ax.axvline(0.0, color="0.6", lw=0.6, zorder=0)
        ax.set_xlabel(vlab)
        ax.set_ylabel(ylab)
        if o.get("legend", True) and n > 1:
            ax.legend(handles=handles, loc=o.get("legend_loc", "best"),
                      fontsize=font_size(spec, "legend"), frameon=False,
                      ncol=int(spec.get("legend", {}).get("ncol", 1) or 1))
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
