"""Figure editor: figures made of parts.  Each part is a figure of its own (its own kind
of panels, runs, layers and style: e.g. plan views beside soundings, or a plan view
with its A–B line above the cross-section; the plan-view and section parts share one
list of cross-sections), and the parts are drawn side by side or
stacked as one figure (figdraw: kind "combo").  The editor shows one part at a time;
the preview, saving and the download take the whole figure.

A mixin of the FigureEditor (figures/editor.py)."""

import json

import panel as pn

from . import draw as figdraw, spec as fg
from .cards import _auto, _chk, _grid, _hint, _num, _section

KIND_NAMES = {"plan": "plan views", "xsec": "cross-sections", "th": "time–height",
              "line": "time series", "sounding": "soundings", "dist": "distributions",
              "profile": "profiles", "joint": "joint distributions",
              "azim": "azimuthal means"}


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
            "Side by side": "row", "Stacked": "col"})
        self.part_title = pn.widgets.TextInput(name="Title of the whole figure (blank: none)")
        self.part_w = _auto("Figure width (in)", start=1.0,
                            description="Blank: the parts' widths together (side by side)")
        self.part_h = _auto("Figure height (in)", start=1.0,
                            description="Blank: the tallest part's (side by side)")
        self.part_share = _auto(
            "This part's share (0–1)", start=0.02, end=1.0, step=0.05,
            description="Of the figure's width (side by side) or height (stacked). Blank: "
                        "by its size, from what the other parts leave")
        self.part_cb = _chk("One colorbar for the whole figure (the first fill's, styled "
                            "as this part's)", False)
        self.part_note = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 4))
        self.part_size = _grid(self.part_w, self.part_h, self.part_share, (self.part_cb, 3))
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
                "size (the parts then keep their shares of it). Panel letters run on from "
                "part to part."),
            self.part_sel, _grid(self.part_add, self.part_rm, self.part_arr),
            self.part_title, self.part_size, self.part_note)
        self._show_parts()

    # ------------------------------------------------------------ the parts
    def _multi_part(self):
        return len(self.parts) > 1

    def _show_parts(self):
        multi = self._multi_part()
        kinds = [p["kind"] for p in self.parts] if multi else [self.kind.value]
        if multi:
            kinds[self.part_i] = self.kind.value
        opts = {f"Part {k + 1}: {KIND_NAMES.get(kd, kd)}": k for k, kd in enumerate(kinds)}
        hold, self._hold = self._hold, True
        try:
            self.part_sel.options = opts
            self.part_sel.value = self.part_i if multi else 0
        finally:
            self._hold = hold
        self.part_sel.visible = self.part_rm.visible = self.part_arr.visible = \
            self.part_title.visible = self.part_size.visible = multi
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
        new["share"] = None  # (its share follows its size until set)
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
        hold, self._hold = self._hold, True
        try:
            self.part_arr.value = spec.get("arrange", "row")
            self.part_title.value = spec.get("suptitle", "")
            own = spec.get("size_set") or [None, None]
            self.part_w.value, self.part_h.value = _num(own[0]), _num(own[1])
            self.part_cb.value = (spec.get("colorbar") or {}).get("mode") == "figure"
        finally:
            self._hold = hold
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
                       one_colorbar=bool(self.part_cb.value))

    def _combo_data(self, spec, progress=None, cancelled=None):
        data = {}
        for k, part in enumerate(spec["parts"]):
            d = self.panel_data(part, progress, cancelled)
            if d is None:
                return None
            for i, v in d.items():
                data[k * 1000 + int(i)] = v
        return data


def share_sections(parts, src):
    """The plan-view and section parts of a figure of parts take part src's list of
    cross-sections (when src is one of those kinds), in place: they share one list."""
    if src.get("kind") not in ("plan", "xsec") or not src.get("sections"):
        return parts
    for p in parts:
        if p is not src and p.get("kind") in ("plan", "xsec"):
            p["sections"] = json.loads(json.dumps(src["sections"], default=float))
    return parts


def combine(parts, arrange="row", title="", like=None, size=None, one_colorbar=False):
    """A figure of parts (figdraw kind "combo"): as wide as the parts side by side (as
    tall when stacked), or `size` [width, height] in (either None: that default); its
    export settings, fonts and background those of `like`, and with one_colorbar a
    colorbar for the whole figure styled as like's."""
    like = like or parts[0]
    row = arrange == "row"
    w = [float(p["size"][0]) for p in parts]
    h = [float(p["size"][1]) for p in parts]
    own = list(size or [None, None])
    W = float(own[0]) if own[0] else (sum(w) if row else max(w))
    H = float(own[1]) if own[1] else (max(h) if row else sum(h))
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
                mplstyle=like.get("mplstyle", ""), spacing=like.get("spacing", {}))


def panel_name(spec, i):
    """Panel i's letter (a figure of parts: data key k * 1000 + j, letters running on)."""
    if spec.get("kind") != "combo":
        return figdraw.panel_letter(i, "{a}")
    k, j = divmod(int(i), 1000)
    return figdraw.panel_letter(sum(fg.npanels(p) for p in spec["parts"][:k]) + j, "{a}")
