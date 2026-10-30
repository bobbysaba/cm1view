"""The cards of one series of a time-height / time-series figure and of one
sounding of a sounding figure."""

import os

import panel as pn

from ...core import series as ser
from ...core.fields import deriv_name
from .. import spec as fg
from .base import (
    FIG_CMAPS, _hex, _f, _auto, _grid, _hint, _fold, SER_REGIONS, SER_REDUCE, SER_OPS,
    MARKERS, SND_WHERE, _BTN, _chk, _deriv_pair,
)
from .seriesvals import SeriesValues

ENS_BANDS = {"Off": "", "Min to max": "minmax", "10–90th percentile": "p10p90",
             "25–75th percentile": "p25p75", "Mean ± 1 sd": "sd"}
SER_STYLES = {"Solid": "-", "Dashed": "--", "Dotted": ":", "Dash-dot": "-."}
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


class SeriesCard:
    """One series of a time-height / time-series figure, like a sounding card: its
    run (a time series: also every run, or the runs picked), panel, a Series-tab
    recipe (field, level or layer, region, reduction), an optional derivative, and its
    look.  A time-height card is one panel (its run's series)."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        F, r = ed.fields, ent["recipe"]
        self.box = r.get("box")
        self.w = w = {}
        self.up = pn.widgets.Button(name="↑", description="Earlier in the list", **_BTN)
        self.down = pn.widgets.Button(name="↓", description="Later in the list", **_BTN)
        self.rm = pn.widgets.Button(name="✕", description="Remove the series", **_BTN)
        self.dup = pn.widgets.Button(name="Duplicate", height=32, button_type="light",
                                     button_style="outline",
                                     description="A copy of this card in a new panel")
        self.per_run = pn.widgets.Button(
            name="One per run", height=32, button_type="light", button_style="outline",
            description="Time series: a card for each run (this card's runs, or each "
                        "other run of the figure) in this panel; time-height: a copy for "
                        "each other run, down this card's column (a row per run)")
        self._kind = ed.kind.value
        runs = ent.get("runs")
        k = (ALL_RUNS if self._kind != "th" else 0) if runs is None else \
            int(runs[0]) if len(runs) == 1 else SOME_RUNS
        w["run"] = pn.widgets.Select(name="Run", width=170, **self._run_choices())
        w["run"].value = k if k in self._run_values() else 0
        w["field"], w["deriv"] = _deriv_pair(F, r["field"])
        w["vmode"] = pn.widgets.Select(name="Vertical", options={
            "Layer (every level)": "layer", "At a height": "height"},
            value="height" if r["vmode"] == "height" else "layer", width=150)
        w["z"] = _f("Height (km)", float(r.get("z", 1.0)), 90, step=0.25)
        w["z0"] = _f("Bottom (km)", float(r.get("z0", 0.0)), 90, step=0.5)
        w["z1"] = _f("Top (km)", float(r.get("z1", 10.0)), 80, step=0.5)
        w["region"] = pn.widgets.Select(name="Region", options=SER_REGIONS, value=r["region"],
                                        width=180)
        w["radius"] = _f("Radius (km)", float(r.get("radius", 5.0)), 90, step=0.5)
        off = r.get("offset", (0.0, 0.0))
        w["offx"] = _f("Offset x (km)", float(off[0]), 100, step=1.0)
        w["offy"] = _f("Offset y (km)", float(off[1]), 100, step=1.0)
        w["reduce"] = pn.widgets.Select(name="Reduce", options=SER_REDUCE, value=r["reduce"],
                                        width=120)
        w["pct"] = _f("Percentile", float(r.get("pct", 99.0)), 90, step=0.5)
        w["op"] = pn.widgets.Select(name="Plot", options=SER_OPS, value=ent.get("op", ""),
                                    width=130)
        w["label"] = pn.widgets.TextInput(name="Label (titles, legend)",
                                          value=ent.get("label", ""), width=300)
        # time-height look
        w["cmap"] = pn.widgets.Select(name="Colormap", options=FIG_CMAPS, width=150,
                                      value=ent["cmap"] if ent["cmap"] in FIG_CMAPS
                                      else "viridis")
        w["reverse"] = _chk("Reverse", ent.get("reverse", False))
        w["white_first"] = _chk("White first", ent.get("white_first", False))
        w["vmin"] = _f("Min", float(ent["vmin"]))
        w["vmax"] = _f("Max", float(ent["vmax"]))
        w["nlevels"] = pn.widgets.IntInput(name="Steps (0 = smooth)", start=0, end=60,
                                           value=int(ent.get("nlevels") or 0), width=120)
        w["extend"] = pn.widgets.Select(name="Colorbar ends", options=[
            "auto", "neither", "max", "min", "both"], value=ent.get("extend", "neither"),
            width=110)
        w["cbar_label"] = pn.widgets.TextInput(
            name="Colorbar label (blank: units)", value=ent.get("cbar_label", "") or "",
            placeholder=ent.get("units", ""), width=240)
        w["cbar_ticks"] = pn.widgets.TextInput(
            name="Colorbar ticks (blank: auto)", value=ent.get("cbar_ticks", "") or "",
            placeholder="0:60:10", width=150)
        # time-series look
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(ent.get("color", "k")),
                                            width=70)
        w["lw"] = _f("Line width", float(ent.get("lw", 1.5)), 90, step=0.25)
        w["ls"] = pn.widgets.Select(name="Line", options=SER_STYLES, width=100,
                                    value=ent.get("ls") if ent.get("ls") in
                                    SER_STYLES.values() else "-")
        w["t0"] = _f("Time zero (min)", float(ent.get("t0_min") or 0.0), 110, step=1.0,
                     description="This series' times are shown from here, e.g. its run's "
                                 "initiation, so runs line up (0: model time; adds to "
                                 "Style → Panel labels → Minutes counted from)")
        w["marker"] = pn.widgets.Select(name="Markers", options=MARKERS,
                                        value=ent.get("marker", ""), width=100)
        w["panel"] = pn.widgets.IntInput(name="Panel", start=1, end=64, width=70,
                                         value=int(ent.get("panel", 0)) + 1)
        w["axis"] = pn.widgets.Select(name="y axis", options={"By units": "auto",
                                                              "Own axis (right)": "right"},
                                      value=ent.get("axis", "auto"), width=140)
        w["runs"] = pn.widgets.MultiChoice(name="Runs", options=ed._series_run_opts(),
                                           value=[int(k) for k in (runs or [])]
                                           if k == SOME_RUNS else [], width=260)
        w["ylabel"] = pn.widgets.TextInput(name="Axis label (blank: units)",
                                           value=ent.get("ylabel", ""), width=180)
        w["ens"] = pn.widgets.Select(name="Ensemble of its runs", options=ENS_BANDS,
                                     value=ent.get("ens", ""), width=170)
        w["ens_mid"] = pn.widgets.Select(name="Centre line", options={
            "Mean": "mean", "Median": "median", "None": ""},
            value=ent.get("ens_mid", "mean"), width=100)
        w["ens_members"] = pn.widgets.Select(name="Runs' own lines", options={
            "Faint": "faint", "Hidden": "hidden", "As other lines": "full"},
            value=ent.get("ens_members", "faint"), width=130)
        w["ens_alpha"] = _f("Band opacity", float(ent.get("ens_alpha", 0.25)), 100, step=0.05,
                            start=0.0, end=1.0)
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
        self.trk_box = pn.Column(margin=0, sizing_mode="stretch_width")  # (refresh_tracks)
        self.vals = SeriesValues(self)  # (time series: its values, and your edits of them)
        self.where = _grid(w["run"], (w["runs"], 2), w["panel"], w["t0"], self.dup,
                           self.per_run)
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.up, self.down, self.rm],
            [self.where,
             _grid((w["field"], 2), w["deriv"], w["vmode"], w["z"], w["z0"], w["z1"],
                   w["region"], w["radius"], w["offx"], w["offy"], w["reduce"], w["pct"],
                   w["op"], (w["label"], 3)), self.trk_box, self.th_row, self.line_row,
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
        trkr = w["region"].value == "track"
        w["radius"].visible = w["offx"].visible = w["offy"].visible = trkr
        w["pct"].visible = w["reduce"].value == "pct"
        self.th_row.visible = kind == "th"
        self.line_row.visible = self.vals.section.visible = kind == "line"
        w["runs"].visible = kind == "line" and w["run"].value == SOME_RUNS
        several = kind == "line" and w["run"].value in (ALL_RUNS, SOME_RUNS)
        w["ens"].visible = several
        for k in ("ens_mid", "ens_members", "ens_alpha"):
            w[k].visible = several and bool(w["ens"].value)
        self.refresh_tracks()
        self._set_title()

    def refresh_tracks(self):
        """Around the tracked storm: the storm track of each of the card's runs (the
        figure's, shared by every card of that run: the viewer's Track tab for the
        viewer's run, or a track file), as the run rows have them."""
        ed, rows = self.ed, getattr(self.ed, "run_rows", [])
        if self.w["region"].value != "track" or not rows:
            self.trk_box.objects, self.trk_box.visible, self.trk_w = [], False, {}
            return
        ks = self.run_list()
        ks = [k for k in (range(len(rows)) if ks is None else ks) if k < len(rows)]
        out, self.trk_w = [], {}  # (run index: its viewer's-track box and track file)
        for k in ks:
            r = rows[k]
            name = os.path.basename(r["path"].rstrip("/"))
            own = r["path"] == ed.run.path
            tab = _chk("Viewer's track", r["tab"].value)
            tab.visible = own
            txt = pn.widgets.TextInput(
                name=f"Storm track of {name} (blank: none)", value=r["track"].value,
                disabled=own and r["tab"].value, placeholder="storm_tracks/<run>.csv",
                sizing_mode="stretch_width", min_width=240)
            tab.param.watch(lambda ev, r=r: r["tab"].param.update(value=ev.new), "value")
            txt.param.watch(lambda ev, r=r: r["track"].param.update(value=ev.new), "value")
            self.trk_w[k] = (tab, txt)
            out.append(_grid((txt, 2), tab))
            out.append(pn.pane.HTML(f'<div class="cv-hint">{ed._track_note(r)}</div>',
                                    margin=(0, 4)))
        out.append(_hint("A run's track is shared by every card of that run "
                         "(storm_tracks/*.csv next to a run is found automatically)."))
        self.trk_box.objects, self.trk_box.visible = out, True

    # ---- run
    def _run_choices(self, names=None):
        """The Run list's choices: the figure's runs (a time series: then every run, or
        the runs picked), and the others (picking one adds it)."""
        if self._kind == "th":
            return self.ed._run_choices(names)
        return several_run_choices(self.ed, names)

    def _run_values(self):
        o = self.w["run"].groups or {"": self.w["run"].options}
        return [v for g in o.values() for v in (g.values() if isinstance(g, dict) else g)]

    def run_list(self):
        """The card's runs: None for every run, else a list of run indices."""
        k = self.w["run"].value
        if self._kind != "th" and k == ALL_RUNS:
            return None
        if self._kind != "th" and k == SOME_RUNS:
            return sorted(int(j) for j in self.w["runs"].value if not isinstance(j, str)) \
                or None
        return [int(k)] if isinstance(k, int) and k >= 0 else [0]

    def set_runs(self, runs):
        """Show runs (None: every run; a time-height card: its first run)."""
        w = self.w
        hold, self.ed._hold = self.ed._hold, True
        try:
            if runs is not None and len(runs) == 1 or self._kind == "th":
                w["runs"].value = []
                w["run"].value = int((runs or [0])[0])
            elif runs is None:
                w["runs"].value = []
                w["run"].value = ALL_RUNS
            else:
                w["runs"].value = sorted(int(k) for k in runs)
                w["run"].value = SOME_RUNS
        finally:
            self.ed._hold = hold
        self.show(self._kind)

    def refresh_runs(self, names=None):
        """The run lists' choices again (runs renamed, added or removed, or another
        kind of figure), keeping the card's runs."""
        names = names or self.ed._run_names()
        keep = self.run_list()
        hold, self.ed._hold = self.ed._hold, True
        try:
            self.w["runs"].options = self.ed._series_run_opts(names)
            self.w["run"].param.update(**self._run_choices(names))
        finally:
            self.ed._hold = hold
        self.set_runs([k for k in keep if k in names.values()] or [0]
                      if keep is not None else None)

    def _on_run(self, ev):
        if self.ed._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
            return
        if ev.new == SOME_RUNS and not self.w["runs"].value:  # (from every run)
            hold, self.ed._hold = self.ed._hold, True
            try:
                self.w["runs"].value = sorted(self.ed._run_names().values())
            finally:
                self.ed._hold = hold
        self._where_changed()

    def _where_changed(self):
        self.show(self.ed.kind.value)
        self.ed._series_changed()
        self.vals.refresh()

    def _on_runs(self, ev):
        """A run not in the figure picked (its path): add it to the figure, and keep
        it picked here."""
        new = [v for v in ev.new if isinstance(v, str)]
        if self.ed._hold:
            return
        if not new:
            self.ed._series_changed()
            return
        keep = [v for v in ev.new if not isinstance(v, str)]
        for p in new:
            k = self.ed._add_run(p, grid=False)
            if k is not None:
                keep.append(k)
        hold, self.ed._hold = self.ed._hold, True
        try:
            self.w["runs"].value = sorted(set(keep))
        finally:
            self.ed._hold = hold
        self.ed._series_changed()

    def _set_title(self):
        w = self.w
        d = self.ed.fields[self.field_name()]
        op = {"ddz": " · d/dz", "ddt": " · d/dt"}.get(w["op"].value, "")
        runs = self.run_list()
        names = {k: n.split(". ", 1)[-1] for n, k in self.ed._run_names().items()}
        run = "every run" if runs is None else names.get(runs[0], "") if len(runs) == 1 \
            else f"{len(runs)} runs"
        self.title.object = (f"<b>Series</b> · {d.label}{op} · {run} · "
                             f"panel {w['panel'].value}")

    def _changed(self):
        if self.w["region"].value == "box" and self.box is None:
            self.box = [float(v) for v in self.ed.v.view]
        self.show(self.ed.kind.value)
        self._auto_label()
        self._edits_stale()
        self.ed.request()

    def _op_changed(self):
        self._set_title()
        self._edits_stale()

    def _edits_stale(self):
        """The recipe or derivative changed: hand edits (made on the values before)
        are kept, with a word on the card."""
        self._stale = bool(self.vals.count())
        self.edits_changed()
        self.vals.refresh()

    def edits_changed(self):
        n = self.vals.count()
        self._stale = getattr(self, "_stale", False) and bool(n)
        self.info.object = (
            f'<div class="cv-hint">{n} hand edit{"s" if n != 1 else ""} made on this '
            f'series before its recipe or Plot changed are still drawn: check them under '
            f'Values (Reset all edits clears them).</div>' if self._stale else "")

    def _auto_label(self):
        """Keep an automatic label in step with the recipe (an edited one stays)."""
        old = self.ent.get("_auto", self.ent.get("label", ""))
        d = self.ed.fields[self.field_name()]
        new = ser.describe(self.recipe(), d.label)
        if self.w["label"].value in ("", old):
            hold, self.ed._hold = self.ed._hold, True
            try:
                self.w["label"].value = new
            finally:
                self.ed._hold = hold
        self.ent["_auto"] = new

    def _on_field(self, ev):
        """New field: its colours and range."""
        e = fg.series_defaults(self.ed.fields, self.recipe())
        self.ed._hold = True
        try:
            for k in ("vmin", "vmax", "extend", "white_first"):
                self.w[k].value = e[k]
            self.w["cmap"].value = e["cmap"] if e["cmap"] in FIG_CMAPS else "viridis"
        finally:
            self.ed._hold = False
        self._set_title()
        self._changed()

    def field_name(self):
        """The series' field: the Field, or its Derivative (fields.deriv_name)."""
        return deriv_name(self.w["deriv"].value, self.w["field"].value)

    def recipe(self):
        w, d = self.w, self.ed.fields[self.field_name()]
        vm = "layer" if self._kind == "th" else w["vmode"].value  # (see show)
        r = dict(field=d.name, vmode="2d" if d.ndim == 2 else vm,
                 z=w["z"].value or 0.0, z0=w["z0"].value or 0.0, z1=w["z1"].value or 0.0,
                 region=w["region"].value, radius=w["radius"].value or 5.0,
                 offset=(w["offx"].value or 0.0, w["offy"].value or 0.0),
                 reduce=w["reduce"].value,
                 pct=w["pct"].value if w["pct"].value is not None else 99.0,
                 box=self.box or [float(v) for v in self.ed.v.view])
        return ser.normalize(r)

    def collect(self):
        w, e = self.w, dict(self.ent)
        e.pop("_auto", None)
        e["recipe"] = self.recipe()
        for k in ("op", "label", "cmap", "reverse", "white_first", "nlevels", "extend",
                  "color", "ls", "marker", "axis", "ylabel", "cbar_label", "cbar_ticks", "ens",
                  "ens_mid", "ens_members"):
            e[k] = w[k].value
        e["vmin"], e["vmax"] = float(w["vmin"].value or 0.0), float(w["vmax"].value or 0.0)
        e["lw"] = float(w["lw"].value or 1.5)
        e["t0_min"] = float(w["t0"].value or 0.0)
        e["ens_alpha"] = float(w["ens_alpha"].value if w["ens_alpha"].value is not None
                               else 0.25)
        e["panel"] = max(0, int(w["panel"].value or 1) - 1)
        e["runs"] = self.run_list()
        if e.get("edits"):  # (a copy: the card goes on editing its own)
            e["edits"] = {k: dict(v) for k, v in e["edits"].items() if v}
        if not e.get("edits"):
            e.pop("edits", None)
        e["base_units"] = self.ed.fields[e["recipe"]["field"]].units
        e["units"] = fg.op_units(e["base_units"], e["op"])
        return e


class SoundingCard:
    """One sounding of a sounding figure: run, time, where, look and panel."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        self.w = w = {}
        self.rm = pn.widgets.Button(name="✕", description="Remove the sounding", **_BTN)
        names = ed._run_names()
        k = int(ent.get("run", 0)) if int(ent.get("run", 0)) in names.values() else 0
        w["run"] = pn.widgets.Select(name="Run", value=k, width=170, **ed._run_choices(names))
        opts = ed._time_opts(k)
        w["time"] = pn.widgets.Select(name="Time", options=opts, width=210,
                                      value=ed._nearest(opts, ent.get("time_s")))
        wh = ent.get("where", {})
        w["kind"] = pn.widgets.Select(name="Where", options=SND_WHERE,
                                      value=wh.get("kind", "trk"), width=180)
        w["x"] = _f("x (km)", float(wh.get("x", 0.0)), 80, step=1.0)
        w["y"] = _f("y (km)", float(wh.get("y", 0.0)), 80, step=1.0)
        w["avg"] = _f("Box width (km, 0: column)", float(wh.get("avg", 0.0)), 170, step=0.5,
                      start=0.0)
        w["label"] = pn.widgets.TextInput(name="Legend text (blank: automatic)",
                                          value=ent.get("label", ""), width=220)
        w["auto_color"] = _chk("Automatic colour", not ent.get("color"))
        w["color"] = pn.widgets.ColorPicker(name="Color", value=_hex(ent.get("color") or "k"),
                                            width=70)
        w["panel"] = pn.widgets.IntInput(name="Panel", start=1, end=64, width=70,
                                         value=int(ent.get("panel", 0)) + 1)
        w["run"].param.watch(self._on_run, "value")
        for k, x in w.items():
            if k != "run":
                x.param.watch(lambda e: self._changed(), "value")
        w["panel"].param.watch(lambda e: ed._fit_grid(), "value")
        self.title = pn.pane.HTML("<b>Sounding</b>", margin=(6, 4, 0, 4))
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [_grid(w["run"], (w["time"], 2), w["kind"], w["x"], w["y"], w["avg"],
                   w["auto_color"], w["color"], w["panel"], (w["label"], 3)),
             _hint("Automatic colour: the run's colour (<b>Layers → Runs used</b>) when each "
                   "sounding of the panel is from another run, else the next colour.")])
        self._show()

    def _show(self):
        w = self.w
        w["x"].visible = w["y"].visible = w["avg"].visible = w["kind"].value != "mean"
        w["color"].visible = not w["auto_color"].value
        where = {"trk": "storm", "pt": "point", "mean": "domain mean"}[w["kind"].value]
        when = next((k for k, v in w["time"].options.items() if v == w["time"].value), "")
        self.title.object = (f"<b>Sounding</b> · {where} · {when.split('(')[-1].rstrip(')')} "
                             f"· panel {w['panel'].value}")

    def _changed(self):
        self._show()
        self.ed.request()

    def _on_run(self, ev):
        if self.ed._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self.ed._pick_other(self.w["run"], ev.old)
            return
        o = self.ed._time_opts(ev.new)
        cur = self.w["time"].value
        self.ed._hold = True
        try:
            self.w["time"].options = o
            self.w["time"].value = self.ed._nearest(o, cur)
        finally:
            self.ed._hold = False
        self.ed.request()

    def collect(self):
        w = self.w
        return dict(run=int(w["run"].value or 0), time_s=float(w["time"].value or 0.0),
                    panel=max(0, int(w["panel"].value or 1) - 1), label=w["label"].value,
                    color="" if w["auto_color"].value else w["color"].value,
                    where=dict(kind=w["kind"].value, x=float(w["x"].value or 0.0),
                               y=float(w["y"].value or 0.0),
                               avg=float(w["avg"].value or 0.0)))
