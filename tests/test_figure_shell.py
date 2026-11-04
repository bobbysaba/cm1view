"""The figure editor's new layout (figures/shell): the tree of a document, picking in it and in
the preview, edits, undo, and the switch that shows it."""
import pytest

from cm1view.figures.shell import nodes


def small_doc():
    fill = dict(type="fill", field="dbz", run=None)
    return dict(
        version=3, size=[8.0, 6.0], grid=dict(rows=1, cols=3), style={}, kinds={}, sections={},
        runs=[dict(id="r0", path="/x/one"), dict(id="r1", path="/x/two", label="Two"),
              dict(id="r2", path="/x/three")],
        layers={"l0": fill},
        panels=[
            dict(id=7, kind="sounding", cell=[0, 2, 1, 1], run=None, time_s=None, title="",
                 layers=[dict(type="sounding", label="Inflow", run="r0")]),
            dict(id=0, kind="plan", cell=[0, 0, 1, 1], run="r0", time_s=600.0, title="Early",
                 layers=[dict(ref="l0", over=dict(field="w"))]),
            dict(id=1, kind="plan", cell=[0, 1, 1, 1], run="r1", time_s=1200.0, title="",
                 layers=[dict(ref="l0", over={})], letter=25)])


def test_tree_rows_in_reading_order_under_their_kind():
    rows = nodes.tree_items(small_doc())
    assert [(r["id"], r["depth"]) for r in rows] == [
        ("figure", 0), ("runs", 0), ("kind:plan", 0), ("panel:0", 1), ("layer:0:0", 2),
        ("panel:1", 1), ("layer:1:0", 2), ("kind:sounding", 0), ("panel:7", 1),
        ("layer:7:0", 2)]
    labels = {r["id"]: r["label"] for r in rows}
    assert labels["runs"] == "Runs (3)"
    assert labels["kind:plan"] == "All plan views (2)"
    assert labels["panel:0"] == "a  one · 10 min · “Early”"
    assert labels["panel:1"].startswith("z  Two · 20 min")  # (its own letter)
    assert labels["layer:0:0"] == "Fill · w"  # (what differs in this panel)
    assert labels["layer:7:0"] == "Sounding · Inflow"


def test_letters_follow_the_reading_order_not_the_list():
    assert nodes.letters(small_doc()) == {0: "a", 1: "z", 7: "c"}


def test_what_a_node_speaks_for():
    doc = small_doc()
    assert nodes.outlined(doc, "figure") == nodes.outlined(doc, "runs") == []
    assert sorted(nodes.outlined(doc, "kind:plan")) == [0, 1]
    assert nodes.outlined(doc, "panel:7") == nodes.outlined(doc, "layer:7:0") == [7]
    assert nodes.scope(doc, "kind:plan") == "Applies to all plan views (2)"
    assert nodes.scope(doc, "panel:0") == "Applies to panel a only"
    assert nodes.scope(doc, "layer:1:0") == "Applies to panel z only"
    assert nodes.scope(doc, "figure") == "Applies to the whole figure"


@pytest.mark.parametrize("node, there", [
    ("figure", True), ("runs", True), ("kind:plan", True), ("kind:th", False), ("panel:7", True),
    ("panel:8", False), ("layer:0:0", True), ("layer:0:1", False), ("layer:8:0", False)])
def test_still_there(node, there):
    assert nodes.still_there(small_doc(), node) is there


def test_runs_used_by_panels_and_their_layers():
    doc = small_doc()
    doc["panels"][2]["layers"][0]["over"] = dict(minus=dict(run="r2"))
    assert nodes.runs_used(doc) == {"r0": [7, 0], "r1": [1], "r2": [1]}


def test_pick_at():
    boxes = {3: [0.0, 0.4, 0.0, 1.0], 4: [0.6, 1.0, 0.0, 1.0]}
    assert nodes.pick_at(boxes, 0.2, 0.5) == 3
    assert nodes.pick_at(boxes, 0.7, 0.5) == 4
    assert nodes.pick_at(boxes, 0.5, 0.5) is None  # (between them)


def test_grid_map_shows_spans_and_empty_cells():
    from cm1view.figures.shell.inspector import grid_map
    doc = small_doc()
    doc["grid"] = dict(rows=2, cols=3)
    doc["panels"][1]["cell"] = [0, 0, 2, 1]
    text = grid_map(doc).object
    assert 'rowspan="2"' in text
    assert text.count("<tr>") == 2
    assert text.count("<td") == 5 and text.count(">·<") == 2  # (a spans two rows; two empty)


def test_a_preview_doc_only_touches_a_scene():
    from cm1view.figures.shell.frame import preview_doc, preview_dpi
    doc = small_doc()
    assert preview_doc(doc, 100.0) is doc
    doc["kinds"] = dict(scene=dict(scene3d=dict(zoom=1.0)))
    out = preview_doc(doc, 100.0)
    assert out["kinds"]["scene"]["scene3d"] == dict(zoom=1.0, dpi=100.0)
    assert doc["kinds"]["scene"]["scene3d"] == dict(zoom=1.0)
    assert preview_dpi(dict(size=[8.0, 6.0], export=dict(dpi=100))) == 100.0
    assert preview_dpi(dict(size=[1.0, 1.0], export=dict(dpi=2000))) == 1100.0


# ------------------------------------------------------------------ on the demo run
class _Now:
    """A pool that runs what it is given at once."""

    def submit(self, fn, *a):
        fn(*a)

    def shutdown(self, *a, **kw):
        pass


@pytest.fixture
def shell(reg, monkeypatch):
    """The new layout showing the demo's example figure, drawing as it is asked (not in the
    background)."""
    from cm1view.viewer import app as A
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    v._schedule = lambda f: f()
    v.pools["fig"].shutdown(wait=False)
    v.pools["fig"] = _Now()
    v.figed.shell.open()
    yield v.figed.shell
    v.close()


def _new_figure(shell, kind):
    ed = shell.ed
    ed.open_quick()
    ed.qs_kind.value = kind
    ed._quick_make()


def test_open_shows_the_figure_there(shell):
    assert shell.showing and shell.panel.visible
    assert shell.doc["version"] == 3
    assert shell.image.src.startswith("data:image/png")
    assert "6 panels" in shell.status.object
    assert set(shell._boxes) == {p["id"] for p in shell.doc["panels"]}
    assert shell.tree.sel == "figure" and shell.image.marks == {}


def test_a_click_in_the_preview_picks_the_panel(shell):
    x0, x1, y0, y1 = shell._boxes[4]
    shell.image.click = [0.5 * (x0 + x1), 0.5 * (y0 + y1), 1]
    assert shell.node == shell.tree.sel == "panel:4"
    assert shell.image.marks == {"4": shell._boxes[4]}
    assert "Panel" in shell.inspector.head.object and "panel e only" in shell.inspector.head.object
    shell.image.click = [0.0, 0.999, 2]  # (off every panel: the figure)
    assert shell.node == "figure" and shell.image.marks == {}


def test_a_click_in_the_tree_picks_the_node(shell):
    shell.tree.pick = ["kind:plan", 1]
    assert shell.node == "kind:plan" and len(shell.image.marks) == 6
    shell.tree.pick = ["runs", 2]
    assert shell.image.marks == {}
    assert "every panel" in shell.inspector.head.object


def test_every_node_shows(shell):
    for row in shell.tree.items:
        shell.select(row["id"])
        assert shell.inspector.body.objects, row["id"]


def _named(col, name):
    """The widget called `name` in a column, however deep."""
    for w in col.select():
        if getattr(w, "name", None) == name and hasattr(w, "value"):
            return w
    raise AssertionError(f"no {name}")


def test_edits_undo_and_redo_with_what_was_picked(shell):
    shell.select("panel:1")
    _named(shell.inspector.body, "Title").value = " North "
    pan = next(p for p in shell.doc["panels"] if p["id"] == 1)
    assert pan["title"] == "North"
    assert any("North" in r["label"] for r in shell.tree.items if r["id"] == "panel:1")
    assert not shell.undo_btn.disabled and shell.redo_btn.disabled
    shell.select("figure")
    shell.undo()
    assert next(p for p in shell.doc["panels"] if p["id"] == 1)["title"] == ""
    assert shell.node == "panel:1"  # (where the edit was made)
    assert shell.undo_btn.disabled and not shell.redo_btn.disabled
    assert _named(shell.inspector.body, "Title").value == ""
    shell.redo()
    assert next(p for p in shell.doc["panels"] if p["id"] == 1)["title"] == "North"
    assert _named(shell.inspector.body, "Title").value == "North"


def test_figure_size_and_title(shell):
    _named(shell.inspector.body, "Width (in)").value = 5.0
    assert shell.doc["size"][0] == 5.0 and shell.doc["size_auto"] is False
    _named(shell.inspector.body, "Figure title").value = "Storm"
    assert shell.doc["suptitle"] == "Storm"
    assert shell._png[1][0] / shell._png[2] < 5.5  # (drawn at that width)


def test_runs_are_a_tree_item(shell):
    shell.select("runs")
    _named(shell.inspector.body, "Label").value = "Control"
    assert shell.doc["runs"][0]["label"] == "Control"
    _named(shell.inspector.body, "Time zero (min)").value = 5.0
    assert shell.doc["runs"][0]["t0_min"] == 5.0
    rm = next(w for w in shell.inspector.body.select() if getattr(w, "name", "") == "✕")
    assert rm.disabled  # (in use, and the only one)


def test_add_and_remove_a_run(shell, demo_run):
    import os
    other = os.path.join(os.path.dirname(demo_run), "supercell_weak")
    shell.select("runs")
    shell.inspector._add_run(other)
    assert [r["path"] for r in shell.doc["runs"]][-1] == other
    assert shell.tree.items[1]["label"] == "Runs (2)"
    assert shell.node == "runs"
    rms = [w for w in shell.inspector.body.select() if getattr(w, "name", "") == "✕"]
    assert [b.disabled for b in rms] == [True, False]  # (the first in use)
    rms[1].clicks += 1
    assert len(shell.doc["runs"]) == 1


def test_leaving_the_workspace_and_returning_keeps_the_edits(shell):
    shell.edit(lambda d: d.update(suptitle="Kept"))
    shell.open()
    assert shell.doc["suptitle"] == "Kept"


def test_what_the_data_asks_of_the_editor_reaches_the_shell(shell):
    gen = shell.v.gen["fig"]
    shell.ed.request(force=True, delay=False)  # (a series coming in)
    assert shell.v.gen["fig"] == gen + 1
    shell.ed._status("from the data")
    assert "from the data" in shell.status.object


def test_live_off_waits_for_redraw(shell):
    shell.auto.value = False
    src = shell.image.src
    shell.edit(lambda d: d.update(suptitle="Later"))
    assert shell.image.src == src
    shell.update.clicks += 1
    assert shell.image.src != src


def test_panel_boxes_are_the_panels_places_in_the_image(shell):
    b = shell._boxes
    assert all(0.0 <= x[0] < x[1] <= 1.0 and 0.0 <= x[2] < x[3] <= 1.0 for x in b.values())
    assert b[0][1] < b[1][0] < b[1][1] < b[2][0]  # (a b c, left to right)
    assert b[0][3] < b[3][2]  # (d under a)
    assert abs(b[0][0] - b[3][0]) < 1e-6


def test_every_kind_opens_and_every_node_shows(shell):
    for kind in ("xsec", "sounding", "profile", "dist", "joint", "azim", "table", "line", "th"):
        _new_figure(shell, kind)
        assert shell.doc["panels"] or kind == "th", kind
        assert "Could not draw" not in shell.status.object, kind
        for row in shell.tree.items:
            shell.select(row["id"])
            assert shell.inspector.body.objects, (kind, row["id"])


def test_the_plain_code_box_holds_the_same_code():
    import panel as pn
    from cm1view.figures.shell.looks import code_extra
    editor = pn.widgets.TextInput(value="x = 1")
    plain, box = code_extra({"code.text": editor})
    assert plain.value == "x = 1"
    box.value = True
    assert plain.visible and not editor.visible
    plain.value = "y = 2"
    assert editor.value == "y = 2"
    box.value = False
    assert editor.visible and not plain.visible

