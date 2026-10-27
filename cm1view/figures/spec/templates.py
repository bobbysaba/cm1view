"""Templates, style presets and copying a layer's look."""

import json
import os

import numpy as np

from ... import config
from .base import tindex, shift_times, _abs
from .bundle import _plain

def template(spec, name=""):
    """`spec` as a template to apply to another run (from_template): its layout and
    look without its runs (what only another run had is left out), its times kept
    relative to the shown time."""
    s = _plain(spec)
    t0 = (s["parts"][0] if s.get("kind") == "combo" else s).get("time_s")
    s.pop("runs", None)
    for p in s["parts"] if s.get("kind") == "combo" else [s]:
        p.pop("runs", None)
        p["run"] = 0
        p["panels"] = [q for q in p.get("panels") or [] if int(q.get("run", 0)) == 0]
        for key in ("soundings", "dists", "profiles", "joints", "azims"):
            p[key] = [e for e in p.get(key) or [] if int(e.get("run", 0)) == 0]
        for e in p.get("series") or []:
            e["runs"] = None
        for lay in p.get("layers") or []:
            if (lay.get("minus") or {}).get("run") not in (None, 0):
                lay.pop("minus")
            if lay.get("ens"):  # (an ensemble: of the new figure's runs)
                lay["ens"] = dict(lay["ens"], runs=None)
        for e in (p.get("edits") or {}).values():
            for lay in [e] + list((e.get("layers") or {}).values()) + list(e.get("extra") or []):
                if lay.get("run") not in (None, 0):
                    lay["run"] = None
    s["template"] = dict(name=name, time_s=None if t0 is None else float(t0))
    return s


def from_template(tpl, run, t):
    """Template `tpl` applied to `run` shown at output t: its times moved to there
    (each to the nearest output; panels past the run's end are left empty).  The
    run itself is added by the editor (as for a saved figure without runs)."""
    s = _plain(tpl)
    t0 = (s.pop("template", None) or {}).get("time_s")
    s = shift_times(s, 0.0 if t0 is None else float(run.times[t]) - float(t0))
    tt = np.asarray(run.times, dtype=float)

    def near(ts, clip=True):
        if ts is None or (not clip and not tt[0] - 1.0 <= float(ts) <= tt[-1] + 1.0):
            return None
        return float(tt[int(np.argmin(np.abs(tt - float(ts))))])

    for p in s["parts"] if s.get("kind") == "combo" else [s]:
        p.pop("runs", None)
        p["times_s"] = [near(ts, clip=False) for ts in p.get("times_s") or []]
        p["time_s"] = near(p.get("time_s", tt[t]))
        p["times"] = [None if ts is None else tindex(run, ts) for ts in p["times_s"]]
        p["time"] = tindex(run, p["time_s"])
        for e in (p.get("panels") or []) + (p.get("soundings") or []) + \
                (p.get("dists") or []) + (p.get("profiles") or []) + (p.get("joints") or []) + \
                (p.get("azims") or []):
            e["time_s"] = near(e["time_s"])
            if e.get("time_s1") is not None:
                e["time_s1"] = near(e["time_s1"])
        for e in (p.get("edits") or {}).values():
            for lay in [e] + list((e.get("layers") or {}).values()) + list(e.get("extra") or []):
                if lay.get("time_s") is not None and not lay.get("time_lock"):
                    lay["time_s"] = near(lay["time_s"])
    return s


def templates_dir():
    return os.path.join(os.path.dirname(config.config_path()), "templates")


def list_templates():
    """{name: path} of the saved templates."""
    d = templates_dir()
    names = sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json")) \
        if os.path.isdir(d) else []
    return {n: os.path.join(d, n + ".json") for n in names}


def save_template(spec, name):
    name = "".join(c if c.isalnum() or c in "-_ ." else "_" for c in name).strip(" .")
    if not name:
        raise ValueError("give the template a name")
    path = os.path.join(templates_dir(), name + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(template(spec, name), f, indent=1)
    return path


def load_template(path):
    with open(_abs(path)) as f:
        tpl = json.load(f)
    if not isinstance(tpl, dict) or "template" not in tpl:
        raise ValueError("not a cm1view figure template")
    return tpl


_TEXT = ("letters", "time_label", "run_label", "z_label")
_SIZES = dict(tick=None, label=None, title=None, suptitle=None, legend=None)
# what each style preset changes: {spec key: value, or {sub-key: value}}; "width"
# sets the figure width (in), the height following at the same shape
STYLES = {
    "default": dict(font=dict(family="sans-serif", size=10.0, math="dejavusans", **_SIZES),
                    axes=dict(frame_lw=0.8, title_bold=True), background="white",
                    mplstyle="", **{k: dict(size=12.0, bold=True) for k in _TEXT}),
    # AMS journals: one column 3.2 in (19 pc) or two 6.5 in (39 pc); 8–9 pt lettering
    # in a sans-serif font; vector PDF or 600 DPI
    "ams": dict(font=dict(family="sans-serif", size=8.0, math="dejavusans", **_SIZES),
                axes=dict(frame_lw=0.6, title_bold=False), background="white", mplstyle="",
                export=dict(format="pdf", dpi=600), width="ams",
                letters=dict(fmt="({a})", size=9.0, bold=False),
                **{k: dict(size=8.0, bold=False) for k in _TEXT[1:]}),
    # slides (16:9): large text, thicker frames
    "talk": dict(font=dict(family="sans-serif", size=14.0, math="dejavusans", **_SIZES),
                 axes=dict(frame_lw=1.2, title_bold=True), background="white", mplstyle="",
                 export=dict(format="png", dpi=200), width=10.0,
                 **{k: dict(size=15.0, bold=True) for k in _TEXT}),
}
STYLES["dark"] = dict(STYLES["talk"], background="black", mplstyle="dark_background")


def apply_style(spec, name):
    """A copy of `spec` with style preset `name` (STYLES)."""
    s = _plain(spec)
    for k, v in STYLES[name].items():
        if k == "width":
            w0, h0 = (float(x) for x in s["size"])
            w = (3.2 if int(s.get("cols", 1)) == 1 else 6.5) if v == "ams" else float(v)
            s["size"], s["size_auto"] = [w, round(h0 * w / w0, 2)], False
        elif isinstance(v, dict):
            s[k] = dict(s.get(k) or {}, **v)
        else:
            s[k] = v
    return s


# what copy_look leaves: where a layer's data come from, and (between fields) its
# values and names
_OWN = ("type", "on", "field", "mode", "z", "spacing", "zspacing", "frame", "reduce",
        "vector", "minus", "ens", "panels", "run", "time_s", "time_lock")
_OF_FIELD = ("units", "vmin", "vmax", "levels", "threshold", "mask_below", "cbar_label",
             "cbar_ticks", "legend", "label", "ticks")


def copy_look(src, dst):
    """Layer `dst` with the look (colours, lines, style, ...) of layer `src` of the
    same type; ranges and labels too when both show the same field."""
    if src["type"] != dst["type"]:
        raise ValueError("layers of different kinds")
    skip = _OWN + (() if src.get("field") == dst.get("field") else _OF_FIELD)
    return dict(dst, **{k: v for k, v in _plain(src).items() if k not in skip})
