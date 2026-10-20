"""Panel application: map + sounding / cross-section / 3D panels."""

import base64
import html as html_lib
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
from bokeh.events import RangesUpdate, SelectionGeometry, Tap  # noqa: E402
from bokeh.models import (  # noqa: E402
    BoxSelectTool, BoxZoomTool, ColorBar, ColumnDataSource, CustomJS, HoverTool,
    LinearColorMapper,
    FixedTicker, LinearAxis, PanTool, Range1d, ResetTool, SaveTool, WheelZoomTool,
)
from bokeh.plotting import figure  # noqa: E402
from bokeh.transform import transform  # noqa: E402

from . import registry, render, sounding_plot as sp, thermo, track as trk, volume3d  # noqa: E402
from .fields import CMAPS, palette  # noqa: E402
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


def _png(fig, dpi=200):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor())
    return buf.getvalue()


# click a sounding image -> full-window viewer: wheel zoom about the cursor, drag to
# pan, double-click to refit, Esc or the close button to leave (inline so it works
# from inside Panel's shadow DOM)
_ZOOM_JS = """(function(src){
var o=document.createElement('div');
o.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(5,8,14,.94);overflow:hidden;cursor:grab';
var i=document.createElement('img');i.src=src;i.draggable=false;
i.style.cssText='position:absolute;left:0;top:0;transform-origin:0 0;max-width:none;user-select:none';
var h=document.createElement('div');
h.textContent='scroll: zoom \u00b7 drag: pan \u00b7 double-click: fit \u00b7 Esc: close';
h.style.cssText='position:absolute;left:16px;bottom:12px;color:#94a3b8;font:12px system-ui,sans-serif';
var x=document.createElement('div');x.textContent='\u2715';x.title='Close (Esc)';
x.style.cssText='position:absolute;right:18px;top:10px;color:#e2e8f0;font:24px system-ui,sans-serif;cursor:pointer';
o.append(i,h,x);document.body.append(o);
var s=1,tx=0,ty=0,d=null;
function ap(){i.style.transform='translate('+tx+'px,'+ty+'px) scale('+s+')';}
function fit(){var W=innerWidth,H=innerHeight,w=i.naturalWidth,g=i.naturalHeight;
s=Math.min(W/w,H/g)*0.96;tx=(W-w*s)/2;ty=(H-g*s)/2;ap();}
i.onload=fit;if(i.complete)fit();
o.addEventListener('wheel',function(e){e.preventDefault();
var n=Math.min(Math.max(s*Math.exp(-e.deltaY*0.0015),0.1),12);
tx=e.clientX-(e.clientX-tx)*n/s;ty=e.clientY-(e.clientY-ty)*n/s;s=n;ap();},{passive:false});
o.onmousedown=function(e){d=[e.clientX-tx,e.clientY-ty];o.style.cursor='grabbing';e.preventDefault();};
o.onmousemove=function(e){if(d){tx=e.clientX-d[0];ty=e.clientY-d[1];ap();}};
o.onmouseup=o.onmouseleave=function(){d=null;o.style.cursor='grab';};
o.ondblclick=fit;
function k(e){if(e.key==='Escape'){e.stopPropagation();c();}}
function c(){o.remove();document.removeEventListener('keydown',k,true);}
document.addEventListener('keydown',k,true);o.tabIndex=-1;o.style.outline='none';o.focus();
x.onmousedown=function(e){e.stopPropagation();};x.onclick=c;
})(this.src)"""
_ZOOM_ATTR = html_lib.escape(_ZOOM_JS.replace("\n", ""), quote=True)


def _img(png):
    """PNG bytes as an <img> that scales with the panel width; click to zoom."""
    b64 = base64.b64encode(png).decode()
    return (f'<img src="data:image/png;base64,{b64}" title="Click to zoom" '
            f'onclick="{_ZOOM_ATTR}" style="width:100%;height:auto;display:block;'
            f'cursor:zoom-in">')


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
    def __init__(self, run, fields, maxpix=900, error=""):
        self.run, self.F = run, fields
        self.maxpix = maxpix
        self.error = error
        self.doc = pn.state.curdoc
        self.pools = {k: ThreadPoolExecutor(1, thread_name_prefix=f"cm1view-{k}")
                      for k in ("map", "snd", "xs", "3d", "trk")}
        self.gen = dict.fromkeys(self.pools, 0)
        # soundings: (kind, where, tpin) with kind "pt" (where = x, y km), "mean"
        # (where = None) or "trk" (where = offset from the tracked meso, km);
        # tpin = None follows the time slider, otherwise a pinned time index
        self.points, self.results, self.xs_pts, self.box = [], [], [], None
        self.fixes, self.trk_spec = {}, None  # meso track: {t: fix}, settings used
        self._hold = False
        dxk, dyk = run.dx / 1000.0, run.dy / 1000.0
        self.extent = (run.xh[0] - dxk / 2, run.xh[-1] + dxk / 2,
                       run.yh[0] - dyk / 2, run.yh[-1] + dyk / 2)
        self.view = self.extent
        self._build_widgets()
        self._build_map()
        self._build_xsec()
        self._build_track()
        self._build_panels()
        self.map_bar, self.v3_bar = self._map_toolbar(), self._3d_toolbar()
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
            options=["Map", "3D"], value="Map", button_type="primary",
            button_style="outline", width=120, height=32, margin=(4, 2))
        modes = ["Sounding", "Cross-section", "3D region"]
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

        self.status = _html()
        self.cache_html = _html()
        self.clear_btn = pn.widgets.Button(name="Clear cache", button_type="default",
                                           button_style="outline", width=100, height=28,
                                           margin=(2, 6))
        self.clear_pts = pn.widgets.Button(name="", icon="eraser", button_type="light",
                                           button_style="outline", width=40, height=32,
                                           margin=(4, 2),
                                           description="Clear map markers (soundings, "
                                                       "section, 3D region)")
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
        self.rp_list = pn.widgets.Select(name="Runs here", options={}, width=620, size=7)
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
                  'below. Opening a run reloads the page; 3D caches of other runs are '
                  'freed.</div>'),
            self.rp_path, self.rp_msg, self.rp_list, self.rp_recent,
            pn.Row(self.rp_open),
            _html(f'<div class="cv-h" style="margin-top:14px">This run</div>'
                  f'<div class="cv-run"><b>{run.path}</b><br>{run.ni}×{run.nj}×{run.nk} · '
                  f'Δx {run.dx:.0f} m · {len(run.times)} times · domain motion '
                  f'({run.umove:g}, {run.vmove:g}) m/s</div>'),
            pn.Row(self.cache_html, self.clear_btn), width=680, margin=10)

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
            if os.path.isdir(p):
                runs = registry.sibling_runs(p)
                self._rp_busy = True
                try:
                    self.rp_list.options = {"/".join(r.split("/")[-3:]): r for r in runs}
                    self.rp_list.value = p if p in runs else None
                finally:
                    self._rp_busy = False

        self.rp_list.param.watch(pick, "value")
        self.rp_recent.param.watch(pick, "value")
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
        self.fig = fig
        self.map_title = _html()

    def _build_xsec(self):
        # static view: no pan/zoom, so the plot can't be dragged off the sampled data
        fig = figure(sizing_mode="stretch_width", height=430, tools="save",
                     toolbar_location="above", x_axis_label="Distance along section (km)",
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
        self.trk_metric = pn.widgets.Select(name="Track on", options=trk.METRICS, value="uh",
                                            width=200)
        self.trk_z = pn.widgets.FloatInput(name="Height (km)", value=1.0, step=0.25,
                                           start=0.0, end=float(run.z[-1]), width=90,
                                           visible=False)
        self.trk_radius = pn.widgets.FloatInput(
            name="Search radius (km)", value=5.0, step=0.5, start=0.5, width=120,
            description="How far from the expected position to look at the next time")
        self.trk_smooth = pn.widgets.FloatInput(
            name="Smoothing (km)", value=1.0, step=0.25, start=0.0, width=110,
            description="Box-average the field before picking the maximum, so the fix "
                        "follows the meso rather than single-grid-point noise")
        self.trk_stop = pn.widgets.FloatInput(
            name="Stop below", value=trk.METRIC_STOP["uh"], width=100,
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
                        "x_km, y_km and time_s / time_hms / time_index)")
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

    def _build_panels(self):
        F, run = self.F, self.run
        g3 = F.groups(ndim=3)
        self.skew_png = _html(sizing_mode="stretch_width", visible=False)
        self.prof_png = _html(sizing_mode="stretch_width", visible=False)
        self.params = _html(sizing_mode="stretch_width")
        self.snd_head = _html(
            '<div class="cv-empty">Click anywhere on the map to drop a sounding. '
            '<kbd>Shift</kbd>-click to add up to four for comparison.</div>',
            sizing_mode="stretch_width")
        self.snd_msg = _html(sizing_mode="stretch_width")
        self.snd_tabs = pn.Tabs(sizing_mode="stretch_width", dynamic=False, visible=False)
        self.prof_row = pn.Row(
            _html('<div class="cv-hint" style="margin:8px 0 0 4px">Profile panels below '
                  'go up to</div>'), self.prof_top,
            _html('<div class="cv-hint" style="margin:8px 0 0 0">km AGL</div>'),
            visible=False, margin=(4, 0, 0, 0))
        self.snd_col = pn.Column(self.snd_head, self.snd_tabs, self.skew_png, self.params,
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

        # ---- analysis panel (right of the map)
        snd_set = pn.FlexBox(self.parcel, self.wunits, self.storm, self.storm_u,
                             self.storm_v, self.avg, self.base_on, self.follow,
                             self.storm_follow, flex_wrap="wrap", align_items="flex-end",
                             gap="0 4px", sizing_mode="stretch_width",
                             styles={"border-top": f"1px solid {GRID}"})
        snd_opts = pn.Column(
            pn.FlexBox(self.mean_btn, self.pin_btn, self.snd_clear, self.compare,
                       _settings_toggle(snd_set), flex_wrap="wrap", align_items="center",
                       gap="0 4px", sizing_mode="stretch_width"),
            snd_set, sizing_mode="stretch_width", margin=0)
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
            self.xs_status, pn.pane.Bokeh(self.xs_fig, sizing_mode="stretch_width"),
            sizing_mode="stretch_width")
        trk_set = pn.FlexBox(self.trk_metric, self.trk_z, self.trk_radius, self.trk_smooth,
                             self.trk_stop, self.trk_dir, self.trk_snap, self.trk_near,
                             flex_wrap="wrap", align_items="flex-end", gap="0 4px",
                             sizing_mode="stretch_width",
                             styles={"border-top": f"1px solid {GRID}"})
        self.tabs = pn.Tabs(
            ("Sounding", pn.Column(snd_opts, self.snd_msg, self.snd_col, scroll=True,
                                   sizing_mode="stretch_both")),
            ("Cross-section", pn.Column(xs, scroll=True, sizing_mode="stretch_both")),
            ("Track", pn.Column(
                pn.FlexBox(self.trk_how, self.trk_stop_btn, self.trk_del, self.trk_clear,
                           _settings_toggle(trk_set), self.trk_advance, flex_wrap="wrap",
                           align_items="center", gap="0 4px", sizing_mode="stretch_width"),
                trk_set,
                self.trk_status,
                pn.pane.Bokeh(self.trk_fig, sizing_mode="stretch_width"),
                pn.FlexBox(self.trk_path, self.trk_save, self.trk_dl, self.trk_load,
                           flex_wrap="wrap",
                           align_items="flex-end", gap="0 4px", sizing_mode="stretch_width"),
                self.trk_table, scroll=True, sizing_mode="stretch_both")),
            sizing_mode="stretch_both", dynamic=False,
            styles={"flex": "1 1 48%", "min-width": "0"})

    def _top_bar(self):
        """Run, time and workspace pills floating across the top of the window."""
        return pn.Column(
            _bar(_group(self.workspace),
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
        vec = _pill(self.vec_on, d.add("vec", "Winds", self.vec_lvl, self.vec_frame,
                                       self.vec_density, self.vec_ref, self.vec_color))
        for b, _ in d.items.values():
            b.param.update(height=32, margin=(4, 2), button_type="light")
        d.panel.styles = dict(d.panel.styles, **{"pointer-events": "auto",
                                                 "background": "rgba(17,23,35,0.95)",
                                                 "box-shadow": "0 6px 20px rgba(0,0,0,.45)"})
        bar = _bar(_group(self.fill_var, self.fill_mode, self.fill_lvl),
                   _group(style, *ovb, vec))
        self.mode_group = _group(*self.mode.btns.values(), self.clear_pts, self.panel_btn)
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
        caption = pn.Column(self.map_title, self.hint, self.status, styles=floor, margin=0)
        map_area = pn.Column(
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
            sizing_mode="stretch_width", visible=False, margin=0,
            styles=dict(below, position="relative"))
        err = _html(f'<div class="cv-status" style="color:#f87171;padding:4px 8px">'
                    f'{self.error}</div>') if self.error else None
        objs = [o for o in (err,) if o is not None]
        return pn.Column(self._top_bar(), *objs, self.map_ws, self.v3_ws, self.rp_modal,
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
                  self.fill_nlev, self.vec_on, self.vec_frame, self.vec_color, self.vec_ref):
            w.param.watch(rm, "value")
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
            w.param.watch(rs, "value")
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
        r3 = lambda *e: self.request_3d() if self.plot3d.visible else None  # noqa: E731
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
        self.trk_metric.param.watch(self._on_trk_metric, "value")
        self.trk_stop_btn.on_click(lambda e: self._cancel_track())
        self.trk_clear.on_click(self._on_clear_track)
        self.trk_how.param.watch(self._on_trk_how, "value")
        self.trk_del.on_click(self._on_delete_fix)
        self.trk_load.on_click(self._on_load_track)
        self.trk_save.on_click(self._on_save_track)
        self.trk_path.param.watch(self._on_trk_path, "value")
        self.storm_follow.param.watch(lambda e: self._draw_points(), "value")
        self._on_trk_path(None)
        self._update_track_view()
        self._update_3d_labels()
        self._update_region_html()
        self.clear_btn.on_click(self._on_clear_cache)
        self.clear_pts.on_click(self._on_clear_points)
        self._on_mode(None, init=True)
        self._show_panel(False)  # the map gets the full width until a panel is needed
        self._update_time_html()
        if self.doc is not None:
            pn.state.add_periodic_callback(self._update_cache_html, period=3000)
        self._update_cache_html()

    def _schedule(self, fn):
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
            "Cross-section": "Click two points (A, then B) to draw a vertical section",
            "3D region": "Drag a box to choose the 3D region; it renders in the 3D view",
            "Track": "Auto-track: click the meso to follow it through time; click near the "
                     "track at another time to correct it · Place by hand: each click sets "
                     "the fix at the shown time",
        }
        self.hint.object = f'<div class="cv-hint">{hints[mode]}</div>'
        self.fig.toolbar.active_drag = self.bsel if mode == "3D region" else self.pan
        tabs = {"Sounding": 0, "Cross-section": 1, "Track": 2}
        if not init and mode in tabs:
            self._show_panel(True, tabs[mode])

    def _show_panel(self, show, tab=None):
        self.tabs.visible = show
        self.panel_btn.icon = ("layout-sidebar-right-collapse" if show
                               else "layout-sidebar-right-expand")
        if tab is not None:
            self.tabs.active = tab

    def _on_workspace(self, ev):
        is3d = ev.new == "3D"
        self.v3_ws.visible, self.map_ws.visible = is3d, not is3d
        self.mode_group.visible = not is3d
        if is3d and self.box is None:
            self._update_region_html()

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
            new = ("pt", (x, y), None)
            meso = trk.position(self.fixes, self.t)
            if self.storm_follow.value:
                if meso is None:
                    self._set_status('<span style="color:#fbbf24">No tracked meso at this '
                                     'time; the sounding stays at a fixed point</span>')
                else:
                    new = ("trk", (x - meso[0], y - meso[1]), None)
            if shift and self.points:
                self.points = (self.points + [new])[-4:]
            else:
                self.points = [new]
            self._draw_points()
            self._show_panel(True, 0)
            self.request_soundings()
        elif mode == "Track":
            self._show_panel(True, 2)
            self.request_track(x, y)
        elif mode == "Cross-section":
            self.xs_pts = [(x, y)] if len(self.xs_pts) != 1 else self.xs_pts + [(x, y)]
            self._draw_xs()
            if len(self.xs_pts) == 2:
                self._show_panel(True, 1)
                self.request_xsec()

    def _on_select(self, ev):
        if self.mode.value != "3D region" or not getattr(ev, "final", True):
            return
        g = ev.geometry
        if g.get("type") != "rect":
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
            return where
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

    def _draw_xs(self):
        pts = self.xs_pts
        self.xs_pt_src.data = dict(x=[p[0] for p in pts], y=[p[1] for p in pts],
                                   label=["A", "B"][:len(pts)])
        self.xs_line_src.data = dict(x=[p[0] for p in pts], y=[p[1] for p in pts]) \
            if len(pts) == 2 else dict(x=[], y=[])

    # ================================================================ map job
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
            res = render.compute_map(self.F, spec)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["map"]:
            self._schedule(partial(self._apply_map, res, spec, g))

    def _apply_map(self, res, spec, g):
        if g != self.gen["map"]:
            return
        if isinstance(res, Exception):
            self._set_status(f'<span style="color:#f87171">Map error: {res}</span>')
            return
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
            self.cbar_label.axis_label = F[fs["var"]].title
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
            _BASE_CACHE[key] = {v: run.read_column(v, 0, 0, 0) for v in BASE_VARS}
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
            self.params.object = ""
            self.snd_head.object = ('<div class="cv-empty">Click anywhere on the map to drop '
                                    'a sounding. <kbd>Shift</kbd>-click to add up to four '
                                    'for comparison.</div>')
            return
        spec = dict(t=self.t, points=list(self.points), avg=float(self.avg.value),
                    storm=self.storm.value,
                    custom=(self.storm_u.value or 0.0, self.storm_v.value or 0.0),
                    parcel=self.parcel.value, units=self.wunits.value,
                    zmax=float(self.prof_top.value), base=self.base_on.value,
                    style=self.compare.value,
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
                    i0, i1 = max(0, i - h), min(run.ni, i + h + 1)
                    j0, j1 = max(0, j - h), min(run.nj, j + h + 1)
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
                    if kind == "trk":
                        dx_, dy_ = where
                        rel = "meso" if dx_ == 0 and dy_ == 0 else f"meso {dx_:+.1f}, {dy_:+.1f}"
                        label = f"{POINT_LABELS[n]} {rel} km{when}"
                    else:
                        label = f"{POINT_LABELS[n]} ({x:.1f}, {y:.1f}) km{when}"
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
            st = spec["style"]
            short = [(lab.split(" ")[0] + (" mean" if "mean" in lab else "")
                      + (" meso" if "meso" in lab else "")
                      + (f' {lab.split("@ ")[1]}' if "@ " in lab else ""), c, r)
                     for lab, c, r in items]  # table column headers
            html = sp.params_html(short, base, spec["units"])
            if st == "tabs" and len(items) > 1:
                pngs = [(lab, _png(sp.skewt_hodo_figure([it], base, spec["parcel"],
                                                        spec["units"])),
                         _png(sp.profiles_figure([it], base, spec["zmax"], spec["units"])))
                        for it in items for lab in [it[0]]]
            else:
                pngs = [(None, _png(sp.skewt_hodo_figure(items, base, spec["parcel"],
                                                         spec["units"], style=st)),
                         _png(sp.profiles_figure(items, base, spec["zmax"], spec["units"],
                                                 style=st)))]
            res = (pngs, html, items)
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
        pngs, html, items = res
        self.results = items
        run = self.run
        avg = "single column" if spec["avg"] == 0 else f'{spec["avg"]:g} km box mean'
        pts = " ".join(f'<span style="color:{c};margin-right:14px">{lab}</span>'
                       for lab, c, r in items)
        self.snd_head.object = (f'<div class="cv-maptitle">t = {run.time_label(spec["t"])} · '
                                f'{avg} · {pts}</div>')
        if pngs[0][0] is None:
            self.skew_png.object, self.prof_png.object = _img(pngs[0][1]), _img(pngs[0][2])
            self.skew_png.visible = self.prof_png.visible = True
            self.snd_tabs.visible = False
        else:
            active = self.snd_tabs.active
            self.snd_tabs[:] = [(lab.replace(" km", ""), pn.Column(
                _html(_img(a), sizing_mode="stretch_width"),
                _html(_img(b), sizing_mode="stretch_width"), sizing_mode="stretch_width"))
                for lab, a, b in pngs]
            self.snd_tabs.active = min(active, len(pngs) - 1)
            self.skew_png.visible = self.prof_png.visible = False
            self.snd_tabs.visible = True
        self.params.object = html
        self.prof_row.visible = True
        self._set_status("")
        if self.vec_on.value and self.vec_frame.value == "storm":
            self.request_map()

    # ================================================================ meso track
    def _trk_opts(self):
        return dict(metric=self.trk_metric.value, zkm=float(self.trk_z.value or 0.0),
                    radius=float(self.trk_radius.value or 5.0),
                    smooth=float(self.trk_smooth.value or 0.0),
                    stop=float(self.trk_stop.value or 0.0), snap=self.trk_snap.value,
                    nearest=self.trk_near.value)

    def _on_trk_metric(self, ev):
        self.trk_z.visible = ev.new != "uh"
        self.trk_stop.value = trk.METRIC_STOP[ev.new]
        if ev.new == "w":
            self.trk_z.value = 5.0
        elif ev.new == "zeta":
            self.trk_z.value = 1.0

    def request_track(self, x, y):
        """Track from a click at the shown time.  A click near the existing track
        (same settings) corrects it from that time on, keeping the other side;
        anywhere else starts a new track."""
        opts, t0, run = self._trk_opts(), self.t, self.run
        if self.trk_how.value == "manual":
            self._place_fix(x, y, opts)
            return
        direction, existing = self.trk_dir.value, None
        same = self.trk_spec is not None and all(
            self.trk_spec.get(k) == opts[k] for k in ("metric", "zkm", "smooth", "nearest"))
        if self.fixes and same:
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
            if self.points and (self.storm.value == "track"
                                or any(k == "trk" for k, _, _ in self.points)):
                self.request_soundings()

    def _track_summary(self, note=""):
        run, ts = self.run, sorted(self.fixes)
        if not ts:
            return ('<div class="cv-empty">Pick <b>Track</b> in the click modes and click '
                    'on a mesocyclone (try 2–5 km UH or ζ as the map fill). It is followed '
                    'through time from there; the path is drawn on the map.</div>')
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
                    ref=float(self.xs_vref.value or 20.0), vcolor=self.xs_vcolor.value)
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
            fill = render.sample_section(run, F.volume(spec["fill"], t), fi, fj, zq)
            lo, hi = F.auto_range(spec["fill"], fill) if spec["auto"] else \
                (spec["vmin"], spec["vmax"])
            if hi <= lo:
                hi = lo + 1e-6
            out = dict(s=s, zq=zq, fill=fill, lo=lo, hi=hi)
            if spec["cont"]:
                c = render.sample_section(run, F.volume(spec["cont"], t), fi, fj, zq)
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
            res = out
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = e
        if g == self.gen["xs"]:
            self._schedule(partial(self._apply_xs, res, spec, g))

    def _apply_xs(self, res, spec, g):
        if g != self.gen["xs"]:
            return
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
        self.xs_cbar_label.axis_label = d.title
        (xa, ya), (xb, yb) = spec["A"], spec["B"]
        cont = f' · contours: {F[spec["cont"]].label}' if spec["cont"] else ""
        self.xs_status.object = (
            f'<div class="cv-maptitle">t = {self.run.time_label(spec["t"])} · '
            f'<b>{d.label}</b>{cont} · A ({xa:.1f}, {ya:.1f}) → B ({xb:.1f}, {yb:.1f}) km, '
            f'{s[-1]:.1f} km long</div>')

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
                    storm=self._storm_motion(),
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
                m = volume3d.isosurface(run, F.volume(iso["var"], t), spec["box"], iso["val"],
                                        stride, spec["smooth"], spec["ztop"])
                name = f'{d.label} = {iso["val"]:g} {d.units}'
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
            res = (fig, notes, nf, stride)
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
        fig, notes, nf, stride = res
        self.plot3d.object = fig
        self.plot3d.visible = True
        extra = (" · " + " · ".join(notes)) if notes else ""
        self.v3_status.object = (f'<div class="cv-status">{nf:,} triangles · '
                                 f'{"full" if stride == 1 else f"1/{stride}"} resolution'
                                 f'{extra}</div>')


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
    v = Viewer(run, fields, maxpix=maxpix, error=error)
    # the template only supplies the dark theme: header and margins are hidden so the
    # visualisations fill the window and the controls float over them
    chrome = ("#header{display:none !important} #main{padding:0 !important;"
              "overflow:hidden !important} .card-margin{margin:0 !important}"
              " #container{height:100vh}")
    return pn.template.FastListTemplate(
        title="CM1 View", theme="dark", accent=ACCENT, header_background=BG,
        main=[v.main()], theme_toggle=False, main_layout=None, raw_css=[CSS, chrome])
