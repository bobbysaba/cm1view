"""Figure editor: what a 3D scene figure takes from the viewer (from_3d, its camera as the user left
it, its parcel sets), and the widgets the shell's scene settings are copied from.

A mixin of the FigureEditor (figures/editor.py)."""

import numpy as np
import panel as pn

from . import draw as figdraw, spec as fg
from ..core import parcels as P, vectors, volume3d
from ..viewer.numinput import FloatInput
from .cards import (SCENE_ARROWS, SCENE_BARS, SCENE_BG, SCENE_FLOOR_CMAPS,
                    SCENE_FLOOR_RANGE, SCENE_LIGHTS, SCENE_PROJ, SCENE_RES, SCENE_STREAM_BY,
                    SCENE_STREAM_DIR, SCENE_VIEWS, _auto, _chk, _dark, _f, _hex, parcel_pick)

ISO_MAX = VEC_MAX = PAR_MAX = 6


def next_iso(F, isos):
    """A new isosurface after `isos`: reflectivity 30 dBZ first, then updraft 10 m/s, then the
    last one's field."""
    have = [(e.get("var"), e.get("val")) for e in isos]
    return next((dict(var=v, val=x, color=c, op=o) for v, x, c, o in (
        ("dbz", 30.0, "#7dd3fc", 0.25), ("winterp", 10.0, "#f97316", 0.85),
        ("winterp", -5.0, "#3b82f6", 0.7)) if v in F and (v, x) not in have),
        dict(var=have[-1][0] if have else None, val=0.0, color="#a3a3a3", op=0.5))


def next_vec(run, vecs):
    """A new plane of vectors after `vecs`."""
    lv = [float(e.get("level") or 0.0) for e in vecs]
    return dict(level=max(lv) + 1.0 if lv else 0.0,
                frame="grid" if (run.umove or run.vmove) else "ground",
                color=("#000000", "#b45309", "#0e7490")[len(lv) % 3])


class FigureScene:
    """The widgets of a 3D scene figure, and what it takes from the viewer."""

    def _build_scene(self):
        F, run = self.fields, self.run
        floor0 = "cref" if "cref" in F else ("dbz" if "dbz" in F else next(iter(F.defs)))
        # (keys: the spec's; scene3d, ground, stream, camera and look)
        self.sc_w = dict(
            ztop=_f("Top (km MSL)" if run.terrain else "Top (km)",
                    min(15.0, float(np.floor(volume3d.top_height(run)))), step=0.5,
                    start=0.5),
            exag=_f("Vertical exaggeration", 2.0, step=0.5, start=0.25),
            smooth=_f("Smoothing σ (grid cells)", 0.75, step=0.25, start=0.0),
            res=pn.widgets.Select(name="Resolution", options=SCENE_RES, value=0,
                                  description="Auto: coarser for a large region (about 12 "
                                              "million grid points at most)"))
        self.sc_region = pn.widgets.Select(name="Region", options={
            "Whole domain": "full", "Fixed box": "box"})
        self.sc_box = [_f(n, None, step=0.5) for n in ("x min (km)", "x max (km)",
                                                       "y min (km)", "y max (km)")]
        self.sc_g = dict(
            on=_chk("Floor", True),
            var=pn.widgets.Select(name="Field", groups=F.groups(), value=floor0),
            z=_f("Height (km; 0: lowest level)", 0.0, step=0.25, start=0.0),
            cmap=pn.widgets.Select(name="Colormap", options=SCENE_FLOOR_CMAPS,
                                   value="Field default"),
            rev=_chk("Reverse", False),
            range=pn.widgets.Select(name="Range", options=SCENE_FLOOR_RANGE, value="data"),
            lo=_f("Min", 0.0), hi=_f("Max", 1.0))
        self.sc_s = dict(
            on=_chk("Streamlines", False),
            z=_f("Seed height (km)", 0.5, step=0.1, start=0.0),
            n=pn.widgets.IntInput(name="Seeds across (n × n)", start=2, end=40, value=12),
            length=_f("Max length (km)", 40.0, step=5.0, start=1.0),
            dir=pn.widgets.Select(name="Direction", options=SCENE_STREAM_DIR),
            frame=pn.widgets.Select(name="Frame", options=vectors.frames(self.run),
                                    value=vectors.frame_of(self.run, "storm")),
            color_by=pn.widgets.Select(name="Colour by", options=SCENE_STREAM_BY))
        self.sc_c = dict(
            preset=pn.widgets.Select(name="View", options=SCENE_VIEWS, value="oblique"),
            azimuth=_auto("Azimuth (°)", description="The compass bearing the camera "
                                                     "stands at from the middle (0: north, "
                                                     "90: east). Blank: the view's"),
            elevation=_auto("Elevation (°)", description="Above the horizon (90: straight "
                                                         "down). Blank: the view's"),
            zoom=_f("Zoom", 1.0, step=0.1, start=0.1,
                    description="1: the whole region fits; 2: twice as close"),
            projection=pn.widgets.Select(name="Projection", options=SCENE_PROJ),
            view_angle=_f("View angle (°)", 30.0, step=5.0, start=5.0, end=120.0,
                          description="Perspective only: smaller is flatter (a long lens)"))
        self.sc_l = dict(
            lighting=pn.widgets.Select(name="Lighting", options=SCENE_LIGHTS),
            background=pn.widgets.Select(name="Background", options=SCENE_BG, value=""),
            outline_color=pn.widgets.ColorPicker(name="Box colour", value="#475569"),
            tube=_f("Line thickness", 1.0, step=0.25, start=0.1,
                    description="Streamline tubes and line arrows (1: the default)"),
            arrows=pn.widgets.Select(name="Vectors as", options=SCENE_ARROWS),
            shine=_f("Shine", 0.3, step=0.1, start=0.0, end=1.0,
                     description="The surfaces' specular highlight (0: matte)"),
            ambient=_f("Ambient light", 0.25, step=0.05, start=0.0, end=1.0,
                       description="How light the shadowed sides stay"),
            floor_bar=pn.widgets.Select(name="Floor colorbar", options=SCENE_BARS),
            stream_bar=pn.widgets.Select(name="Streamline colorbar", options=SCENE_BARS,
                                         value="right"),
            parcel_bar=pn.widgets.Select(name="Parcel colorbar", options=SCENE_BARS,
                                         value="left"),
            outline=_chk("Box outline", True), ticks=_chk("Axis ticks", True),
            legend=_chk("Legend", True), seed_box=_chk("Seed box outline", True))
        self.sc_anim = dict(
            follow=pn.widgets.Select(name="Box in animations", options={
                "Stays where it is": "fixed", "Follows the track": "track"},
                description="A fixed box moved each frame by as far as the run's track "
                            "has moved since the first frame"),
            orbit=_f("Camera orbit (°)", 0.0, step=15.0, start=-3600.0, end=3600.0,
                     description="How far the camera turns round the region over the "
                                 "whole animation (360: once round; negative: the other "
                                 "way)"))
        self.sc_labels = [pn.widgets.TextInput(name=f"{a} axis label", value=f"{a} (km)")
                          for a in "xyz"]
        # the 3D workspace's camera as the user leaves it (plotly's relayout after a drag)
        self._cam3d = None
        v = self.v
        if hasattr(v, "plot3d"):
            v.plot3d.param.watch(self._on_3d_relayout, "relayout_data")
        if hasattr(v, "v3_cam"):  # (a preset picked there: the latest camera)
            v.v3_cam.param.watch(lambda e: setattr(self, "_cam3d", None), "value")

    def next_parcels(self, have, say):
        """A new parcel set of a scene holding the sets named `have`: the viewer's next one,
        else the run's first saved set (None: there is none; say(html, True) says so)."""
        e = next((e for e in self._scene_parcels() if e["name"] not in have), None)
        if e is not None:
            return e
        v = self.v
        saved = P.list_sets(v.run.path) if v.pf is not None else []
        if not saved:
            say("Choose parcels in the viewer's <b>Parcels</b> tab first (or save a set "
                "there).", True)
            return None
        src = parcel_pick(self, "f:" + saved[0])
        return None if src is None else dict(fg.layer_defaults("parcels", self.F), lw=1.5, **src)

    def _scene_parcels(self):
        """The viewer's parcel sets as entries of a scene (as its 2D layers, lines a
        little wider)."""
        return [dict(lay, lw=round(1.5 * float(self.v.par_width.value or 1.0), 3))
                for lay in self._parcel_layers()]

    def _on_3d_relayout(self, ev):
        d = ev.new or {}
        if isinstance(d.get("scene.camera"), dict):
            self._cam3d = d["scene.camera"]

    def _view_camera(self):
        """CAMERA keys of the 3D workspace's camera: as it was left after a drag, else
        its preset view."""
        v = self.v
        preset = v.v3_cam.value if hasattr(v, "v3_cam") else "oblique"
        cam = dict(figdraw.CAMERA, preset=preset)
        cam.update(figdraw.camera_from_plotly(self._cam3d))
        return cam

    def viewer_scene(self):
        """The scene block of what the 3D workspace shows (its box, top, exaggeration,
        smoothing, resolution, surfaces, floor, vectors, streamlines, parcel sets when
        it shows them, and camera); light vector colours chosen for its dark background
        turn black."""
        v = self.v
        try:
            box = [float(x) for x in v.box] if v.box is not None else None
            isos = [dict(on=bool(d["on"].value), var=d["var"].value,
                         val=float(d["val"].value or 0.0), color=d["color"].value,
                         op=float(d["op"].value)) for d in v.isos]
            vecs = [dict(on=bool(o["on"].value), q=o["q"].value, level=float(o["level"].value),
                         frame=o["frame"].value, density=int(o["density"].value),
                         ref=float(o["ref"].value or 0.0) or None,
                         color=_dark(o["color"].value)) for o in v.svs]
            sb = v._seed_in_box()
            stream = dict(on=bool(v.st_on.value), z=float(v.st_z.value), n=int(v.st_n.value),
                          length=float(v.st_len.value), dir=v.st_dir.value,
                          frame=v.st_frame.value, color_by=v.st_color.value,
                          seed_box=list(sb) if sb else None)
            ground = dict(on=bool(v.v3_ground.value), var=v.v3_floor.value,
                          z=float(v.v3_floor_z.value), cmap=v.v3_floor_cmap.value,
                          rev=bool(v.v3_floor_rev.value), range=v.v3_floor_range.value,
                          lo=float(v.v3_floor_min.value or 0.0),
                          hi=float(v.v3_floor_max.value or 0.0))
            sc = dict(box=box, ztop=float(v.v3_ztop.value), exag=float(v.v3_exag.value),
                      smooth=float(v.v3_smooth.value), res=int(v.v3_res.value), isos=isos,
                      vecs=vecs, stream=stream, ground=ground,
                      parcels=self._scene_parcels() if getattr(v, "par_3d", None) is not None
                      and v.par_3d.value else [])
        except AttributeError:  # (a viewer without the 3D workspace)
            sc = dict(isos=[dict(on=True, var="dbz", val=30.0, color="#7dd3fc", op=0.25)]
                      if "dbz" in self.F else [])
        for e in sc.get("vecs", []):
            if e["ref"] is None:
                e.pop("ref")
        return fg.scene3d_of(dict(scene3d=dict(sc, camera=self._view_camera(), look={})))

    def from_3d(self):
        """A 3D scene figure of the 3D workspace (its box, settings and camera) at the
        shown time."""
        t = self.v.t
        s = self._keep_runs(fg.default_spec(self.run, self.F, t))
        self._times(s, [t], t)
        s.update(kind="scene", rows=1, cols=1, size=[6.5, 5.2], size_auto=False,
                 vary="time", scene3d=self.viewer_scene())
        s["axes"] = dict(s["axes"], xlabel="", ylabel="", ticklabels="all", equal=False)
        s["colorbar"] = dict(s["colorbar"], mode="none")
        s["letters"] = dict(s["letters"], on=False)
        self.shell.open_new(s)

def _put(ws, d):
    """Widgets ws take the values of d (by key; blank-able numbers may be None; a
    choice a list lacks leaves the widget as it is)."""
    for k, x in ws.items():
        if k not in d:
            continue
        v = d[k]
        if isinstance(x, pn.widgets.ColorPicker):
            v = _hex(v)
        elif isinstance(x, pn.widgets.Checkbox):
            v = bool(v)
        elif isinstance(x, pn.widgets.IntInput):
            v = int(v)
        elif isinstance(x, FloatInput):
            v = None if v is None else float(v)
        elif isinstance(x, pn.widgets.Select):
            vals = [y for g in x.groups.values() for y in g.values()] if x.groups \
                else list(x.values)
            if v not in vals:
                continue
        x.value = v

