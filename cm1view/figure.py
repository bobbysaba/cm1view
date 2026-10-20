"""Publication figures: the figure spec, the data behind each panel, and export.

The spec (a JSON-able dict) says what each panel shows and how it looks; figdraw.draw
turns it plus the panel arrays into a matplotlib figure.  Panels vary in time (one
field setup at several times) or in field (several fills at one time), as plan views
at fixed heights or vertical cross-sections, over the whole domain, a fixed box, or a
window centred on the tracked storm.

Exporting writes the image and, optionally, a stand-alone script (figdraw's code +
the spec as a Python dict), the plotted arrays (.npz) and the spec (.json), so the
figure can be redrawn or restyled later without the viewer.
"""

import json
import os
import pprint
import time as _time

import numpy as np

from . import figdraw, render
from .run import FileBusy, MissingAtTime

DATA_KEYS = ("type", "field", "mode", "z", "spacing", "zspacing", "frame")  # -> data


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
                    frame="ground", scale=250.0, width=0.002, color="k", key=0.0)
    if kind == "track":
        return dict(type="track", on=True, color="k", lw=1.0, ls="-", marker=True, legend="")
    if kind == "line":
        return dict(type="line", on=True, color="k", lw=2.0, labels="X, X′", legend="")
    raise ValueError(kind)


def _refl_cmap():
    """HomeyerRainbow when pyart is available, else NWS reflectivity steps."""
    try:
        figdraw.colormap("HomeyerRainbow")
        return "HomeyerRainbow"
    except Exception:  # noqa: BLE001
        return "reflectivity"


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
        domain=dict(mode="storm", half=12.5, box=None), coords="grid",
        xsec=dict(mode="storm", a=None, b=None, angle=0.0, half=10.0, offset=[0.0, 0.0],
                  ztop=6.0, dz=0.025),
        axes=dict(xlabel="x (km)", ylabel="y (km)", ticks=True, ticklabels="outer",
                  equal=True, minor=False, title_bold=True),
        letters=dict(on=True, fmt="{a}", loc="lower left", size=12, bold=True),
        time_label=dict(on=True, fmt="t = {min:g} min", loc="lower right", size=12,
                        bold=True, t0_min=0.0),
        titles=[], suptitle="",
        colorbar=dict(mode="shared", orientation="horizontal", label="", shrink=0.7,
                      fraction=0.05, pad=0.02, ticks=""),
        legend=dict(panel=0, loc="upper right", frame=True),
        font=dict(family="sans-serif", size=10), background="white",
        spacing=dict(w_pad=0.04, h_pad=0.04, wspace=0.02, hspace=0.02),
        export=dict(format="png", dpi=250, tight=True),
    )


def npanels(spec):
    n = len(spec["times"]) if spec["vary"] == "time" else max(1, len(spec["panel_fills"]))
    return min(n, int(spec["rows"]) * int(spec["cols"]))


def panel_time(spec, i):
    if spec["vary"] == "time":
        return int(spec["times"][i])
    return int(spec["time"])


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


def data_key(spec, i, center):
    """Everything panel i's arrays depend on (style changes leave it unchanged)."""
    layers = figdraw.spec_layers(spec, i)
    lk = [{k: lay.get(k) for k in DATA_KEYS if k in lay} | {"on": lay.get("on", True)}
          for lay in layers]
    return json.dumps(dict(kind=spec["kind"], t=panel_time(spec, i), dom=spec["domain"],
                           coords=spec["coords"], xsec=spec["xsec"] if spec["kind"] == "xsec"
                           or any(lay["type"] == "line" for lay in layers) else None,
                           layers=lk, center=center), sort_keys=True, default=float)


# ------------------------------------------------------------------ data
def extract(run, F, spec, i, center, fixes=None, storm=None, progress=None):
    """Arrays of panel i (dict for figdraw).  center: tracked storm (x, y) km at the
    panel time or None; fixes: {t: fix} for the track layer; storm: ground-relative
    storm motion (u, v) at this time for storm-relative fields and vectors."""
    t = panel_time(spec, i)
    out = dict(time_s=float(run.times[t]))
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
            si = max(1, int(round(float(lay["spacing"]) / max(s[1] - s[0], 1e-6))))
            zi = max(1, int(round(float(lay.get("zspacing", 0.5)) / dz)))
            sl = (slice(zi // 2, None, zi), slice(si // 2, None, si))
            S, Z = np.meshgrid(out["x"], zq)
            out[f"L{j}_x"], out[f"L{j}_y"] = S[sl], Z[sl]
            out[f"L{j}_u"], out[f"L{j}_v"] = (u * ex + v * ey)[sl], w[sl]


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


def save_bundle(spec, data, base, run=None, note=""):
    """Image + script + data + spec next to each other: <base>.<fmt>, <base>.py,
    <base>_data.npz, <base>_spec.json.  Returns the paths."""
    base = _abs(base)
    root, ext = os.path.splitext(base)
    if ext.lower() in (".png", ".pdf", ".svg", ".eps", ".tif", ".tiff", ".jpg"):
        base = root
    fmt = spec.get("export", {}).get("format", "png")
    os.makedirs(os.path.dirname(base), exist_ok=True)
    img = save_image(spec, data, f"{base}.{fmt}")
    npz = f"{base}_data.npz"
    np.savez_compressed(npz, **flatten(data))
    with open(f"{base}_spec.json", "w") as f:
        json.dump(spec, f, indent=1, default=float)
    with open(f"{base}.py", "w") as f:
        f.write(script(spec, os.path.basename(npz), f"{os.path.basename(base)}.{fmt}", run,
                       note))
    return dict(image=img, script=f"{base}.py", data=npz, spec=f"{base}_spec.json")


def script(spec, npz_name, out_name, run=None, note=""):
    """A stand-alone script that redraws the figure from the saved arrays."""
    import inspect
    src = inspect.getsource(figdraw)
    head = [
        f'"""Figure made with cm1view on {_time.strftime("%Y-%m-%d %H:%M")}.',
        "",
        f"run: {run.path}" if run is not None else "",
        note,
        "Redraw:  python this_script.py   (needs numpy and matplotlib; pyart for its",
        "colormaps).  Change SPEC below to restyle (colours, ranges, labels, size, ...);",
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
        f"    data = load_data(os.path.join(here, {npz_name!r}))",
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
    return spec


def _abs(path):
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
