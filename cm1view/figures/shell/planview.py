"""Plan views in the inspector.  Where you click says what an edit reaches:

  All plan views   the shared layers and the kind's settings (a panel's own stay: it says so)
  a panel          its run, time, height, title, its layers (overrides, or of its own), its look
  a layer          that layer in that panel

and on the figure node, the tool that fills panels and the panel titles from what differs."""

import html

import panel as pn

from .. import draw as figdraw, spec as fg
from ..cards import GRID_DIMS, TYPE_LABEL, _grid
from ..cards.base import SECTION, _near
from ..draw.base import _cell
from ..times import _heights, _nearest_t, _tlabel
from . import docedit as de, nodes
from .layerrow import InPanel, LayerRow, Shared, describe, own_time_widgets
from .looks import KIND_SECTIONS, PANEL_KEYS, Scope, Sections, area_extra, panels_differ

ZMODES = {"km": "height", "Model level": "level"}


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


def _head(text):
    return pn.pane.HTML(f"<b>{html.escape(text)}</b>", margin=(8, 4, 0, 4))


def new_layer(shell, kind):
    """A new layer of a type, as the old editor starts one (a parcels one: the viewer's set
    not drawn yet; None if there is none)."""
    F = shell.fields
    field = None
    if kind in ("fill", "contour", "shade"):
        field = {"fill": "dbz", "contour": "winterp", "shade": "winterp"}[kind]
        if field not in F:
            field = next(iter(F.defs))
    lay = fg.layer_defaults(kind, F, field, 1.0)
    if kind == "parcels":
        doc = shell.doc
        have = {x.get("name") for x in (doc.get("layers") or {}).values()}
        sets = shell.ed._parcel_layers()
        if not sets:
            return None
        lay = next((x for x in sets if x["name"] not in have), sets[0])
    return lay


class PlanPane:
    def __init__(self, inspector):
        self.ins, self.shell = inspector, inspector.shell

    # ------------------------------------------------------------ shared by kind and panel
    def _add_menu(self, add, name="Add a layer"):
        """A menu of the types of layer; add(type)."""
        items = [(label, t) for t, label in TYPE_LABEL.items()
                 if t != "parcels" or self.shell.v.pf is not None]
        menu = pn.widgets.MenuButton(name=name, items=items, button_type="primary",
                                     button_style="outline", height=32, margin=(4, 4))
        menu.on_click(lambda ev: add(ev.new))
        return menu

    def _by_height(self, doc):
        return any(p.get("z") is not None for p in de.panels_of(doc, "plan"))

    # ------------------------------------------------------------ All plan views
    def kind_objs(self, doc, kind="plan"):
        mine = de.panels_of(doc, kind)
        names = nodes.letters(doc)
        ids = de.shared_ids(doc, kind)
        objs = [_note("Panels " + ", ".join(names[p["id"]] for p in mine)), _head("Layers"),
                _note("Drawn in this order, the last on top. Changes reach every panel, but what "
                      "a panel has set for itself."),
                self._add_menu(self.add_shared)]
        by_z = self._by_height(doc)
        for lid in ids:
            objs.append(LayerRow(
                self.ins, Shared(lid, kind), by_height=by_z,
                moves=dict(up=lambda i=lid: self._shared(de.move_shared, i, -1),
                           down=lambda i=lid: self._shared(de.move_shared, i, 1),
                           copy=lambda i=lid: self._copy_shared(i),
                           remove=lambda i=lid: self._shared(de.remove_shared, i)),
                extras=lambda row, i=lid: self._shared_extras(i), opened=lid == ids[0]).panel)
        if not ids:
            objs.append(_note("No shared layers: add one above."))
        own = [names[p["id"]] for p in mine if any("ref" not in x for x in p.get("layers") or [])]
        if own:
            objs.append(_note("Panel" + ("s " if len(own) > 1 else " ") + ", ".join(own)
                              + " also draw" + ("" if len(own) > 1 else "s")
                              + " layers of their own: see the panel."))
        looks = Sections(self.ins, Scope(kind), [kind], {
            "Area": area_extra(self.shell, Scope(kind))})
        objs += [c for c in (looks.card(s) for s in KIND_SECTIONS[kind]) if c is not None]
        differ = panels_differ(doc, kind, [k for keys in PANEL_KEYS[kind].values() for k in keys])
        if differ:
            objs.append(_note("Set in a panel alone, so changes here skip it: panel"
                              + ("s " if len(differ) > 1 else " ") + ", ".join(differ) + "."))
        return f"All {nodes.kind_name(kind, len(mine))}", objs

    def _shared(self, fn, lid, *args):
        self.shell.edit(lambda d: fn(d, "plan", lid, *args), node=self.shell.node)

    def _copy_shared(self, lid):
        made = []

        def apply(d):
            made.append(de.copy_shared(d, "plan", lid))
            self.ins.folds[f"s:{made[0]}"] = True  # (the copy: open, to change it)
        self.shell.edit(apply, node=self.shell.node)

    def add_shared(self, kind):
        """A new shared layer on top of every plan view, open."""
        lay = new_layer(self.shell, kind)
        if lay is None:
            self.shell.say("No parcel sets: make one in the viewer's Parcels tab.", True)
            return

        def apply(d):
            self.ins.folds[f"s:{de.add_shared(d, 'plan', lay)}"] = True
        self.shell.edit(apply, node=self.shell.node)

    def _shared_extras(self, lid):
        """Which panels draw a shared layer, and which of them have it otherwise."""
        doc, shell = self.shell.doc, self.shell
        names = nodes.letters(doc)
        mine = de.panels_of(doc, "plan")
        opts = {names[p["id"]]: p["id"] for p in mine}
        pick = pn.widgets.CheckButtonGroup(
            name="In panels", options=opts, value=[p["id"] for p in mine if de.draws(doc, p, lid)],
            button_type="light", button_style="outline", margin=(2, 4), height=28)

        def on_pick(ev):
            def apply(d):
                for p in de.panels_of(d, "plan"):
                    now = p["id"] in ev.new
                    if now != de.draws(d, p, lid):
                        de.in_panel(d, p, lid, now)
            shell.edit(apply)

        pick.param.watch(on_pick, "value")
        objs = [_note("Drawn in panels:"), pick]
        differ = de.differing(doc, lid, "plan")
        if differ:
            n = len(differ)
            back = pn.widgets.Button(name="↺ All as shared", height=26, margin=(2, 4),
                                     button_type="light", button_style="outline",
                                     description="No panel has this layer otherwise any more")
            back.on_click(lambda e: shell.edit(
                lambda d: de.clear_shared_over(d, lid, "plan"), node=shell.node))
            objs += [_note(f"{n} panel{'s differ' if n > 1 else ' differs'} ("
                           + ", ".join(names[i] for i in differ)
                           + "): what they set stays as it is when this changes."), back]
        return objs

    # ------------------------------------------------------------ a panel
    def panel_objs(self, doc, node):
        p = nodes.panel_of(doc, node)
        pid, letter = p["id"], nodes.letters(doc)[p["id"]]
        shell = self.shell

        def set_keys(**kw):
            def apply(d):
                q = de.panel_by_id(d, pid)
                for k, v in kw.items():
                    if v is None:
                        q.pop(k, None)
                    else:
                        q[k] = v
            shell.edit(apply)

        title = pn.widgets.TextInput(name="Title", value=p.get("title") or "",
                                     sizing_mode="stretch_width")
        title.param.watch(lambda ev: set_keys(title=ev.new.strip()), "value")
        rowlabel = pn.widgets.TextInput(name="Row label (left)", value=p.get("rowlabel") or "",
                                        placeholder="none")
        rowlabel.param.watch(lambda ev: set_keys(rowlabel=ev.new.strip() or None), "value")
        rname = nodes.run_names(doc)
        run_opts = {f"{k + 1}. {rname[r['id']]}": r["id"] for k, r in enumerate(doc["runs"])}
        run = pn.widgets.Select(name="Run", options=run_opts,
                                value=p.get("run") if p.get("run") in run_opts.values()
                                else doc["runs"][0]["id"])
        time = pn.widgets.Select(name="Time", options=self._times(p.get("run"), p.get("time_s")),
                                 value=None if p.get("time_s") is None else float(p["time_s"]))

        def on_run(ev):
            ts = de._moved(shell.doc, time.value, ev.old, ev.new) if time.value is not None \
                else None
            tl = list(shell.time_opts(de.run_index(shell.doc, ev.new)).values())
            if ts is not None and tl:
                ts = _nearest_t(tl, ts)
            shell.edit(lambda d: de.panel_by_id(d, pid).update(run=ev.new, time_s=ts),
                       node=shell.node)

        run.param.watch(on_run, "value")
        time.param.watch(lambda ev: set_keys(time_s=float(ev.new)), "value")
        z = pn.widgets.TextInput(
            name="Own height (blank: its layers')",
            value="" if p.get("z") is None else f"{float(p['z']):g}", placeholder="e.g. 1",
            description="The layers at a height draw at this one here, and the panel's height "
                        "label says it")
        zmode = pn.widgets.Select(name="Height in", options=ZMODES,
                                  value=p.get("zmode", "height"))

        def on_z(*ev):
            txt = z.value.strip()
            try:
                val = float(txt) if txt else None
            except ValueError:
                shell.say(f"Height of panel {letter}: “{html.escape(txt)}” is not a number", True)
                return
            shell.edit(lambda d: de.set_height(d, de.panel_by_id(d, pid), val, zmode.value),
                       node=shell.node)

        z.param.watch(on_z, "value")
        zmode.param.watch(on_z, "value")
        objs = [title, _grid(run, time, z, zmode, rowlabel, n=2)]
        secs = doc.get("sections") or {}
        if len(secs) > 1:
            sopts = {f"{k + 1}: {s.get('label') or fg.describe(s)}": sid
                     for k, (sid, s) in enumerate(secs.items())}
            sec = pn.widgets.Select(name="Its section line", options=sopts,
                                    value=p.get("section") if p.get("section") in secs else
                                    next(iter(secs)), sizing_mode="stretch_width")
            sec.param.watch(lambda ev: set_keys(section=ev.new), "value")
            objs.append(sec)
        r, c, rs, cs = _cell(p)
        objs.append(_note(f"Row {r + 1}, column {c + 1}"
                          + (f", {rs} × {cs} cells" if (rs, cs) != (1, 1) else "")
                          + ". The figure's Fill panels tool sets rows and columns."))
        objs += [_head("Layers"),
                 _note("Changes here are for this panel alone; a shared layer's other settings "
                       "follow All plan views.")]
        objs.append(self._add_menu(lambda t: self.add_own(pid, t), "Add a layer to this panel"))
        lays = figdraw.panel_layers(doc, p)
        for j, _ in enumerate(lays):
            objs.append(self._panel_row(doc, pid, j, len(lays)).panel)
        if not lays:
            objs.append(_note("No layers here: add one above."))
        objs += self._panel_looks(doc, pid)
        rm = pn.widgets.Button(name="Remove this panel", button_type="light",
                               button_style="outline", height=30, margin=(8, 4),
                               disabled=len(doc["panels"]) < 2,
                               description="Its cell stays empty; the Fill panels tool can fill "
                                           "it again")
        rm.on_click(lambda e: shell.edit(
            lambda d: d.update(panels=[q for q in d["panels"] if q["id"] != pid]),
            node=nodes.KIND_PREFIX + "plan"))
        objs.append(rm)
        return f"Panel {letter}", objs

    def _times(self, rid, now):
        """A panel's Time list: its run's outputs, and the time it has if that is none of
        them."""
        doc, shell = self.shell.doc, self.shell
        opts = dict(shell.time_opts(de.run_index(doc, rid)))
        if now is not None and not any(abs(float(now) - t) <= 0.0 for t in opts.values()):
            opts[_tlabel(now) + " · no output"] = float(now)
        return opts

    def _panel_row(self, doc, pid, j, n):
        """Layer j of a panel, in the panel's list."""
        shell = self.shell

        def step(fn, *args):
            shell.edit(lambda d: fn(d, de.panel_by_id(d, pid), j, *args), node=shell.node)

        moves = {}
        if j > 0:
            moves["up"] = lambda: step(de.move_in_panel, -1)
        if j < n - 1:
            moves["down"] = lambda: step(de.move_in_panel, 1)
        moves["copy"] = lambda: step(de.copy_in_panel)
        moves["remove"] = lambda: step(de.remove_in_panel)
        return LayerRow(self.ins, InPanel(doc, pid, j), moves=moves,
                        by_height=de.panel_by_id(doc, pid).get("z") is not None,
                        extras=own_time_widgets, opened=n == 1)

    def add_own(self, pid, kind):
        """A layer of this panel alone, on top, open."""
        lay = new_layer(self.shell, kind)
        if lay is None:
            self.shell.say("No parcel sets: make one in the viewer's Parcels tab.", True)
            return

        def apply(d):
            p = de.panel_by_id(d, pid)
            de.add_own(p, lay)
            j = len(de.places(d, p)) - 1
            self.ins.folds[f"p:{pid}:own{j}"] = True
            de.apply_heights(d, [p])
        self.shell.edit(apply, node=self.shell.node)

    def _panel_looks(self, doc, pid):
        """The panel's own look: what it inherits, each setting to change here."""
        scope = Scope("plan", pid)
        looks = Sections(self.ins, scope, ["plan"])
        objs = []
        for section, keys in PANEL_KEYS["plan"].items():
            card = looks.card(section, only=keys)
            if card is not None:
                objs += looks.chips(keys)
                objs.append(card)
        return objs

    # ------------------------------------------------------------ a layer of a panel
    def layer_objs(self, doc, node):
        p = nodes.panel_of(doc, node)
        j = int(node.rsplit(":", 1)[1])
        target = InPanel(doc, p["id"], j)
        letter = nodes.letters(doc)[p["id"]]
        row = LayerRow(self.ins, target, fixed=True, by_height=p.get("z") is not None,
                       extras=own_time_widgets)
        objs = [row.panel]
        if target.ref is not None:
            objs.insert(0, _note("A shared layer, as panel " + letter + " draws it: what is set "
                                 "here stays here. <b>All plan views</b> sets it for all."))
        else:
            objs.insert(0, _note(f"A layer of panel {letter} alone."))
        name = describe(target.layer(doc), self.shell.fields)
        return f"{name} in panel {letter}", objs

    # ------------------------------------------------------------ fill panels (figure)
    def fill_card(self, doc):
        """The Fill panels tool, in a section: its widgets are made when it is opened."""
        folds = self.ins.folds
        card = pn.Card(title="Fill panels", collapsed=True, **SECTION)

        def on_fold(ev):
            folds["fill"] = not ev.new
            if not ev.new and not card.objects:
                card.objects = self.fill_objs()

        card.param.watch(on_fold, "collapsed")
        if folds.get("fill"):
            card.collapsed = False
        return card

    def fill_objs(self):
        """Rows, columns, what each steps through, and its list.  Run once: it writes ordinary
        panels, which can be changed one by one; run it again to change them all."""
        shell, doc = self.shell, self.shell.doc
        was = de.guess_fill(doc)
        rname = nodes.run_names(doc)
        run_opts = {f"{k + 1}. {rname[r['id']]}": r["id"] for k, r in enumerate(doc["runs"])}
        dims = {k: v for k, v in GRID_DIMS.items()
                if v != "sections" or len(doc.get("sections") or {}) > 1}
        rows = pn.widgets.IntInput(name="Rows", start=1, end=12, value=was["rows"])
        cols = pn.widgets.IntInput(name="Columns", start=1, end=12, value=was["cols"])
        row_dim = pn.widgets.Select(name="Rows are", options=dims, value=was["row_dim"])
        col_dim = pn.widgets.Select(name="Columns are", options=dims, value=was["col_dim"])
        run = pn.widgets.Select(name="Run", options=run_opts,
                                value=was["runs"][0] if was["runs"] else doc["runs"][0]["id"])
        runs = pn.widgets.MultiChoice(name="Runs (blank: all)", options=run_opts,
                                      value=was["runs"] if len(was["runs"]) > 1 else [])
        time = pn.widgets.Select(name="Time", options=shell.time_opts(0))
        every = pn.widgets.IntInput(name="Every nth output", start=1, end=100,
                                    value=self._every(was, run.value))
        heights = pn.widgets.TextInput(name="Heights (e.g. 1, 3, 6 or 1:6:1)", value=", ".join(
            f"{z:g}" for z in was["heights"]) or "1, 3, 6")
        zmode = pn.widgets.Select(name="Heights in", options=ZMODES, value=was["zmode"])
        names = {f"{shell.fields[f].label} [{f}]": f for f in shell.fields.defs}
        fields = pn.widgets.MultiChoice(name="Fields (each panel's fill)", options=names,
                                        value=[f for f in was["fields"] if f in names.values()])
        go = pn.widgets.Button(name="Fill the panels", button_type="primary", height=32,
                               margin=(6, 4))
        note = pn.pane.HTML(margin=(2, 4), sizing_mode="stretch_width")
        titles = pn.widgets.Button(name="Titles from what differs", button_type="light",
                                   button_style="outline", height=30, margin=(6, 4))
        clear = pn.widgets.Button(name="Clear the titles", button_type="light",
                                  button_style="outline", height=30, margin=(6, 4))

        def used():
            return [d for d in (row_dim.value, col_dim.value) if d != "none"]

        def first_run():
            return (runs.value or list(run_opts.values()))[0] if "runs" in used() else run.value

        def show(*ev):
            on = used()
            run.visible = "runs" not in on
            runs.visible = "runs" in on
            heights.visible = zmode.visible = "heights" in on
            fields.visible = "fields" in on
            every.visible = "times" in on
            time.name = "First time" if "times" in on else "Time"
            opts = shell.time_opts(de.run_index(shell.doc, first_run()))
            cur = time.value
            time.options = opts
            if opts:
                time.value = opts[next(iter(opts))] if cur is None else _near(opts, cur)

        def steps_of(d):
            """The list of one dimension, as long as it can be used."""
            nr, nc = int(rows.value or 1), int(cols.value or 1)
            n = nc if d == col_dim.value and row_dim.value != "none" else \
                nr if d == row_dim.value and col_dim.value != "none" else nr * nc
            if d == "times":
                tl = list(shell.time_opts(de.run_index(shell.doc, first_run())).values())
                at = tl.index(_nearest_t(tl, time.value))
                step = int(every.value or 1)
                return [tl[at + step * k] if at + step * k < len(tl) else None for k in range(n)]
            if d == "runs":
                return list(runs.value) or [r["id"] for r in shell.doc["runs"]]
            if d == "heights":
                return _heights(heights.value)
            if d == "fields":
                return [fg.layer_defaults("fill", shell.fields, f, 1.0) for f in fields.value]
            return list(shell.doc.get("sections") or {})

        def on_go(e):
            nr, nc = int(rows.value or 1), int(cols.value or 1)
            why = de.fill_problem(shell.doc, nr, nc)
            if not why and row_dim.value == col_dim.value != "none":
                why = "Rows and columns can't step through the same thing."
            if why:
                note.object = f'<div class="cv-status" style="color:#f87171">{why}</div>'
                return
            try:
                steps = {d: steps_of(d) for d in used()}
            except ValueError as err:
                note.object = ('<div class="cv-status" style="color:#f87171">'
                               f'{html.escape(str(err))}</div>')
                return
            done = []

            def apply(d):
                done.append(de.fill_panels(
                    d, nr, nc, row_dim.value, col_dim.value, steps, run=first_run(),
                    time_s=None if "times" in steps else time.value, zmode=zmode.value))
                _fields_colorbar(d, row_dim.value, col_dim.value)
                if len(used()) == 2 and not any(p.get("title") for p in de.panels_of(d, "plan")):
                    de.auto_titles(d, shell.fields)  # (rows and columns, named)
            shell.edit(apply, node=nodes.FIGURE)
            made, gone = done[0]
            self.ins.fill_said = f"{made} panel{'s' if made != 1 else ''} filled" + (
                f"; {gone} no longer on the grid (Undo brings them back)." if gone else ".")
            self.ins.show(nodes.FIGURE)

        def on_titles(e):
            shell.edit(lambda d: de.auto_titles(d, shell.fields), node=nodes.FIGURE)

        def on_clear(e):
            def apply(d):
                for p in de.panels_of(d, "plan"):
                    p["title"] = ""
                    p.pop("rowlabel", None)
            shell.edit(apply, node=nodes.FIGURE)

        for w in (row_dim, col_dim, run, runs):
            w.param.watch(show, "value")
        go.on_click(on_go)
        titles.on_click(on_titles)
        clear.on_click(on_clear)
        show()
        if was["times"]:
            time.value = _near(time.options, was["times"][0])
        said = getattr(self.ins, "fill_said", "")
        self.ins.fill_said = ""
        note.object = f'<div class="cv-hint">{html.escape(said)}</div>' if said else ""
        self.widgets = dict(rows=rows, cols=cols, row_dim=row_dim, col_dim=col_dim, run=run,
                            runs=runs, time=time, every=every, heights=heights, zmode=zmode,
                            fields=fields, go=go)
        return [
            _note("Writes the panels once; no rule is kept. Run it again to change them all: "
                  "it replaces runs and times set by hand, layers stay."),
            _grid(rows, cols, row_dim, col_dim, run, (runs, 2), time, every, heights, zmode,
                  (fields, 2), n=2),
            go, note, pn.Row(titles, clear, margin=0)]

    def _every(self, was, rid):
        """The step between the panels' times, in outputs of a run."""
        ts = was["times"]
        if len(ts) < 2:
            return 1
        tl = list(self.shell.time_opts(de.run_index(self.shell.doc, rid)).values())
        if not tl:
            return 1
        a, b = tl.index(_nearest_t(tl, ts[0])), tl.index(_nearest_t(tl, ts[1]))
        return max(1, b - a)


def _fields_colorbar(doc, row_dim, col_dim):
    """Panels of different fields can't share one colorbar: one per row, column or panel, as
    the old layout's grid of fields did."""
    if "fields" not in (row_dim, col_dim):
        return
    style = doc.setdefault("style", {})
    cb = style.get("colorbar") or {}
    if cb.get("mode", "shared") == "shared":
        mode = "row" if row_dim == "fields" and col_dim != "none" else \
            "col" if col_dim == "fields" and row_dim != "none" else "each"
        style["colorbar"] = dict(cb, mode=mode)
