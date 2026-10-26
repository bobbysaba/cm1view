"""The figure: blocks of panels, each panel's layers, labels and annotations."""

import numpy as np
import matplotlib
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Patch, Rectangle

from .base import (RC_LOCK, ENTRIES, _anchored, ann_on, panel_letter, time_text, _new_fig,
                   _fs, _cell, rc, anchor_kw, font_size, run_code, run_color, layer_color)
from .v2 import (upgrade, block_view, panel_view, block_shares, _panel_layers, _z_text,
                 LEGEND_OPTS)
from .layers import (_fill, _contour, _shade, _vectors, extend_of, union_extend, _extends,
                     _ticks, _colorbars, _cbar_style, _contour_key)
from .lines import _lines, _dists
from .sounding import _sounding, shared_hodo_half


def draw(spec, data, ends=None):
    """The matplotlib Figure of `spec` (either version) with arrays `data` (see the
    module notes); `ends` ({(panel id, layer): colorbar ends}, fill_ends) fixes the
    "auto" ends of those fills (an animation's, the same in every frame).  Save it
    with save(), which keeps the spec's fonts for what matplotlib draws late (tick
    labels)."""
    spec, data = upgrade(spec, data)
    if ends:
        spec = dict(spec, panels=[dict(p, layers=[
            dict(lay, extend=ends[(p["id"], j)]) if (p["id"], j) in ends else lay
            for j, lay in enumerate(p.get("layers") or [])]) for p in spec["panels"]])
    with RC_LOCK:
        return _draw2(spec, data)


def fill_ends(spec, data, ends=None):
    """{(panel id, layer): colorbar ends} of the fills with "auto" ends (extend_of),
    united with `ends` (another frame's: an animation's ends are those of all its
    frames)."""
    spec, data = upgrade(spec, data)
    out = dict(ends or {})
    for p in spec["panels"]:
        d = (data or {}).get(p["id"])
        if d is None or d.get("missing") or p["kind"] in ENTRIES:
            continue
        for j, lay in enumerate(_panel_layers(p)):
            a = d.get(f"L{j}")
            if lay["type"] == "fill" and lay.get("on", True) and a is not None and \
                    lay.get("extend") == "auto":
                out[(p["id"], j)] = union_extend([extend_of(lay, a),
                                                  out.get((p["id"], j), "neither")])
    return out


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
    used, placed, mappables, entries = [], [], [], {}
    share = bv.get("axes", {}).get("share", "none")
    half = share != "none" and shared_hodo_half(
        [(data[p["id"]], panel_view(spec, p, bv).get("skewt", {}))
         for p in pans if p["kind"] == "sounding" and p["id"] in data])
    for p in pans:
        r, c, rs, cs = _cell(p)
        d = data.get(p["id"]) if data is not None else None
        if d is None:
            continue
        ax = grid[r * cols + c] if grid is not None else \
            fig.add_subplot(gs[r:r + rs, c:c + cs])
        V = panel_view(spec, p, bv)
        if half and p["kind"] == "sounding":
            V = dict(V, skewt=dict(V.get("skewt", {}), _hodo_half=half))
        used.append(ax)
        ax, m = _panel(fig, ax, d, V, _panel_layers(p), fs, entries.setdefault(p["id"], {}),
                       ext.get(p["id"]))
        used[-1] = ax
        if grid is not None:
            grid[r * cols + c] = ax
        if m is not None and (p.get("colorbar") or {}).get("show", True):
            mappables.append((p["id"], ax, m))
        letter = p.get("letter")
        _decorate(ax, d, V, fs, p.get("title") or "",
                  order[id(p)] if letter is None else int(letter), _z_text(V, p), p["id"])
        placed.append((p, ax, V))
        if getattr(ax, "_cv_hodo", False) and cols > 1:
            # equal axes are squares in the middle of a wider cell: pack the outer columns
            # towards the middle, so the spacing between columns shows
            ax.set_anchor("E" if c == 0 else "W" if c + cs >= cols else "C")
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
    _share_limits(placed, data, share)
    _ticks(cells, used, bv.get("axes", {}))
    _legends(fig, bv, placed, entries)
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


def _style_key(h):
    """What makes two legend handles look alike (so the same entry of two panels is
    listed once)."""
    out = [type(h).__name__]
    for name in ("get_color", "get_linewidth", "get_linestyle", "get_facecolor",
                 "get_edgecolor", "get_alpha", "get_marker"):
        get = getattr(h, name, None)
        out.append(repr(get()) if callable(get) else "")
    return tuple(out)


def _legends(fig, bv, placed, entries):
    """The block's legend (bv["legend"]): the layer entries of its panels
    (entries[panel id] = {text: handle}) in one panel's axes ("where": "panel", at
    "panel"), or on the figure ("figure": gathering also the legends of the panels' own),
    at "loc" (and "anchor" [x, y]: base.anchor_kw).  "panels" (0-based, blank: all but
    those keeping their own) are the panels it draws from; the same text and look is
    listed once.  A panel's own legend goes under a figure legend, or with "own" False,
    unless the panel keeps it (its Tree legend "on": legend_keep)."""
    lg = bv.get("legend", {})
    if not placed:
        return
    on_fig = lg.get("where") == "figure"
    host = placed[min(max(int(lg.get("panel", 0)), 0), len(placed) - 1)][1]

    def keeps(i):  # (a panel whose own legend stays)
        p, _, V = placed[i]
        return bool((V.get(LEGEND_OPTS.get(p.get("kind"), ("",))[0]) or {}).get("legend_keep"))

    pick = [i for i in (lg.get("panels") or []) if 0 <= int(i) < len(placed)] or \
        [i for i in range(len(placed)) if not (on_fig and keeps(i))]
    handles, labels, seen = [], [], set()

    def add(h, text):
        key = (text, _style_key(h))
        if key not in seen:
            seen.add(key)
            handles.append(h)
            labels.append(text)

    own = [(placed[i][1], placed[i][0]["id"]) for i in pick]
    if not on_fig and host not in [a for a, _ in own]:
        own.append((host, None))  # (a panel's legend the block's would replace)

    def axes(ax):  # (a panel's axes, and those beside them: a sounding's hodograph)
        return [ax] + getattr(ax, "_cv_more", [])

    for ax, pid in own:
        if on_fig or ax is host:
            for a in axes(ax):
                for h, text in getattr(a, "_cv_entries", ()):
                    add(h, text)
        for text, h in entries.get(pid, {}).items():
            add(h, text)
    if on_fig or lg.get("own", True) is False:  # (panels' own legends off, but kept ones)
        for i, (_, ax, _) in enumerate(placed):
            for a in [] if keeps(i) else axes(ax):
                if a.get_legend() is not None:
                    a.get_legend().remove()
    if not handles or (not on_fig and not any(entries.get(pid) for _, pid in own)):
        return  # (nothing, or only panels' own legends, which stay)
    loc, anchor = lg.get("loc", "upper right"), lg.get("anchor")
    kw = dict(fontsize=font_size(bv, "legend"), ncol=int(lg.get("ncol", 1) or 1),
              frameon=lg.get("frame", True), framealpha=0.85, title=lg.get("title") or None,
              title_fontsize=font_size(bv, "legend"))
    if on_fig:
        fig.legend(handles, labels, **anchor_kw(loc, anchor), **kw)
    else:  # (the "outside" places belong to the figure's legend)
        host.legend(handles, labels, **anchor_kw(
            "best" if loc.startswith("outside") and not anchor else loc, anchor), **kw)


def _share_limits(placed, data, share):
    """share "x", "y" or "both": the panels of a kind (not soundings: their views are
    shared in _block) take the union of their limits, as sharex / sharey would."""
    if share not in ("x", "y", "both"):
        return
    for kind in {p["kind"] for p, _, _ in placed if p["kind"] != "sounding"}:
        axs = [ax for p, ax, _ in placed if p["kind"] == kind
               and not data[p["id"]].get("missing") and not getattr(ax, "_cv_hodo", False)]
        for name in ("x", "y"):
            if share not in (name, "both") or len(axs) < 2:
                continue
            lims = [getattr(ax, f"get_{name}lim")() for ax in axs]
            lo, hi = min(min(l) for l in lims), max(max(l) for l in lims)
            for ax, l in zip(axs, lims):
                getattr(ax, f"set_{name}lim")((hi, lo) if l[0] > l[1] else (lo, hi))


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
        nkey = 0  # vector key arrows so far
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
                _vectors(ax, d, j, lay, xsec, nkey)
                nkey += bool(lay.get("key")) and lay.get("style") != "streamlines"
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
        _extremes(ax, d, spec, layers, fs)
    return ax, m


EXTREME_TYPES = ("fill", "contour", "shade")


def extremes_layer(ex, layers):
    """The layer whose maximum and minimum a panel shows: layer ex["layer"] (a fill,
    contour or shade), else its first fill that is on, else its first such layer."""
    k = int(ex.get("layer", -1))
    if 0 <= k < len(layers) and layers[k]["type"] in EXTREME_TYPES:
        return k
    on = [j for j, l in enumerate(layers) if l["type"] in EXTREME_TYPES and l.get("on", True)]
    return next((j for j in on if layers[j]["type"] == "fill"), on[0] if on else None)


def panel_extremes(d, j):
    """((max, x, y), (min, x, y)) of layer j's array in panel data d within the
    panel's window (d["xlim"], d["ylim"]; None: nothing finite there)."""
    a = d.get(f"L{j}")
    if a is None:
        return None
    a = np.asarray(a, dtype=float)
    x = np.asarray(d.get(f"L{j}_cx", d["x"]), dtype=float)
    y = np.asarray(d.get(f"L{j}_cy", d["y"]), dtype=float)
    if x.ndim == 1 and y.ndim == 1:
        x, y = np.meshgrid(x, y)
    if x.shape != a.shape or y.shape != a.shape:
        return None
    ok = np.isfinite(a)
    for lim, c in (("xlim", x), ("ylim", y)):
        if lim in d:
            lo, hi = sorted(float(v) for v in d[lim])
            ok &= (c >= lo) & (c <= hi)
    if not ok.any():
        return None
    v = np.where(ok, a, np.nan)
    i, k = np.nanargmax(v), np.nanargmin(v)
    return ((float(v.flat[i]), float(x.flat[i]), float(y.flat[i])),
            (float(v.flat[k]), float(x.flat[k]), float(y.flat[k])))


def _extremes(ax, d, spec, layers, fs):
    """spec["extremes"]: a layer's maximum and / or minimum over the panel's window in
    a corner ("max 32.1, min −8.4 m/s"), with markers where they are."""
    ex = spec.get("extremes", {})
    if not ex.get("on"):
        return
    j = extremes_layer(ex, layers)
    r = None if j is None else panel_extremes(d, j)
    if r is None:
        return
    what = ex.get("what", "both")
    pick = [("max", r[0])] * (what in ("max", "both")) + [("min", r[1])] * (what in ("min", "both"))
    units = layers[j].get("units", "")
    txt = ", ".join(f"{w} {v:.3g}" for w, (v, _, _) in pick) + (f" {units}" if units else "")
    _anchored(ax, txt, dict(loc=ex.get("loc", "upper right"), box=ex.get("box", True),
                            bold=False, size=ex.get("size")), fs)
    if ex.get("marker", True):
        for w, (_, x, y) in pick:
            ax.plot(x, y, marker="+" if w == "max" else "x", ms=8, mew=1.5,
                    color=ex.get("color", "k"), zorder=5, clip_on=True)


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
    panel; a list: those panels), in data coordinates or as fractions of the panel (coords 'axes').  In a
    skew-T, data coordinates are temperature (deg C) and pressure (hPa)."""
    skew = getattr(ax, "_cv_skew", None)
    for a in anns:
        if not ann_on(a, i):
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
