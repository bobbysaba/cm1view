"""The page layout: the panels in their drawers, the top bar, the map and 3D
toolbars, the main column, full-screen and showing a panel or workspace.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import numpy as np
import panel as pn

from ..core.fields import CMAPS
from .zoomview import ParamTable
from ..theme import CSS, GRID, PANEL
from .numinput import FloatInput
from .ui import (
    BAR, DRAWER, FILL, FRAMES, PANEL_TITLES, PANELS, RAIL_BTN, TAB_MODE, Drawer, Plotly3D,
    _bar, _bokeh, _group, _html, _pill, _settings_toggle,
)


class Layout:
    def _build_panels(self):
        F, run = self.F, self.run
        g3 = F.groups(ndim=3)
        self.skew_png = self._zoom_image("skewt_hodograph.svg",
                                         styles={"flex": "1 1 640px", "min-width": "0"})
        self.prof_png = self._zoom_image("profiles.svg")
        self.params = ParamTable(stylesheets=[CSS], sizing_mode="stretch_width",
                                 styles={"flex": "1 1 380px", "min-width": "0"})
        self.snd_head = _html(
            '<div class="cv-empty">Click anywhere on the map to drop a sounding. '
            '<kbd>Shift</kbd>-click to add up to four for comparison.</div>',
            sizing_mode="stretch_width")
        self.snd_msg = _html(sizing_mode="stretch_width")
        self.snd_tabs = pn.Tabs(sizing_mode="stretch_width", dynamic=False, visible=False)
        self._snd_tab_names = []
        self.prof_row = pn.Row(
            _html('<div class="cv-hint" style="margin:8px 0 0 4px">Profile panels below '
                  'go up to</div>'), self.prof_top,
            _html('<div class="cv-hint" style="margin:8px 0 0 0">km AGL</div>'),
            visible=False, margin=(4, 0, 0, 0))
        # skew-T and table side by side when there is room (expanded view)
        self.snd_col = pn.Column(
            self.snd_head, self.snd_tabs,
            pn.FlexBox(self.skew_png, self.params, flex_wrap="wrap", gap="4px 16px",
                       align_items="flex-start", sizing_mode="stretch_width"),
            self.prof_row, self.prof_png, sizing_mode="stretch_width")

        # ---- 3D
        iso_defaults = [("dbz", 30.0, "#7dd3fc", 0.22, True),
                        ("winterp", 10.0, "#f97316", 0.85, True),
                        ("winterp", -5.0, "#3b82f6", 0.7, False),
                        ("zvort", 0.05, "#e11d48", 0.95, False)]
        first3d = next(iter(next(iter(g3.values())).values()))
        self.isos = []
        for var, val, col, op, on in iso_defaults:
            if var not in F:
                var, on = first3d, False
            self.isos.append(dict(
                on=pn.widgets.Checkbox(value=on, width=24, margin=(18, 4, 0, 4)),
                var=pn.widgets.Select(name="Field", groups=g3, value=var, width=230),
                val=FloatInput(name="Value", value=val, width=90),
                color=pn.widgets.ColorPicker(name="Color", value=col, width=60),
                op=pn.widgets.FloatSlider(name="Opacity", start=0.05, end=1.0, step=0.05,
                                          value=op, width=130),
            ))
        ztop = float(np.floor(run.z[-1]))
        self.v3_ztop = pn.widgets.FloatSlider(name="Top (km)", start=2, end=ztop, step=0.5,
                                              value=min(15.0, ztop), width=150)
        self.v3_exag = pn.widgets.FloatSlider(name="Vertical exaggeration", start=1, end=6,
                                              step=0.5, value=2, width=150)
        self.v3_smooth = pn.widgets.FloatSlider(name="Smoothing σ", start=0, end=3,
                                                step=0.25, value=0.75, width=150)
        self.v3_res = pn.widgets.Select(name="Resolution",
                                        options={"Auto": 0, "Full": 1, "1/2": 2, "1/3": 3,
                                                 "1/4": 4}, value=0, width=100)
        # the floor: a 2D field, or a 3D field at one height
        fl0 = "cref" if "cref" in F else ("dbz" if "dbz" in F else first3d)
        self.v3_ground = pn.widgets.Checkbox(value=fl0 in ("cref", "dbz"), width=18,
                                             margin=(14, 0, 0, 8))
        self.v3_floor = pn.widgets.Select(name="Field", groups=F.groups(), value=fl0,
                                          width=250)
        self.v3_floor_z = pn.widgets.FloatSlider(name="Height (km AGL; 0 = lowest level)",
                                                 start=0.0, end=min(10.0, ztop), step=0.05,
                                                 value=0.0, width=210)
        self.v3_floor_cmap = pn.widgets.Select(name="Colormap", options=["Field default"] +
                                               CMAPS, value="Field default", width=150)
        self.v3_floor_rev = pn.widgets.Checkbox(name="Reverse", value=False,
                                                margin=(28, 10, 0, 10))
        self.v3_floor_range = pn.widgets.Select(
            name="Range", options={"From the data": "data", "Field default": "field",
                                   "Custom": "custom"}, value="data", width=140)
        self.v3_floor_min = FloatInput(name="Min", value=0.0, width=90,
                                                  visible=False)
        self.v3_floor_max = FloatInput(name="Max", value=1.0, width=90,
                                                  visible=False)
        self.v3_follow = pn.widgets.Checkbox(name="Re-render when time changes", value=True,
                                             margin=(5, 10, 14, 10))
        self.v3_cam = pn.widgets.Select(
            name="View from", options={"Southwest (default)": "oblique", "Above": "top",
                                       "South": "south", "North": "north", "West": "west",
                                       "East": "east"}, value="oblique", width=170)
        self.v3_drag = pn.widgets.Select(
            name="Mouse drag", options={"Rotate": "turntable", "Free rotate": "orbit",
                                        "Move (pan)": "pan", "Zoom": "zoom"},
            value="turntable", width=130)
        self._cam_rev = 0

        # vectors at a height: wind, horizontal vorticity, ... (Widgets._add_sv)
        self.svs = []
        self.sv_list = pn.Column(margin=0, sizing_mode="stretch_width")
        self.sv_add = pn.widgets.Button(name="Add vectors", icon="plus", button_type="primary",
                                        button_style="outline", height=32,
                                        margin=(6, 4, 8, 4))
        self.sv_add.on_click(lambda e: self._add_sv())
        self._add_sv(on=False)

        # streamlines
        self.st_on = pn.widgets.Checkbox(value=False, width=18, margin=(14, 0, 0, 8))
        self.st_z = pn.widgets.FloatSlider(name="Seed height (km AGL)", start=0.0,
                                           end=min(10.0, ztop), step=0.1, value=0.5,
                                           width=180)
        self.st_n = pn.widgets.IntSlider(name="Seeds across (n × n)", start=3, end=30,
                                         value=12, width=170)
        self.st_len = pn.widgets.FloatSlider(name="Max length (km)", start=5, end=150,
                                             step=5, value=40, width=170)
        self.st_dir = pn.widgets.Select(name="Direction",
                                        options={"Forward": "forward", "Backward": "backward",
                                                 "Both": "both"}, value="forward", width=120)
        self.st_frame = pn.widgets.Select(name="Frame", options=FRAMES, value="storm",
                                          width=150)
        self.st_color = pn.widgets.Select(name="Color by",
                                          options={"Height": "z", "Vertical velocity": "w"},
                                          value="z", width=150)
        self.st_seed_pick = pn.widgets.Button(name="Seed box on map", icon="square-dot",
                                              button_type="default", button_style="outline",
                                              height=32, margin=(4, 4),
                                              description="Drag a box on the map: the "
                                                          "streamlines start inside it")
        self.st_seed_clear = pn.widgets.Button(name="Whole region", button_type="light",
                                               button_style="outline", height=32,
                                               margin=(4, 4), visible=False,
                                               description="Seed over the whole 3D region "
                                                           "again")
        self.st_seed_html = _html()

        self.v3_pick = pn.widgets.Button(name="Pick region on map", button_type="default",
                                         button_style="outline", height=34, margin=(5, 3))
        self.v3_view = pn.widgets.Button(name="Use map view", button_type="default",
                                         button_style="outline", height=34, margin=(5, 3))
        self.v3_render = pn.widgets.Button(name="Render 3D", button_type="primary",
                                           icon="cube", height=34, margin=(5, 3))
        self.v3_region = _html(margin=0, align="center")
        self.v3_status = _html('<div class="cv-hint">No 3D region yet: <b>Pick region on '
                               'map</b> (or the <b>3D box</b> tool on the map) and drag a '
                               'box, or <b>Use map view</b>, then <b>Render 3D</b>. Keep it '
                               'storm-scale (≲ 50 km) for full resolution.</div>')
        self.plot3d = Plotly3D(None, sizing_mode="stretch_both", min_height=400,
                               config={"displaylogo": False, "responsive": True},
                               visible=False)
        self._build_streamline_card()

        # ---- analysis panel (right of the map)
        snd_set = pn.FlexBox(self.parcel, self.wunits, self.storm, self.storm_u,
                             self.storm_v, self.avg, self.base_on, self.follow,
                             self.storm_follow, flex_wrap="wrap", align_items="flex-end",
                             gap="0 4px", sizing_mode="stretch_width",
                             styles={"border-top": f"1px solid {GRID}"})
        ps = self.ps
        snd_look = pn.FlexBox(*[ps[k] for k in ("t", "td", "parcel", "base", "lw", "parcel_lw",
                                                "hodo_lw", "prof_lw", "ptop", "tmin", "tmax",
                                                "ring", "htop", "hheights", "shade", "barbs",
                                                "guides")],
                              self.ps_reset, flex_wrap="wrap", align_items="flex-end",
                              gap="0 6px", sizing_mode="stretch_width",
                              styles={"border-top": f"1px solid {GRID}"})
        look_btn = _settings_toggle(snd_look, "palette", "Plot style: colours, line widths, "
                                                         "axis limits")
        snd_opts = pn.Column(
            pn.FlexBox(self.snd_pick, self.mean_btn, self.pin_btn, self.snd_clear, self.compare,
                       _settings_toggle(snd_set, description="Sounding settings: parcel, "
                                                             "storm motion, averaging"),
                       look_btn, flex_wrap="wrap",
                       align_items="center", gap="0 4px", sizing_mode="stretch_width"),
            snd_set, snd_look, sizing_mode="stretch_width", margin=0)
        d = self.xs_drawer = Drawer()
        # as on the map: the fill's style in the fill's pill, what goes over it in the next
        xs_style = d.add("style", "Style", self.xs_fill_style, self.xs_cmap, self.xs_rev,
                         self.xs_auto, self.xs_min, self.xs_max, self.xs_nlev)
        xs_more = d.add("fills", "More fills", pn.Column(
            self.xs_fill_list, self.xs_fill_add, margin=0, sizing_mode="stretch_width"))
        xs_cont = d.add("ov", "Contours", pn.Column(
            self.xs_ov_list, self.xs_ov_add, margin=0, sizing_mode="stretch_width"))
        xs_vec = d.add("vec", "Vectors", pn.Column(
            self.xs_vec_list, self.xs_vec_add,
            _html('<div class="cv-hint" style="margin:0 0 12px">In the plane: the '
                  'along-section component and the vertical one (w for the wind, ζ for '
                  'vorticity).  Several at once.</div>'),
            margin=0, sizing_mode="stretch_width"))
        for b, _ in d.items.values():  # the same pill as the map's layer menus
            b.param.update(height=32, margin=(4, 2), button_type="light")
        xs_layers = (_group(self.xs_fill, xs_style), _group(xs_more, xs_cont, xs_vec))
        for gp in xs_layers:
            gp.margin = (0, 4, 6, 6)
        xs_look = pn.FlexBox(self.xs_smin, self.xs_smax, self.xs_zmin, self.xs_zmax,
                             self.xs_height, self.xs_font, self.xs_grid, self.xs_ab,
                             self.xs_style_reset, flex_wrap="wrap", align_items="flex-end",
                             gap="0 6px", sizing_mode="stretch_width",
                             styles={"border-top": f"1px solid {GRID}"})
        xs = pn.Column(
            pn.FlexBox(*xs_layers, self.xs_ztop,
                       _settings_toggle(xs_look, "palette", "Plot style: axis limits, size, "
                                                            "fonts, grid lines"),
                       flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                       sizing_mode="stretch_width"), xs_look, d.panel,
            self.xs_status, self.xs_pd_btn,
            _bokeh(self.xs_fig, sizing_mode="stretch_width"),
            sizing_mode="stretch_width")
        trk_set = pn.FlexBox(self.trk_metric, self.trk_field, self.trk_sense, self.trk_z,
                             self.trk_smooth, self.trk_kernel, self.trk_radius,
                             self.trk_fix, self.trk_cut, self.trk_stop, self.trk_from,
                             self.trk_to, self.trk_snap, self.trk_near, self.trk_whole,
                             flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                             sizing_mode="stretch_width",
                             styles={"border-top": f"1px solid {GRID}"})
        self.tabs = pn.Tabs(
            ("Sounding", pn.Column(snd_opts, self.snd_msg, self.snd_col, scroll="y-auto",
                                   sizing_mode="stretch_both")),
            ("Cross-section", pn.Column(xs, scroll="y-auto", sizing_mode="stretch_both")),
            ("Track", pn.Column(
                pn.FlexBox(self.trk_how, self.trk_find, self.trk_stop_btn, self.trk_del,
                           self.trk_clear,
                           _settings_toggle(trk_set, description="Tracking settings"),
                           self.trk_advance, flex_wrap="wrap",
                           align_items="center", gap="0 4px", sizing_mode="stretch_width"),
                trk_set,
                self.trk_status,
                self.trk_pane,
                pn.FlexBox(self.trk_path, self.trk_save, self.trk_dl, self.trk_load,
                           flex_wrap="wrap",
                           align_items="flex-end", gap="0 4px", sizing_mode="stretch_width"),
                self.trk_table, scroll="y-auto", sizing_mode="stretch_both")),
            ("Series", pn.Column(
                pn.FlexBox(self.ser_field, self.ser_vmode, self.ser_z, self.ser_z0,
                           self.ser_z1, self.ser_region, self.ser_radius, self.ser_offx,
                           self.ser_offy, self.ser_reduce, self.ser_pct, self.ser_go,
                           self.ser_stop, flex_wrap="wrap", align_items="flex-end",
                           gap="0 4px", sizing_mode="stretch_width"),
                self.ser_status,
                pn.FlexBox(self.ser_pick, self.ser_view, self.ser_remove, self.ser_set_btn,
                           flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                           sizing_mode="stretch_width"),
                self.ser_set, self.ser_plot,
                pn.FlexBox(self.ser_path, self.ser_fmt, self.ser_save, self.ser_dl,
                           self.ser_load, flex_wrap="wrap", align_items="flex-end",
                           gap="0 4px", sizing_mode="stretch_width"),
                self.ser_file_msg, scroll="y-auto", sizing_mode="stretch_both")),
            ("Distribution", pn.Column(
                pn.FlexBox(self.dist_field, self.dist_vmode, self.dist_z, self.dist_z0,
                           self.dist_z1, self.dist_region, self.dist_radius, self.dist_offx,
                           self.dist_offy, self.dist_lo, self.dist_hi, self.dist_go,
                           self.dist_follow, flex_wrap="wrap", align_items="flex-end",
                           gap="0 4px", sizing_mode="stretch_width"),
                self.dist_status,
                pn.FlexBox(self.dist_pick, self.dist_remove, self.dist_clear,
                           self.dist_to_fig, flex_wrap="wrap", align_items="flex-end",
                           gap="0 4px", sizing_mode="stretch_width"),
                pn.FlexBox(self.dist_kind, self.dist_norm, self.dist_bins, self.dist_cum,
                           self.dist_whis, self.dist_logy, self.dist_x0, self.dist_x1,
                           flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                           sizing_mode="stretch_width",
                           styles={"border-top": f"1px solid {GRID}"}),
                self.dist_plot, self.dist_table, scroll="y-auto",
                sizing_mode="stretch_both")),
            sizing_mode="stretch_both", dynamic=False, margin=0,
            # no tab strip: the tool rail picks the panel (_show_panel)
            stylesheets=[":host > .bk-header { display: none !important; }"])
        # the open tool's panel, right of the map: its name, expand and close
        self.panel_col = pn.Column(
            pn.Row(self.panel_title, pn.Spacer(), self.full_btn, self.panel_btn, margin=0,
                   sizing_mode="stretch_width", styles={"border-bottom": f"1px solid {GRID}"}),
            self.tabs, sizing_mode="stretch_both", margin=(0, 8, 0, 4),
            styles={"flex": "1 1 48%", "min-width": "0"})

    def _top_bar(self):
        """Run, time and workspace pills floating across the top of the window."""
        self.ws_group = _group(self.workspace)  # Map | 3D | Figure
        # the time pill comes last and takes the rest of the row; when the window is
        # too narrow it wraps onto a row of its own, full width
        times = _group(self.t_prev, self.t_play, self.t_next, self.t_speed, self.tslider,
                       self.time_html)
        times.styles = dict(times.styles, flex="1 1 420px", **{"min-width": "0"})
        return pn.Column(
            _bar(self.ws_group, _group(self.run_btn, self.gear_btn),
                 _group(self.storm_btn), times),
            styles=dict(BAR, **{"z-index": "40"}), margin=0, sizing_mode="stretch_width")

    def _map_toolbar(self):
        d = self.map_drawer = Drawer()
        style = d.add("style", "Style", self.fill_style, self.fill_cmap, self.fill_rev,
                      self.fill_auto, self.fill_min, self.fill_max, self.fill_nlev,
                      self.fill_alpha)
        more = d.add("fills", "More fills", pn.Column(self.fill_list, self.fill_add, margin=0,
                                                      sizing_mode="stretch_width"))
        cont = d.add("ov", "Contours", pn.Column(self.ov_list, self.ov_add, margin=0,
                                                 sizing_mode="stretch_width"))
        vec = d.add("vec", "Vectors", pn.Column(
            self.vec_list, self.vec_add,
            _html('<div class="cv-hint" style="margin:0 0 12px">Several at once.  '
                  'Storm-relative wind uses the sounding panel’s storm motion.</div>'),
            margin=0, sizing_mode="stretch_width"))
        for b, _ in d.items.values():
            b.param.update(height=32, margin=(4, 2), button_type="light")
        d.panel.styles = dict(d.panel.styles, **DRAWER)
        # the fill's style sits in the fill's own pill; what goes over it in the next
        bar = _bar(_group(self.fill_var, self.fill_mode, self.fill_lvl, style),
                   _group(more, cont, vec))
        # the tools, down the left edge: each sets what a map click does and opens its
        # panel; the eraser clears every marker on the map
        self.clear_pts.param.update(name="Clear", width=64, height=58, margin=(2, 4),
                                    stylesheets=[RAIL_BTN])
        self.rail = pn.Column(
            *self.mode.btns.values(), pn.Spacer(), self.clear_pts, margin=0, width=72,
            sizing_mode="stretch_height",
            styles={"flex": "0 0 72px", "padding": "6px 0", "align-items": "center",
                    "background": PANEL, "border-right": f"1px solid {GRID}"})
        return pn.Column(bar, d.panel, styles=BAR, margin=0, sizing_mode="stretch_width")

    def _3d_toolbar(self):
        d = self.v3_drawer = Drawer()
        iso_rows = [pn.Row(o["on"], o["var"], o["val"], o["color"], o["op"], margin=0)
                    for o in self.isos]
        iso = d.add("iso", "Isosurfaces", pn.Column(*iso_rows, margin=0))
        sv = d.add("sv", "Vectors", pn.Column(
            self.sv_list, self.sv_add,
            _html('<div class="cv-hint" style="margin:0 0 12px">Arrows at a height '
                  '(0 = lowest level); several at once.  Storm-relative wind uses the '
                  'sounding panel’s storm motion.</div>'),
            margin=0, sizing_mode="stretch_width"))
        st = _pill(self.st_on, d.add("st", "Streamlines", self.st_z, self.st_n, self.st_len,
                                     self.st_dir, self.st_frame, self.st_color,
                                     pn.Row(self.st_seed_pick, self.st_seed_clear, margin=0),
                                     self.st_seed_html))
        fl = _pill(self.v3_ground, d.add(
            "floor", "Floor", self.v3_floor, self.v3_floor_z,
            pn.Row(self.v3_floor_cmap, self.v3_floor_rev, margin=0),
            pn.Row(self.v3_floor_range, self.v3_floor_min, self.v3_floor_max, margin=0),
            _html('<div class="cv-hint" style="margin:0 0 12px">A 2D field, or a 3D field '
                  'at one height, coloured on the ground.  From the data: 1st–99th '
                  'percentiles (symmetric about 0 for signed fields).</div>')))
        scene = d.add("scene", "Scene", self.v3_cam, self.v3_drag, self.v3_ztop, self.v3_exag,
                      self.v3_smooth, self.v3_res, self.v3_follow,
                      _html('<div class="cv-hint" style="margin:0 0 12px">Drag: rotate · '
                            'right-drag: move (or set Mouse drag to Move) · '
                            'scroll: zoom · double-click: reset</div>'))
        for b, _ in d.items.values():
            b.param.update(height=32, margin=(4, 2), button_type="light")
        for b in (self.v3_pick, self.v3_view, self.v3_render):
            b.param.update(height=32, margin=(4, 2))
        d.panel.styles = dict(d.panel.styles, **DRAWER)
        bar = _bar(_group(iso, fl, sv, st, scene),
                   _group(self.v3_region, self.v3_pick, self.v3_view, self.v3_render))
        return pn.Column(bar, d.panel, styles=BAR, margin=0, sizing_mode="stretch_width")

    def main(self):
        floor = {"position": "absolute", "left": "70px", "bottom": "56px", "z-index": "20",
                 "pointer-events": "none", "background": "rgba(11,15,23,0.75)",
                 "border-radius": "8px", "padding": "0 8px"}
        # below the map (not over its corner), in line with the plot's left edge; a
        # fixed height, so a longer hint doesn't resize (and redraw) the map
        for h in (self.map_title, self.hint, self.status):
            h.margin = (2, 0)
        caption = pn.Row(
            pn.Column(self.map_title, self.hint, self.status, margin=0,
                      sizing_mode="stretch_width"), self.pd_row,
            margin=0, sizing_mode="stretch_width",
            styles={"flex": "0 0 auto", "height": "60px", "overflow-y": "auto",
                    "padding": "0 12px 0 60px"})
        self.map_area = map_area = pn.Column(
            self.map_bar, _bokeh(self.fig, sizing_mode="stretch_both",
                                        styles=dict(FILL, position="relative",
                                                    **{"z-index": "0"})),
            self.items_bar, caption, sizing_mode="stretch_both",
            styles={"position": "relative", "flex": "1 1 55%", "min-width": "0"})
        self.map_ws = pn.Row(self.rail, map_area, self.panel_col,
                             sizing_mode="stretch_width", margin=0,
                             styles=FILL)
        self.plot3d.margin = 0
        self.plot3d.styles = dict(FILL, position="relative", **{"z-index": "0"})
        self.v3_ws = pn.Column(
            self.v3_bar, self.plot3d,
            pn.Column(self.v3_status, styles=dict(floor, left="12px", bottom="12px"),
                      margin=0),
            self.sl_card,
            sizing_mode="stretch_width", visible=False, margin=0,
            styles=dict(FILL, position="relative"))
        err = _html(f'<div class="cv-status" style="color:#f87171;padding:4px 8px">'
                    f'{self.error}</div>') if self.error else None
        objs = [o for o in (err,) if o is not None]
        self.fig_ws = pn.Column(self.figed.panel, sizing_mode="stretch_width", visible=False,
                                margin=0, styles=dict(FILL, position="relative"))
        return pn.Column(self._top_bar(), *objs, self.map_ws, self.v3_ws, self.fig_ws,
                         self.rp_modal, self.settings.modal, self.confirm.modal,
                         margin=0, styles={"position": "fixed", "top": "0", "left": "0",
                                           "width": "100vw", "height": "100vh",
                                           "display": "flex", "flex-direction": "column"})

    def _set_full(self, on):
        """Analysis panel over the whole window (map hidden); the sounding graphics
        become zoomable.  The button turns into 'Map' to come back."""
        self.full = on
        self.map_area.visible = not on
        if on:
            self.panel_col.visible = True
        self.panel_col.styles = dict(self.panel_col.styles,
                                     flex="1 1 100%" if on else "1 1 48%")
        self.full_btn.param.update(name="Map" if on else "",
                                   icon="arrows-minimize" if on else "arrows-maximize")
        for z in self._zoom_images():
            z.interactive = on

    def _show_panel(self, show, tab=None):
        """Show (or close) the panel, on tab `tab`.  The tool rail follows the panel:
        opening a tool's panel makes it the active tool."""
        if not show and self.full:
            self._set_full(False)
        self.panel_col.visible = show
        if tab is not None:
            self.tabs.active = tab
            self.panel_title.object = f'<div class="cv-h" style="margin:0">{PANEL_TITLES[tab]}</div>'
            if show and PANELS.get(self.mode.value) != tab:
                self.mode.set(self.snd_pick.value if tab == 0 else TAB_MODE[tab])

    def _on_workspace(self, ev):
        is3d, isfig = ev.new == "3D", ev.new == "Figure"
        self.v3_ws.visible, self.fig_ws.visible = is3d, isfig
        self.map_ws.visible = not (is3d or isfig)
        if is3d and self.box is None:
            self._update_region_html()
        if isfig:
            self.figed.request(delay=False)
            self.figed.opened()
