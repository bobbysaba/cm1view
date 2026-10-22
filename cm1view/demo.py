"""Synthetic CM1 output for demos and tests:  python -m cm1view.demo OUTDIR

Writes small runs in CM1's output layout (output_format = 2: one time per file,
cm1out_NNNNNN.nc, plus namelist.input) under OUTDIR/demo/, and their storm tracks under
OUTDIR/storm_tracks/:

  demo/supercell        a rotating, tilted updraft with a rear-flank cold pool, a
                        precipitation core and an anvil, moving across a translating
                        grid, plus a weaker second cell 15 km away
  demo/supercell_weak   the same storm with a weak mesocyclone (a tor / ntor pair)

The environment is a Weisman–Klemp sounding with a quarter-circle hodograph. The fields
are analytic, not a simulation, but they are shaped and named like CM1 output (staggered
u/v/w, base-state fields, running-max swaths, one horizontal level per chunk), so every
part of the viewer has something to show. The first file is the undisturbed base state at
t = 0, as in CM1. The output is deterministic: the same version writes the same values.
"""

import argparse
import hashlib
import os

import numpy as np

VERSION = 1  # bump when the fields change: cached copies are rewritten

G, RD, RV, CP, P00 = 9.81, 287.04, 461.5, 1005.7, 1.0e5
EPS, KAPPA = RD / RV, RD / CP

NI, NK, DX = 96, 40, 0.5  # grid points per side, levels, km
TIMES = [0.0] + [3600.0 + 300.0 * n for n in range(9)]  # s
UMOVE, VMOVE = 12.0, 2.0  # grid translation (m/s)
STORM = (15.0, 3.0)  # ground-relative storm motion (m/s)
CELL0 = (-10.0, -6.0)  # supercell position at 3600 s, grid-relative (km)
CELL2 = (6.0, 8.0)  # second cell, same motion

RUNS = {"supercell": dict(vmax=22.0, wmax=35.0),
        "supercell_weak": dict(vmax=8.0, wmax=30.0)}


# ------------------------------------------------------------------ grid / base state
def grid():
    xf = (np.arange(NI + 1) - NI / 2) * DX  # km, origin at the domain centre
    dz = 0.1 + 0.6 * np.arange(NK) / (NK - 1)  # stretched: 100 m to 700 m
    zf = np.concatenate([[0.0], np.cumsum(dz)])
    return dict(xf=xf, xh=0.5 * (xf[:-1] + xf[1:]), zf=zf, z=0.5 * (zf[:-1] + zf[1:]))


def _qvs(T, p):
    es = 611.2 * np.exp(17.67 * (T - 273.15) / (T - 29.65))
    return EPS * es / np.maximum(p - es, 1.0)


def sounding(zkm):
    """Weisman–Klemp (1982) θ, qv, p, π at heights zkm (hydrostatic, 1000 hPa at z = 0)."""
    z = np.linspace(0.0, 20.0, 4001)
    ztr, thtr, ttr = 12.0, 343.0, 213.0
    th = np.where(z <= ztr, 300.0 + (thtr - 300.0) * (z / ztr) ** 1.25,
                  thtr * np.exp(G * (z - ztr) * 1000.0 / (CP * ttr)))
    rh = np.where(z <= ztr, 1.0 - 0.75 * (z / ztr) ** 1.25, 0.25)
    qv = np.zeros_like(z)
    for _ in range(4):
        thv = th * (1.0 + qv / EPS) / (1.0 + qv)
        dpi = G / (CP * thv)
        pi = 1.0 - np.concatenate([[0.0], np.cumsum(0.5 * (dpi[1:] + dpi[:-1])
                                                    * np.diff(z) * 1000.0)])
        p = P00 * pi ** (1.0 / KAPPA)
        qv = np.minimum(rh * _qvs(th * pi, p), 0.014)
    return {k: np.interp(zkm, z, a) for k, a in (("th", th), ("qv", qv), ("p", p),
                                                 ("pi", pi))}


def hodograph(zkm):
    """Quarter circle to 2 km, then straight to (25, 10) m/s at 6 km (ground-relative)."""
    phi = 0.5 * np.pi * np.clip(zkm / 2.0, 0.0, 1.0)
    u = np.where(zkm < 2.0, 10.0 * (1.0 - np.cos(phi)),
                 10.0 + 15.0 * np.clip((zkm - 2.0) / 4.0, 0.0, 1.0))
    v = np.where(zkm < 2.0, 10.0 * np.sin(phi), 10.0)
    return u, v


# ------------------------------------------------------------------ storm
def _centres(t):
    """Grid-relative (x, y) km of the supercell and the second cell at time t (s)."""
    dt = (t - 3600.0) / 1000.0
    sx, sy = (STORM[0] - UMOVE) * dt, (STORM[1] - VMOVE) * dt
    return (CELL0[0] + sx, CELL0[1] + sy), (CELL2[0] + sx, CELL2[1] + sy)


def _amp(t):
    return 0.0 if t < 3600.0 else 0.6 + 0.4 * min(1.0, (t - 3600.0) / 1200.0)


class Storm:
    """Analytic perturbation fields at time t; coordinates in km, broadcastable."""

    def __init__(self, t, vmax, wmax):
        self.a = _amp(t)
        (self.xc, self.yc), (self.x2, self.y2) = _centres(t)
        self.vmax, self.wmax = vmax, wmax

    def _axis(self, Z):  # the updraft and mesocyclone tilt downshear
        return self.xc + 0.25 * Z, self.yc + 0.05 * Z

    def w(self, X, Y, Z):
        ax, ay = self._axis(Z)
        r2 = ((X - ax) ** 2 + (Y - ay) ** 2) / 3.0 ** 2
        up = self.wmax * np.sin(np.pi * np.clip(Z / 12.0, 0, 1)) * np.exp(-r2)
        rd2 = ((X - self.xc + 4.0) ** 2 + (Y - self.yc + 3.0) ** 2) / 3.0 ** 2
        down = -6.0 * np.sin(np.pi * np.clip(Z / 4.0, 0, 1)) * np.exp(-rd2)
        r22 = ((X - self.x2) ** 2 + (Y - self.y2) ** 2) / 2.5 ** 2
        cell2 = 12.0 * np.sin(np.pi * np.clip(Z / 10.0, 0, 1)) * np.exp(-r22)
        return self.a * (up + down + cell2)

    def _vt(self, X, Y, Z):
        """Tangential wind of the mesocyclone and the offsets from its axis."""
        ax, ay = self._axis(Z)
        dx, dy = X - ax, Y - ay
        r = np.maximum(np.hypot(dx, dy), 1e-6)
        rm = 2.5
        fz = (0.4 + 0.6 * np.exp(-((Z - 3.0) / 2.5) ** 2)) * np.exp(
            -(np.maximum(Z - 8.0, 0.0) / 2.0) ** 2)
        vt = self.a * self.vmax * fz * (r / rm) * np.exp(0.5 * (1.0 - (r / rm) ** 2))
        return vt, dx / r, dy / r, fz, r / rm

    def uv(self, X, Y, Z):
        vt, cx, cy, _, _ = self._vt(X, Y, Z)
        # outflow from the cold pool, low levels only
        ox, oy = X - self.xc + 5.0, Y - self.yc + 4.0
        ro = np.maximum(np.hypot(ox, oy), 1e-6)
        out = self.a * 8.0 * (ro / 5.0) * np.exp(-(ro / 5.0) ** 2) * np.exp(-Z / 0.8)
        return -vt * cy + out * ox / ro, vt * cx + out * oy / ro

    def cold(self, X, Y, Z):
        """Cold-pool shape (1 at its centre near the ground)."""
        return np.exp(-(((X - self.xc + 5.0) ** 2 + (Y - self.yc + 4.0) ** 2) / 6.0 ** 2)
                      - Z / 1.5)

    def thp(self, X, Y, Z):
        ax, ay = self._axis(Z)
        warm = 4.0 * np.exp(-((X - ax) ** 2 + (Y - ay) ** 2) / 3.0 ** 2) * np.sin(
            np.pi * np.clip(Z / 12.0, 0, 1))
        return self.a * (warm - 6.0 * self.cold(X, Y, Z))

    def prsp(self, X, Y, Z, rho0):
        _, _, _, fz, rr = self._vt(X, Y, Z)
        low = -rho0 * (self.a * self.vmax * fz) ** 2 * np.exp(-rr ** 2)
        return low + self.a * 150.0 * self.cold(X, Y, Z)

    def hydro(self, X, Y, Z):
        a, xc, yc = self.a, self.xc, self.yc
        g = lambda x0, y0, rx, ry=None: np.exp(  # noqa: E731
            -((X - x0) / rx) ** 2 - ((Y - y0) / (ry or rx)) ** 2)
        ax, ay = self._axis(Z)
        wup = np.clip(self.w(X, Y, Z) / max(self.a * 8.0, 1e-6), 0, 1) if a else 0 * X
        qc = 0.002 * wup * np.exp(-((Z - 6.0) / 3.5) ** 2)
        qr = a * np.clip((7.0 - Z) / 4.0, 0, 1) * (0.006 * g(xc + 4.0, yc + 2.0, 4.0)
                                                    + 0.003 * g(xc - 3.0, yc - 2.0, 2.5))
        qg = a * 0.003 * g(ax + 1.0, ay, 3.0) * np.exp(-((Z - 6.0) / 2.5) ** 2)
        qs = a * 0.0015 * g(xc + 12.0, yc + 2.0, 12.0, 5.0) * np.exp(-((Z - 10.0) / 1.5) ** 2)
        qi = a * 0.0008 * g(xc + 10.0, yc + 2.0, 10.0, 4.0) * np.exp(-((Z - 11.0) / 1.2) ** 2)
        qc2 = a * 0.0015 * g(self.x2, self.y2, 2.5) * np.exp(-((Z - 5.0) / 2.5) ** 2)
        return dict(qc=qc + qc2, qr=qr, qi=qi, qs=qs, qg=qg)


# ------------------------------------------------------------------ fields
def _destag(a, axis):
    s0 = [slice(None)] * a.ndim
    s1 = [slice(None)] * a.ndim
    s0[axis], s1[axis] = slice(None, -1), slice(1, None)
    return 0.5 * (a[tuple(s0)] + a[tuple(s1)])


def fields(t, vmax, wmax):
    """All 3D fields at time t on CM1's grids, float32, (z, y, x)."""
    g = grid()
    z, zf, xh, xf = g["z"], g["zf"], g["xh"], g["xf"]
    Z, Zf = z[:, None, None], zf[:, None, None]
    Yh, Yf = xh[None, :, None], xf[None, :, None]
    Xh, Xf = xh[None, None, :], xf[None, None, :]
    full = (NK, NI, NI)
    bs = sounding(z)
    u0, v0 = hodograph(z)
    u0, v0 = u0 - UMOVE, v0 - VMOVE  # CM1 writes winds relative to the moving grid
    st = Storm(t, vmax, wmax)

    th0 = np.broadcast_to(bs["th"][:, None, None], full)
    qv0 = np.broadcast_to(bs["qv"][:, None, None], full)
    prs0 = np.broadcast_to(bs["p"][:, None, None], full)
    pi0 = np.broadcast_to(bs["pi"][:, None, None], full)
    rho0 = bs["p"] / (RD * bs["th"] * bs["pi"] * (1.0 + bs["qv"] / EPS) / (1.0 + bs["qv"]))

    up, _ = st.uv(Xf, Yh, Z)
    _, vp = st.uv(Xh, Yf, Z)
    u = u0[:, None, None] + up + 0 * Yh
    v = v0[:, None, None] + vp + 0 * Xh
    w = st.w(Xh, Yh, Zf)
    w[0], w[-1] = 0.0, 0.0
    th = th0 + st.thp(Xh, Yh, Z)
    prs = prs0 + st.prsp(Xh, Yh, Z, rho0[:, None, None])
    pi = (prs / P00) ** KAPPA
    T = th * pi
    q = st.hydro(Xh, Yh, Z)
    winterp = _destag(w, 0)
    sat = np.clip(winterp / 4.0, 0.0, 1.0)
    qv = qv0 + (np.minimum(_qvs(T, prs), 0.025) - qv0) * sat
    qv = qv * (1.0 - 0.25 * st.a * st.cold(Xh, Yh, Z))
    rho = prs / (RD * T * (1.0 + qv / EPS))
    ze = (3.63e9 * (rho * q["qr"]) ** 1.75 + 1.0e9 * (rho * q["qg"]) ** 1.75
          + 2.0e8 * (rho * (q["qs"] + q["qi"])) ** 1.75)
    dbz = np.maximum(10.0 * np.log10(np.maximum(ze, 1e-3)), 0.0)

    uinterp, vinterp = _destag(u, 2), _destag(v, 1)
    dxm = DX * 1000.0
    zm = z * 1000.0
    ddx = lambda a: np.gradient(a, dxm, axis=2)  # noqa: E731
    ddy = lambda a: np.gradient(a, dxm, axis=1)  # noqa: E731
    ddz = lambda a: np.gradient(a, zm, axis=0)  # noqa: E731
    r = np.hypot(Xh - st._axis(Zf)[0], Yh - st._axis(Zf)[1])
    tke = 0.2 + st.a * 8.0 * np.exp(-(r / 3.0) ** 2) * np.sin(np.pi * np.clip(Zf / 12.0, 0, 1))
    out = dict(th=th, prs=prs, pi=pi, rho=rho, qv=qv, **q, dbz=dbz,
               uinterp=uinterp, vinterp=vinterp, winterp=winterp,
               xvort=ddy(winterp) - ddz(vinterp), yvort=ddz(uinterp) - ddx(winterp),
               zvort=ddx(vinterp) - ddy(uinterp),
               pi0=pi0, th0=th0, prs0=prs0, qv0=qv0,
               u=u, u0=np.broadcast_to(u0[:, None, None], u.shape),
               v=v, v0=np.broadcast_to(v0[:, None, None], v.shape), w=w, tke=tke)
    return {k: np.ascontiguousarray(a, dtype=np.float32) for k, a in out.items()}


# ------------------------------------------------------------------ files
ATTRS = {  # long_name, units, as CM1 writes them
    "rain": ("accumulated surface rainfall", "cm"),
    "sws": ("max horiz wind speed at lowest model level", "m/s"),
    "svs": ("max vert vorticity at lowest model level", "1/s"),
    "sps": ("min pressure at lowest model level", "Pa"),
    "sus": ("max w at 5 km AGL", "m/s"),
    "shs": ("max integrated updraft helicity", "m2/s2"),
    "cref": ("composite reflectivity", "dBZ"),
    "th": ("potential temperature", "K"), "prs": ("pressure", "Pa"),
    "pi": ("nondimensional pressure", "nondimensional"), "rho": ("dry-air density", "kg/m^3"),
    "qv": ("water vapor mixing ratio", "kg/kg"), "qc": ("qc", "kg/kg"), "qr": ("qr", "kg/kg"),
    "qi": ("qi", "kg/kg"), "qs": ("qs", "kg/kg"), "qg": ("qg", "kg/kg"),
    "dbz": ("reflectivity", "dBZ"),
    "uinterp": ("u interpolated to scalar points", "m/s"),
    "vinterp": ("v interpolated to scalar points", "m/s"),
    "winterp": ("w interpolated to scalar points", "m/s"),
    "xvort": ("horizontal vorticity (x)", "1/s"), "yvort": ("horizontal vorticity (y)", "1/s"),
    "zvort": ("vertical vorticity", "1/s"),
    "pi0": ("base-state nondimensional pressure", "nondimensional"),
    "th0": ("base-state potential temperature", "K"), "prs0": ("base-state pressure", "Pa"),
    "qv0": ("base-state water vapor mixing ratio", "kg/kg"),
    "u": ("E-W (x) velocity", "m/s"), "u0": ("base-state u", "m/s"),
    "v": ("N-S (y) velocity", "m/s"), "v0": ("base-state v", "m/s"),
    "w": ("vertical velocity", "m/s"), "tke": ("subgrid turbulence kinetic energy", "m^2/s^2"),
}

NAMELIST = """ &param1
 nx = {n},
 ny = {n},
 nz = {nk},
 dx = {dx},
 dy = {dx},
 dz = 100.0,
 tapfrq = 300.0,
 imove = 1,
 umove = {umove},
 vmove = {vmove},
 /
 &param2
 output_format = 2,
 iorigin = 2,
 wbc = 2,
 ebc = 2,
 sbc = 2,
 nbc = 2,
 imoist = 1,
 /
"""


def _write(path, t, f, swaths, g):
    import netCDF4
    tmp = path + ".part"
    with netCDF4.Dataset(tmp, "w") as d:
        for n, size in (("ni", NI), ("nj", NI), ("nk", NK), ("nip1", NI + 1),
                        ("njp1", NI + 1), ("nkp1", NK + 1), ("time", 1), ("one", 1)):
            d.createDimension(n, size)
        d.setncatts({"cm1 version": "cm1view demo", "x_units": "km", "y_units": "km",
                     "z_units": "km", "nx": NI, "ny": NI, "nz": NK, "imoist": 1,
                     "iorigin": 2, "wbc": 2, "ebc": 2, "sbc": 2, "nbc": 2,
                     "cm1view_demo_version": VERSION})
        for n, dims, val, ln, un in (
                ("time", ("time",), [t], "time since beginning of simulation", "seconds"),
                ("xh", ("ni",), g["xh"], "west-east location of scalar grid points", "km"),
                ("xf", ("nip1",), g["xf"], "west-east location of staggered u grid points",
                 "km"),
                ("yh", ("nj",), g["xh"], "south-north location of scalar grid points", "km"),
                ("yf", ("njp1",), g["xf"], "south-north location of staggered v grid points",
                 "km"),
                ("z", ("nk",), g["z"], "nominal height of scalar grid points", "km"),
                ("zf", ("nkp1",), g["zf"], "nominal height of staggered w grid points", "km"),
                ("ztop", ("one",), [g["zf"][-1]], "model top", "km")):
            v = d.createVariable(n, "f4", dims)
            v.setncatts({"long_name": ln, "units": un})
            v[:] = val
        for n, a in swaths.items():
            v = d.createVariable(n, "f4", ("time", "nj", "ni"), zlib=True, complevel=1,
                                 shuffle=True, chunksizes=(1, NI, NI))
            v.setncatts(dict(zip(("long_name", "units"), ATTRS[n])))
            v[0] = a
        for n, a in f.items():
            nz = "nkp1" if a.shape[0] == NK + 1 else "nk"
            ny = "njp1" if a.shape[1] == NI + 1 else "nj"
            nx = "nip1" if a.shape[2] == NI + 1 else "ni"
            v = d.createVariable(n, "f4", ("time", nz, ny, nx), zlib=True, complevel=1,
                                 shuffle=True, chunksizes=(1, 1, a.shape[1], a.shape[2]))
            v.setncatts(dict(zip(("long_name", "units"), ATTRS[n])))
            v[0] = a
    os.replace(tmp, path)


def write_run(path, vmax, wmax):
    """One run: namelist.input + one cm1out file per time; returns the track rows."""
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "namelist.input"), "w") as fh:
        fh.write(NAMELIST.format(n=NI, nk=NK, dx=DX * 1000.0, umove=UMOVE, vmove=VMOVE))
    g = grid()
    k5 = int(np.argmin(np.abs(g["z"] - 5.0)))
    uh_k = (g["z"] >= 2.0) & (g["z"] <= 5.0)
    dz = np.diff(g["zf"])[uh_k][:, None, None] * 1000.0
    run = None
    rows = []
    for n, t in enumerate(TIMES):
        f = fields(t, vmax, wmax)
        uh = (f["winterp"][uh_k] * f["zvort"][uh_k] * dz).sum(0)
        spd = np.hypot(f["uinterp"][0] + UMOVE, f["vinterp"][0] + VMOVE)
        now = dict(sws=spd, svs=f["zvort"][0], sps=f["prs"][0], sus=f["winterp"][k5],
                   shs=np.maximum(uh, 0.0))
        if run is None:
            run = dict(now, rain=np.zeros((NI, NI)))
        else:
            for k in ("sws", "svs", "sus", "shs"):
                run[k] = np.maximum(run[k], now[k])
            run["sps"] = np.minimum(run["sps"], now["sps"])
            dt = t - TIMES[n - 1]
            run["rain"] = run["rain"] + f["rho"][0] * f["qr"][0] * 5.0 * dt / 10.0
        swaths = {k: run[k] for k in ("rain", "sws", "svs", "sps", "sus", "shs")}
        swaths["cref"] = f["dbz"].max(axis=0)
        _write(os.path.join(path, f"cm1out_{n + 1:06d}.nc"), t, f, swaths, g)
        if t >= 3600.0:
            (xc, yc), _ = _centres(t)
            ax = xc + 0.25 * 1.0  # updraft axis at 1 km, as the tracking default
            rows.append((t / 60.0, ax, yc + 0.05, STORM[0], STORM[1]))
    return rows


def is_demo(run_path):
    """A run written by make() (its stamp file is two folders up)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(run_path)))
    return os.path.exists(os.path.join(root, ".cm1view-demo"))


def _stamp():
    src = open(os.path.abspath(__file__), "rb").read()
    return f"{VERSION} {hashlib.sha1(src).hexdigest()[:12]}"


def make(root, force=False):
    """Write the demo runs under root (skipped when an up-to-date copy is there);
    returns the path of the main run."""
    root = os.path.abspath(os.path.expanduser(root))
    stamp_file = os.path.join(root, ".cm1view-demo")
    main = os.path.join(root, "demo", "supercell")
    try:
        if not force and open(stamp_file).read().strip() == _stamp():
            return main
    except OSError:
        pass
    os.makedirs(os.path.join(root, "storm_tracks"), exist_ok=True)
    for name, kw in RUNS.items():
        rows = write_run(os.path.join(root, "demo", name), **kw)
        with open(os.path.join(root, "storm_tracks", f"demo_{name}.csv"), "w") as fh:
            fh.write("time,loc_x,loc_y,storm_u,storm_v\n")
            for r in rows:
                fh.write(",".join(f"{x:.4f}" for x in r) + "\n")
    with open(stamp_file, "w") as fh:
        fh.write(_stamp() + "\n")
    return main


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m cm1view.demo", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", help="folder to write demo/ and storm_tracks/ into")
    ap.add_argument("--force", action="store_true", help="rewrite even if up to date")
    a = ap.parse_args(argv)
    print(make(a.outdir, a.force))


if __name__ == "__main__":
    main()
