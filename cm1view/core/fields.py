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


# colormaps with a neutral (white) middle: kept on 0 when the range has both signs
DIVERGING = {"BrBG", "PiYG", "PRGn", "PuOr", "RdBu", "RdGy", "RdYlBu", "RdYlGn", "bwr",
             "coolwarm", "seismic", "cmo.balance", "cmo.curl", "cmo.delta", "cmo.diff",
             "cmo.tarn"}


def zero_window(name, lo=None, hi=None):
    """(start, stop) of the part of colormap `name` that keeps its middle on 0 over
    lo..hi: -2..6 on RdBu uses 0.33..1 (the colours of -6..6, cut at -2).  (0, 1) when
    the map is not diverging or lo..hi does not cross 0."""
    base = name[:-2] if name.endswith("_r") else name
    if base not in DIVERGING or lo is None or hi is None or not lo < 0 < hi:
        return 0.0, 1.0
    m = 2.0 * max(-lo, hi)
    return 0.5 + lo / m, 0.5 + hi / m


def palette(name, n=256, reverse=False, lo=None, hi=None):
    """n colours of colormap `name`; given lo / hi, a diverging map stays white at 0."""
    if name == "reflectivity":
        pal = _reflectivity(n)
        return pal[::-1] if reverse else pal
    a, b = zero_window(name, lo, hi)
    p = np.linspace(a, b, n)
    cmap = matplotlib.colormaps[name]
    return [mcolors.to_hex(c) for c in cmap(1.0 - p if reverse else p)]


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
                 storm=False, layer=None, edges=False, costly=False):
        self.name, self.label, self.units, self.group = name, label, units, group
        # layer: a column field (2D from 3D natives) over (z0, z1) km AGL, z1 None: the
        # model top.  func(f, c) gets f(n) -> (levels, ny, nx) of native n on the model
        # levels whose cells reach into the layer, c["dz"] (m, each one's thickness in
        # it), c["zk"] (km) and c["top"] (the layer top, km); see column_levels.
        # edges: also the level just below and above the layer (thickness 0), so func
        # can interpolate to its bounds
        self.layer = None if layer is None else tuple(layer)
        self.edges = edges
        # costly: a column field slow per column (parcels): computed on every
        # column_stride(run)-th column, and func gets c["memo"] (a dict shared by the
        # fields of one time, to keep results such as a parcel's) and c["threads"]
        self.costly = costly
        if self.layer is not None:
            ndim, pointwise = 2, False
        self.ndim, self.scale, self.cmap, self.vrange = ndim, scale, cmap, vrange
        self.diverging, self.deps, self.func = diverging, tuple(deps), func
        # deps may name derivatives of native fields ("ddz.winterp": per km, in the
        # field's display units), which Fields and the series worker compute for func
        # pointwise: func works on any samples of its inputs (no spatial derivatives)
        self.pointwise = pointwise and not any(split_deriv(n)[0] for n in self.deps)
        # storm: depends on the storm motion, c["storm"] = ground-relative (u, v) m/s
        self.storm = storm

    @property
    def derived(self):
        return self.func is not None

    @property
    def column(self):
        return self.layer is not None

    def levels(self, z, zf):
        """(ks, dz) of a column field's layer on model levels z, cell faces zf (km)."""
        return column_levels(z, zf, *self.layer, edges=self.edges)

    @property
    def natives(self):
        """The native fields read: deps, with a derivative's base field in its place."""
        return tuple(dict.fromkeys(split_deriv(n)[1] for n in self.deps))

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
    # baroclinic generation of horizontal vorticity, ∇ × (B k) = (∂B/∂y, −∂B/∂x): the
    # components of the "Baroclinic generation" vector (core/vectors.py)
    bdeps = ("th", "qv", "th0", "qv0", *hyd)
    D.append(FieldDef("bgen_x", "Baroclinic x-vorticity generation (∂B/∂y)", "10⁻⁴ s⁻²",
                      "Kinematics", cmap="RdBu_r", vrange=(-2, 2), diverging=True, deps=bdeps,
                      func=lambda f, c: 1.0e4 * np.gradient(buoy(f, c), c["dy"], axis=-2),
                      pointwise=False))
    D.append(FieldDef("bgen_y", "Baroclinic y-vorticity generation (−∂B/∂x)", "10⁻⁴ s⁻²",
                      "Kinematics", cmap="RdBu_r", vrange=(-2, 2), diverging=True, deps=bdeps,
                      func=lambda f, c: -1.0e4 * np.gradient(buoy(f, c), c["dx"], axis=-1),
                      pointwise=False))
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
    D += _vort_tendencies()
    D += _columns()
    D += _sounding_kinematics()
    D += _sounding_thermo()
    return [d for d in D if all(x in avail for x in d.natives)]


def _vort_tendencies():
    """Vertical-vorticity tendencies and the Okubo–Weiss parameter, in 10⁻⁴ s⁻².  Their
    deps' derivatives are per km (m/s per km = 10⁻³ s⁻¹)."""
    def stretch(f, c):  # ζ ∂w/∂z
        return 10.0 * f("zvort") * f("ddz.winterp")

    def tilt(f, c):  # ξ ∂w/∂x + η ∂w/∂y
        return 10.0 * (f("xvort") * f("ddx.winterp") + f("yvort") * f("ddy.winterp"))

    def okubo(f, c):  # W = s_n² + s_s² − ω² (strain dominates > 0, rotation < 0)
        ux, uy, vx, vy = (f("ddx.uinterp"), f("ddy.uinterp"), f("ddx.vinterp"),
                          f("ddy.vinterp"))
        return 0.01 * ((ux - vy) ** 2 + (vx + uy) ** 2 - (vx - uy) ** 2)

    g, kw = "Vorticity tendencies", dict(cmap="RdBu_r", vrange=(-5, 5), diverging=True)
    sdeps = ("zvort", "ddz.winterp")
    tdeps = ("xvort", "yvort", "ddx.winterp", "ddy.winterp")
    return [
        FieldDef("zstretch", "ζ stretching (ζ ∂w/∂z)", "10⁻⁴ s⁻²", g, deps=sdeps,
                 func=stretch, **kw),
        FieldDef("ztilt", "ζ tilting (ξ ∂w/∂x + η ∂w/∂y)", "10⁻⁴ s⁻²", g, deps=tdeps,
                 func=tilt, **kw),
        FieldDef("ztend", "ζ stretching + tilting", "10⁻⁴ s⁻²", g, deps=sdeps + tdeps,
                 func=lambda f, c: stretch(f, c) + tilt(f, c), **kw),
        FieldDef("okubo", "Okubo–Weiss (s_n² + s_s² − ω²)", "10⁻⁴ s⁻²", g,
                 deps=("ddx.uinterp", "ddy.uinterp", "ddx.vinterp", "ddy.vinterp"),
                 func=okubo, **kw),
    ]


def _columns():
    """Column fields (2D from 3D): updraft helicity and layer maxima."""
    def uh(f, c):  # ∫ w ζ dz
        return np.tensordot(c["dz"], f("winterp") * f("zvort"), axes=1)

    def top(n):
        return lambda f, c: f(n).max(axis=0)

    g = "Column fields"
    return [
        FieldDef("uh25", "Updraft helicity 2–5 km (∫ w ζ dz)", "m²/s²", g, cmap="magma",
                 vrange=(0, 300), deps=("winterp", "zvort"), func=uh, layer=(2.0, 5.0)),
        FieldDef("uh01", "Updraft helicity 0–1 km (∫ w ζ dz)", "m²/s²", g, cmap="magma",
                 vrange=(0, 50), deps=("winterp", "zvort"), func=uh, layer=(0.0, 1.0)),
        FieldDef("zvmax01", "Max vertical vorticity 0–1 km", "1/s", g, cmap="magma",
                 vrange=(0, 0.05), deps=("zvort",), func=top("zvort"), layer=(0.0, 1.0)),
        FieldDef("wmax", "Column max vertical velocity", "m/s", g, cmap="turbo",
                 vrange=(0, 50), deps=("winterp",), func=top("winterp"),
                 layer=(0.0, None)),
    ]


def _wind(f, c):  # ground-relative
    return f("uinterp") + c["umove"], f("vinterp") + c["vmove"]


def bulk_shear(u, v, zk, top):
    """|V(top) − V(lowest level)| of (L, ...) winds on levels zk (km)."""
    return np.hypot(at_height(u, zk, top) - u[0], at_height(v, zk, top) - v[0])


def helicity(u, v, zk, top, storm):
    """Storm-relative helicity from the lowest level to top km:
    Σ (u_k+1 − cx)(v_k − cy) − (u_k − cx)(v_k+1 − cy)."""
    u = layer_points(u - storm[0], zk, top)
    v = layer_points(v - storm[1], zk, top)
    return (u[1:] * v[:-1] - u[:-1] * v[1:]).sum(axis=0)


def _sounding_kinematics():
    """Bulk shear and storm-relative helicity of every column, as the soundings give
    them (thermo.analyze): from the lowest model level up to the layer top, the winds
    linearly interpolated between the levels."""
    def shear(f, c):
        return bulk_shear(*_wind(f, c), c["zk"], c["top"])

    def srh(f, c):
        return helicity(*_wind(f, c), c["zk"], c["top"], c["storm"])

    g, deps = "Sounding parameters", ("uinterp", "vinterp")
    kw = dict(deps=deps, edges=True)
    return [
        FieldDef("shear01", "Bulk shear 0–1 km", "m/s", g, cmap="viridis", vrange=(0, 25),
                 func=shear, layer=(0.0, 1.0), **kw),
        FieldDef("shear06", "Bulk shear 0–6 km", "m/s", g, cmap="viridis", vrange=(0, 40),
                 func=shear, layer=(0.0, 6.0), **kw),
        FieldDef("srh01", "Storm-relative helicity 0–1 km", "m²/s²", g, cmap="RdBu_r",
                 vrange=(-300, 300), diverging=True, func=srh, layer=(0.0, 1.0),
                 storm=True, **kw),
        FieldDef("srh03", "Storm-relative helicity 0–3 km", "m²/s²", g, cmap="RdBu_r",
                 vrange=(-500, 500), diverging=True, func=srh, layer=(0.0, 3.0),
                 storm=True, **kw),
    ]


def _parcel(f, c, kind):
    """(CAPE, CIN, LCL m) of parcel kind ('sb', 'ml', 'mu') in the columns, kept in
    c["memo"] for the other fields of this time."""
    memo = c.get("memo")
    if memo is not None and kind in memo:
        return memo[kind]
    from . import thermo
    out = thermo.parcel_columns(1000.0 * np.asarray(c["zk"], np.float64), f("prs"),
                                f("th"), f("qv"), kind, c.get("threads", 1))
    if memo is not None:
        memo[kind] = out
    return out


def _sounding_thermo():
    """CAPE, CIN and LCL of surface-based, 100 hPa mixed-layer and most-unstable
    parcels in every column, and fixed-layer STP and SCP: as the soundings compute
    them (thermo.analyze), on every column_stride-th column."""
    g, deps = "Sounding parameters", ("prs", "th", "qv")
    kw = dict(layer=(0.0, None), costly=True)
    names = dict(sb="Surface-based", ml="Mixed-layer (100 hPa)", mu="Most-unstable")
    D = []
    for kind, lab in names.items():
        def pick(i, kind=kind):
            return lambda f, c: _parcel(f, c, kind)[i]
        D += [
            FieldDef(f"{kind}cape", f"{lab} CAPE", "J/kg", g, cmap="magma",
                     vrange=(0, 4000), deps=deps, func=pick(0), **kw),
            FieldDef(f"{kind}cin", f"{lab} CIN", "J/kg", g, cmap="cmo.ice",
                     vrange=(-300, 0), deps=deps, func=pick(1), **kw),
            FieldDef(f"{kind}lcl", f"{lab} LCL height", "m AGL", g, cmap="cividis",
                     vrange=(0, 3000), deps=deps, func=pick(2), **kw),
        ]

    def stp(f, c):  # (SBCAPE/1500)(SBLCL term)(0–1 km SRH/150)(0–6 km shear term)
        cape, _, lcl = _parcel(f, c, "sb")
        u, v = _wind(f, c)
        zk = c["zk"]
        bwd = bulk_shear(u, v, zk, 6.0)
        return ((cape / 1500.0) * np.clip((2000.0 - lcl) / 1000.0, 0.0, 1.0)
                * (helicity(u, v, zk, 1.0, c["storm"]) / 150.0)
                * np.where(bwd < 12.5, 0.0, np.minimum(bwd, 30.0) / 20.0))

    def scp(f, c):  # (MUCAPE/1000)(0–3 km SRH/50)(0–6 km shear term)(MUCIN term)
        cape, cin, _ = _parcel(f, c, "mu")
        u, v = _wind(f, c)
        zk = c["zk"]
        bwd = bulk_shear(u, v, zk, 6.0)
        return ((cape / 1000.0) * (helicity(u, v, zk, 3.0, c["storm"]) / 50.0)
                * np.where(bwd < 10.0, 0.0, np.minimum(bwd, 20.0) / 20.0)
                * np.where(cin > -40.0, 1.0, -40.0 / np.minimum(cin, -40.0)))

    wdeps = deps + ("uinterp", "vinterp")
    ckw = dict(cmap="RdBu_r", diverging=True, deps=wdeps, storm=True, **kw)
    D += [
        FieldDef("stp", "Significant tornado parameter (fixed layer)", "", g,
                 vrange=(-6, 6), func=stp, **ckw),
        FieldDef("scp", "Supercell composite parameter (fixed layer)", "", g,
                 vrange=(-20, 20), func=scp, **ckw),
    ]
    return D


COSTLY = frozenset(d.name for d in _sounding_thermo())  # (names of the costly fields)


def finite_sample(a, n=200000):
    """About n of a's finite values, evenly spaced (for percentiles of a large array:
    the stride is taken before the finite test, so no full-size copy is made)."""
    a = np.asarray(a).ravel()
    sub = a[:: max(1, a.size // n)]
    return sub[np.isfinite(sub)]


def column_stride(run):
    """Columns apart of the costly column fields' computed columns: the column_stride
    setting; auto: the smallest that keeps them to about 250 000 (1 up to 500 x 500)."""
    from .. import config
    s = config.get("column_stride")
    if s == "auto":
        s = int(np.ceil(np.sqrt(run.ni * run.nj / 250000.0)))
    return max(1, int(s))


def stride_cols(lo, hi, n, s):
    """Points lo..hi-1 (of n along an axis) on a stride s: each s-wide block (from 0)
    takes the value at its middle point.  Returns (r0, r1, take, back): read r0..r1,
    keep `take` of those (relative to r0); back[i - lo] is point i's among the kept."""
    idx = np.minimum((np.arange(lo, hi) // s) * s + s // 2, n - 1)
    u, back = np.unique(idx, return_inverse=True)
    return int(u[0]), int(u[-1]) + 1, u - u[0], back


def at_height(a, zk, h):
    """(L, ...) values a on levels zk (km) linearly interpolated to height h km,
    held at the end levels beyond them."""
    zk = np.asarray(zk, dtype=np.float64)
    if zk.size == 1 or h <= zk[0]:
        return a[0]
    if h >= zk[-1]:
        return a[-1]
    k = int(np.searchsorted(zk, h)) - 1
    w = (h - zk[k]) / (zk[k + 1] - zk[k])
    return (1.0 - w) * a[k] + w * a[k + 1]


def layer_points(a, zk, top):
    """(P, ...) a from the lowest level up to height top km: the levels below it, then
    its value at top (interpolated)."""
    zk = np.asarray(zk, dtype=np.float64)
    below = np.flatnonzero(zk < top)
    if below.size == 0:
        return a[:1]
    return np.concatenate([a[below], at_height(a, zk, top)[None]])


def layer_top(d, run):
    """Top (km) of column field d's layer (None: the model top)."""
    return float(run.zf[-1]) if d.layer[1] is None else float(d.layer[1])


def column_levels(z, zf, z0, z1, edges=False):
    """(ks, dz) of a column layer z0..z1 km AGL (z1 None: the model top): the model
    levels (heights z, km) whose cells (between the zf levels) reach into it, and each
    one's thickness inside it (m), so sum(dz * f[ks]) integrates f over the layer.
    edges: also the level below and above those (where there is one), thickness 0."""
    zf = np.asarray(zf, dtype=np.float64)
    top = zf[-1] if z1 is None else float(z1)
    lo, hi = np.clip(zf[:-1], z0, top), np.clip(zf[1:], z0, top)
    ks = np.flatnonzero(hi > lo)
    if ks.size == 0:  # (a layer thinner than nothing: the nearest level)
        ks = np.array([int(np.argmin(np.abs(np.asarray(z) - z0)))])
        return [int(ks[0])], np.zeros(1)
    dz = 1000.0 * (hi - lo)[ks]
    if edges:
        lo_k, hi_k = int(ks[0]) - 1, int(ks[-1]) + 1
        if lo_k >= 0:
            ks, dz = np.concatenate([[lo_k], ks]), np.concatenate([[0.0], dz])
        if hi_k < len(zf) - 1:
            ks, dz = np.concatenate([ks, [hi_k]]), np.concatenate([dz, [0.0]])
    return [int(k) for k in ks], dz


GROUP_ORDER = ["Radar", "Kinematics", "Vorticity tendencies", "Column fields",
               "Sounding parameters", "Thermodynamics",
               "Pressure decomposition", "Microphysics", "Swaths & 2D", "Turbulence",
               "Budgets", "Base state"]


# ---- derivatives of any field, per km: "ddz.winterp" (∂w/∂z), "ddx.", "ddy.", "gradh."
# (|∇h|).  Built on demand by Fields / AllFields, not listed in the field lists: a
# Derivative select beside a Field select names them (deriv_name).
DERIVS = OrderedDict([("ddz", "∂/∂z"), ("ddx", "∂/∂x"), ("ddy", "∂/∂y"), ("gradh", "|∇h|")])


def deriv_name(op, base):
    """The field name of derivative op ('' : none) of field `base`."""
    return f"{op}.{base}" if op else base


def split_deriv(name):
    """(op, base field) of a derivative's name; ('', name) for any other field."""
    if not isinstance(name, str):
        return "", name
    op, dot, base = name.partition(".")
    return (op, base) if dot and op in DERIVS else ("", name)


def deriv_options(d):
    """{label: op} for a Derivative select of field d (∂/∂z: 3D fields only)."""
    return {"None": ""} | {v: k for k, v in DERIVS.items() if k != "ddz" or d.ndim == 3}


def _per_km(units):
    return {"m/s": "10⁻³ s⁻¹", "1/s": "s⁻¹ km⁻¹", "": "km⁻¹"}.get(units, f"{units} km⁻¹")


def _no_func(f, c):
    raise ValueError("a derivative is computed from whole levels (Fields.plane / volume)")


def deriv_def(op, base):
    """FieldDef of derivative op of field `base` (a FieldDef), in its units per km
    (m/s: 10⁻³ s⁻¹); None when there is none (∂/∂z of a 2D field)."""
    if op not in DERIVS or (op == "ddz" and base.ndim != 3):
        return None
    vr = None
    if base.vrange is not None:  # (a starting range: half the field's per km)
        m = 0.5 * max(abs(float(base.vrange[0])), abs(float(base.vrange[1])))
        vr = (0.0, m) if op == "gradh" else (-m, m)
    deps = base.deps if base.derived else (base.name,)
    return FieldDef(deriv_name(op, base.name), f"{base.label} · {DERIVS[op]}",
                    _per_km(base.units), "Derivatives", ndim=base.ndim,
                    cmap="magma" if op == "gradh" else "RdBu_r", vrange=vr,
                    diverging=op != "gradh", deps=deps, func=_no_func, pointwise=False,
                    storm=base.storm)


def ddz_level(f, z, k):
    """∂/∂z (per km) on model level k of f(level) -> plane, on levels z (km): centred
    on the stretched levels inside, one-sided at the bottom and top (as np.gradient of
    the volume, so maps, sections and series agree)."""
    nk = len(z)
    k = min(max(int(k), 0), nk - 1)
    lo, hi = max(k - 1, 0), min(k + 1, nk - 1)
    if lo == hi:
        return np.zeros_like(f(k))
    if lo == k or hi == k:
        return (f(hi) - f(lo)) / (z[hi] - z[lo])
    hl, hr = z[k] - z[lo], z[hi] - z[k]
    return (hl * hl * f(hi) - hr * hr * f(lo) + (hr * hr - hl * hl) * f(k)) / \
        (hl * hr * (hl + hr))


def hgrad(op, a, xkm, ykm):
    """Horizontal derivative op ('ddx', 'ddy', 'gradh') of a (..., ny, nx) array on
    the grid's x / y (km; stretched grids too), per km."""
    def d(axis, c):
        return np.gradient(a, c, axis=axis) if a.shape[axis] > 1 else np.zeros_like(a)
    if op == "ddx":
        return d(-1, xkm)
    if op == "ddy":
        return d(-2, ykm)
    return np.hypot(d(-1, xkm), d(-2, ykm))


def once(fetch):
    """fetch(name), each name fetched once: a derived field asks for its inputs several
    times (θe: prs three times), and each ask of a plane not cached is a read."""
    got = {}

    def f(n):
        if n not in got:
            got[n] = fetch(n)
        return got[n]
    return f


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
        self._derivs = {}  # (derivative name -> its FieldDef, built when first asked)
        self._memo = OrderedDict()  # (t, stride) -> costly column fields' shared results

    # ---- catalog helpers
    def __getitem__(self, name):
        d = self.defs.get(name) if isinstance(name, str) else None
        if d is None:
            d = self._deriv(name)
            if d is None:
                raise KeyError(name)
        return d

    def __contains__(self, name):
        return (isinstance(name, str) and name in self.defs) or self._deriv(name) is not None

    def _deriv(self, name):
        """FieldDef of a derivative's name (split_deriv), or None."""
        op, base = split_deriv(name)
        if not op or base not in self.defs:
            return None
        d = self._derivs.get(name)
        if d is None:
            d = deriv_def(op, self.defs[base])
            if d is not None:
                self._derivs[name] = d
        return d

    def groups(self, ndim=None):
        """{group: {label: name}} for grouped Select widgets."""
        out = OrderedDict((g, OrderedDict()) for g in GROUP_ORDER)
        for d in self.defs.values():
            if ndim is not None and d.ndim != ndim:
                continue
            out.setdefault(d.group, OrderedDict())[f"{d.label} [{d.name}]"] = d.name
        return OrderedDict((g, v) for g, v in out.items() if v)

    def native_deps(self, name):
        d = self[name]
        return list(d.natives) if d.derived else [name]

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
        d = self[name]
        if d.ndim == 2:
            mode, value = "2d", 0
        ctx = self._ctx(d, storm)
        key = (name, t, mode, round(float(value), 4),
               tuple(round(float(x), 3) for x in ctx["storm"]) if d.storm else None,
               column_stride(self.run) if d.costly else None)
        with self._lock:
            a = self._planes.get(key)
            if a is not None:
                self._planes.move_to_end(key)
                return a
        op, base = split_deriv(name)
        if mode in ("colmax", "colmin"):
            vol = self.volume(name, t, storm)
            a = vol.max(axis=0) if mode == "colmax" else vol.min(axis=0)
        elif op:
            a = self._deriv_plane(op, base, t, mode, value, storm)
        elif d.column:
            a = self._column(d, t, ctx)
        else:
            run = self.run

            def fetch(n):
                if split_deriv(n)[0]:  # (a derivative input, e.g. ∂w/∂z)
                    return self.plane(n, t, mode, value, storm)
                if mode == "level":
                    return run.read_level(n, t, int(value))
                if mode == "2d":
                    return run.read_level(n, t)
                return run.read_height(n, t, float(value))

            a = d.func(once(fetch), ctx) if d.derived else fetch(name) * d.scale
        # a copy: a slice of a cached volume would keep the whole volume alive
        a = np.array(a, dtype=np.float32)
        with self._lock:
            self._planes[key] = a
            while len(self._planes) > 40:
                self._planes.popitem(last=False)
        return a

    def _column(self, d, t, ctx):
        """A column field: its inputs on the levels of its layer only (a costly one on
        every column_stride-th column, each block of columns showing its middle one)."""
        run = self.run
        ks, dz = d.levels(run.z, run.zf)
        c = dict(ctx, dz=dz, zk=run.z[ks], top=layer_top(d, run))
        layers = once(lambda n: np.stack([run.read_level(n, t, k) for k in ks]))
        if not d.costly:
            return d.func(layers, c)
        s = column_stride(run)
        with self._lock:
            memo = self._memo.setdefault((t, s), {})
            self._memo.move_to_end((t, s))
            while len(self._memo) > 4:
                self._memo.popitem(last=False)
        c.update(memo=memo, threads=run.workers)
        if s == 1:
            return d.func(layers, c)
        r0, r1, tj, bj = stride_cols(0, run.nj, run.nj, s)
        c0, c1, ti, bi = stride_cols(0, run.ni, run.ni, s)
        a = d.func(once(lambda n: np.stack([run.read_level(n, t, k)[r0:r1, c0:c1][
            np.ix_(tj, ti)] for k in ks])), c)
        return np.asarray(a)[np.ix_(bj, bi)]

    def _deriv_plane(self, op, base, t, mode, value, storm):
        """2D derivative op of field base: horizontal ones of its plane; ∂/∂z on a
        model level from the levels next to it (as np.gradient does on the volume, so
        maps and cross-sections agree), at a height between the two levels' values."""
        if op != "ddz":
            if self.defs[base].ndim == 2:
                mode, value = "2d", 0
            return hgrad(op, self.plane(base, t, mode, value, storm), self.run.xh,
                         self.run.yh)
        if mode == "level":
            return self._ddz_level(base, t, int(value), storm)
        k0, k1, w = self.run.level_weights(float(value))
        a = self._ddz_level(base, t, k0, storm)
        if w == 0.0 or k1 == k0:
            return a
        return (1.0 - w) * a + w * self._ddz_level(base, t, k1, storm)

    def _ddz_level(self, base, t, k, storm):
        """∂/∂z (per km) of field base on model level k (ddz_level)."""
        return ddz_level(lambda kk: self.plane(base, t, "level", kk, storm), self.run.z, k)

    def forget(self, t, names):
        """Drop cached planes at time t of `names` and the fields derived from them
        (after those were recomputed)."""
        names = set(names)
        dep = {n for n, d in self.defs.items() if n in names or names & set(d.natives)}
        dep |= {n for n in list(self._derivs) if split_deriv(n)[1] in dep}
        with self._lock:
            for k in [k for k in self._planes if k[1] == t and k[0] in dep]:
                del self._planes[k]
            if any(self.defs[n].costly for n in dep if n in self.defs):
                for k in [k for k in self._memo if k[0] == t]:
                    del self._memo[k]
        self.run.forget(dep, t)

    def volume(self, name, t, storm=None):
        d = self[name]
        if d.column:  # (2D: its plane)
            return self.plane(name, t, storm=storm)
        op, base = split_deriv(name)
        if op:  # (cached as '~ddz.w', '~ddz.name@u,v' if storm-relative)
            ctx = self._ctx(d, storm)
            key = f"~{name}" + ("@{:.3f},{:.3f}".format(*ctx["storm"]) if d.storm else "")
            vol = self.run.cached(key, t)
            if vol is None:
                b = np.asarray(self.volume(base, t, storm), dtype=np.float32)
                vol = np.asarray(np.gradient(b, self.run.z, axis=0) if op == "ddz" else
                                 hgrad(op, b, self.run.xh, self.run.yh), dtype=np.float32)
                self.run._insert(key, t, vol)
            return vol
        if d.derived:
            # derived volumes are cached too (as '~name', '~name@u,v' if storm-relative)
            ctx = self._ctx(d, storm)
            key = f"~{name}" + ("@{:.3f},{:.3f}".format(*ctx["storm"]) if d.storm else "")
            vol = self.run.cached(key, t)
            if vol is None:
                self.run.load_volumes(d.natives, t)
                vol = np.asarray(d.func(lambda n: self._input(n, t, storm), ctx),
                                 dtype=np.float32)
                self.run._insert(key, t, vol)
            return vol
        vol = self.run.volume(name, t)
        return vol if d.scale == 1.0 else vol * np.float32(d.scale)

    def _input(self, n, t, storm):
        """Volume of a derived field's input n: raw native, or a derivative."""
        return self.volume(n, t, storm) if split_deriv(n)[0] else self.run.volume(n, t)

    def at_points(self, name, t, sample, storm=None):
        """Field values at arbitrary points: sample(vol) -> values.  Pointwise derived
        fields are computed from sampled inputs, so no derived volume is built."""
        d = self[name]
        if d.derived and d.pointwise:
            self.run.load_volumes(d.natives, t)
            return np.asarray(d.func(once(lambda n: sample(self.run.volume(n, t))),
                                     self._ctx(d, storm)))
        if d.derived:
            return np.asarray(sample(self.volume(name, t, storm)))
        return np.asarray(sample(self.run.volume(name, t))) * d.scale

    def auto_range(self, name, a):
        d = self[name]
        if d.vrange is not None:
            return d.vrange
        sub = finite_sample(a)
        if sub.size == 0:
            return (0.0, 1.0)
        if d.diverging:
            m = float(np.percentile(np.abs(sub), 99.5)) or 1.0
            return (-m, m)
        lo, hi = np.percentile(sub, [0.5, 99.5])
        if hi <= lo:
            hi = lo + 1.0
        return (float(lo), float(hi))
