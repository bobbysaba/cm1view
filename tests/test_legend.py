"""Legends: a block's legend on a panel or on the figure, and each panel's own."""
import pytest
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from conftest import render


def _axes(n=2):
    fig = Figure(figsize=(6, 3), layout="constrained")
    axs = list(fig.subplots(1, n, squeeze=False).ravel())
    placed = [(dict(id=i), ax, {}) for i, ax in enumerate(axs)]
    return fig, axs, placed


def _own_legend(ax, text="mean", color="C0"):
    """What a panel's draw leaves: its legend and the entries for a figure legend."""
    h = Line2D([], [], color=color)
    ax.legend([h], [text])
    ax._cv_entries = [(h, text)]


def _legends(fig, placed, entries, **lg):
    from cm1view.figures.draw.figure import _legends
    _legends(fig, dict(legend=lg), placed, entries)


def test_figure_legend_gathers_panels_and_lists_shared_entries_once():
    fig, axs, placed = _axes(3)
    for ax in axs[:2]:
        _own_legend(ax)  # the same entry in two panels
    _own_legend(axs[2], "other", "C1")
    _legends(fig, placed, {}, where="figure", loc="outside lower center", ncol=2, title="Key")
    assert len(fig.legends) == 1 and all(ax.get_legend() is None for ax in axs)
    leg = fig.legends[0]
    assert [t.get_text() for t in leg.get_texts()] == ["mean", "other"]
    assert leg.get_title().get_text() == "Key" and leg._ncols == 2


def test_figure_legend_lists_the_same_text_in_another_colour_again():
    fig, axs, placed = _axes(2)
    _own_legend(axs[0], "mean", "C0")
    _own_legend(axs[1], "mean", "C1")
    _legends(fig, placed, {}, where="figure")
    assert len(fig.legends[0].get_texts()) == 2


def test_figure_legend_takes_only_the_panels_asked_for():
    fig, axs, placed = _axes(2)
    _own_legend(axs[0], "a")
    _own_legend(axs[1], "b")
    _legends(fig, placed, {}, where="figure", panels=[1])
    assert [t.get_text() for t in fig.legends[0].get_texts()] == ["b"]
    assert all(ax.get_legend() is None for ax in axs)  # (not gathered: still turned off)


def test_panel_legend_lists_layers_and_leaves_panels_own_alone():
    fig, axs, placed = _axes(2)
    _own_legend(axs[0])
    _legends(fig, placed, {}, where="panel", panel=1)  # (no layer entries: nothing to add)
    assert axs[1].get_legend() is None and axs[0].get_legend() is not None
    _legends(fig, placed, {0: {"w": Line2D([], [], color="k")}}, where="panel", panel=1)
    assert [t.get_text() for t in axs[1].get_legend().get_texts()] == ["w"]
    assert not fig.legends


def test_outside_place_on_a_panel_falls_back():
    fig, axs, placed = _axes(1)
    _legends(fig, placed, {0: {"w": Line2D([], [], color="k")}}, where="panel",
             loc="outside lower center")
    assert axs[0].get_legend() is not None


def test_legend_settings_round_trip(ed):
    ed.lg_where.value = "figure"
    assert ed.lg_from.visible and not ed.lg_panel.visible
    ed.lg_loc.value = "outside right center"
    ed.lg_from.value = "1, 2"
    ed.lg_title.value = " Layers "
    ed.lg_ncol.value = 2
    lg = ed.collect()["legend"]
    assert (lg["where"], lg["loc"], lg["panels"], lg["title"], lg["ncol"]) == \
        ("figure", "outside right center", [0, 1], "Layers", 2)
    ed.ts_legncol.value, ed.ts_legframe.value = 3, True
    ts = ed.collect()["ts"]
    assert ts["legend_ncol"] == 3 and ts["legend_frame"] is True
    ed.lg_where.value = "panel"
    assert ed.lg_panel.visible and "outside right center" not in ed.lg_loc.options


def test_figure_legend_draws_from_the_editor(ed):
    cont = next(c for c in ed.cards if c.type == "contour")
    cont.w["legend"].value = "w"
    ed.lg_where.value = "figure"
    ed.lg_loc.value = "outside lower center"
    spec, data, fig = render(ed)
    assert len(fig.legends) == 1
    assert [t.get_text() for t in fig.legends[0].get_texts()] == ["w"]
    assert all(ax.get_legend() is None for ax in fig.axes)


def test_figure_legend_gathers_the_axes_beside_a_panel():
    """A skew-T beside its hodograph: the hodograph's key joins the figure legend."""
    fig, axs, placed = _axes(2)
    _own_legend(axs[0], "T")
    axs[0]._cv_more = [axs[1]]
    _own_legend(axs[1], "0–1 km", "C2")
    _legends(fig, placed[:1], {}, where="figure")
    assert [t.get_text() for t in fig.legends[0].get_texts()] == ["T", "0–1 km"]
    assert all(ax.get_legend() is None for ax in axs)


def test_panel_legend_opts_and_their_merge():
    from cm1view.figures.draw import legend_opts, panel_view
    assert legend_opts("plan", {"on": True}) == {} and legend_opts("line", {}) == {}
    assert legend_opts("line", {"ncol": 2, "frame": True}) == \
        {"ts": {"legend_ncol": 2, "legend_frame": True}}
    o = legend_opts("sounding", {"on": False, "loc": "lower left"})["skewt"]
    assert o["legend"] is False and o["hodo_key"] is False and o["legend_off"] is True
    assert o["legend_loc"] == o["hodo_key_loc"] == "lower left"
    spec = dict(version=2, blocks=[{}], skewt=dict(layout="hodo", storm="lm"), panels=[])
    p = dict(kind="sounding", block=0, opts=legend_opts("sounding", {"ncol": 3}))
    sk = panel_view(spec, p)["skewt"]
    assert sk["storm"] == "lm" and sk["hodo_key_ncol"] == 3  # (merged, not replaced)


def test_panel_edit_legend_reaches_that_panel_alone():
    from cm1view.figures.draw import upgrade
    v1 = dict(kind="line", rows=1, cols=2, size=[6, 3], ts=dict(legend_ncol=1),
              series=[dict(panel=0), dict(panel=1)], edits={"1": {"legend": {"ncol": 2}}})
    v2, _ = upgrade(v1)
    assert not v2["panels"][0].get("opts")
    assert v2["panels"][1]["opts"] == {"ts": {"legend_ncol": 2}}



def test_panel_edit_axis_labels_reach_that_panel_alone():
    from cm1view.figures.draw import upgrade, panel_view
    v1 = dict(kind="line", rows=1, cols=2, size=[6, 3], axes=dict(xlabel="t", ylabel=""),
              series=[dict(panel=0), dict(panel=1)],
              edits={"1": {"xlabel": "time (min)", "ylabel": " ",
                           "legend": {"ncol": 2}}})
    v2, _ = upgrade(v1)
    assert not v2["panels"][0].get("opts")
    assert v2["panels"][1]["opts"]["axes"] == {"xlabel": "time (min)", "ylabel": " "}
    ax = panel_view(v2, v2["panels"][1])["axes"]
    assert (ax["xlabel"], ax["ylabel"]) == ("time (min)", " ")

def test_hodograph_key_settings_round_trip(ed):
    ed.sk["layout"].value = "hodo"
    assert ed.sk["hodo_key_loc"].visible
    ed.sk["hodo_key_loc"].value, ed.sk["hodo_key_ncol"].value = "lower left", 3
    ed.sk["hodo_key_frame"].value = True
    sk = ed.collect()["skewt"]
    assert (sk["hodo_key_loc"], sk["hodo_key_ncol"], sk["hodo_key_frame"]) == \
        ("lower left", 3, True)
    ed.sk["hodo_key"].value = False
    assert not ed.sk["hodo_key_loc"].visible


def _keeping(placed, i):
    """Panel i's Tree legend set to Yes: it keeps its own legend."""
    from cm1view.figures.draw import legend_opts
    p, ax, _ = placed[i]
    placed[i] = (dict(p, kind="line"), ax, legend_opts("line", {"on": True}))


def test_figure_legend_leaves_a_panel_that_keeps_its_own():
    fig, axs, placed = _axes(3)
    for i, ax in enumerate(axs):
        _own_legend(ax, f"e{i}", f"C{i}")
    _keeping(placed, 1)
    _legends(fig, placed, {}, where="figure")
    assert [t.get_text() for t in fig.legends[0].get_texts()] == ["e0", "e2"]
    assert [ax.get_legend() is not None for ax in axs] == [False, True, False]


def test_panels_own_legends_off_but_the_kept_one():
    fig, axs, placed = _axes(3)
    for ax in axs:
        _own_legend(ax)
    _keeping(placed, 2)
    _legends(fig, placed, {}, where="panel", own=False)
    assert [ax.get_legend() is not None for ax in axs] == [False, False, True]


def test_legend_anchor_puts_its_corner_at_the_point():
    fig, axs, placed = _axes(2)
    _own_legend(axs[0])
    _legends(fig, placed, {}, where="figure", loc="outside right upper", anchor=[0.5, 0.25])
    leg = fig.legends[0]
    assert leg._loc == 2  # ("upper left": "outside" dropped with an anchor)
    box = leg.get_bbox_to_anchor().transformed(fig.transFigure.inverted())
    assert (round(box.x0, 6), round(box.y0, 6)) == (0.5, 0.25)


def test_panel_legend_anchor():
    from cm1view.figures.draw.base import panel_legend
    fig, axs, _ = _axes(1)
    leg = panel_legend(axs[0], [Line2D([], [])], dict(legend_loc="upper left",
                                                      legend_anchor=[1.02, 1.0]), {}, "best",
                       False)
    box = leg.get_bbox_to_anchor().transformed(axs[0].transAxes.inverted())
    assert (round(box.x0, 6), round(box.y0, 6)) == (1.02, 1.0)


def test_anchor_text_round_trip():
    from cm1view.figures.cards import _xy, _xy_text
    assert _xy("1.02, -0.1") == [1.02, -0.1] and _xy("1") is None and _xy("") is None
    assert _xy_text([1.02, 1.0]) == "1.02, 1" and _xy_text(None) == ""


def test_style_legend_anchor_and_own_round_trip(ed):
    ed.lg_anchor.value, ed.lg_own.value = "1.02, 1", False
    lg = ed.collect()["legend"]
    assert lg["anchor"] == [1.02, 1.0] and lg["own"] is False
