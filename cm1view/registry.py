"""Open CM1 runs shared by all browser sessions, plus run discovery for the picker."""

import glob
import json
import os
import threading

from . import config
from .fields import Fields
from .run import CM1Run, VolumeCache

_RECENT = os.path.join(os.path.expanduser("~"), ".cache", "cm1view", "recent.json")


def is_run(path):
    return bool(path) and os.path.isdir(path) and count_files(path) > 0


def count_files(path):
    return len(glob.glob(os.path.join(path, config.get("output_glob"))))


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


def subfolders(path, limit=400):
    """{label: path} for a folder browser: '..' first, then the subfolders of `path`
    (hidden ones skipped); folders that hold CM1 output are marked ● with a file count."""
    path = os.path.abspath(path)
    out = {}
    parent = os.path.dirname(path)
    if parent != path:
        out["↑  ..  (" + os.path.basename(parent.rstrip("/") or "/") + ")"] = parent
    try:
        names = sorted(e.name for e in os.scandir(path)
                       if e.is_dir(follow_symlinks=True) and not e.name.startswith("."))
    except OSError:
        return out
    for n in names[:limit]:
        d = os.path.join(path, n)
        k = count_files(d)
        out[f"●  {n}   ({k} files)" if k else f"▸  {n}"] = d
    if len(names) > limit:
        out[f"… {len(names) - limit} more (type the name)"] = path
    return out


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
    """CM1Run + Fields per run directory.  All runs share one 3D cache (one memory
    budget, least recently used evicted first), so tabs on different runs do not
    empty each other's cache."""

    def __init__(self, default, cache_gb, workers):
        self.default = os.path.abspath(default) if default else None
        self.cache_gb, self.workers = cache_gb, workers
        self.cache = VolumeCache(cache_gb)
        self._runs = {}
        self._lock = threading.Lock()

    def get(self, path=None):
        if not (path or self.default):
            raise FileNotFoundError("no run given")
        path = os.path.abspath(path or self.default)
        with self._lock:
            if path not in self._runs:
                run = CM1Run(path, cache_gb=self.cache_gb, workers=self.workers,
                             cache=self.cache)
                self._runs[path] = (run, Fields(run))
            remember(path)
            return self._runs[path]
