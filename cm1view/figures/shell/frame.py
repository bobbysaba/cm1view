"""The three panes and what runs them: the document, the node picked, undo and the preview.
The figure's data and pools are the FigureEditor's."""

import base64
import html
import io
import json
import os
import struct
import time as _time
import traceback
from functools import partial

import panel as pn

from .. import draw as figdraw, settings as table, spec as fg
from ...theme import GRID
from ..click import ClickImage, panel_boxes, place_map, watch_tight
from ..draw.base import _cell
from ..runs import AllFields
from ..times import _tlabel
from ...viewer.ui import out_of_flow
from . import docedit as de, nodes, scrub, vision
from .exportview import ExportDialog
from .inspector import Inspector
from .placing import Placing
from .treeview import TreeView

HISTORY = 50  # undo steps kept
FIT = "max-width:100%;max-height:100%;width:auto;height:auto;"


def preview_doc(doc, dpi):
    """The document to draw for a preview at dpi: a 3D scene's picture at that resolution."""
    return fg.doc_scene_dpi(doc, dpi)


def preview_dpi(doc):
    """Sharp at the page's size, and on screen at 96 px per inch when actual size."""
    return min(float((doc.get("export") or {}).get("dpi", 250)),
               max(1100.0 / max(float(doc["size"][0]), 0.5), 192.0))


def _code_waits(doc, note):
    """Code in a figure read from a file stays off until ticked: `note`, saying so if it has any."""
    code = doc.get("code") or {}
    if code.get("on") and str(code.get("text") or "").strip():
        doc["code"] = dict(code, on=False)
        note += (". It has code of its own (<b>Your own code</b>): read it, then tick <b>Run the "
                 "code</b>.")
    return note


class FigureShell:
    def __init__(self, ed):
        self.ed, self.v = ed, ed.v
        self.doc, self.node = None, nodes.FIGURE
        self.showing = False  # (the Figure workspace has been opened: it draws from then on)
        self._stale = True  # (the panes don't show the document yet)
        self.made = False  # (a figure made or opened, not the example the page starts with)
        self._base = None  # (the document as it came, to tell whether it was edited)
        self._kept = None  # (the document as last autosaved)
        self._said = ""  # (a line for under the next preview)
        self._hist, self._future = [], []
        self._req = 0
        self._boxes = {}  # panel -> where it is in the preview
        self._png = None
        self._seen_key, self._seen_png = None, ""  # (the vision preview's last picture)
        self._frames = None  # (the scrubber's: key, offsets, labels, saved frame)
        self._dt = None  # (how far the preview is moved from the saved figure; None: not)
        self._syncing = False
        self.fields = ed.fields  # (the fields of the document's runs: _sync_fields)
        self._build()

    # ------------------------------------------------------------ widgets
    def _build(self):
        ib = dict(name="", button_type="light", button_style="outline", width=36, height=32,
                  margin=(4, 2))
        self.tree_btn = pn.widgets.Button(icon="layout-sidebar", description="Show or hide the "
                                                                             "tree", **ib)
        self.undo_btn = pn.widgets.Button(icon="arrow-back-up", description="Undo", **ib)
        self.redo_btn = pn.widgets.Button(icon="arrow-forward-up", description="Redo", **ib)
        self.new_btn = pn.widgets.Button(
            icon="file-plus", description="New figure: what the panels show, the grid, field "
                                          "and width; or a template, or a saved figure (Undo "
                                          "takes it back)", **ib)
        self.exp_btn = pn.widgets.Button(name="Export", icon="download", height=32, margin=(4, 4),
                                         button_type="primary",
                                         description="Save or download the image, an animation "
                                                     "or a template")
        self.update = pn.widgets.Button(name="Redraw", icon="refresh", height=32, margin=(4, 4),
                                        button_type="primary", button_style="outline")
        self.auto = pn.widgets.Checkbox(name="Auto-redraw", value=True, margin=(4, 8),
                                       align="center")
        self.zoom = pn.widgets.RadioButtonGroup(
            options={"Fit": "fit", "Actual size": "actual"}, value="fit", height=32, margin=(4, 4),
            description="Actual size: as large as the printed figure (at 96 pixels per inch) to "
                        "judge the font sizes")
        self.vision = pn.widgets.Select(
            name="", options=dict(vision.MODES), value="", width=170, height=32, margin=(4, 4),
            description="Preview only: how the picture reads in greyscale or with a colour-vision "
                        "deficiency (Machado et al. 2009, full loss of one cone type). The "
                        "figure, its document, undo and every export are unchanged.")
        self.status = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8),
                                   styles={"flex": "0 0 auto"})
        self.image = ClickImage(sizing_mode="stretch_both", margin=(4, 8), fit=True)
        sb = dict(name="", button_type="light", button_style="outline", width=34, height=30,
                  margin=(2, 2))
        self.scr_prev = pn.widgets.Button(icon="player-skip-back", description="One output "
                                                                               "earlier", **sb)
        self.scr_next = pn.widgets.Button(icon="player-skip-forward", description="One output "
                                                                                  "later", **sb)
        self.scr_slider = pn.widgets.IntSlider(name="", start=0, end=1, value=0, step=1,
                                               show_value=False, sizing_mode="stretch_width",
                                               margin=(4, 8), height=30)
        self.scr_label = pn.pane.HTML("", margin=(6, 4), width=230, styles={"flex": "0 0 auto"})
        self.scr_keep = pn.widgets.Button(name="Keep this time", height=30, margin=(2, 2),
                                          button_type="light", button_style="outline",
                                          description="Move the figure's panels to the time "
                                                      "shown (Undo takes it back); the saved "
                                                      "figure otherwise stays where it was")
        self.scr_back = pn.widgets.Button(name="Saved time", height=30, margin=(2, 2),
                                          button_type="light", button_style="outline",
                                          description="Back to the time the figure is at")
        self.scrubber = pn.Row(self.scr_prev, self.scr_slider, self.scr_next, self.scr_label,
                               self.scr_back, self.scr_keep, margin=0, visible=False,
                               sizing_mode="stretch_width", align="center",
                               styles={"flex": "0 0 auto"})
        self.tree = TreeView(sizing_mode="stretch_width", margin=(4, 2))
        self.tree_pane = pn.Column(self.tree, width=240, scroll="y-auto",
                                   sizing_mode="stretch_height",
                                   styles={"border-right": f"1px solid {GRID}",
                                           "flex": "0 0 auto", "overflow-x": "hidden"})
        self.placing = Placing(self)
        self.inspector = Inspector(self)
        self.export = ExportDialog(self)
        # (the tree's button stays over the tree; the rest is right-aligned, Export last)
        actions = pn.Row(self.new_btn, self.undo_btn, self.redo_btn, self.auto,
                         self.update, self.exp_btn, margin=0, align="center")
        toolbar = pn.FlexBox(self.tree_btn, actions, flex_wrap="wrap", align_items="center",
                             justify_content="space-between", sizing_mode="stretch_width",
                             styles={"flex": "0 0 auto", "border-bottom": f"1px solid {GRID}"})

        def label(text):
            return pn.pane.HTML(f'<span class="cv-hint">{text}</span>', margin=(4, 2, 4, 10),
                                align="center")

        # (these change the preview alone, so they sit on it)
        view_bar = pn.FlexBox(label("Size"), self.zoom, label("Colours"), self.vision,
                              label("Mouse"), self.placing.mode, flex_wrap="wrap",
                              align_items="center", sizing_mode="stretch_width",
                              styles={"flex": "0 0 auto"})
        self.picture = pn.Column(self.image, margin=0, sizing_mode="stretch_both",
                                 styles={"flex": "1 1 0", "min-height": "0", "overflow": "auto"})
        preview = pn.Column(view_bar, self.placing.hint, self.picture, self.scrubber, self.status, margin=0,
                            sizing_mode="stretch_both",
                            styles={"flex": "1 1 0", "min-width": "0", "min-height": "0"})
        self.panes = pn.Row(self.tree_pane, preview, self.inspector.panel, margin=0,
                            sizing_mode="stretch_both",
                            styles={"flex": "1 1 0", "min-height": "0"})
        self.panel = pn.Column(toolbar, self.panes, out_of_flow(self.export.dlg), margin=0,
                               sizing_mode="stretch_both", styles={"min-height": "0"})
        self.tree_btn.on_click(lambda e: setattr(self.tree_pane, "visible",
                                                 not self.tree_pane.visible))
        self.new_btn.on_click(lambda e: self.new_figure())
        self.exp_btn.on_click(lambda e: self.export.open())
        self.undo_btn.on_click(lambda e: self.undo())
        self.redo_btn.on_click(lambda e: self.redo())
        self.update.on_click(lambda e: self.request(force=True, delay=False))
        self.auto.param.watch(lambda e: self.request() if e.new else None, "value")
        self.zoom.param.watch(lambda e: self._show_image(), "value")
        self.vision.param.watch(lambda e: self._show_image(), "value")
        self.scr_slider.param.watch(self._on_scrub, "value")
        self.scr_prev.on_click(lambda e: self._scrub_by(-1))
        self.scr_next.on_click(lambda e: self._scrub_by(1))
        self.scr_back.on_click(lambda e: self._scrub_saved())
        self.scr_keep.on_click(lambda e: self.keep_scrub())
        self.tree.param.watch(lambda e: self.select(e.new[0]) if e.new else None, "pick")
        self.image.param.watch(self._on_click, "click")
        self.image.param.watch(self._on_drag, "drag")

    # ------------------------------------------------------------ showing it
    def open(self):
        """The Figure workspace is shown: the panes show the document and it is drawn."""
        self.showing = True
        if self._stale:
            self._show(self.node if nodes.still_there(self.doc, self.node) else nodes.FIGURE)
        self.request(force=True, delay=False)

    def start(self, spec):
        """The example the page starts with, which isn't a figure of the user's to keep."""
        self.doc = fg.to_doc(spec)
        self._follow_size(de.kind_size(self.doc))
        self._came_as_it_is()
        self._sync_fields()

    def _came_as_it_is(self):
        self._base, self._kept = json.dumps(self.doc, sort_keys=True, default=float), None

    def _take(self, doc, note="", save_as=None, render=True, fit=True):
        """Document doc is now the figure (Undo goes back to what was here).  fit: an automatic
        size follows its panels (a document as saved stays as it was)."""
        ed = self.ed
        if self.doc is not None:
            self._keep()
            self._future = []
        self.doc = doc
        self.made = True
        self._said = note
        self._sync_fields()
        if fit:
            self._follow_size(de.kind_size(doc))
        self._came_as_it_is()
        self._kept = self._base if not render else None  # (a session's: as it was left)
        if save_as:
            ed.path.value = save_as
        if self.showing:
            self._show(nodes.FIGURE)
            if render:
                self.request(force=True, delay=False)
        else:
            self.node, self._stale = nodes.FIGURE, True

    def new_form(self, spec):
        """A new figure's version-1 spec, as it goes into the document: what it doesn't name at
        its default."""
        ed = self.ed
        s = table.filled(fg.normalize(spec, ed.run, ed._own_track()))
        if (s.get("letters") or {}).get("auto"):  # (one panel: no letter)
            s["letters"] = dict(s["letters"], on=figdraw.npanels(s) > 1)
        cb = s["colorbar"]
        if not cb.get("location"):  # (its boxes say where it is)
            s["colorbar"] = dict(cb, location="bottom" if cb.get("orientation", "horizontal")
                                 == "horizontal" else "right")
        for k, r in enumerate(s["runs"]):
            r.setdefault("color", figdraw.RUN_COLORS[k % len(figdraw.RUN_COLORS)])
        return s

    def new_doc(self, spec):
        """The document of a new figure's version-1 spec, made here."""
        return fg.to_doc(self.new_form(spec))

    def open_new(self, spec, note=""):
        """A new figure, from a version-1 spec (what the viewer's tools make)."""
        self._take(self.new_doc(spec), note)

    def open_spec(self, spec, note="", save_as=None, render=True):
        """A figure saved in the older form (with what it lacks from this version's defaults)."""
        ed = self.ed
        d = fg.older_to_doc(spec, ed.run, ed.F, self.v.t, ed._own_track())
        self._take(d, _code_waits(d, note), save_as, render)

    def open_doc(self, doc, note="", save_as=None, render=True):
        """A saved figure, template or session's document."""
        ed = self.ed
        d = fg.doc_defaults(doc, ed.run, ed.F, self.v.t, ed._own_track())
        self._take(d, _code_waits(d, note), save_as, render, fit=False)

    def own_figure(self):
        """Whether this is more than the example the page starts with."""
        return self.made or json.dumps(self.doc, sort_keys=True, default=float) != self._base

    def state(self):
        """What a session or the autosave keeps of the figure."""
        return dict(doc=fg.plain_copy(self.doc), save_as=self.ed.path.value)

    def _keep_figure(self):
        """The autosave: this figure for the next page on this run, if it has changed and is more
        than the example."""
        j = json.dumps(self.doc, sort_keys=True, default=float)
        if j == self._kept:
            return
        self._kept = j
        if self.own_figure():
            self.ed._autosave()

    def apply_style(self, name):
        """Style preset `name` on the whole figure, saying what it did beyond the look (Undo takes
        it all back)."""
        old = self.doc
        new = fg.apply_style(old, name)
        said = []
        if new["size"][0] != old["size"][0]:
            said.append(f"width {old['size'][0]:g} → {new['size'][0]:g} in")
        e0, e1 = old.get("export") or {}, new.get("export") or {}
        if (e0.get("format"), e0.get("dpi")) != (e1.get("format"), e1.get("dpi")):
            said.append(f"saves as {str(e1.get('format')).upper()} at {e1.get('dpi')} DPI")
        self._said = f"{name} style applied" + (f": {', '.join(said)}" if said else "")

        def apply(d):
            d.clear()
            d.update(new)
        self.edit(apply, node=nodes.FIGURE)

    def new_figure(self):
        """The New dialog, over this figure: its gallery, templates and last figure."""
        self.ed.open_quick()

    def _show(self, node):
        """The tree, the outlines and the inspector for the document, with node picked."""
        self.node, self._stale = node, False
        self.placing.pending = None  # (a first click: of what was showing)
        self.tree.param.update(items=nodes.tree_items(self.doc, self.fields), sel=node)
        self._mark()
        self.inspector.show(node)
        self.undo_btn.disabled, self.redo_btn.disabled = not self._hist, not self._future

    def select(self, node):
        """Pick node (of the tree, or a panel clicked in the preview)."""
        if node == self.node or not nodes.still_there(self.doc, node):
            return
        self.node = node
        self.tree.sel = node
        self._mark()
        self.inspector.show(node)

    def _mark(self):
        self.image.marks = {str(i): self._boxes[i] for i in nodes.outlined(self.doc, self.node)
                            if i in self._boxes}

    def _on_click(self, ev):
        """A click places what Click to says, if anything, else picks the panel."""
        if not ev.new:
            return
        fx, fy = float(ev.new[0]), float(ev.new[1])
        if self.placing.on:
            self.placing.click(fx, fy)
            return
        hit = nodes.pick_at(self._boxes, fx, fy)
        self.select(nodes.FIGURE if hit is None else nodes.node_at(self.doc, hit))

    def _on_drag(self, ev):
        if ev.new and self.placing.on:
            self.placing.drag([float(v) for v in ev.new[:2]], [float(v) for v in ev.new[2:4]])

    # ------------------------------------------------------------ edits and undo
    def edit(self, fn, node=None):
        """Change the document: fn(doc), in place.  node: what is picked after it, shown anew
        (else what is shown stays: its widgets made the edit)."""
        if self.doc is None:
            return
        self._keep()
        snd, rows = de.kind_size(self.doc), de.grid_shape(self.doc)[0]
        fn(self.doc)
        self._follow_size(snd)
        self._follow_rows(rows)
        self._future = []
        self.tree.items = nodes.tree_items(self.doc, self.fields)
        self.undo_btn.disabled, self.redo_btn.disabled = False, True
        if node is not None:
            self._show(node if nodes.still_there(self.doc, node) else nodes.FIGURE)
        else:
            self.inspector.refresh_marks()
        self.request()

    def can_follow(self, doc=None):
        """Whether the figure's size can follow its panels: one kind of those moved here, on a
        plain grid (an estimate from one panel knows no spans, shares or other kinds)."""
        doc = self.doc if doc is None else doc
        grid = doc.get("grid") or {}
        kinds = {p["kind"] for p in doc["panels"]}
        return len(kinds) == 1 and not kinds & {"scene"} and \
            not grid.get("widths") and not grid.get("heights") and \
            all(_cell(p)[2:] == (1, 1) for p in doc["panels"])

    def _follow_size(self, snd_was=None):
        """A figure with an automatic size: the height of plan views or cross-sections for their
        width and grid; the size of the other kinds when what it depends on just changed
        (snd_was: what it gave before), and then a table's height, for its rows."""
        doc = self.doc
        if not doc.get("size_auto") or not self.can_follow():
            return
        kind = doc["panels"][0]["kind"]
        if kind not in ("plan", "xsec"):
            now = de.kind_size(doc)
            if now != snd_was and now is not None:
                doc["size"] = list(now)
                self.inspector.size_followed(doc["size"])
            if kind != "table":
                return
        try:
            h = self.fit_height(doc)
        except (KeyError, TypeError, ValueError):  # (settings it can't estimate from)
            return
        if abs(h - float(doc["size"][1])) > 0.02:
            doc["size"] = [float(doc["size"][0]), h]
            self.inspector.size_followed(doc["size"])

    def _follow_rows(self, rows):
        """Rows came or went in a figure whose size can't follow its panels (kinds mixed, spans):
        its height by the same share, or its panels would collapse.  It says so."""
        doc = self.doc
        now = de.grid_shape(doc)[0]
        if now == rows or self.can_follow():
            return
        w, h = (float(v) for v in doc["size"])
        doc["size"] = [w, round(h * now / rows, 2)]
        self._said = f"Height {h:g} → {doc['size'][1]:g} in, for {now} rows"
        self.inspector.size_followed(doc["size"])

    def fit_height(self, doc):
        """The estimate of the height (de.fit_height), of the first panel's settings."""
        res = figdraw.resolve(doc)
        q = res["panels"][0]
        grid = doc.get("grid") or {}
        s = dict(figdraw.panel_view(res, q), rows=grid.get("rows", 1), cols=grid.get("cols", 1),
                 size=doc["size"], suptitle=doc.get("suptitle") or "",
                 titles=[p["title"] for p in doc["panels"] if p.get("title")],
                 row_titles=[p["rowlabel"] for p in doc["panels"] if p.get("rowlabel")])
        if any("domain" in (p.get("opts") or {}) for p in doc["panels"]):
            s["shape"] = self._mean_shape(res, grid, s)
        if q["kind"] == "table":  # (its tallest table's rows: entries by their panel's place)
            cols = int(grid.get("cols", 1))
            s["tables"] = [dict(lay, panel=_cell(p)[0] * cols + _cell(p)[1])
                           for p in res["panels"] for lay in p["layers"]]
        return de.fit_height(s, self.ed.run)

    def _mean_shape(self, res, grid, s):
        """Plan views with areas of their own: a row is as tall as its tallest panel, so the
        figure's height goes by the mean of those (a row with no panel: as the first panel)."""
        tall = {}
        for q in res["panels"]:
            shape = de.panel_shape(figdraw.panel_view(res, q), self.ed.run)
            r = _cell(q)[0]
            tall[r] = max(tall.get(r, 0.0), shape)
        first = de.panel_shape(s, self.ed.run)
        rows = int(grid.get("rows", 1))
        return sum(tall.get(r, first) for r in range(rows)) / max(rows, 1)

    # ------------------------------------------------------------ the document's runs
    def _sync_fields(self):
        """The field lists: the fields of every run of the document."""
        fields = []
        for r in self.doc.get("runs") or []:
            try:
                fields.append(self.ed.open_run(r["path"])[1])
            except Exception:  # noqa: BLE001  (a run that can't be opened: its panels say)
                continue
        self.fields = AllFields(fields) if fields else self.ed.fields

    def time_opts(self, k):
        """{label: model time} of the outputs of the document's run k."""
        try:
            run = self.ed.open_run(self.doc["runs"][k]["path"])[0]
        except Exception:  # noqa: BLE001
            return {}
        return {_tlabel(t): float(t) for t in run.times}

    def other_runs(self):
        """{label: path} of the runs not in the document."""
        return self.ed._other_runs({os.path.abspath(r["path"]) for r in self.doc["runs"]})

    def add_run(self, path, node=None):
        """A run into the document.  Its place, or None (the status line says why)."""
        try:
            run = self.ed.open_run(path)[0]
        except Exception as e:  # noqa: BLE001
            self.say(f"Could not open {html.escape(path)}: {html.escape(str(e))}", True)
            return None
        entry = dict(fg.run_entry(run), id=de.new_run_id(self.doc))
        entry["color"] = figdraw.RUN_COLORS[len(self.doc["runs"]) % len(figdraw.RUN_COLORS)]

        def apply(d):
            d["runs"].append(entry)
        self.edit(apply, node=node)
        self._sync_fields()
        return len(self.doc["runs"]) - 1

    def _keep(self):
        self._hist.append(self._state())
        del self._hist[:-HISTORY]

    def _state(self):
        return json.dumps(self.doc, default=float), self.node

    def _restore(self, state):
        self.doc = json.loads(state[0])
        self._sync_fields()
        self._show(state[1] if nodes.still_there(self.doc, state[1]) else nodes.FIGURE)
        self.request()

    def _step(self, source, other):
        """One step back or on: the other list can return to this document, at the node of
        the edit this step crosses."""
        if source:
            state = source.pop()
            other.append((self._state()[0], state[1]))
            self._restore(state)

    def undo(self):
        self._step(self._hist, self._future)

    def redo(self):
        self._step(self._future, self._hist)

    # ------------------------------------------------------------ the preview
    # ------------------------------------------------------------ the time scrubber
    def _scrub_sync(self):
        """The scrubber's frames for the document as it is (they are found again only when
        where the panels are in time changed, which also puts the preview back at the saved
        time)."""
        try:
            key = scrub.scrub_key(self.doc)
        except Exception:  # noqa: BLE001
            key = None
        if self._frames is not None and self._frames[0] == key:
            return
        self._dt = None
        offs, labels, zero = [], [], 0
        if key is not None:
            try:
                offs, labels, zero = scrub.scrub_frames(
                    self.doc, lambda p: self.ed.open_run(p)[0])
            except Exception:  # noqa: BLE001  (a run that can't be opened: the panels say)
                offs, labels, zero = [], [], 0
        self._frames = (key, offs, labels, zero)
        self._syncing = True
        try:
            self.scrubber.visible = bool(offs)
            if offs:
                self.scr_slider.param.update(end=len(offs) - 1, value=zero)
        finally:
            self._syncing = False
        self._scrub_label()

    def _scrub_label(self):
        if not self._frames or not self._frames[1]:
            return
        _, offs, labels, zero = self._frames
        i = self.scr_slider.value
        off = i != zero
        self.scr_label.object = (f'<div class="cv-hint"><b>{labels[i]}</b>' +
                                 (f' (saved: {labels[zero]})' if off else " (saved)") + "</div>")
        self.scr_back.disabled = self.scr_keep.disabled = not off

    def _on_scrub(self, ev):
        if self._syncing or not self._frames or not self._frames[1]:
            return
        _, offs, _, zero = self._frames
        i = int(ev.new)
        self._dt = None if i == zero else offs[i]
        self._scrub_label()
        self.request(force=True, wait=150)  # (a drag gives one drawing when it settles)

    def _scrub_by(self, n):
        s = self.scr_slider
        s.value = max(s.start, min(s.end, s.value + n))

    def _scrub_saved(self):
        if self._frames and self._frames[1]:
            self.scr_slider.value = self._frames[3]

    def keep_scrub(self):
        """The panels at the time shown, in the document (one undo step)."""
        dt = self._dt
        if dt is None or self.doc is None:
            return
        self._dt = None

        def apply(d):
            new = fg.shift_times(d, dt)
            d.clear()
            d.update(new)
        self.edit(apply)

    def _shown_doc(self):
        """The document to draw: a copy, moved to the time the scrubber shows."""
        if self._dt is None:
            return json.loads(json.dumps(self.doc, default=float))
        return fg.shift_times(self.doc, self._dt)

    def request(self, force=False, delay=True, wait=400):
        """Draw the preview again (shortly: several quick changes give one drawing)."""
        if not (force or self.auto.value):
            if self.showing:  # (no drawing to wait for)
                self._keep_figure()
            return
        self._req += 1
        n = self._req
        doc = self.v.doc
        if delay and doc is not None:
            doc.add_timeout_callback(partial(self._fire, n), wait)
        else:
            self._fire(n)

    def _fire(self, n):
        if n != self._req or not self.showing:
            return
        self._keep_figure()
        self._scrub_sync()
        self.ed._preview_waiting = True  # (a GIF being saved lets it in after a frame)
        self.v.gen["fig"] += 1
        self.say('<span class="busy">● Rendering…</span>')
        self.v.pools["fig"].submit(self._job, self.v.gen["fig"], self._shown_doc())

    def _job(self, g, doc):
        t0, ed = _time.time(), self.ed
        ed._preview_waiting = False

        def cancelled():
            return g != self.v.gen["fig"]

        def progress(i, n):
            self.v._schedule(partial(self.say, f'<span class="busy">● Reading panel {i + 1}/{n}'
                                               '…</span>'))

        try:
            ed.data.ser_touch = set()
            data = ed.data.panel_data(doc, progress, cancelled)
            if data is None:
                return
            ed.data.ser_live = ed.data.ser_touch
            dpi = preview_dpi(doc)
            fig = figdraw.draw(preview_doc(doc, dpi), data)
            code_err = getattr(fig, "_cv_code_error", None)
            watch_tight(fig)
            buf = io.BytesIO()
            figdraw.save(doc, fig, buf, format="png", **fg.save_kw(doc, dpi))
            raw = buf.getvalue()
            wh = struct.unpack(">II", raw[16:24])  # the PNG header's width and height
            boxes = panel_boxes(fig, doc, wh, dpi)
            place = place_map(fig, doc, wh, dpi)
            note = self._note(doc, data, wh, dpi, _time.time() - t0, code_err)
            self.v._schedule(partial(self._apply, g, base64.b64encode(raw).decode(), wh, dpi,
                                     doc.get("background"), boxes, note, (doc, place, data)))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.v._schedule(partial(self.say, f"Could not draw: {html.escape(str(e))}", True))

    def _note(self, doc, data, wh, dpi, secs, code_err):
        """The line under the preview: the figure as saved, and what is missing from it."""
        out = float((doc.get("export") or {}).get("dpi", 250))
        w, h = wh[0] / dpi, wh[1] / dpi
        n = len(doc["panels"])
        note = (f"{n} panel{'s' if n != 1 else ''} · {w:.2f} × {h:.2f} in as saved "
                f"({w * out:.0f} × {h * out:.0f} px at {out:g} dpi) · {secs:.1f} s")
        said = list(dict.fromkeys(str(d["notes"]) for d in data.values() if d.get("notes")))
        if said:
            note += " · " + html.escape("; ".join(said))
        if {p["kind"] for p in doc["panels"]} & {"th", "line"} and self.ed.series_pending():
            pend = "; ".join(p for p in self.ed.series_pending() if p)
            note += f' · <span class="busy">● computing series {html.escape(pend)}</span>'
        if code_err:
            note += f' · <span style="color:#f87171">your code stopped at ' \
                    f'{html.escape(code_err)}</span>'
        names = nodes.letters(doc)
        miss = [names[i] for i, d in data.items() if d.get("missing") and i in names]
        if miss:
            note += f" · no data in panel{'s' if len(miss) > 1 else ''} " + ", ".join(miss)
        if any(i < 0 and d.get("missing") for i, d in data.items()):
            note += " · no data in an inset"
        return note

    def _apply(self, g, png, wh, dpi, bg, boxes, note, drawn):
        if g != self.v.gen["fig"] or not self.showing:
            return
        self._png = (png, wh, dpi, bg)
        self._boxes = boxes
        self.placing.took(drawn[0], drawn[1], boxes, drawn[2])
        self._show_image()
        self._mark()
        self.say(f"{self._said} · {note}" if self._said else note)
        self._said = ""

    def _seen(self, png):
        """The drawn picture (base64 PNG) as the vision preview says (vision.py); the one just
        made is kept for the next look at it."""
        mode = self.vision.value
        self.vision.styles = {"outline": "2px solid #f59e0b", "border-radius": "4px"} if mode \
            else {}
        if not mode:
            return png
        if self._seen_key != (png, mode):
            self._seen_key = (png, mode)
            self._seen_png = base64.b64encode(
                vision.simulate_png(base64.b64decode(png), mode)).decode()
        return self._seen_png

    def _show_image(self):
        if not self._png:
            return
        png, (w, _), dpi, bg = self._png
        png = self._seen(png)
        back = ("background:repeating-conic-gradient(#d4d4d4 0% 25%, #fff 0% 50%) 50% / "
                "16px 16px;" if bg == "none" else "")
        size = f"width:{w / dpi * 96:.0f}px;max-width:none;" if self.zoom.value == "actual" \
            else FIT
        self.image.param.update(src=f"data:image/png;base64,{png}",
                                fit=self.zoom.value != "actual",
                                css=f"{size}{back}cursor:{self.placing.cursor()};display:block;"
                                    "margin:auto;"
                                    "box-shadow:0 4px 18px rgba(0,0,0,.5)")

    def say(self, text, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.status.object = f'<div class="cv-status"{col}>{text}</div>'
