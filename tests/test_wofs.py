"""WoFS reader (core/wofs.py): one member of a tiny synthetic WoFS run (cycle folders of
wrfout_d01_<time>_<member> files beside DART files that are ignored), its names, grid,
times, base state and perturbations, its terrain-following heights and maps at a height
above ground or sea level, and how runs are found and opened."""
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
    hgt = np.broadcast_to(100.0 + 100.0 * i, (NJ, NI)).astype(np.float32)  # a slope
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
        # levels 500 m apart above the ground at first, then stretched by c (20 + 5 i)
        # m a level: heights that change with time and from column to column
        PH=(G * c * (20.0 + 5.0 * i) * kw).astype(np.float32),
        PHB=(G * (hgt + 500.0 * kw)).astype(np.float32),
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
              "UP_HELI_MAX", "zagl", "zmsl"):
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


def _dz(c):
    """Level spacing (km) of every column (along x) at cycle c: 0.5 + c (20 + 5 i) m."""
    return 0.5 + c * (20.0 + 5.0 * np.arange(NI)) / 1000.0


GROUND = (100.0 + 100.0 * np.arange(NI)) / 1000.0  # km MSL, along x


def test_heights(wofs_root):
    """Heights from the geopotential, per column and time: above ground and sea level,
    at mass and w levels, as fields too (m)."""
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    assert run.terrain is True
    np.testing.assert_allclose(run.terrain_height()[0], GROUND, atol=1e-6)
    kw = np.arange(NK + 1)[:, None, None]
    for c in (0, 2):
        zw = kw * _dz(c)
        np.testing.assert_allclose(run.heights(c, "agl", w=True), np.broadcast_to(
            zw, (NK + 1, NJ, NI)), atol=1e-4)
        za = run.heights(c, "agl")
        assert za.shape == (NK, NJ, NI)
        np.testing.assert_allclose(za, np.broadcast_to(0.5 * (zw[1:] + zw[:-1]), za.shape),
                                   atol=1e-4)
        np.testing.assert_allclose(run.heights(c, "msl") - za,
                                   np.broadcast_to(GROUND, za.shape), atol=1e-4)
        np.testing.assert_allclose(run.volume("zagl", c), 1000.0 * za, atol=0.1)
    # (the one profile for what takes one: the mean at the first time)
    np.testing.assert_allclose(run.z, run.heights(0).mean(axis=(1, 2)), atol=1e-4)
    assert run.vars["zmsl"].units == "m" and run.vars["zmsl"].ndim == 3


def test_maps_at_a_height_column_by_column(wofs_root):
    """A map at a height interpolates each column on its own levels: above ground, and
    above sea level (blank under the ground); derived fields and ∂/∂z too."""
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    F = Fields(run)
    c, dz = 2, _dz(2)
    # winterp is k + 0.5 + c on mass level k, at (k + 0.5) dz in each column
    for h in (0.1, 0.6, 1.3, 5.0):
        want = np.clip(h / dz - 0.5, 0, NK - 1) + 0.5 + c  # (held beyond the levels)
        np.testing.assert_allclose(F.plane("winterp", c, "height", h)[0], want, atol=1e-4)
        np.testing.assert_allclose(run.read_height("winterp", c, h)[2], want, atol=1e-4)
    h = 0.6
    want = np.clip((h - GROUND) / dz - 0.5, 0, NK - 1) + 0.5 + c
    want[h < GROUND] = np.nan
    msl = F.plane("winterp", c, "msl", h)
    assert msl.shape == (NJ, NI)
    np.testing.assert_allclose(msl[0], want, atol=1e-4)
    assert np.isnan(msl[:, GROUND > h]).all() and np.isfinite(msl[:, GROUND <= h]).all()
    np.testing.assert_allclose(F.plane("zagl", c, "height", 1.0), 1000.0, atol=0.1)
    inside = GROUND + 0.5 * dz < 1.0  # (columns whose lowest level is below 1 km MSL)
    np.testing.assert_allclose(F.plane("zmsl", c, "msl", 1.0)[:, inside], 1000.0, atol=0.1)
    np.testing.assert_allclose(F.plane("thpert", c, "msl", 1.0)[:, GROUND < 1.0], 0.2,
                               atol=1e-3)
    assert np.isfinite(F.plane("ddz.winterp", c, "height", 1.0)).all()
    # a model level is the level, whatever its height
    np.testing.assert_allclose(F.plane("winterp", c, "level", 3), 3.5 + c, atol=1e-5)


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


# ------------------------------------------------------------- W3: sections, soundings,
# column fields and series on each column's own heights (winterp = level + 0.5 + c, so
# at a height h above ground it is h / dz + c between the lowest and highest level)
def _w_at(h_agl, c):
    return np.clip(h_agl / _dz(c), 0.5, NK - 0.5) + c


def test_section_on_terrain(wofs_root):
    """A section across the slope: above sea level, from the lowest ground along it,
    each column on its own heights, blank under the ground; the figure's the same."""
    from cm1view.core import render
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    F, c = Fields(run), 2
    s, fi, fj, _ = render.section_coords(run, (run.xh[0], 0.0), (run.xh[-1], 0.0))
    z0, top, ground = render.section_span(run, fi, fj, 2.0)
    assert (z0, top) == (0.1, 2.0)
    np.testing.assert_allclose(ground, GROUND, atol=1e-6)
    zq = np.arange(z0, top + 1e-6, 0.1)
    a = render.sample_section(run, F.volume("winterp", c), fi, fj, zq, c)
    want = _w_at(zq[:, None] - GROUND[None], c)
    want[zq[:, None] < GROUND[None]] = np.nan
    np.testing.assert_allclose(a, want, atol=1e-4)
    # a top under the lowest ground: that far above it
    assert render.section_span(run, fi, fj, 0.3)[:2] == (0.1, 0.4)
    # the figure: same heights, the ground, limits from the bottom
    from cm1view.figures import spec as fg
    from cm1view.figures.spec import arrays
    sp = fg.default_spec(run, F, 1)
    sp.update(kind="xsec", layers=[fg.layer_defaults("fill", F, "winterp")])
    sp["sections"] = [fg.section_defaults(orient="ab", pos="fixed", a=[run.xh[0], 0.0],
                                          b=[run.xh[-1], 0.0])]
    sp["xsec"] = dict(sp["xsec"], ztop=2.0, dz=0.1)
    d = arrays.extract(run, F, sp, 0, None)
    assert d["ylim"] == (0.1, 2.0) and d["y"][0] == pytest.approx(0.1)
    np.testing.assert_allclose(d["ground"], GROUND, atol=1e-6)
    want = _w_at(d["y"][:, None] - GROUND[None], 1)
    want[d["y"][:, None] < GROUND[None]] = np.nan
    np.testing.assert_allclose(d["L0"], want, atol=1e-4)


def test_sounding_on_the_columns_heights(wofs_root):
    from cm1view.figures.spec import panels
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    r = panels.sounding_column(run, dict(time_s=360.0, where=dict(kind="pt", x=3.5, y=0.0,
                                                                   avg=0.0)), {})
    np.testing.assert_allclose(r["prof"]["z"][:NK], 1000.0 * run.heights(2)[:, 3, NI - 1],
                               rtol=1e-5)


def test_column_fields_and_ddz_on_own_heights(wofs_root):
    from cm1view.core.fields import column_levels_3d
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    F, c = Fields(run), 2
    dz = _dz(c)
    ks, th, zk = column_levels_3d(run.heights(c), run.heights(c, w=True), 0.0, 1.0)
    assert ks == [0, 1]  # (1 km: inside the second cell everywhere)
    np.testing.assert_allclose(th[0], 1000.0 * np.broadcast_to(dz, (NJ, NI)), atol=0.01)
    np.testing.assert_allclose(th[1], 1000.0 * np.broadcast_to(1.0 - dz, (NJ, NI)), atol=0.01)
    np.testing.assert_allclose(zk, run.heights(c)[:2])
    np.testing.assert_allclose(F.plane("wmax", c), NK - 0.5 + c)
    # ∂w/∂z = 1 / dz per km, on a level, at a height and as a volume
    np.testing.assert_allclose(F.plane("ddz.winterp", c, "level", 2)[0], 1.0 / dz,
                               atol=1e-4)
    np.testing.assert_allclose(F.plane("ddz.winterp", c, "height", 1.0)[0], 1.0 / dz,
                               atol=1e-4)
    np.testing.assert_allclose(F.volume("ddz.winterp", c)[:, 0], np.broadcast_to(
        1.0 / dz, (NK, NI)), atol=1e-4)
    assert np.isfinite(F.plane("sbcape", c)).all()


def test_series_on_own_heights(wofs_root, monkeypatch):
    """Series at a height and over a layer: each column on its own heights (the
    reader process reads them)."""
    from cm1view.core import series as ser
    monkeypatch.setattr(ser, "store", lambda *a, **k: None)
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    F = Fields(run)
    c = np.arange(NC)
    dz0 = 0.5 + c * 20.0 / 1000.0  # (the first column: the max of w at a height)

    def go(**r):
        rec = ser.normalize(dict(dict(region="domain", reduce="max"), **r))
        ds, skipped = ser.compute(run, F, rec, ser.empty(run, rec), workers=1)
        assert not skipped
        return ds
    np.testing.assert_allclose(go(field="winterp", vmode="height", z=1.0)["value"],
                               1.0 / dz0 + c, rtol=1e-5)
    np.testing.assert_allclose(go(field="ddz.winterp", vmode="height", z=1.0)["value"],
                               1.0 / dz0, rtol=1e-4)
    ds = go(field="winterp", vmode="layer", z0=0.0, z1=1.0)
    np.testing.assert_allclose(ds["value"], 1.5 + c, rtol=1e-6)  # (level 2 is above)
    np.testing.assert_allclose(ds["z_km"], 1.5 * dz0, rtol=1e-5)
    np.testing.assert_allclose(go(field="wmax", vmode="2d")["value"], NK - 0.5 + c)


def test_points_on_own_heights(wofs_root):
    """3D points (km MSL) placed among their column's levels: w = k + 0.5 + c at mass
    level k, between two columns bilinear; a single column like np.interp."""
    from cm1view.core import volume3d
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    F, c = Fields(run), 2
    H, W = run.heights(c, "msl"), F.volume("winterp", c)
    for k in (0.0, 1.0, 2.5):
        k0, f = int(k), k - int(k)
        z = (1 - f) * H[k0, 2, 5] + f * H[min(k0 + 1, NK - 1), 2, 5]
        v = volume3d.sample_points(run, W, [run.xh[5]], [run.yh[2]], [z], c)
        assert float(v[0]) == pytest.approx(k + 0.5 + c, abs=1e-4)
    x, z = 0.5 * (run.xh[3] + run.xh[4]), 0.5 * (H[1, 2, 3] + H[1, 2, 4])
    assert float(volume3d.sample_points(run, W, [x], [run.yh[2]], [z], c)[0]) == \
        pytest.approx(1.5 + c, abs=1e-4)
    with pytest.raises(ValueError):  # (a terrain run's points need their time)
        volume3d.sample_points(run, W, [x], [run.yh[2]], [z])
    col = np.array([[0.1, 0.4, 1.0, 2.5]])
    zz = np.array([-1.0, 0.1, 0.7, 2.0, 9.0])
    np.testing.assert_allclose(volume3d.frac_level(np.repeat(col, 5, 0), zz),
                               np.interp(zz, col[0], np.arange(4.0)))


def test_scene_on_terrain(wofs_root):
    """The 3D scene above sea level: isosurface vertices at their columns' level
    heights, the ground drawn (the floor on it), vectors that far above the ground,
    streamlines between each column's lowest level and the top."""
    from cm1view.core import volume3d
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    F, c = Fields(run), 2
    H = run.heights(c, "msl")
    box = (float(run.xh[0]), float(run.xh[-1]), float(run.yh[0]), float(run.yh[-1]))
    scene = dict(t=c, box=box, ztop=3.0, exag=2.0, smooth=0.0, res=1,
                 ground=dict(on=True, var="dbz", z=0.5, cmap="Field default", rev=False,
                             range="data", lo=0.0, hi=1.0),
                 isos=[dict(var="winterp", val=6.0, color="#ffffff", op=0.5)],
                 storm=(0.0, 0.0), fstorm=((0.0, 0.0), ""),
                 vecs=[dict(q="wind", level=1.0, frame="grid", density=4, ref=20.0,
                            color="#ffffff")],
                 stream=dict(on=True, z=0.5, n=3, length=6.0, dir="both", frame="grid",
                             color_by="w", seed_box=[-2.0, 2.0, -1.0, 1.0]))
    sc = volume3d.build_scene(run, F, scene)
    m = sc["meshes"][0]  # (w = 6 halfway between levels 3 and 4)
    i = np.round((m["x"] - run.xh[0])).astype(int)
    j = np.round((m["y"] - run.yh[0])).astype(int)
    np.testing.assert_allclose(m["z"], 0.5 * (H[3, j, i] + H[4, j, i]), atol=1e-4)
    np.testing.assert_allclose(sc["terrain"]["z"], run.terrain_height(), atol=1e-6)
    np.testing.assert_allclose(sc["ground"]["z"], run.terrain_height(), atol=1e-6)
    v = sc["vecs"][0]
    ok = np.isfinite(v["x"])
    np.testing.assert_allclose(v["z"][ok] - volume3d.ground_at(run, v["x"][ok], v["y"][ok]),
                               1.0, atol=1e-6)
    s = sc["stream"]
    ok = np.isfinite(s["x"])
    low = volume3d.columns(H, *volume3d._fij(run, s["x"][ok], s["y"][ok]))[:, 0]
    assert (s["z"][ok] >= low - 1e-4).all() and (s["z"][ok] <= 3.0 + 1e-6).all()
    assert s["seed_ring"].shape[1] == 3
    fig = volume3d.scene_figure(sc["meshes"], None, box, 3.0, 2.0, terrain=sc["terrain"])
    assert fig.data[0].name == "ground" and fig.layout.scene.zaxis.title.text == "z (km MSL)"
    # the figure's arrays keep the ground, the per-point vector heights and the ring
    from cm1view.figures.draw import scene3d
    a = scene3d.scene_arrays(scene3d.scene_data(sc, box, 3.0))
    np.testing.assert_allclose(a["terrain"]["z"], run.terrain_height(), atol=1e-6)
    assert np.shape(a["vecs"][0]["z"]) == np.shape(v["x"]) and a["ground"]["z"] is not None
    assert a["stream"]["seed_ring"].shape == s["seed_ring"].shape
    assert volume3d.top_height(run) == pytest.approx(run.z[-1] + GROUND.max())


def test_traced_trajectories(wofs_root, tmp_path, monkeypatch):
    """No parcel output: trajectories traced through the 3D winds (once, to the cache),
    above sea level, never under their column's lowest level, read like CM1's; turned
    off when the output is less often than the setting."""
    from cm1view.core import parcels as P, trajcalc, volume3d
    monkeypatch.setattr(P, "CACHE_DIR", str(tmp_path / "parcels"))
    monkeypatch.delenv("CM1VIEW_TRAJ_MAX_INTERVAL", raising=False)
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    F = Fields(run)
    assert run.traced_parcels and P.offered(run) and trajcalc.interval(run) == 180.0
    pf = P.for_run(run, F)
    assert isinstance(pf, trajcalc.Traced) and not pf.traced and pf.lattice() is None
    assert pf.n == pf.lat["nx"] * pf.lat["ny"] * pf.lat["nz"] and set(pf.vars) == set(trajcalc.VARS)
    ps = P.select(pf, dict(box=[-3.0, 3.0, -2.0, 2.0], z=[0.0, 3.0]), "s")
    assert pf.traced and len(ps)
    tr = pf.trajectories(ps, ("x", "y", "z", "w", "@winterp"))
    assert tr["z"].shape == (NC, len(ps))
    np.testing.assert_allclose(tr["w"], tr["@winterp"], atol=1e-4, equal_nan=True)
    for k in range(NC):
        ok = np.isfinite(tr["z"][k])
        low = volume3d.columns(run.heights(k, "msl"), *volume3d._fij(
            run, tr["x"][k][ok], tr["y"][k][ok]))[:, 0]
        assert (tr["z"][k][ok] >= low - 1e-4).all()
    ok = np.isfinite(tr["x"][-1])
    assert ok.any() and (tr["x"][-1][ok] > tr["x"][0][ok]).all()  # (u > 0 everywhere)
    assert (tr["z"][-1][ok] > tr["z"][0][ok]).all()  # (w > 0 everywhere)
    assert P.for_run(run, F) is pf  # (the same files: kept)
    monkeypatch.setenv("CM1VIEW_TRAJ_MAX_INTERVAL", "120")
    assert "180 s" in trajcalc.off(run) and P.for_run(run, F) is None and P.offered(run)
    monkeypatch.setenv("CM1VIEW_TRAJ_MAX_INTERVAL", "0")  # (0: never off)
    assert trajcalc.off(run) == ""
