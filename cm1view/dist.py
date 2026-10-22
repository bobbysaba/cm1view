"""Distributions: every value of a field over a region at one time (a sample), and its
summary, from which histograms (counts, PDF or fractions), box plots, violins and
cumulative distributions are drawn (figdraw.dist_*) without the sample itself.

A recipe says which values:
  field   any 3D or 2D field of the catalog (native or derived)
  vmode   'height' (one height, km AGL), 'layer' (every model level in z0..z1), 'all'
          (every model level) or '2d'
  region  'domain', 'box' (x0, x1, y0, y1 km) or 'track' (disc of `radius` km around
          the tracked storm, shifted by `offset` km), as series.region_at
  lo, hi  keep only values in lo..hi (None: no limit), e.g. updrafts: lo = 1 m/s

The summary keeps the whole sample's shape in a few kB, whatever its size: a fine
histogram (NFINE bins from its minimum to its maximum; coarser bins, the cumulative
distribution and the violin's density come from it), the quantiles figdraw.DIST_PROBS
(box plots), the mean and standard deviation, and the box-plot whiskers at 1.5 times
the interquartile range (Tukey)."""

import numpy as np

from . import figdraw, series as ser

NFINE = 4000
VMODES = ("height", "layer", "all", "2d")
_CHUNK = 1 << 22  # (values per pass: means and whiskers without full float64 copies)


def normalize(recipe):
    """A recipe with only the keys that matter for it (a stable cache key)."""
    r = dict(recipe)
    vmode = r.get("vmode", "height")
    out = dict(field=r["field"], vmode=vmode if vmode in VMODES else "height",
               region=r.get("region", "domain"))
    if out["vmode"] == "height":
        out["z"] = round(float(r.get("z") or 0.0), 4)
    elif out["vmode"] == "layer":
        out["z0"], out["z1"] = (round(float(r.get(k) or 0.0), 4) for k in ("z0", "z1"))
    if out["region"] == "box":
        out["box"] = [round(float(v), 4) for v in r["box"]]
    elif out["region"] == "track":
        out["radius"] = round(float(r.get("radius") or 5.0), 4)
        out["offset"] = [round(float(v), 4) for v in (r.get("offset") or (0.0, 0.0))]
    for k in ("lo", "hi"):
        v = r.get(k)
        out[k] = None if v is None or v == "" or not np.isfinite(float(v)) else float(v)
    return out


def describe(recipe, label="", units=""):
    """Legend text of a recipe, e.g. 'w 1 km, domain' or 'w 0–10 km ≥ 1 m/s, storm'."""
    r = recipe
    name = label or r["field"]
    where = {"height": f" {r.get('z', 0):g} km", "layer":
             f" {r.get('z0', 0):g}–{r.get('z1', 0):g} km", "all": " all levels"}.get(
        r["vmode"], "")
    lo, hi = r.get("lo"), r.get("hi")
    u = f" {units}" if units else ""
    keep = (f" {lo:g}–{hi:g}{u}" if lo is not None and hi is not None else
            f" ≥ {lo:g}{u}" if lo is not None else f" ≤ {hi:g}{u}" if hi is not None else "")
    reg = {"domain": "domain", "box": "box", "track": "storm"}.get(r["region"], r["region"])
    return f"{name}{where}{keep}, {reg}"


def sample(run, F, recipe, t, storm=None, center=None):
    """The finite values (float32, 1D) of a recipe at output t.  storm: storm motion of
    storm-relative fields; center: (x, y) km of the tracked storm (track regions).
    Raises ValueError when the region is empty or off the domain."""
    r = recipe
    reg = ser.region_at(run, dict(r, offset=r.get("offset") or (0.0, 0.0),
                                  radius=r.get("radius") or 5.0), center)
    if reg is None:
        raise ValueError("no track position at this time" if r["region"] == "track"
                         and center is None else "the region is empty")
    i0, i1, j0, j1, mask, _ = reg
    d = F[r["field"]]
    if d.ndim == 2 or r["vmode"] in ("height", "2d"):
        a = F.plane(d.name, t, "height", float(r.get("z") or 0.0), storm=storm)[j0:j1, i0:i1]
        a = a[mask] if mask is not None else a.ravel()
    else:
        ks = ser.levels(run, r) if r["vmode"] == "layer" else [0, len(run.z) - 1]
        a = F.volume(d.name, t, storm=storm)[ks[0]:ks[-1] + 1, j0:j1, i0:i1]
        a = a[:, mask].ravel() if mask is not None else a.ravel()
    keep = np.isfinite(a)
    if r.get("lo") is not None:
        keep &= a >= r["lo"]
    if r.get("hi") is not None:
        keep &= a <= r["hi"]
    return np.asarray(a[keep], dtype=np.float32)


def summarize(a):
    """Summary of a sample (dict: n, mean, std, lo, hi (min, max), wlo, whi (Tukey
    whiskers), q (quantiles at figdraw.DIST_PROBS), h (NFINE counts from lo to hi));
    {n: 0} for none.  The sample's order may change."""
    a = np.asarray(a).ravel()
    n = int(a.size)
    if n == 0:
        return dict(n=0)
    lo, hi = float(a.min()), float(a.max())
    h, _ = np.histogram(a, bins=NFINE, range=figdraw.dist_span(lo, hi))
    s = sum(float(a[k:k + _CHUNK].sum(dtype=np.float64)) for k in range(0, n, _CHUNK))
    mean = s / n
    var = 0.0
    for k in range(0, n, _CHUNK):
        b = a[k:k + _CHUNK].astype(np.float64) - mean
        var += float(b @ b)
    q = np.quantile(a, figdraw.DIST_PROBS, overwrite_input=True).astype(np.float64)
    p25, p75 = q[figdraw.DIST_PROBS.index(0.25)], q[figdraw.DIST_PROBS.index(0.75)]
    flo, fhi = p25 - 1.5 * (p75 - p25), p75 + 1.5 * (p75 - p25)
    wlo, whi = hi, lo
    for k in range(0, n, _CHUNK):
        b = a[k:k + _CHUNK]
        inside = b[(b >= flo) & (b <= fhi)]
        if inside.size:
            wlo, whi = min(wlo, float(inside.min())), max(whi, float(inside.max()))
    return dict(n=n, mean=mean, std=float(np.sqrt(var / n)), lo=lo, hi=hi, wlo=wlo, whi=whi,
                q=q, h=h.astype(np.int64))


def compute(run, F, recipe, t, storm=None, center=None):
    """summarize(sample(...)): the summary of a recipe at output t."""
    return summarize(sample(run, F, recipe, t, storm, center))
