"""“Apply to other runs” in the Export dialog: the figure the shell holds, drawn for each run the
user picks as a template of it would be (batch.on_run; the same as `cm1view render --run`) and
saved in that run's figures folder (or the folder pattern given).  One run per job on the
figure pool, the next queued when it ends, so the preview gets its turn between runs; Stop
ends after the run being drawn.  A run that fails is reported with the others; files already
there are asked about first (the viewer's ConfirmOverwrite)."""

import html
import json
import os
import traceback
from functools import partial

import panel as pn

from ... import config
from .. import batch
from ..cards import _grid, _hint
from ..cards.base import SECTION

MAX_RUNS = 200  # (runs offered in the list)


def run_label(path):
    parent = os.path.basename(os.path.dirname(path.rstrip("/")))
    return f"{parent}/{os.path.basename(path.rstrip('/'))}"


def plan(runs, name, pattern, fmt):
    """[(run path, base)] for `runs`: <the run's figures folder>/<name>, or `pattern` (path and name; may
    hold {run}, {parent} and {name}, as `render --out` does).  ValueError when two runs would
    save to the same files."""
    out = []
    for rp in runs:
        if pattern.strip():
            base, _ = batch.image_base(batch._out_pattern(pattern.strip(), rp, name), fmt)
        else:
            base = os.path.join(config.figures_dir(rp), name)
        out.append((rp, base))
    if len({b for _, b in out}) < len(out):
        raise ValueError("two runs would save to the same file: put {run} in the folder")
    return out


def run_paths(listed, typed):
    """The picked runs and the typed ones (one per line), as absolute paths without repeats; the
    folders that don't exist come second, as errors."""
    seen, ok, bad = set(), [], []
    for p in list(listed) + [ln.strip() for ln in (typed or "").splitlines()]:
        if not p:
            continue
        p = os.path.abspath(config.expand(p))
        if p in seen:
            continue
        seen.add(p)
        (ok if os.path.isdir(p) else bad).append(p)
    return ok, bad


class ApplyRuns:
    def __init__(self, shell):
        self.shell, self.ed = shell, shell.ed
        self.gen, self.fd = 0, None
        self.pick = pn.widgets.MultiSelect(name="Runs", options={}, size=8,
                                           sizing_mode="stretch_width",
                                           description="Runs found under the Runs-root setting, "
                                                       "next to this one and recently opened")
        self.typed = pn.widgets.TextAreaInput(name="Other run folders (one per line)", height=70,
                                              sizing_mode="stretch_width")
        self.name = pn.widgets.TextInput(name="Name", value="figure", sizing_mode="stretch_width")
        self.folder = pn.widgets.TextInput(
            name="Save as (optional)", sizing_mode="stretch_width",
            placeholder="blank: each run's figures folder; or e.g. ~/figs/{run}/{name}")
        self.time = pn.widgets.FloatInput(name="First panel's time (min)", value=None, width=170,
                                          placeholder="blank: as now")
        self.more = pn.widgets.Checkbox(name="Also the script and data", value=False)
        self.go = pn.widgets.Button(name="Save for these runs", icon="copy",
                                    button_type="primary", height=32)
        self.stop = pn.widgets.Button(name="Stop", button_type="light", button_style="outline",
                                      height=32, disabled=True)
        self.said = pn.pane.HTML(margin=(0, 8), sizing_mode="stretch_width")
        self.go.on_click(lambda e: self.start())
        self.stop.on_click(lambda e: self.cancel())
        self.card = pn.Card(
            _hint("The figure drawn for other runs as a template of it would be (Template, below; "
                  "<code>cm1view render --run</code> does the same): its layout and look, its "
                  "times moved so the first panel is at the time given (else where it is now), "
                  "what only another run had left out. Each is saved as an image and the "
                  "settings to reopen it. Files already there are asked about; a run that fails "
                  "doesn't stop the others. It runs in the background: Stop ends it after the "
                  "run being drawn."),
            self.pick, self.typed, _grid((self.name, 2), self.time), self.folder, self.more,
            pn.Row(self.go, self.stop, margin=0), self.said,
            title="Apply to other runs", collapsed=True, **SECTION)

    # ------------------------------------------------------------ opening it
    def refresh(self):
        """The runs on offer (the figure editor's candidates), keeping the picks."""
        have = list(self.pick.value)
        cands = list(getattr(self.ed, "_cands", []))[:MAX_RUNS]
        self.pick.options = {run_label(p): p for p in cands}
        self.pick.value = [p for p in have if p in cands]
        cur = os.path.basename(config.expand(self.ed.path.value.strip()))
        if cur and self.name.value in ("", "figure"):
            self.name.value = cur

    # ------------------------------------------------------------ doing it
    def _say(self, text, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.said.object = f'<div class="cv-hint"{col}>{text}</div>'
        self.shell.say(text, err)

    def start(self):
        ed = self.ed
        runs, bad = run_paths(self.pick.value, self.typed.value)
        if bad:
            self._say("No such run folder: " + ", ".join(f"<code>{html.escape(b)}</code>"
                                                         for b in bad), True)
            return
        if not runs:
            self._say("Pick at least one run.", True)
            return
        doc = json.loads(json.dumps(self.shell.doc, default=float))
        name = "".join(c if c.isalnum() or c in "-_ ." else "_"
                       for c in self.name.value.strip()).strip(" .") or "figure"
        fmt = (doc.get("export") or {}).get("format", "png")
        try:
            jobs = plan(runs, name, self.folder.value, fmt)
        except ValueError as e:
            self._say(html.escape(str(e)), True)
            return
        paths = [p for rp, base in jobs for p in batch.run_outputs(doc, base, fmt, self.more.value)]
        time_s = None if self.time.value is None else float(self.time.value) * 60.0
        bundle = bool(self.more.value)
        self.shell.export.dlg.hide()  # ("replace?" is a dialog too)

        def go():
            self.gen += 1
            self.go.disabled, self.stop.disabled = True, False
            self._say(f'<span class="busy">● Run 1/{len(jobs)}…</span>')
            ed.v.pools["fig"].submit(self._step, self.gen, doc, name, jobs, 0, fmt, bundle,
                                     time_s, [])
        ed.v.confirm.ask(paths, go)

    def cancel(self):
        self.gen += 1
        self.stop.disabled = True

    def _step(self, g, doc, name, jobs, i, fmt, bundle, time_s, results):
        """Draw and save the figure for run i (a job of the figure pool), then queue the next."""
        sch = self.ed.v._schedule
        if g != self.gen:
            sch(partial(self._finish, results, len(jobs), True))
            return
        rp, base = jobs[i]
        try:
            if self.fd is None:
                from ..render import FigureData
                self.fd = FigureData(reg=getattr(self.ed.v, "reg", None),
                                     cache_gb=config.cache_gb()[0], workers=config.workers()[0])
            out, notes = batch.save_on_run(self.fd, doc, name, rp, base, fmt, bundle, time_s,
                                           cancelled=lambda: g != self.gen)
            results.append((rp, out, notes, None))
        except InterruptedError:
            sch(partial(self._finish, results, len(jobs), True))
            return
        except Exception as e:  # noqa: BLE001  (the other runs still get theirs)
            traceback.print_exc()
            results.append((rp, [], [], str(e) or type(e).__name__))
        if i + 1 < len(jobs):
            sch(partial(self._say, f'<span class="busy">● Run {i + 2}/{len(jobs)}…</span>'))
            self.ed.v.pools["fig"].submit(self._step, g, doc, name, jobs, i + 1, fmt, bundle,
                                          time_s, results)
        else:
            sch(partial(self._finish, results, len(jobs), False))

    def _finish(self, results, n, stopped):
        self.go.disabled, self.stop.disabled = False, True
        bad = [r for r in results if r[3]]
        lines = [f"<li>{html.escape(run_label(rp))}: " + (
            f"<b>failed</b>, {html.escape(err)}" if err else
            ", ".join(f"<code>{html.escape(p)}</code>" for p in out[:1])
            + "".join(f"; note: {html.escape(x)}" for x in notes)) + "</li>"
            for rp, out, notes, err in results]
        head = (f"Stopped after {len(results)} of {n} runs. " if stopped else "") + \
            f"{len(results) - len(bad)} saved" + (f", {len(bad)} failed" if bad else "") + "."
        self._say(head + f"<ul style='margin:4px 0'>{''.join(lines)}</ul>", bool(bad))
        self.ed._refresh_saved()
