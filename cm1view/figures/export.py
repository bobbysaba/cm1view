"""Figure editor: saving (image and spec, script and data if asked), the download, and
reopening a saved figure.

A mixin of the FigureEditor (figures/editor.py)."""

import asyncio
import html as _html
import io
import json
import os
import threading
import traceback
from functools import partial

from .. import config
from ..core.run import temp_name
from . import draw as figdraw, spec as fg

PICK = "Pick a saved figure…"
NONE_SAVED = "No saved figures yet"
SERIES_RECHECK = 2.0  # seconds between looks at the series a save is waiting for
AUTOSAVE, AUTOSAVE_LAST = "figure.json", "figure_earlier.json"  # (in the cache, by run)


RASTERS = (".png", ".jpg", ".tif", ".tiff", ".gif")  # (what a thumbnail can be made from)


def saved_list(own, root, extra=""):
    """The saved figures (their _src/<name>_spec.json), as (folder, name, spec path, when
    saved): this run's folder `own` first, then the other folders in `root` (the Figures
    setting) and `extra` (the last folder of a figure of several runs); newest first in
    each.  One level of folders: no deep search."""
    dirs = [own]
    try:
        dirs += sorted(e.path for e in os.scandir(root) if e.is_dir() and e.path != own)
    except OSError:
        pass
    if extra and extra not in dirs:
        dirs.append(extra)
    out = []
    for d in dirs:
        try:
            specs = [e for e in os.scandir(os.path.join(d, "_src"))
                     if e.is_file() and e.name.endswith("_spec.json")]
        except OSError:
            continue
        specs = sorted(((e.stat().st_mtime, e) for e in specs), key=lambda x: -x[0])
        head = f"This run ({os.path.basename(d)})" if d == own else os.path.basename(d)
        out += [(head, e.name[:-len("_spec.json")], e.path, when) for when, e in specs]
    return out


def saved_figures(own, root, extra=""):
    """saved_list as Select groups {folder: {name: spec path}}."""
    out = {}
    for head, name, path, _ in saved_list(own, root, extra):
        out.setdefault(head, {})[name] = path
    return out


def saved_base(spec_path):
    """The "Save as" of a saved figure's spec: <folder>/_src/<name>_spec.json was saved
    as <folder>/<name> (a spec elsewhere: its path without _spec.json)."""
    d, name = os.path.split(spec_path)
    name = name[:-len("_spec.json")] if name.endswith("_spec.json") else \
        os.path.splitext(name)[0]
    if os.path.basename(d) == "_src":
        d = os.path.dirname(d)
    return os.path.join(d, name)


def _newest_raster(spec_path):
    """(mtime, path) of the newest image of a saved figure a thumbnail can be made from,
    or None."""
    base, found = saved_base(spec_path), []
    for ext in RASTERS:
        try:
            found.append((os.path.getmtime(base + ext), base + ext))
        except OSError:
            pass
    return max(found) if found else None


def saved_thumb(spec_path):
    """The bytes of a saved figure's thumbnail, if it has one and no image newer (a script
    may have redrawn it)."""
    path = fg.thumb_path(spec_path)
    try:
        image = _newest_raster(spec_path)
        if image and image[0] > os.path.getmtime(path):
            return None
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def make_thumb(spec_path):
    """The bytes of a thumbnail made from a saved figure's image (a figure saved before
    there were thumbnails, an animation), kept if its folder can be written to; None
    without an image that can be read."""
    from PIL import Image
    image = _newest_raster(spec_path)
    if not image:
        return None
    buf = io.BytesIO()
    try:
        with Image.open(image[1]) as im:
            im.thumbnail((fg.THUMB_PX, fg.THUMB_PX))
            im.convert("RGBA").save(buf, "png")
    except Exception:  # noqa: BLE001  (a damaged or huge image has no thumbnail)
        traceback.print_exc()
        return None
    try:
        with open(fg.thumb_path(spec_path), "wb") as f:
            f.write(buf.getvalue())
    except OSError:
        pass
    return buf.getvalue()


class FigureExport:
    # ------------------------------------------------------------ export
    def _set_dl_name(self):
        self.dl.filename = f"{os.path.basename(self.path.value) or 'figure'}.{self.fmt.value}"
        self.save_img.disabled = not self.path.value.strip()

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
                      "<b>Export</b> → “Save as”.", True)

    def config_changed(self):
        new = config.figures_dir(self.run.path)
        cur = config.expand(self.path.value.strip())
        if cur and os.path.dirname(cur) == self._fig_dir:
            self.path.value = os.path.join(new, os.path.basename(cur))
        self._fig_dir = new
        self._scan_roots()  # (the runs_root setting may have changed)
        self._refresh_saved()

    def _refresh_saved(self):
        """The File tab's list of saved figures, keeping its pick."""
        g = saved_figures(self._fig_dir, config.expand(config.get("figures_dir")),
                          config.expand(config.state("last_multi_run_dir")))
        ch = dict(options={}, groups={"": {PICK: ""}} | g) if g else \
            dict(groups=None, options={NONE_SAVED: ""})
        paths = {p for grp in g.values() for p in grp.values()}
        w, keep = self.saved_pick, self.saved_pick.value
        w.param.update(**ch)
        w.value = keep if keep in paths else ""
        w.disabled = not g

    def _figure_now(self):
        """The figure to save: what the new layout holds, while it is what shows, else the
        widgets'."""
        if self._in_shell():
            return json.loads(json.dumps(self.shell.doc, default=float))
        return self.collect_all()

    def _save(self, bundle=None):
        """Save what the Export dialog says; bundle (default: its tick): script and data
        too.  The image and the spec are always written, so it can be reopened."""
        bundle = self.save_more.value if bundle is None else bundle
        spec = self._figure_now()
        base = config.expand(self.path.value.strip())
        if not base:
            self._msg("Choose where to save the figure (<b>Export</b> → “Save as”).", True)
            return
        self.exp_dlg.hide()  # (progress is above the preview; "replace?" is a dialog too)
        out = fg.bundle_paths(spec, base)
        paths = list(out.values()) if bundle else [out["image"], out["spec"]]

        def go():
            if len(spec.get("runs") or []) > 1:
                config.set_state("last_multi_run_dir", os.path.dirname(base))
            self._msg('<span class="busy">● Saving…</span>')
            self._save_gen += 1
            self.v.pools["fig"].submit(self._save_job, spec, bundle, base, self._save_gen)
        self.v.confirm.ask(paths, go)

    def _save_job(self, spec, bundle, base=None, gen=None):
        """Save the figure as it was asked for; while its series are being computed, look
        again in a moment (the fig pool stays free for the preview, a later save replaces
        this one).  Edits made meanwhile are not in it."""
        if gen is not None and gen != self._save_gen:
            return
        if {p["kind"] for p in spec.get("panels" if fg.is_doc(spec) else "parts", [spec])} & \
                {"th", "line"}:
            self.panel_data(spec)  # (starts computing what is missing)
            wait = self.series_pending()
            if wait:
                what = f" ({_html.escape(wait[0])})" if wait[0] else ""
                self.v._schedule(partial(self._msg, '<span class="busy">● Will save when the '
                                                    f'series are done{what}…</span>'))
                timer = threading.Timer(SERIES_RECHECK, self._save_later,
                                        (spec, bundle, base, gen))
                timer.daemon = True
                timer.start()
                return
        try:
            data = self.panel_data(spec)
            base = base or config.expand(self.path.value.strip())
            if bundle:
                out = fg.save_bundle(spec, data, base, None if fg.is_doc(spec) else self.run)
            else:
                out = fg.bundle_paths(spec, base)
                out = dict(image=fg.save_image(spec, data, out["image"],
                                               thumb=fg.thumb_path(out["spec"])),
                           spec=fg.save_spec(spec, base))
            html = "Saved " + ", ".join(f"<code>{p}</code>" for p in out.values())
            self.v._schedule(partial(self._msg, html))
            self.v._schedule(self._refresh_saved)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.v._schedule(partial(self._msg, f"Could not save: {e}", True))

    def _save_later(self, spec, bundle, base, gen):
        try:
            self.v.pools["fig"].submit(self._save_job, spec, bundle, base, gen)
        except RuntimeError:  # (the viewer has closed)
            pass

    async def _download(self):
        """The image for the browser's download, drawn in the background (reading a
        large figure's data must not hold up the server)."""
        spec = self._figure_now()
        self._msg('<span class="busy">● Preparing the download…</span>')
        try:
            buf = await asyncio.wrap_future(self.v.pools["fig"].submit(self._download_job,
                                                                       spec))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._msg(f"Could not draw the download: {e}", True)
            raise
        self._msg("")
        return buf

    def _download_job(self, spec):
        data = self.panel_data(spec)
        fig = figdraw.draw(spec, data)
        buf = io.BytesIO()
        figdraw.save(spec, fig, buf, format=spec["export"]["format"], **fg.save_kw(spec))
        buf.seek(0)
        return buf

    def _with_defaults(self, spec):
        """A saved figure (or part) with what it lacks from this version's defaults."""
        return fg.with_defaults(spec, self.run, self.F, self.v.t, self._own_track())

    def _load_spec(self, path=None):
        """Open a saved figure: its _spec.json, or the image / script saved with it
        (default: the path in the File tab).  True when it opened."""
        path = config.expand((path or self.spec_path.value).strip())
        if path and not path.lower().endswith(".json"):
            path = fg.bundle_paths({}, path)["spec"]
        try:
            spec = fg.load_spec(path)
        except (OSError, ValueError) as e:
            self._msg(f"Could not load <code>{path}</code>: {e}", True)
            return False
        note = f"Loaded <code>{path}</code>" + "".join(
            f". <b>Note:</b> the namelist.input of <code>{p}</code> changed since "
            "the figure was saved, so its data may differ" for p in fg.changed_runs(spec))
        if fg.is_doc(spec):
            return self._open_doc(spec, note, saved_base(path))
        if not self._open_spec(spec, note):
            return False
        self.path.value = saved_base(path)  # (after the runs' sync of the save path)
        return True

    def _open_doc(self, doc, note, save_as=None):
        """Show a figure saved in the new layout's form, which only it can: True when shown."""
        if self.shell is None:
            self._msg("This figure was made in the new layout, which this page does not have "
                      "(it needs the CM1VIEW_FIGURE_SHELL setting).", True)
            return False
        self.quick.hide()
        self.shell.open_doc(doc, note, save_as)
        return True

    def _open_spec(self, spec, note, part=0):
        """Show a saved figure (or an applied template) in the editor, `part` of a figure
        of parts in the widgets.  True when shown."""
        parts = spec["parts"] if spec.get("kind") == "combo" else [spec]
        bases, ran = [], False
        for part in parts:
            base = self._with_defaults(part)
            bad = [lay.get("field") for lay in base["layers"]
                   if lay.get("field") and lay["field"] not in self.F]
            if bad and len(base.get("runs") or part.get("runs") or []) <= 1:
                self._msg("This run has no field " + ", ".join(bad), True)
                return False
            code = base.get("code") or {}
            if code.get("on") and str(code.get("text") or "").strip():
                base["code"] = dict(code, on=False)  # (code from a file runs once read)
                ran = True
            bases.append(base)
        self.set_parts(dict(spec, parts=bases) if spec.get("kind") == "combo" else bases[0],
                       part)
        self._msg(note + (
            ". It has code of its own (<b>Annotate → Your own code</b>): read it, then tick "
            "<b>Run the code</b>." if ran else ""))
        return True

    # ------------------------------------------------------------ session and autosave
    def own_figure(self, j=None):
        """Is the figure in the editor more than the example it starts with?  j: its
        JSON (_remember's), when already made."""
        if self.shell is not None and self.shell.edited(j):
            return True
        if self._made or self._example is None:
            return self._made
        if j is None:
            j = json.dumps(self.collect_all(), sort_keys=True, default=float)
        return j != self._example

    def figure_state(self, spec=None):
        """The figure as a session or the autosave keeps it: its settings, the part in
        the widgets and where it would be saved; with the new layout, what it holds, if that came
        from those settings ("doc", "showing"; a page without it opens "spec")."""
        state = dict(spec=self.collect_all() if spec is None else spec, part=self.part_i,
                     save_as=self.path.value)
        if self.shell is not None:
            state.update(self.shell.state_of(state["spec"]))
        return state

    def open_state(self, state, note, render=True):
        """Show a figure_state (its code stays off until ticked, as with any figure
        read from a file).  render=False: no preview until the workspace asks for one.
        The reason when it cannot be shown, else None."""
        spec = state["spec"]
        try:
            fg.check_runs(spec)
        except (KeyError, TypeError, ValueError) as e:
            return str(e)
        live = self.auto.value
        if not render:
            self.auto.value = False
        try:
            if not self._open_spec(spec, note, int(state.get("part") or 0)):
                return self.msg.object
        finally:
            self.auto.value = live
        if state.get("save_as"):
            self.path.value = state["save_as"]
        if state.get("doc") and self.shell is not None:
            try:
                fg.check_runs(state["doc"])
            except (KeyError, TypeError, ValueError) as e:
                return str(e)
            self.shell.take_state(state, render)
        return None

    def _auto_path(self, name=AUTOSAVE):
        return config.cache_dir("autosave", config.run_key(self.run.path), name)

    def _autosave(self, spec):
        """Keep the figure for the next page on this run.  This page's first write moves
        the last page's to one side, so making a new figure does not lose it."""
        path = self._auto_path()
        tmp = temp_name(path)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(self.figure_state(spec), f, default=float)
            if not self._auto_wrote and os.path.exists(path):
                os.replace(path, self._auto_path(AUTOSAVE_LAST))
            os.replace(tmp, path)
            self._auto_wrote = True
        except OSError as e:
            if not self._auto_failed:  # (once: it would be tried at every change)
                self._auto_failed = True
                self._msg(f"Could not autosave this figure: {_html.escape(str(e))}", True)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _auto_earlier(self):
        """(figure_state, when it was written) of the figure an earlier page left, or
        None."""
        path = self._auto_path(AUTOSAVE_LAST if self._auto_wrote else AUTOSAVE)
        try:
            with open(path) as f:
                state = json.load(f)
            return (state, os.path.getmtime(path)) if isinstance(state.get("spec"), dict) \
                else None
        except (OSError, ValueError, AttributeError):
            return None
