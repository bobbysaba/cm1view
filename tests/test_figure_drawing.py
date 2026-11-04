"""What figures draw and save, from the specs and documents they are made of: every kind's plots,
tables, series, animations, the exported script, own code and exact sizes."""
import os
import subprocess
import sys

import numpy as np
import pytest

from cm1view.figures import draw as figdraw, spec as fg
from conftest import (difference_layer, doc_now, new_spec, put, render, settled, swath_layer, txt,
                      wait)

DEMO_WEAK = ("demo", "supercell_weak")


def _script_of(base):
    return fg.bundle_paths({}, base)["script"]


def _tracks_from_files(s, demo_root):
    for e in s["runs"]:
        name = os.path.basename(e["path"].rstrip("/"))
        e["track"] = os.path.join(demo_root, "storm_tracks", f"demo_{name}.csv")
    return s


def _one_line(ed):
    s = new_spec(ed, "line", 1, 1)
    s["series"] = s["series"][:1]
    return s


def test_publication_options_draw(ed):
    s = new_spec(ed, "plan", 1, 2)
    for widget, value in (("font", "serif"), ("math", "custom"), ("fs_tick", 7), ("fs_label", 9),
                          ("fs_title", 11), ("tickdir", "in"), ("xstep", 5.0), ("ystep", 5.0),
                          ("grid", True), ("frame_lw", 1.2), ("minor", True), ("let_box", True),
                          ("let_loc", "above left"), ("tl_box", True), ("cb_loc", "right"),
                          ("cb_lsize", 9), ("cb_tsize", 7), ("lg_ncol", 2), ("sp_w", 0.1)):
        put(s, widget, value)
    fill = next(lay for lay in s["layers"] if lay["type"] == "fill")
    fill.update(alpha=0.7, scale="log", vmin=1.0, vmax=60.0, cbar_label="reflectivity (dBZ)")
    cont = next(lay for lay in s["layers"] if lay["type"] == "contour")
    cont.update(clabel=True, clabel_fmt="%.0f", legend="w")
    _, _, fig = render(ed, s)
    ax = fig.axes[0]
    assert ax.xaxis.get_major_ticks()[0]._tickdir == "in"
    assert np.allclose(np.diff(ax.get_xticks()), 5.0)
    cb = [a for a in fig.axes if a.get_label() == "<colorbar>"]
    assert cb and cb[0].get_ylabel() == "reflectivity (dBZ)"
    assert ax.get_title(loc="left") == "a"


def test_time_series_y_range(ed):
    s = put(put(_one_line(ed), "ts_ymin", 0.0), "ts_ymax", 50.0)
    _, _, fig = render(ed, settled(ed, s))
    assert fig.axes[0].get_ylim() == (0.0, 50.0)


def test_time_series_marks_extremes(ed):
    s = put(put(_one_line(ed), "ts_mark", "max"), "ts_mark_legend", True)
    _, data, fig = render(ed, settled(ed, s))
    ax, d = fig.axes[0], data[0]
    (_, _, v), = figdraw.series_extremes(d["S0_t"], d["S0_v"], "max")
    assert v == np.nanmax(d["S0_v"])
    assert f"{v:.3g}" in [a.get_text() for a in ax.texts]
    assert "max" in ax.get_legend().texts[0].get_text()  # (one line: still a legend)


def test_map_panels_show_the_maximum(ed):
    from matplotlib.offsetbox import AnchoredText
    s = new_spec(ed, "plan", 1, 1)
    cont = next(j for j, lay in enumerate(s["layers"]) if lay["type"] == "contour")
    s["extremes"] = dict(s["extremes"], on=True, layer=cont, what="max")
    _, data, fig = render(ed, s)
    (vmax, x, _), _ = figdraw.panel_extremes(data[0], cont)
    texts = [a.txt.get_text() for a in fig.axes[0].artists if isinstance(a, AnchoredText)]
    assert f"max {vmax:.3g}" in texts
    x0, x1 = sorted(data[0].get("xlim", (x, x)))
    assert x0 <= x <= x1


@pytest.mark.parametrize("layout", ["inset", "side", "hodo", "skewt"])
def test_sounding_layouts(ed, layout):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.quiver import Barbs
    s = new_spec(ed, "sounding", 1, 1)
    s["skewt"] = dict(s["skewt"], layout=layout, srh="1")
    _, data, fig = render(ed, s)
    assert "N0_rm" in data[0] and "N0_srh1" in data[0]
    hodos = [a for a in fig.axes + [c for a in fig.axes for c in a.child_axes]
             if getattr(a, "_cv_hodo", False)]
    assert len(hodos) == (0 if layout == "skewt" else 1)
    if layout == "inset":  # the barbs stay clear of the inset
        FigureCanvasAgg(fig).draw()
        ax = next(a for a in fig.axes if not getattr(a, "_cv_hodo", False))
        b = next(c for c in ax.collections if isinstance(c, Barbs))
        bx = ax.transData.transform(b.get_offsets()[:1])[0, 0]
        assert hodos[0].get_window_extent().x1 < bx


@pytest.mark.parametrize("plot", ["hist", "box", "violin", "ecdf"])
def test_distribution_figure_draws_each_plot(ed, plot):
    s = new_spec(ed, "dist", 1, 1)
    assert len(s["dists"]) == 1
    s["dists"].append(fg.dist_defaults(dict(field="winterp", vmode="layer", z0=0.0, z1=5.0,
                                            region="domain", lo=0.5), 0,
                                       float(ed.run.times[4])))
    s["dist"] = dict(s["dist"], plot=plot, stats=["mean", "sd", "n"])
    spec, data, fig = render(ed, s)
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
    assert ed.data.dist_cache  # (restyling reads nothing again)
    n = len(ed.data.dist_cache)
    s["dist"] = dict(s["dist"], bins=20, logy=True)
    render(ed, s)
    assert len(ed.data.dist_cache) == n


@pytest.mark.parametrize("plot", ["hist", "scatter", "contour"])
def test_joint_figure_draws_each_plot(ed, plot):
    s = new_spec(ed, "joint", 1, 1)
    r = s["joints"][0]["recipe"]
    assert (r["field"], r["yfield"]) == ("winterp", "zvort")
    t = ed.run.times
    s["joints"] = [fg.joint_defaults(r, 0, float(t[2])),
                   dict(fg.joint_defaults(r, 0, float(t[1])), time_s1=float(t[2]))]
    s["joint"] = dict(s["joint"], plot=plot, stats=["n", "r", "fit"], fit=True, contours=True)
    _, data, fig = render(ed, s)
    d = data[0]
    assert d["njoint"] == 2 and not d.get("missing") and "time_s" not in d
    n0, n1 = float(d["J0_s"][0]), float(d["J1_s"][0])
    assert n1 > n0 > 0 and int(d["J0_h"].sum()) == n0  # (the window: two outputs' pairs)
    assert -1.0 <= float(d["J0_s"][5]) <= 1.0 and d["J0_p"].shape[0] == 2
    assert "min" in str(d["J1_label"]) and "mean" not in str(d["J1_label"])
    ax = fig.axes[0]
    assert "(" in ax.get_xlabel() and "(" in ax.get_ylabel()  # (fields, units)
    assert len(fig.axes) == (2 if plot == "hist" else 1)  # (the colorbar)
    assert ax.get_legend() is not None


def test_azim_figure_shades_the_first_and_contours_the_rest(ed):
    s = new_spec(ed, "azim", 1, 1)
    r = s["azims"][0]["recipe"]
    assert (r["field"], r["center"], r["rmax"], r["op"]) == ("winterp", "track", 20.0, "mean")
    t = ed.run.times
    ks = sorted(ed.run_fixes(s["runs"][0], ed.run))  # (outputs with a centre)
    one = fg.azim_defaults(dict(r, z1=8.0), 0, float(t[ks[3]]))
    over = dict(fg.azim_defaults(dict(r, op="max", az0=0.0, az1=90.0, dr=2.0), 0, float(t[ks[2]])),
                time_s1=float(t[ks[3]]), levels="5, 10", color="#ff0000")
    s["azims"] = [one, over]
    s["azim"] = dict(s["azim"], plot="filled", zmax=6.0)
    _, data, fig = render(ed, s)
    d = data[0]
    assert d["nazim"] == 2 and not d.get("missing") and "time_s" not in d
    assert d["A0_v"].shape == (d["A0_z"].size, d["A0_x"].size) == (d["A0_z"].size, 40)
    assert d["A1_x"].size == 10 and np.isfinite(d["A0_v"]).any()
    assert "min" in str(d["A1_label"]) and "0–90°" in str(d["A1_label"])
    assert str(d["A0_cm"]) and "(" in str(d["A0_cl"])  # (the field's colours, units)
    ax = fig.axes[0]
    assert ax.get_xlabel() == "Radius (km)" and ax.get_ylabel() == "Height (km)"
    assert len(fig.axes) == 2 and ax.get_ylim()[1] == 6.0  # (the colorbar)
    assert ax.get_legend() is not None


def test_table_missing_value_says_why(ed):
    s = new_spec(ed, "table", 1, 1)
    e = s["tables"][0]
    e["where"] = dict(e["where"], kind="trk")  # (no track yet at the first output)
    e["times_s"] = [float(ed.run.times[0])]
    spec, data, _ = render(ed, s)
    assert "track" in data[0].get("why", "")
    assert figdraw.tbl_grid(data[0], spec["table"])[1][0][1][0] == "–"
    assert not fg.animated(spec)


def test_style_presets_and_matplotlib_styles(ed, tmp_path):
    s = fg.apply_style(new_spec(ed), "ams")
    assert (s["font"]["size"], s["letters"]["fmt"], s["export"]["format"]) == (8.0, "({a})", "pdf")
    assert s["size"][0] == (3.2 if s["cols"] == 1 else 6.5) and not s["size_auto"]
    s = fg.apply_style(s, "dark")
    assert (s["background"], s["mplstyle"]) == ("black", "dark_background")
    assert figdraw.rc(s)["axes.edgecolor"] == "white" and figdraw.rc(s)["font.size"] == 14.0
    render(ed, s)
    f = tmp_path / "thick.mplstyle"
    f.write_text("lines.linewidth: 3\nbackend: agg\n")
    rc = figdraw.rc(dict(s, mplstyle=str(f)))
    assert rc["lines.linewidth"] == 3 and "backend" not in rc
    with pytest.raises(ValueError, match="no such style"):
        figdraw.rc(dict(s, mplstyle="no-such-style"))
    s = fg.apply_style(s, "default")
    assert (s["mplstyle"], s["font"]["size"]) == ("", 10.0)


def test_templates_apply_to_another_run(ed, coarse_run):
    spec = new_spec(ed)
    path = fg.save_template(spec, "two by three")
    try:
        assert os.path.dirname(path) == fg.templates_dir()
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
        ed.open_quick()  # (the New dialog applies it; one it can't, says why there)
        ed.qs_tpl.value = path
        assert not ed.qs_tpl_go.disabled
        ed.qs_tpl_go.clicks += 1
        assert not ed.quick.open and "two by three" in ed.shell._said + ed.shell.status.object
        assert ed.shell.doc["runs"][0]["path"] == ed.run.path
        render(ed)
        ed.open_quick()
        ed.qs_tpl.value = path
        with open(path, "w") as f:
            f.write("[]")
        ed.qs_tpl_go.clicks += 1
        assert ed.quick.open and ed.qs_load_note.visible and "Could not" in ed.qs_load_note.object
    finally:
        os.remove(path)
        ed.quick.hide()


def test_ensemble_band_of_a_series_over_runs(ed, demo_root):
    from matplotlib.collections import PolyCollection
    ed.shell.add_run(os.path.join(demo_root, *DEMO_WEAK))
    s = _one_line(ed)
    assert len(s["runs"]) == 2
    e = s["series"][0]
    e.update(runs=[0, 1], ens="minmax")
    settled(ed, s)
    _, data, fig = render(ed, s)
    d = data[0]
    j = next(j for j in range(d["nlines"]) if f"S{j}_ens" in d)
    assert d[f"S{j}_ens"] == 2 and d[f"S{j}_r"] == -1
    assert d[f"S{j}_label"] == e["label"]  # (the series' label, as it is)
    ok = np.isfinite(d[f"S{j}_v"])
    assert ok.any() and np.all(d[f"S{j}_lo"][ok] <= d[f"S{j}_v"][ok] + 1e-6)
    assert np.all(d[f"S{j}_v"][ok] <= d[f"S{j}_hi"][ok] + 1e-6)
    assert sum(f"S{n}_mem" in d for n in range(d["nlines"])) == 2
    assert any(isinstance(x, PolyCollection) for x in fig.axes[0].collections)
    e["ens_members"] = "hidden"  # (the band and its centre alone)
    _, data, _ = render(ed, s)
    assert data[0]["nlines"] == 1 and "S0_ens" in data[0]


def test_a_run_time_zero_on_a_time_series_figure(ed):
    """A run's time zero shifts its line."""
    s = settled(ed, _one_line(ed))
    t = ed.panel_data(s)[0]["S0_t"]
    s["runs"][0]["t0_min"] = 30.0
    np.testing.assert_allclose(ed.panel_data(s)[0]["S0_t"], t - 30.0)


def test_a_figure_draws_your_own_data_and_hand_edits(ed):
    """A hand-edited series and a series of your own data draw both lines; the edited one's
    legend entry says "(edited)"."""
    spec = settled(ed, _one_line(ed))
    n = ed.panel_data(spec)[0]["nlines"]
    e0 = spec["series"][0]
    spec["series"][0] = dict(e0, edits={"0": {fg.edit_key(ed.v.run.times[0]): -123.0}})
    spec["series"].append(dict(e0, source="table", label="obs", runs=[], panel=0,
                               table=dict(t=[0.0, 5.0], v=[1.0, 2.0])))
    data = ed.panel_data(spec)
    assert data[0]["nlines"] == n + 1
    assert any(-123.0 in data[0][f"S{j}_v"] for j in range(n))
    fig = figdraw.draw(spec, data)
    texts = [x.get_text() for x in fig.axes[0].get_legend().texts]
    assert any(x.endswith(" (edited)") for x in texts) and "obs" in texts


def test_labels_shrink_to_fit_a_narrow_panel(ed):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    s = new_spec(ed)
    s["size"] = [3.25, s["size"][1]]
    spec, _, fig = render(ed, s)
    assert spec["label_fit"]
    sizes = {t.get_fontsize() for ax in fig.axes for _, t in getattr(ax, "_cv_labels", [])}
    assert len(sizes) == 1 and 6.0 <= sizes.pop() < 12.0  # (one size, across the figure)
    FigureCanvasAgg(fig).draw()
    r = fig.canvas.get_renderer()
    for ax in fig.axes:
        if getattr(ax, "_cv_labels", None):
            panel = ax.get_window_extent(r)
            labels = sorted((t.get_window_extent(r) for _, t in ax._cv_labels), key=lambda b: b.x0)
            assert panel.x0 <= labels[0].x0 and labels[-1].x1 <= panel.x1
            assert all(a.x1 <= b.x0 for a, b in zip(labels, labels[1:]))


# ------------------------------------------------------------ saving
@pytest.mark.parametrize("start", ["plan", "series", "soundings", "dists", "difference", "swath",
                                   "dark"])
def test_script_redraws_the_identical_image(ed, tmp_path, start):
    import matplotlib.image as mi
    if start == "difference":
        ed.shell.open_new(difference_layer(ed, ed._default()))
    elif start == "swath":
        ed.shell.open_new(swath_layer(ed, ed._default()))
    elif start == "dark":  # (a matplotlib style in the document)
        ed.shell.apply_style("dark")
    elif start == "series":
        ed.from_series()
        settled(ed, doc_now(ed))
    elif start == "soundings":
        ed.from_soundings()
    elif start == "dists":
        ed.from_dists()
        ed.shell.edit(lambda d: d["kinds"]["dist"]["dist"].update(plot="violin"))
    base = str(tmp_path / start)
    ed.path.value = base
    ed._save_job(doc_now(ed), True, base)
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    os.rename(base + ".png", base + "_viewer.png")
    with open(_script_of(base)) as f:  # (short: the drawing code is in _src/)
        assert "def _draw2" not in f.read()
    assert os.path.isfile(str(tmp_path / "_src" / f"{start}_draw.py"))
    r = subprocess.run([sys.executable, "-I", _script_of(base)], capture_output=True, text=True,
                       cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-500:]
    assert np.array_equal(mi.imread(base + ".png"), mi.imread(base + "_viewer.png"))


def test_saving_the_image_also_writes_a_spec_that_reopens(ed, tmp_path):
    base = str(tmp_path / "fig")
    ed.shell.edit(lambda d: d.update(suptitle="reopened"))
    ed._save_job(doc_now(ed), False, base)
    out = fg.bundle_paths({}, base)
    assert os.path.exists(out["image"]) and os.path.exists(out["spec"]), ed.msg.object
    assert not os.path.exists(out["script"]) and not os.path.exists(out["data"])
    ed.shell.edit(lambda d: d.update(suptitle=""))
    assert ed._load_spec(out["spec"]) and ed.shell.doc["suptitle"] == "reopened"
    assert ed.path.value == base


@pytest.mark.parametrize("fit, height", [("width", False), ("full", True)])
def test_exact_size(ed, tmp_path, fit, height):
    """At the figure's width (trimming alone gives 3.27 in for 3.25 in), in the script too."""
    from PIL import Image

    def size_and(fit_to):
        def apply(d):
            d["size"] = [3.25, d["size"][1]]
            d["export"] = dict(d["export"], dpi=200)
            put(d, "fit", fit_to)
        return apply

    ed.shell.edit(size_and("trim"))
    base = str(tmp_path / f"{fit}_trim")
    ed._save_job(doc_now(ed), False, base)
    trim = Image.open(base + ".png").size
    assert trim[0] != 650  # (what the option is for)
    ed.shell.edit(size_and(fit))
    doc = doc_now(ed)
    base = str(tmp_path / fit)
    ed._save_job(doc, True, base)
    saved = Image.open(base + ".png")
    size = saved.size
    assert size[0] == 650, size
    if height:
        assert size[1] == round(doc["size"][1] * 200), size
    else:
        assert abs(size[1] - trim[1]) <= 1, size  # (the height is trimmed as before)
    before = np.asarray(saved.convert("RGB"))
    os.remove(base + ".png")
    subprocess.run([sys.executable, fg.bundle_paths({}, base)["script"]], check=True,
                   capture_output=True)
    assert np.array_equal(np.asarray(Image.open(base + ".png").convert("RGB")), before)
    assert ed._load_spec(fg.bundle_paths({}, base)["spec"])
    export = ed.shell.doc["export"]
    assert export["tight"] == (fit != "full") and export["exact_width"] == (fit == "width")


def test_own_code_runs_saves_and_reports_errors(ed, tmp_path):
    s = new_spec(ed, "plan", 1, 1)
    s["code"] = dict(s.get("code") or {}, on=True, text="axs[0].set_title('from code', loc='right')")
    _, _, fig = render(ed, s)
    assert fig.axes[0].get_title(loc="right") == "from code"
    s["code"]["text"] = "x = 1\n1 / 0"
    _, _, fig = render(ed, s)
    assert fig._cv_code_error.startswith("line 2: ZeroDivisionError")
    s["code"]["text"] = "fig.text(0.5, 0.5, 'CODE')"
    ed.shell.open_new(s)
    ed.shell.edit(lambda d: d["code"].update(on=True))
    base = str(tmp_path / "code")
    ed.path.value = base
    ed._save_job(doc_now(ed), True, base)
    r = subprocess.run([sys.executable, "-I", _script_of(base)], capture_output=True, text=True)
    assert r.returncode == 0 and "stopped" not in r.stdout, r.stderr[-500:]
    assert ed._load_spec(base)  # (finds the spec saved with it): code from a file waits to be read
    assert ed.shell.doc["code"]["text"] == "fig.text(0.5, 0.5, 'CODE')"
    assert not ed.shell.doc["code"]["on"]
    assert "code of its own" in ed.shell._said


def test_save_waits_for_the_series(ed, tmp_path, monkeypatch):
    from cm1view.figures import export as X
    monkeypatch.setattr(X, "SERIES_RECHECK", 0.05)
    s = dict(new_spec(ed), kind="line")
    saved, jobs, busy = [], [], [["run: w 3/9"], ["run: w 3/9"], []]
    monkeypatch.setattr(ed, "panel_data", lambda f: {})
    monkeypatch.setattr(ed, "series_pending", lambda: busy[0])
    monkeypatch.setattr(X.fg, "save_image", lambda f, d, p, **k: saved.append(p) or p)
    monkeypatch.setattr(X.fg, "save_spec", lambda f, b: "spec")
    monkeypatch.setattr(ed.v.pools["fig"], "submit", lambda f, *a: jobs.append((f, a)))
    ed._save_gen = 7
    ed._save_job(s, False, str(tmp_path / "fig"), 7)
    assert not saved
    wait(lambda: jobs, 10, "the second look")
    busy[0] = []
    f, a = jobs.pop()
    f(*a)
    assert saved == [str(tmp_path / "fig.png")]


# ------------------------------------------------------------ animations
def test_animation_steps_every_panel(ed, tmp_path):
    from PIL import Image
    s = new_spec(ed, "plan", 1, 2)
    ts = ed.run.times  # not evenly spaced: offsets follow the first panel's outputs
    s["times_s"] = [float(ts[1]), float(ts[2])]
    ed.shell.open_new(s)
    spec = doc_now(ed)
    ed.an_step.value, ed.an_end.value = 2, None
    full = ed._anim_offsets(spec)  # through the end of the run (the second panel's)
    assert full == [float(ts[i] - ts[1]) for i in range(1, len(full) * 2, 2)]
    assert len(full) == 4 and float(ts[2]) + full[-1] <= ts[-1]  # (the second ends it)
    ed._anim_refresh()  # the End time choices: the frames' times
    assert list(ed.an_end.options.values())[1:] == [float(ts[i])
                                                     for i in range(3, len(full) * 2, 2)]
    ed.an_end.value = float(ts[5])
    offsets = ed._anim_offsets(spec)
    assert offsets == [float(ts[i] - ts[1]) for i in (1, 3, 5)]
    assert "→ 3 frames" in txt(ed.an_count.object), ed.an_count.object
    moved = fg.shift_times(spec, offsets[1])
    assert [p["time_s"] for p in moved["panels"]] == [p["time_s"] + offsets[1]
                                                      for p in spec["panels"]]
    base = str(tmp_path / "loop")
    ed._anim_job(ed._anim_gen, spec, offsets, base, dict(fps=5.0, dpi=40, loop=True, frames=True))
    assert "Saved" in txt(ed.an_msg.object), ed.an_msg.object
    gif = Image.open(base + ".gif")
    assert gif.n_frames == len(offsets) and gif.info.get("loop") == 0
    assert len(list((tmp_path / "loop_frames").glob("loop_*.png"))) == len(offsets)


@pytest.mark.parametrize("kind", ["dist", "profile", "joint", "azim"])
def test_animation_of_entry_figures(ed, demo_root, tmp_path, kind):
    from PIL import Image
    s = _tracks_from_files(new_spec(ed, kind, 1, 1), demo_root)
    assert fg.animated(s)
    ed.an_step.value, ed.an_end.value = 2, None
    offsets = ed._anim_offsets(s)[:2]
    assert len(offsets) == 2
    base = str(tmp_path / kind)
    ed._anim_job(ed._anim_gen, s, offsets, base, dict(fps=5.0, dpi=40, loop=True, frames=False))
    msg = txt(ed.an_msg.object)
    assert "Saved" in msg and "empty panel" not in msg, msg
    assert Image.open(base + ".gif").n_frames == 2


@pytest.mark.parametrize("kind", ["dist", "profile", "joint", "azim"])
def test_animation_scales_are_those_of_all_frames(ed, demo_root, kind):
    s = _tracks_from_files(new_spec(ed, kind, 1, 1), demo_root)
    offsets = ed._anim_offsets(s)
    ends = {}
    for dt in offsets:
        moved = fg.shift_times(s, dt)
        ends = figdraw.fill_ends(moved, ed.panel_data(moved), ends)
    ends = figdraw.fit_scales(s, ends)
    assert figdraw.fit_scales(s, ends) == ends  # (fitted once: as it is)
    seen = set()
    for dt in (offsets[0], offsets[-1]):
        moved = fg.shift_times(s, dt)
        ax = figdraw.draw(moved, ed.panel_data(moved), ends)._cv_axes[0]
        clim = ax.collections[0].get_clim() if kind in ("joint", "azim") else None
        seen.add((ax.get_xlim(), ax.get_ylim() if kind != "profile" else None, clim))
    assert len(seen) == 1


@pytest.mark.parametrize("layout", ["inset", "hodo"])
def test_animation_of_soundings(ed, tmp_path, layout):
    from PIL import Image
    s = new_spec(ed, "sounding", 1, 1)
    s["skewt"] = dict(s["skewt"], layout=layout)
    assert fg.animated(s)
    ed.an_step.value, ed.an_end.value = 2, None
    offsets = ed._anim_offsets(s)[:2]
    assert len(offsets) == 2
    base = str(tmp_path / layout)
    ed._anim_job(ed._anim_gen, s, offsets, base, dict(fps=5.0, dpi=40, loop=True, frames=False))
    assert "Saved" in txt(ed.an_msg.object), ed.an_msg.object
    assert Image.open(base + ".gif").n_frames == 2
