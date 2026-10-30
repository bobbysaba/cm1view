"""The card of one vertical profile of a profile figure."""

import panel as pn

from ...core import series as ser
from ...core.fields import deriv_name
from .. import spec as fg
from .base import (
    _hex, _f, _grid, _hint, _fold, SER_REGIONS, SER_REDUCE, _BTN, _chk, _deriv_pair,
)
from .seriescard import ALL_RUNS, ENS_BANDS, SOME_RUNS, several_run_choices
from .seriesvals import ProfileValues

PROF_STYLES = {"Solid": "", "Dashed": "--", "Dotted": ":", "Dash-dot": "-."}
ONE_TIME = -1.0  # (the "to" time of a profile at one time)
PROF_OPS = {"Value": "", "d/dz (per m)": "ddz"}


class ProfileCard:
    """One profile of a profile figure: its run (or every run, or the runs picked:
    a line each, or an ensemble band), time (or a time window it is averaged over), a
    layer series recipe (field, bottom and top, region, reduction), look and panel."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.box = r.get("box")
        self.w = w = {}
        self.rm = pn.widgets.Button(name="✕", description="Remove the profile", **_BTN)
        self.dup = pn.widgets.Button(name="Duplicate", height=32, button_type="light",
                                     button_style="outline",
                                     description="A copy of this card in a new panel")
        self.per_run = pn.widgets.Button(
            name="One per run", height=32, button_type="light", button_style="outline",
            description="A card for each run (this card's runs, or each other run of the "
                        "figure) in this panel")
        runs = fg.profile_runs(ent)
        k = ALL_RUNS if runs is None else int(runs[0]) if len(runs) == 1 else SOME_RUNS
        w["run"] = pn.widgets.Select(name="Run", width=170, **several_run_choices(ed))
        w["run"].value = k if k in self._run_values() else 0
        w["runs"] = pn.widgets.MultiChoice(name="Runs", options=ed._series_run_opts(),
                                           value=[int(j) for j in (runs or [])]
                                           if k == SOME_RUNS else [], width=260)
        opts = ed._time_opts(self._time_run())
        w["time"] = pn.widgets.Select(name="Time", options=opts, width=210,
                                      value=ed._nearest(opts, ent.get("time_s")))
        t1 = ent.get("time_s1")
        w["time1"] = pn.widgets.Select(
            name="Mean to (a time window)", options=self._to_opts(opts), width=210,
            value=ONE_TIME if t1 is None else ed._nearest(opts, t1),
            description="Average the profiles of every output from Time to this one")
        w["field"], w["deriv"] = _deriv_pair(F, r["field"])
        w["z0"] = _f("Bottom (km)", float(r.get("z0", 0.0)), 90, step=0.5)
        w["z1"] = _f("Top (km)", float(r.get("z1", 10.0)), 80, step=0.5)
        w["region"] = pn.widgets.Select(name="Region", options=SER_REGIONS, value=r["region"],
                                        width=180)
        w["radius"] = _f("Radius (km)", float(r.get("radius", 5.0)), 90, step=0.5)
        off = r.get("offset") or (0.0, 0.0)
        w["offx"] = _f("Offset x (km)", float(off[0]), 100, step=1.0)
        w["offy"] = _f("Offset y (km)", float(off[1]), 100, step=1.0)
        w["reduce"] = pn.widgets.Select(name="Reduce", options=SER_REDUCE, value=r["reduce"],
                                        width=120)
        w["pct"] = _f("Percentile", float(r.get("pct", 99.0)), 90, step=0.5)
        w["op"] = pn.widgets.Select(
            name="Plot", options=PROF_OPS, value=ent.get("op", ""), width=130,
            description="d/dz of this profile, e.g. of the maximum w at each level (not "
                        "the maximum of dw/dz at each level)")
        w["label"] = pn.widgets.TextInput(name="Legend text (blank: automatic)",
                                          value=ent.get("label", ""), width=220)
        w["auto_color"] = _chk("Automatic colour", not ent.get("color"))
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(ent.get("color") or "k"),
                                            width=70)
        w["ls"] = pn.widgets.Select(name="Line", options=PROF_STYLES, width=100,
                                    value=ent.get("ls", "") if ent.get("ls", "") in
                                    PROF_STYLES.values() else "")
        w["lw"] = _f("Line width", float(ent.get("lw") or 1.5), 90, step=0.25)
        w["panel"] = pn.widgets.IntInput(name="Panel", start=1, end=64, width=70,
                                         value=int(ent.get("panel", 0)) + 1)
        w["ens"] = pn.widgets.Select(name="Ensemble of its runs", options=ENS_BANDS,
                                     value=ent.get("ens", ""), width=170)
        w["ens_mid"] = pn.widgets.Select(name="Centre line", options={
            "Mean": "mean", "Median": "median", "None": ""},
            value=ent.get("ens_mid", "mean"), width=100)
        w["ens_members"] = pn.widgets.Select(name="Runs' own lines", options={
            "Faint": "faint", "Hidden": "hidden", "As other lines": "full"},
            value=ent.get("ens_members", "faint"), width=130)
        w["ens_alpha"] = _f("Band opacity", float(ent.get("ens_alpha", 0.25)), 100, step=0.05,
                            start=0.0, end=1.0)
        w["run"].param.watch(self._on_run, "value")
        w["runs"].param.watch(self._on_runs, "value")
        what = ("time", "time1", "field", "deriv", "z0", "z1", "region", "radius", "offx",
                "offy", "reduce", "pct", "op")  # (what the values are of: edits go stale)
        for k, x in w.items():
            if k not in ("run", "runs", "panel"):
                x.param.watch(lambda e, k=k: self._changed(k in what), "value")
        w["panel"].param.watch(lambda e: (self._show(), ed._fit_grid(), ed.request()), "value")
        self.title = pn.pane.HTML("<b>Profile</b>", margin=(6, 4, 0, 4))
        self.info = pn.pane.HTML(margin=(0, 4))
        self.vals = ProfileValues(self)  # (its values, and your edits of them)
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [_grid(w["run"], (w["runs"], 2), w["panel"], self.dup, self.per_run),
             _grid((w["time"], 2), (w["time1"], 2), (w["field"], 2), w["deriv"],
                   w["z0"], w["z1"], w["region"], w["radius"], w["offx"], w["offy"],
                   w["reduce"], w["pct"], w["op"], w["auto_color"], w["color"], w["ls"],
                   w["lw"],
                   (w["label"], 3)),
             _grid(w["ens"], w["ens_mid"], w["ens_members"], w["ens_alpha"]),
             self.vals.section, self.info,
             _hint("The field reduced over the region at every model level from Bottom to "
                   "Top (a layer series, computed only at the times needed and cached with "
                   "the Series tool's). Around the storm: a disc around each run's track. "
                   "A time window averages the profiles of its outputs. Several runs: a "
                   "line each at the nearest output to Time (the first run's times), or "
                   "an ensemble band. Automatic colour: the run's colour when each "
                   "profile of the panel is from another run, else the next colour.")])
        self._show()

    @staticmethod
    def _to_opts(opts):
        return {"— (this time only)": ONE_TIME} | dict(opts)

    def _show(self):
        w = self.w
        trk = w["region"].value == "track"
        w["radius"].visible = w["offx"].visible = w["offy"].visible = trk
        w["pct"].visible = w["reduce"].value == "pct"
        w["color"].visible = not w["auto_color"].value
        w["runs"].visible = w["run"].value == SOME_RUNS
        several = w["run"].value in (ALL_RUNS, SOME_RUNS)
        w["ens"].visible = several
        for k in ("ens_mid", "ens_members", "ens_alpha"):
            w[k].visible = several and bool(w["ens"].value)
        d = self.ed.fields[self.field_name()]
        when = next((k for k, v in w["time"].options.items() if v == w["time"].value), "")
        when = when.split("(")[-1].rstrip(")")
        if self._t1() is not None:
            to = next((k for k, v in w["time1"].options.items() if v == w["time1"].value), "")
            when += f" to {to.split('(')[-1].rstrip(')')}"
        two = " · <i>a 3D field is needed</i>" if d.ndim == 2 else ""
        runs = self.run_list()
        names = {k: n.split(". ", 1)[-1] for n, k in self.ed._run_names().items()}
        run = "every run" if runs is None else names.get(runs[0], "") if len(runs) == 1 \
            else f"{len(runs)} runs"
        op = " · d/dz" if w["op"].value == "ddz" else ""
        self.title.object = (f"<b>Profile</b> · {d.label}{op} · {run} · {when} · panel "
                             f"{w['panel'].value}{two}")

    def _t1(self):
        """The end of the time window (None: one time)."""
        t0, t1 = self.w["time"].value, self.w["time1"].value
        return None if t1 in (None, ONE_TIME) or t0 is None or float(t1) <= float(t0) \
            else float(t1)

    def _changed(self, stale=False):
        if self.w["region"].value == "box" and self.box is None:
            self.box = [float(v) for v in self.ed.v.view]
        self._show()
        if stale:
            self._edits_stale()
        self.ed.request()

    def _edits_stale(self):
        """What the values are of changed: hand edits (made on the values before)
        are kept, with a word on the card."""
        self._stale = bool(self.vals.count())
        self.edits_changed()
        self.vals.refresh()

    def edits_changed(self):
        n = self.vals.count()
        self._stale = getattr(self, "_stale", False) and bool(n)
        self.info.object = (
            f'<div class="cv-hint">{n} hand edit{"s" if n != 1 else ""} made on this '
            f'profile before its recipe, time or Plot changed are still drawn: check them '
            f'under Values (Reset all edits clears them).</div>' if self._stale else "")

    # ---- run
    def _run_values(self):
        o = self.w["run"].groups or {"": self.w["run"].options}
        return [v for g in o.values() for v in (g.values() if isinstance(g, dict) else g)]

    def run_list(self):
        """The card's runs: None for every run, else a list of run indices."""
        k = self.w["run"].value
        if k == ALL_RUNS:
            return None
        if k == SOME_RUNS:
            return sorted(int(j) for j in self.w["runs"].value if not isinstance(j, str)) \
                or None
        return [int(k)] if isinstance(k, int) and k >= 0 else [0]

    def _time_run(self):
        """The run whose outputs the Time lists offer: the first of the card's."""
        ks = self.run_list()
        return int(ks[0]) if ks else 0

    def set_runs(self, runs):
        """Show runs (None: every run)."""
        w = self.w
        hold, self.ed._hold = self.ed._hold, True
        try:
            if runs is not None and len(runs) == 1:
                w["runs"].value = []
                w["run"].value = int(runs[0])
            elif runs is None:
                w["runs"].value = []
                w["run"].value = ALL_RUNS
            else:
                w["runs"].value = sorted(int(k) for k in runs)
                w["run"].value = SOME_RUNS
        finally:
            self.ed._hold = hold
        self._show()

    def refresh_runs(self, names=None):
        """The run lists' choices again (runs renamed, added or removed), keeping the
        card's runs."""
        names = names or self.ed._run_names()
        keep = self.run_list()
        hold, self.ed._hold = self.ed._hold, True
        try:
            self.w["runs"].options = self.ed._series_run_opts(names)
            self.w["run"].param.update(**several_run_choices(self.ed, names))
        finally:
            self.ed._hold = hold
        self.set_runs([k for k in keep if k in names.values()] or [0]
                      if keep is not None else None)

    def _on_run(self, ev):
        if self.ed._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
            return
        if ev.new == SOME_RUNS and not self.w["runs"].value:  # (from every run)
            hold, self.ed._hold = self.ed._hold, True
            try:
                self.w["runs"].value = sorted(self.ed._run_names().values())
            finally:
                self.ed._hold = hold
        self._runs_changed()

    def _on_runs(self, ev):
        """A run not in the figure picked (its path): add it to the figure, and keep
        it picked here."""
        if self.ed._hold:
            return
        new = [v for v in ev.new if isinstance(v, str)]
        if new:
            keep = [v for v in ev.new if not isinstance(v, str)]
            for p in new:
                k = self.ed._add_run(p, grid=False)
                if k is not None:
                    keep.append(k)
            hold, self.ed._hold = self.ed._hold, True
            try:
                self.w["runs"].value = sorted(set(keep))
            finally:
                self.ed._hold = hold
        self._runs_changed()

    def _runs_changed(self):
        """The card's runs changed: the Time lists offer its first run's outputs."""
        o = self.ed._time_opts(self._time_run())
        cur, cur1 = self.w["time"].value, self._t1()
        hold, self.ed._hold = self.ed._hold, True
        try:
            self.w["time"].options = o
            self.w["time"].value = self.ed._nearest(o, cur)
            self.w["time1"].options = self._to_opts(o)
            self.w["time1"].value = ONE_TIME if cur1 is None else self.ed._nearest(o, cur1)
        finally:
            self.ed._hold = hold
        self._show()
        self.vals.refresh()
        self.ed.request()

    def field_name(self):
        """The profile's field: the Field, or its Derivative (fields.deriv_name)."""
        return deriv_name(self.w["deriv"].value, self.w["field"].value)

    def recipe(self):
        w, d = self.w, self.ed.fields[self.field_name()]
        return ser.normalize(dict(
            field=d.name, vmode="layer", z0=w["z0"].value or 0.0, z1=w["z1"].value or 0.0,
            region=w["region"].value, radius=w["radius"].value or 5.0,
            offset=(w["offx"].value or 0.0, w["offy"].value or 0.0),
            reduce=w["reduce"].value,
            pct=w["pct"].value if w["pct"].value is not None else 99.0,
            box=self.box or [float(v) for v in self.ed.v.view]))

    def collect(self):
        w, runs = self.w, self.run_list()
        eds = {k: dict(v) for k, v in (self.ent.get("edits") or {}).items() if v}
        return dict(run=int(runs[0]) if runs else 0, runs=runs,
                    time_s=float(w["time"].value or 0.0),
                    time_s1=self._t1(), panel=max(0, int(w["panel"].value or 1) - 1),
                    label=w["label"].value,
                    color="" if w["auto_color"].value else w["color"].value,
                    ls=w["ls"].value, lw=float(w["lw"].value or 1.5), recipe=self.recipe(),
                    ens=w["ens"].value, ens_mid=w["ens_mid"].value,
                    ens_members=w["ens_members"].value, op=w["op"].value,
                    ens_alpha=float(w["ens_alpha"].value if w["ens_alpha"].value is not None
                                    else 0.25), **({"edits": eds} if eds else {}))
