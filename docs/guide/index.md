# Using cm1view

cm1view opens in your browser as one window with three **workspaces**, a **top bar**
that every workspace shares, and a set of **tools** down the left edge of the map. This
page explains the parts of the window and what they have in common; the other pages take
one area each.

| Page | What it covers |
|---|---|
| [The map](map.md) | Fill, more fills, contours, vectors and streamlines; levels, ranges, zoom |
| [Soundings](soundings.md) | Skew-T, hodograph, parcels, indices, comparing points and times |
| [Storm tracking](tracking.md) | Following a storm through time; saving and loading tracks |
| [Cross-sections](cross-sections.md) | Vertical sections between two points |
| [3D](3d.md) | Isosurfaces, vectors and streamlines in a 3D scene |
| [Series and distributions](series.md) | A field reduced over a region at every time; all values at one time |
| [Figures](figures.md) | The quick start and saving; then [panels](figures-panels.md), [layers](figures-layers.md), [style and annotations](figures-style.md), and [export, animations and the script](figures-export.md) |
| [Notes on the fields](fields.md) | Winds, parcels, derived fields, pressure decomposition |
| [Worked examples](recipes.md) | Short walkthroughs that combine the tools |
| [Mouse and keyboard](shortcuts.md) | Every click, drag and shortcut in one place |
| [Troubleshooting](troubleshooting.md) | Messages and what to do about them |
| [Glossary](glossary.md) | Terms used in the viewer and the docs |

## The window

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Map | 3D | Figure   run ⚙   storm track   ⏮ ▶ ⏭ 1×  ──●────────  t = …    │  top bar
├───────────────────────────────────────────────────────────────────────────┤
│ fill field · level · Style ▾     More fills ▾  Contours ▾  Vectors ▾       │  map toolbar
├────┬──────────────────────────────────────────┬───────────────────────────┤
│tool│                                          │  the open tool's panel    │
│rail│                 the map                  │  (Sounding, Section, …)   │
│    │                                          │                           │
├────┴──────────────────────────────────────────┴───────────────────────────┤
│ items: Map view · sounding 1 · section · 3D box · series …                │  items tray
└───────────────────────────────────────────────────────────────────────────┘
```

### Workspaces

The **Map | 3D | Figure** buttons at the left of the top bar switch between:

- **Map**: the plan view, the tools and their panels. Most of the work starts here.
- **3D**: a 3D scene of a box you chose on the map ([3D](3d.md)).
- **Figure**: the editor for publication figures ([Figures](figures.md)).

Switching keeps everything: the map, your soundings and the computed series are still
there when you come back.

### Top bar

- **Run name** (folder icon): click it to open another run. See [Switching runs](#switching-runs).
- **⚙ Settings**: where your runs live, where figures and saved data go, and the other
  [settings](../settings.md). Most apply to the next save; a few (port, cache, workers)
  need a restart.
- **Storm track**: the tracked storm, used by everything storm-relative: soundings that
  move with the storm, the tracked storm motion, series around the storm, storm-relative
  vorticity and figures centred on the storm. The chip says how many fixes there are and
  turns amber when the shown time has none. Without a track it offers the run's track
  file when one is found (`track_dirs` / `track_patterns` in the settings): one click
  loads it. Otherwise a click opens the Track tool ([Storm tracking](tracking.md)).
- **Time controls**: ⏮ and ⏭ step one output back or forward (wrapping around at the
  ends), ▶ plays through the outputs, and the speed list sets the pace
  (0.5×, 1×, 2×, 4×: one output every 2.4, 1.2, 0.6 or 0.3 s, as fast as the data can
  be read). Drag the slider to jump. The label gives the model time and the output's
  place in the run (e.g. `12/60`; hover for the time in seconds). Every view follows the
  one time, except the items that you froze with *Pin this time*
  ([Soundings](soundings.md#comparing-places-and-times)). The map follows the slider at once; the
  slower panels (soundings, section, 3D, distributions) follow when time settles: when
  you release the slider, press a step button or pause playback. Soundings, 3D and
  distributions have a *Follow* option to turn that off.

### Tool rail

Down the left edge of the map: **Sounding**, **Section**, **Track**, **Series**,
**Distrib.** and **3D box**. (*Track* appears only when the run has what tracking
needs.)

- A tool sets what a click on the map does and opens its panel to the right of the map.
  One tool is on at a time; the line under the map says what a click will do.
- Pressing the lit tool again switches it off.
- The panel's ✕ closes the panel but leaves the tool on (its button reopens it). ⤢ gives
  the panel the whole window; **Map** brings the map back. Choosing another tool also
  brings the map back.
- **Clear** (eraser) removes every marker from the map: soundings, section line, 3D box
  and the streamline seed box.
- Less-used options in the Sounding and Track panels sit behind the settings button
  (sliders icon).

### Items tray

The row under the map lists what you have made: the **Map view**, each sounding, the
section, the 3D box and the computed series and distributions. Click an item to open its
panel; ✕ removes it, and the picture button makes a figure from it in the Figure
workspace (the box's cube opens it in 3D). Markers on the map use the same colours as
the items, so a sounding's point and its curves match.

### URL options

The address carries two options you can bookmark or share (on the same tunnel):

- `?run=/path/to/run` opens that run (the run picker sets it).
- `?t=<index>` opens at that output time (0 is the first).

## Switching runs

Click the run name in the top bar. In the dialog you can

- type to filter the list of your recent runs and the runs found under *Where your runs
  live* (the `runs_root` setting),
- paste or type a folder to list the runs inside it,
- pick one and press **Open run**.

The dialog also shows the open run's path, grid size, grid spacing, number of times and
domain motion (`umove`, `vmove`), and has **Clear cache**, which frees the cached 3D
fields of this run.

Opening a run reloads the page with `?run=/path`, so the old run's tabs stay open if you
had more than one. Open runs share one 3D cache (the `--cache-gb` budget); the least
recently used fields are freed first, so tabs on different runs do not empty each
other's cache.

## Performance

CM1 stores each 3D field one horizontal level per chunk. Plan views are therefore
instant, but anything that needs whole columns (soundings, sections, 3D, series over
layers) must read the full 3D field once per time: about 2.5 s per field per CPU. Those
fields stay cached, so every later click at that time is instant. The first sounding at
a new time loads five fields (`th`, `prs`, `qv`, `uinterp`, `vinterp`).

- Zooming the map re-renders at full resolution for the area in view; the map title
  says `full res` or `1/2 res (zoom for full)`. The `maxpix` setting caps the pixels sent
  per axis.
- The cache budget and number of reader processes come from the job's memory and CPUs;
  see [Running on a cluster](../hpc.md#resources) for how much to ask for.
- Computed series and distributions are kept in the cache folder, so asking again for the
  same one reads nothing.
