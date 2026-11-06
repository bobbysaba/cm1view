"""The map on the Earth (runs with a map projection, Run.geo: WoFS / WRF): boundary
lines (coastlines, countries, states, lakes, US counties), lat/lon lines with
labels, and lat/lon in the map's hover.  Idealized runs (CM1) have none of it: no
widgets, no glyphs, no Boundaries pill.

The lines are worked out once (core/geo.py, projected into the grid's km) and
drawn in the browser; showing, hiding or restyling them never redraws the map.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import numpy as np
import panel as pn
from bokeh.models import ColumnDataSource, CustomJSHover

from ..core import geo as G

from ..figures.draw.layers import BOUNDARY_LOOK as GEO_LOOK  # (figures draw them alike)

GEO_ON = list(G.SHOWN)  # shown at first
GEO_COLOR = "#cbd5e1"
# the session's "boundaries" entry: key -> Viewer attribute
GEO_KEYS = (("kinds", "geo_kinds"), ("color", "geo_color"), ("width", "geo_width"),
            ("grid", "geo_grid"), ("step", "geo_step"))

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


class MapLines:
    geo = None  # the run's Geo (None: an idealized run, nothing here is built)

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
        self._geo_style()

    def _geo_bar(self, drawer):
        """The Boundaries pill and its drawer row (None without Run.geo)."""
        if self.geo is None:
            return None
        return drawer.add("geo", "Boundaries", self.geo_kinds, self.geo_color, self.geo_width,
                          self.geo_grid, self.geo_step)

    def _wire_geo(self):
        if self.geo is None:
            return
        for w in (self.geo_kinds, self.geo_color, self.geo_width, self.geo_grid):
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
