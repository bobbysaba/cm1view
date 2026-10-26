"""Map layers (fills, contours, shading, vectors) and their colorbars."""

import numpy as np
import matplotlib
from matplotlib.colors import LogNorm
from matplotlib.patches import Circle, Rectangle
from matplotlib.ticker import MultipleLocator
from matplotlib.transforms import Bbox

from .base import ENTRIES, colormap, _bounds, _steps, _norm, _levels, _cell
from .v2 import block_view, _panel_layers, _key_layer

def _fill(ax, x, y, a, lay):
    a = np.array(a, dtype=float)
    if lay.get("mask_below") is not None and lay["mask_below"] != "":
        a[a <= float(lay["mask_below"])] = np.nan
    lo, hi = (None, None) if lay.get("scale") == "log" else _bounds(lay)
    cm = colormap(lay["cmap"], lay.get("reverse", False), lay.get("white_first", False), lo, hi)
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
    color, hatch = lay.get("color", "magenta"), lay.get("hatch") or ""
    if hatch:  # hatching or stippling in the colour, over the fields below
        with matplotlib.rc_context({"hatch.color": color,
                                    "hatch.linewidth": float(lay.get("hatch_lw", 0.6))}):
            ax.contourf(x, y, a, lv, colors="none", hatches=[hatch],
                        alpha=float(lay.get("alpha", 0.6)))
    else:
        ax.contourf(x, y, a, lv, colors=[color], alpha=float(lay.get("alpha", 0.6)))
    if lay.get("outline"):
        ax.contour(x, y, a, [thr], colors=lay["outline"],
                   linewidths=float(lay.get("lw", 1.0)))


# a vector layer's key arrow units (lay["vector"]: the vectors of cm1view/core/vectors.py)
KEY_UNITS = {"wind": "m s$^{-1}$", "hvort": "s$^{-1}$", "bgen": "10$^{-4}$ s$^{-2}$"}


def _vectors(ax, d, j, lay, xsec, nkey=0):
    """Arrows, barbs (plan panels; wind in kt or m/s: half barb 5, full 10, flag 50)
    or streamlines of vector layer j; nkey: key arrows drawn before this one's in the
    panel (each further one to the left)."""
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
    if lay.get("style") == "barbs" and not xsec:  # (a section's arrows stay arrows)
        kt = lay.get("barb_units", "kt") == "kt" and lay.get("vector", "wind") == "wind"
        f = 1.943844 if kt else 1.0  # m/s -> kt
        ax.barbs(x, y, np.asarray(u) * f, np.asarray(v) * f, color=lay.get("color", "k"),
                 length=float(lay.get("barb_len", 5.5)), linewidth=float(lay.get("slw", 0.8)),
                 pivot="middle" if lay.get("pivot_mid") else "tip")
        return
    q = ax.quiver(x, y, u, v, color=lay.get("color", "k"), scale=float(lay.get("scale", 250)),
                  width=float(lay.get("width", 0.002)), angles="xy" if xsec else "uv",
                  scale_units=None, pivot="middle" if lay.get("pivot_mid") else "tail")
    ref = lay.get("key")
    if ref:
        units = KEY_UNITS.get(lay.get("vector", "wind"), "")
        ax.quiverkey(q, 0.88 - 0.3 * nkey, 1.02, float(ref), f"{float(ref):g} {units}",
                     labelpos="E", coordinates="axes",
                     fontproperties={"size": max(6, 0.8 * matplotlib.rcParams["font.size"])})


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
    panel below), kind, axes options)]; block_opts["ticklabels"] outer: tick labels on
    the left column (y) and bottom row (x) only, each while all panels show the same
    range of it, and axis labels there only, but a panel's own label that differs from
    theirs."""
    mode = block_opts.get("ticklabels", "all")  # all | outer | none
    same = {name: len({tuple(np.round(getattr(ax, f"get_{name}lim")(), 6))
                       for ax in used}) <= 1 for name in ("x", "y")}
    cells = [cell for cell in cells if cell[0] in used]
    outer_x = {ax.get_xlabel() for ax, _, last_row, _, _ in cells if last_row}
    outer_y = {ax.get_ylabel() for ax, c, _, _, _ in cells if c == 0}
    for ax, c, last_row, kind, opts in cells:
        hodo = getattr(ax, "_cv_hodo", False)  # (a hodograph keeps its own look)
        if mode == "none" or not opts.get("ticks", True):
            ax.tick_params(labelleft=False, labelbottom=False)
            ax.set_xlabel("")
            ax.set_ylabel("")
        elif mode == "outer":
            if not last_row:
                if same["x"]:
                    ax.tick_params(labelbottom=False)
                if ax.get_xlabel() in outer_x:
                    ax.set_xlabel("")
            if c > 0:
                if same["y"]:
                    ax.tick_params(labelleft=False)
                if ax.get_ylabel() in outer_y:
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
        c = fig.colorbar(m, ax=axes, extend=lay.get("extend", "neither"),
                         aspect=_cbar_aspect(axes, kw, orient), **kw)
        _cbar_style(c, cb, lay, loc)


def _cbar_aspect(axes, kw, orient):
    """Length / thickness of a colorbar that fills its share (kw fraction) of the
    panels' box and kw shrink of their length: matplotlib's default (20) caps the
    thickness, so a larger "Thickness" would only add space."""
    boxes = [a.get_position().transformed(a.figure.transSubfigure)
             for a in np.atleast_1d(axes)]
    box = Bbox.union(boxes)
    w, h = (box.width, box.height) if orient == "horizontal" else (box.height, box.width)
    return max(kw["shrink"] * w / max(kw["fraction"] * h, 1e-6), 1.0)


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
    """Label and ticks (the layer's or series' own, else the Style tab's for every
    colorbar, else its units / automatic ticks) and fonts."""
    units = lay.get("units", "")
    if lay.get("reduce"):  # (a time window)
        units = reduce_label(lay["reduce"], units)
    if lay.get("minus"):  # (a difference)
        units = f"difference ({units})" if units else "difference"
    c.set_label(lay.get("cbar_label") or cb.get("label") or units,
                size=float(cb.get("label_size") or 0) or None,
                weight="bold" if cb.get("label_bold") else "normal")
    side = cb.get("label_side", "")
    if side:
        if loc in ("bottom", "top"):
            c.ax.xaxis.set_label_position("top" if side == "first" else "bottom")
        else:
            c.ax.yaxis.set_label_position("left" if side == "first" else "right")
    ticks = lay.get("cbar_ticks") or cb.get("ticks")
    if ticks:
        c.set_ticks(_levels(ticks))
    if cb.get("tick_fmt"):
        c.formatter = matplotlib.ticker.FormatStrFormatter(cb["tick_fmt"])
        c.update_ticks()
    if cb.get("tick_size"):
        c.ax.tick_params(labelsize=float(cb["tick_size"]))


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
