"""3D workspace: the scene job, camera, the pressure decomposition button,
and picking / sampling streamlines.

A mixin of the Viewer (cm1view/app.py): its methods use the Viewer's widgets and state."""

import os
import traceback
from functools import partial

import numpy as np
import panel as pn
from bokeh.models import ColumnDataSource, HoverTool, LinearAxis, Range1d, Span
from bokeh.plotting import figure

from . import pdecomp, volume3d
from .run import FileBusy, MissingAtTime
from .theme import GRID, MUTED
from .ui import FRAME_SHORT, _bokeh, _html, style_fig


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
                    vec=dict(on=self.sv_on.value, level=float(self.sv_lvl.value),
                             frame=self.sv_frame.value, density=int(self.sv_density.value),
                             ref=float(self.sv_ref.value or 20.0), color=self.sv_color.value),
                    stream=dict(on=self.st_on.value, z=float(self.st_z.value),
                                n=int(self.st_n.value), length=float(self.st_len.value),
                                dir=self.st_dir.value, frame=self.st_frame.value,
                                color_by=self.st_color.value))
        self.v3_status.object = '<div class="cv-status"><span class="busy">● Rendering…' \
                                '</span></div>'
        self.pools["3d"].submit(self._3d_job, spec, g)

    def _3d_job(self, spec, g):
        if g != self.gen["3d"]:
            return
        run, F, t = self.run, self.F, spec["t"]
        try:
            names = []
            for iso in spec["isos"]:
                names += F.native_deps(iso["var"])
            if spec["stream"]["on"]:
                names += ["uinterp", "vinterp", "winterp"]

            def prog(done, total, name):
                if total:
                    self._schedule(partial(
                        setattr, self.v3_status, "object",
                        f'<div class="cv-status"><span class="busy">● Loading 3D fields '
                        f'({done}/{total}) {name}…</span></div>'))

            if not run.load_volumes(names, t, progress=prog,
                                    cancelled=lambda: g != self.gen["3d"]):
                return
            stride = spec["res"] or volume3d.auto_stride(run, spec["box"], spec["ztop"], 12e6)
            meshes, notes = [], []
            for iso in spec["isos"]:
                d = F[iso["var"]]
                m = volume3d.isosurface(run, F.volume(iso["var"], t, spec["fstorm"][0]),
                                        spec["box"], iso["val"], stride, spec["smooth"],
                                        spec["ztop"])
                name = f'{d.label} = {iso["val"]:g} {d.units}'
                if d.storm:
                    name += f' ({spec["fstorm"][1]})'
                if m is None:
                    notes.append(f"{name}: no surface in region")
                    continue
                if m["step"] > 1:
                    notes.append(f"{name}: coarsened ×{m['step']} (mesh too large)")
                m.update(color=iso["color"], opacity=iso["op"], name=name)
                meshes.append(m)
            ground = self._floor(spec["ground"], spec["box"], t, spec["fstorm"])
            vectors = stream = None
            vs, ss = spec["vec"], spec["stream"]
            if vs["on"]:
                cu, cv = self._frame_offset(vs["frame"], spec["storm"])
                u = F.plane("uinterp", t, "height", vs["level"]) - cu
                v = F.plane("vinterp", t, "height", vs["level"]) - cv
                X, Y, _ = volume3d.surface_vectors(run, u, v, spec["box"], vs["density"],
                                                   vs["ref"])
                zlev = max(vs["level"], float(run.z[0]))
                # drawn at least 2% of the scene height up: right at z = 0 the opaque
                # reflectivity floor hides them (depth-buffer ties); label keeps zlev
                vectors = dict(x=X, y=Y, z=max(zlev, 0.02 * spec["ztop"]), color=vs["color"],
                               name=f'Winds @ {zlev * 1000:.0f} m ({FRAME_SHORT[vs["frame"]]})')
            if ss["on"]:
                stream = volume3d.streamlines(
                    run, run.volume("uinterp", t), run.volume("vinterp", t),
                    run.volume("winterp", t), spec["box"], spec["ztop"], ss["z"], ss["n"],
                    ss["length"], ss["dir"], self._frame_offset(ss["frame"], spec["storm"]))
                if stream is None:
                    notes.append("streamlines: none (calm or outside region)")
                else:
                    stream.update(color_by=ss["color_by"],
                                  name=f'Streamlines ({FRAME_SHORT[ss["frame"]]}, '
                                       f'{stream["n"]})')
            title = (f"t = {run.time_label(t)} · "
                     f"{'full res' if stride == 1 else f'1/{stride} res'}")
            fig = volume3d.scene_figure(meshes, ground, spec["box"], spec["ztop"],
                                        spec["exag"], title, vectors=vectors, stream=stream,
                                        camera=self.v3_cam.value, dragmode=self.v3_drag.value,
                                        revision=f"cam{self._cam_rev}")
            nf = sum(len(m["faces"]) for m in meshes)
            s3 = dict(t=t, stream=stream, off=self._frame_offset(ss["frame"], spec["storm"]),
                      frame=ss["frame"])
            res = (fig, notes, nf, stride, s3)
        except (MissingAtTime, FileBusy) as e:  # expected: no traceback
            res = e
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["3d"]:
            self._schedule(partial(self._apply_3d, res, g))

    def _floor(self, fs, box, t, fstorm):
        """The floor surface for scene_figure (None when off): the field over the region,
        thinned to about 300 points across, with its colours and range."""
        F, run, name = self.F, self.run, fs["var"]
        if not fs["on"] or name not in F:
            return None
        d = F[name]
        i0, i1, j0, j1 = volume3d.box_indices(run, box)
        gs = max(1, int(np.ceil(max(i1 - i0, j1 - j0) / 300)))
        a = F.plane(name, t, "height", fs["z"], storm=fstorm[0])[j0:j1:gs, i0:i1:gs]
        a = np.asarray(a, np.float64)
        cmap = d.cmap if fs["cmap"] == "Field default" else fs["cmap"]
        title = d.title
        if d.ndim == 3:
            title += f' @ {max(fs["z"], float(run.z[0])) * 1000:.0f} m'
        if d.storm:
            title += f" ({fstorm[1]})"
        if fs["range"] == "custom" and fs["hi"] > fs["lo"]:
            lo, hi = fs["lo"], fs["hi"]
        elif cmap == "reflectivity" and not fs["rev"]:
            lo, hi = 0.0, 75.0  # the stepped NWS scale is laid out for 0-75 dBZ
        else:
            lo, hi = volume3d.floor_range(a, d.vrange, d.diverging, fs["range"])
        return dict(x=run.xh[i0:i1:gs], y=run.yh[j0:j1:gs], a=a, lo=lo, hi=hi, title=title,
                    colorscale=volume3d.floor_colorscale(cmap, fs["rev"]))

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

    def _frame_offset(self, frame, storm):
        """What to subtract from grid-relative (u, v) to get the wanted frame."""
        run = self.run
        if frame == "ground":
            return (-run.umove, -run.vmove)
        if frame == "storm":
            return (storm[0] - run.umove, storm[1] - run.vmove)
        return (0.0, 0.0)

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
        self.plot3d.object = fig
        self._select_line(line, push=False)
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
        self._pd_button(self.pd_btn, [self.fill_var.value] +
                        [o["var"].value for o in self.ovs if o["on"].value], self.t)
        self._pd_button(self.xs_pd_btn, [self.xs_fill.value, self.xs_cont.value], self.t)
        if isinstance(res, Exception) or t != self.t:
            return
        self.request_map()
        if len(self.xs_pts) == 2:
            self.request_xsec()
        if self.gen["3d"] and self.workspace.value == "3D":
            self.request_3d()

    # ---------------------------------------------------------- streamline pick
    def _trace(self, meta):
        fig = self.plot3d.object
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
        k, c = int(p["pointNumber"]), p.get("curveNumber")
        idx, _ = self._trace("stream")
        pidx, _ = self._trace("pinned")
        if idx is not None and c == idx:
            segs = self._s3["stream"]["segs"]
            line = int(np.searchsorted(segs[:, 0], k, side="right")) - 1
            if 0 <= line < len(segs) and k < segs[line, 1]:
                self._select_line(line)
        elif pidx is not None and c == pidx and k < len(self._pin_of):
            self._select_line(self._sl_pins[self._pin_of[k]]["line"])

    @staticmethod
    def _seed_line(st, seed):
        """The streamline of `st` seeded at `seed` (x, y), or None."""
        if st is None or seed is None:
            return None
        sd = st["segs"][:, 2]
        d = np.hypot(st["x"][sd] - seed[0], st["y"][sd] - seed[1])
        return int(np.argmin(d)) if d.size and d.min() < 1e-3 else None

    def _pin_index(self, seed):
        if seed is None:
            return None
        for i, p in enumerate(self._sl_pins):
            if np.hypot(p["seed"][0] - seed[0], p["seed"][1] - seed[1]) < 1e-3:
                return i
        return None

    def _select_line(self, line, push=True):
        """Select streamline `line` (None: clear the selection, keeping the pins) and plot
        fields along it and the pins."""
        st = self._s3["stream"] if self._s3 else None
        if line is None or st is None or self._trace("selected")[1] is None:
            self._sl_seed, self._sl_line = None, None
        else:
            sd = int(st["segs"][line, 2])
            self._sl_seed = (float(st["x"][sd]), float(st["y"][sd]))
            self._sl_line = line
        self._draw_lines(push)
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

    def _draw_lines(self, push=True):
        """Draw the selection (yellow) and the pins into the 3D scene's highlight traces;
        the card shows while there is either."""
        st = self._s3["stream"] if self._s3 else None
        _, hl = self._trace("selected")
        _, seed = self._trace("seed")
        _, pl = self._trace("pinned")
        _, ps = self._trace("pinseeds")
        if hl is not None:
            if self._sl_line is None:
                hl.update(x=[], y=[], z=[])
                seed.update(x=[], y=[], z=[])
            else:
                a, b, sd = (int(v) for v in st["segs"][self._sl_line])
                hl.update(x=st["x"][a:b], y=st["y"][a:b], z=st["z"][a:b])
                seed.update(x=[st["x"][sd]], y=[st["y"][sd]], z=[st["z"][sd]])
        parts = []
        if pl is not None:
            parts = [(i, p, *(int(v) for v in st["segs"][p["line"]]))
                     for i, p in enumerate(self._sl_pins) if p["line"] is not None]

            def cat(k):  # the pins' points, a NaN after each line to break it
                return (np.concatenate([np.append(np.asarray(st[k][a:b], np.float64), np.nan)
                                        for _, _, a, b, _ in parts]) if parts else [])
            colors = [p["color"] for _, p, a, b, _ in parts for _ in range(b - a + 1)]
            pl.update(x=cat("x"), y=cat("y"), z=cat("z"), line_color=colors)
            ps.update(x=[st["x"][sd] for *_, sd in parts], y=[st["y"][sd] for *_, sd in parts],
                      z=[st["z"][sd] for *_, sd in parts],
                      marker_color=[p["color"] for _, p, *_ in parts])
            self._pin_of = [i for i, _, a, b, _ in parts for _ in range(b - a + 1)]
        if push and hl is not None:  # only the changed (highlight) traces are sent
            self.plot3d.param.trigger("object")
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
                out.append(dict(key=L["key"], color=L["color"], no=L["no"], s=s,
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
