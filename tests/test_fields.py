"""Derived fields and the data layer: θρ, streamwise / crosswise vorticity (domain and
tracked motion), reads shared by concurrent requests, cached derived volumes, one cache
for all runs, and the base state."""
import os
import threading

import netCDF4
import numpy as np

from cm1view import config, track as trk


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
