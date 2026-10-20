"""Pressure decomposition written into the output file: a fresh write, and an
overwrite of fields from the older script.  RUN ONLY ON COPIES of output files.
Usage: python tests/smoke8.py NEW_RUN_COPY OLD_RUN_COPY   (each: first file + one more)"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import netCDF4
from cm1view.registry import Registry
from cm1view import app as A, pdecomp
from cm1view.run import CM1Run

txt = lambda h: re.sub("<[^>]+>", "", h or "")  # noqa: E731


def wait(pred, tmax=900):
    t0 = time.time()
    while not pred() and time.time() - t0 < tmax:
        time.sleep(0.3)
    return time.time() - t0


def check(path, before):
    print(f"\n=== {path}  (before: {before})")
    reg = Registry(path, 4, None)
    run, F = reg.get()
    T = 1
    print("source before:", pdecomp.source(run, T))
    v = A.Viewer(run, F)
    v.main()
    v.tslider.value = T
    v.fill_var.value = "p_b"
    v.fill_mode.value, v.fill_lvl.value = "level", 10.0
    v.request_map()
    wait(lambda: v.pd_row.visible, 300)
    print("button:", v.pd_btn.name, "| write:", v.pd_write.value)
    size0 = os.path.getsize(run.files[T])
    phases = set()
    t0 = time.time()
    v._on_pd_compute(None)
    wait(lambda: "computed in" in (v.status.object or "") or "failed" in (v.status.object or "")
         or "needs about" in (v.status.object or ""), 900)
    print(f"status: {txt(v.status.object)} [{time.time() - t0:.0f}s]")
    wait(lambda: "decomposition" in (v.map_title.object or ""), 120)
    time.sleep(1)
    print("map title:", txt(v.map_title.object))
    print("button visible after:", v.pd_row.visible, "| writing set empty:", not run._writing)
    print(f"file size {size0 / 1e9:.1f} -> {os.path.getsize(run.files[T]) / 1e9:.1f} GB")
    with netCDF4.Dataset(run.files[T]) as d:
        for n in pdecomp.NAMES:
            x = d[n]
            a = np.asarray(x[0, 10])
            m = run.extra[(n, T)][10]
            print(f"  {n}: {x.dtype} dims {x.dimensions} version "
                  f"{getattr(x, 'pdecomp_version', '-')!r}; max|file - memory| "
                  f"{np.abs(a - m).max():.2e} (max |value| {np.abs(a).max():.3g})")
    # a fresh start reads it from the file
    run2 = CM1Run(path, cache_gb=4, workers=1)
    from cm1view.fields import Fields
    F2 = Fields(run2)
    print("fresh start:", pdecomp.source(run2, T), "| p_b in file at t:", run2.in_file("p_b", T))
    a = F2.plane("p_b", T, "level", 10)
    print("  plane from file vs computed: max diff", float(np.abs(a - run.extra[("p_b", T)][10]).max()))


def main():
    check(sys.argv[1], "no decomposition")
    check(sys.argv[2], "older-script fields")
    print("ok")


if __name__ == "__main__":
    main()
