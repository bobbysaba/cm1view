"""WoFS reader (core/wofs.py): one member of a tiny synthetic WoFS run (cycle folders of
wrfout_d01_<time>_<member> files beside DART files that are ignored), its names, grid,
times, base state and perturbations, its terrain-following heights and maps at a height
above ground or sea level, and how runs are found and opened; the ensemble mean (<root>/mean)."""
import datetime
import os

import netCDF4
import numpy as np
import pytest

from cm1view import config, registry
from cm1view.core import models, wofs
from cm1view.core.fields import Fields
from cm1view.demo_wofs import PROJ
from conftest import txt

NI, NJ, NK, NC = 8, 6, 5, 3  # mass points, levels, cycles (every 3 minutes)
G = 9.81
START = datetime.datetime(2022, 5, 23, 22, 0)
# WoFS's projection, the grid centred on the Texas / New Mexico border (103.06° W)
ON_MAP = dict(PROJ, CEN_LON=np.float32(-103.03), CEN_LAT=np.float32(34.0))


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
                                 TITLE=" OUTPUT FROM WRF V3.9 MODEL", MP_PHYSICS=18,
                                 **ON_MAP))
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


def test_experiment_is_one_run(wofs_root, tmp_path):
    exp = os.path.dirname(wofs_root)  # <exp>/20220523/<cycles>: the experiment is the run
    assert wofs.members(exp) == wofs.members(wofs_root) == [1, 2, 3]
    assert wofs.cycles(exp)[0] == os.path.join("20220523", "202205232200")
    assert models.detect(exp).key == "wofs" and models.count(exp) == NC
    runs, complete = config.scan_runs([str(tmp_path)], model=None)
    assert runs == [exp] and complete  # (one entry, not one per member)
    assert config.scan_runs([str(tmp_path)], model="cm1")[0] == []
    assert models.summary(exp) == "3 members"
    assert models.parts(exp) == [os.path.join(exp, n)
                                 for n in ("mem01", "mem02", "mem03", "mean")]
    mem = os.path.join(exp, "mem02")
    assert models.exists(mem) and not os.path.isdir(mem)
    assert models.detect(mem).key == "wofs" and models.count(mem) == NC
    assert registry.is_run(mem) and registry.is_run(mem, "wofs")
    assert not registry.is_run(mem, "cm1")
    assert not models.exists(os.path.join(exp, "mem09"))  # no such member
    assert models.root_of(mem) == exp and models.root_of(exp) == exp
    assert models.part_label(mem) == "Member 2"
    assert models.part_label(os.path.join(exp, "mean")) == "Ensemble mean"
    assert models.canonical(exp) == os.path.join(exp, "mem01")
    assert models.canonical(wofs_root) == os.path.join(wofs_root, "mem01")  # (a date folder)
    assert registry.sibling_runs(mem) == [os.path.join(exp, n)
                                          for n in ("mem01", "mem03", "mean")]


@pytest.mark.parametrize("setting, opens", [("2", "mem02"), ("mean", "mean"),
                                            ("9", "mem01"), ("junk", "mem01")])
def test_member_opened_first_is_a_setting(wofs_root, monkeypatch, setting, opens):
    exp = os.path.dirname(wofs_root)
    monkeypatch.setenv("CM1VIEW_WOFS_MEMBER", setting)
    assert models.canonical(exp) == os.path.join(exp, opens)
    run = models.open_run(exp, workers=1)
    assert run.path == os.path.join(exp, opens)


def test_date_folders_joined(tmp_path):
    """A run cycling across 00 UTC: its cycles are in two date folders, one timeline."""
    exp = str(tmp_path / "exp")
    make_wofs(os.path.join(exp, "20220523"))
    last = f"{START + datetime.timedelta(minutes=3 * (NC - 1)):%Y%m%d%H%M}"
    os.makedirs(os.path.join(exp, "20220524"))
    os.rename(os.path.join(exp, "20220523", last), os.path.join(exp, "20220524", last))
    os.makedirs(os.path.join(exp, "FCST", "20220523"))  # (other folders: ignored)
    assert wofs.cycles(exp)[-1] == os.path.join("20220524", last)
    assert models.count(exp) == NC
    run = models.open_run(exp, workers=1)
    np.testing.assert_allclose(run.times, [0.0, 180.0, 360.0])
    assert os.path.basename(os.path.dirname(os.path.dirname(run.files[-1]))) == "20220524"


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
    prof = run.mean_profiles(["th", "prs0"], 2)
    np.testing.assert_allclose(prof["th"], 301.2 + np.arange(NK), rtol=1e-6)
    np.testing.assert_allclose(prof["prs0"], 1.0e5 - 1000.0 * np.arange(NK))
    np.testing.assert_allclose(run.read_box("winterp", 1, 0, 2, 0, 2)[:, 0, 0],
                               np.arange(NK) + 1.5)


def test_registry_keeps_members_apart(wofs_root):
    reg = registry.Registry(None, 1, 1)
    r1, _ = reg.get(os.path.join(wofs_root, "mem01"))
    r2, _ = reg.get(os.path.join(wofs_root, "mem02"))
    assert r1 is not r2 and r1.path != r2.path
    root_run, _ = reg.get(wofs_root)  # the folder itself: its first member
    assert root_run is r1
    np.testing.assert_allclose(r2.read_level("th", 0, 0) - r1.read_level("th", 0, 0), 1.0)


def test_picker_lists_the_experiment(wofs_root, tmp_path, monkeypatch):
    from cm1view.viewer.picker import RunPicker
    monkeypatch.setattr(registry, "recent_runs", lambda: [])
    exp = os.path.dirname(wofs_root)
    p = RunPicker()
    p.query.value_input = f"{tmp_path}/"
    assert list(p.list.options) == ["exp"]  # one run, not one per member
    assert p.selected == exp and not p.open.disabled
    assert "WoFS" in p.msg.object and "3 members" in p.msg.object
    assert "3 output times" in p.msg.object
    p.query.value_input = os.path.join(exp, "mem03")  # a member typed in full: picked
    assert p.selected == os.path.join(exp, "mem03") and not p.open.disabled


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


def test_scene_on_terrain_read_in_parts(wofs_root, monkeypatch):
    """A terrain run's 3D scene whose fields do not fit the 3D cache (its box and the
    level heights there read alone) is the whole-volume scene; so are the points of a
    streamline placed among their columns' levels from those columns alone."""
    from cm1view.core import volume3d
    path = os.path.join(wofs_root, "mem02")
    ref, run, c = models.open_run(path, workers=1), models.open_run(path, workers=1), 2
    monkeypatch.setattr(run, "fits", lambda nbytes: False)
    for res, box in ((1, (float(ref.xh[0]), float(ref.xh[-1]), float(ref.yh[0]),
                          float(ref.yh[-1]))),
                     (2, (float(ref.xh[1]), float(ref.xh[-3]), float(ref.yh[2]),
                          float(ref.yh[-2])))):
        scene = dict(t=c, box=box, ztop=3.0, exag=2.0, smooth=0.0, res=res,
                     ground=dict(on=False, var="dbz", z=0.5, cmap="Field default",
                                 rev=False, range="data", lo=0.0, hi=1.0),
                     isos=[dict(var="winterp", val=6.0, color="#ffffff", op=0.5)],
                     storm=(0.0, 0.0), fstorm=((0.0, 0.0), ""), vecs=[],
                     stream=dict(on=True, z=0.5, n=3, length=6.0, dir="both",
                                 frame="grid", color_by="w", seed_box=[-2.0, 2.0, -1.0, 1.0]))
        want = volume3d.build_scene(ref, Fields(ref), scene)
        got = volume3d.build_scene(run, Fields(run), scene)
        assert len(got["meshes"]) == len(want["meshes"]) == 1
        a, b = got["meshes"][0], want["meshes"][0]
        assert np.array_equal(a["faces"], b["faces"])
        for k in "xyz":
            np.testing.assert_allclose(a[k], b[k], atol=1e-4)
        a, b = got["stream"], want["stream"]
        assert a["n"] == b["n"] > 0 and np.array_equal(a["segs"], b["segs"])
        for k in "xyzw":
            np.testing.assert_allclose(a[k], b[k], atol=1e-4)
        ok = np.isfinite(b["x"])
        pts = (b["x"][ok], b["y"][ok], b["z"][ok])
        for p, q in zip(volume3d.point_index(run, c, *pts, parts=True),
                        volume3d.point_index(ref, c, *pts)):
            np.testing.assert_allclose(p, q, atol=1e-6)
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


def test_traced_trajectories_read_in_parts(wofs_root, tmp_path, monkeypatch):
    """A terrain run's winds too large for the 3D cache: traced in boxes (their level
    heights read with them), the trajectories are the whole-volume ones, also when
    every band has to be traced again in a wider box; and a field sampled along them
    from the columns around the parcels on those columns' own heights is the one
    sampled from its volume."""
    from cm1view.core import fields as fmod, parcels as P, trajcalc
    from test_parcels import _spy_parts
    monkeypatch.setattr(P, "CACHE_DIR", str(tmp_path / "parcels"))
    path = os.path.join(wofs_root, "mem02")
    ref, run = models.open_run(path, workers=1), models.open_run(path, workers=1)
    monkeypatch.setattr(run, "fits", lambda nbytes: False)
    lat = trajcalc.lattice(ref)
    want = trajcalc.trace(ref, lat)
    boxes, redone = _spy_parts(monkeypatch, trajcalc)
    monkeypatch.setattr(fmod, "PART_BYTES", 1)
    monkeypatch.setattr(trajcalc, "MARGIN", 0.0)
    monkeypatch.setattr(trajcalc, "U_MIN", 0.0)
    monkeypatch.setattr(trajcalc, "W_MIN", 0.0)
    real_box = trajcalc._box

    def tight(run, p, mh, mv):  # (on an 8 x 6 grid the points around a box span it:
        K1, J0, J1, I0, I1 = real_box(run, p, mh, mv)  # first tries without them)
        if mh == 0.0:
            fi, fj = trajcalc._fij(run, p[:, 0], p[:, 1])
            J0, J1 = int(np.floor(np.nanmin(fj))), int(np.ceil(np.nanmax(fj))) + 1
            I0, I1 = int(np.floor(np.nanmin(fi))), int(np.ceil(np.nanmax(fi))) + 1
        return K1, J0, J1, I0, I1

    monkeypatch.setattr(trajcalc, "_box", tight)
    got = trajcalc.trace(run, lat)
    assert boxes and None not in boxes and sum(redone) > 0
    for k in trajcalc.VARS:
        np.testing.assert_allclose(got[k], want[k], rtol=0, atol=1e-5, equal_nan=True)
    assert np.isnan(got["x"][0]).any()  # (seeds under the ground)
    pf = P.for_run(ref, Fields(ref))
    ps = P.select(pf, dict(box=[-3.0, 3.0, -2.0, 2.0], z=[0.0, 3.0]), "s")
    assert len(ps)
    want_w = pf._sample(ps, "winterp")
    pf.attach(Fields(run))
    got_w = pf._sample(ps, "winterp")
    assert np.isfinite(got_w).any()
    np.testing.assert_allclose(got_w, want_w, rtol=0, atol=1e-4, equal_nan=True)


# ------------------------------------------------------------- W5: the ensemble mean
# (members 1, 2, 3: T = m + 0.1 c + k, U = i + c + m, QVAPOR = 0.01 + 0.001 m + ...,
# so the mean is member 2's state; PH and W are the same in every member)
def test_mean_run_found_and_opened(wofs_root):
    mean = os.path.join(wofs_root, "mean")
    assert models.exists(mean) and not os.path.isdir(mean) and wofs.is_mean(mean)
    assert models.detect(mean).key == "wofs" and models.count(mean) == NC
    assert registry.is_run(mean) and not registry.is_run(mean, "cm1")
    run = models.open_run(mean, workers=1)
    assert isinstance(run, wofs.WoFSMeanRun) and run.path == mean and run.member is None
    assert run.stat == "mean" and "3 members" in run.model_label
    assert "mean state" in run.note and "first time" in run.note
    np.testing.assert_allclose(run.times, [0.0, 180.0, 360.0])
    assert run.time_label(2) == "22:06 UTC" and len(run.parts[0]) == 3
    # one member: no mean listed (but a single-member root still opens as one)
    one = make_wofs(os.path.join(os.path.dirname(wofs_root), "one"), members=(4,))
    assert models.runs_in(one, list(os.scandir(one))) == [one]
    assert models.parts(one) == [os.path.join(one, "mem04")]


@pytest.mark.parametrize("workers", [1, 2])
def test_mean_values(wofs_root, workers):
    """Every field in the files is the member mean (in reader processes: each a share
    of the members); the base state is the mean at the first time."""
    run = models.open_run(os.path.join(wofs_root, "mean"), workers=workers)
    m2 = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    for c in range(NC):
        for n in ("th", "prs", "qv", "uinterp", "vinterp", "winterp", "dbz", "zagl",
                  "zmsl", "th0", "u0", "qv0"):
            np.testing.assert_allclose(run.volume(n, c), m2.volume(n, c), rtol=1e-6,
                                       atol=1e-5, err_msg=f"{n} at {c}")
        np.testing.assert_allclose(run.read_level("th", c, 1), m2.read_level("th", c, 1),
                                   rtol=1e-6)
        np.testing.assert_allclose(run.read_level("UP_HELI_MAX", c), float(c))
        np.testing.assert_allclose(run.heights(c, "msl", w=True),
                                   m2.heights(c, "msl", w=True), atol=1e-4)
        np.testing.assert_allclose(run.heights(c, w=True), m2.heights(c, w=True),
                                   atol=1e-4)
    run.clear_cache()  # (columns from the files, then from the cached volume)
    np.testing.assert_allclose(run.read_box("th", 1, 0, 2, 0, 2)[:, 0, 0],
                               302.1 + np.arange(NK), rtol=1e-6)
    run.volume("th", 1)
    np.testing.assert_allclose(run.read_box("th", 1, 0, 2, 0, 2)[:, 0, 0],
                               302.1 + np.arange(NK), rtol=1e-6)
    prof = run.mean_profiles(["th", "prs0"], 2)
    np.testing.assert_allclose(prof["th"], 302.2 + np.arange(NK), rtol=1e-6)
    np.testing.assert_allclose(prof["prs0"], 1.0e5 - 1000.0 * np.arange(NK))
    # derived fields: from the mean state
    F, F2 = Fields(run), Fields(m2)
    for n in ("thpert", "wmax", "sbcape"):
        np.testing.assert_allclose(F.plane(n, 2), F2.plane(n, 2), rtol=1e-5, atol=1e-5)


def test_mean_source_split():
    src = wofs.WRFMeanSource([(f"f{i}", f"g{i}") for i in range(36)])
    parts = src.split(8)
    assert len(parts) == 8 and sum(len(p.pairs) for p in parts) == 36
    assert [q for p in parts for q in p.pairs] == src.pairs
    assert len(src.split(100)) == 36 and len(src.split(0)) == 1


def test_mean_series_and_trajectories(wofs_root, tmp_path, monkeypatch):
    """Series read the mean in reader processes; trajectories follow the mean winds,
    traced to their own file (not a member's)."""
    from cm1view.core import parcels as P, series as ser, trajcalc
    monkeypatch.setattr(ser, "store", lambda *a, **k: None)
    monkeypatch.setattr(P, "CACHE_DIR", str(tmp_path / "parcels"))
    monkeypatch.setenv("CM1VIEW_TRAJ_MAX_INTERVAL", "0")
    run = models.open_run(os.path.join(wofs_root, "mean"), workers=1)
    m2 = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    rec = ser.normalize(dict(region="domain", reduce="max", field="uinterp",
                             vmode="height", z=1.0))
    got = [ser.compute(r, Fields(r), rec, ser.empty(r, rec), workers=1)[0]["value"]
           for r in (run, m2)]
    np.testing.assert_allclose(got[0], got[1], rtol=1e-6)
    pf, pf2 = P.for_run(run, Fields(run)), P.for_run(m2, Fields(m2))
    assert isinstance(pf, trajcalc.Traced) and pf.path != pf2.path
    box = dict(box=[-3.0, 3.0, -2.0, 2.0], z=[0.0, 3.0])
    tr = pf.trajectories(P.select(pf, box, "s"), ("x", "y", "z"))
    tr2 = pf2.trajectories(P.select(pf2, box, "s"), ("x", "y", "z"))
    for k in "xyz":
        np.testing.assert_allclose(tr[k], tr2[k], atol=1e-4, equal_nan=True)


def test_registry_and_figures_open_the_mean(wofs_root):
    reg = registry.Registry(None, 1, 1)
    r, F = reg.get(os.path.join(wofs_root, "mean"))
    assert isinstance(r, wofs.WoFSMeanRun) and reg.get(os.path.join(wofs_root, "mean"))[0] is r
    assert reg.get(os.path.join(wofs_root, "mem02"))[0] is not r
    assert config.run_key(r.path).endswith("_mean")


def test_demo_ensemble(tmp_path):
    """The synthetic demo (cm1view --demo wofs): found as a root, opens, has terrain, and a
    storm that shows in reflectivity and updraft helicity; the mean differs from a member."""
    from cm1view import demo, demo_wofs
    root = demo_wofs.make(str(tmp_path))
    assert demo_wofs.make(str(tmp_path)) == root  # (up to date: not rewritten)
    assert wofs.members(root) == [1, 2, 3]
    assert demo.is_demo(os.path.join(root, "mem02"))
    run = models.open_run(os.path.join(root, "mem02"), workers=1)
    assert run.terrain and len(run.times) == demo_wofs.NCYCLE
    F = Fields(run)
    t = len(run.times) - 1
    assert F.plane("dbz", t, "level", 2).max() > 30.0
    assert F.plane("UP_HELI_MAX", t, "level", 0).max() > 10.0
    mean = models.open_run(os.path.join(root, "mean"), workers=1)
    a = F.plane("winterp", t, "level", 8)
    b = Fields(mean).plane("winterp", t, "level", 8)
    assert a.shape == b.shape and not np.allclose(a, b)


def test_recent_runs_keep_the_experiment(wofs_root, tmp_path, monkeypatch):
    """A member opened is remembered as its experiment (the run), once."""
    exp = os.path.dirname(wofs_root)
    recent = tmp_path / "recent.json"
    monkeypatch.setattr(registry, "_recent_file", lambda: str(recent))
    monkeypatch.setattr(registry, "_OLD_RECENT", str(tmp_path / "old.json"))
    registry.remember(os.path.join(exp, "mem02"))
    registry.remember(os.path.join(exp, "mean"))
    assert registry.recent_runs() == [exp]
    recent.write_text(f'["{exp}/mem03", "{exp}"]')  # (as kept before: members)
    assert registry.recent_runs() == [exp]


def test_ground_relative_winds_only(wofs_root):
    """No storm motion for WoFS yet: winds are ground-relative only, and the fields
    that take a storm motion (storm-relative helicity, STP, SCP, streamwise
    vorticity) are left out; a saved storm-relative frame draws ground-relative."""
    from cm1view.core import vectors
    from cm1view.core.volume3d import frame_offset
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    assert not run.storm_relative
    assert vectors.frames(run) == {"Ground-relative": "ground"}
    assert vectors.frame_of(run, "storm") == vectors.frame_of(run, "grid") == "ground"
    assert vectors.to_frame(run, 1.0, 2.0, "storm", (5.0, 5.0)) == (1.0, 2.0)
    assert frame_offset(run, "storm", (5.0, 5.0)) == (0.0, 0.0)
    F = Fields(run)
    assert not [d.name for d in F.defs.values() if d.storm]
    assert vectors.frames(None) == vectors.FRAMES  # (other runs: every frame)


# ------------------------------------------------- P1: reading progress of the mean
@pytest.mark.parametrize("workers", [1, 2])
def test_mean_reports_members_and_stops_when_cancelled(wofs_root, workers):
    """Reads within reporting() say how many members of the mean are read so far,
    and stop (Cancelled, nothing half-read cached) once the block is cancelled; an
    explicit cancelled argument still makes load_volumes return False."""
    from cm1view.core.run import Cancelled, reporting
    run = models.open_run(os.path.join(wofs_root, "mean"), workers=workers)
    seen = []
    with reporting(lambda d, n, w: seen.append((d, n, w))):
        run.volume("th", 1)
    assert seen and seen[-1][0] == 1 and seen[-1][1] == 1
    whats = [w for _, _, w in seen]
    assert all(w.startswith("th") for w in whats)
    assert any(w.endswith("members") and "/3 " in w for w in whats)
    with pytest.raises(Cancelled):
        with reporting(None, cancelled=lambda: True):
            run.volume("qv", 2)
    assert run.cached("qv", 2) is None
    assert run.load_volumes(["qv"], 2, cancelled=lambda: True) is False
    assert run.volume("qv", 2).shape == (NK, NJ, NI)  # (and then reads in full)
    # explicit progress and the block's both hear the reads
    mine, block = [], []
    run.clear_cache()
    with reporting(lambda *a: block.append(a)):
        run.load_volumes(["prs"], 0, progress=lambda *a: mine.append(a))
    assert mine and all(a in block for a in mine)


def test_map_says_the_mean_is_being_read(wofs_root):
    """The map's status while a slow map is made: what is read, for how long."""
    from cm1view.viewer.mapview import MapView
    v = type("V", (), {"run": models.open_run(os.path.join(wofs_root, "mean"),
                                              workers=1)})()
    html = MapView._map_loading_html(v, (0, 1, "th · 18/36 members"), 4.2)
    assert "Ensemble mean: reading th · 18/36 members" in html and "4 s" in html
    assert "cv-maploading" in html
    assert "computing" in MapView._map_loading_html(v, None, 0.1)
    v.run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    assert "Loading th · field 2/3" in MapView._map_loading_html(v, (1, 3, "th"), 0.1)


def test_map_boundaries_and_lat_lon(wofs_root):
    """A WoFS map gets a Boundaries pill: layers shown / hidden and restyled in the
    browser only, lat/lon lines with labels, lat, lon in the hover, all kept in a
    session.  A CM1 run has none of it (see test_session for the CM1 viewer)."""
    from cm1view.registry import Registry
    from cm1view.viewer import app as A
    reg = Registry(os.path.join(wofs_root, "mem02"), 4, 2)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    try:
        assert v.geo is not None and "geo" in v.map_drawer.items
        assert v.geo_r["states"].visible and not v.geo_r["counties"].visible
        gen = v.gen["map"]
        v.geo_kinds.value = ["counties"]
        v.geo_width.value = 2.0
        v.geo_color.value = "#000000"
        v.geo_grid.value = True
        assert v.gen["map"] == gen  # (no map redraw)
        assert v.geo_r["counties"].visible and not v.geo_r["states"].visible
        assert v.geo_r["counties"].glyph.line_width == pytest.approx(2.0 * 0.55)
        assert v.geo_r["counties"].glyph.line_color == "#000000"
        assert v.grid_r.visible and len(v.grid_src.data["x"])
        assert v.grid_lab["left"][0].data["text"]
        assert v.map_drawer.items["geo"][0].name.startswith("Boundaries · 2")
        hover = [t for t in v.fig.tools if type(t).__name__ == "HoverTool"
                 and v.img_r in t.renderers][0]
        assert ("lat, lon", "$x{lonlat}") in hover.tooltips and "$x" in hover.formatters
        v.geo_step.value = 0.25
        s = v.session_state()
        assert s["boundaries"] == dict(kinds=["counties"], color="#000000", width=2.0,
                                       grid=True, step=0.25, inset=True)
    finally:
        v.close()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    try:
        assert v.apply_session(s) == []
        assert v._geo_state() == s["boundaries"] and v.geo_r["counties"].visible
        assert v.grid_r.visible
    finally:
        v.close()


def test_figure_map_boundaries(wofs_root, tmp_path):
    """A plan-view figure of a run on a map gets a Map boundaries layer: its lines cut
    to the panel's window (the Texas / New Mexico border runs through the fixture),
    lat/lon lines and labels, all saved with the figure so its script redraws them.
    A run without a projection: no layer in a new figure, a note if one is there."""
    import matplotlib
    matplotlib.use("Agg")
    from cm1view.core import geo
    from cm1view.figures import draw as figdraw, spec as fg
    from cm1view.figures.spec import arrays, bundle
    run = models.open_run(os.path.join(wofs_root, "mem02"), workers=1)
    F = Fields(run)
    sp = fg.default_spec(run, F, 1)
    types = [lay["type"] for lay in sp["layers"]]
    assert types[-1] == "boundaries" and sp["layers"][-1]["kinds"] == list(geo.SHOWN)
    j = len(types) - 1
    sp["layers"][j].update(kinds=["states"], grid=True, step=0.5)
    sp.update(rows=1, cols=1, times=[1], times_s=[float(run.times[1])],
              domain=dict(mode="full", half=12.5, box=None))
    d = arrays.extract(run, F, sp, 0, None)
    xy = d[f"L{j}_b_states"]
    assert xy.shape[0] == 2 and np.isfinite(xy).sum() >= 4
    lon, lat = run.geo.lonlat(xy[0][np.isfinite(xy[0])], xy[1][np.isfinite(xy[1])])
    np.testing.assert_allclose(lon, -103.06, atol=0.03)  # (the border, not the box)
    assert f"L{j}_b_counties" not in d  # (only the chosen kinds)
    assert set(d[f"L{j}_glab_t"]) == {"103° W", "34° N"}
    assert d[f"L{j}_glab"][:, 2].tolist() == [0.0, 1.0]  # (bottom edge, left edge)
    # a storm-centred panel: the same border, from the storm's position
    sp2 = dict(sp, coords="storm", domain=dict(mode="storm", half=2.0, box=None))
    d2 = arrays.extract(run, F, sp2, 0, (1.0, 0.5))
    xy = d2[f"L{j}_b_states"]
    ok = np.isfinite(xy[0])
    lon, _ = run.geo.lonlat(xy[0][ok] + 1.0, xy[1][ok] + 0.5)
    np.testing.assert_allclose(lon, -103.06, atol=0.03)
    # changing what is drawn reads the data again
    sp3 = dict(sp, layers=[dict(lay) for lay in sp["layers"]])
    sp3["layers"][j]["kinds"] = ["counties"]
    assert arrays.data_key(sp3, 0, None) != arrays.data_key(sp, 0, None)
    fig = figdraw.draw(sp, {0: d})
    ax = fig.axes[0]
    assert {t.get_text() for t in ax.texts} >= {"103° W", "34° N"}
    out = bundle.save_bundle(sp, {0: d}, str(tmp_path / "out" / "fig"), run=run)
    with np.load(out["data"]) as z:
        assert f"p0__L{j}_b_states" in z.files and z[f"p0__L{j}_glab_t"].dtype.kind == "U"
    assert "def _boundaries" in open(out["draw"]).read()
    # an idealized run (no projection)
    run.geo = None
    assert "boundaries" not in [lay["type"] for lay in fg.default_spec(run, F, 1)["layers"]]
    d = arrays.extract(run, F, sp, 0, None)
    assert not any(k.startswith(f"L{j}_") for k in d) and "map projection" in d["notes"]


def test_member_switch_loads_the_same_storm(wofs_root, tmp_path, monkeypatch):
    """Each member has its own track file; the Member box shows another member (in
    place) on the storm shown (by name), from that member's file, or says it has none."""
    from cm1view.registry import Registry
    from cm1view.viewer import app as A
    from cm1view.core import track as trk
    monkeypatch.setenv("CM1VIEW_EXPORTS_DIR", str(tmp_path / "exports"))

    def write(path, x):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("storm,time_index,x_km,y_km\n")
            f.write("".join(f"A,{t},{x},0.0\n" for t in range(NC)))
            f.write("".join(f"B,{t},{x + 10},5.0\n" for t in range(NC)))

    reg = Registry(os.path.join(wofs_root, "mem02"), 4, 2)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    member = lambda n: next(q for q in v.part_sel.options.values()  # noqa: E731
                            if q.endswith(n))
    try:
        assert v.trk_storm.visible  # (a member: storms are expected)
        write(v.trk_path.value, 1.0)
        v._refresh_storms()
        v.trk_storm.value = "B"
        assert v.fixes[0]["x"] == 11.0
        v.part_sel.value = member("mem03")
        assert v.run.path.endswith("mem03") and not v.ses_go.value  # (no reload)
        assert v.trk_storm.value == "B" and not v.fixes
        assert "This member has no storm B" in txt(v.trk_status.object)
        assert "mem03" in v.trk_path.value  # (its own track file)
        write(v.trk_path.value, 2.0)
        v._refresh_storms()
        assert v._load_track("B") and v.fixes[0]["x"] == 12.0
        v.part_sel.value = member("mem02")
        assert v.trk_storm.value == "B" and v.fixes[0]["x"] == 11.0
        v.part_sel.value = member("mem03")
        assert v.trk_storm.value == "B" and v.fixes[0]["x"] == 12.0
        assert v.storm_btn.name.startswith("Storm B")
        assert trk.storms(v.trk_path.value) == ["A", "B"]
    finally:
        v.close()


def test_member_switch_keeps_the_view_without_a_reload(wofs_root, tmp_path, monkeypatch):
    """Members (and the mean) share the grid: the Member box swaps the run in place,
    keeping time, view, fills and soundings; per-member save boxes, the figure editor's
    own run and the address follow.  A run on another grid reopens the page."""
    import copy
    import json
    from cm1view.registry import Registry
    from cm1view.viewer import app as A
    from cm1view.viewer import swap
    monkeypatch.setenv("CM1VIEW_EXPORTS_DIR", str(tmp_path / "exports"))
    reg = Registry(os.path.join(wofs_root, "mem02"), 4, 2)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    try:
        v.tslider.value = 2
        field = next(n for n in v.fill_var.values if n and n != v.fill_var.value)
        v.fill_var.value = field
        v.points = [("pt", (1.0, 2.0), None)]
        mean = next(q for q in v.part_sel.options.values() if q.endswith("mean"))
        ser_dir = os.path.dirname(v.ser_path.value)
        v.part_sel.value = mean
        assert v.run is reg.get(mean)[0] and v.F is reg.get(mean)[1]
        assert not v.ses_go.value and v.url_run.value == v.run.path
        assert v.t == 2 and v.fill_var.value == field and v.points[0][1] == (1.0, 2.0)
        assert "Ensemble mean" in v._run_info.object
        assert v.figed.run is v.run and v.figed.data.run is v.run
        assert os.path.dirname(v.ser_path.value) != ser_dir
        assert "mean" in v.ses_path.value and "mean" in v.trk_path.value
        assert v.settings.run_path == v.run.path
        # another grid: not swapped (the page reloads, through a session file)
        other = reg.get(os.path.join(wofs_root, "mem01"))
        assert swap.same_grid(v.run, v.F, *other)
        bigger = copy.copy(other[0])
        bigger.ni += 1
        assert not swap.same_grid(v.run, v.F, bigger, other[1])
        monkeypatch.setattr(swap, "same_grid", lambda *a: False)
        v.part_sel.value = os.path.join(os.path.dirname(mean), "mem01")
        assert v.run.path == mean
        s = json.load(open(v.ses_go.value))
        assert s["run"].endswith("mem01") and s["track"]["member"]
    finally:
        v.close()
