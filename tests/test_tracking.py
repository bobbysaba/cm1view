"""Storm tracking: automatic (nearest core / whole domain), click corrections, hand-placed
fixes, save / load, storm-following soundings. Truth = the demo's storm_tracks CSV."""
import os

import numpy as np

from cm1view.core import track as trk
from conftest import tap, txt, wait


def truth(demo_root, run):
    return trk.load(run, os.path.join(demo_root, "storm_tracks", "demo_supercell.csv"))


def steps(fixes):
    ts = sorted(fixes)
    return [np.hypot(fixes[b]["x"] - fixes[a]["x"], fixes[b]["y"] - fixes[a]["y"])
            for a, b in zip(ts, ts[1:])]


def test_uh_metric_peaks_at_the_storm(reg, demo_root):
    run, _ = reg.get()
    uh, _ = trk.metric_field(run, 4, "uh")
    j, i = np.unravel_index(np.argmax(uh), uh.shape)
    ref = truth(demo_root, run)[4]
    assert uh.max() > 100
    assert np.hypot(run.xh[i] - ref["x"], run.yh[j] - ref["y"]) < 2.0


def test_snap_without_weighting_finds_the_maximum(viewer):
    v = viewer
    run = v.run
    v.trk_how.value, v.trk_snap.value = "manual", True
    o = dict(v._trk_opts(), nearest=False)
    f, _ = trk.metric_field(run, 4, o["metric"], o["zkm"])
    j, i = np.unravel_index(np.nanargmax(f), f.shape)
    fx = trk.place(run, 4, run.xh[i] + 2.0, run.yh[j] + 2.0, o)
    assert (fx["x"], fx["y"]) == (run.xh[i], run.yh[j]) and fx["source"] == "manual"


def test_find_strongest_follows_the_storm(viewer, demo_root):
    v = viewer
    run = v.run
    v._show_panel(True, 2)
    v.request_track(None, None)  # Find strongest
    wait(lambda: v.trk_stop_btn.disabled and v.fixes, msg="track")
    ref = truth(demo_root, run)
    assert sorted(v.fixes) == sorted(ref)
    for t, f in v.fixes.items():
        assert np.hypot(f["x"] - ref[t]["x"], f["y"] - ref[t]["y"]) < 0.75, t
        assert f["source"] == "auto"
    u, vv = np.mean([m for m in trk.motion(run, v.fixes).values()], axis=0)
    assert abs(u - 15.0) < 1.5 and abs(vv - 3.0) < 1.5
    assert "fixes" in txt(v.trk_status.object)
    assert len(v.trk_line_src.data["x"]) == len(v.fixes)
    assert "mean motion" in txt(v.trk_status.object)
    lines = trk.to_text(run, v.fixes, v.trk_spec).split("\n")
    assert lines[0] == "# cm1view mesocyclone track"
    assert sum(1 for ln in lines if ln and not ln.startswith("#")) == len(v.fixes) + 1


def test_whole_domain_search(viewer):
    v = viewer
    v.trk_whole.value = True
    assert v.trk_radius.disabled
    v.request_track(None, None)
    wait(lambda: v.trk_stop_btn.disabled and v.fixes, msg="track")
    assert len(v.fixes) == 9 and max(steps(v.fixes)) < 2.0


def test_pressure_low_and_any_field(viewer, demo_root):
    """Min p′ follows the meso; 'any field' at its max / min matches the presets."""
    v = viewer
    run = v.run
    v.trk_metric.value = "pmin"
    assert v.trk_stop.name == "Stop above" and v.trk_stop.value < 0
    v.request_track(None, None)
    wait(lambda: v.trk_stop_btn.disabled and v.fixes, msg="track")
    ref = truth(demo_root, run)
    assert sorted(v.fixes) == sorted(ref)
    for t, f in v.fixes.items():
        assert np.hypot(f["x"] - ref[t]["x"], f["y"] - ref[t]["y"]) < 1.5, t
        assert f["value"] < 0
    assert "minimum of p′" in trk.to_text(run, v.fixes, v.trk_spec, fields=v.F)
    pmin = trk.place(run, 4, ref[4]["x"] + 1, ref[4]["y"], dict(v.trk_spec, snap=True),
                     fields=v.F)
    v.trk_metric.value = "field"
    assert v.trk_field.visible and v.trk_stop.value is None
    v.trk_field.value, v.trk_sense.value = "prspert", "min"
    o = dict(v._trk_opts(), radius=v.trk_spec["radius"], smooth=v.trk_spec["smooth"],
             kernel=v.trk_spec["kernel"], snap=True)
    other = trk.place(run, 4, ref[4]["x"] + 1, ref[4]["y"], o, fields=v.F)
    assert (other["x"], other["y"], other["value"]) == (pmin["x"], pmin["y"], pmin["value"])
    assert trk.column(o) == "min_prspert_1km"


def test_centroid_fix_and_time_window(viewer, demo_root):
    v = viewer
    run = v.run
    ref = truth(demo_root, run)
    v.trk_fix.value = "centroid"
    assert v.trk_cut.visible
    v.tslider.value = 4
    v.trk_from.value, v.trk_to.value = 2, 6
    v.request_track(None, None)
    wait(lambda: v.trk_stop_btn.disabled and v.fixes, msg="track")
    assert sorted(v.fixes) == [2, 3, 4, 5, 6]
    for t, f in v.fixes.items():
        assert np.hypot(f["x"] - ref[t]["x"], f["y"] - ref[t]["y"]) < 1.5, t
    # a centroid is not tied to grid points
    assert any(f["x"] not in run.xh for f in v.fixes.values())
    head = trk.to_text(run, v.fixes, v.trk_spec)
    assert "centroid" in head and f"{run.time_label(2)} – {run.time_label(6)}" in head
    # a click outside the window is refused
    v.tslider.value = 8
    v.request_track(None, None)
    assert "outside the From–To window" in txt(v.trk_status.object)


def test_click_track_correction_and_new_track(viewer, demo_root):
    v = viewer
    ref = truth(demo_root, v.run)
    v.mode.set("Track")
    tap(v, ref[1]["x"] + 1.0, ref[1]["y"] - 1.0)
    wait(lambda: v.trk_stop_btn.disabled and v.fixes, msg="track")
    assert len(v.fixes) == 9
    # a correction click near the track at a later time keeps the earlier fixes
    v.tslider.value = 4
    before = dict(v.fixes)
    tap(v, v.fixes[4]["x"] + 0.5, v.fixes[4]["y"] + 0.5)
    wait(lambda: v.trk_stop_btn.disabled, msg="correction")
    assert all(v.fixes[t] == before[t] for t in before if t < 4)
    # a click far away starts a new track (on the second cell, backward only; it is
    # below the stop threshold before t = 4, so the track ends there)
    v.trk_from.value, v.trk_to.value = 0, "click"
    tap(v, ref[4]["x"] + 16.0, ref[4]["y"] + 14.0)
    wait(lambda: v.trk_stop_btn.disabled, msg="new track")
    assert 4 in v.fixes and max(v.fixes) == 4
    assert all(np.hypot(f["x"] - ref[t]["x"], f["y"] - ref[t]["y"]) > 8 for t, f in
               v.fixes.items())
    v._on_clear_track(None)
    assert not v.fixes


def test_manual_fixes_delete_save_load(viewer, demo_root, tmp_path):
    v = viewer
    ref = truth(demo_root, v.run)
    v.mode.set("Track")
    v.trk_how.value = "manual"
    assert not v.trk_from.visible and v.trk_advance.visible
    for t in (1, 2, 3):  # each click advances the time
        tap(v, ref[t]["x"] + 0.3, ref[t]["y"])
    assert v.t == 4 and sorted(v.fixes) == [1, 2, 3]
    wait(lambda: all(np.isfinite(f["value"]) for f in v.fixes.values()), msg="values")
    assert {f["source"] for f in v.fixes.values()} == {"manual"}
    # a snapped fix moves toward the core (the nearest-core weighting stops it partway)
    v.trk_snap.value, v.trk_advance.value = True, False
    tap(v, ref[4]["x"] + 2.0, ref[4]["y"] + 2.0)
    wait(lambda: np.isfinite(v.fixes[4]["value"]), msg="snapped value")
    d = np.hypot(v.fixes[4]["x"] - ref[4]["x"], v.fixes[4]["y"] - ref[4]["y"])
    assert d < np.hypot(2.0, 2.0) - 0.5
    assert not v.trk_del.disabled
    v._on_delete_fix(None)
    assert sorted(v.fixes) == [1, 2, 3]
    # csv round trip, text export, missing file
    v.trk_path.value = str(tmp_path / "manual.csv")
    v._on_save_track(None)
    saved = {t: (round(f["x"], 3), round(f["y"], 3), f["source"]) for t, f in v.fixes.items()}
    v._on_load_track(None)
    assert saved == {t: (round(f["x"], 3), round(f["y"], 3), f["source"])
                     for t, f in v.fixes.items()}
    v.trk_path.value = str(tmp_path / "manual.txt")
    v._on_save_track(None)
    assert (tmp_path / "manual.txt").read_text().count("\n") > 3
    v.trk_path.value = str(tmp_path / "nope.csv")
    v._on_load_track(None)
    assert "nope.csv" in txt(v.trk_status.object)


def test_load_ground_relative_hms_file(viewer, tmp_path):
    v = viewer
    run = v.run
    p = tmp_path / "hand.txt"
    rows = ["# hand-made", "time_hms x_ground_km y_ground_km"]
    for t in (2, 3):
        s = run.times[t]
        rows.append(f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:00 "
                    f"{5 + run.umove * s / 1000:.3f} {-2 + run.vmove * s / 1000:.3f}")
    p.write_text("\n".join(rows) + "\n")
    v.trk_path.value = str(p)
    v._on_load_track(None)
    assert sorted(v.fixes) == [2, 3]
    assert all(abs(f["x"] - 5) < 1e-3 and abs(f["y"] + 2) < 1e-3 and f["source"] == "loaded"
               for f in v.fixes.values())


def test_storm_following_pinned_sounding(viewer, demo_root):
    v = viewer
    ref = truth(demo_root, v.run)
    v.trk_path.value = os.path.join(demo_root, "storm_tracks", "demo_supercell.csv")
    v._on_load_track(None)
    assert sorted(v.fixes) == sorted(ref)
    v.mode.set("Sounding")
    v.storm_follow.value = True
    v.storm.value = "track"
    tap(v, ref[1]["x"] + 8.0, ref[1]["y"] - 4.0)
    wait(lambda: not v.snd_col.loading and v.results, msg="sounding")
    assert v.points[0][0] == "trk"
    v._pin_time()
    v.tslider.value = 3
    v._refresh_panels()
    wait(lambda: not v.snd_col.loading and len(v.results) == 2, msg="pinned soundings")
    storms = [tuple(np.round(r["kin"]["storm"], 0)) for _, _, r in v.results]
    assert all(abs(s[0] - 15) <= 2 and abs(s[1] - 3) <= 2 for s in storms), storms
