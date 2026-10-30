"""Figure editor: animations.  The figure as it is set up, redrawn at a run of output
times (every panel steps forward together; storm-centred panels follow the storm; a 3D
scene's box can follow the track and its camera orbit) and saved as an animated GIF,
optionally with each frame as a PNG.

A mixin of the FigureEditor (figures/editor.py)."""

import io
import os
import traceback
from functools import partial

import panel as pn
from PIL import Image

from .. import config
from . import draw as figdraw, spec as fg
from .cards import _chk, _f, _grid, _hint, _section

MAX_FRAMES = 300  # (every frame is held in memory until the GIF is written)
END = "End of run"
IMAGE_EXTS = (".gif", ".png", ".pdf", ".svg", ".eps", ".jpg", ".jpeg", ".tif", ".tiff")


class FigureAnimation:
    _anim_gen = 0  # bumped to stop a running animation
    _an_times = []  # (label, model time s) of the frames through the run's end
    _preview_waiting = False  # a preview render is queued (set by request, FigureEditor)

    def _build_anim(self):
        self.an_path = pn.widgets.TextInput(name="GIF path",
                                            placeholder="blank: <Save as>.gif")
        self.an_step = pn.widgets.IntInput(name="Step (outputs)", value=1, start=1,
                                           end=1000, width=90,
                                           description="Outputs from one frame to the "
                                                       "next: 1 = every output, 2 = every "
                                                       "other one, …")
        self.an_end = pn.widgets.Select(name="End time", options={END: None}, value=None,
                                        description="The first panel's time in the last "
                                                    "frame")
        self.an_count = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8))
        self.an_fps = _f("Frames per second", 4.0, step=0.5, start=0.2, end=50.0)
        self.an_dpi = pn.widgets.IntInput(name="DPI", value=110, start=30, end=600,
                                          step=10, width=80,
                                          description="Lower than for print: a GIF grows "
                                                      "quickly with its size")
        self.an_loop = _chk("Loop", True)
        self.an_frames = _chk("Also save the frames (PNG)", False)
        self.an_go = pn.widgets.Button(name="Save animation", icon="movie",
                                       button_type="primary", height=32)
        self.an_stop = pn.widgets.Button(name="Stop", button_type="light",
                                         button_style="outline", height=32, disabled=True)
        self.an_msg = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8))
        self.an_go.on_click(lambda e: self._on_anim())
        self.an_stop.on_click(lambda e: self._stop_anim())
        self.an_step.param.watch(lambda e: self._anim_refresh(), "value")
        self.an_end.param.watch(lambda e: self._anim_count(), "value")
        self.anim_sec = _section(
            "Animation (GIF)",
            _hint("Plan views, cross-sections and 3D scenes, redrawn at successive output "
                  "times from the panels' own times: every panel steps forward together, "
                  "and storm-centred panels follow the storm (a 3D scene: its box and "
                  "camera orbit, Layers → Animation). In a figure of parts, every "
                  "part steps (soundings too; time–height and time series stay). Saved at "
                  "<i>GIF path</i>, or <code>&lt;Save as&gt;.gif</code> if it is blank "
                  "(frames in <code>&lt;name&gt;_frames/</code>)."),
            _grid((self.an_path, 3)),
            _grid(self.an_step, self.an_end, self.an_fps), self.an_count,
            _grid(self.an_dpi, self.an_loop, self.an_frames),
            pn.Row(self.an_go, self.an_stop, margin=0), self.an_msg)
        self.anim_sec.param.watch(lambda e: e.new or self._anim_refresh(), "collapsed")

    def _anim_msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.an_msg.object = f'<div class="cv-status"{col}>{html}</div>'

    def _anim_runs(self, spec):
        return {p: self.open_run(p)[0] for p in {p for p, _ in fg.time_refs(spec)}}

    def _anim_offsets(self, spec, limit=MAX_FRAMES + 1):
        return fg.frame_offsets(spec, self._anim_runs(spec), int(self.an_step.value or 1),
                                self.an_end.value, limit)

    def _anim_refresh(self, spec=None):
        """The End time choices (the frames' times through the run's end) and the
        frame count, while the Animation section is open."""
        if self.anim_sec.collapsed:
            return
        self._an_times, opts = [], {END: None}
        try:
            spec = self.collect_all() if spec is None else spec
            refs = fg.time_refs(spec) if fg.animated(spec) else []
            if refs:
                runs = self._anim_runs(spec)
                run0, ts0 = runs[refs[0][0]], refs[0][1]
                dts = fg.frame_offsets(spec, runs, int(self.an_step.value or 1))
                ks = [fg.tindex(run0, ts0 + dt) for dt in dts]
                self._an_times = [(run0.time_label(k), float(run0.times[k])) for k in ks]
                opts.update({lab: t for lab, t in self._an_times[1:]})
        except Exception:  # noqa: BLE001  (incomplete settings: no count)
            pass
        v = self.an_end.value
        self.an_end.options = opts
        self.an_end.value = v if v in opts.values() else None
        self._anim_count()

    def _anim_count(self):
        end = self.an_end.value
        tl = [x for x in self._an_times if end is None or x[1] <= end + 1.0]
        if len(tl) < 2:
            msg, col = "No later output times with data in every panel", ""
        elif len(tl) > MAX_FRAMES:
            msg = (f"{len(tl)} frames, {tl[0][0]} to {tl[-1][0]}: at most {MAX_FRAMES} "
                   "(take a larger step or an earlier end time)")
            col = ' style="color:#f87171"'
        else:
            msg, col = f"→ {len(tl)} frames, {tl[0][0]} to {tl[-1][0]}", ""
        self.an_count.object = f'<div class="cv-hint"{col}>{msg}</div>'

    def _on_anim(self):
        spec = self.collect_all()
        if not fg.animated(spec):
            self._anim_msg("Animations are made of plan views, cross-sections or 3D "
                           "scenes (the panels' kind in <b>Panels</b>; in a figure of "
                           "parts, at least one part of them).", True)
            return
        base = config.expand(self.an_path.value.strip() or self.path.value.strip())
        if not base:
            self._anim_msg("Choose where to save it (“GIF path” or “Save as”).", True)
            return
        stem, ext = os.path.splitext(base)
        base = stem if ext.lower() in IMAGE_EXTS else base
        try:
            offsets = self._anim_offsets(spec)
        except Exception as e:  # noqa: BLE001
            self._anim_msg(f"Could not open the panels' runs: {e}", True)
            return
        if len(offsets) < 2:
            self._anim_msg("No later output times with data in every panel: move the "
                           "panels' times earlier, or take fewer outputs per step.", True)
            return
        if len(offsets) > MAX_FRAMES:
            self._anim_msg(f"More than {MAX_FRAMES} frames: take a larger step or an "
                           "earlier end time.", True)
            return
        opts = dict(fps=float(self.an_fps.value or 4.0), dpi=int(self.an_dpi.value or 110),
                    loop=bool(self.an_loop.value), frames=bool(self.an_frames.value))
        paths = [base + ".gif"] + ([base + "_frames"] if opts["frames"] else [])

        def go():
            self._anim_gen += 1
            self.an_go.disabled, self.an_stop.disabled = True, False
            self._anim_msg(f'<span class="busy">● Drawing frame 1/{len(offsets)}…</span>')
            self.v.pools["fig"].submit(self._anim_job, self._anim_gen, spec, offsets, base,
                                       opts)
        self.v.confirm.ask(paths, go)

    @staticmethod
    def _anim_frame(spec, offsets, j, opts):
        """The spec of frame j: its times moved on; a 3D scene's camera turned by its
        share of the orbit and its picture rendered at the animation's DPI."""
        s = fg.scene_frame(fg.shift_times(spec, offsets[j]), j, len(offsets))
        if s.get("kind") == "scene":
            s["scene3d"] = dict(s["scene3d"], dpi=opts["dpi"])
        return s

    def _stop_anim(self):
        self._anim_gen += 1
        self.an_stop.disabled = True

    def _anim_job(self, g, spec, offsets, base, opts, images=None, missing=0, ends=None,
                  scanned=0):
        """Read the frames from `scanned` on for the colorbar ends of the fills with
        "auto" ends (`ends`: those of all frames, so every frame has the same), then draw
        the frames from len(images) on and write the GIF.  When a preview is waiting (an
        edit while the animation is saved) the job puts itself back in the queue after
        the frame it is on, so the preview waits for one frame, not for all of them; the
        frames keep the spec as it was when Save animation was pressed."""
        def done(html, err=False):
            def f():
                self.an_go.disabled, self.an_stop.disabled = False, True
                self._anim_msg(html, err)
            self.v._schedule(f)

        images = [] if images is None else images
        ends = {} if ends is None else ends
        auto = any(lay.get("type") == "fill" and lay.get("extend") == "auto"
                   for p in figdraw.upgrade(spec)[0]["panels"] for lay in p.get("layers") or [])
        try:
            for j in range(scanned, len(offsets) if auto else 0):
                if g != self._anim_gen:
                    done(f"Stopped while reading frame {j + 1} of {len(offsets)}; "
                         "nothing saved.")
                    return
                self.v._schedule(partial(
                    self._anim_msg, f'<span class="busy">● Reading frame {j + 1}/'
                                    f'{len(offsets)} for the colorbar ends…</span>'))
                s = fg.shift_times(spec, offsets[j])
                ends = figdraw.fill_ends(s, self.panel_data(s), ends)
                if self._preview_waiting and j + 1 < len(offsets):
                    self.v.pools["fig"].submit(self._anim_job, g, spec, offsets, base,
                                               opts, images, missing, ends, j + 1)
                    return
            fdir = base + "_frames"
            name = os.path.basename(base)
            if opts["frames"]:
                os.makedirs(fdir, exist_ok=True)
            for j in range(len(images), len(offsets)):
                if g != self._anim_gen:
                    done(f"Stopped after {j} of {len(offsets)} frames; nothing saved.")
                    return
                self.v._schedule(partial(
                    self._anim_msg, f'<span class="busy">● Drawing frame {j + 1}/'
                                    f'{len(offsets)}…</span>'))
                s = self._anim_frame(spec, offsets, j, opts)
                data = self.panel_data(s)
                missing += any(d.get("missing") for d in data.values())
                fig = figdraw.draw(s, data, ends)
                buf = io.BytesIO()
                figdraw.save(s, fig, buf, format="png", **fg.save_kw(s, opts["dpi"]))
                buf.seek(0)
                im = Image.open(buf)
                im.load()
                if opts["frames"]:
                    im.save(os.path.join(fdir, f"{name}_{j:03d}.png"))
                images.append(im.convert("RGBA") if im.mode in ("RGBA", "LA", "P")
                              else im.convert("RGB"))
                if self._preview_waiting and len(images) < len(offsets):
                    self.v.pools["fig"].submit(self._anim_job, g, spec, offsets, base,
                                               opts, images, missing, ends, len(offsets))
                    return
            path = fg.write_gif(images, base + ".gif", opts["fps"], opts["loop"])
            mb = os.path.getsize(path) / 1e6
            note = (f" · {missing} frame{'s' if missing != 1 else ''} with an empty panel"
                    if missing else "")
            done(f"Saved <code>{path}</code> ({len(images)} frames, "
                 f"{images[0].width} × {images[0].height} px, {mb:.1f} MB)"
                 + (f" and the frames in <code>{fdir}/</code>" if opts["frames"] else "")
                 + note)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            done(f"Could not make the animation: {e}", True)
