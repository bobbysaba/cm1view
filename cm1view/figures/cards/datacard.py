"""The cards of your own data: a series in a time-series figure (DataCard) or a
profile in a profile figure (ProfileDataCard), points pasted or loaded from a CSV
file, kept in the spec (entry["table"], see spec/panels.parse_table) and drawn beside
the computed ones, with no run and nothing computed."""

import html
import re

import panel as pn

from .. import spec as fg
from .base import (
    _f, _grid, _hint, _fold, LINE_STYLES, card_buttons, label_widget, look_values, look_widgets,
    panel_index, panel_tag, panel_widget, where_grid,
)
from ...viewer.ui import held

UPLOAD_MAX = 2_000_000  # (bytes of a file loaded)
DEFAULT_LABEL = "My data"


class _TableCard:
    """What the cards of your own data share: reading the pasted text or a file into
    self.table (w["text"], w["file"], self.note), a header's label and units, and the
    list interface without runs (the run lists leave the card alone)."""

    AXIS, UNIT = "time", "min"  # (the first column)

    def run_list(self):
        return []

    def set_runs(self, runs):
        pass

    def refresh_runs(self, names=None):
        pass

    def refresh_tracks(self):
        pass

    def _parse(self, text):
        try:
            tab, notes = fg.parse_table(text, self.AXIS)
        except ValueError as ex:
            had = bool(self.table.get("t"))
            self._note(f"Not read: {ex}." + (" The data before is still drawn." if had
                                             else ""), bad=True)
            return
        self.table = tab
        self._from_header(tab.get("names"))
        self._note(notes)
        self._changed()

    def _on_file(self, ev):
        b = ev.new
        if not b:
            return
        if len(b) > UPLOAD_MAX:
            self._note(f"{self.w['file'].filename or 'The file'} is over "
                       f"{UPLOAD_MAX // 1_000_000} MB: thin it first.", bad=True)
            return
        text = b.decode("utf-8-sig", errors="replace")
        if text == self.w["text"].value:
            return
        self.w["text"].value = text  # (read by _parse)

    def _from_header(self, names):
        """A header's second column ("rain (mm)") as the label and units, unless you
        gave them already."""
        if not names or len(names) < 2:
            return
        m = re.match(r"^(.*?)\s*[\(\[](.+)[\)\]]\s*$", names[1])
        lab, units = (m.group(1), m.group(2)) if m else (names[1], "")
        with held(self.ed):
            if lab and self.w["label"].value.strip() in ("", DEFAULT_LABEL):
                self.w["label"].value = lab
            if units and not self.w["units"].value.strip():
                self.w["units"].value = units

    def _note(self, notes=(), bad=False):
        if bad:
            self.note.object = (f'<div class="cv-hint" style="color:#e57373">'
                                f'{html.escape(notes)}</div>')
            return
        t, v = self.table.get("t", []), self.table.get("v", [])
        if not t:
            self.note.object = '<div class="cv-hint">No data yet: paste some or load a ' \
                               'file.</div>'
            return
        gaps = sum(x is None for x in v)
        say = [f"{len(t)} points, {min(t):g} to {max(t):g} {self.UNIT}"
               + (f", {gaps} missing" if gaps else "")] + list(notes)
        self.note.object = f'<div class="cv-hint">{html.escape("; ".join(say))}.</div>'

    def _set_title(self):
        n = len(self.table.get("t", []))
        self.title.object = (f"<b>Your data</b> · {html.escape(self.w['label'].value)} · "
                             f"{n} point{'s' if n != 1 else ''} · panel "
                             f"{panel_tag(self.w)}")


class DataCard(_TableCard):
    """A series of your own: its points (paste them, or load a file), panel, time zero
    and look.  Has the SeriesCard's list interface (panel, buttons, show, collect);
    no runs, so the run lists leave it alone."""

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        self.table = dict(self.ent.get("table") or dict(t=[], v=[]))
        self._kind = ed.kind.value
        self.w = w = {}
        card_buttons(self, "Remove your data", moves=True, dup=True)
        w["text"] = pn.widgets.TextAreaInput(
            name="Your data: time (min), value (paste; read when you click away)",
            value=fg.table_text(self.table) if self.table.get("t") else "",
            placeholder="time_min,value\n0,12.5\n5,14.1\n10,\n15,18.0",
            rows=8, sizing_mode="stretch_width", min_width=300)
        w["file"] = pn.widgets.FileInput(accept=".csv,.txt,.dat,.tsv", multiple=False,
                                         width=240)
        w["label"] = label_widget(self.ent, "Legend text", DEFAULT_LABEL)
        w["units"] = pn.widgets.TextInput(name="Units (axis sharing)", width=130,
                                          value=self.ent.get("units", ""),
                                          placeholder="e.g. m/s")
        w["panel"] = panel_widget(self.ent)
        w["t0"] = _f("Time zero (min)", float(self.ent.get("t0_min") or 0.0), 110, step=1.0,
                     description="Your times are counted from here, as a run's are from its "
                                 "time zero (your data has no run)")
        look_widgets(w, self.ent, ls=LINE_STYLES, lw=1.5, marker=True, axis=True)
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self.note = pn.pane.HTML(margin=(0, 4), sizing_mode="stretch_width")
        self.th_note = _hint("Your own data is drawn in time-series figures only.")
        w["text"].param.watch(lambda e: self._parse(e.new), "value")
        w["file"].param.watch(self._on_file, "value")
        w["panel"].param.watch(lambda e: self._where_changed(), "value")
        for k in ("label", "units", "ylabel", "t0", "color", "ls", "lw", "marker", "axis"):
            w[k].param.watch(lambda e: self._changed(), "value")
        self.body_col = pn.Column(
            where_grid(self, w["t0"]), w["text"],
            pn.Column(pn.pane.HTML("<small>Or load a file</small>", margin=(0, 4)), w["file"],
                      margin=0),
            self.note,
            _hint("Two columns, time (min) and value, split by commas, tabs or spaces; a "
                  "header line is optional (<i>time, rain (mm)</i> gives the label and "
                  "units), lines starting with # are skipped, and a blank or <i>nan</i> "
                  f"value leaves a gap.  Up to {fg.TABLE_MAX} points, kept in the figure."),
            _grid((w["label"], 2), w["units"], w["color"], w["ls"], w["lw"], w["marker"],
                  w["axis"], w["ylabel"]),
            margin=0, sizing_mode="stretch_width")
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.up, self.down, self.rm],
            [self.th_note, self.body_col])
        self._note()
        self.show(self._kind)

    # ---- the list's interface (no runs, no recipe)
    def show(self, kind):
        self._kind = kind
        self.body_col.visible = kind == "line"
        self.th_note.visible = kind != "line"
        self._set_title()

    # ---- changes
    def _changed(self):
        self._set_title()
        self.ed.request()

    def _where_changed(self):
        self._set_title()
        self.ed._series_changed()

    def collect(self):
        w, e = self.w, dict(self.ent)
        e.update(source="table", recipe={}, runs=[], op="", ens="",
                 table={k: list(v) for k, v in self.table.items()})
        e.update(look_values(w), label=w["label"].value)
        e["units"] = e["base_units"] = w["units"].value.strip()
        e["t0_min"] = float(w["t0"].value or 0.0)
        e["panel"] = panel_index(w)
        e.pop("edits", None)
        return e


class ProfileDataCard(_TableCard):
    """A profile of your own: its points (height, km, and value; paste them, or load a
    file), panel and look.  Has the ProfileCard's list interface (panel, buttons,
    collect); no runs, so the run lists leave it alone."""

    AXIS, UNIT = "height", "km"

    def __init__(self, ed, ent):
        self.ed, self.ent = ed, dict(ent)
        self.table = dict(self.ent.get("table") or dict(t=[], v=[]))
        self.w = w = {}
        card_buttons(self, "Remove your data", dup=True)
        w["text"] = pn.widgets.TextAreaInput(
            name="Your data: height (km), value (paste; read when you click away)",
            value=fg.table_text(self.table, "height") if self.table.get("t") else "",
            placeholder="z_km,value\n0.5,12.5\n1,14.1\n1.5,\n2,18.0",
            rows=8, sizing_mode="stretch_width", min_width=300)
        w["file"] = pn.widgets.FileInput(accept=".csv,.txt,.dat,.tsv", multiple=False,
                                         width=240)
        w["label"] = label_widget(self.ent, "Legend text", DEFAULT_LABEL)
        w["units"] = pn.widgets.TextInput(name="Units", width=110,
                                          value=self.ent.get("units", ""),
                                          placeholder="e.g. m/s")
        w["xlabel"] = pn.widgets.TextInput(
            name="Value axis label (blank: the computed profiles')", width=260,
            value=self.ent.get("xlabel", ""))
        w["panel"] = panel_widget(self.ent)
        look_widgets(w, self.ent, ls=LINE_STYLES, lw=1.5, marker=True)
        self.title = pn.pane.HTML(margin=(6, 4, 0, 4))
        self.note = pn.pane.HTML(margin=(0, 4), sizing_mode="stretch_width")
        w["text"].param.watch(lambda e: self._parse(e.new), "value")
        w["file"].param.watch(self._on_file, "value")
        w["panel"].param.watch(lambda e: (self._set_title(), ed._fit_grid(), ed.request()),
                               "value")
        for k in ("label", "units", "xlabel", "color", "ls", "lw", "marker"):
            w[k].param.watch(lambda e: self._changed(), "value")
        self.panel, self.body = _fold(
            [self.title, pn.Spacer(), self.rm],
            [where_grid(self), w["text"],
             pn.Column(pn.pane.HTML("<small>Or load a file</small>", margin=(0, 4)), w["file"],
                       margin=0),
             self.note,
             _hint("Two columns, height (km) and value, split by commas, tabs or spaces; a "
                   "header line is optional (<i>z, w (m/s)</i> gives the label and units), "
                   "lines starting with # are skipped, and a blank or <i>nan</i> value "
                   f"leaves a gap.  Up to {fg.TABLE_MAX} points, kept in the figure.  A "
                   "profile card's <b>Download CSV</b> (under Values) reads back in here."),
             _grid((w["label"], 2), w["units"], w["color"], w["ls"], w["lw"], w["marker"],
                   (w["xlabel"], 2))])
        self._note()
        self._set_title()

    def _changed(self):
        self._set_title()
        self.ed.request()

    def collect(self):
        w = self.w
        e = fg.profile_table_defaults()
        e.update(table={k: list(v) for k, v in self.table.items()},
                 panel=panel_index(w), units=w["units"].value.strip(), label=w["label"].value,
                 xlabel=w["xlabel"].value, **look_values(w))
        return e
