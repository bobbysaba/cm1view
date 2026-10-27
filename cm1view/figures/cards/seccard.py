"""The card of one cross-section of a figure (spec["sections"]): in a section figure
one panel's (Layers tab: its run, time, section and panel number), in a plan view one
of the sections its Section line layer draws (Panels tab → Area)."""

import panel as pn

from .. import draw as figdraw
from ..spec.sections import MOTION, ORIENTS, POSITIONS, describe, section_defaults
from .base import _f, _grid, _hint, _fold, _load_widgets, _BTN


class SectionCard:
    """One section: label, orientation (x–z, y–z, angled, along or across the storm's
    motion, A–B), through the storm or fixed, its position and length, and the width it
    is averaged across; in a section figure also its run, time and panel."""

    def __init__(self, ed, sec):
        self.ed, self.sec = ed, section_defaults(**sec)
        self._loading = False  # (load: the widgets take another section's settings)
        s, self.w = self.sec, {}
        w = self.w
        self.rm = pn.widgets.Button(name="✕", description="Remove the section", **_BTN)
        self.ab = pn.widgets.Button(name="Use map A–B", height=32, button_type="light",
                                    button_style="outline")
        self.dup = pn.widgets.Button(name="Duplicate", height=32, button_type="light",
                                     button_style="outline",
                                     description="A copy of this card in a new panel")
        self.per_run = pn.widgets.Button(
            name="One per run", height=32, button_type="light", button_style="outline",
            description="A copy of this card for each other run of the figure, down this "
                        "card's column (a row per run)")
        names = ed._run_names()
        k = int(s.get("run") or 0)
        k = k if k in names.values() else 0
        w["run"] = pn.widgets.Select(name="Run", value=k, width=170, **ed._run_choices(names))
        opts = ed._time_opts(k)
        w["time"] = pn.widgets.Select(name="Time", options=opts, width=210, value=ed._nearest(
            opts, s.get("time_s") if s.get("time_s") is not None else ed.time1.value))
        w["panel"] = pn.widgets.IntInput(name="Panel", start=1, end=64, width=70,
                                         value=int(s.get("panel") or 0) + 1)
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
        w["run"].param.watch(self._on_run, "value")
        for key, x in w.items():
            if key != "run":
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: None if self._loading else ed._fit_grid(), "value")
        self.hint = pn.pane.HTML(margin=(2, 4))
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self.where = _grid(w["run"], (w["time"], 2), w["panel"], self.dup, self.per_run)
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [self.where,
             _grid(w["label"], w["orient"], w["pos"], w["half"], w["off"], w["y"], w["x0"],
                   w["x1"], w["x"], w["y0"], w["y1"], w["angle"], w["offx"], w["offy"],
                   w["cx"], w["cy"], w["ahead"], w["right"], w["mwin"], w["avg"],
                   self.ab),
             self.hint])
        self.tracked(True)

    def load(self, sec):
        """Show section sec in these widgets (a new figure keeps the cards the browser
        already has)."""
        new = SectionCard(self.ed, sec)  # (never shown: its settings)
        self._loading = True
        try:
            _load_widgets(self.w, new.w)
        finally:
            self._loading = False
        self.sec = new.sec
        self._show()

    def cards(self):
        """Whether this is a section figure's card (with its run, time and panel)."""
        return self.ed.kind.value == "xsec"

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
        self.where.visible = self.cards()
        self.w["label"].name = "Label = panel title (blank: none)" if self.cards() \
            else "Label (blank: automatic)"
        if self.cards():
            run = next((n for n, v in self.ed._run_names().items() if v == s["run"]), "")
            when = next((n for n, v in w["time"].options.items() if v == s["time_s"]), "")
            head = (f"<b>Panel {figdraw.panel_letter(s['panel'], '{a}')}</b> · "
                    f"{run.split('. ', 1)[-1]} · {when.split('(')[-1].rstrip(')')}")
        else:
            head = f"<b>Section {self.index() + 1}</b>"
        self.title.object = (head + (f" · {s['label']}" if s["label"] else "")
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
        if self._loading:
            return
        self._show()
        if not self.ed._hold:
            self.ed.request()

    def _on_run(self, ev):
        """Another run: its time nearest the card's (a run not in the figure: added)."""
        if self.ed._hold or self._loading:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
            return
        self.set_run(ev.new)
        self._changed()

    def set_run(self, k, time_s=None):
        """Run k, at its time nearest time_s (None: the card's time)."""
        o = self.ed._time_opts(k)
        cur = self.w["time"].value if time_s is None else time_s
        hold, self.ed._hold = self.ed._hold, True
        try:
            self.w["run"].value = k
            self.w["time"].options = o
            self.w["time"].value = self.ed._nearest(o, cur)
        finally:
            self.ed._hold = hold
        self._show()

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
            a=self.sec.get("a"), b=self.sec.get("b"), avg=float(w["avg"].value or 0.0),
            run=int(w["run"].value or 0) if isinstance(w["run"].value, int) else 0,
            time_s=None if w["time"].value is None else float(w["time"].value),
            panel=max(0, int(w["panel"].value or 1) - 1))
