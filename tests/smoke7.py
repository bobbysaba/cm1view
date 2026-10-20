"""Headless checks for θρ, streamwise / crosswise vorticity and the pressure
decomposition (computed on demand, and read from post-processed files).
Usage: python tests/smoke7.py"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import netCDF4
from cm1view.registry import Registry
from cm1view import app as A, pdecomp

PHD = "/glade/derecho/scratch/rasaba/phd"
txt = lambda h: re.sub("<[^>]+>", "", h or "")  # noqa: E731


def wait(pred, tmax=900):
    t0 = time.time()
    while not pred() and time.time() - t0 < tmax:
        time.sleep(0.3)
    return time.time() - t0


def main():
    reg = Registry(f"{PHD}/test/initiation/c", 16, 1)
    run, F = reg.get()
    print("new fields:", [n for n in ("thrho", "thrhopert", "wstream", "wcross", "p_b", "p_l",
                                      "p_nl", "acc_b", "acc_l", "acc_nl", "p_dyn", "acc_dyn",
                                      "acc_tot") if n in F])
    print("decomposition script:", pdecomp.script(), "can compute:", pdecomp.can_compute(run))
    T, K = 48, 10

    # ---- θρ against funcs.theta_rho, straight from the file
    with netCDF4.Dataset(run.files[T]) as d:
        g = lambda n: np.asarray(d[n][0, K], np.float64)  # noqa: E731
        q = sum(g(n) for n in ("qc", "qr", "qi", "qs", "qg") if n in d.variables)
        q = q + (g("qhl") if "qhl" in d.variables else 0)
        eps = 287.04 / 461.51
        ref = g("th") * (1 + g("qv") / eps) / (1 + g("qv") + q)
    a = F.plane("thrho", T, "level", K)
    print(f"θρ vs funcs.theta_rho at k={K}: max |diff| = {np.abs(a - ref).max():.4f} K "
          f"(range {ref.min():.1f}..{ref.max():.1f})")
    tp = F.plane("thrhopert", T, "level", K)
    print(f"θρ′ at k={K}: {tp.min():.2f}..{tp.max():.2f} K")

    # ---- streamwise / crosswise vorticity: domain motion, then tracked motion
    v = A.Viewer(run, F)
    v.main()
    v.tslider.value = T
    v.fill_var.value = "wstream"
    v.fill_mode.value, v.fill_lvl.value = "height", 0.5
    v.request_map()
    wait(lambda: "Streamwise" in (v.map_title.object or ""))
    time.sleep(1)
    print("map title:", txt(v.map_title.object))
    print("colorbar:", v.cbar_label.axis_label)
    ws0 = F.plane("wstream", T, "height", 0.5)
    # independent check of the definition with the domain motion
    xv, yv = run.read_height("xvort", T, 0.5), run.read_height("yvort", T, 0.5)
    u, w_ = run.read_height("uinterp", T, 0.5), run.read_height("vinterp", T, 0.5)
    sp_ = np.hypot(u, w_)
    print("streamwise check (grid-relative = umove/vmove frame): max |diff|",
          float(np.nanmax(np.abs(ws0 - (xv * u + yv * w_) / np.maximum(sp_, 1e-6)))))
    wc0 = F.plane("wcross", T, "height", 0.5)
    print("|ω_h|² = ω_s² + ω_c²:", float(np.nanmax(np.abs(ws0**2 + wc0**2 - xv**2 - yv**2))))
    v.request_track(None, None)
    wait(lambda: v.trk_stop_btn.disabled and v.fixes)
    wait(lambda: "tracked" in (v.map_title.object or ""), 60)
    print("after tracking:", txt(v.map_title.object))
    st = v._field_storm(T)
    ws1 = F.plane("wstream", T, "height", 0.5, storm=st[0])
    print(f"tracked motion {st[0][0]:.1f}, {st[0][1]:.1f} m/s: streamwise changed by up to "
          f"{np.nanmax(np.abs(ws1 - ws0)):.4f} 1/s")

    # ---- decomposition missing -> compute through the button
    v.fill_var.value = "p_b"
    v.fill_mode.value, v.fill_lvl.value = "level", float(K)
    v.request_map()
    wait(lambda: v.pd_btn.visible, 120)
    print("status:", txt(v.status.object))
    print("button:", v.pd_btn.visible, v.pd_btn.name)
    t0 = time.time()
    v._on_pd_compute(None)
    wait(lambda: "computed in" in (v.status.object or "") or "failed" in (v.status.object or "")
         or "needs about" in (v.status.object or ""), 900)
    print(f"compute: {txt(v.status.object)} [{time.time() - t0:.0f}s wall]")
    wait(lambda: "decomposition computed" in (v.map_title.object or ""), 120)
    print("map title:", txt(v.map_title.object))
    print("button after:", v.pd_btn.visible)
    with netCDF4.Dataset(run.files[T]) as d, netCDF4.Dataset(run.files[0]) as d0:
        for k in (1, 10, 50):
            pp = np.asarray(d["prs"][0, k], float) - np.asarray(d0["prs"][0, k], float)
            s = sum(run.extra[(n, T)][k].astype(float) for n in ("p_b", "p_l", "p_nl"))
            print(f"  k={k}: max|p_b| {np.abs(run.extra[('p_b', T)][k]).max():.0f} Pa, "
                  f"max|p_b+p_l+p_nl - p'| = {np.abs(s - pp).max():.2f} Pa")
    for n in ("acc_dyn", "acc_tot", "p_dyn"):
        a = F.plane(n, T, "height", 3.0)
        print(f"  {n} at 3 km: {np.nanmin(a):.3g}..{np.nanmax(a):.3g}")

    # ---- post-processed run: fields from the files (older script)
    run2, F2 = reg.get(f"{PHD}/cp20/ntor_125m")
    ts = sorted(run2.var_times["p_b"])
    print(f"cp20/ntor_125m: p_b in {len(ts)} of {len(run2.files)} files, "
          f"from {run2.time_label(ts[0])}; zchunk {run2.vars['p_b'].zchunk}")
    v2 = A.Viewer(run2, F2)
    v2.main()
    v2.tslider.value = 0
    v2.fill_var.value = "acc_dyn"
    wait(lambda: v2.pd_btn.visible or "acc" in (v2.map_title.object or ""), 120)
    time.sleep(1)
    print("t=0:", txt(v2.status.object), "| button:", v2.pd_btn.name)
    tt = ts[len(ts) // 2]
    t0 = time.time()
    v2.tslider.value = tt
    wait(lambda: run2.time_label(tt) in (v2.map_title.object or "")
         and "Dynamic" in (v2.map_title.object or ""), 300)
    print(f"t={run2.time_label(tt)} [{time.time() - t0:.1f}s]:", txt(v2.map_title.object))
    print("button:", v2.pd_btn.visible, v2.pd_btn.name)
    print("ok")


if __name__ == "__main__":
    main()
