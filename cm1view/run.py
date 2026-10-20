"""Data access for a directory of CM1 netCDF output (one time per file).

Everything returned from here is on the scalar (xh, yh, z) grid: staggered
fields (u, v, w, ...) are averaged onto scalar points on read.

CM1 stores each 3D field chunked one horizontal level at a time, so
  * a single horizontal level is cheap (one chunk, ~0.1 s),
  * a full 3D field costs ~1-3 s (115 chunks),
  * a single column costs about as much as the full field.
Columns, cross-sections and 3D views therefore go through an LRU cache of
full 3D fields bounded by a memory budget.
"""

import glob
import hashlib
import json
import os
import re
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import netCDF4

# netCDF/HDF5 is not thread safe: every in-process read goes through this lock.
IO_LOCK = threading.RLock()

STAG_DIMS = {"nip1": "x", "njp1": "y", "nkp1": "z"}


def _destagger(a, stag):
    """Average a (nk*, nj*, ni*) or (nj*, ni*) array onto scalar points."""
    if stag == "x":
        return 0.5 * (a[..., :-1] + a[..., 1:])
    if stag == "y":
        return 0.5 * (a[..., :-1, :] + a[..., 1:, :])
    if stag == "z":
        return 0.5 * (a[:-1] + a[1:])
    return a


def _read_volume_worker(path, name, stag, outdir):
    """Process-pool worker: read one full 3D field, write it to tmpfs as .npy."""
    with netCDF4.Dataset(path) as d:
        d.set_auto_mask(False)
        a = np.asarray(d[name][0], dtype=np.float32)
    a = np.ascontiguousarray(_destagger(a, stag), dtype=np.float32)
    out = os.path.join(outdir, f"cm1view-{os.getpid()}-{uuid.uuid4().hex}.npy")
    np.save(out, a)
    return out


def _mean_profile_worker(path, name, stag):
    """Process-pool worker: horizontal mean profile of one 3D field."""
    with netCDF4.Dataset(path) as d:
        d.set_auto_mask(False)
        a = np.asarray(d[name][0], dtype=np.float32)
    return _destagger(a, stag).mean(axis=(1, 2), dtype=np.float64)


def parse_namelist(path):
    """Very small Fortran-namelist reader: returns {lowercase key: value}."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.split("!")[0]
            for m in re.finditer(r"(\w+)\s*=\s*([^,=]+?)\s*(?:,|$)", line):
                key, val = m.group(1).lower(), m.group(2).strip().strip("'\"")
                try:
                    out[key] = float(val.lower().replace("d", "e"))
                except ValueError:
                    out[key] = val
    return out


class MissingAtTime(LookupError):
    """A variable that exists in some output files but not at this time."""

    def __init__(self, name, t, msg):
        super().__init__(msg)
        self.name, self.t = name, t


def _var_info(name, v):
    """VarInfo of a netCDF variable, or None if it is not a (time, ...) 2D/3D field."""
    dims = v.dimensions
    if not dims or dims[0] != "time" or len(dims) not in (3, 4):
        return None
    stag = next((STAG_DIMS[x] for x in dims if x in STAG_DIMS), None)
    ch = v.chunking()
    zchunk = int(ch[1]) if len(dims) == 4 and ch != "contiguous" else 1
    return VarInfo(name, getattr(v, "long_name", name), getattr(v, "units", ""),
                   len(dims) - 1, stag, zchunk, dict(v.__dict__))


class VarInfo:
    __slots__ = ("name", "long_name", "units", "ndim", "stag", "zchunk", "attrs")

    def __init__(self, name, long_name, units, ndim, stag, zchunk=1, attrs=None):
        self.name, self.long_name, self.units = name, long_name, units
        self.ndim, self.stag = ndim, stag
        # levels per chunk: > 1 (e.g. post-processed fields) makes single-level reads
        # cost several levels, so those are read (and cached) as whole volumes
        self.zchunk, self.attrs = zchunk, attrs or {}

    def __repr__(self):
        return f"VarInfo({self.name}, {self.ndim}D, stag={self.stag})"


class CM1Run:
    def __init__(self, path, cache_gb=12.0, workers=None):
        self.path = os.path.abspath(path)
        self.files = sorted(glob.glob(os.path.join(self.path, "cm1out_[0-9]*.nc")))
        if not self.files:
            raise FileNotFoundError(f"no cm1out_NNNNNN.nc files found in {self.path}")

        with netCDF4.Dataset(self.files[0]) as d:
            self.xh = np.asarray(d["xh"][:], dtype=np.float64)  # km
            self.yh = np.asarray(d["yh"][:], dtype=np.float64)
            self.z = np.asarray(d["z"][:], dtype=np.float64)
            self.zf = np.asarray(d["zf"][:], dtype=np.float64)
            self.attrs = {k: d.getncattr(k) for k in d.ncattrs()}
            self.vars = {}
            for name, v in d.variables.items():
                info = _var_info(name, v)
                if info is not None:
                    self.vars[name] = info

        self.ni, self.nj, self.nk = len(self.xh), len(self.yh), len(self.z)
        self.dx = float(np.mean(np.diff(self.xh))) * 1000.0  # m
        self.dy = float(np.mean(np.diff(self.yh))) * 1000.0
        self.nml = parse_namelist(os.path.join(self.path, "namelist.input"))
        moving = int(self.nml.get("imove", 0)) == 1
        # CM1 writes winds relative to the (possibly translating) grid.
        self.umove = float(self.nml.get("umove", 0.0)) if moving else 0.0
        self.vmove = float(self.nml.get("vmove", 0.0)) if moving else 0.0
        self.times, names = self._scan()
        # fields written into only some files (e.g. by post-processing): which times
        self.var_times = {}
        for n in sorted(set().union(*names) - set(self.vars)):
            ts = [t for t, ns in enumerate(names) if n in ns]
            with netCDF4.Dataset(self.files[ts[-1]]) as d:
                info = _var_info(n, d[n])
            if info is not None:
                self.vars[n] = info
                self.var_times[n] = frozenset(ts)
        for n in self.vars:
            ts = frozenset(t for t, ns in enumerate(names) if n in ns)
            if len(ts) < len(self.files) and n not in self.var_times:
                self.var_times[n] = ts
        # fields computed here (not in the files), consulted before the files:
        # (name, t) -> float32 (nk, nj, ni); never evicted by the cache
        self.extra = OrderedDict()

        self.cache_bytes = int(cache_gb * 1024**3)
        self._cache = OrderedDict()  # (name, tindex) -> float32 (nk, nj, ni)
        self._cache_lock = threading.Lock()
        self._open = OrderedDict()  # tindex -> netCDF4.Dataset
        if workers is None:
            workers = len(os.sched_getaffinity(0))
        self.workers = max(1, min(int(workers), 8))
        self._pool = None
        self._means = {}  # (name, tindex) -> domain-mean profile (nk,)
        self._shm = "/dev/shm" if os.path.isdir("/dev/shm") else None

    # ------------------------------------------------------------------ meta
    @property
    def name(self):
        parts = self.path.rstrip("/").split("/")
        return "/".join(parts[-3:])

    def _scan(self):
        """Simulation time (s) and field names of every file, cached on disk by file
        stat (one quick metadata pass over the files the first time)."""
        sig = hashlib.sha1(
            json.dumps(
                [(f, os.path.getsize(f), int(os.path.getmtime(f))) for f in self.files]
            ).encode()
        ).hexdigest()[:16]
        cdir = os.path.join(os.path.expanduser("~"), ".cache", "cm1view")
        cfile = os.path.join(cdir, f"scan-{sig}.json")
        try:
            with open(cfile) as f:
                c = json.load(f)
            return np.array(c["times"], dtype=np.float64), [set(n) for n in c["vars"]]
        except (OSError, ValueError, KeyError):
            pass
        times, names = [], []
        for f in self.files:
            with netCDF4.Dataset(f) as d:
                times.append(float(d["time"][0]))
                names.append(sorted(n for n, v in d.variables.items()
                                    if v.dimensions[:1] == ("time",) and v.ndim in (3, 4)))
        try:
            os.makedirs(cdir, exist_ok=True)
            with open(cfile, "w") as f:
                json.dump(dict(times=times, vars=names), f)
        except OSError:
            pass
        return np.array(times, dtype=np.float64), [set(n) for n in names]

    def time_label(self, t):
        s = int(round(self.times[t]))
        return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def has(self, name):
        return name in self.vars

    def in_file(self, name, t):
        ts = self.var_times.get(name)
        return name in self.vars and (ts is None or t in ts)

    def _check(self, name, t):
        if (name, t) in self.extra or self.in_file(name, t):
            return
        ts = sorted(self.var_times.get(name, ()))
        where = (f"; the files have it at {self.time_label(ts[0])}–{self.time_label(ts[-1])} "
                 f"({len(ts)} times)") if ts else ""
        raise MissingAtTime(name, t, f"{name} is not in the output at "
                                     f"{self.time_label(t)}{where}")

    # ------------------------------------------------------------------ io
    def _ds(self, t):
        d = self._open.get(t)
        if d is None:
            d = netCDF4.Dataset(self.files[t])
            d.set_auto_mask(False)
            self._open[t] = d
            while len(self._open) > 6:
                _, old = self._open.popitem(last=False)
                old.close()
        else:
            self._open.move_to_end(t)
        return d

    def cached(self, name, t):
        with self._cache_lock:
            vol = self.extra.get((name, t))
            if vol is not None:
                return vol
            vol = self._cache.get((name, t))
            if vol is not None:
                self._cache.move_to_end((name, t))
            return vol

    def read_level(self, name, t, k=0):
        """One horizontal level of a native field (2D fields ignore k)."""
        info = self.vars[name]
        if info.ndim == 3:
            vol = self.cached(name, t)
            if vol is not None:
                return vol[k]
        self._check(name, t)
        if info.ndim == 3 and info.zchunk > 4:  # a level costs several: read the volume
            return self.volume(name, t)[k]
        with IO_LOCK:
            v = self._ds(t)[name]
            if info.ndim == 2:
                a = v[0]
            elif info.stag == "z":
                a = 0.5 * (v[0, k].astype(np.float32) + v[0, k + 1])
            else:
                a = v[0, k]
        a = np.asarray(a, dtype=np.float32)
        if info.stag in ("x", "y"):
            a = _destagger(a, info.stag)
        return a

    def level_weights(self, zkm):
        """(k0, k1, w) such that f(zkm) = (1-w) f[k0] + w f[k1]."""
        z = self.z
        if zkm <= z[0]:
            return 0, 0, 0.0
        if zkm >= z[-1]:
            return self.nk - 1, self.nk - 1, 0.0
        k1 = int(np.searchsorted(z, zkm))
        k0 = k1 - 1
        return k0, k1, float((zkm - z[k0]) / (z[k1] - z[k0]))

    def read_height(self, name, t, zkm):
        """Native field linearly interpolated to a height (km AGL)."""
        if self.vars[name].ndim == 2:
            return self.read_level(name, t)
        k0, k1, w = self.level_weights(zkm)
        a = self.read_level(name, t, k0)
        if w == 0.0 or k1 == k0:
            return a
        return (1.0 - w) * a + w * self.read_level(name, t, k1)

    def read_column(self, name, t, i, j):
        """A single column without populating the cache (slow: ~1-3 s)."""
        info = self.vars[name]
        with IO_LOCK:
            v = self._ds(t)[name]
            if info.stag == "x":
                a = 0.5 * (v[0, :, j, i] + v[0, :, j, i + 1])
            elif info.stag == "y":
                a = 0.5 * (v[0, :, j, i] + v[0, :, j + 1, i])
            else:
                a = np.asarray(v[0, :, j, i], dtype=np.float32)
                if info.stag == "z":
                    a = 0.5 * (a[:-1] + a[1:])
        return np.asarray(a, dtype=np.float32)

    def read_box(self, name, t, i0, i1, j0, j1):
        """Columns [j0:j1, i0:i1] of a 3D field without populating the cache.  With
        one horizontal level per chunk this costs about as much as a full read, but
        keeps the cache for the times being browsed."""
        info = self.vars[name]
        with IO_LOCK:
            v = self._ds(t)[name]
            if info.stag == "x":
                a = np.asarray(v[0, :, j0:j1, i0:i1 + 1], dtype=np.float32)
                a = 0.5 * (a[..., :-1] + a[..., 1:])
            elif info.stag == "y":
                a = np.asarray(v[0, :, j0:j1 + 1, i0:i1], dtype=np.float32)
                a = 0.5 * (a[:, :-1] + a[:, 1:])
            else:
                a = np.asarray(v[0, :, j0:j1, i0:i1], dtype=np.float32)
                if info.stag == "z":
                    a = 0.5 * (a[:-1] + a[1:])
        return a

    def _insert(self, name, t, vol):
        with self._cache_lock:
            self._cache[(name, t)] = vol
            self._cache.move_to_end((name, t))
            total = sum(a.nbytes for a in self._cache.values())
            while total > self.cache_bytes and len(self._cache) > 1:
                _, old = self._cache.popitem(last=False)
                total -= old.nbytes

    def _read_volume_local(self, name, t):
        info = self.vars[name]
        with IO_LOCK:
            a = np.asarray(self._ds(t)[name][0], dtype=np.float32)
        return np.ascontiguousarray(_destagger(a, info.stag), dtype=np.float32)

    def volume(self, name, t):
        vol = self.cached(name, t)
        if vol is None:
            self._check(name, t)
            vol = self._read_volume_local(name, t)
            self._insert(name, t, vol)
        return vol

    def load_volumes(self, names, t, progress=None, cancelled=None):
        """Ensure several full 3D fields are cached; reads in parallel when
        more than one CPU is available.  Returns False if cancelled."""
        missing = [n for n in dict.fromkeys(names) if self.cached(n, t) is None]
        for n in missing:
            self._check(n, t)
        total, done = len(missing), 0
        if progress:
            progress(done, total, missing[0] if missing else "")
        if not missing:
            return True
        if self.workers > 1 and len(missing) > 1 and self._shm:
            futs = {
                self._get_pool().submit(
                    _read_volume_worker,
                    self.files[t],
                    n,
                    self.vars[n].stag,
                    self._shm,
                ): n
                for n in missing
            }
            from concurrent.futures import as_completed

            for fut in as_completed(futs):
                n = futs[fut]
                path = fut.result()
                try:
                    self._insert(n, t, np.load(path))
                finally:
                    os.remove(path)
                done += 1
                if progress:
                    progress(done, total, n)
            return True
        for n in missing:
            if cancelled and cancelled():
                return False
            if progress:
                progress(done, total, n)
            self._insert(n, t, self._read_volume_local(n, t))
            done += 1
            if progress:
                progress(done, total, n)
        return True

    def _get_pool(self):
        if self._pool is None:
            import multiprocessing as mp

            self._pool = ProcessPoolExecutor(max_workers=self.workers,
                                             mp_context=mp.get_context("spawn"))
        return self._pool

    def mean_profiles(self, names, t, progress=None):
        """Domain-mean profiles {name: (nk,)} at time t.  Uses cached volumes when
        present; otherwise reads in parallel without filling the 3D cache."""
        out, todo = {}, []
        for n in dict.fromkeys(names):
            if (n, t) in self._means:
                out[n] = self._means[(n, t)]
            elif (vol := self.cached(n, t)) is not None:
                out[n] = self._means[(n, t)] = vol.mean(axis=(1, 2), dtype=np.float64)
            else:
                todo.append(n)
        total = len(todo)
        if progress and todo:
            progress(0, total, todo[0])
        if self.workers > 1 and len(todo) > 1:
            from concurrent.futures import as_completed

            futs = {self._get_pool().submit(_mean_profile_worker, self.files[t], n,
                                            self.vars[n].stag): n for n in todo}
            for done, fut in enumerate(as_completed(futs), 1):
                n = futs[fut]
                out[n] = self._means[(n, t)] = fut.result()
                if progress:
                    progress(done, total, n)
        else:
            for done, n in enumerate(todo, 1):
                out[n] = self._means[(n, t)] = \
                    self._read_volume_local(n, t).mean(axis=(1, 2), dtype=np.float64)
                if progress:
                    progress(done, total, n)
        return out

    # ------------------------------------------------------------------ misc
    def cache_info(self):
        with self._cache_lock:
            used = sum(a.nbytes for a in self._cache.values())
            n = len(self._cache)
        return used / 1024**3, self.cache_bytes / 1024**3, n

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()

    def trim_cache(self, nbytes):
        """Evict least-recently-used cached volumes until `nbytes` are freed (or the
        cache is empty).  Returns the bytes freed."""
        freed = 0
        with self._cache_lock:
            while self._cache and freed < nbytes:
                _, old = self._cache.popitem(last=False)
                freed += old.nbytes
        return freed

    def ij(self, x, y):
        """Nearest scalar-grid indices for a position in km."""
        i = int(np.clip(np.rint((x - self.xh[0]) * 1000.0 / self.dx), 0, self.ni - 1))
        j = int(np.clip(np.rint((y - self.yh[0]) * 1000.0 / self.dy), 0, self.nj - 1))
        return i, j
