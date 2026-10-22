"""The figure: blocks of panels, each panel's layers, labels and annotations."""

import numpy as np
import matplotlib
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Patch, Rectangle

from .base import (RC_LOCK, _anchored, panel_letter, time_text, _new_fig, _fs, _cell, rc,
                   font_size, run_code, run_color, layer_color)
from .v2 import upgrade, block_view, panel_view, block_shares, _panel_layers, _z_text
from .layers import (_fill, _contour, _shade, _vectors, extend_of, _extends, _ticks,
                     _colorbars, _cbar_style, _contour_key)
from .lines import _lines, _dists
from .sounding import _sounding

def draw(spec, data):
    """The matplotlib Figure of `spec` (either version) with arrays `data` (see the
    module notes).  Save it with save(), which keeps the spec's fonts for what
    matplotlib draws late (tick labels)."""
    spec, data = upgrade(spec, data)
    with RC_LOCK:
        return _draw2(spec, data)


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
