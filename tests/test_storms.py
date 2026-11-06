"""Several storms per track file (a 'storm' column) and storm motion fitted over a
window of track (core.track; T1 of the WoFS viewer plan).  A stand-in run object: no
model output needed."""
import numpy as np
import pytest

from cm1view.core import track as trk

OPTS = dict(metric="uh", zkm=1.0, radius=5.0, smooth=1.0, kernel="box", stop=50.0)


class FakeRun:
    def __init__(self, nt=13, dt=300.0, umove=0.0, vmove=0.0, window=0.0):
        self.path = "/nowhere/exp/mem01"
        self.times = np.arange(nt) * dt
        self.files = [f"/nowhere/out_{t:03d}.nc" for t in range(nt)]
        self.umove, self.vmove, self.track_window = umove, vmove, window

    def time_label(self, t):
        s = int(self.times[t])
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def line(run, x0, y0, u, v, ts, value=100.0, jitter=0.0, seed=0):
    """Fixes of a storm moving at (u, v) m/s on the grid, optionally jittered (km)."""
    rng = np.random.default_rng(seed)
    out = {}
    for t in ts:
        s = run.times[t]
        dx, dy = rng.normal(0, jitter, 2) if jitter else (0.0, 0.0)
        out[t] = dict(x=x0 + u * s / 1000 + dx, y=y0 + v * s / 1000 + dy,
                      value=value + t, source="auto")
    return out


@pytest.fixture(autouse=True)
def window(monkeypatch):
    """Sets the track_motion_window setting (minutes or auto); auto to begin with."""
    def put(v):
        monkeypatch.setenv("CM1VIEW_TRACK_MOTION_WINDOW", v)
    put("auto")
    return put


def test_one_storm_file_has_no_storm_column(tmp_path):
    run = FakeRun()
    fx = line(run, 10, 20, 10, 5, range(3, 8))
    p = trk.save(run, fx, OPTS, str(tmp_path / "a.csv"))
    head = [ln for ln in open(p) if not ln.startswith("#")][0]
    assert not head.startswith("storm,")
    assert trk.storms(p) == []
    back = trk.load(run, p)
    assert sorted(back) == list(range(3, 8))
    assert trk.load(run, p, storm="whatever") == back  # (one storm whatever is asked)
    assert list(trk.load_all(run, p)) == [""]


@pytest.mark.parametrize("ext", ["csv", "txt"])
def test_storms_saved_into_one_file_keep_each_other(tmp_path, ext):
    run = FakeRun()
    a = line(run, 10, 20, 10, 5, range(2, 9))
    b = line(run, -30, 0, 15, 0, range(5, 12), value=0.5)
    p = str(tmp_path / f"member.{ext}")
    trk.save(run, a, OPTS, p, storm="north cell")  # (the space becomes "_")
    trk.save(run, b, dict(OPTS, metric="zeta"), p, storm="2")
    assert trk.storms(p) == ["north_cell", "2"]
    ga, gb = trk.load(run, p, "north cell"), trk.load(run, p, 2)
    assert sorted(ga) == list(range(2, 9)) and sorted(gb) == list(range(5, 12))
    assert all(abs(ga[t]["x"] - a[t]["x"]) < 1e-3 for t in a)
    assert all(abs(gb[t]["y"] - b[t]["y"]) < 1e-3 for t in b)
    # each storm keeps its own value column (uh_2_5km for one, zeta_1km for the other)
    assert all(ga[t]["value"] == pytest.approx(a[t]["value"]) for t in a)
    assert all(gb[t]["value"] == pytest.approx(b[t]["value"]) for t in b)
    assert trk.load(run, p) == ga  # (no storm named: the first)
    # re-saving the first storm replaces only its rows and keeps its place
    a2 = {t: dict(f, x=f["x"] + 1) for t, f in a.items() if t < 6}
    trk.save(run, a2, OPTS, p, storm="north_cell")
    assert trk.storms(p) == ["north_cell", "2"]
    assert sorted(trk.load(run, p, "north_cell")) == [2, 3, 4, 5]
    assert sorted(trk.load(run, p, "2")) == list(range(5, 12))
    every = trk.load_all(run, p)
    assert list(every) == ["north_cell", "2"] and sorted(every["2"]) == sorted(b)
    with pytest.raises(ValueError, match="no storm 'nope'"):
        trk.load(run, p, "nope")


def test_hand_made_file_with_numbered_storms(tmp_path):
    run = FakeRun()
    p = tmp_path / "hand.csv"
    p.write_text("# two storms\nstorm,time_s,x_km,y_km\n"
                 "1,600,0,0\n1,900,1,0\n7,600,50,50\n7,900,50,52\n")
    assert trk.storms(str(p)) == ["1", "7"]
    s7 = trk.load(run, str(p), "7")
    assert sorted(s7) == [2, 3] and s7[3]["y"] == 52
    assert np.isnan(s7[2]["value"])


def test_saving_a_named_storm_over_a_one_storm_file_replaces_it(tmp_path):
    run = FakeRun()
    p = str(tmp_path / "t.csv")
    trk.save(run, line(run, 0, 0, 10, 0, range(4)), OPTS, p)
    trk.save(run, line(run, 5, 5, 10, 0, range(4, 8)), OPTS, p, storm="A")
    assert trk.storms(p) == ["A"]
    assert sorted(trk.load(run, p)) == list(range(4, 8))


def test_motion_window_steadies_a_jumpy_track():
    run = FakeRun(nt=25, umove=3.0, vmove=-2.0)
    fx = line(run, 0, 0, 12.0, 6.0, range(25), jitter=0.6, seed=3)
    raw = trk.motion(run, fx, window=0)
    fit = trk.motion(run, fx, window=1800)
    true = np.array([15.0, 4.0])  # grid motion + umove, vmove
    err = {k: np.mean([np.hypot(*(np.array(m[t]) - true)) for t in range(3, 22)])
           for k, m in (("raw", raw), ("fit", fit))}
    assert err["fit"] < 0.5 * err["raw"]
    # a straight track gives its own motion either way, ends included
    st = line(run, 0, 0, 12.0, 6.0, range(25))
    for m in (trk.motion(run, st, 0), trk.motion(run, st, 1800)):
        assert all(np.allclose(m[t], true, atol=1e-6) for t in (0, 12, 24))


def test_motion_window_follows_the_setting_and_the_run(window):
    jumpy = line(FakeRun(nt=25), 0, 0, 12.0, 6.0, range(25), jitter=0.6, seed=3)
    cm1, wofs = FakeRun(nt=25), FakeRun(nt=25, window=1800.0)
    assert trk.motion_window(cm1) == 0.0 and trk.motion_window(wofs) == 1800.0
    assert trk.motion(cm1, jumpy) == trk.motion(cm1, jumpy, 0)
    assert trk.motion(wofs, jumpy) == trk.motion(wofs, jumpy, 1800)
    window("20")
    assert trk.motion_window(cm1) == 1200.0 and trk.motion_window(wofs) == 1200.0
    window("0")
    assert trk.motion(wofs, jumpy) == trk.motion(wofs, jumpy, 0)


def test_wofs_runs_fit_motion_over_30_min():
    from cm1view.core.run import CM1Run, Run
    from cm1view.core.wofs import WoFSRun
    assert Run.track_window == 0.0 and CM1Run.track_window == 0.0
    assert WoFSRun.track_window == 1800.0


def test_export_reads_the_named_storm(tmp_path):
    from cm1view.core import export
    run = FakeRun()
    p = str(tmp_path / "two.csv")
    trk.save(run, line(run, 0, 0, 10, 0, range(13)), OPTS, p, storm="A")
    trk.save(run, line(run, 0, 0, 0, 20, range(13)), OPTS, p, storm="B")
    sa, _ = export.storm_motion(run, p)
    sb, note = export.storm_motion(run, p, "B")
    assert np.allclose(sa(5), (10, 0)) and np.allclose(sb(5), (0, 20))
    assert "13 of 13" in note
