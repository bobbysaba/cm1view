"""Time series and time-height panels in the inspector: the entry pane of soundings, with series
for entries.  A time series panel draws any number: computed series (of one run, several or every
run), your own data, parcel series.  A time-height panel shows one, of one run (the panel's)."""

import panel as pn

from ...core import series as ser
from .. import spec as fg
from ..cards import DataCard, ParcelSeriesCard, SeriesCard
from ..kinds import KINDS
from . import docedit as de
from .entryview import EntryPane, _button, _note
from .gridview import own_run
from .looks import Sections


def series_card(host, ent):
    """The card of a series entry, by what it draws."""
    cls = DataCard if fg.is_table(ent) else ParcelSeriesCard if fg.is_parcels(ent) else SeriesCard
    return cls(host, ent)


def new_recipe(shell):
    """A new series' recipe: max w in 0–10 km near the storm (the whole domain without a track),
    as for updraft time-height plots."""
    F = shell.fields
    field = "winterp" if "winterp" in F else next(iter(F.defs))
    track = bool(shell.v.fixes) or any(r.get("track") for r in shell.doc["runs"])
    return ser.normalize(dict(field=field, vmode="layer", z0=0.0, z1=10.0,
                              region="track" if track else "domain", radius=5.0,
                              offset=(0.0, 0.0), reduce="max"))


class SeriesPane(EntryPane):
    head = "Series"
    make_card = staticmethod(series_card)

    def __init__(self, inspector, kind):
        super().__init__(inspector)
        self.kind = kind

    def first_entries(self):
        """None: nothing is computed until one is added."""
        return []

    # ------------------------------------------------------------ what a section shows
    def _looks(self, doc, scope):
        return Sections(self.ins, scope, [self.kind])

    def _shows(self, doc, scope, section):
        return True

    # ------------------------------------------------------------ all of the kind
    def _kind_tools(self):
        return [pn.Row(_button(f"+ {KINDS[self.kind].head or 'Time–height'} panel", self.add_panel,
                               primary=True, tip="In the first free cell, or a new row or column: "
                                                 "nothing is computed until it has a series"),
                       margin=0), *self.ins.grid.titles_objs(self.kind)]

    # ------------------------------------------------------------ a panel
    def _from_tool(self, pid):
        """A menu of the Series tool's series, when it has any."""
        have = getattr(self.shell.v, "series", {}) or {}
        if not have:
            return []
        menu = pn.widgets.MenuButton(name="+ From the Series tool", button_type="light",
                                     button_style="outline", height=32, margin=(4, 4),
                                     items=[(s["label"], key) for key, s in have.items()])
        menu.on_click(lambda ev: self.add_from_tool(pid, ev.new))
        return [menu]

    def _panel_tools(self, doc, p):
        pid = p["id"]
        lays = de.places(doc, p)
        if self.kind == "th":
            if not lays:
                return [_note("One series, of one run. Nothing is computed until there is one."),
                        pn.Row(_button("+ Series", lambda: self.add_entry(pid), primary=True),
                               *self._from_tool(pid), margin=0)]
            more = " Only the first is drawn." if len(lays) > 1 else ""
            return [_note("A time-height panel shows one series: <b>Copy this panel</b> for "
                          f"another.{more}")]
        v = self.shell.v
        tools = [_button("+ Series", lambda: self.add_entry(pid), primary=True),
                 _button("+ Your data", lambda: self.add_data(pid),
                         tip="A series of your own (observations, another model): paste time and "
                             "value columns or load a CSV file")]
        if v.pf is not None:
            tools.append(_button("+ Parcels", lambda: self.add_parcels(pid),
                                 tip="A variable of a parcel set over the parcel times: its mean "
                                     "or median, a band, and parcels' own lines"))
            if v.pf.has_budget():
                budget = pn.widgets.MenuButton(
                    name="+ w budget", button_type="light", button_style="outline", height=32,
                    margin=(4, 4), items=[("Rates: Dw/Dt, b, vpg, the rest", "rates"), (
                        "Integrated since the set's time: Δw, ∫b, ∫vpg, ∫rest", "int")])
                budget.on_click(lambda ev: self.add_budget(pid, ev.new))
                tools.append(budget)
        objs = [_note("Series of one panel share its axes; other units get their own axis."),
                pn.FlexBox(*tools, *self._from_tool(pid), sizing_mode="stretch_width")]
        if not lays:
            objs.append(_note("No series here: add one above. Nothing is computed until then."))
        return objs

    def _add(self, pid, new):
        """Entries into a panel, the last open."""
        def apply(d):
            p = de.panel_by_id(d, pid)
            for e in new:
                de.add_series(p, de.plain(e))
            self.ins.folds[f"p:{pid}:own{len(de.places(d, p)) - 1}"] = True
        self.shell.edit(apply, node=self.shell.node)

    def _count(self):
        """How many series the figure has (a new one's colour goes by it)."""
        return sum(len(p.get("layers") or []) for p in de.panels_of(self.shell.doc, "line"))

    def _entry(self, recipe):
        """A new series of a recipe: of every run; time-height: of the viewer's run."""
        e = fg.series_defaults(self.shell.fields, recipe, self._count())
        e.pop("panel", None)
        e["type"] = "series"
        if self.kind == "th":
            e.update(on=True, runs=[own_run(self.shell)])
        return e

    def add_entry(self, pid):
        self._add(pid, [self._entry(new_recipe(self.shell))])

    def add_from_tool(self, pid, key):
        self._add(pid, [self._entry(dict(self.shell.v.series[key]["recipe"]))])

    def add_data(self, pid):
        e = fg.table_defaults(self._count())
        e.pop("panel", None)
        self._add(pid, [dict(e, type="series")])

    def _parcel_source(self):
        have = {x.get("name") for p in de.panels_of(self.shell.doc, "line")
                for x in p.get("layers") or [] if fg.is_parcels(x)}
        src = self.shell.ed._parcel_series_source(have)
        if src is None:
            self.shell.say("No parcel set yet: choose some in the viewer's <b>Parcels</b> tab "
                           "first.", True)
        return src

    def add_parcels(self, pid):
        v = self.shell.v
        src = self._parcel_source()
        if src is None:
            return
        var = "w" if "w" in v.pf.vars else next(n for n in v.pf.vars if n != "mtime")
        e = fg.parcel_series_defaults(src, var, v.pf.units(var), 0, self._count())
        e.pop("panel", None)
        self._add(pid, [dict(e, type="series", runs=[own_run(self.shell)])])

    def add_budget(self, pid, how):
        """The w budget of the next parcel set, a series per term, in this panel."""
        v = self.shell.v
        src = self._parcel_source()
        if src is None:
            return
        out = []
        for e in fg.w_budget_entries(v.pf, src, how, 0, 0):
            e.pop("panel", None)
            out.append(dict(e, type="series", runs=[own_run(self.shell)]))
        self._add(pid, out)

    # ------------------------------------------------------------ one series
    def _moves(self, pid, j, n):
        moves = super()._moves(pid, j, n)
        if self.kind == "th":  # (a second one there isn't drawn)
            moves.pop("copy", None)
        return moves

    def _panel_pick(self, row):
        return [] if self.kind == "th" else super()._panel_pick(row)

    def _per_run(self, pid, j):
        return (lambda: self.one_per_run(pid, j)) if self.kind == "line" else \
            (lambda: self.one_panel_per_run(pid))

    def one_per_run(self, pid, j):
        """A series of several runs split into one per run; of one, a copy for each other."""
        shell, doc = self.shell, self.shell.doc
        if len(doc["runs"]) < 2:
            shell.say("The figure has one run: add others first (Runs).", True)
            return
        if not de.series_per_run(de.plain(doc), de.panel_by_id(de.plain(doc), pid), j):
            shell.say("Every run has this series already.", True)
            return
        shell.edit(lambda d: de.series_per_run(d, de.panel_by_id(d, pid), j), node=shell.node)

    def one_panel_per_run(self, pid):
        shell, doc = self.shell, self.shell.doc
        if len(doc["runs"]) < 2:
            shell.say("The figure has one run: add others first (Runs).", True)
            return
        if not de.panel_per_run(de.plain(doc), pid):
            shell.say("Every run has this series already.", True)
            return
        shell.edit(lambda d: de.panel_per_run(d, pid), node=shell.node)
