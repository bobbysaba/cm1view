"""Panel application: map + sounding / cross-section / 3D panels."""

import base64
import io
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from functools import partial

_VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.append(_VENDOR)

import numpy as np  # noqa: E402
import panel as pn  # noqa: E402
from bokeh.events import PanStart, RangesUpdate, SelectionGeometry, Tap  # noqa: E402
from bokeh.models import (  # noqa: E402
    BoxSelectTool, BoxZoomTool, ColorBar, ColumnDataSource, CustomJS, HoverTool, Label,
    LinearColorMapper,
    FixedTicker, LinearAxis, PanTool, Range1d, ResetTool, SaveTool, Span, WheelZoomTool,
)
from bokeh.plotting import figure  # noqa: E402
from bokeh.transform import transform  # noqa: E402

from . import pdecomp  # noqa: E402
from . import figui, registry, render, series as ser, sounding_plot as sp, thermo  # noqa: E402
from . import track as trk, volume3d  # noqa: E402
from .run import FileBusy, MissingAtTime  # noqa: E402
from .fields import CMAPS, palette  # noqa: E402
from .zoomview import ParamTable, ZoomImage  # noqa: E402
from .theme import (  # noqa: E402
    ACCENT, BG, CSS, GRID, MUTED, PANEL, POINT_COLORS, POINT_LABELS, TEXT,
)

SOUNDING_VARS = ("th", "prs", "qv", "uinterp", "vinterp")
BASE_VARS = ("th0", "prs0", "qv0", "u0", "v0")
LEVEL_MODES = {"Height AGL (km)": "height", "Model level (k)": "level",
               "Column max": "colmax", "Column min": "colmin"}
FRAMES = {"Ground-relative": "ground", "Grid-relative": "grid", "Storm-relative": "storm"}
FRAME_SHORT = {"ground": "ground-rel", "grid": "grid-rel", "storm": "storm-rel"}
EMPTY_LINES = dict(xs=[], ys=[])
EMPTY_VEC = dict(x0=[], y0=[], x1=[], y1=[], angle=[])

_BASE_CACHE = {}


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


def _svg(fig):
    """Matplotlib figure as an SVG data URI (sharp at any zoom, smaller than PNG)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", facecolor=fig.get_facecolor())
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


# run picker dialog in the dark theme (Panel's dialog box is white by default)
RP_DARK = f"""
.dialog-content {{ background-color: {PANEL} !important; color: {TEXT};
  border: 1px solid {GRID}; border-radius: 12px; padding: 14px 16px 20px 16px;
  box-shadow: 0 18px 50px rgba(0,0,0,.55); }}
.dialog-overlay {{ background-color: rgba(5, 8, 14, 0.78) !important; }}
.pnx-dialog-close {{ color: {MUTED} !important; }}
.pnx-dialog-close:hover {{ color: {TEXT} !important; }}
"""


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
                    "border-radius": "10px", "padding": "2px 8px 6px 8px"})

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
OVERLAY = {"position": "absolute", "top": "8px", "left": "8px", "width": "calc(100% - 16px)",
           "z-index": "30", "pointer-events": "none"}


# controls inside the floating pills: no borders of their own (the pill is the frame),
# a light hover, and a cyan tint for the active / open one
GHOST = """
.bk-btn { border-color: transparent !important; background-color: transparent !important;
          color: #cbd5e1 !important; box-shadow: none !important; }
.bk-btn:hover { background-color: rgba(148,163,184,.14) !important; }
.bk-btn.bk-active, :host(.cv-open) .bk-btn {
  background-color: rgba(34,211,238,.18) !important; color: #a5f3fc !important; }
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


def _settings_toggle(body):
    """A '⚙ Settings' toggle that shows / hides `body`."""
    btn = pn.widgets.Toggle(name="⚙ Settings", value=False, button_type="primary",
                            button_style="outline", height=32, margin=(5, 4, 8, 4))
    btn.param.watch(lambda e: setattr(body, "visible", e.new), "value")
    body.visible = False
    return btn


def _bar(*groups):
    return pn.FlexBox(*groups, flex_wrap="wrap", align_items="center", gap="0 8px",
                      styles={"pointer-events": "none"}, sizing_mode="stretch_width")


class ModeToggles:
    """Mutually exclusive toggle buttons that may all be off (value None)."""

    def __init__(self, options, **kw):
        self.btns = {o: pn.widgets.Toggle(name=o, button_type="primary",
                                          button_style="outline", **kw) for o in options}
        self.value, self._busy, self._cbs = None, False, []
        for o, b in self.btns.items():
            b.param.watch(partial(self._on, o), "value")

    def _on(self, o, ev):
        if not self._busy:
            self.set(o if ev.new else None)

    def set(self, o):
        self._busy = True
        try:
            for k, b in self.btns.items():
                b.value = k == o
        finally:
            self._busy = False
        if o != self.value:
            self.value = o
            for cb in self._cbs:
                cb(o)

    def watch(self, cb):
        self._cbs.append(cb)


class Viewer:
    def __init__(self, run, fields, maxpix=900, error="", reg=None):
        self.run, self.F = run, fields
        self.reg = reg  # the shared runs (figures with panels from other runs)
        self.maxpix = maxpix
        self.error = error
        self.doc = pn.state.curdoc
        self.pools = {k: ThreadPoolExecutor(1, thread_name_prefix=f"cm1view-{k}")
                      for k in ("map", "snd", "xs", "3d", "trk", "sl", "pd", "ser", "fig")}
        self.gen = dict.fromkeys(self.pools, 0)
        # soundings: (kind, where, tpin) with kind "pt" (where = x, y km), "mean"
        # (where = None) or "trk" (where = offset from the tracked meso, km);
        # where may carry a box size, (x, y, width, height) km, for area means;
        # tpin = None follows the time slider, otherwise a pinned time index
        self.points, self.results, self.xs_pts, self.box = [], [], [], None
        self.fixes, self.trk_spec = {}, None  # meso track: {t: fix}, settings used
        self._hold = False
        self._drag_shift = False  # Shift held when the last map drag started
        dxk, dyk = run.dx / 1000.0, run.dy / 1000.0
        self.extent = (run.xh[0] - dxk / 2, run.xh[-1] + dxk / 2,
                       run.yh[0] - dyk / 2, run.yh[-1] + dyk / 2)
        self.view = self.extent
        self._build_widgets()
        self._build_map()
        self._build_xsec()
        self._build_track()
        self._build_series()
        self._build_panels()
        self.map_bar, self.v3_bar = self._map_toolbar(), self._3d_toolbar()
        self.figed = figui.FigureEditor(self)
        self._wire()
        self.request_map()

    # ================================================================ widgets
    @property
    def t(self):
        return int(self.tslider.value)

    def _level_pair(self, mode="height", value=1.0, compact=False):
        """Level-mode select + level value.  compact: unlabelled spinner for the
        toolbar (arrow keys / wheel step through levels)."""
        run = self.run
        ztop = float(np.floor(run.z[-1] * 10) / 10)
        if compact:
            mode_w = pn.widgets.Select(options=LEVEL_MODES, value=mode, width=140, height=32,
                                       margin=(4, 2))
            lvl = pn.widgets.FloatInput(start=0.0, end=ztop, step=0.25, value=value,
                                        width=70, height=32, margin=(4, 4))
            hstep, names = 0.25, ("", "")
        else:
            mode_w = pn.widgets.Select(name="Level", options=LEVEL_MODES, value=mode,
                                       width=150)
            lvl = pn.widgets.FloatSlider(name="km AGL", start=0.0, end=ztop, step=0.05,
                                         value=value, width=210)
            hstep, names = 0.05, ("Model level k", "km AGL")

        def on_mode(ev):
            if ev.new == "level":
                k = run.level_weights(lvl.value)[0] if ev.old == "height" else 0
                lvl.param.update(start=0, end=run.nk - 1, step=1, value=float(k))
                if names[0]:
                    lvl.name = names[0]
            elif ev.new == "height":
                z = float(run.z[int(lvl.value)]) if ev.old == "level" else 1.0
                lvl.param.update(start=0.0, end=ztop, step=hstep, value=round(z, 2))
                if names[1]:
                    lvl.name = names[1]
            lvl.disabled = ev.new in ("colmax", "colmin")

        mode_w.param.watch(on_mode, "value")
        return mode_w, lvl

    def _build_widgets(self):
        run, F = self.run, self.F
        g_all, g3 = F.groups(), F.groups(ndim=3)
        default_fill = "cref" if "cref" in F else ("dbz" if "dbz" in F else next(iter(F.defs)))

        t0 = 0
        try:  # ?t=<index> in the URL opens at that time
            t0 = int(pn.state.session_args.get("t", [b"0"])[0])
            t0 = min(max(t0, 0), len(run.times) - 1)
        except (AttributeError, TypeError, ValueError):
            pass
        self.tslider = pn.widgets.IntSlider(name="", start=0, end=len(run.times) - 1,
                                            value=t0, show_value=False, width=260,
                                            margin=(4, 12))
        btn = dict(button_type="light", button_style="outline", width=34, height=32,
                   name="", icon_size="1.1em", margin=(4, 1))
        self.t_prev = pn.widgets.Button(icon="player-track-prev", **btn)
        self.t_play = pn.widgets.Button(icon="player-play", **btn)
        self.t_next = pn.widgets.Button(icon="player-track-next", **btn)
        self.t_speed = pn.widgets.Select(options={"0.5×": 2400, "1×": 1200, "2×": 600,
                                                  "4×": 300}, value=1200, width=66, height=32,
                                         margin=(4, 4))
        self.playing = False
        self._play_cb = None
        self.time_html = _html()

        self.workspace = pn.widgets.RadioButtonGroup(
            options=["Map", "3D", "Figure"], value="Map", button_type="primary",
            button_style="outline", width=190, height=32, margin=(4, 2))
        modes = ["Sounding", "Area sounding", "Cross-section", "3D region"]
        if trk.available(run):
            modes.append("Track")
        self.mode = ModeToggles(modes, height=32, margin=(4, 1))
        self.hint = _html()

        # ---- fill layer
        fd = F[default_fill]
        self.fill_var = pn.widgets.Select(groups=g_all, value=default_fill, width=220,
                                          height=32, margin=(4, 2))
        self.fill_mode, self.fill_lvl = self._level_pair("height", 1.0, compact=True)
        self.fill_style = pn.widgets.RadioButtonGroup(
            options={"Pixels": "image", "Filled contours": "contourf"}, value="image",
            button_type="primary", button_style="outline", width=230, margin=(5, 10, 8, 10))
        self.fill_cmap = pn.widgets.Select(name="Colormap", options=CMAPS, value=fd.cmap,
                                           width=150)
        self.fill_rev = pn.widgets.Checkbox(name="Reverse", value=False, margin=(5, 10, 14, 10))
        self.fill_auto = pn.widgets.Checkbox(name="Auto range", value=True,
                                             margin=(5, 10, 14, 10))
        lo, hi = fd.vrange or (0.0, 1.0)
        self.fill_min = pn.widgets.FloatInput(name="Min", value=lo, width=90, disabled=True)
        self.fill_max = pn.widgets.FloatInput(name="Max", value=hi, width=90, disabled=True)
        self.fill_nlev = pn.widgets.IntSlider(name="Contour intervals", start=4, end=30,
                                              value=15, width=160)
        self.fill_alpha = pn.widgets.FloatSlider(name="Opacity", start=0.1, end=1.0,
                                                 step=0.05, value=1.0, width=150)

        # ---- contour overlays
        def overlay(on, var, mode, level, levels, color, width):
            m, lv = self._level_pair(mode, level)
            return dict(
                on=pn.widgets.Checkbox(value=on, width=18, margin=(14, 0, 0, 8)),
                var=pn.widgets.Select(name="Field", groups=g_all, value=var, width=250),
                mode=m, level=lv,
                levels=pn.widgets.TextInput(
                    name="Levels", value=levels, width=190,
                    placeholder="auto  |  5, 10, 20  |  -4:4:1"),
                color=pn.widgets.ColorPicker(name="Color", value=color, width=60),
                width=pn.widgets.FloatSlider(name="Line width", start=0.5, end=4, step=0.25,
                                             value=1.4, width=130),
                negdash=pn.widgets.Checkbox(name="Dash negative", value=True,
                                            margin=(5, 10, 14, 10)),
            )

        ov1 = ("winterp", "height", 3.0, "5, 15, 25", "#ffffff") if "winterp" in F \
            else (default_fill, "height", 1.0, "auto", "#ffffff")
        ov2 = ("thpert", "level", 0.0, "-6, -4, -2, -1", "#60a5fa") if "thpert" in F \
            else (default_fill, "height", 1.0, "auto", "#60a5fa")
        self.ovs = [overlay(True, *ov1, 1.4), overlay(False, *ov2, 1.4)]
        if ov2[1] == "level":
            self.ovs[1]["mode"].value = "level"
            self.ovs[1]["level"].value = 0.0

        # ---- vectors
        self.vec_on = pn.widgets.Checkbox(value=False, width=18, margin=(14, 0, 0, 8))
        self.vec_lvl = pn.widgets.FloatSlider(name="Height (km AGL)", start=0.0,
                                              end=float(np.floor(run.z[-1])), step=0.05,
                                              value=0.5, width=190)
        self.vec_frame = pn.widgets.Select(
            name="Frame", options=FRAMES,
            value="grid" if (run.umove or run.vmove) else "ground", width=150)
        self.vec_style = pn.widgets.Select(name="Draw as", options={
            "Arrows": "arrows", "Streamlines": "streamlines"}, value="arrows", width=120)
        self.vec_density = pn.widgets.IntSlider(name="Arrows across view", start=8, end=50,
                                                value=24, width=170)
        self.vec_ref = pn.widgets.FloatInput(name="Ref. speed (m/s)", value=20.0, width=110)
        self.vec_color = pn.widgets.ColorPicker(name="Color", value="#e5e7eb", width=60)

        # ---- sounding options
        self.storm = pn.widgets.Select(
            name="Storm motion", options={"Bunkers right-mover": "rm",
                                          "Bunkers left-mover": "lm",
                                          "0–6 km mean wind": "mean",
                                          "Domain motion (umove, vmove)": "domain",
                                          "Tracked meso motion": "track",
                                          "Custom": "custom"},
            value="rm", width=210)
        self.storm_u = pn.widgets.FloatInput(name="u (m/s)", value=run.umove, width=80,
                                             visible=False)
        self.storm_v = pn.widgets.FloatInput(name="v (m/s)", value=run.vmove, width=80,
                                             visible=False)
        self.parcel = pn.widgets.RadioButtonGroup(
            options={"SB": "sb", "ML": "ml", "MU": "mu"}, value="ml",
            button_type="primary", button_style="outline", width=140, margin=(5, 10, 8, 10))
        self.wunits = pn.widgets.RadioButtonGroup(options=["m/s", "kt"], value="m/s",
                                                  button_type="primary",
                                                  button_style="outline", width=100,
                                                  margin=(5, 10, 8, 10))
        self.avg = pn.widgets.Select(
            name="Column average", options={"Single column": 0.0, "1 km box": 1.0,
                                            "2 km box": 2.0, "5 km box": 5.0,
                                            "10 km box": 10.0},
            value=0.0, width=130)
        self.prof_top = pn.widgets.Select(options=[1, 3, 6, 10, 15], value=6, width=70,
                                          height=30, margin=(2, 6))
        self.compare = pn.widgets.RadioButtonGroup(
            options={"Line styles": "lines", "Colors": "colors", "Tabs": "tabs"},
            value="lines", button_type="primary", button_style="outline", width=230,
            margin=(5, 10, 8, 10), description="How several soundings are shown")
        self.mean_btn = pn.widgets.Button(
            name="Domain mean", button_type="primary", button_style="outline", height=32,
            margin=(5, 4, 8, 10), description="Show the domain-mean sounding (follows time)")
        self.pin_btn = pn.widgets.Button(
            name="📌 Pin this time", button_type="primary", button_style="outline",
            height=32, margin=(5, 4, 8, 4),
            description="Freeze sounding 1 at the current time (the domain mean if there is "
                        "none); move the time slider and sounding 1 follows, so you can "
                        "compare times")
        self.storm_follow = pn.widgets.Checkbox(
            name="Move with tracked storm", value=False, margin=(5, 10, 14, 10),
            disabled=True)  # clicked soundings keep their offset from the tracked meso
        self.snd_clear = pn.widgets.Button(name="Clear", button_type="light",
                                           button_style="outline", height=32,
                                           margin=(5, 4, 8, 4))
        self.base_on = pn.widgets.Checkbox(name="Base state", value=True,
                                           margin=(5, 10, 14, 10))
        self.follow = pn.widgets.Checkbox(name="Follow time", value=True,
                                          margin=(5, 10, 14, 10))

        # ---- sounding plot style (redraws only) and zoom limits
        st = sp.STYLE
        ck = dict(margin=(5, 10, 14, 10))
        self.ps = dict(
            t=pn.widgets.ColorPicker(name="Temperature", value=st["t_color"], width=86),
            td=pn.widgets.ColorPicker(name="Dewpoint", value=st["td_color"], width=86),
            parcel=pn.widgets.ColorPicker(name="Parcel", value=st["parcel_color"], width=86),
            base=pn.widgets.ColorPicker(name="Base state", value=st["base_color"], width=86),
            lw=pn.widgets.FloatSlider(name="T / Td width", start=0.5, end=5, step=0.1,
                                      value=st["lw"], width=130),
            parcel_lw=pn.widgets.FloatSlider(name="Parcel width", start=0.5, end=4, step=0.1,
                                             value=st["parcel_lw"], width=130),
            hodo_lw=pn.widgets.FloatSlider(name="Hodograph width", start=0.5, end=5, step=0.1,
                                           value=st["hodo_lw"], width=130),
            prof_lw=pn.widgets.FloatSlider(name="Profile width", start=0.5, end=4, step=0.1,
                                           value=st["prof_lw"], width=130),
            ptop=pn.widgets.Select(name="Skew-T top (hPa)", value=100,
                                   options=[100, 150, 200, 250, 300, 400, 500, 600, 700],
                                   width=110),
            tmin=pn.widgets.FloatInput(name="T left (°C)", value=None, placeholder="auto",
                                       width=90),
            tmax=pn.widgets.FloatInput(name="T right (°C)", value=None, placeholder="auto",
                                       width=90),
            ring=pn.widgets.Select(name="Hodograph rings", value=0,
                                   options={"Auto": 0, "5": 5, "10": 10, "20": 20}, width=110),
            htop=pn.widgets.Select(name="Hodograph top (km)", value=12,
                                   options=[3, 6, 9, 12, 15], width=120),
            shade=pn.widgets.Checkbox(name="CAPE / CIN shading", value=st["shade"], **ck),
            barbs=pn.widgets.Checkbox(name="Wind barbs", value=st["barbs"], **ck),
            guides=pn.widgets.Checkbox(name="Adiabats & mixing lines", value=st["guides"], **ck),
        )
        self.ps_reset = pn.widgets.Button(name="Default style", button_type="light",
                                          button_style="outline", height=32,
                                          margin=(5, 4, 8, 10))
        self.snd_lim = {}  # zoom: skew, hodo, prof_z, prof_x (see _on_zoom_box)

        self.status = _html()
        # pressure decomposition for the shown time (map caption / cross-section tab)
        pdb = dict(button_type="warning", button_style="outline", height=30,
                   description=f"Run phd_scripts/{pdecomp.script_name()} on this output time "
                               "in a separate process (~45 s and ~40 GB with 4 CPUs, "
                               "~80 s and ~30 GB on one)")
        self.pd_write = pn.widgets.Checkbox(
            name="Write into the output file", value=True, margin=(10, 4, 0, 10),
            styles={"pointer-events": "auto"})  # with the script's own write_data
        self.pd_btn = pn.widgets.Button(margin=(4, 0, 6, 0),
                                        styles={"pointer-events": "auto"}, **pdb)
        self.pd_row = pn.Row(self.pd_btn, self.pd_write, margin=0, visible=False)
        self.xs_pd_btn = pn.widgets.Button(margin=(4, 4), visible=False, **pdb)
        self.cache_html = _html()
        self.clear_btn = pn.widgets.Button(name="Clear cache", button_type="default",
                                           button_style="outline", width=100, height=28,
                                           margin=(2, 6))
        self.clear_pts = pn.widgets.Button(name="", icon="eraser", button_type="light",
                                           button_style="outline", width=40, height=32,
                                           margin=(4, 2),
                                           description="Clear map markers (soundings, "
                                                       "section, 3D region)")
        self.full = False  # analysis panel expanded over the whole window
        self.full_btn = pn.widgets.Button(name="", icon="arrows-maximize", button_type="light",
                                          button_style="outline", height=32, margin=(4, 2),
                                          description="Expand the analysis panel to the full "
                                                      "window (sounding graphics become "
                                                      "zoomable)")
        self.panel_btn = pn.widgets.Button(name="", icon="layout-sidebar-right-collapse",
                                           button_type="light", button_style="outline",
                                           width=40, height=32, margin=(4, 2),
                                           description="Hide / show the analysis panel")
        self._build_run_picker()

    def _build_run_picker(self):
        run = self.run
        self.run_btn = pn.widgets.Button(name=run.name, button_type="light",
                                         button_style="outline", height=32,
                                         icon="folder-open", margin=(4, 2))
        self.rp_path = pn.widgets.TextInput(name="Run directory (contains cm1out_NNNNNN.nc)",
                                            value=run.path, width=620)
        self.rp_msg = _html()
        self.rp_list = pn.widgets.Select(name="Runs here", options={}, width=330, size=11)
        # folder browser: '..' and the subfolders of the typed path (● = has output)
        self.rp_dirs = pn.widgets.Select(name="Folders", options={}, width=280, size=11)
        recent = [p for p in registry.recent_runs() if p != run.path]
        self.rp_recent = pn.widgets.Select(
            name="Recent", options={"—": ""} | {p: p for p in recent}, value="", width=620)
        self.rp_open = pn.widgets.Button(name="Open run", button_type="primary", width=120)
        # navigation happens in the browser: the new session opens the run from ?run=
        self.rp_open.js_on_click(args=dict(inp=self.rp_path), code="""
            const p = (inp.value_input || inp.value || '').trim();
            if (!p) return;
            const q = new URLSearchParams(window.location.search);
            q.set('run', p); q.delete('t');
            window.location.search = q.toString();
        """)
        self.rp_modal = pn.Modal(
            _html('<div class="cv-maptitle" style="font-size:16px"><b>Open a CM1 run</b>'
                  '</div><div class="cv-hint">Type or paste a run directory, or pick one '
                  'below. Opening a run reloads the page; open runs share one 3D cache '
                  '(least recently used fields are freed first).</div>'),
            self.rp_path, self.rp_msg, pn.Row(self.rp_list, self.rp_dirs, margin=0),
            self.rp_recent, pn.Row(self.rp_open),
            _html(f'<div class="cv-h" style="margin-top:14px">This run</div>'
                  f'<div class="cv-run"><b>{run.path}</b><br>{run.ni}×{run.nj}×{run.nk} · '
                  f'Δx {run.dx:.0f} m · {len(run.times)} times · domain motion '
                  f'({run.umove:g}, {run.vmove:g}) m/s</div>'),
            pn.Row(self.cache_html, self.clear_btn), width=680, margin=10,
            stylesheets=[RP_DARK])

        self._rp_busy = False

        def pick(ev):
            if ev.new and not self._rp_busy:
                self.rp_path.param.update(value=ev.new, value_input=ev.new)

        def check(ev):
            p = os.path.abspath(os.path.expanduser((ev.new or "").strip()))
            n = registry.count_files(p) if os.path.isdir(p) else 0
            if n:
                self.rp_msg.object = (f'<div class="cv-status" style="color:#4ade80">'
                                      f'✓ {n} output files</div>')
            elif os.path.isdir(p):
                self.rp_msg.object = ('<div class="cv-status">No cm1out files directly '
                                      'here — pick a run below.</div>')
            else:
                self.rp_msg.object = ('<div class="cv-status" style="color:#f87171">'
                                      'Not a directory</div>')
            self.rp_open.disabled = n == 0
            base = p if os.path.isdir(p) else os.path.dirname(p)
            if os.path.isdir(base):
                runs = registry.sibling_runs(base)
                self._rp_busy = True
                try:
                    self.rp_list.options = {"/".join(r.split("/")[-3:]): r for r in runs}
                    self.rp_list.value = p if p in runs else None
                    self.rp_dirs.options = registry.subfolders(base)
                    self.rp_dirs.value = None
                finally:
                    self._rp_busy = False

        def browse(ev):  # into a folder: it becomes the path, the lists follow it
            if ev.new and not self._rp_busy:
                self.rp_path.param.update(value=ev.new, value_input=ev.new)

        self.rp_list.param.watch(pick, "value")
        self.rp_recent.param.watch(pick, "value")
        self.rp_dirs.param.watch(browse, "value")
        self.rp_path.param.watch(check, "value_input")
        self.rp_path.param.watch(check, "value")
        self.rp_path.param.trigger("value")
        self.run_btn.on_click(lambda e: self.rp_modal.show())

    # ================================================================ map
    def _build_map(self):
        x0, x1, y0, y1 = self.extent
        fig = figure(sizing_mode="stretch_both", min_height=420,
                     x_range=Range1d(x0, x1), y_range=Range1d(y0, y1),
                     tools="", toolbar_location="right",
                     x_axis_label="x (km)", y_axis_label="y (km)")
        style_fig(fig)
        fig.min_border_top = 96  # room for the floating toolbar
        fig.toolbar.autohide = True
        outline = fig.rect(x=[(x0 + x1) / 2], y=[(y0 + y1) / 2], width=[x1 - x0],
                           height=[y1 - y0], fill_alpha=0, line_color=GRID, line_width=1)
        outline.nonselection_glyph = outline.glyph
        outline.selection_glyph = outline.glyph
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

    def _build_xsec(self):
        # static view: no pan/zoom, so the plot can't be dragged off the sampled data
        fig = figure(sizing_mode="stretch_width", height=430, tools="save",
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
        self.xs_status = _html('<div class="cv-empty">Switch the click mode to '
                               '<b>Cross-section</b> and click two points on the map.</div>')

    # ================================================================ panels
    def _build_track(self):
        run = self.run
        metrics = trk.metrics(run)
        self.trk_metric = pn.widgets.Select(name="Track on", options=metrics,
                                            value=next(iter(metrics.values())), width=200)
        self.trk_z = pn.widgets.FloatInput(name="Height (km)", value=1.0, step=0.25,
                                           start=0.0, end=float(run.z[-1]), width=90,
                                           visible=self.trk_metric.value != "uh")
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
            description="Tracking ends when the maximum in the search disc falls below "
                        "this (meso lost)")
        self.trk_dir = pn.widgets.Select(
            name="Direction", options={"Forward + backward": "both", "Forward": "forward",
                                       "Backward": "backward"}, value="both", width=160)
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
            description="Start the track from the domain-wide maximum of the (smoothed) "
                        "field at the shown time, then follow it forward and backward")
        self.trk_stop_btn = pn.widgets.Button(name="Stop", button_type="danger",
                                              button_style="outline", height=32,
                                              margin=(5, 4, 8, 10), disabled=True)
        self.trk_clear = pn.widgets.Button(name="Clear track", button_type="light",
                                           button_style="outline", height=32,
                                           margin=(5, 4, 8, 4))
        parts = run.path.rstrip("/").split("/")[-2:]
        self.trk_path = pn.widgets.TextInput(
            name="Save to (on the server; .csv = comma separated, .txt = aligned columns)",
            value=os.path.join(os.getcwd(), "_".join(parts) + "_meso_track.csv"),
            sizing_mode="stretch_width", min_width=300)
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
        self.trk_table = pn.widgets.Tabulator(
            pd_empty(), disabled=True, show_index=False, theme="midnight", height=260,
            sizing_mode="stretch_width", layout="fit_data_fill", visible=False)

    def _build_series(self):
        """Series tab: one field reduced over a region at every output time."""
        run, F = self.run, self.F
        ztop = float(np.floor(run.z[-1] * 10) / 10)
        first = "thpert" if "thpert" in F else next(iter(F.defs))
        self.ser_field = pn.widgets.Select(name="Field", groups=F.groups(), value=first,
                                           width=230)
        self.ser_vmode = pn.widgets.Select(
            name="Vertical", options={"At a height": "height", "Layer (every level)": "layer"},
            value="height", width=150,
            description="Layer: the reduction is also kept at every model level in the "
                        "layer (time–height plot, sub-layers from the saved file)")
        self.ser_z = pn.widgets.FloatInput(name="Height (km AGL)", value=1.0, step=0.25,
                                           start=0.0, end=ztop, width=110)
        self.ser_z0 = pn.widgets.FloatInput(name="Bottom (km)", value=0.0, step=0.5,
                                            start=0.0, end=ztop, width=90, visible=False)
        self.ser_z1 = pn.widgets.FloatInput(name="Top (km)", value=10.0, step=0.5,
                                            start=0.0, end=ztop, width=90, visible=False)
        self.ser_region = pn.widgets.Select(
            name="Region", options={"Whole domain": "domain", "Current map view": "view",
                                    "3D region box": "box3d", "Around tracked storm": "track"},
            value="domain", width=180)
        self.ser_radius = pn.widgets.FloatInput(name="Radius (km)", value=5.0, step=0.5,
                                                start=0.25, width=90, visible=False)
        self.ser_offx = pn.widgets.FloatInput(
            name="Offset x (km)", value=0.0, step=1.0, width=90, visible=False,
            description="Centre the disc this far from the tracked storm (e.g. in the "
                        "inflow); x, y on the model grid")
        self.ser_offy = pn.widgets.FloatInput(name="Offset y (km)", value=0.0, step=1.0,
                                              width=90, visible=False)
        self.ser_reduce = pn.widgets.Select(
            name="Reduce", options={"Minimum": "min", "Maximum": "max", "Mean": "mean",
                                    "Percentile": "pct"}, value="min", width=120)
        self.ser_pct = pn.widgets.FloatInput(name="Percentile", value=99.0, step=0.5,
                                             start=0.0, end=100.0, width=90, visible=False)
        self.ser_go = pn.widgets.Button(name="Compute", button_type="primary", icon="chart-line",
                                        height=32, margin=(5, 4, 8, 10))
        self.ser_stop = pn.widgets.Button(name="Stop", button_type="danger",
                                          button_style="outline", height=32,
                                          margin=(5, 4, 8, 4), disabled=True)
        self.ser_status = _html(
            '<div class="cv-empty">Choose a field, height or layer, region and reduction, '
            'then <b>Compute</b>: every output time is processed (a few seconds for one '
            'height, about a minute for a deep layer). Results are cached, so the same '
            'recipe comes back instantly in a later session.</div>',
            sizing_mode="stretch_width")

        # computed series of this session: key -> dict(ds, recipe, color)
        self.series, self._ser_n = {}, 0
        self.ser_pick = pn.widgets.Select(name="Series", options={}, width=420,
                                          description="The series used by the time–height "
                                                      "view, Save and Remove")
        self.ser_view = pn.widgets.RadioButtonGroup(
            options={"Time series": "line", "Time–height": "th"}, value="line",
            button_type="primary", button_style="outline", height=32, margin=(18, 4, 4, 10),
            disabled=True)
        self.ser_remove = pn.widgets.Button(name="Remove", button_type="light",
                                            button_style="outline", height=32,
                                            margin=(18, 4, 4, 4), disabled=True)

        fig = figure(sizing_mode="stretch_width", height=300, tools="pan,wheel_zoom,reset,save",
                     x_axis_label="time (min)", y_axis_label="")
        style_fig(fig)
        fig.toolbar.autohide = True
        fig.add_tools(HoverTool(tooltips=[("", "@name"), ("t", "@hms"),
                                          ("value", "@value{0.0000}"), ("at", "@where")]))
        self.ser_now = Span(location=run.times[self.t] / 60.0, dimension="height",
                            line_color="#fbbf24", line_width=1.5, line_alpha=0.7)
        fig.add_layout(self.ser_now)
        fig.on_event(Tap, self._on_ser_tap)
        self.ser_fig = fig
        self._ser_glyphs = []  # renderers of the line view

        th = figure(sizing_mode="stretch_width", height=300, tools="pan,wheel_zoom,reset,save",
                    x_axis_label="time (min)", y_axis_label="height (km AGL)")
        style_fig(th)
        th.toolbar.autohide = True
        self.ser_th_src = ColumnDataSource(dict(l=[], r=[], b=[], t=[], v=[], hms=[], z=[]))
        self.ser_th_map = LinearColorMapper(palette=palette("viridis"), low=0, high=1)
        q = th.quad(left="l", right="r", bottom="b", top="t", source=self.ser_th_src,
                    fill_color=transform("v", self.ser_th_map),
                    line_color=transform("v", self.ser_th_map), line_width=0.6)  # no seams
        th.add_tools(HoverTool(renderers=[q], tooltips=[("t", "@hms"), ("z", "@z{0.00} km"),
                                                       ("value", "@v{0.0000}")]))
        self.ser_th_bar = ColorBar(color_mapper=self.ser_th_map, width=12,
                                   background_fill_color=BG, major_label_text_color=MUTED)
        th.add_layout(self.ser_th_bar, "right")
        self.ser_th_now = Span(location=run.times[self.t] / 60.0, dimension="height",
                               line_color="#fbbf24", line_width=1.5, line_alpha=0.7)
        th.add_layout(self.ser_th_now)
        th.on_event(Tap, self._on_ser_tap)
        self.ser_thfig = th
        self.ser_plot = pn.pane.Bokeh(fig, sizing_mode="stretch_width")  # or the th view

        parts = run.path.rstrip("/").split("/")[-2:]
        self._ser_prefix = os.path.join(os.getcwd(), "_".join(parts))
        self.ser_path = pn.widgets.TextInput(
            name="Save to / load from (on the server)", value=self._ser_prefix + "_series.nc",
            sizing_mode="stretch_width", min_width=300)
        self.ser_fmt = pn.widgets.Select(
            name="Format", options={"netCDF (.nc)": ".nc", "CSV (.csv)": ".csv",
                                    "Text columns (.txt)": ".txt", "Pickle (.pkl)": ".pkl"},
            value=".nc", width=150,
            description="netCDF keeps everything, including per-level values of a layer; "
                        "CSV / text hold the series only; pickle loads into pandas")
        self.ser_save = pn.widgets.Button(name="Save", button_type="primary", height=32,
                                          margin=(5, 4, 8, 10), disabled=True)
        self.ser_dl = pn.widgets.FileDownload(
            callback=self._ser_download, filename="series.nc", label="Download",
            button_type="primary", button_style="outline", height=32, margin=(5, 4, 8, 4),
            disabled=True)
        self.ser_load = pn.widgets.Button(
            name="Load", button_type="primary", button_style="outline", height=32,
            margin=(5, 4, 8, 4), description="Read a saved series (.nc, .csv, .txt, .pkl) "
                                             "from the path")
        self.ser_file_msg = _html(sizing_mode="stretch_width")

        def vis(*e):
            d = F[self.ser_field.value]
            two = d.ndim == 2
            lay = self.ser_vmode.value == "layer"
            self.ser_vmode.visible = not two
            self.ser_z.visible = not two and not lay
            self.ser_z0.visible = self.ser_z1.visible = not two and lay
            trkr = self.ser_region.value == "track"
            self.ser_radius.visible = self.ser_offx.visible = self.ser_offy.visible = trkr
            self.ser_pct.visible = self.ser_reduce.value == "pct"

        for w in (self.ser_field, self.ser_vmode, self.ser_region, self.ser_reduce):
            w.param.watch(vis, "value")
        self.ser_go.on_click(self._on_ser_compute)
        self.ser_stop.on_click(lambda e: self._cancel_series())
        self.ser_pick.param.watch(lambda e: self._ser_select(), "value")
        self.ser_view.param.watch(lambda e: self._ser_draw(), "value")
        self.ser_remove.on_click(self._on_ser_remove)
        self.ser_fmt.param.watch(self._on_ser_fmt, "value")
        self.ser_path.param.watch(
            lambda e: setattr(self.ser_dl, "filename", os.path.basename(e.new) or "series"),
            "value")
        self.ser_save.on_click(self._on_ser_save)
        self.ser_load.on_click(self._on_ser_load)

    def _build_panels(self):
        F, run = self.F, self.run
        g3 = F.groups(ndim=3)
        self.skew_png = self._zoom_image("skewt_hodograph.svg",
                                         styles={"flex": "1 1 640px", "min-width": "0"})
        self.prof_png = self._zoom_image("profiles.svg")
        self.params = ParamTable(stylesheets=[CSS], sizing_mode="stretch_width",
                                 styles={"flex": "1 1 380px", "min-width": "0"})
        self.snd_head = _html(
            '<div class="cv-empty">Click anywhere on the map to drop a sounding. '
            '<kbd>Shift</kbd>-click to add up to four for comparison.</div>',
            sizing_mode="stretch_width")
        self.snd_msg = _html(sizing_mode="stretch_width")
        self.snd_tabs = pn.Tabs(sizing_mode="stretch_width", dynamic=False, visible=False)
        self._snd_tab_names = []
        self.prof_row = pn.Row(
            _html('<div class="cv-hint" style="margin:8px 0 0 4px">Profile panels below '
                  'go up to</div>'), self.prof_top,
            _html('<div class="cv-hint" style="margin:8px 0 0 0">km AGL</div>'),
            visible=False, margin=(4, 0, 0, 0))
        # skew-T and table side by side when there is room (expanded view)
        self.snd_col = pn.Column(
            self.snd_head, self.snd_tabs,
            pn.FlexBox(self.skew_png, self.params, flex_wrap="wrap", gap="4px 16px",
                       align_items="flex-start", sizing_mode="stretch_width"),
            self.prof_row, self.prof_png, sizing_mode="stretch_width")

        # ---- 3D
        iso_defaults = [("dbz", 30.0, "#7dd3fc", 0.22, True),
                        ("winterp", 10.0, "#f97316", 0.85, True),
                        ("winterp", -5.0, "#3b82f6", 0.7, False),
                        ("zvort", 0.05, "#e11d48", 0.95, False)]
        first3d = next(iter(next(iter(g3.values())).values()))
        self.isos = []
        for var, val, col, op, on in iso_defaults:
            if var not in F:
                var, on = first3d, False
            self.isos.append(dict(
                on=pn.widgets.Checkbox(value=on, width=24, margin=(18, 4, 0, 4)),
                var=pn.widgets.Select(name="Field", groups=g3, value=var, width=230),
                val=pn.widgets.FloatInput(name="Value", value=val, width=90),
                color=pn.widgets.ColorPicker(name="Color", value=col, width=60),
                op=pn.widgets.FloatSlider(name="Opacity", start=0.05, end=1.0, step=0.05,
                                          value=op, width=130),
            ))
        ztop = float(np.floor(run.z[-1]))
        self.v3_ztop = pn.widgets.FloatSlider(name="Top (km)", start=2, end=ztop, step=0.5,
                                              value=min(15.0, ztop), width=150)
        self.v3_exag = pn.widgets.FloatSlider(name="Vertical exaggeration", start=1, end=6,
                                              step=0.5, value=2, width=150)
        self.v3_smooth = pn.widgets.FloatSlider(name="Smoothing σ", start=0, end=3,
                                                step=0.25, value=0.75, width=150)
        self.v3_res = pn.widgets.Select(name="Resolution",
                                        options={"Auto": 0, "Full": 1, "1/2": 2, "1/3": 3,
                                                 "1/4": 4}, value=0, width=100)
        self.v3_ground = pn.widgets.Checkbox(name="Composite reflectivity floor",
                                             value="cref" in F, margin=(5, 10, 14, 10))
        self.v3_follow = pn.widgets.Checkbox(name="Re-render when time changes", value=False,
                                             margin=(5, 10, 14, 10))
        self.v3_cam = pn.widgets.Select(
            name="View from", options={"Southwest (default)": "oblique", "Above": "top",
                                       "South": "south", "North": "north", "West": "west",
                                       "East": "east"}, value="oblique", width=170)
        self.v3_drag = pn.widgets.Select(
            name="Mouse drag", options={"Rotate": "turntable", "Free rotate": "orbit",
                                        "Move (pan)": "pan", "Zoom": "zoom"},
            value="turntable", width=130)
        self._cam_rev = 0

        # surface wind vectors
        self.sv_on = pn.widgets.Checkbox(value=False, width=18, margin=(14, 0, 0, 8))
        self.sv_lvl = pn.widgets.FloatSlider(name="Height (km AGL; 0 = lowest level)",
                                             start=0.0, end=3.0, step=0.05, value=0.0,
                                             width=210)
        self.sv_frame = pn.widgets.Select(name="Frame", options=FRAMES,
                                          value=self.vec_frame.value, width=150)
        self.sv_density = pn.widgets.IntSlider(name="Arrows across region", start=6, end=40,
                                               value=16, width=170)
        self.sv_ref = pn.widgets.FloatInput(name="Ref. speed (m/s)", value=20.0, width=110)
        self.sv_color = pn.widgets.ColorPicker(name="Color", value="#f8fafc", width=60)

        # streamlines
        self.st_on = pn.widgets.Checkbox(value=False, width=18, margin=(14, 0, 0, 8))
        self.st_z = pn.widgets.FloatSlider(name="Seed height (km AGL)", start=0.0,
                                           end=min(10.0, ztop), step=0.1, value=0.5,
                                           width=180)
        self.st_n = pn.widgets.IntSlider(name="Seeds across (n × n)", start=3, end=30,
                                         value=12, width=170)
        self.st_len = pn.widgets.FloatSlider(name="Max length (km)", start=5, end=150,
                                             step=5, value=40, width=170)
        self.st_dir = pn.widgets.Select(name="Direction",
                                        options={"Forward": "forward", "Backward": "backward",
                                                 "Both": "both"}, value="forward", width=120)
        self.st_frame = pn.widgets.Select(name="Frame", options=FRAMES, value="storm",
                                          width=150)
        self.st_color = pn.widgets.Select(name="Color by",
                                          options={"Height": "z", "Vertical velocity": "w"},
                                          value="z", width=150)

        self.v3_pick = pn.widgets.Button(name="Pick region on map", button_type="default",
                                         button_style="outline", height=34, margin=(5, 3))
        self.v3_view = pn.widgets.Button(name="Use map view", button_type="default",
                                         button_style="outline", height=34, margin=(5, 3))
        self.v3_render = pn.widgets.Button(name="Render 3D", button_type="primary",
                                           icon="cube", height=34, margin=(5, 3))
        self.v3_region = _html()
        self.v3_status = _html('<div class="cv-hint">Pick a region (button above, or '
                               '<b>3D region</b> click mode on the map) or use the current '
                               'map view, then <b>Render 3D</b>. Keep it storm-scale '
                               '(≲ 50 km) for full resolution.</div>')
        self.plot3d = pn.pane.Plotly(None, sizing_mode="stretch_both", min_height=400,
                                     config={"displaylogo": False, "responsive": True},
                                     visible=False)
        self._build_streamline_card()

        # ---- analysis panel (right of the map)
        snd_set = pn.FlexBox(self.parcel, self.wunits, self.storm, self.storm_u,
                             self.storm_v, self.avg, self.base_on, self.follow,
                             self.storm_follow, flex_wrap="wrap", align_items="flex-end",
                             gap="0 4px", sizing_mode="stretch_width",
                             styles={"border-top": f"1px solid {GRID}"})
        ps = self.ps
        snd_look = pn.FlexBox(*[ps[k] for k in ("t", "td", "parcel", "base", "lw", "parcel_lw",
                                                "hodo_lw", "prof_lw", "ptop", "tmin", "tmax",
                                                "ring", "htop", "shade", "barbs", "guides")],
                              self.ps_reset, flex_wrap="wrap", align_items="flex-end",
                              gap="0 6px", sizing_mode="stretch_width",
                              styles={"border-top": f"1px solid {GRID}"})
        look_btn = _settings_toggle(snd_look)
        look_btn.name = "🎨 Plot style"
        snd_opts = pn.Column(
            pn.FlexBox(self.mean_btn, self.pin_btn, self.snd_clear, self.compare,
                       _settings_toggle(snd_set), look_btn, flex_wrap="wrap",
                       align_items="center", gap="0 4px", sizing_mode="stretch_width"),
            snd_set, snd_look, sizing_mode="stretch_width", margin=0)
        d = self.xs_drawer = Drawer()
        xs_style = d.add("fill", "Fill style", self.xs_cmap, self.xs_rev, self.xs_auto,
                         self.xs_min, self.xs_max)
        xs_cont = d.add("cont", "Contours", self.xs_cont, self.xs_levels, self.xs_ccolor,
                        self.xs_cwidth, self.xs_negdash)
        xs_vec = _pill(self.xs_vecs, d.add("vec", "Winds", self.xs_vframe, self.xs_vdensity,
                                           self.xs_vref, self.xs_vcolor,
                                           _html('<div class="cv-hint" style="margin:0 0 '
                                                 '12px">In-plane wind (along-section u, w)'
                                                 '</div>')))
        for b, _ in d.items.values():
            b.param.update(height=32, margin=(18, 2, 4, 2), button_type="light")
        xs = pn.Column(
            pn.FlexBox(self.xs_fill, self.xs_ztop, xs_style, xs_cont, xs_vec,
                       flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                       sizing_mode="stretch_width"), d.panel,
            self.xs_status, self.xs_pd_btn,
            pn.pane.Bokeh(self.xs_fig, sizing_mode="stretch_width"),
            sizing_mode="stretch_width")
        trk_set = pn.FlexBox(self.trk_metric, self.trk_z, self.trk_smooth, self.trk_kernel,
                             self.trk_radius, self.trk_stop, self.trk_dir, self.trk_snap,
                             self.trk_near, self.trk_whole,
                             flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                             sizing_mode="stretch_width",
                             styles={"border-top": f"1px solid {GRID}"})
        self.tabs = pn.Tabs(
            ("Sounding", pn.Column(snd_opts, self.snd_msg, self.snd_col, scroll=True,
                                   sizing_mode="stretch_both")),
            ("Cross-section", pn.Column(xs, scroll=True, sizing_mode="stretch_both")),
            ("Track", pn.Column(
                pn.FlexBox(self.trk_how, self.trk_find, self.trk_stop_btn, self.trk_del,
                           self.trk_clear,
                           _settings_toggle(trk_set), self.trk_advance, flex_wrap="wrap",
                           align_items="center", gap="0 4px", sizing_mode="stretch_width"),
                trk_set,
                self.trk_status,
                pn.pane.Bokeh(self.trk_fig, sizing_mode="stretch_width"),
                pn.FlexBox(self.trk_path, self.trk_save, self.trk_dl, self.trk_load,
                           flex_wrap="wrap",
                           align_items="flex-end", gap="0 4px", sizing_mode="stretch_width"),
                self.trk_table, scroll=True, sizing_mode="stretch_both")),
            ("Series", pn.Column(
                pn.FlexBox(self.ser_field, self.ser_vmode, self.ser_z, self.ser_z0,
                           self.ser_z1, self.ser_region, self.ser_radius, self.ser_offx,
                           self.ser_offy, self.ser_reduce, self.ser_pct, self.ser_go,
                           self.ser_stop, flex_wrap="wrap", align_items="flex-end",
                           gap="0 4px", sizing_mode="stretch_width"),
                self.ser_status,
                pn.FlexBox(self.ser_pick, self.ser_view, self.ser_remove, flex_wrap="wrap",
                           align_items="flex-end", gap="0 4px", sizing_mode="stretch_width"),
                self.ser_plot,
                pn.FlexBox(self.ser_path, self.ser_fmt, self.ser_save, self.ser_dl,
                           self.ser_load, flex_wrap="wrap", align_items="flex-end",
                           gap="0 4px", sizing_mode="stretch_width"),
                self.ser_file_msg, scroll=True, sizing_mode="stretch_both")),
            sizing_mode="stretch_both", dynamic=False,
            styles={"flex": "1 1 48%", "min-width": "0"})

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
        fig = figure(sizing_mode="stretch_width", height=210, tools="pan,wheel_zoom,"
                     "box_zoom,reset,save", x_axis_label="Distance from seed (km)",
                     y_axis_label="")
        style_fig(fig)
        fig.toolbar.autohide = True
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
            pn.Row(self.sl_info, self.sl_field, self.sl_clear, margin=0,
                   sizing_mode="stretch_width"),
            pn.pane.Bokeh(fig, sizing_mode="stretch_width"),
            visible=False, margin=0,
            styles={"position": "absolute", "right": "12px", "bottom": "12px",
                    "width": "min(600px, 46vw)", "z-index": "25", "padding": "6px 8px",
                    "background": "rgba(17,23,35,0.94)", "border": f"1px solid {GRID}",
                    "border-radius": "10px", "box-shadow": "0 6px 20px rgba(0,0,0,.45)"})
        self._s3 = None      # last 3D scene: t, streamlines, frame offset
        self._sl_seed = None  # seed of the selected streamline (kept across re-renders)
        self._sl_line = None

    def _top_bar(self):
        """Run, time and workspace pills floating across the top of the window."""
        self.ws_group = _group(self.workspace)  # Map | 3D | Figure
        return pn.Column(
            _bar(self.ws_group,
                 _group(self.t_prev, self.t_play, self.t_next, self.t_speed, self.tslider,
                        self.time_html),
                 self.mode_group, _group(self.run_btn)),
            styles=dict(OVERLAY, **{"z-index": "40"}), margin=0)

    def _map_toolbar(self):
        d = self.map_drawer = Drawer()
        style = d.add("style", "Style", self.fill_style, self.fill_cmap, self.fill_rev,
                      self.fill_auto, self.fill_min, self.fill_max, self.fill_nlev,
                      self.fill_alpha)
        ovb = []
        for n, o in enumerate(self.ovs):
            ovb.append(_pill(o["on"], d.add(f"ov{n}", f"Contours {'AB'[n]}", o["var"],
                                            o["mode"], o["level"], o["levels"], o["color"],
                                            o["width"], o["negdash"])))
        vec = _pill(self.vec_on, d.add("vec", "Winds", self.vec_style, self.vec_lvl,
                                       self.vec_frame, self.vec_density, self.vec_ref,
                                       self.vec_color))
        for b, _ in d.items.values():
            b.param.update(height=32, margin=(4, 2), button_type="light")
        d.panel.styles = dict(d.panel.styles, **{"pointer-events": "auto",
                                                 "background": "rgba(17,23,35,0.95)",
                                                 "box-shadow": "0 6px 20px rgba(0,0,0,.45)"})
        bar = _bar(_group(self.fill_var, self.fill_mode, self.fill_lvl),
                   _group(style, *ovb, vec))
        self.mode_group = _group(*self.mode.btns.values(), self.clear_pts, self.panel_btn,
                                 self.full_btn)
        return pn.Column(bar, d.panel, styles=OVERLAY, margin=0)

    def _3d_toolbar(self):
        d = self.v3_drawer = Drawer()
        iso_rows = [pn.Row(o["on"], o["var"], o["val"], o["color"], o["op"], margin=0)
                    for o in self.isos]
        iso = d.add("iso", "Isosurfaces", pn.Column(*iso_rows, margin=0))
        sv = _pill(self.sv_on, d.add("sv", "Surface winds", self.sv_lvl, self.sv_frame,
                                     self.sv_density, self.sv_ref, self.sv_color,
                                     _html('<div class="cv-hint" style="margin:0 0 12px">'
                                           'Storm-relative uses the sounding panel’s '
                                           'storm motion.</div>')))
        st = _pill(self.st_on, d.add("st", "Streamlines", self.st_z, self.st_n, self.st_len,
                                     self.st_dir, self.st_frame, self.st_color,
                                     _html('<div class="cv-hint" style="margin:0 0 12px">'
                                           'Instantaneous streamlines seeded on an n×n grid '
                                           'over the region.</div>')))
        scene = d.add("scene", "Scene", self.v3_cam, self.v3_drag, self.v3_ztop, self.v3_exag,
                      self.v3_smooth, self.v3_res, self.v3_ground, self.v3_follow,
                      _html('<div class="cv-hint" style="margin:0 0 12px">Drag: rotate · '
                            'right-drag: move (or set Mouse drag to Move) · '
                            'scroll: zoom · double-click: reset</div>'))
        for b, _ in d.items.values():
            b.param.update(height=32, margin=(4, 2), button_type="light")
        for b in (self.v3_pick, self.v3_view, self.v3_render):
            b.param.update(height=32, margin=(4, 2))
        d.panel.styles = dict(d.panel.styles, **{"pointer-events": "auto",
                                                 "background": "rgba(17,23,35,0.95)",
                                                 "box-shadow": "0 6px 20px rgba(0,0,0,.45)"})
        bar = _bar(_group(iso, sv, st, scene),
                   _group(self.v3_region, self.v3_pick, self.v3_view, self.v3_render))
        return pn.Column(bar, d.panel, styles=OVERLAY, margin=0)

    def main(self):
        floor = {"position": "absolute", "left": "70px", "bottom": "56px", "z-index": "20",
                 "pointer-events": "none", "background": "rgba(11,15,23,0.75)",
                 "border-radius": "8px", "padding": "0 8px"}
        caption = pn.Column(self.map_title, self.hint, self.status, self.pd_row, styles=floor,
                            margin=0)
        self.map_area = map_area = pn.Column(
            self.map_bar, pn.pane.Bokeh(self.fig, sizing_mode="stretch_both"), caption,
            sizing_mode="stretch_both",
            styles={"position": "relative", "flex": "1 1 55%", "min-width": "0"})
        self.tabs.margin = (0, 8, 0, 4)
        below = {"margin-top": "52px", "height": "calc(100vh - 52px)"}
        self.map_ws = pn.Row(map_area, self.tabs, sizing_mode="stretch_width", margin=0,
                             styles=below)
        self.plot3d.margin = 0
        self.v3_ws = pn.Column(
            self.v3_bar, self.plot3d,
            pn.Column(self.v3_status, styles=dict(floor, left="12px", bottom="12px"),
                      margin=0),
            self.sl_card,
            sizing_mode="stretch_width", visible=False, margin=0,
            styles=dict(below, position="relative"))
        err = _html(f'<div class="cv-status" style="color:#f87171;padding:4px 8px">'
                    f'{self.error}</div>') if self.error else None
        objs = [o for o in (err,) if o is not None]
        self.fig_ws = pn.Column(self.figed.panel, sizing_mode="stretch_width", visible=False,
                                margin=0, styles=dict(below, position="relative"))
        return pn.Column(self._top_bar(), *objs, self.map_ws, self.v3_ws, self.fig_ws,
                         self.rp_modal,
                         margin=0, styles={"position": "fixed", "top": "0", "left": "0",
                                           "width": "100vw", "height": "100vh"})

    # ================================================================ wiring
    def _wire(self):
        rm = lambda *e: self.request_map()  # noqa: E731
        self.tslider.param.watch(self._on_time, "value")
        self.tslider.param.watch(lambda e: self._refresh_panels(), "value_throttled")
        self.t_play.on_click(self._on_play)
        self.t_prev.on_click(lambda e: self._step(-1))
        self.t_next.on_click(lambda e: self._step(1))
        self.t_speed.param.watch(self._on_speed, "value")
        self.mode.watch(self._on_mode)
        self.fill_var.param.watch(self._on_fill_var, "value")
        for w in (self.fill_mode, self.fill_style, self.fill_cmap, self.fill_rev,
                  self.fill_nlev, self.vec_on, self.vec_frame, self.vec_color, self.vec_ref,
                  self.vec_style):
            w.param.watch(rm, "value")

        def vec_vis(*e):
            st = self.vec_style.value == "streamlines"
            self.vec_density.name = "Streamline density" if st else "Arrows across view"
            self.vec_ref.visible = not st

        self.vec_style.param.watch(vec_vis, "value")
        for w in (self.fill_lvl, self.fill_alpha, self.vec_lvl, self.vec_density):
            w.param.watch(rm, "value_throttled")
        self.fill_auto.param.watch(self._on_fill_auto, "value")
        for w in (self.fill_min, self.fill_max):
            w.param.watch(lambda e: None if self.fill_auto.value else self.request_map(),
                          "value")
        for o in self.ovs:
            for k in ("on", "var", "mode", "levels", "color", "negdash"):
                o[k].param.watch(rm, "value")
            for k in ("level", "width"):
                o[k].param.watch(rm, "value_throttled")
        self.storm.param.watch(self._on_storm, "value")
        rs = lambda *e: self.request_soundings()  # noqa: E731
        self.mean_btn.on_click(lambda e: self._add_mean())
        self.pin_btn.on_click(lambda e: self._pin_time())
        self.snd_clear.on_click(self._on_clear_soundings)
        for w in (self.storm_u, self.storm_v, self.parcel, self.wunits, self.avg,
                  self.prof_top, self.base_on, self.compare):
            w.param.watch(rs, "value", precedence=1)  # after the zoom resets below
        rl = lambda *e: self._restyle()  # noqa: E731
        for k, w in self.ps.items():
            w.param.watch(rl, "value_throttled" if isinstance(w, pn.widgets.FloatSlider)
                          else "value")
        self.ps_reset.on_click(self._on_style_reset)

        def unzoom(*keys):
            def f(*e):
                for k in keys:
                    self.snd_lim.pop(k, None)
            return f
        # zoom limits in wind units / below the profile top no longer fit
        # (before the sounding request those changes also trigger)
        self.wunits.param.watch(unzoom("hodo", "prof_x"), "value")
        self.prof_top.param.watch(unzoom("prof_z", "prof_x"), "value")
        rx = lambda *e: self.request_xsec()  # noqa: E731
        for w in (self.xs_cont, self.xs_levels, self.xs_vecs, self.xs_cmap, self.xs_rev,
                  self.xs_ccolor, self.xs_negdash, self.xs_vframe, self.xs_vref,
                  self.xs_vcolor):
            w.param.watch(rx, "value")
        for w in (self.xs_cwidth, self.xs_vdensity):
            w.param.watch(rx, "value_throttled")
        for w in (self.xs_min, self.xs_max):
            w.param.watch(lambda e: None if self.xs_auto.value else self.request_xsec(),
                          "value")
        self.xs_fill.param.watch(self._on_xs_fill, "value")
        self.xs_auto.param.watch(self._on_xs_auto, "value")
        self.xs_ztop.param.watch(rx, "value_throttled")
        self.v3_view.on_click(self._on_use_view)
        self.v3_render.on_click(lambda e: self.request_3d())
        self.v3_pick.on_click(self._on_pick_region)
        self.workspace.param.watch(self._on_workspace, "value")
        self.panel_btn.on_click(lambda e: self._show_panel(not self.tabs.visible))
        self.full_btn.on_click(lambda e: self._set_full(not self.full))
        # once a scene is shown or being rendered, 3D settings re-render it
        r3 = lambda *e: self.request_3d() if self.gen["3d"] else None  # noqa: E731
        w3 = [self.v3_ground, self.v3_res, self.sv_on, self.sv_frame, self.sv_ref,
              self.sv_color, self.st_on, self.st_dir, self.st_frame, self.st_color]
        for o in self.isos:
            w3 += [o["on"], o["var"], o["val"], o["color"]]
        for w in w3:
            w.param.watch(r3, "value")
        for w in [self.v3_ztop, self.v3_exag, self.v3_smooth, self.sv_lvl, self.sv_density,
                  self.st_z, self.st_n, self.st_len] + [o["op"] for o in self.isos]:
            w.param.watch(r3, "value_throttled")
        for o in self.isos:
            o["on"].param.watch(lambda e: self._update_3d_labels(), "value")
        self.v3_cam.param.watch(self._on_camera, "value")
        self.v3_drag.param.watch(self._on_drag, "value")
        self.plot3d.param.watch(self._on_3d_click, "click_data")
        self.sl_field.param.watch(lambda e: self._sample_line(), "value")
        self.sl_clear.on_click(lambda e: self._select_line(None))
        self.trk_metric.param.watch(self._on_trk_metric, "value")
        self.trk_whole.param.watch(self._on_trk_whole, "value")
        self.trk_find.on_click(lambda e: (self._show_panel(True, 2),
                                          self.request_track(None, None)))
        self.trk_stop_btn.on_click(lambda e: self._cancel_track())
        self.trk_clear.on_click(self._on_clear_track)
        self.trk_how.param.watch(self._on_trk_how, "value")
        self.trk_del.on_click(self._on_delete_fix)
        self.trk_load.on_click(self._on_load_track)
        self.trk_save.on_click(self._on_save_track)
        self.trk_path.param.watch(self._on_trk_path, "value")
        self.storm_follow.param.watch(lambda e: self._draw_points(), "value")
        self._on_trk_path(None)
        self._trk_preset(self.trk_metric.value)
        self._update_track_view()
        self._update_3d_labels()
        self._update_region_html()
        self.clear_btn.on_click(self._on_clear_cache)
        self.pd_btn.on_click(self._on_pd_compute)
        self.pd_write.param.watch(lambda e: self.request_map(), "value")  # relabel
        self.xs_pd_btn.on_click(self._on_pd_compute)
        self.clear_pts.on_click(self._on_clear_points)
        self._on_mode(None, init=True)
        self._show_panel(False)  # the map gets the full width until a panel is needed
        self._update_time_html()
        if self.doc is not None:
            pn.state.add_periodic_callback(self._update_cache_html, period=3000)
        self._update_cache_html()

    def close(self):
        """The browser session ended: stop its jobs and free its threads and data
        (otherwise every page load leaves a thread and ~20 MB behind)."""
        for k in self.gen:
            self.gen[k] += 1  # running jobs see a newer generation and stop
        if self._play_cb is not None:
            self._play_cb.stop()
        for p in self.pools.values():
            p.shutdown(wait=False, cancel_futures=True)
        self._figs, self.results, self._snd_last, self._s3 = {}, [], None, None
        self._closed = True

    _closed = False

    def _schedule(self, fn):
        if self._closed:  # session gone: late results are dropped
            return
        if self.doc is not None:
            self.doc.add_next_tick_callback(fn)
        else:  # e.g. tests without a server
            fn()

    def _set_status(self, html):
        self.status.object = f'<div class="cv-status">{html}</div>'

    def _status_async(self, html):
        self._schedule(partial(self._set_status, html))

    def _update_time_html(self):
        r = self.run
        self.time_html.object = (f'<div class="cv-time" style="font-size:17px;margin-top:2px"'
                                 f' title="t = {r.times[self.t]:.0f} s">{r.time_label(self.t)}'
                                 f' <small>{self.t + 1}/{len(r.times)}</small></div>')

    def _update_cache_html(self):
        used, cap, n = self.run.cache_info()
        self.cache_html.object = (f'<div class="cv-status">3D cache: {used:.1f} / {cap:.0f} GB '
                                  f'({n} fields) · {self.run.workers} reader'
                                  f'{"s" if self.run.workers > 1 else ""}</div>')

    # ================================================================ events
    def _on_time(self, ev):
        """Every time change (drag, step, playback) updates the map."""
        self._update_time_html()
        self._update_track_now()
        self.ser_now.location = self.ser_th_now.location = self.run.times[self.t] / 60.0
        self._draw_points()
        self.request_map()

    def _refresh_panels(self):
        """The slower panels follow time only once it settles (slider released,
        step button, or playback paused)."""
        if self.playing:
            return
        if self.points and self.follow.value:
            self.request_soundings()
        if len(self.xs_pts) == 2 and self.tabs.visible and self.tabs.active == 1:
            self.request_xsec()
        if self.v3_follow.value and self.plot3d.visible and self.workspace.value == "3D":
            self.request_3d()

    def _step(self, d):
        if self.playing:
            self._on_play(None)
        self.tslider.value = (self.t + d) % (self.tslider.end + 1)
        self._refresh_panels()

    def _tick(self):
        self.tslider.value = (self.t + 1) % (self.tslider.end + 1)

    def _on_play(self, ev):
        self.playing = not self.playing
        self.t_play.icon = "player-pause" if self.playing else "player-play"
        if self.playing:
            if self._play_cb is None:
                self._play_cb = pn.state.add_periodic_callback(
                    self._tick, period=self.t_speed.value, start=False)
            self._play_cb.start()
        else:
            if self._play_cb is not None:
                self._play_cb.stop()
            self._refresh_panels()

    def _on_speed(self, ev):
        if self._play_cb is not None:
            self._play_cb.period = ev.new

    def _on_mode(self, mode, init=False):
        hints = {
            None: "Pick a click mode (Sounding, Cross-section, 3D region) to query the map",
            "Sounding": "Click: sounding at a point · <kbd>Shift</kbd>-click: add a point "
                        "(up to 4)",
            "Area sounding": "Drag a box: sounding averaged over it · <kbd>Shift</kbd>-drag: "
                             "add a box (up to 4)",
            "Cross-section": "Click two points (A, then B) to draw a vertical section",
            "3D region": "Drag a box to choose the 3D region; it renders in the 3D view",
            "Track": "Auto-track: click the meso to follow it through time; click near the "
                     "track at another time to correct it · Place by hand: each click sets "
                     "the fix at the shown time",
        }
        self.hint.object = f'<div class="cv-hint">{hints[mode]}</div>'
        self.fig.toolbar.active_drag = self.bsel if mode in ("3D region", "Area sounding") \
            else self.pan
        tabs = {"Sounding": 0, "Area sounding": 0, "Cross-section": 1, "Track": 2}
        if not init and mode in tabs:
            self._show_panel(True, tabs[mode])

    def _zoom_image(self, filename, **kw):
        z = ZoomImage(filename=filename, interactive=self.full, sizing_mode="stretch_width",
                      visible=kw.pop("visible", False), **kw)
        z.param.watch(lambda e: self._set_full(True), "clicks")  # click: expand
        z.param.watch(partial(self._on_zoom_box, z), "box")
        z.param.watch(partial(self._on_zoom_pan, z), "pan")
        z.param.watch(lambda e: self._on_zoom_out(z), "zoom_out")
        z.param.watch(lambda e: self._on_zoom_reset(z), "resets")
        return z

    def _zoom_images(self):
        return [self.skew_png, self.prof_png] + [
            z for tab in self.snd_tabs for z in tab if isinstance(z, ZoomImage)]

    def _set_full(self, on):
        """Analysis panel over the whole window (map hidden); the sounding graphics
        become zoomable.  The button turns into 'Map' to come back."""
        self.full = on
        self.map_area.visible = not on
        if on:
            self.tabs.visible = True
        self.tabs.styles = dict(self.tabs.styles, flex="1 1 100%" if on else "1 1 48%")
        self.full_btn.param.update(name="Map" if on else "",
                                   icon="arrows-minimize" if on else "arrows-maximize")
        self.panel_btn.disabled = on
        for z in self._zoom_images():
            z.interactive = on

    def _show_panel(self, show, tab=None):
        if not show and self.full:
            self._set_full(False)
        self.tabs.visible = show
        self.panel_btn.icon = ("layout-sidebar-right-collapse" if show
                               else "layout-sidebar-right-expand")
        if tab is not None:
            self.tabs.active = tab

    def _on_workspace(self, ev):
        is3d, isfig = ev.new == "3D", ev.new == "Figure"
        self.v3_ws.visible, self.fig_ws.visible = is3d, isfig
        self.map_ws.visible = not (is3d or isfig)
        self.mode_group.visible = ev.new == "Map"
        if is3d and self.box is None:
            self._update_region_html()
        if isfig:
            self.figed.request(delay=False)

    def _on_pick_region(self, ev):
        self.workspace.value = "Map"
        self.mode.set("3D region")

    def _update_region_html(self):
        if self.box is None:
            txt = "Region: current map view"
            box = self.view
        else:
            box = self.box
            txt = "Region"
        x0, x1, y0, y1 = box
        stride = volume3d.auto_stride(self.run, box, self.v3_ztop.value, 12e6)
        self.v3_region.object = (
            f'<div class="cv-hint" style="margin:0 8px">{txt} {x1 - x0:.1f} × {y1 - y0:.1f} '
            f'km · auto res {"full" if stride == 1 else f"1/{stride}"}</div>')

    def _update_3d_labels(self):
        n = sum(o["on"].value for o in self.isos)
        self.v3_drawer.label("iso", f"Isosurfaces ({n})")

    def _on_fill_var(self, ev):
        d = self.F[ev.new]
        self._hold = True
        try:
            self.fill_cmap.value = d.cmap
            self.fill_rev.value = False
            if d.vrange:
                self.fill_min.value, self.fill_max.value = d.vrange
            self.fill_auto.value = True
            self.fill_mode.disabled = self.fill_lvl.disabled = d.ndim == 2
        finally:
            self._hold = False
        self.request_map()

    def _on_fill_auto(self, ev):
        self.fill_min.disabled = self.fill_max.disabled = ev.new
        if not ev.new and self._last_range is not None:
            self._hold = True
            self.fill_min.value, self.fill_max.value = [round(v, 4) for v in self._last_range]
            self._hold = False
        self.request_map()

    _last_range = None

    _xs_range = None

    def _on_xs_fill(self, ev):
        self._hold_xs = True
        self.xs_cmap.value, self.xs_rev.value, self.xs_auto.value = \
            self.F[ev.new].cmap, False, True
        self._hold_xs = False
        self.request_xsec()

    def _on_xs_auto(self, ev):
        self.xs_min.disabled = self.xs_max.disabled = ev.new
        if not ev.new and self._xs_range is not None:
            self._hold_xs = True
            self.xs_min.value, self.xs_max.value = [round(v, 4) for v in self._xs_range]
            self._hold_xs = False
        self.request_xsec()

    def _on_storm(self, ev):
        custom = ev.new == "custom"
        self.storm_u.visible = self.storm_v.visible = custom
        self.request_soundings()
        if self.vec_on.value and self.vec_frame.value == "storm":
            self.request_map()

    def _on_tap(self, ev):
        x, y = float(ev.x), float(ev.y)
        x0, x1, y0, y1 = self.extent
        v0, v1, w0, w1 = self.view
        if not (x0 <= x <= x1 and y0 <= y <= y1 and min(v0, v1) <= x <= max(v0, v1)
                and min(w0, w1) <= y <= max(w0, w1)):
            return
        mode = self.mode.value
        if mode == "Sounding":
            shift = bool((getattr(ev, "modifiers", None) or {}).get("shift"))
            self._add_sounding(x, y, shift)
        elif mode == "Track":
            self._show_panel(True, 2)
            self.request_track(x, y)
        elif mode == "Cross-section":
            self.xs_pts = [(x, y)] if len(self.xs_pts) != 1 else self.xs_pts + [(x, y)]
            self._draw_xs()
            if len(self.xs_pts) == 2:
                self._show_panel(True, 1)
                self.request_xsec()

    def _add_sounding(self, x, y, add, size=()):
        """A sounding at (x, y) km (a box mean when size = (width, height) km): replaces
        the shown ones, or is added to them (up to 4) when `add`."""
        new = ("pt", (x, y, *size), None)
        meso = trk.position(self.fixes, self.t)
        if self.storm_follow.value:
            if meso is None:
                self._set_status('<span style="color:#fbbf24">No tracked meso at this '
                                 'time; the sounding stays at a fixed point</span>')
            else:
                new = ("trk", (x - meso[0], y - meso[1], *size), None)
        if add and self.points:
            self.points = (self.points + [new])[-4:]
        else:
            self.points = [new]
        self._draw_points()
        self._show_panel(True, 0)
        self.request_soundings()

    def _on_pan_start(self, ev):
        self._drag_shift = bool((getattr(ev, "modifiers", None) or {}).get("shift"))

    def _on_select(self, ev):
        if not getattr(ev, "final", True):
            return
        g = ev.geometry
        if g.get("type") != "rect":
            return
        if self.mode.value == "Area sounding":
            X0, X1, Y0, Y1 = self.extent
            x0, x1 = sorted((max(X0, min(g["x0"], g["x1"])), min(X1, max(g["x0"], g["x1"]))))
            y0, y1 = sorted((max(Y0, min(g["y0"], g["y1"])), min(Y1, max(g["y0"], g["y1"]))))
            if x1 - x0 > 0 and y1 - y0 > 0:
                self._add_sounding((x0 + x1) / 2, (y0 + y1) / 2, self._drag_shift,
                                   (x1 - x0, y1 - y0))
            return
        if self.mode.value != "3D region":
            return
        self._set_box((g["x0"], g["x1"], g["y0"], g["y1"]))
        self.workspace.value = "3D"
        self.request_3d()

    def _on_use_view(self, ev):
        self._set_box(self.view)
        self.request_3d()

    def _set_box(self, box):
        x0, x1, y0, y1 = box
        X0, X1, Y0, Y1 = self.extent
        x0, x1 = sorted((max(X0, min(x0, x1)), min(X1, max(x0, x1))))
        y0, y1 = sorted((max(Y0, min(y0, y1)), min(Y1, max(y0, y1))))
        self.box = (x0, x1, y0, y1)
        self.box_src.data = dict(left=[x0], right=[x1], bottom=[y0], top=[y1])
        self._update_region_html()

    def _on_resized(self, attr, old, new):
        """The browser re-fitted the map to a new plot size: render the new view (the
        range values arrive in the same message, so read them on the next tick)."""
        def update():
            xr, yr = self.fig.x_range, self.fig.y_range
            self.view = (float(xr.start), float(xr.end), float(yr.start), float(yr.end))
            self.request_map()
            if self.box is None:
                self._update_region_html()
        self._schedule(update)

    def _on_ranges(self, ev):
        if None in (ev.x0, ev.x1, ev.y0, ev.y1):
            return
        self.view = (float(ev.x0), float(ev.x1), float(ev.y0), float(ev.y1))
        self.request_map()
        if self.box is None:
            self._update_region_html()

    def _on_clear_cache(self, ev):
        self.run.clear_cache()
        self._update_cache_html()

    def _on_clear_points(self, ev):
        self.points, self.xs_pts, self.box = [], [], None
        self._draw_points()
        self._draw_xs()
        self.box_src.data = dict(left=[], right=[], bottom=[], top=[])
        self.workspace.value = "Map"
        self._update_region_html()
        self.request_soundings()

    def _add_mean(self):
        """Domain-mean sounding that follows the time slider."""
        self.points = [("mean", None, None)]
        self._draw_points()
        self._show_panel(True, 0)
        self.request_soundings()

    def _pin_time(self):
        """Freeze sounding 1 at the current time next to the live one, so moving the
        time slider compares times (the domain mean if nothing is shown yet)."""
        if not self.points:
            self.points = [("mean", None, None)]
        kind, where, _ = self.points[0]
        new = (kind, where, self.t)
        if new not in self.points:
            self.points = self.points[:1] + (self.points[1:] + [new])[-3:]
        self._draw_points()
        self._show_panel(True, 0)
        self.request_soundings()

    def _snd_xy(self, kind, where, t):
        """Map position (km) of a sounding at time index t (None: domain mean, or no
        tracked meso at t)."""
        if kind == "pt":
            return where[:2]
        if kind == "trk":
            meso = trk.position(self.fixes, t)
            return None if meso is None else (meso[0] + where[0], meso[1] + where[1])
        return None

    def _on_clear_soundings(self, ev):
        self.points = []
        self._draw_points()
        self.request_soundings()

    def _draw_points(self):
        pts = [(n, self._snd_xy(kind, where, self.t if tp is None else tp))
               for n, (kind, where, tp) in enumerate(self.points)]
        pts = [(n, xy) for n, xy in pts if xy is not None]
        self.pt_src.data = dict(x=[xy[0] for _, xy in pts], y=[xy[1] for _, xy in pts],
                                color=[POINT_COLORS[n] for n, _ in pts],
                                label=[POINT_LABELS[n] for n, _ in pts])
        boxes = [(n, xy, self.points[n][1][2:]) for n, xy in pts
                 if len(self.points[n][1] or ()) == 4]
        self.pbox_src.data = dict(
            x=[xy[0] for _, xy, _ in boxes], y=[xy[1] for _, xy, _ in boxes],
            w=[wh[0] for _, _, wh in boxes], h=[wh[1] for _, _, wh in boxes],
            color=[POINT_COLORS[n] for n, _, _ in boxes])

    def _draw_xs(self):
        pts = self.xs_pts
        self.xs_pt_src.data = dict(x=[p[0] for p in pts], y=[p[1] for p in pts],
                                   label=["A", "B"][:len(pts)])
        self.xs_line_src.data = dict(x=[p[0] for p in pts], y=[p[1] for p in pts]) \
            if len(pts) == 2 else dict(x=[], y=[])

    # ================================================================ map job
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

    # ================================================================ soundings
    def _base_result(self, spec):
        run = self.run
        key = run.path
        if key not in _BASE_CACHE:
            if not all(run.has(v) for v in BASE_VARS):
                return None
            # horizontally uniform: the domain mean is the column, and mean_profiles
            # reads in the reader processes (a column costs a full read anyway)
            _BASE_CACHE[key] = {v: np.asarray(p, np.float32)
                                for v, p in run.mean_profiles(BASE_VARS, 0).items()}
        b = _BASE_CACHE[key]
        storm, custom = self._item_storm(spec, spec["t"])
        return thermo.analyze(run.z * 1000.0, b["prs0"], b["th0"], b["qv0"],
                              b["u0"] + run.umove, b["v0"] + run.vmove, storm=storm,
                              custom=custom, domain=(run.umove, run.vmove))

    @staticmethod
    def _item_storm(spec, t):
        """(storm, custom) for thermo.analyze; 'track' uses the tracked meso's motion
        at time t, falling back to Bunkers right-mover where there is no track."""
        if spec["storm"] != "track":
            return spec["storm"], spec["custom"]
        m = spec["trk_motion"].get(t)
        if m is None or not np.all(np.isfinite(m)):
            return "rm", spec["custom"]
        return "custom", m

    def request_soundings(self):
        self.gen["snd"] += 1
        g = self.gen["snd"]
        if not self.points:
            self.results = []
            self.skew_png.visible = self.prof_png.visible = self.snd_tabs.visible = False
            self.prof_row.visible = False
            self.params.html = ""
            self.snd_head.object = ('<div class="cv-empty">Click anywhere on the map to drop '
                                    'a sounding. <kbd>Shift</kbd>-click to add up to four '
                                    'for comparison.</div>')
            return
        spec = dict(t=self.t, points=list(self.points), avg=float(self.avg.value),
                    storm=self.storm.value,
                    custom=(self.storm_u.value or 0.0, self.storm_v.value or 0.0),
                    parcel=self.parcel.value, units=self.wunits.value,
                    zmax=float(self.prof_top.value), base=self.base_on.value,
                    style=self.compare.value, look=self._look(), lim=self._lim_copy(),
                    xy=[self._snd_xy(k, w, self.t if tp is None else tp)
                        for k, w, tp in self.points],
                    trk_motion=trk.motion(self.run, self.fixes) if self.fixes else {})
        self.snd_col.loading = True
        self.pools["snd"].submit(self._snd_job, spec, g)

    def _snd_job(self, spec, g):
        if g != self.gen["snd"]:
            return
        run, t = self.run, spec["t"]
        try:
            def prog_for(tt, what):
                def prog(done, total, name):
                    if total:
                        msg = (f'<div class="cv-status"><span class="busy">● Reading {what} '
                               f'for t = {run.time_label(tt)} ({done}/{total}) {name}… a few '
                               f'seconds per field the first time at each time</span></div>')
                        self._schedule(partial(setattr, self.snd_msg, "object", msg))
                return prog

            # live soundings at the shown time read (and cache) whole 3D fields, so
            # later clicks are instant; pinned other times read just their box
            if any(kind != "mean" and tp is None for kind, _, tp in spec["points"]):
                if any(run.cached(v, t) is None for v in SOUNDING_VARS):
                    ok = run.load_volumes(SOUNDING_VARS, t, progress=prog_for(t, "3D fields"),
                                          cancelled=lambda: g != self.gen["snd"])
                    if not ok or g != self.gen["snd"]:
                        return
            z = run.z * 1000.0
            h = int(round(spec["avg"] * 1000.0 / run.dx / 2.0))
            items = []
            for n, (kind, where, tp) in enumerate(spec["points"]):
                tt = t if tp is None else tp
                when = "" if tp is None else f" @ {run.time_label(tt)}"
                if kind != "mean":
                    xy = spec["xy"][n]
                    if xy is None:  # storm-following, but no tracked meso at tt
                        continue
                    x, y = xy
                    i, j = run.ij(x, y)
                    hi = hj = h
                    if len(where) == 4:  # area sounding: mean over the dragged box
                        hi = int(round(where[2] * 500.0 / run.dx))
                        hj = int(round(where[3] * 500.0 / run.dy))
                    i0, i1 = max(0, i - hi), min(run.ni, i + hi + 1)
                    j0, j1 = max(0, j - hj), min(run.nj, j + hj + 1)
                    c = {}
                    for v in SOUNDING_VARS:
                        vol = run.cached(v, tt)
                        if vol is None:
                            prog_for(tt, "columns")(SOUNDING_VARS.index(v), len(SOUNDING_VARS), v)
                            a = run.read_box(v, tt, i0, i1, j0, j1)
                        else:
                            a = vol[:, j0:j1, i0:i1]
                        c[v] = a.mean(axis=(1, 2), dtype=np.float64)
                        if g != self.gen["snd"]:
                            return
                    box = (f" box {where[2]:.3g}×{where[3]:.3g} km at" if len(where) == 4
                           else "")
                    if kind == "trk":
                        dx_, dy_ = where[:2]
                        rel = "meso" if dx_ == 0 and dy_ == 0 else f"meso {dx_:+.1f}, {dy_:+.1f}"
                        label = f"{POINT_LABELS[n]}{box} {rel} km{when}"
                    else:
                        label = f"{POINT_LABELS[n]}{box} ({x:.1f}, {y:.1f}) km{when}"
                else:
                    c = run.mean_profiles(SOUNDING_VARS, tt, progress=prog_for(tt, "domain means"))
                    if g != self.gen["snd"]:
                        return
                    label = f"{POINT_LABELS[n]} domain mean {run.time_label(tt)}"
                storm, custom = self._item_storm(spec, tt)
                r = thermo.analyze(z, c["prs"], c["th"], c["qv"], c["uinterp"] + run.umove,
                                   c["vinterp"] + run.vmove, storm=storm,
                                   custom=custom, domain=(run.umove, run.vmove))
                r["domain"] = (run.umove, run.vmove)
                items.append((label, POINT_COLORS[n], r))
            if not items:
                raise ValueError("no tracked meso at this time for the storm-following "
                                 "sounding(s)")
            base = self._base_result(spec) if spec["base"] else None
            short = [(lab.split(" ")[0] + (" mean" if "mean" in lab else "")
                      + (" box" if " box " in lab else "")
                      + (" meso" if "meso" in lab else "")
                      + (f' {lab.split("@ ")[1]}' if "@ " in lab else ""), c, r)
                     for lab, c, r in items]  # table column headers
            html = sp.params_html(short, base, spec["units"])
            res = (self._draw_figs(items, base, spec), html, items, base)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["snd"]:
            self._schedule(partial(self._apply_snd, res, spec, g))

    def _apply_snd(self, res, spec, g):
        if g != self.gen["snd"]:
            return
        self.snd_col.loading = False
        self.snd_msg.object = ""
        if isinstance(res, Exception):
            self._set_status(f'<span style="color:#f87171">Sounding error: {res}</span>')
            return
        draws, html, items, base = res
        self.results = items
        self._snd_last = (items, base, spec)
        run = self.run
        avg = "single column" if spec["avg"] == 0 else f'{spec["avg"]:g} km box mean'
        if all(k == "mean" or len(w) == 4 for k, w, _ in spec["points"]):
            avg = "area mean"  # the column-average setting applies to point soundings
        pts = " ".join(f'<span style="color:{c};margin-right:14px">{lab}</span>'
                       for lab, c, r in items)
        self.snd_head.object = (f'<div class="cv-maptitle">t = {run.time_label(spec["t"])} · '
                                f'{avg} · {pts}</div>')
        self._show_figs(draws)
        self.params.html = html
        self.prof_row.visible = True
        self._set_status("")
        if self.vec_on.value and self.vec_frame.value == "storm":
            self.request_map()

    def _draw_figs(self, items, base, spec):
        """[(tab label or None, skew-T/hodograph figure, its SVG, profiles figure, its
        SVG)]: one entry, or one per sounding in the Tabs comparison style."""
        st, look, lim = spec["style"], spec["look"], spec["lim"]
        groups = [(it[0], [it]) for it in items] if st == "tabs" and len(items) > 1 \
            else [(None, items)]
        out = []
        for lab, its in groups:
            fs = sp.skewt_hodo_figure(its, base, spec["parcel"], spec["units"],
                                      style="lines" if lab else st, look=look, limits=lim)
            fp = sp.profiles_figure(its, base, spec["zmax"], spec["units"],
                                    style="lines" if lab else st, look=look,
                                    limits=dict(z=lim.get("prof_z"), x=lim.get("prof_x")))
            out.append((lab, fs, _svg(fs), fp, _svg(fp)))
        return out

    def _show_figs(self, draws):
        """Put drawn sounding figures on the page; remembers each image's figure so a
        dragged box can be turned into axes limits."""
        self._figs = {}
        if draws[0][0] is None:
            _, fs, a, fp, b = draws[0]
            self.skew_png.src, self.prof_png.src = a, b
            self._figs = {self.skew_png: fs, self.prof_png: fp}
            self.skew_png.visible = self.prof_png.visible = True
            self.snd_tabs.visible = False
        else:
            active = self.snd_tabs.active
            names = [lab.replace(" km", "") for lab, *_ in draws]
            if self._snd_tab_names != names:
                self.snd_tabs[:] = [(name, pn.Column(
                    self._zoom_image("skewt_hodograph.svg", visible=True),
                    self._zoom_image("profiles.svg", visible=True),
                    sizing_mode="stretch_width")) for name in names]
                self._snd_tab_names = names
            for tab, (_, fs, a, fp, b) in zip(self.snd_tabs, draws):
                tab[0].src, tab[1].src = a, b
                self._figs[tab[0]], self._figs[tab[1]] = fs, fp
            self.snd_tabs.active = min(active, len(draws) - 1)
            self.skew_png.visible = self.prof_png.visible = False
            self.snd_tabs.visible = True
        for z in self._figs:
            z.done += 1

    # ---------------------------------------------------------- restyle / zoom
    def _look(self):
        ps = self.ps
        return dict(t_color=ps["t"].value, td_color=ps["td"].value,
                    parcel_color=ps["parcel"].value, base_color=ps["base"].value,
                    lw=ps["lw"].value, parcel_lw=ps["parcel_lw"].value,
                    hodo_lw=ps["hodo_lw"].value, prof_lw=ps["prof_lw"].value,
                    shade=ps["shade"].value, barbs=ps["barbs"].value,
                    guides=ps["guides"].value, ptop=float(ps["ptop"].value),
                    tmin=ps["tmin"].value, tmax=ps["tmax"].value,
                    ring=float(ps["ring"].value) or None, hodo_top=float(ps["htop"].value))

    def _restyle(self):
        """Redraw the shown soundings with the current style and zoom (no new analysis)."""
        if self._hold_style or not self.points or not getattr(self, "_snd_last", None):
            return
        if self.snd_col.loading:  # a new analysis is on its way: let it use them
            self.request_soundings()
            return
        items, base, spec = self._snd_last
        spec = dict(spec, look=self._look(), lim=self._lim_copy())
        self.gen["snd"] += 1
        g = self.gen["snd"]

        def job():
            try:
                draws = self._draw_figs(items, base, spec)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                draws = e
            if g == self.gen["snd"]:
                self._schedule(partial(apply, draws))

        def apply(draws):
            if g != self.gen["snd"]:
                return
            if isinstance(draws, Exception):
                self._set_status(f'<span style="color:#f87171">Sounding error: {draws}</span>')
                return
            self._snd_last = (items, base, spec)
            self._show_figs(draws)
        self.pools["snd"].submit(job)

    def _on_style_reset(self, ev):
        st = sp.STYLE
        defaults = dict(t=st["t_color"], td=st["td_color"], parcel=st["parcel_color"],
                        base=st["base_color"], lw=st["lw"], parcel_lw=st["parcel_lw"],
                        hodo_lw=st["hodo_lw"], prof_lw=st["prof_lw"], ptop=100, tmin=None,
                        tmax=None, ring=0, htop=12, shade=st["shade"], barbs=st["barbs"],
                        guides=st["guides"])
        self._hold_style = True
        try:
            for k, v in defaults.items():
                self.ps[k].value = v
        finally:
            self._hold_style = False
        self._restyle()

    _hold_style = False

    def _lim_copy(self):
        lim = dict(self.snd_lim)
        if "prof_x" in lim:
            lim["prof_x"] = dict(lim["prof_x"])
        return lim

    def _on_zoom_box(self, z, ev):
        """A box dragged on a sounding image -> axes limits of the panel under it."""
        fig = getattr(self, "_figs", {}).get(z)
        b = ev.new
        if fig is None or not b or len(b) < 4:
            z.done += 1
            return
        W, H = fig.bbox.width, fig.bbox.height
        x0, x1 = b[0] * W, b[2] * W
        y0, y1 = (1.0 - b[3]) * H, (1.0 - b[1]) * H  # display y grows upward
        hit = self._axes_at(fig, 0.5 * (x0 + x1), 0.5 * (y0 + y1))
        if hit is None:
            z.done += 1
            return
        key, ax = hit
        bb = ax.bbox
        self._set_lims(key, ax, max(x0, bb.x0), min(x1, bb.x1),
                       max(y0, bb.y0), min(y1, bb.y1))
        self._restyle()

    def _on_zoom_pan(self, z, ev):
        """A drag in pan mode -> the panel under its start point shows the region the
        drag moved into view (the content follows the pointer)."""
        fig = getattr(self, "_figs", {}).get(z)
        p = ev.new
        if fig is None or not p or len(p) < 4:
            z.done += 1
            return
        W, H = fig.bbox.width, fig.bbox.height
        hit = self._axes_at(fig, p[0] * W, (1.0 - p[1]) * H)
        if hit is None:
            z.done += 1
            return
        key, ax = hit
        dx, dy = p[2] * W, -p[3] * H  # display y grows upward
        bb = ax.bbox
        self._set_lims(key, ax, bb.x0 - dx, bb.x1 - dx, bb.y0 - dy, bb.y1 - dy)
        self._restyle()

    @staticmethod
    def _axes_at(fig, x, y):
        return next(((k, ax) for k, ax in fig.cv_axes.items() if ax.bbox.contains(x, y)),
                    None)

    def _set_lims(self, key, ax, x0, x1, y0, y1):
        """Axes limits of panel `key` that show the display rectangle x0..x1, y0..y1."""
        inv = ax.transData.inverted()
        (a0, b0), (a1, b1) = inv.transform([(x0, y0), (x1, y1)])
        if key == "skew":  # x limits are the temperatures along the bottom edge
            t_left, p_bot = a0, b0
            t_right = inv.transform([(x1, y0)])[0][0]
            p_top = inv.transform([(x0, y1)])[0][1]
            self.snd_lim["skew"] = (float(t_left), float(t_right), float(p_bot), float(p_top))
        elif key == "hodo":
            self.snd_lim["hodo"] = (float(a0), float(a1), float(b0), float(b1))
        else:
            self.snd_lim["prof_z"] = (float(b0), float(b1))
            self.snd_lim.setdefault("prof_x", {})[int(key[4:])] = (float(a0), float(a1))

    def _on_zoom_out(self, z):
        """Widen the zoomed panels of this image by 1.6 (pressure in log p)."""
        fig = getattr(self, "_figs", {}).get(z)
        lim, f = self.snd_lim, 1.6
        if fig is None or not any(k in lim for k in self._lim_keys(fig)):
            z.done += 1
            return

        def widen(a, b):
            c, h = 0.5 * (a + b), 0.5 * (b - a) * f
            return c - h, c + h

        if "skew" in lim and "skew" in fig.cv_axes:
            t0, t1, pb, pt = lim["skew"]
            lb, lt = widen(np.log(pb), np.log(pt))
            pb, pt = min(np.exp(lb), 1100.0), max(np.exp(lt), 50.0)
            lim["skew"] = (*widen(t0, t1), pb, pt)
        if "hodo" in lim and "hodo" in fig.cv_axes:
            u0, u1, v0, v1 = lim["hodo"]
            lim["hodo"] = (*widen(u0, u1), *widen(v0, v1))
        if "prof_z" in lim and "prof0" in fig.cv_axes:
            z0, z1 = widen(*lim["prof_z"])
            lim["prof_z"] = (max(z0, 0.0), z1)
            lim["prof_x"] = {i: widen(*x) for i, x in lim.get("prof_x", {}).items()}
        self._restyle()

    def _on_zoom_reset(self, z):
        fig = getattr(self, "_figs", {}).get(z)
        keys = self._lim_keys(fig) if fig is not None else ()
        if not any(k in self.snd_lim for k in keys):
            z.done += 1
            return
        for k in keys:
            self.snd_lim.pop(k, None)
        self._restyle()

    @staticmethod
    def _lim_keys(fig):
        ks = []
        if "skew" in fig.cv_axes:
            ks += ["skew", "hodo"]
        if "prof0" in fig.cv_axes:
            ks += ["prof_z", "prof_x"]
        return ks

    # ================================================================ meso track
    def _trk_opts(self):
        return dict(metric=self.trk_metric.value, zkm=float(self.trk_z.value or 0.0),
                    radius=float(self.trk_radius.value or 5.0),
                    smooth=float(self.trk_smooth.value or 0.0), kernel=self.trk_kernel.value,
                    stop=float(self.trk_stop.value or 0.0), snap=self.trk_snap.value,
                    nearest=self.trk_near.value, whole=self.trk_whole.value)

    def _trk_preset(self, metric):
        """Default settings per tracked field.  Updraft: w at 1 km with a Gaussian of
        sigma = 3 grid points, as in storm_tracking.ipynb."""
        dxk = self.run.dx / 1000.0
        z, smooth, kernel = {"w": (1.0, 3 * dxk, "gauss"), "zeta": (1.0, 1.0, "box"),
                             "uh": (self.trk_z.value, 1.0, "box")}[metric]
        self.trk_z.param.update(value=z, visible=metric != "uh")
        self.trk_smooth.value, self.trk_kernel.value = round(smooth, 3), kernel
        self.trk_stop.value = trk.METRIC_STOP[metric]

    def _on_trk_metric(self, ev):
        self._trk_preset(ev.new)

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
        direction, existing = self.trk_dir.value, None
        same = self.trk_spec is not None and all(
            self.trk_spec.get(k) == opts[k]
            for k in ("metric", "zkm", "smooth", "kernel", "nearest", "whole"))
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
        self.trk_dir.visible = self.trk_stop.visible = not manual
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
            fx = trk.place(self.run, t, x, y, opts)
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
                              on_fix=on_fix, cancelled=cancelled, progress=progress)
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
            return ('<div class="cv-empty">Pick <b>Track</b> in the click modes and click '
                    'on the storm, or press <b>Find strongest</b> to start from the '
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
            mv = (' · tracking stopped after one time: the signal was below '
                  '<i>Stop below</i> at the next time')
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
        m = (self.trk_spec or self._trk_opts())["metric"]
        self.trk_fig.yaxis.axis_label = f"{trk.METRIC_LABEL[m]} ({trk.METRIC_UNITS[m]})"
        if ts:
            import pandas as pd
            df = pd.DataFrame(trk.rows(run, fx)).drop(columns=["file", "time_s"])
            self.trk_table.value = df.round(4)
        self.trk_table.visible = bool(ts)
        self.trk_save.disabled = self.trk_dl.disabled = not ts
        self.storm_follow.disabled = not ts
        if not ts:
            self.trk_status.object = self._track_summary()
        self._update_track_now()
        # storm-relative fields take their motion from the track: redraw, but not for
        # every fix while auto-tracking (that ends with one redraw in _apply_track)
        if self._storm_fields_shown() and self.trk_stop_btn.disabled:
            self.request_map()

    def _update_track_now(self):
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
        text = trk.to_text(self.run, self.fixes, self.trk_spec or self._trk_opts(), fmt)
        return io.BytesIO(text.encode())

    def _on_save_track(self, ev):
        try:
            path = trk.save(self.run, self.fixes, self.trk_spec or self._trk_opts(),
                            self.trk_path.value)
        except OSError as e:
            self.trk_status.object = (f'<div class="cv-status" style="color:#f87171">Could '
                                      f'not save: {e}</div>')
            return
        self.trk_status.object = self._track_summary(f' · saved to <code>{path}</code>')

    # ================================================================ time series
    def _ser_recipe(self):
        """The recipe of the Series form, normalized (None + message if incomplete)."""
        d = self.F[self.ser_field.value]
        r = dict(field=d.name, vmode="2d" if d.ndim == 2 else self.ser_vmode.value,
                 z=self.ser_z.value or 0.0, z0=self.ser_z0.value or 0.0,
                 z1=self.ser_z1.value or 0.0, reduce=self.ser_reduce.value,
                 pct=self.ser_pct.value if self.ser_pct.value is not None else 99.0,
                 radius=self.ser_radius.value or 5.0,
                 offset=(self.ser_offx.value or 0.0, self.ser_offy.value or 0.0))
        reg = self.ser_region.value
        if reg == "view":
            r.update(region="box", box=self.view)
        elif reg == "box3d":
            if self.box is None:
                return None, ("Pick a 3D region first (<b>3D region</b> click mode on the "
                              "map), or choose another region")
            r.update(region="box", box=self.box)
        else:
            r["region"] = reg
        if reg == "track" and not self.fixes:
            return None, ("Track the storm first (<b>Track</b> tab), then compute around "
                          "it")
        return ser.normalize(r), ""

    def _ser_key(self, recipe, source=""):
        import json
        return json.dumps(recipe, sort_keys=True) + (f"|{source}" if source else "")

    def _ser_add(self, key, ds, recipe, loaded=""):
        """Register a series of this session (or refresh it) and make it the active one."""
        d = self.F[recipe["field"]] if recipe["field"] in self.F else None
        label = ser.describe(recipe, d.label if d else "", d.units if d else "")
        if loaded:
            label += f" — {os.path.basename(loaded)}"
        if key not in self.series:
            self.series[key] = dict(ds=ds, recipe=recipe, label=label,
                                    color=POINT_COLORS[self._ser_n % len(POINT_COLORS)]
                                    if self._ser_n < 4 else
                                    palette("Spectral_r", 12)[(3 * self._ser_n) % 12])
            self._ser_n += 1
        else:
            self.series[key]["ds"] = ds
        self.ser_pick.options = {v["label"]: k for k, v in self.series.items()}
        if self.ser_pick.value == key:
            self._ser_select()
        else:
            self.ser_pick.value = key
        self.ser_path.value = (f"{self._ser_prefix}_{ser.short_name(recipe)}"
                               f"{self.ser_fmt.value}")

    def _on_ser_compute(self, ev):
        recipe, why = self._ser_recipe()
        if recipe is None:
            self.ser_status.object = f'<div class="cv-status" style="color:#f87171">{why}</div>'
            return
        run, d = self.run, self.F[recipe["field"]]
        centers = ser.track_centers(self.fixes, len(run.times)) \
            if recipe["region"] == "track" else None
        storm = {t: self._field_storm(t)[0] for t in range(len(run.times))} \
            if d.storm else None
        key = self._ser_key(recipe)
        if key in self.series:
            ds = self.series[key]["ds"]
            if centers is not None:
                ser.invalidate_moved(ds, recipe, centers)
        else:
            ds = ser.cached(run, recipe, d.label, d.units, centers)
        self._ser_add(key, ds, recipe)
        self.gen["ser"] += 1
        g = self.gen["ser"]
        todo = int(len(run.times) - ds["computed"].sum())
        self.ser_go.disabled, self.ser_stop.disabled = True, False
        self.ser_status.object = (f'<div class="cv-status"><span class="busy">● Computing '
                                  f'{todo} of {len(run.times)} times '
                                  f'({run.workers} reader{"s" if run.workers > 1 else ""})…'
                                  f'</span></div>')
        self.pools["ser"].submit(self._ser_job, g, key, recipe, ds, centers, storm)

    def _ser_job(self, g, key, recipe, ds, centers, storm):
        import time as _t
        run, t0, last = self.run, _t.time(), [0.0]

        def cancelled():
            return g != self.gen["ser"]

        def on_result(ds_, done, total):
            if cancelled() or (_t.time() - last[0] < 1.0 and done < total):
                return
            last[0] = _t.time()
            msg = (f'<div class="cv-status"><span class="busy">● Computing… {done}/{total} '
                   f'times · {_t.time() - t0:.0f} s</span></div>')
            self._schedule(partial(self._ser_progress, g, msg))

        try:
            ds, skipped = ser.compute(run, self.F, recipe, ds, centers, storm,
                                      on_result=on_result, cancelled=cancelled)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            msg = f'<div class="cv-status" style="color:#f87171">Series error: {e}</div>'
            self._schedule(partial(self._ser_finish, g, msg))
            return
        n = int(ds["computed"].sum())
        msg = (f'<div class="cv-status">{n} of {len(run.times)} times · '
               f'{_t.time() - t0:.0f} s{" · stopped" if cancelled() else ""}')
        if skipped:
            why = {}
            for t, r in skipped.items():
                why.setdefault(r, []).append(t)
            msg += " · not computed: " + "; ".join(
                f"{len(ts)} time{'s' if len(ts) > 1 else ''} ({r})" for r, ts in why.items())
        msg += "</div>"
        self._schedule(partial(self._ser_finish, g, msg, force=cancelled()))

    def _ser_progress(self, g, msg):
        if g == self.gen["ser"]:
            self.ser_status.object = msg
            self._ser_draw()

    def _ser_finish(self, g, msg, force=False):
        if g != self.gen["ser"] and not force:
            return
        self.ser_status.object = msg
        self.ser_go.disabled, self.ser_stop.disabled = False, True
        self._ser_draw()

    def _cancel_series(self):
        self.gen["ser"] += 1
        self.ser_go.disabled, self.ser_stop.disabled = False, True

    def _ser_select(self):
        s = self.series.get(self.ser_pick.value)
        has = s is not None
        self.ser_save.disabled = self.ser_dl.disabled = self.ser_remove.disabled = not has
        prof = has and "profile" in s["ds"]
        self.ser_view.disabled = not prof
        if not prof and self.ser_view.value != "line":
            self.ser_view.value = "line"  # redraws
            return
        self._ser_draw()

    def _ser_draw(self):
        from bokeh.models import DataRange1d, Legend, LegendItem, LinearAxis

        run, fig = self.run, self.ser_fig
        fig.renderers = [r for r in fig.renderers if r not in self._ser_glyphs]
        self._ser_glyphs = []
        # series in other units than the first get their own y axis on the right
        for ax in getattr(self, "_ser_axes", []):
            if ax in fig.right:
                fig.right.remove(ax)
        self._ser_axes = []
        order = list(dict.fromkeys(s["ds"]["value"].attrs.get("units", "")
                                   for s in self.series.values()))
        ranges = {u: "default" if n == 0 else f"u{n}" for n, u in enumerate(order)}
        fig.extra_y_ranges = {name: DataRange1d() for name in ranges.values()
                              if name != "default"}
        by_range = {name: [] for name in ranges.values()}
        items = []
        for key, s in self.series.items():
            ds = s["ds"]
            ok = ds["computed"].values == 1
            ts = np.flatnonzero(ok)
            v = ds["value"].values[ts]
            where = [("" if not np.isfinite(x) else
                      f"({x:.1f}, {y:.1f}) km" + (f", {z:.2f} km AGL" if np.isfinite(z) else ""))
                     for x, y, z in zip(ds["x_km"].values[ts], ds["y_km"].values[ts],
                                        ds["z_km"].values[ts])]
            src = ColumnDataSource(dict(tmin=run.times[ts] / 60.0, value=v,
                                        hms=[run.time_label(t) for t in ts],
                                        name=[s["label"]] * len(ts), where=where))
            act = key == self.ser_pick.value
            rng = ranges[ds["value"].attrs.get("units", "")]
            ln = fig.line("tmin", "value", source=src, line_color=s["color"],
                          line_width=2.5 if act else 1.6, y_range_name=rng)
            pt = fig.scatter("tmin", "value", source=src, size=5 if act else 3,
                             color=s["color"], y_range_name=rng)
            self._ser_glyphs += [ln, pt]
            by_range[rng] += [ln, pt]
            items.append(LegendItem(label=s["label"], renderers=[ln, pt]))
        if not fig.legend:
            # below the plot: a click on an entry (hide / show) is not a click on a time
            fig.add_layout(Legend(click_policy="hide", background_fill_color=BG,
                                  label_text_color=TEXT, label_text_font_size="11px",
                                  border_line_color=None, spacing=0, padding=4), "below")
        fig.legend[0].items = items
        fig.legend[0].visible = bool(items)
        fig.y_range.renderers = by_range.get("default", []) or "auto"
        for u, name in ranges.items():
            if name == "default":
                continue
            fig.extra_y_ranges[name].renderers = by_range[name]
            ax = LinearAxis(y_range_name=name, axis_label=u or "(no units)")
            for k in ("axis_label_text_color", "major_label_text_color", "axis_line_color",
                      "major_tick_line_color", "minor_tick_line_color"):
                setattr(ax, k, getattr(fig.yaxis[0], k))
            fig.add_layout(ax, "right")
            self._ser_axes.append(ax)
        fig.yaxis[0].axis_label = order[0] if order else ""
        s = self.series.get(self.ser_pick.value)
        th = (s is not None and "profile" in s["ds"] and self.ser_view.value == "th")
        if th:
            self._ser_draw_th(s)
        want = self.ser_thfig if th else fig
        if self.ser_plot.object is not want:
            self.ser_plot.object = want

    def _ser_draw_th(self, s):
        """Time–height quads of the active layer series (stretched grid: cell edges)."""
        run, ds, r = self.run, s["ds"], s["recipe"]
        ks = ser.levels(run, r)
        ts = np.flatnonzero(ds["computed"].values == 1)
        tm = run.times / 60.0
        te = np.concatenate([[tm[0] - 0.5 * (tm[1] - tm[0])], 0.5 * (tm[1:] + tm[:-1]),
                             [tm[-1] + 0.5 * (tm[-1] - tm[-2])]]) if len(tm) > 1 \
            else np.array([tm[0] - 1, tm[0] + 1])
        P = ds["profile"].values
        L, R, B, T, V, H, Z = [], [], [], [], [], [], []
        for t in ts:
            for n, k in enumerate(ks):
                L.append(te[t]), R.append(te[t + 1])
                B.append(run.zf[k]), T.append(run.zf[k + 1])
                V.append(P[t, n]), H.append(run.time_label(t)), Z.append(run.z[k])
        self.ser_th_src.data = dict(l=L, r=R, b=B, t=T, v=V, hms=H, z=Z)
        d = self.F[r["field"]] if r["field"] in self.F else None
        fin = np.asarray(V)[np.isfinite(V)] if V else np.array([])
        lo, hi = np.percentile(fin, [1, 99]) if fin.size else (0.0, 1.0)
        # diverging colours only when the values have both signs (max w: one sign)
        if d is not None and d.diverging and lo < -0.05 * hi and hi > -0.05 * lo:
            m = float(np.percentile(np.abs(fin), 99)) if fin.size else 1.0
            lo, hi, pal = -(m or 1.0), (m or 1.0), palette("RdBu_r")
        else:
            lo, hi = (np.percentile(fin, [1, 99]) if fin.size else (0.0, 1.0))
            lo, hi = float(lo), float(hi if hi > lo else lo + 1.0)
            pal = palette("viridis")
        self.ser_th_map.update(low=lo, high=hi, palette=pal)
        self.ser_thfig.title.text = s["label"]
        self.ser_thfig.title.text_color = MUTED

    def _on_ser_tap(self, ev):
        """Click on a series plot: show that time."""
        if ev.x is None:
            return
        t = int(np.argmin(np.abs(self.run.times / 60.0 - ev.x)))
        if t != self.t:
            self.tslider.value = t
            self._refresh_panels()

    def _on_ser_remove(self, ev):
        self.series.pop(self.ser_pick.value, None)
        self.ser_pick.options = {v["label"]: k for k, v in self.series.items()}
        self.ser_pick.value = next(iter(self.series), None)
        self._ser_select()

    def _on_ser_fmt(self, ev):
        base, _ = os.path.splitext(self.ser_path.value)
        self.ser_path.value = base + ev.new

    def _ser_file_msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.ser_file_msg.object = f'<div class="cv-status"{col}>{html}</div>'

    def _on_ser_save(self, ev):
        s = self.series.get(self.ser_pick.value)
        if s is None:
            return
        path = self.ser_path.value
        if os.path.splitext(path)[1].lower() not in ser.FORMATS:
            path += self.ser_fmt.value
        try:
            path = ser.save(s["ds"], path)
        except (OSError, ValueError) as e:
            self._ser_file_msg(f"Could not save: {e}", err=True)
            return
        self._ser_file_msg(f"Saved to <code>{path}</code>")

    def _ser_download(self):
        import tempfile
        s = self.series.get(self.ser_pick.value)
        name = self.ser_dl.filename or "series.nc"
        if os.path.splitext(name)[1].lower() not in ser.FORMATS:
            name += self.ser_fmt.value
        with tempfile.TemporaryDirectory() as tmp:
            path = ser.save(s["ds"], os.path.join(tmp, os.path.basename(name)))
            with open(path, "rb") as f:
                return io.BytesIO(f.read())

    def _on_ser_load(self, ev):
        path = os.path.abspath(os.path.expanduser(self.ser_path.value))
        try:
            ds, recipe, note = ser.load(self.run, path, self.F)
        except (OSError, ValueError, KeyError) as e:
            self._ser_file_msg(f"Could not load <code>{path}</code>: {e}", err=True)
            return
        self._ser_add(self._ser_key(recipe, path), ds, recipe, loaded=path)
        self.ser_path.value = path
        warn = (" · pickle files can run code when loaded: open only your own"
                if path.lower().endswith(".pkl") else "")
        self._ser_file_msg(f"Loaded <code>{path}</code>"
                           + (f" · {note}" if note else "") + warn)
        self._show_panel(True, 3)

    # ================================================================ cross-section
    _hold_xs = False

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
        self.xs_fig.x_range.update(start=0.0, end=float(s[-1]))
        self.xs_fig.y_range.update(start=0.0, end=float(zq[-1]))
        self.xs_lab[1].x = float(s[-1])
        for a in self.xs_lab:
            a.visible = True
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
        self.pd_write.disabled = busy

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
        self.sl_fig.yaxis[0].axis_label = res["label"]
        frame = FRAME_SHORT[self._s3["frame"]] if self._s3 else ""
        self.sl_info.object = (
            f'<div class="cv-status" style="line-height:1.35"><b style="color:'
            f'{volume3d.SELECTED}">Streamline</b> ({frame}) · seed ({res["x0"]:.1f}, '
            f'{res["y0"]:.1f}) km, {res["z0"] * 1000:.0f} m<br>{res["length"]:.1f} km long · '
            f'z {z0:.2f}–{z1:.2f} km</div>')


def create_app(reg, maxpix=900):
    pn.extension("plotly", "modal", "tabulator", notifications=False, raw_css=[CSS])
    want, error = None, ""
    try:  # ?run=/path/to/run picks the run directory
        want = pn.state.session_args.get("run", [b""])[0].decode().strip() or None
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        run, fields = reg.get(os.path.expanduser(want) if want else None)
    except Exception as e:  # noqa: BLE001
        print(f"cm1view: could not open {want}: {e}", flush=True)
        error = f"Could not open {want}: {e}. Showing the default run instead."
        run, fields = reg.get()
    v = Viewer(run, fields, maxpix=maxpix, error=error, reg=reg)
    pn.state.on_session_destroyed(lambda ctx: v.close())
    # the template only supplies the dark theme: header and margins are hidden so the
    # visualisations fill the window and the controls float over them
    chrome = ("#header{display:none !important} #main{padding:0 !important;"
              "overflow:hidden !important} .card-margin{margin:0 !important}"
              " #container{height:100vh}")
    return pn.template.FastListTemplate(
        title="CM1 View", theme="dark", accent=ACCENT, header_background=BG,
        main=[v.main()], theme_toggle=False, main_layout=None, raw_css=[CSS, chrome])
