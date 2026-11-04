"""Version-3 figures (the document): resolve() into a version-2 spec, which is what is drawn."""

import copy

from .base import _cell, _key_layer

DOC_ONLY = ("version", "grid", "style", "kinds", "layers", "sections", "panels", "groups",
            "annotations", "notes")


def run_ids(item, f):
    """Item (a layer, its "over", or an entry) with f applied to the runs it names, in
    place: its "run" and "runs", a difference's "minus" run, an ensemble's "ens" runs.
    None stays (the panel's run; every run)."""
    def one(v):
        return None if v is None else f(v)

    def many(vs):
        return None if vs is None else [f(v) for v in vs]

    if "run" in item:
        item["run"] = one(item["run"])
    if "runs" in item:
        item["runs"] = many(item["runs"])
    if isinstance(item.get("minus"), dict) and "run" in item["minus"]:
        item["minus"] = dict(item["minus"], run=one(item["minus"]["run"]))
    if isinstance(item.get("ens"), dict) and "runs" in item["ens"]:
        item["ens"] = dict(item["ens"], runs=many(item["ens"]["runs"]))
    return item


def panel_layers(doc, p):
    """Panel p's layers written out: [(its shared layer's id or None, the layer)]."""
    out = []
    for item in p.get("layers") or []:
        if "ref" not in item:
            out.append((None, copy.deepcopy(item)))
        elif item["ref"] in (doc.get("layers") or {}):
            out.append((item["ref"], dict(copy.deepcopy(doc["layers"][item["ref"]]),
                                          **copy.deepcopy(item.get("over") or {}))))
    return out


def _legend_at(lg, ids):
    """Legend settings lg with its panels (ids) as places among the panels `ids`."""
    return dict(lg, panel=ids.index(lg["panel"]) if lg.get("panel") in ids else 0,
                panels=[ids.index(i) for i in lg.get("panels") or [] if i in ids])


def _key_at(ck, doc):
    """Contour key settings with the layer it speaks for: ck["lay"], or written out from
    its shared layer (blank: the first contour layer that is on)."""
    if not ck.get("on") or ck.get("lay"):
        return ck
    ids = list(doc.get("layers") or {})
    lays = [doc["layers"][i] for i in ids]
    at = ids.index(ck["layer"]) if ck.get("layer") in ids else -1
    return dict(ck, layer=at, lay=copy.deepcopy(_key_layer(dict(ck, layer=at), lays)))


def inset_items(p):
    """The layer items of panel p's insets with layers of their own."""
    return [item for ins in p.get("insets") or [] for item in ins.get("layers") or []]


def _resolved_inset(doc, ins, at):
    """An inset as version 2 has it: its own layers written out, None for the panel's."""
    out = copy.deepcopy(ins)
    if ins.get("layers") is not None:
        out["layers"] = [run_ids(lay, at) for _, lay in panel_layers(doc, ins)]
    return out


def inset_panel(q, ins):
    """Inset `ins` of version-2 panel q as a panel of its own, which is how its arrays are read and
    how it is drawn: the panel, with its layers unless the inset has others and its settings
    unless the inset has others (its own area), keyed by the negative of the inset's id."""
    out = {k: v for k, v in q.items() if k != "insets"}
    opts = copy.deepcopy(q.get("opts") or {})
    for key, val in (ins.get("opts") or {}).items():
        opts[key] = dict(opts[key], **val) if isinstance(val, dict) and \
            isinstance(opts.get(key), dict) else copy.deepcopy(val)
    out.update(id=-int(ins["id"]), title="")
    if ins.get("layers") is not None:
        out["layers"] = ins["layers"]
    if opts:
        out["opts"] = opts
    return out


def panel_or_inset(res, pid):
    """The version-2 panel of id pid, or as a panel the inset whose key it is (inset_panel)."""
    for q in res["panels"]:
        if q["id"] == pid:
            return q
        for ins in q.get("insets") or []:
            if -int(ins["id"]) == pid:
                return inset_panel(q, ins)
    raise KeyError(pid)


def resolve(doc):
    """The version-2 spec of document `doc` (the figure settings, style and kinds' settings
    side by side; a kind's settings another kind has otherwise: in its panels' opts; shared
    layers and overrides written out; run ids as indices; legend panels as places)."""
    out = {k: copy.deepcopy(v) for k, v in doc.items() if k not in DOC_ONLY}
    out.update(copy.deepcopy(doc.get("style") or {}))
    out["annotations"] = copy.deepcopy(doc.get("annotations") or [])
    runs = out.get("runs") or []
    index = {r["id"]: k for k, r in enumerate(runs)}

    def at(v):  # (a run no longer in the figure: past the end, "no such run")
        return index.get(v, len(runs))

    kinds = doc.get("kinds") or {}
    pans = sorted(doc.get("panels") or [], key=lambda p: _cell(p)[:2])
    for p in pans:
        for key, val in (kinds.get(p["kind"]) or {}).items():
            out.setdefault(key, copy.deepcopy(val))
    secs = list(doc.get("sections") or {})
    panels = []
    ex = out.get("extremes") or {}
    ex_at = None
    for p in pans:
        q = {k: copy.deepcopy(v) for k, v in p.items() if k not in ("layers", "over", "insets")}
        q["block"] = 0
        q["run"] = None if p.get("run") is None else at(p["run"])
        refs = panel_layers(doc, p)
        q["layers"] = [run_ids(lay, at) for _, lay in refs]
        opts = {}
        for key, val in (kinds.get(p["kind"]) or {}).items():
            if out.get(key) != val:
                opts[key] = copy.deepcopy(val)
        for key, val in (p.get("opts") or {}).items():
            opts[key] = dict(opts[key], **val) if isinstance(val, dict) and \
                isinstance(opts.get(key), dict) else copy.deepcopy(val)
        if ex.get("on") and p["kind"] in ("plan", "xsec"):  # (a layer: its place in the panel)
            lid = dict(ex, **opts.get("extremes", {})).get("layer")
            ids = [i for i, _ in refs]
            place = ids.index(lid) if lid in ids else -1
            ex_at = place if ex_at is None else ex_at
            if place != ex_at or "extremes" in opts:
                opts["extremes"] = dict(opts.get("extremes", {}), layer=place)
        if opts:
            q["opts"] = opts
        else:
            q.pop("opts", None)
        if p.get("section") is not None:
            q["section"] = secs.index(p["section"]) if p["section"] in secs else 0
        if p.get("insets"):
            q["insets"] = [_resolved_inset(doc, ins, at) for ins in p["insets"]]
        panels.append(q)
    if "extremes" in out:
        out["extremes"] = dict(ex, layer=-1 if ex_at is None else ex_at)
    ids = [p["id"] for p in pans]
    if isinstance(out.get("legend"), dict):
        out["legend"] = _legend_at(out["legend"], ids)
    if isinstance(out.get("contour_key"), dict):
        out["contour_key"] = _key_at(out["contour_key"], doc)
    groups = copy.deepcopy(doc.get("groups") or {})
    for name, g in groups.items():
        if isinstance(g.get("legend"), dict):
            g["legend"] = _legend_at(g["legend"], [p["id"] for p in pans if p.get("group") == name])
        if isinstance(g.get("contour_key"), dict):
            g["contour_key"] = _key_at(g["contour_key"], doc)
    if groups:
        out["groups"] = groups
    grid = doc.get("grid") or {}
    block = dict(rows=int(grid.get("rows", 1)), cols=int(grid.get("cols", 1)))
    block.update({k: grid[k] for k in ("widths", "heights") if grid.get(k)})
    out.update(version=2, arrange="row", blocks=[block], panels=panels)
    return out
