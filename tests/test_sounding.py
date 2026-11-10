"""Soundings: point / mean / pinned soundings and the comparison styles, the m/hPa level
rows, the plot style, and the data the browser-drawn graphics (skew-T, hodograph,
profile panels) are given."""
import re

import numpy as np

from conftest import tap, wait


def drawn(v):
    return lambda: v.skew_view.panel.visible and not v.snd_col.loading and v.results


def sounding(v, x=5.0, y=-15.0, shift=False):
    v.mode.set("Sounding")
    n = len(v.results) if shift else 0
    tap(v, x, y, shift)
    wait(lambda: drawn(v)() and len(v.results) > n, msg="sounding")


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
    assert not v.results and not v.skew_view.panel.visible
    assert not v.prof_view.panel.visible


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
    v.ps["t"].value = "#ff00ff"
    wait(lambda: v.skew_view.t_r[0].glyph.line_color == "#ff00ff", msg="redraw")
    assert v.prof_view.lines[0]["th"].glyph.line_color == "#ff00ff"  # (θ shares it)


def test_skewt_and_profile_data_follow_the_analysis(viewer):
    v = viewer
    sounding(v, 5.0, -15.0)
    sounding(v, 15.0, -15.0, shift=True)
    sv, pv = v.skew_view, v.prof_view
    assert sv.panel.visible and pv.panel.visible
    r0 = v.results[0][2]
    d = sv.src[0].data
    k = 10
    assert abs(d["p"][k] - r0["prof"]["p"][k] / 100) < 0.05
    assert abs(d["T"][k] - (r0["prof"]["T"][k] - 273.15)) < 0.01
    # slots follow the soundings shown: two, then (when shown) the base state
    assert [r.visible for r in sv.t_r] == [True, True, False, False]
    assert [row["sr"].visible for row in pv.lines[:3]] == [True, True, False]
    base = v._snd_last[1] is not None
    assert pv.lines[-1]["sr"].visible == base
    pf = r0["profiles"]
    assert np.allclose(pv.m[0].data["zm"], pf["zm"] / 1000.0)
    assert np.allclose(pv.z[0].data["srh"], pf["cum_srh"])
    fit = pv.fit.data
    assert len(fit["x0"]) == 5 and fit["y1"][0] == float(v.prof_top.value)
    assert all(a < b for a, b in zip(fit["x0"], fit["x1"]))


def test_wind_units_and_profile_top_reach_the_panels(viewer):
    v = viewer
    sounding(v)
    zmax0 = v.prof_view.fit.data["y1"][0]
    sr0 = list(v.prof_view.m[0].data["sr"])
    v.wunits.value = "kt"
    wait(lambda: v.prof_view.figs[0].xaxis[0].axis_label.endswith("(kt)")
         and not v.snd_col.loading, msg="kt")
    sr1 = list(v.prof_view.m[0].data["sr"])
    assert np.allclose(sr1, np.array(sr0) * 1.943844, rtol=1e-3)
    assert v.skew_view.hfig.xaxis[0].axis_label == "u (kt)"
    v.prof_top.value = 3.0 if zmax0 != 3.0 else 6.0
    wait(lambda: v.prof_view.fit.data["y1"][0] == float(v.prof_top.value), msg="top")


def test_compare_styles_draw_every_sounding(viewer):
    v = viewer
    sounding(v, 5.0, -15.0)
    sounding(v, 15.0, -15.0, shift=True)
    v.compare.value = "colors"
    wait(lambda: v.skew_view.t_r[0].glyph.line_color == v.results[0][1], msg="colors")
    assert v.prof_view.lines[1]["sr"].glyph.line_color == v.results[1][1]
    v.compare.value = "tabs"
    wait(lambda: v.snd_tabs.visible and len(v._snd_tab_views) == 2, msg="tabs")
    assert not v.skew_view.panel.visible and not v.prof_view.panel.visible
    for (sv, pv), (_, _, r) in zip(v._snd_tab_views, v.results):
        assert sv.t_r[0].visible and not sv.t_r[1].visible
        assert pv.lines[0]["sr"].visible and not pv.lines[1]["sr"].visible


def test_profiles_are_finite(viewer):
    v = viewer
    sounding(v)
    prof = v.results[0][2]["prof"]
    assert np.all(np.isfinite(prof["T"])) and np.all(np.diff(prof["p"]) < 0)
