"""Figure editor: the panels' times (the time grid, each panel's run and time) and
titles.

A mixin of the FigureEditor (figures/editor.py)."""

import panel as pn

from . import draw as figdraw, spec as fg
from .cards import NONE, _grid


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
    """The time grid and each panel's run and time, and the titles."""

    # ------------------------------------------------------------ panels: own run & time
    def _time_opts(self, k):
        try:
            run, _ = self.open_run(self.run_rows[k]["path"])
        except Exception:  # noqa: BLE001
            return {}
        return {_tlabel(t): float(t) for t in run.times}

    def _build_pc(self, panels):
        n = int(self.rows.value or 1) * int(self.cols.value or 1)
        rows = []
        for i in range(n if self.vary.value == "custom" else 0):
            if i < len(panels):
                p = panels[i]
            elif self.pc_rows and i < len(self.pc_rows):
                p = dict(run=self.pc_rows[i]["run"].value, time_s=self.pc_rows[i]["time"].value)
            else:  # new panels: the runs in turn, at the shown time
                p = dict(run=i % max(1, len(self.run_rows)),
                         time_s=float(self.run.times[self.v.t]))
            rows.append(self._pc_row(i, p))
        self.pc_rows = rows
        self.pc_box.objects = [r["panel"] for r in rows]

    def _pc_row(self, i, p):
        names = self._run_names()
        k = int(p["run"]) if int(p["run"]) in names.values() else 0
        r = dict(run=pn.widgets.Select(name=f"Panel {figdraw.panel_letter(i, '{a}')}: run",
                                       value=k, **self._run_choices(names)))
        opts = self._time_opts(k)
        ts = p.get("time_s")
        r["time"] = pn.widgets.Select(name="time", options=opts, value=self._nearest(opts, ts))

        def on_run(ev):
            if self._hold:
                return
            if isinstance(ev.new, str):  # a run not in the figure yet
                self._pick_other(r["run"], ev.old)
                return
            o = self._time_opts(ev.new)
            cur = r["time"].value
            self._hold = True
            try:
                r["time"].options = o
                r["time"].value = self._nearest(o, cur)
            finally:
                self._hold = False
            self.request()

        r["run"].param.watch(on_run, "value")
        r["time"].param.watch(lambda e: self.request(), "value")
        r["panel"] = _grid(r["run"], r["time"], n=2)
        return r

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
        """How many times to choose: one per panel (panels in time), else none."""
        if self.kind.value not in ("plan", "xsec"):
            return 0
        r, c = int(self.rows.value or 1), int(self.cols.value or 1)
        return r * c if self.vary.value == "time" else 0

    def _time_values(self):
        """Model time (s) of each time picker (NONE: an empty panel)."""
        return [w.value for w in self.tm_rows]

    def _shown_s(self):
        return float(self.run.times[self.v.t])

    def _sel_run(self):
        """The run of "Run" (panels in time or in field)."""
        k = int(self.run_sel.value or 0)
        try:
            return self.open_run(self.run_rows[k]["path"])[0]
        except Exception:  # noqa: BLE001
            return self.run

    def _panel_times(self):
        """(model times in s, those some runs lack) the time pickers offer: the outputs
        of the panels' run."""
        return [float(t) for t in self._sel_run().times], set()

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
            name = f"Panel {figdraw.panel_letter(i, '{a}')}"
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
        hold, self._hold = self._hold, True
        try:
            self.time1.options = opts
            self.time1.value = v if v in opts.values() else next(iter(opts.values()), None)
        finally:
            self._hold = hold

    def _on_run_sel(self, ev):
        if self._hold:
            return
        if isinstance(ev.new, str):  # a run not in the figure yet
            self._pick_other(self.run_sel, ev.old)
            return
        self._build_times()  # (the new run's outputs)
        self.request()

    def _on_gg_runs(self, ev):
        """A run not in the figure picked in Fill a grid (its path): add it, keep it
        picked."""
        new = [v for v in ev.new if isinstance(v, str)]
        if self._hold or not new:
            return
        keep = [v for v in ev.new if not isinstance(v, str)]
        for p in new:
            k = self._add_run(p)
            if k is not None:
                keep.append(k)
        hold, self._hold = self._hold, True
        try:
            self.gg_runs.value = sorted(set(keep))
        finally:
            self._hold = hold

    def _fill_grid(self):
        """Panels of runs x times: the chosen runs (rows or columns) and `Times` times
        from the shown time, every `Every … outputs` outputs of the first run; each
        panel takes the nearest output of its own run."""
        ks = sorted(k for k in self.gg_runs.value if isinstance(k, int)
                    and k < len(self.run_rows)) or [0]
        runs = [self.open_run(self.run_rows[k]["path"])[0] for k in ks]
        base = [float(t) for t in runs[0].times]
        step, p0 = int(self.gg_step.value or 1), base.index(_nearest_t(base, self._shown_s()))
        times = [base[q] for q in range(p0, len(base), step)][:int(self.gg_n.value or 1)]
        by_rows = self.gg_as.value == "rows"
        nr, nc = (len(ks), len(times)) if by_rows else (len(times), len(ks))
        panels = []
        for r in range(nr):
            for c in range(nc):
                k, j = (r, c) if by_rows else (c, r)
                panels.append(dict(run=ks[k], time_s=_nearest_t(
                    [float(t) for t in runs[k].times], times[j])))
        self._hold = True
        try:
            self.vary.value = "custom"
            self.rows.value, self.cols.value = nr, nc
        finally:
            self._hold = False
        self._on_layout(panels)

    def _fill_times(self):
        """The time pickers from the shown time, every `tstep` outputs."""
        tl, _ = self._panel_times()
        if not tl:
            return
        step, p0 = int(self.tstep.value or 1), tl.index(_nearest_t(tl, self._shown_s()))
        hold, self._hold = self._hold, True
        try:
            for k, w in enumerate(self.tm_rows):
                q = p0 + step * k
                w.value = tl[q] if q < len(tl) else NONE
        finally:
            self._hold = hold
        self.request()

    def _build_titles(self, titles=None):
        """A title box per grid cell, keeping what is typed."""
        vals = [w.value for w in self.title_ws] if titles is None else list(titles)
        n = int(self.rows.value or 1) * int(self.cols.value or 1)
        ws = []
        for i in range(n):
            w = pn.widgets.TextInput(name=f"Panel {figdraw.panel_letter(i, '{a}')}",
                                     value=vals[i] if i < len(vals) else "",
                                     placeholder="no title")
            w.param.watch(lambda e: self.request(), "value")
            ws.append(w)
        self.title_ws = ws
        self.titles_box.objects = [_grid(*ws)] if ws else []

    def _set_titles(self, titles):
        hold, self._hold = self._hold, True
        try:
            for i, w in enumerate(self.title_ws):
                w.value = titles[i] if i < len(titles) else ""
        finally:
            self._hold = hold
        self.request()
