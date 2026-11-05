"""The models cm1view can read, and which one a folder holds.

Each model names its reader (a core.run.Run subclass) and how its output is found:
count(path) is the number of output times in a folder, and looks(entries) says from
one folder listing (os.scandir entries, no further reads) whether it is a run of the
model, which keeps the search for runs cheap.  "auto" picks the first model whose
output a folder holds.

A run's path is usually its folder.  A model may also name runs inside one folder
(WoFS: <root>/memNN, one per ensemble member, no such folder on disk): runs(path,
entries) lists them, virtual(path) says a path is one, and canonical(path) turns the
folder itself into its first run."""

import glob
import os

AUTO = "auto"


class Model:
    key = ""
    label = ""
    run_class = None

    def count(self, path):
        return 0

    def looks(self, entries):
        return False

    def runs(self, path, entries):
        """The runs in a folder that looks(entries) like this model's."""
        return [path]

    def virtual(self, path):
        """Is `path` a run of this model that is not a folder on disk?"""
        return False

    def canonical(self, path):
        """The run path to open for `path` (a folder holding several runs: its first)."""
        return path

    def open(self, path, **kw):
        return self.run_class(path, **kw)


class CM1(Model):
    key, label = "cm1", "CM1"

    @property
    def run_class(self):
        from .run import CM1Run
        return CM1Run

    def count(self, path):
        from .. import config
        return len(glob.glob(os.path.join(path, config.get("output_glob"))))

    def looks(self, entries):
        from .. import config
        return any(_is_file(e) and config.is_output(e.name) for e in entries)


class WoFS(Model):
    """WoFS (DART-cycled WRF): cycle folders of member wrfouts; one run per member."""
    key, label = "wofs", "WoFS"

    @property
    def run_class(self):
        from .wofs import WoFSRun
        return WoFSRun

    def count(self, path):
        from . import wofs
        return wofs.count(path)

    def looks(self, entries):
        from . import wofs
        entries = list(entries)
        # (one more listing: the first cycle folder, for member files)
        return bool(entries) and bool(wofs.members(os.path.dirname(entries[0].path), entries))

    def runs(self, path, entries):
        from . import wofs
        return [wofs.member_path(path, m) for m in wofs.members(path, entries)]

    def virtual(self, path):
        from . import wofs
        return wofs.is_member(path)

    def canonical(self, path):
        from . import wofs
        ms = wofs.members(path) if os.path.isdir(path) else []
        return wofs.member_path(path, ms[0]) if ms else path


MODELS = {m.key: m for m in (CM1(), WoFS())}


def choices():
    """{label: key} for a model picker, auto-detect first."""
    return {"Auto-detect": AUTO, **{m.label: k for k, m in MODELS.items()}}


def get(key):
    """The Model of a key (None or "auto": None)."""
    if not key or key == AUTO:
        return None
    try:
        return MODELS[key]
    except KeyError:
        raise ValueError(f"unknown model {key!r} (one of: {', '.join(MODELS)})") from None


def detect(path):
    """The Model whose output is in `path`, or None."""
    if not exists(path):
        return None
    return next((m for m in MODELS.values() if m.count(path) > 0), None)


def exists(path):
    """A folder, or a run a model names inside one (see virtual())."""
    return bool(path) and (os.path.isdir(path)
                           or any(m.virtual(path) for m in MODELS.values()))


def canonical(path, key=None):
    """The run to open for `path`: a folder holding several runs (a WoFS root) gives
    its first; anything else is returned as is."""
    if not path or not os.path.isdir(path) or (get(key) is None and detect(path)):
        return path
    for m in [get(key)] if get(key) else MODELS.values():
        p = m.canonical(path)
        if p != path:
            return p
    return path


def runs_in(path, entries, key=None):
    """The runs in a folder whose listing looks like a run (of `key`, or any model)."""
    ms = [get(key)] if get(key) else MODELS.values()
    m = next((m for m in ms if m.looks(entries)), None)
    return m.runs(path, entries) if m is not None else []


def siblings(path):
    """The other runs named inside the same folder as a virtual run (else [])."""
    for m in MODELS.values():
        if m.virtual(path):
            return m.runs(os.path.dirname(os.path.abspath(path)),
                          list(os.scandir(os.path.dirname(os.path.abspath(path)))))
    return []


def resolve(path, key=None):
    """The Model to open `path` with: `key` if given, else the detected one, else
    FileNotFoundError."""
    m = get(key) or detect(path)
    if m is None:
        raise FileNotFoundError(f"no model output found in {path}")
    return m


def count(path, key=None):
    """Output times in `path` (of model `key`, else of the model detected there)."""
    m = get(key) or detect(path)
    return m.count(path) if m is not None and exists(path) else 0


def looks_like_run(entries, key=None):
    """From one folder listing: is it a run (of model `key`, or of any model)?"""
    ms = [get(key)] if get(key) else MODELS.values()
    return any(m.looks(entries) for m in ms)


def open_run(path, key=None, **kw):
    """The Run in `path`, read by model `key` (auto-detected when None or "auto")."""
    path = canonical(path, key)
    return resolve(path, key).open(path, **kw)


def _is_file(entry):
    try:
        return entry.is_file()
    except OSError:
        return False

