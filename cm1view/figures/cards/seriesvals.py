"""The Values section of a time-series card: its computed values, one run at a time,
with your hand edits (a value of your own, or the point blanked), kept on the card's
entry (entry["edits"], see spec/panels.apply_edits) and drawn by the preview without
computing anything again."""

import io
import math

import numpy as np
import pandas as pd
import panel as pn

from .. import spec as fg
from .base import SECTION, _grid, _hint

BLANK = "blank"  # (the Yours column of a blanked point)
_BLANKS = ("blank", "nan", "none", "-", "–", "x")


def _fmt(x):
    return "" if x is None or not math.isfinite(x) else f"{x:.6g}"


def parse_yours(text):
    """A Yours cell: (True, None) blank the point, (True, value) your value, (False,
    None) no edit (empty), or None when it is not a number."""
    s = str(text if text is not None else "").strip()
    if not s:
        return False, None
    if s.lower() in _BLANKS:
        return True, None
    try:
        v = float(s)
    except ValueError:
        return None
    return (True, v) if math.isfinite(v) else (True, None)


class SeriesValues:
    """A collapsed section of a SeriesCard; its widgets are made the first time it is
    opened (most cards are never edited)."""

    def __init__(self, card):
        self.card, self.ed = card, card.ed
        self.section = pn.Card(title="Values (edit points)", collapsed=True, **SECTION)
        self.section.param.watch(self._opened, "collapsed")
        self.w = None
        self.times = np.array([])  # (model times, s, of the rows shown)
        self.k = None  # (the run shown)

    # ---- edits on the entry
    def edits(self, k=None):
        """The card's edits of run k (all runs: k None) {str(run): {key: value or None}}."""
        eds = self.card.ent.setdefault("edits", {})
        return eds if k is None else eds.setdefault(str(k), {})

    def count(self):
        return sum(len(v) for v in (self.card.ent.get("edits") or {}).values())

    def _store(self, k, key, val=None, drop=False):
        eds = self.edits(k)
        if drop:
            eds.pop(key, None)
        else:
            eds[key] = val
        self._tidy()

    def _tidy(self):
        e = self.card.ent
        e["edits"] = {k: v for k, v in (e.get("edits") or {}).items() if v}
        if not e["edits"]:
            e.pop("edits")

    # ---- widgets
    def _opened(self, ev):
        if ev.new or self.w is not None:
            return
        w = self.w = {}
        w["run"] = pn.widgets.Select(name="Run", width=200)
        w["refresh"] = pn.widgets.Button(name="Refresh", height=32, button_type="light",
                                         button_style="outline",
                                         description="The values again (e.g. more times "
                                                     "computed since)")
        w["blank"] = pn.widgets.Button(name="Blank points", height=32, button_type="light",
                                       button_style="outline",
                                       description="Leave the rows picked out of the line")
        w["reset"] = pn.widgets.Button(name="Reset points", height=32, button_type="light",
                                       button_style="outline",
                                       description="The rows picked back to their computed "
                                                   "values")
        w["reset_all"] = pn.widgets.Button(name="Reset all edits", height=32,
                                           button_type="warning", button_style="outline",
                                           description="Every edit of this card, every run")
        w["dl"] = pn.widgets.FileDownload(callback=self._csv, filename="series.csv",
                                          label="Download CSV", button_type="primary",
                                          button_style="outline", height=32)
        w["table"] = pn.widgets.Tabulator(
            pd.DataFrame(dict(t=[], model_s=[], computed=[], yours=[])), show_index=False,
            selectable="checkbox", theme="midnight", height=300, layout="fit_data_fill",
            sizing_mode="stretch_width", editors={"t": None, "model_s": None,
                                                  "computed": None, "yours": "input"},
            titles={"t": "Time (min)", "model_s": "Model time (s)", "computed": "Computed",
                    "yours": "Yours"})
        w["note"] = pn.pane.HTML(margin=(0, 4), sizing_mode="stretch_width")
        w["drop_gone"] = pn.widgets.Button(name="Drop those", height=28, button_type="light",
                                           button_style="outline", visible=False,
                                           description="Forget the edits at times this run "
                                                       "does not have")
        w["run"].param.watch(lambda e: self.refresh(), "value")
        w["refresh"].on_click(lambda e: self.refresh())
        w["blank"].on_click(lambda e: self._picked(blank=True))
        w["reset"].on_click(lambda e: self._picked(blank=False))
        w["reset_all"].on_click(lambda e: self._reset_all())
        w["drop_gone"].on_click(lambda e: self._drop_gone())
        w["table"].on_edit(self._on_edit)
        self.section.objects = [
            _grid(w["run"], w["refresh"], w["dl"], w["blank"], w["reset"], w["reset_all"]),
            _hint("Type a value in Yours to replace a point, <i>blank</i> to leave it out, "
                  "or clear the cell to undo.  Edits are on the plotted values (after "
                  "d/dt) and stay with the card when the time zero changes."),
            w["table"], pn.Row(w["note"], w["drop_gone"], margin=0,
                               sizing_mode="stretch_width")]
        self.refresh()

    def _run_opts(self):
        names = self.ed._run_names()  # {name: index}
        ks = self.card.run_list()
        return {n: k for n, k in names.items() if ks is None or k in ks}

    def refresh(self):
        """The rows again: the card's values of the run picked, with its edits."""
        if self.w is None or self.section.collapsed:
            return
        w = self.w
        opts = self._run_opts()
        if w["run"].options != opts:
            hold, self.ed._hold = self.ed._hold, True
            try:
                keep = w["run"].value
                w["run"].param.update(options=opts,
                                      value=keep if keep in opts.values()
                                      else next(iter(opts.values()), None))
            finally:
                self.ed._hold = hold
        w["run"].visible = len(opts) > 1
        self.k = k = w["run"].value
        ent = self.card.collect()
        w["dl"].filename = f"{(ent.get('label') or 'series').strip() or 'series'}.csv" \
            .replace("/", "_").replace(" ", "_")
        if k is None:
            return self._show([], [], [], "no run")
        spec = {"runs": self.ed._runs_collect(), "series": [ent]}
        got = self.ed._series_get(spec, k, 0)
        if isinstance(got, str):
            return self._show([], [], [], got)
        run, ds = got
        t0 = fg.series_t0({"time_label": {"t0_min": self._fig_t0()}}, ent)
        t, v, _, _ = fg.series_arrays(run, ds, ent, t0)
        why = ""
        if v is None:
            v, why = np.full(len(run.times), np.nan), "d/dz applies to time–height panels"
        elif not np.isfinite(v).any():
            why = "not computed yet (Refresh once it is)"
        self._show(np.asarray(run.times, dtype=np.float64), t, v, why)

    def _fig_t0(self):
        tl = getattr(self.ed, "tl_t0", None)  # (Style: built when first opened)
        if tl is not None:
            return float(tl.value or 0.0)
        return float(self.ed.spec.get("time_label", {}).get("t0_min", 0.0))

    def _show(self, times_s, t, v, why):
        w, k = self.w, self.k
        self.times = np.asarray(times_s, dtype=np.float64)
        yours = [""] * len(self.times)
        eds = (self.card.ent.get("edits") or {}).get(str(k)) or {}
        gone = 0
        for key, val in eds.items():
            j = np.flatnonzero(np.abs(self.times - float(key)) < 0.5)
            if not j.size:
                gone += 1
                continue
            yours[j[0]] = BLANK if val is None else _fmt(val)
        w["table"].value = pd.DataFrame(dict(
            t=[round(float(x), 4) for x in t], model_s=[float(x) for x in self.times],
            computed=[_fmt(float(x)) for x in v], yours=yours))
        w["table"].selection = []
        msg = [why] if why else []
        n = len(eds) - gone
        if n:
            msg.append(f"{n} point{'s' if n != 1 else ''} edited")
        if gone:
            msg.append(f"{gone} edit{'s' if gone != 1 else ''} at times this run does not "
                       f"have (not drawn)")
        w["note"].object = f'<div class="cv-hint">{" · ".join(msg)}</div>' if msg else ""
        w["drop_gone"].visible = bool(gone)

    # ---- editing
    def _on_edit(self, ev):
        if ev.column != "yours" or self.k is None or not 0 <= ev.row < self.times.size:
            return
        key = fg.edit_key(self.times[ev.row])
        p = parse_yours(ev.value)
        old = self._old_key(key)
        if old is not None and old != key:  # (an edit stored for the same time)
            self._store(self.k, old, drop=True)
        if p is None:
            self.w["note"].object = (f'<div class="cv-hint">“{ev.value}” is not a number '
                                     f'(type a value, blank, or clear the cell)</div>')
            self.refresh()
            return
        edit, val = p
        self._store(self.k, key, val, drop=not edit)
        self.done()

    def _old_key(self, key):
        """The stored key of the edit at the time of key, if any (keys may come from
        another rounding)."""
        for x in (self.card.ent.get("edits") or {}).get(str(self.k)) or {}:
            if abs(float(x) - float(key)) < 0.5:
                return x
        return None

    def _picked(self, blank):
        rows = [j for j in self.w["table"].selection if 0 <= j < self.times.size]
        if not rows or self.k is None:
            return
        for j in rows:
            key = fg.edit_key(self.times[j])
            old = self._old_key(key)
            if old is not None:
                self._store(self.k, old, drop=True)
            if blank:
                self._store(self.k, key, None)
        self.done()

    def _reset_all(self):
        self.card.ent.pop("edits", None)
        self.done()

    def _drop_gone(self):
        eds = self.edits(self.k)
        for key in [x for x in eds if not (np.abs(self.times - float(x)) < 0.5).any()]:
            eds.pop(key)
        self._tidy()
        self.done()

    def done(self):
        """Edits changed: the rows, the card's note and the preview (the values are
        the computed ones already: nothing to compute)."""
        self.card.edits_changed()
        self.refresh()
        self.ed.request()

    # ---- download
    def _csv(self):
        """The run's line as drawn: time (min), model time (s), computed, plotted."""
        df = self.w["table"].value
        out = io.StringIO()
        out.write("time_min,model_time_s,computed,plotted\n")
        for t, s, c, y in zip(df["t"], df["model_s"], df["computed"], df["yours"]):
            p = c if y == "" else "" if y == BLANK else y
            out.write(f"{t:g},{s:g},{c},{p}\n")
        out.seek(0)
        return out
