"""The arrays of plan-view and cross-section panels."""

import json

import numpy as np

from ...core import azim, render, series as ser, swath, vectors
from .. import draw as figdraw
from ...core.run import FileBusy, MissingAtTime
from .base import panel_ref, tindex, storm_motion
from .sections import (domain_box, is_storm, panel_section, section_ends, section_motion,
                       sections, x_axis)

DATA_KEYS = ("type", "field", "mode", "z", "spacing", "zspacing", "frame",  # -> data
             "style", "reduce", "vector", "which")


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
    return center[0] - h, center[0] + h, center[1] - h, center[1] + h


def data_key(spec, i, center, path=""):
    """Everything panel i's arrays depend on (style changes leave it unchanged)."""
    layers = figdraw.spec_layers(spec, i)
    lk = [{k: lay.get(k) for k in DATA_KEYS if k in lay} | {"on": lay.get("on", True)}
          for lay in layers]
    return json.dumps(dict(kind=spec["kind"], ref=panel_ref(spec, i), path=path,
                           dom=spec["domain"],
                           coords=spec["coords"],
                           xsec=[spec["xsec"], panel_section(spec, i)[1], sections(spec)]
                           if spec["kind"] == "xsec" or any(lay["type"] == "line"
                                                            for lay in layers) else None,
                           layers=lk, center=center), sort_keys=True, default=float)


def extract(run, F, spec, i, center, fixes=None, storm=None, progress=None):
    """Arrays of panel i (dict for figdraw).  center: tracked storm (x, y) km at the
    panel time or None; fixes: {t: fix} for the track layer; storm: ground-relative
    storm motion (u, v) at this time for storm-relative fields and vectors."""
    ts = panel_ref(spec, i)[1]
    t = tindex(run, ts)
    if t is None:
        return dict(time_s=ts, missing=f"no output at {ts / 60:g} min in this run")
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
        elif lay["type"] == "line":  # (every section, or with which "panel" its own)
            secs = list(enumerate(sections(spec)))
            if lay.get("which", "all") == "panel":
                secs = [panel_section(spec, i)]
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


def reduce_layer(run, F, lay, t, fixes=None, progress=None):
    """swath.reduce of plan layer `lay` (its "reduce") for a panel at output t, with
    the storm centres and motions of the track `fixes`."""
    centers = ser.track_centers(fixes, len(run.times)) if fixes else {}
    storm = ({k: storm_motion(run, fixes, k) for k in range(len(run.times))}
             if F[lay["field"]].storm else None)
    return swath.reduce(run, F, lay, t, centers, storm, progress)


def _strip(run, vol, fi, fj, zq, across, width):
    """render.sample_section, or with width (km) > 0 its mean over lines parallel to
    the section within width / 2 either side (about one per grid column, at most 21);
    across: the unit vector across the section (grid x, y)."""
    if not width or width <= 0:
        return render.sample_section(run, vol, fi, fj, zq)
    dxk, dyk = run.dx / 1000.0, run.dy / 1000.0
    n = int(min(21, max(3, round(width / min(dxk, dyk)) + 1)))
    secs = [render.sample_section(run, vol, fi + o * across[0] / dxk,
                                  fj + o * across[1] / dyk, zq)
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
    run.load_volumes([n for n in names if n in run.vars], t, progress=progress)
    s, fi, fj, (ex, ey) = render.section_coords(run, *ends)
    ztop, dz = float(xs["ztop"]), float(xs.get("dz", 0.025))
    zq = np.arange(0.0, ztop + 0.5 * dz, dz)
    k, o, out["xname"] = x_axis(sec, xs.get("coords", "storm"), center)
    if k is None:  # the distance along: 0 at the storm (the middle), else at A
        x = s - (s[-1] / 2.0 if is_storm(sec) else 0.0)
    else:  # x or y
        x = ends[0][k] - o + s * (ex, ey)[k]
    width, across = float(sec.get("avg") or 0.0), (-ey, ex)  # (a strip: its mean)
    out["x"], out["y"] = x, zq
    out["xlim"], out["ylim"] = (min(x[0], x[-1]), max(x[0], x[-1])), (0.0, ztop)
    for j, lay in enumerate(layers):
        if not lay.get("on", True):
            continue
        if lay["type"] in ("fill", "contour", "shade"):
            out[f"L{j}"] = _strip(run, F.volume(lay["field"], t, storm), fi, fj, zq,
                                  across, width)
        elif lay["type"] == "vectors":
            q = lay.get("vector", "wind")  # in the plane: along-section and vertical
            u, v, w = (np.zeros((zq.size, s.size), np.float32) if a is None else
                       _strip(run, a, fi, fj, zq, across, width)
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
