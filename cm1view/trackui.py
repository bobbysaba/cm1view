"""Storm tracking: the Track panel, automatic and hand-placed fixes, the storm chip,
and saving / loading tracks.

A mixin of the Viewer (cm1view/app.py): its methods use the Viewer's widgets and state."""

import io
import os
import traceback
from functools import partial

import numpy as np
import panel as pn
from bokeh.models import ColumnDataSource, HoverTool
from bokeh.plotting import figure

from . import config, track as trk
from .theme import ACCENT
from .ui import _bokeh, _html, pd_empty, style_fig


class TrackPanel:
    _track_found = ()

    def _build_track(self):
        run = self.run
        metrics = trk.metrics(run)
        self.trk_metric = pn.widgets.Select(name="Track on", options=metrics,
                                            value=next(iter(metrics.values())), width=200)
        self.trk_z = pn.widgets.FloatInput(name="Height (km)", value=1.0, step=0.25,
                                           start=0.0, end=float(run.z[-1]), width=90,
                                           visible=self.trk_metric.value != "uh")
        groups = self.F.groups()
        self.trk_field = pn.widgets.Select(
            name="Field", groups=groups, width=200, visible=False,
            value="winterp" if "winterp" in self.F else
            next(iter(next(iter(groups.values())).values())))
        self.trk_sense = pn.widgets.Select(
            name="Track the", options={"Maximum": "max", "Minimum": "min"}, value="max",
            width=110, visible=False)
        self.trk_fix = pn.widgets.Select(
            name="Fix at", options={"Peak": "peak", "Centroid": "centroid"}, value="peak",
            width=110,
            description="Peak: the strongest point.  Centroid: the field-weighted centre "
                        "of the area around it beyond the cutoff (a smoother track)")
        self.trk_cut = pn.widgets.FloatInput(
            name="Centroid cutoff (%)", value=50.0, step=5.0, start=1.0, end=99.0,
            width=130, visible=False,
            description="The centroid area: where the smoothed field is beyond this "
                        "percentage of the way from the background (0) to the peak")
        self.trk_radius = pn.widgets.FloatInput(
            name="Search radius (km)", value=5.0, step=0.5, start=0.5, width=120,
            description="How far from the expected position to look at the next time")
        self.trk_smooth = pn.widgets.FloatInput(
            name="Smoothing (km)", value=1.0, step=0.125, start=0.0, width=110,
            description="Smooth the field before picking the maximum, so the fix follows "
                        "the storm rather than single-grid-point noise (Gaussian: σ; "
                        "box: width)")
        self.trk_kernel = pn.widgets.Select(
            name="Smoothing filter", options={"Gaussian": "gauss", "Box": "box"},
            value="gauss", width=110)
        self.trk_whole = pn.widgets.Checkbox(  # storm_tracking.ipynb: no search radius
            name="Search whole domain each time", value=False, margin=(5, 10, 14, 10))
        self.trk_stop = pn.widgets.FloatInput(
            name="Stop below", value=trk.METRIC_STOP[self.trk_metric.value], width=100,
            description="Tracking ends when the extreme in the search disc is no longer "
                        "beyond this (meso lost); empty: never")
        times = {run.time_label(t): t for t in range(len(run.times))}
        self.trk_from = pn.widgets.Select(
            name="From", options={"Clicked time": "click", **times}, value="click",
            width=120, description="First time to track (earlier than the clicked time "
                                   "tracks backward too)")
        self.trk_to = pn.widgets.Select(
            name="To", options={"End of run": "end", "Clicked time": "click", **times},
            value="end", width=120, description="Last time to track")
        self.trk_snap = pn.widgets.Checkbox(  # move the click to the max within the radius
            name="Snap click to max", value=True, margin=(5, 10, 14, 10))
        self.trk_near = pn.widgets.Checkbox(  # distance-weight the max (no core hopping)
            name="Prefer nearest core", value=True, margin=(5, 10, 14, 10))
        self.trk_how = pn.widgets.RadioButtonGroup(
            options={"Auto-track": "auto", "Place by hand": "manual"}, value="auto",
            button_type="primary", button_style="outline", width=240, margin=(5, 10, 8, 10),
            description="Auto-track follows the meso from a click; Place by hand sets the "
                        "fix at the shown time to exactly where you click")
        self.trk_advance = pn.widgets.Checkbox(  # click, step, click, ... through time
            name="Step time after each click", value=True, margin=(5, 10, 14, 10),
            visible=False)
        self.trk_del = pn.widgets.Button(name="Delete fix at this time", button_type="light",
                                         button_style="outline", height=32,
                                         margin=(5, 4, 8, 4), disabled=True)
        self.trk_load = pn.widgets.Button(
            name="Load", button_type="primary", button_style="outline", height=32,
            margin=(5, 4, 8, 4),
            description="Read a track from the path (CSV or whitespace columns with "
                        "x_km, y_km or loc_x, loc_y and time_s / time_hms / time_index / "
                        "time in minutes)")
        self.trk_find = pn.widgets.Button(
            name="Find strongest", button_type="primary", button_style="outline", height=32,
            margin=(5, 4, 8, 4),
            description="Start the track from the domain-wide extreme of the "
                        "(smoothed) field at the shown time, then follow it through the "
                        "From–To window")
        self.trk_stop_btn = pn.widgets.Button(name="Stop", button_type="danger",
                                              button_style="outline", height=32,
                                              margin=(5, 4, 8, 10), disabled=True)
        self.trk_clear = pn.widgets.Button(name="Clear track", button_type="light",
                                           button_style="outline", height=32,
                                           margin=(5, 4, 8, 4))
        self.trk_path = pn.widgets.TextInput(
            name="Save to (on the server; .csv = comma separated, .txt = aligned columns)",
            value=self._trk_default(), sizing_mode="stretch_width", min_width=300)
        self.trk_save = pn.widgets.Button(name="Save", button_type="primary", height=32,
                                          margin=(5, 4, 8, 10), disabled=True)
        self.trk_dl = pn.widgets.FileDownload(
            callback=self._track_download, filename="meso_track.csv", label="Download",
            button_type="primary", button_style="outline", height=32, margin=(5, 4, 8, 4),
            disabled=True)
        self.trk_status = _html(sizing_mode="stretch_width")

        fig = figure(sizing_mode="stretch_width", height=210, tools="save,hover",
                     x_axis_label="time (min)", y_axis_label="")
        style_fig(fig)
        fig.toolbar.autohide = True
        self.trk_ts_src = ColumnDataSource(dict(tmin=[], value=[], hms=[]))
        fig.line("tmin", "value", source=self.trk_ts_src, line_color=ACCENT, line_width=2)
        fig.scatter("tmin", "value", source=self.trk_ts_src, size=5, color=ACCENT)
        self.trk_ts_now = ColumnDataSource(dict(tmin=[], value=[]))
        fig.scatter("tmin", "value", source=self.trk_ts_now, size=11, fill_alpha=0,
                    line_color="#fbbf24", line_width=2.5)
        fig.select_one(HoverTool).tooltips = [("t", "@hms"), ("value", "@value{0.000}")]
        self.trk_fig = fig
        # shown once there are tracked values (a loaded track may have none: an all-NaN
        # plot is an empty box)
        self.trk_pane = _bokeh(fig, sizing_mode="stretch_width", visible=False)
        self.trk_table = pn.widgets.Tabulator(
            pd_empty(), disabled=True, show_index=False, theme="midnight", height=260,
            sizing_mode="stretch_width", layout="fit_data_fill", visible=False)

    # ================================================================ meso track
    def _trk_opts(self):
        stop = self.trk_stop.value
        o = dict(metric=self.trk_metric.value, zkm=float(self.trk_z.value or 0.0),
                 radius=float(self.trk_radius.value or 5.0),
                 smooth=float(self.trk_smooth.value or 0.0), kernel=self.trk_kernel.value,
                 stop=None if stop is None else float(stop), snap=self.trk_snap.value,
                 nearest=self.trk_near.value, whole=self.trk_whole.value,
                 fix=self.trk_fix.value, cutoff=float(self.trk_cut.value or 50.0))
        if o["metric"] == "field":
            o.update(field=self.trk_field.value, sense=self.trk_sense.value)
        return o

    def _trk_window(self, t0):
        """(first, last) output index to track for a click at t0."""
        f, t = self.trk_from.value, self.trk_to.value
        return (t0 if f == "click" else int(f),
                len(self.run.times) - 1 if t == "end" else t0 if t == "click" else int(t))

    def _trk_stop_label(self):
        mn = trk.sense(dict(metric=self.trk_metric.value, sense=self.trk_sense.value))
        self.trk_stop.name = "Stop above" if mn == "min" else "Stop below"

    def _trk_preset(self, metric):
        """Default settings per tracked field.  Updraft: w at 1 km with a Gaussian of
        sigma = 3 grid points, as in storm_tracking.ipynb."""
        dxk = self.run.dx / 1000.0
        z, smooth, kernel = {"w": (1.0, 3 * dxk, "gauss"), "zeta": (1.0, 1.0, "box"),
                             "uh": (self.trk_z.value, 1.0, "box"),
                             "pmin": (1.0, 1.0, "box"),
                             "field": (self.trk_z.value, 1.0, "box")}[metric]
        self.trk_z.param.update(value=z, visible=metric != "uh")
        self.trk_field.visible = self.trk_sense.visible = metric == "field"
        self.trk_smooth.value, self.trk_kernel.value = round(smooth, 3), kernel
        self.trk_stop.value = trk.METRIC_STOP[metric]
        self._trk_stop_label()

    def _on_trk_metric(self, ev):
        self._trk_preset(ev.new)

    def _on_trk_fix(self, ev):
        self.trk_cut.visible = ev.new == "centroid"

    def _on_trk_whole(self, ev):
        self.trk_radius.disabled = self.trk_near.disabled = ev.new

    def request_track(self, x, y):
        """Track from a click at the shown time.  A click near the existing track
        (same settings) corrects it from that time on, keeping the other side;
        anywhere else starts a new track."""
        opts, t0, run = self._trk_opts(), self.t, self.run
        if self.trk_how.value == "manual" and x is not None:
            self._place_fix(x, y, opts)
            return
        lo, hi = self._trk_window(t0)
        if not lo <= t0 <= hi:
            self.trk_status.object = (
                f'<div class="cv-status" style="color:#f87171">The shown time '
                f'{run.time_label(t0)} is outside the From–To window; change the time '
                f'or the window</div>')
            return
        opts.update(t_from=lo, t_to=hi)
        direction, existing = "both", None
        same = self.trk_spec is not None and all(
            self.trk_spec.get(k) == opts.get(k)
            for k in ("metric", "zkm", "field", "sense", "smooth", "kernel", "nearest",
                      "whole", "fix", "cutoff"))
        if x is None:  # Find strongest: a new track from the domain-wide maximum
            direction = "both"
        elif self.fixes and same:
            ts = sorted(self.fixes)
            near = min(ts, key=lambda tt: abs(tt - t0))
            fx = self.fixes[near]
            if np.hypot(fx["x"] - x, fx["y"] - y) <= 3 * opts["radius"]:
                direction = "forward" if t0 > ts[0] else "backward"
                existing = self.fixes
        self.gen["trk"] += 1
        g = self.gen["trk"]
        self.trk_stop_btn.disabled = False
        what = "Correcting" if existing else "Tracking"
        self.trk_status.object = (f'<div class="cv-status"><span class="busy">● {what} from '
                                  f'{run.time_label(t0)}…</span></div>')
        self.pools["trk"].submit(self._trk_job, g, t0, x, y, opts, direction, existing)

    def _on_trk_how(self, ev):
        manual = ev.new == "manual"
        self.trk_advance.visible = manual
        self.trk_from.visible = self.trk_to.visible = self.trk_stop.visible = not manual
        if manual:
            self.trk_snap.value = False

    def _place_fix(self, x, y, opts):
        """Hand-placed fix at the shown time: drawn at once, its value (and snapped
        position, with Snap on) filled in from the data in the background."""
        t = self.t
        if not self.trk_stop_btn.disabled:  # a hand fix ends any running auto-track
            self._cancel_track()
        g = self.gen["trk"]
        self.fixes = {**self.fixes, t: dict(x=x, y=y, value=float("nan"), source="manual")}
        self.trk_spec = opts
        self._update_track_view()
        self.trk_status.object = self._track_summary(f" · placed {self.run.time_label(t)}")
        self.pools["trk"].submit(self._place_job, g, t, x, y, opts)
        if self.trk_advance.value and self.t < self.tslider.end:
            self.tslider.value = self.t + 1
            self._refresh_panels()

    def _place_job(self, g, t, x, y, opts):
        try:
            fx = trk.place(self.run, t, x, y, opts, fields=self.F)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return
        if fx is not None:
            self._schedule(partial(self._apply_place, g, t, x, y, fx))

    def _apply_place(self, g, t, x, y, fx):
        cur = self.fixes.get(t)
        # still the same click (not cleared, deleted or re-placed meanwhile)
        if g != self.gen["trk"] or cur is None or (cur["x"], cur["y"]) != (x, y):
            return
        self.fixes = {**self.fixes, t: fx}
        self._update_track_view()
        if self.points and (self.storm.value == "track"
                            or any(k == "trk" for k, _, _ in self.points)):
            self.request_soundings()

    def _on_delete_fix(self, ev):
        if self.t in self.fixes:
            self.fixes = {t: f for t, f in self.fixes.items() if t != self.t}
            self._update_track_view()
            self.trk_status.object = self._track_summary(
                f" · deleted {self.run.time_label(self.t)}")
            self._draw_points()

    def _on_load_track(self, ev):
        try:
            fixes = trk.load(self.run, self.trk_path.value)
        except (OSError, ValueError, KeyError) as e:
            self.trk_status.object = (f'<div class="cv-status" style="color:#f87171">Could '
                                      f'not load: {e}</div>')
            return
        self.gen["trk"] += 1
        self.trk_stop_btn.disabled = True
        self.fixes, self.trk_spec = fixes, self._trk_opts()
        self._update_track_view()
        self.trk_status.object = self._track_summary(f" · loaded from <code>"
                                                     f"{self.trk_path.value}</code>")
        self._draw_points()

    def _trk_job(self, g, t0, x, y, opts, direction, existing):
        run = self.run

        def cancelled():
            return g != self.gen["trk"]

        def on_fix(fixes):
            if not cancelled():
                self._schedule(partial(self._apply_track, fixes, opts, g, False))

        def progress(done, total, t):
            msg = (f'<div class="cv-status"><span class="busy">● Tracking… '
                   f'{run.time_label(t)} ({done + 1}/{total} times, a few seconds each)'
                   f'</span></div>')
            if not cancelled():
                self._schedule(partial(setattr, self.trk_status, "object", msg))

        try:
            fixes = trk.track(run, t0, x, y, opts, direction, existing=existing,
                              on_fix=on_fix, cancelled=cancelled, progress=progress,
                              fields=self.F)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            msg = f'<div class="cv-status" style="color:#f87171">Tracking error: {e}</div>'
            self._schedule(partial(setattr, self.trk_status, "object", msg))
            self._schedule(partial(setattr, self.trk_stop_btn, "disabled", True))
            return
        if not cancelled():
            self._schedule(partial(self._apply_track, fixes, opts, g, True))

    def _apply_track(self, fixes, opts, g, final):
        if g != self.gen["trk"]:
            return
        self.fixes, self.trk_spec = fixes, opts
        self._update_track_view()
        if final:
            self.trk_stop_btn.disabled = True
            self.trk_status.object = self._track_summary()
            if self._storm_fields_shown():
                self.request_map()
            if self.points and (self.storm.value == "track"
                                or any(k == "trk" for k, _, _ in self.points)):
                self.request_soundings()

    def _track_summary(self, note=""):
        run, ts = self.run, sorted(self.fixes)
        if not ts:
            return ('<div class="cv-empty">With the <b>Track</b> tool on, click on the '
                    'storm, or press <b>Find strongest</b> to start from the '
                    'domain-wide maximum. It is followed through time from there; the path '
                    'is drawn on the map.</div>')
        mv = ""
        if len(ts) > 1:  # mean ground-relative motion, first to last fix
            f0, f1, dt = self.fixes[ts[0]], self.fixes[ts[-1]], run.times[ts[-1]] - run.times[ts[0]]
            u = (f1["x"] - f0["x"]) * 1000.0 / dt + run.umove
            v = (f1["y"] - f0["y"]) * 1000.0 / dt + run.vmove
            spd, dirn = np.hypot(u, v), np.degrees(np.arctan2(-u, -v)) % 360
            mv = f' · mean motion {spd:.1f} m/s from {dirn:.0f}° (u {u:.1f}, v {v:.1f})'
        elif self.fixes[ts[0]].get("source") == "auto":
            mv = (' · tracking stopped after one time: the signal was not past '
                  f'<i>{self.trk_stop.name}</i> at the next time, or the From–To '
                  'window ends there')
        return (f'<div class="cv-status">{len(ts)} fixes, {run.time_label(ts[0])} → '
                f'{run.time_label(ts[-1])}{mv}{note}</div>')

    def _update_track_view(self):
        run, fx = self.run, self.fixes
        ts = sorted(fx)
        xs, ys = [fx[t]["x"] for t in ts], [fx[t]["y"] for t in ts]
        vals, hms = [fx[t]["value"] for t in ts], [run.time_label(t) for t in ts]
        self.trk_line_src.data = dict(x=xs, y=ys)
        self.trk_pts_src.data = dict(x=xs, y=ys, hms=hms, value=vals)
        self.trk_ts_src.data = dict(tmin=[run.times[t] / 60.0 for t in ts], value=vals,
                                    hms=hms)
        lab, units = trk.label(self.trk_spec or self._trk_opts(), self.F)
        self.trk_fig.yaxis.axis_label = f"{lab} ({units})" if units else lab
        if ts:
            import pandas as pd
            df = pd.DataFrame(trk.rows(run, fx)).drop(columns=["file", "time_s"])
            self.trk_table.value = df.round(4)
        self.trk_table.visible = bool(ts)
        self.trk_pane.visible = bool(np.isfinite(np.asarray(vals, float)).any())
        self.trk_save.disabled = self.trk_dl.disabled = not ts
        self.storm_follow.disabled = not ts
        if not ts:
            self.trk_status.object = self._track_summary()
        self._update_track_now()
        # storm-relative fields take their motion from the track: redraw, but not for
        # every fix while auto-tracking (that ends with one redraw in _apply_track)
        if self._storm_fields_shown() and self.trk_stop_btn.disabled:
            self.request_map()

    def _on_storm_btn(self, ev):
        """The Storm chip: load the run's track file if there is no track yet, and open
        the Track tool."""
        found = None if self.fixes else self._track_file()
        self._show_panel(True, 2)
        if found:
            self.trk_path.value = found
            self._on_load_track(None)

    def _track_file(self):
        """The run's storm track file (track_dirs / track_patterns), or None; looked up
        once (again after a settings change)."""
        if self._track_found == ():
            self._track_found = config.find_track(self.run.path)
        return self._track_found

    def _update_storm_btn(self):
        """The Storm chip says whether there is a track and a fix at the shown time."""
        ts = sorted(self.fixes)
        b = self.storm_btn
        if not ts:
            found = self._track_file()
            name, cls = (f"Load storm track ({os.path.basename(found)})" if found
                         else "No storm track"), []
        elif self.t in self.fixes:
            name, cls = (f"Storm track · {len(ts)} fixes, {self.run.time_label(ts[0])}–"
                         f"{self.run.time_label(ts[-1])}"), ["cv-on"]
        else:
            name, cls = f"Storm track · no fix at this time ({len(ts)} fixes)", ["cv-warn"]
        if b.name != name:
            b.name = name
        b.css_classes = cls

    def _update_track_now(self):
        self._update_storm_btn()
        f = self.fixes.get(self.t)
        self.trk_del.disabled = f is None
        self.trk_now_src.data = dict(x=[f["x"]], y=[f["y"]]) if f else dict(x=[], y=[])
        self.trk_ts_now.data = (dict(tmin=[self.run.times[self.t] / 60.0], value=[f["value"]])
                                if f else dict(tmin=[], value=[]))

    def _cancel_track(self):
        self.gen["trk"] += 1
        self.trk_stop_btn.disabled = True
        self.trk_status.object = self._track_summary(" · stopped")

    def _on_clear_track(self, ev):
        self.gen["trk"] += 1
        self.trk_stop_btn.disabled = True
        self.fixes, self.trk_spec = {}, None
        self.points = [p for p in self.points if p[0] != "trk"]
        self.storm_follow.value = False
        self._update_track_view()
        self._draw_points()
        self.request_soundings()

    def _on_trk_path(self, ev):
        self.trk_dl.filename = os.path.basename(self.trk_path.value) or "meso_track.csv"

    def _track_download(self):
        fmt = "csv" if self.trk_dl.filename.lower().endswith(".csv") else "txt"
        text = trk.to_text(self.run, self.fixes, self.trk_spec or self._trk_opts(), fmt,
                           self.F)
        return io.BytesIO(text.encode())

    def _trk_default(self):
        return config.track_save_path(self.run.path)

    def _on_save_track(self, ev):
        path = config.expand(self.trk_path.value.strip())
        if path:
            self.confirm.ask([path], partial(self._save_track, path))

    def _save_track(self, path):
        try:
            path = trk.save(self.run, self.fixes, self.trk_spec or self._trk_opts(), path,
                            self.F)
        except OSError as e:
            self.trk_status.object = (f'<div class="cv-status" style="color:#f87171">Could '
                                      f'not save: {e}</div>')
            return
        self.trk_status.object = self._track_summary(f' · saved to <code>{path}</code>')
        self._track_found = ()  # the chip may now find this file
