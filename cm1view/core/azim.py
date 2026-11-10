"""Azimuthal means: a 3D field reduced (mean, maximum or minimum) over rings around a
centre, in bins of radius at every model level of a layer, within a sector of
azimuths, at one output or over a time window (a storm-following composite).

A recipe says which values:
  field     any 3D field of the catalog (native or derived) on the scalar grid
  center    'track' (the run's tracked storm, shifted by `offset` km) or 'point'
            (`point` [x, y] grid km)
  ref       'motion' (azimuth 0 = the direction the storm moves) or 'north' (0 = grid
            north); azimuths go clockwise, so 90 is right of the motion (or east)
  az0, az1  the sector, degrees from az0 clockwise to az1 (0, 360: the full ring;
            e.g. 0, 90: the front-right quadrant)
  rmax, dr  the largest radius and the bin width (km; dr None: the grid spacing)
  z0, z1    the layer (km)
  op        'mean', 'max' or 'min' of every value in a bin (over a time window: of
            every value of every output)"""

import numpy as np

from . import series as ser
from .run import ahead, ahead_width

OPS = ("mean", "max", "min")
REFS = ("motion", "north")


def normalize(recipe):
    """A recipe with only the keys that matter for it (a stable cache key)."""
    r = dict(recipe)
    out = dict(field=r["field"], center="point" if r.get("center") == "point" else "track",
               ref="north" if r.get("ref") == "north" else "motion",
               op=r.get("op") if r.get("op") in OPS else "mean")
    if out["center"] == "point":
        out["point"] = [round(float(v), 4) for v in (r.get("point") or (0.0, 0.0))]
    else:
        out["offset"] = [round(float(v), 4) for v in (r.get("offset") or (0.0, 0.0))]
    for k, d in (("az0", 0.0), ("az1", 360.0), ("rmax", 20.0), ("z0", 0.0), ("z1", 15.0)):
        v = r.get(k)
        out[k] = round(float(d if v is None or v == "" else v), 4)
    dr = r.get("dr")
    out["dr"] = None if dr in (None, "") or not float(dr) > 0 else round(float(dr), 4)
    return out


def full_ring(recipe):
    """Whether the sector is the whole ring."""
    return sector_span(recipe["az0"], recipe["az1"]) >= 360.0


def sector_span(az0, az1):
    """Degrees from az0 clockwise to az1 (360 when they coincide, e.g. 0 to 360)."""
    return (float(az1) - float(az0)) % 360.0 or 360.0


def describe(recipe, label=""):
    """Legend text of a recipe, e.g. 'w mean, storm' or 'w max 0–90° from motion,
    (10, -5) km'."""
    r = recipe
    sec = "" if full_ring(r) else \
        f" {r['az0']:g}–{r['az1']:g}° from {'motion' if r['ref'] == 'motion' else 'north'}"
    where = "storm" if r["center"] == "track" else \
        "({:g}, {:g}) km".format(*r["point"])
    return f"{label or r['field']} {r['op']}{sec}, {where}"


def bearing(u, v):
    """Direction (degrees clockwise from grid north) of the vector (u, v); 0 when it is
    (nearly) zero."""
    return float(np.degrees(np.arctan2(u, v)) % 360.0) if np.hypot(u, v) > 0.1 else 0.0


def bins(run, recipe):
    """(bin width km, number of radius bins) of a recipe."""
    dr = recipe.get("dr") or run.dx / 1000.0
    return dr, max(1, int(np.ceil(recipe["rmax"] / dr - 1e-6)))


def at_time(run, F, recipe, t, center, ref, storm=None):
    """(sums or extremes, counts) of a recipe at output t, each (levels, radius bins).
    center: (x, y) grid km; ref: bearing (deg) of azimuth 0; storm: storm motion of
    storm-relative fields.  Raises ValueError for a 2D field, one off the scalar grid
    or a centre off the domain."""
    r = recipe
    d = F[r["field"]]
    if d.ndim == 2:
        raise ValueError("an azimuthal mean needs a 3D field")
    ks = ser.mean_levels(run, r)
    dr, nr = bins(run, r)
    dxk, dyk = run.dx / 1000.0, run.dy / 1000.0
    cx, cy = center
    a, b = (cx - run.xh[0]) / dxk, (cy - run.yh[0]) / dyk
    ri, rj = int(np.ceil(r["rmax"] / dxk)) + 1, int(np.ceil(r["rmax"] / dyk)) + 1
    i0, i1 = max(0, int(np.floor(a)) - ri), min(run.ni, int(np.ceil(a)) + ri + 1)
    j0, j1 = max(0, int(np.floor(b)) - rj), min(run.nj, int(np.ceil(b)) + rj + 1)
    if i0 >= i1 or j0 >= j1:
        raise ValueError("the centre is off the domain")
    # the field's volume where it fits the 3D cache; else only the box of the rings
    vol = None
    if F.fits([d.name], t):
        vol, scale = F.raw(d.name, t, storm)
        if vol.shape[1:] != (run.nj, run.ni) or vol.shape[0] != len(run.z):
            raise ValueError(f"{d.name} is not on the scalar grid (pick an interpolated "
                             "field, e.g. winterp, not w)")

    def box(k0, k1):  # (levels k0:k1 of the box, and their factor to display units)
        if vol is not None:
            return vol[k0:k1, j0:j1, i0:i1], scale
        return F.box(d.name, t, k0, k1, j0, j1, i0, i1, storm), 1.0

    X, Y = np.meshgrid(run.xh[i0:i1] - cx, run.yh[j0:j1] - cy)
    R = np.hypot(X, Y)
    az = (np.degrees(np.arctan2(X, Y)) - ref) % 360.0
    m = R < r["rmax"]
    if not full_ring(r):
        m &= (az - r["az0"]) % 360.0 <= sector_span(r["az0"], r["az1"])
    nz = len(ks)
    if not m.any():
        return np.full((nz, nr), np.nan), np.zeros((nz, nr), dtype=np.int64)
    rb = np.minimum((R[m] / dr).astype(np.int64), nr - 1)
    if run.terrain:  # (each column interpolated to the levels' mean heights, z below)
        from .fields import at_height
        Z, (cols, scale) = run.heights(t)[:, j0:j1, i0:i1], box(0, len(run.z))
        sub = np.stack([at_height(cols, Z, float(h)) for h in run.z[ks[0]:ks[-1] + 1]])
    else:
        sub, scale = box(ks[0], ks[-1] + 1)
    v = np.asarray(sub[:, m], dtype=np.float64) * float(scale)
    idx = (np.arange(nz)[:, None] * nr + rb[None, :])
    ok = np.isfinite(v)
    idx, v = idx[ok], v[ok]
    n = np.bincount(idx, minlength=nz * nr).reshape(nz, nr)
    if r["op"] == "mean":
        s = np.bincount(idx, weights=v, minlength=nz * nr)
    else:
        s = np.full(nz * nr, -np.inf if r["op"] == "max" else np.inf)
        (np.maximum if r["op"] == "max" else np.minimum).at(s, idx, v)
    return s.reshape(nz, nr), n


def compute(run, F, recipe, ts, centers, refs, storm=None, cancelled=None):
    """The recipe at the outputs ts together (dict: r (bin centres, km), z (levels,
    km), v (levels x bins; nan where a bin has no value), n (counts), nt (outputs)).
    centers: {t: (x, y)}; refs: {t: bearing of azimuth 0}; storm: {t: storm motion}
    of storm-relative fields.  Raises ValueError as at_time(); None when cancelled()
    turns true before a time."""
    r = recipe
    dr, nr = bins(run, r)
    ks = ser.mean_levels(run, r)
    S = N = None
    if cancelled and cancelled():
        return None
    # several outputs at once where their volumes are small (the next one is read while
    # one is binned), combined in the order of ts
    cost = getattr(F, "read_bytes", None)
    each = ahead(lambda t: at_time(run, F, r, t, centers[t], refs[t], (storm or {}).get(t)),
                 ts, ahead_width(run, cost(r["field"]) if cost else 0) if len(ts) > 1 else 0)
    try:
        for _, (s, n) in each:
            if S is None:
                S, N = s, n
            elif r["op"] == "mean":
                S, N = S + s, N + n
            else:
                S, N = (np.fmax if r["op"] == "max" else np.fmin)(S, s), N + n
            if cancelled and cancelled():
                return None
    finally:
        each.close()
    with np.errstate(invalid="ignore", divide="ignore"):
        v = S / N if r["op"] == "mean" else np.where(N > 0, S, np.nan)
    v = np.where(N > 0, v, np.nan)
    return dict(r=(np.arange(nr) + 0.5) * dr, z=np.asarray(run.z, dtype=np.float64)[ks],
                v=v.astype(np.float32), n=N, nt=len(ts))
