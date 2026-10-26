# Export, animations and the script

The **Export** tab holds the settings that apply when a figure is written, the animation,
templates and reopening a saved figure. Saving itself (folder, format, DPI) is above the
preview ([Figures](figures.md#saving)).

## Image settings

- **Trim white space**, with the margin it leaves (inches).
- **Background**: white, black or transparent.
- PDF, SVG and EPS keep text and lines as vectors; the fields are embedded as images at
  the chosen DPI.

## Reopening a saved figure

Give the path of a saved figure's `_spec.json` (in the `_src/` folder next to the image)
under *A saved figure* and press **Open**; its image or script path works too. The
editor then shows the figure with all its settings, ready to keep editing.

## Templates

*Save as template* keeps a figure's panels, layers and look **without its runs**, in
`templates/` next to the settings file. *Apply to this run* opens the template on the run
shown:

- its times are moved to the map's time and kept as far apart as they were (each at the
  nearest output; panels past the run's end stay empty);
- what only another run had (its soundings, a difference from it) is left out.

Use a template to make the same figure for each of several runs.

## Animations

**Export → Animation (GIF)** saves plan-view and cross-section figures as animated GIFs.
Figures made of parts work if at least one part is a plan view or cross-section: every
part steps together (soundings too), while time–height and time-series parts stay as they
are.

Each frame redraws the figure exactly as it is set up, a few outputs later. Every panel
steps forward together, and storm-centred panels and sections follow the storm. A fixed
*Minus time* in a difference layer stays put.

| Setting | Meaning |
|---|---|
| **End time** | The first panel's time in the last frame. By default the end of the run: the last time every panel has output. |
| **Step (outputs)** | Outputs from one frame to the next: 1 = every output, 2 = every other one, …. A line below counts the frames (at most 300). |
| **Frames per second** | Default 4. |
| **DPI** | Default 110. Keep it low: a GIF grows quickly with its size. |
| **Loop** | On by default. |
| **GIF path** | Where to save; blank uses `<Save as>.gif`. |
| **Also save the frames (PNG)** | Saves each frame as `<name>_frames/<name>_000.png`, …. |

To make a video from the frames, e.g.
`ffmpeg -framerate 4 -i name_%03d.png -pix_fmt yuv420p name.mp4`. **Stop** abandons a
running animation.

Colorbars stay the same in every frame: a fill whose colorbar ends are *auto* gets the
ends of the whole animation (every frame is read for them before the first is drawn), so
an arrow drawn for one frame is drawn for all of them.

A single panel (1 × 1) is the usual choice, but any grid works: a 1 × 2 figure of two
runs makes a side-by-side loop.

## The script and data

**+ script & data** saves, next to the image:

| File | Contents |
|---|---|
| `<name>.<fmt>` | The image. |
| `<name>.py` | The script. It redraws the identical image without the viewer. |
| `_src/<name>_data.npz` | The plotted arrays. |
| `_src/<name>_spec.json` | The figure's settings (the spec). |
| `_src/<name>_draw.py` | The drawing code, which the script imports. |

The script is short: `SPEC` (the figure's settings, as in the editor) and
`my_changes()`, where your own matplotlib goes (`fig`, `axs` by panel, `data`, `spec`, as
in *Your own code*). It finds the files relative to itself, so the folder can be moved or
copied.

The spec and the script's header record the cm1view version and, from a git checkout, its
commit, and a hash (sha256) of each run's `namelist.input`. The spec also records the
settings that change what a figure shows (`output_glob`, `track_dirs`, `track_patterns`,
`pdecomp_script`), so you can tell later exactly what made it.

To redraw: `python name.py`. To reopen it in the viewer, open its `_spec.json`
(above).

## Style presets (in scripts)

The editor has no preset menu, but `cm1view.figures.spec.apply_style(spec, name)` returns a
copy of a figure's spec with a preset applied. It is meant for Python scripts that use
cm1view, e.g. to restyle a saved figure's `_spec.json` for a journal or a talk (an
exported figure script does not import cm1view):

| Preset | What it sets |
|---|---|
| `default` | 10 pt sans-serif, 0.8 pt frames, white background. |
| `ams` | American Meteorological Society journals: 8 pt lettering, thinner frames, panel letters `(a)`, a vector PDF at 600 DPI, and a width of 3.2 in for one column or 6.5 in for more. |
| `talk` | Slides: 14 pt text, thicker frames, 10 in wide, PNG at 200 DPI. |
| `dark` | `talk` with a black background and matplotlib's `dark_background` style. |

The height follows the width at the same shape.

