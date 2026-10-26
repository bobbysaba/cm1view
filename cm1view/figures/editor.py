"""Figure workspace: build a publication figure from panels and layers (from one run or
several, e.g. tornadic vs non-tornadic), preview it at its final size, and export the
image, a stand-alone script, the data and the spec.

The editor has six tabs: Panels (what the grid shows: kind, size, times, titles,
area, runs), Layers (what each panel draws), Tree (each panel alone), Style (fonts,
axes, labels, colorbar, legend, spacing), Annotate and Export (with animated GIFs).
Saving sits above the preview.

The FigureEditor is here (putting the widgets together, wiring them, the layer cards
and rendering the preview); the rest are mixins, one module each: the widgets
(widgets), spec <-> widgets and undo (specio), the panels' times and titles (times),
the Panels tab's reactions (panelopts), runs (runs), sources and lists (sources),
export (export), animations (anim), figures of several parts (combo), placing by
clicking the preview (click), the panel tree (tree), style (style) and the quick start
(quick).  Constants, helpers and cards are in the cards package."""

import base64
import html
import io
import json
import struct
import time as _time
import traceback
from collections import OrderedDict
from functools import partial

import panel as pn

from . import draw as figdraw, spec as fg
from ..core import series as ser
from ..theme import GRID
from .cards import LayerCard
from .anim import FigureAnimation
from .click import ClickImage, FigureClick, place_map, watch_tight
from .combo import FigureCombo, panel_name
from .export import FigureExport
from .runs import AllFields, FigureRuns
from .sources import FigureSources
from .style import FigureStyle
from .panelopts import FigurePanelOpts
from .quick import FigureQuick
from .specio import FigureSpecIO
from .times import FigureTimes
from .tree import FigureTree
from .widgets import FigureWidgets


class FigureEditor(FigureWidgets, FigureSpecIO, FigureTimes, FigurePanelOpts, FigureRuns,
                   FigureSources, FigureExport, FigureAnimation, FigureCombo, FigureClick,
                   FigureTree, FigureStyle, FigureQuick):
    def __init__(self, viewer):
        self.v = viewer
        self.run, self.F = viewer.run, viewer.F
        self.fields = AllFields([self.F])  # the field lists: the fields of every run
        self.cache = OrderedDict()  # data key -> panel arrays
        self._opened = {}  # run path -> (CM1Run, Fields) when the viewer has no registry
        self._tracks = {}  # track file -> (mtime, run path, fixes)
        self._track_err = {}  # track file -> error text
        self._hold = False  # widgets being set from a spec: no re-render per widget
        self._req = 0
        self.cards = []
        self._pf_base = None  # a 'field' figure's fill (Panels → Time and fields), not a card
        self.ser_cards, self.snd_cards, self.dist_cards, self.ann_rows = [], [], [], []
        self.tm_rows, self.title_ws = [], []
        self.parts, self.part_i = [], 0  # a figure of parts (figcombo)
        # undo / redo: (figure JSON with all its parts, part in the widgets) before each
        # change, and the ones undone
        self._hist, self._future, self._last, self._restoring = [], [], None, False
        self._png = None  # (width, height) px and dpi of the shown preview
        self._lims = {}  # panel -> (xlim, ylim) of the last preview, to place annotations
        # series of time-height / time-series figures: (run path, recipe, track) ->
        # dataset (filled in place while it is computed); state "running" / "done"
        self._ser_mem, self._ser_state, self._ser_prog = {}, {}, {}
        self.snd_cache = OrderedDict()  # sounding (run, time, where, track) -> analysis
        self.dist_cache = OrderedDict()  # distribution (run, time, recipe, track) -> summary
        from concurrent.futures import ThreadPoolExecutor
        viewer.pools["figser"] = ThreadPoolExecutor(1, thread_name_prefix="cm1view-figser")
        viewer.gen["figser"] = 0
        self._build()
        self.set_spec(self._default())
        self._started = False  # (the example: the quick start opens over it)
        self._scan_roots()

    # ------------------------------------------------------------ widgets
    def _build(self):
        ib = dict(name="", button_type="light", button_style="outline", width=36, height=32,
                  margin=(4, 2))
        self.new_btn = pn.widgets.Button(
            icon="file-plus", description="New figure: what the panels show, the grid, "
                                          "field and width (Undo takes it back)", **ib)
        self.undo_btn = pn.widgets.Button(icon="arrow-back-up", description="Undo", **ib)
        self.redo_btn = pn.widgets.Button(icon="arrow-forward-up", description="Redo", **ib)
        self._build_panel_widgets()
        self._build_layer_widgets()
        self._build_text()
        self._build_more()
        self._build_anim()
        self._build_style()
        self._build_quick()
        self.plan_layers.append(self.look_row)
        # ---- preview
        self.auto = pn.widgets.Checkbox(name="Live", value=True, margin=(12, 8, 0, 8))
        self.update = pn.widgets.Button(name="Redraw", icon="refresh", height=32,
                                        button_type="primary", button_style="outline",
                                        margin=(4, 4))
        self.zoom = pn.widgets.RadioButtonGroup(
            options={"Fit": "fit", "Actual size": "actual"}, value="fit", height=32,
            margin=(4, 4), description="Actual size: as large as the printed figure "
                                       "(at 96 pixels per inch) to judge the font sizes")
        self.status = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8))
        self.image = ClickImage(sizing_mode="stretch_width", margin=(4, 8))
        self._build_click()

        panels_tab = self._panels_tab()
        layers_tab = pn.Column(self.plan_layers, self.series_col, self.snd_col, self.dist_col,
                               self.ext_sec, self.runs_sec,
                               sizing_mode="stretch_width")
        style_tab = self._style_tab()
        annotate_tab, export_tab = self._more_tabs()
        self.tabs = pn.Tabs(("Panels", panels_tab), ("Layers", layers_tab),
                            ("Tree", self.tree_tab), ("Style", style_tab),
                            ("Annotate", annotate_tab), ("Export", export_tab),
                            dynamic=False, sizing_mode="stretch_width")
        self.tabs.param.watch(lambda e: self._tree_sync() if e.new == 2 else None, "active")
        self.tabs.param.watch(lambda e: self._refresh_saved() if e.new == 5 else None,
                              "active")
        self.editor = pn.Column(
            self.tabs, scroll="y-auto", sizing_mode="stretch_height", width=580,
            styles={"border-left": f"1px solid {GRID}", "padding": "0 8px",
                    "overflow-x": "hidden"})
        self.path.styles = {"flex": "1 1 300px"}
        save_bar = pn.FlexBox(self.path, self.fmt, self.dpi, self.save_img, self.save_all,
                              self.dl, flex_wrap="wrap", align_items="flex-end", gap="0 2px",
                              sizing_mode="stretch_width")
        view_bar = pn.Row(self.update, self.auto, self.new_btn, self.undo_btn, self.redo_btn,
                          self.zoom, self.place_mode, self.status, margin=0,
                          sizing_mode="stretch_width")
        self.preview = pn.Column(
            save_bar, self.msg, view_bar, self.place_hint, self.image, self.quick,
            scroll="y-auto",
            sizing_mode="stretch_both", styles={"min-width": "0"})
        self.panel = pn.Row(self.preview, self.editor, sizing_mode="stretch_both", margin=0)
        self._wire()

    def _wire(self):
        rq = lambda *e: self.request()  # noqa: E731
        for w in (self.kind, self.width, self.height, self.time1, self.suptitle,
                  self.half, self.coords, self.xs_mode, self.xs_angle,
                  self.xs_half, self.xs_offx, self.xs_offy, self.xs_top, self.xs_avg,
                  self.font, self.math,
                  self.fsize, self.fs_tick, self.fs_label, self.fs_title, self.fs_sup,
                  self.fs_legend, self.xlabel, self.ylabel, self.ticklabels, self.share, self.tickdir,
                  self.ticks, self.minor, self.xstep, self.ystep, self.frame_lw, self.grid,
                  self.grid_ls, self.equal, self.title_loc, self.title_bold,
                  self.let_on, self.let_fmt, self.let_loc, self.let_size, self.let_bold,
                  self.let_box, self.tl_on, self.tl_fmt, self.tl_loc, self.tl_size,
                  self.tl_bold, self.tl_box, self.tl_t0, self.rl_on, self.rl_loc,
                  self.rl_size, self.rl_bold, self.rl_box, self.rl_color, self.zl_on,
                  self.zl_fmt, self.zl_loc, self.zl_size, self.zl_bold, self.zl_box,
                  self.cb_mode, self.cb_loc,
                  self.cb_label, self.cb_ticks, self.cb_shrink, self.cb_fraction, self.cb_pad,
                  self.cb_lsize, self.cb_tsize, self.cb_lbold, self.cb_lside, self.cb_fmt,
                  self.lg_where, self.lg_loc, self.lg_anchor, self.lg_panel, self.lg_from,
                  self.lg_title, self.lg_ncol, self.lg_frame, self.lg_own, self.sp_w, self.sp_h,
                  self.sp_wpad, self.sp_hpad,
                  self.bg, self.mplstyle, self.tight, self.pad):
            w.param.watch(rq, "value")
        self.run_sel.param.watch(self._on_run_sel, "value")
        self.cb_mode.param.watch(lambda e: self._show_cbar(), "value")
        self.lg_where.param.watch(lambda e: self._show_legend(), "value")
        for w in (self.rows, self.cols):
            w.param.watch(lambda e: self._on_layout(), "value")
        self.vary.param.watch(lambda e: self._on_vary(), "value")
        self.pz.param.watch(lambda e: self._on_heights(), "value")
        self.pz_mode.param.watch(lambda e: self._on_zmode(), "value")
        self.sk["storm"].param.watch(lambda e: self._show_storm(), "value")
        self.sk["layout"].param.watch(lambda e: self._show_storm(), "value")
        self.sk["inset_loc"].param.watch(lambda e: self._show_storm(), "value")
        self.sk["hodo_center"].param.watch(lambda e: self._show_storm(), "value")
        self.sk["hodo_key"].param.watch(lambda e: self._show_storm(), "value")
        self.sk["hodo_labels"].param.watch(lambda e: self._show_storm(), "value")
        self.code_plain.param.watch(lambda e: self._sync_code(e.new), "value")
        self.code.param.watch(lambda e: self._sync_code(e.new), "value")
        self.code_box.param.watch(lambda e: self._show_code(True), "value")
        self.runs_as.param.watch(lambda e: self._on_vary(), "value")
        self.gg_go.on_click(lambda e: self._fill_grid())
        self.gg_runs.param.watch(self._on_gg_runs, "value")
        self.size_preset.param.watch(self._on_preset, "value")
        self.fit_btn.on_click(lambda e: self._refit())
        self.kind.param.watch(lambda e: self._on_kind(), "value")
        self.dom.param.watch(self._on_dom, "value")
        for w in (self.box_x0, self.box_x1, self.box_y0, self.box_y1):
            w.param.watch(lambda e: self._on_box(), "value")
        self.xs_ab.on_click(lambda e: self._use_ab())
        self.tfill.on_click(lambda e: self._fill_times())
        self.auto_titles.on_click(lambda e: self._auto_titles())
        self.clear_titles.on_click(lambda e: self._set_titles([]))
        for k, b in self.add_btns.items():
            b.on_click(partial(self._add_layer, k))
        self.new_btn.on_click(lambda e: self.open_quick())
        for w in (self.width, self.height):
            w.param.watch(lambda e: self._size_by_hand(), "value")
        self.dist_tab.on_click(lambda e: self._add_tab_dists())
        self.dist_new.on_click(lambda e: self._add_dist())
        for k in ("plot", "stats_at"):
            self.ds[k].param.watch(lambda e: self._show_dist_opts(), "value")
        self.ser_add.on_click(lambda e: self._add_series_from_tab())
        self.ser_new.on_click(lambda e: self._add_series())
        self.snd_tab.on_click(lambda e: self._add_tab_soundings())
        for k in ("layout", "table"):
            self.sk[k].param.watch(lambda e: self._fit_size(), "value")
        self.snd_new.on_click(lambda e: self._add_sounding())
        self.ann_add.on_click(lambda e: self._add_annotation())
        for w in (*self.sk.values(), *self.ds.values(), self.ts_tmin, self.ts_tmax, self.ts_zmin, self.ts_zmax,
                  self.ts_ymin, self.ts_ymax,
                  self.ts_legend, self.ts_legloc, self.ts_legncol, self.ts_legframe, self.ts_zero,
                  self.ts_mark,
                  self.ts_mark_legend, self.ex_on, self.ex_layer, self.ex_what, self.ex_loc,
                  self.ex_marker, self.ex_box, self.ck_on, self.ck_layer,
                  self.ck_label, self.ck_x, self.ck_y, self.ck_size, self.ck_fs,
                  self.ck_frame, self.code_on, self.code):
            w.param.watch(rq, "value")
        self.update.on_click(lambda e: self.request(force=True, delay=False))
        self.undo_btn.on_click(lambda e: self.undo())
        self.redo_btn.on_click(lambda e: self.redo())
        self.zoom.param.watch(lambda e: self._show_image(), "value")
        self.image.param.watch(self._on_click, "click")
        self.image.param.watch(self._on_drag, "drag")
        self.save_img.on_click(lambda e: self._save(False))
        self.save_all.on_click(lambda e: self._save(True))
        self.load_btn.on_click(lambda e: self._load_spec())
        self.saved_pick.param.watch(
            lambda e: setattr(self.spec_path, "value", e.new) if e.new else None, "value")
        for w in (self.fmt, self.path):
            w.param.watch(lambda e: self._set_dl_name(), "value")
        self.fmt.param.watch(rq, "value")
        self.dpi.param.watch(rq, "value")

    # ------------------------------------------------------------ layers
    def _build_cards(self, layers):
        # a long list starts folded: the first layer open, the rest by their titles
        self.cards = [self._card(lay, collapsed=len(layers) > 2 and j > 0)
                      for j, lay in enumerate(layers)]
        self._show_cards()

    def _card(self, lay, collapsed=False):
        c = LayerCard(self, lay, collapsed)
        c.up.on_click(lambda e: self._move(c, -1))
        c.down.on_click(lambda e: self._move(c, 1))
        c.rm.on_click(lambda e: self._remove(c))
        return c

    def _show_cards(self):
        self.layer_box.objects = [c.panel for c in self.cards] or [pn.pane.HTML(
            '<div class="cv-empty">No layers: add one above.</div>')]
        self._show_region()
        self._look_opts()
        opts = {"First contours": -1} | {
            f"{j + 1}. {self.fields[c.w['field'].value].label}": j
            for j, c in enumerate(self.cards) if c.type == "contour"}
        ex_opts = {"First fill": -1} | {
            f"{j + 1}. {self.fields[c.w['field'].value].label}": j
            for j, c in enumerate(self.cards) if c.type in figdraw.EXTREME_TYPES}
        hold, self._hold = self._hold, True
        try:
            for w, o in ((self.ck_layer, opts), (self.ex_layer, ex_opts)):
                v = w.value
                w.options = o
                w.value = v if v in o.values() else -1
        finally:
            self._hold = hold

    def _add_layer(self, kind, ev=None):
        F = self.fields
        field = None
        if kind in ("fill", "contour", "shade"):
            field = {"fill": "dbz", "contour": "winterp", "shade": "winterp"}[kind]
            if field not in F:
                field = next(iter(F.defs))
        lay = fg.layer_defaults(kind, F, field, 1.0)
        if kind == "vectors" and self.kind.value == "xsec":
            lay.update(spacing=0.75, scale=400.0, width=0.0015)
        self.cards.append(self._card(lay))
        self._show_cards()
        self.request()

    def _move(self, c, d):
        i = self.cards.index(c)
        j = min(max(i + d, 0), len(self.cards) - 1)
        self.cards[i], self.cards[j] = self.cards[j], self.cards[i]
        self._show_cards()
        self.request()

    def _remove(self, c):
        self.cards.remove(c)
        self._show_cards()
        self.request()

    # ------------------------------------------------------------ rendering
    def request(self, force=False, delay=True):
        """Re-render the preview (shortly: several quick changes give one render)."""
        if self._hold or not (force or self.auto.value):
            return
        self._req += 1
        n = self._req
        doc = self.v.doc
        if delay and doc is not None:
            doc.add_timeout_callback(partial(self._fire, n), 400)
        else:
            self._fire(n)

    def _fire(self, n):
        if n != self._req:
            return
        try:
            self._prune_runs()
            self._follow_size()
            spec = self.collect_all()  # (several parts: the figure of them)
        except Exception as e:  # noqa: BLE001
            self._status(f"Incomplete settings: {e}", True)
            return
        self._tree_sync()
        self._remember(spec)
        self._anim_refresh(spec)  # (the frames follow the panels' times)
        self.v.gen["fig"] += 1
        g = self.v.gen["fig"]
        self._status('<span class="busy">● Rendering…</span>')
        self._preview_waiting = True  # (a GIF being saved lets it in after a frame)
        self.v.pools["fig"].submit(self._job, g, spec)

    def panel_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of the spec, from the cache where possible."""
        if spec["kind"] == "combo":
            return self._combo_data(spec, progress, cancelled)
        if spec["kind"] in ("th", "line"):
            return self._series_data(spec)
        if spec["kind"] == "sounding":
            return self._sounding_data(spec, progress, cancelled)
        if spec["kind"] == "dist":
            return self._dist_data(spec, progress, cancelled)
        ctx = {}  # run index -> (run, Fields, fixes, centres, track signature)

        def context(k):
            if k not in ctx:
                e = spec["runs"][k]
                run, F = self.open_run(e["path"])
                fx = self.run_fixes(e, run)
                sig = json.dumps(sorted((t, round(f["x"], 4), round(f["y"], 4))
                                        for t, f in fx.items()))
                ctx[k] = (run, F, fx, ser.track_centers(fx, len(run.times)), sig)
            return ctx[k]

        def read(s, i, k, ts, n, at):
            """Arrays of panel i of spec s, read from run k at time ts (for panel `at`)."""
            entry = spec["runs"][k]
            try:
                run, F, fx, centers, sig = context(k)
            except Exception as e:  # noqa: BLE001
                return dict(time_s=ts, missing=f"could not open {entry['path']}: {e}")
            t = fg.tindex(run, ts)
            c = centers.get(t) if t is not None else None
            key = fg.data_key(s, i, c, run.path)
            if any(lay["type"] == "track" or (lay.get("reduce") or {}).get("op") ==
                   "composite" for lay in figdraw.spec_layers(s, i)):
                key += sig  # (a composite follows the whole track)
            d = self.cache.get(key)
            if d is None:
                if progress:
                    progress(at, n)
                storm = fg.storm_motion(run, fx, t) if t is not None else None
                rp = None
                if progress and any(lay.get("reduce") for lay in figdraw.spec_layers(s, i)):
                    def rp(done, total):  # (a time window: one output at a time)
                        self.v._schedule(partial(self._status, (
                            f'<span class="busy">● Time window of panel '
                            f'{panel_name(spec, at)}: output {done + 1}/{total}…</span>')))
                d = fg.extract(run, F, s, i, c, fx, storm, rp)
                self.cache[key] = d
                while len(self.cache) > 60:
                    self.cache.popitem(last=False)
            else:
                self.cache.move_to_end(key)
            return d

        multi = len(spec["runs"]) > 1
        data = {}
        n = fg.npanels(spec)
        for i in range(n):
            if cancelled and cancelled():
                return None
            ref = fg.panel_ref(spec, i)
            if ref is None:
                continue  # an empty cell of a run x time grid
            k, ts = ref
            groups = fg.layer_groups(spec, i)  # (layers of another run or time)
            lays = figdraw.spec_layers(spec, i)
            if not groups:
                d = read(spec, i, k, ts, n, i)
            else:
                others = {j for js in groups.values() for j in js}
                d = read(fg.group_spec(spec, i, ref, set(range(len(lays))) - others), 0,
                         k, ts, n, i)
                for g, js in groups.items():
                    dd = read(fg.group_spec(spec, i, g, set(js)), 0, g[0], g[1], n, i)
                    d = fg.merge_group(d, dd, js, lays)
            for j, lay in enumerate(lays):  # differences: minus another run or time
                if lay["type"] == "fill" and lay.get("minus") and lay.get("on", True):
                    g = fg.minus_ref(spec, i, lay)
                    if g[0] >= len(spec["runs"]):
                        d = dict(d, missing="difference: that run is no longer in the figure")
                        continue
                    dd = read(fg.group_spec(spec, i, g, {j}), 0, g[0], g[1], n, i)
                    d = fg.subtract(d, dd, j, lay["minus"].get("grid", "ask"))
            entry = spec["runs"][k]
            data[i] = dict(d, run=k, **({"run_label": entry.get("label", "")} if multi
                                         else {}))
        return data

    def _job(self, g, spec):
        t0 = _time.time()
        self._preview_waiting = False

        def cancelled():
            return g != self.v.gen["fig"]

        def progress(i, n):
            what = {"sounding": "sounding", "dist": "distribution"}.get(spec["kind"], "panel")
            self.v._schedule(partial(self._status, f'<span class="busy">● Reading {what} '
                                                   f'{i + 1}/{n}…</span>'))

        try:
            data = self.panel_data(spec, progress, cancelled)
            if data is None:
                return
            self._lims = {i: (d["xlim"], d["ylim"]) for i, d in data.items()
                          if "xlim" in d and "ylim" in d and not d.get("missing")}
            fig = figdraw.draw(spec, data)
            code_err = getattr(fig, "_cv_code_error", None)
            watch_tight(fig)  # (where the panels are in the image, for clicks)
            # sharp at the page's size, and on screen at 96 px per inch when actual size
            dpi = min(float(spec["export"]["dpi"]), max(1100.0 / max(spec["size"][0], 0.5),
                                                         192.0))
            buf = io.BytesIO()
            figdraw.save(spec, fig, buf, format="png", **fg.save_kw(spec, dpi))
            raw = buf.getvalue()
            wh = struct.unpack(">II", raw[16:24])  # the PNG header's width and height
            place = place_map(fig, spec, wh, dpi)
            origin = {int(i) % 1000: tuple(d["origin"]) for i, d in data.items()
                      if "origin" in d and (spec["kind"] != "combo" or
                                            int(i) // 1000 == self.part_i)}
            png = base64.b64encode(raw).decode()
            miss = [i for i, d in data.items() if d.get("missing")]
            w_in, h_in = wh[0] / dpi, wh[1] / dpi  # as saved (after trimming)
            note = (f"{len(data)} panel{'s' if len(data) != 1 else ''} · "
                    f"{w_in:.2f} × {h_in:.2f} in as saved "
                    f"({w_in * float(spec['export']['dpi']):.0f} × "
                    f"{h_in * float(spec['export']['dpi']):.0f} px at "
                    f"{spec['export']['dpi']} dpi) · {_time.time() - t0:.1f} s")
            kinds = {p["kind"] for p in spec.get("parts", [spec])}
            pend = self.series_pending() if kinds & {"th", "line"} else []
            if pend:
                note += (' · <span class="busy">● computing series '
                         + "; ".join(p for p in pend if p) + "</span>")
            if code_err:
                note += (' · <span style="color:#f87171">your code stopped at '
                         f'{html.escape(code_err)}</span>')
            if miss:
                note += (f" · no data in panel{'s' if len(miss) > 1 else ''} "
                         + ", ".join(panel_name(spec, i) for i in miss))
                storm = (spec["kind"] == "plan" and spec["domain"]["mode"] == "storm") or \
                    (spec["kind"] == "xsec" and spec["xsec"]["mode"] == "storm")
                if storm and any(not e.get("track") for e in spec["runs"]):
                    note += (" · storm-centred panels need a track for each run (see "
                             "<b>Runs</b>)")
                elif storm and not self.v.fixes and any(e.get("track") == "viewer"
                                                        for e in spec["runs"]):
                    note += (" · storm-centred panels need a track: follow the storm in "
                             "the <b>Track</b> tab (Map), or pick another area in "
                             "<b>Area</b>")
            self.v._schedule(partial(self._apply, g, png, note, (wh, dpi,
                                                                 spec.get("background")),
                                     (place, spec, origin)))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.v._schedule(partial(self._status, f"Could not draw: {e}", True))

    def _apply(self, g, png, note, info=None, place=None):
        if g != self.v.gen["fig"]:
            return
        self._png = (png,) + tuple(info or ((None, None), 100.0, "white"))
        if place is not None:
            self._place, self._place_spec, self._place_origin = place
        self._show_image()
        self._status(note)

    def _show_image(self):
        """The preview: the whole figure in view (within the width and the height left
        under the bars, no scrolling), or at its printed size (96 px per inch)."""
        if not self._png:
            return
        png, (w, h), dpi, bg = self._png
        # a transparent background shows as a checkerboard
        back = ("background:repeating-conic-gradient(#d4d4d4 0% 25%, #fff 0% 50%) 50% / "
                "16px 16px;" if bg == "none" else "")
        if self.zoom.value == "actual" and w:
            size = f"width:{w / dpi * 96:.0f}px;max-width:none;"
        else:
            size = "max-width:100%;max-height:calc(100vh - 230px);width:auto;height:auto;"
        mode = self.place_mode.value
        cursor = "cursor:move;" if mode == "move" else "cursor:crosshair;" if mode else ""
        self.image.param.update(src=f"data:image/png;base64,{png}",
                                css=f"{size}{back}{cursor}display:block;margin:auto;"
                                    "box-shadow:0 4px 18px rgba(0,0,0,.5)")

    def _status(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.status.object = f'<div class="cv-status"{col}>{html}</div>'

    def _msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.msg.object = f'<div class="cv-status"{col}>{html}</div>'
