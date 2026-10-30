"""The card of one layer of a figure panel (Layers tab)."""

from types import SimpleNamespace

import panel as pn

from .. import draw as figdraw, spec as fg
from ...core import vectors
from ...core.fields import DERIVS, deriv_name, deriv_options, split_deriv
from .base import (
    FIG_CMAPS, LEVEL_MODES, FRAMES, HATCHES, TYPE_LABEL, REDUCE, GRIDS, EXTEND, AZ_REFS,
    AZ_CENTERS, _hex, _f, _grid, _hint, _checks, _fold, _near, _nice, _panels_parse, _panels_text,
    _chk, _load_widgets, _take_new_runs,
)
from ...viewer.ui import held

ENS_STATS = {"Mean": "mean", "Median": "median", "Spread (sd)": "sd", "Min": "min",
             "Max": "max", "Range (max − min)": "range",
             "Probability of exceeding (%)": "prob"}


class LayerCard:
    """Widgets of one layer (a card that folds away); collect() -> the layer dict."""

    def __init__(self, ed, lay, collapsed=False):
        self.ed, self.type = ed, lay["type"]
        self._loading = False  # (load: the widgets take another layer's settings)
        self._syncing = False  # (the Derivative list following the Field)
        F, g = ed.fields, ed.fields.groups()
        self.lay = dict(lay)
        self.w = w = {}
        w["on"] = pn.widgets.Checkbox(value=lay.get("on", True), width=20, margin=(8, 2, 0, 4))
        btn = dict(width=32, height=28, margin=(2, 1), button_type="default",
                   button_style="outline")
        self.up = pn.widgets.Button(name="↑", description="Draw earlier (below)", **btn)
        self.down = pn.widgets.Button(name="↓", description="Draw later (on top)", **btn)
        self.rm = pn.widgets.Button(name="✕", description="Remove the layer", **btn)
        t = self.type
        if t in ("fill", "contour", "shade"):
            op, base = split_deriv(lay["field"])
            w["field"] = pn.widgets.Select(name="Field", groups=g, value=base)
            dopts = self._deriv_opts(base)
            w["deriv"] = pn.widgets.Select(
                name="Derivative", options=dopts, value=op if op in dopts.values() else "",
                width=100, description="Plot a derivative of the field (per km): ∂/∂z on "
                "the model levels, ∂/∂x, ∂/∂y or the horizontal gradient's size on the "
                "grid")
            # (watched before the fill's colours: a 2D field has no ∂/∂z)
            w["field"].param.watch(self._on_base_field, "value")
            w["mode"] = pn.widgets.Select(name="Level", options=LEVEL_MODES,
                                          value=lay.get("mode", "height"))
            w["z"] = _f("Height (km)", lay.get("z", 1.0), step=0.25)
            r = lay.get("reduce") or {}
            topts = getattr(ed, "_time_opts", lambda k: {})(int(lay.get("run") or 0)) or {}
            w["reduce_op"] = pn.widgets.Select(name="Over a time window", options=REDUCE,
                                               value=r.get("op", ""))
            w["reduce_t0"] = pn.widgets.Select(
                name="From", options={"the run's first output": ""} | topts,
                value=_near(topts, r.get("t0")))
            w["reduce_t1"] = pn.widgets.Select(
                name="To", options={"the panel's time": ""} | topts,
                value=_near(topts, r.get("t1")))
            w["reduce_every"] = pn.widgets.IntInput(name="Every nth output",
                                                    value=int(r.get("every") or 1), start=1)
        if t in ("fill", "contour", "shade", "vectors"):
            w["z_fixed"] = _chk("Own height (not the panel's)", lay.get("z_fixed", False))
        if t == "fill":
            w["cmap"] = pn.widgets.Select(name="Colormap", options=FIG_CMAPS,
                                          value=lay["cmap"] if lay["cmap"] in FIG_CMAPS
                                          else "viridis")
            w["reverse"] = pn.widgets.Checkbox(name="Reverse", value=lay.get("reverse", False))
            w["white_first"] = pn.widgets.Checkbox(
                name="Start from white", value=lay.get("white_first", False))
            w["vmin"] = _f("Min", lay["vmin"])
            w["vmax"] = _f("Max", lay["vmax"])
            w["nlevels"] = pn.widgets.IntInput(name="Color steps (0: smooth)",
                                               value=int(lay.get("nlevels") or 0), start=0,
                                               end=60)
            w["scale"] = pn.widgets.Select(name="Scale", options={"Linear": "linear",
                                                                  "Logarithmic": "log"},
                                           value=lay.get("scale", "linear"))
            w["extend"] = pn.widgets.Select(name="Colorbar arrows", options=EXTEND,
                                            value=lay.get("extend", "neither"))
            w["alpha"] = _f("Opacity (0–1)", float(lay.get("alpha", 1.0)), step=0.1, start=0.0,
                            end=1.0)
            w["style"] = pn.widgets.Select(name="Draw as", options={
                "Grid cells": "mesh", "Filled contours": "contourf"},
                value=lay.get("style", "mesh"))
            w["mask_below"] = pn.widgets.TextInput(
                name="Blank where ≤", value="" if lay.get("mask_below") is None
                else f"{lay['mask_below']:g}", placeholder="off")
            w["cbar_label"] = pn.widgets.TextInput(
                name="Colorbar label (blank: units)", value=lay.get("cbar_label", "") or "",
                placeholder=lay.get("units", ""))
            w["cbar_ticks"] = pn.widgets.TextInput(
                name="Colorbar ticks (blank: auto)", value=lay.get("cbar_ticks", "") or "",
                placeholder="0:60:10")
            m = lay.get("minus") or {}
            w["minus_on"] = _chk("Difference: minus another run or time", bool(lay.get("minus")))
            try:
                runs = {"the layer's": -1} | ed._run_names()
            except AttributeError:  # (no run list yet)
                runs = {"the layer's": -1}
            w["minus_run"] = pn.widgets.Select(
                name="Minus run", options=runs,
                value=int(m["run"]) if m.get("run") is not None and int(m["run"]) in
                runs.values() else -1)
            w["minus_time"] = pn.widgets.Select(name="Minus time", options={"the layer's": ""})
            self._minus_times(m.get("time_s"))
            w["minus_grid"] = pn.widgets.Select(name="If the grids differ", options=GRIDS,
                                                value=m.get("grid", "ask"))
            en = lay.get("ens") or {}
            w["ens_on"] = _chk("Ensemble: a statistic over several runs", bool(en))
            try:
                ropts = ed._series_run_opts()
            except AttributeError:  # (no run list yet)
                ropts = {}
            w["ens_runs"] = pn.widgets.MultiChoice(
                name="Runs (blank: all)", options=ropts, width=260,
                value=[int(k) for k in (en.get("runs") or []) if int(k) in ropts.values()])
            w["ens_stat"] = pn.widgets.Select(name="Statistic", options=ENS_STATS,
                                              value=en.get("stat", "mean"))
            w["ens_thr"] = _f("Threshold", float(en.get("threshold", 0.0)))
            w["ens_above"] = pn.widgets.Select(name="Where the value is", options={
                "Above": True, "Below": False}, value=bool(en.get("above", True)))
            w["ens_grid"] = pn.widgets.Select(name="If the grids differ", options=GRIDS,
                                              value=en.get("grid", "ask"))
            w["field"].param.watch(self._on_fill_field, "value")
            w["deriv"].param.watch(self._on_fill_field, "value")
            w["minus_on"].param.watch(self._on_minus, "value")
            w["ens_on"].param.watch(self._on_ens, "value")
            w["ens_stat"].param.watch(self._on_ens, "value")
            w["ens_runs"].param.watch(self._on_ens_runs, "value")
            w["minus_run"].param.watch(
                lambda e: None if self._loading else
                self._minus_times(w["minus_time"].value or None), "value")
        if t == "contour":
            w["levels"] = pn.widgets.TextInput(name="Levels (e.g. 10, 20 or -6:6:2)",
                                               value=str(lay["levels"]))
            w["neg_dashed"] = pn.widgets.Checkbox(name="Dash negative",
                                                  value=lay.get("neg_dashed", True))
            w["clabel"] = pn.widgets.Checkbox(name="Label the lines",
                                              value=lay.get("clabel", False))
            w["clabel_size"] = _f("Label size (pt)", float(lay.get("clabel_size") or 8.0),
                                  step=1, start=4)
            w["clabel_fmt"] = pn.widgets.TextInput(name="Label format",
                                                   value=lay.get("clabel_fmt") or "%g",
                                                   placeholder="%g")
        if t == "shade":
            w["threshold"] = _f("Threshold", lay["threshold"])
            w["above"] = pn.widgets.Select(name="Shade", options={"Above": True, "Below": False},
                                           value=lay.get("above", True))
            w["alpha"] = _f("Opacity (0–1)", lay.get("alpha", 0.6), step=0.1, start=0, end=1)
            w["hatch"] = pn.widgets.Select(name="Pattern", options=HATCHES,
                                           value=lay.get("hatch") or "")
            w["hatch_lw"] = _f("Pattern line width", float(lay.get("hatch_lw", 0.6)),
                               step=0.1, start=0.1)
            w["outline_on"] = pn.widgets.Checkbox(name="Outline", value=bool(lay.get("outline")))
            w["outline"] = pn.widgets.ColorPicker(name="Outline color",
                                                  value=_hex(lay.get("outline") or "magenta"))
        if t == "vectors":
            opts = vectors.options(F)
            q = lay.get("vector", "wind")
            w["vector"] = pn.widgets.Select(name="Vector", options=opts,
                                            value=q if q in opts.values() else "wind")
            w["style"] = pn.widgets.Select(name="Draw as", options={
                "Arrows": "arrows", "Barbs (plan views)": "barbs",
                "Streamlines": "streamlines"}, value=lay.get("style", "arrows"))
            w["frame"] = pn.widgets.Select(name="Frame", options=FRAMES,
                                           value=lay.get("frame", "ground"))
            w["z"] = _f("Height (km)", lay.get("z", 0.0), step=0.25)
            w["spacing"] = _f("Spacing (km)", lay.get("spacing", 2.0), step=0.25)
            w["zspacing"] = _f("Vertical spacing (km)", lay.get("zspacing", 0.5), step=0.1)
            w["scale"] = _f("Scale (larger: shorter)", lay.get("scale", 250.0), step=25)
            w["width"] = _f("Arrow width", lay.get("width", 0.002), step=0.0005)
            w["key"] = _f("Key arrow (m/s, 0: none)", lay.get("key", 0.0), step=5)
            w["density"] = _f("Density", float(lay.get("density", 1.5)), step=0.25, start=0.25)
            w["slw"] = _f("Line width", float(lay.get("slw", 0.8)), step=0.1)
            w["arrowsize"] = _f("Arrow size", float(lay.get("arrowsize", 1.0)), step=0.25)
            w["barb_len"] = _f("Barb length", float(lay.get("barb_len", 5.5)), step=0.5,
                               start=2)
            w["barb_units"] = pn.widgets.Select(name="Barbs in", options={
                "knots": "kt", "m/s": "ms"}, value=lay.get("barb_units", "kt"))
        if t == "sector":  # (as an azimuthal mean panel's sector)
            w["center"] = pn.widgets.Select(name="Centre", options=AZ_CENTERS,
                                            value=lay.get("center", "track"))
            for k, lab, v, st in (("offx", "Offset x (km)", 0.0, 1.0),
                                  ("offy", "Offset y (km)", 0.0, 1.0),
                                  ("cx", "x (km)", 0.0, 1.0), ("cy", "y (km)", 0.0, 1.0),
                                  ("az0", "Azimuth from (°)", 0.0, 15.0),
                                  ("az1", "to (°)", 360.0, 15.0),
                                  ("rmax", "Radius (km)", 20.0, 1.0)):
                w[k] = _f(lab, float(lay.get(k, v)), step=st)
            w["ref"] = pn.widgets.Select(name="Azimuth 0", options=AZ_REFS,
                                         value=lay.get("ref", "motion"))
        if t in ("contour", "shade", "vectors", "track", "line", "sector"):
            w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(lay.get("color", "k")))
        if t in ("contour", "shade", "track", "line", "sector"):
            w["lw"] = _f("Outline width" if t == "shade" else "Line width", lay.get("lw", 1.0),
                         step=0.25)
        if t in ("track", "sector"):
            w["ls"] = pn.widgets.Select(name="Style", options={"solid": "-", "dashed": "--",
                                                               "dotted": ":"},
                                        value=lay.get("ls", "-"))
        if t == "track":
            w["run_color"] = _chk("Run's colour", lay.get("run_color", False))
            w["marker"] = pn.widgets.Checkbox(name="Dot at the panel time",
                                              value=lay.get("marker", True))
        if t == "line":
            w["labels"] = pn.widgets.TextInput(
                name="End labels", value=lay.get("labels", ""),
                description="The first section's ends; the others step on (A, A′ → B, B′)")
            w["which"] = pn.widgets.Select(name="Sections", options={
                "All, labelled in turn": "all", "The panel's own": "panel"},
                value=lay.get("which", "all"))
        if t in ("contour", "shade", "track", "line", "sector"):
            w["legend"] = pn.widgets.TextInput(name="Legend entry (blank: none)",
                                               value=lay.get("legend", ""),
                                               placeholder="e.g. w = 10, 20 m s⁻¹")
        names = ed._run_names()
        k = lay.get("run")
        w["run"] = pn.widgets.Select(
            name="Run", value=int(k) if k is not None and int(k) in names.values() else -1,
            width=170, **ed._layer_run_choices(names))
        w["panels"] = pn.widgets.TextInput(
            name="In panels (blank: all)", value=_panels_text(lay.get("panels")),
            placeholder="e.g. a, c or 1-3",
            description="Draw this layer only in these panels (letters or numbers)")
        if t == "vectors":
            w["vector"].param.watch(self._on_vector, "value")
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k != "run" and (k not in ("field", "deriv", "minus_on", "ens_on", "ens_stat",
                                         "ens_runs") or t != "fill"):
                x.param.watch(lambda e: self._changed(), "value")
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self._set_title()
        self.panel, self.body = _fold([w["on"], self.title, pn.Spacer(), self.up, self.down,
                                       self.rm], self._layout(), collapsed)
        self.show(ed.kind.value)

    def load(self, lay, collapsed=False):
        """Show layer lay (of this card's type) in these widgets: a new figure keeps its
        cards, which the browser already has, instead of building new ones."""
        new = LayerCard(self.ed, lay, collapsed)  # (never shown: its settings)
        self._loading = True
        try:
            _load_widgets(self.w, new.w)
        finally:
            self._loading = False
        self.lay = new.lay
        if self.body.visible == collapsed:
            self.panel.objects[0].objects[0].clicks += 1  # (the chevron: fold / unfold)
        self.show(self.ed.kind.value)
        self._set_title()

    def _layout(self):
        return [_grid(self.w["run"])] + self._rows()

    def _deriv_opts(self, base):
        F = self.ed.fields
        return deriv_options(F[base]) if base in F else {"None": ""} | \
            {v: k for k, v in DERIVS.items()}

    def field_name(self):
        """The layer's field: the Field, or its Derivative (fields.deriv_name)."""
        return deriv_name(self.w["deriv"].value, self.w["field"].value)

    def _on_base_field(self, ev):
        """Another Field: the derivatives it has (a 2D field: no ∂/∂z)."""
        if self._loading:
            return
        dw = self.w["deriv"]
        opts = self._deriv_opts(ev.new)
        if opts != dw.options:
            self._syncing = True
            try:
                v = dw.value
                dw.options = opts
                dw.value = v if v in opts.values() else ""
            finally:
                self._syncing = False

    def _on_run(self, ev):
        if self.ed._hold or self._loading:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
            return
        w = self.w
        if "reduce_t0" in w:  # (the window's times are the layer's run's)
            topts = self.ed._time_opts(ev.new if ev.new != -1 else 0) or {}
            with held(self.ed):
                for k, first in (("reduce_t0", "the run's first output"),
                                 ("reduce_t1", "the panel's time")):
                    cur = w[k].value
                    w[k].options = {first: ""} | topts
                    w[k].value = "" if cur == "" else _near(topts, cur)
        self._changed()

    def _rows(self):
        w, t = self.w, self.type
        if t == "fill":
            return [_grid((w["field"], 2), w["deriv"], w["mode"], w["z"], w["z_fixed"],
                          w["style"], w["mask_below"]),
                    _grid(w["cmap"], w["reverse"], w["white_first"], w["vmin"], w["vmax"],
                          w["nlevels"], w["scale"], w["extend"], w["alpha"],
                          (w["cbar_label"], 2), w["cbar_ticks"], (w["panels"], 3)),
                    _grid((w["minus_on"], 2), w["minus_run"], w["minus_time"],
                          w["minus_grid"]),
                    _grid((w["ens_on"], 2), (w["ens_runs"], 2), w["ens_stat"], w["ens_thr"],
                          w["ens_above"], w["ens_grid"]),
                    _hint("Ensemble: the field of each of the runs at the layer's time "
                          "(the layer's Run is not used), combined cell by cell; runs "
                          "without output at that time are left out."),
                    self._reduce_row()]
        if t == "contour":
            return [_grid((w["field"], 2), w["deriv"], w["mode"], w["z"], w["z_fixed"],
                          (w["levels"], 2),
                          w["color"], w["lw"], w["clabel_size"], w["clabel_fmt"],
                          (w["legend"], 3), (w["panels"], 3)),
                    self._reduce_row(), _checks(w["clabel"], w["neg_dashed"], title="Options")]
        if t == "shade":
            return [_grid((w["field"], 2), w["deriv"], w["mode"], w["z"], w["z_fixed"],
                          w["threshold"],
                          w["above"], w["hatch"], w["hatch_lw"],
                          w["color"], w["alpha"], w["outline_on"], w["outline"], w["lw"],
                          (w["legend"], 3), (w["panels"], 3)),
                    self._reduce_row()]
        if t == "vectors":
            return [_grid((w["vector"], 2), w["style"], w["frame"], w["color"], w["z"],
                          w["z_fixed"], w["spacing"],
                          w["zspacing"], w["scale"], w["width"], w["key"], w["density"],
                          w["slw"], w["arrowsize"], w["barb_len"], w["barb_units"],
                          (w["panels"], 3))]
        if t == "track":
            return [_grid(w["run_color"], w["color"], w["lw"], w["ls"],
                          (w["legend"], 3), (w["panels"], 3)), _checks(w["marker"])]
        if t == "sector":
            return [_grid((w["center"], 2), w["offx"], w["offy"], w["cx"], w["cy"],
                          (w["ref"], 2), w["az0"], w["az1"], w["rmax"], w["color"], w["lw"],
                          w["ls"], (w["legend"], 3), (w["panels"], 3)),
                    _hint("The sector of an azimuthal mean panel, at each panel's time: "
                          "azimuths clockwise from the storm's motion (its track's) or "
                          "from north, from the first to the second (0 to 360: a circle). "
                          "Give it the settings of the azimuthal mean it shows.")]
        return [_grid(w["which"], w["color"], w["lw"], w["labels"], (w["legend"], 3),
                      (w["panels"], 3))]

    def _reduce_row(self):
        w = self.w
        return _grid((w["reduce_op"], 2), w["reduce_t0"], w["reduce_t1"], w["reduce_every"])

    def show(self, kind):
        """Only the settings that matter for this layer in `kind` panels (a section
        samples the fields along the section, at every height)."""
        w, t, xs = self.w, self.type, kind == "xsec"
        by_z = self.ed._uses("heights") and not xs  # panels at their own heights
        if "mode" in w:
            m = w["mode"].value
            w["mode"].visible = not xs
            w["z_fixed"].visible = by_z and m == "height"
            w["z"].visible = not xs and m in ("height", "level") and (
                m == "level" or not by_z or w["z_fixed"].value)
            w["z"].name = "Model level (k)" if m == "level" else "Height (km)"
            w["reduce_op"].visible = not xs  # (plan panels only)
            for k in ("reduce_t0", "reduce_t1", "reduce_every"):
                w[k].visible = not xs and bool(w["reduce_op"].value)
        if t == "vectors":
            st = w["style"].value == "streamlines"
            barbs = w["style"].value == "barbs" and not xs
            for k in ("density", "arrowsize"):
                w[k].visible = st
            w["slw"].visible = st or barbs
            for k in ("scale", "width", "key"):
                w[k].visible = not st and not barbs
            w["barb_len"].visible = barbs
            w["barb_units"].visible = barbs and w["vector"].value == "wind"
            w["z_fixed"].visible = by_z
            w["z"].visible = not xs and (not by_z or w["z_fixed"].value)
            w["spacing"].visible = not st
            w["spacing"].name = "Spacing along (km)" if xs else "Spacing (km)"
            w["zspacing"].visible = xs and not st
            w["frame"].visible = vectors.VECTORS[w["vector"].value].framed
            w["key"].name = f'Key arrow ({vectors.VECTORS[w["vector"].value].units}, 0: none)'
        if t == "shade":
            w["outline"].visible = w["lw"].visible = w["outline_on"].value
            w["hatch_lw"].visible = bool(w["hatch"].value)
        if t == "track":  # (each panel's run's colour: Layers → Runs used)
            w["color"].visible = not w["run_color"].value
        if t == "sector":
            pt = w["center"].value == "point"
            w["cx"].visible = w["cy"].visible = pt
            w["offx"].visible = w["offy"].visible = not pt
        if t == "contour":
            w["clabel_size"].visible = w["clabel_fmt"].visible = w["clabel"].value
        if t == "fill":
            w["white_first"].visible = True
            ens = w["ens_on"].value
            w["minus_on"].visible = not ens
            for k in ("minus_run", "minus_time", "minus_grid"):
                w[k].visible = w["minus_on"].value and not ens
            for k in ("ens_runs", "ens_stat", "ens_grid"):
                w[k].visible = ens
            w["ens_thr"].visible = w["ens_above"].visible = \
                ens and w["ens_stat"].value == "prob"
            w["run"].visible = not ens

    def _on_vector(self, ev):
        """Another vector: arrows scaled for its magnitudes (a key arrow of its typical
        one, when there is a key)."""
        d, w = vectors.VECTORS[ev.new], self.w
        if self._loading:
            return
        w["scale"].value = vectors.FIG_SCALE * d.ref
        if w["key"].value:
            w["key"].value = d.ref

    def _changed(self):
        if self._loading:
            return
        self.show(self.ed.kind.value)
        self._set_title()
        if self.type == "line":
            self.ed._show_region()  # (the section settings show while a line is on)
        self.ed.request()

    def _set_title(self):
        t, w = self.type, self.w
        sub = ""
        if "field" in w:
            d = self.ed.fields[self.field_name()]
            sub = f" · {d.label}"
            m = w["mode"].value
            if self.ed.kind.value != "xsec":
                z = w["z"].value or 0
                own = self.ed._uses("heights") and not w["z_fixed"].value
                sub += {"height": " · the panel's height" if own else f" · {z:g} km",
                        "level": f" · k = {z:g}",
                        "colmax": " · column max", "colmin": " · column min"}.get(m, "")
            if w["reduce_op"].value and self.ed.kind.value != "xsec":
                sub += {"composite": " · storm-following mean"}.get(
                    w["reduce_op"].value, f" · {w['reduce_op'].value} over a time window")
            if t == "fill" and w["ens_on"].value:
                sub += f" · ensemble {w['ens_stat'].value}"
            elif t == "fill" and w["minus_on"].value:
                sub += " · difference"
        elif t == "sector":
            a0, a1 = w["az0"].value or 0.0, w["az1"].value
            a1 = 360.0 if a1 is None else a1
            sub = (f" · {a0:g}–{a1:g}° from "
                   f"{'motion' if w['ref'].value == 'motion' else 'north'}"
                   f" · {w['rmax'].value or 0:g} km")
        elif t == "vectors":
            sub = (f' · {vectors.VECTORS[w["vector"].value].label}'
                   + {"streamlines": " · streamlines", "barbs": " · barbs"}.get(
                       w["style"].value, " · arrows"))
        try:
            only = _panels_parse(w["panels"].value)
        except ValueError:  # (collect() reports it)
            only = []
        if only:
            sub += " · panel" + ("s " if len(only) > 1 else " ") + ", ".join(
                figdraw.panel_letter(i, "{a}") for i in only)
        self.title.object = f"<b>{TYPE_LABEL[t]}</b>{sub}"

    def _on_fill_field(self, ev):
        """New fill field: its default colours, range and units."""
        if self._loading:
            return
        if self._syncing:  # (the Derivative list following the Field)
            return
        d = fg.layer_defaults("fill", self.ed.fields, self.field_name())
        self.lay["units"] = d["units"]
        with held(self.ed):
            for k in ("cmap", "vmin", "vmax", "extend"):
                self.w[k].value = d[k] if k != "cmap" or d[k] in FIG_CMAPS else "viridis"
            self.w["mask_below"].value = "" if d["mask_below"] is None else f"{d['mask_below']:g}"
            self.w["cbar_label"].placeholder = d["units"]
        if self.w["ens_on"].value:  # (an ensemble: its statistic's colours)
            self._on_ens(None)
            return
        if self.w["minus_on"].value:  # (a difference: diverging, from the new range)
            self._on_minus(SimpleNamespace(new=True))
            return
        self._changed()

    def _minus_times(self, ts):
        """The Minus time list: the times of the Minus run (else the first run), at the
        time nearest ts ("" / None: the layer's)."""
        w = self.w
        k = w["minus_run"].value if w["minus_run"].value != -1 else 0
        opts = {"the layer's": ""} | (getattr(self.ed, "_time_opts", lambda k: {})(k) or {})
        vals = [v for v in opts.values() if v != ""]
        w["minus_time"].options = opts
        w["minus_time"].value = "" if ts in (None, "") or not vals else \
            min(vals, key=lambda v: abs(v - float(ts)))

    def _on_minus(self, ev):
        """Difference on: a diverging colormap centred on 0, nothing blanked; off: the
        field's own colours."""
        w = self.w
        if self._loading:
            return
        d = fg.layer_defaults("fill", self.ed.fields, self.field_name())
        with held(self.ed):
            if ev.new:
                a = _nice(0.25 * (float(w["vmax"].value) - float(w["vmin"].value)))
                vals = dict(cmap="RdBu", reverse=True, white_first=False, vmin=-a, vmax=a,
                            scale="linear", mask_below="")
            else:
                vals = dict(cmap=d["cmap"] if d["cmap"] in FIG_CMAPS else "viridis",
                            reverse=False, vmin=d["vmin"], vmax=d["vmax"],
                            mask_below="" if d["mask_below"] is None else f"{d['mask_below']:g}")
            for k, v in vals.items():
                w[k].value = v
        self._changed()

    def _on_ens(self, ev):
        """Ensemble on or another statistic: its colours (a probability 0–100 %, a
        spread or range from 0, else the field's own); off: the field's own."""
        w = self.w
        if self.ed._hold or self._loading:
            return
        if ev is not None and ev.obj is w["ens_stat"] and not w["ens_on"].value:
            self._changed()
            return
        d = fg.layer_defaults("fill", self.ed.fields, self.field_name())
        own = dict(cmap=d["cmap"] if d["cmap"] in FIG_CMAPS else "viridis", reverse=False,
                   vmin=d["vmin"], vmax=d["vmax"],
                   mask_below="" if d["mask_below"] is None else f"{d['mask_below']:g}")
        st = w["ens_stat"].value
        if not w["ens_on"].value:
            vals = own
        elif st == "prob":
            vals = dict(cmap="Blues", reverse=False, white_first=True, vmin=0.0, vmax=100.0,
                        scale="linear", mask_below="0", nlevels=10, extend="neither")
        elif st in ("sd", "range"):
            a = _nice((0.25 if st == "sd" else 0.5) * (float(d["vmax"]) - float(d["vmin"])))
            vals = dict(cmap="viridis", reverse=False, white_first=False, vmin=0.0, vmax=a,
                        scale="linear", mask_below="")
        else:
            vals = own
        with held(self.ed):
            if w["ens_on"].value:
                w["minus_on"].value = False
            for k, v in vals.items():
                w[k].value = v
        self._changed()

    def _on_ens_runs(self, ev):
        """A run not in the figure picked (its path): add it, and keep it picked."""
        if self.ed._hold or self._loading:
            return
        _take_new_runs(self.ed, self.w["ens_runs"], ev.new)
        self._changed()

    def collect(self):
        w, lay = self.w, dict(self.lay)
        for k, x in w.items():
            if k in ("outline_on",) or k.startswith(("minus_", "reduce_", "ens_")):
                continue
            lay[k] = x.value
        if "deriv" in lay:
            lay["field"] = deriv_name(lay.pop("deriv"), lay["field"])
        lay.pop("run", None)
        if w["run"].value != -1:
            lay["run"] = int(w["run"].value)
        if "reduce_op" in w:
            lay.pop("reduce", None)
            if w["reduce_op"].value:
                t0, t1 = w["reduce_t0"].value, w["reduce_t1"].value
                lay["reduce"] = dict(op=w["reduce_op"].value,
                                     t0=None if t0 == "" else float(t0),
                                     t1=None if t1 == "" else float(t1),
                                     every=max(1, int(w["reduce_every"].value or 1)))
        if self.type == "fill":
            lay.pop("minus", None)
            lay.pop("ens", None)
            if w["ens_on"].value:
                ks = [int(k) for k in w["ens_runs"].value if not isinstance(k, str)]
                lay["ens"] = dict(runs=sorted(ks) or None, stat=w["ens_stat"].value,
                                  threshold=float(w["ens_thr"].value or 0.0),
                                  above=bool(w["ens_above"].value), grid=w["ens_grid"].value)
            elif w["minus_on"].value:
                r, ts = w["minus_run"].value, w["minus_time"].value
                lay["minus"] = dict(run=None if r == -1 else int(r),
                                    time_s=None if ts == "" else float(ts),
                                    grid=w["minus_grid"].value)
            mb = str(w["mask_below"].value).strip()
            try:
                lay["mask_below"] = float(mb) if mb else None
            except ValueError:
                lay["mask_below"] = None
            lay["units"] = self.ed.fields[lay["field"]].units
            lay["alpha"] = float(w["alpha"].value if w["alpha"].value is not None else 1.0)
        if self.type == "shade":
            lay["outline"] = w["outline"].value if w["outline_on"].value else ""
        lay["panels"] = _panels_parse(w["panels"].value)
        return lay
