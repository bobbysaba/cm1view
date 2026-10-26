"""Export: image, plotted arrays, stand-alone script and spec."""

import hashlib
import json
import os
import pprint
import time as _time

import numpy as np

from ... import config
from .. import draw as figdraw
from .base import _abs

def flatten(data):
    """{panel: {name: array}} -> {'p<panel>__<name>': array} for .npz files."""
    out = {}
    for i, d in data.items():
        for k, v in d.items():
            out[f"p{i}__{k}"] = np.asarray(v)
    return out


def unflatten(npz):
    data = {}
    for key in npz.files if hasattr(npz, "files") else npz:
        p, name = key.split("__", 1)
        v = npz[key]
        data.setdefault(int(p[1:]), {})[name] = v.item() if v.ndim == 0 else v
    return data


def save_image(spec, data, path, dpi=None):
    path = _abs(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig = figdraw.draw(spec, data)
    figdraw.save(spec, fig, path, **save_kw(spec, dpi))
    return path


def save_kw(spec, dpi=None):
    """savefig arguments of the spec's export settings."""
    ex = spec.get("export", {})
    tight = ex.get("tight", True)
    return dict(dpi=float(dpi or ex.get("dpi", 250)), bbox_inches="tight" if tight else None,
                pad_inches=float(ex.get("pad", 0.05)) if tight else 0.1,
                facecolor=spec.get("background", "white"),
                transparent=spec.get("background") == "none")


def bundle_paths(spec, base):
    """{image, script, data, spec, draw} for a bundle saved as `base`: the image and
    script side by side, the arrays, spec and drawing code in _src/ next to them."""
    base = _abs(base)
    root, ext = os.path.splitext(base)
    if ext.lower() in (".png", ".pdf", ".svg", ".eps", ".tif", ".tiff", ".jpg"):
        base = root
    fmt = spec.get("export", {}).get("format", "png")
    src, name = os.path.join(os.path.dirname(base), "_src"), os.path.basename(base)
    return dict(image=f"{base}.{fmt}", script=f"{base}.py",
                data=os.path.join(src, f"{name}_data.npz"),
                spec=os.path.join(src, f"{name}_spec.json"),
                draw=os.path.join(src, f"{name}_draw.py"))


_PROVENANCE = None


def provenance():
    """What made the figure: cm1view's version and, from a git checkout, its commit
    (with "+changes" when the checkout has uncommitted changes)."""
    global _PROVENANCE
    if _PROVENANCE is None:
        import subprocess
        from ... import __version__
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        commit = ""
        try:
            git = ["git", "-C", here]
            commit = subprocess.run(git + ["rev-parse", "--short", "HEAD"], text=True,
                                    capture_output=True, timeout=10).stdout.strip()
            if commit and subprocess.run(git + ["status", "--porcelain", "--", "."],
                                         text=True, capture_output=True,
                                         timeout=10).stdout.strip():
                commit += "+changes"
        except (OSError, subprocess.SubprocessError):
            pass
        _PROVENANCE = dict(cm1view=__version__, commit=commit)
    return dict(_PROVENANCE)


# the settings that change what a figure shows (which files are output, which track)
SETTINGS_USED = ("output_glob", "track_dirs", "track_patterns", "pdecomp_script")


def namelist_hash(path):
    """sha256 (first 16 hex digits) of the namelist.input of the run in `path` ("" when
    it has none): which setup the figure's data came from."""
    try:
        with open(os.path.join(path, "namelist.input"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return ""


def made_with(spec):
    """The provenance saved with a figure: cm1view's version and commit, the date, each
    run's namelist hash, and the settings in SETTINGS_USED."""
    return dict(provenance(), date=_time.strftime("%Y-%m-%d %H:%M"),
                runs=[dict(label=r.get("label", ""), path=r["path"],
                           namelist_sha256=namelist_hash(r["path"]))
                      for r in spec.get("runs") or []],
                settings={k: config.get(k) for k in SETTINGS_USED})


def changed_runs(spec):
    """Paths of the runs whose namelist.input differs from when the figure was saved
    (spec["made_with"]): its data may not draw the same now.  Runs saved without a
    hash, or now without a namelist, are not checked."""
    return [r["path"] for r in (spec.get("made_with") or {}).get("runs", [])
            if r.get("namelist_sha256") and namelist_hash(r["path"]) not in
            ("", r["namelist_sha256"])]


def save_bundle(spec, data, base, run=None, note=""):
    """Image + script side by side, data, spec and drawing code in _src/ (see
    bundle_paths).  Returns the paths.  The spec is saved as version 2 (every panel
    written out) with the editor's settings that made it under "form" (load_spec opens
    those); the script draws the version-2 spec with the drawing code."""
    out = bundle_paths(spec, base)
    form = dict(spec, made_with=made_with(spec))
    v2, data = figdraw.upgrade(form, data)
    os.makedirs(os.path.dirname(out["data"]), exist_ok=True)
    out["image"] = save_image(v2, data, out["image"])
    np.savez_compressed(out["data"], **flatten(data))
    with open(out["spec"], "w") as f:
        json.dump(dict(v2, form=form), f, indent=1, default=float)
    with open(out["draw"], "w") as f:
        f.write(drawing_code())
    with open(out["script"], "w") as f:
        f.write(script(v2, "_src/" + os.path.basename(out["data"]),
                       os.path.basename(out["image"]), run, note,
                       "_src/" + os.path.basename(out["draw"])))
    return out


def drawing_code():
    """The module saved in _src/ that a bundle's script draws with: draw's modules as
    one (figdraw.source()), and load_data."""
    return "\n".join([
        '"""cm1view\'s drawing code, saved with a figure: its script imports draw, save and',
        "load_data from here.  Needs only numpy and matplotlib (cmweather or pyart, if",
        "installed, for their colormaps).  The figure's own settings are SPEC in its script;",
        "change this code only for what SPEC cannot do.",
        "",
        figdraw.__doc__.strip(),
        '"""',
        "",
        figdraw.source(),
        "",
        "",
        "def load_data(path):",
        "    \"\"\"The arrays saved with the figure: {panel: {name: array}}.\"\"\"",
        "    data = {}",
        "    with np.load(path, allow_pickle=False) as z:",
        "        for key in z.files:",
        "            p, name = key.split('__', 1)",
        "            v = z[key]",
        "            data.setdefault(int(p[1:]), {})[name] = v.item() if v.ndim == 0 else v",
        "    return data",
        "",
    ])


def script(spec, npz_name, out_name, run=None, note="", draw_name="_src/draw.py"):
    """A short stand-alone script that redraws the figure from the saved arrays: SPEC,
    my_changes (the user's own matplotlib) and the drawing code imported from
    draw_name (drawing_code())."""
    made = provenance()
    nml = {r["path"]: r.get("namelist_sha256", "")
           for r in (spec.get("made_with") or {}).get("runs", [])}

    def tag(path):
        return f"  (namelist sha256 {nml[path]})" if nml.get(path) else ""

    head = [
        f'"""Figure made with cm1view {made["cm1view"]}'
        + (f' (commit {made["commit"]})' if made["commit"] else "")
        + f' on {_time.strftime("%Y-%m-%d %H:%M")}.',
        "",
        *(["runs:"] + [f"  {r['label']}: {r['path']}{tag(r['path'])}" for r in spec["runs"]]
          if len(spec.get("runs") or []) > 1 else
          [f"run: {run.path}{tag(run.path)}" if run is not None else ""]),
        note,
        "Redraw:  python this_script.py   (needs numpy and matplotlib; cmweather or pyart",
        "for their colormaps).  To change the figure:",
        "  - SPEC below: its settings (colours, ranges, labels, size, ...), as in the editor;",
        "  - my_changes() below: anything else, in plain matplotlib, after it is drawn.",
        f"The plotted arrays are in {npz_name}, the drawing code in {draw_name}.",
        '"""',
    ]
    body = [
        "import importlib.util",
        "import os",
        "",
        "import numpy as np",
        "",
        "HERE = os.path.dirname(os.path.abspath(__file__))",
        "",
        "# ----------------------------------------------------------------- figure spec",
        "SPEC = " + pprint.pformat(_plain(spec), width=92, sort_dicts=False),
        "",
        "",
        "# ----------------------------------------------------------------- your changes",
        "def my_changes(fig, axs, data, spec):",
        '    """Run after the figure is drawn: fig the matplotlib Figure, axs the panels\' axes',
        "    (axs[0] the first panel; colorbars and a skew-T's hodograph are in fig.axes), data",
        "    the plotted arrays of each panel (data[0][\"x\"], ...; listed at the top of the",
        "    drawing code), spec SPEC.  The editor's \"Your own code\" works here too.",
        "    For example:",
        "        axs[0].set_xlim(-20, 20)",
        "        axs[0].plot(5.0, 3.0, \"k*\", ms=12)",
        "        axs[0].set_title(\"my title\")",
        '    """',
        "",
        "",
        "# ----------------------------------------------------------------- redraw",
        "def drawing_code(path):",
        '    """cm1view\'s drawing code saved with the figure (draw, save, load_data)."""',
        "    s = importlib.util.spec_from_file_location(\"cm1view_draw\", path)",
        "    code = importlib.util.module_from_spec(s)",
        "    s.loader.exec_module(code)",
        "    return code",
        "",
        "",
        'if __name__ == "__main__":',
        f"    cv = drawing_code(os.path.join(HERE, *{draw_name!r}.split('/')))",
        f"    data = cv.load_data(os.path.join(HERE, *{npz_name!r}.split('/')))",
        "    fig = cv.draw(SPEC, data)",
        "    if getattr(fig, '_cv_code_error', None):",
        "        print('the figure code stopped at', fig._cv_code_error)",
        "    my_changes(fig, [fig._cv_axes[i] for i in sorted(fig._cv_axes)], data, SPEC)",
        f"    out = os.path.join(HERE, {out_name!r})",
        "    ex = SPEC.get('export', {})",
        "    tight = ex.get('tight', True)",
        "    cv.save(SPEC, fig, out, dpi=ex.get('dpi', 250), bbox_inches='tight' if tight else None,",
        "            pad_inches=ex.get('pad', 0.05) if tight else 0.1,",
        "            facecolor=fig.get_facecolor(), transparent=SPEC.get('background') == 'none')",
        "    print('saved', out)",
        "",
    ]
    return "\n".join([h for h in head if h is not None]) + "\n" + "\n".join(body)


def _plain(o):
    """JSON round trip: numpy scalars and tuples become plain Python."""
    return json.loads(json.dumps(o, default=float))


def load_spec(path):
    """The editor's settings of a saved figure: a version-1 spec as it is, of a
    version-2 one the settings that made it ("form")."""
    with open(_abs(path)) as f:
        spec = json.load(f)
    if spec.get("version") == 2:
        if not isinstance(spec.get("form"), dict):
            raise ValueError("this version-2 spec has no editor settings (\"form\"): "
                             "redraw it with its script")
        spec = spec["form"]
    if spec.get("version") != 1:
        raise ValueError("not a cm1view figure spec (version 1 or 2)")
    for r in spec.get("runs") or []:
        if not os.path.isdir(r["path"]):
            raise ValueError(f"run folder {r['path']} not found")
    return spec
