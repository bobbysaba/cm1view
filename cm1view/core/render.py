"""Pure computations behind the map and cross-section views.

All functions here are called from worker threads and return plain dicts
of numpy arrays ready to drop into Bokeh ColumnDataSources.
"""

import math

import numpy as np
import contourpy
from scipy.ndimage import map_coordinates

from . import vectors as vectors_mod
from .fields import finite_sample, palette


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


def contour_fill(x, y, a, levels, open_ends=True):
    """Filled bands as Bokeh multi_polygons rows (one row per band).  open_ends: the
    first / last band takes in the values below / above the levels too."""
    xs, ys, val = [], [], []
    gen = contourpy.contour_generator(x, y, _masked(a), fill_type="OuterOffset")
    lv = np.asarray(levels, dtype=float)
    lo_edges = np.concatenate(([-1e30] if open_ends else lv[:1], lv[1:-1]))
    hi_edges = np.concatenate((lv[1:-1], [1e30] if open_ends else lv[-1:]))
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
    """Arrow segments (data units) ~n_across arrows across the window; ref_speed (any
    vector's units) is drawn 0.9 arrow spacings long."""
    nx = x.size
    s = max(1, nx // max(n_across, 1))
    xs, ys = np.meshgrid(x[s // 2::s], y[s // 2::s])
    uu, vv = u[s // 2::s, s // 2::s], v[s // 2::s, s // 2::s]
    spacing = (x[-1] - x[0]) / max(n_across, 1)
    k = 0.9 * spacing / ref_speed
    good = np.isfinite(uu) & np.isfinite(vv) & (np.hypot(uu, vv) > 0.01 * ref_speed)
    x0, y0 = xs[good], ys[good]
    x1, y1 = x0 + uu[good] * k, y0 + vv[good] * k
    ang = np.arctan2(vv[good], uu[good]) - np.pi / 2
    return dict(x0=x0, y0=y0, x1=x1, y1=y1, angle=ang), spacing


def streamlines(x, y, u, v, density=1.2):
    """2D streamlines (matplotlib's streamplot) as polylines + one arrowhead per line:
    ({'xs', 'ys'}, {'x', 'y', 'angle'}).  x, y evenly spaced."""
    from matplotlib.figure import Figure

    out, heads = dict(xs=[], ys=[]), dict(x=[], y=[], angle=[])
    if x.size < 3 or y.size < 3 or not np.isfinite(u).any():
        return out, heads
    ax = Figure().add_subplot()
    # (float32 grid coordinates are not equally spaced to streamplot's tolerance)
    x, y = np.linspace(x[0], x[-1], x.size), np.linspace(y[0], y[-1], y.size)
    sp = ax.streamplot(x, y, np.ma.masked_invalid(u), np.ma.masked_invalid(v),
                       density=density)
    for sg in sp.lines.get_segments():  # one polyline per streamline
        a = np.asarray(sg)
        keep = np.concatenate(([True], np.any(np.diff(a, axis=0) != 0, axis=1)))
        a = a[keep]  # (repeated points)
        if len(a) < 3:
            continue
        out["xs"].append(a[:, 0])
        out["ys"].append(a[:, 1])
        m = len(a) // 2
        d = a[m + 1] - a[m - 1]
        heads["x"].append(a[m, 0])
        heads["y"].append(a[m, 1])
        heads["angle"].append(float(np.arctan2(d[1], d[0]) - np.pi / 2))
    return out, heads


# ------------------------------------------------------------ map
def fill_palette(spec):
    if spec["style"] == "contourf":
        n = max(len(spec["levels"]) - 1, 1)
        full = palette(spec["cmap"], 256, spec["rev"], spec["lo"], spec["hi"])
        return [full[min(255, int((i + 0.5) * 256 / n))] for i in range(n)]  # band midpoints
    return palette(spec["cmap"], 256, spec["rev"], spec["lo"], spec["hi"])


def _map_fill(F, f, t, win, fstorm):
    a = F.plane(f["var"], t, f["mode"], f["level"], storm=fstorm)
    m = f.get("minus")  # (a difference: {F, t} of the other run / time)
    if m:
        a = a - minus_plane(F, m["F"], f["var"], m["t"], f["mode"], f["level"], fstorm)
        lo, hi = diff_range(a) if f["auto"] else (f["vmin"], f["vmax"])
    else:
        lo, hi = F.auto_range(f["var"], a) if f["auto"] else (f["vmin"], f["vmax"])
    if hi <= lo:
        hi = lo + 1e-6
    x, y, ac = _crop(F.run, a, win)
    return fill_bands(x, y, ac, lo, hi, f)


def fill_bands(x, y, a, lo, hi, f):
    """A fill (map or cross-section) as an image or filled-contour bands from lo to hi.
    f: style, nlev, cmap, rev, clip (values outside lo..hi left uncoloured)."""
    clip = f.get("clip", False)
    fill = dict(style=f["style"], lo=lo, hi=hi, cmap=f["cmap"], rev=f["rev"])
    if f["style"] == "contourf":
        levels = np.linspace(lo, hi, max(int(f["nlev"]), 2) + 1)
        fill.update(levels=levels, poly=contour_fill(x, y, a, levels, open_ends=not clip))
    else:
        if clip:
            a = np.where((a >= lo) & (a <= hi), a, np.nan)
        fill.update(image=image_data(x, y, a))
    fill["palette"] = fill_palette(fill)
    return fill


def _map_vectors(F, o, t, win, storm):
    """{"vec": arrows} or {"stream": (lines, heads)} of map vector layer o."""
    u, v = vectors_mod.plane(F, o["q"], t, "height", o["level"], o["frame"], storm)
    x, y, uc = _crop(F.run, u, win)
    _, _, vc = _crop(F.run, v, win)
    if o["style"] == "streamlines":
        return dict(stream=streamlines(x, y, uc, vc, o["density"] / 20.0))
    return dict(vec=vectors(x, y, uc, vc, o["density"], o["ref"])[0])


def compute_map(F, spec):
    run, t = F.run, spec["t"]
    win = view_window(run, spec["view"], spec["maxpix"])
    out = dict(win=win)

    if spec["fill"]["var"]:
        out["fill"] = _map_fill(F, spec["fill"], t, win, spec.get("fstorm"))
    # more fills drawn over the first; clip: clear outside their range
    out["fills"] = [_map_fill(F, f, t, win, spec.get("fstorm"))
                    if f["on"] and f["var"] else None for f in spec.get("fills", [])]

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

    # vector layers: arrows or streamlines each
    out["vecs"] = [_map_vectors(F, o, t, win, spec["storm"]) if o["on"] else None
                   for o in spec["vecs"]]
    return out


# ------------------------------------------------------------ differences
def same_grid(u, v):
    u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
    return u.shape == v.shape and np.allclose(u, v, atol=1e-6)


def regrid(a, x, y, xn, yn):
    """2-D array a on the rectilinear grid (y, x) interpolated bilinearly onto (yn, xn)
    (NaN outside a's grid)."""
    a, x, y = np.asarray(a, dtype=float), np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    rows = np.array([np.interp(xn, x, r, left=np.nan, right=np.nan) for r in a])
    return np.array([np.interp(yn, y, c, left=np.nan, right=np.nan) for c in rows.T]).T


def diff_range(a):
    """Auto range of a difference: symmetric about 0 (99.5th percentile of |a|)."""
    sub = finite_sample(a)
    if sub.size == 0:
        return (-1.0, 1.0)
    m = float(np.percentile(np.abs(sub), 99.5)) or 1.0
    return (-m, m)


def _other_has(F, F2, name):
    if name not in F2:
        raise ValueError(f"difference: {F[name].label} is not in {F2.run.name}")


def minus_plane(F, F2, name, t2, mode, level, fstorm=None):
    """Field `name` of the run of F2 at time index t2, on the grid of F's run (what a
    map difference subtracts): as is on the same grid, else interpolated (NaN outside
    the other run's domain)."""
    _other_has(F, F2, name)
    b = F2.plane(name, t2, mode, level, storm=fstorm)
    r, r2 = F.run, F2.run
    if r2 is r or (same_grid(r.xh, r2.xh) and same_grid(r.yh, r2.yh)):
        return b
    return regrid(b, r2.xh, r2.yh, r.xh, r.yh).astype(np.float32)


def minus_section(F, F2, name, t2, A, B, s, zq, fstorm=None):
    """Field `name` of the run of F2 at time index t2 along the section A–B, on the
    distances s and heights zq of F's section (NaN outside the other run's domain).
    Its 3D field must be loaded (CM1Run.load_volumes)."""
    _other_has(F, F2, name)
    r2 = F2.run
    s2, fi, fj, _ = section_coords(r2, A, B)
    b = sample_section(r2, F2.volume(name, t2, fstorm), fi, fj, zq)
    out = (fi < -0.5) | (fi > r2.ni - 0.5) | (fj < -0.5) | (fj > r2.nj - 0.5)
    b[:, out] = np.nan
    if s2.size != np.size(s):
        b = regrid(b, s2, zq, s, zq).astype(np.float32)
    return b


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
    good = np.isfinite(U) & np.isfinite(W) & (np.hypot(U, W) > 0.015 * ref_speed)
    x0, y0 = S[good], Z[good]
    # aspect converts so the arrow's on-screen direction is the true (u, w)
    x1, y1 = x0 + U[good] * k, y0 + W[good] * k * aspect
    ang = np.arctan2(W[good], U[good]) - np.pi / 2
    return dict(x0=x0, y0=y0, x1=x1, y1=y1, angle=ang)
