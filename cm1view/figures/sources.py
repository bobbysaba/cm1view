"""Figure editor: new figures from the map, the cross-section, the series, the
soundings and the distributions, and the series / sounding / distribution / profile /
joint distribution / azimuthal mean / annotation lists.  (The data of a figure is
FigureData's, figures/render.py.)

A mixin of the FigureEditor (figures/editor.py)."""

import json

import panel as pn

from . import draw as figdraw, spec as fg
from ..core import render, series as ser, vectors
from .cards import (AnnotationRow, AzimCard, DistCard, JointCard, LEVEL_MODES, ProfileCard,
                    ProfileDataCard,
                    DataCard, SeriesCard, SoundingCard, _dark)
from ..viewer.ui import held


class FigureSources:
    # ------------------------------------------------------------ start from
    def _default(self):
        """2 x 3 grid in time from the shown time: centred on the storm when there is a
        track, else the whole domain."""
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        if not self.v.fixes:
            s["domain"] = dict(s["domain"], mode="full")
        return s

    def _own_track(self):
        """Track of this run in a new figure: the Track tab's when it has one, else a
        storm_tracks file next to the run (the Track tab when there is neither)."""
        return "viewer" if self.v.fixes else (fg.find_track(self.run.path) or "viewer")

    def _keep_runs(self, s):
        """A new spec of this run keeps the runs already added (this run selected)."""
        s["runs"][0]["track"] = self._own_track()
        if self.run_rows:
            runs = self._runs_collect()
            paths = [r["path"] for r in runs]
            if self.run.path not in paths:
                runs.insert(0, fg.run_entry(self.run, "viewer"))
                paths.insert(0, self.run.path)
            s["runs"], s["run"] = runs, paths.index(self.run.path)
        return s

    def _times(self, s, times, t):
        s.update(times=list(times), time=t,
                 times_s=[float(self.run.times[k]) for k in times],
                 time_s=float(self.run.times[t]))
        return s

    def _minus(self, s, lay, m, rng):
        """Fill layer `lay` of figure spec s as the viewer's difference m (_minus_spec;
        another run is added to the figure's runs), in the colours it is shown in:
        range rng (lo, hi)."""
        if not m:
            return
        run = None
        if m["path"]:
            other, _ = self.open_run(m["path"])
            paths = [r["path"] for r in s["runs"]]
            if other.path not in paths:
                s["runs"].append(fg.run_entry(other, ""))
                paths.append(other.path)
            run = paths.index(other.path)
        t = self.v.t
        ts = None if m["time"] == "" else float(self.run.times[max(t - 1, 0)]) \
            if m["time"] == "prev" else float(m["time"])
        lay.update(minus=dict(run=run, time_s=ts, grid="interp"), cmap="RdBu", reverse=True,
                   white_first=False, mask_below=None, scale="linear")
        if rng:
            lay.update(vmin=round(float(rng[0]), 6), vmax=round(float(rng[1]), 6))

    def from_map(self):
        """A one-panel figure of what the map shows (field, levels, contours, vectors,
        view), at the shown time."""
        v, F, t = self.v, self.F, self.v.t
        sp = v._map_spec()

        def fill_layer(f):
            fill = fg.layer_defaults("fill", F, f["var"], f["level"])
            fill.update(mode=f["mode"] if f["mode"] in LEVEL_MODES.values() else "height",
                        cmap=f["cmap"], reverse=f["rev"])
            try:  # the range the map shows
                a = F.plane(f["var"], t, fill["mode"], f["level"], storm=sp["fstorm"])
                lo, hi = F.auto_range(f["var"], a) if f["auto"] else (f["vmin"], f["vmax"])
                fill.update(vmin=round(float(lo), 6), vmax=round(float(hi), 6))
            except Exception:  # noqa: BLE001
                pass
            return fill

        layers = [fill_layer(sp["fill"])]
        for f in sp["fills"]:  # the more fills, over the first
            if not f["on"]:
                continue
            lay = fill_layer(f)
            lay.update(alpha=float(f["alpha"]),
                       style="contourf" if f["style"] == "contourf" else "mesh",
                       nlevels=int(f["nlev"]) if f["style"] == "contourf" else 0,
                       mask_below=lay.get("vmin") if f["clip"] else None)
            layers.append(lay)
        for o in sp["ov"]:
            if not o["on"]:
                continue
            lay = fg.layer_defaults("contour", F, o["var"], o["level"])
            try:
                a = F.plane(o["var"], t, o["mode"], o["level"], storm=sp["fstorm"])
                lo, hi = F.auto_range(o["var"], a)
                lv = render.parse_levels(o["levels"], lo, hi)
                lay["levels"] = ", ".join(f"{x:g}" for x in lv)
            except Exception:  # noqa: BLE001
                pass
            lay.update(mode=o["mode"], color=_dark(o["color"]), lw=0.75 * float(o["width"]),
                       neg_dashed=o["negdash"])
            layers.append(lay)
        for o in sp["vecs"]:
            if not o["on"]:
                continue
            lay = fg.layer_defaults("vectors", F)
            lay.update(vector=o["q"], z=o["level"], frame=o["frame"], style=o["style"],
                       color=_dark(o["color"]), scale=vectors.FIG_SCALE * o["ref"])
            layers.append(lay)
        s = self._keep_runs(fg.default_spec(self.run, F, t))
        self._times(s, [t], t)
        self._minus(s, layers[0], sp["fill"].get("minus"), v._last_range)
        s.update(rows=1, cols=1, size=[5.0, 4.5], layers=layers, vary="time", kind="plan")
        s["domain"] = dict(s["domain"], mode="box", box=[float(x) for x in v.view])
        s["colorbar"] = dict(s["colorbar"], mode="each", orientation="vertical", shrink=0.9)
        s["axes"] = dict(s["axes"], ticklabels="all")
        self.set_spec(s)

    def from_xsec(self):
        v, F, t = self.v, self.F, self.v.t
        if len(v.xs_pts) != 2:
            self._msg("Draw a cross-section on the map first (Section tool).", True)
            return
        def fill_layer(f):
            fill = fg.layer_defaults("fill", F, f["var"])
            fill.update(cmap=f["cmap"], reverse=f["rev"],
                        style="contourf" if f["style"] == "contourf" else "mesh",
                        nlevels=int(f["nlev"]) if f["style"] == "contourf" else 0)
            if not f["auto"]:
                fill.update(vmin=float(f["vmin"]), vmax=float(f["vmax"]))
            return fill

        sp = v.xs_spec()
        layers = [fill_layer(dict(sp, var=sp["fill"]))]
        for f in sp["fills"]:  # the more fills, over the first
            if f["on"]:
                lay = fill_layer(f)
                lay.update(alpha=float(f["alpha"]),
                           mask_below=lay.get("vmin") if f["clip"] else None)
                layers.append(lay)
        for o in sp["ov"]:
            if o["on"]:
                lay = fg.layer_defaults("contour", F, o["var"])
                lay.update(levels=o["levels"] if o["levels"].strip() not in ("", "auto")
                           else "10, 20", color=_dark(o["color"]),
                           lw=0.75 * float(o["width"]), neg_dashed=o["negdash"])
                layers.append(lay)
        for o in sp["vecs"]:
            if o["on"]:
                lay = fg.layer_defaults("vectors", F)
                lay.update(vector=o["q"], frame=o["frame"], spacing=0.75,
                           scale=20.0 * o["ref"], width=0.0015, color=_dark(o["color"]))
                layers.append(lay)
        s = self._keep_runs(fg.default_spec(self.run, F, t))
        self._times(s, [t], t)
        self._minus(s, layers[0], sp["minus"], v._xs_range)
        s.update(kind="xsec", rows=1, cols=1, size=[7.0, 3.5], layers=layers, vary="time")
        s["xsec"] = dict(s["xsec"], ztop=float(v.xs_ztop.value))
        s["sections"] = [fg.section_defaults(orient="ab", pos="fixed", a=list(v.xs_pts[0]),
                                             b=list(v.xs_pts[1]))]
        s["axes"] = dict(s["axes"], xlabel="", ylabel="height (km)",
                         ticklabels="all")
        s["colorbar"] = dict(s["colorbar"], mode="each", orientation="vertical", shrink=0.9)
        self.set_spec(s)

    # ------------------------------------------------------------ series cards
    def _ser_card(self, e):
        c = DataCard(self, e) if fg.is_table(e) else SeriesCard(self, e)
        c.up.on_click(lambda ev: self._move_ser(c, -1))
        c.down.on_click(lambda ev: self._move_ser(c, 1))
        c.rm.on_click(lambda ev: self._remove_ser(c))
        c.dup.on_click(lambda ev: self._dup_series(c))
        if not isinstance(c, DataCard):
            c.per_run.on_click(lambda ev: self._per_run_series(c))
        return c

    def _show_series(self):
        for c in self.ser_cards:
            c.show(self.kind.value)
        self.ser_data.visible = self.kind.value == "line"
        self.ser_box.objects = [c.panel for c in self.ser_cards] or [pn.pane.HTML(
            '<div class="cv-empty">No series yet, so nothing is computed: add one of the '
            'Series tool’s (above) or a new one.</div>')]
        ss = getattr(self.v, "series", {}) or {}
        self.ser_from.options = {"": ""} | {v["label"]: k for k, v in ss.items()}
        if not self.ser_from.value and ss:  # (the Series tool's shown series, ready to add)
            act = getattr(getattr(self.v, "ser_pick", None), "value", None)
            self.ser_from.value = act if act in ss else next(iter(ss))

    def _series_changed(self):
        self._show_series()
        self._fit_grid()
        self.request()

    def _free_ser_panel(self):
        """The first panel number no series card is in."""
        used = {int(c.w["panel"].value or 1) - 1 for c in self.ser_cards}
        return next(p for p in range(len(used) + 1) if p not in used)

    def _new_series(self, ents, at=None, wide=True):
        """Cards for series entries ents (after card `at`, else after the others; wide:
        a grid of one row widens for them, else it grows down)."""
        new = [self._ser_card(e) for e in ents]
        i = self.ser_cards.index(at) + 1 if at in self.ser_cards else len(self.ser_cards)
        self.ser_cards[i:i] = new
        self._show_series()
        self._fit_grid(wide=wide)
        self._build_titles()
        self.request()

    def _dup_series(self, c):
        """A copy of card c in a new panel."""
        self._new_series([dict(c.collect(), panel=self._free_ser_panel())], at=c)

    def _per_run_series(self, c):
        """Time series: card c of several runs (or every run) becomes a card per run in
        its panel, each in the run's colour; of one run, a copy for each other run of
        the figure in its panel.  Time-height: a copy for each other run down c's column
        (run j's in row j after c's, or the next free panel).  A run with the same
        series in that panel (time-height: anywhere) already is skipped."""
        s, names = c.collect(), self._run_names()
        line = self.kind.value == "line"
        runs = sorted(names.values())
        spec = dict(runs=self._runs_collect())  # (the runs' colours)
        if line and (s["runs"] is None or len(s["runs"]) > 1):  # (several runs)
            ks = s["runs"] or runs
            if len(ks) < 2:
                self._msg("The figure has one run: add others first (pick one in a "
                          "card's <b>Run</b> list).", True)
                return
            ents = [dict(s, runs=[k], ens="", color=figdraw.run_color(spec, k))
                    for k in ks]
            i = self.ser_cards.index(c)
            self.ser_cards.remove(c)
            self.ser_cards[i:i] = [self._ser_card(e) for e in ents]
            self._series_changed()
            self._build_titles()
            return
        k0 = s["runs"][0]
        others = [k for k in runs if k != k0]
        if not others:
            self._msg("The figure has one run: add others first (pick one in a card's "
                      "<b>Run</b> list).", True)
            return
        key = json.dumps(s["recipe"], sort_keys=True, default=float)
        have = {(x["runs"][0] if x["runs"] else -1,
                 x["panel"] if line else -1, json.dumps(x["recipe"], sort_keys=True,
                                                         default=float))
                for x in (y.collect() for y in self.ser_cards) if not fg.is_table(x)}
        C = int(self.cols.value or 1)
        row, col = divmod(s["panel"], C)
        taken = {int(x.w["panel"].value or 1) - 1 for x in self.ser_cards}
        new = []
        for j, k in enumerate(others):
            if (k, s["panel"] if line else -1, key) in have:
                continue
            if line:  # (in the run's colour)
                new.append(dict(s, runs=[k], color=figdraw.run_color(spec, k)))
                continue
            p = (row + j + 1) * C + col
            while p in taken:
                p += 1
            taken.add(p)
            new.append(dict(s, runs=[k], panel=p))
        if not new:
            self._msg("Every run has this series already.", True)
            return
        self._new_series(new, at=c, wide=line)  # (time-height: down the column)

    def _th_cards_from_line(self):
        """Time series become time-height panels: a card per series and run (a card of
        every run or several runs: one for each), each in a panel of its own: a row
        per run when the series split all have the same runs, else its panel when no
        card before it is there (else the next free one)."""
        names = sorted(self._run_names().values())
        mine = [c for c in self.ser_cards if isinstance(c, DataCard)]  # (stay as they are)
        ents = [c.collect() for c in self.ser_cards if c not in mine]
        own = [e["runs"] or names for e in ents]
        split = any(len(ks) > 1 for ks in own)
        alike = split and all(r == own[0] for r in own)
        out, taken = [], set()
        for n, (e, ks) in enumerate(zip(ents, own)):
            for j, k in enumerate(ks):
                p = j * len(ents) + n if alike else int(e["panel"])
                while p in taken:
                    p += 1
                taken.add(p)
                out.append(dict(e, runs=[k], panel=p))  # (its band: back as time series)
        if out != ents:
            self.ser_cards = [self._ser_card(e) for e in out] + mine

    def _line_cards_from_th(self):
        """Time-height panels become time series: the cards of one series (alike but
        for their run and panel) one card of their runs (every run: All runs), a panel
        per series."""
        if not any(c._kind == "th" for c in self.ser_cards):
            return
        names = sorted(self._run_names().values())
        mine = [c for c in self.ser_cards if isinstance(c, DataCard)]  # (stay as they are)
        groups = {}
        for e in (c.collect() for c in self.ser_cards if c not in mine):
            key = json.dumps({k: v for k, v in e.items() if k not in ("runs", "panel")},
                             sort_keys=True, default=float)
            groups.setdefault(key, (e, []))[1].extend(e["runs"] or names)
        out = []
        for n, (e, ks) in enumerate(groups.values()):
            ks = sorted(set(ks))
            out.append(dict(e, runs=None if ks == names and len(ks) > 1 else ks, panel=n))
        self.ser_cards = [self._ser_card(e) for e in out] + mine

    def _move_ser(self, c, d):
        i = self.ser_cards.index(c)
        j = min(max(i + d, 0), len(self.ser_cards) - 1)
        self.ser_cards[i], self.ser_cards[j] = self.ser_cards[j], self.ser_cards[i]
        self._series_changed()

    def _remove_ser(self, c):
        self.ser_cards.remove(c)
        self._series_changed()

    def _tab_series(self, key):
        """A spec["series"] entry of a series of the Series tab."""
        s = self.v.series[key]
        r = dict(s["recipe"])
        e = fg.series_defaults(self.F, r, len(self.ser_cards))
        e["panel"] = 0
        return e

    def _add_series_from_tab(self):
        key = self.ser_from.value
        if not key or key not in getattr(self.v, "series", {}):
            return
        e = self._tab_series(key)
        if self.kind.value == "th":  # (a panel of its own, of the figure's own run)
            e.update(panel=self._free_ser_panel(), runs=[self._own_index()])
        self.ser_cards.append(self._ser_card(e))
        self._series_changed()

    def _new_recipe(self):
        """A recipe for a new series: max w in 0–10 km near the storm (whole domain
        without a track), as for updraft time-height plots."""
        f = "winterp" if "winterp" in self.F else next(iter(self.F.defs))
        track = bool(self.v.fixes) or any(r.get("track") for r in self._runs_collect())
        return ser.normalize(dict(field=f, vmode="layer", z0=0.0, z1=10.0,
                                  region="track" if track else "domain", radius=5.0,
                                  offset=(0.0, 0.0), reduce="max"))

    def _add_series(self):
        e = fg.series_defaults(self.F, self._new_recipe(), len(self.ser_cards))
        e["panel"] = self._free_ser_panel()
        if self.kind.value == "th":  # (the last card's run, else the figure's own)
            last = self.ser_cards[-1].run_list() if self.ser_cards else None
            e["runs"] = [last[0] if last else self._own_index()]
        self.ser_cards.append(self._ser_card(e))
        self._series_changed()

    def _add_data(self):
        """A card of your own data, in the last card's panel (to compare with it)."""
        e = fg.table_defaults(len(self.ser_cards))
        e["panel"] = int(self.ser_cards[-1].w["panel"].value or 1) - 1 if self.ser_cards else 0
        self.ser_cards.append(self._ser_card(e))
        self._series_changed()

    def _fit_grid(self, reset=False, wide=False):
        """Time-series / sounding / distribution / section figures: enough grid cells
        for the highest panel number of the cards (reset: a column of up to 3, else 2
        columns; sections of several runs, as many alike: a row per run; else the grid
        only grows, keeping the rows and columns the user set; wide: a grid of one row
        widens, up to 3 columns)."""
        kind = self.kind.value
        if kind not in ("line", "th", "sounding", "dist", "profile", "joint", "azim",
                        "xsec"):
            return
        cards = {"line": self.ser_cards, "th": self.ser_cards, "sounding": self.snd_cards,
                 "dist": self.dist_cards, "profile": self.prof_cards,
                 "joint": self.joint_cards, "azim": self.azim_cards,
                 "xsec": self.sec_cards}[kind]
        if kind == "th":  # (your own data: time series only)
            cards = [c for c in cards if not isinstance(c, DataCard)]
        n = 1 + max([max(0, int(c.w["panel"].value or 1) - 1) for c in cards] or [0])
        r, c = int(self.rows.value or 1), int(self.cols.value or 1)
        runs = len({c.w["run"].value for c in cards}) if kind in ("xsec", "th") else 1
        if reset and runs > 1 and n % runs == 0:
            r, c = runs, n // runs
        elif reset:
            r, c = (n, 1) if n <= 3 else ((n + 1) // 2, 2)
        elif wide and r == 1 and n <= 3:
            c = max(c, n)
        elif r * c < n:
            r = -(-n // c)
        if (r, c) != (self.rows.value, self.cols.value):
            with held(self):
                self.rows.value, self.cols.value = r, c
            self._fit_size()
            self._build_titles()

    def _fit_size(self):
        """A size for the grid (plan views and sections: the height for the width)."""
        kind, r, c = self.kind.value, int(self.rows.value or 1), int(self.cols.value or 1)
        if not self._auto_size:
            return
        if kind in ("plan", "xsec"):
            self._follow_size()
            return
        if kind == "th":
            w, h = 4.5 * c + 1.0, 2.8 * r + 0.6
        elif kind == "sounding":
            lay = self.sk["layout"].value
            w = {"side": 8.2, "hodo": 4.5}.get(lay, 5.0) * c + 0.5
            h = (4.5 if lay == "hodo" else 5.0) * r
            if self.sk["table"].value:  # (a row per sounding of the fullest panel)
                per = max([sum(int(c.w["panel"].value or 1) == p + 1 for c in self.snd_cards)
                           for p in range(r * c)] or [1])
                h += r * (0.45 + 0.25 * per)
        elif kind == "dist":
            w, h = (5.5 if c == 1 else 4.2 * c), 3.6 * r + 0.3
        elif kind == "profile":
            w, h = (4.0 if c == 1 else 3.4 * c) + 0.4, 4.6 * r + 0.3
        elif kind == "joint":  # (with its colorbar)
            w, h = (5.2 if c == 1 else 4.4 * c) + 0.3, 4.0 * r + 0.3
        elif kind == "azim":  # (with its colorbar)
            w, h = (5.6 if c == 1 else 4.6 * c) + 0.3, 3.8 * r + 0.3
        elif kind == "scene":  # (one picture, its colorbars beside it)
            w, h = 6.5, 5.2
        else:
            w, h = (7.0 if c == 1 else 6.0 * c), 3.0 * r + 0.5
        with held(self):
            self.width.value, self.height.value = round(min(16.0, w), 2), round(min(16.0, h), 2)
            self.size_preset.value = ""

    def _size_by_hand(self):
        if not self._hold:
            self._auto_size = False
            with held(self):
                self.size_preset.value = ""

    # ------------------------------------------------------------ entry cards
    @staticmethod
    def _listed(box, cards, empty):
        """Drawer box shows the cards' panels, or (none) the words empty."""
        box.objects = [c.panel for c in cards] or [pn.pane.HTML(
            f'<div class="cv-empty">{empty}</div>')]

    def _cards_changed(self, show, fit=True):
        """Cards added or removed: show() lists them again; fit: the grid of panels
        fitted to them; the preview drawn again."""
        show()
        if fit:
            self._fit_grid()
        self.request()

    def _entry_card(self, cls, e, remove):
        c = cls(self, e)
        c.rm.on_click(lambda ev: remove(c))
        return c

    def _from_tool(self, cards, new, make, show, none):
        """Cards (make(entry)) for entries `new` of a viewer tool; none: what to say
        when there are none."""
        if not new:
            self._msg(none, True)
            return
        cards.extend(make(e) for e in new)
        self._cards_changed(show, fit=False)

    # ------------------------------------------------------------ sounding cards
    def _snd_card(self, e):
        return self._entry_card(SoundingCard, e, self._remove_snd)

    def _show_soundings(self):
        self._listed(self.snd_box, self.snd_cards, "No soundings: add the map's, or a new one.")

    def _remove_snd(self, c):
        self.snd_cards.remove(c)
        self._cards_changed(self._show_soundings, fit=False)

    def _own_index(self):
        paths = [r["path"] for r in self.run_rows]
        return paths.index(self.run.path) if self.run.path in paths else 0

    def tab_soundings(self):
        """spec["soundings"] entries of the Sounding tab's soundings (this run)."""
        out = []
        for n, (kind, where, tp) in enumerate(self.v.points):
            t = self.v.t if tp is None else tp
            if kind == "mean":
                wh = dict(kind="mean", x=0.0, y=0.0, avg=0.0)
            else:
                avg = (0.5 * (where[2] + where[3]) if len(where) == 4
                       else float(self.v.avg.value or 0.0) if hasattr(self.v, "avg") else 0.0)
                wh = dict(kind=kind, x=float(where[0]), y=float(where[1]), avg=float(avg))
            out.append(fg.sounding_defaults(self._own_index(), float(self.run.times[t]), wh,
                                            n + len(self.snd_cards)))
        return out

    def _add_tab_soundings(self):
        self._from_tool(self.snd_cards, self.tab_soundings(), self._snd_card,
                        self._show_soundings, "No soundings yet: click the map with the "
                        "Sounding tool first, or add one here.")

    def _add_sounding(self):
        e = fg.sounding_defaults(self._own_index(), float(self.run.times[self.v.t]),
                                 dict(kind="trk", x=0.0, y=0.0, avg=0.0), len(self.snd_cards))
        e["panel"] = len(self.snd_cards)
        self.snd_cards.append(self._snd_card(e))
        self._cards_changed(self._show_soundings)

    # ------------------------------------------------------------ distribution cards
    def _dist_card(self, e):
        return self._entry_card(DistCard, e, self._remove_dist)

    def _show_dists(self):
        self._listed(self.dist_box, self.dist_cards, "No distributions: add the map's "
                     "(Distribution tool), or a new one.")

    def _remove_dist(self, c):
        self.dist_cards.remove(c)
        self._cards_changed(self._show_dists)

    def tab_dists(self):
        """spec["dists"] entries of the Distribution tool's distributions (this run),
        all in the first panel."""
        out = []
        for n, s in enumerate((getattr(self.v, "dists", {}) or {}).values()):
            out.append(fg.dist_defaults(s["recipe"], self._own_index(),
                                        float(self.run.times[s["t"]]),
                                        n + len(self.dist_cards)))
        return out

    def _add_tab_dists(self):
        self._from_tool(self.dist_cards, self.tab_dists(), self._dist_card, self._show_dists,
                        "No distributions yet: compute one with the Distribution tool on "
                        "the map first, or add one here.")

    def _new_dist_recipe(self):
        """A recipe for a new distribution: w over the whole domain at 1 km."""
        f = "winterp" if "winterp" in self.F else next(iter(self.F.defs))
        return dict(field=f, vmode="height", z=1.0, region="domain")

    def _add_dist(self):
        e = fg.dist_defaults(self._new_dist_recipe(), self._own_index(),
                             float(self.run.times[self.v.t]), len(self.dist_cards))
        e["panel"] = 0
        self.dist_cards.append(self._dist_card(e))
        self._cards_changed(self._show_dists)

    # ------------------------------------------------------------ profile cards
    def _prof_card(self, e):
        c = ProfileDataCard(self, e) if fg.is_table(e) else ProfileCard(self, e)
        c.rm.on_click(lambda ev: self._remove_prof(c))
        c.dup.on_click(lambda ev: self._dup_prof(c))
        if not fg.is_table(e):
            c.per_run.on_click(lambda ev: self._per_run_prof(c))
        return c

    def _add_prof_data(self):
        """A card of your own profile data, in the last card's panel (to compare with
        it)."""
        e = fg.profile_table_defaults(len(self.prof_cards))
        e["panel"] = int(self.prof_cards[-1].w["panel"].value or 1) - 1 \
            if self.prof_cards else 0
        self.prof_cards.append(self._prof_card(e))
        self._cards_changed(self._show_profiles)

    def _new_profs(self, ents, at):
        """Cards for profile entries ents after card `at`."""
        i = self.prof_cards.index(at) + 1 if at in self.prof_cards else len(self.prof_cards)
        self.prof_cards[i:i] = [self._prof_card(e) for e in ents]
        self._show_profiles()
        self._fit_grid()
        self._build_titles()
        self.request()

    def _dup_prof(self, c):
        """A copy of card c in a new panel (the first no profile card is in)."""
        used = {int(x.w["panel"].value or 1) - 1 for x in self.prof_cards}
        free = next(p for p in range(len(used) + 1) if p not in used)
        self._new_profs([dict(c.collect(), panel=free)], at=c)

    def _per_run_prof(self, c):
        """Card c of several runs (or every run) becomes a card per run in its panel,
        each in the run's colour; of one run, a copy for each other run of the figure
        in its panel (a run with the same profile there already is skipped)."""
        s, runs = c.collect(), sorted(self._run_names().values())
        spec = dict(runs=self._runs_collect())  # (the runs' colours)
        if s["runs"] is None or len(s["runs"]) > 1:
            ks = s["runs"] or runs
            if len(ks) < 2:
                self._msg("The figure has one run: add others first (pick one in a "
                          "card's <b>Run</b> list).", True)
                return
            i = self.prof_cards.index(c)
            self.prof_cards.remove(c)
            self.prof_cards[i:i] = [self._prof_card(dict(
                s, run=k, runs=[k], ens="", color=figdraw.run_color(spec, k))) for k in ks]
            self._show_profiles()
            self._build_titles()
            self.request()
            return
        others = [k for k in runs if k != s["runs"][0]]
        if not others:
            self._msg("The figure has one run: add others first (pick one in a card's "
                      "<b>Run</b> list).", True)
            return
        key = json.dumps(s["recipe"], sort_keys=True, default=float)
        have = {(x["run"], x["panel"], x["time_s"], x["time_s1"],
                 json.dumps(x["recipe"], sort_keys=True, default=float))
                for x in (y.collect() for y in self.prof_cards)
                if x["runs"] is not None and len(x["runs"]) == 1}
        new = [dict(s, run=k, runs=[k], label="", color="") for k in others
               if (k, s["panel"], s["time_s"], s["time_s1"], key) not in have]
        if not new:
            self._msg("Each run has this profile in this panel already.", True)
            return
        self._new_profs(new, at=c)

    def _show_profiles(self):
        self._listed(self.prof_box, self.prof_cards, "No profiles: add the Series tool's "
                     "layer series, or a new one.")

    def _remove_prof(self, c):
        self.prof_cards.remove(c)
        self._cards_changed(self._show_profiles)

    def tab_profiles(self):
        """spec["profiles"] entries of the Series tool's layer series (this run) at the
        shown time, all in the first panel."""
        out = []
        for s in (getattr(self.v, "series", {}) or {}).values():
            if "profile" in s["ds"]:
                out.append(fg.profile_defaults(s["recipe"], self._own_index(),
                                               float(self.run.times[self.v.t]),
                                               len(out) + len(self.prof_cards)))
        return out

    def _add_tab_profiles(self):
        self._from_tool(self.prof_cards, self.tab_profiles(), self._prof_card,
                        self._show_profiles, "No layer series yet: make one with the "
                        "Series tool (Vertical: Layer) first, or add a profile here.")

    def _add_profile(self):
        e = fg.profile_defaults(self._new_recipe(), self._own_index(),
                                float(self.run.times[self.v.t]), len(self.prof_cards))
        self.prof_cards.append(self._prof_card(e))
        self._cards_changed(self._show_profiles)

    # ------------------------------------------------------------ joint distribution cards
    def _joint_card(self, e):
        return self._entry_card(JointCard, e, self._remove_joint)

    def _show_joints(self):
        self._listed(self.joint_box, self.joint_cards, "No joint distributions: add one.")

    def _remove_joint(self, c):
        self.joint_cards.remove(c)
        self._cards_changed(self._show_joints)

    def _new_joint_recipe(self):
        """A recipe for a new joint distribution: vertical vorticity against w (the
        map's distribution's field and place, when the Distribution tool has one) over
        the whole domain at 1 km."""
        tool = list((getattr(self.v, "dists", {}) or {}).values())
        r = dict(tool[-1]["recipe"]) if tool else self._new_dist_recipe()
        r["yfield"] = "zvort" if "zvort" in self.F and r["field"] != "zvort" else r["field"]
        return r

    def _add_joint(self):
        e = fg.joint_defaults(self._new_joint_recipe(), self._own_index(),
                              float(self.run.times[self.v.t]), len(self.joint_cards))
        self.joint_cards.append(self._joint_card(e))
        self._cards_changed(self._show_joints)

    # ------------------------------------------------------------ azimuthal mean cards
    def _azim_card(self, e):
        return self._entry_card(AzimCard, e, self._remove_azim)

    def _show_azims(self):
        self._listed(self.azim_box, self.azim_cards, "No azimuthal means: add one.")

    def _remove_azim(self, c):
        self.azim_cards.remove(c)
        self._cards_changed(self._show_azims)

    def _new_azim_recipe(self):
        """A recipe for a new azimuthal mean: w (the previous one's field and sector,
        when there is one) around the tracked storm, else around the middle of the
        map's view; the whole ring out to 20 km, 0-15 km."""
        if self.azim_cards:
            return self.azim_cards[-1].recipe()
        f = "winterp" if "winterp" in self.F else next(
            (k for k, d in self.F.defs.items() if d.ndim == 3), next(iter(self.F.defs)))
        track = bool(self.v.fixes) or any(r.get("track") for r in self._runs_collect())
        x0, x1, y0, y1 = (float(v) for v in self.v.view)
        return dict(field=f, center="track" if track else "point",
                    point=(0.5 * (x0 + x1), 0.5 * (y0 + y1)))

    def _add_azim(self):
        e = fg.azim_defaults(self._new_azim_recipe(), self._own_index(),
                             float(self.run.times[self.v.t]), len(self.azim_cards))
        self.azim_cards.append(self._azim_card(e))
        self._cards_changed(self._show_azims)

    # ------------------------------------------------------------ annotations
    def _ann_row(self, a):
        r = AnnotationRow(self, a)
        r.rm.on_click(lambda ev: self._remove_ann(r))
        return r

    def _show_anns(self):
        self.ann_box.objects = [r.panel for r in self.ann_rows]

    def _add_annotation(self):
        kind = self.ann_kind.value
        # in the middle of the first drawn panel, so it shows (storm-centred panels in
        # grid km may not contain (0, 0)); no axis ranges yet: as panel fractions
        lims = self._lims.get(min(self._lims)) if self._lims else None
        if lims is None or self.kind.value == "sounding":
            coords, (x, y), dx, dy = "axes", (0.5, 0.5), 0.15, 0.15
        else:
            (x0, x1), (y0, y1) = lims
            coords, x, y = "data", 0.5 * (x0 + x1), 0.5 * (y0 + y1)
            dx, dy = 0.15 * (x1 - x0), 0.15 * (y1 - y0)
        r = min(abs(dx), abs(dy)) if coords == "data" else 0.15
        a = dict(kind=kind, panel=-1, coords=coords, x=round(x, 2), y=round(y, 2),
                 x2=round(x + dx, 2), y2=round(y + dy, 2), r=round(r, 2),
                 text={"text": "A", "legend": "Entry"}.get(kind, ""),
                 color="#000000", size=10.0 if kind != "marker" else 8.0, lw=1.5,
                 ls="--" if kind in ("vline", "hline") else "-")
        self.ann_rows.append(self._ann_row(a))
        self._show_anns()
        self.request()

    def _remove_ann(self, r):
        self.ann_rows.remove(r)
        self._show_anns()
        self.request()

    # ------------------------------------------------------------ start from series / soundings
    def from_series(self):
        """Time-height panels of the Series tab's layer series (the active one first),
        or time series when the active one is at one height; every run of the figure.
        Without series: the maximum updraft near the storm (edit it in Layers)."""
        ss = getattr(self.v, "series", {}) or {}
        if ss:
            act = self.v.ser_pick.value if self.v.ser_pick.value in ss else next(iter(ss))
            keys = [act] + [k for k in ss if k != act]
            th = "profile" in ss[act]["ds"]
            keys = [k for k in keys if ("profile" in ss[k]["ds"]) == th][:4 if th else 6]
            ents = [fg.series_defaults(self.F, dict(ss[k]["recipe"]), n)
                    for n, k in enumerate(keys)]
        else:
            th, ents = True, [fg.series_defaults(self.F, self._new_recipe())]
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        nr = len(s["runs"])
        s.update(kind="th" if th else "line", series=ents, runs_as="cols", vary="time",
                 layers=[lay for lay in s["layers"] if lay["type"] != "vectors"])
        s["axes"] = dict(s["axes"], xlabel="time (min)", ylabel="height (km)" if th else "",
                         ticklabels="outer", equal=False)
        s["time_label"] = dict(s["time_label"], on=False)
        s["letters"] = dict(s["letters"], loc="upper left")
        if th:
            s.update(rows=len(ents), cols=nr, size=[5.0 * nr + 1.0, 3.0 * len(ents) + 0.5])
            s["colorbar"] = dict(s["colorbar"], mode="row", orientation="vertical", shrink=1.0)
            s["titles"] = [f"{s['runs'][c]['label']} – {e['label']}" for e in ents
                           for c in range(nr)]
            s["run_label"] = dict(s["run_label"], on=False)
        else:
            s.update(rows=1, cols=1, size=[7.0, 3.5])
            s["colorbar"] = dict(s["colorbar"], mode="none")
        self.set_spec(s)

    def from_soundings(self):
        """Skew-T panels: the Sounding tab's soundings in one panel (or the storm's
        sounding at the shown time when there are none)."""
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        own = s["runs"][s["run"]]
        track = bool(self.run_fixes(own, self.run))
        snd = self.tab_soundings() or [fg.sounding_defaults(
            s["run"], float(self.run.times[self.v.t]),
            dict(kind="trk" if track else "mean", x=0.0, y=0.0, avg=0.0))]
        s.update(kind="sounding", soundings=snd, rows=1, cols=1, size=[5.5, 5.5],
                 vary="time")
        s["axes"] = dict(s["axes"], xlabel="temperature (°C)", ylabel="pressure (hPa)",
                         ticklabels="all", equal=False)
        s["colorbar"] = dict(s["colorbar"], mode="none")
        # one sounding figure: no letters; a part of a figure: letters above, clear of
        # the time and the legend
        s["letters"] = dict(s["letters"], on=self._multi_part(), loc="above left")
        s["time_label"] = dict(s["time_label"], loc="lower left")
        self.set_spec(s)

    def from_dists(self):
        """One distribution panel of the Distribution tool's distributions (or w over
        the whole domain at 1 km at the shown time when there are none), drawn as the
        tool draws them."""
        s = self._keep_runs(fg.default_spec(self.run, self.F, self.v.t))
        ents = self.tab_dists() or [fg.dist_defaults(
            self._new_dist_recipe(), s["run"], float(self.run.times[self.v.t]))]
        look = getattr(self.v, "dist_look", None)
        s.update(kind="dist", dists=ents, rows=1, cols=1, size=[5.5, 3.9], vary="time")
        if look:
            s["dist"] = dict(s["dist"], **look())
        s["axes"] = dict(s["axes"], xlabel="", ylabel="", ticklabels="all", equal=False)
        s["colorbar"] = dict(s["colorbar"], mode="none")
        s["letters"] = dict(s["letters"], on=self._multi_part(), loc="above left")
        s["time_label"] = dict(s["time_label"], loc="upper left")
        s["run_label"] = dict(s["run_label"], on=False)
        self.set_spec(s)
