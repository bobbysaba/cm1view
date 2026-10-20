"""Draw a figure from a spec (a dict) and the plotted arrays: plan views or vertical
cross-sections on a grid of panels.

Needs only numpy and matplotlib (pyart, if installed, for its colormaps).  cm1view
copies this file into every exported figure script, so the script redraws exactly
what the viewer showed; edit SPEC in the script (or this code) to change the figure.

data: {panel index: {name: array}} with, per panel,
  x, y          1D coordinates (km): plan x / y, or section distance / height
  L<j>          2D field of layer j (fill, contour, shade)
  L<j>_x, L<j>_y, L<j>_u, L<j>_v   vectors of layer j
  track_x, track_y, now_x, now_y   storm track (plan views)
  line          [xa, ya, xb, yb] cross-section line (plan views)
  time_s        model time (s)
  missing       reason the panel has no data (a string), if any
"""

import string

import numpy as np
import matplotlib
from matplotlib.figure import Figure
from matplotlib.colors import BoundaryNorm, ListedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnchoredText
from matplotlib.patches import Patch

# NWS-style reflectivity steps (every 5 dBZ from 5 dBZ)
NWS_REF = ["#04e9e7", "#019ff4", "#0300f4", "#02fd02", "#01c501", "#008e00", "#fdf802",
           "#e5bc00", "#fd9500", "#fd0000", "#d40000", "#bc0000", "#f800fd", "#9854c6",
           "#fdfdfd"]


def colormap(name, reverse=False, white_first=False):
    """A matplotlib colormap by name ('reflectivity' = NWS steps; pyart maps such as
    HomeyerRainbow / ChaseSpectral when pyart is installed).  white_first: the lowest
    of 20 steps is white (as for updraft speed)."""
    if name == "reflectivity":
        cm = ListedColormap(["#ffffff00"] + NWS_REF, name="reflectivity")
    else:
        try:
            cm = matplotlib.colormaps[name]
        except KeyError:
            import pyart  # noqa: F401  (registers its colormaps)
            cm = matplotlib.colormaps[name]
    if reverse:
        cm = cm.reversed()
    if white_first:
        cols = cm(np.linspace(0, 1, 19))
        cm = ListedColormap(np.vstack([[1, 1, 1, 1], cols]), name=cm.name + "_white")
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
    xsec = spec["kind"] == "xsec"
    ax_opts = spec.get("axes", {})
    labels = spec.get("letters", {})
    tlab = spec.get("time_label", {})
    titles = spec.get("titles", [])
    cbar = spec.get("colorbar", {})
    npan = min(rows * cols, len(spec["times"]) if spec.get("vary") == "time"
               else max(1, len(spec.get("panel_fills", []))))
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
            if "xlim" in d:
                ax.set_xlim(*d["xlim"])
                ax.set_ylim(*d["ylim"])
        if m is not None:
            mappables.append((ax, m))
        if not xsec and ax_opts.get("equal", True):
            ax.set_aspect("equal")
        ax.set_xlabel(ax_opts.get("xlabel", ""))
        ax.set_ylabel(ax_opts.get("ylabel", ""))
        if i < len(titles) and titles[i]:
            ax.set_title(titles[i], weight="bold" if ax_opts.get("title_bold", True)
                         else "normal")
        if labels.get("on", True):
            _anchored(ax, panel_letter(i, labels.get("fmt", "{a}")), labels, fs * 1.2)
        if tlab.get("on", True) and "time_s" in d:
            _anchored(ax, time_text(d["time_s"], tlab), tlab, fs * 1.2)
    _ticks(axs[:npan], used, ax_opts, rows, cols)
    if legend:
        lg = spec.get("legend", {})
        where = used[min(int(lg.get("panel", 0)), len(used) - 1)] if used else None
        if where is not None:
            where.legend(list(legend.values()), list(legend.keys()),
                         loc=lg.get("loc", "upper right"), fontsize=fs * 0.85,
                         frameon=lg.get("frame", True), framealpha=0.85)
    _colorbars(fig, cbar, mappables, used, spec)
    if spec.get("suptitle"):
        fig.suptitle(spec["suptitle"], weight="bold", fontsize=fs * 1.4)
    return fig


def spec_layers(spec, i):
    """Layers of panel i: the shared layers, with the per-panel fill of a 'field'
    figure replacing the first fill layer."""
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
        ax0, (m, lay) = mappables[0]
        c = fig.colorbar(m, ax=used, extend=lay.get("extend", "neither"), **kw)
        c.set_label(cb.get("label", "") or lay.get("units", ""))
        _cbar_ticks(c, cb)
        return
    for ax, (m, lay) in mappables:
        c = fig.colorbar(m, ax=ax, extend=lay.get("extend", "neither"), **kw)
        c.set_label(lay.get("cbar_label") or lay.get("units", ""))
        _cbar_ticks(c, cb)


def _cbar_ticks(c, cb):
    if cb.get("ticks"):
        c.set_ticks(_levels(cb["ticks"]))
