"""Figure editor: the runs panels can come from (adding, labelling, removing them,
and their storm tracks).

A mixin of the FigureEditor (cm1view/figui.py)."""

import os

import panel as pn

from . import figure as fg, registry, track as trk
from .fields import Fields
from .run import CM1Run
from .figparts import CARD, _row


class FigureRuns:
    # ------------------------------------------------------------ runs
    def open_run(self, path):
        """(CM1Run, Fields) of the run in `path` (the viewer's own run, or one opened
        through the viewer's registry so its cache is shared)."""
        path = os.path.abspath(path)
        if path == self.run.path:
            return self.run, self.F
        reg = getattr(self.v, "reg", None)
        if reg is not None:
            return reg.get(path)
        if path not in self._opened:
            r = CM1Run(path, workers=self.run.workers, cache=self.run._vc)
            self._opened[path] = (r, Fields(r))
        return self._opened[path]

    def run_fixes(self, entry, run):
        """Track fixes {t: fix} of a spec["runs"] entry ({} without a track)."""
        tr = entry.get("track") or ""
        if tr == "viewer":
            return dict(self.v.fixes) if run is self.run else {}
        if not tr:
            return {}
        path = os.path.abspath(os.path.expanduser(os.path.expandvars(tr)))
        try:
            mt = os.path.getmtime(path)
            hit = self._tracks.get(path)
            if hit is None or hit[0] != mt or hit[1] != run.path:
                self._tracks[path] = (mt, run.path, trk.load(run, path))
            self._track_err.pop(path, None)
            return self._tracks[path][2]
        except Exception as e:  # noqa: BLE001
            self._track_err[path] = str(e)
            return {}

    def _build_runs(self, runs):
        self.run_rows = [self._run_row(e) for e in runs]
        self._show_runs()

    def _run_row(self, e):
        own = os.path.abspath(e["path"]) == self.run.path
        r = dict(path=os.path.abspath(e["path"]))
        r["label"] = pn.widgets.TextInput(name="Label", value=e.get("label", ""), width=130)
        r["tab"] = pn.widgets.Checkbox(name="Viewer's track", value=e.get("track") == "viewer",
                                       visible=own, margin=(5, 6, 12, 6))
        r["track"] = pn.widgets.TextInput(
            name="Track file (blank: none)", sizing_mode="stretch_width", min_width=200,
            value="" if e.get("track") == "viewer" else e.get("track", ""),
            disabled=e.get("track") == "viewer", placeholder="storm_tracks/<run>.csv")
        r["rm"] = pn.widgets.Button(name="✕", description="Remove the run", width=32, height=28,
                                    margin=(2, 1), button_type="default", button_style="outline")
        r["info"] = pn.pane.HTML(margin=(0, 4))
        r["head"] = pn.pane.HTML(margin=(6, 4, 0, 4))

        def on_label(ev):
            self._refresh_run_names()
            self.request()

        def on_track(ev):
            r["track"].disabled = r["tab"].value
            self._run_info(r)
            self.request()

        r["label"].param.watch(on_label, "value")
        r["tab"].param.watch(on_track, "value")
        r["track"].param.watch(on_track, "value")
        r["rm"].on_click(lambda ev: self._remove_run(r))
        r["panel"] = pn.Column(
            pn.Row(r["head"], pn.Spacer(), r["rm"], margin=0, sizing_mode="stretch_width"),
            _row(r["label"], r["tab"], r["track"]), r["info"], styles=CARD,
            sizing_mode="stretch_width", margin=(2, 0))
        self._run_info(r)
        return r

    def _run_entry(self, r):
        tr = "viewer" if r["tab"].visible and r["tab"].value else r["track"].value.strip()
        return dict(path=r["path"], label=r["label"].value, track=tr)

    def _runs_collect(self):
        return [self._run_entry(r) for r in self.run_rows]

    def _run_info(self, r):
        k = self.run_rows.index(r) if r in self.run_rows else len(self.run_rows)
        own = " (this viewer's run)" if r["path"] == self.run.path else ""
        r["head"].object = (f'<b>{k + 1}.</b> <code>{r["path"]}</code>'
                            f'<span class="cv-hint">{own}</span>')
        try:
            run, _ = self.open_run(r["path"])
        except Exception as e:  # noqa: BLE001
            r["info"].object = f'<div class="cv-status" style="color:#f87171">{e}</div>'
            return
        e = self._run_entry(r)
        fx = self.run_fixes(e, run)
        tr = e["track"]
        path = os.path.abspath(os.path.expanduser(tr)) if tr and tr != "viewer" else ""
        if path in self._track_err:
            tnote = f'<span style="color:#f87171">track: {self._track_err[path]}</span>'
        elif tr:
            tnote = f"track: {len(fx)} fix{'es' if len(fx) != 1 else ''}"
            if fx:
                ts = sorted(fx)
                tnote += f" ({run.times[ts[0]] / 60:g}–{run.times[ts[-1]] / 60:g} min)"
        else:
            tnote = "no track (storm-centred panels stay empty)"
        r["info"].object = (
            f'<div class="cv-hint">{len(run.times)} outputs, {run.times[0] / 60:g}–'
            f'{run.times[-1] / 60:g} min · {run.ni}×{run.nj}×{run.nk}, dx {run.dx:g} m · '
            f'{tnote}</div>')

    def _show_runs(self):
        for r in self.run_rows:
            r["rm"].visible = len(self.run_rows) > 1
            self._run_info(r)
        self.runs_box.objects = [r["panel"] for r in self.run_rows]
        self._refresh_run_names()
        self._sync_save_path()
        have = {r["path"] for r in self.run_rows}
        opts = {}
        for p in registry.sibling_runs(self.run.path) + registry.recent_runs():
            p = os.path.abspath(p)
            if p not in have:
                opts.setdefault("/".join(p.rstrip("/").split("/")[-2:]), p)
        self.add_sel.options = {"": ""} | opts

    def _run_names(self):
        return {f"{k + 1}. {r['label'].value or os.path.basename(r['path'])}": k
                for k, r in enumerate(self.run_rows)}

    def _refresh_run_names(self):
        names = self._run_names()
        hold, self._hold = self._hold, True
        try:
            v = self.run_sel.value
            self.run_sel.options = names
            self.run_sel.value = v if v in names.values() else 0
            for r in self.pc_rows:
                v = r["run"].value
                r["run"].options = names
                r["run"].value = v if v in names.values() else 0
            for c in self.snd_cards:
                v = c.w["run"].value
                c.w["run"].options = names
                c.w["run"].value = v if v in names.values() else 0
            for c in self.ser_cards:
                v = [k for k in c.w["runs"].value if k in names.values()]
                c.w["runs"].options = names
                c.w["runs"].value = v
        finally:
            self._hold = hold
        self.run_sel.visible = len(names) > 1 and self.vary.value in ("time", "field")

    def _add_run(self):
        path = os.path.abspath(os.path.expanduser(self.add_path.value.strip()))
        if not registry.is_run(path):
            self._runs_msg(f"No cm1out_*.nc files in <code>{path}</code>", True)
            return
        if path in {r["path"] for r in self.run_rows}:
            self._runs_msg("That run is already in the list.", True)
            return
        self._runs_msg('<span class="busy">● Opening…</span>')
        try:
            run, _ = self.open_run(path)
        except Exception as e:  # noqa: BLE001
            self._runs_msg(f"Could not open <code>{path}</code>: {e}", True)
            return
        self.run_rows.append(self._run_row(fg.run_entry(run)))
        self._show_runs()
        self.add_path.value = ""
        self._runs_msg(f"Added <code>{path}</code>")
        if self.vary.value == "time":  # a second run: compare them side by side
            self.vary.value = "grid"
        else:
            self._on_vary()

    def _remove_run(self, r):
        k = self.run_rows.index(r)
        self.run_rows.remove(r)
        self._hold = True
        try:
            if self.run_sel.value is not None and self.run_sel.value >= k:
                self.run_sel.value = max(0, self.run_sel.value - (self.run_sel.value > k))
            keep = []
            for p in self.pc_rows:
                if p["run"].value != k:
                    if p["run"].value > k:
                        p["run"].value -= 1
                    keep.append(p)
            self.pc_rows = keep
        finally:
            self._hold = False
        self._show_runs()
        self._on_vary()

    def _runs_msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.runs_msg.object = f'<div class="cv-status"{col}>{html}</div>'
