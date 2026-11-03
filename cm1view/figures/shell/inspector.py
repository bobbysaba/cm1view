"""The inspector: the settings of the one thing picked in the tree, and what an edit reaches.
Only what is shown exists as widgets: a node's are made when it is picked.

So far: the figure's size and title, the runs, a panel's title; the rest is shown, not yet
edited."""

import html
import os

import panel as pn

from ... import config
from .. import draw as figdraw
from ..cards import _hex, _row
from ..cards.base import _f
from ..draw.base import _cell
from ..runs import TYPE_PATH, _track_options, _track_path
from . import nodes
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


def grid_map(doc):
    """The grid with each panel's letter where it sits (a table: spans shown as spans)."""
    grid, names = doc.get("grid") or {}, nodes.letters(doc)
    rows, cols = int(grid.get("rows", 1)), int(grid.get("cols", 1))
    at = {tuple(_cell(p)[:2]): p for p in doc.get("panels") or []}
    covered, trs = set(), []
    for r in range(rows):
        tds = []
        for c in range(cols):
            if (r, c) in covered:
                continue
            p = at.get((r, c))
            rs, cs = _cell(p)[2:] if p else (1, 1)
            covered.update((r + a, c + b) for a in range(rs) for b in range(cs))
            tds.append(f'<td rowspan="{rs}" colspan="{cs}" style="border:1px solid {GRID};'
                       f'text-align:center;min-width:28px;height:24px;padding:2px">'
                       f'{names[p["id"]] if p else "·"}</td>')
        trs.append(f'<tr>{"".join(tds)}</tr>')
    return pn.pane.HTML(f'<table style="border-collapse:collapse;font-size:12px">{"".join(trs)}'
                        '</table>', margin=(4, 4))


class Inspector:
    def __init__(self, shell):
        self.shell = shell
        self.head = pn.pane.HTML(margin=(4, 4, 0, 4), sizing_mode="stretch_width")
        self.body = pn.Column(margin=0, sizing_mode="stretch_width")
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
        title = pn.widgets.TextInput(name="Figure title", value=doc.get("suptitle") or "",
                                     sizing_mode="stretch_width")

        def on_size(ev):
            if width.value and height.value:
                self.shell.edit(lambda d: d.update(size=[float(width.value), float(height.value)],
                                                   size_auto=False))

        width.param.watch(on_size, "value")
        height.param.watch(on_size, "value")
        title.param.watch(lambda ev: self.shell.edit(
            lambda d: d.update(suptitle=ev.new.strip())), "value")
        objs = [_row(width, height), title, _note("Where the panels sit:"), grid_map(doc)]
        for text in doc.get("notes") or []:
            objs.append(_note(html.escape(str(text))))
        return objs

    # ------------------------------------------------------------ the runs
    def _runs(self, doc):
        used, names = nodes.runs_used(doc), nodes.letters(doc)
        objs = [self._run_row(r, k, used.get(r["id"], []), names, len(doc["runs"]))
                for k, r in enumerate(doc.get("runs") or [])]
        have = {os.path.abspath(r["path"]) for r in doc.get("runs") or []}
        others = self.shell.ed._other_runs(have)
        if others:
            pick = pn.widgets.Select(name="Add a run", options=others, sizing_mode="stretch_width")
            add = pn.widgets.Button(name="Add", width=70, align="end", button_type="primary",
                                    button_style="outline")
            add.on_click(lambda ev: self._add_run(pick.value))
            objs.append(pn.Row(pick, add, margin=0, sizing_mode="stretch_width"))
        return objs

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
                description="The model time this run counts from: time labels and legends "
                            "count this run's times from it")
        label.param.watch(lambda ev: change(label=ev.new), "value")
        color.param.watch(lambda ev: change(color=ev.new), "value")
        t0.param.watch(lambda ev: change(t0_min=float(ev.new or 0.0)), "value")
        track = self._track_widgets(r, own, change)
        rm = pn.widgets.Button(name="✕", width=32, height=28, margin=(2, 1), button_type="default",
                               button_style="outline", disabled=bool(used) or n < 2,
                               description="Remove the run" if not used else
                               "In use by panel " + ", ".join(names[i] for i in used))
        rm.on_click(lambda ev: self.shell.edit(
            lambda d: d.update(runs=[x for x in d["runs"] if x["id"] != rid]), node=nodes.RUNS))
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
        def apply(d):
            ids = {r["id"] for r in d["runs"]}
            n = len(d["runs"])
            while f"r{n}" in ids:
                n += 1
            d["runs"].append(dict(id=f"r{n}", path=path, label=os.path.basename(path), track="",
                                  color=figdraw.RUN_COLORS[len(d["runs"]) %
                                                           len(figdraw.RUN_COLORS)]))
        self.shell.edit(apply, node=nodes.RUNS)

    # ------------------------------------------------------------ all panels of a kind
    def _kind(self, doc, node):
        kind = node.partition(":")[2]
        mine = [p for p in nodes.in_order(doc) if p["kind"] == kind]
        names, fields = nodes.letters(doc), self.shell.ed.fields
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
        pid = p["id"]
        letter = nodes.letters(doc)[pid]
        fields = self.shell.ed.fields
        r, c, rs, cs = _cell(p)

        def apply(d, value):
            next(x for x in d["panels"] if x["id"] == pid)["title"] = value

        title = pn.widgets.TextInput(name="Title", value=p.get("title") or "",
                                     sizing_mode="stretch_width")
        title.param.watch(lambda ev: self.shell.edit(lambda d: apply(d, ev.new.strip())), "value")
        rows = [("Kind", nodes.KINDS[p["kind"]].label if p["kind"] in nodes.KINDS else p["kind"]),
                ("Place", f"row {r + 1}, column {c + 1}"
                          + (f", {rs} × {cs} cells" if (rs, cs) != (1, 1) else ""))]
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
                                   _note("Shown only, apart from the title: editing comes with "
                                         "each kind's move here.")]

    # ------------------------------------------------------------ a layer
    def _layer(self, doc, node):
        p = nodes.panel_of(doc, node)
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
        name = nodes.layer_name(lay, self.shell.ed.fields)
        return f"{name} in panel {letter}", [
            _lines([x for x in rows if x[1]]),
            _note("Shown only: editing comes with each kind's move here.")]
