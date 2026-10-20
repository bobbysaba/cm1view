"""Pressure decomposition: one at a time (a second time waits, the same time is
refused), and a failed write keeps the computed fields in memory and releases the
file.  RUN ONLY ON A COPY of output files (first file + two more).
Usage: python tests/smoke11.py RUN_COPY"""
import os
import stat
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import netCDF4
from cm1view.registry import Registry
from cm1view import pdecomp


def main():
    reg = Registry(sys.argv[1], 4, None)
    run, F = reg.get()
    phases = {1: [], 2: []}
    res, err = {}, {}

    def job(t, write=False):
        try:
            res[t] = pdecomp.compute(run, t, lambda s, ph: phases[t].append(ph), write=write)
        except Exception as e:  # noqa: BLE001
            err[t] = e

    # ---- queue
    print("=== queue")
    a = threading.Thread(target=job, args=(1,))
    a.start()
    while not phases[1]:
        time.sleep(0.2)
    b = threading.Thread(target=job, args=(2,))
    b.start()
    try:
        pdecomp.compute(run, 1)
        print("FAIL: same time computed twice")
    except RuntimeError as e:
        print("same time again refused:", e)
    a.join()
    print(f"time 1 done ({res[1]['elapsed']:.0f}s); time 2 waited:",
          "waiting for another decomposition" in phases[2])
    b.join()
    print(f"time 2 done ({res[2]['elapsed']:.0f}s); errors: {err or 'none'}")
    print("running list empty:", pdecomp.running(run) == [])
    print("both in memory:", all((n, t) in run.extra for n in pdecomp.NAMES for t in (1, 2)))

    # ---- failed write
    print("=== failed write")
    T = 1
    path = run.files[T]
    with netCDF4.Dataset(path) as d:
        before = set(d.variables)
    for n in pdecomp.NAMES:
        run.extra.pop((n, T), None)
    phases[T].clear()
    res.pop(T, None)
    mode = os.stat(path).st_mode
    th = threading.Thread(target=job, args=(T, True))
    th.start()
    while "computing" not in phases[T] and th.is_alive():
        time.sleep(0.2)
    os.chmod(path, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    print("file made read-only during compute")
    th.join()
    os.chmod(path, mode)
    r = res.get(T)
    if r is None:
        print("FAIL: compute raised", err.get(T))
        return
    print("wrote:", r["wrote"], "| write_error:", r["write_error"])
    print("kept in memory:", all((n, T) in run.extra for n in pdecomp.NAMES))
    print("file released (writing set empty):", not run._writing)
    with netCDF4.Dataset(path) as d:
        print("file variables unchanged:", set(d.variables) == before)
    print("source:", pdecomp.source(run, T))
    F.plane("p_b", T, "level", 10)
    print("plane of p_b from memory: ok")
    print("ok")


if __name__ == "__main__":
    main()
