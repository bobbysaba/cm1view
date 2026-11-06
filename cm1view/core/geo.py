"""Where a run's grid sits on the Earth, and map boundary lines on it.

A run with a map projection (WoFS / WRF: Run.geo) gets a Geo: its projection
(pyproj) and the projected position of cm1view's x = y = 0.  Boundary lines are
projected INTO the grid's x, y (km); the data are never reprojected.  Idealized runs
(CM1) have no geo (Run.geo None).

The lines ship with cm1view (data/boundaries.npz, built by tools/make_boundaries.py
from public-domain US Census and Natural Earth files); nothing is downloaded.
"""

import os
import threading

import numpy as np

# boundary layers in data/boundaries.npz (see tools/make_boundaries.py)
KINDS = ("coastlines", "countries", "states", "lakes", "counties")
KIND_LABELS = {"coastlines": "Coastlines", "countries": "Countries",
               "states": "States / provinces", "lakes": "Lakes",
               "counties": "Counties (US)"}
SHOWN = ("coastlines", "countries", "states", "lakes")  # drawn unless chosen otherwise
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data",
                    "boundaries.npz")
Q = 1e4  # points per degree in the file
R_WRF = 6370000.0  # WRF's Earth: a sphere of this radius (m)
TOL = 0.1  # largest allowed misfit to the file's lat/lon, in grid spacings

_layers = {}  # kind -> (n, bb, lon/lat int32 (2, N), start index of each polyline)
_layers_lock = threading.Lock()


def _layer(kind):
    with _layers_lock:
        if kind not in _layers:
            if kind not in KINDS:
                raise KeyError(f"unknown boundary layer {kind!r} (one of {', '.join(KINDS)})")
            with np.load(DATA) as z:
                n, bb, d = z[kind + "_n"], z[kind + "_bb"], z[kind + "_d"]
            q = np.cumsum(d, axis=1, dtype=np.int64).astype(np.int32)
            start = np.concatenate([[0], np.cumsum(n[:-1], dtype=np.int64)])
            _layers[kind] = (n, bb, q, start)
        return _layers[kind]


def wrf_crs(attrs):
    """pyproj CRS of a WRF grid from its global attributes, or None (no projection
    cm1view knows: MAP_PROJ 1 Lambert conformal, 2 polar stereographic, 3 Mercator)."""
    try:
        proj = int(attrs["MAP_PROJ"])
        t1 = float(attrs["TRUELAT1"])
        lon0 = float(attrs["STAND_LON"])
    except (KeyError, TypeError, ValueError):
        return None
    if proj == 1:
        t2 = float(attrs.get("TRUELAT2", t1))
        lat0 = float(attrs.get("MOAD_CEN_LAT", attrs.get("CEN_LAT", t1)))
        p4 = f"+proj=lcc +lat_1={t1} +lat_2={t2} +lat_0={lat0} +lon_0={lon0}"
    elif proj == 2:
        p4 = f"+proj=stere +lat_0={90.0 if t1 >= 0 else -90.0} +lat_ts={t1} +lon_0={lon0}"
    elif proj == 3:
        p4 = f"+proj=merc +lat_ts={t1} +lon_0={lon0}"
    else:
        return None
    from pyproj import CRS
    return CRS.from_proj4(f"{p4} +R={R_WRF} +units=m +no_defs")


def from_wrf(attrs, xh, yh, lat=None, lon=None):
    """The Geo of a WRF grid whose mass points are at xh, yh (km), or None.  With the
    file's lat, lon of those points (2D, nj x ni) the origin comes from them and the
    projection must place every point within TOL grid spacings of them (else None);
    without, the origin is the projected CEN_LAT, CEN_LON (the domain centre)."""
    crs = wrf_crs(attrs)
    if crs is None:
        return None
    g = Geo(crs, 0.0, 0.0)
    xh, yh = np.asarray(xh, np.float64), np.asarray(yh, np.float64)
    d = float(min(np.min(np.diff(xh)), np.min(np.diff(yh))))
    g.spacing = d
    if lat is not None and lon is not None:
        px, py = g.xy(np.asarray(lon, np.float64), np.asarray(lat, np.float64))
        ex, ey = px - xh[None, :], py - yh[:, None]
        g.x0, g.y0 = float(np.mean(ex)), float(np.mean(ey))
        miss = float(np.max(np.hypot(ex - g.x0, ey - g.y0)))
        if not np.isfinite(miss) or miss > TOL * d:
            return None
        g.misfit = miss
    else:
        try:
            cx, cy = g.xy(float(attrs["CEN_LON"]), float(attrs["CEN_LAT"]))
        except (KeyError, TypeError, ValueError):
            return None
        g.x0 = float(cx - 0.5 * (xh[0] + xh[-1]))
        g.y0 = float(cy - 0.5 * (yh[0] + yh[-1]))
    g.limits = (float(xh[0]), float(xh[-1]), float(yh[0]), float(yh[-1]))
    return g


class Geo:
    """A grid's map projection.  x, y in km as cm1view's (origin x0, y0 km in the
    projection's coordinates); lon, lat in degrees."""

    def __init__(self, crs, x0=0.0, y0=0.0):
        from pyproj import Transformer
        self.crs = crs
        self.x0, self.y0 = x0, y0
        self.limits = None  # x0, x1, y0, y1 (km) of the grid's mass points
        self.spacing = None  # grid spacing (km)
        self.misfit = None  # largest distance (km) to the file's lat/lon, if checked
        self._fwd = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
        self._inv = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
        self._lines = {}
        self._lock = threading.Lock()

    def xy(self, lon, lat):
        """x, y (km) of lon, lat (degrees)."""
        x, y = self._fwd.transform(lon, lat)
        return np.asarray(x) / 1000.0 - self.x0, np.asarray(y) / 1000.0 - self.y0

    def lonlat(self, x, y):
        """lon, lat (degrees) of x, y (km)."""
        lon, lat = self._inv.transform((np.asarray(x, np.float64) + self.x0) * 1000.0,
                                       (np.asarray(y, np.float64) + self.y0) * 1000.0)
        return np.asarray(lon), np.asarray(lat)

    def box(self, xlim, ylim):
        """lon0, lon1, lat0, lat1 around the x, y box: lons unwrapped about its centre
        (lon1 - lon0 may pass 180 W/E), all lons if a pole is inside."""
        (xa, xb), (ya, yb) = xlim, ylim
        s = np.linspace(0.0, 1.0, 65)
        ex = np.concatenate([xa + (xb - xa) * s, np.full(65, xb), xb - (xb - xa) * s,
                             np.full(65, xa)])
        ey = np.concatenate([np.full(65, ya), ya + (yb - ya) * s, np.full(65, yb),
                             yb - (yb - ya) * s])
        lon, lat = self.lonlat(ex, ey)
        clon = float(self.lonlat(0.5 * (xa + xb), 0.5 * (ya + yb))[0])
        lon = clon + (lon - clon + 180.0) % 360.0 - 180.0
        lo, hi = float(lon.min()), float(lon.max())
        la, lb = float(lat.min()), float(lat.max())
        for pole in (90.0, -90.0):
            px, py = self.xy(0.0, pole)
            if np.isfinite(px) and xa <= px <= xb and ya <= py <= yb:
                lo, hi = -180.0, 180.0
                la, lb = (la, 90.0) if pole > 0 else (-90.0, lb)
        return lo, hi, la, lb

    def lines(self, kind, xlim=None, ylim=None):
        """Boundary lines of one layer (KINDS) over the x, y box (km; default the grid
        and a few grid spacings round it): x, y float32 (km), lines separated by NaN,
        each running a point past the box so it reaches the edge.  Cached."""
        if xlim is None or ylim is None:
            x0, x1, y0, y1 = self.limits
            pad = 3.0 * (self.spacing or 0.01 * max(x1 - x0, y1 - y0))
            xlim, ylim = (x0 - pad, x1 + pad), (y0 - pad, y1 + pad)
        key = (kind, tuple(map(float, xlim)), tuple(map(float, ylim)))
        with self._lock:
            if key in self._lines:
                return self._lines[key]
        out = self._clip(kind, xlim, ylim)
        with self._lock:
            self._lines[key] = out
        return out

    def _clip(self, kind, xlim, ylim):
        n, bb, q, start = _layer(kind)
        lo, hi, la, lb = self.box(xlim, ylim)
        pick = np.zeros(len(n), bool)
        for shift in (-360.0, 0.0, 360.0):
            pick |= ((bb[:, 0] + shift <= hi) & (bb[:, 2] + shift >= lo)
                     & (bb[:, 1] <= lb) & (bb[:, 3] >= la))
        ids = np.flatnonzero(pick)
        empty = (np.zeros(0, np.float32), np.zeros(0, np.float32))
        if not len(ids):
            return empty
        idx = np.concatenate([np.arange(start[i], start[i] + n[i]) for i in ids])
        line = np.repeat(np.arange(len(ids)), n[ids])
        x, y = self.xy(q[0, idx] / Q, q[1, idx] / Q)
        inside = ((x >= xlim[0]) & (x <= xlim[1]) & (y >= ylim[0]) & (y <= ylim[1])
                  & np.isfinite(x) & np.isfinite(y))
        same_next = np.zeros(len(idx), bool)
        same_next[:-1] = line[1:] == line[:-1]
        keep = inside.copy()
        keep[1:] |= inside[:-1] & same_next[:-1]  # the point after an inside one
        keep[:-1] |= inside[1:] & same_next[:-1]  # and the one before
        keep &= np.isfinite(x) & np.isfinite(y)
        k = np.flatnonzero(keep)
        if len(k) < 2:
            return empty
        # a break wherever kept points are not neighbours on the same line
        brk = (np.diff(k) != 1) | (line[k[1:]] != line[k[:-1]])
        m = len(k) + int(brk.sum())
        pos = np.arange(len(k)) + np.concatenate([[0], np.cumsum(brk)])
        ox = np.full(m, np.nan, np.float32)
        oy = np.full(m, np.nan, np.float32)
        ox[pos], oy[pos] = x[k], y[k]
        return _drop_single(ox, oy)


def _drop_single(x, y):
    """Drop lone points (a 'line' of one point between NaNs)."""
    ok = np.isfinite(x)
    prev = np.concatenate([[False], ok[:-1]])
    nxt = np.concatenate([ok[1:], [False]])
    lone = ok & ~prev & ~nxt
    if lone.any():
        keep = ~lone
        x, y = x[keep], y[keep]
        # collapse repeated NaNs left behind
        nan = ~np.isfinite(x)
        dup = nan & np.concatenate([[False], nan[:-1]])
        x, y = x[~dup], y[~dup]
    return x, y


def clip(x, y, xlim, ylim):
    """NaN-separated lines x, y cut to the x, y box: the points inside it and their
    neighbours on the same line (so the lines reach its edges); float32."""
    x, y = np.asarray(x, np.float32), np.asarray(y, np.float32)
    if not len(x):
        return x, y
    ok = np.isfinite(x) & np.isfinite(y)
    inside = ok & (x >= xlim[0]) & (x <= xlim[1]) & (y >= ylim[0]) & (y <= ylim[1])
    keep = inside.copy()
    keep[1:] |= inside[:-1] & ok[1:]
    keep[:-1] |= inside[1:] & ok[:-1]
    k = np.flatnonzero(keep)
    if len(k) < 2:
        return np.zeros(0, np.float32), np.zeros(0, np.float32)
    brk = np.diff(k) != 1  # (a gap: a new line)
    m = len(k) + int(brk.sum())
    pos = np.arange(len(k)) + np.concatenate([[0], np.cumsum(brk)])
    ox = np.full(m, np.nan, np.float32)
    oy = np.full(m, np.nan, np.float32)
    ox[pos], oy[pos] = x[k], y[k]
    return _drop_single(ox, oy)


# lat/lon line spacings (degrees) the graticule picks from (Auto) or offers
STEPS = (0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0)


def auto_step(lo, hi, la, lb, lines=4):
    """The spacing giving about `lines` lat (or lon) lines across the box."""
    span = max(min(hi - lo, 360.0), lb - la, 1e-6)
    for s in STEPS:
        if span / s <= lines + 1:
            return s
    return STEPS[-1]


def _fmt(v, step, pos, neg):
    """A lat / lon label: 33.5° N, 97° W (decimals as the step needs)."""
    nd = 0 if step >= 1 else (1 if round(step * 10, 6) == int(round(step * 10)) else 2)
    a = abs(v)
    num = f"{a:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{a:.0f}"
    return f"{num}°" + ("" if a < 0.5 * 10 ** -nd else f" {pos if v > 0 else neg}")


def _graticule(geo, step, xlim, ylim):
    """Lat/lon lines over the x, y box (km): x, y float32 NaN-separated, and their
    labels where they cross the box's bottom (meridians) and left (parallels) edges:
    list of (x, y, text, edge)."""
    lo, hi, la, lb = geo.box(xlim, ylim)
    step = step or auto_step(lo, hi, la, lb)
    xs, ys, labels = [], [], []
    (xa, xb), (ya, yb) = xlim, ylim
    pad = 0.02 * max(xb - xa, yb - ya)

    def add(lon, lat, text, edge):
        x, y = geo.xy(lon, lat)
        x, y = np.asarray(x, np.float64), np.asarray(y, np.float64)
        inside = (x >= xa - pad) & (x <= xb + pad) & (y >= ya - pad) & (y <= yb + pad)
        if not inside.any():
            return
        x, y = np.where(inside, x, np.nan), np.where(inside, y, np.nan)
        xs.extend([x, [np.nan]])
        ys.extend([y, [np.nan]])
        # where the line crosses the edge the label sits on
        c = x - xa if edge == "left" else y - ya
        s = np.flatnonzero(np.isfinite(c[:-1]) & np.isfinite(c[1:]) & (np.sign(c[:-1])
                                                                       != np.sign(c[1:])))
        if len(s):
            i = s[0]
            f = c[i] / (c[i] - c[i + 1])
            px, py = x[i] + f * (x[i + 1] - x[i]), y[i] + f * (y[i + 1] - y[i])
            if (edge == "left" and ya <= py <= yb) or (edge == "bottom" and xa <= px <= xb):
                labels.append((float(px), float(py), text, edge))

    n = 181
    for lon in np.arange(np.ceil(lo / step) * step, hi + 1e-9, step):
        wrapped = (lon + 180.0) % 360.0 - 180.0
        add(np.full(n, lon), np.linspace(la, lb, n), _fmt(wrapped, step, "E", "W"), "bottom")
    for lat in np.arange(np.ceil(la / step) * step, lb + 1e-9, step):
        if abs(lat) >= 90.0:
            continue
        add(np.linspace(lo, hi, n), np.full(n, lat), _fmt(lat, step, "N", "S"), "left")
    if not xs:
        return np.zeros(0, np.float32), np.zeros(0, np.float32), [], step
    return (np.concatenate(xs).astype(np.float32), np.concatenate(ys).astype(np.float32),
            labels, step)


def graticule(geo, step=None, xlim=None, ylim=None):
    """Lat/lon lines of a Geo every `step` degrees (None: auto_step) over the x, y
    box (default its grid): (x, y, labels, step), see _graticule."""
    if xlim is None or ylim is None:
        x0, x1, y0, y1 = geo.limits
        xlim, ylim = (x0, x1), (y0, y1)
    return _graticule(geo, step, tuple(map(float, xlim)), tuple(map(float, ylim)))


def lonlat_table(geo, xlim, ylim, n=33):
    """lon, lat on an n x n grid over the x, y box (for the browser's hover, read
    off by bilinear interpolation): dict(x0, x1, y0, y1, n, lon, lat) lists, lon
    unwrapped about the box's centre."""
    xs, ys = np.linspace(xlim[0], xlim[1], n), np.linspace(ylim[0], ylim[1], n)
    X, Y = np.meshgrid(xs, ys)
    lon, lat = geo.lonlat(X, Y)
    c = float(lon[n // 2, n // 2])
    lon = c + (lon - c + 180.0) % 360.0 - 180.0
    return dict(x0=float(xlim[0]), x1=float(xlim[1]), y0=float(ylim[0]), y1=float(ylim[1]),
                n=n, lon=[round(float(v), 5) for v in lon.ravel()],
                lat=[round(float(v), 5) for v in lat.ravel()])
