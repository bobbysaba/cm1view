"""Pure computations behind the map and cross-section views.

All functions here are called from worker threads and return plain dicts
of numpy arrays ready to drop into Bokeh ColumnDataSources.
"""

import math

import numpy as np
import contourpy
from scipy.ndimage import map_coordinates

from .fields import palette


# ------------------------------------------------------------ helpers
def parse_levels(text, lo, hi, n=8):
    """'5, 10, 20' -> array; 'auto' / '' -> n nice levels in (lo, hi);
    'a:b:c' -> arange(a, b + c/2, c)."""
    text = (text or "").strip().lower()
    if text in ("", "auto"):
        lv = np.linspace(lo, hi, n + 2)[1:-1]
        return lv[lv != 0] if lo < 0 < hi else lv
    if text.count(":") == 2:
        a, b, c = (float(x) for x in text.split(":"))
        return np.arange(a, b + c * 0.5, c)
    return np.array(sorted(float(x) for x in text.replace(";", ",").split(",") if x.strip()))


def view_window(run, view, maxpix):
    """Index window + stride covering the current map view."""
    x0, x1, y0, y1 = view
    dxk, dyk = run.dx / 1000.0, run.dy / 1000.0
    i0 = max(0, int(math.floor((x0 - run.xh[0]) / dxk)) - 2)
    i1 = min(run.ni, int(math.ceil((x1 - run.xh[0]) / dxk)) + 3)
    j0 = max(0, int(math.floor((y0 - run.yh[0]) / dyk)) - 2)
    j1 = min(run.nj, int(math.ceil((y1 - run.yh[0]) / dyk)) + 3)
    if i1 - i0 < 2 or j1 - j0 < 2:
        i0, i1, j0, j1 = 0, run.ni, 0, run.nj
    s = max(1, int(math.ceil(max(i1 - i0, j1 - j0) / maxpix)))
    return i0, i1, j0, j1, s


def _crop(run, a, win):
    i0, i1, j0, j1, s = win
    return run.xh[i0:i1:s], run.yh[j0:j1:s], a[j0:j1:s, i0:i1:s]


def image_data(x, y, a):
    dx = (x[1] - x[0]) if x.size > 1 else 1.0
    dy = (y[1] - y[0]) if y.size > 1 else 1.0
    return dict(image=[np.ascontiguousarray(a, dtype=np.float32)],
                x=[x[0] - dx / 2], y=[y[0] - dy / 2],
                dw=[x[-1] - x[0] + dx], dh=[y[-1] - y[0] + dy])


def _masked(a):
    return np.ma.masked_invalid(a) if not np.isfinite(a).all() else a


def contour_lines(x, y, a, levels):
    """{'xs': [...], 'ys': [...]} - one NaN-separated row per level."""
    xs, ys = [], []
    if a.size == 0 or len(levels) == 0:
        return dict(xs=xs, ys=ys)
    gen = contourpy.contour_generator(x, y, _masked(a), line_type="Separate")
    for lv in levels:
        segs = gen.lines(lv)
        if not segs:
            continue
        nan = np.array([[np.nan, np.nan]])
        cat = np.concatenate([np.concatenate((s, nan)) for s in segs])[:-1]
        xs.append(cat[:, 0])
        ys.append(cat[:, 1])
    return dict(xs=xs, ys=ys)


def contour_fill(x, y, a, levels):
    """Filled bands as Bokeh multi_polygons rows (one row per band)."""
    xs, ys, val = [], [], []
    gen = contourpy.contour_generator(x, y, _masked(a), fill_type="OuterOffset")
    lv = np.asarray(levels, dtype=float)
    # open-ended first/last bands so out-of-range values still get colour
    lo_edges = np.concatenate(([-1e30], lv[1:-1]))
    hi_edges = np.concatenate((lv[1:-1], [1e30]))
    for k, (lo, hi) in enumerate(zip(lo_edges, hi_edges)):
        pts, offs = gen.filled(lo, hi)
        if not pts:
            continue
        px, py = [], []
        for p, o in zip(pts, offs):
            px.append([p[o[n]:o[n + 1], 0] for n in range(len(o) - 1)])
            py.append([p[o[n]:o[n + 1], 1] for n in range(len(o) - 1)])
        xs.append(px)
        ys.append(py)
        val.append(0.5 * (lv[k] + lv[k + 1]))
    return dict(xs=xs, ys=ys, val=val)


def vectors(x, y, u, v, n_across, ref_speed=20.0):
    """Arrow segments (data units) ~n_across arrows across the window."""
    nx = x.size
    s = max(1, nx // max(n_across, 1))
    xs, ys = np.meshgrid(x[s // 2::s], y[s // 2::s])
    uu, vv = u[s // 2::s, s // 2::s], v[s // 2::s, s // 2::s]
    spacing = (x[-1] - x[0]) / max(n_across, 1)
    k = 0.9 * spacing / ref_speed
    good = np.isfinite(uu) & np.isfinite(vv) & (np.hypot(uu, vv) > 0.2)
    x0, y0 = xs[good], ys[good]
    x1, y1 = x0 + uu[good] * k, y0 + vv[good] * k
    ang = np.arctan2(vv[good], uu[good]) - np.pi / 2
    return dict(x0=x0, y0=y0, x1=x1, y1=y1, angle=ang), spacing


# ------------------------------------------------------------ map
def fill_palette(spec):
    if spec["style"] == "contourf":
        n = max(len(spec["levels"]) - 1, 1)
        full = palette(spec["cmap"], 256, spec["rev"])
        return [full[min(255, int((i + 0.5) * 256 / n))] for i in range(n)]  # band midpoints
    return palette(spec["cmap"], 256, spec["rev"])


def compute_map(F, spec):
    run, t = F.run, spec["t"]
    win = view_window(run, spec["view"], spec["maxpix"])
    out = dict(win=win)

    f = spec["fill"]
    if f["var"]:
        a = F.plane(f["var"], t, f["mode"], f["level"], storm=spec.get("fstorm"))
        lo, hi = F.auto_range(f["var"], a) if f["auto"] else (f["vmin"], f["vmax"])
        if hi <= lo:
            hi = lo + 1e-6
        x, y, ac = _crop(run, a, win)
        fill = dict(style=f["style"], lo=lo, hi=hi, cmap=f["cmap"], rev=f["rev"])
        if f["style"] == "contourf":
            levels = np.linspace(lo, hi, max(int(f["nlev"]), 2) + 1)
            fill.update(levels=levels, poly=contour_fill(x, y, ac, levels))
        else:
            fill.update(image=image_data(x, y, ac))
        fill["palette"] = fill_palette(fill)
        out["fill"] = fill

    out["ov"] = []
    for o in spec["ov"]:
        if not o["on"] or not o["var"]:
            out["ov"].append(None)
            continue
        a = F.plane(o["var"], t, o["mode"], o["level"], storm=spec.get("fstorm"))
        lo, hi = F.auto_range(o["var"], a)
        levels = parse_levels(o["levels"], lo, hi)
        x, y, ac = _crop(run, a, win)
        out["ov"].append(dict(pos=contour_lines(x, y, ac, levels[levels >= 0]),
                              neg=contour_lines(x, y, ac, levels[levels < 0])))

    vsp = spec["vec"]
    out["vec"] = None
    if vsp["on"]:
        u = F.plane("uinterp", t, "height", vsp["level"])
        v = F.plane("vinterp", t, "height", vsp["level"])
        if vsp["frame"] == "ground":
            u, v = u + run.umove, v + run.vmove
        elif vsp["frame"] == "storm":
            cu, cv = spec["storm"]
            u, v = u + run.umove - cu, v + run.vmove - cv
        x, y, uc = _crop(run, u, win)
        _, _, vc = _crop(run, v, win)
        out["vec"], _ = vectors(x, y, uc, vc, vsp["density"], vsp["ref"])
    return out


# ------------------------------------------------------------ cross-section
def section_coords(run, A, B, max_pts=1200):
    (xa, ya), (xb, yb) = A, B
    L = math.hypot(xb - xa, yb - ya)
    n = int(min(max_pts, max(2, math.ceil(L / (run.dx / 1000.0)) + 1)))
    s = np.linspace(0.0, L, n)
    xp = xa + (xb - xa) * s / max(L, 1e-9)
    yp = ya + (yb - ya) * s / max(L, 1e-9)
    fi = (xp - run.xh[0]) / (run.dx / 1000.0)
    fj = (yp - run.yh[0]) / (run.dy / 1000.0)
    return s, fi, fj, ((xb - xa) / max(L, 1e-9), (yb - ya) / max(L, 1e-9))


def sample_section(run, vol, fi, fj, zq):
    """Bilinear sampling along the line, then linear in z onto zq (km)."""
    nk = vol.shape[0]
    kk = np.repeat(np.arange(nk)[:, None], fi.size, axis=1)
    coords = np.stack([kk, np.broadcast_to(fj, kk.shape), np.broadcast_to(fi, kk.shape)])
    sec = map_coordinates(vol, coords, order=1, mode="nearest")  # (nk, n)
    kf = np.interp(zq, run.z, np.arange(nk))
    k0 = np.clip(np.floor(kf).astype(int), 0, nk - 2)
    w = (kf - k0)[:, None]
    return ((1 - w) * sec[k0] + w * sec[k0 + 1]).astype(np.float32)


def section_vectors(s, zq, upar, w, n_across=28, aspect=1.0, ref_speed=20.0):
    """In-plane arrows. aspect = (km of z per pixel)/(km of s per pixel)."""
    si = max(1, s.size // n_across)
    zi = max(1, int(round(zq.size / max(n_across * 0.45, 1))))
    S, Z = np.meshgrid(s[si // 2::si], zq[zi // 2::zi])
    U, W = upar[zi // 2::zi, si // 2::si], w[zi // 2::zi, si // 2::si]
    spacing = (s[-1] - s[0]) / n_across
    k = 0.9 * spacing / ref_speed
    good = np.isfinite(U) & np.isfinite(W) & (np.hypot(U, W) > 0.3)
    x0, y0 = S[good], Z[good]
    # aspect converts so the arrow's on-screen direction is the true (u, w)
    x1, y1 = x0 + U[good] * k, y0 + W[good] * k * aspect
    ang = np.arctan2(W[good], U[good]) - np.pi / 2
    return dict(x0=x0, y0=y0, x1=x1, y1=y1, angle=ang)
