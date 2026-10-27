"""The card of one joint distribution of a joint distribution figure."""

import panel as pn

from ...core import joint
from ...viewer.numinput import FloatInput
from .base import _hex, _f, _num, _grid, _hint, _fold, SER_REGIONS, _BTN, _chk
from .distcard import DIST_VMODES
from .profcard import ONE_TIME

JOINT_PLOTS = {"2D histogram": "hist", "Scatter": "scatter", "Density contours": "contour"}


class JointCard:
    """One joint distribution of a joint distribution figure: run, time (or a time
    window whose pairs are all taken), a joint recipe (x and y fields, height, layer or
    whole depth, region, value limits of each), look and panel."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.box = r.get("box")
        self.w = w = {}
        self.rm = pn.widgets.Button(name="✕", description="Remove the joint distribution",
                                    **_BTN)
        names = ed._run_names()
        k = int(ent.get("run", 0)) if int(ent.get("run", 0)) in names.values() else 0
        w["run"] = pn.widgets.Select(name="Run", value=k, width=170, **ed._run_choices(names))
        opts = ed._time_opts(k)
        w["time"] = pn.widgets.Select(name="Time", options=opts, width=210,
                                      value=ed._nearest(opts, ent.get("time_s")))
        t1 = ent.get("time_s1")
        w["time1"] = pn.widgets.Select(
            name="To (a time window)", options=self._to_opts(opts), width=210,
            value=ONE_TIME if t1 is None else ed._nearest(opts, t1),
            description="Take the pairs of every output from Time to this one")
        first = next(iter(F.defs))
        w["field"] = pn.widgets.Select(name="x field", groups=F.groups(), width=210,
                                       value=r["field"] if r["field"] in F else first)
        w["yfield"] = pn.widgets.Select(name="y field", groups=F.groups(), width=210,
                                        value=r["yfield"] if r["yfield"] in F else first)
        w["vmode"] = pn.widgets.Select(name="Vertical", options=DIST_VMODES, width=170,
                                       value=r["vmode"] if r["vmode"] in DIST_VMODES.values()
                                       else "height")
        w["z"] = _f("Height (km)", float(r.get("z", 1.0)), 90, step=0.25)
        w["z0"] = _f("Bottom (km)", float(r.get("z0", 0.0)), 90, step=0.5)
        w["z1"] = _f("Top (km)", float(r.get("z1", 10.0)), 80, step=0.5)
        w["region"] = pn.widgets.Select(name="Region", options=SER_REGIONS, value=r["region"],
                                        width=180)
        w["radius"] = _f("Radius (km)", float(r.get("radius", 5.0)), 90, step=0.5)
        off = r.get("offset") or (0.0, 0.0)
        w["offx"] = _f("Offset x (km)", float(off[0]), 100, step=1.0)
        w["offy"] = _f("Offset y (km)", float(off[1]), 100, step=1.0)
        for key, lab, desc in (("lo", "Only x from", "Keep pairs whose x is at or above "
                                "this (blank: no limit), e.g. 1 m/s for updrafts"),
                               ("hi", "to", ""),
                               ("ylo", "Only y from", "Keep pairs whose y is at or above "
                                "this (blank: no limit)"),
                               ("yhi", "to", "")):
            w[key] = FloatInput(  # (0 is a limit here, not blank)
                name=lab, value=r.get(key), placeholder="all",
                width=120 if key in ("lo", "ylo") else 90, **({"description": desc} if desc
                                                              else {}))
        w["label"] = pn.widgets.TextInput(name="Legend text (blank: automatic)",
                                          value=ent.get("label", ""), width=220)
        w["auto_color"] = _chk("Automatic colour", not ent.get("color"))
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(ent.get("color") or "k"),
                                            width=70)
        w["panel"] = pn.widgets.IntInput(name="Panel", start=1, end=64, width=70,
                                         value=int(ent.get("panel", 0)) + 1)
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k not in ("run", "panel"):
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: (self._show(), ed._fit_grid(), ed.request()), "value")
        self.title = pn.pane.HTML("<b>Joint</b>", margin=(6, 4, 0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [_grid(w["run"], (w["time"], 2), (w["time1"], 2), (w["field"], 2),
                   (w["yfield"], 2), w["vmode"], w["z"], w["z0"], w["z1"], w["region"],
                   w["radius"], w["offx"], w["offy"], w["lo"], w["hi"], w["ylo"], w["yhi"],
                   w["auto_color"], w["color"], w["panel"], (w["label"], 3)),
             _hint("The pairs of x and y values at the same points of the region (a 2D "
                   "field pairs at one height). Around the storm: a disc around each "
                   "run's track. A time window takes the pairs of all its outputs. "
                   "Automatic colour: the run's colour when each joint distribution of "
                   "the panel is from another run, else the next colour.")])
        self._show()

    @staticmethod
    def _to_opts(opts):
        return {"— (this time only)": ONE_TIME} | dict(opts)

    def _show(self):
        w = self.w
        F = self.ed.fields
        two = F[w["field"].value].ndim == 2 or F[w["yfield"].value].ndim == 2
        mode = w["vmode"].value
        w["vmode"].visible = not two
        w["z"].visible = two or mode == "height"
        w["z0"].visible = w["z1"].visible = not two and mode == "layer"
        trk = w["region"].value == "track"
        w["radius"].visible = w["offx"].visible = w["offy"].visible = trk
        w["color"].visible = not w["auto_color"].value
        when = next((k for k, v in w["time"].options.items() if v == w["time"].value), "")
        when = when.split("(")[-1].rstrip(")")
        if self._t1() is not None:
            to = next((k for k, v in w["time1"].options.items() if v == w["time1"].value), "")
            when += f" to {to.split('(')[-1].rstrip(')')}"
        self.title.object = (f"<b>Joint</b> · {F[w['yfield'].value].label} vs "
                             f"{F[w['field'].value].label} · {when} · panel "
                             f"{w['panel'].value}")

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
        w, F = self.w, self.ed.fields
        flat = [F[w[k].value].ndim == 2 for k in ("field", "yfield")]
        return joint.normalize(dict(
            field=w["field"].value, yfield=w["yfield"].value,
            vmode="2d" if all(flat) else "height" if any(flat) else w["vmode"].value,
            z=w["z"].value or 0.0, z0=w["z0"].value or 0.0, z1=w["z1"].value or 0.0,
            region=w["region"].value, radius=w["radius"].value or 5.0,
            offset=(w["offx"].value or 0.0, w["offy"].value or 0.0),
            box=self.box or [float(v) for v in self.ed.v.view],
            lo=_num(w["lo"].value), hi=_num(w["hi"].value),
            ylo=_num(w["ylo"].value), yhi=_num(w["yhi"].value)))

    def collect(self):
        w = self.w
        return dict(run=int(w["run"].value or 0), time_s=float(w["time"].value or 0.0),
                    time_s1=self._t1(), panel=max(0, int(w["panel"].value or 1) - 1),
                    label=w["label"].value,
                    color="" if w["auto_color"].value else w["color"].value,
                    recipe=self.recipe())
