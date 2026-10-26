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
from conftest import difference_layer, swath_layer, txt, wait

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline")
DPI = 72


def _png(ed, path):
    """Draw the editor's figure (every part) at DPI into path."""
    from cm1view.figures import draw as figdraw
    spec = ed.collect_all()
    ed.panel_data(spec)
    wait(lambda: not ed.series_pending(), 120, "the series")
    fig = figdraw.draw(spec, ed.panel_data(spec))
    fig.savefig(path, dpi=DPI)
    return spec


def _setup(ed, how):
    if how == "xsec":
        ed.kind.value = "xsec"
    elif how in ("th", "line"):
        ed.from_series()  # (no series computed: max updraft near the storm)
        ed.kind.value = how
    elif how == "sounding":
        ed.from_soundings()
    elif how == "dist":
        ed.from_dists()
        ed.ds["plot"].value = "violin"
    elif how == "difference":
        difference_layer(ed)
    elif how == "swath":
        swath_layer(ed)
    elif how == "dark":
        ed.set_spec(fg.apply_style(ed.collect(), "dark"))
    elif how == "parts":
        ed.rows.value, ed.cols.value = 1, 2
        ed._add_part()
        ed.from_soundings()


@pytest.mark.parametrize("how", ["plan", "xsec", "th", "line", "sounding", "dist",
                                 "difference", "swath", "dark", "parts"])
def test_figure_matches_its_baseline(ed, tmp_path, request, how):
    from matplotlib.testing.compare import compare_images
    _setup(ed, how)
    out = str(tmp_path / f"{how}.png")
    _png(ed, out)
    ref = os.path.join(BASE, f"{how}.png")
    if request.config.getoption("--make-baselines") or not os.path.exists(ref):
        os.makedirs(BASE, exist_ok=True)
        shutil.copyfile(out, ref)
        pytest.skip(f"wrote {ref}: look at it, then commit it")
    tol = float(os.environ.get("CM1VIEW_IMAGE_TOL", "3"))
    err = compare_images(ref, out, tol)
    assert err is None, err


@pytest.mark.parametrize("how", ["plan", "xsec", "th", "line", "sounding", "dist", "parts"])
def test_saved_figure_reopens_and_draws_the_same(ed, tmp_path, how):
    import matplotlib.image as mi
    _setup(ed, how)
    before = _png(ed, str(tmp_path / "before.png"))
    base = str(tmp_path / how)
    ed.path.value = base
    ed._save_job(before, True, base)
    assert "Saved" in txt(ed.msg.object), ed.msg.object
    if ed.parts:
        ed._remove_part()
    ed.kind.value = "sounding" if how == "plan" else "plan"  # (something else in between)
    ed.spec_path.value = base + ".png"
    ed._load_spec()
    assert "Loaded" in txt(ed.msg.object), ed.msg.object
    after = _png(ed, str(tmp_path / "after.png"))
    assert after["kind"] == before["kind"]
    assert [p["kind"] for p in after.get("parts", [])] == \
        [p["kind"] for p in before.get("parts", [])]
    assert np.array_equal(mi.imread(str(tmp_path / "before.png")),
                          mi.imread(str(tmp_path / "after.png")))
