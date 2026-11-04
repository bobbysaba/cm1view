"""3D scenes in the inspector.  Where you click says what an edit reaches:

  All 3D scenes   what every scene shows and how: its surfaces, floor, vectors, streamlines,
                  parcels, region, camera, look, animation (kinds["scene"]["scene3d"])
  a panel         its run, time, title, its own look, and any of those for this scene alone
                  (its opts["scene3d"], a key of the block at a time, each to take back)

The only scene's settings go to the kind unless it holds them itself (docedit.write_scene), so
one scene, the usual figure, has no two places to look.  The widgets are copies of the old
editor's (figures/scene.py) and its rows' (cards/scenecard.py), made when a section opens."""

import panel as pn

from .. import draw as figdraw
from ..cards import IsoRow, ParRow, VecRow, _checks, _grid
from ..cards.base import SECTION, grid_columns
from ..scene import ISO_MAX, PAR_MAX, VEC_MAX, _put, next_iso, next_vec
from . import docedit as de, nodes
from .layerrow import CardHost
from .planview import PlanPane


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


def _copy(src, **kw):
    """A copy of one of the editor's scene widgets, on its own."""
    return src.clone(visible=True, disabled=False, **kw)


def _button(name, on_click, tip=None):
    b = pn.widgets.Button(name=name, height=32, margin=(4, 4), button_type="light",
                          button_style="outline", description=tip)
    b.on_click(lambda e: on_click())
    return b


# (each section: the keys of the block it writes, whether it starts open)
SECTIONS = {"Isosurfaces": (("isos",), True), "Floor": (("ground",), False),
            "Vectors": (("vecs",), False), "Streamlines": (("stream",), False),
            "Parcels": (("parcels",), False),
            "Region and resolution": (("box", "ztop", "exag", "smooth", "res"), False),
            "Camera": (("camera",), True), "Look": (("look",), False),
            "Animation": (("follow", "orbit"), False)}
KEY_NAMES = dict(isos="Isosurfaces", ground="Floor", vecs="Vectors", stream="Streamlines",
                 parcels="Parcels", box="Region", ztop="Top", exag="Exaggeration",
                 smooth="Smoothing", res="Resolution", camera="Camera", look="Look",
                 follow="Box in animations", orbit="Camera orbit")


class SceneCards:
    """The sections of scene settings at one scope: pid, or None for all scenes."""

    def __init__(self, pane, pid=None):
        self.pane, self.pid = pane, pid
        self.ins, self.shell, self.ed = pane.ins, pane.shell, pane.shell.ed

    def block(self):
        return de.scene_block(self.shell.doc, self.pid)

    def write(self, key, value, again=False):
        """A key of the block, whole.  again: the node is shown anew (what shows follows it)."""
        value = de.plain(value)
        doc = self.shell.doc
        # (the first of this scene's own: its ↺ appears)
        again = again or (self.pid is not None and key not in de.scene_own(doc, self.pid)
                          and len(de.panels_of(doc, "scene")) > 1)
        self.shell.edit(lambda d: de.write_scene(d, self.pid, key, value),
                        node=self.shell.node if again else None)

    def card(self, title):
        keys, first_open = SECTIONS[title]
        key = f"scene:{self.pid}:{title}"
        folds = self.ins.folds
        card = pn.Card(title=title, collapsed=True, **SECTION)

        def fill():
            if not card.objects:
                with grid_columns(2):
                    card.objects = getattr(self, "_" + title.split()[0].lower())(self.block())

        def on_fold(ev):
            folds[key] = not ev.new
            if not ev.new:
                fill()

        card.param.watch(on_fold, "collapsed")
        if folds.get(key, first_open):
            card.collapsed = False
        return card

    def cards(self):
        return [self.card(t) for t in SECTIONS
                if t != "Parcels" or self.shell.v.pf is not None or self.block()["parcels"]]

    def _each(self, name, ws, tidy=lambda d: d):
        """Each widget of ws edits its key of block `name` (a dict).  tidy: what is written of it
        (the block with the change)."""
        def on(k, ev):
            of = dict(camera=figdraw.camera_of, look=figdraw.look_of).get(name)
            sub = of(self.block()) if of else self.block()[name]
            self.write(name, tidy(dict(sub, **{k: ev.new})))

        for k, w in ws.items():
            w.param.watch(lambda ev, k=k: on(k, ev), "value")

    # ------------------------------------------------------------ lists of rows
    def _rows(self, key, make, entries, add, most, more=()):
        """A list's rows (make(host, entry)), an add button, and what else is below."""
        base, rows = {}, []

        def changed():
            new = [r.collect() for r in rows]
            if de.plain(new) != base["now"]:
                base["now"] = de.plain(new)
                self.write(key, new)

        def gone(n):
            self.write(key, [r.collect() for j, r in enumerate(rows) if j != n], again=True)

        host = CardHost(self.shell, changed)
        for n, e in enumerate(entries):
            r = make(host, e)
            r.rm.on_click(lambda ev, n=n: gone(n))
            rows.append(r)
        base["now"] = de.plain([r.collect() for r in rows])
        btn = _button(*add)
        btn.disabled = len(rows) >= most
        return [*[r.panel for r in rows], pn.Row(btn, margin=0), *more]

    def _append(self, key, make, entry):
        """A new row's entry, as its row has it (with what it fills in)."""
        new = make(CardHost(self.shell, lambda: None), entry).collect()
        self.write(key, [*self.block()[key], new], again=True)

    def _isosurfaces(self, sc):
        F = self.shell.fields
        add = ("+ Isosurface", lambda: self._append("isos", IsoRow,
                                                    next_iso(F, self.block()["isos"])))
        objs = self._rows("isos", IsoRow, sc["isos"], add, ISO_MAX, [_note(
            "Untick a surface to leave it out (it is kept). Storm-relative fields use the run's "
            "track.")])
        return objs if sc["isos"] else [_note("No isosurfaces: add one."), *objs]

    def _vectors(self, sc):
        add = ("+ Vectors", lambda: self._append("vecs", VecRow,
                                                 next_vec(self.ed.run, self.block()["vecs"])))
        return self._rows("vecs", VecRow, sc["vecs"], add, VEC_MAX, [_note(
            "Arrows in a plane at a height; Arrows across: across the region's width.")])

    def _parcels(self, sc):
        def more():
            e = self.ed.next_parcels({x.get("name") for x in self.block()["parcels"]},
                                     self.shell.say)
            if e is not None:
                self._append("parcels", ParRow, e)

        return self._rows("parcels", ParRow, sc["parcels"], ("+ Parcels", more), PAR_MAX, [_note(
            "Parcel sets as the viewer's Parcels tab chose them: tails as lines, heads at the "
            "scene's time as balls, inside the region. Coloured by a variable, the first such set "
            "gets the parcel colorbar (Look).")])

    # ------------------------------------------------------------ settings
    def _floor(self, sc):
        ed, F = self.ed, self.shell.fields
        ws = {k: _copy(w) for k, w in ed.sc_g.items()}
        ws["var"].groups = F.groups()
        _put(ws, sc["ground"])

        def show(*ev):
            d = F[ws["var"].value] if ws["var"].value in F else None
            ws["z"].visible = d is not None and d.ndim == 3
            ws["lo"].visible = ws["hi"].visible = ws["range"].value == "custom"

        def on_range(ev):
            """A custom range starts at the field's display range."""
            show()
            d = F[ws["var"].value] if ws["var"].value in F else None
            new = dict(self.block()["ground"], range=ev.new)
            custom = ev.new == "custom" and d is not None and d.vrange
            if custom:
                new.update(lo=float(d.vrange[0]), hi=float(d.vrange[1]))
            self.write("ground", new, again=bool(custom))

        ws["var"].param.watch(show, "value")
        ws["range"].param.watch(on_range, "value")
        self._each("ground", {k: w for k, w in ws.items() if k != "range"})
        show()
        return [_grid((ws["var"], 2), ws["z"], ws["cmap"], ws["range"], ws["lo"], ws["hi"]),
                _checks(ws["on"], ws["rev"])]

    def _streamlines(self, sc):
        ed = self.ed
        ws = {k: _copy(w) for k, w in ed.sc_s.items()}
        _put(ws, sc["stream"])
        self._each("stream", ws)
        sb = sc["stream"].get("seed_box")
        said = '<div class="cv-hint">Seeded over the whole region.</div>' if not sb else (
            f'<div class="cv-hint">Seeded in x {sb[0]:.1f} to {sb[1]:.1f}, y {sb[2]:.1f} to '
            f'{sb[3]:.1f} km.</div>')

        def seed(box):
            self.write("stream", dict(self.block()["stream"], seed_box=box), again=True)

        def from_map():
            box = getattr(self.shell.v, "seed_box", None)
            if box is None:
                self.shell.say("Pick a seed box on the map first (3D tool → Seed box on map).",
                               True)
                return
            seed([float(v) for v in box])

        tools = [_button("The map's seed box", from_map, "Seed inside the box picked on the map "
                                                         "(3D tool → Seed box on map)")]
        if sb:
            tools.append(_button("Whole region", lambda: seed(None)))
        return [_grid(ws["z"], ws["n"], ws["length"], ws["dir"], ws["frame"], ws["color_by"]),
                _checks(ws["on"]), pn.Row(*tools, margin=0),
                pn.pane.HTML(said, margin=(2, 4))]

    def _region(self, sc):
        ed = self.ed
        ws = {k: _copy(w) for k, w in ed.sc_w.items()}
        _put(ws, sc)
        for k, w in ws.items():
            w.param.watch(lambda ev, k=k: self.write(k, self._number(k, ev.new)), "value")
        box = sc.get("box")
        region = _copy(ed.sc_region, value="box" if box else "full")
        boxes = [_copy(w, value=None if box is None else float(box[n]))
                 for n, w in enumerate(ed.sc_box)]
        said = pn.pane.HTML(margin=(0, 4), sizing_mode="stretch_width")

        def show():
            for w in boxes:
                w.visible = region.value == "box"

        def commit(*ev):
            b = [w.value for w in boxes]
            ok = None not in b and b[1] > b[0] and b[3] > b[2]
            said.object = "" if ok else (
                '<div class="cv-status" style="color:#f87171">The box needs x max above x min and '
                'y max above y min.</div>')
            if ok and [float(v) for v in b] != self.block().get("box"):
                self.write("box", [float(v) for v in b])

        def on_region(ev):
            show()
            if ev.new != "box":
                said.object = ""
                self.write("box", None)
                return
            for w, v in zip(boxes, self.shell.v.view):  # (a start: the map's view)
                if w.value is None:
                    w.value = round(float(v), 2)
            commit()

        def from_map():
            b = getattr(self.shell.v, "box", None)
            if b is None:
                self.shell.say("Draw a 3D box on the map first (3D tool), or type one.", True)
                return
            self.write("box", [round(float(v), 2) for v in b], again=True)

        region.param.watch(on_region, "value")
        show()
        for w in boxes:
            w.param.watch(commit, "value")
        return [_grid(region, ws["ztop"], ws["exag"]),
                _grid(*boxes, n=2), said,
                pn.Row(_button("The map's 3D box", from_map, "The box drawn on the map (3D tool)"),
                       margin=0),
                _grid(ws["smooth"], ws["res"]),
                _note("The exaggeration only stretches the picture (nothing is read again); the "
                      "region, top, smoothing and resolution compute the surfaces again.")]

    @staticmethod
    def _number(key, value):
        """A setting of Region as the document holds it (blank: as the scene reads it)."""
        if key == "res":
            return int(value or 0)
        return float(value or dict(ztop=15.0, exag=1.0, smooth=0.0)[key])

    def _camera(self, sc):
        ed = self.ed
        cam = figdraw.camera_of(sc)
        ws = {k: _copy(w) for k, w in ed.sc_c.items()}
        _put(ws, cam)

        def tidy(c):  # (an explicit position, as a saved figure has, no longer holds)
            return dict(c, zoom=c.get("zoom") or 1.0, view_angle=c.get("view_angle") or 30.0,
                        position=None, focal=None, up=None)

        self._each("camera", ws, tidy)

        def from_3d():
            self.write("camera", tidy(ed._view_camera()), again=True)

        return [_grid(ws["preset"], ws["azimuth"], ws["elevation"], ws["zoom"], ws["projection"],
                      ws["view_angle"]),
                pn.Row(_button("Camera of the 3D view", from_3d, "The direction and distance the "
                               "3D workspace is seen from now"), margin=0),
                _note("A view, turned by the azimuth and elevation typed (blank: the view's own), "
                      "at the distance where the region fits, divided by the zoom. Camera of the "
                      "3D view: as you left the 3D workspace (rotate it there, then click).")]

    def _look(self, sc):
        ed = self.ed
        lk = figdraw.look_of(sc)
        ws = {k: _copy(w) for k, w in ed.sc_l.items()}
        _put(ws, dict(lk, background=lk["background"] or ""))
        labels = [_copy(w, value=str(t)) for w, t in zip(ed.sc_labels,
                                                         list(lk["labels"]) + ["", "", ""])]

        def tidy(d):
            d = dict(d, background=d.get("background") or None)
            for k, v in (("tube", 1.0), ("shine", 0.3), ("ambient", 0.25)):
                if d.get(k) is None:
                    d[k] = v
            return d

        self._each("look", ws, tidy)

        def on_label(ev):
            self.write("look", tidy(dict(figdraw.look_of(self.block()), labels=[w.value for w in labels])))

        for w in labels:
            w.param.watch(on_label, "value")
        return [_grid(ws["lighting"], ws["background"], ws["arrows"], ws["shine"], ws["ambient"],
                      ws["tube"], ws["floor_bar"], ws["stream_bar"], ws["parcel_bar"],
                      ws["outline_color"]),
                _grid(*labels, n=3),
                _checks(ws["outline"], ws["ticks"], ws["legend"], ws["seed_box"])]

    def _animation(self, sc):
        ed = self.ed
        follow = _copy(ed.sc_anim["follow"], value="track" if sc["follow"] == "track" else "fixed")
        orbit = _copy(ed.sc_anim["orbit"], value=float(sc["orbit"] or 0.0))
        follow.param.watch(lambda ev: self.write("follow", ev.new), "value")
        orbit.param.watch(lambda ev: self.write("orbit", float(ev.new or 0.0)), "value")
        return [_grid(follow, orbit),
                _note("For an animation: each frame steps the scene's time. A box following the "
                      "track needs a Fixed box and the run's track; the orbit is shared out "
                      "evenly, so a looping 360° turn does not repeat a frame.")]


class ScenePane(PlanPane):
    kind = "scene"

    # ------------------------------------------------------------ from the viewer
    def _tools(self, pid):
        cards = SceneCards(self, pid)

        def copy_view():
            ed = self.shell.ed
            sc = de.plain(ed.viewer_scene())
            now = cards.block()
            sc.update(follow=now["follow"], orbit=now["orbit"])  # (the animation stays)

            def apply(d):
                for key, value in sc.items():
                    de.write_scene(d, pid, key, value)
            self.shell.edit(apply, node=self.shell.node)

        return [pn.Row(_button("Copy the 3D view", copy_view, "Everything the 3D workspace shows "
                               "now (its box, surfaces, floor, vectors, streamlines and camera)"),
                       margin=0)]

    def _hint(self):
        return _note("One 3D picture, rendered off-screen at the preview's resolution here and at "
                     "the export's DPI when saved.")

    # ------------------------------------------------------------ all scenes
    def _differ(self, doc):
        names, out = nodes.letters(doc), []
        for p in de.panels_of(doc, "scene"):
            if de.scene_own(doc, p["id"]):
                out.append(names[p["id"]])
        return out

    def kind_objs(self, doc):
        mine = de.panels_of(doc, "scene")
        names = nodes.letters(doc)
        objs = [_note("Panels " + ", ".join(names[p["id"]] for p in mine) + ": a run and time "
                      "each, on the panel."), self._hint(),
                pn.Row(*self._tools(None), _button("+ 3D scene panel", self.add_panel,
                                                   "In the first free cell, or a new row or "
                                                   "column"), margin=0),
                *SceneCards(self).cards()]
        differ = self._differ(doc)
        if differ:
            objs.append(_note("Set in a panel alone, so changes here skip it: panel"
                              + ("s " if len(differ) > 1 else " ") + ", ".join(differ) + "."))
        return f"All {nodes.kind_name('scene', len(mine))}", objs

    def add_panel(self):
        return self.ins.grid.add_panel("scene")

    # ------------------------------------------------------------ a panel
    def panel_objs(self, doc, node):
        p = nodes.panel_of(doc, node)
        pid, letter = p["id"], nodes.letters(doc)[p["id"]]
        shell = self.shell

        def set_key(key, value):
            def apply(d):
                q = de.panel_by_id(d, pid)
                if value is None:
                    q.pop(key, None)
                else:
                    q[key] = value
            shell.edit(apply)

        title = pn.widgets.TextInput(name="Title", value=p.get("title") or "")
        title.param.watch(lambda ev: set_key("title", ev.new.strip()), "value")
        rowlabel = pn.widgets.TextInput(name="Row label (left)", value=p.get("rowlabel") or "",
                                        placeholder="none")
        rowlabel.param.watch(lambda ev: set_key("rowlabel", ev.new.strip() or None), "value")
        run, time = self._run_time(doc, p)
        objs = [_grid(title, rowlabel, run, time, n=2), self._hint(), *self._tools(pid),
                *self._own_chips(doc, pid), *SceneCards(self, pid).cards()]
        objs += self._panel_looks(doc, pid)
        objs += self.ins.grid.place_objs(doc, pid)
        return f"Panel {letter}", objs

    def _own_chips(self, doc, pid):
        """What this scene alone has, each to take back (↺)."""
        own = de.scene_own(doc, pid)
        if not own:
            return []

        def back(key):
            self.shell.edit(lambda d: de.scene_take_back(d, pid, key), node=self.shell.node)

        chips = []
        for key in own:
            b = pn.widgets.Button(name=f"↺ {KEY_NAMES.get(key, key)}", height=26,
                                  margin=(2, 2), button_type="light", button_style="outline",
                                  description="Back to what all 3D scenes have")
            b.on_click(lambda e, k=key: back(k))
            chips.append(b)
        return [_note("Set for this scene alone:"), pn.FlexBox(*chips, sizing_mode="stretch_width")]

    def layer_objs(self, doc, node):  # (a scene's panel has no layers in the tree)
        return self.panel_objs(doc, node)
