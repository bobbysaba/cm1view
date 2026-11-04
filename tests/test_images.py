"""Image tests: typical figures of the demo run against the PNGs in tests/baseline, and
save -> load -> draw of every panel kind giving the identical image.

  pytest tests/test_images.py                    compare (a missing baseline is written)
  pytest tests/test_images.py --make-baselines   rewrite every baseline (then commit them)

CM1VIEW_IMAGE_TOL sets the allowed RMS difference (0-255, default 3); fonts and
matplotlib versions shift pixels between machines. A failure leaves the image and a
*-failed-diff.png next to it in pytest's tmp dir."""
import os
import shutil

import numpy as np
import pytest

from cm1view.figures import spec as fg
from conftest import difference_layer, doc_now, new_spec, swath_layer, txt, wait

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline")
DPI = 72


def _png(ed, figure, path):
    """Draw a figure (every panel) at DPI into path."""
    from cm1view.figures import draw as figdraw
    ed.panel_data(figure)
    wait(lambda: not ed.series_pending(), 120, "the series")
    fig = figdraw.draw(figure, ed.panel_data(figure))
    fig.savefig(path, dpi=DPI)
    return figure


def _made_by(ed, make):
    """The spec a viewer's tool (a from_ method) opens a figure with."""
    sh, got = ed.shell, []
    sh.open_new = got.append
    try:
        make()
    finally:
        del sh.open_new
    return sh.new_form(got[0])


def _figure(ed, how):
    """The figure of each image: a document, or for "parts" the older form it was saved in."""
    sh = ed.shell
    # (as the page's example: from the run's first output, whatever the slider says)
    new = ed._keep_runs(fg.default_spec(ed.run, ed.F, 0))
    if not ed.v.fixes:
        new["domain"] = dict(new["domain"], mode="full")
    if how == "xsec":  # (the plan views' grid, as sections)
        new["kind"] = "xsec"
        fg.kind_look(new, "xsec")
        sh.open_new(new)
    elif how == "th":
        ed.from_series()  # (no series computed: max updraft near the storm)
    elif how == "line":  # (the same max updraft, as a line)
        s = _made_by(ed, ed.from_series)
        s.update(kind="line", size=[7.0, 3.5], axes=dict(s["axes"], ylabel=""))
        s["series"][0]["runs"] = [0]
        sh.open_new(s)
    elif how == "sounding":
        ed.from_soundings()
    elif how == "dist":
        ed.from_dists()
        sh.edit(lambda d: d["kinds"]["dist"]["dist"].update(plot="violin"))
    elif how == "profile":  # (max w near the storm, at two times)
        s = new_spec(ed, "profile", 1, 1)
        s["profiles"].append(dict(s["profiles"][0], time_s=float(ed.run.times[2])))
        sh.open_new(s)
    elif how == "joint":  # (zvort against w at 1 km, as a 2D histogram with contours)
        s = new_spec(ed, "joint", 1, 1)
        s["joint"] = dict(s["joint"], contours=True, fit=True)
        sh.open_new(s)
    elif how == "azim":  # (w around the storm, with its maximum in the front-right as lines)
        s = new_spec(ed, "azim", 1, 1)
        e = s["azims"][0]
        s["azims"].append(dict(e, recipe=dict(e["recipe"], op="max", az0=0.0, az1=90.0),
                               levels="2, 6, 10"))
        sh.open_new(s)
    elif how == "difference":
        sh.open_new(difference_layer(ed, new))
    elif how == "swath":
        sh.open_new(swath_layer(ed, new))
    elif how == "dark":
        sh.apply_style("dark")
    elif how == "parts":
        from cm1view.figures.combo import combine
        new.update(rows=1, cols=2, size=[8.0, 4.99], times=new["times"][:2],
                   times_s=new["times_s"][:2])
        parts = [sh.new_form(new), _made_by(ed, ed.from_soundings)]
        for p in parts:
            p["letters"] = dict(p["letters"], on=True)  # (they run on from part to part)
        return fg.plain_copy(combine(parts, like=parts[0]))
    return doc_now(ed)


@pytest.mark.parametrize("how", ["plan", "xsec", "th", "line", "sounding", "dist",
                                 "profile", "joint", "azim", "difference", "swath", "dark",
                                 "parts"])
def test_figure_matches_its_baseline(ed, tmp_path, request, how):
    from matplotlib.testing.compare import compare_images
    out = str(tmp_path / f"{how}.png")
    _png(ed, _figure(ed, how), out)
    ref = os.path.join(BASE, f"{how}.png")
    if request.config.getoption("--make-baselines", default=False) or not os.path.exists(ref):
        os.makedirs(BASE, exist_ok=True)
        shutil.copyfile(out, ref)
        pytest.skip(f"wrote {ref}: look at it, then commit it")
    tol = float(os.environ.get("CM1VIEW_IMAGE_TOL", "3"))
    err = compare_images(ref, out, tol)
    assert err is None, err


@pytest.mark.parametrize("how", ["plan", "xsec", "th", "line", "sounding", "dist",
                                 "profile", "joint", "azim", "parts"])
def test_saved_figure_reopens_and_draws_the_same(ed, tmp_path, how):
    import matplotlib.image as mi
    figure = _figure(ed, how)
    if how == "parts":  # (it opens as a document)
        ed.shell.open_spec(figure)
    before = _png(ed, doc_now(ed), str(tmp_path / "before.png"))
    base = str(tmp_path / how)
    ed.path.value = base
    ed._save_job(before, True, base)
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    ed.shell.open_new(new_spec(ed, "sounding" if how == "plan" else "plan"))  # (something else)
    assert ed._load_spec(base + ".png")
    assert "Loaded" in txt(ed.shell.status.object) or "Loaded" in ed.shell._said
    after = _png(ed, doc_now(ed), str(tmp_path / "after.png"))
    assert [p["kind"] for p in after["panels"]] == [p["kind"] for p in before["panels"]]
    a, b = mi.imread(str(tmp_path / "before.png")), mi.imread(str(tmp_path / "after.png"))
    # (2 levels: identical draws of a sounding can differ by 1 in a few pixels)
    assert a.shape == b.shape and np.abs(a - b).max() <= 2 / 255
