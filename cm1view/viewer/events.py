"""Events: time and playback, the tool modes, zoom images, regions, fill
and cross-section colour ranges, map taps, drags and box selections, ranges and
clearing.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

from functools import partial

import panel as pn

from ..core import volume3d
from .zoomview import ZoomImage
from .ui import PANELS


class Events:
    def _on_time(self, ev):
        """Every time change (drag, step, playback) updates the map."""
        self._update_time_html()
        self._update_track_now()
        self.ser_now.location = self.ser_th_now.location = self.run.times[self.t] / 60.0
        self._draw_points()
        self.request_map()

    def _refresh_panels(self):
        """The slower panels follow time only once it settles (slider released,
        step button, or playback paused)."""
        if self.playing:
            return
        if self.points and self.follow.value:
            self.request_soundings()
        if len(self.xs_pts) == 2 and self.panel_col.visible and self.tabs.active == 1:
            self.request_xsec()
        if self.v3_follow.value and self.plot3d.visible and self.workspace.value == "3D":
            self.request_3d()
        if self.dist_follow.value and self.dists:
            self._dist_follow()

    def _step(self, d):
        if self.playing:
            self._on_play(None)
        self.tslider.value = (self.t + d) % (self.tslider.end + 1)
        self._refresh_panels()

    def _tick(self):
        self.tslider.value = (self.t + 1) % (self.tslider.end + 1)

    def _on_play(self, ev):
        self.playing = not self.playing
        self.t_play.icon = "player-pause" if self.playing else "player-play"
        if self.playing:
            if self._play_cb is None:
                self._play_cb = pn.state.add_periodic_callback(
                    self._tick, period=self.t_speed.value, start=False)
            self._play_cb.start()
        else:
            if self._play_cb is not None:
                self._play_cb.stop()
            self._refresh_panels()

    def _on_speed(self, ev):
        if self._play_cb is not None:
            self._play_cb.period = ev.new

    def _on_mode(self, mode, init=False):
        hints = {
            None: "Pick a tool on the left (Sounding, Section, Track, Series, Distribution, "
                  "3D box) to query the map",
            "Sounding": "Click: sounding at a point · <kbd>Shift</kbd>-click: add a point "
                        "(up to 4)",
            "Area sounding": "Drag a box: sounding averaged over it · <kbd>Shift</kbd>-drag: "
                             "add a box (up to 4)",
            "Cross-section": "Click two points (A, then B) to draw a vertical section",
            "3D region": "Drag a box to choose the 3D region; it renders in the 3D view",
            "Track": "Auto-track: click the meso to follow it through time; click near the "
                     "track at another time to correct it · Place by hand: each click sets "
                     "the fix at the shown time",
            "Series": "Choose a field and a region in the panel, then Compute · click a "
                      "series plot to go to that time",
            "Distribution": "Choose a field, height or layer and a region in the panel, then "
                            "Compute: every value there at the shown time",
        }
        self.hint.object = f'<div class="cv-hint">{hints[mode]}</div>'
        self.fig.toolbar.active_drag = self.bsel if mode in ("3D region", "Area sounding") \
            else self.pan
        if mode in ("Sounding", "Area sounding"):  # the Sounding button reopens this kind
            self.mode.mode_for["Sounding"] = self.snd_pick.value = mode
        if init:
            return
        if self.full and PANELS.get(mode) != self.tabs.active:
            self._set_full(False)  # another tool: back to the map
        if mode in PANELS:
            self._show_panel(True, PANELS[mode])
        elif mode is None:
            self._show_panel(False)

    def _on_tool_reclick(self, tool):
        """The lit tool's button pressed again: reopen its closed panel (True), or
        let the tool switch off (False)."""
        tab = PANELS.get(tool)
        if tab is None or (self.panel_col.visible and self.tabs.active == tab):
            return False
        self._show_panel(True, tab)
        return True

    def _zoom_image(self, filename, **kw):
        z = ZoomImage(filename=filename, interactive=self.full, sizing_mode="stretch_width",
                      visible=kw.pop("visible", False), **kw)
        z.param.watch(lambda e: self._set_full(True), "clicks")  # click: expand
        z.param.watch(partial(self._on_zoom_box, z), "box")
        z.param.watch(partial(self._on_zoom_pan, z), "pan")
        z.param.watch(lambda e: self._on_zoom_out(z), "zoom_out")
        z.param.watch(lambda e: self._on_zoom_reset(z), "resets")
        return z

    def _zoom_images(self):
        return [self.skew_png, self.prof_png] + [
            z for tab in self.snd_tabs for z in tab if isinstance(z, ZoomImage)]

    def _on_pick_region(self, ev):
        self.workspace.value = "Map"
        self.mode.set("3D region")

    def _ser_regions(self):
        """Series regions on offer: the 3D region box only once one is drawn."""
        opts = {"Whole domain": "domain", "Current map view": "view"}
        if self.box is not None:
            opts["3D region box"] = "box3d"
        opts["Around tracked storm"] = "track"
        return opts

    def _update_region_html(self):
        self._update_items()
        for w in (getattr(self, "ser_region", None), getattr(self, "dist_region", None)):
            if w is None:
                continue
            opts = self._ser_regions()
            if w.options != opts:
                if w.value not in opts.values():
                    w.param.update(options=opts, value="domain")
                else:
                    w.options = opts
        if self.box is None:
            txt = "Region: current map view"
            box = self.view
        else:
            box = self.box
            txt = "Region"
        x0, x1, y0, y1 = box
        stride = volume3d.auto_stride(self.run, box, self.v3_ztop.value, 12e6)
        self.v3_region.object = (
            f'<div class="cv-hint" style="margin:0 8px;white-space:nowrap">{txt} {x1 - x0:.1f} × {y1 - y0:.1f} '
            f'km · auto res {"full" if stride == 1 else f"1/{stride}"}</div>')

    def _update_3d_labels(self):
        n = sum(o["on"].value for o in self.isos)
        self.v3_drawer.label("iso", f"Isosurfaces ({n})")

    def _on_fill_var(self, ev):
        d = self.F[ev.new]
        self._hold = True
        try:
            self.fill_cmap.value = d.cmap
            self.fill_rev.value = False
            if d.vrange:
                self.fill_min.value, self.fill_max.value = d.vrange
            self.fill_auto.value = True
            self.fill_mode.disabled = self.fill_lvl.disabled = d.ndim == 2
        finally:
            self._hold = False
        self.request_map()

    def _on_fill_auto(self, ev):
        self.fill_min.disabled = self.fill_max.disabled = ev.new
        if not ev.new and self._last_range is not None:
            self._hold = True
            self.fill_min.value, self.fill_max.value = [round(v, 4) for v in self._last_range]
            self._hold = False
        self.request_map()

    _last_range = None

    _xs_range = None

    def _on_xs_fill(self, ev):
        self._hold_xs = True
        self.xs_cmap.value, self.xs_rev.value, self.xs_auto.value = \
            self.F[ev.new].cmap, False, True
        self._hold_xs = False
        self.request_xsec()

    def _on_xs_auto(self, ev):
        self.xs_min.disabled = self.xs_max.disabled = ev.new
        if not ev.new and self._xs_range is not None:
            self._hold_xs = True
            self.xs_min.value, self.xs_max.value = [round(v, 4) for v in self._xs_range]
            self._hold_xs = False
        self.request_xsec()

    def _on_storm(self, ev):
        custom = ev.new == "custom"
        self.storm_u.visible = self.storm_v.visible = custom
        self.request_soundings()
        if self.vec_on.value and self.vec_frame.value == "storm":
            self.request_map()

    def _on_tap(self, ev):
        x, y = float(ev.x), float(ev.y)
        x0, x1, y0, y1 = self.extent
        v0, v1, w0, w1 = self.view
        if not (x0 <= x <= x1 and y0 <= y <= y1 and min(v0, v1) <= x <= max(v0, v1)
                and min(w0, w1) <= y <= max(w0, w1)):
            return
        mode = self.mode.value
        if mode == "Sounding":
            shift = bool((getattr(ev, "modifiers", None) or {}).get("shift"))
            self._add_sounding(x, y, shift)
        elif mode == "Track":
            self._show_panel(True, 2)
            self.request_track(x, y)
        elif mode == "Cross-section":
            self.xs_pts = [(x, y)] if len(self.xs_pts) != 1 else self.xs_pts + [(x, y)]
            self._draw_xs()
            if len(self.xs_pts) == 2:
                self._show_panel(True, 1)
                self.request_xsec()

    def _on_pan_start(self, ev):
        self._drag_shift = bool((getattr(ev, "modifiers", None) or {}).get("shift"))

    def _on_select(self, ev):
        if not getattr(ev, "final", True):
            return
        g = ev.geometry
        if g.get("type") != "rect":
            return
        if self.mode.value == "Area sounding":
            X0, X1, Y0, Y1 = self.extent
            x0, x1 = sorted((max(X0, min(g["x0"], g["x1"])), min(X1, max(g["x0"], g["x1"]))))
            y0, y1 = sorted((max(Y0, min(g["y0"], g["y1"])), min(Y1, max(g["y0"], g["y1"]))))
            if x1 - x0 > 0 and y1 - y0 > 0:
                self._add_sounding((x0 + x1) / 2, (y0 + y1) / 2, self._drag_shift,
                                   (x1 - x0, y1 - y0))
            return
        if self.mode.value != "3D region":
            return
        self._set_box((g["x0"], g["x1"], g["y0"], g["y1"]))
        self.workspace.value = "3D"
        self.request_3d()

    def _on_use_view(self, ev):
        self._set_box(self.view)
        self.request_3d()

    def _set_box(self, box):
        x0, x1, y0, y1 = box
        X0, X1, Y0, Y1 = self.extent
        x0, x1 = sorted((max(X0, min(x0, x1)), min(X1, max(x0, x1))))
        y0, y1 = sorted((max(Y0, min(y0, y1)), min(Y1, max(y0, y1))))
        self.box = (x0, x1, y0, y1)
        self.box_src.data = dict(left=[x0], right=[x1], bottom=[y0], top=[y1])
        self._update_region_html()

    def _on_resized(self, attr, old, new):
        """The browser re-fitted the map to a new plot size: render the new view (the
        range values arrive in the same message, so read them on the next tick)."""
        def update():
            xr, yr = self.fig.x_range, self.fig.y_range
            self.view = (float(xr.start), float(xr.end), float(yr.start), float(yr.end))
            self.request_map()
            if self.box is None:
                self._update_region_html()
        self._schedule(update)

    def _on_ranges(self, ev):
        if None in (ev.x0, ev.x1, ev.y0, ev.y1):
            return
        self.view = (float(ev.x0), float(ev.x1), float(ev.y0), float(ev.y1))
        self.request_map()
        if self.box is None:
            self._update_region_html()

    def _on_clear_cache(self, ev):
        self.run.clear_cache()
        self._update_cache_html()

    def _on_clear_points(self, ev):
        self.points, self.xs_pts, self.box = [], [], None
        self._draw_points()
        self._draw_xs()
        self.box_src.data = dict(left=[], right=[], bottom=[], top=[])
        self.workspace.value = "Map"
        self._update_region_html()
        self.request_soundings()
