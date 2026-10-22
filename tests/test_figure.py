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
    from cm1view.figures import draw as figdraw
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
    from cm1view.figures.editor import NONE
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
    from cm1view.figures import spec as fg
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
    from cm1view.core.fields import FieldDef
    from cm1view.figures.runs import AllFields

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


@pytest.mark.parametrize("start", ["plan", "series", "soundings", "dists", "difference",
                                   "swath", "dark"])
def test_script_redraws_the_identical_image(ed, tmp_path, start):
    import os
    import subprocess
    import sys
    import matplotlib.image as mi
    if start == "difference":
        _difference(ed)
    elif start == "swath":
        _swath(ed)
    elif start == "dark":  # (a matplotlib style in the spec)
        ed.preset.value = "dark"
        ed._apply_preset()
    elif start == "series":
        ed.from_series()
        ed.panel_data(ed.collect())
        wait(lambda: not ed.series_pending(), 120, "the series")
    elif start == "soundings":
        ed.from_soundings()
    elif start == "dists":
        ed.from_dists()
        ed.ds["plot"].value = "violin"
    base = str(tmp_path / start)
    ed.path.value = base
    ed._save_job(ed.collect(), True, base)
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    os.rename(base + ".png", base + "_viewer.png")
    r = subprocess.run([sys.executable, "-I", base + ".py"], capture_output=True, text=True,
                       cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-500:]
    assert np.array_equal(mi.imread(base + ".png"), mi.imread(base + "_viewer.png"))


def test_drawing_code_stitches_into_one_module():
    """Exported scripts carry draw's modules as one: no imports between them, and
    every name the package has (bar source and MODULES) defined there."""
    from cm1view.figures import draw as figdraw
    src = figdraw.source()
    assert "from ." not in src and '"""Shared pieces' not in src
    ns = {}
    exec(compile(src, "script", "exec"), ns)
    names = {k for m in figdraw.MODULES for k in vars(m) if not k.startswith("__")}
    assert names - set(ns) == set()


def test_animation_steps_every_panel(ed, tmp_path):
    from PIL import Image
    from cm1view.figures import spec as fg
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
    from cm1view.figures import draw as figdraw
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
    from cm1view.figures import draw as figdraw
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
    from cm1view.figures import spec as fg
    ed.rows.value, ed.cols.value = 1, 1
    ed._add_part()
    ed.from_soundings()  # part 2: a sounding at the plan view's time (the outputs are
    # not evenly spaced: panels at other times may lack an output a step later)
    ed.snd_cards[0].w["time"].value = ed.parts[0]["times_s"][0]
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
    from cm1view import config, registry
    root, real = os.path.dirname(coarse_run), config.get
    monkeypatch.setattr(config, "get", lambda k: [root] if k == "runs_root" else real(k))
    # only the scan can find it (earlier tests made it a recent run)
    monkeypatch.setattr(registry, "recent_runs", lambda *a, **k: [])
    monkeypatch.setattr(registry, "sibling_runs", lambda *a, **k: [])
    ed._scanned = []
    ed._find_runs()
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
    from cm1view.figures import draw as figdraw
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



# ------------------------------------------------------------------ spec version 2
def _setup(ed, how):
    if how == "height":
        ed.vary.value = "height"
        ed.pz.value = "1, 3, 6"
    elif how == "xsec":
        ed.kind.value = "xsec"
    elif how == "sounding":
        ed.from_soundings()
    elif how == "parts":
        ed.rows.value, ed.cols.value = 1, 2
        ed._add_part()
        ed.from_soundings()


@pytest.mark.parametrize("how", ["time", "height", "xsec", "sounding", "parts"])
def test_version_1_specs_upgrade_and_draw(ed, how):
    """Version-1 specs (and figures of parts) upgrade to version 2 and draw every panel."""
    from cm1view.figures import draw as figdraw
    _setup(ed, how)
    ed.let_on.value = True
    spec = ed.collect_all()
    data = ed.panel_data(spec)
    v2, d2 = figdraw.upgrade(spec, data)
    assert v2["version"] == 2 and {p["id"] for p in v2["panels"]} >= set(data)
    fig = figdraw.draw(spec, data)
    assert set(fig._cv_axes) == set(data)


def test_upgrade_writes_out_each_panel():
    from cm1view.figures import draw as figdraw
    lay = dict(type="fill", on=True, field="dbz", mode="height", z=1.0, cmap="viridis",
               vmin=0.0, vmax=60.0, extend="max")
    cont = dict(type="contour", on=True, field="w", mode="height", z=3.0, levels="5",
                z_fixed=True, panels=[2])
    v1 = dict(version=1, kind="plan", rows=1, cols=3, vary="height", time_s=600.0,
              times_s=[600.0], panel_z=[1.0, 3.0, 6.0], panel_zmode="height", run=0,
              layers=[lay, cont], titles=["A", "", "C"], runs=[dict(path="/r", label="r")],
              size=[8, 3], letters=dict(on=True), contour_key=dict(on=True, layer=-1),
              annotations=[dict(kind="text", panel=1, text="x")])
    v2, _ = figdraw.upgrade(v1)
    pans = v2["panels"]
    assert [p["z"] for p in pans] == [1.0, 3.0, 6.0]
    assert [p["layers"][0]["z"] for p in pans] == [1.0, 3.0, 6.0]  # the fill follows the panel
    assert [p["layers"][1]["on"] for p in pans] == [False, False, True]  # (panels=[2])
    assert [p["title"] for p in pans] == ["A", "", "C"] and [p["letter"] for p in pans] == [0, 1, 2]
    assert [p["cell"] for p in pans] == [[0, 0, 1, 1], [0, 1, 1, 1], [0, 2, 1, 1]]
    assert all((p["run"], p["time_s"]) == (0, 600.0) for p in pans)
    assert v2["blocks"] == [dict(rows=1, cols=3)] and "layers" not in v2
    assert v2["contour_key"]["lay"]["field"] == "w"
    assert figdraw.upgrade(v2)[0] is v2  # (already version 2)
    assert v1["layers"][0]["extend"] == "max" and "lay" not in v1["contour_key"]  # (untouched)


def test_upgrade_counts_soundings_within_their_panel():
    from cm1view.figures import draw as figdraw
    snd = [dict(run=0, time_s=0.0, panel=0), dict(run=1, time_s=0.0, panel=1),
           dict(run=1, time_s=60.0, panel=0)]
    v1 = dict(version=1, kind="sounding", rows=1, cols=2, soundings=snd, size=[8, 4],
              runs=[dict(path="/a"), dict(path="/b")])
    data = {0: dict(nsnd=2, N0_e=0, N1_e=2), 1: dict(nsnd=1, N0_e=1)}
    v2, d2 = figdraw.upgrade(v1, data)
    p0, p1 = v2["panels"]
    assert [lay["run"] for lay in p0["layers"]] == [0, 1] and p1["layers"][0]["run"] == 1
    assert all(lay["type"] == "sounding" and "panel" not in lay for lay in p0["layers"])
    assert (d2[0]["N0_e"], d2[0]["N1_e"], d2[1]["N0_e"]) == (0, 1, 0)
    assert data[0]["N1_e"] == 2  # (the caller's data unchanged)


def test_upgrade_of_parts_keeps_each_parts_settings():
    from cm1view.figures import draw as figdraw
    part = dict(version=1, kind="plan", rows=2, cols=1, vary="time", times_s=[0.0, 60.0],
                run=0, layers=[], runs=[dict(path="/b")], size=[4, 6], share=0.4,
                font=dict(size=8), annotations=[dict(panel=1), dict(panel=-1)])
    combo = dict(version=1, kind="combo", arrange="row", parts=[dict(part, share=None), part],
                 size=[8, 6], colorbar=dict(mode="parts"), runs=[dict(path="/b")])
    v2, _ = figdraw.upgrade(combo)
    assert [p["id"] for p in v2["panels"]] == [0, 1, 1000, 1001]
    assert [p["letter"] for p in v2["panels"]] == [0, 1, 2, 3]
    b = v2["blocks"][1]
    assert (b["rows"], b["cols"], b["share"]) == (2, 1, 0.4)
    assert [a["panel"] for a in b["opts"]["annotations"]] == [1001, -1]
    assert figdraw.block_view(v2, 1)["font"] == dict(size=8)
    assert figdraw.block_shares(v2) == pytest.approx([0.6, 0.4])


def test_colorbar_ends_auto_and_shared():
    from cm1view.figures import draw as figdraw
    lay = dict(type="fill", vmin=0.0, vmax=10.0, extend="auto")
    assert figdraw.extend_of(lay, np.array([1.0, 5.0])) == "neither"
    assert figdraw.extend_of(lay, np.array([1.0, 12.0, np.nan])) == "max"
    assert figdraw.extend_of(lay, np.array([-1.0, 12.0])) == "both"
    assert figdraw.extend_of(dict(lay, mask_below=0.0), np.array([-1.0, 5.0])) == "neither"
    assert figdraw.extend_of(dict(lay, extend="min"), np.array([5.0])) == "min"
    assert figdraw.union_extend(["min", "max"]) == "both"
    assert figdraw.union_extend(["neither", "max"]) == "max"
    assert figdraw.union_extend([]) == "neither"


def _v2_plan(mode="shared"):
    x = np.linspace(-5.0, 5.0, 11)
    fill = dict(type="fill", on=True, cmap="viridis", vmin=0.0, vmax=10.0, extend="auto",
                style="mesh", units="dBZ")
    track = dict(type="track", on=True, run_color=True, run=1)
    spec = dict(version=2, size=[8.0, 6.0], blocks=[dict(rows=2, cols=2)],
                colorbar=dict(mode=mode), letters=dict(on=True), axes=dict(ticklabels="outer"),
                runs=[dict(path="/a"), dict(path="/b", color="#00ff00")],
                panels=[dict(id=0, kind="plan", cell=[0, 0, 1, 1], layers=[fill]),
                        dict(id=1, kind="plan", cell=[0, 1, 1, 1], layers=[fill]),
                        dict(id=2, kind="plan", cell=[1, 0, 1, 2], layers=[fill, track],
                             letter=5, z=2.0)])
    a = np.tile(x, (11, 1))
    data = {0: dict(x=x, y=x, L0=a + 10.0, time_s=0.0),  # past vmax
            1: dict(x=x, y=x, L0=a, time_s=0.0),  # below vmin
            2: dict(x=x, y=x, L0=a * 0.1 + 5.0, time_s=0.0, track_x=x, track_y=x)}
    return spec, data


def test_version_2_panels_span_cells_and_share_colorbar_ends():
    from cm1view.figures import draw as figdraw
    from matplotlib.colors import to_hex
    spec, data = _v2_plan()
    assert figdraw._extends(spec, data) == {0: "both", 1: "both", 2: "both"}
    fig = figdraw.draw(spec, data)
    axs = fig._cv_axes
    assert set(axs) == {0, 1, 2}
    # panel 2 spans both columns: centred under them (an equal-aspect map of square data
    # stays square, so its width does not double)
    c = [(axs[i].get_position().x0 + axs[i].get_position().x1) / 2 for i in (0, 1, 2)]
    assert abs(c[2] - (c[0] + c[1]) / 2) < 0.02 and c[1] - c[0] > 0.2
    assert to_hex(axs[2].lines[0].get_color()) == "#00ff00"  # the track in its own run's colour
    assert "f" in [a.txt._text.get_text() for a in axs[2].artists if hasattr(a, "txt")]
    cbars = [a for a in fig.axes if a not in axs.values()]
    assert len(cbars) == 1
    spec, data = _v2_plan("row")
    assert figdraw._extends(spec, data) == {0: "both", 1: "both", 2: "neither"}
    fig = figdraw.draw(spec, data)
    assert len([a for a in fig.axes if a not in fig._cv_axes.values()]) == 2


def test_layers_take_the_panels_run_time_and_height():
    from cm1view.figures import draw as figdraw
    p = dict(run=1, time_s=600.0, z=2.0)
    assert figdraw.resolved(p, dict(type="fill", z=None)) == \
        dict(type="fill", run=1, time_s=600.0, z=2.0)
    assert figdraw.resolved(p, dict(type="fill", run=0, z=5.0))["run"] == 0
    assert figdraw.resolved({}, dict(type="fill"))["run"] == 0


# ------------------------------------------------------------------ the panel tree
def _edited_v1():
    fill = dict(type="fill", on=True, field="dbz", mode="height", z=1.0, cmap="viridis",
                vmin=0.0, vmax=60.0, extend="neither")
    cont = dict(type="contour", on=True, field="w", mode="height", z=3.0, levels="5")
    edits = {"1": dict(run=1, time_s=900.0, z=2.0, title="B",
                       layers={"0": dict(cmap="magma", run=0, time_s=60.0)},
                       extra=[cont])}
    return dict(version=1, kind="plan", rows=1, cols=3, vary="time",
                times_s=[0.0, 300.0, 600.0], run=0, layers=[fill], titles=["A"],
                runs=[dict(path="/a"), dict(path="/b")], size=[9, 3], edits=edits)


def test_panel_edits_change_that_panel_alone():
    from cm1view.figures import draw as figdraw
    v1 = _edited_v1()
    assert figdraw.panel_ref(v1, 0) == (0, 0.0) and figdraw.panel_ref(v1, 1) == (1, 900.0)
    assert figdraw.form_ref(v1, 1) == (0, 300.0)
    lays = figdraw.spec_layers(v1, 1)
    assert len(lays) == 2 and lays[1]["type"] == "contour"  # (the extra layer)
    assert (lays[0]["z"], lays[0]["cmap"], lays[0]["run"]) == (2.0, "magma", 0)
    assert figdraw.spec_layers(v1, 0)[0]["cmap"] == "viridis"
    v2, _ = figdraw.upgrade(v1)
    p0, p1 = v2["panels"][:2]
    assert (p0["title"], p1["title"]) == ("A", "B")
    assert (p1["run"], p1["time_s"], p1["z"]) == (1, 900.0, 2.0) and "z" not in p0
    assert p1["layers"][0]["time_s"] == 60.0 and len(p1["layers"]) == 2
    assert "edits" not in v2 and "edits" not in (v2["blocks"][0].get("opts") or {})


def test_layers_of_another_run_or_time_are_read_apart():
    from cm1view.figures import spec as fg
    v1 = _edited_v1()
    assert fg.layer_groups(v1, 1) == {(0, 60.0): [0]}  # the fill; the contours: the panel's
    assert fg.layer_groups(v1, 0) == {}
    g = fg.group_spec(v1, 1, (0, 60.0), {0})
    assert fg.panel_ref(g, 0) == (0, 60.0)
    assert [lay["on"] for lay in fg.figdraw.spec_layers(g, 0)] == [True, False]
    x = np.arange(3.0)
    d = fg.merge_group(dict(x=x, y=x, L1=1), dict(x=x + 5, y=x, L0=2, L0_u=3), [0],
                       fg.figdraw.spec_layers(v1, 1))
    assert (d["L0"], d["L0_u"], d["L1"]) == (2, 3, 1) and d["L0_cx"][0] == 5.0


def test_animation_moves_edited_times_but_locked_layers():
    from cm1view.figures import spec as fg
    v1 = _edited_v1()
    v1["edits"]["1"]["extra"][0].update(time_s=60.0, time_lock=True)
    s = fg.shift_times(v1, 120.0)
    e = s["edits"]["1"]
    assert e["time_s"] == 1020.0 and e["layers"]["0"]["time_s"] == 180.0
    assert e["extra"][0]["time_s"] == 60.0  # (kept)
    assert v1["edits"]["1"]["time_s"] == 900.0  # (a copy)


def test_tree_layer_from_another_time_is_drawn(ed):
    """A layer of panel b at panel a's time: the same arrays as panel a's."""
    ed.rows.value, ed.cols.value = 1, 2
    ed.dom.value = "full"
    s = ed.collect()
    t0, t1 = s["times_s"][:2]
    assert t0 != t1
    ed.edits = {"1": {"layers": {"0": {"time_s": t0}}}}
    spec, data, fig = render(ed)
    assert spec["edits"] == {"1": {"layers": {"0": {"time_s": t0}}}}
    assert data[1]["time_s"] == pytest.approx(t1)  # (the panel keeps its time)
    assert np.array_equal(data[1]["L0"], data[0]["L0"], equal_nan=True)
    assert "L0_cx" in data[1] and set(fig._cv_axes) == {0, 1}


def _w(col, kind, name):
    return next(w for w in col.select(kind) if str(w.name).startswith(name))


def test_tree_widgets_change_one_panel(ed):
    import panel as pn
    ed.rows.value, ed.cols.value = 1, 2
    ed._tree_sync(force=True)
    assert len(ed.tree_list.objects) == 2 and "✎" not in ed.tree_list.objects[1].name
    ed._tree_pick(1)
    _w(ed.tree_detail, pn.widgets.TextInput, "Title").value = "Later"
    _w(ed.tree_detail, pn.widgets.TextInput, "Height").value = "3"
    _w(ed.tree_detail, pn.widgets.Select, "Add a layer").value = "contour"
    e = ed.collect()["edits"]
    assert e["1"]["title"] == "Later" and e["1"]["z"] == 3.0
    assert [lay["type"] for lay in e["1"]["extra"]] == ["contour"] and "0" not in e
    assert "✎" in ed.tree_list.objects[1].name
    s = ed.collect()
    ed.set_spec(json.loads(json.dumps(s)))  # (the edits come back)
    assert ed.collect()["edits"] == s["edits"]
    render(ed)
    ed._tree_pick(1)
    btn = next(b for b in ed.tree_detail.select(pn.widgets.Button)
               if b.name.startswith("Undo panel"))
    btn.clicks += 1
    assert ed.collect()["edits"] == {}


def test_tree_lists_soundings_of_each_panel(ed):
    ed.from_soundings()
    ed._tree_sync(force=True)
    assert ed.tree_list.objects and ed.tree_list.objects[0].name.startswith("a  Sounding")
    ed._tree_pick(0)
    assert "<li>" in "".join(str(getattr(o, "object", "")) for o in ed.tree_detail.objects)


def test_saved_spec_is_version_2_and_reopens_with_its_edits(ed, tmp_path):
    import os
    ed.rows.value, ed.cols.value = 1, 2
    ed.edits = {"1": {"title": "edited"}}
    base = str(tmp_path / "v2")
    ed.path.value = base
    ed._save_job(ed.collect(), True, base)
    with open(os.path.join(str(tmp_path), "_src", "v2_spec.json")) as f:
        saved = json.load(f)
    assert saved["version"] == 2 and [p["title"] for p in saved["panels"]][1] == "edited"
    assert saved["form"]["version"] == 1 and "made_with" in saved
    ed.edits = {}
    ed.spec_path.value = base + ".png"
    ed._load_spec()
    assert ed.collect()["edits"] == {"1": {"title": "edited"}}


# ------------------------------------------------------------------ distributions
@pytest.mark.parametrize("plot", ["hist", "box", "violin", "ecdf"])
def test_distribution_figure_draws_each_plot(ed, plot):
    from cm1view.figures import spec as fg
    ed.from_dists()  # (no distributions on the map: w over the domain)
    assert ed.kind.value == "dist" and len(ed.dist_cards) == 1
    t1 = float(ed.run.times[4])
    e = fg.dist_defaults(dict(field="winterp", vmode="layer", z0=0.0, z1=5.0,
                              region="domain", lo=0.5), 0, t1)
    ed.dist_cards.append(ed._dist_card(e))
    ed.ds["plot"].value = plot
    ed.ds["stats"].value = True
    spec, data, fig = render(ed)
    d = data[0]
    assert d["ndist"] == 2 and not d.get("missing") and "time_s" not in d  # (two times)
    assert spec["dist"]["plot"] == plot and len(fig.axes) == 1
    ax = fig.axes[0]
    if plot in ("hist", "ecdf"):
        assert ax.get_legend() is not None and "mean" in ax.get_legend().texts[0].get_text()
        assert "(" in ax.get_xlabel()  # the field and its units
    else:
        ticks = [t.get_text() for t in ax.get_xticklabels()]
        assert len(ticks) == 2 and ticks[1].startswith(str(d["D1_label"]))
        assert "mean" in ticks[0] and "(" in ax.get_ylabel()
    assert ed.dist_cache  # (restyling reads nothing again)
    n = len(ed.dist_cache)
    ed.ds["bins"].value, ed.ds["logy"].value = 20, True
    render(ed)
    assert len(ed.dist_cache) == n


def test_distribution_figure_of_the_maps(ed, viewer):
    v = viewer
    v.dist_field.value, v.dist_vmode.value = "winterp", "all"
    v._dist_request()
    wait(lambda: len(v.dists) == 1, msg="the distribution")
    v.dist_kind.value, v.dist_norm.value = "violin", "pdf"
    v._on_dist_figure(None)
    assert v.workspace.value == "Figure" and ed.kind.value == "dist"
    s = ed.collect()
    assert s["dist"]["plot"] == "violin" and s["dists"][0]["recipe"]["vmode"] == "all"
    assert s["dists"][0]["time_s"] == float(ed.run.times[v.t])
    spec, data, fig = render(ed)
    st = next(iter(v.dists.values()))["st"]
    assert data[0]["D0_s"][0] == st["n"]  # (the same values as the map's)


def test_distribution_spec_upgrades_to_panels(ed):
    from cm1view.figures import draw as figdraw, spec as fg
    ed.from_dists()
    e = dict(ed.dist_cards[0].collect(), panel=1)
    ed.dist_cards.append(ed._dist_card(e))
    ed._fit_grid(reset=True)
    s = ed.collect()
    assert fg.npanels(s) == 2
    data = ed.panel_data(s)
    v2, d2 = figdraw.upgrade(s, data)
    assert [p["kind"] for p in v2["panels"]] == ["dist", "dist"]
    assert [[lay["type"] for lay in p["layers"]] for p in v2["panels"]] == [["dist"], ["dist"]]
    assert int(d2[1]["D0_e"]) == 0  # (counted within its panel)
    figdraw.draw(s, data)
    ed._tree_sync(force=True)
    assert ed.tree_list.objects[0].name.startswith("a  Distribution")


def _difference(ed):
    """The first fill as a difference: minus the run's first output."""
    c = next(c for c in ed.cards if c.type == "fill")
    c.w["minus_on"].value = True
    c.w["minus_time"].value = next(v for v in c.w["minus_time"].options.values() if v != "")
    return c


def test_difference_layer(ed):
    c = _difference(ed)
    lay = c.collect()
    assert lay["minus"] == dict(run=None, time_s=lay["minus"]["time_s"], grid="ask")
    assert (lay["cmap"], lay["reverse"], lay["mask_below"]) == ("RdBu", True, None)
    assert lay["vmin"] == -lay["vmax"] < 0  # (centred on 0)
    spec, data, fig = render(ed)
    j = next(j for j, x in enumerate(spec["layers"]) if x.get("minus"))
    t0 = lay["minus"]["time_s"]
    for d in data.values():  # (a panel at the subtracted time: zero)
        if abs(d["time_s"] - t0) < 1:
            assert np.nanmax(np.abs(d[f"L{j}"])) == 0.0
    assert any(np.nanmax(np.abs(d[f"L{j}"])) > 0 for d in data.values())
    assert any("difference" in a.get_ylabel() + a.get_xlabel() for a in fig.axes)
    c.w["minus_on"].value = False
    assert "minus" not in c.collect() and c.collect()["cmap"] != "RdBu"


def test_difference_of_different_grids():
    from cm1view.figures import spec as fg
    x, y = np.arange(4.0), np.arange(3.0)
    a, b = np.ones((3, 4)), np.add.outer(y, x)
    d = fg.subtract(dict(x=x, y=y, L0=a), dict(x=x, y=y, L0=b), 0)
    assert np.array_equal(d["L0"], a - b)
    moved = dict(x=x + 0.5, y=y, L0=b)
    assert "choose" in fg.subtract(dict(x=x, y=y, L0=a), moved, 0)["missing"]
    assert "choose" not in fg.subtract(dict(x=x, y=y, L0=a), moved, 0, "refuse")["missing"]
    d = fg.subtract(dict(x=x, y=y, L0=a), moved, 0, "interp")
    assert np.isnan(d["L0"][0, 0]) and d["L0"][1, 1] == 1.0 - 1.5
    assert fg.subtract(dict(x=x, y=y, L0=a), dict(missing="no output"), 0)["missing"] == \
        "difference: no output"
    v1 = _edited_v1()
    lay = dict(fg.figdraw.spec_layers(v1, 1)[0], minus=dict(run=1, time_s=None))
    assert fg.minus_ref(v1, 1, lay) == (1, 60.0)  # (the layer's own time)
    assert fg.minus_ref(v1, 0, dict(type="fill", minus=dict(time_s=30.0))) == (0, 30.0)
    v2, _ = fg.figdraw.upgrade(dict(v1, layers=[dict(v1["layers"][0], minus=dict(run=1))]))
    assert v2["panels"][0]["layers"][0]["minus"] == dict(run=1)


def _swath(ed):
    """The first fill as a swath: its maximum from the run's first output to each panel's
    time."""
    c = next(c for c in ed.cards if c.type == "fill")
    c.w["reduce_op"].value = "max"
    c.w["reduce_t0"].value = next(v for v in c.w["reduce_t0"].options.values() if v != "")
    return c


def test_time_window_layer(ed):
    from cm1view.core import swath
    c = _swath(ed)
    lay = c.collect()
    assert lay["reduce"] == dict(op="max", t0=lay["reduce"]["t0"], t1=None, every=1)
    assert "max over a time window" in c.title.object
    spec, data, fig = render(ed)
    j = next(j for j, x in enumerate(spec["layers"]) if x.get("reduce"))
    assert any("max" in a.get_ylabel() + a.get_xlabel() for a in fig.axes)
    c.w["reduce_op"].value = ""
    assert "reduce" not in c.collect()
    _, plain, _ = render(ed)
    for i, d in data.items():  # (the window ends at the panel's own output)
        a, b = d[f"L{j}"], plain[i][f"L{j}"]
        ok = np.isfinite(a) & np.isfinite(b)
        assert ok.any() and np.all(a[ok] >= b[ok] - 1e-5)
    assert any(f.endswith(".npz") for f in __import__("os").listdir(swath.cache_dir()))


class _Run:
    """A tiny run on a 1 km grid with three outputs a minute apart."""
    def __init__(self, umove=0.0):
        self.times, self.dx, self.dy, self.files = [0.0, 60.0, 120.0], 1000.0, 1000.0, []
        self.umove, self.vmove, self.path = umove, 0.0, f"fake-{umove}"


class _Fields:
    def __init__(self, col):
        self.col = col  # output t -> the column of the blob

    def __getitem__(self, name):
        from types import SimpleNamespace
        return SimpleNamespace(storm=False)

    def plane(self, name, t, mode, z, storm=None):
        a = np.zeros((3, 8), dtype=np.float32)
        a[:, self.col(t)] = 1.0
        return a


def test_swaths_follow_the_ground_and_composites_the_storm(tmp_path, monkeypatch):
    from cm1view.core import swath
    monkeypatch.setattr(swath, "CACHE_DIR", str(tmp_path))
    lay = dict(field="w", mode="height", z=1.0, reduce=dict(op="max", t0=None, t1=None))
    # the grid moves 1 km a minute: a blob fixed on the ground moves 1 column back
    run = _Run(umove=1000.0 / 60.0)
    a, n = swath.reduce(run, _Fields(lambda t: 5 - t), lay, 2)
    assert n == 3 and np.array_equal(np.flatnonzero(a[0] > 0), [3])
    a2, _ = swath.reduce(run, _Fields(lambda t: 0), lay, 2)  # (from the cache)
    assert np.array_equal(a, a2, equal_nan=True)
    assert swath.window(run, dict(lay["reduce"], every=2), 120.0) == [0, 2]
    assert swath.window(run, dict(lay["reduce"], t0=60.0), 60.0) == [1]
    # a storm moving 1 km a minute with its blob: the composite keeps it in one column
    lay = dict(lay, reduce=dict(op="composite"))
    centers = {t: (float(t), 0.0) for t in range(3)}
    a, n = swath.reduce(_Run(), _Fields(lambda t: 2 + t), lay, 2, centers)
    assert n == 3 and np.array_equal(np.flatnonzero(a[0] > 0), [4]) and a[0, 4] == 1.0
    with pytest.raises(ValueError, match="track"):
        swath.reduce(_Run(), _Fields(lambda t: 0), lay, 2, {})


def test_templates_apply_to_another_run(ed, coarse_run):
    import os
    from cm1view.figures import spec as fg
    spec = ed.collect()
    ed.tpl_name.value = "two by three"
    ed._save_template()
    path = ed.tpl_sel.value
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    assert os.path.dirname(path) == fg.templates_dir() and not ed.tpl_go.disabled
    tpl = fg.load_template(path)
    assert "runs" not in tpl and tpl["template"]["time_s"] == spec["time_s"]
    run, _ = ed.open_run(coarse_run)
    out = fg.from_template(tpl, run, 2)
    dt, half = run.times[2] - spec["time_s"], float(np.diff(run.times).max()) / 2 + 1
    assert out["time_s"] == run.times[2] and "runs" not in out
    assert len(out["times_s"]) == len(spec["times_s"])
    for a, b in zip(spec["times_s"], out["times_s"]):  # (as far apart, at outputs)
        assert b is None or (b in run.times and abs(b - (a + dt)) <= half)
    assert out["layers"] == spec["layers"]
    ed.tpl_sel.value = path
    ed._apply_template()  # (onto the run shown)
    assert "Applied" in txt(ed.msg.object), ed.msg.object
    got = ed.collect()
    assert got["layers"] == spec["layers"] and got["runs"][0]["path"] == ed.run.path
    render(ed)


def test_style_presets_and_matplotlib_styles(ed, tmp_path):
    from cm1view.figures import draw as figdraw
    ed.preset.value = "ams"
    ed._apply_preset()
    s = ed.collect()
    assert (s["font"]["size"], s["letters"]["fmt"], s["export"]["format"]) == \
        (8.0, "({a})", "pdf")
    assert s["size"][0] == (3.2 if s["cols"] == 1 else 6.5) and not s["size_auto"]
    ed.preset.value = "dark"
    ed._apply_preset()
    s = ed.collect()
    assert (s["background"], s["mplstyle"], ed.bg.value) == ("black", "dark_background", "black")
    assert figdraw.rc(s)["axes.edgecolor"] == "white" and figdraw.rc(s)["font.size"] == 14.0
    render(ed)
    f = tmp_path / "thick.mplstyle"
    f.write_text("lines.linewidth: 3\nbackend: agg\n")
    rc = figdraw.rc(dict(s, mplstyle=str(f)))
    assert rc["lines.linewidth"] == 3 and "backend" not in rc
    with pytest.raises(ValueError, match="no such style"):
        figdraw.rc(dict(s, mplstyle="no-such-style"))
    ed.preset.value = "default"
    ed._apply_preset()
    assert (ed.collect()["mplstyle"], ed.collect()["font"]["size"]) == ("", 10.0)


def test_copy_a_layers_look(ed):
    ed._add_layer("contour")
    src, dst = [c for c in ed.cards if c.type == "contour"][:2]
    other = next(f for f in ed.fields.defs if f != src.w["field"].value)
    dst.w["field"].value = other
    src.w["color"].value, src.w["lw"].value = "#ff0000", 2.0
    levels = dst.collect()["levels"]
    i, j = ed.cards.index(src), ed.cards.index(dst)
    fill = next(k for k, c in enumerate(ed.cards) if c.type == "fill")
    cmap = ed.cards[fill].collect()["cmap"]
    assert set(ed.look_from.options.values()) == set(range(len(ed.cards)))
    ed.look_from.value, ed.look_to.value = i, [j, fill]
    ed._copy_look()
    new = ed.cards[j].collect()
    assert (new["color"], new["lw"], new["field"], new["levels"]) == \
        ("#ff0000", 2.0, other, levels)  # (another field: its levels stay)
    assert "another kind" in txt(ed.msg.object) and ed.cards[fill].collect()["cmap"] == cmap
    render(ed)
