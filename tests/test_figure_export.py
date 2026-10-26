"""Figure workspace output: the exported script, animations, own code, provenance, and
figures of parts."""
import json

import numpy as np
import pytest

from cm1view.figures import spec as fg
from conftest import txt, wait, render, difference_layer, swath_layer


@pytest.mark.parametrize("start", ["plan", "series", "soundings", "dists", "difference",
                                   "swath", "dark"])
def test_script_redraws_the_identical_image(ed, tmp_path, start):
    import os
    import subprocess
    import sys
    import matplotlib.image as mi
    if start == "difference":
        difference_layer(ed)
    elif start == "swath":
        swath_layer(ed)
    elif start == "dark":  # (a matplotlib style in the spec)
        ed.set_spec(fg.apply_style(ed.collect(), "dark"))
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
    with open(base + ".py") as f:  # (short: the drawing code is in _src/)
        assert "def _draw2" not in f.read()
    assert os.path.isfile(str(tmp_path / "_src" / f"{start}_draw.py"))
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
    ts = ed.run.times  # not evenly spaced: offsets follow the first panel's outputs
    ed.an_step.value, ed.an_end.value = 2, None
    full = ed._anim_offsets(spec)  # through the end of the run (the second panel's)
    assert full == [float(ts[i] - ts[1]) for i in range(1, len(full) * 2, 2)]
    assert len(full) == 4 and spec["times_s"][1] + full[-1] <= ts[-1]  # (the second ends it)
    ed.anim_sec.collapsed = False  # the End time choices: the frames' times
    assert list(ed.an_end.options.values())[1:] == [float(ts[i])
                                                     for i in range(3, len(full) * 2, 2)]
    ed.an_end.value = float(ts[5])
    offsets = ed._anim_offsets(spec)
    assert offsets == [float(ts[i] - ts[1]) for i in (1, 3, 5)]
    assert "→ 3 frames" in txt(ed.an_count.object), ed.an_count.object
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


def test_animation_saves_at_gif_path_or_save_as(ed, tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(ed.v.confirm, "ask", lambda paths, go: asked.append(paths))
    ed.rows.value, ed.cols.value = 1, 1
    ed.tm_rows[0].value = float(ed.run.times[1])
    ed.path.value, ed.an_frames.value = str(tmp_path / "fig.png"), True
    ed.an_path.value = str(tmp_path / "loops" / "storm.gif")
    ed._on_anim()
    assert asked[-1] == [str(tmp_path / "loops" / "storm.gif"),
                         str(tmp_path / "loops" / "storm_frames")]
    ed.an_path.value = ""  # blank: next to Save as
    ed._on_anim()
    assert asked[-1] == [str(tmp_path / "fig.gif"), str(tmp_path / "fig_frames")]


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
    with open(base + ".py") as f:  # (short: the drawing code is in _src/)
        assert "def _draw2" not in f.read()
    assert os.path.isfile(str(tmp_path / "_src" / "parts_draw.py"))
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
    ed.an_step.value = 1
    ed.anim_sec.collapsed = False
    ed.an_end.value = list(ed.an_end.options.values())[2]
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
    with open(base + ".py") as f:  # (short: the drawing code is in _src/)
        assert "def _draw2" not in f.read()
    assert os.path.isfile(str(tmp_path / "_src" / "withseries_draw.py"))
    r = subprocess.run([sys.executable, "-I", base + ".py"], capture_output=True, text=True,
                       cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-500:]
    assert np.array_equal(mi.imread(base + ".png"), mi.imread(base + "_viewer.png"))
