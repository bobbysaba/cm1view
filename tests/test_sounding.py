"""Soundings: point / mean / pinned soundings and the comparison styles, the m/hPa level
rows, the plot style, zoom and pan of the graphics by redrawing with axes limits, and the
hover readout data."""
import base64
import re
import time

import numpy as np

from conftest import tap, wait


def drawn(v):
    return lambda: v.skew_png.src and not v.snd_col.loading and v.results


def sounding(v, x=5.0, y=-15.0, shift=False):
    v.mode.set("Sounding")
    n = len(v.results) if shift else 0
    tap(v, x, y, shift)
    wait(lambda: drawn(v)() and len(v.results) > n, msg="sounding")


def send(z, name, vals):
    """A zoom message from the browser (box / pan), answered by bumping `done`."""
    d = z.done
    setattr(z, name, list(vals) + [time.time()])
    wait(lambda: z.done > d, msg=f"{name} answered")


def aff(m, fx, fy):
    return m[0] * fx + m[1] * fy + m[2]


def test_point_mean_and_pinned_soundings(viewer):
    v = viewer
    v.points = [("pt", (5.0, -15.0), None), ("mean", None, None)]
    v.request_soundings()
    wait(lambda: not v.snd_col.loading and len(v.results) == 2, msg="two soundings")
    v.tslider.value = 3
    v._pin_time()
    wait(lambda: not v.snd_col.loading and len(v.results) == 3, msg="pinned")
    for style in ("colors", "tabs"):
        v.compare.value = style
        wait(lambda: not v.snd_col.loading, msg=style)
    assert v.snd_tabs.visible and len(v._snd_tab_names) == 3
    v.compare.value = "lines"
    v._on_clear_soundings(None)
    assert not v.results and not v.skew_png.visible


def test_shift_click_adds_up_to_four(viewer):
    v = viewer
    sounding(v, 5.0, -15.0)
    for x in (10.0, 15.0, 20.0, 0.0):
        tap(v, x, -15.0, shift=True)
    assert len(v.points) == 4 and v.points[-1][1][:2] == (0.0, -15.0)


def test_area_soundings_replace_and_add(viewer):
    v = viewer
    v.mode.set("Area sounding")
    assert v.fig.toolbar.active_drag is v.bsel

    def box(x0, x1, y0, y1, shift):
        v._on_pan_start(type("E", (), {"modifiers": {"shift": shift}})())
        v._on_select(type("E", (), {"final": True, "geometry": dict(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1)})())

    box(0.0, 10.0, -20.0, -10.0, False)
    box(-20.0, -10.0, 5.0, 15.0, True)
    assert [p[1] for p in v.points] == [(5.0, -15.0, 10.0, 10.0), (-15.0, 10.0, 10.0, 10.0)]
    assert len(v.pbox_src.data["x"]) == 2
    wait(lambda: not v.snd_col.loading and len(v.results) == 2, msg="area soundings")


def test_level_rows_keep_their_units(viewer):
    v = viewer
    sounding(v)
    rows = re.findall(r'<tr class="alt" data-row="([^"]+)">', v.params.html)
    assert "SB LCL" in rows
    v.params.alt_rows = ["SB LCL"]
    v.request_soundings()
    wait(lambda: not v.snd_col.loading, msg="refresh")
    assert v.params.alt_rows == ["SB LCL"]


def test_style_reaches_the_drawn_figure(viewer):
    v = viewer
    sounding(v)
    d0 = v.skew_png.done
    v.ps["t"].value = "#ff00ff"
    wait(lambda: v.skew_png.done > d0, msg="redraw")
    svg = base64.b64decode(v.skew_png.src.split(",", 1)[1]).decode()
    assert "#ff00ff" in svg


def test_zoom_box_out_reset_and_units(viewer):
    v = viewer
    sounding(v)
    v._set_full(True)
    assert v.skew_png.interactive and not v.map_area.visible
    send(v.skew_png, "box", (0.10, 0.45, 0.35, 0.92))
    assert "skew" in v.snd_lim
    lim = list(v.snd_lim["skew"])
    ylim = sorted(v._figs[v.skew_png].cv_axes["skew"].get_ylim())
    assert np.allclose(ylim, sorted(lim[2:]), atol=1)
    send(v.skew_png, "box", (0.65, 0.30, 0.85, 0.70))
    assert "hodo" in v.snd_lim
    send(v.prof_png, "box", (0.30, 0.30, 0.45, 0.70))
    assert "prof_z" in v.snd_lim and v.snd_lim["prof_x"]
    d = v.skew_png.done
    v.skew_png.zoom_out += 1
    wait(lambda: v.skew_png.done > d, msg="zoom out")
    wide = v.snd_lim["skew"]
    assert wide[1] - wide[0] > lim[1] - lim[0]
    # kept when the sounding is analysed again (next time)
    v.tslider.value = 2
    v._refresh_panels()
    wait(lambda: not v.snd_col.loading, msg="next time")
    assert v.snd_lim["skew"] == wide
    d = v.skew_png.done
    v.skew_png.resets += 1
    wait(lambda: v.skew_png.done > d, msg="reset")
    assert "skew" not in v.snd_lim and "hodo" not in v.snd_lim
    assert "prof_z" in v.snd_lim  # another image's zoom stays
    v.wunits.value = "kt"  # profile values in other units no longer fit
    assert "prof_x" not in v.snd_lim
    v._set_full(False)
    assert v.map_area.visible and not v.skew_png.interactive


def test_pan_moves_the_limits(viewer):
    v = viewer
    sounding(v)
    v._set_full(True)
    send(v.skew_png, "box", (0.10, 0.45, 0.35, 0.92))
    s0 = v.snd_lim["skew"]
    # content dragged right and down -> colder temperatures and higher levels come in
    send(v.skew_png, "pan", (0.3, 0.6, 0.05, 0.05))
    s1 = v.snd_lim["skew"]
    assert s1[0] < s0[0] and s1[1] < s0[1]
    assert s1[2] < s0[2] and s1[3] < s0[3]
    assert abs((s1[1] - s1[0]) - (s0[1] - s0[0])) < 0.02 * (s0[1] - s0[0])
    # hodograph without a previous zoom: content dragged left -> larger u
    fig = v._figs[v.skew_png]
    hb = fig.cv_axes["hodo"].bbox
    W, H = fig.bbox.width, fig.bbox.height
    u0 = fig.cv_axes["hodo"].get_xlim()
    send(v.skew_png, "pan", ((hb.x0 + hb.x1) / 2 / W, 1 - (hb.y0 + hb.y1) / 2 / H,
                             -0.05, 0.0))
    h1 = v.snd_lim["hodo"]
    assert h1[0] > u0[0] and h1[1] > u0[1]
    # profiles: content dragged up -> lower heights come in
    send(v.prof_png, "box", (0.30, 0.30, 0.45, 0.70))
    z0 = v.snd_lim["prof_z"]
    send(v.prof_png, "pan", (0.37, 0.5, 0.0, -0.05))
    z1 = v.snd_lim["prof_z"]
    assert z1[0] < z0[0] and z1[1] < z0[1]
    # outside every panel: answered, nothing changes
    lim = dict(v.snd_lim)
    send(v.skew_png, "pan", (0.995, 0.995, 0.05, 0.05))
    assert v.snd_lim == lim


def test_hover_readout_inverts_the_figure(viewer):
    v = viewer
    sounding(v, 5.0, -15.0)
    sounding(v, 15.0, -15.0, shift=True)
    pa, pb = v.skew_png.probe, v.prof_png.probe
    nsnd = 2 + (v._snd_last[1] is not None)  # and the base state when shown
    assert [p["kind"] for p in pa["panels"] + pb["panels"]] == ["y", "xy", "z"]
    assert len(pa["panels"][0]["snd"]) == nsnd == len(pb["panels"][0]["snd"])
    fig = v._figs[v.skew_png]
    sk, hd = fig.cv_axes["skew"], fig.cv_axes["hodo"]
    W, H = fig.bbox.width, fig.bbox.height
    for ax, P, pt, ylog in ((sk, pa["panels"][0], (12.0, 700.0), True),
                            (hd, pa["panels"][1], (8.0, -3.0), False)):
        dx, dy = ax.transData.transform([pt])[0]
        fx, fy = dx / W, 1.0 - dy / H
        x, y = aff(P["aff"][0], fx, fy), aff(P["aff"][1], fx, fy)
        y = 10 ** y if ylog else y
        assert abs(x - pt[0]) < 1e-6 and abs(y - pt[1]) < 1e-6 * max(1, pt[1])
    # skew-T columns match the analysed profile
    s0, r0, k = pa["panels"][0]["snd"][0], v.results[0][2]["prof"], 10
    col = {c[0]: c[3] for c in s0["cols"]}
    assert abs(10 ** s0["y"][k] - r0["p"][k] / 100) < 0.05
    assert abs(col["T"][k] - (r0["T"][k] - 273.15)) < 0.01
    # hodograph points sit on the drawn trace
    h0 = pa["panels"][1]["snd"][0]
    dx, dy = hd.transData.transform([(h0["wind"][0][5], h0["wind"][1][5])])[0]
    assert abs(dx / W - h0["fx"][5]) < 1e-3 and abs(1 - dy / H - h0["fy"][5]) < 1e-3
    pz = pb["panels"][0]
    assert len(pz["frames"]) == 5 and pz["yunit"] == "km AGL"


def test_profiles_are_finite(viewer):
    v = viewer
    sounding(v)
    prof = v.results[0][2]["prof"]
    assert np.all(np.isfinite(prof["T"])) and np.all(np.diff(prof["p"]) < 0)
