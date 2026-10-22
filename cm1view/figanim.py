"""Figure editor: animations.  The figure as it is set up, redrawn at a run of output
times (every panel steps forward together; storm-centred panels follow the storm) and
saved as an animated GIF, optionally with each frame as a PNG.

A mixin of the FigureEditor (cm1view/figui.py)."""

import io
import os
import traceback
from functools import partial

import panel as pn
from PIL import Image

from . import config, figdraw, figure as fg
from .figparts import _chk, _f, _grid, _hint, _section

MAX_FRAMES = 300


class FigureAnimation:
    _anim_gen = 0  # bumped to stop a running animation

    def _build_anim(self):
        self.an_n = pn.widgets.IntInput(name="Frames", value=12, start=2, end=MAX_FRAMES,
                                        width=90)
        self.an_step = pn.widgets.IntInput(name="Every … outputs", value=1, start=1,
                                           end=1000, width=90)
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
        self.anim_sec = _section(
            "Animation (GIF)",
            _hint("Plan views and cross-sections, redrawn at successive output times from "
                  "the panels' own times: every panel steps forward together, and "
                  "storm-centred panels follow the storm. In a figure of parts, every "
                  "part steps (soundings too; time–height and time series stay). Saved as "
                  "<code>&lt;Save as&gt;.gif</code> (frames in "
                  "<code>&lt;Save as&gt;_frames/</code>)."),
            _grid(self.an_n, self.an_step, self.an_fps),
            _grid(self.an_dpi, self.an_loop, self.an_frames),
            pn.Row(self.an_go, self.an_stop, margin=0), self.an_msg, collapsed=True)

    def _anim_msg(self, html, err=False):
        col = ' style="color:#f87171"' if err else ""
        self.an_msg.object = f'<div class="cv-status"{col}>{html}</div>'

    def _anim_offsets(self, spec):
        runs = {p: self.open_run(p)[0] for p in {p for p, _ in fg.time_refs(spec)}}
        return fg.frame_offsets(spec, runs, int(self.an_n.value or 2),
                                int(self.an_step.value or 1))

    def _on_anim(self):
        spec = self.collect_all()
        if not fg.animated(spec):
            self._anim_msg("Animations are made of plan views or cross-sections (the "
                           "panels' kind in <b>Panels</b>; in a figure of parts, at least "
                           "one part of them).", True)
            return
        base = config.expand(self.path.value.strip())
        if not base:
            self._anim_msg("Choose where to save it (“Save as”).", True)
            return
        base = os.path.splitext(base)[0] if base.lower().endswith(".gif") else base
        try:
            offsets = self._anim_offsets(spec)
        except Exception as e:  # noqa: BLE001
            self._anim_msg(f"Could not open the panels' runs: {e}", True)
            return
        if len(offsets) < 2:
            self._anim_msg("No later output times with data in every panel: move the "
                           "panels' times earlier, or take fewer outputs per step.", True)
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

    def _stop_anim(self):
        self._anim_gen += 1
        self.an_stop.disabled = True

    def _anim_job(self, g, spec, offsets, base, opts):
        def done(html, err=False):
            def f():
                self.an_go.disabled, self.an_stop.disabled = False, True
                self._anim_msg(html, err)
            self.v._schedule(f)

        try:
            images, missing = [], 0
            fdir = base + "_frames"
            name = os.path.basename(base)
            if opts["frames"]:
                os.makedirs(fdir, exist_ok=True)
            for j, dt in enumerate(offsets):
                if g != self._anim_gen:
                    done(f"Stopped after {j} of {len(offsets)} frames; nothing saved.")
                    return
                self.v._schedule(partial(
                    self._anim_msg, f'<span class="busy">● Drawing frame {j + 1}/'
                                    f'{len(offsets)}…</span>'))
                s = fg.shift_times(spec, dt)
                data = self.panel_data(s)
                missing += any(d.get("missing") for d in data.values())
                fig = figdraw.draw(s, data)
                buf = io.BytesIO()
                figdraw.save(s, fig, buf, format="png", **fg.save_kw(s, opts["dpi"]))
                buf.seek(0)
                im = Image.open(buf)
                im.load()
                if opts["frames"]:
                    im.save(os.path.join(fdir, f"{name}_{j:03d}.png"))
                images.append(im.convert("RGBA") if im.mode in ("RGBA", "LA", "P")
                              else im.convert("RGB"))
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
