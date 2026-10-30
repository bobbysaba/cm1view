"""Differences: the map fill or the cross-section fill minus the same field at another
time and/or in another run (its Difference controls, and finding what it subtracts).

A mixin of the Viewer (cm1view/viewer/app.py): its methods use the Viewer's widgets and state."""

import os

import panel as pn

from .. import registry
from ..figures.spec import tindex

DIFF_CMAP = "RdBu_r"  # (a difference's colours: diverging, centred on 0)


class Differences:
    def _diff_widgets(self):
        """A fill's Difference controls: on, minus which run, minus which time."""
        on = pn.widgets.Checkbox(name="Difference: minus another time or run", value=False,
                                 margin=(5, 10, 8, 10))
        run = pn.widgets.Select(name="Minus run", options={"this run": ""}, value="",
                                width=210, visible=False,
                                description="The run to subtract (other runs on another "
                                            "grid are interpolated onto this one)")
        time = pn.widgets.Select(name="Minus time", options=self._minus_times(), value="",
                                 width=170, visible=False,
                                 description="The time to subtract: the shown one (another "
                                             "run's at the same time), the output before "
                                             "it, or a fixed time")
        return dict(on=on, run=run, time=time)

    def _minus_times(self):
        run = self.run
        return {"the shown time": "", "the output before": "prev"} | {
            run.time_label(k): float(t) for k, t in enumerate(run.times)}

    def _minus_runs(self):
        """{label: path} of this run, then the runs next to it and the recent ones."""
        out, here = {"this run": ""}, os.path.abspath(self.run.path)
        for p in registry.sibling_runs(self.run.path) + registry.recent_runs():
            p = os.path.abspath(p)
            if p != here and p not in out.values():
                lab = "/".join(p.rstrip("/").split("/")[-2:])
                out[lab if lab not in out else p] = p
        return out

    def _wire_diff(self, w, cmap, rev, auto, field, request, hold):
        """Difference on: the run and time lists, a diverging colormap on an automatic
        range (symmetric about 0); off: the field's own colours.  field(): the fill's
        field; hold: the Viewer attribute that holds back its redraws."""

        def toggle(ev):
            w["run"].visible = w["time"].visible = ev.new
            if ev.new and len(w["run"].options) == 1:
                w["run"].options = self._minus_runs()
            setattr(self, hold, True)
            try:
                cmap.value = DIFF_CMAP if ev.new else self.F[field()].cmap
                rev.value, auto.value = False, True
            finally:
                setattr(self, hold, False)
            request()

        w["on"].param.watch(toggle, "value")
        for k in ("run", "time"):
            w[k].param.watch(lambda e: request() if w["on"].value else None, "value")

    @staticmethod
    def _minus_spec(w):
        """What a fill's Difference subtracts, from its controls: None (no difference)
        or {path: "" for this run, time: "" the shown time, "prev" or a time in s}."""
        if not w["on"].value:
            return None
        return dict(path=w["run"].value or "", time=w["time"].value)

    def _minus_ref(self, m, t):
        """{F, t, label} of a _minus_spec m at the shown time index t: the other run's
        Fields and output index (an error when it has no output then).  Opens the other
        run (off the page thread)."""
        if m["path"]:
            run, F = self.figed.open_run(m["path"])
        else:
            run, F = self.run, self.F
        ts = float(self.run.times[t])
        where = "" if run is self.run else f" of {run.name}"
        if m["time"] == "prev":
            k = tindex(run, ts)
            if k is None or k == 0:
                raise ValueError(f"difference: {run.name} has no output before "
                                 f"{self.run.time_label(t)}")
            k -= 1
        else:
            want = ts if m["time"] == "" else float(m["time"])
            k = tindex(run, want)
            if k is None:
                s = int(round(want))
                raise ValueError(f"difference: {run.name} has no output at "
                                 f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}")
        return dict(F=F, t=k, label=f"{run.time_label(k)}{where}")

    @staticmethod
    def _minus_note(m):
        """The title's note on a difference ('' without one)."""
        return f' <span>minus {m["label"]}</span>' if m else ""
