"""core.geo: a WRF grid's projection and the boundary lines cm1view ships."""
import os

import numpy as np
import pytest

from cm1view.core import geo

R = 6370000.0
WOFS = dict(MAP_PROJ=1, TRUELAT1=30.0, TRUELAT2=60.0, STAND_LON=-102.75,
            MOAD_CEN_LAT=33.75, CEN_LAT=33.75, CEN_LON=-102.75)


def _lambert(t1, t2, lon0, lat0):
    """Lambert conformal on WRF's sphere from Snyder's formulas (not pyproj): forward
    and inverse in metres."""
    f1, f2, l0 = np.radians(t1), np.radians(t2), np.radians(lon0)
    n = (np.log(np.cos(f1) / np.cos(f2))
         / np.log(np.tan(np.pi / 4 + f2 / 2) / np.tan(np.pi / 4 + f1 / 2)))
    F = np.cos(f1) * np.tan(np.pi / 4 + f1 / 2) ** n / n
    rho0 = R * F / np.tan(np.pi / 4 + np.radians(lat0) / 2) ** n

    def fwd(lon, lat):
        rho = R * F / np.tan(np.pi / 4 + np.radians(lat) / 2) ** n
        th = n * (np.radians(lon) - l0)
        return rho * np.sin(th), rho0 - rho * np.cos(th)

    def inv(x, y):
        rho = np.hypot(x, rho0 - y)
        th = np.arctan2(x, rho0 - y)
        lat = 2 * np.arctan((R * F / rho) ** (1 / n)) - np.pi / 2
        return np.degrees(th / n + l0), np.degrees(lat)

    return fwd, inv


def _grid(ni=199, nj=199, dx=1.0):
    xh = (np.arange(ni) - 0.5 * (ni - 1)) * dx
    yh = (np.arange(nj) - 0.5 * (nj - 1)) * dx
    return xh, yh


def _wofs_latlon(xh, yh, a=WOFS):
    fwd, inv = _lambert(a["TRUELAT1"], a["TRUELAT2"], a["STAND_LON"], a["MOAD_CEN_LAT"])
    cx, cy = fwd(a["CEN_LON"], a["CEN_LAT"])
    X, Y = np.meshgrid(xh, yh)
    lon, lat = inv(cx + X * 1000.0, cy + Y * 1000.0)
    return lat, lon


def test_lambert_grid_matches_its_lat_lon():
    """A WoFS-like grid: the projection places every point where the file's (here
    Snyder's) lat/lon say, x = y = 0 is the domain centre, and lat/lon go both ways."""
    xh, yh = _grid()
    lat, lon = _wofs_latlon(xh, yh)
    g = geo.from_wrf(WOFS, xh, yh, lat, lon)
    assert g is not None and g.misfit < 1e-3  # km
    assert abs(g.x0) < 1e-3 and abs(g.y0) < 1e-3  # (centred on CEN_LAT, CEN_LON)
    lo, la = g.lonlat(0.0, 0.0)
    assert abs(lo + 102.75) < 1e-6 and abs(la - 33.75) < 1e-6
    x, y = g.xy(lon[10, 20], lat[10, 20])
    assert abs(x - xh[20]) < 1e-3 and abs(y - yh[10]) < 1e-3
    # without the file's lat/lon: placed by CEN_LAT, CEN_LON alone, the same
    g2 = geo.from_wrf(WOFS, xh, yh)
    assert abs(g2.x0 - g.x0) < 1e-3 and abs(g2.y0 - g.y0) < 1e-3


def test_wrong_or_unknown_projection_gives_no_geo():
    xh, yh = _grid(41, 41, 3.0)
    lat, lon = _wofs_latlon(xh, yh)
    assert geo.from_wrf(dict(WOFS, STAND_LON=-100.0), xh, yh, lat, lon) is None
    assert geo.from_wrf(dict(WOFS, TRUELAT1=45.0), xh, yh, lat, lon) is None
    assert geo.from_wrf(dict(WOFS, MAP_PROJ=6), xh, yh, lat, lon) is None  # lat-lon grid
    assert geo.from_wrf({}, xh, yh, lat, lon) is None  # e.g. an idealized run
    assert geo.from_wrf(dict(WOFS, MAP_PROJ=2), xh, yh) is not None
    assert geo.from_wrf(dict(WOFS, MAP_PROJ=3), xh, yh) is not None


def test_shipped_layers():
    with np.load(geo.DATA) as z:
        for k in geo.KINDS:
            n, d = z[k + "_n"], z[k + "_d"]
            assert len(n) and d.shape == (2, int(n.sum()))
    assert os.path.getsize(geo.DATA) < 8e6


def test_lines_over_the_texas_panhandle():
    """The real WoFS domain of 2022-05-23: the New Mexico - Texas border (103.04 W) runs
    north-south through the west of it; lines stop at the
    domain (a point past it) and are separated by NaN."""
    xh, yh = _grid()
    lat, lon = _wofs_latlon(xh, yh)
    g = geo.from_wrf(WOFS, xh, yh, lat, lon)
    x, y = g.lines("states")
    ok = np.isfinite(x)
    assert ok.sum() > 10
    lo, la = g.lonlat(x[ok], y[ok])
    border = (la > 33.0) & (la < 34.5)  # (south of the Oklahoma line)
    assert np.all(np.abs(lo[border] + 103.05) < 0.03)
    pad = 3.0 * g.spacing
    inside = (np.abs(x[ok]) <= 99.0 + pad) & (np.abs(y[ok]) <= 99.0 + pad)
    assert inside.mean() > 0.9  # (only the points just past the box are outside)
    xc, yc = g.lines("counties")
    assert np.isfinite(xc).sum() > 50 and np.isnan(xc).sum() > 5  # Texas' county grid
    assert len(g.lines("coastlines")[0]) == 0  # (no sea near Lubbock)
    assert g.lines("states") is g.lines("states")  # cached


def test_lines_round_the_pole_and_across_180():
    """A polar stereographic grid over the North Pole and a Mercator one across 180 E/W
    find their lines (the lon box covers every lon / wraps past 180)."""
    xh, yh = _grid(100, 100, 30.0)
    polar = dict(MAP_PROJ=2, TRUELAT1=60.0, STAND_LON=-100.0, CEN_LAT=89.0, CEN_LON=-100.0)
    g = geo.from_wrf(polar, xh, yh)
    lo, hi, la, lb = g.box((xh[0], xh[-1]), (yh[0], yh[-1]))
    assert (lo, hi, lb) == (-180.0, 180.0, 90.0)
    assert np.isfinite(g.lines("coastlines")[0]).sum() > 100
    merc = dict(MAP_PROJ=3, TRUELAT1=20.0, STAND_LON=180.0, CEN_LAT=-17.5, CEN_LON=178.5)
    g = geo.from_wrf(merc, *_grid(100, 100, 5.0))
    lo, hi, la, lb = g.box((-250.0, 250.0), (-250.0, 250.0))
    assert lo < 180.0 < hi  # (Fiji: unwrapped about 178.5 E)
    x, y = g.lines("coastlines")
    assert np.isfinite(x).sum() > 100
    lon, _ = g.lonlat(x[np.isfinite(x)], y[np.isfinite(y)])
    assert (lon > 0).any() and (lon < 0).any()  # both sides of 180


def test_wofs_run_has_geo_cm1_run_none(tmp_path):
    from cm1view import demo_wofs
    from cm1view.core import models
    root = demo_wofs.make(str(tmp_path))
    run = models.open_run(os.path.join(root, "mem01"), workers=1)
    assert run.geo is not None and run.geo.misfit < 0.01 * run.dx / 1000.0
    mean = models.open_run(os.path.join(root, "mean"), workers=1)
    assert mean.geo is not None
    from cm1view.core.run import Run
    assert Run.geo is None


def _wofs_geo():
    xh, yh = _grid()
    lat, lon = _wofs_latlon(xh, yh)
    return geo.from_wrf(WOFS, xh, yh, lat, lon)


def test_graticule_lines_and_labels():
    """Lat/lon lines over the grid: auto spacing gives a few, each labelled where it
    leaves the bottom (meridians) or left (parallels) edge, at the right lon / lat."""
    g = _wofs_geo()
    x, y, labels, step = geo.graticule(g)
    assert step == 0.5 and np.isnan(x).any() and np.isfinite(x).sum() > 100
    bottom = [lab for lab in labels if lab[3] == "bottom"]
    left = [lab for lab in labels if lab[3] == "left"]
    assert 2 <= len(bottom) <= 6 and 2 <= len(left) <= 6
    assert "103° W" in [lab[2] for lab in bottom] and "34° N" in [lab[2] for lab in left]
    for lx, ly, text, edge in labels:
        lon, lat = g.lonlat(lx, ly)
        v = float(lon) if edge == "bottom" else float(lat)
        num = float(text.split("°")[0]) * (-1 if text.endswith(("W", "S")) else 1)
        assert abs(v - num) < 1e-3, (text, v)
        assert (ly == pytest.approx(g.limits[2]) if edge == "bottom"
                else lx == pytest.approx(g.limits[0]))
    fine = geo.graticule(g, 0.25)
    assert fine[3] == 0.25 and "102.75° W" in [lab[2] for lab in fine[2]]
    assert geo.auto_step(-180, 180, -90, 90) == 30.0


def test_hover_table_reads_lat_lon_to_a_few_metres():
    """The browser's lat, lon (bilinear in lonlat_table, as LONLAT_JS) matches the
    projection to ~1e-4 degrees anywhere in the domain."""
    g = _wofs_geo()
    x0, x1, y0, y1 = g.limits
    t = geo.lonlat_table(g, (x0, x1), (y0, y1), n=49)
    n = t["n"]
    lon_t, lat_t = np.reshape(t["lon"], (n, n)), np.reshape(t["lat"], (n, n))
    rng = np.random.default_rng(0)
    px, py = rng.uniform(x0, x1, 200), rng.uniform(y0, y1, 200)
    fx, fy = (px - x0) / (x1 - x0) * (n - 1), (py - y0) / (y1 - y0) * (n - 1)
    i, j = np.minimum(fx.astype(int), n - 2), np.minimum(fy.astype(int), n - 2)
    a, b = fx - i, fy - j

    def bil(v):
        return ((1 - a) * (1 - b) * v[j, i] + a * (1 - b) * v[j, i + 1]
                + (1 - a) * b * v[j + 1, i] + a * b * v[j + 1, i + 1])

    lon, lat = g.lonlat(px, py)
    assert np.max(np.abs(bil(lon_t) - lon)) < 1e-4
    assert np.max(np.abs(bil(lat_t) - lat)) < 1e-4
