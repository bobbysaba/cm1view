"""Figure editor: the runs panels can come from (adding, labelling, removing them,
and their storm tracks).

A mixin of the FigureEditor (cm1view/figui.py)."""

import os
import threading
from collections import OrderedDict

import panel as pn

from .. import config, registry
from . import draw as figdraw, spec as fg
from ..core import track as trk
from ..core.fields import GROUP_ORDER, Fields
from ..core.run import CM1Run
from .cards import CARD, _hex, _row

RUN_LINES = {"solid": "-", "dashed": "--", "dotted": ":", "dash-dot": "-."}


class AllFields:
    """The fields of every run of a figure (the viewer's run's first), for the field
    lists: a field only some runs have is listed too, marked as such (its panels in the
    other runs say they have no such field)."""

    def __init__(self, fields):
        self.defs, self._some = OrderedDict(), set()
        for F in fields:
            for name, d in F.defs.items():
                self.defs.setdefault(name, d)
        for name in self.defs:
            if any(name not in F for F in fields):
                self._some.add(name)

    def __getitem__(self, name):
        return self.defs[name]

    def __contains__(self, name):
        return name in self.defs

    def groups(self, ndim=None):
        out = OrderedDict((g, OrderedDict()) for g in GROUP_ORDER)
        for d in self.defs.values():
            if ndim is not None and d.ndim != ndim:
                continue
            some = " · not in every run" if d.name in self._some else ""
            out.setdefault(d.group, OrderedDict())[f"{d.label} [{d.name}]{some}"] = d.name
        return OrderedDict((g, v) for g, v in out.items() if v)


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
        self.run_rows = [self._run_row(e, k) for k, e in enumerate(runs)]
        self._show_runs()

    def _run_row(self, e, k=0):
        own = os.path.abspath(e["path"]) == self.run.path
        r = dict(path=os.path.abspath(e["path"]))
        r["label"] = pn.widgets.TextInput(name="Label", value=e.get("label", ""), width=130)
        r["tab"] = pn.widgets.Checkbox(name="Viewer's track", value=e.get("track") == "viewer",
                                       visible=own, margin=(5, 6, 12, 6))
        r["track"] = pn.widgets.TextInput(
            name="Track file (blank: none)", sizing_mode="stretch_width", min_width=200,
            value="" if e.get("track") == "viewer" else e.get("track", ""),
            disabled=e.get("track") == "viewer", placeholder="storm_tracks/<run>.csv")
        r["color"] = pn.widgets.ColorPicker(
            name="Colour", width=70, value=_hex(e.get("color") or
                                                 figdraw.RUN_COLORS[k % len(figdraw.RUN_COLORS)]))
        r["ls"] = pn.widgets.Select(name="Line", width=90, options=RUN_LINES, value=e.get(
            "ls") or figdraw.RUN_STYLES[k % len(figdraw.RUN_STYLES)])
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
        for w in (r["color"], r["ls"]):
            w.param.watch(lambda ev: self.request(), "value")
        r["rm"].on_click(lambda ev: self._remove_run(r))
        r["panel"] = pn.Column(
            pn.Row(r["head"], pn.Spacer(), r["rm"], margin=0, sizing_mode="stretch_width"),
            _row(r["label"], r["color"], r["ls"], r["tab"], r["track"]), r["info"], styles=CARD,
            sizing_mode="stretch_width", margin=(2, 0))
        self._run_info(r)
        return r

    def _run_entry(self, r):
        tr = "viewer" if r["tab"].visible and r["tab"].value else r["track"].value.strip()
        return dict(path=r["path"], label=r["label"].value, track=tr, color=r["color"].value,
                    ls=r["ls"].value)

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
        path = os.path.abspath(os.path.expanduser(os.path.expandvars(tr))) \
            if tr and tr != "viewer" else ""
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
        self._find_runs()
        self._refresh_run_names()
        self._refresh_fields()
        self._sync_save_path()
        if self._scan_new:  # (a scan that finished without a page to tell)
            self._scan_new = False
            self.add_pick.set_known(self._scanned, self._scan_complete)
        else:
            self.add_pick._refresh()  # (without the runs added now)

    # ------------------------------------------------------------ runs to add
    _scanned, _scan_complete, _scan_new, _cands = [], True, False, []

    def _scan_roots(self):
        """Look for the runs under the runs_root setting in the background (as the Open
        dialog does); the run lists offer them when it is done."""
        roots = list(config.get("runs_root") or [])
        if not roots:
            self._scanned = []
            return

        def job():
            runs, complete = config.scan_runs(roots)

            def done():
                self._scanned, self._scan_complete = runs, complete
                self._find_runs()
                self.add_pick.set_known(runs, complete)
                self._refresh_run_names()

            if self.v.doc is not None:
                self.v._schedule(done)
            else:  # (picked up by the next change of the runs)
                self._scanned, self._scan_complete, self._scan_new = runs, complete, True

        threading.Thread(target=job, daemon=True, name="cm1view-runscan").start()

    def _find_runs(self):
        """Runs the figure could add: under runs_root, next to this run, and recent."""
        out = []
        for p in (list(self._scanned) + registry.sibling_runs(self.run.path)
                  + registry.recent_runs()):
            p = os.path.abspath(p)
            if p not in out:
                out.append(p)
        self._cands = out

    def _other_runs(self):
        """{label: path} of the runs not in the figure (for the run lists)."""
        have = {r["path"] for r in self.run_rows}
        roots = [config.expand(r).rstrip("/") + "/" for r in config.get("runs_root") or []]
        out = {}
        for p in self._cands:
            if p in have:
                continue
            lab = next((p[len(r):] for r in roots if p.startswith(r)), None) or \
                "/".join(p.rstrip("/").split("/")[-2:])
            out[lab if lab not in out else p] = p
        return out

    def _run_choices(self, names=None):
        """A run list's choices (Select keywords): the figure's runs, then under a
        heading of their own the other runs (picking one adds it); just the figure's
        runs, without headings, when there are no others."""
        names = names or self._run_names()
        others = self._other_runs()
        if not others:
            return dict(groups=None, options=names)
        return dict(options={}, groups={"In this figure": names,
                                        "Other runs (adds it)": others})

    def _set_runs_of(self, w, value):
        """A run list's choices, keeping its run (else the first)."""
        names = self._run_names()
        w.param.update(**self._run_choices(names))
        w.value = value if value in names.values() else 0

    def _series_run_opts(self, names=None):
        """Options of a series' Runs list (no groups in a multi-choice): the figure's
        runs, then the others, marked (picking one adds it to the figure)."""
        names = dict(names or self._run_names())
        for lab, p in self._other_runs().items():
            names[f"+ {lab} (adds it)"] = p
        return names

    def _pick_other(self, w, old):
        """A run list picked a run not in the figure: add it, and pick it."""
        k = self._add_run(w.value, grid=False)
        hold, self._hold = self._hold, True
        try:
            if k is None:  # (the message says why)
                w.value = old if isinstance(old, int) else 0
                return
        finally:
            self._hold = hold
        w.value = k  # (as if picked from the list: the panel's times follow)

    def _run_names(self):
        return {f"{k + 1}. {r['label'].value or os.path.basename(r['path'])}": k
                for k, r in enumerate(self.run_rows)}

    def _refresh_run_names(self):
        names = self._run_names()
        hold, self._hold = self._hold, True
        try:
            for w in [self.run_sel] + [r["run"] for r in self.pc_rows] + \
                    [c.w["run"] for c in self.snd_cards + self.dist_cards]:
                self._set_runs_of(w, w.value)
            opts = self._series_run_opts(names)
            for c in self.ser_cards:
                v = [k for k in c.w["runs"].value if k in names.values()]
                c.w["runs"].options = opts
                c.w["runs"].value = v
            for c in self.cards:  # (a difference's Minus run)
                if "minus_run" in c.w:
                    v = c.w["minus_run"].value
                    c.w["minus_run"].options = {"the layer's": -1} | names
                    c.w["minus_run"].value = v if v in names.values() else -1
        finally:
            self._hold = hold
        self.run_sel.visible = (len(names) > 1 or bool(self._other_runs())) and \
            self.vary.value in ("time", "field") and self.kind.value in ("plan", "xsec")

    def _refresh_fields(self):
        """The field lists offer the fields of every run of the figure."""
        fields = [self.F]
        for r in self.run_rows:
            try:
                fields.append(self.open_run(r["path"])[1])
            except Exception:  # noqa: BLE001  (its card says why)
                pass
        self.fields = AllFields(fields)
        g = self.fields.groups()
        hold, self._hold = self._hold, True
        try:
            for w in ([c.w["field"] for c in self.cards if "field" in c.w]
                      + [r["field"] for r in self.pf_rows]
                      + [c.w["field"] for c in self.ser_cards]):
                v = w.value
                w.groups = g
                w.value = v
        finally:
            self._hold = hold

    def _add_run(self, path=None, grid=True):
        """Add the run in `path` (default: the box) with its storm track (a
        storm_tracks file found for it).  grid: a second run turns panels in time into
        a run x time grid.  Returns its index, or None."""
        path = config.expand((path or self.add_path.value).strip())
        if not registry.is_run(path):
            self._runs_msg(f"No cm1out_*.nc files in <code>{path}</code>", True)
            return None
        if path in {r["path"] for r in self.run_rows}:
            self._runs_msg("That run is already in the list.", True)
            return None
        self._runs_msg('<span class="busy">● Opening…</span>')
        try:
            run, _ = self.open_run(path)
        except Exception as e:  # noqa: BLE001
            self._runs_msg(f"Could not open <code>{path}</code>: {e}", True)
            return None
        self.run_rows.append(self._run_row(fg.run_entry(run), len(self.run_rows)))
        self._show_runs()
        self.add_pick.clear()
        self._runs_msg(f"Added <code>{path}</code>")
        if not grid:
            pass
        elif self.vary.value == "time":  # a second run: compare them side by side
            self.vary.value = "grid"
        else:
            self._on_vary()
        return len(self.run_rows) - 1

    def _remove_run(self, r):
        """Remove run k: panels, soundings, distributions and series of it go, and those
        of the runs after it follow their run to its new number."""
        k = self.run_rows.index(r)
        self.run_rows.remove(r)
        names = self._run_names()  # (the new numbering)
        gone = []
        self._hold = True
        try:
            if self.run_sel.value is not None and self.run_sel.value >= k:
                self.run_sel.value = max(0, self.run_sel.value - (self.run_sel.value > k))
            keep = []
            for p in self.pc_rows:
                if p["run"].value != k:
                    if p["run"].value > k:  # (the lists follow in _show_runs)
                        p["run"].value -= 1
                    keep.append(p)
            self.pc_rows = keep
            for what in ("sounding", "distribution"):
                keep = []
                cards = self.snd_cards if what == "sounding" else self.dist_cards
                for c in cards:
                    j = int(c.w["run"].value or 0)
                    if j == k:
                        gone.append(what)
                        continue
                    if j > k:
                        c.w["run"].value = j - 1
                    keep.append(c)
                cards[:] = keep
            keep = []
            for c in self.ser_cards:
                old = [int(j) for j in c.w["runs"].value]
                new = [j - (j > k) for j in old if j != k]
                if old and not new:  # it was of that run only
                    gone.append("series")
                    continue
                c.w["runs"].value = new
                c.w["runs"].options = self._series_run_opts(names)
                keep.append(c)
            self.ser_cards = keep
        finally:
            self._hold = False
        self._show_runs()
        self._show_soundings()
        self._show_dists()
        self._show_series()
        if gone:
            n = {w: gone.count(w) for w in dict.fromkeys(gone)}
            self._runs_msg("Removed the run and its " + " and ".join(
                f"{c} {w}{'s' if c > 1 and w != 'series' else ''}" for w, c in n.items()) + ".")
        self._on_vary()

    def _runs_msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.runs_msg.object = f'<div class="cv-status"{col}>{html}</div>'
