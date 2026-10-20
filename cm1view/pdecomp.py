"""Pressure decomposition (p_b, p_l, p_nl and the matching vertical accelerations).

The fields come from the output files when post-processing wrote them there, or are
computed here for one time on request by running the user's own
`pdecomp_new_fixed.py` (phd_scripts) unchanged, in a separate process: it peaks at
~30 GB (float64, full domain) and takes ~1-1.5 min per time on one CPU, so the
viewer's memory is freed again as soon as it is done.  Computed fields are kept in
memory (run.extra) for the last MAX_TIMES times and are never written to the files.
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
SCRIPT = os.environ.get("CM1VIEW_PDECOMP",
                        "/glade/work/rasaba/phd_scripts/pdecomp_new_fixed.py")
NEEDS = ("th", "qv", "pi", "rho", "prs")
NEED_GB = 34.0     # free memory wanted before starting (peak ~30 GB)
EXPECT_S = 90.0    # typical duration on one CPU, for the progress message
MAX_TIMES = 2      # computed times kept in memory (6 float32 volumes each)

_lock = threading.Lock()
_running = {}      # (run path, t) -> started (time.time())


def script():
    return SCRIPT if os.path.isfile(SCRIPT) else None


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
    'file-old' | None, description)."""
    if all((n, t) in run.extra for n in NAMES):
        return "computed", "computed here with pdecomp_new_fixed.py"
    if not run.in_file("p_b", t):
        return None, "not available"
    key = (run.path, t)
    if key not in _version_cache:
        with IO_LOCK:
            v = run._ds(t)["p_b"]
            _version_cache[key] = getattr(v, "pdecomp_version", "")
    ver = _version_cache[key]
    if ver:
        return "file-fixed", f"from the output file ({ver})"
    return "file-old", ("from the output file, written by an earlier pdecomp script "
                        "(no pdecomp_version; pdecomp_new.py swapped x and y in p_b and "
                        "p_l)")


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
class _ZAsZh:
    """The script reads heights as 'zh'; older CM1 files call them 'z'."""

    def __init__(self, d):
        self._d = d

    def __getitem__(self, k):
        if k == "zh" and "zh" not in self._d.variables:
            k = "z"
        return self._d[k]

    def __getattr__(self, k):
        return getattr(self._d, k)


def _worker(script_path, run_path, file0, file_t, outdir):
    """Process-pool worker: run the script's decomposition on file_t (write=False) and
    save the six fields as float32 .npy files; returns {name: path} and the log."""
    import netCDF4 as nc

    spec = importlib.util.spec_from_file_location("cm1view_user_pdecomp", script_path)
    P = importlib.util.module_from_spec(spec)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        spec.loader.exec_module(P)
        with nc.Dataset(file0) as d0:
            periodic = P.lbc_type(run_path.rstrip("/") + "/")
            dom = P.domain_info(_ZAsZh(d0))
            base = P.compute_base_state(d0)
        solver = P.setup_pressure_solver(dom, base, periodic)
        out = P.pressure_decomposition(file_t, dom, base, solver, write=False)
    paths, tag = {}, uuid.uuid4().hex
    for n in NAMES:
        p = os.path.join(outdir, f"cm1view-pdecomp-{os.getpid()}-{tag}-{n}.npy")
        np.save(p, np.asarray(out[n], dtype=np.float32))
        paths[n] = p
    return paths, log.getvalue()


def compute(run, t, progress=None):
    """Decompose time t with the user's script; stores the fields in run.extra.
    progress(elapsed_s, message) is called about once a second.  Raises RuntimeError
    with a readable message on failure."""
    key = (run.path, t)
    with _lock:
        if key in _running:
            raise RuntimeError(f"already being computed for {run.time_label(t)}")
        _running[key] = time.time()
    try:
        return _compute(run, t, progress)
    finally:
        with _lock:
            _running.pop(key, None)


def _compute(run, t, progress):
    sp = script()
    if sp is None:
        raise RuntimeError(f"pressure decomposition script not found: {SCRIPT}")
    free = free_gb()
    if free < NEED_GB:  # make room from the 3D cache first
        run.trim_cache(int((NEED_GB - free) * 1024**3))
        time.sleep(0.5)
        free = free_gb()
        if free < NEED_GB:
            raise RuntimeError(
                f"needs about {NEED_GB:.0f} GB of free memory, the job has {free:.0f} GB "
                f"free after emptying the 3D cache (start the viewer in a job with more "
                f"memory, or with a smaller --cache-gb)")
    import multiprocessing as mp

    outdir = "/dev/shm" if os.path.isdir("/dev/shm") else os.path.expanduser("~/.cache")
    pool = ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"))
    t0 = time.time()
    try:
        fut = pool.submit(_worker, sp, run.path, run.files[0], run.files[t], outdir)
        while True:
            try:
                paths, log = fut.result(timeout=1.0)
                break
            except FutTimeout:
                if progress:
                    progress(time.time() - t0, "")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"pressure decomposition failed: {type(e).__name__}: {e}") from e
    finally:
        pool.shutdown(wait=True)  # the worker process exits: its memory is freed
    try:
        vols = {n: np.load(p) for n, p in paths.items()}
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
    return time.time() - t0, log
