"""F1: a plan view's own area, in the document, in the drawing and in the new layout."""
import time
from types import SimpleNamespace

import pytest

from cm1view.figures import draw as figdraw, spec as fg
from cm1view.figures.shell import docedit as de, findview, looks
from cm1view.figures.shell.looks import Scope


def doc_of(*panels):
    return dict(version=3, size=[6.0, 3.0], grid=dict(rows=1, cols=max(len(panels), 1)), style={},
                kinds=dict(plan=dict(domain=dict(mode="storm", half=12.5, box=None), coords="grid")),
                runs=[dict(id="r0", path="/x/one", t0_min=0.0, label="a")], sections={}, layers={},
                panels=list(panels), annotations=[])


def panel(pid, c=0, kind="plan", **more):
    return dict(id=pid, kind=kind, cell=[0, c, 1, 1], run="r0", time_s=600.0, title="", layers=[],
                **more)


# ------------------------------------------------------------------ the document
def test_the_area_dragged_goes_to_the_panel_and_keeps_the_kinds():
    doc = doc_of(panel(0), panel(1, 1))
    de.set_area(doc, [1.234, 5.0, -2.0, 2.0], pid=1)
    assert doc["panels"][1]["opts"]["domain"] == dict(mode="box", box=[1.23, 5.0, -2.0, 2.0])
    assert doc["kinds"]["plan"]["domain"]["mode"] == "storm"
    assert "opts" not in doc["panels"][0]


def test_a_panels_area_reaches_its_view_over_the_kinds():
    doc = doc_of(panel(0), panel(1, 1, opts=dict(domain=dict(mode="box", box=[0, 4, 0, 2]),
                                                 coords="storm")))
    res = figdraw.resolve(doc)
    views = {q["id"]: figdraw.panel_view(res, q) for q in res["panels"]}
    assert views[0]["domain"]["mode"] == "storm" and views[0]["coords"] == "grid"
    assert views[1]["domain"] == dict(mode="box", half=12.5, box=[0, 4, 0, 2])
    assert views[1]["coords"] == "storm"
    assert fg.one_panel(doc, 1)["domain"]["box"] == [0, 4, 0, 2]
    assert fg.one_panel(doc, 0)["domain"]["mode"] == "storm"


def test_a_panels_own_half_width_alone_leaves_the_rest_to_the_kind():
    doc = doc_of(panel(0, opts=dict(domain=dict(half=5.0))))
    res = figdraw.resolve(doc)
    dom = figdraw.panel_view(res, res["panels"][0])["domain"]
    assert dom == dict(mode="storm", half=5.0, box=None)


def test_scope_reads_writes_and_takes_back_a_panels_area_with_coords():
    doc = doc_of(panel(0), panel(1, 1))
    at = Scope("plan", 1)
    mode = next(st for st in looks.rows_of("Area", ["plan"]) if st.key == "domain.mode")
    coords = next(st for st in looks.rows_of("Area", ["plan"]) if st.key == "coords")
    assert at.value(doc, mode) == "storm"
    at.write(doc, mode, "full")
    at.write(doc, coords, "storm")
    assert doc["panels"][1]["opts"] == dict(domain=dict(mode="full"), coords="storm")
    assert at.value(doc, mode) == "full" and Scope("plan", 0).value(doc, mode) == "storm"
    assert set(at.own_keys(doc, looks.AREA_OF_A_PANEL)) == {"domain.mode", "coords"}
    assert looks.panels_differ(doc, "plan", looks.AREA_OF_A_PANEL) == {"b": ["domain.mode", "coords"]}
    at.take_back(doc, "coords")
    assert at.own_keys(doc, looks.AREA_OF_A_PANEL) == ["domain.mode"]
    at.take_back(doc, "domain.mode")
    assert "opts" not in doc["panels"][1]


def test_only_plan_views_have_the_new_area():
    assert "domain.mode" in looks.PANEL_KEYS["plan"]["Area"]
    assert looks.PANEL_KEYS["xsec"]["Area"] == ("xsec.ztop", "xsec.coords")
    for kind in ("sounding", "th", "line", "dist", "profile", "joint", "azim", "table", "scene"):
        assert "Area" not in looks.PANEL_KEYS[kind], kind


def test_copying_a_panel_keeps_its_area():
    doc = doc_of(panel(0, opts=dict(domain=dict(mode="box", box=[0, 4, 0, 2]))))
    doc["grid"]["cols"] = 2
    new = de.copy_panel(doc, 0, (0, 1))
    assert new["opts"]["domain"]["box"] == [0, 4, 0, 2]
    new["opts"]["domain"]["box"][0] = 1
    assert doc["panels"][0]["opts"]["domain"]["box"][0] == 0


# ------------------------------------------------------------------ on the demo run
class _Now:
    def submit(self, fn, *a):
        fn(*a)

    def shutdown(self, *a, **k):
        pass


@pytest.fixture
def shell(reg, monkeypatch):
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
    ed.shell.inspector.grid.add_panel("plan", "new column")
    yield ed.shell
    v.close()


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


def _area_card(shell):
    card = next(c for c in shell.inspector.body.objects if getattr(c, "title", None) == "Area")
    card.collapsed = False
    return card


def _in(card, name):
    return next(w for w in card.select() if getattr(w, "name", None) == name
                and hasattr(w, "value"))


def test_dragging_one_panels_area_leaves_the_other(shell):
    _drew(shell)
    a, b = (p["id"] for p in shell.doc["panels"][:2])
    was = shell.placing.place[a][4]
    shell.placing.mode.value = "area_panel"
    shell._on_drag(_event(*_at(shell, b, 0.25, 0.25), *_at(shell, b, 0.75, 0.75), 1))
    assert shell.node == f"panel:{b}"
    assert de.panel_by_id(shell.doc, b)["opts"]["domain"]["mode"] == "box"
    assert "opts" not in de.panel_by_id(shell.doc, a)
    _drew(shell)
    assert shell.placing.place[a][4] == pytest.approx(was)
    assert shell.placing.place[b][4] != pytest.approx(was)
    assert shell.placing.shown_area(b)[0] == pytest.approx(
        de.panel_by_id(shell.doc, b)["opts"]["domain"]["box"][0])
    assert "● 2" in _area_card(shell).header.object
    shell.undo()
    assert "opts" not in de.panel_by_id(shell.doc, b)


def test_dragging_all_panels_skips_and_names_one_with_its_own(shell):
    _drew(shell)
    a, b = (p["id"] for p in shell.doc["panels"][:2])
    shell.edit(lambda d: de.set_area(d, [0.0, 4.0, 0.0, 2.0], pid=b))
    _drew(shell)
    shell.placing.mode.value = "area"
    shell._on_drag(_event(*_at(shell, a, 0.25, 0.25), *_at(shell, a, 0.75, 0.75), 2))
    assert shell.doc["kinds"]["plan"]["domain"]["mode"] == "box"
    assert de.panel_by_id(shell.doc, b)["opts"]["domain"]["box"] == [0.0, 4.0, 0.0, 2.0]
    assert "keeps an area of its own" in shell.status.object


def test_a_panels_area_section_edits_marks_and_resets(shell):
    pid = shell.doc["panels"][1]["id"]
    shell.select(f"panel:{pid}")
    card = _area_card(shell)
    start = shell.doc["kinds"]["plan"]["domain"]["mode"]
    other = "storm" if start == "full" else "full"
    _in(card, "Plan-view area").value = other
    assert de.panel_by_id(shell.doc, pid)["opts"]["domain"] == dict(mode=other)
    assert "● 1" in card.header.object
    assert shell.doc["kinds"]["plan"]["domain"]["mode"] == start
    reset = next(w for w in card.select() if getattr(w, "name", "").startswith("↺"))
    reset.clicks += 1
    assert "opts" not in de.panel_by_id(shell.doc, pid)


def test_a_panels_fixed_box_starts_from_what_it_shows(shell):
    _drew(shell)
    pid = shell.doc["panels"][1]["id"]
    shell.select(f"panel:{pid}")
    shown = shell.placing.shown_area(pid)
    _in(_area_card(shell), "Plan-view area").value = "box"
    dom = de.panel_by_id(shell.doc, pid)["opts"]["domain"]
    assert dom["mode"] == "box" and dom["box"] == pytest.approx(shown, abs=0.01)


def test_find_goes_to_a_panels_area(shell):
    pid = shell.doc["panels"][1]["id"]
    shell.select(f"panel:{pid}")
    hits = [h for h in findview.hits_of(shell) if h.node == f"panel:{pid}" and h.section == "Area"]
    assert {"Fixed box", "Plan-view area"} <= {h.label for h in hits}


def test_the_height_follows_the_tallest_panel_of_a_row(shell):
    shell.doc["size_auto"] = True
    pid = shell.doc["panels"][1]["id"]
    even = shell.fit_height(shell.doc)
    shell.edit(lambda d: de.set_area(d, [0.0, 5.0, 0.0, 10.0], pid=pid))
    assert shell.fit_height(shell.doc) > even


def test_a_panels_area_saves_and_renders(shell, tmp_path):
    from cm1view.figures.batch import main
    pid = shell.doc["panels"][1]["id"]
    shell.edit(lambda d: de.set_area(d, [0.0, 5.0, 0.0, 5.0], pid=pid))
    path = fg.save_spec(de.plain(shell.doc), str(tmp_path / "f"))
    again = fg.load_spec(path)
    assert de.panel_by_id(again, pid)["opts"]["domain"]["box"] == [0.0, 5.0, 0.0, 5.0]
    assert main([path, "--out", str(tmp_path / "again.png"), "--dpi", "50"]) == 0
    assert (tmp_path / "again.png").exists()
