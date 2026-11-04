"""The inspector: the settings of the one thing picked in the tree, and what an edit reaches.
Only what is shown exists as widgets: a node's are made when it is picked.

The figure's size, title, look, grid and panels, the runs, plan views (planview), soundings
(entryview), cross-sections (xsecview), time-height panels and time series (seriesview),
distributions, profiles, joint distributions, azimuthal means and tables (statsview), 3D scenes
(sceneview), zoom insets (insetview) and annotations (annotview).  Every kind has a pane in `panes`.  Above them, Find
(findview), which comes here with a section to pin at the top."""

import html
import os

import panel as pn

from ... import config
from .. import draw as figdraw, spec as fg
from ..cards import SIZE_PRESETS, _hex, _row
from ..cards.base import _f
from ..runs import TYPE_PATH, _track_options, _track_path
from ..style import STYLE_LABELS
from . import docedit as de, nodes
from .annotview import AnnotPane
from .entryview import EntryPane
from .findview import Finder
from .gridview import GridPane, grid_map  # noqa: F401  (grid_map: of the Figure node)
from .insetview import InsetPane
from .looks import (FIGURE_SECTIONS, PANEL_KEYS, Scope, Sections, key_layer_widget, kind_bar_rows,
                    legend_extra, legend_reaches, panels_differ)
from .planview import PlanPane
from .sceneview import ScenePane
from .seriesview import SeriesPane
from .statsview import AzimPane, DistPane, JointPane, ProfilePane, TablePane
from .xsecview import XsecPane
from ...theme import GRID


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


class Inspector:
    def __init__(self, shell):
        self.shell = shell
        self.folds = {}  # what is open: by layer id or section, so it outlasts undo and redo
        self.live = []  # the Sections of what is shown
        self.pin = None  # what Find went to: {node, section, key}, while that node is picked
        self._fresh = {}  # (kind, a track or not) -> a new figure's look
        self.plan = PlanPane(self)
        self.grid = GridPane(self)
        self.annots = AnnotPane(self)
        self.insets = InsetPane(self)
        self.panes = dict(plan=self.plan, sounding=EntryPane(self), xsec=XsecPane(self),
                          th=SeriesPane(self, "th"), line=SeriesPane(self, "line"),
                          dist=DistPane(self), profile=ProfilePane(self), joint=JointPane(self),
                          azim=AzimPane(self), table=TablePane(self),
                          scene=ScenePane(self))
        self.head = pn.pane.HTML(margin=(4, 4, 0, 4), sizing_mode="stretch_width",
                                 styles={"flex": "0 0 auto"})
        # (taller than the pane: it scrolls.  Its height is what it holds: Bokeh's max-height 100%
        # would cap it and each card in it at the pane's, and a taller card run over the next)
        self.body = pn.Column(margin=0, sizing_mode="stretch_width",
                              styles={"flex": "0 0 auto", "height": "max-content",
                                      "max-height": "none"})
        self.finder = Finder(self)
        self.panel = pn.Column(self.finder.panel, self.head, self.body, width=440, scroll="y-auto",
                               sizing_mode="stretch_height",
                               styles={"border-left": f"1px solid {GRID}", "padding": "0 8px",
                                       "overflow-x": "hidden", "flex": "0 0 auto"})

    def show(self, node):
        """The settings of node, from the document."""
        doc = self.shell.doc
        self.live = []
        if self.pin is not None and self.pin["node"] != node:
            self.pin = None
            self.finder.said("")
        title = {nodes.FIGURE: "Figure", nodes.RUNS: "Runs"}.get(node)
        if node.startswith("kind:"):
            title, objs = self._kind(doc, node)
        elif node.startswith("layer:"):
            title, objs = self._layer(doc, node)
        elif node.startswith("panel:"):
            title, objs = self._panel(doc, node)
        elif node.startswith("inset:"):
            title, objs = self.insets.objs(doc, node)
        else:
            objs = self._figure(doc) if node == nodes.FIGURE else self._runs(doc)
        self.head.object = (f'<div class="cv-h" style="margin:0">{html.escape(title)}</div>'
                            f'<div class="cv-hint">{html.escape(nodes.scope(doc, node))}</div>')
        self.body.objects = self._pinned(objs)

    def _pinned(self, objs):
        """What is shown, with the section Find went to first and open, so it needs no looking
        for: the browser's scrolling isn't reachable from here, and this reads the same at any
        size.  It keeps its place until another node is picked."""
        section = (self.pin or {}).get("section")
        if not section:
            return objs
        hit = next((c for c in objs if isinstance(c, pn.Card) and (
            c.title == section or c.title.startswith(f"{section} ("))), None)
        if hit is None:
            self.pin["key"] = None
            self.finder.said(f"{html.escape(section)} isn't shown here now: what the panels are "
                             "set to leaves it out.")
            return objs
        hit.collapsed = False
        self.pin["key"] = None  # (marked once: not on later showings of the node)
        return [hit, *(c for c in objs if c is not hit)]

    def pin_key(self):
        """The setting Find went to, while its section is being made."""
        return (self.pin or {}).get("key")

    def go_to(self, node, section=None, key=None):
        """A node shown with a section of it first, open, and a setting in it marked (Find)."""
        self.pin = dict(node=node, section=section, key=key)
        self.shell._show(node)
        self.panel.scroll_position = 1  # (twice: the server's last value may be 0 already)
        self.panel.scroll_position = 0

    def fresh(self, kind):
        """A new figure's look with panels of `kind`: what changed marks and resets go by."""
        v, ed = self.shell.v, self.shell.ed
        key = (kind, bool(v.fixes))
        if key not in self._fresh:
            self._fresh[key] = fg.fresh_look(ed.run, ed.fields, v.t, kind, tracked=key[1])
        return self._fresh[key]

    def refresh_marks(self):
        """An edit from what is shown: each section's marks say so."""
        for looks in self.live:
            looks.refresh()

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
            else:  # (only plan views' and sections' height follows a width, and tables' rows)
                size = [float(ev.new), float(height.value or 6.0)]
                auto = self.shell.can_follow() and \
                    self.shell.doc["panels"][0]["kind"] in ("plan", "xsec", "table")
            self.shell.edit(lambda d: d.update(size=size, size_auto=auto), node=nodes.FIGURE)

        width.param.watch(on_size, "value")
        height.param.watch(on_size, "value")
        preset.param.watch(on_preset, "value")

        def on_fit(ev):
            def apply(d):
                d["size_auto"] = True
                now = de.kind_size(d)  # (a kind with a size of its own: now, not at its next change)
                if now is not None:
                    d["size"] = list(now)
            self.shell.edit(apply, node=nodes.FIGURE)

        fit.on_click(on_fit)
        fit.disabled = not self.shell.can_follow(doc)
        if fit.disabled:
            fit.description = "Only a figure of one kind of panel, in equal cells, has an " \
                              "automatic size (a 3D scene's is typed)"
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
                self.shell, doc, "extremes", figdraw.EXTREME_TYPES, "First fill")],
            **legend_extra(self.shell, kinds)})
        objs.append(self._presets())
        objs += [c for c in (looks.card(s) for s in FIGURE_SECTIONS)
                 if c is not None and (c.title != "Legend" or legend_reaches(doc))]
        objs.append(self.annots.card(doc))
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

    def _presets(self):
        menu = pn.widgets.MenuButton(name="Apply a style preset", button_type="light",
                                     button_style="outline", height=32, margin=(4, 4),
                                     items=[(label, key) for key, label in STYLE_LABELS.items()])
        menu.on_click(lambda e: self.shell.apply_style(e.new))
        return menu

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
        title, objs = self.panes[kind].kind_objs(doc)
        bars = kind_bar_rows(self, doc, kind)
        return title, [*objs, bars] if bars is not None else objs

    # ------------------------------------------------------------ a panel
    def _panel(self, doc, node):
        return self.panes[nodes.panel_of(doc, node)["kind"]].panel_objs(doc, node)

    # ------------------------------------------------------------ a layer
    def _layer(self, doc, node):
        return self.panes[nodes.panel_of(doc, node)["kind"]].layer_objs(doc, node)
