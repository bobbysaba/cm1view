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
  run           index of the panel's run in spec["runs"] (its colour: tracks, run names)
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
  N<n>_rm, N<n>_lm, N<n>_mean        Bunkers right / left mover and 0-6 km mean wind
                                     (u, v m/s), N<n>_storm the storm motion of the SRH
                                     (spec["skewt"]["storm"]: rm, lm, mean or custom)
  N<n>_srh1, N<n>_srh3               0-1 and 0-3 km storm-relative helicity (m2/s2)
  N<n>_par                           the SND_PARAMS values (spec["skewt"]["table"]: a
                                     table of the chosen ones under the panel)
  spec["skewt"]["layout"]: "inset" (skew-T with a hodograph inset), "side" (skew-T and
  hodograph side by side), "skewt" (no hodograph) or "hodo" (the hodograph alone)
figures of parts (kind "combo"): part k's panel i under k * 1000 + i
"""

import string

import numpy as np
import matplotlib
from matplotlib.figure import Figure
from matplotlib.colors import (BoundaryNorm, LinearSegmentedColormap, ListedColormap,
                               LogNorm, Normalize)
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnchoredText
from matplotlib.patches import Circle, Patch, Rectangle
from matplotlib.ticker import MultipleLocator, NullFormatter

# NWS-style reflectivity steps (every 5 dBZ from 5 dBZ)
NWS_REF = ["#04e9e7", "#019ff4", "#0300f4", "#02fd02", "#01c501", "#008e00", "#fdf802",
           "#e5bc00", "#fd9500", "#fd0000", "#d40000", "#bc0000", "#f800fd", "#9854c6",
           "#fdfdfd"]
RUN_COLORS = ["k", "#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e"]
RUN_STYLES = ["-", "--", ":", "-."]
SND_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "k"]
STORM_NAMES = {"rm": "RM", "lm": "LM", "mean": "mean wind", "custom": "custom"}
FILL_KEYS = ("cmap", "reverse", "white_first", "vmin", "vmax", "nlevels", "style",
             "mask_below", "extend", "units", "cbar_label")
SND_PARAMS = [  # (key, column heading, units) of the sounding parameter table
    ("sbcape", "SBCAPE", "J kg$^{-1}$"), ("mlcape", "MLCAPE", "J kg$^{-1}$"),
    ("mucape", "MUCAPE", "J kg$^{-1}$"), ("mlcin", "MLCIN", "J kg$^{-1}$"),
    ("mllcl", "MLLCL", "m"), ("srh1", "0–1 km SRH", "m$^2$ s$^{-2}$"),
    ("srh3", "0–3 km SRH", "m$^2$ s$^{-2}$"), ("esrh", "ESRH", "m$^2$ s$^{-2}$"),
    ("shear06", "0–6 km shear", "m s$^{-1}$"), ("stp_eff", "STP", ""), ("scp", "SCP", "")]
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
    if white_first:  # white, then 19 colours of the map, blended
        cols = cm(np.linspace(0, 1, 19))
        cm = LinearSegmentedColormap.from_list(cm.name + "_white",
                                               np.vstack([[1, 1, 1, 1], cols]))
    return cm


def _bounds(lay):
    """(min, max) of a fill; a log scale needs min > 0 (else max / 1000)."""
    lo, hi = float(lay["vmin"]), float(lay["vmax"])
    if lay.get("scale") == "log":
        hi = hi if hi > 0 else 1.0
        lo = lo if 0 < lo < hi else hi * 1e-3
    return lo, hi


def _steps(lay, n):
    lo, hi = _bounds(lay)
    return np.geomspace(lo, hi, n + 1) if lay.get("scale") == "log" else \
        np.linspace(lo, hi, n + 1)


def _norm(lay, cm):
    lo, hi = _bounds(lay)
    n = int(lay.get("nlevels") or 0)
    if n > 1:
        return BoundaryNorm(_steps(lay, n), cm.N, extend=lay.get("extend", "neither"))
    return LogNorm(lo, hi) if lay.get("scale") == "log" else Normalize(lo, hi)


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


def _levels_list(text):
    """'1, 3, 6' or '1:9:2' -> floats in the order given (heights of the panels)."""
    out = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part.count(":") == 2:
            a, b, s = (float(v) for v in part.split(":"))
            out += [float(v) for v in np.arange(a, b + 0.5 * s, s)]
        elif part:
            out.append(float(part))
    return out


def _fill(ax, x, y, a, lay):
    a = np.array(a, dtype=float)
    if lay.get("mask_below") is not None and lay["mask_below"] != "":
        a[a <= float(lay["mask_below"])] = np.nan
    cm = colormap(lay["cmap"], lay.get("reverse", False), lay.get("white_first", False))
    alpha = float(lay.get("alpha", 1.0))
    alpha = alpha if alpha < 1.0 else None  # (opaque: matplotlib's plain path)
    if lay.get("style") == "contourf":
        n = int(lay.get("nlevels") or 20)
        lv = _steps(lay, n)
        return ax.contourf(x, y, a, lv, cmap=cm, extend=lay.get("extend", "neither"),
                           norm=LogNorm(lv[0], lv[-1]) if lay.get("scale") == "log" else None,
                           alpha=alpha)
    # rasterized: a PDF / SVG keeps text and lines as vectors but the field as pixels
    return ax.pcolormesh(x, y, a, cmap=cm, norm=_norm(lay, cm), shading="nearest",
                         rasterized=True, alpha=alpha)


def _contour(ax, x, y, a, lay):
    lv = _levels(lay["levels"])
    if not lv or not np.isfinite(a).any():
        return None
    ls = ["dashed" if (v < 0 and lay.get("neg_dashed", True)) else "solid" for v in lv]
    cs = ax.contour(x, y, a, lv, colors=lay.get("color", "k"),
                    linewidths=float(lay.get("lw", 1.0)), linestyles=ls)
    if lay.get("clabel"):
        ax.clabel(cs, fmt=lay.get("clabel_fmt") or "%g",
                  fontsize=float(lay.get("clabel_size") or 8))
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


def _anchored(ax, text, opts, size, color=None):
    """A panel label in a corner of the panel (on a white box with opts["box"]), or
    above it (loc "above left" / "above right")."""
    loc = opts.get("loc", "upper left")
    prop = {"weight": "bold" if opts.get("bold", True) else "normal",
            "size": float(opts.get("size") or size)}
    if color is not None:
        prop["color"] = color
    if loc.startswith("above"):
        ax.set_title(text, loc=loc.split()[-1], fontsize=prop["size"], fontweight=prop["weight"],
                     color=color)
        return
    box = bool(opts.get("box"))
    at = AnchoredText(text, loc=loc, frameon=box, prop=prop, pad=0.25 if box else 0.4,
                      borderpad=0.5)
    if box:
        at.patch.set(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none",
                     alpha=0.85)
    at.set_in_layout(False)  # it sits in the panel: small panels must not shrink for it
    ax.add_artist(at)


def panel_letter(i, fmt):
    return (fmt.replace("{a}", string.ascii_lowercase[i % 26])
            .replace("{A}", string.ascii_uppercase[i % 26]))


def time_text(t_s, opts):
    mins = (float(t_s) - 60.0 * float(opts.get("t0_min", 0.0))) / 60.0
    s = int(round(float(t_s)))
    return opts.get("fmt", "t = {min:g} min").format(
        min=round(mins, 2), s=s, hms=f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}")


def z_text(spec, i):
    """The height label of panel i of a figure of panels at heights (spec["z_label"];
    {z}: the height in km, {k}: the model level), or "" for none."""
    zs = spec.get("panel_z") or []
    if spec.get("vary") != "height" or i >= len(zs) or zs[i] is None:
        return ""
    level = spec.get("panel_zmode", "height") == "level"
    fmt = spec.get("z_label", {}).get("fmt") or ("k = {k}" if level else "z = {z:g} km")
    return fmt.format(z=float(zs[i]), k=int(round(float(zs[i]))))


def draw(spec, data):
    """The matplotlib Figure of `spec` with arrays `data` (see the module notes).  Save
    it with save(), which keeps the spec's fonts for what matplotlib draws late (tick
    labels)."""
    if spec.get("kind") == "combo":
        return _draw_combo(spec, data)
    with matplotlib.rc_context(rc(spec)):
        return _draw(spec, data, float(spec.get("font", {}).get("size", 10)))


def _draw_combo(spec, data):
    """A figure of parts (spec["parts"]: figure specs of their own, e.g. plan views
    beside soundings), side by side (arrange "row") or stacked ("col"), each as large
    as its share says (part_shares); data of part k's panel i under k * 1000 + i.  The
    panel letters run on from part to part.  spec["colorbar"]["mode"] "figure": one
    colorbar for the whole figure (of the first fill), instead of the parts' own."""
    parts = spec["parts"]
    row = spec.get("arrange", "row") == "row"
    W, H = (float(v) for v in spec["size"])
    fig = Figure(figsize=(W, H), layout="constrained",
                 facecolor=spec.get("background", "white"))
    gap = spec.get("spacing", {})
    fig.get_layout_engine().set(w_pad=float(gap.get("w_pad", 0.04)),
                                h_pad=float(gap.get("h_pad", 0.04)),
                                wspace=float(gap.get("wspace", 0.02)),
                                hspace=float(gap.get("hspace", 0.02)))
    cb = spec.get("colorbar") or {}
    one_cb = cb.get("mode") == "figure"
    host, bar = fig, None
    if one_cb:  # a strip along one side for the colorbar, the parts in the rest
        loc = cb.get("location") or "bottom"
        side = loc in ("left", "right")
        th = float(cb.get("strip", 1.0 if side else 0.7))  # (in: the bar and its labels)
        size = (W if side else H) - th
        rat = [max(size, 0.5), th] if loc in ("right", "bottom") else [th, max(size, 0.5)]
        subs = fig.subfigures(1, 2, width_ratios=rat) if side else \
            fig.subfigures(2, 1, height_ratios=rat)
        host, bar = (subs[0], subs[1]) if loc in ("right", "bottom") else (subs[1], subs[0])
        host.set_facecolor("none")
        bar.set_facecolor("none")
    ratios = part_shares(spec)
    subs = np.atleast_1d(host.subfigures(1, len(parts), width_ratios=ratios) if row else
                         host.subfigures(len(parts), 1, height_ratios=ratios)).ravel()
    start, fig._cv_axes, mappables = 0, {}, []
    for k, (part, sf) in enumerate(zip(parts, subs)):
        pd = {int(i) % 1000: v for i, v in data.items() if int(i) // 1000 == k}
        part = dict(part, letters=dict(part.get("letters", {}), start=start))
        if one_cb:
            part["colorbar"] = dict(part.get("colorbar", {}), mode="none")
        sf.set_facecolor("none")
        with matplotlib.rc_context(rc(part)):
            _draw(part, pd, float(part.get("font", {}).get("size", 10)), fig=sf)
        fig._cv_axes.update({k * 1000 + i: a for i, a in getattr(sf, "_cv_axes", {}).items()})
        mappables += getattr(sf, "_cv_mappables", [])
        err = getattr(sf, "_cv_code_error", None)
        if err:
            fig._cv_code_error = f"part {k + 1}, {err}"
        start += npanels(part)
    if one_cb and mappables:
        m, lay = mappables[0][2]
        s = min(max(float(cb.get("shrink", 0.7)), 0.05), 1.0)
        third = [0.5 * (1.0 - s), s, 0.5 * (1.0 - s)]
        gs = bar.add_gridspec(3, 1, height_ratios=third) if side else \
            bar.add_gridspec(1, 3, width_ratios=third)
        cax = bar.add_subplot(gs[1])
        c = bar.colorbar(m, cax=cax, orientation="vertical" if side else "horizontal",
                         extend=lay.get("extend", "neither"))
        if loc in ("left", "top"):
            (c.ax.yaxis if side else c.ax.xaxis).set_ticks_position(loc)
            (c.ax.yaxis if side else c.ax.xaxis).set_label_position(loc)
        with matplotlib.rc_context(rc(parts[0])):
            _cbar_style(c, cb, lay, loc)
    if spec.get("suptitle"):
        fig.suptitle(spec["suptitle"], weight="bold", fontsize=font_size(spec, "suptitle"))
    return fig


def part_shares(spec):
    """Each part's share of a figure of parts (of its width side by side, of its height
    stacked): a part's own "share" (0-1), and the rest split among the others by
    their sizes."""
    parts = spec["parts"]
    k = 0 if spec.get("arrange", "row") == "row" else 1
    own = [float(p["share"]) if p.get("share") else None for p in parts]
    size = [float(p["size"][k]) for p in parts]
    free = sum(sz for s, sz in zip(own, size) if s is None)
    rest = max(0.0, 1.0 - sum(s for s in own if s is not None))
    return [max(0.02, s if s is not None else (rest * sz / free if free else 0.0))
            for s, sz in zip(own, size)]


def save(spec, fig, fname, **kw):
    """fig.savefig(fname, **kw) with the spec's fonts and ticks in effect."""
    with matplotlib.rc_context(rc(spec)):
        fig.savefig(fname, **kw)


def rc(spec):
    """matplotlib settings of the spec's fonts and axes."""
    font, ax = spec.get("font", {}), spec.get("axes", {})
    fs = float(font.get("size", 10))
    fam = font.get("family", "sans-serif")
    rc = {"font.size": fs, "font.family": fam,
          "axes.titlesize": font_size(spec, "title"), "axes.labelsize": font_size(spec, "label"),
          "xtick.labelsize": font_size(spec, "tick"), "ytick.labelsize": font_size(spec, "tick"),
          "xtick.direction": ax.get("tickdir", "out"), "ytick.direction": ax.get("tickdir", "out"),
          "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none"}
    math = font.get("math", "dejavusans")
    rc["mathtext.fontset"] = math
    if math == "custom":  # math in the text font
        base = {"sans-serif": "sans", "serif": "serif"}.get(fam, fam)
        rc.update({"mathtext.rm": base, "mathtext.it": f"{base}:italic",
                   "mathtext.bf": f"{base}:bold"})
    if ax.get("frame_lw"):
        lw = float(ax["frame_lw"])
        rc.update({"axes.linewidth": lw, "xtick.major.width": lw, "ytick.major.width": lw,
                   "xtick.minor.width": 0.6 * lw, "ytick.minor.width": 0.6 * lw})
    return rc


def font_size(spec, what):
    """Font size (pt) of 'tick' labels, axis 'label's, panel 'title's, the 'suptitle'
    or the 'legend': the spec's own, else a multiple of the base size."""
    font = spec.get("font", {})
    v = font.get(what)
    if v not in (None, "", 0):
        return float(v)
    return float(font.get("size", 10)) * {"tick": 0.9, "label": 1.0, "title": 1.1,
                                          "suptitle": 1.4, "legend": 0.85}[what]


def _draw(spec, data, fs, fig=None):
    """Draw the panels into fig (a new Figure, or a part of one: a SubFigure)."""
    rows, cols = int(spec["rows"]), int(spec["cols"])
    gap = spec.get("spacing", {})
    if fig is None:
        fig = Figure(figsize=tuple(spec["size"]), layout="constrained",
                     facecolor=spec.get("background", "white"))
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
        elif kind == "sounding":  # (a layout or table may replace the panel's axes)
            ax = axs[i] = used[-1] = _sounding(fig, ax, d, spec, fs)
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
                    col = layer_color(spec, lay, d)
                    ax.plot(d["track_x"], d["track_y"], color=col,
                            lw=float(lay.get("lw", 1.0)), ls=lay.get("ls", "-"))
                    if lay.get("marker", True) and "now_x" in d:
                        ax.plot(d["now_x"], d["now_y"], marker="o", ms=4, color=col)
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
                        Line2D([], [], color=layer_color(spec, lay, d),
                               lw=float(lay.get("lw", 1.0))))
        if "xlim" in d and not d.get("missing") and kind != "sounding":
            ax.set_xlim(*d["xlim"])
            if "ylim" in d:
                ax.set_ylim(*d["ylim"])
        if m is not None:
            mappables.append((i, ax, m))
        if kind == "plan" and ax_opts.get("equal", True):
            ax.set_aspect("equal")
        if not getattr(ax, "_cv_hodo", False):  # (a hodograph panel labels its rings)
            ax.set_xlabel(ax_opts.get("xlabel", ""))
            if ax_opts.get("ylabel") or kind != "line":  # time series: units by default
                ax.set_ylabel(ax_opts.get("ylabel", ""))
        if i < len(titles) and titles[i]:
            ax.set_title(titles[i], weight="bold" if ax_opts.get("title_bold", True)
                         else "normal", loc=ax_opts.get("title_loc", "center"))
        if labels.get("on", True):
            k = i + int(labels.get("start", 0))  # (parts of a figure: letters run on)
            _anchored(ax, panel_letter(k, labels.get("fmt", "{a}")), labels, fs * 1.2)
        if tlab.get("on", True) and "time_s" in d:
            _anchored(ax, time_text(d["time_s"], tlab), tlab, fs * 1.2)
        zlab = spec.get("z_label", {})
        if zlab.get("on") and z_text(spec, i):
            _anchored(ax, z_text(spec, i), zlab, fs * 1.2)
        if rlab.get("on", True) and d.get("run_label"):
            _anchored(ax, str(d["run_label"]), rlab, fs * 1.2,
                      run_color(spec, int(d.get("run", 0))) if rlab.get("run_color") else None)
        _annotate(ax, i, spec.get("annotations", []), fs)
    _ticks(axs[:npan], used, ax_opts, rows, cols, kind)
    if legend:
        lg = spec.get("legend", {})
        where = used[min(int(lg.get("panel", 0)), len(used) - 1)] if used else None
        if where is not None:
            where.legend(list(legend.values()), list(legend.keys()),
                         loc=lg.get("loc", "upper right"), fontsize=font_size(spec, "legend"),
                         ncol=int(lg.get("ncol", 1) or 1),
                         frameon=lg.get("frame", True), framealpha=0.85)
    fig._cv_mappables = mappables  # (a figure of parts may draw one colorbar for all)
    _colorbars(fig, cbar, mappables, used, spec)
    _contour_key(fig, spec, fs)
    fig._cv_axes = {i: ax for i, ax in enumerate(axs) if ax in used}  # (panel -> axes)
    if spec.get("suptitle"):
        fig.suptitle(spec["suptitle"], weight="bold", fontsize=font_size(spec, "suptitle"))
    code = spec.get("code") or {}
    if code.get("on") and str(code.get("text") or "").strip():
        run_code(fig, axs, data, spec, code["text"])
    return fig


def run_code(fig, axs, data, spec, text):
    """The figure's own code (spec["code"]["text"]), run after everything else is drawn
    with fig, axs (the panels' axes, by panel number), data, spec, np and matplotlib.
    An error leaves the figure as drawn so far, with fig._cv_code_error saying why."""
    env = dict(fig=fig, axs=list(axs), data=data, spec=spec, np=np, matplotlib=matplotlib)
    try:
        exec(compile(str(text), "<figure code>", "exec"), env)  # noqa: S102 (the user's code)
    except Exception as e:  # noqa: BLE001
        import traceback
        line = [f.lineno for f in traceback.extract_tb(e.__traceback__)
                if f.filename == "<figure code>"] or [getattr(e, "lineno", None)]
        fig._cv_code_error = (f"line {line[-1]}: " if line[-1] else "") + \
            f"{type(e).__name__}: {e}"


def npanels(spec):
    """Number of panel slots (grid cells; empty ones are hidden)."""
    if spec.get("kind") == "combo":
        return sum(npanels(p) for p in spec["parts"])
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
    elif vary == "height":
        n = max(1, len(spec.get("panel_z") or []))
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
    figure replacing the first fill layer, and in a 'height' figure the panel's height
    (spec["panel_z"], km) for the layers at a height (but those with "z_fixed"), or
    with spec["panel_zmode"] "level" the panel's model level for the layers at a
    height or level (time-height panels: the fill of the panel's series).  A layer
    with a "panels" list is off in the other panels (so layer j stays layer j
    everywhere)."""
    if spec.get("kind") == "th":
        ref = series_ref(spec, i)
        if ref is None:
            return []
        e = spec["series"][ref[1]]
        return [dict({k: e[k] for k in FILL_KEYS if k in e}, type="fill", on=True)]
    layers = [dict(lay) if not lay.get("panels") or i in lay["panels"] else
              dict(lay, on=False) for lay in spec["layers"]]
    if spec.get("vary") == "height":
        zs = spec.get("panel_z") or []
        level = spec.get("panel_zmode", "height") == "level"
        if i < len(zs) and zs[i] is not None:
            for j, lay in enumerate(layers):
                if lay.get("z_fixed") or "z" not in lay:
                    continue
                mode = lay.get("mode", "height")
                if level and (lay["type"] == "vectors" or mode in ("height", "level")):
                    layers[j] = dict(lay, mode="level", z=float(round(float(zs[i]))))
                elif not level and (lay["type"] == "vectors" or mode == "height"):
                    layers[j] = dict(lay, z=float(zs[i]))
    if spec.get("vary") == "field":
        pf = spec.get("panel_fills", [])
        if i < len(pf):
            for j, lay in enumerate(layers):
                if lay["type"] == "fill":
                    layers[j] = dict(lay, **pf[i])
                    break
    return layers


def _ticks(axs, used, opts, rows, cols, kind="plan"):
    mode = opts.get("ticklabels", "all")  # all | outer | none
    lims = {(tuple(np.round(ax.get_xlim(), 6)), tuple(np.round(ax.get_ylim(), 6)))
            for ax in used}
    if mode == "outer" and len(lims) > 1:  # panels show different ranges: label all
        mode = "all"
    for i, ax in enumerate(axs):
        if ax not in used:
            continue
        hodo = getattr(ax, "_cv_hodo", False)  # (a hodograph keeps its own look)
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
        if hodo:
            continue
        if opts.get("minor"):
            ax.minorticks_on()
        for step, axis, ok in ((opts.get("xstep"), ax.xaxis, True),
                               (opts.get("ystep"), ax.yaxis, kind != "sounding")):
            if ok and step not in (None, "") and float(step) > 0:
                axis.set_major_locator(MultipleLocator(float(step)))
        if opts.get("grid"):
            ax.grid(True, color=opts.get("grid_color", "0.5"), lw=0.5,
                    ls=opts.get("grid_ls", ":"), alpha=0.8)


def _colorbars(fig, cb, mappables, used, spec):
    mode = cb.get("mode", "shared")
    if mode == "none" or not mappables:
        return
    orient = cb.get("orientation", "horizontal" if mode == "shared" else "vertical")
    loc = cb.get("location") or ("bottom" if orient == "horizontal" else "right")
    kw = dict(location=loc, shrink=float(cb.get("shrink", 0.8)),
              fraction=float(cb.get("fraction", 0.05)), pad=float(cb.get("pad", 0.02)))
    if mode == "shared":
        groups = [(used, mappables[0][2])]
    elif mode in ("row", "col"):  # one colorbar per row (column) of panels
        cols, by = int(spec["cols"]), {}
        for i, ax, ml in mappables:
            r, c = divmod(i, cols)
            by.setdefault(r if mode == "row" else c, []).append((ax, ml))
        groups = [([a for a, _ in items], items[0][1]) for items in by.values()]
    else:
        groups = [(ax, ml) for _, ax, ml in mappables]
    for axes, (m, lay) in groups:
        c = fig.colorbar(m, ax=axes, extend=lay.get("extend", "neither"), **kw)
        _cbar_style(c, cb, lay, loc)


def _cbar_style(c, cb, lay, loc):
    """Label (the colorbar's own, else the layer's, else its units), ticks and fonts."""
    c.set_label(cb.get("label") or lay.get("cbar_label") or lay.get("units", ""),
                size=float(cb.get("label_size") or 0) or None,
                weight="bold" if cb.get("label_bold") else "normal")
    side = cb.get("label_side", "")
    if side:
        if loc in ("bottom", "top"):
            c.ax.xaxis.set_label_position("top" if side == "first" else "bottom")
        else:
            c.ax.yaxis.set_label_position("left" if side == "first" else "right")
    if cb.get("ticks"):
        c.set_ticks(_levels(cb["ticks"]))
    if cb.get("tick_fmt"):
        c.formatter = matplotlib.ticker.FormatStrFormatter(cb["tick_fmt"])
        c.update_ticks()
    if cb.get("tick_size"):
        c.ax.tick_params(labelsize=float(cb["tick_size"]))


# ------------------------------------------------------------------ time series
def run_color(spec, k):
    """Colour of run k (its own, else the k-th of RUN_COLORS)."""
    runs = spec.get("runs") or []
    return (runs[k].get("color") if k < len(runs) else None) or RUN_COLORS[k % len(RUN_COLORS)]


def layer_color(spec, lay, d):
    """Colour of a layer in panel data d: the run's (a track with "run_color"), else
    its own."""
    if lay.get("run_color"):
        return run_color(spec, int(d.get("run", 0)))
    return lay.get("color", "k")


def run_style(spec, k):
    """Line style of run k (its own, else the k-th of RUN_STYLES)."""
    runs = spec.get("runs") or []
    return (runs[k].get("ls") if k < len(runs) else None) or RUN_STYLES[k % len(RUN_STYLES)]


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


def sounding_layout(o):
    """The skewt options' layout (older specs: the "hodo" checkbox)."""
    lay = o.get("layout")
    if lay in ("inset", "side", "skewt", "hodo"):
        return lay
    return "inset" if o.get("hodo", True) else "skewt"


def sounding_colors(spec, d):
    """Colour of each sounding of panel data d: its own, else its run's when each of
    the panel's soundings comes from another run, else the next of SND_COLORS."""
    ents = spec.get("soundings", [])
    n = int(d.get("nsnd", 0))
    es = [ents[int(d[f"N{j}_e"])] if int(d[f"N{j}_e"]) < len(ents) else {} for j in range(n)]
    runs = [int(e.get("run", 0)) for e in es]
    by_run = n > 1 and len(set(runs)) == n
    return [e.get("color") or (run_color(spec, k) if by_run else SND_COLORS[j % len(SND_COLORS)])
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

    def fmt(v, k):
        if not np.isfinite(v):
            return "–"
        return f"{v:.1f}" if k in ("stp_eff", "scp") else f"{v:.0f}"

    rows = [[fmt(float(d[f"N{j}_par"][c]), SND_PARAMS[c][0]) for c in idx]
            for j in range(n)]
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
    barbs at the right and an optional hodograph inset (skewt "inset_loc": upper
    right, upper left, or auto: the corner the traces cross least)."""
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
        if not rect:  # a top corner (the right one left of the barbs, which it would hide)
            right = 0.99 if not nbarb else 0.985 - 0.07 * (nbarb + 0.6)
            where = o.get("inset_loc") or "auto"
            corners = {"upper right": [right - 0.37, 0.6, 0.37, 0.39],
                       "upper left": [0.01, 0.6, 0.37, 0.39]}
            if where not in corners:
                legend = (many or o.get("legend", False)) and o.get("legend_loc", "upper left")
                where = min(corners, key=lambda c: _crossed(d, n, X, pb, pt, ax.get_xlim(),
                                                            corners[c], legend == c))
            rect = corners[where]
        hx = ax.inset_axes([float(v) for v in rect])
        _hodo(hx, d, n, cols, o, fs, full=bool(o.get("hodo_full_inset", False)))
    if many or o.get("legend", False):
        ax.legend(handles=handles, loc=o.get("legend_loc", "upper left"),
                  fontsize=font_size(spec, "legend"), frameon=True, framealpha=0.85)


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


def _hodo(hx, d, n, cols, o, fs, full=False):
    """Hodograph of the panel's soundings (one sounding: coloured by height bands).
    Bunkers right / left movers and the 0-6 km mean wind (hodo_kin), a ring at the
    storm motion of the SRH (hodo_storm; one sounding: with the storm-relative
    inflow and the 0-0.5 km shear, as the Sounding tab draws them), height labels
    along the trace (hodo_labels); full (a hodograph panel, not an inset): a key of
    the height bands (hodo_key) and SRH shading (srh "1" / "3": 0-1 / 0-3 km)."""
    hx._cv_hodo = True
    many = n > 1
    hm = float(o.get("hodo_max", 40.0))
    top = float(o.get("hodo_top", 9.0))
    small = 0.55 if not full else 0.75
    storm = STORM_NAMES.get(o.get("storm", "rm"), "RM")
    ring = "#ea580c"
    if not full:
        hx.set_facecolor((1, 1, 1, 0.9))
    for r in np.arange(10.0, hm + 0.1, 10.0):
        hx.add_patch(Circle((0, 0), r, fill=False, ec="0.8", lw=0.5))
        hx.text(r * 0.707, -r * 0.707, f"{r:g}", fontsize=fs * small, color="0.5",
                ha="left", va="top")
    hx.axhline(0, color="0.7", lw=0.5)
    hx.axvline(0, color="0.7", lw=0.5)
    srh = str(o.get("srh") or "") if full else ""
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
        if many:
            sel = z <= top
            hx.plot(u[sel], v[sel], color=col, lw=1.4, zorder=3)
        else:
            for z0, z1, c in HODO_BANDS:
                if z0 >= top:
                    break
                sel = (z >= z0) & (z <= min(z1, top))
                hx.plot(u[sel], v[sel], color=c, lw=1.6 if not full else 2.0, zorder=3)
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
        if o.get("hodo_kin", True):  # Bunkers movers and the 0-6 km mean wind
            for key, mk, lab in (("rm", "o", "RM"), ("lm", "o", "LM"), ("mean", "s", "")):
                c = d.get(f"N{j}_{key}")
                if c is None:
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
    hx.set_xlim(-hm, hm)
    hx.set_ylim(-hm, hm)
    hx.set_aspect("equal")
    hx.set_xticks([])
    hx.set_yticks([])
    hx.text(0.03, 0.97, "m s$^{-1}$", transform=hx.transAxes, fontsize=fs * (small + 0.05),
            va="top", color="0.4")
    if full and not many and o.get("hodo_key", True):  # the height bands
        hs = [Line2D([], [], color=c, lw=2.0, label=f"{z0:g}–{min(z1, top):g} km")
              for z0, z1, c in HODO_BANDS if z0 < top]
        if o.get("hodo_storm", True):
            hs.append(Line2D([], [], marker="o", ms=6, mfc="none", mec=ring, mew=1.4, lw=0,
                             label=f"storm ({storm})"))
        hx.legend(handles=hs, loc="upper right", fontsize=fs * small, frameon=False,
                  handlelength=1.2, borderaxespad=0.3, labelspacing=0.25)


# ------------------------------------------------------------------ annotations
def _annotate(ax, i, anns, fs):
    """Text, markers, arrows, lines, boxes and circles in panel i (panel -1: every
    panel), in data coordinates or as fractions of the panel (coords 'axes').  In a
    skew-T, data coordinates are temperature (deg C) and pressure (hPa)."""
    skew = getattr(ax, "_cv_skew", None)
    for a in anns:
        if int(a.get("panel", -1)) not in (-1, i):
            continue
        data = a.get("coords") != "axes"
        tr = ax.transData if data else ax.transAxes
        kind = a.get("kind", "text")
        col, lw = a.get("color", "k"), float(a.get("lw", 1.5))
        size = float(a.get("size") or fs)
        x, y = float(a.get("x", 0.0)), float(a.get("y", 0.0))
        x2, y2 = float(a.get("x2", x)), float(a.get("y2", y))
        txt = str(a.get("text", ""))
        wt = "bold" if a.get("bold") else "normal"
        if skew and data and kind in ("vline", "box"):  # isotherms are skewed lines
            T = [x, x] if kind == "vline" else [x, x2, x2, x, x]
            p = list(ax.get_ylim()) if kind == "vline" else [y, y, y2, y2, y]
            ax.plot(*_skewed(skew, T, p), color=col, lw=lw,
                    ls=a.get("ls", "--" if kind == "vline" else "-"))
            if kind == "vline" and txt:  # (at the bottom: its top is often off the panel)
                ax.text(*_skewed(skew, x, max(p)), f" {txt}", color=col, fontsize=fs * 0.85,
                        weight=wt, ha="left", va="bottom", clip_on=True)
            continue
        if skew and data:
            (x, x2), (y, y2) = _skewed(skew, [x, x2], [y, y2])
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


def _skewed(skew, T, p):
    """Skew-T axes coordinates of temperatures T (deg C) at pressures p (hPa)."""
    k, pb = skew
    T, p = np.asarray(T, dtype=float), np.asarray(p, dtype=float)
    return T + k * np.log(pb / np.maximum(p, 1e-6)), p


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
