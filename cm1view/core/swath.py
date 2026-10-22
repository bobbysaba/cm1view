"""Time windows of a plan layer: swaths (the maximum, minimum, mean or sum of a field
over a window of outputs, e.g. an updraft-helicity or hail swath) and storm-following
composites (the mean in the box that moves with the tracked storm).

A layer's "reduce" says which:
  op      'max', 'min', 'mean', 'sum' or 'composite'
  t0, t1  model times (s) of the window (None: the run's first output / the panel's
          time); the outputs between them, both included
  every   every nth output of the window (1: all)

The result is placed as at the panel's output: a swath follows the ground (the model
grid moves with umove, vmove), a composite follows the storm.  Either is a whole-domain
array (blank where the window's outputs do not reach), kept in the cache folder
(Settings: cache_dir) so redrawing, restyling or moving the area reads nothing again."""

import hashlib
import json
import os

import numpy as np

from .run import FileBusy, MissingAtTime

OPS = ("max", "min", "mean", "sum", "composite")
CACHE_DIR = None  # None: <cache_dir setting>/swath (tests point this elsewhere)


def cache_dir():
    if CACHE_DIR:
        return CACHE_DIR
    from .. import config
    return config.cache_dir("swath")


def window(run, red, ts):
    """Output indices of the window of `red` for a panel at model time ts (s)."""
    times = np.asarray(run.times, dtype=float)
    t0 = times[0] if red.get("t0") is None else float(red["t0"])
    t1 = float(ts) if red.get("t1") is None else float(red["t1"])
    t0, t1 = min(t0, t1), max(t0, t1)
    idx = np.flatnonzero((times >= t0 - 0.5) & (times <= t1 + 0.5))
    return [int(t) for t in idx[::max(1, int(red.get("every") or 1))]]


def shifts(run, red, ts, tp, centers=None):
    """{t: (di, dj)} grid cells from where a point of output tp is to where it is at
    output t, for each t of ts: with the ground (swaths) or with the storm (composite,
    centers {t: (x, y)} km; outputs without a centre are left out)."""
    out = {}
    if red["op"] == "composite":
        c0 = (centers or {}).get(tp)
        if c0 is None:
            return out
        for t in ts:
            c = centers.get(t)
            if c is not None:
                out[t] = (int(round((c[0] - c0[0]) * 1000.0 / run.dx)),
                          int(round((c[1] - c0[1]) * 1000.0 / run.dy)))
        return out
    for t in ts:
        dt = float(run.times[tp]) - float(run.times[t])
        out[t] = (int(round(run.umove * dt / run.dx)), int(round(run.vmove * dt / run.dy)))
    return out


def shifted(a, di, dj):
    """b with b[j, i] = a[j + dj, i + di] (blank off the grid)."""
    nj, ni = a.shape
    b = np.full(a.shape, np.nan, dtype=np.float32)
    if abs(di) >= ni or abs(dj) >= nj:
        return b
    src = (slice(max(dj, 0), nj + min(dj, 0)), slice(max(di, 0), ni + min(di, 0)))
    dst = (slice(max(-dj, 0), nj + min(-dj, 0)), slice(max(-di, 0), ni + min(-di, 0)))
    b[dst] = a[src]
    return b


def _mtimes(run, ts):
    try:
        if not run.files:
            return []
        if len(run.files) == len(run.times):
            return [round(os.path.getmtime(run.files[t]), 3) for t in ts]
        return [round(max(os.path.getmtime(f) for f in run.files), 3)]
    except OSError:
        return []


def _key(run, lay, sh, storm):
    red = lay["reduce"]
    k = [run.path, lay["field"], lay.get("mode", "height"), round(float(lay.get("z", 0)), 4),
         red["op"], sorted([t, d[0], d[1]] for t, d in sh.items()),
         sorted([t, round(m[0], 3), round(m[1], 3)] for t, m in (storm or {}).items()
                if t in sh), _mtimes(run, sorted(sh))]
    return hashlib.sha1(json.dumps(k).encode()).hexdigest()[:24]


def reduce(run, F, lay, tp, centers=None, storm=None, progress=None):
    """(whole-domain float32 array, outputs used) of plan layer `lay` reduced over its
    window ("reduce", above) for a panel at output tp.  centers: tracked storm centres
    {t: (x, y)} km (composites); storm: {t: (u, v)} storm motion of storm-relative
    fields; progress(done, total).  Raises ValueError when no output can be used."""
    red = lay["reduce"]
    if red.get("op") not in OPS:
        raise ValueError(f"unknown time window {red.get('op')!r}")
    ts = window(run, red, float(run.times[tp]))
    sh = shifts(run, red, ts, tp, centers)
    if not sh:
        raise ValueError("a storm-following composite needs the storm track at the panel "
                         "time and in the window" if red["op"] == "composite" else
                         "no output in the time window")
    if F[lay["field"]].storm:
        storm = {t: (storm or {}).get(t) or (run.umove, run.vmove) for t in sh}
    else:
        storm = None
    path = os.path.join(cache_dir(), _key(run, lay, sh, storm) + ".npz")
    try:
        with np.load(path) as c:
            return c["a"], int(c["n"])
    except (OSError, ValueError, KeyError):
        pass
    acc = cnt = None
    n = 0
    for k, (t, (di, dj)) in enumerate(sorted(sh.items())):
        if progress:
            progress(k, len(sh))
        try:
            a = F.plane(lay["field"], t, lay.get("mode", "height"), float(lay.get("z", 0)),
                        storm=storm.get(t) if storm else None)
        except (MissingAtTime, FileBusy):
            continue
        b = shifted(np.asarray(a, dtype=np.float32), di, dj)
        if acc is None:
            acc = np.full(b.shape, np.nan if red["op"] in ("max", "min") else 0.0,
                          dtype=np.float64)
            cnt = np.zeros(b.shape, dtype=np.int32)
        ok = np.isfinite(b)
        if red["op"] == "max":
            acc = np.fmax(acc, b)
        elif red["op"] == "min":
            acc = np.fmin(acc, b)
        else:
            acc[ok] += b[ok]
        cnt += ok
        n += 1
    if acc is None:
        raise ValueError("no output in the time window could be read")
    if red["op"] in ("mean", "composite"):
        with np.errstate(invalid="ignore", divide="ignore"):
            acc = acc / cnt
    acc[cnt == 0] = np.nan
    out = acc.astype(np.float32)
    try:
        os.makedirs(cache_dir(), exist_ok=True)
        tmp = path + f".{os.getpid()}.tmp.npz"
        np.savez(tmp, a=out, n=n)
        os.replace(tmp, path)
    except OSError:
        pass
    return out, n

