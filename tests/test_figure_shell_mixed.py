"""Soundings in the figure editor's new layout, panels of several kinds on one grid, and cell
spans: the grid's shape and shares, where a panel sits, a kind new to a figure, what a sounding
edit reaches, time zero with soundings, a shared layer other kinds draw."""
import copy
import json

import pytest

from cm1view.figures import draw as figdraw
from cm1view.figures.kinds import KINDS
from cm1view.figures.shell import docedit as de, gridview, nodes
from cm1view.figures.shell.gridview import grid_map


def sounding(run="r0", t=600.0):
    return dict(type="sounding", run=run, time_s=t, label="", color="",
                where=dict(kind="trk", x=0.0, y=0.0, avg=0.0))


def mixed():
    """Two plan views and a sounding panel of two soundings, in one row."""
    return dict(
        version=3, size=[9.0, 3.0], grid=dict(rows=1, cols=3),
        style=dict(letters=dict(on=True, auto=True, loc="lower left")), sections={},
        kinds=dict(plan=dict(axes=dict(xlabel="x", ylabel="y", ticklabels="outer", xstep=10.0)),
                   sounding=dict(axes=dict(xlabel="T", ylabel="p"), skewt=dict(layout="inset"))),
        runs=[dict(id="r0", path="/x/one"), dict(id="r1", path="/x/two")],
        layers=dict(l0=dict(type="fill", on=True, field="dbz", z=1.0)),
        panels=[
            dict(id=0, kind="plan", cell=[0, 0, 1, 1], run="r0", time_s=600.0, title="",
                 layers=[dict(ref="l0", over={})]),
            dict(id=1, kind="plan", cell=[0, 1, 1, 1], run="r0", time_s=1200.0, title="",
                 layers=[dict(ref="l0", over={})]),
            dict(id=2, kind="sounding", cell=[0, 2, 1, 1], run=None, time_s=None, title="",
                 layers=[sounding(), sounding("r1")])])


def panel(doc, pid):
    return de.panel_by_id(doc, pid)


# ------------------------------------------------------------------ the grid
def test_a_grid_grows_and_shrinks_past_a_panel():
    doc = mixed()
    assert de.set_grid(doc, 2, 3) is None
    assert de.free_cells(doc) == [(1, 0), (1, 1), (1, 2)]
    said = de.set_grid(doc, 2, 2)  # (c moves into the free row, it isn't refused)
    assert "free cell" in said and doc["grid"]["cols"] == 2
    assert len(doc["panels"]) == 3 and not doc.get(de.OFF_GRID)


def test_panels_with_no_room_are_set_aside_and_come_back():
    doc = mixed()
    n = len(doc["panels"])
    ids = {p["id"] for p in doc["panels"]}
    said = de.set_grid(doc, 1, 1)
    assert "set aside" in said and len(doc["panels"]) == 1 and len(doc[de.OFF_GRID]) == n - 1
    assert de.next_panel_id(doc) > max(ids)  # (no new panel takes the id of one set aside)
    said = de.set_grid(doc, 1, n)
    assert "Back on the grid" in said and de.OFF_GRID not in doc
    assert {p["id"] for p in doc["panels"]} == ids
    assert len({tuple(p["cell"][:2]) for p in doc["panels"]}) == n


def test_a_lone_panel_past_a_smaller_grid_moves_into_it():
    doc = mixed()
    doc["panels"] = doc["panels"][-1:]
    r, c = de.grid_shape(doc)
    doc["panels"][0]["cell"] = [r - 1, c - 1, 1, 1]
    de.set_grid(doc, 1, 1)
    assert doc["panels"][0]["cell"] == [0, 0, 1, 1] and de.OFF_GRID not in doc


def test_a_panel_over_the_new_edge_is_cut_to_it():
    doc = mixed()
    doc["panels"] = doc["panels"][:1]
    de.set_grid(doc, 2, 3)
    doc["panels"][0]["cell"] = [0, 0, 2, 3]
    de.set_grid(doc, 1, 2)
    assert doc["panels"][0]["cell"] == [0, 0, 1, 2]


def test_panels_set_aside_can_be_brought_back_or_removed():
    doc = mixed()
    n = len(doc["panels"])
    de.set_grid(doc, 1, 1)
    de.bring_back(doc)
    assert len(doc["panels"]) == n and de.OFF_GRID not in doc
    de.set_grid(doc, 1, 1)
    de.forget_aside(doc)
    assert len(doc["panels"]) == 1 and de.OFF_GRID not in doc


def test_shares_are_checked_and_follow_the_grid():
    doc = mixed()
    assert de.set_shares(doc, "widths", [2.0, 1.0, 1.0]) is None
    assert "needs 3" in de.set_shares(doc, "widths", [2.0, 1.0])
    assert "above 0" in de.set_shares(doc, "widths", [2.0, 0.0, 1.0])
    assert "needs 1" in de.set_shares(doc, "heights", [1.0, 1.0])
    de.set_grid(doc, 1, 4)
    assert doc["grid"]["widths"] == [2.0, 1.0, 1.0, pytest.approx(4.0 / 3.0)]
    de.set_shares(doc, "widths", [])
    assert "widths" not in doc["grid"]
    assert figdraw.resolve(doc)["blocks"] == [dict(rows=1, cols=4)]


def test_the_next_cell_is_free_or_grows_the_grid():
    doc = mixed()
    assert de.next_cell(doc) == (0, 3) and doc["grid"]["cols"] == 4  # (one row: another column)
    de.set_grid(doc, 2, 4)
    assert de.next_cell(doc) == (0, 3)
    assert de.next_cell(doc, "row") == (2, 0) and doc["grid"]["rows"] == 3
    assert de.next_cell(doc, "col") == (0, 4) and doc["grid"]["cols"] == 5


# ------------------------------------------------------------------ where a panel sits
def test_a_panel_spans_cells_unless_another_is_there():
    doc = mixed()
    de.set_grid(doc, 2, 3)
    assert de.place_panel(doc, 2, [0, 2, 2, 1]) is None
    assert panel(doc, 2)["cell"] == [0, 2, 2, 1]
    assert de.free_cells(doc) == [(1, 0), (1, 1)]
    assert "b is there" in de.place_problem(doc, 0, [0, 0, 1, 2])
    assert "off the grid" in de.place_problem(doc, 0, [0, 0, 3, 1])
    assert panel(doc, 0)["cell"] == [0, 0, 1, 1]


def test_a_panel_of_the_same_shape_swaps_places_and_letters_follow():
    doc = mixed()
    assert de.place_panel(doc, 0, [0, 2, 1, 1]) is None
    assert panel(doc, 0)["cell"] == [0, 2, 1, 1] and panel(doc, 2)["cell"] == [0, 0, 1, 1]
    assert nodes.letters(doc) == {2: "a", 1: "b", 0: "c"}


def test_moving_a_panel_ends_letters_a_conversion_held():
    doc = mixed()
    panel(doc, 1)["letter"] = 5
    de.place_panel(doc, 2, [0, 2, 1, 1])
    assert "letter" not in panel(doc, 1)


def test_grid_map_shows_a_span_of_a_mixed_figure():
    doc = mixed()
    de.set_grid(doc, 2, 3)
    de.place_panel(doc, 2, [0, 2, 2, 1])
    assert 'rowspan="2"' in grid_map(doc).object


def test_copy_and_remove_any_kind():
    doc = mixed()
    new = de.copy_panel(doc, 2, de.next_cell(doc))
    assert new["id"] == 3 and new["cell"] == [0, 3, 1, 1] and new["layers"] == panel(doc, 2)["layers"]
    new["layers"][0]["time_s"] = 1.0
    assert panel(doc, 2)["layers"][0]["time_s"] == 600.0
    de.remove_panel(doc, 3)
    assert [p["id"] for p in doc["panels"]] == [0, 1, 2]
    for pid in (1, 2):
        de.remove_panel(doc, pid)
    assert doc["style"]["letters"]["on"] is False  # (one panel, and letters following the count)


# ------------------------------------------------------------------ a kind new to a figure
def test_a_new_kind_takes_its_settings_and_the_look_of_the_axes_there():
    doc = mixed()
    del doc["kinds"]["sounding"]
    doc["kinds"]["plan"]["axes"]["minor"] = True
    de.seed_kind(doc, "sounding", dict(axes=dict(ticks=True), skewt=dict(layout="side")),
                 KINDS["sounding"].labels)
    k = doc["kinds"]["sounding"]
    assert k["skewt"] == dict(layout="side") and k["axes"]["minor"] is True
    assert k["axes"]["ylabel"] == "pressure (hPa)" and "xstep" not in k["axes"]
    was = copy.deepcopy(k)
    de.seed_kind(doc, "sounding", dict(skewt=dict(layout="hodo")), ("", ""))
    assert doc["kinds"]["sounding"] == was  # (already there: as it is)


def test_a_new_panels_labels_go_where_its_kind_has_them_unless_moved_by_hand():
    every = {KINDS["plan"], KINDS["sounding"]}
    doc = mixed()
    p = dict()
    de.label_places(doc, p, KINDS["sounding"], every)
    assert p["opts"]["letters"] == dict(loc="above left")
    doc["style"]["letters"]["loc"] = "upper right"
    p = dict()
    de.label_places(doc, p, KINDS["sounding"], every)
    assert "letters" not in p["opts"]


def test_the_first_plan_view_of_a_figure_gets_layers_and_a_section():
    doc = mixed()
    doc.update(layers={}, panels=[p for p in doc["panels"] if p["kind"] == "sounding"])
    p = de.plan_panel(doc, (0, 0), "r0", 60.0, [dict(type="fill", field="dbz")], dict(orient="x"))
    assert p["layers"] == [dict(ref="l0", over={})] and doc["layers"]["l0"]["field"] == "dbz"
    assert p["section"] == "s0" and doc["sections"]["s0"] == dict(orient="x")
    assert (p["run"], p["time_s"]) == ("r0", 60.0)


def test_another_plan_view_is_like_the_last():
    doc = mixed()
    panel(doc, 1)["title"] = "b"
    p = de.plan_panel(doc, de.next_cell(doc), "r1", 5.0)
    assert (p["run"], p["time_s"], p["title"]) == ("r0", 1200.0, "")
    assert p["layers"] == [dict(ref="l0", over={})]


# ------------------------------------------------------------------ soundings
def test_a_sounding_moves_to_another_panel():
    doc = mixed()
    new = de.copy_panel(doc, 2, de.next_cell(doc))
    de.move_entry(doc, 2, 1, new["id"])
    assert [x["run"] for x in panel(doc, 2)["layers"]] == ["r0"]
    assert [x["run"] for x in new["layers"]] == ["r0", "r1", "r1"]


def test_a_soundings_name_says_where_and_when():
    assert nodes.layer_name(sounding()) == "Sounding · storm · 10 min"
    assert nodes.layer_name(dict(sounding(), label="Inflow")) == "Sounding · Inflow · 10 min"


def test_the_run_of_a_sounding_counts_as_used():
    assert nodes.runs_used(mixed())["r1"] == [2]


def test_time_zero_moves_soundings_measured_from_the_first():
    doc = mixed()
    de.set_t0(doc, "r1", 10.0)
    assert [x["time_s"] for x in panel(doc, 2)["layers"]] == [600.0, 1200.0]
    assert panel(doc, 0)["time_s"] == 600.0  # (the panels' list: all of r0)
    doc = mixed()
    de.set_t0(doc, "r0", 5.0)
    assert [x["time_s"] for x in panel(doc, 2)["layers"]] == [600.0, 300.0]


def test_time_zero_moves_soundings_of_a_run_by_output_number_not_at_all():
    doc = mixed()
    doc["runs"][1]["outputs_s"] = [0.0, 300.0]
    de.set_t0(doc, "r1", 10.0)
    assert [x["time_s"] for x in panel(doc, 2)["layers"]] == [600.0, 600.0]


def test_a_soundings_automatic_size_follows_layout_grid_and_table():
    doc = mixed()
    assert de.sounding_size(doc) is None  # (other kinds are there)
    doc["panels"] = [panel(doc, 2)]
    de.place_panel(doc, 2, [0, 0, 1, 1])
    de.set_grid(doc, 1, 2)
    assert de.sounding_size(doc) == (10.5, 5.0)
    doc["kinds"]["sounding"]["skewt"]["layout"] = "side"
    assert de.sounding_size(doc) == (16.9, 5.0)
    doc["kinds"]["sounding"]["skewt"]["table"] = ["cape"]
    assert de.sounding_size(doc) == (16.9, pytest.approx(5.95))


# ------------------------------------------------------------------ a layer of several kinds
def test_a_kind_can_keep_a_layer_apart():
    doc = mixed()
    doc["panels"].append(dict(id=3, kind="xsec", cell=[0, 2, 1, 1], run="r0", time_s=1.0,
                              layers=[dict(ref="l0", over=dict(vmax=9.0))]))
    assert [p["id"] for p in de.other_kinds_with(doc, "plan", "l0")] == [3]
    panel(doc, 1)["layers"][0]["over"] = dict(vmin=2.0)
    new = de.split_shared(doc, "plan", "l0")
    assert panel(doc, 3)["layers"] == [dict(ref="l0", over=dict(vmax=9.0))]
    assert panel(doc, 1)["layers"] == [dict(ref=new, over=dict(vmin=2.0))]
    assert de.other_kinds_with(doc, "plan", new) == []
    de.write_shared(doc, new, dict(vmax=70.0))
    assert "vmax" not in doc["layers"]["l0"]


# ------------------------------------------------------------------ on the demo run
class _Now:
    """A pool that runs what it is given at once."""

    def submit(self, fn, *a):
        fn(*a)

    def shutdown(self, *a, **kw):
        pass


@pytest.fixture
def shell(reg, monkeypatch):
    """The new layout showing the demo's example figure, drawing as it is asked."""
    monkeypatch.setenv("CM1VIEW_FIGURE_SHELL", "1")
    from cm1view.viewer import app as A
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    v._schedule = lambda f: f()
    v.pools["fig"].shutdown(wait=False)
    v.pools["fig"] = _Now()
    v.tslider.value = min(4, len(run.times) - 1)
    v.figed.shell.open()
    yield v.figed.shell
    v.close()


def _named(shell, name):
    """The widget called `name` in the inspector, however deep."""
    for w in shell.inspector.body.select():
        if getattr(w, "name", None) == name and hasattr(w, "value"):
            return w
    raise AssertionError(f"no {name}")


def _drew(shell):
    shell.request(force=True, delay=False)
    assert "Could not draw" not in shell.status.object
    return shell.status.object


def test_a_sounding_panel_joins_a_grid_of_plan_views(shell):
    n = len(shell.doc["panels"])
    p = shell.inspector.grid.add_panel("sounding", "new column")
    assert shell.node == f"panel:{p['id']}" and len(shell.doc["panels"]) == n + 1
    assert set(shell.doc["kinds"]) >= {"plan", "sounding"}
    assert p["layers"][0]["type"] == "sounding" and p["opts"]["letters"]["loc"] == "above left"
    assert f"{n + 1} panels" in _drew(shell)
    assert p["id"] in shell._boxes
    res = figdraw.resolve(shell.doc)
    q = next(x for x in res["panels"] if x["id"] == p["id"])
    assert figdraw.panel_view(res, q)["axes"]["ylabel"] == "pressure (hPa)"
    r0 = next(x for x in res["panels"] if x["kind"] == "plan")
    assert figdraw.panel_view(res, r0)["axes"]["ylabel"] == "y (km)"
    shell.undo()
    assert len(shell.doc["panels"]) == n


def test_every_node_of_a_mixed_figure_shows(shell):
    shell.inspector.grid.add_panel("sounding", "new column")
    for row in shell.tree.items:
        shell.select(row["id"])
        assert shell.inspector.body.objects, row["id"]


def test_a_plan_view_joins_a_figure_of_soundings(shell):
    shell.close()
    shell.ed.kind.value = "sounding"
    shell.open()
    p = shell.inspector.grid.add_panel("plan", "new column")
    assert p["layers"] and p["section"] in shell.doc["sections"]
    assert p["opts"]["letters"]["loc"] == "lower left"
    assert "2 panels" in _drew(shell)


def test_the_place_boxes_move_and_span_a_panel(shell):
    p = shell.inspector.grid.add_panel("sounding", "new column")
    _named(shell, "Rows tall").value = 2
    assert de.panel_by_id(shell.doc, p["id"])["cell"][2] == 2
    _drew(shell)
    assert shell._boxes[p["id"]][3] - shell._boxes[p["id"]][2] > \
        1.3 * (shell._boxes[0][3] - shell._boxes[0][2])


def test_the_place_boxes_refuse_what_cant_be(shell):
    shell.select("panel:0")
    was = de.panel_by_id(shell.doc, 0)["cell"]
    _named(shell, "Columns wide").value = 2
    assert de.panel_by_id(shell.doc, 0)["cell"] == was
    assert any("is there" in str(getattr(o, "object", "")) for o in shell.inspector.body.select())


def test_changing_a_panels_type_keeps_its_cell(shell):
    shell.select("figure")
    pid = shell.doc["panels"][0]["id"]
    was = list(de.panel_by_id(shell.doc, pid)["cell"])
    n = len(shell.doc["panels"])
    made = shell.inspector.grid.set_kind([pid], "sounding")
    assert made[0]["kind"] == "sounding" and made[0]["cell"] == was
    assert len(shell.doc["panels"]) == n
    shell.undo()
    assert de.panel_by_id(shell.doc, pid)["kind"] != "sounding"


def test_the_figure_type_changes_every_panel(shell):
    shell.select("figure")
    n = len(shell.doc["panels"])
    _named(shell, "Figure type").value = "sounding"
    assert {p["kind"] for p in shell.doc["panels"]} == {"sounding"}
    assert len(shell.doc["panels"]) == n
    assert _named(shell, "Add a panel of").value == "sounding"
    _named(shell, "Rows").value = shell.doc["grid"]["rows"] + 1  # (no error, no going back)
    assert shell.doc["grid"]["rows"] == _named(shell, "Rows").value
    k = len(de.free_cells(shell.doc))
    shell.inspector.grid.fill_empty("sounding")
    assert len(shell.doc["panels"]) == n + k and not de.free_cells(shell.doc)


def test_the_figure_type_reaches_panels_set_aside_and_keeps_times(shell):
    shell.select("figure")
    n = len(shell.doc["panels"])
    assert n > 1
    last = max(shell.doc["panels"], key=lambda p: p["cell"][:2])
    when = gridview.moment_of(last)[1]
    _named(shell, "Rows").value = 1
    _named(shell, "Columns").value = 1
    assert shell.doc.get(de.OFF_GRID)
    _named(shell, "Figure type").value = "sounding"
    assert {p["kind"] for p in shell.doc[de.OFF_GRID]} == {"sounding"}
    _named(shell, "Rows").value = n
    assert de.OFF_GRID not in shell.doc and len(shell.doc["panels"]) == n
    assert {p["kind"] for p in shell.doc["panels"]} == {"sounding"}
    assert when in [gridview.moment_of(p)[1] for p in shell.doc["panels"]]


def test_the_grid_boxes_on_the_figure_node(shell):
    shell.select("figure")
    n = len(shell._hist)
    panels = len(shell.doc["panels"])
    _named(shell, "Columns").value = 1
    _named(shell, "Rows").value = 1
    assert shell.doc["grid"] == dict(shell.doc["grid"], rows=1, cols=1)  # (it takes what's asked)
    assert len(shell.doc["panels"]) == 1
    assert len(shell.doc[de.OFF_GRID]) == panels - 1
    assert "not drawn" in " ".join(str(getattr(o, "object", ""))
                                   for o in shell.inspector.body.select())
    while len(shell._hist) > n:
        shell.undo()
    assert len(shell.doc["panels"]) == panels
    cols = shell.doc["grid"]["cols"]
    _named(shell, "Columns").value = cols + 1
    assert shell.doc["grid"]["cols"] == cols + 1
    _named(shell, "Column widths").value = ", ".join(["1"] * cols + ["2"])
    assert shell.doc["grid"]["widths"][-1] == 2.0
    _drew(shell)
    assert shell.can_follow() is False  # (its size doesn't follow panels with shares)


def test_a_soundings_card_edits_its_entry(shell):
    p = shell.inspector.grid.add_panel("sounding", "new column")
    pid = p["id"]
    shell.select(f"layer:{pid}:0")
    time = _named(shell, "Time")
    new = [v for v in time.options.values() if v != time.value][0]
    time.value = new
    assert de.panel_by_id(shell.doc, pid)["layers"][0]["time_s"] == new
    _named(shell, "Where").value = "pt"
    entry = de.panel_by_id(shell.doc, pid)["layers"][0]
    assert entry["where"]["kind"] == "pt" and "panel" not in entry and entry["run"] == "r0"
    shell.undo()
    assert de.panel_by_id(shell.doc, pid)["layers"][0]["where"]["kind"] == "trk"


def test_a_time_that_is_no_output_stays_until_another_is_picked(shell):
    p = shell.inspector.grid.add_panel("sounding", "new column")
    pid = p["id"]
    shell.edit(lambda d: de.panel_by_id(d, pid)["layers"][0].update(time_s=4001.0))
    shell.select(f"layer:{pid}:0")
    assert _named(shell, "Time").value == 4001.0
    assert de.panel_by_id(shell.doc, pid)["layers"][0]["time_s"] == 4001.0


def test_the_panel_adds_copies_moves_and_removes_soundings(shell):
    ins = shell.inspector
    p = ins.grid.add_panel("sounding", "new column")
    pid = p["id"]
    ins.panes["sounding"].add_entry(pid)
    assert len(de.panel_by_id(shell.doc, pid)["layers"]) == 2
    other = ins.panes["sounding"].add_panel()
    shell.select(f"layer:{pid}:1")
    _named(shell, "In panel").value = other["id"]
    assert shell.node == f"panel:{other['id']}"
    assert len(de.panel_by_id(shell.doc, other["id"])["layers"]) == 2
    _drew(shell)


def test_the_kinds_sections_follow_the_layout_and_write_the_kind(shell):
    p = shell.inspector.grid.add_panel("sounding", "new column")
    shell.select("kind:sounding")

    def sections():
        return [c.title for c in shell.inspector.body.objects if hasattr(c, "collapsed")]

    assert {"Skew-T", "Hodograph", "Sounding panels"} <= set(sections())
    for c in shell.inspector.body.objects:
        if getattr(c, "title", "") == "Sounding panels":
            c.collapsed = False
    _named(shell, "Sounding layout").value = "skewt"
    assert shell.doc["kinds"]["sounding"]["skewt"]["layout"] == "skewt"
    assert "Hodograph" not in sections()
    assert "skewt" not in (de.panel_by_id(shell.doc, p["id"]).get("opts") or {})
    assert figdraw.resolve(shell.doc)["skewt"]["layout"] == "skewt"


def test_a_panels_own_look_stays_in_it(shell):
    ins = shell.inspector
    a = ins.grid.add_panel("sounding", "new column")
    b = ins.grid.copy_panel(a["id"])
    shell.select(f"panel:{a['id']}")
    for c in ins.body.objects:
        if getattr(c, "title", "") == "Skew-T":
            c.collapsed = False
    _named(shell, "Bottom (hPa)").value = 900.0
    res = figdraw.resolve(shell.doc)

    def view(pid):
        return figdraw.panel_view(res, next(x for x in res["panels"] if x["id"] == pid))["skewt"]

    assert view(a["id"])["pmax"] == 900.0 and view(b["id"])["pmax"] == 1000.0
    _drew(shell)


def test_a_panels_chips_say_which_of_two_settings_alike(shell):
    p = shell.inspector.grid.add_panel("sounding", "new column")
    names = [o.name for o in shell.inspector.body.select() if str(getattr(o, "name", "")).startswith("↺")]
    assert {"↺ Letter Where", "↺ Time label Where"} <= set(names)
    assert p["opts"]["letters"]["loc"] == "above left"


def test_a_figure_of_soundings_keeps_its_size_until_what_it_depends_on_changes(shell):
    shell.close()
    shell.ed.kind.value = "sounding"
    shell.open()
    shell.doc.update(size=[5.5, 5.5], size_auto=True)
    shell.select("panel:0")
    _named(shell, "Title").value = "x"
    assert shell.doc["size"] == [5.5, 5.5]
    shell.inspector.panes["sounding"].add_panel()
    assert shell.doc["size"] == [10.5, 5.0]


def test_a_shared_layer_of_another_kind_says_so_on_all_plan_views(shell):
    lid = next(iter(shell.doc["layers"]))
    shell.edit(lambda d: d["panels"].append(dict(
        id=99, kind="xsec", cell=list(de.next_cell(d)) + [1, 1], run="r0", time_s=3600.0, title="",
        layers=[dict(ref=lid, over={})], insets=[], section=None)))
    shell.select("kind:plan")
    said = [o for o in shell.inspector.body.select() if "another kind" in str(getattr(o, "object", ""))]
    assert said


def test_panels_of_a_kind_keep_outer_tick_labels_of_their_own(shell):
    shell.inspector.grid.add_panel("sounding", "new column")
    res = figdraw.resolve(shell.doc)
    data = shell.ed.data.panel_data(json.loads(json.dumps(shell.doc, default=float)))
    fig = figdraw.draw(json.loads(json.dumps(shell.doc, default=float)), data)
    axes = fig._cv_axes
    plan = [p for p in res["panels"] if p["kind"] == "plan"]
    inner = next(p for p in plan if p["cell"][1] > 0)
    outer = next(p for p in plan if p["cell"][1] == 0)
    assert axes[outer["id"]].get_ylabel() and not axes[inner["id"]].get_ylabel()
    snd = next(p for p in res["panels"] if p["kind"] == "sounding")
    assert axes[snd["id"]].get_ylabel() == "pressure (hPa)"
