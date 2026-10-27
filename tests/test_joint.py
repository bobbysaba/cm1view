"""Joint distributions: the summary against numpy on the whole paired sample (moments,
correlation, rebinned 2D histograms, density contours, the random pick), pairing two
fields of the demo run at the same points, and the recipe's keys and text."""
import numpy as np
import pytest

from cm1view.core import joint
from cm1view.figures import draw as figdraw


@pytest.fixture(scope="module")
def pairs():
    rng = np.random.default_rng(2)
    x = rng.normal(0.0, 2.0, 300_000)
    y = 0.6 * x + rng.normal(1.0, 1.0, x.size)
    return x.astype(np.float32), y.astype(np.float32)


def test_summary_matches_the_sample(pairs):
    x, y = pairs
    st = joint.summarize(x, y)
    assert st["n"] == x.size and (st["xlo"], st["yhi"]) == (x.min(), y.max())
    assert np.isclose(st["mx"], x.mean(dtype=np.float64))
    assert np.isclose(st["sy"], y.std(dtype=np.float64))
    assert np.isclose(st["r"], np.corrcoef(x.astype(float), y.astype(float))[0, 1])
    assert st["h"].shape == (joint.NJ, joint.NJ) and st["h"].sum() == x.size
    assert st["px"].size == joint.NPTS  # (a random pick, the same each time)
    assert np.array_equal(st["px"], joint.summarize(x, y)["px"])
    assert joint.summarize(np.array([]), np.array([])) == dict(n=0)
    flat = joint.summarize(np.ones(5), np.arange(5.0))  # (x constant: no correlation)
    assert np.isnan(flat["r"]) and flat["h"].sum() == 5 and flat["px"].size == 5


def test_histograms_and_contours_from_the_summary(pairs):
    x, y = pairs
    st = joint.summarize(x, y)
    ex, ey = figdraw.joint_edges([st], bins=30, xlo=-4.0, xhi=4.0, ylo=-3.0, yhi=5.0)
    assert ex.size == ey.size == 31 and (ex[0], ey[-1]) == (-4.0, 5.0)
    H = figdraw.joint_hist(st, ex, ey)
    ref, _, _ = np.histogram2d(x, y, bins=[ex, ey])
    assert abs(H - ref).sum() / ref.sum() < 0.05  # (a pair moves at most one fine bin)
    full = figdraw.joint_edges([st], bins=40)
    pdf = figdraw.joint_hist(st, *full, "pdf")
    assert np.isclose((pdf * np.outer(np.diff(full[0]), np.diff(full[1]))).sum(), 1.0)
    assert np.isclose(figdraw.joint_hist(st, *full, "frac").sum(), 1.0)
    # contours: the bins above each level hold about that share of the pairs
    Hf = figdraw.joint_hist(st, *full)
    lv = figdraw.joint_levels(Hf, figdraw.joint_pcts("90, 50%, x, 120"))
    assert [p for _, p in lv] == [90.0, 50.0] and lv[0][0] < lv[1][0]
    for v, p in lv:
        assert abs(Hf[Hf >= v].sum() / Hf.sum() - p / 100.0) < 0.05
    assert figdraw.joint_levels(np.zeros((3, 3)), [50.0]) == []


def test_summary_round_trips_and_stats_text(pairs):
    st = joint.summarize(*pairs)
    back = figdraw.joint_of(figdraw.joint_arrays(st, 1), 1)
    for k in ("n", "mx", "my", "sx", "sy", "r", "xlo", "xhi", "ylo", "yhi"):
        assert np.isclose(back[k], st[k])
    assert np.array_equal(back["h"], st["h"]) and np.allclose(back["py"], st["py"])
    t = figdraw.joint_stats_text(st, ["n", "r", "fit"])
    assert t.startswith(f"n {st['n']:,}, r 0.") and ", y = 0." in t


def test_pairs_of_the_demo_run(reg):
    run, F = reg.get()
    t = 4
    r = joint.normalize(dict(field="winterp", yfield="zvort", vmode="height", z=1.0,
                             region="domain"))
    x, y = joint.sample(run, F, r, t)
    w = F.plane("winterp", t, "height", 1.0)
    z = F.plane("zvort", t, "height", 1.0)
    ok = np.isfinite(w) & np.isfinite(z)
    assert x.size == y.size == ok.sum()
    assert np.allclose(np.sort(x), np.sort(w[ok])) and np.allclose(np.sort(y), np.sort(z[ok]))
    up_x, up_y = joint.sample(run, F, dict(r, lo=1.0, yhi=0.0), t)
    assert up_x.min() >= 1.0 and up_y.max() <= 0.0 and up_x.size == ((w >= 1) & (z <= 0)).sum()
    lay = joint.normalize(dict(r, vmode="layer", z0=0.0, z1=3.0))
    ks = np.flatnonzero((run.z >= 0.0) & (run.z <= 3.0))
    assert joint.sample(run, F, lay, t)[0].size == ks.size * run.nj * run.ni
    flat = joint.normalize(dict(r, yfield="sws"))  # (a 2D field with a 3D one)
    assert joint.sample(run, F, flat, t)[0].size == run.nj * run.ni
    st = joint.compute(run, F, r, [t, t + 1])
    assert st["n"] == x.size + joint.sample(run, F, r, t + 1)[0].size
    with pytest.raises(ValueError):
        joint.sample(run, F, dict(r, region="track"), t)  # (no storm centre)


def test_recipe_keys_and_text():
    r = joint.normalize(dict(field="winterp", yfield="zvort", vmode="height", z=1.0,
                             region="domain", ylo="", yhi=0.5))
    assert r == dict(field="winterp", yfield="zvort", vmode="height", z=1.0,
                     region="domain", lo=None, hi=None, ylo=None, yhi=0.5)
    assert joint.describe(r, "w", "ζ") == "ζ vs w 1 km, domain"
