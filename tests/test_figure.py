"""Figure workspace: the editor's widgets <-> spec, panel times and titles, undo / redo,
soundings, clicks on the preview, and the publication options drawn without errors."""
import json

import numpy as np
import pytest

from conftest import txt, wait, render


def test_default_times_are_all_different(ed):
    s = ed.collect()
    assert len(set(s["times"])) == len(s["times"]) > 1


def test_round_trip_keeps_the_spec(ed):
    s = ed.collect()
    ed.set_spec(json.loads(json.dumps(s)))
    assert json.dumps(ed.collect(), sort_keys=True) == json.dumps(s, sort_keys=True)


def test_panel_time_pickers_follow_the_grid(ed):
    from cm1view.figures.cards import NONE
    ed.rows.value, ed.cols.value = 1, 2
    assert len(ed.tm_rows) == 2 and len(ed.title_ws) == 2
    ed.cols.value = 3  # a new panel continues the times
    assert len(ed.tm_rows) == 3 and ed.tm_rows[2].value != NONE
    ed.tm_rows[1].value = NONE  # an empty cell in the middle
    s = ed.collect()
    assert s["times"][1] is None and s["times_s"][1] is None
    spec, data, fig = render(ed)
    assert 1 not in data and len(data) == 2
    ed.tm_rows[2].value = NONE  # trailing empties: fewer panels
    assert len(ed.collect()["times"]) == 1


def test_titles_per_panel(ed):
    ed.rows.value, ed.cols.value = 1, 2
    ed.title_ws[0].value = "Left"
    assert ed.collect()["titles"] == ["Left"]
    ed._auto_titles()
    assert all(ed.collect()["titles"])
    ed.clear_titles.clicks += 1
    assert ed.collect()["titles"] == []


def test_publication_options_draw(ed):
    ed.rows.value, ed.cols.value = 1, 2
    ed.font.value = "serif"
    ed.math.value = "custom"
    ed.fs_tick.value, ed.fs_label.value, ed.fs_title.value = 7, 9, 11
    ed.tickdir.value, ed.xstep.value, ed.ystep.value = "in", 5.0, 5.0
    ed.grid.value, ed.frame_lw.value, ed.minor.value = True, 1.2, True
    ed.let_box.value, ed.let_loc.value = True, "above left"
    ed.tl_box.value = True
    ed.cb_loc.value, ed.cb_lsize.value, ed.cb_tsize.value = "right", 9, 7
    ed.lg_ncol.value = 2
    ed.sp_w.value = 0.1
    fill = ed.cards[0]
    fill.w["alpha"].value, fill.w["scale"].value = 0.7, "log"
    fill.w["vmin"].value, fill.w["vmax"].value = 1.0, 60.0
    fill.w["cbar_label"].value = "reflectivity (dBZ)"
    cont = next(c for c in ed.cards if c.type == "contour")
    cont.w["clabel"].value, cont.w["clabel_fmt"].value = True, "%.0f"
    cont.w["legend"].value = "w"
    spec, data, fig = render(ed)
    ax = fig.axes[0]
    assert ax.xaxis.get_major_ticks()[0]._tickdir == "in"
    steps = np.diff(ax.get_xticks())
    assert np.allclose(steps, 5.0)
    cb = [a for a in fig.axes if a.get_label() == "<colorbar>"]
    assert cb and cb[0].get_ylabel() == "reflectivity (dBZ)"
    assert ax.get_title(loc="left") == "a"


def test_cross_section_hides_plan_settings(ed, viewer):
    from conftest import tap
    viewer.mode.set("Cross-section")
    tap(viewer, -10.0, 0.0)
    tap(viewer, 10.0, 0.0)
    ed.from_xsec()
    assert ed.kind.value == "xsec"
    fill = ed.cards[0]
    assert not fill.w["mode"].visible and not fill.w["z"].visible
    assert not ed.add_btns["track"].visible
    render(ed)


def test_sections_list_and_a_section_per_panel(ed):
    """Section panels pick one of the figure's sections (panel tree: Section); removing
    a section keeps the panels on theirs."""
    from cm1view.figures import spec as fg
    ed.kind.value = "xsec"
    ed.rows.value, ed.cols.value = 1, 2
    ed.sec_cards[0].w["pos"].value = "fixed"  # x–z at the domain's centre
    ed._add_section()  # its y–z twin
    assert [c.w["orient"].value for c in ed.sec_cards] == ["x", "y"]
    ed.sec_cards[1].w["y0"].value = 5.0
    ed._tree_edit(1)["section"] = 1
    spec, data, fig = render(ed)
    assert [s["orient"] for s in spec["sections"]] == ["x", "y"]
    x0, x1, y0, y1 = fg.domain_box(ed.run)
    assert np.allclose(data[0]["xlim"], (x0, x1), atol=0.3)  # (fixed: the model's x, y)
    assert np.allclose(data[1]["xlim"], (5.0, y1), atol=0.3)
    assert data[0]["xname"] == "x (km)" and data[1]["xname"] == "y (km)"
    ed.set_spec(json.loads(json.dumps(spec)))  # round trip
    assert json.dumps(ed.collect(), sort_keys=True) == json.dumps(spec, sort_keys=True)
    ed._remove_section(ed.sec_cards[0])
    assert ed.collect()["edits"]["1"]["section"] == 0 and len(ed.sec_cards) == 1
    assert not ed.sec_cards[0].rm.visible  # (the last one stays)


def test_a_grid_of_runs_by_sections(ed, demo_root):
    """Rows of runs and columns of sections (untracked runs: fixed sections); the
    lists set the rows and columns, a panel edit still picks its own section."""
    import os
    from cm1view.figures import draw as figdraw, spec as fg
    ed.kind.value = "xsec"
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.sec_cards[0].w["pos"].value = "fixed"  # x–z at the domain's centre
    ed._add_section()  # its y–z twin
    ed.gg_runs.value = [0, 1]
    ed.g_rows.value, ed.g_cols.value = "runs", "sections"
    assert (ed.rows.value, ed.cols.value) == (2, 2) and ed.rows.disabled and ed.cols.disabled
    assert ed.time1.visible and not ed.tm_box.visible and ed.gg_runs.visible
    spec, data, fig = render(ed)
    assert spec["grid"] == dict(rows="runs", cols="sections", runs=[0, 1])
    assert [fg.panel_ref(spec, i)[0] for i in range(4)] == [0, 0, 1, 1]
    assert [fg.panel_section(spec, i)[0] for i in range(4)] == [0, 1, 0, 1]
    x0, x1, y0, y1 = fg.domain_box(ed.run)
    assert np.allclose(data[0]["xlim"], (x0, x1), atol=0.3)  # (the viewer's run)
    assert np.allclose(data[1]["xlim"], (y0, y1), atol=0.3)
    # (labelled as the grid was made: sections over the columns, runs left of the rows)
    assert "x–z" in spec["titles"][0] and "y–z" in spec["titles"][1] and len(spec["titles"]) == 2
    assert spec["row_titles"] == [r["label"] for r in spec["runs"]]
    assert not spec["run_label"]["on"]
    assert [p.get("rowlabel") for p in figdraw.upgrade(spec)[0]["panels"]] == \
        [spec["runs"][0]["label"], None, spec["runs"][1]["label"], None]
    assert any(t.get_text() == spec["runs"][1]["label"] and t.get_rotation() == 90
               for ax in fig.axes for t in ax.texts)
    xl = [fig._cv_axes[i].get_xlabel() for i in (2, 3)]  # (outer: on the bottom row)
    assert xl == ["x (km)", "y (km)"]
    ed.set_spec(json.loads(json.dumps(ed.collect())))  # round trip
    assert (ed.g_rows.value, ed.g_cols.value, ed.cols.value) == ("runs", "sections", 2)
    ed._add_section()  # a column more
    assert ed.cols.value == 3
    ed._tree_edit(0)["section"] = 2  # (a panel's own section wins)
    assert fg.panel_section(ed.collect(), 0)[0] == 2
    ed.kind.value = "plan"  # plan views have no sections: a column per time
    assert ed.g_cols.value == "times" and "sections" not in ed.g_cols.options.values()
    assert not ed.cols.disabled


def test_old_cross_section_spec_converts(ed):
    """An older spec's one spec["xsec"] becomes the list of sections."""
    s = ed.collect()
    del s["sections"]
    s["xsec"] = dict(mode="fixed", a=[-5.0, 0.0], b=[5.0, 0.0], angle=0.0, half=10.0,
                     offset=[0.0, 0.0], ztop=5.0, dz=0.025, avg=1.0)
    ed.set_spec(s)
    c = ed.collect()
    assert c["xsec"] == dict(ztop=5.0, dz=0.025, coords="storm")
    assert len(c["sections"]) == 1
    sec = c["sections"][0]
    assert sec["orient"] == "ab" and sec["a"] == [-5.0, 0.0] and sec["avg"] == 1.0
    from cm1view.figures import spec as fg
    old = fg.from_xsec(dict(mode="storm", angle=30.0, half=10.0, offset=[1.0, 1.0]))
    assert old["orient"] == "angle" and old["angle"] == 60.0  # (clockwise from north)
    assert fg.from_xsec(dict(mode="storm", angle=90.0, half=8.0, offset=[2.0, 0.0])) \
        == fg.section_defaults(orient="y", half=8.0, off=2.0)


def test_section_x_axes_follow_how_each_section_runs(ed):
    """x–z through the storm: x from the storm's (or the model's x); angled: the
    distance along it; the x label follows each panel's section unless one is typed."""
    ed.kind.value = "xsec"
    assert ed.xlabel.value == ""
    ed.sec_cards[0].w["orient"].value = "x"
    ed.sec_cards[0].w["half"].value = 8.0
    ed._add_section()
    ed.sec_cards[1].w["orient"].value = "angle"
    ed.g_rows.value, ed.g_cols.value = "none", "sections"
    spec, data, fig = render(ed)
    if data[0].get("missing"):
        pytest.skip("no track position at the panel time")
    assert np.allclose(data[0]["xlim"], (-8.0, 8.0), atol=0.3)
    assert data[0]["xname"] == "x from storm (km)"
    assert data[1]["xname"] == "distance from storm (km)"
    assert [ax.get_xlabel() for ax in fig.axes[:2]] == ["x from storm (km)",
                                                       "distance from storm (km)"]
    ed.xs_coords.value = "grid"  # the model's x
    spec, data, fig = render(ed)
    assert data[0]["xname"] == "x (km)"
    assert np.isclose(data[0]["xlim"][1] - data[0]["xlim"][0], 16.0, atol=0.3)
    ed.xlabel.value = "along x (km)"  # (typed: every panel)
    spec, data, fig = render(ed)
    assert [ax.get_xlabel() for ax in fig.axes[:2]] == ["along x (km)"] * 2


def test_section_line_layer_draws_every_section(ed):
    """A Section line layer on a plan view: every section, labelled A–A′, B–B′; with
    "The panel's own" only the panel's.  Parts of a figure share the sections."""
    from cm1view.figures import draw as figdraw
    ed.sec_cards[0].w["pos"].value = "fixed"
    ed._add_section()
    ed._add_layer("line")
    spec, data, fig = render(ed)
    assert data[0]["lines"].shape == (2, 6)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert all(x in texts for x in ("A", "A′", "B", "B′"))
    assert figdraw.end_labels("X, X′", 2) == ("Z", "Z′")
    assert figdraw.end_labels("start, end", 1) == ("start 2", "end 2")
    next(c for c in ed.cards if c.type == "line").w["which"].value = "panel"
    spec, data, fig = render(ed)
    assert data[0]["lines"].shape == (1, 6)
    ed._add_part()  # part 2: sections
    ed.kind.value = "xsec"
    ed.sec_cards[1].w["orient"].value = "angle"
    whole = ed.collect_all()
    assert [s["orient"] for s in whole["parts"][0]["sections"]] == ["x", "angle"]
    ed.part_sel.value = 0
    assert [c.w["orient"].value for c in ed.sec_cards] == ["x", "angle"]


def test_motion_section_ends_turn_with_the_motion():
    """Along / across the storm motion: behind -> ahead and left -> right of the
    tracked motion, centred ahead / right of the storm; mwin: a mean motion."""
    from types import SimpleNamespace
    from cm1view.figures import spec as fg
    run = SimpleNamespace(umove=0.0, vmove=0.0, dx=1000.0, dy=1000.0,
                          xh=np.arange(100.0) + 0.5, yh=np.arange(100.0) + 0.5,
                          times=np.array([0.0, 300.0, 600.0, 900.0]))
    fixes = {t: dict(x=20.0 + 3.0 * t, y=50.0 + 3.0 * t * (t >= 2)) for t in range(4)}
    along = fg.section_defaults(orient="along", half=10.0, ahead=2.0, right=1.0)
    m = fg.section_motion(run, fixes, 0, along)
    assert np.allclose(m, (10.0, 0.0))  # (eastward: the first fixes)
    a, b = fg.section_ends(run, along, (20.0, 50.0), m)
    assert np.allclose(a, (12.0, 49.0)) and np.allclose(b, (32.0, 49.0))  # (right: south)
    across = dict(along, orient="across")
    a, b = fg.section_ends(run, across, (20.0, 50.0), m)
    assert np.allclose(a, (22.0, 59.0)) and np.allclose(b, (22.0, 39.0))  # (north -> south)
    assert fg.is_storm(across) and fg.uses_motion(across) and not fg.uses_motion(
        fg.section_defaults())
    assert fg.section_ends(run, along, None, m) is None  # (no track position)
    mean = fg.section_motion(run, fixes, 2, dict(along, mwin=10.0))  # (fixes 1–3)
    assert np.allclose(mean, np.mean([fg.section_motion(run, fixes, t, along)
                                      for t in (1, 2, 3)], axis=0))
    assert fg.section_motion(run, None, 0, along) == (0.0, 0.0)  # (no track: the domain's)
    assert fg.x_axis(along, "storm", (20.0, 50.0))[0] is None  # (the distance along)
    assert fg.describe(along) == "along the storm motion, +2 km ahead, +1 km right"


def test_motion_sections_in_the_editor(ed):
    """The card shows the motion options; + Section after an along one is across."""
    ed.kind.value = "xsec"
    c = ed.sec_cards[0]
    c.w["orient"].value = "along"
    assert c.w["ahead"].visible and c.w["mwin"].visible and c.w["half"].visible
    assert not c.w["pos"].visible and not c.w["off"].visible
    ed._add_section()
    assert ed.sec_cards[1].w["orient"].value == "across"
    ed.g_rows.value, ed.g_cols.value = "none", "sections"
    spec, data, fig = render(ed)
    assert [s["orient"] for s in spec["sections"]] == ["along", "across"]
    if data[0].get("missing"):
        pytest.skip("no track position at the panel time")
    assert data[0]["xname"] == data[1]["xname"] == "distance from storm (km)"
    assert np.allclose(data[0]["xlim"], (-10.0, 10.0), atol=0.3)


def test_soundings_render(ed):
    ed.from_soundings()
    assert ed.kind.value == "sounding"
    render(ed)


def test_undo_and_redo(ed):
    ed.auto.value = True
    ed.request(delay=False)
    first = ed.fsize.value
    ed.fsize.value = 14.0
    ed.request(delay=False)
    assert not ed.undo_btn.disabled
    ed.undo()
    assert ed.fsize.value == first and not ed.redo_btn.disabled
    ed.redo()
    assert ed.fsize.value == 14.0
    ed.from_soundings()  # a new figure can be undone too
    ed.undo()
    assert ed.kind.value == "plan"


def test_quick_start(ed, viewer):
    ed._started = False
    ed.auto.value = True  # (renders, so that Undo has the example)
    ed.request(delay=False)
    viewer.workspace.value = "Map"
    viewer.workspace.value = "Figure"  # the first time: the quick start
    assert ed.quick.open and ed._started
    ed.qs_kind.value = "xsec"
    assert "heights" not in ed.qs_vary.options.values() and ed.qs_rows.visible
    ed.qs_kind.value = "sounding"  # (rows and columns for every kind but time-height)
    assert ed.qs_rows.visible and not ed.qs_field.visible
    ed.qs_kind.value = "th"
    assert not ed.qs_rows.visible
    ed.qs_kind.value = "plan"
    f = next(v for g in ed.qs_field.groups.values() for v in g.values()
             if v != ed.cards[0].collect()["field"])
    ed.qs_vary.value, ed.qs_field.value = "fields", f
    ed.qs_rows.value, ed.qs_cols.value = 1, 2
    ed.qs_size.value = "6.5"
    ed.qs_go.clicks += 1
    s = ed.collect()
    assert not ed.quick.open
    assert (s["vary"], s["rows"], s["cols"], s["size"][0]) == ("field", 1, 2, 6.5)
    assert s["grid"]["cols"] == "fields" and s["grid"]["rows"] == "none"
    assert s["layers"][0]["field"] == f
    render(ed)
    ed.undo()  # the example again
    assert ed.collect()["vary"] == "time"
    viewer.workspace.value = "Map"
    viewer.workspace.value = "Figure"  # not again
    assert not ed.quick.open
    ed.new_btn.clicks += 1  # the new-figure button shows it again
    assert ed.quick.open
    ed.from_soundings()  # a figure from the viewer closes it
    assert not ed.quick.open


def test_saved_bundle_reopens(ed, tmp_path):
    ed.rows.value, ed.cols.value = 1, 1
    ed.let_box.value = True
    base = str(tmp_path / "fig")
    ed.path.value = base
    ed.tickdir.value, ed.grid.value, ed.pad.value = "in", True, 0.2
    ed._save_job(ed.collect(), True, base)
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    import os
    import subprocess
    import sys
    os.remove(base + ".png")  # the script redraws it, with the new options
    subprocess.run([sys.executable, base + ".py"], check=True, capture_output=True)
    assert os.path.getsize(base + ".png") > 1000
    ed.let_box.value = False
    ed.spec_path.value = base + ".png"  # the image's path finds the spec
    ed._load_spec()
    assert ed.let_box.value and "Loaded" in txt(ed.msg.object)


def test_saved_figures_listed(ed, tmp_path):
    import os
    own, ed._fig_dir = ed._fig_dir, str(tmp_path / "parent_run")
    try:
        ed.rows.value, ed.cols.value = 1, 1
        ed.let_box.value = True
        ed._save_job(ed.collect(), True, os.path.join(ed._fig_dir, "fig"))
        ed._refresh_saved()  # (the save schedules it)
        spec = os.path.join(ed._fig_dir, "_src", "fig_spec.json")
        assert ed.saved_pick.groups["This run (parent_run)"] == {"fig": spec}
        ed.saved_pick.value = spec  # the Export tab: picking fills in the path
        assert ed.spec_path.value == spec
        ed.open_quick()  # the quick start lists it too
        assert ed.qs_saved.value == "" and ed.qs_open.disabled
        ed.qs_saved.value = spec
        ed.let_box.value = False
        ed.qs_open.clicks += 1
        assert not ed.quick.open and ed.let_box.value
        assert "Loaded" in txt(ed.msg.object)
        ed.path.value = ""
        assert ed._load_spec(spec)  # Save as: where it was saved
        assert ed.path.value == os.path.join(ed._fig_dir, "fig")
    finally:
        ed._fig_dir = own


def test_series_without_the_series_tool(ed):
    ed.from_series()  # no series computed yet: max updraft
    assert ed.kind.value == "th" and len(ed.ser_cards) == 1
    ed.panel_data(ed.collect())  # starts computing
    wait(lambda: not ed.series_pending(), 120, "the series")
    spec, data, fig = render(ed)
    assert not any(d.get("missing") for d in data.values())


@pytest.mark.parametrize("kind", ["line", "th"])
def test_time_series_start_without_series(ed, kind):
    ed.kind.value = kind  # nothing computed until a series is added
    assert ed.ser_cards == []
    spec, data, fig = render(ed)
    assert not spec["series"] and not ed.series_pending()


def test_time_height_range_is_the_layer():
    import xarray as xr
    from types import SimpleNamespace
    from cm1view.figures import spec as fg
    z = np.arange(0.125, 10.0, 0.25)  # (level centres of a 0–10 km layer)
    ds = xr.Dataset(dict(computed=("t", np.ones(3, dtype=int)), value=("t", np.zeros(3)),
                         profile=(("t", "z"), np.ones((3, z.size))), z=("z", z)))
    run = SimpleNamespace(times=[0.0, 60.0, 120.0])
    ent = dict(recipe=dict(z0=0.0, z1=10.0), op="")
    d = fg.th_panel(run, ds, ent, dict(ts=dict(zmin=None, zmax=None)))
    assert d["ylim"] == (0.0, 10.0)  # (not 0.125–9.875: the 10 km tick shows)
    d = fg.th_panel(run, ds, ent, dict(ts=dict(zmin=2.0, zmax=8.0)))
    assert d["ylim"] == (2.0, 8.0)


def test_each_colorbar_has_its_own_label(ed):
    ed.rows.value, ed.cols.value = 1, 2
    ed.g_rows.value, ed.g_cols.value = "none", "fields"
    ed.cb_mode.value = "each"
    ed.pf_rows[0]["cbar_label"].value = "first bar"
    ed.pf_rows[0]["cbar_ticks"].value = "0, 10"
    ed.cb_label.value = "every other bar"  # (the Style tab's: bars without their own)
    spec, data, fig = render(ed)
    bars = [a for a in fig.axes[2:]]
    labels = [a.get_xlabel() or a.get_ylabel() for a in bars]
    assert sorted(labels) == ["every other bar", "first bar"]
    first = bars[labels.index("first bar")]
    ticks = first.get_xticks() if first.get_xlabel() else first.get_yticks()
    assert list(ticks) == [0.0, 10.0]


def test_field_panels_own_their_fill(ed):
    from cm1view.figures import draw as figdraw
    ed.rows.value, ed.cols.value = 1, 2
    fills = sum(c.type == "fill" for c in ed.cards)
    ed.g_rows.value, ed.g_cols.value = "none", "fields"  # (Time and fields sets the fill: not a Layers card)
    assert sum(c.type == "fill" for c in ed.cards) == fills - 1
    ed.pf_rows[1]["extend"].value = "max"
    ed.pf_rows[1]["z"].value = 3.0
    s = ed.collect()
    assert s["layers"][0]["type"] == "fill"
    lay = figdraw.spec_layers(s, 1)[0]
    assert lay["z"] == 3.0 and lay["extend"] == "max"
    spec, data, fig = render(ed)
    ed.set_spec(json.loads(json.dumps(s)))  # (opened again: still no card)
    assert sum(c.type == "fill" for c in ed.cards) == fills - 1
    assert ed.collect()["layers"][0] == s["layers"][0]
    ed.g_rows.value, ed.g_cols.value = "none", "times"  # back: a fill card again, as panel a had it
    assert ed.cards[0].type == "fill" and ed.cards[0].collect()["z"] == 1.0


def test_number_boxes_round_float_tails():
    from cm1view.viewer.numinput import FloatInput, tidy
    w = FloatInput(name="x", value=float(np.float32(0.01)), step=0.001)
    assert w.value == 0.01
    w._process_events({"value": 0.008 + 0.001})  # (the arrows' step, in the browser)
    assert w.value == 0.009 and w.get_root().value == 0.009
    w.value = float(np.float32(0.3))
    assert w.value == 0.3
    assert tidy(None) is None and tidy(123456.5) == 123456.5


def test_time_series_y_range(ed):
    ed.from_series()
    ed.kind.value = "line"
    assert ed.ts_ymin.visible and not ed.ts_zmin.visible
    ed.ts_ymin.value, ed.ts_ymax.value = 0.0, 50.0
    ed.panel_data(ed.collect())
    wait(lambda: not ed.series_pending(), 120, "the series")
    spec, data, fig = render(ed)
    assert fig.axes[0].get_ylim() == (0.0, 50.0)


def test_time_series_marks_extremes(ed):
    from cm1view.figures import draw as figdraw
    ed.from_series()
    ed.kind.value = "line"
    assert ed.ts_mark.visible and not ed.ext_sec.visible
    ed.ts_mark.value, ed.ts_mark_legend.value = "max", True
    ed.panel_data(ed.collect())
    wait(lambda: not ed.series_pending(), 120, "the series")
    spec, data, fig = render(ed)
    ax, d = fig.axes[0], data[0]
    (w, t, v), = figdraw.series_extremes(d["S0_t"], d["S0_v"], "max")
    assert v == np.nanmax(d["S0_v"])
    assert f"{v:.3g}" in [a.get_text() for a in ax.texts]
    assert "max" in ax.get_legend().texts[0].get_text()  # (one line: still a legend)


def test_map_panels_show_the_maximum(ed):
    from matplotlib.offsetbox import AnchoredText
    from cm1view.figures import draw as figdraw
    ed.set_parts(ed._default())  # (a plan view of reflectivity and updraft contours)
    ed.rows.value, ed.cols.value = 1, 1
    assert ed.kind.value == "plan" and ed.ext_sec.visible
    cont = next(j for j, c in enumerate(ed.cards) if c.type == "contour")
    assert cont in ed.ex_layer.options.values()
    ed.ex_on.value, ed.ex_layer.value, ed.ex_what.value = True, cont, "max"
    spec, data, fig = render(ed)
    (vmax, x, y), _ = figdraw.panel_extremes(data[0], cont)
    texts = [a.txt.get_text() for a in fig.axes[0].artists if isinstance(a, AnchoredText)]
    assert f"max {vmax:.3g}" in texts
    x0, x1 = sorted(data[0].get("xlim", (x, x)))
    assert x0 <= x <= x1


@pytest.mark.parametrize("layout", ["inset", "side", "skewt", "hodo"])
def test_sounding_layouts(ed, layout):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.quiver import Barbs
    ed.from_soundings()
    ed.sk["layout"].value = layout
    assert ed.skewt_sec.visible == (layout != "hodo")  # (each section when it is drawn)
    assert ed.hodo_sec.visible == (layout != "skewt")
    assert ed.sk["srh"].visible == (layout in ("side", "hodo"))
    ed.sk["srh"].value = "1"
    spec, data, fig = render(ed)
    assert "N0_rm" in data[0] and "N0_srh1" in data[0]
    hodos = [a for a in fig.axes + [c for a in fig.axes for c in a.child_axes]
             if getattr(a, "_cv_hodo", False)]
    assert len(hodos) == (0 if layout == "skewt" else 1)
    if layout == "inset":  # the barbs stay clear of the inset
        FigureCanvasAgg(fig).draw()
        ax = next(a for a in fig.axes if not getattr(a, "_cv_hodo", False))
        b = next(c for c in ax.collections if isinstance(c, Barbs))
        bx = ax.transData.transform(b.get_offsets()[:1])[0, 0]
        assert hodos[0].get_window_extent().x1 < bx


def test_sounding_table_lists_every_parameter(ed):
    from cm1view.figures import draw as figdraw
    ed.from_soundings()
    keys = [k for k, _, _ in figdraw.SND_PARAMS]
    assert sorted(ed.sk["table"].options.values()) == sorted(keys)
    ed.sk["table"].value = ["sbcape", "sbcin", "mucin", "shear01"]
    spec, data, fig = render(ed)
    par = data[0]["N0_par"]
    assert par.size == len(keys)
    assert np.isfinite(par[keys.index("sbcin")]) and par[keys.index("sbcin")] <= 0.0
    table = next(t for a in fig.axes for t in a.tables)
    heads = [c.get_text().get_text() for (r, _), c in table.get_celld().items() if r == 0]
    assert any(h.startswith("SBCIN") for h in heads)
    data[0]["N0_par"] = par[:11]  # (figure data saved before the newer parameters)
    table = next(t for a in figdraw.draw(spec, data).axes for t in a.tables)
    row = {c: cell.get_text().get_text() for (r, c), cell in table.get_celld().items()
           if r == 1}
    assert row[0] != "–" and row[1] == "–"


def test_hodograph_marks_each_storm_motion_on_its_own(ed):
    ed.from_soundings()
    ed.sk["layout"].value = "side"
    ed.sk["hodo_lm"].value = ed.sk["hodo_mean"].value = False
    spec, data, fig = render(ed)
    hodo = next(a for a in fig.axes if getattr(a, "_cv_hodo", False))
    texts = {t.get_text() for t in hodo.texts}
    assert "RM" in texts and "LM" not in texts
    s = json.loads(json.dumps(spec))  # (a figure saved with one storm-motions box)
    for k in ("hodo_rm", "hodo_lm", "hodo_mean"):
        del s["skewt"][k]
    s["skewt"]["hodo_kin"] = False
    ed.set_spec(s)
    assert not any(ed.sk[k].value for k in ("hodo_rm", "hodo_lm", "hodo_mean"))


def test_panels_at_heights(ed):
    from cm1view.figures import draw as figdraw
    ed.g_rows.value, ed.g_cols.value = "none", "heights"
    ed.pz.value = "1, 3, 6"
    assert (ed.rows.value, ed.cols.value) == (1, 3) and ed.pz.visible
    ed.time1.value = ed._shown_s()  # (the storm's first time)
    cont = next(c for c in ed.cards if c.type == "contour")
    cont.w["z_fixed"].value, cont.w["z"].value = True, 2.0  # one layer keeps its height
    spec, data, fig = render(ed)
    j = ed.cards.index(cont)
    assert [figdraw.spec_layers(spec, i)[0]["z"] for i in range(3)] == [1.0, 3.0, 6.0]
    assert {figdraw.spec_layers(spec, i)[j]["z"] for i in range(3)} == {2.0}
    assert not np.array_equal(data[0]["L0"], data[2]["L0"], equal_nan=True)
    ed._auto_titles()
    assert ed.collect()["titles"] == ["1 km", "3 km", "6 km"]
    s = ed.collect()
    ed.set_spec(json.loads(json.dumps(s)))
    assert ed.collect()["panel_z"] == [1.0, 3.0, 6.0]
    ed.kind.value = "xsec"  # sections have no heights to vary
    assert ed.g_cols.value == "times" and "heights" not in ed.g_cols.options.values()


def test_clicks_on_the_preview_place_things(ed):
    ed.rows.value, ed.cols.value = 1, 2
    ed.dom.value = "full"
    ed._job(ed.v.gen["fig"], ed.collect())  # a preview, as drawn in the background
    assert set(ed._place) == {0, 1}
    left, right, top, bottom, xl, yl, skew = ed._place[1]
    assert skew is None
    ed.place_mode.value = "marker"
    ed.image.click = [left + 0.5 * (right - left), top + 0.25 * (bottom - top), 1]
    a = ed.ann_rows[-1].collect()
    assert a["kind"] == "marker" and a["panel"] == 1
    assert abs(a["x"] - 0.5 * sum(xl)) < 0.02 * (xl[1] - xl[0])
    assert abs(a["y"] - (yl[0] + 0.75 * (yl[1] - yl[0]))) < 0.02 * (yl[1] - yl[0])
    ed.place_mode.value = "section"  # two clicks: the section's A and B
    for n, f in enumerate((0.2, 0.8)):
        ed.image.click = [left + f * (right - left), top + 0.5 * (bottom - top), 2 + n]
    s = ed.collect()
    sec = s["sections"][0]  # (the only section becomes the A–B one)
    assert len(s["sections"]) == 1 and sec["orient"] == "ab" and sec["a"][0] < sec["b"][0]
    assert not any(lay["type"] == "line" for lay in s["layers"])  # (no layer added)
    ed.image.click = [0.999, 0.999, 9]  # outside the panels
    assert "inside a panel" in txt(ed.status.object)


def test_sounding_storm_motion_ring_and_inset(ed):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    ed.from_soundings()
    ed.sk["srh"].value = "1"
    spec, data, fig = render(ed)
    d = data[0]
    assert np.allclose(d["N0_storm"], d["N0_rm"])
    srh_rm = d["N0_srh1"]
    ed.sk["storm"].value = "lm"  # the SRH follows the storm motion
    spec, data, fig = render(ed)
    assert np.allclose(data[0]["N0_storm"], data[0]["N0_lm"])
    assert data[0]["N0_srh1"] != srh_rm
    assert not ed.sk["storm_u"].visible
    ed.sk["storm"].value = "custom"
    assert ed.sk["storm_u"].visible
    ed.sk["storm_u"].value, ed.sk["storm_v"].value = 5.0, -3.0
    spec, data, fig = render(ed)
    assert np.allclose(data[0]["N0_storm"], [5.0, -3.0])
    skew = next(a for a in fig.axes if a.child_axes)
    hodo = next(c for c in skew.child_axes if getattr(c, "_cv_hodo", False))
    assert any(ln.get_marker() == "o" and np.allclose(ln.get_xydata()[0], [5.0, -3.0])
               for ln in hodo.get_lines())  # the ring
    for where, left in (("upper left", True), ("upper right", False)):
        ed.sk["inset_loc"].value = where
        spec, data, fig = render(ed)
        FigureCanvasAgg(fig).draw()
        skew = next(a for a in fig.axes if a.child_axes)
        hx = skew.child_axes[0].get_window_extent()
        mid = 0.5 * (skew.get_window_extent().x0 + skew.get_window_extent().x1)
        assert (hx.x1 < mid) == left
    assert not ed.sk["inset_x"].visible
    ed.sk["inset_loc"].value = "custom"
    assert ed.sk["inset_x"].visible and ed.sk["inset_y"].visible
    ed.sk["inset_x"].value, ed.sk["inset_y"].value, ed.sk["inset_size"].value = 0.0, 0.0, 0.5
    spec, data, fig = render(ed)
    FigureCanvasAgg(fig).draw()
    skew = next(a for a in fig.axes if a.child_axes)
    sx, hx = skew.get_window_extent(), skew.child_axes[0].get_window_extent()
    assert np.isclose(hx.x0, sx.x0, atol=1) and np.isclose(hx.y0, sx.y0, atol=1)
    assert np.isclose(hx.width, 0.5 * sx.width, rtol=0.02) or \
        np.isclose(hx.height, 0.5 * 0.39 / 0.37 * sx.height, rtol=0.02)  # (equal aspect)
    # the view: square, about the origin, a custom centre, or fit to the traces
    hodo = next(c for c in skew.child_axes if getattr(c, "_cv_hodo", False))
    assert np.allclose(hodo.get_xlim(), (-40, 40)) and np.allclose(hodo.get_ylim(), (-40, 40))
    assert not ed.sk["hodo_cu"].visible
    ed.sk["hodo_center"].value = "custom"
    assert ed.sk["hodo_cu"].visible and ed.sk["hodo_max"].visible
    ed.sk["hodo_cu"].value, ed.sk["hodo_cv"].value, ed.sk["hodo_max"].value = 10.0, 5.0, 20.0
    spec, data, fig = render(ed)
    hodo = next(c for c in next(a for a in fig.axes if a.child_axes).child_axes
                if getattr(c, "_cv_hodo", False))
    assert np.allclose(hodo.get_xlim(), (-10, 30)) and np.allclose(hodo.get_ylim(), (-15, 25))
    ed.sk["hodo_center"].value = "fit"
    assert not ed.sk["hodo_max"].visible
    spec, data, fig = render(ed)
    hodo = next(c for c in next(a for a in fig.axes if a.child_axes).child_axes
                if getattr(c, "_cv_hodo", False))
    (x0, x1), (y0, y1) = hodo.get_xlim(), hodo.get_ylim()
    assert np.isclose(x1 - x0, y1 - y0)  # (square)
    z, u, v = (np.asarray(data[0][f"N0_{k}"], float) for k in ("z", "u", "v"))
    sel = z <= 9.0
    assert x0 <= u[sel].min() and u[sel].max() <= x1
    assert y0 <= v[sel].min() and v[sel].max() <= y1


def test_drag_moves_annotations_and_sets_the_area(ed):
    ed.rows.value, ed.cols.value = 1, 1
    ed.dom.value = "full"
    ed._job(ed.v.gen["fig"], ed.collect())
    left, right, top, bottom, xl, yl, _ = ed._place[0]

    def at(u, w):  # image fractions of panel fractions (from the left and bottom)
        return [left + u * (right - left), bottom - w * (bottom - top)]

    ed.place_mode.value = "marker"
    ed.image.click = at(0.5, 0.5) + [1]
    m0 = ed.ann_rows[-1].collect()
    ed.place_mode.value = "move"  # the marker, dragged up and right
    ed.image.drag = at(0.5, 0.5) + at(0.75, 0.75) + [2]
    m1 = ed.ann_rows[-1].collect()
    assert m1["x"] - m0["x"] > 0.2 * (xl[1] - xl[0]) and m1["y"] - m0["y"] > 0.2 * (yl[1] - yl[0])
    ed.place_mode.value = "line"  # a drag: both ends of a line
    ed.image.drag = at(0.2, 0.2) + at(0.4, 0.2) + [3]
    ln = ed.ann_rows[-1].collect()
    assert ln["kind"] == "line" and ln["x"] < ln["x2"]
    ed.place_mode.value = "move"  # its end only
    ed.image.drag = at(0.4, 0.2) + at(0.4, 0.4) + [4]
    ln2 = ed.ann_rows[-1].collect()
    assert (ln2["x"], ln2["y"]) == (ln["x"], ln["y"]) and ln2["y2"] > ln["y2"]
    ed.image.drag = at(0.95, 0.05) + at(0.9, 0.1) + [5]  # nothing there
    assert "No annotation there" in txt(ed.status.object)
    ed.place_mode.value = "area"
    ed.image.drag = at(0.25, 0.25) + at(0.75, 0.75) + [6]
    s = ed.collect()
    x0, x1, y0, y1 = s["domain"]["box"]
    assert s["domain"]["mode"] == "box" and x1 > x0 and y1 > y0
    assert abs(x0 - (xl[0] + 0.25 * (xl[1] - xl[0]))) < 0.02 * (xl[1] - xl[0])


def test_clicks_in_a_skewt_are_temperature_and_pressure(ed):
    import math
    ed.from_soundings()
    ed._job(ed.v.gen["fig"], ed.collect())
    left, right, top, bottom, xl, yl, skew = ed._place[0]
    assert skew is not None
    ed.place_mode.value = "text"
    ed.image.click = [0.5 * (left + right), 0.5 * (top + bottom), 1]
    a = ed.ann_rows[-1].collect()
    p = math.sqrt(yl[0] * yl[1])  # (log-pressure axis: the middle)
    assert abs(a["y"] - p) < 0.02 * p
    assert abs(a["x"] - (0.5 * sum(xl) - skew[0] * math.log(skew[1] / a["y"]))) < 0.5
    spec, data, fig = render(ed)  # drawn where it was clicked
    t = next(x for x in fig._cv_axes[0].texts if x.get_text() == "A")
    X, y = t.get_position()
    assert abs(X - 0.5 * sum(xl)) < 0.5 and abs(y - a["y"]) < 0.02 * p


def test_parts_size_share_and_one_colorbar(ed):
    from cm1view.figures import draw as figdraw
    ed.rows.value, ed.cols.value = 1, 1
    ed._add_part()
    ed.part_w.value, ed.part_h.value = 9.0, 4.0
    ed.part_share.value = 0.3
    ed.part_cb.value = True
    spec = ed.collect_all()
    assert spec["size"] == [9.0, 4.0] and spec["parts"][1]["share"] == 0.3
    assert figdraw.part_shares(spec) == pytest.approx([0.7, 0.3])
    fig = figdraw.draw(spec, ed.panel_data(spec))
    assert len([a for a in fig.axes if a not in fig._cv_axes.values()]) == 1  # one colorbar
    ed.set_parts(json.loads(json.dumps(spec)), 1)  # as reopened
    again = ed.collect_all()
    assert again["size_set"] == [9.0, 4.0] and again["colorbar"]["mode"] == "figure"
    assert ed.part_i == 1 and ed.part_share.value == 0.3


def test_panels_at_model_levels_with_height_labels(ed):
    from cm1view.figures import draw as figdraw
    ed.g_rows.value, ed.g_cols.value = "none", "heights"
    ed.pz.value = "1, 3"
    ed.time1.value = ed._shown_s()
    ed.pz_mode.value = "level"  # the heights become the nearest levels
    ks = [int(v) for v in ed.collect()["panel_z"]]
    z = np.asarray(ed.run.z)
    assert ks == [int(np.argmin(abs(z - 1.0))), int(np.argmin(abs(z - 3.0)))]
    assert ed.pz.name.startswith("Model levels")
    ed.zl_on.value = True
    spec, data, fig = render(ed)
    lay = figdraw.spec_layers(spec, 1)[0]
    assert lay["mode"] == "level" and lay["z"] == ks[1]
    assert not np.array_equal(data[0]["L0"], data[1]["L0"], equal_nan=True)
    texts = [a.txt._text.get_text() for a in fig._cv_axes[1].artists if hasattr(a, "txt")]
    assert f"k = {ks[1]}" in texts
    ed._auto_titles()
    assert ed.collect()["titles"] == [f"k = {k}" for k in ks]
    ed.pz_mode.value = "height"  # and back
    assert ed.collect()["panel_z"] == [round(float(z[k]), 2) for k in ks]
