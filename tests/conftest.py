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
    # runs written by tests are opened at once: no file counts as still being written
    # for being new (test_running.py sets its own)
    os.environ["CM1VIEW_SETTLE_SECONDS"] = "0"


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
    e.shell.auto.value = False  # renders only when a test asks
    return e


def doc_now(ed):
    """A copy of the figure the editor holds, as a file has it."""
    from cm1view.figures import spec as fg
    return fg.plain_copy(ed.shell.doc)


def new_spec(ed, kind="plan", rows=2, cols=3, vary="times"):
    """The version-1 spec the New dialog starts a figure of a kind from (time series and
    time-height: with two series, as nothing is computed without one)."""
    from cm1view.figures import spec as fg
    from cm1view.figures.kinds import KINDS
    ed.open_quick()
    ed.quick.hide()
    ed.qs_kind.value = kind
    ed.qs_vary.value = vary
    ed.qs_rows.value, ed.qs_cols.value = rows, cols
    s = ed._quick_spec()
    if kind in ("th", "line"):
        s["series"] = [dict(fg.series_defaults(ed.F, ed._new_recipe(), n),
                            panel=n if kind == "th" else 0) for n in range(2)]
        if kind == "th":
            s.update(rows=2, cols=1)
    size = KINDS[kind].size
    if size:
        s["size"] = [round(min(16.0, float(v)), 2) for v in size(s["rows"], s["cols"])]
    return fg.plain_copy(ed.shell.new_form(s))


def set_look(ed, kind, block, **values):
    """Settings of a kind's look changed in the figure the editor holds, as its card does."""
    ed.shell.edit(lambda d: d["kinds"][kind][block].update(values))


def put(s, widget, value):
    """Spec s with the setting of widget name `widget` (settings.py) as if typed there."""
    from cm1view.figures import settings as table
    st = next(x for x in table.SETTINGS if x.widget == widget)
    block, _, key = st.key.rpartition(".")
    held = s.setdefault(block, {}) if block else s
    if key == "*":
        held.update(st.as_.read(value))
    else:
        held[key] = st.as_.read(value)
    return s


def render(ed, figure=None):
    """Draw a figure (default: the one the editor holds) as the preview does (raises on errors):
    (the figure, its data, the matplotlib figure)."""
    from cm1view.figures import draw as figdraw
    figure = doc_now(ed) if figure is None else figure
    data = ed.panel_data(figure)
    return figure, data, figdraw.draw(figure, data)


def settled(ed, figure):
    """What the figure's series need, computed."""
    ed.panel_data(figure)
    wait(lambda: not ed.series_pending(), 120, "the series")
    return figure


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


def difference_layer(ed, s):
    """Spec s's first fill as a difference: minus the run's first output, diverging about 0."""
    from cm1view.figures.cards.layercard import _nice
    lay = next(x for x in s["layers"] if x["type"] == "fill")
    a = _nice(0.25 * (float(lay["vmax"]) - float(lay["vmin"])))
    lay.update(minus=dict(run=None, time_s=float(ed.run.times[0]), grid="ask"), cmap="RdBu",
               reverse=True, white_first=False, vmin=-a, vmax=a, scale="linear", mask_below=None)
    return s


def swath_layer(ed, s):
    """Spec s's first fill as a swath: its maximum from the run's first output to each panel's
    time."""
    lay = next(x for x in s["layers"] if x["type"] == "fill")
    lay["reduce"] = dict(op="max", t0=float(ed.run.times[0]), t1=None, every=1)
    return s


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
