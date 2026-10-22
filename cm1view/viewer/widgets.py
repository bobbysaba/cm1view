"""Widgets: the side drawers' controls (field, level, time, tools,
options) and the run picker.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import numpy as np
import panel as pn

from .. import config, pdecomp
from ..core import sounding_plot as sp, track as trk
from ..core.fields import CMAPS
from .picker import RunPicker
from .settings import ConfirmOverwrite, Settings
from .ui import FRAMES, LEVEL_MODES, ON, TIME_BAR, ToolRail, _html


class Widgets:
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
            + ["Series", "Distribution", "3D region"]
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
