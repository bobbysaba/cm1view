"""Figure editor: new figures from the map, the cross-section, the series, the soundings and the
distributions, and the entries a new panel starts with.  (The data of a figure is FigureData's,
figures/render.py.)

A mixin of the FigureEditor (figures/editor.py)."""

from . import spec as fg
from ..core import parcels as P, render, series as ser, vectors
from .cards import TERRAIN_LEVEL_MODES, _dark, parcel_source
from .kinds import KINDS


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
        doc = self.shell.doc if self.shell is not None else None
        if doc is not None:
            runs = [{k: v for k, v in r.items() if k != "id"} for r in doc["runs"]]
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

    def _parcel_layers(self):
        """A parcels layer per parcel set of the viewer, drawn as it draws them (empty
        without parcel output or sets)."""
        v = self.v
        if v.pf is None:
            return []
        look = dict(cvar=v.par_color.value or "", cmap=v.par_cmap.value,
                    units=v.pf.units(v.par_color.value) if v.par_color.value else "",
                    tails=v.par_window.value, minutes=float(v.par_minutes.value or 0.0),
                    heads=bool(v.par_heads.value), interp=bool(v.par_interp.value),
                    lw=round(0.8 * float(v.par_width.value or 1.0), 3),
                    alpha=float(v.par_alpha.value), within=float(v.par_xs_within.value or 0.0),
                    xs_tails=v.par_xs_tails.value, moving=v.par_frame.value,
                    move_u=float(v.par_fu.value or 0.0), move_v=float(v.par_fv.value or 0.0))
        return [dict(fg.layer_defaults("parcels", self.F), **look, **parcel_source(name, e))
                for name, e in v.psets.items()]

    def from_map(self):
        """A one-panel figure of what the map shows (field, levels, contours, vectors,
        view), at the shown time."""
        v, F, t = self.v, self.F, self.v.t
        sp = v._map_spec()

        def fill_layer(f):
            fill = fg.layer_defaults("fill", F, f["var"], f["level"])
            modes = TERRAIN_LEVEL_MODES.values()
            fill.update(mode=f["mode"] if f["mode"] in modes else "height",
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
        layers += self._parcel_layers()
        s = self._keep_runs(fg.default_spec(self.run, F, t))
        self._times(s, [t], t)
        self._minus(s, layers[0], sp["fill"].get("minus"), v._last_range)
        s.update(rows=1, cols=1, size=[5.0, 4.5], layers=layers, vary="time", kind="plan")
        s["domain"] = dict(s["domain"], mode="box", box=[float(x) for x in v.view])
        s["colorbar"] = dict(s["colorbar"], mode="each", orientation="vertical", shrink=0.9)
        s["axes"] = dict(s["axes"], ticklabels="all")
        self.shell.open_new(s)

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
        layers += self._parcel_layers()
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
        self.shell.open_new(s)

    # ------------------------------------------------------------ entries
    def _new_recipe(self):
        """A recipe for a new series: max w in 0–10 km near the storm (whole domain
        without a track), as for updraft time-height plots."""
        f = "winterp" if "winterp" in self.F else next(iter(self.F.defs))
        track = bool(self.v.fixes) or any(r.get("track") for r in self.shell.doc["runs"])
        return ser.normalize(dict(field=f, vmode="layer", z0=0.0, z1=10.0,
                                  region="track" if track else "domain", radius=5.0,
                                  offset=(0.0, 0.0), reduce="max"))

    def _parcel_series_source(self, have=None):
        """The set a new parcel series draws: the next viewer set not drawn yet (have: the sets'
        names drawn; else the first; no set: the first saved one), or None (and a message)."""
        v = self.v
        have = have or set()
        src = next((parcel_source(n, e) for n, e in v.psets.items() if n not in have),
                   None) or next((parcel_source(n, e) for n, e in v.psets.items()), None)
        if src is None:
            saved = P.list_sets(v.run.path)
            if not saved:
                self._msg("No parcel set yet: choose some in the viewer's <b>Parcels</b> "
                          "tab first.", True)
                return None
            ps = P.ParcelSet.load(saved[0])
            src = dict(name=ps.name, rule=ps.rule or None,
                       ids=None if ps.rule else [int(i) for i in ps.ids])
        return src

    def _own_index(self):
        paths = [r["path"] for r in self.shell.doc["runs"]]
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
                                            n))
        return out

    def tab_dists(self):
        """spec["dists"] entries of the Distribution tool's distributions (this run),
        all in the first panel."""
        out = []
        for n, s in enumerate((getattr(self.v, "dists", {}) or {}).values()):
            out.append(fg.dist_defaults(s["recipe"], self._own_index(),
                                        float(self.run.times[s["t"]]),
                                        n))
        return out

    def _new_dist_recipe(self):
        """A recipe for a new distribution: w over the whole domain at 1 km."""
        f = "winterp" if "winterp" in self.F else next(iter(self.F.defs))
        return dict(field=f, vmode="height", z=1.0, region="domain")

    def tab_profiles(self):
        """spec["profiles"] entries of the Series tool's layer series (this run) at the
        shown time, all in the first panel."""
        out = []
        for s in (getattr(self.v, "series", {}) or {}).values():
            if "profile" in s["ds"]:
                out.append(fg.profile_defaults(s["recipe"], self._own_index(),
                                               float(self.run.times[self.v.t]),
                                               len(out)))
        return out

    def _new_joint_recipe(self):
        """A recipe for a new joint distribution: vertical vorticity against w (the
        map's distribution's field and place, when the Distribution tool has one) over
        the whole domain at 1 km."""
        tool = list((getattr(self.v, "dists", {}) or {}).values())
        r = dict(tool[-1]["recipe"]) if tool else self._new_dist_recipe()
        r["yfield"] = "zvort" if "zvort" in self.F and r["field"] != "zvort" else r["field"]
        return r

    def _new_azim_recipe(self):
        """A recipe for a new azimuthal mean: w (the previous one's field and sector,
        when there is one) around the tracked storm, else around the middle of the
        map's view; the whole ring out to 20 km, 0-15 km."""
        f = "winterp" if "winterp" in self.F else next(
            (k for k, d in self.F.defs.items() if d.ndim == 3), next(iter(self.F.defs)))
        track = bool(self.v.fixes) or any(r.get("track") for r in self.shell.doc["runs"])
        x0, x1, y0, y1 = (float(v) for v in self.v.view)
        return dict(field=f, center="track" if track else "point",
                    point=(0.5 * (x0 + x1), 0.5 * (y0 + y1)))

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
        self.shell.open_new(s)

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
        # (one panel: no letter)
        k = KINDS["sounding"]
        s["letters"] = dict(s["letters"], on=False, loc=k.letter_at)
        s["time_label"] = dict(s["time_label"], loc=k.time_at)
        self.shell.open_new(s)

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
        s["letters"] = dict(s["letters"], on=False, loc="above left")
        s["time_label"] = dict(s["time_label"], loc="upper left")
        s["run_label"] = dict(s["run_label"], on=False)
        self.shell.open_new(s)
