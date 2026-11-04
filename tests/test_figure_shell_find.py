"""M10: find a setting, what is changed from a new figure, and a section's reset, in the new
layout."""
import pytest

from cm1view.figures import settings as table, spec as fg
from cm1view.figures.kinds import KINDS
from cm1view.figures.shell import findview, nodes
from cm1view.figures.shell.looks import EXTRA_ROWS, Scope, _same, row_words


class _Now:
    """Runs what is submitted to it, as it is asked."""

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
    yield v.figed.shell
    v.close()


def _new_figure(shell, kind):
    ed = shell.ed
    ed.open_quick()
    ed.qs_kind.value = kind
    ed._quick_make()


def _section(shell, title):
    card = next(c for c in shell.inspector.body.objects if getattr(c, "title", None) == title)
    card.collapsed = False
    return card


def _in(card, name, nth=0):
    return [w for w in card.select() if getattr(w, "name", None) == name
            and hasattr(w, "value")][nth]


def _reset(card):
    return next(o for o in card.objects if type(o).__name__ == "Row")


# ------------------------------------------------------------------ without widgets
def test_values_that_read_the_same():
    assert _same(None, "") and _same([], None) and _same(10, 10.0) and _same([1], (1,))
    assert not _same(0, None) and not _same("a", "b") and not _same(1.0, 1.5)


def test_a_new_figures_look_differs_by_kind(reg):
    run, F = reg.get()
    plan = fg.fresh_look(run, F, 0, "plan")
    assert plan["kinds"]["plan"]["axes"]["xlabel"] == "x (km)"
    assert plan["kinds"]["plan"]["domain"]["mode"] == "storm"
    assert fg.fresh_look(run, F, 0, "plan", tracked=False)["kinds"]["plan"]["domain"]["mode"] == "full"
    snd = fg.fresh_look(run, F, 0, "sounding")
    assert snd["style"]["letters"]["loc"] == KINDS["sounding"].letter_at
    assert "domain" not in snd["kinds"]["sounding"] and "skewt" in snd["kinds"]["sounding"]
    th = fg.fresh_look(run, F, 0, "th")
    assert th["style"]["time_label"]["on"] is False and th["style"]["colorbar"]["mode"] == "row"
    assert th["style"]["colorbar"]["location"] == "right"


def test_search_ranks_the_name_first_and_needs_every_word():
    Hit = findview.Hit
    a = Hit("Frame width (pt)", "Axes", "Figure", "figure", "axes.frame_lw", "")
    b = Hit("Width (in)", None, "Figure", "figure", None, "size figure")
    c = Hit("Colormap", None, "Layers", "kind:plan", None, "cmap palette colours")
    assert findview.search([a, b], "width")[0] is b
    assert findview.search([a, b], "width frame") == [a]
    assert findview.search([a, b, c], "palette") == [c]
    assert findview.search([a, b, c], "   ") == []
    # (either spelling, and a colour bar is a colorbar)
    assert findview.search([Hit("Colorbar", None, "x", "n", None, "")], "colour bar")


# ------------------------------------------------------------------ new figures read as unchanged
@pytest.mark.parametrize("kind", ["plan", "xsec", "line", "sounding", "dist", "profile", "joint",
                                  "azim", "table", "scene"])
def test_nothing_is_changed_in_a_new_figure(shell, kind):
    _new_figure(shell, kind)
    for node in (nodes.FIGURE, f"kind:{kind}"):
        shell._show(node)
        for looks in shell.inspector.live:
            for section, marks in looks.live.items():
                assert [st.key for st in marks["rows"]
                        if looks._is_changed(shell.doc, st)] == [], (node, section)


# ------------------------------------------------------------------ marks follow the edits
def test_a_change_is_marked_and_a_reset_undoes_one_step(shell):
    _new_figure(shell, "plan")
    shell._show(nodes.FIGURE)
    card = _section(shell, "Text")
    assert card.header is None and not _reset(card).visible
    w = _in(card, "Panel titles (pt)")
    w.value = 15.0
    assert "● 1" in card.header.object and card.title == "Text"
    assert "box-shadow" in w.styles
    line = _reset(card)
    assert line.visible and "Panel titles" in line[0].object
    _in(card, "Tick labels (pt)").value = 9.0
    assert "● 2" in card.header.object
    was = len(shell._hist)
    line[1].clicks += 1
    assert len(shell._hist) == was + 1
    font = shell.doc["style"]["font"]
    assert font["title"] is None and font["tick"] is None
    card = _section(shell, "Text")
    assert card.header is None and not _reset(card).visible
    assert _in(card, "Panel titles (pt)").value is None
    shell.undo()
    assert shell.doc["style"]["font"]["title"] == 15.0
    assert "● 2" in _section(shell, "Text").header.object


def test_folded_sections_count_too_and_an_edit_elsewhere_updates_them(shell):
    _new_figure(shell, "plan")
    shell._show(nodes.FIGURE)
    card = next(c for c in shell.inspector.body.objects if getattr(c, "title", None) == "Spacing")
    assert card.collapsed and card.header is None
    shell.edit(lambda d: d["style"]["spacing"].update(wspace=0.3))
    assert "● 1" in card.header.object and card.collapsed and not card.objects


def test_a_kinds_reset_goes_to_its_own_new_figure_and_skips_what_panels_set(shell):
    _new_figure(shell, "plan")
    ins = shell.inspector
    ins.go_to("kind:plan", "Axes and ticks")
    card = ins.body.objects[0]
    _in(card, "x label").value = "mine"
    shell.edit(lambda d: d["panels"][1].setdefault("opts", {}).update(axes=dict(tickdir="in")))
    _reset(card)[1].clicks += 1
    assert shell.doc["kinds"]["plan"]["axes"]["xlabel"] == "x (km)"
    assert shell.doc["panels"][1]["opts"]["axes"]["tickdir"] == "in"
    assert "Panel b keeps what it set alone" in shell.status.object


def test_a_panel_marks_its_own_and_goes_back_to_inheriting(shell):
    _new_figure(shell, "plan")
    pid = shell.doc["panels"][0]["id"]
    ins = shell.inspector
    ins.go_to(f"panel:{pid}", "Axes and ticks")
    card = ins.body.objects[0]
    assert card.header is None
    _in(card, "Ticks point").value = "in"
    assert "● 1" in card.header.object
    assert _reset(card)[1].name == "↺ Use the setting for all panels"
    _reset(card)[1].clicks += 1
    assert "opts" not in shell.doc["panels"][0]


def test_letters_go_back_to_following_the_count(shell):
    _new_figure(shell, "plan")
    ins = shell.inspector
    ins.go_to(nodes.FIGURE, "Panel labels")
    card = ins.body.objects[0]
    _in(card, "Panel letters").value = False
    assert shell.doc["style"]["letters"]["auto"] is False
    assert "● 1" in card.header.object
    _reset(card)[1].clicks += 1
    letters = shell.doc["style"]["letters"]
    assert letters["auto"] is True and letters["on"] is True


def test_area_counts_its_box_while_it_is_used_and_resets_it(shell):
    _new_figure(shell, "plan")
    ins = shell.inspector
    ins.go_to("kind:plan", "Area")
    card = ins.body.objects[0]
    start = shell.doc["kinds"]["plan"]["domain"]["mode"]
    _in(card, "Plan-view area").value = "box"
    dom = shell.doc["kinds"]["plan"]["domain"]
    assert dom["mode"] == "box" and dom["box"]
    assert "● 2" in card.header.object
    _reset(card)[1].clicks += 1
    dom = shell.doc["kinds"]["plan"]["domain"]
    assert dom["mode"] == start and dom["box"] is None


def test_a_kinds_own_colorbar_goes_back_to_the_figures(shell):
    _new_figure(shell, "plan")
    shell.inspector.grid.add_panel("sounding")
    shell.edit(lambda d: d["kinds"]["plan"].update(colorbar=dict(
        shrink=0.3, location="right", orientation="vertical")))
    shell._show("kind:plan")
    card = _section(shell, "Colorbar")
    assert "● 2" in card.header.object
    line = _reset(card)
    assert line[1].name == "↺ Back to the figure's"
    line[1].clicks += 1
    assert "colorbar" not in shell.doc["kinds"]["plan"]


def test_your_own_code_has_no_reset_but_is_marked(shell):
    _new_figure(shell, "plan")
    shell.edit(lambda d: d["code"].update(text="print(1)"))
    shell._show(nodes.FIGURE)
    card = _section(shell, "Your own code")
    assert "● 1" in card.header.object
    assert not [o for o in card.objects if type(o).__name__ == "Row"]


def test_an_odd_value_is_no_reason_to_fail(shell):
    _new_figure(shell, "plan")
    shell.edit(lambda d: d["style"]["spacing"].update(wspace="odd"))
    shell._show(nodes.FIGURE)
    card = next(c for c in shell.inspector.body.objects if getattr(c, "title", None) == "Spacing")
    assert card.title == "Spacing"


def test_extra_rows_and_every_row_have_a_name(shell):
    keys = [st.key for st in (*table.SETTINGS, *EXTRA_ROWS)]
    words = row_words(shell.ed, keys)
    assert all(words[k] for k in keys)
    assert Scope._names_in(next(st for st in table.SETTINGS if st.key == "colorbar.*")) == [
        "location", "orientation"]


# ------------------------------------------------------------------ find
def test_find_lists_only_what_this_figure_has(shell):
    _new_figure(shell, "plan")
    f = shell.inspector.finder
    f.box.value_input = "hodograph"
    assert not f.hits and not f.rows.visible and "Nothing here" in f.note.object
    f.box.value_input = "colour bar len"
    assert f.rows.visible and f.rows.items[0]["label"].startswith("Length (0–1) — Colorbar")
    f.box.value_input = ""
    assert not f.hits and not f.rows.visible and f.note.object == ""


def test_finding_pins_the_section_open_and_marks_the_setting(shell):
    _new_figure(shell, "plan")
    ins = shell.inspector
    f = ins.finder
    f.box.value_input = "panel titles"
    assert f.hits["0"].label == "Panel titles (pt)"
    f.pick("0")
    assert shell.node == nodes.FIGURE and f.box.value_input == "" and not f.rows.visible
    card = ins.body.objects[0]
    assert card.title == "Text" and not card.collapsed
    assert "outline" in _in(card, "Panel titles (pt)").styles
    assert "Panel titles" in f.note.object
    # (it keeps its place through an edit; another node ends it)
    shell.edit(lambda d: None, node=nodes.FIGURE)
    assert ins.body.objects[0].title == "Text"
    assert "outline" not in _in(ins.body.objects[0], "Panel titles (pt)").styles
    shell.select(nodes.RUNS)
    assert ins.pin is None and f.note.object == ""
    shell.select(nodes.FIGURE)
    assert getattr(ins.body.objects[0], "title", None) != "Text"


def test_find_and_marks_with_the_page_built(shell):
    """With models made, as in a browser: a ReactiveHTML's list can't be emptied then."""
    from bokeh.document import Document
    ins = shell.inspector
    root = ins.panel.get_root(Document())
    f = ins.finder
    f.box.value_input = "panel titles"
    f.box.value_input = ""
    f.box.value_input = "panel titles"
    f.pick("0")
    card = ins.body.objects[0]
    _in(card, "Panel titles (pt)").value = 14.0
    assert "● 1" in card.header.object
    _reset(card)[1].clicks += 1
    assert ins.body.objects[0].header is None
    assert root is not None


def test_find_offers_the_panel_picked_first(shell):
    _new_figure(shell, "plan")
    pid = shell.doc["panels"][1]["id"]
    shell._show(f"panel:{pid}")
    f = shell.inspector.finder
    f.box.value_input = "ticks point"
    assert f.hits["0"].node == f"panel:{pid}"
    assert f.hits["1"].node == "kind:plan"
    f.first()
    assert shell.node == f"panel:{pid}"
    assert shell.inspector.body.objects[0].title == "Axes and ticks"


def test_find_says_when_a_section_is_left_out(shell):
    _new_figure(shell, "sounding")
    shell.edit(lambda d: d["kinds"]["sounding"]["skewt"].update(layout="hodo"))
    f = shell.inspector.finder
    f.box.value_input = "skew"
    hit = next(h for h in f.hits.values() if h.section == "Skew-T")
    shell.inspector.go_to(hit.node, hit.section, hit.key)
    assert "isn't shown here" in f.note.object


def test_find_goes_to_the_export_dialog(shell, monkeypatch):
    opened = []
    monkeypatch.setattr(shell.export, "open", lambda: opened.append(1))
    f = shell.inspector.finder
    f.box.value_input = "dpi"
    assert f.hits["0"].node == findview.EXPORT and f.rows.items[0]["label"] == "DPI — Export"
    node = shell.node
    f.pick("0")
    assert opened == [1] and shell.node == node


def test_every_hit_opens_where_it_says(shell):
    _new_figure(shell, "plan")
    hits = [h for h in findview.hits_of(shell) if h.node != findview.EXPORT]
    assert all(nodes.still_there(shell.doc, h.node) for h in hits)
    for node, section in {(h.node, h.section) for h in hits if h.section}:
        shell.inspector.go_to(node, section)
        title = shell.inspector.body.objects[0].title
        assert title == section or title.startswith(f"{section} ("), (node, section)
