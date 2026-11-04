"""Changes to a figure document, without widgets: layers shared or of a panel, what differs in
a panel, a panel's height, a run's time zero, titles, the grid and where panels sit, sections,
series, annotations, a 3D scene's settings, and filling panels.  Each takes the document and changes it in place; the shell keeps a copy first, for
undo.

Layers are named by id (shared) or by place in their panel (j, as figdraw.panel_layers counts
them), so nothing is renumbered when one moves or goes."""

import copy
import json

from .. import draw as figdraw
from ..draw.base import _cell
from ..kinds import KINDS
from ..spec.arrays import scene3d_of
from ..spec.doc import ann_panels, drop_annotations  # noqa: F401  (de.drop_annotations)
from ..spec.sections import describe as section_words, section_defaults
from ..spec.tables import tbl_points

MISSING = object()  # (a key a layer no longer has)
OFF_GRID = "off_grid"  # (the document's panels with no room on the grid: not drawn; settle_grid)
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


def remove_run(doc, rid):
    """A run out of the figure.  A series' hand edits are held by the run's place (spec/panels
    apply_edits), so those of the runs after it move with it."""
    k = run_index(doc, rid)
    doc["runs"] = [r for r in doc["runs"] if r["id"] != rid]
    for p in [*(doc.get("panels") or []), *(doc.get(OFF_GRID) or [])]:
        for item in p.get("layers") or []:
            if item.get("edits"):
                item["edits"] = {str(int(n) - (int(n) > k)): v for n, v in item["edits"].items()
                                 if int(n) != k}
                if not item["edits"]:
                    del item["edits"]


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
    _follow_series(p)


def _panels_draw(doc, lid):
    """Whether a panel, or an inset of one, draws shared layer lid."""
    return any(x.get("ref") == lid for q in doc["panels"]
               for x in [*(q.get("layers") or []), *figdraw.inset_items(q)])


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
        for ins in p.get("insets") or []:
            if ins.get("layers") is not None:
                ins["layers"] = [x for x in ins["layers"] if x.get("ref") != lid]
    if not _panels_draw(doc, lid):
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
    if lid is not None and not _panels_draw(doc, lid):
        doc["layers"].pop(lid, None)
    _follow_series(p)


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
        have = doc.get("layers") or {}
        for item in [*places(doc, p), *(x for x in figdraw.inset_items(p)
                                        if "ref" not in x or x["ref"] in have)]:
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
        for item in [*places(doc, p), *figdraw.inset_items(p)]:
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
    ordered = sorted(doc.get("panels") or [], key=lambda p: _cell(p)[:2])
    _keep_moment([p for p in ordered if p.get("time_s") is not None and p.get("run") is not None],
                 rid, dt)
    for kind in dict.fromkeys(p["kind"] for p in ordered):
        if kind not in ("line", "th"):  # (a series has no one time)
            # (a profile of your own has no time; a table's times are its first run's, as
            # the other runs' follow by time zero: both stay)
            _keep_moment([x for p in ordered if p["kind"] == kind for x in p.get("layers") or []
                          if "ref" not in x and x.get("time_s") is not None
                          and x.get("run") is not None and x.get("source") != "table"], rid, dt)


def _keep_moment(timed, rid, dt):
    """Items with a run and time (one list: a kind's soundings, say, or the panels) stay at
    the moment they showed when run rid's time zero moves by dt s: measured from the first
    one's run, whose items stay."""
    if not timed:
        return
    ref = timed[0]["run"]
    for x in timed:
        if x["run"] != ref:
            for key in ("time_s", "time_s1"):
                if x.get(key) is not None:
                    if rid == ref:
                        x[key] = float(x[key]) - dt
                    elif x["run"] == rid:
                        x[key] = float(x[key]) + dt


# ------------------------------------------------------------ the grid: its shape
def grid_shape(doc):
    grid = doc.get("grid") or {}
    return int(grid.get("rows", 1)), int(grid.get("cols", 1))


def _cells_of(p):
    r, c, rs, cs = _cell(p)
    return {(r + a, c + b) for a in range(rs) for b in range(cs)}


def free_cells(doc):
    """The cells of the grid no panel covers, in reading order."""
    rows, cols = grid_shape(doc)
    taken = {x for p in doc.get("panels") or [] for x in _cells_of(p)}
    return [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in taken]


def _fit_ratios(vals, n):
    """A list of column or row shares for n of them: cut, or the new ones as wide as the
    average."""
    vals = [float(v) for v in vals]
    return vals[:n] + [sum(vals) / len(vals)] * (n - len(vals))


def next_panel_id(doc):
    """An id no panel has, on the grid or set aside."""
    return 1 + max([p["id"] for p in [*(doc.get("panels") or []), *(doc.get(OFF_GRID) or [])]]
                   or [-1])


def _shape(doc, rows, cols):
    """The grid's rows and columns; its shares follow (set_shares)."""
    grid = doc.setdefault("grid", {})
    grid.update(rows=int(rows), cols=int(cols))
    for key, n in (("widths", int(cols)), ("heights", int(rows))):
        if grid.get(key):
            grid[key] = _fit_ratios(grid[key], n)


def _back_in(doc, p, cell):
    """Panel p, set aside, into the figure at cell.  What went while it was aside is gone from
    it: shared layers, its run."""
    doc[OFF_GRID] = [q for q in doc[OFF_GRID] if q["id"] != p["id"]]
    if not doc[OFF_GRID]:
        del doc[OFF_GRID]
    p["cell"] = list(cell)
    p["layers"] = [x for x in p.get("layers") or [] if "ref" not in x
                   or x["ref"] in (doc.get("layers") or {})]
    if p.get("run") is not None and all(r["id"] != p["run"] for r in doc.get("runs") or []):
        p["run"] = doc["runs"][0]["id"]
    doc["panels"].append(p)


def _take_back_aside(doc):
    """Those set aside into the grid: to their own cells if free, then any free ones.  How many."""
    rows, cols = grid_shape(doc)
    n = 0
    for p in list(doc.get(OFF_GRID) or []):
        r, c, rs, cs = _cell(p)
        taken = {x for q in doc["panels"] for x in _cells_of(q)}
        if r + rs <= rows and c + cs <= cols and not _cells_of(p) & taken:
            _back_in(doc, p, [r, c, rs, cs])
            n += 1
    for p in list(doc.get(OFF_GRID) or []):
        free = free_cells(doc)
        if free:
            _back_in(doc, p, [*free[0], 1, 1])
            n += 1
    return n


def settle_grid(doc):
    """The panels and the grid as it now is.  A panel running over the edge is cut to it; one
    starting past it takes a free cell; with none free it is set aside: kept in the document
    under OFF_GRID, not drawn, until there is room.  Those aside return when a cell is free.
    Returns what became of them, as a line, or None."""
    from . import nodes
    rows, cols = grid_shape(doc)
    names = nodes.letters(doc)
    off = []
    for p in nodes.in_order(doc):
        r, c, rs, cs = _cell(p)
        if r >= rows or c >= cols:
            off.append(p)
            continue
        if r + rs > rows or c + cs > cols:
            p["cell"] = [r, c, min(rs, rows - r), min(cs, cols - c)]
    if off:
        gone = {p["id"] for p in off}
        doc["panels"] = [p for p in doc["panels"] if p["id"] not in gone]
    moved, aside = [], []
    for p in off:
        free = free_cells(doc)
        if free:
            p["cell"] = [*free[0], 1, 1]
            doc["panels"].append(p)
            moved.append(p)
        else:
            doc.setdefault(OFF_GRID, []).append(p)
            aside.append(p)
    back = 0 if aside else _take_back_aside(doc)
    if off or back:
        letters_in_order(doc)
    said = []
    if moved:
        said.append("Moved to a free cell: panel " + ", ".join(names[p["id"]] for p in moved) + ".")
    if aside:
        said.append(f"No room for panel{'s' if len(aside) > 1 else ''} "
                    + ", ".join(names[p["id"]] for p in aside) + ": set aside, not drawn, and "
                    "back when the grid has room.")
    if back:
        said.append(f"Back on the grid: {back} panel{'s' if back > 1 else ''} set aside.")
    return " ".join(said) or None


def set_grid(doc, rows, cols):
    """The grid's rows and columns.  Any size can be asked for: panels that no longer fit are
    moved or set aside (settle_grid).  Returns what became of them, as a line, or None."""
    _shape(doc, rows, cols)
    return settle_grid(doc)


def bring_back(doc):
    """Every panel set aside onto the grid, which grows if it has to."""
    while doc.get(OFF_GRID):
        p = doc[OFF_GRID][0]
        at = next_cell(doc)
        _back_in(doc, p, [at[0], at[1], 1, 1])
    letters_in_order(doc)


def forget_aside(doc):
    """The panels set aside gone for good."""
    gone = {p["id"] for p in doc.pop(OFF_GRID, [])}
    drop_annotations(doc, gone)


def set_shares(doc, key, vals):
    """The columns' ("widths") or rows' ("heights") shares of the figure; none: equal.  Why it
    can't be, or None."""
    n = grid_shape(doc)[key == "widths"]
    word = "column" if key == "widths" else "row"
    grid = doc.setdefault("grid", {})
    if not vals:
        grid.pop(key, None)
        return None
    if len(vals) != n or min(vals) <= 0:
        return f"That needs {n} numbers above 0, one for each {word}."
    grid[key] = [float(v) for v in vals]
    return None


def next_cell(doc, grow=None):
    """Where a new panel goes: the first free cell (grow "row" or "col": in a new row or
    column, as also when none is free).  Grows the grid when it has to."""
    rows, cols = grid_shape(doc)
    free = free_cells(doc)
    if free and grow is None:
        return free[0]
    if grow is None:
        grow = "col" if rows == 1 else "row"
    if grow == "col":
        _shape(doc, rows, cols + 1)
        return 0, cols
    _shape(doc, rows + 1, cols)
    return rows, 0


def place_problem(doc, pid, cell):
    """Why panel pid can't take cell [row, col, rowspan, colspan], or None (a panel of the
    same shape exactly there is no problem: they swap)."""
    from . import nodes
    rows, cols = grid_shape(doc)
    r, c, rs, cs = cell
    if min(rs, cs) < 1 or r < 0 or c < 0 or r + rs > rows or c + cs > cols:
        return f"That is off the grid of {rows} × {cols}: make the grid larger first."
    p = panel_by_id(doc, pid)
    wanted = {(r + a, c + b) for a in range(rs) for b in range(cs)}
    names = nodes.letters(doc)
    hit = [q for q in nodes.in_order(doc) if q["id"] != pid and wanted & _cells_of(q)]
    if len(hit) == 1 and list(_cell(hit[0])) == list(cell) and _cell(p)[2:] == _cell(hit[0])[2:]:
        return None
    if hit:
        return f"Panel{'s' if len(hit) > 1 else ''} {', '.join(names[q['id']] for q in hit)} " \
               f"{'are' if len(hit) > 1 else 'is'} there."
    return None


def place_panel(doc, pid, cell):
    """Panel pid at cell (a panel of its shape exactly there takes its place).  Why it can't
    be, or None."""
    why = place_problem(doc, pid, cell)
    if why:
        return why
    p = panel_by_id(doc, pid)
    for q in doc["panels"]:
        if q["id"] != pid and list(_cell(q)) == [int(v) for v in cell]:
            q["cell"] = list(_cell(p))
    p["cell"] = [int(v) for v in cell]
    letters_in_order(doc)
    return None


def letters_in_order(doc):
    """Panels were added, moved or removed: letters go by reading order (a conversion's held
    letters, kept to match the old drawing, no longer mean anything), and a figure whose
    letters follow the count has them with more than one panel."""
    for p in doc.get("panels") or []:
        p.pop("letter", None)
    letters = (doc.get("style") or {}).get("letters")
    if isinstance(letters, dict) and letters.get("auto"):
        letters["on"] = len(doc.get("panels") or []) > 1


# ------------------------------------------------------------ panels of any kind
AXES_LOOK = ("ticks", "ticklabels", "minor", "tickdir", "frame_lw", "title_bold", "title_loc")


def seed_kind(doc, kind, start, labels=("", "")):
    """A kind new to the figure: its settings from `start` (a new figure's, {key: settings}),
    its axes looking like those of the kinds already there, with its own axis labels."""
    kinds = doc.setdefault("kinds", {})
    if kind in kinds:
        return
    have = next((k["axes"] for k in kinds.values() if isinstance(k.get("axes"), dict)), None)
    new = copy.deepcopy(start)
    axes = dict(new.get("axes") or {})
    if have is not None:
        axes.update({k: have[k] for k in AXES_LOOK if k in have})
    axes.update(xlabel=labels[0], ylabel=labels[1])
    new["axes"] = axes
    kinds[kind] = new


def label_places(doc, p, kind_info, all_kinds):
    """A new panel's letter and time label go where its kind has them, unless the figure's were
    moved by hand (they are at no kind's place): as its own settings, since style holds one
    place for the whole figure."""
    style = doc.get("style") or {}
    places_of = dict(letters=("letter_at", "lower left"), time_label=("time_at", "lower right"))
    for block, (attr, fallback) in places_of.items():
        now = (style.get(block) or {}).get("loc", fallback)
        want = getattr(kind_info, attr)
        if now != want and now in {getattr(k, attr) for k in all_kinds}:
            opts = p.setdefault("opts", {})
            opts[block] = dict(opts.get(block) or {}, loc=want)


def add_panel(doc, kind, cell, layers=None, **keys):
    """A new panel at (row, col) in one cell, with its layers and other keys.  Returns it."""
    pid = next_panel_id(doc)
    p = dict(id=pid, kind=kind, cell=[int(cell[0]), int(cell[1]), 1, 1], run=None, time_s=None,
             title="", layers=list(layers or []), insets=[])
    p.update(keys)
    doc.setdefault("panels", []).append(p)
    letters_in_order(doc)
    return p


def plan_panel(doc, cell, run, time_s, start_layers=(), section=None):
    """A new plan view at cell: as the last plan view is, but for its titles; the first draws
    the shared layers there are (none: start_layers, shared from now on)."""
    mine = panels_of(doc, "plan")
    new_id = next_panel_id(doc)
    if mine:
        p = _new_panel(doc, new_id, mine[-1], "plan")
        doc["panels"].append(p)
    else:
        if not doc.get("layers"):
            for lay in start_layers:
                doc.setdefault("layers", {})[new_layer_id(doc)] = copy.deepcopy(lay)
        p = _new_panel(doc, new_id, None, "plan")
        p.update(run=run, time_s=time_s)
        doc["panels"].append(p)
    p["cell"] = [int(cell[0]), int(cell[1]), 1, 1]
    if p.get("section") is None:
        secs = doc.setdefault("sections", {})
        if not secs and section is not None:
            secs["s0"] = copy.deepcopy(section)
        if secs:
            p["section"] = next(iter(secs))
    letters_in_order(doc)
    return p


def copy_panel(doc, pid, cell):
    """A copy of panel pid at (row, col), in one cell, without its row label.  Returns it."""
    new = copy.deepcopy(panel_by_id(doc, pid))
    new.pop("rowlabel", None)
    new.update(id=next_panel_id(doc), cell=[int(cell[0]), int(cell[1]), 1, 1])
    _new_inset_ids(doc, new)
    doc["panels"].append(new)
    copy_annotations(doc, pid, new["id"])
    letters_in_order(doc)
    return new


def remove_panel(doc, pid):
    """Panel pid out of the figure; its cell stays empty.  Shared layers stay in the document
    (a plan view added later finds them)."""
    doc["panels"] = [p for p in doc["panels"] if p["id"] != pid]
    drop_annotations(doc, {pid})
    letters_in_order(doc)


def move_entry(doc, pid, j, other):
    """Layer j of panel pid (one of its own) to the end of panel `other`'s."""
    item = places(doc, panel_by_id(doc, pid))[j]
    panel_by_id(doc, pid)["layers"].remove(item)
    panel_by_id(doc, other).setdefault("layers", []).append(item)


# ------------------------------------------------------------ a shared layer, other kinds
def other_kinds_with(doc, kind, lid):
    """The panels of other kinds drawing shared layer lid."""
    return [p for p in doc.get("panels") or [] if p["kind"] != kind
            and any(x.get("ref") == lid for x in p.get("layers") or [])]


def split_shared(doc, kind, lid):
    """A kind's panels get a copy of shared layer lid of their own, so changes to it stay among
    them; what differs in a panel stays.  Returns the copy's id."""
    new = new_layer_id(doc)
    keys = list(doc["layers"])
    keys.insert(keys.index(lid) + 1, new)
    layers = dict(doc["layers"], **{new: copy.deepcopy(doc["layers"][lid])})
    doc["layers"] = {k: layers[k] for k in keys}
    for p in panels_of(doc, kind):
        for item in [*(p.get("layers") or []), *figdraw.inset_items(p)]:
            if item.get("ref") == lid:
                item["ref"] = new
    return new


def sounding_size(doc):
    """A figure of soundings alone, as its automatic size has it: (width, height) in, for its
    layout, grid and how many soundings share a panel when each has a parameter table.  None:
    other kinds are there."""
    pans = doc.get("panels") or []
    if not pans or {p["kind"] for p in pans} != {"sounding"}:
        return None
    rows, cols = grid_shape(doc)
    res = figdraw.resolve(doc)
    sk = figdraw.panel_view(res, res["panels"][0]).get("skewt", {})
    lay = figdraw.sounding_layout(sk)
    w = {"side": 8.2, "hodo": 4.5}.get(lay, 5.0) * cols + 0.5
    h = (4.5 if lay == "hodo" else 5.0) * rows
    if sk.get("table"):
        h += rows * (0.45 + 0.25 * max(len(p.get("layers") or []) for p in pans))
    return float(w), float(h)


# ------------------------------------------------------------ sections
def new_section_id(doc):
    have = doc.get("sections") or {}
    n = len(have)
    while f"s{n}" in have:
        n += 1
    return f"s{n}"


def add_section(doc, geom):
    """A new section's geometry (a copy; without a card's run, time and panel).  Returns its
    id."""
    sid = new_section_id(doc)
    doc.setdefault("sections", {})[sid] = copy.deepcopy(
        {k: v for k, v in geom.items() if k not in ("run", "time_s", "panel")})
    return sid


def twin_section(geom):
    """A new section after geom: an x–z one's y–z twin, along the motion's across one, and
    back; no label of its own."""
    swap = {"x": "y", "y": "x", "along": "across", "across": "along"}
    return dict(geom, label="", orient=swap.get(geom.get("orient"), geom.get("orient")))


def write_section(doc, sid, changes):
    """Keys changed on a section (MISSING: no longer there)."""
    sec = doc["sections"][sid]
    for k, v in changes.items():
        if v is MISSING:
            sec.pop(k, None)
        else:
            sec[k] = v


def section_panels(doc, sid, kind="xsec"):
    """The panels of a kind showing section sid, in reading order."""
    return [p for p in panels_of(doc, kind) if p.get("section") == sid]


def split_section(doc, pid):
    """Panel pid gets a copy of its section of its own, so changes to it stay there.  Returns
    the copy's id."""
    p = panel_by_id(doc, pid)
    p["section"] = add_section(doc, doc["sections"][p["section"]])
    return p["section"]


def remove_section(doc, sid):
    """A section no cross-section shows out of the figure; plan views naming it go to the first
    left.  Why it can't be (a panel shows it, or it is the last), or None."""
    from . import nodes
    using = section_panels(doc, sid)
    if using:
        names = nodes.letters(doc)
        return f"Panel{'s' if len(using) > 1 else ''} " + ", ".join(
            names[p["id"]] for p in using) + " show" + ("" if len(using) > 1 else "s") + " it."
    if len(doc.get("sections") or {}) < 2:
        return "A figure keeps one section."
    del doc["sections"][sid]
    first = next(iter(doc["sections"]))
    for p in doc.get("panels") or []:
        if p.get("section") == sid:
            p["section"] = first
    return None


def xsec_panel(doc, cell, run, time_s, start_layers=(), section=None):
    """A new cross-section at cell.  After another: like it (run, time, layers), showing a new
    section, its twin.  The first: at the run and time of the last plan view, drawing its shared
    layers but section lines and sectors, which a section doesn't draw (no plan view: run, time_s
    and every shared layer; none: start_layers, shared from now on), showing the first section
    of the figure (none: `section`)."""
    mine = panels_of(doc, "xsec")
    new_id = next_panel_id(doc)
    if mine:
        p = _new_panel(doc, new_id, mine[-1], "xsec")
        p["section"] = add_section(doc, twin_section(doc["sections"][mine[-1]["section"]]))
    else:
        plans = panels_of(doc, "plan")
        like = plans[-1] if plans else None
        if not doc.get("layers") and like is None:
            for lay in start_layers:
                doc.setdefault("layers", {})[new_layer_id(doc)] = copy.deepcopy(lay)
        refs = [x["ref"] for x in like.get("layers") or [] if "ref" in x] if like \
            else list(doc.get("layers") or {})
        p = dict(id=new_id, kind="xsec", run=like["run"] if like else run,
                 time_s=like["time_s"] if like else time_s, title="", insets=[],
                 layers=[dict(ref=i, over={}) for i in refs if i in (doc.get("layers") or {})
                         and doc["layers"][i].get("type") not in ("line", "sector")])
        secs = doc.setdefault("sections", {})
        if not secs and section is not None:
            add_section(doc, section)
        p["section"] = next(iter(secs))
    p["cell"] = [int(cell[0]), int(cell[1]), 1, 1]
    doc["panels"].append(p)
    letters_in_order(doc)
    return p


def _cell_below(doc, r, c):
    """The first free cell under (r, c) in its column, the grid growing a row if none is."""
    free = free_cells(doc)
    hit = next((x for x in free if x[1] == c and x[0] > r), None)
    if hit is not None:
        return hit
    rows, cols = grid_shape(doc)
    set_grid(doc, rows + 1, cols)
    return rows, c


def panel_per_run(doc, pid, times=None):
    """A copy of panel pid (a cross-section or a time-height panel) for each other run, down its
    column, each with its layers and section.  A run with the same section or series already
    there is skipped.  times: {run id: the copy's time}.  Returns how many were made."""
    p = panel_by_id(doc, pid)
    kind = p["kind"]

    def what(q):
        return q.get("section") if kind == "xsec" else json.dumps(
            ((q.get("layers") or [{}])[0]).get("recipe"), sort_keys=True, default=float)

    have = {(q.get("run"), what(q)) for q in panels_of(doc, kind)}
    made = 0
    for r in doc["runs"]:
        rid = r["id"]
        if (rid, what(p)) in have:
            continue
        new = copy.deepcopy(p)
        new.pop("rowlabel", None)
        new.pop("letter", None)
        at = _cell_below(doc, *_cell(p)[:2])
        new.update(id=next_panel_id(doc), run=rid,
                   cell=[int(at[0]), int(at[1]), 1, 1])
        if kind == "th":
            for item in new.get("layers") or []:
                item["runs"] = [rid]
        if times and rid in times:
            new["time_s"] = float(times[rid])
        _new_inset_ids(doc, new)
        doc["panels"].append(new)
        made += 1
    letters_in_order(doc)
    return made


# ------------------------------------------------------------ series
def _follow_series(p):
    """A time-height panel's run is its series': the one shown (the first), as one_panel reads
    it by the panel's."""
    if p.get("kind") != "th":  # (an inset's layers: no kind, and no run of its own)
        return
    first = next((x for x in p.get("layers") or [] if x.get("source") not in ("table", "parcels")),
                 None)
    if first is None:
        p["run"] = None
    elif first.get("runs"):
        p["run"] = first["runs"][0]


def add_series(p, lay):
    """A series on top of panel p's own (time-height: the panel takes its run)."""
    add_own(p, lay)
    _follow_series(p)


def series_per_run(doc, p, j):
    """Series j of a time-series panel, a card per run in the panel, each in its run's colour:
    a series of several runs (or every run) splits; of one, a copy for each other run (a run
    with the same series there already is skipped).  Returns how many there are new."""
    items = places(doc, p)
    lay = items[j]
    view = dict(runs=doc.get("runs") or [])
    ids = [r["id"] for r in doc.get("runs") or []]

    def of_run(rid, **more):
        return dict(copy.deepcopy(lay), runs=[rid], color=figdraw.run_color(
            view, run_index(doc, rid)), **more)

    at = p["layers"].index(lay)
    mine = lay.get("runs")
    if mine is None or len(mine) > 1:
        runs = mine or ids
        if len(runs) < 2:
            return 0
        p["layers"][at:at + 1] = [of_run(rid, ens="") for rid in runs]
        return len(runs)
    recipe = json.dumps(lay.get("recipe"), sort_keys=True, default=float)
    have = {(x["runs"][0] if x.get("runs") else None,
             json.dumps(x.get("recipe"), sort_keys=True, default=float)) for x in items}
    new = [of_run(rid) for rid in ids if rid != mine[0] and (rid, recipe) not in have]
    p["layers"][at + 1:at + 1] = new
    return len(new)


def profile_per_run(doc, p, j):
    """Profile j of a panel, an entry per run in the panel, at the same time since each run's time
    zero: of several runs (or every run), it splits, each in its run's colour; of one, a copy for
    each other run, coloured automatically (a run with the same profile there already is
    skipped).  Returns how many are new."""
    items = places(doc, p)
    lay = items[j]
    view = dict(runs=doc.get("runs") or [])
    ids = [r["id"] for r in doc.get("runs") or []]
    mine = lay.get("runs")

    def moved(rid, a, **more):
        out = dict(copy.deepcopy(lay), run=rid, runs=[rid], **more)
        for key in ("time_s", "time_s1"):
            if out.get(key) is not None:
                out[key] = _moved(doc, float(lay[key]), a, rid)
        return out

    at = p["layers"].index(lay)
    if mine is None or len(mine) > 1:
        runs = mine or ids
        if len(runs) < 2:
            return 0
        p["layers"][at:at + 1] = [moved(rid, runs[0], ens="", color=figdraw.run_color(
            view, run_index(doc, rid))) for rid in runs]
        return len(runs)

    def what(x):
        return (x["runs"][0] if x.get("runs") else None, x.get("time_s"), x.get("time_s1"),
                json.dumps(x.get("recipe"), sort_keys=True, default=float))

    have = {what(x) for x in items}
    new = [moved(rid, mine[0], label="", color="") for rid in ids if rid != mine[0]]
    new = [x for x in new if what(x) not in have]
    p["layers"][at + 1:at + 1] = new
    return len(new)


def entry_titles(doc, kind):
    """Titles of a kind's panels from what each shows: a cross-section's
    section (with several runs: its run first), a time-height panel's run and series, a time
    series panel's labels.  Titles that name the runs turn the run labels off."""
    mine = panels_of(doc, kind)
    names = {r["id"]: r.get("label") or str(r.get("path", "")).rstrip("/").rsplit("/", 1)[-1]
             for r in doc.get("runs") or []}
    many = kind == "th" or (kind == "xsec" and len({p.get("run") for p in mine}) > 1)
    for p in mine:
        lays = figdraw.panel_layers(doc, p)
        if kind == "xsec":
            sec = (doc.get("sections") or {}).get(p.get("section")) or {}
            words = [sec.get("label") or section_words(sec)]
        elif kind == "th":
            words = [lays[0][1].get("label", "")] if lays else []
        else:
            words = [" / ".join(dict.fromkeys(x for x in (lay.get("label", "")
                                                          for _, lay in lays) if x))]
        if many and lays is not None and p.get("run") in names:
            words.insert(0, names[p["run"]])
        p["title"] = " – ".join(w for w in words if w)
    if many:
        style = doc.setdefault("style", {})
        style["run_label"] = dict(style.get("run_label") or {}, on=False)


def kind_size(doc):
    """A figure of one kind with a size of its own (not plan views or cross-sections, whose height
    goes by their shape), as its automatic size has it: (width, height) in; None: otherwise."""
    pans = doc.get("panels") or []
    kinds = {p["kind"] for p in pans}
    if kinds == {"sounding"}:
        return sounding_size(doc)
    if len(kinds) != 1 or KINDS[pans[0]["kind"]].size is None:
        return None
    w, h = KINDS[pans[0]["kind"]].size(*grid_shape(doc))
    return min(16.0, float(w)), min(16.0, float(h))


def panel_shape(s, run):
    """Height / width of a panel's plotting area, of its settings s (one_panel's): the plan-view
    area at equal scale, else a usual shape for the kind of panel."""
    if s["kind"] == "plan" and s["axes"].get("equal", True):
        d = s["domain"]
        if d["mode"] == "box" and d.get("box"):
            x0, x1, y0, y1 = d["box"]
        elif d["mode"] == "full":
            x0, x1, y0, y1 = run.xh[0], run.xh[-1], run.yh[0], run.yh[-1]
        else:
            return 1.0
        return abs(y1 - y0) / max(abs(x1 - x0), 1e-6)
    return KINDS[s["kind"]].shape


def fit_height(s, run):
    """A figure height (in) that fits the panels at the figure's width, of its settings s: their
    shape plus room for tick labels, titles and colorbars (an estimate: the layout engine does
    the rest)."""
    w, r, c = float(s["size"][0]), int(s["rows"]), int(s["cols"])
    line = float(s["font"].get("size", 10)) / 72.0  # a line of text (in)
    outer = s["axes"].get("ticklabels", "all") != "all"
    left, right, bottom, top = 4.5 * line, 0.15, 3.6 * line, 0.15
    gx, gy = (0.15, 0.15) if outer else (4.2 * line, 3.6 * line)
    above = any(s[k].get("on") and str(s[k].get("loc", "")).startswith("above")
                for k in ("letters", "time_label"))
    if s.get("titles") or above or (s["letters"].get("on") and s["kind"] == "table"):  # (always)
        top += 1.6 * line
        gy += 1.6 * line
    if s.get("suptitle"):
        top += 2.2 * line
    if s["kind"] == "table":
        gap = 1.6 * line if top > 0.15 else 0.15  # (no tick labels: only what is above it)
        tall = tbl_points(s) / 72.0 / figdraw.TBL_FILL
        return round(max(1.0, top + 0.05 + r * tall + (r - 1) * gap), 2)
    if s.get("row_titles"):
        left += 1.6 * line
    cb = s["colorbar"]
    mode = cb.get("mode", "shared") if s["kind"] in ("plan", "xsec", "th") else "none"
    side = (cb.get("location") or ("bottom" if cb.get("orientation", "horizontal")
                                   == "horizontal" else "right")) in ("left", "right")
    if mode != "none":
        if side:
            right += 0.9
            gx += 0.9 if mode in ("each", "col") else 0.0
        else:
            bottom += 0.8
            gy += 0.8 if mode in ("each", "row") else 0.0
    pw = max(0.3, (w - left - right - (c - 1) * gx) / c)
    shape = s.get("shape") or panel_shape(s, run)  # (given: panels of several shapes)
    return round(max(1.0, bottom + top + r * pw * shape + (r - 1) * gy), 2)


# ------------------------------------------------------------ annotations
def set_panel_colorbar(doc, pid, show=None, group=None):
    """Panel pid's part in the colorbars: whether its colours have a bar (show), and the bar it
    shares with the panels naming the same one (group; blank: as the figure's mode says)."""
    p = panel_by_id(doc, pid)
    cb = dict(p.get("colorbar") or {})
    if show is not None:
        cb.pop("show", None)
        if not show:
            cb["show"] = False
    if group is not None:
        cb.pop("group", None)
        if group.strip():
            cb["group"] = group.strip()
    if cb:
        p["colorbar"] = cb
    else:
        p.pop("colorbar", None)


def copy_annotations(doc, pid, new):
    """Panel `new` is a copy of pid: what is in pid is in the copy too."""
    for a in doc.get("annotations") or []:
        ids = ann_panels(a)
        if pid in ids and -1 not in ids:
            a["panel"] = [*ids, new]


def new_annotation(kind, panel, lims=None):
    """A new annotation of a kind: in the middle of the panel, so it
    shows.  lims: the (xlim, ylim) of the axis units; None: as fractions of the panel."""
    if lims is None:
        coords, (x, y), dx, dy = "axes", (0.5, 0.5), 0.15, 0.15
    else:
        (x0, x1), (y0, y1) = lims
        coords, x, y = "data", 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        dx, dy = 0.15 * (x1 - x0), 0.15 * (y1 - y0)
    r = min(abs(dx), abs(dy)) if coords == "data" else 0.15
    return dict(kind=kind, panel=panel, coords=coords, x=round(x, 2), y=round(y, 2),
                x2=round(x + dx, 2), y2=round(y + dy, 2), r=round(r, 2),
                text={"text": "A", "legend": "Entry"}.get(kind, ""), color="#000000",
                size=10.0 if kind != "marker" else 8.0, lw=1.5,
                ls="--" if kind in ("vline", "hline") else "-")


# ------------------------------------------------------------ placing by clicks
def place_section(doc, pid, a, b):
    """A-B (grid km) from two clicks in plan view pid: into the panel's section if that is an A-B
    one, else the first A-B section, else the only section, else a new one, which the panel then
    shows.  Returns its id."""
    p = panel_by_id(doc, pid)
    secs = doc.setdefault("sections", {})
    sid = p.get("section") if secs.get(p.get("section"), {}).get("orient") == "ab" else None
    sid = sid or next((i for i, s in secs.items() if s.get("orient") == "ab"), None)
    if sid is None and len(secs) == 1:
        sid = next(iter(secs))
    if sid is None:
        sid = add_section(doc, section_defaults(orient="ab", pos="fixed"))
    write_section(doc, sid, dict(orient="ab", a=[float(v) for v in a], b=[float(v) for v in b]))
    p["section"] = sid
    return sid


def set_area(doc, box, kind="plan", pid=None):
    """The kind's panels, or panel pid alone, show the fixed box [x0, x1, y0, y1] (grid km)."""
    if pid is None:
        k = doc.setdefault("kinds", {}).setdefault(kind, {})
    else:
        k = panel_by_id(doc, pid).setdefault("opts", {})
    k["domain"] = dict(k.get("domain") or {}, mode="box", box=[round(float(v), 2) for v in box])


# ------------------------------------------------------------ zoom insets
INSET_KINDS = figdraw.INSET_KINDS
INSET_LOOK = dict(mark=True, connect=True, color="#000000", lw=1.0, ls="-", ticks=False)
INSET_PLACE = dict(loc="upper right", size=0.4, x=None, y=None, h=None)


def inset_by_id(p, iid):
    return next((ins for ins in p.get("insets") or [] if int(ins["id"]) == int(iid)), None)


def new_inset_id(doc):
    """An id no inset has (arrays go by it, in the whole figure: spec.doc)."""
    return 1 + max([int(ins["id"]) for p in doc.get("panels") or [] for ins in p.get("insets") or []]
                   or [0])


def _new_inset_ids(doc, p):
    """A panel just copied, not yet in the document: its insets get ids of their own."""
    start = new_inset_id(doc)
    for n, ins in enumerate(p.get("insets") or []):
        ins["id"] = start + n


def clear_corner(area, lims):
    """The corner of a panel whose axis limits are `lims` furthest from `area` (x0, x1, y0, y1)
    in it, where an inset of it hides the least of what it zooms in on."""
    (a, b), (c, e) = lims
    u = (0.5 * (area[0] + area[1]) - a) / ((b - a) or 1.0)
    w = (0.5 * (area[2] + area[3]) - c) / ((e - c) or 1.0)
    return f"{'lower' if w > 0.5 else 'upper'} {'left' if u > 0.5 else 'right'}"


def set_inset_area(p, ins, box, center=None):
    """What inset `ins` of panel p shows: box [x0, x1, y0, y1], in grid km for a plan view, in the
    panel's axis units for a cross-section.  center: the storm's (x, y) in grid km when the panel
    follows it, and the inset follows too, staying square, over the same part of the storm."""
    box = [round(float(v), 2) for v in box]
    if p["kind"] != "plan":
        ins["view"] = box
        return
    opts = ins.setdefault("opts", {})
    if center is None:
        opts["domain"] = dict(mode="box", box=box)
    else:
        half = round(0.5 * max(box[1] - box[0], box[3] - box[2]), 2)
        opts["domain"] = dict(mode="storm", half=half,
                              off=[round(0.5 * (box[0] + box[1]) - float(center[0]), 2),
                                   round(0.5 * (box[2] + box[3]) - float(center[1]), 2)])


def add_inset(doc, pid, box, lims=None, center=None):
    """A new zoom inset of panel pid showing box (set_inset_area), with the panel's layers, in the
    corner furthest from what it shows.  lims: the panel's axis limits, with box in those units
    (cross-section) or at the same origin (plan view).  Returns it."""
    p = panel_by_id(doc, pid)
    ins = dict(id=new_inset_id(doc), loc="upper right", size=0.4)
    if lims is not None:
        ins["loc"] = clear_corner(box, lims)
    set_inset_area(p, ins, box, center)
    p.setdefault("insets", []).append(ins)
    return ins


def remove_inset(doc, pid, iid):
    p = panel_by_id(doc, pid)
    p["insets"] = [ins for ins in p.get("insets") or [] if int(ins["id"]) != int(iid)]


def own_inset_layers(doc, pid, iid, own):
    """An inset's layers its own, starting as the panel's (each still following a shared layer, but
    for what it changes), or (own False) back to the panel's."""
    p = panel_by_id(doc, pid)
    ins = inset_by_id(p, iid)
    if own:
        ins["layers"] = copy.deepcopy(p.get("layers") or [])
    else:
        ins.pop("layers", None)


# ------------------------------------------------------------ 3D scenes
SCENE_START_AXES = dict(xlabel="", ylabel="", ticklabels="all", equal=False)  # (as from_3d's)


def scene_kind_block(doc):
    """The scene settings all 3D scenes share, as the document holds them."""
    return ((doc.get("kinds") or {}).get("scene") or {}).get("scene3d") or {}


def scene_own(doc, pid):
    """The scene settings panel pid has of its own, as the document holds them."""
    return (panel_by_id(doc, pid).get("opts") or {}).get("scene3d") or {}


def scene_block(doc, pid=None):
    """A panel's whole scene block, with the defaults, or the kind's (pid None)."""
    own = {} if pid is None else scene_own(doc, pid)
    return scene3d_of(dict(scene3d={**scene_kind_block(doc), **own}))


def scene_kind_write(doc, key, value):
    k = doc.setdefault("kinds", {}).setdefault("scene", {})
    k["scene3d"] = dict(k.get("scene3d") or {}, **{key: value})


def write_scene(doc, pid, key, value):
    """A scene setting (a key of the block, whole) on panel pid, or all scenes (pid None).  The
    only scene's goes to the kind unless it holds that setting itself: there is nothing to differ
    from, and what reads the kind's block keeps working."""
    if pid is None or (key not in scene_own(doc, pid) and len(panels_of(doc, "scene")) < 2):
        scene_kind_write(doc, key, value)
        return
    opts = panel_by_id(doc, pid).setdefault("opts", {})
    opts["scene3d"] = dict(opts.get("scene3d") or {}, **{key: value})


def scene_take_back(doc, pid, key):
    """Panel pid's own setting gone: it has all scenes' again."""
    p = panel_by_id(doc, pid)
    opts = p.get("opts") or {}
    own = dict(opts.get("scene3d") or {})
    own.pop(key, None)
    if own:
        opts["scene3d"] = own
    else:
        opts.pop("scene3d", None)
    if not opts:
        p.pop("opts", None)


# ------------------------------------------------------------ the grid: filling panels
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
    next_id = next_panel_id(doc)
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
    drop_annotations(doc, gone)
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
    settle_grid(doc)  # (panels of other kinds past the new edge)
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
