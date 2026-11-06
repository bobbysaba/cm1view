"""Map layers (fills, contours, shading, vectors) and their colorbars."""

import numpy as np
import matplotlib
from matplotlib.collections import LineCollection
from matplotlib.colors import LogNorm, Normalize
from matplotlib.patches import Circle, Rectangle
from matplotlib.ticker import MultipleLocator
from matplotlib.transforms import Bbox

from .base import ENTRIES, colormap, _bounds, _steps, _norm, _levels, _cell, _key_layer
from .v2 import block_view, _panel_layers

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
        # (the opacity is the lines': an alpha on the contourf would make its empty
        # fill opaque black)
        rgba = matplotlib.colors.to_rgba(color, float(lay.get("alpha", 0.6)))
        with matplotlib.rc_context({"hatch.color": rgba,
                                    "hatch.linewidth": float(lay.get("hatch_lw", 0.6))}):
            ax.contourf(x, y, a, lv, colors="none", hatches=[hatch])
    else:
        ax.contourf(x, y, a, lv, colors=[color], alpha=float(lay.get("alpha", 0.6)))
    if lay.get("outline"):
        ax.contour(x, y, a, [thr], colors=lay["outline"],
                   linewidths=float(lay.get("lw", 1.0)))


# a vector layer's key arrow units (lay["vector"]: the vectors of cm1view/core/vectors.py)
KEY_UNITS = {"wind": "m s$^{-1}$", "hvort": "s$^{-1}$", "bgen": "10$^{-4}$ s$^{-2}$"}


# a Map boundaries layer's lines: width and opacity as a share of the layer's (the
# viewer's map draws them alike)
BOUNDARY_LOOK = {"coastlines": (1.0, 1.0), "countries": (1.25, 1.0), "states": (1.0, 1.0),
                 "lakes": (0.8, 0.9), "counties": (0.55, 0.6)}


def _boundaries(ax, d, j, lay, fs):
    """A Map boundaries layer j: its chosen lines (d["L<j>_b_<kind>"], rows x, y,
    NaN-separated), and its lat/lon lines (L<j>_grid) with their labels where they
    meet the bottom and left edges (L<j>_glab rows x, y, edge 0 bottom / 1 left;
    L<j>_glab_t their texts)."""
    col, lw = lay.get("color", "0.35"), float(lay.get("lw", 0.6))
    for kind in lay.get("kinds") or []:
        xy = d.get(f"L{j}_b_{kind}")
        if xy is None or not np.size(xy):
            continue
        fw, fa = BOUNDARY_LOOK.get(kind, (1.0, 1.0))
        ax.plot(xy[0], xy[1], color=col, lw=lw * fw, alpha=fa, solid_joinstyle="round",
                solid_capstyle="round")
    g = d.get(f"L{j}_grid")
    if not lay.get("grid") or g is None or not np.size(g):
        return
    ax.plot(g[0], g[1], color=col, lw=max(0.4, 0.75 * lw), ls=":", alpha=0.7)
    if not lay.get("grid_labels", True):
        return
    rows = np.atleast_2d(d.get(f"L{j}_glab", np.zeros((0, 3))))
    texts = np.atleast_1d(d.get(f"L{j}_glab_t", np.array([], str)))
    for (x, y, edge), text in zip(rows, texts):
        left = int(edge) == 1
        ax.annotate(str(text), (x, y), xytext=(3, 0) if left else (0, 2),
                    textcoords="offset points", ha="left" if left else "center",
                    va="center" if left else "bottom", color=col, fontsize=0.65 * fs,
                    annotation_clip=True)


def sector_outline(d, lay):
    """(x, y) of a Sector layer's outline in panel data d (a plan view): the wedge from
    az0 clockwise to az1 (degrees from the storm motion's direction, d["sector"], or
    from north) out to rmax, around the track's centre (shifted by offx, offy) or a
    fixed point (cx, cy grid km); a circle for the whole ring.  None without a
    centre."""
    if lay.get("center") == "point":
        o = d.get("origin", (0.0, 0.0))
        cx, cy = float(lay.get("cx", 0.0)) - o[0], float(lay.get("cy", 0.0)) - o[1]
    else:
        cx = float(d["sector"][0]) + float(lay.get("offx", 0.0))
        cy = float(d["sector"][1]) + float(lay.get("offy", 0.0))
    if not (np.isfinite(cx) and np.isfinite(cy)):
        return None
    ref = float(d["sector"][2]) if lay.get("ref", "motion") == "motion" else 0.0
    a0, R = float(lay.get("az0", 0.0)), float(lay.get("rmax", 20.0))
    span = (float(lay.get("az1", 360.0)) - a0) % 360.0 or 360.0
    th = np.radians(ref + a0 + np.linspace(0.0, span, max(8, int(span / 2.0)) + 1))
    x, y = cx + R * np.sin(th), cy + R * np.cos(th)
    if span >= 360.0:
        return x, y
    return np.concatenate([[cx], x, [cx]]), np.concatenate([[cy], y, [cy]])


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


def parcel_label(lay):
    """Colour bar label of parcels coloured by lay["cvar"]: "parcel w (m/s)"; a 3D field
    sampled at them ("@thpert"): "thpert at the parcels (K)"."""
    cv, u = lay["cvar"], lay.get("units")
    lab = f"{cv[1:]} at the parcels" if cv.startswith("@") else f"parcel {cv}"
    return f"{lab} ({u})" if u else lab


def parcel_norm(lay, values):
    """(colormap, norm) of parcels coloured by a variable: parcel layer `lay`'s vmin..vmax,
    blank ones from the 2nd-98th percentile of `values` (arrays or None), symmetric about
    0 when it straddles 0."""
    lo, hi = lay.get("vmin"), lay.get("vmax")
    if lo in (None, "") or hi in (None, ""):
        v = [np.ravel(a) for a in values if a is not None]
        v = np.concatenate(v) if v else np.zeros(0)
        v = v[np.isfinite(v)]
        plo, phi = (np.percentile(v, [2, 98]) if v.size else (0.0, 1.0))
        if plo < 0 < phi:
            plo, phi = -max(-plo, phi), max(-plo, phi)
        lo = float(plo) if lo in (None, "") else float(lo)
        hi = float(phi) if hi in (None, "") else float(hi)
    cm = colormap(lay.get("cmap", "viridis"), lay.get("reverse", False))
    return cm, Normalize(float(lo), float(hi) if float(hi) > float(lo) else float(lo) + 1.0)


def _parcels(ax, d, j, lay):
    """A parcel layer: tails (L<j>_px, L<j>_py: NaN-separated lines) and heads at the
    panel time (L<j>_hx, L<j>_hy), in the layer's colour or coloured by a parcel
    variable (L<j>_pv, L<j>_hv; its range vmin..vmax, blank: the 2nd-98th percentile,
    symmetric about 0 when it straddles 0).  Returns the mappable of a coloured layer,
    else None."""
    px, py, pv = (d.get(f"L{j}_p{c}") for c in "xyv")
    hx, hy, hv = (d.get(f"L{j}_h{c}") for c in "xyv")
    by = bool(lay.get("cvar")) and (pv is not None or hv is not None)
    lw, alpha = float(lay.get("lw", 0.8)), float(lay.get("alpha", 0.8))
    cm = norm = m = None
    if by:
        cm, norm = parcel_norm(lay, (pv, hv))
    if px is not None and len(px) > 1:
        pts = np.column_stack([px, py])
        seg = np.stack([pts[:-1], pts[1:]], axis=1)
        ok = np.isfinite(seg).all(axis=(1, 2))
        lc = LineCollection(seg[ok], linewidths=lw, alpha=alpha, zorder=2.5,
                            capstyle="round")
        if by and pv is not None:
            lc.set_array(0.5 * (pv[:-1] + pv[1:])[ok])
            lc.set_cmap(cm)
            lc.set_norm(norm)
            m = lc
        else:
            lc.set_color(lay.get("color", "k"))
        lc.set_rasterized(bool(ok.sum() > 20000))  # (a PDF of many lines: as pixels)
        ax.add_collection(lc)
    if lay.get("heads", True) and hx is not None and len(hx):
        kw = dict(s=float(lay.get("ms", 3.0)) ** 2, edgecolors="none", zorder=2.6,
                  alpha=min(1.0, alpha + 0.2))
        if by and hv is not None:
            sc = ax.scatter(hx, hy, c=hv, cmap=cm, norm=norm, **kw)
            m = m or sc
        else:
            ax.scatter(hx, hy, color=lay.get("color", "k"), **kw)
    return m


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


BAR_LOOK = ("cmap", "reverse", "white_first", "vmin", "vmax", "nlevels", "scale", "levels", "units",
            "cbar_label", "cbar_ticks")


def bar_key(p, lay, mixed):
    """Which bar of a block panel p's first fill `lay` goes on, among bars that a mode would
    otherwise make one: the bar it names (p["colorbar"]["group"]), else in a block of several
    kinds one for each look of colours, as one bar can't speak for a time-height plot and a map
    in other colours; else "" (the mode alone says)."""
    named = (p.get("colorbar") or {}).get("group")
    if named:
        return f"named:{named}"
    return repr([lay.get(k) for k in BAR_LOOK]) if mixed else ""


def _mixed_kinds(spec, k):
    """Whether block k has panels of several kinds, not apart in groups of their own."""
    return not spec.get("groups") and \
        len({p["kind"] for p in spec["panels"] if int(p.get("block", 0)) == k}) > 1


def bar_fill(lay):
    """Whether layer lay can have a colorbar: a fill, or a time-height series, that is on."""
    return lay.get("type") in ("fill", "series") and lay.get("on", True) is not False


def _bar_group(spec, p, fill, modes):
    """(what identifies the bar of panel p with first fill `fill`, the colorbar mode there)."""
    k = int(p.get("block", 0))
    r, c = _cell(p)[:2]
    name = p.get("group")
    own = spec.get("groups") or {}
    mode = (own.get(name, {}).get("colorbar") or {}).get("mode", "shared") \
        if modes[k] == "groups" else modes[k]
    bar = bar_key(p, fill, _mixed_kinds(spec, k))
    g = ("figure",) if (spec.get("colorbar") or {}).get("mode") == "figure" else \
        (k, name if modes[k] == "groups" else "", bar,
         "" if bar.startswith("named:") else
         {"shared": "", "row": ("r", r), "col": ("c", c)}.get(mode, ("p", p["id"])))
    return g, mode


def _block_modes(spec):
    return [(block_view(spec, k).get("colorbar") or {}).get("mode", "shared")
            for k in range(len(spec["blocks"]))]


def bar_members(spec):
    """{panel id: the ids of the panels on its colorbar, in the order they are drawn}, of the panels
    with a colorbar: the first of them is the one whose colours it shows."""
    modes = _block_modes(spec)
    groups, of = {}, {}
    pans = sorted(spec["panels"], key=lambda p: (int(p.get("block", 0)), _cell(p)[:2]))
    for p in pans:
        if (p["kind"] in ENTRIES and p["kind"] != "th") or \
                not (p.get("colorbar") or {}).get("show", True):
            continue
        fill = next((lay for lay in _panel_layers(p) if bar_fill(lay)), None)
        if fill is None:
            continue
        g, mode = _bar_group(spec, p, fill, modes)
        if mode != "none" or g == ("figure",):
            groups.setdefault(g, []).append(p["id"])
            of[p["id"]] = g
    return {i: groups[g] for i, g in of.items()}


def _extends(spec, data):
    """{panel id: colorbar ends of its first fill}: the ends of all first fills that
    share a colorbar (the block's colorbar mode: shared, row, col; "figure": all
    blocks'; bar_key) united."""
    modes = _block_modes(spec)
    groups, first = {}, {}
    for p in spec["panels"]:
        d = (data or {}).get(p["id"])
        if d is None or d.get("missing") or p["kind"] in ENTRIES or \
                not (p.get("colorbar") or {}).get("show", True):
            continue
        at = next((j for j, lay in enumerate(_panel_layers(p))
                   if lay["type"] == "fill" and lay.get("on", True)
                   and d.get(f"L{j}") is not None), None)
        if at is None:
            continue
        first_fill = _panel_layers(p)[at]
        ends = extend_of(first_fill, d[f"L{at}"])
        g = _bar_group(spec, p, first_fill, modes)[0]
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
        groups = [(used, [ml for _, _, ml in mappables])]
    elif mode in ("row", "col"):  # one colorbar per row (column) of panels
        by = {}
        for i, ax, ml in mappables:
            r, c = cell(i)
            by.setdefault(r if mode == "row" else c, []).append((ax, ml))
        groups = [([a for a, _ in items], [ml for _, ml in items]) for items in by.values()]
    else:
        groups = [(ax, [ml]) for _, ax, ml in mappables]
    for axes, mls in groups:
        m, lay = mls[0]
        c = fig.colorbar(m, ax=axes, extend=lay.get("extend", "neither"),
                         aspect=_cbar_aspect(axes, kw, orient), **kw)
        _cbar_style(c, cb, bar_layer([ml[1] for ml in mls]), loc)


def bar_layer(lays):
    """The layer a colorbar shared by layers lays speaks for: the first, with the first
    label and ticks any of them sets (a label on any panel's card reaches their bar)."""
    return dict(lays[0], **{k: next((lay[k] for lay in lays if lay.get(k)), "")
                            for k in ("cbar_label", "cbar_ticks")})


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


def ens_label(ens, units=""):
    """Colorbar text of an ensemble layer: its statistic (and units)."""
    stat = ens.get("stat", "mean")
    if stat == "prob":
        thr = float(ens.get("threshold") or 0.0)
        return f"probability {'>' if ens.get('above', True) else '<'} {thr:g}" + \
            (f" {units}" if units else "") + " (%)"
    what = {"sd": "ensemble spread (sd)", "range": "ensemble range (max − min)"}.get(
        stat, f"ensemble {stat}")
    return f"{what} ({units})" if units else what


def _cbar_style(c, cb, lay, loc):
    """Label and ticks (the layer's or series' own, else the Style tab's for every
    colorbar, else its units / automatic ticks) and fonts."""
    units = lay.get("units", "")
    if lay.get("reduce"):  # (a time window)
        units = reduce_label(lay["reduce"], units)
    if lay.get("ens"):  # (a statistic over several runs)
        units = ens_label(lay["ens"], units)
    elif lay.get("minus"):  # (a difference)
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
