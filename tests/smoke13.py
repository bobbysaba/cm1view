"""Headless checks: Series tab (time series of a field reduced over a region).
Writes only to a temporary folder (cache and saved files).
Usage: python tests/smoke13.py"""
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cm1view.registry import Registry
from cm1view import app as A
from cm1view import series as S

RUN = "/glade/derecho/scratch/rasaba/phd/test/initiation/c"


def wait(pred, tmax=900):
    t0 = time.time()
    while not pred() and time.time() - t0 < tmax:
        time.sleep(0.2)
    return time.time() - t0


def main():
    tmp = tempfile.mkdtemp(prefix="cm1view-smoke13-",
                           dir=os.environ.get("TMPDIR") or None)
    S.CACHE_DIR = os.path.join(tmp, "cache")
    reg = Registry(RUN, 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F)
    v.main()
    nt = len(run.times)
    done = lambda: not v.ser_go.disabled  # noqa: E731

    # ---- min θ′ at 1 km, whole domain
    v.ser_field.value, v.ser_z.value, v.ser_reduce.value = "thpert", 1.0, "min"
    v.ser_region.value = "domain"
    v._on_ser_compute(None)
    dt = wait(done)
    s = v.series[v.ser_pick.value]
    ds = s["ds"]
    print(f"min θ′ 1 km: {dt:.1f} s, computed {int(ds.computed.sum())}/{nt}:",
          np.round(ds.value.values[::11], 2))
    assert int(ds.computed.sum()) == nt
    # same value as the map field at one time
    t = 40
    ref = float(np.nanmin(F.plane("thpert", t, "height", 1.0)))
    print("  check t=40:", round(ds.value.values[t], 4), "map plane min:", round(ref, 4))
    assert abs(ds.value.values[t] - ref) < 1e-3
    print("  status:", v.ser_status.object)

    # ---- cached: a new viewer gets it without computing
    v2 = A.Viewer(run, F)
    v2.main()
    v2.ser_field.value, v2.ser_z.value = "thpert", 1.0
    t0 = time.time()
    v2._on_ser_compute(None)
    wait(lambda: not v2.ser_go.disabled)
    print(f"  second session: {time.time() - t0:.1f} s ->", v2.ser_status.object)

    # ---- track, then max w in 0-10 km within 5 km of it (time x height)
    v.trk_whole.value = False
    v.tslider.value = 30
    v.request_track(None, None)  # Find strongest
    wait(lambda: v.trk_stop_btn.disabled, 600)
    print("track fixes:", len(v.fixes), "from", min(v.fixes), "to", max(v.fixes))
    v.ser_field.value, v.ser_vmode.value = "winterp", "layer"
    v.ser_z0.value, v.ser_z1.value = 0.0, 10.0
    v.ser_region.value, v.ser_radius.value, v.ser_reduce.value = "track", 5.0, "max"
    v._on_ser_compute(None)
    dt = wait(done)
    ds = v.series[v.ser_pick.value]["ds"]
    n = int(ds.computed.sum())
    print(f"max w 0-10 km near track: {dt:.1f} s, computed {n}, profile {ds.profile.shape}")
    print("  ", v.ser_status.object)
    assert n == len(v.fixes) or n >= len(v.fixes)  # gaps inside the track are filled
    ok = np.flatnonzero(ds.computed.values == 1)
    tt = ok[len(ok) // 2]
    colmax = np.nanmax(ds.profile.values[tt])
    assert abs(colmax - ds.value.values[tt]) < 1e-6
    cx, cy = ds.center_x_km.values[tt], ds.center_y_km.values[tt]
    dist = np.hypot(ds.x_km.values[tt] - cx, ds.y_km.values[tt] - cy)
    print(f"  t={tt}: wmax {ds.value.values[tt]:.1f} at z {ds.z_km.values[tt]:.2f} km, "
          f"{dist:.2f} km from centre")
    assert dist <= 5.0 + 1e-6
    # time-height view
    v.ser_view.value = "th"
    print("  time-height quads:", len(v.ser_th_src.data["v"]), "shown:",
          v.ser_plot.object is v.ser_thfig, "range", round(v.ser_th_map.low, 1),
          round(v.ser_th_map.high, 1))
    v.ser_view.value = "line"
    print("  legend items:", [i.label["value"] for i in v.ser_fig.legend[0].items])

    # ---- moving one fix invalidates only that time
    k = sorted(v.fixes)[3]
    v.fixes[k] = dict(v.fixes[k], x=v.fixes[k]["x"] + 1.0)
    cen = S.track_centers(v.fixes, nt)
    r = v.series[v.ser_pick.value]["recipe"]
    c2 = S.cached(run, r, centers=cen)
    print("  after moving one fix: cached times", int(c2.computed.sum()), "of", n)
    assert int(c2.computed.sum()) == n - 1

    # ---- click on the plot jumps to that time
    v._on_ser_tap(type("E", (), {"x": run.times[20] / 60.0 + 0.3})())
    print("tap -> time index", v.t)
    assert v.t == 20

    # ---- save / load in every format
    for ext in (".nc", ".csv", ".txt", ".pkl"):
        v.ser_fmt.value = ext
        v.ser_path.value = os.path.join(tmp, "out", "wmax" + ext)
        v._on_ser_save(None)
        assert os.path.exists(v.ser_path.value), v.ser_file_msg.object
        size = os.path.getsize(v.ser_path.value)
        ds2, rec, note = S.load(run, v.ser_path.value, F)
        a, b = ds.value.values[ok], ds2.value.values[ok]
        same = np.allclose(a, b, rtol=1e-5, equal_nan=True)
        prof = "profile" in ds2 and np.allclose(ds2.profile.values[ok], ds.profile.values[ok],
                                                equal_nan=True)
        print(f"  {ext}: {size} bytes, recipe ok {rec == r}, values ok {same}, "
              f"per-level ok {prof}")
        assert same and rec == r
    v._on_ser_load(None)
    print("  loaded into session:", v.ser_file_msg.object)
    print("  series now:", list(v.ser_pick.options)[-1])
    data = v._ser_download().getvalue()
    print("  download bytes:", len(data))
    print("ok", tmp)


if __name__ == "__main__":
    main()
