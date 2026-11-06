"""The arrays of plan-view and cross-section panels."""

import json

import numpy as np

from ...core import (azim, geo, parcels as P, render, series as ser, swath, track as trk, vectors,
                     volume3d)
from .. import draw as figdraw
from ...core.run import FileBusy, MissingAtTime
from .base import panel_ref, tindex, storm_motion
from .sections import (card_section, domain_box, is_storm, panel_section, section_ends,
                       section_motion, sections, x_axis)

DATA_KEYS = ("type", "field", "mode", "z", "spacing", "zspacing", "frame",  # -> data
             "style", "reduce", "vector", "which", "rule", "ids", "cvar", "tails",
             "minutes", "heads", "interp", "within", "xs_tails", "moving", "move_u",
             "move_v", "kinds", "grid", "step")
MAX_PARCEL_POINTS = 300_000  # per parcel layer: longer tails at every n-th parcel time


def plan_window(run, spec, center):
    """(x0, x1, y0, y1) grid km of a plan panel, or None."""
    dom = spec["domain"]
    if dom["mode"] == "full":
        return domain_box(run)
    if dom["mode"] == "box":
        return tuple(dom["box"]) if dom.get("box") else None
    if center is None:
        return None
    h = float(dom["half"])
    ox, oy = dom.get("off") or (0.0, 0.0)  # (an inset's: its centre from the storm's)
    return center[0] + ox - h, center[0] + ox + h, center[1] + oy - h, center[1] + oy + h


def data_key(spec, i, center, path=""):
    """Everything panel i's arrays depend on (style changes leave it unchanged)."""
    layers = figdraw.spec_layers(spec, i)
    lk = [{k: lay.get(k) for k in DATA_KEYS if k in lay} | {"on": lay.get("on", True)}
          for lay in layers]
    line = any(lay["type"] == "line" for lay in layers)  # (the sections: all of them)
    return json.dumps(dict(kind=spec["kind"], ref=panel_ref(spec, i), path=path,
                           dom=spec["domain"],
                           coords=spec["coords"],
                           xsec=[spec["xsec"], card_section(panel_section(spec, i)[1]),
                                 [card_section(sec) for sec in sections(spec)] if line else None]
                           if spec["kind"] == "xsec" or line else None,
                           layers=lk, center=center), sort_keys=True, default=float)


def extract(run, F, spec, i, center, fixes=None, storm=None, progress=None):
    """Arrays of panel i (dict for figdraw).  center: tracked storm (x, y) km at the
    panel time or None; fixes: {t: fix} for the track layer; storm: ground-relative
    storm motion (u, v) at this time for storm-relative fields and vectors."""
    k, ts = panel_ref(spec, i)
    t = tindex(run, ts)
    if t is None:
        t0 = figdraw.run_t0(spec, k)
        why = " (runs paired by output number)" if figdraw.output_times(spec, k) else \
            f" (its time zero: {t0:g} min)" if t0 else ""
        return dict(time_s=ts, missing=f"no output at {ts / 60:g} min in this run" + why)
    out = dict(time_s=float(run.times[t]))
    bad = [lay["field"] for lay in figdraw.spec_layers(spec, i)
           if lay.get("on", True) and lay.get("field") and lay["field"] not in F]
    if bad:
        return dict(out, missing="this run has no " + ", ".join(bad))
    try:
        if spec["kind"] == "xsec":
            _extract_xsec(run, F, spec, i, t, center, fixes, storm, out, progress)
        else:
            _extract_plan(run, F, spec, i, t, center, fixes, storm, out, progress)
    except (MissingAtTime, FileBusy) as e:
        out = dict(time_s=float(run.times[t]), missing=str(e))
    return out


# a 3D scene figure's spec["scene3d"]: build_scene's request (the viewer's 3D tab; box
# None: the whole domain; isosurfaces and vectors with on False kept but not drawn), the
# picture's camera and look (figdraw.CAMERA, LOOK keys) and, in animations, whether the
# box follows the track ("track") or stays ("fixed") and the camera's turn over all the
# frames (orbit, degrees; t0_s: the first frame's time, set by shift_times); parcels:
# parcel sets drawn in it (dicts like a parcels layer's, layer_defaults("parcels"))
SCENE3D = dict(box=None, ztop=15.0, exag=2.0, smooth=0.75, res=0, isos=[], vecs=[],
               stream=dict(on=False, z=0.5, n=12, length=40.0, dir="forward",
                           frame="storm", color_by="z", seed_box=None),
               ground=dict(on=False, var="dbz", z=0.0, cmap="Field default", rev=False,
                           range="data", lo=0.0, hi=0.0),
               camera={}, look={}, follow="fixed", orbit=0.0, parcels=[])
SCENE_DATA = ("box", "ztop", "smooth", "res", "isos", "vecs", "stream", "ground")  # -> data
SCENE_PARCEL_DATA = ("on", "rule", "ids", "cvar", "tails", "minutes", "heads", "interp",
                     "moving", "move_u", "move_v")


def _on(items):
    return [dict(i) for i in items or [] if i.get("on", True)]


def scene3d_of(spec):
    """A 3D scene figure's scene block with the defaults (SCENE3D) where it has none."""
    sc = dict(SCENE3D, **(spec.get("scene3d") or {}))
    for k in ("stream", "ground"):
        sc[k] = dict(SCENE3D[k], **(sc.get(k) or {}))
    return sc


def scene_key(spec, path, sig=""):
    """Everything a 3D scene's arrays depend on (camera, look and exaggeration
    changes leave it unchanged); sig: the run's track."""
    sc = scene3d_of(spec)
    t0 = sc.get("t0_s") if sc["follow"] == "track" else None
    return json.dumps(["scene", path, float(spec["time_s"]),
                       {k: sc[k] for k in SCENE_DATA}, t0, sig], sort_keys=True,
                      default=float)


def scene_request(run, spec, fixes, t):
    """build_scene's request of a 3D scene figure at output t: its settings, the whole
    domain for no box, and the track's storm motion (else the domain's) for the
    storm-relative fields, vectors and streamlines.  A box following the track (an
    animation's frame) moves, with the streamlines' seed box, as far as the track has
    since the first frame (t0_s): shift (dx, dy km), None when it stays."""
    sc = scene3d_of(spec)
    storm = tuple(float(v) for v in storm_motion(run, fixes, t))
    own = bool(fixes) and storm != (float(run.umove), float(run.vmove))
    box = tuple(float(v) for v in sc["box"]) if sc.get("box") else domain_box(run)
    stream = dict(sc["stream"])
    shift = scene_shift(run, sc, fixes, t) if sc.get("box") else None
    if shift:
        dx, dy = shift
        box = (box[0] + dx, box[1] + dx, box[2] + dy, box[3] + dy)
        sb = stream.get("seed_box")
        if sb:
            stream["seed_box"] = [sb[0] + dx, sb[1] + dx, sb[2] + dy, sb[3] + dy]
    ztop = min(float(sc["ztop"]), volume3d.top_height(run))  # (terrain: km MSL)
    return dict(t=t, box=box, ztop=ztop, exag=float(sc["exag"]),
                smooth=float(sc["smooth"]), res=int(sc["res"]), isos=_on(sc["isos"]),
                vecs=_on(sc["vecs"]), stream=stream, ground=dict(sc["ground"]),
                storm=storm, fstorm=(storm, "rel. to tracked motion" if own
                                     else "rel. to umove/vmove"), shift=shift)


def scene_shift(run, sc, fixes, t):
    """(dx, dy) km the track moved from the animation's first frame (sc["t0_s"]) to
    output t when scene block sc follows the track; None when it does not, or the
    track has no fix at either time (the box then stays)."""
    if sc.get("follow") != "track" or sc.get("t0_s") is None or not fixes:
        return None
    t0 = tindex(run, float(sc["t0_s"]))
    p0 = trk.position(fixes, t0) if t0 is not None else None
    p1 = trk.position(fixes, t)
    if p0 is None or p1 is None:
        return None
    return float(p1[0] - p0[0]), float(p1[1] - p0[1])


def parcels_follow_track(lays):
    """Whether any of these parcel layers / scene entries is seen moving with the track
    (its arrays then depend on the track)."""
    return any(e.get("type", "parcels") == "parcels" and e.get("moving") == "track"
               and e.get("on", True) for e in lays)


def scene_parcel_key(spec, path, d, sig=""):
    """Everything the parcels of a 3D scene depend on besides what its other arrays
    (d, of scene_key) do: their sets and what of them is drawn (not their look); sig:
    the track's signature (counts only when a set is seen moving with it)."""
    sc = scene3d_of(spec)
    return json.dumps(["scene parcels", path, d.get("time_s"), d.get("box"), d.get("ztop"),
                       [{k: e.get(k) for k in SCENE_PARCEL_DATA} for e in sc["parcels"]],
                       sig if parcels_follow_track(sc["parcels"]) else ""],
                      sort_keys=True, default=lambda v: np.asarray(v).tolist())


def scene_parcels(run, spec, d, fixes=None):
    """The parcel arrays (P<n>_*: figdraw.scene_data) of a 3D scene figure whose
    other arrays are d: each set's tails over its window of parcel times and heads at
    the scene's time, inside the region it was computed over (d["box"], up to
    d["ztop"]; the lines break where they leave it); fixes: the track, for sets seen
    moving with it.  Why a set has nothing: "notes"."""
    out = {}
    if "box" not in d or d.get("missing"):
        return out
    ts = float(d["time_s"])
    x0, x1, y0, y1 = (float(v) for v in np.asarray(d["box"]).ravel())
    ztop = float(d["ztop"])

    def inside(x, y, z):
        return ((min(x0, x1) <= x) & (x <= max(x0, x1)) & (min(y0, y1) <= y)
                & (y <= max(y0, y1)) & (z <= ztop))

    for n, e in enumerate(scene3d_of(spec)["parcels"]):
        if not e.get("on", True):
            continue
        got = _parcel_layer(run, e, ts, out, fixes)
        if got is None:
            continue
        pf, tr, cvar, sl, per = got
        idx = P.thin_times(sl, tr["x"].shape[1], MAX_PARCEL_POINTS)
        lines = (None,) * 4
        if len(idx) > 1:
            cols = {k: tr[k][idx] for k in ("x", "y", "z")}
            if cvar:
                cols["v"] = tr[cvar][idx]
            pl = P.polylines(cols, per=per)
            with np.errstate(invalid="ignore"):
                ok = inside(pl["x"], pl["y"], pl["z"])
            lines = tuple(None if a is None else np.where(ok, a, np.nan)
                          for a in (pl["x"], pl["y"], pl["z"], pl.get("v")))
        heads = (None,) * 4
        if e.get("heads", True):
            hx, hy, hz, hv = _parcel_heads(pf, tr, cvar, ts, e, per)
            with np.errstate(invalid="ignore"):
                ok = np.isfinite(hx) & np.isfinite(hy) & np.isfinite(hz) & inside(hx, hy, hz)
            heads = (hx[ok], hy[ok], hz[ok], None if hv is None else hv[ok])
        for pre, cols in (("p", lines), ("h", heads)):
            for c, a in zip("xyzv", cols):
                if a is not None:
                    out[f"P{n}_{pre}{c}"] = np.asarray(a, dtype=np.float32)
    return out


def with_scene_parcels(d, parcels):
    """Scene arrays d with the parcel arrays (scene_parcels') added, their notes
    joined to d's."""
    out = dict(d, **{k: v for k, v in parcels.items() if k != "notes"})
    notes = "; ".join(filter(None, [d.get("notes"), parcels.get("notes")]))
    if notes:
        out["notes"] = notes
    return out


def scene_extract(run, F, spec, fixes=None, progress=None, cancelled=None, cache=None,
                  parcels=True):
    """Arrays of a 3D scene figure's panel (figdraw.scene_data), or None when
    cancelled.  progress(done, total, name) reports the loading; cache: build_scene's
    (the streamlines kept across calls); parcels False: without the parcel sets'
    (scene_parcels, kept apart since they change without the rest)."""
    ts = float(spec["time_s"])
    t = tindex(run, ts)
    if t is None:
        return dict(time_s=ts, missing=f"no output at {ts / 60:g} min in this run")
    bad = [n for n in [i["var"] for i in _on(scene3d_of(spec)["isos"])] if n not in F]
    if bad:
        return dict(time_s=ts, missing="this run has no " + ", ".join(bad))
    req = scene_request(run, spec, fixes, t)
    try:
        arrays = volume3d.build_scene(run, F, req, progress, cancelled, cache)
    except (MissingAtTime, FileBusy) as e:
        return dict(time_s=float(run.times[t]), missing=str(e))
    if arrays is None:
        return None
    out = dict(figdraw.scene_data(arrays, req["box"], req["ztop"]), time_s=float(run.times[t]))
    notes = list(arrays["notes"])
    if req["shift"]:
        out["shift"] = np.asarray(req["shift"], np.float64)
    elif (scene3d_of(spec)["follow"] == "track" and scene3d_of(spec).get("t0_s") is not None
          and scene3d_of(spec).get("box")):
        notes.append("no track fix at this time or the first frame's: the box stays")
    if notes:
        out["notes"] = "; ".join(notes)
    return with_scene_parcels(out, scene_parcels(run, spec, out, fixes)) if parcels else out


def _origin(spec, center):
    if spec["coords"] == "storm" and center is not None:
        return center
    return (0.0, 0.0)


def _extract_plan(run, F, spec, i, t, center, fixes, storm, out, progress=None):
    win = plan_window(run, spec, center)
    if win is None:
        out["missing"] = ("no track position at this time" if spec["domain"]["mode"] == "storm"
                          else "no box chosen")
        return
    x0, x1, y0, y1 = win
    ox, oy = _origin(spec, center)
    i0 = max(0, int(np.searchsorted(run.xh, x0)) - 1)
    i1 = min(run.ni, int(np.searchsorted(run.xh, x1)) + 1)
    j0 = max(0, int(np.searchsorted(run.yh, y0)) - 1)
    j1 = min(run.nj, int(np.searchsorted(run.yh, y1)) + 1)
    out["x"], out["y"] = run.xh[i0:i1] - ox, run.yh[j0:j1] - oy
    out["xlim"], out["ylim"] = (x0 - ox, x1 - ox), (y0 - oy, y1 - oy)
    out["origin"] = np.array([ox, oy], dtype=float)  # grid km of the axes' (0, 0)
    for j, lay in enumerate(figdraw.spec_layers(spec, i)):
        if not lay.get("on", True):
            continue
        if lay["type"] in ("fill", "contour", "shade") and lay.get("reduce"):
            try:  # (a time window: a swath or a storm-following composite)
                a, _ = reduce_layer(run, F, lay, t, fixes, progress)
            except ValueError as e:
                out["missing"] = f"time window: {e}"
                return
            out[f"L{j}"] = a[j0:j1, i0:i1]
        elif lay["type"] in ("fill", "contour", "shade"):
            a = F.plane(lay["field"], t, lay.get("mode", "height"), float(lay["z"]),
                        storm=storm)
            out[f"L{j}"] = np.asarray(a[j0:j1, i0:i1], dtype=np.float32)
        elif lay["type"] == "vectors":  # (at a height, or a model level: panels by level)
            mode = "level" if lay.get("mode") == "level" else "height"
            u, v = vectors.plane(F, lay.get("vector", "wind"), t, mode, float(lay["z"]),
                                 lay["frame"], storm)
            u, v = u[j0:j1, i0:i1], v[j0:j1, i0:i1]
            if lay.get("style") == "streamlines":  # the vectors on a (thinned) grid
                g = max(1, int(np.ceil(max(u.shape) / 300.0)))
                out[f"L{j}_gx"], out[f"L{j}_gy"] = out["x"][::g], out["y"][::g]
                out[f"L{j}_gu"] = np.asarray(u[::g, ::g], dtype=np.float32)
                out[f"L{j}_gv"] = np.asarray(v[::g, ::g], dtype=np.float32)
                continue
            st = max(1, int(round(float(lay["spacing"]) * 1000.0 / run.dx)))
            sl = (slice(st // 2, None, st), slice(st // 2, None, st))
            X, Y = np.meshgrid(out["x"], out["y"])
            out[f"L{j}_x"], out[f"L{j}_y"] = X[sl], Y[sl]
            out[f"L{j}_u"], out[f"L{j}_v"] = u[sl], v[sl]
        elif lay["type"] == "track" and fixes:
            ts = sorted(fixes)
            out["track_x"] = np.array([fixes[s]["x"] for s in ts]) - ox
            out["track_y"] = np.array([fixes[s]["y"] for s in ts]) - oy
            if t in fixes:
                out["now_x"], out["now_y"] = fixes[t]["x"] - ox, fixes[t]["y"] - oy
        elif lay["type"] == "parcels":
            _parcels_plan(run, lay, out, j, (x0, x1, y0, y1), (ox, oy), fixes)
        elif lay["type"] == "boundaries":
            _boundaries_plan(run, lay, out, j, (x0, x1, y0, y1), (ox, oy))
        elif lay["type"] == "line":  # (every section, or with which "panel" its own)
            if lay.get("which", "all") == "panel":
                secs = [panel_section(spec, i)]
            else:  # (cards alike but for their run, time or panel: one line, numbered on)
                seen = []
                for sec in sections(spec):
                    if card_section(sec) not in seen:
                        seen.append(card_section(sec))
                secs = list(enumerate(seen))
            rows = []
            for k, sec in secs:
                ends = section_ends(run, sec, center, section_motion(run, fixes, t, sec))
                if ends is not None:
                    (xa, ya), (xb, yb) = ends
                    rows.append([xa - ox, ya - oy, xb - ox, yb - oy,
                                 float(sec.get("avg") or 0.0), k])  # (avg: the strip)
            if rows:
                out["lines"] = np.array(rows, dtype=float)
        elif lay["type"] == "sector":  # (the track's centre; the wedge itself: drawn)
            m = storm_motion(run, fixes, t)
            c = ser.track_centers(fixes or {}, len(run.times)).get(t)  # (not the view's)
            out["sector"] = np.array([np.nan, np.nan, azim.bearing(*m)]) if c is None \
                else np.array([c[0] - ox, c[1] - oy, azim.bearing(*m)])


def _boundaries_plan(run, lay, out, j, win, origin):
    """A Map boundaries layer's lines over the panel's window (run.geo's, cut to it)
    and its lat/lon lines and their labels, from the axes' origin (km)."""
    g = getattr(run, "geo", None)
    if g is None:
        _note(out, "map boundaries: this run is not on a map projection")
        return
    x0, x1, y0, y1 = win
    ox, oy = origin
    pad = 2.0 * float(run.dx) / 1000.0
    xlim, ylim = (x0 - pad, x1 + pad), (y0 - pad, y1 + pad)
    for kind in lay.get("kinds") or []:
        if kind not in geo.KINDS:
            continue
        x, y = geo.clip(*g.lines(kind), xlim, ylim)
        out[f"L{j}_b_{kind}"] = np.array([x - ox, y - oy], dtype=np.float32)
    if lay.get("grid"):
        x, y, labels, _ = geo.graticule(g, float(lay.get("step") or 0.0) or None,
                                        (x0, x1), (y0, y1))
        out[f"L{j}_grid"] = np.array([x - ox, y - oy], dtype=np.float32)
        out[f"L{j}_glab"] = np.array([[lx - ox, ly - oy, float(edge == "left")]
                                      for lx, ly, _, edge in labels],
                                     dtype=float).reshape(-1, 3)
        out[f"L{j}_glab_t"] = np.array([lab[2] for lab in labels], dtype=str)


def _note(out, why):
    out["notes"] = "; ".join(filter(None, [out.get("notes"), why]))


def _parcel_layer(run, lay, ts, out, fixes=None):
    """(ParcelFile, trajectories, colour variable, tail slice, period) of parcel layer
    `lay` at model time ts, or None (with why in out["notes"]); the trajectories seen
    from its frame ("moving": "grid", "track" with fixes, "motion" at move_u, move_v),
    the same as the grid's at ts."""
    pf = P.for_run(run)
    cvar = lay.get("cvar") or ""
    why = "no parcel output in this run" if pf is None else \
        f"no parcel {cvar} in this run" if cvar and not pf.has(cvar) else None
    ps = None
    if why is None:
        ps = P.chosen(pf, lay.get("rule"), lay.get("ids"), lay.get("name") or "parcels")
        if not len(ps):
            why = f"parcels {lay.get('name') or ''}: none chosen".replace("  ", " ")
    if why:
        _note(out, why)
        return None
    tr = pf.trajectories(ps, P.POS + ((cvar,) if cvar and cvar not in P.POS else ()))
    how = lay.get("moving") or "grid"
    if how != "grid":
        shift = P.frame_shift(pf, run, ts, how, (float(lay.get("move_u") or 0.0),
                                                 float(lay.get("move_v") or 0.0)), fixes)
        if shift is None and how == "track":
            _note(out, "parcel tails seen from the grid: no track of two fixes or more")
        tr = P.moving(tr, shift)
    mode = lay.get("tails", "until")
    sl = slice(0, 0) if mode == "none" else pf.window(ts, mode, lay.get("minutes"))
    return pf, tr, cvar, sl, P.period(run)


def _parcel_heads(pf, tr, cvar, ts, lay, per):
    """(x, y, z, value or None) km of the parcels at ts (interpolated with "interp")."""
    interp = lay.get("interp", True)
    x, y, z = P.heads(pf, tr, ts, interp, per)
    return x, y, z, (P.at_time(pf, tr[cvar], ts, interp) if cvar else None)


def _put_parcels(out, j, lines, heads):
    """L<j>_px, _py, _pv (NaN-separated trajectories) and L<j>_hx, _hy, _hv (heads)."""
    for pre, cols in (("p", lines), ("h", heads)):
        for name, a in zip("xyv", cols):
            if a is not None:
                out[f"L{j}_{pre}{name}"] = np.asarray(a, dtype=np.float32)


def _parcels_plan(run, lay, out, j, win, origin, fixes=None):
    """A parcel layer of a plan panel: tails over its window of parcel times and heads
    at the panel time, in the panel's coordinates; points well outside the panel are
    left out (the lines break there)."""
    ts = out["time_s"]
    got = _parcel_layer(run, lay, ts, out, fixes)
    if got is None:
        return
    pf, tr, cvar, sl, per = got
    (x0, x1, y0, y1), (ox, oy) = win, origin
    mx, my = 0.1 * (x1 - x0), 0.1 * (y1 - y0)

    def inside(x, y):
        return (x >= x0 - mx) & (x <= x1 + mx) & (y >= y0 - my) & (y <= y1 + my)

    idx = P.thin_times(sl, tr["x"].shape[1], MAX_PARCEL_POINTS)
    lines = (None, None, None)
    if len(idx) > 1:
        cols = {"x": tr["x"][idx], "y": tr["y"][idx]}
        if cvar:
            cols["v"] = tr[cvar][idx]
        pl = P.polylines(cols, per=per)
        ok = inside(pl["x"], pl["y"])
        lines = tuple(None if a is None else np.where(ok, a, np.nan)
                      for a in (pl["x"] - ox, pl["y"] - oy, pl.get("v")))
    heads = (None, None, None)
    if lay.get("heads", True):
        hx, hy, _, hv = _parcel_heads(pf, tr, cvar, ts, lay, per)
        ok = np.isfinite(hx) & np.isfinite(hy) & inside(hx, hy)
        heads = (hx[ok] - ox, hy[ok] - oy, None if hv is None else hv[ok])
    _put_parcels(out, j, lines, heads)


def _parcels_xsec(run, lay, out, j, ends, along, fixes=None):
    """A parcel layer of a section panel: the parcels within ± lay["within"] km of the
    section's line, projected onto it (along(distance from A) -> panel x; height):
    heads at the panel time, and the parts of their tails near it (xs_tails "near") or
    whole tails of the parcels near it now ("whole")."""
    ts = out["time_s"]
    got = _parcel_layer(run, lay, ts, out, fixes)
    if got is None:
        return
    pf, tr, cvar, sl, per = got
    A, B = ends
    L, w = float(np.hypot(B[0] - A[0], B[1] - A[1])), float(lay.get("within", 1.0) or 0.0)

    def inside(s, d):
        return np.isfinite(s) & (np.abs(d) <= w) & (s >= 0.0) & (s <= L)

    hx, hy, hz, hv = _parcel_heads(pf, tr, cvar, ts, lay, per)
    hs, hd = P.section_xy(hx, hy, A, B)
    near = inside(hs, hd) & np.isfinite(hz)
    heads = (None, None, None)
    if lay.get("heads", True):
        heads = (along(hs[near]), hz[near], None if hv is None else hv[near])
    lines = (None, None, None)
    whole = lay.get("xs_tails", "near") == "whole"
    cols_n = int(near.sum()) if whole else tr["x"].shape[1]
    idx = P.thin_times(sl, cols_n, MAX_PARCEL_POINTS)
    if len(idx) > 1 and cols_n:
        pick = near if whole else slice(None)
        x, y = tr["x"][idx][:, pick], tr["y"][idx][:, pick]
        S, D = P.section_xy(x, y, A, B)
        z = tr["z"][idx][:, pick]
        if not whole:  # (only the parts in the slab: the rest breaks the lines)
            z = np.where(inside(S, D), z, np.nan)
        cols = {"x": x, "y": y, "s": S, "z": z}
        if cvar:
            cols["v"] = tr[cvar][idx][:, pick]
        pl = P.polylines(cols, per=per)
        lines = (along(np.where(np.isfinite(pl["z"]), pl["s"], np.nan)), pl["z"], pl.get("v"))
    _put_parcels(out, j, lines, heads)


def reduce_layer(run, F, lay, t, fixes=None, progress=None):
    """swath.reduce of plan layer `lay` (its "reduce") for a panel at output t, with
    the storm centres and motions of the track `fixes`."""
    centers = ser.track_centers(fixes, len(run.times)) if fixes else {}
    storm = ({k: storm_motion(run, fixes, k) for k in range(len(run.times))}
             if F[lay["field"]].storm else None)
    return swath.reduce(run, F, lay, t, centers, storm, progress)


def _strip(run, vol, fi, fj, zq, across, width, t=None):
    """render.sample_section (at time t: a terrain run's heights), or with width (km)
    > 0 its mean over lines parallel to the section within width / 2 either side
    (about one per grid column, at most 21; under the ground of any line: blank);
    across: the unit vector across the section (grid x, y)."""
    if not width or width <= 0:
        return render.sample_section(run, vol, fi, fj, zq, t)
    dxk, dyk = run.dx / 1000.0, run.dy / 1000.0
    n = int(min(21, max(3, round(width / min(dxk, dyk)) + 1)))
    secs = [render.sample_section(run, vol, fi + o * across[0] / dxk,
                                  fj + o * across[1] / dyk, zq, t)
            for o in np.linspace(-0.5 * width, 0.5 * width, n)]
    return np.mean(secs, axis=0).astype(np.float32)


def _extract_xsec(run, F, spec, i, t, center, fixes, storm, out, progress):
    sec = panel_section(spec, i)[1]
    ends = section_ends(run, sec, center, section_motion(run, fixes, t, sec))
    if ends is None:
        out["missing"] = ("no track position at this time" if is_storm(sec)
                          else "no section line: click A and B on the map first")
        return
    xs = spec["xsec"]
    layers = figdraw.spec_layers(spec, i)
    names = []
    for lay in layers:
        if not lay.get("on", True):
            continue
        if lay["type"] in ("fill", "contour", "shade"):
            names += F.native_deps(lay["field"])
        elif lay["type"] == "vectors":
            names += vectors.deps(F, lay.get("vector", "wind"))
    if run.terrain:  # (each column on its own heights, above sea level)
        names.append("zmsl")
    run.load_volumes([n for n in names if n in run.vars], t, progress=progress)
    s, fi, fj, (ex, ey) = render.section_coords(run, *ends)
    dz = float(xs.get("dz", 0.025))
    z0, ztop, ground = render.section_span(run, fi, fj, float(xs["ztop"]))
    zq = z0 + np.arange(0.0, ztop - z0 + 0.5 * dz, dz)
    k, o, out["xname"] = x_axis(sec, xs.get("coords", "storm"), center)
    if k is None:  # the distance along: 0 at the storm (the middle), else at A
        x = s - (s[-1] / 2.0 if is_storm(sec) else 0.0)
    else:  # x or y
        x = ends[0][k] - o + s * (ex, ey)[k]
    width, across = float(sec.get("avg") or 0.0), (-ey, ex)  # (a strip: its mean)
    out["x"], out["y"] = x, zq
    out["xlim"], out["ylim"] = (min(x[0], x[-1]), max(x[0], x[-1])), (z0, ztop)
    if ground is not None:  # (drawn filled)
        out["ground"] = ground
    for j, lay in enumerate(layers):
        if not lay.get("on", True):
            continue
        if lay["type"] in ("fill", "contour", "shade"):
            out[f"L{j}"] = _strip(run, F.volume(lay["field"], t, storm), fi, fj, zq,
                                  across, width, t)
        elif lay["type"] == "vectors":
            q = lay.get("vector", "wind")  # in the plane: along-section and vertical
            u, v, w = (np.zeros((zq.size, s.size), np.float32) if a is None else
                       _strip(run, a, fi, fj, zq, across, width, t)
                       for a in vectors.volumes(F, q, t))
            if vectors.VECTORS[q].framed:
                u, v = vectors.to_frame(run, u, v, lay["frame"], storm)
            if lay.get("style") == "streamlines":
                gs, gz = max(1, int(np.ceil(s.size / 300.0))), max(1, int(np.ceil(zq.size / 200.0)))
                out[f"L{j}_gx"], out[f"L{j}_gy"] = out["x"][::gs], zq[::gz]
                out[f"L{j}_gu"] = np.asarray((u * ex + v * ey)[::gz, ::gs], dtype=np.float32)
                out[f"L{j}_gv"] = np.asarray(w[::gz, ::gs], dtype=np.float32)
                continue
            si = max(1, int(round(float(lay["spacing"]) / max(s[1] - s[0], 1e-6))))
            zi = max(1, int(round(float(lay.get("zspacing", 0.5)) / dz)))
            sl = (slice(zi // 2, None, zi), slice(si // 2, None, si))
            S, Z = np.meshgrid(out["x"], zq)
            out[f"L{j}_x"], out[f"L{j}_y"] = S[sl], Z[sl]
            out[f"L{j}_u"], out[f"L{j}_v"] = (u * ex + v * ey)[sl], w[sl]
        elif lay["type"] == "parcels":
            if k is None:
                along = (lambda a: a - s[-1] / 2.0) if is_storm(sec) else (lambda a: a)
            else:
                along = (lambda a, k=k: ends[0][k] - o + a * (ex, ey)[k])
            _parcels_xsec(run, lay, out, j, ends, along, fixes)
