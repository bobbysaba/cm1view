"""cm1view bench: how long the viewer's updates take on this machine, without a browser.

    cm1view bench RUN [options]     time a fixed list of actions on RUN
    cm1view bench --demo            the same on the synthetic demo run (checks it works)
    cm1view bench --report FILE     summary of a viewer timing log (cm1view RUN --timing)

The viewer is built on RUN just as a browser page gets it, then a fixed list of actions
is played: step through times, go back to a time already read, change the level, the
fill style and the field, show a column maximum and the column fields (column-max w, a
CAPE map), turn contours and vectors on and off, zoom, drop soundings, draw a
cross-section and a 3D view.  Each is split into reading the model output, computing
and updating the page's models, with the size of what would be sent to the browser.
The network and the browser are not part of this: for those, run the viewer with
--timing.

Picking the Sounding and the Section tool is timed too (it reads their fields at the
shown time in the background), with the first click after it.  A sounding and a
cross-section are then read in parts, as they are when their fields do
not fit the 3D cache (a very large grid, or a small --cache-gb), and the work over
several outputs is timed: tracking, a swath and trajectories traced through the winds
(from whole volumes and read in parts) over --window outputs.

Run it where you run the viewer (a compute node with the run's data), not on a login
node: it reads several full 3D fields."""

import argparse
import json
import os
import resource
import shutil
import sys
import tempfile
import threading
import time
from contextlib import contextmanager

import param

from . import config


def parser():
    ap = argparse.ArgumentParser(prog="cm1view bench", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?", default=None, help="directory containing model output")
    ap.add_argument("--report", metavar="FILE",
                    help="print the summary of a viewer timing log instead")
    ap.add_argument("--demo", nargs="?", const="cm1", choices=("cm1", "wofs"),
                    metavar="MODEL", help="use a synthetic demo run, CM1 (the default) or "
                                          "wofs (written once to the cache folder)")
    from .core.models import AUTO, MODELS
    ap.add_argument("--model", default=AUTO, choices=[AUTO, *MODELS])
    ap.add_argument("--config", default=None, help="settings file")
    ap.add_argument("--cache-gb", type=float, default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--maxpix", type=int, default=None)
    ap.add_argument("--field", default=None,
                    help="map fill to start from (default: the viewer's)")
    ap.add_argument("--field2", default=None,
                    help="field to switch to (default: one of winterp, thpert, dbz, ...)")
    ap.add_argument("--time", type=int, default=None,
                    help="first output index (default: the middle of the run)")
    ap.add_argument("--steps", type=int, default=4,
                    help="time steps to take, each reading a new time (default 4)")
    ap.add_argument("--window", type=int, default=8,
                    help="outputs to track over and to reduce in a swath (default 8; "
                         "0: skip both)")
    ap.add_argument("--no-3d", action="store_true", help="skip the 3D view")
    ap.add_argument("--out", default=None,
                    help="results file (default: bench-DATE.json in the cache folder)")
    return ap


def main(argv=None):
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    from .viewer import timing
    if args.report:
        timing.summarize(args.report)
        return 0
    if args.config:
        config.load(args.config)
    for name, flag in (("cache_gb", "--cache-gb"), ("workers", "--workers"),
                       ("maxpix", "--maxpix")):
        if getattr(args, name) is not None:
            config.override(name, getattr(args, name), flag)
    if args.demo:
        from . import demo, demo_wofs
        root = os.path.join(config.expand(config.get("cache_dir")), "demo")
        args.run = demo_wofs.make(root) if args.demo == "wofs" else demo.make(root)
    if not args.run:
        parser().error("give a run folder (or --demo, or --report FILE)")
    out = args.out or config.cache_dir("timing", time.strftime("bench-%Y%m%d-%H%M%S.json"))
    res = Bench(config.expand(args.run), args).play()
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"\ncm1view bench: results in {out}")
    from .core import pool
    pool.close()
    return 0


def _values(w):
    """A choice widget's values."""
    opts = w.options
    return list(opts.values()) if isinstance(opts, dict) else list(opts)


def _wait_idle(v, rounds=3):
    """Wait until the Viewer's workers have nothing left (a result can ask for more).
    A view with several threads is idle when all of them are: one task for each, done
    only once every one of them has started."""
    for _ in range(rounds):
        for p in v.pools.values():
            n = getattr(p, "_max_workers", 1)
            gate = threading.Barrier(n)
            for f in [p.submit(gate.wait) for _ in range(n)]:
                f.result()


class Bench:
    def __init__(self, path, args):
        self.path, self.args = path, args
        self.rows, self.info = [], {}

    def say(self, msg):
        print(msg, flush=True)

    # ---------------------------------------------------------------- set up
    def _open(self):
        from .registry import Registry
        cache, _ = config.cache_gb()
        workers, _ = config.workers()
        from .core import pool
        from .core.run import MAX_READERS
        pool.warm(min(workers, MAX_READERS))  # (as the viewer does when it starts)
        t0 = time.perf_counter()
        self.reg = Registry(self.path, cache, workers, model=self.args.model)
        self.run, self.F = self.reg.get()
        run = self.run
        self.info.update(open_s=round(time.perf_counter() - t0, 3), cache_gb=cache)
        from .viewer import timing
        self.info.update(timing.run_info(run))
        self.say(f"cm1view bench: {run.model_label} {run.path}\n"
                 f"  grid {run.ni} x {run.nj} x {run.nk}, {len(run.times)} times, "
                 f"{run.workers} reader(s), cache {cache:.0f} GB, on {self.info['host']} "
                 f"({self.info['cpus']} CPUs, job {self.info['job'] or 'none'})\n"
                 f"  opened in {self.info['open_s']:.2f} s")

    def _build(self):
        """The Viewer and its page, as a browser session gets them."""
        from bokeh.document import Document
        from .viewer import app as A, timing
        t0 = time.perf_counter()
        self.v = v = A.Viewer(self.run, self.F, maxpix=config.get("maxpix"), reg=self.reg)
        t1 = time.perf_counter()
        doc = Document()
        doc.add_root(v.main().get_root(doc))
        t2 = time.perf_counter()
        _wait_idle(v)  # (the first map, asked for by the Viewer itself)
        try:
            page_bytes = timing.doc_bytes(doc)
        except Exception as e:  # noqa: BLE001
            page_bytes = None
            self.say(f"  (page size not measured: {e})")
        self.info.update(viewer_build_s=round(t1 - t0, 3), page_build_s=round(t2 - t1, 3),
                         page_models=len(doc.models), page_bytes=page_bytes)
        mb = f"{page_bytes / 1e6:.2f} MB" if page_bytes else "?"
        self.say(f"  viewer built in {t1 - t0:.2f} s, page models in {t2 - t1:.2f} s: "
                 f"{len(doc.models)} Bokeh models, {mb} first sent to a browser")
        self.tm = timing.Timing(v, path=None, browser=False, doc=doc)

    # ---------------------------------------------------------------- actions
    def act(self, label, view, fn, cold=False):
        """Do fn (it changes widgets or asks for an update), wait for every worker, and
        keep the last update of `view` it caused."""
        v = self.v
        if cold:
            self.run.clear_cache()
        n0 = len(self.tm.records)
        t0 = time.perf_counter()
        try:
            fn()
            _wait_idle(v)
        except Exception as e:  # noqa: BLE001
            self.say(f"  {label}: failed ({type(e).__name__}: {e})")
            self.rows.append(dict(label=label, view=view, error=str(e)))
            return
        wall = time.perf_counter() - t0
        new = self.tm.records[n0:]
        mine = [r for r in new if r.get("view") == view]
        row = dict(label=label, view=view, wall=round(wall, 4),
                   also=sorted({r["view"] for r in new if r.get("view") != view}))
        if mine:
            row.update(mine[-1])
        else:
            row["error"] = "no update"
        self.rows.append(row)
        self._print_row(row)

    def core(self, label, fn):
        """An action that is not an update of one of the page's views (tracking, a
        swath): fn() timed whole, with nothing cached.  Its reads, on its own thread and
        the ones reading ahead for it, are split out as for a view."""
        from .viewer import timing
        self.run.clear_cache()
        self.F.clear_planes()
        row = dict(label=label, view="core")
        count = timing.counting()
        t0 = time.perf_counter()
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            self.say(f"  {label}: failed ({type(e).__name__}: {e})")
            self.rows.append(dict(row, error=str(e)))
            return
        wall = time.perf_counter() - t0
        read = min(count.secs, wall)
        row.update(wall=round(wall, 4), total=round(wall, 4), read=round(read, 4),
                   compute=round(wall - read, 4), disk_reads=count.fields)
        self.rows.append(row)
        self._print_row(row)

    def picked(self, label, fn):
        """fn picks a tool, with nothing cached: the time until the reads it starts in
        the background are done (no view updates, so no read/compute split)."""
        self.run.clear_cache()
        self.F.clear_planes()
        n0 = self.run.cache_info()[2]
        t0 = time.perf_counter()
        try:
            fn()
            _wait_idle(self.v)
        except Exception as e:  # noqa: BLE001
            self.say(f"  {label}: failed ({type(e).__name__}: {e})")
            self.rows.append(dict(label=label, view="pre", error=str(e)))
            return
        wall = time.perf_counter() - t0
        row = dict(label=label, view="pre", wall=round(wall, 4), total=round(wall, 4),
                   disk_reads=self.run.cache_info()[2] - n0)
        self.rows.append(row)
        self._print_row(row)

    @contextmanager
    def _in_parts(self):
        """Meanwhile nothing fits the 3D cache: every request reads the part of each
        field it needs, as on a grid whose fields are larger than the cache."""
        self.run.fits = lambda nbytes: False
        try:
            yield
        finally:
            del self.run.fits  # (the class's again)

    def _set(self, w, value):
        """A widget changed as from the page (sliders and number boxes redraw on their
        released value)."""
        if "value_throttled" in w.param:
            with param.edit_constant(w):
                w.param.update(value=value, value_throttled=value)
        else:
            w.value = value

    def _time(self, t):
        """Show time t on the map (only the map: the panels follow a released slider,
        and the actions ask for them themselves)."""
        v = self.v
        if v.t == t:
            v.request_map()
        else:
            v.tslider.value = t

    def _watch_memory(self):
        """Keep the most the job holds while the actions play (looked at twice a
        second: process memory and cached fields, see config.job_memory_used_gb)."""
        self.info["job_peak_gb"] = config.job_memory_used_gb()
        done = threading.Event()
        if self.info["job_peak_gb"] is None:
            return done

        def look():
            while not done.wait(0.5):
                now = config.job_memory_used_gb()
                if now is not None:
                    self.info["job_peak_gb"] = max(self.info["job_peak_gb"], now)
        threading.Thread(target=look, daemon=True).start()
        return done

    def play(self):
        watched = self._watch_memory()
        self._open()
        self._build()
        v, run, F = self.v, self.run, self.F
        nt = len(run.times)
        if self.args.field:
            if self.args.field not in F:
                raise SystemExit(f"cm1view bench: no field {self.args.field} in this run")
            self._set(v.fill_var, self.args.field)
            _wait_idle(v)
        t0 = self.args.time if self.args.time is not None else nt // 2
        t0 = max(0, min(nt - 1, t0))
        times = list(dict.fromkeys(min(t0 + i, nt - 1) for i in range(self.args.steps + 1)))
        X0, X1, Y0, Y1 = v.extent
        xc, yc, w, h = (X0 + X1) / 2, (Y0 + Y1) / 2, X1 - X0, Y1 - Y0
        f2 = self.args.field2 or next(
            (n for n in ("winterp", "thpert", "dbz", "uinterp", "qr", "prspert")
             if n in F and F[n].ndim == 3 and n != v.fill_var.value), None)
        self.say("\n" + self._head())

        # ---- the map
        self.act("map: first time (nothing cached)", "map", lambda: self._time(times[0]),
                 cold=True)
        for t in times[1:]:
            self.act(f"map: step to a new time ({t})", "map", lambda t=t: self._time(t))
        self.act("map: back to a time already read", "map", lambda: self._time(times[0]))
        top = float(v.fill_lvl.end or 1.0)
        lvl = float(v.fill_lvl.value)
        self.act("map: level +1 km", "map", lambda: self._set(v.fill_lvl, min(lvl + 1, top)))
        self.act("map: filled contours", "map", lambda: self._set(v.fill_style, "contourf"))
        self.act("map: back to pixels", "map", lambda: self._set(v.fill_style, "image"))
        if v.ovs:
            o = v.ovs[0]
            on = o["on"].value
            self.act(f"map: contours {'off' if on else 'on'}", "map",
                     lambda: self._set(o["on"], not on))
            self.act(f"map: contours {'on' if on else 'off'}", "map",
                     lambda: self._set(o["on"], on))
        if v.vecs:
            o = v.vecs[0]
            self.act("map: wind vectors on", "map", lambda: self._set(o["on"], True))
            if "style" in o and "streamlines" in _values(o["style"]):
                was = o["style"].value
                self.act("map: streamlines", "map",
                         lambda: self._set(o["style"], "streamlines"))
                self._set(o["style"], was)
                _wait_idle(v)
            self.act("map: vectors off", "map", lambda: self._set(o["on"], False))
        if f2:
            self.act(f"map: switch field to {f2} (first read)", "map",
                     lambda: self._set(v.fill_var, f2))
            # the column maximum of that field, then the column fields: every level
            # of one or several inputs, read together in the reader processes
            if "colmax" in _values(v.fill_mode):
                was = v.fill_mode.value
                self.act(f"map: column max of {f2}", "map",
                         lambda: self._set(v.fill_mode, "colmax"))
                self._set(v.fill_mode, was)
                _wait_idle(v)
        shown = v.fill_var.value
        for name, what in (("wmax", "column-max w"), ("sbcape", "surface-based CAPE")):
            if name in F and name != shown:
                self.act(f"map: {what} ({name})", "map",
                         lambda name=name: self._set(v.fill_var, name), cold=True)
        if v.fill_var.value != shown:
            self._set(v.fill_var, shown)
            _wait_idle(v)
        quarter = (xc - w / 8, xc + w / 8, yc - h / 8, yc + h / 8)

        def zoom(view):
            v.view = view
            v.request_map()
        self.act("map: zoom in 4x", "map", lambda: zoom(quarter))
        self.act("map: whole domain", "map", lambda: zoom(v.extent))

        # ---- soundings
        def sounding(x, y):
            v.points = [("pt", (x, y), None)]
            v.request_soundings()
        self.act("sounding: first (reads its 3D fields)", "snd", lambda: sounding(xc, yc))
        self.act("sounding: another point (cached)", "snd",
                 lambda: sounding(xc + w / 10, yc))

        # ---- cross-section
        def section():
            v.xs_pts = [(X0 + w / 4, yc), (X0 + 3 * w / 4, yc)]
            v.request_xsec()
        self.act("cross-section: first", "xs", section)
        self.act("cross-section: again (cached)", "xs", section)

        # ---- both at a time not read yet (as when stepping with them open; the map
        # of that time is read meanwhile, as in the viewer)
        later = [t for t in range(times[-1] + 1, nt)] + [t for t in range(times[0])][::-1]
        if later:
            t1 = later[0]
            self.act(f"sounding: at a new time ({t1})", "snd",
                     lambda: (self._time(t1), sounding(xc, yc)))
            if len(later) > 1:  # (not t1 + 1: the sounding read that ahead)
                t2 = later[2] if len(later) > 2 else later[1]
                self.act(f"cross-section: at a new time ({t2})", "xs",
                         lambda: (self._time(t2), section()))

        # ---- picking the tool reads its fields at the shown time in the background
        # (here the user waits for that read before clicking: the click is then cached)
        for tool, click, other in (("Sounding", lambda: sounding(xc, yc - h / 10), "snd"),
                                   ("Cross-section", section, "xs")):
            what = tool.lower()
            v.mode.set(None)
            self.picked(f"{what}: tool picked (early load)", lambda tool=tool: v.mode.set(tool))
            self.act(f"{what}: first click after picking the tool", other, click)
        v.mode.set(None)
        _wait_idle(v)

        # ---- the same two read in parts, as when their fields do not fit the 3D cache
        # (other places than above, with nothing cached: compare with the first ones)
        def section2():
            v.xs_pts = [(X0 + w / 4, yc + h / 10), (X0 + 3 * w / 4, yc + h / 10)]
            v.request_xsec()
        with self._in_parts():
            self.act("sounding: read in parts", "snd",
                     lambda: sounding(xc - w / 10, yc), cold=True)
            self.act("cross-section: read in parts", "xs", section2, cold=True)

        # ---- 3D
        if not self.args.no_3d:
            def scene():
                v.box = None  # (the view's region)
                v.request_3d()
            self.act("3D: view of a quarter of the domain", "3d",
                     lambda: (zoom(quarter), scene()))
            # (the same scene from the box alone, nothing cached, its lines traced again)
            with self._in_parts():
                self.act("3D: read in parts", "3d",
                         lambda: (v._st_cache.clear(), scene()), cold=True)

        # ---- work over several outputs, each timed whole
        n = min(self.args.window, nt - 1)
        if n > 0:
            self._over_times(max(0, min(times[0], nt - 1 - n)), n)

        self.info["peak_rss_gb"] = round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2, 2)
        watched.set()
        if self.info["job_peak_gb"] is not None:
            self.info["job_peak_gb"] = round(self.info["job_peak_gb"], 2)
            self.say(f"\nmost memory held by the job {self.info['job_peak_gb']:.1f} GB "
                     f"(every process in it and the cached fields; file cache not "
                     f"counted)")
        else:
            self.say(f"\npeak memory of this process {self.info['peak_rss_gb']:.1f} GB "
                     f"(not the readers, nor cached fields it has not looked at: no "
                     f"job memory limit to measure under)")
        self.say("columns: seconds; MB = what the update sends to the browser; "
                 "reads = whole fields or single levels read from disk\n"
                 "(tracking and the swath have no apply: they are not views of the page)")
        v.close()
        return dict(info=self.info, actions=self.rows)

    def _over_times(self, ta, n):
        """Tracking and a swath over the n outputs after output ta."""
        from .core import swath, track
        v, run, F = self.v, self.run, self.F
        have = set(track.metrics(run).values())
        metric = next((m for m in ("uh", "w") if m in have), None)
        if metric:
            def follow():
                opts = dict(v._trk_opts(), metric=metric, zkm=1.0, stop=None,
                            t_from=ta, t_to=ta + n)
                track.track(run, ta, None, None, opts, "forward", fields=F)
            self.core(f"tracking: {n} outputs on {track.METRIC_LABEL[metric]}", follow)
        name = next((x for x in ("uh25", "winterp", v.fill_var.value) if x in F), None)
        if name:
            lay = dict(field=name, mode="height", z=1.0,
                       reduce=dict(op="max", t0=float(run.times[ta]), t1=None, every=1))
            # (a swath is kept in the cache folder: this one in a folder of its own,
            # so it is computed here and leaves nothing behind)
            os.makedirs(config.cache_dir("timing"), exist_ok=True)
            kept, tmp = swath.CACHE_DIR, tempfile.mkdtemp(
                prefix="bench-swath-", dir=config.cache_dir("timing"))
            swath.CACHE_DIR = tmp
            try:
                self.core(f"swath: max of {name} over {n + 1} outputs",
                          lambda: swath.reduce(run, F, lay, ta + n))
            finally:
                swath.CACHE_DIR = kept
                shutil.rmtree(tmp, ignore_errors=True)
        # trajectories traced through the winds (as for a run without parcel output),
        # the whole domain's seeding, from whole volumes and read in parts
        from .core import trajcalc
        if all(x in run.vars for x in trajcalc.WINDS):
            lat, span = trajcalc.lattice(run), (ta, ta + n)
            what = f"trajectories: {n} outputs, {lat['nx'] * lat['ny'] * lat['nz']} parcels"
            self.core(what, lambda: trajcalc.trace(run, lat, span=span))
            with self._in_parts():
                self.core("trajectories: read in parts",
                          lambda: trajcalc.trace(run, lat, span=span))

    # ---------------------------------------------------------------- printing
    COLS = (("read", 7), ("compute", 8), ("apply", 7), ("total", 7))

    def _head(self):
        return (f"{'action':<44}" + "".join(f"{c:>{n}}" for c, n in self.COLS)
                + f"{'MB':>8}{'reads':>6}")

    def _print_row(self, r):
        if r.get("error") and "total" not in r:
            self.say(f"{r['label']:<44}  {r['error']}")
            return
        line = f"{r['label'][:43]:<44}"
        for c, n in self.COLS:
            x = r.get(c)
            line += f"{'-' if x is None else f'{x:.3f}':>{n}}"
        b, n = r.get("bytes"), r.get("disk_reads", 0)
        line += f"{'-' if b is None else f'{b / 1e6:.2f}':>8}{n:>6}"
        if r.get("error"):
            line += f"  ({r['error'][:60]})"
        self.say(line)
