"""3D scenes, annotations and placing by clicks in the figure editor's new layout: the document's
scene settings at each scope, what panels going or being copied does to annotations, the sums of
placing, and the panes driven by their widgets."""
import time
from types import SimpleNamespace

import pytest

from cm1view.figures import click as C, draw as figdraw
from cm1view.figures.shell import docedit as de, looks, nodes
from cm1view.figures.shell.gridview import ADDABLE
from cm1view.figures.shell.placing import fraction_entry


def doc_of(*panels, **more):
    return dict(version=3, size=[6.0, 3.0], grid=dict(rows=1, cols=max(len(panels), 1)), style={},
                kinds={}, runs=[dict(id="r0", path="/x/one", t0_min=0.0, label="a")], sections={},
                layers={}, panels=list(panels), annotations=[], **more)


def panel(pid, kind="scene", c=0):
    return dict(id=pid, kind=kind, cell=[0, c, 1, 1], run="r0", time_s=600.0, title="", layers=[])


# ------------------------------------------------------------------ a scene's settings
def test_the_only_scenes_settings_are_the_kinds():
    doc = doc_of(panel(0))
    de.write_scene(doc, 0, "exag", 3.0)
    assert doc["kinds"]["scene"]["scene3d"]["exag"] == 3.0
    assert "opts" not in doc["panels"][0]
    assert de.scene_block(doc, 0)["exag"] == 3.0


def test_with_two_scenes_a_panels_settings_are_its_own_and_can_be_taken_back():
    doc = doc_of(panel(0), panel(1, c=1))
    de.write_scene(doc, None, "exag", 3.0)
    de.write_scene(doc, 1, "exag", 5.0)
    assert doc["panels"][1]["opts"]["scene3d"] == dict(exag=5.0)
    assert (de.scene_block(doc, 0)["exag"], de.scene_block(doc, 1)["exag"]) == (3.0, 5.0)
    de.write_scene(doc, None, "exag", 4.0)
    assert (de.scene_block(doc, 0)["exag"], de.scene_block(doc, 1)["exag"]) == (4.0, 5.0)
    de.scene_take_back(doc, 1, "exag")
    assert "opts" not in doc["panels"][1] and de.scene_block(doc, 1)["exag"] == 4.0


def test_a_lone_scene_that_holds_a_setting_keeps_writing_it():
    doc = doc_of(panel(0))
    doc["panels"][0]["opts"] = dict(scene3d=dict(exag=5.0))
    de.write_scene(doc, 0, "exag", 6.0)
    assert doc["panels"][0]["opts"]["scene3d"]["exag"] == 6.0
    assert "exag" not in de.scene_kind_block(doc)


def test_a_panels_own_scene_settings_reach_its_view():
    doc = doc_of(panel(0), panel(1, c=1))
    doc["kinds"]["scene"] = dict(scene3d=dict(exag=3.0, ztop=10.0))
    de.write_scene(doc, 1, "exag", 5.0)
    res = figdraw.resolve(doc)
    views = {q["id"]: figdraw.panel_view(res, q)["scene3d"] for q in res["panels"]}
    assert (views[0]["exag"], views[1]["exag"]) == (3.0, 5.0)
    assert views[1]["ztop"] == 10.0


def test_scene_is_a_kind_to_add_with_labels_of_a_panel():
    assert "scene" in ADDABLE
    assert "Panel labels" in looks.PANEL_KEYS["scene"]
    assert nodes.kind_name("scene", 2) == "3D scenes (2)"


# ------------------------------------------------------------------ annotations and panels
def test_a_removed_panels_annotations_go_with_it():
    doc = doc_of(panel(0), panel(1, c=1))
    doc["annotations"] = [dict(kind="text", panel=0), dict(kind="text", panel=[0, 1]),
                          dict(kind="text", panel=-1), dict(kind="text", panel=1)]
    de.remove_panel(doc, 0)
    assert [a["panel"] for a in doc["annotations"]] == [1, -1, 1]


def test_a_removed_panels_annotation_does_not_land_on_the_next_panel_with_its_id():
    doc = doc_of(panel(0), panel(1, c=1))
    doc["annotations"] = [dict(kind="text", panel=1)]
    de.remove_panel(doc, 1)
    p = de.add_panel(doc, "scene", (0, 1))
    assert p["id"] == 1 and doc["annotations"] == []


def test_fill_drops_the_annotations_of_the_panels_left_over():
    doc = doc_of(panel(0, "plan"), panel(1, "plan", c=1))
    doc["annotations"] = [dict(kind="text", panel=1), dict(kind="text", panel=0)]
    de.fill_panels(doc, 1, 1)
    assert [a["panel"] for a in doc["annotations"]] == [0]


def test_a_copied_panel_has_its_annotations_too():
    doc = doc_of(panel(0), panel(1, c=1))
    doc["annotations"] = [dict(kind="text", panel=0), dict(kind="text", panel=-1),
                          dict(kind="text", panel=1)]
    new = de.copy_panel(doc, 0, (1, 0))
    assert [a["panel"] for a in doc["annotations"]] == [[0, new["id"]], -1, 1]


@pytest.mark.parametrize("kind", ["text", "marker", "arrow", "line", "vline", "hline", "box",
                                  "circle", "legend"])
def test_a_new_annotation_in_axis_units_or_fractions(kind):
    a = de.new_annotation(kind, 3, ((0.0, 10.0), (-5.0, 5.0)))
    assert (a["panel"], a["coords"], a["x"], a["y"]) == (3, "data", 5.0, 0.0)
    assert a["x2"] == 6.5 and a["r"] == 1.5
    b = de.new_annotation(kind, -1)
    assert (b["coords"], b["x"], b["y"], b["x2"]) == ("axes", 0.5, 0.5, 0.65)


# ------------------------------------------------------------------ placing: the sums
def box(xlim=(0.0, 10.0), ylim=(0.0, 20.0)):
    return (0.1, 0.5, 0.2, 0.8, xlim, ylim, None)


def test_a_point_of_the_preview_is_a_panel_and_fractions_of_it():
    hit = C.locate({7: box()}, 0.3, 0.5)
    assert hit[0] == 7 and hit[2:] == pytest.approx((0.5, 0.5))
    assert C.locate({7: box()}, 0.7, 0.5) is None


def test_a_drag_ends_where_it_went_with_the_image_upside_down():
    u, w = C.dragged_to(box(), 0.5, 0.5, (0.3, 0.5), (0.4, 0.2))
    assert (u, w) == pytest.approx((0.75, 1.0))


def test_a_placed_item_of_one_and_of_two_points():
    a = C.placed_item("text", 2, None, 1.0, 2.0)
    assert (a["kind"], a["panel"], a["x"], a["y"], a["text"]) == ("text", 2, 1.0, 2.0, "A")
    a = C.placed_item("line", 2, (1.0, 2.0), 3.0, 4.0)
    assert (a["x"], a["y"], a["x2"], a["y2"]) == (1.0, 2.0, 3.0, 4.0)
    a = C.placed_item("circle", 2, (0.0, 0.0), 3.0, 4.0)
    assert a["r"] == 5.0


def test_grabbing_and_moving_an_annotation():
    b = box()
    anns = [dict(kind="text", panel=1, x=5.0, y=10.0), dict(kind="text", panel=7, x=5.0, y=10.0)]
    assert C.grab_annotation(anns, 7, b, (0.5, 0.5)) == (1, "all")
    assert C.grab_annotation(anns, 7, b, (0.9, 0.9)) is None
    assert C.moved_annotation(anns[1], b, (0.5, 0.5), (0.6, 0.7), "all") == dict(x=6.0, y=14.0)


def test_axes_of_small_values_keep_digits_enough_to_place_on():
    assert C.axis_digits((-20.0, 20.0)) == 2
    assert C.axis_digits((0.0, 1.0)) == 3
    assert C.axis_digits((-0.1, 0.1)) == 4
    assert C.axis_digits((1.0, 1.0)) == 2


def test_a_panel_by_fractions_has_fractions_as_its_axis_units():
    b = fraction_entry([0.1, 0.5, 0.2, 0.8])
    assert C.to_data(b, 0.25, 0.75) == pytest.approx((0.25, 0.75))
    a = dict(kind="text", coords="axes", panel=1, x=0.25, y=0.75)
    assert C.grab_annotation([a], 1, b, (0.25, 0.75)) == (0, "all")


def test_section_clicks_go_to_the_panels_ab_section_or_the_first_or_the_only_or_a_new_one():
    doc = doc_of(panel(0, "plan"))
    doc["sections"] = dict(s0=dict(orient="x"))
    assert de.place_section(doc, 0, (1, 2), (3, 4)) == "s0"  # (the only one)
    assert doc["sections"]["s0"]["orient"] == "ab" and doc["sections"]["s0"]["b"] == [3.0, 4.0]
    doc["sections"] = dict(s0=dict(orient="x"), s1=dict(orient="ab"), s2=dict(orient="ab"))
    doc["panels"][0]["section"] = "s0"
    assert de.place_section(doc, 0, (1, 2), (3, 4)) == "s1"  # (the first A-B)
    assert doc["sections"]["s0"]["orient"] == "x" and doc["panels"][0]["section"] == "s1"
    doc["panels"][0]["section"] = "s2"
    assert de.place_section(doc, 0, (5, 6), (7, 8)) == "s2"  # (its own)
    doc["sections"] = dict(s0=dict(orient="x"), s1=dict(orient="y"))
    new = de.place_section(doc, 0, (1, 2), (3, 4))
    assert new not in ("s0", "s1") and doc["sections"][new]["orient"] == "ab"
    assert doc["sections"]["s0"]["orient"] == "x"


def test_the_area_dragged_is_the_kinds():
    doc = doc_of(panel(0, "plan"))
    doc["kinds"]["plan"] = dict(domain=dict(mode="full", half=20.0))
    de.set_area(doc, [1.234, 5.0, -2.0, 2.0])
    assert doc["kinds"]["plan"]["domain"] == dict(mode="box", half=20.0,
                                                  box=[1.23, 5.0, -2.0, 2.0])


# ------------------------------------------------------------------ the panes, by their widgets
class _Now:
    def submit(self, fn, *a):
        fn(*a)

    def shutdown(self, *a, **k):
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


def _walk(shell):
    return list(shell.inspector.body.select())


def _named(shell, name, nth=0):
    hits = [w for w in _walk(shell) if getattr(w, "name", None) == name and hasattr(w, "value")
            and w.visible]
    assert hits, f"no {name}"
    return hits[nth]


def _click(shell, name, nth=0):
    hits = [w for w in _walk(shell) if getattr(w, "name", None) == name and hasattr(w, "clicks")]
    assert hits, f"no {name}"
    hits[nth].clicks += 1


def _cards(shell):
    return {c.title: c for c in _walk(shell) if type(c).__name__ == "Card"}


def _open_all(shell):
    for title in list(_cards(shell)):
        _cards(shell)[title].collapsed = False


def _drew(shell):
    t0 = time.time()
    while shell.ed.series_pending() and time.time() - t0 < 60:
        time.sleep(0.2)
    shell.request(force=True, delay=False)
    assert "Could not draw" not in shell.status.object, shell.status.object


def _event(*new):
    return SimpleNamespace(new=list(new))


def _at(shell, pid, u, w):
    b = shell.placing.place[pid]
    return b[0] + u * (b[1] - b[0]), b[3] - w * (b[3] - b[2])


def _scene_figure(shell):
    pytest.importorskip("pyvista")
    ed = shell.ed
    ed.open_quick()
    ed.qs_kind.value = "scene"
    ed._quick_make()
    shell.doc["export"] = dict(shell.doc.get("export") or {}, dpi=60)
    shell.doc["size"] = [3.0, 2.4]
    return shell.doc["panels"][0]["id"]


def test_a_click_adds_an_annotation_in_axis_units_and_picks_its_panel(shell):
    _drew(shell)
    pid = shell.doc["panels"][0]["id"]
    b = shell.placing.place[pid]
    shell.placing.mode.value = "text"
    shell._on_click(_event(*_at(shell, pid, 0.25, 0.75), 1))
    a = shell.doc["annotations"][-1]
    assert (a["kind"], a["panel"], a["coords"]) == ("text", pid, "data")
    assert a["x"] == pytest.approx(b[4][0] + 0.25 * (b[4][1] - b[4][0]), abs=0.01)
    assert a["y"] == pytest.approx(b[5][0] + 0.75 * (b[5][1] - b[5][0]), abs=0.01)
    assert shell.node == f"panel:{pid}"
    assert any(t.startswith("Annotations") for t in _cards(shell))


def test_without_a_mode_a_click_picks_and_a_drag_does_nothing(shell):
    _drew(shell)
    pid = shell.doc["panels"][0]["id"]
    place = shell._boxes[pid]
    n = len(shell.doc.get("annotations") or [])
    shell._on_click(_event(0.5 * (place[0] + place[1]), 0.5 * (place[2] + place[3]), 1))
    assert shell.node == f"panel:{pid}"
    shell._on_drag(_event(place[0], place[2], place[1], place[3], 2))
    assert len(shell.doc.get("annotations") or []) == n


def test_two_clicks_a_drag_and_moving_with_undo(shell):
    _drew(shell)
    pid = shell.doc["panels"][0]["id"]
    pl = shell.placing
    pl.mode.value = "line"
    shell._on_click(_event(*_at(shell, pid, 0.1, 0.1), 1))
    assert pl.pending is not None and not shell.doc.get("annotations")
    shell._on_click(_event(*_at(shell, pid, 0.9, 0.2), 2))
    assert pl.pending is None and shell.doc["annotations"][-1]["kind"] == "line"
    pl.mode.value = "text"
    shell._on_click(_event(*_at(shell, pid, 0.3, 0.8), 3))
    was = dict(shell.doc["annotations"][-1])
    pl.mode.value = "move"
    shell._on_drag(_event(*_at(shell, pid, 0.3, 0.8), *_at(shell, pid, 0.4, 0.6), 4))
    assert shell.doc["annotations"][-1]["x"] > was["x"]
    assert shell.doc["annotations"][-1]["y"] < was["y"]
    shell.undo()
    assert shell.doc["annotations"][-1]["x"] == was["x"]


def test_section_and_area_only_in_a_plan_view(shell):
    _drew(shell)
    pid = shell.doc["panels"][0]["id"]
    pl = shell.placing
    pl.mode.value = "section"
    shell._on_drag(_event(*_at(shell, pid, 0.2, 0.5), *_at(shell, pid, 0.8, 0.5), 1))
    sid = de.panel_by_id(shell.doc, pid)["section"]
    assert shell.doc["sections"][sid]["orient"] == "ab"
    pl.mode.value = "area"
    shell._on_drag(_event(*_at(shell, pid, 0.25, 0.25), *_at(shell, pid, 0.75, 0.75), 2))
    dom = shell.doc["kinds"]["plan"]["domain"]
    assert dom["mode"] == "box" and dom["box"][1] > dom["box"][0]
    other = shell.inspector.grid.add_panel("dist", "new column")
    _drew(shell)
    was = de.plain(shell.doc["kinds"]["plan"]["domain"])
    shell._on_drag(_event(*_at(shell, other["id"], 0.2, 0.2), *_at(shell, other["id"], 0.8, 0.8), 3))
    assert shell.doc["kinds"]["plan"]["domain"] == was and "plan view" in shell.status.object


def test_annotations_on_the_figure_and_on_a_panel_by_their_cards(shell):
    pid = shell.doc["panels"][0]["id"]
    shell.select(nodes.FIGURE)
    _cards(shell)["Annotations"].collapsed = False
    _named(shell, "Add").value = "vline"
    _click(shell, "+ Add")
    assert shell.doc["annotations"][-1]["panel"] == -1
    assert _named(shell, "Panels (blank: all)").value == []
    _named(shell, "Panels (blank: all)").value = [pid]
    assert shell.doc["annotations"][-1]["panel"] == pid
    shell.select(f"panel:{pid}")
    assert "Annotations (1)" in _cards(shell)
    _cards(shell)["Annotations (1)"].collapsed = False
    _click(shell, "+ Add")
    assert shell.doc["annotations"][-1]["panel"] == pid
    shell.undo()
    assert len(shell.doc["annotations"]) == 1


def test_opening_an_annotation_writes_nothing_and_a_gone_panels_stays_gone(shell):
    shell.doc["annotations"] = [dict(kind="text", panel=999, coords="data", x=1.0, y=2.0, text="z")]
    shell._show(nodes.FIGURE)
    kept = len(shell._hist)
    _cards(shell)["Annotations (1)"].collapsed = False
    assert len(shell._hist) == kept and shell.doc["annotations"][0]["panel"] == 999
    assert any("no such panel" in str(getattr(w, "object", "")) for w in _walk(shell))


def test_a_scene_edits_the_document_from_all_scenes_and_from_its_panel(shell):
    pid = _scene_figure(shell)
    shell._show("kind:scene")
    kept = len(shell._hist)
    _open_all(shell)
    assert len(shell._hist) == kept  # (opening its sections writes nothing)
    _named(shell, "Azimuth (°)").value = 200.0
    assert de.scene_kind_block(shell.doc)["camera"]["azimuth"] == 200.0
    _named(shell, "Vertical exaggeration").value = 1.5
    assert de.scene_kind_block(shell.doc)["exag"] == 1.5
    _named(shell, "x axis label").value = "east"
    assert de.scene_kind_block(shell.doc)["look"]["labels"][0] == "east"
    shell._show(f"panel:{pid}")
    _named(shell, "Zoom").value = 1.2
    assert de.scene_kind_block(shell.doc)["camera"]["zoom"] == 1.2
    _drew(shell)
    assert pid in shell._boxes


def test_a_scenes_lists_add_edit_and_remove_rows(shell):
    _scene_figure(shell)
    shell._show("kind:scene")
    _open_all(shell)
    n = len(de.scene_kind_block(shell.doc)["isos"])
    _click(shell, "+ Isosurface")
    assert len(de.scene_kind_block(shell.doc)["isos"]) == n + 1
    _named(shell, "Value", n).value = 42.0
    assert de.scene_kind_block(shell.doc)["isos"][n]["val"] == 42.0
    _click(shell, "✕", n)
    assert len(de.scene_kind_block(shell.doc)["isos"]) == n
    _click(shell, "+ Vectors")
    assert de.scene_kind_block(shell.doc)["vecs"][-1]["q"]  # (as its row fills it in)
    _drew(shell)


def test_a_bad_box_writes_nothing(shell):
    _scene_figure(shell)
    shell._show("kind:scene")
    _open_all(shell)
    _named(shell, "Region").value = "box"
    box = de.scene_kind_block(shell.doc)["box"]
    assert box is not None
    kept = len(shell._hist)
    _named(shell, "x max (km)").value = box[0] - 1.0
    assert len(shell._hist) == kept and de.scene_kind_block(shell.doc)["box"] == box
    _named(shell, "Region").value = "full"
    assert de.scene_kind_block(shell.doc)["box"] is None


def test_a_click_in_a_scene_is_a_fraction_of_it(shell):
    pid = _scene_figure(shell)
    _drew(shell)
    shell.placing.mode.value = "text"
    shell._on_click(_event(*_at(shell, pid, 0.3, 0.8), 1))
    a = shell.doc["annotations"][-1]
    assert a["coords"] == "axes" and a["x"] == pytest.approx(0.3, abs=0.01)
    assert a["y"] == pytest.approx(0.8, abs=0.01)
    _drew(shell)


def test_two_scenes_differ_where_one_is_set_and_it_can_go_back(shell):
    pid = _scene_figure(shell)
    copy = shell.inspector.grid.copy_panel(pid)
    assert shell.node == f"panel:{copy['id']}"
    _named(shell, "Azimuth (°)").value = 30.0
    assert de.scene_own(shell.doc, copy["id"])["camera"]["azimuth"] == 30.0
    assert not de.scene_own(shell.doc, pid)
    _drew(shell)
    _click(shell, "↺ Camera")
    assert not de.scene_own(shell.doc, copy["id"])


def test_a_new_scene_panel_beside_a_plan_view_draws(shell):
    pytest.importorskip("pyvista")
    shell.doc["export"] = dict(shell.doc.get("export") or {}, dpi=60)
    p = shell.inspector.grid.add_panel("scene", "new column")
    assert p["kind"] == "scene" and p["run"] and p["time_s"] is not None
    assert "scene3d" in shell.doc["kinds"]["scene"]
    _drew(shell)
    assert p["id"] in shell._boxes
    for row in shell.tree.items:
        shell.select(row["id"])
        assert shell.inspector.body.objects, row["id"]
