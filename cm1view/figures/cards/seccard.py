"""The card of one cross-section of a figure (spec["sections"])."""

import panel as pn

from ..spec.sections import MOTION, ORIENTS, POSITIONS, describe, section_defaults
from .base import _f, _grid, _hint, _fold, _BTN


class SectionCard:
    """One section: label, orientation (x–z, y–z, angled, along or across the storm's
    motion, A–B), through the storm or fixed, its position and length, and the width it is averaged across."""

    def __init__(self, ed, sec):
        self.ed, self.sec = ed, section_defaults(**sec)
        s, self.w = self.sec, {}
        w = self.w
        self.rm = pn.widgets.Button(name="✕", description="Remove the section", **_BTN)
        self.ab = pn.widgets.Button(name="Use map A–B", height=32, button_type="light",
                                    button_style="outline")
        w["label"] = pn.widgets.TextInput(name="Label (blank: automatic)", value=s["label"],
                                          width=160)
        w["orient"] = pn.widgets.Select(name="Orientation", options=ORIENTS,
                                        value=s["orient"], width=150)
        w["pos"] = pn.widgets.Select(name="Position", options=POSITIONS, value=s["pos"],
                                     width=150)
        w["half"] = _f("Half-length (km)", float(s["half"]), step=1, start=0.5)
        w["off"] = _f("Offset (km)", float(s["off"]), step=0.5)
        w["y"] = _f("At y (km; blank: centre)", s["y"], step=0.5)
        w["x0"] = _f("From x (km; blank: edge)", s["x0"], step=0.5)
        w["x1"] = _f("To x (km; blank: edge)", s["x1"], step=0.5)
        w["x"] = _f("At x (km; blank: centre)", s["x"], step=0.5)
        w["y0"] = _f("From y (km; blank: edge)", s["y0"], step=0.5)
        w["y1"] = _f("To y (km; blank: edge)", s["y1"], step=0.5)
        w["angle"] = _f("Direction (° clockwise from north)", float(s["angle"]), step=15)
        w["offx"] = _f("Offset x (km)", float(s["offset"][0]), step=0.5)
        w["offy"] = _f("Offset y (km)", float(s["offset"][1]), step=0.5)
        w["cx"] = _f("Centre x (km; blank: centre)", s["cx"], step=0.5)
        w["cy"] = _f("Centre y (km; blank: centre)", s["cy"], step=0.5)
        w["ahead"] = _f("Centre ahead of the storm (km)", float(s["ahead"]), step=0.5)
        w["right"] = _f("Centre right of the storm (km)", float(s["right"]), step=0.5)
        w["mwin"] = _f("Motion averaged over (min; 0: at the time)", float(s["mwin"]),
                       step=5, start=0.0)
        w["avg"] = _f("Average across (km)", float(s["avg"] or 0.0), step=0.5, start=0.0)
        for x in w.values():
            x.param.watch(lambda e: self._changed(), "value")
        self.hint = pn.pane.HTML(margin=(2, 4))
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [_grid(w["label"], w["orient"], w["pos"], w["half"], w["off"], w["y"], w["x0"],
                   w["x1"], w["x"], w["y0"], w["y1"], w["angle"], w["offx"], w["offy"],
                   w["cx"], w["cy"], w["ahead"], w["right"], w["mwin"], w["avg"],
                   self.ab),
             self.hint])
        self.tracked(True)

    def tracked(self, ok):
        """Through the storm needs a run with a track (ok: one has; a section through
        it already stays so, its panels saying they need a track)."""
        self.w["pos"].disabled_options = [] if ok or self.w["pos"].value == "storm" \
            else ["storm"]
        self._show()

    def _show(self):
        w, s = self.w, self.collect()
        o, fixed = s["orient"], s["pos"] == "fixed"
        mot = o in MOTION
        w["pos"].visible = o != "ab" and not mot
        w["half"].visible = o == "angle" or mot or (o in ("x", "y") and not fixed)
        for k in ("ahead", "right", "mwin"):
            w[k].visible = mot
        w["off"].visible = o in ("x", "y") and not fixed
        w["off"].name = f"Offset in {'y' if o == 'x' else 'x'} (km)"
        for k in ("y", "x0", "x1"):
            w[k].visible = o == "x" and fixed
        for k in ("x", "y0", "y1"):
            w[k].visible = o == "y" and fixed
        w["angle"].visible = o == "angle"
        w["offx"].visible = w["offy"].visible = o == "angle" and not fixed
        w["cx"].visible = w["cy"].visible = o == "angle" and fixed
        self.ab.visible = o == "ab"
        k = self.index()
        self.title.object = (f"<b>Section {k + 1}</b>"
                             + (f" · {s['label']}" if s["label"] else "")
                             + f" · {describe(s)}")
        self.hint.object = (
            '<div class="cv-hint">Draw a section on the map (Section tool), then use its '
            'A–B, or click its ends in a plan-view panel (Place: section).</div>'
            if o == "ab" else
            '<div class="cv-hint">Direction: 0° runs south → north, 90° west → east.</div>'
            if o == "angle" else
            '<div class="cv-hint">Turns with the storm\'s tracked motion at each time '
            '(behind → ahead, or left → right of it); needs a track for each run.</div>'
            if mot else "")

    def index(self):
        cards = getattr(self.ed, "sec_cards", [])
        return cards.index(self) if self in cards else len(cards)

    def _changed(self):
        self._show()
        if not self.ed._hold:
            self.ed.request()

    def set_ab(self, a, b):
        """Make this an A–B section from a to b (grid km)."""
        self.sec = dict(self.sec, a=list(a), b=list(b))
        hold, self.ed._hold = self.ed._hold, True
        try:
            self.w["orient"].value = "ab"
        finally:
            self.ed._hold = hold
        self._show()

    def collect(self):
        w = self.w
        return section_defaults(
            label=w["label"].value.strip(), orient=w["orient"].value, pos=w["pos"].value,
            half=float(w["half"].value or 10.0), off=float(w["off"].value or 0.0),
            **{k: None if w[k].value is None else float(w[k].value)
               for k in ("y", "x0", "x1", "x", "y0", "y1", "cx", "cy")},
            angle=float(w["angle"].value or 0.0),
            offset=[float(w["offx"].value or 0.0), float(w["offy"].value or 0.0)],
            ahead=float(w["ahead"].value or 0.0), right=float(w["right"].value or 0.0),
            mwin=float(w["mwin"].value or 0.0),
            a=self.sec.get("a"), b=self.sec.get("b"), avg=float(w["avg"].value or 0.0))
