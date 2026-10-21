"""Headless checks: Figure workspace (spec <-> widgets, preview, start from map /
cross-section, layers, panel fields, export bundle, script reproduces the image, spec
reload).  Writes only to a temporary folder.  Usage: python tests/smoke14.py"""
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

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
    tmp = tempfile.mkdtemp(prefix="cm1view-smoke14-", dir=os.environ.get("TMPDIR") or None)
    reg = Registry(RUN, 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F)
    v.main()
    ed = v.figed

    def rendered(before):
        wait(lambda: "img src" in (ed.image.object or "") and ed.image.object != before
             and "busy" not in (ed.status.object or ""), 600)
        return ed.status.object

    # track first (storm-centred panels)
    v.tslider.value = 30
    v.request_track(None, None)
    wait(lambda: v.trk_stop_btn.disabled, 600)
    print("track fixes:", len(v.fixes))

    # default figure: 2 x 3 storm-centred grid in time
    v.tslider.value = 20
    ed.set_spec(__import__("cm1view.figure", fromlist=["x"]).default_spec(run, F, 20))
    v.workspace.value = "Figure"
    print("default:", rendered(""))
    s = ed.collect()
    print("  spec: kind", s["kind"], "times", s["times"], "layers",
          [lay["type"] for lay in s["layers"]])
    img0 = ed.image.object

    # style change re-renders from the cache (fast)
    t0 = time.time()
    ed.cards[0].w["cmap"].value = "ChaseSpectral"
    ed.request(delay=False)
    print("restyle:", rendered(img0), f"({time.time() - t0:.1f} s)")

    # add shading + track layers, letters as (a), storm-relative coordinates
    ed._add_layer("shade")
    ed._add_layer("track")
    ed.let_fmt.value = "({a})"
    ed.coords.value = "storm"
    ed.ticklabels.value = "outer"
    ed.request(delay=False)
    print("layers:", [c.type for c in ed.cards], rendered(img0))

    # field panels at one time
    ed.vary.value = "field"
    ed.rows.value, ed.cols.value = 1, 3
    ed.pf_rows[1]["field"].value = "thpert"
    ed.pf_rows[2]["field"].value = "zvort"
    ed._auto_titles()
    ed.request(delay=False)
    s = ed.collect()
    print("fields:", [p["field"] for p in s["panel_fills"]], "titles", s["titles"],
          "cbar", s["colorbar"]["mode"], rendered(img0))

    # export bundle; the script redraws the identical image
    ed.path.value = os.path.join(tmp, "fig_fields")
    ed._save_job(ed.collect(), True)
    print("  saved:", ed.msg.object[:160])
    png = os.path.join(tmp, "fig_fields.png")
    a = open(png, "rb").read()
    os.rename(png, png + ".viewer")
    r = subprocess.run([sys.executable, "-I", os.path.join(tmp, "fig_fields.py")],
                       capture_output=True, text=True, cwd=tmp)
    print("  script:", r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-400:])
    import matplotlib.image as mi
    same = np.array_equal(mi.imread(png), mi.imread(png + ".viewer"))
    print("  script image identical to the viewer's:", same)
    assert same

    # reload the spec
    ed.spec_path.value = os.path.join(tmp, "_src", "fig_fields_spec.json")
    ed.start_def.clicks += 1
    ed._load_spec()
    s2 = ed.collect()
    print("  reloaded:", ed.msg.object[:80], "| same panels:",
          [p["field"] for p in s2["panel_fills"]] == [p["field"] for p in s["panel_fills"]])

    # cross-section through the storm, 1 x 3 in time
    ed.set_spec(__import__("cm1view.figure", fromlist=["x"]).default_spec(run, F, 25))
    ed.kind.value = "xsec"
    ed.rows.value, ed.cols.value = 1, 3
    ed._fill_times()
    ed.cards[0].w["field"].value = "zvort"
    ed.request(delay=False)
    print("xsec:", rendered(ed.image.object), ed.collect()["times"])
    ed.fmt.value = "pdf"
    ed.path.value = os.path.join(tmp, "fig_xsec")
    ed._save_job(ed.collect(), False)
    print("  pdf:", os.path.getsize(os.path.join(tmp, "fig_xsec.pdf")), "bytes")

    # from the map
    v.workspace.value = "Map"
    v.fill_var.value = "thpert"
    ed.from_map()
    s = ed.collect()
    print("from map:", [(lay["type"], lay.get("field"), lay.get("levels", "")) for lay in
                        s["layers"]], s["domain"]["mode"], rendered(""))
    # download
    print("download bytes:", len(ed._download().getvalue()))
    print("ok", tmp)


if __name__ == "__main__":
    main()
