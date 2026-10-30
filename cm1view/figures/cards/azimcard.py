"""The card of one azimuthal mean of an azimuthal mean figure."""

import panel as pn

from ...core import azim
from ...viewer.numinput import FloatInput
from .base import (_hex, _f, _grid, _hint, _fold, AZ_REFS, AZ_CENTERS, _BTN, _chk,
                   TimeCard)

AZ_OPS = {"Mean": "mean", "Maximum": "max", "Minimum": "min"}


class AzimCard(TimeCard):
    """One azimuthal mean of an azimuthal mean figure: run, time (or a time window it
    is a composite of), an azimuthal mean recipe (field, centre, sector, radius, layer,
    reduction), look and panel."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.w = w = {}
        self.rm = pn.widgets.Button(name="✕", description="Remove the azimuthal mean", **_BTN)
        names = ed._run_names()
        k = int(ent.get("run", 0)) if int(ent.get("run", 0)) in names.values() else 0
        w["run"] = pn.widgets.Select(name="Run", value=k, width=170, **ed._run_choices(names))
        opts = ed._time_opts(k)
        self._time_widgets(opts, "Composite to (a time window)",
                           "Every output from Time to this one, each around its own centre")
        field = r["field"] if r["field"] in F else next(iter(F.defs))
        w["field"] = pn.widgets.Select(name="Field", groups=F.groups(), value=field, width=210)
        w["op"] = pn.widgets.Select(name="Reduce", options=AZ_OPS, value=r["op"], width=110)
        w["center"] = pn.widgets.Select(name="Centre", options=AZ_CENTERS, value=r["center"],
                                        width=210)
        off = r.get("offset") or (0.0, 0.0)
        w["offx"] = _f("Offset x (km)", float(off[0]), 100, step=1.0)
        w["offy"] = _f("Offset y (km)", float(off[1]), 100, step=1.0)
        pt = r.get("point") or (0.0, 0.0)
        w["px"] = _f("x (km)", float(pt[0]), 90, step=1.0)
        w["py"] = _f("y (km)", float(pt[1]), 90, step=1.0)
        w["ref"] = pn.widgets.Select(name="Azimuth 0", options=AZ_REFS, value=r["ref"],
                                     width=230)
        w["az0"] = _f("Azimuth from (°)", float(r["az0"]), 110, step=15.0)
        w["az1"] = _f("to (°)", float(r["az1"]), 80, step=15.0)
        w["rmax"] = _f("Radius (km)", float(r["rmax"]), 90, step=1.0)
        w["dr"] = FloatInput(name="Bin width (km)", value=r.get("dr"), placeholder="grid",
                             width=100, description="Blank: the grid spacing")
        w["z0"] = _f("Bottom (km)", float(r["z0"]), 90, step=0.5)
        w["z1"] = _f("Top (km)", float(r["z1"]), 80, step=0.5)
        w["label"] = pn.widgets.TextInput(name="Legend text (blank: automatic)",
                                          value=ent.get("label", ""), width=220)
        w["levels"] = pn.widgets.TextInput(name="Contour levels (blank: auto)",
                                           value=ent.get("levels", ""), width=170,
                                           placeholder="e.g. 5, 10 or -6:6:2")
        w["auto_color"] = _chk("Automatic colour", not ent.get("color"))
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(ent.get("color") or "k"),
                                            width=70)
        w["lw"] = _f("Line width", float(ent.get("lw") or 1.0), 90, step=0.25)
        w["panel"] = pn.widgets.IntInput(name="Panel", start=1, end=64, width=70,
                                         value=int(ent.get("panel", 0)) + 1)
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k not in ("run", "panel"):
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: (self._show(), ed._fit_grid(), ed.request()), "value")
        self.title = pn.pane.HTML("<b>Azimuthal</b>", margin=(6, 4, 0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [_grid(w["run"], (w["time"], 2), (w["time1"], 2), (w["field"], 2), w["op"],
                   (w["center"], 2), w["offx"], w["offy"], w["px"], w["py"], (w["ref"], 2),
                   w["az0"], w["az1"], w["rmax"], w["dr"], w["z0"], w["z1"], w["panel"],
                   (w["label"], 3)),
             _grid(w["levels"], w["auto_color"], w["color"], w["lw"]),
             _hint("The field reduced over rings around the centre, in bins of radius at "
                   "every model level from Bottom to Top, within the sector: azimuths "
                   "clockwise from the storm's motion (its track's; the domain's without "
                   "one) or from north, from the first to the second (0 to 360: the whole "
                   "ring; 0 to 90: the front-right quadrant). A time window is a "
                   "composite, each output around its own centre. The panel's first is "
                   "shaded; the others are contour lines (levels, colour and width "
                   "below).")])
        self._show()

    def _show(self):
        w = self.w
        pt = w["center"].value == "point"
        w["px"].visible = w["py"].visible = pt
        w["offx"].visible = w["offy"].visible = not pt
        w["color"].visible = not w["auto_color"].value
        d = self.ed.fields[w["field"].value]
        two = " · <i>a 3D field is needed</i>" if d.ndim == 2 else ""
        self.title.object = (f"<b>Azimuthal</b> · {d.label} · {self._when()} · panel "
                             f"{w['panel'].value}{two}")

    def recipe(self):
        w = self.w
        a1 = w["az1"].value
        return azim.normalize(dict(
            field=w["field"].value, op=w["op"].value, center=w["center"].value,
            offset=(w["offx"].value or 0.0, w["offy"].value or 0.0),
            point=(w["px"].value or 0.0, w["py"].value or 0.0), ref=w["ref"].value,
            az0=w["az0"].value or 0.0, az1=360.0 if a1 is None else a1,
            rmax=w["rmax"].value or 20.0, dr=w["dr"].value, z0=w["z0"].value or 0.0,
            z1=w["z1"].value or 15.0))

    def collect(self):
        w = self.w
        return dict(self._entry(), lw=float(w["lw"].value or 1.0),
                    levels=w["levels"].value.strip(), recipe=self.recipe())
