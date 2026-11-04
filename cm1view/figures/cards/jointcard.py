"""The card of one joint distribution of a joint distribution figure."""

from ...core import joint
from ...viewer.numinput import FloatInput
from .base import (_num, _grid, _hint, TimeCard, card_body, field_widget,
                   label_widget, look_widgets, region_recipe,
                   region_widgets, show_region, vertical_recipe, vertical_widgets)
from .distcard import DIST_VMODES

JOINT_PLOTS = {"2D histogram": "hist", "Scatter": "scatter", "Density contours": "contour"}


class JointCard(TimeCard):
    """One joint distribution of a joint distribution figure: run, time (or a time
    window whose pairs are all taken), a joint recipe (x and y fields, height, layer or
    whole depth, region, value limits of each) and look."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.w = w = {}
        self._run_time_widgets("To (a time window)",
                               "Take the pairs of every output from Time to this one")
        w["field"] = field_widget(F, r["field"], "x field")
        w["yfield"] = field_widget(F, r["yfield"], "y field")
        vertical_widgets(w, r, DIST_VMODES, "height")
        region_widgets(self, r)
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
        w["label"] = label_widget(ent)
        look_widgets(w, ent, auto=True)
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k != "run":
                x.param.watch(lambda e: self._changed(), "value")
        self.body = card_body(
            _grid(w["run"], (w["time"], 2), (w["time1"], 2), w["hold"]),
            _grid((w["field"], 2), (w["yfield"], 2), w["vmode"], w["z"], w["z0"], w["z1"],
                  w["region"], w["radius"], w["offx"], w["offy"], w["lo"], w["hi"], w["ylo"],
                  w["yhi"], w["auto_color"], w["color"], (w["label"], 3)),
            _hint("The pairs of x and y values at the same points of the region (a 2D "
                  "field pairs at one height). Around the storm: a disc around each "
                  "run's track. A time window takes the pairs of all its outputs. "
                  "Automatic colour: the run's colour when each joint distribution of "
                  "the panel is from another run, else the next colour."))
        self._show()

    def _show(self):
        w = self.w
        F = self.ed.fields
        two = F[w["field"].value].ndim == 2 or F[w["yfield"].value].ndim == 2
        mode = w["vmode"].value
        w["vmode"].visible = not two
        w["z"].visible = two or mode == "height"
        w["z0"].visible = w["z1"].visible = not two and mode == "layer"
        show_region(w)
        w["color"].visible = not w["auto_color"].value

    def recipe(self):
        w, F = self.w, self.ed.fields
        flat = [F[w[k].value].ndim == 2 for k in ("field", "yfield")]
        return joint.normalize(dict(
            field=w["field"].value, yfield=w["yfield"].value,
            vmode="2d" if all(flat) else "height" if any(flat) else w["vmode"].value,
            **vertical_recipe(w), **region_recipe(self),
            lo=_num(w["lo"].value), hi=_num(w["hi"].value),
            ylo=_num(w["ylo"].value), yhi=_num(w["yhi"].value)))

    def collect(self):
        return dict(self._entry(), recipe=self.recipe())
