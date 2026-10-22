"""Figure workspace: the editor's widgets <-> spec, panel times and titles, undo / redo,
and the publication options drawn without errors."""
import json

import numpy as np
import pytest

from conftest import txt, wait


@pytest.fixture
def ed(viewer):
    e = viewer.figed
    e.auto.value = False  # renders only when a test asks
    return e


def render(ed):
    """Draw the editor's figure as the preview does (raises on errors)."""
    from cm1view import figdraw
    spec = ed.collect()
    data = ed.panel_data(spec)
    return spec, data, figdraw.draw(spec, data)


def test_default_times_are_all_different(ed):
    s = ed.collect()
    assert len(set(s["times"])) == len(s["times"]) > 1


def test_round_trip_keeps_the_spec(ed):
    s = ed.collect()
    ed.set_spec(json.loads(json.dumps(s)))
    assert json.dumps(ed.collect(), sort_keys=True) == json.dumps(s, sort_keys=True)


def test_panel_time_pickers_follow_the_grid(ed):
    from cm1view.figui import NONE
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


def test_two_runs_make_a_grid(ed, demo_root):
    import os
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    assert len(ed.run_rows) == 2 and ed.vary.value == "grid"
    assert ed.rows.value == 2 and len(ed.tm_rows) == ed.cols.value
    assert ed.times_sec.title == "Times (one per column)"
    spec, data, fig = render(ed)
    assert {d.get("run_label") for d in data.values()} == {"supercell", "supercell_weak"}


def test_series_without_the_series_tool(ed):
    ed.from_series()  # no series computed yet: max updraft
    assert ed.kind.value == "th" and len(ed.ser_cards) == 1
    ed.panel_data(ed.collect())  # starts computing
    wait(lambda: not ed.series_pending(), 120, "the series")
    spec, data, fig = render(ed)
    assert not any(d.get("missing") for d in data.values())


def test_time_series_y_range(ed):
    ed.from_series()
    ed.kind.value = "line"
    assert ed.ts_ymin.visible and not ed.ts_zmin.visible
    ed.ts_ymin.value, ed.ts_ymax.value = 0.0, 50.0
    ed.panel_data(ed.collect())
    wait(lambda: not ed.series_pending(), 120, "the series")
    spec, data, fig = render(ed)
    assert fig.axes[0].get_ylim() == (0.0, 50.0)


@pytest.mark.parametrize("start", ["plan", "series", "soundings"])
def test_script_redraws_the_identical_image(ed, tmp_path, start):
    import os
    import subprocess
    import sys
    import matplotlib.image as mi
    if start == "series":
        ed.from_series()
        ed.panel_data(ed.collect())
        wait(lambda: not ed.series_pending(), 120, "the series")
    elif start == "soundings":
        ed.from_soundings()
    base = str(tmp_path / start)
    ed.path.value = base
    ed._save_job(ed.collect(), True, base)
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    os.rename(base + ".png", base + "_viewer.png")
    r = subprocess.run([sys.executable, "-I", base + ".py"], capture_output=True, text=True,
                       cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-500:]
    assert np.array_equal(mi.imread(base + ".png"), mi.imread(base + "_viewer.png"))
