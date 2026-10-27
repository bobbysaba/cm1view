# Changes

What changed in each release, newest first. The version is in `pyproject.toml`; a release
has a matching git tag.

## Unreleased (since v0.4.0)

### Figures

- **Time–height panels follow each series' Runs**: a series is drawn for the runs it
  picks (blank: every run), and a run no series uses gets no column
  ([Panels](guide/figures-panels.md#timeheight-series)).
- **Hatching and stippling**: a shading layer's *Pattern* hatches, cross-hatches or
  stipples its area ([Layers](guide/figures-layers.md)).
- **Wind barbs** on plan views, in knots or m/s, as a vector layer's *Draw as*.
- **Strip-averaged cross-sections**: *Average across* (km) averages the sections within
  a strip along the line; a *Section line* layer shows the strip.
- Reopening a saved figure says when a run's `namelist.input` changed since it was saved.
- **Vertical profile panels**: a field's maximum, minimum, mean or percentile over the
  domain, a box or around the storm, against height, one line per run and time (or the
  mean over a time window); computed like a layer series and cached with them
  ([Panels](guide/figures-panels.md#vertical-profiles)).
- **Joint distribution panels**: one field against another at the same points (at a
  height, over a layer or the whole depth, in the domain, a box or around the storm, at
  one time or over a time window), as a 2D histogram, a scatter or density contours
  enclosing chosen percentages, with a fit line and n, r, r², fit and means in a box
  ([Panels](guide/figures-panels.md#joint-distributions)).
- **Azimuthal mean panels**: a field's mean, maximum or minimum in radius bins against
  height around the tracked storm or a fixed point, within a sector of azimuths
  (clockwise from the storm's motion or from north), at one time or as a
  storm-following composite over a time window; the first in a panel shaded, the others
  as contour lines ([Panels](guide/figures-panels.md#azimuthal-means)). A **Sector**
  layer outlines the sector on plan views.
- **Ensemble bands** on time-series panels: a series over several runs as its mean or
  median and a shaded min–max, 10–90 %, 25–75 % or ±1 sd range, the runs faint or hidden
  ([Panels](guide/figures-panels.md#time-series)).
- **Ensemble fills**: a fill layer as the mean, median, spread, min, max, range or
  probability of exceeding a threshold over several runs
  ([Layers](guide/figures-layers.md#ensembles)).
- **Several cross-sections in a figure**: *Panels → Sections* lists named sections,
  each x–z, y–z, angled (clockwise from north) or A–B, through the storm or fixed
  (fixed x–z / y–z default to the domain's centre and full length), and a section panel
  picks its own in the panel tree. Older figures' one section opens as the list's first
  ([Panels](guide/figures-panels.md)).
- **Rows × columns**: *Rows are* and *Columns are* each step through runs, sections,
  times, fields or heights (e.g. 3 runs × an x–z and a y–z section), replacing *Panels
  differ in* and *Fill a grid*; older figures open as the same panels
  ([Panels](guide/figures-panels.md#rows-and-columns)).
- **Sections labelled and drawn as they run**: an x–z or y–z section panel's x axis is
  x or y (from the storm's, or the model's), an angled or A–B one's the distance along
  it, each labelled so unless an x label is typed; a grid of rows and columns is
  labelled with column titles on the top row and a label left of each row (*Titles →
  Row … label*); a *Section line* layer draws every section, A–A′, B–B′ …; figure parts
  share their sections.
- **Sections along and across the storm motion**: they turn with the tracked motion
  at each time (or its mean over a few minutes), centred on the storm or ahead of / right
  of it ([Panels](guide/figures-panels.md)).

### The viewer

- **Linked clicks**: clicking the track's time series shows that time; clicking the
  time–height plot also moves the map to the clicked height.

## 0.4.0 (2026-10-26)

Per-layer runs, more map and section layers, 3D streamlines and a much larger figure
workspace (differences, swaths, legends, statistics, a quick start).

### The map

- **More fills** (up to three) over the first fill, each with its own field, level,
  colormap, range, opacity and colorbar, and *Clear outside range* so the fill
  underneath shows ([The map](guide/map.md#more-fills)).
- **Contours** are now a list of up to six rows, each with its own field, level, levels,
  colour and line width, in place of the two fixed contour sets.
- **Vectors** are a list of up to three rows: the wind (ground-, grid- or storm-relative),
  **horizontal vorticity** and **baroclinic generation**, each drawn as arrows or as
  **streamlines**, with a reference arrow in the vector's units.
- A **diverging colormap stays white at zero** when the range crosses zero unevenly, on
  the map, sections, time–height plots and figures.
- The fill's **Style** now sits in the fill's own pill in the toolbar.
- Numeric boxes keep what you type and tidy values to 7 significant digits.

### Cross-sections

- The section has the **same layers as the map**: a fill with its Style, more fills,
  contours and vectors. Vectors are the in-plane components (along the section and
  vertical) ([Cross-sections](guide/cross-sections.md)).

### 3D

- **Seed box on map**: start the streamlines inside a box you drag on the map.
- While a streamline is selected or pinned, the others turn grey and faint, and the
  pointer on the card's plot shows its position on each line in the scene. Streamlines
  are traced again only when something they depend on changes, so selecting, pinning and
  restyling are quick.
- The tracer takes smaller steps in strong updrafts, stops at stagnation points and ends
  exactly at the maximum length or the region's edge.
- **Vectors** at a height in the scene, a list of up to three with the same vectors as
  the map (this replaces *Surface winds*), and **Re-render when time changes** can be
  turned off ([3D](guide/3d.md)).

### Storm tracking

- New things to track: the **pressure low** (minimum p′) and **any field** (maximum or
  minimum) at a height.
- **Fix at: Centroid** puts each fix at the field-weighted centre of the area around the
  peak, for a smoother track.
- A **From / To** window replaces the direction setting: track backward by choosing an
  earlier *From* ([Storm tracking](guide/tracking.md)).

### Figures

- **Quick start** dialog the first time the Figure workspace opens, and a new-figure
  button ([Figures](guide/figures.md#the-quick-start)).
- **Open a saved figure from a list**: the quick start and *Export → Open a saved
  figure* list the figures saved in the *Figures* folder (⚙ Settings), this run's first
  ([Export](guide/figures-export.md#reopening-a-saved-figure)). A reopened figure's
  *Save as* is where it was saved.
- **Difference fills**: a fill layer minus another run or time, with a choice for runs
  on different grids.
- **Time windows**: swaths (maximum, minimum, mean or sum over a window of outputs) and
  storm-following composites.
- **Templates**: save a figure's layout and look without its runs, and apply it to
  another run. **Copy a layer's look** onto others. (Style presets are now for scripts
  only.)
- **Runs are picked per layer**, sounding, distribution and series; the Panels-tab run
  list is gone. *Layers → Runs used* holds each run's label, colour, line style and
  track, and **Fill a grid** makes panels of runs × times. A run keeps its colour in every
  panel.
- **Distributions**: bar labels (counts, percentages or values) and statistics in the
  legend or in a box. **Time series**: mark each line's maximum or minimum. **Maximum and
  minimum** of a layer in a corner of plan views, sections and time–height panels.
- **Soundings**: the hodograph inset can sit in any corner or at a chosen place, the
  hodograph view can be centred on the data, each storm-motion marker is a separate
  option, the table lists more parameters, and the layer options are split into
  Sounding panels, Skew-T and Hodograph.
- Colorbar **label and ticks can be set on the layer** that the colours belong to, and the
  thickness setting works beyond matplotlib's usual limit. The contour key and the
  matplotlib style moved to the Style tab. Settings that switch things on and off are one
  *Show* list at the foot of their section. Sections open collapsed.
- **Animations**: choose the end time and the step between outputs, with a live frame
  count; editing the figure no longer hangs while a GIF is saving.
- **Exported scripts** are short (about 55 lines plus the spec) and import their drawing
  code from `_src/<name>_draw.py`; a `my_changes()` hook takes your own matplotlib.
- Figures are drawn and saved one at a time (matplotlib's style settings are
  process-wide).
- A fix for a figure preview that drew a second, stale image under the first.
- **Legends**: a hodograph's key now joins a legend on the figure (*Style → Legend*),
  so panels with the same entries share one legend; the key has its own place, columns
  and frame (*Hodograph*); and the **Tree** tab sets one panel's legend alone (shown or
  not, where, columns, frame) for time-series, distribution and sounding panels.
  A legend on the figure now turns off every panel's own legend, also those of panels
  it does not list; *Panels' own legends* (off) does the same for a legend on a panel,
  and a panel whose Tree *Legend* is *Yes* keeps its own either way. *Anchor x, y*
  (Style and Tree) places a legend at any point, inside or outside the panel or figure.
- **Axis labels for one panel**: the **Tree** tab's *x label* and *y label* set a
  panel's own labels (blank: Style's; a space: none).
- **Tick labels on: outer panels** decides x and y apart: a range the panels share
  loses its inner tick labels even when the other differs, and inner panels drop a
  repeated axis label always (before, panels of different ranges kept everything).
- **Hodograph heights**: *Heights marked (km)* sets the heights marked along the trace
  (e.g. `0.5, 1, 3, 6`); labels read `0.5` rather than being whole kilometres only. The
  Sounding tab's *Plot style* has the same, as *Hodograph heights (km)*: its marks are
  now labelled and drawn in the height-coloured hodograph too.
- **New figure**: *Rows* and *Columns* are offered for every kind of panel but
  time–height (its grid is series × runs). Soundings and distributions go one per panel
  (more than panels: they wrap and share panels; panels left over start as a copy of
  the last). Adding or renumbering a series, sounding or distribution now only grows
  the grid, never shrinking the rows and columns you set.

### Under the hood

- The package is split into `core`, `viewer`, `figures` and `pdecomp`; the large modules
  are split into mixins and subpackages. The layout is in [Developing](developing.md).
  Figures saved by earlier versions open as before, and exported scripts do not import
  cm1view.
- Image tests compare typical figures with baselines in `tests/baseline/`
  ([Developing](developing.md#tests)).
- A new documentation site: one page per area of the viewer, a troubleshooting page, a
  page of shortcuts and a glossary.

## 0.3.0

The first tagged release: the map, soundings, storm tracking, cross-sections, 3D
isosurfaces, series, and the figure workspace with stand-alone scripts, for CM1
`output_format = 2`.
