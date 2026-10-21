"""Headless checks: Figure workspace with panels from several runs (tornadic vs
non-tornadic): track files found next to the runs, run x time grid (runs as rows and
as columns), panels with their own run and time, run labels, export bundle (the script
redraws the identical image), spec reload, an older one-run spec, removing a run.
Writes only to a temporary folder.  Usage: python tests/smoke15.py"""
import json
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cm1view.registry import Registry
from cm1view import app as A, figure as fg

TOR = "/glade/derecho/scratch/rasaba/phd/southeast/rm_tor_125m"
NTOR = "/glade/derecho/scratch/rasaba/phd/southeast/rm_ntor_125m"


def wait(pred, tmax=900):
    t0 = time.time()
    while not pred() and time.time() - t0 < tmax:
        time.sleep(0.2)
    return time.time() - t0


def main():
    tmp = tempfile.mkdtemp(prefix="cm1view-smoke15-", dir=os.environ.get("TMPDIR") or None)
    reg = Registry(TOR, 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    ed = v.figed

    def rendered(before):
        wait(lambda: "img src" in (ed.image.object or "") and ed.image.object != before
             and "busy" not in (ed.status.object or ""))
        return ed.status.object

    print("track file found:", fg.find_track(TOR), "|", fg.find_track(NTOR))
    assert fg.find_track(NTOR).endswith("storm_tracks/rm_ntor_125m.csv")

    # this run with its track file instead of the Track tab
    t60 = int(np.argmin(np.abs(np.asarray(run.times) - 3600)))
    v.tslider.value = t60
    s = fg.default_spec(run, F, t60)
    s["runs"] = [fg.run_entry(run)]
    s["layers"] = [lay for lay in s["layers"] if lay["type"] != "vectors"]
    ed.set_spec(s)
    v.workspace.value = "Figure"
    print("one run:", rendered(""))
    print("  runs tab:", ed.run_rows[0]["info"].object)

    # add the non-tornadic run: becomes a 2 x N grid, runs as rows
    ed.add_path.value = NTOR
    ed._add_run()
    print("added:", ed.runs_msg.object, "| info:", ed.run_rows[1]["info"].object)
    ed.tstep.value = 10
    ed.cols.value = 3
    ed._fill_times()
    ed.run_rows[0]["label"].value = "tor"
    ed.run_rows[1]["label"].value = "ntor"
    ed.request(delay=False)
    s = ed.collect()
    print("grid:", s["vary"], s["rows"], "x", s["cols"], "times (min)",
          [x / 60 for x in s["times_s"]], rendered(""))
    data = ed.panel_data(s)
    refs = [fg.panel_ref(s, i) for i in range(fg.npanels(s))]
    print("  panels:", [(s["runs"][k]["label"], t / 60) for k, t in refs])
    print("  labels:", [data[i].get("run_label") for i in sorted(data)],
          "missing:", [data[i].get("missing") for i in sorted(data) if data[i].get("missing")])
    assert s["rows"] == 2 and all(not d.get("missing") for d in data.values())
    assert [data[i]["run_label"] for i in sorted(data)] == ["tor"] * 3 + ["ntor"] * 3
    # each run is centred on its own storm
    c0 = (data[0]["xlim"], data[3]["xlim"])
    print("  tor / ntor x window at the first time:", c0)

    # export; the script redraws the identical image
    ed.path.value = os.path.join(tmp, "tor_ntor")
    ed._save_job(ed.collect(), True)
    print("  saved:", ed.msg.object[:200])
    png = os.path.join(tmp, "tor_ntor.png")
    os.rename(png, png + ".viewer")
    r = subprocess.run([sys.executable, "-I", os.path.join(tmp, "tor_ntor.py")],
                       capture_output=True, text=True, cwd=tmp)
    print("  script:", r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-400:])
    import matplotlib.image as mi
    same = np.array_equal(mi.imread(png), mi.imread(png + ".viewer"))
    print("  script image identical to the viewer's:", same)
    assert same
    head = open(os.path.join(tmp, "tor_ntor.py")).read().split('"""')[1]
    print("  script header runs:", [ln for ln in head.splitlines() if ": /" in ln])

    # runs as columns
    ed.runs_as.value = "cols"
    ed.request(delay=False)
    s = ed.collect()
    print("runs as columns:", s["rows"], "x", s["cols"],
          [(s["runs"][k]["label"], t / 60) for k, t in
           (fg.panel_ref(s, i) for i in range(fg.npanels(s)))], rendered(""))
    assert s["rows"] == 3 and s["cols"] == 2

    # each panel its own run and time (e.g. both storms at their own peak)
    ed.vary.value = "custom"
    ed.rows.value, ed.cols.value = 1, 3
    times = list(ed.pc_rows[0]["time"].options.values())
    ed.pc_rows[0]["run"].value, ed.pc_rows[0]["time"].value = 0, times[30]
    ed.pc_rows[1]["run"].value, ed.pc_rows[1]["time"].value = 1, times[30]
    ed.pc_rows[2]["run"].value, ed.pc_rows[2]["time"].value = 1, times[40]
    ed._auto_titles()
    ed.request(delay=False)
    s = ed.collect()
    print("custom:", s["panels"], "titles", s["titles"], rendered(""))
    assert [p["run"] for p in s["panels"]] == [0, 1, 1]

    # reload the saved grid spec
    ed.spec_path.value = os.path.join(tmp, "_src", "tor_ntor_spec.json")
    ed._load_spec()
    s2 = ed.collect()
    print("reloaded:", ed.msg.object[:90], s2["vary"], [r["label"] for r in s2["runs"]],
          rendered(""))
    assert s2["vary"] == "grid" and len(s2["runs"]) == 2

    # an older (one-run) spec without runs / seconds: this run, times by index
    old = {k: val for k, val in s2.items() if k not in ("runs", "run", "runs_as", "panels",
                                                         "times_s", "time_s", "run_label")}
    old["vary"], old["rows"], old["cols"] = "time", 1, 2
    old["times"] = [t60, t60 + 5]
    with open(os.path.join(tmp, "old_spec.json"), "w") as f:
        json.dump(old, f)
    ed.spec_path.value = os.path.join(tmp, "old_spec.json")
    ed._load_spec()
    s3 = ed.collect()
    print("old spec:", ed.msg.object[:80], [r["path"] for r in s3["runs"]],
          [x / 60 for x in s3["times_s"]], rendered(""))
    assert len(s3["runs"]) == 1 and s3["times"] == [t60, t60 + 5]
    # the Track tab is empty here: the run's storm_tracks file centres the panels
    assert s3["runs"][0]["track"].endswith("rm_tor_125m.csv"), s3["runs"][0]
    assert "no data" not in ed.status.object

    # remove a run from a two-run list
    ed.spec_path.value = os.path.join(tmp, "_src", "tor_ntor_spec.json")
    ed._load_spec()
    ed._remove_run(ed.run_rows[1])
    s4 = ed.collect()
    print("removed:", [r["label"] for r in s4["runs"]], s4["rows"], "x", s4["cols"],
          rendered(""))
    assert len(s4["runs"]) == 1 and s4["rows"] == 1
    print("ok", tmp)


if __name__ == "__main__":
    main()
