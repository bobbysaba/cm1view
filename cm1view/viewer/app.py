"""Panel application: the Viewer (one per browser session) and the page.

The Viewer is assembled from mixins, one module each: widgets (the drawers' controls),
mapview (the map and its job), layout (the page), events (time, tools, map clicks),
sounding, tracking, series, dist, xsec, view3d (3D, pressure decomposition,
streamline pick) and items (the items tray).  This module builds it, wires the
events and makes the page; shared UI pieces are in ui.py, the Figure workspace in
figures/editor.py."""

import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import panel as pn

from .. import config, pdecomp
from ..figures import editor as figui
from .picker import RunPicker
from .settings import Settings
from ..theme import ACCENT, BG, CSS, GRID, PANEL, Fast
from .ui import PANELS, _html
# the Viewer's feature groups, one module each
from .events import Events
from .layout import Layout
from .mapview import MapView
from .widgets import Widgets
from .dist import DistPanel
from .items import ItemsTray
from .sounding import SoundingPanel
from .series import SeriesPanel
from .tracking import TrackPanel
from .view3d import View3DPanel
from .xsec import SectionPanel


class Viewer(Widgets, MapView, Layout, Events, SoundingPanel, TrackPanel, SeriesPanel,
             DistPanel, SectionPanel, View3DPanel, ItemsTray):
    def __init__(self, run, fields, maxpix=900, error="", reg=None):
        self.run, self.F = run, fields
        self.reg = reg  # the shared runs (figures with panels from other runs)
        self.maxpix = maxpix
        self.error = error
        self.doc = pn.state.curdoc
        self.pools = {k: ThreadPoolExecutor(1, thread_name_prefix=f"cm1view-{k}")
                      for k in ("map", "snd", "xs", "3d", "trk", "sl", "pd", "ser", "dist",
                            "fig")}
        self.gen = dict.fromkeys(self.pools, 0)
        # soundings: (kind, where, tpin) with kind "pt" (where = x, y km), "mean"
        # (where = None) or "trk" (where = offset from the tracked meso, km);
        # where may carry a box size, (x, y, width, height) km, for area means;
        # tpin = None follows the time slider, otherwise a pinned time index
        self.points, self.results, self.xs_pts, self.box = [], [], [], None
        self.seed_box = None  # where 3D streamlines start (None: the whole 3D region)
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
        self._build_dist()
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

    @property
    def t(self):
        return int(self.tslider.value)

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
                  self.fill_nlev):
            w.param.watch(rm, "value")
        for w in (self.fill_lvl, self.fill_alpha):
            w.param.watch(rm, "value_throttled")
        self.fill_auto.param.watch(self._on_fill_auto, "value")
        for w in (self.fill_min, self.fill_max):
            w.param.watch(lambda e: None if self.fill_auto.value else self.request_map(),
                          "value")
        for o in self.ovs:
            self._wire_overlay(o)
        for o in self.vecs:
            self._wire_vec(o)
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
        self.xs_style_reset.on_click(self._on_xs_style_reset)
        for w in (self.xs_smin, self.xs_smax, self.xs_zmin, self.xs_zmax):
            w.param.watch(self._xs_limits, "value")
        for w in (self.xs_height, self.xs_font, self.xs_grid, self.xs_ab):
            w.param.watch(self._xs_look, "value")

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
        for w in (self.xs_cmap, self.xs_rev, self.xs_fill_style):
            w.param.watch(rx, "value")
        self.xs_nlev.param.watch(rx, "value_throttled")
        for o in self.xs_fills:
            self._wire_fill(o, xs=True)
        for o in self.xs_ovs:
            self._wire_overlay(o, xs=True)
        for o in self.xs_vecs:
            self._wire_vec(o, xs=True)
        self._xs_wired = True
        for w in (self.xs_min, self.xs_max):
            w.param.watch(lambda e: None if self.xs_auto.value else self.request_xsec(),
                          "value")
        self.xs_fill.param.watch(self._on_xs_fill, "value")
        self.xs_auto.param.watch(self._on_xs_auto, "value")
        self.xs_ztop.param.watch(rx, "value_throttled")
        self.v3_view.on_click(self._on_use_view)
        self.v3_render.on_click(lambda e: self.request_3d())
        self.v3_pick.on_click(self._on_pick_region)
        self.st_seed_pick.on_click(self._on_pick_seeds)
        self.st_seed_clear.on_click(self._clear_seed_box)
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
        w3 = [self.v3_ground, self.v3_floor, self.v3_floor_cmap, self.v3_floor_rev,
              self.v3_floor_range, self.v3_floor_min, self.v3_floor_max,
              self.v3_res, self.st_on, self.st_dir, self.st_frame, self.st_color]
        for o in self.isos:
            w3 += [o["on"], o["var"], o["val"], o["color"]]
        for w in w3:
            w.param.watch(r3, "value")
        self.v3_floor.param.watch(self._floor_widgets, "value")
        self.v3_floor_range.param.watch(self._floor_widgets, "value")
        self._floor_widgets()
        for o in self.svs:
            self._wire_sv(o)
        self._sv_wired = True
        for w in [self.v3_ztop, self.v3_exag, self.v3_smooth, self.v3_floor_z,
                  self.st_z, self.st_n, self.st_len] + \
                [o["op"] for o in self.isos]:
            w.param.watch(r3, "value_throttled")
        for o in self.isos:
            o["on"].param.watch(lambda e: self._update_3d_labels(), "value")
        self.v3_cam.param.watch(self._on_camera, "value")
        self.v3_drag.param.watch(self._on_drag, "value")
        self.plot3d.param.watch(self._on_3d_click, "click_data")
        self.sl_field.param.watch(lambda e: self._sample_line(), "value")
        self.sl_clear.on_click(lambda e: self._clear_lines())
        self.sl_pin.on_click(self._on_pin)
        self.trk_metric.param.watch(self._on_trk_metric, "value")
        self.trk_whole.param.watch(self._on_trk_whole, "value")
        self.trk_sense.param.watch(lambda e: self._trk_stop_label(), "value")
        self.trk_fix.param.watch(self._on_trk_fix, "value")
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
        self._update_seed_box()
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

    def _layer_request(self, xs):
        """What a layer row's change redraws: the map, or (xs) the cross-section."""
        return (lambda *e: self.request_xsec()) if xs else (lambda *e: self.request_map())

    def _wire_fill(self, o, xs=False):
        rq = self._layer_request(xs)
        hold = "_hold_xs" if xs else "_hold"

        def on_var(ev):  # the field's own colormap and range
            d = self.F[ev.new]
            setattr(self, hold, True)
            try:
                o["cmap"].value, o["rev"].value = d.cmap, False
                if d.vrange:
                    o["vmin"].value, o["vmax"].value = d.vrange
                if "mode" in o:
                    o["mode"].disabled = o["level"].disabled = d.ndim == 2
            finally:
                setattr(self, hold, False)
            rq()

        def on_auto(ev):
            o["vmin"].disabled = o["vmax"].disabled = ev.new
            if not ev.new and o["last"] is not None:
                setattr(self, hold, True)
                o["vmin"].value, o["vmax"].value = [round(v, 4) for v in o["last"]]
                setattr(self, hold, False)
            rq()

        o["var"].param.watch(on_var, "value")
        o["auto"].param.watch(on_auto, "value")
        for k in ("on", "mode", "style", "cmap", "rev", "clip"):
            if k in o:
                o[k].param.watch(rq, "value")
        for k in ("vmin", "vmax"):
            o[k].param.watch(lambda e: None if o["auto"].value else rq(), "value")
        for k in ("level", "alpha"):
            if k in o:
                o[k].param.watch(rq, "value_throttled")

    def _wire_overlay(self, o, xs=False):
        rq = self._layer_request(xs)
        for k in ("on", "var", "mode", "levels", "color", "negdash"):
            if k in o:
                o[k].param.watch(rq, "value")
        for k in ("level", "width"):
            if k in o:
                o[k].param.watch(rq, "value_throttled")

    def _wire_vec(self, o, xs=False):
        """A map (or xs: cross-section) vector layer's widgets redraw it (a new vector:
        its reference arrow first, then one redraw)."""
        rq = self._layer_request(xs)
        for k in ("q", "style"):
            if k in o:
                o[k].param.watch(lambda e: self._vec_vis(o, e), "value")
        for k in ("on", "q", "frame", "style", "ref", "color"):
            if k in o:
                o[k].param.watch(rq, "value")
        for k in ("level", "density"):
            if k in o:
                o[k].param.watch(rq, "value_throttled")

    def _wire_sv(self, o):
        """A 3D vector layer's widgets re-render a scene shown or being rendered."""
        r3 = lambda *e: self.request_3d() if self.gen["3d"] else None  # noqa: E731
        o["q"].param.watch(lambda e: self._vec_vis(o, e), "value")
        for k in ("on", "q", "frame", "ref", "color"):
            o[k].param.watch(r3, "value")
        for k in ("level", "density"):
            o[k].param.watch(r3, "value_throttled")
        for k in ("on", "q"):
            o[k].param.watch(lambda e: self._update_3d_labels(), "value")

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
        self._pd_button(self.pd_btn, self._shown_names(), self.t)
        self._pd_button(self.xs_pd_btn, self._xs_names(), self.t)

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


def create_app(reg, maxpix=None):
    pn.extension("plotly", "modal", "tabulator", "codeeditor", notifications=False,
                 raw_css=[CSS])
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
