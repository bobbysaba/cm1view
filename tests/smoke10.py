"""Headless checks of the data-layer fixes: reads in reader processes (the map is not
blocked), de-duplicated reads, cached derived volumes, one cache shared by runs,
base state from domain means.  Usage: python tests/smoke10.py"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import netCDF4
from cm1view.registry import Registry

PHD = "/glade/derecho/scratch/rasaba/phd"


def main():
    reg = Registry(f"{PHD}/test/initiation/c", 12, None)
    run, F = reg.get()
    print("workers:", run.workers)
    T = 44

    # ---- a volume read in progress does not block plane reads (map) any more
    th = threading.Thread(target=run.volume, args=("th", T))
    th.start()
    time.sleep(0.3)
    t0 = time.time()
    F.plane("winterp", T, "height", 3.0)
    print(f"map plane during a volume read: {time.time() - t0:.2f}s")
    th.join()

    # ---- two jobs asking for the same field: one read
    reads = []
    orig = run._read_into_cache

    def counting(missing, *a, **k):
        reads.extend(missing)
        return orig(missing, *a, **k)
    run._read_into_cache = counting
    t0 = time.time()
    ths = [threading.Thread(target=run.volume, args=("qv", T)) for _ in range(3)]
    [x.start() for x in ths]
    [x.join() for x in ths]
    print(f"3 jobs, same field: read {reads.count('qv')} time(s), {time.time() - t0:.1f}s")
    run._read_into_cache = orig

    # ---- derived volumes cached
    t0 = time.time()
    a = F.volume("thpert", T)
    t1 = time.time()
    b = F.volume("thpert", T)
    print(f"derived θ′ volume: first {t1 - t0:.1f}s, again {time.time() - t1:.3f}s, "
          f"same object {a is b}")
    st = (12.0, 9.0)
    t0 = time.time()
    F.volume("wstream", T, st)
    t1 = time.time()
    F.volume("wstream", T, st)
    print(f"streamwise (storm-relative) volume: first {t1 - t0:.1f}s, again "
          f"{time.time() - t1:.3f}s; other motion is a separate entry: "
          f"{F.volume('wstream', T, (0.0, 0.0)) is not F.volume('wstream', T, st)}")
    F.forget(T, ["th"])
    print("after forget(th): θ′ dropped", run.cached("~thpert", T) is None)

    # ---- one cache for all runs: opening another run keeps this run's fields
    n_before = sum(1 for k in run._vc._d if k[0] == run.path)
    run2, F2 = reg.get(f"{PHD}/test/initiation/b")
    run2.volume("th", len(run2.files) - 1)
    n_after = sum(1 for k in run._vc._d if k[0] == run.path)
    used, cap, n = run.cache_info()
    print(f"run c fields cached before/after opening run b: {n_before}/{n_after}; "
          f"shared cache {used:.1f}/{cap:.0f} GB, {n} fields, same object "
          f"{run._vc is run2._vc}")

    # ---- base state: domain means == the old corner column
    m = run.mean_profiles(("th0", "u0"), 0)
    with netCDF4.Dataset(run.files[0]) as d:
        col_th = np.asarray(d["th0"][0, :, 0, 0], float)
    print("base th0 mean vs corner column: max diff", float(np.abs(m["th0"] - col_th).max()))
    print("ok")


if __name__ == "__main__":
    main()
