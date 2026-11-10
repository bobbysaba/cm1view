"""Soundings: the analysis jobs, the skew-T / hodograph and profile panels (drawn in the
browser: viewer.skewt_view, viewer.profiles_view) and their style.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import traceback
from functools import partial

import numpy as np
import panel as pn

from ..core import sounding_plot as sp, thermo, track as trk
from ..theme import POINT_COLORS, POINT_LABELS
from .profiles_view import ProfilesView, payload as prof_payload
from .skewt_view import SkewTView, payload as skewt_payload
from .ui import BASE_VARS, SOUNDING_VARS, held

_BASE_CACHE = {}  # base-state soundings per run and time (see _base_result)


class SoundingPanel:
    _hold_style = False

    def _add_sounding(self, x, y, add, size=()):
        """A sounding at (x, y) km (a box mean when size = (width, height) km): replaces
        the shown ones, or is added to them (up to 4) when `add`."""
        new = ("pt", (x, y, *size), None)
        meso = trk.position(self.fixes, self.t)
        if self.storm_follow.value:
            if meso is None:
                self._set_status('<span style="color:#fbbf24">No tracked meso at this '
                                 'time; the sounding stays at a fixed point</span>')
            else:
                new = ("trk", (x - meso[0], y - meso[1], *size), None)
        if add and self.points:
            self.points = (self.points + [new])[-4:]
        else:
            self.points = [new]
        self._draw_points()
        self._show_panel(True, 0)
        self.request_soundings()

    def _add_mean(self):
        """Domain-mean sounding that follows the time slider."""
        self.points = [("mean", None, None)]
        self._draw_points()
        self._show_panel(True, 0)
        self.request_soundings()

    def _pin_time(self):
        """Freeze sounding 1 at the current time next to the live one, so moving the
        time slider compares times (the domain mean if nothing is shown yet)."""
        if not self.points:
            self.points = [("mean", None, None)]
        kind, where, _ = self.points[0]
        new = (kind, where, self.t)
        if new not in self.points:
            self.points = self.points[:1] + (self.points[1:] + [new])[-3:]
        self._draw_points()
        self._show_panel(True, 0)
        self.request_soundings()

    def _snd_xy(self, kind, where, t):
        """Map position (km) of a sounding at time index t (None: domain mean, or no
        tracked meso at t)."""
        if kind == "pt":
            return where[:2]
        if kind == "trk":
            meso = trk.position(self.fixes, t)
            return None if meso is None else (meso[0] + where[0], meso[1] + where[1])
        return None

    def _on_clear_soundings(self, ev):
        self.points = []
        self._draw_points()
        self.request_soundings()

    def _draw_points(self):
        pts = [(n, self._snd_xy(kind, where, self.t if tp is None else tp))
               for n, (kind, where, tp) in enumerate(self.points)]
        pts = [(n, xy) for n, xy in pts if xy is not None]
        self.pt_src.data = dict(x=[xy[0] for _, xy in pts], y=[xy[1] for _, xy in pts],
                                color=[POINT_COLORS[n] for n, _ in pts],
                                label=[POINT_LABELS[n] for n, _ in pts])
        boxes = [(n, xy, self.points[n][1][2:]) for n, xy in pts
                 if len(self.points[n][1] or ()) == 4]
        self.pbox_src.data = dict(
            x=[xy[0] for _, xy, _ in boxes], y=[xy[1] for _, xy, _ in boxes],
            w=[wh[0] for _, _, wh in boxes], h=[wh[1] for _, _, wh in boxes],
            color=[POINT_COLORS[n] for n, _, _ in boxes])
        self._update_items()

    # ================================================================ soundings
    def _base_result(self, spec):
        run = self.run
        key = run.path
        if key not in _BASE_CACHE:
            if not all(run.has(v) for v in BASE_VARS):
                return None
            # horizontally uniform: the domain mean is the column, and mean_profiles
            # reads in the reader processes (a column costs a full read anyway)
            _BASE_CACHE[key] = {v: np.asarray(p, np.float32) for v, p in run.mean_profiles(
                BASE_VARS + (("zagl",) if run.terrain else ()), 0).items()}
        b = _BASE_CACHE[key]
        storm, custom = self._item_storm(spec, spec["t"])
        z = b["zagl"] if "zagl" in b else run.z * 1000.0  # (a terrain run's mean, m AGL)
        return thermo.analyze(z, b["prs0"], b["th0"], b["qv0"],
                              b["u0"] + run.umove, b["v0"] + run.vmove, storm=storm,
                              custom=custom, domain=(run.umove, run.vmove))

    @staticmethod
    def _item_storm(spec, t):
        """(storm, custom) for thermo.analyze; 'track' uses the tracked meso's motion
        at time t, falling back to Bunkers right-mover where there is no track."""
        if spec["storm"] != "track":
            return spec["storm"], spec["custom"]
        m = spec["trk_motion"].get(t)
        if m is None or not np.all(np.isfinite(m)):
            return "rm", spec["custom"]
        return "custom", m

    def request_soundings(self):
        if self._applying:  # (a session going back: once, at its end)
            self._due.add("snd")
            return
        self.gen["snd"] += 1
        g = self.gen["snd"]
        if not self.points:
            self.results = []
            self.skew_view.panel.visible = False
            self.prof_view.panel.visible = self.snd_tabs.visible = False
            self.prof_row.visible = False
            self.params.html = ""
            self.snd_head.object = ('<div class="cv-empty">Click anywhere on the map to drop '
                                    'a sounding. <kbd>Shift</kbd>-click to add up to four '
                                    'for comparison.</div>')
            return
        spec = dict(t=self.t, points=list(self.points), avg=float(self.avg.value),
                    storm=self.storm.value,
                    custom=(self.storm_u.value or 0.0, self.storm_v.value or 0.0),
                    parcel=self.parcel.value, units=self.wunits.value,
                    zmax=float(self.prof_top.value), base=self.base_on.value,
                    style=self.compare.value, look=self._look(),
                    xy=[self._snd_xy(k, w, self.t if tp is None else tp)
                        for k, w, tp in self.points],
                    trk_motion=trk.motion(self.run, self.fixes) if self.fixes else {})
        self.snd_col.loading = True
        self.pools["snd"].submit(self._snd_job, spec, g)

    def _snd_job(self, spec, g):
        if g != self.gen["snd"]:
            return
        run, t = self.run, spec["t"]
        # (a terrain run's columns: on their own heights above ground)
        names = SOUNDING_VARS + (("zagl",) if run.terrain else ())
        try:
            def prog_for(tt, what):
                def prog(done, total, name):
                    if total:
                        msg = (f'<div class="cv-status"><span class="busy">● Reading {what} '
                               f'for t = {run.time_label(tt)} ({done}/{total}) {name}… a few '
                               f'seconds per field the first time at each time</span></div>')
                        self._schedule(partial(setattr, self.snd_msg, "object", msg))
                return prog

            # live soundings at the shown time read (and cache) whole 3D fields, so
            # later clicks are instant; pinned other times read just their box, and so
            # do live ones whose fields together do not fit the 3D cache
            if any(kind != "mean" and tp is None for kind, _, tp in spec["points"]):
                if any(run.cached(v, t) is None for v in names) and \
                        run.fits(4 * run.nk * run.nj * run.ni * len(names)):
                    ok = run.load_volumes(names, t, progress=prog_for(t, "3D fields"),
                                          cancelled=lambda: g != self.gen["snd"])
                    if not ok or g != self.gen["snd"]:
                        return
            z = run.z * 1000.0
            h = int(round(spec["avg"] * 1000.0 / run.dx / 2.0))
            items = []
            for n, (kind, where, tp) in enumerate(spec["points"]):
                tt = t if tp is None else tp
                when = "" if tp is None else f" @ {run.time_label(tt)}"
                if kind != "mean":
                    xy = spec["xy"][n]
                    if xy is None:  # storm-following, but no tracked meso at tt
                        continue
                    x, y = xy
                    i, j = run.ij(x, y)
                    hi = hj = h
                    if len(where) == 4:  # area sounding: mean over the dragged box
                        hi = int(round(where[2] * 500.0 / run.dx))
                        hj = int(round(where[3] * 500.0 / run.dy))
                    i0, i1 = max(0, i - hi), min(run.ni, i + hi + 1)
                    j0, j1 = max(0, j - hj), min(run.nj, j + hj + 1)
                    boxes = {}
                    miss = [v for v in names if run.cached(v, tt) is None]
                    if miss:  # (all the uncached fields at once, not one by one)
                        prog_for(tt, "columns")(0, len(names), miss[0])
                        boxes = run.read_boxes(miss, tt, i0, i1, j0, j1)
                        if g != self.gen["snd"]:
                            return
                    c = {}
                    for v in names:
                        vol = run.cached(v, tt)
                        a = boxes[v] if vol is None and v in boxes else (
                            vol[:, j0:j1, i0:i1] if vol is not None
                            else run.read_box(v, tt, i0, i1, j0, j1))
                        c[v] = a.mean(axis=(1, 2), dtype=np.float64)
                    box = (f" box {where[2]:.3g}×{where[3]:.3g} km at" if len(where) == 4
                           else "")
                    if kind == "trk":
                        dx_, dy_ = where[:2]
                        rel = "meso" if dx_ == 0 and dy_ == 0 else f"meso {dx_:+.1f}, {dy_:+.1f}"
                        label = f"{POINT_LABELS[n]}{box} {rel} km{when}"
                    else:
                        label = f"{POINT_LABELS[n]}{box} ({x:.1f}, {y:.1f}) km{when}"
                else:
                    c = run.mean_profiles(names, tt, progress=prog_for(tt, "domain means"))
                    if g != self.gen["snd"]:
                        return
                    label = f"{POINT_LABELS[n]} domain mean {run.time_label(tt)}"
                storm, custom = self._item_storm(spec, tt)
                zc = c["zagl"] if "zagl" in c else z  # (a terrain run's column: its own)
                r = thermo.analyze(zc, c["prs"], c["th"], c["qv"], c["uinterp"] + run.umove,
                                   c["vinterp"] + run.vmove, storm=storm,
                                   custom=custom, domain=(run.umove, run.vmove))
                r["domain"] = (run.umove, run.vmove)
                items.append((label, POINT_COLORS[n], r))
            if not items:
                raise ValueError("no tracked meso at this time for the storm-following "
                                 "sounding(s)")
            base = self._base_result(spec) if spec["base"] else None
            short = [(lab.split(" ")[0] + (" mean" if "mean" in lab else "")
                      + (" box" if " box " in lab else "")
                      + (" meso" if "meso" in lab else "")
                      + (f' {lab.split("@ ")[1]}' if "@ " in lab else ""), c, r)
                     for lab, c, r in items]  # table column headers
            html = sp.params_html(short, base, spec["units"])
            res = (self._draw_figs(items, base, spec), html, items, base)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["snd"]:
            self._schedule(partial(self._apply_snd, res, spec, g))

    def _apply_snd(self, res, spec, g):
        if g != self.gen["snd"]:
            return
        self.snd_msg.object = ""
        if isinstance(res, Exception):
            self.snd_col.loading = False
            self._set_status(f'<span style="color:#f87171">Sounding error: {res}</span>')
            return
        draws, html, items, base = res
        self.results = items
        self._snd_last = (items, base, spec)
        run = self.run
        avg = "single column" if spec["avg"] == 0 else f'{spec["avg"]:g} km box mean'
        if all(k == "mean" or len(w) == 4 for k, w, _ in spec["points"]):
            avg = "area mean"  # the column-average setting applies to point soundings
        pts = " ".join(f'<span style="color:{c};margin-right:14px">{lab}</span>'
                       for lab, c, r in items)
        self.snd_head.object = (f'<div class="cv-maptitle">t = {run.time_label(spec["t"])} · '
                                f'{avg} · {pts}</div>')
        try:
            self._show_figs(draws)
            self.params.html = html
            self.prof_row.visible = True
        finally:  # (after the graphics are on the page: "not loading" means drawn)
            self.snd_col.loading = False
        self._set_status("")
        if self._storm_vecs():
            self.request_map()

    def _draw_figs(self, items, base, spec):
        """[(tab label or None, skew-T/hodograph data (skewt_view.payload), profile panel
        data (profiles_view.payload))]: one entry, or one per sounding in the Tabs
        comparison style."""
        st, look = spec["style"], spec["look"]
        groups = [(it[0], [it]) for it in items] if st == "tabs" and len(items) > 1 \
            else [(None, items)]
        return [(lab,
                 skewt_payload(its, base, spec["parcel"], spec["units"],
                               style="lines" if lab else st, look=look),
                 prof_payload(its, base, spec["zmax"], spec["units"],
                              style="lines" if lab else st, look=look))
                for lab, its in groups]

    def _show_figs(self, draws):
        """Put the sounding graphics on the page (the Bokeh models are reused: only
        their data changes)."""
        if draws[0][0] is None:
            _, ds, pds = draws[0]
            self.skew_view.apply(ds)
            self.prof_view.apply(pds)
            self.skew_view.panel.visible = self.prof_view.panel.visible = True
            self.snd_tabs.visible = False
        else:
            active = self.snd_tabs.active
            names = [lab.replace(" km", "") for lab, *_ in draws]
            if self._snd_tab_names != names:
                self._snd_tab_views = [(SkewTView(), ProfilesView()) for _ in names]
                self.snd_tabs[:] = [(name, pn.Column(sv.panel, pv.panel,
                                                     sizing_mode="stretch_width"))
                                    for name, (sv, pv) in zip(names, self._snd_tab_views)]
                self._snd_tab_names = names
            for (sv, pv), (_, ds, pds) in zip(self._snd_tab_views, draws):
                sv.apply(ds)
                pv.apply(pds)
            self.snd_tabs.active = min(active, len(draws) - 1)
            self.skew_view.panel.visible = self.prof_view.panel.visible = False
            self.snd_tabs.visible = True

    # ---------------------------------------------------------- style
    def _look(self):
        ps = self.ps
        return dict(t_color=ps["t"].value, td_color=ps["td"].value,
                    parcel_color=ps["parcel"].value, base_color=ps["base"].value,
                    lw=ps["lw"].value, parcel_lw=ps["parcel_lw"].value,
                    hodo_lw=ps["hodo_lw"].value, prof_lw=ps["prof_lw"].value,
                    shade=ps["shade"].value, barbs=ps["barbs"].value,
                    guides=ps["guides"].value, ptop=float(ps["ptop"].value),
                    tmin=ps["tmin"].value, tmax=ps["tmax"].value,
                    ring=float(ps["ring"].value) or None, hodo_top=float(ps["htop"].value),
                    hodo_heights=ps["hheights"].value)

    def _restyle(self):
        """Redraw the shown soundings with the current style (no new analysis)."""
        if self._hold_style or not self.points or not getattr(self, "_snd_last", None):
            return
        if self.snd_col.loading:  # a new analysis is on its way: let it use them
            self.request_soundings()
            return
        items, base, spec = self._snd_last
        spec = dict(spec, look=self._look())
        self.gen["snd"] += 1
        g = self.gen["snd"]

        def job():
            try:
                draws = self._draw_figs(items, base, spec)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                draws = e
            if g == self.gen["snd"]:
                self._schedule(partial(apply, draws))

        def apply(draws):
            if g != self.gen["snd"]:
                return
            if isinstance(draws, Exception):
                self._set_status(f'<span style="color:#f87171">Sounding error: {draws}</span>')
                return
            self._snd_last = (items, base, spec)
            self._show_figs(draws)
        self.pools["snd"].submit(job)

    def _on_style_reset(self, ev):
        st = sp.STYLE
        defaults = dict(t=st["t_color"], td=st["td_color"], parcel=st["parcel_color"],
                        base=st["base_color"], lw=st["lw"], parcel_lw=st["parcel_lw"],
                        hodo_lw=st["hodo_lw"], prof_lw=st["prof_lw"], ptop=100, tmin=None,
                        tmax=None, ring=0, htop=12, hheights=st["hodo_heights"],
                        shade=st["shade"], barbs=st["barbs"],
                        guides=st["guides"])
        with held(self, "_hold_style"):
            for k, v in defaults.items():
                self.ps[k].value = v
        self._restyle()
