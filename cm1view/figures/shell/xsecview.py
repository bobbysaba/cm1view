"""Cross-sections in the inspector: plan views' pane (shared layers, what differs in a panel, the
look), where a panel also shows a section.  Where you click says what an edit reaches:

  All cross-sections   the sections, the shared layers, the height and x axis, the look; new panels
  a panel              its run, time and section, its layers, its look
  a layer              that layer in that panel"""

import html

import panel as pn

from .. import spec as fg
from ..cards import _grid
from ..times import _nearest_t
from . import docedit as de, nodes
from .planview import PlanPane
from .sectionrow import section_objs, section_row


def _note(text):
    return pn.pane.HTML(f'<div class="cv-hint">{text}</div>', margin=(2, 4),
                        sizing_mode="stretch_width")


def _button(name, on_click, tip="", primary=False):
    b = pn.widgets.Button(name=name, height=32, margin=(4, 4), description=tip or None,
                          button_type="primary" if primary else "light", button_style="outline")
    b.on_click(lambda e: on_click())
    return b


class XsecPane(PlanPane):
    kind = "xsec"

    def _kind_tools(self, doc):
        return [pn.Row(_button("+ Cross-section panel", lambda: self.ins.grid.add_panel("xsec"),
                               primary=True, tip="Like the last, showing a new section: an x–z "
                                                 "one's y–z twin. In the first free cell, or a "
                                                 "new row or column"), margin=0),
                *self.ins.grid.titles_objs("xsec")]

    def _kind_sections(self, doc):
        return section_objs(self.ins, doc)

    def _look_extras(self):
        return {}

    def panel_objs(self, doc, node):
        p = nodes.panel_of(doc, node)
        pid, letter = p["id"], nodes.letters(doc)[p["id"]]
        shell = self.shell

        def set_keys(**kw):
            def apply(d):
                q = de.panel_by_id(d, pid)
                for k, v in kw.items():
                    if v is None:
                        q.pop(k, None)
                    else:
                        q[k] = v
            shell.edit(apply)

        title = pn.widgets.TextInput(name="Title", value=p.get("title") or "",
                                     sizing_mode="stretch_width")
        title.param.watch(lambda ev: set_keys(title=ev.new.strip()), "value")
        rowlabel = pn.widgets.TextInput(name="Row label (left)", value=p.get("rowlabel") or "",
                                        placeholder="none")
        rowlabel.param.watch(lambda ev: set_keys(rowlabel=ev.new.strip() or None), "value")
        run, time = self._run_time(doc, p)
        objs = [title, _grid(run, time, rowlabel, n=2), *self._section_objs(doc, p),
                _button("One per run", lambda: self.one_per_run(pid),
                        tip="A copy of this panel for each other run, down its column, at the "
                            "same time since time zero")]
        return f"Panel {letter}", objs + self._panel_rest(doc, p)

    # ------------------------------------------------------------ a panel's section
    def _section_objs(self, doc, p):
        """Which section a panel shows, and that section's settings (which reach what else shows
        it, it says; it can then have its own)."""
        pid, shell = p["id"], self.shell
        secs = doc.get("sections") or {}
        if not secs:
            return [_note("No section yet."), _button("+ Section", lambda: self.new_section(pid))]
        opts = {f"{k + 1}: {s.get('label') or fg.describe(s)}": sid
                for k, (sid, s) in enumerate(secs.items())}
        sid = p.get("section") if p.get("section") in secs else next(iter(secs))
        pick = pn.widgets.Select(name="Section", options=opts, value=sid,
                                 sizing_mode="stretch_width")
        pick.param.watch(lambda ev: shell.edit(
            lambda d: de.panel_by_id(d, pid).update(section=ev.new), node=shell.node), "value")

        def words(now):
            names = nodes.letters(now)
            others = [q for q in de.section_panels(now, sid) if q["id"] != pid]
            if not others:
                return []
            n = len(others)
            apart = pn.widgets.Button(name="Keep apart", height=26, margin=(2, 4),
                                      button_type="light", button_style="outline",
                                      description="This panel gets a copy of the section of its "
                                                  "own; the others keep this one")
            apart.on_click(lambda e: self.keep_apart(pid))
            return [_note(f"<b>Panel{'s' if n > 1 else ''} "
                          + html.escape(", ".join(names[q["id"]] for q in others))
                          + f" show{'' if n > 1 else 's'} this section too:</b> changes here "
                            "reach them."), apart]

        return [pn.Row(pick, _button("+ Section", lambda: self.new_section(pid),
                                     tip="A new section for this panel: an x–z one's y–z twin, "
                                         "along the motion's across one"),
                       margin=0, sizing_mode="stretch_width"),
                section_row(self.ins, doc, sid, where=f"{pid}:", opened=True, words=words).panel]

    def new_section(self, pid):
        def apply(d):
            p = de.panel_by_id(d, pid)
            now = (d.get("sections") or {}).get(p.get("section"))
            p["section"] = de.add_section(d, de.twin_section(now) if now else fg.section_defaults())
        self.shell.edit(apply, node=self.shell.node)

    def keep_apart(self, pid):
        self.shell.edit(lambda d: de.split_section(d, pid), node=self.shell.node)

    def one_per_run(self, pid):
        shell, doc = self.shell, self.shell.doc
        if len(doc["runs"]) < 2:
            shell.say("The figure has one run: add others first (Runs).", True)
            return
        p = de.panel_by_id(doc, pid)
        times = {}
        for r in doc["runs"]:
            if p.get("time_s") is not None:
                ts = de._moved(doc, p["time_s"], p["run"], r["id"])
                tl = list(shell.time_opts(de.run_index(doc, r["id"])).values())
                times[r["id"]] = _nearest_t(tl, ts) if tl else ts
        if not de.panel_per_run(de.plain(doc), pid, times):
            shell.say("Every run has this section already.", True)
            return
        shell.edit(lambda d: de.panel_per_run(d, pid, times), node=shell.node)
