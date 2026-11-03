"""Figure editor: the spec and the widgets (set_spec puts a spec into the widgets,
collect reads it back) and undo / redo.

A mixin of the FigureEditor (figures/editor.py)."""

import json

from . import draw as figdraw, settings, spec as fg
from .cards import GRID_DIMS, NONE, _num, _plain, kept_cards
from .times import _heights
from ..viewer.ui import held


class FigureSpecIO:
    """spec <-> widgets, and the undo history."""

    # ------------------------------------------------------------ spec <-> widgets
    def set_spec(self, spec):
        """Show `spec` in the widgets (one re-render at the end)."""
        self.spec = spec = fg.normalize(spec, self.run, self._own_track())
        self.edits = json.loads(json.dumps(spec.get("edits") or {}))  # (the panel tree's)
        self.msg.object = ""
        self._started = True  # (no quick start over a figure made from the viewer)
        self._made = True  # (not the example: __init__ takes this back)
        self.quick.hide()
        self._auto_size = bool(spec.get("size_auto", False))  # until set by hand
        # (undo: cards list runs and their times, so they stay only if those do)
        self._same_runs = self._undoing and self.time_match.value == \
            spec.get("time_match", "time") and _plain(self._runs_collect()) == _plain(spec["runs"])
        with held(self):
            s = spec
            self._leg_block = ""  # (the panel legend's widgets: this spec's, not to be kept)
            self.time_match.value = s.get("time_match", "time")  # (the rows' time zeros show it)
            self._build_runs(s["runs"])
            self.kind.value = s["kind"]
            self._legend_follow()
            self.g_rows.options = self.g_cols.options = dict(GRID_DIMS)  # (all, then the kind's)
            self.g_rows.value, self.g_cols.value = figdraw.grid_axes(s)
            self.gg_runs.value = figdraw.grid_runs(s)
            self.run_sel.value = min(int(s.get("run", 0)), len(s["runs"]) - 1)
            if s["kind"] != "scene":  # (one picture: the grid stays for the other kinds)
                self.rows.value, self.cols.value = int(s["rows"]), int(s["cols"])
            self._grid_grown = None  # (the spec's grid is the one set)
            self.width.value, self.height.value = float(s["size"][0]), float(s["size"][1])
            self.size_preset.value = ""
            self._let_auto = bool(s["letters"].get("auto"))  # (follows the panels until set by hand)
            settings.load(self, s, ("legend.where",))  # (the legend's places follow it)
            self._show_legend()
            settings.load(self, s)
            for w, v in zip((self.box_x0, self.box_x1, self.box_y0, self.box_y1),
                            s["domain"].get("box") or [None] * 4):
                w.value = v
            self.xlabel.placeholder = "blank: as each section runs" \
                if s.get("kind") == "xsec" else ""
            self.part_share.value = _num(s.get("share"))
            self.code_plain.value = self.code.value
            self.sec_cards = self._sec_cards(  # (a plan view's: a panel each)
                [dict({"panel": k}, **e) for k, e in enumerate(fg.sections(s))])
            self._show_sections()
            layers, card_of = self._split_pf(s)
            self._build_cards(layers)
            for w, block in ((self.ck_layer, "contour_key"), (self.ex_layer, "extremes")):
                j = card_of(s.get(block, {}).get("layer", -1))
                w.value = j if j in w.options.values() else -1
            self._refresh_time1(float(s["time_s"]) if s.get("time_s") is not None
                                else self._shown_s(), snap=False)
            self._build_times([NONE if t is None else float(t) for t in s["times_s"]],
                              extend=False, snap=False)
            self._build_pf(s.get("panel_fills", []))
            self.pz_mode.value = s.get("panel_zmode", "height")
            self.pz.value = ", ".join(f"{float(z):g}" for z in s.get("panel_z") or [1, 3, 6])
            self._build_titles(s.get("titles", []), s.get("row_titles", []))
            self.ser_cards = self._entry_cards(self.ser_cards, s.get("series", []), self._ser_card)
            self.snd_cards = self._entry_cards(self.snd_cards, s.get("soundings", []), self._snd_card)
            self.dist_cards = self._entry_cards(self.dist_cards, s.get("dists", []), self._dist_card)
            self.prof_cards = self._entry_cards(self.prof_cards, s.get("profiles", []), self._prof_card)
            self.joint_cards = self._entry_cards(self.joint_cards, s.get("joints", []), self._joint_card)
            self.azim_cards = self._entry_cards(self.azim_cards, s.get("azims", []), self._azim_card)
            self.table_cards = self._entry_cards(self.table_cards, s.get("tables", []), self._table_card)
            self.ann_rows = [self._ann_row(a) for a in s.get("annotations", [])]
            self._scene_set(fg.scene3d_of(s))
            self._show_series()
            self._show_soundings()
            self._show_dists()
            self._show_profiles()
            self._show_joints()
            self._show_azims()
            self._show_tables()
            self._show_anns()
        self._show_region()
        self._on_kind(render_=False)
        self._show_vary()
        self._fit_axes()  # (rows / columns a list sets cannot be typed)
        self._panel_was = self._panel_layout()  # (the numbers the spec's edits are of)
        self._show_cbar()
        self._show_storm()
        self._show_code()
        self._set_dl_name()
        self._tree_sync(force=True)
        self.request(delay=False)

    def _entry_cards(self, old, ents, make):
        """The cards of a list of entries: new ones, but for undo (kept_cards)."""
        if self._undoing:
            return kept_cards(old, ents, make, self._same_runs)
        return [make(e) for e in ents]

    def _split_pf(self, s):
        """(Layers cards' layers, spec layer index -> card index (-1: none)) of spec s:
        a 'field' figure's first fill is the panels' fill (self._pf_base), not a card."""
        layers = list(s["layers"])
        self._pf_base, k = None, None
        if "fields" in figdraw.grid_axes(s):
            k = next((j for j, lay in enumerate(layers) if lay["type"] == "fill"), None)
            self._pf_base = layers.pop(k) if k is not None else self._pf_fill()

        def card_of(j):
            j = int(j)
            return -1 if j < 0 or j == k else j - 1 if k is not None and j > k else j
        return layers, card_of

    def collect(self):
        """The spec of the current widget values."""
        s = dict(self.spec)
        pf = [dict(self._pf_base, on=True)] if self._pf_base is not None else []  # (layer 0)
        tv = self._time_values()
        while tv and tv[-1] == NONE:
            tv.pop()
        times_s = [None if t == NONE else float(t) for t in tv]
        titles = [w.value for w in self.title_ws]
        while titles and not titles[-1].strip():
            titles.pop()
        row_titles = [w.value for w in self.row_ws]
        while row_titles and not row_titles[-1].strip():
            row_titles.pop()
        scene = self.kind.value == "scene"
        rd, cd = ("none", "none") if self.kind.value == "xsec" else (  # (a card per panel)
            self.g_rows.value, self.g_cols.value)
        s.update(
            kind=self.kind.value, vary=fg.legacy_vary(rd, cd),
            grid=dict(rows=rd, cols=cd, runs=self._grid_runs() if self._uses("runs") else []),
            rows=1 if scene else int(self.rows.value or 1),
            cols=1 if scene else int(self.cols.value or 1),
            size=[float(self.width.value or 8), float(self.height.value or 6)],
            size_auto=bool(self._auto_size),
            times=[None if t is None else self._index_of(t) for t in times_s],
            time=self._index_of(float(self.time1.value), one=True),
            times_s=times_s, time_s=float(self.time1.value),
            runs=self._runs_collect(), run=int(self.run_sel.value or 0),
            runs_as="cards" if self.kind.value == "th" else "rows",
            panels=[],
            layers=pf + [c.collect() for c in self.cards],
            panel_fills=[self._pf_collect(c) for c in self.pf_cards],
            panel_z=_heights(self.pz.value), panel_zmode=self.pz_mode.value,
            share=_num(self.part_share.value), place=self._part_place(),
            titles=titles, row_titles=row_titles)
        settings.store(self, s)
        s["letters"]["auto"] = self._let_auto
        s.pop("time_match", None)
        if self.time_match.value == "output":
            s["time_match"] = "output"
        s["sections"] = [c.collect() for c in self.sec_cards] or fg.sections(s)
        s["series"] = [c.collect() for c in self.ser_cards]
        s["soundings"] = [c.collect() for c in self.snd_cards]
        s["dists"] = [c.collect() for c in self.dist_cards]
        s["profiles"] = [c.collect() for c in self.prof_cards]
        s["joints"] = [c.collect() for c in self.joint_cards]
        s["azims"] = [c.collect() for c in self.azim_cards]
        s["tables"] = [c.collect() for c in self.table_cards]
        s["annotations"] = [r.collect() for r in self.ann_rows]
        if self.kind.value == "scene":  # (other figures: no 3D block in their spec)
            s["scene3d"] = self._scene_collect()
        else:
            s.pop("scene3d", None)
        s["extremes"]["layer"] = _spec_index(self.ex_layer.value, len(pf))
        s["contour_key"]["layer"] = _spec_index(self.ck_layer.value, len(pf))
        self._legend_store(s)
        s["edits"] = self._tree_collect()
        if self._let_auto:
            on = self._multi_part() or figdraw.npanels(s) > 1
            s["letters"]["on"] = on
            if self.let_on.value != on:
                with held(self):
                    self.let_on.value = on
        self.spec = s
        return s

    # ------------------------------------------------------------ undo / redo
    def _remember(self, spec):
        """Record a rendered figure (spec: collect_all, so adding, removing and changing
        parts can be undone): the one before it goes on the undo list."""
        j = json.dumps(spec, sort_keys=True, default=float)
        if self._last is not None and j != self._last[0] and self.own_figure(j):
            self._autosave(spec)
        if self._restoring or self._last is None:
            self._restoring = False
        elif j != self._last[0]:
            self._hist = (self._hist + [self._last])[-50:]
            self._future = []
        self._last = (j, self.part_i)  # (switching parts alone is no change)
        self._show_history()

    def _show_history(self):
        self.undo_btn.disabled = not self._hist
        self.redo_btn.disabled = not self._future

    def undo(self):
        if not self._hist:
            return
        self._future.append(self._last)
        self._restore(self._hist.pop())

    def redo(self):
        if not self._future:
            return
        self._hist.append(self._last)
        self._restore(self._future.pop())

    def _restore(self, state):
        j, part = state
        self._last, self._restoring = state, True
        self.style_note.object = ""
        self._undoing = True
        try:
            self.set_parts(json.loads(j), part)
        finally:
            self._undoing = False
        if not self.auto.value:  # (no render to record it)
            self._remember(self.collect_all())


def _spec_index(card, pf):
    """The spec layer index of Layers card `card` (-1: none) when the spec's layers
    start with pf (0 or 1) panel fills."""
    card = int(card)
    return card + pf if card >= 0 else -1
