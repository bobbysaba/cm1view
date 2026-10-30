"""Figure editor: the panels' times (a picker per panel, row or column of times), the
runs of a grid of runs, and the titles.

A mixin of the FigureEditor (figures/editor.py)."""

import panel as pn

from . import draw as figdraw, spec as fg
from .cards import NONE, _grid
from ..viewer.ui import held


def _tlabel(t_s):
    """A time picker's label of model time t_s (s): h:mm:ss  (minutes)."""
    s = int(round(float(t_s)))
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}  ({float(t_s) / 60:g} min)"


def _heights(text):
    """'1, 3, 6' -> [1.0, 3.0, 6.0] (km); also start:stop:step."""
    return figdraw._levels_list(text)


def _match(times, t_s):
    """The time of `times` within a second of t_s, or None."""
    return next((t for t in times if abs(t - float(t_s)) <= 1.0), None)


def _nearest_t(times, t_s):
    return min(times, key=lambda t: abs(t - float(t_s))) if times else float(t_s)


def _place(times, t_s, snap):
    """A chosen time in a picker of `times`: the nearest of them (snap), else the
    matching one, else itself."""
    if snap:
        return _nearest_t(times, t_s)
    m = _match(times, t_s)
    return float(t_s) if m is None else m


class FigureTimes:
    """The panels' times, a grid's runs, and the titles."""

    # ------------------------------------------------------------ runs and times
    def _time_opts(self, k):
        try:
            run, _ = self.open_run(self.run_rows[k]["path"])
        except Exception:  # noqa: BLE001
            return {}
        return {_tlabel(t): float(t) for t in run.times}

    @staticmethod
    def _nearest(opts, ts):
        vals = list(opts.values())
        if not vals:
            return None
        if ts is None:
            return vals[0]
        return min(vals, key=lambda v: abs(v - float(ts)))

    # ------------------------------------------------------------ panel times and titles
    def _slots(self):
        """How many times to choose: one per row, column or panel of times."""
        return self._dim_count("times")

    def _time_values(self):
        """Model time (s) of each time picker (NONE: an empty panel)."""
        return [w.value for w in self.tm_rows]

    def _shown_s(self):
        return float(self.run.times[self.v.t])

    def _sel_run(self):
        """The run of "Run" (every panel's), or the first of a grid of runs."""
        k = self._grid_runs()[0] if self._uses("runs") else int(self.run_sel.value or 0)
        try:
            return self.open_run(self.run_rows[k]["path"])[0]
        except Exception:  # noqa: BLE001
            return self.run

    def _panel_times(self):
        """(model times in s, those some runs lack) the time pickers offer: the outputs
        of the panels' run (a grid of runs: of its first run, marked where another of
        its runs has no output)."""
        tl = [float(t) for t in self._sel_run().times]
        if not self._uses("runs"):
            return tl, set()
        others = []
        for k in self._grid_runs()[1:]:
            try:
                others.append([float(t) for t in self.open_run(self.run_rows[k]["path"])[0].times])
            except Exception:  # noqa: BLE001
                continue
        return tl, {t for t in tl if any(_match(o, t) is None for o in others)}

    def _topts(self, values=()):
        """Time picker options: the outputs, plus any chosen time that has none (a
        figure opened from another run keeps its times; the panel says it has no
        output there)."""
        tl, some = self._panel_times()
        opts = {_tlabel(t) + (" · not in every run" if t in some else ""): t for t in tl}
        for v in values:
            if v not in (None, NONE) and _match(tl, v) is None:
                opts[_tlabel(v) + " · no output"] = float(v)
        return opts

    def _index_of(self, ts, one=False):
        """Output index of time ts (s) in the panels' run, for older readers of the
        spec."""
        runs = [self._sel_run()]
        for run in runs:
            k = fg.tindex(run, ts)
            if k is not None:
                return k
        ts0 = runs[0].times
        return min(range(len(ts0)), key=lambda k: abs(ts0[k] - ts))

    def _build_times(self, values=None, extend=True, snap=True):
        """A time picker per panel, keeping the chosen times (snap: moved to the nearest
        output the pickers offer).  Pickers added continue every `tstep` outputs
        (extend), or start empty."""
        vals = list(self._time_values() if values is None else values)
        tl, _ = self._panel_times()
        step = int(self.tstep.value or 1)
        if snap:  # different times stay different (e.g. moving to a coarser run)
            taken, out = set(), []
            for v in vals:
                if v in (None, NONE):
                    out.append(NONE)
                    continue
                free = [t for t in tl if t not in taken] or tl
                out.append(_nearest_t(free, v))
                taken.add(out[-1])
            vals = out
        else:
            vals = [NONE if v in (None, NONE) else _place(tl, v, False) for v in vals]
        n = self._slots()
        while len(vals) < n:
            last = next((v for v in reversed(vals) if v != NONE), None)
            if not extend or not tl:
                vals.append(NONE)
                continue
            if last is None:
                vals.append(_nearest_t(tl, self._shown_s()))
                continue
            q = tl.index(_nearest_t(tl, last)) + step
            vals.append(tl[q] if q < len(tl) else NONE)
        opts = {"— empty —": NONE} | self._topts(vals)
        rows = []
        for i in range(n):
            name = self._step_name("times", i)
            v = vals[i] if vals[i] in opts.values() else NONE
            w = pn.widgets.Select(name=name, options=opts, value=v)
            w.param.watch(lambda e: self.request(), "value")
            rows.append(w)
        self.tm_rows = rows
        self.tm_box.objects = [_grid(*rows)] if rows else []
        self._refresh_time1(snap=snap)

    def _refresh_time1(self, value=None, snap=True):
        """The one time of a figure in fields: the outputs of the panels' run."""
        v = self.time1.value if value is None else value
        tl, _ = self._panel_times()
        if v is not None and tl:
            v = _place(tl, v, snap)
        opts = self._topts([v])
        with held(self):
            self.time1.options = opts
            self.time1.value = v if v in opts.values() else next(iter(opts.values()), None)

    def _on_run_sel(self, ev):
        if self._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self._pick_other(self.run_sel, ev.old)
            return
        self._build_times()  # (the new run's outputs)
        self.request()

    def _grid_runs(self):
        """The runs of a grid of runs, in the order picked (none: every run)."""
        n = len(self.run_rows)
        return [k for k in self.gg_runs.value if isinstance(k, int) and k < n] or \
            list(range(max(1, n)))

    def _on_gg_runs(self, ev):
        """The runs of a grid of runs changed (a run not in the figure picked, its
        path: added to the figure, and kept in its place)."""
        if self._hold:
            return
        new = [v for v in ev.new if isinstance(v, str)]
        if new:
            keep = []
            for v in ev.new:
                k = self._add_run(v) if isinstance(v, str) else v
                if k is not None and k not in keep:
                    keep.append(k)
            with held(self):
                self.gg_runs.value = keep
        self._on_layout()

    def _fill_times(self):
        """The time pickers from the shown time, every `tstep` outputs."""
        tl, _ = self._panel_times()
        if not tl:
            return
        step, p0 = int(self.tstep.value or 1), tl.index(_nearest_t(tl, self._shown_s()))
        with held(self):
            for k, w in enumerate(self.tm_rows):
                q = p0 + step * k
                w.value = tl[q] if q < len(tl) else NONE
        self.request()

    def _build_titles(self, titles=None, row_titles=None):
        """A title box per grid cell, and in a grid of rows and columns (runs ×
        sections, ...) a label box per row, keeping what is typed."""
        vals = [w.value for w in self.title_ws] if titles is None else list(titles)
        rvals = [w.value for w in self.row_ws] if row_titles is None else list(row_titles)
        r, c = int(self.rows.value or 1), int(self.cols.value or 1)
        ws = []
        for i in range(r * c):
            w = pn.widgets.TextInput(name=f"Panel {figdraw.panel_letter(i, '{a}')}",
                                     value=vals[i] if i < len(vals) else "",
                                     placeholder="no title")
            w.param.watch(lambda e: self.request(), "value")
            ws.append(w)
        rws = []
        if "none" not in self._axes():
            for k in range(r):
                w = pn.widgets.TextInput(name=f"Row {k + 1} label (left)",
                                         value=rvals[k] if k < len(rvals) else "",
                                         placeholder="no label")
                w.param.watch(lambda e: self.request(), "value")
                rws.append(w)
        self.title_ws, self.row_ws = ws, rws
        self.titles_box.objects = [_grid(*ws)] * bool(ws) + [_grid(*rws)] * bool(rws)

    def _set_titles(self, titles, row_titles=()):
        with held(self):
            for i, w in enumerate(self.title_ws):
                w.value = titles[i] if i < len(titles) else ""
            for k, w in enumerate(self.row_ws):
                w.value = row_titles[k] if k < len(row_titles) else ""
        self.request()
