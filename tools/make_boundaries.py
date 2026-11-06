"""Build cm1view/data/boundaries.npz, the map boundary lines cm1view ships (core.geo).

Run once by a maintainer when the source data changes; cm1view itself never downloads
anything.  Needs pyshp (`import shapefile`) besides numpy:

    python tools/make_boundaries.py SRC_DIR

SRC_DIR holds these shapefiles, unzipped, each in a folder named like its zip (all
public domain):

  US Census cartographic boundary files, 1:5,000,000 (www.census.gov/geographies/
  mapping-files/time-series/geo/cartographic-boundary.html)
    cb_2023_us_county_5m       https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_5m.zip
    cb_2023_us_state_5m        https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_5m.zip
  Natural Earth, 1:10m (www.naturalearthdata.com)
    ne_10m_coastline                       https://naciscdn.org/naturalearth/10m/physical/ne_10m_coastline.zip
    ne_10m_lakes                           https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip
    ne_10m_admin_0_boundary_lines_land     https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_boundary_lines_land.zip
    ne_10m_admin_1_states_provinces_lines  https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces_lines.zip

Layers (core.geo.KINDS):
  coastlines  Natural Earth coastline
  countries   Natural Earth land borders between countries
  states      US: borders shared by two Census states; elsewhere Natural Earth
              first-level (state/province) borders
  lakes       Natural Earth lake shores
  counties    US only: borders shared by two Census counties

For polygon sources (Census states and counties) only edges shared by two polygons are
kept, so coasts and country borders are not drawn a second time by those layers.

File format, per layer K: K_n (int32) points per polyline, K_bb (float32, n x 4) each
polyline's lon0, lat0, lon1, lat1, and K_d (int32, 2 x N) the points' lon and lat
in units of 1e-4 degree (about 10 m, well below the sources' detail), delta-encoded
over the whole layer: np.cumsum(K_d, axis=1) gives the lon, lat of every point,
polylines one after another.  About 5 MB in all, most of it the world's coasts and
provinces (simplifying the lines saves little: the sources are already lean).
"""

import os
import sys

import numpy as np
import shapefile

Q = 1e4  # quantisation: points per degree
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cm1view", "data",
                   "boundaries.npz")


def rings(shp, keep=lambda rec: True):
    """Each part of each shape (whose record passes keep) as quantised int64 (n, 2)."""
    r = shapefile.Reader(shp)
    for sr in r.iterShapeRecords():
        if not keep(sr.record):
            continue
        s = sr.shape
        pts = np.asarray(s.points, np.float64)
        bounds = list(s.parts) + [len(pts)]
        for a, b in zip(bounds[:-1], bounds[1:]):
            q = np.round(pts[a:b] * Q).astype(np.int64)
            if len(q) >= 2:
                yield q


def dedupe(q):
    """Drop repeated consecutive points."""
    if len(q) < 2:
        return q
    ok = np.ones(len(q), bool)
    ok[1:] = np.any(q[1:] != q[:-1], axis=1)
    return q[ok]


def shared_edges(polys):
    """Polylines of the edges that two of the rings share (each drawn once)."""
    polys = [dedupe(p) for p in polys]
    polys = [p for p in polys if len(p) >= 2]

    def key(a, b):
        ka, kb = (int(a[0]), int(a[1])), (int(b[0]), int(b[1]))
        return (ka, kb) if ka <= kb else (kb, ka)

    count = {}
    for p in polys:
        for a, b in zip(p[:-1], p[1:]):
            k = key(a, b)
            count[k] = count.get(k, 0) + 1
    seen = set()
    out = []
    for p in polys:
        run = []
        for a, b in zip(p[:-1], p[1:]):
            k = key(a, b)
            if count[k] >= 2 and k not in seen:
                seen.add(k)
                if not run:
                    run = [a]
                run.append(b)
            elif run:
                out.append(np.array(run))
                run = []
        if run:
            out.append(np.array(run))
    return join_ends(out)


def join_ends(lines):
    """Join polylines where one ends exactly where the next (in order) starts."""
    out = []
    for p in lines:
        if out and np.array_equal(out[-1][-1], p[0]):
            out[-1] = np.vstack([out[-1], p[1:]])
        else:
            out.append(p)
    return out


def pack(lines):
    lines = [dedupe(p) for p in lines]
    lines = [p for p in lines if len(p) >= 2]
    n = np.array([len(p) for p in lines], np.int32)
    allq = np.vstack(lines)
    d = np.diff(allq, axis=0, prepend=np.zeros((1, 2), np.int64))
    assert np.abs(d).max() < 2**31
    bb = np.array([[p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()]
                   for p in lines], np.float64) / Q
    return n, bb.astype(np.float32), np.ascontiguousarray(d.T, dtype=np.int32)


def main(src):
    def f(name):
        return os.path.join(src, name, name + ".shp")

    layers = {
        "coastlines": list(rings(f("ne_10m_coastline"))),
        "countries": list(rings(f("ne_10m_admin_0_boundary_lines_land"))),
        "states": shared_edges(rings(f("cb_2023_us_state_5m")))
        + list(rings(f("ne_10m_admin_1_states_provinces_lines"),
                     keep=lambda rec: rec["ADM0_A3"] != "USA")),
        "lakes": list(rings(f("ne_10m_lakes"))),
        "counties": shared_edges(rings(f("cb_2023_us_county_5m"))),
    }
    out = {}
    for k, lines in layers.items():
        n, bb, d = pack(lines)
        out[k + "_n"], out[k + "_bb"], out[k + "_d"] = n, bb, d
        print(f"{k:11s} {len(n):6d} lines {int(n.sum()):8d} points")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(OUT, **out)
    print(f"{os.path.normpath(OUT)}: {os.path.getsize(OUT) / 1e6:.2f} MB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
