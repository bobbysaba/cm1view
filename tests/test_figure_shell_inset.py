"""F2: zoom insets, in the document, in the drawing and in the new layout."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg

from cm1view.figures import draw as figdraw, spec as fg
from cm1view.figures.shell import docedit as de, findview, nodes
from cm1view.figures.shell.looks import InsetScope


def doc_of(*panels):
    return dict(version=3, size=[6.0, 3.0], grid=dict(rows=1, cols=max(len(panels), 1)), style={},
                kinds=dict(plan=dict(domain=dict(mode="full", half=12.5, box=None), coords="grid")),
                runs=[dict(id="r0", path="/x/one", t0_min=0.0, label="a")], sections={},
                layers=dict(l0=dict(type="fill", field="dbz", z=1.0, on=True)),
                panels=list(panels), annotations=[])


def panel(pid, c=0, kind="plan", **more):
    return dict(id=pid, kind=kind, cell=[0, c, 1, 1], run="r0", time_s=600.0, title="",
                layers=[dict(ref="l0", over={})], **more)


BOX = dict(domain=dict(mode="box", box=[0.0, 4.0, 0.0, 2.0]))


# ------------------------------------------------------------------ the document
def test_a_figure_without_insets_resolves_as_it_did():
    res = figdraw.resolve(doc_of(panel(0, insets=[])))
    assert "insets" not in res["panels"][0]


def test_an_inset_shows_the_panels_layers_until_it_has_its_own():
    doc = doc_of(panel(0, insets=[dict(id=3, opts=BOX)]))
    res = figdraw.resolve(doc)
    q = figdraw.panel_or_inset(res, -3)
    assert q["id"] == -3 and q["layers"] == res["panels"][0]["layers"]
    doc["layers"]["l0"]["z"] = 2.0
    assert figdraw.panel_or_inset(figdraw.resolve(doc), -3)["layers"][0]["z"] == 2.0
    de.own_inset_layers(doc, 0, 3, True)
    de.write_panel(doc, de.inset_by_id(doc["panels"][0], 3), 0, dict(z=5.0))
    assert doc["panels"][0]["layers"] == [dict(ref="l0", over={})]
    res = figdraw.resolve(doc)
    assert figdraw.panel_or_inset(res, -3)["layers"][0]["z"] == 5.0
    assert res["panels"][0]["layers"][0]["z"] == 2.0
    de.own_inset_layers(doc, 0, 3, False)
    assert figdraw.panel_or_inset(figdraw.resolve(doc), -3)["layers"][0]["z"] == 2.0


def test_an_insets_area_is_its_own_and_reaches_what_it_reads():
    doc = doc_of(panel(0, insets=[dict(id=1, opts=BOX)]))
    assert fg.one_panel(doc, -1)["domain"]["box"] == [0.0, 4.0, 0.0, 2.0]
    assert fg.one_panel(doc, 0)["domain"]["mode"] == "full"


def test_a_plan_window_can_follow_the_storm_from_off_centre():
    spec = dict(domain=dict(mode="storm", half=2.0, off=[1.0, -1.0]))
    assert fg.plan_window(None, spec, (10.0, 20.0)) == (9.0, 13.0, 17.0, 21.0)
    spec = dict(domain=dict(mode="storm", half=2.0))
    assert fg.plan_window(None, spec, (10.0, 20.0)) == (8.0, 12.0, 18.0, 22.0)


def test_new_insets_sit_away_from_what_they_show_with_ids_of_their_own():
    doc = doc_of(panel(0), panel(1, 1))
    lims = ((0.0, 10.0), (0.0, 10.0))
    a = de.add_inset(doc, 0, [1.0, 2.0, 1.0, 2.0], lims)
    b = de.add_inset(doc, 1, [8.0, 9.0, 8.0, 9.0], lims)
    assert a["loc"] == "upper right" and b["loc"] == "lower left"
    assert a["id"] != b["id"]
    new = de.copy_panel(doc, 0, (0, 2))
    assert new["insets"][0]["id"] not in (a["id"], b["id"])
    assert new["insets"][0]["opts"] == a["opts"]


def test_a_new_inset_of_a_panel_following_the_storm_follows_it():
    doc = doc_of(panel(0))
    ins = de.add_inset(doc, 0, [12.0, 16.0, 19.0, 21.0], center=(10.0, 20.0))
    assert ins["opts"]["domain"] == dict(mode="storm", half=2.0, off=[4.0, 0.0])


def test_a_cross_sections_inset_keeps_a_view():
    doc = doc_of(panel(0, kind="xsec"))
    ins = de.add_inset(doc, 0, [-2.0, 2.0, 0.0, 4.0], ((-10.0, 10.0), (0.0, 6.0)))
    assert ins["view"] == [-2.0, 2.0, 0.0, 4.0] and "opts" not in ins


def test_times_move_an_insets_own_layers_and_templates_keep_it():
    doc = doc_of(panel(0, insets=[dict(id=1, opts=BOX, layers=[
        dict(type="contour", field="w", z=1.0, time_s=600.0),
        dict(type="contour", field="w", z=1.0, time_s=600.0, time_lock=True)])]))
    moved = fg.shift_times(doc, 60.0)
    lays = moved["panels"][0]["insets"][0]["layers"]
    assert lays[0]["time_s"] == 660.0 and lays[1]["time_s"] == 600.0
    tpl = fg.template(doc, "t")
    assert tpl["panels"][0]["insets"][0]["opts"] == BOX


def test_a_shared_layer_goes_from_an_insets_own_list_too():
    doc = doc_of(panel(0, insets=[dict(id=1, layers=[dict(ref="l0", over={})])]))
    de.remove_shared(doc, "plan", "l0")
    assert doc["panels"][0]["insets"][0]["layers"] == [] and "l0" not in doc["layers"]


def test_a_shared_layer_an_inset_draws_alone_stays():
    doc = doc_of(panel(0, insets=[dict(id=1, layers=[dict(ref="l0", over={})])]))
    de.remove_in_panel(doc, doc["panels"][0], 0)
    assert "l0" in doc["layers"]


def test_keeping_a_layer_apart_takes_insets_along():
    doc = doc_of(panel(0, insets=[dict(id=1, layers=[dict(ref="l0", over={})])]))
    new = de.split_shared(doc, "plan", "l0")
    assert doc["panels"][0]["insets"][0]["layers"][0]["ref"] == new


def test_a_panels_height_reaches_an_insets_own_layers():
    doc = doc_of(panel(0, insets=[dict(id=1, layers=[dict(type="fill", field="dbz", z=1.0)])]))
    de.set_height(doc, doc["panels"][0], 3.0)
    assert doc["panels"][0]["insets"][0]["layers"][0]["z"] == 3.0


def test_a_run_an_inset_uses_is_in_use():
    doc = doc_of(panel(0, insets=[dict(id=1, layers=[dict(type="fill", run="r1", field="dbz")])]))
    assert nodes.runs_used(doc)["r1"] == [0]


def test_the_tree_has_an_insets_node():
    doc = doc_of(panel(0, insets=[dict(id=4)]))
    assert dict(id="inset:0:4", depth=2, label="Zoom inset 1") in nodes.tree_items(doc)
    assert nodes.still_there(doc, "inset:0:4") and not nodes.still_there(doc, "inset:0:5")
    assert nodes.outlined(doc, "inset:0:4") == [-4]
    assert nodes.panel_of(doc, "inset:0:4")["id"] == 0
    assert nodes.node_at(doc, -4) == "inset:0:4" and nodes.node_at(doc, 0) == "panel:0"
    assert "inset 1 of panel a" in nodes.scope(doc, "inset:0:4")


def test_an_insets_scope_reads_through_the_panel_and_writes_its_own():
    doc = doc_of(panel(0, opts=dict(coords="storm"), insets=[dict(id=1)]))
    at = InsetScope("plan", 0, 1)
    assert at._layers_up(doc, "coords")[-2] == dict(coords="storm")
    at._targets(doc, "domain")[0]["domain"] = dict(mode="box")
    assert doc["panels"][0]["insets"][0]["opts"] == dict(domain=dict(mode="box"))
    assert at.own_keys(doc, ("domain.mode",)) == ["domain.mode"]
    at.take_back(doc, "domain.mode")
    assert "opts" not in doc["panels"][0]["insets"][0]
    assert doc["panels"][0]["opts"] == dict(coords="storm")


# ------------------------------------------------------------------ the drawing
def plan_data(x0=0.0, x1=10.0):
    x = np.linspace(x0, x1, 21)
    return dict(x=x, y=x, xlim=(x0, x1), ylim=(x0, x1), origin=np.zeros(2), time_s=600.0,
                L0=np.outer(x, x).astype(float))


def fill_doc(**inset):
    doc = doc_of(panel(0, insets=[dict(dict(id=1, opts=BOX), **inset)]))
    doc["layers"]["l0"].update(cmap="viridis", vmin=0.0, vmax=100.0, levels=11)
    return doc


def _drawn(doc, data):
    fig = figdraw.draw(doc, data)
    fig.canvas = FigureCanvasAgg(fig)
    fig.canvas.draw()
    return fig


def test_the_rectangle_of_an_inset():
    lims, panel_lims = ((0.0, 4.0), (0.0, 2.0)), ((0.0, 10.0), (0.0, 10.0))
    x, y, w, h = figdraw.inset_rect(dict(loc="lower left", size=0.4), lims, panel_lims, True)
    assert (x, y, w) == (figdraw.INSET_PAD, figdraw.INSET_PAD, 0.4) and h == pytest.approx(0.2)
    x, y, w, h = figdraw.inset_rect(dict(size=0.5, h=0.1), lims, panel_lims, True)
    assert x == pytest.approx(0.47) and y == pytest.approx(0.87) and h == 0.1
    assert figdraw.inset_rect(dict(loc="custom", x=0.2, y=0.3, size=0.5), lims, panel_lims, False) \
        == [0.2, 0.3, 0.5, 0.5]
    tall = figdraw.inset_rect(dict(size=0.5), ((0.0, 1.0), (0.0, 4.0)), panel_lims, True)
    assert max(tall[2:]) <= 1.0 - 2 * figdraw.INSET_PAD


def test_lines_join_sides_that_face_each_other():
    box = [0.4, 0.4, 0.2, 0.2]
    assert figdraw.inset_lines([0.7, 0.45, 0.2, 0.1], box) == [((1, 0), (0, 0)), ((1, 1), (0, 1))]
    assert figdraw.inset_lines([0.1, 0.45, 0.2, 0.1], box) == [((0, 0), (1, 0)), ((0, 1), (1, 1))]
    assert figdraw.inset_lines([0.45, 0.7, 0.1, 0.2], box) == [((0, 1), (0, 0)), ((1, 1), (1, 0))]
    assert figdraw.inset_lines([0.7, 0.7, 0.2, 0.2], box) == [((0, 1), (0, 1)), ((1, 0), (1, 0))]
    assert figdraw.inset_lines([0.1, 0.7, 0.2, 0.2], box) == [((0, 0), (0, 0)), ((1, 1), (1, 1))]


def test_an_inset_is_drawn_with_its_box_and_lines_and_leaves_the_panel_where_it_was():
    bare = _drawn(doc_of(panel(0)) | dict(layers=fill_doc()["layers"]), {0: plan_data()})
    doc = fill_doc()
    fig = _drawn(doc, {0: plan_data(), -1: plan_data(0.0, 4.0)})
    ax = fig._cv_axes[0]
    assert ax.get_position().bounds == pytest.approx(bare._cv_axes[0].get_position().bounds)
    assert list(ax._cv_insets) == [-1]
    cax = ax._cv_insets[-1]
    assert cax in ax.child_axes and cax.get_xlim() == (0.0, 4.0) and cax.get_ylim() == (0.0, 4.0)
    kinds = [type(a).__name__ for a in ax.patches]
    assert kinds.count("ConnectionPatch") == 2 and "Rectangle" in kinds


def test_an_inset_can_go_without_lines_or_box():
    fig = _drawn(fill_doc(connect=False), {0: plan_data(), -1: plan_data(0.0, 4.0)})
    assert [type(a).__name__ for a in fig._cv_axes[0].patches] == ["Rectangle"]
    fig = _drawn(fill_doc(mark=False), {0: plan_data(), -1: plan_data(0.0, 4.0)})
    assert not fig._cv_axes[0].patches


def test_an_inset_without_arrays_is_left_out():
    fig = _drawn(fill_doc(), {0: plan_data()})
    assert not getattr(fig._cv_axes[0], "_cv_insets", None)


def test_an_inset_says_it_has_no_data():
    fig = _drawn(fill_doc(), {0: plan_data(), -1: dict(time_s=600.0, missing="no box chosen")})
    cax = fig._cv_axes[0]._cv_insets[-1]
    assert "no box chosen" in [t.get_text() for t in cax.texts]


def test_arrays_of_an_inset_go_through_a_file_by_their_key(tmp_path):
    from cm1view.figures.spec.bundle import flatten, unflatten
    keys = flatten({0: dict(a=np.arange(2)), -1: dict(a=np.arange(3))})
    np.savez(tmp_path / "d.npz", **keys)
    with np.load(tmp_path / "d.npz") as z:
        back = unflatten(z)
    assert set(back) == {0, -1} and back[-1]["a"].size == 3


def test_a_drawn_inset_is_found_in_the_preview_ahead_of_its_panel():
    from cm1view.figures.click import panel_boxes
    doc = fill_doc()
    fig = _drawn(doc, {0: plan_data(), -1: plan_data(0.0, 4.0)})
    W, H = fig.get_size_inches() * fig.dpi
    boxes = panel_boxes(fig, doc, (W, H), fig.dpi)
    assert list(boxes)[0] == -1
    b = boxes[-1]
    assert nodes.pick_at(boxes, 0.5 * (b[0] + b[1]), 0.5 * (b[2] + b[3])) == -1
    p = boxes[0]
    assert nodes.pick_at(boxes, p[0] + 0.001, p[3] - 0.001) == 0


# ------------------------------------------------------------------ on the demo run
class _Now:
    def submit(self, fn, *a):
        fn(*a)

    def shutdown(self, *a, **k):
        pass


@pytest.fixture
def shell(reg, monkeypatch):
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
    ed = v.figed
    ed.open_quick()
    ed.qs_kind.value = "plan"
    ed._quick_make()
    ed.shell.take_figure()
    ed.shell.inspector.grid.add_panel("plan", "new column")
    yield ed.shell
    v.close()


def _drew(shell):
    shell.request(force=True, delay=False)
    assert "Could not draw" not in shell.status.object, shell.status.object


def _event(*new):
    return SimpleNamespace(new=list(new))


def _at(shell, pid, u, w):
    b = shell.placing.place[pid]
    return b[0] + u * (b[1] - b[0]), b[3] - w * (b[3] - b[2])


def _card(shell, title):
    card = next(c for c in shell.inspector.body.objects if getattr(c, "title", None) == title)
    card.collapsed = False
    return card


def _in(card, name):
    return next(w for w in card.select() if getattr(w, "name", None) == name
                and hasattr(w, "value"))


def _one(shell, name):
    return next(o for o in shell.inspector.body.objects if getattr(o, "name", "") == name)


def _made(shell):
    """A new inset of the first plan view, by the panel's button.  (panel id, inset id)."""
    _drew(shell)
    pid = shell.doc["panels"][0]["id"]
    shell.select(f"panel:{pid}")
    _one(shell, "+ Zoom inset").clicks += 1
    return pid, de.panel_by_id(shell.doc, pid)["insets"][-1]["id"]


def test_the_button_makes_an_inset_and_picks_it(shell):
    pid, iid = _made(shell)
    assert shell.node == f"inset:{pid}:{iid}"
    _drew(shell)
    assert -iid in shell._boxes and -iid in shell.ed.panel_data(de.plain(shell.doc))
    assert list(shell.image.marks) == [str(-iid)]
    shell.undo()
    assert not de.panel_by_id(shell.doc, pid)["insets"]


def test_clicking_the_preview_picks_the_inset(shell):
    pid, iid = _made(shell)
    _drew(shell)
    b = shell._boxes[-iid]
    shell.select(nodes.FIGURE)
    shell._on_click(_event(0.5 * (b[0] + b[1]), 0.5 * (b[2] + b[3]), 1))
    assert shell.node == f"inset:{pid}:{iid}"


def test_a_drag_makes_an_inset_clear_of_what_it_shows(shell):
    _drew(shell)
    a = shell.doc["panels"][0]["id"]
    shell.placing.mode.value = "inset"
    shell._on_drag(_event(*_at(shell, a, 0.1, 0.1), *_at(shell, a, 0.4, 0.3), 1))
    ins = de.panel_by_id(shell.doc, a)["insets"][0]
    assert shell.node == f"inset:{a}:{ins['id']}" and ins["loc"] == "upper right"
    assert ins["opts"]["domain"]["mode"] in ("box", "storm")


def test_a_small_drag_makes_none(shell):
    _drew(shell)
    a = shell.doc["panels"][0]["id"]
    shell.placing.mode.value = "inset"
    shell._on_drag(_event(*_at(shell, a, 0.5, 0.5), *_at(shell, a, 0.51, 0.51), 1))
    assert not de.panel_by_id(shell.doc, a).get("insets")


def test_drags_change_the_picked_inset(shell):
    pid, iid = _made(shell)
    _drew(shell)
    pl = shell.placing
    pl.mode.value = "inset_place"
    shell._on_drag(_event(*_at(shell, pid, 0.1, 0.5), *_at(shell, pid, 0.4, 0.9), 1))
    ins = de.inset_by_id(de.panel_by_id(shell.doc, pid), iid)
    assert ins["loc"] == "custom" and ins["x"] == pytest.approx(0.1, abs=0.01)
    assert ins["y"] == pytest.approx(0.5, abs=0.01) and ins["size"] == pytest.approx(0.3, abs=0.01)
    was = json.dumps(ins["opts"])
    pl.mode.value = "inset_area"
    shell._on_drag(_event(*_at(shell, pid, 0.2, 0.2), *_at(shell, pid, 0.3, 0.4), 2))
    assert json.dumps(de.inset_by_id(de.panel_by_id(shell.doc, pid), iid)["opts"]) != was


def test_an_insets_cards_write_it_mark_it_and_reset(shell):
    pid, iid = _made(shell)
    card = _card(shell, "Where it sits")
    _in(card, "Where").value = "lower left"
    ins = de.inset_by_id(de.panel_by_id(shell.doc, pid), iid)
    assert ins["loc"] == "lower left" and "● 1" in card.header.object
    look = _card(shell, "Box and lines")
    _in(look, "Lines to the inset").value = False
    _in(look, "Tick labels").value = True
    ins = de.inset_by_id(de.panel_by_id(shell.doc, pid), iid)
    assert ins["connect"] is False and ins["ticks"] is True
    _drew(shell)
    reset = next(w for w in look.select() if getattr(w, "name", "").startswith("↺"))
    reset.clicks += 1
    ins = de.inset_by_id(de.panel_by_id(shell.doc, pid), iid)
    assert "connect" not in ins and "ticks" not in ins and ins["loc"] == "lower left"


def test_an_insets_own_layers_are_edited_apart_from_the_panel(shell):
    pid, iid = _made(shell)
    before = json.dumps(de.panel_by_id(shell.doc, pid)["layers"])
    _one(shell, "The panel's layers").value = False
    pane = shell.inspector.insets
    pane._add_layer(pid, iid, "contour")
    ins = de.inset_by_id(de.panel_by_id(shell.doc, pid), iid)
    assert ins["layers"][-1]["type"] == "contour"
    row = pane._row(shell.doc, pid, iid, 0, len(ins["layers"]), "plan")
    row.on.value = False
    assert json.dumps(de.panel_by_id(shell.doc, pid)["layers"]) == before
    _drew(shell)
    _one(shell, "The panel's layers").value = True
    assert "layers" not in de.inset_by_id(de.panel_by_id(shell.doc, pid), iid)


def test_find_reaches_an_inset(shell):
    pid, iid = _made(shell)
    found = findview.search(findview.hits_of(shell), "zoom inset")
    assert any(h.node == f"inset:{pid}:{iid}" and h.section == "Where it sits" for h in found)
    assert any(h.label == "Zoom inset" for h in found)
    shell.inspector.go_to(f"inset:{pid}:{iid}", "Box and lines")
    assert shell.inspector.body.objects[0].title == "Box and lines"


def test_every_hit_of_an_inset_opens_where_it_says(shell):
    pid, iid = _made(shell)
    hits = [h for h in findview.hits_of(shell) if h.node == f"inset:{pid}:{iid}"]
    for section in {h.section for h in hits}:
        shell.inspector.go_to(f"inset:{pid}:{iid}", section)
        assert shell.inspector.body.objects[0].title == section


def test_removing_a_panels_inset(shell):
    pid, iid = _made(shell)
    _one(shell, "Remove this inset").clicks += 1
    assert shell.node == f"panel:{pid}" and not de.panel_by_id(shell.doc, pid)["insets"]


def test_a_cross_section_has_insets_too(shell):
    shell.inspector.grid.add_panel("xsec", "new column")
    _drew(shell)
    pid = next(p["id"] for p in shell.doc["panels"] if p["kind"] == "xsec")
    shell.placing.mode.value = "inset"
    shell._on_drag(_event(*_at(shell, pid, 0.4, 0.2), *_at(shell, pid, 0.6, 0.5), 1))
    ins = de.panel_by_id(shell.doc, pid)["insets"][0]
    assert len(ins["view"]) == 4
    _drew(shell)
    assert -ins["id"] in shell._boxes
    to = ins["view"][1] + 1.0
    _in(_card(shell, "Area"), "To (km)").value = to
    assert de.panel_by_id(shell.doc, pid)["insets"][0]["view"][1] == to


def test_an_inset_saves_and_renders(shell, tmp_path):
    from cm1view.figures.batch import main
    pid, iid = _made(shell)
    path = fg.save_spec(de.plain(shell.doc), str(tmp_path / "f"))
    again = fg.load_spec(path)
    assert de.panel_by_id(again, pid)["insets"] == de.panel_by_id(shell.doc, pid)["insets"]
    assert main([path, "--out", str(tmp_path / "again.png"), "--dpi", "50"]) == 0
    assert (tmp_path / "again.png").exists()
