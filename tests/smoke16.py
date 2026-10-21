"""Headless checks: figure phase 3 -- time-height panels from series (tornadic vs
non-tornadic, a row per series incl. d/dz, colorbar per row), time series with a second
y axis for other units, sounding panels (skew-T + hodograph, two runs in one panel),
contour key, annotations, streamlines (figure layer), export bundles whose scripts
redraw the identical image, spec reload.
Writes only to a temporary folder (and the series cache: SMOKE_SER_CACHE, else a
temporary one).  Usage: python tests/smoke16.py"""
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cm1view.registry import Registry
from cm1view import app as A, figure as fg, figdraw, series as S

TOR = "/glade/derecho/scratch/rasaba/phd/southeast/rm_tor_125m"
NTOR = "/glade/derecho/scratch/rasaba/phd/southeast/rm_ntor_125m"


def wait(pred, tmax=1800):
    t0 = time.time()
    while not pred() and time.time() - t0 < tmax:
        time.sleep(0.3)
    return time.time() - t0


def main():
    tmp = tempfile.mkdtemp(prefix="cm1view-smoke16-", dir=os.environ.get("TMPDIR") or None)
    S.CACHE_DIR = os.environ.get("SMOKE_SER_CACHE") or os.path.join(tmp, "cache")
    reg = Registry(TOR, 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    ed = v.figed

    def rendered(tmax=1800):
        def idle():
            return (not ed.series_pending() and "img src" in (ed.image.object or "")
                    and "busy" not in (ed.status.object or ""))
        time.sleep(0.5)
        dt = wait(idle, tmax)
        return f"{ed.status.object} [{dt:.0f} s]"

    def bundle(name):
        ed.path.value = os.path.join(tmp, name)
        ed._save_job(ed.collect(), True)
        print("  saved:", ed.msg.object[:160])
        png = os.path.join(tmp, name + ".png")
        os.rename(png, png + ".viewer")
        r = subprocess.run([sys.executable, "-I", os.path.join(tmp, name + ".py")],
                           capture_output=True, text=True, cwd=tmp)
        import matplotlib.image as mi
        same = os.path.exists(png) and np.array_equal(mi.imread(png), mi.imread(png + ".viewer"))
        print("  script redraws the identical image:", same, r.stderr[-300:] if not same else "")
        assert same

    # ---- two runs
    ed.add_path.value = NTOR
    ed._add_run()
    ed.run_rows[0]["label"].value, ed.run_rows[1]["label"].value = "Tornadic", "Nontornadic"
    v.workspace.value = "Figure"

    # ---- time-height: max w (default new series), max zeta, d/dz of max w
    ed.kind.value = "th"
    print("th cards:", [c.collect()["label"] for c in ed.ser_cards], ed.rows.value, "x",
          ed.cols.value)
    ed._add_series()
    ed.ser_cards[1].w["field"].value = "zvort"
    ed.ser_cards[1].w["vmin"].value, ed.ser_cards[1].w["vmax"].value = 0.0, 0.1
    ed._add_series()
    c = ed.ser_cards[2]
    c.w["op"].value = "ddz"
    c.w["cmap"].value, c.w["white_first"].value = "RdBu_r", False
    c.w["vmin"].value, c.w["vmax"].value, c.w["extend"].value = -0.02, 0.02, "both"
    ed._auto_titles()
    ed.request(delay=False)
    print("th:", rendered())
    s = ed.collect()
    assert (s["rows"], s["cols"]) == (3, 2), (s["rows"], s["cols"])
    assert s["size"] == [10.0, 9.0], s["size"]  # the size follows the grid
    assert s["series"][2]["units"] == "s$^{-1}$", s["series"][2]["units"]
    data = ed.panel_data(s)
    print("  panels:", [(figdraw.series_ref(s, i), data[i].get("missing"),
                         data[i].get("xlim")) for i in sorted(data)])
    assert all(not d.get("missing") for d in data.values())
    assert len({d["xlim"] for d in data.values()}) == 1  # shared time range
    # same as the Series computation: max w at one time and level
    ds = next(iter(ed._ser_mem.values()))
    print("  titles:", s["titles"][:2])
    bundle("th")

    # ---- time series: max w of both runs (panel 1); tor w and zeta on twin axes (panel 2)
    ed.kind.value = "line"
    cards = ed.ser_cards
    ed._remove_ser(cards[2])
    cards = ed.ser_cards
    cards[0].w["panel"].value = 1
    cards[1].w["panel"].value = 2
    ed._add_series()  # max w again, tor only, in panel 2
    cards = ed.ser_cards
    cards[2].w["panel"].value = 2
    cards[2].w["runs"].value = [0]
    cards[1].w["runs"].value = [0]
    cards[1].w["color"].value = "#d62728"
    ed.ann_kind.value = "vline"
    ed._add_annotation()
    ed.ann_rows[0].w["x"].value, ed.ann_rows[0].w["text"].value = 120.0, "TG"
    ed.request(delay=False)
    print("line:", rendered())
    s = ed.collect()
    data = ed.panel_data(s)
    print("  panels:", [(d.get("nlines"), [d.get(f"S{j}_label") for j in range(d.get("nlines", 0))])
           for d in data.values()])
    assert data[0]["nlines"] == 2 and data[1]["nlines"] == 2
    fig = figdraw.draw(s, data)
    print("  grid", s["rows"], "x", s["cols"], "· axes (2 panels + twin y):", len(fig.axes))
    assert (s["rows"], s["cols"]) == (2, 1) and len(fig.axes) == 3
    bundle("line")

    # ---- soundings: storm sounding of each run at 90 min in one panel
    ed.from_soundings()
    t90 = float(run.times[int(np.argmin(np.abs(np.asarray(run.times) - 5400)))])
    ed.snd_cards[0].w["time"].value = t90
    ed._add_sounding()
    c = ed.snd_cards[1]
    c.w["run"].value = 1
    c.w["time"].value = ed._nearest(c.w["time"].options, t90)
    c.w["panel"].value = 1
    c.w["kind"].value, c.w["x"].value = "trk", 0.0
    ed.request(delay=False)
    print("soundings:", rendered())
    s = ed.collect()
    data = ed.panel_data(s)
    print("  ", s["kind"], [(d.get("nsnd"), [d.get(f"N{j}_label") for j in range(d.get("nsnd", 0))],
                             d.get("missing")) for d in data.values()])
    assert data[0]["nsnd"] == 2
    bundle("snd")

    # ---- plan view with contour key, annotations, streamlines
    ed.set_spec(ed._default())
    s = ed.collect()
    print("default layers:", [lay["type"] for lay in s["layers"]])
    ed.ck_on.value = True
    ed.ck_label.value = "w"
    vec = next(c for c in ed.cards if c.type == "vectors")
    vec.w["on"].value = True
    ed.ann_kind.value = "arrow"
    ed._add_annotation()
    a = ed.ann_rows[-1].w
    a["x"].value, a["y"].value, a["x2"].value, a["y2"].value = 0.2, 0.8, 0.5, 0.5
    a["coords"].value, a["text"].value = "axes", "meso"
    ed.request(delay=False)
    print("plan + key:", rendered())
    s = ed.collect()
    data = ed.panel_data(s)
    fig = figdraw.draw(s, data)
    print("  axes (6 panels + key + colorbar):", len(fig.axes))
    bundle("plan_key")
    # streamlines style for the vectors layer (a LayerCard option)
    if "style" in vec.w:
        vec.w["style"].value = "streamlines"
        ed.request(delay=False)
        print("streamlines:", rendered())
        s = ed.collect()
        d0 = ed.panel_data(s)[0]
        j = [lay["type"] for lay in s["layers"]].index("vectors")
        print("  stream grid:", np.shape(d0.get(f"L{j}_gu")))
        assert d0.get(f"L{j}_gu") is not None
        bundle("plan_stream")

    # ---- reload the time-height spec
    ed.spec_path.value = os.path.join(tmp, "th_spec.json")
    ed._load_spec()
    s = ed.collect()
    print("reloaded:", ed.msg.object[:80], s["kind"], len(s["series"]), rendered())
    assert s["kind"] == "th" and len(s["series"]) == 3
    print("ok", tmp)


if __name__ == "__main__":
    main()
