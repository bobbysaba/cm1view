"""WoFS output: one ensemble member of a DART-cycled WRF experiment.

A WoFS experiment folder (the "root"; its name is the run's name) holds one folder per
date, YYYYMMDD, each holding one folder per cycle, YYYYMMDDHHMM, each with one WRF
file per member, wrfout_d01_<YYYY-MM-DD_HH:MM:SS>_<member>.  A run that cycles across
00 UTC has two date folders; their cycles are joined into one timeline.  Cycle
folders straight in the root are read too (a date folder picked as the root).
Everything else (DART output, wrfinput, obs_seq, logs, FCST/, postpr/, summary/) is
ignored.

The experiment is one run in the picker; a member is chosen inside it.  Under the
hood each member is a run of its own with the path <root>/memNN, a folder that does
not exist on disk (models.WoFS knows it), so everything keyed by a run's path (the 3D
cache, saved figures, exports, ?run=) tells the members apart.  <root>/mean is the
ensemble mean (WoFSMeanRun, below).  Opening the root opens the member the
wofs_member setting names (default 1).

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
from collections import OrderedDict

import netCDF4
import numpy as np

from . import geo
from .run import (IO_LOCK, Run, VarInfo, _drop_pending, _read_volume_worker,
                  check_cancelled, report)

G = 9.81  # m/s^2, as WRF

CYCLE_RE = re.compile(r"^\d{12}$")
DATE_RE = re.compile(r"^\d{8}$")
FILE_RE = re.compile(r"^wrfout_d01_(\d{4}-\d\d-\d\d_\d\d:\d\d:\d\d)_(\d+)$")
MEMBER_RE = re.compile(r"^mem0*(\d+)$")
MEAN = "mean"  # <root>/mean: the ensemble mean run

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


def mean_path(root):
    return os.path.join(os.path.abspath(root), MEAN)


def mean_of(path):
    """The root of a mean path <root>/mean, or None."""
    p = os.path.abspath(path).rstrip("/")
    return os.path.dirname(p) if os.path.basename(p) == MEAN else None


def _ok_dir(entry):
    try:
        return entry.is_dir()
    except OSError:
        return False


def _cycle_names(ents):
    return sorted(e.name for e in ents if CYCLE_RE.match(e.name) and _ok_dir(e))


def _date_dirs(ents):
    return sorted(e.name for e in ents if DATE_RE.match(e.name) and _ok_dir(e))


def _scan(folder):
    try:
        return list(os.scandir(folder))
    except OSError:
        return []


def cycles(root, entries=None, first=False):
    """Cycle folders of a root, oldest first, as paths relative to it: YYYYMMDDHHMM
    straight in the root, and YYYYMMDD/YYYYMMDDHHMM in its date folders (joined into
    one timeline).  first: stop at the first folder holding any (no more listings)."""
    ents = entries if entries is not None else _scan(root)
    out = _cycle_names(ents)
    if first and out:
        return out[:1]
    for d in _date_dirs(ents):
        cs = _cycle_names(_scan(os.path.join(root, d)))
        out += [os.path.join(d, c) for c in cs]
        if first and out:
            break
    return sorted(out, key=os.path.basename)


def default_member(ms):
    """The member the wofs_member setting names, of members ms (else the first); None:
    the mean."""
    from .. import config
    want = str(config.get("wofs_member")).strip().lower()
    if want == MEAN and len(ms) > 1:
        return None
    try:
        m = int(want.removeprefix("mem"))
    except ValueError:
        m = None
    return m if m in ms else (ms[0] if ms else None)


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
    cs = cycles(root, entries, first=True)
    return sorted(_files_in(os.path.join(root, cs[0]))) if cs else []


def is_root(path, entries=None):
    return bool(path) and os.path.isdir(path) and bool(members(path, entries))


def is_member(path):
    """A member path <root>/memNN of a WoFS root holding that member (no such folder
    on disk)."""
    rm = member_of(path) if path else None
    return (rm is not None and not os.path.isdir(path) and os.path.isdir(rm[0])
            and rm[1] in members(rm[0]))


def is_mean(path):
    """The mean path <root>/mean of a WoFS root (no such folder on disk)."""
    root = mean_of(path) if path else None
    return root is not None and not os.path.isdir(path) and is_root(root)


def _when(s):
    return datetime.datetime.strptime(s, "%Y-%m-%d_%H:%M:%S").replace(
        tzinfo=datetime.timezone.utc)


def member_files(root, m):
    """[(valid time, file path)] of member m, one per cycle folder holding its file."""
    out = []
    for c in cycles(root):
        folder = os.path.join(root, c)
        b = os.path.basename(c)
        name = (f"wrfout_d01_{b[:4]}-{b[4:6]}-{b[6:8]}_{b[8:10]}:{b[10:12]}:00_{m}")
        if not os.path.isfile(os.path.join(folder, name)):
            name = _files_in(folder).get(m)  # (a file not at the cycle's own time)
            if name is None:
                continue
        out.append((_when(FILE_RE.match(name).group(1)), os.path.join(folder, name)))
    return out


def mean_files(root):
    """[(valid time, {member: file path})] of every cycle folder holding member files:
    what the mean averages at each time (one listing per cycle folder)."""
    out = []
    for c in cycles(root):
        folder = os.path.join(root, c)
        found = _files_in(folder)
        if found:
            when = _when(FILE_RE.match(found[min(found)]).group(1))
            out.append((when, {m: os.path.join(folder, n) for m, n in sorted(found.items())}))
    return out


def count(path):
    """Output times of a member or mean path, or of a root (its cycle folders)."""
    if not path:
        return 0
    if os.path.isdir(path):
        return len(cycles(path)) if is_root(path) else 0
    root = mean_of(path)
    if root is not None:
        return len(mean_files(root)) if os.path.isdir(root) else 0
    rm = member_of(path)
    if rm is None or not os.path.isdir(rm[0]):
        return 0
    return len(member_files(*rm))


def run_paths(root, entries=None):
    """Every run of a root: its members' paths, then the mean's (more than one member)."""
    ms = members(root, entries)
    return [member_path(root, m) for m in ms] + [mean_path(root)] * (len(ms) > 1)


def open_path(root):
    """The run to open for a root: the wofs_member setting's member (or the mean)."""
    ms = members(root)
    if not ms:
        return root
    m = default_member(ms)
    return mean_path(root) if m is None else member_path(root, m)


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


class _Mean:
    """The same field of several members, indexed like a netCDF variable: the mean of
    their values (summed in float64)."""

    def __init__(self, vs, name=""):
        self.vs, self.name = vs, name

    def __getitem__(self, key):
        n = len(self.vs)
        acc = np.array(self.vs[0][key], dtype=np.float64)
        for i, v in enumerate(self.vs[1:], 1):  # (read on this thread: tell, may stop)
            report(0, 1, f"{self.name} · {i}/{n} members")
            check_cancelled()
            acc += np.asarray(v[key], dtype=np.float64)
        return (acc / len(self.vs)).astype(np.float32)


class WRFMeanView:
    """Several members' files at one time, seen as one: d[name][...] is the member mean
    of what each member's WRFView gives (base-state fields: of each member's first
    time).  The files are opened on the first read of a field."""

    def __init__(self, pairs):
        self._pairs, self._views = list(pairs), None
        with _open_nc(self._pairs[0][0]) as d:
            self.variables = table(d.variables)

    def __getitem__(self, name):
        if name not in self.variables:
            raise KeyError(name)
        if self._views is None:
            self._views = []
            try:
                for path, path0 in self._pairs:
                    self._views.append(WRFView(path, path0))
            except BaseException:
                self.close()
                raise
        return _Mean([v[name] for v in self._views], name)

    def close(self):
        for v in self._views or ():
            v.close()
        self._views = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class WRFMeanSource:
    """Picklable: what reader processes open for the mean of several members at one
    time, [(file, the member's first-time file)]."""

    def __init__(self, pairs):
        self.pairs = list(pairs)

    def open(self):
        return WRFMeanView(self.pairs)

    def split(self, n):
        """At most n sources of about equal shares of the members (in order)."""
        n = max(1, min(int(n), len(self.pairs)))
        cuts = [round(i * len(self.pairs) / n) for i in range(n + 1)]
        return [WRFMeanSource(self.pairs[a:b]) for a, b in zip(cuts, cuts[1:])]


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
    storm_relative = False  # (how to get the storm motion is still to be decided)
    # every cycle is a fresh DART analysis, so tracked fixes jump by its increments:
    # storm motion is fitted over 30 min of track (core.track.motion)
    track_window = 1800.0

    def __init__(self, path, cache_gb=12.0, workers=None, cache=None):
        super().__init__(path, cache_gb, workers, cache)
        found = self._locate()
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
            lat = lon = None
            if "XLAT" in d.variables and "XLONG" in d.variables:
                lat = np.asarray(d["XLAT"][0], np.float64)
                lon = np.asarray(d["XLONG"][0], np.float64)
        # x, y (km) of mass points, origin at the domain centre (as CM1 runs)
        self.xh = (np.arange(ni) - 0.5 * (ni - 1)) * dx / 1000.0
        self.yh = (np.arange(nj) - 0.5 * (nj - 1)) * dy / 1000.0
        self.zf = zf - zf[0]
        self.z = 0.5 * (self.zf[:-1] + self.zf[1:])
        self._hgt = hgt / 1000.0  # ground height (km MSL); WRF's HGT does not change
        self._grid_done()
        # the grid on the Earth (None if its projection is not one cm1view knows or does
        # not match the file's XLAT, XLONG)
        self.geo = geo.from_wrf(self.attrs, self.xh, self.yh, lat, lon)

    def _locate(self):
        """Set root, member, members and path (<root>/memNN); [(valid time, file)]."""
        if is_root(self.path):
            ms = members(self.path)
            self.root, self.member = self.path, (default_member(ms) or ms[0])
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
        return found

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


MEAN_NOTE = ("Ensemble mean of {n} members. Fields in the files (winds, potential "
             "temperature, pressure, moisture, heights, reflectivity, WRF's 2D fields) "
             "are the member mean at each time; fields cm1view computes (CAPE, updraft "
             "helicity, vorticity, ...) are computed from that mean state. Base state: "
             "the mean at the first time. Trajectories follow the mean winds.")


class WoFSMeanRun(WoFSRun):
    """The ensemble mean of a WoFS run: path <root>/mean.  At each time (cycle folder)
    every field in the files is the mean over the members with a file there; the base
    state is the mean of the members' first-time fields, so a perturbation is the
    mean's change since then.  Fields cm1view derives (core.fields) are computed from
    the mean state, not averaged member by member; reflectivity (REFL_10CM) and WRF's
    2D diagnostics are member means of the values in the files.  Traced trajectories
    follow the mean winds.  The provisional 1D z is the first member's.

    Reading: a 3D field at one time is averaged in the reader processes, each reading
    its share of the members (Run._read_into_cache), and kept in the 3D cache like any
    volume; single levels come from that cached volume.  Other reads (2D fields, column
    boxes, series) open every member's file through a WRFMeanSource.

    stat names the statistic: "mean".  A probability-matched mean would be another
    (<root>/pmm): it needs every member's whole field before combining, so it would
    collect per-member volumes (split(len(pairs))) and combine them in _combine
    instead of weighting partial means."""

    stat = MEAN
    open_max = 2  # (each open time holds every member's file)

    def __init__(self, path, cache_gb=12.0, workers=None, cache=None):
        super().__init__(path, cache_gb, workers, cache)
        for v in self.vars.values():  # (levels: from the whole mean volume, cached)
            if v.ndim == 3:
                v.zchunk = 1 << 20
        self._zw = OrderedDict()  # t -> heights (km MSL) of the w levels

    def _locate(self):
        root = mean_of(self.path)
        if root is None or not is_root(root):
            raise FileNotFoundError(f"{self.path} is not a WoFS ensemble mean (<root>/mean)")
        self.root, self.member = root, None
        self.path = mean_path(root)
        self.members = members(root)
        found = mean_files(root)
        if not found:
            raise FileNotFoundError(f"no wrfout_d01_* member files under {root}")
        first = {}
        for _, fs in found:
            for m, f in fs.items():
                first.setdefault(m, f)
        # per time: (file, that member's first file) of every member there
        self.parts = [[(f, first[m]) for m, f in fs.items()] for _, fs in found]
        self.model_label = f"WoFS ensemble mean ({len(first)} members)"
        self.note = MEAN_NOTE.format(n=len(first))
        return [(w, fs[min(fs)]) for w, fs in found]

    def source(self, t):
        return WRFMeanSource(self.parts[t])

    # ------------------------------------------------------------------ reading
    def _combine(self, parts):
        """The statistic from [(partial mean volume, members in it)]."""
        n = sum(k for _, k in parts)
        acc = np.zeros(parts[0][0].shape, np.float64)
        for a, k in parts:
            acc += a.astype(np.float64) * (k / n)
        return acc.astype(np.float32)

    def _pooled(self, wants, t, done, progress=None, cancelled=None):
        """Mean volumes of [(name, stag)] at time t, read in the reader processes: one
        task per field and share of the members, each a partial mean in shared memory;
        done(name, volume) as each field completes.  False if cancelled."""
        from concurrent.futures import as_completed

        parts = self.source(t).split(self.workers)
        pool = self._get_pool()
        futs = {pool.submit(_read_volume_worker, p, n, stag, self._shm): (n, len(p.pairs))
                for n, stag in wants for p in parts}
        got = {n: [] for n, _ in wants}
        pending, finished = set(futs), 0
        members = sum(len(p.pairs) for p in parts)
        read = 0  # member reads done, over all the fields

        def tell():  # e.g. "th · 18/36 members" (or "th, qv · 40/72 member reads")
            if progress:
                left = [n for n, _ in wants if n in got]
                what = ", ".join(left[:3]) + (", …" if len(left) > 3 else "")
                unit = "members" if len(wants) == 1 else "member reads"
                progress(finished, len(wants),
                         f"{what or wants[-1][0]} · {read}/{members * len(wants)} {unit}")

        tell()
        try:
            for fut in as_completed(futs):
                pending.discard(fut)
                n, k = futs[fut]
                path = fut.result()
                try:
                    got[n].append((np.load(path), k))
                finally:
                    os.remove(path)
                read += k
                if len(got[n]) == len(parts):
                    done(n, self._combine(got.pop(n)))
                    finished += 1
                tell()
                if cancelled and cancelled() and pending:
                    return False
            return True
        finally:
            _drop_pending(pending)  # (cancelled or failed: tidy what the others write)

    def _read_into_cache(self, missing, t, protect, progress, cancelled):
        if self.workers <= 1 or not self._shm:  # (in this process: WRFMeanView)
            return super()._read_into_cache(missing, t, protect, progress, cancelled)
        return self._pooled([(n, self.vars[n].stag) for n in missing], t,
                            lambda n, a: self._insert(n, t, a, protect), progress, cancelled)

    def read_box(self, name, t, i0, i1, j0, j1):
        vol = self.cached(name, t)
        if vol is not None:
            return np.array(vol[:, j0:j1, i0:i1])
        return super().read_box(name, t, i0, i1, j0, j1)

    def mean_profiles(self, names, t, progress=None):
        todo = [n for n in dict.fromkeys(names) if (n, t) not in self._means]
        if todo:  # (the mean volumes, read in parallel, then averaged here)
            self.load_volumes(todo, t, progress)
        return super().mean_profiles(names, t)

    def heights(self, t, ref="agl", w=False):
        if not w:
            return super().heights(t, ref)
        z = self._zw.get(t)
        if z is None:
            self._check("zmsl", t)
            if self.workers > 1 and self._shm:
                out = {}
                self._pooled([("zmsl", None)], t, out.__setitem__)
                z = out["zmsl"]
            else:
                with IO_LOCK:
                    z = np.asarray(self._ds(t)["zmsl"][0], np.float32)
            z = z / np.float32(1000.0)
            self._zw[t] = z
            while len(self._zw) > 4:
                self._zw.popitem(last=False)
        else:
            self._zw.move_to_end(t)
        return z if ref == "msl" else z - self._hgt.astype(np.float32)


def open_run(path, **kw):
    """A member's run, or the mean's (<root>/mean)."""
    return (WoFSMeanRun if mean_of(path) is not None and not os.path.isdir(path)
            else WoFSRun)(path, **kw)
