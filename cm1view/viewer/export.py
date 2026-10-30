"""The Export data dialog: fields of a box, some times, on the model levels or at
heights, written to netCDF (core/export.py) in the background, with progress and Stop.

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import time as _time
import traceback
from functools import partial

import panel as pn

from .. import config
from ..core import export as ex
from ..core.fields import COSTLY, DERIVS, column_stride, deriv_name, split_deriv
from ..theme import DIALOG_DARK
from .ui import _html

REGIONS = {"Whole domain": "domain", "Map view": "view", "Box": "box"}
VERTICAL = {"Model levels": "levels", "Heights": "heights"}


class DataExport:
    _exp_built = False

    def _build_export(self):
        """The button and an empty dialog; its widgets are made when it first opens."""
        self.exp_body = pn.Column(margin=0, sizing_mode="stretch_width")
        self.exp_modal = pn.Modal(
            _html('<div class="cv-maptitle" style="font-size:16px"><b>Export data</b></div>'
                  '<div class="cv-hint">Fields of a box and some times to a netCDF file, '
                  'on the model levels or at heights (the values the map shows).  The '
                  'file is written one time after another; Stop keeps the times done.  '
                  'Without the viewer: <code>cm1view export -h</code>.</div>'),
            self.exp_body, width=640, margin=10, stylesheets=[DIALOG_DARK])
        self.exp_btn = pn.widgets.Button(
            name="", icon="database-export", button_type="light", button_style="outline",
            width=40, height=32, margin=(4, 2),
            description="Export data: fields of a box and some times to netCDF")
        self.exp_btn.on_click(self._open_export)

    def _open_export(self, ev=None):
        if not self._exp_built:
            self._exp_widgets()
        if not self.exp_go.disabled:  # (not while one is being written)
            self.exp_fields.value = list(dict.fromkeys(self.exp_fields.value
                                                       or [self._fill_name()]))
            self._exp_times_here()
            self._exp_update()
        self.exp_modal.show()

    def _exp_widgets(self):
        self._exp_built = True
        run, F = self.run, self.F
        opts = {f"{d.label} [{n}]": n for n, d in F.defs.items()}
        fill = self._fill_name()
        if fill not in opts.values():
            opts[f"{F[fill].label} [{fill}]"] = fill
        self.exp_fields = pn.widgets.MultiChoice(
            name="Fields", options=opts, value=[fill], width=600, search_option_limit=60,
            description="Any fields of the lists (derived ones and column fields too); "
                        "a derivative: add it below")
        self.exp_dop = pn.widgets.Select(name="Derivative", width=90,
                                         options={v: k for k, v in DERIVS.items()})
        self.exp_dvar = pn.widgets.Select(name="of", groups=F.groups(), width=300,
                                          value=split_deriv(fill)[1])
        self.exp_dadd = pn.widgets.Button(name="Add", icon="plus", width=80,
                                          margin=(24, 4, 5, 4))
        labels = {f"{run.time_label(t)} ({run.times[t] / 60:g} min)": t
                  for t in range(len(run.times))}
        self.exp_t0 = pn.widgets.Select(name="From", options=labels, width=170)
        self.exp_t1 = pn.widgets.Select(name="To", options=labels, width=170)
        self.exp_every = pn.widgets.IntInput(name="Every n-th output", value=1, start=1,
                                             width=120)
        self.exp_now = pn.widgets.Button(name="This time", width=90, margin=(24, 4, 5, 4))
        self.exp_all = pn.widgets.Button(name="All", width=60, margin=(24, 4, 5, 4))
        self.exp_region = pn.widgets.RadioButtonGroup(options=list(REGIONS),
                                                      value="Map view", margin=(4, 4))
        self.exp_box = [pn.widgets.FloatInput(name=n, width=95, visible=False)
                        for n in ("x0 (km)", "x1 (km)", "y0 (km)", "y1 (km)")]
        self.exp_vert = pn.widgets.RadioButtonGroup(options=list(VERTICAL),
                                                    value="Model levels", margin=(4, 4))
        self.exp_ztop = pn.widgets.FloatInput(
            name="Up to (km, 0: the top)", value=0.0, start=0.0, width=150,
            description="Model levels up to this height")
        self.exp_heights = pn.widgets.TextInput(
            name="Heights (km AGL)", value="0.5, 1, 2, 3, 5", width=300, visible=False,
            description="Comma-separated; each as the map shows the field there")
        self.exp_zip = pn.widgets.Checkbox(name="Compress (zlib)", value=True,
                                           margin=(12, 8))
        self.exp_path = pn.widgets.TextInput(name="File", width=600)
        self._exp_auto = ""
        self.exp_go = pn.widgets.Button(name="Export", icon="database-export",
                                        button_type="primary", width=110, margin=(5, 4))
        self.exp_stop = pn.widgets.Button(name="Stop", icon="player-stop", width=90,
                                          disabled=True, margin=(5, 4))
        self.exp_size, self.exp_msg = _html(), _html()
        self.exp_body.objects = [
            self.exp_fields,
            pn.Row(self.exp_dop, self.exp_dvar, self.exp_dadd, margin=0),
            pn.Row(self.exp_t0, self.exp_t1, self.exp_every, self.exp_now, self.exp_all,
                   margin=0),
            pn.Row(_html('<div class="cv-hint" style="width:60px">Region</div>'),
                   self.exp_region, margin=0),
            pn.Row(*self.exp_box, margin=0),
            pn.Row(_html('<div class="cv-hint" style="width:60px">Vertical</div>'),
                   self.exp_vert, margin=0),
            pn.Row(self.exp_ztop, self.exp_heights, self.exp_zip, margin=0),
            self.exp_path, self.exp_size,
            pn.Row(self.exp_go, self.exp_stop, margin=0), self.exp_msg]

        def region(e):
            box = e.new == "Box"
            for w in self.exp_box:
                w.visible = box
            if box and e.old != "Box":  # (starting from the map view)
                for w, v in zip(self.exp_box, self.view):
                    w.value = round(float(v), 2)
            self._exp_update()

        def vert(e):
            self.exp_ztop.visible = e.new == "Model levels"
            self.exp_heights.visible = not self.exp_ztop.visible
            self._exp_update()

        self.exp_region.param.watch(region, "value")
        self.exp_vert.param.watch(vert, "value")
        for w in (self.exp_fields, self.exp_t0, self.exp_t1, self.exp_every, self.exp_ztop,
                  self.exp_heights, *self.exp_box):
            w.param.watch(lambda e: self._exp_update(), "value")
        self.exp_dadd.on_click(self._exp_add_deriv)
        self.exp_now.on_click(lambda e: (self._exp_times_here(), self._exp_update()))
        self.exp_all.on_click(lambda e: self._exp_times_all())
        self.exp_go.on_click(self._on_export)
        self.exp_stop.on_click(lambda e: self._cancel_export())

    def _exp_times_here(self):
        self.exp_t0.value = self.exp_t1.value = self.t

    def _exp_times_all(self):
        self.exp_t0.value, self.exp_t1.value = 0, len(self.run.times) - 1

    def _exp_add_deriv(self, ev):
        name = deriv_name(self.exp_dop.value, self.exp_dvar.value)
        if name not in self.F:  # (∂/∂z of a 2D field)
            self._exp_note(f"{DERIVS[self.exp_dop.value]} of a 2D field: there is none",
                           error=True)
            return
        if name not in self.exp_fields.options.values():
            self.exp_fields.options = dict(self.exp_fields.options,
                                           **{f"{self.F[name].label} [{name}]": name})
        if name not in self.exp_fields.value:
            self.exp_fields.value = self.exp_fields.value + [name]

    def _exp_note(self, html, error=False):
        color = ' style="color:#f87171"' if error else ""
        self.exp_msg.object = f'<div class="cv-status"{color}>{html}</div>'

    def _exp_plan(self):
        """(plan, None) of the dialog's choices, or (None, why not)."""
        a, b = sorted((int(self.exp_t0.value), int(self.exp_t1.value)))
        times = range(a, b + 1, max(1, int(self.exp_every.value or 1)))
        how = REGIONS[self.exp_region.value]
        box = None if how == "domain" else (
            self.view if how == "view" else [w.value for w in self.exp_box])
        heights = None
        try:
            if box is not None and any(v is None for v in box):
                raise ValueError("the box needs x0, x1, y0 and y1")
            if self.exp_vert.value == "Heights":
                heights = ex._floats(self.exp_heights.value, what="Heights")
            return ex.plan(self.run, self.F, self.exp_fields.value, times, box, heights,
                           self.exp_ztop.value), None
        except ValueError as e:
            return None, str(e)

    def _exp_update(self):
        p, why = self._exp_plan()
        if p is None:
            self.exp_size.object = f'<div class="cv-hint" style="color:#f87171">{why}</div>'
            return
        run, F = self.run, self.F
        i0, i1, j0, j1 = p["box"]
        vert = (f"{p['nz']} model level{'s' * (p['nz'] > 1)} (to "
                f"{run.z[p['ks'][-1]]:.2f} km)" if p["heights"] is None
                else f"{p['nz']} height{'s' * (p['nz'] > 1)}")
        notes = []
        if any(F[n].storm for n in p["names"]):
            notes.append("storm-relative fields: the tracked storm motion where the track "
                         "has a fix, else umove, vmove (as the map)")
        s = column_stride(run)
        if s > 1 and any(split_deriv(n)[1] in COSTLY for n in p["names"]):
            notes.append(f"parcel fields on every {s}th column (the column_stride setting)")
        self.exp_size.object = (
            f'<div class="cv-hint">{len(p["names"])} field{"s" * (len(p["names"]) > 1)} · '
            f'{len(p["times"])} time{"s" * (len(p["times"]) > 1)} · {i1 - i0}×{j1 - j0} '
            f'columns · {vert} · ~{ex.size_text(p["bytes"])} before compression'
            + "".join(f"<br>{n}" for n in notes) + "</div>")
        auto = ex.default_path(run, p)  # (followed until the file is edited)
        if self.exp_path.value in ("", self._exp_auto):
            self.exp_path.value = auto
        self._exp_auto = auto

    def _on_export(self, ev):
        p, why = self._exp_plan()
        if p is None:
            self._exp_note(why, error=True)
            return
        path = config.expand(self.exp_path.value.strip()) or ex.default_path(self.run, p)
        if not path.endswith((".nc", ".nc4")):
            path += ".nc"
        self.confirm.ask([path], lambda: self._start_export(p, path))

    def _start_export(self, p, path):
        storm = None
        if any(self.F[n].storm for n in p["names"]):
            m = {t: self._field_storm(t)[0] for t in p["times"]}
            storm = m.__getitem__
        self.gen["exp"] += 1
        g = self.gen["exp"]
        self.exp_go.disabled, self.exp_stop.disabled = True, False
        self._exp_note(f'<span class="busy">● Writing {len(p["times"])} time(s)…</span>')
        self.pools["exp"].submit(self._exp_job, g, p, path, storm, self.exp_zip.value)

    def _exp_job(self, g, p, path, storm, compress):
        t0, last = _time.time(), [0.0]

        def cancelled():
            return g != self.gen["exp"]

        def progress(done, total, what):
            if _time.time() - last[0] < 1.0 and done < total:
                return
            last[0] = _time.time()
            self._schedule(partial(self._exp_progress, g, done, total, what, t0))

        try:
            r = ex.write(self.run, self.F, path, p, storm, compress, progress, cancelled)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._schedule(partial(self._exp_finish, g, f"Export error: {e}", True, force=True))
            return
        msg = (f"Saved <code>{r['path']}</code> · {r['times']} of {len(p['times'])} "
               f"times · {_time.time() - t0:.0f} s")
        if r["cancelled"]:
            msg += " · stopped (the file keeps the times done)"
        for n, ts in r["missing"].items():
            msg += f" · {n} not in the output at {len(ts)} time(s) (NaN)"
        self._schedule(partial(self._exp_finish, g, msg, False, force=True))

    def _exp_progress(self, g, done, total, what, t0):
        if g == self.gen["exp"]:
            self._exp_note(f'<span class="busy">● Writing… {done}/{total} · {what} · '
                           f'{_time.time() - t0:.0f} s</span>')

    def _exp_finish(self, g, msg, error, force=False):
        if g != self.gen["exp"] and not force:
            return
        self._exp_note(msg, error)
        self.exp_go.disabled, self.exp_stop.disabled = False, True

    def _cancel_export(self):
        self.gen["exp"] += 1  # (the job stops after the field it is on)
        self.exp_stop.disabled = True
        self._exp_note('<span class="busy">● Stopping after this field…</span>')
