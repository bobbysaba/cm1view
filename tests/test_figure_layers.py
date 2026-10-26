"""Figure layers: distributions, differences, time windows / swaths, style presets and
copying a layer's look."""
import numpy as np
import pytest

from conftest import txt, wait, render, difference_layer, swath_layer, edited_v1


# ------------------------------------------------------------------ distributions
@pytest.mark.parametrize("plot", ["hist", "box", "violin", "ecdf"])
def test_distribution_figure_draws_each_plot(ed, plot):
    from cm1view.figures import spec as fg
    ed.from_dists()  # (no distributions on the map: w over the domain)
    assert ed.kind.value == "dist" and len(ed.dist_cards) == 1
    t1 = float(ed.run.times[4])
    e = fg.dist_defaults(dict(field="winterp", vmode="layer", z0=0.0, z1=5.0,
                              region="domain", lo=0.5), 0, t1)
    ed.dist_cards.append(ed._dist_card(e))
    ed.ds["plot"].value = plot
    ed.ds["stats"].value = ["mean", "sd", "n"]
    spec, data, fig = render(ed)
    d = data[0]
    assert d["ndist"] == 2 and not d.get("missing") and "time_s" not in d  # (two times)
    assert spec["dist"]["plot"] == plot and len(fig.axes) == 1
    ax = fig.axes[0]
    if plot in ("hist", "ecdf"):
        assert ax.get_legend() is not None and "mean" in ax.get_legend().texts[0].get_text()
        assert "(" in ax.get_xlabel()  # the field and its units
    else:
        ticks = [t.get_text() for t in ax.get_xticklabels()]
        assert len(ticks) == 2 and ticks[1].startswith(str(d["D1_label"]))
        assert "mean" in ticks[0] and "(" in ax.get_ylabel()
    assert ed.dist_cache  # (restyling reads nothing again)
    n = len(ed.dist_cache)
    ed.ds["bins"].value, ed.ds["logy"].value = 20, True
    render(ed)
    assert len(ed.dist_cache) == n


def test_distribution_bar_labels_and_statistics_box(ed):
    from matplotlib.offsetbox import AnchoredOffsetbox, AnchoredText
    ed.from_dists()  # one distribution: its statistics still show
    ed.ds["plot"].value, ed.ds["bins"].value = "hist", 10
    ed.ds["bar_labels"].value = "percent"
    ed.ds["stats"].value, ed.ds["stats_at"].value = ["n", "median", "p5_95"], "box"
    assert ed.ds["bar_labels"].visible and ed.ds["stats_loc"].visible
    spec, data, fig = render(ed)
    ax = fig.axes[0]
    pct = [float(t.get_text().rstrip("%")) for t in ax.texts if t.get_text().endswith("%")]
    assert pct and abs(sum(pct) - 100.0) < 5.0  # (every value is in the bins; 2 digits)
    boxes = [a for a in ax.artists  # (not the panel labels)
             if isinstance(a, AnchoredOffsetbox) and not isinstance(a, AnchoredText)]
    assert len(boxes) == 1 and ax.get_legend() is None
    ed.ds["stats_at"].value = "legend"  # one distribution: a legend for its statistics
    assert not ed.ds["stats_loc"].visible
    spec, data, fig = render(ed)
    assert "median" in fig.axes[0].get_legend().texts[0].get_text()
    ed.ds["plot"].value = "box"
    assert not ed.ds["bar_labels"].visible


def test_old_distribution_stats_flag(ed):
    ed.from_dists()
    s = ed.collect()
    s["dist"]["stats"] = True  # (a spec saved before the statistics list)
    ed.set_spec(s)
    assert ed.ds["stats"].value == ["mean", "sd", "n"]


def test_distribution_figure_of_the_maps(ed, viewer):
    v = viewer
    v.dist_field.value, v.dist_vmode.value = "winterp", "all"
    v._dist_request()
    wait(lambda: len(v.dists) == 1, msg="the distribution")
    v.dist_kind.value, v.dist_norm.value = "violin", "pdf"
    v._on_dist_figure(None)
    assert v.workspace.value == "Figure" and ed.kind.value == "dist"
    s = ed.collect()
    assert s["dist"]["plot"] == "violin" and s["dists"][0]["recipe"]["vmode"] == "all"
    assert s["dists"][0]["time_s"] == float(ed.run.times[v.t])
    spec, data, fig = render(ed)
    st = next(iter(v.dists.values()))["st"]
    assert data[0]["D0_s"][0] == st["n"]  # (the same values as the map's)


def test_distribution_spec_upgrades_to_panels(ed):
    from cm1view.figures import draw as figdraw, spec as fg
    ed.from_dists()
    e = dict(ed.dist_cards[0].collect(), panel=1)
    ed.dist_cards.append(ed._dist_card(e))
    ed._fit_grid(reset=True)
    s = ed.collect()
    assert fg.npanels(s) == 2
    data = ed.panel_data(s)
    v2, d2 = figdraw.upgrade(s, data)
    assert [p["kind"] for p in v2["panels"]] == ["dist", "dist"]
    assert [[lay["type"] for lay in p["layers"]] for p in v2["panels"]] == [["dist"], ["dist"]]
    assert int(d2[1]["D0_e"]) == 0  # (counted within its panel)
    figdraw.draw(s, data)
    ed._tree_sync(force=True)
    assert ed.tree_list.objects[0].name.startswith("a  Distribution")


def test_difference_layer(ed):
    c = difference_layer(ed)
    lay = c.collect()
    assert lay["minus"] == dict(run=None, time_s=lay["minus"]["time_s"], grid="ask")
    assert (lay["cmap"], lay["reverse"], lay["mask_below"]) == ("RdBu", True, None)
    assert lay["vmin"] == -lay["vmax"] < 0  # (centred on 0)
    spec, data, fig = render(ed)
    j = next(j for j, x in enumerate(spec["layers"]) if x.get("minus"))
    t0 = lay["minus"]["time_s"]
    for d in data.values():  # (a panel at the subtracted time: zero)
        if abs(d["time_s"] - t0) < 1:
            assert np.nanmax(np.abs(d[f"L{j}"])) == 0.0
    assert any(np.nanmax(np.abs(d[f"L{j}"])) > 0 for d in data.values())
    assert any("difference" in a.get_ylabel() + a.get_xlabel() for a in fig.axes)
    c.w["minus_on"].value = False
    assert "minus" not in c.collect() and c.collect()["cmap"] != "RdBu"


def test_difference_of_different_grids():
    from cm1view.figures import spec as fg
    x, y = np.arange(4.0), np.arange(3.0)
    a, b = np.ones((3, 4)), np.add.outer(y, x)
    d = fg.subtract(dict(x=x, y=y, L0=a), dict(x=x, y=y, L0=b), 0)
    assert np.array_equal(d["L0"], a - b)
    moved = dict(x=x + 0.5, y=y, L0=b)
    assert "choose" in fg.subtract(dict(x=x, y=y, L0=a), moved, 0)["missing"]
    assert "choose" not in fg.subtract(dict(x=x, y=y, L0=a), moved, 0, "refuse")["missing"]
    d = fg.subtract(dict(x=x, y=y, L0=a), moved, 0, "interp")
    assert np.isnan(d["L0"][0, 0]) and d["L0"][1, 1] == 1.0 - 1.5
    assert fg.subtract(dict(x=x, y=y, L0=a), dict(missing="no output"), 0)["missing"] == \
        "difference: no output"
    v1 = edited_v1()
    lay = dict(fg.figdraw.spec_layers(v1, 1)[0], minus=dict(run=1, time_s=None))
    assert fg.minus_ref(v1, 1, lay) == (1, 60.0)  # (the layer's own time)
    assert fg.minus_ref(v1, 0, dict(type="fill", minus=dict(time_s=30.0))) == (0, 30.0)
    v2, _ = fg.figdraw.upgrade(dict(v1, layers=[dict(v1["layers"][0], minus=dict(run=1))]))
    assert v2["panels"][0]["layers"][0]["minus"] == dict(run=1)


def test_time_window_layer(ed):
    from cm1view.core import swath
    c = swath_layer(ed)
    lay = c.collect()
    assert lay["reduce"] == dict(op="max", t0=lay["reduce"]["t0"], t1=None, every=1)
    assert "max over a time window" in c.title.object
    spec, data, fig = render(ed)
    j = next(j for j, x in enumerate(spec["layers"]) if x.get("reduce"))
    assert any("max" in a.get_ylabel() + a.get_xlabel() for a in fig.axes)
    c.w["reduce_op"].value = ""
    assert "reduce" not in c.collect()
    _, plain, _ = render(ed)
    for i, d in data.items():  # (the window ends at the panel's own output)
        a, b = d[f"L{j}"], plain[i][f"L{j}"]
        ok = np.isfinite(a) & np.isfinite(b)
        assert ok.any() and np.all(a[ok] >= b[ok] - 1e-5)
    assert any(f.endswith(".npz") for f in __import__("os").listdir(swath.cache_dir()))


class _Run:
    """A tiny run on a 1 km grid with three outputs a minute apart."""
    def __init__(self, umove=0.0):
        self.times, self.dx, self.dy, self.files = [0.0, 60.0, 120.0], 1000.0, 1000.0, []
        self.umove, self.vmove, self.path = umove, 0.0, f"fake-{umove}"


class _Fields:
    def __init__(self, col):
        self.col = col  # output t -> the column of the blob

    def __getitem__(self, name):
        from types import SimpleNamespace
        return SimpleNamespace(storm=False)

    def plane(self, name, t, mode, z, storm=None):
        a = np.zeros((3, 8), dtype=np.float32)
        a[:, self.col(t)] = 1.0
        return a


def test_swaths_follow_the_ground_and_composites_the_storm(tmp_path, monkeypatch):
    from cm1view.core import swath
    monkeypatch.setattr(swath, "CACHE_DIR", str(tmp_path))
    lay = dict(field="w", mode="height", z=1.0, reduce=dict(op="max", t0=None, t1=None))
    # the grid moves 1 km a minute: a blob fixed on the ground moves 1 column back
    run = _Run(umove=1000.0 / 60.0)
    a, n = swath.reduce(run, _Fields(lambda t: 5 - t), lay, 2)
    assert n == 3 and np.array_equal(np.flatnonzero(a[0] > 0), [3])
    a2, _ = swath.reduce(run, _Fields(lambda t: 0), lay, 2)  # (from the cache)
    assert np.array_equal(a, a2, equal_nan=True)
    assert swath.window(run, dict(lay["reduce"], every=2), 120.0) == [0, 2]
    assert swath.window(run, dict(lay["reduce"], t0=60.0), 60.0) == [1]
    # a storm moving 1 km a minute with its blob: the composite keeps it in one column
    lay = dict(lay, reduce=dict(op="composite"))
    centers = {t: (float(t), 0.0) for t in range(3)}
    a, n = swath.reduce(_Run(), _Fields(lambda t: 2 + t), lay, 2, centers)
    assert n == 3 and np.array_equal(np.flatnonzero(a[0] > 0), [4]) and a[0, 4] == 1.0
    with pytest.raises(ValueError, match="track"):
        swath.reduce(_Run(), _Fields(lambda t: 0), lay, 2, {})


def test_style_presets_and_matplotlib_styles(ed, tmp_path):
    from cm1view.figures import draw as figdraw
    from cm1view.figures import spec as fg
    ed.set_spec(fg.apply_style(ed.collect(), "ams"))
    s = ed.collect()
    assert (s["font"]["size"], s["letters"]["fmt"], s["export"]["format"]) == \
        (8.0, "({a})", "pdf")
    assert s["size"][0] == (3.2 if s["cols"] == 1 else 6.5) and not s["size_auto"]
    ed.set_spec(fg.apply_style(ed.collect(), "dark"))
    s = ed.collect()
    assert (s["background"], s["mplstyle"], ed.bg.value) == ("black", "dark_background", "black")
    assert figdraw.rc(s)["axes.edgecolor"] == "white" and figdraw.rc(s)["font.size"] == 14.0
    render(ed)
    f = tmp_path / "thick.mplstyle"
    f.write_text("lines.linewidth: 3\nbackend: agg\n")
    rc = figdraw.rc(dict(s, mplstyle=str(f)))
    assert rc["lines.linewidth"] == 3 and "backend" not in rc
    with pytest.raises(ValueError, match="no such style"):
        figdraw.rc(dict(s, mplstyle="no-such-style"))
    ed.set_spec(fg.apply_style(ed.collect(), "default"))
    assert (ed.collect()["mplstyle"], ed.collect()["font"]["size"]) == ("", 10.0)


def test_copy_a_layers_look(ed):
    ed._add_layer("contour")
    src, dst = [c for c in ed.cards if c.type == "contour"][:2]
    other = next(f for f in ed.fields.defs if f != src.w["field"].value)
    dst.w["field"].value = other
    src.w["color"].value, src.w["lw"].value = "#ff0000", 2.0
    levels = dst.collect()["levels"]
    i, j = ed.cards.index(src), ed.cards.index(dst)
    fill = next(k for k, c in enumerate(ed.cards) if c.type == "fill")
    cmap = ed.cards[fill].collect()["cmap"]
    assert set(ed.look_from.options.values()) == set(range(len(ed.cards)))
    ed.look_from.value, ed.look_to.value = i, [j, fill]
    ed._copy_look()
    new = ed.cards[j].collect()
    assert (new["color"], new["lw"], new["field"], new["levels"]) == \
        ("#ff0000", 2.0, other, levels)  # (another field: its levels stay)
    assert "another kind" in txt(ed.msg.object) and ed.cards[fill].collect()["cmap"] == cmap
    render(ed)


# ------------------------------------------------------------------ diverging maps
def test_a_diverging_map_stays_white_at_zero():
    import matplotlib.colors as mc
    from cm1view.core.fields import palette
    from cm1view.figures.draw.base import colormap
    mid = mc.to_rgb(colormap("RdBu")(0.5))
    white = lambda c: np.allclose(mc.to_rgb(c), mid, atol=2 / 255)  # noqa: E731  (a
    # reversed map's middle is the colour next to it: #f7f6f6 or #f6f7f7)
    for rev in (False, True):  # viewer: 0 is a quarter of the way up -2..6
        assert white(palette("RdBu_r", 257, rev, -2.0, 6.0)[64])
        cm = colormap("RdBu", rev, False, -2.0, 6.0)  # figures
        assert white(cm(mc.Normalize(-2.0, 6.0)(0.0)))
        assert mc.to_hex(cm(1.0)) == mc.to_hex(colormap("RdBu", rev)(1.0))  # (6: the full end)
    # no change for a sequential map or a range on one side of 0
    assert palette("viridis", 8, lo=-2.0, hi=6.0) == palette("viridis", 8)
    assert colormap("RdBu", lo=270.0, hi=310.0)(0.0) == colormap("RdBu")(0.0)


# ------------------------------------------------------------------ outer tick labels
def test_outer_labels_each_axis_on_its_own():
    """Outer: a range the panels share loses its inner tick labels, one they don't keeps
    them; the inner axis labels go either way, but a panel's own (different) label."""
    from matplotlib.figure import Figure
    from cm1view.figures.draw.layers import _ticks
    axs = Figure().subplots(1, 3)
    for ax, top in zip(axs, (1, 2, 3)):
        ax.set_xlim(0, 10)
        ax.set_ylim(0, top)  # (y ranges differ)
        ax.set_xlabel("x (km)")
        ax.set_ylabel("PDF")
    axs[2].set_ylabel("count")  # (its own)
    cells = [(ax, c, True, "dist", {}) for c, ax in enumerate(axs)]
    _ticks(cells, list(axs), dict(ticklabels="outer"))
    assert [ax.get_ylabel() for ax in axs] == ["PDF", "", "count"]
    assert all(ax.yaxis.get_tick_params().get("labelleft", True) for ax in axs)
    assert [ax.get_xlabel() for ax in axs] == ["x (km)"] * 3  # (all in the bottom row)
    for ax in axs:
        ax.set_ylim(0, 1)
    _ticks(cells, list(axs), dict(ticklabels="outer"))
    assert [ax.yaxis.get_tick_params().get("labelleft", True) for ax in axs] == \
        [True, False, False]
