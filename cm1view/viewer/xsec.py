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
from bokeh.transform import transform

from .. import pdecomp
from ..core import render, vectors
from ..core.run import FileBusy, MissingAtTime
from ..core.fields import CMAPS, palette
from ..theme import ACCENT, BG, MUTED
from .numinput import FloatInput
from .ui import EMPTY_LINES, EMPTY_VEC, _cbar_label, _html, style_fig
from .widgets import _layer_row, _unlist


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
        r = self.xs_img_r = fig.image(image="image", x="x", y="y", dw="dw", dh="dh",
                                      source=self.xs_img, color_mapper=self.xs_mapper)
        self.xs_poly = ColumnDataSource(dict(xs=[], ys=[], val=[]))
        self.xs_poly_r = fig.multi_polygons(xs="xs", ys="ys", source=self.xs_poly,
                                            fill_color=transform("val", self.xs_mapper),
                                            line_color=None, visible=False)
        # more fills, contours and vectors: their glyphs as their rows are added
        self.xs_fill_r, self.xs_ov_r, self.xs_vec_r = [], [], []
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

        F = self.F
        g3 = F.groups(ndim=3)
        self.xs_fill = pn.widgets.Select(groups=g3,
                                         value="dbz" if "dbz" in F else next(iter(F.defs)),
                                         width=220, height=32, margin=(4, 2))
        self.xs_fill_style = pn.widgets.RadioButtonGroup(
            options={"Pixels": "image", "Filled contours": "contourf"}, value="image",
            button_type="primary", button_style="outline", width=230, margin=(5, 10, 8, 10))
        self.xs_cmap = pn.widgets.Select(name="Colormap", options=CMAPS,
                                         value=F[self.xs_fill.value].cmap, width=150)
        self.xs_rev = pn.widgets.Checkbox(name="Reverse", value=False, margin=(5, 10, 14, 10))
        self.xs_auto = pn.widgets.Checkbox(name="Auto range", value=True,
                                           margin=(5, 10, 14, 10))
        self.xs_min = FloatInput(name="Min", value=0.0, width=90, disabled=True)
        self.xs_max = FloatInput(name="Max", value=1.0, width=90, disabled=True)
        self.xs_nlev = pn.widgets.IntSlider(name="Contour intervals", start=4, end=30,
                                            value=15, width=160)
        # more fills, contours and vectors: a row each in their drawers, as on the map
        self.xs_fills, self.xs_ovs, self.xs_vecs = [], [], []
        self.xs_fill_list, self.xs_ov_list, self.xs_vec_list = (
            pn.Column(margin=0, sizing_mode="stretch_width") for _ in range(3))
        add = dict(icon="plus", button_type="primary", button_style="outline", height=32,
                   margin=(6, 4, 8, 4))
        self.xs_fill_add = pn.widgets.Button(name="Add fill", **add)
        self.xs_ov_add = pn.widgets.Button(name="Add contour", **add)
        self.xs_vec_add = pn.widgets.Button(name="Add vectors", **add)
        self.xs_fill_add.on_click(lambda e: self._xs_add_fill())
        self.xs_ov_add.on_click(lambda e: self._xs_add_contour())
        self.xs_vec_add.on_click(lambda e: self._xs_add_vec())
        self._xs_ov_next = [("winterp", "-10, -5, 5, 10, 20, 30") if "winterp" in F
                            else (self.xs_fill.value, "auto"),
                            ("thpert", "-6, -4, -2, -1") if "thpert" in F
                            else (self.xs_fill.value, "auto")]
        self._xs_add_contour(on="winterp" in F)
        self._xs_add_vec()
        self.xs_ztop = pn.widgets.FloatSlider(name="Top (km)", start=1.0,
                                              end=float(np.floor(self.run.z[-1])), step=0.5,
                                              value=min(15.0, float(np.floor(self.run.z[-1]))),
                                              width=150)
        # plot style: axis limits (blank = the whole section), size, fonts, guides
        lim = dict(value=None, placeholder="auto", width=85)
        self.xs_smin = FloatInput(name="From (km)", **lim)
        self.xs_smax = FloatInput(name="To (km)", **lim)
        self.xs_zmin = FloatInput(name="Bottom (km)", **lim)
        self.xs_zmax = FloatInput(name="Top (km)", **lim)
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

    # ---- more fills, contours and vectors (rows as on the map: Widgets, app._wire_*)
    _xs_wired = False  # (Viewer._wire wires the first rows)

    def _xs_place(self, new, after):
        """Put renderers `new` right after renderer `after` in the section plot."""
        fig = self.xs_fig
        rs = [r for r in fig.renderers if r not in new]
        i = rs.index(after) + 1
        fig.renderers = rs[:i] + new + rs[i:]

    def _xs_fill_top(self):
        return self.xs_fill_r[-1]["poly"] if self.xs_fill_r else self.xs_poly_r

    def _xs_ov_top(self):
        return self.xs_ov_r[-1][3] if self.xs_ov_r else self._xs_fill_top()

    def _xs_added(self, o, wire):
        """A row added from the page: wire it and redraw the section."""
        if self._xs_wired:
            wire(o, xs=True)
            self.request_xsec()

    def _xs_add_fill(self):
        """One more fill over the first: its row in More fills, its image / bands and
        colorbar on the section (above the other fills, under the contours)."""
        n = len(self.xs_fills)
        if n >= self.FILL_MAX:
            return
        F = self.F
        var = "winterp" if "winterp" in F else self.xs_fill.value
        o = self._fill_widgets(F.groups(ndim=3), var)
        o["row"] = _layer_row(n, o["on"], o["var"], o["style"], o["cmap"], o["rev"],
                              o["auto"], o["vmin"], o["vmax"], o["alpha"], o["clip"],
                              o["drop"])
        o["drop"].on_click(lambda e: self._xs_drop_fill(o))
        self.xs_fills.append(o)
        self.xs_fill_list.append(o["row"])
        self.xs_fill_add.disabled = n + 1 >= self.FILL_MAX
        fig = self.xs_fig
        mapper = LinearColorMapper(palette=palette("viridis"), low=0, high=1,
                                   nan_color="#00000000")
        src = ColumnDataSource(dict(image=[np.full((2, 2), np.nan, np.float32)],
                                    x=[0], y=[0], dw=[1], dh=[1]))
        poly_src = ColumnDataSource(dict(xs=[], ys=[], val=[]))
        img = fig.image(image="image", x="x", y="y", dw="dw", dh="dh", source=src,
                        color_mapper=mapper)
        poly = fig.multi_polygons(xs="xs", ys="ys", source=poly_src,
                                  fill_color=transform("val", mapper), line_color=None,
                                  visible=False)
        self._xs_place([img, poly], self._xs_fill_top())
        cbar = ColorBar(color_mapper=mapper, width=12, padding=6, title="", visible=False,
                        title_text_color=MUTED, title_text_font_size="11px",
                        title_text_font_style="normal", background_fill_color=BG,
                        major_label_text_color=MUTED, major_tick_line_color=None,
                        bar_line_color=None)
        fig.add_layout(cbar, "right")
        self.xs_fill_r.append(dict(mapper=mapper, src=src, poly_src=poly_src, img=img,
                                   poly=poly, cbar=cbar))
        self._xs_added(o, self._wire_fill)

    def _xs_drop_fill(self, o):
        i = self.xs_fills.index(o)
        self.xs_fills.pop(i)
        _unlist(self.xs_fill_list, self.xs_fills, o)
        self.xs_fill_add.disabled = False
        g = self.xs_fill_r.pop(i)
        fig = self.xs_fig
        fig.renderers = [r for r in fig.renderers if r is not g["img"] and r is not g["poly"]]
        fig.right = [x for x in fig.right if x is not g["cbar"]]
        self.request_xsec()

    def _xs_add_contour(self, on=True):
        """One more contour layer: its row in Contours, its lines on the section."""
        n = len(self.xs_ovs)
        if n >= self.OV_MAX:
            return
        var, levels = (self._xs_ov_next[n] if n < len(self._xs_ov_next)
                       else (self.xs_fill.value, "auto"))
        o = self._contour_widgets(self.xs_ovs, self.F.groups(ndim=3), var, levels)
        o["on"].value = on
        o["row"] = _layer_row(n, o["on"], o["var"], o["levels"], o["color"], o["width"],
                              o["negdash"], o["drop"])
        o["drop"].on_click(lambda e: self._xs_drop_contour(o))
        self.xs_ovs.append(o)
        self.xs_ov_list.append(o["row"])
        self.xs_ov_add.disabled = n + 1 >= self.OV_MAX
        fig = self.xs_fig
        ps, ns = ColumnDataSource(dict(EMPTY_LINES)), ColumnDataSource(dict(EMPTY_LINES))
        pr = fig.multi_line("xs", "ys", source=ps, line_color="#ffffff", line_width=1.4)
        nr = fig.multi_line("xs", "ys", source=ns, line_color="#ffffff", line_width=1.4,
                            line_dash="dashed")
        self._xs_place([pr, nr], self._xs_ov_top())
        self.xs_ov_r.append((ps, ns, pr, nr))
        self._xs_added(o, self._wire_overlay)

    def _xs_drop_contour(self, o):
        i = self.xs_ovs.index(o)
        self.xs_ovs.pop(i)
        _unlist(self.xs_ov_list, self.xs_ovs, o)
        self.xs_ov_add.disabled = False
        _, _, pr, nr = self.xs_ov_r.pop(i)
        self.xs_fig.renderers = [r for r in self.xs_fig.renderers
                                 if r is not pr and r is not nr]
        self.request_xsec()

    def _xs_add_vec(self):
        """One more vector layer: its row in Vectors, its arrows on the section (the
        along-section and vertical components)."""
        n = len(self.xs_vecs)
        if n >= self.VEC_MAX:
            return
        o = self._vec_row(self.xs_vecs, self.VEC_COLORS, True, 0.0, 28, (8, 60),
                          styles=False)
        del o["level"]  # (a section has every height)
        o["row"] = _layer_row(n, o["on"], o["q"], o["frame"], o["density"], o["ref"],
                              o["color"], o["drop"])
        o["drop"].on_click(lambda e: self._xs_drop_vec(o))
        self.xs_vecs.append(o)
        self.xs_vec_list.append(o["row"])
        self.xs_vec_add.disabled = n + 1 >= self.VEC_MAX
        fig = self.xs_fig
        src = ColumnDataSource(dict(EMPTY_VEC))
        seg = fig.segment("x0", "y0", "x1", "y1", source=src, line_color="#e5e7eb",
                          line_width=1.1)
        head = fig.scatter("x1", "y1", source=src, marker="triangle", angle="angle", size=5,
                           color="#e5e7eb")
        prev = self.xs_vec_r[-1]["head"] if self.xs_vec_r else self._xs_ov_top()
        self._xs_place([seg, head], prev)
        self.xs_vec_r.append(dict(src=src, seg=seg, head=head))
        self._xs_added(o, self._wire_vec)

    def _xs_drop_vec(self, o):
        i = self.xs_vecs.index(o)
        self.xs_vecs.pop(i)
        _unlist(self.xs_vec_list, self.xs_vecs, o)
        self.xs_vec_add.disabled = False
        g = self.xs_vec_r.pop(i)
        self.xs_fig.renderers = [r for r in self.xs_fig.renderers
                                 if r is not g["seg"] and r is not g["head"]]
        self.request_xsec()

    def _xs_names(self, spec=None):
        """The fields the section draws (of its spec, or of the widgets)."""
        if spec is not None:
            return [spec["fill"]] + [o["var"] for o in spec["fills"] + spec["ov"] if o["on"]]
        return [self.xs_fill.value] + [o["var"].value for o in self.xs_fills + self.xs_ovs
                                       if o["on"].value]

    def request_xsec(self):
        if len(self.xs_pts) != 2 or self._hold_xs:
            return
        self.gen["xs"] += 1
        g = self.gen["xs"]
        spec = self.xs_spec()
        self.xs_status.object = '<div class="cv-status"><span class="busy">● Computing ' \
                                'cross-section…</span></div>'
        self.pools["xs"].submit(self._xs_job, spec, g)

    def xs_spec(self):
        """What the section draws, from its widgets (also the Figure workspace's
        'figure from this section')."""
        try:  # synced from the browser once the figure has been drawn
            w, h = self.xs_fig.inner_width or 800, self.xs_fig.inner_height or 360
        except Exception:  # noqa: BLE001
            w, h = 800, 360
        spec = dict(t=self.t, A=self.xs_pts[0], B=self.xs_pts[1], fill=self.xs_fill.value,
                    ztop=float(self.xs_ztop.value), px=(w, h), storm=self._storm_motion(),
                    style=self.xs_fill_style.value, nlev=int(self.xs_nlev.value),
                    cmap=self.xs_cmap.value, rev=self.xs_rev.value, auto=self.xs_auto.value,
                    vmin=self.xs_min.value or 0.0, vmax=self.xs_max.value or 0.0,
                    fills=[dict(on=o["on"].value, var=o["var"].value, style=o["style"].value,
                                cmap=o["cmap"].value, rev=o["rev"].value,
                                auto=o["auto"].value, vmin=o["vmin"].value or 0.0,
                                vmax=o["vmax"].value or 0.0, nlev=15, alpha=o["alpha"].value,
                                clip=o["clip"].value) for o in self.xs_fills],
                    ov=[dict(on=o["on"].value, var=o["var"].value, levels=o["levels"].value,
                             color=o["color"].value, width=o["width"].value,
                             negdash=o["negdash"].value) for o in self.xs_ovs],
                    vecs=[dict(on=o["on"].value, q=o["q"].value, frame=o["frame"].value,
                               density=int(o["density"].value),
                               ref=o["ref"].value or vectors.VECTORS[o["q"].value].ref,
                               color=o["color"].value) for o in self.xs_vecs],
                    fstorm=self._field_storm(self.t)[0])
        spec["fnote"] = self._storm_note(self._xs_names(spec), self.t)
        return spec

    def _xs_job(self, spec, g):
        if g != self.gen["xs"]:
            return
        run, F, t = self.run, self.F, spec["t"]
        try:
            names = []
            for n in self._xs_names(spec):
                names += F.native_deps(n)
            for o in spec["vecs"]:
                if o["on"]:
                    names += vectors.deps(F, o["q"])

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

            def sample(name):
                return render.sample_section(run, F.volume(name, t, spec["fstorm"]),
                                             fi, fj, zq)

            def fill(name, f):
                a = sample(name)
                lo, hi = F.auto_range(name, a) if f["auto"] else (f["vmin"], f["vmax"])
                return render.fill_bands(s, zq, a, lo, max(hi, lo + 1e-6), f)

            out = dict(s=s, zq=zq, fill=fill(spec["fill"], spec))
            # more fills drawn over the first; clip: clear outside their range
            out["fills"] = [fill(f["var"], f) if f["on"] else None for f in spec["fills"]]
            out["ov"] = []
            for o in spec["ov"]:
                if not o["on"]:
                    out["ov"].append(None)
                    continue
                c = sample(o["var"])
                lv = render.parse_levels(o["levels"], *F.auto_range(o["var"], c))
                out["ov"].append(dict(pos=render.contour_lines(s, zq, c, lv[lv >= 0]),
                                      neg=render.contour_lines(s, zq, c, lv[lv < 0])))
            W, H = spec["px"]
            aspect = (W * spec["ztop"]) / (max(s[-1], 1e-6) * H)
            out["vecs"] = []
            for o in spec["vecs"]:
                if not o["on"]:
                    out["vecs"].append(None)
                    continue
                # in the plane: the along-section and vertical components
                u, v, w = (np.zeros((zq.size, s.size), np.float32) if a is None else
                           render.sample_section(run, a, fi, fj, zq)
                           for a in vectors.volumes(F, o["q"], t))
                if vectors.VECTORS[o["q"]].framed:
                    u, v = vectors.to_frame(run, u, v, o["frame"], spec["storm"])
                out["vecs"].append(render.section_vectors(
                    s, zq, u * ex + v * ey, w, n_across=o["density"], aspect=aspect,
                    ref_speed=o["ref"]))
            if any(pdecomp.is_pdecomp(F, n) for n in self._xs_names(spec)):
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
        names = self._xs_names(spec)
        self._pd_button(self.xs_pd_btn, names, spec["t"])
        if isinstance(res, Exception):
            self.xs_status.object = f'<div class="cv-status" style="color:#f87171">{res}</div>'
            return
        F = self.F
        d = F[spec["fill"]]
        s, zq, fill = res["s"], res["zq"], res["fill"]
        self._xs_range = (fill["lo"], fill["hi"])
        self.xs_mapper.update(palette=fill["palette"], low=fill["lo"], high=fill["hi"])
        image = fill["style"] == "image"
        if image:
            self.xs_img.data = fill["image"]
        else:
            self.xs_poly.data = fill["poly"]
        self.xs_img_r.visible, self.xs_poly_r.visible = image, not image
        for f, fres, r in zip(spec["fills"], res["fills"], self.xs_fill_r):
            r["cbar"].visible = fres is not None
            if fres is None:
                r["img"].visible = r["poly"].visible = False
                continue
            r["mapper"].update(palette=fres["palette"], low=fres["lo"], high=fres["hi"])
            r["cbar"].title = F[f["var"]].name
            image = fres["style"] == "image"
            if image:
                r["src"].data = fres["image"]
                r["img"].glyph.global_alpha = f["alpha"]
            else:
                r["poly_src"].data = fres["poly"]
                r["poly"].glyph.fill_alpha = f["alpha"]
            r["img"].visible, r["poly"].visible = image, not image
        for o, f, fres in zip(self.xs_fills, spec["fills"], res["fills"]):
            if fres is not None and o["var"].value == f["var"]:
                o["last"] = (fres["lo"], fres["hi"])  # (Auto range off starts from it)
        for o, ores, (ps, ns, pr, nr) in zip(spec["ov"], res["ov"], self.xs_ov_r):
            ps.data, ns.data = (ores["pos"], ores["neg"]) if ores else \
                (dict(EMPTY_LINES), dict(EMPTY_LINES))
            for r in (pr, nr):
                r.glyph.line_color, r.glyph.line_width = o["color"], o["width"]
            nr.glyph.line_dash = "dashed" if o["negdash"] else "solid"
        for o, vres, r in zip(spec["vecs"], res["vecs"], self.xs_vec_r):
            r["src"].data = vres or dict(EMPTY_VEC)
            r["seg"].glyph.line_color = o["color"]
            r["head"].glyph.fill_color = r["head"].glyph.line_color = o["color"]
        self._xs_extent = (float(s[-1]), float(zq[-1]))
        self._xs_limits()
        self.xs_lab[1].x = float(s[-1])
        self._xs_look()
        self.xs_cbar_label.axis_label = d.title + (
            f' · {spec["fnote"][1]}' if spec["fnote"] and d.storm else "")
        self._xs_labels(spec)
        (xa, ya), (xb, yb) = spec["A"], spec["B"]
        parts = [f'<b>{d.label}</b>']
        parts += [f'+ <b>{F[f["var"]].label}</b>' for f in spec["fills"] if f["on"]]
        parts += [f'<span style="color:{o["color"]}">— {F[o["var"]].label}</span>'
                  for o in spec["ov"] if o["on"]]
        self.xs_status.object = (
            f'<div class="cv-maptitle">t = {self.run.time_label(spec["t"])} · '
            + " · ".join(parts)
            + f' · A ({xa:.1f}, {ya:.1f}) → B ({xb:.1f}, {yb:.1f}) km, {s[-1]:.1f} km long'
            + (f' · storm-relative vorticity {spec["fnote"][2]}' if spec["fnote"] else "")
            + (f' · pressure decomposition '
               f'{pdecomp.source(self.run, spec["t"], block=False)[1]}'
               if any(pdecomp.is_pdecomp(F, n) for n in names) else "")
            + '</div>')

    def _xs_labels(self, spec):
        """The drawer pills say what is on: one layer's field, or how many."""
        F, d = self.F, self.xs_drawer
        for key, name, on in (("fills", "More fills", [o for o in spec["fills"] if o["on"]]),
                              ("ov", "Contours", [o for o in spec["ov"] if o["on"]])):
            d.label(key, f'{name} · {F[on[0]["var"]].name}' if len(on) == 1 else
                    f"{name} · {len(on)}" if on else name)
        on = [o for o in spec["vecs"] if o["on"]]
        d.label("vec", f'Vectors · {vectors.VECTORS[on[0]["q"]].label}' if len(on) == 1 else
                f"Vectors · {len(on)}" if on else "Vectors")

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
