"""Time series of one field reduced over a region, at every output time of a run.

A recipe says what to compute at each time:
  field   any 3D or 2D field of the catalog (native or derived, e.g. thpert, thrhopert,
          or a column field such as uh25), or a derivative of one (fields.deriv_name,
          e.g. ddz.winterp)
  vmode   'height' (one height, km AGL), 'layer' (every model level in z0..z1) or '2d'
  region  'domain', 'box' (x0, x1, y0, y1 km) or 'track' (disc of `radius` km around
          the tracked storm, shifted by `offset` km)
  reduce  'min', 'max', 'mean' or 'pct' (percentile `pct`)
For a layer the reduction is also kept at every level (time x height), so any
sub-layer or a time-height plot comes from the saved result without recomputing.

Each time is computed in a reader process that reads its file one horizontal level at
a time (one chunk per level), so memory stays small and the browsing cache is not
touched.  Results are cached on disk per (run, recipe) and reused per time as long as
the file is unchanged (mtime) and, for track regions, the region centre is the same.

Results are xarray Datasets; save() writes them as netCDF (default, keeps the
per-level data), CSV / aligned text (the series only) or pickle.
"""

import hashlib
import io
import json
import os
import time as _time

import numpy as np

REDUCE_LABEL = {"min": "min", "max": "max", "mean": "mean", "pct": "percentile"}
FORMATS = {".nc": "netCDF", ".csv": "CSV", ".txt": "text", ".pkl": "pickle"}
CACHE_DIR = None  # None: <cache_dir setting>/series (tests point this elsewhere)


def cache_dir():
    if CACHE_DIR:
        return CACHE_DIR
    from .. import config
    return config.cache_dir("series")


# ------------------------------------------------------------------ recipe
def normalize(recipe):
    """Recipe with only the keys that matter for its kind (the cache key)."""
    r = dict(field=recipe["field"], vmode=recipe["vmode"], region=recipe["region"],
             reduce=recipe["reduce"])
    if r["vmode"] == "height":
        r["z"] = round(float(recipe["z"]), 4)
    elif r["vmode"] == "layer":
        r["z0"], r["z1"] = sorted((round(float(recipe["z0"]), 4),
                                   round(float(recipe["z1"]), 4)))
    if r["region"] == "box":
        x0, x1, y0, y1 = (float(v) for v in recipe["box"])
        r["box"] = [round(min(x0, x1), 3), round(max(x0, x1), 3),
                    round(min(y0, y1), 3), round(max(y0, y1), 3)]
    elif r["region"] == "track":
        r["radius"] = round(float(recipe["radius"]), 3)
        r["offset"] = [round(float(v), 3) for v in recipe.get("offset", (0.0, 0.0))]
    if r["reduce"] == "pct":
        r["pct"] = round(float(recipe["pct"]), 3)
    return r


def describe(recipe, label="", units=""):
    """One-line description, e.g. 'min θ′ at 1 km AGL, whole domain (K)'."""
    r = recipe
    red = f"{r['pct']:g}th percentile" if r["reduce"] == "pct" else REDUCE_LABEL[r["reduce"]]
    what = label or r["field"]
    if len(what) > 1 and what[0].isupper() and what[1].islower():  # 'Vertical velocity'
        what = what[0].lower() + what[1:]
    if r["vmode"] == "height":
        where = f" at {r['z']:g} km AGL"
    elif r["vmode"] == "layer":
        where = f" in {r['z0']:g}–{r['z1']:g} km AGL"
    else:
        where = ""
    if r["region"] == "domain":
        reg = "whole domain"
    elif r["region"] == "box":
        reg = "box x {:g}–{:g}, y {:g}–{:g} km".format(*r["box"])
    else:
        dx, dy = r["offset"]
        reg = f"within {r['radius']:g} km of the tracked storm"
        if dx or dy:
            reg += f" offset ({dx:g}, {dy:g}) km"
    return f"{red} {what}{where}, {reg}" + (f" ({units})" if units else "")


def short_name(recipe):
    """File-name friendly name, e.g. 'min_thpert_1km_domain'."""
    r = recipe
    red = f"p{r['pct']:g}" if r["reduce"] == "pct" else r["reduce"]
    if r["vmode"] == "height":
        lv = f"{r['z']:g}km"
    elif r["vmode"] == "layer":
        lv = f"{r['z0']:g}-{r['z1']:g}km"
    else:
        lv = "2d"
    reg = {"domain": "domain", "box": "box", "track": f"trk{r.get('radius', 0):g}km"}
    return f"{red}_{r['field']}_{lv}_{reg[r['region']]}".replace(".", "p")


def levels(run, recipe):
    """Model level indices of a layer recipe (at least the nearest one)."""
    z0, z1 = recipe["z0"], recipe["z1"]
    ks = np.flatnonzero((run.z >= z0) & (run.z <= z1))
    if ks.size == 0:
        ks = np.array([int(np.argmin(np.abs(run.z - 0.5 * (z0 + z1))))])
    return [int(k) for k in ks]


def region_at(run, recipe, center):
    """(i0, i1, j0, j1, mask or None, center or None) of the region at one time;
    None if a track region has no centre (or lies off the domain)."""
    dxk, dyk = run.dx / 1000.0, run.dy / 1000.0
    reg = recipe["region"]
    if reg == "domain":
        return 0, run.ni, 0, run.nj, None, None

    def idx(x, y):
        return ((x - run.xh[0]) / dxk, (y - run.yh[0]) / dyk)

    if reg == "box":
        x0, x1, y0, y1 = recipe["box"]
        a0, b0 = idx(x0, y0)
        a1, b1 = idx(x1, y1)
        i0, i1 = max(0, int(np.ceil(a0))), min(run.ni, int(np.floor(a1)) + 1)
        j0, j1 = max(0, int(np.ceil(b0))), min(run.nj, int(np.floor(b1)) + 1)
        return (i0, i1, j0, j1, None, None) if i0 < i1 and j0 < j1 else None
    if center is None:
        return None
    cx, cy = center[0] + recipe["offset"][0], center[1] + recipe["offset"][1]
    R = recipe["radius"]
    a, b = idx(cx, cy)
    ri, rj = int(np.ceil(R / dxk)), int(np.ceil(R / dyk))
    i0, i1 = max(0, int(np.floor(a)) - ri), min(run.ni, int(np.ceil(a)) + ri + 1)
    j0, j1 = max(0, int(np.floor(b)) - rj), min(run.nj, int(np.ceil(b)) + rj + 1)
    if i0 >= i1 or j0 >= j1:
        return None
    X, Y = np.meshgrid(run.xh[i0:i1], run.yh[j0:j1])
    mask = (X - cx) ** 2 + (Y - cy) ** 2 <= R * R
    if not mask.any():
        return None
    return i0, i1, j0, j1, mask, (cx, cy)


def track_centers(fixes, nt):
    """Storm centre {t: (x, y)} from the track fixes, linearly interpolated over times
    missing between fixes (none before the first or after the last fix)."""
    ts = sorted(fixes)
    if not ts:
        return {}
    out = {}
    for t in range(ts[0], ts[-1] + 1):
        if t in fixes:
            out[t] = (fixes[t]["x"], fixes[t]["y"])
            continue
        a = max(s for s in ts if s < t)
        b = min(s for s in ts if s > t)
        w = (t - a) / (b - a)
        out[t] = (fixes[a]["x"] + w * (fixes[b]["x"] - fixes[a]["x"]),
                  fixes[a]["y"] + w * (fixes[b]["y"] - fixes[a]["y"]))
    return out


# ------------------------------------------------------------------ worker
def _read(v, stag, k, j0, j1, i0, i1, ndim):
    """One horizontal level of an open (time, [z,] y, x) variable on scalar points."""
    if ndim == 2:
        return np.asarray(v[0, j0:j1, i0:i1], dtype=np.float32)
    if stag == "x":
        a = np.asarray(v[0, k, j0:j1, i0:i1 + 1], dtype=np.float32)
        return 0.5 * (a[:, :-1] + a[:, 1:])
    if stag == "y":
        a = np.asarray(v[0, k, j0:j1 + 1, i0:i1], dtype=np.float32)
        return 0.5 * (a[:-1] + a[1:])
    if stag == "z":
        a = np.asarray(v[0, k:k + 2, j0:j1, i0:i1], dtype=np.float32)
        return 0.5 * (a[0] + a[1])
    return np.asarray(v[0, k, j0:j1, i0:i1], dtype=np.float32)


_DEFS = {}


def _field_def(name, avail):
    key = (name, frozenset(avail))
    if key not in _DEFS:
        from .fields import _make_fields
        _DEFS[key] = next((d for d in _make_fields(set(avail)) if d.name == name), None)
    return _DEFS[key]


def _reduce(a, how, pct):
    """(value, flat index of the extreme or -1) of the finite values of a."""
    ok = np.isfinite(a)
    if not ok.any():
        return np.nan, -1
    if how in ("min", "max"):
        b = np.where(ok, a, np.inf if how == "min" else -np.inf)
        i = int(np.argmin(b) if how == "min" else np.argmax(b))
        return float(a.flat[i]), i
    if how == "mean":
        return float(np.mean(a[ok], dtype=np.float64)), -1
    return float(np.percentile(a[ok], pct)), -1


def _ddz(f, z, k, nk):
    """∂/∂z (per km) on model level k of f(level) -> plane: centred on the stretched
    levels inside, one-sided at the bottom and top (as Fields._ddz_level)."""
    k = min(max(int(k), 0), nk - 1)
    lo, hi = max(k - 1, 0), min(k + 1, nk - 1)
    if lo == hi:
        return np.zeros_like(f(k))
    if lo == k or hi == k:
        return (f(hi) - f(lo)) / (z[hi] - z[lo])
    hl, hr = z[k] - z[lo], z[hi] - z[k]
    return (hl * hl * f(hi) - hr * hr * f(lo) + (hr * hr - hl * hl) * f(k)) / \
        (hl * hr * (hl + hr))


def _worker(task):
    """Reader process: the recipe at one time.  Returns dict(t, value, x, y, z, prof,
    npts) or dict(t, error).  A derivative (task "op", of field task "field") and
    derived fields that are not pointwise are computed on the region plus a one-point
    border (task "halo"), so their values at its edge are those of the map."""
    import netCDF4

    from .fields import hgrad, split_deriv, stride_cols

    t = task["t"]
    try:
        with netCDF4.Dataset(task["path"]) as d:
            d.set_auto_mask(False)
            name, info = task["field"], task["natives"]
            op = task.get("op", "")
            fdef = None if name in info else _field_def(name, task["avail"])
            if fdef is None and name not in info:
                return dict(t=t, error=f"unknown field {name}")
            deps = [name] if fdef is None else list(fdef.natives)
            missing = [n for n in deps if n not in d.variables]
            if missing:
                return dict(t=t, error="not in this file: " + ", ".join(missing))
            i0, i1, j0, j1 = task["box"]
            # the box read: the region and its border (cut off at the domain's edge)
            e0, e1, f0, f1 = task.get("halo") or (i0, i1, j0, j1)
            crop = (slice(j0 - f0, j1 - f0), slice(i0 - e0, i1 - e0))
            mask = task["mask"]
            ctx = task["ctx"]

            def base(fetch):
                """The field (not yet differentiated) on the box read."""
                if fdef is not None and fdef.column:  # (its layer's levels only)
                    ks, dz, zk, top = task["column"]
                    c = dict(ctx, dz=dz, zk=zk, top=top, memo={})
                    s = task.get("stride", 1)
                    if s == 1:
                        return np.asarray(fdef.func(lambda n: np.stack(
                            [_read(d[n], info[n][0], k, f0, f1, e0, e1, info[n][2])
                             for k in ks]), c), dtype=np.float32)
                    # (costly: the middle columns of the stride's blocks, as the map)
                    r0, r1, tj, bj = stride_cols(f0, f1, task["nj"], s)
                    c0, c1, ti, bi = stride_cols(e0, e1, task["ni"], s)
                    a = fdef.func(lambda n: np.stack(
                        [_read(d[n], info[n][0], k, r0, r1, c0, c1, info[n][2])[
                            np.ix_(tj, ti)] for k in ks]), c)
                    return np.asarray(a, dtype=np.float32)[np.ix_(bj, bi)]
                return (np.asarray(fdef.func(fetch, ctx), dtype=np.float32)
                        if fdef is not None else fetch(name) * np.float32(info[name][1]))

            def finish(a):
                """Horizontal derivative (on the box read), cut to the region, masked."""
                if op in ("ddx", "ddy", "gradh"):
                    a = hgrad(op, a, task["xe"], task["ye"])
                a = np.asarray(a, dtype=np.float32)[crop]
                if mask is not None:
                    a = np.where(mask, a, np.nan)
                return a

            zfull, nk = task.get("zfull"), task.get("nk", 0)
            raw = {}  # (native, level) -> plane on the box read; ∂/∂z inputs reuse them

            def read(n, k):
                if (n, k) not in raw:
                    if len(raw) > 24:
                        raw.pop(next(iter(raw)))
                    raw[n, k] = _read(d[n], info[n][0], k, f0, f1, e0, e1, info[n][2])
                return raw[n, k]

            def fetcher(k):
                memo = {}

                def fetch(n):
                    """Input n on level k: native (raw units), or a derivative of one
                    (per km, in its display units, as Fields gives it)."""
                    if n not in memo:
                        dop, dn = split_deriv(n)
                        sc = np.float32(task.get("dscale", {}).get(dn, 1.0))
                        if dop == "ddz":
                            memo[n] = sc * _ddz(lambda kk: read(dn, kk), zfull, k, nk)
                        elif dop:
                            memo[n] = sc * hgrad(dop, read(dn, k), task["xe"], task["ye"])
                        else:
                            memo[n] = read(n, k)
                    return memo[n]
                return fetch

            memo_k = {}  # (∂/∂z: each level's field is used by up to three levels)

            def level_base(k):
                if k not in memo_k:
                    if len(memo_k) > 4:
                        memo_k.pop(min(memo_k))
                    memo_k[k] = base(fetcher(k))
                return memo_k[k]

            def level(k):
                """The final field on model level k, cut to the region and masked."""
                if op == "ddz":
                    return finish(_ddz(level_base, zfull, k, nk))
                return finish(base(fetcher(k)))

            how, pct = task["reduce"], task.get("pct", 99.0)
            ny, nx = j1 - j0, i1 - i0
            out = dict(t=t, npts=int(mask.sum()) if mask is not None else nx * ny)
            if task["vmode"] in ("height", "2d"):
                if task["vmode"] == "2d":
                    a = finish(base(fetcher(0)))
                else:
                    k0, k1, w = task["weights"]
                    if op == "ddz":  # (∂/∂z of the two levels, then between them)
                        a = level(k0)
                        if w != 0.0 and k0 != k1:
                            a = (1.0 - w) * a + w * level(k1)
                    else:
                        g0, g1 = fetcher(k0), fetcher(k1)
                        a = finish(base(g0 if (w == 0.0 or k0 == k1) else
                                        (lambda n: (1.0 - w) * g0(n) + w * g1(n))))
                val, i = _reduce(a, how, pct)
                out.update(value=val, prof=None, z=task.get("zkm", np.nan))
                if i >= 0:
                    jj, ii = divmod(i, nx)
                    out.update(x=float(task["xh"][ii]), y=float(task["yh"][jj]))
                return out
            ks, zs = task["levels"], task["zlev"]
            prof = np.full(len(ks), np.nan)
            best = (np.nan, -1, -1)  # value, level position, flat index
            pool = []  # values for an overall mean / percentile
            for n, k in enumerate(ks):
                a = level(k)
                prof[n], i = _reduce(a, how, pct)
                if how in ("min", "max") and np.isfinite(prof[n]):
                    if (not np.isfinite(best[0]) or (prof[n] < best[0] if how == "min"
                                                     else prof[n] > best[0])):
                        best = (prof[n], n, i)
                elif how in ("mean", "pct"):
                    v = a[np.isfinite(a)]
                    cap = max(10_000, 2_000_000 // len(ks))  # percentile: subsample
                    if how == "pct" and v.size > cap:
                        v = v[:: v.size // cap + 1]
                    pool.append(v)
            out["prof"] = prof
            if how in ("min", "max"):
                out["value"] = best[0]
                if best[1] >= 0:
                    jj, ii = divmod(best[2], nx)
                    out.update(x=float(task["xh"][ii]), y=float(task["yh"][jj]),
                               z=float(zs[best[1]]))
            else:
                v = np.concatenate(pool) if pool else np.array([])
                out["value"] = (float("nan") if v.size == 0 else
                                float(np.mean(v, dtype=np.float64)) if how == "mean"
                                else float(np.percentile(v, pct)))
            return out
    except Exception as e:  # noqa: BLE001
        return dict(t=t, error=f"{type(e).__name__}: {e}")


# ------------------------------------------------------------------ dataset
def empty(run, recipe, label="", units=""):
    """Dataset with every output time and nothing computed yet."""
    import xarray as xr

    nt = len(run.times)
    data = dict(
        value=("time", np.full(nt, np.nan)),
        x_km=("time", np.full(nt, np.nan)), y_km=("time", np.full(nt, np.nan)),
        z_km=("time", np.full(nt, np.nan)),
        center_x_km=("time", np.full(nt, np.nan)), center_y_km=("time", np.full(nt, np.nan)),
        npoints=("time", np.zeros(nt, np.int64)),
        computed=("time", np.zeros(nt, np.int8)),
        file_mtime=("time", np.zeros(nt)),
    )
    coords = dict(time=("time", np.asarray(run.times, dtype=np.float64)),
                  time_index=("time", np.arange(nt)),
                  time_hms=("time", [run.time_label(t) for t in range(nt)]))
    if recipe["vmode"] == "layer":
        ks = levels(run, recipe)
        coords["z"] = ("z", run.z[ks])
        data["profile"] = (("time", "z"), np.full((nt, len(ks)), np.nan))
    ds = xr.Dataset(data, coords=coords)
    ds["time"].attrs.update(units="s", long_name="model time")
    if "z" in ds.coords:
        ds["z"].attrs.update(units="km", long_name="height AGL of the model level")
    red = describe(recipe, label, units)
    ds["value"].attrs.update(units=units, long_name=red)
    if "profile" in ds:
        ds["profile"].attrs.update(units=units, long_name=(
            f"{REDUCE_LABEL[recipe['reduce']]} over the region at each model level"))
    for c, txt in (("x_km", "x of the extreme (model grid)"),
                   ("y_km", "y of the extreme (model grid)"),
                   ("z_km", "height AGL of the extreme"),
                   ("center_x_km", "region centre x (track regions)"),
                   ("center_y_km", "region centre y (track regions)")):
        ds[c].attrs.update(units="km", long_name=txt)
    ds["npoints"].attrs["long_name"] = "grid columns in the region"
    ds["computed"].attrs["long_name"] = "1 where this time has been computed"
    ds.attrs.update(
        title="cm1view time series", description=red, recipe=json.dumps(recipe),
        run=run.path, field=recipe["field"], field_label=label, units=units,
        perturbations="perturbations (′) are relative to the CM1 base state (th0, qv0, "
                      "prs0 in the output)",
        grid=f"dx = {run.dx:g} m; x/y on the model grid, which moves with "
             f"(umove, vmove) = ({run.umove:g}, {run.vmove:g}) m/s",
        created=_time.strftime("%Y-%m-%d %H:%M:%S"))
    return ds


def _cache_path(run, recipe):
    from .fields import COSTLY, column_stride, split_deriv
    key = [run.path, recipe]
    if split_deriv(recipe["field"])[1] in COSTLY:  # (its values depend on the stride)
        key.append(column_stride(run))
    key = hashlib.sha1(json.dumps(key, sort_keys=True).encode())
    return os.path.join(cache_dir(), key.hexdigest()[:20] + ".nc")


def cached(run, recipe, label="", units="", centers=None):
    """The cached dataset of this recipe (all times, possibly partly computed), or an
    empty one.  Times whose file changed since, or (track regions, `centers` given)
    whose region centre moved, are marked as not computed."""
    ds = empty(run, recipe, label, units)
    path = _cache_path(run, recipe)
    if not os.path.exists(path):
        return ds
    import xarray as xr
    try:
        with xr.open_dataset(path) as c:
            c = c.load()
    except (OSError, ValueError):
        return ds
    if c.sizes.get("time") != ds.sizes["time"] or (
            "z" in ds.coords and ("z" not in c.coords or c.sizes["z"] != ds.sizes["z"])):
        return ds
    mt = np.array([os.path.getmtime(f) for f in run.files])
    ok = (c["computed"].values == 1) & (np.abs(c["file_mtime"].values - mt) < 1e-3)
    for v in ds.data_vars:
        if v in c:
            ds[v].values[ok] = c[v].values[ok]
    ds["computed"].values[:] = ok.astype(np.int8)
    if centers is not None and recipe["region"] == "track":
        invalidate_moved(ds, recipe, centers)
    return ds


def invalidate_moved(ds, recipe, centers):
    """Mark computed times whose track-region centre differs from `centers` (the track
    was changed) as not computed.  Returns how many."""
    dx, dy = recipe["offset"]
    n = 0
    for t in np.flatnonzero(ds["computed"].values == 1):
        c = centers.get(int(t))
        cx, cy = ds["center_x_km"].values[t], ds["center_y_km"].values[t]
        if c is None or not (abs(c[0] + dx - cx) < 1e-3 and abs(c[1] + dy - cy) < 1e-3):
            ds["computed"].values[t] = 0
            n += 1
    return n


def store(run, recipe, ds):
    """Write the dataset to the cache (best effort)."""
    try:
        os.makedirs(cache_dir(), exist_ok=True)
        path = _cache_path(run, recipe)
        tmp = path + f".{os.getpid()}.tmp"
        ds.to_netcdf(tmp)
        os.replace(tmp, path)
    except (OSError, ValueError):
        pass


# ------------------------------------------------------------------ compute
def compute(run, F, recipe, ds, centers=None, storm=None, on_result=None, cancelled=None,
            workers=None, times=None):
    """Fill the not-yet-computed times of `ds` (from cached()), or of those among
    `times` (output indices; None: every time).  centers: {t: (x, y)} for track
    regions; storm: {t: (u, v)} ground-relative storm motion for storm-relative
    fields.  on_result(ds, done, total) after each time.  Returns (ds, {t: reason}) for
    times that could not be computed."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import multiprocessing as mp

    centers, storm = centers or {}, storm or {}
    from .fields import column_stride, layer_top, split_deriv

    d = F[recipe["field"]]
    op, name = split_deriv(recipe["field"])  # (a derivative: op of field `name`)
    b = F[name]
    # (stag, scale, ndim) of the native fields read: derived fields work in raw units
    natives = {n: (run.vars[n].stag, 1.0, run.vars[n].ndim)
               for n in (b.natives if b.derived else (name,)) if n in run.vars}
    # derivative inputs of a derived field (∂w/∂z ...) are of the display-unit field
    dscale = {split_deriv(n)[1]: F[split_deriv(n)[1]].scale
              for n in b.deps if split_deriv(n)[0]} if b.derived else {}
    if not b.derived:
        natives[name] = (run.vars[name].stag, b.scale, run.vars[name].ndim)
    # a one-point border around the region for horizontal derivatives
    halo = op in ("ddx", "ddy", "gradh") or (b.derived and not b.pointwise
                                              and not b.column)
    column = None
    if b.column:  # (levels of its layer, their thickness in it, heights)
        ks_c, dz_c = b.levels(run.z, run.zf)
        column = (ks_c, dz_c, run.z[ks_c], layer_top(b, run))
    ctx = dict(F.ctx)
    skipped, tasks = {}, []
    vmode = recipe["vmode"] if d.ndim == 3 else "2d"
    weights = run.level_weights(recipe["z"]) if vmode == "height" else None
    ks = levels(run, recipe) if vmode == "layer" else None
    t_done = ds["computed"].values
    for t in range(len(run.times)) if times is None else sorted(set(times)):
        if t_done[t]:
            continue
        reg = region_at(run, recipe, centers.get(t))
        if reg is None:
            skipped[t] = "no track fix" if recipe["region"] == "track" else "empty region"
            continue
        if t in run._writing:
            skipped[t] = "file being written"
            continue
        i0, i1, j0, j1, mask, cen = reg
        c = dict(ctx)
        if d.storm:
            c["storm"] = tuple(storm.get(t, (run.umove, run.vmove)))
        e0, e1, f0, f1 = ((max(i0 - 1, 0), min(i1 + 1, run.ni), max(j0 - 1, 0),
                           min(j1 + 1, run.nj)) if halo else (i0, i1, j0, j1))
        tasks.append(dict(
            t=t, path=run.files[t], field=name, op=op, natives=natives, dscale=dscale,
            avail=sorted(run.vars), box=(i0, i1, j0, j1), halo=(e0, e1, f0, f1),
            mask=mask, ctx=c, reduce=recipe["reduce"],
            pct=recipe.get("pct", 99.0), vmode=vmode, weights=weights,
            zkm=recipe.get("z", np.nan), levels=ks,
            zlev=None if ks is None else run.z[ks], xh=run.xh[i0:i1], yh=run.yh[j0:j1],
            xe=run.xh[e0:e1], ye=run.yh[f0:f1], zfull=np.asarray(run.z), nk=run.nk,
            column=column, stride=column_stride(run) if b.costly else 1, ni=run.ni,
            nj=run.nj, center=cen))
    total, done = len(tasks), 0
    if not tasks:
        return ds, skipped
    nw = max(1, min(int(workers or run.workers), len(tasks)))
    by_t = {tk["t"]: tk for tk in tasks}
    last_store = _time.time()
    ex = ProcessPoolExecutor(max_workers=nw, mp_context=mp.get_context("spawn"))
    try:
        futs = [ex.submit(_worker, tk) for tk in tasks]
        for fut in as_completed(futs):
            if cancelled and cancelled():
                for f in futs:
                    f.cancel()
                break
            r = fut.result()
            t = r["t"]
            done += 1
            if "error" in r:
                skipped[t] = r["error"]
            else:
                _put(ds, t, r, by_t[t]["center"], os.path.getmtime(run.files[t]))
            if on_result:
                on_result(ds, done, total)
            if _time.time() - last_store > 20:  # partial results survive a crash/stop
                store(run, recipe, ds)
                last_store = _time.time()
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    store(run, recipe, ds)
    return ds, skipped


def _put(ds, t, r, center, mtime):
    ds["value"].values[t] = r["value"]
    for k, c in (("x", "x_km"), ("y", "y_km"), ("z", "z_km")):
        ds[c].values[t] = r.get(k, np.nan)
    if center is not None:
        ds["center_x_km"].values[t], ds["center_y_km"].values[t] = center
    ds["npoints"].values[t] = r["npts"]
    if r.get("prof") is not None and "profile" in ds:
        ds["profile"].values[t] = r["prof"]
    ds["computed"].values[t] = 1
    ds["file_mtime"].values[t] = mtime


# ------------------------------------------------------------------ files
_TABLE = ["time_index", "time", "time_hms", "value", "x_km", "y_km", "z_km",
          "center_x_km", "center_y_km", "npoints"]


def table(ds):
    """The computed times as a pandas DataFrame (time in s; value named after the
    recipe)."""
    import pandas as pd

    ok = ds["computed"].values == 1
    df = pd.DataFrame({c: ds[c].values[ok] for c in _TABLE})
    return df.rename(columns={"time": "time_s"})


def save(ds, path):
    """Write the computed times to `path`; the format follows the extension (.nc,
    .csv, .txt, .pkl).  Creates missing directories.  Returns the absolute path."""
    path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    ext = os.path.splitext(path)[1].lower()
    if ext not in FORMATS:
        raise ValueError(f"unknown format '{ext}': use one of " + ", ".join(FORMATS))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sub = ds.isel(time=np.flatnonzero(ds["computed"].values == 1))
    if ext == ".nc":
        sub.drop_vars(["computed", "file_mtime"]).to_netcdf(path)
    elif ext == ".pkl":
        import pickle
        prof = None
        if "profile" in sub:
            import pandas as pd
            prof = pd.DataFrame(sub["profile"].values, index=sub["time"].values,
                                columns=sub["z"].values)
            prof.index.name, prof.columns.name = "time_s", "z_km"
        with open(path, "wb") as f:
            pickle.dump(dict(series=table(ds), profile=prof, recipe=json.loads(ds.attrs["recipe"]),
                             attrs=dict(ds.attrs)), f)
    else:
        with open(path, "w") as f:
            f.write(to_text(ds, "csv" if ext == ".csv" else "txt"))
    return path


def to_text(ds, fmt="csv"):
    df = table(ds)
    a = ds.attrs
    head = [
        a["title"], f"created: {a['created']}", f"run: {a['run']}",
        f"series: {a['description']}", f"recipe: {a['recipe']}", a["perturbations"],
        a["grid"],
        "value: the reduced field; x/y/z_km: where the min/max is (nan for mean / "
        "percentile); center_*: region centre for track regions; npoints: grid columns",
    ]
    if "profile" in ds:
        head.append("per-level values (time x height) are kept only in .nc / .pkl files")
    buf = io.StringIO()
    for h in head:
        buf.write(f"# {h}\n")
    cols = list(df.columns)

    def cell(c, v):
        if c in ("time_index", "npoints"):
            return f"{int(v):d}"
        if c == "time_hms":
            return str(v)
        if c == "time_s":
            return f"{v:.0f}"
        return f"{v:.6g}" if np.isfinite(v) else "nan"

    body = [[cell(c, v) for c, v in zip(cols, row)] for row in df.itertuples(index=False)]
    if fmt == "csv":
        buf.write(",".join(cols) + "\n")
        for b in body:
            buf.write(",".join(b) + "\n")
    else:
        w = [max(len(c), *(len(b[i]) for b in body)) if body else len(c)
             for i, c in enumerate(cols)]
        buf.write("  ".join(c.rjust(x) for c, x in zip(cols, w)) + "\n")
        for b in body:
            buf.write("  ".join(v.rjust(x) for v, x in zip(b, w)) + "\n")
    return buf.getvalue()


def load(run, path, F=None):
    """A saved series as a dataset on this run's times (labels and units from the
    field catalog F when given).  Returns (ds, recipe, note)."""
    import xarray as xr

    path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    ext = os.path.splitext(path)[1].lower()
    src = None  # run the file was computed for

    def new(recipe, label="", units=""):
        if F is not None and recipe["field"] in F:
            label, units = F[recipe["field"]].label, F[recipe["field"]].units
        return empty(run, recipe, label, units)

    if ext == ".nc":
        with xr.open_dataset(path) as s:
            s = s.load()
        recipe, src = json.loads(s.attrs["recipe"]), s.attrs.get("run")
        ds = new(recipe, s.attrs.get("field_label", ""), s.attrs.get("units", ""))
        idx = [int(i) for i in s["time_index"].values]
        for v in ds.data_vars:
            if v in s and v not in ("computed", "file_mtime"):
                ds[v].values[idx] = s[v].values
        ds.attrs.update({k: v for k, v in s.attrs.items() if k in ("created", "description")})
    elif ext == ".pkl":
        import pickle
        with open(path, "rb") as f:
            obj = pickle.load(f)
        recipe, df = obj["recipe"], obj["series"]
        at = obj.get("attrs", {})
        src = at.get("run")
        ds = new(recipe, at.get("field_label", ""), at.get("units", ""))
        idx = df["time_index"].astype(int).to_numpy()
        for c in _TABLE[3:]:
            if c in df:
                ds[c].values[idx] = df[c].to_numpy()
        if obj.get("profile") is not None and "profile" in ds:
            ds["profile"].values[idx] = obj["profile"].to_numpy()
    elif ext in (".csv", ".txt"):
        import pandas as pd
        recipe = None
        with open(path) as f:
            for line in f:
                if not line.startswith("#"):
                    break
                if line.startswith("# recipe:"):
                    recipe = json.loads(line.split(":", 1)[1])
                elif line.startswith("# run:"):
                    src = line.split(":", 1)[1].strip()
        if recipe is None:
            raise ValueError("no '# recipe:' line in the header (not a cm1view series)")
        df = pd.read_csv(path, comment="#", sep="," if ext == ".csv" else r"\s+")
        ds = new(recipe)
        idx = df["time_index"].astype(int).to_numpy()
        for c in _TABLE[3:]:
            if c in df:
                ds[c].values[idx] = df[c].to_numpy()
    else:
        raise ValueError(f"unknown format '{ext}': use one of " + ", ".join(FORMATS))
    if len(idx) and max(idx) >= len(run.times):
        raise ValueError("the file has more times than this run")
    ds["computed"].values[idx] = 1
    note = f"computed for another run ({src})" if src and src != run.path else ""
    return ds, recipe, note
