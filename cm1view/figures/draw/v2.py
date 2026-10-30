"""Version-2 specs: upgrade() of a version-1 spec, and the views of blocks and panels."""

import copy

from .base import FILL_KEYS, ENTRIES, part_shares

GRID_DIMS = ("runs", "sections", "times", "fields", "heights")  # (or "none")
LEGACY_VARY = {"time": "times", "field": "fields", "height": "heights", "custom": "custom"}


def xsec_cards(spec):
    """The section cards of a section figure made of them (spec["sections"] entries
    with a "panel": each one panel's section, its "run" and "time_s"; None: the
    figure's), or None (a plan view, or an older section figure: its grid)."""
    if spec.get("kind") != "xsec":
        return None
    secs = spec.get("sections") or []
    return secs if any("panel" in sec for sec in secs) else None


def xsec_card(spec, i):
    """(index, card) of the first section card drawn in panel i of a figure of cards,
    or None (none there, or its run is not one of the figure's)."""
    nr = len(spec.get("runs") or [None])
    for k, sec in enumerate(xsec_cards(spec) or []):
        if int(sec.get("panel", 0)) == i:
            return (k, sec) if 0 <= int(sec.get("run") or 0) < nr else None
    return None


def grid_axes(spec):
    """(rows, columns) of a plan-view or section figure: what each steps through,
    "runs", "sections", "times", "fields", "heights" or "none" (spec["grid"]; an older
    spec: its "vary", the panels filling the grid row by row).  With one of them
    "none" the other's panels fill the grid row by row; with both "none" every panel
    is alike (but for its panel edits)."""
    g = spec.get("grid") or {}
    if g.get("rows") or g.get("cols"):
        return g.get("rows") or "none", g.get("cols") or "none"
    vary = spec.get("vary", "time")
    if vary == "grid":
        return ("runs", "times") if spec.get("runs_as", "rows") == "rows" else ("times", "runs")
    return "none", LEGACY_VARY.get(vary, "times")


def grid_runs(spec):
    """The run indices a grid of runs steps through (spec["grid"]["runs"]; blank:
    every run of the figure)."""
    nr = len(spec.get("runs") or [None])
    ks = [int(k) for k in (spec.get("grid") or {}).get("runs") or [] if 0 <= int(k) < nr]
    return ks or list(range(nr))


def dim_items(spec, d):
    """What each step of grid dimension d gives its panels (a dict of "run",
    "time_s", "fill", "z" and "section"; None: an empty cell)."""
    nr = len(spec.get("runs") or [None])
    if d == "runs":
        return [dict(run=k) for k in grid_runs(spec)]
    if d == "times":
        return [None if t is None else dict(time_s=float(t)) for t in spec.get("times_s") or []]
    if d == "fields":
        return [dict(fill=pf) for pf in spec.get("panel_fills") or []]
    if d == "heights":
        return [None if z is None else dict(z=float(z)) for z in spec.get("panel_z") or []]
    if d == "sections":
        return [dict(section=k) for k in range(len(spec.get("sections") or [None]))]
    if d == "custom":  # (an older spec: a run and time per panel)
        return [dict(run=int(p["run"]), time_s=float(p["time_s"])) if int(p["run"]) < nr
                else None for p in spec.get("panels", [])]
    return []


def grid_cell(spec, i):
    """What panel i of a plan-view or section figure takes from its row and column
    (grid_axes, dim_items: a dict, {} for nothing), or None for an empty cell.  A
    figure of fields or heights without any yet draws its one panel as it is.  A
    section figure of cards: {} where a card is, else None."""
    if xsec_cards(spec) is not None:
        return {} if xsec_card(spec, i) is not None else None
    rd, cd = grid_axes(spec)
    if rd != "none" and cd != "none":
        r, c = divmod(i, int(spec["cols"]))
        idx = ((rd, r), (cd, c))
    else:
        idx = tuple((d, i) for d in (rd, cd) if d != "none")
    out = {}
    for d, j in idx:
        items = dim_items(spec, d)
        if not items and d in ("fields", "heights"):
            continue
        if j >= len(items) or items[j] is None:
            return None
        out.update(items[j])
    return out


def z_text(spec, i):
    """The height label of panel i of a figure with a row or column of heights
    (spec["z_label"]; {z}: the height in km, {k}: the model level), or "" for none."""
    z = (grid_cell(spec, i) or {}).get("z")
    if z is None:
        return ""
    level = spec.get("panel_zmode", "height") == "level"
    fmt = spec.get("z_label", {}).get("fmt") or ("k = {k}" if level else "z = {z:g} km")
    return fmt.format(z=float(z), k=int(round(float(z))))


def npanels(spec):
    """Number of panel slots (grid cells; empty ones are hidden)."""
    if spec.get("kind") == "combo":
        return sum(npanels(p) for p in spec["parts"])
    cells = int(spec["rows"]) * int(spec["cols"])
    kind = spec.get("kind", "plan")
    if kind == "scene":  # (one 3D scene)
        n = 1
    elif kind == "th" and th_cards(spec):
        n = 1 + max([int(e.get("panel", 0)) for e in spec.get("series") or []] or [0])
    elif kind == "th":
        n = cells
    elif kind in ENTRIES or xsec_cards(spec) is not None:
        ents = spec.get(ENTRIES.get(kind, "sections"), [])
        n = 1 + max([int(e.get("panel", 0)) for e in ents] or [0])
    else:
        dims = [d for d in grid_axes(spec) if d != "none"]
        if len(dims) == 1:  # (one list filling the grid row by row)
            n = len(dim_items(spec, dims[0]))
            if dims[0] in ("fields", "heights"):
                n = max(1, n)
        else:
            n = cells
    return min(n, cells)


def th_cards(spec):
    """Whether a time-height figure is made of cards (spec["runs_as"] "cards"): each
    series entry one panel's, at its "panel" with its one run ("runs" [k]); else (an
    older figure) a panel per series and run (th_grid)."""
    return spec.get("kind") == "th" and spec.get("runs_as") == "cards"


def th_grid(spec):
    """(rows, cols, cells) of a time-height figure: a panel per series and run of that
    series (its "runs"; blank: every run of the figure).  The runs any series uses are
    the columns (runs_as "cols", rows the series) or the rows; cells lists (run index,
    series index) row by row, None where a series skips that run.  A figure of cards
    (th_cards): its rows and columns, each panel the first card with its number (None:
    no card there, or its run is not one of the figure's)."""
    nr, ents = len(spec.get("runs") or [None]), spec.get("series", [])
    if th_cards(spec):
        r, c = int(spec["rows"]), int(spec["cols"])
        cells, seen = [None] * (r * c), set()
        for e, ent in enumerate(ents):
            p, k = int(ent.get("panel", 0)), int((ent.get("runs") or [0])[0])
            if p in seen or not 0 <= p < r * c or ent.get("source") == "table":
                continue
            seen.add(p)
            cells[p] = (k, e) if 0 <= k < nr else None
        return r, c, cells
    own = [[int(k) for k in (e.get("runs") or range(nr)) if 0 <= int(k) < nr]
           or list(range(nr)) for e in ents]
    ks = sorted({k for ks in own for k in ks}) or [0]
    by_cols = spec.get("runs_as", "cols") == "cols"
    cells = []
    for a in range(len(ents) if by_cols else len(ks)):
        for b in range(len(ks) if by_cols else len(ents)):
            e, j = (a, b) if by_cols else (b, a)
            cells.append((ks[j], e) if ks[j] in own[e] else None)
    n = max(1, len(ents))
    return (n, len(ks), cells) if by_cols else (len(ks), n, cells)


def series_ref(spec, i):
    """(run index, series entry index) of time-height panel i, or None (an empty cell);
    see th_grid."""
    cells = th_grid(spec)[2]
    return cells[i] if i < len(cells) else None


def spec_layers(spec, i):
    """Layers of panel i: the shared layers, with the fill of the panel's row or
    column of fields (grid_cell) replacing the first fill layer, and in a row or
    column of heights the panel's height (spec["panel_z"], km) for the layers at a
    height (but those with "z_fixed"), or with spec["panel_zmode"] "level" the
    panel's model level for the layers at a height or level (time-height panels: the fill of the panel's series).  A layer
    with a "panels" list is off in the other panels (so layer j stays layer j
    everywhere)."""
    if spec.get("kind") == "th":
        ref = series_ref(spec, i)
        if ref is None:
            return []
        e = spec["series"][ref[1]]
        return [dict({k: e[k] for k in FILL_KEYS if k in e}, type="fill", on=True)]
    layers = [dict(lay) if not lay.get("panels") or i in lay["panels"] else
              dict(lay, on=False) for lay in spec["layers"]]
    cell = grid_cell(spec, i) or {}
    if cell.get("z") is not None:
        z = float(cell["z"])
        level = spec.get("panel_zmode", "height") == "level"
        for j, lay in enumerate(layers):
            if lay.get("z_fixed") or "z" not in lay:
                continue
            mode = lay.get("mode", "height")
            if level and (lay["type"] == "vectors" or mode in ("height", "level")):
                layers[j] = dict(lay, mode="level", z=float(round(z)))
            elif not level and (lay["type"] == "vectors" or mode == "height"):
                layers[j] = dict(lay, z=z)
    if cell.get("fill"):
        for j, lay in enumerate(layers):
            if lay["type"] == "fill":
                layers[j] = dict(lay, **cell["fill"])
                break
    return edited_layers(layers, panel_edit(spec, i))


def panel_edit(spec, i):
    """The changes made to panel i alone (spec["edits"][str(i)], the panel tree): its
    "run", "time_s", "z" (km), "title", "xlabel", "ylabel" (" ": none), "layers"
    ({str(j): the keys layer j has in this panel only, its own "run", "time_s" and "z"
    among them}), "extra" (layers of this panel only, drawn after the others),
    "legend" (its own legend: legend_opts) and "section" (the index of its
    cross-section in spec["sections"])."""
    return (spec.get("edits") or {}).get(str(i)) or {}


def edited_layers(layers, e):
    """Layers with panel edit e: its height for the layers at a height (but those with
    "z_fixed" or a height of their own), then each layer's own keys, then its extra
    layers."""
    if not e:
        return layers
    out = []
    for j, lay in enumerate(layers):
        own = (e.get("layers") or {}).get(str(j)) or {}
        if e.get("z") is not None and "z" not in own and "z" in lay and \
                not lay.get("z_fixed") and (lay["type"] == "vectors" or
                                            lay.get("mode", "height") == "height"):
            lay = dict(lay, z=float(e["z"]))
        out.append(dict(lay, **own) if own else lay)
    return out + [dict(lay) for lay in e.get("extra") or []]


def panel_ref(spec, i):
    """(run index, model time in s) of panel i of a version-1 spec, or None for an
    empty grid cell: as its layout says (form_ref), or as changed in this panel alone
    (panel_edit)."""
    ref = form_ref(spec, i)
    e = panel_edit(spec, i)
    if ref is None or not e:
        return ref
    k = int(e["run"]) if e.get("run") is not None and \
        int(e["run"]) < len(spec.get("runs") or [None]) else ref[0]
    return k, float(e["time_s"]) if e.get("time_s") is not None else ref[1]


def form_ref(spec, i):
    """(run index, model time in s) of panel i as the layout says, or None for an
    empty cell: the run and time of its row or column (grid_cell), else the figure's
    one run (spec["run"]) and time (spec["time_s"]); a section figure of cards: the
    panel's card's run and time (blank: the figure's time)."""
    if xsec_cards(spec) is not None:
        kc = xsec_card(spec, i)
        if kc is None:
            return None
        ts = kc[1].get("time_s")
        return int(kc[1].get("run") or 0), float(spec["time_s"] if ts is None else ts)
    cell = grid_cell(spec, i)
    if cell is None:
        return None
    return (int(cell["run"]) if "run" in cell else int(spec.get("run", 0)),
            float(cell["time_s"]) if "time_s" in cell else float(spec["time_s"]))


V1_PANEL_KEYS = ("version", "kind", "rows", "cols", "vary", "times", "time", "times_s",
                 "time_s", "panel_fills", "panel_z", "panel_zmode", "layers", "run",
                 "runs_as", "panels", "grid", "titles", "row_titles", "series", "soundings",
                 "dists", "edits",
                 "form")
FIG_ONLY = ("version", "kind", "arrange", "parts", "blocks", "panels", "size", "size_set",
            "size_auto", "share", "suptitle", "export", "made_with", "code")
EXTENDS = ("auto", "neither", "min", "max", "both")


def _part_panels(k, p):
    """An annotation's panel(s) p in part k of a figure of parts, as keys of the whole
    figure (k * 1000 + panel; -1, every panel, as it is)."""
    if isinstance(p, (list, tuple)):
        return -1 if -1 in [int(q) for q in p] else [k * 1000 + int(q) for q in p]
    return -1 if int(p) == -1 else k * 1000 + int(p)


def upgrade(spec, data=None):
    """(version-2 spec, data) of a version-1 spec or a figure of parts (a version-2
    spec comes back as it is): each panel written out with its own layers (the
    shared layers as the panel had them, its height, fill, title and letter), each
    part a block with its settings, and in `data` (a copy; None: none) each line's and
    sounding's entry counted within its panel."""
    if int(spec.get("version", 1)) >= 2:
        return spec, data
    combo = spec.get("kind") == "combo"
    parts = spec["parts"] if combo else [spec]
    out = {k: copy.deepcopy(v) for k, v in spec.items() if k not in V1_PANEL_KEYS + ("parts",)}
    out.update(version=2, arrange=spec.get("arrange", "row"))
    data = None if data is None else dict(data)
    blocks, panels, start = [], [], 0
    for k, part in enumerate(parts):
        b = dict(rows=int(part["rows"]), cols=int(part["cols"]))
        ck = None
        if combo:
            opts = {key: copy.deepcopy(v) for key, v in part.items() if key not in V1_PANEL_KEYS}
            opts["annotations"] = [dict(a, panel=_part_panels(k, a.get("panel", -1)))
                                   for a in opts.get("annotations", [])]
            b.update(share=part.get("share"), size=list(part["size"]), opts=opts)
            ck = opts.get("contour_key")
        else:
            ck = out.get("contour_key")
        if ck and ck.get("on"):
            ck["lay"] = copy.deepcopy(_key_layer(ck, part.get("layers", [])))
        blocks.append(b)
        n = npanels(part)
        for i in range(n):
            p = _v1_panel(part, i)
            if p is None:
                continue
            key = k * 1000 + i if combo else i
            p.update(id=key, block=k, letter=i + start)
            panels.append(p)
            if data is not None and key in data:
                data[key] = _local_entries(part, i, data[key])
        start += n
    out.update(blocks=blocks, panels=panels)
    return out, data


def _v1_panel(spec, i):
    """Panel i of a version-1 spec as a version-2 panel (None: an empty cell)."""
    kind = spec.get("kind", "plan")
    r, c = divmod(i, int(spec["cols"]))
    titles = spec.get("titles") or []
    p = dict(kind=kind, cell=[r, c, 1, 1], run=None, time_s=None,
             title=titles[i] if i < len(titles) and titles[i] else "", layers=[])
    if not p["title"] and xsec_cards(spec) is not None:  # (a section card's label)
        p["title"] = ((xsec_card(spec, i) or (0, {}))[1].get("label") or "").strip()
    if kind == "th":
        ref = series_ref(spec, i)
        if ref is None:
            return None
        p["run"] = ref[0]
        p["layers"] = [dict(copy.deepcopy(spec["series"][ref[1]]), type="series", on=True)]
    elif kind in ENTRIES:
        p["layers"] = [dict({k: copy.deepcopy(v) for k, v in e.items() if k != "panel"},
                            type="series" if kind == "line" else kind)
                       for e in spec.get(ENTRIES[kind], []) if int(e.get("panel", 0)) == i]
    elif kind == "scene":  # (its settings: spec["scene3d"], in the panel's view)
        p["run"], p["time_s"] = int(spec.get("run", 0)), float(spec["time_s"])
    else:
        ref = panel_ref(spec, i)
        if ref is None:
            return None
        p["run"], p["time_s"] = ref
        p["layers"] = copy.deepcopy(spec_layers(spec, i))
        z = (grid_cell(spec, i) or {}).get("z")
        if z is not None:
            p["z"], p["zmode"] = float(z), spec.get("panel_zmode", "height")
        e = panel_edit(spec, i)
        if e.get("z") is not None:
            p["z"], p["zmode"] = float(e["z"]), "height"
    if panel_edit(spec, i).get("title") is not None:
        p["title"] = panel_edit(spec, i)["title"]
    rt = spec.get("row_titles") or []
    if c == 0 and r < len(rt) and rt[r]:
        p["rowlabel"] = rt[r]
    own = legend_opts(kind, panel_edit(spec, i).get("legend"))
    labels = {k: v for k, v in panel_edit(spec, i).items()
              if k in ("xlabel", "ylabel") and v is not None}
    if labels:
        own["axes"] = labels
    if own:
        p["opts"] = own
    return p


LEGEND_OPTS = {"line": ("ts", ("legend",)), "dist": ("dist", ("legend",)),
               "profile": ("prof", ("legend",)), "joint": ("joint", ("legend",)),
               "azim": ("azim", ("legend",)),
               "sounding": ("skewt", ("legend", "hodo_key"))}


def legend_opts(kind, lg):
    """The settings a panel's own legend (panel edit "legend": "on" True / False, "loc",
    "anchor" [x, y], "ncol", "frame"; a missing key: as laid out) changes, as panel opts:
    its kind's legend keys (a sounding's: both its skew-T legend and its hodograph key).
    "on" True also keeps it beside a figure legend, or with the block's panels' own
    legends off ("legend_keep")."""
    if kind not in LEGEND_OPTS or not lg:
        return {}
    key, names = LEGEND_OPTS[kind]
    o = {}
    for name in names:
        if lg.get("on") is not None:
            o[name] = bool(lg["on"])
        for k in ("loc", "anchor", "ncol", "frame"):
            if lg.get(k) is not None:
                o[f"{name}_{k}"] = lg[k]
    if kind == "sounding" and lg.get("on") is not None:
        o["legend_off"] = not lg["on"]  # (several soundings have a legend regardless)
    if lg.get("on"):
        o["legend_keep"] = True
    return {key: o} if o else {}


def _local_entries(spec, i, d):
    """Panel data d of version-1 panel i with its lines' (soundings') entries counted
    within the panel."""
    kind = spec.get("kind")
    if kind not in ENTRIES:
        return d
    key, count = {"line": ("S", "nlines"), "sounding": ("N", "nsnd"),
                  "dist": ("D", "ndist"), "profile": ("P", "nprof"),
                  "joint": ("J", "njoint"), "azim": ("A", "nazim")}[kind]
    mine = [e for e, ent in enumerate(spec.get(ENTRIES[kind], []))
            if int(ent.get("panel", 0)) == i]
    where = {e: n for n, e in enumerate(mine)}
    d = dict(d)
    for j in range(int(d.get(count, 0))):
        e = int(d[f"{key}{j}_e"])
        d[f"{key}{j}_e"] = where.get(e, len(mine))
    return d


def block_view(spec, k):
    """The settings of block k of a version-2 spec: the figure's (but those of the
    figure alone: size, title, export, code) and the block's own (opts)."""
    v = {key: val for key, val in spec.items() if key not in FIG_ONLY}
    v.update(spec["blocks"][k].get("opts") or {})
    if (v.get("colorbar") or {}).get("mode") in ("parts", "figure"):
        v["colorbar"] = dict(v["colorbar"], mode="shared")
    return v


def panel_view(spec, p, bv=None):
    """The settings panel p is drawn with: its block's (bv: block_view), then its own
    (p["opts"]; a group of settings, such as "skewt", merged into the block's), with
    its kind and layers where version 1 kept them (soundings and the series of a
    time-series panel, distributions, profiles, joint distributions and azimuthal
    means under "soundings", "series", "dists", "profiles", "joints" and "azims")."""
    v = dict(block_view(spec, int(p.get("block", 0))) if bv is None else bv)
    for k, val in (p.get("opts") or {}).items():  # (a group of settings: merged)
        v[k] = dict(v[k], **val) if isinstance(val, dict) and isinstance(v.get(k), dict) \
            else val
    kind = v["kind"] = p["kind"]
    v[ENTRIES.get(kind, "layers")] = p.get("layers") or []
    return v


def block_shares(spec):
    """Each block's share of a version-2 figure (part_shares of its blocks)."""
    return part_shares(dict(arrange=spec.get("arrange", "row"), parts=[
        dict(share=b.get("share"), size=b.get("size") or spec["size"])
        for b in spec["blocks"]]))


def _panel_layers(p):
    """The map layers panel p is drawn with (a time-height panel: its series' fill)."""
    if p["kind"] == "th":
        return [dict({k: lay[k] for k in FILL_KEYS if k in lay}, type="fill",
                     on=lay.get("on", True)) for lay in p.get("layers", [])]
    return p.get("layers") or []


def resolved(p, lay):
    """Layer lay of panel p with its run, time and height filled in from the panel's
    (where the layer has None or none)."""
    out = dict(lay)
    for k in ("run", "time_s", "z"):
        if out.get(k) is None and p.get(k) is not None:
            out[k] = p[k]
    if out.get("run") is None:
        out["run"] = 0
    return out


def _z_text(spec, p):
    """The height label of version-2 panel p (z_text), or "" for a panel without a
    height of its own."""
    if p.get("z") is None:
        return ""
    level = p.get("zmode", "height") == "level"
    fmt = spec.get("z_label", {}).get("fmt") or ("k = {k}" if level else "z = {z:g} km")
    return fmt.format(z=float(p["z"]), k=int(round(float(p["z"]))))


def _key_layer(ck, layers):
    """The contour layer of a contour key: layer ck["layer"], else the first contour
    layer that is on (None: none)."""
    k = int(ck.get("layer", -1))
    return layers[k] if 0 <= k < len(layers) and layers[k]["type"] == "contour" else next(
        (l for l in layers if l["type"] == "contour" and l.get("on", True)), None)
