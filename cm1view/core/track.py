"""Mesocyclone tracking through output times, and export of the track to CSV / text."""

import io
import os
import time as _time

import numpy as np
from scipy.ndimage import gaussian_filter, label as _label, uniform_filter

METRICS = {"Updraft: w at height": "w", "2–5 km updraft helicity": "uh",
           "Vertical vorticity at height": "zeta", "Pressure low: min p′ at height": "pmin",
           "Other field (max or min)…": "field"}
METRIC_LABEL = {"uh": "2–5 km UH", "zeta": "ζ", "w": "w", "pmin": "p′"}
METRIC_UNITS = {"uh": "m²/s²", "zeta": "1/s", "w": "m/s", "pmin": "hPa"}
# default "lost" threshold: tracking stops when the metric falls below this (above it
# for a minimum); "field" has none
METRIC_STOP = {"uh": 50.0, "zeta": 0.01, "w": 5.0, "pmin": -0.5, "field": None}
UH_LAYER = (2.0, 5.0)  # km AGL


def available(run):
    return run.has("winterp")


def metrics(run):
    """The METRICS this run has the fields for."""
    ok = {"w": run.has("winterp"), "uh": run.has("winterp") and run.has("zvort"),
          "zeta": run.has("zvort"),
          "pmin": run.has("prspert") or (run.has("prs") and run.has("prs0")),
          "field": True}
    return {k: v for k, v in METRICS.items() if ok[v]}


def sense(opts):
    """'max' or 'min': which extreme of the field marks the storm."""
    m = opts["metric"]
    return "min" if m == "pmin" else opts.get("sense", "max") if m == "field" else "max"


def label(opts, fields=None):
    """(label, units) of the tracked value."""
    m = opts["metric"]
    if m != "field":
        return METRIC_LABEL[m], METRIC_UNITS[m]
    d = fields[opts["field"]] if fields is not None and opts.get("field") in fields else None
    return (d.label, d.units) if d is not None else (opts.get("field") or "value", "")


def column(opts):
    """Name of the tracked-value column in saved tracks."""
    m, z = opts["metric"], f"{opts['zkm']:g}km"
    if m == "field":
        return f"{sense(opts)}_{opts.get('field') or 'value'}_{z}"
    return {"uh": "uh_2_5km", "zeta": f"zeta_{z}", "w": f"w_{z}", "pmin": f"prspert_{z}"}[m]


def _beyond(value, stop, sgn):
    """True while the value is past the stop threshold (above it for a maximum)."""
    return stop is None or sgn * value >= sgn * stop


def _smooth(a, smooth, dxk, kernel):
    """Box average of width `smooth` km, or Gaussian with sigma = `smooth` km."""
    if kernel == "gauss":
        sig = smooth / dxk
        return gaussian_filter(a, sig, mode="nearest") if sig > 0.3 else a
    ns = max(1, int(round(smooth / dxk)) | 1)
    return uniform_filter(a, size=ns, mode="nearest") if ns > 1 else a


def _fields(run, fields):
    if fields is None:
        from .fields import Fields
        fields = Fields(run)
    return fields


def metric_field(run, t, metric, zkm=1.0, cancelled=None, field=None, fields=None):
    """2D metric on the scalar grid at time t, plus extra 2D fields to report.
    UH = sum over the 2-5 km layer of w * zeta * dz (instantaneous).  'pmin' is p′
    and 'field' the field named `field` at zkm (fields: the run's Fields, made if
    None)."""
    if metric in ("pmin", "field"):
        name = "prspert" if metric == "pmin" else field
        return _fields(run, fields).plane(name, t, "height", zkm), {}
    if metric == "zeta":
        return run.read_height("zvort", t, zkm), {}
    if metric == "w":
        return run.read_height("winterp", t, zkm), {}
    if run.terrain:  # (each column's own levels: those in 2-5 km, thickness in it)
        from .fields import column_levels_3d
        ks, dzs, _ = column_levels_3d(run.heights(t), run.heights(t, w=True), *UH_LAYER)
        dzs = dzs.astype(np.float32)
    else:
        ks = np.flatnonzero((run.z >= UH_LAYER[0]) & (run.z <= UH_LAYER[1]))
    uh = np.zeros((run.nj, run.ni), np.float32)
    wmax = np.full((run.nj, run.ni), -np.inf, np.float32)
    zmax = np.full((run.nj, run.ni), -np.inf, np.float32)
    lv = run.read_levels(["winterp", "zvort"], t, ks, cancelled=cancelled)
    if lv is None:  # (cancelled)
        return None, None
    for n, k in enumerate(ks):
        w, zeta = lv["winterp"][n], lv["zvort"][n]
        if run.terrain:
            inside = dzs[n] > 0  # (dz 0 outside the layer)
            uh += w * zeta * dzs[n]
            w, zeta = np.where(inside, w, -np.inf), np.where(inside, zeta, -np.inf)
        else:
            dz = float(run.zf[k + 1] - run.zf[k]) * 1000.0
            uh += w * zeta * dz
        np.maximum(wmax, w, out=wmax)
        np.maximum(zmax, zeta, out=zmax)
    return uh, {"w_max_2_5km": wmax, "zeta_max_2_5km": zmax}


def locate(run, field, extras, x, y, opts, snap=True, whole=False):
    """Fix near (x, y) km: the extreme (opts 'sense': max or min) of the smoothed
    field within opts['radius'] km.
    opts: radius, smooth, kernel ('box': width `smooth` km, 'gauss': sigma), nearest,
    fix, cutoff.
    nearest: weight the field by a Gaussian of the distance from (x, y) (sigma =
    radius / 2) first, so a nearby core wins over a slightly stronger one farther
    away (keeps the track from hopping between neighbouring cores).
    whole: search the whole domain instead (x, y and radius unused).
    fix 'centroid': the fix is the field-weighted centre of the connected area around
    the extreme where the smoothed field is beyond `cutoff` % of the way from the
    disc's background (0, or the disc's weakest value if that is past 0) to the
    extreme.
    Returns dict(x, y, value, **extras) with value = the raw extreme and extras = raw
    maxima within `smooth` km of the fix (or None if the search disc is off the
    domain)."""
    radius, smooth = opts["radius"], opts["smooth"]
    whole = whole or opts.get("whole", False)
    sgn = -1.0 if sense(opts) == "min" else 1.0
    dxk = run.dx / 1000.0
    if whole:
        i0, i1, j0, j1 = 0, run.ni, 0, run.nj
    else:
        i, j = run.ij(x, y)
        r = int(np.ceil(radius / dxk))
        i0, i1 = max(0, i - r), min(run.ni, i + r + 1)
        j0, j1 = max(0, j - r), min(run.nj, j + r + 1)
    if i0 >= i1 or j0 >= j1:
        return None
    sub = sgn * field[j0:j1, i0:i1]
    ok = np.isfinite(sub)
    if not ok.any():
        return None
    sm = _smooth(np.where(ok, sub, np.min(sub[ok])), smooth, dxk,
                 opts.get("kernel", "box"))
    jj, ii = np.mgrid[j0:j1, i0:i1]
    d2 = (run.xh[ii] - x) ** 2 + (run.yh[jj] - y) ** 2 if not whole else None
    disc = ok if whole else ok & (d2 <= radius ** 2)
    sm = np.where(disc, sm, -np.inf)
    if not (whole or snap):
        jf, if_ = j, i
        xf, yf = float(run.xh[i]), float(run.yh[j])
    else:
        pick = sm
        base = max(0.0, float(np.min(sm[disc]))) if disc.any() else 0.0
        if not whole and opts.get("nearest", True):
            wt = np.exp(-0.5 * d2 / (0.5 * radius) ** 2)
            pick = np.where(sm > base, base + (sm - base) * wt, sm)
        jm, im = np.unravel_index(int(np.argmax(pick)), pick.shape)
        jf, if_ = j0 + jm, i0 + im
        xf, yf = float(run.xh[if_]), float(run.yh[jf])
        if opts.get("fix") == "centroid" and np.isfinite(sm[jm, im]):
            cut = base + float(opts.get("cutoff", 50.0)) / 100.0 * (sm[jm, im] - base)
            lab, _ = _label(sm >= cut)
            core = lab == lab[jm, im]
            wsum = (sm - cut)[core]
            if wsum.sum() > 0:
                xf = float(np.sum(run.xh[ii[core]] * wsum) / wsum.sum())
                yf = float(np.sum(run.yh[jj[core]] * wsum) / wsum.sum())
                if_, jf = run.ij(xf, yf)
    h = max(1, int(round(smooth / dxk)) // 2)
    win = (slice(max(0, jf - h), jf + h + 1), slice(max(0, if_ - h), if_ + h + 1))
    out = dict(x=xf, y=yf, value=float(sgn * np.nanmax(sgn * field[win])))
    for k, a in extras.items():
        out[k] = float(np.max(a[win]))
    return out


def track(run, t0, x0, y0, opts, direction="both", existing=None, on_fix=None,
          cancelled=None, progress=None, fields=None):
    """Follow the feature at (x0, y0) from time t0 (x0 None: start from the domain-wide
    extreme).  opts: metric, zkm, field, sense, radius, smooth, kernel, stop, snap,
    nearest, whole, fix, cutoff, and t_from / t_to (output indices; the run's first
    / last when missing) bounding the tracked times.  `existing` fixes ({t: fix}) on
    the side not being tracked are kept.  on_fix(fixes) is called after every new
    fix.  Returns {t: fix}."""
    from .run import ahead, ahead_width

    fixes = dict(existing or {})
    lo, hi = opts.get("t_from", 0), opts.get("t_to", len(run.times) - 1)
    sgn = -1.0 if sense(opts) == "min" else 1.0
    metric = opts["metric"]
    if metric in ("pmin", "field"):
        fields = _fields(run, fields)  # (one for every time)

    def field_at(t):  # (the same whatever the fixes before it: read ahead of them)
        return metric_field(run, t, metric, opts["zkm"], cancelled, opts.get("field"),
                            fields)

    f, ex = field_at(t0)
    first = None if f is None else locate(run, f, ex, x0, y0, opts, opts.get("snap", True),
                                          whole=x0 is None)
    del f, ex
    if first is None:
        return fixes
    # the times ahead being read while one is searched: by what each reads
    per = 4 * run.nj * run.ni
    if metric == "uh":
        nbytes = 2 * per * max(1, int(np.sum((np.asarray(run.z) >= UH_LAYER[0])
                                             & (np.asarray(run.z) <= UH_LAYER[1]))))
    elif metric in ("pmin", "field"):
        nbytes = fields.read_bytes("prspert" if metric == "pmin" else opts.get("field"),
                                   "height")
    else:
        nbytes = 2 * per
    width = ahead_width(run, nbytes)
    if direction == "forward":
        fixes = {t: f for t, f in fixes.items() if t < t0}
    elif direction == "backward":
        fixes = {t: f for t, f in fixes.items() if t > t0}
    else:
        fixes = {}
    first["source"] = "auto"
    fixes[t0] = first
    if on_fix:
        on_fix(dict(fixes))
    steps = {"forward": [1], "backward": [-1], "both": [1, -1]}[direction]
    total = sum(max(0, hi - t0) if s > 0 else max(0, t0 - lo) for s in steps)
    done = 0
    for s in steps:
        t = t0
        coming = ahead(field_at, range(t0 + s, hi + 1 if s > 0 else lo - 1, s), width)
        try:
            while lo <= t + s <= hi:
                if cancelled and cancelled():
                    return fixes
                tn = t + s
                # extrapolate with the grid-relative motion of the last two fixes
                px, py = fixes[t]["x"], fixes[t]["y"]
                if t - s in fixes:
                    dt_prev = run.times[t] - run.times[t - s]
                    dt_next = run.times[tn] - run.times[t]
                    if dt_prev:
                        px += (fixes[t]["x"] - fixes[t - s]["x"]) * dt_next / dt_prev
                        py += (fixes[t]["y"] - fixes[t - s]["y"]) * dt_next / dt_prev
                if progress:
                    progress(done, total, tn)
                _, (f, ex) = next(coming)
                fx = None if f is None else locate(run, f, ex, px, py, opts)
                done += 1
                if fx is None or not _beyond(fx["value"], opts.get("stop"), sgn):
                    break
                fx["source"] = "auto"
                fixes[tn] = fx
                if on_fix:
                    on_fix(dict(fixes))
                t = tn
        finally:
            coming.close()  # (stops the reads of the times past the last fix)
    return fixes


def place(run, t, x, y, opts, fields=None):
    """A hand-placed fix at (x, y) km at time t: snapped to the nearby extreme when
    opts['snap'], and carrying the tracked value there either way."""
    f, ex = metric_field(run, t, opts["metric"], opts["zkm"], field=opts.get("field"),
                         fields=fields)
    fx = locate(run, f, ex, x, y, dict(opts, whole=False), opts.get("snap", False))
    if fx is None:
        return None
    if not opts.get("snap", False):
        fx["x"], fx["y"] = float(x), float(y)
    fx["source"] = "manual"
    return fx


STORM_COL = "storm"  # optional column naming the storm of each row (several per file)


def storm_name(name):
    """A storm name as written to a track file: stripped, with spaces and commas made
    underscores (so whitespace tables still split into columns)."""
    import re
    return re.sub(r"[\s,]+", "_", str(name or "").strip())


def _table(path):
    """(absolute path, DataFrame) of a track file (CSV, or whitespace columns), comment
    lines ('#') skipped."""
    import pandas as pd

    path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    with open(path) as f:
        first = next((ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")), "")
    sep = "," if "," in first else r"\s+"
    df = pd.read_csv(path, comment="#", sep=sep, engine="python")
    df.columns = [c.strip() for c in df.columns]
    return path, df


def _storm_of(df):
    """Each row's storm name ("" without a storm column, or for a blank cell)."""
    if STORM_COL not in df:
        return np.full(len(df), "", object)
    return np.array(["" if v != v or v is None else storm_name(v)  # (v != v: NaN)
                     for v in df[STORM_COL]], object)


def storms(path):
    """The storms a track file holds, in the order they first appear; [] for a file
    without a storm column (one storm, as CM1 tracks are)."""
    _, df = _table(path)
    if STORM_COL not in df:
        return []
    return list(dict.fromkeys(_storm_of(df)))


def load(run, path, storm=None):
    """Fixes {t: fix} from a CSV / whitespace table with x_km, y_km or loc_x, loc_y
    (grid-relative) or x_ground_km, y_ground_km, and time_s, time_hms, time_index or
    time (minutes; seconds if the values are too large for minutes).  Lines starting
    with '#' are comments.  Times are matched to the nearest output time; a column
    named value or like uh_* / zeta_* / w_* / prspert_* / max_* / min_* becomes the
    fix value.
    A file may hold several storms, told apart by a 'storm' column (a name or number
    per row): `storm` picks one (None: the file's first).  A storm the file lacks is a
    ValueError; without a storm column the whole file is the one storm whatever
    `storm` says."""
    _, df = _table(path)
    names = _storm_of(df)
    if STORM_COL in df:
        order = list(dict.fromkeys(names))
        want = order[0] if storm is None and order else storm_name(storm)
        if want not in order:
            raise ValueError(f"no storm {want!r} in the file (it has "
                             f"{', '.join(repr(n) for n in order) or 'none'})")
        df = df[names == want].reset_index(drop=True)
    return _fixes(run, df)


def load_all(run, path):
    """{storm: fixes} of every storm in a track file, in file order ({"": fixes} for a
    file without a storm column)."""
    _, df = _table(path)
    names = _storm_of(df)
    return {n: _fixes(run, df[names == n].reset_index(drop=True))
            for n in dict.fromkeys(names)}


def _fixes(run, df):
    """Fixes {t: fix} of one storm's rows (see load)."""
    times = np.asarray(run.times)
    n_rows = len(df)
    # each row takes the first time / position columns that hold numbers in it: a file
    # of several storms may mix them (a storm saved by cm1view has time_s, another
    # written by hand only time_index; the columns it lacks are blank in its rows)
    tsec = np.full(n_rows, np.nan)
    by_index = np.zeros(n_rows, bool)  # (a time_index row is always an output time)
    found = False
    for c in ("time_s", "time_hms", "time_index", "time"):
        if c not in df:
            continue
        found = True
        if c == "time_hms":
            def hms(v):
                try:
                    h, m, s = (float(p) for p in str(v).split(":"))
                except ValueError:
                    return np.nan
                return h * 3600 + m * 60 + s
            tv = np.array([hms(v) for v in df[c]], float)
        else:
            tv = pd_floats(df[c])
        if c == "time_index":
            ok = np.isfinite(tv)
            tv = np.where(ok, times[np.clip(np.nan_to_num(tv).astype(int), 0,
                                            len(times) - 1)], np.nan)
        elif c == "time":  # e.g. storm_tracks/*.csv: model minutes
            fin = tv[np.isfinite(tv)]
            if len(fin) and np.max(fin) <= times[-1] / 60.0 + 1.0:
                tv = tv * 60.0
        fill = ~np.isfinite(tsec) & np.isfinite(tv)
        tsec[fill] = tv[fill]
        if c == "time_index":
            by_index |= fill
    if not found:
        raise ValueError("needs a time_s, time_hms, time_index or time (min) column")
    x, y = np.full(n_rows, np.nan), np.full(n_rows, np.nan)
    found = False
    for cx, cy in (("x_km", "y_km"), ("loc_x", "loc_y"), ("x_ground_km", "y_ground_km")):
        if not {cx, cy} <= set(df.columns):
            continue
        found = True
        xv, yv = pd_floats(df[cx]), pd_floats(df[cy])
        if cx == "x_ground_km":
            xv = xv - run.umove * tsec / 1000.0
            yv = yv - run.vmove * tsec / 1000.0
        fill = ~np.isfinite(x) & np.isfinite(xv) & np.isfinite(yv)
        x[fill], y[fill] = xv[fill], yv[fill]
    if not found:
        raise ValueError("needs x_km, y_km or loc_x, loc_y (grid), or x_ground_km, "
                         "y_ground_km columns")
    # the value column: in a file of several storms each may have its own (tracked on
    # different fields), the others blank in its rows -> the first with a number here
    cand = [c for c in df.columns if c == "value"
            or c.split("_")[0] in ("uh", "zeta", "w", "prspert", "max", "min")
            and c not in ("w_max_2_5km", "zeta_max_2_5km")]
    vals = {c: pd_floats(df[c]) for c in cand}
    vcol = next((c for c in cand if np.isfinite(vals[c]).any()), cand[0] if cand else None)
    keep = [c for c in ("w_max_2_5km", "zeta_max_2_5km") if c in df]
    fixes = {}
    for n in range(len(df)):
        if not (np.isfinite(tsec[n]) and np.isfinite(x[n])):
            continue  # (a row without a time or a position)
        t = int(np.argmin(np.abs(times - tsec[n])))
        if abs(times[t] - tsec[n]) > 1.0 and not by_index[n]:
            continue  # not an output time of this run
        fx = dict(x=float(x[n]), y=float(y[n]),
                  value=float(vals[vcol][n]) if vcol else float("nan"))
        for c in keep:
            fx[c] = float(pd_floats(df[c])[n])
        src = df["source"].iloc[n] if "source" in df else None
        fx["source"] = "loaded" if src is None or src != src or str(src) in ("", "nan") \
            else str(src)  # (blank in another storm's rows)
        fixes[t] = fx
    return fixes


def pd_floats(col):
    """A column as floats, NaN where a cell is not a number (blank, 'nan', text)."""
    import pandas as pd
    return pd.to_numeric(col, errors="coerce").to_numpy(float)


def motion_window(run):
    """Seconds of track the storm motion is fitted over (the track_motion_window
    setting, minutes; auto: the run's own, Run.track_window); 0: centred differences."""
    from .. import config
    w = config.get("track_motion_window")
    if w == "auto":
        return float(getattr(run, "track_window", 0.0) or 0.0)
    return max(0.0, 60.0 * float(w))


def motion(run, fixes, window=None):
    """Ground-relative motion (m/s) at every fix, from the ground-relative track (grid
    positions + grid translation).  window (s; None: motion_window(run)): the slope of
    a least-squares line through the fixes within window / 2 of each fix (fewer near
    the ends), which steadies a jumpy track (WoFS: every cycle is a fresh analysis, so
    the fixes jump by its increments); 0, or fewer than two fixes in the window:
    centred differences."""
    ts = sorted(fixes)
    if len(ts) < 2:
        return {t: (np.nan, np.nan) for t in ts}
    tsec = np.array([run.times[t] for t in ts], float)
    xg = np.array([fixes[t]["x"] * 1000.0 + run.umove * run.times[t] for t in ts])
    yg = np.array([fixes[t]["y"] * 1000.0 + run.vmove * run.times[t] for t in ts])
    u, v = np.gradient(xg, tsec), np.gradient(yg, tsec)
    w = motion_window(run) if window is None else max(0.0, float(window))
    if w > 0:
        for n in range(len(ts)):
            near = np.abs(tsec - tsec[n]) <= 0.5 * w + 1e-6
            if near.sum() < 2:
                continue
            tt = tsec[near] - tsec[n]
            d = tt - tt.mean()
            den = float(np.sum(d * d))
            if den > 0:
                u[n] = float(np.sum(d * xg[near]) / den)
                v[n] = float(np.sum(d * yg[near]) / den)
    return {t: (float(a), float(b)) for t, a, b in zip(ts, u, v)}


def position(fixes, t):
    """Fix position at time index t, or None."""
    f = fixes.get(t)
    return None if f is None else (f["x"], f["y"])


def rows(run, fixes):
    """Table rows (list of dicts) of a track, in time order."""
    mot = motion(run, fixes)
    # extra columns: union over fixes (hand-placed / loaded ones may lack some),
    # with the source last
    extra = [k for k in dict.fromkeys(k for f in fixes.values() for k in f)
             if k not in ("x", "y", "value", "source")] + ["source"]
    out = []
    for t in sorted(fixes):
        f = fixes[t]
        s = float(run.times[t])
        r = dict(time_index=t, file=os.path.basename(run.files[t]), time_s=s,
                 time_hms=run.time_label(t), x_km=f["x"], y_km=f["y"],
                 x_ground_km=f["x"] + run.umove * s / 1000.0,
                 y_ground_km=f["y"] + run.vmove * s / 1000.0,
                 u_motion_ms=mot[t][0], v_motion_ms=mot[t][1], value=f["value"])
        r.update({k: f.get(k, "auto" if k == "source" else float("nan")) for k in extra})
        out.append(r)
    return out


_FMT = {"time_index": "{:d}", "time_s": "{:.0f}", "x_km": "{:.3f}", "y_km": "{:.3f}",
        "x_ground_km": "{:.3f}", "y_ground_km": "{:.3f}", "u_motion_ms": "{:.2f}",
        "v_motion_ms": "{:.2f}"}


def to_text(run, fixes, opts, fmt="csv", fields=None, storm=None, others=None):
    """The track as CSV (fmt='csv') or a whitespace-aligned table ('txt'), with a
    '#'-commented header describing the run, method and columns.
    storm: the storm's name -> a 'storm' column (first), so a file can hold several;
    others: rows of the file's other storms to keep, a list of {column: text} (from
    save), written in their place in `others` order (this storm where it was, or
    last)."""
    rs = rows(run, fixes)
    m, sn = opts["metric"], sense(opts)
    lab, units = label(opts, fields)
    vname = column(opts)
    stop = opts.get("stop")
    nt = len(run.times)
    lo, hi = opts.get("t_from", 0), opts.get("t_to", nt - 1)
    cols = list(rs[0].keys()) if rs else ["time_index", "time_s", "x_km", "y_km", "value"]
    win = motion_window(run)
    storm = storm_name(storm) if storm is not None else None
    head = [
        "cm1view mesocyclone track",
        f"created: {_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"run: {run.path}",
        f"tracked field: {sn}imum of {lab}"
        + ("" if m == "uh" else f" at {opts['zkm']:g} km AGL")
        + (f" ({units})" if units else "") + f"  -> column '{vname}'",
        ("search: whole domain at every time" if opts.get("whole") else
         f"search radius {opts['radius']:g} km, prefer nearest core: "
         f"{opts.get('nearest', True)}")
        + f", smoothing {opts['smooth']:g} km "
        + ("(Gaussian sigma)" if opts.get("kernel") == "gauss" else "(box width)")
        + ("" if stop is None else
           f", stop {'below' if sn == 'max' else 'above'} {stop:g}"),
        "fix: " + (f"centroid of the area beyond {opts.get('cutoff', 50.0):g}% of the "
                   f"{sn}imum" if opts.get("fix") == "centroid" else f"the {sn}imum")
        + f", times {run.time_label(lo)} – {run.time_label(hi)}",
        f"grid translation (umove, vmove) = ({run.umove:g}, {run.vmove:g}) m/s",
        "x_km, y_km: position on the (translating) model grid; "
        "x/y_ground_km: ground-relative = grid + (umove, vmove) * time_s",
        "u/v_motion_ms: ground-relative storm motion ("
        + (f"least-squares fit over {win / 60.0:g} min of track)" if win > 0 else
           "centred differences)"),
        f"{vname}: raw {sn} within the smoothing box around the fix",
        "source: auto = tracked, manual = placed by hand, loaded = read from a file",
    ]
    if storm is not None:
        head.insert(3, "storm: which storm a row belongs to (a file may hold several; "
                       "the method lines above are this file's last saved storm, "
                       f"{storm!r})")
    names = [vname if c == "value" else c for c in cols]

    def cell(c, v):
        if isinstance(v, str):
            return v
        if c in _FMT:
            return _FMT[c].format(v) if np.isfinite(v) else "nan"
        return f"{v:.6g}"

    body = [[cell(c, r[c]) for c in cols] for r in rs]
    if storm is not None:
        names, body = [STORM_COL] + names, [[storm] + b for b in body]
        order = list(dict.fromkeys([r.get(STORM_COL, "") for r in others or []]))
        if storm not in order:
            order.append(storm)
        names += [c for c in dict.fromkeys(c for r in others or [] for c in r)
                  if c not in names]
        mine = [b + ["nan"] * (len(names) - len(b)) for b in body]
        body = []
        for n in order:
            if n == storm:
                body += mine
            else:
                body += [[r.get(c, "nan") or "nan" for c in names]
                         for r in others if r.get(STORM_COL, "") == n]
    buf = io.StringIO()
    for h in head:
        buf.write(f"# {h}\n")
    if fmt == "csv":
        buf.write(",".join(names) + "\n")
        for b in body:
            buf.write(",".join(b) + "\n")
    else:
        widths = [max(len(n), *(len(b[i]) for b in body)) if body else len(n)
                  for i, n in enumerate(names)]
        buf.write("  ".join(n.rjust(w) for n, w in zip(names, widths)) + "\n")
        for b in body:
            buf.write("  ".join(v.rjust(w) for v, w in zip(b, widths)) + "\n")
    return buf.getvalue()


def _other_storms(path, storm):
    """Rows ({column: text}) of the storms other than `storm` in the track file at
    path, to keep when saving `storm` into it; [] when there is no such file or it has
    no storm column (it is then replaced whole, as a one-storm file always was)."""
    if not os.path.isfile(path):
        return []
    try:
        _, df = _table(path)
    except Exception:  # noqa: BLE001  (not a readable track: replaced)
        return []
    if STORM_COL not in df:
        return []
    names = _storm_of(df)
    out = []
    for n, (_, r) in zip(names, df.iterrows()):
        if n == storm:
            out.append({STORM_COL: n})  # (keeps its place in the order)
            continue
        d = {c: ("nan" if v != v else str(v)) for c, v in r.items()}
        d[STORM_COL] = n
        out.append(d)
    return out


def save(run, fixes, opts, path, fields=None, storm=None):
    """Write the track to `path` (.csv -> comma separated, anything else -> aligned
    text).  Creates missing directories.  storm: the storm's name -> written with a
    storm column, replacing only that storm's rows of a file that already holds
    several (its other storms are kept).  Returns the absolute path."""
    path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fmt = "csv" if path.lower().endswith(".csv") else "txt"
    others = None
    if storm is not None:
        storm = storm_name(storm)
        keep = _other_storms(path, storm)
        # this storm's own old rows only mark its place; drop all but the first marker
        seen, others = False, []
        for r in keep:
            if r.get(STORM_COL) == storm:
                if not seen:
                    others.append({STORM_COL: storm})
                seen = True
            else:
                others.append(r)
    text = to_text(run, fixes, opts, fmt, fields, storm, others)
    with open(path, "w") as f:
        f.write(text)
    return path
