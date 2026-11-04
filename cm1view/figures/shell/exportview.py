"""The Export dialog of the new layout: where and how the image is saved, an animation, and the
figure as a template.  The saving itself is the FigureEditor's (FigureExport, FigureAnimation,
FigureStyle), which takes what the shell holds while it is what shows: its widgets here are copies
that write to the editor's.  The image's settings (format, DPI, background, fit, margin) are the
document's, written with its other edits, so Undo takes them back."""

import os

import panel as pn

from ... import config
from .. import spec as fg
from ..cards import _grid, _hint
from ..cards.base import SECTION
from ..widgets import DIALOG_DARK
from .looks import Scope, make_widget, rows_of
from .multirun import ApplyRuns


class ExportDialog:
    def __init__(self, shell):
        self.shell, self.ed = shell, shell.ed
        ed = self.ed
        self.path = self._copy(ed.path)
        self.more = self._copy(ed.save_more)
        self.save = pn.widgets.Button(name="Save", icon="device-floppy", button_type="primary",
                                      height=32, margin=(5, 3),
                                      description="Save the image, and the figure's settings to "
                                                  "reopen it")
        self.dl = pn.widgets.FileDownload(callback=ed._download, filename="figure.png",
                                          label="Download", icon="download", button_type="primary",
                                          button_style="outline", height=32, margin=(5, 3))
        self.save.on_click(lambda e: self._save())
        self.path.param.watch(lambda e: self._names(), "value")
        self.rows = pn.Column(margin=0, sizing_mode="stretch_width")
        self.body = pn.Column(margin=0, sizing_mode="stretch_width", scroll="y-auto",
                              styles={"max-height": "82vh"})
        self.dlg = pn.Modal(self.body, width=640, margin=10, stylesheets=[DIALOG_DARK])
        self._built = False

    # ------------------------------------------------------------ copies of the editor's widgets
    @staticmethod
    def _copy(src):
        """A copy of an editor's widget: each follows the other."""
        w = src.clone(visible=True, disabled=False)

        def put(to):
            return lambda ev: setattr(to, "value", ev.new)

        w.param.watch(put(src), "value")
        src.param.watch(put(w), "value")
        return w

    @staticmethod
    def _echo(src):
        """A pane saying what an editor's pane says."""
        w = pn.pane.HTML(src.object, margin=(0, 8), sizing_mode="stretch_width")
        src.param.watch(lambda ev: setattr(w, "object", ev.new), "object")
        return w

    def _build(self):
        """The widgets that aren't the image's: made the first time the dialog opens."""
        ed = self.ed
        self.an_end = self._copy(ed.an_end)
        self.an_fmt = self._copy(ed.an_fmt)
        self.an_path = self._copy(ed.an_path)
        self.an_path.name = "Save path"
        self.an_path.placeholder = "blank: <Save as>.gif or .mp4"
        self.an_fmt.param.watch(lambda ev: setattr(self.an_loop, "visible", ev.new == "gif"),
                                "value")
        ed.an_end.param.watch(lambda ev: setattr(self.an_end, "options", ev.new), "options")
        self.an_go = pn.widgets.Button(name="Save animation", icon="movie", button_type="primary",
                                       height=32)
        self.an_stop = pn.widgets.Button(name="Stop", button_type="light", button_style="outline",
                                         height=32, disabled=True)
        self.an_go.on_click(lambda e: self._animate())
        self.an_stop.on_click(lambda e: ed._stop_anim())
        for src, w in ((ed.an_go, self.an_go), (ed.an_stop, self.an_stop)):
            src.param.watch(lambda ev, w=w: setattr(w, "disabled", ev.new), "disabled")
        self.an_loop = self._copy(ed.an_loop)
        self.anim = pn.Card(
            _hint("The figure redrawn at successive output times from the panels' own times: every "
                  "panel steps forward together, storm-centred panels and soundings follow the "
                  "storm, and each 3D scene turns by its own orbit. Time–height plots and time "
                  "series show every time already, so they stay as they are. The frames start "
                  "from the saved time, not the preview scrubber's. Saved at <i>Save path</i>, "
                  "or <code>&lt;Save as&gt;.gif</code> / <code>.mp4</code> if it is blank."),
            _grid((self.an_path, 3)), _grid(self.an_fmt), self._echo(ed.an_fmt_note),
            _grid(self._copy(ed.an_step), self.an_end, self._copy(ed.an_fps)), self._echo(ed.an_count),
            _grid(self._copy(ed.an_dpi), self.an_loop, self._copy(ed.an_frames)),
            pn.Row(self.an_go, self.an_stop, margin=0), title="Animation (GIF or video)", collapsed=True,
            **SECTION)
        self.anim.param.watch(lambda ev: ev.new or ed._anim_refresh(force=True), "collapsed")
        self.tpl_go = pn.widgets.Button(name="Save as template", button_type="light",
                                        button_style="outline", height=32, align="end")
        self.tpl_go.on_click(lambda e: self._template())
        self.tpl_said = pn.pane.HTML(margin=(0, 8), sizing_mode="stretch_width")
        self.template = pn.Card(
            _hint("A template keeps the figure's panels, layers and look without its runs: New "
                  "applies it to the run shown, its times moved to the map's time (as far apart as "
                  "they were). What only another run had is left out. Saved in "
                  f"<code>{fg.templates_dir()}</code>."),
            _grid((self._copy(ed.tpl_name), 2), self.tpl_go), self.tpl_said,
            title="Template", collapsed=True, **SECTION)
        self.runs = ApplyRuns(self.shell)
        self.body.objects = [
            pn.pane.HTML('<div class="cv-maptitle" style="font-size:16px"><b>Export the figure'
                         '</b></div>', margin=(0, 4)),
            self.path, self.rows,
            _hint("Publishers usually ask for 300–600 DPI, or PDF / EPS for line art."),
            self.more,
            _hint("The script (<code>scripts/&lt;name&gt;.py</code>) redraws the figure without the "
                  "viewer, from the data and drawing code it adds to <code>_src/</code>."),
            pn.Row(self.save, self.dl), self.anim, self.template, self.runs.card]
        self._built = True

    # ------------------------------------------------------------ opening it
    def open(self):
        if not self._built:
            self._build()
        self.shell.ed.path.value = self._default_path()
        self._show_rows()
        self._names()
        self.runs.refresh()
        if not self.anim.collapsed:
            self.ed._anim_refresh(force=True)
        self.dlg.show()

    def _default_path(self):
        """Where to save: as the old layout says for a figure of several runs, which has no folder
        of its own: the last folder used for one, else the user chooses."""
        ed = self.ed
        cur = config.expand(ed.path.value.strip())
        if len(self.shell.doc.get("runs") or []) > 1 and \
                (not cur or os.path.dirname(cur) == ed._fig_dir):
            last = config.state("last_multi_run_dir")
            return os.path.join(last, os.path.basename(cur) or "figure") if last else ""
        return ed.path.value

    def _show_rows(self):
        """The image's settings, from the document."""
        shell, doc = self.shell, self.shell.doc
        scope = Scope()
        kinds = list(dict.fromkeys(p["kind"] for p in doc["panels"]))

        def changed(st, w):
            shell.edit(lambda d: scope.write(d, st, w.value))
            self._names()
            self._fit_shows(by_key)

        by_key = {st.key: make_widget(self.ed, st, scope.value(doc, st), changed)
                  for st in rows_of("Export", kinds)}
        self.rows.objects = [_grid(*by_key.values(), n=3)]
        self._fit_shows(by_key)

    @staticmethod
    def _fit_shows(by_key):
        if "export.pad" in by_key and "export.*" in by_key:
            by_key["export.pad"].visible = by_key["export.*"].value != "full"

    def _names(self):
        doc = self.shell.doc or {}
        fmt = (doc.get("export") or {}).get("format", "png")
        self.dl.filename = f"{os.path.basename(self.path.value or '') or 'figure'}.{fmt}"
        self.save.disabled = not (self.path.value or "").strip()

    # ------------------------------------------------------------ doing it
    def _save(self):
        self.dlg.hide()  # (progress is above the preview; "replace?" is a dialog too)
        self.ed._save(self.more.value)

    def _animate(self):
        self.dlg.hide()
        self.ed._on_anim()

    def _template(self):
        ed = self.ed
        ed._save_template()
        self.tpl_said.object = ed.msg.object
