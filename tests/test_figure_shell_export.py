"""M9: documents through time, templates and files (spec/docfile.py), colorbars and legends across
kinds, and the new layout's autosave, session, Export, animation and templates."""
import json
import os

import numpy as np
import pytest

from conftest import new_spec
from matplotlib.collections import QuadMesh
from matplotlib.lines import Line2D

from cm1view.figures import draw as figdraw, spec as fg
from cm1view.figures.shell import docedit as de, nodes

FILL = dict(type="fill", field="dbz", on=True, cmap="viridis", vmin=0.0, vmax=60.0, units="dBZ")


def doc_of(*panels, **more):
    return {**dict(version=3, size=[6.0, 4.0], grid=dict(rows=1, cols=max(len(panels), 1)),
                   style={}, kinds={}, layers={}, sections={}, annotations=[],
                   runs=[dict(id="r0", path="/x/one"), dict(id="r1", path="/x/two", t0_min=10.0)],
                   panels=list(panels)), **more}


def plan(pid, c=0, run="r0", t=600.0, **more):
    return {**dict(id=pid, kind="plan", cell=[0, c, 1, 1], run=run, time_s=t, title="", layers=[]),
            **more}


# ------------------------------------------------------------------ through time
def test_shift_moves_panels_entries_and_layers_but_what_is_locked():
    d = doc_of(plan(0), dict(plan(1, 1), layers=[
        dict(ref="l0", over=dict(time_s=300.0)), dict(type="fill", time_s=100.0, time_lock=True)]),
        dict(id=2, kind="sounding", cell=[0, 2, 1, 1], run=None, time_s=None, title="", layers=[
            dict(type="sounding", run="r0", time_s=600.0, time_s1=700.0),
            dict(type="sounding", run="r0", time_s=50.0, time_lock=True)]),
        dict(id=3, kind="table", cell=[0, 3, 1, 1], run=None, time_s=None, title="", layers=[
            dict(type="table", times_s=[600.0])]))
    d["layers"]["l0"] = dict(type="fill", field="dbz")
    was = json.dumps(d)
    s = fg.shift_times(d, 60.0)
    assert json.dumps(d) == was  # (a copy)
    assert s["panels"][0]["time_s"] == 660.0
    assert s["panels"][1]["layers"][0]["over"]["time_s"] == 360.0
    assert s["panels"][1]["layers"][1]["time_s"] == 100.0
    assert s["panels"][2]["layers"][0]["time_s"] == 660.0
    assert s["panels"][2]["layers"][0]["time_s1"] == 760.0
    assert s["panels"][2]["layers"][1]["time_s"] == 50.0
    assert s["panels"][3]["layers"][0]["times_s"] == [600.0]


def test_a_scenes_own_settings_step_with_it():
    scene = dict(id=0, kind="scene", cell=[0, 0, 1, 1], run="r0", time_s=600.0, title="", layers=[],
                 opts=dict(scene3d=dict(orbit=90.0)))
    other = dict(scene, id=1, cell=[0, 1, 1, 1], opts=dict(scene3d=dict(orbit=0.0)))
    d = doc_of(scene, other)
    d["kinds"]["scene"] = dict(scene3d=dict(camera=dict(azimuth=30.0, elevation=20.0, zoom=1.0)))
    s = fg.shift_times(d, 60.0)
    assert s["panels"][0]["opts"]["scene3d"]["t0_s"] == 600.0
    f = fg.scene_frame(s, 1, 3)
    assert f["panels"][0]["opts"]["scene3d"]["camera"] != d["kinds"]["scene"]["scene3d"]["camera"]
    assert "camera" not in f["panels"][1]["opts"]["scene3d"]


def test_by_output_each_time_steps_its_own_runs_outputs():
    d = doc_of(plan(0, t=60.0), plan(1, 1, run="r1", t=200.0))
    d["runs"][0]["outputs_s"] = [0.0, 60.0, 120.0, 180.0]
    d["runs"][1]["outputs_s"] = [0.0, 100.0, 200.0, 300.0]
    s = fg.shift_times(d, fg.OutputStep(60.0, 1))
    assert [p["time_s"] for p in s["panels"]] == [120.0, 300.0]


def test_only_series_dont_animate():
    line = dict(id=0, kind="line", cell=[0, 0, 1, 1], run=None, time_s=None, title="", layers=[])
    assert not fg.animated(doc_of(line))
    assert fg.animated(doc_of(line, plan(1, 1)))


def test_form_and_document_step_alike(ed):
    form = new_spec(ed)
    d = fg.to_doc(form)
    assert sorted(fg.time_refs(d)) == sorted(fg.time_refs(form))
    runs = {ed.run.path: ed.run}
    assert fg.frame_offsets(d, runs, 2) == fg.frame_offsets(form, runs, 2)


# ------------------------------------------------------------------ templates
class _Run:
    times = np.array([0.0, 300.0, 600.0, 900.0, 1200.0])


def test_a_template_keeps_the_first_panels_run_and_its_annotations():
    d = doc_of(plan(0, t=600.0), plan(1, 1, run="r1", t=600.0), annotations=[
        dict(kind="text", panel=1), dict(kind="text", panel=0)])
    d["style"]["time_match"] = "output"
    t = fg.template(d, "name")
    assert "runs" not in t and "time_match" not in t["style"]
    assert [p["id"] for p in t["panels"]] == [0]
    assert t["template"] == dict(name="name", time_s=600.0)
    assert [a["panel"] for a in t["annotations"]] == [0]


def test_a_templates_times_go_to_the_shown_time_and_past_the_end_stay_empty():
    d = doc_of(plan(0, t=600.0), plan(1, 1, t=1200.0))
    s = fg.from_template(fg.template(d), _Run, 3)
    assert [p["time_s"] for p in s["panels"]] == [900.0]  # (1500 s: past the run's end)


def test_entries_of_another_run_go_and_every_run_stays_so():
    prof = dict(id=0, kind="profile", cell=[0, 0, 1, 1], run=None, time_s=None, title="", layers=[
        dict(type="profile", run="r0", runs=None, time_s=600.0),
        dict(type="profile", run="r1", runs=["r1"], time_s=600.0)])
    snd = dict(id=1, kind="sounding", cell=[0, 1, 1, 1], run=None, time_s=None, title="", layers=[
        dict(type="sounding", run="r1", time_s=600.0)])
    t = fg.template(doc_of(prof, snd))
    assert [p["id"] for p in t["panels"]] == [0]
    assert len(t["panels"][0]["layers"]) == 1 and t["panels"][0]["layers"][0]["runs"] is None


def test_applied_template_draws_like_the_forms(ed):
    from cm1view.figures import batch
    form = new_spec(ed)
    t = len(ed.run.times) - 1
    a = batch.finish(fg.from_template(fg.template(form, "x"), ed.run, t), ed.run, ed.F, t)
    b = batch.finish(fg.from_template(fg.template(fg.to_doc(form), "x"), ed.run, t), ed.run, ed.F, t)
    assert [p["time_s"] for p in figdraw.upgrade(a)[0]["panels"]] == \
        [p["time_s"] for p in figdraw.upgrade(b)[0]["panels"]]


def test_a_preset_sets_the_style_every_kind_and_what_a_panel_has_of_its_own():
    d = doc_of(plan(0, opts=dict(font=dict(size=5.0))))
    d["kinds"] = dict(plan=dict(axes=dict(frame_lw=3.0)), th=dict(axes=dict()))
    s = fg.apply_style(d, "ams")
    assert s["style"]["font"]["size"] == 8.0 and s["panels"][0]["opts"]["font"]["size"] == 8.0
    assert s["kinds"]["plan"]["axes"]["frame_lw"] == 0.6 and s["kinds"]["th"]["axes"]["frame_lw"] == 0.6
    assert s["export"]["format"] == "pdf"
    assert s["size"][0] == 3.2 and s["size_auto"] is False


# ------------------------------------------------------------------ files
def test_a_document_saves_as_version_2_and_opens_as_itself(ed, tmp_path):
    d = fg.to_doc(new_spec(ed))
    d["suptitle"] = "here"
    path = fg.save_spec(d, str(tmp_path / "f"))
    with open(path) as f:
        raw = json.load(f)
    assert raw["version"] == 2 and raw["form"]["version"] == 3 and raw["panels"]
    back = fg.load_spec(path)
    assert fg.is_doc(back) and back["suptitle"] == "here" and "made_with" in back


def test_a_bundle_of_a_document_redraws_alone(ed, tmp_path):
    import subprocess
    import sys
    d = fg.to_doc(new_spec(ed))
    out = fg.save_bundle(d, ed.panel_data(d), str(tmp_path / "f"))
    r = subprocess.run([sys.executable, out["script"]], capture_output=True, text=True,
                       env=dict(os.environ, MPLBACKEND="Agg"), timeout=120)
    assert r.returncode == 0, r.stderr


def test_defaults_fill_what_a_document_lacks_and_keep_what_it_has(ed):
    d = fg.to_doc(new_spec(ed))
    d["style"]["font"] = dict(size=7.0)
    del d["style"]["spacing"]
    d["kinds"]["plan"].pop("domain")
    s = fg.doc_defaults(d, ed.run, ed.F, 0)
    assert s["style"]["font"]["size"] == 7.0 and s["style"]["font"]["family"]
    assert "wspace" in s["style"]["spacing"] and s["kinds"]["plan"]["domain"]["mode"]


def test_render_a_document(ed, tmp_path):
    from cm1view.figures.batch import main
    d = fg.to_doc(new_spec(ed))
    spec = fg.save_spec(d, str(tmp_path / "f"))
    assert main([spec, "--out", str(tmp_path / "again.png"), "--dpi", "50"]) == 0
    assert (tmp_path / "again.png").exists()
    assert main([spec, "--run", ed.run.path, "--out", str(tmp_path / "on_{run}.png"),
                 "--dpi", "50"]) == 0


# ------------------------------------------------------------------ colorbars and legends
def _mesh_data(pid, **more):
    x = np.linspace(0.0, 10.0, 6)
    a = np.outer(x[:-1] + 1.0, x[:-1] + 1.0)
    return dict(x=x[:-1], y=x[:-1], L0=a, time_s=600.0, xlim=(0.0, 10.0), ylim=(0.0, 10.0), **more)


def _bars(fig):
    return [a for a in fig.axes if getattr(a, "_colorbar", None) is not None
            or a.get_label() == "<colorbar>"]


def _base(*panels):
    d = doc_of(*panels)
    d["style"] = dict(colorbar=dict(mode="shared", location="bottom", orientation="horizontal"),
                      font=dict(size=10.0))
    d["kinds"] = dict(plan=dict(axes={}), th=dict(axes={}))
    return d


def _layer(**more):
    return dict(FILL, **more)


def test_one_kind_keeps_one_bar_and_mixed_kinds_one_for_each_look():
    a = plan(0, layers=[_layer()])
    b = dict(plan(1, 1, layers=[_layer()]))
    assert len(_bars(figdraw.draw(_base(a, b), {0: _mesh_data(0), 1: _mesh_data(1)}))) == 1
    th = dict(id=2, kind="th", cell=[0, 2, 1, 1], run="r0", time_s=None, title="",
              layers=[_layer(type="series", cmap="magma", units="m/s", vmax=40.0)])
    d = _base(a, b, th)
    d["grid"]["cols"] = 3
    fig = figdraw.draw(d, {0: _mesh_data(0), 1: _mesh_data(1), 2: _mesh_data(2)})
    assert len(_bars(fig)) == 2


def test_panels_naming_a_bar_share_it_whatever_the_mode():
    a, b = plan(0, layers=[_layer()]), plan(1, 1, layers=[_layer(cmap="magma")])
    d = _base(a, b)
    d["style"]["colorbar"]["mode"] = "each"
    data = {0: _mesh_data(0), 1: _mesh_data(1)}
    assert len(_bars(figdraw.draw(d, data))) == 2
    de.set_panel_colorbar(d, 0, group="one")
    de.set_panel_colorbar(d, 1, group="one")
    assert len(_bars(figdraw.draw(d, data))) == 1
    de.set_panel_colorbar(d, 1, show=False)
    assert d["panels"][1]["colorbar"] == dict(show=False, group="one")
    de.set_panel_colorbar(d, 1, show=True, group="")
    assert "colorbar" not in d["panels"][1]


def test_a_kinds_colorbar_settings_reach_its_bar_only():
    th = dict(id=1, kind="th", cell=[0, 1, 1, 1], run="r0", time_s=None, title="",
              layers=[_layer(type="series", cmap="magma")])
    d = _base(plan(0, layers=[_layer()]), th)
    d["kinds"]["th"]["colorbar"] = dict(location="right", orientation="vertical")
    fig = figdraw.draw(d, {0: _mesh_data(0), 1: _mesh_data(1)})
    bars = _bars(fig)
    wide = [a.get_position().width > a.get_position().height for a in bars]
    assert sorted(wide) == [False, True]


def test_in_a_mixed_figure_the_legend_goes_where_entries_are():
    line = dict(type="contour", on=True, legend="Updraft", levels="1", color="k", field="w")
    snd = dict(id=0, kind="dist", cell=[0, 0, 1, 1], run=None, time_s=None, title="", layers=[])
    d = _base(snd, plan(1, 1, layers=[line]))
    d["style"]["legend"] = dict(where="panel", panel=0)
    d["kinds"]["dist"] = dict(axes={}, dist={})
    x = np.linspace(0.0, 10.0, 6)
    data = {0: dict(ndist=0, time_s=600.0), 1: dict(x=x, y=x, L0=np.outer(x, x), time_s=600.0,
                                                    xlim=(0.0, 10.0), ylim=(0.0, 10.0))}
    fig = figdraw.draw(d, data)
    assert fig._cv_axes[1].get_legend() is not None
    assert fig._cv_axes[0].get_legend() is None
    assert isinstance(fig._cv_axes[1].get_legend().legend_handles[0], Line2D)
    assert fig.axes and not any(isinstance(c, QuadMesh) for c in fig._cv_axes[0].collections)


def test_a_legend_panel_id_stays_with_its_panel():
    d = _base(plan(5), plan(2, 1))
    d["style"]["legend"] = dict(panel=2, panels=[5])
    res = figdraw.resolve(d)
    order = [p["id"] for p in res["panels"]]
    assert res["legend"]["panel"] == order.index(2) and res["legend"]["panels"] == [order.index(5)]


# ------------------------------------------------------------------ the new layout
class _Now:
    def submit(self, fn, *a, **k):
        fn(*a, **k)

    def shutdown(self, *a, **k):
        pass


@pytest.fixture
def shell(reg, monkeypatch, tmp_path):
    monkeypatch.setenv("CM1VIEW_CACHE_DIR", str(tmp_path / "cache"))
    from cm1view.viewer import app as A
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    v._schedule = lambda f: f()
    v.pools["fig"].shutdown(wait=False)
    v.pools["fig"] = _Now()
    v.confirm.ask = lambda paths, go: go()
    v.figed.shell.open()
    yield v.figed.shell
    v.close()


def test_the_example_is_not_kept_but_an_edit_is(shell):
    ed = shell.ed
    assert not ed.own_figure() and not os.path.exists(ed._auto_path())
    shell.edit(lambda d: d.update(suptitle="mine"))
    shell.request(force=True, delay=False)
    assert ed.own_figure()
    with open(ed._auto_path()) as f:
        state = json.load(f)
    assert state["doc"]["suptitle"] == "mine" and "spec" not in state


def test_a_session_gives_the_document_back(shell, reg):
    from cm1view.viewer import app as A
    shell.edit(lambda d: d.update(suptitle="mine"))
    s = json.loads(json.dumps(shell.v.session_state()))
    assert s["figure"]["doc"]["suptitle"] == "mine"
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    v.apply_session(s)
    other = v.figed.shell
    assert other.doc["suptitle"] == "mine"
    v.close()


def test_export_saves_the_document_and_opens_it_again(shell, tmp_path):
    ed = shell.ed
    assert not shell.exp_btn.disabled
    shell.export.open()
    shell.edit(lambda d: d.update(suptitle="saved"))
    ed.path.value = str(tmp_path / "f" / "one")
    assert shell.export.path.value == ed.path.value
    shell.export._save()
    assert (tmp_path / "f" / "one.png").exists()
    spec = tmp_path / "f" / "_src" / "one_spec.json"
    assert spec.exists() and (tmp_path / "f" / "_src" / "one_thumb.png").exists()
    shell.edit(lambda d: d.update(suptitle="later"))
    assert ed._load_spec(str(spec)) and shell.doc["suptitle"] == "saved"
    assert ed.path.value == str(tmp_path / "f" / "one")
    shell.undo()
    assert shell.doc["suptitle"] == "later"


def test_a_template_of_the_document_opens_here(shell):
    ed = shell.ed
    shell.edit(lambda d: d.update(suptitle="in the template"))
    path = fg.save_template(ed._figure_now(), "t")
    try:
        shell.edit(lambda d: d.update(suptitle="other"))
        assert ed._apply_template(path) and shell.doc["suptitle"] == "in the template"
        assert shell.doc["runs"][0]["path"] == ed.run.path
    finally:
        os.remove(path)


def test_a_preset_is_one_undo_step(shell):
    before = json.dumps(shell.doc, default=float)
    shell.apply_style("talk")
    assert shell.doc["style"]["font"]["size"] == 14.0
    shell.undo()
    assert json.dumps(shell.doc, default=float) == before


def test_a_mixed_figures_height_follows_its_rows(shell):
    pane = shell.inspector.grid
    pane.add_panel("sounding", "new column")
    h = shell.doc["size"][1]
    rows = de.grid_shape(shell.doc)[0]
    pane.add_panel("sounding", "new row")
    assert shell.doc["size"][1] == pytest.approx(h * (rows + 1) / rows, abs=0.01)


def test_the_figure_node_has_a_legend_section_for_maps(shell):
    shell._show(nodes.FIGURE)
    assert any(getattr(o, "title", "") == "Legend" for o in shell.inspector.body.objects)


def _on_rows(ed):
    """A 2 × 2 of plan views with one colorbar per row, past the fill's range: (shell, doc)."""
    from cm1view.figures import spec as fg
    ed.open_quick()
    ed.qs_kind.value = "plan"
    ed.qs_rows.value, ed.qs_cols.value = 2, 2
    ed._quick_make()
    shell = ed.shell
    d = fg.plain_copy(shell.doc)
    d["style"]["colorbar"]["mode"] = "row"
    next(x for x in d["layers"].values() if x["type"] == "fill").update(
        vmin=0.0, vmax=0.1, extend="auto")
    shell._take(d)
    return shell, shell.doc


def _inspector_widgets(shell, node):
    def walk(o):
        out = [o]
        for c in getattr(o, "objects", None) or []:
            out += walk(c)
        return out
    shell._show(node)
    for o in walk(shell.inspector.body):
        if hasattr(o, "collapsed"):
            o.collapsed = False
    return walk(shell.inspector.body)


def test_a_bar_has_one_controlling_panel(ed):
    from cm1view.figures import draw as figdraw
    shell, doc = _on_rows(ed)
    assert figdraw.bar_members(figdraw.upgrade(doc)[0]) == {
        0: [0, 1], 1: [0, 1], 2: [2, 3], 3: [2, 3]}
    for mode, first in (("shared", [0, 1, 2, 3]), ("col", [0, 2]), ("each", [0])):
        doc["style"]["colorbar"]["mode"] = mode
        assert figdraw.bar_members(figdraw.upgrade(doc)[0])[0] == first
    doc["style"]["colorbar"]["mode"] = "none"
    assert figdraw.bar_members(figdraw.upgrade(doc)[0]) == {}
    doc["style"]["colorbar"]["mode"] = "row"
    from cm1view.figures.shell import docedit as de
    de.set_panel_colorbar(doc, 0, show=False)  # (the next panel then controls the row's)
    assert figdraw.bar_members(figdraw.upgrade(doc)[0])[1] == [1]


def test_arrows_set_on_the_controlling_panel_reach_its_whole_bar(ed):
    from conftest import render
    shell, _ = _on_rows(ed)
    ends = lambda: [a._colorbar.extend for a in render(ed)[2].axes  # noqa: E731
                    if getattr(a, "_colorbar", None) is not None]
    assert ends() == ["max", "max"]
    arrows = [w for w in _inspector_widgets(shell, "panel:0")
              if getattr(w, "name", "") == "Colorbar arrows"]
    assert len(arrows) == 1
    arrows[0].value = "neither"
    assert ends() == ["neither", "max"]  # (this row's, not the other's)


def test_bar_settings_show_only_where_they_change_the_bar(ed):
    shell, doc = _on_rows(ed)
    names = lambda node: {getattr(w, "name", "") for w in _inspector_widgets(shell, node)  # noqa: E731
                          if getattr(w, "visible", True)}
    first, other = names("panel:0"), names("panel:1")
    assert {"Colorbar arrows", "Colorbar ticks (blank: the figure's, else auto)"} <= first
    assert "Colorbar arrows" not in other and "Go to panel a" in other
    assert "Colorbar arrows" not in names("layer:0:0")  # (in the panel's section now)
    assert "Colormap" in names("layer:0:0") and "Colormap" not in names("layer:1:0")
    doc["style"]["colorbar"]["mode"] = "each"
    assert "Colorbar arrows" in names("panel:1") and "Colormap" in names("layer:1:0")
    doc["style"]["colorbar"]["mode"] = "none"
    assert "Its colours have a bar" not in names("panel:0")


def test_colours_on_a_shared_bar_follow_its_controlling_panel(ed):
    from cm1view.figures import draw as figdraw
    from cm1view.figures.shell import bars, docedit as de
    shell, doc = _on_rows(ed)
    cmap = lambda pid: figdraw.panel_layers(  # noqa: E731
        shell.doc, de.panel_by_id(shell.doc, pid))[0][1]["cmap"]
    was = cmap(2)
    w = next(w for w in _inspector_widgets(shell, "layer:0:0") if getattr(w, "name", "") == "Colormap")
    w.value = "viridis"
    assert cmap(0) == cmap(1) == "viridis" and cmap(2) == was
    de.write_panel(shell.doc, de.panel_by_id(shell.doc, 1), 0, {"cmap": "magma"})
    bar = bars.bar_of(shell.doc, 1)
    assert bars.colours_differ(shell.doc, bar, 1)
    match = next(w for w in _inspector_widgets(shell, "layer:1:0")
                 if getattr(w, "name", "") == "Match the bar")
    match.clicks += 1
    assert cmap(1) == "viridis" and not bars.colours_differ(shell.doc, bars.bar_of(shell.doc, 1), 1)


def test_a_shared_layers_bar_settings_reach_every_panel(ed):
    from cm1view.figures.shell import layerrow
    from cm1view.figures.shell import bars
    shell, doc = _on_rows(ed)
    bars.set_value(doc, bars.bar_of(doc, 0), "extend", "neither")
    lid = next(k for k, x in doc["layers"].items() if x["type"] == "fill")
    layerrow.Shared(lid, "plan").write(doc, dict(extend="both"))
    assert bars.values(doc, bars.bar_of(doc, 0))["extend"] == "both"
    assert not any("extend" in (i.get("over") or {}) for p in doc["panels"] for i in p["layers"])
