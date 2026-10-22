"""Checks on your own CM1 output: the run opens, and a map, a sounding, a cross-section
and a series work on it.  Reads only (never writes into the run).

  CM1VIEW_TEST_RUN=/path/to/run pytest -m real

Use a run whose files are not too large: every 3D field read here is read whole."""
import os

import numpy as np
import pytest

from conftest import wait

RUN = os.environ.get("CM1VIEW_TEST_RUN")
pytestmark = [pytest.mark.real,
              pytest.mark.skipif(not RUN, reason="set CM1VIEW_TEST_RUN to a CM1 run folder")]


@pytest.fixture(scope="module")
def real():
    from cm1view.viewer import app as A
    from cm1view.registry import Registry
    reg = Registry(os.path.abspath(os.path.expanduser(RUN)), 8, None)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    v.tslider.value = len(run.times) // 2
    yield v
    v.close()


def test_opens(real):
    run = real.run
    assert len(run.files) >= 1 and run.ni > 1 and run.nj > 1 and run.nk > 1
    assert len(run.times) == len(run.files)


def test_map(real):
    v = real
    name = "dbz" if "dbz" in v.F else "winterp"
    a = v.F.plane(name, v.t, "height", 1.0)
    assert a.shape == (len(v.run.yh), len(v.run.xh)) and np.isfinite(a).any()


def test_sounding(real):
    v = real
    X0, X1, Y0, Y1 = v.extent
    v.points = [("pt", ((X0 + X1) / 2, (Y0 + Y1) / 2), None)]
    v.request_soundings()
    wait(lambda: not v.snd_col.loading and v.results, 900, "sounding")
    assert np.all(np.isfinite(v.results[0][2]["prof"]["T"]))


def test_cross_section(real):
    v = real
    X0, X1, Y0, Y1 = v.extent
    yc = (Y0 + Y1) / 2
    v.xs_pts = [(X0 + 0.25 * (X1 - X0), yc), (X0 + 0.75 * (X1 - X0), yc)]
    v.request_xsec()
    wait(lambda: "long" in (v.xs_status.object or ""), 900, "section")


def test_series(real, tmp_path, monkeypatch):
    from cm1view.core import series as S
    monkeypatch.setattr(S, "CACHE_DIR", str(tmp_path))
    v = real
    v.ser_field.value, v.ser_vmode.value, v.ser_reduce.value = "winterp", "height", "max"
    v.ser_z.value, v.ser_region.value = 1.0, "domain"
    v._on_ser_compute(None)
    wait(lambda: not v.ser_go.disabled, 1800, "series")
    ds = v.series[v.ser_pick.value]["ds"]
    assert int(ds.computed.sum()) == len(v.run.times)
