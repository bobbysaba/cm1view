"""The cards of one series of a time-height / time-series figure and of one
sounding of a sounding figure."""

import html
import os

import panel as pn

from ...core import series as ser
from ...core.fields import deriv_name
from .. import spec as fg
from .base import (
    _auto, _chk, _f, _grid, _hex, _hint, _fold, _retired, SER_OPS, SND_WHERE, _deriv_pair, TimeCard,
    _take_new_runs, LINE_STYLES, card_buttons, color_widgets, ens_values, ens_widgets, keep_box, known_cmap,
    label_widget, look_values, look_widgets, panel_index, panel_tag, panel_widget, reduce_recipe,
    reduce_widgets, region_recipe, region_widgets, show_ens, show_region, vertical_recipe,
    vertical_widgets, where_grid,
)
from .seriesvals import SeriesValues
from ...viewer.ui import held

SER_VMODES = {"Layer (every level)": "layer", "At a height": "height"}
ALL_RUNS, SOME_RUNS = -1, -2  # (a time series' Run list: every run / the runs picked)


def several_run_choices(ed, names=None):
    """A Run list's choices with every run and the runs picked: the figure's runs,
    All runs, Several runs…, and the others (picking one adds it)."""
    names = names or ed._run_names()
    more = {"All runs": ALL_RUNS, "Several runs…": SOME_RUNS}
    ch = ed._run_choices(names)
    if ch["groups"]:
        return dict(options={}, groups={"In this figure": names, "Several": more,
                                        **{k: v for k, v in ch["groups"].items()
                                           if k != "In this figure"}})
    return dict(groups=None, options=names | more)


class SeveralRuns:
    """The Run list of a card that may show one run, every run or the runs picked (Runs
    box): a series card (but a time-height one: one run) and a profile card.  After a
    change: _run_picked() (the Run list), _runs_picked() (the Runs box), _reshow()."""
    _EDITS = "series before its recipe or Then apply changed"  # (what edits_changed says)

    def _several(self):
        return True

    def _run_choices(self, names=None):
        return several_run_choices(self.ed, names)

    def _run_values(self):
        o = self.w["run"].groups or {"": self.w["run"].options}
        return [v for g in o.values() for v in (g.values() if isinstance(g, dict) else g)]

    def run_list(self):
        """The card's runs: None for every run, else a list of run indices."""
        k = self.w["run"].value
        if self._several() and k == ALL_RUNS:
            return None
        if self._several() and k == SOME_RUNS:
            return sorted(int(j) for j in self.w["runs"].value if not isinstance(j, str)) \
                or None
        return [int(k)] if isinstance(k, int) and k >= 0 else [0]

    def set_runs(self, runs):
        """Show runs (None: every run; a card of one run: the first)."""
        w = self.w
        with held(self.ed):
            if runs is not None and len(runs) == 1 or not self._several():
                w["runs"].value = []
                w["run"].value = int((runs or [0])[0])
            elif runs is None:
                w["runs"].value = []
                w["run"].value = ALL_RUNS
            else:
                w["runs"].value = sorted(int(k) for k in runs)
                w["run"].value = SOME_RUNS
        self._reshow()

    def refresh_runs(self, names=None):
        """The run lists' choices again (runs renamed, added or removed, or another
        kind of figure), keeping the card's runs."""
        names = names or self.ed._run_names()
        keep = self.run_list()
        with held(self.ed):
            self.w["runs"].options = self.ed._series_run_opts(names)
            self.w["run"].param.update(**self._run_choices(names))
        self.set_runs([k for k in keep if k in names.values()] or [0]
                      if keep is not None else None)

    def _on_run(self, ev):
        if self.ed._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
            return
        if ev.new == SOME_RUNS and not self.w["runs"].value:  # (from every run)
            with held(self.ed):
                self.w["runs"].value = sorted(self.ed._run_names().values())
        self._run_picked()

    def _on_runs(self, ev):
        """A run not in the figure picked (its path): add it to the figure, and keep
        it picked here."""
        if self.ed._hold:
            return
        _take_new_runs(self.ed, self.w["runs"], ev.new)
        self._runs_picked()

    def _edits_stale(self):
        """What the values are of changed: hand edits (made on the values before) are
        kept, with a word on the card."""
        self._stale = bool(self.vals.count())
        self.edits_changed()
        self.vals.refresh()

    def edits_changed(self):
        n = self.vals.count()
        self._stale = getattr(self, "_stale", False) and bool(n)
        self.info.object = (
            f'<div class="cv-hint">{n} hand edit{"s" if n != 1 else ""} made on this '
            f'{self._EDITS} are still drawn: check them under Values (Reset all edits '
            f'clears them).</div>' if self._stale else "")


class SeriesCard(SeveralRuns):
    """One series of a time-height / time-series figure, like a sounding card: its
    run (a time series: also every run, or the runs picked), panel, a Series-tab
    recipe (field, level or layer, region, reduction), an optional derivative, and its
    look.  A time-height card is one panel (its run's series)."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.w = w = {}
        card_buttons(self, "Remove the series", moves=True, dup=True, per_run=(
            "Time series: a card for each run (this card's runs, or each "
            "other run of the figure) in this panel; time-height: a copy for "
            "each other run, down this card's column (a row per run)"))
        self._kind = ed.kind.value
        runs = ent.get("runs")
        k = (ALL_RUNS if self._kind != "th" else 0) if runs is None else \
            int(runs[0]) if len(runs) == 1 else SOME_RUNS
        w["run"] = pn.widgets.Select(name="Run", width=170, **self._run_choices())
        w["run"].value = k if k in self._run_values() else 0
        w["field"], w["deriv"] = _deriv_pair(F, r["field"])
        vertical_widgets(w, r, SER_VMODES, "layer")
        region_widgets(self, r)
        reduce_widgets(w, r)
        w["op"] = pn.widgets.Select(
            name="Then apply", options=SER_OPS, value=ent.get("op", ""), width=130,
            description="Applied to this series once computed (a Derivative is taken of "
                        "the field before the reduction)")
        w["label"] = label_widget(ent)
        color_widgets(w, ent)  # (time-height)
        look_widgets(w, ent, ls=LINE_STYLES, lw=1.5, marker=True, axis=True)  # (time series)
        w["t0"] = _retired(_f(
            "Time zero (min)", float(ent.get("t0_min") or 0.0), 110, step=1.0,
            description="From an older figure: adds to its run's time zero (on the Runs "
                        "node), which is the place to set it. At 0 this box goes away"))
        w["panel"] = panel_widget(ent)
        w["runs"] = pn.widgets.MultiChoice(name="Runs", options=ed._series_run_opts(),
                                           value=[int(k) for k in (runs or [])]
                                           if k == SOME_RUNS else [], width=260)
        ens_widgets(w, ent)
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self.info = pn.pane.HTML(margin=(0, 4))
        recipe_keys = ("vmode", "z", "z0", "z1", "region", "radius", "offx", "offy", "reduce",
                       "pct")
        for k in recipe_keys:
            w[k].param.watch(lambda e: self._changed(), "value")
        for k, x in w.items():
            if k not in recipe_keys and k not in ("field", "deriv", "panel", "run", "runs"):
                x.param.watch(lambda e: ed.request(), "value")
        w["panel"].param.watch(lambda e: self._where_changed(), "value")
        w["run"].param.watch(self._on_run, "value")
        w["runs"].param.watch(self._on_runs, "value")
        w["field"].param.watch(self._on_field, "value")
        w["deriv"].param.watch(self._on_field, "value")
        w["op"].param.watch(lambda e: self._op_changed(), "value")
        w["ens"].param.watch(lambda e: self.show(ed.kind.value), "value")
        self.th_row = _grid(w["cmap"], w["reverse"], w["white_first"], w["vmin"], w["vmax"],
                            w["nlevels"], w["extend"], (w["cbar_label"], 2), w["cbar_ticks"])
        self.line_row = _grid(w["color"], w["ls"], w["lw"], w["marker"], w["axis"], w["ylabel"],
                              w["ens"], w["ens_mid"], w["ens_members"], w["ens_alpha"])
        self.trk_note = pn.pane.HTML(margin=(0, 4), sizing_mode="stretch_width")
        self.vals = SeriesValues(self)  # (time series: its values, and your edits of them)
        self.where = where_grid(self, w["run"], (w["runs"], 2), w["t0"])
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.up, self.down, self.rm],
            [self.where,
             _grid((w["field"], 2), w["deriv"], w["vmode"], w["z"], w["z0"], w["z1"],
                   w["region"], w["radius"], w["offx"], w["offy"], w["reduce"], w["pct"],
                   w["op"], (w["label"], 3)), self.trk_note, self.th_row, self.line_row,
             self.vals.section, self.info])
        self._set_title()
        self.show(ed.kind.value)

    def show(self, kind):
        if kind != self._kind:  # (every run / the runs picked: time series only)
            self._kind = kind
            self.refresh_runs()
        w, two = self.w, self.ed.fields[self.field_name()].ndim == 2
        th = kind == "th"  # (time-height: always every level of the layer)
        lay = th or w["vmode"].value == "layer"
        w["vmode"].visible = not two and not th
        w["z"].visible = not two and not lay
        w["z0"].visible = w["z1"].visible = not two and lay
        show_region(w)
        w["pct"].visible = w["reduce"].value == "pct"
        self.th_row.visible = kind == "th"
        self.line_row.visible = self.vals.section.visible = kind == "line"
        w["runs"].visible = kind == "line" and w["run"].value == SOME_RUNS
        show_ens(w, kind == "line" and w["run"].value in (ALL_RUNS, SOME_RUNS))
        self.refresh_tracks()
        self._set_title()

    def refresh_tracks(self):
        """Around the tracked storm: what the track of each of the card's runs gives (they
        are set on the Runs node)."""
        rows = getattr(self.ed, "run_rows", [])
        self.trk_note.visible = self.w["region"].value == "track" and bool(rows)
        if not self.trk_note.visible:
            self.trk_note.object = ""
            return
        ks = self.run_list()
        ks = [k for k in (range(len(rows)) if ks is None else ks) if k < len(rows)]
        notes = [f"{html.escape(os.path.basename(rows[k]['path'].rstrip('/')))}: "
                 f"{self.ed._track_note(rows[k])}" for k in ks]
        self.trk_note.object = (f'<div class="cv-hint">{"; ".join(notes)}. Set a run\'s track '
                                'on the <b>Runs</b> node.</div>')

    # ---- run
    def _several(self):  # (a time-height card: one run)
        return self._kind != "th"

    def _run_choices(self, names=None):
        """The Run list's choices: the figure's runs (a time series: then every run, or
        the runs picked), and the others (picking one adds it)."""
        if self._kind == "th":
            return self.ed._run_choices(names)
        return several_run_choices(self.ed, names)

    def _reshow(self):
        self.show(self._kind)

    def _run_picked(self):
        self._where_changed()

    def _runs_picked(self):
        self.ed._series_changed()

    def _where_changed(self):
        self.show(self.ed.kind.value)
        self.ed._series_changed()
        self.vals.refresh()

    def _set_title(self):
        w = self.w
        d = self.ed.fields[self.field_name()]
        op = {"ddz": " · d/dz", "ddt": " · d/dt"}.get(w["op"].value, "")
        runs = self.run_list()
        names = {k: n.split(". ", 1)[-1] for n, k in self.ed._run_names().items()}
        run = "every run" if runs is None else names.get(runs[0], "") if len(runs) == 1 \
            else f"{len(runs)} runs"
        self.title.object = (f"<b>Series</b> · {d.label}{op} · {run} · "
                             f"panel {panel_tag(w)}")

    def _changed(self):
        keep_box(self)
        self.show(self.ed.kind.value)
        self._auto_label()
        self._edits_stale()
        self.ed.request()

    def _op_changed(self):
        self._set_title()
        self._edits_stale()

    def _auto_label(self):
        """Keep an automatic label in step with the recipe (an edited one stays)."""
        old = self.ent.get("_auto", self.ent.get("label", ""))
        d = self.ed.fields[self.field_name()]
        new = ser.describe(self.recipe(), d.label)
        if self.w["label"].value in ("", old):
            with held(self.ed):
                self.w["label"].value = new
        self.ent["_auto"] = new

    def _on_field(self, ev):
        """New field: its colours and range."""
        e = fg.series_defaults(self.ed.fields, self.recipe())
        with held(self.ed):
            for k in ("vmin", "vmax", "extend", "white_first"):
                self.w[k].value = e[k]
            self.w["cmap"].value = known_cmap(e["cmap"])
        self._set_title()
        self._changed()

    def field_name(self):
        """The series' field: the Field, or its Derivative (fields.deriv_name)."""
        return deriv_name(self.w["deriv"].value, self.w["field"].value)

    def recipe(self):
        w, d = self.w, self.ed.fields[self.field_name()]
        vm = "layer" if self._kind == "th" else w["vmode"].value  # (see show)
        return ser.normalize(dict(
            field=d.name, vmode="2d" if d.ndim == 2 else vm, **vertical_recipe(w),
            **region_recipe(self), **reduce_recipe(w)))

    def collect(self):
        w, e = self.w, dict(self.ent)
        e.pop("_auto", None)
        e["recipe"] = self.recipe()
        for k in ("op", "label", "cmap", "reverse", "white_first", "nlevels", "extend",
                  "cbar_label", "cbar_ticks"):
            e[k] = w[k].value
        e.update(look_values(w), **ens_values(w))
        e["vmin"], e["vmax"] = float(w["vmin"].value or 0.0), float(w["vmax"].value or 0.0)
        e["t0_min"] = float(w["t0"].value or 0.0)
        e["panel"] = panel_index(w)
        e["runs"] = self.run_list()
        if e.get("edits"):  # (a copy: the card goes on editing its own)
            e["edits"] = {k: dict(v) for k, v in e["edits"].items() if v}
        if not e.get("edits"):
            e.pop("edits", None)
        e["base_units"] = self.ed.fields[e["recipe"]["field"]].units
        e["units"] = fg.op_units(e["base_units"], e["op"])
        return e


SND_LINES = (("T", "Temperature", "#d62728", "-"), ("Td", "Dewpoint", "#2ca02c", "-"),
             ("Tp", "Parcel", "#000000", "--"))  # (what Own line looks starts from)


class SoundingCard(TimeCard):
    """One sounding of a sounding figure: run, time, where, look and panel."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        self.w = w = {}
        card_buttons(self, "Remove the sounding", dup=True)
        self._run_time_widgets()
        wh = ent.get("where", {})
        w["kind"] = pn.widgets.Select(name="Where", options=SND_WHERE,
                                      value=wh.get("kind", "trk"), width=180)
        w["x"] = _f("x (km)", float(wh.get("x", 0.0)), 80, step=1.0)
        w["y"] = _f("y (km)", float(wh.get("y", 0.0)), 80, step=1.0)
        w["avg"] = _f("Box width (km, 0: column)", float(wh.get("avg", 0.0)), 170, step=0.5,
                      start=0.0)
        w["label"] = label_widget(ent)
        look_widgets(w, ent, auto=True)
        w["own_looks"] = _chk("Own line looks", any(
            ent.get(f"{k}_{x}") for k, *_ in SND_LINES for x in ("color", "ls", "lw")))
        for k, name, col, ls in SND_LINES:
            w[f"{k}_color"] = pn.widgets.ColorPicker(name=f"{name} colour",
                                                     value=_hex(ent.get(f"{k}_color") or col))
            w[f"{k}_ls"] = pn.widgets.Select(
                name="Line style", options=LINE_STYLES,
                value=ent.get(f"{k}_ls") if ent.get(f"{k}_ls") in LINE_STYLES.values() else ls)
            w[f"{k}_lw"] = _auto("Line width", ent.get(f"{k}_lw"), step=0.25)
        w["panel"] = panel_widget(ent)
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k != "run":
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: ed._fit_grid(), "value")
        self.title = pn.pane.HTML("<b>Sounding</b>", margin=(6, 4, 0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [where_grid(self, w["run"], (w["time"], 2), w["hold"]),
             _grid(w["kind"], w["x"], w["y"], w["avg"], w["auto_color"], w["color"],
                   (w["label"], 3), w["own_looks"]),
             _grid(*[w[f"{k}_{x}"] for k, *_ in SND_LINES for x in ("color", "ls", "lw")]),
             _hint("Automatic colour: the run's colour (the <b>Runs</b> node) when each "
                   "sounding of the panel is from another run, else the next colour. Own line "
                   "looks set the temperature, dewpoint and parcel lines (a blank width: "
                   "automatic); the colour above stays on the barbs and hodograph marks. Keep "
                   "this time holds the sounding still under the ones that step in an "
                   "animation.")])
        self._show()

    def _show(self):
        w = self.w
        w["x"].visible = w["y"].visible = w["avg"].visible = w["kind"].value != "mean"
        w["color"].visible = not w["auto_color"].value
        for k, *_ in SND_LINES:
            for x in ("color", "ls", "lw"):
                w[f"{k}_{x}"].visible = w["own_looks"].value
        where = {"trk": "storm", "pt": "point", "mean": "domain mean"}[w["kind"].value]
        self.title.object = (f"<b>Sounding</b> · {where} · {self._when()} "
                             f"· panel {panel_tag(w)}")

    def collect(self):
        w = self.w
        looks = {}
        if w["own_looks"].value:
            for k, *_ in SND_LINES:
                looks.update({f"{k}_color": w[f"{k}_color"].value, f"{k}_ls": w[f"{k}_ls"].value})
                if w[f"{k}_lw"].value:
                    looks[f"{k}_lw"] = float(w[f"{k}_lw"].value)
        return dict(self._entry(), **looks, where=dict(
            kind=w["kind"].value, x=float(w["x"].value or 0.0), y=float(w["y"].value or 0.0),
            avg=float(w["avg"].value or 0.0)))
