"""Settings: run search and the first-run guesses."""
import os

from cm1view import config, demo, registry


def test_scan_skips_unreadable_links(tmp_path, demo_root):
    locked = tmp_path / "locked"
    (locked / "inside").mkdir(parents=True)
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(locked / "inside", root / "project")  # like /glade/p/univ/... links
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
