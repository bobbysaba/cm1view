"""Headless check of the settings: config file load / save / precedence, run search,
track lookup, save folders, the figure bundle layout (_src/), the overwrite prompt,
the multi-run figure folder rule and the pressure-decomposition write switch.
Writes only into a temporary folder (its own config file too).
Usage: python tests/smoke20.py"""
import os
import subprocess
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="cm1view-smoke20-", dir=os.environ.get("TMPDIR") or None)
os.environ["CM1VIEW_CONFIG"] = os.path.join(TMP, "cfg", "config.toml")
for k in list(os.environ):
    if k.startswith("CM1VIEW_") and k != "CM1VIEW_CONFIG":
        del os.environ[k]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cm1view import config as C  # noqa: E402

PHD = "/glade/derecho/scratch/rasaba/phd"
TOR = f"{PHD}/southeast/rm_tor_125m"
NTOR = f"{PHD}/southeast/rm_ntor_125m"


def main():
    C.load()
    # ---- no file yet: defaults, setup required
    assert not C.exists() and C.needs_setup()
    assert C.get("runs_root") == [] and C.source("runs_root") == "default"
    assert C.get("cache_gb") == "auto" and C.get("allow_writes_to_output") is False
    sug = C.suggestions(TOR)
    print("suggestions:", {k: sug[k] for k in ("runs_root", "default_run", "cache_dir",
                                               "pdecomp_script")})
    assert sug["runs_root"] and os.path.isdir(sug["runs_root"][0])

    # ---- save, reload, precedence
    out = os.path.join(TMP, "out")
    C.save(dict(runs_root=[PHD], figures_dir=f"{out}/figs", exports_dir=f"{out}/data",
                cache_dir=f"{out}/cache", cache_gb="12", workers="auto"))
    assert C.exists() and not C.needs_setup(), C.problems()
    assert C.get("cache_gb") == 12.0 and C.source("cache_gb") == "config file"
    assert C.get("workers") == "auto" and C.cache_gb() == (12.0, "set")
    text = open(C.config_path()).read()
    assert "[paths]" in text and "# Where your runs live" in text
    os.environ["CM1VIEW_CACHE_GB"] = "20"
    assert C.get("cache_gb") == 20.0 and C.source("cache_gb").startswith("environment")
    C.override("cache_gb", 30, "--cache-gb")
    assert C.get("cache_gb") == 30.0 and C.source("cache_gb") == "command line (--cache-gb)"
    C._state["cli"].clear()
    del os.environ["CM1VIEW_CACHE_GB"]
    os.environ["CM1VIEW_PDECOMP"] = "/nonexistent.py"  # the old variable still works
    assert C.get("pdecomp_script") == "/nonexistent.py"
    assert "pdecomp_script" in C.problems()
    del os.environ["CM1VIEW_PDECOMP"]
    print("cache auto:", C.workers(), "| job memory %.0f GB" % C.job_memory_gb())

    # bad raw text is refused and leaves the file alone
    try:
        C.save_text("[server]\ncache_gb = [1, 2]\n")
        raise AssertionError("bad value accepted")
    except (ValueError, TypeError):
        pass
    assert C.get("runs_root") == [PHD]

    # ---- runs and tracks
    runs, complete = C.scan_runs()
    print(f"scan: {len(runs)} runs (complete={complete}):", [os.path.relpath(r, PHD)
                                                             for r in runs[:6]])
    assert TOR in runs and NTOR in runs
    tr = C.find_track(TOR)
    print("track:", tr)
    assert tr and tr.endswith("storm_tracks/rm_tor_125m.csv") or tr.endswith(
        "storm_tracks/southeast_rm_tor_125m.csv")
    C.save(dict(track_dirs=[os.path.join(TMP, "tracks")], track_patterns=["{name}_*.csv"]))
    os.makedirs(os.path.join(TMP, "tracks"))
    open(os.path.join(TMP, "tracks", "rm_tor_125m_v2.csv"), "w").close()
    assert C.find_track(TOR) == os.path.join(TMP, "tracks", "rm_tor_125m_v2.csv")
    assert C.find_track(NTOR) is None
    C.save(dict(track_dirs=["storm_tracks"], track_patterns=C.BY_NAME["track_patterns"]
                .default))
    assert C.run_key(TOR) == "southeast_rm_tor_125m"
    assert C.exports_dir(TOR, "series") == f"{out}/data/southeast_rm_tor_125m/series"

    # ---- the viewer
    from cm1view import app as A, figure as fg, pdecomp
    from cm1view.registry import Registry
    reg = Registry(TOR, 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    print("save boxes:", v.trk_path.value, "|", v.ser_path.value, "|", v.figed.path.value)
    assert v.trk_path.value == f"{out}/data/southeast_rm_tor_125m/tracks/meso_track.csv"
    assert v.ser_path.value == f"{out}/data/southeast_rm_tor_125m/series/series.nc"
    assert v.figed.path.value == f"{out}/figs/southeast_rm_tor_125m/figure"
    assert not pdecomp.writes_allowed() and v.pd_write.disabled and not v.pd_write.value

    # settings saved elsewhere: boxes still in the old default folder follow
    v.ser_path.value = os.path.join(TMP, "mine", "keep.nc")
    C.save(dict(exports_dir=f"{out}/data2", figures_dir=f"{out}/figs2",
                allow_writes_to_output=True))
    v._config_changed()  # (scheduled on the session's document in the browser)
    print("after save:", v.trk_path.value, "|", v.ser_path.value, "|", v.figed.path.value)
    assert v.trk_path.value == f"{out}/data2/southeast_rm_tor_125m/tracks/meso_track.csv"
    assert v.ser_path.value == os.path.join(TMP, "mine", "keep.nc")
    assert v.figed.path.value == f"{out}/figs2/southeast_rm_tor_125m/figure"
    assert pdecomp.writes_allowed() and not v.pd_write.disabled and v.pd_write.value

    # settings window: first-run form, check, save
    s = v.settings
    s.show(required=True)
    assert not s.modal.show_close_button and not s.cancel_btn.visible
    s.w["runs_root"].value = "/nonexistent/folder"
    s._save(None)
    assert "Fix these first" in s.msg.object and C.get("runs_root") == [PHD]
    s.w["runs_root"].value = PHD
    assert "found" in s.notes["runs_root"].object
    s.w["maxpix"].value = "1200"
    s._save(None)
    assert C.get("maxpix") == 1200 and not s.required
    s.show(flagged={"figures_dir": "x"})
    assert not s.more.collapsed and s.adv.collapsed and s.modal.show_close_button
    s.tabs.active = 1
    assert "[server]" in s.raw.value and not s.buttons.visible

    # track save: asks before overwriting
    v.fixes = __import__("cm1view.track", fromlist=["load"]).load(run, fg.find_track(TOR))
    v._on_save_track(None)
    assert os.path.isfile(v.trk_path.value) and not v.confirm.modal.open
    v._on_save_track(None)
    assert v.confirm.modal.open and "Replace" in v.confirm.text.object
    v.confirm._yes(None)  # (as the Overwrite button)
    assert not v.confirm.modal.open

    # ---- figure bundle: image + script on top, data + spec in _src/, script reruns
    ed = v.figed
    spec = ed.collect()
    data = ed.panel_data(spec)
    base = os.path.join(ed._fig_dir, "refl")
    paths = fg.save_bundle(spec, data, base, run)
    print("bundle:", {k: os.path.relpath(p, ed._fig_dir) for k, p in paths.items()})
    assert paths["data"] == os.path.join(ed._fig_dir, "_src", "refl_data.npz")
    assert all(os.path.isfile(p) for p in paths.values())
    os.remove(paths["image"])
    copy = os.path.join(TMP, "moved")
    subprocess.run(["cp", "-r", ed._fig_dir, copy], check=True)
    r = subprocess.run([sys.executable, os.path.join(copy, "refl.py")], capture_output=True,
                       text=True)
    print("script:", r.stdout.strip(), r.stderr.strip()[-300:])
    assert r.returncode == 0 and os.path.isfile(os.path.join(copy, "refl.png"))

    # ---- several runs: no folder of their own; the user chooses, then it's remembered
    ed.add_path.value = NTOR
    ed._add_run()
    assert len(ed.run_rows) == 2
    print("multi-run box:", repr(ed.path.value), "| save disabled:", ed.save_img.disabled)
    assert ed.path.value == "" and ed.save_img.disabled
    ed.path.value = os.path.join(TMP, "compare", "tor_vs_ntor")
    assert not ed.save_img.disabled
    ed._save(False)
    ed.v.pools["fig"].submit(lambda: None).result(timeout=600)
    assert C.state("last_multi_run_dir") == os.path.join(TMP, "compare")
    assert os.path.isfile(os.path.join(TMP, "compare", "tor_vs_ntor.png"))
    ed._remove_run(ed.run_rows[1])
    print("back to one run:", ed.path.value)
    assert ed.path.value == os.path.join(ed._fig_dir, "tor_vs_ntor")
    ed.add_path.value = NTOR
    ed._add_run()
    print("multi again:", ed.path.value)
    assert ed.path.value == os.path.join(TMP, "compare", "tor_vs_ntor")
    v.close()

    # ---- no run: the landing page
    from cm1view import app
    body, st = app._landing()
    assert st.modal is not None
    print("OK", TMP)


if __name__ == "__main__":
    main()
