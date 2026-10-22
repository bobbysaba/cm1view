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
