"""Pressure decomposition (p_b, p_l, p_nl and the matching vertical accelerations).

The fields come from the output files when post-processing wrote them there, or are
computed here for one time on request by running the user's own
`pdecomp_new_fixed.py` (phd_scripts) unchanged, in a separate process, so the
viewer's memory is freed again as soon as it is done.  With several CPUs and enough
memory the script's inputs are read in parallel first and its FFTs use several
threads (~45 s with 4 CPUs, ~40 GB peak; otherwise ~80 s, ~30 GB): the math is the
script's own either way.  The result is kept in memory (run.extra) for the last
MAX_TIMES times and, on request, written into the output file with the script's own
write_data (float64, with its pdecomp_version attribute), replacing older values.
"""

import contextlib
import importlib.util
import io
import os
import threading
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutTimeout

import numpy as np

from .run import IO_LOCK, VarInfo

NAMES = ("p_b", "p_l", "p_nl", "acc_b", "acc_l", "acc_nl")
_PHD = "/glade/work/rasaba/phd_scripts"
# the multi-CPU version (same math) when it is there, else the original fixed script
SCRIPT = os.environ.get("CM1VIEW_PDECOMP") or next(
    (p for p in (f"{_PHD}/pdecomp_new_fixed_mp.py", f"{_PHD}/pdecomp_new_fixed.py")
     if os.path.isfile(p)), f"{_PHD}/pdecomp_new_fixed.py")
NEEDS = ("th", "qv", "pi", "rho", "prs")
NEED_GB = 34.0     # free memory wanted before starting (serial reads: peak ~30 GB)
NEED_GB_PAR = 44.0  # inputs read in parallel up front: peak ~40 GB, ~45 s with 4 CPUs
EXPECT_S = {False: 85.0, True: 50.0}  # typical durations (serial / parallel reads)
MAX_TIMES = 2      # computed times kept in memory (6 float32 volumes each)

_lock = threading.Lock()
_running = {}      # (run path, t) -> started (time.time())


def script():
    return SCRIPT if os.path.isfile(SCRIPT) else None


def script_name():
    return os.path.basename(SCRIPT)


def can_compute(run):
    return (script() is not None and all(run.has(n) for n in NEEDS)
            and (run.has("w") or run.has("winterp")))


def register(run):
    """Make the decomposition fields known to the run even where no file has them,
    so they can be chosen (and computed) anywhere."""
    if not can_compute(run):
        return
    units = {"p": "Pa", "a": "m/s^2"}
    for n in NAMES:
        if n not in run.vars:
            run.vars[n] = VarInfo(n, n, units[n[0]], 3, None)
            run.var_times[n] = frozenset()


def is_pdecomp(F, name):
    """True for a decomposition field or one derived from them."""
    if not name or name not in F:
        return False
    return name in NAMES or any(d in NAMES for d in F[name].deps)


def available(run, t):
    return all((n, t) in run.extra or run.in_file(n, t) for n in NAMES)


_version_cache = {}


def source(run, t):
    """Where the decomposition at time t comes from: ('computed' | 'file-fixed' |
    'file-old' | 'busy' | None, description)."""
    from .run import FileBusy

    kind = None
    if run.in_file("p_b", t):
        key = (run.path, t)
        if key not in _version_cache:
            try:
                with IO_LOCK:
                    v = run._ds(t)["p_b"]
                    _version_cache[key] = getattr(v, "pdecomp_version", "")
            except FileBusy:
                return "busy", "being written to the output file"
        ver = _version_cache[key]
        kind = "file-fixed" if ver else "file-old"
    if all((n, t) in run.extra for n in NAMES):
        if kind == "file-fixed":
            return "computed", (f"computed here with {script_name()} and written to the "
                                f"output file")
        return "computed", f"computed here with {script_name()} (in memory only)"
    if kind == "file-fixed":
        return kind, f"from the output file ({_version_cache[(run.path, t)]})"
    if kind == "file-old":
        return kind, ("from the output file, written by an earlier pdecomp script (no "
                      "pdecomp_version; pdecomp_new.py swapped x and y in p_b and p_l)")
    return None, "not available"


def running(run, t=None):
    with _lock:
        if t is None:
            return [tt for (p, tt) in _running if p == run.path]
        return _running.get((run.path, t))


# ------------------------------------------------------------------ memory
def _cgroup_mem():
    """(limit, used) bytes of this job's memory cgroup, or None."""
    try:
        v = open("/sys/fs/cgroup/memory.max").read().strip()
        if v != "max":
            return int(v), int(open("/sys/fs/cgroup/memory.current").read())
    except OSError:
        pass
    try:
        cg = [ln.split(":")[2].strip() for ln in open("/proc/self/cgroup")
              if ":memory:" in ln][0]
        base = f"/sys/fs/cgroup/memory{cg}"
        lim = int(open(f"{base}/memory.limit_in_bytes").read())
        stat = dict(ln.split() for ln in open(f"{base}/memory.stat"))
        # page cache (e.g. of the netCDF files) is reclaimable: count rss only
        used = int(stat.get("total_rss", stat.get("rss", 0))) + \
            int(stat.get("total_shmem", stat.get("shmem", 0)))
        if lim < 1 << 50:
            return lim, used
    except (OSError, IndexError, ValueError):
        pass
    return None


def free_gb():
    m = _cgroup_mem()
    if m is not None:
        return (m[0] - m[1]) / 1024**3
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3
    except (ValueError, OSError):
        return float("inf")


# ------------------------------------------------------------------ worker
class _Inputs:
    """A netCDF4.Dataset stand-in for the script: variables read beforehand (in
    parallel) come from memory, anything else from the file; heights are read as
    'zh' by the script but called 'z' in older CM1 files."""

    def __init__(self, path, arrays, mode="r"):
        self._d = nc_dataset(path, mode)
        self._a = arrays

    def __getitem__(self, k):
        if k == "zh" and "zh" not in self._d.variables:
            k = "z"
        return self._a[k] if k in self._a else self._d[k]

    def __getattr__(self, k):
        return getattr(self._d, k)

    def close(self):
        self._d.close()


def nc_dataset(path, mode="r"):
    import netCDF4
    return netCDF4.Dataset(path, mode)


def _load(paths):
    out = {}
    for n, p in paths.items():
        out[n] = np.load(p)
        os.remove(p)
    return out


def _worker(script_path, run_path, file0, file_t, pre0, pre_t, nthreads, outdir, write,
            ready, go):
    """Process-pool worker: the script's decomposition of file_t (write=False), then,
    with `write`, its write_data into file_t once the viewer has let go of the file
    (ready -> go).  Saves the six fields as float32 .npy; returns paths, log, wrote."""
    import types
    import scipy.fft

    spec = importlib.util.spec_from_file_location("cm1view_user_pdecomp", script_path)
    P = importlib.util.module_from_spec(spec)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        spec.loader.exec_module(P)
        a0, at = _load(pre0), _load(pre_t)
        # the script opens file_t itself: hand it the pre-read inputs
        P.nc = types.SimpleNamespace(
            Dataset=lambda p, mode="r": _Inputs(p, at if p == file_t else {}, mode))
        with scipy.fft.set_workers(nthreads):
            d0 = _Inputs(file0, a0)
            periodic = P.lbc_type(run_path.rstrip("/") + "/")
            dom = P.domain_info(d0)
            base = P.compute_base_state(d0)
            d0.close()
            del a0
            solver = P.setup_pressure_solver(dom, base, periodic)
            out = P.pressure_decomposition(file_t, dom, base, solver, write=False)
        del at
        wrote = False
        if write:
            ready.set()
            if not go.wait(600):
                raise RuntimeError("the viewer did not release the file for writing")
            ds = nc_dataset(file_t, "r+")
            try:
                P.write_data(ds, out)
            finally:
                ds.close()
            wrote = True
    paths, tag = {}, uuid.uuid4().hex
    for n in NAMES:
        p = os.path.join(outdir, f"cm1view-pdecomp-{os.getpid()}-{tag}-{n}.npy")
        np.save(p, np.asarray(out[n], dtype=np.float32))
        paths[n] = p
    return paths, log.getvalue(), wrote


def writable(run, t):
    return os.access(run.files[t], os.W_OK)


def compute(run, t, progress=None, write=False):
    """Decompose time t with the user's script; stores the fields in run.extra and,
    with `write`, writes them into the output file (replacing older values).
    progress(elapsed_s, phase) is called about once a second.  Returns dict(elapsed,
    wrote, parallel, log).  Raises RuntimeError with a readable message on failure."""
    key = (run.path, t)
    with _lock:
        if key in _running:
            raise RuntimeError(f"already being computed for {run.time_label(t)}")
        _running[key] = time.time()
    try:
        return _compute(run, t, progress, write)
    finally:
        with _lock:
            _running.pop(key, None)


def _inputs(run, t):
    """Fields the script reads from file t and from the first file."""
    hyd = [n for n in ("qc", "qr", "qi", "qs", "qg", "qhl") if run.has(n)]
    at = ["th", "qv", *hyd, "pi", "rho", "w" if run.has("w") else "winterp"]
    a0 = ["pi" if run.has("pi") else "prs", "th", "qv"]
    return at, a0


def _compute(run, t, progress, write):
    import multiprocessing as mp

    sp = script()
    if sp is None:
        raise RuntimeError(f"pressure decomposition script not found: {SCRIPT}")
    if write and not writable(run, t):
        raise RuntimeError(f"no write permission for {run.files[t]}")
    ncpu = len(os.sched_getaffinity(0))
    free = free_gb()
    want = NEED_GB_PAR if ncpu > 1 else NEED_GB
    if free < want:  # make room from the 3D cache first
        run.trim_cache(int((want - free) * 1024**3))
        time.sleep(0.5)
        free = free_gb()
    parallel = ncpu > 1 and free >= NEED_GB_PAR
    if not parallel and free < NEED_GB:
        raise RuntimeError(
            f"needs about {NEED_GB:.0f} GB of free memory, the job has {free:.0f} GB free "
            f"after emptying the 3D cache (start the viewer in a job with more memory, or "
            f"with a smaller --cache-gb)")
    outdir = "/dev/shm" if os.path.isdir("/dev/shm") else os.path.expanduser("~/.cache")
    ctx = mp.get_context("spawn")
    t0 = time.time()
    pre0, pre_t, began, wrote = {}, {}, False, False

    def tick(phase):
        if progress:
            progress(time.time() - t0, phase)

    try:
        if parallel:  # read the script's inputs in parallel, straight to /dev/shm
            at, a0 = _inputs(run, t)
            run._not_writing(t)
            with ProcessPoolExecutor(min(ncpu, 8), mp_context=ctx) as ex:
                futs = {("t", n): ex.submit(_read_raw, run.files[t], n, outdir) for n in at}
                futs.update({("0", n): ex.submit(_read_raw, run.files[0], n, outdir)
                             for n in a0})
                while not all(f.done() for f in futs.values()):
                    tick("reading")
                    time.sleep(1.0)
                for (w, n), f in futs.items():
                    (pre_t if w == "t" else pre0)[n] = f.result()
        mgr = ctx.Manager()
        ready, go = mgr.Event(), mgr.Event()
        pool = ProcessPoolExecutor(max_workers=1, mp_context=ctx)
        try:
            fut = pool.submit(_worker, sp, run.path, run.files[0], run.files[t], pre0,
                              pre_t, min(ncpu, 8), outdir, write, ready, go)
            pre0, pre_t = {}, {}  # the worker owns (and removes) them now
            while True:
                try:
                    paths, log, wrote = fut.result(timeout=1.0)
                    break
                except FutTimeout:
                    if write and not began and ready.is_set():
                        run.begin_write(t)  # let go of the file, then let it write
                        began = True
                        go.set()
                    tick("writing to the file" if began else "computing")
        finally:
            pool.shutdown(wait=True)  # the worker exits: its memory is freed
            mgr.shutdown()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"pressure decomposition failed: {type(e).__name__}: {e}") from e
    finally:
        for p in list(pre0.values()) + list(pre_t.values()):
            with contextlib.suppress(OSError):
                os.remove(p)
        if began:
            run.end_write(t, NAMES if wrote else ())
            _version_cache.pop((run.path, t), None)
    try:
        vols = _load(paths)
    finally:
        for p in paths.values():
            with contextlib.suppress(OSError):
                os.remove(p)
    with run._cache_lock:
        for n, a in vols.items():
            run.extra[(n, t)] = a
        times = list(dict.fromkeys(tt for (n, tt) in run.extra if n in NAMES))
        for old in times[:-MAX_TIMES]:
            for n in NAMES:
                run.extra.pop((n, old), None)
    return dict(elapsed=time.time() - t0, wrote=wrote, parallel=parallel, log=log)


def _read_raw(path, name, outdir):
    """Process-pool worker: one variable exactly as stored (time axis kept), to .npy."""
    import netCDF4
    with netCDF4.Dataset(path) as d:
        d.set_auto_mask(False)
        a = np.asarray(d[name][:])
    out = os.path.join(outdir, f"cm1view-pdin-{os.getpid()}-{uuid.uuid4().hex}.npy")
    np.save(out, a)
    return out
