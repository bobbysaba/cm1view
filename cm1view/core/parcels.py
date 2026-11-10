"""Parcel (trajectory) output: CM1's cm1out_pdata.nc (iprcl = 1).

Layout, as CM1 writes it: dimension xh is the parcel number (n parcels; the "xh"
variable holds 1..n), yh = zh = 1, time; every variable is (time, xh): x, y, z (m; z
above sea level), u, v, w, th, prs, ...  The global missing_value marks parcels without
a value; parcels that leave an open domain are written as -1e30.  Both read as NaN.
A run's parcel output may be split over several files (Settings: parcel_glob, e.g. one
per restart): they are joined by time, a later file winning where times overlap.

Parcel times are their own axis, usually much finer than the 3D output: nothing here
assumes they equal run.times.  A viewer time picks the parcel time at or before it, or
interpolates between the two around it (heads).

Reads.  The files are uncompressed, chunked one time per chunk, so a range of parcels at
a range of times can be read without reading whole chunks; but every (time, range) read
pays a seek (~30 ms on a parallel filesystem), while a whole time of one variable of
10 M parcels (43 MB) takes ~0.3 s.  So the parcels wanted are grouped into contiguous
runs of IDs, runs closer than GAP IDs are merged (reading through the gap is cheaper
than another seek), and each run is read for all its times at once, in blocks of at
most BLOCK bytes.  Few clustered parcels cost a few seeks per time; many scattered ones
cost whole time slices.  Trajectories of a parcel set are kept in memory and in the
cache folder (Settings: cache_dir), so they are read once.

Selections (select) pick parcels by a rule at one parcel time: a box and/or a height
range, a disc or ball around a point, value ranges of parcel variables, then at most
`cap` of them (every n-th, or a random sample).  When the parcels were seeded on a
regular lattice (detected from the first time and cached) and the rule is at that time,
the box / height / point part is index arithmetic and reads nothing.  The result is a
ParcelSet (IDs, name, rule), saved under <exports_dir>/<run>/parcels.

Positions are returned in km (x, y as the 3D grid's xh, yh; z above sea level), other
variables in their file units.

Gridded fields along the trajectories.  A parcel variable "@<field>" is a field of the
run's 3D output (native, derived or a derivative, as named in Fields) sampled at the
parcels' positions: trilinear in space, and at a parcel time between two 3D outputs
linear in time between the values of the two fields at the parcel's position then.
Parcel times outside the 3D outputs' span are NaN.  Each 3D time's field is read once
for all parcel times around it; the result is cached like a trajectory (keyed also by
the 3D files, so rewritten files are sampled again).  Heights: the parcel's z against
the grid's z, which are the same without terrain; on a terrain run against the level
heights of the parcel's column at that 3D time (z above sea level).

Traced trajectories.  A model that writes no parcel output (WoFS: run.traced_parcels)
gets parcels cm1view traces itself through the 3D winds (core.trajcalc), written in
this same layout to the cache folder and read by the same code (trajcalc.Traced).

The w budget.  Along a parcel, Dw/Dt = b + vpg + the rest (subgrid mixing, numerical
diffusion), with CM1's parcel buoyancy b and vertical perturbation pressure gradient
acceleration vpg.  Two variables are computed from the output (ALONG): "dwdt", Dw/Dt
as centred differences of the parcel's w over the parcel times, and "wres", Dw/Dt - b -
vpg.  So they are as good as the parcel cadence resolves w.  since() turns any of them
into its change, or its time integral, from the time the set was chosen: integrated,
Δw = ∫b dt + ∫vpg dt + ∫rest dt.
"""

import glob
import hashlib
import json
import os
import re
import threading
from collections import OrderedDict

import numpy as np
import netCDF4

from .run import IO_LOCK, ahead, ahead_width, temp_name

CACHE_DIR = None  # None: <cache_dir setting>/parcels (tests point this elsewhere)
GAP = 1 << 20  # parcels: read through gaps between wanted IDs shorter than this
BLOCK = 256 * 1024**2  # bytes read at once
POS = ("x", "y", "z")
MISSING_ABS = 1e29  # |value| >= this is missing (CM1's -1e30 for parcels that left)
GRID = "@"  # parcel variable "@<field>": the run's 3D field sampled along the trajectories
# variables computed along the trajectories: name -> (the output's variables they need,
# short label, long name)
ALONG = {
    "dwdt": (("w",), "Dw/Dt", "Dw/Dt along the parcel (d/dt of its w)"),
    "wres": (("w", "b", "vpg"), "Dw/Dt − b − vpg",
             "the rest of the w budget, Dw/Dt − b − vpg (subgrid mixing, numerics)"),
}
BUDGET = ("dwdt", "b", "vpg", "wres")  # (the w budget's terms, as plotted)
BUDGET_NEEDS = ("w", "b", "vpg")
SINCE = {"delta": "change since the set's time", "int": "∫ dt since the set's time"}
_lock = threading.Lock()


def cache_dir():
    if CACHE_DIR:
        return CACHE_DIR
    from .. import config
    return config.cache_dir("parcels")


def find_files(run_path, pattern=None):
    """The parcel output files of a run folder (Settings: parcel_glob).  (A run whose
    model writes none, run.traced_parcels, gets them traced instead: core.trajcalc.)"""
    if pattern is None:
        from .. import config
        pattern = config.get("parcel_glob")
    return sorted(glob.glob(os.path.join(run_path, pattern)))


_open = {}  # run path -> ParcelFile


def offered(run):
    """Whether the run has parcels to choose: parcel output files, or (a model that
    writes none: run.traced_parcels) trajectories cm1view traces itself, which may be
    turned off for the run (trajcalc.off says why; for_run is then None)."""
    return getattr(run, "traced_parcels", False) or bool(find_files(run.path))


def for_run(run, fields=None):
    """The run's ParcelFile (reopened when its files change), or None without any.
    A run whose model writes no parcels (run.traced_parcels) gets trajectories traced
    through its 3D winds (trajcalc.Traced) unless they are turned off for it
    (trajcalc.off).  fields: the run's Fields (for "@<field>" variables; made when first
    needed if not given)."""
    traced = getattr(run, "traced_parcels", False)
    files = [] if traced else find_files(run.path)
    if traced:
        from . import trajcalc
        if trajcalc.off(run):
            return None
        sig = trajcalc.signature(run)
    elif not files:
        return None
    else:
        sig = _signature(files)
    with _lock:
        pf = _open.get(run.path)
        if pf is None or pf.sig != sig:
            pf = _open[run.path] = trajcalc.Traced(run, sig) if traced else ParcelFile(files)
        if fields is not None:
            pf.attach(fields)
        elif pf._run is not run:
            pf._run, pf._fields = run, None
    return pf


def grid_field(name):
    """The 3D field of parcel variable "@<field>", or "" (a variable of the output)."""
    return name[len(GRID):] if isinstance(name, str) and name.startswith(GRID) else ""


def _signature(paths):
    return hashlib.sha1(json.dumps(
        [(p, os.path.getsize(p), int(os.path.getmtime(p))) for p in paths]
    ).encode()).hexdigest()[:16]


def _id_runs(ids):
    """[(lo, hi)] half-open ranges covering sorted unique ids, gaps < GAP merged."""
    if len(ids) == 0:
        return []
    cut = np.flatnonzero(np.diff(ids) > GAP) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [len(ids)]])
    return [(int(ids[a]), int(ids[b - 1]) + 1) for a, b in zip(starts, ends)]


class ParcelFile:
    """One run's parcel output (one or several files joined by time)."""

    def __init__(self, paths):
        paths = [paths] if isinstance(paths, str) else list(paths)
        if not paths:
            raise FileNotFoundError("no parcel output files")
        parts = []
        self.vars, self.missing, self.n = {}, None, None
        with IO_LOCK:
            for p in paths:
                with netCDF4.Dataset(p) as d:
                    d.set_auto_mask(False)
                    t = np.asarray(d["time"][:], dtype=np.float64)
                    if "x" not in d.variables:
                        raise ValueError(f"{p}: no parcel positions (x)")
                    dim = d["x"].dimensions[-1]
                    n = len(d.dimensions[dim])
                    if self.n is None:
                        self.n, self.dim = n, dim
                    elif n != self.n:
                        raise ValueError(f"{p}: {n} parcels, the other files {self.n}")
                    for name, v in d.variables.items():
                        if v.dimensions[:1] == ("time",) and v.ndim >= 2 \
                                and v.dimensions[-1] == dim and name not in self.vars:
                            self.vars[name] = (getattr(v, "long_name", name),
                                               getattr(v, "units", ""))
                    if self.missing is None and "missing_value" in d.ncattrs():
                        self.missing = np.float32(d.getncattr("missing_value"))
                parts.append((p, t))
        # join by time: each file up to the first time of the next (a restart rewrites
        # from there), keeping the later file's values where they overlap
        parts.sort(key=lambda pt: pt[1][0] if len(pt[1]) else np.inf)
        self.segments, times = [], []  # (path, local i0, local i1, global i0)
        for k, (p, t) in enumerate(parts):
            stop = parts[k + 1][1][0] if k + 1 < len(parts) and len(parts[k + 1][1]) \
                else np.inf
            m = int(np.searchsorted(t, stop - 1e-6))
            if m > 0:
                self.segments.append((p, 0, m, len(times)))
                times.extend(t[:m])
        self.times = np.asarray(times, dtype=np.float64)
        self.paths = [p for p, _ in parts]
        self.sig = _signature(self.paths)
        self._fresh()

    def _fresh(self):
        """What is kept in memory (none of it yet)."""
        self._pos = OrderedDict()  # time index -> (x, y, z) km of every parcel
        self._traj = OrderedDict()  # (set key, name) -> (nt, n) array
        self._traj_bytes = 0
        self._lattice = False  # (not detected yet; None: no lattice)
        self._chosen = OrderedDict()  # json rule -> ParcelSet (chosen())
        self._run = self._fields = None  # the run's 3D output (for_run): "@" variables

    def __repr__(self):
        return f"ParcelFile({self.n} parcels, {len(self.times)} times, {len(self.paths)} file(s))"

    @property
    def nt(self):
        return len(self.times)

    # ------------------------------------------------------------------ variables
    def attach(self, fields):
        """The run's Fields, whose 3D fields "@<field>" samples along trajectories."""
        self._run, self._fields = fields.run, fields

    @property
    def fields(self):
        if self._fields is None and self._run is not None:
            from .fields import Fields
            self._fields = Fields(self._run)
        return self._fields

    def has(self, name):
        """Whether `name` is a parcel variable: in the output, or "@<field>" of a 3D
        field of the run (not a column field)."""
        f = grid_field(name)
        if not f:
            return name in self.vars or self.computed(name)
        F = self.fields
        return F is not None and f in F and F[f].ndim == 3 and not F[f].column

    def computed(self, name):
        """Whether `name` is computed along the trajectories (ALONG; the output has
        what it needs and no variable of that name)."""
        return name in ALONG and name not in self.vars \
            and all(n in self.vars for n in ALONG[name][0])

    def has_budget(self):
        """Whether the output has what the w budget needs (w, b, vpg)."""
        return all(n in self.vars for n in BUDGET_NEEDS)

    def units(self, name):
        f = grid_field(name)
        if f:
            return self.fields[f].units
        if self.computed(name):
            u = self.vars["w"][1]
            return f"{u}/s" if u else "1/s"
        return "km" if name in POS else self.vars[name][1]

    def long_name(self, name):
        f = grid_field(name)
        if f:
            return self.fields[f].label
        return ALONG[name][2] if self.computed(name) else self.vars[name][0]

    def title(self, name):
        """Axis / colour bar title: "w (m/s)"; a gridded field's own label."""
        f = grid_field(name)
        lab = f"{self.fields[f].label} at the parcels" if f else var_label(name)
        u = self.units(name)
        return f"{lab} ({u})" if u else lab

    def grid_names(self):
        """{label: "@<field>"} of the 3D fields that can be sampled along trajectories."""
        F = self.fields
        if F is None:
            return {}
        return {f"{d.label} [{d.name}]": GRID + d.name for d in F.defs.values()
                if d.ndim == 3 and not d.column}

    # ------------------------------------------------------------------ times
    def index_before(self, t, tol=0.5):
        """The last parcel time index at or before model time t (s); None before the first."""
        i = int(np.searchsorted(self.times, float(t) + tol, side="right")) - 1
        return i if i >= 0 else None

    def nearest(self, t):
        """The parcel time index nearest model time t (s)."""
        return int(np.argmin(np.abs(self.times - float(t))))

    def bracket(self, t, tol=0.5):
        """(i0, i1, w) with value(t) = (1-w) value[i0] + w value[i1]; None outside the
        parcel times."""
        t = float(t)
        if not self.nt or t < self.times[0] - tol or t > self.times[-1] + tol:
            return None
        i = self.nearest(t)
        if abs(self.times[i] - t) <= tol:
            return i, i, 0.0
        i1 = int(np.searchsorted(self.times, t))  # (strictly inside: 0 < i1 < nt)
        i0 = i1 - 1
        return i0, i1, float((t - self.times[i0]) / (self.times[i1] - self.times[i0]))

    def window(self, t, mode="all", minutes=None):
        """Slice of parcel time indices for a tail drawn at model time t (s): 'all'
        times, 'until' t, or the 'last' `minutes` before t."""
        if mode == "all":
            return slice(0, self.nt)
        i = self.index_before(t)
        if i is None:
            return slice(0, 0)
        if mode == "last":
            i0 = int(np.searchsorted(self.times, float(t) - 60.0 * float(minutes or 0) - 0.5))
            return slice(i0, i + 1)
        return slice(0, i + 1)

    # ------------------------------------------------------------------ reads
    def _clean(self, a):
        bad = np.abs(a) >= MISSING_ABS
        if self.missing is not None:
            bad |= a == self.missing
        a[bad] = np.nan
        return a

    def read(self, name, ids=None, times=None):
        """Values of variable `name`: (nt, len(ids)) for a range of times (slice or
        None: all), (len(ids),) for one time index.  ids: parcel indices (0-based, any
        order; None: all).  Missing values are NaN; x, y, z in km."""
        if name not in self.vars:
            raise KeyError(f"{name} is not in the parcel output")
        one = isinstance(times, (int, np.integer))
        if one:
            ta, tb = int(times), int(times) + 1
        else:
            ta, tb, _ = (times or slice(None)).indices(self.nt)
        if ids is None:
            uniq, back = None, None
            runs, ncol = [(0, self.n)], self.n
        else:
            ids = np.asarray(ids, dtype=np.int64).ravel()
            if len(ids) and (ids.min() < 0 or ids.max() >= self.n):
                raise IndexError("parcel index out of range")
            uniq, back = np.unique(ids, return_inverse=True)
            runs, ncol = _id_runs(uniq), len(uniq)
        out = np.full((max(tb - ta, 0), ncol), np.nan, dtype=np.float32)
        col = 0
        for lo, hi in runs:
            want = None if uniq is None else uniq[(uniq >= lo) & (uniq < hi)] - lo
            for p, l0, l1, g0 in self.segments:
                a, b = max(ta, g0), min(tb, g0 + l1 - l0)
                if a >= b:
                    continue
                step = max(1, BLOCK // (4 * (hi - lo)))
                for s in range(a, b, step):
                    e = min(b, s + step)
                    with IO_LOCK, netCDF4.Dataset(p) as d:
                        d.set_auto_mask(False)
                        v = d[name]
                        idx = (slice(s - g0 + l0, e - g0 + l0),) + (0,) * (v.ndim - 2) \
                            + (slice(lo, hi),)
                        blk = np.asarray(v[idx], dtype=np.float32)
                    out[s - ta:e - ta, col:col + (hi - lo if want is None else len(want))] = \
                        blk if want is None else blk[:, want]
            col += hi - lo if want is None else len(want)
        self._clean(out)
        if name in POS:
            out *= np.float32(0.001)
        if back is not None:
            out = out[:, back]
        return out[0] if one else out

    def positions(self, ti):
        """(x, y, z) km of every parcel at time index ti (the last few kept)."""
        ti = int(ti)
        with _lock:
            hit = self._pos.get(ti)
            if hit is not None:
                self._pos.move_to_end(ti)
                return hit
        xyz = tuple(self.read(n, None, ti) for n in POS)
        with _lock:
            self._pos[ti] = xyz
            while len(self._pos) > 2:
                self._pos.popitem(last=False)
        return xyz

    # ------------------------------------------------------------------ lattice
    def lattice(self):
        """The seeding lattice at the first parcel time, or None: dict x0, dx, nx, y0,
        dy, ny, z0, dz, nz (km), parcel index = i + nx (j + ny k).  Cached on disk."""
        if self._lattice is not False:
            return self._lattice
        path = os.path.join(cache_dir(), f"lattice-{self.sig}.json")
        try:
            with open(path) as f:
                self._lattice = json.load(f)["lattice"]
            return self._lattice
        except (OSError, ValueError, KeyError):
            pass
        self._lattice = _detect_lattice(*self.positions(0)) if self.nt else None
        try:
            os.makedirs(cache_dir(), exist_ok=True)
            tmp = temp_name(path)
            with open(tmp, "w") as f:
                json.dump({"lattice": self._lattice}, f)
            os.replace(tmp, path)
        except OSError:
            pass
        return self._lattice

    # ------------------------------------------------------------------ trajectories
    def ready(self, pset, names):
        """Whether the trajectories of `names` are in memory (trajectories is quick)."""
        return all((pset.key, n) in self._traj for n in names)

    def trajectories(self, pset, names=POS, progress=None):
        """{name: (nt, len(pset)) float32} at every parcel time, columns in pset.ids
        order; "@<field>" names are sampled from the 3D output (progress(done, total)
        is told of each 3D time).  Kept in memory (up to ~1 GB) and in the cache
        folder."""
        out = {}
        for name in names:
            key = (pset.key, name)
            with _lock:
                a = self._traj.get(key)
                if a is not None:
                    self._traj.move_to_end(key)
            if a is None and self.computed(name):  # (quick: in memory only)
                a = self._along(pset, name)
                self._remember(key, a)
            if a is None:
                f = grid_field(name)
                if f and not self.has(name):
                    raise KeyError(f"{f} is not a 3D field of this run")
                tag = "grid-" + re.sub(r"[^\w.,-]+", "_", f) + "-" + self._grid_sig() \
                    if f else name
                path = os.path.join(cache_dir(), f"traj-{self.sig}-{pset.key}-{tag}.npy")
                try:
                    a = np.load(path)
                    if a.shape != (self.nt, len(pset)):
                        a = None
                except (OSError, ValueError):
                    a = None
                if a is None:
                    a = self._sample(pset, f, progress) if f else self.read(name, pset.ids)
                    try:
                        os.makedirs(cache_dir(), exist_ok=True)
                        tmp = temp_name(path, ".tmp.npy")
                        np.save(tmp, a)
                        os.replace(tmp, path)
                    except OSError:
                        pass
                self._remember(key, a)
            out[name] = a
        return out

    def _along(self, pset, name):
        """(nt, len(pset)) of a variable computed along the trajectories (ALONG)."""
        tr = self.trajectories(pset, ALONG[name][0])
        a = d_dt(self.times, tr["w"])
        if name == "wres":
            a = a - tr["b"] - tr["vpg"]
        return a.astype(np.float32)

    def _grid_sig(self):
        """The run's 3D files (names, sizes, times written) and times, as a short hash."""
        run = self._run
        return hashlib.sha1(json.dumps(
            [run.path, [float(t) for t in run.times]]
            + [(os.path.basename(p), os.path.getsize(p), int(os.path.getmtime(p)))
               for p in run.files]).encode()).hexdigest()[:12]

    def time_weights(self, times, tol=0.5):
        """{3D time index k: (parcel time indices, weights)}: a parcel time's value is
        the sum over the k it appears under of weight × the field at time k (linear in
        time between the 3D outputs around it).  Parcel times outside them: absent."""
        T = np.asarray(times, dtype=np.float64)
        out = {}
        if not len(T):
            return out
        for i, t in enumerate(self.times):
            if t < T[0] - tol or t > T[-1] + tol:
                continue
            k1 = int(np.clip(np.searchsorted(T, t - tol), 0, len(T) - 1))
            if abs(T[k1] - t) <= tol:
                pairs = ((k1, 1.0),)
            else:
                k0 = k1 - 1
                w = float((t - T[k0]) / (T[k1] - T[k0]))
                pairs = ((k0, 1.0 - w), (k1, w))
            for k, w in pairs:
                ii, ww = out.setdefault(k, ([], []))
                ii.append(i)
                ww.append(w)
        return {k: (np.asarray(ii, np.int64), np.asarray(ww, np.float32))
                for k, (ii, ww) in sorted(out.items())}

    def _sample(self, pset, field, progress=None):
        """(nt, len(pset)) of 3D field `field` at the parcels' positions (module doc)."""
        from .volume3d import sample_points
        F = self.fields
        run = F.run
        tr = self.trajectories(pset, POS)
        out = np.full((self.nt, len(pset)), np.nan, dtype=np.float32)
        wts = self.time_weights(run.times)
        if not len(pset) or not wts:
            return out
        acc = np.zeros(out.shape, dtype=np.float32)
        seen = np.zeros(self.nt, dtype=bool)

        def at(item):  # (the field at the parcels' positions around 3D output k)
            k, (ii, _) = item
            x, y, z = (tr[c][ii] for c in POS)
            ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            vals = np.full(x.shape, np.nan, dtype=np.float32)
            if ok.any() and (run.terrain or F.fits([field], k)):
                vals[ok] = F.at_points(field, k, lambda vol: sample_points(
                    run, vol, x[ok], y[ok], z[ok], k))
            elif ok.any():  # (too large for the 3D cache: the columns around them)
                vals[ok] = F.at_levels(
                    field, k, (x[ok] - run.xh[0]) / (run.dx / 1000.0),
                    (y[ok] - run.yh[0]) / (run.dy / 1000.0),
                    np.interp(z[ok], run.z, np.arange(run.nk, dtype=np.float64)))
            return vals

        # several 3D outputs at once where their volumes are small, added in their order
        width = ahead_width(run, F.read_bytes(field))
        for n, ((k, (ii, ww)), vals) in enumerate(ahead(at, wts.items(), width)):
            acc[ii] += ww[:, None] * vals
            seen[ii] = True
            if progress is not None:
                progress(n + 1, len(wts))
        out[seen] = acc[seen]
        return out

    def _remember(self, key, a):
        with _lock:
            if key not in self._traj:
                self._traj[key] = a
                self._traj_bytes += a.nbytes
            while self._traj_bytes > 1024**3 and len(self._traj) > 1:
                self._traj_bytes -= self._traj.popitem(last=False)[1].nbytes


def _detect_lattice(x, y, z):
    """Lattice parameters if parcel k sits at (x0 + i dx, y0 + j dy, z0 + l dz) with
    k = i + nx (j + ny l), else None."""
    n = len(x)
    if n < 2 or not (np.isfinite(x).all() and np.isfinite(y).all() and np.isfinite(z).all()):
        return None
    yz = np.flatnonzero((y != y[0]) | (z != z[0]))
    nx = int(yz[0]) if len(yz) else n
    zz = np.flatnonzero(z != z[0])
    nxy = int(zz[0]) if len(zz) else n
    if nxy % nx or n % nxy:
        return None
    ny, nz = nxy // nx, n // nxy
    k = np.arange(n)
    lat = dict(x0=float(x[0]), dx=float(x[nx - 1] - x[0]) / max(nx - 1, 1), nx=nx,
               y0=float(y[0]), dy=float(y[nxy - nx] - y[0]) / max(ny - 1, 1), ny=ny,
               z0=float(z[0]), dz=float(z[n - nxy] - z[0]) / max(nz - 1, 1), nz=nz)
    for c, arr, idx, nn in (("x", x, k % nx, nx), ("y", y, (k // nx) % ny, ny),
                            ("z", z, k // nxy, nz)):
        d = lat["d" + c]
        if nn > 1 and d <= 0:
            return None
        tol = 1e-3 * d if d else 1e-6
        if np.max(np.abs(arr - (lat[c + "0"] + d * idx))) > max(tol, 1e-6):
            return None
    return lat


def _lattice_axis(v0, d, n, lo, hi):
    """Indices of lattice points v0 + i d within [lo, hi]."""
    if n == 1 or d == 0:
        return np.arange(1) if lo - 1e-9 <= v0 <= hi + 1e-9 else np.arange(0)
    i0 = int(np.clip(np.ceil((lo - v0) / d - 1e-6), 0, n))
    i1 = int(np.clip(np.floor((hi - v0) / d + 1e-6), -1, n - 1))
    return np.arange(i0, i1 + 1)


def _lattice_pick(lat, box, zr):
    """(ids, x, y, z) of the lattice points in box (x0, x1, y0, y1) and height range."""
    big = (-np.inf, np.inf)
    bx = (box[0], box[1]) if box else big
    by = (box[2], box[3]) if box else big
    i = _lattice_axis(lat["x0"], lat["dx"], lat["nx"], *bx)
    j = _lattice_axis(lat["y0"], lat["dy"], lat["ny"], *by)
    k = _lattice_axis(lat["z0"], lat["dz"], lat["nz"], *(zr or big))
    K, J, I = np.meshgrid(k, j, i, indexing="ij")
    ids = (I + lat["nx"] * (J + lat["ny"] * K)).ravel().astype(np.int64)
    return (ids, (lat["x0"] + lat["dx"] * I).ravel(), (lat["y0"] + lat["dy"] * J).ravel(),
            (lat["z0"] + lat["dz"] * K).ravel())


# ------------------------------------------------------------------ selections
class ParcelSet:
    """Selected parcels: sorted parcel indices, a name, and the rule that chose them
    (`matched` parcels met it before the cap)."""

    def __init__(self, ids, name="parcels", rule=None, matched=None):
        self.ids = np.unique(np.asarray(ids, dtype=np.int64))
        self.name, self.rule = name, dict(rule or {})
        self.matched = len(self.ids) if matched is None else int(matched)
        self.key = hashlib.sha1(self.ids.tobytes()).hexdigest()[:16]

    def __len__(self):
        return len(self.ids)

    def __repr__(self):
        return f"ParcelSet({self.name!r}, {len(self)} of {self.matched})"

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = temp_name(path, ".tmp.npz")
        np.savez_compressed(tmp, ids=self.ids, meta=json.dumps(
            dict(name=self.name, rule=self.rule, matched=self.matched)))
        os.replace(tmp, path)
        return path

    @classmethod
    def load(cls, path):
        with np.load(path) as f:
            meta = json.loads(str(f["meta"]))
            return cls(f["ids"], meta["name"], meta.get("rule"), meta.get("matched"))


def sets_dir(run_path):
    from .. import config
    return config.exports_dir(run_path, "parcels")


def set_path(run_path, name):
    safe = re.sub(r"[^\w.-]+", "_", name).strip("_") or "parcels"
    return os.path.join(sets_dir(run_path), safe + ".npz")


def save_set(run_path, pset):
    return pset.save(set_path(run_path, pset.name))


def list_sets(run_path):
    """Paths of the run's saved parcel sets."""
    return sorted(glob.glob(os.path.join(sets_dir(run_path), "*.npz")))


def normalize(rule):
    """The rule with only the keys that matter, rounded (what a set remembers)."""
    r = {}
    if rule.get("t") is not None:
        r["t"] = round(float(rule["t"]), 3)
    if rule.get("box"):
        x0, x1, y0, y1 = (float(v) for v in rule["box"])
        r["box"] = [round(min(x0, x1), 4), round(max(x0, x1), 4),
                    round(min(y0, y1), 4), round(max(y0, y1), 4)]
    if rule.get("z"):
        r["z"] = sorted(round(float(v), 4) for v in rule["z"])
    if rule.get("near"):
        r["near"] = [round(float(v), 4) for v in rule["near"]]
        if len(r["near"]) not in (3, 4):
            raise ValueError("near is [x, y, r] or [x, y, z, r] (km)")
    w = [dict(var=c["var"], min=None if c.get("min") is None else float(c["min"]),
              max=None if c.get("max") is None else float(c["max"]))
         for c in rule.get("where") or ()]
    if w:
        r["where"] = w
    r["cap"] = int(rule.get("cap") or 0)
    r["sample"] = rule.get("sample") or "stride"
    if r["sample"] not in ("stride", "random"):
        raise ValueError(f"unknown sample {r['sample']!r}")
    if r["sample"] == "random":
        r["seed"] = int(rule.get("seed") or 0)
    return r


def select(pf, rule, name="parcels"):
    """A ParcelSet of the parcels meeting `rule` at one parcel time:
      t      model time (s), snapped to the nearest parcel time (None: the first)
      box    [x0, x1, y0, y1] km;  z  [z0, z1] km
      near   [x, y, r] (disc) or [x, y, z, r] (ball), km
      where  [{var, min, max}]: value ranges of parcel variables (None: open)
      cap    at most this many (0: all), every n-th (sample 'stride') or a random
             sample ('random', seed)
    Only the parts given apply.  At the first time of a lattice-seeded file the box /
    height / point part reads nothing."""
    r = normalize(rule)
    ti = 0 if r.get("t") is None else pf.nearest(r["t"])
    r["t"] = round(float(pf.times[ti]), 3)
    box, zr, near = r.get("box"), r.get("z"), r.get("near")
    if near:  # its bounding box narrows the candidates first
        nx, ny, rad = near[0], near[1], near[-1]
        nb = [nx - rad, nx + rad, ny - rad, ny + rad]
        box = nb if not box else [max(box[0], nb[0]), min(box[1], nb[1]),
                                  max(box[2], nb[2]), min(box[3], nb[3])]
        if len(near) == 4:
            nz = [near[2] - rad, near[2] + rad]
            zr = nz if not zr else [max(zr[0], nz[0]), min(zr[1], nz[1])]
    lat = pf.lattice() if ti == 0 and (box or zr) else None
    if lat:
        ids, x, y, z = _lattice_pick(lat, box, zr)
    else:
        ids = np.arange(pf.n, dtype=np.int64)
        x = y = z = None
        if box or zr:
            X, Y, Z = pf.positions(ti)
            ok = np.ones(pf.n, dtype=bool)
            if box:
                ok &= (X >= box[0]) & (X <= box[1]) & (Y >= box[2]) & (Y <= box[3])
            if zr:
                ok &= (Z >= zr[0]) & (Z <= zr[1])
            ids, x, y, z = ids[ok], X[ok], Y[ok], Z[ok]
    if near:
        d2 = (x - near[0]) ** 2 + (y - near[1]) ** 2
        if len(near) == 4:
            d2 = d2 + (z - near[2]) ** 2
        ids = ids[d2 <= near[-1] ** 2]
    for c in r.get("where", ()):
        if not len(ids):
            break
        v = pf.read(c["var"], None if len(ids) == pf.n else ids, ti)
        ok = np.isfinite(v)
        if c["min"] is not None:
            ok &= v >= c["min"]
        if c["max"] is not None:
            ok &= v <= c["max"]
        ids = ids[ok]
    ids = np.sort(ids)
    matched = len(ids)
    if r["cap"] and matched > r["cap"]:
        if r["sample"] == "random":
            ids = np.sort(np.random.default_rng(r["seed"]).choice(ids, r["cap"],
                                                                  replace=False))
        else:
            ids = ids[np.linspace(0, matched - 1, r["cap"]).round().astype(np.int64)]
    return ParcelSet(ids, name, r, matched)


def chosen(pf, rule=None, ids=None, name="parcels"):
    """The ParcelSet of `rule` (select; the last few kept, as a figure redraws them at
    every time), or of the parcel indices `ids` without one."""
    if not rule:
        return ParcelSet(ids if ids is not None else [], name)
    key = json.dumps(normalize(rule), sort_keys=True)
    with _lock:
        ps = pf._chosen.get(key)
        if ps is not None:
            pf._chosen.move_to_end(key)
    if ps is None:
        ps = select(pf, rule, name)
        with _lock:
            pf._chosen[key] = ps
            while len(pf._chosen) > 16:
                pf._chosen.popitem(last=False)
    return ParcelSet(ps.ids, name, ps.rule, ps.matched)


def var_choices(pf, first=None, keep=""):
    """{group: {label: name}} for a grouped Select of parcel variables: `first`
    ({label: value}) if given, the output's (mtime aside), and the 3D fields sampled at
    the parcels ("@<field>"); `keep` added when pf lacks it (a spec's own)."""
    out = {"": dict(first)} if first else {}
    if pf is None:
        out["Parcel output"] = {}
    else:
        out["Parcel output"] = {f"{n} ({pf.units(n)})" if pf.units(n) else n: n
                                for n in pf.vars if n != "mtime"}
        along = {f"{ALONG[n][1]} ({pf.units(n)})": n for n in ALONG if pf.computed(n)}
        if along:
            out["w budget (along the parcels)"] = along
        grid = pf.grid_names()
        if grid:
            out["3D fields at the parcels"] = grid
    if keep and not any(keep in g.values() for g in out.values()):
        out["Parcel output"][keep] = keep
    return out


def var_label(name):
    """A parcel variable in a legend or colour bar: "w", "thpert at the parcels"."""
    f = grid_field(name)
    if f:
        return f"{f} at the parcels"
    return ALONG[name][1] if name in ALONG else name


# ------------------------------------------------------------------ along the parcels
def d_dt(times, a):
    """d/dt (per s) of a (nt, ...) along each parcel over the parcel times (centred,
    one-sided at the ends); NaN next to a missing value; all NaN with one time."""
    a = np.asarray(a, dtype=np.float64)
    if len(times) < 2:
        return np.full(a.shape, np.nan)
    return np.gradient(a, np.asarray(times, dtype=np.float64), axis=0)


def ref_index(pf, rule=None):
    """The parcel time index a set's changes are counted from: its rule's time (when it
    was chosen), else the first."""
    t = (rule or {}).get("t")
    return 0 if t is None else pf.nearest(t)


def since(times, a, i0, how):
    """a (nt, ...) as its change since parcel time index i0 ('delta': a - a[i0]) or its
    time integral from there ('int': trapezoids over the parcel times, negative
    before i0); NaN where a parcel was missing on the way from i0."""
    a = np.asarray(a, dtype=np.float64)
    if how == "delta":
        return a - a[i0]
    if how != "int":
        return a
    dt = np.diff(np.asarray(times, dtype=np.float64)).reshape((-1,) + (1,) * (a.ndim - 1))
    # trapezoids, summed outwards from i0: a missing value spoils only the times beyond it
    seg = 0.5 * (a[1:] + a[:-1]) * dt
    out = np.full(a.shape, np.nan)
    out[i0] = np.where(np.isfinite(a[i0]), 0.0, np.nan)
    out[i0 + 1:] = np.cumsum(seg[i0:], axis=0)
    if i0 > 0:
        out[:i0] = -np.cumsum(seg[:i0][::-1], axis=0)[::-1]
    return out


# ------------------------------------------------------------------ drawing helpers
def value_range(arrays):
    """2nd–98th percentile of the finite values (symmetric about 0 when they straddle
    it): the colour range of parcels coloured by a variable."""
    v = np.concatenate([np.asarray(a, dtype=np.float32).ravel() for a in arrays]) \
        if len(arrays) else np.zeros(0, np.float32)
    v = v[np.isfinite(v)]
    if not len(v):
        return 0.0, 1.0
    lo, hi = (float(x) for x in np.percentile(v, [2, 98]))
    if lo < 0 < hi:
        m = max(-lo, hi)
        lo, hi = -m, m
    return (lo, hi) if hi > lo else (lo - 0.5, lo + 0.5)


def thin_times(sl, ncols, budget):
    """Parcel time indices of window sl to draw for ncols parcels: every n-th, so that
    there are at most about `budget` segments, and always the last."""
    a, b = sl.start or 0, sl.stop or 0
    if b - a < 1:
        return np.arange(0)
    every = max(1, int(np.ceil((b - a - 1) * max(ncols, 1) / budget)))
    idx = np.arange(a, b)[::every]
    return idx if idx[-1] == b - 1 else np.append(idx, b - 1)


def joined(x, y, per):
    """(nt-1, n): consecutive points (nt, n) both there and not across a periodic wrap."""
    ok = np.isfinite(x[:-1]) & np.isfinite(x[1:]) & np.isfinite(y[:-1]) & np.isfinite(y[1:])
    px, py = per or (None, None)
    if px:
        ok &= np.abs(x[1:] - x[:-1]) <= 0.5 * px
    if py:
        ok &= np.abs(y[1:] - y[:-1]) <= 0.5 * py
    return ok


def period(run):
    """(Lx, Ly) km of a doubly periodic domain (wbc = sbc = 1); a side that is not
    periodic is None; None when neither is."""
    nml = run.nml
    px = int(nml.get("wbc", 0)) == 1 and int(nml.get("ebc", 0)) == 1
    py = int(nml.get("sbc", 0)) == 1 and int(nml.get("nbc", 0)) == 1
    if not (px or py):
        return None
    return (run.ni * run.dx / 1000.0 if px else None, run.nj * run.dy / 1000.0 if py else None)


def at_time(pf, a, t, interp=True, per=None, axis=None):
    """Values of a trajectory array a (nt, n) at model time t (s): interpolated between
    the parcel times around t (interp) or at the one at or before t.  NaN outside the
    parcel times.  per/axis: the period (km) of a position axis, so a parcel that
    wrapped across the boundary between the two times takes the nearer value."""
    if not interp:
        i = pf.index_before(t)
        return np.full(a.shape[1], np.nan, np.float32) if i is None else a[i]
    b = pf.bracket(t)
    if b is None:
        return np.full(a.shape[1], np.nan, np.float32)
    i0, i1, w = b
    if i0 == i1 or w == 0.0:
        return a[i0]
    out = (1.0 - w) * a[i0] + w * a[i1]
    if per:
        jump = np.abs(a[i1] - a[i0]) > 0.5 * per
        out[jump] = (a[i0] if w < 0.5 else a[i1])[jump]
    return out.astype(np.float32)


# ------------------------------------------------------------------ moving frames
# Trajectories seen from a frame moving with the storm: each point is moved back by how
# far the storm went across the grid between the reference time (the shown or panel
# time) and its parcel time, so at the reference time the parcels are where they are on
# the map, and their tails show the paths relative to the storm.
FRAMES = {"grid": "the grid", "track": "the tracked storm", "motion": "a set motion"}


def frame_shift(pf, run, t_ref, frame="grid", motion=None, fixes=None):
    """How far a frame moving with the storm went across the grid from model time
    t_ref (s) to each parcel time: (dx, dy) km, (nt,) float32 each, or None (the grid
    itself, no motion relative to it, or a track of fewer than two fixes).  frame
    "motion": at the ground-relative motion (u, v) m/s; "track": with the tracked
    storm's centre (fixes {t: fix}, grid km), linear between fixes, and on at the
    motion between the end fixes before the first and after the last."""
    t = np.asarray(pf.times, dtype=np.float64)
    if frame == "motion" and motion is not None:
        u, v = float(motion[0]) - run.umove, float(motion[1]) - run.vmove
        if not (np.isfinite(u) and np.isfinite(v)) or (u == 0.0 and v == 0.0):
            return None
        dt = (t - float(t_ref)) / 1000.0
        return (u * dt).astype(np.float32), (v * dt).astype(np.float32)
    if frame == "track":
        ts = sorted(fixes or {})
        if len(ts) < 2:
            return None
        tt = np.array([run.times[s] for s in ts], dtype=np.float64)

        def at(c, tq):
            out = np.interp(tq, tt, c)
            lo, hi = tq < tt[0], tq > tt[-1]
            out[lo] = c[0] + (tq[lo] - tt[0]) * (c[1] - c[0]) / (tt[1] - tt[0])
            out[hi] = c[-1] + (tq[hi] - tt[-1]) * (c[-1] - c[-2]) / (tt[-1] - tt[-2])
            return out

        ref = np.array([float(t_ref)])
        d = []
        for k in ("x", "y"):
            c = np.array([fixes[s][k] for s in ts], dtype=np.float64)
            d.append((at(c, t) - at(c, ref)[0]).astype(np.float32))
        return tuple(d)
    return None


def frame_label(frame, motion=None):
    """'moving with the tracked storm' / 'moving at (12, 3) m/s' / '' (the grid)."""
    if frame == "track":
        return "moving with the tracked storm"
    if frame == "motion" and motion is not None:
        return f"moving at ({float(motion[0]):g}, {float(motion[1]):g}) m/s"
    return ""


class Shifted:
    """A trajectory position array (nt, n) seen from a moving frame: a[i] - d[i], made
    when read (indexed on the time axis first), so a large set is not copied whole."""

    def __init__(self, a, d):
        self.a, self.d = a, np.asarray(d, dtype=np.float32)
        self.shape, self.dtype, self.ndim = a.shape, a.dtype, a.ndim

    def __len__(self):
        return len(self.a)

    def __getitem__(self, key):
        out = np.asarray(self.a[key])
        d = self.d[key[0] if isinstance(key, tuple) else key]
        if np.ndim(d):
            d = np.reshape(d, np.shape(d) + (1,) * (out.ndim - np.ndim(d)))
        return (out - d).astype(np.float32, copy=False)

    def __array__(self, dtype=None, copy=None):
        a = self[:]
        return a if dtype is None else a.astype(dtype)


def moving(tr, shift):
    """Trajectories tr ({name: (nt, n)}) with x, y in the moving frame of `shift`
    (frame_shift's; None: tr itself)."""
    if shift is None:
        return tr
    return dict(tr, x=Shifted(tr["x"], shift[0]), y=Shifted(tr["y"], shift[1]))


def heads(pf, traj, t, interp=True, per=None):
    """(x, y, z) km of the parcels at model time t (see at_time); per: period(run)."""
    px, py = per or (None, None)
    return (at_time(pf, traj["x"], t, interp, px), at_time(pf, traj["y"], t, interp, py),
            at_time(pf, traj["z"], t, interp))


def polylines(cols, sl=slice(None), per=None):
    """One NaN-separated line through all trajectories, for drawing as a single glyph:
    {name: 1D array} from {name: (nt, n)} (x and y among them) over parcel times sl,
    broken between parcels and where a parcel wraps across a periodic boundary."""
    x, y = cols["x"][sl], cols["y"][sl]
    nt, n = x.shape
    brk = np.zeros((n, max(nt - 1, 0)), dtype=bool)
    px, py = per or (None, None)
    if px:
        brk |= (np.abs(np.diff(x, axis=0)) > 0.5 * px).T
    if py:
        brk |= (np.abs(np.diff(y, axis=0)) > 0.5 * py).T
    p, t = np.nonzero(brk)
    pos = p * (nt + 1) + t + 1
    out = {}
    for name, a in cols.items():
        a = a[sl]
        flat = np.concatenate([a.T, np.full((n, 1), np.nan, np.float32)], axis=1).ravel()
        out[name] = np.insert(flat, pos, np.nan)
    return out


def section_xy(x, y, A, B):
    """(s, d) km of points (x, y) against the section A → B (km): the distance along it
    from A (the section's own axis) and the signed distance off it (+: left of A → B)."""
    (xa, ya), (xb, yb) = A, B
    L = max(float(np.hypot(xb - xa, yb - ya)), 1e-9)
    ex, ey = (xb - xa) / L, (yb - ya) / L
    dx, dy = np.asarray(x) - xa, np.asarray(y) - ya
    return dx * ex + dy * ey, dy * ex - dx * ey


# ------------------------------------------------------------------ export
EXPORT_SKIP = ("mtime",)  # (not written unless asked for)
EXPORT_FORMATS = {".nc": "netCDF", ".csv": "CSV"}
SR = ("x_sr", "y_sr")  # (x, y in a moving frame, when an export is given one)


def export_names(pf, names=None):
    """The variables an export writes: x, y, z, then `names` (None: every variable of
    the output but mtime; "@<field>": a 3D field sampled at the parcels)."""
    names = [n for n in pf.vars if n not in EXPORT_SKIP] if names is None else list(names)
    bad = [n for n in names if not pf.has(n)]
    if bad:
        raise ValueError(f"not parcel variables: {', '.join(bad)}")
    return list(POS) + [n for n in dict.fromkeys(names) if n not in POS]


def export_column(name):
    """The netCDF variable / CSV column of a parcel variable ('@thpert' ->
    'thpert_at_parcels')."""
    from .export import var_name
    f = grid_field(name)
    return var_name(f) + "_at_parcels" if f else var_name(name)


def export_times(pf, t0=None, t1=None, every=1):
    """Parcel time indices from model time t0 to t1 (s; None: the first / last parcel
    time), each end snapped to the nearest parcel time, every `every`-th."""
    a = 0 if t0 is None else pf.nearest(t0)
    b = pf.nt - 1 if t1 is None else pf.nearest(t1)
    return np.arange(min(a, b), max(a, b) + 1, max(1, int(every)), dtype=np.int64)


def export_format(path):
    """'netCDF' or 'CSV', from the file's extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in EXPORT_FORMATS:
        raise ValueError(f"{path}: a parcel export is .nc (netCDF) or .csv")
    return EXPORT_FORMATS[ext]


def export_bytes(pset, names, nt, fmt="netCDF"):
    """About how large an export is (before compression)."""
    vals = len(pset) * int(nt) * len(names)
    return 4 * vals if fmt == "netCDF" else 11 * (vals + 2 * len(pset) * int(nt))


def export_path(run_path, pset, ext=".nc"):
    """<exports folder>/<run>/parcels/<set name>.nc (next to the saved sets)."""
    return set_path(run_path, pset.name)[:-4] + ext


def export_set(pf, pset, path, names=None, times=None, compress=True, progress=None,
               cancelled=None, shift=None, frame=""):
    """Write the set's trajectories to `path`: netCDF (.nc) with dimensions time and
    parcel, every variable (time, parcel) as CM1 writes them, or CSV (.csv) with one
    row per parcel and time it has a position at (# lines first: the set, units).
    names: see export_names; times: parcel time indices (None: all; export_times).
    Positions in km (x, y grid-relative, z above sea level); "parcel" is CM1's parcel
    number (1..n, the parcel output's own), the set's index + 1.  progress(done,
    total, text) after each variable of each block of parcels; cancelled() is asked
    between them, and a stopped export leaves no file.  shift: frame_shift's (dx, dy)
    over all parcel times, to write x_sr, y_sr too (x, y in that moving frame; frame:
    what it is, frame_label's, and its reference time).  Returns dict(path, format,
    parcels, times, cancelled)."""
    from .. import config
    fmt = export_format(path)
    names = export_names(pf, names)
    cols_out = names + (list(SR) if shift is not None else [])
    ti = np.arange(pf.nt, dtype=np.int64) if times is None else \
        np.asarray(times, dtype=np.int64).ravel()
    if not len(pset) or not len(ti):
        raise ValueError("nothing to export: no parcels" if not len(pset) else
                         "nothing to export: no times")
    path = config.expand(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    span = slice(int(ti.min()), int(ti.max()) + 1)
    sub = ti - span.start
    # the parcels in blocks of at most BLOCK bytes of all variables (whole trajectories
    # of the set, when they are cached or small, or for fields sampled from the 3D output
    # and the w budget's)
    grid = [n for n in names if grid_field(n) or pf.computed(n)]
    whole = {n: None for n in names}
    if grid or len(pset) * (span.stop - span.start) * len(cols_out) * 4 <= BLOCK:
        per = len(pset)
    else:
        per = max(1, BLOCK // (4 * (span.stop - span.start) * len(cols_out)))
    blocks = [(a, min(a + per, len(pset))) for a in range(0, len(pset), per)]
    total, done = len(blocks) * len(cols_out), [0]
    got = {}  # (x, y of the block, for x_sr, y_sr)

    def values(name, a, b):
        if name in SR:
            k = SR.index(name)
            return got.pop(POS[k]) - shift[k][ti][:, None]
        out = _values(name, a, b)
        if shift is not None and name in POS[:2]:
            got[name] = out
        return out

    def _values(name, a, b):
        if per == len(pset) or pf.ready(pset, [name]):
            if whole[name] is None:
                whole[name] = pf.trajectories(pset, [name])[name]
            return whole[name][span][sub, a:b]
        return pf.read(name, pset.ids[a:b], span)[sub]

    def stop():
        return cancelled is not None and cancelled()

    part = path + ".part"
    stopped = False
    try:
        if fmt == "netCDF":
            ds = netCDF4.Dataset(part, "w", format="NETCDF4")
            try:
                _export_header(ds, pf, pset, names, ti, compress, shift, frame)
                for a, b in blocks:
                    for n in cols_out:
                        if stop():
                            stopped = True
                            break
                        ds[export_column(n)][:, a:b] = values(n, a, b)
                        done[0] += 1
                        if progress is not None:
                            progress(done[0], total, f"{n}, parcels {a + 1}–{b}")
                    if stopped:
                        break
            finally:
                ds.close()
        else:
            with open(part, "w") as f:
                for line in _export_notes(pf, pset, names, ti, frame if shift else ""):
                    f.write(f"# {line}\n")
                f.write(",".join(["parcel", "time_s"] + [
                    export_column(n) + ("_km" if n in POS + SR else "")
                    for n in cols_out]) + "\n")
                fmt_row = ["%d", "%.10g"] + ["%.7g"] * len(cols_out)
                for a, b in blocks:
                    cols = []
                    for n in cols_out:
                        if stop():
                            stopped = True
                            break
                        cols.append(values(n, a, b).T.ravel())  # (parcel-major)
                        done[0] += 1
                        if progress is not None:
                            progress(done[0], total, f"{n}, parcels {a + 1}–{b}")
                    if stopped:
                        break
                    pid = np.repeat(pset.ids[a:b] + 1, len(ti))
                    t = np.tile(pf.times[ti], b - a)
                    keep = np.isfinite(cols[0]) & np.isfinite(cols[1])
                    rows = np.column_stack([pid, t] + cols)[keep]
                    np.savetxt(f, rows, fmt=fmt_row, delimiter=",")
    except BaseException:
        _remove(part)
        raise
    if stopped:
        _remove(part)
    else:
        os.replace(part, path)
    return dict(path=path, format=fmt, parcels=len(pset), times=len(ti), cancelled=stopped)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _export_notes(pf, pset, names, ti, frame=""):
    """What an export holds, one line each (CSV # lines; netCDF attributes say it too)."""
    run = pf._run
    per = period(run) if run is not None else None
    lines = [
        f"cm1view parcel set {pset.name!r}: {len(pset)} parcels"
        + (f" (of {pset.matched} chosen by the rule)" if pset.matched > len(pset) else ""),
        f"rule: {json.dumps(pset.rule, sort_keys=True)}" if pset.rule else
        "rule: none (parcels given by number)",
        f"parcel output: {', '.join(pf.paths)}",
        f"times: {len(ti)} parcel times, {pf.times[ti[0]]:g} to {pf.times[ti[-1]]:g} s",
        "parcel: CM1's parcel number (1..n); x, y km grid-relative, z km above sea level; "
        "nan: no value (the parcel left the domain, or missing)",
        "units: " + ", ".join(f"{export_column(n)} {pf.units(n) or '1'}" for n in names),
    ]
    if frame:
        lines.append(f"x_sr, y_sr: x, y km in a frame {frame}")
    if any(grid_field(n) for n in names):
        lines.append("<field>_at_parcels: the run's 3D field at the parcels, trilinear in "
                     "space, linear in time between 3D outputs (nan outside them)")
    if any(pf.computed(n) for n in names):
        lines.append("dwdt, wres: Dw/Dt along the parcel (centred differences of its w over "
                     "the parcel times) and Dw/Dt - b - vpg")
    if per:
        lines.append("periodic: x, y jump by the domain length where a parcel wraps "
                     f"(period {', '.join('-' if p is None else f'{p:g} km' for p in per)})")
    return lines


def _export_header(ds, pf, pset, names, ti, compress, shift=None, frame=""):
    """Dimensions, coordinates, global attributes and the (empty) variables."""
    import datetime
    from .. import __version__
    from .export import cf_units
    run = pf._run
    nt, n = len(ti), len(pset)
    ds.createDimension("time", nt)
    ds.createDimension("parcel", n)
    v = ds.createVariable("time", "f8", ("time",))
    v.setncatts(dict(long_name="model time", units="s", axis="T"))
    v[:] = pf.times[ti]
    v = ds.createVariable("parcel", "i4", ("parcel",))
    v.setncatts(dict(long_name="parcel number in the parcel output (CM1's, 1..n)"))
    v[:] = pset.ids + 1
    chunks = (nt, max(1, min(n, (1 << 20) // nt)))
    for name in names:
        u = pf.units(name)
        v = ds.createVariable(export_column(name), "f4", ("time", "parcel"),
                              fill_value=np.float32(np.nan), zlib=compress, complevel=1,
                              shuffle=compress, chunksizes=chunks)
        a = dict(long_name=pf.long_name(name) + (" at the parcels" if grid_field(name)
                                                 else ""),
                 units=cf_units(u), cm1view_name=name)
        if cf_units(u) != (u or "1"):
            a["units_shown"] = u
        if grid_field(name):
            a["comment"] = ("the run's 3D field at the parcels: trilinear in space, "
                            "linear in time between 3D outputs (NaN outside them)")
        v.setncatts(a)
    for c, ax in (("x", "X"), ("y", "Y")):
        ds[c].setncatts(dict(axis=ax, comment="grid-relative"))
    ds["z"].setncatts(dict(positive="up", comment="above sea level"))
    for c in SR if shift is not None else ():
        v = ds.createVariable(c, "f4", ("time", "parcel"), fill_value=np.float32(np.nan),
                              zlib=compress, complevel=1, shuffle=compress, chunksizes=chunks)
        v.setncatts(dict(long_name=f"{c[0]} in a frame {frame}", units="km",
                         comment=f"{c[0]} minus how far the frame moved across the grid "
                                 "since its reference time"))
    notes = _export_notes(pf, pset, names, ti, frame if shift is not None else "")
    atts = {
        "Conventions": "CF-1.8",
        "title": f"cm1view parcel set {pset.name}",
        "source": f"CM1 parcel output {', '.join(pf.paths)}",
        "history": f"{datetime.datetime.now().isoformat(timespec='seconds')} "
                   f"cm1view {__version__} parcel export",
        "cm1view_version": __version__,
        "cm1view_set": pset.name,
        "cm1view_rule": json.dumps(pset.rule, sort_keys=True),
        "cm1view_matched": np.int64(pset.matched),
        "comment": "; ".join(notes[4:]),
    }
    if run is not None:
        atts.update(cm1view_run=run.path, umove=run.umove, vmove=run.vmove)
        per = period(run)
        if per:
            atts["cm1view_period_km"] = np.array([np.nan if p is None else p for p in per])
    ds.setncatts(atts)
