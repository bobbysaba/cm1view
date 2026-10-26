"""Sounding analysis: parcel theory, kinematics and composite parameters.

Conventions: heights in m AGL, pressure in Pa, temperature in K, mixing
ratio in kg/kg, winds in m/s (ground-relative unless stated otherwise).
Parcels are lifted pseudoadiabatically with a virtual-temperature
correction; LCL from Bolton (1980).
"""

import numpy as np
from numba import njit

RD, RV, CP, LV, G = 287.04, 461.5, 1005.7, 2.501e6, 9.81
EPS = RD / RV
KAPPA = RD / CP


# ----------------------------------------------------------------- thermo
@njit(cache=True)
def _esat(T):
    Tc = T - 273.15
    return 611.2 * np.exp(17.67 * Tc / (Tc + 243.5))


@njit(cache=True)
def _rsat(T, p):
    e = _esat(T)
    return EPS * e / max(p - e, 1.0)


@njit(cache=True)
def _dTdlnp(T, p):
    rs = _rsat(T, p)
    return (RD * T + LV * rs) / (CP + LV * LV * rs * EPS / (RD * T * T))


@njit(cache=True)
def lift(p, k0, p0, T0, r0):
    """Lift a parcel (p0, T0, r0) through env pressure levels p[k0:].
    Returns (T, Tv, p_lcl, T_lcl); T/Tv are NaN below k0."""
    n = p.size
    Tout = np.full(n, np.nan)
    Tvout = np.full(n, np.nan)
    e = max(p0 * r0 / (EPS + r0), 1e-3)
    lne = np.log(e / 611.2)
    Td = min(243.5 * lne / (17.67 - lne) + 273.15, T0)
    Tl = 1.0 / (1.0 / (Td - 56.0) + np.log(T0 / Td) / 800.0) + 56.0
    pl = p0 * (Tl / T0) ** (1.0 / KAPPA)
    Tm = Tl
    lpm = np.log(pl)
    for k in range(k0, n):
        pk = p[k]
        if pk >= pl:
            T = T0 * (pk / p0) ** KAPPA
            r = r0
        else:
            lp1 = np.log(pk)
            nsub = int(np.ceil((lpm - lp1) / 0.005)) + 1
            h = (lp1 - lpm) / nsub
            T = Tm
            lp = lpm
            for _ in range(nsub):
                a1 = _dTdlnp(T, np.exp(lp))
                a2 = _dTdlnp(T + 0.5 * h * a1, np.exp(lp + 0.5 * h))
                a3 = _dTdlnp(T + 0.5 * h * a2, np.exp(lp + 0.5 * h))
                a4 = _dTdlnp(T + h * a3, np.exp(lp + h))
                T += h * (a1 + 2.0 * a2 + 2.0 * a3 + a4) / 6.0
                lp += h
            Tm = T
            lpm = lp1
            r = _rsat(T, pk)
        Tout[k] = T
        Tvout[k] = T * (1.0 + r / EPS) / (1.0 + r)
    return Tout, Tvout, pl, Tl


def virtual_temp(T, r):
    return T * (1.0 + r / EPS) / (1.0 + r)


def dewpoint(p, r):
    e = np.maximum(p * r / (EPS + r), 1e-3)
    lne = np.log(e / 611.2)
    return 243.5 * lne / (17.67 - lne) + 273.15


def theta_e(p, T, r):
    """Bolton (1980) eq. 43."""
    r = np.maximum(r, 1e-10)
    Td = np.minimum(dewpoint(p, r), T)
    TL = 1.0 / (1.0 / (Td - 56.0) + np.log(T / Td) / 800.0) + 56.0
    th = T * (1.0e5 / p) ** (0.2854 * (1.0 - 0.28 * r))
    return th * np.exp((3.376 / TL - 0.00254) * 1000.0 * r * (1.0 + 0.81 * r))


def _integrate_buoyancy(z, B, z_lcl):
    """CAPE, CIN, LFC, EL and 0-3 km CAPE from a buoyancy profile that
    starts at the parcel origin (z in m AGL, B in m/s^2)."""
    dz = 10.0
    zf = np.arange(z[0], z[-1], dz)
    bf = np.interp(zf, z, B)
    pos = bf > 0
    edges = np.flatnonzero(np.diff(pos.astype(np.int8))) + 1
    bounds = np.concatenate(([0], edges, [bf.size]))
    runs = [(bounds[i], bounds[i + 1]) for i in range(bounds.size - 1) if pos[bounds[i]]]
    runs = [(a, b) for a, b in runs if zf[b - 1] > z_lcl]
    if not runs:
        return 0.0, 0.0, np.nan, np.nan, 0.0
    lfc = max(runs[0][0], int(np.searchsorted(zf, z_lcl)))
    el = runs[-1][1] - 1
    cape = float(np.clip(bf[lfc:el + 1], 0, None).sum() * dz)
    cin = float(np.clip(bf[:lfc], None, 0).sum() * dz)
    k3 = min(el + 1, int(np.searchsorted(zf, 3000.0)))
    cape3 = float(np.clip(bf[lfc:k3], 0, None).sum() * dz) if k3 > lfc else 0.0
    return cape, cin, float(zf[lfc]), float(zf[el]), cape3


def parcel(z, p, Tv_env, k0, p0, T0, r0):
    T, Tv, pl, Tl = lift(p, k0, p0, T0, r0)
    zl = float(np.interp(-np.log(pl), -np.log(p), z))
    s = slice(k0, None)
    B = G * (Tv[s] - Tv_env[s]) / Tv_env[s]
    cape, cin, lfc, el, cape3 = _integrate_buoyancy(z[s], B, zl)
    return dict(cape=cape, cin=cin, lcl_z=zl, lcl_p=pl, lfc_z=lfc, el_z=el,
                cape3=cape3, T=T, k0=k0, p0=p0)


# --------------------------------------------------------------- kinematics
def _resample(z, a, zz):
    return np.interp(zz, z, a)


def srh(zz, U, V, cx, cy, h0, h1):
    s = (zz >= h0) & (zz <= h1)
    u, v = U[s] - cx, V[s] - cy
    if u.size < 2:
        return 0.0
    return float(np.sum(u[1:] * v[:-1] - u[:-1] * v[1:]))


def _layer_mean(zz, U, V, h0, h1):
    s = (zz >= h0) & (zz <= h1)
    return float(U[s].mean()), float(V[s].mean())


def bunkers(zz, U, V):
    """Bunkers et al. (2000) internal dynamics method (height-weighted)."""
    mu, mv = _layer_mean(zz, U, V, zz[0], 6000.0)
    lu, lv = _layer_mean(zz, U, V, zz[0], 500.0)
    tu, tv = _layer_mean(zz, U, V, 5500.0, 6000.0)
    su, sv = tu - lu, tv - lv
    mag = np.hypot(su, sv) or 1.0
    du, dv = 7.5 * sv / mag, -7.5 * su / mag
    return (mu + du, mv + dv), (mu - du, mv - dv), (mu, mv)


def _wind_at(zz, U, V, h):
    return float(np.interp(h, zz, U)), float(np.interp(h, zz, V))


def _shear(zz, U, V, h0, h1):
    u0, v0 = _wind_at(zz, U, V, h0)
    u1, v1 = _wind_at(zz, U, V, h1)
    return (u1 - u0, v1 - v0)


# --------------------------------------------------------------- analysis
def analyze(z, p, th, qv, u, v, storm="rm", custom=(0.0, 0.0), domain=(0.0, 0.0)):
    """Full analysis of one column.  z (m AGL), p (Pa), th (K), qv (kg/kg),
    u, v ground-relative (m/s).  Returns a nested dict of results."""
    z = np.asarray(z, np.float64)
    p = np.asarray(p, np.float64)
    th = np.asarray(th, np.float64)
    qv = np.maximum(np.asarray(qv, np.float64), 1e-10)
    u = np.asarray(u, np.float64)
    v = np.asarray(v, np.float64)

    T = th * (p / 1.0e5) ** KAPPA
    Td = dewpoint(p, qv)
    Tv = virtual_temp(T, qv)
    the = theta_e(p, T, qv)

    # ---- parcels
    sb = parcel(z, p, Tv, 0, p[0], T[0], qv[0])
    ml_layer = p >= p[0] - 10000.0
    w = np.gradient(-p)[ml_layer]
    th_ml = float(np.sum(th[ml_layer] * w) / w.sum())
    q_ml = float(np.sum(qv[ml_layer] * w) / w.sum())
    ml = parcel(z, p, Tv, 0, p[0], th_ml * (p[0] / 1.0e5) ** KAPPA, q_ml)
    mu_layer = np.flatnonzero(p >= p[0] - 30000.0)
    kmu = int(mu_layer[np.argmax(the[mu_layer])])
    mu = parcel(z, p, Tv, kmu, p[kmu], T[kmu], qv[kmu])

    # ---- effective inflow layer (Thompson et al. 2007)
    eil = (np.nan, np.nan)
    kbase = None
    for k in mu_layer:
        pk = parcel(z, p, Tv, int(k), p[k], T[k], qv[k])
        ok = pk["cape"] >= 100.0 and pk["cin"] >= -250.0
        if ok and kbase is None:
            kbase = k
            eil = (z[k], z[k])
        elif ok:
            eil = (eil[0], z[k])
        elif kbase is not None:
            break

    # ---- kinematics on a uniform 10 m grid
    ztop = min(z[-1], 16000.0)
    zz = np.arange(z[0], ztop, 10.0)
    U, V = _resample(z, u, zz), _resample(z, v, zz)
    rm, lm, mean06 = bunkers(zz, U, V)
    c = {"rm": rm, "lm": lm, "mean": mean06, "domain": tuple(domain),
         "custom": tuple(custom)}[storm]
    cx, cy = c
    sfc = (U[0], V[0])
    sh500 = _shear(zz, U, V, zz[0], 500.0)
    inflow = (cx - sfc[0], cy - sfc[1])
    crit = np.degrees(np.arccos(np.clip(
        (sh500[0] * inflow[0] + sh500[1] * inflow[1])
        / (np.hypot(*sh500) * np.hypot(*inflow) + 1e-9), -1.0, 1.0)))

    if kbase is not None:
        esrh = srh(zz, U, V, cx, cy, eil[0], eil[1])
        if np.isfinite(mu["el_z"]):
            etop = eil[0] + 0.5 * (mu["el_z"] - eil[0])
            ebwd = float(np.hypot(*_shear(zz, U, V, eil[0], min(etop, ztop))))
        else:
            ebwd = 0.0
    else:
        esrh, ebwd = 0.0, 0.0

    kin = dict(
        storm=(cx, cy), rm=rm, lm=lm, mean06=mean06,
        shear250=_shear(zz, U, V, zz[0], 250.0),
        shear500=_shear(zz, U, V, zz[0], 500.0),
        shear01=_shear(zz, U, V, zz[0], 1000.0),
        shear03=_shear(zz, U, V, zz[0], 3000.0),
        shear06=_shear(zz, U, V, zz[0], 6000.0),
        shear08=_shear(zz, U, V, zz[0], 8000.0),
        srh250=srh(zz, U, V, cx, cy, 0.0, 250.0),
        srh500=srh(zz, U, V, cx, cy, 0.0, 500.0),
        srh1=srh(zz, U, V, cx, cy, 0.0, 1000.0),
        srh3=srh(zz, U, V, cx, cy, 0.0, 3000.0),
        eil=eil, esrh=esrh, ebwd=ebwd, crit=float(crit),
        sr_sfc=float(np.hypot(sfc[0] - cx, sfc[1] - cy)),
    )

    # ---- composites (SPC formulations)
    bwd6 = float(np.hypot(*kin["shear06"]))
    bwd6_t = 0.0 if bwd6 < 12.5 else min(bwd6, 30.0) / 20.0
    lcl_t = lambda zl: 1.0 if zl < 1000.0 else (0.0 if zl > 2000.0 else (2000.0 - zl) / 1000.0)
    stp_fixed = (sb["cape"] / 1500.0) * lcl_t(sb["lcl_z"]) * (kin["srh1"] / 150.0) * bwd6_t
    ebwd_t = 0.0 if ebwd < 12.5 else min(ebwd, 30.0) / 20.0
    cin_t = 1.0 if ml["cin"] > -50.0 else (0.0 if ml["cin"] < -200.0 else (ml["cin"] + 200.0) / 150.0)
    surface_based = kbase is not None and kbase == 0
    stp_eff = ((ml["cape"] / 1500.0) * lcl_t(ml["lcl_z"]) * (esrh / 150.0) * ebwd_t * cin_t
               if surface_based else 0.0)
    scp_bwd = 0.0 if ebwd < 10.0 else min(ebwd, 20.0) / 20.0
    scp_cin = 1.0 if mu["cin"] > -40.0 else -40.0 / mu["cin"]
    scp = (mu["cape"] / 1000.0) * (esrh / 50.0) * scp_bwd * scp_cin

    # ---- thermo summary
    def T_at(h):
        return float(np.interp(h, z, T))

    lr03 = (T_at(z[0]) - T_at(3000.0)) / ((3000.0 - z[0]) / 1000.0)
    lr36 = (T_at(3000.0) - T_at(6000.0)) / 3.0
    lnp = -np.log(p)
    z700, z500 = np.interp(-np.log([70000.0, 50000.0]), lnp, z)
    lr75 = (np.interp(-np.log(70000.0), lnp, T) - np.interp(-np.log(50000.0), lnp, T)) / (
        (z500 - z700) / 1000.0)
    q = qv / (1.0 + qv)
    pw = float(np.sum(0.5 * (q[1:] + q[:-1]) * (p[:-1] - p[1:])) / G)
    below = np.flatnonzero(T < 273.15)
    frz = float(np.interp(273.15, [T[below[0]], T[below[0] - 1]], [z[below[0]], z[below[0] - 1]])) \
        if below.size and below[0] > 0 else np.nan

    # ---- vertical profiles (layer midpoints) for plotting
    zm = 0.5 * (z[1:] + z[:-1])
    dz = np.diff(z)
    dudz, dvdz = np.diff(u) / dz, np.diff(v) / dz
    um, vm = 0.5 * (u[1:] + u[:-1]) - cx, 0.5 * (v[1:] + v[:-1]) - cy
    srs = np.hypot(um, vm)
    sx, sy = um / np.maximum(srs, 1e-6), vm / np.maximum(srs, 1e-6)
    wx, wy = -dvdz, dudz
    ur, vr = u - cx, v - cy
    cum = np.concatenate(([0.0], np.cumsum(ur[1:] * vr[:-1] - ur[:-1] * vr[1:])))
    es = 611.2 * np.exp(17.67 * (T - 273.15) / (T - 29.65))
    rh = 100.0 * (p * qv / (EPS + qv)) / es

    return dict(
        prof=dict(z=z, p=p, T=T, Td=Td, Tv=Tv, th=th, the=the, qv=qv, u=u, v=v, rh=rh),
        sb=sb, ml=ml, mu=mu, kin=kin,
        comp=dict(stp_fixed=float(stp_fixed), stp_eff=float(stp_eff), scp=float(scp)),
        thermo=dict(pw=pw, lr03=float(lr03), lr36=float(lr36), lr75=float(lr75), frz=frz,
                    sfc_T=float(T[0]), sfc_Td=float(Td[0]), sfc_the=float(the[0])),
        profiles=dict(zm=zm, sr_speed=srs, shear=np.hypot(dudz, dvdz),
                      ws=wx * sx + wy * sy, wc=-wx * sy + wy * sx, z=z, cum_srh=cum),
    )
