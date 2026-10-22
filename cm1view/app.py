"""Panel application: the Viewer (one per browser session) and the page.

The Viewer builds the widgets, the map and the page layout, wires the events and runs
the map job here; its feature groups live in mixin modules: sndui (soundings), trackui
(storm tracking), seriesui (series), xsecui (cross-sections), view3dui (3D, pressure
decomposition, streamline pick) and itemsui (the items tray).  Shared UI pieces are in
ui.py, the Figure workspace in figui.py."""

import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import numpy as np
import panel as pn
from bokeh.events import PanStart, RangesUpdate, SelectionGeometry, Tap
from bokeh.models import (
    BoxSelectTool, BoxZoomTool, ColorBar, ColumnDataSource, CustomJS, HoverTool,
    LinearColorMapper, PanTool, Range1d, ResetTool, SaveTool, WheelZoomTool,
)
from bokeh.plotting import figure
from bokeh.transform import transform

from . import config, figui, pdecomp, render, sounding_plot as sp, track as trk, volume3d
from .run import FileBusy, MissingAtTime
from .fields import CMAPS, palette
from .picker import RunPicker
from .settings import ConfirmOverwrite, Settings
from .zoomview import ParamTable, ZoomImage
from .theme import ACCENT, BG, CSS, GRID, MUTED, PANEL, Fast
from .ui import (
    BAR, DRAWER, EMPTY_LINES, EMPTY_VEC, FILL, FRAMES, KEEP_ASPECT_JS, LEVEL_MODES, ON,
    PANEL_TITLES, PANELS, RAIL_BTN, TAB_MODE, TIME_BAR, Drawer, ToolRail, _bar, _bokeh,
    _cbar_label, _group, _html, _pill, _settings_toggle, style_fig,
)
# the Viewer's feature groups, one module each
from .itemsui import ItemsTray
from .sndui import SoundingPanel
from .seriesui import SeriesPanel
from .trackui import TrackPanel
from .view3dui import View3DPanel
from .xsecui import SectionPanel


class Viewer(SoundingPanel, TrackPanel, SeriesPanel, SectionPanel, View3DPanel, ItemsTray):
    def __init__(self, run, fields, maxpix=900, error="", reg=None):
        self.run, self.F = run, fields
        self.reg = reg  # the shared runs (figures with panels from other runs)
        self.maxpix = maxpix
        self.error = error
        self.doc = pn.state.curdoc
        self.pools = {k: ThreadPoolExecutor(1, thread_name_prefix=f"cm1view-{k}")
                      for k in ("map", "snd", "xs", "3d", "trk", "sl", "pd", "ser", "fig")}
        self.gen = dict.fromkeys(self.pools, 0)
        # soundings: (kind, where, tpin) with kind "pt" (where = x, y km), "mean"
        # (where = None) or "trk" (where = offset from the tracked meso, km);
        # where may carry a box size, (x, y, width, height) km, for area means;
        # tpin = None follows the time slider, otherwise a pinned time index
        self.points, self.results, self.xs_pts, self.box = [], [], [], None
        self.fixes, self.trk_spec = {}, None  # meso track: {t: fix}, settings used
        self._hold = False
        self._drag_shift = False  # Shift held when the last map drag started
        dxk, dyk = run.dx / 1000.0, run.dy / 1000.0
        self.extent = (run.xh[0] - dxk / 2, run.xh[-1] + dxk / 2,
                       run.yh[0] - dyk / 2, run.yh[-1] + dyk / 2)
        self.view = self.extent
        self._build_widgets()
        self._build_map()
        self._build_xsec()
        self._build_track()
        self._build_series()
        self._build_panels()
        self.map_bar, self.v3_bar = self._map_toolbar(), self._3d_toolbar()
        self.figed = figui.FigureEditor(self)
        self._build_items()
        self._wire()
        # save folders from the settings (followed while the boxes still point there)
        self._auto_dirs = {"series": config.exports_dir(run.path, "series")}
        self._trk_auto = self.trk_path.value
        self._pd_allowed = pdecomp.writes_allowed()
        self.request_map()

    # ================================================================ widgets
    @property
    def t(self):
        return int(self.tslider.value)

    def _level_pair(self, mode="height", value=1.0, compact=False):
        """Level-mode select + level value.  compact: unlabelled spinner for the
        toolbar (arrow keys / wheel step through levels)."""
        run = self.run
        ztop = float(np.floor(run.z[-1] * 10) / 10)
        if compact:
            mode_w = pn.widgets.Select(options=LEVEL_MODES, value=mode, width=140, height=32,
                                       margin=(4, 2))
            lvl = pn.widgets.FloatInput(start=0.0, end=ztop, step=0.25, value=value,
                                        width=70, height=32, margin=(4, 4))
            hstep, names = 0.25, ("", "")
        else:
            mode_w = pn.widgets.Select(name="Level", options=LEVEL_MODES, value=mode,
                                       width=150)
            lvl = pn.widgets.FloatSlider(name="km AGL", start=0.0, end=ztop, step=0.05,
                                         value=value, width=210)
            hstep, names = 0.05, ("Model level k", "km AGL")

        def on_mode(ev):
            if ev.new == "level":
                k = run.level_weights(lvl.value)[0] if ev.old == "height" else 0
                lvl.param.update(start=0, end=run.nk - 1, step=1, value=float(k))
                if names[0]:
                    lvl.name = names[0]
            elif ev.new == "height":
                z = float(run.z[int(lvl.value)]) if ev.old == "level" else 1.0
                lvl.param.update(start=0.0, end=ztop, step=hstep, value=round(z, 2))
                if names[1]:
                    lvl.name = names[1]
            lvl.disabled = ev.new in ("colmax", "colmin")

        mode_w.param.watch(on_mode, "value")
        return mode_w, lvl

    def _build_widgets(self):
        run, F = self.run, self.F
        g_all, g3 = F.groups(), F.groups(ndim=3)
        default_fill = "cref" if "cref" in F else ("dbz" if "dbz" in F else next(iter(F.defs)))

        t0 = 0
        try:  # ?t=<index> in the URL opens at that time
            t0 = int(pn.state.session_args.get("t", [b"0"])[0])
            t0 = min(max(t0, 0), len(run.times) - 1)
        except (AttributeError, TypeError, ValueError):
            pass
        self.tslider = pn.widgets.IntSlider(name="", start=0, end=len(run.times) - 1,
                                            value=t0, show_value=False, min_width=120,
                                            sizing_mode="stretch_width", margin=(4, 12),
                                            align="center", stylesheets=[TIME_BAR])
        btn = dict(button_type="light", button_style="outline", width=34, height=32,
                   name="", icon_size="1.1em", margin=(4, 1))
        self.t_prev = pn.widgets.Button(icon="player-track-prev", **btn)
        self.t_play = pn.widgets.Button(icon="player-play", **btn)
        self.t_next = pn.widgets.Button(icon="player-track-next", **btn)
        self.t_speed = pn.widgets.Select(options={"0.5×": 2400, "1×": 1200, "2×": 600,
                                                  "4×": 300}, value=1200, width=66, height=32,
                                         margin=(4, 4))
        self.playing = False
        self._play_cb = None
        self.time_html = _html(margin=(0, 8, 0, 4), align="center")

        self.workspace = pn.widgets.RadioButtonGroup(
            options=["Map", "3D", "Figure"], value="Map", button_type="primary",
            button_style="outline", width=190, height=32, margin=(4, 2))
        tools = ["Sounding", "Cross-section"] + (["Track"] if trk.available(run) else []) \
            + ["Series", "3D region"]
        self.mode = ToolRail(tools)
        self.hint = _html()
        # the Sounding tool's click: a point, or a dragged box (area mean)
        self.snd_pick = pn.widgets.RadioButtonGroup(
            options={"Click a point": "Sounding", "Drag a box (area mean)": "Area sounding"},
            value="Sounding", button_type="primary", button_style="outline",
            margin=(5, 10, 8, 4), description="What a click on the map makes")
        # the storm track, for everything storm-relative (shown in the top bar)
        self.storm_btn = pn.widgets.Button(
            name="No storm track", icon="tornado", button_type="light",
            button_style="outline", height=32, margin=(4, 2), visible=trk.available(run),
            stylesheets=[ON, ":host(.cv-warn) .bk-btn { color: #fbbf24 !important; }"],
            description="The tracked storm: storm-relative soundings, tracked storm "
                        "motion, series around the storm, figures centred on it. Click to "
                        "make, load or edit the track.")

        # ---- fill layer
        fd = F[default_fill]
        self.fill_var = pn.widgets.Select(groups=g_all, value=default_fill, width=220,
                                          height=32, margin=(4, 2))
        self.fill_mode, self.fill_lvl = self._level_pair("height", 1.0, compact=True)
        self.fill_style = pn.widgets.RadioButtonGroup(
            options={"Pixels": "image", "Filled contours": "contourf"}, value="image",
            button_type="primary", button_style="outline", width=230, margin=(5, 10, 8, 10))
        self.fill_cmap = pn.widgets.Select(name="Colormap", options=CMAPS, value=fd.cmap,
                                           width=150)
        self.fill_rev = pn.widgets.Checkbox(name="Reverse", value=False, margin=(5, 10, 14, 10))
        self.fill_auto = pn.widgets.Checkbox(name="Auto range", value=True,
                                             margin=(5, 10, 14, 10))
        lo, hi = fd.vrange or (0.0, 1.0)
        self.fill_min = pn.widgets.FloatInput(name="Min", value=lo, width=90, disabled=True)
        self.fill_max = pn.widgets.FloatInput(name="Max", value=hi, width=90, disabled=True)
        self.fill_nlev = pn.widgets.IntSlider(name="Contour intervals", start=4, end=30,
                                              value=15, width=160)
        self.fill_alpha = pn.widgets.FloatSlider(name="Opacity", start=0.1, end=1.0,
                                                 step=0.05, value=1.0, width=150)

        # ---- contour overlays
        def overlay(on, var, mode, level, levels, color, width):
            m, lv = self._level_pair(mode, level)
            return dict(
                on=pn.widgets.Checkbox(value=on, width=18, margin=(14, 0, 0, 8)),
                var=pn.widgets.Select(name="Field", groups=g_all, value=var, width=250),
                mode=m, level=lv,
                levels=pn.widgets.TextInput(
                    name="Levels", value=levels, width=190,
                    placeholder="auto  |  5, 10, 20  |  -4:4:1"),
                color=pn.widgets.ColorPicker(name="Color", value=color, width=60),
                width=pn.widgets.FloatSlider(name="Line width", start=0.5, end=4, step=0.25,
                                             value=1.4, width=130),
                negdash=pn.widgets.Checkbox(name="Dash negative", value=True,
                                            margin=(5, 10, 14, 10)),
            )

        ov1 = ("winterp", "height", 3.0, "5, 15, 25", "#ffffff") if "winterp" in F \
            else (default_fill, "height", 1.0, "auto", "#ffffff")
        ov2 = ("thpert", "level", 0.0, "-6, -4, -2, -1", "#60a5fa") if "thpert" in F \
            else (default_fill, "height", 1.0, "auto", "#60a5fa")
        self.ovs = [overlay(True, *ov1, 1.4), overlay(False, *ov2, 1.4)]
        if ov2[1] == "level":
            self.ovs[1]["mode"].value = "level"
            self.ovs[1]["level"].value = 0.0

        # ---- vectors
        self.vec_on = pn.widgets.Checkbox(value=False, width=18, margin=(14, 0, 0, 8))
        self.vec_lvl = pn.widgets.FloatSlider(name="Height (km AGL)", start=0.0,
                                              end=float(np.floor(run.z[-1])), step=0.05,
                                              value=0.5, width=190)
        self.vec_frame = pn.widgets.Select(
            name="Frame", options=FRAMES,
            value="grid" if (run.umove or run.vmove) else "ground", width=150)
        self.vec_style = pn.widgets.Select(name="Draw as", options={
            "Arrows": "arrows", "Streamlines": "streamlines"}, value="arrows", width=120)
        self.vec_density = pn.widgets.IntSlider(name="Arrows across view", start=8, end=50,
                                                value=24, width=170)
        self.vec_ref = pn.widgets.FloatInput(name="Ref. speed (m/s)", value=20.0, width=110)
        self.vec_color = pn.widgets.ColorPicker(name="Color", value="#e5e7eb", width=60)

        # ---- sounding options
        self.storm = pn.widgets.Select(
            name="Storm motion", options={"Bunkers right-mover": "rm",
                                          "Bunkers left-mover": "lm",
                                          "0–6 km mean wind": "mean",
                                          "Domain motion (umove, vmove)": "domain",
                                          "Tracked meso motion": "track",
                                          "Custom": "custom"},
            value="rm", width=210)
        self.storm_u = pn.widgets.FloatInput(name="u (m/s)", value=run.umove, width=80,
                                             visible=False)
        self.storm_v = pn.widgets.FloatInput(name="v (m/s)", value=run.vmove, width=80,
                                             visible=False)
        self.parcel = pn.widgets.RadioButtonGroup(
            options={"SB": "sb", "ML": "ml", "MU": "mu"}, value="ml",
            button_type="primary", button_style="outline", width=140, margin=(5, 10, 8, 10))
        self.wunits = pn.widgets.RadioButtonGroup(options=["m/s", "kt"], value="m/s",
                                                  button_type="primary",
                                                  button_style="outline", width=100,
                                                  margin=(5, 10, 8, 10))
        self.avg = pn.widgets.Select(
            name="Column average", options={"Single column": 0.0, "1 km box": 1.0,
                                            "2 km box": 2.0, "5 km box": 5.0,
                                            "10 km box": 10.0},
            value=0.0, width=130)
        self.prof_top = pn.widgets.Select(options=[1, 3, 6, 10, 15], value=6, width=70,
                                          height=30, margin=(2, 6))
        self.compare = pn.widgets.RadioButtonGroup(
            options={"Line styles": "lines", "Colors": "colors", "Tabs": "tabs"},
            value="lines", button_type="primary", button_style="outline", width=230,
            margin=(5, 10, 8, 10), description="How several soundings are shown")
        self.mean_btn = pn.widgets.Button(
            name="Domain mean", button_type="primary", button_style="outline", height=32,
            margin=(5, 4, 8, 10), description="Show the domain-mean sounding (follows time)")
        self.pin_btn = pn.widgets.Button(
            name="📌 Pin this time", button_type="primary", button_style="outline",
            height=32, margin=(5, 4, 8, 4),
            description="Freeze sounding 1 at the current time (the domain mean if there is "
                        "none); move the time slider and sounding 1 follows, so you can "
                        "compare times")
        self.storm_follow = pn.widgets.Checkbox(
            name="Move with tracked storm", value=False, margin=(5, 10, 14, 10),
            disabled=True)  # clicked soundings keep their offset from the tracked meso
        self.snd_clear = pn.widgets.Button(name="Clear", button_type="light",
                                           button_style="outline", height=32,
                                           margin=(5, 4, 8, 4))
        self.base_on = pn.widgets.Checkbox(name="Base state", value=True,
                                           margin=(5, 10, 14, 10))
        self.follow = pn.widgets.Checkbox(name="Follow time", value=True,
                                          margin=(5, 10, 14, 10))

        # ---- sounding plot style (redraws only) and zoom limits
        st = sp.STYLE
        ck = dict(margin=(5, 10, 14, 10))
        self.ps = dict(
            t=pn.widgets.ColorPicker(name="Temperature", value=st["t_color"], width=86),
            td=pn.widgets.ColorPicker(name="Dewpoint", value=st["td_color"], width=86),
            parcel=pn.widgets.ColorPicker(name="Parcel", value=st["parcel_color"], width=86),
            base=pn.widgets.ColorPicker(name="Base state", value=st["base_color"], width=86),
            lw=pn.widgets.FloatSlider(name="T / Td width", start=0.5, end=5, step=0.1,
                                      value=st["lw"], width=130),
            parcel_lw=pn.widgets.FloatSlider(name="Parcel width", start=0.5, end=4, step=0.1,
                                             value=st["parcel_lw"], width=130),
            hodo_lw=pn.widgets.FloatSlider(name="Hodograph width", start=0.5, end=5, step=0.1,
                                           value=st["hodo_lw"], width=130),
            prof_lw=pn.widgets.FloatSlider(name="Profile width", start=0.5, end=4, step=0.1,
                                           value=st["prof_lw"], width=130),
            ptop=pn.widgets.Select(name="Skew-T top (hPa)", value=100,
                                   options=[100, 150, 200, 250, 300, 400, 500, 600, 700],
                                   width=110),
            tmin=pn.widgets.FloatInput(name="T left (°C)", value=None, placeholder="auto",
                                       width=90),
            tmax=pn.widgets.FloatInput(name="T right (°C)", value=None, placeholder="auto",
                                       width=90),
            ring=pn.widgets.Select(name="Hodograph rings", value=0,
                                   options={"Auto": 0, "5": 5, "10": 10, "20": 20}, width=110),
            htop=pn.widgets.Select(name="Hodograph top (km)", value=12,
                                   options=[3, 6, 9, 12, 15], width=120),
            shade=pn.widgets.Checkbox(name="CAPE / CIN shading", value=st["shade"], **ck),
            barbs=pn.widgets.Checkbox(name="Wind barbs", value=st["barbs"], **ck),
            guides=pn.widgets.Checkbox(name="Adiabats & mixing lines", value=st["guides"], **ck),
        )
        self.ps_reset = pn.widgets.Button(name="Default style", button_type="light",
                                          button_style="outline", height=32,
                                          margin=(5, 4, 8, 10))
        self.snd_lim = {}  # zoom: skew, hodo, prof_z, prof_x (see _on_zoom_box)

        self.status = _html()
        # pressure decomposition for the shown time (map caption / cross-section tab)
        pdb = dict(button_type="warning", button_style="outline", height=30,
                   description=f"Run {pdecomp.script_name()} on this output time "
                               "in a separate process (~45 s and ~40 GB with 4 CPUs, "
                               "~80 s and ~30 GB on one)")
        self.pd_write = pn.widgets.Checkbox(
            name="Write into the output file", value=pdecomp.writes_allowed(),
            disabled=not pdecomp.writes_allowed(), margin=(10, 4, 0, 10),
            styles={"pointer-events": "auto"})  # with the script's own write_data
        self.pd_btn = pn.widgets.Button(margin=(4, 0, 6, 0),
                                        styles={"pointer-events": "auto"}, **pdb)
        self.pd_row = pn.Row(self.pd_btn, self.pd_write, margin=0, visible=False)
        self.xs_pd_btn = pn.widgets.Button(margin=(4, 4), visible=False, **pdb)
        self.cache_html = _html()
        self.clear_btn = pn.widgets.Button(name="Clear cache", button_type="default",
                                           button_style="outline", width=100, height=28,
                                           margin=(2, 6))
        self.clear_pts = pn.widgets.Button(name="", icon="eraser", button_type="light",
                                           button_style="outline", width=40, height=32,
                                           margin=(4, 2),
                                           description="Clear map markers (soundings, "
                                                       "section, 3D region)")
        self.full = False  # analysis panel expanded over the whole window
        self.full_btn = pn.widgets.Button(name="", icon="arrows-maximize", button_type="light",
                                          button_style="outline", height=32, margin=(4, 2),
                                          description="Expand the analysis panel to the full "
                                                      "window (sounding graphics become "
                                                      "zoomable)")
        self.panel_btn = pn.widgets.Button(name="", icon="x", button_type="light",
                                           button_style="outline", width=40, height=32,
                                           margin=(4, 2),
                                           description="Close the panel (the tool stays "
                                                       "on; its button reopens it)")
        self.panel_title = _html(margin=(0, 4), align="center")
        self._build_run_picker()

    def _build_run_picker(self):
        run = self.run
        self.run_btn = pn.widgets.Button(name=run.name, button_type="light",
                                         button_style="outline", height=32,
                                         icon="folder-open", margin=(4, 2),
                                         description=f"{run.path}: open another run",
                                         stylesheets=[".bk-btn { max-width: 260px; "
                                                      "overflow: hidden; white-space: nowrap; "
                                                      "text-overflow: ellipsis; }"])
        self.picker = RunPicker(run.path, extra=(
            _html(f'<div class="cv-h" style="margin-top:14px">This run</div>'
                  f'<div class="cv-run"><b>{run.path}</b><br>{run.ni}×{run.nj}×{run.nk} · '
                  f'Δx {run.dx:.0f} m · {len(run.times)} times · domain motion '
                  f'({run.umove:g}, {run.vmove:g}) m/s</div>'),
            pn.Row(self.cache_html, self.clear_btn)))
        p = self.picker
        self.rp_modal = p.modal
        self.run_btn.on_click(lambda e: p.show())
        self.gear_btn = pn.widgets.Button(
            name="", icon="settings", button_type="light", button_style="outline", width=40,
            height=32, margin=(4, 2), description="Settings: where runs live, where figures "
                                                  "and saved data go, ...")
        self.settings = Settings(run.path)
        self.confirm = ConfirmOverwrite()
        self.gear_btn.on_click(lambda e: self.settings.show())
        self._on_config = lambda: self._schedule(self._config_changed)
        config.on_change(self._on_config)

    # ================================================================ map
    def _build_map(self):
        x0, x1, y0, y1 = self.extent
        fig = figure(sizing_mode="stretch_both", min_height=420,
                     x_range=Range1d(x0, x1), y_range=Range1d(y0, y1),
                     tools="", toolbar_location="right",
                     x_axis_label="x (km)", y_axis_label="y (km)")
        style_fig(fig)
        fig.min_border_top = 10
        fig.toolbar.autohide = True
        fig.toolbar_inner = True  # over the plot's edge, clear of the colorbar label
        outline = fig.rect(x=[(x0 + x1) / 2], y=[(y0 + y1) / 2], width=[x1 - x0],
                           height=[y1 - y0], fill_alpha=0, line_color=GRID, line_width=1)
        outline.nonselection_glyph = outline.glyph
        outline.selection_glyph = outline.glyph
        # shade what lies outside the model domain (the view can extend past it)
        far = 1e5
        fig.quad(left=[-far, x1, x0, x0], right=[x0, far, x1, x1],
                 bottom=[-far, -far, -far, y1], top=[far, far, y0, far],
                 fill_color=BG, fill_alpha=0.55, line_color=None)
        # equal x / y scale at every plot size (e.g. when the side panel opens)
        keep = CustomJS(args=dict(fig=fig, ext=list(self.extent)), code=KEEP_ASPECT_JS)
        fig.js_on_change("inner_width", keep)
        fig.js_on_change("inner_height", keep)
        fig.x_range.on_change("reset_end", self._on_resized)
        fig.y_range.on_change("reset_end", self._on_resized)

        self.mapper = LinearColorMapper(palette=palette("reflectivity"), low=0, high=75,
                                        nan_color="#00000000")
        self.img_src = ColumnDataSource(dict(image=[np.full((2, 2), np.nan, np.float32)],
                                             x=[x0], y=[y0], dw=[x1 - x0], dh=[y1 - y0]))
        self.img_r = fig.image(image="image", x="x", y="y", dw="dw", dh="dh",
                               source=self.img_src, color_mapper=self.mapper)
        self.poly_src = ColumnDataSource(dict(xs=[], ys=[], val=[]))
        self.poly_r = fig.multi_polygons(xs="xs", ys="ys", source=self.poly_src,
                                         fill_color=transform("val", self.mapper),
                                         line_color=None, visible=False)
        self.ov_r = []
        for _ in self.ovs:
            ps, ns = ColumnDataSource(dict(EMPTY_LINES)), ColumnDataSource(dict(EMPTY_LINES))
            pr = fig.multi_line("xs", "ys", source=ps, line_color="#ffffff", line_width=1.4)
            nr = fig.multi_line("xs", "ys", source=ns, line_color="#ffffff", line_width=1.4,
                                line_dash="dashed")
            self.ov_r.append((ps, ns, pr, nr))
        self.vec_src = ColumnDataSource(dict(EMPTY_VEC))
        self.vec_seg = fig.segment("x0", "y0", "x1", "y1", source=self.vec_src,
                                   line_color="#e5e7eb", line_width=1.2)
        self.vec_head = fig.scatter("x1", "y1", source=self.vec_src, marker="triangle",
                                    angle="angle", size=6, color="#e5e7eb")
        self.sl2_src = ColumnDataSource(dict(EMPTY_LINES))
        self.sl2_line = fig.multi_line("xs", "ys", source=self.sl2_src, line_color="#e5e7eb",
                                       line_width=1.1)
        self.sl2_head_src = ColumnDataSource(dict(x=[], y=[], angle=[]))
        self.sl2_head = fig.scatter("x", "y", source=self.sl2_head_src, marker="triangle",
                                    angle="angle", size=7, color="#e5e7eb")

        self.box_src = ColumnDataSource(dict(left=[], right=[], bottom=[], top=[]))
        fig.quad(left="left", right="right", bottom="bottom", top="top", source=self.box_src,
                 fill_color=ACCENT, fill_alpha=0.06, line_color=ACCENT, line_dash="dashed",
                 line_width=1.5)
        self.xs_line_src = ColumnDataSource(dict(x=[], y=[]))
        fig.line("x", "y", source=self.xs_line_src, line_color=ACCENT, line_width=2.5)
        self.xs_pt_src = ColumnDataSource(dict(x=[], y=[], label=[]))
        fig.scatter("x", "y", source=self.xs_pt_src, size=9, fill_color=ACCENT,
                    line_color=BG, line_width=1.5)
        fig.text("x", "y", text="label", source=self.xs_pt_src, x_offset=7, y_offset=-7,
                 text_color=ACCENT, text_font_size="12px", text_font_style="bold")
        # meso track: path, fixes (hover for time/value), and the fix at the shown time
        self.trk_line_src = ColumnDataSource(dict(x=[], y=[]))
        fig.line("x", "y", source=self.trk_line_src, line_color="#fbbf24", line_width=2,
                 line_alpha=0.85)
        self.trk_pts_src = ColumnDataSource(dict(x=[], y=[], hms=[], value=[]))
        trk_pts = fig.scatter("x", "y", source=self.trk_pts_src, size=5, color="#fbbf24",
                              line_color=BG, line_width=0.5)
        self.trk_now_src = ColumnDataSource(dict(x=[], y=[]))
        fig.scatter("x", "y", source=self.trk_now_src, marker="circle_cross", size=17,
                    fill_alpha=0, line_color="#fbbf24", line_width=2.5)
        self.trk_hover = HoverTool(renderers=[trk_pts],
                                   tooltips=[("meso", "@hms"), ("value", "@value{0.000}")])
        self.pbox_src = ColumnDataSource(dict(x=[], y=[], w=[], h=[], color=[]))
        fig.rect("x", "y", "w", "h", source=self.pbox_src, fill_color="color",
                 fill_alpha=0.08, line_color="color", line_width=2, line_dash="dashed")
        self.pt_src = ColumnDataSource(dict(x=[], y=[], color=[], label=[]))
        fig.scatter("x", "y", source=self.pt_src, size=13, fill_color="color",
                    line_color=BG, line_width=2)
        fig.text("x", "y", text="label", source=self.pt_src, x_offset=9, y_offset=-9,
                 text_color="color", text_font_size="13px", text_font_style="bold")

        self.cbar = ColorBar(color_mapper=self.mapper, width=12, padding=6,
                             background_fill_color=BG, major_label_text_color=MUTED,
                             major_tick_line_color=None, bar_line_color=None)
        fig.add_layout(self.cbar, "right")
        self.cbar_label = _cbar_label(fig)

        self.pan, self.wz = PanTool(), WheelZoomTool()
        self.bsel = BoxSelectTool(renderers=[outline], dimensions="both")
        hover = HoverTool(renderers=[self.img_r],
                          tooltips=[("x, y", "$x{0.0}, $y{0.0} km"), ("value", "@image{0.000}")])
        fig.add_tools(self.pan, self.wz, BoxZoomTool(match_aspect=True), self.bsel, hover,
                      self.trk_hover, ResetTool(), SaveTool())
        fig.toolbar.active_drag = self.pan
        fig.toolbar.active_scroll = self.wz
        fig.on_event(Tap, self._on_tap)
        fig.on_event(RangesUpdate, self._on_ranges)
        fig.on_event(SelectionGeometry, self._on_select)
        fig.on_event(PanStart, self._on_pan_start)
        self.fig = fig
        self.map_title = _html()

    # ================================================================ panels
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
                val=pn.widgets.FloatInput(name="Value", value=val, width=90),
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
        self.v3_ground = pn.widgets.Checkbox(name="Composite reflectivity floor",
                                             value="cref" in F, margin=(5, 10, 14, 10))
        self.v3_follow = pn.widgets.Checkbox(name="Re-render when time changes", value=False,
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

        # surface wind vectors
        self.sv_on = pn.widgets.Checkbox(value=False, width=18, margin=(14, 0, 0, 8))
        self.sv_lvl = pn.widgets.FloatSlider(name="Height (km AGL; 0 = lowest level)",
                                             start=0.0, end=3.0, step=0.05, value=0.0,
                                             width=210)
        self.sv_frame = pn.widgets.Select(name="Frame", options=FRAMES,
                                          value=self.vec_frame.value, width=150)
        self.sv_density = pn.widgets.IntSlider(name="Arrows across region", start=6, end=40,
                                               value=16, width=170)
        self.sv_ref = pn.widgets.FloatInput(name="Ref. speed (m/s)", value=20.0, width=110)
        self.sv_color = pn.widgets.ColorPicker(name="Color", value="#f8fafc", width=60)

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
        self.plot3d = pn.pane.Plotly(None, sizing_mode="stretch_both", min_height=400,
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
                                                "ring", "htop", "shade", "barbs", "guides")],
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
        xs_style = d.add("fill", "Fill style", self.xs_cmap, self.xs_rev, self.xs_auto,
                         self.xs_min, self.xs_max)
        xs_cont = d.add("cont", "Contours", self.xs_cont, self.xs_levels, self.xs_ccolor,
                        self.xs_cwidth, self.xs_negdash)
        xs_vec = _pill(self.xs_vecs, d.add("vec", "Winds", self.xs_vframe, self.xs_vdensity,
                                           self.xs_vref, self.xs_vcolor,
                                           _html('<div class="cv-hint" style="margin:0 0 '
                                                 '12px">In-plane wind (along-section u, w)'
                                                 '</div>')))
        for b, _ in d.items.values():  # the same pill as the map's layer menus
            b.param.update(height=32, margin=(4, 2), button_type="light")
        xs_layers = _group(xs_style, xs_cont, xs_vec)
        xs_layers.margin = (0, 4, 6, 6)
        xs = pn.Column(
            pn.FlexBox(self.xs_fill, self.xs_ztop, xs_layers,
                       flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                       sizing_mode="stretch_width"), d.panel,
            self.xs_status, self.xs_pd_btn,
            _bokeh(self.xs_fig, sizing_mode="stretch_width"),
            sizing_mode="stretch_width")
        trk_set = pn.FlexBox(self.trk_metric, self.trk_z, self.trk_smooth, self.trk_kernel,
                             self.trk_radius, self.trk_stop, self.trk_dir, self.trk_snap,
                             self.trk_near, self.trk_whole,
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
        ovb = []
        for n, o in enumerate(self.ovs):
            ovb.append(_pill(o["on"], d.add(f"ov{n}", f"Contours {'AB'[n]}", o["var"],
                                            o["mode"], o["level"], o["levels"], o["color"],
                                            o["width"], o["negdash"])))
        vec = _pill(self.vec_on, d.add("vec", "Winds", self.vec_style, self.vec_lvl,
                                       self.vec_frame, self.vec_density, self.vec_ref,
                                       self.vec_color))
        for b, _ in d.items.values():
            b.param.update(height=32, margin=(4, 2), button_type="light")
        d.panel.styles = dict(d.panel.styles, **DRAWER)
        bar = _bar(_group(self.fill_var, self.fill_mode, self.fill_lvl),
                   _group(style, *ovb, vec))
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
        sv = _pill(self.sv_on, d.add("sv", "Surface winds", self.sv_lvl, self.sv_frame,
                                     self.sv_density, self.sv_ref, self.sv_color,
                                     _html('<div class="cv-hint" style="margin:0 0 12px">'
                                           'Storm-relative uses the sounding panel’s '
                                           'storm motion.</div>')))
        st = _pill(self.st_on, d.add("st", "Streamlines", self.st_z, self.st_n, self.st_len,
                                     self.st_dir, self.st_frame, self.st_color,
                                     _html('<div class="cv-hint" style="margin:0 0 12px">'
                                           'Instantaneous streamlines seeded on an n×n grid '
                                           'over the region.</div>')))
        scene = d.add("scene", "Scene", self.v3_cam, self.v3_drag, self.v3_ztop, self.v3_exag,
                      self.v3_smooth, self.v3_res, self.v3_ground, self.v3_follow,
                      _html('<div class="cv-hint" style="margin:0 0 12px">Drag: rotate · '
                            'right-drag: move (or set Mouse drag to Move) · '
                            'scroll: zoom · double-click: reset</div>'))
        for b, _ in d.items.values():
            b.param.update(height=32, margin=(4, 2), button_type="light")
        for b in (self.v3_pick, self.v3_view, self.v3_render):
            b.param.update(height=32, margin=(4, 2))
        d.panel.styles = dict(d.panel.styles, **DRAWER)
        bar = _bar(_group(iso, sv, st, scene),
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

    # ================================================================ wiring
    def _wire(self):
        rm = lambda *e: self.request_map()  # noqa: E731
        self.tslider.param.watch(self._on_time, "value")
        self.tslider.param.watch(lambda e: self._refresh_panels(), "value_throttled")
        self.t_play.on_click(self._on_play)
        self.t_prev.on_click(lambda e: self._step(-1))
        self.t_next.on_click(lambda e: self._step(1))
        self.t_speed.param.watch(self._on_speed, "value")
        self.mode.watch(self._on_mode)
        self.fill_var.param.watch(self._on_fill_var, "value")
        for w in (self.fill_mode, self.fill_style, self.fill_cmap, self.fill_rev,
                  self.fill_nlev, self.vec_on, self.vec_frame, self.vec_color, self.vec_ref,
                  self.vec_style):
            w.param.watch(rm, "value")

        def vec_vis(*e):
            st = self.vec_style.value == "streamlines"
            self.vec_density.name = "Streamline density" if st else "Arrows across view"
            self.vec_ref.visible = not st

        self.vec_style.param.watch(vec_vis, "value")
        for w in (self.fill_lvl, self.fill_alpha, self.vec_lvl, self.vec_density):
            w.param.watch(rm, "value_throttled")
        self.fill_auto.param.watch(self._on_fill_auto, "value")
        for w in (self.fill_min, self.fill_max):
            w.param.watch(lambda e: None if self.fill_auto.value else self.request_map(),
                          "value")
        for o in self.ovs:
            for k in ("on", "var", "mode", "levels", "color", "negdash"):
                o[k].param.watch(rm, "value")
            for k in ("level", "width"):
                o[k].param.watch(rm, "value_throttled")
        self.storm.param.watch(self._on_storm, "value")
        rs = lambda *e: self.request_soundings()  # noqa: E731
        self.mean_btn.on_click(lambda e: self._add_mean())
        self.pin_btn.on_click(lambda e: self._pin_time())
        self.snd_clear.on_click(self._on_clear_soundings)
        for w in (self.storm_u, self.storm_v, self.parcel, self.wunits, self.avg,
                  self.prof_top, self.base_on, self.compare):
            w.param.watch(rs, "value", precedence=1)  # after the zoom resets below
        rl = lambda *e: self._restyle()  # noqa: E731
        for k, w in self.ps.items():
            w.param.watch(rl, "value_throttled" if isinstance(w, pn.widgets.FloatSlider)
                          else "value")
        self.ps_reset.on_click(self._on_style_reset)

        def unzoom(*keys):
            def f(*e):
                for k in keys:
                    self.snd_lim.pop(k, None)
            return f
        # zoom limits in wind units / below the profile top no longer fit
        # (before the sounding request those changes also trigger)
        self.wunits.param.watch(unzoom("hodo", "prof_x"), "value")
        self.prof_top.param.watch(unzoom("prof_z", "prof_x"), "value")
        rx = lambda *e: self.request_xsec()  # noqa: E731
        for w in (self.xs_cont, self.xs_levels, self.xs_vecs, self.xs_cmap, self.xs_rev,
                  self.xs_ccolor, self.xs_negdash, self.xs_vframe, self.xs_vref,
                  self.xs_vcolor):
            w.param.watch(rx, "value")
        for w in (self.xs_cwidth, self.xs_vdensity):
            w.param.watch(rx, "value_throttled")
        for w in (self.xs_min, self.xs_max):
            w.param.watch(lambda e: None if self.xs_auto.value else self.request_xsec(),
                          "value")
        self.xs_fill.param.watch(self._on_xs_fill, "value")
        self.xs_auto.param.watch(self._on_xs_auto, "value")
        self.xs_ztop.param.watch(rx, "value_throttled")
        self.v3_view.on_click(self._on_use_view)
        self.v3_render.on_click(lambda e: self.request_3d())
        self.v3_pick.on_click(self._on_pick_region)
        self.workspace.param.watch(self._on_workspace, "value")
        self.panel_btn.on_click(lambda e: self._show_panel(False))
        self.mode.reclick = self._on_tool_reclick
        self.snd_pick.param.watch(
            lambda e: self.mode.set(e.new) if self.mode.value in PANELS and
            PANELS[self.mode.value] == 0 else None, "value")
        self.storm_btn.on_click(self._on_storm_btn)
        self.full_btn.on_click(lambda e: self._set_full(not self.full))
        # once a scene is shown or being rendered, 3D settings re-render it
        r3 = lambda *e: self.request_3d() if self.gen["3d"] else None  # noqa: E731
        w3 = [self.v3_ground, self.v3_res, self.sv_on, self.sv_frame, self.sv_ref,
              self.sv_color, self.st_on, self.st_dir, self.st_frame, self.st_color]
        for o in self.isos:
            w3 += [o["on"], o["var"], o["val"], o["color"]]
        for w in w3:
            w.param.watch(r3, "value")
        for w in [self.v3_ztop, self.v3_exag, self.v3_smooth, self.sv_lvl, self.sv_density,
                  self.st_z, self.st_n, self.st_len] + [o["op"] for o in self.isos]:
            w.param.watch(r3, "value_throttled")
        for o in self.isos:
            o["on"].param.watch(lambda e: self._update_3d_labels(), "value")
        self.v3_cam.param.watch(self._on_camera, "value")
        self.v3_drag.param.watch(self._on_drag, "value")
        self.plot3d.param.watch(self._on_3d_click, "click_data")
        self.sl_field.param.watch(lambda e: self._sample_line(), "value")
        self.sl_clear.on_click(lambda e: self._select_line(None))
        self.trk_metric.param.watch(self._on_trk_metric, "value")
        self.trk_whole.param.watch(self._on_trk_whole, "value")
        self.trk_find.on_click(lambda e: (self._show_panel(True, 2),
                                          self.request_track(None, None)))
        self.trk_stop_btn.on_click(lambda e: self._cancel_track())
        self.trk_clear.on_click(self._on_clear_track)
        self.trk_how.param.watch(self._on_trk_how, "value")
        self.trk_del.on_click(self._on_delete_fix)
        self.trk_load.on_click(self._on_load_track)
        self.trk_save.on_click(self._on_save_track)
        self.trk_path.param.watch(self._on_trk_path, "value")
        self.storm_follow.param.watch(lambda e: self._draw_points(), "value")
        self._on_trk_path(None)
        self._trk_preset(self.trk_metric.value)
        self._update_track_view()
        self._update_3d_labels()
        self._update_region_html()
        self.clear_btn.on_click(self._on_clear_cache)
        self.pd_btn.on_click(self._on_pd_compute)
        self.pd_write.param.watch(lambda e: self.request_map(), "value")  # relabel
        self.xs_pd_btn.on_click(self._on_pd_compute)
        self.clear_pts.on_click(self._on_clear_points)
        self._on_mode(None, init=True)
        self._show_panel(False)  # the map gets the full width until a panel is needed
        self._update_time_html()
        self._update_items()
        if self.doc is not None:
            pn.state.add_periodic_callback(self._update_cache_html, period=3000)
        self._update_cache_html()

    def close(self):
        """The browser session ended: stop its jobs and free its threads and data
        (otherwise every page load leaves a thread and ~20 MB behind)."""
        for k in self.gen:
            self.gen[k] += 1  # running jobs see a newer generation and stop
        if self._play_cb is not None:
            self._play_cb.stop()
        for p in self.pools.values():
            p.shutdown(wait=False, cancel_futures=True)
        config.off(self._on_config)
        self._figs, self.results, self._snd_last, self._s3 = {}, [], None, None
        self._closed = True

    _closed = False

    def _config_changed(self):
        """Settings were saved (in this page or another): save boxes still showing the
        old default move to the new folders; the write option follows the setting."""
        new = config.exports_dir(self.run.path, "series")
        if os.path.dirname(config.expand(self.ser_path.value)) == self._auto_dirs["series"]:
            self.ser_path.value = os.path.join(new, os.path.basename(self.ser_path.value))
        self._auto_dirs["series"] = new
        new = self._trk_default()
        if config.expand(self.trk_path.value) == self._trk_auto:
            self.trk_path.value = new
        self._trk_auto = new
        self.figed.config_changed()
        self._track_found = ()  # track_dirs / track_patterns may have changed
        self._update_storm_btn()
        allowed = pdecomp.writes_allowed()
        if allowed != self._pd_allowed:
            self.pd_write.value = self._pd_allowed = allowed
        self.pd_write.disabled = not allowed
        self._pd_button(self.pd_btn, [self.fill_var.value] +
                        [o["var"].value for o in self.ovs if o["on"].value], self.t)
        self._pd_button(self.xs_pd_btn, [self.xs_fill.value, self.xs_cont.value], self.t)

    def _schedule(self, fn):
        if self._closed:  # session gone: late results are dropped
            return
        if self.doc is not None:
            self.doc.add_next_tick_callback(fn)
        else:  # e.g. tests without a server
            fn()

    def _set_status(self, html):
        self.status.object = f'<div class="cv-status">{html}</div>'

    def _status_async(self, html):
        self._schedule(partial(self._set_status, html))

    def _update_time_html(self):
        r = self.run
        self.time_html.object = (f'<div class="cv-time" style="font-size:17px;white-space:nowrap"'
                                 f' title="t = {r.times[self.t]:.0f} s">{r.time_label(self.t)}'
                                 f' <small>{self.t + 1}/{len(r.times)}</small></div>')

    def _update_cache_html(self):
        used, cap, n = self.run.cache_info()
        self.cache_html.object = (f'<div class="cv-status">3D cache: {used:.1f} / {cap:.0f} GB '
                                  f'({n} fields) · {self.run.workers} reader'
                                  f'{"s" if self.run.workers > 1 else ""}</div>')

    # ================================================================ events
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
            None: "Pick a tool on the left (Sounding, Section, Track, Series, 3D box) to "
                  "query the map",
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
        if hasattr(self, "ser_region"):
            opts = self._ser_regions()
            if self.ser_region.options != opts:
                if self.ser_region.value not in opts.values():
                    self.ser_region.param.update(options=opts, value="domain")
                else:
                    self.ser_region.options = opts
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

    # ================================================================ map job
    def _field_storm(self, t):
        """Storm motion for the storm-relative fields (streamwise / crosswise vorticity)
        at time t: the tracked storm's motion where the track has a fix, otherwise the
        domain motion (umove, vmove).  Returns ((u, v), short note, long note)."""
        run = self.run
        if self.fixes:
            m = trk.motion(run, self.fixes).get(t)
            if m is not None and np.all(np.isfinite(m)):
                return (tuple(m), "rel. to tracked motion",
                        f"relative to the tracked storm motion ({m[0]:.1f}, {m[1]:.1f}) m/s")
        why = " (no track fix at this time)" if self.fixes else ""
        return ((run.umove, run.vmove), "rel. to umove/vmove",
                f"relative to the domain motion (umove, vmove) = ({run.umove:g}, "
                f"{run.vmove:g}) m/s{why}")

    def _storm_note(self, names, t):
        """'' or the storm-motion note when any of `names` is storm-relative."""
        if any(n and n in self.F and self.F[n].storm for n in names):
            return self._field_storm(t)
        return None

    def _storm_fields_shown(self):
        names = [self.fill_var.value] + [o["var"].value for o in self.ovs if o["on"].value]
        return any(self.F[n].storm for n in names if n in self.F)

    def _storm_motion(self):
        """Storm motion for storm-relative map vectors (ground-relative m/s)."""
        if self.storm.value == "custom":
            return (self.storm_u.value, self.storm_v.value)
        if self.storm.value == "domain" or not self.results:
            return (self.run.umove, self.run.vmove)
        return tuple(self.results[0][2]["kin"]["storm"])

    def _map_spec(self):
        def lv(mode_w, lvl_w):
            return mode_w.value, float(lvl_w.value)

        fm, fl = lv(self.fill_mode, self.fill_lvl)
        return dict(
            t=self.t, view=self.view, maxpix=self.maxpix, storm=self._storm_motion(),
            fstorm=self._field_storm(self.t)[0],
            fill=dict(var=self.fill_var.value, mode=fm, level=fl, style=self.fill_style.value,
                      cmap=self.fill_cmap.value, rev=self.fill_rev.value,
                      auto=self.fill_auto.value, vmin=self.fill_min.value or 0.0,
                      vmax=self.fill_max.value or 0.0, nlev=self.fill_nlev.value,
                      alpha=self.fill_alpha.value),
            ov=[dict(on=o["on"].value, var=o["var"].value, mode=o["mode"].value,
                     level=float(o["level"].value), levels=o["levels"].value,
                     color=o["color"].value, width=o["width"].value,
                     negdash=o["negdash"].value) for o in self.ovs],
            vec=dict(on=self.vec_on.value, level=self.vec_lvl.value, frame=self.vec_frame.value,
                     style=self.vec_style.value,
                     density=self.vec_density.value, ref=self.vec_ref.value or 20.0,
                     color=self.vec_color.value),
        )

    def request_map(self):
        if self._hold:
            return
        self.gen["map"] += 1
        g, spec = self.gen["map"], self._map_spec()
        self.pools["map"].submit(self._map_job, spec, g)

    def _map_job(self, spec, g):
        if g != self.gen["map"]:
            return
        try:
            if any(pdecomp.is_pdecomp(self.F, n) for n in
                   [spec["fill"]["var"]] + [o["var"] for o in spec["ov"] if o["on"]]):
                pdecomp.source(self.run, spec["t"])  # file version tag, off the page thread
            res = render.compute_map(self.F, spec)
        except (MissingAtTime, FileBusy) as e:  # fields at other times only / being written
            res = e
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["map"]:
            self._schedule(partial(self._apply_map, res, spec, g))

    def _apply_map(self, res, spec, g):
        if g != self.gen["map"]:
            return
        names = [spec["fill"]["var"]] + [o["var"] for o in spec["ov"] if o["on"]]
        self._pd_button(self.pd_btn, names, spec["t"])
        if isinstance(res, Exception):
            if isinstance(res, FileBusy):
                self._set_status(f'<span class="busy">{res}</span>')
            elif isinstance(res, MissingAtTime) and res.name in pdecomp.NAMES:
                self._set_status(f'<span style="color:#fbbf24">{res}.</span>')
            else:
                self._set_status(f'<span style="color:#f87171">Map error: {res}</span>')
            return
        old = self.status.object or ""
        if "Map error" in old or "is not in the output" in old:
            self._set_status("")
        F, run = self.F, self.run
        fill, fs = res.get("fill"), spec["fill"]
        if fill:
            self._last_range = (fill["lo"], fill["hi"])
            self.mapper.update(palette=fill["palette"], low=fill["lo"], high=fill["hi"])
            if fill["style"] == "image":
                self.img_src.data = fill["image"]
                self.poly_src.data = dict(xs=[], ys=[], val=[])
                self.img_r.visible, self.poly_r.visible = True, False
                self.img_r.glyph.global_alpha = fs["alpha"]
            else:
                self.poly_src.data = fill["poly"]
                self.img_r.visible, self.poly_r.visible = False, True
                self.poly_r.glyph.fill_alpha = fs["alpha"]
            note = self._storm_note([fs["var"]], spec["t"])
            self.cbar_label.axis_label = F[fs["var"]].title + (f" · {note[1]}" if note else "")
        for o, ores, (ps, ns, pr, nr) in zip(spec["ov"], res["ov"], self.ov_r):
            if ores is None:
                ps.data, ns.data = dict(EMPTY_LINES), dict(EMPTY_LINES)
                continue
            ps.data, ns.data = ores["pos"], ores["neg"]
            for r in (pr, nr):
                r.glyph.line_color = o["color"]
                r.glyph.line_width = o["width"]
            nr.glyph.line_dash = "dashed" if o["negdash"] else "solid"
        if res["vec"] is not None:
            self.vec_src.data = res["vec"]
            self.vec_seg.glyph.line_color = spec["vec"]["color"]
            self.vec_head.glyph.fill_color = self.vec_head.glyph.line_color = spec["vec"]["color"]
        else:
            self.vec_src.data = dict(EMPTY_VEC)
        if res.get("stream") is not None:
            self.sl2_src.data, self.sl2_head_src.data = res["stream"]
            col = spec["vec"]["color"]
            self.sl2_line.glyph.line_color = col
            self.sl2_head.glyph.fill_color = self.sl2_head.glyph.line_color = col
        else:
            self.sl2_src.data = dict(EMPTY_LINES)
            self.sl2_head_src.data = dict(x=[], y=[], angle=[])

        def lvl_txt(mode, level, name):
            if F[name].ndim == 2:
                return ""
            if mode == "height":
                return f" @ {level:g} km"
            if mode == "level":
                return f" @ k={int(level)} ({run.z[int(level)] * 1000:.0f} m)"
            return " column max" if mode == "colmax" else " column min"

        parts = [f'<b>{F[fs["var"]].label}</b>{lvl_txt(fs["mode"], fs["level"], fs["var"])}']
        for n, o in enumerate(spec["ov"]):
            if o["on"]:
                parts.append(f'<span style="color:{o["color"]}">— {F[o["var"]].label}'
                             f'{lvl_txt(o["mode"], o["level"], o["var"])}</span>')
        self._update_map_labels(spec, lvl_txt)
        note = self._storm_note([fs["var"]] + [o["var"] for o in spec["ov"] if o["on"]],
                                spec["t"])
        if note:
            parts.append(f'<span>storm-relative vorticity {note[2]}</span>')
        if any(pdecomp.is_pdecomp(F, n) for n in names):
            kind, desc = pdecomp.source(run, spec["t"], block=False)
            col = "#fbbf24" if kind == "file-old" else "inherit"
            parts.append(f'<span style="color:{col}">pressure decomposition {desc}</span>')
        stride = res["win"][4]
        parts.append(f'<span>{"full res" if stride == 1 else f"1/{stride} res (zoom for full)"}'
                     f'</span>')
        self.map_title.object = (f'<div class="cv-maptitle">t = {run.time_label(spec["t"])} · '
                                 + " · ".join(parts) + "</div>")

    def _update_map_labels(self, spec, lvl_txt):
        F, d = self.F, self.map_drawer
        for n, o in enumerate(spec["ov"]):
            what = f' · {F[o["var"]].name}{lvl_txt(o["mode"], o["level"], o["var"])}' \
                if o["on"] else ""
            d.label(f"ov{n}", f"Contours {'AB'[n]}{what.replace(' @ ', ' ')}")
        v = spec["vec"]
        d.label("vec", f'Winds · {v["level"]:g} km' if v["on"] else "Winds")


def create_app(reg, maxpix=None):
    pn.extension("plotly", "modal", "tabulator", notifications=False, raw_css=[CSS])
    maxpix = maxpix or config.get("maxpix")
    want, error = None, ""
    try:  # ?run=/path/to/run picks the run directory
        want = pn.state.session_args.get("run", [b""])[0].decode().strip() or None
    except (AttributeError, TypeError, ValueError):
        pass
    run = fields = None
    try:
        if want or reg.default:
            run, fields = reg.get(config.expand(want) if want else None)
    except Exception as e:  # noqa: BLE001
        print(f"cm1view: could not open {want}: {e}", flush=True)
        error = f"Could not open {want}: {e}."
        if want and reg.default:
            error += " Showing the default run instead."
            run, fields = reg.get()
    if run is None:
        body, settings = _landing(error)
    else:
        v = Viewer(run, fields, maxpix=maxpix, error=error, reg=reg)
        pn.state.on_session_destroyed(lambda ctx: v.close())
        body, settings = v.main(), v.settings
    # first run (or settings that no longer work): open the settings window
    if config.needs_setup():
        pn.state.onload(lambda: settings.show(required=True))
    elif config.problems():
        pn.state.onload(lambda: settings.show(flagged=config.problems()))
    # the template only supplies the dark theme: header and margins are hidden so the
    # visualisations fill the window and the controls float over them
    chrome = ("#header{display:none !important} #main{padding:0 !important;"
              "overflow:hidden !important} .card-margin{margin:0 !important}"
              " #container{height:100vh}")
    return pn.template.FastListTemplate(
        title="CM1 View", theme="dark", design=Fast, accent=ACCENT, header_background=BG,
        main=[body], theme_toggle=False, main_layout=None, raw_css=[CSS, chrome])


def _landing(error=""):
    """The page without a run: pick one (and set up cm1view on the first visit)."""
    picker = RunPicker()

    settings = Settings(on_saved=picker.rescan)  # list the runs in the (new) folders
    gear = pn.widgets.Button(name="Settings", icon="settings", button_type="light",
                             button_style="outline", height=32)
    gear.on_click(lambda e: settings.show())
    if not config.needs_setup():
        picker.rescan()
    err = (f'<div class="cv-status" style="color:#f87171">{error}</div>' if error else "")
    head = _html('<div class="cv-maptitle" style="font-size:20px"><b>CM1 View</b></div>'
                 '<div class="cv-hint">Pick a run, or paste the folder it is in.</div>'
                 + err)
    card = pn.Column(pn.Row(head, pn.Spacer(), gear, sizing_mode="stretch_width"),
                     picker.body, width=680, margin=(40, 20), align="center",
                     styles={"background": PANEL, "border": f"1px solid {GRID}",
                             "border-radius": "12px", "padding": "14px 16px 20px 16px"})
    return pn.Column(card, settings.modal, sizing_mode="stretch_both",
                     styles={"overflow-y": "auto"}), settings
