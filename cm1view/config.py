"""User settings: ~/.config/cm1view/config.toml (or $CM1VIEW_CONFIG).

Each setting comes from, in increasing precedence: the built-in default, the config
file, an environment variable CM1VIEW_<NAME> (lists separated by ':'), and a
command-line flag.  `source(name)` says which one won.  Path settings take effect
on the next use; settings marked `restart` only when the server starts again."""

import fnmatch
import json
import os
import threading
import time
import tomllib

DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".config", "cm1view", "config.toml")
SECTIONS = ("paths", "tracks", "data", "server")


class Key:
    def __init__(self, name, section, default, label, help, kind="str", restart=False,
                 advanced=False, required=False):
        self.name, self.section, self.default = name, section, default
        self.label, self.help, self.kind = label, help, kind
        self.restart, self.advanced, self.required = restart, advanced, required


KEYS = [
    Key("runs_root", "paths", [], "Where your runs live",
        "Folders searched for CM1 runs (folders holding the output files). The run "
        "picker starts here.", kind="dirs", required=True),
    Key("default_run", "paths", "", "Run to open on launch",
        "Optional: a run opened when cm1view starts without a run argument.",
        kind="dir"),
    Key("figures_dir", "paths", "~/cm1view/figures", "Figures",
        "Exported figures go to <this>/<parent>_<run>/ (image and script; data and "
        "spec in _src/).", kind="outdir"),
    Key("exports_dir", "paths", "~/cm1view/exports", "Saved data",
        "Saved series and tracks go to <this>/<parent>_<run>/series and .../tracks.",
        kind="outdir"),
    Key("cache_dir", "paths", "~/.cache/cm1view", "Cache",
        "Throwaway files cm1view can rebuild (computed series). Scratch is a good "
        "place: home quotas are small.", kind="outdir"),
    Key("pdecomp_script", "paths", "", "Pressure-decomposition script",
        "Optional: the script run for times whose files lack p_b/p_l/p_nl. Leave "
        "empty to hide the feature.", kind="file"),
    Key("track_dirs", "tracks", ["storm_tracks"], "Track folders",
        "Where storm track files are looked for. A plain name (storm_tracks) is a "
        "folder of that name in the run folder or up to 4 folders above it; a full "
        "path is used as is.", kind="list"),
    Key("track_patterns", "tracks",
        ["{parent}_{name}.csv", "{parent}_{name}.txt", "{name}.csv", "{name}.txt"],
        "Track file names",
        "File names tried in each track folder: {name} = run folder, {parent} = the "
        "folder above it. Wildcards (*) are allowed.", kind="list"),
    Key("output_glob", "data", "cm1out_[0-9]*.nc", "Output file names",
        "Which files in a run folder are CM1 output (applies to runs opened after "
        "saving)."),
    Key("allow_writes_to_output", "data", False, "Allow writing into output files",
        "Lets the pressure decomposition write its fields into the CM1 output files. "
        "Off: results stay in memory.", kind="bool"),
    Key("cache_gb", "server", "auto", "3D cache (GB)",
        "Memory for cached 3D fields. auto = a share of this job's memory, leaving "
        "room for the pressure decomposition.", kind="auto_float", restart=True,
        advanced=True),
    Key("workers", "server", "auto", "Reader processes",
        "Parallel file readers. auto = the CPUs this job was given (at most 8).",
        kind="auto_int", restart=True, advanced=True),
    Key("port", "server", 5006, "Port",
        "Server port; the next free one is used if it is taken.", kind="int",
        restart=True, advanced=True),
    Key("maxpix", "server", 900, "Map pixels",
        "Max map pixels sent per axis (zoom in for full resolution). Applies to "
        "pages opened after saving.", kind="int", advanced=True),
    Key("login_host", "server", "", "SSH login host",
        "Only for the SSH tunnel command printed at launch (the machine you ssh "
        "into, e.g. login.cluster.edu). Empty: a placeholder is printed.",
        advanced=True),
]
BY_NAME = {k.name: k for k in KEYS}
LEGACY_ENV = {"pdecomp_script": "CM1VIEW_PDECOMP"}

_lock = threading.Lock()
_listeners = []
_state = dict(path=None, file={}, cli={}, exists=False, error="")


# ------------------------------------------------------------------ loading
def config_path():
    return _state["path"] or os.environ.get("CM1VIEW_CONFIG") or DEFAULT_PATH


def load(path=None):
    """(Re)read the config file; keeps command-line overrides."""
    with _lock:
        _state["path"] = os.path.abspath(os.path.expanduser(path)) if path else \
            _state["path"]
        p = config_path()
        _state["file"], _state["exists"], _state["error"] = {}, os.path.isfile(p), ""
        if _state["exists"]:
            try:
                with open(p, "rb") as f:
                    _state["file"] = _flatten(tomllib.load(f))
            except (OSError, tomllib.TOMLDecodeError) as e:
                _state["error"] = f"{p}: {e}"


def _flatten(doc):
    out = {}
    for k, v in doc.items():
        if isinstance(v, dict) and k in SECTIONS:
            out.update({kk: vv for kk, vv in v.items() if kk in BY_NAME})
        elif k in BY_NAME:
            out[k] = v
    return {k: _coerce(BY_NAME[k], v) for k, v in out.items()}


def _coerce(key, v):
    kind = key.kind
    if kind in ("dirs", "list"):
        if isinstance(v, str):
            v = [s for s in v.split(os.pathsep if kind == "dirs" else ",") if s.strip()]
        return [str(s).strip() for s in v if str(s).strip()]
    if kind == "bool":
        return v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true",
                                                                         "yes", "on")
    if kind in ("auto_float", "auto_int"):
        if v is None or str(v).strip().lower() in ("", "auto"):
            return "auto"
        return float(v) if kind == "auto_float" else int(v)
    if kind == "int":
        return int(v)
    return "" if v is None else str(v).strip()


def _env(name):
    for var in (f"CM1VIEW_{name.upper()}", LEGACY_ENV.get(name)):
        if var and os.environ.get(var, "") != "":
            return var, os.environ[var]
    return None, None


def override(name, value, flag):
    """A command-line value (wins over everything else)."""
    _state["cli"][name] = (_coerce(BY_NAME[name], value), flag)


def source(name):
    """'command line (--flag)', 'environment (VAR)', 'config file' or 'default'."""
    if name in _state["cli"]:
        return f"command line ({_state['cli'][name][1]})"
    var, _ = _env(name)
    if var:
        return f"environment ({var})"
    if name in _state["file"]:
        return "config file"
    return "default"


def get(name):
    if name in _state["cli"]:
        return _state["cli"][name][0]
    var, val = _env(name)
    if var:
        try:
            return _coerce(BY_NAME[name], val)
        except ValueError:
            pass
    if name in _state["file"]:
        return _state["file"][name]
    d = BY_NAME[name].default
    return list(d) if isinstance(d, list) else d


def file_value(name):
    """What the config file says (or the default): what the settings form edits."""
    d = BY_NAME[name].default
    return _state["file"].get(name, list(d) if isinstance(d, list) else d)


def exists():
    return _state["exists"]


def read_error():
    return _state["error"]


def on_change(fn):
    """fn() after every save (from any session's thread)."""
    _listeners.append(fn)


def off(fn):
    if fn in _listeners:
        _listeners.remove(fn)


# ------------------------------------------------------------------ saving
def to_toml(values):
    """The config file text: every setting, with its help as a comment."""
    out = ["# cm1view settings (edit here or with the gear button in the viewer).",
           "# Environment variables CM1VIEW_<NAME> and command-line flags override these.",
           ""]
    for sec in SECTIONS:
        out.append(f"[{sec}]")
        for k in KEYS:
            if k.section != sec:
                continue
            out.append(f"# {k.label}: {k.help}" + (" (needs a restart)" if k.restart else ""))
            out.append(f"{k.name} = {_toml_value(values.get(k.name, k.default))}")
        out.append("")
    return "\n".join(out)


def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(json.dumps(str(s)) for s in v) + "]"
    return json.dumps(str(v))  # JSON string escapes are valid TOML basic strings


def save(values):
    """Write all settings (values: name -> value; missing ones keep the file's) and
    reload.  Raises ValueError for a bad value, OSError when the file can't be written."""
    merged = {k.name: file_value(k.name) for k in KEYS}
    for name, v in values.items():
        merged[name] = _coerce(BY_NAME[name], v)
    save_text(to_toml(merged))


def save_text(text):
    """Write the raw file text (checked first) and reload."""
    doc = tomllib.loads(text)
    _flatten(doc)  # raises ValueError for values of the wrong type
    p = config_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, p)
    load()
    for fn in list(_listeners):
        try:
            fn()
        except Exception:  # noqa: BLE001  (a closed session must not stop the others)
            pass


def file_text():
    try:
        with open(config_path()) as f:
            return f.read()
    except OSError:
        return to_toml({k.name: file_value(k.name) for k in KEYS})


def state(name, default=""):
    """Small remembered values (e.g. the last folder chosen for a figure), kept in
    state.json next to the config file."""
    try:
        with open(_state_path()) as f:
            return json.load(f).get(name, default)
    except (OSError, ValueError, AttributeError):
        return default


def set_state(name, value):
    p = _state_path()
    try:
        with open(p) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d[name] = value
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(d, f, indent=1)
    except OSError:
        pass


def _state_path():
    return os.path.join(os.path.dirname(config_path()), "state.json")


# ------------------------------------------------------------------ checks
def expand(p):
    return os.path.abspath(os.path.expanduser(os.path.expandvars(p))) if p else ""


def check(name, value):
    """A problem with this value ('' when fine)."""
    key = BY_NAME[name]
    if key.kind == "dirs":
        if key.required and not value:
            return "Required: at least one folder."
        bad = [p for p in value if not os.path.isdir(expand(p))]
        return f"Not a folder: {', '.join(bad)}" if bad else ""
    if key.kind == "dir" and value and not os.path.isdir(expand(value)):
        return "Not a folder."
    if key.kind == "file" and value and not os.path.isfile(expand(value)):
        return "File not found."
    if key.kind == "outdir" and value and not _creatable(expand(value)):
        return "Can't create or write to this folder."
    if key.kind == "outdir" and not value:
        return "Required."
    return ""


def _creatable(p):
    while p and not os.path.exists(p):
        p = os.path.dirname(p)
    return bool(p) and os.path.isdir(p) and os.access(p, os.W_OK | os.X_OK)


def problems():
    """{name: message} for the settings in effect."""
    return {k.name: m for k in KEYS if (m := check(k.name, get(k.name)))}


def needs_setup():
    """The first-run window is required: no config file yet, or no usable runs_root."""
    return not exists() or bool(read_error()) or bool(check("runs_root", get("runs_root")))


# ------------------------------------------------------------------ paths
def run_key(path):
    """<parent>_<name>: one folder name per run for saved files."""
    path = os.path.abspath(path).rstrip("/")
    return f"{os.path.basename(os.path.dirname(path))}_{os.path.basename(path)}"


def figures_dir(run_path):
    return os.path.join(expand(get("figures_dir")), run_key(run_path))


def exports_dir(run_path, kind):
    return os.path.join(expand(get("exports_dir")), run_key(run_path), kind)


def cache_dir(*sub):
    return os.path.join(expand(get("cache_dir")), *sub)


def pdecomp_script():
    return expand(get("pdecomp_script"))


def find_track(path, levels=4):
    """A storm track file for the run in `path` (see track_dirs / track_patterns)."""
    import glob
    path = os.path.abspath(path).rstrip("/")
    name, parent = os.path.basename(path), os.path.basename(os.path.dirname(path))
    dirs = []
    for d in get("track_dirs"):
        if os.path.isabs(os.path.expanduser(d)):
            dirs.append(expand(d))
        else:
            up = path
            for _ in range(levels):
                dirs.append(os.path.join(up, d))
                up = os.path.dirname(up)
    for tdir in dirs:
        for pat in get("track_patterns"):
            hits = sorted(glob.glob(os.path.join(tdir, pat.format(name=name,
                                                                  parent=parent))))
            if hits:
                return hits[0]
    return None


def is_output(fname):
    return fnmatch.fnmatch(fname, get("output_glob"))


def scan_runs(roots=None, depth=5, limit=500, seconds=4.0):
    """Run folders under the roots (breadth first, hidden folders skipped, no search
    inside a run).  Returns (runs, complete)."""
    t0, runs, complete = time.time(), [], True
    level = [expand(r) for r in (get("runs_root") if roots is None else roots) if r]
    for _ in range(depth + 1):
        nxt = []
        for d in level:
            if time.time() - t0 > seconds or len(runs) >= limit:
                return sorted(runs), False
            try:
                ents = list(os.scandir(d))
            except OSError:
                continue
            if any(e.is_file() and is_output(e.name) for e in ents):
                runs.append(d)
                continue
            nxt += sorted(e.path for e in ents
                          if not e.name.startswith(".") and e.is_dir())
        level = nxt
        if not level:
            break
    else:
        complete = not level
    return sorted(runs), complete


# ------------------------------------------------------------------ auto values
def job_memory_gb():
    """Memory this job may use (cgroup limit, else the node's)."""
    limit = None
    try:
        v = open("/sys/fs/cgroup/memory.max").read().strip()
        limit = None if v == "max" else int(v)
    except (OSError, ValueError):
        pass
    if limit is None or limit > 1 << 50:
        try:  # cgroup v1 (Casper)
            cg = [line.split(":")[2].strip() for line in open("/proc/self/cgroup")
                  if ":memory:" in line][0]
            limit = int(open(f"/sys/fs/cgroup/memory{cg}/memory.limit_in_bytes").read())
        except (OSError, IndexError, ValueError):
            limit = None
    if limit is None or limit > 1 << 50:
        limit = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return limit / 1024**3


def job_cpus():
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 1


def cache_gb():
    """(GB, how it was chosen)."""
    v = get("cache_gb")
    if v != "auto":
        return float(v), "set"
    mem = job_memory_gb()
    gb = 0.4 * mem
    if pdecomp_script():  # the decomposition needs ~40 GB at its peak
        gb = min(gb, mem - 48.0)
    gb = float(max(2.0, min(48.0, gb)))
    return gb, f"auto: {gb:.0f} GB of {mem:.0f} GB job memory"


def workers():
    v = get("workers")
    if v != "auto":
        return int(v), "set"
    n = max(1, min(8, job_cpus()))
    return n, f"auto: {n} of {job_cpus()} CPUs"


# ------------------------------------------------------------------ first run
def suggestions(run_path=None):
    """Values to pre-fill the first-run window with (the config file's where set)."""
    from . import registry
    out = {k.name: file_value(k.name) for k in KEYS}
    if not exists():
        recent = [p for p in ([run_path] if run_path else []) + registry.recent_runs() if p]
        if recent:
            # the folder that holds the runs: their common parent, or the grandparent
            # of a single run (e.g. phd/ for phd/southeast/rm_tor_125m)
            common = os.path.commonpath([os.path.abspath(p) for p in recent])
            if len(set(recent)) == 1 or common in recent:
                common = os.path.dirname(os.path.dirname(os.path.abspath(recent[0])))
            out["runs_root"] = [common]
            if run_path:
                out["default_run"] = os.path.abspath(run_path)
        scratch = os.environ.get("SCRATCH")
        if scratch and os.path.isdir(scratch):
            out["cache_dir"] = os.path.join(scratch, ".cache", "cm1view")
        found = _find_pdecomp()
        if found:
            out["pdecomp_script"] = found
        out["login_host"] = out["login_host"] or submit_host()
    return out


def submit_host():
    """The login node this batch job was submitted from (PBS / Slurm), else ""."""
    import socket
    h = os.environ.get("PBS_O_HOST") or os.environ.get("SLURM_SUBMIT_HOST") or ""
    if h and "." not in h:
        domain = socket.getfqdn().partition(".")[2]
        h = f"{h}.{domain}" if domain else h
    return h


def _find_pdecomp():
    """A pressure-decomposition script in the user's own folders, if there is one."""
    bases = [os.path.expanduser("~")] + [os.environ[v] for v in ("WORK", "SCRATCH")
                                          if os.environ.get(v)]
    for name in ("pdecomp_new_fixed_mp.py", "pdecomp_new_fixed.py"):
        for b in bases:
            for d in (b, *(os.path.join(b, e) for e in _subdirs(b))):
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    return p
    return ""


def _subdirs(d):
    try:
        return sorted(e.name for e in os.scandir(d)
                      if e.is_dir() and not e.name.startswith("."))[:200]
    except OSError:
        return []


load()
