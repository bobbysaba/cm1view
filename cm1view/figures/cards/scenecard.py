"""The rows of a 3D scene figure's lists: one isosurface, one plane of vectors, one
parcel set."""

import panel as pn

from ...core import parcels as P, vectors
from ...core.fields import CMAPS
from .base import FRAMES, PAR_MOVING, PAR_TAILS, _BTN, _f, _grid, _hex, cmap_select
from .layercard import parcel_pick, parcel_sets
from ...viewer.ui import held

SCENE_VIEWS = {"From the southwest": "oblique", "From above": "top", "From the south": "south",
               "From the north": "north", "From the west": "west", "From the east": "east"}
SCENE_PROJ = {"Perspective": "perspective", "Orthographic (no foreshortening)": "orthographic"}
SCENE_RES = {"Auto": 0, "Full": 1, "1/2": 2, "1/3": 3, "1/4": 4}
SCENE_LIGHTS = {"Light kit (soft, from several sides)": "kit", "Three lights": "three",
                "Headlight (from the camera)": "head"}
SCENE_BG = {"The figure's (File tab)": "", "White": "white", "Black": "black",
            "Transparent": "transparent"}
SCENE_ARROWS = {"3D arrows (scaled by length)": "glyph", "Lines (as the 3D view)": "lines"}
SCENE_BARS = {"Below": "bottom", "Right": "right", "Left": "left", "Above": "top",
              "None": "none"}
SCENE_STREAM_DIR = {"Forward": "forward", "Backward": "backward", "Both": "both"}
SCENE_STREAM_BY = {"Height": "z", "Vertical velocity": "w"}
SCENE_FLOOR_RANGE = {"From the data": "data", "Field default": "field", "Custom": "custom"}
SCENE_FLOOR_CMAPS = ["Field default"] + list(CMAPS)  # (the 3D view's: also plotly's)
SCENE_PAR_TAILS = {k.replace("panel", "scene"): v for k, v in PAR_TAILS.items()}


def _onbox(value):
    return pn.widgets.Checkbox(value=bool(value), width=22, margin=(18, 4, 0, 4))


class IsoRow:
    """One isosurface of a 3D scene: field, value, colour, opacity (unticked: kept,
    not drawn)."""

    def __init__(self, ed, e):
        F = ed.fields
        g3 = F.groups(ndim=3)
        first = next(iter(next(iter(g3.values())).values()))
        var = e.get("var") if e.get("var") in F else first
        self.w = w = dict(
            on=_onbox(e.get("on", True)),
            var=pn.widgets.Select(name="Field", groups=g3, value=var),
            val=_f("Value", float(e.get("val") or 0.0)),
            color=pn.widgets.ColorPicker(name="Colour", value=_hex(e.get("color") or "#7dd3fc")),
            op=_f("Opacity", float(e.get("op", 0.5)), step=0.05, start=0.05, end=1.0))
        self.rm = pn.widgets.Button(name="✕", description="Remove the isosurface", **_BTN)
        for x in w.values():
            x.param.watch(lambda ev: ed.request(), "value")
        self.panel = pn.Row(w["on"], _grid((w["var"], 2), w["val"], w["color"], w["op"], n=5),
                            self.rm, margin=0, sizing_mode="stretch_width")

    def collect(self):
        w = self.w
        return dict(on=bool(w["on"].value), var=w["var"].value, val=float(w["val"].value or 0.0),
                    color=w["color"].value, op=float(w["op"].value or 0.5))


class VecRow:
    """One plane of vectors of a 3D scene: vector, height, frame, arrows across the
    region, reference length, colour (unticked: kept, not drawn)."""

    def __init__(self, ed, e):
        opts = vectors.options(ed.fields) or {"Wind": "wind"}
        q = e.get("q") if e.get("q") in opts.values() else next(iter(opts.values()))
        self.w = w = dict(
            on=_onbox(e.get("on", True)),
            q=pn.widgets.Select(name="Vector", options=opts, value=q),
            level=_f("Height (km)", float(e.get("level") or 0.0), step=0.25, start=0.0),
            frame=pn.widgets.Select(name="Frame", options=FRAMES,
                                    value=e.get("frame") if e.get("frame") in FRAMES.values()
                                    else "ground"),
            density=pn.widgets.IntInput(name="Arrows across", start=4, end=60,
                                        value=int(e.get("density") or 16)),
            ref=_f("Ref. length", float(e.get("ref") or vectors.VECTORS[q].ref),
                   description="The vector length that makes an arrow one spacing long"),
            color=pn.widgets.ColorPicker(name="Colour", value=_hex(e.get("color") or "#000000")))
        self.rm = pn.widgets.Button(name="✕", description="Remove these vectors", **_BTN)
        w["q"].param.watch(self._on_q, "value")
        for k, x in w.items():
            if k != "q":
                x.param.watch(lambda ev: ed.request(), "value")
        self.ed = ed
        self.panel = pn.Row(w["on"], _grid((w["q"], 2), w["level"], w["frame"], w["density"],
                                           w["ref"], w["color"], n=4),
                            self.rm, margin=0, sizing_mode="stretch_width")
        self._show()

    def _show(self):
        d = vectors.VECTORS[self.w["q"].value]
        self.w["frame"].visible = d.framed
        self.w["ref"].name = f"Ref. length ({d.units})"

    def _on_q(self, ev):
        """A new vector: its typical magnitude as the reference."""
        with held(self.ed):
            self.w["ref"].value = vectors.VECTORS[ev.new].ref
        self._show()
        self.ed.request()

    def collect(self):
        w = self.w
        q = w["q"].value
        return dict(on=bool(w["on"].value), q=q, level=float(w["level"].value or 0.0),
                    frame=w["frame"].value, density=int(w["density"].value or 16),
                    ref=float(w["ref"].value or vectors.VECTORS[q].ref),
                    color=w["color"].value)


class ParRow:
    """One parcel set of a 3D scene: the set (the viewer's sets and the saved ones can
    replace it), colour or the variable it is coloured by, tails, heads and sizes
    (unticked: kept, not drawn).  The entry's other keys (its rule, range, ...) are
    kept as they were."""

    def __init__(self, ed, e):
        self.ed, self.e = ed, dict(e)
        pf = ed.v.pf
        cvar = e.get("cvar") or ""
        self.w = w = dict(
            on=_onbox(e.get("on", True)),
            color=pn.widgets.ColorPicker(name="Colour", value=_hex(e.get("color") or "#d62728")),
            cvar=pn.widgets.Select(name="Colour by", value=cvar, groups=P.var_choices(
                pf, {"Set colour": ""}, keep=cvar)),
            cmap=cmap_select(e.get("cmap")),
            tails=pn.widgets.Select(name="Tails", options=SCENE_PAR_TAILS,
                                    value=e.get("tails", "until")),
            minutes=_f("Minutes", float(e.get("minutes", 10.0)), step=5.0, start=0.0),
            lw=_f("Line width", float(e.get("lw", 1.5)), step=0.5, start=0.0),
            ms=_f("Head size", float(e.get("ms", 3.0)), step=0.5, start=0.0),
            alpha=_f("Opacity", float(e.get("alpha", 0.8)), step=0.1, start=0.0, end=1.0),
            heads=pn.widgets.Checkbox(name="Heads", value=bool(e.get("heads", True)),
                                      margin=(24, 4, 0, 4)),
            moving=pn.widgets.Select(name="Tails seen from", options=PAR_MOVING,
                                     value=e.get("moving", "grid")),
            move_u=_f("u (m/s)", float(e.get("move_u", 0.0) or 0.0), step=1.0),
            move_v=_f("v (m/s)", float(e.get("move_v", 0.0) or 0.0), step=1.0))
        self.pset = pn.widgets.Select(name="Parcels", options=parcel_sets(ed.v, e, "this one"),
                                      value="", description="The parcel set drawn: pick "
                                      "another set of the viewer, or a saved one")
        self.rm = pn.widgets.Button(name="✕", description="Remove these parcels", **_BTN)
        for k, x in w.items():
            x.param.watch(self._on_change, "value")
        self.pset.param.watch(self._on_pset, "value")
        self._show()
        self.panel = pn.Row(w["on"], _grid((self.pset, 2), w["color"], w["cvar"], w["cmap"],
                                           w["tails"], w["minutes"], w["lw"], w["ms"],
                                           w["alpha"], w["heads"], (w["moving"], 2),
                                           w["move_u"], w["move_v"], n=4),
                            self.rm, margin=0, sizing_mode="stretch_width")

    def _show(self):
        w = self.w
        by = bool(w["cvar"].value)
        w["color"].visible, w["cmap"].visible = not by, by
        w["minutes"].visible = w["tails"].value == "last"
        w["move_u"].visible = w["move_v"].visible = w["moving"].value == "motion"

    def _on_change(self, ev):
        self._show()
        self.ed.request()

    def _on_pset(self, ev):
        """Another set: its parcels (its rule) and colour."""
        if not ev.new:
            return
        src = parcel_pick(self.ed, ev.new)
        if src is not None:
            self.e.update(src)
            with held(self.ed):
                if src.get("color"):
                    self.w["color"].value = _hex(src["color"])
        with held(self.ed):
            self.pset.options = parcel_sets(self.ed.v, self.e, "this one")
            self.pset.value = ""
        if src is not None:
            self.ed.request()

    def collect(self):
        w, pf = self.w, self.ed.v.pf
        cvar = w["cvar"].value or ""
        e = dict(self.e, on=bool(w["on"].value), color=w["color"].value, cvar=cvar,
                 cmap=w["cmap"].value, tails=w["tails"].value,
                 minutes=float(w["minutes"].value or 0.0), lw=float(w["lw"].value or 0.0),
                 ms=float(w["ms"].value or 0.0), heads=bool(w["heads"].value),
                 moving=w["moving"].value, move_u=float(w["move_u"].value or 0.0),
                 move_v=float(w["move_v"].value or 0.0),
                 alpha=float(0.8 if w["alpha"].value is None else w["alpha"].value))
        if cvar != (self.e.get("cvar") or ""):  # (another variable: its units and range)
            e.update(units=pf.units(cvar) if pf is not None and cvar else "",
                     vmin=None, vmax=None)
        return e
