"""The card of a parcel series of a time-series figure: a variable of a parcel set
over the parcel times (spec/panels.parcel_series_defaults), as its centre and band
over the parcels and, if you like, the lines of some of them; nothing computed."""

import html

import panel as pn

from .. import spec as fg
from ...core import parcels as P
from .base import (
    _hex, _f, _grid, _hint, _fold, _retired, ENS_BANDS, ENS_MIDS, LINE_STYLES, band_opacity, card_buttons,
    label_widget, look_values, look_widgets, panel_index, panel_tag, panel_widget, run_widget,
    where_grid,
)
from .layercard import parcel_pick, parcel_sets
from ...viewer.ui import held

PAR_OPS = {"Value": "", "d/dt along the parcel": "ddt",
           "Change since the set's time": "delta", "∫ dt since the set's time": "int"}
OP_TAGS = {"ddt": " d/dt", "delta": " change", "int": " ∫ dt"}
PAR_EACH_LOOK = {"Faint": "faint", "As other lines": "full"}


class ParcelSeriesCard:
    """A parcel set's variable over the parcel times: its run, set (the viewer's sets
    and the saved ones can replace it), variable, centre, band, lines of its own,
    panel, time zero and look.  Has the SeriesCard's list interface (panel, buttons,
    show, collect, run lists); no recipe and no hand edits."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        self._kind = ed.kind.value
        pf = ed.v.pf
        self.w = w = {}
        card_buttons(self, "Remove the parcel series", moves=True, dup=True)
        w["run"] = run_widget(ed, dict(run=(ent.get("runs") or [0])[0]))
        w["pset"] = pn.widgets.Select(name="Parcels", value="", width=220,
                                      options=parcel_sets(ed.v, self.ent, "this card's"),
                                      description="The parcel set: pick another set of the "
                                                  "viewer, or a saved one")
        w["var"] = pn.widgets.Select(name="Variable", width=170,
                                     groups=P.var_choices(pf, keep=ent.get("var", "")),
                                     value=ent.get("var", ""))
        w["op"] = pn.widgets.Select(name="Plot", options=PAR_OPS, width=170,
                                    value=ent.get("op", "") if ent.get("op") in
                                    PAR_OPS.values() else "")
        w["mid"] = pn.widgets.Select(name="Centre line", options=ENS_MIDS,
                                     value=ent.get("ens_mid", "mean"), width=100)
        w["ens"] = pn.widgets.Select(name="Band over the parcels", options=ENS_BANDS,
                                     value=ent.get("ens", ""), width=170)
        w["alpha"] = band_opacity(ent)
        w["each"] = pn.widgets.IntInput(
            name="Parcels' own lines", start=0, end=fg.PARCEL_EACH_MAX, width=130,
            value=int(ent.get("each") or 0),
            description=f"Draw this many parcels' own lines too, spread through the set "
                        f"(0: none; at most {fg.PARCEL_EACH_MAX})")
        w["members"] = pn.widgets.Select(name="Their look", options=PAR_EACH_LOOK, width=120,
                                         value=ent.get("ens_members") if
                                         ent.get("ens_members") in PAR_EACH_LOOK.values()
                                         else "faint")
        w["label"] = label_widget(ent, "Legend text")
        w["panel"] = panel_widget(ent)
        w["t0"] = _retired(_f(
            "Time zero (min)", float(ent.get("t0_min") or 0.0), 110, step=1.0,
            description="From an older figure: adds to its run's time zero (on the Runs "
                        "node), which is the place to set it. At 0 this box goes away"))
        look_widgets(w, ent, ls=LINE_STYLES, lw=1.5, marker=True, axis=True)
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self.th_note = _hint("Parcel series are drawn in time-series figures only.")
        w["run"].param.watch(self._on_run, "value")
        w["pset"].param.watch(self._on_pset, "value")
        w["panel"].param.watch(lambda e: self._where_changed(), "value")
        for k in ("var", "op"):
            w[k].param.watch(lambda e: self._on_what(), "value")
        for k in ("mid", "ens", "each", "members", "label", "t0", "color", "ls", "lw",
                  "alpha", "marker", "axis", "ylabel"):
            w[k].param.watch(lambda e: self._changed(), "value")
        self.body_col = pn.Column(
            where_grid(self, w["run"], (w["pset"], 2), w["t0"]),
            _grid(w["var"], w["op"], w["mid"], w["ens"], w["alpha"], w["each"],
                  w["members"], (w["label"], 2)),
            _hint("Over the parcel times (often finer than the 3D output): the centre and "
                  "band at each time are over the parcels there then (a parcel that left "
                  "the domain drops out). Change and ∫ dt count from the time the set was "
                  "chosen."),
            _grid(w["color"], w["ls"], w["lw"], w["marker"], w["axis"], w["ylabel"]),
            margin=0, sizing_mode="stretch_width")
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.up, self.down, self.rm],
            [self.th_note, self.body_col])
        self.ent["_auto"] = self._auto()
        self.show(self._kind)

    # ---- the list's interface (one run, no recipe)
    def show(self, kind):
        self._kind = kind
        w = self.w
        self.body_col.visible = kind == "line"
        self.th_note.visible = kind != "line"
        w["alpha"].visible = bool(w["ens"].value)
        w["members"].visible = bool(w["each"].value) and \
            bool(w["ens"].value or w["mid"].value)
        self._set_title()

    def run_list(self):
        k = self.w["run"].value
        return [int(k) if isinstance(k, int) and k >= 0 else 0]

    def set_runs(self, runs):
        with held(self.ed):
            self.w["run"].value = int((runs or [0])[0])
        self.show(self._kind)

    def refresh_runs(self, names=None):
        names = names or self.ed._run_names()
        keep = self.run_list()[0]
        with held(self.ed):
            self.w["run"].param.update(**self.ed._run_choices(names))
        self.set_runs([keep if keep in names.values() else 0])

    def refresh_tracks(self):
        pass

    def _set_title(self):
        w = self.w
        op = OP_TAGS.get(w["op"].value, "").replace(" ", " · ", 1)
        self.title.object = (f"<b>Parcels</b> · {html.escape(self.ent.get('name') or '')}"
                             f" · {html.escape(w['var'].value or '')}{op} · panel "
                             f"{panel_tag(w)}")

    # ---- changes
    def _on_run(self, ev):
        if self.ed._hold:
            return
        if isinstance(ev.new, str):  # (a run not in the figure yet)
            self.ed._pick_other(self.w["run"], ev.old)
            return
        self._where_changed()

    def _on_pset(self, ev):
        """Another set: its parcels (rule or ids), name and colour."""
        if not ev.new:
            return
        src = parcel_pick(self.ed, ev.new)
        if src is not None:
            self.ent.update(src)
        with held(self.ed):
            self.w["pset"].options = parcel_sets(self.ed.v, self.ent, "this card's")
            self.w["pset"].value = ""
            if src is not None and src.get("color"):
                self.w["color"].value = _hex(src["color"])
        if src is not None:
            self._on_what()

    def _auto(self):
        op = OP_TAGS.get(self.w["op"].value, "")
        return f"{self.ent.get('name') or 'parcels'}: {P.var_label(self.w['var'].value)}{op}"

    def _on_what(self):
        """Another set, variable or Plot: an automatic label follows (an edited one
        stays)."""
        new = self._auto()
        if self.w["label"].value in ("", self.ent.get("_auto", "")):
            with held(self.ed):
                self.w["label"].value = new
        self.ent["_auto"] = new
        self._changed()

    def _changed(self):
        self.show(self._kind)
        self.ed.request()

    def _where_changed(self):
        self.show(self._kind)
        self.ed._series_changed()

    def collect(self):
        w, e, pf = self.w, dict(self.ent), self.ed.v.pf
        e.pop("_auto", None)
        var = w["var"].value or ""
        if pf is not None and pf.has(var):
            e["base_units"] = pf.units(var)
        e.update(source="parcels", recipe={}, runs=self.run_list(), var=var,
                 op=w["op"].value, ens=w["ens"].value, ens_mid=w["mid"].value,
                 ens_members=w["members"].value, each=int(w["each"].value or 0))
        e["units"] = fg.op_units(e.get("base_units", ""), e["op"])
        e.update(look_values(w), label=w["label"].value)
        e["ens_alpha"] = float(w["alpha"].value if w["alpha"].value is not None else 0.25)
        e["t0_min"] = float(w["t0"].value or 0.0)
        e["panel"] = panel_index(w)
        e.pop("edits", None)
        return e
