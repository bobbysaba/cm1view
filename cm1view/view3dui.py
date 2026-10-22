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
        """Floating card for the streamline clicked in the 3D scene: a field and the
        height along it, against distance from the seed."""
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
                                          margin=(4, 4), description="Clear the selection")
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
        r = fig.line("s", "v", source=self.sl_src, line_color=volume3d.SELECTED, line_width=2)
        fig.add_layout(Span(location=0, dimension="height", line_color=MUTED,
                            line_dash="dotted", line_width=1))
        fig.add_tools(HoverTool(renderers=[r], mode="vline",
                                tooltips=[("s", "@s{0.00} km"), ("value", "@v{0.000}"),
                                          ("z", "@z{0.00} km")]))
        self.sl_fig = fig
        self.sl_card = pn.Column(
            pn.Row(self.sl_info, self.sl_field, self.sl_big, self.sl_clear, margin=0,
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

    # ================================================================ 3D
    def request_3d(self):
        if self.box is None:
            self._set_box(self.view)
        self.gen["3d"] += 1
        g = self.gen["3d"]
        spec = dict(t=self.t, box=self.box, ztop=float(self.v3_ztop.value),
                    exag=float(self.v3_exag.value), smooth=float(self.v3_smooth.value),
                    res=int(self.v3_res.value), ground=self.v3_ground.value,
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
            ground = None
            if spec["ground"] and "cref" in F:
                i0, i1, j0, j1 = volume3d.box_indices(run, spec["box"])
                gs = max(1, int(np.ceil(max(i1 - i0, j1 - j0) / 300)))
                a = F.plane("cref", t)[j0:j1:gs, i0:i1:gs]
                ground = (run.xh[i0:i1:gs], run.yh[j0:j1:gs], a)
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
        # keep the selected streamline (same seed) across re-renders, e.g. in time
        line = None
        if self._sl_seed is not None and s3["stream"] is not None:
            st = s3["stream"]
            seeds = st["segs"][:, 2]
            d = np.hypot(st["x"][seeds] - self._sl_seed[0], st["y"][seeds] - self._sl_seed[1])
            if d.size and d.min() < 1e-3:
                line = int(np.argmin(d))
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
        idx, _ = self._trace("stream")
        if not pts or idx is None or self._s3 is None or self._s3["stream"] is None:
            return
        p = pts[0]
        if p.get("curveNumber") != idx or p.get("pointNumber") is None:
            return
        segs = self._s3["stream"]["segs"]
        k = int(p["pointNumber"])
        line = int(np.searchsorted(segs[:, 0], k, side="right")) - 1
        if 0 <= line < len(segs) and k < segs[line, 1]:
            self._select_line(line)

    def _select_line(self, line, push=True):
        """Highlight streamline `line` (None: clear) and plot fields along it."""
        _, hl = self._trace("selected")
        _, seed = self._trace("seed")
        st = self._s3["stream"] if self._s3 else None
        if line is None or st is None or hl is None:
            self._sl_seed, self._sl_line = None, None
            self.sl_card.visible = False
            if hl is not None and hl.x is not None and len(hl.x):
                hl.update(x=[], y=[], z=[])
                seed.update(x=[], y=[], z=[])
                if push:
                    self.plot3d.param.trigger("object")
            return
        a, b, sd = (int(v) for v in st["segs"][line])
        hl.update(x=st["x"][a:b], y=st["y"][a:b], z=st["z"][a:b])
        seed.update(x=[st["x"][sd]], y=[st["y"][sd]], z=[st["z"][sd]])
        self._sl_seed = (float(st["x"][sd]), float(st["y"][sd]))
        self._sl_line = line
        if push:  # only the changed (highlight) traces are sent to the browser
            self.plot3d.param.trigger("object")
        self.sl_card.visible = True
        self._sample_line()

    def _sample_line(self):
        if self._s3 is None or self._s3["stream"] is None or self._sl_line is None:
            return
        self.gen["sl"] += 1
        g = self.gen["sl"]
        a, b, sd = (int(v) for v in self._s3["stream"]["segs"][self._sl_line])
        self.sl_info.object = ('<div class="cv-status"><span class="busy">● Sampling…'
                               '</span></div>')
        self.pools["sl"].submit(self._sl_job, g, dict(self._s3), self.sl_field.value,
                                a, b, sd)

    def _sl_job(self, g, s3, name, a, b, sd):
        run, F, t, st = self.run, self.F, s3["t"], s3["stream"]
        try:
            x, y, z = (np.asarray(st[k][a:b], np.float64) for k in ("x", "y", "z"))
            ds = np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2 + np.diff(z) ** 2)
            s = np.concatenate(([0.0], np.cumsum(ds)))
            s -= s[sd - a]

            def samp(vol):
                return volume3d.sample_points(run, vol, x, y, z)

            if name in ("_ws", "_speed"):
                wind = ["uinterp", "vinterp", "winterp"]
                vort = ["xvort", "yvort", "zvort"] if name == "_ws" else []
                run.load_volumes(wind + vort, t)
                cu, cv = s3["off"]
                u = samp(run.volume("uinterp", t)) - cu
                v = samp(run.volume("vinterp", t)) - cv
                w = samp(run.volume("winterp", t))
                spd = np.sqrt(u * u + v * v + w * w)
                if name == "_speed":
                    val, label = spd, "speed (m/s)"
                else:
                    ox, oy, oz = (samp(run.volume(n, t)) for n in vort)
                    val = (ox * u + oy * v + oz * w) / np.maximum(spd, 1e-6)
                    label = "streamwise vorticity (1/s)"
            else:
                fst = self._field_storm(t)
                val = F.at_points(name, t, samp, storm=fst[0])
                label = F[name].title + (f" · {fst[1]}" if F[name].storm else "")
            res = dict(s=s, v=np.asarray(val, np.float64), z=z, label=label, x0=x[sd - a],
                       y0=y[sd - a], z0=z[sd - a], length=float(s[-1] - s[0]))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["sl"]:
            self._schedule(partial(self._apply_sl, g, res))

    def _apply_sl(self, g, res):
        if g != self.gen["sl"]:
            return
        if isinstance(res, Exception):
            self.sl_info.object = f'<div class="cv-status" style="color:#f87171">{res}</div>'
            return
        self.sl_src.data = dict(s=res["s"], v=res["v"], z=res["z"])
        z0, z1 = float(np.nanmin(res["z"])), float(np.nanmax(res["z"]))
        pad = 0.05 * max(z1 - z0, 0.1)
        self.sl_fig.extra_y_ranges["z"].update(start=max(0.0, z0 - pad), end=z1 + pad)

        def fit(rng, a):
            a = np.asarray(a, dtype=float)
            a = a[np.isfinite(a)]
            lo, hi = (float(a.min()), float(a.max())) if a.size else (0.0, 1.0)
            d = 0.05 * (hi - lo) if hi > lo else (abs(lo) * 0.1 or 1.0)
            rng.update(start=lo - d, end=hi + d, reset_start=lo - d, reset_end=hi + d)
        fit(self.sl_fig.x_range, res["s"])
        fit(self.sl_fig.y_range, res["v"])
        self.sl_fig.yaxis[0].axis_label = res["label"]
        frame = FRAME_SHORT[self._s3["frame"]] if self._s3 else ""
        self.sl_info.object = (
            f'<div class="cv-status" style="line-height:1.35"><b style="color:'
            f'{volume3d.SELECTED}">Streamline</b> ({frame}) · seed ({res["x0"]:.1f}, '
            f'{res["y0"]:.1f}) km, {res["z0"] * 1000:.0f} m<br>{res["length"]:.1f} km long · '
            f'z {z0:.2f}–{z1:.2f} km</div>')
