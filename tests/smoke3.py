import sys, time, base64, re
sys.path.insert(0, "/glade/work/rasaba/cm1view")
from cm1view.registry import Registry
from cm1view import app as A

def main():
    global v, SP
    SP = sys.argv[1]
    reg = Registry("/glade/derecho/scratch/rasaba/phd/test/initiation/c", 20, 1)
    run, F = reg.get()
    v = A.Viewer(run, F)
    v.main()
    v.tslider.value = 40

    def wait(pred, tmax=300):
        t0 = time.time()
        while not pred() and time.time() - t0 < tmax:
            time.sleep(0.5)
        return time.time() - t0

    def save_imgs(tag):
        objs = [v.skew_png.object, v.prof_png.object] if v.skew_png.visible else \
            [o.object for tab in v.snd_tabs.objects for o in tab.objects]
        for n, html in enumerate(objs):
            b = re.search(r"base64,([^\"]+)", html).group(1)
            open(f"{SP}/{tag}_{n}.png", "wb").write(base64.b64decode(b))

    print("mode at start:", v.mode.value)
    v.points = [("pt", (-25.0, -20.0)), ("mean", None)]
    v.request_soundings()
    print(f"pt+mean: {wait(lambda: not v.snd_col.loading):.1f}s", v.snd_head.object[:300])
    save_imgs("lines")
    v.tslider.value = 30
    v._add_mean(replace=False)
    print(f"pin t30: {wait(lambda: not v.snd_col.loading):.1f}s labels:", [l for l, _, _ in v.results])
    v.compare.value = "colors"; wait(lambda: not v.snd_col.loading); save_imgs("colors")
    v.compare.value = "tabs"; wait(lambda: not v.snd_col.loading)
    print("tabs:", v.snd_tabs.visible, len(v.snd_tabs.objects), v.snd_tabs._names)
    v.points = [("pt", (-25.0, -20.0))]; v.compare.value = "lines"; wait(lambda: not v.snd_col.loading); save_imgs("single")

    # cross-section with custom contour settings
    v.xs_pts = [(-45.0, -20.0), (0.0, -20.0)]
    v.xs_ccolor.value = "#fbbf24"; v.xs_negdash.value = False; v.xs_cmap.value = "viridis"
    v.request_xsec()
    print(f"xsec: {wait(lambda: 'busy' not in v.xs_status.object):.1f}s", v.xs_status.object[:160],
          v.xs_pos_r.glyph.line_color, v.xs_neg_r.glyph.line_dash)
    v.xs_auto.value = False
    print("xs manual range:", v.xs_min.value, v.xs_max.value)
    v._on_camera(type("E", (), {"new": "top"})())
    v._on_drag(type("E", (), {"new": "pan"})())
    print("ok")

if __name__ == "__main__":
    main()
