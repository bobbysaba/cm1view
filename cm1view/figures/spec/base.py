"""The figure spec: defaults, panels and layer groups, times and animation."""

import copy
import json
import os
import warnings

import numpy as np

from ... import config
from ...core import track as trk
from .. import draw as figdraw
from .sections import panel_section, section_defaults, to_cards, upgrade_sections

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
                    extend="auto")  # (colorbar ends where the data pass vmin / vmax)
    if kind == "contour":
        return dict(type="contour", on=True, field=field, mode="height", z=z,
                    levels="10, 20", color="k",
                    lw=0.75, neg_dashed=True, clabel=False, legend="")
    if kind == "shade":
        return dict(type="shade", on=True, field=field, mode="height", z=z, threshold=10.0,
                    above=True,
                    color="magenta", alpha=0.6, outline="", lw=1.0, legend="", hatch="",
                    hatch_lw=0.6)
    if kind == "vectors":
        return dict(type="vectors", on=True, vector="wind", z=0.0, spacing=2.0, zspacing=0.5,
                    frame="ground", scale=250.0, width=0.002, color="k", key=0.0,
                    style="arrows", density=1.5, slw=0.8, arrowsize=1.0, barb_len=5.5,
                    barb_units="kt")
    if kind == "track":  # (in its run's colour, run_color)
        return dict(type="track", on=True, color="k", run_color=True, lw=1.0, ls="-",
                    marker=True, legend="")
    if kind == "line":
        return dict(type="line", on=True, color="k", lw=2.0, labels="A, A′", which="all",
                    legend="")
    if kind == "sector":  # (as an azimuthal mean's: azimuths clockwise from the motion)
        return dict(type="sector", on=True, color="k", lw=1.5, ls="-", az0=0.0, az1=360.0,
                    rmax=20.0, ref="motion", center="track", offx=0.0, offy=0.0, cx=0.0,
                    cy=0.0, legend="")
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


def spread_times(nt, t, n, step=5):
    """Up to n different output indices from t, every `step` outputs (closer together
    when the run ends sooner)."""
    step = max(1, min(int(step), (nt - 1 - t) // max(1, n - 1)))
    return [k for k in (t + step * j for j in range(n)) if k < nt]


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
    times = spread_times(nt, t, 6)
    rows, cols = (1, len(times)) if len(times) <= 3 else (2, (len(times) + 1) // 2)
    return dict(
        version=1, kind="plan", size=[8.0, 6.0 if rows > 1 else 3.2], size_auto=True,
        rows=rows, cols=cols, vary="time", grid=dict(rows="none", cols="times", runs=[]),
        times=times, time=t, panel_fills=[], panel_z=[1.0, 3.0, 6.0], panel_zmode="height",
        layers=layers,
        times_s=[float(run.times[k]) for k in times], time_s=float(run.times[t]),
        runs=[run_entry(run, "viewer")], run=0, runs_as="rows", panels=[],
        domain=dict(mode="storm", half=12.5, box=None), coords="grid",
        xsec=dict(ztop=6.0, dz=0.025, coords="storm"),
        sections=[section_defaults()],
        axes=dict(xlabel="x (km)", ylabel="y (km)", ticks=True, ticklabels="outer",
                  equal=True, minor=False, title_bold=True),
        letters=dict(on=True, fmt="{a}", loc="lower left", size=12, bold=True),
        time_label=dict(on=True, fmt="t = {min:g} min", loc="lower right", size=12,
                        bold=True, t0_min=0.0),
        run_label=dict(on=True, loc="upper left", size=12, bold=True, run_color=True),
        z_label=dict(on=False, fmt="", loc="upper right", size=12, bold=True),
        titles=[], suptitle="",
        colorbar=dict(mode="shared", orientation="horizontal", label="", shrink=0.7,
                      fraction=0.05, pad=0.02, ticks=""),
        legend=dict(where="panel", panel=0, panels=[], loc="upper right", anchor=None,
                    ncol=1, frame=True, title="", own=True),
        series=[], ts=dict(tmin=None, tmax=None, zmin=0.0, zmax=10.0, legend=True,
                           legend_loc="best", legend_ncol=1, legend_frame=False,
                           zero_line=False, mark="", mark_legend=False, mark_edited=True),
        extremes=dict(on=False, layer=-1, what="both", marker=True, loc="upper center",
                      box=True),
        soundings=[], skewt=dict(pmax=1000.0, pmin=100.0, tmin=-40.0, tmax=50.0, skew=35.0,
                                 parcel="ml", guides=True, barbs=True, layout="inset",
                                 hodo_max=40.0, hodo_top=9.0, lw=1.8, legend=False,
                                 legend_loc="upper left", legend_ncol=1,
                                 legend_frame=True, params=True, hodo_rm=True,
                                 hodo_lm=True, hodo_mean=True, hodo_labels=True,
                                 hodo_heights="1, 3, 6, 9, 12", hodo_key=True, srh="", table=[],
                                 storm="rm", storm_u=0.0, storm_v=0.0, hodo_storm=True,
                                 inset_loc="auto", inset_size=0.37, inset_x=0.62,
                                 inset_y=0.6, hodo_center="origin", hodo_cu=0.0,
                                 hodo_cv=0.0),
        dists=[], dist=dict(plot="hist", norm="count", bins=50, width=None, xmin=None,
                            xmax=None, ymin=None, ymax=None, logy=False, hstyle="stepfilled",
                            alpha=0.35, lw=1.5, cum="below", whis="tukey", means=True,
                            horizontal=False, legend=True, legend_loc="best", legend_ncol=1,
                            legend_frame=False, stats=[],
                            stats_at="legend", stats_loc="upper right", bar_labels="",
                            zero_line=False),
        profiles=[], prof=dict(xmin=None, xmax=None, zmin=None, zmax=None, zero_line=False,
                               legend=True, legend_loc="best", legend_ncol=1,
                               legend_frame=False, mark_edited=True),
        joints=[], joint=dict(plot="hist", norm="count", bins=60, log=True, cmap="viridis",
                              reverse=False, colorbar=True, ms=2.0, alpha=0.5, lw=1.2,
                              contours=False, pcts="50, 90", contour_labels=True, fit=False,
                              one_one=False, zero_line=False, xmin=None, xmax=None,
                              ymin=None, ymax=None, stats=["n", "r"], stats_loc="upper left",
                              legend=True, legend_loc="best", legend_ncol=1,
                              legend_frame=False),
        azims=[], azim=dict(plot="mesh", cmap="", reverse=False, nlevels=15, vmin=None,
                            vmax=None, cbar_label="", colorbar=True, clabels=True, rmin=None,
                            rmax=None, zmin=None, zmax=None, legend=True, legend_loc="best",
                            legend_ncol=1, legend_frame=False),
        contour_key=dict(on=False, layer=-1, label="w", x=0.01, y=0.01, size=0.1, fs=10.0,
                         r0=0.35, step=0.15, yoffset=0.06, frame=True),
        annotations=[], code=dict(on=False, text=""),
        font=dict(family="sans-serif", size=10), background="white",
        spacing=dict(w_pad=0.04, h_pad=0.04, wspace=0.02, hspace=0.02),
        export=dict(format="png", dpi=250, tight=True),
    )


def npanels(spec):
    return figdraw.npanels(spec)


def panel_ref(spec, i):
    """(run index, model time in s) of panel i, or None for an empty grid cell
    (figdraw.panel_ref)."""
    return figdraw.panel_ref(spec, i)


def layer_groups(spec, i):
    """{(run index, time s): [layer indices]} of the layers of plan or section panel i
    drawn from another run or time than the panel's (their own "run" / "time_s")."""
    ref = panel_ref(spec, i)
    if ref is None or spec.get("kind") not in ("plan", "xsec"):
        return {}
    out = {}
    for j, lay in enumerate(figdraw.spec_layers(spec, i)):
        if not lay.get("on", True):
            continue
        k, ts = lay.get("run"), lay.get("time_s")
        g = (ref[0] if k is None else int(k), ref[1] if ts is None else float(ts))
        if g != ref and g[0] < len(spec.get("runs") or [None]):
            out.setdefault(g, []).append(j)
    return out


def group_spec(spec, i, ref, keep):
    """A spec of one panel: panel i at (run index, time s) ref with its layers `keep`
    (indices) and the others off, to read the layers of another run or time."""
    lays = [dict(lay, panels=[], on=lay.get("on", True) and j in keep)
            for j, lay in enumerate(figdraw.spec_layers(spec, i))]
    edits = {"0": {"section": panel_section(spec, i)[0]}}  # (the panel's cross-section)
    out = dict(spec, vary="custom", grid=None, rows=1, cols=1, layers=lays, edits=edits,
               titles=[],
               panel_fills=[], panels=[dict(run=int(ref[0]), time_s=float(ref[1]))])
    if figdraw.xsec_cards(spec) is not None:  # (a figure of cards: the panel's, at ref)
        out.update(edits={}, sections=[dict(panel_section(spec, i)[1], run=int(ref[0]),
                                            time_s=float(ref[1]), panel=0)])
    return out


def merge_group(d, dd, js, layers):
    """Panel arrays d with the arrays of its layers js read at another run or time (dd),
    each with its own coordinates (L<j>_cx, L<j>_cy)."""
    d = dict(d)
    if dd.get("missing"):
        return d
    for j in js:
        for key, v in dd.items():
            if key == f"L{j}" or key.startswith(f"L{j}_"):
                d[key] = v
        if f"L{j}" in dd:
            d[f"L{j}_cx"], d[f"L{j}_cy"] = dd["x"], dd["y"]
        t = layers[j]["type"]
        keys = ("track_x", "track_y", "now_x", "now_y") if t == "track" else \
            ("lines",) if t == "line" else ("sector",) if t == "sector" else ()
        for key in keys:
            if key in dd:
                d[key] = dd[key]
    return d


def minus_ref(spec, i, lay):
    """(run index, time s) that fill layer `lay` of panel i subtracts: its "minus"
    {run, time_s}, each None for the layer's own (itself the panel's when unset)."""
    ref, m = panel_ref(spec, i), lay.get("minus") or {}
    k = ref[0] if lay.get("run") is None else int(lay["run"])
    ts = ref[1] if lay.get("time_s") is None else float(lay["time_s"])
    return (k if m.get("run") is None else int(m["run"]),
            ts if m.get("time_s") is None else float(m["time_s"]))


def subtract(d, dd, j, grid="ask"):
    """Panel arrays d with layer j minus the same layer read at another run or time
    (dd): a difference.  When the two grids differ, grid "interp" interpolates dd onto
    layer j's grid (blank outside it); "refuse" and "ask" leave the panel blank with a
    note (ask: the user picks one in the layer's Difference settings)."""
    if d.get("missing") or f"L{j}" not in d:
        return d
    if dd.get("missing"):
        return dict(d, missing="difference: " + dd["missing"])
    if f"L{j}" not in dd:
        return d
    a, b = d[f"L{j}"], dd[f"L{j}"]
    ax, ay = d.get(f"L{j}_cx", d["x"]), d.get(f"L{j}_cy", d["y"])
    bx, by = dd["x"], dd["y"]
    if not (a.shape == b.shape and _same(ax, bx) and _same(ay, by)):
        if grid != "interp":
            return dict(d, missing="difference not drawn: the two grids differ" + (
                "" if grid == "refuse" else " (choose Interpolate or Refuse under the "
                                            "layer's Difference)"))
        b = regrid(b, bx, by, ax, ay)
    out = dict(d)
    out[f"L{j}"] = np.asarray(a - b, dtype=np.float32)
    return out


ENS_STATS = ("mean", "median", "sd", "min", "max", "range", "prob")


def ens_refs(spec, i, lay):
    """[(run index, time s)] that fill layer `lay` of panel i is an ensemble of: its
    "ens" runs (None: every run of the figure) at the layer's time (itself the
    panel's when unset)."""
    ref, e = panel_ref(spec, i), lay.get("ens") or {}
    ts = ref[1] if lay.get("time_s") is None else float(lay["time_s"])
    nr = len(spec.get("runs") or [])
    ks = range(nr) if e.get("runs") is None else [int(k) for k in e["runs"] if int(k) < nr]
    return [(k, ts) for k in dict.fromkeys(ks)]


def ensemble(d, dds, j, ens):
    """Panel arrays d with layer j replaced by a statistic over the same layer read
    from each run of an ensemble (dds, one per run; a missing one is left out): ens
    {stat: mean, median, sd, min, max, range (max - min) or prob (% of the members
    above, or with above False below, threshold), threshold, above, grid}.  Members
    on another grid than layer j's: interpolated onto it with grid "interp", else
    the panel is left blank with a note (as a difference).  L<j>_ens: the number of
    members."""
    if d.get("missing") or f"L{j}" not in d:
        return d
    ax, ay = d.get(f"L{j}_cx", d["x"]), d.get(f"L{j}_cy", d["y"])
    shape, grid = np.shape(d[f"L{j}"]), ens.get("grid", "ask")
    stack = []
    for dd in dds:
        if dd.get("missing") or f"L{j}" not in dd:
            continue
        b = np.asarray(dd[f"L{j}"], dtype=float)
        if not (b.shape == shape and _same(ax, dd["x"]) and _same(ay, dd["y"])):
            if grid != "interp":
                return dict(d, missing="ensemble not drawn: the runs' grids differ" + (
                    "" if grid == "refuse" else " (choose Interpolate or Refuse under the "
                                                "layer's Ensemble)"))
            b = regrid(b, dd["x"], dd["y"], ax, ay)
        stack.append(b)
    if not stack:
        return dict(d, missing="ensemble: no run has output at this time")
    V = np.stack(stack)
    ok = np.isfinite(V)
    have = ok.any(axis=0)
    stat = ens.get("stat", "mean")
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # (all-NaN cells: NaN)
        if stat == "prob":
            thr = float(ens.get("threshold") or 0.0)
            hit = (V > thr) if ens.get("above", True) else (V < thr)
            out = 100.0 * (hit & ok).sum(axis=0) / np.maximum(ok.sum(axis=0), 1)
        elif stat == "sd":
            out = np.nanstd(V, axis=0)
        elif stat == "median":
            out = np.nanmedian(V, axis=0)
        elif stat in ("min", "max", "range"):
            lo, hi = np.nanmin(V, axis=0), np.nanmax(V, axis=0)
            out = {"min": lo, "max": hi}.get(stat, hi - lo)
        else:
            out = np.nanmean(V, axis=0)
    out = np.where(have, out, np.nan)
    return dict(d, **{f"L{j}": np.asarray(out, dtype=np.float32), f"L{j}_ens": len(stack)})


def _same(u, v):
    u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
    return u.shape == v.shape and np.allclose(u, v, atol=1e-6)


def regrid(a, x, y, xn, yn):
    """2-D array a on the rectilinear grid (y, x) interpolated bilinearly onto (yn, xn)
    (NaN outside a's grid)."""
    a, x, y = np.asarray(a, dtype=float), np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    rows = np.array([np.interp(xn, x, r, left=np.nan, right=np.nan) for r in a])
    return np.array([np.interp(yn, y, c, left=np.nan, right=np.nan) for c in rows.T]).T


def tindex(run, time_s):
    """Output index of `run` at model time time_s (s), or None if it has none there."""
    k = int(np.argmin(np.abs(np.asarray(run.times) - time_s)))
    return k if abs(run.times[k] - time_s) <= 1.0 else None


def normalize(spec, run, track="viewer"):
    """Fill in what an older spec (cm1view figures before multi-run panels) lacks:
    times in seconds from the time indices of `run`, `run` (with `track`) as the
    only run, its one cross-section (spec["xsec"]) as the list of sections, and a
    section figure as one section card per panel (sections.to_cards)."""
    nt = len(run.times)
    if "times_s" not in spec:
        spec["times_s"] = [None if t is None else float(run.times[min(int(t), nt - 1)])
                           for t in spec["times"]]
    if "time_s" not in spec:
        spec["time_s"] = float(run.times[min(int(spec["time"]), nt - 1)])
    if not spec.get("runs"):
        spec["runs"] = [run_entry(run, track)]
    upgrade_sections(spec)  # (one section before: spec["xsec"])
    for s in [spec] + list(spec.get("parts") or []):
        upgrade_grid(s)
        th_to_cards(s)  # (time-height figures: a card per panel)
        series_looks(s)  # (time series: a run's line style on its series)
    return to_cards(spec)  # (section figures: a card per panel)


def th_to_cards(spec):
    """An older time-height figure (a panel per series and run, figdraw.th_grid) as a
    figure of cards, in place: each panel's series with its one run and panel number,
    the grid as it was.  A figure of cards, or not a time-height figure, stays."""
    if spec.get("kind") != "th" or figdraw.th_cards(spec):
        return spec
    r, c, cells = figdraw.th_grid(spec)
    ents = spec.get("series") or []
    spec["series"] = [dict(copy.deepcopy(ents[ref[1]]), runs=[int(ref[0])], panel=i)
                      for i, ref in enumerate(cells) if ref is not None]
    spec.update(rows=r, cols=c, runs_as="cards")
    return spec


def series_looks(spec):
    """An older figure's time series (without "ls"), in place: a series of one run
    takes the line style and colour it was drawn in (the run's line style when its
    panel had several runs; the run's colour when alone in a panel of a figure of
    several runs).  The series of a newer figure stay."""
    ents, runs = spec.get("series") or [], spec.get("runs") or []
    nr = len(runs)

    def runs_of(e):
        if e.get("source") == "table":  # (your own data: no run)
            return []
        rs = e.get("runs")
        return list(range(nr)) if rs is None else [int(k) for k in rs if int(k) < nr]

    for e in ents:
        if "ls" in e:
            continue
        e["ls"] = "-"
        ks = runs_of(e)
        if len(ks) != 1 or spec.get("kind") != "line":
            continue
        mates = [x for x in ents if int(x.get("panel", 0)) == int(e.get("panel", 0))
                 and runs_of(x)]
        multi = nr > 1 or len({k for x in mates for k in runs_of(x)}) > 1
        if len(mates) == 1 and multi:
            e["color"] = figdraw.run_color(spec, ks[0])
        elif multi:
            e["ls"] = figdraw.run_style(spec, ks[0])
    return spec


def upgrade_grid(spec):
    """spec with spec["grid"] (what its rows and columns step through) from an older
    spec's "vary", in place.  A panel-by-panel run and time ("custom") becomes a grid
    of alike panels, each with its run and time as a panel edit."""
    g = spec.get("grid") or {}
    if g.get("rows") or g.get("cols") or spec.get("kind", "plan") not in ("plan", "xsec"):
        return spec
    rd, cd = figdraw.grid_axes(spec)
    if cd == "custom":
        edits = spec.setdefault("edits", {})
        for i in range(npanels(spec)):
            ref = panel_ref(spec, i)
            if ref is not None:
                e = edits.setdefault(str(i), {})
                e.setdefault("run", ref[0])
                e.setdefault("time_s", ref[1])
        rd = cd = "none"
    spec["grid"] = dict(rows=rd, cols=cd, runs=[])
    spec["vary"] = legacy_vary(rd, cd)
    return spec


def legacy_vary(rd, cd):
    """The "vary" an older spec had for grid axes (rd, cd) (for older readers of the
    spec: "time", "field", "height", else "grid"; spec["grid"] says what it is)."""
    dims = [d for d in (rd, cd) if d != "none"]
    if len(dims) == 1 and dims[0] in ("times", "fields", "heights"):
        return dims[0][:-1]
    return "grid"


def storm_motion(run, fixes, t):
    """Ground-relative storm motion (u, v) for storm-relative fields at time t: the
    tracked motion where the track has a fix, else the domain motion (as the map)."""
    if fixes:
        m = trk.motion(run, fixes).get(t)
        if m is not None and np.all(np.isfinite(m)):
            return tuple(m)
    return (run.umove, run.vmove)


def shift_times(spec, dt_s):
    """A copy of `spec` with every panel's time moved by dt_s seconds (a frame of an
    animation: the panels step through time together; in a figure of parts, the
    panels of every part, and the soundings)."""
    s = json.loads(json.dumps(spec, default=float))
    if s.get("kind") == "combo":
        s["parts"] = [shift_times(p, dt_s) for p in s["parts"]]
        return s
    s["times_s"] = [None if t is None else float(t) + dt_s for t in s.get("times_s", [])]
    if s.get("time_s") is not None:
        s["time_s"] = float(s["time_s"]) + dt_s
    for p in s.get("panels") or []:
        p["time_s"] = float(p["time_s"]) + dt_s
    for sec in s.get("sections") or []:  # (section cards with their own time)
        if sec.get("time_s") is not None:
            sec["time_s"] = float(sec["time_s"]) + dt_s
    for e in [e for key in ("soundings", "dists", "profiles", "joints", "azims")
              for e in s.get(key) or []]:
        e["time_s"] = float(e["time_s"]) + dt_s
        if e.get("time_s1") is not None:
            e["time_s1"] = float(e["time_s1"]) + dt_s
    for e in (s.get("edits") or {}).values():  # (panels and layers with their own time)
        if e.get("time_s") is not None:
            e["time_s"] = float(e["time_s"]) + dt_s
        for lay in list((e.get("layers") or {}).values()) + list(e.get("extra") or []):
            if lay.get("time_s") is not None and not lay.get("time_lock"):
                lay["time_s"] = float(lay["time_s"]) + dt_s
    return s


def animated(spec):
    """Whether the spec has panels that step in time (plan views, sections, soundings;
    time-height and time-series panels stay as they are)."""
    parts = spec["parts"] if spec.get("kind") == "combo" else [spec]
    return any(p["kind"] in ("plan", "xsec") for p in parts)


def time_refs(spec):
    """(run path, model time s) of every panel that steps in an animation: plan views
    and sections (all parts of a figure of parts), soundings, distributions, profiles,
    joint distributions and azimuthal means."""
    out = []
    for p in spec["parts"] if spec.get("kind") == "combo" else [spec]:
        runs = p.get("runs") or []
        if p["kind"] in ("plan", "xsec"):
            for i in range(npanels(p)):
                ref = panel_ref(p, i)
                if ref is None:
                    continue
                out.append((runs[ref[0]]["path"], ref[1]))
                lays = figdraw.spec_layers(p, i)
                out += [(runs[k]["path"], ts) for (k, ts), js in layer_groups(p, i).items()
                        if not all(lays[j].get("time_lock") for j in js)]
        elif p["kind"] in ("sounding", "dist", "profile", "joint", "azim"):
            out += [(runs[int(e.get("run", 0))]["path"], float(e["time_s"]))
                    for e in p.get(figdraw.ENTRIES[p["kind"]]) or []
                    if int(e.get("run", 0)) < len(runs)
                    and e.get("source") != "table"]  # (your own data: no time)
    return out


def frame_offsets(spec, runs, step=1, end_s=None, limit=None):
    """Time offsets (s) of the animation frames, every `step` outputs of the first
    panel's run from the figure's own times up to that run's model time end_s (None:
    its end), while every panel has an output at its shifted time; at most `limit`
    frames.  runs: {run path: CM1Run} of the panels' runs (time_refs)."""
    refs = time_refs(spec)
    if not refs:
        return []
    p0, ts0 = refs[0]
    run0 = runs[p0]
    i0 = tindex(run0, ts0)
    if i0 is None:
        return []
    out = []
    for i in range(i0, len(run0.times), max(int(step), 1)):
        if end_s is not None and run0.times[i] > end_s + 1.0:
            break
        dt = float(run0.times[i] - run0.times[i0])
        if any(tindex(runs[p], ts + dt) is None for p, ts in refs):
            break
        out.append(dt)
        if limit is not None and len(out) >= limit:
            break
    return out


def write_gif(images, path, fps=4.0, loop=True):
    """An animated GIF of PIL images (frames of different sizes are padded to the
    largest, on white)."""
    from PIL import Image
    path = _abs(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    w = max(im.width for im in images)
    h = max(im.height for im in images)
    frames = []
    for im in images:
        if im.size != (w, h) or im.mode != "RGB":
            canvas = Image.new("RGB", (w, h), "white")
            canvas.paste(im, (0, 0), im if im.mode == "RGBA" else None)
            im = canvas
        frames.append(im.convert("P", palette=Image.Palette.ADAPTIVE, colors=256))
    kw = dict(loop=0) if loop else {}
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=max(20, int(round(1000.0 / float(fps)))), disposal=2, **kw)
    return path


def _abs(path):
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
