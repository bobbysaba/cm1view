"""Figure editor: the New dialog.  Opening the Figure workspace the first time (with no
figure made from the viewer yet), and the new-figure button, ask for the few settings a
figure starts from: what the panels show, how they differ, the grid, the main field
and the width.  Everything else is the panes'.  Or it starts from a template, or
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
from .times import _nearest_t
from .kinds import KIND_LABELS, KINDS, MAPS
from .shell import docedit as de
from .shell.gridview import main_kind

ALL_FOLDERS = "Newest first, all folders"
GALLERY_STEP = 12  # thumbnails shown at a time
NO_TEMPLATES = "No templates yet"
PICK = "Pick a saved figure…"
NEW_STEP = 5  # outputs between a new figure's panels, past the times it starts with
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
    _gallery_gen = 0  # (a thumbnail still being made for a closed dialog is dropped)

    def _build_quick(self):
        self.qs_kind = pn.widgets.Select(name="Panels show", options=dict(KIND_LABELS),
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
            name="Keep this figure", button_type="light", button_style="outline", width=150,
            description="Close: the figure stays as it is")
        self.qs_tpl = pn.widgets.Select(name="Or start from a template")
        self.qs_tpl_go = pn.widgets.Button(name="Apply to this run", button_type="primary",
                                           button_style="outline", disabled=True)
        self.qs_pick = pn.widgets.Select(
            name="Or open a saved figure", options={PICK: ""},
            description="This run's saved figures first, then the other folders of the Figures "
                        "setting. Picking one fills in the path below.")
        self.qs_where = pn.widgets.Select(name="Thumbnails from", width=300,
                                          options={ALL_FOLDERS: ""})
        self.qs_none = _hint("No saved figures yet: they appear here once you save one.")
        self.qs_gallery = pn.FlexBox(margin=0, styles={  # (the dialog stays in the window)
            "max-height": "clamp(140px, calc(100vh - 760px), 292px)", "overflow-y": "auto",
            "gap": "4px"})
        self.qs_more = pn.widgets.Button(name="Show more", button_type="light",
                                         button_style="outline", width=120, visible=False)
        self.qs_path = pn.widgets.TextInput(name="Or open one by its path",
                                            placeholder="…/_src/figure_spec.json, or its image")
        self.qs_open = pn.widgets.Button(name="Open", button_type="primary",
                                         button_style="outline", align="end")
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
            _hint("Everything else (times, layers, style, labels) is in the tree and the "
                  "inspector; the new-figure button above the preview shows this again."),
            pn.Row(self.qs_go, self.qs_skip),
            pn.layout.Divider(margin=(6, 4)),
            _grid((self.qs_tpl, 2), self.qs_tpl_go),
            _hint("Saved from Export → Template: its panels and look on this run, its times "
                  "moved to the map's time."),
            pn.layout.Divider(margin=(6, 4)),
            self.qs_pick, self.qs_none, _grid((self.qs_path, 2), self.qs_open),
            self.qs_load_note, self.qs_where, self.qs_gallery, self.qs_more,
            _hint("Figures saved in the Figures folder (⚙ Settings)."), width=680, margin=10,
            stylesheets=[DIALOG_DARK])
        self.qs_kind.param.watch(lambda e: self._quick_show(), "value")
        self.qs_vary.param.watch(lambda e: self._quick_show(), "value")
        self.qs_go.on_click(lambda e: self._quick_make())
        self.qs_skip.on_click(lambda e: self.quick.hide())
        self.qs_tpl_go.on_click(lambda e: self._quick_template())
        self.qs_pick.param.watch(self._quick_pick, "value")
        self.qs_where.param.watch(lambda e: self._gallery_show(), "value")
        self.qs_more.on_click(lambda e: self._gallery_more())
        # (closed: the thumbnails leave the page)
        self.quick.param.watch(lambda e: None if e.new else self._gallery_clear(), "open")
        self.qs_earlier.on_click(lambda e: self._quick_earlier())
        self.qs_open.on_click(lambda e: self._quick_open(self.qs_path.value))

    def opened(self):
        """The Figure workspace is shown: its panes, and the New dialog the first time (with no
        figure made from the viewer yet)."""
        self.shell.open()
        if not self._started and not self.shell.made:
            self._started = True
            self.open_quick()

    def open_quick(self):
        """Show the New dialog, set as the figure is."""
        doc = self.shell.doc
        kind = main_kind(doc)
        g = self.fields.groups()
        fills = de.guess_fill(doc, kind)["fields"] if kind in MAPS else []
        self.qs_field.groups = g
        names = [v for grp in g.values() for v in grp.values()]
        self.qs_field.value = fills[0] if fills and fills[0] in names else (
            names[0] if names else None)
        self.qs_kind.value = kind
        self._quick_show()  # (the panels' choices of this kind first)
        guess = de.guess_fill(doc, kind)
        dims = [d for d in (guess["row_dim"], guess["col_dim"]) if d != "none"]
        vary = dims[0] if len(dims) == 1 else "times"
        self.qs_vary.value = vary if vary in self.qs_vary.options.values() else "times"
        self.qs_rows.value, self.qs_cols.value = guess["rows"], guess["cols"]
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
        self.qs_vary.visible = kind == "plan"
        # (time-height: its cards'; a 3D scene: one picture)
        self.qs_rows.visible = self.qs_cols.visible = KINDS[kind].quick_grid
        note = KINDS[kind].note or (maps and {
            "fields": "Every panel starts with this fill: pick each panel's field in "
                      "the tree.",
            "heights": "Pick each panel's height in the tree, or use Fill panels on the Plan "
                       "views node.",
            "runs": "A panel per run: add runs on the tree's Runs node.  For a grid such as "
                    "runs × times, use Fill panels on the Plan views node.",
            "none": "Every panel is alike: pick one in the tree to change it (its run, time, "
                    "height …)."}.get(vary)) or ""
        self.qs_note.object = f'<div class="cv-hint">{note}</div>'
        self.qs_note.visible = bool(note)

    # ------------------------------------------------------------ gallery of saved figures
    def _gallery_open(self):
        """List the saved figures anew and show the newest."""
        self._qs_figures = saved_list(self._fig_dir, config.expand(config.get("figures_dir")),
                                      config.expand(config.state("last_multi_run_dir")))
        heads = list(dict.fromkeys(f[0] for f in self._qs_figures))
        groups = {"": {PICK: ""}}
        for head, name, path, _ in self._qs_figures:
            groups.setdefault(head, {})[name] = path
        self.qs_pick.param.update(options={}, groups=groups, value="")
        self.qs_where.options = {ALL_FOLDERS: "", **{h: h for h in heads}}
        self.qs_pick.visible = self.qs_where.visible = bool(heads)
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

    def _quick_pick(self, ev):
        """A figure picked from the list: its path, ready to open."""
        if ev.new:
            self.qs_path.value = ev.new

    def _quick_open(self, path):
        """Open a saved figure (it closes the dialog); if it cannot be opened, say why in the
        dialog."""
        if not self._load_spec(path):
            self._quick_note(self.msg.object)

    def _quick_template(self):
        """Apply the template picked (it closes the dialog); if it cannot be applied, say why in
        the dialog."""
        if not self._apply_template(self.qs_tpl.value):
            self._quick_note(self.msg.object)

    def _quick_earlier(self):
        """Open the figure an earlier page left; if it cannot be, say why in the dialog."""
        why = self.open_state(self._earlier[0], "Reopened the last figure")
        if why:
            self._quick_note(f'<div class="cv-status">{why}</div>')
        else:
            self.quick.hide()

    def _quick_make(self):
        """A new figure (Undo takes it back) with the dialog's settings."""
        self.quick.hide()
        kind = self.qs_kind.value
        doc = self.shell.new_doc(self._quick_spec())
        r, c = de.grid_shape(doc)
        size = de.kind_size(doc) or (KINDS[kind].size(r, c) if KINDS[kind].size else None)
        if size:
            doc["size"] = [round(min(16.0, float(v)), 2) for v in size]
        preset = self.qs_size.value
        if preset and "x" in preset:
            doc["size"], doc["size_auto"] = [float(v) for v in preset.split("x")], False
        elif preset:
            doc["size"] = [float(preset), doc["size"][1]]
            if doc["panels"] and kind not in MAPS:
                doc["size"][1] = self.shell.fit_height(doc)
        self.shell._take(doc)

    def _quick_spec(self):
        """The version-1 spec of a new figure with the dialog's settings."""
        kind, vary = self.qs_kind.value, self.qs_vary.value
        s = self._default()
        f = self.qs_field.value
        if kind in MAPS and f:
            fill = next((lay for lay in s["layers"] if lay["type"] == "fill"), None)
            if fill is not None and fill.get("field") != f:
                s["layers"][s["layers"].index(fill)] = fg.layer_defaults(
                    "fill", self.fields, f, 1.0)
        k = KINDS[kind]
        s["kind"] = kind
        if kind != "plan":
            fg.kind_look(s, kind)
        r, c = (int(self.qs_rows.value), int(self.qs_cols.value)) if k.quick_grid else (1, 1)
        if kind == "plan":
            r, c = self._plan_grid(s, vary, r, c)
        else:
            s["grid"] = dict(rows="none", cols="none", runs=[])
        s.update(rows=r, cols=c)
        if kind == "xsec":
            track = bool(self.v.fixes) or any(e.get("track") for e in s["runs"])
            e = fg.section_defaults(run=s["run"], time_s=float(self.run.times[self.v.t]),
                                    pos="storm" if track else "fixed")
            s["sections"] = [dict(e, orient="xy"[i % 2], panel=i) for i in range(r * c)]
        elif kind == "scene":
            s["scene3d"] = self.viewer_scene()
        elif k.entries:  # (one per panel: more wrap and share panels, a copy of the last fills)
            ents = self._first_entries(kind, s["run"])
            n = r * c
            s[k.entries] = [dict(e, panel=i % n) for i, e in enumerate(ents)] + \
                [dict(ents[-1], panel=i) for i in range(len(ents), n)]
        return s

    def _plan_grid(self, s, vary, r, c):
        """A new plan-view figure's panels step through vary: spec s's lists for it, in place;
        its grid, for the lists that set their own number."""
        s["grid"] = dict(rows="none", cols=vary, runs=[])
        s["vary"] = fg.legacy_vary("none", vary)
        n = dict(runs=len(s["runs"]), heights=len(s["panel_z"])).get(vary)
        if n and (r * c < n or r * c - n >= c):
            r, c = (1, n) if n <= 4 else (-(-n // 3), 3)
        if vary == "runs":
            s["grid"]["runs"] = list(range(len(s["runs"])))
        if vary == "times":
            s["times_s"] = self._more_times(s["times_s"], r * c)
            s["times"] = [None if t is None else fg.tindex(self.run, t) for t in s["times_s"]]
        else:
            s["times_s"], s["times"] = [], []
        if vary == "fields":
            base = next((lay for lay in s["layers"] if lay["type"] == "fill"), None)
            if base is not None:
                fill = {k: v for k, v in base.items() if k not in ("type", "on", "panels")}
                fill.setdefault("z_fixed", False)
                s["panel_fills"] = [dict(fill) for _ in range(r * c)]
            if s["colorbar"].get("mode") == "shared":  # (a colorbar a field)
                s["colorbar"] = dict(s["colorbar"], mode="each")
        return r, c

    def _more_times(self, times, n):
        """n times: those given, then going on every NEW_STEP outputs (None past the run's end;
        trailing ones dropped)."""
        out, tl = list(times[:n]), [float(t) for t in self.run.times]
        while len(out) < n:
            q = tl.index(_nearest_t(tl, out[-1])) + NEW_STEP if out and out[-1] is not None \
                else len(tl)
            out.append(tl[q] if q < len(tl) else None)
        while out and out[-1] is None:
            out.pop()
        return out

    def _first_entries(self, kind, own):
        """The entries a new figure of a kind starts with: the viewer's tool's, or one new, at the
        shown time in run `own`."""
        ts = float(self.run.times[self.v.t])
        track = bool(self.v.fixes) or any(e.get("track") for e in self.shell.doc["runs"])
        if kind == "sounding":
            return self.tab_soundings() or [fg.sounding_defaults(
                own, ts, dict(kind="trk", x=0.0, y=0.0, avg=0.0), 0)]
        if kind == "dist":
            return self.tab_dists() or [fg.dist_defaults(self._new_dist_recipe(), own, ts, 0)]
        if kind == "profile":
            return self.tab_profiles() or [fg.profile_defaults(self._new_recipe(), own, ts, 0)]
        if kind == "joint":
            return [fg.joint_defaults(self._new_joint_recipe(), own, ts, 0)]
        if kind == "azim":
            return [fg.azim_defaults(self._new_azim_recipe(), own, ts, 0)]
        return [fg.tbl_defaults(self._new_dist_recipe(), own, ts,
                                dict(kind="trk" if track else "mean", x=0.0, y=0.0, avg=0.0))]
