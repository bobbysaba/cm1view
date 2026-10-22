"""Shared pieces of the viewer UI: constants, figure styling, drawers and pills of the
toolbars, and the tool rail."""

import base64
import io
from functools import partial

import numpy as np
import panel as pn
from bokeh.models import FixedTicker, LinearAxis

from ..theme import BG, CSS, FIGURE, GRID, MUTED, PANEL, TEXT, TOOLBAR

SOUNDING_VARS = ("th", "prs", "qv", "uinterp", "vinterp")
BASE_VARS = ("th0", "prs0", "qv0", "u0", "v0")
LEVEL_MODES = {"Height AGL (km)": "height", "Model level (k)": "level",
               "Column max": "colmax", "Column min": "colmin"}
FRAMES = {"Ground-relative": "ground", "Grid-relative": "grid", "Storm-relative": "storm"}
FRAME_SHORT = {"ground": "ground-rel", "grid": "grid-rel", "storm": "storm-rel"}
EMPTY_LINES = dict(xs=[], ys=[])
EMPTY_VEC = dict(x0=[], y0=[], x1=[], y1=[], angle=[])


def pd_empty():
    import pandas as pd
    return pd.DataFrame({"time": [], "x (km)": [], "y (km)": [], "value": []})


def style_fig(fig):
    fig.background_fill_color = PANEL
    fig.border_fill_color = BG
    fig.outline_line_color = GRID
    for ax in fig.axis:
        ax.axis_line_color = GRID
        ax.major_tick_line_color = GRID
        ax.minor_tick_line_color = None
        ax.major_label_text_color = MUTED
        ax.axis_label_text_color = MUTED
        ax.axis_label_text_font_style = "normal"
    fig.grid.grid_line_color = GRID
    fig.grid.grid_line_alpha = 0.35
    fig.toolbar.logo = None
    fig.min_border_left = 50
    fig.toolbar.stylesheets = [*fig.toolbar.stylesheets, TOOLBAR]


def _bokeh(fig, **kw):
    """A Bokeh figure in a pane, with the figure styles (Panel replaces the figure's
    own stylesheets with the pane's)."""
    return pn.pane.Bokeh(fig, stylesheets=[FIGURE], **kw)


def _svg(fig):
    """Matplotlib figure as an SVG data URI (sharp at any zoom, smaller than PNG)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", facecolor=fig.get_facecolor())
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


# Map ranges: equal km per pixel in x and y at every plot size.  The pan/zoom limits
# and the reset view are the domain fitted to the current plot shape; on a resize the
# view keeps its centre and at least everything that was visible.
KEEP_ASPECT_JS = """
const w = fig.inner_width, h = fig.inner_height;
if (!(w > 0 && h > 0)) return;
const [X0, X1, Y0, Y1] = ext;
const smax = Math.max((X1 - X0) / w, (Y1 - Y0) / h);
const cx0 = (X0 + X1) / 2, cy0 = (Y0 + Y1) / 2;
const bx = [cx0 - smax * w / 2, cx0 + smax * w / 2];
const by = [cy0 - smax * h / 2, cy0 + smax * h / 2];
const xr = fig.x_range, yr = fig.y_range;
const first = !xr.tags.includes('fitted');
let s = Math.max(Math.abs(xr.end - xr.start) / w, Math.abs(yr.end - yr.start) / h);
if (first || !(s < smax)) s = smax;
const hx = s * w / 2, hy = s * h / 2;
const clamp = (c, b, half) => Math.min(Math.max(c, b[0] + half), b[1] - half);
const cx = clamp(first ? cx0 : (xr.start + xr.end) / 2, bx, hx);
const cy = clamp(first ? cy0 : (yr.start + yr.end) / 2, by, hy);
yr.setv({bounds: by, reset_start: by[0], reset_end: by[1], start: cy - hy, end: cy + hy});
xr.setv({bounds: bx, reset_start: bx[0], start: cx - hx, end: cx + hx});
if (first) xr.tags = [...xr.tags, 'fitted'];
xr.reset_end = bx[1];  // last: the server re-renders on this change
"""


def _cbar_label(fig):
    """Colorbar label outside the bar: vertical, centred, reading bottom to top
    (matplotlib style).  A tick-less axis to the right of the colorbar, since its
    label (unlike a side Title) can be rotated."""
    ax = LinearAxis(ticker=FixedTicker(ticks=[]), axis_line_color=None,
                    major_tick_line_color=None, minor_tick_line_color=None,
                    axis_label="", axis_label_text_color=TEXT,
                    axis_label_text_font_style="normal", axis_label_text_font_size="12px",
                    axis_label_orientation=np.pi / 2, axis_label_standoff=6)
    fig.add_layout(ax, "right")
    return ax


def _html(text="", **kw):
    return pn.pane.HTML(text, stylesheets=[CSS], **kw)


class Drawer:
    """Toolbar pills; each opens its own row of controls in a shared drawer
    below the toolbar.  Clicking the open pill again closes the drawer."""

    def __init__(self):
        self.items = {}
        self.panel = pn.Column(
            sizing_mode="stretch_width", visible=False, margin=(0, 4, 4, 4),
            styles={"background": PANEL, "border": f"1px solid {GRID}",
                    "border-radius": "10px", "padding": "2px 8px 6px 8px"},
            # grow with the open row: Panel caps a layout at max-height 100%, which for
            # the floating drawer is the height of the toolbar it hangs from
            stylesheets=[":host { max-height: none !important; }"])

    def add(self, key, label, *content):
        btn = pn.widgets.Button(name=f"{label} ▾", button_type="default",
                                button_style="outline", height=34, margin=(5, 3))
        body = pn.FlexBox(*content, flex_wrap="wrap", align_items="flex-end",
                          gap="2px 14px", visible=False, sizing_mode="stretch_width")
        btn.on_click(lambda e: self.toggle(key))
        self.items[key] = (btn, body)
        self.panel.append(body)
        return btn

    def toggle(self, key=None):
        opening = key is not None and not self.items[key][1].visible
        for k, (btn, body) in self.items.items():
            on = opening and k == key
            body.visible = on
            btn.button_style = "solid" if on else "outline"
            btn.button_type = "primary" if on else "default"
            btn.css_classes = ["cv-open"] if on else []
        self.panel.visible = opening

    def label(self, key, text):
        btn = self.items[key][0]
        if btn.name != f"{text} ▾":
            btn.name = f"{text} ▾"


def _pill(check, btn):
    """Checkbox + pill button kept together when the toolbar wraps."""
    return pn.Row(check, btn, margin=0)


PILL = {"background": "rgba(17,23,35,0.9)", "border": f"1px solid {GRID}",
        "border-radius": "20px", "padding": "0 6px", "backdrop-filter": "blur(6px)",
        "box-shadow": "0 4px 14px rgba(0,0,0,0.35)", "pointer-events": "auto",
        "align-items": "center"}
# toolbars sit in the page flow above what they control (a bar that wraps onto a
# second row pushes the map down instead of covering it); their drawers float below
BAR = {"position": "relative", "z-index": "30", "pointer-events": "none",
       "padding": "8px 8px 0 8px", "flex": "0 0 auto"}
DRAWER = {"position": "absolute", "top": "100%", "left": "8px", "width": "calc(100% - 16px)",
          "pointer-events": "auto", "background": "rgba(17,23,35,0.95)",
          "box-shadow": "0 6px 20px rgba(0,0,0,.45)"}
FILL = {"flex": "1 1 0", "min-height": "0"}  # the rest of a column's height


# controls inside the floating pills: no borders of their own (the pill is the frame),
# a light hover, and a cyan tint for the active / open one
GHOST = """
.bk-btn { border-color: transparent !important; background-color: transparent !important;
          color: #cbd5e1 !important; box-shadow: none !important; }
.bk-btn:hover { background-color: rgba(148,163,184,.14) !important; }
.bk-btn.bk-active, :host(.cv-open) .bk-btn {
  background-color: rgba(34,211,238,.18) !important; color: #a5f3fc !important;
  border-color: transparent !important; }
.bk-input { border-color: transparent !important; background-color: transparent !important; }
.bk-input:hover { background-color: rgba(148,163,184,.10) !important; }
"""


def _ghost(obj):
    for w in obj.select(pn.widgets.Widget):
        w.stylesheets = list(w.stylesheets) + [GHOST]
    return obj


def _group(*objs):
    """A floating pill holding a few related controls."""
    return _ghost(pn.Row(*objs, styles=PILL, margin=(0, 0, 6, 0)))


def _settings_toggle(body, icon="adjustments-horizontal", description="Settings"):
    """An icon button (settings by default) that shows / hides `body`; tinted while
    `body` is shown."""
    btn = pn.widgets.Button(name="", icon=icon, description=description,
                            button_type="primary", button_style="outline", width=40,
                            height=32, margin=(5, 4, 8, 4), stylesheets=[ON])

    def flip(e):
        body.visible = not body.visible
        btn.css_classes = ["cv-on"] if body.visible else []
    btn.on_click(flip)
    body.visible = False
    return btn


# a button kept "pressed" by giving it the cv-on class
ON = """:host(.cv-on) .bk-btn { background-color: rgba(34,211,238,.18) !important;
  border-color: rgba(34,211,238,.5) !important; color: #a5f3fc !important; }"""


def _bar(*groups):
    return pn.FlexBox(*groups, flex_wrap="wrap", align_items="center", gap="0 8px",
                      styles={"pointer-events": "none"}, sizing_mode="stretch_width")


# the analysis tools down the left of the map: button -> (icon, label, tooltip)
TOOLS = {
    "Sounding": ("balloon", "Sounding", "Soundings: click the map (or drag a box for "
                                            "an area mean)"),
    "Cross-section": ("slice", "Section", "Vertical cross-section: click A, then B"),
    "Track": ("route", "Track", "Storm track: click a storm to follow it through time"),
    "Series": ("chart-line", "Series", "Time series of a field over a region"),
    "Distribution": ("chart-histogram", "Distrib.", "Distribution of a field over a region "
                                                    "at one time: histogram, box, violin, "
                                                    "cumulative"),
    "3D region": ("cube", "3D box", "Drag a box on the map to view it in 3D"),
}
# click mode -> its tool button (both kinds of sounding are the Sounding tool)
TOOL_OF = {"Area sounding": "Sounding"}
# click mode -> its panel (tab of the analysis panel); 3D region has none
PANELS = {"Sounding": 0, "Area sounding": 0, "Cross-section": 1, "Track": 2, "Series": 3,
          "Distribution": 4}
TAB_MODE = {0: "Sounding", 1: "Cross-section", 2: "Track", 3: "Series", 4: "Distribution"}
PANEL_TITLES = ["Sounding", "Cross-section", "Storm track", "Time series", "Distribution"]

RAIL_BTN = """
.bk-btn { display: flex !important; flex-direction: column; align-items: center; gap: 3px;
          width: 64px; padding: 7px 0 6px 0 !important; font-size: 11px !important;
          border-color: transparent !important; background-color: transparent !important;
          color: #94a3b8 !important; box-shadow: none !important; }
.bk-btn:hover { background-color: rgba(148,163,184,.14) !important; color: #e2e8f0 !important; }
:host(.cv-on) .bk-btn { background-color: rgba(34,211,238,.18) !important;
                        color: #a5f3fc !important; }
.bk-btn .bk-TablerIcon { font-size: 20px; }
"""


# the time bar: a click anywhere near the track jumps there (noUiSlider's tap works only
# on the few-pixel track itself, so a taller invisible strip catches the clicks)
TIME_BAR = """
.noUi-base::before { content: ""; position: absolute; left: 0; right: 0; top: -12px;
                     bottom: -12px; cursor: pointer; }
"""


class ToolRail:
    """The analysis tools: one on at a time, or none (value None).  The value is the
    click mode; a tool button can stand for several modes (TOOL_OF)."""

    def __init__(self, modes):
        self.btns = {}
        for m in modes:
            icon, label, tip = TOOLS[m]
            b = pn.widgets.Button(name=label, icon=icon, description=tip, width=64,
                                  height=58, margin=(2, 4), stylesheets=[RAIL_BTN])
            b.on_click(partial(self._on, m))
            self.btns[m] = b
        self.value, self._cbs = None, []
        self.mode_for = {}  # tool -> the mode its button picks (e.g. Area sounding)
        self.reclick = None  # f(tool) -> True: the lit button pressed again stays on

    def _on(self, tool, ev):
        if TOOL_OF.get(self.value, self.value) != tool:
            self.set(self.mode_for.get(tool, tool))
        elif self.reclick is None or not self.reclick(tool):
            self.set(None)

    def set(self, o):
        tool = TOOL_OF.get(o, o)
        for k, b in self.btns.items():
            b.css_classes = ["cv-on"] if k == tool else []
        if o != self.value:
            self.value = o
            for cb in self._cbs:
                cb(o)

    def watch(self, cb):
        self._cbs.append(cb)
