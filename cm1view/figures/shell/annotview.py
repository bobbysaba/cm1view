"""Annotations in the inspector: on the Figure node all of them, on a panel those drawn in it, each
over an AnnotationRow but naming panels by id, from a list of their letters."""

import panel as pn

from ..cards import ANN_KINDS, AnnotationRow, _grid
from ..cards.base import SECTION, grid_columns, set_folded
from ..draw.base import ann_on
from . import docedit as de, nodes
from .layerrow import CardHost


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


class AnnRow(AnnotationRow):
    """One annotation of the document: its panels by id.  One naming only panels no longer there
    keeps saying so until its panels are picked."""

    def __init__(self, shell, host, a):
        self.shell = shell
        super().__init__(host, a)

    def _panel_widget(self, a):
        doc = self.shell.doc
        names = nodes.letters(doc)
        opts = {names[p["id"]]: p["id"] for p in nodes.in_order(doc)}
        self.names = names
        ids = de.ann_panels(a)
        now = [i for i in ids if i in names]
        self.stale = ids if -1 not in ids and not now else None
        w = pn.widgets.MultiChoice(name="Panels (blank: all)", options=opts, value=now,
                                   placeholder="all")
        w.param.watch(lambda e: setattr(self, "stale", None), "value")
        return w

    def _panels(self):
        if self.stale:
            return self.stale[0] if len(self.stale) == 1 else list(self.stale)
        ids = sorted(self.w["panel"].value)
        return -1 if not ids else ids[0] if len(ids) == 1 else ids

    def _where(self):
        if self.stale:
            return "no such panel"
        ids = sorted(self.w["panel"].value, key=list(self.names).index)
        if not ids:
            return "every panel"
        return ("panels " if len(ids) > 1 else "panel ") + ", ".join(self.names[i] for i in ids)


class AnnotPane:
    def __init__(self, inspector):
        self.ins, self.shell = inspector, inspector.shell

    def card(self, doc, pid=None):
        """The annotations of the figure, or of panel pid: filled when opened."""
        here = [n for n, a in enumerate(doc.get("annotations") or [])
                if pid is None or ann_on(a, pid)]
        key = f"annots:{pid}"
        folds = self.ins.folds
        card = pn.Card(title=f"Annotations ({len(here)})" if here else "Annotations",
                       collapsed=True, **SECTION)

        def fill():
            if not card.objects:
                card.objects = self._body(self.shell.doc, here, pid)

        def on_fold(ev):
            folds[key] = not ev.new
            if not ev.new:
                fill()

        card.param.watch(on_fold, "collapsed")
        if folds.get(key):
            card.collapsed = False
        return card

    def _body(self, doc, here, pid):
        kind = pn.widgets.Select(name="Add", options=ANN_KINDS)
        add = pn.widgets.Button(name="+ Add", button_type="primary", button_style="outline",
                                height=32, margin=(6, 4), align="end")
        add.on_click(lambda e: self.add(kind.value, pid))
        objs = [_note("Text, markers, arrows, lines, boxes and circles, or an entry of its own in "
                      "the panels' legends. <b>Click</b> (above the preview) places them by "
                      "clicking and moves them by dragging."),
                _grid(kind, add, n=2)]
        with grid_columns(2):
            rows = [self._row(n, doc["annotations"][n]) for n in here]
        return objs + [r.panel for r in rows]

    def _row(self, n, a):
        shell = self.shell
        state = {}

        def changed():
            new = de.plain(row.collect())
            changes = {k: v for k, v in new.items() if v != state["base"].get(k, de.MISSING)}
            state["base"] = new
            if changes:
                shell.edit(lambda d: d["annotations"][n].update(changes))

        host = CardHost(shell, changed)
        row = AnnRow(shell, host, de.plain(a))
        state["base"] = de.plain(row.collect())
        key = f"ann:{n}"
        if not self.ins.folds.get(key, len(shell.doc["annotations"]) == 1):
            set_folded(row, True)
        row.body.param.watch(lambda e: self.ins.folds.__setitem__(key, e.new), "visible")
        row.rm.on_click(lambda e: shell.edit(lambda d: d["annotations"].pop(n), node=shell.node))
        return row

    def _lims(self, doc, pid):
        """The axis ranges a new annotation of panel pid (None: of every panel) goes by; None: as
        fractions of the panel, as a skew-T, a 3D scene or several kinds together have it."""
        place = self.shell.placing
        if pid is None:
            kinds = {p["kind"] for p in doc["panels"]}
            drawn = [p["id"] for p in nodes.in_order(doc) if p["id"] in place.place]
            if len(kinds) != 1 or not drawn:
                return None
            pid = drawn[0]
        b = place.place.get(pid)
        return None if b is None or b[6] is not None or pid in place.fractions else (b[4], b[5])

    def add(self, kind, pid=None):
        """A new annotation, open."""
        doc = self.shell.doc
        new = de.new_annotation(kind, -1 if pid is None else pid, self._lims(doc, pid))
        self.append(new)

    def append(self, new, node=None):
        """Annotation `new` into the document, its row and the card holding it open."""
        shell = self.shell

        def apply(d):
            d.setdefault("annotations", []).append(new)
            folds = self.ins.folds
            folds[f"ann:{len(d['annotations']) - 1}"] = True
        at = node or shell.node
        p = nodes.panel_of(shell.doc, at) if at.startswith(("panel:", "layer:")) else None
        self.ins.folds[f"annots:{p['id'] if p is not None else None}"] = True
        shell.edit(apply, node=at)
