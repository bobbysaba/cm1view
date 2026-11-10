"""Trajectories traced through the 3D winds, for runs whose model writes no parcel
output (WoFS: run.traced_parcels).

Seeding.  A lattice at the first output time: every `step` grid columns across the
domain (about SEEDS_ACROSS of them along the longer side), and in height every DZ_KM
from Z0_KM above the lowest ground up to TOP_KM, or less where the model top is lower
(heights above sea level, as parcel z always is).  On a terrain run the seeds under
the ground are missing throughout.

Tracing.  Midpoint (RK2) steps of at most MAX_DT s in x, y, z (km), with the
grid-relative winds (uinterp, vinterp, winterp) trilinear in space, each output's
taken at its own level heights (a terrain run's columns: run.heights(t, "msl")), and
linear in time between two outputs.  A parcel stays between the lowest and highest
levels of its column (sliding along them) and is missing once it leaves the domain
sideways.  Positions and the winds at them are kept at the output times only, so the
parcel times are the 3D times.

Storage.  A file in the layout of CM1's cm1out_pdata.nc (time, xh = parcel; x, y, z in
m, z above sea level; u, v, w in m/s) in the cache folder (parcels/), named by the
run's files and the seeding, so it is traced once.  Traced (a ParcelFile) reads it
with the same code as CM1's parcel output, and traces it on the first read.

Too coarse.  Between outputs far apart the winds' blend is a poor guess, so a run whose
output comes less often (median interval) than the traj_max_interval setting gets no
trajectories; off(run) says why in plain words."""

import hashlib
import json
import os
import threading

import netCDF4
import numpy as np
from scipy.ndimage import map_coordinates

from . import parcels as P
from .run import IO_LOCK, ahead, ahead_width, temp_name
from .volume3d import _fij, columns, frac_level

VERSION = 1  # (part of the file's name: bump when tracing changes)
SEEDS_ACROSS = 60  # seeds along the longer side of the domain
DZ_KM, Z0_KM, TOP_KM = 0.5, 0.25, 15.0  # seed heights (km above the lowest ground)
MAX_DT = 60.0  # s, the longest step
MISSING = -1.0e30  # (as CM1 writes parcels that left the domain)
WINDS = ("uinterp", "vinterp", "winterp")
VARS = {"x": ("x position (traced)", "m"), "y": ("y position (traced)", "m"),
        "z": ("height above sea level (traced)", "m"), "u": ("u (grid-relative)", "m/s"),
        "v": ("v (grid-relative)", "m/s"), "w": ("w", "m/s")}


def interval(run):
    """The run's output interval (s): the median time between outputs (0 with one)."""
    t = np.asarray(run.times, np.float64)
    return float(np.median(np.diff(t))) if len(t) > 1 else 0.0


def off(run):
    """Why the run gets no traced trajectories ("" when it does)."""
    from .. import config
    if len(run.times) < 2:
        return "Trajectories need at least two output times; this run has one."
    if not all(n in run.vars for n in WINDS):
        return "Trajectories need the 3D winds, which this run's output lacks."
    lim = config.get("traj_max_interval")
    dt = interval(run)
    if lim and dt > float(lim):
        return (f"Trajectories are off for this run: its output comes every {dt:g} s, "
                f"less often than every {float(lim):g} s (Settings: Longest output "
                f"interval for trajectories). Between outputs that far apart the winds "
                f"are too poorly known to follow a parcel.")
    return ""


def lattice(run):
    """The seeding lattice: dict x0, dx, nx, y0, dy, ny, z0, dz, nz (km; z above sea
    level), parcel index = i + nx (j + ny k), as ParcelFile.lattice gives it."""
    step = max(1, int(np.ceil(max(run.ni, run.nj) / SEEDS_ACROSS)))
    i = np.arange(step // 2, run.ni, step)
    j = np.arange(step // 2, run.nj, step)
    g = float(np.min(run.terrain_height())) if run.terrain else 0.0
    z0 = g + max(Z0_KM, float(run.z[0]))
    top = min(g + TOP_KM, g + float(run.z[-1]) - DZ_KM)
    nz = max(1, int(np.floor((top - z0) / DZ_KM + 1e-6)) + 1)
    return dict(x0=float(run.xh[i[0]]), dx=step * run.dx / 1000.0, nx=len(i),
                y0=float(run.yh[j[0]]), dy=step * run.dy / 1000.0, ny=len(j),
                z0=round(z0, 6), dz=DZ_KM, nz=nz)


def seeds(lat):
    """(n, 3) seed positions (km) of a lattice, in parcel order."""
    K, J, I = np.meshgrid(np.arange(lat["nz"]), np.arange(lat["ny"]), np.arange(lat["nx"]),
                          indexing="ij")
    return np.stack([lat["x0"] + lat["dx"] * I.ravel(), lat["y0"] + lat["dy"] * J.ravel(),
                     lat["z0"] + lat["dz"] * K.ravel()], axis=1)


def signature(run):
    """What the traced file depends on (run, its files and times, the seeding), short."""
    files = []
    for p in run.files:
        try:
            files.append((p, os.path.getsize(p), int(os.path.getmtime(p))))
        except OSError:
            files.append((p, -1, -1))
    return hashlib.sha1(json.dumps(
        [VERSION, run.path, [float(t) for t in run.times], files, lattice(run), MAX_DT]
    ).encode()).hexdigest()[:16]


class _Winds:
    """The winds (and a terrain run's level heights) at one output time."""

    def __init__(self, run, t):
        names = list(WINDS) + (["zmsl"] if run.terrain and "zmsl" in run.vars else [])
        run.load_volumes(names, t)
        self.run = run
        self.U, self.V, self.W = (run.volume(n, t) for n in WINDS)
        self.H = run.heights(t, "msl") if run.terrain else None

    def at(self, p):
        """(u, v, w) (n, 3) m/s at points p (n, 3) km, and the lowest and highest level
        heights (km) of their columns."""
        run = self.run
        fi, fj = _fij(run, p[:, 0], p[:, 1])
        if self.H is None:
            z = np.asarray(run.z, np.float64)
            fk = np.interp(p[:, 2], z, np.arange(run.nk, dtype=np.float64))
            lo, hi = np.full(len(p), z[0]), np.full(len(p), z[-1])
        else:
            Hc = columns(self.H, fi, fj)
            fk = frac_level(Hc, p[:, 2])
            lo, hi = Hc[:, 0], Hc[:, -1]
        c = np.stack([fk, fj, fi])
        uvw = np.stack([map_coordinates(a, c, order=1, mode="nearest")
                        for a in (self.U, self.V, self.W)], axis=1)
        return uvw.astype(np.float64), lo, hi


def trace(run, lat, progress=None, cancelled=None):
    """{name: (nt, n) float32} of VARS at every output time (km for positions here;
    NaN: missing) for the parcels seeded on lattice lat at the first output time."""
    nt = len(run.times)
    p = seeds(lat)
    n = len(p)
    out = {k: np.full((nt, n), np.nan, np.float32) for k in VARS}
    xlo, xhi = float(run.xh[0]), float(run.xh[-1])
    ylo, yhi = float(run.yh[0]), float(run.yh[-1])
    w0 = _Winds(run, 0)
    uvw, lo, hi = w0.at(p)
    alive = p[:, 2] >= lo - 1e-9  # (on a terrain run: seeds under the ground are not)
    p[:, 2] = np.clip(p[:, 2], lo, hi)

    def keep(k, p, uvw):
        for c, a in (("x", p[:, 0]), ("y", p[:, 1]), ("z", p[:, 2]), ("u", uvw[:, 0]),
                     ("v", uvw[:, 1]), ("w", uvw[:, 2])):
            out[c][k] = np.where(alive, a, np.nan)

    keep(0, p, uvw)
    # the next output's winds are read while a step is integrated, when three outputs'
    # winds (the two of the step and the next) fit in half the 3D cache
    nbytes = 4 * run.nk * run.nj * run.ni * (len(WINDS) + (w0.H is not None))
    fits = 3 * nbytes <= getattr(run, "cache_bytes", 0) // 2
    winds = ahead(lambda k: _Winds(run, k), range(1, nt),
                  min(1, ahead_width(run)) if fits else 0)
    for k in range(nt - 1):
        if cancelled is not None and cancelled():
            winds.close()
            return None
        _, w1 = next(winds)
        T = float(run.times[k + 1] - run.times[k])
        m = max(1, int(np.ceil(T / MAX_DT)))
        dt = T / m

        def vel(q, a):  # winds (km/s) at time fraction a of the interval, and bounds
            u0, l0, h0 = w0.at(q)
            u1, l1, h1 = w1.at(q)
            return (((1 - a) * u0 + a * u1) / 1000.0, (1 - a) * l0 + a * l1,
                    (1 - a) * h0 + a * h1)

        for s in range(m):
            a = s / m
            v1, _, _ = vel(p, a)
            mid = p + 0.5 * dt * v1
            v2, lo, hi = vel(mid, a + 0.5 / m)
            q = p + dt * v2
            _, lo, hi = vel(q, (s + 1) / m)
            q[:, 2] = np.clip(q[:, 2], lo, hi)  # (slides along the lowest / top level)
            gone = (q[:, 0] < xlo) | (q[:, 0] > xhi) | (q[:, 1] < ylo) | (q[:, 1] > yhi)
            alive &= ~gone & np.isfinite(q).all(axis=1)
            p = np.where(alive[:, None], q, p)
        uvw, _, _ = w1.at(p)
        keep(k + 1, p, uvw)
        w0 = w1
        if progress is not None:
            progress(k + 1, nt - 1)
    return out


def write(path, times, out):
    """Write traced trajectories (trace's, km) in the cm1out_pdata.nc layout."""
    nt, n = out["x"].shape
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = temp_name(path)
    with IO_LOCK, netCDF4.Dataset(tmp, "w", format="NETCDF4") as d:
        d.createDimension("time", None)
        d.createDimension("xh", n)
        d.setncatts(dict(missing_value=np.float32(MISSING),
                         source="traced by cm1view through the 3D winds"))
        tv = d.createVariable("time", "f8", ("time",))
        tv.units = "s"
        tv[:] = np.asarray(times, np.float64)
        for name, (long_name, units) in VARS.items():
            a = np.asarray(out[name], np.float32)
            if name in P.POS:
                a = a * np.float32(1000.0)
            v = d.createVariable(name, "f4", ("time", "xh"), chunksizes=(1, n))
            v.long_name, v.units = long_name, units
            v[:] = np.where(np.isfinite(a), a, np.float32(MISSING))
    os.replace(tmp, path)
    return path


class Traced(P.ParcelFile):
    """A run's traced trajectories, read like CM1's parcel output.  Made without
    reading anything; traced (once: kept in the cache folder) on the first read."""

    def __init__(self, run, sig=None):
        self.src = run
        self.lat = lattice(run)
        self.sig = sig or signature(run)
        self.n, self.dim = self.lat["nx"] * self.lat["ny"] * self.lat["nz"], "xh"
        self.vars = dict(VARS)
        self.missing = np.float32(MISSING)
        self.times = np.asarray(run.times, np.float64).copy()
        self.path = os.path.join(P.cache_dir(), f"traced-{self.sig}.nc")
        self.paths = [self.path]
        self.segments = [(self.path, 0, len(self.times), 0)]
        self._tracing = threading.Lock()
        self._fresh()

    def __repr__(self):
        return f"Traced({self.n} parcels, {len(self.times)} times)"

    @property
    def traced(self):
        """Whether the trajectories are on disk already."""
        return os.path.exists(self.path)

    def describe(self):
        """A line on where the parcels come from."""
        lat = self.lat
        return (f"Traced by cm1view through the 3D winds: seeded at the first output "
                f"every {lat['dx']:g} km across and every {lat['dz'] * 1000:.0f} m in "
                f"height from {lat['z0']:.2f} km above sea level"
                + (", parcels under the ground left out" if self.src.terrain else "")
                + (". " if self.traced else
                   "; the first choice of parcels traces them (once, kept in the cache "
                   "folder). "))

    def ensure(self, progress=None):
        """Trace the trajectories if they are not on disk yet."""
        with self._tracing:
            if os.path.exists(self.path):
                return
            out = trace(self.src, self.lat, progress)
            write(self.path, self.times, out)

    def read(self, name, ids=None, times=None):
        self.ensure()
        return super().read(name, ids, times)

    def lattice(self):
        """The seeding lattice, known without reading; None on a terrain run (seeds
        under the ground are missing, so a choice looks at the positions)."""
        return None if self.src.terrain else dict(self.lat)
