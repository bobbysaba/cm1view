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
