"""Figure editor: the Style tab's widgets (text, axes and ticks, panel labels,
colorbar, legend, contour key, spacing, matplotlib style), copying one layer's look to
others, and figure templates (a figure's layout and look, applied to another
run).

A mixin of the FigureEditor (figures/editor.py)."""

import html
import os

import panel as pn

from . import spec as fg
from .cards import (
    CB_LOCS, CB_MODES, FONTS, LABEL_LOCS, LETTERS, LOCS, MATH_FONTS, TICKDIR, TYPE_LABEL,
    _auto, _checks, _f, _grid, _hint, _label, _row, _section, _when,
)

class FigureStyle:
    def _build_text(self):
        """Style tab: text, axes and ticks, panel labels, colorbar, legend, spacing."""
        # ---- Style: text
        self.font = pn.widgets.Select(name="Font", options=FONTS)
        self.math = pn.widgets.Select(name="Math & units font", options=MATH_FONTS,
                                      description="Font of $...$ text, e.g. m s$^{-1}$")
        self.fsize = _f("Base size (pt)", 10.0, step=0.5, start=4)
        self.fs_tick = _auto("Tick labels (pt)")
        self.fs_label = _auto("Axis labels (pt)")
        self.fs_title = _auto("Panel titles (pt)")
        self.fs_sup = _auto("Figure title (pt)")
        self.fs_legend = _auto("Legends (pt)")
        # axes and ticks
        self.xlabel = pn.widgets.TextInput(name="x label")
        self.ylabel = pn.widgets.TextInput(name="y label")
        self.ticklabels = pn.widgets.Select(name="Tick labels on", options={
            "All panels": "all", "Outer panels": "outer", "No panels": "none"})
        self.share = pn.widgets.Select(name="Share limits (panels of a kind)", options={
            "No": "none", "x": "x", "y": "y", "x and y": "both"})
        self.tickdir = pn.widgets.Select(name="Ticks point", options=TICKDIR)
        self.ticks = pn.widgets.Checkbox(name="Tick marks")
        self.minor = pn.widgets.Checkbox(name="Minor ticks")
        self.xstep = _auto("x tick every", start=0)
        self.ystep = _auto("y tick every", start=0)
        self.frame_lw = _f("Frame width (pt)", 0.8, step=0.1, start=0.1)
        self.grid = pn.widgets.Checkbox(name="Grid lines")
        self.grid_ls = pn.widgets.Select(name="Grid style", options={
            "dotted": ":", "dashed": "--", "solid": "-"})
        self.equal = pn.widgets.Checkbox(name="Equal x/y scale")
        self.title_loc = pn.widgets.Select(name="Panel titles at", options={
            "Center": "center", "Left": "left", "Right": "right"})
        self.title_bold = pn.widgets.Checkbox(name="Bold titles")
        # panel labels
        self.let_on = pn.widgets.Checkbox(name="Panel letters")
        self.let_fmt = pn.widgets.Select(name="Style", options=LETTERS)
        self.let_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.let_size = _f("Size (pt)", 12.0, step=1)
        self.let_bold = pn.widgets.Checkbox(name="Bold")
        self.let_box = pn.widgets.Checkbox(name="White box")
        self.tl_on = pn.widgets.Checkbox(name="Time label")
        self.tl_fmt = pn.widgets.TextInput(name="Text", description="{min}: minutes, {s}: "
                                           "seconds, {hms}: h:mm:ss; e.g. t = {min:g} min")
        self.tl_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.tl_size = _f("Size (pt)", 12.0, step=1)
        self.tl_bold = pn.widgets.Checkbox(name="Bold")
        self.tl_box = pn.widgets.Checkbox(name="White box")
        self.tl_t0 = _f("Minutes counted from", 0.0, step=10,
                        description="Time zero for {min}, in model minutes (e.g. the "
                                    "initiation time)")
        self.zl_on = pn.widgets.Checkbox(name="Height label (panels at heights)")
        self.zl_fmt = pn.widgets.TextInput(name="Text (blank: z = … km / k = …)",
                                           description="{z}: the height (km), {k}: the "
                                                       "model level; e.g. {z:g} km AGL")
        self.zl_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.zl_size = _f("Size (pt)", 12.0, step=1)
        self.zl_bold = pn.widgets.Checkbox(name="Bold")
        self.zl_box = pn.widgets.Checkbox(name="White box")
        self.rl_on = pn.widgets.Checkbox(name="Run name (several runs)")
        self.rl_color = pn.widgets.Checkbox(name="In the run's colour")
        self.rl_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.rl_size = _f("Size (pt)", 12.0, step=1)
        self.rl_bold = pn.widgets.Checkbox(name="Bold")
        self.rl_box = pn.widgets.Checkbox(name="White box")
        # colorbar
        self.cb_mode = pn.widgets.Select(name="Colorbars", options=CB_MODES)
        self.cb_loc = pn.widgets.Select(name="Where", options=CB_LOCS)
        self.cb_label = pn.widgets.TextInput(
            name="Label, every colorbar (blank: units)", placeholder="e.g. w (m s$^{-1}$)",
            description="For colorbars without their own label (Layers: a fill layer's or "
                        "a time–height series' Colorbar label); $…$ is math, e.g. m s$^{-1}$")
        self.cb_lbold = pn.widgets.Checkbox(name="Bold label")
        self.cb_lside = pn.widgets.Select(name="Label side", options={
            "Auto": "", "Above / left": "first", "Below / right": "second"})
        self.cb_fmt = pn.widgets.TextInput(name="Tick format (blank: auto)", placeholder="%g",
                                           description="e.g. %.1f, %d, %.0e")
        self.cb_ticks = pn.widgets.TextInput(
            name="Ticks, every colorbar (blank: auto)", placeholder="0:60:10",
            description="For colorbars without their own ticks (Layers: Colorbar ticks)")
        self.cb_shrink = _f("Length (0–1)", 0.7, step=0.05, start=0.1, end=1.0)
        self.cb_fraction = _f("Thickness (0–1)", 0.05, step=0.01, start=0.01, end=0.5)
        self.cb_pad = _f("Gap (0–1)", 0.02, step=0.01, start=0.0, end=0.5)
        self.cb_lsize = _auto("Label size (pt)")
        self.cb_tsize = _auto("Tick size (pt)")
        # legend
        self.lg_where = pn.widgets.Select(name="Layer legend on", options={
            "A panel": "panel", "The figure (this part)": "figure"})
        self.lg_loc = pn.widgets.Select(name="At", options=LOCS)
        self.lg_panel = pn.widgets.IntInput(name="In panel", start=1, end=64)
        self.lg_anchor = pn.widgets.TextInput(
            name="Anchor x, y (blank: none)", placeholder="1.02, 1",
            description="Puts the legend's 'At' corner at this point: fractions of the panel "
                        "(on the figure: of the figure); below 0 or above 1 is outside it")
        self.lg_from = pn.widgets.TextInput(
            name="From panels (blank: all)", placeholder="1, 3",
            description="The panels whose entries it lists (panel numbers)")
        self.lg_title = pn.widgets.TextInput(name="Title")
        self.lg_ncol = pn.widgets.IntInput(name="Columns", start=1, end=8, value=1)
        self.lg_frame = pn.widgets.Checkbox(name="Frame")
        self.lg_own = pn.widgets.Checkbox(name="Panels' own legends", value=True)
        # spacing
        self.sp_w = _f("Between columns", 0.02, step=0.01, start=0.0,
                       description="Extra space between panels, as a fraction of a panel")
        self.sp_h = _f("Between rows", 0.02, step=0.01, start=0.0)
        self.sp_wpad = _f("Around panels, x (in)", 0.04, step=0.01, start=0.0,
                          description="Padding around each panel and its labels (inches)")
        self.sp_hpad = _f("Around panels, y (in)", 0.04, step=0.01, start=0.0)

    def _style_tab(self):
        """The Style tab."""
        def part(name, *objs):  # a label's settings, under its name
            return pn.Column(_label(f"<b>{name}</b>"), _grid(*objs), margin=0,
                             sizing_mode="stretch_width")
        let = part("Panel letters", self.let_fmt, self.let_loc, self.let_size, self.let_bold,
                   self.let_box)
        tl = part("Time label", (self.tl_fmt, 2), self.tl_loc, self.tl_size, self.tl_bold,
                  self.tl_box)
        rl = part("Run name", self.rl_loc, self.rl_size, self.rl_bold, self.rl_box,
                  self.rl_color)
        zl = part("Height label", (self.zl_fmt, 2), self.zl_loc, self.zl_size,
                                self.zl_bold, self.zl_box)
        _when(self.let_on, let)
        _when(self.tl_on, tl)
        _when(self.rl_on, rl)

        def zl_show(*e):  # (Panels → vary hides zl_on unless the panels vary in height)
            zl.visible = self.zl_on.visible and self.zl_on.value
        self.zl_on.param.watch(zl_show, ["value", "visible"])
        zl_show()
        _when(self.grid, self.grid_ls)
        self.ck_opts = _grid(self.ck_layer, self.ck_label, self.ck_x, self.ck_y,
                             self.ck_size, self.ck_fs)
        _when(self.ck_on, self.ck_opts, self.ck_frame)
        self.cb_opts = _grid(self.cb_loc, self.cb_shrink, self.cb_fraction, (self.cb_label, 2),
                             self.cb_lbold, self.cb_lside, self.cb_lsize, self.cb_pad,
                             self.cb_ticks, self.cb_fmt, self.cb_tsize)
        style_tab = pn.Column(
            _section("Text", _grid(self.font, self.math, self.fsize, self.fs_tick,
                                   self.fs_label, self.fs_title, self.fs_sup, self.fs_legend),
                     _hint("Blank sizes follow the base size.")),
            _section("Axes and ticks", _grid(
                self.xlabel, self.ylabel, self.ticklabels, self.share, self.xstep, self.ystep,
                self.tickdir, self.frame_lw, self.grid_ls, self.title_loc),
                _checks(self.ticks, self.minor, self.grid, self.equal, self.title_bold),
                _hint("Labels take matplotlib math, e.g. <code>w (m s$^{-1}$)</code>. Tick "
                      "labels on outer panels only when the panels share their ranges.")),
            _section("Panel labels", let, tl, _grid(self.tl_t0), zl, rl,
                     _checks(self.let_on, self.tl_on, self.zl_on, self.rl_on)),
            _section("Colorbar", _grid(self.cb_mode), self.cb_opts, _hint(
                "With several colorbars, give each its own label and ticks where its "
                "colours are set: the fill layer (Layers), each time–height series "
                "(Layers → Series) or each panel's field (Panels, when panels differ in "
                "field). The label and ticks here are for the others.")),
            _section("Legend", _grid(self.lg_where, self.lg_loc, self.lg_anchor,
                                     self.lg_panel, self.lg_from, self.lg_ncol, self.lg_title),
                     _checks(self.lg_frame, self.lg_own),
                     _hint("The legend lists layers with a legend entry (contours, shading, "
                           "track, section line), once for all the panels. On the figure "
                           "it also gathers the legends of time-series, distribution and "
                           "sounding panels and hodograph keys (each panel's own Legend "
                           "setting turns its entries on or off), listing an entry shared "
                           "by panels once; the <i>outside</i> places make room beside the "
                           "panels. Columns and frame of those panels' own legends are set "
                           "in Panels, and for one panel alone in Tree. A legend on the "
                           "figure, or <i>Panels' own legends</i> off, hides the panels' "
                           "own legends, except a panel whose Tree <i>Legend</i> is Yes.")),
            _section("Contour key", _hint(
                "Nested circles labelled with a contour layer's levels (a key for unlabelled "
                "contours), placed in figure fractions from the lower left."),
                self.ck_opts, _checks(self.ck_on, self.ck_frame)),
            _section("Spacing", _grid(self.sp_w, self.sp_h, self.sp_wpad, self.sp_hpad)),
            _section("matplotlib style", _grid((self.mplstyle, 3))),
            sizing_mode="stretch_width")
        return style_tab

    def _build_style(self):
        lt = dict(button_type="light", button_style="outline", height=32)
        # ---- matplotlib style (Style tab)
        self.mplstyle = pn.widgets.TextInput(
            name="matplotlib style (blank: none)", placeholder="e.g. dark_background",
            description="A matplotlib style name or a .mplstyle file on the server: its "
                        "colours and lines (fonts and sizes stay those above)")
        # ---- copy look (Layers tab)
        self.look_from = pn.widgets.Select(name="Copy the look of", options={})
        self.look_to = pn.widgets.MultiChoice(name="To layers", options={})
        self.look_go = pn.widgets.Button(name="Copy", **lt)
        self.look_go.on_click(lambda e: self._copy_look())
        self.look_row = _section(
            "Copy a layer's look", _hint(
                "Colours, lines, style and colorbar of one layer onto others of its kind; "
                "the colour range, levels and labels too when they show the same field."),
            _grid(self.look_from, (self.look_to, 2)), _row(self.look_go))
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
