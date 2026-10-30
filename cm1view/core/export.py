"""netCDF export of fields: a box of the domain, some output times, any fields the
viewer shows (native, derived, derivatives, column fields) on the model levels or at
heights, written one time after another to a CF-style file.  Used by the viewer's
Export data dialog and by `cm1view export` (no Panel / Bokeh here)."""

import datetime
import os
import re

import netCDF4
import numpy as np

from .. import config
from .fields import COSTLY, column_stride, split_deriv
from .run import IO_LOCK, MissingAtTime

FILL = np.float32(np.nan)
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def cf_units(units):
    """A field's display units as UDUNITS text ('10⁻³ s⁻¹' -> '1e-3 s-1', '°C' ->
    'degC', 'm²/s²' -> 'm2/s2'); '1' when it has none."""
    u = (units or "").replace("°C", "degC").replace("°", "degree").translate(_SUP).strip()
    u = re.sub(r"^10(-?\d+)\b\s*", r"1e\1 ", u).strip()
    return u or "1"


def var_name(name):
    """The netCDF variable of a field ('ddz.winterp' -> 'ddz_winterp')."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def box_index(run, box):
    """(i0, i1, j0, j1) of the columns whose centres are in box (x0, x1, y0, y1) km
    (None: the whole domain); at least one column each way."""
    if box is None:
        return 0, run.ni, 0, run.nj

    def span(c, lo, hi):
        lo, hi = min(lo, hi), max(lo, hi)
        a, b = int(np.searchsorted(c, lo, "left")), int(np.searchsorted(c, hi, "right"))
        if b <= a:  # (a box narrower than a column: the nearest one)
            a = int(np.clip(np.argmin(np.abs(c - 0.5 * (lo + hi))), 0, len(c) - 1))
            b = a + 1
        return a, b
    x0, x1, y0, y1 = (float(v) for v in box)
    return (*span(run.xh, x0, x1), *span(run.yh, y0, y1))


def model_levels(run, ztop=None):
    """Indices of the model levels up to ztop km (None: all)."""
    if ztop is None or not np.isfinite(ztop) or ztop <= 0:
        return np.arange(run.nk)
    return np.arange(max(1, int(np.searchsorted(run.z, float(ztop), "right"))))


def plan(run, F, names, times, box=None, heights=None, ztop=None):
    """What an export holds: dict(names, times, box (i0, i1, j0, j1), ks (model
    levels) or heights (km), nz, bytes (uncompressed)); ValueError when it holds
    nothing or names a field this run lacks."""
    names = list(dict.fromkeys(n for n in names if n))
    if not names:
        raise ValueError("no fields chosen")
    bad = [n for n in names if n not in F]
    if bad:
        raise ValueError(f"not a field of this run: {', '.join(bad)}")
    times = sorted({int(t) for t in times if 0 <= int(t) < len(run.times)})
    if not times:
        raise ValueError("no output times chosen")
    i0, i1, j0, j1 = box_index(run, box)
    if heights is not None:
        heights = sorted({round(float(h), 4) for h in heights if np.isfinite(h) and h >= 0})
        if not heights:
            raise ValueError("no heights given")
        ks, nz = None, len(heights)
    else:
        ks = model_levels(run, ztop)
        nz = len(ks)
    per = sum(nz if F[n].ndim == 3 else 1 for n in names)
    return dict(names=names, times=times, box=(i0, i1, j0, j1), ks=ks, heights=heights,
                nz=nz, bytes=4 * per * len(times) * (i1 - i0) * (j1 - j0))


def size_text(nbytes):
    for unit, k in (("GB", 1024**3), ("MB", 1024**2), ("kB", 1024)):
        if nbytes >= k:
            return f"{nbytes / k:.1f} {unit}"
    return f"{nbytes} B"


def default_name(run, p):
    """File name of an export, e.g. 'winterp_zvort_t3600-7200s.nc'."""
    names = [var_name(n) for n in p["names"]]
    head = "_".join(names[:3]) + (f"_and{len(names) - 3}" if len(names) > 3 else "")
    t0, t1 = (int(round(run.times[t])) for t in (p["times"][0], p["times"][-1]))
    return f"{head}_t{t0}" + (f"-{t1}" if t1 != t0 else "") + "s.nc"


def default_path(run, p):
    return os.path.join(config.exports_dir(run.path, "data"), default_name(run, p))


def _coord_attrs(run, name, extra):
    """CM1's own attributes of a coordinate (long_name, units) with CF ones added."""
    a = {}
    try:
        with IO_LOCK, netCDF4.Dataset(run.files[0]) as d:
            if name in d.variables:
                v = d[name]
                a = {k: v.getncattr(k) for k in v.ncattrs() if k in ("long_name", "units")}
    except OSError:
        pass
    return dict(a, **extra)


def _values(F, name, t, p, storm):
    """(nz, ny, nx) or (ny, nx) float32 of a field at time t in the export's box."""
    i0, i1, j0, j1 = p["box"]
    d = F[name]
    if d.ndim != 3:
        return F.plane(name, t, storm=storm)[j0:j1, i0:i1]
    if p["heights"] is None:  # (model levels: the volume, as cross-sections use it)
        return F.volume(name, t, storm)[p["ks"], j0:j1, i0:i1]
    # heights: the map's plane at each (same values as the map shows)
    op, base = split_deriv(name)
    natives = F[base].natives if F[base].derived else (base,)
    F.run.load_volumes([n for n in natives if n in F.run.vars and F.run.vars[n].ndim == 3], t)
    return np.stack([F.plane(name, t, "height", h, storm)[j0:j1, i0:i1]
                     for h in p["heights"]])


def write(run, F, path, p, storm=None, compress=True, progress=None, cancelled=None):
    """Write plan p (see plan) to netCDF file `path`, one time after another (a reader
    can open the file while it grows).  storm: storm motion (u, v) m/s for the
    storm-relative fields, or a function of the time index giving it (None: the
    domain motion).  progress(done, total, text) after each field; cancelled() is
    asked between fields: the file then keeps the times done (global attribute
    cm1view_incomplete).  Returns dict(path, times (written), missing {name: [time
    index]} (not in the output then: NaN), cancelled)."""
    path = config.expand(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    i0, i1, j0, j1 = p["box"]
    names, times = p["names"], p["times"]
    any3 = any(F[n].ndim == 3 for n in names)
    stormy = any(F[n].storm for n in names)

    def motion(t):
        if storm is None:
            return (run.umove, run.vmove)
        return tuple(storm(t)) if callable(storm) else tuple(storm)

    part = path + ".part"
    total, done, written, missing, stopped = len(names) * len(times), 0, 0, {}, False
    ds = netCDF4.Dataset(part, "w", format="NETCDF4")
    try:
        _header(ds, run, F, p, any3, stormy, compress)
        for n, t in enumerate(times):
            if cancelled is not None and cancelled():
                stopped = True
                break
            ds["time"][n] = run.times[t]
            uv = motion(t)
            if stormy:
                ds["storm_u"][n], ds["storm_v"][n] = uv
            for name in names:
                if cancelled is not None and cancelled():
                    stopped = True
                    break
                try:
                    a = _values(F, name, t, p, uv if F[name].storm else None)
                    ds[var_name(name)][n] = np.asarray(a, dtype=np.float32)
                except MissingAtTime:
                    missing.setdefault(name, []).append(t)
                done += 1
                if progress is not None:
                    progress(done, total, f"{run.time_label(t)} {name}")
            if stopped:
                break
            written = n + 1
            ds.sync()  # (readable up to here)
        if stopped:
            ds.setncattr("cm1view_incomplete",
                         f"stopped: {written} of {len(times)} times complete"
                         + (f"; time {written + 1} partly written" if written < len(times)
                            and done > written * len(names) else ""))
        if missing:
            ds.setncattr("cm1view_missing", "; ".join(
                f"{n}: not in the output at {', '.join(run.time_label(t) for t in ts)}"
                for n, ts in missing.items()))
    except BaseException:
        ds.close()
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    ds.close()
    os.replace(part, path)
    return dict(path=path, times=written, missing=missing, cancelled=stopped)


def _header(ds, run, F, p, any3, stormy, compress):
    """Dimensions, coordinates, global attributes and the (empty) field variables."""
    from .. import __version__
    i0, i1, j0, j1 = p["box"]
    ds.createDimension("time", None)
    ds.createDimension("yh", j1 - j0)
    ds.createDimension("xh", i1 - i0)
    v = ds.createVariable("time", "f8", ("time",))
    v.setncatts(_coord_attrs(run, "time", dict(axis="T")))
    for name, c, lo, hi, ax, std in (("xh", run.xh, i0, i1, "X", "projection_x_coordinate"),
                                     ("yh", run.yh, j0, j1, "Y", "projection_y_coordinate")):
        v = ds.createVariable(name, "f8", (name,))
        v.setncatts(_coord_attrs(run, name, dict(units="km", axis=ax, standard_name=std)))
        v[:] = c[lo:hi]
    z = None
    if any3:
        ds.createDimension("z", p["nz"])
        v = ds.createVariable("z", "f8", ("z",))
        if p["heights"] is None:
            v.setncatts(_coord_attrs(run, "z", dict(units="km", axis="Z", positive="up",
                                                    standard_name="height")))
            v[:] = run.z[p["ks"]]
            k = ds.createVariable("level", "i4", ("z",))
            k.setncatts(dict(long_name="model level index (from 0)"))
            k[:] = p["ks"]
        else:
            v.setncatts(dict(long_name="height above ground", units="km", axis="Z",
                             positive="up", standard_name="height"))
            v[:] = p["heights"]
        z = ("z",)
    if stormy:
        for c, what in (("storm_u", "x"), ("storm_v", "y")):
            v = ds.createVariable(c, "f4", ("time",))
            v.setncatts(dict(long_name=f"storm motion, {what} (ground-relative), of the "
                                       "storm-relative fields", units="m/s"))
    ny, nx = j1 - j0, i1 - i0
    for name in p["names"]:
        d = F[name]
        dims = ("time",) + (z if d.ndim == 3 else ()) + ("yh", "xh")
        chunks = (1,) * (len(dims) - 2) + (ny, nx)
        v = ds.createVariable(var_name(name), "f4", dims, fill_value=FILL, zlib=compress,
                              complevel=1, shuffle=compress, chunksizes=chunks)
        a = dict(long_name=d.label, units=cf_units(d.units), cm1view_name=name)
        if cf_units(d.units) != (d.units or "1"):
            a["units_shown"] = d.units
        op, base = split_deriv(name)
        if op:
            a["comment"] = (f"{op} of {base}, per km" + (" (centred on the stretched "
                            "levels, one-sided at the bottom and top)" if op == "ddz" else ""))
        if d.column:
            z0, z1 = d.layer
            a["layer"] = f"{z0:g} to {'the model top' if z1 is None else f'{z1:g} km'} AGL"
        if d.storm:
            a["storm_relative"] = "relative to storm_u, storm_v"
        if split_deriv(name)[1] in COSTLY:
            a["column_stride"] = np.int32(column_stride(run))
        v.setncatts(a)
    ds.setncatts({
        "Conventions": "CF-1.8",
        "title": f"cm1view export of {run.name}",
        "source": f"CM1 output in {run.path}",
        "history": f"{datetime.datetime.now().isoformat(timespec='seconds')} "
                   f"cm1view {__version__} export",
        "cm1view_version": __version__,
        "cm1view_run": run.path,
        "cm1view_box_km": np.array([run.xh[i0], run.xh[i1 - 1], run.yh[j0],
                                    run.yh[j1 - 1]]),
        "cm1view_levels": "model levels" if p["heights"] is None else "heights (km AGL)",
        "umove": run.umove, "vmove": run.vmove,
        "comment": "Winds and positions are grid-relative (CM1's); values are in the "
                   "units the viewer shows (units_shown where those are not UDUNITS)."})


# ---------------------------------------------------------------- cm1view export
def times_between(run, t0_min=None, t1_min=None, every=1):
    """Output indices from model time t0 to t1 (min; None: the run's first / last),
    every `every`-th output, each end snapped to the nearest output."""
    ts = np.asarray(run.times)

    def near(m, default):
        return default if m is None else int(np.argmin(np.abs(ts - 60.0 * float(m))))
    a, b = near(t0_min, 0), near(t1_min, len(ts) - 1)
    return list(range(min(a, b), max(a, b) + 1, max(1, int(every))))


def storm_motion(run, track):
    """storm(t) for write: the tracked storm's motion where the track (a storm_tracks
    file; 'auto': the run's own, found by the track_dirs setting) has a fix, else the
    domain motion, as the viewer's map does.  (function, note)"""
    from . import track as trk
    path = config.find_track(run.path) if track == "auto" else config.expand(track)
    if not path:
        return None, "no storm_tracks file found: storm-relative fields use umove, vmove"
    fixes = trk.load(run, path)
    m = {t: uv for t, uv in trk.motion(run, fixes).items() if np.all(np.isfinite(uv))}

    def storm(t):
        return m.get(t, (run.umove, run.vmove))
    return storm, f"storm motion from {path} ({len(m)} of {len(run.times)} times)"


def _floats(text, n=None, what="values"):
    try:
        v = [float(x) for x in re.split(r"[,\s]+", text.strip()) if x]
    except ValueError:
        raise ValueError(f"{what}: numbers separated by commas, not {text!r}") from None
    if n is not None and len(v) != n:
        raise ValueError(f"{what}: {n} numbers, not {text!r}")
    return v


def parser():
    import argparse
    ap = argparse.ArgumentParser(
        prog="cm1view export",
        description="Write fields of a run to a netCDF file: any field the viewer has "
                    "(native, derived, derivatives such as ddz.winterp, column fields), "
                    "in a box, on the model levels or at heights, one time after another.",
        epilog="Fields: names as in the viewer's lists (cm1view export RUN --list); a "
               "derivative is ddx./ddy./gradh./ddz. before a field's name.  --out may "
               "hold {run} (the run's folder name) and {name} (the default file name).")
    ap.add_argument("run", help="the run's folder")
    ap.add_argument("--fields", default="", metavar="A,B,...",
                    help="fields to write, comma-separated")
    ap.add_argument("--list", action="store_true", help="list the run's fields and stop")
    ap.add_argument("--time", type=float, default=None, metavar="MIN",
                    help="one model time (min); else --from / --to / --every")
    ap.add_argument("--from", dest="t0", type=float, default=None, metavar="MIN",
                    help="first model time (min; default: the first output)")
    ap.add_argument("--to", dest="t1", type=float, default=None, metavar="MIN",
                    help="last model time (min; default: the last output)")
    ap.add_argument("--every", type=int, default=1, metavar="N",
                    help="every N-th output (default 1)")
    ap.add_argument("--box", default=None, metavar="X0,X1,Y0,Y1",
                    help="grid-relative box (km; default: the whole domain)")
    ap.add_argument("--ztop", type=float, default=None, metavar="KM",
                    help="model levels up to this height (default: all)")
    ap.add_argument("--heights", default=None, metavar="Z1,Z2,...",
                    help="at these heights (km AGL), as the map shows them, instead of "
                         "on the model levels")
    ap.add_argument("--track", default="auto", metavar="FILE",
                    help="storm track for storm-relative fields (default auto: the run's "
                         "storm_tracks file if there is one; none: umove, vmove)")
    ap.add_argument("--storm", default=None, metavar="U,V",
                    help="fixed ground-relative storm motion (m/s) instead of a track")
    ap.add_argument("--out", default=None, metavar="PATH",
                    help="the file (default: <exports folder>/<run>/data/<name>)")
    ap.add_argument("--no-compress", action="store_true",
                    help="no zlib compression (larger, quicker to write)")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace the file if it is there (default: stop)")
    ap.add_argument("--config", default=None, help="settings file")
    ap.add_argument("--cache-gb", type=float, default=None,
                    help="memory budget for cached 3D fields")
    ap.add_argument("--workers", type=int, default=None, help="parallel reader processes")
    return ap


def main(argv=None):
    import sys
    import time as _time
    argv = list(sys.argv[1:] if argv is None else argv)
    for k in range(len(argv) - 1):  # (--box -20,10,... : argparse takes -20 for an option)
        if argv[k] in ("--box", "--storm", "--heights") and re.match(r"-[\d.]", argv[k + 1]):
            argv[k:k + 2] = [f"{argv[k]}={argv[k + 1]}", ""]
    args = parser().parse_args([a for a in argv if a != ""])

    def fail(msg):
        print(f"cm1view export: {msg}", file=sys.stderr)
        return 2
    if args.config:
        config.load(args.config)
    for name, flag in (("cache_gb", "--cache-gb"), ("workers", "--workers")):
        if getattr(args, name) is not None:
            config.override(name, getattr(args, name), flag)
    path = config.expand(args.run)
    if not os.path.isdir(path):
        return fail(f"run folder {path} not found")
    from .fields import Fields
    from .run import CM1Run
    try:
        run = CM1Run(path, config.cache_gb()[0], config.workers()[0])
    except (OSError, ValueError) as e:
        return fail(str(e))
    F = Fields(run)
    if args.list:
        for g, items in F.groups().items():
            print(f"{g}:")
            for label, n in items.items():
                print(f"  {n:14s} {label.rsplit(' [', 1)[0]} ({F[n].ndim}D)")
        return 0
    try:
        box = None if args.box is None else _floats(args.box, 4, "--box")
        heights = None if args.heights is None else _floats(args.heights, what="--heights")
        storm = None if args.storm is None else tuple(_floats(args.storm, 2, "--storm"))
        times = (times_between(run, args.time, args.time) if args.time is not None else
                 times_between(run, args.t0, args.t1, args.every))
        p = plan(run, F, [n.strip() for n in args.fields.split(",")], times, box,
                 heights, args.ztop)
    except ValueError as e:
        return fail(str(e))
    out = default_path(run, p) if args.out is None else config.expand(args.out.format(
        run=os.path.basename(run.path.rstrip("/")), name=default_name(run, p)))
    if os.path.exists(out) and not args.overwrite:
        return fail(f"{out} is already there (--overwrite replaces it)")
    note = None
    if storm is None and args.track != "none" and any(F[n].storm for n in p["names"]):
        try:
            storm, note = storm_motion(run, args.track)
        except (OSError, ValueError) as e:
            return fail(f"storm track: {e}")
    if note:
        print(f"cm1view export: {note}", flush=True)
    i0, i1, j0, j1 = p["box"]
    print(f"cm1view export: {len(p['names'])} field(s) x {len(p['times'])} time(s), "
          f"{i1 - i0}x{j1 - j0} columns x {p['nz']} "
          f"{'levels' if p['heights'] is None else 'heights'} "
          f"(~{size_text(p['bytes'])} before compression) -> {out}", flush=True)
    t0, last = _time.time(), [0.0]

    def progress(done, total, what):
        if _time.time() - last[0] >= 5.0 or done == total:
            last[0] = _time.time()
            print(f"cm1view export: {done}/{total} {what} [{_time.time() - t0:.0f}s]",
                  flush=True)
    try:
        r = write(run, F, out, p, storm, not args.no_compress, progress)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"cm1view export: failed: {e}", file=sys.stderr)
        return 1
    for n, ts in r["missing"].items():
        print(f"cm1view export: note: {n} is not in the output at {len(ts)} time(s) "
              "(NaN there)", flush=True)
    print(f"cm1view export: saved {r['path']} [{_time.time() - t0:.1f}s]", flush=True)
    return 0
