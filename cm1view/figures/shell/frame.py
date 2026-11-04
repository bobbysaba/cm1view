"""The three panes and what runs them: the document, the node picked, undo and the preview.
The figure's data and pools are the FigureEditor's, so its caches are shared with the old
layout."""

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

from .. import draw as figdraw, spec as fg
from ...theme import GRID
from ..click import ClickImage, panel_boxes, watch_tight
from ..draw.base import _cell
from ..runs import AllFields
from ..times import _tlabel
from . import docedit as de, nodes
from .inspector import Inspector
from .treeview import TreeView

HISTORY = 50  # undo steps kept
FIT = "max-width:100%;max-height:100%;width:auto;height:auto;"


def preview_doc(doc, dpi):
    """The document to draw for a preview at dpi: a 3D scene's picture at that resolution."""
    scene = (doc.get("kinds") or {}).get("scene")
    if not scene or "scene3d" not in scene:
        return doc
    kinds = dict(doc["kinds"], scene=dict(scene, scene3d=dict(scene["scene3d"], dpi=dpi)))
    return dict(doc, kinds=kinds)


def preview_dpi(doc):
    """Sharp at the page's size, and on screen at 96 px per inch when actual size."""
    return min(float((doc.get("export") or {}).get("dpi", 250)),
               max(1100.0 / max(float(doc["size"][0]), 0.5), 192.0))


class FigureShell:
    def __init__(self, ed):
        self.ed, self.v = ed, ed.v
        self.doc, self.node = None, nodes.FIGURE
        self.showing = False
        self._src = None  # (the old editor's figure the document came from)
        self._hist, self._future = [], []
        self._req = 0
        self._boxes = {}  # panel -> where it is in the preview
        self._png = None
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
                                         button_type="primary", disabled=True,
                                         description="Not here yet: in the old layout")
        self.update = pn.widgets.Button(name="Redraw", icon="refresh", height=32, margin=(4, 4),
                                        button_type="primary", button_style="outline")
        self.auto = pn.widgets.Checkbox(name="Live", value=True, margin=(4, 8), align="center")
        self.zoom = pn.widgets.RadioButtonGroup(
            options={"Fit": "fit", "Actual size": "actual"}, value="fit", height=32, margin=(4, 4),
            description="Actual size: as large as the printed figure (at 96 pixels per inch) to "
                        "judge the font sizes")
        self.back = pn.widgets.Button(name="Old layout", icon="layout-columns", height=32,
                                      margin=(4, 4), button_type="light", button_style="outline",
                                      description="Back to the old editor and its figure: what "
                                                  "was changed here stays here")
        self.status = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8),
                                   styles={"flex": "0 0 auto"})
        self.image = ClickImage(sizing_mode="stretch_both", margin=(4, 8), fit=True)
        self.tree = TreeView(sizing_mode="stretch_width", margin=(4, 2))
        self.tree_pane = pn.Column(self.tree, width=240, scroll="y-auto",
                                   sizing_mode="stretch_height",
                                   styles={"border-right": f"1px solid {GRID}",
                                           "flex": "0 0 auto", "overflow-x": "hidden"})
        self.inspector = Inspector(self)
        toolbar = pn.FlexBox(self.tree_btn, self.exp_btn, self.update, self.auto, self.new_btn,
                             self.undo_btn, self.redo_btn, self.zoom, self.back,
                             flex_wrap="wrap", align_items="center", sizing_mode="stretch_width",
                             styles={"flex": "0 0 auto", "border-bottom": f"1px solid {GRID}"})
        self.picture = pn.Column(self.image, margin=0, sizing_mode="stretch_both",
                                 styles={"flex": "1 1 0", "min-height": "0", "overflow": "auto"})
        preview = pn.Column(self.picture, self.status, margin=0, sizing_mode="stretch_both",
                            styles={"flex": "1 1 0", "min-width": "0", "min-height": "0"})
        self.panes = pn.Row(self.tree_pane, preview, self.inspector.panel, margin=0,
                            sizing_mode="stretch_both",
                            styles={"flex": "1 1 0", "min-height": "0"})
        self.panel = pn.Column(toolbar, self.panes, margin=0, sizing_mode="stretch_both",
                               visible=False, styles={"min-height": "0"})
        self.tree_btn.on_click(lambda e: setattr(self.tree_pane, "visible",
                                                 not self.tree_pane.visible))
        self.new_btn.on_click(lambda e: self.new_figure())
        self.undo_btn.on_click(lambda e: self.undo())
        self.redo_btn.on_click(lambda e: self.redo())
        self.update.on_click(lambda e: self.request(force=True, delay=False))
        self.auto.param.watch(lambda e: self.request() if e.new else None, "value")
        self.zoom.param.watch(lambda e: self._show_image(), "value")
        self.back.on_click(lambda e: self.close())
        self.tree.param.watch(lambda e: self.select(e.new[0]) if e.new else None, "pick")
        self.image.param.watch(self._on_click, "click")

    # ------------------------------------------------------------ showing it
    def open(self):
        """Show the old editor's figure here (as it was left here, if it hasn't changed)."""
        ed = self.ed
        why = self._take_old()
        if why:
            ed._msg(f"This figure could not be opened in the new layout: {why}", True)
            return
        self.showing = True
        ed.panel.visible, self.panel.visible = False, True
        self._show(self.node if nodes.still_there(self.doc, self.node) else nodes.FIGURE)
        self.request(force=True, delay=False)

    def _take_old(self):
        """The old editor's figure into the document, if it changed since (Undo goes back to
        what was here).  Why it can't be, or None."""
        try:
            src = json.dumps(self.ed.collect_all(), sort_keys=True, default=float)
            if src != self._src:
                doc = fg.to_doc(json.loads(src))
                if self.doc is not None:
                    self._keep()
                    self._future = []
                self.doc, self._src = doc, src
                self._sync_fields()
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return str(e)
        return None

    def new_figure(self):
        """The quick start, over this figure: its gallery, templates and last figure."""
        ed = self.ed
        ed.open_quick()
        grid = self.doc.get("grid") or {}
        ed.qs_rows.value, ed.qs_cols.value = int(grid.get("rows", 1)), int(grid.get("cols", 1))

    def take_figure(self):
        """The quick start made or opened a figure, which it does in the old editor: here
        now."""
        why = self._take_old()
        if why:
            self.say(f"This figure could not be opened here: {html.escape(why)}", True)
            return
        self._show(nodes.FIGURE)
        self.request(force=True, delay=False)

    def close(self):
        self.showing = False
        self.panel.visible, self.ed.panel.visible = False, True
        self.ed.request(force=True, delay=False)

    def _show(self, node):
        """The tree, the outlines and the inspector for the document, with node picked."""
        self.node = node
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
        if ev.new:
            hit = nodes.pick_at(self._boxes, float(ev.new[0]), float(ev.new[1]))
            self.select(nodes.FIGURE if hit is None else f"panel:{hit}")

    # ------------------------------------------------------------ edits and undo
    def edit(self, fn, node=None):
        """Change the document: fn(doc), in place.  node: what is picked after it, shown anew
        (else what is shown stays: its widgets made the edit)."""
        if self.doc is None:
            return
        self._keep()
        snd = de.sounding_size(self.doc)
        fn(self.doc)
        self._follow_size(snd)
        self._future = []
        self.tree.items = nodes.tree_items(self.doc, self.fields)
        self.undo_btn.disabled, self.redo_btn.disabled = False, True
        if node is not None:
            self._show(node if nodes.still_there(self.doc, node) else nodes.FIGURE)
        self.request()

    def can_follow(self, doc=None):
        """Whether the figure's size can follow its panels: plan views, or soundings, on a plain
        grid (an estimate from one panel knows no spans, shares or other kinds)."""
        doc = self.doc if doc is None else doc
        grid = doc.get("grid") or {}
        return {p["kind"] for p in doc["panels"]} in ({"plan"}, {"sounding"}) and \
            not grid.get("widths") and not grid.get("heights") and \
            all(_cell(p)[2:] == (1, 1) for p in doc["panels"])

    def _follow_size(self, snd_was=None):
        """A figure with an automatic size: the height of plan views for their width and grid;
        soundings' size when what it depends on just changed (snd_was: what it gave before)."""
        doc = self.doc
        if not doc.get("size_auto") or not self.can_follow():
            return
        if doc["panels"][0]["kind"] == "sounding":
            now = de.sounding_size(doc)
            if now != snd_was and now is not None:
                doc["size"] = list(now)
                self.inspector.size_followed(doc["size"])
            return
        try:
            h = self.fit_height(doc)
        except (KeyError, TypeError, ValueError):  # (settings it can't estimate from)
            return
        if abs(h - float(doc["size"][1])) > 0.02:
            doc["size"] = [float(doc["size"][0]), h]
            self.inspector.size_followed(doc["size"])

    def fit_height(self, doc):
        """The old editor's estimate (fit_height), of the first panel's settings."""
        res = figdraw.resolve(doc)
        q = res["panels"][0]
        grid = doc.get("grid") or {}
        s = dict(figdraw.panel_view(res, q), rows=grid.get("rows", 1), cols=grid.get("cols", 1),
                 size=doc["size"], suptitle=doc.get("suptitle") or "",
                 titles=[p["title"] for p in doc["panels"] if p.get("title")],
                 row_titles=[p["rowlabel"] for p in doc["panels"] if p.get("rowlabel")])
        return self.ed.fit_height(s)

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
    def request(self, force=False, delay=True):
        """Draw the preview again (shortly: several quick changes give one drawing)."""
        if not (force or self.auto.value):
            return
        self._req += 1
        n = self._req
        doc = self.v.doc
        if delay and doc is not None:
            doc.add_timeout_callback(partial(self._fire, n), 400)
        else:
            self._fire(n)

    def _fire(self, n):
        if n != self._req or not self.showing:
            return
        self.v.gen["fig"] += 1
        self.say('<span class="busy">● Rendering…</span>')
        self.v.pools["fig"].submit(self._job, self.v.gen["fig"], json.loads(json.dumps(
            self.doc, default=float)))

    def _job(self, g, doc):
        t0, ed = _time.time(), self.ed

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
            note = self._note(doc, data, wh, dpi, _time.time() - t0, code_err)
            self.v._schedule(partial(self._apply, g, base64.b64encode(raw).decode(), wh, dpi,
                                     doc.get("background"), boxes, note))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.v._schedule(partial(self.say, f"Could not draw: {html.escape(str(e))}", True))

    def _note(self, doc, data, wh, dpi, secs, code_err):
        """The line under the preview: the figure as saved, and what is missing from it."""
        out = float((doc.get("export") or {}).get("dpi", 250))
        w, h = wh[0] / dpi, wh[1] / dpi
        n = len(data)
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
        return note

    def _apply(self, g, png, wh, dpi, bg, boxes, note):
        if g != self.v.gen["fig"] or not self.showing:
            return
        self._png = (png, wh, dpi, bg)
        self._boxes = boxes
        self._show_image()
        self._mark()
        self.say(note)

    def _show_image(self):
        if not self._png:
            return
        png, (w, _), dpi, bg = self._png
        back = ("background:repeating-conic-gradient(#d4d4d4 0% 25%, #fff 0% 50%) 50% / "
                "16px 16px;" if bg == "none" else "")
        size = f"width:{w / dpi * 96:.0f}px;max-width:none;" if self.zoom.value == "actual" \
            else FIT
        self.image.param.update(src=f"data:image/png;base64,{png}",
                                fit=self.zoom.value != "actual",
                                css=f"{size}{back}cursor:pointer;display:block;margin:auto;"
                                    "box-shadow:0 4px 18px rgba(0,0,0,.5)")

    def say(self, text, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.status.object = f'<div class="cv-status"{col}>{text}</div>'
