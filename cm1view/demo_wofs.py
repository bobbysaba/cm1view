"""Synthetic WoFS output for demos and tests:  python -m cm1view.demo_wofs OUTDIR

Writes a small ensemble in WoFS's layout under OUTDIR/wofs/: one folder per cycle
(YYYYMMDDHHMM, five minutes apart), each with one wrfout_d01_<time>_<member> file for
three members, beside the empty DART files a real run has (which cm1view ignores).  The
run to open is OUTDIR/wofs (it is member 1; <root>/mem02, <root>/mem03 and <root>/mean
are the other runs).

The domain is 40 x 40 x 20 points of 3 km, on terrain that rises towards the east, with
model levels that follow it.  The fields are analytic, not a simulation: a stable,
moist atmosphere with westerly shear and, in each member, a storm moving north-east
with an updraft, rain, reflectivity, a cold pool and a track of updraft helicity, so
maps, cross-sections, soundings and the 3D views all have something to show.  The
members put the storm a little apart and make it a little stronger or weaker, so the
ensemble mean differs from each of them.  Deterministic: the same version writes the
same values.
"""

import argparse
import datetime
import hashlib
import os

import numpy as np

VERSION = 1  # bump when the fields change: cached copies are rewritten

G, P0 = 9.81, 1.0e5
NI, NJ, NK, DX = 40, 40, 20, 3000.0  # mass points, levels, metres
NCYCLE, STEP = 7, 5  # cycle folders, minutes between them
MEMBERS = (1, 2, 3)
START = datetime.datetime(2022, 5, 23, 22, 0)
ZTOP = 16000.0  # m

_DIMS = dict(T="zyx", P="zyx", PB="zyx", QVAPOR="zyx", QCLOUD="zyx", QRAIN="zyx",
             REFL_10CM="zyx", U="zyX", V="zYx", W="Zyx", PH="Zyx", PHB="Zyx",
             HGT="yx", UP_HELI_MAX="yx")
_NAMES = dict(z="bottom_top", Z="bottom_top_stag", y="south_north", Y="south_north_stag",
              x="west_east", X="west_east_stag")


def _destag(a, axis):
    n = a.shape[axis]
    lo = [slice(None)] * a.ndim
    hi = list(lo)
    lo[axis], hi[axis] = slice(0, n - 1), slice(1, n)
    return 0.5 * (a[tuple(lo)] + a[tuple(hi)])


def fields(member, c):
    """The fields of one member at cycle c, on WRF's own (staggered) grids."""
    xh = (np.arange(NI) - (NI - 1) / 2) * DX / 1000.0  # km from the centre
    yh = (np.arange(NJ) - (NJ - 1) / 2) * DX / 1000.0
    hgt = np.broadcast_to(300.0 + 12.0 * (xh + 60.0), (NJ, NI)).astype(np.float32)  # slope
    eta = np.linspace(1.0, 0.0, NK + 1, dtype=np.float32)[:, None, None]
    zw = hgt + (1.0 - hgt / ZTOP) * ZTOP * (1.0 - eta)  # w levels, m MSL
    zm = 0.5 * (zw[:-1] + zw[1:])
    zkm = zm / 1000.0
    # the storm: starts south-west of the centre, moves north-east (km, m/s)
    t = 60.0 * STEP * c
    cx = -25.0 + 0.012 * t * 3.0 + 3.0 * (member - 2)
    cy = -22.0 + 0.012 * t * 2.0 - 2.0 * (member - 2)
    amp = 1.0 + 0.15 * (member - 2)
    X, Y = xh[None, None, :], yh[None, :, None]
    r2 = ((X - cx) ** 2 + (Y - cy) ** 2) / 8.0 ** 2
    horiz = np.exp(-r2)
    vert = np.exp(-(((zkm - 6.0) / 3.5) ** 2))
    low = np.exp(-zkm / 1.5)
    ramp = min(1.0, 0.2 + 0.2 * c)  # the storm grows over the cycles
    w = 28.0 * amp * ramp * horiz * vert
    rain = 6.0e-3 * amp * ramp * np.exp(-r2 * 0.6) * np.exp(-zkm / 4.0)
    cloud = 2.0e-3 * amp * ramp * horiz * np.exp(-(((zkm - 6.5) / 3.0) ** 2))
    theta = 300.0 + 3.2 * zkm + 0.4 * zkm ** 2 + 6.0 * amp * ramp * horiz * vert \
        - 4.0 * ramp * np.exp(-r2 * 1.5) * low
    qv = 0.016 * np.exp(-zkm / 2.5) * (1.0 + 0.03 * (member - 2)) * (1.0 + 0.1 * horiz * low)
    pb = P0 * np.exp(-zm / 7500.0)
    pert = -150.0 * ramp * horiz * low + 80.0 * ramp * horiz * vert
    u = 4.0 + 2.5 * zkm + 0.0 * X  # westerly shear; flow into the storm
    v = 2.0 + 0.8 * zkm + 0.0 * Y
    uu = np.broadcast_to(u, (NK, NJ, NI)).astype(np.float32)
    vv = np.broadcast_to(v, (NK, NJ, NI)).astype(np.float32)
    ww = np.zeros((NK + 1, NJ, NI), np.float32)
    ww[:-1] += 0.5 * w
    ww[1:] += 0.5 * w
    uh = (w.max(axis=0) ** 2 * 0.4 * horiz[0]).astype(np.float32)
    dbz = np.where(rain > 1e-6, 10.0 * np.log10(np.maximum(rain, 1e-9) / 1e-9), -20.0)
    return dict(
        T=(theta - 300.0).astype(np.float32), P=pert.astype(np.float32),
        PB=pb.astype(np.float32), QVAPOR=qv.astype(np.float32),
        QCLOUD=cloud.astype(np.float32), QRAIN=rain.astype(np.float32),
        REFL_10CM=np.clip(dbz, -20.0, 70.0).astype(np.float32),
        U=np.concatenate([uu[..., :1], 0.5 * (uu[..., :-1] + uu[..., 1:]), uu[..., -1:]],
                         axis=2).astype(np.float32),
        V=np.concatenate([vv[:, :1], 0.5 * (vv[:, :-1] + vv[:, 1:]), vv[:, -1:]],
                         axis=1).astype(np.float32),
        W=ww, PH=np.zeros_like(zw), PHB=(G * zw).astype(np.float32), HGT=hgt,
        UP_HELI_MAX=uh)


def write_member(fn, when, member, c):
    import netCDF4
    tmp = fn + ".part"
    with netCDF4.Dataset(tmp, "w", format="NETCDF3_64BIT_OFFSET") as d:
        d.createDimension("Time", None)
        d.createDimension("DateStrLen", 19)
        for dim, n in (("west_east", NI), ("south_north", NJ), ("bottom_top", NK),
                       ("west_east_stag", NI + 1), ("south_north_stag", NJ + 1),
                       ("bottom_top_stag", NK + 1)):
            d.createDimension(dim, n)
        d.setncatts(dict(DX=np.float32(DX), DY=np.float32(DX),
                         TITLE=" OUTPUT FROM WRF (cm1view synthetic demo)"))
        ts = d.createVariable("Times", "S1", ("Time", "DateStrLen"))
        ts[0] = netCDF4.stringtochar(np.array([f"{when:%Y-%m-%d_%H:%M:%S}"], "S19"))
        for name, a in fields(member, c).items():
            v = d.createVariable(name, "f4", ("Time",) + tuple(
                _NAMES[ch] for ch in _DIMS[name]))
            v.setncatts(dict(description=f"synthetic {name}", units="", stagger=""))
            v[0] = a
    os.replace(tmp, fn)


def write_run(root):
    """The demo ensemble in root: cycle folders of member files, DART files left empty."""
    os.makedirs(root, exist_ok=True)
    for c in range(NCYCLE):
        when = START + datetime.timedelta(minutes=STEP * c)
        cyc = os.path.join(root, f"{when:%Y%m%d%H%M}")
        os.makedirs(cyc, exist_ok=True)
        open(os.path.join(cyc, f"obs_seq.final.{when:%Y%m%d%H%M}"), "w").close()
        for m in MEMBERS:
            write_member(os.path.join(cyc, f"wrfout_d01_{when:%Y-%m-%d_%H:%M:%S}_{m}"),
                         when, m, c)
    return root


def _stamp():
    src = open(os.path.abspath(__file__), "rb").read()
    return f"{VERSION} {hashlib.sha1(src).hexdigest()[:12]}"


def make(root, force=False):
    """Write the WoFS demo under root/wofs (skipped when an up-to-date copy is there);
    returns the run folder."""
    root = os.path.abspath(os.path.expanduser(root))
    run = os.path.join(root, "wofs")
    stamp_file = os.path.join(root, ".cm1view-demo-wofs")
    try:
        if not force and open(stamp_file).read().strip() == _stamp():
            return run
    except OSError:
        pass
    write_run(run)
    with open(stamp_file, "w") as fh:
        fh.write(_stamp() + "\n")
    return run


def is_demo(run_path):
    """A run written by make() (its stamp file is next to the wofs folder)."""
    p = os.path.abspath(run_path)
    for _ in range(3):
        if os.path.exists(os.path.join(p, ".cm1view-demo-wofs")):
            return True
        p = os.path.dirname(p)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m cm1view.demo_wofs", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", help="folder to write wofs/ into")
    ap.add_argument("--force", action="store_true", help="rewrite even if up to date")
    a = ap.parse_args(argv)
    print(make(a.outdir, a.force))


if __name__ == "__main__":
    main()
