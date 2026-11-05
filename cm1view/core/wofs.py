"""WoFS output: one ensemble member of a DART-cycled WRF run.

A WoFS run folder (the "root") holds one folder per cycle, named YYYYMMDDHHMM, each
with one WRF file per member, wrfout_d01_<YYYY-MM-DD_HH:MM:SS>_<member>.  Everything
else in those folders (DART output, wrfinput, obs_seq, logs) is ignored.

A run in cm1view is one member: its path is <root>/memNN, a folder that does not
exist on disk (models.WoFS knows it), so everything keyed by a run's path (the 3D
cache, saved figures, exports, ?run=) tells the members apart.

Fields are renamed to cm1view's (CM1) names where there is one: T+300 -> th,
P+PB -> prs, QVAPOR... -> qv..., REFL_10CM -> dbz, U/V/W -> uinterp/vinterp/winterp
(averaged onto mass points on read, like CM1's staggered fields).  Every other 2D or
3D field on the mass or a staggered grid keeps its WRF name.  The base state
(th0, prs0, qv0, u0, v0) is the member's own 3D field at its first time, so a
perturbation is the change since then.  Winds are grid-relative.

Heights: the levels follow the terrain (Run.terrain), so every column has its own,
changing with time: the fields zmsl and zagl (m above sea level / ground, at mass
levels) are (PH+PHB)/g and that minus HGT, and heights(t, ref) gives them in km for
the whole grid (at the w levels too).  Maps at a height interpolate column by column
(Run.interp_height).  z and zf are one provisional profile for what still takes one:
the domain-mean height above ground of the levels at the first time."""

import datetime
import os
import re

import netCDF4
import numpy as np

from .run import IO_LOCK, Run, VarInfo

G = 9.81  # m/s^2, as WRF

CYCLE_RE = re.compile(r"^\d{12}$")
FILE_RE = re.compile(r"^wrfout_d01_(\d{4}-\d\d-\d\d_\d\d:\d\d:\d\d)_(\d+)$")
MEMBER_RE = re.compile(r"^mem0*(\d+)$")

# cm1view name -> (WRF fields summed, constant added)
MAPPED = {
    "th": (("T",), 300.0),
    "prs": (("P", "PB"), 0.0),
    "qv": (("QVAPOR",), 0.0),
    "qc": (("QCLOUD",), 0.0),
    "qr": (("QRAIN",), 0.0),
    "qi": (("QICE",), 0.0),
    "qs": (("QSNOW",), 0.0),
    "qg": (("QGRAUP",), 0.0),
    "qhl": (("QHAIL",), 0.0),
    "dbz": (("REFL_10CM",), 0.0),
    "uinterp": (("U",), 0.0),
    "vinterp": (("V",), 0.0),
    "winterp": (("W",), 0.0),
}
LABELS = {"th": ("potential temperature", "K"), "prs": ("pressure", "Pa"),
          "qv": ("water vapor mixing ratio", "kg/kg"),
          "uinterp": ("u (grid-relative)", "m/s"), "vinterp": ("v (grid-relative)", "m/s")}
# base state: the member's own field at its first time
BASE = {"th0": "th", "prs0": "prs", "qv0": "qv", "u0": "uinterp", "v0": "vinterp"}
USED = {w for srcs, _ in MAPPED.values() for w in srcs}
# heights of the levels (m), from the geopotential: name -> (above, label)
HEIGHTS = {"zmsl": ("msl", "height above sea level"), "zagl": ("agl", "height above ground")}

# WRF dimensions: (stagger or None) per dimension
_ZDIMS = {"bottom_top": None, "bottom_top_stag": "z"}
_YDIMS = {"south_north": None, "south_north_stag": "y"}
_XDIMS = {"west_east": None, "west_east_stag": "x"}


def member_path(root, m):
    return os.path.join(os.path.abspath(root), f"mem{int(m):02d}")


def member_of(path):
    """(root, member) of a member path <root>/memNN, or None."""
    m = MEMBER_RE.match(os.path.basename(os.path.abspath(path).rstrip("/")))
    return (os.path.dirname(os.path.abspath(path).rstrip("/")), int(m.group(1))) if m \
        else None


def _ok_dir(entry):
    try:
        return entry.is_dir()
    except OSError:
        return False


def cycles(root, entries=None):
    """Cycle folder names under root, oldest first."""
    try:
        ents = entries if entries is not None else list(os.scandir(root))
    except OSError:
        return []
    return sorted(e.name for e in ents if CYCLE_RE.match(e.name) and _ok_dir(e))


def _files_in(folder):
    """{member: file name} of the member files in one cycle folder."""
    try:
        names = [e.name for e in os.scandir(folder)]
    except OSError:
        return {}
    out = {}
    for n in names:
        m = FILE_RE.match(n)
        if m:
            out[int(m.group(2))] = n
    return out


def members(root, entries=None):
    """Member numbers of a WoFS root, from its first cycle folder ([]: not a WoFS run)."""
    cs = cycles(root, entries)
    return sorted(_files_in(os.path.join(root, cs[0]))) if cs else []


def is_root(path, entries=None):
    return bool(path) and os.path.isdir(path) and bool(members(path, entries))


def is_member(path):
    """A member path <root>/memNN of a WoFS root holding that member (no such folder
    on disk)."""
    rm = member_of(path) if path else None
    return (rm is not None and not os.path.isdir(path) and os.path.isdir(rm[0])
            and rm[1] in members(rm[0]))


def _when(s):
    return datetime.datetime.strptime(s, "%Y-%m-%d_%H:%M:%S").replace(
        tzinfo=datetime.timezone.utc)


def member_files(root, m):
    """[(valid time, file path)] of member m, one per cycle folder holding its file."""
    out = []
    for c in cycles(root):
        folder = os.path.join(root, c)
        name = (f"wrfout_d01_{c[:4]}-{c[4:6]}-{c[6:8]}_{c[8:10]}:{c[10:12]}:00_{m}")
        if not os.path.isfile(os.path.join(folder, name)):
            name = _files_in(folder).get(m)  # (a file not at the cycle's own time)
            if name is None:
                continue
        out.append((_when(FILE_RE.match(name).group(1)), os.path.join(folder, name)))
    return out


def count(path):
    rm = member_of(path) if path else None
    if rm is None or os.path.isdir(path) or not os.path.isdir(rm[0]):
        return 0
    return len(member_files(*rm))


# ------------------------------------------------------------------ reading
def _open_nc(path):
    d = netCDF4.Dataset(path)
    d.set_auto_mask(False)
    return d


def _stag(dims):
    """Stagger of a (Time, ...) WRF field on cm1view's grid: (ndim, stag) or None."""
    if not dims or dims[0] != "Time":
        return None
    rest = dims[1:]
    if len(rest) == 2 and rest == ("south_north", "west_east"):
        return 2, None
    if len(rest) != 3 or rest[0] not in _ZDIMS or rest[1] not in _YDIMS \
            or rest[2] not in _XDIMS:
        return None
    st = [s for s in (_ZDIMS[rest[0]], _YDIMS[rest[1]], _XDIMS[rest[2]]) if s]
    return (3, st[0] if st else None) if len(st) <= 1 else None


class _Sum:
    """WRF fields summed (+ a constant), indexed like a netCDF variable."""

    def __init__(self, vs, add):
        self.vs, self.add = vs, add

    def __getitem__(self, key):
        a = np.asarray(self.vs[0][key], dtype=np.float32)
        for v in self.vs[1:]:
            a = a + np.asarray(v[key], dtype=np.float32)
        return a + np.float32(self.add) if self.add else a


class _Height:
    """(PH+PHB)/g (m), less the ground's height HGT with `hgt`, indexed like a
    netCDF variable (Time, bottom_top_stag, south_north, west_east)."""

    def __init__(self, ph, phb, hgt=None):
        self.ph, self.phb, self.hgt = ph, phb, hgt

    def __getitem__(self, key):
        key = key if isinstance(key, tuple) else (key,)
        a = (np.asarray(self.ph[key], np.float32) + np.asarray(self.phb[key], np.float32)) \
            / np.float32(G)
        if self.hgt is None:
            return a
        # (the ground under the same columns: broadcast over the levels, if any)
        return a - np.asarray(self.hgt[(key[0],) + key[2:]], np.float32)


class WRFView:
    """One member's file at one time, seen with cm1view's names (and its first time's
    file for the base state): d.variables, d[name][0, ...], a context manager."""

    def __init__(self, path, path0):
        self._d, self._path0, self._d0 = _open_nc(path), path0, None
        self.variables = table(self._d.variables)

    def _first(self):
        if self._path0 == self._d.filepath():
            return self._d
        if self._d0 is None:
            self._d0 = _open_nc(self._path0)
        return self._d0

    def __getitem__(self, name):
        kind, what = self.variables[name]
        if kind == "wrf":
            return self._d[what]
        if kind == "height":
            d = self._d
            return _Height(d["PH"], d["PHB"], d["HGT"] if what == "agl" else None)
        d = self._first() if kind == "base" else self._d
        srcs, add = MAPPED[what]
        return _Sum([d[s] for s in srcs], add)

    def close(self):
        for d in (self._d, self._d0):
            if d is not None and d.isopen():
                d.close()
        self._d0 = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class WRFSource:
    """Picklable: what reader processes open for one time (core.run.open_source)."""

    def __init__(self, path, path0):
        self.path, self.path0 = path, path0

    def open(self):
        return WRFView(self.path, self.path0)


def table(wrfvars):
    """{cm1view name: (kind, what)} of a WRF file's variables: kind "mapped" (what: a
    MAPPED name), "base" (what: the MAPPED name read at the first time), "height"
    (what: "msl" or "agl", HEIGHTS) or "wrf" (what: the WRF name)."""
    out = {}
    for n, (srcs, _) in MAPPED.items():
        if all(s in wrfvars for s in srcs):
            out[n] = ("mapped", n)
    for n, of in BASE.items():
        if of in out:
            out[n] = ("base", of)
    if all(s in wrfvars for s in ("PH", "PHB", "HGT")):
        for n, (ref, _) in HEIGHTS.items():
            out[n] = ("height", ref)
    for n, v in wrfvars.items():
        if n not in USED and n not in out and _stag(v.dimensions):
            out[n] = ("wrf", n)
    return out


class WoFSRun(Run):
    """One member of a WoFS run (see the module docstring).  `path` is <root>/memNN,
    or the root itself (its first member)."""

    model = "wofs"
    model_label = "WoFS"
    terrain = True
    traced_parcels = True  # (WoFS has no parcel output: core.trajcalc)

    def __init__(self, path, cache_gb=12.0, workers=None, cache=None):
        super().__init__(path, cache_gb, workers, cache)
        if is_root(self.path):
            self.root, self.member = self.path, members(self.path)[0]
        else:
            rm = member_of(self.path)
            if rm is None:
                raise FileNotFoundError(f"{self.path} is not a WoFS member (<root>/memNN)")
            self.root, self.member = rm
        self.path = member_path(self.root, self.member)
        self.members = members(self.root)
        found = member_files(self.root, self.member)
        if not found:
            raise FileNotFoundError(f"no wrfout_d01_*_{self.member} files under {self.root}")
        self.valid = [w for w, _ in found]  # valid times (UTC)
        self.files = [f for _, f in found]
        self.times = np.array([(w - self.valid[0]).total_seconds() for w in self.valid],
                              dtype=np.float64)

        with IO_LOCK, netCDF4.Dataset(self.files[0]) as d:
            d.set_auto_mask(False)
            self.attrs = {k: d.getncattr(k) for k in d.ncattrs()}
            names = table(d.variables)
            self.vars = {}
            for n, (kind, what) in names.items():
                if kind == "wrf":
                    v = d[what]
                    long_name = getattr(v, "description", what)
                    units = getattr(v, "units", "")
                    ndim, stag = _stag(v.dimensions)
                elif kind == "height":
                    v = d["PH"]
                    long_name, units = HEIGHTS[n][1], "m"
                    ndim, stag = 3, "z"
                else:
                    src = MAPPED[what][0][0]
                    v = d[src]
                    long_name, units = LABELS.get(what, (getattr(v, "description", n),
                                                         getattr(v, "units", "")))
                    if kind == "base":
                        long_name = f"base-state {long_name} (first time)"
                    ndim, stag = _stag(v.dimensions)
                self.vars[n] = VarInfo(n, long_name, units, ndim, stag, 1, dict(v.__dict__))
            ni, nj = len(d.dimensions["west_east"]), len(d.dimensions["south_north"])
            dx, dy = float(d.getncattr("DX")), float(d.getncattr("DY"))
            # provisional heights: domain-mean height AGL of the w levels at t0
            if "PH" in d.variables and "PHB" in d.variables and "HGT" in d.variables:
                hgt = np.asarray(d["HGT"][0], np.float64)
                zw = (np.asarray(d["PH"][0], np.float64) + d["PHB"][0]) / G - hgt
                zf = zw.mean(axis=(1, 2)) / 1000.0
            else:
                raise ValueError(f"{self.files[0]} has no PH, PHB and HGT (heights)")
        # x, y (km) of mass points, origin at the domain centre (as CM1 runs)
        self.xh = (np.arange(ni) - 0.5 * (ni - 1)) * dx / 1000.0
        self.yh = (np.arange(nj) - 0.5 * (nj - 1)) * dy / 1000.0
        self.zf = zf - zf[0]
        self.z = 0.5 * (self.zf[:-1] + self.zf[1:])
        self._hgt = hgt / 1000.0  # ground height (km MSL); WRF's HGT does not change
        self._grid_done()

    def terrain_height(self):
        return self._hgt

    def heights(self, t, ref="agl", w=False):
        """Heights (km) of the levels at time t, (nk, nj, ni), from the geopotential:
        at mass levels the cached zagl / zmsl volume, at the w levels (w) read from
        the file each time ((nk + 1, nj, ni))."""
        if not w:
            return self.volume("zmsl" if ref == "msl" else "zagl", t) / np.float32(1000.0)
        self._check("PH", t)
        with IO_LOCK:
            d = self._ds(t)
            z = (np.asarray(d["PH"][0], np.float32) + d["PHB"][0]) / np.float32(G * 1000.0)
        return z if ref == "msl" else z - self._hgt.astype(np.float32)

    def source(self, t):
        return WRFSource(self.files[t], self.files[0])

    def time_label(self, t):
        w = self.valid[t]
        return f"{w:%H:%M:%S} UTC" if w.second else f"{w:%H:%M} UTC"
