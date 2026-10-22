"""Field catalog (native + derived), display defaults and colormaps."""

import threading
from collections import OrderedDict

import numpy as np
import matplotlib
import matplotlib.colors as mcolors

try:  # registers cmo.* colormaps with matplotlib
    import cmocean  # noqa: F401
except ImportError:  # pragma: no cover
    pass

G = 9.81
EPS = 287.04 / 461.5
KAPPA = 287.04 / 1005.7

# --------------------------------------------------------------- colormaps
_NWS_REF = [
    "#04e9e7", "#019ff4", "#0300f4", "#02fd02", "#01c501", "#008e00", "#fdf802",
    "#e5bc00", "#fd9500", "#fd0000", "#d40000", "#bc0000", "#f800fd", "#9854c6",
    "#fdfdfd",
]

CMAPS = [
    "reflectivity", "turbo", "viridis", "magma", "inferno", "plasma", "cividis",
    "RdBu_r", "PuOr_r", "BrBG", "coolwarm", "seismic", "cmo.balance", "cmo.curl",
    "cmo.thermal", "cmo.haline", "cmo.deep", "cmo.rain", "cmo.ice", "cmo.amp",
    "YlGnBu", "YlOrRd", "Spectral_r", "Greys_r", "cubehelix",
]


def _reflectivity(n):
    """NWS-style stepped reflectivity over 0-75 dBZ; < 5 dBZ transparent."""
    out = []
    for v in np.linspace(0, 75, n, endpoint=False):
        idx = int(v // 5) - 1
        out.append("#00000000" if idx < 0 else _NWS_REF[min(idx, len(_NWS_REF) - 1)])
    return out


def palette(name, n=256, reverse=False):
    if name == "reflectivity":
        pal = _reflectivity(n)
    else:
        cmap = matplotlib.colormaps[name]
        pal = [mcolors.to_hex(c) for c in cmap(np.linspace(0, 1, n))]
    return pal[::-1] if reverse else pal


def mpl_cmap(name, reverse=False):
    if name == "reflectivity":
        cm = mcolors.ListedColormap(_reflectivity(256))
    else:
        cm = matplotlib.colormaps[name]
    return cm.reversed() if reverse else cm


# --------------------------------------------------------------- catalog
class FieldDef:
    def __init__(self, name, label, units, group, ndim=3, scale=1.0, cmap="viridis",
                 vrange=None, diverging=False, deps=(), func=None, pointwise=True,
                 storm=False):
        self.name, self.label, self.units, self.group = name, label, units, group
        self.ndim, self.scale, self.cmap, self.vrange = ndim, scale, cmap, vrange
        self.diverging, self.deps, self.func = diverging, tuple(deps), func
        # pointwise: func works on any samples of its inputs (no spatial derivatives)
        self.pointwise = pointwise
        # storm: depends on the storm motion, c["storm"] = ground-relative (u, v) m/s
        self.storm = storm

    @property
    def derived(self):
        return self.func is not None

    @property
    def title(self):
        return f"{self.label} ({self.units})" if self.units else self.label


# display defaults for native CM1 names: label, units, scale, cmap, range, diverging
_NATIVE = {
    "cref": ("Composite reflectivity", "dBZ", 1, "reflectivity", (0, 75), False),
    "dbz": ("Reflectivity", "dBZ", 1, "reflectivity", (0, 75), False),
    "uinterp": ("u (grid-relative)", "m/s", 1, "RdBu_r", (-30, 30), True),
    "vinterp": ("v (grid-relative)", "m/s", 1, "RdBu_r", (-30, 30), True),
    "winterp": ("Vertical velocity", "m/s", 1, "RdBu_r", (-20, 20), True),
    "u": ("u (grid-relative, staggered)", "m/s", 1, "RdBu_r", (-30, 30), True),
    "v": ("v (grid-relative, staggered)", "m/s", 1, "RdBu_r", (-30, 30), True),
    "w": ("w (staggered)", "m/s", 1, "RdBu_r", (-20, 20), True),
    "zvort": ("Vertical vorticity", "1/s", 1, "RdBu_r", (-0.05, 0.05), True),
    "xvort": ("x vorticity", "1/s", 1, "RdBu_r", (-0.05, 0.05), True),
    "yvort": ("y vorticity", "1/s", 1, "RdBu_r", (-0.05, 0.05), True),
    "th": ("Potential temperature", "K", 1, "cmo.thermal", None, False),
    "prs": ("Pressure", "hPa", 0.01, "viridis", None, False),
    "pi": ("Exner function", "", 1, "viridis", None, False),
    "rho": ("Density", "kg/m³", 1, "viridis", None, False),
    "qv": ("Water vapor mixing ratio", "g/kg", 1000, "YlGnBu", (0, 20), False),
    "qc": ("Cloud water", "g/kg", 1000, "cmo.ice", (0, 3), False),
    "qr": ("Rain", "g/kg", 1000, "cmo.rain", (0, 5), False),
    "qi": ("Cloud ice", "g/kg", 1000, "cmo.ice", (0, 2), False),
    "qs": ("Snow", "g/kg", 1000, "cmo.ice", (0, 3), False),
    "qg": ("Graupel", "g/kg", 1000, "cmo.amp", (0, 5), False),
    "qhl": ("Hail", "g/kg", 1000, "cmo.amp", (0, 5), False),
    "tke": ("Subgrid TKE", "m²/s²", 1, "magma", (0, 20), False),
    "rain": ("Accumulated rain", "cm", 1, "cmo.rain", (0, 5), False),
    "rain2": ("Accumulated rain (translated)", "cm", 1, "cmo.rain", (0, 5), False),
    "sws": ("Max sfc wind speed", "m/s", 1, "turbo", (0, 40), False),
    "sws2": ("Max sfc wind speed (translated)", "m/s", 1, "turbo", (0, 40), False),
    "svs": ("Max sfc vertical vorticity", "1/s", 1, "magma", (0, 0.1), False),
    "svs2": ("Max sfc vert. vorticity (translated)", "1/s", 1, "magma", (0, 0.1), False),
    "sps": ("Min sfc pressure", "hPa", 0.01, "viridis", None, False),
    "sps2": ("Min sfc pressure (translated)", "hPa", 0.01, "viridis", None, False),
    "srs": ("Max sfc rain mixing ratio", "g/kg", 1000, "cmo.rain", (0, 5), False),
    "srs2": ("Max sfc qr (translated)", "g/kg", 1000, "cmo.rain", (0, 5), False),
    "sgs": ("Max sfc graupel mixing ratio", "g/kg", 1000, "cmo.amp", (0, 5), False),
    "sgs2": ("Max sfc qg (translated)", "g/kg", 1000, "cmo.amp", (0, 5), False),
    "sus": ("Max w at 5 km", "m/s", 1, "turbo", (0, 60), False),
    "sus2": ("Max w at 5 km (translated)", "m/s", 1, "turbo", (0, 60), False),
    "shs": ("Max updraft helicity", "m²/s²", 1, "magma", (0, 500), False),
    "shs2": ("Max updraft helicity (translated)", "m²/s²", 1, "magma", (0, 500), False),
    # pressure decomposition (from the files, or computed with the pdecomp_script)
    "p_b": ("p′ buoyant (p_b)", "Pa", 1, "PuOr_r", None, True),
    "p_l": ("p′ linear dynamic (p_l)", "Pa", 1, "PuOr_r", None, True),
    "p_nl": ("p′ nonlinear dynamic (p_nl, residual)", "Pa", 1, "PuOr_r", None, True),
    "acc_b": ("Buoyant acceleration (B − ∂p_b/∂z / ρ)", "m/s²", 1, "RdBu_r", None, True),
    "acc_l": ("Linear dynamic VPPGA (−∂p_l/∂z / ρ)", "m/s²", 1, "RdBu_r", None, True),
    "acc_nl": ("Nonlinear dynamic VPPGA (−∂p_nl/∂z / ρ)", "m/s²", 1, "RdBu_r", None,
               True),
}

PDECOMP = ("p_b", "p_l", "p_nl", "acc_b", "acc_l", "acc_nl")


def _group(name, ndim):
    if ndim == 2:
        return "Swaths & 2D"
    if name in ("dbz", "cref"):
        return "Radar"
    if name in PDECOMP:
        return "Pressure decomposition"
    if "b_" in name:
        return "Budgets"
    if name in ("th0", "prs0", "pi0", "qv0", "u0", "v0", "rho0"):
        return "Base state"
    if name in ("u", "v", "w", "uinterp", "vinterp", "winterp", "xvort", "yvort", "zvort"):
        return "Kinematics"
    if name in ("th", "prs", "pi", "rho", "qv"):
        return "Thermodynamics"
    if name in ("tke", "kmh", "kmv", "khh", "khv"):
        return "Turbulence"
    return "Microphysics"


# ---- derived fields: f(name) fetches a native field (raw units) on the same
# plane/volume, c is a context dict (dx, dy in m; umove, vmove in m/s)
def _tempk(f, c):
    return f("th") * (f("prs") / 1.0e5) ** KAPPA


def _vap(f):
    q = np.maximum(f("qv"), 1e-10)
    return f("prs") * q / (EPS + q)


def _dewc(f, c):
    lne = np.log(_vap(f) / 611.2)
    return 243.5 * lne / (17.67 - lne)


def _thetae(f, c):
    """Bolton (1980) eq. 43 equivalent potential temperature."""
    T = _tempk(f, c)
    r = np.maximum(f("qv"), 1e-10)
    Td = _dewc(f, c) + 273.15
    TL = 1.0 / (1.0 / (Td - 56.0) + np.log(T / Td) / 800.0) + 56.0
    th = T * (1.0e5 / f("prs")) ** (0.2854 * (1.0 - 0.28 * r))
    return th * np.exp((3.376 / TL - 0.00254) * 1000.0 * r * (1.0 + 0.81 * r))


def _rh(f, c):
    T = _tempk(f, c) - 273.15
    es = 611.2 * np.exp(17.67 * T / (T + 243.5))
    return 100.0 * _vap(f) / es


def _hydro_names(avail):
    return [n for n in ("qc", "qr", "qi", "qs", "qg", "qhl") if n in avail]


def _make_fields(avail):
    D = []
    hyd = _hydro_names(avail)
    D.append(FieldDef("thpert", "θ′", "K", "Thermodynamics", cmap="RdBu_r",
                      vrange=(-6, 6), diverging=True, deps=("th", "th0"),
                      func=lambda f, c: f("th") - f("th0")))
    D.append(FieldDef("prspert", "p′", "hPa", "Thermodynamics", cmap="PuOr_r",
                      vrange=(-4, 4), diverging=True, deps=("prs", "prs0"),
                      func=lambda f, c: 0.01 * (f("prs") - f("prs0"))))

    def buoy(f, c):
        load = sum(f(n) for n in hyd) if hyd else 0.0
        thr = f("th") * (1.0 + f("qv") / EPS) / (1.0 + f("qv") + load)
        thr0 = f("th0") * (1.0 + f("qv0") / EPS) / (1.0 + f("qv0"))
        return G * (thr - thr0) / thr0

    D.append(FieldDef("buoy", "Buoyancy (θρ′, with loading)", "m/s²", "Thermodynamics",
                      cmap="RdBu_r", vrange=(-0.3, 0.3), diverging=True,
                      deps=("th", "qv", "th0", "qv0", *hyd), func=buoy))
    # density potential temperature (θ including the vapour and condensate loading)
    def thrho(f, c):
        load = sum(f(n) for n in hyd) if hyd else 0.0
        return f("th") * (1.0 + f("qv") / EPS) / (1.0 + f("qv") + load)

    D.append(FieldDef("thrho", "θρ", "K", "Thermodynamics", cmap="cmo.thermal",
                      deps=("th", "qv", *hyd), func=thrho))
    D.append(FieldDef("thrhopert", "θρ′", "K", "Thermodynamics", cmap="RdBu_r",
                      vrange=(-6, 6), diverging=True, deps=("th", "qv", "th0", "qv0", *hyd),
                      func=lambda f, c: thrho(f, c) - f("th0") * (1.0 + f("qv0") / EPS)
                      / (1.0 + f("qv0"))))
    D.append(FieldDef("thetae", "θe", "K", "Thermodynamics", cmap="Spectral_r",
                      deps=("th", "prs", "qv"), func=_thetae))
    D.append(FieldDef("tempc", "Temperature", "°C", "Thermodynamics", cmap="cmo.thermal",
                      deps=("th", "prs"), func=lambda f, c: _tempk(f, c) - 273.15))
    D.append(FieldDef("dewc", "Dewpoint", "°C", "Thermodynamics", cmap="BrBG",
                      deps=("prs", "qv"), func=_dewc))
    D.append(FieldDef("rh", "Relative humidity (liquid)", "%", "Thermodynamics",
                      cmap="YlGnBu", vrange=(0, 100), deps=("th", "prs", "qv"), func=_rh))
    D.append(FieldDef("wspd", "Wind speed (ground-relative)", "m/s", "Kinematics",
                      cmap="turbo", vrange=(0, 40), deps=("uinterp", "vinterp"),
                      func=lambda f, c: np.hypot(f("uinterp") + c["umove"],
                                                 f("vinterp") + c["vmove"])))

    def hdiv(f, c):
        du = np.gradient(f("uinterp"), c["dx"], axis=-1)
        dv = np.gradient(f("vinterp"), c["dy"], axis=-2)
        return 1.0e3 * (du + dv)

    D.append(FieldDef("hdiv", "Horizontal divergence", "10⁻³ s⁻¹", "Kinematics",
                      cmap="PuOr_r", vrange=(-10, 10), diverging=True,
                      deps=("uinterp", "vinterp"), func=hdiv, pointwise=False))
    D.append(FieldDef("hvort", "Horizontal vorticity magnitude", "1/s", "Kinematics",
                      cmap="magma", vrange=(0, 0.1), deps=("xvort", "yvort"),
                      func=lambda f, c: np.hypot(f("xvort"), f("yvort"))))

    # horizontal vorticity along / across the storm-relative horizontal wind; c["storm"]
    # is the storm motion (ground-relative), the grid winds are relative to (umove, vmove)
    def sr_unit(f, c):
        us = f("uinterp") + (c["umove"] - c["storm"][0])
        vs = f("vinterp") + (c["vmove"] - c["storm"][1])
        sp = np.maximum(np.hypot(us, vs), 1e-6)
        return us / sp, vs / sp

    def wstream(f, c):
        sx, sy = sr_unit(f, c)
        return f("xvort") * sx + f("yvort") * sy

    def wcross(f, c):  # positive: vorticity to the left of the storm-relative wind
        sx, sy = sr_unit(f, c)
        return -f("xvort") * sy + f("yvort") * sx

    vdeps = ("xvort", "yvort", "uinterp", "vinterp")
    D.append(FieldDef("wstream", "Streamwise vorticity", "1/s", "Kinematics", cmap="RdBu_r",
                      vrange=(-0.05, 0.05), diverging=True, deps=vdeps, func=wstream,
                      storm=True))
    D.append(FieldDef("wcross", "Crosswise vorticity", "1/s", "Kinematics", cmap="RdBu_r",
                      vrange=(-0.05, 0.05), diverging=True, deps=vdeps, func=wcross,
                      storm=True))
    D.append(FieldDef("p_dyn", "p′ dynamic (p_l + p_nl)", "Pa", "Pressure decomposition",
                      cmap="PuOr_r", diverging=True, deps=("p_l", "p_nl"),
                      func=lambda f, c: f("p_l") + f("p_nl")))
    D.append(FieldDef("acc_dyn", "Dynamic VPPGA (linear + nonlinear)", "m/s²",
                      "Pressure decomposition", cmap="RdBu_r", diverging=True,
                      deps=("acc_l", "acc_nl"), func=lambda f, c: f("acc_l") + f("acc_nl")))
    D.append(FieldDef("acc_tot", "Total acceleration (b + l + nl)", "m/s²",
                      "Pressure decomposition", cmap="RdBu_r", diverging=True,
                      deps=("acc_b", "acc_l", "acc_nl"),
                      func=lambda f, c: f("acc_b") + f("acc_l") + f("acc_nl")))
    if hyd:
        cl = [n for n in ("qc", "qi") if n in avail]
        pr = [n for n in ("qr", "qs", "qg", "qhl") if n in avail]
        if cl:
            D.append(FieldDef("qcloud", "Cloud condensate (qc+qi)", "g/kg", "Microphysics",
                              cmap="cmo.ice", vrange=(0, 3), deps=cl,
                              func=lambda f, c: 1000.0 * sum(f(n) for n in cl)))
        if pr:
            D.append(FieldDef("qprecip", "Precipitation (qr+qs+qg+qhl)", "g/kg",
                              "Microphysics", cmap="cmo.rain", vrange=(0, 8), deps=pr,
                              func=lambda f, c: 1000.0 * sum(f(n) for n in pr)))
    return [d for d in D if all(x in avail for x in d.deps)]


GROUP_ORDER = ["Radar", "Kinematics", "Thermodynamics", "Pressure decomposition",
               "Microphysics", "Swaths & 2D", "Turbulence", "Budgets", "Base state"]


class Fields:
    def __init__(self, run):
        from .. import pdecomp
        pdecomp.register(run)  # decomposition fields, computable where no file has them
        self.run = run
        self.ctx = dict(dx=run.dx, dy=run.dy, umove=run.umove, vmove=run.vmove)
        self.defs = OrderedDict()
        for name, info in run.vars.items():
            if name in _NATIVE:
                label, units, scale, cmap, vr, div = _NATIVE[name]
            else:
                label, units, scale = info.long_name, info.units, 1.0
                div = "b_" in name or name.endswith("vort")
                cmap, vr = ("RdBu_r" if div else "viridis"), None
                if name.startswith("q") and units == "kg/kg":
                    units, scale = "g/kg", 1000.0
            self.defs[name] = FieldDef(name, label, units, _group(name, info.ndim),
                                       ndim=info.ndim, scale=scale, cmap=cmap,
                                       vrange=vr, diverging=div)
        for d in _make_fields(run.vars):
            self.defs[d.name] = d
        self._planes = OrderedDict()
        self._lock = threading.Lock()

    # ---- catalog helpers
    def __getitem__(self, name):
        return self.defs[name]

    def __contains__(self, name):
        return name in self.defs

    def groups(self, ndim=None):
        """{group: {label: name}} for grouped Select widgets."""
        out = OrderedDict((g, OrderedDict()) for g in GROUP_ORDER)
        for d in self.defs.values():
            if ndim is not None and d.ndim != ndim:
                continue
            out.setdefault(d.group, OrderedDict())[f"{d.label} [{d.name}]"] = d.name
        return OrderedDict((g, v) for g, v in out.items() if v)

    def native_deps(self, name):
        d = self.defs[name]
        return list(d.deps) if d.derived else [name]

    # ---- data access
    def _ctx(self, d, storm):
        """Context for a derived field; storm defaults to the domain motion."""
        if not d.storm:
            return self.ctx
        return dict(self.ctx, storm=tuple(storm) if storm is not None
                    else (self.ctx["umove"], self.ctx["vmove"]))

    def plane(self, name, t, mode="height", value=1.0, storm=None):
        """2D (nj, ni) array of a field.
        mode: 'height' (km AGL), 'level' (model level index), 'colmax', 'colmin'.
        storm: ground-relative storm motion (m/s) for storm-relative fields."""
        d = self.defs[name]
        if d.ndim == 2:
            mode, value = "2d", 0
        ctx = self._ctx(d, storm)
        key = (name, t, mode, round(float(value), 4),
               tuple(round(float(x), 3) for x in ctx["storm"]) if d.storm else None)
        with self._lock:
            a = self._planes.get(key)
            if a is not None:
                self._planes.move_to_end(key)
                return a
        if mode in ("colmax", "colmin"):
            vol = self.volume(name, t, storm)
            a = vol.max(axis=0) if mode == "colmax" else vol.min(axis=0)
        else:
            run = self.run

            def fetch(n):
                if mode == "level":
                    return run.read_level(n, t, int(value))
                if mode == "2d":
                    return run.read_level(n, t)
                return run.read_height(n, t, float(value))

            a = d.func(fetch, ctx) if d.derived else fetch(name) * d.scale
        # a copy: a slice of a cached volume would keep the whole volume alive
        a = np.array(a, dtype=np.float32)
        with self._lock:
            self._planes[key] = a
            while len(self._planes) > 40:
                self._planes.popitem(last=False)
        return a

    def forget(self, t, names):
        """Drop cached planes at time t of `names` and the fields derived from them
        (after those were recomputed)."""
        names = set(names)
        dep = {n for n, d in self.defs.items() if n in names or names & set(d.deps)}
        with self._lock:
            for k in [k for k in self._planes if k[1] == t and k[0] in dep]:
                del self._planes[k]
        self.run.forget(dep, t)

    def volume(self, name, t, storm=None):
        d = self.defs[name]
        if d.derived:
            # derived volumes are cached too (as '~name', '~name@u,v' if storm-relative)
            ctx = self._ctx(d, storm)
            key = f"~{name}" + ("@{:.3f},{:.3f}".format(*ctx["storm"]) if d.storm else "")
            vol = self.run.cached(key, t)
            if vol is None:
                self.run.load_volumes(d.deps, t)
                vol = np.asarray(d.func(lambda n: self.run.volume(n, t), ctx),
                                 dtype=np.float32)
                self.run._insert(key, t, vol)
            return vol
        vol = self.run.volume(name, t)
        return vol if d.scale == 1.0 else vol * np.float32(d.scale)

    def at_points(self, name, t, sample, storm=None):
        """Field values at arbitrary points: sample(vol) -> values.  Pointwise derived
        fields are computed from sampled inputs, so no derived volume is built."""
        d = self.defs[name]
        if d.derived and d.pointwise:
            self.run.load_volumes(d.deps, t)
            return np.asarray(d.func(lambda n: sample(self.run.volume(n, t)),
                                     self._ctx(d, storm)))
        if d.derived:
            return np.asarray(sample(self.volume(name, t, storm)))
        return np.asarray(sample(self.run.volume(name, t))) * d.scale

    def auto_range(self, name, a):
        d = self.defs[name]
        if d.vrange is not None:
            return d.vrange
        finite = a[np.isfinite(a)]
        if finite.size == 0:
            return (0.0, 1.0)
        sub = finite[:: max(1, finite.size // 200000)]
        if d.diverging:
            m = float(np.percentile(np.abs(sub), 99.5)) or 1.0
            return (-m, m)
        lo, hi = np.percentile(sub, [0.5, 99.5])
        if hi <= lo:
            hi = lo + 1.0
        return (float(lo), float(hi))
