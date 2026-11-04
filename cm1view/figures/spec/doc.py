"""The figure document (version 3), the editor's one source of truth:

  size, export, suptitle, background, code, made_with    the figure's own
  grid      {rows, cols, widths, heights}
  runs      [{id, path, label, color, t0_min, track, ...}]
  style     fonts, letters, labels, spacing, colorbar, legend, ...
  kinds     {kind: its settings}, e.g. plan: {axes, domain, coords, xsec}, sounding: {axes, skewt}
  layers    {id: settings}, the shared layers
  sections  {id: geometry}
  groups    {name: {colorbar, legend, contour_key, axes}}, what a group of panels has apart
            from the others (a converted figure of parts: one group per part)
  panels    [{id, kind, cell [row, col, rowspan, colspan], run, time_s, z, zmode, title,
            rowlabel, letter, opts, layers, section, group, insets}]
            insets [{id, loc, size, x, y, h, opts, view, layers, mark, connect, color, lw, ls,
            ticks}]: zoom insets of a plan view or cross-section, its arrays under the negative
            of the id (ids are the whole document's; draw.figure's inset_rect has the place);
            layers: as a panel's, or none for the panel's; opts: over the panel's (a plan view's
            area: domain, coords; domain may have "off", its centre from the storm's); view: a
            cross-section's [x0, x1, z0, z1]; mark, connect: the box in the panel, and the lines
  annotations  [{..., panel: id, or a list of ids, or -1 for every panel}]
  notes     what a conversion could not carry over (text for the user)

A panel's layers are {ref: id, over: {keys}} or a whole layer of its own; soundings, series,
distributions, ... are layers of their own.  A panel's z and zmode are its height label: the
heights of its layers are in the layers.  Look resolves style, then kinds[kind], then the
panel's opts (a plan view's own area: opts {domain: {...}, coords}, merged over the kind's).  A
panel's letter is blank for its place in reading order.  Panel ids are
integers (the keys of the plotted arrays, in saved .npz files too); ids never change, so
nothing is renumbered when a panel, layer or run moves or goes.

to_doc converts a version-1 figure (a figure of parts: onto one grid); figdraw.resolve makes
the version-2 spec drawn from a document; one_panel makes the one-panel version-1 spec that
FigureData reads a panel's arrays with, so its caches stay as they are."""

import copy
import json

from .. import draw as figdraw
from .base import is_doc, normalize, renewed  # noqa: F401  (is_doc: fg.is_doc)
from .sections import card_section, panel_section, sections

FIGURE_KEYS = ("size", "size_auto", "size_set", "suptitle", "export", "background", "code",
               "made_with", "template")
KIND_KEYS = {"plan": ("axes", "domain", "coords", "xsec"),
             "xsec": ("axes", "domain", "coords", "xsec"),
             "th": ("axes", "ts"), "line": ("axes", "ts"), "sounding": ("axes", "skewt"),
             "dist": ("axes", "dist"), "profile": ("axes", "prof"),
             "joint": ("axes", "joint"), "azim": ("axes", "azim"),
             "table": ("axes", "table", "skewt"), "scene": ("axes", "scene3d")}
ANY_KIND_KEYS = {k for keys in KIND_KEYS.values() for k in keys}
GROUP_KEYS = ("colorbar", "legend", "contour_key")
NOT_STYLE = set(figdraw.V1_PANEL_KEYS) | set(FIGURE_KEYS) | ANY_KIND_KEYS | {
    "arrange", "parts", "share", "place", "part_grid", "runs", "sections", "annotations",
    "profiles", "joints", "azims", "tables"}
MAPPED = ("plan", "xsec")  # (the kinds whose panels have shared layers and sections)


def _copy(v):
    return json.loads(json.dumps(v, default=float))


class _Builder:
    """A document being filled from the parts of a figure, one part at a time."""

    def __init__(self, spec):
        self.doc = dict(version=3, runs=[], style={}, kinds={}, layers={}, sections={},
                        panels=[], annotations=[])
        self.doc.update({k: _copy(spec[k]) for k in FIGURE_KEYS if k in spec})

    def run_id(self, entry, alike):
        """The id of a run entry, a new one (alike: or that of an entry alike already there)."""
        for r in self.doc["runs"] if alike else []:
            if {k: v for k, v in r.items() if k != "id"} == entry:
                return r["id"]
        rid = f"r{len(self.doc['runs'])}"
        self.doc["runs"].append(dict(_copy(entry), id=rid))
        return rid

    def section_id(self, sec):
        """The id of a section's geometry (one alike already there, else a new one)."""
        geom = _copy(card_section(sec))
        for sid, s in self.doc["sections"].items():
            if s == geom:
                return sid
        sid = f"s{len(self.doc['sections'])}"
        self.doc["sections"][sid] = geom
        return sid

    def layer_ids(self, layers):
        """The ids of a part's shared layers: one alike that another part has, else new."""
        out = []
        for lay in layers:
            own = _copy({k: v for k, v in lay.items() if k != "panels"})
            have = next((i for i, x in self.doc["layers"].items()
                         if x == own and i not in out), None)
            if have is None:
                have = f"l{len(self.doc['layers'])}"
                self.doc["layers"][have] = own
            out.append(have)
        return out


def _layers_of(q, base, ids):
    """Version-2 panel q's map layers as references to the shared layers `base` (`ids`,
    before any run is mapped), each with what differs in this panel; layers beyond them: its
    own."""
    out = []
    for j, lay in enumerate(q["layers"]):
        lay = {k: v for k, v in lay.items() if k != "panels"}
        if j >= len(ids):
            out.append(lay)
            continue
        shared = base[j]
        over = {k: v for k, v in lay.items() if k not in shared or shared[k] != v}
        out.append(dict(ref=ids[j], over=over))
    return out


def _part_doc(b, part, k, combo, rect, edges):
    """Part k of a figure (rect: where it goes, edges: maps it onto the document's grid)
    into builder b."""
    kind, doc = part.get("kind", "plan"), b.doc
    runs = part.get("runs") or []
    rids = []
    for n, r in enumerate(runs):
        entry = _copy(r)
        if combo:  # (runs are renumbered: keep their look)
            entry.setdefault("color", figdraw.run_color(part, n))
            entry.setdefault("ls", figdraw.run_style(part, n))
        rids.append(b.run_id(entry, combo))

    def rid(v):
        return rids[int(v)] if 0 <= int(v) < len(rids) else "gone"

    mapped = kind in MAPPED
    base = part.get("layers") or []
    ids = b.layer_ids(base) if mapped else []
    if mapped:
        for lid in ids:
            figdraw.run_ids(doc["layers"][lid], lambda v: v if isinstance(v, str) else rid(v))
    secs = [b.section_id(s) for s in sections(part)] if mapped else []
    settings = _settings_of(part, kind, ids)

    style = settings["style"]
    group = None
    if combo:
        group = f"part{k}"
        kept = {key: style.pop(key) for key in GROUP_KEYS if key in style}
        kept["axes"] = _copy(settings["kind"].get("axes", {}))
        if isinstance(kept.get("contour_key"), dict):
            kept["contour_key"] = _key_within(kept["contour_key"], rect)
        kept["colorbar"] = _part_colorbar(kept.get("colorbar") or {})
        doc.setdefault("groups", {})[group] = kept
    for key, val in style.items():
        doc["style"].setdefault(key, val)
    have = doc["kinds"].setdefault(kind, {})
    for key, val in settings["kind"].items():
        have.setdefault(key, val)
    # (what this part has otherwise than the document: its panels' opts)
    differs = {key: val for key, val in style.items() if doc["style"].get(key) != val}
    differs.update({key: val for key, val in settings["kind"].items() if have.get(key) != val})
    if combo and len(runs) == 1 and "run_label" in style:  # (its one run: unnamed)
        differs["run_label"] = dict(style["run_label"], on=False)

    before = sum(figdraw.npanels(p) for p in edges["parts"][:k])
    placed = []
    for i in range(figdraw.npanels(part)):
        q = figdraw._v1_panel(part, i)
        if q is None:
            continue
        pid = k * 1000 + i if combo else i
        r, c = q["cell"][:2]
        p = dict(id=pid, kind=kind, cell=edges["cell"](k, r, c), run=None, time_s=q["time_s"],
                 title=q["title"], layers=[], insets=[])
        if q["run"] is not None:
            p["run"] = rid(q["run"])
        for key in ("z", "zmode", "rowlabel"):
            if key in q:
                p[key] = q[key]
        opts = _copy(q.get("opts") or {})
        for key, val in differs.items():
            opts[key] = dict(val, **opts[key]) if isinstance(val, dict) and \
                isinstance(opts.get(key), dict) else _copy(val)
        if opts:
            p["opts"] = opts
        if mapped:
            p["layers"] = _layers_of(q, base, ids)
            p["section"] = secs[panel_section(part, i)[0]]
        else:
            p["layers"] = _copy(q["layers"])
        for item in p["layers"]:
            target = item.get("over", item) if "ref" in item else item
            figdraw.run_ids(target, rid)
        if group:
            p["group"] = group
        p["letter"] = before + i
        doc["panels"].append(p)
        placed.append(pid)
    lg = (doc["groups"][group] if combo else doc["style"]).get("legend")
    if isinstance(lg, dict) and placed:  # (panels by id, not by place among them)
        lg.update(panel=placed[min(max(int(lg.get("panel", 0)), 0), len(placed) - 1)],
                  panels=[placed[int(n)] for n in lg.get("panels") or []
                          if 0 <= int(n) < len(placed)])
    for a in _copy(part.get("annotations") or []):
        panel = a.get("panel", -1)
        if combo:
            on = figdraw._part_panels(k, panel)
            a["panel"] = list(placed) if on == -1 else on  # (every panel of the part)
        doc["annotations"].append(a)


def _settings_of(part, kind, ids):
    """{"style": ..., "kind": ...} of a part: its settings by where they go, with the layer
    its extremes and contour key speak for as an id."""
    keys = KIND_KEYS.get(kind, ("axes",))
    style = {k: _copy(v) for k, v in part.items() if k not in NOT_STYLE}
    own = {k: _copy(part[k]) for k in keys if k in part}
    ex = style.get("extremes")
    if isinstance(ex, dict):
        at = int(ex.get("layer", -1))
        ex["layer"] = ids[at] if 0 <= at < len(ids) else -1
    ck = style.get("contour_key")
    if isinstance(ck, dict):
        at = int(ck.get("layer", -1))
        ck["layer"] = ids[at] if 0 <= at < len(ids) else -1
        if ck.get("on") and not ids:  # (a kind without shared layers: its key's layer now)
            ck.pop("layer")
            ck["lay"] = _copy(figdraw._key_layer(_copy(part["contour_key"]),
                                                 part.get("layers") or []))
    return dict(style=style, kind=own)


def _part_colorbar(cb):
    """A part's colorbar settings, as block_view takes them."""
    return dict(cb, mode="shared") if cb.get("mode") in ("parts", "figure") else cb


def _key_within(ck, rect):
    """Contour key settings of a part at `rect` (x0, x1, y0, y1: fractions of the figure, y
    from the bottom), as fractions of the figure."""
    x0, x1, y0, y1 = rect
    return dict(ck, x=x0 + float(ck.get("x", 0.01)) * (x1 - x0),
                y=y0 + float(ck.get("y", 0.01)) * (y1 - y0),
                size=float(ck.get("size", 0.1)) * min(x1 - x0, y1 - y0))


def _part_rects(spec):
    """Where each part of a figure of parts goes: [(x0, x1, y0, y1)], fractions of the
    figure with y down from the top."""
    parts = spec["parts"]
    if spec.get("arrange") == "grid":
        g = figdraw.grid_layout(parts, spec.get("part_grid"))
        w, h = [float(v) for v in g["width_ratios"]], [float(v) for v in g["height_ratios"]]
        out = []
        for r, c, rs, cs in g["places"]:
            out.append((sum(w[:c]) / sum(w), sum(w[:c + cs]) / sum(w),
                        sum(h[:r]) / sum(h), sum(h[:r + rs]) / sum(h)))
        return out
    shares = [float(v) for v in figdraw.part_shares(spec)]
    total, at, out = sum(shares), 0.0, []
    for s in shares:
        a, b = at / total, (at + s) / total
        at += s
        out.append((a, b, 0.0, 1.0) if spec.get("arrange", "row") == "row" else (0.0, 1.0, a, b))
    return out


def _edges(parts, rects):
    """(columns, rows, cell): the sizes of the one grid every part's rows and columns fit on
    (between every edge of any of them) and cell(part, row, col) -> [row, col, rowspan,
    colspan] on it."""
    def sides(a, b, n):
        return [round(a + (b - a) * j / n, 6) for j in range(n + 1)]

    xs, ys = set(), set()
    for p, (x0, x1, y0, y1) in zip(parts, rects):
        rows, cols = _shape(p)
        xs.update(sides(x0, x1, cols))
        ys.update(sides(y0, y1, rows))
    xs, ys = sorted(xs), sorted(ys)

    def cell(k, r, c):
        rows, cols = _shape(parts[k])
        x0, x1, y0, y1 = rects[k]
        ex, ey = sides(x0, x1, cols), sides(y0, y1, rows)
        a, b = ys.index(ey[r]), xs.index(ex[c])
        return [a, b, ys.index(ey[r + 1]) - a, xs.index(ex[c + 1]) - b]

    return ([round(b - a, 6) for a, b in zip(xs, xs[1:])],
            [round(b - a, 6) for a, b in zip(ys, ys[1:])], cell)


def _shape(part):
    """(rows, cols) of a part, as it is drawn (a 3D scene is one picture)."""
    return (1, 1) if part.get("kind") == "scene" else (int(part["rows"]), int(part["cols"]))


def to_doc(form, run=None):
    """The document of a version-1 figure (a copy).  run: for an older spec with its times
    as output indices or without runs (normalize).  A figure of parts goes onto one grid, a
    group of panels per part: each keeps its panels' settings, colorbar, legend and tick
    labels, but where its panels sit can shift a little, as the grid's gaps are the whole
    figure's now, and a part's own title or code goes into notes.  ValueError: no version 1."""
    spec = _copy(form)
    if int(spec.get("version", 1)) != 1:
        raise ValueError("to_doc: not a version-1 figure")
    if run is not None:
        normalize(spec, run)
    else:
        renewed(spec)
    combo = spec.get("kind") == "combo"
    parts = spec["parts"] if combo else [spec]
    b = _Builder(spec)
    if combo:
        rects = _part_rects(spec)
        widths, heights, cell = _edges(parts, rects)
        grid = dict(rows=len(heights), cols=len(widths), widths=widths, heights=heights)
    else:
        rects = [(0.0, 1.0, 0.0, 1.0)]
        rows, cols = _shape(spec)
        grid = dict(rows=rows, cols=cols)

        def cell(k, r, c):
            return [r, c, 1, 1]
    b.doc["grid"] = grid
    notes = []
    edges = dict(parts=parts, cell=cell)
    for k, part in enumerate(parts):
        x0, x1, y0, y1 = rects[k]
        _part_doc(b, part, k, combo, (x0, x1, 1.0 - y1, 1.0 - y0), edges)
        if combo and part.get("suptitle"):
            notes.append(f"Part {k + 1}'s title was left out: {part['suptitle']}")
        if combo and (part.get("code") or {}).get("on"):
            notes.append(f"Part {k + 1}'s own code was left out.")
    doc = b.doc
    if combo:
        doc["style"].update({k: _copy(spec[k]) for k in ("font", "mplstyle", "spacing")
                             if k in spec and k not in doc["style"]})
        top = spec.get("colorbar") or {}
        doc["style"]["colorbar"] = _copy(top) if top.get("mode") == "figure" else dict(mode="groups")
        if top.get("mode") == "figure":
            doc["style"]["colorbar"]["mode"] = "shared"
            for g in doc.get("groups", {}).values():
                g.pop("colorbar", None)
    doc["panels"].sort(key=lambda p: tuple(p["cell"][:2]))
    for n, p in enumerate(doc["panels"]):  # (blank: its place in reading order)
        if p["letter"] == n:
            del p["letter"]
    if notes:
        doc["notes"] = notes
    return doc


def ann_panels(a):
    """The ids an annotation names: [-1] for every panel."""
    p = a.get("panel", -1)
    return [int(q) for q in p] if isinstance(p, (list, tuple)) else [int(p)]


def drop_annotations(doc, gone):
    """Panels `gone` are no longer in the figure: what names only them goes with them (a later
    panel can take a freed id, and must not inherit it); the others lose them."""
    keep = []
    for a in doc.get("annotations") or []:
        ids = ann_panels(a)
        left = [i for i in ids if i not in gone]
        if left != ids:
            if not left:
                continue
            a["panel"] = left[0] if len(left) == 1 else left
        keep.append(a)
    if doc.get("annotations"):
        doc["annotations"] = keep


def one_panel(doc, p, res=None):
    """The one-panel version-1 spec of panel p (a document's, or its id, or an inset's key)
    that FigureData reads its arrays with: all the panel's settings, the panel's layers written out, and
    every run of the document, so a run's number is the same as in the panel.  res:
    figdraw.resolve(doc) if at hand."""
    res = figdraw.resolve(doc) if res is None else res
    pid = p["id"] if isinstance(p, dict) else p
    q = figdraw.panel_or_inset(res, pid)  # (an inset: read as a panel of its own)
    v = copy.deepcopy(figdraw.panel_view(res, q))
    v.update(version=1, rows=1, cols=1, panels=[], edits={}, titles=[], row_titles=[],
             panel_fills=[], panel_z=[], times_s=[], grid=dict(rows="none", cols="none", runs=[]),
             size=list(res["size"]))
    kind = q["kind"]
    geoms = [dict(s) for s in (doc.get("sections") or {}).values()]
    if kind in MAPPED:
        v["layers"] = copy.deepcopy(q["layers"])
        if q["run"] is not None:
            v["run"] = int(q["run"])
        v["time_s"] = q.get("time_s")
        at = int(q.get("section") or 0)
        if kind == "xsec":
            v["sections"] = [dict(geoms[at], run=v["run"], time_s=q["time_s"], panel=0)]
        else:
            v["sections"] = geoms
            v["edits"] = {"0": {"section": at}}
    elif kind == "th":
        v["layers"] = []
        v["runs_as"] = "cards"
        v["series"] = [dict(copy.deepcopy(lay), panel=0, runs=[int(q["run"])])
                       for lay in q["layers"]]
    elif kind == "scene":
        v.update(layers=[], run=int(q["run"]), time_s=q["time_s"])
    else:
        v[figdraw.ENTRIES[kind]] = [dict(copy.deepcopy(e), panel=0) for e in q["layers"]]
        v["layers"] = []
    return v


def share_series_range(res, data):
    """Time-height and time-series panels (of one kind and group: as a part's did) show
    their time range together (share_time_range), in place."""
    from .panels import share_time_range
    by = {}
    for q in res["panels"]:
        if q["kind"] in ("th", "line") and q["id"] in data:
            by.setdefault((q["kind"], q.get("group")), []).append(q)
    for (kind, _), qs in by.items():
        ts = figdraw.panel_view(res, qs[0]).get("ts", {})
        share_time_range(dict(kind=kind, ts=ts), {q["id"]: data[q["id"]] for q in qs})
    return data
