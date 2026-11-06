"""Run picker: one box and one list.  The list holds your recent runs and the runs found
under the runs_root setting; typing filters it, and a folder typed or pasted with a
"/" at the end (or Enter) lists the runs inside it instead.  Shared folders (see
config.searchable) are never searched.  The model box says which model's output to look
for (auto-detect: any).  Opening a run reloads the page with ?run= (and ?model= when one
was chosen)."""

import json
import os

import panel as pn

from .. import config, registry
from ..core import models
from ..theme import CSS, DIALOG_DARK


def _html(text="", **kw):
    return pn.pane.HTML(text, stylesheets=[CSS], **kw)


def _is_path(text):
    return text[:1] in ("/", "~", "$")


def _shared(folder):
    return (f"Not searching {folder}: it is a shared folder, and looking through it "
            "would list every user's folders. Type the path of a folder of your own.")


class RunPicker:
    """`body` holds the controls; `modal` wraps them in a dialog (with `extra` below).

    on_open(path), when given, is called with the chosen run instead of opening it in
    the browser (e.g. the figure editor adding a run); exclude() -> paths left out of
    the list (besides `current`); compact: a shorter list that fills its column."""

    def __init__(self, current=None, extra=(), on_open=None, open_label="Open run",
                 exclude=None, compact=False):
        self.current, self.on_open, self.exclude = current, on_open, exclude
        size = dict(sizing_mode="stretch_width") if compact else {}
        self.query = pn.widgets.TextInput(
            placeholder="Filter runs, or paste a folder (e.g. /scratch/you/cm1/run1)",
            width=None if compact else 400, margin=(5, 10, 5, 0), **size)
        self.model = pn.widgets.Select(options=models.choices(), value=models.AUTO,
                                       width=110 if compact else 120, margin=(5, 10, 5, 0),
                                       description="Which model's output to look for "
                                                   "(auto-detect: any model cm1view reads)")
        self.open = pn.widgets.Button(name=open_label, button_type="primary", width=110,
                                      disabled=True, margin=(5, 0))
        self.list = pn.widgets.Select(options={}, size=7 if compact else 13,
                                      width=None if compact else 640, margin=(5, 0), **size)
        self.msg = _html()
        # navigation happens in the browser: the new session opens the run from ?run=
        self.go = pn.widgets.TextInput(visible=False)
        self.go.jscallback(value="""
            const v = (cb_obj.value || '').trim();
            if (!v) return;
            const [p, m] = JSON.parse(v);
            const q = new URLSearchParams(window.location.search);
            q.set('run', p); q.delete('t'); q.delete('session');
            if (m && m !== 'auto') q.set('model', m); else q.delete('model');
            window.location.search = q.toString();
        """)
        self.body = pn.Column(pn.Row(self.query, self.model, self.open, margin=0, **size),
                              self.list,
                              self.msg, self.go, margin=0, **size)
        self.modal = pn.Modal(
            _html('<div class="cv-maptitle" style="font-size:16px"><b>Open a run</b>'
                  '</div>'),
            self.body, *extra, width=680, margin=10, stylesheets=[DIALOG_DARK])

        self.selected, self._hint = "", ""
        self._known = []  # runs under runs_root, from the last scan
        self._complete = True
        self._under = {}  # folder -> runs found under it (typed folders)
        self._busy = False
        self.query.param.watch(lambda e: self._refresh(), "value_input")
        self.model.param.watch(lambda e: self.rescan(), "value")
        self.list.param.watch(self._on_list, "value")
        self.open.on_click(lambda e: self._open())
        self.query.param.watch(lambda e: self._on_enter(), "enter_pressed")
        self._refresh()  # recent runs until the first scan

    def show(self):
        self.rescan()
        self.modal.show()

    def rescan(self):
        """Look again for the runs under the runs_root setting."""
        self.set_known(*config.scan_runs(config.get("runs_root"), model=self.model.value))

    def set_known(self, runs, complete=True):
        """The runs under runs_root (from a scan made elsewhere)."""
        self._known, self._complete = list(runs), complete
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
            self._under[folder] = config.scan_runs([folder], seconds=2.0,
                                                   model=self.model.value)
        return self._under[folder]

    def _refresh(self, search=False):
        text = (self.query.value_input or "").strip()
        pick = None
        if _is_path(text):
            opts, hint, pick = self._folder_options(text, search)
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
        skip = {self.current} | set(self.exclude() if self.exclude else ())
        recent = [p for p in registry.recent_runs() if p not in skip]
        runs = recent + [r for r in self._known if r not in recent and r not in skip]
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

    def _folder_options(self, text, search=False):
        """Runs under a typed folder, looked for once the text ends in "/" (or search:
        Enter was pressed); a run typed in full is picked as it is; a partly typed name
        filters the runs found in its folder (if that was looked in).  Shared folders
        are never searched.  Also returns the run to select."""
        p = config.expand(text)
        looking = (search or text.endswith("/")) and os.path.isdir(p)
        pick = None
        if looking:
            base, part = p, ""
        else:
            # (a folder is only looked at when it is not a shared one)
            if not os.path.isdir(p) or config.searchable(p):
                pick = p if registry.is_run(p, self.model.value) else None
            base, part = os.path.dirname(p), ("" if pick else os.path.basename(p).lower())
        if not os.path.isdir(base):
            return {}, "No such folder.", None
        if not (looking or base in self._under):
            opts = {self._label(pick, base): pick} if pick else {}
            where = p if os.path.isdir(p) else base
            hint = (f"End the path with / (or press Enter) to look for runs in {where}."
                    if config.searchable(where) else _shared(where))
            return opts, hint, pick
        if not config.searchable(base):
            opts = {self._label(pick, base): pick} if pick else {}
            return opts, _shared(base), pick
        runs, complete = self._runs_under(base)
        runs = [r for r in runs
                if not part or os.path.relpath(r, base).lower().startswith(part)]
        if pick and pick not in runs:
            runs = [pick] + runs
        opts = {self._label(r, base): r for r in runs}
        n = len(opts)
        more = " (stopped searching)" * (not complete)
        hint = (f'{n} run{"s" * (n != 1)} in {base}{more}' if n else
                f'No {self._what()} in {base} or the folders below it.')
        return opts, hint, pick

    # ------------------------------------------------------------------ pick
    def _on_list(self, ev):
        if not self._busy:
            self._select(ev.new or "")

    def _select(self, path, hint=None):
        self.selected = path
        key = self.model.value
        n = registry.count_files(path, key) if path else 0
        if hint is not None:
            self._hint = hint
        if n:
            m = models.get(key) or models.detect(path)
            more = models.summary(path, key)
            line = (f'<span style="color:#4ade80">✓</span> <b>{path}</b> · {m.label} · '
                    + (f'{more} · ' if more else '') + f'{n} output times')
        else:
            line = self._hint
        self.msg.object = f'<div class="cv-hint" style="line-height:1.5">{line}</div>'
        self.open.disabled = n == 0

    def _what(self):
        m = models.get(self.model.value)
        return f"{m.label} output" if m else "model output"

    def _on_enter(self):
        """Enter: open the chosen run, else look for runs in the typed folder."""
        text = (self.query.value_input or "").strip()
        p = config.expand(text) if _is_path(text) else ""
        unsearched = (p and p != self.selected and os.path.isdir(p)
                      and p not in self._under)
        if self.selected and not self.open.disabled and not unsearched:
            self._open()
        elif p:
            self._refresh(search=True)

    def _open(self):
        if self.selected and not self.open.disabled:
            key = self.model.value
            if models.get(key):  # (read it with that model, in every session)
                registry.choose(self.selected, key)
            if self.on_open is not None:
                self.on_open(self.selected)
            else:
                self.go.value = json.dumps([self.selected, key])

    def clear(self):
        """An empty box (after a pick), and the list of runs again."""
        self.query.value = self.query.value_input = ""
        self._refresh()
