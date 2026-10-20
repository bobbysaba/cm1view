"""Mesocyclone tracking through output times, and export of the track to CSV / text."""

import io
import os
import time as _time

import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter

METRICS = {"Updraft: w at height": "w", "2–5 km updraft helicity": "uh",
           "Vertical vorticity at height": "zeta"}
METRIC_LABEL = {"uh": "2–5 km UH", "zeta": "ζ", "w": "w"}
METRIC_UNITS = {"uh": "m²/s²", "zeta": "1/s", "w": "m/s"}
# default "lost" threshold: tracking stops when the metric falls below this
METRIC_STOP = {"uh": 50.0, "zeta": 0.01, "w": 5.0}
UH_LAYER = (2.0, 5.0)  # km AGL


def available(run):
    return run.has("winterp")


def metrics(run):
    """The METRICS this run has the fields for."""
    ok = {"w": run.has("winterp"), "uh": run.has("winterp") and run.has("zvort"),
          "zeta": run.has("zvort")}
    return {k: v for k, v in METRICS.items() if ok[v]}


def _smooth(a, smooth, dxk, kernel):
    """Box average of width `smooth` km, or Gaussian with sigma = `smooth` km."""
    if kernel == "gauss":
        sig = smooth / dxk
        return gaussian_filter(a, sig, mode="nearest") if sig > 0.3 else a
    ns = max(1, int(round(smooth / dxk)) | 1)
    return uniform_filter(a, size=ns, mode="nearest") if ns > 1 else a


def metric_field(run, t, metric, zkm=1.0, cancelled=None):
    """2D metric on the scalar grid at time t, plus extra 2D fields to report.
    UH = sum over the 2-5 km layer of w * zeta * dz (instantaneous)."""
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


def locate(run, field, extras, x, y, radius, smooth, snap=True, nearest=True,
           kernel="box", whole=False):
    """Fix near (x, y) km: the maximum of the (smoothed) field within `radius` km.
    nearest: weight the field by a Gaussian of the distance from (x, y) (sigma =
    radius / 2) first, so a nearby core wins over a slightly stronger one farther
    away (keeps the track from hopping between neighbouring cores).
    whole: take the maximum over the whole domain instead (x, y and radius unused).
    kernel: 'box' (width `smooth` km) or 'gauss' (sigma `smooth` km).
    Returns dict(x, y, value, **extras) with values = raw maxima within `smooth` km
    of the fix (or None if the search disc is off the domain)."""
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
    sub = field[j0:j1, i0:i1]
    ok = np.isfinite(sub)
    if not ok.any():
        return None
    sm = _smooth(np.where(ok, sub, np.min(sub[ok])), smooth, dxk, kernel)
    sm = np.where(ok, sm, -np.inf)
    if whole:
        jm, im = np.unravel_index(int(np.argmax(sm)), sm.shape)
        jf, if_ = j0 + jm, i0 + im
    elif snap:
        jj, ii = np.mgrid[j0:j1, i0:i1]
        d2 = (run.xh[ii] - x) ** 2 + (run.yh[jj] - y) ** 2
        if nearest:
            wt = np.exp(-0.5 * d2 / (0.5 * radius) ** 2)
            sm = np.where(sm > 0, sm * wt, sm)
        sm = np.where(d2 <= radius ** 2, sm, -np.inf)
        jm, im = np.unravel_index(int(np.argmax(sm)), sm.shape)
        jf, if_ = j0 + jm, i0 + im
    else:
        jf, if_ = j, i
    h = max(1, int(round(smooth / dxk)) // 2)
    win = (slice(max(0, jf - h), jf + h + 1), slice(max(0, if_ - h), if_ + h + 1))
    out = dict(x=float(run.xh[if_]), y=float(run.yh[jf]), value=float(np.nanmax(field[win])))
    for k, a in extras.items():
        out[k] = float(np.max(a[win]))
    return out


def track(run, t0, x0, y0, opts, direction="both", existing=None, on_fix=None,
          cancelled=None, progress=None):
    """Follow the feature at (x0, y0) from time t0 (x0 None: start from the domain-wide
    maximum).  opts: metric, zkm, radius, smooth, kernel, stop, snap, nearest, whole.
    `existing` fixes ({t: fix}) on the side not being tracked are kept.  on_fix(fixes)
    is called after every new fix.  Returns {t: fix}."""
    fixes = dict(existing or {})
    nt = len(run.times)

    def get(t, x, y, snap=True, whole=False):
        f, ex = metric_field(run, t, opts["metric"], opts["zkm"], cancelled)
        if f is None:
            return None
        return locate(run, f, ex, x, y, opts["radius"], opts["smooth"], snap,
                      opts.get("nearest", True), opts.get("kernel", "box"),
                      whole or opts.get("whole", False))

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
    total = sum((nt - 1 - t0) if s > 0 else t0 for s in steps)
    done = 0
    for s in steps:
        t = t0
        while 0 <= t + s < nt:
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
            if fx is None or fx["value"] < opts["stop"]:
                break
            fx["source"] = "auto"
            fixes[tn] = fx
            if on_fix:
                on_fix(dict(fixes))
            t = tn
    return fixes


def place(run, t, x, y, opts):
    """A hand-placed fix at (x, y) km at time t: snapped to the nearby maximum when
    opts['snap'], and carrying the tracked value there either way."""
    f, ex = metric_field(run, t, opts["metric"], opts["zkm"])
    fx = locate(run, f, ex, x, y, opts["radius"], opts["smooth"], opts.get("snap", False),
                opts.get("nearest", True), opts.get("kernel", "box"))
    if fx is None:
        return None
    if not opts.get("snap", False):
        fx["x"], fx["y"] = float(x), float(y)
    fx["source"] = "manual"
    return fx


def load(run, path):
    """Fixes {t: fix} from a CSV / whitespace table with x_km, y_km (grid-relative)
    or x_ground_km, y_ground_km, and time_s, time_hms or time_index.  Lines starting
    with '#' are comments.  Times are matched to the nearest output time; a column
    named value or like uh_* / zeta_* / w_* becomes the fix value."""
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
    else:
        raise ValueError("needs a time_s, time_hms or time_index column")
    if {"x_km", "y_km"} <= set(df.columns):
        x, y = df["x_km"].astype(float).to_numpy(), df["y_km"].astype(float).to_numpy()
    elif {"x_ground_km", "y_ground_km"} <= set(df.columns):
        x = df["x_ground_km"].astype(float).to_numpy() - run.umove * tsec / 1000.0
        y = df["y_ground_km"].astype(float).to_numpy() - run.vmove * tsec / 1000.0
    else:
        raise ValueError("needs x_km, y_km (grid) or x_ground_km, y_ground_km columns")
    vcol = next((c for c in df.columns if c == "value"
                 or c.split("_")[0] in ("uh", "zeta", "w") and c not in
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


def to_text(run, fixes, opts, fmt="csv"):
    """The track as CSV (fmt='csv') or a whitespace-aligned table ('txt'), with a
    '#'-commented header describing the run, method and columns."""
    rs = rows(run, fixes)
    m = opts["metric"]
    vname = {"uh": "uh_2_5km", "zeta": f"zeta_{opts['zkm']:g}km",
             "w": f"w_{opts['zkm']:g}km"}[m]
    cols = list(rs[0].keys()) if rs else ["time_index", "time_s", "x_km", "y_km", "value"]
    head = [
        "cm1view mesocyclone track",
        f"created: {_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"run: {run.path}",
        f"tracked field: {METRIC_LABEL[m]}"
        + ("" if m == "uh" else f" at {opts['zkm']:g} km AGL") + f" ({METRIC_UNITS[m]})"
        + f"  -> column '{vname}'",
        ("search: whole domain at every time" if opts.get("whole") else
         f"search radius {opts['radius']:g} km, prefer nearest core: "
         f"{opts.get('nearest', True)}")
        + f", smoothing {opts['smooth']:g} km "
        + ("(Gaussian sigma)" if opts.get("kernel") == "gauss" else "(box width)")
        + f", stop below {opts['stop']:g}",
        f"grid translation (umove, vmove) = ({run.umove:g}, {run.vmove:g}) m/s",
        "x_km, y_km: position on the (translating) model grid; "
        "x/y_ground_km: ground-relative = grid + (umove, vmove) * time_s",
        "u/v_motion_ms: ground-relative storm motion (centred differences)",
        f"{vname}: raw max within the smoothing box around the fix",
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


def save(run, fixes, opts, path):
    """Write the track to `path` (.csv -> comma separated, anything else -> aligned
    text).  Creates missing directories.  Returns the absolute path."""
    path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fmt = "csv" if path.lower().endswith(".csv") else "txt"
    with open(path, "w") as f:
        f.write(to_text(run, fixes, opts, fmt))
    return path
