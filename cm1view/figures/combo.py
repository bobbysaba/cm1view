"""Figure editor: figures made of parts.  Each part is a figure of its own (its own kind
of panels, runs, layers and style: e.g. plan views beside soundings, or a plan view
with its A–B line above the cross-section; the plan-view and section parts share one
list of cross-sections), and the parts are drawn side by side, stacked or anywhere on
a grid of their own as one figure (figdraw: kind "combo").  The editor shows one part
at a time; the preview, saving and the download take the whole figure.

A mixin of the FigureEditor (figures/editor.py)."""

import json
import math

import panel as pn

from . import draw as figdraw, spec as fg
from .render import panel_name  # noqa: F401  (combo.panel_name, as before)
from .cards import _auto, _chk, _grid, _hint, _num, _section
from .kinds import KIND_NAMES
from ..viewer.ui import held


class FigureCombo:
    parts = []  # the parts' specs (the shown one: as when it was last shown); [] or one
    part_i = 0  # the part in the widgets

    def _build_combo(self):
        self.part_sel = pn.widgets.RadioButtonGroup(options={"Part 1": 0}, value=0,
                                                    button_type="light",
                                                    button_style="outline")
        self.part_add = pn.widgets.Button(
            name="+ Add a part", button_type="primary", button_style="outline", height=32,
            description="A copy of this part, to change into another kind of panels "
                        "(Panels show, in the Panels tab)")
        self.part_rm = pn.widgets.Button(name="Remove this part", button_type="light",
                                         button_style="outline", height=32)
        self.part_arr = pn.widgets.Select(name="Parts are", options={
            "Side by side": "row", "Stacked": "col", "Custom grid": "grid"})
        self.part_title = pn.widgets.TextInput(name="Title of the whole figure (blank: none)")
        self.part_w = _auto("Figure width (in)", start=1.0,
                            description="Blank: the parts' widths together (side by side, grid)")
        self.part_h = _auto("Figure height (in)", start=1.0,
                            description="Blank: the tallest part's (side by side); the rows' together (grid)")
        self.part_share = _auto(
            "This part's share (0–1)", start=0.02, end=1.0, step=0.05,
            description="Of the figure's width (side by side) or height (stacked). Blank: "
                        "by its size, from what the other parts leave")
        self.part_cb = _chk("One colorbar for the whole figure (the first fill's, styled "
                            "as this part's)", False)
        self.part_note = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 4))
        self.part_size = _grid(self.part_w, self.part_h, self.part_share, (self.part_cb, 3))
        self._build_part_grid()
        self.part_sel.param.watch(lambda e: self._switch_part(e.new), "value")
        self.part_add.on_click(lambda e: self._add_part())
        self.part_rm.on_click(lambda e: self._remove_part())
        for w in (self.part_arr, self.part_title, self.part_w, self.part_h, self.part_share,
                  self.part_cb):
            w.param.watch(lambda e: self.request(), "value")
        self.parts_sec = _section(
            "Figure parts", _hint(
                "A figure can have parts with different kinds of panels, e.g. plan views "
                "beside soundings. Each part has its own panels, runs, layers and style; "
                "edit one at a time (pick it here). The parts keep their own sizes: side by "
                "side, the figure is as wide as the parts together, unless you give it a "
                "size (the parts then keep their shares of it). Parts are → Custom grid "
                "puts each part in cells of its own, e.g. a plan view on the left with a "
                "section above a sounding on its right. Panel letters run on from part "
                "to part on the figure; on a part's cards they count from a in that part."),
            self.part_sel, _grid(self.part_add, self.part_rm, self.part_arr),
            self.part_grid_box, self.part_title, self.part_size, self.part_note)
        self._show_parts()

    def _build_part_grid(self):
        """The custom grid's widgets: its size, this part's place on it, and a map."""
        def num(name, end=12, start=1, value=1, description=None):
            return pn.widgets.IntInput(name=name, start=start, end=end, value=value,
                                       description=description)
        self.pg_rows, self.pg_cols = num("Grid rows"), num("Grid columns")
        self.pg_row = num("This part's row", description="Counted from the top")
        self.pg_col = num("This part's column", description="Counted from the left")
        self.pg_rs = num("Rows it spans")
        self.pg_cs = num("Columns it spans")
        self.pg_ws = pn.widgets.TextInput(
            name="Column widths", placeholder="by the parts' sizes",
            description="Relative, one for each column, e.g. 2, 1")
        self.pg_hs = pn.widgets.TextInput(
            name="Row heights", placeholder="by the parts' sizes",
            description="Relative, one for each row, e.g. 1, 1")
        self.pg_map = pn.pane.HTML(sizing_mode="stretch_width", margin=(4, 6))
        for w in (self.pg_rows, self.pg_cols, self.pg_ws, self.pg_hs):
            w.param.watch(lambda e: self._grid_edited(), "value")
        for w in (self.pg_row, self.pg_col, self.pg_rs, self.pg_cs):
            w.param.watch(lambda e: self._place_edited(), "value")
        self.part_arr.param.watch(lambda e: self._arrange_changed(e.new), "value")
        self.part_grid_box = pn.Column(
            _grid(self.pg_rows, self.pg_cols, self.pg_row, self.pg_col, self.pg_rs,
                  self.pg_cs, self.pg_ws, self.pg_hs, n=2),
            self.pg_map, sizing_mode="stretch_width", margin=0)

    # ------------------------------------------------------------ the parts
    def _multi_part(self):
        return len(self.parts) > 1

    def _part_place(self):
        """This part's place on the custom grid, as a part's spec has it."""
        return self.parts[self.part_i].get("place") if self._multi_part() else None

    def _grid_size(self):
        """spec["part_grid"] as the widgets have it."""
        return dict(rows=int(self.pg_rows.value or 1), cols=int(self.pg_cols.value or 1),
                    widths=_ratios(self.pg_ws.value), heights=_ratios(self.pg_hs.value))

    def _arrange_changed(self, how):
        """The custom grid's widgets show or go.  A first custom grid: as square as the
        parts allow, the parts in reading order."""
        if self._hold or not self._multi_part():
            return
        if how == "grid" and not any(p.get("place") for p in self.parts):
            n = len(self.parts)
            cols = math.ceil(math.sqrt(n))
            with held(self):
                self.pg_rows.value, self.pg_cols.value = math.ceil(n / cols), cols
        self._show_part_grid()

    def _grid_edited(self):
        if not self._hold:
            self._show_part_grid()
            self.request()

    def _place_edited(self):
        if self._hold or not self._multi_part():
            return
        self.parts[self.part_i]["place"] = [
            int(self.pg_row.value or 1) - 1, int(self.pg_col.value or 1) - 1,
            int(self.pg_rs.value or 1), int(self.pg_cs.value or 1)]
        self._show_part_grid()
        self.request()

    def _show_part_grid(self):
        """The custom grid's widgets as the parts are: every part gets a place on the grid
        (one left without any, or outside a smaller grid, moves in here)."""
        on = self._multi_part() and self.part_arr.value == "grid"
        self.part_grid_box.visible = on
        self.part_share.visible = self._multi_part() and not on
        if not on:
            return
        g = figdraw.grid_layout(self.parts, self._grid_size())
        for p, place in zip(self.parts, g["places"]):
            p["place"] = list(place)
        r, c, rs, cs = g["places"][self.part_i]
        with held(self):
            self.pg_rows.value, self.pg_cols.value = g["rows"], g["cols"]
            self.pg_row.value, self.pg_col.value = r + 1, c + 1
            self.pg_rs.value, self.pg_cs.value = rs, cs
        kinds = [p["kind"] for p in self.parts]
        kinds[self.part_i] = self.kind.value
        self.pg_map.object = _grid_map(g, kinds, self.part_i, self._grid_size())

    def _show_parts(self):
        multi = self._multi_part()
        kinds = [p["kind"] for p in self.parts] if multi else [self.kind.value]
        if multi:
            kinds[self.part_i] = self.kind.value
        opts = {f"Part {k + 1}: {KIND_NAMES.get(kd, kd)}": k for k, kd in enumerate(kinds)}
        with held(self):
            self.part_sel.options = opts
            self.part_sel.value = self.part_i if multi else 0
        self.part_sel.visible = self.part_rm.visible = self.part_arr.visible = \
            self.part_title.visible = self.part_size.visible = multi
        self._show_part_grid()
        self.parts_sec.title = (f"Figure parts ({len(self.parts)}: editing part "
                                f"{self.part_i + 1})" if multi else "Figure parts")

    def _switch_part(self, k):
        if self._hold or not self._multi_part() or k == self.part_i:
            return
        self.parts[self.part_i] = self.collect()
        share_sections(self.parts, self.parts[self.part_i])
        self.part_i = int(k)
        self.set_spec(json.loads(json.dumps(self.parts[self.part_i], default=float)))
        self._show_parts()

    def _add_part(self):
        cur = self.collect()
        if not self._multi_part():
            self.parts, self.part_i = [cur], 0
        self.parts[self.part_i] = cur
        new = json.loads(json.dumps(cur, default=float))
        new["share"] = new["place"] = None  # (its share follows its size until set)
        self.parts.append(new)
        self.part_i = len(self.parts) - 1
        self.set_spec(json.loads(json.dumps(new)))
        self._show_parts()
        self.part_note.object = ('<div class="cv-status">Part '
                                 f'{self.part_i + 1} starts as a copy of the part you were '
                                 'editing: change its panels here, or make it anew with '
                                 '“This part from …” above.</div>')

    def _remove_part(self):
        if not self._multi_part():
            return
        del self.parts[self.part_i]
        self.part_i = max(0, self.part_i - 1)
        spec = self.parts[self.part_i]
        if len(self.parts) == 1:
            self.parts, self.part_i = [], 0
        self.set_spec(json.loads(json.dumps(spec, default=float)))
        self._show_parts()
        self.part_note.object = ""

    def set_parts(self, spec, part=0):
        """Show a saved figure: its parts (a figure of parts; `part` in the widgets),
        else it alone."""
        if spec.get("kind") != "combo":
            self.parts, self.part_i = [], 0
            self.set_spec(spec)
            self._show_parts()
            return
        self.parts = list(spec["parts"])
        self.part_i = min(max(int(part), 0), len(self.parts) - 1)
        with held(self):
            self.part_arr.value = spec.get("arrange", "row")
            pg = spec.get("part_grid") or {}
            self.pg_rows.value = int(pg.get("rows") or 1)
            self.pg_cols.value = int(pg.get("cols") or 1)
            self.pg_ws.value = _ratio_text(pg.get("widths"))
            self.pg_hs.value = _ratio_text(pg.get("heights"))
            self.part_title.value = spec.get("suptitle", "")
            own = spec.get("size_set") or [None, None]
            self.part_w.value, self.part_h.value = _num(own[0]), _num(own[1])
            self.part_cb.value = (spec.get("colorbar") or {}).get("mode") == "figure"
        if len(self.parts) == 1:
            self.parts, self.part_i = [], 0
        self.set_spec(json.loads(json.dumps(spec["parts"][self.part_i], default=float)))
        self._show_parts()

    def collect_all(self):
        """The whole figure: this part's spec, or (several parts) a figure of parts."""
        cur = self.collect()
        if not self._multi_part():
            return cur
        parts = [cur if k == self.part_i else p for k, p in enumerate(self.parts)]
        share_sections(parts, cur)
        return combine(parts, self.part_arr.value, self.part_title.value, cur,
                       size=[_num(self.part_w.value), _num(self.part_h.value)],
                       one_colorbar=bool(self.part_cb.value), grid=self._grid_size())


def _ratios(text):
    """Relative sizes typed as "2, 1" ([2.0, 1.0]); blank or not numbers: None."""
    try:
        return [float(v) for v in str(text or "").replace(",", " ").split()] or None
    except ValueError:
        return None


def _ratio_text(values):
    return ", ".join(f"{float(v):g}" for v in values or [])


def _grid_map(g, kinds, current, typed):
    """A small picture of where the parts are on the grid (grid_layout's g), this part
    marked, with what is wrong with the grid under it."""
    def cell(r, c, rs, cs, style, text=""):
        return (f'<div style="grid-row:{r + 1}/span {rs};grid-column:{c + 1}/span {cs};'
                'display:flex;align-items:center;justify-content:center;overflow:hidden;'
                f'font-size:11px;text-align:center;border-radius:3px;{style}">{text}</div>')
    html = [cell(i, j, 1, 1, "border:1px dashed rgba(128,128,128,.45);")
            for i in range(g["rows"]) for j in range(g["cols"])]
    for k, (r, c, rs, cs) in enumerate(g["places"]):
        look = ("background:rgba(37,99,235,.28);border:2px solid #2563eb;font-weight:600;"
                if k == current else
                "background:rgba(128,128,128,.22);border:1px solid rgba(128,128,128,.8);")
        html.append(cell(r, c, rs, cs, look, f"{k + 1}: {KIND_NAMES.get(kinds[k], kinds[k])}"))
    notes = [f"Parts {a + 1} and {b + 1} overlap: give them different cells."
             for a, b in figdraw.grid_overlaps(g["places"])]
    if typed.get("widths") and len(typed["widths"]) != g["cols"]:
        notes.append(f"Column widths: give {g['cols']} numbers (until then, by the parts' sizes).")
    if typed.get("heights") and len(typed["heights"]) != g["rows"]:
        notes.append(f"Row heights: give {g['rows']} numbers (until then, by the parts' sizes).")
    note = "".join(f'<div class="cv-status">{n}</div>' for n in notes)
    return (f'<div style="display:grid;grid-template-columns:repeat({g["cols"]},1fr);'
            f'grid-auto-rows:34px;gap:2px;max-width:320px">{"".join(html)}</div>{note}')


def share_sections(parts, src):
    """The plan-view and section parts of a figure of parts take part src's list of
    cross-sections (when src is one of those kinds), in place: they share one list.  A
    section part of cards keeps its cards' runs, times and panels (the cards src has
    beyond its own: new panels, at its first card's run and time)."""
    if src.get("kind") not in ("plan", "xsec") or not src.get("sections"):
        return parts
    new = json.loads(json.dumps(src["sections"], default=float))
    for p in parts:
        if p is src or p.get("kind") not in ("plan", "xsec"):
            continue
        old = figdraw.xsec_cards(p) if src.get("kind") == "plan" else None
        if old is None:
            p["sections"] = json.loads(json.dumps(new))
            continue
        nxt = 1 + max(int(c.get("panel", 0)) for c in old)
        out = []
        for k, sec in enumerate(new):
            keys = {c: old[min(k, len(old) - 1)].get(c) for c in fg.CARD_KEYS}
            if k >= len(old):
                keys["panel"], nxt = nxt, nxt + 1
            out.append(dict(fg.card_section(sec), **keys))
        p["sections"] = out
    return parts


def combine(parts, arrange="row", title="", like=None, size=None, one_colorbar=False,
            grid=None):
    """A figure of parts (figdraw kind "combo"): as wide as the parts side by side (as
    tall when stacked; on a custom grid, `grid`, as its columns and rows need), or `size`
    [width, height] in (either None: that default); its export settings, fonts and
    background those of `like`, and with one_colorbar a colorbar for the whole figure
    styled as like's."""
    like = like or parts[0]
    row = arrange == "row"
    w = [float(p["size"][0]) for p in parts]
    h = [float(p["size"][1]) for p in parts]
    own = list(size or [None, None])
    extra = {}
    if arrange == "grid":
        g = figdraw.grid_layout(parts, grid)
        W, H = sum(g["widths"]), sum(g["heights"])
        extra["part_grid"] = dict(grid or {}, rows=g["rows"], cols=g["cols"])
    else:
        W, H = (sum(w), max(h)) if row else (max(w), sum(h))
    W, H = float(own[0]) if own[0] else W, float(own[1]) if own[1] else H
    runs, seen = [], set()
    for p in parts:
        for r in p.get("runs") or []:
            if r["path"] not in seen:
                seen.add(r["path"])
                runs.append(r)
    cb = dict(like.get("colorbar", {}), mode="figure") if one_colorbar else dict(mode="parts")
    return dict(version=1, kind="combo", arrange=arrange, parts=parts, size=[W, H],
                size_set=[own[0] or None, own[1] or None], colorbar=cb,
                runs=runs, suptitle=title, export=like.get("export", {}),
                background=like.get("background", "white"), font=like.get("font", {}),
                mplstyle=like.get("mplstyle", ""), spacing=like.get("spacing", {}), **extra)
