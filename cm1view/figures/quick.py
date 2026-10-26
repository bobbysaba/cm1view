"""Figure editor: the quick start.  Opening the Figure workspace the first time (with no
figure made from the viewer yet), and the new-figure button, ask for the few settings a
figure starts from: what the panels show, how they differ, the grid, the main field
and the width.  Everything else is the editor's tabs.

A mixin of the FigureEditor (figures/editor.py)."""

import panel as pn

from . import spec as fg
from ..theme import DIALOG_DARK
from .cards import SIZE_PRESETS, VARY, _grid, _hint

MAPS = ("plan", "xsec")  # (the kinds with a fill field, a grid and panels that differ)


class FigureQuick:
    _started = False  # a figure has been made (here, from the viewer, or loaded)

    def _build_quick(self):
        self.qs_kind = pn.widgets.Select(name="Panels show", options=dict(self.kind.options),
                                         value="plan")
        self.qs_vary = pn.widgets.Select(name="Panels differ in", options=VARY, value="time")
        self.qs_rows = pn.widgets.IntInput(name="Rows", start=1, end=8, value=2)
        self.qs_cols = pn.widgets.IntInput(name="Columns", start=1, end=8, value=3)
        self.qs_field = pn.widgets.Select(name="Colour fill")
        self.qs_size = pn.widgets.Select(name="Width", value="", options={
            ("8 in wide" if v == "" else k): v for k, v in SIZE_PRESETS.items()})
        self.qs_note = _hint("")
        self.qs_go = pn.widgets.Button(name="Make the figure", button_type="primary",
                                       width=160)
        self.qs_skip = pn.widgets.Button(
            name="Keep the example", button_type="light", button_style="outline", width=150,
            description="Close: the figure stays as it is")
        self.quick = pn.Modal(
            pn.pane.HTML('<div class="cv-maptitle" style="font-size:16px"><b>New figure'
                         '</b></div>', margin=(0, 4)),
            _grid(self.qs_kind, self.qs_vary, self.qs_field),
            _grid(self.qs_rows, self.qs_cols, self.qs_size), self.qs_note,
            _hint("Everything else (times, layers, style, labels) is in the editor's tabs; "
                  "the new-figure button above the preview shows this again."),
            pn.Row(self.qs_go, self.qs_skip), width=640, margin=10,
            stylesheets=[DIALOG_DARK])
        self.qs_kind.param.watch(lambda e: self._quick_show(), "value")
        self.qs_vary.param.watch(lambda e: self._quick_show(), "value")
        self.qs_go.on_click(lambda e: self._quick_make())
        self.qs_skip.on_click(lambda e: self.quick.hide())

    def opened(self):
        """The Figure workspace is shown: the quick start, the first time."""
        if not self._started:
            self._started = True
            self.open_quick()

    def open_quick(self):
        """Show the quick start, set as the figure in the editor."""
        g = self.fields.groups()
        fill = (self._pf_base or {}).get("field") or next(
            (c.collect()["field"] for c in self.cards if c.type == "fill"), None)
        self.qs_field.groups = g
        names = [v for grp in g.values() for v in grp.values()]
        self.qs_field.value = fill if fill in names else (names[0] if names else None)
        self.qs_kind.value = self.kind.value
        self._quick_show()  # (the panels' choices of this kind first)
        vary = self.vary.value
        self.qs_vary.value = vary if vary in self.qs_vary.options.values() else "time"
        self.qs_rows.value, self.qs_cols.value = int(self.rows.value), int(self.cols.value)
        self.quick.show()

    def _quick_show(self):
        kind, vary = self.qs_kind.value, self.qs_vary.value
        maps = kind in MAPS
        for w in (self.qs_vary, self.qs_field, self.qs_cols):
            w.visible = maps
        self.qs_rows.visible = maps
        self.qs_vary.options = VARY if kind != "xsec" else \
            {k: v for k, v in VARY.items() if v != "height"}
        note = {
            "th": "Time–height panels: one per run and series (Panels → Runs are rows "
                  "or columns).  It starts with no series, so nothing is computed until "
                  "you add one in Layers → Series.",
            "line": "Time series: it starts with no series, so nothing is computed until "
                    "you add one in Layers → Series (each with its panel number).",
            "sounding": "One panel per sounding of the viewer's Sounding tab (Layers → "
                        "Soundings adds more).",
            "dist": "One panel per distribution of the Distribution tool (Layers → "
                    "Distributions adds more)."}.get(kind) or (maps and {
            "field": "Every panel starts with this fill: pick each panel's field in "
                     "Panels → Time and fields.",
            "height": "Pick each panel's height in Panels → Time and heights.",
            "custom": "Pick each panel's run and time in Panels → Run and time of each "
                      "panel, or make a grid of runs × times with Panels → Fill a grid."}.get(vary)) or ""
        self.qs_note.object = f'<div class="cv-hint">{note}</div>'
        self.qs_note.visible = bool(note)

    def _quick_make(self):
        """A new figure (Undo takes it back) with the quick start's settings."""
        self.quick.hide()
        kind, vary = self.qs_kind.value, self.qs_vary.value
        s = self._default()
        f = self.qs_field.value
        if kind in MAPS and f:
            fill = next((lay for lay in s["layers"] if lay["type"] == "fill"), None)
            if fill is not None and fill.get("field") != f:
                s["layers"][s["layers"].index(fill)] = fg.layer_defaults(
                    "fill", self.fields, f, 1.0)
        live, self.auto.value = self.auto.value, False  # (one render: one undo step)
        try:
            self.set_parts(s)
            self.kind.value = kind  # (its own labels, colorbar and series / sounding cards)
            if kind in MAPS:
                self.vary.value = vary
                self.rows.value = int(self.qs_rows.value)
                self.cols.value = int(self.qs_cols.value)
            if self.qs_size.value:
                self.size_preset.value = self.qs_size.value
        finally:
            self.auto.value = live
        self.request(delay=False)

