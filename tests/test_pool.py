"""The reader processes shared by every run (cm1view.core.pool) and the files a reader
keeps open (cm1view.core.run.opened)."""
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from cm1view.core import pool
from cm1view.core import run as R


def test_runs_share_one_pool(demo_run):
    """Two runs read in the same processes, and what they read is what a read in this
    process gives; a pool is replaced only by a larger one."""
    a = R.CM1Run(demo_run, cache_gb=1, workers=2)
    b = R.CM1Run(demo_run, cache_gb=1, workers=2)
    assert a._get_pool() is b._get_pool()
    ex = pool.get(2)
    assert pool.get(1) is ex and pool.size() >= 2
    for run in (a, b):
        assert run.load_volumes(["th", "u", "w"], 3)
        for n in ("th", "u", "w"):
            np.testing.assert_array_equal(run.volume(n, 3), run._read_volume_local(n, 3))
    # (again: the readers have the file open by now)
    a.clear_cache()
    assert a.load_volumes(["v"], 3)
    np.testing.assert_array_equal(a.volume("v", 3), a._read_volume_local("v", 3))
    t0 = time.time()
    pool.release()  # (every reader closes its files; they are idle, so at once)
    assert time.time() - t0 < pool.RELEASE_WAIT
    b.clear_cache()
    assert b.load_volumes(["th"], 4)
    np.testing.assert_array_equal(b.volume("th", 4), b._read_volume_local("th", 4))


def test_reader_keeps_files_open(demo_run, monkeypatch, tmp_path):
    """opened() leaves the last KEEP_OPEN files open (in a reader process), opens a file
    that changed anew, and close_kept() closes them; elsewhere it closes at once."""
    import shutil
    files = []
    for i, f in enumerate(R.CM1Run(demo_run, workers=1).files[:3]):
        files.append(shutil.copy(f, tmp_path / f"f{i}.nc"))
    with R.opened(files[0]) as d:
        pass
    assert not d.isopen() and not R._kept  # (this process keeps none)
    monkeypatch.setattr(R, "KEEP_OPEN", 2)
    try:
        with R.opened(files[0]) as d0:
            th = np.array(d0["th"][0, 0])
        assert d0.isopen()
        with R.opened(files[0]) as again:
            assert again is d0
        with R.opened(files[1]) as d1:
            pass
        with R.opened(files[2]) as d2:
            pass
        assert not d0.isopen() and d1.isopen() and d2.isopen()  # (the oldest went)
        st = os.stat(files[1])
        os.utime(files[1], ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        with R.opened(files[1]) as new:
            assert new is not d1 and not d1.isopen()
        try:
            with R.opened(files[2]) as d2:
                raise ValueError("a failed read")
        except ValueError:
            pass
        assert not d2.isopen() and len(R._kept) == 1  # (not kept after an error)
    finally:
        R.close_kept()
    assert not new.isopen() and not R._kept
    with R.opened(files[0]) as d:
        np.testing.assert_array_equal(d["th"][0, 0], th)
    R.close_kept()


def test_spread_keeps_to_its_width():
    """pool.spread gives every result, with no more than `width` tasks at once, and
    closing it drops what was not started."""
    lock, now, most, started = threading.Lock(), [0], [0], []

    def work(x):
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
            started.append(x)
        time.sleep(0.02)
        with lock:
            now[0] -= 1
        return x * x

    with ThreadPoolExecutor(8) as ex:
        assert sorted(pool.spread(ex, work, range(20), 3)) == [x * x for x in range(20)]
        assert most[0] <= 3
        del started[:]
        gen = pool.spread(ex, work, range(100), 2)
        next(gen)
        gen.close()
    assert len(started) < 10
    assert [pool.width(n) for n in (1, 2, 3, 4, 8, 16)] == [1, 2, 3, 3, 6, 12]
    assert sorted(pool.spread(pool.get(2), math.sqrt, [4.0, 9.0], 2)) == [2.0, 3.0]


def test_scan_in_readers_matches(demo_run, monkeypatch):
    """The first scan of a run's files gives the same shared out over the readers."""
    files = R.CM1Run(demo_run, workers=1).files
    here = R.scan_files(files, 1)
    monkeypatch.setattr(R, "SCAN_POOL", 1)
    assert R.scan_files(files, 2) == here
    assert len(here[0]) == len(files) and "th" in here[1][0]


def test_ahead_keeps_order_and_width(demo_run):
    """run.ahead gives (item, result) in the items' order with no more than `width` at
    work, on the calling thread for width 0; closing it drops what was not started; an
    error comes at its item's turn; and reads made in it go to the reader processes and
    are what a read in this process gives."""
    from types import SimpleNamespace
    lock, now, most, started = threading.Lock(), [0], [0], []

    def work(x):
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
            started.append(x)
        time.sleep(0.02 if x % 3 else 0.05)  # (later items finish before earlier ones)
        with lock:
            now[0] -= 1
        return x * x

    assert list(R.ahead(work, range(12), 3)) == [(x, x * x) for x in range(12)]
    assert 1 < most[0] <= 3
    me = threading.current_thread()
    assert [r for _, r in R.ahead(lambda x: threading.current_thread(), range(3), 0)] \
        == [me] * 3
    del started[:]
    gen = R.ahead(work, range(100), 2)
    assert next(gen) == (0, 0)
    gen.close()
    time.sleep(0.2)
    assert len(started) < 10
    gen = R.ahead(lambda x: 1 // (x - 2), range(5), 2)
    assert [next(gen), next(gen)] == [(0, -1), (1, -1)]
    try:
        next(gen)
        raise AssertionError("no error at its turn")
    except ZeroDivisionError:
        pass

    run = R.CM1Run(demo_run, cache_gb=1, workers=2)
    assert R.ahead_width(SimpleNamespace()) == 0 and R.ahead_width(run) == 2
    assert R.ahead_width(run, 10**12) == 1 and R.ahead_width(run, 0, cap=1) == 1

    def read(t):
        return (run.read_height("w", t, 1.3), run.read_level("cref", t),
                run.read_level("th", t, 2), run.read_levels(["u"], t, [4])["u"][0])

    ref = {t: read(t) for t in range(4)}
    assert run._pool_uses == 0  # (single small levels: read here)
    got = dict(R.ahead(read, range(4), 2))
    assert run._pool_uses > 0 and run._vc.info()[1] == 0  # (in the readers; none cached)
    for t in ref:
        for a, b in zip(got[t], ref[t]):
            np.testing.assert_allclose(a, b, rtol=1e-6, atol=1e-6)


def test_tracking_ahead_matches_in_turn(reg, monkeypatch):
    """A track whose times are read ahead of the search (several at once, in the
    reader processes) is the track found one time after another."""
    from cm1view.core import track
    run = reg.get()[0]
    for metric in ("uh", "w"):
        opts = dict(metric=metric, zkm=1.0, radius=10.0, smooth=2.0, stop=None)
        a = track.track(run, 2, None, None, opts)
        with monkeypatch.context() as m:
            m.setattr(R, "ahead_width", lambda *a, **k: 0)
            b = track.track(run, 2, None, None, opts)
        assert sorted(a) == sorted(b) == list(range(len(run.times)))
        for t in a:
            assert (a[t]["x"], a[t]["y"]) == (b[t]["x"], b[t]["y"])
            assert abs(a[t]["value"] - b[t]["value"]) <= 1e-5 * max(1.0, abs(b[t]["value"]))


def test_close_stops_the_readers_and_the_next_read_starts_new(demo_run):
    """pool.close() (a program about to end) leaves no pool; a read after it starts
    another and gives the same values."""
    run = R.CM1Run(demo_run, cache_gb=1, workers=2)
    assert run.load_volumes(["th", "w"], 2)
    old = pool.get(2)
    pool.close()
    assert pool.size() == 0
    pool.close()  # (nothing to stop: no error)
    run.clear_cache()
    assert run.load_volumes(["th", "w"], 2)
    assert pool.get(2) is not old and pool.size() >= 2
    np.testing.assert_array_equal(run.volume("th", 2), run._read_volume_local("th", 2))
