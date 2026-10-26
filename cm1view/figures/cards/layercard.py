"""The card of one layer of a figure panel (Layers tab)."""

from types import SimpleNamespace

import panel as pn

from .. import draw as figdraw, spec as fg
from ...core import vectors
from .base import (
    FIG_CMAPS, LEVEL_MODES, FRAMES, HATCHES, TYPE_LABEL, REDUCE, GRIDS, EXTEND, _hex, _f, _grid,
    _checks, _fold, _near, _nice, _panels_parse, _panels_text, _chk,
)


class LayerCard:
    """Widgets of one layer (a card that folds away); collect() -> the layer dict."""

    def __init__(self, ed, lay, collapsed=False):
        self.ed, self.type = ed, lay["type"]
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
            w["field"] = pn.widgets.Select(name="Field", groups=g, value=lay["field"])
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
            w["field"].param.watch(self._on_fill_field, "value")
            w["minus_on"].param.watch(self._on_minus, "value")
            w["minus_run"].param.watch(lambda e: self._minus_times(w["minus_time"].value or None),
                                       "value")
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
        if t in ("contour", "shade", "vectors", "track", "line"):
            w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(lay.get("color", "k")))
        if t in ("contour", "shade", "track", "line"):
            w["lw"] = _f("Outline width" if t == "shade" else "Line width", lay.get("lw", 1.0),
                         step=0.25)
        if t == "track":
            w["run_color"] = _chk("Run's colour", lay.get("run_color", False))
            w["ls"] = pn.widgets.Select(name="Style", options={"solid": "-", "dashed": "--",
                                                               "dotted": ":"},
                                        value=lay.get("ls", "-"))
            w["marker"] = pn.widgets.Checkbox(name="Dot at the panel time",
                                              value=lay.get("marker", True))
        if t == "line":
            w["labels"] = pn.widgets.TextInput(name="End labels", value=lay.get("labels", ""))
        if t in ("contour", "shade", "track", "line"):
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
            if k != "run" and (k not in ("field", "minus_on") or t != "fill"):
                x.param.watch(lambda e: self._changed(), "value")
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self._set_title()
        self.panel, self.body = _fold([w["on"], self.title, pn.Spacer(), self.up, self.down,
                                       self.rm], self._layout(), collapsed)
        self.show(ed.kind.value)

    def _layout(self):
        return [_grid(self.w["run"])] + self._rows()

    def _on_run(self, ev):
        if self.ed._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
            return
        w = self.w
        if "reduce_t0" in w:  # (the window's times are the layer's run's)
            topts = self.ed._time_opts(ev.new if ev.new != -1 else 0) or {}
            self.ed._hold = True
            try:
                for k, first in (("reduce_t0", "the run's first output"),
                                 ("reduce_t1", "the panel's time")):
                    cur = w[k].value
                    w[k].options = {first: ""} | topts
                    w[k].value = "" if cur == "" else _near(topts, cur)
            finally:
                self.ed._hold = False
        self._changed()

    def _rows(self):
        w, t = self.w, self.type
        if t == "fill":
            return [_grid((w["field"], 2), w["mode"], w["z"], w["z_fixed"], w["style"],
                          w["mask_below"]),
                    _grid(w["cmap"], w["reverse"], w["white_first"], w["vmin"], w["vmax"],
                          w["nlevels"], w["scale"], w["extend"], w["alpha"],
                          (w["cbar_label"], 2), w["cbar_ticks"], (w["panels"], 3)),
                    _grid((w["minus_on"], 2), w["minus_run"], w["minus_time"],
                          w["minus_grid"]), self._reduce_row()]
        if t == "contour":
            return [_grid((w["field"], 2), w["mode"], w["z"], w["z_fixed"], (w["levels"], 2),
                          w["color"], w["lw"], w["clabel_size"], w["clabel_fmt"],
                          (w["legend"], 3), (w["panels"], 3)),
                    self._reduce_row(), _checks(w["clabel"], w["neg_dashed"], title="Options")]
        if t == "shade":
            return [_grid((w["field"], 2), w["mode"], w["z"], w["z_fixed"], w["threshold"],
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
        return [_grid(w["color"], w["lw"], w["labels"], (w["legend"], 3), (w["panels"], 3))]

    def _reduce_row(self):
        w = self.w
        return _grid((w["reduce_op"], 2), w["reduce_t0"], w["reduce_t1"], w["reduce_every"])

    def show(self, kind):
        """Only the settings that matter for this layer in `kind` panels (a section
        samples the fields along the section, at every height)."""
        w, t, xs = self.w, self.type, kind == "xsec"
        by_z = self.ed.vary.value == "height" and not xs  # panels at their own heights
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
        if t == "contour":
            w["clabel_size"].visible = w["clabel_fmt"].visible = w["clabel"].value
        if t == "fill":
            w["white_first"].visible = True
            for k in ("minus_run", "minus_time", "minus_grid"):
                w[k].visible = w["minus_on"].value

    def _on_vector(self, ev):
        """Another vector: arrows scaled for its magnitudes (a key arrow of its typical
        one, when there is a key)."""
        d, w = vectors.VECTORS[ev.new], self.w
        w["scale"].value = vectors.FIG_SCALE * d.ref
        if w["key"].value:
            w["key"].value = d.ref

    def _changed(self):
        self.show(self.ed.kind.value)
        self._set_title()
        if self.type == "line":
            self.ed._show_region()  # (the section settings show while a line is on)
        self.ed.request()

    def _set_title(self):
        t, w = self.type, self.w
        sub = ""
        if "field" in w:
            d = self.ed.fields[w["field"].value]
            sub = f" · {d.label}"
            m = w["mode"].value
            if self.ed.kind.value != "xsec":
                z = w["z"].value or 0
                own = self.ed.vary.value == "height" and not w["z_fixed"].value
                sub += {"height": " · the panel's height" if own else f" · {z:g} km",
                        "level": f" · k = {z:g}",
                        "colmax": " · column max", "colmin": " · column min"}.get(m, "")
            if w["reduce_op"].value and self.ed.kind.value != "xsec":
                sub += {"composite": " · storm-following mean"}.get(
                    w["reduce_op"].value, f" · {w['reduce_op'].value} over a time window")
            if t == "fill" and w["minus_on"].value:
                sub += " · difference"
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
        d = fg.layer_defaults("fill", self.ed.fields, ev.new)
        self.lay["units"] = d["units"]
        self.ed._hold = True
        try:
            for k in ("cmap", "vmin", "vmax", "extend"):
                self.w[k].value = d[k] if k != "cmap" or d[k] in FIG_CMAPS else "viridis"
            self.w["mask_below"].value = "" if d["mask_below"] is None else f"{d['mask_below']:g}"
            self.w["cbar_label"].placeholder = d["units"]
        finally:
            self.ed._hold = False
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
        d = fg.layer_defaults("fill", self.ed.fields, w["field"].value)
        self.ed._hold = True
        try:
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
        finally:
            self.ed._hold = False
        self._changed()

    def collect(self):
        w, lay = self.w, dict(self.lay)
        for k, x in w.items():
            if k in ("outline_on",) or k.startswith(("minus_", "reduce_")):
                continue
            lay[k] = x.value
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
            if w["minus_on"].value:
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
