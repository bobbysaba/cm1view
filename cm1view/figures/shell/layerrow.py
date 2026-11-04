"""A layer in the inspector: a head (on, what it is, up, down, copy, remove) over a LayerCard's
settings, built only when opened.  It edits a shared layer, or one layer of one panel: Shared
and InPanel say where its changes go.

The card works in the old form (runs by place); CardHost is what it asks of its editor, and
what it collects goes back with run ids.  Only keys the card actually changed are written, so
what a card merely writes differently (a list as text, a key it always adds) is not taken for
a change, and no override appears from it."""

import html
from types import SimpleNamespace

import panel as pn

from .. import draw as figdraw
from ..cards import LayerCard, TYPE_LABEL
from ..cards.base import _BTN, CARD, GHOST, _chk, grid_columns
from ..runs import FigureRuns
from ..times import _tlabel
from ...theme import ACCENT
from . import docedit as de, nodes

GROUPED = {"minus": "minus_on", "ens": "ens_on", "reduce": "reduce_op"}  # (key -> widget)
PANELS_TIME = "the panel's"


class CardHost:
    """What a LayerCard asks of its editor: the kind, the field and run lists of the
    document, and request(), which records the card's settings."""

    _run_choices = FigureRuns._run_choices
    _layer_run_choices = FigureRuns._layer_run_choices
    _series_run_opts = FigureRuns._series_run_opts
    _pick_other = FigureRuns._pick_other

    def __init__(self, shell, changed, by_height=False, kind="plan"):
        self.shell, self.v, self.fields = shell, shell.v, shell.fields
        self.kind = SimpleNamespace(value=kind)
        self._uses = lambda d: by_height and d == "heights"
        self._hold = False
        self._changed = changed

    def _show_region(self):
        """(Sections have their own place in the tree.)"""

    def request(self):
        if not self._hold:
            self._changed()

    def _run_names(self):
        names = nodes.run_names(self.shell.doc)
        return {f"{k + 1}. {names[r['id']]}": k for k, r in enumerate(self.shell.doc["runs"])}

    def _other_runs(self):
        return self.shell.other_runs()

    def _time_opts(self, k):
        return self.shell.time_opts(k)

    def _add_run(self, path, grid=False):
        """A run not in the figure picked: add it.  Its place, or None."""
        return self.shell.add_run(path)

    def _msg(self, text, err=False):
        self.shell.say(text, err)


class Shared:
    """A shared layer: edits reach every panel drawing it, but what differs in one."""

    def __init__(self, lid, kind):
        self.lid, self.kind = lid, kind
        self.key = f"s:{lid}"

    def layer(self, doc):
        return doc["layers"][self.lid]

    def write(self, doc, changes):
        de.write_shared(doc, self.lid, changes)


class InPanel:
    """Layer j of a panel, as it is drawn there: edits go to its overrides, or if it is a
    layer of the panel's own, to it."""

    def __init__(self, doc, pid, j):
        self.pid, self.j = pid, j
        self.ref = figdraw.panel_layers(doc, de.panel_by_id(doc, pid))[j][0]
        self.key = f"p:{pid}:{self.ref}" if self.ref else f"p:{pid}:own{j}"

    def panel(self, doc):
        return de.panel_by_id(doc, self.pid)

    def layer(self, doc):
        return figdraw.panel_layers(doc, self.panel(doc))[self.j][1]

    def over(self, doc):
        return de.overrides(de.places(doc, self.panel(doc))[self.j])

    def write(self, doc, changes):
        de.write_panel(doc, self.panel(doc), self.j, changes)


def describe(lay, fields=None, p=None):
    """A layer in a line: its type, field, height, what it does over time."""
    bits = []
    if lay.get("field"):
        bits.append(fields[lay["field"]].label if fields is not None and lay["field"] in fields
                    else lay["field"])
    elif lay.get("type") == "vectors":
        bits.append(str(lay.get("vector") or "wind"))
    elif lay.get("type") == "parcels":
        bits.append(str(lay.get("name") or "parcels"))
    mode = lay.get("mode", "height")
    if lay.get("field") or lay.get("type") == "vectors":
        if p is not None and p.get("z") is not None and not lay.get("z_fixed"):
            pass  # (the panel's: said beside it)
        elif mode == "height" and lay.get("z") is not None:
            bits.append(f"{float(lay['z']):g} km")
        elif mode == "level":
            bits.append(f"k = {float(lay.get('z') or 0):g}")
        elif mode in ("colmax", "colmin"):
            bits.append(f"column {mode[3:]}")
    if lay.get("minus"):
        bits.append("difference")
    if lay.get("ens"):
        bits.append("ensemble")
    if lay.get("reduce"):
        bits.append("over time")
    return " · ".join([TYPE_LABEL.get(lay.get("type"), str(lay.get("type")))] + bits)


class LayerRow:
    """target: Shared or InPanel.  fixed: always open, with no moving it (a layer's own node).
    moves: {"up", "down", "copy", "remove"} -> what each button does, by document change;
    extras(row): widgets above the settings, when open; opened: open unless folded by hand."""

    def __init__(self, inspector, target, moves=None, fixed=False, by_height=False, extras=None,
                 opened=False):
        self.ins, self.shell, self.target = inspector, inspector.shell, target
        self.moves, self.fixed, self.by_height = moves or {}, fixed, by_height
        self.extras = extras
        self.card, self.base = None, None
        doc = self.shell.doc
        lay = target.layer(doc)
        self.type = lay.get("type")
        self.chev = pn.widgets.Button(name="", icon="chevron-right", width=28, height=28,
                                      margin=(2, 0), button_type="light",
                                      description="Show / hide the settings",
                                      stylesheets=[GHOST], visible=not fixed)
        self.on = pn.widgets.Checkbox(value=lay.get("on", True) is not False, width=20,
                                      margin=(8, 2, 0, 4))
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4), sizing_mode="stretch_width")
        self.body = pn.Column(margin=0, sizing_mode="stretch_width")
        head = [self.chev, self.on, self.title]
        for name, label, icon, tip in (
                ("up", "↑", None, "Draw earlier (below)"), ("down", "↓", None,
                                                            "Draw later (on top)"),
                ("copy", "", "copy", "A copy of this layer, drawn just above it"),
                ("remove", "✕", None, "Remove the layer")):
            if name in self.moves:
                b = pn.widgets.Button(name=label, icon=icon, description=tip, **_BTN)
                b.on_click(lambda e, f=self.moves[name]: f())
                head.append(b)
        self.panel = pn.Column(pn.Row(*head, margin=0, sizing_mode="stretch_width"), self.body,
                               sizing_mode="stretch_width", margin=(2, 0), styles=CARD)
        self.chev.on_click(lambda e: self.flip())
        self.on.param.watch(self._on_on, "value")
        self._set_title()
        if fixed or inspector.folds.get(target.key, opened):
            self._open()

    # ------------------------------------------------------------ folding
    def flip(self):
        if self.body.objects:
            self.ins.folds[self.target.key] = False
            self.body.objects = []
            self.card = None
            self.chev.icon = "chevron-right"
        else:
            self.ins.folds[self.target.key] = True
            self._open()

    def _open(self):
        doc, shell = self.shell.doc, self.shell
        host = CardHost(shell, self._on_card, self.by_height)
        with grid_columns(2):
            self.card = card = LayerCard(host, de.to_card(doc, de.plain(self.target.layer(doc))))
        card.w["panels"].visible = False
        self.base = de.plain(self._collect())
        for name, sec in self._sections():
            key = f"{self.target.key}/{name}"
            if self.ins.folds.get(key):
                sec.collapsed = False
            sec.param.watch(lambda e, k=key: self.ins.folds.__setitem__(k, not e.new), "collapsed")
        self.top = pn.Column(margin=0, sizing_mode="stretch_width")
        own = self.extras(self) if self.extras else []
        self.body.objects = [self.top, *own, *card.body.objects]
        self.chev.icon = "chevron-down"
        self._show_marks()

    def _sections(self):
        card = self.card
        return [(n, getattr(card, f"{n}_sec")) for n in ("minus", "ens", "reduce")
                if hasattr(card, f"{n}_sec")]

    # ------------------------------------------------------------ changes
    def _collect(self):
        return {k: v for k, v in self.card.collect().items() if k != "panels"}

    def _on_card(self):
        """The card changed: what it now says otherwise goes into the document."""
        try:
            new = de.plain(self._collect())
        except Exception as e:  # noqa: BLE001  (half typed)
            self.shell.say(f"Incomplete settings: {html.escape(str(e))}", True)
            return
        keys = [k for k in {*new, *self.base}
                if new.get(k, de.MISSING) != self.base.get(k, de.MISSING)]
        self.base = new
        if not keys:
            return
        out = de.from_card(self.shell.doc, new)
        changes = {k: out[k] if k in out else de.MISSING for k in keys}
        self.shell.edit(lambda d: self.target.write(d, changes))
        self._set_title()
        self._show_marks()

    def _on_on(self, ev):
        if self.card is not None:
            self.card._loading = True
            self.card.w["on"].value = ev.new
            self.card._loading = False
            self.base["on"] = ev.new
        self.shell.edit(lambda d: self.target.write(d, dict(on=bool(ev.new))))
        self._show_marks()

    def _set_title(self):
        doc = self.shell.doc
        t = self.target
        over = t.over(doc) if isinstance(t, InPanel) else {}
        p = t.panel(doc) if isinstance(t, InPanel) else None
        text = html.escape(describe(t.layer(doc), self.shell.fields, p))
        marks = [k for k in over if not (p.get("z") is not None and k in de.HEIGHT_KEYS)
                 and k != "on"] if p is not None else []
        tail = ""
        if isinstance(t, InPanel) and t.ref is None:
            tail = ' <span class="cv-hint">this panel only</span>'
        elif marks:
            tail = f' <span class="cv-hint" style="color:{ACCENT}">differs here</span>'
        self.title.object = f"<b>{text}</b>{tail}"

    # ------------------------------------------------------------ what differs here
    def _label(self, key):
        """A setting's name in words."""
        w = self.card.w.get(GROUPED.get(key, key)) if self.card is not None else None
        return (getattr(w, "name", "") or key).strip()

    def _show_marks(self):
        """A panel's layer: what it has otherwise than the shared layer, each to take back (↺)
        and marked beside its widget."""
        self._set_title()
        if self.card is None:
            return
        t, doc = self.target, self.shell.doc
        over = dict(t.over(doc)) if isinstance(t, InPanel) else {}
        p = t.panel(doc) if isinstance(t, InPanel) else None
        if p is not None and p.get("z") is not None:
            for k in de.HEIGHT_KEYS:
                over.pop(k, None)
        over.pop("on", None)
        marked = {GROUPED.get(k, k) for k in over}
        for k, w in self.card.w.items():
            was = (w.styles or {}).get("box-shadow")
            if (k in marked) != bool(was):
                styles = dict(w.styles or {})
                if k in marked:
                    styles["box-shadow"] = f"-3px 0 0 {ACCENT}"
                else:
                    styles.pop("box-shadow", None)
                w.styles = styles
        if not isinstance(t, InPanel) or t.ref is None:
            self.top.objects = []
            return
        chips = []
        for k in sorted(over):
            b = pn.widgets.Button(name=f"↺ {self._label(k)}", height=26, margin=(2, 2),
                                  button_type="light", button_style="outline",
                                  description=f"Back to the shared layer's {k}")
            b.on_click(lambda e, key=k: self._take_back(key))
            chips.append(b)
        if len(chips) > 1:
            b = pn.widgets.Button(name="↺ All", height=26, margin=(2, 2), button_type="light",
                                  button_style="outline",
                                  description="This layer as shared: all of the above")
            b.on_click(lambda e: self._take_back(None))
            chips.append(b)
        self.top.objects = [pn.FlexBox(*chips, sizing_mode="stretch_width")] if chips else []

    def _take_back(self, key):
        t = self.target
        self.shell.edit(lambda d: de.clear_over(d, t.panel(d), t.j, key), node=self.shell.node)


def own_time_widgets(row):
    """A panel's layer: the run's time it takes, if not the panel's (and whether an animation
    holds it)."""
    shell, t = row.shell, row.target
    doc = shell.doc
    p, lay = t.panel(doc), t.layer(doc)
    rid = lay.get("run") or p.get("run")
    topts = {PANELS_TIME: ""} | shell.time_opts(de.run_index(doc, rid))
    now = "" if lay.get("time_s") is None else float(lay["time_s"])
    if now not in topts.values():
        topts[_tlabel(now) + " · no output"] = now
    time = pn.widgets.Select(name="Time", options=topts, value=now)
    lock = _chk("Keep this time in animations", bool(lay.get("time_lock")))
    lock.visible = time.value != ""

    def on_time(ev):
        lock.visible = ev.new != ""
        val = None if ev.new == "" else float(ev.new)
        shell.edit(lambda d: t.write(d, dict(time_s=val) if val is not None
                                     else dict(time_s=de.MISSING)))

    def on_lock(ev):
        shell.edit(lambda d: t.write(d, dict(time_lock=True) if ev.new
                                     else dict(time_lock=de.MISSING)))

    time.param.watch(on_time, "value")
    lock.param.watch(on_lock, "value")
    return [pn.Row(time, lock, margin=0, sizing_mode="stretch_width")]

