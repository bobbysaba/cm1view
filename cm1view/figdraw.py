"""Draw a figure from a spec (a dict) and the plotted arrays: plan views, vertical
cross-sections, time-height plots, time series or soundings on a grid of panels.

Needs only numpy and matplotlib (cmweather or pyart, if installed, for their colormaps).  cm1view
copies this file into every exported figure script, so the script redraws exactly
what the viewer showed; edit SPEC in the script (or this code) to change the figure.

data: {panel index: {name: array}} with, per panel,
  x, y          1D coordinates (km): plan x / y, or section distance / height
  L<j>          2D field of layer j (fill, contour, shade)
  L<j>_x, L<j>_y, L<j>_u, L<j>_v   vectors of layer j
  L<j>_gx, L<j>_gy, L<j>_gu, L<j>_gv   grid and winds of a streamline layer j
  track_x, track_y, now_x, now_y   storm track (plan views)
  line          [xa, ya, xb, yb] cross-section line (plan views)
  time_s        model time (s)
  run_label     name of the panel's run (figures with panels from several runs)
  missing       reason the panel has no data (a string), if any
time-height panels (kind "th"): x = time (min), y = height (km), L0 = values (z, t)
time-series panels (kind "line"): nlines, and per line n
  S<n>_t, S<n>_v   time (min) and values;  S<n>_e, S<n>_r  series entry and run index
  S<n>_label       legend text
sounding panels (kind "sounding"): nsnd, and per sounding n
  N<n>_p, N<n>_T, N<n>_Td, N<n>_Tp   pressure (hPa), T, dewpoint, lifted parcel (deg C)
  N<n>_u, N<n>_v, N<n>_z             winds (m/s) and height (km AGL)
  N<n>_e, N<n>_label                 sounding entry index and legend text
"""

import string

import numpy as np
import matplotlib
from matplotlib.figure import Figure
from matplotlib.colors import (BoundaryNorm, LinearSegmentedColormap, ListedColormap,
                               Normalize)
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnchoredText
from matplotlib.patches import Circle, Patch, Rectangle
from matplotlib.ticker import NullFormatter

# NWS-style reflectivity steps (every 5 dBZ from 5 dBZ)
NWS_REF = ["#04e9e7", "#019ff4", "#0300f4", "#02fd02", "#01c501", "#008e00", "#fdf802",
           "#e5bc00", "#fd9500", "#fd0000", "#d40000", "#bc0000", "#f800fd", "#9854c6",
           "#fdfdfd"]
RUN_COLORS = ["k", "#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e"]
RUN_STYLES = ["-", "--", ":", "-."]
FILL_KEYS = ("cmap", "reverse", "white_first", "vmin", "vmax", "nlevels", "style",
             "mask_below", "extend", "units", "cbar_label")
HODO_BANDS = [(0, 1, "#e11d48"), (1, 3, "#16a34a"), (3, 6, "#ca8a04"), (6, 9, "#0284c7"),
              (9, 12, "#7c3aed")]
KT = 1.943844


def colormap(name, reverse=False, white_first=False):
    """A matplotlib colormap by name ('reflectivity' = NWS steps; pyart maps such as
    HomeyerRainbow / ChaseSpectral when cmweather or pyart is installed).  white_first: starts from
    white (as for updraft speed)."""
    if name == "reflectivity":
        cm = ListedColormap(["#ffffff00"] + NWS_REF, name="reflectivity")
    else:
        try:
            cm = matplotlib.colormaps[name]
        except KeyError:
            try:  # either registers HomeyerRainbow, ChaseSpectral, ...
                import cmweather  # noqa: F401
            except ImportError:
                import pyart  # noqa: F401
            cm = matplotlib.colormaps[name]
    if reverse:
        cm = cm.reversed()
    if white_first:  # as funcs.w_cmap: white, then 19 colours of the map, blended
        cols = cm(np.linspace(0, 1, 19))
        cm = LinearSegmentedColormap.from_list(cm.name + "_white",
                                               np.vstack([[1, 1, 1, 1], cols]))
    return cm


def _norm(lay, cm):
    lo, hi = float(lay["vmin"]), float(lay["vmax"])
    n = int(lay.get("nlevels") or 0)
    if n > 1:
        return BoundaryNorm(np.linspace(lo, hi, n + 1), cm.N, extend=lay.get("extend",
                                                                             "neither"))
    return Normalize(lo, hi)


def _levels(text):
    """'10, 20' or '-5:5:1' (start:stop:step, inclusive) -> list of floats."""
    out = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if part.count(":") == 2:
            a, b, s = (float(v) for v in part.split(":"))
            out += list(np.arange(a, b + 0.5 * s, s))
        else:
            out.append(float(part))
    return sorted(set(out))


def _fill(ax, x, y, a, lay):
    a = np.array(a, dtype=float)
    if lay.get("mask_below") is not None and lay["mask_below"] != "":
        a[a <= float(lay["mask_below"])] = np.nan
    cm = colormap(lay["cmap"], lay.get("reverse", False), lay.get("white_first", False))
    if lay.get("style") == "contourf":
        n = int(lay.get("nlevels") or 20)
        lv = np.linspace(float(lay["vmin"]), float(lay["vmax"]), n + 1)
        return ax.contourf(x, y, a, lv, cmap=cm, extend=lay.get("extend", "neither"))
    # rasterized: a PDF / SVG keeps text and lines as vectors but the field as pixels
    return ax.pcolormesh(x, y, a, cmap=cm, norm=_norm(lay, cm), shading="nearest",
                         rasterized=True)


def _contour(ax, x, y, a, lay):
    lv = _levels(lay["levels"])
    if not lv or not np.isfinite(a).any():
        return None
    ls = ["dashed" if (v < 0 and lay.get("neg_dashed", True)) else "solid" for v in lv]
    cs = ax.contour(x, y, a, lv, colors=lay.get("color", "k"),
                    linewidths=float(lay.get("lw", 1.0)), linestyles=ls)
    if lay.get("clabel"):
        ax.clabel(cs, fmt="%g", fontsize=float(lay.get("clabel_size", 8)))
    return cs


def _shade(ax, x, y, a, lay):
    thr = float(lay["threshold"])
    lv = [thr, np.inf] if lay.get("above", True) else [-np.inf, thr]
    if not np.isfinite(a).any():
        return
    ax.contourf(x, y, a, lv, colors=[lay.get("color", "magenta")],
                alpha=float(lay.get("alpha", 0.6)))
    if lay.get("outline"):
        ax.contour(x, y, a, [thr], colors=lay["outline"],
                   linewidths=float(lay.get("lw", 1.0)))


def _vectors(ax, d, j, lay, xsec):
    if lay.get("style") == "streamlines":
        gx, gy, gu, gv = (d.get(f"L{j}_g{k}") for k in "xyuv")
        if gx is None or np.size(gx) < 2 or np.size(gy) < 2:
            return
        gx = np.linspace(gx[0], gx[-1], np.size(gx))  # exactly equal spacing
        gy = np.linspace(gy[0], gy[-1], np.size(gy))
        ax.streamplot(gx, gy, np.ma.masked_invalid(gu), np.ma.masked_invalid(gv),
                      density=float(lay.get("density", 1.5)), color=lay.get("color", "k"),
                      linewidth=float(lay.get("slw", 0.8)),
                      arrowsize=float(lay.get("arrowsize", 1.0)))
        return
    x, y, u, v = (d.get(f"L{j}_{k}") for k in "xyuv")
    if x is None or not np.size(x):
        return
    q = ax.quiver(x, y, u, v, color=lay.get("color", "k"), scale=float(lay.get("scale", 250)),
                  width=float(lay.get("width", 0.002)), angles="xy" if xsec else "uv",
                  scale_units=None, pivot="middle" if lay.get("pivot_mid") else "tail")
    ref = lay.get("key")
    if ref:
        ax.quiverkey(q, 0.88, 1.02, float(ref), f"{float(ref):g} m s$^{{-1}}$",
                     labelpos="E", coordinates="axes",
                     fontproperties={"size": max(6, 0.8 * matplotlib.rcParams["font.size"])})


def _anchored(ax, text, opts, size):
    ax.add_artist(AnchoredText(text, loc=opts.get("loc", "upper left"), frameon=False,
                               prop={"weight": "bold" if opts.get("bold", True) else "normal",
                                     "size": float(opts.get("size") or size)}))


def panel_letter(i, fmt):
    return (fmt.replace("{a}", string.ascii_lowercase[i % 26])
            .replace("{A}", string.ascii_uppercase[i % 26]))


def time_text(t_s, opts):
    mins = (float(t_s) - 60.0 * float(opts.get("t0_min", 0.0))) / 60.0
    s = int(round(float(t_s)))
    return opts.get("fmt", "t = {min:g} min").format(
        min=round(mins, 2), s=s, hms=f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}")


def draw(spec, data):
    """The matplotlib Figure of `spec` with arrays `data` (see the module notes)."""
    font = spec.get("font", {})
    fs = float(font.get("size", 10))
    rc = {"font.size": fs, "font.family": font.get("family", "sans-serif"),
          "axes.titlesize": fs * 1.1, "axes.labelsize": fs, "xtick.labelsize": fs * 0.9,
          "ytick.labelsize": fs * 0.9, "pdf.fonttype": 42, "ps.fonttype": 42,
          "svg.fonttype": "none"}
    with matplotlib.rc_context(rc):
        return _draw(spec, data, fs)


def _draw(spec, data, fs):
    rows, cols = int(spec["rows"]), int(spec["cols"])
    fig = Figure(figsize=tuple(spec["size"]), layout="constrained",
                 facecolor=spec.get("background", "white"))
    gap = spec.get("spacing", {})
    fig.get_layout_engine().set(w_pad=float(gap.get("w_pad", 0.04)),
                                h_pad=float(gap.get("h_pad", 0.04)),
                                wspace=float(gap.get("wspace", 0.02)),
                                hspace=float(gap.get("hspace", 0.02)))
    axs = np.atleast_1d(fig.subplots(rows, cols, squeeze=False)).ravel()
    kind = spec["kind"]
    xsec = kind == "xsec"
    ax_opts = spec.get("axes", {})
    labels = spec.get("letters", {})
    tlab = spec.get("time_label", {})
    titles = spec.get("titles", [])
    cbar = spec.get("colorbar", {})
    npan = npanels(spec)
    rlab = spec.get("run_label", {})
    mappables, used, legend = [], [], {}
    for i, ax in enumerate(axs):
        if i >= npan or i not in data:
            ax.set_visible(False)
            continue
        d = data[i]
        used.append(ax)
        layers = spec_layers(spec, i)
        m = None
        if d.get("missing"):
            ax.text(0.5, 0.5, str(d["missing"]), transform=ax.transAxes, ha="center",
                    va="center", color="0.4", fontsize=fs * 0.9, wrap=True)
        elif kind == "line":
            _lines(ax, d, spec, fs)
        elif kind == "sounding":
            _skewt(ax, d, spec, fs)
        else:
            x, y = d["x"], d["y"]
            for j, lay in enumerate(layers):
                if not lay.get("on", True):
                    continue
                t = lay["type"]
                a = d.get(f"L{j}")
                if t == "fill" and a is not None:
                    mm = _fill(ax, x, y, a, lay)
                    m = m or (mm, lay)
                elif t == "contour" and a is not None:
                    _contour(ax, x, y, a, lay)
                elif t == "shade" and a is not None:
                    _shade(ax, x, y, a, lay)
                elif t == "vectors":
                    _vectors(ax, d, j, lay, xsec)
                elif t == "track" and "track_x" in d:
                    ax.plot(d["track_x"], d["track_y"], color=lay.get("color", "k"),
                            lw=float(lay.get("lw", 1.0)), ls=lay.get("ls", "-"))
                    if lay.get("marker", True) and "now_x" in d:
                        ax.plot(d["now_x"], d["now_y"], marker="o", ms=4,
                                color=lay.get("color", "k"))
                elif t == "line" and "line" in d:
                    xa, ya, xb, yb = d["line"]
                    ax.plot([xa, xb], [ya, yb], color=lay.get("color", "k"),
                            lw=float(lay.get("lw", 2.0)))
                    la, lb = ([s.strip() for s in str(lay.get("labels", "")).split(",")]
                              + ["", ""])[:2]
                    yl = d.get("ylim", (np.nanmin(y), np.nanmax(y)))
                    off = 0.02 * (yl[1] - yl[0])  # labels just above the line ends
                    for (px, py, txt) in ((xa, ya, la), (xb, yb, lb)):
                        ax.text(px, py + off, txt, fontsize=fs * 1.1,
                                weight="bold", color=lay.get("color", "k"), ha="center",
                                va="bottom", clip_on=True)
                if lay.get("legend") and t in ("contour", "shade", "track", "line"):
                    legend[lay["legend"]] = (
                        Patch(facecolor=lay.get("color", "magenta"),
                              alpha=float(lay.get("alpha", 0.6)),
                              edgecolor=lay.get("outline") or "none")
                        if t == "shade" else
                        Line2D([], [], color=lay.get("color", "k"),
                               lw=float(lay.get("lw", 1.0))))
        if "xlim" in d and not d.get("missing") and kind != "sounding":
            ax.set_xlim(*d["xlim"])
            if "ylim" in d:
                ax.set_ylim(*d["ylim"])
        if m is not None:
            mappables.append((i, ax, m))
        if kind == "plan" and ax_opts.get("equal", True):
            ax.set_aspect("equal")
        ax.set_xlabel(ax_opts.get("xlabel", ""))
        if ax_opts.get("ylabel") or kind != "line":  # time series: units by default
            ax.set_ylabel(ax_opts.get("ylabel", ""))
        if i < len(titles) and titles[i]:
            ax.set_title(titles[i], weight="bold" if ax_opts.get("title_bold", True)
                         else "normal")
        if labels.get("on", True):
            _anchored(ax, panel_letter(i, labels.get("fmt", "{a}")), labels, fs * 1.2)
        if tlab.get("on", True) and "time_s" in d:
            _anchored(ax, time_text(d["time_s"], tlab), tlab, fs * 1.2)
        if rlab.get("on", True) and d.get("run_label"):
            _anchored(ax, str(d["run_label"]), rlab, fs * 1.2)
        _annotate(ax, i, spec.get("annotations", []), fs)
    _ticks(axs[:npan], used, ax_opts, rows, cols)
    if legend:
        lg = spec.get("legend", {})
        where = used[min(int(lg.get("panel", 0)), len(used) - 1)] if used else None
        if where is not None:
            where.legend(list(legend.values()), list(legend.keys()),
                         loc=lg.get("loc", "upper right"), fontsize=fs * 0.85,
                         frameon=lg.get("frame", True), framealpha=0.85)
    _colorbars(fig, cbar, mappables, used, spec)
    _contour_key(fig, spec, fs)
    if spec.get("suptitle"):
        fig.suptitle(spec["suptitle"], weight="bold", fontsize=fs * 1.4)
    return fig


def npanels(spec):
    """Number of panel slots (grid cells; empty ones are hidden)."""
    cells = int(spec["rows"]) * int(spec["cols"])
    kind, vary = spec.get("kind", "plan"), spec.get("vary", "time")
    if kind == "th":
        n = cells
    elif kind in ("line", "sounding"):
        ents = spec.get("series" if kind == "line" else "soundings", [])
        n = 1 + max([int(e.get("panel", 0)) for e in ents] or [0])
    elif vary == "time":
        n = len(spec.get("times_s", spec["times"]))
    elif vary == "field":
        n = max(1, len(spec.get("panel_fills", [])))
    elif vary == "grid":
        n = cells
    else:
        n = len(spec.get("panels", []))
    return min(n, cells)


def series_ref(spec, i):
    """(run index, series entry index) of time-height panel i, or None (an empty cell).
    runs_as "cols": a column per run and a row per series (else the other way)."""
    r, c = divmod(i, int(spec["cols"]))
    k, e = (c, r) if spec.get("runs_as", "cols") == "cols" else (r, c)
    if k < len(spec.get("runs") or [None]) and e < len(spec.get("series", [])):
        return k, e
    return None


def spec_layers(spec, i):
    """Layers of panel i: the shared layers, with the per-panel fill of a 'field'
    figure replacing the first fill layer (time-height panels: the fill of the
    panel's series)."""
    if spec.get("kind") == "th":
        ref = series_ref(spec, i)
        if ref is None:
            return []
        e = spec["series"][ref[1]]
        return [dict({k: e[k] for k in FILL_KEYS if k in e}, type="fill", on=True)]
    layers = [dict(lay) for lay in spec["layers"]]
    if spec.get("vary") == "field":
        pf = spec.get("panel_fills", [])
        if i < len(pf):
            for j, lay in enumerate(layers):
                if lay["type"] == "fill":
                    layers[j] = dict(lay, **pf[i])
                    break
    return layers


def _ticks(axs, used, opts, rows, cols):
    mode = opts.get("ticklabels", "all")  # all | outer | none
    lims = {(tuple(np.round(ax.get_xlim(), 6)), tuple(np.round(ax.get_ylim(), 6)))
            for ax in used}
    if mode == "outer" and len(lims) > 1:  # panels show different ranges: label all
        mode = "all"
    for i, ax in enumerate(axs):
        if ax not in used:
            continue
        r, c = divmod(i, cols)
        if mode == "none" or not opts.get("ticks", True):
            ax.tick_params(labelleft=False, labelbottom=False)
            ax.set_xlabel("")
            ax.set_ylabel("")
        elif mode == "outer":
            below = i + cols
            last_row = r == rows - 1 or below >= len(axs) or axs[below] not in used
            if not last_row:
                ax.tick_params(labelbottom=False)
                ax.set_xlabel("")
            if c > 0:
                ax.tick_params(labelleft=False)
                ax.set_ylabel("")
        if not opts.get("ticks", True):
            ax.tick_params(left=False, bottom=False)
        if opts.get("minor"):
            ax.minorticks_on()


def _colorbars(fig, cb, mappables, used, spec):
    mode = cb.get("mode", "shared")
    if mode == "none" or not mappables:
        return
    orient = cb.get("orientation", "horizontal" if mode == "shared" else "vertical")
    kw = dict(orientation=orient, shrink=float(cb.get("shrink", 0.8)),
              fraction=float(cb.get("fraction", 0.05)), pad=float(cb.get("pad", 0.02)))
    if mode == "shared":
        _, ax0, (m, lay) = mappables[0]
        c = fig.colorbar(m, ax=used, extend=lay.get("extend", "neither"), **kw)
        c.set_label(cb.get("label", "") or lay.get("units", ""))
        _cbar_ticks(c, cb)
        return
    if mode in ("row", "col"):  # one colorbar per row (column) of panels
        cols, groups = int(spec["cols"]), {}
        for i, ax, ml in mappables:
            r, c = divmod(i, cols)
            groups.setdefault(r if mode == "row" else c, []).append((ax, ml))
        for items in groups.values():
            m, lay = items[0][1]
            c = fig.colorbar(m, ax=[a for a, _ in items], extend=lay.get("extend", "neither"),
                             **kw)
            c.set_label(lay.get("cbar_label") or lay.get("units", ""))
            _cbar_ticks(c, cb)
        return
    for i, ax, (m, lay) in mappables:
        c = fig.colorbar(m, ax=ax, extend=lay.get("extend", "neither"), **kw)
        c.set_label(lay.get("cbar_label") or lay.get("units", ""))
        _cbar_ticks(c, cb)


def _cbar_ticks(c, cb):
    if cb.get("ticks"):
        c.set_ticks(_levels(cb["ticks"]))


# ------------------------------------------------------------------ time series
def _lines(ax, d, spec, fs):
    """Time-series panel: one line per (series, run).  Series in other units get
    their own y axis on the right.  One series from several runs: colour = run;
    several series: colour = series, line style = run."""
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
        color = RUN_COLORS[k % len(RUN_COLORS)] if by_run else e.get("color", "k")
        ls = "-" if by_run or len(rs) == 1 else RUN_STYLES[k % len(RUN_STYLES)]
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
    if ts.get("zero_line"):
        ax.axhline(0.0, color="0.6", lw=0.6, zorder=0)
    if ts.get("legend", True) and len(handles) > 1:
        ax.legend(handles=handles, loc=ts.get("legend_loc", "best"), fontsize=fs * 0.8,
                  frameon=False)


# ------------------------------------------------------------------ soundings
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


def _skewt(ax, d, spec, fs):
    """Skew-T log-p panel (plain axes: x = T + skew * ln(p_bottom / p)), with an
    optional hodograph inset and wind barbs."""
    o = spec.get("skewt", {})
    ents = spec.get("soundings", [])
    pb, pt = float(o.get("pmax", 1000.0)), float(o.get("pmin", 100.0))
    skew = float(o.get("skew", 35.0))

    def X(T, p):
        return np.asarray(T) + skew * np.log(pb / np.asarray(p))

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
        e = ents[int(d[f"N{j}_e"])] if int(d[f"N{j}_e"]) < len(ents) else {}
        p, T, Td = d[f"N{j}_p"], d[f"N{j}_T"], d[f"N{j}_Td"]
        col = e.get("color", RUN_COLORS[j % len(RUN_COLORS)])
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
    if o.get("barbs", True) and n:
        x0, x1 = ax.get_xlim()
        for j in range(n if many else 1):
            p, u, v = d[f"N{j}_p"], d[f"N{j}_u"], d[f"N{j}_v"]
            sel, last = [], None
            for k in range(len(p)):  # every ~25 hPa
                if pt <= p[k] <= pb and (last is None or last - p[k] >= 25.0):
                    sel.append(k)
                    last = p[k]
            xb = x1 - (0.05 + 0.07 * j) * (x1 - x0)
            col = ents[int(d[f"N{j}_e"])].get("color", "k") if many else "k"
            # barbs are drawn in data x, which is skewed: put them on a vertical line
            ax.barbs(np.full(len(sel), xb), p[sel], u[sel] * KT, v[sel] * KT, length=5,
                     lw=0.6, color=col, clip_on=False)
    if o.get("hodo", True) and n:
        _hodo(ax, d, n, many, ents, o, fs)
    if many or o.get("legend", False):
        ax.legend(handles=handles, loc=o.get("legend_loc", "upper left"), fontsize=fs * 0.75,
                  frameon=True, framealpha=0.85)


def _hodo(ax, d, n, many, ents, o, fs):
    hx = ax.inset_axes([float(v) for v in o.get("hodo_rect", [0.6, 0.6, 0.39, 0.39])])
    hm = float(o.get("hodo_max", 40.0))
    top = float(o.get("hodo_top", 9.0))
    hx.set_facecolor((1, 1, 1, 0.9))
    for r in np.arange(10.0, hm + 0.1, 10.0):
        hx.add_patch(Circle((0, 0), r, fill=False, ec="0.8", lw=0.5))
        hx.text(r * 0.707, -r * 0.707, f"{r:g}", fontsize=fs * 0.55, color="0.5",
                ha="left", va="top")
    hx.axhline(0, color="0.7", lw=0.5)
    hx.axvline(0, color="0.7", lw=0.5)
    for j in range(n):
        u, v, z = d[f"N{j}_u"], d[f"N{j}_v"], d[f"N{j}_z"]
        if many:
            col = ents[int(d[f"N{j}_e"])].get("color", "k")
            sel = z <= top
            hx.plot(u[sel], v[sel], color=col, lw=1.4)
            continue
        for z0, z1, col in HODO_BANDS:
            if z0 >= top:
                break
            sel = (z >= z0) & (z <= min(z1, top))
            hx.plot(u[sel], v[sel], color=col, lw=1.6)
    hx.set_xlim(-hm, hm)
    hx.set_ylim(-hm, hm)
    hx.set_aspect("equal")
    hx.set_xticks([])
    hx.set_yticks([])
    hx.text(0.03, 0.97, "m s$^{-1}$", transform=hx.transAxes, fontsize=fs * 0.6, va="top",
            color="0.4")


# ------------------------------------------------------------------ annotations
def _annotate(ax, i, anns, fs):
    """Text, markers, arrows, lines, boxes and circles in panel i (panel -1: every
    panel), in data coordinates or as fractions of the panel (coords 'axes')."""
    for a in anns:
        if int(a.get("panel", -1)) not in (-1, i):
            continue
        tr = ax.transAxes if a.get("coords") == "axes" else ax.transData
        kind = a.get("kind", "text")
        col, lw = a.get("color", "k"), float(a.get("lw", 1.5))
        size = float(a.get("size") or fs)
        x, y = float(a.get("x", 0.0)), float(a.get("y", 0.0))
        x2, y2 = float(a.get("x2", x)), float(a.get("y2", y))
        txt = str(a.get("text", ""))
        wt = "bold" if a.get("bold") else "normal"
        if kind == "text":
            ax.text(x, y, txt, transform=tr, color=col, fontsize=size, weight=wt,
                    ha="center", va="center", clip_on=True)
        elif kind == "marker":
            ax.plot([x], [y], transform=tr, ls="none", marker=a.get("marker", "x"), ms=size,
                    mew=lw, color=col, mfc="none" if a.get("marker") in ("o", "s") else col)
            if txt:
                ax.annotate(txt, (x, y), xycoords=tr, xytext=(0.6 * size, 0.6 * size),
                            textcoords="offset points", color=col, fontsize=fs, weight=wt)
        elif kind == "arrow":  # from (x, y) (the text) to (x2, y2)
            ax.annotate(txt, xy=(x2, y2), xycoords=tr, xytext=(x, y), textcoords=tr,
                        color=col, fontsize=size, weight=wt, ha="center", va="center",
                        arrowprops=dict(arrowstyle="-|>", color=col, lw=lw,
                                        shrinkA=2, shrinkB=0))
        elif kind == "line":
            ax.plot([x, x2], [y, y2], transform=tr, color=col, lw=lw,
                    ls=a.get("ls", "-"))
        elif kind in ("vline", "hline"):
            (ax.axvline if kind == "vline" else ax.axhline)(
                x if kind == "vline" else y, color=col, lw=lw, ls=a.get("ls", "--"))
            if txt:
                ax.text(x if kind == "vline" else 0.01, 0.98 if kind == "vline" else y,
                        txt, transform=(ax.get_xaxis_transform() if kind == "vline"
                                        else ax.get_yaxis_transform()),
                        color=col, fontsize=fs * 0.85, weight=wt,
                        ha="left", va="top" if kind == "vline" else "bottom")
        elif kind == "box":
            ax.add_patch(Rectangle((min(x, x2), min(y, y2)), abs(x2 - x), abs(y2 - y),
                                   transform=tr, fill=False, ec=col, lw=lw,
                                   ls=a.get("ls", "-")))
        elif kind == "circle":  # centre (x, y), radius r
            ax.add_patch(Circle((x, y), float(a.get("r", 1.0)), transform=tr, fill=False,
                                ec=col, lw=lw, ls=a.get("ls", "-")))


def _contour_key(fig, spec, fs):
    """Nested circles labelled with a contour layer's levels and the field's name in
    the middle (a key for unlabelled contours, e.g. updraft speed)."""
    ck = spec.get("contour_key", {})
    if not ck.get("on"):
        return
    layers = spec.get("layers", [])
    k = int(ck.get("layer", -1))
    lay = layers[k] if 0 <= k < len(layers) and layers[k]["type"] == "contour" else next(
        (l for l in layers if l["type"] == "contour" and l.get("on", True)), None)
    if lay is None:
        return
    labels = [f"{v:g}" for v in _levels(lay["levels"])]
    if not labels:
        return
    size = float(ck.get("size", 0.1))
    kx = fig.add_axes([float(ck.get("x", 0.01)), float(ck.get("y", 0.01)), size, size],
                      aspect=1)
    kx.axis("off")
    if ck.get("frame", True):
        kx.add_patch(Rectangle((0, 0), 1, 1, transform=kx.transAxes, fc="white", ec="black",
                               lw=2, zorder=0))
    r0, step = float(ck.get("r0", 0.35)), float(ck.get("step", 0.15))
    c, yoff = 0.5, float(ck.get("yoffset", 0.06))
    kfs = float(ck.get("fs", fs))
    for n, lab in enumerate(labels):
        kx.add_patch(Circle((c, c - n * step - yoff), radius=max(r0 - n * step, 0.01),
                            ec=lay.get("color", "k"), fc="none", lw=1.5))
        kx.text(c, (c - n * step) + (r0 - n * step), lab, ha="center", va="center",
                fontsize=kfs)
    kx.text(c, c - (len(labels) - 1) * step - yoff, str(ck.get("label", "")), ha="center",
            va="center", fontsize=kfs)
