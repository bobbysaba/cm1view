"""Figure workspace with several runs: grids of runs, run lists and pickers, panel times
from each panel's run, run colours, and templates applied to another run."""
import json

import numpy as np

from conftest import txt, wait, render


def test_fill_a_grid_of_runs_and_times(ed, demo_root):
    import os
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    assert len(ed.run_rows) == 2 and ed.vary.value == "time"  # (adding a run keeps the panels)
    ed.gg_runs.value, ed.gg_n.value, ed.gg_step.value = [0, 1], 3, 1
    ed._fill_grid()
    assert ed.vary.value == "custom" and ed.rows.value == 2 and ed.cols.value == 3
    assert [r["run"].value for r in ed.pc_rows] == [0, 0, 0, 1, 1, 1]
    assert ed.pc_rows[0]["time"].value < ed.pc_rows[1]["time"].value
    s = ed.collect()
    assert s["vary"] == "custom" and [p["run"] for p in s["panels"]] == [0, 0, 0, 1, 1, 1]
    spec, data, fig = render(ed)
    assert {d.get("run_label") for d in data.values()} == {"supercell", "supercell_weak"}
    ed.gg_as.value = "cols"  # runs as columns: a row per time
    ed._fill_grid()
    assert ed.rows.value == 3 and ed.cols.value == 2
    assert [r["run"].value for r in ed.pc_rows] == [0, 1, 0, 1, 0, 1]


def test_an_older_run_by_time_grid_opens_as_panels_with_their_own_run(ed, demo_root):
    import os
    ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
    ed._add_run()
    s = ed.collect()
    t0, t1 = float(ed.run.times[0]), float(ed.run.times[1])
    s.update(vary="grid", runs_as="rows", rows=2, cols=2, times_s=[t0, t1], panels=[])
    old = render_spec(ed, s)
    ed.set_spec(json.loads(json.dumps(s)))
    got = ed.collect()
    assert got["vary"] == "custom" and [p["run"] for p in got["panels"]] == [0, 0, 1, 1]
    assert [p["time_s"] for p in got["panels"][:2]] == [t0, t1]
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
    ed.vary.value = "time"
    ed.run_sel.value = 1
    crun = ed.open_run(coarse_run)[0]
    s = ed.collect()
    assert all(t in list(crun.times) for t in s["times_s"] if t is not None)
    ts = [t for t in s["times_s"] if t is not None]  # still different times (as far as
    assert len(set(ts)) == min(len(ts), len(crun.times))  # the run has outputs)
    spec, data, fig = render(ed)
    assert not any(d.get("missing") for d in data.values())
    ed.vary.value = "field"
    assert ed.time1.value in list(crun.times)
    ed.gg_runs.value, ed.gg_n.value = [0, 1], 2  # a grid: each panel's own run's outputs
    ed._fill_grid()
    assert all(r["time"].value in list(crun.times) for r in ed.pc_rows[2:])


def test_reopened_spec_keeps_times_of_another_run(ed, coarse_run):
    ed.add_path.value = coarse_run
    ed._add_run()
    ed.vary.value = "time"
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
    assert len(ed.run_rows) == 2 and ed.run_sel.value == 1 and ed.vary.value == "time"
    assert ed.collect()["runs"][1]["track"].endswith("demo_supercell_weak.csv")
    assert weak not in ed._other_runs().values()
    spec, data, fig = render(ed)
    assert not any(d.get("missing") for d in data.values())


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


def test_series_runs_list_offers_other_runs(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.from_series()
    ed.kind.value = "line"
    c = ed.ser_cards[0]
    assert weak in c.w["runs"].options.values()
    c.w["runs"].value = [0, weak]  # picking it adds it to the figure
    assert [r["path"] for r in ed.run_rows][-1] == weak
    assert c.w["runs"].value == [0, 1] and ed.collect()["series"][0]["runs"] == [0, 1]
    assert weak not in c.w["runs"].options.values()


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
    ed.gg_runs.value = [0, 1]  # a grid of the two runs
    ed._fill_grid()
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
    ax = Figure().subplots()
    _lines(ax, dict(nlines=1, S0_e=0, S0_r=1, S0_t=t, S0_v=t, S0_label="w"),
           dict(runs=runs, series=[dict(color="#0000ff")]), 10)
    assert to_hex(ax.lines[0].get_color()) == "#aa0000"
    ax = Figure().subplots()  # two series of run 1: the series' colours, run 1's line style
    _lines(ax, dict(nlines=2, S0_e=0, S0_r=1, S0_t=t, S0_v=t, S0_label="a",
                    S1_e=1, S1_r=1, S1_t=t, S1_v=t, S1_label="b"),
           dict(runs=runs, series=[dict(color="#0000ff"), dict(color="#ff00ff")]), 10)
    assert [to_hex(ln.get_color()) for ln in ax.lines] == ["#0000ff", "#ff00ff"]
    assert {ln.get_linestyle() for ln in ax.lines} == {"--"}


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


def test_time_height_grid_grows_with_a_series_run(ed, demo_root):
    import os
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    ed.from_series()
    ed.kind.value = "th"
    assert (ed.rows.value, ed.cols.value) == (len(ed.ser_cards), 1)
    ed.ser_cards[0].w["runs"].value = [0, weak]  # a column for the run it adds
    assert (ed.rows.value, ed.cols.value) == (len(ed.ser_cards), 2)
    from cm1view.figures import draw as figdraw
    assert figdraw.series_ref(ed.collect(), 1) == (1, 0)
