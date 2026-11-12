"""A run still going: the output file being written is left out (core.run.finished),
and Reload run adds what finished since (Registry.reopen, Viewer._reload_run)."""
import glob
import os
import shutil
import time

import pytest

from cm1view.core import run as R
from cm1view.registry import Registry

OLD = time.time() - 3600


@pytest.fixture
def running(demo_run, tmp_path, monkeypatch):
    """A copy of the demo supercell (not a demo run: no stamp two folders up), all files
    an hour old, with the 60 s settle time of the default settings."""
    monkeypatch.setenv("CM1VIEW_SETTLE_SECONDS", "60")
    d = str(tmp_path / "a" / "b" / "run")
    shutil.copytree(demo_run, d)
    files = sorted(glob.glob(os.path.join(d, "cm1out_[0-9]*.nc")))
    for f in files:
        os.utime(f, (OLD, OLD))
    return d, files


def test_finished_files_kept(running):
    _, files = running
    assert R.finished(files) == len(files)


def test_newest_file_just_changed_left_out(running):
    _, files = running
    os.utime(files[-1], None)
    assert R.finished(files) == len(files) - 1


def test_half_written_file_left_out(running):
    _, files = running
    with open(files[-1], "r+b") as fh:
        fh.truncate(200)
    os.utime(files[-1], (OLD, OLD))
    assert R.finished(files) == len(files) - 1


def test_only_the_newest_files_count(running, monkeypatch):
    """A broken file further back is not skipped: the reader reports it."""
    _, files = running
    os.utime(files[2], None)
    assert R.finished(files) == len(files)


def test_settle_zero_checks_only_that_it_opens(running, monkeypatch):
    _, files = running
    monkeypatch.setenv("CM1VIEW_SETTLE_SECONDS", "0")
    os.utime(files[-1], None)
    assert R.finished(files) == len(files)


def test_run_opens_without_the_busy_file_and_reload_adds_it(running):
    d, files = running
    keep = files[-1] + ".keep"
    shutil.copy(files[-1], keep)
    with open(files[-1], "r+b") as fh:
        fh.truncate(200)
    reg = Registry(d, 1, 1)
    run, _ = reg.get(d)
    assert len(run.times) == len(files) - 1 and run.busy == [files[-1]]
    assert "still being written" in R.busy_note(run.busy)
    shutil.move(keep, files[-1])
    os.utime(files[-1], (OLD, OLD))
    run2, _ = reg.reopen(d)
    assert run2 is not run and len(run2.times) == len(files) and run2.busy == []
    assert reg.get(d)[0] is run2


def test_only_file_being_written(running):
    d, files = running
    for f in files[1:]:
        os.remove(f)
    os.utime(files[0], None)
    with pytest.raises(FileNotFoundError, match="still being written"):
        Registry(d, 1, 1).get(d)


def test_failed_reopen_keeps_the_open_run(running):
    d, files = running
    reg = Registry(d, 1, 1)
    run, _ = reg.get(d)
    for f in files:
        os.utime(f, None)  # (every file "being written": the reopen fails)
    with pytest.raises(FileNotFoundError):
        reg.reopen(d)
    assert reg.get(d)[0] is run


def test_demo_runs_are_never_busy(demo_run, monkeypatch):
    monkeypatch.setenv("CM1VIEW_SETTLE_SECONDS", "100000000")
    files = sorted(glob.glob(os.path.join(demo_run, "cm1out_[0-9]*.nc")))
    assert R.finished(files, demo_run) == len(files)


def test_wofs_member_and_mean_leave_out_the_newest_cycle(tmp_path, monkeypatch):
    from cm1view.core import models
    from test_wofs import NC, make_wofs
    root = make_wofs(str(tmp_path / "exp" / "20220523"))
    late = sorted(glob.glob(os.path.join(root, "*", "wrfout_d01_*")))
    for f in late:
        os.utime(f, (OLD, OLD))
    monkeypatch.setenv("CM1VIEW_SETTLE_SECONDS", "60")
    newest = sorted(f for f in late if f.endswith("_2"))[-1]
    os.utime(newest, None)  # member 2 is still writing the last cycle
    m1 = models.open_run(os.path.join(root, "mem01"), workers=1)
    m2 = models.open_run(os.path.join(root, "mem02"), workers=1)
    mean = models.open_run(os.path.join(root, "mean"), workers=1)
    assert len(m1.times) == NC and m1.busy == []
    assert len(m2.times) == NC - 1 and m2.busy == [newest]
    # (a mean of only the members done would change: the whole cycle waits)
    assert len(mean.times) == NC - 1 and newest in mean.busy


def test_reload_button(demo_run):
    """Nothing new: the run is swapped in place (no page reload).  (Its own registry: a
    reopen replaces the run that other tests share.)"""
    from cm1view.viewer import app as A
    reg = Registry(demo_run, 4, 1)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    try:
        assert v.reload_btn.visible
        v._reload_run()
        assert v.run is not run and len(v.run.times) == len(run.times)
        assert "No new output" in v.status.object and v.ses_go.value == ""
    finally:
        v.close()
