"""The map: its figure and glyphs, the storm-motion helpers and the map job
(spec, render in the pool, apply to the glyphs, labels).

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import traceback
from functools import partial

import numpy as np
from bokeh.events import PanStart, RangesUpdate, SelectionGeometry, Tap
from bokeh.models import (
    BoxSelectTool, BoxZoomTool, ColorBar, ColumnDataSource, CustomJS, HoverTool,
    LinearColorMapper, PanTool, Range1d, ResetTool, SaveTool, WheelZoomTool,
)
from bokeh.plotting import figure
from bokeh.transform import transform

from .. import pdecomp
from ..core import render, track as trk
from ..core.run import FileBusy, MissingAtTime
from ..core.fields import palette
from ..theme import ACCENT, BG, GRID, MUTED
from .ui import EMPTY_LINES, EMPTY_VEC, KEEP_ASPECT_JS, _cbar_label, _html, style_fig


class MapView:
    def _build_map(self):
        x0, x1, y0, y1 = self.extent
        fig = figure(sizing_mode="stretch_both", min_height=420,
                     x_range=Range1d(x0, x1), y_range=Range1d(y0, y1),
                     tools="", toolbar_location="right",
                     x_axis_label="x (km)", y_axis_label="y (km)")
        style_fig(fig)
        fig.min_border_top = 10
        fig.toolbar.autohide = True
        fig.toolbar_inner = True  # over the plot's edge, clear of the colorbar label
        outline = fig.rect(x=[(x0 + x1) / 2], y=[(y0 + y1) / 2], width=[x1 - x0],
                           height=[y1 - y0], fill_alpha=0, line_color=GRID, line_width=1)
        outline.nonselection_glyph = outline.glyph
        outline.selection_glyph = outline.glyph
        # shade what lies outside the model domain (the view can extend past it)
        far = 1e5
        fig.quad(left=[-far, x1, x0, x0], right=[x0, far, x1, x1],
                 bottom=[-far, -far, -far, y1], top=[far, far, y0, far],
                 fill_color=BG, fill_alpha=0.55, line_color=None)
        # equal x / y scale at every plot size (e.g. when the side panel opens)
        keep = CustomJS(args=dict(fig=fig, ext=list(self.extent)), code=KEEP_ASPECT_JS)
        fig.js_on_change("inner_width", keep)
        fig.js_on_change("inner_height", keep)
        fig.x_range.on_change("reset_end", self._on_resized)
        fig.y_range.on_change("reset_end", self._on_resized)

        self.mapper = LinearColorMapper(palette=palette("reflectivity"), low=0, high=75,
                                        nan_color="#00000000")
        self.img_src = ColumnDataSource(dict(image=[np.full((2, 2), np.nan, np.float32)],
                                             x=[x0], y=[y0], dw=[x1 - x0], dh=[y1 - y0]))
        self.img_r = fig.image(image="image", x="x", y="y", dw="dw", dh="dh",
                               source=self.img_src, color_mapper=self.mapper)
        self.poly_src = ColumnDataSource(dict(xs=[], ys=[], val=[]))
        self.poly_r = fig.multi_polygons(xs="xs", ys="ys", source=self.poly_src,
                                         fill_color=transform("val", self.mapper),
                                         line_color=None, visible=False)
        self.ov_r = []
        for _ in self.ovs:
            ps, ns = ColumnDataSource(dict(EMPTY_LINES)), ColumnDataSource(dict(EMPTY_LINES))
            pr = fig.multi_line("xs", "ys", source=ps, line_color="#ffffff", line_width=1.4)
            nr = fig.multi_line("xs", "ys", source=ns, line_color="#ffffff", line_width=1.4,
                                line_dash="dashed")
            self.ov_r.append((ps, ns, pr, nr))
        self.vec_src = ColumnDataSource(dict(EMPTY_VEC))
        self.vec_seg = fig.segment("x0", "y0", "x1", "y1", source=self.vec_src,
                                   line_color="#e5e7eb", line_width=1.2)
        self.vec_head = fig.scatter("x1", "y1", source=self.vec_src, marker="triangle",
                                    angle="angle", size=6, color="#e5e7eb")
        self.sl2_src = ColumnDataSource(dict(EMPTY_LINES))
        self.sl2_line = fig.multi_line("xs", "ys", source=self.sl2_src, line_color="#e5e7eb",
                                       line_width=1.1)
        self.sl2_head_src = ColumnDataSource(dict(x=[], y=[], angle=[]))
        self.sl2_head = fig.scatter("x", "y", source=self.sl2_head_src, marker="triangle",
                                    angle="angle", size=7, color="#e5e7eb")

        self.box_src = ColumnDataSource(dict(left=[], right=[], bottom=[], top=[]))
        fig.quad(left="left", right="right", bottom="bottom", top="top", source=self.box_src,
                 fill_color=ACCENT, fill_alpha=0.06, line_color=ACCENT, line_dash="dashed",
                 line_width=1.5)
        self.xs_line_src = ColumnDataSource(dict(x=[], y=[]))
        fig.line("x", "y", source=self.xs_line_src, line_color=ACCENT, line_width=2.5)
        self.xs_pt_src = ColumnDataSource(dict(x=[], y=[], label=[]))
        fig.scatter("x", "y", source=self.xs_pt_src, size=9, fill_color=ACCENT,
                    line_color=BG, line_width=1.5)
        fig.text("x", "y", text="label", source=self.xs_pt_src, x_offset=7, y_offset=-7,
                 text_color=ACCENT, text_font_size="12px", text_font_style="bold")
        # meso track: path, fixes (hover for time/value), and the fix at the shown time
        self.trk_line_src = ColumnDataSource(dict(x=[], y=[]))
        fig.line("x", "y", source=self.trk_line_src, line_color="#fbbf24", line_width=2,
                 line_alpha=0.85)
        self.trk_pts_src = ColumnDataSource(dict(x=[], y=[], hms=[], value=[]))
        trk_pts = fig.scatter("x", "y", source=self.trk_pts_src, size=5, color="#fbbf24",
                              line_color=BG, line_width=0.5)
        self.trk_now_src = ColumnDataSource(dict(x=[], y=[]))
        fig.scatter("x", "y", source=self.trk_now_src, marker="circle_cross", size=17,
                    fill_alpha=0, line_color="#fbbf24", line_width=2.5)
        self.trk_hover = HoverTool(renderers=[trk_pts],
                                   tooltips=[("meso", "@hms"), ("value", "@value{0.000}")])
        self.pbox_src = ColumnDataSource(dict(x=[], y=[], w=[], h=[], color=[]))
        fig.rect("x", "y", "w", "h", source=self.pbox_src, fill_color="color",
                 fill_alpha=0.08, line_color="color", line_width=2, line_dash="dashed")
        self.pt_src = ColumnDataSource(dict(x=[], y=[], color=[], label=[]))
        fig.scatter("x", "y", source=self.pt_src, size=13, fill_color="color",
                    line_color=BG, line_width=2)
        fig.text("x", "y", text="label", source=self.pt_src, x_offset=9, y_offset=-9,
                 text_color="color", text_font_size="13px", text_font_style="bold")

        self.cbar = ColorBar(color_mapper=self.mapper, width=12, padding=6,
                             background_fill_color=BG, major_label_text_color=MUTED,
                             major_tick_line_color=None, bar_line_color=None)
        fig.add_layout(self.cbar, "right")
        self.cbar_label = _cbar_label(fig)

        self.pan, self.wz = PanTool(), WheelZoomTool()
        self.bsel = BoxSelectTool(renderers=[outline], dimensions="both")
        hover = HoverTool(renderers=[self.img_r],
                          tooltips=[("x, y", "$x{0.0}, $y{0.0} km"), ("value", "@image{0.000}")])
        fig.add_tools(self.pan, self.wz, BoxZoomTool(match_aspect=True), self.bsel, hover,
                      self.trk_hover, ResetTool(), SaveTool())
        fig.toolbar.active_drag = self.pan
        fig.toolbar.active_scroll = self.wz
        fig.on_event(Tap, self._on_tap)
        fig.on_event(RangesUpdate, self._on_ranges)
        fig.on_event(SelectionGeometry, self._on_select)
        fig.on_event(PanStart, self._on_pan_start)
        self.fig = fig
        self.map_title = _html()

    def _field_storm(self, t):
        """Storm motion for the storm-relative fields (streamwise / crosswise vorticity)
        at time t: the tracked storm's motion where the track has a fix, otherwise the
        domain motion (umove, vmove).  Returns ((u, v), short note, long note)."""
        run = self.run
        if self.fixes:
            m = trk.motion(run, self.fixes).get(t)
            if m is not None and np.all(np.isfinite(m)):
                return (tuple(m), "rel. to tracked motion",
                        f"relative to the tracked storm motion ({m[0]:.1f}, {m[1]:.1f}) m/s")
        why = " (no track fix at this time)" if self.fixes else ""
        return ((run.umove, run.vmove), "rel. to umove/vmove",
                f"relative to the domain motion (umove, vmove) = ({run.umove:g}, "
                f"{run.vmove:g}) m/s{why}")

    def _storm_note(self, names, t):
        """'' or the storm-motion note when any of `names` is storm-relative."""
        if any(n and n in self.F and self.F[n].storm for n in names):
            return self._field_storm(t)
        return None

    def _storm_fields_shown(self):
        names = [self.fill_var.value] + [o["var"].value for o in self.ovs if o["on"].value]
        return any(self.F[n].storm for n in names if n in self.F)

    def _storm_motion(self):
        """Storm motion for storm-relative map vectors (ground-relative m/s)."""
        if self.storm.value == "custom":
            return (self.storm_u.value, self.storm_v.value)
        if self.storm.value == "domain" or not self.results:
            return (self.run.umove, self.run.vmove)
        return tuple(self.results[0][2]["kin"]["storm"])

    def _map_spec(self):
        def lv(mode_w, lvl_w):
            return mode_w.value, float(lvl_w.value)

        fm, fl = lv(self.fill_mode, self.fill_lvl)
        return dict(
            t=self.t, view=self.view, maxpix=self.maxpix, storm=self._storm_motion(),
            fstorm=self._field_storm(self.t)[0],
            fill=dict(var=self.fill_var.value, mode=fm, level=fl, style=self.fill_style.value,
                      cmap=self.fill_cmap.value, rev=self.fill_rev.value,
                      auto=self.fill_auto.value, vmin=self.fill_min.value or 0.0,
                      vmax=self.fill_max.value or 0.0, nlev=self.fill_nlev.value,
                      alpha=self.fill_alpha.value),
            ov=[dict(on=o["on"].value, var=o["var"].value, mode=o["mode"].value,
                     level=float(o["level"].value), levels=o["levels"].value,
                     color=o["color"].value, width=o["width"].value,
                     negdash=o["negdash"].value) for o in self.ovs],
            vec=dict(on=self.vec_on.value, level=self.vec_lvl.value, frame=self.vec_frame.value,
                     style=self.vec_style.value,
                     density=self.vec_density.value, ref=self.vec_ref.value or 20.0,
                     color=self.vec_color.value),
        )

    def request_map(self):
        if self._hold:
            return
        self.gen["map"] += 1
        g, spec = self.gen["map"], self._map_spec()
        self.pools["map"].submit(self._map_job, spec, g)

    def _map_job(self, spec, g):
        if g != self.gen["map"]:
            return
        try:
            if any(pdecomp.is_pdecomp(self.F, n) for n in
                   [spec["fill"]["var"]] + [o["var"] for o in spec["ov"] if o["on"]]):
                pdecomp.source(self.run, spec["t"])  # file version tag, off the page thread
            res = render.compute_map(self.F, spec)
        except (MissingAtTime, FileBusy) as e:  # fields at other times only / being written
            res = e
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["map"]:
            self._schedule(partial(self._apply_map, res, spec, g))

    def _apply_map(self, res, spec, g):
        if g != self.gen["map"]:
            return
        names = [spec["fill"]["var"]] + [o["var"] for o in spec["ov"] if o["on"]]
        self._pd_button(self.pd_btn, names, spec["t"])
        if isinstance(res, Exception):
            if isinstance(res, FileBusy):
                self._set_status(f'<span class="busy">{res}</span>')
            elif isinstance(res, MissingAtTime) and res.name in pdecomp.NAMES:
                self._set_status(f'<span style="color:#fbbf24">{res}.</span>')
            else:
                self._set_status(f'<span style="color:#f87171">Map error: {res}</span>')
            return
        old = self.status.object or ""
        if "Map error" in old or "is not in the output" in old:
            self._set_status("")
        F, run = self.F, self.run
        fill, fs = res.get("fill"), spec["fill"]
        if fill:
            self._last_range = (fill["lo"], fill["hi"])
            self.mapper.update(palette=fill["palette"], low=fill["lo"], high=fill["hi"])
            if fill["style"] == "image":
                self.img_src.data = fill["image"]
                self.poly_src.data = dict(xs=[], ys=[], val=[])
                self.img_r.visible, self.poly_r.visible = True, False
                self.img_r.glyph.global_alpha = fs["alpha"]
            else:
                self.poly_src.data = fill["poly"]
                self.img_r.visible, self.poly_r.visible = False, True
                self.poly_r.glyph.fill_alpha = fs["alpha"]
            note = self._storm_note([fs["var"]], spec["t"])
            self.cbar_label.axis_label = F[fs["var"]].title + (f" · {note[1]}" if note else "")
        for o, ores, (ps, ns, pr, nr) in zip(spec["ov"], res["ov"], self.ov_r):
            if ores is None:
                ps.data, ns.data = dict(EMPTY_LINES), dict(EMPTY_LINES)
                continue
            ps.data, ns.data = ores["pos"], ores["neg"]
            for r in (pr, nr):
                r.glyph.line_color = o["color"]
                r.glyph.line_width = o["width"]
            nr.glyph.line_dash = "dashed" if o["negdash"] else "solid"
        if res["vec"] is not None:
            self.vec_src.data = res["vec"]
            self.vec_seg.glyph.line_color = spec["vec"]["color"]
            self.vec_head.glyph.fill_color = self.vec_head.glyph.line_color = spec["vec"]["color"]
        else:
            self.vec_src.data = dict(EMPTY_VEC)
        if res.get("stream") is not None:
            self.sl2_src.data, self.sl2_head_src.data = res["stream"]
            col = spec["vec"]["color"]
            self.sl2_line.glyph.line_color = col
            self.sl2_head.glyph.fill_color = self.sl2_head.glyph.line_color = col
        else:
            self.sl2_src.data = dict(EMPTY_LINES)
            self.sl2_head_src.data = dict(x=[], y=[], angle=[])

        def lvl_txt(mode, level, name):
            if F[name].ndim == 2:
                return ""
            if mode == "height":
                return f" @ {level:g} km"
            if mode == "level":
                return f" @ k={int(level)} ({run.z[int(level)] * 1000:.0f} m)"
            return " column max" if mode == "colmax" else " column min"

        parts = [f'<b>{F[fs["var"]].label}</b>{lvl_txt(fs["mode"], fs["level"], fs["var"])}']
        for n, o in enumerate(spec["ov"]):
            if o["on"]:
                parts.append(f'<span style="color:{o["color"]}">— {F[o["var"]].label}'
                             f'{lvl_txt(o["mode"], o["level"], o["var"])}</span>')
        self._update_map_labels(spec, lvl_txt)
        note = self._storm_note([fs["var"]] + [o["var"] for o in spec["ov"] if o["on"]],
                                spec["t"])
        if note:
            parts.append(f'<span>storm-relative vorticity {note[2]}</span>')
        if any(pdecomp.is_pdecomp(F, n) for n in names):
            kind, desc = pdecomp.source(run, spec["t"], block=False)
            col = "#fbbf24" if kind == "file-old" else "inherit"
            parts.append(f'<span style="color:{col}">pressure decomposition {desc}</span>')
        stride = res["win"][4]
        parts.append(f'<span>{"full res" if stride == 1 else f"1/{stride} res (zoom for full)"}'
                     f'</span>')
        self.map_title.object = (f'<div class="cv-maptitle">t = {run.time_label(spec["t"])} · '
                                 + " · ".join(parts) + "</div>")

    def _update_map_labels(self, spec, lvl_txt):
        F, d = self.F, self.map_drawer
        for n, o in enumerate(spec["ov"]):
            what = f' · {F[o["var"]].name}{lvl_txt(o["mode"], o["level"], o["var"])}' \
                if o["on"] else ""
            d.label(f"ov{n}", f"Contours {'AB'[n]}{what.replace(' @ ', ' ')}")
        v = spec["vec"]
        d.label("vec", f'Winds · {v["level"]:g} km' if v["on"] else "Winds")
