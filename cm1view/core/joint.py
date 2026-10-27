"""Joint distributions: the pairs of values of two fields at the same points over a
region (a paired sample), and its summary, from which scatter plots, 2D histograms
(counts, PDF or fractions) and density contours are drawn (figdraw.joint_*) without
the sample itself.

A recipe is a dist recipe (dist.normalize: its field is x, with the height, layer or
whole depth, the region and x's value limits lo, hi) and
  yfield    the y field (3D or 2D; a 2D field pairs at one height only)
  ylo, yhi  keep only pairs whose y is in ylo..yhi (None: no limit)

The summary keeps the sample's shape in a few hundred kB, whatever its size: a fine 2D
histogram (NJ x NJ bins from the minima to the maxima; coarser bins and the density
contours come from it), NPTS pairs picked at random (the scatter plot), the means,
standard deviations and Pearson correlation of every pair."""

import numpy as np

from ..figures import draw as figdraw
from . import dist

NJ = 200
NPTS = 5000
_CHUNK = 1 << 22


def normalize(recipe):
    """A recipe with only the keys that matter for it (a stable cache key)."""
    r = dict(recipe)
    out = dist.normalize(r)
    out["yfield"] = r.get("yfield") or out["field"]
    for k in ("ylo", "yhi"):
        v = r.get(k)
        out[k] = None if v is None or v == "" or not np.isfinite(float(v)) else float(v)
    return out


def describe(recipe, xlabel="", ylabel=""):
    """Legend text of a recipe, e.g. 'ζ vs w 1 km, domain'."""
    r = recipe
    return dist.describe(dict(r, lo=None, hi=None),
                         f"{ylabel or r['yfield']} vs {xlabel or r['field']}")


def sample(run, F, recipe, t, storm=None, center=None):
    """The finite pairs (x, y: float32, 1D) of a recipe at output t, both fields at
    the same points (a 2D field with a 3D one: at the recipe's height).  storm: storm
    motion of storm-relative fields; center: (x, y) km of the tracked storm.  Raises
    ValueError when the region is empty or the fields are on different grids."""
    r = recipe
    if (F[r["field"]].ndim == 2 or F[r["yfield"]].ndim == 2) and r["vmode"] in ("layer", "all"):
        r = dict(r, vmode="height", z=r.get("z") or 0.0)
    reg = dist.region(run, r, center)
    x = dist.values(run, F, r, r["field"], t, storm if F[r["field"]].storm else None, reg)
    y = dist.values(run, F, r, r["yfield"], t, storm if F[r["yfield"]].storm else None, reg)
    if x.shape != y.shape:
        raise ValueError("the two fields are on different grids (pick the interpolated "
                         "ones, e.g. winterp, not w)")
    keep = np.isfinite(x) & np.isfinite(y)
    for a, lo, hi in ((x, r.get("lo"), r.get("hi")), (y, r.get("ylo"), r.get("yhi"))):
        if lo is not None:
            keep &= a >= lo
        if hi is not None:
            keep &= a <= hi
    return np.asarray(x[keep], dtype=np.float32), np.asarray(y[keep], dtype=np.float32)


def summarize(x, y, seed=0):
    """Summary of a paired sample (dict: n, mx, my (means), sx, sy (standard
    deviations), r (Pearson; nan when either is constant), xlo, xhi, ylo, yhi (minima,
    maxima), h (NJ x NJ counts, x along the first axis), px, py (up to NPTS pairs
    picked at random)); {n: 0} for none."""
    x, y = np.asarray(x).ravel(), np.asarray(y).ravel()
    n = int(x.size)
    if n == 0:
        return dict(n=0)
    xlo, xhi, ylo, yhi = float(x.min()), float(x.max()), float(y.min()), float(y.max())
    rng = [figdraw.dist_span(xlo, xhi), figdraw.dist_span(ylo, yhi)]
    h = np.zeros((NJ, NJ), dtype=np.int64)
    sx = sy = 0.0
    for k in range(0, n, _CHUNK):
        a, b = x[k:k + _CHUNK], y[k:k + _CHUNK]
        h += np.histogram2d(a, b, bins=NJ, range=rng)[0].astype(np.int64)
        sx += float(a.sum(dtype=np.float64))
        sy += float(b.sum(dtype=np.float64))
    mx, my = sx / n, sy / n
    vx = vy = cxy = 0.0
    for k in range(0, n, _CHUNK):
        a = x[k:k + _CHUNK].astype(np.float64) - mx
        b = y[k:k + _CHUNK].astype(np.float64) - my
        vx, vy, cxy = vx + float(a @ a), vy + float(b @ b), cxy + float(a @ b)
    r = cxy / np.sqrt(vx * vy) if vx > 0 and vy > 0 else np.nan
    pick = np.arange(n) if n <= NPTS else \
        np.sort(np.random.default_rng(seed).choice(n, NPTS, replace=False))
    return dict(n=n, mx=mx, my=my, sx=float(np.sqrt(vx / n)), sy=float(np.sqrt(vy / n)),
                r=float(r), xlo=xlo, xhi=xhi, ylo=ylo, yhi=yhi, h=h,
                px=np.asarray(x[pick], dtype=np.float32),
                py=np.asarray(y[pick], dtype=np.float32))


def compute(run, F, recipe, ts, storm=None, centers=None):
    """summarize() of the pairs of a recipe at the outputs ts, together.  storm: {t:
    storm motion}; centers: {t: (x, y)} (track regions).  Raises ValueError as
    sample() (at any of the times)."""
    xs, ys = [], []
    for t in ts:
        a, b = sample(run, F, recipe, t, (storm or {}).get(t), (centers or {}).get(t))
        xs.append(a)
        ys.append(b)
    if len(xs) == 1:
        return summarize(xs[0], ys[0])
    return summarize(np.concatenate(xs), np.concatenate(ys))
