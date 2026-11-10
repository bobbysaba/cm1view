"""Data access for model output: the model-neutral Run, and CM1Run (a directory of CM1
netCDF output, one time per file).  Other models' readers subclass Run (core.models).

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
from contextlib import contextmanager

import numpy as np
import netCDF4

from . import pool

# netCDF/HDF5 is not thread safe: every in-process read goes through this lock.
IO_LOCK = threading.RLock()

# staggered dimensions: CM1's own names (ni/nj/nk on scalar points) and the CF-style
# ones of newer versions (xh/yh/zh on scalar points, xf/yf/zf staggered)
# reader processes at most: each holds only a block of levels at a time (level_blocks),
# so this is bounded by the CPUs worth using rather than memory
MAX_READERS = 16

STAG_DIMS = {"nip1": "x", "njp1": "y", "nkp1": "z", "xf": "x", "yf": "y", "zf": "z"}


class Cancelled(Exception):
    """A read stopped because the job that asked for it no longer wants it (see
    reporting)."""


_hook = threading.local()  # .on: (progress, cancelled) of the reporting() block

# per-thread state that a helper thread working for a job takes over from the job's
# thread (ahead(), a section's layer threads): (capture, restore) pairs, restore(value)
# returning the value it replaced.  The viewer's timing adds its read count here.
CARRIED = []


def carry(fn):
    """fn, made to run on another thread with this thread's CARRIED state (put back
    as it was once fn returns: pool threads are reused)."""
    if not CARRIED:
        return fn
    saved = [(restore, capture()) for capture, restore in CARRIED]

    def g(*a, **k):
        old = [(restore, restore(v)) for restore, v in saved]
        try:
            return fn(*a, **k)
        finally:
            for restore, v in old:
                restore(v)
    return g


@contextmanager
def reporting(progress=None, cancelled=None):
    """Within the block, reads made on this thread (through any run) report
    progress(done, total, what) as they go, the way load_volumes' own argument does,
    with `what` naming the field and, for an ensemble mean, the members read so far
    ("th · 18/36 members").  Once cancelled() is true a read stops at the next field
    or member share and raises Cancelled.  load_volumes' own progress argument hears
    the same reports; its own cancelled argument takes precedence (and it keeps
    returning False when that one cancels)."""
    old = getattr(_hook, "on", None)
    _hook.on = (progress, cancelled)
    try:
        yield
    finally:
        _hook.on = old


def report(done, total, what):
    """Progress to the reporting() block of this thread, if any."""
    on = getattr(_hook, "on", None)
    if on and on[0]:
        on[0](done, total, what)


def _both(a, b):
    def progress(done, total, what):
        a(done, total, what)
        b(done, total, what)
    return progress


def check_cancelled():
    """Raise Cancelled if the reporting() block of this thread was cancelled."""
    on = getattr(_hook, "on", None)
    if on and on[1] and on[1]():
        raise Cancelled()


AHEAD_BYTES = 1024**3  # most that a loop over times reads ahead of its use (ahead_width)


def ahead_width(run, nbytes=0, cap=8):
    """How many items of a loop over a run's times ahead() works on at once when each
    reads about `nbytes`: most of the readers (pool.width), at most `cap`, and no more
    than read AHEAD_BYTES together (a quarter of the 3D cache if that is less); at
    least 1.  0 (each in turn, on the calling thread) for a run with one worker."""
    workers = int(getattr(run, "workers", 1) or 1)
    if workers <= 1:
        return 0
    room = min(AHEAD_BYTES, int(getattr(run, "cache_bytes", 4 * AHEAD_BYTES)) // 4)
    return max(1, min(int(cap), pool.width(workers), room // max(1, int(nbytes))))


def ahead(fn, items, width):
    """(item, fn(item)) of every item, in order, with fn at work on the next `width`
    items (each on a thread) while the caller uses one: for a loop over output times
    whose reads do not depend on the time before.

    Reads made by fn go to the reader processes even when they are single small levels
    (in this process they would take IO_LOCK in turn and the times would not overlap).
    fn's threads hear the caller's reporting() block.  Closing the generator drops the
    items not started and cancels the reads of those that are (Cancelled, unseen).  An
    exception of fn is raised when its item's turn comes.  width < 1: fn(item) in turn
    on the calling thread, as a plain loop."""
    if width < 1:
        for x in items:
            yield x, fn(x)
        return
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor

    on = getattr(_hook, "on", None)
    err = np.geterr()  # (numpy's error state is each thread's own: the caller's here)
    closed = []

    def stop():
        return bool(closed) or bool(on and on[1] and on[1]())

    @carry
    def work(x):
        _hook.on, _hook.ahead = (on[0] if on else None, stop), True
        with np.errstate(**err):
            return fn(x)

    ex = ThreadPoolExecutor(int(width), thread_name_prefix="cm1view-ahead")
    items, live = iter(items), deque()

    def fill():
        while len(live) < width:
            try:
                x = next(items)
            except StopIteration:
                return
            live.append((x, ex.submit(work, x)))

    try:
        fill()
        while live:
            x, f = live.popleft()
            r = f.result()
            fill()  # (the next ones start before this one is used)
            yield x, r
    finally:
        closed.append(True)
        ex.shutdown(wait=False, cancel_futures=True)


def _destagger(a, stag):
    """Average a (nk*, nj*, ni*) or (nj*, ni*) array onto scalar points."""
    if stag == "x":
        return 0.5 * (a[..., :-1] + a[..., 1:])
    if stag == "y":
        return 0.5 * (a[..., :-1, :] + a[..., 1:, :])
    if stag == "z":
        return 0.5 * (a[:-1] + a[1:])
    return a


def temp_name(path, suffix=".tmp"):
    """A name beside `path` for one write, to os.replace into place: its own for every
    write, so two threads writing one cache file cannot share it."""
    return f"{path}.{os.getpid()}.{uuid.uuid4().hex[:8]}{suffix}"


def open_source(src):
    """One time's output, open for reading (unmasked; use it as a context manager).
    `src` is a file path (opened with netCDF4) or an object with .open() returning
    a dataset-like view (a model reader's own: d.variables, d[name][0, ...])."""
    if isinstance(src, (str, os.PathLike)):
        d = netCDF4.Dataset(src)
        d.set_auto_mask(False)
        return d
    return src.open()


KEEP_OPEN = 0  # output files kept open by opened(): set in the reader processes (pool)
_kept = OrderedDict()  # (in a reader process) key -> open dataset, last used last


def file_key(path):
    """What tells one state of a file from another: its path, time of change and size."""
    st = os.stat(path)
    return (os.fspath(path), st.st_mtime_ns, st.st_size)


def _keep_key(src):
    """The key a reader keeps `src` open under, or None for one it does not keep: a
    file's file_key; a model's own source says with .key() (none: not kept).  Its first
    item names the source whatever state its files are in."""
    try:
        if isinstance(src, (str, os.PathLike)):
            return file_key(src)
        key = getattr(src, "key", None)
        return key() if key else None
    except OSError:
        return None


@contextmanager
def opened(src):
    """open_source(src) for the block, in a reader process left open afterwards (the
    last KEEP_OPEN sources read): the many tasks of one time's fields then open its
    file once per reader, not once each.  A file that changed since is opened anew.
    pool.release() closes them all (before a file is written to)."""
    key = _keep_key(src) if KEEP_OPEN > 0 else None
    if key is None:
        with open_source(src) as d:
            yield d
        return
    d = _kept.pop(key, None)
    if d is None:
        for k in [k for k in _kept if k[0] == key[0]]:  # (as it was before it changed)
            _kept.pop(k).close()
        d = open_source(src)
    try:
        yield d
    except BaseException:
        d.close()
        raise
    _kept[key] = d
    while len(_kept) > KEEP_OPEN:
        _kept.popitem(last=False)[1].close()


def close_kept():
    """Close the sources opened() keeps open."""
    while _kept:
        _kept.popitem()[1].close()


def _read_volume_worker(src, name, stag, outdir):
    """Process-pool worker: read one full 3D field, write it to tmpfs as .npy."""
    with opened(src) as d:
        a = np.asarray(d[name][0], dtype=np.float32)
    a = np.ascontiguousarray(_destagger(a, stag), dtype=np.float32)
    out = os.path.join(outdir, f"cm1view-{os.getpid()}-{uuid.uuid4().hex}.npy")
    np.save(out, a)
    return out


def _read_block_worker(src, name, stag, path, k0, k1):
    """Process-pool worker: levels k0:k1 (scalar points) of one 3D field, written in
    place into `path`, the shared file that holds the whole float32 (nk, nj, ni) field
    (see _SharedVolume).  A file already removed (the read was cancelled) is skipped."""
    with opened(src) as d:
        a = np.asarray(d[name][0, k0:k1 + (stag == "z")], dtype=np.float32)
    _write_rows(path, np.ascontiguousarray(_destagger(a, stag), dtype=np.float32), k0)


def _write_rows(path, a, row):
    """Write float32 (n, ny, nx) `a` into the shared file `path` from its row `row` on
    (a file already removed, the read cancelled, is skipped)."""
    try:
        f = open(path, "r+b")
    except FileNotFoundError:
        return
    with f:
        f.seek(row * a[0].nbytes)
        a.tofile(f)


def _level_runs(ks):
    """[(k0, k1)] of the runs of consecutive levels in ks, in its order (k0..k1-1)."""
    runs, p = [], 0
    while p < len(ks):
        q = p + 1
        while q < len(ks) and ks[q] == ks[q - 1] + 1:
            q += 1
        runs.append((ks[p], ks[q - 1] + 1))
        p = q
    return runs


def _levels(v, stag, ks, rows=None, cols=None, points=False):
    """Levels ks of an open (time, z, y, x) variable on scalar points, float32
    (len(ks), ny, nx): each run of consecutive levels is one read.  rows, cols: keep
    only those rows and columns (index arrays), or with points only the columns
    (rows[n], cols[n]) ((len(ks), n)); only the box around them is read."""
    if rows is not None and not (len(rows) and len(cols)):
        return np.zeros((len(ks), len(rows)) + (() if points else (len(cols),)), np.float32)
    box = (slice(None), slice(None))
    if rows is not None:
        j0, i0 = int(rows.min()), int(cols.min())
        box = (slice(j0, int(rows.max()) + 1 + (stag == "y")),
               slice(i0, int(cols.max()) + 1 + (stag == "x")))
        rows, cols = rows - j0, cols - i0
    out = []
    for k0, k1 in _level_runs(ks):
        a = _destagger(np.asarray(v[(0, slice(k0, k1 + (stag == "z"))) + box],
                                  dtype=np.float32), stag)
        out.append(a if rows is None else a[:, rows, cols] if points
                   else a[:, rows][:, :, cols])
    a = out[0] if len(out) == 1 else np.concatenate(out)
    return np.ascontiguousarray(a, dtype=np.float32)


def _read_levels_worker(src, name, stag, path, p0, ks, rows, cols, points=False):
    """Process-pool worker: levels ks of one 3D field (see _levels), written into
    `path`, the shared file of all the levels asked for, from its row p0 on."""
    with opened(src) as d:
        a = _levels(d[name], stag, ks, rows, cols, points)
    _write_rows(path, a, p0)


def _reduce_block_worker(src, name, stag, path, row, k0, k1, op):
    """Process-pool worker: the max or min (op) over levels k0:k1 of one 3D field, one
    level in memory at a time, written as row `row` of the shared file `path`."""
    f = np.maximum if op == "max" else np.minimum  # (NaN stays, as the volume's max)
    out = None
    with opened(src) as d:
        v = d[name]
        for k in range(k0, k1):
            a = _destagger(np.asarray(v[0, k:k + 1 + (stag == "z")], dtype=np.float32),
                           stag)[0]
            out = a if out is None else f(out, a)
    _write_rows(path, np.ascontiguousarray(out[None], dtype=np.float32), row)


def _read_plane_worker(src, name, stag):
    """Process-pool worker: a 2D field on scalar points (one plane: returned directly)."""
    with opened(src) as d:
        a = np.asarray(d[name][0], dtype=np.float32)
    return np.ascontiguousarray(_destagger(a, stag), dtype=np.float32)


BLOCK_BYTES = 16 * 1024**2  # least worth a reader task of its own (opening costs)
FIT_SHARE = 2  # a request's volumes fit the 3D cache within this share of it (Run.fits)


def level_blocks(shape, zchunk, nfields, workers):
    """Level ranges [(k0, k1)] to split each of `nfields` 3D fields of `shape` (nk, nj,
    ni) into so that `workers` readers share them: about two tasks per reader over all
    the fields (so an uneven block does not keep the rest waiting), whole chunks of
    `zchunk` levels, and no block under BLOCK_BYTES (a small field is one task)."""
    nk = shape[0]
    want = max(1, -(-2 * workers // max(1, nfields)))
    least = -(-BLOCK_BYTES // max(1, 4 * shape[1] * shape[2]))
    step = max(1, least, -(-nk // want))
    if zchunk > 1:
        step = -(-step // zchunk) * zchunk
    return [(k, min(k + step, nk)) for k in range(0, nk, step)]


class _SharedVolume:
    """A float32 volume in a file on tmpfs that reader processes write their level
    blocks into; array() maps it into this process without a copy.  The file is
    removed by array() or discard(); the mapping outlives it (the memory is freed when
    the last view of the array goes)."""

    def __init__(self, outdir, shape):
        self.shape = tuple(int(s) for s in shape)
        nbytes = 4 * int(np.prod(self.shape))
        self.path = os.path.join(outdir, f"cm1view-{os.getpid()}-{uuid.uuid4().hex}.vol")
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            # reserve the space now: a full tmpfs fails here rather than as a crash
            # (SIGBUS) of a reader writing into it
            os.posix_fallocate(self.fd, 0, nbytes)
        except BaseException:
            self.discard()
            raise

    def array(self):
        import mmap

        mm = mmap.mmap(self.fd, 0)
        self.discard()
        return np.frombuffer(mm, np.float32).reshape(self.shape)

    def discard(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
            try:
                os.remove(self.path)
            except OSError:
                pass


def _drop_pending(futs):
    """Cancel reader tasks no longer wanted; those already running remove their file
    when they finish (without waiting here for them)."""
    for f in futs:
        if not f.cancel():
            f.add_done_callback(_remove_result)


def _remove_result(fut):
    try:
        os.remove(fut.result())
    except Exception:  # noqa: BLE001
        pass


def _box(v, stag, i0, i1, j0, j1):
    """Columns [j0:j1, i0:i1] of an open (time, z, y, x) variable, on scalar points."""
    if stag == "x":
        a = np.asarray(v[0, :, j0:j1, i0:i1 + 1], dtype=np.float32)
        return 0.5 * (a[..., :-1] + a[..., 1:])
    if stag == "y":
        a = np.asarray(v[0, :, j0:j1 + 1, i0:i1], dtype=np.float32)
        return 0.5 * (a[:, :-1] + a[:, 1:])
    a = np.asarray(v[0, :, j0:j1, i0:i1], dtype=np.float32)
    return 0.5 * (a[:-1] + a[1:]) if stag == "z" else a


def _read_box_worker(src, name, stag, box):
    """Process-pool worker: columns of one 3D field (small: returned directly)."""
    with opened(src) as d:
        return _box(d[name], stag, *box)


def _mean_profile_worker(src, name, stag, k0=0, k1=None):
    """Process-pool worker: horizontal mean profile of levels k0:k1 (all by default)
    of one 3D field."""
    with opened(src) as d:
        v = d[name]
        a = np.asarray(v[0] if k1 is None else v[0, k0:k1 + (stag == "z")],
                       dtype=np.float32)
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


class VolumeCache:
    """LRU of full 3D volumes shared by all open runs, within one memory budget.
    Keys are (run path, name, time index)."""

    def __init__(self, cache_gb):
        self.bytes = int(cache_gb * 1024**3)
        self._d = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            v = self._d.get(key)
            if v is not None:
                self._d.move_to_end(key)
            return v

    def put(self, key, vol, protect=()):
        """Insert, then evict least-recently-used entries over the budget, never the
        new one nor those in `protect` (the rest of the same request)."""
        with self.lock:
            self._d[key] = vol
            self._d.move_to_end(key)
            total = sum(a.nbytes for a in self._d.values())
            for k in list(self._d):
                if total <= self.bytes:
                    break
                if k != key and k not in protect:
                    total -= self._d.pop(k).nbytes

    def drop(self, pred):
        """Remove entries whose key satisfies pred(key); returns the bytes freed."""
        with self.lock:
            ks = [k for k in self._d if pred(k)]
            return sum(self._d.pop(k).nbytes for k in ks)

    def trim(self, nbytes):
        """Evict least-recently-used entries until `nbytes` are freed."""
        freed = 0
        with self.lock:
            while self._d and freed < nbytes:
                freed += self._d.popitem(last=False)[1].nbytes
        return freed

    def info(self):
        with self.lock:
            return sum(a.nbytes for a in self._d.values()), len(self._d)


class MissingAtTime(LookupError):
    """A variable that exists in some output files but not at this time."""

    def __init__(self, name, t, msg):
        super().__init__(msg)
        self.name, self.t = name, t


class FileBusy(LookupError):
    """The output file of this time is being written (e.g. pressure decomposition)."""


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


class Run:
    """Output of one model run: times, a grid and fields, read one time at a time.

    Everything model-neutral lives here (the 3D cache, reader processes, level and
    height reads, columns, mean profiles).  A model's reader (a subclass) finds the
    files and sets, before calling _grid_done():
      path    the run's folder (also the cache key and where exports go)
      files   one output file per time (their stat says when a time changed)
      times   simulation time (s) of each time index
      xh, yh  scalar-point x, y (km); z, zf scalar and staggered heights (km)
      vars    {name: VarInfo} of the fields in the files, by cm1view's names
      var_times  {name: frozenset of time indices} for fields only at some times
      attrs   global attributes; nml the run's namelist ({} if none)
      umove, vmove  grid motion (m/s) added to the winds for ground-relative ones
    and may override source(t) (what reader processes open for time t)."""

    model = None  # key in core.models.MODELS
    model_label = "model"
    # levels that follow the terrain, their heights varying in space and time (heights());
    # z, zf are then one representative profile.  False: flat, z and zf everywhere.
    terrain = False
    # the model writes no parcel output: cm1view traces trajectories through the 3D winds
    # (core.trajcalc) instead of looking for parcel files
    traced_parcels = False
    # storm-relative winds are offered (vector frames, and fields that take the storm
    # motion: storm-relative helicity, STP, SCP, streamwise vorticity).  False (WoFS,
    # for now): winds are ground-relative only, and those fields are left out
    storm_relative = True
    # seconds of storm track a storm motion is fitted over when the
    # track_motion_window setting is auto (core.track.motion); 0: centred differences
    track_window = 0.0
    # where the grid sits on the Earth (core.geo.Geo: projection, lat/lon, boundary
    # lines), or None: an idealized run (CM1) has none
    geo = None
    # a plain-language note on how this run's fields come about ("" for none), shown
    # with the run's details
    note = ""
    # output times kept open in this process (a model's source may open many files)
    open_max = 6

    def __init__(self, path, cache_gb=12.0, workers=None, cache=None):
        self.path = os.path.abspath(path)
        self.files, self.attrs, self.nml = [], {}, {}
        self.vars, self.var_times = {}, {}
        self.umove = self.vmove = 0.0
        # fields computed here (not in the files), consulted before the files:
        # (name, t) -> float32 (nk, nj, ni); never evicted by the cache
        self.extra = OrderedDict()
        self._writing = set()  # times whose file is being written: no reads meanwhile

        # full 3D volumes (float32, nk x nj x ni), possibly shared with other runs
        self._vc = cache if cache is not None else VolumeCache(cache_gb)
        self._cache_lock = threading.Lock()  # guards self.extra
        self._inflight = {}  # (name, t) -> Event: being read by some job right now
        self._inflight_lock = threading.Lock()
        self._open = OrderedDict()  # tindex -> open dataset
        if workers is None:
            from .. import config
            workers = config.job_cpus()
        self.workers = max(1, min(int(workers), MAX_READERS))
        self._pool_uses = 0  # times this run went to the reader processes
        self._means = {}  # (name, tindex) -> domain-mean profile (nk,)
        self._shm = "/dev/shm" if os.path.isdir("/dev/shm") else None

    def _grid_done(self):
        """Sizes and spacing from xh, yh, z (call once they are set)."""
        self.ni, self.nj, self.nk = len(self.xh), len(self.yh), len(self.z)
        self.dx = float(np.mean(np.diff(self.xh))) * 1000.0  # m
        self.dy = float(np.mean(np.diff(self.yh))) * 1000.0

    # ------------------------------------------------------------------ meta
    @property
    def name(self):
        parts = self.path.rstrip("/").split("/")
        return "/".join(parts[-3:])

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
    def _not_writing(self, t):
        if t in self._writing:
            raise FileBusy(f"the output file at {self.time_label(t)} is being written "
                           f"(pressure decomposition); it is readable again in a moment")

    def source(self, t):
        """What open_source() opens for time t (picklable: reader processes open it
        themselves).  A file path here; a model reader may return its own object."""
        return self.files[t]

    def _ds(self, t):
        self._not_writing(t)
        d = self._open.get(t)
        if d is None:
            d = open_source(self.source(t))
            self._open[t] = d
            while len(self._open) > self.open_max:
                _, old = self._open.popitem(last=False)
                old.close()
        else:
            self._open.move_to_end(t)
        return d

    @property
    def cache_bytes(self):
        return self._vc.bytes

    def cached(self, name, t):
        with self._cache_lock:
            vol = self.extra.get((name, t))
        return vol if vol is not None else self._vc.get((self.path, name, t))

    def forget(self, names, t):
        """Drop cached volumes of `names` at time t (and derived volumes named
        '~name...' built from them)."""
        names = set(names)
        self._vc.drop(lambda k: k[0] == self.path and k[2] == t
                      and (k[1] in names or k[1].split("@")[0].lstrip("~") in names))

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
        if self.workers > 1 and self._shm and getattr(_hook, "ahead", False):
            a = self._level_pooled(name, t, k)  # (a loop over times, reading ahead)
            if a is not None:
                return a
        return self._level_here(name, t, k)

    def _level_pooled(self, name, t, k):
        """read_level in a reader process, for the reads of ahead(): several times'
        levels are then read at once.  None when tmpfs has no room for it."""
        self._not_writing(t)
        info = self.vars[name]
        if info.ndim == 2:
            return self._get_pool().submit(_read_plane_worker, self.source(t), name,
                                           info.stag).result()
        check_cancelled()
        a = (self._read_levels_pool([name], t, [int(k)], None, None, None) or {}).get(name)
        return None if a is None else a[0]

    def _level_here(self, name, t, k=0):
        """read_level of a field not cached, read in this process."""
        info = self.vars[name]
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

    def terrain_height(self):
        """Ground height (km above sea level), (nj, ni): zero on a flat run."""
        return np.zeros((self.nj, self.ni))

    def heights(self, t, ref="agl", w=False):
        """Heights (km) of the model levels at time t, (nk, nj, ni) ((nk + 1, ...) with
        w: the w levels), above ground ("agl") or sea level ("msl").  A flat run's are
        z (zf) in every column (a read-only view)."""
        z = np.asarray(self.zf if w else self.z, dtype=np.float64)
        return np.broadcast_to(z[:, None, None], (len(z), self.nj, self.ni))

    def column_weights(self, t, zkm, ref="agl"):
        """Per column (k0, k1, w, under) of height zkm km at time t on a terrain run's
        levels: f(zkm) = (1-w) f[k0] + w f[k1], held at the lowest and highest level
        beyond them; under: columns where zkm (msl) is below the ground (else None)."""
        Z = self.heights(t, ref)
        nk = Z.shape[0]
        if nk == 1:
            k = np.zeros(Z.shape[1:], dtype=np.intp)
            return k, k, np.zeros(Z.shape[1:]), None
        k1 = np.clip((Z < zkm).sum(axis=0), 1, nk - 1)
        k0 = k1 - 1
        z0 = np.take_along_axis(Z, k0[None], 0)[0]
        z1 = np.take_along_axis(Z, k1[None], 0)[0]
        with np.errstate(divide="ignore", invalid="ignore"):
            w = np.clip((zkm - z0) / (z1 - z0), 0.0, 1.0)
        w = np.where(np.isfinite(w), w, 0.0)
        under = zkm < self.terrain_height() if ref == "msl" else None
        return k0, k1, w, under

    def interp_height(self, level, t, zkm, ref="agl"):
        """level(k) -> (nj, ni) plane, linearly interpolated to height zkm km above
        ground ("agl") or sea level ("msl"): on a flat run between two levels; on a
        terrain run column by column, reading only the levels it needs (NaN under the
        ground)."""
        if not self.terrain:
            k0, k1, w = self.level_weights(zkm)
            a = level(k0)
            if w == 0.0 or k1 == k0:
                return a
            return (1.0 - w) * a + w * level(k1)
        return self._interp_columns(level, self.column_weights(t, zkm, ref))

    @staticmethod
    def _column_levels(cw):
        """The levels column weights cw (column_weights) take values from."""
        k0, k1, w, _ = cw
        return [int(k) for k in np.union1d(np.unique(k0), np.unique(k1[w > 0]))]

    def _interp_columns(self, level, cw):
        """level(k) -> (nj, ni) plane, combined column by column with the weights cw."""
        k0, k1, w, under = cw
        out = np.zeros(w.shape, dtype=np.float64)
        for k in self._column_levels(cw):
            a = np.asarray(level(k), dtype=np.float64)
            m0, m1 = k0 == k, (k1 == k) & (w > 0)
            out[m0] += (1.0 - w[m0]) * a[m0]
            out[m1] += w[m1] * a[m1]
        if under is not None:
            out[under] = np.nan
        return out.astype(np.float32)

    def read_height(self, name, t, zkm, ref="agl"):
        """Native field linearly interpolated to a height (km above ground, or with
        ref "msl" above sea level: the same on a flat run)."""
        if self.vars[name].ndim == 2:
            return self.read_level(name, t)
        return self.interp_height(lambda k: self.read_level(name, t, k), t, zkm, ref)

    def read_heights(self, names, t, zkm, ref="agl"):
        """{name: read_height(name, t, zkm, ref)} of several native fields, the levels
        they need read together (read_levels)."""
        names = list(dict.fromkeys(names))
        out = {n: self.read_level(n, t) for n in names if self.vars[n].ndim == 2}
        n3 = [n for n in names if n not in out]
        if not n3:
            return out
        if not self.terrain:
            k0, k1, w = self.level_weights(zkm)
            one = w == 0.0 or k1 == k0
            lv = self.read_levels(n3, t, [k0] if one else [k0, k1])
            for n in n3:
                out[n] = lv[n][0] if one else (1.0 - w) * lv[n][0] + w * lv[n][1]
            return out
        cw = self.column_weights(t, zkm, ref)
        ks = self._column_levels(cw)
        at = {k: i for i, k in enumerate(ks)}
        lv = self.read_levels(n3, t, ks)
        for n in n3:
            out[n] = self._interp_columns(lambda k, a=lv[n]: a[at[k]], cw)
        return out

    def read_levels(self, names, t, ks, rows=None, cols=None, cancelled=None,
                    points=False):
        """{name: float32 (len(ks), nj, ni)}: model levels ks of several native 3D
        fields at time t, as read_level gives them one at a time.  Levels not in the
        cache are read in the reader processes, all the fields at once, into shared
        memory (a level read here holds IO_LOCK while the readers idle); nothing enters
        the 3D cache.  A few small levels are read here (a reader has to open the file),
        unless the read is one made ahead of a loop over times (ahead()).
        rows, cols: only those rows and columns ((len(ks), len(rows), len(cols))), or
        with points only the columns (rows[n], cols[n]) ((len(ks), n)): what a request
        too large for the 3D cache reads in place of volumes (Fields.box, .along).
        Returns None once cancelled() is true; a cancelled reporting() block raises
        Cancelled instead."""
        names = list(dict.fromkeys(names))
        ks = [int(k) for k in ks]
        if rows is not None:
            rows, cols = np.asarray(rows, np.intp), np.asarray(cols, np.intp)
        on = getattr(_hook, "on", None)
        hooked = cancelled is None and on is not None and on[1] is not None
        if hooked:
            cancelled = on[1]
        out = self._read_levels(names, t, ks, rows, cols, cancelled, points)
        if out is None and hooked:
            raise Cancelled()
        return out

    def _read_levels(self, names, t, ks, rows, cols, cancelled, points=False):
        def part(a):  # (of whole levels: the rows and columns asked for)
            return a if rows is None else a[..., rows, cols] if points \
                else a[..., rows[:, None], cols]

        def take(vol):
            if rows is None:
                return vol[ks]
            return vol[np.asarray(ks, np.intp)[:, None], rows, cols] if points \
                else vol[np.ix_(ks, rows, cols)]

        out, todo, whole = {}, [], []
        for n in names:
            vol = self.cached(n, t)
            if vol is not None:
                out[n] = take(vol)
                continue
            self._check(n, t)
            # (a field whose level costs several: its volume, as read_level does)
            (whole if self.vars[n].zchunk > 4 else todo).append(n)
        if whole:
            if not self.load_volumes(whole, t, cancelled=cancelled):
                return None
            for n in whole:
                out[n] = take(self.volume(n, t))
        if not todo or not ks:
            for n in todo:
                out[n] = part(np.zeros((0,) + self._vol_shape(n, t)[1:], np.float32))
            return {n: out[n] for n in names}
        self._not_writing(t)
        reads = len(ks) * len(todo)
        # (worth the readers: several levels of some size, or any read made ahead())
        if self.workers > 1 and self._shm and (getattr(_hook, "ahead", False) or (
                reads > 1 and 4 * reads * self.nj * self.ni >= BLOCK_BYTES)):
            got = self._read_levels_pool(todo, t, ks, rows, cols, cancelled, points)
            if got is None:
                return None
            out.update(got)
        for n in todo:  # (read here: few or small, or no room in tmpfs)
            if n in out:
                continue
            planes = []
            for k in ks:
                if cancelled and cancelled():
                    return None
                planes.append(part(self._level_here(n, t, k)))
            out[n] = np.stack(planes)
        return {n: out[n] for n in names}

    def _read_levels_pool(self, names, t, ks, rows, cols, cancelled, points=False):
        """read_levels' fields not cached, read in the reader processes: each field's
        levels split into blocks shared by the readers and written into one shared
        array per field.  {name: array} (without those that found no room in tmpfs),
        or None if cancelled."""
        from concurrent.futures import as_completed

        src, pool = self.source(t), self._get_pool()
        futs, vols = [], {}
        try:
            for n in names:
                _, ny, nx = self._vol_shape(n, t)
                shape = (len(ks), ny, nx) if rows is None else \
                    (len(ks), len(rows)) + (() if points else (len(cols),))
                try:
                    vols[n] = _SharedVolume(self._shm, shape)
                except OSError:
                    continue
                for p0, p1 in level_blocks((len(ks), ny, nx), 1, len(names), self.workers):
                    futs.append(pool.submit(_read_levels_worker, src, n, self.vars[n].stag,
                                            vols[n].path, p0, ks[p0:p1], rows, cols,
                                            points))
            pending = set(futs)
            for fut in as_completed(futs):
                pending.discard(fut)
                fut.result()
                if cancelled and pending and cancelled():
                    return None
            return {n: vols.pop(n).array() for n in list(vols)}
        finally:
            for f in futs:
                f.cancel()  # (those running write into a removed file, then stop)
            for v in vols.values():
                v.discard()

    def reduce_levels(self, name, t, op):
        """(nj, ni) float32: the max or min (op) over every level of a native 3D field
        (the volume's .max(axis=0) or .min), without its volume: the reader processes
        each reduce a block of levels, one level in memory at a time.  For a field
        whose volume does not fit the 3D cache (fits); a cached one is used as it is."""
        f = np.maximum if op == "max" else np.minimum
        vol = self.cached(name, t)
        if vol is None:
            self._check(name, t)
            if self.vars[name].zchunk > 4:  # (a level costs several: its volume)
                vol = self.volume(name, t)
        if vol is not None:
            return f.reduce(vol, axis=0)
        self._not_writing(t)
        nk, ny, nx = self._vol_shape(name, t)
        sv = None
        if self.workers > 1 and self._shm:
            blocks = level_blocks((nk, ny, nx), 1, 1, self.workers)
            try:
                sv = _SharedVolume(self._shm, (len(blocks), ny, nx))
            except OSError:  # (no room in tmpfs: read here)
                sv = None
        if sv is None:
            out = None
            for k in range(nk):
                check_cancelled()
                a = self._level_here(name, t, k)
                out = a if out is None else f(out, a)
            return out
        src, pool, futs = self.source(t), self._get_pool(), []
        try:
            for row, (k0, k1) in enumerate(blocks):
                futs.append(pool.submit(_reduce_block_worker, src, name,
                                        self.vars[name].stag, sv.path, row, k0, k1, op))
            for fut in futs:
                fut.result()
                check_cancelled()
            return f.reduce(sv.array(), axis=0)
        finally:
            for fut in futs:
                fut.cancel()
            sv.discard()

    def fits(self, nbytes):
        """Whether volumes of nbytes together belong in the 3D cache: within 1 /
        FIT_SHARE of its budget.  A larger request reads only the part of each field
        it needs (read_levels with rows and columns, reduce_levels)."""
        return nbytes <= self.cache_bytes // FIT_SHARE

    def read_box(self, name, t, i0, i1, j0, j1):
        """Columns [j0:j1, i0:i1] of a 3D field without populating the cache.  With
        one horizontal level per chunk this costs about as much as a full read, but
        keeps the cache for the times being browsed.  Read in a reader process when
        there are several CPUs (the in-process read would hold IO_LOCK for seconds)."""
        info = self.vars[name]
        self._check(name, t)
        self._not_writing(t)
        if self.workers > 1:
            return self._get_pool().submit(_read_box_worker, self.source(t), name, info.stag,
                                           (i0, i1, j0, j1)).result()
        with IO_LOCK:
            return _box(self._ds(t)[name], info.stag, i0, i1, j0, j1)

    def read_boxes(self, names, t, i0, i1, j0, j1):
        """{name: columns} for several 3D fields at one time and box: the reads go to the
        reader processes together (read_box one at a time would queue them one by one).
        Goes through read_box, so a subclass's read_box is honoured."""
        names = list(dict.fromkeys(names))
        if self.workers <= 1 or len(names) < 2:
            return {n: self.read_box(n, t, i0, i1, j0, j1) for n in names}
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(len(names)) as ex:  # (each just waits on its process)
            futs = {n: ex.submit(self.read_box, n, t, i0, i1, j0, j1) for n in names}
            return {n: f.result() for n, f in futs.items()}

    def _insert(self, name, t, vol, protect=()):
        self._vc.put((self.path, name, t), vol, {(self.path, n, t) for n in protect})

    def _read_volume_local(self, name, t):
        info = self.vars[name]
        with IO_LOCK:
            a = np.asarray(self._ds(t)[name][0], dtype=np.float32)
        return np.ascontiguousarray(_destagger(a, info.stag), dtype=np.float32)

    def volume(self, name, t):
        vol = self.cached(name, t)
        if vol is None:
            self.load_volumes([name], t)
            vol = self.cached(name, t)
            if vol is None:  # evicted at once by another job: read it uncached
                self._check(name, t)
                vol = self._read_volume_local(name, t)
        return vol

    def load_volumes(self, names, t, progress=None, cancelled=None):
        """Ensure several full 3D fields are cached; reads in reader processes (in
        parallel) when there is more than one CPU.  A field another job is already
        reading is waited for, not read twice.  Returns False if cancelled."""
        names = list(dict.fromkeys(names))
        on = getattr(_hook, "on", None)
        hooked = cancelled is None and on is not None and on[1] is not None
        if on and on[0] and on[0] is not progress:  # (the block hears it too)
            progress = on[0] if progress is None else _both(progress, on[0])
        if hooked:
            cancelled = on[1]
        if not self._load_volumes(names, t, progress, cancelled):
            if hooked:  # (callers that don't check the result can't use a partial read)
                raise Cancelled()
            return False
        return True

    def _load_volumes(self, names, t, progress, cancelled):
        for _ in range(3):  # (only repeats if a waited-for field was evicted at once)
            missing = [n for n in names if self.cached(n, t) is None]
            if not missing:
                return True
            for n in missing:
                self._check(n, t)
            self._not_writing(t)
            mine, waits = [], []
            with self._inflight_lock:
                for n in missing:
                    ev = self._inflight.get((n, t))
                    if ev is None:
                        self._inflight[(n, t)] = threading.Event()
                        mine.append(n)
                    else:
                        waits.append(ev)
            try:
                if mine and not self._read_into_cache(mine, t, names, progress, cancelled):
                    return False
            finally:
                with self._inflight_lock:
                    for n in mine:
                        self._inflight.pop((n, t)).set()
            for ev in waits:
                ev.wait()
        return True

    def _read_into_cache(self, missing, t, protect, progress, cancelled):
        total, done = len(missing), 0
        if progress:
            progress(done, total, missing[0])
        if self.workers > 1 and self._shm:
            return self._read_blocks(missing, t, protect, progress, cancelled)
        for n in missing:
            if cancelled and cancelled():
                return False
            if progress:
                progress(done, total, n)
            self._insert(n, t, self._read_volume_local(n, t), protect)
            done += 1
            if progress:
                progress(done, total, n)
        return True

    def _vol_shape(self, name, t):
        """(nk, nj, ni) of a 3D field on scalar points, from its variable's shape where
        the reader gives one (else the grid's)."""
        info = self.vars[name]
        with IO_LOCK:
            shp = getattr(self._ds(t)[name], "shape", None)
        if shp is None or len(shp) != 4:
            return self.nk, self.nj, self.ni
        nk, nj, ni = (int(s) for s in shp[1:])
        return nk - (info.stag == "z"), nj - (info.stag == "y"), ni - (info.stag == "x")

    def _read_blocks(self, missing, t, protect, progress, cancelled):
        """Read 3D fields in the reader processes, each split into level blocks shared
        by all the readers and written straight into one shared array per field (no
        copy back).  Fields complete (and enter the cache) in the order given."""
        from concurrent.futures import as_completed

        total, done = len(missing), 0
        src, pool = self.source(t), self._get_pool()
        futs, left, vols = {}, {}, {}
        try:
            for n in missing:
                shape = self._vol_shape(n, t)
                try:
                    vols[n] = _SharedVolume(self._shm, shape)
                except OSError:  # tmpfs full (or no fallocate): read it here instead
                    continue
                blocks = level_blocks(shape, self.vars[n].zchunk, len(missing),
                                      self.workers)
                left[n] = len(blocks)
                for k0, k1 in blocks:
                    futs[pool.submit(_read_block_worker, src, n, self.vars[n].stag,
                                     vols[n].path, k0, k1)] = n
            pending = set(futs)
            for fut in as_completed(futs):
                pending.discard(fut)
                fut.result()
                n = futs[fut]
                left[n] -= 1
                if left[n] == 0:
                    self._insert(n, t, vols.pop(n).array(), protect)
                    done += 1
                    if progress:
                        progress(done, total, n)
                if cancelled and pending and cancelled():
                    return False
        finally:
            for f in futs:
                f.cancel()  # (those running write into a removed file, then stop)
            for v in vols.values():
                v.discard()
        for n in missing:  # (those that found no room in tmpfs)
            if self.cached(n, t) is None and n not in left:
                if cancelled and cancelled():
                    return False
                self._insert(n, t, self._read_volume_local(n, t), protect)
                done += 1
                if progress:
                    progress(done, total, n)
        return True

    def _get_pool(self):
        """The reader processes: one pool for every run (core.pool)."""
        self._pool_uses += 1
        return pool.get(self.workers)

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
        if todo:
            self._not_writing(t)
        total = len(todo)
        if progress and todo:
            progress(0, total, todo[0])
        if self.workers > 1 and todo:
            from concurrent.futures import as_completed

            src, pool = self.source(t), self._get_pool()
            futs, parts = {}, {n: {} for n in todo}
            for n in todo:  # (level blocks: a reader holds a few levels, not a field)
                for k0, k1 in level_blocks(self._vol_shape(n, t), self.vars[n].zchunk,
                                           len(todo), self.workers):
                    futs[pool.submit(_mean_profile_worker, src, n, self.vars[n].stag,
                                     k0, k1)] = (n, k0)
            done = 0
            for fut in as_completed(futs):
                n, k0 = futs[fut]
                parts[n][k0] = fut.result()
                if len(parts[n]) == sum(1 for m, _ in futs.values() if m == n):
                    out[n] = self._means[(n, t)] = np.concatenate(
                        [parts[n][k] for k in sorted(parts[n])])
                    done += 1
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
        """(GB used, GB budget, fields) of the 3D cache (shared by the open runs)."""
        used, n = self._vc.info()
        return used / 1024**3, self.cache_bytes / 1024**3, n

    def clear_cache(self):
        """Free this run's cached volumes."""
        self._vc.drop(lambda k: k[0] == self.path)

    def trim_cache(self, nbytes):
        """Evict least-recently-used cached volumes (of any run) until `nbytes` are
        freed (or the cache is empty).  Returns the bytes freed."""
        return self._vc.trim(nbytes)

    def ij(self, x, y):
        """Nearest scalar-grid indices for a position in km."""
        i = int(np.clip(np.rint((x - self.xh[0]) * 1000.0 / self.dx), 0, self.ni - 1))
        j = int(np.clip(np.rint((y - self.yh[0]) * 1000.0 / self.dy), 0, self.nj - 1))
        return i, j

SCAN_POOL = 24  # files from which the first scan of a run goes to the reader processes


def _scan_worker(files):
    """[(time s, names of the (time, ...) 2D/3D fields)] of CM1 output files."""
    out = []
    for f in files:
        with netCDF4.Dataset(f) as d:
            out.append((float(d["time"][0]),
                        sorted(n for n, v in d.variables.items()
                               if v.dimensions[:1] == ("time",) and v.ndim in (3, 4))))
    return out


def scan_files(files, workers=1):
    """(times, field names) of CM1 output files, one entry a file: each is opened once,
    shared out over the reader processes when there are many (a run of hundreds of
    files opens in a fraction of the time)."""
    files = list(files)
    if workers > 1 and len(files) >= SCAN_POOL:
        step = max(4, -(-len(files) // (4 * workers)))
        parts = [files[i:i + step] for i in range(0, len(files), step)]
        got = [r for part in pool.get(workers).map(_scan_worker, parts) for r in part]
    else:
        with IO_LOCK:  # (netCDF/HDF5 is not thread safe)
            got = _scan_worker(files)
    return [g[0] for g in got], [g[1] for g in got]


class CM1Run(Run):
    """A folder of CM1 netCDF output (one time per file, names by output_glob)."""

    model = "cm1"
    model_label = "CM1"

    def __init__(self, path, cache_gb=12.0, workers=None, cache=None):
        super().__init__(path, cache_gb, workers, cache)
        from .. import config
        pat = config.get("output_glob")
        self.files = sorted(glob.glob(os.path.join(self.path, pat)))
        if not self.files:
            raise FileNotFoundError(f"no {pat} files found in {self.path}")

        with IO_LOCK, netCDF4.Dataset(self.files[0]) as d:
            self.xh = np.asarray(d["xh"][:], dtype=np.float64)  # km
            self.yh = np.asarray(d["yh"][:], dtype=np.float64)
            # scalar heights: "z" in CM1's own layout, "zh" in the CF-style one
            self.z = np.asarray(d["z" if "z" in d.variables else "zh"][:], dtype=np.float64)
            self.zf = np.asarray(d["zf"][:], dtype=np.float64)
            self.attrs = {k: d.getncattr(k) for k in d.ncattrs()}
            self.vars = {}
            for name, v in d.variables.items():
                info = _var_info(name, v)
                if info is not None:
                    self.vars[name] = info

        self._grid_done()
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
            with IO_LOCK, netCDF4.Dataset(self.files[ts[-1]]) as d:
                info = _var_info(n, d[n])
            if info is not None:
                self.vars[n] = info
                self.var_times[n] = frozenset(ts)
        for n in self.vars:
            ts = frozenset(t for t, ns in enumerate(names) if n in ns)
            if len(ts) < len(self.files) and n not in self.var_times:
                self.var_times[n] = ts

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
        times, names = scan_files(self.files, self.workers)
        try:
            os.makedirs(cdir, exist_ok=True)
            with open(cfile, "w") as f:
                json.dump(dict(times=times, vars=names), f)
        except OSError:
            pass
        return np.array(times, dtype=np.float64), [set(n) for n in names]

    def begin_write(self, t):
        """Close this process's handle on file t and refuse reads of it until
        end_write(t), so another process can open it for writing."""
        with IO_LOCK:
            self._writing.add(t)
            d = self._open.pop(t, None)
            if d is not None:
                d.close()
        pool.release()  # (the reader processes keep the files they last read open)

    def end_write(self, t, names=()):
        """File t is readable again; `names` were written into it."""
        with IO_LOCK:
            self._writing.discard(t)
            if names:
                with netCDF4.Dataset(self.files[t]) as d:
                    for n in names:
                        if n in d.variables:
                            self.vars[n] = _var_info(n, d[n])
                            if n in self.var_times:
                                self.var_times[n] = self.var_times[n] | {t}
        self.forget(names, t)  # cached volumes of rewritten fields are stale
