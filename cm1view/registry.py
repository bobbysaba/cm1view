"""Open runs shared by all browser sessions, plus run discovery for the picker."""

import glob
import json
import os
import threading

from . import config
from .core.fields import Fields
from .core import models
from .core.run import VolumeCache

_OLD_RECENT = os.path.join(os.path.expanduser("~"), ".cache", "cm1view", "recent.json")


def _recent_file():
    """Next to the settings file, so tests (with their own settings) keep theirs apart."""
    return os.path.join(os.path.dirname(config.config_path()), "recent.json")


def is_run(path, model=None):
    return models.exists(path) and count_files(path, model) > 0


def count_files(path, model=None):
    """Output times in `path`, of `model` (a core.models key; None/"auto": the model
    detected there)."""
    return models.count(path, model) if path else 0


def sibling_runs(path, limit=60):
    """Run directories next to `path` (same parent), plus any directly under it (for a
    run named inside a folder, e.g. a WoFS member: the folder's other runs)."""
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return [p for p in models.siblings(path) if p != path][:limit]
    out = set()
    for base in (os.path.dirname(path), path):
        if not config.searchable(base):  # (never list a shared folder's users)
            continue
        for d in sorted(glob.glob(os.path.join(base, "*", ""))):
            d = d.rstrip("/")
            if is_run(d):
                out.add(d)
            if len(out) >= limit:
                break
    return sorted(out)


_CHOSEN = {}  # run path -> model key chosen for it (instead of detected)
_CHOSEN_LOCK = threading.Lock()


def choose(path, model):
    """Read `path` with `model` (a core.models key) from now on, in every session;
    None or "auto": detect it again."""
    path = os.path.abspath(path)
    with _CHOSEN_LOCK:
        if models.get(model):
            _CHOSEN[path] = model
        else:
            _CHOSEN.pop(path, None)


def chosen(path):
    """The model key chosen for `path` (None: detected)."""
    with _CHOSEN_LOCK:
        return _CHOSEN.get(os.path.abspath(path))


def recent_runs():
    for fn in (_recent_file(), _OLD_RECENT):  # (older versions kept it in ~/.cache)
        try:
            with open(fn) as f:
                # (a WoFS member, as kept before: its experiment, once)
                found = [models.root_of(p) for p in json.load(f) if models.exists(p)]
                return list(dict.fromkeys(found))
        except (OSError, ValueError):
            continue
    return []


def remember(path):
    from . import demo
    if demo.is_demo(path):
        return
    path = models.root_of(path)  # (a WoFS member: its experiment is the run)
    lst = [path] + [p for p in recent_runs() if p != path]
    try:
        os.makedirs(os.path.dirname(_recent_file()), exist_ok=True)
        with open(_recent_file(), "w") as f:
            json.dump(lst[:15], f)
    except OSError:
        pass


class Registry:
    """A Run + Fields per run directory.  All runs share one 3D cache (one memory
    budget, least recently used evicted first), so tabs on different runs do not
    empty each other's cache.

    Which model reads a folder is detected, unless one was chosen for it (on the
    command line, in the run picker or by ?model=): see choose()."""

    def __init__(self, default, cache_gb, workers, model=None):
        self.default = os.path.abspath(default) if default else None
        self.cache_gb, self.workers = cache_gb, workers
        self.cache = VolumeCache(cache_gb)
        self._runs = {}
        if self.default and models.get(model):
            choose(self.default, model)
        self._lock = threading.Lock()

    def get(self, path=None, model=None):
        """(Run, Fields) of `path` (default: the default run), read by `model` (a
        core.models key) when given, else by the one chosen for it or detected."""
        if not (path or self.default):
            raise FileNotFoundError("no run given")
        path = os.path.abspath(path or self.default)
        # (a folder of several runs, e.g. a WoFS root: its first run)
        path = models.canonical(path, model if models.get(model) else chosen(path))
        with self._lock:
            if models.get(model):
                choose(path, model)
            want = chosen(path)
            if want and path in self._runs and self._runs[path][0].model != want:
                self._runs.pop(path)[0].clear_cache()  # (opened by another model)
            if path not in self._runs:
                run = models.open_run(path, want, cache_gb=self.cache_gb,
                                      workers=self.workers, cache=self.cache)
                self._runs[path] = (run, Fields(run))
            remember(path)
            return self._runs[path]

    def reopen(self, path):
        """(Run, Fields) of `path` opened again: a run still going gains the output
        finished since.  Cached volumes stay (keyed by path and time index, and the
        times loaded before were finished files: new ones only add at the end)."""
        path = models.canonical(os.path.abspath(path), chosen(path))
        with self._lock:
            old = self._runs.pop(path, None)
        try:
            return self.get(path)
        except Exception:
            if old is not None:  # (put back what was open: the page keeps showing it)
                with self._lock:
                    self._runs.setdefault(path, old)
            raise
