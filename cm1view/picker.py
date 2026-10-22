"""Run picker: one box and one list.  The list holds your recent runs and the runs found
under the runs_root setting; typing filters it, and typing or pasting a folder lists
the runs inside that folder instead.  Opening a run reloads the page with ?run=."""

import os

import panel as pn

from . import config, registry
from .theme import CSS, DIALOG_DARK


def _html(text="", **kw):
    return pn.pane.HTML(text, stylesheets=[CSS], **kw)


def _is_path(text):
    return text[:1] in ("/", "~", "$")


class RunPicker:
    """`body` holds the controls; `modal` wraps them in a dialog (with `extra` below)."""

    def __init__(self, current=None, extra=()):
        self.current = current
        self.query = pn.widgets.TextInput(
            placeholder="Filter runs, or paste a folder (e.g. /glade/derecho/scratch/...)",
            width=520, margin=(5, 10, 5, 0))
        self.open = pn.widgets.Button(name="Open run", button_type="primary", width=110,
                                      disabled=True, margin=(5, 0))
        self.list = pn.widgets.Select(options={}, size=13, width=640, margin=(5, 0))
        self.msg = _html()
        # navigation happens in the browser: the new session opens the run from ?run=
        self.go = pn.widgets.TextInput(visible=False)
        self.go.jscallback(value="""
            const p = (cb_obj.value || '').trim();
            if (!p) return;
            const q = new URLSearchParams(window.location.search);
            q.set('run', p); q.delete('t');
            window.location.search = q.toString();
        """)
        self.body = pn.Column(pn.Row(self.query, self.open, margin=0), self.list, self.msg,
                              self.go, margin=0)
        self.modal = pn.Modal(
            _html('<div class="cv-maptitle" style="font-size:16px"><b>Open a CM1 run</b>'
                  '</div>'),
            self.body, *extra, width=680, margin=10, stylesheets=[DIALOG_DARK])

        self.selected, self._hint = "", ""
        self._known = []  # runs under runs_root, from the last scan
        self._complete = True
        self._under = {}  # folder -> runs found under it (typed folders)
        self._busy = False
        self.query.param.watch(lambda e: self._refresh(), "value_input")
        self.list.param.watch(self._on_list, "value")
        self.open.on_click(lambda e: self._open())
        self.query.param.watch(lambda e: self._open(), "enter_pressed")
        self._refresh()  # recent runs until the first scan

    def show(self):
        self.rescan()
        self.modal.show()

    def rescan(self):
        """Look again for the runs under the runs_root setting."""
        self._known, self._complete = config.scan_runs(config.get("runs_root"))
        self._under.clear()
        self._refresh()

    # ------------------------------------------------------------------ list
    def _label(self, run, base=None):
        roots = [base] if base else [config.expand(r) for r in config.get("runs_root")]
        for r in roots:
            if run.startswith(r.rstrip("/") + "/"):
                return os.path.relpath(run, r)
        return run

    def _runs_under(self, folder):
        if folder not in self._under:
            self._under[folder] = config.scan_runs([folder], seconds=2.0)
        return self._under[folder]

    def _refresh(self):
        text = (self.query.value_input or "").strip()
        pick = None
        if _is_path(text):
            opts, hint, pick = self._folder_options(config.expand(text))
        else:
            opts, hint = self._known_options(text)
        keep = pick or (self.selected if self.selected in opts.values() else None)
        # always a selection: a Select shown without one picks its first entry while
        # the page is drawn, and what that changes (the Open button) never reaches
        # the browser
        keep = keep or next(iter(opts.values()), None)
        self._busy = True
        try:
            self.list.options = opts
            self.list.value = keep
        finally:
            self._busy = False
        self._select(keep or "", hint)

    def _known_options(self, text):
        recent = [p for p in registry.recent_runs() if p != self.current]
        runs = recent + [r for r in self._known if r not in recent and r != self.current]
        words = text.lower().split()
        runs = [r for r in runs if all(w in r.lower() for w in words)]
        opts = {}
        for r in runs:
            opts[self._label(r) + ("   · recent" if r in recent else "")] = r
        roots = config.get("runs_root")
        if not roots:
            hint = ('Recent runs. Set “Where your runs live” in ⚙ Settings to list all '
                    'your runs here, or paste a folder above.')
        else:
            n = len(self._known)
            more = " (stopped searching; paste a folder to look further)" * (not self._complete)
            hint = (f'{n} run{"s" * (n != 1)} under {", ".join(roots)}{more}, recent first. '
                    'Type to filter, or paste a folder.')
        if words and not opts:
            hint = f'No run matches “{text}”. ' + hint
        return opts, hint

    def _folder_options(self, p):
        """Runs under a typed folder (a run: it and the runs next to it); a partly
        typed name lists the matching runs of its parent folder.  Also returns the
        run to select."""
        pick = p if registry.is_run(p) else None
        if pick:
            base, part = os.path.dirname(p), ""
        elif os.path.isdir(p):
            base, part = p, ""
        else:
            base, part = os.path.dirname(p), os.path.basename(p).lower()
        if not os.path.isdir(base):
            return {}, "No such folder.", None
        runs, complete = self._runs_under(base)
        runs = [r for r in runs
                if not part or os.path.relpath(r, base).lower().startswith(part)]
        if pick and pick not in runs:
            runs = [pick] + runs
        opts = {self._label(r, base): r for r in runs}
        n = len(opts)
        more = " (stopped searching)" * (not complete)
        hint = (f'{n} run{"s" * (n != 1)} in {base}{more}' if n else
                f'No CM1 output in {base} or the folders below it.')
        return opts, hint, pick

    # ------------------------------------------------------------------ pick
    def _on_list(self, ev):
        if not self._busy:
            self._select(ev.new or "")

    def _select(self, path, hint=None):
        self.selected = path
        n = registry.count_files(path) if path else 0
        if hint is not None:
            self._hint = hint
        if n:
            line = (f'<span style="color:#4ade80">✓</span> <b>{path}</b> · {n} output '
                    f'files')
        else:
            line = self._hint
        self.msg.object = f'<div class="cv-hint" style="line-height:1.5">{line}</div>'
        self.open.disabled = n == 0

    def _open(self):
        if self.selected and not self.open.disabled:
            self.go.value = self.selected
