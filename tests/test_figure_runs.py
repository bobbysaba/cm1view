"""Figure workspace with several runs: grids of runs, run lists and pickers, panel times
from the panels' run, run colours, and templates applied to another run."""

import numpy as np


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


def test_a_saved_figure_pairs_runs_by_their_outputs_now():
    from cm1view.figures import spec as fg
    s = dict(kind="combo", parts=[_paired_spec(), _t0_spec()])
    fg.fill_outputs(s, lambda p: (_Run([0.0, 60.0]), None))
    assert s["parts"][0]["runs"][1]["outputs_s"] == [0.0, 60.0]
    assert "outputs_s" not in s["parts"][1]["runs"][0]


