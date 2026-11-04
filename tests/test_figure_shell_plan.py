"""Plan views in the figure editor's new layout: what a shared edit and a panel's edit reach,
overrides, moving layers, a panel's height, time zero, the Fill panels tool, the look settings,
what stays open across undo, and the quick start."""
import copy
import json
import os

import numpy as np
import pytest

from conftest import new_spec

from cm1view.figures import draw as figdraw
from cm1view.figures.shell import docedit as de, looks


def small():
    """Three plan views over a shared fill and contours: b's fill differs, c has its own
    shading."""
    fill = dict(type="fill", on=True, field="dbz", mode="height", z=1.0, vmin=0.0, vmax=60.0)
    cont = dict(type="contour", on=True, field="w", mode="height", z=3.0, levels="5, 10")
    return dict(
        version=3, size=[8.0, 3.0], grid=dict(rows=1, cols=3), style={}, kinds={}, sections={},
        runs=[dict(id="r0", path="/x/one"), dict(id="r1", path="/x/two", t0_min=0.0)],
        layers={"l0": fill, "l1": cont},
        panels=[
            dict(id=0, kind="plan", cell=[0, 0, 1, 1], run="r0", time_s=600.0, title="",
                 layers=[dict(ref="l0", over={}), dict(ref="l1", over={})]),
            dict(id=1, kind="plan", cell=[0, 1, 1, 1], run="r0", time_s=1200.0, title="",
                 layers=[dict(ref="l0", over=dict(vmax=40.0)), dict(ref="l1", over={})]),
            dict(id=2, kind="plan", cell=[0, 2, 1, 1], run="r0", time_s=1800.0, title="",
                 layers=[dict(ref="l0", over={}), dict(type="shade", on=True, field="w", z=2.0),
                         dict(ref="l1", over={})])])


def panel(doc, pid):
    return de.panel_by_id(doc, pid)


def drawn(doc, pid):
    return [lay for _, lay in figdraw.panel_layers(doc, panel(doc, pid))]


# ------------------------------------------------------------------ what an edit reaches
def test_a_shared_edit_skips_what_a_panel_set():
    doc = small()
    de.write_shared(doc, "l0", dict(vmax=70.0, vmin=5.0))
    assert drawn(doc, 0)[0]["vmax"] == 70.0
    assert drawn(doc, 1)[0]["vmax"] == 40.0 and drawn(doc, 1)[0]["vmin"] == 5.0


def test_a_panel_edit_stays_in_the_panel_and_a_value_back_at_the_shared_one_goes():
    doc = small()
    de.write_panel(doc, panel(doc, 0), 0, dict(vmin=2.0))
    assert panel(doc, 0)["layers"][0]["over"] == dict(vmin=2.0)
    assert doc["layers"]["l0"]["vmin"] == 0.0 and drawn(doc, 2)[0]["vmin"] == 0.0
    de.write_panel(doc, panel(doc, 0), 0, dict(vmin=0.0))
    assert panel(doc, 0)["layers"][0]["over"] == {}


def test_a_panel_can_say_a_shared_key_is_gone():
    doc = small()
    doc["layers"]["l0"]["minus"] = dict(run="r1")
    de.write_panel(doc, panel(doc, 0), 0, dict(minus=de.MISSING))
    assert panel(doc, 0)["layers"][0]["over"] == dict(minus=None)
    assert drawn(doc, 0)[0]["minus"] is None and drawn(doc, 1)[0]["minus"] == dict(run="r1")


def test_a_panels_own_layer_is_edited_as_it_is():
    doc = small()
    de.write_panel(doc, panel(doc, 2), 1, dict(z=4.0, lw=de.MISSING))
    assert panel(doc, 2)["layers"][1]["z"] == 4.0


def test_clear_one_override_or_all():
    doc = small()
    de.write_panel(doc, panel(doc, 1), 0, dict(vmin=3.0))
    de.clear_over(doc, panel(doc, 1), 0, "vmin")
    assert panel(doc, 1)["layers"][0]["over"] == dict(vmax=40.0)
    de.clear_over(doc, panel(doc, 1), 0)
    assert panel(doc, 1)["layers"][0]["over"] == {}


def test_what_differs_leaves_out_a_panels_height_and_whether_it_draws_it():
    doc = small()
    assert de.differing(doc, "l0", "plan") == {1: ["vmax"]}
    de.set_height(doc, panel(doc, 2), 6.0)
    de.in_panel(doc, panel(doc, 0), "l0", False)
    assert de.differing(doc, "l0", "plan") == {1: ["vmax"]}


def test_all_as_shared_keeps_which_panels_draw_it_and_their_heights():
    doc = small()
    de.set_height(doc, panel(doc, 2), 6.0)
    de.in_panel(doc, panel(doc, 0), "l0", False)
    de.clear_shared_over(doc, "l0", "plan")
    assert panel(doc, 0)["layers"][0]["over"] == dict(on=False)
    assert panel(doc, 1)["layers"][0]["over"] == {}
    assert drawn(doc, 2)[0]["z"] == 6.0


# ------------------------------------------------------------------ shared layers
def test_add_copy_remove_shared():
    doc = small()
    lid = de.add_shared(doc, "plan", dict(type="vectors", on=True, z=0.0))
    assert all(panel(doc, i)["layers"][-1] == dict(ref=lid, over={}) for i in (0, 1, 2))
    new = de.copy_shared(doc, "plan", "l0")
    assert list(doc["layers"])[:2] == ["l0", new]
    assert panel(doc, 1)["layers"][1] == dict(ref=new, over=dict(vmax=40.0))  # (what differed)
    de.remove_shared(doc, "plan", new)
    assert new not in doc["layers"] and len(panel(doc, 1)["layers"]) == 3


def test_a_layer_other_kinds_draw_stays_when_plan_views_drop_it():
    doc = small()
    doc["panels"].append(dict(id=3, kind="xsec", cell=[0, 2, 1, 1], layers=[dict(ref="l1")]))
    de.remove_shared(doc, "plan", "l1")
    assert "l1" in doc["layers"] and not any(
        x.get("ref") == "l1" for x in panel(doc, 0)["layers"])


def test_moving_a_shared_layer_leaves_a_panels_own_in_its_place():
    doc = small()
    de.move_shared(doc, "plan", "l1", -1)
    assert list(doc["layers"]) == ["l1", "l0"]
    assert [x.get("ref") for x in panel(doc, 0)["layers"]] == ["l1", "l0"]
    assert [x.get("ref", x.get("type")) for x in panel(doc, 2)["layers"]] == ["l1", "shade", "l0"]
    assert panel(doc, 1)["layers"][1]["over"] == dict(vmax=40.0)  # (goes with its layer)
    de.move_shared(doc, "plan", "l1", -1)  # (already first)
    assert list(doc["layers"]) == ["l1", "l0"]


def test_in_panels_turns_a_layer_off_keeping_what_differs_and_adds_it_where_it_was_not():
    doc = small()
    de.in_panel(doc, panel(doc, 1), "l0", False)
    assert panel(doc, 1)["layers"][0]["over"] == dict(vmax=40.0, on=False)
    assert not de.draws(doc, panel(doc, 1), "l0") and de.draws(doc, panel(doc, 0), "l0")
    de.in_panel(doc, panel(doc, 1), "l0", True)
    assert panel(doc, 1)["layers"][0]["over"] == dict(vmax=40.0)
    panel(doc, 0)["layers"] = [dict(ref="l1", over={})]
    de.in_panel(doc, panel(doc, 0), "l0", True)
    assert [x["ref"] for x in panel(doc, 0)["layers"]] == ["l1", "l0"]


def test_a_shared_layer_that_is_off_stays_off_in_panels_not_told_otherwise():
    doc = small()
    doc["layers"]["l1"]["on"] = False
    assert not de.draws(doc, panel(doc, 0), "l1")
    de.in_panel(doc, panel(doc, 0), "l1", True)
    assert panel(doc, 0)["layers"][1]["over"]["on"] is True


# ------------------------------------------------------------------ layers of a panel
def test_a_panels_layers_copy_move_remove_alone():
    doc = small()
    de.copy_in_panel(doc, panel(doc, 1), 0)
    assert panel(doc, 1)["layers"][1]["vmax"] == 40.0 and "ref" not in panel(doc, 1)["layers"][1]
    assert len(panel(doc, 0)["layers"]) == 2
    assert de.move_in_panel(doc, panel(doc, 1), 1, 1) == 2
    assert panel(doc, 1)["layers"][1]["ref"] == "l1"
    de.remove_in_panel(doc, panel(doc, 1), 0)
    assert "l0" in doc["layers"]  # (others draw it)
    de.remove_in_panel(doc, panel(doc, 0), 0)
    de.remove_in_panel(doc, panel(doc, 2), 0)
    assert "l0" not in doc["layers"]  # (the last that drew it)


def test_runs_go_to_a_card_by_place_and_back_by_id():
    doc = small()
    lay = dict(type="fill", run="r1", minus=dict(run="r0"), ens=dict(runs=["r1", "r0"]))
    card = de.to_card(doc, lay)
    assert (card["run"], card["minus"]["run"], card["ens"]["runs"]) == (1, 0, [1, 0])
    assert de.from_card(doc, card) == lay
    assert de.from_card(doc, dict(run=9))["run"] == "gone"


# ------------------------------------------------------------------ a panel's height
def test_a_panels_height_reaches_its_layers_at_a_height():
    doc = small()
    doc["layers"]["l1"]["z_fixed"] = True
    de.set_height(doc, panel(doc, 0), 6.0)
    assert panel(doc, 0)["z"] == 6.0
    assert drawn(doc, 0)[0]["z"] == 6.0 and drawn(doc, 0)[1]["z"] == 3.0  # (its own height)
    assert drawn(doc, 1)[0]["z"] == 1.0
    de.set_height(doc, panel(doc, 0), None)
    assert "z" not in panel(doc, 0) and panel(doc, 0)["layers"][0]["over"] == {}


def test_a_model_level_makes_its_layers_read_that_level():
    doc = small()
    de.set_height(doc, panel(doc, 0), 7.0, "level")
    assert drawn(doc, 0)[0]["mode"] == "level" and drawn(doc, 0)[0]["z"] == 7.0
    de.set_height(doc, panel(doc, 0), None)
    assert drawn(doc, 0)[0]["mode"] == "height"


def test_a_new_layer_takes_the_height_of_panels_that_have_one():
    doc = small()
    de.set_height(doc, panel(doc, 0), 6.0)
    lid = de.add_shared(doc, "plan", dict(type="fill", on=True, field="w", z=1.0))
    assert drawn(doc, 0)[-1]["z"] == 6.0 and drawn(doc, 1)[-1]["z"] == 1.0
    assert doc["layers"][lid]["z"] == 1.0


def test_own_height_ticked_on_the_shared_layer_shows_the_shared_height():
    doc = small()
    de.set_height(doc, panel(doc, 0), 6.0)
    de.write_shared(doc, "l0", dict(z_fixed=True))
    assert drawn(doc, 0)[0]["z"] == 1.0


def test_own_height_ticked_in_the_panel_keeps_its_z():
    doc = small()
    de.set_height(doc, panel(doc, 0), 6.0)
    de.write_panel(doc, panel(doc, 0), 0, dict(z_fixed=True, z=2.5))
    assert drawn(doc, 0)[0]["z"] == 2.5


# ------------------------------------------------------------------ time zero
def two_runs():
    doc = small()
    panel(doc, 1)["run"] = "r1"
    panel(doc, 2)["run"] = "r1"
    return doc


def test_time_zero_of_a_run_moves_its_panels_to_stay_lined_up():
    doc = two_runs()
    de.set_t0(doc, "r1", 5.0)
    assert doc["runs"][1]["t0_min"] == 5.0
    assert [panel(doc, i)["time_s"] for i in (0, 1, 2)] == [600.0, 1500.0, 2100.0]


def test_time_zero_of_the_reference_run_moves_the_others():
    doc = two_runs()
    de.set_t0(doc, "r0", 5.0)
    assert [panel(doc, i)["time_s"] for i in (0, 1, 2)] == [600.0, 900.0, 1500.0]


def test_time_zero_of_a_figure_of_one_run_only_relabels():
    doc = small()
    de.set_t0(doc, "r0", 5.0)
    assert [panel(doc, i)["time_s"] for i in (0, 1, 2)] == [600.0, 1200.0, 1800.0]


def test_time_zero_keeps_times_when_runs_pair_by_output_number():
    doc = two_runs()
    doc["runs"][1]["outputs_s"] = [0.0, 1200.0]
    de.set_t0(doc, "r1", 5.0)
    assert panel(doc, 1)["time_s"] == 1200.0


# ------------------------------------------------------------------ fill panels
def test_fill_by_time_writes_ordinary_panels_and_layers_stay():
    doc = small()
    made, gone = de.fill_panels(doc, 2, 2, "none", "times",
                                dict(times=[0.0, 300.0, 600.0, 900.0]), run="r0")
    assert (made, gone) == (4, 0) and doc["grid"]["rows"] == 2
    cells = {tuple(p["cell"][:2]): p for p in doc["panels"]}
    assert sorted(p["time_s"] for p in doc["panels"]) == [0.0, 300.0, 600.0, 900.0]
    assert cells[(1, 1)]["time_s"] == 900.0 and cells[(0, 1)]["time_s"] == 300.0
    assert "steps" not in doc and "rule" not in doc["grid"]
    assert panel(doc, 1)["layers"][0]["over"] == dict(vmax=40.0)  # (layers stay)
    assert panel(doc, 3)["layers"] == [dict(ref="l0", over={}), dict(ref="l1", over={})]


def test_fill_a_panel_already_at_a_step_goes_there_keeping_what_was_set_on_it():
    doc = small()
    panel(doc, 1)["title"] = "kept"
    de.fill_panels(doc, 1, 3, "none", "times", dict(times=[1200.0, 1800.0, 2400.0]), run="r0")
    assert panel(doc, 1)["cell"][:2] == [0, 0] and panel(doc, 1)["title"] == "kept"
    assert panel(doc, 2)["cell"][:2] == [0, 1]
    assert panel(doc, 0)["time_s"] == 2400.0  # (the one left takes what is left)


def test_fill_fewer_cells_says_how_many_went_and_the_rest_is_gone():
    doc = small()
    made, gone = de.fill_panels(doc, 1, 2, "none", "times", dict(times=[600.0, 1200.0]), run="r0")
    assert (made, gone) == (2, 1) and {p["id"] for p in doc["panels"]} == {0, 1}


def test_fill_an_empty_step_is_an_empty_cell():
    doc = small()
    de.fill_panels(doc, 1, 3, "none", "times", dict(times=[600.0, None, 1800.0]), run="r0")
    assert [tuple(p["cell"][:2]) for p in doc["panels"]] == [(0, 0), (0, 2)]


def test_fill_runs_by_times_moves_times_with_time_zero():
    doc = small()
    doc["runs"][1]["t0_min"] = 5.0
    de.fill_panels(doc, 2, 2, "runs", "times", dict(runs=["r0", "r1"], times=[600.0, 1200.0]))
    cells = {tuple(p["cell"][:2]): p for p in doc["panels"]}
    assert (cells[(0, 0)]["run"], cells[(0, 0)]["time_s"]) == ("r0", 600.0)
    assert (cells[(1, 1)]["run"], cells[(1, 1)]["time_s"]) == ("r1", 1500.0)


def test_fill_heights_writes_each_panels_height_and_leaving_them_clears_it():
    doc = small()
    de.fill_panels(doc, 1, 3, "none", "heights", dict(heights=[1.0, 3.0, 6.0]), run="r0",
                   time_s=600.0)
    assert [p["z"] for p in doc["panels"]] == [1.0, 3.0, 6.0]
    assert {p["time_s"] for p in doc["panels"]} == {600.0}
    assert drawn(doc, doc["panels"][2]["id"])[0]["z"] == 6.0
    de.fill_panels(doc, 1, 3, "none", "times", dict(times=[0.0, 60.0, 120.0]), run="r0")
    assert all("z" not in p for p in doc["panels"])
    assert drawn(doc, doc["panels"][2]["id"])[0]["z"] == 1.0


def test_fill_fields_change_each_panels_first_fill():
    doc = small()
    d = dict(field="w", vmin=-10.0, vmax=10.0, z=9.0, type="fill", on=True, mode="height")
    e = dict(d, field="dbz", vmin=0.0, vmax=60.0)
    de.fill_panels(doc, 1, 2, "none", "fields", dict(fields=[d, e]), run="r0", time_s=600.0)
    first = doc["panels"][0]
    assert drawn(doc, first["id"])[0]["field"] == "w"
    assert drawn(doc, first["id"])[0]["z"] == 1.0  # (the height isn't a field's)
    assert drawn(doc, doc["panels"][1]["id"])[0]["field"] == "dbz"
    assert doc["layers"]["l0"]["field"] == "dbz"


def test_fill_another_grid_shape_forgets_the_old_ratios():
    doc = small()
    doc["grid"].update(widths=[1, 2, 3])
    de.fill_panels(doc, 1, 3, "none", "times", dict(times=[0.0, 1.0, 2.0]), run="r0")
    assert doc["grid"]["widths"] == [1, 2, 3]
    de.fill_panels(doc, 1, 2, "none", "times", dict(times=[0.0, 1.0]), run="r0")
    assert "widths" not in doc["grid"]


def test_fill_keeps_off_cells_other_kinds_hold():
    doc = small()
    doc["panels"].append(dict(id=7, kind="sounding", cell=[1, 0, 1, 1], layers=[]))
    de.fill_panels(doc, 2, 1, "none", "times", dict(times=[0.0, 60.0]), run="r0")
    assert {tuple(p["cell"][:2]) for p in doc["panels"] if p["kind"] == "plan"} == {(0, 0)}
    assert panel(doc, 7)["cell"][:2] == [1, 0]


def test_fill_letters_that_follow_the_count():
    doc = small()
    doc["style"]["letters"] = dict(on=True, auto=True)
    de.fill_panels(doc, 1, 1, "none", "none", {}, run="r0", time_s=600.0)
    assert doc["style"]["letters"]["on"] is False
    doc["style"]["letters"] = dict(on=True)  # (set by hand)
    de.fill_panels(doc, 1, 1, "none", "none", {}, run="r0", time_s=600.0)
    assert doc["style"]["letters"]["on"] is True


def test_guess_reads_how_the_panels_are_now():
    doc = small()
    was = de.guess_fill(doc)
    assert (was["rows"], was["cols"], was["row_dim"], was["col_dim"]) == (1, 3, "none", "times")
    assert was["times"] == [600.0, 1200.0, 1800.0] and was["runs"] == ["r0"]
    doc = two_runs()
    was = de.guess_fill(doc)
    assert (was["row_dim"], was["col_dim"]) == ("runs", "times")


def test_titles_from_what_differs():
    doc = small()
    doc["runs"][0]["label"], doc["runs"][1]["label"] = "One", "Two"
    panel(doc, 1)["run"] = "r1"
    panel(doc, 2)["run"] = "r1"
    de.auto_titles(doc)
    assert [p["title"] for p in doc["panels"]] == ["One", "Two", "Two"]
    assert doc["style"]["run_label"]["on"] is False


def test_titles_of_panels_in_time_name_the_field():
    doc = small()
    de.auto_titles(doc)
    assert {p["title"] for p in doc["panels"]} == {"dbz"}


def test_titles_of_rows_and_columns_go_on_top_and_left():
    doc = small()
    doc["runs"][0]["label"], doc["runs"][1]["label"] = "One", "Two"
    doc["style"]["time_label"] = dict(fmt="{min:g} min")
    de.fill_panels(doc, 2, 2, "runs", "times", dict(runs=["r0", "r1"], times=[600.0, 1200.0]))
    de.set_t0(doc, "r1", 5.0)
    de.auto_titles(doc)
    cells = {tuple(p["cell"][:2]): p for p in doc["panels"]}
    assert (cells[(0, 0)]["title"], cells[(0, 1)]["title"]) == ("10 min", "20 min")
    assert (cells[(1, 0)]["title"], cells[(1, 1)]["title"]) == ("", "")
    assert (cells[(0, 0)]["rowlabel"], cells[(1, 0)]["rowlabel"]) == ("One", "Two")
    assert "rowlabel" not in cells[(0, 1)]


# ------------------------------------------------------------------ look at each scope
class _St:
    """A row of the settings table, enough for Scope."""

    def __init__(self, key, default=None):
        from cm1view.figures.settings import RAW
        self.key, self.default, self.as_ = key, default, RAW


def test_look_goes_to_the_style_the_kind_or_the_panel():
    doc = small()
    doc["style"]["font"] = dict(size=10.0)
    doc["kinds"]["plan"] = dict(axes=dict(xlabel="x"))
    figure, kind, one = looks.Scope(), looks.Scope("plan"), looks.Scope("plan", 1)
    figure.write(doc, _St("font.size"), 12.0)
    assert doc["style"]["font"]["size"] == 12.0
    kind.write(doc, _St("axes.xlabel"), "km")
    assert doc["kinds"]["plan"]["axes"]["xlabel"] == "km"
    one.write(doc, _St("axes.xlabel"), "own")
    assert panel(doc, 1)["opts"]["axes"]["xlabel"] == "own"
    assert one.value(doc, _St("axes.xlabel")) == "own"
    assert kind.value(doc, _St("axes.xlabel")) == "km"
    assert looks.Scope("plan", 0).value(doc, _St("axes.xlabel")) == "km"
    assert one.value(doc, _St("font.size")) == 12.0


def test_look_of_a_kinds_block_from_the_figure_reaches_every_kind():
    doc = small()
    doc["kinds"] = dict(plan=dict(axes={}), sounding=dict(axes={}))
    looks.Scope().write(doc, _St("axes.title_bold"), False)
    assert doc["kinds"]["sounding"]["axes"]["title_bold"] is False
    assert doc["kinds"]["plan"]["axes"]["title_bold"] is False


def test_look_a_panels_own_goes_back():
    doc = small()
    one = looks.Scope("plan", 1)
    one.write(doc, _St("axes.xlabel"), "own")
    assert one.own_keys(doc, ["axes.xlabel", "axes.ylabel"]) == ["axes.xlabel"]
    assert looks.panels_differ(doc, "plan", ["axes.xlabel"]) == {"b": ["axes.xlabel"]}
    one.take_back(doc, "axes.xlabel")
    assert "opts" not in panel(doc, 1)


def test_letters_set_by_hand_stop_following_the_panel_count():
    doc = small()
    doc["style"]["letters"] = dict(on=True, auto=True)
    looks.Scope().write(doc, _St("letters.on"), False)
    assert doc["style"]["letters"] == dict(on=False, auto=False)


def test_every_section_named_has_rows_and_no_row_names_a_panel_by_place():
    for sec in (*looks.FIGURE_SECTIONS, *looks.KIND_SECTIONS["plan"]):
        rows = looks.rows_of(sec, ["plan"])
        assert rows, sec
        assert not {st.key for st in rows} & {"legend.panel", "legend.panels", "xsec.ztop"}
    keys = {st.key for rows in [looks.rows_of(s, ["plan"]) for s in looks.PANEL_KEYS["plan"]]
            for st in rows}
    extras = {st.key for st in looks.EXTRA_ROWS}  # (a section's extras: the fixed box)
    for wanted in looks.PANEL_KEYS["plan"].values():
        assert set(wanted) <= keys | extras


# ------------------------------------------------------------------ on the demo run
class _Now:
    def submit(self, fn, *a):
        fn(*a)

    def shutdown(self, *a, **kw):
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
    v.figed.shell.open()
    yield v.figed.shell
    v.close()


def named(col, name):
    for w in col.select():
        if getattr(w, "name", None) == name and hasattr(w, "value"):
            return w
    raise AssertionError(f"no {name}")


def in_panel_doc(shell, pid):
    return next(p for p in shell.doc["panels"] if p["id"] == pid)


def test_all_plan_views_edits_the_shared_layer_and_a_panel_its_override(shell):
    lid = next(iter(shell.doc["layers"]))
    shell.select("kind:plan")
    named(shell.inspector.body, "Min").value = 5.0
    assert shell.doc["layers"][lid]["vmin"] == 5.0
    assert in_panel_doc(shell, 1)["layers"][0]["over"] == {}
    shell.select("layer:1:0")
    assert "panel b only" in shell.inspector.head.object
    box = named(shell.inspector.body, "Min")
    assert box.value == 5.0
    box.value = 10.0
    assert in_panel_doc(shell, 1)["layers"][0]["over"] == dict(vmin=10.0)
    assert shell.doc["layers"][lid]["vmin"] == 5.0
    assert "Could not draw" not in shell.status.object


def test_changing_a_setting_writes_only_that_setting(shell):
    shell.select("layer:2:0")
    named(shell.inspector.body, "Max").value = 33.0
    assert in_panel_doc(shell, 2)["layers"][0]["over"] == dict(vmax=33.0)  # (no other key)
    shell.select("kind:plan")
    before = copy.deepcopy(shell.doc["layers"])
    named(shell.inspector.body, "Max").value = 44.0
    lid = next(iter(before))
    before[lid]["vmax"] = 44.0
    assert shell.doc["layers"] == before


def test_a_shared_edit_says_who_differs_and_all_as_shared_clears_them(shell):
    shell.select("layer:1:0")
    named(shell.inspector.body, "Max").value = 33.0
    shell.select("kind:plan")
    words = " ".join(str(getattr(o, "object", "")) for o in shell.inspector.body.select())
    assert "1 panel differs (b)" in words
    next(w for w in shell.inspector.body.select()
         if getattr(w, "name", "") == "↺ All as shared").clicks += 1
    assert in_panel_doc(shell, 1)["layers"][0]["over"] == {}
    words = " ".join(str(getattr(o, "object", "")) for o in shell.inspector.body.select())
    assert "differs" not in words


def test_an_override_is_marked_and_taken_back_one_by_one(shell):
    shell.select("layer:1:0")
    named(shell.inspector.body, "Max").value = 33.0
    named(shell.inspector.body, "Min").value = 3.0
    box = named(shell.inspector.body, "Max")
    assert "box-shadow" in box.styles
    chips = [w.name for w in shell.inspector.body.select()
             if str(getattr(w, "name", "")).startswith("↺")]
    assert set(chips) == {"↺ Max", "↺ Min", "↺ All"}
    next(w for w in shell.inspector.body.select() if getattr(w, "name", "") == "↺ Max").clicks += 1
    assert in_panel_doc(shell, 1)["layers"][0]["over"] == dict(vmin=3.0)
    assert named(shell.inspector.body, "Max").value == shell.doc["layers"]["l0"]["vmax"]


def test_a_layer_copied_added_moved_removed_from_all_plan_views(shell):
    shell.select("kind:plan")
    plan = shell.inspector.plan
    n = len(shell.doc["layers"])
    plan.add_shared("contour")
    assert len(shell.doc["layers"]) == n + 1
    new = list(shell.doc["layers"])[-1]
    assert all(p["layers"][-1]["ref"] == new for p in shell.doc["panels"])
    assert shell.inspector.folds[f"s:{new}"] is True  # (open)
    assert shell.node == "kind:plan"
    shell.undo()
    assert new not in shell.doc["layers"]
    assert "Could not draw" not in shell.status.object


def test_in_panels_buttons(shell):
    from panel.widgets import CheckButtonGroup
    shell.select("kind:plan")
    pick = next(w for w in shell.inspector.body.select() if isinstance(w, CheckButtonGroup))
    assert pick.value == [p["id"] for p in sorted(shell.doc["panels"], key=lambda p: p["id"])]
    pick.value = [i for i in pick.value if i != 3]
    assert in_panel_doc(shell, 3)["layers"][0]["over"]["on"] is False
    assert "Could not draw" not in shell.status.object


def test_a_panels_run_time_and_height(shell):
    shell.select("panel:1")
    body = shell.inspector.body
    time = named(body, "Time")
    other = next(t for t in time.options.values() if t != time.value)
    time.value = other
    assert in_panel_doc(shell, 1)["time_s"] == other
    named(shell.inspector.body, "Own height (blank: its layers')").value = "4"
    pan = in_panel_doc(shell, 1)
    assert pan["z"] == 4.0
    assert figdraw.panel_layers(shell.doc, pan)[0][1]["z"] == 4.0
    named(shell.inspector.body, "Own height (blank: its layers')").value = ""
    assert "z" not in in_panel_doc(shell, 1)
    assert "Could not draw" not in shell.status.object


def test_a_layer_of_this_panel_alone(shell):
    shell.select("panel:2")
    n = len(in_panel_doc(shell, 2)["layers"])
    shell.inspector.plan.add_own(2, "shade")
    pan = in_panel_doc(shell, 2)
    assert len(pan["layers"]) == n + 1 and "ref" not in pan["layers"][-1]
    assert len(in_panel_doc(shell, 1)["layers"]) == n
    assert "Could not draw" not in shell.status.object


def test_a_layers_own_time_in_a_panel(shell):
    shell.select("layer:1:0")
    time = named(shell.inspector.body, "Time")
    assert time.value == ""
    pick = next(v for v in time.options.values() if v != "")
    time.value = pick
    assert in_panel_doc(shell, 1)["layers"][0]["over"]["time_s"] == pick
    time.value = ""
    assert "time_s" not in in_panel_doc(shell, 1)["layers"][0]["over"]


def test_what_is_open_stays_open_across_undo_and_redo(shell):
    shell.select("kind:plan")
    ins = shell.inspector
    first, second = list(shell.doc["layers"])[:2]
    assert ins.folds.get(f"s:{first}") is None
    named(ins.body, "Max").value = 44.0
    row_open = [w for w in ins.body.select() if getattr(w, "name", "") == "Min"]
    assert row_open  # (the first starts open)
    ins.folds[f"s:{first}"] = False
    ins.folds[f"s:{second}"] = True
    ins.show("kind:plan")
    named(ins.body, "Levels (e.g. 10, 20 or -6:6:2)").value = "1, 2"
    shell.undo()
    assert [w for w in ins.body.select()
            if getattr(w, "name", "") == "Levels (e.g. 10, 20 or -6:6:2)"]
    assert not [w for w in ins.body.select() if getattr(w, "name", "") == "Min"]
    shell.redo()
    assert named(ins.body, "Levels (e.g. 10, 20 or -6:6:2)").value == "1, 2"


def test_a_cards_section_left_open_stays_open(shell):
    shell.select("layer:1:0")
    ins = shell.inspector
    sec = next(w for w in ins.body.select() if getattr(w, "title", "") == "Difference")
    sec.collapsed = False
    named(ins.body, "Max").value = 33.0
    shell.undo()
    assert not next(w for w in ins.body.select()
                    if getattr(w, "title", "") == "Difference").collapsed


def test_fill_panels_tool(shell):
    ins = shell.inspector
    ins.folds["fill"] = True
    ins.show("figure")
    f = ins.plan.widgets
    assert (f["rows"].value, f["cols"].value, f["col_dim"].value) == (2, 3, "times")
    f["rows"].value, f["cols"].value = 1, 3
    f["every"].value = 2
    f["go"].clicks += 1
    assert len(shell.doc["panels"]) == 3 and shell.doc["grid"]["rows"] == 1
    times = [p["time_s"] for p in shell.doc["panels"]]
    assert times == sorted(times)
    assert "3 panels" in shell.status.object and "Could not draw" not in shell.status.object
    assert shell.doc["size"][1] < 6.0  # (the height followed)
    assert ins.size_ws[1].value == shell.doc["size"][1]
    words = " ".join(str(getattr(o, "object", "")) for o in ins.body.select())
    assert "3 panels filled" in words and "Undo brings them back" in words
    shell.undo()
    assert len(shell.doc["panels"]) == 6 and shell.doc["grid"]["rows"] == 2


def test_fill_panels_by_heights_draws_as_the_old_grid_did(shell):
    """The tool's panels against a figure made with its panels at heights, in the New dialog."""
    ed = shell.ed
    base = de.plain(shell.doc)
    form = new_spec(ed, "plan", 1, 3, "heights")
    doc = de.plain(base)
    de.fill_panels(doc, 1, 3, "none", "heights", dict(heights=[1.0, 3.0, 6.0]), run="r0",
                   time_s=form["time_s"])
    doc["size"] = form["size"]
    a = ed.data.panel_data(form)
    b = ed.data.panel_data(doc)
    assert sorted(a) == sorted(b)
    for i in a:
        for k in a[i]:
            if isinstance(a[i][k], np.ndarray):
                assert np.array_equal(a[i][k], b[i][k], equal_nan=True), (i, k)


def test_new_opens_over_the_shell_and_what_it_makes_comes_here(shell):
    ed = shell.ed
    shell.new_figure()
    assert (ed.qs_rows.value, ed.qs_cols.value) == (2, 3)
    ed.qs_rows.value, ed.qs_cols.value = 1, 2
    ed._quick_make()
    assert shell.showing and len(shell.doc["panels"]) == 2 and shell.node == "figure"
    assert "2 panels" in shell.status.object
    shell.undo()
    assert len(shell.doc["panels"]) == 6


def test_a_saved_figure_from_the_gallery_comes_here(shell, tmp_path):
    ed = shell.ed
    form = dict(new_spec(ed), suptitle="From the gallery")
    path = tmp_path / "saved_spec.json"
    path.write_text(json.dumps(form, default=float))
    ed._quick_open(str(path))
    assert shell.showing and shell.doc["suptitle"] == "From the gallery"
    shell.undo()
    assert not shell.doc.get("suptitle")


def test_the_quick_start_sits_outside_the_new_layout(shell):
    quick = shell.ed.quick
    assert not any(o is quick for o in shell.panel.select())
    assert any(o is quick for o in shell.v.fig_ws.objects)


def test_look_sections_open_when_asked_and_write_at_their_scope(shell):
    ins = shell.inspector
    ins.folds["look:None:None:Text"] = True
    ins.show("figure")
    box = named(ins.body, shell.ed.fsize.name)
    assert box is not shell.ed.fsize
    box.value = 14.0
    assert shell.doc["style"]["font"]["size"] == 14.0
    assert shell.ed.fsize.value != 14.0  # (the old editor's stays as it is)
    assert "Could not draw" not in shell.status.object
    ins.folds["look:None:plan:Axes and ticks"] = True
    ins.show("kind:plan")
    named(ins.body, shell.ed.xlabel.name).value = "east (km)"
    assert shell.doc["kinds"]["plan"]["axes"]["xlabel"] == "east (km)"
    ins.folds["look:2:plan:Axes and ticks"] = True
    shell.select("panel:2")
    named(ins.body, shell.ed.xlabel.name).value = "own"
    assert in_panel_doc(shell, 2)["opts"]["axes"]["xlabel"] == "own"
    shell.select("kind:plan")
    words = " ".join(str(getattr(o, "object", "")) for o in ins.body.select())
    assert "Set in a panel alone" in words
    shell.select("panel:2")
    chip = next(w for w in ins.body.select()
                if str(getattr(w, "name", "")).startswith("↺ x label"))
    chip.clicks += 1
    assert "opts" not in in_panel_doc(shell, 2)


def test_area_of_all_plan_views(shell):
    ins = shell.inspector
    ins.folds["look:None:plan:Area"] = True
    ins.show("kind:plan")
    named(ins.body, "x min (km)")
    named(ins.body, shell.ed.dom.name).value = "full"
    assert shell.doc["kinds"]["plan"]["domain"]["mode"] == "full"
    assert "Could not draw" not in shell.status.object


def test_time_zero_from_the_runs_node_keeps_panels_lined_up(shell, demo_run):
    other = os.path.join(os.path.dirname(demo_run), "supercell_weak")
    shell.select("runs")
    shell.add_run(other)
    rid = shell.doc["runs"][1]["id"]
    in_panel_doc(shell, 1)["run"] = rid
    before = in_panel_doc(shell, 1)["time_s"]
    shell.inspector.show("runs")
    boxes = [w for w in shell.inspector.body.select()
             if getattr(w, "name", "") == "Time zero (min)"]
    boxes[1].value = 5.0
    assert in_panel_doc(shell, 1)["time_s"] == before + 300.0
    assert in_panel_doc(shell, 0)["time_s"] != before + 300.0
    shell.undo()
    assert in_panel_doc(shell, 1)["time_s"] == before


def test_runs_lined_up_by_output_number(shell, demo_run):
    other = os.path.join(os.path.dirname(demo_run), "supercell_weak")
    shell.add_run(other, node="runs")
    match = named(shell.inspector.body, shell.ed.time_match.name)
    match.value = "output"
    assert shell.doc["style"]["time_match"] == "output"
    assert all(r.get("outputs_s") for r in shell.doc["runs"])
    boxes = [w for w in shell.inspector.body.select()
             if getattr(w, "name", "") == "Time zero (min)"]
    assert [b.disabled for b in boxes] == [False, True]
    named(shell.inspector.body, shell.ed.time_match.name).value = "time"
    assert "time_match" not in shell.doc["style"]
    assert not any(r.get("outputs_s") for r in shell.doc["runs"])


def test_the_field_lists_follow_the_documents_runs(shell, demo_run):
    other = os.path.join(os.path.dirname(demo_run), "supercell_weak")
    was = shell.fields
    shell.add_run(other, node="runs")
    assert shell.fields is not was
    shell.undo()
    assert len(shell.doc["runs"]) == 1


def test_copy_a_shared_layers_look(shell):
    doc = shell.doc
    ids = list(doc["layers"])
    a, b = ids[0], ids[1]
    was = doc["layers"][b]
    assert doc["layers"][a]["type"] != was["type"]
    plan = shell.inspector.panes["plan"]
    plan.copy_look(a, [b])  # (another type: nothing)
    assert doc["layers"][b] == was
    lid = de.add_shared(doc, "plan", dict(doc["layers"][a], cmap="viridis"))
    plan.copy_look(a, [lid])
    assert shell.doc["layers"][lid]["cmap"] == shell.doc["layers"][a]["cmap"]
    shell.undo()
    assert shell.doc["layers"][lid]["cmap"] == "viridis"

