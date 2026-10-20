import sys, time, base64, re
sys.path.insert(0, "/glade/work/rasaba/cm1view")
import numpy as np
from cm1view.registry import Registry
from cm1view import app as A, track as trk


def main():
    SP = sys.argv[1]
    reg = Registry("/glade/derecho/scratch/rasaba/phd/test/initiation/c", 20, 1)
    run, F = reg.get()
    v = A.Viewer(run, F)
    v.main()
    T0 = 48  # 14:08 in this run
    v.tslider.value = T0

    def wait(pred, tmax=900):
        t0 = time.time()
        while not pred() and time.time() - t0 < tmax:
            time.sleep(0.5)
        return time.time() - t0

    def tap(x, y, shift=False):
        v._on_tap(type("E", (), {"x": x, "y": y, "modifiers": {"shift": shift}})())

    def save_imgs(tag):
        objs = [v.skew_png.object, v.prof_png.object] if v.skew_png.visible else \
            [o.object for tab in v.snd_tabs.objects for o in tab.objects]
        for n, html in enumerate(objs):
            b = re.search(r"base64,([^\"]+)", html).group(1)
            open(f"{SP}/{tag}_{n}.png", "wb").write(base64.b64decode(b))

    print("modes:", list(v.mode.btns))
    uh, _ = trk.metric_field(run, T0, "uh")
    j, i = np.unravel_index(np.argmax(uh), uh.shape)
    x0, y0 = float(run.xh[i]) + 1.0, float(run.yh[j]) - 1.0
    print("click near UH max", x0, y0, "max", uh.max())

    # ---- track: limit the search to forward only, to keep the test short
    v.mode.set("Track")
    v.trk_dir.value = "forward"
    tap(x0, y0)
    dt = wait(lambda: v.trk_stop_btn.disabled)
    ts = sorted(v.fixes)
    print(f"track {dt:.0f}s: {len(ts)} fixes {run.time_label(ts[0])}..{run.time_label(ts[-1])}")
    print("status:", re.sub("<[^>]+>", "", v.trk_status.object))
    print("map line pts:", len(v.trk_line_src.data["x"]), "now marker:", v.trk_now_src.data)
    print("table cols:", list(v.trk_table.value.columns))
    v.trk_path.value = f"{SP}/out/test_track.csv"; v._on_save_track(None)
    print("save:", re.sub("<[^>]+>", "", v.trk_status.object)[-120:])
    v.trk_path.value = f"{SP}/out/test_track.txt"; v._on_save_track(None)
    print("download name:", v.trk_dl.filename, len(v._track_download().getvalue()), "bytes")

    # ---- correction click at a later time, near the track
    tc = ts[min(3, len(ts) - 1)]
    v.tslider.value = tc
    f = v.fixes[tc]
    before = dict(v.fixes)
    tap(f["x"] + 0.5, f["y"] + 0.5)
    wait(lambda: v.trk_stop_btn.disabled)
    kept = all(v.fixes.get(t) == before[t] for t in before if t < tc)
    print("correction kept earlier fixes:", kept, "n fixes:", len(v.fixes))
    # click far away -> new track (backward only)
    v.trk_dir.value = "backward"
    tap(f["x"] + 40, f["y"] + 40)
    wait(lambda: v.trk_stop_btn.disabled)
    print("far click -> new track fixes:", sorted(v.fixes)[:3], len(v.fixes))
    # restore the main track
    v.trk_dir.value = "forward"; v.tslider.value = T0; tap(x0, y0)
    wait(lambda: v.trk_stop_btn.disabled)
    print("restored:", len(v.fixes))

    # ---- storm-following sounding + pinning times + tracked motion
    v.mode.set("Sounding")
    v.storm_follow.value = True
    v.storm.value = "track"
    m = v.fixes[T0]
    tap(m["x"] + 8.0, m["y"] - 4.0)
    print(f"storm-following: {wait(lambda: not v.snd_col.loading):.1f}s", v.points,
          re.sub("<[^>]+>", "", v.snd_head.object))
    v._pin_time()
    v.tslider.value = T0 + 3
    v._refresh_panels()
    wait(lambda: not v.snd_col.loading)
    print("after pin + move:", v.points)
    print("labels:", [l for l, _, _ in v.results])
    print("storm motions used:", [tuple(np.round(r["kin"]["storm"], 1)) for _, _, r in v.results])
    print("map markers:", v.pt_src.data["x"], v.pt_src.data["y"])
    v.compare.value = "colors"; wait(lambda: not v.snd_col.loading); save_imgs("time")
    print("status:", re.sub("<[^>]+>", "", v.status.object))
    # point (not storm-following) pinned across time
    v.storm_follow.value = False
    tap(-30.0, -10.0); wait(lambda: not v.snd_col.loading)
    v._pin_time(); v.tslider.value = T0 - 5; v._refresh_panels()
    print(f"pt pinned: {wait(lambda: not v.snd_col.loading):.1f}s", [l for l, _, _ in v.results])
    v._on_clear_track(None)
    print("cleared:", v.fixes, v.points)
    print("ok")


if __name__ == "__main__":
    main()
