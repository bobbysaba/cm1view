"""WoFS reader (core/wofs.py): one member of a tiny synthetic WoFS run (cycle folders of
wrfout_d01_<time>_<member> files beside DART files that are ignored), its names, grid,
times, base state and perturbations, and how runs are found and opened."""
import datetime
import os

import netCDF4
import numpy as np
import pytest

from cm1view import config, registry
from cm1view.core import models, wofs
from cm1view.core.fields import Fields

NI, NJ, NK, NC = 8, 6, 5, 3  # mass points, levels, cycles (every 3 minutes)
G = 9.81
START = datetime.datetime(2022, 5, 23, 22, 0)


def _expect(m, c):
    """The synthetic fields of member m at cycle c (on WRF's own grids)."""
    k = np.arange(NK, dtype=np.float32)[:, None, None]
    kw = np.arange(NK + 1, dtype=np.float32)[:, None, None]
    i = np.arange(NI, dtype=np.float32)
    hgt = np.broadcast_to(100.0 + 10.0 * i, (NJ, NI)).astype(np.float32)
    shape = (NK, NJ, NI)
    return dict(
        T=np.broadcast_to(m + 0.1 * c + k, shape),
        P=np.full(shape, 100.0 * c, np.float32),
        PB=np.broadcast_to(1.0e5 - 1000.0 * k, shape),
        QVAPOR=np.full(shape, 0.01 + 0.001 * m + 0.0001 * c, np.float32),
        QCLOUD=np.zeros(shape, np.float32), QRAIN=np.zeros(shape, np.float32),
        QICE=np.zeros(shape, np.float32), QSNOW=np.zeros(shape, np.float32),
        QGRAUP=np.zeros(shape, np.float32), QHAIL=np.zeros(shape, np.float32),
        REFL_10CM=np.full(shape, 10.0 * c, np.float32),
        U=np.broadcast_to(np.arange(NI + 1, dtype=np.float32) + c + m, (NK, NJ, NI + 1)),
        V=np.broadcast_to(np.arange(NJ + 1, dtype=np.float32)[:, None] - c,
                          (NK, NJ + 1, NI)),
        W=np.broadcast_to(kw + c, (NK + 1, NJ, NI)),
        PH=np.zeros((NK + 1, NJ, NI), np.float32),
        PHB=(G * (hgt + 500.0 * kw)).astype(np.float32),  # levels 500 m apart AGL
        HGT=hgt,
        UP_HELI_MAX=np.full((NJ, NI), float(c), np.float32),
    )


_DIMS = dict(T="zyx", P="zyx", PB="zyx", QVAPOR="zyx", QCLOUD="zyx", QRAIN="zyx",
             QICE="zyx", QSNOW="zyx", QGRAUP="zyx", QHAIL="zyx", REFL_10CM="zyx",
             U="zyX", V="zYx", W="Zyx", PH="Zyx", PHB="Zyx", HGT="yx", UP_HELI_MAX="yx")
_NAMES = dict(z="bottom_top", Z="bottom_top_stag", y="south_north", Y="south_north_stag",
              x="west_east", X="west_east_stag")


def make_wofs(root, members=(1, 2, 3), cycles=NC):
    """A synthetic WoFS run folder: `cycles` cycle folders of member files, each beside
    the DART files a real run has (left empty: they must not be read)."""
    os.makedirs(root, exist_ok=True)
    open(os.path.join(root, "add_noise.csh"), "w").close()
    for c in range(cycles):
        when = START + datetime.timedelta(minutes=3 * c)
        cyc = os.path.join(root, f"{when:%Y%m%d%H%M}")
        os.makedirs(cyc, exist_ok=True)
        for junk in (f"output_mean.nc.{when:%Y%m%d%H%M}", f"obs_seq.final.{when:%Y%m%d%H%M}",
                     "rsl.out.integration.1"):
            open(os.path.join(cyc, junk), "w").close()
        for m in members:
            open(os.path.join(cyc, f"wrfinput_d01.{m}"), "w").close()
            fn = os.path.join(cyc, f"wrfout_d01_{when:%Y-%m-%d_%H:%M:%S}_{m}")
            with netCDF4.Dataset(fn, "w", format="NETCDF3_64BIT_OFFSET") as d:
                d.createDimension("Time", None)
                d.createDimension("DateStrLen", 19)
                for dim, n in (("west_east", NI), ("south_north", NJ), ("bottom_top", NK),
                               ("west_east_stag", NI + 1), ("south_north_stag", NJ + 1),
                               ("bottom_top_stag", NK + 1), ("soil_layers_stag", 4)):
                    d.createDimension(dim, n)
                d.setncatts(dict(DX=np.float32(1000.0), DY=np.float32(1000.0),
                                 TITLE=" OUTPUT FROM WRF V3.9 MODEL", MP_PHYSICS=18))
                ts = d.createVariable("Times", "S1", ("Time", "DateStrLen"))
                ts[0] = netCDF4.stringtochar(np.array([f"{when:%Y-%m-%d_%H:%M:%S}"], "S19"))
                for name, a in _expect(m, c).items():
                    v = d.createVariable(name, "f4", ("Time",) + tuple(
                        _NAMES[ch] for ch in _DIMS[name]))
                    v.setncatts(dict(description=f"synthetic {name}", units="x",
                                     stagger=""))
                    v[0] = a
                # fields that are not on the model grid: left out
                d.createVariable("TSLB", "f4", ("Time", "soil_layers_stag", "south_north",
                                                "west_east"))[0] = 0.0
                d.createVariable("XLAT_U", "f4", ("Time", "south_north",
                                                  "west_east_stag"))[0] = 0.0
                d.createVariable("XTIME", "f4", ("Time",))[0] = 0.0
    return root


@pytest.fixture
def wofs_root(tmp_path):
    return make_wofs(str(tmp_path / "exp" / "20220523"))


def test_found_as_one_run_per_member(wofs_root, tmp_path):
    assert models.detect(wofs_root) is None  # (the folder itself is not one run)
    assert wofs.members(wofs_root) == [1, 2, 3]
    runs, complete = config.scan_runs([str(tmp_path)], model=None)
    assert runs == [os.path.join(wofs_root, f"mem0{m}") for m in (1, 2, 3)] and complete
    assert config.scan_runs([str(tmp_path)], model="cm1")[0] == []
    mem = os.path.join(wofs_root, "mem02")
    assert models.exists(mem) and not os.path.isdir(mem)
    assert models.detect(mem).key == "wofs" and models.count(mem) == NC
    assert registry.is_run(mem) and registry.is_run(mem, "wofs")
    assert not registry.is_run(mem, "cm1")
    assert not models.exists(os.path.join(wofs_root, "mem09"))  # no such member
    assert models.canonical(wofs_root) == os.path.join(wofs_root, "mem01")
    assert registry.sibling_runs(mem) == [os.path.join(wofs_root, f"mem0{m}")
                                          for m in (1, 3)]


def test_member_run(wofs_root):
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    assert run.model == "wofs" and run.member == 2 and run.members == [1, 2, 3]
    assert run.path == os.path.join(wofs_root, "mem02")
    np.testing.assert_allclose(run.times, [0.0, 180.0, 360.0])
    assert run.time_label(1) == "22:03 UTC"
    assert all("wrfout_d01_" in os.path.basename(f) for f in run.files)
    # grid: km, centred on the domain; heights AGL (domain mean) at mass levels
    assert (run.ni, run.nj, run.nk) == (NI, NJ, NK)
    np.testing.assert_allclose(run.xh, np.arange(NI) - 3.5)
    np.testing.assert_allclose(run.yh, np.arange(NJ) - 2.5)
    assert run.dx == pytest.approx(1000.0) and run.dy == pytest.approx(1000.0)
    np.testing.assert_allclose(run.zf, 0.5 * np.arange(NK + 1), atol=1e-4)
    np.testing.assert_allclose(run.z, 0.25 + 0.5 * np.arange(NK), atol=1e-4)
    # names: cm1view's where there is one, else WRF's; nothing off the model grid
    for n in ("th", "prs", "qv", "qc", "qr", "qi", "qs", "qg", "qhl", "dbz", "uinterp",
              "vinterp", "winterp", "th0", "prs0", "qv0", "u0", "v0", "PH", "HGT",
              "UP_HELI_MAX"):
        assert run.has(n), n
    for n in ("T", "P", "PB", "QVAPOR", "U", "W", "REFL_10CM", "TSLB", "XLAT_U", "XTIME",
              "Times"):
        assert not run.has(n), n
    assert run.vars["HGT"].ndim == 2 and run.vars["th"].ndim == 3
    assert run.vars["uinterp"].stag == "x" and run.vars["winterp"].stag == "z"
    assert run.vars["PH"].stag == "z"


def test_values(wofs_root):
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    m, c = 2, 1
    np.testing.assert_allclose(run.read_level("th", c, 3), 300.0 + m + 0.1 * c + 3,
                               rtol=1e-6)
    np.testing.assert_allclose(run.read_level("prs", c, 2), 1.0e5 - 2000.0 + 100.0 * c)
    u = run.read_level("uinterp", c, 0)  # averaged onto mass points
    assert u.shape == (NJ, NI)
    np.testing.assert_allclose(u[0], np.arange(NI) + 0.5 + c + m)
    np.testing.assert_allclose(run.read_level("vinterp", c, 0)[:, 0],
                               np.arange(NJ) + 0.5 - c)
    np.testing.assert_allclose(run.read_level("winterp", c, 1), 1.5 + c)
    np.testing.assert_allclose(run.read_level("UP_HELI_MAX", 2), 2.0)
    vol = run.volume("winterp", 2)
    assert vol.shape == (NK, NJ, NI)
    np.testing.assert_allclose(vol[:, 0, 0], np.arange(NK) + 0.5 + 2)
    box = run.read_box("uinterp", c, 1, 3, 0, 2)
    assert box.shape == (NK, 2, 2)
    np.testing.assert_allclose(box[0, 0], [1.5 + c + m, 2.5 + c + m])


def test_base_state_and_perturbations(wofs_root):
    run = models.open_run(os.path.join(wofs_root, "mem03"), workers=1)
    # the base state is the member's own field at its first time, at every time
    for t in range(NC):
        np.testing.assert_allclose(run.volume("th0", t), run.volume("th", 0))
        np.testing.assert_allclose(run.volume("u0", t), run.volume("uinterp", 0))
    np.testing.assert_allclose(run.read_level("qv0", 2, 0), 0.01 + 0.003, rtol=1e-6)
    F = Fields(run)
    assert "thpert" in F and "prspert" in F
    np.testing.assert_allclose(F.volume("thpert", 2), 0.2, atol=1e-4)  # 2 cycles of 0.1
    np.testing.assert_allclose(F.volume("prspert", 2), 2.0, atol=1e-4)  # hPa
    np.testing.assert_allclose(F.volume("thpert", 0), 0.0, atol=1e-6)
    prof = run.mean_profiles(["th0"], 1)["th0"]
    np.testing.assert_allclose(prof, 303.0 + np.arange(NK), rtol=1e-6)


def test_reader_processes(wofs_root):
    """Reader processes open the member's files themselves (a picklable source)."""
    run = models.open_run(os.path.join(wofs_root, "mem01"), workers=2)
    try:
        prof = run.mean_profiles(["th", "prs0"], 2)
        np.testing.assert_allclose(prof["th"], 301.2 + np.arange(NK), rtol=1e-6)
        np.testing.assert_allclose(prof["prs0"], 1.0e5 - 1000.0 * np.arange(NK))
        np.testing.assert_allclose(run.read_box("winterp", 1, 0, 2, 0, 2)[:, 0, 0],
                                   np.arange(NK) + 1.5)
    finally:
        if run._pool is not None:
            run._pool.shutdown()


def test_registry_keeps_members_apart(wofs_root):
    reg = registry.Registry(None, 1, 1)
    r1, _ = reg.get(os.path.join(wofs_root, "mem01"))
    r2, _ = reg.get(os.path.join(wofs_root, "mem02"))
    assert r1 is not r2 and r1.path != r2.path
    root_run, _ = reg.get(wofs_root)  # the folder itself: its first member
    assert root_run is r1
    np.testing.assert_allclose(r2.read_level("th", 0, 0) - r1.read_level("th", 0, 0), 1.0)


def test_picker_lists_members(wofs_root, monkeypatch):
    from cm1view.viewer.picker import RunPicker
    monkeypatch.setattr(registry, "recent_runs", lambda: [])
    p = RunPicker()
    p.query.value_input = wofs_root
    assert list(p.list.options) == ["mem01", "mem02", "mem03"]
    p.query.value_input = os.path.join(wofs_root, "mem03")  # a member: it is picked
    assert p.selected == os.path.join(wofs_root, "mem03") and not p.open.disabled
    assert "WoFS" in p.msg.object and "3 output times" in p.msg.object
