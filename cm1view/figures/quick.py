"""Figure editor: the quick start.  Opening the Figure workspace the first time (with no
figure made from the viewer yet), and the new-figure button, ask for the few settings a
figure starts from: what the panels show, how they differ, the grid, the main field
and the width.  Everything else is the editor's tabs.  Or it starts from a template, or
from a saved figure, shown as a gallery of thumbnails, newest first.

A mixin of the FigureEditor (figures/editor.py)."""

import base64
import time
from functools import partial

import panel as pn

from .. import config
from . import spec as fg
from ..theme import DIALOG_DARK
from .cards import QUICK_VARY, SIZE_PRESETS, _grid, _hint
from .export import make_thumb, saved_list, saved_thumb
from .kinds import KINDS, MAPS

ALL_FOLDERS = "Newest first, all folders"
GALLERY_STEP = 12  # thumbnails shown at a time
NO_TEMPLATES = "No templates yet"
_THUMB_BOX = 104  # px of a gallery button given to the picture; the name is below it


def _thumb_css(png=None):
    """The stylesheet of a gallery button: its picture is its background, so a click
    anywhere on the picture opens the figure."""
    pic = "none" if png is None else \
        f"url(data:image/png;base64,{base64.b64encode(png).decode()})"
    return (f":host .bk-btn {{ display: block !important; background: #fff {pic} center 4px / calc(100% - 8px) "
            f"{_THUMB_BOX}px no-repeat !important; color: #1f2937 !important; "
            f"padding: {_THUMB_BOX + 6}px 6px 0 6px !important; height: 100% !important; "
            "font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; "
            "border: 1px solid #94a3b8 !important; }")


class FigureQuick:
    _started = False  # a figure has been made (here, from the viewer, or loaded)
    _quick_xsec = False  # (making sections: no cards from the plan views' grid)
    _gallery_gen = 0  # (a thumbnail still being made for a closed dialog is dropped)

    def _build_quick(self):
        self.qs_kind = pn.widgets.Select(name="Panels show", options=dict(self.kind.options),
                                         value="plan")
        self.qs_vary = pn.widgets.Select(name="Panels differ in", options=QUICK_VARY,
                                         value="times")
        self.qs_rows = pn.widgets.IntInput(name="Rows", start=1, end=8, value=2)
        self.qs_cols = pn.widgets.IntInput(name="Columns", start=1, end=8, value=3)
        self.qs_field = pn.widgets.Select(name="Colour fill")
        self.qs_size = pn.widgets.Select(name="Width", value="", options={
            ("8 in wide" if v == "" else k): v for k, v in SIZE_PRESETS.items()})
        self.qs_note = _hint("")
        self.qs_go = pn.widgets.Button(name="Make the figure", button_type="primary",
                                       width=160)
        self.qs_skip = pn.widgets.Button(
            name="Keep the example", button_type="light", button_style="outline", width=150,
            description="Close: the figure stays as it is")
        self.qs_tpl = pn.widgets.Select(name="Or start from a template")
        self.qs_tpl_go = pn.widgets.Button(name="Apply to this run", button_type="primary",
                                           button_style="outline", disabled=True)
        self.qs_where = pn.widgets.Select(name="Or open a saved figure", width=300,
                                          options={ALL_FOLDERS: ""})
        self.qs_none = _hint("No saved figures yet: they appear here once you save one.")
        self.qs_gallery = pn.FlexBox(margin=0, styles={  # (the dialog stays in the window)
            "max-height": "clamp(140px, calc(100vh - 630px), 292px)", "overflow-y": "auto",
            "gap": "4px"})
        self.qs_more = pn.widgets.Button(name="Show more", button_type="light",
                                         button_style="outline", width=120, visible=False)
        self.qs_load_note = _hint("")
        self.qs_load_note.visible = False
        self.qs_earlier = pn.widgets.Button(
            name="Reopen the last figure", icon="history", button_type="primary",
            button_style="outline", width=210,
            description="The figure you were last working on in this run, saved or not")
        self.qs_earlier_note = _hint("")
        self.qs_earlier_note.align = "center"
        self.qs_earlier_row = pn.Row(self.qs_earlier, self.qs_earlier_note, visible=False,
                                     margin=0)
        self.quick = pn.Modal(
            pn.pane.HTML('<div class="cv-maptitle" style="font-size:16px"><b>New figure'
                         '</b></div>', margin=(0, 4)),
            self.qs_earlier_row,
            _grid(self.qs_kind, self.qs_vary, self.qs_field),
            _grid(self.qs_rows, self.qs_cols, self.qs_size), self.qs_note,
            _hint("Everything else (times, layers, style, labels) is in the editor's tabs; "
                  "the new-figure button above the preview shows this again."),
            pn.Row(self.qs_go, self.qs_skip),
            pn.layout.Divider(margin=(6, 4)),
            _grid((self.qs_tpl, 2), self.qs_tpl_go),
            _hint("Saved in File → Templates: its panels and look on this run, its times "
                  "moved to the map's time."),
            pn.layout.Divider(margin=(6, 4)),
            self.qs_where, self.qs_none, self.qs_load_note, self.qs_gallery, self.qs_more,
            _hint("Figures saved in the Figures folder (⚙ Settings); the File tab opens "
                  "any other."), width=680, margin=10,
            stylesheets=[DIALOG_DARK])
        self.qs_kind.param.watch(lambda e: self._quick_show(), "value")
        self.qs_vary.param.watch(lambda e: self._quick_show(), "value")
        self.qs_go.on_click(lambda e: self._quick_make())
        self.qs_skip.on_click(lambda e: self.quick.hide())
        self.qs_tpl_go.on_click(lambda e: self._quick_template())
        self.qs_where.param.watch(lambda e: self._gallery_show(), "value")
        self.qs_more.on_click(lambda e: self._gallery_more())
        # (closed: the thumbnails leave the page)
        self.quick.param.watch(lambda e: None if e.new else self._gallery_clear(), "open")
        self.qs_earlier.on_click(lambda e: self._quick_earlier())

    def opened(self):
        """The Figure workspace is shown: the quick start, the first time."""
        if not self._started and not self._in_shell():
            self._started = True
            self.open_quick()

    def open_quick(self):
        """Show the quick start, set as the figure in the editor."""
        g = self.fields.groups()
        fill = (self._pf_base or {}).get("field") or next(
            (c.collect()["field"] for c in self.cards if c.type == "fill"), None)
        self.qs_field.groups = g
        names = [v for grp in g.values() for v in grp.values()]
        self.qs_field.value = fill if fill in names else (names[0] if names else None)
        self.qs_kind.value = self.kind.value
        self._quick_show()  # (the panels' choices of this kind first)
        dims = [d for d in self._axes() if d != "none"]
        vary = dims[0] if len(dims) == 1 else "times"
        self.qs_vary.value = vary if vary in self.qs_vary.options.values() else "times"
        self.qs_rows.value, self.qs_cols.value = int(self.rows.value), int(self.cols.value)
        self._list_templates()
        tpls, keep = dict(self.tpl_sel.options), self.qs_tpl.value
        self.qs_tpl.options = tpls or {NO_TEMPLATES: ""}
        self.qs_tpl.value = keep if keep in tpls.values() else next(iter(tpls.values()), "")
        self.qs_tpl.disabled = self.qs_tpl_go.disabled = not tpls
        self.qs_load_note.visible = False
        self._gallery_open()
        self._earlier = self._auto_earlier()
        self.qs_earlier_row.visible = self._earlier is not None
        if self._earlier:
            when = time.strftime("%b %d, %H:%M", time.localtime(self._earlier[1]))
            self.qs_earlier_note.object = f'<div class="cv-hint">Last changed {when}</div>'
        self.quick.show()

    def _quick_show(self):
        kind, vary = self.qs_kind.value, self.qs_vary.value
        maps = kind in MAPS
        self.qs_field.visible = maps
        self.qs_vary.visible = kind == "plan"  # (sections: a card per panel)
        # (time-height: its cards'; a 3D scene: one picture)
        self.qs_rows.visible = self.qs_cols.visible = KINDS[kind].quick_grid
        note = KINDS[kind].note or (maps and {
            "fields": "Every panel starts with this fill: pick each panel's field in "
                      "Panels → Time and fields.",
            "heights": "Pick each panel's height in Panels → Time and heights.",
            "runs": "A panel per run: add runs in Layers → Runs used.  For a grid such "
                    "as runs × times, set Panels → Grid and size → Rows are / "
                    "Columns are.",
            "none": "Every panel is alike: change one in the panel tree (its run, time, "
                    "height …)."}.get(vary)) or ""
        self.qs_note.object = f'<div class="cv-hint">{note}</div>'
        self.qs_note.visible = bool(note)

    # ------------------------------------------------------------ gallery of saved figures
    def _gallery_open(self):
        """List the saved figures anew and show the newest."""
        self._qs_figures = saved_list(self._fig_dir, config.expand(config.get("figures_dir")),
                                      config.expand(config.state("last_multi_run_dir")))
        heads = list(dict.fromkeys(f[0] for f in self._qs_figures))
        self.qs_where.options = {ALL_FOLDERS: "", **{h: h for h in heads}}
        self.qs_where.visible = bool(heads)
        self.qs_none.visible = not heads
        if self.qs_where.value:  # (its watcher shows the gallery)
            self.qs_where.value = ""
        else:
            self._gallery_show()

    def _gallery_figures(self):
        """The saved figures of the folder picked; of them all, newest first."""
        where = self.qs_where.value
        if where:
            return [f for f in self._qs_figures if f[0] == where]
        return sorted(self._qs_figures, key=lambda f: -f[3])

    def _gallery_show(self):
        self._gallery_clear()
        self._gallery_more()

    def _gallery_clear(self):
        self._gallery_gen += 1
        self.qs_gallery.objects = []
        self.qs_more.visible = False

    def _gallery_more(self):
        """The next thumbnails.  Those not made yet come from the pool, each in its turn:
        an image can be large."""
        figs = self._gallery_figures()
        n = len(self.qs_gallery.objects)
        add = [self._gallery_button(f) for f in figs[n:n + GALLERY_STEP]]
        self.qs_gallery.objects = list(self.qs_gallery.objects) + add
        self.qs_more.visible = n + len(add) < len(figs)

    def _gallery_button(self, fig):
        head, name, path, when = fig
        png = saved_thumb(path)
        b = pn.widgets.Button(
            name=name, width=200, height=134, margin=2, stylesheets=[_thumb_css(png)],
            description=f"{name} · {head} · saved "
                        f"{time.strftime('%b %d %Y, %H:%M', time.localtime(when))}")
        b.on_click(lambda e: self._quick_open(path))
        if png is None:
            self.v.pools["fig"].submit(self._thumb_job, b, path, self._gallery_gen)
        return b

    def _thumb_job(self, button, path, gen):
        if gen != self._gallery_gen:
            return
        png = make_thumb(path)
        if png is not None:
            self.v._schedule(partial(self._thumb_show, button, png, gen))

    def _thumb_show(self, button, png, gen):
        if gen == self._gallery_gen:
            button.stylesheets = [_thumb_css(png)]

    def _quick_note(self, html):
        self.qs_load_note.object = html
        self.qs_load_note.visible = True

    def _quick_done(self):
        """A figure is in the widgets: the new layout takes it, when it is what shows."""
        if self._in_shell():
            self.shell.take_figure()

    def _quick_open(self, path):
        """Open a saved figure (it closes the dialog); if it cannot be opened, say why in
        the dialog."""
        if self._load_spec(path):
            self._quick_done()
        else:
            self._quick_note(self.msg.object)

    def _quick_template(self):
        """Apply the template picked (it closes the dialog); if it cannot be applied, say
        why in the dialog."""
        if self._apply_template(self.qs_tpl.value):
            self._quick_done()
        else:
            self._quick_note(self.msg.object)

    def _quick_earlier(self):
        """Open the figure an earlier page left; if it cannot be, say why in the dialog."""
        why = self.open_state(self._earlier[0], "Reopened the last figure")
        if why:
            self._quick_note(f'<div class="cv-status">{why}</div>')
        else:
            self._quick_done()

    def _quick_make(self):
        """A new figure (Undo takes it back) with the quick start's settings."""
        self.quick.hide()
        kind, vary = self.qs_kind.value, self.qs_vary.value
        s = self._default()
        f = self.qs_field.value
        if kind in MAPS and f:
            fill = next((lay for lay in s["layers"] if lay["type"] == "fill"), None)
            if fill is not None and fill.get("field") != f:
                s["layers"][s["layers"].index(fill)] = fg.layer_defaults(
                    "fill", self.fields, f, 1.0)
        live, self.auto.value = self.auto.value, False  # (one render: one undo step)
        try:
            self.set_parts(s)
            self._quick_xsec = True  # (_quick_spread makes the section cards, once)
            try:
                self.kind.value = kind  # (its own labels, colorbar and cards)
            finally:
                self._quick_xsec = False
            if kind == "plan":
                self.g_rows.value, self.g_cols.value = "none", vary
            if KINDS[kind].quick_grid:
                self.rows.value = int(self.qs_rows.value)
                self.cols.value = int(self.qs_cols.value)
            if KINDS[kind].spread:
                self._quick_spread(kind)
            if self.qs_size.value:
                self.size_preset.value = self.qs_size.value
        finally:
            self.auto.value = live
        self._quick_done()
        self.request()  # (shortly: the dialog closes and the editor shows first)

    def _quick_spread(self, kind):
        """Sounding / distribution / profile / joint distribution / azimuthal mean cards
        one per panel of the grid: more cards than panels wrap (sharing panels), panels left over get a copy
        of the last card."""
        n = int(self.rows.value or 1) * int(self.cols.value or 1)
        if kind == "xsec":  # (x–z, y–z, x–z ... at the shown time; no track: fixed)
            track = bool(self.v.fixes) or any(r.get("track") for r in self._runs_collect())
            e = fg.section_defaults(run=self._own_index(), time_s=self._shown_s(),
                                    pos="storm" if track else "fixed")
            self.sec_cards = self._sec_cards([dict(e, orient="xy"[i % 2], panel=i)
                                              for i in range(n)])
            self._show_sections()
            self._build_titles()
            return
        k = KINDS[kind]
        ents = [c.collect() for c in getattr(self, k.cards)]
        if not ents:
            return
        ents = [dict(e, panel=i % n) for i, e in enumerate(ents)] + \
            [dict(ents[-1], panel=i) for i in range(len(ents), n)]
        setattr(self, k.cards, [getattr(self, k.card)(e) for e in ents])
        getattr(self, k.show)()
        self._build_titles()
