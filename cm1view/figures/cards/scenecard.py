"""The rows of a 3D scene figure's lists: one isosurface, one plane of vectors."""

import panel as pn

from ...core import vectors
from ...core.fields import CMAPS
from .base import FRAMES, _BTN, _f, _grid, _hex
from ...viewer.ui import held

SCENE_VIEWS = {"From the southwest": "oblique", "From above": "top", "From the south": "south",
               "From the north": "north", "From the west": "west", "From the east": "east"}
SCENE_PROJ = {"Perspective": "perspective", "Orthographic (no foreshortening)": "orthographic"}
SCENE_RES = {"Auto": 0, "Full": 1, "1/2": 2, "1/3": 3, "1/4": 4}
SCENE_LIGHTS = {"Light kit (soft, from several sides)": "kit", "Three lights": "three",
                "Headlight (from the camera)": "head"}
SCENE_BG = {"The figure's (Export tab)": "", "White": "white", "Black": "black",
            "Transparent": "transparent"}
SCENE_ARROWS = {"3D arrows (scaled by length)": "glyph", "Lines (as the 3D view)": "lines"}
SCENE_BARS = {"Below": "bottom", "Right": "right", "Left": "left", "Above": "top",
              "None": "none"}
SCENE_STREAM_DIR = {"Forward": "forward", "Backward": "backward", "Both": "both"}
SCENE_STREAM_BY = {"Height": "z", "Vertical velocity": "w"}
SCENE_FLOOR_RANGE = {"From the data": "data", "Field default": "field", "Custom": "custom"}
SCENE_FLOOR_CMAPS = ["Field default"] + list(CMAPS)  # (the 3D view's: also plotly's)


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
