"""The models cm1view can read, and which one a folder holds.

Each model names its reader (a core.run.Run subclass) and how its output is found:
count(path) is the number of output times in a folder, and looks(entries) says from
one folder listing (os.scandir entries, no further reads) whether it is a run of the
model, which keeps the search for runs cheap.  "auto" picks the first model whose
output a folder holds."""

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


MODELS = {m.key: m for m in (CM1(),)}


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
    if not path or not os.path.isdir(path):
        return None
    return next((m for m in MODELS.values() if m.count(path) > 0), None)


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
    return m.count(path) if m is not None and os.path.isdir(path) else 0


def looks_like_run(entries, key=None):
    """From one folder listing: is it a run (of model `key`, or of any model)?"""
    ms = [get(key)] if get(key) else MODELS.values()
    return any(m.looks(entries) for m in ms)


def open_run(path, key=None, **kw):
    """The Run in `path`, read by model `key` (auto-detected when None or "auto")."""
    return resolve(path, key).open(path, **kw)


def _is_file(entry):
    try:
        return entry.is_file()
    except OSError:
        return False
