"""Figure editor: the runs a figure could add (found in the background), what a run's storm track
gives, and the run lists of cards (RunLists: a card's host has them).

Mixins of the FigureEditor (figures/editor.py) and the shell's card host (shell/layerrow.py)."""

import os
import threading
from collections import OrderedDict

from .. import config, registry
from ..core import models
from ..core.fields import GROUP_ORDER, deriv_def, split_deriv
from ..viewer.ui import held


TYPE_PATH = "type a path"  # (the track list's "Type a path…": never a full path)


def _track_path(value):
    """A track box's text as a full path ("" when blank)."""
    value = (value or "").strip()
    return os.path.abspath(os.path.expanduser(os.path.expandvars(value))) if value else ""


def _track_options(found):
    """The track list's choices {label: value}: files by name, with their folder when
    two folders have the same name."""
    names = [os.path.basename(p) for p in found]
    labels = {(n if names.count(n) == 1 else
               os.path.join(os.path.basename(os.path.dirname(p)), n)
               + f" ({os.path.dirname(os.path.dirname(p))})"): p
              for n, p in zip(names, found)}
    return {"None": ""} | labels | {"Type a path…": TYPE_PATH}


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
        d = self.defs.get(name) if isinstance(name, str) else None
        if d is None:
            op, base = split_deriv(name)
            d = deriv_def(op, self.defs[base]) if op and base in self.defs else None
            if d is None:
                raise KeyError(name)
        return d

    def __contains__(self, name):
        try:
            self[name]
        except KeyError:
            return False
        return True

    def groups(self, ndim=None):
        out = OrderedDict((g, OrderedDict()) for g in GROUP_ORDER)
        for d in self.defs.values():
            if ndim is not None and d.ndim != ndim:
                continue
            some = " · not in every run" if d.name in self._some else ""
            out.setdefault(d.group, OrderedDict())[f"{d.label} [{d.name}]{some}"] = d.name
        return OrderedDict((g, v) for g, v in out.items() if v)


class FigureRuns:
    """The runs a figure could add, and storm tracks."""

    _scanned, _scan_complete, _scan_new, _cands, _cand_labels = [], True, False, [], {}

    def _scan_roots(self):
        """Look for the runs under the runs_root setting in the background (as the Open
        dialog does); the run lists offer them when it is done."""
        roots = list(config.get("runs_root") or [])
        if not roots:
            self._scanned = []
            self._find_runs()
            return
        self._find_runs()  # (next to this run, and recent, meanwhile)

        def job():
            runs, complete = config.scan_runs(roots)

            def done():
                self._scanned, self._scan_complete = runs, complete
                self._find_runs()

            if self.v.doc is not None:
                self.v._schedule(done)
            else:  # (picked up the next time the list is asked for)
                self._scanned, self._scan_complete, self._scan_new = runs, complete, True

        threading.Thread(target=job, daemon=True, name="cm1view-runscan").start()

    def _find_runs(self):
        """Runs the figure could add: under runs_root, next to this run, and recent."""
        out = []
        own = models.root_of(self.run.path)  # (a WoFS member's experiment: its members
        sibs = registry.sibling_runs(self.run.path)  # are listed one by one instead)
        for p in list(self._scanned) + sibs + registry.recent_runs():
            p = os.path.abspath(p)
            if p not in out and (p != own or own == self.run.path):
                out.append(p)
        self._cands = out
        # (members by name: "<experiment> · Member 5")
        m = models.MODELS.get(self.run.model)
        self._cand_labels = {} if own == self.run.path or m is None else {
            p: f"{os.path.basename(own)} · {m.part_label(p)}" for p in sibs}

    def _other_runs(self, have):
        """{label: path} of the runs not in the figure (have: the paths of the runs in it)."""
        if self._scan_new:
            self._scan_new = False
            self._find_runs()
        roots = [config.expand(r).rstrip("/") + "/" for r in config.get("runs_root") or []]
        out = {}
        for p in self._cands:
            if p in have:
                continue
            lab = self._cand_labels.get(p) or \
                next((p[len(r):] for r in roots if p.startswith(r)), None) or \
                "/".join(p.rstrip("/").split("/")[-2:])
            out[lab if lab not in out else p] = p
        return out

    def _track_words(self, e, run=None):
        """What a run entry's storm track gives (HTML): its fixes and times, or why none."""
        if run is None:
            try:
                run, _ = self.open_run(e["path"])
            except Exception as ex:  # noqa: BLE001
                return f'<span style="color:#f87171">{ex}</span>'
        fx = self.run_fixes(e, run)
        tr = e.get("track") or ""
        path = _track_path(tr) if tr != "viewer" else ""
        if path in self.data.track_err:
            return f'<span style="color:#f87171">track: {self.data.track_err[path]}</span>'
        if not tr:
            return "no track (storm-centred panels stay empty)"
        what = f"storm {e['storm']}, " if e.get("storm") and tr != "viewer" else ""
        note = f"track: {what}{len(fx)} fix{'es' if len(fx) != 1 else ''}"
        if fx:
            ts = sorted(fx)
            note += f" ({run.times[ts[0]] / 60:g}–{run.times[ts[-1]] / 60:g} min)"
        return note


class RunLists:
    """A card's run lists; its host has _run_names, _other_runs and _add_run."""

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

    def _layer_run_choices(self, names=None):
        """A layer's run choices: "the panel's run" (-1), then _run_choices."""
        names = names or self._run_names()
        ch = self._run_choices(names)
        first = {"the panel's run": -1}
        if ch["groups"]:
            return dict(options={}, groups={"": first} | ch["groups"])
        return dict(groups=None, options=first | names)

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
        with held(self):
            if k is None:  # (the message says why)
                w.value = old if isinstance(old, int) else 0
                return
        w.value = k  # (as if picked from the list: the panel's times follow)
