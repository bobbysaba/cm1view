"""Figure spec version 2: upgrades from version 1, panels spanning cells, shared colorbar
ends, and the panel tree."""
import json

import numpy as np
import pytest

from conftest import edited_v1


# ------------------------------------------------------------------ spec version 2


def test_upgrade_writes_out_each_panel():
    from cm1view.figures import draw as figdraw
    lay = dict(type="fill", on=True, field="dbz", mode="height", z=1.0, cmap="viridis",
               vmin=0.0, vmax=60.0, extend="max")
    cont = dict(type="contour", on=True, field="w", mode="height", z=3.0, levels="5",
                z_fixed=True, panels=[2])
    v1 = dict(version=1, kind="plan", rows=1, cols=3, vary="height", time_s=600.0,
              times_s=[600.0], panel_z=[1.0, 3.0, 6.0], panel_zmode="height", run=0,
              layers=[lay, cont], titles=["A", "", "C"], runs=[dict(path="/r", label="r")],
              size=[8, 3], letters=dict(on=True), contour_key=dict(on=True, layer=-1),
              annotations=[dict(kind="text", panel=1, text="x")])
    v2, _ = figdraw.upgrade(v1)
    pans = v2["panels"]
    assert [p["z"] for p in pans] == [1.0, 3.0, 6.0]
    assert [p["layers"][0]["z"] for p in pans] == [1.0, 3.0, 6.0]  # the fill follows the panel
    assert [p["layers"][1]["on"] for p in pans] == [False, False, True]  # (panels=[2])
    assert [p["title"] for p in pans] == ["A", "", "C"] and [p["letter"] for p in pans] == [0, 1, 2]
    assert [p["cell"] for p in pans] == [[0, 0, 1, 1], [0, 1, 1, 1], [0, 2, 1, 1]]
    assert all((p["run"], p["time_s"]) == (0, 600.0) for p in pans)
    assert v2["blocks"] == [dict(rows=1, cols=3)] and "layers" not in v2
    assert v2["contour_key"]["lay"]["field"] == "w"
    assert figdraw.upgrade(v2)[0] is v2  # (already version 2)
    assert v1["layers"][0]["extend"] == "max" and "lay" not in v1["contour_key"]  # (untouched)


def test_upgrade_counts_soundings_within_their_panel():
    from cm1view.figures import draw as figdraw
    snd = [dict(run=0, time_s=0.0, panel=0), dict(run=1, time_s=0.0, panel=1),
           dict(run=1, time_s=60.0, panel=0)]
    v1 = dict(version=1, kind="sounding", rows=1, cols=2, soundings=snd, size=[8, 4],
              runs=[dict(path="/a"), dict(path="/b")])
    data = {0: dict(nsnd=2, N0_e=0, N1_e=2), 1: dict(nsnd=1, N0_e=1)}
    v2, d2 = figdraw.upgrade(v1, data)
    p0, p1 = v2["panels"]
    assert [lay["run"] for lay in p0["layers"]] == [0, 1] and p1["layers"][0]["run"] == 1
    assert all(lay["type"] == "sounding" and "panel" not in lay for lay in p0["layers"])
    assert (d2[0]["N0_e"], d2[0]["N1_e"], d2[1]["N0_e"]) == (0, 1, 0)
    assert data[0]["N1_e"] == 2  # (the caller's data unchanged)


def test_upgrade_of_parts_keeps_each_parts_settings():
    from cm1view.figures import draw as figdraw
    part = dict(version=1, kind="plan", rows=2, cols=1, vary="time", times_s=[0.0, 60.0],
                run=0, layers=[], runs=[dict(path="/b")], size=[4, 6], share=0.4,
                font=dict(size=8), annotations=[dict(panel=1), dict(panel=-1),
                                                 dict(panel=[0, 1])])
    combo = dict(version=1, kind="combo", arrange="row", parts=[dict(part, share=None), part],
                 size=[8, 6], colorbar=dict(mode="parts"), runs=[dict(path="/b")])
    v2, _ = figdraw.upgrade(combo)
    assert [p["id"] for p in v2["panels"]] == [0, 1, 1000, 1001]
    assert [p["letter"] for p in v2["panels"]] == [0, 1, 2, 3]
    b = v2["blocks"][1]
    assert (b["rows"], b["cols"], b["share"]) == (2, 1, 0.4)
    assert [a["panel"] for a in b["opts"]["annotations"]] == [1001, -1, [1000, 1001]]
    assert figdraw.block_view(v2, 1)["font"] == dict(size=8)
    assert figdraw.block_shares(v2) == pytest.approx([0.6, 0.4])


def test_colorbar_ends_auto_and_shared():
    from cm1view.figures import draw as figdraw
    lay = dict(type="fill", vmin=0.0, vmax=10.0, extend="auto")
    assert figdraw.extend_of(lay, np.array([1.0, 5.0])) == "neither"
    assert figdraw.extend_of(lay, np.array([1.0, 12.0, np.nan])) == "max"
    assert figdraw.extend_of(lay, np.array([-1.0, 12.0])) == "both"
    assert figdraw.extend_of(dict(lay, mask_below=0.0), np.array([-1.0, 5.0])) == "neither"
    assert figdraw.extend_of(dict(lay, extend="min"), np.array([5.0])) == "min"
    assert figdraw.union_extend(["min", "max"]) == "both"
    assert figdraw.union_extend(["neither", "max"]) == "max"
    assert figdraw.union_extend([]) == "neither"


def _v2_plan(mode="shared"):
    x = np.linspace(-5.0, 5.0, 11)
    fill = dict(type="fill", on=True, cmap="viridis", vmin=0.0, vmax=10.0, extend="auto",
                style="mesh", units="dBZ")
    track = dict(type="track", on=True, run_color=True, run=1)
    spec = dict(version=2, size=[8.0, 6.0], blocks=[dict(rows=2, cols=2)],
                colorbar=dict(mode=mode), letters=dict(on=True), axes=dict(ticklabels="outer"),
                runs=[dict(path="/a"), dict(path="/b", color="#00ff00")],
                panels=[dict(id=0, kind="plan", cell=[0, 0, 1, 1], layers=[fill]),
                        dict(id=1, kind="plan", cell=[0, 1, 1, 1], layers=[fill]),
                        dict(id=2, kind="plan", cell=[1, 0, 1, 2], layers=[fill, track],
                             letter=5, z=2.0)])
    a = np.tile(x, (11, 1))
    data = {0: dict(x=x, y=x, L0=a + 10.0, time_s=0.0),  # past vmax
            1: dict(x=x, y=x, L0=a, time_s=0.0),  # below vmin
            2: dict(x=x, y=x, L0=a * 0.1 + 5.0, time_s=0.0, track_x=x, track_y=x)}
    return spec, data


def test_version_2_panels_span_cells_and_share_colorbar_ends():
    from cm1view.figures import draw as figdraw
    from matplotlib.colors import to_hex
    spec, data = _v2_plan()
    assert figdraw._extends(spec, data) == {0: "both", 1: "both", 2: "both"}
    fig = figdraw.draw(spec, data)
    axs = fig._cv_axes
    assert set(axs) == {0, 1, 2}
    # panel 2 spans both columns: centred under them (an equal-aspect map of square data
    # stays square, so its width does not double)
    c = [(axs[i].get_position().x0 + axs[i].get_position().x1) / 2 for i in (0, 1, 2)]
    assert abs(c[2] - (c[0] + c[1]) / 2) < 0.02 and c[1] - c[0] > 0.2
    assert to_hex(axs[2].lines[0].get_color()) == "#00ff00"  # the track in its own run's colour
    assert "f" in [a.txt._text.get_text() for a in axs[2].artists if hasattr(a, "txt")]
    cbars = [a for a in fig.axes if a not in axs.values()]
    assert len(cbars) == 1
    spec, data = _v2_plan("row")
    assert figdraw._extends(spec, data) == {0: "both", 1: "both", 2: "neither"}
    fig = figdraw.draw(spec, data)
    assert len([a for a in fig.axes if a not in fig._cv_axes.values()]) == 2


def test_animation_colorbar_ends_are_those_of_all_frames():
    from cm1view.figures import draw as figdraw
    spec, data = _v2_plan("none")
    spec["panels"][0]["layers"][0]["nlevels"] = 10  # (every panel's: the norm has the ends)
    calm ={i: dict(d, L0=np.full((11, 11), 5.0)) for i, d in data.items()}
    ends = figdraw.fill_ends(spec, calm)
    assert ends == {(0, 0): "neither", (1, 0): "neither", (2, 0): "neither"}
    ends = figdraw.fill_ends(spec, data, ends)  # a later frame past vmin / vmax
    assert ends == {(0, 0): "max", (1, 0): "min", (2, 0): "neither"}
    assert figdraw.fill_ends(spec, calm, ends) == ends  # (ends only grow)
    fig = figdraw.draw(spec, calm, ends)  # the calm frame keeps panel 0's arrow
    assert [fig._cv_axes[i].collections[0].norm.extend for i in (0, 1, 2)] == \
        ["max", "min", "neither"]
    assert spec["panels"][0]["layers"][0]["extend"] == "auto"  # (the spec untouched)


def test_layers_take_the_panels_run_time_and_height():
    from cm1view.figures import draw as figdraw
    p = dict(run=1, time_s=600.0, z=2.0)
    assert figdraw.resolved(p, dict(type="fill", z=None)) == \
        dict(type="fill", run=1, time_s=600.0, z=2.0)
    assert figdraw.resolved(p, dict(type="fill", run=0, z=5.0))["run"] == 0
    assert figdraw.resolved({}, dict(type="fill"))["run"] == 0


# ------------------------------------------------------------------ the panel tree
def test_panel_edit_y_range_is_that_panel_s_and_keeps_its_legend():
    from cm1view.figures import draw as figdraw
    v1 = dict(version=1, kind="line", rows=1, cols=2, size=[8, 4], ts=dict(ymin=-1.0, ymax=9.0),
              series=[dict(panel=0), dict(panel=1)],
              edits={"1": dict(ymax=0.0, legend=dict(on=False))})
    v2, _ = figdraw.upgrade(v1)
    a, b = (figdraw.panel_view(v2, p)["ts"] for p in v2["panels"])
    assert (a["ymin"], a["ymax"]) == (-1.0, 9.0)
    assert (b["ymin"], b["ymax"], b["legend"]) == (-1.0, 0.0, False)


def test_panel_edits_change_that_panel_alone():
    from cm1view.figures import draw as figdraw
    v1 = edited_v1()
    assert figdraw.panel_ref(v1, 0) == (0, 0.0) and figdraw.panel_ref(v1, 1) == (1, 900.0)
    assert figdraw.form_ref(v1, 1) == (0, 300.0)
    lays = figdraw.spec_layers(v1, 1)
    assert len(lays) == 2 and lays[1]["type"] == "contour"  # (the extra layer)
    assert (lays[0]["z"], lays[0]["cmap"], lays[0]["run"]) == (2.0, "magma", 0)
    assert figdraw.spec_layers(v1, 0)[0]["cmap"] == "viridis"
    v2, _ = figdraw.upgrade(v1)
    p0, p1 = v2["panels"][:2]
    assert (p0["title"], p1["title"]) == ("A", "B")
    assert (p1["run"], p1["time_s"], p1["z"]) == (1, 900.0, 2.0) and "z" not in p0
    assert p1["layers"][0]["time_s"] == 60.0 and len(p1["layers"]) == 2
    assert "edits" not in v2 and "edits" not in (v2["blocks"][0].get("opts") or {})


def test_layers_of_another_run_or_time_are_read_apart():
    from cm1view.figures import spec as fg
    v1 = edited_v1()
    assert fg.layer_groups(v1, 1) == {(0, 60.0): [0]}  # the fill; the contours: the panel's
    assert fg.layer_groups(v1, 0) == {}
    g = fg.group_spec(v1, 1, (0, 60.0), {0})
    assert fg.panel_ref(g, 0) == (0, 60.0)
    assert [lay["on"] for lay in fg.figdraw.spec_layers(g, 0)] == [True, False]
    x = np.arange(3.0)
    d = fg.merge_group(dict(x=x, y=x, L1=1), dict(x=x + 5, y=x, L0=2, L0_u=3), [0],
                       fg.figdraw.spec_layers(v1, 1))
    assert (d["L0"], d["L0_u"], d["L1"]) == (2, 3, 1) and d["L0_cx"][0] == 5.0


def test_animation_moves_edited_times_but_locked_layers():
    from cm1view.figures import spec as fg
    v1 = edited_v1()
    v1["edits"]["1"]["extra"][0].update(time_s=60.0, time_lock=True)
    s = fg.shift_times(v1, 120.0)
    e = s["edits"]["1"]
    assert e["time_s"] == 1020.0 and e["layers"]["0"]["time_s"] == 180.0
    assert e["extra"][0]["time_s"] == 60.0  # (kept)
    assert v1["edits"]["1"]["time_s"] == 900.0  # (a copy)


def test_annotation_in_several_panels():
    from cm1view.figures.cards.distcard import parse_panels, panels_text
    from cm1view.figures.draw.base import ann_on
    assert [parse_panels(t) for t in ("", "all", "0", "2", "1, 3-4", "a, c-d", "b")] == \
        [-1, -1, -1, 1, [0, 2, 3], [0, 2, 3], 1]
    assert panels_text([0, 2, 3]) == "a, c-d" and panels_text(-1) == "" and panels_text(1) == "b"
    assert parse_panels(panels_text([0, 26, 27])) == [0, 26, 27]  # (past z: numbers)
    a = dict(kind="text", panel=[0, 2])
    assert [ann_on(a, i) for i in range(4)] == [True, False, True, False]
    assert all(ann_on(dict(panel=-1), i) for i in range(4))


# ------------------------------------------------------------------ section cards
def _xsec_grid_v1():
    """A version 1 section figure of two runs (rows) by two sections (columns), the
    last panel at its own time."""
    from cm1view.figures import spec as fg
    fill = dict(type="fill", on=True, field="w", mode="height", z=1.0, cmap="RdBu_r",
                vmin=-10.0, vmax=10.0, extend="both")
    return dict(version=1, kind="xsec", rows=2, cols=2, time_s=600.0, times_s=[600.0],
                run=0, layers=[fill], titles=["", ""], row_titles=["a", "b"],
                grid=dict(rows="runs", cols="sections", runs=[0, 1]), vary="grid",
                runs=[dict(path="/a", label="a"), dict(path="/b", label="b")], size=[8, 6],
                sections=[fg.section_defaults(orient="x", pos="fixed"),
                          fg.section_defaults(orient="y", pos="fixed")],
                xsec=dict(ztop=6.0, dz=0.025, coords="storm"), domain=dict(mode="full"),
                coords="grid", edits={"3": dict(time_s=900.0, title="late")})


def test_section_cards_give_each_panel_its_run_time_and_section():
    """A section figure of cards: each card is one panel's section, run and time (blank:
    the figure's); panels without a card are empty, the grid fits the last card."""
    from cm1view.figures import draw as figdraw, spec as fg
    s = _xsec_grid_v1()
    s.update(grid=dict(rows="none", cols="none", runs=[]), edits={}, rows=2, cols=3,
             sections=[dict(fg.section_defaults(orient="x"), run=0, time_s=None, panel=0),
                       dict(fg.section_defaults(orient="y"), run=1, time_s=900.0, panel=1),
                       dict(fg.section_defaults(orient="angle"), run=1, time_s=300.0,
                            panel=4),
                       dict(fg.section_defaults(orient="x"), run=7, time_s=None, panel=5)])
    assert figdraw.xsec_cards(s) is not None and figdraw.xsec_cards(dict(s, kind="plan")) is None
    assert fg.npanels(s) == 6
    assert [fg.panel_ref(s, i) for i in range(6)] == [(0, 600.0), (1, 900.0), None, None,
                                                    (1, 300.0), None]  # (run 7: none)
    assert [fg.panel_section(s, i)[1]["orient"] for i in (0, 1, 4)] == ["x", "y", "angle"]
    sh = fg.shift_times(s, 60.0)  # (an animation frame: the cards' own times move too)
    assert [fg.panel_ref(sh, i) for i in (0, 1, 4)] == [(0, 660.0), (1, 960.0), (1, 360.0)]
    g = fg.group_spec(s, 1, (0, 120.0), [0])  # (one panel's layers at another run, time)
    assert fg.panel_ref(g, 0) == (0, 120.0) and fg.panel_section(g, 0)[1]["orient"] == "y"
    v2, _ = figdraw.upgrade(s)
    assert [(p["id"], p["run"], p["time_s"]) for p in v2["panels"]] == \
        [(0, 0, 600.0), (1, 1, 900.0), (4, 1, 300.0)]
    k0 = fg.data_key(s, 0, None)  # (another card changing leaves panel 0's arrays)
    s["sections"][1]["half"] = 3.0
    assert fg.data_key(s, 0, None) == k0


def test_older_section_figures_become_cards():
    """to_cards: an older grid of runs × sections becomes a card per panel with its
    run, time (its panel edit's) and section; panel titles stay; cards stay cards."""
    from cm1view.figures import spec as fg
    s = _xsec_grid_v1()
    before = [(fg.panel_ref(s, i), fg.panel_section(s, i)[1]["orient"]) for i in range(4)]
    fg.to_cards(s)
    assert [(c["run"], c["time_s"], c["panel"], c["orient"]) for c in s["sections"]] == \
        [(0, 600.0, 0, "x"), (0, 600.0, 1, "y"), (1, 600.0, 2, "x"), (1, 900.0, 3, "y")]
    assert [(fg.panel_ref(s, i), fg.panel_section(s, i)[1]["orient"])
            for i in range(4)] == before
    assert s["edits"] == {"3": dict(title="late")}
    assert s["grid"] == dict(rows="none", cols="none", runs=[])
    again = json.loads(json.dumps(s))
    assert fg.to_cards(again) == s
    one = dict(_xsec_grid_v1(), rows=1, cols=1, grid=None, vary="time", edits={})
    one.pop("sections")  # (an older figure's one section: spec["xsec"])
    one["xsec"] = dict(mode="storm", angle=0.0, half=8.0, offset=[0.0, 0.0])
    fg.to_cards(one)
    assert [(c["orient"], c["half"], c["panel"], c["run"]) for c in one["sections"]] == \
        [("x", 8.0, 0, 0)]
    plan = dict(_xsec_grid_v1(), kind="plan")
    assert fg.to_cards(json.loads(json.dumps(plan))) == plan  # (not a section figure)


def test_older_time_height_figures_become_cards():
    """th_to_cards: an older time-height grid (a panel per series and run) becomes a
    card per panel with its one run and panel number; the panels show the same; cards
    stay cards; a template keeps the first run's cards."""
    from cm1view.figures import draw as figdraw, spec as fg
    s = dict(kind="th", runs=[dict(path="/a"), dict(path="/b"), dict(path="/c")],
             runs_as="cols", rows=1, cols=1, titles=["A", "", "", "", "", "F"],
             series=[dict(label="w", runs=None, panel=0), dict(label="q", runs=[2], panel=0)])
    before = [(lambda r: r and (r[0], s["series"][r[1]]["label"]))(figdraw.series_ref(s, i))
              for i in range(6)]
    fg.th_to_cards(s)
    assert s["runs_as"] == "cards" and (s["rows"], s["cols"]) == (2, 3)
    assert [(e["label"], e["runs"], e["panel"]) for e in s["series"]] == \
        [("w", [0], 0), ("w", [1], 1), ("w", [2], 2), ("q", [2], 5)]
    assert figdraw.npanels(s) == 6
    assert [(lambda r: r and (r[0], s["series"][r[1]]["label"]))(figdraw.series_ref(s, i))
            for i in range(6)] == before
    again = json.loads(json.dumps(s))
    assert fg.th_to_cards(again) == s
    s["series"].append(dict(label="dup", runs=[0], panel=0))  # (first card per panel)
    assert figdraw.series_ref(s, 0) == (0, 0)
    s["series"].append(dict(label="bad", runs=[7], panel=3))  # (not one of the runs)
    assert figdraw.series_ref(s, 3) is None
    line = dict(s, kind="line")
    assert fg.th_to_cards(json.loads(json.dumps(line))) == line  # (not time-height)
    t = fg.template(s, "t")
    assert [(e["label"], e["runs"]) for e in t["series"]] == [("w", [0]), ("dup", [0])]


def test_parts_share_sections_and_keep_the_cards():
    """A plan-view part's sections changed: the section part's cards take the new
    sections but keep their runs, times and panels (one more: a new panel); the
    section part's cards go to the plan part as they are."""
    from cm1view.figures import spec as fg
    from cm1view.figures.combo import share_sections
    xs = _xsec_grid_v1()
    fg.to_cards(xs)
    plan = dict(_xsec_grid_v1(), kind="plan",
                sections=[fg.section_defaults(orient="angle", pos="fixed", angle=45.0)]
                + [fg.card_section(c) for c in xs["sections"][1:]]
                + [fg.section_defaults(orient="ab", pos="fixed", a=[0, 0], b=[1, 1])])
    share_sections([plan, xs], plan)
    assert [(c["orient"], c["run"], c["time_s"], c["panel"]) for c in xs["sections"]] == \
        [("angle", 0, 600.0, 0), ("y", 0, 600.0, 1), ("x", 1, 600.0, 2),
         ("y", 1, 900.0, 3), ("ab", 1, 900.0, 4)]
    xs["sections"][0]["half"] = 4.0
    share_sections([plan, xs], xs)
    assert plan["sections"] == xs["sections"]


# ------------------------------------------------------------------ series time zero
def test_each_series_has_its_own_time_zero():
    """Run B's series shifted by its card's time zero (30 min) lines up with run A's,
    in time series and time-height panels; the figure's time zero adds to both."""
    from types import SimpleNamespace
    import xarray as xr
    from cm1view.figures import spec as fg
    times = np.arange(0.0, 5401.0, 600.0)  # 0-90 min
    nt = times.size
    run = SimpleNamespace(times=times)
    ds = xr.Dataset(dict(value=("time", np.arange(nt, dtype=float)),
                         computed=("time", np.ones(nt, np.int8)),
                         profile=(("time", "z"), np.ones((nt, 2)))), coords=dict(z=[1.0, 2.0]))
    a = dict(recipe=dict(z0=0.0, z1=3.0), op="", panel=0, runs=[0], label="w")
    b = dict(a, runs=[1], t0_min=30.0)
    spec = dict(kind="line", series=[a, b], ts={}, runs=[dict(label="A"), dict(label="B")])
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert d["S0_t"][0] == 0.0 and d["S1_t"][0] == -30.0 and d["S1_t"][3] == 0.0
    spec["time_label"] = dict(t0_min=10.0)
    assert fg.line_panel(spec, 0, lambda k, e: (run, ds))["S1_t"][0] == -40.0
    assert fg.th_panel(run, ds, b, spec)["x"][0] == -40.0
    assert fg.th_panel(run, ds, a, spec)["x"][0] == -10.0
    # the legend: a series' own label; a series of several runs adds each run's folder
    assert [d["S0_label"], d["S1_label"]] == ["w", "w"]
    spec["runs"] = [dict(label="A", path="/x/run_a"), dict(label="B", path="/x/run_b/")]
    spec["series"] = [dict(a, runs=None)]
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert [d["S0_label"], d["S1_label"]] == ["w · run_a", "w · run_b"]


def test_a_run_time_zero_shifts_its_lines():
    """A run's time zero moves that run's lines and time-height panels, on top of the
    figure's and the card's; hand edits stay at their model time, your own data has no
    run, and an ensemble band of the runs lines up."""
    from types import SimpleNamespace
    import xarray as xr
    from cm1view.figures import spec as fg
    times = np.arange(0.0, 5401.0, 600.0)  # 0-90 min
    nt = times.size
    run = SimpleNamespace(times=times)
    ds = xr.Dataset(dict(value=("time", np.arange(nt, dtype=float)),
                         computed=("time", np.ones(nt, np.int8)),
                         profile=(("time", "z"), np.ones((nt, 2)))), coords=dict(z=[1.0, 2.0]))
    a = dict(recipe=dict(z0=0.0, z1=3.0), op="", panel=0, runs=None, label="w", t0_min=1.0)
    obs = dict(source="table", table=dict(t=[0.0, 5.0], v=[1.0, 2.0]), panel=0, label="obs")
    spec = dict(kind="line", series=[a, obs], ts={}, time_label=dict(t0_min=10.0),
                runs=[dict(path="a"), dict(path="b", t0_min=30.0)])
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert d["S0_t"][0] == -11.0 and d["S1_t"][0] == -41.0  # (figure + run + card)
    assert d["S2_label"] == "obs" and d["S2_t"][0] == -10.0  # (figure + its card: no run)
    assert d["xlim"] == (-41.0, 79.0)
    assert fg.th_panel(run, ds, a, spec, 1)["x"][0] == -41.0
    assert fg.th_panel(run, ds, a, spec, 0)["x"][0] == -11.0
    assert fg.th_panel(run, ds, a, spec)["x"][0] == -11.0  # (no run: none of a run's)
    # a hand edit stays at its model time, wherever the time zero puts it
    e = dict(a, runs=[1], edits={"1": {fg.edit_key(600.0): -5.0}})
    d = fg.line_panel(dict(spec, series=[e]), 0, lambda k, e: (run, ds))
    assert d["S0_v"][1] == -5.0 and d["S0_t"][1] == -31.0
    # an ensemble of the runs: on their shifted times (two runs where both have values)
    b = dict(a, ens="minmax", ens_mid="mean", t0_min=0.0)
    spec = dict(spec, series=[b], time_label={})
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    j = next(j for j in range(d["nlines"]) if f"S{j}_ens" in d)
    assert d[f"S{j}_t"][0] == 0.0 and d[f"S{j}_t"][-1] == 60.0
    # no time zero: as before
    for r in spec["runs"]:
        r.pop("t0_min", None)
    assert fg.line_panel(spec, 0, lambda k, e: (run, ds))["S0_t"][0] == 0.0


# ------------------------------------------------------------------ series data by hand
def _line_setup():
    from types import SimpleNamespace
    import xarray as xr
    times = np.arange(0.0, 3001.0, 600.0)  # 0-50 min
    nt = times.size
    run = SimpleNamespace(times=times)
    ds = xr.Dataset(dict(value=("time", np.arange(nt, dtype=float)),
                         computed=("time", np.ones(nt, np.int8))))
    a = dict(recipe=dict(), op="", panel=0, runs=[0], label="w")
    spec = dict(kind="line", series=[a], ts={}, runs=[dict(label="A"), dict(label="B")])
    return run, ds, a, spec


def test_hand_edits_change_and_blank_a_series():
    """A series' hand edits (by model time, s) replace or blank its values for that run
    only; an edit at a time the run lacks is left out; the legend says "(edited)"
    unless Style turns it off."""
    from cm1view.figures import spec as fg
    run, ds, a, spec = _line_setup()
    a["edits"] = {"0": {fg.edit_key(1200.0): 9.5, fg.edit_key(1800.0): None,
                        fg.edit_key(99999.0): 1.0}}
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert d["S0_v"][2] == 9.5 and np.isnan(d["S0_v"][3]) and d["S0_v"][4] == 4.0
    assert d["S0_label"] == "w (edited)"
    spec["ts"]["mark_edited"] = False
    assert fg.line_panel(spec, 0, lambda k, e: (run, ds))["S0_label"] == "w"
    a["runs"] = [1]  # (the edits are run 0's: run 1 drawn as computed)
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert list(d["S0_v"]) == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    v, used, gone = fg.apply_edits(np.zeros(6), run.times, dict(a, edits={"1": {
        fg.edit_key(600.0): 2.0, fg.edit_key(7.0): 3.0}}), 1)
    assert (used, gone) == (1, 1) and v[1] == 2.0


def test_hand_edits_feed_the_ensemble_band():
    """An ensemble band is made from the members as edited, and says "(edited)"."""
    from cm1view.figures import spec as fg
    run, ds, a, spec = _line_setup()
    a.update(runs=None, ens="minmax", ens_members="hidden",
             edits={"1": {fg.edit_key(0.0): 10.0}})
    d = fg.line_panel(spec, 0, lambda k, e: (run, ds))
    assert d["nlines"] == 1 and "S0_ens" in d
    assert d["S0_hi"][0] == 10.0 and d["S0_lo"][0] == 0.0
    assert d["S0_label"].endswith(" (edited)")


def test_a_series_of_your_own_data_draws_without_a_run():
    """A series of your own (source "table"): its points in time order, shifted by the
    time zero, beside a computed series; nothing asked of any run."""
    from cm1view.figures import spec as fg
    run, ds, a, spec = _line_setup()
    obs = dict(recipe=dict(), op="", panel=0, source="table", label="obs", ls="--",
               color="k", table=dict(t=[20.0, 0.0, 10.0, None], v=[3.0, 1.0, None, 7.0]))
    spec["series"].append(obs)
    asked = []
    d = fg.line_panel(spec, 0, lambda k, e: asked.append((k, e)) or (run, ds))
    assert asked == [(0, 0)] and d["nlines"] == 2
    assert d["S1_label"] == "obs" and d["S1_r"] == -1
    assert list(d["S1_t"]) == [0.0, 10.0, 20.0] and np.isnan(d["S1_v"][1])
    assert fg.series_pairs(spec) == [(0, 0)]
    spec["time_label"] = dict(t0_min=5.0)
    assert fg.line_panel(spec, 0, lambda k, e: (run, ds))["S1_t"][0] == -5.0
    spec["series"] = [obs]  # (alone, with no data at all: why)
    obs["table"] = dict(t=[0.0], v=[None])
    assert fg.line_panel(spec, 0, lambda k, e: None)["missing"] == "no values in your data"


def test_parse_your_own_data():
    """Pasted text: commas, tabs, semicolons or spaces; a header (its second column
    with units in brackets); # comments; blank / nan values gaps; errors with their line;
    table_text reads back the same."""
    from cm1view.figures import spec as fg
    tab, notes = fg.parse_table("# obs\ntime, rain (mm)\n0,1\n5,2\n10, nan\n7,3,9\n")
    assert tab == dict(t=[0.0, 5.0, 10.0, 7.0], v=[1.0, 2.0, None, 3.0],
                       names=["time", "rain (mm)"])
    assert len(notes) == 2  # (a third column; times out of order)
    assert fg.parse_table(fg.table_text(tab))[0] == tab
    assert fg.parse_table("0\t1\n5\t\n")[0] == dict(t=[0.0, 5.0], v=[1.0, None])
    assert fg.parse_table("t  v\n 0 1\n5   2\n")[0]["v"] == [1.0, 2.0]
    for bad, why in [("", "no data"), ("0,1\nx,2", "line 2"), ("5", "line 1"),
                     ("a,b\nc,d", "line 2"), ("\n".join(f"{j},1" for j in range(10001)),
                                              "more than")]:
        with pytest.raises(ValueError, match=why):
            fg.parse_table(bad)


# ------------------------------------------------------------------ panel letters


# ------------------------------------------------------------------ 3D scenes


def test_an_older_scene_with_a_grid_draws_one_picture():
    from cm1view.figures import draw as figdraw
    s = dict(version=1, kind="scene", rows=2, cols=3, run=0, time_s=600.0, layers=[],
             size=[4.0, 3.0], runs=[dict(path="a")])
    v2, _ = figdraw.upgrade(s)
    assert [(b["rows"], b["cols"]) for b in v2["blocks"]] == [(1, 1)]
    assert [p["cell"] for p in v2["panels"]] == [[0, 0, 1, 1]]


# ------------------------------------------------------------------ figure parts' note


# ---------------------------------------------------------------- B3: parts, label defaults


