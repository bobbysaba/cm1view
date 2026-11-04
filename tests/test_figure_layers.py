"""Figure layers: distributions, vertical profiles, joint distributions, azimuthal means
and the Sector layer, differences,
time windows / swaths, style presets and copying a layer's look."""
import json

import numpy as np
import pytest

from conftest import difference_layer, edited_v1, new_spec, render, swath_layer


# ------------------------------------------------------------------ distributions


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


# ------------------------------------------------------------------ vertical profiles


# ------------------------------------------------------------------ joint distributions


# ------------------------------------------------------------------ azimuthal means


def test_difference_layer(ed):
    spec = difference_layer(ed, new_spec(ed))
    lay = next(x for x in spec["layers"] if x.get("minus"))
    spec, data, fig = render(ed, spec)
    j = next(j for j, x in enumerate(spec["layers"]) if x.get("minus"))
    t0 = lay["minus"]["time_s"]
    for d in data.values():  # (a panel at the subtracted time: zero)
        if abs(d["time_s"] - t0) < 1:
            assert np.nanmax(np.abs(d[f"L{j}"])) == 0.0
    assert any(np.nanmax(np.abs(d[f"L{j}"])) > 0 for d in data.values())
    assert any("difference" in a.get_ylabel() + a.get_xlabel() for a in fig.axes)


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
    base = new_spec(ed)
    spec, data, fig = render(ed, swath_layer(ed, json.loads(json.dumps(base))))
    j = next(j for j, x in enumerate(spec["layers"]) if x.get("reduce"))
    assert any("max" in a.get_ylabel() + a.get_xlabel() for a in fig.axes)
    _, plain, _ = render(ed, base)
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


# ------------------------------------------------------------------ patterns, barbs, strips
def test_shading_hatches_or_stipples():
    from matplotlib.figure import Figure
    from cm1view.figures.draw.layers import _shade
    x = np.linspace(-5.0, 5.0, 11)
    a = np.tile(np.linspace(0.0, 20.0, 11), (11, 1))
    ax = Figure().subplots()
    _shade(ax, x, x, a, dict(threshold=10.0, hatch="..", color="#ff0000", alpha=1.0))
    cs = ax.collections[-1]  # (a contour set's hatches are its own, applied as it draws)
    assert cs.hatches == [".."] and cs.get_facecolor()[0][3] == 0.0  # (no fill, not black)
    _shade(ax, x, x, a, dict(threshold=10.0, color="#ff0000"))  # solid, as before
    assert all(h is None for h in ax.collections[-1].hatches)


def test_vectors_as_barbs_in_knots():
    from matplotlib.figure import Figure
    from matplotlib.quiver import Barbs, Quiver
    from cm1view.figures.draw.layers import _vectors
    d = dict(L0_x=np.array([0.0, 1.0]), L0_y=np.array([0.0, 1.0]),
             L0_u=np.array([10.0, 0.0]), L0_v=np.array([0.0, 5.0]))
    ax = Figure().subplots()
    _vectors(ax, d, 0, dict(style="barbs", vector="wind"), False)
    b = ax.collections[-1]
    assert isinstance(b, Barbs) and np.allclose(b.u, [19.43844, 0.0])
    _vectors(ax, d, 0, dict(style="barbs", vector="wind", barb_units="ms"), False)
    assert np.allclose(ax.collections[-1].u, [10.0, 0.0])
    _vectors(ax, d, 0, dict(style="barbs", vector="wind"), True)  # a section: arrows
    assert isinstance(ax.collections[-1], Quiver)


def test_strip_averaged_section():
    from types import SimpleNamespace
    from cm1view.figures.spec.arrays import _strip
    run = SimpleNamespace(dx=1000.0, dy=1000.0, z=np.array([0.5, 1.5]))
    vol = np.broadcast_to((np.arange(11.0) ** 2)[None, :, None], (2, 11, 11)).copy()
    fi, fj, zq = np.arange(2.0, 9.0), np.full(7, 5.0), np.array([0.5, 1.0])
    line = _strip(run, vol, fi, fj, zq, (0.0, 1.0), 0.0)  # along x, at y index 5
    assert np.allclose(line, 25.0)
    strip = _strip(run, vol, fi, fj, zq, (0.0, 1.0), 4.0)  # y index 3..7
    assert np.allclose(strip, (9 + 16 + 25 + 36 + 49) / 5.0)


def test_reopening_notes_a_changed_namelist(tmp_path):
    from cm1view.figures import spec as fg
    (tmp_path / "namelist.input").write_text("&param1\n dx = 250.0\n/\n")
    spec = dict(runs=[dict(path=str(tmp_path), label="a")])
    spec["made_with"] = fg.made_with(spec)
    assert fg.changed_runs(spec) == []
    (tmp_path / "namelist.input").write_text("&param1\n dx = 500.0\n/\n")
    assert fg.changed_runs(spec) == [str(tmp_path)]


def test_ensemble_statistics_and_band():
    from cm1view.figures import spec as fg
    from cm1view.figures.draw import ens_label
    x, y = np.arange(4.0), np.arange(3.0)
    a, b = np.ones((3, 4)), 3 * np.ones((3, 4))
    b[0, 0] = np.nan
    d = dict(x=x, y=y, L0=a)
    dds = [dict(x=x, y=y, L0=a), dict(x=x, y=y, L0=b), dict(missing="no output")]
    want = dict(mean=2.0, median=2.0, sd=1.0, min=1.0, max=3.0, range=2.0, prob=50.0)
    for st, v in want.items():
        r = fg.ensemble(d, dds, 0, dict(stat=st, threshold=2.0))
        assert r["L0_ens"] == 2 and r["L0"][1, 1] == v
        assert r["L0"][0, 0] == (0.0 if st in ("sd", "range") else 1.0 if st != "prob"
                                 else 0.0)  # (one member there)
    assert fg.ensemble(d, dds, 0, dict(stat="prob", threshold=2.0, above=False))["L0"][1, 1] \
        == 50.0
    moved = dict(x=x + 0.5, y=y, L0=a)
    assert "choose" in fg.ensemble(d, [moved], 0, {})["missing"]
    r = fg.ensemble(d, [moved], 0, dict(grid="interp"))
    assert np.isnan(r["L0"][0, 0]) and r["L0"][0, 1] == 1.0
    assert "no run" in fg.ensemble(d, [dict(missing="x")], 0, {})["missing"]
    assert ens_label(dict(stat="prob", threshold=30.0), "m/s") == "probability > 30 m/s (%)"
    assert ens_label(dict(stat="sd"), "K") == "ensemble spread (sd) (K)"
    spec = dict(kind="plan", runs=[{}, {}, {}], panels=[dict(run=1, time_s=60.0)],
                vary="custom", rows=1, cols=1)
    assert fg.ens_refs(spec, 0, dict(ens=dict(runs=[2, 0, 7]))) == [(2, 60.0), (0, 60.0)]
    assert fg.ens_refs(spec, 0, dict(ens={}, time_s=30.0)) == [(0, 30.0), (1, 30.0),
                                                               (2, 30.0)]
    t = np.arange(10.0)
    T, c, lo, hi = fg.ensemble_band([(t, t), (t[2:], 2 * t[2:])], "minmax", "mean")
    assert T[0] == 2.0 and c[0] == 3.0 and (lo[0], hi[0]) == (2.0, 4.0)
    T, c, lo, hi = fg.ensemble_band([(t, t), (t, 3 * t)], "sd", "")
    assert np.isnan(c).all() and np.allclose(hi - lo, 2 * t)
    assert fg.ensemble_band([(t, t)]) is None


# ------------------------------------------------------------------ tables


def test_table_differences():
    from cm1view.figures import draw as figdraw
    d = dict(nq=1, row_k=np.array([0, 0, 1, 1]), row_min=np.array([30.0, 60.0, 30.0, 60.0]),
             row_run=np.array(["A", "A", "B", "B"]), Q0_v=np.array([10.0, 12.0, 15.0, 9.0]),
             Q0_name="x", Q0_units="", Q0_src="", Q0_dec=0, Q0_e=0)
    _, rows, _ = figdraw.tbl_grid(d, dict(layout="rows", compare="run"))
    assert rows == [("A · 30 min", ["10"]), ("A · 60 min", ["12"]),
                    ("B − A · 30 min", ["+5"]), ("B − A · 60 min", ["−3"])]
    _, rows, _ = figdraw.tbl_grid(d, dict(layout="rows", compare="time"))
    assert [r[1][0] for r in rows] == ["10", "+2", "15", "−6"]
    assert rows[1][0] == "A · 60 − 30 min"
    # (nothing to differ from: the values)
    one = dict(d, row_k=np.array([0, 0]), row_min=np.array([30.0, 60.0]),
               row_run=np.array(["A", "A"]), Q0_v=np.array([1.0, 2.0]))
    _, rows, _ = figdraw.tbl_grid(one, dict(compare="run"))
    assert rows == [("30 min", ["1"]), ("60 min", ["2"])]


def test_table_times_box():
    from cm1view.figures import spec as fg
    outs = [0.0, 1800.0, 3600.0, 5400.0, 7200.0]
    assert fg.parse_times("30, 60", outs) == ([1800.0, 3600.0], [])
    assert fg.parse_times("30-90/30", outs) == ([1800.0, 3600.0, 5400.0], [])
    assert fg.parse_times("30-90", outs) == ([1800.0, 3600.0, 5400.0], [])
    assert fg.parse_times("31 x", outs) == ([1800.0], ["x"])
    assert fg.parse_times("", outs) == ([], [])
    assert fg.times_text([1800.0, 5400.0]) == "30, 90"


