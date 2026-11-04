"""Soundings in the inspector: panels whose layers are entries of their own (each with its run,
time and place), rather than shared map layers.  Where you click says what an edit reaches:

  All soundings   the kind's settings: skew-T, hodograph, the panels' look; new panels
  a panel         its soundings, its title and place, and its own look
  a sounding      that sounding

Nothing here is sounding-only but `make_card`, `_entries` and the buttons that add them: the
other kinds of entries (M7) take the same pane."""

import html

import panel as pn

from .. import draw as figdraw
from ..cards import SoundingCard, _grid
from . import docedit as de, nodes
from .gridview import map_soundings, new_sounding
from .layerrow import InPanel, LayerRow
from .looks import (KIND_SECTIONS, LAYOUT_HIDES, PANEL_KEYS, Scope, Sections, panels_differ,
                    sounding_extra)


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


def _head(text):
    return pn.pane.HTML(f"<b>{html.escape(text)}</b>", margin=(8, 4, 0, 4))


def _button(name, on_click, tip="", primary=False):
    b = pn.widgets.Button(name=name, height=32, margin=(4, 4), description=tip or None,
                          button_type="primary" if primary else "light",
                          button_style="outline")
    b.on_click(lambda e: on_click())
    return b


class EntryPane:
    kind = "sounding"
    one = "sounding"
    make_card = SoundingCard

    def __init__(self, inspector):
        self.ins, self.shell = inspector, inspector.shell

    # ------------------------------------------------------------ what a section shows
    def _layout(self, doc, scope):
        """The layout at a scope: a panel's, or as the first panel of the kind has it."""
        res = figdraw.resolve(doc)
        pid = scope.pid if scope.pid is not None else de.panels_of(doc, self.kind)[0]["id"]
        q = next(x for x in res["panels"] if x["id"] == pid)
        return figdraw.sounding_layout(figdraw.panel_view(res, q).get("skewt", {}))

    def _looks(self, doc, scope):
        return Sections(self.ins, scope, [self.kind], sounding_extra(self._layout(doc, scope)),
                        redraws=("skewt.layout",))

    def _shows(self, doc, scope, section):
        """Whether a look section reaches what the layout draws."""
        return self._layout(doc, scope) not in LAYOUT_HIDES.get(section, ())

    # ------------------------------------------------------------ all of the kind
    def kind_objs(self, doc):
        mine = de.panels_of(doc, self.kind)
        names = nodes.letters(doc)
        objs = [_note("Panels " + ", ".join(names[p["id"]] for p in mine)),
                pn.Row(_button("+ Sounding panel", self.add_panel, primary=True,
                               tip="In the first free cell, or a new row or column"),
                       _button("+ The map's soundings", self.add_map_panels,
                               tip="A panel for each sounding marked in the viewer's Sounding "
                                   "tool"), margin=0)]
        scope = Scope(self.kind)
        looks = self._looks(doc, scope)
        objs += [c for c in (looks.card(s) for s in KIND_SECTIONS[self.kind]
                             if self._shows(doc, scope, s)) if c is not None]
        keys = [k for sec in PANEL_KEYS[self.kind].values() for k in sec]
        differ = panels_differ(doc, self.kind, keys)
        if differ:
            objs.append(_note("Set in a panel alone, so changes here skip it: panel"
                              + ("s " if len(differ) > 1 else " ") + ", ".join(differ) + "."))
        return f"All {nodes.kind_name(self.kind, len(mine))}", objs

    def add_panel(self):
        return self.ins.grid.add_panel(self.kind)

    def add_map_panels(self):
        """Each of the viewer's soundings in a panel of its own."""
        shell = self.shell
        new = map_soundings(shell)
        if not new:
            shell.say("No soundings yet: click the map with the Sounding tool first.", True)
            return

        def apply(d):
            for e in new:
                p = de.add_panel(d, self.kind, de.next_cell(d), [de.plain(e)])
                self.ins.folds.setdefault(f"p:{p['id']}:own0", True)
        shell.edit(apply, node=shell.node)

    # ------------------------------------------------------------ a panel
    def panel_objs(self, doc, node):
        p = nodes.panel_of(doc, node)
        pid, letter = p["id"], nodes.letters(doc)[p["id"]]
        shell = self.shell

        def set_keys(**kw):
            def apply(d):
                q = de.panel_by_id(d, pid)
                for k, v in kw.items():
                    if v is None:
                        q.pop(k, None)
                    else:
                        q[k] = v
            shell.edit(apply)

        title = pn.widgets.TextInput(name="Title", value=p.get("title") or "")
        title.param.watch(lambda ev: set_keys(title=ev.new.strip()), "value")
        rowlabel = pn.widgets.TextInput(name="Row label (left)", value=p.get("rowlabel") or "",
                                        placeholder="none")
        rowlabel.param.watch(lambda ev: set_keys(rowlabel=ev.new.strip() or None), "value")
        objs = [_grid(title, rowlabel, n=2), _head("Soundings"),
                _note("Soundings of one panel share its skew-T (colour = sounding)."),
                pn.Row(_button("+ Sounding", lambda: self.add_entry(pid), primary=True),
                       _button("+ The map's soundings", lambda: self.add_map_entries(pid)),
                       margin=0)]
        lays = figdraw.panel_layers(doc, p)
        for j, _ in enumerate(lays):
            objs.append(self._entry_row(doc, pid, j, len(lays)).panel)
        if not lays:
            objs.append(_note("No soundings here: add one above."))
        objs += self._panel_looks(doc, pid)
        objs += self.ins.grid.place_objs(doc, pid)
        return f"Panel {letter}", objs

    def add_entry(self, pid):
        """A new sounding in a panel, open."""
        shell = self.shell
        new = new_sounding(shell)

        def apply(d):
            p = de.panel_by_id(d, pid)
            de.add_own(p, new)
            self.ins.folds[f"p:{pid}:own{len(de.places(d, p)) - 1}"] = True
        shell.edit(apply, node=shell.node)

    def add_map_entries(self, pid):
        """The viewer's soundings into this panel."""
        shell = self.shell
        new = map_soundings(shell)
        if not new:
            shell.say("No soundings yet: click the map with the Sounding tool first.", True)
            return
        shell.edit(lambda d: [de.add_own(de.panel_by_id(d, pid), de.plain(e)) for e in new],
                   node=shell.node)

    def _entry_row(self, doc, pid, j, n, fixed=False):
        shell = self.shell

        def step(fn, *args):
            shell.edit(lambda d: fn(d, de.panel_by_id(d, pid), j, *args), node=shell.node)

        moves = {}
        if not fixed:
            if j > 0:
                moves["up"] = lambda: step(de.move_in_panel, -1)
            if j < n - 1:
                moves["down"] = lambda: step(de.move_in_panel, 1)
            moves["copy"] = lambda: step(de.copy_in_panel)
            moves["remove"] = lambda: step(de.remove_in_panel)
        return LayerRow(self.ins, InPanel(doc, pid, j), moves=moves, fixed=fixed, opened=n == 1,
                        extras=self._panel_pick, make_card=type(self).make_card, kind=self.kind)

    def _panel_pick(self, row):
        """Which of the kind's panels a sounding is in: it moves there."""
        shell, t = row.shell, row.target
        doc = shell.doc
        names = nodes.letters(doc)
        mine = de.panels_of(doc, self.kind)
        if len(mine) < 2:
            return []
        pick = pn.widgets.Select(name="In panel", value=t.pid,
                                 options={names[p["id"]]: p["id"] for p in mine})

        def on_pick(ev):
            shell.edit(lambda d: de.move_entry(d, t.pid, t.j, ev.new), node=f"panel:{ev.new}")

        pick.param.watch(on_pick, "value")
        return [_grid(pick, n=2)]

    def _panel_looks(self, doc, pid):
        """The panel's own look: what it inherits, each setting to change here."""
        scope = Scope(self.kind, pid)
        looks = self._looks(doc, scope)
        objs = []
        for section, keys in PANEL_KEYS[self.kind].items():
            if not self._shows(doc, scope, section):
                continue
            card = looks.card(section, only=keys)
            if card is not None:
                objs += looks.chips(keys)
                objs.append(card)
        return objs

    # ------------------------------------------------------------ one sounding
    def layer_objs(self, doc, node):
        p = nodes.panel_of(doc, node)
        j = int(node.rsplit(":", 1)[1])
        letter = nodes.letters(doc)[p["id"]]
        row = self._entry_row(doc, p["id"], j, 1, fixed=True)
        lay = figdraw.panel_layers(doc, p)[j][1]
        return f"{nodes.sounding_name(lay)} in panel {letter}", [row.panel]
