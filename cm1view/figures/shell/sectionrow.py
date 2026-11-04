"""A section's geometry in the inspector: a row over the old editor's SectionCard, without its
run, time and panel, which are the panel's here.  Sections are shared: every cross-section showing
one and the Section line layers of plan views follow it."""

import html

import panel as pn

from ..cards import SectionCard
from . import docedit as de, nodes
from .layerrow import ASection, LayerRow


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


def _use_ab(row):
    """Section `row`'s from the map's A–B points."""
    pts = row.shell.v.xs_pts
    if len(pts) != 2:
        row.shell.say("Draw a cross-section on the map first (Cross-section click mode, points A "
                      "and B).", True)
        return
    row.card.set_ab(pts[0], pts[1])
    row.card.ed.request()


def section_row(ins, doc, sid, where="", opened=False, moves=None, words=None):
    """The row of section sid.  where: part of its folding's key (a panel's row folds apart from
    the kind's); words: {doc: its note} above the settings; moves as LayerRow's."""
    def extras(row):
        card = row.card
        card.tracked(any(r.get("track") for r in row.shell.doc["runs"]))
        card.w["label"].name = "Name (blank: automatic)"
        card.ab.on_click(lambda e: _use_ab(row))
        return [] if words is None else words(row.shell.doc)

    # (kind plan: the card shows no run, time or panel)
    return LayerRow(ins, ASection(sid, where), moves=moves, opened=opened, extras=extras,
                    make_card=SectionCard, kind="plan")


def section_objs(ins, doc):
    """All the figure's sections: to add one, each with what shows it, removing those no panel
    shows."""
    shell = ins.shell
    secs = doc.get("sections") or {}
    add = pn.widgets.Button(name="+ Section", button_type="light", button_style="outline",
                            height=30, margin=(4, 4),
                            description="A new section after the last: an x–z one's y–z twin, "
                                        "along the motion's across one")

    def on_add(e):
        def apply(d):
            last = list(d.get("sections", {}).values())
            geom = de.twin_section(last[-1]) if last else {}
            ins.folds[f"sec:{de.add_section(d, geom)}"] = True
        shell.edit(apply, node=shell.node)

    add.on_click(on_add)

    def row_of(sid):
        def words(now):
            names = nodes.letters(now)
            using = de.section_panels(now, sid)
            return [_note("Cross-section panels " + ", ".join(names[p["id"]] for p in using) + "."
                          if using else "No cross-section shows it: a plan view's Section line "
                                        "layer draws it.")]

        moves = dict(copy=lambda: shell.edit(lambda d: _copied(ins, d, sid), node=shell.node))
        if de.remove_section(de.plain(doc), sid) is None:
            moves["remove"] = lambda: shell.edit(lambda d: de.remove_section(d, sid),
                                                 node=shell.node)
        return section_row(ins, doc, sid, opened=len(secs) == 1, moves=moves, words=words).panel

    return [pn.pane.HTML(f"<b>{html.escape('Sections')}</b>", margin=(8, 4, 0, 4)),
            _note("Where the cross-sections and section lines run. A change reaches everything "
                  "showing the section."), add, *[row_of(sid) for sid in secs]]


def _copied(ins, doc, sid):
    new = de.add_section(doc, doc["sections"][sid])
    ins.folds[f"sec:{new}"] = True
