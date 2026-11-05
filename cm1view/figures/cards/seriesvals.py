"""The Values section of a time-series card (and of a profile card: ProfileValues):
its computed values, one run at a time, with your hand edits (a value of your own,
or the point blanked) and rows of your own (a point the run does not have), kept on the
card's entry (entry["edits"], entry["added"], see spec/panels.apply_edits, apply_added)
and drawn by the preview without computing anything again."""

import io
import math

import numpy as np
import pandas as pd
import panel as pn

from .. import spec as fg
from .base import SECTION, _grid, _hint
from ...viewer.ui import held

BLANK = "blank"  # (the Yours column of a blanked point)
_BLANKS = ("blank", "nan", "none", "-", "–", "x")
# (text in these columns, not numbers: an empty frame's would format a blank Yours as 0.0)
AS_TEXT = dict(formatters={"computed": "plaintext", "yours": "plaintext"},
               text_align={"computed": "right", "yours": "right"})


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

    TOL = fg.EDIT_TOL  # (an edit is at a row's key within this)
    NAME = "series"  # (the CSV file's name when the card has no label)
    HINT = ("Type a value in Yours to replace a point, <i>blank</i> to leave it out, or "
            "clear the cell to undo.  <b>Add row</b> puts in a point at a time of your own "
            "(clear its Yours to take it out).  Edits are on the plotted values (after d/dt) "
            "and stay with the card when the time zero changes.")
    GONE = "at times this run does not have"
    AT = "New row: time (min)"

    def __init__(self, card):
        self.card, self.ed = card, card.ed
        self.section = pn.Card(title="Values (edit points)", collapsed=True, **SECTION)
        self.section.param.watch(self._opened, "collapsed")
        self.w = None
        self.keys = np.array([])  # (where each row is: model time, s)
        self.base = np.array([])  # (where each row of the run's own is)
        self.lead = {}  # (those rows' leading columns)
        self.k = None  # (the run shown)

    # ---- what differs between a series and a profile
    def _table(self):
        return pn.widgets.Tabulator(
            pd.DataFrame(dict(t=[], model_s=[], computed=[], yours=[])), show_index=False,
            selectable="checkbox", theme="midnight", height=300, layout="fit_columns",
            sizing_mode="stretch_width", editors={"t": None, "model_s": None,
                                                  "computed": None, "yours": "input"},
            titles={"t": "Time (min)", "model_s": "Model time (s)", "computed": "Computed",
                    "yours": "Yours"}, **AS_TEXT)

    def _fetch(self, k, ent):
        """(row keys, the leading columns {name: values}, computed values, why there
        are none) of run k."""
        spec = {"runs": self.ed._runs_collect(), "series": [ent],
                "time_label": {"t0_min": self._fig_t0()}}
        got = self.ed.data.series_get(spec, k, 0)
        if isinstance(got, str):
            return [], dict(t=[], model_s=[]), [], got
        run, ds = got
        t, v, _, _ = fg.series_of_run(spec, run, ds, ent, k)
        why = ""
        if v is None:
            v, why = np.full(len(run.times), np.nan), "d/dz applies to time–height panels"
        elif not np.isfinite(v).any():
            why = "not computed yet (Refresh once it is)"
        tm = np.asarray(run.times, dtype=np.float64)
        return tm, dict(t=[round(float(x), 4) for x in t], model_s=[float(x) for x in tm]), \
            v, why

    def _key_at(self, at):
        """The key (model time, s) of a new row at this time on the axis (min)."""
        return fg.axis_at(at, self.lead["t"], self.lead["model_s"], 60.0)

    def _lead_at(self, key):
        """The leading columns of an added row at this key."""
        return dict(t=round(fg.axis_at(key, self.lead["model_s"], self.lead["t"], 1.0 / 60.0), 4),
                    model_s=key)

    def _csv_head(self):
        return "time_min,model_time_s,computed,plotted\n"

    def _csv_lead(self, df, j):
        return f"{df['t'][j]:g},{df['model_s'][j]:g}"

    # ---- edits on the entry
    def edits(self, k=None):
        """The card's edits of run k (all runs: k None) {str(run): {key: value or None}}."""
        eds = self.card.ent.setdefault("edits", {})
        return eds if k is None else eds.setdefault(str(k), {})

    def added(self, k):
        """The card's rows of its own of run k {key: value}."""
        return self.card.ent.setdefault("added", {}).setdefault(str(k), {})

    def count(self):
        e = self.card.ent
        return sum(len(v) for key in ("edits", "added") for v in (e.get(key) or {}).values())

    def _store(self, k, key, val=None, drop=False):
        eds = self.edits(k)
        if drop:
            eds.pop(key, None)
        else:
            eds[key] = val
        self._tidy()

    def _tidy(self):
        e = self.card.ent
        for name in ("edits", "added"):
            e[name] = {k: v for k, v in (e.get(name) or {}).items() if v}
            if not e[name]:
                e.pop(name)

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
                                           description="Every edit and added row of this "
                                                       "card, every run")
        w["dl"] = pn.widgets.FileDownload(callback=self._csv, filename=f"{self.NAME}.csv",
                                          label="Download CSV", button_type="primary",
                                          button_style="outline", height=32)
        w["add_at"] = pn.widgets.FloatInput(name=self.AT, value=None)
        w["add_val"] = pn.widgets.FloatInput(name="Value", value=None)
        w["add"] = pn.widgets.Button(name="Add row", height=32, button_type="primary",
                                     button_style="outline",
                                     description="A point at this place in the line; where "
                                                 "there is a row already, that row's value")
        w["table"] = self._table()
        w["note"] = pn.pane.HTML(margin=(0, 4), sizing_mode="stretch_width")
        w["drop_gone"] = pn.widgets.Button(name="Drop those", height=28, button_type="light",
                                           button_style="outline", visible=False,
                                           description=f"Forget the edits {self.GONE}")
        w["run"].param.watch(lambda e: self.refresh(), "value")
        w["refresh"].on_click(lambda e: self.refresh())
        w["blank"].on_click(lambda e: self._picked(blank=True))
        w["reset"].on_click(lambda e: self._picked(blank=False))
        w["reset_all"].on_click(lambda e: self._reset_all())
        w["drop_gone"].on_click(lambda e: self._drop_gone())
        w["add"].on_click(lambda e: self._add_row())
        w["table"].on_edit(self._on_edit)
        self.section.objects = [
            _grid(w["run"], w["refresh"], w["dl"], w["blank"], w["reset"], w["reset_all"]),
            _hint(self.HINT),
            _grid(w["add_at"], w["add_val"], w["add"]),
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
            with held(self.ed):
                keep = w["run"].value
                w["run"].param.update(options=opts,
                                      value=keep if keep in opts.values()
                                      else next(iter(opts.values()), None))
        w["run"].visible = len(opts) > 1
        self.k = k = w["run"].value
        ent = self.card.collect()
        name = (ent.get("label") or "").strip() or self.NAME
        w["dl"].filename = f"{name}.csv".replace("/", "_").replace(" ", "_")
        if k is None:
            return self._show(*self._fetch_none(), "no run")
        self._show(*self._fetch(k, ent))

    def _fetch_none(self):
        return [], {c: [] for c in self.w["table"].value.columns[:-2]}, []

    def _fig_t0(self):
        tl = getattr(self.ed, "tl_t0", None)  # (Style: built when first opened)
        if tl is not None:
            return float(tl.value or 0.0)
        return float(self.ed.spec.get("time_label", {}).get("t0_min", 0.0))

    def _show(self, keys, lead, v, why):
        w, k = self.w, self.k
        self.base, self.lead = np.asarray(keys, dtype=np.float64), lead
        yours = [""] * len(self.base)
        eds = (self.card.ent.get("edits") or {}).get(str(k)) or {}
        gone = 0
        for key, val in eds.items():
            j = np.flatnonzero(np.abs(self.base - float(key)) < self.TOL)
            if not j.size:
                gone += 1
                continue
            yours[j[0]] = BLANK if val is None else _fmt(val)
        df = pd.DataFrame(dict(lead, computed=[_fmt(float(x)) for x in v], yours=yours))
        ads = (self.card.ent.get("added") or {}).get(str(k)) or {}
        rows = []
        for key, val in ads.items():
            j = np.flatnonzero(np.abs(self.base - float(key)) < self.TOL)
            if j.size:  # (the run has this row now)
                df.loc[j[0], "yours"] = _fmt(val)
            else:
                rows.append(dict(self._lead_at(float(key)), computed="", yours=_fmt(val)))
        keys = self.base
        if rows:
            more = [float(x) for x in ads if not (np.abs(self.base - float(x)) < self.TOL).any()]
            keys = np.r_[self.base, more]
            order = np.argsort(keys, kind="stable")
            df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True).iloc[order]
            df, keys = df.reset_index(drop=True), keys[order]
        self.keys = keys
        w["table"].value = df
        w["table"].selection = []
        msg = [why] if why else []
        n = len(eds) - gone
        if n:
            msg.append(f"{n} point{'s' if n != 1 else ''} edited")
        if ads:
            msg.append(f"{len(ads)} row{'s' if len(ads) != 1 else ''} added")
        if gone:
            msg.append(f"{gone} edit{'s' if gone != 1 else ''} {self.GONE} (not drawn)")
        w["note"].object = f'<div class="cv-hint">{" · ".join(msg)}</div>' if msg else ""
        w["drop_gone"].visible = bool(gone)

    # ---- editing
    def _on_edit(self, ev):
        if ev.column != "yours" or self.k is None or not 0 <= ev.row < self.keys.size:
            return
        key = fg.edit_key(self.keys[ev.row])
        p = parse_yours(ev.value)
        mine = self._added_key(key)
        if mine is not None and p is not None:
            self._set_added(mine, None if not p[0] else p[1])
            return self.done()
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
            if abs(float(x) - float(key)) < self.TOL:
                return x
        return None

    def _added_key(self, key):
        """The stored key of the row of your own at the place of key, if any."""
        for x in (self.card.ent.get("added") or {}).get(str(self.k)) or {}:
            if abs(float(x) - float(key)) < self.TOL:
                return x
        return None

    def _set_added(self, key, val):
        """A row of your own at key takes value val; None (blanked, cleared): it goes."""
        ads = self.added(self.k)
        if val is None:
            ads.pop(key, None)
        else:
            ads[key] = val
        self._tidy()

    def _add_row(self):
        w = self.w
        at, val = w["add_at"].value, w["add_val"].value
        why = ("no run" if self.k is None else "no rows to place it among yet"
               if not self.base.size else "give it a place and a value"
               if at is None or val is None else "")
        if why:
            w["note"].object = f'<div class="cv-hint">Add row: {why}</div>'
            return
        where = self._key_at(float(at))
        j = np.flatnonzero(np.abs(self.base - where) < self.TOL)
        mine = self._added_key(where)
        if mine is not None:
            self._set_added(mine, float(val))
        elif j.size:  # (a row the run has: its value)
            key = fg.edit_key(self.base[j[0]])
            old = self._old_key(key)
            if old is not None:
                self._store(self.k, old, drop=True)
            self._store(self.k, key, float(val))
        else:
            self._set_added(fg.edit_key(where), float(val))
        w["add_val"].value = None
        self.done()

    def _picked(self, blank):
        rows = [j for j in self.w["table"].selection if 0 <= j < self.keys.size]
        if not rows or self.k is None:
            return
        for j in rows:
            key = fg.edit_key(self.keys[j])
            mine = self._added_key(key)
            if mine is not None:  # (a row of your own: blanked or reset, it goes)
                self._set_added(mine, None)
                continue
            old = self._old_key(key)
            if old is not None:
                self._store(self.k, old, drop=True)
            if blank:
                self._store(self.k, key, None)
        self.done()

    def _reset_all(self):
        self.card.ent.pop("edits", None)
        self.card.ent.pop("added", None)
        self.done()

    def _drop_gone(self):
        eds = self.edits(self.k)
        for key in [x for x in eds if not (np.abs(self.base - float(x)) < self.TOL).any()]:
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
        """The run's line as drawn: where (series: time, min, and model time, s;
        profile: height, km), computed, plotted."""
        df = self.w["table"].value
        out = io.StringIO()
        out.write(self._csv_head())
        for j, (c, y) in enumerate(zip(df["computed"], df["yours"])):
            p = c if y == "" else "" if y == BLANK else y
            out.write(f"{self._csv_lead(df, j)},{c},{p}\n")
        out.seek(0)
        return out


class ProfileValues(SeriesValues):
    """The Values section of a ProfileCard: a row per level (height, km)."""

    TOL = fg.EDIT_ZTOL
    NAME = "profile"
    HINT = ("Type a value in Yours to replace a level's, <i>blank</i> to leave it out, or "
            "clear the cell to undo.  <b>Add row</b> puts in a point at a height of your own "
            "(clear its Yours to take it out).  Edits are on the plotted values (after d/dz "
            "and the time window's mean); the values are the preview's (nothing is computed "
            "here).")
    GONE = "at heights this profile does not have"
    AT = "New row: height (km)"

    def _table(self):
        return pn.widgets.Tabulator(
            pd.DataFrame(dict(z=[], computed=[], yours=[])), show_index=False,
            selectable="checkbox", theme="midnight", height=300, layout="fit_data_fill",
            sizing_mode="stretch_width", editors={"z": None, "computed": None,
                                                  "yours": "input"},
            titles={"z": "Height (km)", "computed": "Computed", "yours": "Yours"}, **AS_TEXT)

    def _fetch(self, k, ent):
        runs = self.ed._runs_collect()
        if k >= len(runs):
            return [], dict(z=[]), [], "no such run"
        got = self.ed.data.profile_get(runs[k], fg.entry_at(dict(runs=runs), ent, k), 0, 1,
                                       compute=False)
        if isinstance(got, str):
            return [], dict(z=[]), [], got
        z, v = got
        why = "" if np.isfinite(v).any() else "no values"
        return z, dict(z=[round(float(x), 4) for x in z]), v, why

    def _key_at(self, at):
        return at

    def _lead_at(self, key):
        return dict(z=round(key, 4))

    def _csv_head(self):
        return "z_km,computed,plotted\n"

    def _csv_lead(self, df, j):
        return f"{df['z'][j]:g}"
