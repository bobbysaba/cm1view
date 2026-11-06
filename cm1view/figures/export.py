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
    _save_gen = 0  # (a save waiting for series goes on only if still the last)

    # ------------------------------------------------------------ export
    def config_changed(self):
        new = config.figures_dir(self.run.path)
        cur = config.expand(self.path.value.strip())
        if cur and os.path.dirname(cur) == self._fig_dir:
            self.path.value = os.path.join(new, os.path.basename(cur))
        self._fig_dir = new
        self._scan_roots()  # (the runs_root setting may have changed)

    def _figure_now(self):
        """The figure to save: a copy of the document, a run on the viewer's track naming the
        viewer's storm (drawn later without the viewer, it is that storm of its track file)."""
        doc = json.loads(json.dumps(self.shell.doc, default=float))
        for r in doc.get("runs") or []:
            if r.get("track") == "viewer" and os.path.abspath(r.get("path", "")) == self.run.path:
                r.pop("storm", None)
                if self._viewer_storm():
                    r["storm"] = self._viewer_storm()
        return doc

    def _save(self, bundle=None):
        """Save what the Export dialog says; bundle (default: its tick): script and data
        too.  The image and the spec are always written, so it can be reopened."""
        bundle = self.save_more.value if bundle is None else bundle
        spec = self._figure_now()
        base = config.expand(self.path.value.strip())
        if not base:
            self._msg("Choose where to save the figure (<b>Export</b> → “Save as”).", True)
            return
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

    def _load_spec(self, path):
        """Open a saved figure: its _spec.json, or the image / script saved with it.  True when
        it opened."""
        path = config.expand((path or "").strip())
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
            self.quick.hide()
            self.shell.open_doc(spec, note, saved_base(path))
            return True
        return self._open_spec(spec, note, saved_base(path))

    def _open_spec(self, spec, note, save_as=None, render=True):
        """Show a figure saved in the older form (or an applied template of it).  True when
        shown."""
        for one in spec["parts"] if spec.get("kind") == "combo" else [spec]:
            bad = [lay.get("field") for lay in one.get("layers") or []
                   if lay.get("field") and lay["field"] not in self.F]
            if bad and len(one.get("runs") or []) <= 1:
                self._msg("This run has no field " + ", ".join(bad), True)
                return False
        self.quick.hide()
        self.shell.open_spec(spec, note, save_as, render)
        return True

    # ------------------------------------------------------------ session and autosave
    def own_figure(self):
        """Is the figure more than the example the page starts with?"""
        return self.shell.own_figure()

    def figure_state(self):
        """The figure as a session or the autosave keeps it: the document and where it would be
        saved."""
        return self.shell.state()

    def open_state(self, state, note, render=True):
        """Show a figure_state (its code stays off until ticked, as with any figure read from a
        file); one from an earlier version holds "spec" instead.  render=False: no preview until
        the workspace asks for one.  The reason when it cannot be shown, else None."""
        form = state.get("doc") or state["spec"]
        try:
            fg.check_runs(form)
        except (KeyError, TypeError, ValueError) as e:
            return str(e)
        if state.get("doc"):
            self.shell.open_doc(form, note, state.get("save_as"), render)
        elif not self._open_spec(form, note, state.get("save_as"), render):
            return self.msg.object
        return None

    def _auto_path(self, name=AUTOSAVE):
        return config.cache_dir("autosave", config.run_key(self.run.path), name)

    def _autosave(self):
        """Keep the figure for the next page on this run.  This page's first write moves
        the last page's to one side, so making a new figure does not lose it."""
        path = self._auto_path()
        tmp = temp_name(path)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(self.figure_state(), f, default=float)
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
            return (state, os.path.getmtime(path)) \
                if isinstance(state.get("doc") or state.get("spec"), dict) else None
        except (OSError, ValueError, AttributeError):
            return None
