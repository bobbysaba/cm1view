"""Distributions: the summary against numpy on the whole sample (moments, quantiles,
whiskers, rebinned histograms, cumulative fractions, the violin's density), sampling
regions and layers of the demo run, and the map's Distribution panel."""
import numpy as np
import pytest

from cm1view.core import dist
from cm1view.figures import draw as figdraw
from conftest import txt, wait


@pytest.fixture(scope="module")
def sample():
    rng = np.random.default_rng(1)
    return np.concatenate([rng.normal(0.0, 2.0, 200_000),
                           rng.exponential(5.0, 5_000) + 4.0]).astype(np.float32)


def test_summary_matches_the_sample(sample):
    a = sample.copy()
    st = dist.summarize(sample.copy())
    assert st["n"] == a.size and (st["lo"], st["hi"]) == (a.min(), a.max())
    assert np.isclose(st["mean"], a.mean(dtype=np.float64))
    assert np.isclose(st["std"], a.std(dtype=np.float64))
    assert np.allclose(st["q"], np.quantile(a, figdraw.DIST_PROBS), rtol=1e-6, atol=1e-6)
    q1, q3 = np.quantile(a, [0.25, 0.75])
    inside = a[(a >= q1 - 1.5 * (q3 - q1)) & (a <= q3 + 1.5 * (q3 - q1))]
    assert (st["wlo"], st["whi"]) == (inside.min(), inside.max())
    assert st["h"].sum() == a.size and len(st["h"]) == dist.NFINE
    assert dist.summarize(np.array([], dtype=np.float32)) == dict(n=0)
    one = dist.summarize(np.full(10, 3.0, dtype=np.float32))  # (a single value)
    assert one["h"].sum() == 10 and one["lo"] == one["hi"] == 3.0


def test_histograms_from_the_summary(sample):
    st = dist.summarize(sample.copy())
    edges = figdraw.dist_edges([st], bins=40, lo=-6.0, hi=6.0)
    assert len(edges) == 41 and edges[0] == -6.0 and edges[-1] == 6.0
    v = figdraw.dist_hist(st, edges)
    ref, _ = np.histogram(sample, bins=edges)
    fine = (st["hi"] - st["lo"]) / dist.NFINE  # (a value moves at most one fine bin)
    near = sum(((sample > e - fine) & (sample < e + fine)).sum() for e in edges)
    assert abs(v - ref).sum() <= near
    # PDF: the whole sample integrates to 1 (values outside the bins count too)
    full = figdraw.dist_edges([st], bins=50)
    assert np.isclose((figdraw.dist_hist(st, full, "pdf") * np.diff(full)).sum(), 1.0)
    assert np.isclose(figdraw.dist_hist(st, full, "frac").sum(), 1.0)
    w = figdraw.dist_edges([st], width=0.5, lo=-2.0, hi=2.0)
    assert np.allclose(np.diff(w), 0.5) and w[-1] >= 2.0
    # cumulative: 0 to 1 (or 1 to 0 above), the median near one half
    x, y = figdraw.dist_cdf(st)
    assert y[0] == 0.0 and np.isclose(y[-1], 1.0) and np.all(np.diff(y) >= 0)
    assert abs(np.interp(np.median(sample), x, y) - 0.5) < 0.01
    xa, ya = figdraw.dist_cdf(st, above=True)
    assert np.allclose(ya, 1.0 - y)
    # violin: a density that integrates to about 1
    kx, kd = figdraw.dist_kde(st)
    assert np.all(kd >= 0) and abs((0.5 * (kd[1:] + kd[:-1]) * np.diff(kx)).sum() - 1.0) < 0.05
    assert figdraw.dist_whiskers(st, "range") == (st["lo"], st["hi"])
    assert figdraw.dist_whiskers(st, "p5") == (figdraw.dist_q(st, 0.05),
                                               figdraw.dist_q(st, 0.95))


def test_summary_round_trips_through_panel_arrays(sample):
    st = dist.summarize(sample.copy())
    back = figdraw.dist_of(figdraw.dist_arrays(st, 2), 2)
    for k in ("n", "mean", "std", "lo", "hi", "wlo", "whi"):
        assert np.isclose(back[k], st[k])
    assert np.array_equal(back["h"], st["h"]) and np.allclose(back["q"], st["q"])


def test_sample_regions_and_layers(reg):
    run, F = reg.get()
    t = 4
    r = dist.normalize(dict(field="winterp", vmode="height", z=1.0, region="domain"))
    a = dist.sample(run, F, r, t)
    plane = F.plane("winterp", t, "height", 1.0)
    assert a.size == np.isfinite(plane).sum() and np.isclose(a.max(), np.nanmax(plane))
    up = dist.sample(run, F, dict(r, lo=1.0), t)
    assert up.size == (plane >= 1.0).sum() and up.min() >= 1.0
    x0, x1, y0, y1 = -10.0, 10.0, -5.0, 5.0
    box = dist.sample(run, F, dist.normalize(dict(r, region="box", box=[x0, x1, y0, y1])), t)
    assert 0 < box.size < a.size
    lay = dist.normalize(dict(field="winterp", vmode="layer", z0=0.0, z1=3.0, region="domain"))
    ks = np.flatnonzero((run.z >= 0.0) & (run.z <= 3.0))
    assert dist.sample(run, F, lay, t).size == ks.size * run.nj * run.ni
    whole = dist.normalize(dict(field="winterp", vmode="all", region="domain"))
    assert dist.sample(run, F, whole, t).size == len(run.z) * run.nj * run.ni
    trk = dist.normalize(dict(field="winterp", vmode="height", z=1.0, region="track"))
    with pytest.raises(ValueError):
        dist.sample(run, F, trk, t)  # (no storm centre)
    disc = dist.sample(run, F, trk, t, center=(0.0, 0.0))
    assert 0 < disc.size < a.size


def test_recipe_keys_and_text():
    r = dist.normalize(dict(field="winterp", vmode="layer", z=1.0, z0=0.0, z1=10.0,
                            region="domain", box=[0, 1, 0, 1], radius=3.0, lo="", hi=None))
    assert r == dict(field="winterp", vmode="layer", region="domain", z0=0.0, z1=10.0,
                     lo=None, hi=None)
    assert dist.describe(dict(r, lo=0.0), "w", "m/s") == "w 0–10 km ≥ 0 m/s, domain"


def test_map_distribution_panel(viewer):
    v = viewer
    v.mode._on("Distribution", None)
    assert v.mode.value == "Distribution" and v.panel_col.visible and v.tabs.active == 4
    v.dist_field.value, v.dist_z.value = "winterp", 1.0
    v._dist_request()
    wait(lambda: len(v.dists) == 1, msg="the distribution")
    assert "values" in txt(v.dist_status.object) and not v.dist_to_fig.disabled
    v.tslider.value = 4
    v._dist_request()
    wait(lambda: len(v.dists) == 2, msg="the second distribution")
    assert v.dist_table.object.count("<tr>") == 2  # (a row of statistics each)
    for kind in ("hist", "box", "violin", "ecdf"):
        v.dist_kind.value = kind
        assert v.dist_plot.object is not None
    v.dist_kind.value, v.dist_norm.value, v.dist_logy.value = "hist", "pdf", True
    assert v.dist_plot.object.yaxis[0].axis_label == "probability density"
    look = v.dist_look()
    assert look["plot"] == "hist" and look["norm"] == "pdf" and look["logy"]
    # following the time: the chosen one at the new time, in its place
    v.dist_follow.value = True
    first = v.dist_pick.value
    v.tslider.value = 6
    v._refresh_panels()
    wait(lambda: first not in v.dists, msg="the followed distribution")
    assert len(v.dists) == 2 and any(s["t"] == 6 for s in v.dists.values())
    v.dist_follow.value = False
    v._dist_drop(list(v.dists))
    assert not v.dists and v.dist_clear.disabled and v.dist_table.object == ""
