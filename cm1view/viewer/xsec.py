"""Vertical cross-sections: the panel, the A-B line on the map and the section job.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import traceback
from functools import partial

import numpy as np
import panel as pn
from bokeh.models import (
    ColorBar, ColumnDataSource, HoverTool, Label, LinearColorMapper, Range1d,
)
from bokeh.plotting import figure

from .. import pdecomp
from ..core import render
from ..core.run import FileBusy, MissingAtTime
from ..core.fields import CMAPS, palette
from ..theme import ACCENT, BG, MUTED
from .ui import EMPTY_LINES, EMPTY_VEC, FRAMES, _cbar_label, _html, style_fig


class SectionPanel:
    _hold_xs = False

    def _build_xsec(self):
        # zoom and pan stay inside the sampled data (range bounds, set with the data)
        fig = figure(sizing_mode="stretch_width", height=430,
                     tools="box_zoom,wheel_zoom,pan,reset,save", active_drag="box_zoom",
                     toolbar_location="above", x_axis_label="Distance from A toward B (km)",
                     y_axis_label="Height (km AGL)", x_range=Range1d(0, 1),
                     y_range=Range1d(0, 15))
        style_fig(fig)
        self.xs_mapper = LinearColorMapper(palette=palette("reflectivity"), low=0, high=75,
                                           nan_color="#00000000")
        self.xs_img = ColumnDataSource(dict(image=[np.full((2, 2), np.nan, np.float32)],
                                            x=[0], y=[0], dw=[1], dh=[1]))
        r = fig.image(image="image", x="x", y="y", dw="dw", dh="dh", source=self.xs_img,
                      color_mapper=self.xs_mapper)
        self.xs_pos = ColumnDataSource(dict(EMPTY_LINES))
        self.xs_neg = ColumnDataSource(dict(EMPTY_LINES))
        self.xs_pos_r = fig.multi_line("xs", "ys", source=self.xs_pos, line_color="#ffffff",
                                       line_width=1.3)
        self.xs_neg_r = fig.multi_line("xs", "ys", source=self.xs_neg, line_color="#ffffff",
                                       line_width=1.3, line_dash="dashed")
        self.xs_vec = ColumnDataSource(dict(EMPTY_VEC))
        self.xs_vseg = fig.segment("x0", "y0", "x1", "y1", source=self.xs_vec,
                                   line_color="#e5e7eb", line_width=1.1)
        self.xs_vhead = fig.scatter("x1", "y1", source=self.xs_vec, marker="triangle",
                                    angle="angle", size=5, color="#e5e7eb")
        # A and B, as on the map, at the two ends of the distance axis
        lab = dict(y=0, x_units="data", y_units="data", y_offset=5, text_color=ACCENT,
                   text_font_size="14px", text_font_style="bold", text_baseline="bottom",
                   background_fill_color=BG, background_fill_alpha=0.75, padding=3,
                   border_radius=3, visible=False)
        self.xs_lab = (Label(x=0, text="A", x_offset=5, text_align="left", **lab),
                       Label(x=1, text="B", x_offset=-5, text_align="right", **lab))
        for a in self.xs_lab:
            fig.add_layout(a)
        self.xs_cbar = ColorBar(color_mapper=self.xs_mapper, width=12, padding=6,
                                background_fill_color=BG, major_label_text_color=MUTED,
                                major_tick_line_color=None, bar_line_color=None)
        fig.add_layout(self.xs_cbar, "right")
        self.xs_cbar_label = _cbar_label(fig)
        fig.add_tools(HoverTool(renderers=[r], tooltips=[("s, z", "$x{0.0} km, $y{0.00} km"),
                                                          ("value", "@image{0.000}")]))
        self.xs_fig = fig

        g3 = self.F.groups(ndim=3)
        none = {"(none)": {"None": ""}}
        F = self.F
        self.xs_fill = pn.widgets.Select(name="Fill", groups=g3,
                                         value="dbz" if "dbz" in F else next(iter(F.defs)),
                                         width=230)
        self.xs_cont = pn.widgets.Select(name="Contours", groups={**none, **g3},
                                         value="winterp" if "winterp" in F else "",
                                         width=230)
        self.xs_levels = pn.widgets.TextInput(name="Contour levels",
                                              value="-10, -5, 5, 10, 20, 30", width=180)
        self.xs_vecs = pn.widgets.Checkbox(value=True, width=18, margin=(14, 0, 0, 8))
        self.xs_cmap = pn.widgets.Select(name="Colormap", options=CMAPS,
                                         value=F[self.xs_fill.value].cmap, width=150)
        self.xs_rev = pn.widgets.Checkbox(name="Reverse", value=False, margin=(5, 10, 14, 10))
        self.xs_auto = pn.widgets.Checkbox(name="Auto range", value=True,
                                           margin=(5, 10, 14, 10))
        self.xs_min = pn.widgets.FloatInput(name="Min", value=0.0, width=90, disabled=True)
        self.xs_max = pn.widgets.FloatInput(name="Max", value=1.0, width=90, disabled=True)
        self.xs_ccolor = pn.widgets.ColorPicker(name="Color", value="#ffffff", width=60)
        self.xs_cwidth = pn.widgets.FloatSlider(name="Line width", start=0.5, end=4,
                                                step=0.25, value=1.3, width=130)
        self.xs_negdash = pn.widgets.Checkbox(name="Dash negative", value=True,
                                              margin=(5, 10, 14, 10))
        self.xs_vframe = pn.widgets.Select(name="Frame", options=FRAMES,
                                           value=self.vec_frame.value, width=150)
        self.xs_vdensity = pn.widgets.IntSlider(name="Arrows across", start=8, end=60,
                                                value=28, width=150)
        self.xs_vref = pn.widgets.FloatInput(name="Ref. speed (m/s)", value=20.0, width=110)
        self.xs_vcolor = pn.widgets.ColorPicker(name="Color", value="#e5e7eb", width=60)
        self.xs_ztop = pn.widgets.FloatSlider(name="Top (km)", start=1.0,
                                              end=float(np.floor(self.run.z[-1])), step=0.5,
                                              value=min(15.0, float(np.floor(self.run.z[-1]))),
                                              width=150)
        # plot style: axis limits (blank = the whole section), size, fonts, guides
        lim = dict(value=None, placeholder="auto", width=85)
        self.xs_smin = pn.widgets.FloatInput(name="From (km)", **lim)
        self.xs_smax = pn.widgets.FloatInput(name="To (km)", **lim)
        self.xs_zmin = pn.widgets.FloatInput(name="Bottom (km)", **lim)
        self.xs_zmax = pn.widgets.FloatInput(name="Top (km)", **lim)
        self.xs_height = pn.widgets.IntSlider(name="Plot height (px)", start=250, end=900,
                                              step=10, value=430, width=150)
        self.xs_font = pn.widgets.IntSlider(name="Font size", start=8, end=20, value=12,
                                            width=120)
        self.xs_grid = pn.widgets.Checkbox(name="Grid lines", value=True,
                                           margin=(5, 10, 14, 10))
        self.xs_ab = pn.widgets.Checkbox(name="A / B labels", value=True,
                                         margin=(5, 10, 14, 10))
        self.xs_style_reset = pn.widgets.Button(name="Default style", button_type="light",
                                                button_style="outline", height=32,
                                                margin=(5, 4, 14, 4))
        self._xs_view = None  # (section length, top, limits) the plot's ranges were set for
        self.xs_status = _html('<div class="cv-empty">Click two points on the map, A then B '
                               '(the <b>Section</b> tool is on while this panel is open).'
                               '</div>')

    def _draw_xs(self):
        pts = self.xs_pts
        self.xs_pt_src.data = dict(x=[p[0] for p in pts], y=[p[1] for p in pts],
                                   label=["A", "B"][:len(pts)])
        self.xs_line_src.data = dict(x=[p[0] for p in pts], y=[p[1] for p in pts]) \
            if len(pts) == 2 else dict(x=[], y=[])
        self._update_items()

    def request_xsec(self):
        if len(self.xs_pts) != 2 or self._hold_xs:
            return
        self.gen["xs"] += 1
        g = self.gen["xs"]
        try:  # synced from the browser once the figure has been drawn
            w, h = self.xs_fig.inner_width or 800, self.xs_fig.inner_height or 360
        except Exception:  # noqa: BLE001
            w, h = 800, 360
        spec = dict(t=self.t, A=self.xs_pts[0], B=self.xs_pts[1], fill=self.xs_fill.value,
                    cont=self.xs_cont.value, levels=self.xs_levels.value,
                    vec=self.xs_vecs.value, ztop=float(self.xs_ztop.value), px=(w, h),
                    frame=self.xs_vframe.value, storm=self._storm_motion(),
                    cmap=self.xs_cmap.value, rev=self.xs_rev.value, auto=self.xs_auto.value,
                    vmin=self.xs_min.value or 0.0, vmax=self.xs_max.value or 0.0,
                    ccolor=self.xs_ccolor.value, cwidth=float(self.xs_cwidth.value),
                    negdash=self.xs_negdash.value, density=int(self.xs_vdensity.value),
                    ref=float(self.xs_vref.value or 20.0), vcolor=self.xs_vcolor.value,
                    fstorm=self._field_storm(self.t)[0],
                    fnote=self._storm_note([self.xs_fill.value, self.xs_cont.value], self.t))
        self.xs_status.object = '<div class="cv-status"><span class="busy">● Computing ' \
                                'cross-section…</span></div>'
        self.pools["xs"].submit(self._xs_job, spec, g)

    def _xs_job(self, spec, g):
        if g != self.gen["xs"]:
            return
        run, F, t = self.run, self.F, spec["t"]
        try:
            names = F.native_deps(spec["fill"])
            if spec["cont"]:
                names += F.native_deps(spec["cont"])
            if spec["vec"]:
                names += ["uinterp", "vinterp", "winterp"]

            def prog(done, total, name):
                if total:
                    self._schedule(partial(
                        setattr, self.xs_status, "object",
                        f'<div class="cv-status"><span class="busy">● Loading 3D fields '
                        f'({done}/{total}) {name}…</span></div>'))

            if not run.load_volumes(names, t, progress=prog,
                                    cancelled=lambda: g != self.gen["xs"]):
                return
            s, fi, fj, (ex, ey) = render.section_coords(run, spec["A"], spec["B"])
            zq = np.linspace(0.0, spec["ztop"], max(120, int(spec["ztop"] / 0.04)))
            fill = render.sample_section(run, F.volume(spec["fill"], t, spec["fstorm"]),
                                         fi, fj, zq)
            lo, hi = F.auto_range(spec["fill"], fill) if spec["auto"] else \
                (spec["vmin"], spec["vmax"])
            if hi <= lo:
                hi = lo + 1e-6
            out = dict(s=s, zq=zq, fill=fill, lo=lo, hi=hi)
            if spec["cont"]:
                c = render.sample_section(run, F.volume(spec["cont"], t, spec["fstorm"]),
                                          fi, fj, zq)
                clo, chi = F.auto_range(spec["cont"], c)
                lv = render.parse_levels(spec["levels"], clo, chi)
                out["pos"] = render.contour_lines(s, zq, c, lv[lv >= 0])
                out["neg"] = render.contour_lines(s, zq, c, lv[lv < 0])
            if spec["vec"]:
                u = render.sample_section(run, run.volume("uinterp", t), fi, fj, zq)
                v = render.sample_section(run, run.volume("vinterp", t), fi, fj, zq)
                w = render.sample_section(run, run.volume("winterp", t), fi, fj, zq)
                if spec["frame"] == "ground":
                    u, v = u + run.umove, v + run.vmove
                elif spec["frame"] == "storm":
                    u, v = u + run.umove - spec["storm"][0], v + run.vmove - spec["storm"][1]
                upar = u * ex + v * ey
                W, H = spec["px"]
                aspect = (W * spec["ztop"]) / (max(s[-1], 1e-6) * H)
                out["vec"] = render.section_vectors(s, zq, upar, w, n_across=spec["density"],
                                                    aspect=aspect, ref_speed=spec["ref"])
            if any(pdecomp.is_pdecomp(F, n) for n in (spec["fill"], spec["cont"])):
                pdecomp.source(run, t)  # file version tag, off the page thread
            res = out
        except (MissingAtTime, FileBusy) as e:  # expected: no traceback
            res = e
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["xs"]:
            self._schedule(partial(self._apply_xs, res, spec, g))

    def _apply_xs(self, res, spec, g):
        if g != self.gen["xs"]:
            return
        self._pd_button(self.xs_pd_btn, [spec["fill"], spec["cont"]], spec["t"])
        if isinstance(res, Exception):
            self.xs_status.object = f'<div class="cv-status" style="color:#f87171">{res}</div>'
            return
        F = self.F
        d = F[spec["fill"]]
        s, zq = res["s"], res["zq"]
        self._xs_range = (res["lo"], res["hi"])
        self.xs_mapper.update(palette=palette(spec["cmap"], 256, spec["rev"]), low=res["lo"],
                              high=res["hi"])
        for r in (self.xs_pos_r, self.xs_neg_r):
            r.glyph.line_color, r.glyph.line_width = spec["ccolor"], spec["cwidth"]
        self.xs_neg_r.glyph.line_dash = "dashed" if spec["negdash"] else "solid"
        self.xs_vseg.glyph.line_color = spec["vcolor"]
        self.xs_vhead.glyph.fill_color = self.xs_vhead.glyph.line_color = spec["vcolor"]
        self.xs_img.data = render.image_data(s, zq, res["fill"])
        self.xs_pos.data = res.get("pos", dict(EMPTY_LINES))
        self.xs_neg.data = res.get("neg", dict(EMPTY_LINES))
        self.xs_vec.data = res.get("vec", dict(EMPTY_VEC))
        self._xs_extent = (float(s[-1]), float(zq[-1]))
        self._xs_limits()
        self.xs_lab[1].x = float(s[-1])
        self._xs_look()
        self.xs_cbar_label.axis_label = d.title + (
            f' · {spec["fnote"][1]}' if spec["fnote"] and d.storm else "")
        (xa, ya), (xb, yb) = spec["A"], spec["B"]
        cont = f' · contours: {F[spec["cont"]].label}' if spec["cont"] else ""
        self.xs_status.object = (
            f'<div class="cv-maptitle">t = {self.run.time_label(spec["t"])} · '
            f'<b>{d.label}</b>{cont} · A ({xa:.1f}, {ya:.1f}) → B ({xb:.1f}, {yb:.1f}) km, '
            f'{s[-1]:.1f} km long'
            + (f' · storm-relative vorticity {spec["fnote"][2]}' if spec["fnote"] else "")
            + (f' · pressure decomposition '
               f'{pdecomp.source(self.run, spec["t"], block=False)[1]}'
               if any(pdecomp.is_pdecomp(F, n) for n in (spec["fill"], spec["cont"])) else "")
            + '</div>')

    _xs_extent = None  # (length, top) of the section shown (km)

    def _xs_limits(self, *e, force=False):
        """Axis ranges from the From/To/Bottom/Top limits (blank: the whole section).  A
        new section (length or top) or new limits reset the view; otherwise a zoom is
        kept.  The reset tool goes back to the limits; zoom and pan stay inside the data."""
        if self._xs_extent is None:
            return
        L, top = self._xs_extent

        def val(w, default, hi):
            v = w.value
            return default if v is None else float(min(max(v, 0.0), hi))

        s0, s1 = val(self.xs_smin, 0.0, L), val(self.xs_smax, L, L)
        z0, z1 = val(self.xs_zmin, 0.0, top), val(self.xs_zmax, top, top)
        if s1 <= s0:
            s0, s1 = 0.0, L
        if z1 <= z0:
            z0, z1 = 0.0, top
        view = (L, top, s0, s1, z0, z1)
        if view == self._xs_view and not force:
            return
        self._xs_view = view
        self.xs_fig.x_range.update(start=s0, end=s1, reset_start=s0, reset_end=s1,
                                   bounds=(0.0, L))
        self.xs_fig.y_range.update(start=z0, end=z1, reset_start=z0, reset_end=z1,
                                   bounds=(0.0, top))
        for a in self.xs_lab:  # A and B sit on the bottom axis of the limits
            a.y = z0

    def _xs_look(self, *e):
        """Plot height, fonts, grid lines and the A / B labels (no new section needed)."""
        fig, fs = self.xs_fig, int(self.xs_font.value)
        fig.height = int(self.xs_height.value)
        for ax in fig.axis:
            ax.major_label_text_font_size = f"{max(fs - 1, 6)}px"
            if ax is not self.xs_cbar_label:
                ax.axis_label_text_font_size = f"{fs}px"
        self.xs_cbar_label.axis_label_text_font_size = f"{fs}px"
        self.xs_cbar.major_label_text_font_size = f"{max(fs - 1, 6)}px"
        fig.grid.visible = self.xs_grid.value
        for a in self.xs_lab:
            a.text_font_size = f"{fs + 2}px"
            a.visible = self.xs_ab.value and self._xs_extent is not None

    def _on_xs_style_reset(self, ev):
        for w in (self.xs_smin, self.xs_smax, self.xs_zmin, self.xs_zmax):
            w.value = None
        self.xs_height.value, self.xs_font.value = 430, 12
        self.xs_grid.value = self.xs_ab.value = True
        self._xs_limits(force=True)
