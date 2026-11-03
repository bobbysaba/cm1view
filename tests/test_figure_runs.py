"""Figure workspace with several runs: grids of runs, run lists and pickers, panel times
from the panels' run, run colours, and templates applied to another run."""
import json

import numpy as np
import panel as pn

from conftest import txt, wait, render


def test_a_grid_of_runs_and_times(ed, demo_root):
    import os
    from cm1view.figures import spec as fg
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    assert len(ed.run_rows) == 2 and ed.g_cols.value == "times"  # (adding a run keeps the panels)
    ed.gg_runs.value = [0, 1]
    ed.g_rows.value = "runs"  # a row per run, a column per time
    ed.cols.value, ed.tstep.value = 3, 1
    ed._fill_times()
    assert ed.rows.value == 2 and ed.rows.disabled and not ed.cols.disabled
    assert len(ed.tm_rows) == 3 and ed.tm_rows[0].value < ed.tm_rows[1].value
    assert ed.tm_rows[0].name == "Column 1" and ed.gg_runs.visible and not ed.run_sel.visible
    s = ed.collect()
    assert s["grid"] == dict(rows="runs", cols="times", runs=[0, 1])
    assert [fg.panel_ref(s, i)[0] for i in range(6)] == [0, 0, 0, 1, 1, 1]
    spec, data, fig = render(ed)
    assert {d.get("run_label") for d in data.values()} == {"supercell", "supercell_weak"}
    ed.g_cols.value = "runs"  # runs as columns (the rows step through nothing now) …
    assert ed.g_rows.value == "none" and (ed.rows.value, ed.cols.value) == (1, 2)
    ed.g_rows.value = "times"  # … and a row per time
    ed.rows.value = 3
    s = ed.collect()
    assert (s["rows"], s["cols"]) == (3, 2)
    assert [fg.panel_ref(s, i)[0] for i in range(6)] == [0, 1, 0, 1, 0, 1]
    ed.gg_runs.value = [1, 0]  # in the order picked
    assert [fg.panel_ref(ed.collect(), i)[0] for i in range(2)] == [1, 0]


def test_an_older_run_by_time_grid_opens_as_a_grid_of_runs(ed, demo_root):
    import os
    from cm1view.figures import spec as fg
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    s = ed.collect()
    s.pop("grid")
    t0, t1 = float(ed.run.times[0]), float(ed.run.times[1])
    s.update(vary="grid", runs_as="rows", rows=2, cols=2, times_s=[t0, t1], panels=[])
    old = render_spec(ed, s)
    ed.set_spec(json.loads(json.dumps(s)))
    got = ed.collect()
    assert got["grid"]["rows"] == "runs" and got["grid"]["cols"] == "times"
    assert [fg.panel_ref(got, i) for i in range(4)] == [(0, t0), (0, t1), (1, t0), (1, t1)]
    assert old == render_spec(ed, got)


def test_an_older_figure_of_own_runs_and_times_opens_as_panel_edits(ed, demo_root):
    import os
    from cm1view.figures import spec as fg
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    s = ed.collect()
    s.pop("grid")
    t0, t1 = float(ed.run.times[0]), float(ed.run.times[1])
    s.update(vary="custom", rows=1, cols=2, panels=[dict(run=1, time_s=t1),
                                                    dict(run=0, time_s=t0)])
    old = render_spec(ed, s)
    ed.set_spec(json.loads(json.dumps(s)))
    got = ed.collect()
    assert (got["grid"]["rows"], got["grid"]["cols"]) == ("none", "none")
    assert [fg.panel_ref(got, i) for i in range(2)] == [(1, t1), (0, t0)]
    assert got["edits"]["0"]["run"] == 1 and got["edits"]["1"]["time_s"] == t0
    assert old == render_spec(ed, got)


def render_spec(ed, spec):
    """The preview's arrays of `spec` as the sets of (panel, run, time)."""
    from cm1view.figures import spec as fg
    return [fg.panel_ref(spec, i) for i in range(fg.npanels(spec))]


def test_a_run_nothing_uses_any_more_is_dropped(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed._prune_runs()  # (notes that the viewer's run is used)
    ed.run_sel.value = weak  # picking a run adds it, and the panels use it
    assert len(ed.run_rows) == 2 and ed.run_sel.value == 1
    ed._prune_runs()  # the viewer's run was used and is not now
    assert [r["path"] for r in ed.run_rows] == [weak] and ed.run_sel.value == 0
    assert "Dropped" in txt(ed.runs_msg.object)
    spec, data, fig = render(ed)
    assert spec["runs"][0]["path"] == weak and not any(d.get("missing") for d in data.values())


def test_a_run_added_by_hand_stays_until_it_has_been_used(ed, demo_root):
    import os
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed._prune_runs()
    ed._prune_runs()
    assert len(ed.run_rows) == 2
    assert "not used yet" in ed.run_rows[1]["info"].object


def test_removing_a_run_moves_the_layers_that_pick_runs(ed, demo_root, coarse_run):
    import os
    for p in (os.path.join(demo_root, "demo", "supercell_weak"), coarse_run):
        ed.add_path.value = p
        ed._add_run()
    c = ed.cards[0]
    c.w["run"].value = 2
    ed._remove_run(ed.run_rows[1])
    assert c.w["run"].value == 1 and [r["path"] for r in ed.run_rows][-1] == coarse_run
    ed._remove_run(ed.run_rows[1])  # the run the layer picked: back to the panel's
    assert c.w["run"].value == -1


def test_removing_a_run_keeps_soundings_and_series_on_their_runs(ed, demo_root, coarse_run):
    import os
    from cm1view.figures import spec as fg
    for p in (os.path.join(demo_root, "demo", "supercell_weak"), coarse_run):
        ed.add_path.value = p
        ed._add_run()
    assert len(ed.run_rows) == 3
    ed.snd_cards = [ed._snd_card(dict(fg.sounding_defaults(k, 3600.0, n=k), label=f"r{k}"))
                    for k in range(3)]
    ed.ser_cards = [ed._ser_card(dict(fg.series_defaults(ed.F, ed._new_recipe()), runs=r))
                    for r in ([0], [1, 2], None)]
    ed._remove_run(ed.run_rows[0])  # runs B and C become 1 and 2 (indices 0, 1)
    assert [(c.w["label"].value, c.w["run"].value) for c in ed.snd_cards] == [("r1", 0),
                                                                             ("r2", 1)]
    assert [c.collect()["runs"] for c in ed.ser_cards] == [[0, 1], None]
    assert "1 sounding" in txt(ed.runs_msg.object)


def test_panel_times_come_from_the_panels_run(ed, coarse_run):
    ed.add_path.value = coarse_run
    ed._add_run()
    ed.g_rows.value, ed.g_cols.value = "none", "times"
    ed.run_sel.value = 1
    crun = ed.open_run(coarse_run)[0]
    s = ed.collect()
    assert all(t in list(crun.times) for t in s["times_s"] if t is not None)
    ts = [t for t in s["times_s"] if t is not None]  # still different times (as far as
    assert len(set(ts)) == min(len(ts), len(crun.times))  # the run has outputs)
    spec, data, fig = render(ed)
    assert not any(d.get("missing") for d in data.values())
    ed.g_rows.value, ed.g_cols.value = "none", "fields"
    assert ed.time1.value in list(crun.times)
    ed.gg_runs.value = [1, 0]  # a grid of runs: the first one's outputs, marked where
    ed.g_rows.value, ed.g_cols.value = "runs", "times"  # the other has none
    from cm1view.figures.cards import NONE  # (pickers past its last output: empty)
    assert all(w.value in list(crun.times) for w in ed.tm_rows if w.value != NONE)
    assert any(w.value != NONE for w in ed.tm_rows)
    base = [float(t) for t in ed.run.times]
    ed.gg_runs.value = [0, 1]
    assert len(base) > len(crun.times) and any(
        "not in every run" in k for k in ed.tm_rows[0].options)


def test_reopened_spec_keeps_times_of_another_run(ed, coarse_run):
    ed.add_path.value = coarse_run
    ed._add_run()
    ed.g_rows.value, ed.g_cols.value = "none", "times"
    ed.run_sel.value = 1
    s = ed.collect()
    ed.set_spec(json.loads(json.dumps(s)))
    assert ed.collect()["times_s"] == s["times_s"]
    s["times_s"][0] = 3671.0  # no run has it: kept, and the panel says why
    ed.set_spec(json.loads(json.dumps(s)))
    assert ed.collect()["times_s"][0] == 3671.0
    spec, data, fig = render(ed)
    assert "no output" in data[0]["missing"]


def test_run_lists_offer_runs_to_add(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")  # next to the viewer's run
    assert weak in ed.run_sel.groups["Other runs (adds it)"].values()
    assert ed.run_sel.visible  # (one run in the figure, but others to pick)
    ed.run_sel.value = weak  # picking it adds it, with its track, and shows it
    assert len(ed.run_rows) == 2 and ed.run_sel.value == 1 and ed.g_cols.value == "times"
    assert ed.collect()["runs"][1]["track"].endswith("demo_supercell_weak.csv")
    assert weak not in ed._other_runs().values()
    spec, data, fig = render(ed)
    assert not any(d.get("missing") for d in data.values())


def test_track_file_list_and_typed_path(ed, demo_root, tmp_path):
    import os
    from cm1view.figures.runs import TYPE_PATH
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.run_sel.value = weak
    r = ed.run_rows[1]
    pick, box = r["track_pick"], r["track"]
    own = os.path.join(demo_root, "storm_tracks", "demo_supercell_weak.csv")
    other = os.path.join(demo_root, "storm_tracks", "demo_supercell.csv")
    assert pick.value == own and list(pick.options.values())[1] == own and not box.visible
    pick.value = other  # picked: it is the run's track
    assert box.value == other and ed.collect()["runs"][1]["track"] == other
    pick.value = ""
    assert box.value == "" and ed.collect()["runs"][1]["track"] == ""
    pick.value = other
    pick.value = TYPE_PATH  # (the path stays, to edit)
    assert box.visible and box.value == other
    typed = str(tmp_path / "mine.csv")
    box.value = typed
    assert pick.value == TYPE_PATH and ed.collect()["runs"][1]["track"] == typed
    ed._show_runs()  # (looked for again: a typed path isn't lost)
    assert pick.value == TYPE_PATH and box.value == typed and box.visible


def test_track_box_alone_when_no_files_are_found(ed, monkeypatch):
    from cm1view import config
    r = ed.run_rows[0]
    monkeypatch.setattr(config, "track_files", lambda path: [])
    ed._show_track_pick(r, look=True)
    assert not r["track_pick"].visible and r["track"].visible


def test_run_picker_adds_a_run(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.add_pick.query.value_input = weak  # a pasted folder: picked, then added
    assert ed.add_pick.selected == weak
    ed.add_pick._open()
    assert [r["path"] for r in ed.run_rows][-1] == weak
    assert ed.add_pick.query.value == "" and weak not in ed.add_pick.list.options.values()


def test_field_lists_cover_every_run():
    from cm1view.core.fields import FieldDef
    from cm1view.figures.runs import AllFields

    class F:
        def __init__(self, *names):
            self.defs = {n: FieldDef(n, n.upper(), "", "Winds") for n in names}

        def __contains__(self, n):
            return n in self.defs

    a = AllFields([F("u", "w"), F("u", "zvort")])
    assert list(a.defs) == ["u", "w", "zvort"]
    labels = [k for g in a.groups().values() for k in g]
    assert "U [u]" in labels and "W [w] · not in every run" in labels


def test_run_colours_and_line_styles(ed, demo_root):
    import os
    from matplotlib.colors import to_hex
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.from_series()
    ed.kind.value = "line"  # one series from two runs: coloured by run
    ed.run_rows[1]["color"].value = "#00aa00"
    ed.panel_data(ed.collect())
    wait(lambda: not ed.series_pending(), 120, "the series")
    spec, data, fig = render(ed)
    assert spec["runs"][1]["color"] == "#00aa00"
    assert "#00aa00" in {to_hex(ln.get_color()) for ln in fig.axes[0].get_lines()}


def test_series_run_list_offers_other_runs(ed, demo_root):
    import os
    from cm1view.figures.cards.seriescard import SOME_RUNS
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.from_series()
    ed.kind.value = "line"
    c = ed.ser_cards[0]
    assert weak in c._run_values() and weak in c.w["runs"].options.values()
    c.w["run"].value = weak  # picking it adds it to the figure, and picks it
    assert [r["path"] for r in ed.run_rows][-1] == weak
    assert c.w["run"].value == 1 and ed.collect()["series"][0]["runs"] == [1]
    assert weak not in c._run_values()
    c.w["run"].value = SOME_RUNS  # (starts from every run)
    assert c.w["runs"].visible and c.w["runs"].value == [0, 1]
    c.w["runs"].value = [1]
    assert ed.collect()["series"][0]["runs"] == [1]


def test_series_card_settings_follow_the_panel_kind(ed):
    ed.kind.value = "line"
    ed._add_series()
    c = ed.ser_cards[-1]
    c.w["vmode"].value = "height"
    assert c.line_row.visible and not c.th_row.visible and c.w["vmode"].visible
    assert c.recipe()["vmode"] == "height" and not ed.cb_sec.visible
    ed.kind.value = "th"  # (a time-height card is always a layer: no Vertical choice)
    c = ed.ser_cards[-1]
    assert c.th_row.visible and not c.line_row.visible and not c.w["vmode"].visible
    assert c.w["z0"].visible and not c.w["z"].visible
    assert c.recipe()["vmode"] == "layer" and ed.cb_sec.visible


def test_style_shows_what_the_kind_draws(ed):
    def shown(*names):
        return [getattr(ed, n).visible for n in names]
    # kind: colorbar, contour key, time label, run name, axis labels, y tick step
    want = dict(plan=(1, 1, 1, 1, 1, 1), xsec=(1, 1, 1, 1, 1, 1), th=(1, 0, 0, 1, 1, 1),
                line=(0, 0, 0, 0, 1, 1), sounding=(0, 0, 1, 0, 1, 0), dist=(0, 0, 1, 0, 1, 1),
                profile=(0, 0, 1, 0, 1, 1), joint=(0, 0, 1, 0, 1, 1), azim=(0, 0, 1, 0, 1, 1),
                scene=(0, 0, 1, 1, 0, 0))
    for kind, row in want.items():
        ed.kind.value = kind
        assert shown("cb_sec", "ck_sec", "tl_on", "rl_on", "xlabel", "ystep") == \
            [bool(v) for v in row], kind
        assert ed.tickdir.visible and ed.title_bold.visible, kind
    assert not ed.grid.visible and not ed.axes_hint.visible  # (the last: a 3D scene)


def test_style_keeps_what_a_kind_hides_and_its_values(ed):
    ed.kind.value = "plan"
    ed.grid.value = True
    ed.rl_on.value = True
    assert ed.grid_ls.visible
    ed.kind.value = "scene"  # (no grid to style)
    assert not ed.grid_ls.visible
    ed.kind.value = "dist"  # (no run name: its settings go with the switch)
    assert ed.grid_ls.visible and not ed.rl_on.visible and ed.rl_on.value
    assert ed.collect()["run_label"]["on"] is True


def test_contour_key_stays_shown_while_on(ed):
    ed.kind.value = "plan"
    ed.ck_on.value = True
    ed.kind.value = "line"  # (it still draws, from the plan layers: it must be turned off)
    assert ed.ck_sec.visible
    ed.ck_on.value = False
    assert not ed.ck_sec.visible
    ed.kind.value = "plan"
    assert ed.ck_sec.visible


def test_series_card_picks_its_run_like_a_sounding(ed, demo_root):
    import os
    from cm1view.figures.cards.seriescard import ALL_RUNS, SOME_RUNS
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.from_series()
    ed.kind.value = "line"  # (the time-height cards of one series: one card again)
    assert len(ed.ser_cards) == 1
    c = ed.ser_cards[0]
    assert c.w["run"].value == ALL_RUNS and not c.w["runs"].visible and c.w["ens"].visible
    assert ed.collect()["series"][0]["runs"] is None
    c.w["run"].value = 1
    assert ed.collect()["series"][0]["runs"] == [1] and not c.w["ens"].visible
    c.w["run"].value = SOME_RUNS
    assert c.w["runs"].visible and ed.collect()["series"][0]["runs"] == [0, 1]
    ed.kind.value = "th"  # a time-height card has one run: no All / Several
    assert ALL_RUNS not in ed.ser_cards[0]._run_values()


def test_series_cards_say_what_the_runs_tracks_give(ed, demo_root):
    """A card around the tracked storm says what each of its runs' tracks gives, and where
    to set them; it has no boxes of its own for them."""
    import os
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.from_series()
    ed.kind.value = "line"
    assert ed.runs_sec.visible  # (a run's name, colour, time zero and track)
    c = ed.ser_cards[0]
    c.w["region"].value = "domain"
    assert not c.trk_note.visible
    c.w["region"].value = "track"
    assert c.trk_note.visible and "Runs used" in c.trk_note.object
    c.w["run"].value = 1
    assert "supercell_weak" in c.trk_note.object
    assert not any(isinstance(x, pn.widgets.TextInput) and "track" in x.name.lower()
                   for x in c.w.values())
    ed.run_rows[1]["track"].value = ""  # (the run's row: the card's note follows)
    assert "no track" in c.trk_note.object
    ed.kind.value = "plan"
    assert ed.runs_sec.visible


def test_retired_time_zeros_show_only_when_set(ed):
    """The figure's and a run-based series card's time zero: only in figures that use them,
    which keep them; the run's and your own data's are always there."""
    assert not ed.tl_t0.visible
    ed.from_series()
    ed.kind.value = "line"
    c = ed.ser_cards[0]
    assert not c.w["t0"].visible and ed.run_rows[0]["t0"].visible
    s = ed.collect()
    s["time_label"]["t0_min"] = 10.0
    s["series"][0]["t0_min"] = 5.0
    ed.set_spec(s)
    c = ed.ser_cards[0]
    assert ed.tl_t0.visible and c.w["t0"].visible
    back = ed.collect()
    assert back["time_label"]["t0_min"] == 10.0 and back["series"][0]["t0_min"] == 5.0
    ed.tl_t0.value = 0.0  # (taken back to 0: gone, as in a new figure)
    c.w["t0"].value = 0.0
    assert not ed.tl_t0.visible and not c.w["t0"].visible
    ed._add_data()
    assert ed.ser_cards[-1].w["t0"].visible


def test_each_setting_has_one_home(ed):
    """A series figure's axes are in Layers → Plot, a section figure's top and x axis over
    its cards; a plan view's section line keeps them in Panels → Area."""
    def holds(col, *ws):  # (a section's contents arrive when it is opened)
        for o in col.objects:
            if isinstance(o, pn.Card):
                o.collapsed = False
        found = [x for o in col.objects for x in o.select(pn.widgets.Widget)]
        return all(any(x is w for x in found) for w in ws)
    for kind, own in (("line", ed.ts_mark), ("th", ed.ts_zmin)):  # (each kind's own axis or mark)
        ed.kind.value = kind
        assert holds(ed.series_col, ed.ts_tmin, ed.ts_tmax, own)
        assert any(o is ed.series_col for o in ed.layers_tab.objects)
    assert not any(c.title.endswith("axes") for c in ed.panels_tab.objects
                   if isinstance(c, pn.Card))
    ed.kind.value = "xsec"
    assert not ed.area_sec.visible and not any(o is ed.area_sec for o in ed.panels_tab.objects)
    assert list(ed.xs_axes_layers.objects) == [ed.xs_axes] and not ed.xs_axes_area.objects
    order = [id(o) for o in ed.xsec_col.objects]
    assert order.index(id(ed.xs_axes_layers)) < order.index(id(ed.xsec_box))
    ed.kind.value = "plan"
    assert list(ed.xs_axes_area.objects) == [ed.xs_axes] and not ed.xs_axes_layers.objects
    ed._add_layer("line")
    assert ed.area_sec.visible and ed.area_xs.visible and ed.area_sec.title.endswith("line")
    assert [n for n, _ in ed.tab_list] == ["Panels", "Layers", "Tree", "Style", "Annotate",
                                           "File"]


def test_one_per_run_splits_a_time_series_card(ed, demo_root):
    import os
    from cm1view.figures import draw as figdraw
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.from_series()
    ed.kind.value = "line"
    ed._per_run_series(ed.ser_cards[0])  # every run: a card per run, in the run's colour
    s = ed.collect()
    assert [(e["runs"], e["panel"]) for e in s["series"]] == [([0], 0), ([1], 0)]
    assert [e["color"] for e in s["series"]] == [figdraw.run_color(s, 0),
                                                figdraw.run_color(s, 1)]
    ed._per_run_series(ed.ser_cards[1])  # (run 1 has it in this panel already)
    assert len(ed.ser_cards) == 2 and "already" in txt(ed.msg.object)
    ed._dup_series(ed.ser_cards[0])  # a copy in a new panel
    assert [e["panel"] for e in ed.collect()["series"]] == [0, 1, 0]
    assert ed.rows.value * ed.cols.value >= 2


def test_run_lists_without_other_runs_have_no_heading(ed):
    ed._find_runs = lambda: setattr(ed, "_cands", [])  # nothing else to offer
    ed._find_runs()
    ed._refresh_run_names()
    assert not ed.run_sel.groups and list(ed.run_sel.options.values()) == [0]
    ed.from_soundings()
    w = ed.snd_cards[0].w["run"]
    assert not w.groups and w.value == 0


def test_runs_root_scan_feeds_the_run_lists(ed, coarse_run, monkeypatch):
    import os
    from cm1view import config, registry
    root, real = os.path.dirname(coarse_run), config.get
    monkeypatch.setattr(config, "get", lambda k: [root] if k == "runs_root" else real(k))
    # only the scan can find it (earlier tests made it a recent run)
    monkeypatch.setattr(registry, "recent_runs", lambda *a, **k: [])
    monkeypatch.setattr(registry, "sibling_runs", lambda *a, **k: [])
    ed._scanned = []
    ed._find_runs()
    assert coarse_run not in ed._other_runs().values()
    ed._scan_roots()  # in the background; no page: the next change of the runs shows it
    wait(lambda: ed._scan_new, 60, "the runs_root scan")
    ed._show_runs()
    assert coarse_run in ed._other_runs().values()
    assert coarse_run in ed.run_sel.groups["Other runs (adds it)"].values()
    assert coarse_run in ed.add_pick._known


def test_run_colours_are_the_default(ed, demo_root):
    import os
    from matplotlib.colors import to_hex
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.gg_runs.value = [0, 1]  # a column of the two runs (each panel names its run)
    ed.g_rows.value, ed.g_cols.value = "runs", "none"
    ed.run_rows[1]["color"].value = "#00aa00"
    ed._add_layer("track")  # a new track layer: each panel's run's colour
    spec, data, fig = render(ed)
    i = next(i for i, d in data.items() if d.get("run") == 1 and "track_x" in d)
    ax = fig._cv_axes[i]
    assert "#00aa00" in {to_hex(ln.get_color()) for ln in ax.get_lines()}
    names = {a.txt._text.get_text(): to_hex(a.txt._text.get_color())
             for a in ax.artists if hasattr(a, "txt")}
    assert names[spec["runs"][1]["label"]] == "#00aa00"  # the run's name too
    ed.from_soundings()  # soundings of two runs in one panel: the runs' colours
    ed._add_sounding()
    for c, k in zip(ed.snd_cards[:2], (0, 1)):
        c.w["run"].value, c.w["panel"].value, c.w["kind"].value = k, 1, "mean"
    spec, data, fig = render(ed)
    assert data[0]["nsnd"] == 2
    cols = {to_hex(ln.get_color()) for ln in fig._cv_axes[0].get_lines()}
    assert {"#00aa00", to_hex(spec["runs"][0]["color"])} <= cols
    ed.snd_cards[1].w["auto_color"].value = False  # a colour of its own
    ed.snd_cards[1].w["color"].value = "#123456"
    spec, data, fig = render(ed)
    assert "#123456" in {to_hex(ln.get_color()) for ln in fig._cv_axes[0].get_lines()}


def test_templates_apply_to_another_run(ed, coarse_run):
    import os
    from cm1view.figures import spec as fg
    spec = ed.collect()
    ed.tpl_name.value = "two by three"
    ed._save_template()
    path = ed.tpl_sel.value
    ed.tpl_sel.value = None  # as a page starts: the list picks one, as the browser shows
    ed._list_templates()
    assert ed.tpl_sel.value in ed.tpl_sel.options.values()
    ed.tpl_sel.value = path
    ed.open_quick()  # the quick start applies it too
    ed.qs_tpl.value = path
    assert not ed.qs_tpl_go.disabled
    ed.qs_tpl_go.clicks += 1
    assert not ed.quick.open and "two by three" in ed.msg.object
    ed.open_quick()
    with open(path) as f:
        kept = f.read()
    with open(path, "w") as f:
        f.write("[]")
    ed.qs_tpl_go.clicks += 1  # (it can't be: says why, in the dialog)
    assert ed.quick.open and ed.qs_load_note.visible and "Could not" in ed.qs_load_note.object
    ed.quick.hide()
    with open(path, "w") as f:
        f.write(kept)
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    assert os.path.dirname(path) == fg.templates_dir() and not ed.tpl_go.disabled
    tpl = fg.load_template(path)
    assert "runs" not in tpl and tpl["template"]["time_s"] == spec["time_s"]
    run, _ = ed.open_run(coarse_run)
    out = fg.from_template(tpl, run, 2)
    dt, half = run.times[2] - spec["time_s"], float(np.diff(run.times).max()) / 2 + 1
    assert out["time_s"] == run.times[2] and "runs" not in out
    assert len(out["times_s"]) == len(spec["times_s"])
    for a, b in zip(spec["times_s"], out["times_s"]):  # (as far apart, at outputs)
        assert b is None or (b in run.times and abs(b - (a + dt)) <= half)
    assert out["layers"] == spec["layers"]
    ed.tpl_sel.value = path
    ed._apply_template()  # (onto the run shown)
    assert "Applied" in txt(ed.msg.object), ed.msg.object
    got = ed.collect()
    assert got["layers"] == spec["layers"] and got["runs"][0]["path"] == ed.run.path
    render(ed)


def test_a_run_keeps_its_colour_in_every_panel():
    from matplotlib.colors import to_hex
    from matplotlib.figure import Figure
    from cm1view.figures.draw.lines import _lines, dist_colors
    from cm1view.figures.draw.sounding import sounding_colors
    runs = [dict(color="#00aa00"), dict(color="#aa0000")]
    one = dict(nsnd=1, N0_e=0)  # a panel with one sounding (distribution) of run 1
    assert sounding_colors(dict(runs=runs, soundings=[dict(run=1)]), one) == ["#aa0000"]
    assert dist_colors(dict(runs=runs, dists=[dict(run=1)]), dict(ndist=1, D0_e=0)) == \
        ["#aa0000"]
    alone = sounding_colors(dict(runs=runs[:1], soundings=[dict(run=0)]), one)
    assert alone != ["#00aa00"]  # one run in the figure: the sounding colours as before
    same = sounding_colors(dict(runs=runs, soundings=[dict(run=1), dict(run=1)]),
                           dict(nsnd=2, N0_e=0, N1_e=1))
    assert len(set(same)) == 2  # two of one run: told apart by colour, not the run's
    t = np.arange(3.0)
    ax = Figure().subplots()  # a series of every run, alone: run 1's line in its colour
    _lines(ax, dict(nlines=1, S0_e=0, S0_r=1, S0_t=t, S0_v=t, S0_label="w"),
           dict(runs=runs, series=[dict(color="#0000ff", ls=":")]), 10)
    assert to_hex(ax.lines[0].get_color()) == "#aa0000"
    assert ax.lines[0].get_linestyle() == ":"  # (the series' line style)
    ax = Figure().subplots()  # two series of every run: the series' colours, run 1's style
    _lines(ax, dict(nlines=2, S0_e=0, S0_r=1, S0_t=t, S0_v=t, S0_label="a",
                    S1_e=1, S1_r=1, S1_t=t, S1_v=t, S1_label="b"),
           dict(runs=runs, series=[dict(color="#0000ff"), dict(color="#ff00ff")]), 10)
    assert [to_hex(ln.get_color()) for ln in ax.lines] == ["#0000ff", "#ff00ff"]
    assert {ln.get_linestyle() for ln in ax.lines} == {"--"}


def test_a_series_of_one_run_draws_in_its_own_colour_and_style():
    """A card's colour and line style apply to its line in a figure of several runs,
    alone in a panel or not; an older figure opens looking as it was drawn."""
    from matplotlib.colors import to_hex
    from matplotlib.figure import Figure
    from cm1view.figures.draw.lines import _lines
    from cm1view.figures.spec.base import series_looks
    runs = [dict(color="#00aa00", ls="-"), dict(color="#aa0000", ls=":")]
    t = np.arange(3.0)
    ax = Figure().subplots()
    _lines(ax, dict(nlines=1, S0_e=0, S0_r=1, S0_t=t, S0_v=t, S0_label="w"),
           dict(runs=runs, series=[dict(color="#0000ff", ls="--", runs=[1])]), 10)
    assert to_hex(ax.lines[0].get_color()) == "#0000ff"
    assert ax.lines[0].get_linestyle() == "--"
    ax = Figure().subplots()
    _lines(ax, dict(nlines=2, S0_e=0, S0_r=0, S0_t=t, S0_v=t, S0_label="a",
                    S1_e=1, S1_r=1, S1_t=t, S1_v=t, S1_label="b"),
           dict(runs=runs, series=[dict(color="#0000ff", ls="-", runs=[0]),
                                   dict(color="#ff00ff", ls="-.", runs=[1])]), 10)
    assert [to_hex(ln.get_color()) for ln in ax.lines] == ["#0000ff", "#ff00ff"]
    assert [ln.get_linestyle() for ln in ax.lines] == ["-", "-."]
    # older figures (no "ls" on the series): the look they were drawn with
    old = dict(kind="line", runs=runs, series=[
        dict(color="k", runs=[1], panel=0),  # alone: run 1's colour
        dict(color="b", runs=[0], panel=1), dict(color="r", runs=[1], panel=1)])
    series_looks(old)
    a, b, c = old["series"]
    assert (a["color"], a["ls"]) == ("#aa0000", "-")
    assert (b["color"], b["ls"]) == ("b", "-") and (c["color"], c["ls"]) == ("r", ":")
    series_looks(old)  # (a newer figure stays)
    assert old["series"][0]["color"] == "#aa0000"


def test_time_height_panels_follow_each_series_runs():
    from cm1view.figures import draw as figdraw
    runs = [dict(path="/a"), dict(path="/b"), dict(path="/c")]
    s = dict(kind="th", runs=runs, runs_as="cols",
             series=[dict(runs=None), dict(runs=[2])])  # every run; run 2 alone
    assert figdraw.th_grid(s) == (2, 3, [(0, 0), (1, 0), (2, 0), None, None, (2, 1)])
    s["series"][0]["runs"] = [0]  # run 1: no series uses it, no column
    assert figdraw.th_grid(s) == (2, 2, [(0, 0), None, None, (2, 1)])
    s["runs_as"] = "rows"
    assert figdraw.th_grid(s) == (2, 2, [(0, 0), None, None, (2, 1)])
    s["series"][1]["runs"] = [0, 2]
    assert figdraw.th_grid(s)[2] == [(0, 0), (0, 1), None, (2, 1)]
    s.update(rows=2, cols=2)
    assert figdraw.series_ref(s, 1) == (0, 1) and figdraw.series_ref(s, 2) is None
    assert figdraw.series_ref(dict(s, runs_as="cols"), 9) is None


def test_time_height_cards_one_per_panel(ed, demo_root):
    import os
    from cm1view.figures import draw as figdraw
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.from_series()
    ed.kind.value = "th"
    s = ed.collect()
    assert s["runs_as"] == "cards" and [(e["runs"], e["panel"]) for e in s["series"]] == \
        [([0], 0)]
    c = ed.ser_cards[0]
    c.w["run"].value = weak  # (adds the run; the card is of it now)
    assert ed.collect()["series"][0]["runs"] == [1]
    c.w["run"].value = 0
    ed._per_run_series(c)  # a copy for the other run, down the column
    s = ed.collect()
    assert [(e["runs"], e["panel"]) for e in s["series"]] == [([0], 0), ([1], 1)]
    assert (ed.rows.value, ed.cols.value) == (2, 1)
    assert [figdraw.series_ref(s, i) for i in range(2)] == [(0, 0), (1, 1)]
    ed.rows.value = 3
    ed._add_series()  # a new card: the grid's free panel, of the last card's run
    s = ed.collect()
    assert (s["series"][-1]["runs"], s["series"][-1]["panel"]) == ([1], 2)
    assert ed.rows.value * ed.cols.value >= 3
    ed.kind.value = "line"  # the cards of one series: one card of both runs
    s = ed.collect()
    assert [(e["runs"], e["panel"]) for e in s["series"]] == [(None, 0), ([1], 1)]
    ed.kind.value = "th"  # and back: a card per run
    assert [e["runs"] for e in ed.collect()["series"]] == [[0], [1], [1]]


def test_ensemble_band_of_a_series_over_runs(ed, demo_root):
    import os
    from matplotlib.collections import PolyCollection
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.from_series()
    ed.kind.value = "line"
    c = ed.ser_cards[0]
    assert not c.w["ens_mid"].visible
    c.w["ens"].value = "minmax"
    assert c.w["ens_mid"].visible and c.collect()["ens"] == "minmax"
    ed.panel_data(ed.collect())
    wait(lambda: not ed.series_pending(), 120, "the series")
    spec, data, fig = render(ed)
    d = data[0]
    j = next(j for j in range(d["nlines"]) if f"S{j}_ens" in d)
    assert d[f"S{j}_ens"] == 2 and d[f"S{j}_r"] == -1
    assert d[f"S{j}_label"] == c.collect()["label"]  # (the card's label, as it is)
    ok = np.isfinite(d[f"S{j}_v"])
    assert ok.any() and np.all(d[f"S{j}_lo"][ok] <= d[f"S{j}_v"][ok] + 1e-6)
    assert np.all(d[f"S{j}_v"][ok] <= d[f"S{j}_hi"][ok] + 1e-6)
    assert sum(f"S{n}_mem" in d for n in range(d["nlines"])) == 2
    assert any(isinstance(x, PolyCollection) for x in fig.axes[0].collections)
    c.w["ens_members"].value = "hidden"  # (the band and its centre alone)
    spec, data, fig = render(ed)
    assert data[0]["nlines"] == 1 and "S0_ens" in data[0]


def test_ensemble_fill_layer_over_runs(ed, demo_root):
    import os
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    c = next(c for c in ed.cards if c.type == "fill")
    c.w["ens_on"].value = True
    c.w["ens_grid"].value = "interp"
    lay = c.collect()
    assert lay["ens"] == dict(runs=None, stat="mean", threshold=0.0, above=True, grid="interp")
    assert "minus" not in lay and not c.w["minus_on"].visible and not c.w["run"].visible
    assert ed._runs_used() == {0, 1}
    spec, data, fig = render(ed)
    j = next(j for j, x in enumerate(spec["layers"]) if x.get("ens"))
    assert all(d[f"L{j}_ens"] == 2 for d in data.values() if not d.get("missing"))
    assert any("ensemble mean" in a.get_ylabel() + a.get_xlabel() for a in fig.axes)
    c.w["ens_stat"].value = "prob"  # (a probability: 0-100 %)
    c.w["ens_thr"].value = 1.0
    lay = c.collect()
    assert (lay["cmap"], lay["vmin"], lay["vmax"]) == ("Blues", 0.0, 100.0)
    spec, data, fig = render(ed)
    v = np.concatenate([d[f"L{j}"][np.isfinite(d[f"L{j}"])].ravel() for d in data.values()
                        if not d.get("missing")])
    assert v.min() >= 0 and v.max() <= 100 and set(np.unique(v)) <= {0.0, 50.0, 100.0}
    c.w["ens_runs"].value = [1]
    ed._remove_run(ed.run_rows[0])  # (run 1 becomes 0)
    assert c.collect()["ens"]["runs"] == [0]
    c.w["ens_on"].value = False
    assert "ens" not in c.collect()


def _t0_spec(**kw):
    """A plan figure of two runs with time zeros 60 and 90 min: runs by times."""
    return dict(dict(kind="plan", rows=2, cols=2, run=0, time_s=3900.0, times_s=[3900.0, 4200.0],
                     runs=[dict(path="a", t0_min=60.0), dict(path="b", t0_min=90.0)],
                     grid=dict(rows="runs", cols="times", runs=[]),
                     layers=[dict(type="fill", field="dbz", on=True)]), **kw)


def test_run_time_zeros_move_times_taken_from_another_run():
    from cm1view.figures import draw as figdraw, spec as fg
    s = _t0_spec()
    assert [fg.panel_ref(s, i) for i in range(4)] == [(0, 3900.0), (0, 4200.0),
                                                      (1, 5700.0), (1, 6000.0)]
    # a grid's first run sets the times, whichever run that is
    assert fg.panel_ref(_t0_spec(grid=dict(rows="runs", cols="times", runs=[1, 0])), 2) == \
        (0, 2100.0)
    # a run taken over moves; a time picked for a run stays its model time
    s = _t0_spec(grid=dict(rows="none", cols="times", runs=[]), rows=1,
                 edits={"0": dict(run=1), "1": dict(run=1, time_s=4200.0)})
    assert fg.panel_ref(s, 0) == (1, 5700.0)
    assert fg.panel_ref(s, 1) == (1, 4200.0)
    # layers, differences and ensembles of another run: the same time since time zero
    s = _t0_spec(grid=dict(rows="none", cols="times", runs=[]), rows=1)
    lay = s["layers"][0]
    assert fg.minus_ref(s, 0, dict(lay, minus=dict(run=1))) == (1, 5700.0)
    assert fg.minus_ref(s, 0, dict(lay, minus=dict(run=1, time_s=4500.0))) == (1, 4500.0)
    assert fg.minus_ref(s, 0, dict(lay, minus=dict(run=None, time_s=None))) == (0, 3900.0)
    assert fg.ens_refs(s, 0, dict(lay, ens=dict(runs=None))) == [(0, 3900.0), (1, 5700.0)]
    assert fg.ens_refs(s, 0, dict(lay, run=1, time_s=5700.0, ens=dict(runs=None))) == \
        [(0, 3900.0), (1, 5700.0)]
    s["layers"].append(dict(type="contour", field="w", on=True, run=1))
    s["layers"].append(dict(type="contour", field="w", on=True, run=1, time_s=4200.0))
    assert fg.layer_groups(s, 0) == {(1, 5700.0): [1], (1, 4200.0): [2]}
    # the lookup of a layer's group keeps the times it is given
    g = fg.group_spec(s, 0, (1, 5700.0), {1})
    assert fg.panel_ref(g, 0) == (1, 5700.0)
    # an animation steps every panel alike, time zeros kept
    assert fg.panel_ref(fg.shift_times(_t0_spec(), 300.0), 2) == (1, 6000.0)
    # the label counts from the figure's time zero plus the run's; {model} doesn't
    s = _t0_spec(time_label=dict(fmt="{min:g} of {model:g}", t0_min=5.0))
    assert figdraw.time_text(5700.0, figdraw.run_time_opts(s, 1)) == "0 of 95"
    # no time zero: as before
    for e in s["runs"]:
        e.pop("t0_min")
    assert fg.panel_ref(s, 2) == (1, 3900.0)


def test_a_run_time_zero_on_a_time_series_figure(ed):
    """Set in Runs used, a run's time zero shifts its line and the card's Values rows
    (not their model times), and is kept with the figure."""
    ed.from_series()
    ed.kind.value = "line"
    spec = ed.collect()
    ed.panel_data(spec)  # (starts computing the series)
    wait(lambda: not ed.series_pending(), 120, "the series")
    t = ed.panel_data(ed.collect())[0]["S0_t"]
    c = ed.ser_cards[0]
    c.vals.section.collapsed = False
    before = c.vals.w["table"].value
    ed.run_rows[0]["t0"].value = 30.0
    spec = ed.collect()
    assert spec["runs"][0]["t0_min"] == 30.0
    np.testing.assert_allclose(ed.panel_data(spec)[0]["S0_t"], t - 30.0)
    after = c.vals.w["table"].value  # (refreshed by the time zero)
    np.testing.assert_allclose(after["t"], before["t"] - 30.0)
    assert list(after["model_s"]) == list(before["model_s"])
    ed.run_rows[0]["t0"].value = 0.0


def test_a_time_zero_with_cards_and_no_output_there(ed, demo_root):
    import os
    from cm1view.figures import spec as fg
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.gg_runs.value = [0, 1]
    ed.g_rows.value = "runs"
    ed.cols.value, ed.tstep.value = 2, 1
    ed.tm_rows[0].value, ed.tm_rows[1].value = 3600.0, 3900.0
    assert "t0_min" not in ed.collect()["runs"][1]  # (none: as saved before)
    ed.run_rows[1]["t0"].value = 5.0  # (one output of the demo)
    ed._set_titles([], [])  # (only the panels' time labels below)
    spec, data, fig = render(ed)
    assert spec["runs"][1]["t0_min"] == 5.0
    assert [d["time_s"] for d in data.values()] == [3600.0, 3900.0, 3900.0, 4200.0]
    assert not any(d.get("missing") for d in data.values())
    from matplotlib.text import Text
    texts = [t.get_text() for a in fig.axes for t in a.findobj(Text)]
    assert texts.count("t = 60 min") == 2  # (both runs at 60 of the first)
    last = ed.tm_rows[0].options
    assert any("not in every run" in k and v == float(ed.run.times[-1]) for k, v in last.items())
    ed.set_spec(json.loads(json.dumps(spec)))  # round trip
    assert ed.run_rows[1]["t0"].value == 5.0
    ed.run_rows[1]["t0"].value = 7.0  # (between outputs: said, not moved to the nearest)
    data = ed.panel_data(ed.collect())
    assert "no output at 67 min" in data[2]["missing"] and "time zero: 7" in data[2]["missing"]
    assert not data[0].get("missing")
    ed.run_rows[1]["t0"].value = 5.0
    ed.kind.value = "xsec"  # section cards: copies at the matching time, kept when it changes
    while len(ed.sec_cards) > 1:
        ed._remove_section(ed.sec_cards[-1])
    c = ed.sec_cards[0]
    c.w["pos"].value = "fixed"
    c.set_run(0, 3600.0)
    ed._per_run_section(c)
    assert [(x.w["run"].value, x.w["time"].value) for x in ed.sec_cards] == \
        [(0, 3600.0), (1, 3900.0)]
    for t0 in (6.0, 7.0, 8.0, 9.0, 10.0):  # (small steps add up)
        ed.run_rows[1]["t0"].value = t0
    assert ed.sec_cards[1].w["time"].value == 4200.0 and c.w["time"].value == 3600.0
    ed.run_rows[0]["t0"].value = 5.0  # (the first card's run: the others move)
    assert ed.sec_cards[1].w["time"].value == 3900.0 and c.w["time"].value == 3600.0
    ed.run_rows[0]["t0"].value = ed.run_rows[1]["t0"].value = 0.0


def test_run_time_zeros_on_entries_of_their_own_time():
    """A profile of several runs reads each at the matching time; entries at one moment
    share a time label; animations step each run at its own time."""
    from cm1view.figures import spec as fg
    from cm1view.figures.draw import base
    runs = [dict(path="a", t0_min=60.0), dict(path="b", t0_min=90.0), dict(path="c")]
    s = dict(kind="profile", runs=runs, time_label={})
    e = dict(run=0, runs=[0, 1], time_s=3900.0, time_s1=None, panel=0, recipe={})
    assert fg.entry_at(s, e, 0) is e  # (its own run's times: as they are)
    assert fg.entry_at(s, e, 1)["time_s"] == 5700.0 and e["time_s"] == 3900.0
    win = dict(e, time_s1=4200.0)
    assert fg.entry_at(s, win, 1)["time_s1"] == 6000.0
    assert fg.entry_run(dict(e, runs=None)) == 0 and fg.entry_run(dict(e, runs=[2, 1])) == 2
    assert fg.entry_run(dict(run=1, time_s=0.0)) == 1  # (a card of one run)
    # in legends: since the time zero
    assert fg.profile_when(fg.since_t0(s, e)) == "5 min"
    assert fg.time_key(s, e) == fg.time_key(s, dict(e, run=1, runs=[1], time_s=5700.0))
    assert fg.time_key(s, win)[1] == 600.0
    # animations: each run's own times
    assert fg.time_refs(dict(s, profiles=[e])) == [("a", 3900.0), ("b", 5700.0)]
    # a panel at one moment: the first's time and run, so its label counts from its t0
    asked = []

    def get(i, k):
        asked.append(k)
        return np.array([0.0, 1.0]), np.array([1.0, 2.0])

    d = fg.profile_panel(dict(s, profiles=[e]), 0, get)
    assert asked == [0, 1] and (d["time_s"], d["run"]) == (3900.0, 0)
    text = base.time_text(d["time_s"], base.run_time_opts(s, d["run"]))
    assert text == "t = 5 min"
    # two cards at one moment since t0, then at two moments
    a, b = dict(e, runs=[0]), dict(e, run=1, runs=[1], time_s=5700.0)
    assert fg.profile_panel(dict(s, profiles=[a, b]), 0, get)["time_s"] == 3900.0
    d = fg.profile_panel(dict(s, profiles=[a, dict(b, time_s=3900.0)]), 0, get)
    assert "time_s" not in d
    d = fg.profile_panel(dict(s, profiles=[win]), 0, get)  # (a window: no one time)
    assert "time_s" not in d
    # no time zero: as before
    plain = [dict(path="a"), dict(path="b")]
    assert fg.entry_at(dict(runs=plain), e, 1) is e
    assert fg.since_t0(dict(runs=plain), e) is e


def test_a_time_zero_moves_cards_with_their_own_time(ed, demo_root):
    import os
    from cm1view.figures import spec as fg
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.kind.value = "profile"
    ed._add_profile()
    ed._add_profile()
    d, c = ed.prof_cards[-2:]
    ed.prof_cards[:] = [d, c]
    d.set_runs([0])
    d.w["time"].value = 3600.0
    c.set_runs([0, 1])
    c.w["time"].value = 3600.0
    ed.run_rows[1]["t0"].value = 5.0  # (one output of the demo)
    assert c.w["time"].value == 3600.0  # (the first run's stays; run 2's line moves)
    assert fg.entry_at(ed.collect(), c.collect(), 1)["time_s"] == 3900.0
    assert not c.t_note.object
    # a card of one run: picking the other run keeps the moment
    c.set_runs([0])
    c.w["run"].value = 1
    assert c.w["time"].value == 3900.0
    # a card of the other run moves with its time zero, by small steps too
    for t0 in (6.0, 7.0, 8.0, 9.0, 10.0):
        ed.run_rows[1]["t0"].value = t0
    assert c.w["time"].value == 4200.0 and d.w["time"].value == 3600.0
    ed.run_rows[0]["t0"].value = 5.0  # (the first card's run: the others move)
    assert c.w["time"].value == 3900.0 and d.w["time"].value == 3600.0
    ed.run_rows[0]["t0"].value = 0.0
    ed.run_rows[1]["t0"].value = 0.0
    # one per run copies at the matching time
    c.set_runs([0])
    c.w["time"].value = 3600.0
    ed.run_rows[1]["t0"].value = 5.0
    n = len(ed.prof_cards)
    ed._per_run_prof(c)
    assert len(ed.prof_cards) == n + 1
    assert ed.prof_cards[ed.prof_cards.index(c) + 1].w["time"].value == 3900.0
    # between outputs: a card of two runs says which has no line
    c.set_runs([0, 1])
    ed.run_rows[1]["t0"].value = 7.0
    c.time_note()
    assert "no output at 67 min" in c.t_note.object
    ed.run_rows[1]["t0"].value = 0.0


def _paired_spec(**kw):
    """A grid of two runs paired by output number: run 2 outputs every 10 min, 3 outputs
    to the first's 4 every 5 min, with a time zero on the first."""
    return _t0_spec(**dict(dict(
        time_match="output", time_s=3600.0, times_s=[3600.0, 3900.0],
        runs=[dict(path="a", t0_min=60.0, outputs_s=[3600.0, 3900.0, 4200.0, 4500.0]),
              dict(path="b", t0_min=7.0, outputs_s=[0.0, 600.0, 1200.0])]), **kw))


class _Run:
    def __init__(self, times):
        self.times = np.asarray(times, dtype=float)


def test_runs_paired_by_output_number():
    from cm1view.figures import draw as figdraw, spec as fg
    s = _paired_spec()
    # the nth output of each run; a time zero doesn't move it
    assert [fg.panel_ref(s, i) for i in range(4)] == [(0, 3600.0), (0, 3900.0),
                                                      (1, 0.0), (1, 600.0)]
    assert figdraw.moved_time(s, 1200.0, 1, 0) == 4200.0
    assert figdraw.moved_time(s, 1200.0, 1, 1) == 1200.0
    # past the shorter run's end: a time it has no output at, so its panel is blank
    late = figdraw.moved_time(s, 4500.0, 0, 1)
    assert late > 1200.0 and fg.tindex(_Run([0.0, 600.0, 1200.0]), late) is None
    # between outputs: none in the other run either
    assert fg.tindex(_Run([0.0, 600.0, 1200.0]), figdraw.moved_time(s, 3750.0, 0, 1)) is None
    # within a second of an output is that output
    assert figdraw.moved_time(s, 3900.5, 0, 1) == 600.0
    # differences, ensembles and layers of another run read the same outputs
    s1 = _paired_spec(grid=dict(rows="none", cols="times", runs=[]), rows=1)
    lay = s1["layers"][0]
    assert fg.minus_ref(s1, 1, dict(lay, minus=dict(run=1))) == (1, 600.0)
    assert fg.ens_refs(s1, 1, dict(lay, ens=dict(runs=None))) == [(0, 3900.0), (1, 600.0)]
    s1["layers"].append(dict(type="contour", field="w", on=True, run=1))
    assert fg.layer_groups(s1, 1) == {(1, 600.0): [1]}
    # both runs' labels: the reference run's minutes since its time zero; {model} its own
    s2 = _paired_spec(time_label=dict(fmt="{min:g} of {model:g}"))
    assert figdraw.time_text(600.0, figdraw.run_time_opts(s2, 1, 600.0)) == "5 of 10"
    assert figdraw.time_text(3900.0, figdraw.run_time_opts(s2, 0, 3900.0)) == "5 of 65"
    # without their outputs_s, the time zeros again (and figures saved before)
    plain = _t0_spec()
    assert figdraw.output_times(plain, 0) is None
    assert fg.panel_ref(plain, 2) == (1, 5700.0)


def test_entries_of_runs_paired_by_output_number():
    from cm1view.figures import spec as fg
    s = _paired_spec(kind="profile", time_label={})
    e = dict(run=0, runs=[0, 1], time_s=3900.0, time_s1=4200.0, panel=0, recipe={})
    at = fg.entry_at(s, e, 1)
    assert (at["time_s"], at["time_s1"]) == (600.0, 1200.0)
    assert fg.entry_at(s, e, 0) is e
    # two cards at one output share a label, whatever their model times
    other = dict(e, run=1, runs=[1], time_s=600.0, time_s1=1200.0)
    assert fg.time_key(s, e) == fg.time_key(s, other)
    assert fg.since_t0(s, other)["time_s"] == 300.0  # (5 min of the reference run)


def test_animating_runs_paired_by_output_number():
    from cm1view.figures import spec as fg
    runs = {"a": _Run([3600.0, 3900.0, 4200.0, 4500.0]), "b": _Run([0.0, 600.0, 1200.0])}
    s = _paired_spec()
    off = fg.frame_offsets(s, runs)
    assert [float(d) for d in off] == [0.0, 300.0]  # (panels from the second output: 2 left)
    f = fg.shift_times(s, off[1])
    assert [fg.panel_ref(f, i) for i in range(4)] == [(0, 3900.0), (0, 4200.0),
                                                      (1, 600.0), (1, 1200.0)]
    # times of its own on a card, a panel, a layer: each steps its own run's outputs
    c = dict(_paired_spec(), sections=[dict(run=1, time_s=600.0, panel=0)],
             soundings=[dict(run=1, time_s=0.0, time_s1=600.0)],
             edits={"2": dict(time_s=0.0, layers={"0": dict(time_s=3600.0, run=0)})})
    f = fg.shift_times(c, fg.OutputStep(300.0, 1))
    assert f["sections"][0]["time_s"] == 1200.0
    assert (f["soundings"][0]["time_s"], f["soundings"][0]["time_s1"]) == (600.0, 1200.0)
    assert f["edits"]["2"]["time_s"] == 600.0
    assert f["edits"]["2"]["layers"]["0"]["time_s"] == 3900.0
    # any other figure takes the step's seconds
    assert fg.panel_ref(fg.shift_times(_t0_spec(), fg.OutputStep(300.0, 1)), 2) == (1, 6000.0)
    # a figure of parts: each part as it pairs its runs
    combo = dict(kind="combo", parts=[_paired_spec(), _t0_spec()])
    f = fg.shift_times(combo, fg.OutputStep(300.0, 1))
    assert fg.panel_ref(f["parts"][0], 2) == (1, 600.0)
    assert fg.panel_ref(f["parts"][1], 2) == (1, 6000.0)


def test_paired_series_use_the_reference_runs_times():
    from cm1view.figures import spec as fg
    import xarray as xr
    s = _paired_spec(kind="line", time_label={})
    ds = xr.Dataset(dict(value=("t", np.array([1.0, 2.0, 3.0])),
                         computed=("t", np.array([1, 1, 1]))))
    ent = dict(field="w", t0_min=1.0)
    t, v, _, _ = fg.series_of_run(s, _Run([0.0, 600.0, 1200.0]), ds, ent, 1)
    np.testing.assert_allclose(t, [-1.0, 4.0, 9.0])  # (the first's t0 + the card's)
    # a run with more outputs than the reference: on at its last spacing
    t, _, _, _ = fg.series_of_run(s, _Run(np.arange(5) * 60.0),
                                  xr.Dataset(dict(value=("t", np.zeros(5)),
                                                  computed=("t", np.ones(5, dtype=int)))), ent, 1)
    np.testing.assert_allclose(t, [-1.0, 4.0, 9.0, 14.0, 19.0])
    # a figure not pairing: as before
    t, _, _, _ = fg.series_of_run(_t0_spec(time_label={}), _Run([0.0, 600.0, 1200.0]), ds, ent, 1)
    np.testing.assert_allclose(t, [-91.0, -81.0, -71.0])


def test_pairing_by_output_number_in_the_editor(ed, demo_root):
    import os
    from cm1view.figures import spec as fg
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    ed.gg_runs.value = [0, 1]
    ed.g_rows.value = "runs"
    ed.cols.value, ed.tstep.value = 2, 1
    ed.tm_rows[0].value, ed.tm_rows[1].value = 3600.0, 3900.0
    spec = ed.collect()
    assert "time_match" not in spec and "outputs_s" not in spec["runs"][0]  # (as saved before)
    ed.run_rows[1]["t0"].value = 5.0
    assert not ed.run_rows[1]["t0"].disabled
    ed.time_match.value = "output"
    assert ed.run_rows[1]["t0"].disabled and not ed.run_rows[0]["t0"].disabled
    spec = ed.collect()
    assert spec["time_match"] == "output"
    assert spec["runs"][1]["outputs_s"] == [float(t) for t in ed.open_run(spec["runs"][1]["path"])[0].times]
    # the same outputs: the demo's runs share their times, so the time zero moves nothing
    assert fg.panel_ref(spec, 2) == (1, 3600.0)
    data = ed.panel_data(spec)
    assert not any(d.get("missing") for d in data.values())
    ed.set_spec(json.loads(json.dumps(spec)))  # round trip
    assert ed.time_match.value == "output" and ed.run_rows[1]["t0"].disabled
    # Offsets don't move cards while pairing
    ed.kind.value = "xsec"
    c = ed.sec_cards[0]
    c.set_run(1, 3900.0)
    ed.run_rows[0]["t0"].value = 10.0
    assert c.w["time"].value == 3900.0
    ed.run_rows[0]["t0"].value = 0.0
    ed.time_match.value = "time"
    assert "time_match" not in ed.collect() and not ed.run_rows[1]["t0"].disabled
    ed.run_rows[1]["t0"].value = 0.0


def test_a_saved_figure_pairs_runs_by_their_outputs_now():
    from cm1view.figures import spec as fg
    s = dict(kind="combo", parts=[_paired_spec(), _t0_spec()])
    fg.fill_outputs(s, lambda p: (_Run([0.0, 60.0]), None))
    assert s["parts"][0]["runs"][1]["outputs_s"] == [0.0, 60.0]
    assert "outputs_s" not in s["parts"][1]["runs"][0]


def test_a_run_added_again_gets_its_settings_back(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    own = ed.run_rows[0]["path"]
    ed._prune_runs()  # (notes that the viewer's run is used)
    r = ed.run_rows[0]
    r["label"].value, r["t0"].value, r["color"].value = "main", 30.0, "#123456"
    ed.run_sel.value = weak
    ed._prune_runs()  # (the viewer's run is dropped)
    assert [x["path"] for x in ed.run_rows] == [weak]
    ed.run_sel.value = own
    r = next(x for x in ed.run_rows if x["path"] == own)
    assert (r["label"].value, r["t0"].value, r["color"].value) == ("main", 30.0, "#123456")


def test_a_new_figure_forgets_the_runs_taken_out(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.add_path.value = weak
    k = ed._add_run()
    ed.run_rows[k]["label"].value = "mine"
    ed._remove_run(ed.run_rows[k])
    ed.set_spec(ed.collect())
    k = ed._add_run(weak)
    assert ed.run_rows[k]["label"].value == "supercell_weak"
