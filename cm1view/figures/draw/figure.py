"""The figure: blocks of panels, each panel's layers, labels and annotations."""

from contextlib import nullcontext

import numpy as np
import matplotlib
from matplotlib.collections import Collection
from matplotlib.colors import to_rgba
from matplotlib.contour import ContourSet
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnchoredOffsetbox
from matplotlib.patches import Circle, ConnectionPatch, Patch, Rectangle
from matplotlib.text import Text

from .base import (RC_LOCK, ENTRIES, _anchored, ann_on, legend_handles, panel_letter,
                   time_text, _new_fig, _fs, _cell, grid_layout, rc, anchor_kw, font_size,
                   run_code, run_color, layer_color, run_time_opts)
from .v2 import (upgrade, block_view, panel_view, block_shares, _panel_layers, _z_text,
                 LEGEND_OPTS)
from .v3 import inset_panel
from .layers import (_fill, _contour, _shade, _vectors, _parcels, parcel_label,
                     sector_outline, extend_of,
                     union_extend, _extends, _ticks, _colorbars, _cbar_style, bar_layer,
                     _contour_key, _mixed_kinds, bar_key)
from .lines import (_lines, _dists, _profiles, _joints, _azims, azim_range, dist_edges,
                    dist_hist, dist_of, joint_edges, joint_hist, joint_of)
from .sounding import _sounding, _hodo_view, shared_hodo_half, sounding_layout
from .tables import _table, _tbl_width, finish_tables
from .scene3d import scene_panel, finish_scenes, scene_dpi

MIN_LABEL_PT = 6.0  # (fit_labels)
INSET_KINDS = ("plan", "xsec")  # (the kinds with zoom insets: axes in km, arrays that can be cut)
INSET_PAD = 0.03  # (from a panel's edge, a fraction of it)
SCALE_OPTS = {"dist": "dist", "profile": "prof", "joint": "joint", "azim": "azim",
              "sounding": "skewt"}  # (a kind whose scales follow its data -> its options)


def draw(spec, data, ends=None):
    """The matplotlib Figure of `spec` (either version) with arrays `data` (see the
    module notes); `ends` ({(panel id, layer): colorbar ends}, fill_ends; and
    {(panel id, "opts"): options}, fit_scales) fixes the "auto" ends of those fills and
    the scales of those panels (an animation's, the same in every frame).  Save it
    with save(), which keeps the spec's fonts for what matplotlib draws late (tick
    labels)."""
    spec, data = upgrade(spec, data)
    if ends:
        spec = dict(spec, panels=[dict(_with_scales(p, ends), layers=[
            dict(lay, extend=ends[(p["id"], j)]) if (p["id"], j) in ends else lay
            for j, lay in enumerate(p.get("layers") or [])]) for p in spec["panels"]])
    with RC_LOCK:
        return _draw2(spec, data)


def _with_scales(p, ends):
    fit = ends.get((p["id"], "opts"))
    if not fit:
        return p
    opts = dict(p.get("opts") or {})
    for k, v in fit.items():
        opts[k] = dict(opts.get(k) or {}, **v)
    return dict(p, opts=opts)


def _scales_free(V):
    """Whether panel view V has scales that follow its data, frame by frame."""
    kind = V["kind"]
    if kind != "sounding":
        return kind in SCALE_OPTS
    o = V.get("skewt", {})
    return o.get("hodo_center") == "fit" and sounding_layout(o) != "skewt"


def scales_free(spec):
    """Whether an animation of `spec` needs fit_scales to keep its scales still."""
    spec = upgrade(spec)[0]
    return any(_scales_free(panel_view(spec, p)) for p in spec["panels"])


def fill_ends(spec, data, ends=None):
    """{(panel id, layer): colorbar ends} of the fills with "auto" ends (extend_of),
    united with `ends` (another frame's: an animation's ends are those of all its
    frames); {(panel id, "frames"): each frame's panel arrays} of the panels with free
    scales (_scales_free), for fit_scales once all the frames are read."""
    spec, data = upgrade(spec, data)
    out = dict(ends or {})
    for p in spec["panels"]:
        d = (data or {}).get(p["id"])
        if d is None or d.get("missing"):
            continue
        if p["kind"] in ENTRIES:
            if _scales_free(panel_view(spec, p)):
                out[(p["id"], "frames")] = out.get((p["id"], "frames"), []) + [d]
            continue
        for j, lay in enumerate(_panel_layers(p)):
            a = d.get(f"L{j}")
            if lay["type"] == "fill" and lay.get("on", True) and a is not None and \
                    lay.get("extend") == "auto":
                out[(p["id"], j)] = union_extend([extend_of(lay, a),
                                                  out.get((p["id"], j), "neither")])
    return out


def fit_scales(spec, ends):
    """`ends` (fill_ends, all frames read) with each panel's frames replaced by
    {(panel id, "opts"): {options group: limits}}: the scales that hold all its frames,
    so they stay still in an animation.  Limits set in the spec stay."""
    spec = upgrade(spec)[0]
    out = dict(ends)
    for p in spec["panels"]:
        frames = out.pop((p["id"], "frames"), None)
        if frames:
            group = SCALE_OPTS[p["kind"]]
            o = panel_view(spec, p).get(group, {})
            out[(p["id"], "opts")] = {group: _frame_scales(p["kind"], o, frames)}
    return out


def _free(o, **limits):
    """The limits not already set in options o."""
    return {k: float(v) for k, v in limits.items() if o.get(k) in (None, "")}


def _padded(a, b, frac=0.05):
    pad = frac * (b - a)
    return a - pad, b + pad


def _frame_scales(kind, o, frames):
    """The options (limits) that hold every frame's arrays of a panel of `kind`."""
    def num(k):
        v = o.get(k)
        return None if v in (None, "") else float(v)

    if kind == "dist":
        sts = [dist_of(d, j) for d in frames for j in range(int(d.get("ndist", 0)))]
        plot, logy = o.get("plot", "hist"), bool(o.get("logy"))
        edges = dist_edges(sts, o.get("bins", 50), num("width"), num("xmin"), num("xmax"))
        a, b = float(edges[0]), float(edges[-1])
        if plot not in ("hist", "ecdf"):  # (box, violin: room around the extremes)
            a, b = (a, b * 1.1 if b > 0 else b) if logy else _padded(a, b)
        fit = _free(o, xmin=a, xmax=b)
        if plot == "hist":
            edges = dist_edges(sts, o.get("bins", 50), num("width"), fit.get("xmin", a),
                               fit.get("xmax", b))
            v = np.concatenate([np.ravel(dist_hist(s, edges, o.get("norm", "count")))
                                for s in sts] or [[]])
            v = v[np.isfinite(v) & (v > 0)]
            if v.size and logy:
                fit.update(_free(o, ymin=v.min() * 0.7, ymax=v.max() * 1.4))
            elif v.size:
                room = 1.25 if o.get("bar_labels") else 1.05
                fit.update(_free(o, ymin=0.0, ymax=v.max() * room))
        return fit
    if kind == "profile":
        v = [np.ravel(np.asarray(d[f"P{j}_{k}"], dtype=float)) for d in frames
             for j in range(int(d.get("nprof", 0))) for k in ("v", "lo", "hi")
             if f"P{j}_{k}" in d]
        v = np.concatenate(v or [[]])
        v = v[np.isfinite(v)]
        return _free(o, **dict(zip(("xmin", "xmax"), _padded(v.min(), v.max())))) \
            if v.size and v.max() > v.min() else {}
    if kind == "joint":
        ends = [(num(k + "min"), num(k + "max")) for k in "xy"]
        per = [[joint_of(d, j) for j in range(int(d.get("njoint", 0)))] for d in frames]
        ex, ey = joint_edges([s for ss in per for s in ss], o.get("bins", 60), *ends[0], *ends[1])
        fit = _free(o, xmin=ex[0], xmax=ex[-1], ymin=ey[0], ymax=ey[-1])
        v = np.concatenate([np.ravel(joint_hist(ss[0], ex, ey, o.get("norm", "count")))
                            for ss in per if ss] or [[]])
        v = v[v > 0]
        if o.get("plot", "hist") == "hist" and v.size:
            fit.update(_hmin=float(v.min()), _hmax=float(v.max()))
        return fit
    if kind == "azim":
        rs = [azim_range(np.asarray(d["A0_v"]), o, bool(int(d.get("A0_div", 0))))
              for d in frames if int(d.get("nazim", 0))]
        return _free(o, vmin=min(r[0] for r in rs), vmax=max(r[1] for r in rs)) if rs else {}
    top, hm = float(o.get("hodo_top", 9.0)), float(o.get("hodo_max", 40.0))  # (a hodograph)
    vs = [_hodo_view(d, int(d["nsnd"]), o, top, hm, str(o.get("srh") or "")) for d in frames
          if int(d.get("nsnd", 0))]
    if not vs:
        return {}
    u0, u1 = min(c - h for c, _, h in vs), max(c + h for c, _, h in vs)
    v0, v1 = min(c - h for _, c, h in vs), max(c + h for _, c, h in vs)
    return dict(hodo_center="custom", hodo_cu=0.5 * (u0 + u1), hodo_cv=0.5 * (v0 + v1),
                hodo_max=float(5.0 * np.ceil(0.5 * max(u1 - u0, v1 - v0) / 5.0)))


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
            fit_labels(fig)
            _on_dark(fig, spec)
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
    if spec.get("arrange") == "grid":
        subs = _grid_subfigures(host, spec)
    else:
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
        own = [block_view(spec, k).get("colorbar") or {} for k in range(len(blocks))]
        words = {k: cb.get(k) or next((o[k] for o in own if o.get(k)), "")
                 for k in ("label", "ticks")}  # (the Style tab's of any part)
        with matplotlib.rc_context(rc(block_view(spec, 0))):
            _cbar_style(c, dict(cb, **words), bar_layer([ml[1] for _, _, ml in mappables]), loc)
    if spec.get("suptitle"):
        fig.suptitle(spec["suptitle"], weight="bold", fontsize=font_size(spec, "suptitle"))
    with matplotlib.rc_context(rc(spec)):
        fit_labels(fig)
    _on_dark(fig, spec)
    code = spec.get("code") or {}
    if code.get("on") and str(code.get("text") or "").strip():
        run_code(fig, [fig._cv_axes[i] for i in sorted(fig._cv_axes)], data, spec,
                 code["text"])
    return fig


def _grid_subfigures(host, spec):
    """A subfigure of `host` for each block, in the cells grid_layout gives it."""
    g = grid_layout(spec["blocks"], spec.get("part_grid"))
    gs = host.add_gridspec(g["rows"], g["cols"], width_ratios=g["width_ratios"],
                           height_ratios=g["height_ratios"], left=0, right=1, bottom=0, top=1)
    return [host.add_subfigure(gs[r:r + rs, c:c + cs]) for r, c, rs, cs in g["places"]]


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
    own = spec.get("groups") or {}
    names = list(dict.fromkeys(p.get("group") for p in pans)) or [None]

    def gview(name):  # (a group's settings apart from the others')
        return dict(bv, **own[name]) if name in own else bv

    half = {}
    for name in names:
        snd = [p for p in pans if p["kind"] == "sounding" and p.get("group") == name]
        axes = gview(name).get("axes", {})
        if snd and {p["kind"] for p in pans if p.get("group") == name} != {"sounding"}:
            axes = panel_view(spec, snd[0], bv).get("axes", {})  # (kinds mixed: the soundings')
        half[name] = axes.get("share", "none") != "none" and \
            shared_hodo_half([(data[p["id"]], panel_view(spec, p, bv).get("skewt", {}))
                              for p in snd if p["id"] in data])
    for p in pans:
        r, c, rs, cs = _cell(p)
        d = data.get(p["id"]) if data is not None else None
        if d is None:
            continue
        ax = grid[r * cols + c] if grid is not None else \
            fig.add_subplot(gs[r:r + rs, c:c + cs])
        V = panel_view(spec, p, bv)
        if half[p.get("group")] and p["kind"] == "sounding":
            V = dict(V, skewt=dict(V.get("skewt", {}), _hodo_half=half[p.get("group")]))
        used.append(ax)
        extra = legend_handles(V.get("annotations", []), p["id"])
        if p["kind"] in LEGEND_OPTS:  # (into the panel's own legend)
            V = dict(V, _legend_extra=extra)
        if p["kind"] == "scene" and not own and len(pans) > 1:  # (its bars: to fit its cell)
            V = dict(V, _cell_in=_cell_inches(fig, b, r, c, rs, cs))
        font = "font" in (p.get("opts") or {})  # (fonts of its own: a part's, converted)
        pfs = _fs(V) if font else fs
        with matplotlib.rc_context(rc(V)) if font else nullcontext():
            if font:
                ax.tick_params(labelsize=font_size(V, "tick"))
            ax, m = _panel(fig, ax, d, V, _panel_layers(p), pfs, entries.setdefault(p["id"], {}),
                           ext.get(p["id"]))
        if p["kind"] not in LEGEND_OPTS:  # (after its layers' entries, in the block's legend)
            entries[p["id"]].update(extra)
        used[-1] = ax
        if grid is not None:
            grid[r * cols + c] = ax
        if m is not None and (p.get("colorbar") or {}).get("show", True):
            mappables.append((p["id"], ax, m))
        letter = p.get("letter")
        with matplotlib.rc_context(rc(V)) if font else nullcontext():
            _decorate(ax, d, V, pfs, p.get("title") or "",
                      order[id(p)] if letter is None else int(letter), _z_text(V, p), p["id"])
            if p.get("rowlabel"):
                _row_label(ax, p["rowlabel"], V, pfs)
            _insets(fig, ax, spec, p, V, d, data, pfs, entries[p["id"]], bv)
        placed.append((p, ax, V))
        if getattr(ax, "_cv_hodo", False) and cols > 1:
            # equal axes are squares in the middle of a wider cell: pack the outer columns
            # towards the middle, so the spacing between columns shows
            ax.set_anchor("E" if c == 0 else "W" if c + cs >= cols else "C")
    if grid is not None:
        for ax in grid:
            if ax not in used:
                ax.set_visible(False)
    mixed = _mixed_kinds(spec, k)
    for name in names:  # (tick labels, limits and legend within the group)
        gv, mine = gview(name), [x for x in placed if x[0].get("group") == name]
        kinds = list(dict.fromkeys(x[0]["kind"] for x in mine))
        if len(kinds) > 1:  # (each kind's ticks, limits and outer labels are its own)
            for kind in kinds:
                these = [x for x in mine if x[0]["kind"] == kind]
                _axes_of(these, data, rows, min(_cell(x[0])[1] for x in these),
                         these[0][2].get("axes", {}))
        else:
            _axes_of(mine, data, rows, min((_cell(p)[1] for p, _, _ in mine), default=0)
                     if name in own else 0, gv.get("axes", {}))
        _legends(fig, gv, mine, entries, mixed)
    for _, ax, _ in placed:  # (the panels' limits are final now)
        for mark in getattr(ax, "_cv_marks", ()):
            _inset_mark(ax, *mark)
    fig._cv_mappables = mappables
    where = {p["id"]: _cell(p)[:2] for p in pans}
    if bv.get("colorbar", {}).get("mode") == "groups":
        for name in names:
            mine = [p["id"] for p in pans if p.get("group") == name]
            _colorbars(fig, gview(name).get("colorbar") or {},
                       [m for m in mappables if m[0] in mine],
                       [ax for p, ax, _ in placed if p["id"] in mine], lambda i: where[i])
    else:
        _bars(fig, bv.get("colorbar", {}), mappables, placed, used, mixed, lambda i: where[i])
    for name in names:
        gv, mine = gview(name), [p for p in pans if p.get("group") == name]
        ck = gv.get("contour_key", {})
        keyp = next((p for p in mine if p["id"] == ck.get("panel")), None) or next(
            (p for p in mine if any(lay.get("type") == "contour" for lay in p.get("layers") or [])),
            mine[0] if mine else None)
        _contour_key(fig, gv, _fs(gv), keyp.get("layers", []) if keyp else [])
    finish_scenes(fig, scene_dpi(spec))
    fig._cv_axes = {p["id"]: ax for p, ax, _ in placed}  # (panel -> axes)
    fig._cv_grid = grid if grid is not None else [ax for _, ax, _ in placed]
    opts = b.get("opts") or {}
    if opts.get("suptitle"):
        fig.suptitle(opts["suptitle"], weight="bold", fontsize=font_size(bv, "suptitle"))
    finish_tables(fig)
    code = opts.get("code") or {}
    if code.get("on") and str(code.get("text") or "").strip():
        run_code(fig, fig._cv_grid, {p["id"]: data[p["id"]] for p, _, _ in placed}, bv,
                 code["text"])


def inset_limits(ins, d):
    """((x0, x1), (y0, y1)) an inset shows, in its axis units, with its arrays d, or None: where its
    window was read (a plan view's), cut to its "view" (a cross-section's: the arrays are the
    section's)."""
    view = ins.get("view")
    if view and None not in view:
        return tuple(float(v) for v in view[:2]), tuple(float(v) for v in view[2:4])
    if d.get("missing") or "xlim" not in d or "ylim" not in d:
        return None
    return tuple(float(v) for v in d["xlim"]), tuple(float(v) for v in d["ylim"])


def inset_rect(ins, lims, panel_lims, equal):
    """[x, y, width, height] of an inset, fractions of its panel: "loc" a corner, or "custom" (its
    lower left at "x", "y"); "size" its width; "h" its height, else as tall as what it shows is
    on the panel's scale (equal: a plan view's km are square), else square in fractions."""
    w = float(ins.get("size") or 0.4)
    h = ins.get("h")
    if h not in (None, ""):
        h = float(h)
    elif equal and lims and panel_lims:
        (a0, a1), (b0, b1) = lims
        (c0, c1), (e0, e1) = panel_lims
        h = w * abs((b1 - b0) / (a1 - a0)) * abs((c1 - c0) / (e1 - e0))
    else:
        h = w
    most = 1.0 - 2.0 * INSET_PAD
    if max(w, h) > most:  # (it stays inside its panel, and its shape)
        w, h = w * most / max(w, h), h * most / max(w, h)
    loc = ins.get("loc") or "upper right"
    if loc == "custom":
        return [float(ins.get("x", INSET_PAD)), float(ins.get("y", INSET_PAD)), w, h]
    return [INSET_PAD if "left" in loc else 1.0 - INSET_PAD - w,
            INSET_PAD if "lower" in loc else 1.0 - INSET_PAD - h, w, h]


def _inset_shift(d, cd):
    """What to add to an inset's axis units for its panel's (their origins differ: an inset with
    other coordinates than its panel's)."""
    if "origin" not in d or "origin" not in cd:
        return 0.0, 0.0
    return tuple(float(a) - float(b) for a, b in zip(cd["origin"], d["origin"]))


def inset_lines(rect, box):
    """Which corners to join, as [(corner of the box, corner of the inset)], each corner (0 or 1 from
    the left, 0 or 1 from the bottom), for an inset at `rect` and a box at `box` ([x, y, width,
    height] alike): two lines that keep clear of both, or as near as an overlap allows."""
    def apart(a, a1, b, b1):  # (b is after a: 1; before it: -1; they overlap: 0)
        return 1 if b >= a1 else -1 if b1 <= a else 0

    dx = apart(box[0], box[0] + box[2], rect[0], rect[0] + rect[2])
    dy = apart(box[1], box[1] + box[3], rect[1], rect[1] + rect[3])
    if dx and not dy:  # (beside it: the sides facing each other)
        return [(((dx + 1) // 2, e), ((1 - dx) // 2, e)) for e in (0, 1)]
    if dy and not dx:  # (above or below it)
        return [((e, (dy + 1) // 2), (e, (1 - dy) // 2)) for e in (0, 1)]
    if not dx:  # (over it: by where the middles are)
        dx = 1 if rect[0] + 0.5 * rect[2] >= box[0] + 0.5 * box[2] else -1
        dy = 1 if rect[1] + 0.5 * rect[3] >= box[1] + 0.5 * box[3] else -1
    return [((0, 1), (0, 1)), ((1, 0), (1, 0))] if dx * dy > 0 else \
        [((0, 0), (0, 0)), ((1, 1), (1, 1))]


def _inset_mark(ax, ins, cax, rect, lims, shift, color):
    """The box in the panel over what inset cax (at `rect`) shows, and the lines from it to the
    inset, inside the panel's limits as they finally are: what shows beyond them has no place in
    it.  None of it moves the panel, or says how much room the figure needs."""
    if ins.get("mark", True) is False or not lims:
        return
    (x0, x1), (y0, y1) = lims
    (c0, c1), (e0, e1) = sorted(ax.get_xlim()), sorted(ax.get_ylim())
    x0, x1 = max(x0 + shift[0], c0), min(x1 + shift[0], c1)
    y0, y1 = max(y0 + shift[1], e0), min(y1 + shift[1], e1)
    if x1 <= x0 or y1 <= y0 or (x0, x1, y0, y1) == (c0, c1, e0, e1):
        return  # (nothing of it in the panel; all of the panel: an overview, not a zoom)
    look = dict(edgecolor=color, linewidth=float(ins.get("lw", 1.0)), linestyle=ins.get("ls", "-"),
                zorder=4.99, clip_on=False, in_layout=False)
    ax.add_artist(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, **look))
    if ins.get("connect", True) is False:
        return
    box = [(x0 - c0) / (c1 - c0), (y0 - e0) / (e1 - e0), (x1 - x0) / (c1 - c0), (y1 - y0) / (e1 - e0)]
    for (u, w), at_inset in inset_lines(rect, box):
        ax.add_artist(ConnectionPatch((x0 + u * (x1 - x0), y0 + w * (y1 - y0)), at_inset,
                                      ax.transData, cax.transAxes, **look))


def _insets(fig, ax, spec, p, V, d, data, fs, legend, bv):
    """Panel p's zoom insets, in its axes ax: each a small panel of its own arrays (panel_view of
    inset_panel, data[negative of its id]) with no labels, a frame, and a box and lines in the panel
    (spec.doc has what an inset holds).  What a panel's labels say holds for its insets; a
    colorbar is the panel's; a layer of the inset's own names itself in the panel's legend."""
    if p["kind"] not in INSET_KINDS or d.get("missing"):
        return
    for ins in p.get("insets") or []:
        q = inset_panel(p, ins)
        cd = data.get(q["id"])
        if cd is None:
            continue
        IV = dict(panel_view(spec, q, bv), extremes={})
        # (a vector key is the panel's, as its colorbar; an own layer's stays with it)
        lays = _panel_layers(q) if ins.get("layers") is not None else \
            [dict(lay, key=False) for lay in _panel_layers(q)]
        lims = inset_limits(ins, cd)
        equal = p["kind"] == "plan" and V.get("axes", {}).get("equal", True)
        rect = inset_rect(ins, lims, (d["xlim"], d["ylim"]) if "xlim" in d else None, equal)
        cax = ax.inset_axes(rect)
        cax.set_in_layout(False)
        color = ins.get("color") or ("white" if spec.get("mplstyle") == "dark_background"
                                     else "black")
        _panel(fig, cax, cd, IV, lays, fs, legend)
        if lims:
            cax.set_xlim(*lims[0])
            cax.set_ylim(*lims[1])
        if equal:
            cax.set_aspect("equal")
        if ins.get("ticks"):
            cax.tick_params(labelsize=0.8 * font_size(V, "tick"), length=2.0, pad=1.5)
        else:
            cax.set_xticks([])
            cax.set_yticks([])
        for spine in cax.spines.values():
            spine.set_edgecolor(color)
            spine.set_linewidth(float(ins.get("lw", 1.0)))
        shift = _inset_shift(d, cd)
        if shift == (0.0, 0.0):  # (annotations are in the panel's axis units)
            _annotate(cax, p["id"], [a for a in V.get("annotations", [])
                                     if a.get("coords") != "axes"], fs)
        ax.__dict__.setdefault("_cv_insets", {})[q["id"]] = cax
        ax.__dict__.setdefault("_cv_marks", []).append((ins, cax, rect, lims, shift, color))


def _cell_inches(fig, b, r, c, rs, cs):
    """(width, height) in inches of cells of block b, by their shares (before any gaps)."""
    W, H = fig.get_figure(root=True).get_size_inches()

    def share(vals, n, at, span):
        vals = [float(v) for v in vals or [1.0] * n]
        return sum(vals[at:at + span]) / sum(vals)

    return (float(W) * share(b.get("widths"), int(b["cols"]), c, cs),
            float(H) * share(b.get("heights"), int(b["rows"]), r, rs))


def _bars(fig, cb, mappables, placed, used, mixed, cell):
    """The colorbars of a block's panels: as its mode says, for panels that share them all; else
    a bar for each bar_key, each taking its room from the panels it speaks for, with the
    settings its first panel sees (a kind's or a panel's "colorbar" over the figure's).  A bar
    that panels name is one bar, whatever the mode."""
    views = {p["id"]: (p, V) for p, _, V in placed}
    keys = {m[0]: bar_key(views[m[0]][0], m[2][1], mixed) for m in mappables}
    if not any(keys.values()):
        _colorbars(fig, cb, mappables, used, cell)
        return
    for key in dict.fromkeys(keys.values()):
        mine = [m for m in mappables if keys[m[0]] == key]
        look = dict(cb, **(views[mine[0][0]][1].get("colorbar") or {}))
        look["mode"] = cb.get("mode", "shared")
        if key.startswith("named:") and look["mode"] != "none":
            look["mode"] = "shared"
        _colorbars(fig, look, mine, [m[1] for m in mine], cell)


def _axes_of(mine, data, rows, first, axes):
    """Shared limits and tick labels of placed panels `mine` [(panel, axes, view)]: first, the
    column their left edge counts from; axes: their axes settings."""
    occ = {(r + a, c + e) for p, _, _ in mine for r, c, rs, cs in [_cell(p)]
           for a in range(rs) for e in range(cs)}
    cells = []
    for p, ax, V in mine:
        r, c, rs, cs = _cell(p)
        cells.append((ax, c - first, r + rs >= rows or (r + rs, c) not in occ, p["kind"],
                      V.get("axes", {})))
    _share_limits(mine, data, axes.get("share", "none"))
    _ticks(cells, [ax for _, ax, _ in mine], axes)


def _row_label(ax, text, V, fs):
    """A row's label left of its first panel (beyond the y label), bold as the titles
    are."""
    bold = V.get("axes", {}).get("title_bold", True)
    ax.annotate(text, xy=(0, 0.5), xycoords=ax.yaxis.label,
                xytext=(-ax.yaxis.labelpad - 0.4 * fs, 0), textcoords="offset points",
                ha="right", va="center", rotation=90, fontsize=font_size(V, "title"),
                weight="bold" if bold else "normal")


def _style_key(h):
    """What makes two legend handles look alike (so the same entry of two panels is
    listed once)."""
    out = [type(h).__name__]
    for name in ("get_color", "get_linewidth", "get_linestyle", "get_facecolor",
                 "get_edgecolor", "get_alpha", "get_marker"):
        get = getattr(h, name, None)
        out.append(repr(get()) if callable(get) else "")
    return tuple(out)


def _scene_legend(ax, handles, labels, lg, V):
    """A 3D scene's legend when other kinds share the figure: its own, smaller, in its corner."""
    loc = lg.get("loc", "upper right")
    ax.legend(handles, labels, loc="upper right" if loc.startswith("outside") else loc,
              fontsize=0.85 * font_size(V, "legend"), frameon=lg.get("frame", True), framealpha=0.7,
              ncol=int(lg.get("ncol", 1) or 1))


def _legends(fig, bv, placed, entries, mixed=False):
    """The block's legend (bv["legend"]): the layer entries of its panels
    (entries[panel id] = {text: handle}) in one panel's axes ("where": "panel", at
    "panel"), or on the figure ("figure": gathering also the legends of the panels' own),
    at "loc" (and "anchor" [x, y]: base.anchor_kw).  "panels" (0-based, blank: all but
    those keeping their own) are the panels it draws from; the same text and look is
    listed once.  A panel's own legend goes under a figure legend, or with "own" False,
    unless the panel keeps it (its Tree legend "on": legend_keep).  mixed (kinds mixed in a
    panel's legend): it goes in a panel with entries, if the one named has none; a 3D scene keeps
    its entries in its own corner, as a map's don't explain its picture."""
    lg = bv.get("legend", {})
    if not placed:
        return
    on_fig = lg.get("where") == "figure"
    host = placed[min(max(int(lg.get("panel", 0)), 0), len(placed) - 1)][1]
    apart = []  # (scenes with a legend of their own)
    if mixed and not on_fig:
        apart = [x for x in placed if x[0]["kind"] == "scene"]
        for p, ax, V in apart:
            have = entries.get(p["id"]) or {}
            if have:
                _scene_legend(ax, list(have.values()), list(have), lg, V)
        rest = [x for x in placed if x[0]["kind"] != "scene"]
        chosen = next((x for x in rest if x[1] is host), None)
        if rest and (chosen is None or not entries.get(chosen[0]["id"])):
            host = next((ax for p, ax, _ in rest if entries.get(p["id"])), rest[0][1])

    def keeps(i):  # (a panel whose own legend stays)
        p, _, V = placed[i]
        return bool((V.get(LEGEND_OPTS.get(p.get("kind"), ("",))[0]) or {}).get("legend_keep"))

    pick = [i for i in (lg.get("panels") or []) if 0 <= int(i) < len(placed)] or \
        [i for i in range(len(placed)) if not (on_fig and keeps(i))]
    pick = [i for i in pick if not any(placed[i] is x for x in apart)]
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
    if not on_fig and any(host is x[1] for x in apart):
        return  # (a figure of scenes alone: each has its own)
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
    elif kind == "profile":
        _profiles(ax, d, spec, fs)
    elif kind == "joint":
        _joints(ax, d, spec, fs)
    elif kind == "azim":
        _azims(ax, d, spec, fs)
    elif kind == "table":
        _table(ax, d, spec)  # (its rows: finish_tables, once the figure is laid out)
    elif kind == "scene":  # (its picture: finish_scenes, once the figure is laid out)
        scene_panel(fig, ax, d, spec, fs, legend)
    else:
        xsec = kind == "xsec"
        x, y = d["x"], d["y"]
        nkey = 0  # vector key arrows so far
        pm_lay = None  # (mappable, layer) of the first parcel layer coloured by a value
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
                nkey += bool(lay.get("key")) and lay.get("style", "arrows") == "arrows"
            elif t == "track" and "track_x" in d:
                col = layer_color(spec, lay, d)
                ax.plot(d["track_x"], d["track_y"], color=col,
                        lw=float(lay.get("lw", 1.0)), ls=lay.get("ls", "-"))
                if lay.get("marker", True) and "now_x" in d:
                    ax.plot(d["now_x"], d["now_y"], marker="o", ms=4, color=col)
            elif t == "sector" and "sector" in d and not xsec:
                xy = sector_outline(d, lay)
                if xy is not None:
                    ax.plot(*xy, color=lay.get("color", "k"), lw=float(lay.get("lw", 1.5)),
                            ls=lay.get("ls", "-"))
            elif t == "line" and ("lines" in d or "line" in d):
                _section_lines(ax, d, lay, y, fs)
            elif t == "parcels":  # (its colorbar: the panel's when it has no fill)
                pm = _parcels(ax, d, j, lay)
                if pm is not None and pm_lay is None:
                    pm_lay = (pm, dict(lay, extend=lay.get("extend") or "neither",
                                       units=parcel_label(lay)))
            if lay.get("legend") and t in ("contour", "shade", "track", "line", "sector",
                                           "parcels"):
                legend[lay["legend"]] = (
                    Patch(facecolor="none" if lay.get("hatch") else lay.get("color", "magenta"),
                          alpha=float(lay.get("alpha", 0.6)), hatch=lay.get("hatch") or None,
                          edgecolor=(lay.get("outline") or lay.get("color", "magenta")
                                     if lay.get("hatch") else lay.get("outline") or "none"))
                    if t == "shade" else
                    Line2D([], [], color=layer_color(spec, lay, d),
                           lw=float(lay.get("lw", 1.0))))
        m = m or pm_lay
        _extremes(ax, d, spec, layers, fs)
    return ax, m


def _section_lines(ax, d, lay, y, fs):
    """A Section line layer: each section's line (d["lines"] rows [xa, ya, xb, yb,
    width averaged across, section index]; older data: d["line"], d["line_w"]), the
    edges of the strip a section averages, and its end labels (end_labels: A–A′,
    B–B′ ...)."""
    rows = np.atleast_2d(d["lines"]) if "lines" in d else \
        np.array([list(d["line"]) + [float(d.get("line_w", 0.0)), 0]])
    col, lw = lay.get("color", "k"), float(lay.get("lw", 2.0))
    yl = d.get("ylim", (np.nanmin(y), np.nanmax(y)))
    off = 0.02 * (yl[1] - yl[0])  # labels just above the line ends
    for xa, ya, xb, yb, wd, k in rows:
        ax.plot([xa, xb], [ya, yb], color=col, lw=lw)
        hw = 0.5 * float(wd)
        if hw > 0:  # a strip-averaged section: the strip's edges
            n = np.hypot(xb - xa, yb - ya) or 1.0
            px, py = -(yb - ya) / n * hw, (xb - xa) / n * hw
            for sg in (-1, 1):
                ax.plot([xa + sg * px, xb + sg * px], [ya + sg * py, yb + sg * py],
                        color=col, lw=0.6 * lw, ls="--")
        for (px, py, txt) in zip((xa, xb), (ya, yb), end_labels(lay.get("labels", ""), int(k))):
            ax.text(px, py + off, txt, fontsize=fs * 1.1, weight="bold", color=col,
                    ha="center", va="bottom", clip_on=True)


def end_labels(labels, k):
    """The end labels of section k: the layer's "labels" ("A, A′") for the first; for
    the others a one-letter label steps on k letters (B, B′; C, C′ ...), a longer one
    is numbered ("start 2")."""
    a, b = ([t.strip() for t in str(labels or "").split(",")] + ["", ""])[:2]

    def step(t):
        letters = [ch for ch in t if ch.isalpha()]
        if len(letters) != 1:
            return f"{t} {k + 1}" if t else t
        ch = letters[0]
        base = ord("A") if ch.isupper() else ord("a")
        return t.replace(ch, chr(base + (ord(ch) - base + k) % 26)) \
            if ch.isascii() else f"{t} {k + 1}"
    return (step(a), step(b)) if k else (a, b)


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


AUTO_XSEC_X = ("", "distance (km)", "distance from storm (km)")  # (" ": none)


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
    if not getattr(ax, "_cv_hodo", False) and kind != "scene":  # (a hodograph labels its rings)
        xl = ax_opts.get("xlabel", "")
        if kind == "xsec" and xl in AUTO_XSEC_X and d.get("xname"):
            xl = d["xname"]  # (x, y or the distance, as the panel's section runs)
        if xl or kind not in ("dist", "profile", "joint", "azim"):
            ax.set_xlabel(xl)  # (dist, ...: the field's)
        if ax_opts.get("ylabel") or kind not in ("line", "dist", "joint", "azim"):
            ax.set_ylabel(ax_opts.get("ylabel", ""))  # (time series: units)
            ax.set_ylabel(ax_opts.get("ylabel", ""))
    if title:
        ax.set_title(title, weight="bold" if ax_opts.get("title_bold", True)
                     else "normal", loc=ax_opts.get("title_loc", "center"))
    labels, tlab, rlab = (spec.get(k, {}) for k in ("letters", "time_label", "run_label"))
    if kind == "table":  # (the table fills the panel from its top)
        labels = dict(labels, loc="above left")

    def label(text, opts, color=None):
        t = _anchored(ax, text, opts, fs * 1.2, color)
        if spec.get("label_fit"):  # (fit_labels, once the figure is laid out)
            edge = str(opts.get("loc", "upper left")).split()[0]
            ax.__dict__.setdefault("_cv_labels", []).append((edge, t))

    if labels.get("on", True):
        label(panel_letter(letter, labels.get("fmt", "{a}")), labels)
    if tlab.get("on", True) and "time_s" in d:
        label(time_text(d["time_s"], run_time_opts(spec, int(d.get("run", 0)), d["time_s"])), tlab)
    zlab = spec.get("z_label", {})
    if zlab.get("on") and ztxt:
        label(ztxt, zlab)
    if rlab.get("on", True) and d.get("run_label"):
        label(str(d["run_label"]), rlab,
              run_color(spec, int(d.get("run", 0))) if rlab.get("run_color") else None)
    _annotate(ax, key, spec.get("annotations", []), fs)


def _on_dark(fig, spec):
    """On the matplotlib style dark_background: what is drawn in black (lines, barbs,
    contours, text, the first run's colour) in white, and white boxes behind text in
    black.  A hodograph keeps its own look: a light card, with its dark lines."""
    if spec.get("mplstyle") != "dark_background":
        return

    def like(c, v):  # (colour c is black or white, not see-through)
        r, g, b, a = to_rgba(c)
        return a > 0 and max(abs(r - v), abs(g - v), abs(b - v)) < 0.01

    def swap(colors, v=0.0, to="white"):  # (a Collection's array of colours)
        return [to if like(c, v) else c for c in colors]

    keep = {id(a) for hodo in fig.findobj(lambda a: getattr(a, "_cv_hodo", False))
            for a in hodo.findobj()}
    for a in fig.findobj():
        if id(a) in keep:
            continue
        if isinstance(a, Text):
            if like(a.get_color(), 0.0):
                a.set_color("white")
        elif isinstance(a, Line2D):
            if like(a.get_color(), 0.0):
                a.set_color("white")
            if like(a.get_markeredgecolor(), 0.0):
                a.set_markeredgecolor("white")
            if like(a.get_markerfacecolor(), 0.0):
                a.set_markerfacecolor("white")
        elif isinstance(a, ContourSet):
            if not a.filled and all(like(c, 0.0) for c in a.get_edgecolor()):
                a.set_array(None)
                a.set_edgecolor("white")
        elif isinstance(a, Collection):
            if a.get_array() is None:
                a.set_edgecolor(swap(a.get_edgecolor()))
                a.set_facecolor(swap(a.get_facecolor()))
        else:  # (a label's box is not among the label's children)
            p = a.patch if isinstance(a, AnchoredOffsetbox) else a
            if isinstance(p, Patch):
                if like(p.get_edgecolor(), 0.0):
                    p.set_edgecolor("white")
                if like(p.get_facecolor(), 1.0):
                    p.set_facecolor("black")


def _labels_width(labels):
    """The width (pt) the panel labels [(edge, Text)] need: those on one edge side by
    side, with a font size of room around each."""
    edges = {}
    for edge, t in labels:
        size = t.get_fontsize()
        edges[edge] = edges.get(edge, size) + size + _tbl_width(t.get_text(),
                                                                t.get_fontproperties())
    return max(edges.values())


def _cell_width(ax):
    """The width (pt) of the grid cells of panel ax: what it gets at most."""
    w = ax.get_figure().bbox.width * 72.0 / ax.get_figure(root=True).dpi
    ss = ax.get_subplotspec().get_topmost_subplotspec()
    gs = ss.get_gridspec()
    ratios = gs.get_width_ratios() or [1.0] * gs.ncols
    return w * sum(ratios[c] for c in ss.colspan) / sum(ratios)


def fit_labels(fig):
    """Shrink the panel labels of the panels with "label_fit" until those on one edge of
    a panel fit it side by side: all by one factor, so they stay the same size across
    the figure, in half points and to 6 pt at least.  Most figures have room to spare,
    and only the others cost a layout here."""
    panels = [(ax, ax._cv_labels) for ax in fig.axes if getattr(ax, "_cv_labels", None)]
    if all(_labels_width(labs) <= 0.7 * _cell_width(ax) for ax, labs in panels):
        return
    where = [(ax, ax.get_position(original=True), ax.get_in_layout()) for ax in fig.axes]
    fig.draw_without_rendering()  # (the layout: how big the panels are)
    f = min(ax.get_window_extent().width * 72.0 / fig.dpi / _labels_width(labs)
            for ax, labs in panels)
    for ax, pos, in_layout in where:  # (a second layout from the first's moves them a little)
        ax.set_position(pos)
        ax.set_in_layout(in_layout)  # (set_position takes it out)
    if f >= 1.0:
        return
    for _, labs in panels:
        for _, t in labs:
            size = t.get_fontsize()
            t.set_fontsize(max(min(size, MIN_LABEL_PT), np.floor(2.0 * size * f) / 2.0))


def _annotate(ax, i, anns, fs):
    """Text, markers, arrows, lines, boxes and circles in panel i (panel -1: every
    panel; a list: those panels), in data coordinates or as fractions of the panel (coords 'axes').  In a
    skew-T, data coordinates are temperature (deg C) and pressure (hPa)."""
    skew = getattr(ax, "_cv_skew", None)
    for a in anns:
        if not ann_on(a, i) or a.get("kind") == "legend":  # (legend_handles)
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
