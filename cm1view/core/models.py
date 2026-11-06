"""The models cm1view can read, and which one a folder holds.

Each model names its reader (a core.run.Run subclass) and how its output is found:
count(path) is the number of output times in a folder, and looks(entries) says from
one folder listing (os.scandir entries, no further reads) whether it is a run of the
model, which keeps the search for runs cheap.  "auto" picks the first model whose
output a folder holds.

A run's path is usually its folder.  A model may also name runs inside one folder
(WoFS: an experiment folder is one run in the picker, but each ensemble member is
read as <root>/memNN, and their mean as <root>/mean; no such folders on disk):
parts(path) lists them, virtual(path) says a path is one, and canonical(path) turns
the folder itself into the one to open."""

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

    def parts(self, path, entries=None):
        """The runs named inside a run folder (WoFS: members and mean); [] if none."""
        return []

    def summary(self, path):
        """A few words on a run folder for the picker (e.g. "36 members"), or ""."""
        return ""

    def part_label(self, path):
        """The name of a run named inside a folder (parts) in a list: e.g. "Member 5"."""
        return os.path.basename(path.rstrip("/"))

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
    """WoFS (DART-cycled WRF): an experiment folder of date folders of cycle folders of
    member wrfouts.  The experiment is one run; its members (and their mean) are read
    as runs of their own (parts)."""
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
        # (one or two more listings: the first date folder, the first cycle folder)
        return bool(entries) and bool(wofs.members(os.path.dirname(entries[0].path), entries))

    def runs(self, path, entries):
        return [path]  # (the experiment: one run)

    def parts(self, path, entries=None):
        from . import wofs
        return wofs.run_paths(path, entries)

    def summary(self, path):
        from . import wofs
        root = path if os.path.isdir(path) else (wofs.mean_of(path)
                                                 or (wofs.member_of(path) or ("",))[0])
        n = len(wofs.members(root)) if root else 0
        return f"{n} member{'s' * (n != 1)}" if n else ""

    def part_label(self, path):
        from . import wofs
        rm = wofs.member_of(path)
        return f"Member {rm[1]}" if rm else "Ensemble mean"

    def virtual(self, path):
        from . import wofs
        return wofs.is_member(path) or wofs.is_mean(path)

    def open(self, path, **kw):
        from . import wofs
        return wofs.open_run(path, **kw)

    def canonical(self, path):
        from . import wofs
        return wofs.open_path(path) if os.path.isdir(path) else path


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
    """The run to open for `path`: a folder holding several runs (a WoFS experiment)
    gives the one its model opens first; anything else is returned as is."""
    if not path or not os.path.isdir(path):
        return path
    m = get(key) or detect(path)
    return m.canonical(path) if m is not None else path


def root_of(path):
    """The run folder a virtual run is named in (a WoFS member's experiment), else
    `path` itself."""
    for m in MODELS.values():
        if m.virtual(path):
            return os.path.dirname(os.path.abspath(path))
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
            return m.parts(os.path.dirname(os.path.abspath(path)))
    return []


def parts(path, key=None):
    """The runs named inside a run folder or next to a virtual run (WoFS members and
    mean), else []."""
    if not exists(path):
        return []
    if not os.path.isdir(path):
        return siblings(path)
    m = get(key) or detect(path)
    return m.parts(path) if m is not None else []


def part_label(path):
    """A virtual run's name in its folder's list ("Member 5"), else its folder name."""
    for m in MODELS.values():
        if m.virtual(path):
            return m.part_label(path)
    return os.path.basename(os.path.abspath(path).rstrip("/"))


def summary(path, key=None):
    m = get(key) or detect(path)
    return m.summary(path) if m is not None and exists(path) else ""


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

