"""Changes to a figure document, without widgets: layers shared or of a panel, what differs in
a panel, a panel's height, a run's time zero, titles, and filling panels.  Each takes the
document and changes it in place; the shell keeps a copy first, for undo.

Layers are named by id (shared) or by place in their panel (j, as figdraw.panel_layers counts
them), so nothing is renumbered when one moves or goes."""

import copy
import json

from .. import draw as figdraw
from ..draw.base import _cell

MISSING = object()  # (a key a layer no longer has)
HEIGHT_KEYS = ("z", "mode")  # (what a panel's own height writes in its layers)


def plain(x):
    """x as JSON would give it back."""
    return json.loads(json.dumps(x, default=float))


def panel_by_id(doc, pid):
    return next((p for p in doc.get("panels") or [] if p["id"] == pid), None)


def panels_of(doc, kind):
    """The panels of a kind, in reading order."""
    return sorted((p for p in doc.get("panels") or [] if p["kind"] == kind),
                  key=lambda p: _cell(p)[:2])


def places(doc, p):
    """Panel p's layer items, as figdraw.panel_layers counts them (a reference to a shared
    layer no longer there is not counted)."""
    have = doc.get("layers") or {}
    return [x for x in p.get("layers") or [] if "ref" not in x or x["ref"] in have]


def overrides(item):
    """What a panel's layer item changes of its shared layer (a layer of its own: nothing)."""
    return item.get("over") or {} if "ref" in item else {}


# ------------------------------------------------------------ runs of a layer
def to_card(doc, lay):
    """Layer lay (run ids) as a card takes it: runs as their places in the figure."""
    at = {r["id"]: k for k, r in enumerate(doc.get("runs") or [])}
    n = len(at)
    return figdraw.run_ids(copy.deepcopy(lay), lambda v: at.get(v, n))


def from_card(doc, lay):
    """What a card collected (runs as places) with run ids."""
    runs = doc.get("runs") or []
    return figdraw.run_ids(copy.deepcopy(lay), lambda k: runs[int(k)]["id"]
                           if 0 <= int(k) < len(runs) else "gone")


def run_index(doc, rid):
    return next((k for k, r in enumerate(doc.get("runs") or []) if r["id"] == rid), 0)


def new_run_id(doc):
    ids = {r["id"] for r in doc.get("runs") or []}
    n = len(ids)
    while f"r{n}" in ids:
        n += 1
    return f"r{n}"


# ------------------------------------------------------------ writing a layer's settings
def write_shared(doc, lid, changes):
    """Keys changed on a shared layer (MISSING: it no longer has them).  A panel's override
    of a key stays: it wins when the panel is drawn."""
    lay = doc["layers"][lid]
    for k, v in changes.items():
        if v is MISSING:
            lay.pop(k, None)
        else:
            lay[k] = v
    apply_heights(doc)


def write_panel(doc, p, j, changes):
    """Keys changed on layer j of panel p: into its overrides (a value back at the shared
    layer's: no longer an override), or a layer of its own as they are."""
    item = places(doc, p)[j]
    if "ref" not in item:
        for k, v in changes.items():
            if v is MISSING:
                item.pop(k, None)
            else:
                item[k] = v
    else:
        shared = doc["layers"][item["ref"]]
        over = item.setdefault("over", {})
        for k, v in changes.items():
            if v is MISSING:  # (the shared layer has it: the panel says none)
                if k in shared:
                    over[k] = None
                else:
                    over.pop(k, None)
            elif k in shared and plain(shared[k]) == plain(v):
                over.pop(k, None)
            else:
                over[k] = v
    apply_heights(doc, [p])


def clear_over(doc, p, j, key=None):
    """Layer j of panel p back at its shared layer's: one key, or all."""
    item = places(doc, p)[j]
    if "ref" not in item:
        return
    if key is None:
        item["over"] = {}
    else:
        (item.get("over") or {}).pop(key, None)
    apply_heights(doc, [p])


def differing(doc, lid, kind):
    """{panel id: the keys it has otherwise than shared layer lid}: a panel's own height and
    whether it draws the layer don't count."""
    out = {}
    for p in panels_of(doc, kind):
        own = p.get("z") is not None
        for item in places(doc, p):
            if item.get("ref") == lid:
                keys = [k for k in overrides(item)
                        if k != "on" and not (own and k in HEIGHT_KEYS)]
                if keys:
                    out[p["id"]] = keys
    return out


def clear_shared_over(doc, lid, kind):
    """No panel of a kind differs from shared layer lid any more (what draws it stays)."""
    for p in panels_of(doc, kind):
        for item in places(doc, p):
            if item.get("ref") == lid:
                on = overrides(item).get("on", MISSING)
                item["over"] = {} if on is MISSING else dict(on=on)
    apply_heights(doc)


# ------------------------------------------------------------ shared layers
def new_layer_id(doc):
    have = doc.get("layers") or {}
    n = len(have)
    while f"l{n}" in have:
        n += 1
    return f"l{n}"


def shared_ids(doc, kind):
    """The ids of the shared layers a kind's panels draw, in drawing order (the document's,
    but for those it doesn't list)."""
    used = {x["ref"] for p in panels_of(doc, kind) for x in places(doc, p) if "ref" in x}
    return [i for i in doc.get("layers") or {} if i in used]


def add_shared(doc, kind, lay):
    """A new shared layer on top in every panel of a kind.  Returns its id."""
    lid = new_layer_id(doc)
    doc.setdefault("layers", {})[lid] = lay
    for p in panels_of(doc, kind):
        p.setdefault("layers", []).append(dict(ref=lid, over={}))
    apply_heights(doc)
    return lid


def copy_shared(doc, kind, lid):
    """A copy of a shared layer just above it, in each panel of a kind drawing it, each with
    what differed there.  Returns its id."""
    new = new_layer_id(doc)
    keys = list(doc["layers"])
    keys.insert(keys.index(lid) + 1, new)
    layers = dict(doc["layers"], **{new: copy.deepcopy(doc["layers"][lid])})
    doc["layers"] = {k: layers[k] for k in keys}
    for p in panels_of(doc, kind):
        for at, item in enumerate(p["layers"]):
            if item.get("ref") == lid:
                p["layers"].insert(at + 1, dict(ref=new, over=copy.deepcopy(overrides(item))))
                break
    return new


def remove_shared(doc, kind, lid):
    """A shared layer out of a kind's panels (out of the document when no panel draws it)."""
    for p in panels_of(doc, kind):
        p["layers"] = [x for x in p.get("layers") or [] if x.get("ref") != lid]
    if not any(x.get("ref") == lid for p in doc.get("panels") or [] for x in p.get("layers") or []):
        doc["layers"].pop(lid, None)


def move_shared(doc, kind, lid, d):
    """A shared layer d places later (on top) or earlier among a kind's shared layers: in the
    document and in each of its panels, where layers of a panel's own stay in their places."""
    order = shared_ids(doc, kind)
    i = order.index(lid)
    j = min(max(i + d, 0), len(order) - 1)
    if i == j:
        return
    order[i], order[j] = order[j], order[i]
    rest = iter(order)
    keys = [next(rest) if k in order else k for k in doc["layers"]]
    doc["layers"] = {k: doc["layers"][k] for k in keys}
    rank = {k: n for n, k in enumerate(order)}
    for p in panels_of(doc, kind):
        at = [n for n, x in enumerate(p["layers"]) if x.get("ref") in rank]
        items = sorted((p["layers"][n] for n in at), key=lambda x: rank[x["ref"]])
        for n, item in zip(at, items):
            p["layers"][n] = item


def in_panel(doc, p, lid, on):
    """Whether panel p draws shared layer lid.  Not yet among its layers: added on top of its
    shared ones; dropped: it stays among them, off, so what differs there is kept."""
    item = next((x for x in p.setdefault("layers", []) if x.get("ref") == lid), None)
    if item is not None:
        over = item.setdefault("over", {})
        if on:
            over.pop("on", None)
            if doc["layers"][lid].get("on", True) is False:
                over["on"] = True
        else:
            over["on"] = False
        return
    if on:
        last = max((n for n, x in enumerate(p["layers"]) if "ref" in x), default=-1)
        p["layers"].insert(last + 1, dict(ref=lid, over={}))
        apply_heights(doc, [p])


def draws(doc, p, lid):
    """Whether panel p draws shared layer lid."""
    item = next((x for x in p.get("layers") or [] if x.get("ref") == lid), None)
    if item is None:
        return False
    return overrides(item).get("on", doc["layers"][lid].get("on", True)) is not False


# ------------------------------------------------------------ layers of a panel
def add_own(p, lay):
    """A layer of panel p alone, on top."""
    p.setdefault("layers", []).append(lay)


def copy_in_panel(doc, p, j):
    """A copy of layer j of panel p just above it: a layer of its own, as the panel draws
    it."""
    lay = figdraw.panel_layers(doc, p)[j][1]
    at = p["layers"].index(places(doc, p)[j])
    p["layers"].insert(at + 1, lay)


def remove_in_panel(doc, p, j):
    """Layer j out of panel p (a shared one no panel draws any more: out of the document)."""
    item = places(doc, p)[j]
    p["layers"].remove(item)
    lid = item.get("ref")
    if lid is not None and not any(x.get("ref") == lid for q in doc["panels"]
                                   for x in q.get("layers") or []):
        doc["layers"].pop(lid, None)


def move_in_panel(doc, p, j, d):
    """Layer j of panel p d places later or earlier in this panel alone.  Returns its new
    place."""
    items = places(doc, p)
    k = min(max(j + d, 0), len(items) - 1)
    a, b = p["layers"].index(items[j]), p["layers"].index(items[k])
    p["layers"][a], p["layers"][b] = p["layers"][b], p["layers"][a]
    return k


# ------------------------------------------------------------ a panel's height
def _at_height(lay, level):
    """Whether a panel's height reaches layer lay (figdraw.spec_layers)."""
    if lay.get("z_fixed") or "z" not in lay:
        return False
    mode = lay.get("mode", "height")
    if level:
        return lay["type"] == "vectors" or mode in ("height", "level")
    return lay["type"] == "vectors" or mode == "height"


def _set_keys(doc, item, vals):
    """A panel's layer item takes these keys (a reference: only what differs is kept)."""
    if "ref" not in item:
        item.update(vals)
        return
    shared = doc["layers"][item["ref"]]
    over = item.setdefault("over", {})
    for k, v in vals.items():
        if k in shared and shared[k] == v:
            over.pop(k, None)
        else:
            over[k] = v


def apply_heights(doc, panels=None):
    """Panels with a height of their own (p["z"]): their layers at a height take it, as the
    old form's row of heights did.  Layers with "z_fixed" keep theirs: set on the panel's
    layer, its z stays there; on the shared layer, the shared height shows."""
    for p in doc.get("panels") if panels is None else panels:
        if p.get("z") is None or p["kind"] != "plan":
            continue
        z, level = float(p["z"]), p.get("zmode", "height") == "level"
        for item in places(doc, p):
            lay = dict(doc["layers"][item["ref"]], **overrides(item)) if "ref" in item else item
            if _at_height(lay, level):
                _set_keys(doc, item, dict(mode="level", z=float(round(z))) if level
                          else dict(z=z))
            elif "ref" in item and lay.get("z_fixed") and not overrides(item).get("z_fixed"):
                overrides(item).pop("z", None)


def set_height(doc, p, z, zmode="height"):
    """Panel p's own height (km; zmode "level": a model level), or none (z None): its layers
    back at theirs."""
    if z is None:
        p.pop("z", None)
        p.pop("zmode", None)
        for item in places(doc, p):
            if "ref" in item:
                over = overrides(item)
                if not over.get("z_fixed"):
                    over.pop("z", None)
                    over.pop("mode", None)
        return
    p["z"], p["zmode"] = float(z), zmode
    apply_heights(doc, [p])


# ------------------------------------------------------------ time zero
def _moved(doc, ts, a, b):
    """Model time (s) in run b of the moment ts is in run a (their ids)."""
    return figdraw.moved_time(dict(runs=doc.get("runs") or []), ts, run_index(doc, a),
                              run_index(doc, b))


def set_t0(doc, rid, t0_min):
    """A run's time zero (min).  Each panel stays at the moment it showed: times stay in the
    run of the first panel with a time (the figure's reference), and move in the others, by
    the difference, so runs lined up stay lined up; a figure of one run only relabels.  Runs
    paired by output number: time zero doesn't pair them, so no time moves."""
    run = next(r for r in doc["runs"] if r["id"] == rid)
    dt = 60.0 * (float(t0_min or 0.0) - float(run.get("t0_min") or 0.0))
    run["t0_min"] = float(t0_min or 0.0)
    if not dt or run.get("outputs_s"):
        return
    timed = [p for p in sorted(doc.get("panels") or [], key=lambda p: _cell(p)[:2])
             if p.get("time_s") is not None and p.get("run") is not None]
    if not timed:
        return
    ref = timed[0]["run"]
    for p in timed:
        if p["run"] != ref:
            if rid == ref:
                p["time_s"] = float(p["time_s"]) - dt
            elif p["run"] == rid:
                p["time_s"] = float(p["time_s"]) + dt


# ------------------------------------------------------------ the grid: filling panels
def fill_problem(doc, rows, cols, kind="plan"):
    """Why the grid can't be rows x cols (panels of other kinds off it), or None."""
    off = [p for p in doc.get("panels") or [] if p["kind"] != kind and (
        _cell(p)[0] + _cell(p)[2] > rows or _cell(p)[1] + _cell(p)[3] > cols)]
    if off:
        from . import nodes
        names = nodes.letters(doc)
        return "These panels would be off the grid: " + ", ".join(names[p["id"]] for p in off)
    return None


def _taken(doc, kind):
    """The cells panels of other kinds hold."""
    out = set()
    for p in doc.get("panels") or []:
        if p["kind"] != kind:
            r, c, rs, cs = _cell(p)
            out.update((r + a, c + b) for a in range(rs) for b in range(cs))
    return out


def _targets(rows, cols, row_dim, col_dim, steps, taken):
    """[(row, column), {dim: its value}] of each panel to fill: two dimensions step through
    the rows and columns, one fills the free cells row by row; a cell past what it lists, or
    with None: none.  A list of fields or heights with nothing in it: as if not asked for."""
    both = "none" not in (row_dim, col_dim)
    dims = [d for d in (row_dim, col_dim) if d != "none"]
    out, free = [], 0
    for r in range(rows):
        for c in range(cols):
            if (r, c) in taken:
                continue
            pairs = ((row_dim, r), (col_dim, c)) if both else [(d, free) for d in dims]
            free += 1
            cell, ok = {}, True
            for d, j in pairs:
                items = steps.get(d) or []
                if not items and d in ("fields", "heights"):
                    continue
                if j >= len(items) or items[j] is None:
                    ok = False
                    break
                cell[d] = items[j]
            if ok:
                out.append(((r, c), cell))
    return out


def _first_fill(doc, p):
    """Place of panel p's first fill layer, or None."""
    return next((j for j, (_, lay) in enumerate(figdraw.panel_layers(doc, p))
                 if lay.get("type") == "fill"), None)


def _is_step(doc, p, cell):
    """Whether panel p already is what cell asks for."""
    for d, v in cell.items():
        if d == "times" and abs(float(p.get("time_s") or -1e9) - float(v)) > 1.0:
            return False
        if d == "runs" and p.get("run") != v:
            return False
        if d == "heights" and (p.get("z") is None or abs(float(p["z"]) - float(v)) > 1e-6):
            return False
        if d == "sections" and p.get("section") != v:
            return False
        if d == "fields":
            j = _first_fill(doc, p)
            if j is None or figdraw.panel_layers(doc, p)[j][1].get("field") != v.get("field"):
                return False
    return bool(cell)


def _new_panel(doc, pid, like, kind):
    """A panel drawing the shared layers `like` does, with nothing different; its own
    layers copied (no `like`: every shared layer)."""
    if like is None:
        layers = [dict(ref=i, over={}) for i in doc.get("layers") or {}]
        return dict(id=pid, kind=kind, run=None, time_s=None, title="", layers=layers, insets=[])
    layers = [dict(ref=x["ref"], over={}) if "ref" in x else copy.deepcopy(x)
              for x in like.get("layers") or []]
    out = {k: copy.deepcopy(v) for k, v in like.items()
           if k not in ("layers", "z", "zmode", "title", "rowlabel", "letter", "insets")}
    out.update(id=pid, layers=layers, title="", insets=[])
    return out


def fill_panels(doc, rows, cols, row_dim="none", col_dim="none", steps=None, run=None,
                time_s=None, zmode="height", kind="plan"):
    """Write the panels of a grid, once: no rule is kept, run it again to change them.

    row_dim, col_dim: what the rows and columns step through ("times", "heights", "runs",
    "fields", "sections", or "none"; one alone fills the grid row by row).  steps: {dim: its
    list}: times as model times in the first listed run's (or `run`'s) outputs, moved for the
    others by time zero; heights in km (zmode: or model levels); runs as ids; fields as the
    fill's settings; sections as ids.  run, time_s: every panel's, where neither steps.

    A panel that is already what a cell asks for goes there, keeping what was set on it; two
    dimensions then keep a panel in its cell, the rest take the panels left in reading order.
    Times and runs are written over; layers stay.  New panels draw the first panel's shared
    layers.  Panels left over go.  Returns (how many panels, how many gone)."""
    steps = steps or {}
    pool = panels_of(doc, kind)
    like = pool[0] if pool else None
    targets = _targets(rows, cols, row_dim, col_dim, steps, _taken(doc, kind))
    place = [None] * len(targets)
    for n, (_, cell) in enumerate(targets):
        hit = next((p for p in pool if _is_step(doc, p, cell)), None)
        if hit is not None:
            place[n] = hit
            pool.remove(hit)
    if "none" not in (row_dim, col_dim):
        for n, (at, _) in enumerate(targets):
            hit = next((p for p in pool if tuple(_cell(p)[:2]) == at), None)
            if place[n] is None and hit is not None:
                place[n] = hit
                pool.remove(hit)
    next_id = 1 + max([p["id"] for p in doc.get("panels") or []] or [-1])
    runs = steps.get("runs") or []
    time_run = runs[0] if runs else run
    for n, (at, cell) in enumerate(targets):
        p = place[n]
        if p is None and pool:
            p = pool.pop(0)
        if p is None:
            p = _new_panel(doc, next_id, like, kind)
            next_id += 1
            doc["panels"].append(p)
        p["cell"] = [at[0], at[1], 1, 1]
        p.pop("letter", None)
        rid = cell.get("runs", run if run is not None else p.get("run"))
        p["run"] = rid
        ts = cell.get("times", time_s)
        if ts is not None:
            p["time_s"] = _moved(doc, ts, time_run, rid) if time_run is not None else float(ts)
        if "sections" in cell:
            p["section"] = cell["sections"]
        if "heights" in cell:
            set_height(doc, p, cell["heights"], zmode)
        elif p.get("z") is not None:
            set_height(doc, p, None)
        if "fields" in cell:
            j = _first_fill(doc, p)
            if j is not None:
                write_panel(doc, p, j, {k: v for k, v in cell["fields"].items()
                                        if k not in ("z", "mode", "on", "type")})
    gone = {p["id"] for p in pool}
    doc["panels"] = sorted((p for p in doc["panels"] if p["id"] not in gone),
                           key=lambda p: _cell(p)[:2])
    grid = doc.setdefault("grid", {})
    if (int(grid.get("rows", 1)), int(grid.get("cols", 1))) != (rows, cols):
        grid.pop("widths", None)
        grid.pop("heights", None)
    grid.update(rows=int(rows), cols=int(cols))
    letters = (doc.get("style") or {}).get("letters")
    if isinstance(letters, dict) and letters.get("auto"):  # (one panel: no letter)
        letters["on"] = len(doc["panels"]) > 1
    return len(targets), len(gone)


def guess_fill(doc, kind="plan"):
    """What the tool starts from: how the panels of a kind are now.  {rows, cols, row_dim,
    col_dim, run, runs, times (their model times), heights, fields}."""
    grid = doc.get("grid") or {}
    rows, cols = int(grid.get("rows", 1)), int(grid.get("cols", 1))
    mine = panels_of(doc, kind)
    times = list(dict.fromkeys(float(p["time_s"]) for p in mine if p.get("time_s") is not None))
    runs = list(dict.fromkeys(p["run"] for p in mine if p.get("run") is not None))
    heights = list(dict.fromkeys(float(p["z"]) for p in mine if p.get("z") is not None))
    fields = []
    for p in mine:
        j = _first_fill(doc, p)
        if j is not None:
            fields.append(figdraw.panel_layers(doc, p)[j][1].get("field"))
    fields = list(dict.fromkeys(f for f in fields if f))
    across = [d for d, n in (("runs", len(runs)), ("fields", len(fields)),
                             ("heights", len(heights)), ("times", len(times))) if n > 1]
    row_dim, col_dim = "none", across[-1] if across else "none"
    if len(across) >= 2:
        row_dim = across[0]
    return dict(rows=rows, cols=cols, row_dim=row_dim, col_dim=col_dim, runs=runs, times=times,
                heights=heights, fields=fields, zmode=mine[0].get("zmode", "height")
                if mine else "height")


def auto_titles(doc, fields=None, kind="plan"):
    """Titles from what differs between a kind's panels: run, field and height (panels
    differing only in time: the field, as the time is labelled).  Rows and columns both
    stepping: column titles on the top row, row labels at the left.  Titles that name the runs
    turn the run labels off."""
    mine = panels_of(doc, kind)

    def run_of(p):
        return p.get("run")

    def field_of(p):
        j = _first_fill(doc, p)
        return None if j is None else figdraw.panel_layers(doc, p)[j][1].get("field")

    def field_word(f):
        if f is None:
            return ""
        return fields[f].label if fields is not None and f in fields else str(f)

    def z_word(p):
        if p.get("z") is None:
            return ""
        return f"k = {int(round(float(p['z'])))}" if p.get("zmode") == "level" \
            else f"{float(p['z']):g} km"

    names = {r["id"]: r.get("label") or str(r.get("path", "")).rstrip("/").rsplit("/", 1)[-1]
             for r in doc.get("runs") or []}
    many = {k: len({f(p) for p in mine}) > 1 for k, f in (
        ("run", run_of), ("field", field_of), ("z", z_word))}

    def words(p):
        out = []
        if many["run"]:
            out.append(names.get(p.get("run"), ""))
        if many["field"]:
            out.append(field_word(field_of(p)))
        if many["z"]:
            out.append(z_word(p))
        return " – ".join(x for x in out if x)

    def since(p):  # (the time since its run's time zero: alike in panels lined up)
        if p.get("time_s") is None:
            return None
        return round(float(p["time_s"]) / 60.0 - figdraw.run_t0(view, run_index(doc, p["run"])), 3)

    def time_word(p):
        k = run_index(doc, p["run"])
        return figdraw.time_text(float(p["time_s"]), figdraw.run_time_opts(view, k, p["time_s"]))

    view = dict(runs=doc.get("runs") or [], time_label=(doc.get("style") or {}).get("time_label"))
    sides = [(run_of, lambda p: names.get(p.get("run"), "")),
             (field_of, lambda p: field_word(field_of(p))),
             (z_word, z_word), (since, time_word)]

    def along(p, axis):
        return _along(p, mine, axis, sides)

    rows = sorted({_cell(p)[0] for p in mine})
    cols = sorted({_cell(p)[1] for p in mine})
    if len(mine) == len(rows) * len(cols) > 1 and len(rows) > 1 and len(cols) > 1 and \
            all(along(p, 0) and along(p, 1) for p in mine):
        for p in mine:
            r, c = _cell(p)[:2]
            p["title"] = along(p, 1) if r == rows[0] else ""
            if c == cols[0]:
                p["rowlabel"] = along(p, 0)
            else:
                p.pop("rowlabel", None)
    else:
        one_field = field_word(field_of(mine[0])) if mine else ""
        for p in mine:
            p["title"] = words(p) or one_field
            p.pop("rowlabel", None)
    if many["run"]:
        style = doc.setdefault("style", {})
        style["run_label"] = dict(style.get("run_label") or {}, on=False)


def _along(p, mine, axis, words):
    """The words of what stays the same along a row (axis 0) or a column (axis 1) of p and
    differs across the other side.  words: [(what a panel has of it, that in words)]."""
    r = _cell(p)[axis]
    same = [q for q in mine if _cell(q)[axis] == r]
    other = [q for q in mine if _cell(q)[axis] != r]
    out = []
    for f, word in words:
        here = {f(q) for q in same}
        if len(here) == 1 and {f(q) for q in other} != here and f(p) not in (None, ""):
            out.append(word(p))
    return " – ".join(x for x in out if x)
