"""The inspector: the settings of the one thing picked in the tree, and what an edit reaches.
Only what is shown exists as widgets: a node's are made when it is picked.

Editable so far: the figure's size, title, look, grid and panels, the runs, plan views
(planview), soundings (entryview), cross-sections (xsecview), time-height panels and time series
(seriesview).  Other kinds are shown, with a panel's title and place to edit, until they move
here."""

import html
import os

import panel as pn

from ... import config
from .. import draw as figdraw
from ..cards import SIZE_PRESETS, _hex, _row
from ..cards.base import _f
from ..runs import TYPE_PATH, _track_options, _track_path
from . import docedit as de, nodes
from .entryview import EntryPane
from .gridview import GridPane, grid_map  # noqa: F401  (grid_map: of the Figure node)
from .looks import (FIGURE_SECTIONS, PANEL_KEYS, Scope, Sections, key_layer_widget,
                    panels_differ)
from .planview import PlanPane
from .seriesview import SeriesPane
from .xsecview import XsecPane
from ...theme import GRID


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


def _lines(rows):
    """Rows of (name, value) as a small table (values are escaped)."""
    cells = "".join(f'<tr><td style="padding:1px 10px 1px 0;opacity:.7">{html.escape(a)}</td>'
                    f'<td>{html.escape(str(b))}</td></tr>' for a, b in rows)
    return pn.pane.HTML(f'<table style="font-size:13px;border-collapse:collapse">{cells}</table>',
                        margin=(4, 4), sizing_mode="stretch_width")


class Inspector:
    def __init__(self, shell):
        self.shell = shell
        self.folds = {}  # what is open: by layer id or section, so it outlasts undo and redo
        self.plan = PlanPane(self)
        self.grid = GridPane(self)
        self.panes = dict(plan=self.plan, sounding=EntryPane(self), xsec=XsecPane(self),
                          th=SeriesPane(self, "th"), line=SeriesPane(self, "line"))  # (moved here)
        self.head = pn.pane.HTML(margin=(4, 4, 0, 4), sizing_mode="stretch_width",
                                 styles={"flex": "0 0 auto"})
        # (taller than the pane: it scrolls.  Its height is what it holds: Bokeh's max-height 100%
        # would cap it and each card in it at the pane's, and a taller card run over the next)
        self.body = pn.Column(margin=0, sizing_mode="stretch_width",
                              styles={"flex": "0 0 auto", "height": "max-content",
                                      "max-height": "none"})
        self.panel = pn.Column(self.head, self.body, width=440, scroll="y-auto",
                               sizing_mode="stretch_height",
                               styles={"border-left": f"1px solid {GRID}", "padding": "0 8px",
                                       "overflow-x": "hidden", "flex": "0 0 auto"})

    def show(self, node):
        """The settings of node, from the document."""
        doc = self.shell.doc
        title = {nodes.FIGURE: "Figure", nodes.RUNS: "Runs"}.get(node)
        if node.startswith("kind:"):
            title, objs = self._kind(doc, node)
        elif node.startswith("layer:"):
            title, objs = self._layer(doc, node)
        elif node.startswith("panel:"):
            title, objs = self._panel(doc, node)
        else:
            objs = self._figure(doc) if node == nodes.FIGURE else self._runs(doc)
        self.head.object = (f'<div class="cv-h" style="margin:0">{html.escape(title)}</div>'
                            f'<div class="cv-hint">{html.escape(nodes.scope(doc, node))}</div>')
        self.body.objects = objs

    # ------------------------------------------------------------ the figure
    def _figure(self, doc):
        w, h = (list(doc.get("size") or [8.0, 6.0]) + [6.0])[:2]
        width = _f("Width (in)", float(w), 110, step=0.25)
        height = _f("Height (in)", float(h), 110, step=0.25)
        preset = pn.widgets.Select(name="Size", options=SIZE_PRESETS, value="", width=170)
        fit = pn.widgets.Button(name="Fit height", height=32, align="end", button_type="light",
                                button_style="outline", margin=(4, 4),
                                description="The height for the width and the panels; it then "
                                            "follows them, until a size is typed")
        self.size_ws = (width, height)
        title = pn.widgets.TextInput(name="Figure title", value=doc.get("suptitle") or "",
                                     sizing_mode="stretch_width")

        def on_size(ev):
            if self._quiet:
                return
            if width.value and height.value:
                self.shell.edit(lambda d: d.update(size=[float(width.value), float(height.value)],
                                                   size_auto=False))

        def on_preset(ev):
            if not ev.new:
                return
            if "x" in ev.new:
                size, auto = [float(v) for v in ev.new.split("x")], False
            else:  # (only plan views' and sections' height follows a width)
                size = [float(ev.new), float(height.value or 6.0)]
                auto = self.shell.can_follow() and \
                    self.shell.doc["panels"][0]["kind"] in ("plan", "xsec")
            self.shell.edit(lambda d: d.update(size=size, size_auto=auto), node=nodes.FIGURE)

        width.param.watch(on_size, "value")
        height.param.watch(on_size, "value")
        preset.param.watch(on_preset, "value")
        fit.on_click(lambda ev: self.shell.edit(lambda d: d.update(size_auto=True),
                                                node=nodes.FIGURE))
        fit.disabled = not self.shell.can_follow(doc)
        if fit.disabled:
            fit.description = "Only a figure of one kind of panel, in equal cells, has an " \
                              "automatic size"
        title.param.watch(lambda ev: self.shell.edit(
            lambda d: d.update(suptitle=ev.new.strip())), "value")
        objs = [_row(width, height, preset, fit), title, *self.grid.grid_objs(doc)]
        for text in doc.get("notes") or []:
            objs.append(_note(html.escape(str(text))))
        if any(p["kind"] == "plan" for p in doc.get("panels") or []):
            objs.append(self.plan.fill_card(doc))
        kinds = list(dict.fromkeys(p["kind"] for p in doc.get("panels") or []))
        looks = Sections(self, Scope(), kinds, {
            "Contour key": lambda by: [key_layer_widget(self.shell, doc, "contour_key",
                                                        ("contour",), "First contours")],
            "Maximum and minimum": lambda by: [key_layer_widget(
                self.shell, doc, "extremes", figdraw.EXTREME_TYPES, "First fill")]})
        objs += [c for c in (looks.card(s) for s in FIGURE_SECTIONS) if c is not None]
        own = {}
        for kind in kinds:
            if kind in PANEL_KEYS:
                own.update(panels_differ(doc, kind, PANEL_KEYS[kind]["Panel labels"]))
        if own:
            objs.append(_note("Panel labels set in a panel alone, which changes here skip: panel"
                              + ("s " if len(own) > 1 else " ") + ", ".join(own) + "."))
        if doc.get("groups"):
            objs.append(_note("This figure was made of parts: each part's colorbar, legend and "
                              "ticks stay its own, whatever is set here."))
        return objs

    _quiet = False  # (the size boxes being set from the document)

    def size_followed(self, size):
        """The height followed the panels: the Figure node's boxes say so."""
        ws = getattr(self, "size_ws", None)
        if ws is None or self.shell.node != nodes.FIGURE:
            return
        self._quiet = True
        try:
            ws[0].value, ws[1].value = float(size[0]), float(size[1])
        finally:
            self._quiet = False

    # ------------------------------------------------------------ the runs
    def _runs(self, doc):
        used, names = nodes.runs_used(doc), nodes.letters(doc)
        objs = [self._run_row(r, k, used.get(r["id"], []), names, len(doc["runs"]))
                for k, r in enumerate(doc.get("runs") or [])]
        if len(doc.get("runs") or []) > 1:
            objs.insert(0, self._time_match(doc))
        have = {os.path.abspath(r["path"]) for r in doc.get("runs") or []}
        others = self.shell.ed._other_runs(have)
        if others:
            pick = pn.widgets.Select(name="Add a run", options=others, sizing_mode="stretch_width")
            add = pn.widgets.Button(name="Add", width=70, align="end", button_type="primary",
                                    button_style="outline")
            add.on_click(lambda ev: self._add_run(pick.value))
            objs.append(pn.Row(pick, add, margin=0, sizing_mode="stretch_width"))
        return objs

    def _time_match(self, doc):
        """How the runs line up: by time zero, or output number (each run lists its outputs)."""
        w = self.shell.ed.time_match.clone(visible=True, disabled=False, value="output" if any(
            r.get("outputs_s") for r in doc["runs"]) else "time")

        def on_pick(ev):
            def apply(d):
                style = d.setdefault("style", {})
                style.pop("time_match", None)
                for r in d["runs"]:
                    r.pop("outputs_s", None)
                if ev.new == "output":
                    style["time_match"] = "output"
                    for r in d["runs"]:
                        run = self.shell.ed.open_run(r["path"])[0]
                        r["outputs_s"] = [float(t) for t in run.times]
            self.shell.edit(apply, node=nodes.RUNS)

        w.param.watch(on_pick, "value")
        return w

    def _run_row(self, r, k, used, names, n):
        rid = r["id"]
        path = os.path.abspath(r["path"])
        own = path == self.shell.ed.run.path

        def change(**kw):
            def apply(d):
                run = next(x for x in d["runs"] if x["id"] == rid)
                run.update(kw)
            self.shell.edit(apply)

        label = pn.widgets.TextInput(name="Label", value=r.get("label", ""), width=130)
        color = pn.widgets.ColorPicker(name="Colour", width=70, value=_hex(
            r.get("color") or figdraw.RUN_COLORS[k % len(figdraw.RUN_COLORS)]))
        t0 = _f("Time zero (min)", float(r.get("t0_min") or 0.0), 110, step=1.0,
                description="The model time this run counts from: its time labels count from "
                            "it, and panels of the other runs move to stay at the same time "
                            "since their time zeros")
        by_output = bool(r.get("outputs_s"))
        label.param.watch(lambda ev: change(label=ev.new), "value")
        color.param.watch(lambda ev: change(color=ev.new), "value")
        t0.disabled = by_output and k > 0
        t0.param.watch(lambda ev: self.shell.edit(lambda d: de.set_t0(d, rid, ev.new)), "value")
        track = self._track_widgets(r, own, change)
        rm = pn.widgets.Button(name="✕", width=32, height=28, margin=(2, 1), button_type="default",
                               button_style="outline", disabled=bool(used) or n < 2,
                               description="Remove the run" if not used else
                               "In use by panel " + ", ".join(names[i] for i in used))
        rm.on_click(lambda ev: self.shell.edit(lambda d: de.remove_run(d, rid), node=nodes.RUNS))
        head = pn.pane.HTML(f'<b>{k + 1}.</b> <code>{html.escape(path)}</code>'
                            + ('<span class="cv-hint"> (this viewer\'s run)</span>' if own else ""),
                            margin=(6, 4, 0, 4))
        return pn.Column(pn.Row(head, pn.Spacer(), rm, margin=0, sizing_mode="stretch_width"),
                         _row(label, color, t0), *track, _note(self._run_note(r, used, names)),
                         margin=(2, 0), sizing_mode="stretch_width",
                         styles={"border-bottom": f"1px solid {GRID}"})

    def _track_widgets(self, r, own, change):
        """A run's storm track: the viewer's, or one of its track files, or a path typed."""
        found = config.track_files(r["path"])
        now = r.get("track") or ""
        viewer = pn.widgets.Checkbox(name="Viewer's track", value=now == "viewer", visible=own,
                                     margin=(5, 6, 8, 6))
        typed = now != "viewer" and bool(now) and _track_path(now) not in found
        pick = pn.widgets.Select(name="Track file", options=_track_options(found),
                                 value=TYPE_PATH if typed else ("" if now == "viewer" else
                                                                _track_path(now)),
                                 disabled=now == "viewer", sizing_mode="stretch_width",
                                 visible=bool(found))
        box = pn.widgets.TextInput(name="Track file path (blank: none)",
                                   value="" if now == "viewer" else now,
                                   disabled=now == "viewer", sizing_mode="stretch_width",
                                   visible=typed or not found)

        viewer.param.watch(lambda ev: change(track="viewer" if ev.new else ""), "value")
        box.param.watch(lambda ev: change(track=ev.new.strip()), "value")

        def on_pick(ev):
            box.visible = ev.new == TYPE_PATH
            if ev.new != TYPE_PATH:
                change(track=ev.new)

        pick.param.watch(on_pick, "value")
        return [viewer, pick, box]

    def _run_note(self, r, used, names):
        where = "not used yet" if not used else \
            "panel " + ", ".join(names[i] for i in used)
        try:
            run, _ = self.shell.ed.open_run(r["path"])
        except Exception as e:  # noqa: BLE001
            return f'<span style="color:#f87171">{html.escape(str(e))}</span>'
        return (f"{len(run.times)} outputs, {run.times[0] / 60:g}–{run.times[-1] / 60:g} min · "
                f"{run.ni}×{run.nj}×{run.nk}, dx {run.dx:g} m · {where}")

    def _add_run(self, path):
        self.shell.add_run(path, node=nodes.RUNS)

    # ------------------------------------------------------------ all panels of a kind
    def _kind(self, doc, node):
        kind = node.partition(":")[2]
        if kind in self.panes:
            return self.panes[kind].kind_objs(doc)
        mine = [p for p in nodes.in_order(doc) if p["kind"] == kind]
        names, fields = nodes.letters(doc), self.shell.fields
        shared = {}  # (the shared layers these panels draw: how many of them)
        for p in mine:
            for ref, _ in figdraw.panel_layers(doc, p):
                if ref is not None:
                    shared[ref] = shared.get(ref, 0) + 1
        rows = [("Panels", ", ".join(names[p["id"]] for p in mine))]
        rows += [(f"Layer {j + 1}", f"{nodes.layer_name(doc['layers'][ref], fields)} "
                                    f"({n} of {len(mine)} panels)")
                 for j, (ref, n) in enumerate(shared.items())]
        return f"All {nodes.kind_name(kind, len(mine))}", [
            _lines(rows), _note("Shown only: editing comes with each kind's move here.")]

    # ------------------------------------------------------------ a panel
    def _panel(self, doc, node):
        p = nodes.panel_of(doc, node)
        if p["kind"] in self.panes:
            return self.panes[p["kind"]].panel_objs(doc, node)
        pid = p["id"]
        letter = nodes.letters(doc)[pid]
        fields = self.shell.fields

        def apply(d, value):
            next(x for x in d["panels"] if x["id"] == pid)["title"] = value

        title = pn.widgets.TextInput(name="Title", value=p.get("title") or "",
                                     sizing_mode="stretch_width")
        title.param.watch(lambda ev: self.shell.edit(lambda d: apply(d, ev.new.strip())), "value")
        rows = [("Kind", nodes.KINDS[p["kind"]].label if p["kind"] in nodes.KINDS else p["kind"])]
        if p.get("run") is not None:
            rows.append(("Run", nodes.run_names(doc).get(p["run"], "no such run")))
        if p.get("time_s") is not None:
            rows.append(("Time", f"{float(p['time_s']) / 60:g} min"))
        if p.get("z") is not None:
            rows.append(("Height", f"{float(p['z']):g} km"))
        for j, (ref, lay) in enumerate(figdraw.panel_layers(doc, p)):
            rows.append((f"Layer {j + 1}", nodes.layer_name(lay, fields)
                         + ("" if ref is None else " (shared)")))
        return f"Panel {letter}", [title, _lines(rows),
                                   _note("Shown only, apart from the title and its place: "
                                         "editing comes with each kind's move here."),
                                   *self.grid.place_objs(doc, pid)]

    # ------------------------------------------------------------ a layer
    def _layer(self, doc, node):
        p = nodes.panel_of(doc, node)
        if p["kind"] in self.panes:
            return self.panes[p["kind"]].layer_objs(doc, node)
        j = int(node.rsplit(":", 1)[1])
        ref, lay = figdraw.panel_layers(doc, p)[j]
        letter = nodes.letters(doc)[p["id"]]
        item = p["layers"][j] if ref is None else next(
            (x for x in p["layers"] if x.get("ref") == ref), {})
        rows = [("Type", lay.get("type", "entry")), ("Field", lay.get("field") or "")]
        if ref is not None:
            over = sorted(item.get("over") or {})
            rows.append(("Shared", "with the other panels drawing it"))
            rows.append(("Differs here", ", ".join(over) or "nothing"))
        name = nodes.layer_name(lay, self.shell.fields)
        return f"{name} in panel {letter}", [
            _lines([x for x in rows if x[1]]),
            _note("Shown only: editing comes with each kind's move here.")]
