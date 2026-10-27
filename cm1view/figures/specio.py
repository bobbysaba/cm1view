"""Figure editor: the spec and the widgets (set_spec puts a spec into the widgets,
collect reads it back) and undo / redo.

A mixin of the FigureEditor (figures/editor.py)."""

import json
import re

import panel as pn

from . import draw as figdraw, spec as fg
from .cards import FONTS, LETTERS, MATH_FONTS, NONE, TICKDIR, _num, _xy, _xy_text
from .times import _heights


class FigureSpecIO:
    """spec <-> widgets, and the undo history."""

    # ------------------------------------------------------------ spec <-> widgets
    def set_spec(self, spec):
        """Show `spec` in the widgets (one re-render at the end)."""
        self.spec = spec = fg.normalize(spec, self.run, self._own_track())
        self.edits = json.loads(json.dumps(spec.get("edits") or {}))  # (the panel tree's)
        self.msg.object = ""
        self._started = True  # (no quick start over a figure made from the viewer)
        self.quick.hide()
        self._auto_size = bool(spec.get("size_auto", False))  # until set by hand
        self._hold = True
        try:
            s = spec
            self._build_runs(s["runs"])
            self.kind.value, self.vary.value = s["kind"], s["vary"]
            self.run_sel.value = min(int(s.get("run", 0)), len(s["runs"]) - 1)
            self.runs_as.value = s.get("runs_as", "rows")
            self.rows.value, self.cols.value = int(s["rows"]), int(s["cols"])
            self.width.value, self.height.value = float(s["size"][0]), float(s["size"][1])
            self.size_preset.value = ""
            self.suptitle.value = s.get("suptitle", "")
            d = s["domain"]
            self.dom.value, self.half.value = d["mode"], float(d.get("half", 12.5))
            for w, v in zip((self.box_x0, self.box_x1, self.box_y0, self.box_y1),
                            d.get("box") or [None] * 4):
                w.value = v
            self.coords.value = s.get("coords", "grid")
            x = s["xsec"]
            self.xs_mode.value, self.xs_angle.value = x["mode"], float(x["angle"])
            self.xs_half.value, self.xs_top.value = float(x["half"]), float(x["ztop"])
            self.xs_avg.value = float(x.get("avg") or 0.0)
            self.xs_offx.value, self.xs_offy.value = (float(v) for v in x["offset"])
            a = s["axes"]
            self.xlabel.value, self.ylabel.value = a.get("xlabel", ""), a.get("ylabel", "")
            self.ticklabels.value = a.get("ticklabels", "all")
            self.share.value = a.get("share", "none")
            self.ticks.value, self.minor.value = a.get("ticks", True), a.get("minor", False)
            self.equal.value = a.get("equal", True)
            self.tickdir.value = a.get("tickdir", "out") if a.get("tickdir") in TICKDIR.values() \
                else "out"
            self.xstep.value, self.ystep.value = _num(a.get("xstep")), _num(a.get("ystep"))
            self.frame_lw.value = float(a.get("frame_lw") or 0.8)
            self.grid.value = bool(a.get("grid", False))
            self.grid_ls.value = a.get("grid_ls", ":")
            self.title_loc.value = a.get("title_loc", "center")
            self.title_bold.value = a.get("title_bold", True)
            f = s.get("font", {})
            self.font.value = f.get("family", "sans-serif") if f.get("family") in FONTS \
                else "sans-serif"
            self.math.value = f.get("math", "dejavusans") \
                if f.get("math") in MATH_FONTS.values() else "dejavusans"
            self.fsize.value = float(f.get("size", 10))
            for w, k in ((self.fs_tick, "tick"), (self.fs_label, "label"),
                         (self.fs_title, "title"), (self.fs_sup, "suptitle"),
                         (self.fs_legend, "legend")):
                w.value = _num(f.get(k)) or None
            L = s["letters"]
            self.let_on.value, self.let_loc.value = L.get("on", True), L.get("loc", "upper left")
            self.let_fmt.value = L.get("fmt", "{a}") if L.get("fmt") in LETTERS.values() \
                else "{a}"
            self.let_size.value, self.let_bold.value = float(L.get("size", 12)), \
                L.get("bold", True)
            self.let_box.value = bool(L.get("box", False))
            T = s["time_label"]
            self.tl_on.value, self.tl_fmt.value = T.get("on", True), T.get("fmt", "")
            self.tl_loc.value, self.tl_size.value = T.get("loc", "lower right"), \
                float(T.get("size", 12))
            self.tl_bold.value, self.tl_t0.value = T.get("bold", True), float(T.get("t0_min", 0))
            self.tl_box.value = bool(T.get("box", False))
            R = s.get("run_label", {})
            self.rl_on.value, self.rl_loc.value = R.get("on", True), R.get("loc", "upper left")
            self.rl_size.value, self.rl_bold.value = float(R.get("size", 12)), R.get("bold", True)
            self.rl_box.value = bool(R.get("box", False))
            self.rl_color.value = bool(R.get("run_color", False))
            Z = s.get("z_label", {})
            self.zl_on.value, self.zl_fmt.value = bool(Z.get("on", False)), Z.get("fmt", "")
            self.zl_loc.value = Z.get("loc", "upper right")
            self.zl_size.value, self.zl_bold.value = float(Z.get("size", 12)), Z.get("bold", True)
            self.zl_box.value = bool(Z.get("box", False))
            self.part_share.value = _num(s.get("share"))
            c = s["colorbar"]
            self.cb_mode.value = c.get("mode", "shared")
            self.cb_loc.value = c.get("location") or (
                "bottom" if c.get("orientation", "horizontal" if c.get("mode", "shared")
                                  == "shared" else "vertical") == "horizontal" else "right")
            self.cb_label.value, self.cb_shrink.value = c.get("label", ""), \
                float(c.get("shrink", 0.7))
            self.cb_ticks.value = c.get("ticks", "")
            self.cb_fraction.value = float(c.get("fraction", 0.05))
            self.cb_pad.value = float(c.get("pad", 0.02))
            self.cb_lsize.value = _num(c.get("label_size")) or None
            self.cb_tsize.value = _num(c.get("tick_size")) or None
            self.cb_lbold.value = bool(c.get("label_bold", False))
            self.cb_lside.value = c.get("label_side", "")
            self.cb_fmt.value = c.get("tick_fmt", "")
            lg = s.get("legend", {})
            self.lg_where.value = lg.get("where", "panel")
            self._show_legend()
            self.lg_loc.value, self.lg_panel.value = lg.get("loc", "upper right"), \
                int(lg.get("panel", 0)) + 1
            self.lg_from.value = ", ".join(str(int(i) + 1) for i in lg.get("panels") or [])
            self.lg_title.value = lg.get("title") or ""
            self.lg_ncol.value = int(lg.get("ncol", 1) or 1)
            self.lg_frame.value = lg.get("frame", True)
            self.lg_anchor.value = _xy_text(lg.get("anchor"))
            self.lg_own.value = lg.get("own", True) is not False
            sp = s.get("spacing", {})
            self.sp_w.value, self.sp_h.value = float(sp.get("wspace", 0.02)), \
                float(sp.get("hspace", 0.02))
            self.sp_wpad.value, self.sp_hpad.value = float(sp.get("w_pad", 0.04)), \
                float(sp.get("h_pad", 0.04))
            e = s.get("export", {})
            self.fmt.value, self.dpi.value = e.get("format", "png"), int(e.get("dpi", 250))
            self.tight.value = e.get("tight", True)
            self.pad.value = float(e.get("pad", 0.05))
            self.bg.value = s.get("background", "white")
            self.mplstyle.value = s.get("mplstyle") or ""
            ts = s.get("ts", {})
            self.ts_tmin.value = "" if ts.get("tmin") in (None, "") else f"{float(ts['tmin']):g}"
            self.ts_tmax.value = "" if ts.get("tmax") in (None, "") else f"{float(ts['tmax']):g}"
            self.ts_zmin.value = float(ts.get("zmin") or 0.0)
            self.ts_zmax.value = float(ts.get("zmax") or 10.0)
            self.ts_legend.value, self.ts_zero.value = ts.get("legend", True), \
                ts.get("zero_line", False)
            self.ts_legloc.value = ts.get("legend_loc", "best")
            self.ts_legncol.value = int(ts.get("legend_ncol") or 1)
            self.ts_legframe.value = bool(ts.get("legend_frame", False))
            self.ts_mark.value = ts.get("mark") or ""
            self.ts_mark_legend.value = bool(ts.get("mark_legend", False))
            self.ts_ymin.value, self.ts_ymax.value = _num(ts.get("ymin")), _num(ts.get("ymax"))
            sk = s.get("skewt", {})
            sk = dict(sk, layout=figdraw.sounding_layout(sk),
                      **{f"hodo_{k}": k in figdraw.hodo_marks(sk) for k in figdraw.HODO_MARKS})
            for k, wdg in self.sk.items():
                if k in sk:
                    wdg.value = sk[k] if not isinstance(wdg, pn.widgets.FloatInput) \
                        else float(sk[k])
            dd = s.get("dist", {})
            dd = dict(dd, stats=figdraw.dist_stat_keys(dd), bar_labels=dd.get("bar_labels") or "")
            for k, wdg in self.ds.items():
                if k in dd:
                    wdg.value = (None if dd[k] in (None, "") else float(dd[k])) \
                        if isinstance(wdg, pn.widgets.FloatInput) else dd[k]
            for opts, ws in ((s.get("prof", {}), self.po), (s.get("joint", {}), self.jo),
                             (s.get("azim", {}), self.ao)):
                for k, wdg in ws.items():
                    if k in opts:
                        wdg.value = (None if opts[k] in (None, "") else float(opts[k])) \
                            if isinstance(wdg, pn.widgets.FloatInput) else opts[k]
            ck = s.get("contour_key", {})
            self.ck_on.value, self.ck_label.value = ck.get("on", False), ck.get("label", "w")
            self.ck_x.value, self.ck_y.value = float(ck.get("x", 0.01)), float(ck.get("y", 0.01))
            self.ck_size.value, self.ck_fs.value = float(ck.get("size", 0.1)), \
                float(ck.get("fs", 10.0))
            self.ck_frame.value = ck.get("frame", True)
            code = s.get("code") or {}
            self.code_on.value, self.code.value = bool(code.get("on")), code.get("text") or ""
            self.code_plain.value = self.code.value
            layers, card_of = self._split_pf(s)
            self._build_cards(layers)
            self.ck_layer.value = card_of(ck.get("layer", -1)) \
                if card_of(ck.get("layer", -1)) in self.ck_layer.options.values() else -1
            ex = s.get("extremes", {})
            self.ex_on.value, self.ex_what.value = bool(ex.get("on")), ex.get("what", "both")
            self.ex_loc.value = ex.get("loc", "upper center")
            self.ex_marker.value, self.ex_box.value = ex.get("marker", True), ex.get("box", True)
            self.ex_layer.value = card_of(ex.get("layer", -1)) \
                if card_of(ex.get("layer", -1)) in self.ex_layer.options.values() else -1
            self._refresh_time1(float(s["time_s"]) if s.get("time_s") is not None
                                else self._shown_s(), snap=False)
            self._build_times([NONE if t is None else float(t) for t in s["times_s"]],
                              extend=False, snap=False)
            self._build_pf(s.get("panel_fills", []))
            self.pz_mode.value = s.get("panel_zmode", "height")
            self.pz.value = ", ".join(f"{float(z):g}" for z in s.get("panel_z") or [1, 3, 6])
            self._build_pc(s.get("panels", []))
            self._build_titles(s.get("titles", []))
            self.ser_cards = [self._ser_card(e) for e in s.get("series", [])]
            self.snd_cards = [self._snd_card(e) for e in s.get("soundings", [])]
            self.dist_cards = [self._dist_card(e) for e in s.get("dists", [])]
            self.prof_cards = [self._prof_card(e) for e in s.get("profiles", [])]
            self.joint_cards = [self._joint_card(e) for e in s.get("joints", [])]
            self.azim_cards = [self._azim_card(e) for e in s.get("azims", [])]
            self.ann_rows = [self._ann_row(a) for a in s.get("annotations", [])]
            self._show_series()
            self._show_soundings()
            self._show_dists()
            self._show_profiles()
            self._show_joints()
            self._show_azims()
            self._show_anns()
        finally:
            self._hold = False
        self._show_region()
        self._on_kind(render_=False)
        self._show_vary()
        self._show_cbar()
        self._show_storm()
        self._show_code()
        self._set_dl_name()
        self._tree_sync(force=True)
        self.request(delay=False)

    def _split_pf(self, s):
        """(Layers cards' layers, spec layer index -> card index (-1: none)) of spec s:
        a 'field' figure's first fill is the panels' fill (self._pf_base), not a card."""
        layers = list(s["layers"])
        self._pf_base, k = None, None
        if s.get("vary") == "field":
            k = next((j for j, lay in enumerate(layers) if lay["type"] == "fill"), None)
            self._pf_base = layers.pop(k) if k is not None else self._pf_fill()

        def card_of(j):
            j = int(j)
            return -1 if j < 0 or j == k else j - 1 if k is not None and j > k else j
        return layers, card_of

    def collect(self):
        """The spec of the current widget values."""
        s = dict(self.spec)
        pf = [dict(self._pf_base, on=True)] if self._pf_base is not None else []  # (layer 0)
        tv = self._time_values()
        while tv and tv[-1] == NONE:
            tv.pop()
        times_s = [None if t == NONE else float(t) for t in tv]
        titles = [w.value for w in self.title_ws]
        while titles and not titles[-1].strip():
            titles.pop()
        s.update(
            kind=self.kind.value, vary=self.vary.value, rows=int(self.rows.value or 1),
            cols=int(self.cols.value or 1),
            size=[float(self.width.value or 8), float(self.height.value or 6)],
            size_auto=bool(self._auto_size),
            times=[None if t is None else self._index_of(t) for t in times_s],
            time=self._index_of(float(self.time1.value), one=True),
            times_s=times_s, time_s=float(self.time1.value),
            runs=self._runs_collect(), run=int(self.run_sel.value or 0),
            runs_as=self.runs_as.value,
            panels=[dict(run=int(r["run"].value), time_s=float(r["time"].value))
                    for r in self.pc_rows if r["time"].value is not None],
            layers=pf + [c.collect() for c in self.cards],
            panel_fills=[self._pf_collect(r) for r in self.pf_rows],
            panel_z=_heights(self.pz.value), panel_zmode=self.pz_mode.value,
            share=_num(self.part_share.value),
            suptitle=self.suptitle.value, titles=titles,
            coords=self.coords.value, background=self.bg.value,
            mplstyle=self.mplstyle.value.strip())
        s["domain"] = dict(s["domain"], mode=self.dom.value, half=float(self.half.value or 12.5))
        s["xsec"] = dict(s["xsec"], mode=self.xs_mode.value,
                         angle=float(self.xs_angle.value or 0.0),
                         half=float(self.xs_half.value or 10.0),
                         offset=[float(self.xs_offx.value or 0.0),
                                 float(self.xs_offy.value or 0.0)],
                         ztop=float(self.xs_top.value or 6.0),
                         avg=float(self.xs_avg.value or 0.0))
        s["axes"] = dict(s["axes"], xlabel=self.xlabel.value, ylabel=self.ylabel.value,
                         ticklabels=self.ticklabels.value, share=self.share.value, ticks=self.ticks.value,
                         minor=self.minor.value, equal=self.equal.value,
                         tickdir=self.tickdir.value, xstep=_num(self.xstep.value),
                         ystep=_num(self.ystep.value),
                         frame_lw=float(self.frame_lw.value or 0.8), grid=self.grid.value,
                         grid_ls=self.grid_ls.value, title_loc=self.title_loc.value,
                         title_bold=self.title_bold.value)
        s["font"] = dict(family=self.font.value, size=float(self.fsize.value or 10),
                         math=self.math.value, tick=_num(self.fs_tick.value),
                         label=_num(self.fs_label.value), title=_num(self.fs_title.value),
                         suptitle=_num(self.fs_sup.value), legend=_num(self.fs_legend.value))
        s["letters"] = dict(on=self.let_on.value, fmt=self.let_fmt.value, loc=self.let_loc.value,
                            size=float(self.let_size.value or 12), bold=self.let_bold.value,
                            box=self.let_box.value)
        s["time_label"] = dict(on=self.tl_on.value, fmt=self.tl_fmt.value or "t = {min:g} min",
                               loc=self.tl_loc.value, size=float(self.tl_size.value or 12),
                               bold=self.tl_bold.value, box=self.tl_box.value,
                               t0_min=float(self.tl_t0.value or 0))
        s["run_label"] = dict(on=self.rl_on.value, loc=self.rl_loc.value,
                              size=float(self.rl_size.value or 12), bold=self.rl_bold.value,
                              box=self.rl_box.value, run_color=self.rl_color.value)
        s["z_label"] = dict(on=self.zl_on.value, fmt=self.zl_fmt.value.strip(),
                            loc=self.zl_loc.value, size=float(self.zl_size.value or 12),
                            bold=self.zl_bold.value, box=self.zl_box.value)
        loc = self.cb_loc.value
        s["colorbar"] = dict(s["colorbar"], mode=self.cb_mode.value, location=loc,
                             orientation="horizontal" if loc in ("bottom", "top") else "vertical",
                             label=self.cb_label.value,
                             shrink=float(self.cb_shrink.value or 0.7), ticks=self.cb_ticks.value,
                             fraction=float(self.cb_fraction.value or 0.05),
                             pad=float(self.cb_pad.value or 0.0),
                             label_size=_num(self.cb_lsize.value),
                             tick_size=_num(self.cb_tsize.value),
                             label_bold=self.cb_lbold.value, label_side=self.cb_lside.value,
                             tick_fmt=self.cb_fmt.value.strip())
        s["legend"] = dict(s.get("legend", {}), where=self.lg_where.value,
                           loc=self.lg_loc.value,
                           panel=max(0, int(self.lg_panel.value or 1) - 1),
                           panels=[int(v) - 1 for v in re.findall(r"\d+", self.lg_from.value)
                                   if int(v) > 0],
                           title=self.lg_title.value.strip(),
                           ncol=int(self.lg_ncol.value or 1), frame=self.lg_frame.value,
                           anchor=_xy(self.lg_anchor.value), own=self.lg_own.value)
        s["spacing"] = dict(wspace=float(self.sp_w.value or 0.0),
                            hspace=float(self.sp_h.value or 0.0),
                            w_pad=float(self.sp_wpad.value or 0.0),
                            h_pad=float(self.sp_hpad.value or 0.0))
        s["export"] = dict(format=self.fmt.value, dpi=int(self.dpi.value or 250),
                           tight=self.tight.value, pad=float(self.pad.value or 0.0))

        def minutes(w):
            try:
                return float(w.value) if str(w.value).strip() else None
            except ValueError:
                return None

        s["code"] = dict(on=bool(self.code_on.value), text=self.code.value or "")
        s["series"] = [c.collect() for c in self.ser_cards]
        s["soundings"] = [c.collect() for c in self.snd_cards]
        s["dists"] = [c.collect() for c in self.dist_cards]
        s["dist"] = dict(s.get("dist", {}), **{
            k: _num(w.value) if isinstance(w, pn.widgets.FloatInput) else w.value
            for k, w in self.ds.items()})
        for k, v in (("alpha", 0.35), ("lw", 1.5)):  # (not blank-able)
            if s["dist"][k] is None:
                s["dist"][k] = v
        s["profiles"] = [c.collect() for c in self.prof_cards]
        s["prof"] = dict(s.get("prof", {}), **{
            k: _num(w.value) if isinstance(w, pn.widgets.FloatInput) else w.value
            for k, w in self.po.items()})
        s["joints"] = [c.collect() for c in self.joint_cards]
        s["joint"] = dict(s.get("joint", {}), **{
            k: _num(w.value) if isinstance(w, pn.widgets.FloatInput) else w.value
            for k, w in self.jo.items()})
        for k, v in (("ms", 2.0), ("alpha", 0.5), ("lw", 1.2)):  # (not blank-able)
            if s["joint"][k] is None:
                s["joint"][k] = v
        s["azims"] = [c.collect() for c in self.azim_cards]
        s["azim"] = dict(s.get("azim", {}), **{
            k: _num(w.value) if isinstance(w, pn.widgets.FloatInput) else w.value
            for k, w in self.ao.items()})
        s["annotations"] = [r.collect() for r in self.ann_rows]
        s["ts"] = dict(s.get("ts", {}), tmin=minutes(self.ts_tmin), tmax=minutes(self.ts_tmax),
                       zmin=float(self.ts_zmin.value or 0.0),
                       zmax=float(self.ts_zmax.value or 10.0), legend=self.ts_legend.value,
                       legend_loc=self.ts_legloc.value, legend_ncol=int(self.ts_legncol.value or 1),
                       legend_frame=self.ts_legframe.value, zero_line=self.ts_zero.value,
                       ymin=_num(self.ts_ymin.value), ymax=_num(self.ts_ymax.value),
                       mark=self.ts_mark.value, mark_legend=self.ts_mark_legend.value)
        s["extremes"] = dict(s.get("extremes", {}), on=self.ex_on.value,
                             layer=_spec_index(self.ex_layer.value, len(pf)),
                             what=self.ex_what.value,
                             loc=self.ex_loc.value, marker=self.ex_marker.value,
                             box=self.ex_box.value)
        s["skewt"] = dict(s.get("skewt", {}), **{
            k: (float(w.value or 0.0) if isinstance(w, pn.widgets.FloatInput) else w.value)
            for k, w in self.sk.items()})
        s["edits"] = self._tree_collect()
        s["contour_key"] = dict(s.get("contour_key", {}), on=self.ck_on.value,
                                layer=_spec_index(self.ck_layer.value, len(pf)),
                                label=self.ck_label.value,
                                x=float(self.ck_x.value or 0.0), y=float(self.ck_y.value or 0.0),
                                size=float(self.ck_size.value or 0.1),
                                fs=float(self.ck_fs.value or 10.0), frame=self.ck_frame.value)
        self.spec = s
        return s

    # ------------------------------------------------------------ undo / redo
    def _remember(self, spec):
        """Record a rendered figure (spec: collect_all, so adding, removing and changing
        parts can be undone): the one before it goes on the undo list."""
        j = json.dumps(spec, sort_keys=True, default=float)
        if self._restoring or self._last is None:
            self._restoring = False
        elif j != self._last[0]:
            self._hist = (self._hist + [self._last])[-50:]
            self._future = []
        self._last = (j, self.part_i)  # (switching parts alone is no change)
        self._show_history()

    def _show_history(self):
        self.undo_btn.disabled = not self._hist
        self.redo_btn.disabled = not self._future

    def undo(self):
        if not self._hist:
            return
        self._future.append(self._last)
        self._restore(self._hist.pop())

    def redo(self):
        if not self._future:
            return
        self._hist.append(self._last)
        self._restore(self._future.pop())

    def _restore(self, state):
        j, part = state
        self._last, self._restoring = state, True
        self.set_parts(json.loads(j), part)
        if not self.auto.value:  # (no render to record it)
            self._remember(self.collect_all())


def _spec_index(card, pf):
    """The spec layer index of Layers card `card` (-1: none) when the spec's layers
    start with pf (0 or 1) panel fills."""
    card = int(card)
    return card + pf if card >= 0 else -1
