"""The card of one vertical profile of a profile figure."""

import panel as pn

from ...core import series as ser
from .base import _hex, _f, _grid, _hint, _fold, SER_REGIONS, SER_REDUCE, _BTN, _chk

PROF_STYLES = {"Solid": "", "Dashed": "--", "Dotted": ":", "Dash-dot": "-."}
ONE_TIME = -1.0  # (the "to" time of a profile at one time)


class ProfileCard:
    """One profile of a profile figure: run, time (or a time window it is averaged
    over), a layer series recipe (field, bottom and top, region, reduction), look and
    panel."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.box = r.get("box")
        self.w = w = {}
        self.rm = pn.widgets.Button(name="✕", description="Remove the profile", **_BTN)
        names = ed._run_names()
        k = int(ent.get("run", 0)) if int(ent.get("run", 0)) in names.values() else 0
        w["run"] = pn.widgets.Select(name="Run", value=k, width=170, **ed._run_choices(names))
        opts = ed._time_opts(k)
        w["time"] = pn.widgets.Select(name="Time", options=opts, width=210,
                                      value=ed._nearest(opts, ent.get("time_s")))
        t1 = ent.get("time_s1")
        w["time1"] = pn.widgets.Select(
            name="Mean to (a time window)", options=self._to_opts(opts), width=210,
            value=ONE_TIME if t1 is None else ed._nearest(opts, t1),
            description="Average the profiles of every output from Time to this one")
        field = r["field"] if r["field"] in F else next(iter(F.defs))
        w["field"] = pn.widgets.Select(name="Field", groups=F.groups(), value=field, width=210)
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
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k not in ("run", "panel"):
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: (self._show(), ed._fit_grid(), ed.request()), "value")
        self.title = pn.pane.HTML("<b>Profile</b>", margin=(6, 4, 0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [_grid(w["run"], (w["time"], 2), (w["time1"], 2), (w["field"], 2), w["z0"],
                   w["z1"], w["region"], w["radius"], w["offx"], w["offy"], w["reduce"],
                   w["pct"], w["auto_color"], w["color"], w["ls"], w["lw"], w["panel"],
                   (w["label"], 3)),
             _hint("The field reduced over the region at every model level from Bottom to "
                   "Top (a layer series, computed only at the times needed and cached with "
                   "the Series tool's). Around the storm: a disc around each run's track. "
                   "A time window averages the profiles of its outputs. Automatic colour: "
                   "the run's colour when each profile of the panel is from another run, "
                   "else the next colour.")])
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
        d = self.ed.fields[w["field"].value]
        when = next((k for k, v in w["time"].options.items() if v == w["time"].value), "")
        when = when.split("(")[-1].rstrip(")")
        if self._t1() is not None:
            to = next((k for k, v in w["time1"].options.items() if v == w["time1"].value), "")
            when += f" to {to.split('(')[-1].rstrip(')')}"
        two = " · <i>a 3D field is needed</i>" if d.ndim == 2 else ""
        self.title.object = (f"<b>Profile</b> · {d.label} · {when} · panel "
                             f"{w['panel'].value}{two}")

    def _t1(self):
        """The end of the time window (None: one time)."""
        t0, t1 = self.w["time"].value, self.w["time1"].value
        return None if t1 in (None, ONE_TIME) or t0 is None or float(t1) <= float(t0) \
            else float(t1)

    def _changed(self):
        if self.w["region"].value == "box" and self.box is None:
            self.box = [float(v) for v in self.ed.v.view]
        self._show()
        self.ed.request()

    def _on_run(self, ev):
        if self.ed._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
            return
        o = self.ed._time_opts(ev.new)
        cur, cur1 = self.w["time"].value, self._t1()
        self.ed._hold = True
        try:
            self.w["time"].options = o
            self.w["time"].value = self.ed._nearest(o, cur)
            self.w["time1"].options = self._to_opts(o)
            self.w["time1"].value = ONE_TIME if cur1 is None else self.ed._nearest(o, cur1)
        finally:
            self.ed._hold = False
        self._show()
        self.ed.request()

    def recipe(self):
        w, d = self.w, self.ed.fields[self.w["field"].value]
        return ser.normalize(dict(
            field=d.name, vmode="layer", z0=w["z0"].value or 0.0, z1=w["z1"].value or 0.0,
            region=w["region"].value, radius=w["radius"].value or 5.0,
            offset=(w["offx"].value or 0.0, w["offy"].value or 0.0),
            reduce=w["reduce"].value,
            pct=w["pct"].value if w["pct"].value is not None else 99.0,
            box=self.box or [float(v) for v in self.ed.v.view]))

    def collect(self):
        w = self.w
        return dict(run=int(w["run"].value or 0), time_s=float(w["time"].value or 0.0),
                    time_s1=self._t1(), panel=max(0, int(w["panel"].value or 1) - 1),
                    label=w["label"].value,
                    color="" if w["auto_color"].value else w["color"].value,
                    ls=w["ls"].value, lw=float(w["lw"].value or 1.5), recipe=self.recipe())
