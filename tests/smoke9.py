"""Headless checks: run-picker folder browser, m/hPa level rows, sounding plot style,
zoom by redrawing with axes limits.  Usage: python tests/smoke9.py"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cm1view.registry import Registry, subfolders
from cm1view import app as A

PHD = "/glade/derecho/scratch/rasaba/phd"


def wait(pred, tmax=600):
    t0 = time.time()
    while not pred() and time.time() - t0 < tmax:
        time.sleep(0.2)
    return time.time() - t0


def main():
    sf = subfolders(PHD)
    print("subfolders of phd/:", list(sf)[:6])
    reg = Registry(f"{PHD}/test/initiation/c", 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F)
    v.main()

    # ---- run picker: browse up and into folders
    v.rp_path.value = f"{PHD}/cp20"
    print("runs here:", list(v.rp_list.options)[:3])
    print("folders:", list(v.rp_dirs.options)[:4])
    up = next(p for k, p in v.rp_dirs.options.items() if k.startswith("↑"))
    v.rp_dirs.value = up
    print("after '..': path", v.rp_path.value, "| folders", list(v.rp_dirs.options)[:4])

    # ---- a sounding
    v.tslider.value = 48
    v.mode.set("Sounding")
    v._on_tap(type("E", (), {"x": -25.0, "y": -22.0, "modifiers": {}})())
    wait(lambda: v.skew_png.src and not v.snd_col.loading)
    html = v.params.html
    rows = re.findall(r'<tr class="alt" data-row="([^"]+)">(.*?)</tr>', html)
    for name, body in rows[:7]:
        a = re.findall(r'<span class="ua">([^<]*)</span><span class="ub">([^<]*)</span>', body)
        print(f"  {name}: {a[0][0]} m = {a[0][1]} hPa")
    v.params.alt_rows = ["SB LCL"]
    v.request_soundings()
    wait(lambda: not v.snd_col.loading)
    print("alt rows kept after refresh:", v.params.alt_rows)

    # ---- style: colour and width reach the drawn figure
    d0 = v.skew_png.done
    v.ps["t"].value = "#ff00ff"
    wait(lambda: v.skew_png.done > d0)
    import base64
    svg = base64.b64decode(v.skew_png.src.split(",", 1)[1]).decode()
    print("magenta T line in SVG:", "#ff00ff" in svg)

    # ---- zoom: skew-T box, hodograph box, profile box
    v._set_full(True)
    fig = v._figs[v.skew_png]
    print("skew axes before:", [round(x, 1) for x in fig.cv_axes["skew"].get_xlim()],
          [round(x) for x in fig.cv_axes["skew"].get_ylim()])

    def boxed(z, box):
        d = z.done
        z.box = list(box) + [time.time()]
        wait(lambda: z.done > d, 60)

    boxed(v.skew_png, (0.10, 0.45, 0.35, 0.92))
    fig = v._figs[v.skew_png]
    print("skew limits:", [round(x, 1) for x in v.snd_lim["skew"]])
    print("skew axes after:", [round(x, 1) for x in fig.cv_axes["skew"].get_xlim()],
          [round(x) for x in fig.cv_axes["skew"].get_ylim()])
    boxed(v.skew_png, (0.65, 0.30, 0.85, 0.70))
    print("hodo limits:", [round(x, 1) for x in v.snd_lim["hodo"]])
    boxed(v.prof_png, (0.30, 0.30, 0.45, 0.70))
    print("profile limits: z", [round(x, 2) for x in v.snd_lim["prof_z"]],
          "x", {k: [round(a, 2) for a in x] for k, x in v.snd_lim["prof_x"].items()})
    d = v.skew_png.done
    v.skew_png.zoom_out += 1
    wait(lambda: v.skew_png.done > d, 60)
    print("after zoom out, skew:", [round(x, 1) for x in v.snd_lim["skew"]])
    # zoom kept when the sounding is re-analysed (e.g. next time)
    v.tslider.value = 49
    v._refresh_panels()
    wait(lambda: not v.snd_col.loading, 300)
    time.sleep(1)
    fig = v._figs[v.skew_png]
    print("next time keeps zoom:", [round(x) for x in fig.cv_axes["skew"].get_ylim()])
    d = v.skew_png.done
    v.skew_png.resets += 1
    wait(lambda: v.skew_png.done > d, 60)
    print("after reset:", sorted(v.snd_lim))
    v.wunits.value = "kt"
    print("after kt:", sorted(v.snd_lim))
    print("ok")


if __name__ == "__main__":
    main()
