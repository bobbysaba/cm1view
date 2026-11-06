"""Switching to another member of the same run (or to their mean) without reloading the
page.  Members of one WoFS experiment share their grid, times and fields, so the widgets
built from the run stay right: the Viewer takes the new Run and Fields, resets what it
derived from the old one and puts what it showed back with apply_session (the page's
own route for a session).  Runs that differ in any of that are opened by reloading the
page, as before."""

import os

import numpy as np

from .. import config
from ..core import parcels as P
from ..figures.runs import AllFields


def same_grid(a, Fa, b, Fb):
    """Do runs a and b (with their Fields) fit the same widgets: grid, heights, times,
    terrain, motion, fields, map and parcels?"""
    try:
        if (a.model, a.ni, a.nj, a.nk, a.dx, a.dy, a.terrain, a.umove, a.vmove) != \
                (b.model, b.ni, b.nj, b.nk, b.dx, b.dy, b.terrain, b.umove, b.vmove):
            return False
        if getattr(a, "storm_relative", True) != getattr(b, "storm_relative", True):
            return False
        for k in ("xh", "yh", "z", "zf", "times"):
            if not np.array_equal(np.asarray(getattr(a, k)), np.asarray(getattr(b, k))):
                return False
        if list(Fa.defs) != list(Fb.defs):
            return False
        return (getattr(a, "geo", None) is None) == (getattr(b, "geo", None) is None)
    except (AttributeError, TypeError, ValueError):
        return False


class RunSwap:
    _3d_stale = False  # the 3D scene is of the run shown before (redrawn when opened)

    def _build_swap(self):
        import panel as pn
        # the address follows the run shown (a reload stays on it)
        self.url_run = pn.widgets.TextInput(visible=False)
        self.url_run.jscallback(value="""
            const p = (cb_obj.value || '').trim();
            if (!p) return;
            const q = new URLSearchParams(window.location.search);
            q.set('run', p); q.delete('session'); q.delete('t');
            window.history.replaceState(null, '', '?' + q.toString());
        """)

    def swap_run(self, path, state=None):
        """Show the run in `path` in place of this one, keeping the view (state: what to
        put back, default what the viewer shows now).  False: it does not fit this
        page's widgets (or did not open), nothing changed."""
        if self.reg is None:
            return False
        try:
            run, F = self.reg.get(path)
        except Exception:  # noqa: BLE001  (the reload says why)
            return False
        if run is self.run:
            return True
        pf = P.for_run(run, F)
        if not same_grid(self.run, self.F, run, F) or (pf is None) != (self.pf is None) or \
                (pf is not None and list(pf.vars) != list(self.pf.vars)):
            return False
        s = self.session_state() if state is None else state
        old = self.run
        for k in self.gen:  # (jobs of the run before stop)
            self.gen[k] += 1
        self.run, self.F = run, F
        self._reset_derived(pf)
        self._refresh_run_labels()
        self._swap_figure(run, F)  # (before the paths: the figure's folder moves too)
        self._follow_run_paths(old)
        self.apply_session(s)
        if self.box is not None and self.workspace.value != "3D":
            self._3d_stale = True
        self.url_run.value = ""
        self.url_run.value = run.path
        return True

    def _reset_derived(self, pf):
        """What was worked out from the run before: parcels, track, 3D scene."""
        self.pf = pf
        self.psets.clear()
        self._par_key = self._par_xs_key = self._par_3d_key = self._pp_key = None
        self._par_busy = None
        self._par_saved_options()
        self.fixes, self.trk_spec = {}, None
        self._track_found = ()
        self._s3, self._st_cache = None, {}
        self.results = []
        for w in (self.fill_diff, self.xs_diff):  # (this run is no longer "another")
            if len(w["run"].options) > 1:
                cur = w["run"].value
                w["run"].options = self._minus_runs()
                if cur == self.run.path:
                    w["run"].value = ""

    def _refresh_run_labels(self):
        self._run_info.object = self._run_info_html()
        self._update_cache_html()
        self.settings.run_path = self.run.path
        with_hold = getattr(self, "_part_hold", False)
        self._part_hold = True
        try:
            if self.part_sel.value != self.run.path:
                self.part_sel.value = self.run.path
        finally:
            self._part_hold = with_hold

    def _follow_run_paths(self, old):
        """Save boxes still on the run before's default folders move to this run's."""
        if config.expand(self.ses_path.value) == os.path.join(
                config.exports_dir(old.path, "sessions"), "session.json"):
            self.ses_path.value = self._ses_default()
        self._config_changed()

    def _swap_figure(self, run, F):
        """The figure editor's own run follows the viewer (the document is kept: a run
        it names is drawn as before)."""
        ed = self.figed
        was = ed.fields
        ed.run, ed.F = run, F
        ed.fields = AllFields([F])
        d = ed.data
        d.run, d.F = run, F
        for c in (d.cache, d.snd_cache, d.dist_cache, d.scene_cache):
            c.clear()  # (the viewer's track may be another now)
        d.st_cache = {}
        if ed.shell is not None and ed.shell.fields is was:
            ed.shell.fields = ed.fields
        if hasattr(ed, "_find_runs"):
            ed._find_runs()
