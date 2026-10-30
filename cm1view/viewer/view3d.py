"""3D workspace: the scene job, camera, the pressure decomposition button,
and picking / sampling streamlines.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import os
import traceback
from functools import partial

import numpy as np
import panel as pn
from bokeh.events import MouseLeave, MouseMove
from bokeh.models import ColumnDataSource, CustomJS, HoverTool, LinearAxis, Range1d, Span
from bokeh.plotting import figure

from .. import pdecomp
from ..core import vectors, volume3d
from ..core.run import FileBusy, MissingAtTime
from ..theme import GRID, MUTED
from .ui import FRAME_SHORT, _bokeh, _html, style_fig

# The pointer on the streamline card's plot, in the browser: snap it to the nearest
# sample of each line and put it in the `at` Span (synced to the server, which moves the
# 3D cursor) only when a sample under it changes, at most every 150 ms. Each move of the
# 3D cursor makes plotly.js recompute and redraw the whole scene, meshes and all.
CURSOR_JS = """
const st = at._cv ?? (at._cv = {sent: undefined, timer: null, last: 0, x: null, key: ""})
const x = cb_obj.event_name === "mouseleave" ? null : cb_obj.x
if (at.location == null && x != null) st.sent = undefined  // cleared by the server
let key = ""
if (x != null) {
  for (const s of [sel.data.s, ...pins.data.xs]) {
    const n = s ? s.length : 0
    if (!n || x < s[0] || x > s[n - 1]) { key += n + ":-,"; continue }
    let lo = 0, hi = n - 1
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (s[m] <= x) lo = m; else hi = m }
    key += n + ":" + (x - s[lo] <= s[hi] - x ? lo : hi) + ","
  }
}
st.x = x
st.key = key
const send = () => {
  st.timer = null
  if (st.key === st.sent) return
  st.sent = st.key
  st.last = Date.now()
  at.location = st.x
}
if (st.timer == null && key !== st.sent) {
  const wait = 150 - (Date.now() - st.last)
  if (wait <= 0) send(); else st.timer = setTimeout(send, wait)
}
"""


class View3DPanel:
    def _build_streamline_card(self):
        """Floating card for the streamline clicked in the 3D scene and the pinned ones:
        a field and the height along each, against distance from its seed."""
        F = self.F
        along = {}
        if all(n in F for n in ("xvort", "yvort", "zvort")):
            along["Streamwise vorticity (streamline frame)"] = "_ws"
        along["Speed (streamline frame)"] = "_speed"
        self.sl_field = pn.widgets.Select(
            groups={"Along the streamline": along, **F.groups(ndim=3)},
            value="winterp" if "winterp" in F else next(iter(along.values())), width=250,
            height=32, margin=(4, 4))
        self.sl_clear = pn.widgets.Button(name="", icon="x", button_type="light",
                                          button_style="outline", width=34, height=32,
                                          margin=(4, 4),
                                          description="Clear the selection and the pins")
        self.sl_pin = pn.widgets.Button(name="", icon="pin", button_type="light",
                                        button_style="outline", width=34, height=32,
                                        margin=(4, 4), visible=False,
                                        description="Pin this streamline to compare it "
                                                    "with others")
        self.sl_info = _html(sizing_mode="stretch_width")
        self.sl_big = pn.widgets.Toggle(name="", icon="arrows-maximize", button_type="light",
                                        button_style="outline", width=34, height=32,
                                        margin=(4, 4))
        # fixed ranges fitted to the field (an automatic range would also take in the
        # height line and flatten the field); reset comes back to the fit
        fig = figure(sizing_mode="stretch_width", height=210, tools="pan,wheel_zoom,"
                     "box_zoom,reset,save", x_axis_label="Distance from seed (km)",
                     y_axis_label="", x_range=Range1d(0, 1), y_range=Range1d(0, 1),
                     active_scroll="wheel_zoom")
        style_fig(fig)
        fig.min_border_right = 10
        self.sl_src = ColumnDataSource(dict(s=[], v=[], z=[]))
        fig.extra_y_ranges = {"z": Range1d(0, 1)}
        zax = LinearAxis(y_range_name="z", axis_label="height (km)", axis_line_color=GRID,
                         major_tick_line_color=GRID, minor_tick_line_color=None,
                         major_label_text_color=MUTED, axis_label_text_color=MUTED,
                         axis_label_text_font_style="normal")
        fig.add_layout(zax, "right")
        fig.line("s", "z", source=self.sl_src, y_range_name="z", line_color=MUTED,
                 line_width=1.5, line_dash="dashed")
        # pinned lines under the selection, each in its pin colour
        self.sl_pins_src = ColumnDataSource(dict(xs=[], ys=[], zs=[], color=[], name=[]))
        fig.multi_line("xs", "zs", source=self.sl_pins_src, y_range_name="z",
                       line_color="color", line_alpha=0.6, line_width=1, line_dash="dashed")
        rp = fig.multi_line("xs", "ys", source=self.sl_pins_src, line_color="color",
                            line_width=2)
        fig.add_tools(HoverTool(renderers=[rp], tooltips=[("", "@name"),
                                                          ("s", "$x{0.00} km"),
                                                          ("value", "$y{0.000}")]))
        r = fig.line("s", "v", source=self.sl_src, line_color=volume3d.SELECTED, line_width=2)
        fig.add_layout(Span(location=0, dimension="height", line_color=MUTED,
                            line_dash="dotted", line_width=1))
        fig.add_tools(HoverTool(renderers=[r], mode="vline",
                                tooltips=[("s", "@s{0.00} km"), ("value", "@v{0.000}"),
                                          ("z", "@z{0.00} km")]))
        # the pointer's distance, snapped and throttled in the browser (CURSOR_JS)
        self.sl_at = Span(location=None, dimension="height", line_color=MUTED,
                          line_alpha=0.7, line_width=1)
        fig.add_layout(self.sl_at)
        cb = CustomJS(args=dict(at=self.sl_at, sel=self.sl_src, pins=self.sl_pins_src),
                      code=CURSOR_JS)
        fig.js_on_event(MouseMove, cb)
        fig.js_on_event(MouseLeave, cb)
        self.sl_at.on_change("location", lambda attr, old, new: self._sl_cursor_at(new))
        self.sl_fig = fig
        self.sl_card = pn.Column(
            pn.Row(self.sl_info, self.sl_field, self.sl_pin, self.sl_big, self.sl_clear,
                   margin=0,
                   sizing_mode="stretch_width"),
            _bokeh(fig, sizing_mode="stretch_width"),
            visible=False, margin=0,
            styles={"position": "absolute", "right": "12px", "bottom": "12px",
                    "width": "min(600px, 46vw)", "z-index": "25", "padding": "6px 8px",
                    "background": "rgba(17,23,35,0.94)", "border": f"1px solid {GRID}",
                    "border-radius": "10px", "box-shadow": "0 6px 20px rgba(0,0,0,.45)"})

        def big(e):
            fig.height = 440 if e.new else 210
            self.sl_card.styles = dict(self.sl_card.styles,
                                       width="min(1200px, 92vw)" if e.new else
                                       "min(600px, 46vw)")
            self.sl_big.icon = "arrows-minimize" if e.new else "arrows-maximize"
        self.sl_big.param.watch(big, "value")
        self._s3 = None      # last 3D scene: t, streamlines, frame offset
        self._sl_seed = None  # seed of the selected streamline (kept across re-renders)
        self._sl_line = None
        self._sl_pins = []    # pinned: dict(seed, line in this scene or None, color, no)
        self._pin_no = 0
        self._pin_of = []     # pin index of each point of the "pinned" trace
        self._sl_samples = []  # sampled lines: (first index, distances s, colour)
        self._sl_cursor = None  # distance under the pointer on the card's plot
        self._sl_cursor_pts = []  # cursor markers now in the scene
        self._sl_dim = False  # the streamlines are greyed (DIM_SCALE)
        self._sl_scale = None  # their own colour scale
        self._hl_line = None  # line now in the "selected" trace
        self._pl_key = ()  # (line, colour) of each pin now in the "pinned" trace
        self._fig3d = None    # the scene shown: the streamline traces are updated in it
        self._st_cache = {}  # build_scene's: the last tracing's inputs and streamlines

    # ================================================================ 3D
    def request_3d(self):
        if self.box is None:
            self._set_box(self.view)
        self.gen["3d"] += 1
        g = self.gen["3d"]
        spec = dict(t=self.t, box=self.box, ztop=float(self.v3_ztop.value),
                    exag=float(self.v3_exag.value), smooth=float(self.v3_smooth.value),
                    res=int(self.v3_res.value),
                    ground=dict(on=self.v3_ground.value, var=self.v3_floor.value,
                                z=float(self.v3_floor_z.value),
                                cmap=self.v3_floor_cmap.value, rev=self.v3_floor_rev.value,
                                range=self.v3_floor_range.value,
                                lo=float(self.v3_floor_min.value or 0.0),
                                hi=float(self.v3_floor_max.value or 0.0)),
                    isos=[dict(var=d["var"].value, val=float(d["val"].value or 0.0),
                               color=d["color"].value, op=float(d["op"].value))
                          for d in self.isos if d["on"].value],
                    storm=self._storm_motion(), fstorm=self._field_storm(self.t),
                    vecs=[dict(q=o["q"].value, level=float(o["level"].value),
                               frame=o["frame"].value, density=int(o["density"].value),
                               ref=float(o["ref"].value or vectors.VECTORS[o["q"].value].ref),
                               color=o["color"].value) for o in self.svs if o["on"].value],
                    stream=dict(on=self.st_on.value, z=float(self.st_z.value),
                                n=int(self.st_n.value), length=float(self.st_len.value),
                                dir=self.st_dir.value, frame=self.st_frame.value,
                                color_by=self.st_color.value,
                                seed_box=self._seed_in_box()))
        self.v3_status.object = '<div class="cv-status"><span class="busy">● Rendering…' \
                                '</span></div>'
        self.pools["3d"].submit(self._3d_job, spec, g)

    def _3d_job(self, spec, g):
        if g != self.gen["3d"]:
            return
        run, t = self.run, spec["t"]
        try:
            def prog(done, total, name):
                if total:
                    self._schedule(partial(
                        setattr, self.v3_status, "object",
                        f'<div class="cv-status"><span class="busy">● Loading 3D fields '
                        f'({done}/{total}) {name}…</span></div>'))

            sc = volume3d.build_scene(run, self.F, spec, progress=prog,
                                      cancelled=lambda: g != self.gen["3d"],
                                      cache=self._st_cache)
            if sc is None:
                return
            meshes, stream, stride = sc["meshes"], sc["stream"], sc["stride"]
            title = (f"t = {run.time_label(t)} · "
                     f"{'full res' if stride == 1 else f'1/{stride} res'}")
            fig = volume3d.scene_figure(meshes, sc["ground"], spec["box"], spec["ztop"],
                                        spec["exag"], title, vectors=sc["vecs"], stream=stream,
                                        camera=self.v3_cam.value, dragmode=self.v3_drag.value,
                                        revision=f"cam{self._cam_rev}")
            nf = sum(len(m["faces"]) for m in meshes)
            s3 = dict(t=t, stream=stream, off=sc["off"], frame=spec["stream"]["frame"])
            res = (fig, sc["notes"], nf, stride, s3)
        except (MissingAtTime, FileBusy) as e:  # expected: no traceback
            res = e
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["3d"]:
            self._schedule(partial(self._apply_3d, res, g))

    def _floor_widgets(self, *e):
        """Height only for 3D floor fields; Min/Max only for a custom range (filled from
        the field's display range when they are first shown)."""
        d = self.F[self.v3_floor.value] if self.v3_floor.value in self.F else None
        self.v3_floor_z.visible = d is not None and d.ndim == 3
        custom = self.v3_floor_range.value == "custom"
        if custom and not self.v3_floor_min.visible and d is not None and d.vrange:
            self.v3_floor_min.value, self.v3_floor_max.value = (float(v) for v in d.vrange)
        self.v3_floor_min.visible = self.v3_floor_max.visible = custom

    def _on_drag(self, ev):
        """Change what a left-drag does in the 3D scene, keeping the current camera."""
        fig = self.plot3d.object
        if fig is None:
            return
        fig.update_layout(scene_dragmode=ev.new)
        self.plot3d.object = fig
        self.plot3d.param.trigger("object")

    def _on_camera(self, ev):
        """Jump to a preset viewpoint without recomputing the scene."""
        self._cam_rev += 1
        fig = self.plot3d.object
        if fig is None:
            return
        fig.update_layout(uirevision=f"cam{self._cam_rev}",
                          scene_camera=volume3d.CAMERAS[ev.new])
        self.plot3d.object = fig
        self.plot3d.param.trigger("object")

    def _apply_3d(self, res, g):
        if g != self.gen["3d"]:
            return
        if isinstance(res, Exception):
            self.v3_status.object = f'<div class="cv-status" style="color:#f87171">{res}</div>'
            return
        fig, notes, nf, stride, s3 = res
        self._s3 = s3
        # keep the selected and pinned streamlines (same seeds) across re-renders,
        # e.g. in time
        line = self._seed_line(s3["stream"], self._sl_seed)
        for p in self._sl_pins:
            p["line"] = self._seed_line(s3["stream"], p["seed"])
        # keep the current view: Panel copies each rotate/zoom into the shown figure, and
        # once that camera has been sent back (any push of the figure), plotly's
        # uirevision sees the preset camera as a change and jumps back to it
        old = self.plot3d.object
        if old is not None and old.layout.scene.camera is not None:
            fig.update_layout(scene_camera=old.layout.scene.camera)
        # the highlights go into the new figure before it is shown, so they travel with
        # it; the old scene's cursor samples point into the old lines
        self._fig3d, self._sl_samples, self._sl_cursor_pts = fig, [], []
        _, base = self._trace("stream")
        self._sl_scale = base.line.colorscale if base is not None else None
        self._sl_dim, self._hl_line, self._pl_key = False, None, ()
        self._select_line(line)
        self.plot3d.object = fig
        self.plot3d.visible = True
        extra = (" · " + " · ".join(notes)) if notes else ""
        self.v3_status.object = (f'<div class="cv-status">{nf:,} triangles · '
                                 f'{"full" if stride == 1 else f"1/{stride}"} resolution'
                                 f'{extra}</div>')

    # ---------------------------------------------------------- pressure decomposition
    def _pd_button(self, btn, names, t):
        """Offer the decomposition for time t when a shown field needs it: missing at t,
        or only in the file from the earlier (pre-fix) script."""
        run, label = self.run, None
        if any(pdecomp.is_pdecomp(self.F, n) for n in names) and pdecomp.can_compute(run):
            kind, _ = pdecomp.source(run, t, block=False)
            write = self.pd_write.value and pdecomp.writable(run, t)
            par = len(os.sched_getaffinity(0)) > 1  # ~45 s with 4 CPUs; writing ~+40 s
            est = {(True, False): "~45 s", (True, True): "~1.5 min",
                   (False, False): "~1.5 min", (False, True): "~2 min"}[(par, write)]
            if kind is None:
                label = (f"Compute pressure decomposition for {run.time_label(t)}"
                         f"{' and write it to the file' if write else ''} ({est})")
            elif kind == "file-old":
                label = (f"Recompute {run.time_label(t)} with {pdecomp.script_name()}"
                         f"{' and overwrite it in the file' if write else ''} ({est})")
        busy = pdecomp.running(run, t) is not None
        if busy:
            label = f"Computing pressure decomposition for {run.time_label(t)}…"
        btn.param.update(name=label or "", disabled=busy)
        (self.pd_row if btn is self.pd_btn else btn).visible = label is not None
        self.pd_write.disabled = busy or not pdecomp.writes_allowed()

    def _on_pd_compute(self, ev):
        t = self.t
        if pdecomp.running(self.run, t) is not None:
            return
        for b in (self.pd_btn, self.xs_pd_btn):
            b.param.update(disabled=True, name=f"Computing pressure decomposition for "
                                               f"{self.run.time_label(t)}…")
        self.pd_write.disabled = True
        self.pools["pd"].submit(self._pd_job, t, self.pd_write.value)

    def _pd_job(self, t, write):
        run = self.run

        def prog(el, phase):
            self._status_async(f'<span class="busy">● Pressure decomposition for '
                               f'{run.time_label(t)}: {phase} … {el:.0f} s</span>')
        try:
            res = pdecomp.compute(run, t, prog, write=write and pdecomp.writable(run, t))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        self._schedule(partial(self._apply_pd, t, res))

    def _apply_pd(self, t, res):
        if isinstance(res, Exception):
            self._set_status(f'<span style="color:#f87171">{res}</span>')
        else:
            where = ("written to " + os.path.basename(self.run.files[t]) if res["wrote"]
                     else "kept in memory, not written to the file")
            if res.get("write_error"):
                where = (f'<span style="color:#f87171">kept in memory; writing to the file '
                         f'failed: {res["write_error"]}</span>')
            self._set_status(f'Pressure decomposition for {self.run.time_label(t)} computed '
                             f'in {res["elapsed"]:.0f} s with {pdecomp.script_name()}; {where}')
            self.F.forget(t, pdecomp.NAMES)
        self._pd_button(self.pd_btn, self._shown_names(), self.t)
        self._pd_button(self.xs_pd_btn, self._xs_names(), self.t)
        if isinstance(res, Exception) or t != self.t:
            return
        self.request_map()
        if len(self.xs_pts) == 2:
            self.request_xsec()
        if self.gen["3d"] and self.workspace.value == "3D":
            self.request_3d()

    # ---------------------------------------------------------- streamline pick
    def _trace(self, meta):
        fig = self._fig3d
        for n, tr in enumerate(fig.data if fig is not None else ()):
            if tr.meta == meta:
                return n, tr
        return None, None

    def _on_3d_click(self, ev):
        pts = (ev.new or {}).get("points") or []
        if not pts or self._s3 is None or self._s3["stream"] is None:
            return
        p = pts[0]
        if p.get("pointNumber") is None:
            return
        # cleared, so that clicking the same point again (e.g. after ×) fires again
        self.plot3d.click_data = None
        k, c = int(p["pointNumber"]), p.get("curveNumber")
        idx, base = self._trace("stream")
        pidx, pl = self._trace("pinned")
        tr = base if c == idx else pl if c == pidx else None
        if tr is None or k >= len(tr.x if tr.x is not None else ()):
            return
        # a click made on the previous scene (sent while a re-render was on its way) is
        # not at that point of this one
        if any(p.get(a) is not None and not np.isclose(p[a], getattr(tr, a)[k], atol=1e-3)
               for a in ("x", "y", "z")):
            return
        if idx is not None and c == idx:
            segs = self._s3["stream"]["segs"]
            line = int(np.searchsorted(segs[:, 0], k, side="right")) - 1
            if 0 <= line < len(segs) and k < segs[line, 1]:
                self._select_line(line)
        elif pidx is not None and c == pidx and k < len(self._pin_of):
            self._select_line(self._sl_pins[self._pin_of[k]]["line"])

    @staticmethod
    def _seed_line(st, seed):
        """The streamline of `st` seeded at `seed` (x, y, z), or None."""
        if st is None or seed is None:
            return None
        sd = st["segs"][:, 2]
        d = np.max(np.abs(np.stack([st["x"][sd], st["y"][sd], st["z"][sd]], axis=1)
                          - np.asarray(seed)), axis=1)
        return int(np.argmin(d)) if d.size and d.min() < 1e-3 else None

    def _pin_index(self, seed):
        if seed is None:
            return None
        for i, p in enumerate(self._sl_pins):
            if np.max(np.abs(np.subtract(p["seed"], seed))) < 1e-3:
                return i
        return None

    def _select_line(self, line):
        """Select streamline `line` (None: clear the selection, keeping the pins) and plot
        fields along it and the pins."""
        st = self._s3["stream"] if self._s3 else None
        if line is None or st is None or self._trace("selected")[1] is None:
            self._sl_seed, self._sl_line = None, None
        else:
            sd = int(st["segs"][line, 2])
            self._sl_seed = (float(st["x"][sd]), float(st["y"][sd]), float(st["z"][sd]))
            self._sl_line = line
        self._draw_lines()
        self._sample_line()

    def _on_pin(self, ev=None):
        """Pin the selected streamline in a colour of its own (and drop the selection, so
        the next click picks another), or unpin it when it is already pinned."""
        if self._sl_seed is None:
            return
        k = self._pin_index(self._sl_seed)
        if k is not None:
            del self._sl_pins[k]
        else:
            used = {p["color"] for p in self._sl_pins}
            free = [c for c in volume3d.PIN_COLORS if c not in used]
            self._pin_no += 1
            self._sl_pins.append(dict(
                seed=self._sl_seed, line=self._sl_line, no=self._pin_no,
                color=free[0] if free else
                volume3d.PIN_COLORS[len(self._sl_pins) % len(volume3d.PIN_COLORS)]))
        self._select_line(None if k is None else self._sl_line)

    def _clear_lines(self):
        """The card's ×: drop the selection and every pin."""
        self._sl_pins = []
        self._select_line(None)

    def _draw_lines(self):
        """Draw the selection (yellow) and the pins into the 3D scene's highlight traces,
        the other streamlines grey and faint meanwhile; the card shows while there is either.
        Once the figure is shown, Panel sends each trace's update as a Plotly.restyle of
        that trace; re-sending the figure (param.trigger) would rebuild the whole scene,
        meshes and all, in the browser."""
        st = self._s3["stream"] if self._s3 else None
        _, hl = self._trace("selected")
        _, seed = self._trace("seed")
        _, pl = self._trace("pinned")
        _, ps = self._trace("pinseeds")
        if hl is not None and self._sl_line != self._hl_line:
            self._hl_line = self._sl_line
            if self._sl_line is None:
                hl.update(x=[], y=[], z=[])
                seed.update(x=[], y=[], z=[])
            else:
                a, b, sd = (int(v) for v in st["segs"][self._sl_line])
                hl.update(x=st["x"][a:b], y=st["y"][a:b], z=st["z"][a:b])
                seed.update(x=[st["x"][sd]], y=[st["y"][sd]], z=[st["z"][sd]])
        _, base = self._trace("stream")
        if base is not None:  # the rest go grey while a line is selected or pinned
            focus = self._sl_line is not None or any(p["line"] is not None
                                                     for p in self._sl_pins)
            if focus != self._sl_dim:  # scale and opacity: the colours stay in the browser
                self._sl_dim = focus
                base.update(line_colorscale=volume3d.DIM_SCALE if focus else self._sl_scale,
                            opacity=volume3d.DIM_OPACITY if focus else 1.0)
        key = tuple((p["line"], p["color"]) for p in self._sl_pins)
        if pl is not None and key != self._pl_key:
            self._pl_key = key
            parts = [(i, p, *(int(v) for v in st["segs"][p["line"]]))
                     for i, p in enumerate(self._sl_pins) if p["line"] is not None]

            def cat(k):  # the pins' points, a NaN after each line to break it
                return (np.concatenate([np.append(np.asarray(st[k][a:b], np.float64), np.nan)
                                        for _, _, a, b, _ in parts]) if parts else [])
            colors = np.repeat([volume3d.PIN_COLORS.index(p["color"]) for _, p, *_ in parts],
                               [b - a + 1 for _, _, a, b, _ in parts])
            pl.update(x=cat("x"), y=cat("y"), z=cat("z"), line_color=colors)
            ps.update(x=[st["x"][sd] for *_, sd in parts], y=[st["y"][sd] for *_, sd in parts],
                      z=[st["z"][sd] for *_, sd in parts],
                      marker_color=[p["color"] for _, p, *_ in parts])
            self._pin_of = [i for i, _, a, b, _ in parts for _ in range(b - a + 1)]
        pinned = self._pin_index(self._sl_seed) is not None
        self.sl_pin.param.update(
            visible=self._sl_line is not None, icon="pinned-off" if pinned else "pin",
            description="Unpin this streamline" if pinned else
            "Pin this streamline to compare it with others")
        self.sl_card.visible = self._sl_line is not None or bool(self._sl_pins)

    def _sample_line(self):
        """Sample the field along the selection and the pins in this scene (one job)."""
        st = self._s3["stream"] if self._s3 else None
        self.gen["sl"] += 1
        g = self.gen["sl"]
        lines = []
        if st is not None:
            cur = self._pin_index(self._sl_seed)
            if self._sl_line is not None:
                lines.append(dict(key="sel", color=volume3d.SELECTED, line=self._sl_line,
                                  no=self._sl_pins[cur]["no"] if cur is not None else None))
            lines += [dict(key="pin", color=p["color"], line=p["line"], no=p["no"])
                      for i, p in enumerate(self._sl_pins)
                      if p["line"] is not None and i != cur]
        if not lines:
            if self.sl_card.visible:
                self._apply_sl(g, dict(label=None, lines=[]))
            return
        for L in lines:
            L["abs"] = tuple(int(v) for v in st["segs"][L["line"]])
        self.sl_info.object = ('<div class="cv-status"><span class="busy">● Sampling…'
                               '</span></div>')
        self.pools["sl"].submit(self._sl_job, g, dict(self._s3), self.sl_field.value, lines)

    def _sl_job(self, g, s3, name, lines):
        run, F, t, st = self.run, self.F, s3["t"], s3["stream"]
        try:
            if name in ("_ws", "_speed"):
                wind = ["uinterp", "vinterp", "winterp"]
                vort = ["xvort", "yvort", "zvort"] if name == "_ws" else []
                run.load_volumes(wind + vort, t)
                cu, cv = s3["off"]
                label = "speed (m/s)" if name == "_speed" else "streamwise vorticity (1/s)"
            else:
                fst = self._field_storm(t)
                label = F[name].title + (f" · {fst[1]}" if F[name].storm else "")
            out = []
            for L in lines:
                a, b, sd = L["abs"]
                x, y, z = (np.asarray(st[k][a:b], np.float64) for k in ("x", "y", "z"))
                ds = np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2 + np.diff(z) ** 2)
                s = np.concatenate(([0.0], np.cumsum(ds)))
                s -= s[sd - a]

                def samp(vol):
                    return volume3d.sample_points(run, vol, x, y, z)

                if name in ("_ws", "_speed"):
                    u = samp(run.volume("uinterp", t)) - cu
                    v = samp(run.volume("vinterp", t)) - cv
                    w = samp(run.volume("winterp", t))
                    spd = np.sqrt(u * u + v * v + w * w)
                    if name == "_speed":
                        val = spd
                    else:
                        ox, oy, oz = (samp(run.volume(n, t)) for n in vort)
                        val = (ox * u + oy * v + oz * w) / np.maximum(spd, 1e-6)
                else:
                    val = F.at_points(name, t, samp, storm=fst[0])
                out.append(dict(key=L["key"], color=L["color"], no=L["no"], s=s, a=a,
                                v=np.asarray(val, np.float64), z=z, x0=x[sd - a],
                                y0=y[sd - a], z0=z[sd - a], length=float(s[-1] - s[0])))
            res = dict(label=label, lines=out)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["sl"]:
            self._schedule(partial(self._apply_sl, g, res))

    def _apply_sl(self, g, res):
        """Plot the sampled lines: the selection on its own source (with the vline hover),
        the pins on a multi-line one; the axes fit them all."""
        if g != self.gen["sl"]:
            return
        if isinstance(res, Exception):
            self.sl_info.object = f'<div class="cv-status" style="color:#f87171">{res}</div>'
            return
        lines = res["lines"]
        self._sl_samples = [(L["a"], L["s"], L["color"]) for L in lines]
        self.sl_at.location = None  # the cursor is redrawn when the pointer next moves
        sel = next((L for L in lines if L["key"] == "sel"), None)
        pins = [L for L in lines if L["key"] != "sel"]
        self.sl_src.data = (dict(s=sel["s"], v=sel["v"], z=sel["z"]) if sel else
                            dict(s=[], v=[], z=[]))
        self.sl_pins_src.data = dict(xs=[L["s"] for L in pins], ys=[L["v"] for L in pins],
                                     zs=[L["z"] for L in pins],
                                     color=[L["color"] for L in pins],
                                     name=[f'#{L["no"]}' for L in pins])
        frame = FRAME_SHORT[self._s3["frame"]] if self._s3 else ""
        gone = sum(p["line"] is None for p in self._sl_pins)
        gone = (f' · <span style="color:{MUTED}">{gone} pinned not in this scene</span>'
                if gone else "")
        if not lines:
            self.sl_info.object = (f'<div class="cv-status">No pinned streamline in this '
                                   f'scene{gone}</div>')
            return

        def cat(k):
            return np.concatenate([np.asarray(L[k], np.float64) for L in lines])
        z = cat("z")
        z0, z1 = float(np.nanmin(z)), float(np.nanmax(z))
        pad = 0.05 * max(z1 - z0, 0.1)
        self.sl_fig.extra_y_ranges["z"].update(start=max(0.0, z0 - pad), end=z1 + pad)

        def fit(rng, a):
            a = a[np.isfinite(a)]
            lo, hi = (float(a.min()), float(a.max())) if a.size else (0.0, 1.0)
            d = 0.05 * (hi - lo) if hi > lo else (abs(lo) * 0.1 or 1.0)
            rng.update(start=lo - d, end=hi + d, reset_start=lo - d, reset_end=hi + d)
        fit(self.sl_fig.x_range, cat("s"))
        fit(self.sl_fig.y_range, cat("v"))
        self.sl_fig.yaxis[0].axis_label = res["label"]
        def name(L):  # "#3", "Selected", or "Selected #3" when the selection is pinned
            no = f'#{L["no"]}' if L["no"] else ""
            return f"Selected {no}".rstrip() if L["key"] == "sel" else no
        if sel and not pins:
            self.sl_info.object = (
                f'<div class="cv-status" style="line-height:1.35"><b style="color:'
                f'{volume3d.SELECTED}">Streamline{name(sel).replace("Selected", "")}</b> '
                f'({frame}) · seed '
                f'({sel["x0"]:.1f}, {sel["y0"]:.1f}) km, {sel["z0"] * 1000:.0f} m<br>'
                f'{sel["length"]:.1f} km long · z {z0:.2f}–{z1:.2f} km{gone}</div>')
            return
        rows = "".join(
            f'<div><b style="color:{L["color"]}">■ {name(L)}</b> seed ({L["x0"]:.1f}, '
            f'{L["y0"]:.1f}) km, {L["z0"] * 1000:.0f} m · {L["length"]:.1f} km</div>'
            for L in lines)
        self.sl_info.object = (
            f'<div class="cv-status" style="line-height:1.35"><b>{len(lines)} streamlines'
            f'</b> ({frame}){gone}<div style="max-height:4.2em;overflow-y:auto">{rows}'
            f'</div></div>')

    def _sl_cursor_at(self, x):
        """The pointer is at distance x on the card's plot (None: it left): mark that
        point of each line in the 3D scene. The browser snaps and throttles x
        (CURSOR_JS)."""
        self._sl_cursor = x
        self._draw_cursor()

    def _draw_cursor(self):
        st = self._s3["stream"] if self._s3 else None
        _, cur = self._trace("cursor")
        if self._closed or st is None or cur is None:
            return
        x, pts = self._sl_cursor, []
        if x is not None:
            for a, s, color in self._sl_samples:
                i = a + int(np.argmin(np.abs(s - x)))
                if s[0] <= x <= s[-1] and i < len(st["x"]):
                    pts.append((float(st["x"][i]), float(st["y"][i]), float(st["z"][i]),
                                color))
        if pts == self._sl_cursor_pts:  # same samples under the pointer: nothing to send
            return
        self._sl_cursor_pts = pts
        # one small restyle of this trace, not the whole scene (see _draw_lines)
        cur.update(x=[p[0] for p in pts], y=[p[1] for p in pts], z=[p[2] for p in pts],
                   marker_color=[p[3] for p in pts])

    # ---------------------------------------------------------- streamline seed box
    def _on_pick_seeds(self, ev=None):
        self.workspace.value = "Map"
        self.mode.set("Seed box")

    def _set_seed_box(self, box):
        x0, x1, y0, y1 = box
        self.seed_box = (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1))
        self._update_seed_box()

    def _clear_seed_box(self, ev=None):
        had = self.seed_box is not None
        self.seed_box = None
        self._update_seed_box()
        if had and self.st_on.value and self.gen["3d"]:
            self.request_3d()

    def _seed_in_box(self):
        """The seed box inside the 3D region, or None (seed the whole region)."""
        if self.seed_box is None or self.box is None:
            return None
        s0, s1, t0, t1 = self.seed_box
        x0, x1, y0, y1 = self.box
        b = (max(s0, x0), min(s1, x1), max(t0, y0), min(t1, y1))
        return b if b[1] > b[0] and b[3] > b[2] else None

    def _update_seed_box(self):
        b = self.seed_box
        self.seed_src.data = (dict(left=[b[0]], right=[b[1]], bottom=[b[2]], top=[b[3]])
                              if b else dict(left=[], right=[], bottom=[], top=[]))
        self.st_seed_clear.visible = b is not None
        where = (f"the seed box ({b[1] - b[0]:.1f} × {b[3] - b[2]:.1f} km)" if b else
                 "the whole region")
        self.st_seed_html.object = (
            f'<div class="cv-hint" style="margin:0 0 12px">Instantaneous streamlines seeded '
            f'on an n×n grid over {where}; they run until they leave the region.</div>')
