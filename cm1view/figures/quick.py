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
        self.qs_saved = pn.widgets.Select(name="Or open a saved figure")
        self.qs_open = pn.widgets.Button(name="Open", button_type="primary",
                                         button_style="outline", disabled=True)
        self.qs_load_note = _hint("")
        self.qs_load_note.visible = False
        self.quick = pn.Modal(
            pn.pane.HTML('<div class="cv-maptitle" style="font-size:16px"><b>New figure'
                         '</b></div>', margin=(0, 4)),
            _grid(self.qs_kind, self.qs_vary, self.qs_field),
            _grid(self.qs_rows, self.qs_cols, self.qs_size), self.qs_note,
            _hint("Everything else (times, layers, style, labels) is in the editor's tabs; "
                  "the new-figure button above the preview shows this again."),
            pn.Row(self.qs_go, self.qs_skip),
            pn.layout.Divider(margin=(6, 4)),
            _grid((self.qs_saved, 2), self.qs_open), self.qs_load_note,
            _hint("Figures saved with <b>+ script & data</b> in the Figures folder "
                  "(⚙ Settings); the Export tab opens any other."), width=640, margin=10,
            stylesheets=[DIALOG_DARK])
        self.qs_kind.param.watch(lambda e: self._quick_show(), "value")
        self.qs_vary.param.watch(lambda e: self._quick_show(), "value")
        self.qs_go.on_click(lambda e: self._quick_make())
        self.qs_skip.on_click(lambda e: self.quick.hide())
        self.qs_saved.param.watch(
            lambda e: setattr(self.qs_open, "disabled", not e.new), "value")
        self.qs_open.on_click(lambda e: self._quick_open())

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
        self._refresh_saved()
        self.qs_load_note.visible = False
        self.quick.show()

    def _quick_show(self):
        kind, vary = self.qs_kind.value, self.qs_vary.value
        maps = kind in MAPS
        for w in (self.qs_vary, self.qs_field):
            w.visible = maps
        self.qs_rows.visible = self.qs_cols.visible = kind != "th"  # (th: series × runs)
        self.qs_vary.options = VARY if kind != "xsec" else \
            {k: v for k, v in VARY.items() if v != "height"}
        note = {
            "th": "Time–height panels: one per run and series (Panels → Grid and size → "
                  "Runs are: rows or columns).  It starts with no series, so nothing is "
                  "computed until you add one in Layers → Series.",
            "line": "Time series: it starts with no series, so nothing is computed until "
                    "you add one in Layers → Series (each with its panel number).",
            "sounding": "The Sounding tab's soundings go one per panel (more soundings "
                        "than panels: they wrap and share panels); panels left over start "
                        "as a copy of the last, to change in Layers → Soundings.",
            "dist": "The Distribution tool's distributions go one per panel (more than "
                    "panels: they wrap and share panels); panels left over start as a "
                    "copy of the last, to change in Layers → Distributions.",
            "profile": "The Series tool's layer series go one per panel at the shown time "
                       "(more than panels: they wrap and share panels); panels left over "
                       "start as a copy of the last, to change in Layers → Profiles.",
            "joint": "Every panel starts with vertical vorticity against w at 1 km at the "
                     "shown time, to change in Layers → Joint distributions.",
            "azim": "Every panel starts with w around the tracked storm (else the middle "
                    "of the map's view) at the shown time, the whole ring out to 20 km, to "
                    "change in Layers → Azimuthal means."}.get(kind) or (maps and {
            "field": "Every panel starts with this fill: pick each panel's field in "
                     "Panels → Time and fields.",
            "height": "Pick each panel's height in Panels → Time and heights.",
            "custom": "Pick each panel's run and time in Panels → Run and time of each "
                      "panel, or make a grid of runs × times with Panels → Fill a grid."}.get(vary)) or ""
        self.qs_note.object = f'<div class="cv-hint">{note}</div>'
        self.qs_note.visible = bool(note)

    def _quick_open(self):
        """Open the saved figure picked in the quick start (it closes the dialog); if
        it cannot be opened, say why in the dialog."""
        if not self._load_spec(self.qs_saved.value):
            self.qs_load_note.object = self.msg.object
            self.qs_load_note.visible = True

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
            if kind != "th":
                self.rows.value = int(self.qs_rows.value)
                self.cols.value = int(self.qs_cols.value)
            if kind in ("sounding", "dist", "profile", "joint", "azim"):
                self._quick_spread(kind)
            if self.qs_size.value:
                self.size_preset.value = self.qs_size.value
        finally:
            self.auto.value = live
        self.request(delay=False)

    def _quick_spread(self, kind):
        """Sounding / distribution / profile / joint distribution / azimuthal mean cards
        one per panel of the grid: more cards than panels wrap (sharing panels), panels left over get a copy
        of the last card."""
        n = int(self.rows.value or 1) * int(self.cols.value or 1)
        cards = {"sounding": self.snd_cards, "dist": self.dist_cards,
                 "profile": self.prof_cards, "joint": self.joint_cards,
                 "azim": self.azim_cards}[kind]
        ents = [c.collect() for c in cards]
        if not ents:
            return
        ents = [dict(e, panel=i % n) for i, e in enumerate(ents)] + \
            [dict(ents[-1], panel=i) for i in range(len(ents), n)]
        if kind == "sounding":
            self.snd_cards = [self._snd_card(e) for e in ents]
            self._show_soundings()
        elif kind == "dist":
            self.dist_cards = [self._dist_card(e) for e in ents]
            self._show_dists()
        elif kind == "profile":
            self.prof_cards = [self._prof_card(e) for e in ents]
            self._show_profiles()
        elif kind == "joint":
            self.joint_cards = [self._joint_card(e) for e in ents]
            self._show_joints()
        else:
            self.azim_cards = [self._azim_card(e) for e in ents]
            self._show_azims()
        self._build_titles()
