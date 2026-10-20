"""Open CM1 runs shared by all browser sessions, plus run discovery for the picker."""

import glob
import json
import os
import threading

from .fields import Fields
from .run import CM1Run

_RECENT = os.path.join(os.path.expanduser("~"), ".cache", "cm1view", "recent.json")


def is_run(path):
    return bool(path) and os.path.isdir(path) and bool(
        glob.glob(os.path.join(path, "cm1out_[0-9]*.nc")))


def count_files(path):
    return len(glob.glob(os.path.join(path, "cm1out_[0-9]*.nc")))


def sibling_runs(path, limit=60):
    """Run directories next to `path` (same parent), plus any directly under it."""
    path = os.path.abspath(path)
    out = set()
    for base in (os.path.dirname(path), path):
        for d in sorted(glob.glob(os.path.join(base, "*", ""))):
            d = d.rstrip("/")
            if is_run(d):
                out.add(d)
            if len(out) >= limit:
                break
    return sorted(out)


def recent_runs():
    try:
        with open(_RECENT) as f:
            return [p for p in json.load(f) if os.path.isdir(p)]
    except (OSError, ValueError):
        return []


def remember(path):
    lst = [path] + [p for p in recent_runs() if p != path]
    try:
        os.makedirs(os.path.dirname(_RECENT), exist_ok=True)
        with open(_RECENT, "w") as f:
            json.dump(lst[:15], f)
    except OSError:
        pass


class Registry:
    """CM1Run + Fields per run directory.  Opening a new run frees the 3D caches of
    the others, so memory stays within one run's budget."""

    def __init__(self, default, cache_gb, workers):
        self.default = os.path.abspath(default)
        self.cache_gb, self.workers = cache_gb, workers
        self._runs = {}
        self._lock = threading.Lock()

    def get(self, path=None):
        path = os.path.abspath(path or self.default)
        with self._lock:
            if path not in self._runs:
                run = CM1Run(path, cache_gb=self.cache_gb, workers=self.workers)
                for other, _ in self._runs.values():
                    other.clear_cache()
                self._runs[path] = (run, Fields(run))
            remember(path)
            return self._runs[path]
