"""The timing hooks (cm1view --timing, cm1view bench): records split into parts, the
log and its summary."""
import json

from bokeh.document import Document

from conftest import wait
from cm1view.viewer import timing


def _idle(v):
    for _ in range(3):
        for p in v.pools.values():
            p.submit(lambda: None).result()


def test_map_update_is_timed_and_measured(viewer, tmp_path):
    v = viewer
    _idle(v)
    doc = Document()
    doc.add_root(v.main().get_root(doc))
    log = tmp_path / "t.jsonl"
    tm = timing.Timing(v, path=str(log), browser=False, doc=doc)
    v.run.clear_cache()
    v.F.clear_planes()  # (the fields keep the planes they made, too)
    v.request_map()
    wait(lambda: any(r.get("view") == "map" for r in tm.records), msg="a timed map")
    r = [r for r in tm.records if r.get("view") == "map"][-1]
    for k in ("queue", "read", "compute", "wait", "apply", "total"):
        assert r[k] is not None and r[k] >= 0, k
    assert r["total"] >= r["read"] + r["compute"] - 1e-6
    # nothing cached: the job's reads are its own, not lumped into the queue (the job
    # can start before the request returns)
    assert r["disk_reads"] > 0 and r["read"] > 0
    assert r["field"] == v._fill_name() and r["t"] == v.t
    assert r["bytes"] > 1000  # (the image went into the patch)
    # the same map again: nothing read from disk
    v.request_map()
    wait(lambda: len([r for r in tm.records if r.get("view") == "map"]) >= 2, msg="2nd map")
    r2 = [r for r in tm.records if r.get("view") == "map"][-1]
    assert r2["cached"] and r2["disk_reads"] == 0
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(lines) == len(tm.records)


def test_summary_of_a_log(tmp_path, capsys):
    log = tmp_path / "t.jsonl"
    recs = [dict(kind="start", host="h", cpus=4, job=None, run="/r", grid=[1, 2, 3],
                 times=5, workers=2),
            dict(kind="page", build=1.0, load=3.0, bytes=2_000_000, models=900),
            dict(kind="ping", net=0.05, browser=0.02)]
    for i in range(3):
        recs.append(dict(kind="view", view="map", cached=i > 0, queue=0.0, read=0.5 * (i == 0),
                         compute=0.1, wait=0.0, apply=0.01, echo=0.2, browser=0.03,
                         total=0.8, bytes=40_000, superseded=0))
    log.write_text("".join(json.dumps(r) + "\n" for r in recs))
    timing.summarize(str(log))
    out = capsys.readouterr().out
    assert "900 Bokeh models" in out and "ping" in out
    assert out.count("\nmap ") == 2  # cached and not cached rows
