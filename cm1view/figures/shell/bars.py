"""Which panel's settings a colorbar answers to.  Each bar has one controlling panel, the first in
reading order of the panels sharing it: a shared bar's label, ticks and arrows are set there, and
reach every panel on the bar (the drawing unites them: an older figure's differences still show);
its colours are those of the controlling panel, so the others' follow it."""

from .. import draw as figdraw
from . import docedit as de

BAR_KEYS = de.BAR_KEYS
COLOUR_KEYS = ("cmap", "reverse", "white_first", "vmin", "vmax", "nlevels", "scale", "levels")


def place(doc, p):
    """The place in panel p of the layer its bar speaks for, or None."""
    return next((j for j, (_, lay) in enumerate(figdraw.panel_layers(doc, p))
                 if figdraw.bar_fill(lay)), None)


def bar_of(doc, pid, as_if_shown=False):
    """Panel pid's bar: dict(members (panel ids, the controlling one first), follows (they share
    its colours)), or None when it has none.  as_if_shown: were its "has a bar" on."""
    if as_if_shown:
        doc = dict(doc, panels=[
            dict(p, colorbar=dict(p.get("colorbar") or {}, show=True)) if p["id"] == pid else p
            for p in doc.get("panels") or []])
    spec = figdraw.upgrade(doc)[0]
    members = figdraw.bar_members(spec).get(pid)
    if members is None:
        return None
    p = next(q for q in spec["panels"] if q["id"] == pid)
    mixed = figdraw._mixed_kinds(spec, int(p.get("block", 0)))
    named = (p.get("colorbar") or {}).get("group")
    # (kinds mixed, unnamed: other colours make a bar of their own, so they can differ)
    return dict(members=members, follows=len(members) > 1 and (bool(named) or not mixed))


def _lays(doc, members):
    """[(panel, place, layer)] of the panels on a bar."""
    out = []
    for pid in members:
        p = de.panel_by_id(doc, pid)
        j = place(doc, p)
        out.append((p, j, figdraw.panel_layers(doc, p)[j][1]))
    return out


def values(doc, bar):
    """{key: value} a bar shows now: the first label and ticks among its panels, and its arrows
    (several: Auto if any is, as the data decide there; else their union)."""
    lays = [x[2] for x in _lays(doc, bar["members"])]
    ends = [lay.get("extend") or "neither" for lay in lays]
    return dict(cbar_label=next((lay["cbar_label"] for lay in lays if lay.get("cbar_label")), ""),
                cbar_ticks=next((lay["cbar_ticks"] for lay in lays if lay.get("cbar_ticks")), ""),
                extend="auto" if "auto" in ends else figdraw.union_extend(ends))


def set_value(doc, bar, key, value):
    """A setting of the bar, on all its panels."""
    for p, j, _ in _lays(doc, bar["members"]):
        de.write_panel(doc, p, j, {key: value})


def follow_colours(doc, pid, j, changes):
    """The controlling panel's layer j changed: colours among the changes reach the bar's others."""
    colours = {k: v for k, v in changes.items() if k in COLOUR_KEYS}
    if not colours:
        return
    p = de.panel_by_id(doc, pid)
    if place(doc, p) != j:
        return
    bar = bar_of(doc, pid)
    if bar is None or not bar["follows"] or bar["members"][0] != pid:
        return
    for q, at, _ in _lays(doc, bar["members"][1:]):
        de.write_panel(doc, q, at, colours)


def colours_differ(doc, bar, pid):
    """Whether panel pid's colours aren't those its bar shows."""
    lays = {p["id"]: lay for p, _, lay in _lays(doc, bar["members"])}
    return any(lays[pid].get(k) != lays[bar["members"][0]].get(k) for k in COLOUR_KEYS)


def match_colours(doc, bar, pid):
    """Panel pid in the colours its bar shows."""
    lays = {p["id"]: (p, j, lay) for p, j, lay in _lays(doc, bar["members"])}
    first = lays[bar["members"][0]][2]
    p, j, lay = lays[pid]
    de.write_panel(doc, p, j, {k: first[k] if k in first else de.MISSING
                               for k in COLOUR_KEYS if k in first or k in lay})


def layer_has_bar(doc, lid):
    """Whether a bar speaks for shared layer lid."""
    for p in doc.get("panels") or []:
        j = place(doc, p)
        if j is not None and figdraw.panel_layers(doc, p)[j][0] == lid \
                and bar_of(doc, p["id"]) is not None:
            return True
    return False


def clear_bar_overrides(doc, lid, keys):
    """A shared layer's bar settings changed: they reach every panel drawing it."""
    for p in doc.get("panels") or []:
        for item in p.get("layers") or []:
            if item.get("ref") == lid:
                for k in keys:
                    (item.get("over") or {}).pop(k, None)
