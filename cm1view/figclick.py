"""Figure editor: placing things by clicking the preview.  A click in a panel of the
preview is turned into that panel's axis units (km, minutes, values; temperature and
pressure in a skew-T) and starts or finishes what the "Click to" list says: text, a
marker, an arrow, a line, a box, a circle, or the A–B of the cross-section (on a plan
view).  Dragging does the two clicks of those in one go, moves an annotation (its
text, marker or centre moves it all; an end moves that end), or sets the plan-view
area to the box dragged.

A mixin of the FigureEditor (cm1view/figui.py), and the clickable image."""

import math

import panel as pn
import param
from panel.reactive import ReactiveHTML

from .figparts import ANN_FIELDS, _hint

PLACE = {"Click: nothing": "", "Click to add text": "text",
         "Click to add a marker": "marker", "Click twice: arrow (text, then tip)": "arrow",
         "Click twice: line": "line", "Click twice: box (corners)": "box",
         "Click twice: circle (centre, edge)": "circle",
         "Click twice: section A–B (plan views)": "section",
         "Drag: move an annotation": "move",
         "Drag a box: plan-view area": "area"}
TWO = ("arrow", "line", "box", "circle", "section")
DRAG = ("move", "area")  # (modes that need a drag, not a click)
LINEAR = ("plan", "xsec", "th", "line", "sounding")  # (panels whose axes clicks map onto)
GRAB = 0.06  # how near (a fraction of the panel) a drag must start to grab a point


class ClickImage(ReactiveHTML):
    """An image that reports where it is clicked or dragged, as fractions of its width
    and height from the upper left: click = [x, y, n], drag = [x0, y0, x1, y1, n] (n: a
    count, so the same spot twice is a new event).  band: show the box being dragged."""

    src = param.String(default="")
    css = param.String(default="")
    band = param.Boolean(default=False)
    click = param.List(default=[])
    drag = param.List(default=[])

    _template = (
        '<div id="wrap" style="position:relative;line-height:0">'
        '<img id="img" src="${src}" style="${css}" draggable="false" '
        'onmousedown="${script(\'down\')}" onmousemove="${script(\'move\')}" '
        'onmouseup="${script(\'up\')}" onmouseleave="${script(\'leave\')}"></img>'
        '<div id="box" style="position:absolute;display:none;pointer-events:none;'
        'border:1px dashed #f59e0b;background:rgba(245,158,11,0.12)"></div></div>')
    _scripts = {
        "down": """
            const e = state.event;
            if (e.button !== 0) return;
            e.preventDefault();
            state.d = [e.clientX, e.clientY];
        """,
        "move": """
            const e = state.event;
            if (!state.d || !data.band) return;
            const w = wrap.getBoundingClientRect();
            const x0 = Math.min(state.d[0], e.clientX), y0 = Math.min(state.d[1], e.clientY);
            box.style.left = (x0 - w.left) + 'px';
            box.style.top = (y0 - w.top) + 'px';
            box.style.width = Math.abs(e.clientX - state.d[0]) + 'px';
            box.style.height = Math.abs(e.clientY - state.d[1]) + 'px';
            box.style.display = 'block';
        """,
        "up": """
            const e = state.event, r = img.getBoundingClientRect();
            const d = state.d;
            state.d = null;
            box.style.display = 'none';
            if (!d || !r.width || !r.height) return;
            state.n = (state.n || 0) + 1;
            const fx = (x) => (x - r.left) / r.width, fy = (y) => (y - r.top) / r.height;
            if (Math.hypot(e.clientX - d[0], e.clientY - d[1]) < 4)
                data.click = [fx(e.clientX), fy(e.clientY), state.n];
            else
                data.drag = [fx(d[0]), fy(d[1]), fx(e.clientX), fy(e.clientY), state.n];
        """,
        "leave": """
            state.d = null;
            box.style.display = 'none';
        """}


def place_map(fig, spec, size_px, dpi):
    """{data key: (left, right, top, bottom) as fractions of the saved image, xlim,
    ylim, skew} of the panels whose axes clicks map onto (plain linear axes, and
    skew-T panels: skew = (skew, bottom pressure), else None), for the preview just
    saved from fig (its trimmed box, if any, recorded by watch_tight)."""
    kinds = {}
    for k, part in enumerate(spec.get("parts") or [spec]):
        kinds[k] = part["kind"]
    tb = getattr(fig, "_cv_tight", None)  # inches
    W, H = size_px[0] / dpi, size_px[1] / dpi
    if tb is not None:
        pad = float(spec.get("export", {}).get("pad", 0.05))
        x0, y1 = tb.x0 - pad, tb.y1 + pad
    else:
        x0, y1 = 0.0, float(fig.get_size_inches()[1])
    out = {}
    for i, ax in (getattr(fig, "_cv_axes", None) or {}).items():
        if kinds.get(int(i) // 1000 if spec.get("kind") == "combo" else 0) not in LINEAR:
            continue
        skew = getattr(ax, "_cv_skew", None)
        if getattr(ax, "_cv_hodo", False) or ax.get_xscale() != "linear" or (
                ax.get_yscale() != "linear" and skew is None):
            continue
        e = ax.get_window_extent()
        f = fig.dpi
        out[i] = ((e.x0 / f - x0) / W, (e.x1 / f - x0) / W, (y1 - e.y1 / f) / H,
                  (y1 - e.y0 / f) / H, tuple(ax.get_xlim()), tuple(ax.get_ylim()),
                  None if skew is None else tuple(float(v) for v in skew))
    return out


def to_data(b, u, w):
    """Axis units of the point at fractions (u from the left, w from the bottom) of
    panel box b (a place_map entry): x, y, or in a skew-T temperature and pressure."""
    xl, yl, skew = b[4], b[5], b[6]
    x = xl[0] + u * (xl[1] - xl[0])
    if skew is None:
        return x, yl[0] + w * (yl[1] - yl[0])
    p = math.exp(math.log(yl[0]) + w * (math.log(yl[1]) - math.log(yl[0])))
    return x - skew[0] * math.log(skew[1] / p), p


def to_frac(b, x, y):
    """The inverse of to_data: fractions (u, w) of the panel at axis units x, y."""
    xl, yl, skew = b[4], b[5], b[6]
    if skew is not None:
        y = max(float(y), 1e-6)
        x = x + skew[0] * math.log(skew[1] / y)
        w = (math.log(yl[0]) - math.log(y)) / (math.log(yl[0]) - math.log(yl[1]))
    else:
        w = (y - yl[0]) / ((yl[1] - yl[0]) or 1e-9)
    return (x - xl[0]) / ((xl[1] - xl[0]) or 1e-9), w


def watch_tight(fig):
    """Record the trimmed box (inches) savefig computes for fig (fig._cv_tight)."""
    orig = fig.get_tightbbox

    def spy(*a, **kw):
        b = orig(*a, **kw)
        fig._cv_tight = b
        return b

    fig.get_tightbbox = spy


class FigureClick:
    _place = {}  # data key -> panel box and axis ranges in the shown preview
    _place_spec = None  # the spec the preview was drawn from
    _pending = None  # (panel, x, y) of a two-click placement's first click

    def _build_click(self):
        self.place_mode = pn.widgets.Select(options=PLACE, value="", width=230,
                                            margin=(4, 4))
        self.place_mode.param.watch(lambda e: self._on_place_mode(), "value")
        self.place_hint = _hint("", margin=(0, 8))
        self.place_hint.visible = False

    def _on_place_mode(self):
        self._pending = None
        mode = self.place_mode.value
        self.place_hint.visible = bool(mode)
        self.image.band = mode in ("box", "area")
        if mode == "section":
            text = ("Click A, then B, in a plan view (or drag from A to B): the figure's "
                    "section line (a Section line layer shows it).")
        elif mode == "move":
            text = ("Drag an annotation in the preview: from its text, marker, centre or "
                    "middle to move it all, from an end to move that end.")
        elif mode == "area":
            text = ("Drag a box in a plan view: the panels show that area (<b>Area</b> → "
                    "Fixed box).")
        else:
            text = ("Click in a panel of the preview" + (" twice, or drag from the first "
                                                          "point to the second"
                                                          if mode in TWO else "")
                    + "; the new item is in <b>Annotate</b>, to fine-tune. In a skew-T, "
                      "positions are temperature (°C) and pressure (hPa).")
        self.place_hint.object = f'<div class="cv-hint">{text}</div>'
        self._show_image()

    def _locate(self, fx, fy):
        """(panel j, its place_map entry, u, w) of a point of the preview (u, w:
        fractions of the panel from the left and bottom), or None (the status line
        says why)."""
        hit = next(((i, b) for i, b in self._place.items()
                    if b[0] <= fx <= b[1] and b[2] <= fy <= b[3]), None)
        if hit is None:
            self._status("Click inside a panel (plan views, sections, time–height, "
                         "time series or skew-Ts)." if self._place else
                         "Clicks place things in plan views, sections, time–height, "
                         "time-series and skew-T panels.", True)
            return None
        i, b = hit
        k, j = divmod(int(i), 1000) if (self._place_spec or {}).get("kind") == "combo" \
            else (0, int(i))
        if self._multi_part() and k != self.part_i:
            self._status(f"That panel is in part {k + 1}: pick it in <b>Figure parts</b> "
                         "to place things there.", True)
            return None
        u = (fx - b[0]) / max(b[1] - b[0], 1e-9)
        w = (b[3] - fy) / max(b[3] - b[2], 1e-9)
        return j, b, u, w

    def _on_click(self, ev):
        if not ev.new or not self.place_mode.value:
            return
        if self.place_mode.value in DRAG:
            self._status("Drag (press, move, release) in the preview to "
                         + ("move an annotation." if self.place_mode.value == "move" else
                            "draw the plan-view area."), True)
            return
        got = self._locate(float(ev.new[0]), float(ev.new[1]))
        if got is not None:
            j, b, u, w = got
            x, y = to_data(b, u, w)
            self._placed(j, round(x, 2), round(y, 2))

    def _on_drag(self, ev):
        if not ev.new or not self.place_mode.value:
            return
        mode = self.place_mode.value
        got = self._locate(float(ev.new[0]), float(ev.new[1]))
        if got is None:
            return
        j, b, u0, w0 = got
        u1 = u0 + (float(ev.new[2]) - float(ev.new[0])) / max(b[1] - b[0], 1e-9)
        w1 = w0 - (float(ev.new[3]) - float(ev.new[1])) / max(b[3] - b[2], 1e-9)
        if mode == "move":
            self._move_annotation(j, b, (u0, w0), (u1, w1))
            return
        (x0, y0), (x1, y1) = to_data(b, u0, w0), to_data(b, u1, w1)
        if mode == "area":
            self._place_area(j, (x0, y0), (x1, y1))
            return
        self._pending = None  # (a drag: both points of a two-point item)
        self._placed(j, round(x0, 2), round(y0, 2))
        if mode in TWO:
            self._placed(j, round(x1, 2), round(y1, 2))

    def _placed(self, j, x, y):
        mode = self.place_mode.value
        if mode in TWO and (self._pending is None or self._pending[0] != j):
            self._pending = (j, x, y)
            self._status(f"First point ({x:g}, {y:g}): now click the second.")
            return
        if mode == "section":
            self._place_section(j, self._pending[1:], (x, y))
            self._pending = None
            return
        a = dict(kind=mode, panel=j, coords="data", x=x, y=y, x2=x, y2=y,
                 text="A" if mode == "text" else "", color="#000000",
                 size=10.0 if mode != "marker" else 8.0, lw=1.5, ls="-", r=1.0)
        if mode in TWO:
            (_, x1, y1), self._pending = self._pending, None
            a.update(x=x1, y=y1, x2=x, y2=y)
            if mode == "circle":
                a.update(x2=x1, y2=y1, r=round(((x - x1) ** 2 + (y - y1) ** 2) ** 0.5, 2))
        self.ann_rows.append(self._ann_row(a))
        self._show_anns()
        self._status(f"Added {mode} in panel {j + 1}: see <b>Annotate</b>.")
        self.request()

    def _place_section(self, j, p1, p2):
        """A–B from two clicks in a plan view (in its axis units: grid or storm km)."""
        if self.kind.value != "plan":
            self._status("Click the section's ends in a plan view.", True)
            return
        d = self._place_origin.get(j, (0.0, 0.0))
        a = [round(p1[0] + d[0], 2), round(p1[1] + d[1], 2)]
        b = [round(p2[0] + d[0], 2), round(p2[1] + d[1], 2)]
        self.spec["xsec"] = dict(self.spec["xsec"], a=a, b=b)
        hold, self._hold = self._hold, True
        try:
            self.xs_mode.value = "fixed"
        finally:
            self._hold = hold
        if not any(c.type == "line" and c.w["on"].value for c in self.cards):
            self._add_layer("line")  # (shows the line, and the section settings)
        self._show_region()
        self._status(f"Section A ({a[0]:g}, {a[1]:g}) → B ({b[0]:g}, {b[1]:g}) km.")
        self.request()

    def _place_area(self, j, p1, p2):
        """The plan-view area from a box dragged in a plan view (grid km)."""
        if self.kind.value != "plan":
            self._status("Drag the area in a plan view.", True)
            return
        d = self._place_origin.get(j, (0.0, 0.0))
        xs = sorted((p1[0] + d[0], p2[0] + d[0]))
        ys = sorted((p1[1] + d[1], p2[1] + d[1]))
        box = [round(v, 2) for v in (*xs, *ys)]
        self.spec["domain"] = dict(self.spec["domain"], box=box)
        hold, self._hold = self._hold, True
        try:
            self.dom.value = "box"
        finally:
            self._hold = hold
        self._show_region()
        self._status("Area x {:g} – {:g}, y {:g} – {:g} km.".format(*box))
        self.request()

    def _move_annotation(self, j, b, start, end):
        """Move the annotation of panel j grabbed at `start` (panel fractions) to `end`:
        all of it, or the end grabbed."""
        best = None
        for r in self.ann_rows:
            a = r.collect()
            if int(a.get("panel", -1)) not in (-1, j):
                continue
            for grip, (u, w) in _grips(a, b, start).items():
                dist = math.hypot(u - start[0], w - start[1])
                if dist < GRAB and (best is None or dist < best[0]):
                    best = (dist, r, a, grip)
        if best is None:
            self._status("No annotation there: start the drag on one (its text, marker, "
                         "centre, middle or an end).", True)
            return
        _, row, a, grip = best
        du, dw = end[0] - start[0], end[1] - start[1]
        axes = a.get("coords") == "axes"
        new = {}
        pts = {"all": [("x", "y"), ("x2", "y2")], "1": [("x", "y")], "2": [("x2", "y2")]}
        for kx, ky in pts[grip if grip in pts else "all"]:
            if kx not in a and ky not in a:
                continue
            x, y = float(a.get(kx, a.get("x", 0.0))), float(a.get(ky, a.get("y", 0.0)))
            if a["kind"] == "vline":  # (moves sideways only; hline: up and down)
                y = to_data(b, *start)[1]
            u, w = (x, y) if axes else to_frac(b, x, y)
            x, y = (u + du, w + dw) if axes else to_data(b, u + du, w + dw)
            if kx in a:
                new[kx] = round(x, 4 if axes else 2)
            if ky in a and a["kind"] != "vline":
                new[ky] = round(y, 4 if axes else 2)
        hold, self._hold = self._hold, True
        try:
            for k, v in new.items():
                row.w[k].value = v
        finally:
            self._hold = hold
        row._show()
        self._status(f"Moved the {a['kind']}" + (" (one end)" if grip in ("1", "2") else "")
                     + ": see <b>Annotate</b>.")
        self.request()

    _place_origin = {}  # panel -> grid km of the axes' (0, 0) (storm-relative plan views)


def _grips(a, b, start):
    """{grip: (u, w) panel fractions} of annotation a: "all" (its text, marker, centre
    or middle: moves it all), "1" and "2" (the ends of an arrow, line or box)."""
    use = ANN_FIELDS.get(a.get("kind", "text"), ())
    axes = a.get("coords") == "axes"

    def frac(x, y):
        return (float(x), float(y)) if axes else to_frac(b, float(x), float(y))

    kind = a.get("kind")
    if kind == "vline":  # (grabbed anywhere along it)
        return {"all": (to_frac(b, float(a["x"]), to_data(b, *start)[1])[0], start[1])}
    if kind == "hline":
        return {"all": (start[0], to_frac(b, to_data(b, *start)[0], float(a["y"]))[1])}
    p1 = frac(a.get("x", 0.0), a.get("y", 0.0))
    if "x2" not in use:
        return {"all": p1}
    p2 = frac(a.get("x2", 0.0), a.get("y2", 0.0))
    return {"1": p1, "2": p2, "all": (0.5 * (p1[0] + p2[0]), 0.5 * (p1[1] + p2[1]))}
