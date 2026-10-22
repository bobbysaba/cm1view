"""Time-series, time-height, sounding and distribution panels."""

import numpy as np

from ...core import dist, series as ser, thermo, track as trk
from .. import draw as figdraw
from .base import npanels, tindex, storm_motion

LINE_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "k"]
SOUNDING_VARS = ("th", "prs", "qv", "uinterp", "vinterp")


def series_defaults(F, recipe, n=0, label=""):
    """A spec["series"] entry for a Series recipe: colours and range for time-height
    panels, colour and line for time series (both from the field)."""
    d = F[recipe["field"]] if recipe["field"] in F else None
    lo, hi = d.vrange if d is not None and d.vrange is not None else (0.0, 1.0)
    cmap, white = (d.cmap if d is not None else "viridis"), False
    red = recipe["reduce"]
    if d is not None and d.diverging and red == "max":  # e.g. max w: one sign
        lo, cmap = 0.0, "viridis"
    elif d is not None and d.diverging and red == "min":
        hi, cmap = 0.0, "viridis_r"
    if recipe["field"] in ("winterp", "w") and red == "max":  # updraft speed
        cmap, white, lo, hi = _w_cmap(), True, 0.0, max(hi, 40.0)
    units = d.units if d is not None else ""
    return dict(recipe=recipe, label=label or (ser.describe(recipe, d.label) if d else
                                               recipe["field"]),
                op="", cmap=cmap, reverse=False, white_first=white, vmin=float(lo),
                vmax=float(hi), nlevels=0, style="mesh", mask_below=None, extend="auto",
                units=units, base_units=units, color=LINE_COLORS[n % len(LINE_COLORS)],
                lw=1.5, marker="", panel=0, axis="auto", ylabel="", runs=None)


def _w_cmap():
    try:
        figdraw.colormap("ChaseSpectral")
        return "ChaseSpectral"
    except Exception:  # noqa: BLE001
        return "viridis"


def op_units(units, op):
    """Units after a derivative of the series (d/dz per m, d/dt per s)."""
    ms = units in ("m/s", "m s-1", "m s$^{-1}$")
    if op == "ddz":
        return "s$^{-1}$" if ms else (f"{units} m$^{{-1}}$" if units else "m$^{-1}$")
    if op == "ddt":
        return "m s$^{-2}$" if ms else (f"{units} s$^{{-1}}$" if units else "s$^{-1}$")
    return units


def series_pairs(spec):
    """(run index, series index) pairs whose results the panels need."""
    out = []
    nr = len(spec.get("runs") or [])
    if spec["kind"] == "th":
        for i in range(npanels(spec)):
            ref = figdraw.series_ref(spec, i)
            if ref is not None and ref not in out:
                out.append(ref)
    else:
        for e, ent in enumerate(spec.get("series", [])):
            for k in _entry_runs(ent, nr):
                out.append((k, e))
    return out


def _entry_runs(ent, nr):
    runs = ent.get("runs")
    return list(range(nr)) if runs is None else [int(k) for k in runs if int(k) < nr]


def series_arrays(run, ds, entry, t0_min=0.0):
    """(t in min from t0_min, values (nt,), z (nz,) or None, per-level values (nt, nz)
    or None) of a series dataset, NaN where not computed, with the entry's derivative
    ('ddz': d/dz of the per-level values, 'ddt': d/dt) applied."""
    ok = ds["computed"].values == 1
    tm = np.asarray(run.times, dtype=np.float64)
    v = np.where(ok, ds["value"].values, np.nan)
    P = z = None
    if "profile" in ds:
        P = np.where(ok[:, None], ds["profile"].values, np.nan)
        z = np.asarray(ds["z"].values, dtype=np.float64)
    op = entry.get("op", "")
    if op == "ddz":
        if P is None or P.shape[1] < 2:
            return tm / 60.0 - t0_min, None, None, None
        P = np.gradient(P, z * 1000.0, axis=1)
        v = np.full_like(v, np.nan)
    elif op == "ddt" and tm.size > 1:
        v = np.gradient(v, tm)
        P = None if P is None else np.gradient(P, tm, axis=0)
    return tm / 60.0 - t0_min, v, z, P


def th_panel(run, ds, entry, spec):
    """Arrays of a time-height panel."""
    t0 = float(spec.get("time_label", {}).get("t0_min", 0.0))
    t, v, z, P = series_arrays(run, ds, entry, t0)
    if P is None:
        return dict(missing="time–height panels need a layer series (Vertical: Layer)"
                    if "profile" not in ds else "d/dz needs at least two levels")
    have = np.flatnonzero(np.isfinite(P).any(axis=1))
    if not have.size:
        return dict(missing="not computed yet")
    ts = spec.get("ts", {})
    half = 0.5 * (t[1] - t[0]) if t.size > 1 else 1.0
    x0 = float(ts["tmin"]) if ts.get("tmin") not in (None, "") else t[have[0]] - half
    x1 = float(ts["tmax"]) if ts.get("tmax") not in (None, "") else t[have[-1]] + half
    z0 = float(ts["zmin"]) if ts.get("zmin") not in (None, "") else float(z[0])
    z1 = float(ts["zmax"]) if ts.get("zmax") not in (None, "") else float(z[-1])
    return dict(x=t, y=z, L0=np.asarray(P.T, dtype=np.float32), xlim=(x0, x1),
                ylim=(z0, min(z1, float(z[-1]) + 1e-6) if z1 > z0 else (z0, z0 + 1.0)))


def line_panel(spec, i, get):
    """Arrays of time-series panel i.  get(run index, series index) -> (run, dataset)
    or None (not available)."""
    ents, runs = spec.get("series", []), spec.get("runs") or []
    t0 = float(spec.get("time_label", {}).get("t0_min", 0.0))
    ts = spec.get("ts", {})
    lines = [(e, k) for e, ent in enumerate(ents) if int(ent.get("panel", 0)) == i
             for k in _entry_runs(ent, len(runs))]
    out, n, lo, hi, why = {}, 0, np.inf, -np.inf, ""
    one_e = len({e for e, _ in lines}) == 1
    one_r = len({k for _, k in lines}) == 1
    for e, k in lines:
        got = get(k, e)
        if got is None:
            why = "not computed yet"
            continue
        run, ds = got
        t, v, _, _ = series_arrays(run, ds, ents[e], t0)
        if v is None or not np.isfinite(v).any():
            why = why or ("d/dz applies to time–height panels" if ents[e].get("op") == "ddz"
                          else "not computed yet")
            continue
        fin = np.flatnonzero(np.isfinite(v))
        sl = slice(fin[0], fin[-1] + 1)
        rl, el = runs[k].get("label", ""), ents[e].get("label", "")
        out[f"S{n}_t"], out[f"S{n}_v"] = t[sl], v[sl]
        out[f"S{n}_e"], out[f"S{n}_r"] = e, k
        out[f"S{n}_label"] = rl if one_e and not one_r else (
            el if one_r else f"{el} · {rl}")
        lo, hi = min(lo, t[fin[0]]), max(hi, t[fin[-1]])
        n += 1
    if not n:
        return dict(missing=why or "no series in this panel")
    out["nlines"] = n
    x0 = float(ts["tmin"]) if ts.get("tmin") not in (None, "") else lo
    x1 = float(ts["tmax"]) if ts.get("tmax") not in (None, "") else hi
    out["xlim"] = (x0, x1 if x1 > x0 else x0 + 1.0)
    return out


def share_time_range(spec, data):
    """Time-height / time-series panels without a set time range all show the range
    of every panel together (as sharex), so they line up and inner labels can go."""
    ts = spec.get("ts", {})
    if spec["kind"] not in ("th", "line"):
        return data
    lims = [d["xlim"] for d in data.values() if "xlim" in d and not d.get("missing")]
    if not lims:
        return data
    lo, hi = min(a for a, _ in lims), max(b for _, b in lims)
    for d in data.values():
        if "xlim" in d and not d.get("missing"):
            a, b = d["xlim"]
            d["xlim"] = (a if ts.get("tmin") not in (None, "") else lo,
                         b if ts.get("tmax") not in (None, "") else hi)
    return data


def sounding_defaults(run_index=0, time_s=0.0, where=None, n=0, label=""):
    """A spec["soundings"] entry: where = dict(kind 'trk' (offset x, y km from the
    tracked storm), 'pt' (x, y km on the model grid) or 'mean' (domain mean), avg =
    width (km) of the box averaged around the point)."""
    return dict(run=int(run_index), time_s=float(time_s), panel=0, label=label,
                where=dict(where or dict(kind="trk", x=0.0, y=0.0, avg=0.0)),
                color="")  # ("": automatic, figdraw.sounding_colors)


def storm_choice(skewt):
    """(storm, custom) for thermo.analyze of a spec's skewt options: the storm motion
    of the SRH (rm, lm, mean, or custom (u, v) ground-relative m/s)."""
    st = skewt.get("storm", "rm")
    if st not in ("rm", "lm", "mean", "custom"):
        st = "rm"
    return st, (float(skewt.get("storm_u") or 0.0), float(skewt.get("storm_v") or 0.0))


def sounding_column(run, entry, fixes, progress=None, storm=("rm", (0.0, 0.0))):
    """thermo.analyze result of a sounding entry, or a string (why there is none).
    storm: (storm, custom) of storm_choice."""
    t = tindex(run, float(entry["time_s"]))
    if t is None:
        return f"no output at {float(entry['time_s']) / 60:g} min in this run"
    w = entry["where"]
    kind = w.get("kind", "trk")
    if kind == "mean":
        c = run.mean_profiles(SOUNDING_VARS, t, progress=progress)
    else:
        x, y = float(w.get("x", 0.0)), float(w.get("y", 0.0))
        if kind == "trk":
            pos = trk.position(fixes, t) if fixes else None
            if pos is None:
                return "no track position at this time"
            x, y = pos[0] + x, pos[1] + y
        i, j = run.ij(x, y)
        h = int(round(float(w.get("avg", 0.0)) * 500.0 / run.dx))
        i0, i1 = max(0, i - h), min(run.ni, i + h + 1)
        j0, j1 = max(0, j - h), min(run.nj, j + h + 1)
        c = {}
        for v in SOUNDING_VARS:
            vol = run.cached(v, t)
            a = vol[:, j0:j1, i0:i1] if vol is not None else run.read_box(v, t, i0, i1, j0, j1)
            c[v] = a.mean(axis=(1, 2), dtype=np.float64)
    return thermo.analyze(run.z * 1000.0, c["prs"], c["th"], c["qv"], c["uinterp"] + run.umove,
                          c["vinterp"] + run.vmove, storm=storm[0], custom=storm[1],
                          domain=(run.umove, run.vmove))


def _param(r, key):
    """A value of figdraw.SND_PARAMS from a thermo.analyze result (NaN if none)."""
    try:
        if key.endswith(("cape", "cin")):
            return float(r[key[:2]][key[2:]])
        if key == "mllcl":
            return float(r["ml"]["lcl_z"])
        if key in ("srh1", "srh3", "esrh"):
            return float(r["kin"][key])
        if key == "shear06":
            return float(np.hypot(*r["kin"]["shear06"]))
        if key in ("stp_eff", "scp"):
            return float(r["comp"][key])
    except (KeyError, TypeError, ValueError):
        pass
    return float("nan")


def sounding_label(entry, run_label, run, multi):
    w = entry["where"]
    when = f"{float(entry['time_s']) / 60:g} min"
    kind = w.get("kind", "trk")
    if kind == "mean":
        where = "domain mean"
    elif kind == "trk":
        dx, dy = float(w.get("x", 0)), float(w.get("y", 0))
        where = "storm" if not (dx or dy) else f"storm {dx:+g}, {dy:+g} km"
    else:
        where = f"({float(w['x']):.1f}, {float(w['y']):.1f}) km"
    return " ".join(p for p in ((run_label if multi else ""), where, when) if p)


def sounding_panel(spec, i, get, auto_label=None):
    """Arrays of sounding panel i.  get(sounding index) -> thermo result or a string
    (why there is none); auto_label(sounding index) -> legend text when it has no
    label of its own."""
    ents = spec.get("soundings", [])
    parcel = spec.get("skewt", {}).get("parcel", "ml")
    out, n, why, times = {}, 0, "", set()
    for e, ent in enumerate(ents):
        if int(ent.get("panel", 0)) != i:
            continue
        r = get(e)
        if isinstance(r, str) or r is None:
            why = r or why
            continue
        pr = r["prof"]
        out[f"N{n}_p"] = pr["p"] / 100.0
        out[f"N{n}_T"], out[f"N{n}_Td"] = pr["T"] - 273.15, pr["Td"] - 273.15
        if parcel in ("sb", "ml", "mu"):
            out[f"N{n}_Tp"] = r[parcel]["T"] - 273.15
        out[f"N{n}_u"], out[f"N{n}_v"], out[f"N{n}_z"] = pr["u"], pr["v"], pr["z"] / 1000.0
        out[f"N{n}_e"] = e
        kin = r.get("kin", {})
        for k, name in (("rm", "rm"), ("lm", "lm"), ("mean06", "mean"), ("storm", "storm")):
            if k in kin:
                out[f"N{n}_{name}"] = np.asarray(kin[k], dtype=float)
        for k in ("srh1", "srh3"):
            if k in kin:
                out[f"N{n}_{k}"] = float(kin[k])
        out[f"N{n}_par"] = np.array([_param(r, k) for k, _, _ in figdraw.SND_PARAMS])
        lab = ent.get("label") or (auto_label(e) if auto_label else "")
        if spec.get("skewt", {}).get("params", True) and parcel in ("sb", "ml", "mu"):
            lab += (f" ({parcel.upper()}CAPE {r[parcel]['cape']:.0f}, "
                    f"CIN {r[parcel]['cin']:.0f} J kg$^{{-1}}$)")
        out[f"N{n}_label"] = lab.strip()
        times.add(round(float(ent["time_s"]), 1))
        n += 1
    if not n:
        return dict(missing=why or "no sounding in this panel")
    out["nsnd"] = n
    if len(times) == 1:
        out["time_s"] = times.pop()
    return out


def dist_defaults(recipe, run_index=0, time_s=0.0, n=0, label=""):
    """A spec["dists"] entry: a dist recipe (dist.normalize) at a run and time."""
    return dict(run=int(run_index), time_s=float(time_s), panel=0, label=label,
                recipe=dist.normalize(recipe), color="")  # ("": figdraw.dist_colors)


def dist_value_label(F, field):
    """Value axis label of a field: its label and units."""
    if field not in F:
        return field
    d = F[field]
    return f"{d.label} ({d.units})" if d.units else d.label


def dist_label(entry, run_label, F, multi, times):
    """Legend text of a distribution: what (dist.describe), and the run and time when
    the figure has several runs or the panel's distributions several times."""
    r = entry["recipe"]
    d = F[r["field"]] if r["field"] in F else None
    lab = dist.describe(r, d.label if d else "", d.units if d else "")
    when = f"{float(entry['time_s']) / 60:g} min" if times else ""
    return " · ".join([x for x in ((run_label if multi else ""), when) if x] + [lab])


def dist_compute(run, F, entry, fixes):
    """dist.summarize result of a distribution entry, or a string (why there is
    none)."""
    t = tindex(run, float(entry["time_s"]))
    if t is None:
        return f"no output at {float(entry['time_s']) / 60:g} min in this run"
    r = entry["recipe"]
    if r["field"] not in F:
        return f"this run has no {r['field']}"
    center = None
    if r["region"] == "track":
        center = ser.track_centers(fixes or {}, len(run.times)).get(t)
        if center is None:
            return "no track position at this time"
    storm = storm_motion(run, fixes, t) if F[r["field"]].storm else None
    try:
        st = dist.compute(run, F, r, t, storm, center)
    except ValueError as e:
        return str(e)
    return st if st["n"] else "no values in the region (or the value limits)"


def dist_panel(spec, i, get, auto_label=None, value_label=None):
    """Arrays of distribution panel i.  get(entry index) -> summary or a string (why
    there is none); auto_label(entry index) -> legend text when it has no label of its
    own; value_label(entry index) -> its value axis label."""
    out, n, why, times = {}, 0, "", set()
    for e, ent in enumerate(spec.get("dists", [])):
        if int(ent.get("panel", 0)) != i:
            continue
        r = get(e)
        if isinstance(r, str) or r is None:
            why = r or why
            continue
        out.update(figdraw.dist_arrays(r, n))
        out[f"D{n}_e"] = e
        out[f"D{n}_label"] = (ent.get("label") or (auto_label(e) if auto_label else "")).strip()
        out[f"D{n}_xl"] = value_label(e) if value_label else ""
        times.add(round(float(ent["time_s"]), 1))
        n += 1
    if not n:
        return dict(missing=why or "no distribution in this panel")
    out["ndist"] = n
    if len(times) == 1:
        out["time_s"] = times.pop()
    return out
