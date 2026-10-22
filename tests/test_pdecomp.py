"""Pressure decomposition with cm1view's solver (or the pdecomp_script setting's).
Works on copies of the demo run's first files (never on real output): computing one
time, one decomposition at a time, writing into the file and reading it back, and a
failed write that keeps the result in memory."""
import os
import shutil
import stat
import threading
import time

import netCDF4
import numpy as np
import pytest

from cm1view import pdecomp
from cm1view.registry import Registry
from conftest import txt, wait


@pytest.fixture
def copy_run(demo_run, tmp_path):
    """A writable copy of the demo run: namelist + the first three files."""
    dst = tmp_path / "pd_copy"
    dst.mkdir()
    shutil.copy(os.path.join(demo_run, "namelist.input"), dst)
    for n in (1, 2, 3):
        shutil.copy(os.path.join(demo_run, f"cm1out_{n:06d}.nc"), dst)
    reg = Registry(str(dst), 4, 1)
    run, F = reg.get()
    yield run, F, reg


def test_compute_from_the_map(copy_run):
    from cm1view import app as A
    run, F, reg = copy_run
    v = A.Viewer(run, F, reg=reg)
    v.main()
    try:
        v.tslider.value = 1
        v.fill_var.value = "p_b"
        v.fill_mode.value, v.fill_lvl.value = "level", 10.0
        v.request_map()
        wait(lambda: v.pd_row.visible, 120, "compute button")
        v.pd_write.value = False
        v._on_pd_compute(None)
        wait(lambda: any(s in txt(v.status.object) for s in
                         ("computed in", "failed", "needs about")), 900, "decomposition")
        assert "computed in" in txt(v.status.object), txt(v.status.object)
        assert all((n, 1) in run.extra for n in pdecomp.NAMES)
        for n in ("acc_dyn", "acc_tot", "p_dyn"):
            assert np.isfinite(np.nanmax(F.plane(n, 1, "height", 3.0)))
    finally:
        v.close()


def test_one_at_a_time(copy_run):
    run, _, _ = copy_run
    phases = {1: [], 2: []}
    res, err = {}, {}

    def job(t):
        try:
            res[t] = pdecomp.compute(run, t, lambda s, ph: phases[t].append(ph))
        except Exception as e:  # noqa: BLE001
            err[t] = e

    a = threading.Thread(target=job, args=(1,))
    a.start()
    wait(lambda: phases[1], 300, "first started")
    b = threading.Thread(target=job, args=(2,))
    b.start()
    with pytest.raises(RuntimeError):
        pdecomp.compute(run, 1)  # the same time again
    a.join()
    b.join()
    assert not err, err
    assert "waiting for another decomposition" in phases[2]
    assert pdecomp.running(run) == []
    assert all((n, t) in run.extra for n in pdecomp.NAMES for t in (1, 2))


def test_write_and_read_back(copy_run):
    from cm1view.fields import Fields
    from cm1view.run import CM1Run
    run, _, _ = copy_run
    r = pdecomp.compute(run, 1, write=True)
    assert r["wrote"], r.get("write_error")
    assert not run._writing
    with netCDF4.Dataset(run.files[1]) as d:
        for n in pdecomp.NAMES:
            assert getattr(d[n], "pdecomp_version", "")
            assert np.abs(np.asarray(d[n][0, 10]) - run.extra[(n, 1)][10]).max() < 1e-3
    run2 = CM1Run(run.path, cache_gb=1, workers=1)
    assert run2.in_file("p_b", 1)
    a = Fields(run2).plane("p_b", 1, "level", 10)
    assert np.abs(a - run.extra[("p_b", 1)][10]).max() < 1e-3


def test_failed_write_keeps_the_result(copy_run):
    run, F, _ = copy_run
    T, path = 1, run.files[1]
    with netCDF4.Dataset(path) as d:
        before = set(d.variables)
    phases, res, err = [], {}, {}

    def job():
        try:
            res[T] = pdecomp.compute(run, T, lambda s, ph: phases.append(ph), write=True)
        except Exception as e:  # noqa: BLE001
            err[T] = e

    mode = os.stat(path).st_mode
    th = threading.Thread(target=job)
    th.start()
    while "computing" not in phases and th.is_alive():
        time.sleep(0.2)
    os.chmod(path, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    try:
        th.join()
    finally:
        os.chmod(path, mode)
    assert T in res, err.get(T)
    assert not res[T]["wrote"] and res[T]["write_error"]
    assert all((n, T) in run.extra for n in pdecomp.NAMES) and not run._writing
    with netCDF4.Dataset(path) as d:
        assert set(d.variables) == before
    assert np.isfinite(np.nanmax(F.plane("p_b", T, "level", 10)))


def test_solver_satisfies_the_pressure_equation(demo_run):
    """The solved Exner perturbation, put back into the discrete operator, gives the
    forcing (open lateral boundaries: zero-gradient images)."""
    from cm1view import pdecomp_solver as P
    files = sorted(f for f in os.listdir(demo_run) if f.startswith("cm1out_"))
    with netCDF4.Dataset(os.path.join(demo_run, files[0])) as d0:
        dom, base = P.domain_info(d0), P.compute_base_state(d0)
    solver = P.setup_pressure_solver(dom, base, P.lbc_type(demo_run + "/"))
    assert not solver["isperiodic"]
    with netCDF4.Dataset(os.path.join(demo_run, files[4])) as d:
        B = P.compute_buoyancy(d, base)
    rho0 = base["rho0"][:, None, None]
    rb = P.interp_to_w_levels(rho0 * B, dom)
    F = (rb[1:] - rb[:-1]) / dom["dz_layer"][:, None, None]
    pi = P.solve_pressure_equation(F, solver)

    def lap(a, axis, h):
        e = np.concatenate([a.take([0], axis), a, a.take([-1], axis)], axis)
        n = a.shape[axis]
        return (e.take(range(2, n + 2), axis) - 2 * a + e.take(range(n), axis)) / h ** 2

    H, Hf = base["H"], solver["Hf"]
    flux = np.zeros((pi.shape[0] + 1,) + pi.shape[1:])
    flux[1:-1] = Hf[:, None, None] * np.diff(pi, axis=0) / dom["dz_center"][:, None, None]
    lhs = P.cp * (H[:, None, None] * (lap(pi, 2, dom["dx"]) + lap(pi, 1, dom["dy"]))
                  + np.diff(flux, axis=0) / dom["dz_layer"][:, None, None])
    assert np.abs(lhs - F).max() < 1e-6 * np.abs(F).max()
