"""The card of one vertical profile of a profile figure."""

import panel as pn

from ...core import series as ser
from ...core.fields import deriv_name
from .. import spec as fg
from .base import (
    _grid, _hint, _deriv_pair, TimeCard, LINE_STYLES, card_body, ens_values,
    ens_widgets, hold_value, keep_box, label_widget, layer_widgets, look_values, look_widgets,
    per_run_button, reduce_recipe, reduce_widgets, region_recipe, region_widgets, show_ens,
    show_region, vertical_recipe,
)
from .seriescard import ALL_RUNS, SOME_RUNS, SeveralRuns, several_run_choices
from .seriesvals import ProfileValues

PROF_STYLES = dict(LINE_STYLES, Solid="")  # (saved so: solid is the blank value)
PROF_OPS = {"None": "", "d/dz (per m)": "ddz"}


class ProfileCard(SeveralRuns, TimeCard):
    """One profile of a profile figure: its run (or every run, or the runs picked:
    a line each, or an ensemble band), time (or a time window it is averaged over), a
    layer series recipe (field, bottom and top, region, reduction) and look."""
    _EDITS = "profile before its recipe, time or Then apply changed"

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.w = w = {}
        self.per_run = per_run_button(
            "A card for each run (this card's runs, or each other run of the "
            "figure) in this panel")
        runs = fg.profile_runs(ent)
        k = ALL_RUNS if runs is None else int(runs[0]) if len(runs) == 1 else SOME_RUNS
        w["run"] = pn.widgets.Select(name="Run", width=170, **several_run_choices(ed))
        w["run"].value = k if k in self._run_values() else 0
        w["runs"] = pn.widgets.MultiChoice(name="Runs", options=ed._series_run_opts(),
                                           value=[int(j) for j in (runs or [])]
                                           if k == SOME_RUNS else [], width=260)
        opts = ed._time_opts(self._time_run())
        self._time_widgets(opts, "Mean to (a time window)",
                           "Average the profiles of every output from Time to this one")
        w["field"], w["deriv"] = _deriv_pair(F, r["field"])
        layer_widgets(w, r)
        region_widgets(self, r)
        reduce_widgets(w, r)
        w["op"] = pn.widgets.Select(
            name="Then apply", options=PROF_OPS, value=ent.get("op", ""), width=130,
            description="d/dz of this profile, e.g. of the maximum w at each level (not "
                        "the maximum of dw/dz at each level)")
        w["label"] = label_widget(ent)
        look_widgets(w, ent, auto=True, ls=PROF_STYLES, lw=1.5)
        ens_widgets(w, ent)
        w["run"].param.watch(self._on_run, "value")
        w["runs"].param.watch(self._on_runs, "value")
        what = ("time", "time1", "field", "deriv", "z0", "z1", "region", "radius", "offx",
                "offy", "reduce", "pct", "op")  # (what the values are of: edits go stale)
        for k, x in w.items():
            if k not in ("run", "runs"):
                x.param.watch(lambda e, k=k: self._changed(k in what), "value")
        self.info = pn.pane.HTML(margin=(0, 4))
        self.t_note = pn.pane.HTML(margin=(0, 4))  # (a run with no output at the time)
        self._t_run = self._time_run()  # (the run the Time lists are of)
        self.vals = ProfileValues(self)  # (its values, and your edits of them)
        self.body = card_body(
            _grid(w["run"], (w["time"], 2), (w["runs"], 3), (w["time1"], 2), w["hold"],
                  self.per_run),
            _grid((w["field"], 2), w["deriv"],
                  w["z0"], w["z1"], w["region"], w["radius"], w["offx"], w["offy"],
                  w["reduce"], w["pct"], w["op"], w["auto_color"], w["color"], w["ls"],
                  w["lw"],
                  (w["label"], 3)),
            _grid(w["ens"], w["ens_mid"], w["ens_members"], w["ens_alpha"]),
            self.vals.section, self.t_note, self.info,
            _hint("The field reduced over the region at every model level from Read "
                   "from to Read to (a layer series, computed only at the times needed and cached with "
                   "the Series tool's). Around the storm: a disc around each run's track. "
                   "A time window averages the profiles of its outputs. Several runs: a "
                   "line each at the same time since each run's time zero (Time is the "
                   "first run's), or an ensemble band. Automatic colour: the run's colour "
                   "when each profile of the panel is from another run, else the next "
                   "colour."))
        self._show()

    def _show(self):
        w = self.w
        show_region(w)
        w["pct"].visible = w["reduce"].value == "pct"
        w["color"].visible = not w["auto_color"].value
        w["runs"].visible = w["run"].value == SOME_RUNS
        show_ens(w, w["run"].value in (ALL_RUNS, SOME_RUNS))
        self.time_note()

    def time_note(self):
        """Says which of the card's runs have no line: no output at the matching time."""
        ed, t = self.ed, self.w["time"].value
        rows, gone = ed.run_rows, []
        if t is not None and self._t1() is None:
            k0 = self._time_run()
            names = {k: n.split(". ", 1)[-1] for n, k in ed._run_names().items()}
            ks = range(len(rows)) if self.run_list() is None else self.run_list()
            for k in ks:
                if k == k0 or k >= len(rows):
                    continue
                o = ed._time_opts(k)
                at = ed._moved_time(t, k0, k)
                if o and abs(ed._nearest(o, at) - at) > 1.0:
                    gone.append(f"{names.get(k, k)} (no output at {at / 60:g} min)")
        self.t_note.object = f'<div class="cv-hint">No line for {", ".join(gone)}.</div>' \
            if gone else ""

    def _changed(self, stale=False):
        keep_box(self)
        self._show()
        if stale:
            self._edits_stale()
        self.ed.request()

    # ---- run
    def _time_run(self):
        """The run whose outputs the Time lists offer: the first of the card's."""
        ks = self.run_list()
        return int(ks[0]) if ks else 0

    def _run_picked(self):
        self._runs_changed()

    def _runs_picked(self):
        self._runs_changed()

    def _runs_changed(self):
        """The card's runs changed: the Time lists offer its first run's outputs, at the
        same time since their time zeros."""
        k = self._time_run()
        self._set_times(k, self._t_run)
        self._t_run = k
        self._show()
        self.vals.refresh()
        self.ed.request()

    def field_name(self):
        """The profile's field: the Field, or its Derivative (fields.deriv_name)."""
        return deriv_name(self.w["deriv"].value, self.w["field"].value)

    def recipe(self):
        w, d = self.w, self.ed.fields[self.field_name()]
        return ser.normalize(dict(field=d.name, vmode="layer", **vertical_recipe(w),
                                  **region_recipe(self), **reduce_recipe(w)))

    def collect(self):
        w, runs = self.w, self.run_list()
        eds = {key: {k: dict(v) for k, v in (self.ent.get(key) or {}).items() if v}
               for key in ("edits", "added")}
        return dict(run=int(runs[0]) if runs else 0, runs=runs,
                    time_s=float(w["time"].value or 0.0),
                    time_s1=self._t1(), label=w["label"].value,
                    recipe=self.recipe(), op=w["op"].value, **look_values(w), **ens_values(w),
                    **hold_value(w),
                    **{key: v for key, v in eds.items() if v})
