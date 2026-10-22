"""Figure editor: new figures from the map, the cross-section, the series, the
soundings and the distributions, the series / sounding / distribution / annotation
lists, and the series, sounding and distribution data of a figure.

A mixin of the FigureEditor (cm1view/figui.py)."""

import json
import time as _time
import traceback
from functools import partial

import panel as pn

from . import draw as figdraw, spec as fg
from ..core import render, series as ser
from ..core.run import FileBusy, MissingAtTime
from .cards import AnnotationRow, DistCard, LEVEL_MODES, SeriesCard, SoundingCard, _dark


class FigureSources:
    # ------------------------------------------------------------ start from
    def _default(self):
        """2 x 3 grid in time from the shown time: centred on the storm when there is a
        track, else the whole domain."""
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        if not self.v.fixes:
            s["domain"] = dict(s["domain"], mode="full")
        return s

    def _own_track(self):
        """Track of this run in a new figure: the Track tab's when it has one, else a
        storm_tracks file next to the run (the Track tab when there is neither)."""
        return "viewer" if self.v.fixes else (fg.find_track(self.run.path) or "viewer")

    def _keep_runs(self, s):
        """A new spec of this run keeps the runs already added (this run selected)."""
        s["runs"][0]["track"] = self._own_track()
        if self.run_rows:
            runs = self._runs_collect()
            paths = [r["path"] for r in runs]
            if self.run.path not in paths:
                runs.insert(0, fg.run_entry(self.run, "viewer"))
                paths.insert(0, self.run.path)
            s["runs"], s["run"] = runs, paths.index(self.run.path)
        return s

    def _times(self, s, times, t):
        s.update(times=list(times), time=t,
                 times_s=[float(self.run.times[k]) for k in times],
                 time_s=float(self.run.times[t]))
        return s

    def from_map(self):
        """A one-panel figure of what the map shows (field, levels, contours, winds,
        view), at the shown time."""
        v, F, t = self.v, self.F, self.v.t
        sp = v._map_spec()
        f = sp["fill"]
        fill = fg.layer_defaults("fill", F, f["var"], f["level"])
        fill.update(mode=f["mode"] if f["mode"] in LEVEL_MODES.values() else "height",
                    cmap=f["cmap"], reverse=f["rev"])
        try:  # the range the map shows
            a = F.plane(f["var"], t, fill["mode"], f["level"], storm=sp["fstorm"])
            lo, hi = F.auto_range(f["var"], a) if f["auto"] else (f["vmin"], f["vmax"])
            fill.update(vmin=round(float(lo), 6), vmax=round(float(hi), 6))
        except Exception:  # noqa: BLE001
            pass
        layers = [fill]
        for o in sp["ov"]:
            if not o["on"]:
                continue
            lay = fg.layer_defaults("contour", F, o["var"], o["level"])
            try:
                a = F.plane(o["var"], t, o["mode"], o["level"], storm=sp["fstorm"])
                lo, hi = F.auto_range(o["var"], a)
                lv = render.parse_levels(o["levels"], lo, hi)
                lay["levels"] = ", ".join(f"{x:g}" for x in lv)
            except Exception:  # noqa: BLE001
                pass
            lay.update(mode=o["mode"], color=_dark(o["color"]), lw=0.75 * float(o["width"]),
                       neg_dashed=o["negdash"])
            layers.append(lay)
        if sp["vec"]["on"]:
            lay = fg.layer_defaults("vectors", F)
            lay.update(z=sp["vec"]["level"], frame=sp["vec"]["frame"],
                       color=_dark(sp["vec"]["color"]))
            layers.append(lay)
        s = self._keep_runs(fg.default_spec(self.run, F, t))
        self._times(s, [t], t)
        s.update(rows=1, cols=1, size=[5.0, 4.5], layers=layers, vary="time", kind="plan")
        s["domain"] = dict(s["domain"], mode="box", box=[float(x) for x in v.view])
        s["colorbar"] = dict(s["colorbar"], mode="each", orientation="vertical", shrink=0.9)
        s["axes"] = dict(s["axes"], ticklabels="all")
        self.set_spec(s)

    def from_xsec(self):
        v, F, t = self.v, self.F, self.v.t
        if len(v.xs_pts) != 2:
            self._msg("Draw a cross-section on the map first (Section tool).", True)
            return
        fill = fg.layer_defaults("fill", F, v.xs_fill.value)
        fill.update(cmap=v.xs_cmap.value, reverse=v.xs_rev.value)
        if not v.xs_auto.value:
            fill.update(vmin=float(v.xs_min.value), vmax=float(v.xs_max.value))
        layers = [fill]
        if v.xs_cont.value:
            lay = fg.layer_defaults("contour", F, v.xs_cont.value)
            lay.update(levels=v.xs_levels.value or "10, 20", color=_dark(v.xs_ccolor.value),
                       neg_dashed=v.xs_negdash.value)
            layers.append(lay)
        if v.xs_vecs.value:
            lay = fg.layer_defaults("vectors", F)
            lay.update(frame=v.xs_vframe.value, spacing=0.75, scale=400.0, width=0.0015)
            layers.append(lay)
        s = self._keep_runs(fg.default_spec(self.run, F, t))
        self._times(s, [t], t)
        s.update(kind="xsec", rows=1, cols=1, size=[7.0, 3.5], layers=layers, vary="time")
        s["xsec"] = dict(s["xsec"], mode="fixed", a=list(v.xs_pts[0]), b=list(v.xs_pts[1]),
                         ztop=float(v.xs_ztop.value))
        s["axes"] = dict(s["axes"], xlabel="distance (km)", ylabel="height (km)",
                         ticklabels="all")
        s["colorbar"] = dict(s["colorbar"], mode="each", orientation="vertical", shrink=0.9)
        self.set_spec(s)

    # ------------------------------------------------------------ series cards
    def _ser_card(self, e):
        c = SeriesCard(self, e)
        c.up.on_click(lambda ev: self._move_ser(c, -1))
        c.down.on_click(lambda ev: self._move_ser(c, 1))
        c.rm.on_click(lambda ev: self._remove_ser(c))
        return c

    def _show_series(self):
        for c in self.ser_cards:
            c.show(self.kind.value)
        self.ser_box.objects = [c.panel for c in self.ser_cards] or [pn.pane.HTML(
            '<div class="cv-empty">No series: add one from the Series tool above, or a new '
            'one.</div>')]
        ss = getattr(self.v, "series", {}) or {}
        self.ser_from.options = {"": ""} | {v["label"]: k for k, v in ss.items()}

    def _series_changed(self):
        self._show_series()
        if self.kind.value == "th":
            self._th_grid()
        self._fit_grid()
        self.request()

    def _move_ser(self, c, d):
        i = self.ser_cards.index(c)
        j = min(max(i + d, 0), len(self.ser_cards) - 1)
        self.ser_cards[i], self.ser_cards[j] = self.ser_cards[j], self.ser_cards[i]
        self._series_changed()

    def _remove_ser(self, c):
        self.ser_cards.remove(c)
        self._series_changed()

    def _tab_series(self, key):
        """A spec["series"] entry of a series of the Series tab."""
        s = self.v.series[key]
        r = dict(s["recipe"])
        e = fg.series_defaults(self.F, r, len(self.ser_cards))
        e["panel"] = 0
        return e

    def _add_series_from_tab(self):
        key = self.ser_from.value
        if not key or key not in getattr(self.v, "series", {}):
            return
        self.ser_cards.append(self._ser_card(self._tab_series(key)))
        self._series_changed()

    def _new_recipe(self):
        """A recipe for a new series: max w in 0–10 km near the storm (whole domain
        without a track), as for updraft time-height plots."""
        f = "winterp" if "winterp" in self.F else next(iter(self.F.defs))
        track = bool(self.v.fixes) or any(r.get("track") for r in self._runs_collect())
        return ser.normalize(dict(field=f, vmode="layer", z0=0.0, z1=10.0,
                                  region="track" if track else "domain", radius=5.0,
                                  offset=(0.0, 0.0), reduce="max"))

    def _add_series(self):
        e = fg.series_defaults(self.F, self._new_recipe(), len(self.ser_cards))
        if self.kind.value == "line":
            e["panel"] = len({c.collect()["panel"] for c in self.ser_cards})
        self.ser_cards.append(self._ser_card(e))
        self._series_changed()

    def _fit_grid(self, reset=False):
        """Time-series / sounding / distribution figures: enough grid cells for the
        highest panel number of the cards and no empty rows (reset: a column of up to
        3, else 2 columns)."""
        kind = self.kind.value
        if kind not in ("line", "sounding", "dist"):
            return
        cards = {"line": self.ser_cards, "sounding": self.snd_cards,
                 "dist": self.dist_cards}[kind]
        n = 1 + max([max(0, int(c.w["panel"].value or 1) - 1) for c in cards] or [0])
        r, c = int(self.rows.value or 1), int(self.cols.value or 1)
        if reset:
            r, c = (n, 1) if n <= 3 else ((n + 1) // 2, 2)
        else:
            c = min(c, n)
            r = -(-n // c)
        if (r, c) != (self.rows.value, self.cols.value):
            hold, self._hold = self._hold, True
            try:
                self.rows.value, self.cols.value = r, c
            finally:
                self._hold = hold
            self._fit_size()
            self._build_titles()

    def _fit_size(self):
        """A size for the grid (plan views and sections: the height for the width)."""
        kind, r, c = self.kind.value, int(self.rows.value or 1), int(self.cols.value or 1)
        if not self._auto_size:
            return
        if kind in ("plan", "xsec"):
            self._follow_size()
            return
        if kind == "th":
            w, h = 4.5 * c + 1.0, 2.8 * r + 0.6
        elif kind == "sounding":
            lay = self.sk["layout"].value
            w = {"side": 8.2, "hodo": 4.5}.get(lay, 5.0) * c + 0.5
            h = (4.5 if lay == "hodo" else 5.0) * r
            if self.sk["table"].value:  # (a row per sounding of the fullest panel)
                per = max([sum(int(c.w["panel"].value or 1) == p + 1 for c in self.snd_cards)
                           for p in range(r * c)] or [1])
                h += r * (0.45 + 0.25 * per)
        elif kind == "dist":
            w, h = (5.5 if c == 1 else 4.2 * c), 3.6 * r + 0.3
        else:
            w, h = (7.0 if c == 1 else 6.0 * c), 3.0 * r + 0.5
        hold, self._hold = self._hold, True
        try:
            self.width.value, self.height.value = round(min(16.0, w), 2), round(min(16.0, h), 2)
            self.size_preset.value = ""
        finally:
            self._hold = hold

    def _size_by_hand(self):
        if not self._hold:
            self._auto_size = False
            hold, self._hold = self._hold, True
            try:
                self.size_preset.value = ""
            finally:
                self._hold = hold

    def _th_grid(self):
        """Time-height grid: a row (column) per series and a column (row) per run."""
        ne, nr = max(1, len(self.ser_cards)), max(1, len(self.run_rows))
        r, c = (ne, nr) if self.runs_as.value == "cols" else (nr, ne)
        if (self.rows.value, self.cols.value) != (r, c):
            hold, self._hold = self._hold, True
            try:
                self.rows.value, self.cols.value = r, c
            finally:
                self._hold = hold
            self._fit_size()
            self._build_titles()

    # ------------------------------------------------------------ sounding cards
    def _snd_card(self, e):
        c = SoundingCard(self, e)
        c.rm.on_click(lambda ev: self._remove_snd(c))
        return c

    def _show_soundings(self):
        self.snd_box.objects = [c.panel for c in self.snd_cards] or [pn.pane.HTML(
            '<div class="cv-empty">No soundings: add the map\'s, or a new one.'
            '</div>')]

    def _remove_snd(self, c):
        self.snd_cards.remove(c)
        self._show_soundings()
        self.request()

    def _own_index(self):
        paths = [r["path"] for r in self.run_rows]
        return paths.index(self.run.path) if self.run.path in paths else 0

    def tab_soundings(self):
        """spec["soundings"] entries of the Sounding tab's soundings (this run)."""
        out = []
        for n, (kind, where, tp) in enumerate(self.v.points):
            t = self.v.t if tp is None else tp
            if kind == "mean":
                wh = dict(kind="mean", x=0.0, y=0.0, avg=0.0)
            else:
                avg = (0.5 * (where[2] + where[3]) if len(where) == 4
                       else float(self.v.avg.value or 0.0) if hasattr(self.v, "avg") else 0.0)
                wh = dict(kind=kind, x=float(where[0]), y=float(where[1]), avg=float(avg))
            out.append(fg.sounding_defaults(self._own_index(), float(self.run.times[t]), wh,
                                            n + len(self.snd_cards)))
        return out

    def _add_tab_soundings(self):
        new = self.tab_soundings()
        if not new:
            self._msg("No soundings yet: click the map with the Sounding tool first, or "
                      "add one here.", True)
            return
        self.snd_cards += [self._snd_card(e) for e in new]
        self._show_soundings()
        self.request()

    def _add_sounding(self):
        e = fg.sounding_defaults(self._own_index(), float(self.run.times[self.v.t]),
                                 dict(kind="trk", x=0.0, y=0.0, avg=0.0), len(self.snd_cards))
        e["panel"] = len(self.snd_cards)
        self.snd_cards.append(self._snd_card(e))
        self._show_soundings()
        self._fit_grid()
        self.request()

    # ------------------------------------------------------------ distribution cards
    def _dist_card(self, e):
        c = DistCard(self, e)
        c.rm.on_click(lambda ev: self._remove_dist(c))
        return c

    def _show_dists(self):
        self.dist_box.objects = [c.panel for c in self.dist_cards] or [pn.pane.HTML(
            '<div class="cv-empty">No distributions: add the map\'s (Distribution tool), '
            'or a new one.</div>')]

    def _remove_dist(self, c):
        self.dist_cards.remove(c)
        self._show_dists()
        self._fit_grid()
        self.request()

    def tab_dists(self):
        """spec["dists"] entries of the Distribution tool's distributions (this run),
        all in the first panel."""
        out = []
        for n, s in enumerate((getattr(self.v, "dists", {}) or {}).values()):
            out.append(fg.dist_defaults(s["recipe"], self._own_index(),
                                        float(self.run.times[s["t"]]),
                                        n + len(self.dist_cards)))
        return out

    def _add_tab_dists(self):
        new = self.tab_dists()
        if not new:
            self._msg("No distributions yet: compute one with the Distribution tool on "
                      "the map first, or add one here.", True)
            return
        self.dist_cards += [self._dist_card(e) for e in new]
        self._show_dists()
        self.request()

    def _new_dist_recipe(self):
        """A recipe for a new distribution: w over the whole domain at 1 km."""
        f = "winterp" if "winterp" in self.F else next(iter(self.F.defs))
        return dict(field=f, vmode="height", z=1.0, region="domain")

    def _add_dist(self):
        e = fg.dist_defaults(self._new_dist_recipe(), self._own_index(),
                             float(self.run.times[self.v.t]), len(self.dist_cards))
        e["panel"] = 0
        self.dist_cards.append(self._dist_card(e))
        self._show_dists()
        self._fit_grid()
        self.request()

    # ------------------------------------------------------------ annotations
    def _ann_row(self, a):
        r = AnnotationRow(self, a)
        r.rm.on_click(lambda ev: self._remove_ann(r))
        return r

    def _show_anns(self):
        self.ann_box.objects = [r.panel for r in self.ann_rows]

    def _add_annotation(self):
        kind = self.ann_kind.value
        # in the middle of the first drawn panel, so it shows (storm-centred panels in
        # grid km may not contain (0, 0)); no axis ranges yet: as panel fractions
        lims = self._lims.get(min(self._lims)) if self._lims else None
        if lims is None or self.kind.value == "sounding":
            coords, (x, y), dx, dy = "axes", (0.5, 0.5), 0.15, 0.15
        else:
            (x0, x1), (y0, y1) = lims
            coords, x, y = "data", 0.5 * (x0 + x1), 0.5 * (y0 + y1)
            dx, dy = 0.15 * (x1 - x0), 0.15 * (y1 - y0)
        r = min(abs(dx), abs(dy)) if coords == "data" else 0.15
        a = dict(kind=kind, panel=-1, coords=coords, x=round(x, 2), y=round(y, 2),
                 x2=round(x + dx, 2), y2=round(y + dy, 2), r=round(r, 2),
                 text="A" if kind == "text" else "",
                 color="#000000", size=10.0 if kind != "marker" else 8.0, lw=1.5,
                 ls="--" if kind in ("vline", "hline") else "-")
        self.ann_rows.append(self._ann_row(a))
        self._show_anns()
        self.request()

    def _remove_ann(self, r):
        self.ann_rows.remove(r)
        self._show_anns()
        self.request()

    # ------------------------------------------------------------ series data
    def _series_get(self, spec, k, e):
        """(run, dataset) of series e of spec for run k, or why not (a string).  Starts
        computing the missing times in the background (the preview updates as they come
        in)."""
        runs, ent = spec["runs"], spec["series"][e]
        try:
            run, F = self.open_run(runs[k]["path"])
        except Exception as ex:  # noqa: BLE001
            return f"could not open {runs[k]['path']}: {ex}"
        r = ent["recipe"]
        if r["field"] not in F:
            return f"this run has no {r['field']}"
        fx = self.run_fixes(runs[k], run)
        track = r["region"] == "track"
        if track and not fx:
            return "no storm track for this run (Runs tab)"
        centers = ser.track_centers(fx, len(run.times)) if track else None
        sig = json.dumps(sorted((t, round(f["x"], 4), round(f["y"], 4))
                                for t, f in fx.items())) if track else ""
        key = (run.path, json.dumps(r, sort_keys=True), sig)
        ds = self._ser_mem.get(key)
        if ds is None:
            d = F[r["field"]]
            ds = ser.cached(run, r, d.label, d.units, centers)
            self._ser_mem[key] = ds
        if key not in self._ser_state and int(ds["computed"].sum()) < len(run.times):
            self._ser_state[key] = "running"
            storm = ({t: fg.storm_motion(run, fx, t) for t in range(len(run.times))}
                     if F[r["field"]].storm else None)
            self.v.pools["figser"].submit(self._ser_compute, key, run, F, r, ds, centers, storm,
                                          f"{runs[k].get('label') or ''}: {ent.get('label', '')}")
        elif key not in self._ser_state:
            self._ser_state[key] = "done"
        return run, ds

    def _ser_compute(self, key, run, F, recipe, ds, centers, storm, what):
        g0, last = self.v.gen["figser"], [_time.time()]

        def on_result(ds_, done, total):
            self._ser_prog[key] = f"{what[:60]} {done}/{total}"
            if _time.time() - last[0] > 10 and done < total:  # partial preview
                last[0] = _time.time()
                self.v._schedule(partial(self.request, False, False))

        try:
            ser.compute(run, F, recipe, ds, centers, storm, on_result=on_result,
                        cancelled=lambda: self.v.gen["figser"] != g0)
            self._ser_state[key] = "done"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._ser_state[key] = f"error: {e}"
        self._ser_prog.pop(key, None)
        self.v._schedule(partial(self.request, False, False))

    def series_pending(self):
        return [v for k, v in self._ser_prog.items() if self._ser_state.get(k) == "running"] \
            or [""] * sum(v == "running" for v in self._ser_state.values())

    def _series_data(self, spec):
        got = {}

        def get(k, e):
            if (k, e) not in got:
                got[(k, e)] = self._series_get(spec, k, e)
            return None if isinstance(got[(k, e)], str) else got[(k, e)]

        data, multi = {}, len(spec["runs"]) > 1
        busy = bool(self.series_pending())
        for i in range(fg.npanels(spec)):
            if spec["kind"] == "th":
                ref = figdraw.series_ref(spec, i)
                if ref is None:
                    continue
                r = get(*ref)
                d = (dict(missing=got[ref]) if r is None else
                     fg.th_panel(r[0], r[1], spec["series"][ref[1]], spec))
                d["run"] = ref[0]
                if multi:
                    d["run_label"] = spec["runs"][ref[0]].get("label", "")
            else:
                d = fg.line_panel(spec, i, get)
            if busy and d.get("missing") == "not computed yet":
                d["missing"] = "computing…"
            data[i] = d
        return fg.share_time_range(spec, data)

    def _sounding_data(self, spec, progress=None, cancelled=None):
        runs, ents = spec["runs"], spec.get("soundings", [])
        res, labels = {}, {}
        multi = len(runs) > 1
        storm = fg.storm_choice(spec.get("skewt", {}))  # (of the SRH and the ring)

        def get(e):
            if e in res:
                return res[e]
            ent = ents[e]
            k = int(ent.get("run", 0))
            if k >= len(runs):
                res[e] = "no such run"
                return res[e]
            try:
                run, _ = self.open_run(runs[k]["path"])
                fx = self.run_fixes(runs[k], run)
                sig = json.dumps(sorted((t, round(f["x"], 4), round(f["y"], 4))
                                        for t, f in fx.items())) \
                    if ent["where"].get("kind") == "trk" else ""
                key = json.dumps([run.path, float(ent["time_s"]), ent["where"], sig, storm],
                                 sort_keys=True)
                r = self.snd_cache.get(key)
                if r is None:
                    if progress:
                        progress(e, len(ents))
                    r = fg.sounding_column(run, ent, fx, storm=storm)
                    self.snd_cache[key] = r
                    while len(self.snd_cache) > 40:
                        self.snd_cache.popitem(last=False)
                labels[e] = fg.sounding_label(ent, runs[k].get("label", ""), run, multi)
            except (MissingAtTime, FileBusy) as ex:
                r = str(ex)
            except Exception as ex:  # noqa: BLE001
                traceback.print_exc()
                r = f"{type(ex).__name__}: {ex}"
            res[e] = r
            return r

        data = {}
        for i in range(fg.npanels(spec)):
            if cancelled and cancelled():
                return None
            data[i] = fg.sounding_panel(spec, i, get, lambda e: labels.get(e, ""))
        return data

    def _dist_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of a distribution figure; the summaries are kept
        (dist_cache), so restyling reads nothing."""
        runs, ents = spec["runs"], spec.get("dists", [])
        res, labels, vlabs = {}, {}, {}
        multi = len(runs) > 1

        def get(e):
            if e in res:
                return res[e]
            ent = ents[e]
            k = int(ent.get("run", 0))
            if k >= len(runs):
                res[e] = "no such run"
                return res[e]
            try:
                run, F = self.open_run(runs[k]["path"])
                fx = self.run_fixes(runs[k], run)
                track = ent["recipe"]["region"] == "track" or \
                    (ent["recipe"]["field"] in F and F[ent["recipe"]["field"]].storm)
                sig = json.dumps(sorted((t, round(f["x"], 4), round(f["y"], 4))
                                        for t, f in fx.items())) if track else ""
                key = json.dumps([run.path, float(ent["time_s"]), ent["recipe"], sig],
                                 sort_keys=True)
                r = self.dist_cache.get(key)
                if r is None:
                    if progress:
                        progress(e, len(ents))
                    r = fg.dist_compute(run, F, ent, fx)
                    self.dist_cache[key] = r
                    while len(self.dist_cache) > 60:
                        self.dist_cache.popitem(last=False)
                mine = [x for x in ents if int(x.get("panel", 0)) == int(ent.get("panel", 0))]
                times = len({round(float(x["time_s"]), 1) for x in mine}) > 1
                labels[e] = fg.dist_label(ent, runs[k].get("label", ""), F, multi, times)
                vlabs[e] = fg.dist_value_label(F, ent["recipe"]["field"])
            except (MissingAtTime, FileBusy) as ex:
                r = str(ex)
            except Exception as ex:  # noqa: BLE001
                traceback.print_exc()
                r = f"{type(ex).__name__}: {ex}"
            res[e] = r
            return r

        data = {}
        for i in range(fg.npanels(spec)):
            if cancelled and cancelled():
                return None
            data[i] = fg.dist_panel(spec, i, get, lambda e: labels.get(e, ""),
                                    lambda e: vlabs.get(e, ""))
        return data

    # ------------------------------------------------------------ start from series / soundings
    def from_series(self):
        """Time-height panels of the Series tab's layer series (the active one first),
        or time series when the active one is at one height; every run of the figure.
        Without series: the maximum updraft near the storm (edit it in Layers)."""
        ss = getattr(self.v, "series", {}) or {}
        if ss:
            act = self.v.ser_pick.value if self.v.ser_pick.value in ss else next(iter(ss))
            keys = [act] + [k for k in ss if k != act]
            th = "profile" in ss[act]["ds"]
            keys = [k for k in keys if ("profile" in ss[k]["ds"]) == th][:4 if th else 6]
            ents = [fg.series_defaults(self.F, dict(ss[k]["recipe"]), n)
                    for n, k in enumerate(keys)]
        else:
            th, ents = True, [fg.series_defaults(self.F, self._new_recipe())]
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        nr = len(s["runs"])
        s.update(kind="th" if th else "line", series=ents, runs_as="cols", vary="time",
                 layers=[lay for lay in s["layers"] if lay["type"] != "vectors"])
        s["axes"] = dict(s["axes"], xlabel="time (min)", ylabel="height (km)" if th else "",
                         ticklabels="outer", equal=False)
        s["time_label"] = dict(s["time_label"], on=False)
        s["letters"] = dict(s["letters"], loc="upper left")
        if th:
            s.update(rows=len(ents), cols=nr, size=[5.0 * nr + 1.0, 3.0 * len(ents) + 0.5])
            s["colorbar"] = dict(s["colorbar"], mode="row", orientation="vertical", shrink=1.0)
            s["titles"] = [f"{s['runs'][c]['label']} – {e['label']}" for e in ents
                           for c in range(nr)]
            s["run_label"] = dict(s["run_label"], on=False)
        else:
            s.update(rows=1, cols=1, size=[7.0, 3.5])
            s["colorbar"] = dict(s["colorbar"], mode="none")
        self.set_spec(s)

    def from_soundings(self):
        """Skew-T panels: the Sounding tab's soundings in one panel (or the storm's
        sounding at the shown time when there are none)."""
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        own = s["runs"][s["run"]]
        track = bool(self.run_fixes(own, self.run))
        snd = self.tab_soundings() or [fg.sounding_defaults(
            s["run"], float(self.run.times[self.v.t]),
            dict(kind="trk" if track else "mean", x=0.0, y=0.0, avg=0.0))]
        s.update(kind="sounding", soundings=snd, rows=1, cols=1, size=[5.5, 5.5],
                 vary="time")
        s["axes"] = dict(s["axes"], xlabel="temperature (°C)", ylabel="pressure (hPa)",
                         ticklabels="all", equal=False)
        s["colorbar"] = dict(s["colorbar"], mode="none")
        # one sounding figure: no letters; a part of a figure: letters above, clear of
        # the time and the legend
        s["letters"] = dict(s["letters"], on=self._multi_part(), loc="above left")
        s["time_label"] = dict(s["time_label"], loc="lower left")
        self.set_spec(s)

    def from_dists(self):
        """One distribution panel of the Distribution tool's distributions (or w over
        the whole domain at 1 km at the shown time when there are none), drawn as the
        tool draws them."""
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        ents = self.tab_dists() or [fg.dist_defaults(
            self._new_dist_recipe(), s["run"], float(self.run.times[self.v.t]))]
        look = getattr(self.v, "dist_look", None)
        s.update(kind="dist", dists=ents, rows=1, cols=1, size=[5.5, 3.9], vary="time")
        if look:
            s["dist"] = dict(s["dist"], **look())
        s["axes"] = dict(s["axes"], xlabel="", ylabel="", ticklabels="all", equal=False)
        s["colorbar"] = dict(s["colorbar"], mode="none")
        s["letters"] = dict(s["letters"], on=self._multi_part(), loc="above left")
        s["time_label"] = dict(s["time_label"], loc="upper left")
        s["run_label"] = dict(s["run_label"], on=False)
        self.set_spec(s)
