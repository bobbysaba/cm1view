"""Derived fields and the data layer: θρ, streamwise / crosswise vorticity (domain and
tracked motion), reads shared by concurrent requests, cached derived volumes, one cache
for all runs, and the base state."""
import os
import threading

import netCDF4
import numpy as np

from cm1view import config
from cm1view.core import track as trk


def test_theta_rho_matches_the_definition(reg):
    run, F = reg.get()
    T, K = 4, 10
    with netCDF4.Dataset(run.files[T]) as d:
        g = lambda n: np.asarray(d[n][0, K], np.float64)  # noqa: E731
        q = sum(g(n) for n in ("qc", "qr", "qi", "qs", "qg") if n in d.variables)
        eps = 287.04 / 461.51
        ref = g("th") * (1 + g("qv") / eps) / (1 + g("qv") + q)
    assert np.abs(F.plane("thrho", T, "level", K) - ref).max() < 0.01
    tp = F.plane("thrhopert", T, "level", K)
    assert np.all(np.isfinite(tp)) and tp.max() - tp.min() > 0.5


def test_streamwise_and_crosswise_vorticity(reg):
    run, F = reg.get()
    T, z = 4, 0.5
    ws = F.plane("wstream", T, "height", z)
    wc = F.plane("wcross", T, "height", z)
    xv, yv = run.read_height("xvort", T, z), run.read_height("yvort", T, z)
    u, v = run.read_height("uinterp", T, z), run.read_height("vinterp", T, z)
    # without a track: relative to the domain motion (the grid-relative winds)
    sp = np.maximum(np.hypot(u, v), 1e-6)
    assert np.nanmax(np.abs(ws - (xv * u + yv * v) / sp)) < 1e-6
    assert np.nanmax(np.abs(ws ** 2 + wc ** 2 - xv ** 2 - yv ** 2)) < 1e-6
    # a storm motion changes it
    fixes = trk.load(run, config.find_track(run.path))
    storm = trk.motion(run, fixes)[T]
    ws1 = F.plane("wstream", T, "height", z, storm=tuple(storm))
    assert np.nanmax(np.abs(ws1 - ws)) > 1e-4


def test_concurrent_requests_read_once(reg):
    run, F = reg.get()
    T = 5
    run.forget(["qv"], T)
    reads = []
    orig = run._read_into_cache

    def counting(missing, *a, **k):
        reads.extend(missing)
        return orig(missing, *a, **k)
    run._read_into_cache = counting
    try:
        ths = [threading.Thread(target=run.volume, args=("qv", T)) for _ in range(3)]
        [x.start() for x in ths]
        [x.join() for x in ths]
    finally:
        run._read_into_cache = orig
    assert reads.count("qv") == 1


def test_plane_reads_during_a_volume_read(reg):
    run, F = reg.get()
    th = threading.Thread(target=run.volume, args=("th", 6))
    th.start()
    assert F.plane("winterp", 6, "height", 3.0).shape == (len(run.yh), len(run.xh))
    th.join()


def test_derived_volumes_are_cached(reg):
    run, F = reg.get()
    T = 4
    assert F.volume("thpert", T) is F.volume("thpert", T)
    st = (12.0, 9.0)
    assert F.volume("wstream", T, st) is F.volume("wstream", T, st)
    assert F.volume("wstream", T, (0.0, 0.0)) is not F.volume("wstream", T, st)
    F.forget(T, ["th"])
    assert run.cached("~thpert", T) is None


def test_one_cache_for_all_runs(reg, demo_root):
    run, _ = reg.get()
    run.volume("th", 3)
    n = sum(1 for k in run._vc._d if k[0] == run.path)
    run2, _ = reg.get(os.path.join(demo_root, "demo", "supercell_weak"))
    run2.volume("th", len(run2.files) - 1)
    assert run._vc is run2._vc
    assert sum(1 for k in run._vc._d if k[0] == run.path) == n


def test_base_state_is_the_domain_mean(reg):
    run, _ = reg.get()
    m = run.mean_profiles(("th0", "u0"), 0)
    with netCDF4.Dataset(run.files[0]) as d:
        col = np.asarray(d["th0"][0, :, 0, 0], float)
    assert np.abs(m["th0"] - col).max() < 1e-3


def test_derivatives_of_any_field(reg):
    """'ddz.w', 'ddx.', 'ddy.', 'gradh.' (per km): not in the field lists; maps (at a
    level or a height) agree with the volume's np.gradient on the stretched levels, so
    maps and cross-sections agree; ∂/∂z only of 3D fields."""
    from cm1view.core.fields import deriv_name, deriv_options, split_deriv
    run, F = reg.get()
    T, K = 4, 6
    assert split_deriv("ddz.winterp") == ("ddz", "winterp")
    assert split_deriv("winterp") == ("", "winterp") and deriv_name("", "th") == "th"
    assert "ddz.winterp" in F and "ddq.winterp" not in F and "ddz.nothing" not in F
    assert not any("ddz.winterp" in g.values() for g in F.groups().values())
    d = F["ddz.winterp"]
    assert d.units == "10⁻³ s⁻¹" and d.ndim == 3 and d.diverging and d.vrange == (-10, 10)
    w = np.asarray(F.volume("winterp", T), np.float64)
    ref = np.gradient(w, run.z, axis=0)  # (km: per km)
    vol = F.volume("ddz.winterp", T)
    assert vol is F.volume("ddz.winterp", T)
    assert np.abs(vol - ref).max() < 1e-3 * max(1.0, np.abs(ref).max())
    assert np.abs(F.plane("ddz.winterp", T, "level", K) - ref[K]).max() < \
        1e-3 * max(1.0, np.abs(ref).max())
    zk = 0.5 * (run.z[K] + run.z[K + 1])
    mid = 0.5 * (ref[K] + ref[K + 1])
    assert np.abs(F.plane("ddz.winterp", T, "height", zk) - mid).max() < \
        1e-3 * max(1.0, np.abs(ref).max())
    assert np.allclose(F.plane("ddz.winterp", T, "colmax", 0), ref.max(axis=0), atol=1e-3)
    # horizontal, of a derived field too, on the grid's x / y
    th = np.asarray(F.plane("thpert", T, "height", 1.0), np.float64)
    gx, gy = np.gradient(th, run.xh, axis=-1), np.gradient(th, run.yh, axis=-2)
    assert np.allclose(F.plane("ddx.thpert", T, "height", 1.0), gx, atol=1e-4)
    assert np.allclose(F.plane("ddy.thpert", T, "height", 1.0), gy, atol=1e-4)
    assert np.allclose(F.plane("gradh.thpert", T, "height", 1.0), np.hypot(gx, gy), atol=1e-4)
    assert F["gradh.thpert"].vrange[0] == 0.0 and F["ddx.thpert"].units == "K km⁻¹"
    # a 2D field: horizontal derivatives only
    two = next(n for n, x in F.defs.items() if x.ndim == 2)
    assert "ddz." + two not in F and "ddx." + two in F
    assert "∂/∂z" not in deriv_options(F[two]) and "∂/∂z" in deriv_options(F["winterp"])
    assert F.plane("ddx." + two, T).shape == (run.nj, run.ni)
    F.forget(T, ["winterp"])
    assert run.cached("~ddz.winterp", T) is None


def test_vorticity_tendencies(reg):
    """ζ stretching, tilting, their sum and Okubo–Weiss (10⁻⁴ s⁻²) against np.gradient of
    the volumes; deps naming derivatives read their base fields, are not pointwise, and
    are forgotten with them."""
    run, F = reg.get()
    T, K = 4, 5
    assert F["zstretch"].group == "Vorticity tendencies"
    assert sorted(F.native_deps("ztend")) == ["winterp", "xvort", "yvort", "zvort"]
    assert F.native_deps("okubo") == ["uinterp", "vinterp"]
    assert not F["ztilt"].pointwise and F["ztilt"].units == "10⁻⁴ s⁻²"
    assert "Vorticity tendencies" in F.groups()
    v = {n: np.asarray(F.volume(n, T), np.float64)
         for n in ("zvort", "xvort", "yvort", "winterp", "uinterp", "vinterp")}
    wz = np.gradient(v["winterp"], run.z, axis=0) * 1e-3  # 1/s
    wx = np.gradient(v["winterp"], run.xh, axis=-1) * 1e-3
    wy = np.gradient(v["winterp"], run.yh, axis=-2) * 1e-3
    ref = {"zstretch": 1e4 * v["zvort"] * wz,
           "ztilt": 1e4 * (v["xvort"] * wx + v["yvort"] * wy)}
    ref["ztend"] = ref["zstretch"] + ref["ztilt"]
    g = {(c, a): np.gradient(v[c + "interp"], x, axis=a) * 1e-3
         for c in "uv" for a, x in ((-1, run.xh), (-2, run.yh))}
    ux, uy, vx, vy = g["u", -1], g["u", -2], g["v", -1], g["v", -2]
    ref["okubo"] = 1e4 * ((ux - vy) ** 2 + (vx + uy) ** 2 - (vx - uy) ** 2)
    for n, r in ref.items():
        tol = 1e-3 * max(1.0, np.abs(r).max())
        assert np.abs(F.volume(n, T) - r).max() < tol, n
        assert np.abs(F.plane(n, T, "level", K) - r[K]).max() < tol, n
        assert np.allclose(F.plane(n, T, "colmax", 0), r.max(axis=0), atol=tol), n
    # at a height: the inputs' planes there (∂w/∂z between the levels' values)
    a = F.plane("zstretch", T, "height", 1.0)
    b = 10.0 * F.plane("zvort", T, "height", 1.0) * F.plane("ddz.winterp", T, "height", 1.0)
    assert np.allclose(a, b, atol=1e-5)
    # and a derivative of one: ∂/∂z of stretching
    assert np.abs(F.volume("ddz.zstretch", T) - np.gradient(ref["zstretch"], run.z, axis=0)
                  ).max() < 1e-2 * max(1.0, np.abs(ref["zstretch"]).max())
    F.forget(T, ["winterp"])
    assert run.cached("~zstretch", T) is None and run.cached("~ddz.zstretch", T) is None


def test_column_fields(reg):
    """Updraft helicity integrates w ζ over exactly its layer (cells between the zf levels,
    clipped to it); the maxima are over the levels whose cells reach into the layer; the
    fields are 2D and have horizontal derivatives."""
    from cm1view.core.fields import column_levels
    run, F = reg.get()
    T = 4
    assert F["uh25"].group == "Column fields" and F["uh25"].ndim == 2
    assert F["uh25"].column and not F["uh25"].pointwise
    assert sorted(F.native_deps("uh25")) == ["winterp", "zvort"]
    assert "uh25" in F.groups(2)["Column fields"].values()
    ks, dz = column_levels(run.z, run.zf, 2.0, 5.0)
    assert abs(dz.sum() - 3000.0) < 1e-6 and (dz > 0).all()
    assert run.zf[ks[0]] <= 2.0 < run.zf[ks[0] + 1] and run.zf[ks[-1]] < 5.0 <= run.zf[ks[-1] + 1]
    ks_all, dz_all = column_levels(run.z, run.zf, 0.0, None)
    assert ks_all == list(range(run.nk)) and abs(dz_all.sum() - 1000 * run.zf[-1]) < 1e-6
    w = np.asarray(F.volume("winterp", T), np.float64)
    z = np.asarray(F.volume("zvort", T), np.float64)
    ref = np.tensordot(dz, w[ks] * z[ks], axes=1)
    a = F.plane("uh25", T)
    assert a.shape == (run.nj, run.ni)
    assert np.abs(a - ref).max() < 1e-4 * max(1.0, np.abs(ref).max())
    assert np.allclose(F.plane("uh25", T, "level", 7), a)  # (2D: no level)
    assert np.array_equal(F.volume("uh25", T), a)
    k1, _ = column_levels(run.z, run.zf, 0.0, 1.0)
    assert np.allclose(F.plane("zvmax01", T), z[k1].max(axis=0), atol=1e-6)
    assert np.allclose(F.plane("wmax", T), w.max(axis=0), atol=1e-5)
    assert np.allclose(F.plane("ddx.uh25", T), np.gradient(a, run.xh, axis=-1), atol=1e-3)


def test_sounding_kinematics_match_the_soundings(reg):
    """Bulk shear and storm-relative helicity maps give the sounding analysis's values
    at sampled columns (helicity to ~1%: the sounding's 10 m grid stops short of the
    layer top); helicity follows the storm motion it is given, shear does not."""
    from cm1view.core import thermo
    from cm1view.core.fields import column_levels
    run, F = reg.get()
    T, storm = 4, (10.0, 5.0)
    assert F["srh01"].group == "Sounding parameters" and F["srh01"].ndim == 2
    assert F["srh01"].storm and not F["shear06"].storm
    assert sorted(F.native_deps("srh03")) == ["uinterp", "vinterp"]
    ks, dz = column_levels(run.z, run.zf, 0.0, 6.0, edges=True)
    assert ks[0] == 0 and run.z[ks[-1]] > 6.0 > run.z[ks[-2]] and dz[-1] == 0.0
    vol = {n: np.asarray(F.volume(n, T), np.float64) for n in ("uinterp", "vinterp", "th",
                                                                "qv", "prs")}
    planes = {n: F.plane(n, T, storm=storm) for n in ("shear01", "shear06", "srh01",
                                                       "srh03")}
    z = 1000.0 * np.asarray(run.z, np.float64)
    for j, i in ((5, 7), (run.nj // 2, run.ni // 2), (run.nj - 3, 2)):
        col = {n: a[:, j, i] for n, a in vol.items()}
        kin = thermo.analyze(z, 100.0 * col["prs"], col["th"], col["qv"] / 1000.0,
                             col["uinterp"] + run.umove, col["vinterp"] + run.vmove,
                             storm="custom", custom=storm)["kin"]
        for n, k in (("shear01", "shear01"), ("shear06", "shear06")):
            assert abs(planes[n][j, i] - np.hypot(*kin[k])) < 1e-3, n
        for n, k in (("srh01", "srh1"), ("srh03", "srh3")):
            assert abs(planes[n][j, i] - kin[k]) <= 0.02 * abs(kin[k]) + 1.0, n
    assert not np.allclose(F.plane("srh01", T, storm=(0.0, 0.0)), planes["srh01"])
    assert np.array_equal(F.plane("shear06", T, storm=(0.0, 0.0)), planes["shear06"])


def test_parcel_maps_match_the_soundings(reg, monkeypatch):
    """CAPE, CIN and LCL maps of the SB, ML and MU parcels give the sounding analysis's
    values at sampled columns, STP its fixed-layer STP (to the ~1% of its helicity);
    with a column stride, each block shows its middle column, in a series too."""
    from cm1view.core import fields as FF, series as S, thermo
    run, F = reg.get()
    T, storm = 4, (10.0, 5.0)
    assert F["mlcape"].group == "Sounding parameters" and F["mlcape"].ndim == 2
    assert F["mlcape"].costly and F["stp"].storm and not F["mucin"].storm
    assert sorted(F.native_deps("scp")) == ["prs", "qv", "th", "uinterp", "vinterp"]
    assert FF.column_stride(run) == 1  # (auto: every column of a small domain)
    vol = {n: np.asarray(run.volume(n, T), np.float64)
           for n in ("prs", "th", "qv", "uinterp", "vinterp")}
    names = [f"{k}{q}" for k in thermo.PARCELS for q in ("cape", "cin", "lcl")]
    P = {n: F.plane(n, T, storm=storm) for n in names + ["stp"]}
    z = 1000.0 * np.asarray(run.z, np.float64)
    for j, i in ((5, 7), (run.nj // 2, run.ni // 2), (run.nj - 3, 2)):
        c = {n: a[:, j, i] for n, a in vol.items()}
        r = thermo.analyze(z, c["prs"], c["th"], c["qv"], c["uinterp"] + run.umove,
                           c["vinterp"] + run.vmove, storm="custom", custom=storm)
        for k in thermo.PARCELS:
            assert abs(P[f"{k}cape"][j, i] - r[k]["cape"]) < 0.01, k
            assert abs(P[f"{k}cin"][j, i] - r[k]["cin"]) < 0.01, k
            assert abs(P[f"{k}lcl"][j, i] - r[k]["lcl_z"]) < 0.01, k
        ref = r["comp"]["stp_fixed"]
        assert abs(P["stp"][j, i] - ref) <= 0.02 * abs(ref) + 1e-3
    assert P["mucape"].max() > 1000.0 and P["sbcin"].min() < 0.0
    assert np.all(np.isfinite(F.plane("scp", T, storm=storm)))

    monkeypatch.setitem(config._state["cli"], "column_stride", (3, "test"))
    assert FF.column_stride(run) == 3
    s3 = F.plane("mlcape", T)
    mid = lambda n: np.minimum(np.arange(n) // 3 * 3 + 1, n - 1)  # noqa: E731
    assert np.array_equal(s3, P["mlcape"][np.ix_(mid(run.nj), mid(run.ni))])
    r = S.normalize(dict(field="mlcape", vmode="2d", region="box",
                         box=(10.3, 31.1, 12.2, 29.7), reduce="mean"))
    ds, skipped = S.compute(run, F, r, S.empty(run, r), times=[T], workers=1)
    i0, i1, j0, j1 = S.region_at(run, r, None)[:4]
    ref = float(np.mean(s3[j0:j1, i0:i1], dtype=np.float64))
    assert not skipped and abs(ds.value.values[T] - ref) < 1e-3 * abs(ref)
