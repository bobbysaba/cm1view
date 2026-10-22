"""Soundings: the analysis jobs, the skew-T / hodograph / profile graphics,
their style, and zoom / pan by redrawing with axes limits.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import traceback
from functools import partial

import numpy as np
import panel as pn

from ..core import sounding_plot as sp, thermo, track as trk
from ..theme import POINT_COLORS, POINT_LABELS
from .ui import BASE_VARS, SOUNDING_VARS, _svg

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
            _BASE_CACHE[key] = {v: np.asarray(p, np.float32)
                                for v, p in run.mean_profiles(BASE_VARS, 0).items()}
        b = _BASE_CACHE[key]
        storm, custom = self._item_storm(spec, spec["t"])
        return thermo.analyze(run.z * 1000.0, b["prs0"], b["th0"], b["qv0"],
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
        self.gen["snd"] += 1
        g = self.gen["snd"]
        if not self.points:
            self.results = []
            self.skew_png.visible = self.prof_png.visible = self.snd_tabs.visible = False
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
                    style=self.compare.value, look=self._look(), lim=self._lim_copy(),
                    xy=[self._snd_xy(k, w, self.t if tp is None else tp)
                        for k, w, tp in self.points],
                    trk_motion=trk.motion(self.run, self.fixes) if self.fixes else {})
        self.snd_col.loading = True
        self.pools["snd"].submit(self._snd_job, spec, g)

    def _snd_job(self, spec, g):
        if g != self.gen["snd"]:
            return
        run, t = self.run, spec["t"]
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
            # later clicks are instant; pinned other times read just their box
            if any(kind != "mean" and tp is None for kind, _, tp in spec["points"]):
                if any(run.cached(v, t) is None for v in SOUNDING_VARS):
                    ok = run.load_volumes(SOUNDING_VARS, t, progress=prog_for(t, "3D fields"),
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
                    c = {}
                    for v in SOUNDING_VARS:
                        vol = run.cached(v, tt)
                        if vol is None:
                            prog_for(tt, "columns")(SOUNDING_VARS.index(v), len(SOUNDING_VARS), v)
                            a = run.read_box(v, tt, i0, i1, j0, j1)
                        else:
                            a = vol[:, j0:j1, i0:i1]
                        c[v] = a.mean(axis=(1, 2), dtype=np.float64)
                        if g != self.gen["snd"]:
                            return
                    box = (f" box {where[2]:.3g}×{where[3]:.3g} km at" if len(where) == 4
                           else "")
                    if kind == "trk":
                        dx_, dy_ = where[:2]
                        rel = "meso" if dx_ == 0 and dy_ == 0 else f"meso {dx_:+.1f}, {dy_:+.1f}"
                        label = f"{POINT_LABELS[n]}{box} {rel} km{when}"
                    else:
                        label = f"{POINT_LABELS[n]}{box} ({x:.1f}, {y:.1f}) km{when}"
                else:
                    c = run.mean_profiles(SOUNDING_VARS, tt, progress=prog_for(tt, "domain means"))
                    if g != self.gen["snd"]:
                        return
                    label = f"{POINT_LABELS[n]} domain mean {run.time_label(tt)}"
                storm, custom = self._item_storm(spec, tt)
                r = thermo.analyze(z, c["prs"], c["th"], c["qv"], c["uinterp"] + run.umove,
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
        self.snd_col.loading = False
        self.snd_msg.object = ""
        if isinstance(res, Exception):
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
        self._show_figs(draws)
        self.params.html = html
        self.prof_row.visible = True
        self._set_status("")
        if self.vec_on.value and self.vec_frame.value == "storm":
            self.request_map()

    def _draw_figs(self, items, base, spec):
        """[(tab label or None, skew-T/hodograph figure, its SVG, profiles figure, its
        SVG, their hover data)]: one entry, or one per sounding in the Tabs comparison
        style."""
        st, look, lim = spec["style"], spec["look"], spec["lim"]
        groups = [(it[0], [it]) for it in items] if st == "tabs" and len(items) > 1 \
            else [(None, items)]
        out = []
        for lab, its in groups:
            fs = sp.skewt_hodo_figure(its, base, spec["parcel"], spec["units"],
                                      style="lines" if lab else st, look=look, limits=lim)
            fp = sp.profiles_figure(its, base, spec["zmax"], spec["units"],
                                    style="lines" if lab else st, look=look,
                                    limits=dict(z=lim.get("prof_z"), x=lim.get("prof_x")))
            a, b = _svg(fs), _svg(fp)
            try:
                probes = (sp.probe_skewt(fs, its, base, spec["parcel"], spec["units"]),
                          sp.probe_profiles(fp, its, base, spec["units"]))
            except Exception:  # noqa: BLE001  (a readout is not worth losing the figure)
                traceback.print_exc()
                probes = ({}, {})
            out.append((lab, fs, a, fp, b, probes))
        return out

    def _show_figs(self, draws):
        """Put drawn sounding figures on the page; remembers each image's figure so a
        dragged box can be turned into axes limits."""
        self._figs = {}
        if draws[0][0] is None:
            _, fs, a, fp, b, (pa, pb) = draws[0]
            self.skew_png.param.update(src=a, probe=pa)
            self.prof_png.param.update(src=b, probe=pb)
            self._figs = {self.skew_png: fs, self.prof_png: fp}
            self.skew_png.visible = self.prof_png.visible = True
            self.snd_tabs.visible = False
        else:
            active = self.snd_tabs.active
            names = [lab.replace(" km", "") for lab, *_ in draws]
            if self._snd_tab_names != names:
                self.snd_tabs[:] = [(name, pn.Column(
                    self._zoom_image("skewt_hodograph.svg", visible=True),
                    self._zoom_image("profiles.svg", visible=True),
                    sizing_mode="stretch_width")) for name in names]
                self._snd_tab_names = names
            for tab, (_, fs, a, fp, b, (pa, pb)) in zip(self.snd_tabs, draws):
                tab[0].param.update(src=a, probe=pa)
                tab[1].param.update(src=b, probe=pb)
                self._figs[tab[0]], self._figs[tab[1]] = fs, fp
            self.snd_tabs.active = min(active, len(draws) - 1)
            self.skew_png.visible = self.prof_png.visible = False
            self.snd_tabs.visible = True
        for z in self._figs:
            z.done += 1

    # ---------------------------------------------------------- restyle / zoom
    def _look(self):
        ps = self.ps
        return dict(t_color=ps["t"].value, td_color=ps["td"].value,
                    parcel_color=ps["parcel"].value, base_color=ps["base"].value,
                    lw=ps["lw"].value, parcel_lw=ps["parcel_lw"].value,
                    hodo_lw=ps["hodo_lw"].value, prof_lw=ps["prof_lw"].value,
                    shade=ps["shade"].value, barbs=ps["barbs"].value,
                    guides=ps["guides"].value, ptop=float(ps["ptop"].value),
                    tmin=ps["tmin"].value, tmax=ps["tmax"].value,
                    ring=float(ps["ring"].value) or None, hodo_top=float(ps["htop"].value))

    def _restyle(self):
        """Redraw the shown soundings with the current style and zoom (no new analysis)."""
        if self._hold_style or not self.points or not getattr(self, "_snd_last", None):
            return
        if self.snd_col.loading:  # a new analysis is on its way: let it use them
            self.request_soundings()
            return
        items, base, spec = self._snd_last
        spec = dict(spec, look=self._look(), lim=self._lim_copy())
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
                        tmax=None, ring=0, htop=12, shade=st["shade"], barbs=st["barbs"],
                        guides=st["guides"])
        self._hold_style = True
        try:
            for k, v in defaults.items():
                self.ps[k].value = v
        finally:
            self._hold_style = False
        self._restyle()

    def _lim_copy(self):
        lim = dict(self.snd_lim)
        if "prof_x" in lim:
            lim["prof_x"] = dict(lim["prof_x"])
        return lim

    def _on_zoom_box(self, z, ev):
        """A box dragged on a sounding image -> axes limits of the panel under it."""
        fig = getattr(self, "_figs", {}).get(z)
        b = ev.new
        if fig is None or not b or len(b) < 4:
            z.done += 1
            return
        W, H = fig.bbox.width, fig.bbox.height
        x0, x1 = b[0] * W, b[2] * W
        y0, y1 = (1.0 - b[3]) * H, (1.0 - b[1]) * H  # display y grows upward
        hit = self._axes_at(fig, 0.5 * (x0 + x1), 0.5 * (y0 + y1))
        if hit is None:
            z.done += 1
            return
        key, ax = hit
        bb = ax.bbox
        self._set_lims(key, ax, max(x0, bb.x0), min(x1, bb.x1),
                       max(y0, bb.y0), min(y1, bb.y1))
        self._restyle()

    def _on_zoom_pan(self, z, ev):
        """A drag in pan mode -> the panel under its start point shows the region the
        drag moved into view (the content follows the pointer)."""
        fig = getattr(self, "_figs", {}).get(z)
        p = ev.new
        if fig is None or not p or len(p) < 4:
            z.done += 1
            return
        W, H = fig.bbox.width, fig.bbox.height
        hit = self._axes_at(fig, p[0] * W, (1.0 - p[1]) * H)
        if hit is None:
            z.done += 1
            return
        key, ax = hit
        dx, dy = p[2] * W, -p[3] * H  # display y grows upward
        bb = ax.bbox
        self._set_lims(key, ax, bb.x0 - dx, bb.x1 - dx, bb.y0 - dy, bb.y1 - dy)
        self._restyle()

    @staticmethod
    def _axes_at(fig, x, y):
        return next(((k, ax) for k, ax in fig.cv_axes.items() if ax.bbox.contains(x, y)),
                    None)

    def _set_lims(self, key, ax, x0, x1, y0, y1):
        """Axes limits of panel `key` that show the display rectangle x0..x1, y0..y1."""
        inv = ax.transData.inverted()
        (a0, b0), (a1, b1) = inv.transform([(x0, y0), (x1, y1)])
        if key == "skew":  # x limits are the temperatures along the bottom edge
            t_left, p_bot = a0, b0
            t_right = inv.transform([(x1, y0)])[0][0]
            p_top = inv.transform([(x0, y1)])[0][1]
            self.snd_lim["skew"] = (float(t_left), float(t_right), float(p_bot), float(p_top))
        elif key == "hodo":
            self.snd_lim["hodo"] = (float(a0), float(a1), float(b0), float(b1))
        else:
            self.snd_lim["prof_z"] = (float(b0), float(b1))
            self.snd_lim.setdefault("prof_x", {})[int(key[4:])] = (float(a0), float(a1))

    def _on_zoom_out(self, z):
        """Widen the zoomed panels of this image by 1.6 (pressure in log p)."""
        fig = getattr(self, "_figs", {}).get(z)
        lim, f = self.snd_lim, 1.6
        if fig is None or not any(k in lim for k in self._lim_keys(fig)):
            z.done += 1
            return

        def widen(a, b):
            c, h = 0.5 * (a + b), 0.5 * (b - a) * f
            return c - h, c + h

        if "skew" in lim and "skew" in fig.cv_axes:
            t0, t1, pb, pt = lim["skew"]
            lb, lt = widen(np.log(pb), np.log(pt))
            pb, pt = min(np.exp(lb), 1100.0), max(np.exp(lt), 50.0)
            lim["skew"] = (*widen(t0, t1), pb, pt)
        if "hodo" in lim and "hodo" in fig.cv_axes:
            u0, u1, v0, v1 = lim["hodo"]
            lim["hodo"] = (*widen(u0, u1), *widen(v0, v1))
        if "prof_z" in lim and "prof0" in fig.cv_axes:
            z0, z1 = widen(*lim["prof_z"])
            lim["prof_z"] = (max(z0, 0.0), z1)
            lim["prof_x"] = {i: widen(*x) for i, x in lim.get("prof_x", {}).items()}
        self._restyle()

    def _on_zoom_reset(self, z):
        fig = getattr(self, "_figs", {}).get(z)
        keys = self._lim_keys(fig) if fig is not None else ()
        if not any(k in self.snd_lim for k in keys):
            z.done += 1
            return
        for k in keys:
            self.snd_lim.pop(k, None)
        self._restyle()

    @staticmethod
    def _lim_keys(fig):
        ks = []
        if "skew" in fig.cv_axes:
            ks += ["skew", "hodo"]
        if "prof0" in fig.cv_axes:
            ks += ["prof_z", "prof_x"]
        return ks
