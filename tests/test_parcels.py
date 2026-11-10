"""Parcels (core/parcels.py): the demo's parcel output (every 60 s, the 3D output every
300 s), missing values, the seeding lattice, grouped reads, selections, saved sets,
trajectory caching, heads between parcel times, periodic wrap breaks, several files
joined by time; and the viewer's Parcels panel (map, cross-section, 3D view, plot)."""
import os

import netCDF4
import numpy as np
import pytest

from cm1view import demo
from cm1view.core import parcels as P


@pytest.fixture
def pf(demo_run, tmp_path, monkeypatch):
    monkeypatch.setattr(P, "CACHE_DIR", str(tmp_path / "cache"))
    return P.ParcelFile(P.find_files(demo_run))


def test_meta_and_own_time_axis(pf, reg):
    run, _ = reg.get()
    assert pf.n == np.prod([s[2] for s in demo.PRCL_SEEDS.values()])
    assert np.allclose(pf.times, demo.PRCL_TIMES)
    assert len(pf.times) > len([t for t in run.times if t >= pf.times[0]])  # finer
    assert {"x", "y", "z", "w", "th", "b"} <= set(pf.vars)
    assert pf.units("x") == "km" and pf.units("w") == "m/s"


def test_missing_values_are_nan(pf):
    x = pf.read("x")
    gone = np.isnan(x)
    assert gone.any() and not gone[0].any()  # some leave the domain, none at the start
    assert (gone[:-1] <= gone[1:]).all()  # ... and stay gone
    assert np.isnan(pf.read("th", [0], 2)[0])  # the file's missing_value
    assert np.nanmax(np.abs(x)) < 30.0  # km, not m


def test_lattice_detected_and_cached(pf):
    lat = pf.lattice()
    for c in "xyz":
        x0, d, n = demo.PRCL_SEEDS[c]
        assert lat[c + "0"] == pytest.approx(x0, abs=1e-4)
        assert lat["d" + c] == pytest.approx(d, abs=1e-4) and lat["n" + c] == n
    again = P.ParcelFile(pf.paths)
    again.positions = None  # the cached copy is used: nothing read
    assert again.lattice() == lat


def test_lattice_rejects_scattered_points():
    rng = np.random.default_rng(1)
    assert P._detect_lattice(*rng.random((3, 100)).astype(np.float32)) is None


def test_grouped_reads_match_whole_reads(pf, monkeypatch):
    whole = pf.read("w")
    ids = np.array([5, 3, 3, 400, 401, 402, 2000, 7])
    for gap in (0, 10, P.GAP):
        monkeypatch.setattr(P, "GAP", gap)
        monkeypatch.setattr(P, "BLOCK", 4 * 50)  # several time blocks
        np.testing.assert_array_equal(pf.read("w", ids), whole[:, ids])
        np.testing.assert_array_equal(pf.read("w", ids, slice(3, 9)), whole[3:9, ids])
        np.testing.assert_array_equal(pf.read("w", ids, 4), whole[4, ids])
    assert pf.read("w", []).shape == (pf.nt, 0)
    with pytest.raises(IndexError):
        pf.read("w", [pf.n])


def test_selection_on_the_lattice_reads_nothing(pf):
    rule = dict(box=[-15.5, -5.5, -10.5, -0.5], z=[0.0, 1.0])
    s = P.select(pf, rule, "box")
    assert len(s) == 10 * 10 * 2 and s.rule["t"] == pf.times[0]
    pos = pf._pos.copy()
    pf._pos.clear()
    assert np.array_equal(P.select(pf, rule).ids, s.ids) and not pf._pos  # no read
    pf._lattice = None  # the general path agrees
    assert np.array_equal(P.select(pf, rule).ids, s.ids)
    x, y, z = (a[s.ids] for a in pos[0])
    assert (x > -15.5).all() and (x < -5.5).all() and (z < 1.0).all()


def test_selection_later_near_point_values_and_cap(pf):
    t = 4800.0
    ti = pf.nearest(t)
    x, y, z = pf.positions(ti)
    w = pf.read("w", None, ti)
    s = P.select(pf, dict(t=t + 20.0, near=[-10.0, -6.0, 6.0], where=[dict(var="w", min=0.5)]))
    assert s.rule["t"] == pf.times[ti]  # snapped to a parcel time
    ref = np.flatnonzero((np.hypot(x + 10.0, y + 6.0) <= 6.0) & (w >= 0.5))
    assert len(ref) > 10 and np.array_equal(s.ids, ref)
    ball = P.select(pf, dict(t=t, near=[-10.0, -6.0, 1.0, 3.0]))
    d = np.sqrt((x + 10.0) ** 2 + (y + 6.0) ** 2 + (z - 1.0) ** 2)
    assert np.array_equal(ball.ids, np.flatnonzero(d <= 3.0))
    capped = P.select(pf, dict(t=t, near=[-10.0, -6.0, 6.0], where=[dict(var="w", min=0.5)],
                               cap=10))
    assert len(capped) == 10 and capped.matched == len(ref) and set(capped.ids) <= set(ref)
    assert capped.ids[0] == ref[0] and capped.ids[-1] == ref[-1]  # every n-th: both ends
    r1 = P.select(pf, dict(t=t, near=[-10.0, -6.0, 6.0], cap=10, sample="random", seed=3))
    r2 = P.select(pf, dict(t=t, near=[-10.0, -6.0, 6.0], cap=10, sample="random", seed=3))
    assert np.array_equal(r1.ids, r2.ids) and len(r1) == 10


def test_saved_sets(pf, demo_run, tmp_path, monkeypatch):
    monkeypatch.setenv("CM1VIEW_EXPORTS_DIR", str(tmp_path / "exports"))
    s = P.select(pf, dict(box=[-12, -8, -8, -4], cap=5), "inflow / low")
    path = P.save_set(demo_run, s)
    assert path in P.list_sets(demo_run) and os.path.basename(path) == "inflow_low.npz"
    back = P.ParcelSet.load(path)
    assert np.array_equal(back.ids, s.ids) and back.rule == s.rule
    assert back.name == "inflow / low" and back.matched == s.matched and back.key == s.key


def test_trajectories_are_cached(pf, monkeypatch):
    s = P.select(pf, dict(box=[-12, -8, -8, -4]))
    tr = pf.trajectories(s, ("x", "y", "z", "th"))
    np.testing.assert_array_equal(tr["th"], pf.read("th")[:, s.ids])
    reads = []
    monkeypatch.setattr(pf, "read", lambda *a, **k: reads.append(a))
    assert pf.trajectories(s, ("x", "th"))["th"] is tr["th"]  # memory
    pf._traj.clear()
    np.testing.assert_array_equal(pf.trajectories(s, ("th",))["th"], tr["th"])  # disk
    assert not reads


def test_heads_between_parcel_times(pf):
    s = P.select(pf, dict(box=[-12, -8, -8, -4]))
    tr = pf.trajectories(s)
    i = 10
    t = 0.25 * pf.times[i] + 0.75 * pf.times[i + 1]
    x, _, _ = P.heads(pf, tr, t)
    np.testing.assert_allclose(x, 0.25 * tr["x"][i] + 0.75 * tr["x"][i + 1], rtol=1e-6)
    x, _, _ = P.heads(pf, tr, t, interp=False)
    np.testing.assert_array_equal(x, tr["x"][i])
    assert np.isnan(P.heads(pf, tr, pf.times[0] - 60.0)[0]).all()
    assert pf.window(t, "until") == slice(0, i + 1)
    assert pf.window(t, "last", 2.0) == slice(i - 1, i + 1)  # 60-s parcel times
    assert pf.window(t, "all") == slice(0, pf.nt)


def test_periodic_wraps_break_lines():
    x = np.array([[1.0, 9.0], [3.0, 9.5], [5.0, 0.2], [7.0, 0.5]], np.float32)  # (nt, n)
    y = np.zeros_like(x)
    pl = P.polylines(dict(x=x, y=y, v=x * 2), per=(10.0, 10.0))
    # parcel 0: no wrap; parcel 1 wraps between times 1 and 2
    ref = [1.0, 3.0, 5.0, 7.0, np.nan, 9.0, 9.5, np.nan, 0.2, 0.5, np.nan]
    np.testing.assert_array_equal(pl["x"], np.array(ref, np.float32))
    np.testing.assert_array_equal(pl["v"], 2 * pl["x"])
    assert np.isnan(P.polylines(dict(x=x, y=y))["x"]).sum() == 2  # not periodic


def test_heads_across_a_periodic_boundary(pf):
    a = np.array([[9.9], [0.1]], np.float32)
    t = pf.times[0] + 0.25 * (pf.times[1] - pf.times[0])
    assert P.at_time(pf, a, t, per=10.0)[0] == pytest.approx(9.9)
    assert P.at_time(pf, a, t)[0] == pytest.approx(7.45)


def test_split_files_join_by_time(pf, tmp_path):
    """Two files (e.g. a restart) overlapping in time: the later file wins there."""
    src = pf.paths[0]
    names = list(pf.vars)
    parts = []
    for k, (a, b) in enumerate(((0, 20), (18, pf.nt))):
        out = str(tmp_path / f"cm1out_pdata_{k}.nc")
        with netCDF4.Dataset(src) as d, netCDF4.Dataset(out, "w") as o:
            d.set_auto_mask(False)
            for dn, dim in d.dimensions.items():
                o.createDimension(dn, None if dim.isunlimited() else len(dim))
            o.setncatts({n: d.getncattr(n) for n in d.ncattrs()})
            o.createVariable("time", "f4", ("time",))[:] = d["time"][a:b]
            for n in names:
                v = o.createVariable(n, "f4", ("time", "xh"))
                v[:] = d[n][a:b] + (1000.0 if k == 1 and n == "w" else 0.0)
        parts.append(out)
    two = P.ParcelFile(parts[::-1])
    assert np.allclose(two.times, pf.times)
    w = two.read("w", [0, 100, 1500])
    ref = pf.read("w", [0, 100, 1500])
    np.testing.assert_array_equal(w[:18], ref[:18])
    np.testing.assert_allclose(w[18:], ref[18:] + 1000.0)  # the later file
    found = P.find_files(str(tmp_path))
    assert found == sorted(parts)


def test_for_run(reg):
    run, _ = reg.get()
    pf = P.for_run(run)
    assert pf is P.for_run(run) and pf.n > 0


# ------------------------------------------------------------------ the Parcels panel
def _wait_sets(v, n):
    from conftest import wait
    # (added on the pool's thread: listed in psets first, drawn a moment later)
    wait(lambda: len(v.psets) >= n and v._par_added >= n, msg=f"{n} parcel sets")


@pytest.fixture
def pviewer(viewer, tmp_path, monkeypatch):
    monkeypatch.setenv("CM1VIEW_EXPORTS_DIR", str(tmp_path / "exports"))
    viewer.tslider.value = 5  # 4800 s: between the first and last parcel times
    return viewer


def test_parcels_tool_click_and_box(pviewer):
    v = pviewer
    assert "Parcels" in v.mode.btns and v.pf is not None
    v.mode._on("Parcels", None)
    assert v.mode.value == "Parcels" and v.panel_col.visible and v.tabs.active == 5
    v.par_radius.value = 3.0
    v._on_tap(type("E", (), {"x": -8.0, "y": -5.0, "modifiers": {}})())
    _wait_sets(v, 1)
    ps = v.psets["set 1"]["set"]
    assert ps.rule["near"] == [-8.0, -5.0, 3.0] and ps.rule["t"] == 4800.0
    assert len(v.par_head_src.data["x"]) == len(ps)  # all inside the domain at 4800 s
    assert len(v.par_seg_src.data["x0"]) > 0 and v.par_cbar.visible  # coloured by z
    v.par_pick.value = "Parcel box"
    assert v.mode.value == "Parcel box" and v.mode.btns["Parcels"].css_classes == ["cv-on"]
    v.par_z1.value = 1.0
    v._on_select(type("E", (), {"final": True, "geometry": dict(
        type="rect", x0=-15.0, x1=-10.0, y0=-10.0, y1=-5.0)})())
    _wait_sets(v, 2)
    box = v.psets["set 2"]["set"]
    x, y, z = v.pf.positions(v.pf.nearest(4800.0))
    assert (x[box.ids] >= -15).all() and (z[box.ids] <= 1.0).all()
    assert [e[0] for e in v._item_entries()].count("par") == 2


def test_parcel_tails_heads_and_colours(pviewer):
    v = pviewer
    v.par_at.value = "first"
    v._par_choose(box=(-12.0, -6.0, -8.0, -2.0))
    _wait_sets(v, 1)
    ps = v.psets["set 1"]["set"]
    assert ps.rule["t"] == v.pf.times[0]
    v.par_window.value = "all"
    n_all = len(v.par_seg_src.data["x0"])
    v.par_window.value = "until"
    assert 0 < len(v.par_seg_src.data["x0"]) < n_all
    v.par_window.value = "none"
    assert len(v.par_seg_src.data["x0"]) == 0 and len(v.par_head_src.data["x"])
    v.par_color.value = ""
    assert not v.par_cbar.visible and set(v.par_head_src.data["color"]) == {
        v.psets["set 1"]["color"]}
    from conftest import wait
    v.par_color.value = "w"  # read in the pool, then drawn
    wait(lambda: v.par_cbar.visible, msg="coloured by w")
    tr = v.pf.trajectories(ps, ("w",))["w"]
    from cm1view.core import parcels as PP
    np.testing.assert_allclose(np.sort(v.par_head_src.data["val"]),
                               np.sort(PP.at_time(v.pf, tr, 4800.0)[np.isfinite(
                                   PP.heads(v.pf, v.pf.trajectories(ps), 4800.0)[0])]))
    v.tslider.value = 0  # t = 0: before the parcel output
    assert len(v.par_head_src.data["x"]) == 0 and "no parcel output" in v.par_info.object


def test_parcel_sets_rename_save_load_and_session(pviewer):
    from cm1view.viewer import app as A
    v = pviewer
    v._par_choose(-8.0, -5.0)
    _wait_sets(v, 1)
    v.par_list.value = "set 1"
    v.par_rename.value = "updraft"
    assert list(v.psets) == ["updraft"] and v.psets["updraft"]["set"].name == "updraft"
    v._par_save(v.psets["updraft"]["set"])
    assert "updraft" in v.par_saved.options
    v.par_saved.value = v.par_saved.options["updraft"]
    v._on_par_load(None)
    _wait_sets(v, 2)
    a, b = (e["set"] for e in v.psets.values())
    assert np.array_equal(a.ids, b.ids)
    v.par_window.value = "last"
    v.par_minutes.value = 5.0
    s = v.session_state()
    v2 = A.Viewer(v.run, v.F, reg=v.reg)
    v2.main()
    try:
        v2.apply_session(s)
        _wait_sets(v2, 2)
        assert [len(e["set"]) for e in v2.psets.values()] == [len(a), len(b)]
        assert v2.par_window.value == "last" and v2.par_minutes.value == 5.0
        assert v2.par_minutes.visible
    finally:
        v2.close()
    v._par_drop(v.par_list.value)
    assert len(v.psets) == 1


def test_section_projection():
    s, d = P.section_xy(np.array([1.0, 2.0, 0.0]), np.array([0.0, 1.0, -3.0]),
                        (0.0, 0.0), (4.0, 0.0))
    np.testing.assert_allclose(s, [1.0, 2.0, 0.0])
    np.testing.assert_allclose(d, [0.0, 1.0, -3.0])  # + left of A -> B


def test_band_matches_ensemble_band():
    from cm1view.core import series as ser
    from cm1view.figures.spec.panels import ensemble_band
    V = np.array([[1.0, 2.0, np.nan], [3.0, 6.0, 5.0], [2.0, 4.0, np.nan]])
    c, lo, hi = ser.band(V, "minmax", "mean")
    np.testing.assert_allclose(c, [2.0, 4.0, 5.0])
    np.testing.assert_allclose(lo, [1.0, 2.0, 5.0])
    T, c2, lo2, hi2 = ensemble_band([([0, 1, 2], v) for v in V], "minmax", "mean")
    np.testing.assert_allclose(c2, c[:2])
    np.testing.assert_allclose(hi2, hi[:2])


def test_parcels_on_section_in_3d_and_plot(pviewer):
    from conftest import wait
    v = pviewer
    v.par_at.value = "first"
    v._par_choose(box=(-12.0, -6.0, -8.0, -2.0))
    _wait_sets(v, 1)
    ps = v.psets["set 1"]["set"]
    # the plot: each parcel, the mean and a band over the parcel times
    wait(lambda: len(v.pp_mid.data["xs"]) == 1, msg="plot")
    assert len(v.pp_each.data["xs"]) == min(len(ps), 300) and v.pp_band.data["xs"]
    np.testing.assert_allclose(v.pp_mid.data["xs"][0], v.pf.times / 60.0)
    v.par_plot_kind.value = "scatter"
    wait(lambda: len(v.pp_scat.data["x"]) > 0, msg="scatter")
    assert v.pp_fig.xaxis[0].axis_label.startswith(v.par_plot_x.value)
    # the section: heads within ± 1 km of its line, at the section's time
    v.xs_pts = [(-14.0, -5.0), (0.0, -5.0)]
    v._show_panel(True, 1)
    v.request_xsec()
    wait(lambda: v._par_xs_key is not None and len(v.par_xs_head_src.data["x"]), msg="xs")
    tr = v.pf.trajectories(ps)
    hx, hy, hz = P.heads(v.pf, tr, v._par_xs_t, True, P.period(v.run))
    s, d = P.section_xy(hx, hy, *v.xs_pts)
    near = np.isfinite(s) & (np.abs(d) <= 1.0) & (s >= 0) & (s <= 14.0)
    assert len(v.par_xs_head_src.data["x"]) == near.sum()
    n_near = len(v.par_xs_src.data["x0"])
    v.par_xs_within.value = 0.0
    assert len(v.par_xs_src.data["x0"]) < n_near
    # the 3D view: tails and heads inside the region, in the set's colour
    v.par_color.value = ""
    v.workspace.value = "3D"
    v._set_box((-20.0, 5.0, -15.0, 5.0))
    v.request_3d()
    wait(lambda: v._par_3d_key is not None and v._trace("parcelheads")[1] is not None
         and len(v._trace("parcelheads")[1].x), msg="3D")
    _, lines = v._trace("parcels")
    assert np.isfinite(np.asarray(lines.x, float)).any() and not lines.line.showscale
    v.par_3d.value = False
    assert len(v._trace("parcels")[1].x) == 0
    look = v.session_state()["parcels"]["look"]
    assert look["plot"] == "scatter" and look["xs_within"] == 0.0 and look["in3d"] is False


# ------------------------------------------------------------------ figures (P4a)
def _par_spec(reg, kind="plan", **par):
    """A one-panel figure of the demo at 4800 s: dbz and a parcels layer."""
    from cm1view.figures import spec as fg
    run, F = reg.get()
    t = int(np.argmin(np.abs(run.times - 4800.0)))
    s = fg.default_spec(run, F, t)
    s.update(kind=kind, rows=1, cols=1, times=[t], times_s=[float(run.times[t])])
    s["runs"][0]["track"] = ""
    s["domain"] = dict(s["domain"], mode="full")
    if kind == "xsec":
        s["sections"] = [fg.section_defaults(orient="ab", pos="fixed", a=[-15.0, -5.0],
                                             b=[10.0, -5.0])]
    lay = dict(fg.layer_defaults("parcels", F), name="low",
               rule=dict(box=[-15.0, -5.0, -10.0, 0.0], z=[0.0, 1.0], cap=200), **par)
    s["layers"] = [s["layers"][0], lay]
    return fg.normalize(s, run, ""), run


@pytest.fixture
def pcache(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "CACHE_DIR", str(tmp_path / "cache"))


def test_figure_parcel_layer_plan(reg, pcache):
    from cm1view.figures import draw as figdraw
    from cm1view.figures.render import FigureData
    s, run = _par_spec(reg, cvar="w", units="m/s")
    d = FigureData().panel_data(s)[0]
    pf = P.for_run(run)
    ps = P.select(pf, s["layers"][1]["rule"])
    tr = pf.trajectories(ps, ("x", "y", "z", "w"))
    hx, hy, _ = P.heads(pf, tr, 4800.0, True, P.period(run))
    assert len(d["L1_hx"]) == np.sum(np.isfinite(hx) & np.isfinite(hy))
    np.testing.assert_allclose(np.sort(d["L1_hx"]), np.sort(hx[np.isfinite(hx)]), atol=1e-4)
    assert len(d["L1_pv"]) == len(d["L1_px"]) == len(d["L1_py"]) and len(d["L1_hv"])
    # tails up to the panel time: no vertex lies past where the parcels are at 4800 s
    last = pf.index_before(4800.0)
    assert np.nanmax(np.abs(d["L1_px"])) <= np.nanmax(np.abs(tr["x"][:last + 1])) + 1e-4
    # drawn: the panel's colorbar is the fill's; without a fill, the parcels'
    fig = figdraw.draw(s, {0: d})
    assert fig._cv_mappables
    s1 = dict(s, layers=[s["layers"][1]])
    fig = figdraw.draw(s1, FigureData().panel_data(s1))
    assert fig._cv_mappables and fig._cv_mappables[0][2][1]["units"] == "parcel w (m/s)"
    # in the set's colour: no values, no colorbar
    s2 = dict(s, layers=[dict(s["layers"][1], cvar="", tails="none")])
    d2 = FigureData().panel_data(s2)[0]
    assert "L1_pv" not in d2 and "L0_px" not in d2 and "L0_hv" not in d2 and len(d2["L0_hx"])
    assert not figdraw.draw(s2, {0: d2})._cv_mappables


def test_figure_parcel_layer_section_and_notes(reg, pcache):
    from cm1view.figures.render import FigureData
    s, run = _par_spec(reg, "xsec", within=2.0)
    fd = FigureData()
    d = fd.panel_data(s)[0]
    pf = P.for_run(run)
    ps = P.select(pf, s["layers"][1]["rule"])
    tr = pf.trajectories(ps)
    hx, hy, hz = P.heads(pf, tr, 4800.0, True, P.period(run))
    sa, sd = P.section_xy(hx, hy, (-15.0, -5.0), (10.0, -5.0))
    near = np.isfinite(sa) & np.isfinite(hz) & (np.abs(sd) <= 2.0) & (sa >= 0) & (sa <= 25.0)
    assert len(d["L1_hx"]) == near.sum() > 0
    np.testing.assert_allclose(np.sort(d["L1_hy"]), np.sort(hz[near]), atol=1e-4)
    assert np.nanmin(d["L1_px"]) >= d["xlim"][0] - 1e-4  # (on the panel's x axis)
    whole = fd.panel_data(dict(s, layers=[s["layers"][0], dict(s["layers"][1],
                                                                xs_tails="whole")]))[0]
    assert np.isfinite(whole["L1_py"]).sum() != np.isfinite(d["L1_py"]).sum()
    # nothing to draw: a note, the panel stays
    s0 = dict(s, layers=[s["layers"][0], dict(s["layers"][1], rule=dict(
        box=[100.0, 101.0, 100.0, 101.0]))])
    d0 = fd.panel_data(s0)[0]
    assert not d0.get("missing") and "none chosen" in d0["notes"] and "L1_hx" not in d0


def test_figure_parcel_choice_is_kept_and_keyed(reg, pcache, monkeypatch):
    from cm1view.figures import spec as fg
    s, run = _par_spec(reg)
    pf = P.for_run(run)
    a = P.chosen(pf, s["layers"][1]["rule"], name="a")
    monkeypatch.setattr(P, "select", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    b = P.chosen(pf, s["layers"][1]["rule"], name="b")
    assert b.name == "b" and np.array_equal(a.ids, b.ids)
    assert len(P.chosen(pf, None, [3, 1], "ids")) == 2
    k0 = fg.data_key(s, 0, None)
    for change, same in ((dict(lw=3.0, color="#000000"), True), (dict(cvar="w"), False),
                         (dict(tails="all"), False), (dict(rule=dict(cap=5)), False)):
        s2 = dict(s, layers=[s["layers"][0], dict(s["layers"][1], **change)])
        assert (fg.data_key(s2, 0, None) == k0) == same, change


def test_template_moves_the_parcel_rule(reg):
    from cm1view.figures import spec as fg
    s, run = _par_spec(reg)
    s["layers"][1]["rule"] = dict(s["layers"][1]["rule"], t=4200.0)
    tpl = fg.template(s)
    t = int(np.argmin(np.abs(run.times - 5400.0)))
    out = fg.from_template(tpl, run, t)
    assert out["layers"][1]["rule"]["t"] == pytest.approx(4200.0 + float(run.times[t]) - 4800.0)
    assert fg.shift_times(s, 600.0)["layers"][1]["rule"]["t"] == 4200.0  # (frames: kept)


def test_figure_from_map_and_section_bring_parcel_sets(pviewer, ed):
    from conftest import render
    v = pviewer
    v.request_parcels(dict(t=4800.0, near=[-8.0, -5.0, 3.0], cap=100), "near")
    _wait_sets(v, 1)
    v.request_parcels(dict(box=[-15.0, -5.0, -10.0, 0.0], z=[0.0, 1.0], cap=200), "low")
    _wait_sets(v, 2)
    v.par_window.value = "all"
    ed.from_map()
    doc = ed.shell.doc
    lids = [i["ref"] for i in doc["panels"][0]["layers"]]
    lays = [doc["layers"][i] for i in lids if doc["layers"][i]["type"] == "parcels"]
    assert [lay["name"] for lay in lays] == ["near", "low"]
    assert lays[0]["rule"] == v.psets["near"]["set"].rule and lays[0]["tails"] == "all"
    assert lays[0]["cvar"] == v.par_color.value and lays[0]["color"] == v.psets["near"]["color"]
    _, data, _ = render(ed)
    j = [doc["layers"][i]["type"] for i in lids].index("parcels")
    assert len(data[0][f"L{j}_hx"]) and len(data[0][f"L{j}_px"])
    # the cross-section
    v.xs_pts = [(-15.0, -5.0), (10.0, -5.0)]
    ed.from_xsec()
    doc = ed.shell.doc
    assert doc["panels"][0]["kind"] == "xsec"
    lays = [lay for lay in doc["layers"].values() if lay["type"] == "parcels"]
    assert len(lays) == 2 and lays[0]["within"] == v.par_xs_within.value
    render(ed)


def _scene_par_spec(reg, **par):
    """A 3D scene figure of the demo at 4800 s over a box: no surfaces, two parcel sets
    (the second coloured by w)."""
    from cm1view.figures import spec as fg
    s, run = _par_spec(reg)
    e = dict(s["layers"][1], lw=1.5, **par)
    s.update(kind="scene", time_s=4800.0, scene3d=dict(
        box=[-12.0, 0.0, -10.0, 2.0], ztop=6.0, isos=[],
        parcels=[e, dict(e, name="w", cvar="w", units="m/s", tails="all")]))
    s["export"] = dict(s["export"], dpi=50)
    return s, run


def test_scene_parcels_inside_the_region_and_kept_apart(reg, pcache):
    from cm1view.figures import spec as fg
    from cm1view.figures.render import FigureData
    s, run = _scene_par_spec(reg)
    fd = FigureData()
    d = fd.panel_data(s)[0]
    assert not d.get("missing") and len(d["P0_hx"]) and len(d["P1_pv"]) == len(d["P1_px"])
    assert "P0_pv" not in d and "P0_hv" not in d
    for c, (lo, hi) in (("x", (-12.0, 0.0)), ("y", (-10.0, 2.0)), ("z", (-1.0, 6.0))):
        for k in (f"P0_h{c}", f"P1_p{c}"):
            a = d[k][np.isfinite(d[k])]
            assert a.min() >= lo - 1e-4 and a.max() <= hi + 1e-4, k
    pf = P.for_run(run)
    tr = pf.trajectories(P.select(pf, s["scene3d"]["parcels"][0]["rule"]))
    hx, hy, hz = P.heads(pf, tr, 4800.0, True, P.period(run))
    inside = (hx >= -12) & (hx <= 0) & (hy >= -10) & (hy <= 2) & (hz <= 6)
    assert len(d["P0_hx"]) == np.sum(np.isfinite(hx) & np.isfinite(hz) & inside)
    # the parcels' look, or the parcels themselves, change nothing else's key; their
    # look leaves their own key too
    k, kp = fg.scene_key(s, run.path), fg.scene_parcel_key(s, run.path, d)
    for change, same in ((dict(color="#000000", lw=3.0, ms=6.0, alpha=0.3), True),
                         (dict(tails="none"), False), (dict(on=False), False),
                         (dict(rule=dict(cap=5)), False)):
        p = [dict(s["scene3d"]["parcels"][0], **change), s["scene3d"]["parcels"][1]]
        s2 = dict(s, scene3d=dict(s["scene3d"], parcels=p))
        assert fg.scene_key(s2, run.path) == k
        assert (fg.scene_parcel_key(s2, run.path, d) == kp) == same, change
    s3 = dict(s, scene3d=dict(s["scene3d"], parcels=[dict(s["scene3d"]["parcels"][0],
                                                          tails="none", on=True)]))
    d3 = fd.panel_data(s3)[0]
    assert "P0_px" not in d3 and "P1_hx" not in d3 and len(d3["P0_hx"])
    # nothing chosen: a note, the scene stays
    s4 = dict(s, scene3d=dict(s["scene3d"], parcels=[dict(
        s["scene3d"]["parcels"][0], rule=dict(box=[100.0, 101.0, 100.0, 101.0]))]))
    d4 = fd.panel_data(s4)[0]
    assert not d4.get("missing") and "none chosen" in d4["notes"]
    # a template moves the sets' time as a layer's
    s["scene3d"]["parcels"][0]["rule"] = dict(s["scene3d"]["parcels"][0]["rule"], t=4200.0)
    t = int(np.argmin(np.abs(run.times - 5400.0)))
    out = fg.from_template(fg.template(s), run, t)
    assert out["scene3d"]["parcels"][0]["rule"]["t"] == pytest.approx(
        4200.0 + float(run.times[t]) - 4800.0)


def test_scene_figure_draws_parcels(reg, pcache):
    pytest.importorskip("pyvista")
    from cm1view.figures import draw as figdraw
    from cm1view.figures.render import FigureData
    s, run = _scene_par_spec(reg)
    s["scene3d"]["parcels"][1]["cbar_label"] = "w of the parcels"
    d = FigureData().panel_data(s)[0]
    arr = figdraw.scene_parcels(d, figdraw.scene_spec(d, s))
    assert [p["name"] for p in arr] == ["low", "w"] and arr[0]["cm"] is None
    assert arr[1]["norm"].vmin == -arr[1]["norm"].vmax  # (straddles 0: symmetric)
    fig = figdraw.draw(s, {0: d})
    ax = fig._cv_axes[0]
    assert ax.images and getattr(ax, "_cv_proj", None)
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ["low", "w"]
    (cb,) = [a for a in fig.axes if a is not ax]
    assert "w of the parcels" in (cb.get_ylabel(), cb.get_xlabel())
    # no colorbar asked for; a set unticked: not drawn
    s2 = dict(s, scene3d=dict(s["scene3d"], look=dict(parcel_bar="none"), parcels=[
        s["scene3d"]["parcels"][0], dict(s["scene3d"]["parcels"][1], on=False)]))
    fig = figdraw.draw(s2, FigureData().panel_data(s2))
    ax = fig._cv_axes[0]
    assert len(fig.axes) == 1 and [t.get_text() for t in ax.get_legend().get_texts()] == ["low"]


# ------------------------------------------------------------------ parcel series (P4c)
def test_parcel_series_arrays():
    """Centre and band over the parcels at each parcel time (a parcel gone: left out),
    d/dt along each parcel, and up to `each` parcels' own lines in one NaN-separated
    line; one parcel: its own line."""
    from types import SimpleNamespace
    from cm1view.core import series as ser
    from cm1view.figures import spec as fg
    pf = SimpleNamespace(times=np.array([0.0, 60.0, 120.0, 180.0]))
    a = np.array([[1.0, 2.0, 3.0], [2.0, 4.0, np.nan], [3.0, 6.0, 9.0], [4.0, 8.0, 12.0]])
    e = dict(ens="minmax", ens_mid="mean", each=2, op="")
    out = fg.parcel_series_arrays(pf, a, e, t0_min=1.0)
    np.testing.assert_allclose(out["t"], [-1.0, 0.0, 1.0, 2.0])
    c, lo, hi = ser.band(a.T, "minmax", "mean")
    np.testing.assert_allclose(out["mid"], c)
    np.testing.assert_allclose(out["mid"][1], 3.0)  # (the gone parcel left out)
    np.testing.assert_allclose(out["lo"], lo)
    np.testing.assert_allclose(out["hi"], hi)
    T, V = out["each"]
    assert np.isnan(T).sum() == 1 and len(T) == 2 * 4 + 1  # (two lines, one gap)
    np.testing.assert_allclose(V[:4], a[:, 0])
    np.testing.assert_allclose(V[5:], a[:, 2])
    d = fg.parcel_series_arrays(pf, a, dict(e, op="ddt", each=0), 0.0)
    assert d["each"] is None
    np.testing.assert_allclose(d["mid"][0],  # (the parcel missing next to it left out)
                               np.nanmean(np.gradient(a, pf.times, axis=0)[0]))
    one = fg.parcel_series_arrays(pf, a[:, :1], dict(e, ens="", ens_mid=""), 0.0)
    np.testing.assert_allclose(one["mid"], a[:, 0])
    assert one["lo"] is None
    none = fg.parcel_series_arrays(pf, a, dict(e, ens="", ens_mid="", each=0), 0.0)
    assert none["mid"] is None and none["lo"] is None


def _par_series_spec(reg, **par):
    """A one-panel time-series figure of the demo: a parcel series of w."""
    from cm1view.figures import spec as fg
    run, F = reg.get()
    s = fg.default_spec(run, F, int(np.argmin(np.abs(run.times - 4800.0))))
    s.update(kind="line", rows=1, cols=1)
    src = dict(name="low", rule=dict(box=[-15.0, -5.0, -10.0, 0.0], z=[0.0, 1.0], cap=200))
    e = dict(fg.parcel_series_defaults(src, "w", "m/s"), **par)
    s["series"] = [e]
    return fg.normalize(s, run, ""), run


def test_figure_parcel_series(reg, pcache):
    """A parcel series draws its mean and band over the parcel times (not the 3D
    output's) and its parcels' own lines faint; a variable the run lacks: a note."""
    from cm1view.figures import draw as figdraw
    from cm1view.figures.render import FigureData
    s, run = _par_series_spec(reg, each=10)
    d = FigureData().panel_data(s)[0]
    pf = P.for_run(run)
    w = pf.trajectories(P.select(pf, s["series"][0]["rule"]), ("w",))["w"]
    assert d["nlines"] == 2 and d["S0_mem"] == 1 and d["S1_ens"] == w.shape[1]
    have = np.flatnonzero(np.isfinite(w).any(axis=1))  # (the parcel times, not the 3D's)
    sl = slice(have[0], have[-1] + 1)
    assert pf.nt != len(run.times) and len(d["S1_t"]) == len(pf.times[sl])
    np.testing.assert_allclose(d["S1_t"], pf.times[sl] / 60.0)
    np.testing.assert_allclose(d["S1_v"], np.nanmean(w[sl], axis=1), rtol=1e-5)
    assert np.isnan(d["S0_t"]).sum() == 9 and d["S1_label"] == "low: w"
    figdraw.draw(s, {0: d})
    # its own time zero; the figure's time range from the parcel times
    s2 = dict(s, series=[dict(s["series"][0], t0_min=60.0)])
    d2 = FigureData().panel_data(s2)[0]
    np.testing.assert_allclose(d2["S1_t"], pf.times[sl] / 60.0 - 60.0)
    assert d2["xlim"][0] == pytest.approx(pf.times[sl][0] / 60.0 - 60.0)
    # its run's time zero adds to it
    s4 = dict(s2, runs=[dict(s2["runs"][0], t0_min=5.0)])
    np.testing.assert_allclose(FigureData().panel_data(s4)[0]["S1_t"],
                               pf.times[sl] / 60.0 - 65.0)
    s3 = dict(s, series=[dict(s["series"][0], var="nope")])
    assert "no parcel nope" in FigureData().panel_data(s3)[0]["missing"]


def test_template_moves_the_parcel_series_rule(reg):
    from cm1view.figures import spec as fg
    s, run = _par_series_spec(reg)
    s["series"][0]["rule"] = dict(s["series"][0]["rule"], t=4200.0)
    assert s["time_s"] == pytest.approx(4800.0)
    t = int(np.argmin(np.abs(run.times - 5400.0)))
    out = fg.from_template(fg.template(s), run, t)
    e = out["series"][0]
    assert e["source"] == "parcels" and e["runs"] == [0]
    assert e["rule"]["t"] == pytest.approx(4200.0 + float(run.times[t]) - 4800.0)


# ------------------------------------------------------------------ P5a: 3D fields along trajectories
def test_time_weights_between_3d_outputs(pf, reg):
    """A parcel time at a 3D time: that field alone; between two: linear weights;
    outside the 3D outputs' span: absent."""
    run, _ = reg.get()
    T = np.array([3600.0, 3900.0, 4500.0])
    wts = pf.time_weights(T)
    got = {}
    for k, (ii, ww) in wts.items():
        for i, w in zip(ii, ww):
            got.setdefault(int(i), {})[k] = float(w)
    for i, t in enumerate(pf.times):
        if t > 4500.5:
            assert i not in got
            continue
        assert sum(got[i].values()) == pytest.approx(1.0)
        if t in T:
            assert got[i] == {int(np.flatnonzero(T == t)[0]): 1.0}
    i = int(np.flatnonzero(pf.times == 3960.0)[0])  # 1/10 of the way 3900 → 4500
    assert got[i] == pytest.approx({1: 0.9, 2: 0.1})


def test_grid_field_sampled_along_trajectories(pf, reg, monkeypatch):
    """"@w" (the 3D output's w at the parcels) matches the parcel output's own w at the
    3D times; derived fields too; cached on disk (a new ParcelFile samples nothing);
    titles, units and the grouped choices."""
    run, F = reg.get()
    pf.attach(F)
    assert pf.has("@w") and pf.has("w") and not pf.has("@nope") and not pf.has("nope")
    assert pf.units("@w") == F["w"].units and "at the parcels" in pf.title("@w")
    ps = P.select(pf, dict(box=[-15.0, -5.0, -10.0, 0.0], z=[0.0, 1.0], cap=150))
    seen = []
    tr = pf.trajectories(ps, ("w", "@w"), progress=lambda a, b: seen.append((a, b)))
    assert seen and seen[-1][0] == seen[-1][1]
    at = [i for i, t in enumerate(pf.times) if np.min(np.abs(run.times - t)) < 0.5]
    a, b = tr["w"][at], tr["@w"][at]
    ok = np.isfinite(a) & np.isfinite(b)
    assert ok.sum() > 100
    assert np.sqrt(np.mean((a[ok] - b[ok]) ** 2)) < 0.1 * np.nanmax(np.abs(a))
    assert (np.isnan(tr["@w"]) >= np.isnan(tr["w"])).all()  # (gone parcels: NaN too)
    derived = next(n for n, d in F.defs.items() if d.derived and d.ndim == 3
                   and not d.column)
    assert pf.has("@" + derived)
    v = pf.trajectories(ps, ("@" + derived,))["@" + derived]
    assert v.shape == (pf.nt, len(ps)) and np.isfinite(v).any()
    again = P.ParcelFile(pf.paths)
    again.attach(F)
    monkeypatch.setattr(F, "at_points", lambda *a, **k: pytest.fail("sampled again"))
    np.testing.assert_array_equal(again.trajectories(ps, ("@w",))["@w"], tr["@w"])
    ch = P.var_choices(pf, {"Set colour": ""}, keep="mine")
    assert ch[""] == {"Set colour": ""} and "w" in ch["Parcel output"].values()
    assert "mine" in ch["Parcel output"].values()
    assert "@w" in ch["3D fields at the parcels"].values()
    assert P.var_label("@thpert") == "thpert at the parcels" and P.var_label("w") == "w"


def test_viewer_colours_and_plots_a_grid_field(pviewer):
    from conftest import wait
    v = pviewer
    v._par_choose(box=(-12.0, -6.0, -8.0, -2.0))
    _wait_sets(v, 1)
    assert "@w" in v.par_color.groups["3D fields at the parcels"].values()
    v.par_color.value = "@w"  # sampled in the pool, then drawn
    wait(lambda: v.par_cbar.visible and "at the parcels" in v.par_cbar.title,
         msg="coloured by @w")
    ps = v.psets["set 1"]["set"]
    tr = v.pf.trajectories(ps, ("@w",))["@w"]
    vals = v.par_head_src.data["val"]
    np.testing.assert_allclose(np.sort(vals[np.isfinite(vals)]),
                               np.sort(P.at_time(v.pf, tr, 4800.0)[np.isfinite(
                                   P.at_time(v.pf, tr, 4800.0)) & np.isfinite(
                                   P.heads(v.pf, v.pf.trajectories(ps), 4800.0)[0])]),
                               rtol=1e-5)
    v.par_plot_y.value = "@w"
    assert "at the parcels" in v.pp_fig.yaxis.axis_label and len(v.pp_mid.data["xs"])


def test_figure_layer_and_series_of_a_grid_field(reg, pcache):
    from cm1view.figures import draw as figdraw
    from cm1view.figures.render import FigureData
    s, run = _par_spec(reg, cvar="@w", units="m/s")
    d = FigureData().panel_data(s)[0]
    assert "L1_hv" in d and np.isfinite(d["L1_hv"]).any() and not d.get("notes")
    figdraw.draw(s, {0: d})
    s, run = _par_series_spec(reg, var="@w")
    d = FigureData().panel_data(s)[0]
    assert not d.get("missing") and np.isfinite(d["S0_v"]).any()  # (no own lines: S0)
    figdraw.draw(s, {0: d})
    s3 = dict(s, series=[dict(s["series"][0], var="@nope")])
    assert "no parcel @nope" in FigureData().panel_data(s3)[0]["missing"]


# ------------------------------------------------------------------ export (P5b)
def _read_csv(path):
    """(rows with named columns, the # lines) of a parcel CSV export."""
    with open(path) as f:
        head = [ln for ln in f if ln.startswith("#")]
    return np.genfromtxt(path, delimiter=",", skip_header=len(head), names=True), head


def test_export_netcdf_matches_trajectories(reg, pcache, tmp_path):
    run, F = reg.get()
    pf = P.for_run(run, F)
    ps = P.select(pf, dict(box=[-15.0, -5.0, -10.0, 0.0], z=[0.0, 1.0], cap=60), "up")
    ti = P.export_times(pf, 4000.0, 5000.0, 2)
    assert pf.times[ti[0]] == pytest.approx(pf.times[pf.nearest(4000.0)])
    r = P.export_set(pf, ps, str(tmp_path / "up.nc"), ["w", "@w"], ti)
    assert r["format"] == "netCDF" and r["times"] == len(ti) and not r["cancelled"]
    tr = pf.trajectories(ps, ("x", "z", "w", "@w"))
    with netCDF4.Dataset(r["path"]) as d:
        assert d["x"].dimensions == ("time", "parcel")
        assert set(d.variables) == {"time", "parcel", "x", "y", "z", "w", "w_at_parcels"}
        np.testing.assert_array_equal(d["parcel"][:], ps.ids + 1)  # CM1's numbers
        np.testing.assert_allclose(d["time"][:], pf.times[ti])
        for c, n in (("x", "x"), ("z", "z"), ("w", "w"), ("w_at_parcels", "@w")):
            np.testing.assert_array_equal(d[c][:].filled(np.nan), tr[n][ti])
        assert d["w_at_parcels"].cm1view_name == "@w" and d["x"].units == "km"
        assert "at the parcels" in d["w_at_parcels"].long_name
        assert d.cm1view_set == "up" and '"cap": 60' in d.cm1view_rule
    assert not os.path.exists(r["path"] + ".part")
    assert P.export_column("@ddz.winterp") == "ddz_winterp_at_parcels"
    with pytest.raises(ValueError, match="not parcel variables"):
        P.export_set(pf, ps, str(tmp_path / "bad.nc"), ["nope"])
    with pytest.raises(ValueError, match=".nc"):
        P.export_set(pf, ps, str(tmp_path / "bad.txt"))


def test_export_csv_in_blocks_and_stop(reg, pcache, tmp_path, monkeypatch):
    run, F = reg.get()
    pf = P.for_run(run, F)
    ps = P.select(pf, dict(box=[-15.0, -5.0, -10.0, 0.0], cap=40))
    monkeypatch.setattr(P, "BLOCK", 4 * pf.nt * 4 * 7)  # 7 parcels a block (4 variables)
    seen = []
    r = P.export_set(pf, ps, str(tmp_path / "a.csv"), ["w"],
                     progress=lambda a, b, what: seen.append((a, b)))
    assert seen[-1] == (len(seen), len(seen)) and len(seen) == 4 * int(np.ceil(40 / 7))
    a, head = _read_csv(r["path"])
    assert any("units:" in h and "w m/s" in h for h in head)
    assert a.dtype.names == ("parcel", "time_s", "x_km", "y_km", "z_km", "w")
    tr = pf.trajectories(ps, ("x", "w"))
    there = np.isfinite(tr["x"])
    assert len(a) == there.sum()  # one row per parcel and time it has a position at
    col = np.searchsorted(ps.ids + 1, a["parcel"].astype(np.int64))
    row = np.searchsorted(pf.times, a["time_s"])
    np.testing.assert_allclose(a["x_km"], tr["x"][row, col], rtol=1e-6)
    np.testing.assert_allclose(a["w"], tr["w"][row, col], rtol=1e-5, atol=1e-9)
    calls = []
    r = P.export_set(pf, ps, str(tmp_path / "b.nc"), ["w"],
                     cancelled=lambda: calls.append(1) or len(calls) > 2)
    assert r["cancelled"] and not os.path.exists(r["path"]) \
        and not os.path.exists(r["path"] + ".part")


def test_export_command_line(reg, pcache, tmp_path, monkeypatch, capsys):
    from cm1view.core import export as ex
    monkeypatch.setenv("CM1VIEW_EXPORTS_DIR", str(tmp_path / "exports"))
    run, F = reg.get()
    pf = P.for_run(run, F)
    ps = P.select(pf, dict(near=[-8.0, -5.0, 3.0]), "updraft")
    P.save_set(run.path, ps)
    assert ex.main([run.path, "--parcels", ".", "--list"]) == 0
    out = capsys.readouterr().out
    assert "updraft" in out and "\n  @" in out and "dwdt" in out and "wres" in out
    assert ex.main([run.path, "--parcels", "updraft", "--fields", "w,winterp",
                    "--from", "70", "--to", "80"]) == 0
    path = P.export_path(run.path, ps)
    with netCDF4.Dataset(path) as d:
        assert {"w", "winterp_at_parcels"} <= set(d.variables)  # (a 3D field's own name)
        assert d["time"][0] == pytest.approx(pf.times[pf.nearest(4200.0)])
        assert d["time"][-1] == pytest.approx(pf.times[pf.nearest(4800.0)])
    assert ex.main([run.path, "--parcels", "updraft"]) == 2  # (there: no --overwrite)
    assert ex.main([run.path, "--parcels", "updraft", "--csv"]) == 0
    assert os.path.exists(path[:-3] + ".csv")
    assert ex.main([run.path, "--parcels", "nothere"]) == 2


def test_viewer_exports_a_set(pviewer):
    from conftest import wait
    v = pviewer
    v._par_choose(box=(-12.0, -6.0, -8.0, -2.0))
    _wait_sets(v, 1)
    assert not v.par_export.disabled and not v._pexp_built
    v._on_par_export(None)
    assert v.par_exp_box.visible and v.pexp_path.value.endswith("set_1.nc")
    v.pexp_fmt.value = ".csv"
    assert v.pexp_path.value.endswith("set_1.csv")  # (the default follows the format)
    v.pexp_vars.value = ["w"]
    v.pexp_times.value = "until"
    ps, names, ti = v._pexp_plan()
    assert names == ["x", "y", "z", "w"] and v.pf.times[ti[-1]] <= 4800.0 + 0.5
    assert "parcels ×" in v.pexp_note.object
    v._on_pexp_go(None)
    wait(lambda: "Saved" in v.pexp_note.object, msg="parcel export written")
    a, _ = _read_csv(v.pexp_path.value)
    assert a["time_s"].max() <= 4800.0 and set(a["parcel"].astype(int)) <= set(ps.ids + 1)
    v._par_drop("set 1")
    assert v.par_export.disabled and not v.par_exp_box.visible


# ------------------------------------------------------------------ relative to the storm (P5c)
def _fixes(run, u, v, ts=range(2, 6)):
    """A track of fixes moving at ground-relative (u, v) m/s, at 0, 0 at t = 0."""
    return {t: dict(x=(u - run.umove) * run.times[t] / 1000.0,
                    y=(v - run.vmove) * run.times[t] / 1000.0, value=1.0, source="manual")
            for t in ts}


def test_frame_shift_and_moving_trajectories(pf, reg):
    run, _ = reg.get()
    sh = P.frame_shift(pf, run, 4800.0, "motion", demo.STORM)
    du = (demo.STORM[0] - run.umove) / 1000.0
    np.testing.assert_allclose(sh[0], du * (pf.times - 4800.0), atol=1e-5)
    assert sh[0][pf.nearest(4800.0)] == 0.0
    # a track at the same motion: the same frame, beyond its ends too
    st = P.frame_shift(pf, run, 4800.0, "track", None, _fixes(run, *demo.STORM))
    np.testing.assert_allclose(st[0], sh[0], atol=1e-5)
    np.testing.assert_allclose(st[1], sh[1], atol=1e-5)
    # the grid, the grid's own motion, a track of one fix: no frame
    assert P.frame_shift(pf, run, 4800.0) is None
    assert P.frame_shift(pf, run, 4800.0, "motion", (run.umove, run.vmove)) is None
    assert P.frame_shift(pf, run, 4800.0, "track", None, {2: dict(x=0.0, y=0.0)}) is None
    ps = P.select(pf, dict(box=[-15.0, -5.0, -10.0, 0.0], cap=30))
    tr = pf.trajectories(ps)
    m = P.moving(tr, sh)
    assert P.moving(tr, None) is tr and m["z"] is tr["z"] and m["x"].shape == tr["x"].shape
    want = tr["x"] - sh[0][:, None]
    np.testing.assert_array_equal(np.asarray(m["x"]), want)
    idx = np.array([1, 4, 9])
    np.testing.assert_array_equal(m["x"][idx], want[idx])
    np.testing.assert_array_equal(m["x"][3], want[3])
    np.testing.assert_array_equal(m["y"][2:5, :4], (tr["y"] - sh[1][:, None])[2:5, :4])
    per = P.period(run)
    np.testing.assert_allclose(P.heads(pf, m, 4800.0, True, per)[0],  # (heads stay put)
                               P.heads(pf, tr, 4800.0, True, per)[0], atol=1e-5)
    assert P.frame_label("track") == "moving with the tracked storm"
    assert P.frame_label("motion", (15, 3)) == "moving at (15, 3) m/s"


def test_export_writes_storm_relative_positions(reg, pcache, tmp_path, monkeypatch, capsys):
    from cm1view.core import export as ex
    run, F = reg.get()
    pf = P.for_run(run, F)
    ps = P.select(pf, dict(box=[-15.0, -5.0, -10.0, 0.0], cap=20), "sr")
    sh = P.frame_shift(pf, run, 4800.0, "motion", demo.STORM)
    tr = pf.trajectories(ps)
    r = P.export_set(pf, ps, str(tmp_path / "sr.nc"), ["w"], shift=sh, frame="f")
    with netCDF4.Dataset(r["path"]) as d:
        assert {"x_sr", "y_sr"} <= set(d.variables) and d["x_sr"].units == "km"
        np.testing.assert_allclose(d["x_sr"][:].filled(np.nan), tr["x"] - sh[0][:, None],
                                   atol=1e-5)
        assert "x_sr" in d.comment
    monkeypatch.setattr(P, "BLOCK", 4 * pf.nt * 6 * 7)  # 7 parcels a block (6 columns)
    ti = P.export_times(pf, 4000.0, 5000.0)
    r = P.export_set(pf, ps, str(tmp_path / "sr.csv"), ["w"], ti, shift=sh, frame="f")
    a, head = _read_csv(r["path"])
    assert a.dtype.names[-2:] == ("x_sr_km", "y_sr_km") and any("x_sr" in h for h in head)
    np.testing.assert_allclose(a["x_sr_km"] - a["x_km"],
                               -sh[0][np.searchsorted(pf.times, a["time_s"])], atol=1e-4)
    # the command line: --relative with --storm, or with the run's track (none here)
    monkeypatch.setenv("CM1VIEW_EXPORTS_DIR", str(tmp_path / "exports"))
    P.save_set(run.path, ps)
    assert ex.main([run.path, "--parcels", "sr", "--relative", "80", "--storm",
                    f"{demo.STORM[0]},{demo.STORM[1]}"]) == 0
    with netCDF4.Dataset(P.export_path(run.path, ps)) as d:
        np.testing.assert_allclose(d["x_sr"][:].filled(np.nan), tr["x"] - sh[0][:, None],
                                   atol=1e-5)
    assert ex.main([run.path, "--parcels", "sr", "--relative", "80", "--track", "none",
                    "--overwrite"]) == 2
    assert "--relative needs" in capsys.readouterr().err


def test_viewer_tails_seen_moving_with_the_storm(pviewer):
    v = pviewer
    v.par_window.value = "all"
    v._par_choose(box=(-12.0, -6.0, -8.0, -2.0))
    _wait_sets(v, 1)
    x0 = np.array(v.par_seg_src.data["x0"])
    h0 = np.sort(v.par_head_src.data["x"])
    v.par_frame.value = "motion"
    assert v.par_fu.visible and v.par_fv.visible
    v.par_fu.value, v.par_fv.value = demo.STORM
    x1 = np.array(v.par_seg_src.data["x0"])
    np.testing.assert_allclose(np.sort(v.par_head_src.data["x"]), h0, atol=1e-5)
    assert len(x1) == len(x0) and not np.allclose(x1, x0)
    assert "moving at (15, 3) m/s" in v.par_info.object
    v.tslider.value = 6  # (another reference time: the tails move)
    assert not np.allclose(np.array(v.par_seg_src.data["x0"]), x1)
    v.par_frame.value = "track"
    assert "no track of two fixes" in v.par_info.object
    v.fixes = _fixes(v.run, *demo.STORM, ts=range(3, 8))
    v._update_track_view()  # (editing the track redraws them)
    assert "moving with the tracked storm" in v.par_info.object
    v._on_par_export(None)
    assert v.pexp_sr.visible and v._pexp_frame()[0] is not None
    look = v.session_state()["parcels"]["look"]
    assert look["frame"] == "track" and look["frame_u"] == demo.STORM[0]
    v.par_frame.value = "grid"
    assert not v.pexp_sr.visible and v._pexp_frame() == (None, "")


def test_figure_parcels_seen_moving_with_the_storm(reg, pcache):
    from cm1view.figures import spec as fg
    from cm1view.figures.render import FigureData
    s, run = _par_spec(reg, tails="all")
    fd = FigureData()
    d = fd.panel_data(s)[0]
    mv = dict(s, layers=[s["layers"][0], dict(s["layers"][1], moving="motion",
                                              move_u=demo.STORM[0], move_v=demo.STORM[1])])
    assert fg.data_key(mv, 0, None) != fg.data_key(s, 0, None)
    d2 = fd.panel_data(mv)[0]
    np.testing.assert_allclose(np.sort(d2["L1_hx"]), np.sort(d["L1_hx"]), atol=1e-4)
    assert np.nanmax(np.abs(d2["L1_px"] - d["L1_px"])) > 1.0
    tk = dict(s, layers=[s["layers"][0], dict(s["layers"][1], moving="track")])
    assert fg.parcels_follow_track(tk["layers"]) and not fg.parcels_follow_track(s["layers"])
    d3 = fd.panel_data(tk)[0]  # (no track in this figure's run: the grid, and a note)
    assert "no track" in d3["notes"]
    np.testing.assert_allclose(d3["L1_px"], d["L1_px"], equal_nan=True)
    lay = fg.layer_defaults("parcels", reg.get()[1])
    assert lay["moving"] == "grid" and lay["move_u"] == lay["move_v"] == 0.0
    # a 3D scene's sets: keyed by the track only when one moves with it
    sc, _ = _scene_par_spec(reg)
    ds = fd.panel_data(sc)[0]
    assert fg.scene_parcel_key(sc, run.path, ds, "a") == fg.scene_parcel_key(sc, run.path,
                                                                              ds, "b")
    p = [dict(e, moving="track") for e in sc["scene3d"]["parcels"]]
    st = dict(sc, scene3d=dict(sc["scene3d"], parcels=p))
    assert fg.scene_parcel_key(st, run.path, ds, "a") != fg.scene_parcel_key(st, run.path,
                                                                              ds, "b")
    p = [dict(e, moving="motion", move_u=demo.STORM[0], move_v=demo.STORM[1])
         for e in sc["scene3d"]["parcels"]]
    dm = fd.panel_data(dict(sc, scene3d=dict(sc["scene3d"], parcels=p)))[0]
    np.testing.assert_allclose(np.sort(dm["P0_hx"]), np.sort(ds["P0_hx"]), atol=1e-4)


# ------------------------------------------------------------------ P5d: the w budget
def test_d_dt_and_since():
    """d/dt along each parcel over uneven parcel times; the change and the time integral
    since a parcel time (negative before it); a gap before it does not spoil after."""
    t = np.array([0.0, 10.0, 30.0, 60.0, 100.0])
    a = np.column_stack([2.0 * t + 1.0, np.full(t.size, 3.0)])
    np.testing.assert_allclose(P.d_dt(t, a)[:, 0], 2.0)
    assert np.isnan(P.d_dt(t[:1], a[:1])).all()
    np.testing.assert_allclose(P.since(t, a, 2, "delta")[:, 0], 2.0 * (t - 30.0))
    c = P.since(t, a, 2, "int")
    np.testing.assert_allclose(c[:, 1], 3.0 * (t - 30.0))  # (a constant: exact)
    np.testing.assert_allclose(c[:, 0], (t ** 2 + t) - (30.0 ** 2 + 30.0))  # (linear: too)
    g = a.copy()
    g[0, 1] = np.nan  # (missing before i0: only the times before the gap are NaN)
    cg = P.since(t, g, 2, "int")[:, 1]
    assert np.isnan(cg[0]) and np.isfinite(cg[1:]).all()
    np.testing.assert_allclose(cg[1:], 3.0 * (t[1:] - 30.0))
    g = a.copy()
    g[3, 1] = np.nan  # (missing after: from there on)
    cg = P.since(t, g, 2, "int")[:, 1]
    assert np.isfinite(cg[:3]).all() and np.isnan(cg[3:]).all()
    np.testing.assert_array_equal(P.since(t, a, 2, ""), a)


def test_w_budget_variables(pf, reg, tmp_path):
    """dwdt and wres are parcel variables wherever w, b and vpg are (choices, units,
    labels, trajectories, export); Dw/Dt = b + vpg + wres; integrated, Δw = ∫Dw/Dt."""
    run, F = reg.get()
    pf.attach(F)
    assert pf.has_budget() and pf.has("dwdt") and pf.has("wres")
    assert not ({"dwdt", "wres"} & set(pf.vars))
    assert pf.units("dwdt") == "m/s/s" and pf.title("wres") == "Dw/Dt − b − vpg (m/s/s)"
    assert P.var_choices(pf)["w budget (along the parcels)"] == {
        "Dw/Dt (m/s/s)": "dwdt", "Dw/Dt − b − vpg (m/s/s)": "wres"}
    ps = P.select(pf, dict(t=4800.0, z=[0.5, 2.0], cap=150), "mid")
    tr = pf.trajectories(ps, ("w", "b", "vpg", "dwdt", "wres"))
    np.testing.assert_allclose(tr["dwdt"], np.gradient(tr["w"].astype(np.float64),
                                                       pf.times, axis=0), rtol=1e-5,
                               atol=1e-7)
    np.testing.assert_allclose(tr["dwdt"], tr["b"] + tr["vpg"] + tr["wres"], atol=1e-5)
    i0 = P.ref_index(pf, ps.rule)
    assert pf.times[i0] == pytest.approx(4800.0) and P.ref_index(pf, None) == 0
    dw = P.since(pf.times, tr["w"], i0, "delta")
    idw = P.since(pf.times, tr["dwdt"], i0, "int")
    ok = np.isfinite(dw) & np.isfinite(idw)
    assert ok.sum() > 1000 and (dw[i0][ok[i0]] == 0).all()
    assert np.sqrt(np.mean((dw[ok] - idw[ok]) ** 2)) < 0.2 * np.sqrt(np.mean(dw[ok] ** 2))
    r = P.export_set(pf, ps, str(tmp_path / "mid.nc"), ["w", "dwdt", "wres"])
    with netCDF4.Dataset(r["path"]) as d:
        np.testing.assert_array_equal(d["dwdt"][:].filled(np.nan), tr["dwdt"])
        assert d["wres"].units == "m/s/s" and "rest of the w budget" in d["wres"].long_name
    with pytest.raises(KeyError):  # (not in the file: never read from it)
        pf.read("dwdt", ps.ids, 0)


def test_figure_w_budget(reg, pcache):
    """w_budget_entries: a card per term in one panel; rates are the parcels' means of
    Dw/Dt, b, vpg and the rest; integrated, Δw and the integrals are 0 at the set's
    time and the integrals add up to Δw's integral."""
    from cm1view.figures import draw as figdraw
    from cm1view.figures import spec as fg
    from cm1view.figures.render import FigureData
    s, run = _par_series_spec(reg)
    pf = P.for_run(run)
    src = dict(name="up", rule=dict(t=4800.0, z=[0.5, 2.0], cap=150))
    es = fg.w_budget_entries(pf, src, "rates", 0, 0)
    assert [e["var"] for e in es] == ["dwdt", "b", "vpg", "wres"]
    assert [e["label"] for e in es] == ["up: Dw/Dt", "up: b", "up: vpg", "up: Dw/Dt − b − vpg"]
    assert {e["panel"] for e in es} == {0} and not any(e["ens"] for e in es)
    d = FigureData().panel_data(fg.normalize(dict(s, series=es), run, ""))[0]
    assert d["nlines"] == 4
    tr = pf.trajectories(P.select(pf, src["rule"]), ("dwdt", "b"))
    have = np.flatnonzero(np.isfinite(tr["b"]).any(axis=1))
    sl = slice(have[0], have[-1] + 1)
    np.testing.assert_allclose(d["S1_v"], np.nanmean(tr["b"][sl], axis=1), rtol=1e-5)
    ei = fg.w_budget_entries(pf, src, "int", 0, 1)
    assert [(e["var"], e["op"]) for e in ei] == [("w", "delta"), ("b", "int"),
                                                  ("vpg", "int"), ("wres", "int")]
    assert ei[0]["label"] == "up: Δw" and ei[3]["label"] == "up: ∫ (Dw/Dt − b − vpg) dt"
    assert ei[1]["units"] == ei[0]["units"] == "m s$^{-1}$"  # (one axis)
    si = fg.normalize(dict(s, series=[dict(e, panel=0) for e in ei]), run, "")
    d = FigureData().panel_data(si)[0]
    for n in range(4):
        i = int(np.argmin(np.abs(d[f"S{n}_t"] * 60.0 - 4800.0)))
        assert d[f"S{n}_v"][i] == pytest.approx(0.0, abs=1e-6)
    figdraw.draw(si, {0: d})




def _spy_parts(monkeypatch, trajcalc):
    """Record the boxes the winds are read in and the parcels traced again (left a
    box) while trajcalc.trace runs."""
    boxes, redone = [], []
    real_w, real_adv = trajcalc._Winds, trajcalc._advance

    class Spy(real_w):
        def __init__(self, run, t, box=None):
            boxes.append(box)
            super().__init__(run, t, box)

    def adv(*a):
        r = real_adv(*a)
        redone.append(int(r[3].sum()))
        return r

    monkeypatch.setattr(trajcalc, "_Winds", Spy)
    monkeypatch.setattr(trajcalc, "_advance", adv)
    return boxes, redone


def test_traced_through_winds_read_in_parts(demo_run, monkeypatch):
    """Winds too large for the 3D cache: trajectories traced in boxes around bands of
    parcels (traced again in a wider box when their path leaves it) are the
    whole-volume ones to the bit, with the default margins and with none at all."""
    from cm1view.core import fields as fmod, models, trajcalc
    ref = models.open_run(demo_run, workers=1)
    run = models.open_run(demo_run, workers=1)
    monkeypatch.setattr(run, "fits", lambda nbytes: False)
    lat = dict(x0=float(ref.xh[4]), dx=4.0, nx=10, y0=float(ref.yh[4]), dy=4.0, ny=10,
               z0=0.25, dz=2.0, nz=5)
    want = trajcalc.trace(ref, lat)
    assert not trajcalc._in_parts(ref) and trajcalc._in_parts(run)
    boxes, redone = _spy_parts(monkeypatch, trajcalc)
    for tight in (False, True):
        if tight:  # (bands of 4 rows, boxes of the parcels' own extent)
            monkeypatch.setattr(fmod, "PART_BYTES", 1)
            monkeypatch.setattr(trajcalc, "MARGIN", 0.0)
            monkeypatch.setattr(trajcalc, "U_MIN", 0.0)
            monkeypatch.setattr(trajcalc, "W_MIN", 0.0)
        del boxes[:], redone[:]
        got = trajcalc.trace(run, lat)
        assert boxes and None not in boxes
        for k in trajcalc.VARS:
            np.testing.assert_array_equal(got[k], want[k])
        assert np.isfinite(got["x"][4]).any()  # (all have left the domain by output 8)
    assert sum(redone) > 0 and len({b[1] for b in boxes}) > 1
    assert any(b[0] < run.nk or b[2] - b[1] < run.nj for b in boxes)  # (parts, not all)
