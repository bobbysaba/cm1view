"""A document (version 3) through time and between runs: what spec.base and spec.templates do to
a version-1 figure, done to a document.  Those functions hand a document to these, so an
animation, a template and `cm1view render` go through them unchanged.

What steps and how far is read one panel at a time through one_panel, as the data are, so a
panel's own settings (a 3D scene's opts) count; what moves is written back to the document."""

import json

import numpy as np

from .. import draw as figdraw
from .base import OutputStep, STEP_ENTRIES, _window_ends, default_spec, run_entry, time_refs
from .bundle import OLDER
from .doc import (ANY_KIND_KEYS, FIGURE_KEYS, KIND_KEYS, MAPPED, NOT_STYLE, drop_annotations,
                  one_panel)
from .templates import STYLES

TEMPLATE_RUN = "r0"  # (the one run of a template: the figure's first, on whatever it is applied to)


def plain_copy(v):
    """A copy as a file has it."""
    return json.loads(json.dumps(v, default=float))


_copy = plain_copy


def _items(p):
    """Panel p's layers as [(the dictionary its own keys are in, the whole of the item)]: of a
    reference to a shared layer, its "over"."""
    return [(item.setdefault("over", {}) if "ref" in item else item) for item in
            p.get("layers") or []]


def _scene_of(doc, p):
    """The 3D settings of scene panel p: its kind's, then its own."""
    block = dict(((doc.get("kinds") or {}).get("scene") or {}).get("scene3d") or {})
    block.update((p.get("opts") or {}).get("scene3d") or {})
    return block


def _scene_write(p, **keys):
    opts = p.setdefault("opts", {})
    opts["scene3d"] = dict(opts.get("scene3d") or {}, **keys)


def _entry_run(e, first):
    """The run an entry's times are of (ids): the first of its runs, else its run."""
    runs = e.get("runs")
    if runs:
        return runs[0]
    return e.get("run", first)


def _resolved_refs(doc, get):
    """get(one_panel's spec) for every panel, in reading order; a panel whose run or a layer's
    has gone from the figure has nothing that steps (the panel itself says it has no run)."""
    res, out = figdraw.resolve(doc), []
    for q in res["panels"]:
        try:
            out += get(one_panel(doc, q["id"], res))
        except IndexError:
            continue
    return out


def doc_time_refs(doc):
    """time_refs of a document: (run path, model time s) of what steps, first panel first."""
    return _resolved_refs(doc, time_refs)


def doc_window_ends(doc):
    return _resolved_refs(doc, _window_ends)


def doc_animated(doc):
    return any(p["kind"] in ("plan", "xsec", "scene") + STEP_ENTRIES for p in doc.get("panels") or [])


def shift_doc(doc, dt):
    """shift_times of a document: a copy with every panel's time moved by dt s (an OutputStep,
    with the runs paired by output number: by its outputs, each time in its own run).  A layer or
    entry with "time_lock" stays, and so do a table's times; series have none."""
    s = _copy(doc)
    index = {r["id"]: k for k, r in enumerate(s.get("runs") or [])}
    by_output = isinstance(dt, OutputStep) and any(r.get("outputs_s") for r in s.get("runs") or [])

    def moved(ts, rid):
        times = figdraw.output_times(s, index.get(rid, 0)) if by_output else None
        if times:
            return figdraw.output_at(times, figdraw.output_number(times, ts) + dt.n)
        return float(ts) + dt

    def layer(lay, rid):
        if lay.get("time_s") is not None and not lay.get("time_lock"):
            lay["time_s"] = moved(lay["time_s"], rid if lay.get("run") is None else lay["run"])

    shared = s.get("layers") or {}
    for p in s.get("panels") or []:
        rid, kind = p.get("run"), p["kind"]
        if kind == "scene" and p.get("time_s") is not None and "t0_s" not in _scene_of(s, p):
            _scene_write(p, t0_s=float(p["time_s"]))  # (a box following the track: from here)
        if p.get("time_s") is not None:
            p["time_s"] = moved(p["time_s"], rid)
        for item in p.get("layers") or []:
            if kind in STEP_ENTRIES:
                if not item.get("time_lock") and item.get("time_s") is not None:
                    k = _entry_run(item, (s.get("runs") or [{}])[0].get("id"))
                    item["time_s"] = moved(item["time_s"], k)
                    if item.get("time_s1") is not None:
                        item["time_s1"] = moved(item["time_s1"], k)
            elif kind in MAPPED and "ref" in item:
                over = item.get("over") or {}
                if not shared.get(item["ref"], {}).get("time_lock"):
                    layer(over, rid)
            elif kind in MAPPED:
                layer(item, rid)
    for lay in shared.values():
        layer(lay, None)
    return s


def doc_scene_frame(doc, j, n):
    """scene_frame of a document: frame j of n, each scene's camera turned by its share of its
    own orbit."""
    s = doc
    for at, p in enumerate(doc.get("panels") or []):
        if p["kind"] != "scene":
            continue
        sc = _scene_of(doc, p)
        deg = float(sc.get("orbit") or 0.0) * j / max(int(n), 1)
        if deg:
            if s is doc:
                s = dict(doc, panels=list(doc["panels"]))
            q = _copy(p)
            _scene_write(q, camera=figdraw.orbit_camera(sc.get("camera"), deg))
            s["panels"][at] = q
    return s


def doc_scene_dpi(doc, dpi):
    """A document whose 3D scenes' pictures are rendered at dpi (a preview's, a frame's)."""
    kinds = dict(doc.get("kinds") or {})
    if "scene" not in kinds and not any(p["kind"] == "scene" for p in doc.get("panels") or []):
        return doc
    scene = dict(kinds.get("scene") or {})
    kinds["scene"] = dict(scene, scene3d=dict(scene.get("scene3d") or {}, dpi=dpi))
    return dict(doc, kinds=kinds)


# ------------------------------------------------------------ templates
def _template_layer(lay, first):
    """A map layer of a template: what names another run goes, as it does in template()."""
    if lay.get("run") not in (None, first):
        lay["run"] = None
    if (lay.get("minus") or {}).get("run") not in (None, first):
        lay.pop("minus")
    if lay.get("ens"):  # (an ensemble: of the new figure's runs)
        lay["ens"] = dict(lay["ens"], runs=None)


def _template_entries(p, first):
    """A panel's entries of a template: None when nothing is left of it."""
    kind = p["kind"]
    keep = []
    for e in p.get("layers") or []:
        runs = e.get("runs")
        if kind == "th":
            if (runs or [first])[0] == first:
                keep.append(e)
        elif kind == "line":  # (a series of the first run only stays so, the others: every run)
            e["runs"] = [first] if runs == [first] else None
            keep.append(e)
        elif kind == "table":  # (of several runs: every run of the new figure)
            e["runs"], e["run"] = [first] if runs == [first] else None, first
            keep.append(e)
        elif kind == "profile" and "runs" in e and e.get("source") != "table":
            if runs is None or len(runs) > 1 or runs == [first] or e.get("run") == first:
                e["runs"], e["run"] = [first] if runs == [first] else None, first
                keep.append(e)
        elif e.get("run", first) == first:
            keep.append(e)
    return keep or None


def doc_template(doc, name=""):
    """template() of a document: its layout and look without its runs.  The first panel's run
    becomes the template's one run; a panel of another run is left out (its cell stays empty), and
    so are entries of another run, while what shows every run stays so.  Times stay relative to
    the first panel's."""
    s = _copy(doc)
    refs = doc_time_refs(s) if s.get("runs") else []
    runs = s.get("runs") or []
    first = next((r["id"] for r in runs if refs and r["path"] == refs[0][0]),
                 runs[0]["id"] if runs else TEMPLATE_RUN)
    keep, gone = [], set()
    for p in s.get("panels") or []:
        if p["kind"] in MAPPED or p["kind"] == "scene":
            ok = p.get("run") in (None, first)
        else:
            left = _template_entries(p, first)
            ok = left is not None
            if ok:
                p["layers"] = left
                p["run"] = first if p.get("run") is not None else None
        if ok:
            keep.append(p)
        else:
            gone.add(p["id"])
    s["panels"] = keep
    drop_annotations(s, gone)
    for p in keep:
        if p["kind"] in MAPPED:
            for item in _items(p):
                _template_layer(item, first)
    for lay in (s.get("layers") or {}).values():
        _template_layer(lay, first)

    def renamed(v):
        return TEMPLATE_RUN if v == first else v

    for p in keep:
        if p.get("run") is not None:
            p["run"] = renamed(p["run"])
        for item in _items(p):
            figdraw.run_ids(item, renamed)
    for lay in (s.get("layers") or {}).values():
        figdraw.run_ids(lay, renamed)
    s.pop("runs", None)
    s.pop("made_with", None)
    (s.get("style") or {}).pop("time_match", None)
    s["template"] = dict(name=name, time_s=float(refs[0][1]) if refs else _table_time(keep))
    return s


def _table_time(panels):
    """The time a figure with nothing that steps is at: its first table's first (a table's times
    move with a template, though not with an animation), else None."""
    times = [float(ts) for p in panels if p["kind"] == "table"
             for e in p.get("layers") or [] for ts in e.get("times_s") or []]
    return min(times) if times else None


def _parcel_rules(items, dt):
    """Parcels chosen as long after as before; animations keep theirs."""
    for lay in items:
        r = lay.get("rule") or {}
        if (lay.get("type") == "parcels" or lay.get("source") == "parcels") and \
                r.get("t") is not None:
            lay["rule"] = dict(r, t=float(r["t"]) + dt)


def doc_from_template(tpl, run, t):
    """from_template() of a document's template: its times moved so the first panel is at output t
    of `run`, each to the nearest output; a plan view past the run's ends is left out, its cell
    empty.  doc_defaults adds the run."""
    s = _copy(tpl)
    t0 = (s.pop("template", None) or {}).get("time_s")
    dt = 0.0 if t0 is None else float(run.times[t]) - float(t0)
    s = shift_doc(s, dt)
    tt = np.asarray(run.times, dtype=float)

    def near(ts):
        return float(tt[int(np.argmin(np.abs(tt - float(ts))))])

    def inside(ts):
        return tt[0] - 1.0 <= float(ts) <= tt[-1] + 1.0

    def layer(lay):
        if lay.get("time_s") is not None and not lay.get("time_lock"):
            lay["time_s"] = near(lay["time_s"])

    keep, gone = [], set()
    for p in s.get("panels") or []:
        kind = p["kind"]
        if p.get("time_s") is not None:
            if kind == "plan" and not inside(p["time_s"]):
                gone.add(p["id"])
                continue
            p["time_s"] = near(p["time_s"])
        for item in _items(p):
            if kind in MAPPED:
                layer(item)
            elif kind == "table":  # (shift_doc leaves a table's times)
                item["times_s"] = sorted({near(float(ts) + dt) for ts in item.get("times_s") or []})
            elif kind in STEP_ENTRIES:
                if item.get("time_s") is not None:
                    item["time_s"] = near(item["time_s"])
                if item.get("time_s1") is not None:
                    item["time_s1"] = near(item["time_s1"])
        _parcel_rules(_items(p), dt)
        for block in [(p.get("opts") or {}).get("scene3d") or {}]:
            _parcel_rules(block.get("parcels") or [], dt)
        keep.append(p)
    s["panels"] = keep
    drop_annotations(s, gone)
    for lay in (s.get("layers") or {}).values():
        layer(lay)
    _parcel_rules((s.get("layers") or {}).values(), dt)
    scene = ((s.get("kinds") or {}).get("scene") or {}).get("scene3d") or {}
    _parcel_rules(scene.get("parcels") or [], dt)
    return s


# ------------------------------------------------------------ a document from a file
def doc_defaults(doc, run, F, t=0, track=None):
    """A document read from a file (a copy), with what it lacks from this version's defaults, as
    with_defaults does for an older figure; without runs (a template), `run` with `track`."""
    d = _copy(doc)
    base = default_spec(run, F, t)
    style = d.setdefault("style", {})
    style.setdefault("label_fit", False)  # (its labels as they were)

    def filled(have, key, val):
        if isinstance(val, dict):
            have[key] = dict(_copy(val), **(have.get(key) or {}))
        else:
            have.setdefault(key, _copy(val))

    for key, val in base.items():
        if key in FIGURE_KEYS:
            filled(d, key, val)
        elif key not in NOT_STYLE and key not in ANY_KIND_KEYS:
            filled(style, key, val)
    kinds = d.setdefault("kinds", {})
    for kind in {p["kind"] for p in d.get("panels") or []}:
        have = kinds.setdefault(kind, {})
        for key in KIND_KEYS.get(kind, ()):
            if key in base:
                filled(have, key, base[key])
    for key, was in OLDER.items():  # (what would change how it looked)
        for have in [style, *kinds.values()]:
            if isinstance(have.get(key), dict):
                have[key].update({k: v for k, v in was.items() if k not in have[key]})
    if not d.get("runs"):
        d["runs"] = [dict(run_entry(run, track), id=TEMPLATE_RUN)]
    d.setdefault("layers", {})
    d.setdefault("sections", {})
    d.setdefault("annotations", [])
    return d


# ------------------------------------------------------------ a style preset
def doc_style(doc, name, width=True):
    """apply_style() of a document: style preset `name`, in the style, every kind's axes, and any
    panel or group that has such settings of its own (a converted part's: a preset sets them
    all)."""
    s = _copy(doc)
    style, kinds = s.setdefault("style", {}), s.setdefault("kinds", {})
    for key, val in STYLES[name].items():
        if key == "width":
            if width:
                w0, h0 = (float(x) for x in s["size"])
                cols = int((s.get("grid") or {}).get("cols", 1))
                w = (3.2 if cols == 1 else 6.5) if val == "ams" else float(val)
                s["size"], s["size_auto"] = [w, round(h0 * w / w0, 2)], False
            continue
        if key in FIGURE_KEYS:
            target = [s]
        elif key in ANY_KIND_KEYS:
            target = list(kinds.values()) or [kinds.setdefault("plan", {})]
        else:
            target = [style]
        for have in target:
            have[key] = dict(have.get(key) or {}, **val) if isinstance(val, dict) else val
        if isinstance(val, dict):
            for have in [*((p.get("opts") or {}) for p in s.get("panels") or []),
                         *(s.get("groups") or {}).values()]:
                if isinstance(have.get(key), dict):
                    have[key] = dict(have[key], **val)
    return s
