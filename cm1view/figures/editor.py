"""Figure workspace: build a publication figure from panels and layers (from one run or
several, e.g. tornadic vs non-tornadic), preview it at its final size, and export the
image, a stand-alone script, the data and the document.

What is on the page is the shell (figures/shell): the tree, the preview and the inspector, on
the figure document.  The FigureEditor holds what the shell works with, one mixin a module: the
widgets its settings are copied from (widgets, style, scene), the runs a figure could add (runs),
new figures from the viewer's tools (sources, scene), saving and autosave (export), animations
(anim), templates (style) and the New dialog (quick).
The data behind a figure (reading the runs, the caches) is FigureData's (render), which
works without the editor."""

import html
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from .anim import FigureAnimation
from .export import FigureExport
from .quick import FigureQuick
from .render import FigureData
from .runs import AllFields, FigureRuns
from .scene import FigureScene
from .shell import FigureShell
from .sources import FigureSources
from .style import FigureStyle
from .widgets import FigureWidgets


class FigureEditor(FigureWidgets, FigureRuns, FigureSources, FigureExport, FigureAnimation,
                   FigureStyle, FigureQuick, FigureScene):
    shell = None  # (made last: what builds the widgets asks whether there is one)

    def __init__(self, viewer):
        self.v = viewer
        self.run, self.F = viewer.run, viewer.F
        self.fields = AllFields([self.F])  # the field lists: the fields of every run
        self._auto_wrote = self._auto_failed = False  # (this page's autosave: _autosave)
        viewer.pools["figser"] = ThreadPoolExecutor(1, thread_name_prefix="cm1view-figser")
        viewer.gen["figser"] = 0
        # the figure's data and its caches (figures/render.py), the series filled in
        # the background, each update re-rendering the preview
        self.data = FigureData(
            self.run, self.F, getattr(viewer, "reg", None), lambda: viewer.fixes,
            lambda text: viewer._schedule(partial(
                self._status, f'<span class="busy">● {html.escape(text)}</span>')),
            viewer.pools["figser"], lambda: viewer._schedule(partial(self.request, False, False)),
            lambda: viewer.gen["figser"])
        self._build_panel_widgets()
        self._build_layer_widgets()
        self._build_scene()
        self._build_text()
        self._build_more()
        self._build_anim()
        self._build_style()
        self._build_quick()
        self._scan_roots()
        self.shell = FigureShell(self)
        self.shell.start(self._default())

    @property
    def panel(self):
        """What goes on the page."""
        return self.shell.panel

    def request(self, force=False, delay=True):
        """Draw the preview again, once the workspace has been opened (a series coming in)."""
        if self.shell is not None and self.shell.showing:
            self.shell.request(force, delay)

    def panel_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of the figure, from the cache where possible."""
        return self.data.panel_data(spec, progress, cancelled)

    def open_run(self, path):
        """(CM1Run, Fields) of the run in `path` (the viewer's own run, or one opened
        through the viewer's registry so its cache is shared)."""
        return self.data.open_run(path)

    def run_fixes(self, entry, run):
        """Track fixes {t: fix} of a run entry ({} without a track)."""
        return self.data.run_fixes(entry, run)

    def series_pending(self):
        return self.data.series_pending()

    def _status(self, text, err=False):
        if self.shell is not None:
            self.shell.say(text, err)

    def _msg(self, text, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.msg.object = f'<div class="cv-status"{col}>{text}</div>'
        self._status(text, err)
