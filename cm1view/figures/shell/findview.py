"""Find a setting: words typed above the inspector list what has them, across the whole figure,
and picking one goes there.  The list comes from what the inspector would show for this figure
(its sections' rows, so a setting of a kind not here isn't offered), and from the names below for
what the settings table doesn't hold: the rows are one widget (TreeView), not a widget each."""

import html
from collections import namedtuple

import panel as pn

from ...theme import PANEL
from .. import settings as table
from . import nodes
from .looks import (FIGURE_SECTIONS, KIND_SECTIONS, PANEL_KEYS, SECTION_NAMES, legend_reaches,
                    row_words, rows_of)
from .sceneview import KEY_NAMES, SECTIONS as SCENE_SECTIONS
from .treeview import TreeView

MOST = 14  # hits listed
EXPORT = "export"  # (a hit's node: the Export dialog)
MAPS = ("plan", "xsec")
AREA_WORDS = "domain x min max y limits region zoom"
Hit = namedtuple("Hit", "label section where node key words")

# (label, section, more words to find it by)
FIGURE_ROWS = (("Width (in)", None, "size figure"), ("Height (in)", None, "size figure"),
               ("Size", None, "preset journal column page"), ("Fit height", None, "size automatic"),
               ("Rows", None, "grid layout"), ("Columns", None, "grid layout"),
               ("Column widths", None, "grid ratio"), ("Row heights", None, "grid ratio"),
               ("Add a panel of", None, "new kind"),
               ("Apply a style preset", None, "journal ams poster talk"),
               ("Annotations", "Annotations", "text arrow line box note"))
SECTION_ROWS = (("Of the layer", "Contour key", "which contours"),
                ("Of the layer", "Maximum and minimum", "which fill extremes"),
                ("In panel", "Legend", "which"), ("From panels", "Legend", "entries lists which"))
RUN_ROWS = (("Label", "name of the run"), ("Colour", "of the run"),
            ("Time zero (min)", "t0 align runs offset"), ("Track file", "storm motion path"),
            ("Add a run", "another compare"))
PANEL_ROWS = (("Title", "of the panel heading"), ("Row label (left)", "row title"),
              ("Row", "place move cell"), ("Column", "place move cell"),
              ("Rows tall", "span cell"), ("Columns wide", "span cell"))
TIMED_ROWS = (("Run", "of the panel"), ("Time", "of the panel when"))
HEIGHT_ROWS = (("Own height", "z of the panel"), ("Height in", "z level model"))
BAR_ROWS = (("Its colours have a bar", "colorbar of the panel"),
            ("The bar it shares", "colorbar group"))
LAYER_ROWS = (("Field", "variable"), ("Colormap", "cmap palette colors"), ("Min", "range vmin limit"),
              ("Max", "range vmax limit"), ("Colour steps", "levels contours discrete"),
              ("Reverse", "colormap flip"), ("Start from white", "colormap"),
              ("Opacity", "alpha transparent"), ("Draw as", "pcolormesh contourf shading"),
              ("Height (km)", "z level"), ("Level", "z model"), ("Blank where", "mask threshold"),
              ("Scale", "multiply"), ("Derivative", "gradient d/dz d/dx"),
              ("Colorbar label", "units"), ("Colorbar ticks", ""), ("Colorbar arrows", "extend"),
              ("Difference", "minus another run time"), ("Ensemble", "statistic several runs mean"),
              ("Over a time window", "average maximum"), ("Keep this time in animations", "lock"),
              ("Add a layer", "contours vectors streamlines shading"))
ENTRY_ROWS = {"sounding": ("Soundings", "where when location point"),
              "th": ("Series", "field run"), "line": ("Series", "field run your own data csv"),
              "dist": ("Distributions", "field region when"), "profile": ("Profiles", "field when"),
              "joint": ("Joint distributions", "fields region"),
              "azim": ("Azimuthal means", "field center"), "table": ("Values", "columns")}
SECTION_WORDS = {"Text": "font size", "Spacing": "gap margin padding", "Legend": "key",
                 "Panel labels": "text"}
EXPORT_ROWS = (("Save to", "path file folder image"), ("Animation", "gif frames movie"),
               ("Template", "save reuse"), ("Download", "image"))


def _plain(text):
    """Words as searched: British spellings and a split "color bar" are the same."""
    text = str(text).lower().replace("colour", "color").replace("centre", "center")
    return text.replace("color bar", "colorbar")


def _title(kinds, section):
    return next((SECTION_NAMES[(k, section)] for k in kinds if (k, section) in SECTION_NAMES),
                section)


def _kinds(doc):
    return list(dict.fromkeys(p["kind"] for p in doc.get("panels") or []))


def _panel_node(doc, picked, kinds=None):
    """The panel a panel's setting goes to: the one picked if it can, else the first that can."""
    if picked is not None and (kinds is None or picked["kind"] in kinds):
        return picked
    return next((p for p in nodes.in_order(doc) if kinds is None or p["kind"] in kinds), None)


def hits_of(shell):
    """Everything Find can go to in this figure, the picked panel's own first."""
    doc, ed = shell.doc, shell.ed
    kinds = _kinds(doc)
    names = nodes.letters(doc)
    picked = nodes.panel_of(doc, shell.node)
    out = []

    def add_rows(rows, where, node, section, title=None):
        words = row_words(ed, [st.key for st in rows])
        for st in rows:
            if st.key == "time_label.t0_min":
                continue  # (an older figure's: it shows only with a value)
            w = table.widget_of(ed, st)
            more = getattr(w, "description", None) or ""
            out.append(Hit(words[st.key], title or section, where, node, st.key,
                           f"{section} {st.key} {more} {SECTION_WORDS.get(section, '')}"))

    def add_hand(label, section, where, node, words=""):
        out.append(Hit(label, section, where, node, None, f"{section or ''} {where} {words}"))

    # (a picked panel's own, first)
    if picked is not None:
        kind, letter = picked["kind"], names[picked["id"]]
        for section, keys in PANEL_KEYS.get(kind, {}).items():
            rows = rows_of(section, [kind], keys)
            add_rows(rows, f"panel {letter}", f"panel:{picked['id']}", section,
                     _title([kind], section))
        if kind == "plan":
            add_hand("Fixed box", "Area", f"panel {letter}", f"panel:{picked['id']}", AREA_WORDS)
    # (the figure's)
    fig = "Figure"
    for section in FIGURE_SECTIONS:
        if section != "Legend" or legend_reaches(doc):
            add_rows(rows_of(section, kinds), fig, nodes.FIGURE, section)
    add_hand("Figure title", None, fig, nodes.FIGURE, "suptitle heading")
    for label, section, words in FIGURE_ROWS:
        add_hand(label, section, fig, nodes.FIGURE, words)
    for label, section, words in SECTION_ROWS:
        if section != "Legend" or legend_reaches(doc):
            add_hand(label, section, fig, nodes.FIGURE, words)
    if "plan" in kinds:
        add_hand("Fill panels", "Fill panels", fig, nodes.FIGURE,
                 "times heights fields runs generate grid")
    # (each kind's)
    for kind in kinds:
        n = sum(1 for p in doc["panels"] if p["kind"] == kind)
        where = f"All {nodes.kind_name(kind, n)}"
        node = f"kind:{kind}"
        for section in KIND_SECTIONS.get(kind, ()):
            add_rows(rows_of(section, [kind]), where, node, section, _title([kind], section))
        if kind == "plan":
            add_hand("Fixed box", "Area", where, node, AREA_WORDS)
        if kind in MAPS:
            at = shell.node if shell.node.startswith("layer:") and picked["kind"] == kind else node
            place = "this layer" if at != node else f"Layers · {where}"
            for label, words in LAYER_ROWS:
                add_hand(label, None, place, at, words)
        if kind == "scene":
            for title in SCENE_SECTIONS:
                keys = " ".join(KEY_NAMES.get(k, k) for k in SCENE_SECTIONS[title][0])
                add_hand(title, title, where, node, f"3d {keys}")
    # (a panel's, at the one picked or the first of its kind)
    for rows, of in ((PANEL_ROWS, None), (TIMED_ROWS, ("plan", "xsec", "scene")),
                     (HEIGHT_ROWS, ("plan",)), (BAR_ROWS, tuple(table.CBAR))):
        p = _panel_node(doc, picked, of)
        if p is None:
            continue
        section = "Colorbar" if rows is BAR_ROWS else None
        for label, words in rows:
            add_hand(label, section, f"panel {names[p['id']]}", f"panel:{p['id']}", words)
    if "xsec" in kinds:
        p = _panel_node(doc, picked, ("xsec",))
        add_hand("Section", None, f"panel {names[p['id']]}", f"panel:{p['id']}",
                 "cross-section line where along through")
    for kind, (label, words) in ENTRY_ROWS.items():
        if kind in kinds:
            p = _panel_node(doc, picked, (kind,))
            add_hand(label, None, f"panel {names[p['id']]}", f"panel:{p['id']}", words)
    # (the runs', and Export's)
    for label, words in RUN_ROWS:
        add_hand(label, None, "Runs", nodes.RUNS, f"{words} run")
    if len(doc.get("runs") or []) > 1:
        add_hand(ed.time_match.name, None, "Runs", nodes.RUNS, "output number align match")
    for st in rows_of("Export", kinds):
        add_rows([st], "Export", EXPORT, "Export")
    for label, words in EXPORT_ROWS:
        add_hand(label, None, "Export", EXPORT, words)
    return out


def _rank(hit, words):
    """How well a hit answers the words (lower: better), or None when it hasn't them all."""
    label = _plain(hit.label)
    rest = _plain(f"{hit.section or ''} {hit.where} {hit.words}")
    score = 0
    for w in words:
        if label.startswith(w):
            continue
        if any(part.startswith(w) for part in label.replace("(", " ").split()):
            score = max(score, 1)
        elif w in label:
            score = max(score, 2)
        elif any(part.startswith(w) for part in rest.replace(".", " ").split()):
            score = max(score, 3)
        elif w in rest:
            score = max(score, 4)
        else:
            return None
    return score


def search(hits, text):
    """The hits with all of the words of text, best first (a tie: as they were)."""
    words = _plain(text).split()
    if not words:
        return []
    ranked = [(r, n) for n, r in enumerate(_rank(h, words) for h in hits) if r is not None]
    return [hits[n] for _, n in sorted(ranked)]


def _row(hit):
    """A hit in words: what it is, and where."""
    place = " · ".join(dict.fromkeys(x for x in (hit.section, hit.where) if x))
    return f"{hit.label} — {place}" if place else hit.label


class Finder:
    def __init__(self, ins):
        self.ins, self.shell = ins, ins.shell
        self.hits = {}
        self.box = pn.widgets.TextInput(placeholder="Find a setting…", margin=(6, 4, 2, 4),
                                        sizing_mode="stretch_width")
        self.rows = TreeView(sizing_mode="stretch_width", margin=(0, 2), visible=False)
        self.note = pn.pane.HTML(margin=(0, 4), sizing_mode="stretch_width", visible=False)
        self.panel = pn.Column(self.box, self.rows, self.note, margin=0,
                               sizing_mode="stretch_width",
                               styles={"position": "sticky", "top": "0", "z-index": "20",
                                       "background": PANEL, "flex": "0 0 auto"})
        self.box.param.watch(lambda ev: self.look_for(ev.new), "value_input")
        self.box.param.watch(lambda ev: self.first(), "enter_pressed")
        self.rows.param.watch(lambda ev: self.pick(ev.new[0]) if ev.new else None, "pick")

    def said(self, text):
        self.note.object = f'<div class="cv-hint">{text}</div>' if text else ""
        self.note.visible = bool(text)

    def look_for(self, text):
        """What has the words typed, listed under the box."""
        if not (text or "").strip() or self.shell.doc is None:
            self._no_rows()
            self.said("")
            return
        found = search(hits_of(self.shell), text)
        self.hits = {str(n): h for n, h in enumerate(found[:MOST])}
        if self.hits:
            self.rows.items = [dict(id=n, label=_row(h), depth=1) for n, h in self.hits.items()]
        self.rows.visible = bool(self.hits)
        more = len(found) - MOST
        self.said("Nothing here has those words." if not found else
                  f"And {more} more: type another word." if more > 0 else "")

    def _no_rows(self):
        """(Hidden, not emptied: emptying a ReactiveHTML's list of dicts raises in Panel 1.7.5.)"""
        self.hits = {}
        self.rows.visible = False

    def first(self):
        """Enter: the best hit."""
        if self.hits:
            self.pick("0")

    def pick(self, row):
        """Go to a hit: its node, with its section first and open."""
        hit = self.hits.get(row)
        if hit is None:
            return
        self.box.param.update(value="", value_input="")
        self._no_rows()
        self.said("")
        if hit.node == EXPORT:
            self.shell.export.open()
            return
        place = f", in {html.escape(hit.section)}" if hit.section else ""
        self.said(f"<b>{html.escape(hit.label)}</b>{place}.")
        self.ins.go_to(hit.node, hit.section, hit.key)
