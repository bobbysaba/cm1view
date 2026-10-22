"""Shared test setup: synthetic demo runs (cm1view.demo), a throwaway settings file, and
one Registry for the whole session.

  pytest                 tests on the demo data (the default)
  pytest -m real         checks on your own run: CM1VIEW_TEST_RUN=/path/to/run (slow)
  pytest -m browser      the viewer in headless Firefox, with screenshots (slow)
  pytest --make-baselines   rewrite the PNGs in tests/baseline (test_images.py)

The demo data is written once to $CM1VIEW_TEST_DATA (default: <tmp>/cm1view-demo-$USER)
and rewritten only when cm1view/demo.py changes.
"""
import os
import re
import sys
import tempfile
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)


def pytest_addoption(parser):
    parser.addoption("--make-baselines", action="store_true",
                     help="rewrite the baseline images of test_images.py")


def pytest_configure(config):
    # before cm1view.config is imported anywhere; spawned readers inherit these
    cfg = tempfile.mkdtemp(prefix="cm1view-testcfg-")
    os.environ["CM1VIEW_CONFIG"] = os.path.join(cfg, "config.toml")
    os.environ["CM1VIEW_CACHE_DIR"] = os.path.join(cfg, "cache")
    os.environ["CM1VIEW_ALLOW_WRITES_TO_OUTPUT"] = "1"


@pytest.fixture(scope="session")
def demo_root():
    from cm1view import demo
    root = os.environ.get("CM1VIEW_TEST_DATA") or os.path.join(
        tempfile.gettempdir(), f"cm1view-demo-{os.environ.get('USER', 'user')}")
    demo.make(root)
    return root


@pytest.fixture(scope="session")
def demo_run(demo_root):
    return os.path.join(demo_root, "demo", "supercell")


@pytest.fixture(scope="session")
def reg(demo_run):
    from cm1view.registry import Registry
    r = Registry(demo_run, 4, 2)
    yield r


@pytest.fixture
def viewer(reg):
    """A fresh Viewer on the demo supercell, at the first storm time."""
    from cm1view.viewer import app as A
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    v.tslider.value = 1
    yield v
    v.close()


def wait(pred, tmax=60, msg="condition"):
    """Poll pred() until true; fail the test after tmax seconds."""
    t0 = time.time()
    while not pred():
        if time.time() - t0 > tmax:
            raise AssertionError(f"timed out after {tmax}s waiting for {msg}")
        time.sleep(0.02)
    return time.time() - t0


def txt(html):
    return re.sub("<[^>]+>", "", html or "")


def tap(v, x, y, shift=False):
    v._on_tap(type("E", (), {"x": x, "y": y, "modifiers": {"shift": shift}})())


# ------------------------------------------------------------------ figure workspace
@pytest.fixture
def ed(viewer):
    e = viewer.figed
    e.auto.value = False  # renders only when a test asks
    return e


def render(ed):
    """Draw the editor's figure as the preview does (raises on errors)."""
    from cm1view.figures import draw as figdraw
    spec = ed.collect()
    data = ed.panel_data(spec)
    return spec, data, figdraw.draw(spec, data)


@pytest.fixture(scope="module")
def coarse_run(demo_root, tmp_path_factory):
    """The demo supercell with every other output (600 s apart, from 3600 s): a run
    whose output times differ from the viewer's."""
    import os
    main = os.path.join(demo_root, "demo", "supercell")
    d = tmp_path_factory.mktemp("coarse") / "supercell_coarse"
    d.mkdir()
    for f in ["namelist.input"] + [f"cm1out_{n:06d}.nc" for n in (2, 4, 6, 8, 10)]:
        os.symlink(os.path.join(main, f), d / f)
    return str(d)


def difference_layer(ed):
    """The first fill as a difference: minus the run's first output."""
    c = next(c for c in ed.cards if c.type == "fill")
    c.w["minus_on"].value = True
    c.w["minus_time"].value = next(v for v in c.w["minus_time"].options.values() if v != "")
    return c


def swath_layer(ed):
    """The first fill as a swath: its maximum from the run's first output to each panel's
    time."""
    c = next(c for c in ed.cards if c.type == "fill")
    c.w["reduce_op"].value = "max"
    c.w["reduce_t0"].value = next(v for v in c.w["reduce_t0"].options.values() if v != "")
    return c


def edited_v1():
    """A version 1 plan spec of two runs with per-panel edits."""
    fill = dict(type="fill", on=True, field="dbz", mode="height", z=1.0, cmap="viridis",
                vmin=0.0, vmax=60.0, extend="neither")
    cont = dict(type="contour", on=True, field="w", mode="height", z=3.0, levels="5")
    edits = {"1": dict(run=1, time_s=900.0, z=2.0, title="B",
                       layers={"0": dict(cmap="magma", run=0, time_s=60.0)},
                       extra=[cont])}
    return dict(version=1, kind="plan", rows=1, cols=3, vary="time",
                times_s=[0.0, 300.0, 600.0], run=0, layers=[fill], titles=["A"],
                runs=[dict(path="/a"), dict(path="/b")], size=[9, 3], edits=edits)
