"""The data behind a figure, without the editor: FigureData turns a figure spec into
{panel: arrays} for figdraw.draw, opening the spec's runs and reading their storm
tracks, and keeps what it read (plan-view and section panels, series, soundings,
distributions, profiles, joint distributions, azimuthal means, 3D scenes), so drawing
the same figure again, restyled, reads nothing.

The figure editor keeps one (FigureEditor.data) with hooks into the viewer (its run,
its track, the status line, a series pool that fills series in the background);
without them it works on its own, e.g. for rendering a saved spec from a script or a
batch job:

    fd = FigureData()
    fig = figdraw.draw(spec, fd.panel_data(spec))

No Panel / Bokeh here."""

import json
import os
import time as _time
import traceback
from collections import OrderedDict

from . import draw as figdraw, spec as fg
from ..core import series as ser, track as trk
from ..core.fields import Fields
from ..core.run import CM1Run, FileBusy, MissingAtTime


def panel_name(spec, i):
    """Panel i's letter (a figure of parts: data key k * 1000 + j, letters running on)."""
    if spec.get("kind") != "combo":
        return figdraw.panel_letter(i, "{a}")
    k, j = divmod(int(i), 1000)
    return figdraw.panel_letter(sum(fg.npanels(p) for p in spec["parts"][:k]) + j, "{a}")


def track_sig(fx):
    """A storm track's signature, for cache keys."""
    return json.dumps(sorted((t, round(f["x"], 4), round(f["y"], 4)) for t, f in fx.items()))


class FigureData:
    """{panel: arrays} of figure specs, with caches.

    run, F: a run already open (spec runs at its path use it); reg: a registry
    (viewer's) to open the others through, sharing its cache; else they are opened
    here (cache_gb, workers as CM1Run's).  viewer_fixes(): the fixes a run entry with
    track "viewer" takes (of `run` only).  note(text): progress text while reading.
    series_pool: an executor that computes missing series in the background (the
    figure is drawn with what is there; on_series() is called as they come in, gen()
    tells a newer figure from the one that started them); None: computed here, before
    panel_data returns."""

    def __init__(self, run=None, F=None, reg=None, viewer_fixes=None, note=None,
                 series_pool=None, on_series=None, gen=None, cache_gb=4.0, workers=None):
        self.run, self.F, self.reg = run, F, reg
        self.viewer_fixes = viewer_fixes or dict
        self.note = note or (lambda text: None)
        self.series_pool, self.on_series = series_pool, on_series or (lambda: None)
        self.gen = gen or (lambda: 0)
        self.cache_gb, self.workers = cache_gb, workers
        self._vc = getattr(run, "_vc", None)  # (runs opened here share one 3D cache)
        self.cache = OrderedDict()  # data key -> panel arrays
        self.opened = {}  # run path -> (CM1Run, Fields) opened here
        self.tracks = {}  # track file -> (mtime, run path, fixes)
        self.track_err = {}  # track file -> error text
        # series of time-height / time-series figures: (run path, recipe, track) ->
        # dataset (filled in place while it is computed); state "running" / "done"
        self.ser_mem, self.ser_state, self.ser_prog = {}, {}, {}
        # the series keys the shown figure needs (its last whole preview's, and any
        # started since): a series job of one no longer needed stops
        self.ser_live, self.ser_touch = set(), set()
        self.snd_cache = OrderedDict()  # sounding (run, time, where, track) -> analysis
        self.dist_cache = OrderedDict()  # distribution (run, time, recipe, track) -> summary
        self.scene_cache = OrderedDict()  # 3D scene (run, time, scene, track) -> arrays
        self.st_cache = {}  # (build_scene's: the last scene's streamlines)

    # ------------------------------------------------------------ runs
    def open_run(self, path):
        """(CM1Run, Fields) of the run in `path` (the given run, or one opened through
        the registry so its cache is shared, or here)."""
        path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
        if self.run is not None and path == self.run.path:
            return self.run, self.F
        if self.reg is not None:
            return self.reg.get(path)
        if path not in self.opened:
            if self._vc is None:
                from ..core.run import VolumeCache
                self._vc = VolumeCache(self.cache_gb)
            r = CM1Run(path, cache_gb=self.cache_gb, workers=self.workers, cache=self._vc)
            self.opened[path] = (r, Fields(r))
        return self.opened[path]

    def run_fixes(self, entry, run):
        """Track fixes {t: fix} of a spec["runs"] entry ({} without a track)."""
        tr = entry.get("track") or ""
        if tr == "viewer":
            return dict(self.viewer_fixes()) if run is self.run else {}
        if not tr:
            return {}
        path = os.path.abspath(os.path.expanduser(os.path.expandvars(tr)))
        try:
            mt = os.path.getmtime(path)
            hit = self.tracks.get(path)
            if hit is None or hit[0] != mt or hit[1] != run.path:
                self.tracks[path] = (mt, run.path, trk.load(run, path))
            self.track_err.pop(path, None)
            return self.tracks[path][2]
        except Exception as e:  # noqa: BLE001
            self.track_err[path] = str(e)
            return {}

    # ------------------------------------------------------------ panels
    def panel_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of the spec, from the cache where possible.  progress(i, n):
        reading panel (sounding, ...) i of n; cancelled(): stop (returns None)."""
        if spec["kind"] == "combo":
            return self._combo_data(spec, progress, cancelled)
        if spec["kind"] in ("th", "line"):
            return self._series_data(spec, cancelled)
        if spec["kind"] == "sounding":
            return self._sounding_data(spec, progress, cancelled)
        if spec["kind"] == "dist":
            return self._dist_data(spec, progress, cancelled)
        if spec["kind"] == "profile":
            return self._profile_data(spec, progress, cancelled)
        if spec["kind"] == "joint":
            return self._joint_data(spec, progress, cancelled)
        if spec["kind"] == "azim":
            return self._azim_data(spec, progress, cancelled)
        if spec["kind"] == "scene":
            return self._scene_data(spec, cancelled)
        ctx = {}  # run index -> (run, Fields, fixes, centres, track signature)

        def context(k):
            if k not in ctx:
                e = spec["runs"][k]
                run, F = self.open_run(e["path"])
                fx = self.run_fixes(e, run)
                ctx[k] = (run, F, fx, ser.track_centers(fx, len(run.times)), track_sig(fx))
            return ctx[k]

        def read(s, i, k, ts, n, at):
            """Arrays of panel i of spec s, read from run k at time ts (for panel `at`)."""
            entry = spec["runs"][k]
            try:
                run, F, fx, centers, sig = context(k)
            except Exception as e:  # noqa: BLE001
                return dict(time_s=ts, missing=f"could not open {entry['path']}: {e}")
            t = fg.tindex(run, ts)
            c = centers.get(t) if t is not None else None
            key = fg.data_key(s, i, c, run.path)
            lays = figdraw.spec_layers(s, i)
            if any(lay["type"] in ("track", "sector") or (lay.get("reduce") or {}).get(
                    "op") == "composite" for lay in lays) or \
                    (s["kind"] == "xsec" and fg.uses_motion(fg.panel_section(s, i)[1])) or \
                    (any(lay["type"] == "line" for lay in lays)
                     and any(fg.uses_motion(x) for x in fg.sections(s))):
                key += sig  # (a composite follows the whole track; a sector, section its motion)
            d = self.cache.get(key)
            if d is None:
                if progress:
                    progress(at, n)
                storm = fg.storm_motion(run, fx, t) if t is not None else None
                rp = None
                if progress and any(lay.get("reduce") for lay in figdraw.spec_layers(s, i)):
                    def rp(done, total):  # (a time window: one output at a time)
                        self.note(f"Time window of panel {panel_name(spec, at)}: output "
                                  f"{done + 1}/{total}…")
                d = fg.extract(run, F, s, i, c, fx, storm, rp)
                self.cache[key] = d
                while len(self.cache) > 60:
                    self.cache.popitem(last=False)
            else:
                self.cache.move_to_end(key)
            return d

        multi = len(spec["runs"]) > 1
        data = {}
        n = fg.npanels(spec)
        for i in range(n):
            if cancelled and cancelled():
                return None
            ref = fg.panel_ref(spec, i)
            if ref is None:
                continue  # an empty cell of a run x time grid
            k, ts = ref
            groups = fg.layer_groups(spec, i)  # (layers of another run or time)
            lays = figdraw.spec_layers(spec, i)
            if not groups:
                d = read(spec, i, k, ts, n, i)
            else:
                others = {j for js in groups.values() for j in js}
                d = read(fg.group_spec(spec, i, ref, set(range(len(lays))) - others), 0,
                         k, ts, n, i)
                for g, js in groups.items():
                    dd = read(fg.group_spec(spec, i, g, set(js)), 0, g[0], g[1], n, i)
                    d = fg.merge_group(d, dd, js, lays)
            for j, lay in enumerate(lays):  # ensembles: a statistic over several runs
                if lay["type"] == "fill" and lay.get("ens") and lay.get("on", True):
                    dds = [read(fg.group_spec(spec, i, g, {j}), 0, g[0], g[1], n, i)
                           for g in fg.ens_refs(spec, i, lay)]
                    d = fg.ensemble(d, dds, j, lay["ens"])
            for j, lay in enumerate(lays):  # differences: minus another run or time
                if lay["type"] == "fill" and lay.get("minus") and lay.get("on", True) \
                        and not lay.get("ens"):
                    g = fg.minus_ref(spec, i, lay)
                    if g[0] >= len(spec["runs"]):
                        d = dict(d, missing="difference: that run is no longer in the figure")
                        continue
                    dd = read(fg.group_spec(spec, i, g, {j}), 0, g[0], g[1], n, i)
                    d = fg.subtract(d, dd, j, lay["minus"].get("grid", "ask"))
            entry = spec["runs"][k]
            data[i] = dict(d, run=k, **({"run_label": entry.get("label", "")} if multi
                                         else {}))
        return data

    def _combo_data(self, spec, progress=None, cancelled=None):
        data = {}
        for k, part in enumerate(spec["parts"]):
            d = self.panel_data(part, progress, cancelled)
            if d is None:
                return None
            for i, v in d.items():
                data[k * 1000 + int(i)] = v
        return data

    # ------------------------------------------------------------ series
    def series_get(self, spec, k, e, cancelled=None):
        """(run, dataset) of series e of spec for run k, or why not (a string).  The
        missing times are computed: in the background with a series pool (the figure
        updates as they come in), else here."""
        runs, ent = spec["runs"], spec["series"][e]
        try:
            run, F = self.open_run(runs[k]["path"])
        except Exception as ex:  # noqa: BLE001
            return f"could not open {runs[k]['path']}: {ex}"
        r = ent["recipe"]
        if r["field"] not in F:
            return f"this run has no {r['field']}"
        fx = self.run_fixes(runs[k], run)
        track = r["region"] == "track"
        if track and not fx:
            return "no storm track for this run (Runs tab)"
        centers = ser.track_centers(fx, len(run.times)) if track else None
        key = (run.path, json.dumps(r, sort_keys=True), track_sig(fx) if track else "")
        self.ser_touch.add(key)
        ds = self.ser_mem.get(key)
        if ds is None:
            d = F[r["field"]]
            ds = ser.cached(run, r, d.label, d.units, centers)
            self.ser_mem[key] = ds
        if key not in self.ser_state and int(ds["computed"].sum()) < len(run.times):
            storm = ({t: fg.storm_motion(run, fx, t) for t in range(len(run.times))}
                     if F[r["field"]].storm else None)
            what = f"{runs[k].get('label') or ''}: {ent.get('label', '')}"
            self.ser_state[key] = "running"
            self.ser_live = self.ser_live | {key}
            if self.series_pool is not None:
                self.series_pool.submit(self.ser_compute, key, run, F, r, ds, centers, storm,
                                        what)
            else:
                self.ser_compute(key, run, F, r, ds, centers, storm, what, cancelled)
        elif key not in self.ser_state:
            self.ser_state[key] = "done"
        return run, ds

    def ser_compute(self, key, run, F, recipe, ds, centers, storm, what, cancelled=None):
        """Compute series `key`; in the background, it stops (its times so far kept, to
        go on from when it is needed again) once the shown figure no longer needs it,
        e.g. its region changed from around the storm to the whole domain."""
        g0, last = self.gen(), [_time.time()]

        def stale():
            return self.gen() != g0 or key not in self.ser_live or \
                bool(cancelled and cancelled())

        if stale():  # (queued behind another, and changed meanwhile: not started)
            self.ser_state.pop(key, None)
            self.ser_prog.pop(key, None)
            return

        def on_result(ds_, done, total):
            self.ser_prog[key] = f"{what[:60]} {done}/{total}"
            if self.series_pool is None:
                self.note(f"Series {what[:60]}: output {done}/{total}…")
            elif _time.time() - last[0] > 10 and done < total:  # partial preview
                last[0] = _time.time()
                self.on_series()

        try:
            ser.compute(run, F, recipe, ds, centers, storm, on_result=on_result,
                        cancelled=stale)
            if stale():  # (computed again from where it stopped when it is wanted)
                self.ser_state.pop(key, None)
            else:
                self.ser_state[key] = "done"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.ser_state[key] = f"error: {e}"
        self.ser_prog.pop(key, None)
        if self.series_pool is not None:
            self.on_series()

    def series_pending(self):
        return [v for k, v in self.ser_prog.items() if self.ser_state.get(k) == "running"] \
            or [""] * sum(v == "running" for v in self.ser_state.values())

    def _series_data(self, spec, cancelled=None):
        got = {}

        def get(k, e):
            if (k, e) not in got:
                got[(k, e)] = self.series_get(spec, k, e, cancelled)
            return None if isinstance(got[(k, e)], str) else got[(k, e)]

        data, multi = {}, len(spec["runs"]) > 1
        busy = bool(self.series_pending())
        for i in range(fg.npanels(spec)):
            if spec["kind"] == "th":
                ref = figdraw.series_ref(spec, i)
                if ref is None:
                    continue
                r = get(*ref)
                d = (dict(missing=got[ref]) if r is None else
                     fg.th_panel(r[0], r[1], spec["series"][ref[1]], spec))
                d["run"] = ref[0]
                if multi:
                    d["run_label"] = fg.run_folder(spec, ref[0])
            else:
                d = fg.line_panel(spec, i, get)
            if busy and d.get("missing") == "not computed yet":
                d["missing"] = "computing…"
            data[i] = d
        if cancelled and cancelled():
            return None
        return fg.share_time_range(spec, data)

    # ------------------------------------------------------------ soundings, distributions
    def _entries(self, spec, key, entry, panel, progress=None, cancelled=None):
        """{panel: arrays} of a figure of entries spec[key] (soundings, distributions,
        joint distributions, azimuthal means): entry(e, ent, run spec, note) gives entry
        e's result (an error is its message), each at most once; note() reports it being
        computed (progress); panel(i, get) draws panel i with get(e) -> that result."""
        runs, ents = spec["runs"], spec.get(key, [])
        res = {}

        def get(e):
            if e in res:
                return res[e]
            ent = ents[e]
            k = int(ent.get("run", 0))
            try:
                note = (lambda: progress(e, len(ents))) if progress else (lambda: None)
                res[e] = entry(e, ent, runs[k], note) if k < len(runs) else "no such run"
            except (MissingAtTime, FileBusy) as ex:
                res[e] = str(ex)
            except Exception as ex:  # noqa: BLE001
                traceback.print_exc()
                res[e] = f"{type(ex).__name__}: {ex}"
            return res[e]

        data = {}
        for i in range(fg.npanels(spec)):
            if cancelled and cancelled():
                return None
            data[i] = panel(i, get)
        return data

    @staticmethod
    def _kept(cache, key, most, compute, note):
        """cache[key], computed (note(), then compute()) when not there and kept, the
        `most` used last; None (not kept) when compute() gives None (stopped for a newer
        preview)."""
        r = cache.get(key)
        if r is not None:
            cache.move_to_end(key)
            return r
        note()
        r = compute()
        if r is not None:
            cache[key] = r
            while len(cache) > most:
                cache.popitem(last=False)
        return r

    @staticmethod
    def _times_vary(ents, ent, when):
        """Whether the entries in ent's panel (your own data aside: no time) are at
        more than one time (when(x): an entry's time)."""
        mine = [x for x in ents if int(x.get("panel", 0)) == int(ent.get("panel", 0))
                and not fg.is_table(x)]
        return len({when(x) for x in mine}) > 1

    # ------------------------------------------------------------ soundings, distributions
    def _sounding_data(self, spec, progress=None, cancelled=None):
        runs, ents = spec["runs"], spec.get("soundings", [])
        labels, multi = {}, len(runs) > 1
        storm = fg.storm_choice(spec.get("skewt", {}))  # (of the SRH and the ring)

        def entry(e, ent, rs, note):
            run, _ = self.open_run(rs["path"])
            fx = self.run_fixes(rs, run)
            sig = track_sig(fx) if ent["where"].get("kind") == "trk" else ""
            key = json.dumps([run.path, float(ent["time_s"]), ent["where"], sig, storm],
                             sort_keys=True)
            r = self._kept(self.snd_cache, key, 40, note=note, compute=lambda:
                           fg.sounding_column(run, ent, fx, storm=storm))
            labels[e] = fg.sounding_label(ent, rs.get("label", ""), run, multi)
            return r

        return self._entries(spec, "soundings", entry, lambda i, get: fg.sounding_panel(
            spec, i, get, lambda e: labels.get(e, "")), progress, cancelled)

    def _dist_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of a distribution figure; the summaries are kept
        (dist_cache), so restyling reads nothing."""
        runs, ents = spec["runs"], spec.get("dists", [])
        labels, vlabs, multi = {}, {}, len(runs) > 1

        def entry(e, ent, rs, note):
            run, F = self.open_run(rs["path"])
            fx = self.run_fixes(rs, run)
            r = ent["recipe"]
            track = r["region"] == "track" or (r["field"] in F and F[r["field"]].storm)
            key = json.dumps([run.path, float(ent["time_s"]), r,
                              track_sig(fx) if track else ""], sort_keys=True)
            res = self._kept(self.dist_cache, key, 60, note=note, compute=lambda:
                           fg.dist_compute(run, F, ent, fx))
            times = self._times_vary(ents, ent, lambda x: round(float(x["time_s"]), 1))
            labels[e] = fg.dist_label(ent, rs.get("label", ""), F, multi, times)
            vlabs[e] = fg.profile_value_label(F, ent)
            return res

        return self._entries(spec, "dists", entry, lambda i, get: fg.dist_panel(
            spec, i, get, lambda e: labels.get(e, ""), lambda e: vlabs.get(e, "")),
            progress, cancelled)

    def _joint_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of a joint distribution figure; the summaries are kept
        (dist_cache, with the distributions'), so restyling reads nothing."""
        runs, ents = spec["runs"], spec.get("joints", [])
        labels, axlabs, multi = {}, {}, len(runs) > 1

        def entry(e, ent, rs, note):
            run, F = self.open_run(rs["path"])
            fx = self.run_fixes(rs, run)
            r = ent["recipe"]
            track = r["region"] == "track" or any(
                f in F and F[f].storm for f in (r["field"], r["yfield"]))
            key = json.dumps(["joint", run.path, float(ent["time_s"]), ent.get("time_s1"),
                              r, track_sig(fx) if track else ""], sort_keys=True)
            res = self._kept(self.dist_cache, key, 60, note=note, compute=lambda:
                           fg.joint_compute(run, F, ent, fx, cancelled))
            if res is None:  # (stopped for a newer preview: not kept)
                return "cancelled"
            times = self._times_vary(ents, ent, lambda x: (round(float(x["time_s"]), 1),
                                                           x.get("time_s1")))
            labels[e] = fg.joint_label(ent, rs.get("label", ""), F, multi, times)
            axlabs[e] = (fg.dist_value_label(F, r["field"]),
                         fg.dist_value_label(F, r["yfield"]))
            return res

        return self._entries(spec, "joints", entry, lambda i, get: fg.joint_panel(
            spec, i, get, lambda e: labels.get(e, ""), lambda e: axlabs.get(e, ("", ""))),
            progress, cancelled)

    def _scene_data(self, spec, cancelled=None):
        """{0: arrays} of a 3D scene figure; kept (scene_cache) by what they depend on
        (scene_key), so camera and look changes only render again, and an isosurface
        edit keeps the traced streamlines (st_cache)."""
        runs, k = spec["runs"], int(spec.get("run", 0))
        ts = float(spec["time_s"])
        if k >= len(runs):
            return {0: dict(time_s=ts, missing="no such run")}
        try:
            run, F = self.open_run(runs[k]["path"])
            fx = self.run_fixes(runs[k], run)
            key = fg.scene_key(spec, run.path, track_sig(fx))
            d = self.scene_cache.get(key)
            if d is None:
                def prog(done, total, name):
                    if total:
                        self.note(f"Loading 3D fields ({done}/{total}) {name}…")

                d = fg.scene_extract(run, F, spec, fx, prog, cancelled, self.st_cache)
                if d is None:  # (stopped for a newer preview)
                    return None
                self.scene_cache[key] = d
                while len(self.scene_cache) > 6:  # (meshes are large)
                    self.scene_cache.popitem(last=False)
            else:
                self.scene_cache.move_to_end(key)
        except (MissingAtTime, FileBusy) as ex:
            d = dict(time_s=ts, missing=str(ex))
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            d = dict(time_s=ts, missing=f"{type(ex).__name__}: {ex}")
        out = dict(d, run=k)
        if len(runs) > 1:
            out["run_label"] = runs[k].get("label", "")
        return {0: out}

    def _azim_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of an azimuthal mean figure; the results are kept
        (dist_cache, with the distributions'), so restyling reads nothing."""
        runs, ents = spec["runs"], spec.get("azims", [])
        labels, cbl, look, multi = {}, {}, {}, len(runs) > 1

        def entry(e, ent, rs, note):
            run, F = self.open_run(rs["path"])
            fx = self.run_fixes(rs, run)
            r = ent["recipe"]
            # (the track: centres, and azimuth 0 / storm-relative fields: motion)
            key = json.dumps(["azim", run.path, float(ent["time_s"]), ent.get("time_s1"),
                              r, track_sig(fx)], sort_keys=True)
            res = self._kept(self.dist_cache, key, 60, note=note, compute=lambda:
                           fg.azim_compute(run, F, ent, fx, cancelled))
            if res is None:  # (stopped for a newer preview: not kept)
                return "cancelled"
            times = self._times_vary(ents, ent, lambda x: (round(float(x["time_s"]), 1),
                                                           x.get("time_s1")))
            labels[e] = fg.azim_label(ent, rs.get("label", ""), F, multi, times)
            cbl[e] = fg.dist_value_label(F, r["field"])
            d = F[r["field"]] if r["field"] in F else None
            look[e] = (d.cmap, d.diverging) if d is not None else ("viridis", False)
            return res

        return self._entries(spec, "azims", entry, lambda i, get: fg.azim_panel(
            spec, i, get, lambda e: labels.get(e, ""), lambda e: cbl.get(e, ""),
            lambda e: look.get(e, ("viridis", False))), progress, cancelled)

    # ------------------------------------------------------------ profiles
    def _profile_data(self, spec, progress=None, cancelled=None):
        """{panel: arrays} of a profile figure.  Each profile is a layer series
        computed (ser.compute) only at the outputs it needs and cached with the series
        (on disk and in ser_mem), so restyling reads nothing."""
        runs, ents = spec["runs"], spec.get("profiles", [])
        res, labels, vlabs = {}, {}, {}
        multi = len(runs) > 1

        def get(e, k):
            if (e, k) in res:
                return res[e, k]
            ent = ents[e]
            if k >= len(runs):
                res[e, k] = "no such run"
                return res[e, k]
            try:
                n = sum(len(fg.profile_runs(x, len(runs))) for x in ents)
                res[e, k] = self.profile_get(runs[k], ent, len(res), n, progress, cancelled)
                run, F = self.open_run(runs[k]["path"])
                times = self._times_vary(ents, ent, lambda x: (round(float(x["time_s"]), 1),
                                                               x.get("time_s1")))
                labels[e, k] = fg.profile_label(ent, runs[k].get("label", ""), F, multi, times)
                labels.setdefault((e, -1), fg.profile_label(ent, "", F, False, times))
                vlabs[e] = fg.profile_value_label(F, ent)
            except Exception as ex:  # noqa: BLE001
                traceback.print_exc()
                res[e, k] = f"{type(ex).__name__}: {ex}"
            return res[e, k]

        data = {}
        for i in range(fg.npanels(spec)):
            if cancelled and cancelled():
                return None
            data[i] = fg.profile_panel(spec, i, get, lambda e, k: labels.get((e, k), ""),
                                       lambda e: vlabs.get(e, ""))
        return data

    def profile_get(self, rentry, ent, e, n, progress=None, cancelled=None, compute=True):
        """(z, values) of profile entry ent of run entry rentry, or why not (a
        string): its outputs not computed yet are computed here (compute False: not,
        say so)."""
        run, F = self.open_run(rentry["path"])
        r = ent["recipe"]
        if r["field"] not in F:
            return f"this run has no {r['field']}"
        if F[r["field"]].ndim != 3:
            return "profiles need a 3D field"
        ts = fg.profile_times(run, ent)
        if not ts:
            return f"no output at {float(ent['time_s']) / 60:g} min in this run"
        fx = self.run_fixes(rentry, run)
        track = r["region"] == "track"
        if track and not fx:
            return "no storm track for this run (Runs tab)"
        centers = ser.track_centers(fx, len(run.times)) if track else None
        key = (run.path, json.dumps(r, sort_keys=True),
               track_sig(fx) if track else "")  # (as series_get's)
        ds = self.ser_mem.get(key)
        if ds is None:
            d = F[r["field"]]
            ds = ser.cached(run, r, d.label, d.units, centers)
            self.ser_mem[key] = ds
        todo = [t for t in ts if not ds["computed"].values[t]]
        skipped = {}
        if todo and not compute:
            return "not computed yet (Refresh once the preview has drawn it)"
        if todo:
            if progress:
                progress(e, n)
            storm = ({t: fg.storm_motion(run, fx, t) for t in todo}
                     if F[r["field"]].storm else None)
            _, skipped = ser.compute(run, F, r, ds, centers, storm, cancelled=cancelled,
                                     times=todo)
        z, v, used = fg.profile_values(ds, ts)
        if not used:
            why = next(iter(skipped.values()), "not computed")
            return f"no profile: {why}"
        return z, fg.profile_op(z, v, ent.get("op", ""))
