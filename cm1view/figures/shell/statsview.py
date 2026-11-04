"""Distributions, profiles, joint distributions, azimuthal means and tables in the inspector: the
entry pane of soundings, each kind with its own card, look and what a new entry is.  A new entry
starts at the viewer's shown time in the viewer's run, and like the kind's last where the old
editor's does (an azimuthal mean's recipe, a table's whole card)."""

from .. import spec as fg
from ..cards import AzimCard, DistCard, JointCard, ProfileCard, ProfileDataCard, TableCard
from . import docedit as de
from .entryview import EntryPane, _button
from .gridview import own_run, shown_time
from .looks import Sections, dist_extra, joint_extra, rows_of
from .seriesview import new_recipe


def has_track(shell):
    return bool(shell.v.fixes) or any(r.get("track") for r in shell.doc["runs"])


def new_dist_recipe(shell):
    """w over the whole domain at 1 km."""
    F = shell.fields
    field = "winterp" if "winterp" in F else next(iter(F.defs))
    return dict(field=field, vmode="height", z=1.0, region="domain")


def new_joint_recipe(shell):
    """Vertical vorticity against w (the Distribution tool's last field and place, if it has any)
    over the whole domain at 1 km."""
    tool = list((getattr(shell.v, "dists", {}) or {}).values())
    r = dict(tool[-1]["recipe"]) if tool else new_dist_recipe(shell)
    r["yfield"] = "zvort" if "zvort" in shell.fields and r["field"] != "zvort" else r["field"]
    return r


def new_azim_recipe(shell):
    """w around the tracked storm, else around the middle of the map's view; the whole ring out to
    20 km, 0-15 km."""
    F = shell.fields
    field = "winterp" if "winterp" in F else next(
        (k for k, d in F.defs.items() if d.ndim == 3), next(iter(F.defs)))
    x0, x1, y0, y1 = (float(v) for v in shell.v.view)
    return dict(field=field, center="track" if has_track(shell) else "point",
                point=(0.5 * (x0 + x1), 0.5 * (y0 + y1)))


def profile_card(host, ent):
    """The card of a profile entry: computed, or your own data."""
    return ProfileDataCard(host, ent) if fg.is_table(ent) else ProfileCard(host, ent)


class StatsPane(EntryPane):
    tool = ""
    extras = staticmethod(dict)  # (what the look's settings show hangs on)
    redraws = ()  # (the look's settings that change which sections there are)

    def _looks(self, doc, scope):
        return Sections(self.ins, scope, [self.kind], self.extras(), redraws=self.redraws)

    def _shows(self, doc, scope, section):
        return True

    def _start(self):
        """(place of the run a new entry is of, its run's id, the shown time in that run)."""
        rid = own_run(self.shell)
        return de.run_index(self.shell.doc, rid), rid, shown_time(self.shell, rid)

    def _entry(self, e):
        """An entry as a card gives it (runs by place) as the document holds it."""
        e = de.from_card(self.shell.doc, de.plain(e))
        e.pop("panel", None)
        e["type"] = self.kind
        return e

    def _count(self):
        """How many the figure has."""
        return sum(len(p.get("layers") or []) for p in de.panels_of(self.shell.doc, self.kind))

    def _last(self):
        """The kind's last entry in reading order (None: it has none)."""
        for p in reversed(de.panels_of(self.shell.doc, self.kind)):
            if p.get("layers"):
                return de.plain(p["layers"][-1])
        return None

    def _tool_of(self, entries):
        """The old editor's lists of the viewer's tool, in the viewer's run."""
        rid = own_run(self.shell)
        out = []
        for e in entries:
            e = de.plain(e)
            e.pop("panel", None)
            e.update(type=self.kind, run=rid)
            if "runs" in e:
                e["runs"] = [rid]
            out.append(e)
        return out


class DistPane(StatsPane):
    kind = "dist"
    head, one = "Distributions", "Distribution"
    make_card = DistCard
    panel_note = "Distributions of one panel share its axes (colour = distribution)."
    tool = "+ The Distribution tool's"
    tool_tip = "A panel for each distribution computed with the viewer's Distribution tool"
    tool_none = "No distributions yet: compute one with the Distribution tool on the map first."
    extras = staticmethod(dist_extra)
    redraws = ("dist.plot",)

    def _shows(self, doc, scope, section):
        """A box plot or violin has no legend (its statistics go under the boxes)."""
        if section != "Legend in the panel":
            return True
        st = next(s for s in rows_of("Plot", [self.kind]) if s.key == "dist.plot")
        return scope.value(doc, st) not in ("box", "violin")

    def _new_entry(self):
        k, _, ts = self._start()
        return self._entry(fg.dist_defaults(new_dist_recipe(self.shell), k, ts, self._count()))

    def _tool_entries(self):
        return self._tool_of(self.shell.ed.tab_dists())


class ProfilePane(StatsPane):
    kind = "profile"
    head, one = "Profiles", "Profile"
    make_card = staticmethod(profile_card)
    panel_note = "Profiles of one panel share its axes (colour = profile)."
    tool = "+ The Series tool's"
    tool_tip = "A panel for each layer series of the viewer's Series tool, at the shown time"
    tool_none = "No layer series yet: make one with the Series tool (Vertical: Layer) first."

    def _new_entry(self):
        k, _, ts = self._start()
        return self._entry(fg.profile_defaults(new_recipe(self.shell), k, ts, self._count()))

    def _tool_entries(self):
        return self._tool_of(self.shell.ed.tab_profiles())

    def _more_tools(self, pid):
        return [_button("+ Your data", lambda: self.add_data(pid),
                        tip="A profile of your own (observations, another model): paste height "
                            "and value columns or load a CSV file")]

    def add_data(self, pid):
        """A profile of your own in the panel, open: to compare with what it has."""
        e = self._entry(fg.profile_table_defaults(self._count()))

        def apply(d):
            p = de.panel_by_id(d, pid)
            de.add_own(p, e)
            self.ins.folds[f"p:{pid}:own{len(de.places(d, p)) - 1}"] = True
        self.shell.edit(apply, node=self.shell.node)

    def _per_run(self, pid, j):
        return lambda: self.one_per_run(pid, j)

    def one_per_run(self, pid, j):
        """A profile of several runs split into one per run; of one, a copy for each other."""
        shell, doc = self.shell, self.shell.doc
        if len(doc["runs"]) < 2:
            shell.say("The figure has one run: add others first (Runs).", True)
            return
        trial = de.plain(doc)
        if not de.profile_per_run(trial, de.panel_by_id(trial, pid), j):
            shell.say("Each run has this profile in this panel already.", True)
            return
        shell.edit(lambda d: de.profile_per_run(d, de.panel_by_id(d, pid), j), node=shell.node)


class JointPane(StatsPane):
    kind = "joint"
    head, one = "Joint distributions", "Joint distribution"
    make_card = JointCard
    panel_note = "The first of a panel's joint distributions is shaded; the others draw over it."
    extras = staticmethod(joint_extra)

    def _new_entry(self):
        k, _, ts = self._start()
        return self._entry(fg.joint_defaults(new_joint_recipe(self.shell), k, ts, self._count()))


class AzimPane(StatsPane):
    kind = "azim"
    head, one = "Azimuthal means", "Azimuthal mean"
    make_card = AzimCard
    panel_note = "The first of a panel's azimuthal means is shaded; the others are contour lines."

    def _new_entry(self):
        k, _, ts = self._start()
        last = self._last()
        recipe = last["recipe"] if last else new_azim_recipe(self.shell)
        return self._entry(fg.azim_defaults(recipe, k, ts, self._count()))


class TablePane(StatsPane):
    kind = "table"
    head, one = "Values", "Values"
    make_card = TableCard
    panel_note = "The values of one panel make one table: add more for more columns."

    def _new_entry(self):
        """The kind's last, else sounding parameters at the tracked storm (no track: the domain
        mean) at the shown time."""
        last = self._last()
        if last:
            return last
        k, _, ts = self._start()
        where = dict(kind="trk" if has_track(self.shell) else "mean", x=0.0, y=0.0, avg=0.0)
        return self._entry(fg.tbl_defaults(new_dist_recipe(self.shell), k, ts, where))
