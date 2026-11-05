"""Distributions, profiles, joint distributions, azimuthal means and tables in the figure editor's
new layout: a profile per run, time zero, automatic sizes, names in the tree, the look rows of these
kinds, and the panes driven by their widgets."""
import os
import time

import pytest

from cm1view.figures import settings as table
from cm1view.figures.shell import docedit as de, looks, nodes
from cm1view.figures.shell.gridview import ADDABLE

KINDS = ("dist", "profile", "joint", "azim", "table")


def profile(run="r0", runs=("r0",), **more):
    return {**dict(type="profile", run=run, runs=list(runs) if runs is not None else None,
                   time_s=600.0, time_s1=None, recipe=dict(field="w"), color="", ls="", lw=1.5,
                   label="x", ens=""), **more}


def doc_of(*layers, kind="profile"):
    """A panel of a kind in a figure of two runs, the second counting from 5 min."""
    return dict(version=3, size=[9.0, 3.0], grid=dict(rows=1, cols=1), style={}, kinds={},
                runs=[dict(id="r0", path="/x/one", t0_min=0.0, label="a"),
                      dict(id="r1", path="/x/two", t0_min=5.0, label="b")],
                sections={}, layers={},
                panels=[dict(id=0, kind=kind, cell=[0, 0, 1, 1], run=None, time_s=None, title="",
                             layers=list(layers))])


# ------------------------------------------------------------------ a profile per run
def test_a_profile_of_one_run_gets_a_copy_for_each_other_at_the_same_moment():
    doc = doc_of(profile())
    p = doc["panels"][0]
    assert de.profile_per_run(doc, p, 0) == 1
    a, b = p["layers"]
    assert a["runs"] == ["r0"] and (b["run"], b["runs"]) == ("r1", ["r1"])
    assert b["time_s"] == 900.0 and (b["color"], b["label"]) == ("", "")


def test_a_run_with_the_same_profile_is_skipped():
    doc = doc_of(profile())
    p = doc["panels"][0]
    de.profile_per_run(doc, p, 0)
    assert de.profile_per_run(doc, p, 0) == 0 and len(p["layers"]) == 2


def test_a_profile_of_every_run_splits_in_the_runs_colours():
    doc = doc_of(profile(runs=None, ens="mean"))
    p = doc["panels"][0]
    assert de.profile_per_run(doc, p, 0) == 2
    a, b = p["layers"]
    assert (a["runs"], a["time_s"], b["runs"], b["time_s"]) == (["r0"], 600.0, ["r1"], 900.0)
    assert a["ens"] == "" and a["color"] and b["color"] and a["color"] != b["color"]


def test_a_time_window_moves_with_its_run_when_split():
    doc = doc_of(profile(run="r1", runs=("r1", "r0"), time_s1=1200.0))
    p = doc["panels"][0]
    de.profile_per_run(doc, p, 0)
    a, b = p["layers"]
    assert a["runs"] == ["r1"] and (a["time_s"], a["time_s1"]) == (600.0, 1200.0)
    assert b["runs"] == ["r0"] and (b["time_s"], b["time_s1"]) == (300.0, 900.0)


# ------------------------------------------------------------------ time zero
def test_time_zero_moves_a_profiles_window_but_not_your_own_data():
    doc = doc_of(profile(source="table", table=dict(t=[], v=[]), runs=(), run="r1"),
                 profile(), profile(run="r1", runs=("r1",), time_s1=900.0))
    de.set_t0(doc, "r1", 10.0)
    own, first, other = doc["panels"][0]["layers"]
    assert own["time_s"] == 600.0 and first["time_s"] == 600.0  # (first's run: stays)
    assert (other["time_s"], other["time_s1"]) == (900.0, 1200.0)


def test_time_zero_leaves_a_tables_times():
    doc = doc_of(dict(type="table", run="r0", runs=["r0"], times_s=[60.0], what="sounding"),
                 kind="table")
    de.set_t0(doc, "r0", 10.0)
    assert doc["panels"][0]["layers"][0]["times_s"] == [60.0]


# ------------------------------------------------------------------ automatic sizes
@pytest.mark.parametrize("kind, want", [("dist", (5.5, 3.9)), ("profile", (4.4, 4.9)),
                                        ("joint", (5.5, 4.3)), ("azim", (5.9, 4.1)),
                                        ("table", (7.5, 3.3))])
def test_a_figure_of_one_kind_has_the_old_editors_size(kind, want):
    doc = doc_of(kind=kind)
    assert de.kind_size(doc) == pytest.approx(want)
    de.set_grid(doc, 1, 3)
    assert de.kind_size(doc)[0] > want[0]


def test_no_size_of_its_own_for_maps_or_mixed_kinds():
    assert de.kind_size(doc_of(kind="plan")) is None
    assert de.kind_size(doc_of(kind="xsec")) is None
    doc = doc_of()
    doc["panels"].append(dict(id=1, kind="dist", cell=[0, 0, 1, 1], layers=[]))
    assert de.kind_size(doc) is None


# ------------------------------------------------------------------ names in the tree
@pytest.mark.parametrize("lay, want", [
    (profile(), "Profile · x · 10 min"),
    (profile(label="", time_s1=1200.0), "Profile · w · 10–20 min"),
    (profile(source="table", label="obs"), "Your data · obs"),
    (dict(type="dist", recipe=dict(field="w"), time_s=60.0), "Distribution · w · 1 min"),
    (dict(type="joint", recipe=dict(field="w", yfield="z"), time_s=60.0), "Joint · z vs w · 1 min"),
    (dict(type="azim", recipe=dict(field="w"), time_s=60.0), "Azimuthal · w · 1 min"),
    (dict(type="table", what="sounding", recipe={}), "Values · Sounding"),
    (dict(type="table", what="field", recipe=dict(field="w")), "Values · w")])
def test_entries_in_words(lay, want):
    assert nodes.layer_name(lay) == want


# ------------------------------------------------------------------ their look
def test_these_kinds_can_be_added_and_have_sections():
    assert set(KINDS) <= set(ADDABLE)
    for kind in KINDS:
        assert looks.KIND_SECTIONS[kind]
        assert "Panel labels" in looks.PANEL_KEYS[kind]
        for section in looks.KIND_SECTIONS[kind]:
            assert looks.rows_of(section, [kind]), (kind, section)


def test_a_kinds_legend_rows_write_its_own_block():
    for block, kind in (("dist", "dist"), ("prof", "profile"), ("joint", "joint"),
                        ("azim", "azim")):
        rows = looks.rows_of("Legend in the panel", [kind])
        assert {st.key for st in rows} == {f"{block}.legend", f"{block}.legend_loc",
                                           f"{block}.legend_ncol", f"{block}.legend_frame"}
        assert looks.OWN_NAMES[f"{block}.legend"] == "Legend"


def test_a_panels_own_rows_are_rows_of_the_table():
    keys = {st.key for st in (*table.SETTINGS, *looks.LEGEND_ROWS, *looks.EXTRA_ROWS)}
    for kind in KINDS:
        for section, own in looks.PANEL_KEYS[kind].items():
            assert set(own) <= keys, (kind, section)


# ------------------------------------------------------------------ the panes, by their widgets
class _Now:
    def submit(self, fn, *a):
        fn(*a)

    def shutdown(self, *a, **k):
        pass


@pytest.fixture
def shell(reg, monkeypatch):
    """The new layout showing the demo's example figure, drawing as it is asked."""
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


def _named(shell, name):
    for w in _walk(shell):
        if getattr(w, "name", None) == name and hasattr(w, "value") and w.visible:
            return w
    raise AssertionError(f"no {name}")


def _click(shell, name):
    for w in _walk(shell):
        if getattr(w, "name", None) == name and hasattr(w, "clicks"):
            w.clicks += 1
            return
    raise AssertionError(f"no {name}")


def _cards(shell):
    return {c.title: c for c in _walk(shell) if type(c).__name__ == "Card"}


def _drew(shell):
    t0 = time.time()
    while shell.ed.series_pending() and time.time() - t0 < 60:
        time.sleep(0.2)
    shell.request(force=True, delay=False)
    assert "Could not draw" not in shell.status.object, shell.status.object


def _fresh(shell, kind):
    """A figure of one panel of the kind, from the quick start."""
    ed = shell.ed
    ed.open_quick()
    ed.qs_kind.value = kind
    ed.qs_rows.value, ed.qs_cols.value = 1, 1
    ed._quick_make()
    assert shell.doc["panels"][0]["kind"] == kind
    return shell.doc["panels"][0]


@pytest.mark.parametrize("kind", KINDS)
def test_a_new_panel_has_an_entry_at_the_viewers_run_and_draws(shell, kind):
    p = shell.inspector.grid.add_panel(kind, "new column")
    assert shell.node == f"panel:{p['id']}"
    assert len(p["layers"]) == 1 and p["layers"][0]["type"] == kind
    assert p["layers"][0]["run"] == shell.doc["runs"][0]["id"]
    _drew(shell)
    assert p["id"] in shell._boxes


def test_every_node_of_these_kinds_shows(shell):
    for kind in KINDS:
        shell.inspector.grid.add_panel(kind)
    _drew(shell)
    for row in shell.tree.items:
        shell.select(row["id"])
        assert shell.inspector.body.objects, row["id"]
    shell.undo()
    shell.redo()


def test_a_distributions_card_edits_the_document_and_undo_goes_back(shell):
    pid = _fresh(shell, "dist")["id"]
    shell._show(f"panel:{pid}")
    _named(shell, "Only values from").value = 1.0
    assert de.panel_by_id(shell.doc, pid)["layers"][0]["recipe"]["lo"] == 1.0
    _drew(shell)
    shell.undo()
    assert de.panel_by_id(shell.doc, pid)["layers"][0]["recipe"].get("lo") is None


def test_what_a_distribution_shows_follows_its_plot(shell):
    _fresh(shell, "dist")
    shell.select("kind:dist")
    _cards(shell)["Plot"].collapsed = False
    assert _named(shell, "Bins")
    _named(shell, "Draw as").value = "ecdf"
    assert shell.doc["kinds"]["dist"]["dist"]["plot"] == "ecdf"
    assert _named(shell, "Fraction axis from")
    _named(shell, "Draw as").value = "box"
    assert "Legend in the panel" not in _cards(shell)  # (a box plot has none)
    assert not [w for w in _walk(shell) if getattr(w, "name", "") == "Bins" and w.visible]
    _drew(shell)


def test_a_panels_own_plot_stays_its_own_and_goes_back(shell):
    pid = _fresh(shell, "dist")["id"]
    other = shell.inspector.grid.copy_panel(pid)["id"]
    _cards(shell)["Plot"].collapsed = False
    _named(shell, "Draw as").value = "violin"
    assert de.panel_by_id(shell.doc, other)["opts"]["dist"]["plot"] == "violin"
    assert "opts" not in de.panel_by_id(shell.doc, pid)
    _drew(shell)
    _click(shell, "↺ Draw as")
    assert "dist" not in (de.panel_by_id(shell.doc, other).get("opts") or {})


def test_an_entry_moves_to_another_panel_of_the_kind(shell):
    pid = _fresh(shell, "dist")["id"]
    other = shell.inspector.grid.copy_panel(pid)["id"]
    shell.select(f"layer:{pid}:0")
    _named(shell, "In panel").value = other
    assert not de.panel_by_id(shell.doc, pid)["layers"]
    assert len(de.panel_by_id(shell.doc, other)["layers"]) == 2
    _drew(shell)  # (the empty panel says so)


def test_one_per_run_and_your_own_profile_data(shell, demo_run):
    pid = _fresh(shell, "profile")["id"]
    shell.add_run(os.path.join(os.path.dirname(demo_run), "supercell_weak"))
    shell._show(f"panel:{pid}")
    _click(shell, "One per run")
    assert [x["runs"] for x in de.panel_by_id(shell.doc, pid)["layers"]] == [["r0"], ["r1"]]
    _drew(shell)
    shell._show(f"layer:{pid}:0")  # (two entries: folded in the panel)
    _click(shell, "One per run")
    assert "already" in shell.status.object
    shell._show(f"panel:{pid}")
    _click(shell, "+ Your data")
    q = de.panel_by_id(shell.doc, pid)["layers"]
    assert q[-1]["source"] == "table" and q[-1]["type"] == "profile"
    box = next(w for w in _walk(shell)
               if str(getattr(w, "name", "")).startswith("Your data: height"))
    box.value = "z_km,w (m/s)\n0.5,1\n3,20\n"
    q = de.panel_by_id(shell.doc, pid)["layers"]
    assert q[-1]["table"]["t"] == [0.5, 3.0] and q[-1]["units"] == "m/s"
    _drew(shell)


def test_a_profiles_values_can_be_edited_and_undone(shell):
    pid = _fresh(shell, "profile")["id"]
    _drew(shell)
    shell._show(f"layer:{pid}:0")
    sec = next(c for t, c in _cards(shell).items() if t.startswith("Values"))
    sec.collapsed = False
    tab = next(w for w in sec.select() if type(w).__name__ == "Tabulator")
    assert len(tab.value)

    class Ev:
        column, row, value = "yours", 3, "99"

    tab._on_edit_callbacks[0](Ev)
    assert de.panel_by_id(shell.doc, pid)["layers"][0]["edits"]
    _drew(shell)
    shell.undo()
    assert not de.panel_by_id(shell.doc, pid)["layers"][0].get("edits")


def test_a_row_can_be_added_to_a_profiles_values_and_taken_out(shell):
    pid = _fresh(shell, "profile")["id"]
    _drew(shell)
    shell._show(f"layer:{pid}:0")
    sec = next(c for t, c in _cards(shell).items() if t.startswith("Values"))
    sec.collapsed = False
    tab = next(w for w in sec.select() if type(w).__name__ == "Tabulator")
    n, z = len(tab.value), tab.value["z"]
    at = round(float(z[0] + z[1]) / 2.0, 3)
    boxes = [w for w in sec.select() if type(w).__name__ == "FloatInput"]
    add = next(w for w in sec.select() if getattr(w, "name", "") == "Add row")
    add.clicks += 1  # (nothing typed: nothing added)
    assert len(tab.value) == n and not de.panel_by_id(shell.doc, pid)["layers"][0].get("edits")
    boxes[0].value, boxes[1].value = at, 99.0
    add.clicks += 1
    added = de.panel_by_id(shell.doc, pid)["layers"][0]["added"]
    assert list(added.values())[0] == {f"{at:.6g}": 99.0}
    assert len(tab.value) == n + 1 and tab.value["yours"][1] == "99"
    assert tab.value["z"].is_monotonic_increasing
    _drew(shell)

    class Ev:
        column, row, value = "yours", 1, ""

    tab._on_edit_callbacks[0](Ev)
    assert not de.panel_by_id(shell.doc, pid)["layers"][0].get("added")
    assert len(tab.value) == n


def test_what_a_joint_distribution_shows_follows_its_plot(shell):
    _fresh(shell, "joint")
    shell.select("kind:joint")
    _cards(shell)["Plot"].collapsed = False
    assert _named(shell, "Colormap")
    _named(shell, "Draw as").value = "scatter"
    assert not [w for w in _walk(shell) if getattr(w, "name", "") == "Colormap" and w.visible]
    _drew(shell)


def test_a_new_azimuthal_mean_takes_the_last_ones_recipe(shell):
    pid = _fresh(shell, "azim")["id"]
    shell._show(f"panel:{pid}")
    _named(shell, "Radius (km)").value = 12.0
    _click(shell, "+ Azimuthal mean")
    q = de.panel_by_id(shell.doc, pid)["layers"]
    assert q[1]["recipe"]["rmax"] == 12.0
    _drew(shell)


def test_a_tables_height_follows_its_rows_and_values_copy_the_last(shell):
    pid = _fresh(shell, "table")["id"]
    assert shell.can_follow() and shell.doc.get("size_auto")
    tall = shell.doc["size"][1]
    shell._show(f"panel:{pid}")
    outs = list(shell.time_opts(0).values())
    _named(shell, "Times (min)").value = ", ".join(f"{t / 60:g}" for t in outs[2:8])
    q = de.panel_by_id(shell.doc, pid)["layers"][0]
    assert len(q["times_s"]) == 6 and shell.doc["size"][1] > tall
    _drew(shell)
    _click(shell, "+ Values")
    q = de.panel_by_id(shell.doc, pid)["layers"]
    assert len(q) == 2 and q[1]["times_s"] == q[0]["times_s"]
    _drew(shell)


def test_fit_height_gives_a_kinds_size_at_once(shell):
    _fresh(shell, "dist")
    shell.doc.update(size=[3.0, 3.0], size_auto=False)
    shell._show("figure")
    _click(shell, "Fit height")
    assert shell.doc["size_auto"] and shell.doc["size"] == pytest.approx([5.5, 3.9])
