"""Figure editor: animations.  The figure as it is set up, redrawn at a run of output
times (every panel steps forward together; storm-centred panels follow the storm; a 3D
scene's box can follow the track and its camera orbit) and saved as an animated GIF,
optionally with each frame as a PNG.

A mixin of the FigureEditor (figures/editor.py)."""

import os
import traceback
from functools import partial

import panel as pn

from . import draw as figdraw, spec as fg
from .batch import (MAX_FRAMES, anim_frame, auto_ends, frame_image, frame_pixels,
                    frame_pool, pixels_image)
from .cards import _chk, _f

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
        have = fg.video_encoder() is not None
        self.an_fmt = pn.widgets.Select(
            name="Format", width=150, value="gif",
            options={"GIF": "gif", "MP4 video" if have else "MP4 (no encoder)": "mp4"},
            description="A GIF has 256 colours per frame; an MP4 keeps them all and is far "
                        "smaller, but needs ffmpeg")
        self.an_fmt_note = pn.pane.HTML(
            "" if have else f'<div class="cv-hint" style="color:#f87171">{fg.VIDEO_HELP}</div>',
            sizing_mode="stretch_width", margin=(0, 8))
        self.an_frames = _chk("Also save the frames (PNG)", False)
        self.an_go = pn.widgets.Button(name="Save animation", icon="movie",
                                       button_type="primary", height=32)
        self.an_stop = pn.widgets.Button(name="Stop", button_type="light",
                                         button_style="outline", height=32, disabled=True)
        self.an_msg = pn.pane.HTML(sizing_mode="stretch_width", margin=(0, 8))
        self.an_step.param.watch(lambda e: self._anim_refresh(), "value")
        self.an_end.param.watch(lambda e: self._anim_count(), "value")

    def _anim_msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.an_msg.object = f'<div class="cv-status"{col}>{html}</div>'
        self.shell.say(html, err)

    def _anim_runs(self, spec):
        return {p: self.open_run(p)[0] for p in {p for p, _ in fg.time_refs(spec)}}

    def _anim_offsets(self, spec, limit=MAX_FRAMES + 1):
        return fg.frame_offsets(spec, self._anim_runs(spec), int(self.an_step.value or 1),
                                self.an_end.value, limit)

    def _anim_refresh(self, spec=None):
        """The End time choices (the frames' times through the run's end) and the frame count."""
        self._an_times, opts = [], {END: None}
        try:
            spec = self._figure_now() if spec is None else spec
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
        spec = self._figure_now()
        if not fg.animated(spec):
            self._anim_msg("Time–height plots and time series show every time already, "
                           "so they have nothing to step: a figure needs a panel of another "
                           "type.", True)
            return
        base = config.expand(self.an_path.value.strip() or self.path.value.strip())
        if not base:
            self._anim_msg("Choose where to save it (“Save path” or “Save as”).", True)
            return
        stem, ext = os.path.splitext(base)
        base = stem if ext.lower() in IMAGE_EXTS + (".mp4",) else base
        fmt = self.an_fmt.value
        if fmt == "mp4" and fg.video_encoder() is None:
            self._anim_msg(fg.VIDEO_HELP, True)
            return
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
                    loop=bool(self.an_loop.value), frames=bool(self.an_frames.value),
                    fmt=fmt)
        paths = [base + "." + fmt] + ([base + "_frames"] if opts["frames"] else []) + \
            [fg.bundle_paths(spec, base)["spec"]]

        def go():
            self._anim_gen += 1
            self.an_go.disabled, self.an_stop.disabled = True, False
            self._anim_msg(f'<span class="busy">● Drawing frame 1/{len(offsets)}…</span>')
            self.v.pools["fig"].submit(self._anim_job, self._anim_gen, spec, offsets, base,
                                       opts)
        self.v.confirm.ask(paths, go)

    @staticmethod
    def _anim_frame(spec, offsets, j, opts):
        return anim_frame(spec, offsets, j, opts["dpi"])

    def _anim_pool(self, spec, n):
        """(the reader processes, how many frames they draw at once) for `n` frames
        (core.pool: the pool every run reads with, most of it; (None, 1): draw in this
        process, for a 3D scene or a few frames)."""
        return frame_pool(spec, self.v.run.workers, n)

    def _stop_anim(self):
        self._anim_gen += 1
        self.an_stop.disabled = True

    def _anim_job(self, g, spec, offsets, base, opts, images=None, missing=0, ends=None,
                  scanned=0):
        """Read the frames from `scanned` on for the colorbar ends of the fills with
        "auto" ends and the scales of the panels that fit their data (`ends`: those of all
        frames, so every frame has the same), then draw the frames from len(images) on
        and write the GIF.  When a preview is waiting (an
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
        auto = auto_ends(spec)
        try:
            for j in range(scanned, len(offsets) if auto else 0):
                if g != self._anim_gen:
                    done(f"Stopped while reading frame {j + 1} of {len(offsets)}; "
                         "nothing saved.")
                    return
                self.v._schedule(partial(
                    self._anim_msg, f'<span class="busy">● Reading frame {j + 1}/'
                                    f'{len(offsets)} for the scales…</span>'))
                s = fg.shift_times(spec, offsets[j])
                ends = figdraw.fill_ends(s, self.panel_data(s), ends)
                if self._preview_waiting and j + 1 < len(offsets):
                    self.v.pools["fig"].submit(self._anim_job, g, spec, offsets, base,
                                               opts, images, missing, ends, j + 1)
                    return
            ends = figdraw.fit_scales(spec, ends)  # (already fitted: stays as it is)
            fdir = base + "_frames"
            name = os.path.basename(base)
            if opts["frames"]:
                os.makedirs(fdir, exist_ok=True)
            ex, width = self._anim_pool(spec, len(offsets) - len(images))
            todo = list(range(len(images), len(offsets)))
            while todo:
                if g != self._anim_gen:
                    done(f"Stopped after {len(images)} of {len(offsets)} frames; "
                         "nothing saved.")
                    return
                chunk, todo = todo[:width], todo[width:]
                self.v._schedule(partial(
                    self._anim_msg, f'<span class="busy">● Drawing frame {chunk[0] + 1}'
                                    f'–{chunk[-1] + 1}/{len(offsets)}…</span>'
                    if len(chunk) > 1 else f'<span class="busy">● Drawing frame '
                                           f'{chunk[0] + 1}/{len(offsets)}…</span>'))
                jobs = []  # (frame spec, its data, the future drawing it)
                for j in chunk:  # (reads in this thread; drawing overlaps in the pool)
                    s = self._anim_frame(spec, offsets, j, opts)
                    data = self.panel_data(s)
                    missing += any(d.get("missing") for d in data.values())
                    fut = None if ex is None else ex.submit(
                        frame_pixels, s, data, ends, opts["dpi"])
                    jobs.append((s, data, fut))
                for j, (s, data, fut) in zip(chunk, jobs):
                    im = frame_image(s, data, ends, opts["dpi"]) if fut is None \
                        else pixels_image(fut.result())
                    if opts["frames"]:
                        im.save(os.path.join(fdir, f"{name}_{j:03d}.png"))
                    images.append(im)
                if self._preview_waiting and todo:
                    self.v.pools["fig"].submit(self._anim_job, g, spec, offsets, base,
                                               opts, images, missing, ends, len(offsets))
                    return
            if opts.get("fmt") == "mp4":
                self.v._schedule(partial(self._anim_msg, '<span class="busy">● Encoding '
                                                         'the video…</span>'))
                path = fg.write_video(images, base + ".mp4", opts["fps"])
            else:
                path = fg.write_gif(images, base + ".gif", opts["fps"], opts["loop"])
            spec_path = fg.save_spec(spec, base)
            mb = os.path.getsize(path) / 1e6
            note = (f" · {missing} frame{'s' if missing != 1 else ''} with an empty panel"
                    if missing else "")
            done(f"Saved <code>{path}</code> ({len(images)} frames, "
                 f"{images[0].width} × {images[0].height} px, {mb:.1f} MB)"
                 + (f" and the frames in <code>{fdir}/</code>" if opts["frames"] else "")
                 + f"; its settings in <code>{spec_path}</code>" + note)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            done(f"Could not make the animation: {e}", True)
