"""What the tree of a figure document holds, without widgets.  A node is a string:

  figure, runs, kind:<kind>, panel:<id>, layer:<panel id>:<place in the panel>"""

from .. import draw as figdraw
from ..cards import TYPE_LABEL
from ..draw.base import _cell
from ..kinds import KINDS

FIGURE, RUNS, KIND_PREFIX = "figure", "runs", "kind:"


def in_order(doc):
    """The document's panels in reading order, as they are drawn and lettered."""
    return sorted(doc.get("panels") or [], key=lambda p: _cell(p)[:2])


def letters(doc):
    """{panel id: its letter}."""
    out = {}
    for n, p in enumerate(in_order(doc)):
        at = n if p.get("letter") is None else int(p["letter"])
        out[p["id"]] = figdraw.panel_letter(at, "{a}")
    return out


def kind_name(kind, n):
    """All panels of a kind, in words: "plan views (6)"."""
    k = KINDS.get(kind)
    return f"{k.name if k else kind} ({n})"


def layer_name(lay, fields=None):
    """A layer in words: its type and field, or an entry's label or field."""
    if lay.get("type") == "sounding":
        return sounding_name(lay)
    head = TYPE_LABEL.get(lay.get("type"), "")
    recipe = lay.get("recipe") if isinstance(lay.get("recipe"), dict) else {}
    field = lay.get("field") or recipe.get("field")
    what = fields[field].label if fields is not None and field in fields else field
    return " · ".join(str(x) for x in (head, lay.get("label") or what) if x) or \
        str(lay.get("type") or "entry")


def sounding_name(lay):
    """A sounding in words: its label, or where it is, and when."""
    where = {"trk": "storm", "pt": "point", "mean": "domain mean"}.get(
        (lay.get("where") or {}).get("kind"), "")
    when = f"{float(lay['time_s']) / 60:g} min" if lay.get("time_s") is not None else ""
    return " · ".join(x for x in ("Sounding", lay.get("label") or where, when) if x)


def panel_name(doc, p, runs=None):
    """A panel in words, after its letter: its run and time."""
    bits = []
    if len(doc.get("runs") or []) > 1 and p.get("run") is not None:
        bits.append((runs or run_names(doc)).get(p["run"], "no such run"))
    if p.get("time_s") is not None:
        bits.append(f"{float(p['time_s']) / 60:g} min")
    if p.get("title"):
        bits.append(f"“{p['title']}”")
    return " · ".join(bits)


def run_names(doc):
    """{run id: its label, or its folder's name}."""
    return {r["id"]: r.get("label") or str(r.get("path", "")).rstrip("/").rsplit("/", 1)[-1]
            for r in doc.get("runs") or []}


def tree_items(doc, fields=None):
    """The rows of the tree, in order: [{id, label, depth}].  Panels sit under All <kind>,
    their layers under them."""
    panels, names, runs = in_order(doc), letters(doc), run_names(doc)
    out = [dict(id=FIGURE, label="Figure", depth=0),
           dict(id=RUNS, label=f"Runs ({len(doc.get('runs') or [])})", depth=0)]
    for kind in dict.fromkeys(p["kind"] for p in panels):
        mine = [p for p in panels if p["kind"] == kind]
        out.append(dict(id=f"kind:{kind}", label=f"All {kind_name(kind, len(mine))}", depth=0))
        for p in mine:
            tail = panel_name(doc, p, runs)
            out.append(dict(id=f"panel:{p['id']}", depth=1,
                            label=f"{names[p['id']]}  {tail}" if tail else names[p["id"]]))
            for j, (_, lay) in enumerate(figdraw.panel_layers(doc, p)):
                out.append(dict(id=f"layer:{p['id']}:{j}", depth=2, label=layer_name(lay, fields)))
    return out


def panel_of(doc, node):
    """The panel a panel or layer node is of (None: none, or no longer there)."""
    head, _, rest = node.partition(":")
    if head not in ("panel", "layer"):
        return None
    pid = int(rest.partition(":")[0])
    return next((p for p in doc.get("panels") or [] if p["id"] == pid), None)


def outlined(doc, node):
    """The ids of the panels node speaks for (none: the figure, the runs)."""
    if node.startswith("kind:"):
        kind = node.partition(":")[2]
        return [p["id"] for p in doc.get("panels") or [] if p["kind"] == kind]
    p = panel_of(doc, node)
    return [] if p is None else [p["id"]]


def still_there(doc, node):
    """Whether node is in the document (after an undo, or a new conversion)."""
    if node in (FIGURE, RUNS):
        return True
    if node.startswith("kind:"):
        return bool(outlined(doc, node))
    p = panel_of(doc, node)
    if p is None:
        return False
    if node.startswith("layer:"):
        return int(node.rsplit(":", 1)[1]) < len(figdraw.panel_layers(doc, p))
    return True


def scope(doc, node):
    """What an edit made here reaches, in words."""
    if node == FIGURE:
        return "Applies to the whole figure"
    if node == RUNS:
        return "Applies to every panel using these runs"
    if node.startswith("kind:"):
        kind = node.partition(":")[2]
        n = len(outlined(doc, node))
        return f"Applies to all {kind_name(kind, n)}"
    p = panel_of(doc, node)
    return f"Applies to panel {letters(doc)[p['id']]} only"


def runs_used(doc):
    """{run id: the ids of the panels using it}: as their run, or in a layer's."""
    out = {}

    def add(rid, pid):
        out.setdefault(rid, [])
        if pid not in out[rid]:
            out[rid].append(pid)

    for p in doc.get("panels") or []:
        if p.get("run") is not None:
            add(p["run"], p["id"])
        for _, lay in figdraw.panel_layers(doc, p):
            figdraw.run_ids(lay, lambda v, pid=p["id"]: add(v, pid))
    return out


def pick_at(boxes, x, y):
    """The panel whose box ([left, right, top, bottom] fractions) holds the point, or None."""
    return next((i for i, b in boxes.items() if b[0] <= x <= b[1] and b[2] <= y <= b[3]), None)
