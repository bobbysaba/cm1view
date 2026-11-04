"""The figure's grid in the inspector: its rows, columns and their shares, adding a panel of any
kind that has moved here, and on each panel, the cells it covers, a copy of it, removing it.
Kinds mix freely: a panel is only a kind at a place."""

import html

import panel as pn

from .. import spec as fg
from ...theme import GRID
from ..cards import _grid
from ..draw.base import _cell
from ..kinds import KINDS
from ..spec.doc import KIND_KEYS
from ..times import _nearest_t
from . import docedit as de, nodes
from .looks import panel_bar_card

# (the kinds edited here)
ADDABLE = ("plan", "sounding", "xsec", "th", "line", "dist", "profile", "joint", "azim", "table",
           "scene")
NEW_ROW, NEW_COL = "new row", "new column"


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


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


def _shares_text(vals):
    return ", ".join(f"{float(v):g}" for v in vals or [])


def _numbers(text):
    """Numbers typed with commas or spaces.  ValueError: others."""
    return [float(x) for x in text.replace(",", " ").split()]


def main_kind(doc):
    """The kind most of the figure's panels are (the first such: tied)."""
    kinds = [p["kind"] for p in doc.get("panels") or []]
    return max(kinds, key=kinds.count) if kinds else "plan"


def kind_options(also=None):
    """The kinds to choose from, by name (also: a kind not otherwise listed)."""
    extra = (also,) if also and also not in ADDABLE else ()
    return {KINDS[k].label: k for k in (*ADDABLE, *extra)}


def moment_of(p):
    """The run and time panel p shows: its own, else its first entry's that has them."""
    items = [p, *(p.get("layers") or [])]
    return (next((x["run"] for x in items if x.get("run") is not None), None),
            next((x["time_s"] for x in items if x.get("time_s") is not None), None))


def to_moment(p, run, time_s):
    """New panel p, and its entries, show that run and time, where they have one."""
    for x in (p, *(p.get("layers") or [])):
        if run is not None and x.get("run") is not None:
            x["run"] = run
        if time_s is not None and x.get("time_s") is not None:
            x["time_s"] = time_s


def own_run(shell):
    """The run new panels start with: the viewer's, if in the figure, else the first."""
    runs = shell.doc["runs"]
    here = shell.ed.run.path
    return next((r["id"] for r in runs if r["path"] == here), runs[0]["id"])


def shown_time(shell, rid):
    """The viewer's shown time, as the nearest output of run rid."""
    times = list(shell.time_opts(de.run_index(shell.doc, rid)).values())
    now = float(shell.ed.run.times[shell.v.t])
    return _nearest_t(times, now) if times else now


def new_sounding(shell, where=None):
    """A sounding at the shown time in the viewer's run: at the storm, or `where`."""
    rid = own_run(shell)
    e = fg.sounding_defaults(0, shown_time(shell, rid), where)
    e.pop("panel", None)
    return dict(e, type="sounding", run=rid)


def map_soundings(shell):
    """The soundings marked in the viewer's Sounding tool, as entries: in the viewer's run."""
    rid = own_run(shell)
    out = []
    for e in shell.ed.tab_soundings():
        e = {k: v for k, v in e.items() if k != "panel"}
        out.append(dict(e, type="sounding", run=rid, time_s=float(e["time_s"])))
    return out


class GridPane:
    def __init__(self, inspector):
        self.ins, self.shell = inspector, inspector.shell

    # ------------------------------------------------------------ the figure's
    def grid_objs(self, doc):
        """Rows, columns, their shares, where the panels sit, and adding one."""
        shell = self.shell
        rows, cols = de.grid_shape(doc)
        grid = doc.get("grid") or {}
        nr = pn.widgets.IntInput(name="Rows", start=1, end=12, value=rows)
        nc = pn.widgets.IntInput(name="Columns", start=1, end=12, value=cols)
        widths = pn.widgets.TextInput(name="Column widths", value=_shares_text(grid.get("widths")),
                                      placeholder="equal", description="Shares of the figure's "
                                      "width, one for each column, e.g. 2, 1")
        heights = pn.widgets.TextInput(name="Row heights", value=_shares_text(grid.get("heights")),
                                       placeholder="equal", description="Shares of the figure's "
                                       "height, one for each row")
        said = pn.pane.HTML(margin=(2, 4), sizing_mode="stretch_width")

        def problem(text):
            said.object = f'<div class="cv-status" style="color:#f87171">{html.escape(text)}</div>'

        def on_shape(ev):
            r, c = int(nr.value or 1), int(nc.value or 1)

            def apply(d):
                shell._said = de.set_grid(d, r, c) or ""
            shell.edit(apply, node=nodes.FIGURE)

        def on_shares(key, w):
            try:
                vals = _numbers(w.value)
            except ValueError:
                problem(f"“{w.value}” are not numbers.")
                return
            why = de.set_shares(de.plain(shell.doc), key, vals)
            if why:
                problem(why)
                return
            shell.edit(lambda d: de.set_shares(d, key, vals), node=nodes.FIGURE)

        nr.param.watch(on_shape, "value")
        nc.param.watch(on_shape, "value")
        widths.param.watch(lambda ev: on_shares("widths", widths), "value")
        heights.param.watch(lambda ev: on_shares("heights", heights), "value")
        objs = [_grid((self._type_widget(doc), 2), nr, nc, widths, heights, n=2), said,
                _note("Where the panels sit:"), grid_map(doc), *self._aside_objs(doc),
                *self._add_objs(doc)]
        if len({p["kind"] for p in doc.get("panels") or []}) > 1:
            objs.append(_note("Set the figure's size by hand: panels of several kinds have no "
                              "automatic one."))
        return objs

    def _type_widget(self, doc):
        """Which kind every panel of the figure is: choosing one changes them all."""
        kinds = {p["kind"] for p in doc.get("panels") or []}  # (those set aside change with them)
        one = next(iter(kinds)) if len(kinds) == 1 else None
        options = kind_options(one)
        if one is None:
            options = {"Mixed": "", **options}
        w = pn.widgets.Select(name="Figure type", options=options, value=one or "",
                              description="Change every panel to this type, in the cell it is in. "
                                          "What the panels showed is replaced; Undo takes it back. "
                                          "To change only one, pick it in the tree.")

        def on_type(ev):
            if ev.new:
                self.set_kind([p["id"] for p in self.shell.doc["panels"]], ev.new, nodes.FIGURE,
                              aside=True)

        w.param.watch(on_type, "value")
        return w

    def _aside_objs(self, doc):
        """The panels with no room on the grid, if any: back, or gone."""
        aside = doc.get(de.OFF_GRID) or []
        if not aside:
            return []
        shell = self.shell
        n = len(aside)
        what = ", ".join(dict.fromkeys(html.escape(KINDS[p["kind"]].label) for p in aside))
        back = pn.widgets.Button(name="Bring back", button_type="light", button_style="outline",
                                 height=30, margin=(4, 4),
                                 description="Into free cells; the grid grows if it has to")
        drop = pn.widgets.Button(name="Remove", button_type="light", button_style="outline",
                                 height=30, margin=(4, 4),
                                 description="Out of the figure. Undo takes it back")
        back.on_click(lambda e: shell.edit(de.bring_back, node=nodes.FIGURE))
        drop.on_click(lambda e: shell.edit(de.forget_aside, node=nodes.FIGURE))
        return [_note(f"<b>{n} panel{'s' if n > 1 else ''} set aside, not drawn</b> ({what}): no "
                      "room on this grid. They return when the grid has room."),
                pn.Row(back, drop, margin=0)]

    def _add_objs(self, doc):
        kinds = kind_options()
        free = {f"Row {r + 1}, column {c + 1}": (r, c) for r, c in de.free_cells(doc)}
        where = {**free, "A new row": NEW_ROW, "A new column": NEW_COL}
        mine = main_kind(doc)
        kind = pn.widgets.Select(name="Add a panel of", options=kinds,
                                 value=mine if mine in kinds.values() else "plan")
        place = pn.widgets.Select(name="At", options=where)
        go = pn.widgets.Button(name="Add the panel", button_type="primary", button_style="outline",
                               height=32, margin=(6, 4))
        go.on_click(lambda e: self.add_panel(kind.value, place.value))
        if not free:
            return [_grid(kind, place, n=2), go]
        fill = pn.widgets.Button(
            name=f"Fill {len(free)} empty cell{'s' if len(free) > 1 else ''}", button_type="light",
            button_style="outline", height=32, margin=(6, 4),
            description="A new panel of the type chosen in each empty cell")
        fill.on_click(lambda e: self.fill_empty(kind.value))
        return [_grid(kind, place, n=2), pn.Row(go, fill, margin=0)]

    def add_panel(self, kind, place=None):
        """A new panel of a kind at a cell (r, c), in a new row or column, or the first cell
        free; it is then what's picked.  Returns it."""
        shell = self.shell
        make = self._maker(kind)
        made = []

        def apply(d):
            grow = {NEW_ROW: "row", NEW_COL: "col"}.get(place)
            made.append(make(d, place if isinstance(place, tuple) else de.next_cell(d, grow)))

        # (the node goes by id, known only once it is made)
        shell.edit(apply)
        shell._show(f"panel:{made[0]['id']}")
        return made[0]

    def _maker(self, kind):
        """make(doc, cell): a new panel of a kind at a cell, as this moment's viewer starts it."""
        shell = self.shell
        spec = fg.default_spec(shell.ed.run, shell.ed.fields, shell.v.t)
        rid = own_run(shell)
        ts = shown_time(shell, rid)
        scene3d = shell.ed.viewer_scene() if kind == "scene" else None

        def make(d, at):
            start = {k: spec[k] for k in KIND_KEYS[kind] if k in spec}
            if kind == "scene":  # (the first shows what the 3D workspace does; seed_kind)
                start = dict(axes=dict(start.get("axes") or {}, **de.SCENE_START_AXES),
                             scene3d=scene3d)
            de.seed_kind(d, kind, start, KINDS[kind].labels)
            if kind == "plan":
                p = de.plan_panel(d, at, rid, ts, spec["layers"], fg.card_section(
                    spec["sections"][0]))
            elif kind == "xsec":
                p = de.xsec_panel(d, at, rid, ts, spec["layers"], fg.card_section(
                    spec["sections"][0]))
            elif kind == "scene":
                p = de.add_panel(d, kind, at, run=rid, time_s=ts)
            else:
                p = de.add_panel(d, kind, at, self.ins.panes[kind].first_entries())
            present = {KINDS[q["kind"]] for q in d["panels"]} | {KINDS[k] for k in ADDABLE}
            de.label_places(d, p, KINDS[kind], present)
            shell.inspector.folds.setdefault(f"p:{p['id']}:own0", True)
            return p

        return make

    def fill_empty(self, kind):
        """A new panel of a kind in every empty cell."""
        make = self._maker(kind)

        def apply(d):
            for at in de.free_cells(d):
                make(d, at)
        self.shell.edit(apply, node=nodes.FIGURE)

    def set_kind(self, pids, kind, node=None, aside=False):
        """Panels pids become new panels of a kind, each in the cell it holds (and what it
        spans) and at the run and time it shows; what they showed goes, one undo step.  node:
        what to show, else the last one made.  aside: those set aside change too.  Returns the
        new panels."""
        shell = self.shell
        make = self._maker(kind)
        made = []

        def apply(d):
            for pid in pids:
                old = de.panel_by_id(d, pid)
                if old["kind"] == kind:
                    continue
                cell, moment = list(_cell(old)), moment_of(old)
                de.remove_panel(d, pid)
                p = make(d, cell[:2])
                p["cell"] = cell
                to_moment(p, *moment)
                made.append(p)
            for n, old in enumerate(d.get(de.OFF_GRID) or [] if aside else []):
                if old["kind"] != kind:
                    p = make(d, _cell(old)[:2])
                    p["cell"] = list(_cell(old))
                    to_moment(p, *moment_of(old))
                    d["panels"].remove(p)
                    d[de.OFF_GRID][n] = p
                    de.drop_annotations(d, {old["id"]})
            if aside:
                de.letters_in_order(d)
        shell.edit(apply, node=node)
        if node is None and made:
            shell._show(f"panel:{made[-1]['id']}")
        return made

    def titles_objs(self, kind):
        """Titles of a kind's panels from what each shows, and clearing them (plan views': Fill
        panels)."""
        shell = self.shell

        def on_titles(e):
            shell.edit(lambda d: de.entry_titles(d, kind), node=shell.node)

        def on_clear(e):
            def apply(d):
                for p in de.panels_of(d, kind):
                    p["title"] = ""
            shell.edit(apply, node=shell.node)

        make = pn.widgets.Button(name="Titles from what each shows", button_type="light",
                                 button_style="outline", height=30, margin=(4, 4))
        clear = pn.widgets.Button(name="Clear the titles", button_type="light",
                                  button_style="outline", height=30, margin=(4, 4))
        make.on_click(on_titles)
        clear.on_click(on_clear)
        return [pn.Row(make, clear, margin=0)]

    # ------------------------------------------------------------ a panel's
    def place_objs(self, doc, pid):
        """What is at the end of a panel's settings: its annotations; where panel pid sits (its
        cell and how many it spans), a copy of it, removing it."""
        shell = self.shell
        rows, cols = de.grid_shape(doc)
        r, c, rs, cs = _cell(de.panel_by_id(doc, pid))
        row = pn.widgets.IntInput(name="Row", start=1, end=rows, value=r + 1)
        col = pn.widgets.IntInput(name="Column", start=1, end=cols, value=c + 1)
        tall = pn.widgets.IntInput(name="Rows tall", start=1, end=rows, value=rs)
        wide = pn.widgets.IntInput(name="Columns wide", start=1, end=cols, value=cs)
        said = pn.pane.HTML(margin=(2, 4), sizing_mode="stretch_width")
        now_kind = de.panel_by_id(doc, pid)["kind"]
        type_w = pn.widgets.Select(name="Panel type", options=kind_options(now_kind),
                                   value=now_kind,
                                   description="Change this panel to another type, in the same "
                                               "cell. What it showed is replaced; Undo takes it "
                                               "back.")
        type_w.param.watch(lambda ev: self.set_kind([pid], ev.new), "value")

        quiet = []  # (the boxes being set back)

        def on_place(ev):
            if quiet:
                return
            cell = [int(row.value or 1) - 1, int(col.value or 1) - 1, int(tall.value or 1),
                    int(wide.value or 1)]
            why = de.place_problem(shell.doc, pid, cell)
            if why:
                said.object = ('<div class="cv-status" style="color:#f87171">'
                               f'{html.escape(why)}</div>')
                now = _cell(de.panel_by_id(shell.doc, pid))
                quiet.append(1)
                row.value, col.value, tall.value, wide.value = now[0] + 1, now[1] + 1, now[2], now[3]
                quiet.clear()
                return
            shell.edit(lambda d: de.place_panel(d, pid, cell), node=shell.node)

        for w in (row, col, tall, wide):
            w.param.watch(on_place, "value")
        copy_btn = pn.widgets.Button(name="Copy this panel", button_type="light", height=30,
                                     button_style="outline", margin=(8, 4),
                                     description="Into the first free cell, or a new row or "
                                                 "column")
        copy_btn.on_click(lambda e: self.copy_panel(pid))
        rm = pn.widgets.Button(name="Remove this panel", button_type="light",
                               button_style="outline", height=30, margin=(8, 4),
                               disabled=len(doc["panels"]) < 2,
                               description="Its cell stays empty")
        kind = de.panel_by_id(doc, pid)["kind"]
        rm.on_click(lambda e: shell.edit(lambda d: de.remove_panel(d, pid),
                                         node=nodes.KIND_PREFIX + kind))
        bar = panel_bar_card(self.ins, doc, pid)
        return [*([bar] if bar is not None else []), self.ins.annots.card(doc, pid),
                pn.pane.HTML("<b>Place</b>", margin=(8, 4, 0, 4)),
                _grid((type_w, 2), row, col, tall, wide, n=2), said,
                pn.Row(copy_btn, rm, margin=0, sizing_mode="stretch_width")]

    def copy_panel(self, pid):
        made = []

        def apply(d):
            made.append(de.copy_panel(d, pid, de.next_cell(d)))
        self.shell.edit(apply)
        self.shell._show(f"panel:{made[0]['id']}")
        return made[0]
