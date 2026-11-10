"""Timing log for the viewer:  cm1view RUN --timing [FILE]

Every map, sounding, cross-section and 3D update is timed and written as one JSON line,
split into where the time goes:

    queue    request -> its job starts (the view's worker still busy with an older one)
    read     reading model output in the job (about 0 when the fields were cached;
             disk_reads counts the whole fields and single levels read from disk)
    compute  the rest of the job (derived fields, contours, figures)
    wait     job done -> picked up on the page thread
    apply    updating the Bokeh / Panel models (Python side, with the changes Panel
             puts off to the next tick)
    bytes    sent to the browser for it (all websocket traffic of that page meanwhile)
    echo     apply done -> the browser has drawn it and answered (network both ways,
             unpacking the data and drawing)
    browser  the draw itself, measured in the page (part of echo)
    total    request -> drawn in the browser: about click to picture

plus a ping (an empty round trip) when the page loads and every minute, and the page
load itself.  Keep the tab in front while timing: a hidden tab does not draw, so its
updates never echo.  Summary of a log:  cm1view bench --report FILE

The same hooks time the headless benchmark (cm1view.bench), with no browser: there
`bytes` is the size of the Bokeh patch the update would send."""

import json
import os
import platform
import socket
import threading
import time
import weakref
from functools import wraps

LOG = None  # the log file when timing is on (set by cm1view --timing)

# view: (request, job, apply) methods of the Viewer; each job and apply takes the
# request's generation number as its last argument
VIEWS = {
    "map": ("request_map", "_map_job", "_apply_map"),
    "snd": ("request_soundings", "_snd_job", "_apply_snd"),
    "xs": ("request_xsec", "_xs_job", "_apply_xs"),
    "3d": ("request_3d", "_3d_job", "_apply_3d"),
}
ECHO_TIMEOUT = 60.0  # s: an update not drawn by then is logged without the browser part
PING_EVERY = 60_000  # ms

_reads = threading.local()  # read seconds and fields read by the current job's thread
_sent = weakref.WeakKeyDictionary()  # Bokeh document -> websocket bytes sent to it
_write_lock = threading.Lock()


# ------------------------------------------------------------------ reads
def _timed_read(run, f, kind):
    """f, with its time added to the calling thread's read total (outermost call only:
    read_level can call load_volumes), and the disk reads it makes counted: kind
    "volumes" (load_volumes: the fields not cached), "levels" (read_levels /
    read_heights: the fields not cached), "plane" (read_level / read_box: one, unless
    its field is cached), "boxes" (read_boxes: its fields) or "other" (one)."""
    @wraps(f)
    def g(*a, **k):
        depth = getattr(_reads, "depth", 0)
        try:
            if kind == "volumes":
                names, t = a[0], a[1] if len(a) > 1 else k.get("t")
                n = sum(run.cached(x, t) is None for x in dict.fromkeys(names))
            elif kind == "levels":
                n = sum(run.cached(x, a[1]) is None for x in dict.fromkeys(a[0])) \
                    if depth == 0 else 0
            elif kind == "plane":
                n = int(depth == 0 and run.cached(a[0], a[1]) is None)
            elif kind == "boxes":
                n = len(dict.fromkeys(a[0])) if depth == 0 else 0
            else:
                n = int(depth == 0)
            _reads.fields = getattr(_reads, "fields", 0) + n
        except Exception:  # noqa: BLE001
            pass
        _reads.depth = depth + 1
        t0 = time.perf_counter()
        try:
            return f(*a, **k)
        finally:
            _reads.depth = depth
            if depth == 0:
                _reads.secs = getattr(_reads, "secs", 0.0) + time.perf_counter() - t0
    return g


def time_reads(run):
    """Time a run's reads (once per run: runs are shared by the browser sessions)."""
    if getattr(run, "_cv_timed", False):
        return
    for name, kind in (("read_level", "plane"), ("load_volumes", "volumes"),
                       ("read_levels", "levels"), ("read_heights", "levels"),
                       ("reduce_levels", "plane"),
                       ("read_box", "plane"), ("read_boxes", "boxes"),
                       ("mean_profiles", "other"),
                       ("_read_volume_local", "plane")):
        f = getattr(run, name, None)
        if f is not None:
            setattr(run, name, _timed_read(run, f, kind))
    run._cv_timed = True


def _reset_reads():
    _reads.secs, _reads.fields = 0.0, 0


# ------------------------------------------------------------------ bytes
def count_websocket():
    """Count the bytes the server writes to each page (once per process).  Counted in
    Tornado's websocket write, under both senders: Bokeh's handler, and Panel, which
    writes some updates there directly (panel.io.document.dispatch_tornado)."""
    from tornado.websocket import WebSocketHandler
    if getattr(WebSocketHandler, "_cv_counted", False):
        return
    orig = WebSocketHandler.write_message

    def write_message(self, message, binary=False):
        try:
            conn = getattr(self, "connection", None)  # (Bokeh's handler: its session)
            if conn is not None and isinstance(message, (bytes, str)):
                doc = conn.session.document
                _sent[doc] = _sent.get(doc, 0) + len(message)
        except Exception:  # noqa: BLE001
            pass
        return orig(self, message, binary)

    WebSocketHandler.write_message = write_message
    WebSocketHandler._cv_counted = True


def sent(doc):
    return _sent.get(doc, 0) if doc is not None else 0


def message_bytes(msg):
    """Size of a Bokeh protocol message as sent (header, metadata, content, buffers)."""
    n = len(msg.header_json) + len(msg.metadata_json) + len(msg.content_json)
    for b in msg.buffers:
        data = getattr(b, "data", b)
        n += data.nbytes if hasattr(data, "nbytes") else len(data)
    return n


def patch_bytes(events):
    """Size of the PATCH-DOC message carrying Bokeh document change events."""
    from bokeh.protocol import Protocol
    events = [e for e in events if hasattr(e, "to_serializable")]
    return message_bytes(Protocol().create("PATCH-DOC", events)) if events else 0


def doc_bytes(doc):
    """Size of the whole document as first sent to a page."""
    from bokeh.protocol import Protocol
    return message_bytes(Protocol().create("PULL-DOC-REPLY", "0", doc))


# ------------------------------------------------------------------ log
def write(path, rec):
    if not path:
        return
    rec = dict(rec, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    with _write_lock:
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")


def run_info(run):
    """What the log's first line says about the machine and the run."""
    import bokeh
    import panel
    return dict(host=socket.gethostname(), cpus=os.cpu_count(),
                job=os.environ.get("PBS_JOBID") or os.environ.get("SLURM_JOB_ID"),
                python=platform.python_version(), bokeh=bokeh.__version__,
                panel=panel.__version__, run=run.path,
                model=getattr(run, "model_label", ""), grid=[run.ni, run.nj, run.nk],
                times=len(run.times), workers=getattr(run, "workers", None))


def _r(x):
    return None if x is None else round(x, 4)


# ------------------------------------------------------------------ the recorder
class Timing:
    """Times one Viewer's updates.  path: the JSON-lines log (None: records are only
    kept in .records).  doc: a Bokeh document to measure patches in (headless)."""

    def __init__(self, v, path=None, browser=True, doc=None):
        self.v, self.path = v, path
        self.lock = threading.Lock()
        self.req = {}       # (view, gen) -> the record being filled
        self.pending = {}   # stamp id -> record waiting for the browser's echo
        self.records = []
        self._seq = 0
        self.ping = None    # last network round trip (s)
        self.src = None
        self._doc, self._events, self._collect = doc, [], False
        time_reads(v.run)
        for view, names in VIEWS.items():
            self._wrap(view, *names)
        if doc is not None:
            doc.on_change(self._on_doc_change)
        if browser and v.doc is not None:
            count_websocket()
            self._stamp_model()

    # ---- what each update shows (one short line)
    def _what(self, view):
        v = self.v
        try:
            if view == "map":
                x0, x1, y0, y1 = v.view
                X0, X1, Y0, Y1 = v.extent
                zoom = max((X1 - X0) / max(x1 - x0, 1e-9), (Y1 - Y0) / max(y1 - y0, 1e-9))
                nov = sum(o["on"].value for o in v.ovs)
                nvec = sum(o["on"].value for o in v.vecs)
                nfill = sum(o["on"].value for o in v.fills)
                return dict(field=v._fill_name(), level=f"{v.fill_mode.value} "
                            f"{v.fill_lvl.value:g}", style=v.fill_style.value,
                            fills=nfill, contours=nov, vectors=nvec, zoom=round(zoom, 2))
            if view == "snd":
                return dict(points=len(v.points))
            if view == "xs":
                return dict(field=v.xs_fill.value,
                            contours=sum(o["on"].value for o in v.xs_ovs),
                            vectors=sum(o["on"].value for o in v.xs_vecs))
            if view == "3d":
                return dict(isosurfaces=sum(o["on"].value for o in v.isos),
                            streamlines=bool(v.st_on.value))
        except Exception:  # noqa: BLE001
            pass
        return {}

    # ---- the hooks
    def _wrap(self, view, rq_name, job_name, ap_name):
        v = self.v
        f_rq, f_job, f_ap = (getattr(v, n) for n in (rq_name, job_name, ap_name))

        @wraps(f_rq)
        def request(*a, **k):
            # registered before the request is made: its job can start at once, in
            # another thread (each request raises the view's generation by one)
            g, t0 = v.gen[view] + 1, time.perf_counter()
            rec = dict(kind="view", view=view, t=v.t, t_req=t0, **self._what(view))
            with self.lock:
                self.req[(view, g)] = rec
            try:
                return f_rq(*a, **k)
            finally:
                if v.gen[view] != g:  # (nothing went to the worker)
                    with self.lock:
                        if self.req.get((view, g)) is rec:
                            del self.req[(view, g)]

        @wraps(f_job)
        def job(*a, **k):
            g = a[-1]
            rec = self.req.get((view, g))
            _reset_reads()
            t0 = time.perf_counter()
            if rec is not None:
                rec["t_job"], rec["job_thread"] = t0, threading.get_ident()
            try:
                return f_job(*a, **k)
            finally:
                if rec is not None:
                    self._job_done(rec)

        @wraps(f_ap)
        def apply(*a, **k):
            g = a[-1]
            rec = self.req.get((view, g))
            if rec is not None and rec.get("job_thread") == threading.get_ident():
                self._job_done(rec)  # (headless: the job applies before it returns)
            b0 = sent(v.doc)
            self._events, self._collect = [], self._doc is not None
            t0 = time.perf_counter()
            try:
                return f_ap(*a, **k)
            finally:
                t1 = time.perf_counter()
                self._collect = False
                if rec is not None and g == v.gen[view]:
                    self._applied(view, g, rec, a[0], t0, t1, b0)

        setattr(v, rq_name, request)
        setattr(v, job_name, job)
        setattr(v, ap_name, apply)

    def _job_done(self, rec):
        if "t_job_end" not in rec and "t_job" in rec:
            rec["t_job_end"] = time.perf_counter()
            rec["read"] = getattr(_reads, "secs", 0.0)
            rec["disk_reads"] = getattr(_reads, "fields", 0)

    def _applied(self, view, g, rec, res, t0, t1, b0):
        with self.lock:
            self.req.pop((view, g), None)
            older = [key for key in self.req if key[0] == view and key[1] < g]
            for key in older:
                del self.req[key]
        rec.setdefault("t_job", t0)
        rec.update(t_apply=t0, t_apply_end=t1, superseded=len(older), b0=b0)
        if isinstance(res, Exception):
            rec["error"] = f"{type(res).__name__}: {res}"[:200]
        if self._doc is not None:
            try:
                rec["bytes"] = patch_bytes(self._events)
            except Exception as e:  # noqa: BLE001
                rec["bytes_error"] = str(e)[:120]
            self._events = []
        if self.src is not None:
            self._stamp_later(rec)
        else:
            self._finish(rec)

    def _stamp_later(self, rec, ticks=2):
        """Send the stamp once Panel has made the model changes it put off to the next
        tick (pane images, Plotly figures, HTML: Panel defers them when the change does
        not come from a browser event), so it follows everything the update sends."""
        doc = self.v.doc
        if ticks <= 0 or doc is None:
            self._send_stamp(rec)
        else:
            doc.add_next_tick_callback(lambda: self._stamp_later(rec, ticks - 1))

    def _on_doc_change(self, event):
        if self._collect:
            self._events.append(event)

    # ---- the browser's echo
    def _stamp_model(self):
        """An invisible glyph whose tags carry stamps: the page answers each one once it
        has drawn everything sent before it (two animation frames later)."""
        from bokeh.models import ColumnDataSource, CustomJS
        self.src = ColumnDataSource(dict(x=[], y=[]))
        self.v.fig.scatter("x", "y", source=self.src, visible=False)
        self.src.js_on_change("tags", CustomJS(args=dict(src=self.src), code="""
            const t = src.tags
            if (t.length === 2 && t[0] === "s") {
                const t0 = performance.now(), id = t[1]
                requestAnimationFrame(() => requestAnimationFrame(() => {
                    src.tags = ["b", id, (performance.now() - t0) / 1000]
                }))
            }"""))
        self.src.on_change("tags", self._on_echo)

    def _send_stamp(self, rec):
        self._expire()
        self._seq += 1
        rec["t_stamp"] = time.perf_counter()
        self.pending[self._seq] = rec
        self.src.tags = ["s", self._seq]

    def send_ping(self):
        if self.src is not None:
            self._send_stamp(dict(kind="ping", t_req=time.perf_counter()))

    def _on_echo(self, attr, old, new):
        if not (isinstance(new, list) and len(new) == 3 and new[0] == "b"):
            return
        rec = self.pending.pop(new[1], None)
        if rec is None:
            return
        rec["t_echo"] = time.perf_counter()
        rec["browser"] = float(new[2])
        if rec["kind"] == "ping":
            self.ping = rec["t_echo"] - rec["t_stamp"] - rec["browser"]
        self._finish(rec)

    def _expire(self):
        now = time.perf_counter()
        for i, rec in list(self.pending.items()):
            if now - rec["t_stamp"] > ECHO_TIMEOUT:
                self.pending.pop(i, None)
                rec["no_echo"] = True
                self._finish(rec)

    # ---- one log line
    def _finish(self, rec):
        if rec["kind"] == "ping":
            if "t_echo" not in rec:
                return
            out = dict(kind="ping", net=_r(rec["t_echo"] - rec["t_stamp"] - rec["browser"]),
                       browser=_r(rec["browser"]))
        else:
            # (the job may still be finishing its last lines when its result is applied)
            job_end = min(rec.get("t_job_end", rec["t_apply"]), rec["t_apply"])
            job = max(job_end - rec["t_job"], 0.0)
            read = min(rec.get("read", 0.0), job)
            out = {k: rec[k] for k in rec
                   if not k.startswith("t_") and k not in ("b0", "job_thread")}
            # apply: to the stamp when there is one (Panel's deferred changes included)
            end = rec.get("t_stamp", rec["t_apply_end"])
            out.update(queue=_r(rec["t_job"] - rec["t_req"]), read=_r(read),
                       compute=_r(job - read), wait=_r(rec["t_apply"] - job_end),
                       apply=_r(end - rec["t_apply"]),
                       cached=rec.get("disk_reads", 0) == 0)
            if "t_echo" in rec:
                out.update(echo=_r(rec["t_echo"] - end), browser=_r(rec["browser"]),
                           bytes=sent(self.v.doc) - rec["b0"], ping=_r(self.ping))
                end = rec["t_echo"]
            out["total"] = _r(end - rec["t_req"])
        self.records.append(out)
        write(self.path, out)


# ------------------------------------------------------------------ the live viewer
def attach(v, t_session):
    """Time Viewer v's updates into LOG (from create_app, once v is built)."""
    if not LOG:
        return None
    tm = Timing(v, LOG)
    v._timing = tm
    built = time.perf_counter()
    doc = v.doc

    def loaded():  # the page is up in the browser
        n = len(doc.models) if doc is not None else None
        write(LOG, dict(kind="page", build=_r(built - t_session),
                        load=_r(time.perf_counter() - t_session), bytes=sent(doc),
                        models=n))
        tm.send_ping()

    import panel as pn
    pn.state.onload(loaded)
    if doc is not None:
        pn.state.add_periodic_callback(tm.send_ping, period=PING_EVERY)
    return tm


def start(path, run=None):
    """Turn timing on for this server: the log file, and its first line."""
    global LOG
    LOG = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    write(LOG, dict(kind="start", **(run_info(run) if run is not None else
                                     dict(host=socket.gethostname(), cpus=os.cpu_count()))))
    return LOG


# ------------------------------------------------------------------ summary
def _med(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


PARTS = ("queue", "read", "compute", "wait", "apply", "echo", "browser", "total")


def summarize(path, out=print):
    """Median timings of a log, per view and cached / not cached."""
    recs = []
    with open(path) as f:
        for line in f:
            try:
                recs.append(json.loads(line))
            except ValueError:
                continue
    for r in recs:
        if r.get("kind") == "start":
            out(f"{r.get('host')} ({r.get('cpus')} CPUs, job {r.get('job') or 'none'}), "
                f"run {r.get('run', '?')} {r.get('grid', '')} {r.get('times', '')} times, "
                f"{r.get('workers')} readers")
    pages = [r for r in recs if r.get("kind") == "page"]
    for r in pages:
        out(f"page load: built {r['build']:.2f} s, in the browser after {r['load']:.2f} s, "
            f"{(r['bytes'] or 0) / 1e6:.2f} MB, {r['models']} Bokeh models")
    pings = [r["net"] for r in recs if r.get("kind") == "ping"]
    if pings:
        out(f"ping (network round trip): median {_med(pings) * 1000:.0f} ms over "
            f"{len(pings)}")
    views = [r for r in recs if r.get("kind") == "view"]
    if not views:
        out("no view updates in the log")
        return
    out("")
    out("median seconds (bytes in MB)")
    head = f"{'view':<5}{'cached':<8}{'n':>4}" + "".join(f"{p:>9}" for p in PARTS) \
        + f"{'MB':>8}{'missed':>8}"
    out(head)
    out("-" * len(head))
    for view in VIEWS:
        for cached in (False, True):
            rs = [r for r in views if r["view"] == view and r.get("cached") == cached
                  and not r.get("error")]
            if not rs:
                continue
            row = f"{view:<5}{'yes' if cached else 'no':<8}{len(rs):>4}"
            for p in PARTS:
                m = _med([r.get(p) for r in rs])
                row += f"{'-' if m is None else f'{m:.3f}':>9}"
            mb = _med([r.get("bytes") for r in rs])
            row += f"{'-' if mb is None else f'{mb / 1e6:.2f}':>8}"
            row += f"{sum(r.get('superseded', 0) for r in rs):>8}"
            out(row)
    errs = [r for r in views if r.get("error")]
    if errs:
        out(f"\n{len(errs)} update(s) ended in an error (left out above), e.g. "
            f"{errs[0]['error']}")
    noecho = sum(1 for r in views if r.get("no_echo"))
    if noecho:
        out(f"{noecho} update(s) never drawn within {ECHO_TIMEOUT:.0f} s (hidden tab?)")
    out("\nmissed: requests replaced by a newer one before they were drawn (e.g. while "
        "dragging the time slider)")
