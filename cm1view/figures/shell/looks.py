"""The look settings in the inspector, from the settings table (figures/settings.py): each row's
widget is a copy of the old editor's, shown from and written to the document at the scope of
the node picked.  A section's widgets are made when it is opened.

Look resolves style, then kinds[kind], then the panel's opts (spec/doc.py), so:

  Figure   writes style (a kind's block: every kind in the figure), or the figure's own keys
  Kind     writes kinds[kind] (a block no kind holds: the same as Figure)
  Panel    writes the panel's opts, and shows what it inherits otherwise"""

import copy

import panel as pn

from .. import draw as figdraw, settings as table
from ..cards import _grid
from ..cards.base import SECTION
from ..spec.doc import FIGURE_KEYS, KIND_KEYS
from . import docedit as de, nodes

FIGURE_SECTIONS = ("Text", "Panel labels", "Colorbar", "Legend", "Contour key",
                   "Maximum and minimum", "Spacing", "matplotlib style", "Your own code")
KIND_SECTIONS = {"plan": ("Area", "Axes and ticks"),
                 "sounding": ("Sounding panels", "Skew-T", "Hodograph", "Legend in the panel",
                              "Axes and ticks"),
                 "xsec": ("Area", "Axes and ticks"), "th": ("Plot", "Axes and ticks"),
                 "line": ("Plot", "Legend in the panel", "Axes and ticks"),
                 "dist": ("Plot", "Statistics", "Legend in the panel", "Axes and ticks"),
                 "profile": ("Plot", "Legend in the panel", "Axes and ticks"),
                 "joint": ("Plot", "Statistics", "Legend in the panel", "Axes and ticks"),
                 "azim": ("Plot", "Legend in the panel", "Axes and ticks"),
                 "table": ("Table",), "scene": ()}
SECTION_NAMES = {("xsec", "Area"): "Height and x axis"}  # (a kind's words for a section)
# (a plan panel's own look: what is drawn panel by panel, the rest being its grid's or the figure's)
PANEL_KEYS = {
    "plan": {"Axes and ticks": ("axes.xlabel", "axes.ylabel", "axes.ticks", "axes.minor",
                                "axes.tickdir", "axes.xstep", "axes.ystep", "axes.frame_lw",
                                "axes.grid", "axes.grid_ls"),
             "Panel labels": ("axes.title_loc", "axes.title_bold", "letters.on", "letters.loc",
                              "letters.size", "letters.bold", "letters.box", "time_label.on",
                              "time_label.fmt", "time_label.loc", "time_label.size",
                              "time_label.bold", "time_label.box", "run_label.on", "run_label.loc",
                              "run_label.size", "run_label.bold", "run_label.box",
                              "run_label.run_color", "z_label.on", "z_label.fmt", "z_label.loc",
                              "z_label.size", "z_label.bold", "z_label.box")}}
AXES_OF_A_PANEL = ("axes.xlabel", "axes.ylabel", "axes.ticks", "axes.minor", "axes.tickdir",
                   "axes.xstep", "axes.frame_lw", "axes.grid", "axes.grid_ls")
LABELS_OF_A_PANEL = tuple(k for k in PANEL_KEYS["plan"]["Panel labels"]
                          if not k.startswith(("run_label", "z_label")))
# (a panel's soundings are read and drawn with its own view, so all of skewt reaches one panel)
PANEL_KEYS["sounding"] = {
    "Axes and ticks": AXES_OF_A_PANEL, "Panel labels": LABELS_OF_A_PANEL,
    "Sounding panels": tuple(st.key for st in table.SETTINGS if st.section == "Sounding panels"),
    "Skew-T": tuple(st.key for st in table.SETTINGS if st.section == "Skew-T"),
    "Hodograph": tuple(st.key for st in table.SETTINGS if st.section == "Hodograph"),
    "Legend in the panel": ("skewt.legend", "skewt.legend_loc", "skewt.legend_ncol",
                            "skewt.legend_frame")}
# (a cross-section's: its own data and drawing go by its view, so these reach one panel)
PANEL_KEYS["xsec"] = {"Area": ("xsec.ztop", "xsec.coords"), **PANEL_KEYS["plan"]}
# (a panel's series are drawn with its view; its time range is the figure's: share_series_range)
PANEL_KEYS["th"] = {"Plot": ("ts.zmin", "ts.zmax"), **PANEL_KEYS["plan"]}
PANEL_KEYS["line"] = {
    "Plot": ("ts.ymin", "ts.ymax", "ts.zero_line", "ts.mark", "ts.mark_legend", "ts.mark_edited"),
    "Legend in the panel": ("ts.legend", "ts.legend_loc", "ts.legend_ncol", "ts.legend_frame"),
    **PANEL_KEYS["plan"]}


def _own_rows(kind, block, *sections):
    """{section: its rows' keys}, with the kind's panel legend: a panel of these kinds is read
    and drawn with its own view, so all of its block reaches one panel."""
    out = {s: tuple(st.key for st in table.SETTINGS if st.section == s and kind in st.kinds)
           for s in sections}
    if kind in figdraw.LEGEND_OPTS:
        out["Legend in the panel"] = tuple(f"{block}.{k}" for k in (
            "legend", "legend_loc", "legend_ncol", "legend_frame"))
    return out


PANEL_KEYS["dist"] = {**_own_rows("dist", "dist", "Plot", "Statistics"), **PANEL_KEYS["plan"]}
PANEL_KEYS["profile"] = {**_own_rows("profile", "prof", "Plot"), **PANEL_KEYS["plan"]}
PANEL_KEYS["joint"] = {**_own_rows("joint", "joint", "Plot", "Statistics"), **PANEL_KEYS["plan"]}
PANEL_KEYS["azim"] = {**_own_rows("azim", "azim", "Plot"), **PANEL_KEYS["plan"]}
PANEL_KEYS["table"] = {**_own_rows("table", "table", "Table"),
                       "Panel labels": PANEL_KEYS["plan"]["Panel labels"]}
PANEL_KEYS["scene"] = {"Panel labels": PANEL_KEYS["plan"]["Panel labels"]}  # (axes: it has none)
# (shown by the sounding pane, as the layout has them)
LAYOUT_HIDES = {"Skew-T": ("hodo",), "Hodograph": ("skewt",)}
LEFT_OUT = ("legend.panel", "legend.panels")  # (panels by id: M9)
SECTION_ROWS = ("xsec.ztop", "xsec.coords")  # (of cross-sections only: a plan view draws neither)


def _legend_rows():
    """A kind's own panel legend (the old editor's pl_ widgets, not in the table: they go with
    the kind shown), starting as the old editor's _legend_load does: soundings', then the
    others'."""
    return tuple(
        table.Setting(f"{block}.{key}", attr, "Legend in the panel", (kind,), default)
        for block, kind, on, loc, frame in (("skewt", "sounding", False, "upper left", True),
                                            ("ts", "line", True, "best", False),
                                            ("dist", "dist", True, "best", False),
                                            ("prof", "profile", True, "best", False),
                                            ("joint", "joint", True, "best", False),
                                            ("azim", "azim", True, "best", False))
        for key, attr, default in (("legend", "pl_on", on), ("legend_loc", "pl_loc", loc),
                                   ("legend_ncol", "pl_ncol", 1), ("legend_frame", "pl_frame", frame)))


LEGEND_ROWS = _legend_rows()
# (the old editor's widget has one name at a time, its kind's)
OWN_NAMES = {"skewt.legend": "Legend (one sounding)", "ts.legend": "Legend", "dist.legend": "Legend",
             "prof.legend": "Legend", "joint.legend": "Legend", "azim.legend": "Legend",
             # (shorter than the old editor's: these sit in a column of two)
             "joint.cbar_label": "Colorbar label", "azim.cbar_label": "Colorbar label"}
BLOCK_WORDS = {"letters": "Letter", "time_label": "Time label", "run_label": "Run label",
               "z_label": "Height label", "axes": "Axes", "skewt": "Sounding"}


def _split(st):
    block, _, key = st.key.rpartition(".")
    return block, key


def kind_block(block):
    """Whether a block of settings goes under kinds (spec/doc.py's KIND_KEYS)."""
    return any(block in keys for keys in KIND_KEYS.values())


class Scope:
    """Where the settings of a node live.  kind: its kind; pid: its panel."""

    def __init__(self, kind=None, pid=None):
        self.kind, self.pid = kind, pid

    def _layers_up(self, doc, block):
        """The dictionaries a setting of `block` resolves through, last wins."""
        kinds = doc.get("kinds") or {}
        out = [doc.get("style") or {}]
        if self.kind is not None:
            out.append(kinds.get(self.kind) or {})
        elif kind_block(block):  # (the figure: as the first kind has it)
            out.append(next(iter(kinds.values()), {}))
        if self.pid is not None:
            out.append(de.panel_by_id(doc, self.pid).get("opts") or {})
        return out

    def value(self, doc, st):
        """Setting st's value here, as its widget shows it (table.KEEP: its widget's own)."""
        block, key = _split(st)
        if not block:
            held = doc if key in FIGURE_KEYS else {}
            for d in self._layers_up(doc, key):
                if key in d:
                    held = d
            return st.as_.show(held[key]) if key in held else (
                table.KEEP if st.default is table.KEEP else st.as_.show(st.default))
        held = dict(doc[block]) if block in FIGURE_KEYS and isinstance(doc.get(block), dict) else {}
        for d in self._layers_up(doc, block):
            if isinstance(d.get(block), dict):
                held.update(d[block])
        if key == "*":
            return st.as_.show(held)
        if block in table.PREPARED:  # (their saved form differs from their widgets')
            held = table._prepared({block: held})[block]
        if key in held:
            return st.as_.show(held[key])
        return table.KEEP if st.default is table.KEEP else st.as_.show(st.default)

    def _targets(self, doc, top):
        """The dictionaries to write a setting of block (or top-level key) `top` to."""
        if self.pid is not None:
            return [de.panel_by_id(doc, self.pid).setdefault("opts", {})]
        if top in FIGURE_KEYS:
            return [doc]
        if kind_block(top):
            kinds = doc.setdefault("kinds", {})
            names = [self.kind] if self.kind else list(kinds) or ["plan"]
            return [kinds.setdefault(k, {}) for k in names]
        return [doc.setdefault("style", {})]

    def write(self, doc, st, value):
        """Setting st takes its widget's value."""
        block, key = _split(st)
        read = st.as_.read(value)
        for d in self._targets(doc, block or key):
            if not block:
                d[key] = read
            elif key == "*":
                d[block] = dict(d.get(block) or {}, **read)
            else:
                d[block] = dict(d.get(block) or {}, **{key: read})
        if st.key == "letters.on" and self.pid is None:  # (by hand: no longer the count's)
            style = doc.setdefault("style", {})
            style["letters"] = dict(style.get("letters") or {}, auto=False)

    def own_keys(self, doc, keys):
        """Those of the settings `keys` the panel of this scope has of its own."""
        opts = de.panel_by_id(doc, self.pid).get("opts") or {} if self.pid is not None else {}
        out = []
        for k in keys:
            block, _, key = k.rpartition(".")
            if isinstance(opts.get(block), dict) and key in opts[block]:
                out.append(k)
        return out

    def take_back(self, doc, key):
        """A panel's own setting gone: it inherits again."""
        p = de.panel_by_id(doc, self.pid)
        block, _, name = key.rpartition(".")
        opts = p.get("opts") or {}
        if isinstance(opts.get(block), dict):
            opts[block].pop(name, None)
            if not opts[block]:
                opts.pop(block)
        if not opts:
            p.pop("opts", None)


def panels_differ(doc, kind, keys):
    """The panels of a kind with a setting of `keys` of their own: {letter: [keys]}."""
    names, out = nodes.letters(doc), {}
    for p in de.panels_of(doc, kind):
        own = Scope(kind, p["id"]).own_keys(doc, keys)
        if own:
            out[names[p["id"]]] = own
    return out


def rows_of(section, kinds, only=None):
    """The table's rows of a section reaching any of `kinds` (only: of those keys)."""
    out = []
    seen = set()
    for st in (*table.SETTINGS, *LEGEND_ROWS):
        if st.section != section or st.key in LEFT_OUT or st.key in seen:
            continue
        if st.key in SECTION_ROWS and "xsec" not in kinds:
            continue
        if only is not None and st.key not in only:
            continue
        if any(k in st.kinds for k in kinds):
            out.append(st)
            seen.add(st.key)
    return out


def make_widget(ed, st, shown, on_change):
    """A copy of the old editor's widget for setting st, showing `shown`, on its own."""
    w = table.widget_of(ed, st).clone(visible=True, disabled=False)
    if st.key in OWN_NAMES:
        w.name = OWN_NAMES[st.key]
    if shown is not table.KEEP:
        try:
            w.value = shown
        except ValueError:  # (a value its list doesn't have)
            pass
    w.param.watch(lambda ev: on_change(st, w), "value")
    return w


class Sections:
    """The collapsible sections of look settings of one node.  extras: {section: widgets to
    add (a function)}; redraws: the keys that change which sections there are, so the node is
    shown anew."""

    def __init__(self, inspector, scope, kinds, extras=None, redraws=()):
        self.ins, self.shell, self.scope, self.kinds = inspector, inspector.shell, scope, kinds
        self.extras = extras or {}
        self.redraws = redraws

    def _on_change(self, st, w):
        self.shell.edit(lambda d: self.scope.write(d, st, w.value),
                        node=self.shell.node if st.key in self.redraws else None)

    def card(self, section, only=None):
        """The card of a section (None when it has no rows)."""
        rows = rows_of(section, self.kinds, only)
        extra = self.extras.get(section)
        if not rows and extra is None:
            return None
        key = f"look:{self.scope.pid}:{self.scope.kind}:{section}"
        folds = self.ins.folds
        title = next((SECTION_NAMES[(k, section)] for k in self.kinds
                      if (k, section) in SECTION_NAMES), section)
        card = pn.Card(title=title, collapsed=True, **SECTION)

        def fill():
            if not card.objects:
                card.objects = self._body(section, rows, extra)

        def on_fold(ev):
            folds[key] = not ev.new
            if not ev.new:
                fill()

        card.param.watch(on_fold, "collapsed")
        if folds.get(key):
            card.collapsed = False
        return card

    def _body(self, section, rows, extra):
        doc, ed = self.shell.doc, self.shell.ed
        out = []
        by_key = {}
        for st in rows:
            if st.key == "time_label.t0_min" and not self.scope.value(doc, st):
                continue  # (an older figure's: run time zeros do this now)
            w = make_widget(ed, st, self.scope.value(doc, st), self._on_change)
            by_key[st.key] = w
            out.append(w)
        objs = [_grid(*out, n=2)] if out else []
        if extra is not None:
            objs += extra(by_key)
        return objs

    def chips(self, keys):
        """A panel's own settings of `keys`, each to take back (↺)."""
        own = self.scope.own_keys(self.shell.doc, keys)
        if not own:
            return []
        names = {st.key: table.widget_of(self.shell.ed, st).name
                 for st in (*table.SETTINGS, *LEGEND_ROWS)}
        names.update(OWN_NAMES)

        def back(key):
            self.shell.edit(lambda d: self.scope.take_back(d, key), node=self.shell.node)

        words = [names.get(k) or k for k in own]
        chips = []
        for key, word in zip(own, words):
            if words.count(word) > 1:  # (letter's and time label's "Where": which)
                word = f"{BLOCK_WORDS.get(key.partition('.')[0], key.partition('.')[0])} {word}"
            b = pn.widgets.Button(name=f"↺ {word}", height=26, margin=(2, 2),
                                  button_type="light", button_style="outline",
                                  description="Back to what all panels have")
            b.on_click(lambda e, k=key: back(k))
            chips.append(b)
        return [pn.FlexBox(*chips, sizing_mode="stretch_width")]


def key_layer_widget(shell, doc, block, types, first):
    """The layer the contour key or Maximum / minimum speaks for: a shared one by id."""
    fields = shell.fields
    opts = {first: -1}
    for lid, lay in (doc.get("layers") or {}).items():
        if lay.get("type") in types:
            name = lay.get("field")
            label = fields[name].label if fields is not None and name in fields else str(name)
            opts[f"{TYPE_NAME.get(lay['type'], lay['type'])}: {label} ({lid})"] = lid
    now = ((doc.get("style") or {}).get(block) or {}).get("layer", -1)
    w = pn.widgets.Select(name="Of the layer", options=opts, value=now if now in opts.values()
                          else -1, sizing_mode="stretch_width")

    def on_pick(ev):
        def apply(d):
            style = d.setdefault("style", {})
            style[block] = dict(style.get(block) or {}, layer=ev.new)
        shell.edit(apply)

    w.param.watch(on_pick, "value")
    return w


def sounding_extra(layout):
    """What sounding settings show hangs on their neighbours and the layout, as the old editor's
    _show_storm has it: {section: extra} for Sections."""
    def extra(by_key):
        def key(name):
            return by_key.get(f"skewt.{name}")

        def value(name):
            return None if key(name) is None else key(name).value

        def show(*ev):
            inset, whole = layout == "inset", layout in ("side", "hodo")
            for names, on in ((("storm_u", "storm_v"), value("storm") == "custom"),
                              (("hodo_heights",), value("hodo_labels") is not False),
                              (("hodo_key", "srh"), whole),
                              (("hodo_key_loc", "hodo_key_ncol", "hodo_key_frame"),
                               whole and value("hodo_key") is not False),
                              (("hodo_cu", "hodo_cv"), value("hodo_center") == "custom"),
                              (("hodo_max",), value("hodo_center") != "fit"),
                              (("inset_loc", "inset_size"), inset),
                              (("inset_x", "inset_y"), inset and value("inset_loc") == "custom")):
                for n in names:
                    if key(n) is not None:
                        key(n).visible = on

        for name in ("storm", "hodo_center", "inset_loc", "hodo_labels", "hodo_key"):
            if key(name) is not None:
                key(name).param.watch(show, "value")
        show()
        return []

    return {"Sounding panels": extra, "Hodograph": extra}


def dist_extra():
    """What a distribution's settings show hangs on the kind of plot, as the old editor's
    _show_dist_opts has it: {section: extra} for Sections."""
    def plot(by_key):
        def key(name):
            return by_key[f"dist.{name}"]

        def show(*ev):
            kind = key("plot").value
            hist, cum, boxy = kind == "hist", kind == "ecdf", kind in ("box", "violin")
            for name in ("norm", "bins", "width", "hstyle", "bar_labels"):
                key(name).visible = hist
            key("cum").visible = cum
            for name in ("whis", "means", "horizontal"):
                key(name).visible = boxy
            for name, end in (("ymin", "from"), ("ymax", "to")):
                key(name).visible = not boxy
                key(name).name = f"{'Fraction' if cum else 'Count'} axis {end}"

        key("plot").param.watch(show, "value")
        show()
        return []

    def stats(by_key):
        def show(*ev):
            by_key["dist.stats_loc"].visible = by_key["dist.stats_at"].value == "box"

        by_key["dist.stats_at"].param.watch(show, "value")
        show()
        return []

    return {"Plot": plot, "Statistics": stats}


def joint_extra():
    """... and a joint distribution's: the old editor's _show_joint_opts."""
    def plot(by_key):
        def key(name):
            return by_key[f"joint.{name}"]

        def show(*ev):
            kind = key("plot").value
            for name in ("norm", "cmap", "cbar_label", "log", "reverse", "colorbar"):
                key(name).visible = kind == "hist"
            key("ms").visible = key("alpha").visible = kind == "scatter"
            key("contours").visible = kind != "contour"

        key("plot").param.watch(show, "value")
        show()
        return []

    return {"Plot": plot}


TYPE_NAME = {"fill": "Fill", "contour": "Contours", "shade": "Shading"}


def area_extra(shell, scope):
    """The Area section's box, which is written whole (x min ... y max), shown while the area
    is a fixed box; the half-width while it follows the storm."""
    def extra(by_key):
        doc = shell.doc
        kinds = doc.get("kinds") or {}
        dom = copy.deepcopy((kinds.get(scope.kind) or {}).get("domain") or {})
        box = list(dom.get("box") or [None] * 4)
        ed = shell.ed
        ws = [src.clone(value=box[n], visible=True, disabled=False) for n, src in enumerate(
            (ed.box_x0, ed.box_x1, ed.box_y0, ed.box_y1))]
        note = pn.pane.HTML(margin=(0, 4), sizing_mode="stretch_width")
        mode = by_key.get("domain.mode")
        half = by_key.get("domain.half")
        col = pn.Column(_grid(*ws, n=2), note, margin=0, sizing_mode="stretch_width")

        def on_box(ev):
            b = [w.value for w in ws]
            ok = None not in b and b[1] > b[0] and b[3] > b[2]
            note.object = "" if ok else (
                '<div class="cv-status" style="color:#f87171">The box needs x max above x min '
                'and y max above y min.</div>')
            if ok:
                def apply(d):
                    k = d.setdefault("kinds", {}).setdefault(scope.kind, {})
                    k["domain"] = dict(k.get("domain") or {}, box=[float(v) for v in b])
                shell.edit(apply)

        def on_mode(*ev):
            m = mode.value if mode is not None else dom.get("mode")
            col.visible = m == "box"
            if half is not None:
                half.visible = m == "storm"
            if m == "box" and None in [w.value for w in ws]:  # (a start: the map's view)
                for w, v in zip(ws, shell.v.view):
                    w.value = round(float(v), 2)

        for w in ws:
            w.param.watch(on_box, "value")
        if mode is not None:
            mode.param.watch(on_mode, "value")
        on_mode()
        return [col]

    return extra
