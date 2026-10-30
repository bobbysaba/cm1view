"""Figures without the viewer: `cm1view render`.  A saved figure (its _spec.json, or the
image or script saved with it) or a template is drawn again from the runs' files and
saved as an image, a bundle (image + script + data) or an animated GIF, e.g. in a batch
job after the runs are done:

    cm1view render ~/figures/supercell/_src/refl_spec.json
    cm1view render refl_template --run /path/run1 --run /path/run2 --time 90
    cm1view render refl_spec.json --run /path/run* --out '~/figs/{run}/refl.pdf'
    cm1view render refl_spec.json --gif --step 2 --fps 6

Given runs, the figure is drawn for each of them in turn as a template of it would be
(Templates in the editor): its layout and look on that run, its times moved to --time
(else kept).  Without, it is drawn as it was saved (--time moves every panel by the
same amount).

No Panel / Bokeh here (FigureData reads the data)."""

import argparse
import io
import json
import os
import sys
import time as _time
import traceback

import numpy as np

from .. import config
from . import draw as figdraw, spec as fg
from .export import saved_base

MAX_FRAMES = 300  # (every frame of a GIF is held in memory until it is written)
IMAGE_FORMATS = ("png", "pdf", "svg", "eps", "jpg", "jpeg", "tif", "tiff")


# ------------------------------------------------------------ the figure
def load_figure(arg):
    """(spec, is_template, name, source path) of `arg`: a saved figure's _spec.json (or
    the image or script saved with it), a template file, or a template's name."""
    path = config.expand(arg)
    if not os.path.exists(path):
        tpls = fg.list_templates()
        if arg in tpls:
            path = tpls[arg]
        elif not path.lower().endswith(".json") and \
                os.path.exists(fg.bundle_paths({}, path)["spec"]):
            path = fg.bundle_paths({}, path)["spec"]
        else:
            have = ", ".join(tpls) or "none saved"
            raise ValueError(f"{arg}: no such file, saved figure or template "
                             f"(templates: {have})")
    elif not path.lower().endswith(".json"):
        path = fg.bundle_paths({}, path)["spec"]
    with open(path) as f:
        spec = json.load(f)
    if not isinstance(spec, dict):
        raise ValueError(f"{path}: not a cm1view figure")
    if "template" in spec:
        name = (spec["template"] or {}).get("name") or \
            os.path.splitext(os.path.basename(path))[0]
        return spec, True, name, path
    if spec.get("version") == 2:
        if not isinstance(spec.get("form"), dict):
            raise ValueError(f"{path}: this version-2 spec has no editor settings "
                             "(\"form\"): redraw it with its script")
        spec = spec["form"]
    if spec.get("version") != 1:
        raise ValueError(f"{path}: not a cm1view figure spec (version 1 or 2) or template")
    return spec, False, os.path.basename(saved_base(path)), path


def _parts(spec):
    return spec["parts"] if spec.get("kind") == "combo" else [spec]


def finish(spec, run, F, t, code=False):
    """`spec` as the editor would show it on `run` at output t (fg.with_defaults, then
    fg.normalize, part by part; a part without runs takes `run` with its storm_tracks
    file, if any).  Its own code (Annotate → Your own code) stays off unless `code`."""
    track = fg.run_entry(run)["track"]
    parts = []
    for part in _parts(spec):
        p = fg.normalize(fg.with_defaults(part, run, F, t, track), run, track)
        bad = [lay.get("field") for lay in p["layers"]
               if lay.get("field") and lay["field"] not in F]
        if bad and len(p.get("runs") or []) <= 1:
            raise ValueError(f"{run.path} has no field " + ", ".join(bad))
        if not code and (p.get("code") or {}).get("on"):
            p["code"] = dict(p["code"], on=False)
        parts.append(p)
    if spec.get("kind") != "combo":
        return parts[0]
    runs, seen = [], set()  # (the figure's runs: its parts', as combine has them)
    for p in parts:
        for r in p.get("runs") or []:
            if r["path"] not in seen:
                seen.add(r["path"])
                runs.append(r)
    return dict(spec, parts=parts, runs=runs)


def first_time(spec):
    """Model time (s) of the figure's first panel (None: it has none)."""
    refs = fg.time_refs(spec)
    if refs:
        return float(refs[0][1])
    ts = _parts(spec)[0].get("time_s")
    return None if ts is None else float(ts)


def nearest(run, time_s):
    return int(np.argmin(np.abs(np.asarray(run.times, dtype=float) - float(time_s))))


def on_run(spec, is_template, name, run, F, time_s=None, code=False):
    """The figure (or template) drawn on `run`: its first panel at model time time_s
    (s; None: the template's own time, else the run's first output)."""
    tpl = spec if is_template else fg.template(spec, name)
    t0 = (tpl.get("template") or {}).get("time_s")
    ts = time_s if time_s is not None else t0
    t = 0 if ts is None else nearest(run, ts)
    return finish(fg.from_template(tpl, run, t), run, F, t, code)


def as_saved(spec, fd, time_s=None, code=False):
    """The saved figure on its own runs (a storm track from the viewer's Track tab, which
    is not saved with it: the run's storm_tracks file instead); every panel moved so
    the first is at the output nearest model time time_s (s), if given.  (spec,
    notes)."""
    s, notes = json.loads(json.dumps(spec, default=float)), []
    for p in [s] + list(s.get("parts") or []):
        for e in p.get("runs") or []:
            if not os.path.isdir(config.expand(e["path"])):
                raise ValueError(f"run folder {e['path']} not found")
            if e.get("track") == "viewer":
                e["track"] = fg.find_track(config.expand(e["path"])) or ""
                notes.append(f"{e['path']}: the viewer's track is not saved with the "
                             "figure; " + (f"using {e['track']}" if e["track"] else
                                           "no storm_tracks file found, so no track"))
    notes = list(dict.fromkeys(notes))
    for path in fg.changed_runs(s):
        notes.append(f"{path}: namelist.input changed since the figure was saved, so its "
                     "data may differ")
    runs = _parts(s)[0].get("runs") or []
    if not runs:
        raise ValueError("the figure has no runs: give one with --run")
    run, F = fd.open_run(runs[int(_parts(s)[0].get("run", 0) or 0)]["path"])
    if time_s is not None:  # (to the output nearest it)
        t0 = first_time(s)
        if t0 is not None:
            s = fg.shift_times(s, float(run.times[nearest(run, time_s)]) - t0)
    ts = first_time(s)
    t = 0 if ts is None else nearest(run, ts)
    return finish(s, run, F, t, code), notes


# ------------------------------------------------------------ saving
def image_base(out, fmt):
    """(base without extension, format) of an output path: its extension, if an image
    format's, else `fmt`."""
    stem, ext = os.path.splitext(out)
    if ext.lower().lstrip(".") in IMAGE_FORMATS + ("gif",):
        return stem, (fmt if ext.lower() == ".gif" else ext.lower().lstrip("."))
    return out, fmt


def outputs(base, fmt, how):
    """The paths saving as `base` writes (how: "image", "bundle", "gif", "gif+frames")."""
    if how == "image":
        return [f"{base}.{fmt}"]
    if how == "bundle":
        return list(fg.bundle_paths(dict(export=dict(format=fmt)), base).values())
    return [base + ".gif"] + ([base + "_frames"] if how == "gif+frames" else [])


def save_image(spec, data, base, dpi=None):
    return fg.save_image(spec, data, f"{base}.{spec['export']['format']}", dpi)


def anim_frame(spec, offsets, j, dpi):
    """The spec of animation frame j: its times moved on; a 3D scene's camera turned by
    its share of the orbit and its picture rendered at `dpi`."""
    s = fg.scene_frame(fg.shift_times(spec, offsets[j]), j, len(offsets))
    if s.get("kind") == "scene":
        s["scene3d"] = dict(s["scene3d"], dpi=dpi)
    return s


def auto_ends(spec):
    """Whether the figure has fills with "auto" colorbar ends (an animation reads every
    frame first, so all frames have the same)."""
    return any(lay.get("type") == "fill" and lay.get("extend") == "auto"
               for p in figdraw.upgrade(spec)[0]["panels"] for lay in p.get("layers") or [])


def frame_image(s, data, ends, dpi):
    """Frame spec s drawn as a PIL image (RGB, or RGBA when it has transparency)."""
    from PIL import Image
    fig = figdraw.draw(s, data, ends)
    buf = io.BytesIO()
    figdraw.save(s, fig, buf, format="png", **fg.save_kw(s, dpi))
    buf.seek(0)
    im = Image.open(buf)
    im.load()
    return im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")


def frame_offsets(fd, spec, step=1, end_s=None):
    runs = {p: fd.open_run(p)[0] for p in {p for p, _ in fg.time_refs(spec)}}
    return fg.frame_offsets(spec, runs, int(step), end_s, MAX_FRAMES + 1)


def save_gif(fd, spec, base, offsets, fps=4.0, dpi=110, loop=True, frames=False,
             say=print):
    """The figure redrawn at each of `offsets` (s) and saved as base.gif (and
    base_frames/<name>_NNN.png with `frames`).  (path, frames, frames with an empty
    panel)."""
    ends = {}
    if auto_ends(spec):
        for j, dt in enumerate(offsets):
            say(f"reading frame {j + 1}/{len(offsets)} for the colorbar ends")
            s = fg.shift_times(spec, dt)
            ends = figdraw.fill_ends(s, fd.panel_data(s), ends)
    fdir, name = base + "_frames", os.path.basename(base)
    if frames:
        os.makedirs(fdir, exist_ok=True)
    images, missing = [], 0
    for j in range(len(offsets)):
        say(f"drawing frame {j + 1}/{len(offsets)}")
        s = anim_frame(spec, offsets, j, dpi)
        data = fd.panel_data(s)
        missing += any(d.get("missing") for d in data.values())
        im = frame_image(s, data, ends, dpi)
        if frames:
            im.save(os.path.join(fdir, f"{name}_{j:03d}.png"))
        images.append(im)
    return fg.write_gif(images, base + ".gif", fps, loop), len(images), missing


# ------------------------------------------------------------ command line
def _out_pattern(out, run_path, name):
    parent = os.path.basename(os.path.dirname(run_path.rstrip("/")))
    return config.expand(out.format(run=os.path.basename(run_path.rstrip("/")),
                                    parent=parent, name=name))


def parser():
    ap = argparse.ArgumentParser(
        prog="cm1view render",
        description="Draw a saved figure or template from the runs' files, without the "
                    "viewer (e.g. in a batch job).",
        epilog="--out may hold {run} (the run's folder name), {parent} (the folder "
               "above it) and {name} (the figure's or template's name).")
    ap.add_argument("figure",
                    help="a saved figure (its _src/<name>_spec.json, or the image or "
                         "script saved with it), a template file, or a template's name")
    ap.add_argument("--run", action="append", nargs="+", default=[], metavar="PATH",
                    help="draw it for this run (several: one figure each, as a template "
                         "of it would be); a template needs at least one")
    ap.add_argument("--time", type=float, default=None, metavar="MIN",
                    help="model time (min) of the first panel; the others keep their "
                         "spacing (default: the saved figure's)")
    ap.add_argument("--out", default=None, metavar="PATH",
                    help="where to save (its extension, if any, sets the format); default: "
                         "where the figure was saved, or <figures folder>/<run>/<name> "
                         "for --run")
    ap.add_argument("--format", default=None, choices=IMAGE_FORMATS,
                    help="image format (default: the figure's)")
    ap.add_argument("--dpi", type=int, default=None,
                    help="resolution (default: the figure's; 110 for --gif)")
    ap.add_argument("--bundle", action="store_true",
                    help="also save the script, data and spec (as “+ script & data”)")
    ap.add_argument("--gif", action="store_true",
                    help="an animated GIF from the figure's times on (plan views, "
                         "sections and 3D scenes step in time)")
    ap.add_argument("--step", type=int, default=1,
                    help="GIF: outputs from one frame to the next (default 1)")
    ap.add_argument("--end", type=float, default=None, metavar="MIN",
                    help="GIF: model time (min) of the first panel in the last frame "
                         "(default: the run's end)")
    ap.add_argument("--fps", type=float, default=4.0, help="GIF: frames per second")
    ap.add_argument("--no-loop", action="store_true", help="GIF: play once")
    ap.add_argument("--frames", action="store_true",
                    help="GIF: also save each frame as a PNG (in <name>_frames/)")
    ap.add_argument("--code", action="store_true",
                    help="run the figure's own code (Annotate → Your own code), which "
                         "the editor asks before running")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace files that are already there (default: stop)")
    ap.add_argument("--config", default=None, help="settings file")
    ap.add_argument("--cache-gb", type=float, default=None,
                    help="memory budget for cached 3D fields")
    ap.add_argument("--workers", type=int, default=None,
                    help="parallel reader processes (series)")
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    if args.config:
        config.load(args.config)
    for name, flag in (("cache_gb", "--cache-gb"), ("workers", "--workers")):
        if getattr(args, name) is not None:
            config.override(name, getattr(args, name), flag)
    if args.gif and args.bundle:
        print("cm1view render: --gif and --bundle: one or the other", file=sys.stderr)
        return 2
    try:
        spec, is_tpl, name, src = load_figure(args.figure)
    except (OSError, ValueError) as e:
        print(f"cm1view render: {e}", file=sys.stderr)
        return 2
    runs = [config.expand(p) for ps in args.run for p in ps]
    for p in runs:
        if not os.path.isdir(p):
            print(f"cm1view render: run folder {p} not found", file=sys.stderr)
            return 2
    if is_tpl and not runs:
        print(f"cm1view render: {name} is a template: give the run(s) with --run",
              file=sys.stderr)
        return 2
    if args.out and len(runs) > 1 and "{run}" not in args.out and "{parent}" not in args.out:
        print("cm1view render: several runs to one --out: put {run} in it, e.g. "
              "--out '~/figures/{run}/" + name + "'", file=sys.stderr)
        return 2
    how = ("gif+frames" if args.frames else "gif") if args.gif else \
        ("bundle" if args.bundle else "image")
    fmt0 = args.format or (spec.get("export") or {}).get("format") or "png"
    saved_run = ((_parts(spec)[0].get("runs") or [{}])[0]).get("path", "")

    jobs = []  # (run path or None, base, format)
    for rp in runs or [None]:
        if args.out:
            out = _out_pattern(args.out, rp or saved_run, name)
        elif rp:
            out = os.path.join(config.figures_dir(rp), name)
        else:
            out = saved_base(src)
        base, fmt = image_base(out, fmt0)
        jobs.append((rp, base, fmt))
    paths = [p for _, base, fmt in jobs for p in outputs(base, fmt, how)]
    if len(set(paths)) < len(paths):
        print("cm1view render: two runs would save to the same file: put {run} in --out",
              file=sys.stderr)
        return 2
    there = [p for p in paths if os.path.exists(p)]
    if there and not args.overwrite:
        print("cm1view render: already there (--overwrite replaces them):\n  "
              + "\n  ".join(there), file=sys.stderr)
        return 2

    from .render import FigureData
    fd = FigureData(cache_gb=config.cache_gb()[0], workers=config.workers()[0])
    time_s = None if args.time is None else args.time * 60.0
    failed = 0
    for n, (rp, base, fmt) in enumerate(jobs, 1):
        head = f"cm1view render [{n}/{len(jobs)}]"
        t0 = _time.time()

        def say(text, head=head):
            print(f"{head} {text}", flush=True)
        try:
            if rp:
                run, F = fd.open_run(rp)
                s, notes = on_run(spec, is_tpl, name, run, F, time_s, args.code), []
            else:
                s, notes = as_saved(spec, fd, time_s, args.code)
            for note in notes:
                say(f"note: {note}")
            for p in _parts(s) + ([s] if s.get("kind") == "combo" else []):
                p["export"] = dict(p.get("export") or {}, format=fmt,
                                   **({"dpi": args.dpi} if args.dpi and not args.gif else {}))
            say(f"{rp or name}: reading")
            if args.gif:
                if not fg.animated(s):
                    raise ValueError("animations are made of plan views, cross-sections "
                                     "or 3D scenes")
                end_s = None if args.end is None else args.end * 60.0
                offsets = frame_offsets(fd, s, max(1, args.step), end_s)
                if len(offsets) < 2:
                    raise ValueError("no later output times with data in every panel")
                if len(offsets) > MAX_FRAMES:
                    raise ValueError(f"more than {MAX_FRAMES} frames: take a larger "
                                     "--step or an earlier --end")
                path, k, missing = save_gif(fd, s, base, offsets, args.fps,
                                            args.dpi or 110, not args.no_loop,
                                            args.frames, say)
                out = [path] + ([base + "_frames/"] if args.frames else [])
                if missing:
                    say(f"note: {missing} frame(s) with an empty panel")
            else:
                data = fd.panel_data(s)
                for i, d in data.items():
                    if d.get("missing"):
                        say(f"note: panel {i}: {d['missing']}")
                if args.bundle:
                    run = fd.open_run(rp)[0] if rp else None
                    out = list(fg.save_bundle(s, data, base, run).values())
                else:
                    out = [save_image(s, data, base)]
            for path, err in fd.track_err.items():
                say(f"note: storm track {path}: {err}")
            say(f"saved {', '.join(out)} [{_time.time() - t0:.1f}s]")
        except Exception as e:  # noqa: BLE001  (the other runs still get theirs)
            failed += 1
            traceback.print_exc()
            say(f"failed: {e}")
    return 1 if failed else 0
