"""The card of a table figure: which values, of which runs at which times."""

import panel as pn

from ...core import dist
from ...viewer.numinput import FloatInput
from .. import draw as figdraw, spec as fg
from .base import (
    SND_WHERE, _f, _fold, _grid, _hint, _num, card_buttons, field_widget, keep_box, label_widget,
    panel_index, panel_tag, panel_widget, region_recipe, region_widgets, show_region,
    vertical_recipe, vertical_widgets, where_grid,
)
from .distcard import DIST_VMODES
from .seriescard import ALL_RUNS, SOME_RUNS, SeveralRuns, several_run_choices

TBL_WHAT = {"Sounding parameters": "sounding", "Field statistics": "field"}
TBL_LAYOUTS = {"A row per run and time, a column per value": "rows",
               "A row per value, a column per run and time": "values",
               "A row per value and run, a column per time": "values_run",
               "A row per value and time, a column per run": "values_time"}
TBL_COMPARE = {"The values": "", "Differences from the first run": "run",
               "Differences from the first time": "time"}
TBL_DECIMALS = {"Automatic": -1, "0": 0, "1": 1, "2": 2, "3": 3, "4": 4}


class TableCard(SeveralRuns):
    """Columns of a table: sounding parameters at a place, or statistics of a field over a
    region, from its runs at its times.  The cards of a panel make one table."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        r = ent["recipe"]
        self.w = w = {}
        card_buttons(self, "Remove these values", dup=True)
        runs = fg.profile_runs(ent)
        k = ALL_RUNS if runs is None else int(runs[0]) if len(runs) == 1 else SOME_RUNS
        w["run"] = pn.widgets.Select(name="Run", width=170, **several_run_choices(ed))
        w["run"].value = k if k in self._run_values() else 0
        w["runs"] = pn.widgets.MultiChoice(name="Runs", options=ed._series_run_opts(),
                                           value=[int(j) for j in (runs or [])]
                                           if k == SOME_RUNS else [], width=260)
        w["times"] = pn.widgets.TextInput(
            name="Times (min)", value=fg.times_text(ent.get("times_s") or []), width=210,
            placeholder="30, 60, 90 or 30-120/15",
            description="Minutes of the first run: 30, 60, 90; 30-120/15 (every 15 min); 30-120 "
                        "(every output).  Each goes to the nearest output.")
        w["what"] = pn.widgets.Select(name="Values", options=TBL_WHAT, width=170,
                                      value=ent.get("what", "sounding"))
        wh = ent.get("where", {})
        w["kind"] = pn.widgets.Select(name="Where", options=SND_WHERE, width=180,
                                      value=wh.get("kind", "trk"))
        w["x"] = _f("x (km)", float(wh.get("x", 0.0)), 80, step=1.0)
        w["y"] = _f("y (km)", float(wh.get("y", 0.0)), 80, step=1.0)
        w["avg"] = _f("Box width (km, 0: column)", float(wh.get("avg", 0.0)), 170, step=0.5,
                      start=0.0)
        w["params"] = pn.widgets.MultiChoice(
            name="Parameters", value=list(ent.get("params") or []), width=420,
            options={f"{h} ({u})" if u else h: p for p, h, u in figdraw.SND_PARAMS})
        w["field"] = field_widget(ed.fields, r["field"])
        vertical_widgets(w, r, DIST_VMODES, "height")
        region_widgets(self, r)
        w["lo"] = FloatInput(name="Only values from", value=r.get("lo"), placeholder="all",
                             width=120, description="Keep values at or above this (blank: no "
                                                    "limit), e.g. 1 m/s for updrafts")
        w["hi"] = FloatInput(name="to", value=r.get("hi"), placeholder="all", width=90)
        w["stats"] = pn.widgets.MultiChoice(
            name="Statistics", value=list(ent.get("stats") or []), width=420,
            options={v: k for k, v in fg.TBL_STATS.items()})
        w["label"] = label_widget(ent, "Name in the headings (blank: automatic)")
        w["panel"] = panel_widget(ent)
        w["run"].param.watch(self._on_run, "value")
        w["runs"].param.watch(self._on_runs, "value")
        for k, x in w.items():
            if k not in ("run", "runs", "panel"):
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: (self._show(), ed._fit_grid(), ed.request()), "value")
        self.title = pn.pane.HTML("<b>Values</b>", margin=(6, 4, 0, 4))
        self.t_note = pn.pane.HTML(margin=(0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [where_grid(self, w["run"], (w["runs"], 3), (w["times"], 2)), self.t_note,
             _grid(w["what"], w["kind"], w["x"], w["y"], w["avg"], (w["field"], 2), w["vmode"],
                   w["z"], w["z0"], w["z1"], w["region"], w["radius"], w["offx"], w["offy"],
                   w["lo"], w["hi"], (w["label"], 3)),
             w["params"], w["stats"],
             _hint("Each value is read from every run here at every time here (the other runs "
                   "at the same time since their time zeros). More entries in a panel add "
                   "columns to one table, so it can hold both parameters and statistics. "
                   "Statistics take every value of the field in the region at that time.")])
        self._show()

    def _outputs(self):
        return list(self.ed._time_opts(self._time_run()).values())

    def _time_run(self):
        """The run the times are of: the first of the card's."""
        ks = self.run_list()
        return int(ks[0]) if ks else 0

    def _show(self):
        w = self.w
        snd = w["what"].value == "sounding"
        for k in ("kind", "params"):
            w[k].visible = snd
        w["x"].visible = w["y"].visible = w["avg"].visible = snd and w["kind"].value != "mean"
        two = self.ed.fields[w["field"].value].ndim == 2
        for k in ("field", "region", "lo", "hi", "stats"):
            w[k].visible = not snd
        mode = w["vmode"].value
        w["vmode"].visible = not snd and not two
        w["z"].visible = not snd and not two and mode == "height"
        w["z0"].visible = w["z1"].visible = not snd and not two and mode == "layer"
        show_region(w)
        if snd:
            w["radius"].visible = w["offx"].visible = w["offy"].visible = False
        w["runs"].visible = w["run"].value == SOME_RUNS
        self.times, bad = fg.parse_times(w["times"].value, self._outputs())
        self.t_note.object = f'<div class="cv-hint">Not a time: {", ".join(bad)}.</div>' if bad \
            else "" if self.times else '<div class="cv-hint">Give at least one time.</div>'
        runs = self.run_list()
        names = {k: n.split(". ", 1)[-1] for n, k in self.ed._run_names().items()}
        run = "every run" if runs is None else names.get(runs[0], "") if len(runs) == 1 \
            else f"{len(runs)} runs"
        what = "Sounding" if snd else self.ed.fields[w["field"].value].label
        n = len(w["params" if snd else "stats"].value)
        self.title.object = (f"<b>Values</b> · {what} · {n} value{'s' * (n != 1)} · {run} · "
                             f"{len(self.times)} time{'s' * (len(self.times) != 1)} · panel "
                             f"{panel_tag(w)}")

    def _changed(self):
        keep_box(self)
        self._show()
        self.ed.request()

    def _reshow(self):
        self._show()

    def _run_picked(self):
        self._show()
        self.ed.request()

    def _runs_picked(self):
        self._run_picked()

    def recipe(self):
        w, d = self.w, self.ed.fields[self.w["field"].value]
        return dist.normalize(dict(
            field=d.name, vmode="2d" if d.ndim == 2 else w["vmode"].value,
            **vertical_recipe(w), **region_recipe(self),
            lo=_num(w["lo"].value), hi=_num(w["hi"].value)))

    def collect(self):
        w, runs = self.w, self.run_list()
        return dict(what=w["what"].value, panel=panel_index(w), label=w["label"].value,
                    run=int(runs[0]) if runs else 0, runs=runs, times_s=list(self.times),
                    where=dict(kind=w["kind"].value, x=float(w["x"].value or 0.0),
                               y=float(w["y"].value or 0.0), avg=float(w["avg"].value or 0.0)),
                    params=list(w["params"].value), recipe=self.recipe(),
                    stats=list(w["stats"].value))
