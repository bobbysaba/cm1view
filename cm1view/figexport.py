"""Figure editor: saving (image, script and data), the download, and reopening a
saved figure.

A mixin of the FigureEditor (cm1view/figui.py)."""

import io
import os
import traceback
from functools import partial

from . import config, figdraw, figure as fg


class FigureExport:
    # ------------------------------------------------------------ export
    def _set_dl_name(self):
        self.dl.filename = f"{os.path.basename(self.path.value) or 'figure'}.{self.fmt.value}"
        for b in (self.save_img, self.save_all):
            b.disabled = not self.path.value.strip()

    def _sync_save_path(self):
        """One run: <figures_dir>/<parent>_<run>/.  Several runs have no folder of their
        own: the last folder used for one, else the user must choose."""
        multi = len(self.run_rows) > 1
        if multi == getattr(self, "_multi", False):
            return
        self._multi = multi
        cur = config.expand(self.path.value.strip())
        name = os.path.basename(cur) or "figure"
        if multi and (not cur or os.path.dirname(cur) == self._fig_dir):
            last = config.state("last_multi_run_dir")
            self.path.value = os.path.join(last, name) if last else ""
        elif not multi and (not cur or os.path.dirname(cur) == config.expand(
                config.state("last_multi_run_dir"))):
            self.path.value = os.path.join(self._fig_dir, name)
        self.path.placeholder = ("Several runs: choose a folder and name, e.g. "
                                 "~/figures/tor_vs_ntor/refl" if multi else "")
        if multi and not self.path.value:
            self._msg("This figure shows several runs: choose a folder for it in "
                      "“Save as”.", True)

    def config_changed(self):
        new = config.figures_dir(self.run.path)
        cur = config.expand(self.path.value.strip())
        if cur and os.path.dirname(cur) == self._fig_dir:
            self.path.value = os.path.join(new, os.path.basename(cur))
        self._fig_dir = new

    def _save(self, bundle):
        spec = self.collect()
        base = config.expand(self.path.value.strip())
        if not base:
            self._msg("Choose where to save the figure (“Save as”).", True)
            return
        fmt = spec["export"]["format"]
        if bundle:
            paths = list(fg.bundle_paths(spec, base).values())
        else:
            base = os.path.splitext(base)[0] if base.lower().endswith("." + fmt) else base
            paths = [f"{base}.{fmt}"]

        def go():
            if len(spec.get("runs") or []) > 1:
                config.set_state("last_multi_run_dir", os.path.dirname(base))
            self._msg('<span class="busy">● Saving…</span>')
            self.v.pools["fig"].submit(self._save_job, spec, bundle, base)
        self.v.confirm.ask(paths, go)

    def _save_job(self, spec, bundle, base=None):
        if spec["kind"] in ("th", "line"):
            self.panel_data(spec)  # (starts computing what is missing)
            if self.series_pending():
                self.v._schedule(partial(self._msg, "The series are still being computed "
                                                    "(see the preview's status line): save "
                                                    "when they are done.", True))
                return
        try:
            data = self.panel_data(spec)
            base = base or config.expand(self.path.value.strip())
            fmt = spec["export"]["format"]
            if not bundle and base.lower().endswith("." + fmt):
                base = os.path.splitext(base)[0]
            if bundle:
                out = fg.save_bundle(spec, data, base, self.run)
                html = "Saved " + ", ".join(f"<code>{p}</code>" for p in out.values())
            else:
                p = fg.save_image(spec, data, f"{base}.{spec['export']['format']}")
                html = f"Saved <code>{p}</code>"
            self.v._schedule(partial(self._msg, html))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.v._schedule(partial(self._msg, f"Could not save: {e}", True))

    def _download(self):
        spec = self.collect()
        data = self.panel_data(spec)
        fig = figdraw.draw(spec, data)
        buf = io.BytesIO()
        figdraw.save(spec, fig, buf, format=spec["export"]["format"], **fg.save_kw(spec))
        buf.seek(0)
        return buf

    def _load_spec(self):
        """Open a saved figure: its _spec.json, or the image / script saved with it."""
        path = config.expand(self.spec_path.value.strip())
        if path and not path.lower().endswith(".json"):
            path = fg.bundle_paths({}, path)["spec"]
        try:
            spec = fg.load_spec(path)
        except (OSError, ValueError) as e:
            self._msg(f"Could not load <code>{path}</code>: {e}", True)
            return
        base = fg.default_spec(self.run, self.F, self.v.t)
        for k, val in spec.items():  # keys added in later versions keep their defaults
            base[k] = dict(base[k], **val) if isinstance(base.get(k), dict) else val
        bad = [lay.get("field") for lay in base["layers"]
               if lay.get("field") and lay["field"] not in self.F]
        if bad and len(base.get("runs") or spec.get("runs") or []) <= 1:
            self._msg("This run has no field " + ", ".join(bad), True)
            return
        if "runs" not in spec:  # a figure of one run: this viewer's run
            base["runs"] = [fg.run_entry(self.run, self._own_track())]
        nt = len(self.run.times)
        if "times_s" not in spec:
            base["times"] = [t for t in base["times"] if t is None or t < nt]
            base["time"] = min(int(base["time"]), nt - 1)
            base.pop("times_s"), base.pop("time_s")
        self.set_spec(base)
        self._msg(f"Loaded <code>{path}</code>")
