"""Draw a figure from a spec (a dict) and the plotted arrays: plan views, vertical
cross-sections, time-height plots, time series, soundings or distributions on a grid
of panels.

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
distribution panels (kind "dist"): ndist, and per distribution n (a summary of all
  the values of a field over a region at one time; spec["dist"]: how they are drawn,
  hist (counts, PDF or fractions), box, violin or ecdf)
  D<n>_s       [count, mean, std, min, max, lower and upper Tukey whisker]
  D<n>_q       quantiles at DIST_PROBS;  D<n>_h  counts of a fine histogram, min to max
  D<n>_e, D<n>_label, D<n>_xl   distribution entry index, legend text, value axis label
figures of parts (kind "combo"): part k's panel i under k * 1000 + i

Specs of version 2 (upgrade() makes one of a version-1 spec or a figure of parts):
  the figure's own settings (size, fonts, colorbar, labels, axes, skewt, ts, ...),
  blocks   [{rows, cols, share, size, opts}]: grids of panels side by side (arrange
           "row") or stacked ("col"); opts: settings of the block's own
  panels   [{id, block, cell [row, col, rowspan, colspan], kind (plan, xsec, th, line,
           sounding, dist), run, time_s, z, zmode, title, letter, opts, colorbar {show},
           layers}]: data[id] is the panel's data; opts: settings of the panel's own
  layers   a plan or section panel's map layers (as version 1), a time-height panel's
           series ("series"), a time-series panel's lines ("series"), a sounding
           panel's soundings ("sounding") or a distribution panel's distributions
           ("dist"); S<n>_e, N<n>_e and D<n>_e count within the panel.
           A layer's run, time_s and z: None (or missing) for the panel's
           (resolved()); L<j>_cx, L<j>_cy: the layer's own coordinates (another run's)
  Colorbar ends (a fill's "extend"): neither, min, max, both, or auto (from the data:
  where it passes vmin / vmax); panels sharing a colorbar share the ends of all of
  them.
"""

import copy
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
ENTRIES = {"line": "series", "sounding": "soundings", "dist": "dists"}  # (kind -> list)


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
                     **({} if color is None else {"color": color}))
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
    """The matplotlib Figure of `spec` (either version) with arrays `data` (see the
    module notes).  Save it with save(), which keeps the spec's fonts for what
    matplotlib draws late (tick labels)."""
    spec, data = upgrade(spec, data)
    return _draw2(spec, data)


def _new_fig(spec):
    gap = spec.get("spacing", {})
    fig = Figure(figsize=tuple(float(v) for v in spec["size"]), layout="constrained",
                 facecolor=spec.get("background", "white"))
    fig.get_layout_engine().set(w_pad=float(gap.get("w_pad", 0.04)),
                                h_pad=float(gap.get("h_pad", 0.04)),
                                wspace=float(gap.get("wspace", 0.02)),
                                hspace=float(gap.get("hspace", 0.02)))
    return fig


def _draw2(spec, data):
    """A version-2 figure: its one block straight on the figure, or each block on a
    subfigure (as large as its share says, block_shares), with spec["colorbar"]["mode"]
    "figure" one colorbar for them all."""
    blocks = spec["blocks"]
    if len(blocks) == 1 and not blocks[0].get("opts"):
        with matplotlib.rc_context(rc(spec)):
            fig = _new_fig(spec)
            _block(fig, spec, 0, block_view(spec, 0), data, _fs(spec), _extends(spec, data))
            if spec.get("suptitle"):
                fig.suptitle(spec["suptitle"], weight="bold",
                             fontsize=font_size(spec, "suptitle"))
            code = spec.get("code") or {}
            if code.get("on") and str(code.get("text") or "").strip():
                run_code(fig, fig._cv_grid, data, spec, code["text"])
            return fig
    row = spec.get("arrange", "row") == "row"
    W, H = (float(v) for v in spec["size"])
    fig = _new_fig(spec)
    cb = spec.get("colorbar") or {}
    one_cb = cb.get("mode") == "figure"
    host, bar, side = fig, None, False
    if one_cb:  # a strip along one side for the colorbar, the blocks in the rest
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
    ratios = block_shares(spec)
    subs = np.atleast_1d(host.subfigures(1, len(blocks), width_ratios=ratios) if row else
                         host.subfigures(len(blocks), 1, height_ratios=ratios)).ravel()
    fig._cv_axes, mappables = {}, []
    ext = _extends(spec, data)
    for k, sf in enumerate(subs):
        bv = block_view(spec, k)
        if one_cb:
            bv["colorbar"] = dict(bv.get("colorbar", {}), mode="none")
        sf.set_facecolor("none")
        with matplotlib.rc_context(rc(bv)):
            _block(sf, spec, k, bv, data, _fs(bv), ext)
        fig._cv_axes.update(sf._cv_axes)
        mappables += sf._cv_mappables
        err = getattr(sf, "_cv_code_error", None)
        if err:
            fig._cv_code_error = f"part {k + 1}, {err}"
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
        with matplotlib.rc_context(rc(block_view(spec, 0))):
            _cbar_style(c, cb, lay, loc)
    if spec.get("suptitle"):
        fig.suptitle(spec["suptitle"], weight="bold", fontsize=font_size(spec, "suptitle"))
    code = spec.get("code") or {}
    if code.get("on") and str(code.get("text") or "").strip():
        run_code(fig, [fig._cv_axes[i] for i in sorted(fig._cv_axes)], data, spec,
                 code["text"])
    return fig


def _fs(spec):
    return float(spec.get("font", {}).get("size", 10))


def _cell(p):
    """(row, col, rowspan, colspan) of panel p."""
    c = [int(v) for v in p.get("cell", [0, 0])] + [1, 1]
    return c[0], c[1], max(1, c[2]), max(1, c[3])


def _block(fig, spec, k, bv, data, fs, ext):
    """Draw the panels of block k into fig (a Figure or SubFigure) with the block's
    settings bv (block_view): a plain grid of axes (hiding the empty cells, as version
    1 did), or with panels spanning cells, axes for the panels only."""
    b = spec["blocks"][k]
    rows, cols = int(b["rows"]), int(b["cols"])
    pans = sorted((p for p in spec["panels"] if int(p.get("block", 0)) == k),
                  key=lambda p: _cell(p)[:2])
    gkw = {key: [float(v) for v in b[name]] for key, name in
           (("width_ratios", "widths"), ("height_ratios", "heights")) if b.get(name)}
    if any(_cell(p)[2:] != (1, 1) for p in pans):
        gs, grid = fig.add_gridspec(rows, cols, **gkw), None
    else:
        grid = list(np.atleast_1d(fig.subplots(rows, cols, squeeze=False,
                                               gridspec_kw=gkw or None)).ravel())
    order = {id(p): n for n, p in enumerate(spec["panels"])}
    used, placed, mappables, legend = [], [], [], {}
    for p in pans:
        r, c, rs, cs = _cell(p)
        d = data.get(p["id"]) if data is not None else None
        if d is None:
            continue
        ax = grid[r * cols + c] if grid is not None else \
            fig.add_subplot(gs[r:r + rs, c:c + cs])
        V = panel_view(spec, p, bv)
        used.append(ax)
        ax, m = _panel(fig, ax, d, V, _panel_layers(p), fs, legend, ext.get(p["id"]))
        used[-1] = ax
        if grid is not None:
            grid[r * cols + c] = ax
        if m is not None and (p.get("colorbar") or {}).get("show", True):
            mappables.append((p["id"], ax, m))
        letter = p.get("letter")
        _decorate(ax, d, V, fs, p.get("title") or "",
                  order[id(p)] if letter is None else int(letter), _z_text(V, p), p["id"])
        placed.append((p, ax, V))
    if grid is not None:
        for ax in grid:
            if ax not in used:
                ax.set_visible(False)
    occ = {(r + a, c + e) for p, _, _ in placed for r, c, rs, cs in [_cell(p)]
           for a in range(rs) for e in range(cs)}
    cells = []
    for p, ax, V in placed:
        r, c, rs, cs = _cell(p)
        cells.append((ax, c, r + rs >= rows or (r + rs, c) not in occ, p["kind"],
                      V.get("axes", {})))
    _ticks(cells, used, bv.get("axes", {}))
    if legend:
        lg = bv.get("legend", {})
        where = used[min(int(lg.get("panel", 0)), len(used) - 1)] if used else None
        if where is not None:
            where.legend(list(legend.values()), list(legend.keys()),
                         loc=lg.get("loc", "upper right"), fontsize=font_size(bv, "legend"),
                         ncol=int(lg.get("ncol", 1) or 1),
                         frameon=lg.get("frame", True), framealpha=0.85)
    fig._cv_mappables = mappables
    where = {p["id"]: _cell(p)[:2] for p in pans}
    _colorbars(fig, bv.get("colorbar", {}), mappables, used, lambda i: where[i])
    ck = bv.get("contour_key", {})
    keyp = next((p for p in pans if p["id"] == ck.get("panel")), pans[0] if pans else None)
    _contour_key(fig, bv, fs, keyp.get("layers", []) if keyp else [])
    fig._cv_axes = {p["id"]: ax for p, ax, _ in placed}  # (panel -> axes)
    fig._cv_grid = grid if grid is not None else [ax for _, ax, _ in placed]
    opts = b.get("opts") or {}
    if opts.get("suptitle"):
        fig.suptitle(opts["suptitle"], weight="bold", fontsize=font_size(bv, "suptitle"))
    code = opts.get("code") or {}
    if code.get("on") and str(code.get("text") or "").strip():
        run_code(fig, fig._cv_grid, {p["id"]: data[p["id"]] for p, _, _ in placed}, bv,
                 code["text"])


def _panel(fig, ax, d, spec, layers, fs, legend, first_ext=None):
    """Draw panel data d into ax with `spec`'s settings (a version-1 spec, or a panel's
    view of a version-2 one) and its map `layers` (the legend entries go into
    `legend`); first_ext: the colorbar ends of its first fill (else its own).  Returns
    (axes, (mappable, layer) of the first fill or None): a sounding's layout or table
    may replace the axes."""
    kind = spec["kind"]
    m = None
    if d.get("missing"):
        ax.text(0.5, 0.5, str(d["missing"]), transform=ax.transAxes, ha="center",
                va="center", color="0.4", fontsize=fs * 0.9, wrap=True)
    elif kind == "line":
        _lines(ax, d, spec, fs)
    elif kind == "sounding":  # (a layout or table may replace the panel's axes)
        ax = _sounding(fig, ax, d, spec, fs)
    elif kind == "dist":
        _dists(ax, d, spec, fs)
    else:
        xsec = kind == "xsec"
        x, y = d["x"], d["y"]
        for j, lay in enumerate(layers):
            if not lay.get("on", True):
                continue
            t = lay["type"]
            a = d.get(f"L{j}")
            lx, ly = d.get(f"L{j}_cx", x), d.get(f"L{j}_cy", y)
            if t == "fill" and a is not None:
                ends = first_ext if m is None and first_ext else extend_of(lay, a)
                lay = dict(lay, extend=ends)
                mm = _fill(ax, lx, ly, a, lay)
                m = m or (mm, lay)
            elif t == "contour" and a is not None:
                _contour(ax, lx, ly, a, lay)
            elif t == "shade" and a is not None:
                _shade(ax, lx, ly, a, lay)
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
    return ax, m


def _decorate(ax, d, spec, fs, title, letter, ztxt, key):
    """Limits, axis labels, title, the panel's letter (number `letter`), time, height
    (ztxt) and run labels, and the annotations of panel `key`."""
    kind = spec["kind"]
    ax_opts = spec.get("axes", {})
    if "xlim" in d and not d.get("missing") and kind != "sounding":
        ax.set_xlim(*d["xlim"])
        if "ylim" in d:
            ax.set_ylim(*d["ylim"])
    if kind == "plan" and ax_opts.get("equal", True):
        ax.set_aspect("equal")
    if not getattr(ax, "_cv_hodo", False):  # (a hodograph panel labels its rings)
        if ax_opts.get("xlabel") or kind != "dist":  # distributions: the field's
            ax.set_xlabel(ax_opts.get("xlabel", ""))
        if ax_opts.get("ylabel") or kind not in ("line", "dist"):  # (time series: units)
            ax.set_ylabel(ax_opts.get("ylabel", ""))
    if title:
        ax.set_title(title, weight="bold" if ax_opts.get("title_bold", True)
                     else "normal", loc=ax_opts.get("title_loc", "center"))
    labels, tlab, rlab = (spec.get(k, {}) for k in ("letters", "time_label", "run_label"))
    if labels.get("on", True):
        _anchored(ax, panel_letter(letter, labels.get("fmt", "{a}")), labels, fs * 1.2)
    if tlab.get("on", True) and "time_s" in d:
        _anchored(ax, time_text(d["time_s"], tlab), tlab, fs * 1.2)
    zlab = spec.get("z_label", {})
    if zlab.get("on") and ztxt:
        _anchored(ax, ztxt, zlab, fs * 1.2)
    if rlab.get("on", True) and d.get("run_label"):
        _anchored(ax, str(d["run_label"]), rlab, fs * 1.2,
                  run_color(spec, int(d.get("run", 0))) if rlab.get("run_color") else None)
    _annotate(ax, key, spec.get("annotations", []), fs)


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
    elif kind in ENTRIES:
        ents = spec.get(ENTRIES[kind], [])
        n = 1 + max([int(e.get("panel", 0)) for e in ents] or [0])
    elif vary == "time":
        n = len(spec.get("times_s") or spec.get("times") or [])
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
    return edited_layers(layers, panel_edit(spec, i))


def panel_edit(spec, i):
    """The changes made to panel i alone (spec["edits"][str(i)], the panel tree): its
    "run", "time_s", "z" (km), "title", "layers" ({str(j): the keys layer j has in
    this panel only, its own "run", "time_s" and "z" among them}) and "extra" (layers
    of this panel only, drawn after the others)."""
    return (spec.get("edits") or {}).get(str(i)) or {}


def edited_layers(layers, e):
    """Layers with panel edit e: its height for the layers at a height (but those with
    "z_fixed" or a height of their own), then each layer's own keys, then its extra
    layers."""
    if not e:
        return layers
    out = []
    for j, lay in enumerate(layers):
        own = (e.get("layers") or {}).get(str(j)) or {}
        if e.get("z") is not None and "z" not in own and "z" in lay and \
                not lay.get("z_fixed") and (lay["type"] == "vectors" or
                                            lay.get("mode", "height") == "height"):
            lay = dict(lay, z=float(e["z"]))
        out.append(dict(lay, **own) if own else lay)
    return out + [dict(lay) for lay in e.get("extra") or []]


def panel_ref(spec, i):
    """(run index, model time in s) of panel i of a version-1 spec, or None for an
    empty grid cell: as its layout says (form_ref), or as changed in this panel alone
    (panel_edit)."""
    ref = form_ref(spec, i)
    e = panel_edit(spec, i)
    if ref is None or not e:
        return ref
    k = int(e["run"]) if e.get("run") is not None and \
        int(e["run"]) < len(spec.get("runs") or [None]) else ref[0]
    return k, float(e["time_s"]) if e.get("time_s") is not None else ref[1]


def form_ref(spec, i):
    """(run index, model time in s) of panel i as the layout says, or None.  vary:
    "time" (one run, a time per panel), "field" (one run and time, a fill per panel),
    "height" (one run and time, a height per panel:
    spec["panel_z"]), "grid" (runs x times: rows are runs when runs_as == "rows", else
    columns) or "custom" (spec["panels"]: a run and time per panel)."""
    vary, nr = spec["vary"], len(spec.get("runs") or [None])
    if vary == "time":  # (a time of None: an empty grid cell)
        ts = spec["times_s"]
        return (int(spec.get("run", 0)), float(ts[i])) if i < len(ts) and ts[i] is not None \
            else None
    if vary in ("field", "height"):
        return int(spec.get("run", 0)), float(spec["time_s"])
    if vary == "grid":
        r, c = divmod(i, int(spec["cols"]))
        k, j = (r, c) if spec.get("runs_as", "rows") == "rows" else (c, r)
        ts = spec["times_s"]
        return (k, float(ts[j])) if k < nr and j < len(ts) and ts[j] is not None else None
    pans = spec.get("panels", [])
    if i < len(pans) and int(pans[i]["run"]) < nr:
        return int(pans[i]["run"]), float(pans[i]["time_s"])
    return None


# ------------------------------------------------------------------ spec version 2
V1_PANEL_KEYS = ("version", "kind", "rows", "cols", "vary", "times", "time", "times_s",
                 "time_s", "panel_fills", "panel_z", "panel_zmode", "layers", "run",
                 "runs_as", "panels", "titles", "series", "soundings", "dists", "edits",
                 "form")
FIG_ONLY = ("version", "kind", "arrange", "parts", "blocks", "panels", "size", "size_set",
            "size_auto", "share", "suptitle", "export", "made_with", "code")
EXTENDS = ("auto", "neither", "min", "max", "both")


def upgrade(spec, data=None):
    """(version-2 spec, data) of a version-1 spec or a figure of parts (a version-2
    spec comes back as it is): each panel written out with its own layers (the
    shared layers as the panel had them, its height, fill, title and letter), each
    part a block with its settings, and in `data` (a copy; None: none) each line's and
    sounding's entry counted within its panel."""
    if int(spec.get("version", 1)) >= 2:
        return spec, data
    combo = spec.get("kind") == "combo"
    parts = spec["parts"] if combo else [spec]
    out = {k: copy.deepcopy(v) for k, v in spec.items() if k not in V1_PANEL_KEYS + ("parts",)}
    out.update(version=2, arrange=spec.get("arrange", "row"))
    data = None if data is None else dict(data)
    blocks, panels, start = [], [], 0
    for k, part in enumerate(parts):
        b = dict(rows=int(part["rows"]), cols=int(part["cols"]))
        ck = None
        if combo:
            opts = {key: copy.deepcopy(v) for key, v in part.items() if key not in V1_PANEL_KEYS}
            opts["annotations"] = [a if int(a.get("panel", -1)) == -1 else
                                   dict(a, panel=k * 1000 + int(a["panel"]))
                                   for a in opts.get("annotations", [])]
            b.update(share=part.get("share"), size=list(part["size"]), opts=opts)
            ck = opts.get("contour_key")
        else:
            ck = out.get("contour_key")
        if ck and ck.get("on"):
            ck["lay"] = copy.deepcopy(_key_layer(ck, part.get("layers", [])))
        blocks.append(b)
        n = npanels(part)
        for i in range(n):
            p = _v1_panel(part, i)
            if p is None:
                continue
            key = k * 1000 + i if combo else i
            p.update(id=key, block=k, letter=i + start)
            panels.append(p)
            if data is not None and key in data:
                data[key] = _local_entries(part, i, data[key])
        start += n
    out.update(blocks=blocks, panels=panels)
    return out, data


def _v1_panel(spec, i):
    """Panel i of a version-1 spec as a version-2 panel (None: an empty cell)."""
    kind = spec.get("kind", "plan")
    r, c = divmod(i, int(spec["cols"]))
    titles = spec.get("titles") or []
    p = dict(kind=kind, cell=[r, c, 1, 1], run=None, time_s=None,
             title=titles[i] if i < len(titles) and titles[i] else "", layers=[])
    if kind == "th":
        ref = series_ref(spec, i)
        if ref is None:
            return None
        p["run"] = ref[0]
        p["layers"] = [dict(copy.deepcopy(spec["series"][ref[1]]), type="series", on=True)]
    elif kind in ENTRIES:
        p["layers"] = [dict({k: copy.deepcopy(v) for k, v in e.items() if k != "panel"},
                            type="series" if kind == "line" else kind)
                       for e in spec.get(ENTRIES[kind], []) if int(e.get("panel", 0)) == i]
    else:
        ref = panel_ref(spec, i)
        if ref is None:
            return None
        p["run"], p["time_s"] = ref
        p["layers"] = copy.deepcopy(spec_layers(spec, i))
        zs = spec.get("panel_z") or []
        if spec.get("vary") == "height" and i < len(zs) and zs[i] is not None:
            p["z"], p["zmode"] = float(zs[i]), spec.get("panel_zmode", "height")
        e = panel_edit(spec, i)
        if e.get("z") is not None:
            p["z"], p["zmode"] = float(e["z"]), "height"
    if panel_edit(spec, i).get("title") is not None:
        p["title"] = panel_edit(spec, i)["title"]
    return p


def _local_entries(spec, i, d):
    """Panel data d of version-1 panel i with its lines' (soundings') entries counted
    within the panel."""
    kind = spec.get("kind")
    if kind not in ENTRIES:
        return d
    key, count = {"line": ("S", "nlines"), "sounding": ("N", "nsnd"),
                  "dist": ("D", "ndist")}[kind]
    mine = [e for e, ent in enumerate(spec.get(ENTRIES[kind], []))
            if int(ent.get("panel", 0)) == i]
    where = {e: n for n, e in enumerate(mine)}
    d = dict(d)
    for j in range(int(d.get(count, 0))):
        e = int(d[f"{key}{j}_e"])
        d[f"{key}{j}_e"] = where.get(e, len(mine))
    return d


def block_view(spec, k):
    """The settings of block k of a version-2 spec: the figure's (but those of the
    figure alone: size, title, export, code) and the block's own (opts)."""
    v = {key: val for key, val in spec.items() if key not in FIG_ONLY}
    v.update(spec["blocks"][k].get("opts") or {})
    if (v.get("colorbar") or {}).get("mode") in ("parts", "figure"):
        v["colorbar"] = dict(v["colorbar"], mode="shared")
    return v


def panel_view(spec, p, bv=None):
    """The settings panel p is drawn with: its block's (bv: block_view), then its own
    (p["opts"]), with its kind and layers where version 1 kept them (soundings and
    the series of a time-series panel and distributions under "soundings", "series"
    and "dists")."""
    v = dict(block_view(spec, int(p.get("block", 0))) if bv is None else bv)
    v.update(p.get("opts") or {})
    kind = v["kind"] = p["kind"]
    v[ENTRIES.get(kind, "layers")] = p.get("layers") or []
    return v


def block_shares(spec):
    """Each block's share of a version-2 figure (part_shares of its blocks)."""
    return part_shares(dict(arrange=spec.get("arrange", "row"), parts=[
        dict(share=b.get("share"), size=b.get("size") or spec["size"])
        for b in spec["blocks"]]))


def _panel_layers(p):
    """The map layers panel p is drawn with (a time-height panel: its series' fill)."""
    if p["kind"] == "th":
        return [dict({k: lay[k] for k in FILL_KEYS if k in lay}, type="fill",
                     on=lay.get("on", True)) for lay in p.get("layers", [])]
    return p.get("layers") or []


def resolved(p, lay):
    """Layer lay of panel p with its run, time and height filled in from the panel's
    (where the layer has None or none)."""
    out = dict(lay)
    for k in ("run", "time_s", "z"):
        if out.get(k) is None and p.get(k) is not None:
            out[k] = p[k]
    if out.get("run") is None:
        out["run"] = 0
    return out


def _z_text(spec, p):
    """The height label of version-2 panel p (z_text), or "" for a panel without a
    height of its own."""
    if p.get("z") is None:
        return ""
    level = p.get("zmode", "height") == "level"
    fmt = spec.get("z_label", {}).get("fmt") or ("k = {k}" if level else "z = {z:g} km")
    return fmt.format(z=float(p["z"]), k=int(round(float(p["z"]))))


def extend_of(lay, a):
    """The colorbar ends of fill layer lay with values a: its own, or with "auto" the
    ends the (unmasked) values pass vmin or vmax at."""
    ends = lay.get("extend", "neither") or "neither"
    if ends != "auto":
        return ends
    a = np.asarray(a, dtype=float)
    if lay.get("mask_below") not in (None, ""):
        a = a[a > float(lay["mask_below"])]
    a = a[np.isfinite(a)]
    if not a.size:
        return "neither"
    lo, hi = _bounds(lay)
    return union_extend(["min"] * bool(a.min() < lo) + ["max"] * bool(a.max() > hi))


def union_extend(ends):
    """One colorbar's ends for fills with ends `ends` (min and max: both)."""
    lo = any(e in ("min", "both") for e in ends)
    hi = any(e in ("max", "both") for e in ends)
    return "both" if lo and hi else "min" if lo else "max" if hi else "neither"


def _extends(spec, data):
    """{panel id: colorbar ends of its first fill}: the ends of all first fills that
    share a colorbar (the block's colorbar mode: shared, row, col; "figure": all
    blocks') united."""
    fig_mode = (spec.get("colorbar") or {}).get("mode")
    modes = [(block_view(spec, k).get("colorbar") or {}).get("mode", "shared")
             for k in range(len(spec["blocks"]))]
    groups, first = {}, {}
    for p in spec["panels"]:
        d = (data or {}).get(p["id"])
        if d is None or d.get("missing") or p["kind"] in ENTRIES or \
                not (p.get("colorbar") or {}).get("show", True):
            continue
        ends = next((extend_of(lay, d[f"L{j}"]) for j, lay in enumerate(_panel_layers(p))
                     if lay["type"] == "fill" and lay.get("on", True)
                     and d.get(f"L{j}") is not None), None)
        if ends is None:
            continue
        k = int(p.get("block", 0))
        r, c = _cell(p)[:2]
        mode = modes[k]
        g = ("figure",) if fig_mode == "figure" else \
            (k, {"shared": "", "row": ("r", r), "col": ("c", c)}.get(mode, ("p", p["id"])))
        groups.setdefault(g, []).append(ends)
        first[p["id"]] = g
    return {i: union_extend(groups[g]) for i, g in first.items()}


def _ticks(cells, used, block_opts):
    """Tick marks and labels of the panels: cells [(axes, column, in the bottom row (no
    panel below), kind, axes options)]; block_opts["ticklabels"] outer: labels on the
    left column and bottom row only (while all panels show the same ranges)."""
    mode = block_opts.get("ticklabels", "all")  # all | outer | none
    lims = {(tuple(np.round(ax.get_xlim(), 6)), tuple(np.round(ax.get_ylim(), 6)))
            for ax in used}
    if mode == "outer" and len(lims) > 1:  # panels show different ranges: label all
        mode = "all"
    for ax, c, last_row, kind, opts in cells:
        if ax not in used:
            continue
        hodo = getattr(ax, "_cv_hodo", False)  # (a hodograph keeps its own look)
        if mode == "none" or not opts.get("ticks", True):
            ax.tick_params(labelleft=False, labelbottom=False)
            ax.set_xlabel("")
            ax.set_ylabel("")
        elif mode == "outer":
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


def _colorbars(fig, cb, mappables, used, cell):
    """The colorbars of mappables [(panel, axes, (mappable, layer))]: cb["mode"]
    shared (one), row / col (one per row / column of panels: cell(panel) -> (row,
    col)), none, or else one per panel."""
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
        by = {}
        for i, ax, ml in mappables:
            r, c = cell(i)
            by.setdefault(r if mode == "row" else c, []).append((ax, ml))
        groups = [([a for a, _ in items], items[0][1]) for items in by.values()]
    else:
        groups = [(ax, ml) for _, ax, ml in mappables]
    for axes, (m, lay) in groups:
        c = fig.colorbar(m, ax=axes, extend=lay.get("extend", "neither"), **kw)
        _cbar_style(c, cb, lay, loc)


def reduce_label(red, units=""):
    """Colorbar text of a layer's time window ("reduce"), e.g. 'max over 60–90 min
    (m²/s²)' or 'storm-following mean'."""
    op = {"composite": "storm-following mean"}.get(red["op"], red["op"])
    t0, t1 = red.get("t0"), red.get("t1")
    when = "" if t0 is None and t1 is None else " over " + (
        f"{(t0 or 0) / 60:g}–{t1 / 60:g} min" if t1 is not None else
        f"{t0 / 60:g} min to the panel time")
    every = f", every {int(red['every'])}" if int(red.get("every") or 1) > 1 else ""
    return f"{op}{when}{every}" + (f" ({units})" if units else "")


def _cbar_style(c, cb, lay, loc):
    """Label (the colorbar's own, else the layer's, else its units), ticks and fonts."""
    units = lay.get("units", "")
    if lay.get("reduce"):  # (a time window)
        units = reduce_label(lay["reduce"], units)
    if lay.get("minus"):  # (a difference)
        units = f"difference ({units})" if units else "difference"
    c.set_label(cb.get("label") or lay.get("cbar_label") or units,
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
    if lay.get("run_color"):  # (the layer's own run, else the panel's)
        return run_color(spec, int(d.get("run", 0) if lay.get("run") is None else lay["run"]))
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


# ------------------------------------------------------------------ distributions
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


def _key_layer(ck, layers):
    """The contour layer of a contour key: layer ck["layer"], else the first contour
    layer that is on (None: none)."""
    k = int(ck.get("layer", -1))
    return layers[k] if 0 <= k < len(layers) and layers[k]["type"] == "contour" else next(
        (l for l in layers if l["type"] == "contour" and l.get("on", True)), None)


def _contour_key(fig, spec, fs, layers=None):
    """Nested circles labelled with a contour layer's levels and the field's name in
    the middle (a key for unlabelled contours, e.g. updraft speed): ck["lay"] (an
    upgraded spec's), else _key_layer of `layers` (default: spec["layers"])."""
    ck = spec.get("contour_key", {})
    if not ck.get("on"):
        return
    lay = ck.get("lay") or _key_layer(ck, spec.get("layers", []) if layers is None
                                      else layers)
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
