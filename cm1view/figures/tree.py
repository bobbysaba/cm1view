"""The panel tree (the editor's Tree tab): the figure panel by panel, each with what it
draws, to change one panel alone: its run, time, height, title and axis labels, and
its layers (each can come from a run and time of its own, keep its time in an
animation, or look different here), and layers of that panel only.

The changes are kept in the spec as "edits" ({panel: changes}, figdraw.panel_edit):
the Panels and Layers tabs still lay out every panel (they are the generator), and
the edits are applied on top, by figdraw.upgrade into the version-2 panels that are
drawn and saved.  A mixin of the FigureEditor (figui)."""

import copy
import json
from types import SimpleNamespace

import panel as pn

from . import draw as figdraw, spec as fg
from .cards import LOCS, TYPE_LABEL, LayerCard, _chk, _grid, _hint, _xy, _xy_text

PANELS = "the panel's"  # (a layer's run / time: the panel's)
LAYOUT = "as laid out"  # (a panel's run / time / height / title: the layout's)
OWN_KEYS = ("run", "time_s", "time_lock")  # a layer's own source (not its look)
ADD = {"Fill": "fill", "Contours": "contour", "Shading": "shade", "Vectors": "vectors"}


class _PanelEditor:
    """What a LayerCard asks of the editor, for a layer of one panel: the panel's kind,
    the field lists, and request(), which records the card's settings."""

    def __init__(self, ed, kind, changed):
        self.v, self.fields = ed.v, ed.fields
        self.kind = SimpleNamespace(value=kind)
        self.vary = SimpleNamespace(value="custom")  # (its height is the layer's)
        self._hold = False
        self._changed = changed
        self._run_names, self._time_opts = ed._run_names, ed._time_opts  # (Difference)
        self._layer_run_choices = ed._layer_run_choices
        self._pick_other = ed._pick_other  # (adds the run to the figure)

    def _show_region(self):
        """(The tree has no region settings to show.)"""

    def request(self):
        if not self._hold:
            self._changed()


def clean_edits(edits):
    """The edits without empty entries (what collect() stores)."""
    out = {}
    for i, e in (edits or {}).items():
        e = {k: v for k, v in e.items() if v not in (None, {}, [])}
        lays = {j: {k: v for k, v in o.items() if v is not None}
                for j, o in (e.get("layers") or {}).items()}
        lays = {j: o for j, o in lays.items() if o}
        if lays:
            e["layers"] = lays
        else:
            e.pop("layers", None)
        if e:
            out[str(i)] = e
    return out


def _pick(opts, ts):
    """A time list's value for model time ts (s): its nearest time, or "" (the
    panel's / layout's) for None or a run without times."""
    vals = [v for v in opts.values() if v != ""]
    if ts is None or not vals:
        return ""
    return min(vals, key=lambda v: abs(v - float(ts)))


class FigureTree:
    # ------------------------------------------------------------ widgets
    def _build_tree(self):
        self.edits = {}  # str(panel) -> changes of that panel alone (panel_edit)
        self._tree_sel = 0
        self._tree_sig = None
        self.tree_head = pn.pane.HTML(margin=(4, 4, 2, 4), sizing_mode="stretch_width")
        self.tree_reset_all = pn.widgets.Button(name="Undo every panel's changes",
                                                button_type="default", button_style="outline",
                                                width=220)
        self.tree_reset_all.on_click(lambda e: self._tree_reset(None))
        self.tree_list = pn.Column(sizing_mode="stretch_width", margin=0)
        self.tree_detail = pn.Column(sizing_mode="stretch_width", margin=(4, 0))
        self.tree_tab = pn.Column(
            _hint("The figure panel by panel. Pick a panel to change it alone: its run, "
                  "time, height and title, and its layers (a layer can come from a run and "
                  "time of its own, e.g. the other run's contours over this run's fill), "
                  "or add layers to this panel only. <b>Panels</b> and <b>Layers</b> still "
                  "lay out every panel; what you change here stays on top (✎)."),
            self.tree_head, self.tree_list, self.tree_detail,
            sizing_mode="stretch_width")

    # ------------------------------------------------------------ the list
    def _tree_spec(self):
        try:
            return self.collect()
        except Exception:  # noqa: BLE001  (incomplete settings: the last good spec)
            return self.spec

    def _tree_sync(self, force=False):
        """Show the current panels (the selected one's settings again when what it
        draws changed, or force)."""
        if not hasattr(self, "tree_list"):
            return
        s = self._tree_spec()
        n = figdraw.npanels(s)
        names = self._run_names()
        rows = []
        for i in range(n):
            label, ok = self._tree_label(s, i, names)
            b = pn.widgets.Button(name=label, button_type="primary" if i == self._tree_sel
                                  else "light", disabled=not ok, align="start",
                                  sizing_mode="stretch_width", margin=(1, 0),
                                  stylesheets=[":host .bk-btn {text-align:left}"])
            b.on_click(lambda e, i=i: self._tree_pick(i))
            rows.append(b)
        self.tree_list.objects = rows or [pn.pane.HTML(
            '<div class="cv-empty">No panels.</div>')]
        changed = sum(1 for k in clean_edits(self.edits) if int(k) < n)
        multi = self._multi_part() if hasattr(self, "_multi_part") else False
        self.tree_head.object = (
            f'<div class="cv-hint"><b>{n}</b> panel{"s" if n != 1 else ""}'
            + (f" in part {self.part_i + 1} of {len(self.parts)} (switch parts in "
               "<b>Panels → Parts</b>)" if multi else "")
            + (f" · {changed} changed here" if changed else "") + "</div>")
        self.tree_reset_all.visible = bool(changed)
        if self._tree_sel >= n:
            self._tree_sel = 0
        sig = json.dumps([s["kind"], n, self._tree_sel, self._tree_base(s, self._tree_sel),
                          fg.panel_ref(s, self._tree_sel) if s["kind"] in ("plan", "xsec")
                          else None, names], default=float, sort_keys=True)
        if force or sig != self._tree_sig:
            self._tree_sig = sig
            self._tree_show(s)

    def _tree_label(self, s, i, names):
        """(button text of panel i, whether it has anything to show)."""
        letter = figdraw.panel_letter(i, "{a}")
        kind = s["kind"]
        mark = " ✎" if clean_edits(self.edits).get(str(i)) else ""
        title = (figdraw.panel_edit(s, i).get("title") or
                 ((s.get("titles") or [])[i] if i < len(s.get("titles") or []) else ""))
        tail = f" · “{title}”" if title else ""
        rn = {k: n.split(". ", 1)[-1] for n, k in names.items()}
        if kind in ("plan", "xsec"):
            ref = fg.panel_ref(s, i)
            if ref is None:
                return f"{letter}  (empty)", False
            k, ts = ref
            lays = [lay for lay in figdraw.spec_layers(s, i) if lay.get("on", True)]
            what = ", ".join(self._layer_name(lay) for lay in lays[:3]) + \
                (f" +{len(lays) - 3}" if len(lays) > 3 else "")
            z = figdraw.panel_edit(s, i).get("z")
            zs = s.get("panel_z") or []
            if z is None and s.get("vary") == "height" and i < len(zs):
                z = zs[i]
            zt = f" · {float(z):g} km" if z is not None else ""
            return (f"{letter}  {'Plan' if kind == 'plan' else 'Section'} · "
                    f"{rn.get(k, k + 1)} · {ts / 60:g} min{zt} — {what or 'no layers'}"
                    f"{tail}{mark}", True)
        if kind == "th":
            ref = figdraw.series_ref(s, i)
            if ref is None:
                return f"{letter}  (empty)", False
            e = s["series"][ref[1]]
            return f"{letter}  Time-height · {rn.get(ref[0], ref[0] + 1)} · " \
                   f"{e.get('label', '')}{tail}{mark}", True
        ents = s.get(figdraw.ENTRIES[kind]) or []
        mine = [e for e in ents if int(e.get("panel", 0)) == i]
        what = "; ".join(str(e.get("label") or "") or self._entry_name(e, n) for n, e in
                         enumerate(mine[:3])) + (f" +{len(mine) - 3}" if len(mine) > 3 else "")
        head = {"line": "Time series", "sounding": "Sounding", "dist": "Distribution"}[kind]
        return f"{letter}  {head} — {what or 'nothing yet'}{tail}{mark}", True

    def _entry_name(self, e, n):
        """A line, sounding or distribution without a label of its own: its field
        (distributions), else its number."""
        f = (e.get("recipe") or {}).get("field") if "where" not in e else None
        return self.fields[f].label if f in self.fields else f"#{n + 1}"

    def _layer_name(self, lay):
        t = lay["type"]
        if lay.get("field") in self.fields:
            return f"{TYPE_LABEL.get(t, t)} {self.fields[lay['field']].label}"
        return TYPE_LABEL.get(t, t)

    def _tree_pick(self, i):
        self._tree_sel = i
        self._tree_sync(force=True)

    def _tree_base(self, s, i):
        """Panel i's layers as laid out, with its own height (not its layers' own
        changes, nor its extra layers)."""
        if s["kind"] not in ("plan", "xsec"):
            return []
        e = figdraw.panel_edit(s, i)
        form = figdraw.spec_layers(dict(s, edits={}), i)
        return figdraw.edited_layers(form, {"z": e.get("z")} if e.get("z") is not None
                                     else {})

    def _tree_edit(self, i):
        return self.edits.setdefault(str(i), {})

    def _tree_reset(self, i):
        if i is None:
            self.edits = {}
        else:
            self.edits.pop(str(i), None)
        self._tree_sync(force=True)
        self.request()

    def _tree_changed(self):
        """A change in the tree: re-render, and show the panel buttons again."""
        self._tree_sync()
        self.request()

    # ------------------------------------------------------------ one panel
    def _tree_show(self, s):
        i = self._tree_sel
        if i >= figdraw.npanels(s):
            self.tree_detail.objects = []
            return
        e = figdraw.panel_edit(s, i)
        letter = figdraw.panel_letter(i, "{a}")
        title = pn.widgets.TextInput(name="Title (blank: as laid out)",
                                     value=e.get("title") or "",
                                     placeholder=((s.get("titles") or [])[i]
                                                  if i < len(s.get("titles") or []) else ""))

        def on_title(ev):
            self._tree_edit(i)["title"] = ev.new if ev.new.strip() else None
            self._tree_changed()

        title.param.watch(on_title, "value")
        axes = s.get("axes") or {}
        labels = [self._tree_axis_label(i, e, k, axes.get(k) or "")
                  for k in ("xlabel", "ylabel")]
        reset = pn.widgets.Button(name=f"Undo panel {letter}'s changes",
                                  button_type="default", button_style="outline")
        reset.on_click(lambda ev: self._tree_reset(i))
        reset.visible = bool(clean_edits(self.edits).get(str(i)))
        head = pn.pane.HTML(f"<b>Panel {letter}</b>", margin=(6, 4, 0, 4))
        objs = [head]
        if s["kind"] in ("plan", "xsec"):
            objs += self._tree_map_panel(s, i, e, title, labels)
        else:
            objs += [_grid((title, 2)), _grid(*labels)]
            objs += self._tree_entries(s, i)
            if s["kind"] in figdraw.LEGEND_OPTS:
                objs += self._tree_legend(s, i, e)
        objs += [reset, self.tree_reset_all]
        self.tree_detail.objects = objs

    def _tree_map_panel(self, s, i, e, title, labels):
        names = self._run_names()
        ref = figdraw.form_ref(s, i)
        run = pn.widgets.Select(name="Run", options={LAYOUT: -1} | names,
                                value=int(e["run"]) if e.get("run") is not None and
                                int(e["run"]) in names.values() else -1)
        k = ref[0] if run.value == -1 else run.value
        topts = {LAYOUT: ""} | self._time_opts(k)
        time = pn.widgets.Select(name="Time", options=topts,
                                 value=_pick(topts, e.get("time_s")))
        z = pn.widgets.TextInput(name="Height (km; blank: as laid out)",
                                 value="" if e.get("z") is None else f"{float(e['z']):g}",
                                 placeholder="e.g. 1")
        z.visible = s["kind"] == "plan"

        def on_run(ev):
            self._tree_edit(i)["run"] = None if ev.new == -1 else int(ev.new)
            kk = ref[0] if ev.new == -1 else ev.new
            o = {LAYOUT: ""} | self._time_opts(kk)
            cur = time.value
            hold, self._hold = self._hold, True
            try:
                time.options = o
                time.value = _pick(o, None if cur == "" else cur)
            finally:
                self._hold = hold
            if time.value != cur:
                self._tree_edit(i)["time_s"] = None if time.value == "" else float(time.value)
            self._tree_changed()

        def on_time(ev):
            if self._hold:
                return
            self._tree_edit(i)["time_s"] = None if ev.new == "" else float(ev.new)
            self._tree_changed()

        def on_z(ev):
            txt = ev.new.strip()
            try:
                val = float(txt) if txt else None
            except ValueError:
                self._msg(f"Height of panel {figdraw.panel_letter(i, '{a}')}: "
                          f"“{txt}” is not a number", True)
                return
            self._tree_edit(i)["z"] = val
            self._tree_changed()
            self._tree_sync(force=True)  # (its layers' heights follow)

        run.param.watch(on_run, "value")
        time.param.watch(on_time, "value")
        z.param.watch(on_z, "value")
        objs = [_grid(run, time, z), _grid((title, 3)), _grid(*labels)]
        base = self._tree_base(s, i)
        objs.append(pn.pane.HTML("<b>Layers</b>", margin=(8, 4, 0, 4)))
        if not base:
            objs.append(_hint("No layers laid out (<b>Layers</b> tab); add one to this "
                              "panel below."))
        for j, lay in enumerate(base):
            objs.append(self._tree_layer(s, i, j, lay, extra=False))
        for j, lay in enumerate(e.get("extra") or []):
            objs.append(self._tree_layer(s, i, j, lay, extra=True))
        add = pn.widgets.Select(name="Add a layer to this panel only",
                                options={"": ""} | ADD, value="")

        def on_add(ev):
            if not ev.new:
                return
            field = {"fill": "dbz", "contour": "winterp", "shade": "winterp"}.get(ev.new)
            if field is not None and field not in self.fields:
                field = next(iter(self.fields.defs))
            lay = fg.layer_defaults(ev.new, self.fields, field, 1.0)
            if ev.new == "vectors" and s["kind"] == "xsec":
                lay.update(spacing=0.75, scale=400.0, width=0.0015)
            self._tree_edit(i).setdefault("extra", []).append(lay)
            self._tree_changed()
            self._tree_sync(force=True)

        add.param.watch(on_add, "value")
        objs.append(_grid(add))
        return objs

    def _tree_layer(self, s, i, j, base, extra):
        """The card of layer j of panel i: as laid out (base) with this panel's changes,
        or (extra) a layer of this panel only; its run and time above its settings."""
        e = self._tree_edit(i)
        if extra:
            def own():
                return e["extra"][j]
            lay = {k: v for k, v in own().items() if k not in OWN_KEYS}
        else:
            def own():
                return e.setdefault("layers", {}).setdefault(str(j), {})
            o = (e.get("layers") or {}).get(str(j)) or {}
            lay = dict(base, **{k: v for k, v in o.items() if k not in OWN_KEYS})
        src = own() if extra else ((e.get("layers") or {}).get(str(j)) or {})
        names = self._run_names()
        ref = fg.panel_ref(s, i)

        def changed():
            new = {k: v for k, v in card.collect().items()
                   if k not in OWN_KEYS + ("panels",)}
            if extra:
                keep = {k: own()[k] for k in OWN_KEYS if k in own()}
                e["extra"][j] = dict(new, **keep)
            else:
                o = own()
                for k in list(o):
                    if k not in OWN_KEYS:
                        del o[k]
                o.update({k: v for k, v in new.items() if base.get(k) != v})
            self._tree_changed()

        card = LayerCard(_PanelEditor(self, s["kind"], changed), lay,
                         collapsed=True)
        card.w["panels"].visible = False
        if "z_fixed" in card.w:
            card.w["z_fixed"].visible = False
        card.up.visible = card.down.visible = False
        if extra:
            def remove(ev):
                del e["extra"][j]
                self._tree_changed()
                self._tree_sync(force=True)
            card.rm.on_click(remove)
            card.rm.description = "Remove this layer (of this panel only)"
        else:
            card.rm.name, card.rm.description = "↺", "Undo this layer's changes here"

            def undo(ev):
                (e.get("layers") or {}).pop(str(j), None)
                self._tree_changed()
                self._tree_sync(force=True)
            card.rm.on_click(undo)
            card.rm.visible = bool(src)
        run = pn.widgets.Select(name="Run", options={PANELS: -1} | names,
                                value=int(src["run"]) if src.get("run") is not None and
                                int(src["run"]) in names.values() else -1)
        k = ref[0] if run.value == -1 else run.value
        topts = {PANELS: ""} | self._time_opts(k)
        time = pn.widgets.Select(name="Time", options=topts,
                                 value=_pick(topts, src.get("time_s")))
        lock = _chk("Keep this time in animations", bool(src.get("time_lock")))
        lock.visible = time.value != ""

        def set_own(key, val):
            o = own()
            if val is None:
                o.pop(key, None)
            else:
                o[key] = val
            lock.visible = time.value != ""
            self._tree_changed()

        def on_run(ev):
            kk = ref[0] if ev.new == -1 else ev.new
            o = {PANELS: ""} | self._time_opts(kk)
            cur = time.value
            hold, self._hold = self._hold, True
            try:
                time.options = o
                time.value = _pick(o, None if cur == "" else cur)
            finally:
                self._hold = hold
            if time.value != cur:
                own()["time_s"] = None if time.value == "" else float(time.value)
            set_own("run", None if ev.new == -1 else int(ev.new))

        def on_time(ev):
            if not self._hold:
                set_own("time_s", None if ev.new == "" else float(ev.new))

        run.param.watch(on_run, "value")
        time.param.watch(on_time, "value")
        lock.param.watch(lambda ev: set_own("time_lock", True if ev.new else None), "value")
        card.body.objects = [_grid(run, time, lock)] + list(card.body.objects)
        if extra:
            card.body.objects = [_hint("A layer of this panel only.")] + \
                list(card.body.objects)
        return card.panel

    def _tree_axis_label(self, i, e, k, laid):
        """Panel i's own x or y axis label (k "xlabel" / "ylabel"; blank: Style's,
        `laid`; a space: none)."""
        w = pn.widgets.TextInput(
            name=f"{k[0]} label (blank: as laid out)", value=e.get(k) or "",
            placeholder=laid, description="This panel's alone; a space: no label")

        def on_label(ev):
            self._tree_edit(i)[k] = ev.new or None
            self._tree_changed()

        w.param.watch(on_label, "value")
        return w

    def _tree_legend(self, s, i, e):
        """A time-series, sounding or distribution panel's own legend: shown or not
        (yes: also kept beside a figure legend), where (and at which anchor), its columns
        and frame (blank: as laid out in Layers; a sounding's are both its skew-T
        legend's and its hodograph key's)."""
        lg = e.get("legend") or {}
        yes_no = {LAYOUT: "", "Yes": "yes", "No": "no"}

        def tri(v):
            return "" if v is None else ("yes" if v else "no")

        on = pn.widgets.Select(name="Legend", options=yes_no, value=tri(lg.get("on")))
        loc = pn.widgets.Select(name="At", options={LAYOUT: ""} | {k: k for k in
                                                                   ["best"] + LOCS},
                                value=lg.get("loc") or "")
        anchor = pn.widgets.TextInput(
            name="Anchor x, y (blank: none)", placeholder="1.02, 1",
            value=_xy_text(lg.get("anchor")),
            description="Puts the legend's 'At' corner at this point, in fractions of the "
                        "panel; below 0 or above 1 is outside it")
        ncol = pn.widgets.IntInput(name="Columns (0: as laid out)", start=0, end=8,
                                   value=int(lg.get("ncol") or 0))
        frame = pn.widgets.Select(name="Frame", options=yes_no, value=tri(lg.get("frame")))

        def changed(*ev):
            new = {"on": None if not on.value else on.value == "yes",
                   "loc": loc.value or None, "anchor": _xy(anchor.value),
                   "ncol": int(ncol.value or 0) or None,
                   "frame": None if not frame.value else frame.value == "yes"}
            new = {k: v for k, v in new.items() if v is not None}
            if new:
                self._tree_edit(i)["legend"] = new
            else:
                self._tree_edit(i).pop("legend", None)
            self._tree_changed()

        for w in (on, loc, anchor, ncol, frame):
            w.param.watch(changed, "value")
        return [pn.pane.HTML("<b>Legend of this panel</b>", margin=(8, 4, 0, 4)),
                _grid(on, loc, anchor, ncol, frame),
                _hint("Settings for this panel alone (a sounding's: its skew-T legend and "
                      "its hodograph key). With <b>Style → Legend</b> on the figure, the "
                      "panels' legends are gathered into one instead; <i>Legend: Yes</i> "
                      "keeps this one as well (and is not gathered unless listed).")]

    def _tree_entries(self, s, i):
        """A time-series, sounding, distribution or time-height panel: what it draws
        (set in the Layers tab, where each line, sounding and distribution has its own
        run, time and panel)."""
        kind = s["kind"]
        if kind == "th":
            return [_hint("A time-height panel draws its series (<b>Layers</b>): its run "
                          "and series follow from its place in the grid.")]
        ents = s.get(figdraw.ENTRIES[kind]) or []
        mine = [(n, e) for n, e in enumerate(ents) if int(e.get("panel", 0)) == i]
        what = {"line": "line", "sounding": "sounding", "dist": "distribution"}[kind]
        names = {k: n for n, k in self._run_names().items()}
        rows = []
        for n, ent in mine:
            if kind == "line":
                runs = ent.get("runs")
                src = "every run" if runs is None else ", ".join(
                    names.get(int(k), str(k)) for k in runs) or "no run"
            else:
                src = (f"{names.get(int(ent.get('run', 0)), '')} · "
                       f"{float(ent.get('time_s', 0)) / 60:g} min")
            name = ent.get("label") or (self._entry_name(ent, n) if kind == "dist" else what)
            rows.append(f"<li><b>{n + 1}.</b> {name} — {src}</li>")
        go = pn.widgets.Button(name=f"Edit the {what}s (Layers)", button_type="default",
                               button_style="outline")
        go.on_click(lambda ev: setattr(self.tabs, "active", 1))
        return [pn.pane.HTML(f"<ul style='margin:4px 0 4px 18px;padding:0'>"
                             f"{''.join(rows)}</ul>" if rows else
                             f'<div class="cv-empty">No {what}s in this panel: give one '
                             f'this panel number in <b>Layers</b>.</div>',
                             sizing_mode="stretch_width"),
                _hint(f"Each {what} has its own run{'' if kind == 'line' else ' and time'} "
                      "and panel number; several in one panel share its axes (e.g. two "
                      "runs' soundings on one skew-T, or one field at two times)."), go]

    def _tree_collect(self):
        return copy.deepcopy(clean_edits(self.edits))
