"""Figure editor: a 3D scene figure's settings (the Layers tab of kind "scene"): its
isosurfaces, floor, vectors and streamlines, the region and resolution, the camera
and the look; copying the viewer's 3D view (from_3d, and its camera as the user left
it).

The scene's run and time are the Panels tab's (Time); the picture is rendered at the
preview's resolution while editing and at the export's when saved.

A mixin of the FigureEditor (figures/editor.py)."""

import copy

import numpy as np
import panel as pn

from . import draw as figdraw, spec as fg
from ..viewer.numinput import FloatInput
from .cards import (FRAMES, IsoRow, SCENE_ARROWS, SCENE_BARS, SCENE_BG,
                    SCENE_FLOOR_CMAPS, SCENE_FLOOR_RANGE, SCENE_LIGHTS, SCENE_PROJ, SCENE_RES,
                    SCENE_STREAM_BY, SCENE_STREAM_DIR, SCENE_VIEWS, VecRow, _auto, _checks,
                    _chk, _dark, _f, _grid, _hex, _hint, _row, _section)

ISO_MAX = VEC_MAX = 6


class FigureScene:
    """The widgets of a 3D scene figure, and the spec's "scene3d" block."""

    def _build_scene(self):
        F, run = self.fields, self.run
        floor0 = "cref" if "cref" in F else ("dbz" if "dbz" in F else next(iter(F.defs)))
        btn = dict(height=32, button_type="light", button_style="outline")
        # (keys: the spec's; scene3d, ground, stream, camera and look)
        self.sc_w = dict(
            ztop=_f("Top (km)", min(15.0, float(np.floor(run.z[-1]))), step=0.5, start=0.5),
            exag=_f("Vertical exaggeration", 2.0, step=0.5, start=0.25),
            smooth=_f("Smoothing σ (grid cells)", 0.75, step=0.25, start=0.0),
            res=pn.widgets.Select(name="Resolution", options=SCENE_RES, value=0,
                                  description="Auto: coarser for a large region (about 12 "
                                              "million grid points at most)"))
        self.sc_region = pn.widgets.Select(name="Region", options={
            "Whole domain": "full", "Fixed box": "box"})
        self.sc_box = [_f(n, None, step=0.5) for n in ("x min (km)", "x max (km)",
                                                       "y min (km)", "y max (km)")]
        self.sc_box_btn = pn.widgets.Button(name="The map's 3D box", **btn,
                                            description="The box drawn on the map (3D tool)")
        self.sc_g = dict(
            on=_chk("Floor", True),
            var=pn.widgets.Select(name="Field", groups=F.groups(), value=floor0),
            z=_f("Height (km; 0: lowest level)", 0.0, step=0.25, start=0.0),
            cmap=pn.widgets.Select(name="Colormap", options=SCENE_FLOOR_CMAPS,
                                   value="Field default"),
            rev=_chk("Reverse colours", False),
            range=pn.widgets.Select(name="Range", options=SCENE_FLOOR_RANGE, value="data"),
            lo=_f("Min", 0.0), hi=_f("Max", 1.0))
        self.sc_s = dict(
            on=_chk("Streamlines", False),
            z=_f("Seed height (km)", 0.5, step=0.1, start=0.0),
            n=pn.widgets.IntInput(name="Seeds across (n × n)", start=2, end=40, value=12),
            length=_f("Max length (km)", 40.0, step=5.0, start=1.0),
            dir=pn.widgets.Select(name="Direction", options=SCENE_STREAM_DIR),
            frame=pn.widgets.Select(name="Frame", options=FRAMES, value="storm"),
            color_by=pn.widgets.Select(name="Colour by", options=SCENE_STREAM_BY))
        self._sc_seed = None  # the streamlines' seed box (x0, x1, y0, y1 km), or None
        self.sc_seed_btn = pn.widgets.Button(name="The map's seed box", **btn,
                                             description="Seed inside the box picked on "
                                                         "the map (3D tool → Seed box on map)")
        self.sc_seed_clear = pn.widgets.Button(name="Whole region", **btn)
        self.sc_seed_html = pn.pane.HTML(margin=(2, 4))
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
        self._cam_fixed = {}  # (a spec's explicit position / focal / up: kept until edited)
        self.sc_cam_btn = pn.widgets.Button(
            name="Camera of the 3D view", **btn,
            description="The direction and distance the 3D workspace is seen from now")
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
        self.sc_from = pn.widgets.Button(
            name="Copy the 3D view", button_type="primary", button_style="outline",
            height=32, description="Everything the 3D workspace shows now (its box, "
                                   "surfaces, floor, vectors, streamlines and camera)")
        self.iso_rows, self.svec_rows = [], []
        self.iso_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.svec_box = pn.Column(sizing_mode="stretch_width", margin=0)
        self.iso_add = pn.widgets.Button(name="+ Isosurface", **btn)
        self.svec_add = pn.widgets.Button(name="+ Vectors", **btn)

        g, s, c, lk, w = self.sc_g, self.sc_s, self.sc_c, self.sc_l, self.sc_w
        self.scene_col = pn.Column(
            _hint("One 3D picture, rendered off-screen (pyvista) at the preview's "
                  "resolution here and at the export's DPI when saved. Its run and time: "
                  "<b>Panels → Time</b>. <b>Copy the 3D view</b> takes everything the 3D "
                  "workspace shows."),
            _row(self.sc_from),
            _section("Isosurfaces", self.iso_box, _row(self.iso_add),
                     _hint("Untick a surface to leave it out (it is kept). Storm-relative "
                           "fields use the run's track."), collapsed=False),
            _section("Floor", _grid((g["var"], 2), g["z"], g["cmap"], g["range"], g["lo"],
                                    g["hi"]),
                     _checks(g["on"], g["rev"])),
            _section("Vectors", self.svec_box, _row(self.svec_add),
                     _hint("Arrows in a plane at a height; <b>Arrows across</b>: across the "
                           "region's width.")),
            _section("Streamlines", _grid(s["z"], s["n"], s["length"], s["dir"], s["frame"],
                                          s["color_by"]),
                     _checks(s["on"]),
                     _row(self.sc_seed_btn, self.sc_seed_clear), self.sc_seed_html),
            _section("Region and resolution",
                     _grid(self.sc_region, w["ztop"], w["exag"]),
                     _grid(*self.sc_box, n=2), _row(self.sc_box_btn),
                     _grid(w["smooth"], w["res"]),
                     _hint("The exaggeration only stretches the picture (nothing is read "
                           "again); the region, top, smoothing and resolution compute the "
                           "surfaces again.")),
            _section("Camera", _grid(c["preset"], c["azimuth"], c["elevation"], c["zoom"],
                                     c["projection"], c["view_angle"]),
                     _row(self.sc_cam_btn),
                     _hint("A view, turned by the azimuth and elevation typed (blank: the "
                           "view's own), at the distance where the region fits, divided by "
                           "the zoom. <b>Camera of the 3D view</b>: as you left the 3D "
                           "workspace (rotate it there, then click)."), collapsed=False),
            _section("Look", _grid(lk["lighting"], lk["background"], lk["arrows"],
                                   lk["shine"], lk["ambient"], lk["tube"],
                                   lk["floor_bar"], lk["stream_bar"], lk["outline_color"]),
                     _grid(*self.sc_labels),
                     _checks(lk["outline"], lk["ticks"], lk["legend"], lk["seed_box"])),
            _section("Animation", _grid(self.sc_anim["follow"], self.sc_anim["orbit"]),
                     _hint("For <b>Export → Animation (GIF)</b>: each frame steps the "
                           "scene's time. A box following the track needs a <b>Fixed "
                           "box</b> and the run's track; the orbit is shared out evenly, "
                           "so a looping 360° turn does not repeat a frame.")),
            sizing_mode="stretch_width", margin=0)

        rq = lambda *e: self.request()  # noqa: E731
        for d in (self.sc_w, self.sc_g, self.sc_s, self.sc_l, self.sc_anim):
            for x in d.values():
                x.param.watch(rq, "value")
        for x in self.sc_labels:
            x.param.watch(rq, "value")
        for x in self.sc_c.values():
            x.param.watch(self._on_camera_edit, "value")
        self.sc_region.param.watch(lambda e: (self._scene_show(), self.request()), "value")
        for x in self.sc_box:
            x.param.watch(lambda e: self.request(), "value")
        for x in (g["var"], g["range"]):
            x.param.watch(self._on_floor, "value")
        self.sc_box_btn.on_click(lambda e: self._scene_map_box())
        self.sc_seed_btn.on_click(lambda e: self._scene_seed(True))
        self.sc_seed_clear.on_click(lambda e: self._scene_seed(False))
        self.sc_cam_btn.on_click(lambda e: self._scene_camera_from_3d())
        self.sc_from.on_click(lambda e: self._scene_copy_3d())
        self.iso_add.on_click(lambda e: self._add_iso())
        self.svec_add.on_click(lambda e: self._add_svec())
        # the 3D workspace's camera as the user leaves it (plotly's relayout after a drag)
        self._cam3d = None
        v = self.v
        if hasattr(v, "plot3d"):
            v.plot3d.param.watch(self._on_3d_relayout, "relayout_data")
        if hasattr(v, "v3_cam"):  # (a preset picked there: the latest camera)
            v.v3_cam.param.watch(lambda e: setattr(self, "_cam3d", None), "value")
        self._scene_show()

    # ------------------------------------------------------------ rows
    def _iso_row(self, e):
        r = IsoRow(self, e)
        r.rm.on_click(lambda ev: self._remove_row(self.iso_rows, r))
        return r

    def _svec_row(self, e):
        r = VecRow(self, e)
        r.rm.on_click(lambda ev: self._remove_row(self.svec_rows, r))
        return r

    def _remove_row(self, rows, r):
        rows.remove(r)
        self._scene_rows()
        self.request()

    def _scene_rows(self):
        self.iso_box.objects = [r.panel for r in self.iso_rows] or [pn.pane.HTML(
            '<div class="cv-empty">No isosurfaces: add one.</div>')]
        self.svec_box.objects = [r.panel for r in self.svec_rows]
        self.iso_add.disabled = len(self.iso_rows) >= ISO_MAX
        self.svec_add.disabled = len(self.svec_rows) >= VEC_MAX

    def _add_iso(self):
        """A new isosurface: reflectivity 30 dBZ first, then updraft 10 m/s, then the
        last one's field."""
        F, have = self.fields, [r.w["var"].value for r in self.iso_rows]
        e = next((dict(var=v, val=x, color=c, op=o) for v, x, c, o in (
            ("dbz", 30.0, "#7dd3fc", 0.25), ("winterp", 10.0, "#f97316", 0.85),
            ("winterp", -5.0, "#3b82f6", 0.7)) if v in F and (v, x) not in [
            (r.w["var"].value, r.w["val"].value) for r in self.iso_rows]),
            dict(var=have[-1] if have else None, val=0.0, color="#a3a3a3", op=0.5))
        self.iso_rows.append(self._iso_row(e))
        self._scene_rows()
        self.request()

    def _add_svec(self):
        lv = [float(r.w["level"].value or 0.0) for r in self.svec_rows]
        self.svec_rows.append(self._svec_row(dict(
            level=max(lv) + 1.0 if lv else 0.0,
            frame="grid" if (self.run.umove or self.run.vmove) else "ground",
            color=("#000000", "#b45309", "#0e7490")[len(lv) % 3])))
        self._scene_rows()
        self.request()

    # ------------------------------------------------------------ what is shown
    def _scene_show(self, *e):
        box = self.sc_region.value == "box"
        for x in self.sc_box:
            x.visible = box
        g = self.sc_g
        d = self.fields[g["var"].value] if g["var"].value in self.fields else None
        g["z"].visible = d is not None and d.ndim == 3
        g["lo"].visible = g["hi"].visible = g["range"].value == "custom"
        self.sc_seed_clear.visible = self._sc_seed is not None
        sb = self._sc_seed
        self.sc_seed_html.object = (
            '<div class="cv-hint">Seeded over the whole region.</div>' if sb is None else
            f'<div class="cv-hint">Seeded in x {sb[0]:.1f} to {sb[1]:.1f}, y {sb[2]:.1f} '
            f'to {sb[3]:.1f} km.</div>')

    def _on_floor(self, ev):
        """A floor field or range: its height only for 3D fields; a custom range
        starts at the field's display range."""
        g = self.sc_g
        if not self._hold and g["range"].value == "custom" and ev.obj is g["range"]:
            d = self.fields[g["var"].value] if g["var"].value in self.fields else None
            if d is not None and d.vrange:
                hold, self._hold = self._hold, True
                try:
                    g["lo"].value, g["hi"].value = (float(v) for v in d.vrange)
                finally:
                    self._hold = hold
        self._scene_show()

    def _on_camera_edit(self, ev):
        """A camera setting changed: an explicit position (from a spec) no longer holds."""
        if self._hold:
            return
        self._cam_fixed = {}
        self.request()

    # ------------------------------------------------------------ spec <-> widgets
    def _scene_set(self, sc):
        """Show scene block sc (fg.scene3d_of's) in the widgets (no render)."""
        hold, self._hold = self._hold, True
        try:
            for k, x in self.sc_w.items():
                x.value = sc[k] if k == "res" else float(sc[k])
            box = sc.get("box")
            self.sc_region.value = "box" if box else "full"
            for x, b in zip(self.sc_box, box or [None] * 4):
                x.value = None if b is None else float(b)
            self.sc_anim["follow"].value = "track" if sc["follow"] == "track" else "fixed"
            self.sc_anim["orbit"].value = float(sc["orbit"] or 0.0)
            _put(self.sc_g, sc["ground"])
            _put(self.sc_s, sc["stream"])
            sb = sc["stream"].get("seed_box")
            self._sc_seed = tuple(float(v) for v in sb) if sb else None
            cam = figdraw.camera_of(sc)
            _put(self.sc_c, cam)
            self._cam_fixed = {k: cam[k] for k in ("position", "focal", "up")
                               if cam.get(k) is not None}
            lk = figdraw.look_of(sc)
            _put(self.sc_l, dict(lk, background=lk["background"] or ""))
            for x, t in zip(self.sc_labels, list(lk["labels"]) + ["", "", ""]):
                x.value = str(t)
            self._sc_extra = {k: copy.deepcopy(sc[k]) for k in sc
                              if k not in fg.SCENE3D}  # (kept as they were)
            self._sc_look_extra = {k: v for k, v in (sc.get("look") or {}).items()
                                   if k not in self.sc_l and k != "labels"}
            self.iso_rows = [self._iso_row(e) for e in sc["isos"]]
            self.svec_rows = [self._svec_row(e) for e in sc["vecs"]]
        finally:
            self._hold = hold
        self._scene_rows()
        self._scene_show()

    def _scene_collect(self):
        """The spec's scene3d block of the widgets."""
        w = self.sc_w
        box = [x.value for x in self.sc_box]
        ok = self.sc_region.value == "box" and None not in box and box[1] > box[0] \
            and box[3] > box[2]
        cam = dict(_get(self.sc_c), **self._cam_fixed)
        cam["zoom"] = cam["zoom"] or 1.0
        cam["view_angle"] = cam["view_angle"] or 30.0
        look = dict(getattr(self, "_sc_look_extra", {}), **_get(self.sc_l),
                    labels=[x.value for x in self.sc_labels])
        look["background"] = look["background"] or None
        for k, v in (("tube", 1.0), ("shine", 0.3), ("ambient", 0.25)):
            if look[k] is None:
                look[k] = v
        return dict(getattr(self, "_sc_extra", {}),
                    box=[float(v) for v in box] if ok else None,
                    ztop=float(w["ztop"].value or 15.0), exag=float(w["exag"].value or 1.0),
                    smooth=float(w["smooth"].value or 0.0), res=int(w["res"].value or 0),
                    isos=[r.collect() for r in self.iso_rows],
                    vecs=[r.collect() for r in self.svec_rows],
                    stream=dict(_get(self.sc_s), seed_box=list(self._sc_seed)
                                if self._sc_seed else None),
                    ground=_get(self.sc_g), camera=cam, look=look,
                    follow=self.sc_anim["follow"].value,
                    orbit=float(self.sc_anim["orbit"].value or 0.0))

    # ------------------------------------------------------------ from the viewer
    def _scene_map_box(self):
        b = getattr(self.v, "box", None)
        if b is None:
            self._msg("Draw a 3D box on the map first (3D tool), or type one.", True)
            return
        hold, self._hold = self._hold, True
        try:
            self.sc_region.value = "box"
            for x, v in zip(self.sc_box, b):
                x.value = round(float(v), 2)
        finally:
            self._hold = hold
        self._scene_show()
        self.request()

    def _scene_seed(self, use):
        if use:
            sb = getattr(self.v, "seed_box", None)
            if sb is None:
                self._msg("Pick a seed box on the map first (3D tool → <b>Seed box on "
                          "map</b>).", True)
                return
            self._sc_seed = tuple(float(v) for v in sb)
        else:
            self._sc_seed = None
        self._scene_show()
        self.request()

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

    def _scene_camera_from_3d(self):
        cam = self._view_camera()
        hold, self._hold = self._hold, True
        try:
            _put(self.sc_c, cam)
        finally:
            self._hold = hold
        self._cam_fixed = {}
        self.request()

    def viewer_scene(self):
        """The scene block of what the 3D workspace shows (its box, top, exaggeration,
        smoothing, resolution, surfaces, floor, vectors, streamlines and camera); light
        vector colours chosen for its dark background turn black."""
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
                      vecs=vecs, stream=stream, ground=ground)
        except AttributeError:  # (a viewer without the 3D workspace)
            sc = dict(isos=[dict(on=True, var="dbz", val=30.0, color="#7dd3fc", op=0.25)]
                      if "dbz" in self.F else [])
        for e in sc.get("vecs", []):
            if e["ref"] is None:
                e.pop("ref")
        return fg.scene3d_of(dict(scene3d=dict(sc, camera=self._view_camera(), look={})))

    def _scene_copy_3d(self):  # (the animation settings stay)
        self._scene_set(dict(self.viewer_scene(), **{k: x.value
                                                     for k, x in self.sc_anim.items()}))
        self.request()

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
        s["letters"] = dict(s["letters"], on=self._multi_part())
        self.set_spec(s)


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


def _get(ws):
    return {k: x.value for k, x in ws.items()}
