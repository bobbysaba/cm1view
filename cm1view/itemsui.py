"""The items tray under the map: what has been made (map view, soundings, section,
3D box, series), to reopen, remove or make a figure from.

A mixin of the Viewer (cm1view/app.py): its methods use the Viewer's widgets and state."""

from functools import partial

import numpy as np
import panel as pn

from . import series as ser
from .theme import POINT_COLORS, POINT_LABELS
from .ui import _group, _html


class ItemsTray:
    def _build_items(self):
        """The tray under the map: what has been made (soundings, section, 3D box,
        series), each removable, each kind with a way into a figure."""
        self.items_bar = pn.Row(
            margin=0, sizing_mode="stretch_width",
            styles={"flex": "0 0 auto", "height": "44px", "overflow-x": "auto",
                    "overflow-y": "hidden", "padding": "4px 12px 0 60px",
                    "align-items": "center", "gap": "8px"})
        self._items_key = None

    def _item_entries(self):
        """(kind, key, label, colour) of every item, in tray order."""
        run, out = self.run, []
        for n, (kind, where, tp) in enumerate(self.points):
            if kind == "mean":
                lab = "domain mean"
            elif kind == "trk":
                lab = ("meso" if not any(where[:2]) else
                       f"meso {where[0]:+.1f}, {where[1]:+.1f} km")
            else:
                lab = f"({where[0]:.1f}, {where[1]:.1f}) km"
            if len(where or ()) == 4:
                lab = f"box {where[2]:.3g}×{where[3]:.3g} km at {lab}"
            if tp is not None:
                lab += f" · {run.time_label(tp)}"
            out.append(("snd", n, f"{POINT_LABELS[n]} {lab}", POINT_COLORS[n]))
        if len(self.xs_pts) == 2:
            (ax, ay), (bx, by) = self.xs_pts
            out.append(("xs", 0, f"Section A–B · {np.hypot(bx - ax, by - ay):.1f} km", ""))
        if self.box is not None:
            x0, x1, y0, y1 = self.box
            out.append(("box", 0, f"3D box · {x1 - x0:.1f} × {y1 - y0:.1f} km", ""))
        for k, v in getattr(self, "series", {}).items():
            out.append(("ser", k, v["label"], v["color"]))
        return out

    def _update_items(self):
        if not hasattr(self, "items_bar"):
            return
        entries = self._item_entries()
        if entries == self._items_key:
            return
        self._items_key = entries
        ib = dict(button_type="light", height=30, margin=(4, 0))

        def icon(name, tip, cb):
            b = pn.widgets.Button(name="", icon=name, description=tip, width=30, **ib)
            b.on_click(lambda e: cb())
            return b

        def label(text, cb, color="", tip=""):
            dot = (f'<span style="color:{color}">●</span> ' if color else "")
            b = pn.widgets.Button(name=text, description=tip or None, **ib,
                                  stylesheets=[".bk-btn { max-width: 300px; overflow: hidden;"
                                               " text-overflow: ellipsis; white-space: nowrap;"
                                               " }"])
            b.on_click(lambda e: cb())
            return [_html(dot, margin=(0, 0, 0, 6), align="center"), b] if dot else [b]

        def group(*objs):
            g = _group(*objs)
            g.margin = 0
            g.styles = dict(g.styles, flex="0 0 auto", height="38px")
            return g

        def to_fig(make):
            def go():
                make()
                self.workspace.value = "Figure"
            return go

        groups = [group(*label("Map view", lambda: None, tip="What the map shows now"),
                        icon("photo", "Make a figure of the map view", to_fig(
                            self.figed.from_map)))]
        snd = [e for e in entries if e[0] == "snd"]
        if snd:
            objs = [_html('<span class="cv-hint">Soundings</span>', margin=(0, 4, 0, 6),
                          align="center")]
            for _, n, lab, col in snd:
                objs += label(lab, lambda: self._show_panel(True, 0), col)
                objs.append(icon("x", "Remove this sounding", partial(self._remove_point, n)))
            objs.append(icon("photo", "Make a figure of these soundings (skew-T)",
                             to_fig(self.figed.from_soundings)))
            groups.append(group(*objs))
        for kind, k, lab, col in entries:
            if kind == "xs":
                groups.append(group(
                    *label(lab, lambda: self._show_panel(True, 1)),
                    icon("x", "Remove the section", self._remove_xs),
                    icon("photo", "Make a figure of the section", to_fig(
                        self.figed.from_xsec))))
            elif kind == "box":
                groups.append(group(
                    *label(lab, self._open_3d, tip="Show it in the 3D view"),
                    icon("x", "Remove the 3D box", self._remove_box),
                    icon("cube", "Show it in the 3D view", self._open_3d)))
        ser = [e for e in entries if e[0] == "ser"]
        if ser:
            objs = [_html('<span class="cv-hint">Series</span>', margin=(0, 4, 0, 6),
                          align="center")]
            for _, k, lab, col in ser:
                objs += label(lab, partial(self._show_series, k), col)
                objs.append(icon("x", "Remove this series", partial(self._on_ser_remove,
                                                                     None, k)))
            objs.append(icon("photo", "Make a figure of the series (time–height or "
                                      "time series)", to_fig(self.figed.from_series)))
            groups.append(group(*objs))
        self.items_bar.objects = groups

    def _remove_point(self, n):
        if n < len(self.points):
            self.points.pop(n)
            self._draw_points()
            self.request_soundings()

    def _remove_xs(self):
        self.xs_pts = []
        self._draw_xs()

    def _remove_box(self):
        self.box = None
        self.box_src.data = dict(left=[], right=[], bottom=[], top=[])
        self._update_region_html()

    def _open_3d(self):
        self.workspace.value = "3D"
        if self.gen["3d"] == 0:  # nothing rendered yet
            self.request_3d()

    def _show_series(self, key):
        self._show_panel(True, 3)
        self.ser_pick.value = key
