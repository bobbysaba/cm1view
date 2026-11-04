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
def test_panel_edit_y_range_is_that_panel_s_and_keeps_its_legend():
    from cm1view.figures import draw as figdraw
    v1 = dict(version=1, kind="line", rows=1, cols=2, size=[8, 4], ts=dict(ymin=-1.0, ymax=9.0),
              series=[dict(panel=0), dict(panel=1)],
              edits={"1": dict(ymax=0.0, legend=dict(on=False))})
    v2, _ = figdraw.upgrade(v1)
    a, b = (figdraw.panel_view(v2, p)["ts"] for p in v2["panels"])
    assert (a["ymin"], a["ymax"]) == (-1.0, 9.0)
    assert (b["ymin"], b["ymax"], b["legend"]) == (-1.0, 0.0, False)


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
    ed.tabs.active = 2  # (the tree is built while its tab is open)
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
    ed.tabs.active = 2  # (the tree is built while its tab is open)
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
    assert [parse_panels(t) for t in ("", "all", "0", "2", "1, 3-4", "a, c-d", "b")] == \
        [-1, -1, -1, 1, [0, 2, 3], [0, 2, 3], 1]
    assert panels_text([0, 2, 3]) == "a, c-d" and panels_text(-1) == "" and panels_text(1) == "b"
    assert parse_panels(panels_text([0, 26, 27])) == [0, 26, 27]  # (past z: numbers)
    a = dict(kind="text", panel=[0, 2])
    assert [ann_on(a, i) for i in range(4)] == [True, False, True, False]
    assert all(ann_on(dict(panel=-1), i) for i in range(4))


# ------------------------------------------------------------------ section cards
def _xsec_grid_v1():
    """A version 1 section figure of two runs (rows) by two sections (columns), the
    last panel at its own time."""
    from cm1view.figures import spec as fg
    fill = dict(type="fill", on=True, field="w", mode="height", z=1.0, cmap="RdBu_r",
                vmin=-10.0, vmax=10.0, extend="both")
    return dict(version=1, kind="xsec", rows=2, cols=2, time_s=600.0, times_s=[600.0],
                run=0, layers=[fill], titles=["", ""], row_titles=["a", "b"],
                grid=dict(rows="runs", cols="sections", runs=[0, 1]), vary="grid",
                runs=[dict(path="/a", label="a"), dict(path="/b", label="b")], size=[8, 6],
                sections=[fg.section_defaults(orient="x", pos="fixed"),
                          fg.section_defaults(orient="y", pos="fixed")],
                xsec=dict(ztop=6.0, dz=0.025, coords="storm"), domain=dict(mode="full"),
                coords="grid", edits={"3": dict(time_s=900.0, title="late")})


def test_section_cards_give_each_panel_its_run_time_and_section():
    """A section figure of cards: each card is one panel's section, run and time (blank:
    the figure's); panels without a card are empty, the grid fits the last card."""
    from cm1view.figures import draw as figdraw, spec as fg
    s = _xsec_grid_v1()
    s.update(grid=dict(rows="none", cols="none", runs=[]), edits={}, rows=2, cols=3,
             sections=[dict(fg.section_defaults(orient="x"), run=0, time_s=None, panel=0),
                       dict(fg.section_defaults(orient="y"), run=1, time_s=900.0, panel=1),
                       dict(fg.section_defaults(orient="angle"), run=1, time_s=300.0,
                            panel=4),
                       dict(fg.section_defaults(orient="x"), run=7, time_s=None, panel=5)])
    assert figdraw.xsec_cards(s) is not None and figdraw.xsec_cards(dict(s, kind="plan")) is None
    assert fg.npanels(s) == 6
    assert [fg.panel_ref(s, i) for i in range(6)] == [(0, 600.0), (1, 900.0), None, None,
                                                    (1, 300.0), None]  # (run 7: none)
    assert [fg.panel_section(s, i)[1]["orient"] for i in (0, 1, 4)] == ["x", "y", "angle"]
    sh = fg.shift_times(s, 60.0)  # (an animation frame: the cards' own times move too)
    assert [fg.panel_ref(sh, i) for i in (0, 1, 4)] == [(0, 660.0), (1, 960.0), (1, 360.0)]
    g = fg.group_spec(s, 1, (0, 120.0), [0])  # (one panel's layers at another run, time)
    assert fg.panel_ref(g, 0) == (0, 120.0) and fg.panel_section(g, 0)[1]["orient"] == "y"
    v2, _ = figdraw.upgrade(s)
    assert [(p["id"], p["run"], p["time_s"]) for p in v2["panels"]] == \
        [(0, 0, 600.0), (1, 1, 900.0), (4, 1, 300.0)]
    k0 = fg.data_key(s, 0, None)  # (another card changing leaves panel 0's arrays)
    s["sections"][1]["half"] = 3.0
    assert fg.data_key(s, 0, None) == k0


def test_older_section_figures_become_cards():
    """to_cards: an older grid of runs × sections becomes a card per panel with its
    run, time (its panel edit's) and section; panel titles stay; cards stay cards."""
    from cm1view.figures import spec as fg
    s = _xsec_grid_v1()
    before = [(fg.panel_ref(s, i), fg.panel_section(s, i)[1]["orient"]) for i in range(4)]
    fg.to_cards(s)
    assert [(c["run"], c["time_s"], c["panel"], c["orient"]) for c in s["sections"]] == \
        [(0, 600.0, 0, "x"), (0, 600.0, 1, "y"), (1, 600.0, 2, "x"), (1, 900.0, 3, "y")]
    assert [(fg.panel_ref(s, i), fg.panel_section(s, i)[1]["orient"])
            for i in range(4)] == before
    assert s["edits"] == {"3": dict(title="late")}
    assert s["grid"] == dict(rows="none", cols="none", runs=[])
    again = json.loads(json.dumps(s))
    assert fg.to_cards(again) == s
    one = dict(_xsec_grid_v1(), rows=1, cols=1, grid=None, vary="time", edits={})
    one.pop("sections")  # (an older figure's one section: spec["xsec"])
    one["xsec"] = dict(mode="storm", angle=0.0, half=8.0, offset=[0.0, 0.0])
    fg.to_cards(one)
    assert [(c["orient"], c["half"], c["panel"], c["run"]) for c in one["sections"]] == \
        [("x", 8.0, 0, 0)]
    plan = dict(_xsec_grid_v1(), kind="plan")
    assert fg.to_cards(json.loads(json.dumps(plan))) == plan  # (not a section figure)


def test_older_time_height_figures_become_cards():
    """th_to_cards: an older time-height grid (a panel per series and run) becomes a
    card per panel with its one run and panel number; the panels show the same; cards
    stay cards; a template keeps the first run's cards."""
    from cm1view.figures import draw as figdraw, spec as fg
    s = dict(kind="th", runs=[dict(path="/a"), dict(path="/b"), dict(path="/c")],
             runs_as="cols", rows=1, cols=1, titles=["A", "", "", "", "", "F"],
             series=[dict(label="w", runs=None, panel=0), dict(label="q", runs=[2], panel=0)])
    before = [(lambda r: r and (r[0], s["series"][r[1]]["label"]))(figdraw.series_ref(s, i))
              for i in range(6)]
    fg.th_to_cards(s)
    assert s["runs_as"] == "cards" and (s["rows"], s["cols"]) == (2, 3)
    assert [(e["label"], e["runs"], e["panel"]) for e in s["series"]] == \
        [("w", [0], 0), ("w", [1], 1), ("w", [2], 2), ("q", [2], 5)]
    assert figdraw.npanels(s) == 6
    assert [(lambda r: r and (r[0], s["series"][r[1]]["label"]))(figdraw.series_ref(s, i))
            for i in range(6)] == before
    again = json.loads(json.dumps(s))
    assert fg.th_to_cards(again) == s
    s["series"].append(dict(label="dup", runs=[0], panel=0))  # (first card per panel)
    assert figdraw.series_ref(s, 0) == (0, 0)
    s["series"].append(dict(label="bad", runs=[7], panel=3))  # (not one of the runs)
    assert figdraw.series_ref(s, 3) is None
    line = dict(s, kind="line")
    assert fg.th_to_cards(json.loads(json.dumps(line))) == line  # (not time-height)
    t = fg.template(s, "t")
    assert [(e["label"], e["runs"]) for e in t["series"]] == [("w", [0]), ("dup", [0])]


def test_parts_share_sections_and_keep_the_cards():
    """A plan-view part's sections changed: the section part's cards take the new
    sections but keep their runs, times and panels (one more: a new panel); the
    section part's cards go to the plan part as they are."""
    from cm1view.figures import spec as fg
    from cm1view.figures.combo import share_sections
    xs = _xsec_grid_v1()
    fg.to_cards(xs)
    plan = dict(_xsec_grid_v1(), kind="plan",
                sections=[fg.section_defaults(orient="angle", pos="fixed", angle=45.0)]
                + [fg.card_section(c) for c in xs["sections"][1:]]
                + [fg.section_defaults(orient="ab", pos="fixed", a=[0, 0], b=[1, 1])])
    share_sections([plan, xs], plan)
    assert [(c["orient"], c["run"], c["time_s"], c["panel"]) for c in xs["sections"]] == \
        [("angle", 0, 600.0, 0), ("y", 0, 600.0, 1), ("x", 1, 600.0, 2),
         ("y", 1, 900.0, 3), ("ab", 1, 900.0, 4)]
    xs["sections"][0]["half"] = 4.0
    share_sections([plan, xs], xs)
    assert plan["sections"] == xs["sections"]


# ------------------------------------------------------------------ series time zero
def test_each_series_has_its_own_time_zero():
    """Run B's series shifted by its card's time zero (30 min) lines up with run A's,
    in time series and time-height panels; the figure's time zero adds to both."""
    from types import SimpleNamespace
    import xarray as xr
    from cm1view.figures import spec as fg
    times = np.arange(0.0, 5401.0, 600.0)  # 0-90 min
    nt = times.size
    run = SimpleNamespace(times=times)
    ds = xr.Dataset(dict(value=("time", np.arange(nt, dtype=float)),
                         computed=("time", np.ones(nt, np.int8)),
                         profile=(("time", "z"), np.ones((nt, 2)))), coords=dict(z=[1.0, 2.0]))
    a = dict(recipe=dict(z0=0.0, z1=3.0), op="", panel=0, runs=[0], label="w")
    b = dict(a, runs=[1], t0_min=30.0)
    spec = dict(kind="line", series=[a, b], ts={}, runs=[dict(label="A"), dict(label="B")])
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert d["S0_t"][0] == 0.0 and d["S1_t"][0] == -30.0 and d["S1_t"][3] == 0.0
    spec["time_label"] = dict(t0_min=10.0)
    assert fg.line_panel(spec, 0, lambda k, e: (run, ds))["S1_t"][0] == -40.0
    assert fg.th_panel(run, ds, b, spec)["x"][0] == -40.0
    assert fg.th_panel(run, ds, a, spec)["x"][0] == -10.0
    # the legend: a series' own label; a series of several runs adds each run's folder
    assert [d["S0_label"], d["S1_label"]] == ["w", "w"]
    spec["runs"] = [dict(label="A", path="/x/run_a"), dict(label="B", path="/x/run_b/")]
    spec["series"] = [dict(a, runs=None)]
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert [d["S0_label"], d["S1_label"]] == ["w · run_a", "w · run_b"]


def test_a_run_time_zero_shifts_its_lines():
    """A run's time zero moves that run's lines and time-height panels, on top of the
    figure's and the card's; hand edits stay at their model time, your own data has no
    run, and an ensemble band of the runs lines up."""
    from types import SimpleNamespace
    import xarray as xr
    from cm1view.figures import spec as fg
    times = np.arange(0.0, 5401.0, 600.0)  # 0-90 min
    nt = times.size
    run = SimpleNamespace(times=times)
    ds = xr.Dataset(dict(value=("time", np.arange(nt, dtype=float)),
                         computed=("time", np.ones(nt, np.int8)),
                         profile=(("time", "z"), np.ones((nt, 2)))), coords=dict(z=[1.0, 2.0]))
    a = dict(recipe=dict(z0=0.0, z1=3.0), op="", panel=0, runs=None, label="w", t0_min=1.0)
    obs = dict(source="table", table=dict(t=[0.0, 5.0], v=[1.0, 2.0]), panel=0, label="obs")
    spec = dict(kind="line", series=[a, obs], ts={}, time_label=dict(t0_min=10.0),
                runs=[dict(path="a"), dict(path="b", t0_min=30.0)])
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert d["S0_t"][0] == -11.0 and d["S1_t"][0] == -41.0  # (figure + run + card)
    assert d["S2_label"] == "obs" and d["S2_t"][0] == -10.0  # (figure + its card: no run)
    assert d["xlim"] == (-41.0, 79.0)
    assert fg.th_panel(run, ds, a, spec, 1)["x"][0] == -41.0
    assert fg.th_panel(run, ds, a, spec, 0)["x"][0] == -11.0
    assert fg.th_panel(run, ds, a, spec)["x"][0] == -11.0  # (no run: none of a run's)
    # a hand edit stays at its model time, wherever the time zero puts it
    e = dict(a, runs=[1], edits={"1": {fg.edit_key(600.0): -5.0}})
    d = fg.line_panel(dict(spec, series=[e]), 0, lambda k, e: (run, ds))
    assert d["S0_v"][1] == -5.0 and d["S0_t"][1] == -31.0
    # an ensemble of the runs: on their shifted times (two runs where both have values)
    b = dict(a, ens="minmax", ens_mid="mean", t0_min=0.0)
    spec = dict(spec, series=[b], time_label={})
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    j = next(j for j in range(d["nlines"]) if f"S{j}_ens" in d)
    assert d[f"S{j}_t"][0] == 0.0 and d[f"S{j}_t"][-1] == 60.0
    # no time zero: as before
    for r in spec["runs"]:
        r.pop("t0_min", None)
    assert fg.line_panel(spec, 0, lambda k, e: (run, ds))["S0_t"][0] == 0.0


# ------------------------------------------------------------------ series data by hand
def _line_setup():
    from types import SimpleNamespace
    import xarray as xr
    times = np.arange(0.0, 3001.0, 600.0)  # 0-50 min
    nt = times.size
    run = SimpleNamespace(times=times)
    ds = xr.Dataset(dict(value=("time", np.arange(nt, dtype=float)),
                         computed=("time", np.ones(nt, np.int8))))
    a = dict(recipe=dict(), op="", panel=0, runs=[0], label="w")
    spec = dict(kind="line", series=[a], ts={}, runs=[dict(label="A"), dict(label="B")])
    return run, ds, a, spec


def test_hand_edits_change_and_blank_a_series():
    """A series' hand edits (by model time, s) replace or blank its values for that run
    only; an edit at a time the run lacks is left out; the legend says "(edited)"
    unless Style turns it off."""
    from cm1view.figures import spec as fg
    run, ds, a, spec = _line_setup()
    a["edits"] = {"0": {fg.edit_key(1200.0): 9.5, fg.edit_key(1800.0): None,
                        fg.edit_key(99999.0): 1.0}}
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert d["S0_v"][2] == 9.5 and np.isnan(d["S0_v"][3]) and d["S0_v"][4] == 4.0
    assert d["S0_label"] == "w (edited)"
    spec["ts"]["mark_edited"] = False
    assert fg.line_panel(spec, 0, lambda k, e: (run, ds))["S0_label"] == "w"
    a["runs"] = [1]  # (the edits are run 0's: run 1 drawn as computed)
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert list(d["S0_v"]) == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    v, used, gone = fg.apply_edits(np.zeros(6), run.times, dict(a, edits={"1": {
        fg.edit_key(600.0): 2.0, fg.edit_key(7.0): 3.0}}), 1)
    assert (used, gone) == (1, 1) and v[1] == 2.0


def test_hand_edits_feed_the_ensemble_band():
    """An ensemble band is made from the members as edited, and says "(edited)"."""
    from cm1view.figures import spec as fg
    run, ds, a, spec = _line_setup()
    a.update(runs=None, ens="minmax", ens_members="hidden",
             edits={"1": {fg.edit_key(0.0): 10.0}})
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert d["nlines"] == 1 and "S0_ens" in d
    assert d["S0_hi"][0] == 10.0 and d["S0_lo"][0] == 0.0
    assert d["S0_label"].endswith(" (edited)")


def test_a_series_of_your_own_data_draws_without_a_run():
    """A series of your own (source "table"): its points in time order, shifted by the
    time zero, beside a computed series; nothing asked of any run."""
    from cm1view.figures import spec as fg
    run, ds, a, spec = _line_setup()
    obs = dict(recipe=dict(), op="", panel=0, source="table", label="obs", ls="--",
               color="k", table=dict(t=[20.0, 0.0, 10.0, None], v=[3.0, 1.0, None, 7.0]))
    spec["series"].append(obs)
    asked = []
    d = fg.line_panel(spec, 0, lambda k, e: asked.append((k, e)) or (run, ds))
    assert asked == [(0, 0)] and d["nlines"] == 2
    assert d["S1_label"] == "obs" and d["S1_r"] == -1
    assert list(d["S1_t"]) == [0.0, 10.0, 20.0] and np.isnan(d["S1_v"][1])
    assert fg.series_pairs(spec) == [(0, 0)]
    spec["time_label"] = dict(t0_min=5.0)
    assert fg.line_panel(spec, 0, lambda k, e: (run, ds))["S1_t"][0] == -5.0
    spec["series"] = [obs]  # (alone, with no data at all: why)
    obs["table"] = dict(t=[0.0], v=[None])
    assert fg.line_panel(spec, 0, lambda k, e: None)["missing"] == "no values in your data"


def test_a_figure_draws_your_own_data_and_hand_edits(ed):
    """A time-series figure with a hand-edited series and a series of your own data
    draws both lines; the edited one's legend entry says "(edited)"."""
    from conftest import wait
    from cm1view.figures import draw as figdraw, spec as fg
    ed.from_series()
    ed.kind.value = "line"
    spec = ed.collect()
    ed.panel_data(spec)  # (starts computing the series)
    wait(lambda: not ed.series_pending(), 120, "the series")
    n = ed.panel_data(spec)[0]["nlines"]
    e0 = spec["series"][0]
    spec["series"][0] = dict(e0, edits={"0": {fg.edit_key(ed.v.run.times[0]): -123.0}})
    spec["series"].append(dict(e0, source="table", label="obs", runs=[], panel=0,
                               table=dict(t=[0.0, 5.0], v=[1.0, 2.0])))
    data = ed.panel_data(spec)
    assert data[0]["nlines"] == n + 1
    assert any(-123.0 in data[0][f"S{j}_v"] for j in range(n))
    fig = figdraw.draw(spec, data)
    texts = [x.get_text() for x in fig.axes[0].get_legend().texts]
    assert any(x.endswith(" (edited)") for x in texts) and "obs" in texts


def test_series_card_values_section_edits(ed):
    """A time-series card's Values section (built when opened) lists the run's values;
    typing in Yours edits a point, 'blank' blanks one, the edits go into the spec and
    the preview, a recipe change keeps them with a word on the card, Reset all clears."""
    from conftest import wait
    from cm1view.figures import spec as fg
    from cm1view.figures.cards.seriesvals import BLANK, parse_yours

    class Ev:
        def __init__(self, row, value):
            self.column, self.row, self.value = "yours", row, value

    assert parse_yours("") == (False, None) and parse_yours("blank") == (True, None)
    assert parse_yours(" 2.5 ") == (True, 2.5) and parse_yours("two") is None
    ed.from_series()
    ed.kind.value = "line"
    c = ed.ser_cards[0]
    assert c.vals.w is None  # (nothing built until opened)
    ed.panel_data(ed.collect())
    wait(lambda: not ed.series_pending(), 120, "the series")
    c.vals.section.collapsed = False
    df = c.vals.w["table"].value
    assert len(df) == len(ed.v.run.times) and (df["yours"] == "").all()
    c.vals._on_edit(Ev(0, "-123"))
    c.vals._on_edit(Ev(1, "blank"))
    df = c.vals.w["table"].value
    assert df["yours"][0] == "-123" and df["yours"][1] == BLANK
    e = ed.collect()["series"][0]
    t = ed.v.run.times
    assert e["edits"]["0"] == {fg.edit_key(t[0]): -123.0, fg.edit_key(t[1]): None}
    d = ed.panel_data(ed.collect())[0]
    assert -123.0 in d["S0_v"] and d["S0_label"].endswith(fg.EDITED)
    c.vals._on_edit(Ev(0, ""))  # (cleared: back to computed)
    assert list(ed.collect()["series"][0]["edits"]["0"]) == [fg.edit_key(t[1])]
    assert c.vals._csv().getvalue().startswith("time_min,model_time_s,computed,plotted")
    c.w["reduce"].value = "min" if c.w["reduce"].value != "min" else "max"
    assert "hand edit" in c.info.object  # (recipe changed: edits kept, said so)
    c.vals._reset_all()
    assert "edits" not in ed.collect()["series"][0] and not c.info.object


def test_parse_your_own_data():
    """Pasted text: commas, tabs, semicolons or spaces; a header (its second column
    with units in brackets); # comments; blank / nan values gaps; errors with their line;
    table_text reads back the same."""
    from cm1view.figures import spec as fg
    tab, notes = fg.parse_table("# obs\ntime, rain (mm)\n0,1\n5,2\n10, nan\n7,3,9\n")
    assert tab == dict(t=[0.0, 5.0, 10.0, 7.0], v=[1.0, 2.0, None, 3.0],
                       names=["time", "rain (mm)"])
    assert len(notes) == 2  # (a third column; times out of order)
    assert fg.parse_table(fg.table_text(tab))[0] == tab
    assert fg.parse_table("0\t1\n5\t\n")[0] == dict(t=[0.0, 5.0], v=[1.0, None])
    assert fg.parse_table("t  v\n 0 1\n5   2\n")[0]["v"] == [1.0, 2.0]
    for bad, why in [("", "no data"), ("0,1\nx,2", "line 2"), ("5", "line 1"),
                     ("a,b\nc,d", "line 2"), ("\n".join(f"{j},1" for j in range(10001)),
                                              "more than")]:
        with pytest.raises(ValueError, match=why):
            fg.parse_table(bad)


def test_your_data_card(ed):
    """+ Your data (time series): a card in the last card's panel; pasted text becomes
    the entry's table (the header's label and units), a bad paste keeps the data before
    and says why, a file loads the same way; the line is drawn without a run; the card
    stays (not drawn) through time-height and back, and comes back from a saved spec."""
    from cm1view.figures import spec as fg
    from cm1view.figures.cards import DataCard
    ed.from_series()
    ed.kind.value = "line"
    n = len(ed.ser_cards)
    assert ed.ser_data.visible
    ed._add_data()
    c = ed.ser_cards[-1]
    assert isinstance(c, DataCard) and len(ed.ser_cards) == n + 1
    assert c.w["panel"].value == ed.ser_cards[-2].w["panel"].value
    c.w["text"].value = "time, w max (m/s)\n0,1\n5,\n10,30"
    e = ed.collect()["series"][-1]
    assert fg.is_table(e) and e["label"] == "w max" and e["units"] == "m/s"
    assert e["table"]["t"] == [0.0, 5.0, 10.0] and e["table"]["v"] == [1.0, None, 30.0]
    c.w["text"].value = "0,1\nzz,2"
    assert "line 2" in c.note.object and ed.collect()["series"][-1]["table"]["t"][-1] == 10.0
    c.w["file"].value = b"\xef\xbb\xbft,v\n1,2\n3,4\n"
    assert ed.collect()["series"][-1]["table"] == dict(t=[1.0, 3.0], v=[2.0, 4.0],
                                                       names=["t", "v"])
    d = fg.line_panel(dict(ed.collect(), series=[ed.collect()["series"][-1]]), 0,
                      lambda k, e: None)
    assert d["nlines"] == 1 and list(d["S0_t"]) == [1.0, 3.0]
    ed.kind.value = "th"
    assert not ed.ser_data.visible and c in ed.ser_cards and not c.body_col.visible
    ed.kind.value = "line"
    assert c in ed.ser_cards and c.body_col.visible
    s = ed.collect()
    ed.set_spec(s)
    assert isinstance(ed.ser_cards[-1], DataCard)
    assert ed.ser_cards[-1].collect()["table"]["t"] == [1.0, 3.0]


# ------------------------------------------------------------------ panel letters
def test_letters_follow_the_panels_until_set_by_hand(ed):
    def letters():
        return ed.collect()["letters"]["on"]
    ed.rows.value, ed.cols.value = 1, 1
    assert letters() is False and ed.let_on.value is False
    ed.rows.value, ed.cols.value = 1, 2
    assert letters() is True and ed.let_on.value is True
    ed.rows.value, ed.cols.value = 1, 1
    assert letters() is False
    ed.let_on.value = True  # (by hand: it stays)
    assert letters() is True and ed.collect()["letters"]["auto"] is False
    ed.rows.value, ed.cols.value = 1, 2
    ed.let_on.value = False
    assert letters() is False


def test_letters_saved_without_auto_stay_as_saved(ed):
    """A figure saved before letters followed the panels keeps its letter."""
    s = ed.collect()
    s["letters"].pop("auto")
    s["letters"]["on"] = True
    s.update(rows=1, cols=1, times_s=s["times_s"][:1], times=s["times"][:1])
    ed.set_spec(s)
    assert ed.collect()["letters"]["on"] is True


def test_every_part_has_letters_in_a_figure_of_parts(ed):
    ed.rows.value, ed.cols.value = 1, 1
    assert ed.collect()["letters"]["on"] is False
    ed._add_part()
    assert [p["letters"]["on"] for p in ed.collect_all()["parts"]] == [True, True]
    ed._remove_part()
    assert ed.collect()["letters"]["on"] is False


# ------------------------------------------------------------------ 3D scenes
def test_a_scene_is_one_picture_whatever_grid_was_set(ed):
    from cm1view.figures import draw as figdraw
    ed.rows.value, ed.cols.value = 2, 3
    ed.kind.value = "scene"
    s = ed.collect()
    assert (s["rows"], s["cols"]) == (1, 1) and figdraw.npanels(s) == 1
    assert s["letters"]["on"] is False
    ed.kind.value = "plan"  # (the grid stays for the other kinds)
    assert (int(ed.rows.value), int(ed.cols.value)) == (2, 3)


def test_an_older_scene_with_a_grid_draws_one_picture():
    from cm1view.figures import draw as figdraw
    s = dict(version=1, kind="scene", rows=2, cols=3, run=0, time_s=600.0, layers=[],
             size=[4.0, 3.0], runs=[dict(path="a")])
    v2, _ = figdraw.upgrade(s)
    assert [(b["rows"], b["cols"]) for b in v2["blocks"]] == [(1, 1)]
    assert [p["cell"] for p in v2["panels"]] == [[0, 0, 1, 1]]


def test_tree_shows_a_scene(ed):
    ed.kind.value = "scene"
    ed.tabs.active = 2
    assert ed.tree_list.objects[0].name.startswith("a  3D scene")
    assert ed.tree_detail.objects
    ed.tabs.active = 0


def test_a_tree_failure_does_not_stop_the_redraw(ed, monkeypatch):
    def broken(*a, **k):
        raise KeyError("x")
    jobs = []
    monkeypatch.setattr(ed, "_tree_sync", broken)
    monkeypatch.setattr(ed.v.pools["fig"], "submit", lambda *a, **k: jobs.append(a))
    ed._fire(ed._req)
    assert jobs and "panel tree" in ed.msg.object


# ------------------------------------------------------------------ figure parts' note
def test_new_part_note_names_what_exists_and_goes_away(ed):
    ed._add_part()
    assert "Panels show" in ed.part_note.object and "This part from" not in ed.part_note.object
    ed._switch_part(0)
    assert ed.part_note.object == ""


# ------------------------------------------------------------------ what follows a move
def test_step_moves_follow_the_item_or_keep_the_place():
    from cm1view.figures.tree import step_moves
    assert step_moves(["a", "b", "c"], ["b", "c"]) == {1: 0, 2: 1}  # (one gone)
    assert step_moves(["a", "b"], ["b", "a"]) == {0: 1, 1: 0}  # (swapped)
    assert step_moves([1.0, 3.0, 6.0], [1.0, 3.0, 7.0]) == {0: 0, 1: 1, 2: 2}  # (retyped)
    assert step_moves([1.0, 1.0], [1.0]) == {0: 0}  # (the same height twice)


def _grid(rows, cols, rd="none", cd="none", r=(), c=()):
    return dict(rows=rows, cols=cols, axes=(rd, cd), steps=(list(r), list(c)))


def test_panel_moves_of_each_kind_of_grid():
    from cm1view.figures.tree import panel_moves
    # runs × times, a time added: the cell's run and time stay
    was = _grid(2, 2, "runs", "times", "ab", range(2))
    panels, rows = panel_moves(was, _grid(2, 3, "runs", "times", "ab", range(3)))
    assert panels == {0: 0, 1: 1, 2: 3, 3: 4} and rows == {0: 0, 1: 1}
    # the first run taken out: the other run's panels move up
    panels, rows = panel_moves(was, _grid(1, 2, "runs", "times", "b", range(2)))
    assert panels == {2: 0, 3: 1} and rows == {1: 0}
    # one list of runs: at its run, wherever the grid puts it
    panels, _ = panel_moves(_grid(1, 3, "none", "runs", (), "abc"),
                            _grid(1, 2, "none", "runs", (), "ac"))
    assert panels == {0: 0, 2: 1}
    # no list, one more column: each panel keeps its cell
    panels, _ = panel_moves(_grid(2, 2), _grid(2, 3))
    assert panels == {0: 0, 1: 1, 2: 3, 3: 4}


def test_panel_moves_leave_numbers_that_still_hold():
    from cm1view.figures.tree import panel_moves
    assert panel_moves(None, _grid(2, 2)) == (None, None)
    assert panel_moves(_grid(2, 2), None) == (None, None)
    assert panel_moves(_grid(1, 4), _grid(2, 2)) == (None, None)  # (reshaped: reading order)
    assert panel_moves(_grid(2, 2), _grid(1, 2)) == (None, None)  # (off the grid: it waits)
    assert panel_moves(_grid(1, 3, "none", "times", (), range(3)),  # (a list by its place)
                       _grid(3, 1, "none", "times", (), range(3))) == (None, None)
    assert panel_moves(_grid(1, 2, "none", "times", (), range(2)),  # (another list)
                       _grid(1, 2, "none", "heights", (), [1.0, 3.0])) == (None, None)


def _two_contours(ed):
    """Layers: the fill, then two contour cards (card numbers 1 and 2)."""
    ed.cards[:] = ed.cards[:1]
    ed._show_cards()
    ed._add_layer("contour")
    ed._add_layer("contour")
    assert [c.type for c in ed.cards] == ["fill", "contour", "contour"]


def test_moving_a_layer_takes_its_tree_edits_and_the_choices_of_it(ed):
    _two_contours(ed)
    first, second = ed.cards[1], ed.cards[2]
    ed.edits = {"0": {"layers": {"1": {"lw": 3.0}}}}
    ed.ck_layer.value = ed.ex_layer.value = 1
    ed._move(first, 1)
    assert ed.cards[2] is first
    assert ed.collect()["edits"] == {"0": {"layers": {"2": {"lw": 3.0}}}}
    assert ed.ck_layer.value == ed.ex_layer.value == 2
    s = ed.collect()
    assert s["contour_key"]["layer"] == s["extremes"]["layer"] == 2
    assert s["layers"][2]["type"] == "contour"
    ed._move(second, -1)  # (the fill and the other contours swap: this one stays)
    assert ed.cards[0] is second and ed.ck_layer.value == 2


def test_removing_a_layer_drops_its_edits_and_renumbers_the_rest(ed):
    _two_contours(ed)
    ed.edits = {"0": {"layers": {"1": {"lw": 3.0}, "2": {"lw": 4.0}}}}
    ed.ck_layer.value = 2
    ed.ex_layer.value = 1
    ed._remove(ed.cards[1])
    assert ed.collect()["edits"] == {"0": {"layers": {"1": {"lw": 4.0}}}}
    assert ed.ck_layer.value == 1 and ed.ex_layer.value == -1


def test_a_layer_becoming_the_panels_fill_keeps_its_edits(ed):
    """Going to a figure of fields takes the first fill out of the cards, to be the first
    spec layer; going back puts it first."""
    ed.cards[:] = ed.cards[:1]
    ed._show_cards()
    ed._add_layer("contour")
    ed._add_layer("fill")
    ed._move(ed.cards[0], 1)  # (contours, fill, fill)
    assert [c.type for c in ed.cards] == ["contour", "fill", "fill"]
    ed.edits = {"0": {"layers": {"0": {"lw": 3.0}, "1": {"alpha": 0.5}}}}
    ed.ck_layer.value = 0
    ed.g_rows.value, ed.g_cols.value = "none", "fields"
    s = ed.collect()
    assert s["edits"]["0"]["layers"] == {"1": {"lw": 3.0}, "0": {"alpha": 0.5}}
    assert s["layers"][1]["type"] == "contour" and s["contour_key"]["layer"] == 1
    assert ed.ck_layer.value == 0
    ed.g_cols.value = "times"
    s = ed.collect()
    assert s["edits"]["0"]["layers"] == {"1": {"lw": 3.0}, "0": {"alpha": 0.5}}
    assert s["layers"][1]["type"] == "contour" and s["contour_key"]["layer"] == 1
    assert ed.ck_layer.value == 1


def test_a_new_column_leaves_what_names_a_panel_with_that_panel(ed):
    """A grid without lists, one more column: panel c at the start of row 2 becomes d."""
    ed.g_rows.value, ed.g_cols.value = "none", "none"
    ed.rows.value, ed.cols.value = 2, 2
    ed.edits = {"2": {"title": "edited"}}
    ed.title_ws[3].value = "last"
    ed.cards[0].w["panels"].value = "c"
    ed._add_annotation()
    ed.ann_rows[-1].w["panel"].value = "d"
    ed.lg_panel.value = 4
    ed.lg_from.value = "a, c"
    ed.cols.value = 3
    s = ed.collect()
    assert s["edits"] == {"3": {"title": "edited"}}
    assert s["titles"][4] == "last" and not any(s["titles"][:4])
    assert s["layers"][0]["panels"] == [3]
    assert s["annotations"][-1]["panel"] == 4
    assert s["legend"]["panel"] == 4 and s["legend"]["panels"] == [0, 3]


def test_a_panel_that_goes_keeps_only_its_own_references(ed):
    """An annotation in a panel no longer there keeps its letter: blank would mean all."""
    ed.g_rows.value, ed.g_cols.value = "none", "none"
    ed.rows.value, ed.cols.value = 2, 3
    ed.edits = {"2": {"title": "gone"}, "3": {"title": "stays"}}
    ed._add_annotation()
    ed.ann_rows[-1].w["panel"].value = "c"
    ed.cols.value = 2
    s = ed.collect()
    assert s["edits"] == {"2": {"title": "stays"}}
    assert s["annotations"][-1]["panel"] == 2


def test_taking_a_run_out_of_a_grid_of_runs_leaves_the_edits_on_their_run(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.add_path.value = weak
    ed._add_run()
    ed.g_rows.value, ed.g_cols.value = "runs", "times"
    ed.gg_runs.value = [0, 1]
    ed.cols.value = 2
    assert [ed.rows.value, ed.cols.value] == [2, 2]
    ed.edits = {"3": {"title": "weak, later"}, "0": {"title": "main, first"}}
    ed.row_ws[1].value = "weak"
    ed.gg_runs.value = [1]
    s = ed.collect()
    assert s["edits"] == {"1": {"title": "weak, later"}}
    assert s["row_titles"] == ["weak"]


def test_a_panel_edit_stays_when_the_kind_comes_back_on_another_grid(ed):
    ed.g_rows.value, ed.g_cols.value = "none", "none"
    ed.rows.value, ed.cols.value = 2, 2
    ed.edits = {"2": {"title": "edited"}}
    ed.kind.value = "line"
    ed.cols.value = 3
    ed.kind.value = "plan"
    assert ed.collect()["edits"] == {"2": {"title": "edited"}}


# ---------------------------------------------------------------- B3: parts, label defaults
def _label_sizes(fig):
    return {t.get_fontsize() for ax in fig.axes for _, t in getattr(ax, "_cv_labels", [])}


def _label_boxes(fig):
    """[(panel extent, [label extents])] of the laid-out figure."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    FigureCanvasAgg(fig).draw()
    r = fig.canvas.get_renderer()
    return [(ax.get_window_extent(r), [t.get_window_extent(r) for _, t in ax._cv_labels])
            for ax in fig.axes if getattr(ax, "_cv_labels", None)]


def test_whole_figure_settings_do_not_follow_the_part_shown(ed):
    ed.fmt.value, ed.dpi.value, ed.bg.value = "png", 300, "white"
    ed.sp_w.value = 0.2
    ed._add_part()
    ed.dpi.value, ed.fmt.value = 600, "pdf"
    ed.bg.value = "none"
    ed.sp_w.value = 0.3
    ed.part_sel.value = 0
    assert (ed.dpi.value, ed.fmt.value, ed.bg.value, ed.sp_w.value) == (600, "pdf", "none", 0.3)
    spec = ed.collect_all()
    assert spec["export"]["dpi"] == 600 and spec["export"]["format"] == "pdf"
    assert spec["background"] == "none" and spec["spacing"]["wspace"] == 0.3
    ed.dpi.value = 150  # (set in the first part: in the other, and in the figure)
    ed.part_sel.value = 1
    assert ed.dpi.value == 150 and ed.collect_all()["export"]["dpi"] == 150


def test_a_saved_figure_of_parts_opens_with_its_own_export(ed):
    ed._add_part()
    spec = json.loads(json.dumps(ed.collect_all(), default=float))
    spec["export"] = dict(spec["export"], dpi=450)
    spec["background"] = "none"
    spec["parts"][0]["export"] = dict(spec["parts"][0]["export"], dpi=100)  # (an older file)
    ed.set_parts(spec, 0)
    assert ed.dpi.value == 450 and ed.bg.value == "none"
    assert ed.collect_all()["export"]["dpi"] == 450


def test_the_figure_look_of_parts_does_not_follow_the_part_shown(ed):
    ed._add_part()
    ed.fsize.value = 14.0
    second = ed.collect_all()
    ed.part_sel.value = 0
    first = ed.collect_all()
    assert second["font"]["size"] == first["font"]["size"] != 14.0


def test_labels_shrink_to_fit_a_narrow_panel(ed):
    ed.g_rows.value, ed.g_cols.value = "none", "times"
    ed.rows.value, ed.cols.value = 2, 3
    ed.size_preset.value = "3.25"
    spec, data, fig = render(ed)
    assert spec["label_fit"]
    sizes = _label_sizes(fig)
    assert len(sizes) == 1 and 6.0 <= sizes.pop() < 12.0  # (one size, across the figure)
    for panel, labels in _label_boxes(fig):
        labels.sort(key=lambda b: b.x0)
        assert panel.x0 <= labels[0].x0 and labels[-1].x1 <= panel.x1
        assert all(a.x1 <= b.x0 for a, b in zip(labels, labels[1:]))


def test_labels_keep_their_size_with_room_or_when_told(ed):
    from matplotlib.text import Text
    ed.rows.value, ed.cols.value = 1, 2
    fig = render(ed)[2]
    assert _label_sizes(fig) == {12.0}
    ed.size_preset.value = "3.25"
    assert _label_sizes(render(ed)[2]) != {12.0}
    ed.label_fit.value = False
    spec, data, fig = render(ed)
    assert not spec["label_fit"] and not _label_sizes(fig)
    assert {t.get_fontsize() for t in fig.axes[0].findobj(Text) if t.get_text() == "a"} == {12.0}


def test_a_fit_that_shrinks_nothing_leaves_the_layout_alone(ed):
    """The layout it measures with must not shift the panels of the figure as saved."""
    from cm1view.figures import draw as figdraw
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    ed.rows.value, ed.cols.value = 1, 3
    ed.size_preset.value = "6.5"
    spec, data, fig = render(ed)
    assert _label_sizes(fig) == {12.0}
    fig2 = figdraw.draw(dict(spec, label_fit=False), data)
    FigureCanvasAgg(fig).draw()
    FigureCanvasAgg(fig2).draw()
    assert np.allclose([a.get_position().bounds for a in fig.axes],
                       [a.get_position().bounds for a in fig2.axes], atol=1e-9)


def test_a_saved_figure_keeps_its_label_sizes(ed):
    from cm1view.figures import spec as fg
    s = json.loads(json.dumps(ed.collect(), default=float))
    s.pop("label_fit")
    assert fg.with_defaults(s, ed.run, ed.fields, 0)["label_fit"] is False
    assert fg.with_defaults(dict(s, label_fit=True), ed.run, ed.fields, 0)["label_fit"] is True
    ed.set_parts(s)
    assert ed.label_fit.value is False


def test_a_sounding_starts_with_its_labels_clear_of_the_barbs(ed):
    ed.kind.value = "sounding"
    assert (ed.let_loc.value, ed.tl_loc.value) == ("above left", "above right")
    ed.kind.value = "plan"
    assert (ed.let_loc.value, ed.tl_loc.value) == ("lower left", "lower right")
    ed.tl_loc.value = "upper center"  # (moved by hand: it stays)
    ed.kind.value = "sounding"
    assert (ed.let_loc.value, ed.tl_loc.value) == ("above left", "upper center")


def test_the_inset_takes_the_corner_clear_of_the_traces(ed):
    from cm1view.figures import draw as figdraw
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    ed.kind.value = "sounding"
    assert ed.sk["inset_loc"].value == "clear"
    spec, data, fig = render(ed)
    FigureCanvasAgg(fig).draw()
    skew = next(a for a in fig.axes if a.child_axes)
    hx, sx = skew.child_axes[0].get_window_extent(), skew.get_window_extent()
    assert hx.y1 < 0.5 * (sx.y0 + sx.y1) and hx.x1 < 0.5 * (sx.x0 + sx.x1)  # (the demo: lower left)
    # an older figure's "auto" keeps to the top corners
    old = dict(spec, skewt=dict(spec["skewt"], inset_loc="auto"))
    fig = figdraw.draw(old, data)
    FigureCanvasAgg(fig).draw()
    skew = next(a for a in fig.axes if a.child_axes)
    hx, sx = skew.child_axes[0].get_window_extent(), skew.get_window_extent()
    assert hx.y0 > 0.5 * (sx.y0 + sx.y1)
