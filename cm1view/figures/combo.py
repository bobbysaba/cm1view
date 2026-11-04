"""Figures made of parts, a form older figures were saved in (figdraw: kind "combo"): they open by
conversion to one grid (spec.to_doc).

Each part is a figure of its own, drawn side by side, stacked or anywhere on a grid of its own."""

import json

from . import draw as figdraw, spec as fg

def share_sections(parts, src):
    """The plan-view and section parts of a figure of parts take part src's list of
    cross-sections (when src is one of those kinds), in place: they share one list.  A
    section part of cards keeps its cards' runs, times and panels (the cards src has
    beyond its own: new panels, at its first card's run and time)."""
    if src.get("kind") not in ("plan", "xsec") or not src.get("sections"):
        return parts
    new = json.loads(json.dumps(src["sections"], default=float))
    for p in parts:
        if p is src or p.get("kind") not in ("plan", "xsec"):
            continue
        old = figdraw.xsec_cards(p) if src.get("kind") == "plan" else None
        if old is None:
            p["sections"] = json.loads(json.dumps(new))
            continue
        nxt = 1 + max(int(c.get("panel", 0)) for c in old)
        out = []
        for k, sec in enumerate(new):
            keys = {c: old[min(k, len(old) - 1)].get(c) for c in fg.CARD_KEYS}
            if k >= len(old):
                keys["panel"], nxt = nxt, nxt + 1
            out.append(dict(fg.card_section(sec), **keys))
        p["sections"] = out
    return parts


def combine(parts, arrange="row", title="", like=None, size=None, one_colorbar=False,
            grid=None):
    """A figure of parts (figdraw kind "combo"): as wide as the parts side by side (as
    tall when stacked; on a custom grid, `grid`, as its columns and rows need), or `size`
    [width, height] in (either None: that default); its export settings, fonts and
    background those of `like`, and with one_colorbar a colorbar for the whole figure
    styled as like's."""
    like = like or parts[0]
    row = arrange == "row"
    w = [float(p["size"][0]) for p in parts]
    h = [float(p["size"][1]) for p in parts]
    own = list(size or [None, None])
    extra = {}
    if arrange == "grid":
        g = figdraw.grid_layout(parts, grid)
        W, H = sum(g["widths"]), sum(g["heights"])
        extra["part_grid"] = dict(grid or {}, rows=g["rows"], cols=g["cols"])
    else:
        W, H = (sum(w), max(h)) if row else (max(w), sum(h))
    W, H = float(own[0]) if own[0] else W, float(own[1]) if own[1] else H
    runs, seen = [], set()
    for p in parts:
        for r in p.get("runs") or []:
            if r["path"] not in seen:
                seen.add(r["path"])
                runs.append(r)
    cb = dict(like.get("colorbar", {}), mode="figure") if one_colorbar else dict(mode="parts")
    return dict(version=1, kind="combo", arrange=arrange, parts=parts, size=[W, H],
                size_set=[own[0] or None, own[1] or None], colorbar=cb,
                runs=runs, suptitle=title, export=like.get("export", {}),
                background=like.get("background", "white"), font=like.get("font", {}),
                mplstyle=like.get("mplstyle", ""), spacing=like.get("spacing", {}), **extra)
