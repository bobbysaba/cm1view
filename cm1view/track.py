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
    ks = np.flatnonzero((run.z >= UH_LAYER[0]) & (run.z <= UH_LAYER[1]))
    uh = np.zeros((run.nj, run.ni), np.float32)
    wmax = np.full((run.nj, run.ni), -np.inf, np.float32)
    zmax = np.full((run.nj, run.ni), -np.inf, np.float32)
    for k in ks:
        if cancelled and cancelled():
            return None, None
        dz = float(run.zf[k + 1] - run.zf[k]) * 1000.0
        w = run.read_level("winterp", t, int(k))
        zeta = run.read_level("zvort", t, int(k))
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
    fixes = dict(existing or {})
    lo, hi = opts.get("t_from", 0), opts.get("t_to", len(run.times) - 1)
    sgn = -1.0 if sense(opts) == "min" else 1.0

    def get(t, x, y, snap=True, whole=False):
        f, ex = metric_field(run, t, opts["metric"], opts["zkm"], cancelled,
                             opts.get("field"), fields)
        if f is None:
            return None
        return locate(run, f, ex, x, y, opts, snap, whole)

    first = get(t0, x0, y0, opts.get("snap", True), whole=x0 is None)
    if first is None:
        return fixes
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
            fx = get(tn, px, py)
            done += 1
            if fx is None or not _beyond(fx["value"], opts.get("stop"), sgn):
                break
            fx["source"] = "auto"
            fixes[tn] = fx
            if on_fix:
                on_fix(dict(fixes))
            t = tn
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


def load(run, path):
    """Fixes {t: fix} from a CSV / whitespace table with x_km, y_km or loc_x, loc_y
    (grid-relative) or x_ground_km, y_ground_km, and time_s, time_hms, time_index or
    time (minutes; seconds if the values are too large for minutes).  Lines starting
    with '#' are comments.  Times are matched to the nearest output time; a column
    named value or like uh_* / zeta_* / w_* / prspert_* / max_* / min_* becomes the
    fix value."""
    import pandas as pd

    path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    with open(path) as f:
        first = next((ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")), "")
    sep = "," if "," in first else r"\s+"
    df = pd.read_csv(path, comment="#", sep=sep, engine="python")
    df.columns = [c.strip() for c in df.columns]
    times = np.asarray(run.times)
    if "time_s" in df:
        tsec = df["time_s"].astype(float).to_numpy()
    elif "time_hms" in df:
        def hms(v):
            h, m, s = (float(p) for p in str(v).split(":"))
            return h * 3600 + m * 60 + s
        tsec = np.array([hms(v) for v in df["time_hms"]])
    elif "time_index" in df:
        tsec = times[np.clip(df["time_index"].astype(int).to_numpy(), 0, len(times) - 1)]
    elif "time" in df:  # e.g. storm_tracks/*.csv: model minutes
        tv = df["time"].astype(float).to_numpy()
        tsec = tv * 60.0 if np.nanmax(tv) <= times[-1] / 60.0 + 1.0 else tv
    else:
        raise ValueError("needs a time_s, time_hms, time_index or time (min) column")
    if {"x_km", "y_km"} <= set(df.columns):
        x, y = df["x_km"].astype(float).to_numpy(), df["y_km"].astype(float).to_numpy()
    elif {"loc_x", "loc_y"} <= set(df.columns):
        x, y = df["loc_x"].astype(float).to_numpy(), df["loc_y"].astype(float).to_numpy()
    elif {"x_ground_km", "y_ground_km"} <= set(df.columns):
        x = df["x_ground_km"].astype(float).to_numpy() - run.umove * tsec / 1000.0
        y = df["y_ground_km"].astype(float).to_numpy() - run.vmove * tsec / 1000.0
    else:
        raise ValueError("needs x_km, y_km or loc_x, loc_y (grid), or x_ground_km, "
                         "y_ground_km columns")
    vcol = next((c for c in df.columns if c == "value"
                 or c.split("_")[0] in ("uh", "zeta", "w", "prspert", "max", "min")
                 and c not in
                 ("w_max_2_5km", "zeta_max_2_5km")), None)
    keep = [c for c in ("w_max_2_5km", "zeta_max_2_5km") if c in df]
    fixes = {}
    for n in range(len(df)):
        t = int(np.argmin(np.abs(times - tsec[n])))
        if abs(times[t] - tsec[n]) > 1.0 and "time_index" not in df:
            continue  # not an output time of this run
        fx = dict(x=float(x[n]), y=float(y[n]),
                  value=float(df[vcol].iloc[n]) if vcol else float("nan"))
        for c in keep:
            fx[c] = float(df[c].iloc[n])
        fx["source"] = str(df["source"].iloc[n]) if "source" in df else "loaded"
        fixes[t] = fx
    return fixes


def motion(run, fixes):
    """Ground-relative motion (m/s) at every fix from centred differences of the
    ground-relative track (grid positions + grid translation)."""
    ts = sorted(fixes)
    if len(ts) < 2:
        return {t: (np.nan, np.nan) for t in ts}
    tsec = np.array([run.times[t] for t in ts])
    xg = np.array([fixes[t]["x"] * 1000.0 + run.umove * run.times[t] for t in ts])
    yg = np.array([fixes[t]["y"] * 1000.0 + run.vmove * run.times[t] for t in ts])
    u, v = np.gradient(xg, tsec), np.gradient(yg, tsec)
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


def to_text(run, fixes, opts, fmt="csv", fields=None):
    """The track as CSV (fmt='csv') or a whitespace-aligned table ('txt'), with a
    '#'-commented header describing the run, method and columns."""
    rs = rows(run, fixes)
    m, sn = opts["metric"], sense(opts)
    lab, units = label(opts, fields)
    vname = column(opts)
    stop = opts.get("stop")
    nt = len(run.times)
    lo, hi = opts.get("t_from", 0), opts.get("t_to", nt - 1)
    cols = list(rs[0].keys()) if rs else ["time_index", "time_s", "x_km", "y_km", "value"]
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
        "u/v_motion_ms: ground-relative storm motion (centred differences)",
        f"{vname}: raw {sn} within the smoothing box around the fix",
        "source: auto = tracked, manual = placed by hand, loaded = read from a file",
    ]
    names = [vname if c == "value" else c for c in cols]

    def cell(c, v):
        if isinstance(v, str):
            return v
        if c in _FMT:
            return _FMT[c].format(v) if np.isfinite(v) else "nan"
        return f"{v:.6g}"

    body = [[cell(c, r[c]) for c in cols] for r in rs]
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


def save(run, fixes, opts, path, fields=None):
    """Write the track to `path` (.csv -> comma separated, anything else -> aligned
    text).  Creates missing directories.  Returns the absolute path."""
    path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fmt = "csv" if path.lower().endswith(".csv") else "txt"
    with open(path, "w") as f:
        f.write(to_text(run, fixes, opts, fmt, fields))
    return path
