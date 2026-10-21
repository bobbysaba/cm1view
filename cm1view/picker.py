"""Run picker: type a run folder, browse folders, or pick a run found under the
runs_root setting or a recent one.  Opening a run reloads the page with ?run=."""

import os

import panel as pn

from . import config, registry
from .theme import CSS, DIALOG_DARK


def _html(text="", **kw):
    return pn.pane.HTML(text, stylesheets=[CSS], **kw)


class RunPicker:
    """`body` holds the controls; `modal` wraps them in a dialog (with `extra` below)."""

    def __init__(self, current=None, extra=()):
        self.current = current
        start = current or next(iter(config.get("runs_root")), "") or os.getcwd()
        self.path = pn.widgets.TextInput(name="Run directory (contains the CM1 output)",
                                         value=config.expand(start), width=620)
        self.msg = _html()
        self.found = pn.widgets.Select(name="Runs in your folders", options={}, width=620,
                                       size=6)
        self.found_msg = _html()
        self.list = pn.widgets.Select(name="Runs here", options={}, width=330, size=11)
        # folder browser: '..' and the subfolders of the typed path (● = has output)
        self.dirs = pn.widgets.Select(name="Folders", options={}, width=280, size=11)
        recent = [p for p in registry.recent_runs() if p != current]
        self.recent = pn.widgets.Select(
            name="Recent", options={"—": ""} | {p: p for p in recent}, value="", width=620)
        self.open = pn.widgets.Button(name="Open run", button_type="primary", width=120)
        # navigation happens in the browser: the new session opens the run from ?run=
        self.open.js_on_click(args=dict(inp=self.path), code="""
            const p = (inp.value_input || inp.value || '').trim();
            if (!p) return;
            const q = new URLSearchParams(window.location.search);
            q.set('run', p); q.delete('t');
            window.location.search = q.toString();
        """)
        self.body = pn.Column(
            self.path, self.msg, self.found, self.found_msg,
            pn.Row(self.list, self.dirs, margin=0), self.recent, pn.Row(self.open),
            margin=0)
        self.modal = pn.Modal(
            _html('<div class="cv-maptitle" style="font-size:16px"><b>Open a CM1 run</b>'
                  '</div><div class="cv-hint">Type or paste a run directory, or pick one '
                  'below. Opening a run reloads the page; open runs share one 3D cache '
                  '(least recently used fields are freed first).</div>'),
            self.body, *extra, width=680, margin=10, stylesheets=[DIALOG_DARK])

        self._busy = False
        self.list.param.watch(self._pick, "value")
        self.recent.param.watch(self._pick, "value")
        self.found.param.watch(self._pick, "value")
        self.dirs.param.watch(self._pick, "value")  # into a folder: the lists follow it
        self.path.param.watch(self._check, "value_input")
        self.path.param.watch(self._check, "value")
        self.path.param.trigger("value")

    def show(self):
        self.rescan()
        self.modal.show()

    def rescan(self):
        """List the runs under the runs_root setting."""
        roots = config.get("runs_root")
        runs, complete = config.scan_runs(roots)
        self._busy = True
        try:
            self.found.options = {self._label(r, roots): r for r in runs}
            self.found.value = None
        finally:
            self._busy = False
        more = "" if complete else " (stopped searching; browse below for more)"
        self.found_msg.object = (
            f'<div class="cv-hint">{len(runs)} run{"s" * (len(runs) != 1)} under '
            f'{", ".join(roots)}{more}</div>' if roots else
            '<div class="cv-hint">Set “Where your runs live” in ⚙ Settings to list your '
            'runs here.</div>')

    @staticmethod
    def _label(run, roots):
        for r in roots:
            r = config.expand(r)
            if run.startswith(r.rstrip("/") + "/"):
                return os.path.relpath(run, r)
        return run

    def _pick(self, ev):
        if ev.new and not self._busy:
            self.path.param.update(value=ev.new, value_input=ev.new)

    def _check(self, ev):
        p = config.expand((ev.new or "").strip())
        n = registry.count_files(p) if os.path.isdir(p) else 0
        if n:
            self.msg.object = (f'<div class="cv-status" style="color:#4ade80">'
                               f'✓ {n} output files</div>')
        elif os.path.isdir(p):
            self.msg.object = ('<div class="cv-status">No CM1 output files directly '
                               'here — pick a run below.</div>')
        else:
            self.msg.object = ('<div class="cv-status" style="color:#f87171">'
                               'Not a directory</div>')
        self.open.disabled = n == 0
        base = p if os.path.isdir(p) else os.path.dirname(p)
        if os.path.isdir(base):
            runs = registry.sibling_runs(base)
            self._busy = True
            try:
                self.list.options = {"/".join(r.split("/")[-3:]): r for r in runs}
                self.list.value = p if p in runs else None
                self.dirs.options = registry.subfolders(base)
                self.dirs.value = None
            finally:
                self._busy = False
