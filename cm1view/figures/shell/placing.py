"""Placing by clicking the preview: while a mode is picked, a click or a drag in a panel of the
preview makes or moves an annotation, sets a section's A-B or the plan views' area, as it does in
the old editor (click.py holds what both use).  Positions are the panel's axis units; in a 3D scene
or a table, which have none to click on, fractions of the panel."""

import panel as pn

from .. import draw as figdraw
from ..click import (DRAG, PLACE, TWO, axis_digits, dragged_to, grab_annotation, locate, moved_annotation,
                     placed_item, to_data)
from . import docedit as de, nodes

FRACTION_KINDS = ("scene", "table")  # (annotations by fractions of the panel)
HINTS = dict(
    section="Click A, then B, in a plan view (or drag from A to B): a section's line. A Section "
            "line layer shows it.",
    move="Drag an annotation in the preview: from its text, marker, centre or middle to move it "
         "all, from an end to move that end.",
    area="Drag a box in a plan view: all plan views show that area.")


def fraction_entry(box):
    """A place_map entry for a panel placed by fractions of it: its axis units are those."""
    return (*box, (0.0, 1.0), (0.0, 1.0), None)


class Placing:
    def __init__(self, shell):
        self.shell = shell
        self.place, self.origin, self.fractions = {}, {}, set()
        self.pending = None  # (panel, x, y) of a two-point item's first click
        self.mode = pn.widgets.Select(options=PLACE, value="", width=230, height=32, margin=(4, 4))
        self.hint = pn.pane.HTML(margin=(0, 8), sizing_mode="stretch_width", visible=False,
                                 styles={"flex": "0 0 auto"})
        self.mode.param.watch(self._on_mode, "value")

    @property
    def on(self):
        return bool(self.mode.value)

    def _on_mode(self, ev):
        self.pending = None
        mode = ev.new
        self.hint.visible = bool(mode)
        self.shell.image.band = mode in ("box", "area")
        text = HINTS.get(mode) or (
            "Click in a panel of the preview" + (" twice, or drag from the first point to the "
                                                 "second" if mode in TWO else "")
            + "; the new item is under the panel's Annotations, to fine-tune. In a skew-T, "
              "positions are temperature (°C) and pressure (hPa).")
        self.hint.object = f'<div class="cv-hint">{text}</div>'
        self.shell._show_image()

    def cursor(self):
        return "move" if self.mode.value == "move" else "crosshair" if self.on else "pointer"

    def took(self, doc, place, boxes, data):
        """The preview drawn from doc is showing: where its panels are (place_map) and, for
        those placed by fractions, boxes; the plan views' origins (storm-centred axes)."""
        self.fractions = {p["id"] for p in doc["panels"]
                          if p["kind"] in FRACTION_KINDS and p["id"] in boxes}
        self.place = {**place, **{i: fraction_entry(boxes[i]) for i in self.fractions}}
        self.origin = {i: tuple(d["origin"]) for i, d in data.items() if "origin" in d}

    # ------------------------------------------------------------ a click or a drag
    def _locate(self, fx, fy):
        got = locate(self.place, fx, fy)
        if got is not None and not any(p["id"] == got[0] for p in self.shell.doc["panels"]):
            got = None  # (gone since this preview was drawn)
        if got is None:
            self.shell.say("Click inside a panel: skew-T soundings and panels with plain axes "
                           "take axis units, a 3D scene or a table fractions of the panel.", True)
        return got

    def click(self, fx, fy):
        if self.mode.value in DRAG:
            self.shell.say("Drag (press, move, release) in the preview to "
                           + ("move an annotation." if self.mode.value == "move" else
                              "draw the plan-view area."), True)
            return
        got = self._locate(fx, fy)
        if got is not None:
            pid, b, u, w = got
            self._placed(pid, *self._at(pid, b, u, w))

    def _at(self, pid, b, u, w):
        """A panel's axis units at fractions of it, rounded for typing, but no more than its axes
        allow (a joint distribution's may span 0.1)."""
        x, y = to_data(b, u, w)
        return round(x, axis_digits(b[4])), round(y, axis_digits(b[5]))

    def drag(self, f0, f1):
        mode = self.mode.value
        got = self._locate(*f0)
        if got is None:
            return
        pid, b, u0, w0 = got
        u1, w1 = dragged_to(b, u0, w0, f0, f1)
        if mode == "move":
            self._move(pid, b, (u0, w0), (u1, w1))
        elif mode == "area":
            self._area(pid, to_data(b, u0, w0), to_data(b, u1, w1))
        else:
            self.pending = None  # (a drag: both points of a two-point item)
            self._placed(pid, *self._at(pid, b, u0, w0))
            if mode in TWO:
                self._placed(pid, *self._at(pid, b, u1, w1))

    # ------------------------------------------------------------ what it does
    def _kind_is(self, pid, kind):
        return de.panel_by_id(self.shell.doc, pid)["kind"] == kind

    def _placed(self, pid, x, y):
        mode = self.mode.value
        shell = self.shell
        if mode in TWO and (self.pending is None or self.pending[0] != pid):
            self.pending = (pid, x, y)
            shell.say(f"First point ({x:g}, {y:g}): now click the second.")
            return
        first = None
        if mode in TWO:
            (_, *first), self.pending = self.pending, None
        if mode == "section":
            self._section(pid, first, (x, y))
            return
        a = placed_item(mode, pid, first, x, y)
        if pid in self.fractions:
            a["coords"] = "axes"
        shell.inspector.annots.append(a, node=f"panel:{pid}")
        letter = nodes.letters(shell.doc)[pid]
        shell.say(f"Added {mode} in panel {letter}: see its Annotations.")

    def _section(self, pid, p1, p2):
        """A-B from two clicks in a plan view (in its axis units: grid or storm km)."""
        shell = self.shell
        if not self._kind_is(pid, "plan"):
            shell.say("Click the section's ends in a plan view.", True)
            return
        d = self.origin.get(pid, (0.0, 0.0))
        a = [round(p1[0] + d[0], 2), round(p1[1] + d[1], 2)]
        b = [round(p2[0] + d[0], 2), round(p2[1] + d[1], 2)]
        made = []
        shell.edit(lambda doc: made.append(de.place_section(doc, pid, a, b)), node=shell.node)
        names = nodes.letters(shell.doc)
        showing = [names[p["id"]] for p in de.section_panels(shell.doc, made[0])]
        line = any(lay.get("type") == "line" and lay.get("on", True) is not False
                   for _, lay in figdraw.panel_layers(shell.doc, de.panel_by_id(shell.doc, pid)))
        shell.say(f"Section A ({a[0]:g}, {a[1]:g}) → B ({b[0]:g}, {b[1]:g}) km."
                  + ("" if line else " Add a Section line layer to draw it here.")
                  + (f" Cross-section{'s' if len(showing) > 1 else ''} {', '.join(showing)} "
                     "show this section too." if showing else ""))

    def _area(self, pid, p1, p2):
        """All plan views' area from a box dragged in one (grid km)."""
        shell = self.shell
        if not self._kind_is(pid, "plan"):
            shell.say("Drag the area in a plan view.", True)
            return
        d = self.origin.get(pid, (0.0, 0.0))
        xs = sorted((p1[0] + d[0], p2[0] + d[0]))
        ys = sorted((p1[1] + d[1], p2[1] + d[1]))
        shell.edit(lambda doc: de.set_area(doc, [*xs, *ys]), node=shell.node)
        shell.say("Area of all plan views: x {:.2f} – {:.2f}, y {:.2f} – {:.2f} km.".format(
            *xs, *ys))

    def _move(self, pid, b, start, end):
        shell = self.shell
        anns = shell.doc.get("annotations") or []
        got = grab_annotation(anns, pid, b, start)
        if got is None:
            shell.say("No annotation there: start the drag on one (its text, marker, centre, "
                      "middle or an end).", True)
            return
        n, grip = got
        new = moved_annotation(anns[n], b, start, end, grip,
                               (axis_digits(b[4]), axis_digits(b[5])))
        shell.edit(lambda d: d["annotations"][n].update(new), node=shell.node)
        shell.say(f"Moved the {anns[n]['kind']}" + (" (one end)" if grip in ("1", "2") else "") + ".")
