"""Zoom insets in the inspector.  An inset is a box in a plan view or cross-section with lines to
what it zooms in on (spec.doc).  On a panel: its insets' place in the tree, and adding one.  On an
inset's node: where it sits, what it shows, how its box and lines look, and its layers, which are
the panel's until it has its own.  Dragging in the preview does the first two too (placing)."""

import html

import panel as pn

from ..cards import _grid, _hex
from ..cards.base import SECTION, _f
from . import docedit as de, nodes
from .layerrow import InInset, LayerRow, own_time_widgets
from .looks import AREA_OF_A_PANEL, InsetScope, Sections, area_extra
from .planview import new_layer

PLACE, AREA, LOOK = "Where it sits", "Area", "Box and lines"
LOCS = {"Upper right": "upper right", "Upper left": "upper left", "Lower right": "lower right",
        "Lower left": "lower left", "At x, y (left, bottom)": "custom"}
STYLES = {"Solid": "-", "Dashed": "--", "Dotted": ":", "Dash-dot": "-."}
PLACE_KEYS = tuple(de.INSET_PLACE)
LOOK_KEYS = tuple(de.INSET_LOOK)


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


def _button(name, on_click, tip=None):
    b = pn.widgets.Button(name=name, height=30, margin=(4, 4), button_type="light",
                          button_style="outline", description=tip)
    b.on_click(lambda e: on_click())
    return b


class _Card:
    """A section of an inset's own settings: counts on its header what differs from a new inset's,
    and has a reset, as the look sections (looks.Sections) do."""

    def __init__(self, pane, node, title, keys, defaults, body, opened=False):
        self.pane, self.node, self.keys, self.defaults = pane, node, keys, defaults
        self.marks = dict(card=None, header=None)
        ins = pane.ins
        key = f"inset:{node}:{title}"
        reset = pn.widgets.Button(name="↺ Back to a new inset's", height=26, margin=(2, 2),
                                  button_type="light", button_style="outline",
                                  description="Every setting of this section. Undo takes it back")
        reset.on_click(lambda e: self.reset())
        self.line = pn.Row(pn.Spacer(sizing_mode="stretch_width"), reset, margin=0,
                           sizing_mode="stretch_width")
        self.card = pn.Card(self.line, *body, title=title,
                            collapsed=not ins.folds.get(key, opened), **SECTION)
        self.marks["card"] = self.card
        self.card.param.watch(lambda ev: ins.folds.__setitem__(key, not ev.new), "collapsed")
        ins.live.append(self)
        self.refresh()

    def _inset(self, doc):
        return nodes.inset_of(doc, self.node)

    def refresh(self):
        inset = self._inset(self.pane.shell.doc)
        if inset is None:  # (taken away, the tree about to follow)
            return
        n = sum(1 for k in self.keys if k in inset and inset[k] != self.defaults[k])
        Sections._header(self.marks, n)
        self.line.visible = bool(n)

    def reset(self):
        def apply(d):
            inset = self._inset(d)
            for k in self.keys:
                inset.pop(k, None)
        self.pane.shell.edit(apply, node=self.node)


class InsetPane:
    def __init__(self, inspector):
        self.ins, self.shell = inspector, inspector.shell

    # ------------------------------------------------------------ on a panel
    def panel_objs(self, doc, p):
        """What a panel's settings say of its insets."""
        if p["kind"] not in de.INSET_KINDS:
            return []
        pid, n = p["id"], len(p.get("insets") or [])
        hint = "Under the panel in the tree." if n else (
            "A box in the panel showing part of it larger, with lines to where. Or pick <b>Drag: "
            "new zoom inset</b> above the preview and drag over what to zoom in on.")
        return [pn.pane.HTML("<b>Zoom insets</b>" + (f" ({n})" if n else ""), margin=(8, 4, 0, 4)),
                _note(hint), _button("+ Zoom inset", lambda: self.add(pid),
                                     "Of the middle of what the panel shows; then change it")]

    def add(self, pid):
        """A new inset of the middle third of what panel pid shows in the preview."""
        shell, pl = self.shell, self.shell.placing
        p = de.panel_by_id(shell.doc, pid)
        entry = pl.place.get(pid)
        if entry is None or pid in pl.fractions:
            shell.say("Wait for the preview: the inset starts from what the panel shows.", True)
            return
        box, _ = pl._inset_box(pid, entry, (1 / 3, 1 / 3), (2 / 3, 2 / 3))
        made, centre = [], pl._storm_centre(p)
        shell.edit(lambda d: made.append(de.add_inset(d, pid, box, None, centre)))
        shell._show(f"inset:{pid}:{made[0]['id']}")
        return made[0]

    # ------------------------------------------------------------ on its node
    def objs(self, doc, node):
        p, inset = nodes.panel_of(doc, node), nodes.inset_of(doc, node)
        pid, iid = p["id"], int(inset["id"])
        scope = InsetScope(p["kind"], pid, iid)
        objs = [_note("It shows the panel's run and time. Dragging in the preview sets what it "
                      "shows and where it sits: see the list above it."),
                _Card(self, node, PLACE, PLACE_KEYS, de.INSET_PLACE,
                      self._place_rows(p, inset, node), opened=True).card]
        if p["kind"] == "plan":
            self.ins.folds.setdefault(scope.fold_key(AREA), True)
            looks = Sections(self.ins, scope, ["plan"], {AREA: self._area_extra(scope, inset)})
            objs.append(looks.card(AREA, only=AREA_OF_A_PANEL))
        else:
            objs.append(_Card(self, node, AREA, ("view",), dict(view=None),
                              self._view_rows(inset, node), opened=True).card)
        objs.append(_Card(self, node, LOOK, LOOK_KEYS, de.INSET_LOOK,
                          self._look_rows(inset, node)).card)
        objs += self._layers(doc, p, inset)
        objs.append(_button("Remove this inset", lambda: self.remove(pid, iid)))
        return nodes.inset_word(doc, node).capitalize(), objs

    def remove(self, pid, iid):
        self.shell.edit(lambda d: de.remove_inset(d, pid, iid), node=f"panel:{pid}")

    def _write(self, node, **keys):
        """Keys of the inset of node (None: it no longer has them)."""
        def apply(d):
            inset = nodes.inset_of(d, node)
            for k, v in keys.items():
                if v is None:
                    inset.pop(k, None)
                else:
                    inset[k] = v
        self.shell.edit(apply)

    def _place_rows(self, p, inset, node):
        loc = pn.widgets.Select(name="Where", options=LOCS,
                                value=inset.get("loc") or de.INSET_PLACE["loc"])
        size = _f("Width (of the panel)", float(inset.get("size") or de.INSET_PLACE["size"]),
                  step=0.05, start=0.05, end=1.0)
        x = _f("x (left edge)", float(inset.get("x", 0.03)), step=0.01)
        y = _f("y (bottom edge)", float(inset.get("y", 0.03)), step=0.01)
        tall = _f("Height (blank: as it shows)" if p["kind"] == "plan" else "Height (blank: as wide)",
                  None if inset.get("h") is None else float(inset["h"]), step=0.05)

        def show(*ev):
            x.visible = y.visible = loc.value == "custom"

        def on_loc(ev):
            show()
            if ev.new == "custom":  # (from the corner it was in, were it there)
                self._write(node, loc=ev.new, x=x.value, y=y.value)
            else:
                self._write(node, loc=ev.new)

        loc.param.watch(on_loc, "value")
        size.param.watch(lambda ev: self._write(node, size=ev.new), "value")
        x.param.watch(lambda ev: self._write(node, x=ev.new), "value")
        y.param.watch(lambda ev: self._write(node, y=ev.new), "value")
        tall.param.watch(lambda ev: self._write(node, h=ev.new), "value")
        show()
        return [_grid(loc, size, x, y, tall, n=2)]

    def _area_extra(self, scope, inset):
        """A plan view's inset: the Area section's rows, and how far from the storm it is while it
        follows the storm."""
        boxes = area_extra(self.shell, scope)

        def extra(by_key):
            off = ((inset.get("opts") or {}).get("domain") or {}).get("off") or [0.0, 0.0]
            east = _f("Centre east of the storm (km)", float(off[0]), step=0.5)
            north = _f("Centre north of the storm (km)", float(off[1]), step=0.5)
            mode = by_key.get("domain.mode")

            def on_off(ev):
                def apply(d):
                    held = scope._targets(d, "domain")[0]
                    held["domain"] = dict(held.get("domain") or {},
                                          off=[float(east.value or 0), float(north.value or 0)])
                self.shell.edit(apply)

            def show(*ev):
                east.visible = north.visible = mode is not None and mode.value == "storm"

            east.param.watch(on_off, "value")
            north.param.watch(on_off, "value")
            if mode is not None:
                mode.param.watch(show, "value")
            show()
            return [*boxes(by_key), _grid(east, north, n=2)]
        return extra

    def _view_rows(self, inset, node):
        """A cross-section's inset: the part of the panel's axes it shows."""
        view = list(inset.get("view") or [None] * 4)
        ws = [_f(name, view[n], step=0.5) for n, name in enumerate(
            ("From (km)", "To (km)", "Height from (km)", "Height to (km)"))]
        said = pn.pane.HTML(margin=(0, 4), sizing_mode="stretch_width")

        def on_view(ev):
            v = [w.value for w in ws]
            ok = None not in v and v[1] > v[0] and v[3] > v[2]
            said.object = "" if ok else (
                '<div class="cv-status" style="color:#f87171">Each “to” needs to be above its '
                "“from”.</div>")
            if ok:
                self._write(node, view=[float(a) for a in v])

        for w in ws:
            w.param.watch(on_view, "value")
        return [_grid(*ws, n=2), said]

    def _look_rows(self, inset, node):
        look = de.INSET_LOOK

        def check(name, key):
            w = pn.widgets.Checkbox(name=name, value=bool(inset.get(key, look[key])))
            w.param.watch(lambda ev: self._write(node, **{key: bool(ev.new)}), "value")
            return w

        color = pn.widgets.ColorPicker(name="Colour", value=_hex(inset.get("color") or look["color"]))
        lw = _f("Line width", float(inset.get("lw", look["lw"])), step=0.25, start=0.25)
        ls = pn.widgets.Select(name="Line style", options=STYLES, value=inset.get("ls", look["ls"]))
        color.param.watch(lambda ev: self._write(node, color=ev.new), "value")
        lw.param.watch(lambda ev: self._write(node, lw=ev.new), "value")
        ls.param.watch(lambda ev: self._write(node, ls=ev.new), "value")
        return [check("Box in the panel", "mark"), check("Lines to the inset", "connect"),
                check("Tick labels", "ticks"), _grid(color, lw, ls, n=2)]

    # ------------------------------------------------------------ its layers
    def _layers(self, doc, p, inset):
        pid, iid, kind = p["id"], int(inset["id"]), p["kind"]
        own = inset.get("layers") is not None
        node = f"inset:{pid}:{iid}"
        same = pn.widgets.Checkbox(name="The panel's layers", value=not own, margin=(4, 8))
        same.param.watch(lambda ev: self.shell.edit(
            lambda d: de.own_inset_layers(d, pid, iid, not ev.new), node=node), "value")
        objs = [pn.pane.HTML("<b>Layers</b>", margin=(8, 4, 0, 4)), same]
        if not own:
            objs.append(_note("As the panel has them, whatever changes there. Untick for layers of "
                              "its own, starting from these."))
            return objs
        pane = self.ins.panes[kind]
        objs.append(_note("Its own list: what is added, removed or changed here stays here. A "
                          "shared layer's other settings still follow All "
                          f"{html.escape(pane._words())}."))
        objs.append(pane._add_menu(lambda t: self._add_layer(pid, iid, t), "Add a layer to this inset"))
        n = len(de.places(doc, inset))
        for j in range(n):
            objs.append(self._row(doc, pid, iid, j, n, kind).panel)
        if not n:
            objs.append(_note("No layers here: add one above."))
        return objs

    def _row(self, doc, pid, iid, j, n, kind):
        shell = self.shell

        def step(fn, *args):
            def apply(d):
                fn(d, de.inset_by_id(de.panel_by_id(d, pid), iid), j, *args)
            shell.edit(apply, node=shell.node)

        moves = {}
        if j > 0:
            moves["up"] = lambda: step(de.move_in_panel, -1)
        if j < n - 1:
            moves["down"] = lambda: step(de.move_in_panel, 1)
        moves["copy"] = lambda: step(de.copy_in_panel)
        moves["remove"] = lambda: step(de.remove_in_panel)
        return LayerRow(self.ins, InInset(doc, pid, iid, j), moves=moves, extras=own_time_widgets,
                        opened=n == 1, kind=kind)

    def _add_layer(self, pid, iid, kind):
        lay = new_layer(self.shell, kind)
        if lay is None:
            self.shell.say("No parcel sets: make one in the viewer's Parcels tab.", True)
            return

        def apply(d):
            p = de.panel_by_id(d, pid)
            inset = de.inset_by_id(p, iid)
            de.add_own(inset, lay)
            self.ins.folds[f"i:{iid}:own{len(de.places(d, inset)) - 1}"] = True
            de.apply_heights(d, [p])
        self.shell.edit(apply, node=self.shell.node)
