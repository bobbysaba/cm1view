import sys, time, re
sys.path.insert(0, "/glade/work/rasaba/cm1view")
import numpy as np
from cm1view.registry import Registry
from cm1view import app as A


def main():
    SP = sys.argv[1]
    reg = Registry("/glade/derecho/scratch/rasaba/phd/test/initiation/c", 20, 1)
    run, F = reg.get()
    v = A.Viewer(run, F); v.main()
    T0 = 48; v.tslider.value = T0

    def wait(pred, tmax=600):
        t0 = time.time()
        while not pred() and time.time() - t0 < tmax:
            time.sleep(0.3)
        return time.time() - t0

    def tap(x, y):
        v._on_tap(type("E", (), {"x": x, "y": y, "modifiers": {}})())

    txt = lambda h: re.sub("<[^>]+>", "", h)
    v.mode.set("Track")
    v.trk_how.value = "manual"
    print("manual: snap", v.trk_snap.value, "dir visible", v.trk_dir.visible, "advance", v.trk_advance.visible)
    clicks = [(-31.7, -21.4), (-31.5, -21.2), (-31.3, -20.9)]
    for x, y in clicks:
        tap(x, y)
    print("after 3 clicks, t =", v.t, "fixes:", sorted(v.fixes))
    wait(lambda: all(np.isfinite(f["value"]) for f in v.fixes.values()))
    for t, f in sorted(v.fixes.items()):
        print(f"  {run.time_label(t)} x={f['x']:.2f} y={f['y']:.2f} value={f['value']:.0f} {f['source']}")
    # snapped manual fix
    v.trk_snap.value = True; v.trk_advance.value = False
    tap(-30.0, -19.5)
    t = v.t; wait(lambda: np.isfinite(v.fixes[t]["value"]))
    f = v.fixes[t]; print(f"snapped at {run.time_label(t)}: {f['x']:.2f}, {f['y']:.2f} value {f['value']:.0f}")
    # delete
    print("delete enabled:", not v.trk_del.disabled); v._on_delete_fix(None)
    print("after delete:", sorted(v.fixes), txt(v.trk_status.object))
    # save -> load round trip
    v.trk_path.value = f"{SP}/out/manual.csv"; v._on_save_track(None)
    print(open(f"{SP}/out/manual.csv").read().split("\n")[-5:])
    saved = {t: (round(f["x"], 3), round(f["y"], 3), f["source"]) for t, f in v.fixes.items()}
    v._on_load_track(None)
    loaded = {t: (round(f["x"], 3), round(f["y"], 3), f["source"]) for t, f in v.fixes.items()}
    print("round trip equal:", saved == loaded)
    # hand-written whitespace file, ground-relative + hms
    v.trk_path.value = f"{SP}/out/handmade.txt"; v._on_load_track(None)
    print("handmade:", {run.time_label(t): (round(f["x"], 2), round(f["y"], 2), f["source"]) for t, f in v.fixes.items()})
    print(txt(v.trk_status.object))
    # bad file
    v.trk_path.value = f"{SP}/out/nope.csv"; v._on_load_track(None); print(txt(v.trk_status.object))
    # mix: auto-track forward from the last hand fix, keeping hand fixes before it
    v.trk_how.value = "auto"; v.trk_snap.value = True
    v.tslider.value = 52; tap(-31.8, -19.6)
    wait(lambda: v.trk_stop_btn.disabled)
    print("mixed sources:", [(t, v.fixes[t]["source"]) for t in sorted(v.fixes)][:6], len(v.fixes))
    v.trk_path.value = f"{SP}/out/mixed.txt"; v._on_save_track(None)
    print(open(f"{SP}/out/mixed.txt").read().split("\n")[10:15])
    print("ok")


if __name__ == "__main__":
    main()
