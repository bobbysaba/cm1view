"""Figure data without the editor (figures/render.py FigureData): the same arrays as
the editor's preview, for each kind of figure, with no Panel loaded."""
import os
import subprocess
import sys

import numpy as np
import pytest

from conftest import wait


def same(a, b, where="data"):
    """Assert a == b, through dicts, lists and arrays (NaN equal to NaN)."""
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), f"{where}: keys differ"
        for k in a:
            same(a[k], b[k], f"{where}[{k!r}]")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), f"{where}: lengths differ"
        for k, (x, y) in enumerate(zip(a, b)):
            same(x, y, f"{where}[{k}]")
    elif isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a, b = np.asarray(a), np.asarray(b)
        assert a.shape == b.shape, f"{where}: shapes differ"
        if a.dtype.kind in "fc":
            assert np.array_equal(a, b, equal_nan=True), f"{where}: values differ"
        else:
            assert np.array_equal(a, b), f"{where}: values differ"
    elif isinstance(a, float) and isinstance(b, float) and np.isnan(a):
        assert np.isnan(b), f"{where}: {a} != {b}"
    else:
        assert a == b, f"{where}: {a!r} != {b!r}"


def _with_track_file(spec, demo_root):
    """The spec with its runs' tracks the demo's track files (not the viewer's)."""
    for e in spec.get("runs") or []:
        name = os.path.basename(e["path"].rstrip("/"))
        e["track"] = os.path.join(demo_root, "storm_tracks", f"demo_{name}.csv")
    for p in spec.get("parts") or []:
        _with_track_file(p, demo_root)
    return spec


MAKERS = {
    "plan": lambda ed: None,  # (the default: a 2 x 3 grid in time)
    "xsec": lambda ed: ed.from_xsec(),
    "sounding": lambda ed: ed.from_soundings(),
    "dist": lambda ed: ed.from_dists(),
    "series": lambda ed: ed.from_series(),
}


@pytest.mark.parametrize("kind", list(MAKERS))
def test_headless_data_match_the_editor(ed, demo_root, kind):
    from cm1view.figures import draw as figdraw
    from cm1view.figures.render import FigureData
    MAKERS[kind](ed)
    spec = _with_track_file(ed.collect(), demo_root)
    ed.panel_data(spec)  # (series: starts computing them in the background)
    wait(lambda: not ed.series_pending(), 120, "the series")
    mine = ed.panel_data(spec)
    fd = FigureData()  # (opens the runs itself; series computed before it returns)
    data = fd.panel_data(spec)
    assert not fd.series_pending()
    assert data and set(data) == set(mine)
    assert not any(d.get("missing") for d in data.values())
    same(mine, data)
    figdraw.draw(spec, data)  # (draws)


def test_headless_data_are_kept(ed, demo_root, monkeypatch):
    """Drawing the same figure again (restyled) reads nothing."""
    from cm1view.figures import spec as fg
    from cm1view.figures.render import FigureData
    spec = _with_track_file(ed.collect(), demo_root)
    fd = FigureData()
    fd.panel_data(spec)
    n = len(fd.cache)
    assert n

    def extract(*a, **k):
        raise AssertionError("read again")

    monkeypatch.setattr(fg, "extract", extract)
    spec["font"] = dict(spec["font"], size=float(spec["font"].get("size", 10)) + 2)
    fd.panel_data(spec)
    assert len(fd.cache) == n


def test_headless_figure_of_parts_and_viewer_track(ed, demo_root):
    """A figure of parts comes back keyed part * 1000 + panel; a run whose track is
    the viewer's has no track without a viewer."""
    from cm1view.figures import spec as fg
    from cm1view.figures.combo import combine
    from cm1view.figures.render import FigureData
    a = _with_track_file(ed.collect(), demo_root)
    ed.from_dists()
    b = _with_track_file(ed.collect(), demo_root)
    data = FigureData().panel_data(combine([a, b]))
    assert {i for i in data if i < 1000} == set(range(fg.npanels(a))) and 1000 in data
    entry = dict(a["runs"][0], track="viewer")
    fd = FigureData()
    run, _ = fd.open_run(entry["path"])
    assert fd.run_fixes(entry, run) == {}
    assert fd.open_run(entry["path"])[0] is run  # (opened once)


def test_render_module_needs_no_panel():
    code = ("import sys; import cm1view.figures.render; "
            "sys.exit(int(any(m in sys.modules for m in ('panel', 'bokeh'))))")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True,
                       text=True, timeout=300)
    assert r.returncode == 0, r.stderr or "Panel or Bokeh imported"
