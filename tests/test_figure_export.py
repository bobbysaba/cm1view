"""Figure workspace output: the exported script, animations, own code, provenance, and
figures of parts."""

import numpy as np

from cm1view.figures import spec as fg
from conftest import txt


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


def test_animation_needs_panels_that_step(ed):
    ed.from_series()
    ed._on_anim()
    assert "nothing to step" in txt(ed.an_msg.object)


def test_animation_frames_stop_where_a_panel_runs_out():
    class Run:
        def __init__(self, n):
            self.times = np.arange(n) * 60.0

    runs = [dict(path="/long"), dict(path="/short")]
    long_run = {"/long": Run(11), "/short": Run(6)}
    prof = dict(kind="profile", runs=runs, profiles=[
        dict(run=0, runs=[0, 1], time_s=0.0, time_s1=None, panel=0)])
    assert fg.frame_offsets(prof, long_run)[-1] == 300.0  # (every run of a profile)
    prof["profiles"][0]["runs"] = None  # (None: all of them)
    assert fg.frame_offsets(prof, long_run)[-1] == 300.0
    # a time window stays whole: its length is kept to the end of the run
    prof["profiles"][0].update(runs=[0], time_s1=120.0)
    assert fg.frame_offsets(prof, long_run)[-1] == 480.0
    table = dict(kind="profile", runs=runs, profiles=[
        dict(source="table", run=0, runs=[], time_s=0.0, panel=0)])
    assert fg.time_refs(table) == [] and fg.frame_offsets(table, long_run) == []


def test_held_entries_stay_while_the_others_step():
    """An entry with time_lock keeps its times in the frames and does not end them."""
    from cm1view.figures import spec as fg

    class Run:
        def __init__(self, n):
            self.times = np.arange(n) * 60.0

    held = dict(fg.sounding_defaults(0, 0.0), time_lock=True, time_s1=60.0)
    moving = dict(fg.sounding_defaults(1, 0.0))
    s = dict(kind="sounding", runs=[dict(path="/short"), dict(path="/long")],
             soundings=[held, moving])
    f = fg.shift_times(s, 120.0)
    assert [e["time_s"] for e in f["soundings"]] == [0.0, 120.0]
    assert f["soundings"][0]["time_s1"] == 60.0
    assert fg.time_refs(s) == [("/long", 0.0)]
    runs = {"/short": Run(2), "/long": Run(6)}
    assert fg.frame_offsets(s, runs)[-1] == 300.0  # (only the moving one's outputs count)
    both = dict(s, soundings=[held, dict(moving, time_lock=True)])
    assert fg.time_refs(both) == [] and fg.frame_offsets(both, runs) == []
    out = fg.panels._one_time(s, {}, s["soundings"])  # (the time label follows the frames)
    assert out == dict(time_s=0.0, run=1)
    f = fg.shift_times(s, 120.0)
    assert fg.panels._one_time(f, {}, f["soundings"]) == dict(time_s=120.0, run=1)


def test_save_asks_before_replacing_the_image_or_the_spec(ed, tmp_path, monkeypatch):
    from cm1view.figures import spec as fg
    base, asked = str(tmp_path / "fig"), []
    monkeypatch.setattr(ed.v.confirm, "ask", lambda paths, then: asked.append(paths))
    ed.path.value = base
    ed.save_more.value = False
    ed._save()
    out = fg.bundle_paths({}, base)
    assert asked.pop() == [out["image"], out["spec"]]
    ed.save_more.value = True  # (the tick in the dialog: all of them)
    ed._save()
    assert set(asked.pop()) == set(out.values())
    ed.save_more.value = False


