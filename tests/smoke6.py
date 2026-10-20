"""Headless checks for: updraft tracking (notebook method), area soundings, expanded
panel, section A/B labels, 3D switch visibility, streamline pick + sampling.
Usage: python tests/smoke6.py OUTDIR"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from cm1view.registry import Registry
from cm1view import app as A, track as trk


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    reg = Registry("/glade/derecho/scratch/rasaba/phd/test/initiation/c", 20, 1)
    run, F = reg.get()
    v = A.Viewer(run, F)
    v.main()
    T0 = 48
    v.tslider.value = T0
    txt = lambda h: re.sub("<[^>]+>", "", h or "")  # noqa: E731

    def wait(pred, tmax=900):
        t0 = time.time()
        while not pred() and time.time() - t0 < tmax:
            time.sleep(0.3)
        return time.time() - t0

    # ---- 3D switch hidden until a region exists
    print("3D switch visible at start:", v.ws_group.visible)

    # ---- tracking: default preset = smoothed w at 1 km
    o = v._trk_opts()
    print("track defaults:", o["metric"], o["zkm"], o["smooth"], o["kernel"], o["stop"])
    v.trk_dir.value = "forward"
    v._show_panel(True, 2)
    v.request_track(None, None)  # Find strongest
    dt = wait(lambda: v.trk_stop_btn.disabled and v.fixes)
    ts = sorted(v.fixes)
    print(f"find strongest: {len(ts)} fixes {run.time_label(ts[0])}->{run.time_label(ts[-1])} "
          f"in {dt:.0f}s; start {v.fixes[ts[0]]['x']:.1f},{v.fixes[ts[0]]['y']:.1f}")
    steps = [np.hypot(v.fixes[b]["x"] - v.fixes[a]["x"], v.fixes[b]["y"] - v.fixes[a]["y"])
             for a, b in zip(ts, ts[1:])]
    print("max step between fixes (km):", round(max(steps), 2) if steps else None)
    print(txt(v.trk_status.object))
    print(trk.to_text(run, v.fixes, v.trk_spec).split("\n")[4])
    # whole-domain search, as in the notebook
    v.trk_whole.value = True
    print("radius disabled with whole:", v.trk_radius.disabled)
    v.request_track(None, None)
    wait(lambda: v.trk_stop_btn.disabled and v.fixes)
    ts2 = sorted(v.fixes)
    steps2 = [np.hypot(v.fixes[b]["x"] - v.fixes[a]["x"], v.fixes[b]["y"] - v.fixes[a]["y"])
              for a, b in zip(ts2, ts2[1:])]
    print(f"whole-domain: {len(ts2)} fixes, max step {max(steps2):.2f} km" if steps2 else
          "whole-domain: one fix")
    v.trk_whole.value = False
    fx = v.fixes[T0] if T0 in v.fixes else v.fixes[ts2[0]]
    v.tslider.value = T0

    # ---- area soundings: drag (replace), shift-drag (add)
    v.mode.set("Area sounding")
    print("area mode drag tool is box select:", v.fig.toolbar.active_drag is v.bsel)
    ev = lambda x0, x1, y0, y1: type("E", (), {  # noqa: E731
        "final": True, "geometry": {"type": "rect", "x0": x0, "x1": x1, "y0": y0, "y1": y1}})()
    cx, cy = fx["x"], fx["y"]
    v._on_pan_start(type("E", (), {"modifiers": {"shift": False}})())
    v._on_select(ev(cx + 5, cx + 15, cy - 10, cy))
    v._on_pan_start(type("E", (), {"modifiers": {"shift": True}})())
    v._on_select(ev(cx - 20, cx - 10, cy - 5, cy + 5))
    print("points:", v.points)
    print("box quads on map:", len(v.pbox_src.data["x"]))
    wait(lambda: not v.snd_col.loading)
    print("sounding head:", txt(v.snd_head.object))
    print("skew src svg:", v.skew_png.src[:26], len(v.skew_png.src) // 1000, "kB")

    # ---- expanded panel
    v.skew_png.clicks += 1
    print("after image click: full", v.full, "map visible", v.map_area.visible,
          "interactive", v.skew_png.interactive, "button", v.full_btn.name)
    v.compare.value = "tabs"
    wait(lambda: v.snd_tabs.visible and not v.snd_col.loading)
    print("tabs:", v._snd_tab_names, "tab images interactive:",
          [z.interactive for z in v._zoom_images()])
    v._set_full(False)
    print("collapsed: map visible", v.map_area.visible, "interactive", v.skew_png.interactive)
    v.compare.value = "lines"

    # ---- cross-section A/B labels
    v.mode.set("Cross-section")
    tap = lambda x, y: v._on_tap(type("E", (), {"x": x, "y": y, "modifiers": {}})())  # noqa
    tap(cx - 15, cy)
    tap(cx + 15, cy + 5)
    wait(lambda: "long" in (v.xs_status.object or ""))
    print("section:", txt(v.xs_status.object))
    print("A/B labels:", [(a.text, round(a.x, 2), a.visible) for a in v.xs_lab])

    # ---- 3D with streamlines, then pick one
    v.mode.set("3D region")
    v._on_select(ev(cx - 12, cx + 12, cy - 12, cy + 12))
    print("3D switch visible after region:", v.ws_group.visible, "workspace", v.workspace.value)
    v.st_on.value = True
    v.st_dir.value = "both"
    wait(lambda: v._s3 is not None and v._s3["stream"] is not None
         and "triangles" in (v.v3_status.object or ""))
    print("3D:", txt(v.v3_status.object))
    st = v._s3["stream"]
    print("streamlines:", st["n"], "segs", st["segs"].shape,
          "seed inside line:", bool(np.all((st["segs"][:, 2] >= st["segs"][:, 0])
                                           & (st["segs"][:, 2] < st["segs"][:, 1]))))
    idx, _ = v._trace("stream")
    a, b, sd = st["segs"][len(st["segs"]) // 2]
    v.plot3d.click_data = {"points": [{"curveNumber": idx, "pointNumber": int(a + 3)}]}
    print("selected line:", v._sl_line, "card visible:", v.sl_card.visible)
    wait(lambda: len(v.sl_src.data["s"]) > 0)
    _, hl = v._trace("selected")
    print("highlight points:", len(hl.x), "== segment", b - a)
    s_ = np.asarray(v.sl_src.data["s"])
    print(f"w along line: s {s_[0]:.1f}..{s_[-1]:.1f} km, max w "
          f"{np.nanmax(v.sl_src.data['v']):.1f}, label {v.sl_fig.yaxis[0].axis_label}")
    print(txt(v.sl_info.object))
    for name in ("_ws", "thpert", "hdiv"):
        if name.startswith("_") or name in F:
            v.sl_field.value = name
            n0 = v.gen["sl"]
            wait(lambda: "Sampling" not in (v.sl_info.object or "") and v.gen["sl"] == n0)
            vals = np.asarray(v.sl_src.data["v"])
            print(f"  {name}: {v.sl_fig.yaxis[0].axis_label}  range "
                  f"{np.nanmin(vals):.4g}..{np.nanmax(vals):.4g}")
    # re-render keeps the same streamline (same seed)
    seed = v._sl_seed
    v.request_3d()
    wait(lambda: v.gen["3d"] and "Rendering" not in (v.v3_status.object or ""))
    time.sleep(1)
    print("after re-render: same seed", v._sl_seed == seed, "line", v._sl_line)
    v._select_line(None)
    print("cleared: card", v.sl_card.visible, "seed", v._sl_seed)
    v._on_clear_points(None)
    print("after clear: 3D switch", v.ws_group.visible, "workspace", v.workspace.value)
    print("ok")


if __name__ == "__main__":
    main()
