"""The map on the Earth (runs with a map projection, Run.geo: WoFS / WRF): boundary
lines (coastlines, countries, states, lakes, US counties), lat/lon lines with
labels, and lat/lon in the map's hover.  Idealized runs (CM1) have none of it: no
widgets, no glyphs, no Boundaries pill.

The lines are worked out once (core/geo.py, projected into the grid's km) and
drawn in the browser; showing, hiding or restyling them never redraws the map.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import numpy as np
import panel as pn
from bokeh.models import ColumnDataSource, CustomJS, CustomJSHover, Range1d
from bokeh.plotting import figure

from ..core import geo as G

from ..figures.draw.layers import BOUNDARY_LOOK as GEO_LOOK  # (figures draw them alike)

GEO_ON = list(G.SHOWN)  # shown at first
GEO_COLOR = "#cbd5e1"
# the session's "boundaries" entry: key -> Viewer attribute
GEO_KEYS = (("kinds", "geo_kinds"), ("color", "geo_color"), ("width", "geo_width"),
            ("grid", "geo_grid"), ("step", "geo_step"), ("inset", "geo_inset"))

# lat, lon of the hovered x, y: bilinear in a table of the projection over the domain
# (the formatter of every "$x": "$x{lonlat}" gives lat, lon, any other format x)
LONLAT_JS = """
if (format !== "lonlat") return value.toFixed(1);
const n = t.n, fx = (special_vars.x - t.x0) / (t.x1 - t.x0) * (n - 1),
      fy = (special_vars.y - t.y0) / (t.y1 - t.y0) * (n - 1);
if (!(fx >= 0 && fx <= n - 1 && fy >= 0 && fy <= n - 1)) return "";
const i = Math.min(Math.floor(fx), n - 2), j = Math.min(Math.floor(fy), n - 2),
      a = fx - i, b = fy - j;
const g = (v) => (1 - a) * (1 - b) * v[j * n + i] + a * (1 - b) * v[j * n + i + 1]
               + (1 - a) * b * v[(j + 1) * n + i] + a * b * v[(j + 1) * n + i + 1];
const lat = g(t.lat), lon = ((g(t.lon) + 540) % 360) - 180;
return Math.abs(lat).toFixed(3) + "° " + (lat >= 0 ? "N" : "S") + ", "
     + Math.abs(lon).toFixed(3) + "° " + (lon >= 0 ? "E" : "W");
"""

# the inset's box round the map's view: its corners through the lat/lon table (clamped
# to the domain), into the inset's x = (lon - clon) cos(clat), y = lat
INSET_JS = """
const n = t.n, xs = [], ys = [];
const ll = (x, y) => {
  const fx = Math.min(Math.max((x - t.x0) / (t.x1 - t.x0), 0), 1) * (n - 1),
        fy = Math.min(Math.max((y - t.y0) / (t.y1 - t.y0), 0), 1) * (n - 1);
  const i = Math.min(Math.floor(fx), n - 2), j = Math.min(Math.floor(fy), n - 2),
        a = fx - i, b = fy - j;
  const g = (v) => (1 - a) * (1 - b) * v[j * n + i] + a * (1 - b) * v[j * n + i + 1]
                 + (1 - a) * b * v[(j + 1) * n + i] + a * b * v[(j + 1) * n + i + 1];
  xs.push((g(t.lon) - c[0]) * c[1]); ys.push(g(t.lat));
};
const x0 = xr.start, x1 = xr.end, y0 = yr.start, y1 = yr.end, m = 8;
for (let k = 0; k <= m; k++) ll(x0 + (x1 - x0) * k / m, y0);
for (let k = 0; k <= m; k++) ll(x1, y0 + (y1 - y0) * k / m);
for (let k = 0; k <= m; k++) ll(x1 - (x1 - x0) * k / m, y1);
for (let k = 0; k <= m; k++) ll(x0, y1 - (y1 - y0) * k / m);
src.data = {x: xs, y: ys};
"""
INSET_KINDS = ("coastlines", "countries", "states", "lakes")


class MapLines:
    geo = None  # the run's Geo (None: an idealized run, nothing here is built)
    inset = None  # the locator map (a Bokeh pane floated over the map)

    def _build_geo(self, fig, hover):
        """Widgets and glyphs for the map on the Earth (nothing without Run.geo):
        drawn above the data layers, under the markers."""
        self.geo = getattr(self.run, "geo", None)
        if self.geo is None:
            return
        self.geo_kinds = pn.widgets.CheckButtonGroup(
            options={G.KIND_LABELS[k]: k for k in G.KINDS}, value=list(GEO_ON),
            button_type="primary", button_style="outline", height=32, margin=(5, 4, 8, 4),
            description="Boundary lines drawn on the map")
        self.geo_color = pn.widgets.ColorPicker(name="Color", value=GEO_COLOR, width=60)
        self.geo_width = pn.widgets.FloatSlider(name="Line width", start=0.5, end=4,
                                                step=0.25, value=1.0, width=140)
        self.geo_grid = pn.widgets.Checkbox(name="Lat/lon lines", value=False,
                                            margin=(5, 4, 12, 4))
        self.geo_step = pn.widgets.Select(
            name="Every", options={"Auto": 0.0, **{f"{s:g}°": s for s in G.STEPS}},
            value=0.0, width=80)
        self.geo_inset = pn.widgets.Checkbox(name="Inset map", value=True,
                                             margin=(5, 4, 12, 4))
        self.geo_r = {}
        for k in G.KINDS:
            x, y = self.geo.lines(k)
            src = ColumnDataSource(dict(x=x, y=y))
            self.geo_r[k] = fig.line("x", "y", source=src, line_color=GEO_COLOR,
                                     visible=k in GEO_ON)
        self.grid_src = ColumnDataSource(dict(x=[], y=[]))
        self.grid_r = fig.line("x", "y", source=self.grid_src, line_color=GEO_COLOR,
                               line_dash="dotted", line_alpha=0.6, visible=False)
        self.grid_lab = {}
        for edge, kw in (("bottom", dict(text_align="center", text_baseline="bottom",
                                         y_offset=-3)),
                         ("left", dict(text_align="left", text_baseline="middle",
                                       x_offset=4))):
            src = ColumnDataSource(dict(x=[], y=[], text=[]))
            self.grid_lab[edge] = (src, fig.text("x", "y", text="text", source=src,
                                                 text_color=GEO_COLOR, text_font_size="10px",
                                                 visible=False, **kw))
        x0, x1, y0, y1 = self.extent
        table = G.lonlat_table(self.geo, (x0, x1), (y0, y1), n=49)
        hover.tooltips = list(hover.tooltips) + [("lat, lon", "$x{lonlat}")]
        hover.formatters = {"$x": CustomJSHover(args=dict(t=table), code=LONLAT_JS)}
        self._build_inset(fig, table)
        self._geo_style()

    def _build_inset(self, fig, table):
        """A small locator map (lon, lat; states and coasts round the domain) with the
        domain's outline and the map's view on it, floated over the map's corner."""
        x0, x1, y0, y1 = self.extent
        lo, hi, la, lb = self.geo.box((x0, x1), (y0, y1))
        clon, clat = 0.5 * (lo + hi), 0.5 * (la + lb)
        k = max(np.cos(np.radians(clat)), 0.2)
        h = max(6.0, 2.5 * (lb - la))  # half-height (degrees of lat)
        w = 1.35 * h  # half-width (scaled degrees)
        ins = figure(width=190, height=int(190 * h / w), tools="", toolbar_location=None,
                     x_range=Range1d(-w, w), y_range=Range1d(clat - h, clat + h),
                     background_fill_color="#0b0f17", border_fill_color="#0b0f17",
                     outline_line_color="#475569", min_border=0)
        ins.axis.visible = False
        ins.grid.visible = False
        for kind in INSET_KINDS:
            lon, lat = G.lonlat_lines(kind, clon - w / k, clon + w / k, clat - h, clat + h)
            ins.line((lon - clon) * k, lat, line_color="#94a3b8",
                     line_width=0.8 if kind == "states" else 1.0,
                     line_alpha=0.6 if kind == "states" else 0.9)
        s = np.linspace(0.0, 1.0, 17)
        ex = np.concatenate([x0 + (x1 - x0) * s, np.full(17, x1), x1 - (x1 - x0) * s,
                             np.full(17, x0)])
        ey = np.concatenate([np.full(17, y0), y0 + (y1 - y0) * s, np.full(17, y1),
                             y1 - (y1 - y0) * s])
        dl, da = self.geo.lonlat(ex, ey)
        dl = clon + (dl - clon + 180.0) % 360.0 - 180.0
        ins.patch((dl - clon) * k, da, fill_color="#f87171", fill_alpha=0.15,
                  line_color="#f87171", line_width=1.5)
        view = ColumnDataSource(dict(x=[], y=[]))
        ins.line("x", "y", source=view, line_color="#fbbf24", line_width=1.5)
        cb = CustomJS(args=dict(t=table, c=[clon, k], xr=fig.x_range, yr=fig.y_range,
                                src=view), code=INSET_JS)
        for r in (fig.x_range, fig.y_range):
            r.js_on_change("start", cb)
            r.js_on_change("end", cb)
        fig.js_on_event("document_ready", cb)
        
        # Create the Bokeh pane without the absolute positioning styles
        inset_map = pn.pane.Bokeh(ins, margin=0)

        # Wrap it in a Panel Column and apply the styles to the wrapper
        self.inset = pn.Column(
            inset_map, 
            margin=0, 
            visible=True, 
            styles={
                "position": "absolute", "top": "64px", "left": "44px", "z-index": "20",
                "border": "1px solid #475569", "border-radius": "4px", "overflow": "hidden"
            }
        )

    def _geo_bar(self, drawer):
        """The Boundaries pill and its drawer row (None without Run.geo)."""
        if self.geo is None:
            return None
        return drawer.add("geo", "Boundaries", self.geo_kinds, self.geo_color, self.geo_width,
                          self.geo_grid, self.geo_step, self.geo_inset)

    def _wire_geo(self):
        if self.geo is None:
            return
        for w in (self.geo_kinds, self.geo_color, self.geo_width, self.geo_grid,
                  self.geo_inset):
            w.param.watch(lambda e: self._geo_style(), "value")  # (glyph styles only)
        self.geo_step.param.watch(lambda e: self._geo_grid_lines(), "value")

    def _geo_style(self):
        """Show the chosen layers in the chosen colour and width; the lat/lon lines."""
        on, c, w = set(self.geo_kinds.value), self.geo_color.value, self.geo_width.value
        for k, r in self.geo_r.items():
            fw, fa = GEO_LOOK[k]
            r.visible = k in on
            r.glyph.update(line_color=c, line_width=w * fw, line_alpha=fa)
        grid = bool(self.geo_grid.value)
        if grid and not len(self.grid_src.data["x"]):
            self._geo_grid_lines()
        self.grid_r.visible = grid
        self.inset.visible = bool(self.geo_inset.value)
        self.grid_r.glyph.update(line_color=c, line_width=max(0.5, 0.75 * w))
        for src, r in self.grid_lab.values():
            r.visible = grid
            r.glyph.text_color = c
        if getattr(self, "map_drawer", None) is not None:  # (built after the map)
            self.map_drawer.label("geo", self._geo_label())

    def _geo_label(self):
        n = len(self.geo_kinds.value) + bool(self.geo_grid.value)
        return f"Boundaries · {n}" if n else "Boundaries"

    def _geo_grid_lines(self):
        """The lat/lon lines and their labels every geo_step (0: auto) degrees."""
        x0, x1, y0, y1 = self.extent
        x, y, labels, step = G.graticule(self.geo, self.geo_step.value or None,
                                         (x0, x1), (y0, y1))
        self.grid_src.data = dict(x=x, y=y)
        for edge, (src, _) in self.grid_lab.items():
            mine = [lab for lab in labels if lab[3] == edge]
            src.data = dict(x=np.array([lab[0] for lab in mine], np.float64),
                            y=np.array([lab[1] for lab in mine], np.float64),
                            text=[lab[2] for lab in mine])

    def _geo_state(self):
        """The session's "boundaries" entry (None without Run.geo)."""
        if self.geo is None:
            return None
        return {k: getattr(self, a).value for k, a in GEO_KEYS}

    def _put_geo(self, s, put):
        if self.geo is None or not s:
            return
        kinds = s.get("kinds")
        if isinstance(kinds, list):
            self.geo_kinds.value = [k for k in kinds if k in G.KINDS]
        for k, a in GEO_KEYS[1:]:
            put(getattr(self, a), s.get(k), k)
        self._geo_style()
