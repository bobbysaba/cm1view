"""Headless checks: 2D streamlines on the map (Winds → Draw as Streamlines), and the
Series tab's line view with a second y axis for series in other units.
Writes only to the series cache (SMOKE_SER_CACHE, else a temporary one).
Usage: python tests/smoke17.py"""
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cm1view.registry import Registry
from cm1view import app as A, figure as fg, render, series as S, track as trk

TOR = "/glade/derecho/scratch/rasaba/phd/southeast/rm_tor_125m"


def wait(pred, tmax=1800):
    t0 = time.time()
    while not pred() and time.time() - t0 < tmax:
        time.sleep(0.2)
    return time.time() - t0


def main():
    tmp = tempfile.mkdtemp(prefix="cm1view-smoke17-", dir=os.environ.get("TMPDIR") or None)
    S.CACHE_DIR = os.environ.get("SMOKE_SER_CACHE") or os.path.join(tmp, "cache")
    reg = Registry(TOR, 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()

    # ---- streamlines on the map
    t = int(np.argmin(np.abs(np.asarray(run.times) - 5400)))
    v.tslider.value = t
    v.vec_on.value = True
    v.vec_style.value = "streamlines"
    print("density label:", v.vec_density.name, "| ref visible:", v.vec_ref.visible)
    assert v.vec_density.name == "Streamline density" and not v.vec_ref.visible
    spec = v._map_spec()
    t0 = time.time()
    res = render.compute_map(F, spec)
    sl, heads = res["stream"]
    lens = [len(x) for x in sl["xs"]]
    print(f"streamlines: {len(lens)} lines, {sum(lens)} points, {len(heads['x'])} arrowheads,"
          f" {time.time() - t0:.1f} s; arrows: {res['vec']}")
    assert len(lens) > 20 and len(heads["x"]) == len(lens) and res["vec"] is None
    v._apply_map(res, spec, v.gen["map"])
    print("  on the map:", len(v.sl2_src.data["xs"]), "lines; arrow source empty:",
          len(v.vec_src.data["x0"]) == 0)
    assert len(v.sl2_src.data["xs"]) == len(lens) and len(v.vec_src.data["x0"]) == 0
    # one streamline follows the wind: its direction matches (u, v) where it starts
    u = F.plane("uinterp", t, "height", spec["vec"]["level"])
    vv = F.plane("vinterp", t, "height", spec["vec"]["level"])
    if spec["vec"]["frame"] == "ground":
        u, vv = u + run.umove, vv + run.vmove
    x, y = sl["xs"][0], sl["ys"][0]
    i, j = run.ij(x[1], y[1])
    d = np.array([x[2] - x[1], y[2] - y[1]])
    w = np.array([u[j, i], vv[j, i]])
    cos = float(d @ w / (np.linalg.norm(d) * np.linalg.norm(w) + 1e-12))
    print(f"  direction vs wind (cos): {cos:.3f}")
    assert cos > 0.9
    # back to arrows
    v.vec_style.value = "arrows"
    res = render.compute_map(F, v._map_spec())
    v._apply_map(res, v._map_spec(), v.gen["map"])
    assert res.get("stream") is None and len(v.sl2_src.data["xs"]) == 0
    assert len(v.vec_src.data["x0"]) > 0

    # ---- Series tab: m/s and 1/s series get two y axes
    v.fixes = trk.load(run, fg.find_track(TOR))
    for field in ("winterp", "zvort"):
        v.ser_field.value, v.ser_vmode.value = field, "layer"
        v.ser_z0.value, v.ser_z1.value = 0.0, 10.0
        v.ser_region.value, v.ser_radius.value, v.ser_reduce.value = "track", 5.0, "max"
        v._on_ser_compute(None)
        print(f"  {field}: {wait(lambda: not v.ser_go.disabled):.0f} s", v.ser_status.object)
    fig = v.ser_fig
    print("series:", len(v.series), "| extra y ranges:", list(fig.extra_y_ranges),
          "| right axes:", [a.axis_label for a in fig.right],
          "| left:", fig.yaxis[0].axis_label)
    assert list(fig.extra_y_ranges) == ["u1"] and len(fig.right) == 1
    assert fig.right[0].axis_label == F["zvort"].units
    assert fig.yaxis[0].axis_label == F["winterp"].units
    rng = {r.y_range_name for r in v._ser_glyphs}
    assert rng == {"default", "u1"}, rng
    # remove one: back to one axis, redraws do not pile up axes
    v._ser_draw()
    v._ser_draw()
    assert len(fig.right) == 1
    v._on_ser_remove(None)
    print("after remove:", list(fig.extra_y_ranges), len(fig.right), fig.yaxis[0].axis_label)
    assert not fig.extra_y_ranges and not fig.right
    print("ok")


if __name__ == "__main__":
    main()
