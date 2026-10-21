"""Publication figures: the figure spec, the data behind each panel, and export.

The spec (a JSON-able dict) says what each panel shows and how it looks; figdraw.draw
turns it plus the panel arrays into a matplotlib figure.  Panels vary in time (one
field setup at several times) or in field (several fills at one time), as plan views
at fixed heights or vertical cross-sections, over the whole domain, a fixed box, or a
window centred on the tracked storm.  Other kinds of panels: time-height plots and
time series of reduced fields (the Series tab's recipes, spec["series"]), and
soundings (skew-T + hodograph, spec["soundings"]).  Panels can come from different runs (e.g.
tornadic vs non-tornadic): spec["runs"] lists the runs with a label and a storm track
each, and panels refer to them by index, with times in model seconds so they match
across runs.

Exporting writes the image and, optionally, a stand-alone script (figdraw's code +
the spec as a Python dict), the plotted arrays (.npz) and the spec (.json), so the
figure can be redrawn or restyled later without the viewer.
"""

import json
import os
import pprint
import time as _time

import numpy as np

from . import config, figdraw, render, series as ser, thermo, track as trk
from .run import FileBusy, MissingAtTime

DATA_KEYS = ("type", "field", "mode", "z", "spacing", "zspacing", "frame",  # -> data
             "style")
LINE_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "k"]
SOUNDING_VARS = ("th", "prs", "qv", "uinterp", "vinterp")


# ------------------------------------------------------------------ spec
def layer_defaults(kind, F, field=None, z=1.0):
    """A new layer of `kind` with sensible defaults for `field`."""
    if kind == "fill":
        d = F[field]
        lo, hi = d.vrange if d.vrange is not None else (0.0, 1.0)
        refl = field in ("dbz", "cref")
        return dict(type="fill", on=True, field=field, mode="height", z=z, units=d.units,
                    cmap=_refl_cmap() if refl else d.cmap, reverse=False,
                    white_first=False, vmin=0.0 if refl else lo, vmax=60.0 if refl else hi,
                    nlevels=0, style="mesh", mask_below=0.0 if refl else None,
                    extend="max" if refl else ("both" if d.diverging else "neither"))
    if kind == "contour":
        return dict(type="contour", on=True, field=field, mode="height", z=z,
                    levels="10, 20", color="k",
                    lw=0.75, neg_dashed=True, clabel=False, legend="")
    if kind == "shade":
        return dict(type="shade", on=True, field=field, mode="height", z=z, threshold=10.0,
                    above=True,
                    color="magenta", alpha=0.6, outline="", lw=1.0, legend="")
    if kind == "vectors":
        return dict(type="vectors", on=True, z=0.0, spacing=2.0, zspacing=0.5,
                    frame="ground", scale=250.0, width=0.002, color="k", key=0.0,
                    style="arrows", density=1.5, slw=0.8, arrowsize=1.0)
    if kind == "track":
        return dict(type="track", on=True, color="k", lw=1.0, ls="-", marker=True, legend="")
    if kind == "line":
        return dict(type="line", on=True, color="k", lw=2.0, labels="X, X′", legend="")
    raise ValueError(kind)


def _refl_cmap():
    """HomeyerRainbow when cmweather (or pyart) is available, else NWS reflectivity
    steps."""
    try:
        figdraw.colormap("HomeyerRainbow")
        return "HomeyerRainbow"
    except Exception:  # noqa: BLE001
        return "reflectivity"


def run_entry(run, track=None):
    """A spec["runs"] entry for `run`: its path, a label (the folder name) and a storm
    track ("viewer": the viewer's Track tab, a CSV / text file, or "": none; default:
    a storm_tracks file found next to the run, else none)."""
    if track is None:
        track = find_track(run.path) or ""
    return dict(path=run.path, label=os.path.basename(run.path.rstrip("/")), track=track)


def find_track(path):
    """A storm track file for the run in `path` (the track_dirs / track_patterns
    settings: by default storm_tracks/<parent>_<name>.csv or <name>.csv in the run's
    folder or a folder above it), or None."""
    return config.find_track(path)


def default_spec(run, F, t=0):
    """A 2 x 3 plan-view figure in time: reflectivity at 1 km with w contours at 3 km
    and near-surface winds, centred on the tracked storm."""
    fill = "dbz" if "dbz" in F else ("cref" if "cref" in F else next(iter(F.defs)))
    nt = len(run.times)
    layers = [layer_defaults("fill", F, fill, 1.0)]
    if "winterp" in F:
        layers.append(layer_defaults("contour", F, "winterp", 3.0))
    if "uinterp" in F:
        layers.append(dict(layer_defaults("vectors", F), on=False))
    times = [min(nt - 1, t + 5 * k) for k in range(6)]
    return dict(
        version=1, kind="plan", size=[8.0, 6.0], rows=2, cols=3, vary="time",
        times=times, time=t, panel_fills=[], layers=layers,
        times_s=[float(run.times[k]) for k in times], time_s=float(run.times[t]),
        runs=[run_entry(run, "viewer")], run=0, runs_as="rows", panels=[],
        domain=dict(mode="storm", half=12.5, box=None), coords="grid",
        xsec=dict(mode="storm", a=None, b=None, angle=0.0, half=10.0, offset=[0.0, 0.0],
                  ztop=6.0, dz=0.025),
        axes=dict(xlabel="x (km)", ylabel="y (km)", ticks=True, ticklabels="outer",
                  equal=True, minor=False, title_bold=True),
        letters=dict(on=True, fmt="{a}", loc="lower left", size=12, bold=True),
        time_label=dict(on=True, fmt="t = {min:g} min", loc="lower right", size=12,
                        bold=True, t0_min=0.0),
        run_label=dict(on=True, loc="upper left", size=12, bold=True),
        titles=[], suptitle="",
        colorbar=dict(mode="shared", orientation="horizontal", label="", shrink=0.7,
                      fraction=0.05, pad=0.02, ticks=""),
        legend=dict(panel=0, loc="upper right", frame=True),
        series=[], ts=dict(tmin=None, tmax=None, zmin=0.0, zmax=10.0, legend=True,
                           legend_loc="best", zero_line=False),
        soundings=[], skewt=dict(pmax=1000.0, pmin=100.0, tmin=-40.0, tmax=50.0, skew=35.0,
                                 parcel="ml", guides=True, barbs=True, hodo=True,
                                 hodo_max=40.0, hodo_top=9.0, lw=1.8, legend=False,
                                 legend_loc="upper left", params=True),
        contour_key=dict(on=False, layer=-1, label="w", x=0.01, y=0.01, size=0.1, fs=10.0,
                         r0=0.35, step=0.15, yoffset=0.06, frame=True),
        annotations=[],
        font=dict(family="sans-serif", size=10), background="white",
        spacing=dict(w_pad=0.04, h_pad=0.04, wspace=0.02, hspace=0.02),
        export=dict(format="png", dpi=250, tight=True),
    )


def npanels(spec):
    return figdraw.npanels(spec)


def panel_ref(spec, i):
    """(run index, model time in s) of panel i, or None for an empty grid cell.
    vary: "time" (one run, a time per panel), "field" (one run and time, a fill per
    panel), "grid" (runs x times: rows are runs when runs_as == "rows", else columns)
    or "custom" (spec["panels"]: a run and time per panel)."""
    vary, nr = spec["vary"], len(spec.get("runs") or [None])
    if vary == "time":
        ts = spec["times_s"]
        return (int(spec.get("run", 0)), float(ts[i])) if i < len(ts) else None
    if vary == "field":
        return int(spec.get("run", 0)), float(spec["time_s"])
    if vary == "grid":
        r, c = divmod(i, int(spec["cols"]))
        k, j = (r, c) if spec.get("runs_as", "rows") == "rows" else (c, r)
        ts = spec["times_s"]
        return (k, float(ts[j])) if k < nr and j < len(ts) else None
    pans = spec.get("panels", [])
    if i < len(pans) and int(pans[i]["run"]) < nr:
        return int(pans[i]["run"]), float(pans[i]["time_s"])
    return None


def tindex(run, time_s):
    """Output index of `run` at model time time_s (s), or None if it has none there."""
    k = int(np.argmin(np.abs(np.asarray(run.times) - time_s)))
    return k if abs(run.times[k] - time_s) <= 1.0 else None


def normalize(spec, run, track="viewer"):
    """Fill in what an older spec (cm1view figures before multi-run panels) lacks:
    times in seconds from the time indices of `run`, and `run` (with `track`) as the
    only run."""
    nt = len(run.times)
    if "times_s" not in spec:
        spec["times_s"] = [float(run.times[min(int(t), nt - 1)]) for t in spec["times"]]
    if "time_s" not in spec:
        spec["time_s"] = float(run.times[min(int(spec["time"]), nt - 1)])
    if not spec.get("runs"):
        spec["runs"] = [run_entry(run, track)]
    return spec


def storm_motion(run, fixes, t):
    """Ground-relative storm motion (u, v) for storm-relative fields at time t: the
    tracked motion where the track has a fix, else the domain motion (as the map)."""
    if fixes:
        m = trk.motion(run, fixes).get(t)
        if m is not None and np.all(np.isfinite(m)):
            return tuple(m)
    return (run.umove, run.vmove)


# ------------------------------------------------------------------ geometry
def section_ends(run, spec, t, center):
    """Grid-km ends (A, B) of the cross-section at time t (None if it needs a track
    position and there is none)."""
    xs = spec["xsec"]
    if xs["mode"] == "fixed":
        if not xs.get("a") or not xs.get("b"):
            return None
        return tuple(xs["a"]), tuple(xs["b"])
    if center is None:
        return None
    cx, cy = center[0] + xs["offset"][0], center[1] + xs["offset"][1]
    th = np.radians(float(xs["angle"]))  # 0: west -> east, 90: south -> north
    dx, dy = np.cos(th) * xs["half"], np.sin(th) * xs["half"]
    return (cx - dx, cy - dy), (cx + dx, cy + dy)


def plan_window(run, spec, center):
    """(x0, x1, y0, y1) grid km of a plan panel, or None."""
    dom = spec["domain"]
    if dom["mode"] == "full":
        dxk, dyk = run.dx / 2000.0, run.dy / 2000.0
        return run.xh[0] - dxk, run.xh[-1] + dxk, run.yh[0] - dyk, run.yh[-1] + dyk
    if dom["mode"] == "box":
        return tuple(dom["box"]) if dom.get("box") else None
    if center is None:
        return None
    h = float(dom["half"])
    return center[0] - h, center[0] + h, center[1] - h, center[1] + h


def data_key(spec, i, center, path=""):
    """Everything panel i's arrays depend on (style changes leave it unchanged)."""
    layers = figdraw.spec_layers(spec, i)
    lk = [{k: lay.get(k) for k in DATA_KEYS if k in lay} | {"on": lay.get("on", True)}
          for lay in layers]
    return json.dumps(dict(kind=spec["kind"], ref=panel_ref(spec, i), path=path,
                           dom=spec["domain"],
                           coords=spec["coords"], xsec=spec["xsec"] if spec["kind"] == "xsec"
                           or any(lay["type"] == "line" for lay in layers) else None,
                           layers=lk, center=center), sort_keys=True, default=float)


# ------------------------------------------------------------------ data
def extract(run, F, spec, i, center, fixes=None, storm=None, progress=None):
    """Arrays of panel i (dict for figdraw).  center: tracked storm (x, y) km at the
    panel time or None; fixes: {t: fix} for the track layer; storm: ground-relative
    storm motion (u, v) at this time for storm-relative fields and vectors."""
    ts = panel_ref(spec, i)[1]
    t = tindex(run, ts)
    if t is None:
        return dict(time_s=ts, missing=f"no output at {ts / 60:g} min in this run")
    out = dict(time_s=float(run.times[t]))
    bad = [lay["field"] for lay in figdraw.spec_layers(spec, i)
           if lay.get("on", True) and lay.get("field") and lay["field"] not in F]
    if bad:
        return dict(out, missing="this run has no " + ", ".join(bad))
    try:
        if spec["kind"] == "xsec":
            _extract_xsec(run, F, spec, i, t, center, storm, out, progress)
        else:
            _extract_plan(run, F, spec, i, t, center, fixes, storm, out)
    except (MissingAtTime, FileBusy) as e:
        out = dict(time_s=float(run.times[t]), missing=str(e))
    return out


def _origin(spec, center):
    if spec["coords"] == "storm" and center is not None:
        return center
    return (0.0, 0.0)


def _extract_plan(run, F, spec, i, t, center, fixes, storm, out):
    win = plan_window(run, spec, center)
    if win is None:
        out["missing"] = ("no track position at this time" if spec["domain"]["mode"] == "storm"
                          else "no box chosen")
        return
    x0, x1, y0, y1 = win
    ox, oy = _origin(spec, center)
    i0 = max(0, int(np.searchsorted(run.xh, x0)) - 1)
    i1 = min(run.ni, int(np.searchsorted(run.xh, x1)) + 1)
    j0 = max(0, int(np.searchsorted(run.yh, y0)) - 1)
    j1 = min(run.nj, int(np.searchsorted(run.yh, y1)) + 1)
    out["x"], out["y"] = run.xh[i0:i1] - ox, run.yh[j0:j1] - oy
    out["xlim"], out["ylim"] = (x0 - ox, x1 - ox), (y0 - oy, y1 - oy)
    for j, lay in enumerate(figdraw.spec_layers(spec, i)):
        if not lay.get("on", True):
            continue
        if lay["type"] in ("fill", "contour", "shade"):
            a = F.plane(lay["field"], t, lay.get("mode", "height"), float(lay["z"]),
                        storm=storm)
            out[f"L{j}"] = np.asarray(a[j0:j1, i0:i1], dtype=np.float32)
        elif lay["type"] == "vectors":
            u = F.plane("uinterp", t, "height", float(lay["z"]))[j0:j1, i0:i1]
            v = F.plane("vinterp", t, "height", float(lay["z"]))[j0:j1, i0:i1]
            u, v = _frame(run, u, v, lay["frame"], storm)
            if lay.get("style") == "streamlines":  # the winds on a (thinned) grid
                g = max(1, int(np.ceil(max(u.shape) / 300.0)))
                out[f"L{j}_gx"], out[f"L{j}_gy"] = out["x"][::g], out["y"][::g]
                out[f"L{j}_gu"] = np.asarray(u[::g, ::g], dtype=np.float32)
                out[f"L{j}_gv"] = np.asarray(v[::g, ::g], dtype=np.float32)
                continue
            st = max(1, int(round(float(lay["spacing"]) * 1000.0 / run.dx)))
            sl = (slice(st // 2, None, st), slice(st // 2, None, st))
            X, Y = np.meshgrid(out["x"], out["y"])
            out[f"L{j}_x"], out[f"L{j}_y"] = X[sl], Y[sl]
            out[f"L{j}_u"], out[f"L{j}_v"] = u[sl], v[sl]
        elif lay["type"] == "track" and fixes:
            ts = sorted(fixes)
            out["track_x"] = np.array([fixes[s]["x"] for s in ts]) - ox
            out["track_y"] = np.array([fixes[s]["y"] for s in ts]) - oy
            if t in fixes:
                out["now_x"], out["now_y"] = fixes[t]["x"] - ox, fixes[t]["y"] - oy
        elif lay["type"] == "line":
            ends = section_ends(run, spec, t, center)
            if ends is not None:
                (xa, ya), (xb, yb) = ends
                out["line"] = np.array([xa - ox, ya - oy, xb - ox, yb - oy])


def _frame(run, u, v, frame, storm):
    """Grid-relative winds -> the chosen frame."""
    if frame == "ground":
        return u + run.umove, v + run.vmove
    if frame == "storm":
        su, sv = storm if storm is not None else (run.umove, run.vmove)
        return u + run.umove - su, v + run.vmove - sv
    return u, v


def _extract_xsec(run, F, spec, i, t, center, storm, out, progress):
    ends = section_ends(run, spec, t, center)
    if ends is None:
        out["missing"] = ("no track position at this time" if spec["xsec"]["mode"] == "storm"
                          else "no section line: click A and B on the map first")
        return
    xs = spec["xsec"]
    layers = figdraw.spec_layers(spec, i)
    names = []
    for lay in layers:
        if not lay.get("on", True):
            continue
        if lay["type"] in ("fill", "contour", "shade"):
            names += F.native_deps(lay["field"])
        elif lay["type"] == "vectors":
            names += ["uinterp", "vinterp", "winterp"]
    run.load_volumes([n for n in names if n in run.vars], t, progress=progress)
    s, fi, fj, (ex, ey) = render.section_coords(run, *ends)
    ztop, dz = float(xs["ztop"]), float(xs.get("dz", 0.025))
    zq = np.arange(0.0, ztop + 0.5 * dz, dz)
    s0 = s[-1] / 2.0 if xs["mode"] == "storm" else 0.0  # storm sections: 0 at the storm
    out["x"], out["y"] = s - s0, zq
    out["xlim"], out["ylim"] = (s[0] - s0, s[-1] - s0), (0.0, ztop)
    for j, lay in enumerate(layers):
        if not lay.get("on", True):
            continue
        if lay["type"] in ("fill", "contour", "shade"):
            out[f"L{j}"] = render.sample_section(run, F.volume(lay["field"], t, storm),
                                                 fi, fj, zq)
        elif lay["type"] == "vectors":
            u = render.sample_section(run, run.volume("uinterp", t), fi, fj, zq)
            v = render.sample_section(run, run.volume("vinterp", t), fi, fj, zq)
            w = render.sample_section(run, run.volume("winterp", t), fi, fj, zq)
            u, v = _frame(run, u, v, lay["frame"], storm)
            if lay.get("style") == "streamlines":
                gs, gz = max(1, int(np.ceil(s.size / 300.0))), max(1, int(np.ceil(zq.size / 200.0)))
                out[f"L{j}_gx"], out[f"L{j}_gy"] = out["x"][::gs], zq[::gz]
                out[f"L{j}_gu"] = np.asarray((u * ex + v * ey)[::gz, ::gs], dtype=np.float32)
                out[f"L{j}_gv"] = np.asarray(w[::gz, ::gs], dtype=np.float32)
                continue
            si = max(1, int(round(float(lay["spacing"]) / max(s[1] - s[0], 1e-6))))
            zi = max(1, int(round(float(lay.get("zspacing", 0.5)) / dz)))
            sl = (slice(zi // 2, None, zi), slice(si // 2, None, si))
            S, Z = np.meshgrid(out["x"], zq)
            out[f"L{j}_x"], out[f"L{j}_y"] = S[sl], Z[sl]
            out[f"L{j}_u"], out[f"L{j}_v"] = (u * ex + v * ey)[sl], w[sl]


# ------------------------------------------------------------------ series panels
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
    ext = "max" if red == "max" else ("min" if red == "min" else "both")
    units = d.units if d is not None else ""
    return dict(recipe=recipe, label=label or (ser.describe(recipe, d.label) if d else
                                               recipe["field"]),
                op="", cmap=cmap, reverse=False, white_first=white, vmin=float(lo),
                vmax=float(hi), nlevels=0, style="mesh", mask_below=None, extend=ext,
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


# ------------------------------------------------------------------ sounding panels
def sounding_defaults(run_index=0, time_s=0.0, where=None, n=0, label=""):
    """A spec["soundings"] entry: where = dict(kind 'trk' (offset x, y km from the
    tracked storm), 'pt' (x, y km on the model grid) or 'mean' (domain mean), avg =
    width (km) of the box averaged around the point)."""
    return dict(run=int(run_index), time_s=float(time_s), panel=0, label=label,
                where=dict(where or dict(kind="trk", x=0.0, y=0.0, avg=0.0)),
                color=LINE_COLORS[n % len(LINE_COLORS)])


def sounding_column(run, entry, fixes, progress=None):
    """thermo.analyze result of a sounding entry, or a string (why there is none)."""
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
                          c["vinterp"] + run.vmove, domain=(run.umove, run.vmove))


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


# ------------------------------------------------------------------ export
def flatten(data):
    """{panel: {name: array}} -> {'p<panel>__<name>': array} for .npz files."""
    out = {}
    for i, d in data.items():
        for k, v in d.items():
            out[f"p{i}__{k}"] = np.asarray(v)
    return out


def unflatten(npz):
    data = {}
    for key in npz.files if hasattr(npz, "files") else npz:
        p, name = key.split("__", 1)
        v = npz[key]
        data.setdefault(int(p[1:]), {})[name] = v.item() if v.ndim == 0 else v
    return data


def save_image(spec, data, path, dpi=None):
    path = _abs(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig = figdraw.draw(spec, data)
    ex = spec.get("export", {})
    fig.savefig(path, dpi=float(dpi or ex.get("dpi", 250)),
                bbox_inches="tight" if ex.get("tight", True) else None,
                facecolor=fig.get_facecolor())
    return path


def bundle_paths(spec, base):
    """{image, script, data, spec} for a bundle saved as `base`: the image and script
    side by side, the arrays and spec in _src/ next to them."""
    base = _abs(base)
    root, ext = os.path.splitext(base)
    if ext.lower() in (".png", ".pdf", ".svg", ".eps", ".tif", ".tiff", ".jpg"):
        base = root
    fmt = spec.get("export", {}).get("format", "png")
    src, name = os.path.join(os.path.dirname(base), "_src"), os.path.basename(base)
    return dict(image=f"{base}.{fmt}", script=f"{base}.py",
                data=os.path.join(src, f"{name}_data.npz"),
                spec=os.path.join(src, f"{name}_spec.json"))


def save_bundle(spec, data, base, run=None, note=""):
    """Image + script side by side, data + spec in _src/ (see bundle_paths).
    Returns the paths."""
    out = bundle_paths(spec, base)
    os.makedirs(os.path.dirname(out["data"]), exist_ok=True)
    out["image"] = save_image(spec, data, out["image"])
    np.savez_compressed(out["data"], **flatten(data))
    with open(out["spec"], "w") as f:
        json.dump(spec, f, indent=1, default=float)
    with open(out["script"], "w") as f:
        f.write(script(spec, "_src/" + os.path.basename(out["data"]),
                       os.path.basename(out["image"]), run, note))
    return out


def script(spec, npz_name, out_name, run=None, note=""):
    """A stand-alone script that redraws the figure from the saved arrays."""
    import inspect
    src = inspect.getsource(figdraw)
    head = [
        f'"""Figure made with cm1view on {_time.strftime("%Y-%m-%d %H:%M")}.',
        "",
        *(["runs:"] + [f"  {r['label']}: {r['path']}" for r in spec["runs"]]
          if len(spec.get("runs") or []) > 1 else
          [f"run: {run.path}" if run is not None else ""]),
        note,
        "Redraw:  python this_script.py   (needs numpy and matplotlib; cmweather or pyart",
        "for their colormaps).  Change SPEC below to restyle (colours, ranges, labels, size, ...);",
        f"the plotted arrays are in {npz_name}.",
        '"""',
    ]
    body = [
        "",
        "# ----------------------------------------------------------------- figure spec",
        "SPEC = " + pprint.pformat(_plain(spec), width=92, sort_dicts=False),
        "",
        "",
        "# ----------------------------------------------------------------- drawing code",
        _strip_doc(src),
        "",
        "",
        "def load_data(path):",
        "    \"\"\"The arrays saved with the figure: {panel: {name: array}}.\"\"\"",
        "    data = {}",
        "    with np.load(path, allow_pickle=False) as z:",
        "        for key in z.files:",
        "            p, name = key.split('__', 1)",
        "            v = z[key]",
        "            data.setdefault(int(p[1:]), {})[name] = v.item() if v.ndim == 0 else v",
        "    return data",
        "",
        "",
        'if __name__ == "__main__":',
        "    import os",
        "    here = os.path.dirname(os.path.abspath(__file__))",
        f"    data = load_data(os.path.join(here, *{npz_name!r}.split('/')))",
        "    fig = draw(SPEC, data)",
        f"    out = os.path.join(here, {out_name!r})",
        "    ex = SPEC.get('export', {})",
        "    fig.savefig(out, dpi=ex.get('dpi', 250),",
        "                bbox_inches='tight' if ex.get('tight', True) else None,",
        "                facecolor=fig.get_facecolor())",
        "    print('saved', out)",
        "",
    ]
    return "\n".join([h for h in head if h is not None]) + "\n" + "\n".join(body)


def _strip_doc(src):
    """figdraw's source without its module docstring (the script has its own)."""
    if src.startswith('"""'):
        end = src.index('"""', 3)
        return src[end + 3:].lstrip("\n")
    return src


def _plain(o):
    """JSON round trip: numpy scalars and tuples become plain Python."""
    return json.loads(json.dumps(o, default=float))


def load_spec(path):
    with open(_abs(path)) as f:
        spec = json.load(f)
    if spec.get("version") != 1:
        raise ValueError("not a cm1view figure spec (version 1)")
    for r in spec.get("runs") or []:
        if not os.path.isdir(r["path"]):
            raise ValueError(f"run folder {r['path']} not found")
    return spec


def _abs(path):
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
