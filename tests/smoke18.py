"""Headless checks: hover readout data of the sounding graphics, the Series tab's plot
settings (limits, sub-layer of a layer series, time–height colours), the 3D region box
offered as a series region only once drawn, and the streamline card's axes fitted to
the field.
Writes only to the series cache (SMOKE_SER_CACHE, else a temporary one).
Usage: python tests/smoke18.py"""
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bokeh.models import DataRange1d, Range1d  # noqa: E402
from cm1view.registry import Registry  # noqa: E402
from cm1view import app as A, figure as fg, series as S, track as trk  # noqa: E402

TOR = "/glade/derecho/scratch/rasaba/phd/southeast/rm_tor_125m"


def wait(pred, tmax=1800):
    t0 = time.time()
    while not pred() and time.time() - t0 < tmax:
        time.sleep(0.2)
    return time.time() - t0


def aff(m, fx, fy):
    return m[0] * fx + m[1] * fy + m[2]


def main():
    tmp = tempfile.mkdtemp(prefix="cm1view-smoke18-", dir=os.environ.get("TMPDIR") or None)
    S.CACHE_DIR = os.environ.get("SMOKE_SER_CACHE") or os.path.join(tmp, "cache")
    reg = Registry(TOR, 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    t = int(np.argmin(np.abs(np.asarray(run.times) - 5400)))
    v.tslider.value = t

    # ---- hover data of the sounding graphics: two soundings overlaid
    v.mode.set("Sounding")
    v._on_tap(type("E", (), {"x": -30.0, "y": -25.0, "modifiers": {}})())
    wait(lambda: v.skew_png.src and not v.snd_col.loading)
    v._on_tap(type("E", (), {"x": -10.0, "y": -25.0, "modifiers": {"shift": True}})())
    time.sleep(0.5)
    wait(lambda: not v.snd_col.loading and len(v.results) == 2)
    pa, pb = v.skew_png.probe, v.prof_png.probe
    kinds = [p["kind"] for p in pa["panels"]] + [p["kind"] for p in pb["panels"]]
    nsnd = 2 + (v._snd_last[1] is not None)  # and the base state when shown
    print("probe panels:", kinds, "| soundings:", [s["label"] for s in pa["panels"][0]["snd"]],
          "| bytes:", len(str(pa)) + len(str(pb)))
    assert kinds == ["y", "xy", "z"] and len(pa["panels"][0]["snd"]) == nsnd
    assert len(pb["panels"][0]["snd"]) == nsnd
    # the image-fraction -> data maps invert the figure's own transforms
    fig = v._figs[v.skew_png]
    sk, hd = fig.cv_axes["skew"], fig.cv_axes["hodo"]
    W, H = fig.bbox.width, fig.bbox.height
    for ax, P, pt, ylog in ((sk, pa["panels"][0], (12.0, 700.0), True),
                            (hd, pa["panels"][1], (8.0, -3.0), False)):
        dx, dy = ax.transData.transform([pt])[0]
        fx, fy = dx / W, 1.0 - dy / H
        x, y = aff(P["aff"][0], fx, fy), aff(P["aff"][1], fx, fy)
        y = 10 ** y if ylog else y
        fr = P["frame"]
        print(f"  {P['name']}: {pt} -> ({x:.3f}, {y:.3f}) in frame "
              f"{fr[0] <= fx <= fr[2] and fr[1] <= fy <= fr[3]}")
        assert abs(x - pt[0]) < 1e-6 and abs(y - pt[1]) < 1e-6 * max(1, pt[1])
    # skew-T columns at a level match the analysed profile
    s0 = pa["panels"][0]["snd"][0]
    r0 = v.results[0][2]["prof"]
    k = 10
    col = {c[0]: c[3] for c in s0["cols"]}
    print(f"  level {k}: p {10 ** s0['y'][k]:.1f} hPa, T {col['T'][k]} °C, z {col['z'][k]} km")
    assert abs(10 ** s0["y"][k] - r0["p"][k] / 100) < 0.05  # log p kept to 5 decimals
    assert abs(col["T"][k] - (r0["T"][k] - 273.15)) < 0.01
    # hodograph points sit on the drawn trace
    h0 = pa["panels"][1]["snd"][0]
    u, vv = h0["wind"][0][5], h0["wind"][1][5]
    dx, dy = hd.transData.transform([(u, vv)])[0]
    assert abs(dx / W - h0["fx"][5]) < 1e-3 and abs(1 - dy / H - h0["fy"][5]) < 1e-3
    # profiles: one panel over the five, height axis
    pz = pb["panels"][0]
    print("  profiles frames:", len(pz["frames"]), "| cols:", [c[0] for c in pz["snd"][0]["cols"]])
    assert len(pz["frames"]) == 5 and pz["yunit"] == "km AGL"
    v._set_full(True)  # the readout strip shows in the expanded view
    assert v.skew_png.interactive

    # ---- 3D region box: a series region only once drawn
    regs = lambda: list(v.ser_region.options.values())  # noqa: E731
    print("regions without a box:", regs())
    assert "box3d" not in regs()
    v._set_box((-30.0, -10.0, -35.0, -15.0))
    print("with a box:", regs())
    assert "box3d" in regs()
    v.ser_region.value = "box3d"
    v._on_clear_points(None)
    print("cleared:", regs(), v.ser_region.value)
    assert "box3d" not in regs() and v.ser_region.value == "domain"

    # ---- Series plot settings
    v.fixes = trk.load(run, fg.find_track(TOR))
    v.ser_field.value, v.ser_vmode.value = "winterp", "layer"
    v.ser_z0.value, v.ser_z1.value = 0.0, 10.0
    v.ser_region.value, v.ser_radius.value, v.ser_reduce.value = "track", 5.0, "max"
    v._on_ser_compute(None)
    print(f"  max w 0–10 km: {wait(lambda: not v.ser_go.disabled):.0f} s", v.ser_status.object)
    wait(lambda: len(v._ser_glyphs) == 2, 60)  # drawn right after Compute is enabled
    time.sleep(1)
    s = v.series[v.ser_pick.value]
    ds = s["ds"]
    ts = np.flatnonzero(ds["computed"].values == 1)
    fig = v.ser_fig
    assert v.ser_s0.visible and not v.ser_cmap.visible
    full = np.asarray(v._ser_glyphs[0].data_source.data["value"])
    v.ser_s0.value, v.ser_s1.value = 0.0, 2.0
    sub = np.asarray(v._ser_glyphs[0].data_source.data["value"])
    z = ds["z"].values
    want = np.nanmax(ds["profile"].values[ts][:, (z >= 0) & (z <= 2)], axis=1)
    print(f"  sub-layer 0–2 km: max {np.nanmax(sub):.1f} vs whole layer {np.nanmax(full):.1f};"
          f" legend {fig.legend[0].items[0].label['value']!r}")
    assert np.allclose(sub, want, equal_nan=True) and np.nanmax(sub) <= np.nanmax(full)
    assert "0." in fig.legend[0].items[0].label["value"]
    v.ser_t0.value, v.ser_y1.value = 60.0, 30.0
    xr, yr = fig.x_range, fig.y_range
    print(f"  limits: x {xr.start:.1f}–{xr.end:.1f}, y {yr.start:.2f}–{yr.end:.2f}")
    assert isinstance(xr, Range1d) and xr.start == 60.0 and abs(xr.end - run.times[ts[-1]] / 60) < 1e-6
    assert isinstance(yr, Range1d) and yr.end == 30.0 and abs(yr.start - np.nanmin(sub)) < 1e-6
    v.ser_auto.clicks += 1
    print("  auto:", type(fig.x_range).__name__, type(fig.y_range).__name__, v.ser_s0.value)
    assert isinstance(fig.x_range, DataRange1d) and isinstance(fig.y_range, DataRange1d)
    assert v.ser_s0.value is None
    # time–height: height limits and colours
    v.ser_view.value = "th"
    assert v.ser_cmap.visible and not v.ser_s0.visible and v.ser_y0.name.startswith("Height")
    v.ser_y0.value, v.ser_y1.value = 0.0, 2.0
    v.ser_cmap.value, v.ser_c0.value, v.ser_c1.value = "turbo", 0.0, 25.0
    th, m = v.ser_thfig, v.ser_th_map
    print(f"  th: y {th.y_range.start}–{th.y_range.end}, colours {m.low}–{m.high}, "
          f"palette starts {m.palette[0]}")
    assert (th.y_range.start, th.y_range.end) == (0.0, 2.0) and (m.low, m.high) == (0.0, 25.0)
    assert m.palette[0] == A.palette("turbo")[0]

    # ---- streamline card: y axis fitted to the field, not to the height line
    res = dict(s=np.linspace(0, 12, 50), v=0.02 * np.sin(np.linspace(0, 6, 50)),
               z=np.linspace(0.3, 2.5, 50), label="ωs (s⁻¹)", x0=0.0, y0=0.0, z0=0.3,
               length=12.0)
    v._apply_sl(v.gen["sl"], res)
    yr = v.sl_fig.y_range
    print(f"  streamline card y: {yr.start:.4f}–{yr.end:.4f}")
    assert -0.03 < yr.start < -0.019 and 0.019 < yr.end < 0.03
    v.sl_big.value = True
    assert v.sl_fig.height == 440 and "1200px" in v.sl_card.styles["width"]
    print("ok")


if __name__ == "__main__":
    main()
