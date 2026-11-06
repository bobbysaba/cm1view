"""Light checks on your own WoFS output: the root lists its members, member 1 opens, and one
2D field reads at the first time.  Reads only (never writes into the run), and no 3D field.

  CM1VIEW_WOFS_ROOT=/path/to/root pytest -m real tests/test_real_wofs.py

The root is the folder of cycle folders (YYYYMMDDHHMM) that hold the wrfout_d01_* files."""
import os

import numpy as np
import pytest

ROOT = os.environ.get("CM1VIEW_WOFS_ROOT")
pytestmark = [pytest.mark.real,
              pytest.mark.skipif(not ROOT, reason="set CM1VIEW_WOFS_ROOT to a WoFS run folder")]


@pytest.fixture(scope="module")
def root():
    return os.path.abspath(os.path.expanduser(ROOT))


def test_lists_members(root):
    from cm1view.core import models, wofs
    mem = wofs.members(root)
    assert mem and mem == sorted(mem)
    assert models.detect(os.path.join(root, f"mem{mem[0]:02d}")).key == "wofs"
    assert models.canonical(root) == os.path.join(root, f"mem{mem[0]:02d}")


def test_opens_member_one_and_reads_a_2d_field(root):
    from cm1view.core import models, wofs
    from cm1view.core.fields import Fields
    mem = wofs.members(root)[0]
    run = models.open_run(os.path.join(root, f"mem{mem:02d}"), workers=1)
    try:
        assert run.model == "wofs" and len(run.times) >= 1 and run.times[0] == 0.0
        assert run.ni > 1 and run.nj > 1 and run.nk > 1
        name = "UP_HELI_MAX" if run.has("UP_HELI_MAX") else "HGT"
        a = Fields(run).plane(name, 0, "level", 0)
        assert a.shape == (run.nj, run.ni) and np.isfinite(a).any()
    finally:
        getattr(run, "close", lambda: None)()


def test_grid_sits_on_the_map(root):
    """The grid's projection (core.geo) places every point within a tenth of a grid
    spacing of the file's XLAT, XLONG, and finds some boundary lines over it."""
    from cm1view.core import geo, models, wofs
    mem = wofs.members(root)[0]
    run = models.open_run(os.path.join(root, f"mem{mem:02d}"), workers=1)
    try:
        assert run.geo is not None, "projection not recognised or not matching XLAT, XLONG"
        assert run.geo.misfit < 0.1 * run.dx / 1000.0
        assert any(np.isfinite(run.geo.lines(k)[0]).any() for k in geo.KINDS)
    finally:
        getattr(run, "close", lambda: None)()
