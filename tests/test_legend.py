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
    assert axs[0].get_legend() is not None  # (not gathered: left as it was)


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
