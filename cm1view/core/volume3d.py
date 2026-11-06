"""The 3D scene: isosurfaces, floor, vectors and streamlines computed server side
(build_scene), and the viewer's Plotly WebGL figure of them (scene_figure).

Heights.  On a flat run z is the same everywhere: the scene's z is run.z (above ground
and sea level alike).  On a run whose levels follow the terrain (run.terrain) the
scene is above sea level: every column has its own level heights at each time
(run.heights(t, "msl")), which map a height to a fractional level column by column
(columns, frac_level); isosurfaces are found on the model levels and their vertices
placed at those heights; the terrain is drawn as a surface (the floor lies on it); the
floor's, the vectors' and the streamline seeds' heights are above the ground there.
Flat runs take exactly the old path."""

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from skimage.measure import marching_cubes

from . import vectors
from .fields import _NWS_REF, mpl_cmap
from ..theme import BG, GRID, MUTED, TEXT

MAX_FACES = 700_000
SELECTED = "#fde047"  # highlighted streamline
DIM = "#475569"  # the other streamlines while one is selected or pinned
DIM_OPACITY = 0.2  # and how opaque they are meanwhile
# pinned streamlines, in pin order (cycled); none of them is the selection's yellow
PIN_COLORS = ["#38bdf8", "#f472b6", "#a3e635", "#fb923c", "#c084fc", "#2dd4bf", "#f87171",
              "#e2e8f0"]
# the pinned trace's colour is a pin's index in PIN_COLORS (numbers, not a string per
# point) on this stepped scale; DIM_SCALE greys the streamlines without resending colours
PIN_SCALE = [[f, c] for k, c in enumerate(PIN_COLORS)
             for f in (k / len(PIN_COLORS), (k + 1) / len(PIN_COLORS))]
DIM_SCALE = [[0.0, DIM], [1.0, DIM]]


def box_indices(run, box):
    x0, x1, y0, y1 = box
    i0, j0 = run.ij(min(x0, x1), min(y0, y1))
    i1, j1 = run.ij(max(x0, x1), max(y0, y1))
    return i0, i1 + 1, j0, j1 + 1


def _fij(run, x, y):
    """Fractional grid indices (i, j) of points x, y (km)."""
    return ((np.asarray(x, np.float64) - run.xh[0]) / (run.dx / 1000.0),
            (np.asarray(y, np.float64) - run.yh[0]) / (run.dy / 1000.0))


def columns(H, fi, fj):
    """(n, nk) columns of an (nk, nj, ni) array H, bilinear at fractional grid points
    (fi, fj), held at the edges (a 2D H: (n,) values)."""
    H = np.asarray(H)
    flat = H.ndim == 2
    if flat:
        H = H[None]
    nk, nj, ni = H.shape
    fi = np.clip(np.nan_to_num(np.asarray(fi, np.float64)), 0.0, ni - 1)
    fj = np.clip(np.nan_to_num(np.asarray(fj, np.float64)), 0.0, nj - 1)
    i0 = np.minimum(np.floor(fi).astype(np.intp), max(ni - 2, 0))
    j0 = np.minimum(np.floor(fj).astype(np.intp), max(nj - 2, 0))
    i1, j1 = np.minimum(i0 + 1, ni - 1), np.minimum(j0 + 1, nj - 1)
    wi, wj = np.clip(fi - i0, 0.0, 1.0), np.clip(fj - j0, 0.0, 1.0)
    a = ((1 - wi) * (1 - wj) * H[:, j0, i0] + wi * (1 - wj) * H[:, j0, i1]
         + (1 - wi) * wj * H[:, j1, i0] + wi * wj * H[:, j1, i1])
    return a[0] if flat else a.T


def frac_level(Hc, z):
    """Fractional level index of heights z (n,) in columns Hc (n, nk) whose heights
    increase upward, held at the lowest and highest levels (as np.interp)."""
    Hc = np.asarray(Hc, np.float64)
    z = np.asarray(z, np.float64)
    n, nk = Hc.shape
    if nk == 1:
        return np.zeros(n)
    k1 = np.clip((Hc < z[:, None]).sum(axis=1), 1, nk - 1)
    r = np.arange(n)
    z0, z1 = Hc[r, k1 - 1], Hc[r, k1]
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.clip((z - z0) / (z1 - z0), 0.0, 1.0)
    return k1 - 1 + np.where(np.isfinite(w), w, 0.0)


def level_heights(run):
    """Heights (km) the stride and level cut go by without a time: run.z, on a terrain
    run above sea level over the lowest ground (so no level is left out)."""
    z = np.asarray(run.z, np.float64)
    return z + float(np.min(run.terrain_height())) if run.terrain else z


def top_height(run):
    """The highest height (km) a scene can reach: run.z[-1], on a terrain run above sea
    level over the highest ground."""
    return float(run.z[-1]) + (float(np.max(run.terrain_height())) if run.terrain else 0.0)


def auto_stride(run, box, zmax, max_voxels):
    i0, i1, j0, j1 = box_indices(run, box)
    kmax = int(np.searchsorted(level_heights(run), zmax)) + 1
    n = (i1 - i0) * (j1 - j0) * kmax
    return max(1, int(np.ceil(np.sqrt(n / max_voxels))))


def isosurface(run, vol, box, value, stride, smooth, zmax, H=None):
    """Vertices (km) and faces of the `value` isosurface inside `box`.  H: a terrain
    run's level heights (km MSL, (nk, nj, ni)) at the time: the surface is found on the
    model levels and its vertices placed at those heights."""
    i0, i1, j0, j1 = box_indices(run, box)
    if H is None:
        kmax = min(run.nk, int(np.searchsorted(run.z, zmax)) + 1)
    else:  # (up to the first level above zmax everywhere in the box)
        Hb = H[:, j0:j1:stride, i0:i1:stride]
        low = Hb.reshape(Hb.shape[0], -1).min(axis=1) if Hb.size else np.asarray(run.z)
        kmax = min(run.nk, int(np.searchsorted(low, zmax)) + 1)
    sub = np.asarray(vol[:kmax, j0:j1:stride, i0:i1:stride], dtype=np.float32)
    if smooth > 0:
        sub = gaussian_filter(sub, smooth)
    if sub.size == 0 or min(sub.shape) < 2 or not (np.nanmin(sub) < value < np.nanmax(sub)):
        return None
    step = 1
    while True:
        verts, faces, _, _ = marching_cubes(sub, level=value, step_size=step,
                                            allow_degenerate=False)
        if len(faces) <= MAX_FACES or step >= 4:
            break
        step += 1
    kz, jy, ix = verts.T
    if H is None:
        z = np.interp(kz, np.arange(kmax), run.z[:kmax])
    else:
        z = map_coordinates(np.asarray(Hb[:kmax], np.float64), verts.T, order=1,
                            mode="nearest")
    y = run.yh[j0] + jy * stride * run.dy / 1000.0
    x = run.xh[i0] + ix * stride * run.dx / 1000.0
    return dict(x=x.astype(np.float32), y=y.astype(np.float32), z=z.astype(np.float32),
                faces=faces.astype(np.int32), step=step)


def surface_vectors(run, u, v, box, n_across=20, ref_speed=20.0):
    """Horizontal arrows (shaft + V head) as NaN-separated x/y polylines, in km.
    u, v: (nj, ni) planes in the wanted frame (any vector: ref_speed in its units)."""
    i0, i1, j0, j1 = box_indices(run, box)
    s = max(1, (i1 - i0) // max(n_across, 1))
    jj, ii = np.mgrid[j0 + s // 2:j1:s, i0 + s // 2:i1:s]
    uu, vv = u[jj, ii].ravel(), v[jj, ii].ravel()
    x, y = run.xh[ii].ravel(), run.yh[jj].ravel()
    spd = np.hypot(uu, vv)
    good = np.isfinite(spd) & (spd > 0.01 * ref_speed)
    x, y, uu, vv, spd = x[good], y[good], uu[good], vv[good], spd[good]
    k = 0.9 * s * run.dx / 1000.0 / ref_speed  # km per unit
    x1, y1 = x + uu * k, y + vv * k
    hl = np.minimum(0.35 * spd * k, 0.3 * s * run.dx / 1000.0)  # head length (km)
    ang = np.arctan2(vv, uu)
    nan = np.full_like(x, np.nan)
    hx = [x1 - hl * np.cos(ang + a) for a in (0.45, -0.45)]
    hy = [y1 - hl * np.sin(ang + a) for a in (0.45, -0.45)]
    # per arrow: tail -> tip -> barb1, gap, tip -> barb2, gap
    X = np.stack([x, x1, hx[0], nan, x1, hx[1], nan], axis=1).ravel()
    Y = np.stack([y, y1, hy[0], nan, y1, hy[1], nan], axis=1).ravel()
    return X, Y, spd


def streamlines(run, U, V, W, box, ztop, seed_z, n_seed=12, length=30.0,
                direction="forward", offset=(0.0, 0.0), seed_box=None, H=None):
    """Instantaneous 3D streamlines of (U - offset[0], V - offset[1], W).

    U, V, W are full (nk, nj, ni) volumes in m/s.  Seeds form an n_seed x n_seed grid
    inside `seed_box` (default `box`) at height seed_z (km); lines run until they
    leave `box` (ending on its edge), reach `length` km ("both": length / 2 each way),
    or stall: speed under 0.3 m/s, or the flow turning back within a step (a stagnation
    point, where a direction-only tracer would zig-zag).  Lines that reach the lowest
    level slide along it.  Integration is RK2 on the flow's direction with a step of
    0.6 dx, shortened so it climbs at most 0.8 of the local level spacing.
    H: a terrain run's level heights (km MSL) at the time: z is then above sea level
    (ztop too), seed_z above the ground under each seed, and the lowest level is each
    column's own.
    Returns x, y, z (km), w (m/s) as NaN-separated arrays, plus `segs`: per line
    (first, end, seed) indices into those arrays, or None."""
    x0, x1, y0, y1 = box
    dxk, dyk = run.dx / 1000.0, run.dy / 1000.0
    if direction == "both":
        length = 0.5 * length
    ds = max(0.6 * dxk, length / 500.0)  # km per step
    nstep = 4 * int(np.ceil(length / ds))  # room for the shortened (steep) steps
    zlo = float(run.z[0])
    kidx = np.arange(run.nk, dtype=np.float64)
    dz = np.gradient(np.asarray(run.z, np.float64)) if run.nk > 1 else np.array([ds])
    lo = np.array([x0, y0, -np.inf])
    hi = np.array([x1, y1, ztop])
    cu, cv = offset

    def cols(p):  # (terrain) the level heights of the points' columns
        return columns(H, *_fij(run, p[:, 0], p[:, 1]))

    def lowest(p):  # the lowest level's height under the points
        return zlo if H is None else cols(p)[:, 0]

    def spacing(p):  # the level spacing at the points
        if H is None:
            return np.interp(p[:, 2], run.z, dz)
        Hc = cols(p)
        if Hc.shape[1] == 1:
            return np.full(len(p), ds)
        k0 = np.clip(np.floor(frac_level(Hc, p[:, 2])).astype(np.intp), 0, Hc.shape[1] - 2)
        r = np.arange(len(p))
        return Hc[r, k0 + 1] - Hc[r, k0]

    def vel(p):
        fi = (p[:, 0] - run.xh[0]) / dxk
        fj = (p[:, 1] - run.yh[0]) / dyk
        fk = np.interp(p[:, 2], run.z, kidx) if H is None else frac_level(cols(p), p[:, 2])
        c = np.stack([fk, fj, fi])
        u = map_coordinates(U, c, order=1, mode="nearest") - cu
        v = map_coordinates(V, c, order=1, mode="nearest") - cv
        w = map_coordinates(W, c, order=1, mode="nearest")
        return np.stack([u, v, w], axis=1)

    def unit(vv):
        sp = np.linalg.norm(vv, axis=1, keepdims=True)
        return vv / np.maximum(sp, 1e-6), sp[:, 0]

    s0, s1, t0, t1 = seed_box or box
    mx, my = 0.04 * (s1 - s0), 0.04 * (t1 - t0)
    gx, gy = np.meshgrid(np.linspace(s0 + mx, s1 - mx, n_seed),
                         np.linspace(t0 + my, t1 - my, n_seed))
    seeds = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, max(seed_z, zlo))], axis=1)
    if H is not None:  # (seed_z above the ground under each seed)
        g = columns(run.terrain_height(), *_fij(run, seeds[:, 0], seeds[:, 1]))
        seeds[:, 2] = np.maximum(g + seed_z, lowest(seeds))

    lines, seed_col = [], 0
    for sign in {"forward": (1,), "backward": (-1,), "both": (-1, 1)}[direction]:
        p = seeds.copy()
        alive = np.ones(len(p), bool)
        done = np.zeros(len(p))  # km travelled
        track = [p.copy()]
        for _ in range(nstep):
            d1, sp = unit(vel(p))
            dzl = spacing(p)
            h = np.minimum(ds, 0.8 * dzl / np.maximum(np.abs(d1[:, 2]), 1e-6))
            h = np.minimum(h, length - done)[:, None]
            mid = p + sign * 0.5 * h * d1
            mid[:, 2] = np.maximum(mid[:, 2], lowest(mid))
            d2, _ = unit(vel(mid))
            q = p + sign * h * d2
            q[:, 2] = np.maximum(q[:, 2], lowest(q))  # slide along the lowest level
            alive &= (sp > 0.3) & (np.einsum("ij,ij->i", d1, d2) > 0.0)
            # a step that leaves the region ends the line on the region's edge
            dq = q - p
            with np.errstate(divide="ignore", invalid="ignore"):
                f = np.where(q > hi, (hi - p) / dq, np.where(q < lo, (lo - p) / dq, 1.0))
            f = np.clip(np.nan_to_num(f.min(axis=1), nan=1.0), 0.0, 1.0)
            q = p + f[:, None] * dq
            # (a step landing just on the edge ends there too, not with a 0-length step)
            out = (f < 1.0) | np.any(np.isclose(q, lo, rtol=0.0, atol=1e-6)
                                     | np.isclose(q, hi, rtol=0.0, atol=1e-6), axis=1)
            done += f * h[:, 0]
            q[~alive] = np.nan
            alive &= ~out & (done < length - 1e-9)
            p = np.where(alive[:, None], q, p)
            track.append(q)
            if not alive.any():
                break
        tr = np.stack(track, axis=1)  # (nseed, nt, 3); NaN once a line stops
        if sign < 0:
            tr = tr[:, ::-1]
            seed_col = tr.shape[1] - 1  # the seed ends the backward half
        lines.append(tr)
    if direction == "both":  # join backward and forward halves at the seed
        lines = [np.concatenate([lines[0], lines[1][:, 1:]], axis=1)]
    tr = lines[0]

    xs, ys, zs, segs, n0 = [], [], [], [], 0
    for line in tr:
        ok = np.isfinite(line[:, 0])
        seed = int(ok[:seed_col].sum())
        line = line[ok]
        if len(line) < 4:
            continue
        xs.append(np.append(line[:, 0], np.nan))
        ys.append(np.append(line[:, 1], np.nan))
        zs.append(np.append(line[:, 2], np.nan))
        segs.append((n0, n0 + len(line), n0 + seed))
        n0 += len(line) + 1
    if not xs:
        return None
    x, y, z = np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)
    ok = np.isfinite(x)
    pts = np.stack([x[ok], y[ok], z[ok]], axis=1)
    w = np.full_like(x, np.nan)
    w[ok] = vel(pts)[:, 2]
    return dict(x=x.astype(np.float32), y=y.astype(np.float32), z=z.astype(np.float32),
                w=w.astype(np.float32), n=len(xs), segs=np.array(segs, dtype=np.int64))


def sample_points(run, vol, x, y, z, t=None, H=None):
    """Trilinear values of a (nk, nj, ni) volume at points (km).  On a terrain run z is
    above sea level, placed among the levels of the point's column at time t (or of
    the level heights H, km MSL, given instead)."""
    fi = (np.asarray(x) - run.xh[0]) / (run.dx / 1000.0)
    fj = (np.asarray(y) - run.yh[0]) / (run.dy / 1000.0)
    if not run.terrain:
        fk = np.interp(z, run.z, np.arange(run.nk, dtype=np.float64))
    else:
        if H is None:
            if t is None:
                raise ValueError("a terrain run's points need the time (their heights)")
            H = run.heights(t, "msl")
        fk = frac_level(columns(H, fi, fj), np.ravel(z)).reshape(np.shape(z))
    return map_coordinates(vol, np.stack([fk, fj, fi]), order=1, mode="nearest")


def frame_offset(run, frame, storm):
    """What to subtract from grid-relative (u, v) to get the wanted frame."""
    from .vectors import frame_of
    frame = frame_of(run, frame)
    if frame == "ground":
        return (-run.umove, -run.vmove)
    if frame == "storm":
        return (storm[0] - run.umove, storm[1] - run.vmove)
    return (0.0, 0.0)


def floor_surface(run, F, fs, box, t, fstorm):
    """The floor surface (None when off): the field over the region, thinned to about
    300 points across, with its colormap (name, reversed), plotly colorscale and range."""
    name = fs["var"]
    if not fs["on"] or name not in F:
        return None
    d = F[name]
    i0, i1, j0, j1 = box_indices(run, box)
    gs = max(1, int(np.ceil(max(i1 - i0, j1 - j0) / 300)))
    a = F.plane(name, t, "height", fs["z"], storm=fstorm[0])[j0:j1:gs, i0:i1:gs]
    a = np.asarray(a, np.float64)
    cmap = d.cmap if fs["cmap"] == "Field default" else fs["cmap"]
    title = d.title
    if d.ndim == 3:
        title += f' @ {max(fs["z"], float(run.z[0])) * 1000:.0f} m' + \
            (" AGL" if run.terrain else "")
    if d.storm:
        title += f" ({fstorm[1]})"
    if fs["range"] == "custom" and fs["hi"] > fs["lo"]:
        lo, hi = fs["lo"], fs["hi"]
    elif cmap == "reflectivity" and not fs["rev"]:
        lo, hi = 0.0, 75.0  # the stepped NWS scale is laid out for 0-75 dBZ
    else:
        lo, hi = floor_range(a, d.vrange, d.diverging, fs["range"])
    out = dict(x=run.xh[i0:i1:gs], y=run.yh[j0:j1:gs], a=a, lo=lo, hi=hi, title=title,
               cmap=cmap, rev=fs["rev"], colorscale=floor_colorscale(cmap, fs["rev"]))
    if run.terrain:  # (lying on the ground)
        out["z"] = terrain_surface(run, box)["z"]
    return out


def terrain_surface(run, box):
    """A terrain run's ground over the region (km MSL), thinned like the floor (about 300
    points across): dict(x, y, z); None on a flat run."""
    if not run.terrain:
        return None
    i0, i1, j0, j1 = box_indices(run, box)
    gs = max(1, int(np.ceil(max(i1 - i0, j1 - j0) / 300)))
    z = np.asarray(run.terrain_height(), np.float64)[j0:j1:gs, i0:i1:gs]
    return dict(x=run.xh[i0:i1:gs], y=run.yh[j0:j1:gs], z=z)


def ground_at(run, x, y):
    """The ground's height (km MSL) at points x, y (km): 0 on a flat run; NaN where x
    or y is."""
    x, y = np.asarray(x, np.float64), np.asarray(y, np.float64)
    if not run.terrain:
        return np.zeros(np.broadcast(x, y).shape)
    g = columns(run.terrain_height(), *_fij(run, x, y))
    return np.where(np.isfinite(x) & np.isfinite(y), g, np.nan)


def seed_ring(run, seed_box, seed_z, n=24):
    """(m, 3) points (km MSL) of a terrain run's seed box outline at seed_z km above the
    ground (at least the lowest level), n points a side."""
    s0, s1, t0, t1 = seed_box
    f = np.linspace(0.0, 1.0, n)
    x = np.concatenate([s0 + (s1 - s0) * f, np.full(n, s1), s1 - (s1 - s0) * f,
                        np.full(n, s0)])
    y = np.concatenate([np.full(n, t0), t0 + (t1 - t0) * f, np.full(n, t1),
                        t1 - (t1 - t0) * f])
    return np.stack([x, y, ground_at(run, x, y) + seed_z], axis=1)


def build_scene(run, F, scene, progress=None, cancelled=None, cache=None):
    """Everything a 3D scene draws, as arrays (no plotting): the isosurface meshes, the
    floor, the vector planes and the streamlines, for the plotly scene of the viewer
    and the rendered 3D figure alike.

    scene: the request dict (t, box, ztop, exag, smooth, res, isos, vecs, stream, ground,
    storm, fstorm) built by the viewer's request_3d.  progress(done, total, name) reports
    the loading; cancelled() stops it (then None is returned).  cache: a dict kept by the
    caller across calls; the streamlines are traced again only when what they depend on
    changed (an isosurface or floor edit keeps the same lines).

    On a terrain run everything is above sea level (module notes) and `terrain` is the
    ground's surface (terrain_surface; None on a flat run).

    Returns dict(meshes, ground, vecs, stream, notes, stride, off, terrain)."""
    t, box, ztop = scene["t"], scene["box"], scene["ztop"]
    ss = scene["stream"]
    names = []
    for iso in scene["isos"]:
        names += F.native_deps(iso["var"])
    if ss["on"]:
        names += ["uinterp", "vinterp", "winterp"]
    need_h = run.terrain and bool(scene["isos"] or ss["on"])
    if need_h and "zmsl" in run.vars:
        names += ["zmsl"]  # (the levels' heights: run.heights)
    if not run.load_volumes(names, t, progress=progress, cancelled=cancelled):
        return None
    H = run.heights(t, "msl") if need_h else None
    stride = scene["res"] or auto_stride(run, box, ztop, 12e6)
    meshes, notes = [], []
    for iso in scene["isos"]:
        d = F[iso["var"]]
        m = isosurface(run, F.volume(iso["var"], t, scene["fstorm"][0]), box, iso["val"],
                       stride, scene["smooth"], ztop, H)
        name = f'{d.label} = {iso["val"]:g} {d.units}'
        if d.storm:
            name += f' ({scene["fstorm"][1]})'
        if m is None:
            notes.append(f"{name}: no surface in region")
            continue
        if m["step"] > 1:
            notes.append(f"{name}: coarsened ×{m['step']} (mesh too large)")
        m.update(color=iso["color"], opacity=iso["op"], name=name)
        meshes.append(m)
    ground = floor_surface(run, F, scene["ground"], box, t, scene["fstorm"])
    vecs = []
    for vs in scene["vecs"]:
        u, v = vectors.plane(F, vs["q"], t, "height", vs["level"], vs["frame"],
                             scene["storm"])
        X, Y, _ = surface_vectors(run, u, v, box, vs["density"], vs["ref"])
        zlev = max(vs["level"], float(run.z[0]))
        # drawn at least 2% of the scene height up: right at z = 0 the opaque
        # reflectivity floor hides them (depth-buffer ties); label keeps zlev.  On a
        # terrain run that far above the ground under each point (z per point)
        zd = max(zlev, 0.02 * ztop)
        vecs.append(dict(x=X, y=Y, z=ground_at(run, X, Y) + zd if run.terrain else zd,
                         color=vs["color"],
                         name=f'{vectors.label(vs["q"], vs["frame"])} @ '
                              f'{zlev * 1000:.0f} m' + (" AGL" if run.terrain else "")))
    off = frame_offset(run, ss["frame"], scene["storm"])
    stream = None
    if ss["on"]:
        key = (id(run), t, box, ztop, ss["z"], ss["n"], ss["length"], ss["dir"], off,
               ss["seed_box"])
        if cache is not None and cache.get("stream_key") == key:
            stream = cache["stream"]
        else:
            stream = streamlines(run, run.volume("uinterp", t), run.volume("vinterp", t),
                                 run.volume("winterp", t), box, ztop, ss["z"], ss["n"],
                                 ss["length"], ss["dir"], off, seed_box=ss["seed_box"],
                               H=H)
            if cache is not None:
                cache.update(stream_key=key, stream=stream)
        stream = dict(stream) if stream is not None else None
        if stream is None:
            notes.append("streamlines: none (calm or outside region)")
        else:
            stream.update(color_by=ss["color_by"], seed_box=ss["seed_box"],
                          seed_z=max(ss["z"], float(run.z[0])),
                          name=f'Streamlines ({vectors.FRAME_SHORT[ss["frame"]]}, '
                               f'{stream["n"]})')
            if run.terrain and ss["seed_box"] is not None:  # (the outline on the ground)
                stream["seed_ring"] = seed_ring(run, ss["seed_box"], stream["seed_z"])
    return dict(meshes=meshes, ground=ground, vecs=vecs, stream=stream, notes=notes,
                stride=stride, off=off, terrain=terrain_surface(run, box))

def _ref_colorscale():
    """Stepped NWS reflectivity colorscale for 0-75 dBZ (dark below 5)."""
    cs = [[0.0, "#1a2230"], [5 / 75 - 1e-4, "#1a2230"]]
    for n, c in enumerate(_NWS_REF):
        a, b = (5 + 5 * n) / 75, min((10 + 5 * n) / 75, 1.0)
        cs += [[a, c], [b - 1e-4 if b < 1 else 1.0, c]]
    return cs


def floor_colorscale(cmap, reverse=False, n=32):
    """Plotly colorscale for the floor: the stepped NWS scale for 'reflectivity' (meant
    for a 0-75 dBZ range), otherwise n stops of the matplotlib colormap."""
    if cmap == "reflectivity" and not reverse:
        return _ref_colorscale()
    cm = mpl_cmap(cmap, reverse)
    return [[float(f), "rgb({:.0f},{:.0f},{:.0f})".format(*(255 * np.asarray(cm(f)[:3])))]
            for f in np.linspace(0.0, 1.0, n)]


def floor_range(a, vrange=None, diverging=False, mode="data"):
    """(lo, hi) for the floor colours.  mode 'field': the field's display range (data
    when it has none); 'data': 1st-99th percentiles, symmetric about 0 if diverging."""
    if mode == "field" and vrange is not None:
        return float(vrange[0]), float(vrange[1])
    v = np.asarray(a, np.float64)
    v = v[np.isfinite(v)]
    if not v.size:
        return 0.0, 1.0
    if diverging:
        m = float(np.percentile(np.abs(v), 99)) or float(np.abs(v).max()) or 1.0
        return -m, m
    lo, hi = (float(x) for x in np.percentile(v, [1, 99]))
    return (lo, hi) if hi > lo else (lo - 0.5, lo + 0.5)


CAMERAS = {  # eye positions (scene units), plotly convention
    "oblique": dict(eye=dict(x=1.25, y=-1.45, z=0.75)),
    "top": dict(eye=dict(x=0.0, y=-0.01, z=2.2), up=dict(x=0, y=1, z=0)),
    "south": dict(eye=dict(x=0.0, y=-2.1, z=0.25)),
    "north": dict(eye=dict(x=0.0, y=2.1, z=0.25)),
    "west": dict(eye=dict(x=-2.1, y=0.0, z=0.25)),
    "east": dict(eye=dict(x=2.1, y=0.0, z=0.25)),
}


def stream_color(stream):
    """The streamlines' colour per point: w or height, by stream["color_by"]."""
    c = stream["w"] if stream["color_by"] == "w" else stream["z"]
    return np.nan_to_num(c, nan=0.0)


def scene_figure(meshes, ground, box, zmax, exag, title="", vectors=None, stream=None,
                 camera="oblique", revision="keep", dragmode="turntable", terrain=None):
    """terrain: a terrain run's ground (terrain_surface): z is then above sea level, the
    floor lies on the ground, and without a floor the ground is drawn plain."""
    import plotly.graph_objects as go

    fig = go.Figure()
    if ground is not None:  # dict(x, y, a, colorscale, lo, hi, title) for the floor
        ga = ground["a"]
        fig.add_trace(go.Surface(
            x=ground["x"], y=ground["y"],
            z=ground["z"] if ground.get("z") is not None else np.zeros_like(ga),
            surfacecolor=np.nan_to_num(ga, nan=ground["lo"]),
            colorscale=ground["colorscale"], cmin=ground["lo"], cmax=ground["hi"],
            colorbar=dict(title=dict(text=ground["title"], side="top",
                                     font=dict(color=MUTED, size=11)),
                          orientation="h", thickness=10, len=0.35, x=0.5, y=0.0,
                          yanchor="bottom", tickfont=dict(color=MUTED, size=10),
                          outlinewidth=0),
            hoverinfo="skip", lighting=dict(ambient=1.0, diffuse=0.0, specular=0.0),
            name="floor"))
    elif terrain is not None:  # the ground, plain
        fig.add_trace(go.Surface(
            x=terrain["x"], y=terrain["y"], z=terrain["z"], surfacecolor=terrain["z"],
            colorscale=[[0.0, "#3f4a3c"], [1.0, "#8a8f7a"]], showscale=False,
            hovertemplate="ground %{z:.2f} km<extra></extra>",
            lighting=dict(ambient=0.6, diffuse=0.6, specular=0.05), name="ground"))
    for m in meshes:
        f = m["faces"]
        fig.add_trace(go.Mesh3d(
            x=m["x"], y=m["y"], z=m["z"], i=f[:, 0], j=f[:, 1], k=f[:, 2],
            color=m["color"], opacity=m["opacity"], name=m["name"], showlegend=True,
            flatshading=False, hoverinfo="name",
            lighting=dict(ambient=0.35, diffuse=0.85, specular=0.35, roughness=0.5,
                          fresnel=0.15),
            lightposition=dict(x=2000, y=-1000, z=4000)))
    for vec in vectors or []:  # [dict(x, y, z, color, name)]: arrows at a height each
        fig.add_trace(go.Scatter3d(
            x=vec["x"], y=vec["y"], z=np.broadcast_to(vec["z"], np.shape(vec["x"])),
            mode="lines", line=dict(color=vec["color"], width=4),
            name=vec["name"], hoverinfo="skip", showlegend=True))
    if stream is not None:
        c = stream_color(stream)
        if stream["color_by"] == "w":
            m = float(max(np.percentile(np.abs(c), 99), 1.0))
            cs, lo, hi, ttl = "RdBu_r", -m, m, "w (m/s)"
        else:
            cs, lo, hi, ttl = "Viridis", 0.0, float(zmax), "z (km)"
        fig.add_trace(go.Scatter3d(
            x=stream["x"], y=stream["y"], z=stream["z"], mode="lines",
            line=dict(color=c, colorscale=cs, cmin=lo, cmax=hi, width=4,
                      colorbar=dict(title=dict(text=ttl, font=dict(color=MUTED, size=11)),
                                    thickness=12, len=0.5, x=1.0, y=0.5,
                                    tickfont=dict(color=MUTED, size=10),
                                    outlinewidth=0)),
            customdata=np.nan_to_num(stream["w"]), meta="stream",
            hovertemplate="z %{z:.2f} km · w %{customdata:.1f} m/s"
                          "<extra>click: select</extra>",
            name=stream["name"], showlegend=True))
        # pinned streamlines (NaN-separated, a PIN_COLORS index per point) and their
        # seeds, then the selected streamline and its seed: all filled in by the app on a
        # click
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="lines", meta="pinned",
                                   line=dict(color=[], colorscale=PIN_SCALE, cmin=-0.5,
                                             cmax=len(PIN_COLORS) - 0.5, width=7),
                                   connectgaps=False,
                                   hovertemplate="pinned streamline<extra>click: select"
                                                 "</extra>",
                                   name="Pinned streamlines", showlegend=False))
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="markers", meta="pinseeds",
                                   marker=dict(color=[], size=5, symbol="diamond",
                                               line=dict(color=BG, width=1)),
                                   hoverinfo="skip", name="Pinned seeds", showlegend=False))
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="lines", meta="selected",
                                   line=dict(color=SELECTED, width=11), hoverinfo="skip",
                                   name="Selected streamline", showlegend=False))
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="markers", meta="seed",
                                   marker=dict(color=SELECTED, size=6, symbol="diamond",
                                               line=dict(color=BG, width=1)),
                                   hoverinfo="skip", name="Seed", showlegend=False))
        # where the pointer is on the streamline card's plot, one marker per line
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="markers", meta="cursor",
                                   marker=dict(color=[], size=7, symbol="circle",
                                               line=dict(color=BG, width=2)),
                                   hoverinfo="skip", name="Cursor", showlegend=False))
        if stream.get("seed_box") is not None:  # outline of the seed box at seed height
            s0, s1, t0, t1 = stream["seed_box"]
            ring = stream.get("seed_ring")  # (a terrain run's: over the ground)
            fig.add_trace(go.Scatter3d(
                x=[s0, s1, s1, s0, s0] if ring is None else ring[:, 0],
                y=[t0, t0, t1, t1, t0] if ring is None else ring[:, 1],
                z=[stream["seed_z"]] * 5 if ring is None else ring[:, 2],
                mode="lines", hoverinfo="skip",
                line=dict(color=MUTED, width=2, dash="dash"), name="Seed box",
                showlegend=True))
    x0, x1, y0, y1 = box
    lx, ly = abs(x1 - x0), abs(y1 - y0)
    ax = dict(backgroundcolor=BG, gridcolor=GRID, zerolinecolor=GRID, color=MUTED,
              showbackground=True, title_font=dict(color=MUTED, size=11),
              tickfont=dict(color=MUTED, size=10))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=0, r=0, t=56, b=0), uirevision=revision,
        title=dict(text=title, font=dict(color=MUTED, size=12), x=0.99, xanchor="right",
                   y=0.02, yanchor="bottom"),
        legend=dict(bgcolor="rgba(17,23,35,0.8)", bordercolor=GRID, borderwidth=1,
                    font=dict(color=TEXT, size=11), x=0.01, y=0.99),
        scene=dict(
            xaxis=dict(ax, title="x (km)", range=[min(x0, x1), max(x0, x1)]),
            yaxis=dict(ax, title="y (km)", range=[min(y0, y1), max(y0, y1)]),
            zaxis=dict(ax, title="z (km)" if terrain is None else "z (km MSL)",
                       range=[0, zmax]),
            aspectmode="manual",
            aspectratio=dict(x=1.0, y=ly / max(lx, 1e-6), z=exag * zmax / max(lx, 1e-6)),
            camera=CAMERAS[camera], dragmode=dragmode,
        ),
    )
    return fig
