"""The look settings in the inspector, from the settings table (figures/settings.py): each row's
widget is a copy of the old editor's, shown from and written to the document at the scope of
the node picked.  A section's widgets are made when it is opened.

Look resolves style, then kinds[kind], then the panel's opts (spec/doc.py), so:

  Figure   writes style (a kind's block: every kind in the figure), or the figure's own keys
  Kind     writes kinds[kind] (a block no kind holds: the same as Figure)
  Panel    writes the panel's opts, and shows what it inherits otherwise

A section says what is changed in it (a count on its header; open, the settings' names, a bar by
each and a reset).  Changed means what a reset would undo: at a panel, and for a kind's own
colorbar, a value of its own over what it inherits; otherwise, a value other than a new figure's
of that kind (spec.fresh_look), which is not the settings table's default."""

import copy
import html

import panel as pn

from ...theme import ACCENT
from .. import draw as figdraw, settings as table
from ..cards import _grid, _hint
from ..cards.base import FIG_LOCS, LOCS, SECTION
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
LEFT_OUT = ("legend.panel", "legend.panels")  # (panels by id, not place: legend_extra)
OF_A_KIND = ("colorbar",)  # (not under kinds until a kind's node writes it: kind_bar_rows)
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


# (shown by a section's extras, not its table rows: they count as changed and reset with it)
EXTRA_ROWS = (table.Setting("contour_key.layer", "", "Contour key", table.KEY, -1),
              table.Setting("extremes.layer", "", "Maximum and minimum", table.ALL, -1),
              table.Setting("legend.panel", "", "Legend", table.ALL, 0),
              table.Setting("legend.panels", "", "Legend", table.ALL, None),
              table.Setting("domain.box", "", "Area", ("plan",), None))
ROW_WORDS = {"contour_key.layer": "Of the layer", "extremes.layer": "Of the layer",
             "legend.panel": "In panel", "legend.panels": "From panels",
             "domain.box": "Fixed box", "code.text": "The code"}
NO_RESET = ("Your own code",)  # (someone's work, not a look: it can be blanked by hand)
MARK = {"box-shadow": f"-4px 0 0 0 {ACCENT}"}  # (a row changed: outside it, so nothing moves)
FOUND = {"outline": f"2px solid {ACCENT}", "outline-offset": "2px"}  # (the row Find went to)


def _split(st):
    block, _, key = st.key.rpartition(".")
    return block, key


def _same(a, b):
    """Whether two widget values read the same: every blank is one, a number whatever its type."""
    blank = (None, "", [], ())
    if a in blank or b in blank:
        return a in blank and b in blank
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        pass
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) == list(b)
    return a == b


def row_words(ed, keys):
    """{setting's key: its name in words}, saying which label a "Where" or "Bold" is of when `keys`
    has several of a name."""
    names = {st.key: table.widget_of(ed, st).name for st in (*table.SETTINGS, *LEGEND_ROWS)}
    names.update(OWN_NAMES, **ROW_WORDS)
    words = [names.get(k) or k for k in keys]
    out = {}
    for key, word in zip(keys, words):
        if words.count(word) > 1:
            head = key.partition(".")[0]
            word = f"{BLOCK_WORDS.get(head, head)} {word}"
        out[key] = word
    return out


_DOMAIN_MODE = table.Setting("domain.mode", "", "Area", ("plan",), "storm")


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
        if self.kind and top in OF_A_KIND:
            return [doc.setdefault("kinds", {}).setdefault(self.kind, {})]
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

    def inherits(self, st):
        """Whether setting st here is a value of its own over what is above, rather than the top."""
        block, key = _split(st)
        return self.pid is not None or (self.kind is not None and (block or key) in OF_A_KIND)

    def _own_block(self, doc):
        if self.pid is not None:
            return de.panel_by_id(doc, self.pid).get("opts") or {}
        return (doc.get("kinds") or {}).get(self.kind) or {}

    @staticmethod
    def _names_in(st):
        """The keys of its block setting st writes."""
        key = _split(st)[1]
        return list(st.as_.read(st.as_.show({}))) if key == "*" else [key]

    def has_own(self, doc, st):
        """Whether this panel or kind has setting st of its own (inherits)."""
        block, key = _split(st)
        held = self._own_block(doc)
        if not block:
            return key in held
        sub = held.get(block)
        return isinstance(sub, dict) and any(k in sub for k in self._names_in(st))

    def take_own(self, doc, st):
        """Its own setting st gone: it inherits again."""
        block, key = _split(st)
        held = self._own_block(doc)
        if not block:
            held.pop(key, None)
        elif isinstance(held.get(block), dict):
            for k in self._names_in(st):
                held[block].pop(k, None)
            if not held[block]:
                held.pop(block)
        if self.pid is not None and not held:
            de.panel_by_id(doc, self.pid).pop("opts", None)


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
        self.live = {}  # section -> what its marks are on
        inspector.live.append(self)

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
        mark_rows = [*rows, *(st for st in EXTRA_ROWS if st.section == section and only is None
                              and any(k in st.kinds for k in self.kinds))]
        marks = self.live[section] = dict(card=card, rows=mark_rows, widgets={}, line=None,
                                          note=None, header=None)
        self._mark(marks)

        def fill():
            if not card.objects:
                card.objects = self._body(section, rows, extra, marks)

        def on_fold(ev):
            folds[key] = not ev.new
            if not ev.new:
                fill()

        card.param.watch(on_fold, "collapsed")
        if folds.get(key):
            card.collapsed = False
        return card

    def _body(self, section, rows, extra, marks):
        doc, ed = self.shell.doc, self.shell.ed
        out = []
        by_key = {}
        found = self.ins.pin_key()
        for st in rows:
            if st.key == "time_label.t0_min" and not self.scope.value(doc, st):
                continue  # (an older figure's: run time zeros do this now)
            w = make_widget(ed, st, self.scope.value(doc, st), self._on_change)
            by_key[st.key] = w
            out.append(w)
            if st.key == found:
                w.styles = dict(w.styles or {}, **FOUND)
        objs = [_grid(*out, n=2)] if out else []
        if extra is not None:
            objs += extra(by_key)
        marks["widgets"] = by_key
        if section not in NO_RESET:
            objs.insert(0, self._reset_line(section, marks))
        self._mark(marks)
        return objs

    # ------------------------------------------------------------ changed, and back
    def _kinds(self):
        return list(self.kinds) or ["plan"]

    def _start_of(self, doc, kind, st):
        """Setting st's value in a new figure of `kind` (table.KEEP: it has none)."""
        if st.key == "letters.on":  # (they follow the count, until set by hand)
            return len(doc.get("panels") or []) > 1
        return Scope(kind).value(self.ins.fresh(kind), st)

    def _is_changed(self, doc, st):
        """Whether a reset would undo setting st here.  Marks only say: a value that can't be read
        (an older figure's oddity) is no reason to fail."""
        scope = self.scope
        try:
            if scope.inherits(st):
                return scope.has_own(doc, st)
            if st.key == "letters.on" and ((doc.get("style") or {}).get("letters") or {}).get("auto"):
                return False
            if st.key == "domain.box" and scope.value(doc, _DOMAIN_MODE) != "box":
                return False
            for kind, at in self._reach(st):
                now, start = at.value(doc, st), self._start_of(doc, kind, st)
                if now is not table.KEEP and start is not table.KEEP and not _same(now, start):
                    return True
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        return False

    def _reach(self, st):
        """[(kind, Scope)] where setting st is read and written at this scope: all the figure's
        kinds for a block each kind holds, else the one kind or the figure."""
        scope = self.scope
        if scope.kind is not None:
            return [(scope.kind, scope)]
        if kind_block(_split(st)[0] or _split(st)[1]):
            return [(k, Scope(k)) for k in self._kinds()]
        return [(self._kinds()[0], scope)]

    def _mark(self, marks):
        """A section's marks, from the document."""
        doc = self.shell.doc
        changed = [st for st in marks["rows"] if self._is_changed(doc, st)]
        self._header(marks, len(changed))
        keys = {st.key for st in changed}
        for key, w in marks["widgets"].items():
            on = key in keys
            if on != ("box-shadow" in (w.styles or {})):
                styles = {k: v for k, v in (w.styles or {}).items() if k != "box-shadow"}
                w.styles = dict(styles, **MARK) if on else styles
        if marks["line"] is not None:
            marks["line"].visible = bool(changed)
            words = row_words(self.shell.ed, [st.key for st in changed])
            marks["note"].object = '<div class="cv-hint">Changed: ' + html.escape(
                ", ".join(words.values())) + "</div>" if changed and self.scope.pid is None else ""

    @staticmethod
    def _header(marks, n):
        """The count on a section's header (its title stays what it is)."""
        card = marks["card"]
        if not n:
            if card.header is not None:
                card.header = None
            marks["header"] = None
            return
        tip = f"{n} setting{'s' if n > 1 else ''} changed"
        text = (f'<h3>{html.escape(card.title)} <span title="{tip}" style="color:{ACCENT};'
                f'font-weight:400">● {n}</span></h3>')
        if marks["header"] is None:
            marks["header"] = pn.pane.HTML(text, css_classes=card.title_css_classes, margin=(5, 0),
                                           styles={"color": card.header_color})
            card.header = marks["header"]
        else:
            marks["header"].object = text

    def refresh(self):
        """Every section's marks, the document having changed under its widgets."""
        for marks in self.live.values():
            self._mark(marks)

    def _reset_line(self, section, marks):
        """What is changed in a section, and its reset."""
        word = "Back to what all panels have" if self.scope.pid is not None else \
            "Back to the figure's" if self.scope.kind is not None and section == "Colorbar" else \
            "Back to a new figure's"
        reset = pn.widgets.Button(name=f"↺ {word}", height=26, margin=(2, 2), button_type="light",
                                  button_style="outline", align="center",
                                  description="Every setting of this section. Undo takes it back")
        reset.on_click(lambda e: self.reset(section))
        marks["note"] = pn.pane.HTML(margin=(2, 4), sizing_mode="stretch_width")
        marks["line"] = pn.Row(marks["note"], reset, margin=0, sizing_mode="stretch_width")
        return marks["line"]

    def reset(self, section):
        """A section back: one undo step."""
        marks = self.live[section]
        title = marks["card"].title
        rows = marks["rows"]
        scope = self.scope

        def apply(d):
            changed = [st for st in rows if self._is_changed(d, st)]
            # (what isn't marked goes too: a fixed box the area doesn't use now)
            for st in rows:
                if st not in changed and st not in EXTRA_ROWS:
                    continue
                if scope.inherits(st):
                    scope.take_own(d, st)
                    continue
                for kind, at in self._reach(st):
                    start = self._start_of(d, kind, st)
                    if start is not table.KEEP:
                        at.write(d, st, start)
            if any(st.key == "letters.on" for st in changed) and scope.pid is None:
                letters = d.setdefault("style", {}).setdefault("letters", {})
                letters.update(auto=True, on=len(d.get("panels") or []) > 1)
            n = len(changed)
            said = f"{title}: {n} setting{'s' if n != 1 else ''} back. Undo takes it back."
            if scope.pid is None:
                keys = [st.key for st in rows]
                keep = {x for k in self._kinds() if k in PANEL_KEYS
                        for x in panels_differ(d, k, keys)}
                if keep:
                    said += (" Panel" + ("s " if len(keep) > 1 else " ")
                             + ", ".join(sorted(keep)) + (" keep what they" if len(keep) > 1
                                                          else " keeps what it") + " set alone.")
            self.shell._said = said

        self.shell.edit(apply, node=self.shell.node)

    def chips(self, keys):
        """A panel's own settings of `keys`, each to take back (↺)."""
        own = self.scope.own_keys(self.shell.doc, keys)
        if not own:
            return []

        def back(key):
            self.shell.edit(lambda d: self.scope.take_back(d, key), node=self.shell.node)

        chips = []
        for key, word in row_words(self.shell.ed, own).items():
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


def legend_reaches(doc):
    """Whether a figure-level legend has anything to list: not with only box plots, nor only
    time-height panels without legend annotations (the old editor's _show_legend)."""
    kinds = {p["kind"] for p in doc.get("panels") or []}
    if kinds == {"th"}:
        return any(a.get("kind") == "legend" for a in doc.get("annotations") or [])
    if kinds == {"dist"}:
        return Scope("dist")._layers_up(doc, "dist")[-1].get("dist", {}).get("plot") \
            not in ("box", "violin")
    return True


def legend_extra(shell, kinds):
    """The Legend section's rows that go with the kinds in the figure (panels with legends of
    their own have those, or one on the figure; the others one legend of their layers), and the
    panels it is in and lists, by id, so they stay with their panels: {section: extra}."""
    def extra(by_key):
        doc = shell.doc
        names = nodes.letters(doc)
        ids = {names[p["id"]]: p["id"] for p in sorted(doc["panels"], key=lambda p: list(p["cell"]))}
        lg = (doc.get("style") or {}).get("legend") or {}
        panel = pn.widgets.Select(name="In panel", options=ids, value=lg.get("panel") if lg.get(
            "panel") in ids.values() else next(iter(ids.values())))
        listed = pn.widgets.MultiChoice(
            name="From panels (blank: all)", options=ids,
            value=[i for i in lg.get("panels") or [] if i in ids.values()],
            description="The panels whose entries it lists")

        def write(**keys):
            def apply(d):
                style = d.setdefault("style", {})
                style["legend"] = dict(style.get("legend") or {}, **keys)
            shell.edit(apply)

        panel.param.watch(lambda ev: write(panel=ev.new), "value")
        listed.param.watch(lambda ev: write(panels=list(ev.new)), "value")
        own = all(k in figdraw.LEGEND_OPTS for k in kinds)
        some = any(k in figdraw.LEGEND_OPTS for k in kinds)
        scene = set(kinds) == {"scene"}

        def key(name):
            return by_key.get(f"legend.{name}")

        where = key("where")
        where.name = "Legends on" if own else "Layer legend on"
        where.options = {"Each panel" if own else "A panel": "panel", "The figure": "figure"}

        def show(*ev):
            fig = where.value == "figure"
            key("loc").options = LOCS + FIG_LOCS if fig else LOCS
            for name in ("loc", "anchor", "ncol", "title", "frame"):
                key(name).visible = fig or not own
            panel.visible = not fig and not own and not scene
            listed.visible = fig and not scene
            key("own").visible = some and not fig

        where.param.watch(show, "value")
        show()
        return [_grid(panel, listed, n=2)]

    return {"Legend": extra}


def kind_bar_rows(ins, doc, kind):
    """A kind's own colorbar settings, in a figure of several kinds, where its panels' bars are
    apart from the others': a card, or None.  How many bars there are stays the figure's."""
    if kind not in table.CBAR or len({p["kind"] for p in doc.get("panels") or []}) < 2:
        return None
    only = tuple(st.key for st in table.SETTINGS if st.section == "Colorbar"
                 and st.key != "colorbar.mode")
    return Sections(ins, Scope(kind), (kind,)).card("Colorbar", only)


def panel_bar_card(ins, doc, pid):
    """A panel's part in the colorbars, for the kinds that have them: a card, or None."""
    shell = ins.shell
    p = de.panel_by_id(doc, pid)
    if p["kind"] not in table.CBAR:
        return None
    cb = p.get("colorbar") or {}
    show = pn.widgets.Checkbox(name="Its colours have a bar", value=cb.get("show", True))
    group = pn.widgets.TextInput(name="The bar it shares (a name)", value=cb.get("group") or "",
                                 placeholder="blank: as the figure's Colorbars say",
                                 sizing_mode="stretch_width",
                                 description="Panels giving the same name share one bar, whatever "
                                             "their kinds")
    show.param.watch(lambda ev: shell.edit(lambda d: de.set_panel_colorbar(d, pid, show=ev.new)),
                     "value")
    group.param.watch(lambda ev: shell.edit(lambda d: de.set_panel_colorbar(d, pid, group=ev.new)),
                      "value")
    key = f"look:{pid}:bar"
    card = pn.Card(show, group, _hint(
        "Blank: one bar as the figure's Colorbars say. Where kinds are mixed, panels of the same "
        "colours share one bar, each of the others its own."), title="Colorbar",
        collapsed=not ins.folds.get(key), **SECTION)
    card.param.watch(lambda ev: ins.folds.__setitem__(key, not ev.new), "collapsed")
    return card


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
