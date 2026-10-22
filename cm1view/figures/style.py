"""Figure editor: style presets and matplotlib styles, copying one layer's look to
others, and figure templates (a figure's layout and look, applied to another run).

A mixin of the FigureEditor (cm1view/figui.py)."""

import html
import os

import panel as pn

from . import spec as fg
from .cards import TYPE_LABEL, _grid, _hint, _row, _section

PRESETS = {"cm1view (default)": "default", "AMS journal": "ams", "Talk": "talk",
           "Talk, dark": "dark"}


class FigureStyle:
    def _build_style(self):
        lt = dict(button_type="light", button_style="outline", height=32)
        # ---- presets (Style tab)
        self.preset = pn.widgets.Select(name="Preset", options=PRESETS, value="ams")
        self.preset_go = pn.widgets.Button(name="Apply preset", **lt)
        self.mplstyle = pn.widgets.TextInput(
            name="matplotlib style (blank: none)", placeholder="e.g. dark_background",
            description="A matplotlib style name or a .mplstyle file on the server: its "
                        "colours and lines (fonts and sizes stay those above)")
        self.preset_go.on_click(lambda e: self._apply_preset())
        self.preset_sec = _section(
            "Presets", _hint(
                "A preset sets the fonts, label sizes, frame, background, figure width and "
                "export at once (Undo takes it back). <b>AMS journal</b>: 8 pt sans-serif, "
                "(a) letters, 3.2 in wide for one column (6.5 in for more), PDF at 600 DPI. "
                "<b>Talk</b>: large text, 10 in wide; <b>dark</b>: on black."),
            _grid(self.preset, self.preset_go), _grid((self.mplstyle, 3)))
        # ---- copy look (Layers tab)
        self.look_from = pn.widgets.Select(name="Copy the look of", options={})
        self.look_to = pn.widgets.MultiChoice(name="To layers", options={})
        self.look_go = pn.widgets.Button(name="Copy", **lt)
        self.look_go.on_click(lambda e: self._copy_look())
        self.look_row = _section(
            "Copy a layer's look", _hint(
                "Colours, lines, style and colorbar of one layer onto others of its kind; "
                "the colour range, levels and labels too when they show the same field."),
            _grid(self.look_from, (self.look_to, 2)), _row(self.look_go), collapsed=True)
        # ---- templates (Export tab)
        self.tpl_name = pn.widgets.TextInput(name="Template name", placeholder="e.g. 2x3 dbz w")
        self.tpl_save = pn.widgets.Button(name="Save as template", **lt)
        self.tpl_sel = pn.widgets.Select(name="Template", options={})
        self.tpl_go = pn.widgets.Button(name="Apply to this run", **lt)
        self.tpl_save.on_click(lambda e: self._save_template())
        self.tpl_go.on_click(lambda e: self._apply_template())
        self.tpl_sec = _section(
            "Templates", _hint(
                "A template keeps the figure's panels, layers and look without its runs: "
                "apply it to the run shown, its times moved to the map's time (as far "
                "apart as they were). What only another run had is left out. Saved in "
                f"<code>{html.escape(fg.templates_dir())}</code>."),
            _grid((self.tpl_name, 2), self.tpl_save), _grid((self.tpl_sel, 2), self.tpl_go))
        self._list_templates()

    # ------------------------------------------------------------ presets
    def _apply_preset(self):
        self.set_spec(fg.apply_style(self.collect(), self.preset.value))
        self._msg(f"Preset <b>{html.escape(self.preset.label or '')}</b> applied "
                  "(Undo takes it back)")

    # ------------------------------------------------------------ copy look
    def _look_opts(self):
        """The layer choices (after the layer cards change)."""
        opts = {}
        for j, c in enumerate(self.cards):
            name = f"{j + 1}. {TYPE_LABEL[c.type]}"
            if "field" in c.w:
                name += f": {self.fields[c.w['field'].value].label}"
            opts[name] = j
        hold, self._hold = self._hold, True
        try:
            v, to = self.look_from.value, self.look_to.value
            self.look_from.options = opts
            self.look_from.value = v if v in opts.values() else next(iter(opts.values()), None)
            self.look_to.options = opts
            self.look_to.value = [j for j in to or [] if j in opts.values()]
        finally:
            self._hold = hold

    def _copy_look(self):
        i, to = self.look_from.value, [j for j in self.look_to.value if j != self.look_from.value]
        if i is None or not to:
            self._msg("Choose a layer to copy from and layers to copy to", True)
            return
        src = self.cards[i].collect()
        skipped = [j + 1 for j in to if self.cards[j].type != src["type"]]
        for j in to:
            if self.cards[j].type == src["type"]:
                self.cards[j] = self._card(fg.copy_look(src, self.cards[j].collect()))
        self.look_to.value = []
        self._show_cards()
        self.request()
        self._msg("Copied" + (f"; not to layer(s) {', '.join(map(str, skipped))} (another "
                              "kind)" if skipped else ""), bool(skipped))

    # ------------------------------------------------------------ templates
    def _list_templates(self):
        try:
            self.tpl_sel.options = fg.list_templates()
        except OSError:
            self.tpl_sel.options = {}
        self.tpl_go.disabled = not self.tpl_sel.options

    def _save_template(self):
        try:
            path = fg.save_template(self.collect_all(), self.tpl_name.value.strip())
        except (OSError, ValueError) as e:
            self._msg(f"Could not save the template: {html.escape(str(e))}", True)
            return
        self._list_templates()
        self.tpl_sel.value = path
        self._msg(f"Saved the template <code>{html.escape(path)}</code>")

    def _apply_template(self):
        path = self.tpl_sel.value
        try:
            spec = fg.from_template(fg.load_template(path), self.run, self.v.t)
        except (OSError, ValueError) as e:
            self._msg(f"Could not apply <code>{html.escape(str(path))}</code>: "
                      f"{html.escape(str(e))}", True)
            return
        self._open_spec(spec, "Applied the template <b>"
                        f"{html.escape(os.path.basename(path)[:-5])}</b> to this run")
