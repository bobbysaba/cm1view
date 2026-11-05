"""Figure editor: the widgets of the look settings (text, axes and ticks, panel labels, colorbar,
legend, spacing, matplotlib style), and figure templates (a figure's layout and look, applied to
another run).

A mixin of the FigureEditor (figures/editor.py)."""

import html
import os

import panel as pn

from . import spec as fg
from .cards import (CB_LOCS, CB_MODES, FONTS, LABEL_LOCS, LETTERS, LOCS, MATH_FONTS, TICKDIR, _auto,
                    _f, _retired, panel_select)

STYLE_LABELS = {"default": "Default", "ams": "AMS journal", "talk": "Talk", "dark": "Dark"}


class FigureStyle:
    def _build_text(self):
        """The look settings' widgets (settings.py)."""
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
        # panel labels
        self.title_loc = pn.widgets.Select(name="Where", options={
            "Center": "center", "Left": "left", "Right": "right"})
        self.title_bold = pn.widgets.Checkbox(name="Bold")
        self.label_fit = pn.widgets.Checkbox(
            name="Shrink these labels to fit narrow panels", value=True)
        self.let_on = pn.widgets.Checkbox(name="Panel letters")
        self.let_fmt = pn.widgets.Select(name="Style", options=LETTERS)
        self.let_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.let_size = _auto("Size (pt)", step=1)
        self.let_bold = pn.widgets.Checkbox(name="Bold")
        self.let_box = pn.widgets.Checkbox(name="White box")
        self.tl_on = pn.widgets.Checkbox(name="Time label")
        self.tl_fmt = pn.widgets.TextInput(name="Text", description="{min}: minutes (from time zero), {model}: model minutes, {s}: "
                                           "seconds, {hms}: h:mm:ss; e.g. t = {min:g} min")
        self.tl_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.tl_size = _auto("Size (pt)", step=1)
        self.tl_bold = pn.widgets.Checkbox(name="Bold")
        self.tl_box = pn.widgets.Checkbox(name="White box")
        self.tl_t0 = _retired(_f(
            "Minutes counted from", 0.0, step=10,
            description="From an older figure: adds to each run's time zero (on the Runs "
                        "node), which is the place to set it. At 0 this box goes away"))
        self.zl_on = pn.widgets.Checkbox(name="Height label")
        self.zl_fmt = pn.widgets.TextInput(name="Text (blank: z = … km / k = …)",
                                           description="{z}: the height (km), {k}: the "
                                                       "model level; e.g. {z:g} km AGL")
        self.zl_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.zl_size = _auto("Size (pt)", step=1)
        self.zl_bold = pn.widgets.Checkbox(name="Bold")
        self.zl_box = pn.widgets.Checkbox(name="White box")
        self.rl_on = pn.widgets.Checkbox(name="Run name")
        self.rl_color = pn.widgets.Checkbox(name="In the run's colour")
        self.rl_loc = pn.widgets.Select(name="Where", options=LABEL_LOCS)
        self.rl_size = _auto("Size (pt)", step=1)
        self.rl_bold = pn.widgets.Checkbox(name="Bold")
        self.rl_box = pn.widgets.Checkbox(name="White box")
        # colorbar
        self.cb_mode = pn.widgets.Select(name="Colorbars", options=CB_MODES)
        self.cb_loc = pn.widgets.Select(name="Where", options=CB_LOCS)
        self.cb_label = pn.widgets.TextInput(
            name="Label of bars with none of their own (blank: units)",
            placeholder="e.g. w (m s$^{-1}$)",
            description="A panel's own Colorbar label comes first, so clear it for this one to "
                        "show; $…$ is math, e.g. m s$^{-1}$")
        self.cb_lbold = pn.widgets.Checkbox(name="Bold label")
        self.cb_lside = pn.widgets.Select(name="Label side", options={
            "Auto": "", "Above / left": "first", "Below / right": "second"})
        self.cb_fmt = pn.widgets.TextInput(name="Tick format (blank: auto)", placeholder="%g",
                                           description="e.g. %.1f, %d, %.0e")
        self.cb_ticks = pn.widgets.TextInput(
            name="Ticks of bars with none of their own (blank: auto)", placeholder="0:60:10",
            description="A panel's own Colorbar ticks come first")
        self.cb_shrink = _f("Length (0–1)", 0.7, step=0.05, start=0.1, end=1.0)
        self.cb_fraction = _f("Thickness (0–1)", 0.05, step=0.01, start=0.01, end=0.5)
        self.cb_pad = _f("Gap (0–1)", 0.02, step=0.01, start=0.0, end=0.5)
        self.cb_lsize = _auto("Label size (pt)")
        self.cb_tsize = _auto("Tick size (pt)")
        # legend
        self.lg_where = pn.widgets.Select(name="Layer legend on", options={
            "A panel": "panel", "The figure (this part)": "figure"})
        self.lg_loc = pn.widgets.Select(name="At", options=LOCS)
        self.lg_panel = panel_select("In panel")
        self.lg_anchor = pn.widgets.TextInput(
            name="Anchor x, y (blank: none)", placeholder="1.02, 1",
            description="Puts the legend's 'At' corner at this point: fractions of the panel "
                        "(on the figure: of the figure); below 0 or above 1 is outside it")
        self.lg_from = pn.widgets.TextInput(
            name="From panels (blank: all)", placeholder="a, c",
            description="The panels whose entries it lists (letters or numbers)")
        self.lg_title = pn.widgets.TextInput(name="Title")
        self.lg_ncol = pn.widgets.IntInput(name="Columns", start=1, end=8, value=1)
        self.lg_frame = pn.widgets.Checkbox(name="Frame")
        self.lg_own = pn.widgets.Checkbox(name="Panels' own legends", value=True)
        self.pl_on = pn.widgets.Checkbox(name="Legend", value=True)
        self.pl_loc = pn.widgets.Select(name="At", options=["best"] + LOCS)
        self.pl_ncol = pn.widgets.IntInput(name="Columns", start=1, end=8, value=1)
        self.pl_frame = pn.widgets.Checkbox(name="Frame")
        # spacing
        self.sp_w = _f("Between columns", 0.02, step=0.01, start=0.0,
                       description="Extra space between panels, as a fraction of a panel")
        self.sp_h = _f("Between rows", 0.02, step=0.01, start=0.0)
        self.sp_wpad = _f("Around panels, x (in)", 0.04, step=0.01, start=0.0,
                          description="Padding around each panel and its labels (inches)")
        self.sp_hpad = _f("Around panels, y (in)", 0.04, step=0.01, start=0.0)

    def _build_style(self):
        self.mplstyle = pn.widgets.TextInput(
            name="matplotlib style (blank: none)", placeholder="e.g. dark_background",
            description="A matplotlib style name or a .mplstyle file on the server: its "
                        "colours and lines (fonts and sizes stay those above)")
        self.tpl_name = pn.widgets.TextInput(name="Template name", placeholder="e.g. 2x3 dbz w")
        self.tpl_sel = pn.widgets.Select(name="Template", options={})
        self._list_templates()

    # ------------------------------------------------------------ templates
    def _list_templates(self):
        try:
            tpls = fg.list_templates()
        except OSError:
            tpls = {}
        keep = self.tpl_sel.value
        self.tpl_sel.options = tpls  # (a Select does not take a value from new options)
        self.tpl_sel.value = keep if keep in tpls.values() else next(iter(tpls.values()), None)

    def _save_template(self):
        try:
            path = fg.save_template(self._figure_now(), self.tpl_name.value.strip())
        except (OSError, ValueError) as e:
            self._msg(f"Could not save the template: {html.escape(str(e))}", True)
            return
        self._list_templates()
        self.tpl_sel.value = path
        self._msg(f"Saved the template <code>{html.escape(path)}</code>")

    def _apply_template(self, path):
        """Open a template on this run.  True when it opened."""
        try:
            spec = fg.from_template(fg.load_template(path), self.run, self.v.t)
        except (OSError, ValueError) as e:
            self._msg(f"Could not apply <code>{html.escape(str(path))}</code>: "
                      f"{html.escape(str(e))}", True)
            return False
        note = f"Applied the template <b>{html.escape(os.path.basename(path)[:-5])}</b> to this run"
        if fg.is_doc(spec):
            self.quick.hide()
            self.shell.open_doc(spec, note)
            return True
        return self._open_spec(spec, note)
