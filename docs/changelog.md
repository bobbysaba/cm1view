# Changes

What changed in each release, newest first. The version is in `pyproject.toml`; a release
has a matching git tag.

## Unreleased (since v0.4.0)

### Figures

- **Publication 3D scenes**: a new figure kind, *3D scene (one picture)*, renders the 3D
  workspace's isosurfaces, floor, vectors and streamlines off-screen with PyVista at the
  export's DPI (smooth shading, lighting, translucent surfaces in the right order,
  transparent background possible), with matplotlib's title, legend, colorbars and axis
  ticks around it. Start one from the 3D box's photo icon in the items tray (the camera
  as you left the 3D view) or *Copy the 3D view*; camera, look and region are in
  *Layers*. Scenes animate (*Export → Animation*), the box optionally following the
  storm track and the camera orbiting. The saved script redraws it with PyVista
  ([3D scenes](guide/figures-panels.md#3d-scenes)). **New dependency: pyvista** (with
  vtk-base); run `conda env update -f environment.yml --prune` after pulling.
- **Derivatives of any field**: a **Derivative** select beside the Field (the map's
  fill; a figure's fill, contour and shading layers on plan views and cross-sections)
  plots ∂/∂z, ∂/∂x, ∂/∂y or |∇h| of it, per km (∂w/∂z in 10⁻³ s⁻¹), on the stretched
  grid ([Derivatives of any field](guide/fields.md#derivatives-of-any-field)).
  Series (the Series tab, and a figure's series and profile cards) have it too: the
  derivative is taken before the reduction, e.g. the maximum ∂w/∂z at 2 km.
- **Profiles of several runs**: a profile card's *Run* can be **All runs** or
  **Several runs…** (a line per run), with an optional ensemble band (min–max,
  percentiles or ± 1 sd) and mean or median line, and the cards have **Duplicate** and
  **One per run**. *Plot* **d/dz** draws a profile's vertical derivative
  ([Vertical profiles](guide/figures-panels.md#vertical-profiles)).
- **Edit a profile's values and draw your own**: a profile card's *Values (edit
  points)* edits or blanks levels by hand and downloads CSV; **+ Your data** draws a
  profile pasted or loaded from a file (height in km, value)
  ([Profiles: edits and your own data](guide/figures-layers.md#profiles-edits-and-your-own-data)).
  Saved profile figures open as before.
- **Edit a time series' values**: a series card's *Values (edit points)* replaces or
  blanks points by hand, per run, and downloads the line as CSV. Edits are kept in the
  figure and the edited line's legend label ends in "(edited)" (*Panels → Time and value
  axes → Mark edited lines*) ([Editing a series' values](guide/figures-layers.md#editing-a-series-values)).
- **Your own data in a time series**: *Layers → + Your data* draws a series pasted or
  loaded from a CSV file (time in minutes, value), kept in the figure
  ([Your own data](guide/figures-layers.md#your-own-data)).
- **Legend entries of your own**: *Annotate → Add: Legend entry* puts a line, marker,
  line and marker or filled box with your text in the panels' legends.
- **A blank label leaves a line out of the legend**: it showed as `_child1` before.
- **A quicker figure editor**: the browser gets far fewer widgets. Hidden settings are
  not sent until shown, nor a folded card's or section's settings until it is opened; the Layers and
  Panels tabs hold only what the figure kind uses; a tab is sent the first time it is
  opened (the panel tree is built then). A new figure keeps the layer and section cards
  it can and fills them in, so making one sends about 20–30 new widgets instead of
  about 300 (a plan view after the quick start: about 75 widgets until other tabs and
  sections are opened, 980 before).
- **Time zero per series**: each time series and time–height card has a **Time zero
  (min)**, so runs line up on a common stage (e.g. initiation at 0 min in one run and
  30 min in another) ([Time series](guide/figures-panels.md#time-series)).
- **A time series' look is on its card**: the card's **Line** style (new) and colour
  apply to its line, also in a figure of several runs (before, a panel's only series
  took its run's colour, and a run's line style came from *Runs used*). *Runs used*
  no longer has a line style. A card of several runs draws a line per run in the runs'
  colours when alone in its panel, else in its colour with a line style per run. Saved
  figures open looking as before (a one-run series takes the colour and line style it
  was drawn in).
- **No *Runs used* in time series and time–height figures**: the series cards hold all
  of it. A card around the tracked storm shows its runs' storm tracks; runs are added
  from a card's **Run** list. The legend shows a card's **Label** as it is (no run
  labels; a card of several runs adds each run's folder name, an ensemble band no
  longer adds "(mean, min–max, n runs)"), and a time–height panel's run name is the
  run's folder name. Older figures' legends change accordingly.
- Settings that don't apply are hidden again: a time-series card no longer shows the
  time–height colormap and colorbar settings (and the reverse). The same fix applies to
  *Style → Colorbar* with *Colorbars: none* and to the combine dialog's size row.
- Time–height series cards no longer offer *Vertical: At a height*, which can't make a
  time–height panel: a card there is always a layer. *Style → Colorbar* is hidden for
  time series, soundings, distributions and profiles.
- **A series you change stops computing**: changing a series (e.g. its region from
  around the storm to the whole domain) or leaving the figure stops the old series'
  computation at its next output time, so the new one starts at once (its times so far
  are kept for when it is wanted again). Joint distributions and azimuthal means over a
  time window stop the same way for a newer preview.
- **Series cards like sounding and section cards**: each card in *Layers → Series*
  starts with its **Run** and **Panel**, with **Duplicate** (a copy in a new panel) and
  **One per run**. A time-series card can also draw *All runs* or *Several runs…* (for
  an ensemble band); *One per run* splits it into a card per run in the run's colour.
  **Time–height figures** have one card per panel, like cross-sections: *One per run*
  copies a card down its column, and *Grid and size → Runs are* is gone. Older
  time–height figures open as the same panels, a card each; switching between time
  series and time–height splits or merges the cards
  ([Panels](guide/figures-panels.md#timeheight-series)).
- **Hatching and stippling**: a shading layer's *Pattern* hatches, cross-hatches or
  stipples its area ([Layers](guide/figures-layers.md)).
- **Wind barbs** on plan views, in knots or m/s, as a vector layer's *Draw as*.
- **Strip-averaged cross-sections**: *Average across* (km) averages the sections within
  a strip along the line; a *Section line* layer shows the strip.
- Reopening a saved figure says when a run's `namelist.input` changed since it was saved.
- **+ script & data** saves the script in a `scripts/` folder next to `_src/` (no longer
  beside the image); a script's path still opens the figure.
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
- **Section cards, one per panel**: cross-section figures now work like soundings.
  *Layers → Sections* has a card per panel with its run, time, section and panel number
  (*Duplicate*, *One per run*: runs × sections in a few clicks); the Panels tab keeps only
  what the figure shares, and drops the sections list and *Rows are* / *Columns are* for
  sections. A card's label is its panel's title. Older section figures open as the same
  panels, a card each; a *Section line* layer draws each section once
  ([Panels](guide/figures-panels.md#vertical-cross-sections)).

- **`cm1view render`**: draws a saved figure or a template from the command line, with
  no viewer: as saved, or for each of several runs (`--run`, as a template of it), at
  another time (`--time`), as an image, a bundle (`--bundle`) or an animated GIF
  (`--gif`), with `{run}` / `{name}` in `--out`. For batch jobs after the runs finish;
  Slurm and PBS examples in [Running on a cluster](hpc.md#figures-in-a-batch-job)
  ([Drawing figures without the viewer](guide/figures-export.md#drawing-figures-without-the-viewer)).

### The viewer

- **Live differences**: the map's fill and the cross-section's fill can be a difference
  (*Style → Difference: minus another time or run*): minus the output before, a fixed
  time, or another run at the same time (interpolated if its grid differs), drawn in
  `RdBu_r` symmetric about zero. A figure made from the map or section keeps it
  ([The map](guide/map.md#style-the-fill)).
- **Sessions**: the bookmark button in the top bar saves what the viewer shows (time,
  map view, fill with its level, style and difference, more fills, contours, vectors,
  storm motion, storm track, soundings, cross-section, 3D setup, series, distributions,
  tool and workspace) to a JSON file, and loads it back (series from their cache,
  distributions computed again);
  `?session=/path/to/file.json` opens a session (and its run) from the address.
  Saved under `<exports_dir>/<parent>_<run>/sessions` by default
  ([Sessions](guide/index.md#sessions)).
- **netCDF export**: the new *Export data* button in the top bar writes fields (native,
  derived, derivatives, column fields and sounding parameters) of the whole domain, the
  map's view or a box, at chosen times, on the model levels or at heights (the map's
  values there), to a CF-style netCDF file, one time after another, with progress and
  Stop (the file keeps the times done). `cm1view export RUN --fields ...` does the same
  from the command line or a batch job ([Exporting data](guide/index.md#exporting-data)).
- **Vorticity tendencies**: a new field group with ζ stretching (ζ ∂w/∂z), tilting
  (ξ ∂w/∂x + η ∂w/∂y), their sum, and the Okubo–Weiss parameter, in 10⁻⁴ s⁻², on the
  map, sections, 3D, series and figures
  ([Vorticity tendencies](guide/fields.md#vorticity-tendencies)).
- **Column fields**: a new 2D field group made from a layer of each column: updraft
  helicity 2–5 km and 0–1 km (∫ w ζ dz), maximum ζ 0–1 km and column maximum w, on the
  map, series, distributions and figures
  ([Column fields](guide/fields.md#column-fields)).
- **Sounding parameters**: bulk shear 0–1 and 0–6 km and storm-relative helicity 0–1
  and 0–3 km of every column (helicity relative to the tracked storm motion, else the
  domain motion), as 2D fields on the map, series, distributions and figures; and the
  CAPE, CIN and LCL height of surface-based, mixed-layer and most-unstable parcels, and
  fixed-layer STP and SCP, as the soundings compute them. Parcels are lifted in parallel
  on every n-th column (the new `column_stride` setting; auto keeps to about 250 000
  columns) ([Sounding parameters](guide/fields.md#sounding-parameters)).
- Series of horizontal divergence and baroclinic generation over a box or a disc now
  match the map at the region's edge (they were taken with one-sided differences there).
- **Linked clicks**: clicking the track's time series shows that time; clicking the
  time–height plot also moves the map to the clicked height.

### Under the hood

- A figure's data (opening its runs, reading their tracks, the panel arrays and the
  series, soundings, distributions, profiles and 3D scenes behind them, and their
  caches) is now `FigureData` in `cm1view/figures/render.py`, which needs no viewer or
  Panel: `figdraw.draw(spec, FigureData().panel_data(spec))` draws a saved spec from a
  script. The figure editor uses it. `cm1view/figures/batch.py` (`cm1view render`)
  builds on it; filling a saved figure's missing settings is `spec.with_defaults`.

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
