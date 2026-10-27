"""Azimuthal means: radius bins of an axisymmetric field, the sector (clockwise from
the motion or north), max / min and time composites on a synthetic grid; the demo
run's counts against numpy; the recipe's keys and text; the Sector layer's outline."""
from types import SimpleNamespace

import numpy as np
import pytest

from cm1view.core import azim
from cm1view.figures import draw as figdraw


class _Fields(dict):
    """A stand-in for core.fields.Fields: 3D fields {name: callable t -> volume}."""

    def __getitem__(self, k):
        return SimpleNamespace(name=k, ndim=3, storm=False)

    def volume(self, name, t, storm=None):
        return dict.__getitem__(self, name)(t)


@pytest.fixture(scope="module")
def grid():
    """A 1 km grid, 81 x 81 columns centred on (0, 0), 5 levels from 0.25 km."""
    x = np.arange(-40.0, 40.5, 1.0)
    run = SimpleNamespace(xh=x, yh=x.copy(), z=np.arange(5) * 0.5 + 0.25, dx=1000.0,
                          dy=1000.0, ni=x.size, nj=x.size, times=[0.0, 60.0])
    X, Y = np.meshgrid(run.xh, run.yh)
    return run, X, Y


def _vol(run, a):
    return np.broadcast_to(a, (len(run.z),) + a.shape).astype(np.float32)


def test_axisymmetric_field_bins_by_radius(grid):
    run, X, Y = grid
    F = _Fields(r=lambda t: _vol(run, np.hypot(X, Y)))
    r = azim.normalize(dict(field="r", center="point", point=(0, 0), rmax=10, dr=2,
                            z0=0, z1=2))
    assert r["ref"] == "motion" and (r["az0"], r["az1"]) == (0.0, 360.0)
    res = azim.compute(run, F, r, [0], {0: (0.0, 0.0)}, {0: 0.0})
    assert np.allclose(res["r"], [1, 3, 5, 7, 9]) and np.allclose(res["z"], run.z[:4])
    assert res["v"].shape == (4, 5) and res["nt"] == 1
    for b in range(5):  # (each bin: the mean radius of the columns in it)
        R = np.hypot(X, Y)
        ref = R[(R >= 2 * b) & (R < 2 * b + 2)].mean()
        assert np.allclose(res["v"][:, b], ref, rtol=1e-5)
    assert int(res["n"][0].sum()) == int((np.hypot(X, Y) < 10).sum())
    # the bin width defaults to the grid spacing
    assert azim.bins(run, azim.normalize(dict(r, dr=None))) == (1.0, 10)


def test_sector_clockwise_from_north_and_from_motion(grid):
    run, X, Y = grid
    F = _Fields(x=lambda t: _vol(run, X), y=lambda t: _vol(run, Y))

    def mean(field, a0, a1, ref, bearing=0.0):
        r = azim.normalize(dict(field=field, center="point", rmax=20, az0=a0, az1=a1,
                                ref=ref, dr=20, z0=0, z1=0))
        return float(azim.compute(run, F, r, [0], {0: (0.0, 0.0)}, {0: bearing})["v"][0, 0])

    assert mean("x", 45, 135, "north") > 5 > -5 > mean("x", 225, 315, "north")  # east, west
    assert mean("y", 315, 45, "north") > 5  # (wraps through north)
    # moving east (bearing 90): 0 is east, 90 (right of the motion) is south
    east = azim.bearing(10.0, 0.0)
    assert east == 90.0 and azim.bearing(0.0, -10.0) == 180.0 and azim.bearing(0, 0) == 0.0
    assert mean("x", 315, 45, "motion", east) > 5
    assert mean("y", 45, 135, "motion", east) < -5
    assert azim.full_ring(dict(az0=0.0, az1=360.0)) and azim.sector_span(270, 90) == 180.0


def test_max_min_and_time_composite(grid):
    run, X, Y = grid
    F = _Fields(c=lambda t: _vol(run, np.full(X.shape, 1.0 + 2.0 * t)))
    base = dict(field="c", center="point", rmax=5, dr=5, z0=0, z1=0)
    cs, refs = {0: (0.0, 0.0), 1: (3.0, -2.0)}, {0: 0.0, 1: 0.0}
    for op, want in (("mean", 2.0), ("max", 3.0), ("min", 1.0)):
        res = azim.compute(run, F, azim.normalize(dict(base, op=op)), [0, 1], cs, refs)
        assert np.allclose(res["v"], want) and res["nt"] == 2
    with pytest.raises(ValueError, match="off the domain"):
        azim.compute(run, F, azim.normalize(base), [0], {0: (500.0, 0.0)}, {0: 0.0})


def test_demo_run_counts_and_grid_check(reg):
    run, F = reg.get()
    t = 4
    cx, cy = float(run.xh[run.ni // 2]), float(run.yh[run.nj // 2])
    r = azim.normalize(dict(field="winterp", center="point", point=(cx, cy), rmax=8,
                            z0=0, z1=3))
    res = azim.compute(run, F, r, [t], {t: (cx, cy)}, {t: 0.0})
    X, Y = np.meshgrid(run.xh, run.yh)
    inside = np.hypot(X - cx, Y - cy) < 8
    ks = np.flatnonzero((run.z >= 0) & (run.z <= 3))
    w = F.volume("winterp", t)[ks][:, inside]
    assert int(res["n"].sum()) == int(np.isfinite(w).sum())
    num = np.nansum(res["v"] * res["n"], axis=1)  # (bin means x counts: the level sums)
    assert np.allclose(num, np.nansum(w, axis=1), rtol=1e-4, atol=1e-3)
    if "w" in F and F["w"].ndim == 3:  # (volumes are read destaggered: w works too)
        rw = azim.compute(run, F, dict(r, field="w"), [t], {t: (cx, cy)}, {t: 0.0})
        assert int(rw["n"].sum()) == int(np.isfinite(F.volume("w", t)[ks][:, inside]).sum())


def test_recipe_keys_and_text():
    r = azim.normalize(dict(field="w", offset=(1, 2), az0=0, az1=90, op="bad", dr=0))
    assert r["center"] == "track" and r["offset"] == [1.0, 2.0] and "point" not in r
    assert r["op"] == "mean" and r["dr"] is None and (r["rmax"], r["z1"]) == (20.0, 15.0)
    assert azim.describe(r, "w") == "w mean 0–90° from motion, storm"
    p = azim.normalize(dict(field="w", center="point", point=(10, -5), op="max"))
    assert azim.describe(p) == "w max, (10, -5) km"


def test_sector_layer_outline():
    d = dict(sector=np.array([10.0, 20.0, 90.0]), origin=np.array([0.0, 0.0]))
    lay = dict(az0=0.0, az1=90.0, rmax=5.0, ref="motion")
    x, y = figdraw.sector_outline(d, lay)
    assert (x[0], y[0]) == (10.0, 20.0) and (x[-1], y[-1]) == (10.0, 20.0)
    assert np.isclose(x[1], 15.0) and np.isclose(y[1], 20.0)  # (0: the motion, east)
    assert np.isclose(x[-2], 10.0) and np.isclose(y[-2], 15.0)  # (90: right of it, south)
    ring = figdraw.sector_outline(d, dict(lay, az1=360.0, ref="north"))
    assert np.allclose(np.hypot(ring[0] - 10.0, ring[1] - 20.0), 5.0)
    pt = figdraw.sector_outline(dict(d, origin=np.array([1.0, 1.0])),
                                dict(lay, center="point", cx=3.0, cy=4.0))
    assert (pt[0][0], pt[1][0]) == (2.0, 3.0)
    assert figdraw.sector_outline(dict(d, sector=np.array([np.nan, np.nan, 0.0])), lay) is None
