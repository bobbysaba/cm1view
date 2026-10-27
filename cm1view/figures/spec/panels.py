"""Time-series, time-height, sounding, distribution, profile, joint distribution and
azimuthal mean panels."""

import numpy as np

from ...core import azim, dist, joint, series as ser, thermo, track as trk
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
                lw=1.5, marker="", panel=0, axis="auto", ylabel="", runs=None, ens="",
                ens_mid="mean", ens_members="faint", ens_alpha=0.25)


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
    # heights: the cells' edges (drawn "nearest"), within the recipe's layer, so a
    # 0–10 km series shows 0 to 10 km and not the top level's centre (e.g. 9.9)
    dz = np.diff(z) if z.size > 1 else np.array([1.0])
    lo, hi = float(z[0] - 0.5 * dz[0]), float(z[-1] + 0.5 * dz[-1])
    rec = entry.get("recipe") or {}
    if rec.get("z0") not in (None, ""):
        lo = max(lo, float(rec["z0"]))
    if rec.get("z1") not in (None, ""):
        hi = min(hi, float(rec["z1"])) if float(rec["z1"]) > lo else hi
    z0 = float(ts["zmin"]) if ts.get("zmin") not in (None, "") else lo
    z1 = float(ts["zmax"]) if ts.get("zmax") not in (None, "") else hi
    return dict(x=t, y=z, L0=np.asarray(P.T, dtype=np.float32), xlim=(x0, x1),
                ylim=(z0, min(z1, hi)) if z1 > z0 else (z0, z0 + 1.0))


ENS_BANDS = ("minmax", "p10p90", "p25p75", "sd")


def ensemble_band(members, how="minmax", mid="mean"):
    """(t, centre, low, high) of an ensemble of series members [(t, v)]: each member
    interpolated onto every member's times (blank outside its own), and at each time
    with two members or more the centre ("mean", "median"; "": none, NaN) and band:
    "minmax", "p10p90", "p25p75" (percentiles) or "sd" (mean -/+ one standard
    deviation).  None with fewer than two members."""
    if len(members) < 2:
        return None
    T = np.unique(np.round(np.concatenate([np.asarray(t, dtype=float)
                                           for t, _ in members]), 6))
    V = np.full((len(members), T.size), np.nan)
    for m, (t, v) in enumerate(members):
        t, v = np.asarray(t, dtype=float), np.asarray(v, dtype=float)
        ok = np.isfinite(t) & np.isfinite(v)
        if ok.any():
            V[m] = np.interp(T, t[ok], v[ok], left=np.nan, right=np.nan)
    have = np.isfinite(V).sum(axis=0) >= 2
    if not have.any():
        return None
    T, V = T[have], V[:, have]
    if how == "sd":
        c, sd = np.nanmean(V, axis=0), np.nanstd(V, axis=0)
        lo, hi = c - sd, c + sd
    elif how in ("p10p90", "p25p75"):
        q = (10, 90) if how == "p10p90" else (25, 75)
        lo, hi = np.nanpercentile(V, q[0], axis=0), np.nanpercentile(V, q[1], axis=0)
    else:
        lo, hi = np.nanmin(V, axis=0), np.nanmax(V, axis=0)
    c = (np.nanmedian(V, axis=0) if mid == "median" else np.nanmean(V, axis=0)
         if mid == "mean" else np.full(T.size, np.nan))
    return T, c, lo, hi


def ensemble_label(ent, n):
    """Legend text of an ensemble band: the entry's label, its centre and band, the
    number of members."""
    band = {"minmax": "min–max", "p10p90": "10–90%", "p25p75": "25–75%",
            "sd": "±1 sd"}.get(ent.get("ens"), "")
    mid = ent.get("ens_mid", "mean")
    what = f"{mid}, {band}" if mid else band
    return f"{ent.get('label', '')} ({what}, {n} runs)".strip()


def line_panel(spec, i, get):
    """Arrays of time-series panel i.  get(run index, series index) -> (run, dataset)
    or None (not available).  A series with an ensemble band (its "ens") and two runs
    or more: its runs' lines as members (S<n>_mem 1; none when its ens_members is
    "hidden") and one line more of the ensemble (S<n>_ens: the number of members,
    S<n>_r -1, S<n>_v the centre, S<n>_lo / S<n>_hi the band)."""
    ents, runs = spec.get("series", []), spec.get("runs") or []
    t0 = float(spec.get("time_label", {}).get("t0_min", 0.0))
    ts = spec.get("ts", {})
    lines = [(e, k) for e, ent in enumerate(ents) if int(ent.get("panel", 0)) == i
             for k in _entry_runs(ent, len(runs))]
    out, n, lo, hi, why = {}, 0, np.inf, -np.inf, ""
    one_e = len({e for e, _ in lines}) == 1
    one_r = len({k for _, k in lines}) == 1
    members = {}  # (entry index: [(t, v)] of its runs, with an ensemble band)
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
        lo, hi = min(lo, t[fin[0]]), max(hi, t[fin[-1]])
        ens = ents[e].get("ens") in ENS_BANDS and len(_entry_runs(ents[e], len(runs))) > 1
        if ens:
            members.setdefault(e, []).append((t[sl], v[sl]))
            if ents[e].get("ens_members", "faint") == "hidden":
                continue
        rl, el = runs[k].get("label", ""), ents[e].get("label", "")
        out[f"S{n}_t"], out[f"S{n}_v"] = t[sl], v[sl]
        out[f"S{n}_e"], out[f"S{n}_r"] = e, k
        out[f"S{n}_label"] = rl if one_e and not one_r else (
            el if one_r else f"{el} · {rl}")
        if ens:
            out[f"S{n}_mem"] = 1
        n += 1
    for e, ms in members.items():
        b = ensemble_band(ms, ents[e]["ens"], ents[e].get("ens_mid", "mean"))
        if b is None:  # (one run: its line alone, as without a band)
            continue
        out[f"S{n}_t"], out[f"S{n}_v"], out[f"S{n}_lo"], out[f"S{n}_hi"] = b
        out[f"S{n}_e"], out[f"S{n}_r"], out[f"S{n}_ens"] = e, -1, len(ms)
        out[f"S{n}_label"] = ensemble_label(ents[e], len(ms))
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
        if key.endswith(("lcl", "lfc")):
            return float(r[key[:2]][f"{key[2:]}_z"])
        if key in ("srh250", "srh500", "srh1", "srh3", "esrh"):
            return float(r["kin"][key])
        if key.startswith("shear"):
            return float(np.hypot(*r["kin"][key]))
        if key in ("stp_eff", "stp_fixed", "scp"):
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
        # (no CAPE/CIN in the label of a hodograph alone: it has no skew-T options to hide it)
        if (spec.get("skewt", {}).get("params", True) and parcel in ("sb", "ml", "mu")
                and figdraw.sounding_layout(spec.get("skewt", {})) != "hodo"):
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


def profile_defaults(recipe, run_index=0, time_s=0.0, n=0, label=""):
    """A spec["profiles"] entry: a layer series recipe (ser.normalize) at a run and time
    (time_s1: the end of a time window it is averaged over; None: one time)."""
    r = dict(recipe, vmode="layer")
    r.setdefault("z0", 0.0)
    r.setdefault("z1", 10.0)
    return dict(run=int(run_index), time_s=float(time_s), time_s1=None, panel=0,
                label=label, recipe=ser.normalize(r), color="", ls="",  # ("": automatic)
                lw=1.5)


def profile_times(run, entry):
    """Output indices of a profile entry: the one at time_s, or every output from
    time_s to time_s1 (a time window)."""
    t0, t1 = float(entry["time_s"]), entry.get("time_s1")
    if t1 is None or float(t1) <= t0:
        t = tindex(run, t0)
        return [] if t is None else [t]
    tm = np.asarray(run.times, dtype=np.float64)
    return [int(t) for t in np.flatnonzero((tm >= t0 - 1.0) & (tm <= float(t1) + 1.0))]


def profile_values(ds, ts):
    """(z km, the profile averaged over the computed times among ts, how many) of a
    layer series dataset."""
    ok = [t for t in ts if ds["computed"].values[t] == 1]
    z = np.asarray(ds["z"].values, dtype=np.float64)
    if not ok:
        return z, np.full(z.size, np.nan), 0
    P = np.asarray(ds["profile"].values[ok], dtype=np.float64)
    with np.errstate(invalid="ignore"):
        v = np.nanmean(P, axis=0) if len(ok) > 1 else P[0]
    return z, v, len(ok)


def profile_when(entry):
    """'90 min', or '60–90 min mean' for a time window."""
    t0, t1 = float(entry["time_s"]) / 60.0, entry.get("time_s1")
    if t1 is None or float(t1) <= float(entry["time_s"]):
        return f"{t0:g} min"
    return f"{t0:g}–{float(t1) / 60.0:g} min mean"


def profile_label(entry, run_label, F, multi, times):
    """Legend text of a profile: what (ser.describe, without its layer), and the run
    and time when the figure has several runs or the panel's profiles several times
    (a time window always says so)."""
    r = entry["recipe"]
    d = F[r["field"]] if r["field"] in F else None
    lab = ser.describe(dict(r, vmode="2d"), d.label if d else "")
    window = entry.get("time_s1") is not None and \
        float(entry["time_s1"]) > float(entry["time_s"])
    when = profile_when(entry) if times or window else ""
    return " · ".join([x for x in ((run_label if multi else ""), when) if x] + [lab])


def profile_panel(spec, i, get, auto_label=None, value_label=None):
    """Arrays of profile panel i.  get(entry index) -> (z, values) or a string (why
    there is none); auto_label(entry index) -> legend text when it has no label of its
    own; value_label(entry index) -> its value axis label."""
    out, n, why, times = {}, 0, "", set()
    for e, ent in enumerate(spec.get("profiles", [])):
        if int(ent.get("panel", 0)) != i:
            continue
        r = get(e)
        if isinstance(r, str) or r is None:
            why = r or why
            continue
        z, v = r
        out[f"P{n}_z"] = np.asarray(z, dtype=np.float32)
        out[f"P{n}_v"] = np.asarray(v, dtype=np.float32)
        out[f"P{n}_e"] = e
        out[f"P{n}_r"] = int(ent.get("run", 0))
        out[f"P{n}_label"] = (ent.get("label") or (auto_label(e) if auto_label else "")).strip()
        out[f"P{n}_xl"] = value_label(e) if value_label else ""
        times.add((round(float(ent["time_s"]), 1), ent.get("time_s1")))
        n += 1
    if not n:
        return dict(missing=why or "no profile in this panel")
    out["nprof"] = n
    if len(times) == 1:
        t0, t1 = times.pop()
        if t1 is None or float(t1) <= t0:
            out["time_s"] = t0
    return out


def joint_defaults(recipe, run_index=0, time_s=0.0, n=0, label=""):
    """A spec["joints"] entry: a joint recipe (joint.normalize) at a run and time
    (time_s1: the end of a time window whose pairs are all taken; None: one time)."""
    return dict(run=int(run_index), time_s=float(time_s), time_s1=None, panel=0,
                label=label, recipe=joint.normalize(recipe), color="")  # ("": automatic)


def joint_label(entry, run_label, F, multi, times):
    """Legend text of a joint distribution: what (joint.describe), and the run and
    time when the figure has several runs or the panel's several times (a time window
    always says so)."""
    r = entry["recipe"]
    lab = joint.describe(r, *(F[k].label if k in F else "" for k in (r["field"],
                                                                     r["yfield"])))
    window = entry.get("time_s1") is not None and \
        float(entry["time_s1"]) > float(entry["time_s"])
    when = profile_when(entry).replace(" mean", "") if times or window else ""
    return " · ".join([x for x in ((run_label if multi else ""), when) if x] + [lab])


def joint_compute(run, F, entry, fixes):
    """joint.summarize result of a joint distribution entry (every pair of its time or
    time window), or a string (why there is none)."""
    ts = profile_times(run, entry)
    if not ts:
        return f"no output at {float(entry['time_s']) / 60:g} min in this run"
    r = entry["recipe"]
    for k in (r["field"], r["yfield"]):
        if k not in F:
            return f"this run has no {k}"
    centers = None
    if r["region"] == "track":
        centers = ser.track_centers(fixes or {}, len(run.times))
        if any(centers.get(t) is None for t in ts):
            return "no track position at this time"
    storm = {t: storm_motion(run, fixes, t) for t in ts} \
        if F[r["field"]].storm or F[r["yfield"]].storm else None
    try:
        st = joint.compute(run, F, r, ts, storm, centers)
    except ValueError as e:
        return str(e)
    return st if st["n"] else "no values in the region (or the value limits)"


def joint_panel(spec, i, get, auto_label=None, axis_labels=None):
    """Arrays of joint distribution panel i.  get(entry index) -> summary or a string
    (why there is none); auto_label(entry index) -> legend text when it has no label of
    its own; axis_labels(entry index) -> its (x, y) axis labels."""
    out, n, why, times = {}, 0, "", set()
    for e, ent in enumerate(spec.get("joints", [])):
        if int(ent.get("panel", 0)) != i:
            continue
        r = get(e)
        if isinstance(r, str) or r is None:
            why = r or why
            continue
        out.update(figdraw.joint_arrays(r, n))
        out[f"J{n}_e"] = e
        out[f"J{n}_r"] = int(ent.get("run", 0))
        out[f"J{n}_label"] = (ent.get("label") or (auto_label(e) if auto_label else "")).strip()
        out[f"J{n}_xl"], out[f"J{n}_yl"] = axis_labels(e) if axis_labels else ("", "")
        times.add((round(float(ent["time_s"]), 1), ent.get("time_s1")))
        n += 1
    if not n:
        return dict(missing=why or "no joint distribution in this panel")
    out["njoint"] = n
    if len(times) == 1:
        t0, t1 = times.pop()
        if t1 is None or float(t1) <= t0:
            out["time_s"] = t0
    return out


def azim_defaults(recipe, run_index=0, time_s=0.0, n=0, label=""):
    """A spec["azims"] entry: an azimuthal mean recipe (azim.normalize) at a run and
    time (time_s1: the end of a time window it is a composite of; None: one time).  The
    panel's first is shaded, the others drawn as contour lines (color, lw, levels)."""
    return dict(run=int(run_index), time_s=float(time_s), time_s1=None, panel=0,
                label=label, recipe=azim.normalize(recipe), color="", lw=1.0,
                levels="")  # ("": automatic)


def azim_label(entry, run_label, F, multi, times):
    """Legend text of an azimuthal mean: what (azim.describe), and the run and time
    when the figure has several runs or the panel's several times (a time window
    always says so)."""
    r = entry["recipe"]
    lab = azim.describe(r, F[r["field"]].label if r["field"] in F else "")
    window = entry.get("time_s1") is not None and \
        float(entry["time_s1"]) > float(entry["time_s"])
    when = profile_when(entry) if times or window else ""
    return " · ".join([x for x in ((run_label if multi else ""), when) if x] + [lab])


def azim_compute(run, F, entry, fixes):
    """azim.compute result of an azimuthal mean entry (its time, or a composite of its
    time window), or a string (why there is none).  Azimuth 0 follows the tracked
    motion at each time (else the domain motion; north when that is nil)."""
    ts = profile_times(run, entry)
    if not ts:
        return f"no output at {float(entry['time_s']) / 60:g} min in this run"
    r = entry["recipe"]
    if r["field"] not in F:
        return f"this run has no {r['field']}"
    if F[r["field"]].ndim == 2:
        return "an azimuthal mean needs a 3D field"
    if r["center"] == "track":
        cs = ser.track_centers(fixes or {}, len(run.times))
        if any(cs.get(t) is None for t in ts):
            return "no track position at this time"
        ox, oy = r["offset"]
        centers = {t: (cs[t][0] + ox, cs[t][1] + oy) for t in ts}
    else:
        centers = {t: tuple(r["point"]) for t in ts}
    motion = {t: storm_motion(run, fixes, t) for t in ts}
    refs = {t: azim.bearing(*motion[t]) if r["ref"] == "motion" else 0.0 for t in ts}
    try:
        res = azim.compute(run, F, r, ts, centers, refs,
                           motion if F[r["field"]].storm else None)
    except ValueError as e:
        return str(e)
    return res if int(res["n"].sum()) else "no values within the radius and sector"


def azim_panel(spec, i, get, auto_label=None, value_label=None, field_look=None):
    """Arrays of azimuthal mean panel i.  get(entry index) -> azim.compute result or a
    string (why there is none); auto_label(entry index) -> legend text when it has no
    label of its own; value_label(entry index) -> its colorbar label;
    field_look(entry index) -> (colormap name, diverging) of its field."""
    out, n, why, times = {}, 0, "", set()
    for e, ent in enumerate(spec.get("azims", [])):
        if int(ent.get("panel", 0)) != i:
            continue
        r = get(e)
        if isinstance(r, str) or r is None:
            why = r or why
            continue
        out[f"A{n}_x"] = np.asarray(r["r"], dtype=np.float32)
        out[f"A{n}_z"] = np.asarray(r["z"], dtype=np.float32)
        out[f"A{n}_v"] = np.asarray(r["v"], dtype=np.float32)
        out[f"A{n}_e"] = e
        out[f"A{n}_r"] = int(ent.get("run", 0))
        out[f"A{n}_label"] = (ent.get("label") or (auto_label(e) if auto_label else "")).strip()
        out[f"A{n}_cl"] = value_label(e) if value_label else ""
        cm, div = field_look(e) if field_look else ("viridis", False)
        out[f"A{n}_cm"], out[f"A{n}_div"] = cm, int(bool(div))
        times.add((round(float(ent["time_s"]), 1), ent.get("time_s1")))
        n += 1
    if not n:
        return dict(missing=why or "no azimuthal mean in this panel")
    out["nazim"] = n
    if len(times) == 1:
        t0, t1 = times.pop()
        if t1 is None or float(t1) <= t0:
            out["time_s"] = t0
    return out
