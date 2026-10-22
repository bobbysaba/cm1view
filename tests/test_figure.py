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


@pytest.fixture(scope="module")
def coarse_run(demo_root, tmp_path_factory):
    """The demo supercell with every other output (600 s apart, from 3600 s): a run
    whose output times differ from the viewer's."""
    import os
    main = os.path.join(demo_root, "demo", "supercell")
    d = tmp_path_factory.mktemp("coarse") / "supercell_coarse"
    d.mkdir()
    for f in ["namelist.input"] + [f"cm1out_{n:06d}.nc" for n in (2, 4, 6, 8, 10)]:
        os.symlink(os.path.join(main, f), d / f)
    return str(d)


def test_removing_a_run_keeps_soundings_and_series_on_their_runs(ed, demo_root, coarse_run):
    import os
    from cm1view import figure as fg
    for p in (os.path.join(demo_root, "demo", "supercell_weak"), coarse_run):
        ed.add_path.value = p
        ed._add_run()
    assert len(ed.run_rows) == 3
    ed.snd_cards = [ed._snd_card(dict(fg.sounding_defaults(k, 3600.0, n=k), label=f"r{k}"))
                    for k in range(3)]
    ed.ser_cards = [ed._ser_card(dict(fg.series_defaults(ed.F, ed._new_recipe()), runs=r))
                    for r in ([0], [1, 2], None)]
    ed._remove_run(ed.run_rows[0])  # runs B and C become 1 and 2 (indices 0, 1)
    assert [(c.w["label"].value, c.w["run"].value) for c in ed.snd_cards] == [("r1", 0),
                                                                             ("r2", 1)]
    assert [c.collect()["runs"] for c in ed.ser_cards] == [[0, 1], None]
    assert "1 sounding" in txt(ed.runs_msg.object)


def test_panel_times_come_from_the_panels_run(ed, coarse_run):
    ed.add_path.value = coarse_run
    ed._add_run()
    ed.vary.value = "time"
    ed.run_sel.value = 1
    crun = ed.open_run(coarse_run)[0]
    s = ed.collect()
    assert all(t in list(crun.times) for t in s["times_s"] if t is not None)
    ts = [t for t in s["times_s"] if t is not None]  # still different times (as far as
    assert len(set(ts)) == min(len(ts), len(crun.times))  # the run has outputs)
    spec, data, fig = render(ed)
    assert not any(d.get("missing") for d in data.values())
    ed.vary.value = "field"
    assert ed.time1.value in list(crun.times)
    ed.vary.value = "grid"  # every run's times, marked where a run has none
    assert any("not in every run" in o for o in ed.tm_rows[0].options)


def test_reopened_spec_keeps_times_of_another_run(ed, coarse_run):
    ed.add_path.value = coarse_run
    ed._add_run()
    ed.vary.value = "time"
    ed.run_sel.value = 1
    s = ed.collect()
    ed.set_spec(json.loads(json.dumps(s)))
    assert ed.collect()["times_s"] == s["times_s"]
    s["times_s"][0] = 3671.0  # no run has it: kept, and the panel says why
    ed.set_spec(json.loads(json.dumps(s)))
    assert ed.collect()["times_s"][0] == 3671.0
    spec, data, fig = render(ed)
    assert "no output" in data[0]["missing"]


def test_run_lists_offer_runs_to_add(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")  # next to the viewer's run
    assert weak in ed.run_sel.groups["Other runs (adds it)"].values()
    assert ed.run_sel.visible  # (one run in the figure, but others to pick)
    ed.run_sel.value = weak  # picking it adds it, with its track, and shows it
    assert len(ed.run_rows) == 2 and ed.run_sel.value == 1 and ed.vary.value == "time"
    assert ed.collect()["runs"][1]["track"].endswith("demo_supercell_weak.csv")
    assert weak not in ed._other_runs().values()
    spec, data, fig = render(ed)
    assert not any(d.get("missing") for d in data.values())


def test_run_picker_adds_a_run(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.add_pick.query.value_input = weak  # a pasted folder: picked, then added
    assert ed.add_pick.selected == weak
    ed.add_pick._open()
    assert [r["path"] for r in ed.run_rows][-1] == weak
    assert ed.add_pick.query.value == "" and weak not in ed.add_pick.list.options.values()


def test_field_lists_cover_every_run():
    from cm1view.fields import FieldDef
    from cm1view.figruns import AllFields

    class F:
        def __init__(self, *names):
            self.defs = {n: FieldDef(n, n.upper(), "", "Winds") for n in names}

        def __contains__(self, n):
            return n in self.defs

    a = AllFields([F("u", "w"), F("u", "zvort")])
    assert list(a.defs) == ["u", "w", "zvort"]
    labels = [k for g in a.groups().values() for k in g]
    assert "U [u]" in labels and "W [w] · not in every run" in labels


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


def test_animation_steps_every_panel(ed, tmp_path):
    from PIL import Image
    from cm1view import figure as fg
    ed.rows.value, ed.cols.value = 1, 2
    ts = ed.run.times  # (the pickers hold model times in s)
    ed.tm_rows[0].value, ed.tm_rows[1].value = float(ts[1]), float(ts[2])
    spec = ed.collect()
    ed.an_n.value, ed.an_step.value = 4, 2
    offsets = ed._anim_offsets(spec)
    ts = ed.run.times  # not evenly spaced: offsets follow the first panel's outputs
    assert offsets == [float(ts[i] - ts[1]) for i in (1, 3, 5, 7)]
    last = max(t for t in spec["times_s"] if t is not None)
    assert last + offsets[-1] <= ed.run.times[-1]
    s = fg.shift_times(spec, offsets[1])
    assert s["times_s"] == [t + offsets[1] for t in spec["times_s"]]
    base = str(tmp_path / "loop")
    ed._anim_job(ed._anim_gen, spec, offsets, base,
                 dict(fps=5.0, dpi=40, loop=True, frames=True))
    assert "Saved" in txt(ed.an_msg.object), ed.an_msg.object
    gif = Image.open(base + ".gif")
    assert gif.n_frames == len(offsets) and gif.info.get("loop") == 0
    assert len(list((tmp_path / "loop_frames").glob("loop_*.png"))) == len(offsets)


def test_animation_needs_plan_or_section(ed):
    ed.from_soundings()
    ed._on_anim()
    assert "plan views or cross-sections" in txt(ed.an_msg.object)


def test_stopped_animation_saves_nothing(ed, tmp_path):
    spec = ed.collect()
    base = str(tmp_path / "stopped")
    ed._anim_job(ed._anim_gen - 1, spec, [0.0, 300.0], base,
                 dict(fps=5.0, dpi=40, loop=True, frames=False))
    assert "Stopped" in txt(ed.an_msg.object)
    assert not (tmp_path / "stopped.gif").exists()


@pytest.mark.parametrize("layout", ["inset", "side", "skewt", "hodo"])
def test_sounding_layouts(ed, layout):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.quiver import Barbs
    ed.from_soundings()
    ed.sk["layout"].value = layout
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


def test_panels_at_heights(ed):
    from cm1view import figdraw
    ed.vary.value = "height"
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
    assert ed.vary.value == "time" and "height" not in ed.vary.options.values()


def test_own_code_runs_saves_and_reports_errors(ed, tmp_path):
    import subprocess
    import sys
    ed.rows.value, ed.cols.value = 1, 1
    ed.code.value = "axs[0].set_title('from code', loc='right')"
    ed.code_on.value = True
    spec, data, fig = render(ed)
    assert fig.axes[0].get_title(loc="right") == "from code"
    ed.code.value = "x = 1\n1 / 0"
    spec, data, fig = render(ed)
    assert fig._cv_code_error.startswith("line 2: ZeroDivisionError")
    ed.code.value = "fig.text(0.5, 0.5, 'CODE')"
    base = str(tmp_path / "code")
    ed.path.value = base
    ed._save_job(ed.collect(), True, base)
    r = subprocess.run([sys.executable, "-I", base + ".py"], capture_output=True, text=True)
    assert r.returncode == 0 and "stopped" not in r.stdout, r.stderr[-500:]
    ed.code_on.value = False
    ed.spec_path.value = base  # (finds the spec saved with it)
    ed._load_spec()  # code from a file waits until it is read
    assert ed.code.value == "fig.text(0.5, 0.5, 'CODE')" and not ed.code_on.value
    assert "code of its own" in txt(ed.msg.object)


def test_figure_of_parts(ed, tmp_path):
    import os
    import subprocess
    import sys
    import matplotlib.image as mi
    from cm1view import figdraw
    ed.rows.value, ed.cols.value = 1, 2
    ed._add_part()  # part 2: a copy, then soundings
    assert len(ed.parts) == 2 and ed.part_i == 1 and ed.part_sel.visible
    ed.from_soundings()
    ed.let_on.value = True
    spec = ed.collect_all()
    assert spec["kind"] == "combo" and [p["kind"] for p in spec["parts"]] == ["plan", "sounding"]
    assert spec["size"][0] == sum(p["size"][0] for p in spec["parts"])
    data = ed.panel_data(spec)
    assert set(data) == {0, 1, 1000}
    fig = figdraw.draw(spec, data)
    assert len(fig.subfigs) == 2
    ed.part_sel.value = 0  # editing part 1 again
    assert ed.kind.value == "plan" and ed.collect_all()["parts"][1]["kind"] == "sounding"
    base = str(tmp_path / "parts")
    ed.path.value = base
    ed._save_job(ed.collect_all(), True, base)
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    os.rename(base + ".png", base + "_viewer.png")
    r = subprocess.run([sys.executable, "-I", base + ".py"], capture_output=True, text=True,
                       cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-500:]
    assert np.array_equal(mi.imread(base + ".png"), mi.imread(base + "_viewer.png"))
    ed._remove_part()  # (part 1: the soundings stay)
    assert not ed.parts and ed.collect_all()["kind"] == "sounding"
    ed.spec_path.value = base
    ed._load_spec()  # the parts come back
    assert len(ed.parts) == 2, ed.msg.object
    assert ed.collect_all()["parts"][1]["kind"] == "sounding"


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
    assert s["xsec"]["mode"] == "fixed" and s["xsec"]["a"][0] < s["xsec"]["b"][0]
    assert any(lay["type"] == "line" for lay in s["layers"])
    ed.image.click = [0.999, 0.999, 9]  # outside the panels
    assert "inside a panel" in txt(ed.status.object)


def test_run_colours_and_line_styles(ed, demo_root):
    import os
    from matplotlib.colors import to_hex
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.from_series()
    ed.kind.value = "line"  # one series from two runs: coloured by run
    ed.run_rows[1]["color"].value = "#00aa00"
    ed.panel_data(ed.collect())
    wait(lambda: not ed.series_pending(), 120, "the series")
    spec, data, fig = render(ed)
    assert spec["runs"][1]["color"] == "#00aa00"
    assert "#00aa00" in {to_hex(ln.get_color()) for ln in fig.axes[0].get_lines()}


def test_undo_covers_figure_parts(ed):
    ed.auto.value = True
    ed.request(delay=False)
    ed._add_part()
    assert len(ed.parts) == 2
    ed.undo()  # the part added goes
    assert not ed.parts and ed.collect_all()["kind"] == "plan"
    ed.redo()
    assert len(ed.parts) == 2 and ed.part_i == 1
    ed.from_soundings()  # part 2: soundings
    ed.part_sel.value = 0
    ed._remove_part()  # (part 1 goes: the soundings are left)
    assert not ed.parts and ed.kind.value == "sounding"
    ed.undo()  # both parts are back, part 1 in the widgets
    assert [p["kind"] for p in ed.collect_all()["parts"]] == ["plan", "sounding"]
    assert ed.part_i == 0 and ed.kind.value == "plan"


def test_animation_of_figure_parts(ed, tmp_path):
    from PIL import Image
    from cm1view import figure as fg
    ed.rows.value, ed.cols.value = 1, 1
    ed._add_part()
    ed.from_soundings()  # part 2: a sounding at the same time
    spec = ed.collect_all()
    ed.an_n.value, ed.an_step.value = 3, 1
    offsets = ed._anim_offsets(spec)
    assert len(offsets) == 3
    s = fg.shift_times(spec, offsets[1])
    for k, key in ((0, "times_s"), (1, "soundings")):
        a, b = spec["parts"][k][key][0], s["parts"][k][key][0]
        a, b = (a, b) if k == 0 else (a["time_s"], b["time_s"])
        assert b == a + offsets[1]
    base = str(tmp_path / "parts")
    ed._anim_job(ed._anim_gen, spec, offsets, base,
                 dict(fps=4.0, dpi=30, loop=True, frames=False))
    assert "Saved" in txt(ed.an_msg.object), ed.an_msg.object
    assert Image.open(base + ".gif").n_frames == 3


def test_series_runs_list_offers_other_runs(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.from_series()
    ed.kind.value = "line"
    c = ed.ser_cards[0]
    assert weak in c.w["runs"].options.values()
    c.w["runs"].value = [0, weak]  # picking it adds it to the figure
    assert [r["path"] for r in ed.run_rows][-1] == weak
    assert c.w["runs"].value == [0, 1] and ed.collect()["series"][0]["runs"] == [0, 1]
    assert weak not in c.w["runs"].options.values()


def test_run_lists_without_other_runs_have_no_heading(ed):
    ed._find_runs = lambda: setattr(ed, "_cands", [])  # nothing else to offer
    ed._find_runs()
    ed._refresh_run_names()
    assert not ed.run_sel.groups and list(ed.run_sel.options.values()) == [0]
    ed.from_soundings()
    w = ed.snd_cards[0].w["run"]
    assert not w.groups and w.value == 0


def test_runs_root_scan_feeds_the_run_lists(ed, coarse_run, monkeypatch):
    import os
    from cm1view import config
    root, real = os.path.dirname(coarse_run), config.get
    monkeypatch.setattr(config, "get", lambda k: [root] if k == "runs_root" else real(k))
    assert coarse_run not in ed._other_runs().values()
    ed._scan_roots()  # in the background; no page: the next change of the runs shows it
    wait(lambda: ed._scan_new, 60, "the runs_root scan")
    ed._show_runs()
    assert coarse_run in ed._other_runs().values()
    assert coarse_run in ed.run_sel.groups["Other runs (adds it)"].values()
    assert coarse_run in ed.add_pick._known


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


def test_run_colours_are_the_default(ed, demo_root):
    import os
    from matplotlib.colors import to_hex
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()  # a run x time grid
    ed.run_rows[1]["color"].value = "#00aa00"
    ed._add_layer("track")  # a new track layer: each panel's run's colour
    spec, data, fig = render(ed)
    i = next(i for i, d in data.items() if d.get("run") == 1 and "track_x" in d)
    ax = fig._cv_axes[i]
    assert "#00aa00" in {to_hex(ln.get_color()) for ln in ax.get_lines()}
    names = {a.txt._text.get_text(): to_hex(a.txt._text.get_color())
             for a in ax.artists if hasattr(a, "txt")}
    assert names[spec["runs"][1]["label"]] == "#00aa00"  # the run's name too
    ed.from_soundings()  # soundings of two runs in one panel: the runs' colours
    ed._add_sounding()
    for c, k in zip(ed.snd_cards[:2], (0, 1)):
        c.w["run"].value, c.w["panel"].value, c.w["kind"].value = k, 1, "mean"
    spec, data, fig = render(ed)
    assert data[0]["nsnd"] == 2
    cols = {to_hex(ln.get_color()) for ln in fig._cv_axes[0].get_lines()}
    assert {"#00aa00", to_hex(spec["runs"][0]["color"])} <= cols
    ed.snd_cards[1].w["auto_color"].value = False  # a colour of its own
    ed.snd_cards[1].w["color"].value = "#123456"
    spec, data, fig = render(ed)
    assert "#123456" in {to_hex(ln.get_color()) for ln in fig._cv_axes[0].get_lines()}


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
    from cm1view import figdraw
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
    from cm1view import figdraw
    ed.vary.value = "height"
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


def test_code_editor_and_plain_box_hold_the_same_code(ed):
    ed.code.value = "x = 1"
    assert ed.code_plain.value == "x = 1"
    ed.code_box.value = True  # the plain box (no internet for the editor)
    assert ed.code_plain.visible and not ed.code.visible
    ed.code_plain.value = "y = 2"
    assert ed.collect()["code"]["text"] == "y = 2" and ed.code.value == "y = 2"
    ed.code_box.value = False  # (the choice is remembered: back to the editor)


def test_provenance_records_namelists_and_settings(ed, tmp_path):
    import hashlib
    import os
    base = str(tmp_path / "prov")
    ed.path.value = base
    ed._save_job(ed.collect(), True, base)
    with open(os.path.join(str(tmp_path), "_src", "prov_spec.json")) as f:
        made = json.load(f)["made_with"]
    with open(os.path.join(ed.run.path, "namelist.input"), "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()[:16]
    assert made["runs"][0]["namelist_sha256"] == h
    assert {"output_glob", "track_dirs", "track_patterns"} <= set(made["settings"])
    with open(base + ".py") as f:
        assert h in f.read(2000)


def test_figure_of_parts_with_a_series_part(ed, tmp_path):
    import os
    import subprocess
    import sys
    import matplotlib.image as mi
    from cm1view import figdraw
    ed.rows.value, ed.cols.value = 1, 1
    ed._add_part()
    ed.from_series()
    ed.kind.value = "line"  # part 2: time series
    spec = ed.collect_all()
    assert [p["kind"] for p in spec["parts"]] == ["plan", "line"]
    ed.panel_data(spec)  # (starts computing the series)
    wait(lambda: not ed.series_pending(), 180, "the series")
    data = ed.panel_data(spec)
    assert 1000 in data and not data[1000].get("missing"), data.get(1000)
    figdraw.draw(spec, data)
    base = str(tmp_path / "withseries")
    ed.path.value = base
    ed._save_job(spec, True, base)
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    os.rename(base + ".png", base + "_viewer.png")
    r = subprocess.run([sys.executable, "-I", base + ".py"], capture_output=True, text=True,
                       cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-500:]
    assert np.array_equal(mi.imread(base + ".png"), mi.imread(base + "_viewer.png"))

