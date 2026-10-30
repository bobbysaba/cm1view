"""Session files: what the viewer shows saved to JSON and put back."""

import json
import os

import pytest

from conftest import wait


def _set_up(v):
    """A viewer state away from the defaults in every part a session keeps."""
    v.tslider.value = 3
    v.fill_var.value = "winterp"
    v.fill_lvl.value = 2.5
    v.fill_diff["on"].value = True
    v.fill_diff["time"].value = "prev"
    v.fill_auto.value = False
    v.fill_min.value, v.fill_max.value = -7.0, 7.0
    v._add_fill()
    v.fills[0]["var"].value = "thpert"
    v._add_overlay()
    v.ovs[1]["levels"].value = "1, 2"
    o = v.vecs[0]
    o["on"].value = True
    o["q"].value = list(o["q"].options.values())[1]
    o["ref"].value = 12.5
    v.view = (10.0, 40.0, 5.0, 35.0)
    v.fixes = {2: dict(x=20.0, y=21.0, value=float("nan"), source="clicked"),
               3: dict(x=22.0, y=22.0, value=1.0, source="loaded")}
    v.mode.set("Cross-section")


def test_session_round_trip(viewer, reg, tmp_path):
    """Saved, then loaded into a fresh viewer: the same state, one redraw with the
    difference and the extra layers, the view kept for the browser's re-fit."""
    from cm1view.viewer import app as A
    v = viewer
    _set_up(v)
    s1 = v.session_state()
    assert s1["cm1view_session"] == 1 and s1["run"] == os.path.abspath(v.run.path)
    assert s1["track"]["fixes"][0][1]["value"] is None  # NaN as JSON null
    path = str(tmp_path / "s" / "session.json")
    v._save_session(path)
    assert "Saved" in v.ses_msg.object
    json.load(open(path))  # strict JSON

    run, F = reg.get()
    v2 = A.Viewer(run, F, reg=reg)
    v2.main()
    try:
        v2.ses_path.value = path
        v2._on_load_session(None)
        assert "Loaded" in v2.ses_msg.object and "not in this run" not in v2.ses_msg.object
        assert v2.session_state() == s1
        assert v2.t == 3 and v2.view == (10.0, 40.0, 5.0, 35.0)
        assert "fitted" in v2.fig.x_range.tags and v2.fig.tags  # the browser re-fits
        assert len(v2.fills) == 1 and len(v2.ovs) == 2
        assert v2.mode.value == "Cross-section"
        assert sorted(v2.fixes) == [2, 3] and v2.fixes[2]["value"] != v2.fixes[2]["value"]
        wait(lambda: "minus" in (v2.map_title.object or ""), msg="map with the difference")
    finally:
        v2.close()


def test_session_drops_extra_rows_and_skips_what_the_run_lacks(viewer):
    """Fewer rows than shown: the extra ones go; a field, time or tool the run cannot
    take is left as it was and named."""
    v = viewer
    v._add_overlay()
    v._add_fill()
    s = v.session_state()
    s["contours"] = s["contours"][:1]
    s["fills"] = []
    s["fill"]["var"] = "no_such_field"
    s["contours"][0]["level"] = 1e6  # clamped to the top
    s["tool"] = "Nonexistent tool"
    keep = v.fill_var.value
    skipped = v.apply_session(s)
    assert len(v.ovs) == 1 and v.fills == []
    assert v.fill_var.value == keep and any("no_such_field" in x for x in skipped)
    assert v.ovs[0]["level"].value == v.ovs[0]["level"].end
    assert v.mode.value is None


def test_session_of_another_run_reopens_the_page(viewer, demo_root, tmp_path):
    """Loading a session saved on another run sends the browser there (?session=)."""
    v = viewer
    s = v.session_state()
    s["run"] = os.path.join(demo_root, "demo", "supercell_weak")
    path = tmp_path / "weak.json"
    path.write_text(json.dumps(s))
    v.ses_path.value = str(path)
    v._on_load_session(None)
    assert v.ses_go.value == str(path)


def test_not_a_session_file(viewer, tmp_path):
    from cm1view.viewer import session
    p = tmp_path / "x.json"
    p.write_text('{"a": 1}')
    with pytest.raises(ValueError):
        session.read(str(p))
    viewer.ses_path.value = str(p)
    viewer._on_load_session(None)
    assert "Could not load" in viewer.ses_msg.object


PARTS = ("soundings", "section", "view3d", "series", "distributions")


def _fresh(reg):
    from cm1view.viewer import app as A
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    return v


def test_session_soundings_section_and_3d(viewer, reg):
    """Soundings (a point, a box, a pinned time), the section with a contour and
    limits, and the 3D setup come back; the soundings and section are drawn again,
    the 3D scene only when the session is on the 3D workspace."""
    v = viewer
    v._add_sounding(20.0, 25.0, False)
    v._add_sounding(30.0, 30.0, True, (2.0, 2.0))
    v._pin_time()
    v.parcel.value = "mu"
    v.ps["tmin"].value = -30.0
    v.snd_lim["prof_x"] = {0: (1.0, 2.0)}
    v.xs_pts = [(10.0, 10.0), (40.0, 35.0)]
    v._draw_xs()
    v.xs_fill.value = "thpert"
    v._xs_add_contour()
    v.xs_smin.value = 5.0
    v._set_box((5.0, 20.0, 5.0, 20.0))
    v._set_seed_box((8.0, 12.0, 8.0, 12.0))
    v.v3_exag.value = 3.0
    v.isos[0]["val"].value = 7.0
    v._add_sv()
    v.st_on.value = True
    s1 = v.session_state()
    assert s1["soundings"]["zoom"]["prof_x"] == {"0": [1.0, 2.0]}  # (JSON keys)
    s1 = json.loads(json.dumps(s1))  # (as from a file)

    v2 = _fresh(reg)
    try:
        assert v2.apply_session(s1) == []
        s2 = v2.session_state()
        for k in PARTS[:3]:
            assert s2[k] == s1[k], k
        assert v2.points[2][2] == v.t and len(v2.points[1][1]) == 4
        assert v2.snd_lim["prof_x"] == {0: (1.0, 2.0)}
        assert len(v2.xs_ovs) == len(v.xs_ovs) and v2.xs_smin.value == 5.0
        assert v2.box == v.box and v2.seed_box == v.seed_box
        assert [e[0] for e in v2._item_entries()].count("snd") == 3
        wait(lambda: v2.snd_tabs.visible or v2.skew_png.visible, msg="soundings drawn")
        wait(lambda: "A (10.0, 10.0)" in (v2.xs_status.object or ""), msg="section drawn")
        assert v2.gen["3d"] == 0  # (on the Map workspace: not rendered)
    finally:
        v2.close()


def test_session_series_and_distributions(viewer, reg):
    """Series come back from the cache without a recompute; distributions are
    computed again at their times, in their order, the chosen one chosen."""
    v = viewer
    v.ser_field.value = "winterp"
    v.ser_reduce.value = "max"
    v._on_ser_compute(None)
    wait(lambda: not v.ser_go.disabled, tmax=300, msg="series")
    v.ser_y0.value = 1.0
    v.dist_field.value = "winterp"
    v._dist_request()
    wait(lambda: len(v.dists) == 1, msg="distribution 1")
    v.tslider.value = 2
    v.dist_z.value = 2.0
    v._dist_request()
    wait(lambda: len(v.dists) == 2, msg="distribution 2")
    v.dist_kind.value = "ecdf"
    v.dist_pick.value = next(iter(v.dists))
    s1 = json.loads(json.dumps(v.session_state()))

    v2 = _fresh(reg)
    try:
        assert v2.apply_session(s1) == []
        (k, s), = v2.series.items()
        assert int(s["ds"]["computed"].sum()) == len(v2.run.times)  # from the cache
        assert not v2.ser_go.disabled and "1 series" in v2.ser_status.object
        assert v2.ser_y0.value == 1.0 and v2.ser_pick.value == k
        wait(lambda: "from the session" in (v2.dist_status.object or ""),
             msg="distributions computed again")
        assert list(v2.dists) == list(v.dists)
        assert v2.dist_pick.value == next(iter(v.dists)) and v2.dist_kind.value == "ecdf"
        assert [d["color"] for d in v2.dists.values()] == \
            [d["color"] for d in v.dists.values()]
        assert v2.session_state()["series"] == s1["series"]
    finally:
        v2.close()


def test_session_of_the_map_only_keeps_the_rest(viewer):
    """A session without soundings, section, 3D, series or distributions (saved by
    the first version) leaves them as they are."""
    v = viewer
    v._add_sounding(20.0, 25.0, False)
    v.xs_pts = [(10.0, 10.0), (40.0, 35.0)]
    v._draw_xs()
    s = {k: x for k, x in v.session_state().items() if k not in PARTS}
    before = {k: v.session_state()[k] for k in PARTS}
    assert v.apply_session(s) == []
    assert {k: v.session_state()[k] for k in PARTS} == before
