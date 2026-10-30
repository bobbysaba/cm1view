"""Series: a field reduced over a region at every time (domain, storm disc, 3D box),
the cache, the time-height view, a second y axis for other units, the plot settings,
and saving / loading in every format."""
import os

import numpy as np
import pytest
from bokeh.models import DataRange1d, Range1d

from cm1view import config
from cm1view.core import series as S, track as trk
from cm1view.core.fields import palette
from conftest import wait


def compute(v, field, reduce="max", region="domain", vmode="height", z=1.0,
            layer=(0.0, 10.0), radius=5.0, op=""):
    v.ser_field.value, v.ser_vmode.value, v.ser_reduce.value = field, vmode, reduce
    v.ser_op.value = op
    if vmode == "layer":
        v.ser_z0.value, v.ser_z1.value = layer
    else:
        v.ser_z.value = z
    v.ser_region.value = region
    if region == "track":
        v.ser_radius.value = radius
    v._on_ser_compute(None)
    wait(lambda: not v.ser_go.disabled, msg=f"series {field}")
    return v.series[v.ser_pick.value]


@pytest.fixture
def tracked(viewer):
    viewer.fixes = trk.load(viewer.run, config.find_track(viewer.run.path))
    return viewer


def test_domain_min_matches_the_map(viewer, reg):
    v = viewer
    run, F = reg.get()
    ds = compute(v, "thpert", "min", z=1.0)["ds"]
    assert int(ds.computed.sum()) == len(run.times)
    t = 4
    ref = float(np.nanmin(F.plane("thpert", t, "height", 1.0)))
    assert abs(ds.value.values[t] - ref) < 1e-3


def test_derivative_series_match_the_map(viewer, reg):
    """A field derivative is taken before the reduction, with the points just outside
    the region, so a box or a layer gives the map's values (horizontal divergence too)."""
    run, F = reg.get()
    t = 4
    s = compute(viewer, "winterp", "max", z=2.0, op="ddz")
    assert s["recipe"]["field"] == "ddz.winterp"
    ref = float(np.nanmax(F.plane("ddz.winterp", t, "height", 2.0)))
    assert abs(s["ds"].value.values[t] - ref) < 1e-4 * abs(ref)
    viewer.ser_field.value = next(n for n, d in F.defs.items() if d.ndim == 2)
    assert "ddz" not in viewer.ser_op.options.values() and viewer.ser_op.value == ""
    w = F.plane("winterp", t, "height", 3.0)
    j, i = np.unravel_index(np.nanargmax(w), w.shape)
    x, y = float(run.xh[i]), float(run.yh[j])
    box = (x - 7.3, x + 6.1, y - 5.2, y + 8.4)
    for field, vmode, how in (("gradh.thpert", "height", "max"),
                              ("ddx.thpert", "height", "mean"),
                              ("ddy.winterp", "layer", "max"), ("ddz.winterp", "layer", "min"),
                              ("hdiv", "height", "min"), ("bgen_x", "layer", "max")):
        r = S.normalize(dict(field=field, vmode=vmode, z=1.0, z0=0.0, z1=3.0, region="box",
                             box=box, reduce=how))
        ds, skipped = S.compute(run, F, r, S.empty(run, r), times=[t], workers=1)
        assert not skipped
        i0, i1, j0, j1 = S.region_at(run, r, None)[:4]
        if vmode == "height":
            a = F.plane(field, t, "height", 1.0)[j0:j1, i0:i1]
        else:
            a = np.stack([F.plane(field, t, "level", k)[j0:j1, i0:i1]
                          for k in S.levels(run, r)])
            prof = np.array([{"max": np.nanmax, "min": np.nanmin}[how](b) for b in a])
            assert np.allclose(ds.profile.values[t], prof, rtol=1e-5, atol=1e-7)
        ref = {"max": np.nanmax, "min": np.nanmin, "mean": np.nanmean}[how](a)
        assert abs(ds.value.values[t] - ref) <= 1e-5 * max(abs(ref), 1e-3), field


def test_column_field_series_match_the_map(reg):
    """Column fields (and a horizontal derivative of one) reduced over the domain and a
    box give the map's values."""
    run, F = reg.get()
    t = 4
    a = F.plane("uh25", t)
    j, i = np.unravel_index(np.nanargmax(a), a.shape)
    x, y = float(run.xh[i]), float(run.yh[j])
    box = (x - 7.3, x + 6.1, y - 5.2, y + 8.4)
    for field, region, how in (("uh25", "domain", "max"), ("uh25", "box", "mean"),
                               ("uh01", "box", "min"), ("zvmax01", "box", "max"),
                               ("wmax", "domain", "pct"), ("gradh.uh25", "box", "max"),
                               ("srh03", "box", "max"), ("shear06", "domain", "mean"),
                               ("sbcin", "box", "min"), ("stp", "box", "max"),
                               ("ddx.mucape", "box", "max")):
        r = S.normalize(dict(field=field, vmode="2d", region=region, box=box,
                             reduce=how, pct=90.0))
        ds, skipped = S.compute(run, F, r, S.empty(run, r), times=[t], workers=1)
        assert not skipped, field
        i0, i1, j0, j1 = S.region_at(run, r, None)[:4]
        b = F.plane(field, t)[j0:j1, i0:i1]
        ref = {"max": np.nanmax, "min": np.nanmin, "mean": np.nanmean,
               "pct": lambda v: np.nanpercentile(v, 90.0)}[how](b)
        assert abs(ds.value.values[t] - ref) <= 1e-4 * max(abs(ref), 1e-3), field
        if how == "max":
            assert ds.x_km.values[t] == run.xh[i0 + np.nanargmax(b) % (i1 - i0)], field


def test_vorticity_tendency_series_match_the_map(reg):
    """Fields whose inputs are derivatives (ζ ∂w/∂z, tilting, Okubo–Weiss), and a
    derivative of one, give the map's values over a box, at a height and in a layer."""
    run, F = reg.get()
    t = 4
    w = F.plane("winterp", t, "height", 3.0)
    j, i = np.unravel_index(np.nanargmax(w), w.shape)
    x, y = float(run.xh[i]), float(run.yh[j])
    box = (x - 7.3, x + 6.1, y - 5.2, y + 8.4)
    for field, vmode, how in (("zstretch", "height", "max"), ("ztilt", "layer", "min"),
                              ("okubo", "height", "mean"), ("ddz.ztend", "layer", "max")):
        r = S.normalize(dict(field=field, vmode=vmode, z=1.0, z0=0.0, z1=3.0, region="box",
                             box=box, reduce=how))
        ds, skipped = S.compute(run, F, r, S.empty(run, r), times=[t], workers=1)
        assert not skipped, field
        i0, i1, j0, j1 = S.region_at(run, r, None)[:4]
        if vmode == "height":
            a = F.plane(field, t, "height", 1.0)[j0:j1, i0:i1]
        else:
            a = np.stack([F.plane(field, t, "level", k)[j0:j1, i0:i1]
                          for k in S.levels(run, r)])
            prof = np.array([{"max": np.nanmax, "min": np.nanmin}[how](b) for b in a])
            assert np.allclose(ds.profile.values[t], prof, rtol=1e-5, atol=1e-7), field
        ref = {"max": np.nanmax, "min": np.nanmin, "mean": np.nanmean}[how](a)
        assert abs(ds.value.values[t] - ref) <= 1e-5 * max(abs(ref), 1e-3), field


def test_second_session_reads_the_cache(viewer, reg):
    from cm1view.viewer import app as A
    run, F = reg.get()
    recipe = compute(viewer, "thpert", "min", z=1.0)["recipe"]
    assert int(S.cached(run, recipe).computed.sum()) == len(run.times)
    v2 = A.Viewer(run, F, reg=reg)
    v2.main()
    try:
        s = compute(v2, "thpert", "min", z=1.0)
        assert s["recipe"] == recipe and int(s["ds"].computed.sum()) == len(run.times)
    finally:
        v2.close()


def test_storm_disc_layer_and_time_height(tracked):
    v = tracked
    run = v.run
    s = compute(v, "winterp", "max", "track", "layer", radius=5.0)
    ds = s["ds"]
    n = int(ds.computed.sum())
    assert n == len(v.fixes)
    ok = np.flatnonzero(ds.computed.values == 1)
    tt = ok[len(ok) // 2]
    assert abs(np.nanmax(ds.profile.values[tt]) - ds.value.values[tt]) < 1e-6
    cx, cy = ds.center_x_km.values[tt], ds.center_y_km.values[tt]
    assert np.hypot(ds.x_km.values[tt] - cx, ds.y_km.values[tt] - cy) <= 5.0 + 1e-6
    v.ser_view.value = "th"
    assert v.ser_plot.object is v.ser_thfig and len(v.ser_th_src.data["v"]) > 0
    v.ser_view.value = "line"
    # moving one fix invalidates only that time
    k = sorted(v.fixes)[3]
    v.fixes[k] = dict(v.fixes[k], x=v.fixes[k]["x"] + 1.0)
    c2 = S.cached(run, s["recipe"], centers=S.track_centers(v.fixes, len(run.times)))
    assert int(c2.computed.sum()) == n - 1


def test_click_on_the_plot_goes_to_that_time(viewer):
    v = viewer
    compute(v, "thpert", "min")
    v._on_ser_tap(type("E", (), {"x": v.run.times[5] / 60.0 + 0.3})())
    assert v.t == 5


@pytest.mark.parametrize("ext", [".nc", ".csv", ".txt", ".pkl"])
def test_save_and_load(tracked, reg, tmp_path, ext):
    v = tracked
    run, F = reg.get()
    s = compute(v, "winterp", "max", "track", "layer")
    ds = s["ds"]
    ok = np.flatnonzero(ds.computed.values == 1)
    v.ser_fmt.value = ext
    v.ser_path.value = str(tmp_path / ("wmax" + ext))
    v._on_ser_save(None)
    assert os.path.exists(v.ser_path.value), v.ser_file_msg.object
    ds2, rec, _ = S.load(run, v.ser_path.value, F)
    assert rec == s["recipe"]
    assert np.allclose(ds.value.values[ok], ds2.value.values[ok], rtol=1e-5, equal_nan=True)
    n = len(v.series)
    v._on_ser_load(None)
    assert len(v.series) == n + 1
    assert len(v._ser_download().getvalue()) > 0


def test_other_units_get_a_second_axis(tracked, reg):
    v = tracked
    _, F = reg.get()
    for field in ("winterp", "zvort"):
        compute(v, field, "max", "track", "layer")
    fig = v.ser_fig
    assert list(fig.extra_y_ranges) == ["u1"] and len(fig.right) == 1
    assert fig.right[0].axis_label == F["zvort"].units
    assert fig.yaxis[0].axis_label == F["winterp"].units
    assert {r.y_range_name for r in v._ser_glyphs} == {"default", "u1"}
    v._ser_draw()
    v._ser_draw()  # redraws do not pile up axes
    assert len(fig.right) == 1
    v._on_ser_remove(None)
    assert not fig.extra_y_ranges and not fig.right


def test_box_region_only_once_drawn(viewer):
    v = viewer
    regs = lambda: list(v.ser_region.options.values())  # noqa: E731
    assert "box3d" not in regs()
    v._set_box((-10.0, 0.0, -10.0, 0.0))
    assert "box3d" in regs()
    v.ser_region.value = "box3d"
    v._on_clear_points(None)
    assert "box3d" not in regs() and v.ser_region.value == "domain"


def test_plot_settings(tracked):
    v = tracked
    run = v.run
    s = compute(v, "winterp", "max", "track", "layer")
    wait(lambda: len(v._ser_glyphs) >= 1, msg="drawn")
    ds = s["ds"]
    ts = np.flatnonzero(ds["computed"].values == 1)
    fig = v.ser_fig
    assert v.ser_s0.visible and not v.ser_cmap.visible
    full = np.asarray(v._ser_glyphs[0].data_source.data["value"])
    # a sub-layer of the layer, from the stored profiles
    v.ser_s0.value, v.ser_s1.value = 0.0, 2.0
    sub = np.asarray(v._ser_glyphs[0].data_source.data["value"])
    z = ds["z"].values
    want = np.nanmax(ds["profile"].values[ts][:, (z >= 0) & (z <= 2)], axis=1)
    assert np.allclose(sub, want, equal_nan=True) and np.nanmax(sub) <= np.nanmax(full)
    # limits
    t0 = run.times[ts[0]] / 60 + 5
    v.ser_t0.value, v.ser_y1.value = t0, 30.0
    xr, yr = fig.x_range, fig.y_range
    assert isinstance(xr, Range1d) and xr.start == t0
    assert abs(xr.end - run.times[ts[-1]] / 60) < 1e-6
    assert isinstance(yr, Range1d) and yr.end == 30.0
    v.ser_auto.clicks += 1
    assert isinstance(fig.x_range, DataRange1d) and isinstance(fig.y_range, DataRange1d)
    assert v.ser_s0.value is None
    # time-height: height limits and colours
    v.ser_view.value = "th"
    assert v.ser_cmap.visible and not v.ser_s0.visible and v.ser_y0.name.startswith("Height")
    v.ser_y0.value, v.ser_y1.value = 0.0, 2.0
    v.ser_cmap.value, v.ser_c0.value, v.ser_c1.value = "turbo", 0.0, 25.0
    th, m = v.ser_thfig, v.ser_th_map
    assert (th.y_range.start, th.y_range.end) == (0.0, 2.0) and (m.low, m.high) == (0.0, 25.0)
    assert m.palette[0] == palette("turbo")[0]
