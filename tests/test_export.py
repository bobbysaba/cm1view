"""netCDF export (core/export.py): the viewer's Export data dialog and `cm1view export`
write the values the map, volumes and column fields give, in a box, streamed per time."""
import os

import netCDF4
import numpy as np
import pytest

from conftest import wait

FIELDS = ["winterp", "thpert", "ddz.winterp", "ztilt", "uh25", "srh03", "swvort"]


def _open(path):
    """The file, read as plain arrays (NaN, not masked, where nothing was written)."""
    d = netCDF4.Dataset(path)
    d.set_auto_mask(False)
    return d


def _names(F):
    return [n for n in FIELDS if n in F]


def test_model_levels_match_the_volumes(reg, tmp_path):
    """Native, derived, derivative and column fields in a box on model levels: the
    volumes (and 2D planes) exactly; CF coordinates and attributes."""
    from cm1view.core import export as ex
    run, F = reg.get()
    names = _names(F)
    p = ex.plan(run, F, names, [1, 2], box=(-20, 10, -15, 15), ztop=8.0)
    i0, i1, j0, j1 = p["box"]
    assert run.xh[i0] >= -20 and run.xh[i1 - 1] <= 10 and run.z[p["ks"][-1]] <= 8.0
    r = ex.write(run, F, str(tmp_path / "a.nc"), p)
    assert r["times"] == 2 and not r["cancelled"] and not r["missing"]
    assert not os.path.exists(str(tmp_path / "a.nc.part"))
    with _open(r["path"]) as d:
        assert d.Conventions.startswith("CF") and d.cm1view_levels == "model levels"
        assert list(d["time"][:]) == [run.times[1], run.times[2]]
        assert np.array_equal(d["xh"][:], run.xh[i0:i1])
        assert np.array_equal(d["z"][:], run.z[p["ks"]]) and d["z"].axis == "Z"
        for n in names:
            v = d[ex.var_name(n)]
            assert v.cm1view_name == n and v.long_name == F[n].label
            if F[n].ndim == 2:
                assert v.dimensions == ("time", "yh", "xh")
                ref = F.plane(n, 2, storm=(run.umove, run.vmove))[j0:j1, i0:i1]
                assert np.array_equal(v[1], ref), n
            else:
                assert v.dimensions == ("time", "z", "yh", "xh")
                ref = F.volume(n, 2)[p["ks"], j0:j1, i0:i1]
                assert np.array_equal(v[1], ref), n
        assert d["ddz_winterp"].units == "1e-3 s-1"
        assert d["ddz_winterp"].units_shown == "10⁻³ s⁻¹"
        if "srh03" in names:
            assert "storm_u" in d.variables and d["srh03"].storm_relative


def test_heights_match_the_map(reg, tmp_path):
    """At heights: the map's planes there (derived fields computed at the height, as
    the map does, not interpolated from their volume)."""
    from cm1view.core import export as ex
    run, F = reg.get()
    names = _names(F)
    p = ex.plan(run, F, names, [2], heights=[0.5, 1.0, 3.0])
    r = ex.write(run, F, str(tmp_path / "h.nc"), p, storm=(5.0, 3.0), compress=False)
    with _open(r["path"]) as d:
        assert list(d["z"][:]) == [0.5, 1.0, 3.0] and "level" not in d.variables
        assert float(d["storm_u"][0]) == 5.0
        for n in names:
            st = (5.0, 3.0) if F[n].storm else None
            got = d[ex.var_name(n)][0]
            if F[n].ndim == 2:
                assert np.array_equal(got, F.plane(n, 2, storm=st)), n
            else:
                for k, h in enumerate((0.5, 1.0, 3.0)):
                    assert np.array_equal(got[k], F.plane(n, 2, "height", h, st)), (n, h)


def test_plan_checks_and_names(reg):
    from cm1view.core import export as ex
    run, F = reg.get()
    with pytest.raises(ValueError, match="not a field"):
        ex.plan(run, F, ["winterp", "nope"], [0])
    with pytest.raises(ValueError, match="no fields"):
        ex.plan(run, F, [], [0])
    with pytest.raises(ValueError, match="no output times"):
        ex.plan(run, F, ["winterp"], [len(run.times) + 3])
    p = ex.plan(run, F, ["uh25"], [0, 1])  # (2D only: no levels counted)
    assert p["bytes"] == 4 * 2 * run.ni * run.nj
    p = ex.plan(run, F, ["winterp"], [0], box=(0.1, 0.2, 0.1, 0.2))  # (inside a column)
    assert p["box"][1] - p["box"][0] == 1 and p["box"][3] - p["box"][2] == 1
    assert ex.cf_units("°C") == "degC" and ex.cf_units("m²/s²") == "m2/s2"
    assert ex.cf_units("") == "1" and ex.var_name("gradh.thpert") == "gradh_thpert"
    assert ex.default_name(run, ex.plan(run, F, ["winterp"], [1, 3])).startswith(
        f"winterp_t{int(run.times[1])}-{int(run.times[3])}s")


def test_stopped_keeps_the_times_done(reg, tmp_path):
    from cm1view.core import export as ex
    run, F = reg.get()
    p = ex.plan(run, F, ["winterp", "thpert"], range(len(run.times)))
    calls = []
    r = ex.write(run, F, str(tmp_path / "s.nc"), p,
                 progress=lambda done, total, what: calls.append(done),
                 cancelled=lambda: len(calls) >= 3)  # (after a time and a half)
    assert r["cancelled"] and r["times"] == 1
    with _open(r["path"]) as d:
        assert d.dimensions["time"].size == 2 and "1 of" in d.cm1view_incomplete
        assert "partly written" in d.cm1view_incomplete
        assert np.isnan(d["thpert"][1]).all() and np.isfinite(d["winterp"][1]).all()


def test_missing_time_is_nan(reg, tmp_path, monkeypatch):
    """A field the files lack at some time: NaN there, noted in the file."""
    from cm1view.core import export as ex
    run, F = reg.get()
    monkeypatch.setitem(run.var_times, "winterp", frozenset({0}))
    F.forget(1, ["winterp"])  # (not from the cache either)
    p = ex.plan(run, F, ["winterp", "uinterp"], [0, 1])
    r = ex.write(run, F, str(tmp_path / "m.nc"), p)
    assert r["missing"] == {"winterp": [1]}
    with _open(r["path"]) as d:
        assert np.isnan(d["winterp"][1]).all() and np.isfinite(d["uinterp"][1]).all()
        assert "winterp" in d.cm1view_missing
    F.forget(1, ["winterp"])


def test_viewer_dialog(viewer, tmp_path):
    """Fields (a derivative added), a box from the map view, all times, heights;
    Export writes in the background; Stop ends it with the times done."""
    from cm1view.core import export as ex
    v = viewer
    assert not v._exp_built  # (its widgets only when it first opens)
    v._open_export()
    assert v.exp_fields.value == [v._fill_name()] and v.exp_t0.value == v.t
    v.exp_dop.value, v.exp_dvar.value = "ddz", "winterp"
    v._exp_add_deriv(None)
    assert "ddz.winterp" in v.exp_fields.value
    v.exp_dop.value, v.exp_dvar.value = "ddz", "uh25"  # (2D: no ∂/∂z)
    v._exp_add_deriv(None)
    assert "2D" in v.exp_msg.object
    v.view = (-10.0, 10.0, -5.0, 5.0)
    v.exp_region.value = "Box"
    assert [w.value for w in v.exp_box] == [-10.0, 10.0, -5.0, 5.0]
    v._exp_times_all()
    v.exp_vert.value = "Heights"
    v.exp_heights.value = "1, 2"
    assert "2 heights" in v.exp_size.object
    path = str(tmp_path / "v.nc")
    v.exp_path.value = path
    v._on_export(None)
    wait(lambda: not v.exp_go.disabled, msg="the export")
    assert "Saved" in v.exp_msg.object
    with _open(path) as d:
        assert d.dimensions["time"].size == len(v.run.times)
        assert list(d["z"][:]) == [1.0, 2.0] and "ddz_winterp" in d.variables
        assert d["xh"][0] >= -10.0 and d["xh"][-1] <= 10.0
    p, _ = v._exp_plan()
    v._start_export(p, str(tmp_path / "stop.nc"))
    v._cancel_export()
    wait(lambda: not v.exp_go.disabled, msg="the stop")
    assert "stopped" in v.exp_msg.object
    assert ex.default_path(v.run, p).endswith(ex.default_name(v.run, p))


def test_cli(demo_run, tmp_path):
    from cm1view.__main__ import main
    out = str(tmp_path / "{run}_{name}")
    assert main(["export", demo_run, "--fields", "winterp,uh25", "--from", "60",
                 "--to", "70", "--box", "-20,10,-15,15", "--ztop", "5", "--out", out]) == 0
    path = [f for f in os.listdir(tmp_path) if f.endswith(".nc")]
    assert len(path) == 1 and path[0].startswith("supercell_winterp_uh25_t3600")
    with _open(str(tmp_path / path[0])) as d:
        assert d.dimensions["time"].size == 3 and d["z"][-1] <= 5.0
    # already there: refused unless --overwrite; bad names refused before writing
    args = ["export", demo_run, "--fields", "winterp,uh25", "--from", "60", "--to", "70",
            "--box", "-20,10,-15,15", "--ztop", "5", "--out", out]
    assert main(args) == 2 and main(args + ["--overwrite"]) == 0
    assert main(["export", demo_run, "--fields", "nope"]) == 2
    assert main(["export", demo_run, "--list"]) == 0
