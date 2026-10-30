"""Session files: what the viewer shows (run, time, map view, the map's fill, more
fills, contours and vectors, the storm track, soundings, the cross-section, the 3D
setup, series, distributions, the active tool and workspace) saved to JSON and put
back, from the Session dialog or with ?session=/path/to/file.json.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import io
import json
import math
import os
import traceback
from functools import partial

import numpy as np
import panel as pn
from panel.widgets.select import SingleSelectBase

from .. import config, pdecomp
from ..core import dist, series as ser
from ..theme import DIALOG_DARK
from .ui import PANELS, TOOL_OF, _html, held

FORMAT = 1  # the session file's version ("cm1view_session")

# the widgets of a layer row, in the order they are put back (a field before its
# colours and range, a level mode before its level, a vector before its reference)
FILL_KEYS = ("on", "var", "mode", "level", "style", "cmap", "rev", "auto", "vmin", "vmax",
             "alpha", "clip")
OV_KEYS = ("on", "var", "mode", "level", "levels", "color", "width", "negdash")
VEC_KEYS = ("on", "q", "level", "frame", "style", "density", "ref", "color")
# the first fill's widgets (Viewer attributes), the same way
MAIN_FILL = (("var", "fill_var"), ("op", "fill_op"), ("mode", "fill_mode"),
             ("level", "fill_lvl"), ("style", "fill_style"))
MAIN_STYLE = (("cmap", "fill_cmap"), ("rev", "fill_rev"), ("auto", "fill_auto"),
              ("vmin", "fill_min"), ("vmax", "fill_max"), ("nlev", "fill_nlev"),
              ("alpha", "fill_alpha"))
STORM = (("storm", "storm"), ("storm_u", "storm_u"), ("storm_v", "storm_v"))
# soundings: settings (Viewer attributes) and their plot style (Viewer.ps keys)
SND = (("avg", "avg"), ("parcel", "parcel"), ("units", "wunits"), ("prof_top", "prof_top"),
       ("base", "base_on"), ("compare", "compare"), ("follow", "follow"),
       ("storm_follow", "storm_follow"))
SND_STYLE = ("t", "td", "parcel", "base", "lw", "parcel_lw", "hodo_lw", "prof_lw", "ptop",
             "tmin", "tmax", "ring", "htop", "hheights", "shade", "barbs", "guides")
# the cross-section: its first fill, its style, extent and look
XS_FILL = (("var", "xs_fill"), ("style", "xs_fill_style"))
XS_STYLE = (("cmap", "xs_cmap"), ("rev", "xs_rev"), ("auto", "xs_auto"), ("vmin", "xs_min"),
            ("vmax", "xs_max"), ("nlev", "xs_nlev"), ("ztop", "xs_ztop"),
            ("height", "xs_height"), ("font", "xs_font"), ("grid", "xs_grid"),
            ("ab", "xs_ab"))
XS_LIMITS = (("smin", "xs_smin"), ("smax", "xs_smax"), ("zmin", "xs_zmin"),
             ("zmax", "xs_zmax"))  # (blank: the whole section)
# the 3D view: scene, floor, camera; isosurfaces; streamlines
V3 = (("ztop", "v3_ztop"), ("exag", "v3_exag"), ("smooth", "v3_smooth"), ("res", "v3_res"),
      ("ground", "v3_ground"), ("floor", "v3_floor"), ("floor_z", "v3_floor_z"),
      ("floor_cmap", "v3_floor_cmap"), ("floor_rev", "v3_floor_rev"),
      ("floor_range", "v3_floor_range"), ("floor_min", "v3_floor_min"),
      ("floor_max", "v3_floor_max"), ("follow", "v3_follow"), ("camera", "v3_cam"),
      ("drag", "v3_drag"))
ISO_KEYS = ("on", "var", "val", "color", "op")
STREAM = (("on", "st_on"), ("z", "st_z"), ("n", "st_n"), ("length", "st_len"),
          ("dir", "st_dir"), ("frame", "st_frame"), ("color", "st_color"))
# the Series and Distribution forms, and how they are drawn (field before derivative)
SER_FORM = (("field", "ser_field"), ("op", "ser_op"), ("vmode", "ser_vmode"), ("z", "ser_z"),
            ("z0", "ser_z0"), ("z1", "ser_z1"), ("region", "ser_region"),
            ("radius", "ser_radius"), ("offx", "ser_offx"), ("offy", "ser_offy"),
            ("reduce", "ser_reduce"), ("pct", "ser_pct"))
SER_LOOK = (("cmap", "ser_cmap"), ("rev", "ser_crev"))
SER_LIMS = ("t0", "t1", "y0", "y1", "s0", "s1", "c0", "c1")  # (Viewer.ser_lims, blank: auto)
DIST_FORM = (("field", "dist_field"), ("vmode", "dist_vmode"), ("z", "dist_z"),
             ("z0", "dist_z0"), ("z1", "dist_z1"), ("region", "dist_region"),
             ("radius", "dist_radius"), ("offx", "dist_offx"), ("offy", "dist_offy"))
DIST_LOOK = (("kind", "dist_kind"), ("norm", "dist_norm"), ("bins", "dist_bins"),
             ("cum", "dist_cum"), ("whis", "dist_whis"), ("logy", "dist_logy"),
             ("follow", "dist_follow"))
DIST_BLANK = (("lo", "dist_lo"), ("hi", "dist_hi"), ("x0", "dist_x0"), ("x1", "dist_x1"))


def read(path):
    """A session file's contents (ValueError when it is not one)."""
    with open(config.expand(path)) as f:
        s = json.load(f)
    if not isinstance(s, dict) or "cm1view_session" not in s:
        raise ValueError("not a cm1view session file")
    return s


def _plain(v):
    """A widget value as JSON (NaN -> None, numpy scalars -> Python)."""
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return v


def _put(w, v):
    """Set a widget, skipping values it cannot take (a field another run lacks, a
    level above this run's top, ...).  False when skipped."""
    try:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            lo, hi = getattr(w, "start", None), getattr(w, "end", None)
            v = v if lo is None else max(v, lo)
            v = v if hi is None else min(v, hi)
        if isinstance(w, SingleSelectBase):  # (Panel takes a value not among the options)
            have = w.values
            if isinstance(w.value, list):  # (MultiChoice: each of them)
                if not all(x in have for x in v):
                    return False
            elif v not in have:
                if not (isinstance(v, list) and tuple(v) in have):  # (JSON: no tuples)
                    return False
                v = tuple(v)
        w.value = v
        return True
    except (ValueError, TypeError):
        return False


class Sessions:
    _applying = False  # putting a session back: one map redraw at the end
    _views = 0  # views put back (each re-fits the map in the browser)

    def _build_session(self):
        """The Session dialog: a file, Save, Load and a download of the file."""
        self.ses_path = pn.widgets.TextInput(
            name="Session file", value=self._ses_default(), width=520,
            description="A JSON file: the run, time, map view, fills, contours, vectors, "
                        "storm track, soundings, section, 3D setup, series, "
                        "distributions and tool.  Open it later with Load, or with "
                        "?session=<file> in the address")
        self.ses_save = pn.widgets.Button(name="Save", icon="device-floppy",
                                          button_type="primary", width=90, margin=(5, 4))
        self.ses_load = pn.widgets.Button(name="Load", icon="folder-open",
                                          button_type="primary", button_style="outline",
                                          width=90, margin=(5, 4))
        self.ses_dl = pn.widgets.FileDownload(
            callback=self._session_download, filename="session.json", label="Download",
            button_type="light", button_style="outline", width=110, margin=(5, 4))
        self.ses_msg = _html()
        # another run's session: the page reloads with ?session= (the browser navigates)
        self.ses_go = pn.widgets.TextInput(visible=False)
        self.ses_go.jscallback(value="""
            const p = (cb_obj.value || '').trim();
            if (!p) return;
            const q = new URLSearchParams(window.location.search);
            q.set('session', p); q.delete('run'); q.delete('t');
            window.location.search = q.toString();
        """)
        self.ses_modal = pn.Modal(
            _html('<div class="cv-maptitle" style="font-size:16px"><b>Session</b></div>'
                  '<div class="cv-hint">Save what the viewer shows (time, map view, '
                  'fills, contours, vectors, storm track, soundings, section, 3D setup, '
                  'series, distributions, tool) and come back to it.  Series come back '
                  'from their cache and distributions are computed again.  A session of '
                  'another run opens that run.</div>'),
            self.ses_path, pn.Row(self.ses_save, self.ses_load, self.ses_dl, margin=0),
            self.ses_msg, self.ses_go, width=600, margin=10, stylesheets=[DIALOG_DARK])
        self.ses_btn = pn.widgets.Button(
            name="", icon="bookmark", button_type="light", button_style="outline",
            width=40, height=32, margin=(4, 2),
            description="Session: save what the viewer shows, or load a saved session")
        self.ses_btn.on_click(lambda e: (setattr(self.ses_msg, "object", ""),
                                         self.ses_modal.show()))
        self.ses_save.on_click(self._on_save_session)
        self.ses_load.on_click(self._on_load_session)
        self.ses_path.param.watch(self._on_ses_path, "value")
        self._on_ses_path(None)

    def _ses_default(self):
        return os.path.join(config.exports_dir(self.run.path, "sessions"), "session.json")

    def _on_ses_path(self, ev):
        self.ses_dl.filename = os.path.basename(self.ses_path.value) or "session.json"

    def _ses_note(self, html, error=False):
        color = ' style="color:#f87171"' if error else ""
        self.ses_msg.object = f'<div class="cv-status"{color}>{html}</div>'

    # ------------------------------------------------------------ collect
    def session_state(self):
        """What the viewer shows, as a JSON-ready dict."""
        x0, x1, y0, y1 = self.view
        tool = self.mode.value
        s = dict(
            cm1view_session=FORMAT, run=os.path.abspath(self.run.path),
            time_s=float(self.run.times[self.t]), view=[x0, x1, y0, y1],
            workspace=self.workspace.value, tool=tool,
            panel=dict(open=bool(self.panel_col.visible), tab=int(self.tabs.active),
                       full=bool(self.full)),
            fill={k: getattr(self, a).value for k, a in MAIN_FILL + MAIN_STYLE},
            diff={k: w.value for k, w in self.fill_diff.items()},
            fills=[{k: o[k].value for k in FILL_KEYS} for o in self.fills],
            contours=[{k: o[k].value for k in OV_KEYS} for o in self.ovs],
            vectors=[{k: o[k].value for k in VEC_KEYS} for o in self.vecs],
            storm={k: getattr(self, a).value for k, a in STORM},
            track=dict(path=self.trk_path.value, opts=self.trk_spec,
                       fixes=[[float(self.run.times[t]), f]
                              for t, f in sorted(self.fixes.items())]),
            soundings=self._snd_state(), section=self._xs_state(), view3d=self._3d_state(),
            series=self._ser_state(), distributions=self._dist_state(),
        )
        return _plain(s)

    def _time_s(self, t):
        return None if t is None else float(self.run.times[t])

    def _time_index(self, ts):
        """The output time nearest ts seconds (None: none within a second)."""
        if ts is None:
            return None
        times = np.asarray(self.run.times)
        t = int(np.argmin(np.abs(times - float(ts))))
        return t if abs(times[t] - float(ts)) <= 1.0 else None

    def _snd_state(self):
        lim = {k: v for k, v in self.snd_lim.items() if k != "prof_x"}
        if "prof_x" in self.snd_lim:  # (JSON keys are strings)
            lim["prof_x"] = {str(i): x for i, x in self.snd_lim["prof_x"].items()}
        return dict(points=[dict(kind=k, where=w, time_s=self._time_s(tp))
                            for k, w, tp in self.points],
                    **{k: getattr(self, a).value for k, a in SND},
                    style={k: self.ps[k].value for k in SND_STYLE}, zoom=lim)

    def _xs_state(self):
        return dict(points=[list(p) for p in self.xs_pts],
                    **{k: getattr(self, a).value for k, a in XS_FILL + XS_STYLE + XS_LIMITS},
                    diff={k: w.value for k, w in self.xs_diff.items()},
                    fills=[{k: o[k].value for k in FILL_KEYS if k in o} for o in self.xs_fills],
                    contours=[{k: o[k].value for k in OV_KEYS if k in o} for o in self.xs_ovs],
                    vectors=[{k: o[k].value for k in VEC_KEYS if k in o}
                             for o in self.xs_vecs])

    def _3d_state(self):
        return dict(box=self.box, seed_box=self.seed_box,
                    **{k: getattr(self, a).value for k, a in V3},
                    isos=[{k: o[k].value for k in ISO_KEYS} for o in self.isos],
                    vectors=[{k: o[k].value for k in VEC_KEYS if k in o} for o in self.svs],
                    stream={k: getattr(self, a).value for k, a in STREAM})

    def _ser_state(self):
        keys = list(self.series)
        return dict(items=[dict(recipe=v["recipe"], file=v.get("file")) for v in
                           self.series.values()],
                    active=keys.index(self.ser_pick.value) if self.ser_pick.value in keys
                    else None, view=self.ser_view.value,
                    form={k: getattr(self, a).value for k, a in SER_FORM},
                    **{k: getattr(self, a).value for k, a in SER_LOOK},
                    limits=dict(zip(SER_LIMS, (w.value for w in self.ser_lims))))

    def _dist_state(self):
        keys = list(self.dists)
        return dict(items=[dict(recipe=v["recipe"], time_s=self._time_s(v["t"]))
                           for v in self.dists.values()],
                    active=keys.index(self.dist_pick.value) if self.dist_pick.value in keys
                    else None,
                    form={k: getattr(self, a).value for k, a in DIST_FORM},
                    **{k: getattr(self, a).value for k, a in DIST_LOOK + DIST_BLANK})

    def _session_text(self):
        return json.dumps(self.session_state(), indent=1) + "\n"

    def _session_download(self):
        return io.BytesIO(self._session_text().encode())

    def _on_save_session(self, ev):
        path = config.expand(self.ses_path.value.strip())
        if path:
            self.confirm.ask([path], lambda: self._save_session(path))

    def _save_session(self, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(self._session_text())
        except OSError as e:
            self._ses_note(f"Could not save: {e}", error=True)
            return
        self._ses_note(f"Saved to <code>{path}</code> · open it again with "
                       f"<code>?session={path}</code>")

    def _on_load_session(self, ev):
        path = config.expand(self.ses_path.value.strip())
        try:
            s = read(path)
        except (OSError, ValueError) as e:
            self._ses_note(f"Could not load: {e}", error=True)
            return
        run = s.get("run")
        if run and os.path.abspath(config.expand(run)) != os.path.abspath(self.run.path):
            self.ses_go.value = path  # another run: the page reopens on it
            return
        skipped = self.apply_session(s)
        note = f"Loaded <code>{path}</code>"
        if skipped:
            note += f" · not in this run: {', '.join(skipped)}"
        self._ses_note(note)

    # ------------------------------------------------------------ put back
    def apply_session(self, s):
        """Put a session (session_state's dict) back.  Values this run cannot take are
        left as they are; returns their names."""
        skipped = []

        def put(w, v, name, blank=False):
            """blank: None is a value too (a limit left blank: auto)."""
            if (v is not None or blank) and not _put(w, v):
                skipped.append(f"{name} {v}")

        self._applying, self._due = True, set()
        try:
            if s.get("time_s") is not None:
                self.tslider.value = int(np.argmin(np.abs(np.asarray(self.run.times)
                                                          - float(s["time_s"]))))
            f = s.get("fill", {})
            for k, a in MAIN_FILL:
                put(getattr(self, a), f.get(k), k)
            self._put_diff(self.fill_diff, s.get("diff", {}), put)
            for k, a in MAIN_STYLE:
                put(getattr(self, a), f.get(k), k)
            self._put_rows(s.get("fills"), self.fills, self._add_fill, self._drop_fill,
                           FILL_KEYS, put)
            self._put_rows(s.get("contours"), self.ovs, self._add_overlay,
                           self._drop_overlay, OV_KEYS, put)
            self._put_rows(s.get("vectors"), self.vecs, self._add_vec, self._drop_vec,
                           VEC_KEYS, put)
            st = s.get("storm", {})
            for k, a in STORM:
                put(getattr(self, a), st.get(k), k)
            self._put_track(s.get("track"))
            self._put_soundings(s.get("soundings"), put)
            self._put_section(s.get("section"), put)
            self._put_3d(s.get("view3d"), put)
            self._put_series(s.get("series"), put, skipped)
            dists = self._put_dists(s.get("distributions"), put, skipped)
            if s.get("view"):
                self._put_view(s["view"])
            if s.get("workspace") in self.workspace.options:
                self.workspace.value = s["workspace"]
            self._put_tool(s.get("tool"), s.get("panel", {}))
        finally:
            self._applying = False
        self.request_map()
        self.request_soundings()  # (shows the soundings put back, or none)
        self.request_xsec()
        if self.box is not None and ("3d" in self._due or self.workspace.value == "3D"):
            self.request_3d()
        if dists:
            self._dist_restore(*dists)
        self._update_items()
        return skipped

    @staticmethod
    def _put_diff(ws, d, put):
        """A difference's on / Minus run / Minus time (fill_diff or xs_diff)."""
        for k in ("on", "run", "time"):
            if k not in d:
                continue
            w = ws[k]
            if k == "run" and d[k] and d[k] not in w.options.values():
                w.options = dict(w.options, **{d[k]: d[k]})  # a run not listed
            put(w, d[k], f"difference {k}")

    def _put_soundings(self, sd, put):
        if sd is None:
            return
        with held(self, "_hold_style"):
            for k, a in SND:
                put(getattr(self, a), sd.get(k), k)
            st = sd.get("style", {})
            for k in SND_STYLE:
                if k in st:
                    put(self.ps[k], st[k], k, blank=k in ("tmin", "tmax"))
        pts = []
        for p in sd.get("points") or []:
            kind, where = p.get("kind"), p.get("where")
            if kind not in ("pt", "trk", "mean"):
                continue
            ts = p.get("time_s")
            tp = self._time_index(ts)
            if ts is not None and tp is None:
                continue  # (pinned at a time this run lacks)
            pts.append((kind, None if where is None else tuple(float(x) for x in where), tp))
        self.points = pts[:4]
        zoom = sd.get("zoom") or {}  # (after prof_top: changing it un-zooms)
        lim = {k: tuple(v) for k, v in zoom.items() if k in ("skew", "hodo", "prof_z")}
        if zoom.get("prof_x"):
            lim["prof_x"] = {int(i): tuple(x) for i, x in zoom["prof_x"].items()}
        self.snd_lim = lim
        self._draw_points()

    def _put_section(self, xs, put):
        if xs is None:
            return
        with held(self, "_hold_xs"):
            for k, a in XS_FILL:
                put(getattr(self, a), xs.get(k), f"section {k}")
            self._put_diff(self.xs_diff, xs.get("diff", {}), put)
            for k, a in XS_STYLE:
                put(getattr(self, a), xs.get(k), f"section {k}")
            for k, a in XS_LIMITS:
                if k in xs:
                    put(getattr(self, a), xs[k], f"section {k}", blank=True)
            self._put_rows(xs.get("fills"), self.xs_fills, self._xs_add_fill,
                           self._xs_drop_fill, FILL_KEYS, put)
            self._put_rows(xs.get("contours"), self.xs_ovs, self._xs_add_contour,
                           self._xs_drop_contour, OV_KEYS, put)
            self._put_rows(xs.get("vectors"), self.xs_vecs, self._xs_add_vec,
                           self._xs_drop_vec, VEC_KEYS, put)
        pts = xs.get("points") or []
        self.xs_pts = [tuple(float(c) for c in p) for p in pts] if len(pts) == 2 else []
        self._draw_xs()
        self._xs_look()
        self._xs_limits(force=True)

    def _put_3d(self, v3, put):
        if v3 is None:
            return
        for k, a in V3:
            put(getattr(self, a), v3.get(k), f"3D {k}")
        for o, r in zip(self.isos, v3.get("isos") or []):
            for k in ISO_KEYS:
                put(o[k], r.get(k), f"isosurface {k}")
        self._put_rows(v3.get("vectors"), self.svs, self._add_sv, self._drop_sv, VEC_KEYS,
                       put)
        st = v3.get("stream", {})
        for k, a in STREAM:
            put(getattr(self, a), st.get(k), f"streamline {k}")
        if v3.get("box"):
            self._set_box([float(c) for c in v3["box"]])
        else:
            self._remove_box()
        if v3.get("seed_box"):
            self._set_seed_box([float(c) for c in v3["seed_box"]])
        else:
            self._clear_seed_box()
        self._floor_widgets()
        self._update_3d_labels()

    def _put_series(self, sr, put, skipped):
        """The series of the session, from the series cache (or the file they were
        loaded from); times not in the cache stay to be computed."""
        if sr is None:
            return
        self._cancel_series()
        for k, a in SER_FORM:
            put(getattr(self, a), sr.get("form", {}).get(k), f"series {k}")
        run, F = self.run, self.F
        with held(self, "_ser_hold"):
            self.series, self._ser_n = {}, 0  # (the colours of the session's order)
            keys, part = [], 0
            for it in sr.get("items") or []:
                try:
                    if it.get("file"):
                        path = config.expand(it["file"])
                        ds, recipe, _ = ser.load(run, path, F)
                        key = self._ser_key(recipe, path)
                    else:
                        recipe = ser.normalize(it["recipe"])
                        d = F[recipe["field"]]
                        centers = (ser.track_centers(self.fixes, len(run.times))
                                   if recipe["region"] == "track" else None)
                        ds = ser.cached(run, recipe, d.label, d.units, centers)
                        key, path = self._ser_key(recipe), ""
                except (OSError, ValueError, KeyError, TypeError) as e:
                    what = it.get("file") or (it.get("recipe") or {}).get("field")
                    skipped.append(f"series {what} ({e})")
                    continue
                self._ser_add(key, ds, recipe, loaded=path)
                keys.append(key)
                part += int(ds["computed"].sum()) < len(run.times)
            a = sr.get("active")
            if keys:
                self.ser_pick.value = keys[a if isinstance(a, int) and a < len(keys) else -1]
            else:
                self.ser_pick.options, self.ser_pick.value = {}, None
            for k, a in SER_LOOK:
                put(getattr(self, a), sr.get(k), f"series {k}")
            lims = sr.get("limits", {})
            for k, w in zip(SER_LIMS, self.ser_lims):
                if k in lims:
                    put(w, lims[k], f"series {k}", blank=True)
        self._ser_select()
        if sr.get("view"):
            put(self.ser_view, sr["view"], "series view")  # (time–height: a layer series)
        if keys:
            self.ser_status.object = (
                f'<div class="cv-status">{len(keys)} series from the session'
                + (f' · {part} not computed at every time: set the form to it and '
                   f'<b>Compute</b> for the rest' if part else "") + "</div>")
        self._update_items()

    def _put_dists(self, ds, put, skipped):
        """The Distribution form and look; returns what to compute again (or None)."""
        if ds is None:
            return None
        for k, a in DIST_FORM:
            put(getattr(self, a), ds.get("form", {}).get(k), f"distribution {k}")
        for k, a in DIST_LOOK:
            put(getattr(self, a), ds.get(k), f"distribution {k}")
        for k, a in DIST_BLANK:
            if k in ds:
                put(getattr(self, a), ds[k], f"distribution {k}", blank=True)
        items = []
        for it in ds.get("items") or []:
            t = self._time_index(it.get("time_s"))
            try:
                recipe = dist.normalize(it["recipe"])
                ok = recipe["field"] in self.F and t is not None
            except (KeyError, ValueError, TypeError):
                ok = False
            if not ok:
                skipped.append(f"distribution {(it.get('recipe') or {}).get('field')}")
                continue
            items.append((recipe, t))
        self.gen["dist"] += 1  # (one being computed stops)
        self.dists, self._dist_n = {}, 0
        self._dist_set_pick(None)
        return (items, ds.get("active")) if items else None

    def _dist_restore(self, items, active):
        """Compute the session's distributions again, in its order, in one job."""
        run, F = self.run, self.F
        centers = (ser.track_centers(self.fixes, len(run.times))
                   if any(r["region"] == "track" for r, _ in items) else {})
        jobs = [(r, t, self._field_storm(t)[0] if F[r["field"]].storm else None,
                 centers.get(t) if r["region"] == "track" else None) for r, t in items]
        self.gen["dist"] += 1
        g = self.gen["dist"]
        self.dist_go.disabled = True
        self.dist_status.object = (f'<div class="cv-status"><span class="busy">● Computing '
                                   f'{len(jobs)} distributions of the session…</span></div>')

        def job():
            out = []
            for recipe, t, storm, center in jobs:
                if g != self.gen["dist"]:
                    return
                try:
                    if pdecomp.is_pdecomp(F, recipe["field"]):
                        pdecomp.source(run, t)
                    st = dist.compute(run, F, recipe, t, storm, center)
                    res = st if st["n"] else "no values in the region (or the value limits)"
                except ValueError as e:
                    res = str(e)
                except Exception as e:  # noqa: BLE001
                    traceback.print_exc()
                    res = f"{type(e).__name__}: {e}"
                out.append((recipe, t, res))
            self._schedule(partial(apply, out))

        def apply(out):
            if g != self.gen["dist"]:
                return
            keys, bad = [], []
            for recipe, t, res in out:
                if isinstance(res, str):
                    bad.append(res)
                    continue
                key = json.dumps(recipe, sort_keys=True) + f"|{t}"  # (as _dist_request)
                self._dist_apply(g, res, recipe, t, key, None, 0.0)
                keys.append(key)
            if keys:
                self._dist_set_pick(keys[active if isinstance(active, int)
                                         and active < len(keys) else -1])
            self.dist_go.disabled = False
            self.dist_status.object = (
                f'<div class="cv-status">{len(keys)} distributions from the session'
                + (f' · {len(bad)} with no values' if bad else "") + "</div>")
        self.pools["dist"].submit(job)

    def _put_rows(self, rows, have, add, drop, keys, put):
        """As many layer rows as the session has, each set from it."""
        if rows is None:
            return
        while len(have) > len(rows):
            drop(have[-1])
        while len(have) < len(rows):
            n = len(have)
            add()
            if len(have) == n:  # (at the most there can be)
                break
        for o, r in zip(have, rows):
            for k in keys:
                if k in o and k in r:
                    put(o[k], r[k], k)

    def _put_track(self, tr):
        if not tr:
            return
        if tr.get("path"):
            self.trk_path.value = tr["path"]
        times = np.asarray(self.run.times)
        fixes = {}
        for ts, fx in tr.get("fixes") or []:
            t = int(np.argmin(np.abs(times - float(ts))))
            if abs(times[t] - float(ts)) <= 1.0:
                fixes[t] = {k: (float("nan") if v is None and k == "value" else v)
                            for k, v in fx.items()}
        if fixes or self.fixes:
            self.gen["trk"] += 1  # (a track being found stops)
            self.fixes, self.trk_spec = fixes, (tr.get("opts") if fixes else None)
            self._update_track_view()
            self._draw_points()

    def _put_view(self, view):
        """The map's view: set here, re-fitted to the window's shape in the browser
        (KEEP_ASPECT_JS keeps its centre and shows all of it)."""
        x0, x1, y0, y1 = (float(v) for v in view)
        if not (x1 > x0 and y1 > y0):
            return
        xr, yr = self.fig.x_range, self.fig.y_range
        if "fitted" not in xr.tags:  # (the page's first fit keeps this view)
            xr.tags = list(xr.tags) + ["fitted"]
        xr.update(start=x0, end=x1)
        yr.update(start=y0, end=y1)
        self.view = (x0, x1, y0, y1)
        self._views += 1
        self.fig.tags = [f"view{self._views}"]  # re-runs the fit in the browser

    def _put_tool(self, tool, panel):
        if tool is not None and TOOL_OF.get(tool, tool) not in self.mode.btns:
            tool = None  # (e.g. Track, in a run that cannot be tracked)
        if tool in ("Sounding", "Area sounding"):
            self.snd_pick.value = tool
        self.mode.set(tool)
        tab = panel.get("tab")
        if panel.get("open") and tab is not None and (tool is None or PANELS.get(tool) == tab):
            self._show_panel(True, int(tab))
            if panel.get("full"):
                self._set_full(True)
        elif not panel.get("open", True):
            self._show_panel(False)
