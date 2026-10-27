"""Figure spec version 2: upgrades from version 1, panels spanning cells, shared colorbar
ends, and the panel tree."""
import json

import numpy as np
import pytest

from conftest import render, edited_v1


# ------------------------------------------------------------------ spec version 2
def _setup(ed, how):
    if how == "height":
        ed.g_rows.value, ed.g_cols.value = "none", "heights"
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
                font=dict(size=8), annotations=[dict(panel=1), dict(panel=-1),
                                                 dict(panel=[0, 1])])
    combo = dict(version=1, kind="combo", arrange="row", parts=[dict(part, share=None), part],
                 size=[8, 6], colorbar=dict(mode="parts"), runs=[dict(path="/b")])
    v2, _ = figdraw.upgrade(combo)
    assert [p["id"] for p in v2["panels"]] == [0, 1, 1000, 1001]
    assert [p["letter"] for p in v2["panels"]] == [0, 1, 2, 3]
    b = v2["blocks"][1]
    assert (b["rows"], b["cols"], b["share"]) == (2, 1, 0.4)
    assert [a["panel"] for a in b["opts"]["annotations"]] == [1001, -1, [1000, 1001]]
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


def test_animation_colorbar_ends_are_those_of_all_frames():
    from cm1view.figures import draw as figdraw
    spec, data = _v2_plan("none")
    spec["panels"][0]["layers"][0]["nlevels"] = 10  # (every panel's: the norm has the ends)
    calm ={i: dict(d, L0=np.full((11, 11), 5.0)) for i, d in data.items()}
    ends = figdraw.fill_ends(spec, calm)
    assert ends == {(0, 0): "neither", (1, 0): "neither", (2, 0): "neither"}
    ends = figdraw.fill_ends(spec, data, ends)  # a later frame past vmin / vmax
    assert ends == {(0, 0): "max", (1, 0): "min", (2, 0): "neither"}
    assert figdraw.fill_ends(spec, calm, ends) == ends  # (ends only grow)
    fig = figdraw.draw(spec, calm, ends)  # the calm frame keeps panel 0's arrow
    assert [fig._cv_axes[i].collections[0].norm.extend for i in (0, 1, 2)] == \
        ["max", "min", "neither"]
    assert spec["panels"][0]["layers"][0]["extend"] == "auto"  # (the spec untouched)


def test_layers_take_the_panels_run_time_and_height():
    from cm1view.figures import draw as figdraw
    p = dict(run=1, time_s=600.0, z=2.0)
    assert figdraw.resolved(p, dict(type="fill", z=None)) == \
        dict(type="fill", run=1, time_s=600.0, z=2.0)
    assert figdraw.resolved(p, dict(type="fill", run=0, z=5.0))["run"] == 0
    assert figdraw.resolved({}, dict(type="fill"))["run"] == 0


# ------------------------------------------------------------------ the panel tree
def test_panel_edits_change_that_panel_alone():
    from cm1view.figures import draw as figdraw
    v1 = edited_v1()
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
    v1 = edited_v1()
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
    v1 = edited_v1()
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


def test_annotation_in_several_panels():
    from cm1view.figures.cards.distcard import parse_panels, panels_text
    from cm1view.figures.draw.base import ann_on
    assert [parse_panels(t) for t in ("", "all", "0", "2", "1, 3-4")] == \
        [-1, -1, -1, 1, [0, 2, 3]]
    assert panels_text([0, 2, 3]) == "1, 3-4" and panels_text(-1) == "" and panels_text(1) == "2"
    a = dict(kind="text", panel=[0, 2])
    assert [ann_on(a, i) for i in range(4)] == [True, False, True, False]
    assert all(ann_on(dict(panel=-1), i) for i in range(4))
