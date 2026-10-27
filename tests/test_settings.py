"""Settings: run search and the first-run guesses, the config file (defaults, saving,
precedence), track lookup and save folders, the settings window, and figure bundles."""
import os
import subprocess
import sys

import pytest

from cm1view import config, demo, registry
from cm1view.core import track as trk


def test_scan_skips_unreadable_links(tmp_path, demo_root):
    locked = tmp_path / "locked"
    (locked / "inside").mkdir(parents=True)
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(locked / "inside", root / "project")  # like links into projects you can't read
    os.symlink(os.path.join(demo_root, "demo"), root / "demo")
    locked.chmod(0)
    try:
        runs, complete = config.scan_runs([str(root)])
    finally:
        locked.chmod(0o755)
    assert sorted(os.path.basename(r) for r in runs) == ["supercell", "supercell_weak"]


def test_demo_runs_stay_out_of_recent_and_guesses(demo_run, tmp_path, monkeypatch):
    assert demo.is_demo(demo_run)
    registry.remember(demo_run)
    assert demo_run not in registry.recent_runs()
    # runs in unrelated trees: the guess falls back to the newest run's grandparent
    a = tmp_path / "phd" / "southeast" / "tor"
    a.mkdir(parents=True)
    monkeypatch.setattr(registry, "recent_runs", lambda: [str(a), "/opt", demo_run])
    monkeypatch.setattr(config, "exists", lambda: False)
    assert config.suggestions()["runs_root"] == [str(tmp_path / "phd")]


# ------------------------------------------------------------------ the config file

@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """No config file yet and no CM1VIEW_* variables; the session's file afterwards."""
    for k in list(os.environ):
        if k.startswith("CM1VIEW_") and k != "CM1VIEW_CONFIG":
            monkeypatch.delenv(k)
    old = config._state["path"]
    config.load(str(tmp_path / "cfg" / "config.toml"))
    yield tmp_path
    config._state["cli"].clear()
    config._state["path"] = old
    config.load()


def test_defaults_save_and_precedence(fresh, demo_root, monkeypatch):
    C = config
    assert not C.exists() and C.needs_setup()
    assert C.get("runs_root") == [] and C.source("runs_root") == "default"
    assert C.get("cache_gb") == "auto" and C.get("allow_writes_to_output") is False
    out = fresh / "out"
    C.save(dict(runs_root=[demo_root], figures_dir=f"{out}/figs", exports_dir=f"{out}/data",
                cache_dir=f"{out}/cache", cache_gb="12", workers="auto"))
    assert C.exists() and not C.needs_setup(), C.problems()
    assert C.get("cache_gb") == 12.0 and C.source("cache_gb") == "config file"
    assert C.get("workers") == "auto" and C.cache_gb() == (12.0, "set")
    text = open(C.config_path()).read()
    assert "[paths]" in text and "# Where your runs live" in text
    monkeypatch.setenv("CM1VIEW_CACHE_GB", "20")
    assert C.get("cache_gb") == 20.0 and C.source("cache_gb").startswith("environment")
    C.override("cache_gb", 30, "--cache-gb")
    assert C.get("cache_gb") == 30.0 and C.source("cache_gb") == "command line (--cache-gb)"
    C._state["cli"].clear()
    monkeypatch.delenv("CM1VIEW_CACHE_GB")
    monkeypatch.setenv("CM1VIEW_PDECOMP", "/nonexistent.py")  # the old variable still works
    assert C.get("pdecomp_script") == "/nonexistent.py" and "pdecomp_script" in C.problems()
    monkeypatch.delenv("CM1VIEW_PDECOMP")
    # bad raw text is refused and leaves the file alone
    with pytest.raises((ValueError, TypeError)):
        C.save_text("[server]\ncache_gb = [1, 2]\n")
    assert C.get("runs_root") == [demo_root]


def test_runs_tracks_and_save_folders(fresh, demo_root):
    C = config
    tor = os.path.join(demo_root, "demo", "supercell")
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    C.save(dict(runs_root=[demo_root], exports_dir=str(fresh / "data")))
    runs, _ = C.scan_runs()
    assert tor in runs and weak in runs
    assert C.find_track(tor) == os.path.join(demo_root, "storm_tracks", "demo_supercell.csv")
    # new tracks go where they would be found
    assert C.track_save_path(tor) == C.find_track(tor)
    tracks = fresh / "tracks"
    C.save(dict(track_dirs=[str(tracks)], track_patterns=["{name}_*.csv"]))
    tracks.mkdir()
    (tracks / "supercell_v2.csv").write_text("")
    assert C.find_track(tor) == str(tracks / "supercell_v2.csv")
    assert C.find_track(weak) is None
    C.save(dict(track_dirs=["nowhere"], track_patterns=["{name}.csv"]))
    assert C.track_save_path(tor) == os.path.join(C.exports_dir(tor, "tracks"),
                                                  "supercell.csv")
    assert C.run_key(tor) == "demo_supercell"
    assert C.exports_dir(tor, "series") == f"{fresh}/data/demo_supercell/series"


def test_viewer_follows_saved_settings(fresh, reg, demo_root):
    from cm1view.viewer import app as A
    from cm1view import pdecomp
    C = config
    out = fresh / "out"
    C.save(dict(runs_root=[demo_root], figures_dir=f"{out}/figs", exports_dir=f"{out}/data"))
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    try:
        assert v.ser_path.value == f"{out}/data/demo_supercell/series/series.nc"
        assert v.figed.path.value == f"{out}/figs/demo_supercell/figure"
        assert not pdecomp.writes_allowed() and v.pd_write.disabled and not v.pd_write.value
        # settings saved elsewhere: boxes still in the old default folder follow
        v.ser_path.value = str(fresh / "mine" / "keep.nc")
        C.save(dict(exports_dir=f"{out}/data2", figures_dir=f"{out}/figs2",
                    allow_writes_to_output=True))
        v._config_changed()  # (scheduled on the session's document in the browser)
        assert v.ser_path.value == str(fresh / "mine" / "keep.nc")
        assert v.figed.path.value == f"{out}/figs2/demo_supercell/figure"
        assert pdecomp.writes_allowed() and not v.pd_write.disabled and v.pd_write.value

        # the settings window: first-run form, check, save
        s = v.settings
        s.show(required=True)
        assert not s.modal.show_close_button and not s.cancel_btn.visible
        s.w["runs_root"].value = "/nonexistent/folder"
        s._save(None)
        assert "Fix these first" in s.msg.object and C.get("runs_root") == [demo_root]
        s.w["runs_root"].value = demo_root
        assert "found" in s.notes["runs_root"].object
        s.w["maxpix"].value = "1200"
        s._save(None)
        assert C.get("maxpix") == 1200 and not s.required
        s.show(flagged={"figures_dir": "x"})
        assert not s.more.collapsed and s.adv.collapsed and s.modal.show_close_button
        s.tabs.active = 1
        assert "[server]" in s.raw.value and not s.buttons.visible

        # saving a track asks before overwriting
        v.fixes = trk.load(run, C.find_track(run.path))
        v.trk_path.value = str(fresh / "t.csv")
        v._on_save_track(None)
        assert os.path.isfile(v.trk_path.value) and not v.confirm.modal.open
        v._on_save_track(None)
        assert v.confirm.modal.open and "Replace" in v.confirm.text.object
        v.confirm._yes(None)
        assert not v.confirm.modal.open
    finally:
        v.close()


def test_figure_bundle_runs_anywhere(fresh, reg, demo_root):
    """Image, script in scripts/, data and spec in _src/; the script redraws the
    image from a copied folder.  Several runs: no folder of their own until chosen."""
    from cm1view.viewer import app as A
    from cm1view.figures import spec as fg
    C = config
    C.save(dict(runs_root=[demo_root], figures_dir=str(fresh / "figs")))
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    try:
        ed = v.figed
        ed.auto.value = False
        spec = ed.collect()
        paths = fg.save_bundle(spec, ed.panel_data(spec), os.path.join(ed._fig_dir, "refl"),
                               run)
        assert paths["data"] == os.path.join(ed._fig_dir, "_src", "refl_data.npz")
        assert all(os.path.isfile(p) for p in paths.values())
        os.remove(paths["image"])
        copy = fresh / "moved"
        subprocess.run(["cp", "-r", ed._fig_dir, str(copy)], check=True)
        r = subprocess.run([sys.executable, str(copy / "scripts" / "refl.py")], capture_output=True,
                           text=True)
        assert r.returncode == 0, r.stderr[-500:]
        assert (copy / "refl.png").is_file()

        ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
        ed._add_run()
        assert len(ed.run_rows) == 2 and ed.path.value == "" and ed.save_img.disabled
        ed.path.value = str(fresh / "compare" / "tor_vs_ntor")
        assert not ed.save_img.disabled
        ed._save(False)
        ed.v.pools["fig"].submit(lambda: None).result(timeout=600)
        assert C.state("last_multi_run_dir") == str(fresh / "compare")
        assert (fresh / "compare" / "tor_vs_ntor.png").is_file()
        ed._remove_run(ed.run_rows[1])
        assert ed.path.value == os.path.join(ed._fig_dir, "tor_vs_ntor")
        ed.add_path.value = os.path.join(demo_root, "demo", "supercell_weak")
        ed._add_run()
        assert ed.path.value == str(fresh / "compare" / "tor_vs_ntor")
    finally:
        v.close()


def test_landing_page_without_a_run():
    from cm1view.viewer import app
    _, st = app._landing()
    assert st.modal is not None
