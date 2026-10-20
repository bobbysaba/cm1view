"""Headless checks: pan a zoomed sounding graphic (skew-T, hodograph, profile).
Usage: python tests/smoke12.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cm1view.registry import Registry
from cm1view import app as A

RUN = "/glade/derecho/scratch/rasaba/phd/test/initiation/c"


def wait(pred, tmax=600):
    t0 = time.time()
    while not pred() and time.time() - t0 < tmax:
        time.sleep(0.2)
    return time.time() - t0


def main():
    reg = Registry(RUN, 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F)
    v.main()
    v.tslider.value = 48
    v.mode.set("Sounding")
    v._on_tap(type("E", (), {"x": -25.0, "y": -22.0, "modifiers": {}})())
    wait(lambda: v.skew_png.src and not v.snd_col.loading)
    v._set_full(True)

    def send(z, name, vals):
        d = z.done
        setattr(z, name, list(vals) + [time.time()])
        wait(lambda: z.done > d, 60)

    send(v.skew_png, "box", (0.10, 0.45, 0.35, 0.92))
    s0 = v.snd_lim["skew"]
    print("skew after box:", [round(x, 1) for x in s0])
    # content dragged right and down -> colder temperatures and higher levels come in
    send(v.skew_png, "pan", (0.3, 0.6, 0.05, 0.05))
    s1 = v.snd_lim["skew"]
    print("skew after pan:", [round(x, 1) for x in s1])
    assert s1[0] < s0[0] and s1[1] < s0[1], "T range should shift colder"
    assert s1[2] < s0[2] and s1[3] < s0[3], "p range should shift upward (lower p)"
    w0, w1 = s0[1] - s0[0], s1[1] - s1[0]
    assert abs(w1 - w0) < 0.02 * w0, "pan keeps the T width"
    fig = v._figs[v.skew_png]
    print("drawn skew ylim:", [round(x) for x in fig.cv_axes["skew"].get_ylim()])

    # hodograph: pan without a previous zoom, content dragged left -> larger u
    hb = fig.cv_axes["hodo"].bbox
    W, H = fig.bbox.width, fig.bbox.height
    cx, cy = (hb.x0 + hb.x1) / 2 / W, 1 - (hb.y0 + hb.y1) / 2 / H
    u0 = fig.cv_axes["hodo"].get_xlim()
    send(v.skew_png, "pan", (cx, cy, -0.05, 0.0))
    h1 = v.snd_lim["hodo"]
    print("hodo xlim before", [round(x, 1) for x in u0], "after", [round(x, 1) for x in h1[:2]])
    assert h1[0] > u0[0] and h1[1] > u0[1]

    # profile panel: content dragged up -> lower heights come in
    send(v.prof_png, "box", (0.30, 0.30, 0.45, 0.70))
    z0 = v.snd_lim["prof_z"]
    send(v.prof_png, "pan", (0.37, 0.5, 0.0, -0.05))
    z1 = v.snd_lim["prof_z"]
    print("prof z before", [round(x, 2) for x in z0], "after", [round(x, 2) for x in z1])
    assert z1[0] < z0[0] and z1[1] < z0[1]

    # pan outside every panel: answered with done, limits unchanged
    lim = dict(v.snd_lim)
    send(v.skew_png, "pan", (0.995, 0.995, 0.05, 0.05))
    assert v.snd_lim == lim
    print("ok")


if __name__ == "__main__":
    main()
