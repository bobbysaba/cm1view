# Changes

What changed in each release, newest first. The version is in `pyproject.toml`; a release
has a matching git tag.

## 0.5.0 (2026-11-04)

A new three-pane figure editor that replaces the old tabs, with panels of any kinds on one grid,
zoom insets, MP4 video and publication 3D scenes; also parcel trajectories, derived diagnostics,
live differences and run time alignment.

### Figures

- **A new figure editor**: three panes, a tree of what the figure holds, the preview, and an
  inspector of what is picked ([The editor](guide/figures.md#the-editor)). Where you pick says what an
  edit reaches: the figure, all panels of a kind, or one panel. It replaces the tabs and the panel
  tree, and panels of any kinds now share one grid in place of figure parts. Figures, templates and
  sessions saved earlier open in it, and figures with parts open as one grid. Exported scripts keep
  working.
- **Also new in it**: panels with an area of their own, zoom insets, a time slider on the preview,
  MP4 video, saving the figure for several runs, tables as CSV and LaTeX, a colour-vision preview,
  Find for any setting, and a mark on settings that have changed.
- **Copy a layer**: a layer's card has a copy button, for a second contour field or a fill with
  another range ([What a layer is](guide/figures-layers.md#what-a-layer-is)).
- **Undo keeps the cards**: undo and redo leave cards folded or open as they were, and cards the
  step did not change are left alone instead of being built again.
- **A gallery of saved figures**: the new-figure dialog shows saved figures as thumbnails, newest
  first, in place of a list, and a click opens one. It can also apply a template
  ([The New dialog](guide/figures.md#the-new-dialog)). Saving writes the thumbnail to
  `_src/<name>_thumb.png`.
- **Apply to this run** works straight away: it failed on a template listed when the page opened
  until you picked one from the list.
- **A figure survives a closed page**: the editor keeps the figure as you work, and the new-figure
  dialog offers *Reopen the last figure* ([Reopening](guide/figures-export.md#reopening-a-saved-figure)). Session files now hold
  the figure too.
- **One Export dialog**: *Export* above the preview holds where and how a figure is saved (save as,
  format, DPI, background, image size, script and data, download), and the preview has the room
  the bar took. The *File* tab's *Image* settings moved there.
- **Every saved figure can be reopened**: *Save* now also writes `_src/<name>_spec.json`, so a figure
  saved as an image alone appears under *Saved figures*.
- **Exact image size**: *Image size* adds *Exact width, trim the height*, so a 3.25 in figure saves
  at 3.25 in, not 3.27 in ([Image size](guide/figures-export.md#image-size)).
- **Saving waits for series**: a figure whose series are still being computed saves when they are
  done, instead of asking you to save again.
- **Style presets**: *Style → Apply a style* gives the figure the Default, AMS journal, Talk or Dark
  look in one go ([Style preset](guide/figures-style.md#style-preset)).
- **Label sizes follow the base font**: in new figures, a blank *Size* on the panel letters, time,
  height and run labels is 1.2 × the base size. Saved figures keep their sizes.
- **A figure of parts saves the same whichever part you are editing**: format, DPI, trimming,
  background and spacing now belong to the whole figure, and set in any part apply to all of
  them. Its fonts, matplotlib style and one colorbar's look come from the first part.
- **Labels fit narrow panels**: at one journal column the panel letter and time label ran into
  each other. In new figures they now shrink together to fit (*Style → Panel labels*); figures
  with room look as before, and saved figures keep their sizes.
- **Soundings keep their labels and hodograph clear**: a new sounding has its letter and time
  above the panel rather than over the barbs, and *Inset at → Auto* looks at all four corners and
  the parcel trace too, so a typical hodograph goes to the empty lower left. Saved figures keep
  their place (*Auto, top corners only*).
- **Moving things keeps what goes with them**: moving or removing a layer takes its *Tree* changes
  with it, and the contour key and *Maximum / minimum* stay on their layer. A new grid of plan views
  (another column, a run taken out of a grid of runs, ...) leaves each panel's *Tree* changes, title,
  row label, annotations, layer *In panels* and legend panels with that panel.
- **A run added again comes back as it was**: its label, time zero, colour and track, after it was
  removed or dropped for not being used.
- **The workspaces use the whole window**: every workspace stopped 100 px short of the bottom,
  which also cut off the preview's colorbar labels.
- **A table figure is as tall as its rows**, without blank height under a short table, and its
  type shrinks only when the panel it finally gets is too small.
- **One panel, no letter**: a new figure of one panel starts without a panel letter; letters
  come on with a second panel, until you set them yourself.
- **A 3D scene fills its figure**, and the *Tree* tab shows it, where it used to stop the preview.
- **Tables**: a new kind of figure, *Tables*, sets out sounding parameters and field statistics
  you pick across runs and times: rows and columns either way round, the values or their
  differences from the first run or first time. Several cards make one table
  ([Tables](guide/figures-panels.md#tables)).
- **No more gaps in a card's options**: when a choice shows another option (say *Vertical: At a
  height* showing *Height*), it now sits right beside the options around it, not one cell along.
- **Pick a run's track file from a list**: *Track file* in *Layers → Runs used* lists the
  files in your track folders, this run's first; *Type a path…* still takes any other.
- **Animations can be reopened**: *Save animation* also saves the figure's settings as
  `_src/<name>_spec.json`, so a GIF appears among the saved figures and its path opens it.
- **Colorbar labels on shared bars**: a label or ticks on any card now reach a colorbar shared
  by several panels, not only those on the first panel's card, and a figure-wide bar also
  finds them on any part. The Style tab's label and ticks are now named for what they do: bars
  with none of their own. Joint histograms get a *Colorbar label*.
- **Each sounding's own line looks**: *Own line looks* on a sounding card sets the colour,
  style and width of its temperature, dewpoint and parcel lines (say two soundings both red
  and green, one dashed).
- **Hold an entry's time in animations**: *Keep this time in animations* on sounding,
  distribution, profile, joint and azimuthal cards leaves it where it is while the rest step,
  such as t = 0 dashed under the moving time. Saved figures are unchanged.
- **Adding a layer keeps your grid**: a new series, sounding, distribution, profile, joint
  distribution or azimuthal mean goes in an empty panel of the rows and columns you set, or
  with the last card when they are full, instead of always in a new panel. A grid that grew
  for a card goes back to your rows and columns when the card moves back or is removed.
- **Y range for one time-series panel** ([Time series](guide/figures-panels.md#time-series)):
  the **Tree** tab sets a panel's own *y from* and *y to* for its left axis. Blank boxes use
  the figure's values from *Layers → Plot*. Saved figures are unchanged.
- **Tidier cards and sections**: cards now run where (run, time, panel), what, look, extras.
  Panels are picked and shown by letter on every card; *In panels*, annotations and the
  legend's *From panels* take letters or numbers. *Duplicate* is on sounding, distribution,
  joint and azimuthal cards too. A fill's *Difference*, *Ensemble* and *Time window* fold away
  and open when in use. In *Style → Panel labels* each label is one row with its checkbox first,
  and a switch that reveals settings now sits above or beside them (contour key, maximum and
  minimum, grid lines, line labels, hodograph heights and key). Saved figures are unchanged.
- **Panels that differ in field use full fill cards**: *Panels → Time and fields* has a folded
  fill card per row, column or panel, the same as a fill in *Layers*. Each panel's fill can now
  set its scale, colour steps, opacity, blanking, reverse, derivative, difference, ensemble and
  time window. In a grid of fields × heights a new fill now follows its column's height, unless
  *Own height* is ticked. Saved figures open and draw as before.
- **One legend block**: every kind of panel's legend (shown or not, where, columns, frame) is
  now set in *Style → Legend*, showing only what reaches the kind of panel in the figure.
  The separate copies in each kind's *Plot* section are gone. Saved figures are unchanged.
- **Clearer wording in the figure editor**: one name for one thing across the cards
  (*Colour*, *Colormap*, *Reverse*, *Start from white*, *Colorbar arrows*, *Colour steps*,
  *Line style*, *Legend text*). On cards, the layer read is now *Read from* / *Read to*, and
  the height axis's range *Axis from* / *Axis to*; *Plot* on series and profile cards is now
  *Then apply*. The sounding layout is *Sounding layout*. Long hints fold after their first
  sentence: click to read the rest. Saved figures are unchanged.
- **The Style tab shows what applies** ([Style](guide/figures-style.md#style)): settings
  that change nothing for a figure kind are hidden, such as *Colorbar* on joint and azimuthal
  panels, *Contour key* away from maps, and axis labels and grid on a 3D scene. Saved
  figures are unchanged.
- **One home for each setting**: a time series' or time–height figure's axes, legend and
  marks are now in *Layers → Plot* (they were in *Panels*); a section figure's *Top* and x
  axis sit above its cards in *Layers*; panel title position and bold are in *Style → Panel
  labels*; the *Export* tab is now *File*. Time zero is set per run in *Layers → Runs used*:
  the *Minutes counted from* box and the series cards' *Time zero* appear only in figures
  that use them, and still count there. Series cards no longer edit storm tracks: they say
  what each run's track gives and point to *Runs used*. Saved figures are unchanged.
- **Time zero per run** ([Runs](guide/figures-panels.md#runs)): plan views and
  cross-sections of several runs line up by time since each run's time zero, including
  their time labels, differences and ensembles. A time picked for a run stays its model
  time; figures saved before are unchanged. New time label text `{model}`: model minutes.
  Time series and time–height panels (parcel series too) count each run's times from it,
  on top of the figure's and the card's, so a card of several runs and its ensemble band
  line up. *Runs used* now shows on those figures. A profile card of several runs reads each
  run at the matching time, and says when a run has no output there. Cards with their own
  time (soundings, distributions, profiles, joint distributions, azimuthal means) move
  with a time zero and with a new run, as section cards do. Time labels (3D scenes too) and
  automatic legends count from the time zero.
- **Line runs up by output number** ([Runs](guide/figures-panels.md#runs)): a figure's runs
  can pair by their nth output instead of by time zero. The first run's times label the panels
  and time axes; past a shorter run's end its panels are blank.
- **Custom grid for figure parts**
  ([Figure parts](guide/figures-panels.md#custom-grid)): besides side by side and stacked,
  parts can go anywhere on a grid of rows and columns, each spanning as many cells as it
  needs, e.g. a plan view on the left with a cross-section above a sounding on its right.
  A map in the editor shows where the parts are. Figures saved before keep their layout.

### Parcels

- **Parcel trajectories** ([Parcels](guide/parcels.md)): runs with CM1 parcel output
  (`cm1out_pdata.nc`; new setting `parcel_glob`; several files, e.g. one per restart,
  are joined by time) get a **Parcels** tool. Click the map to choose the parcels near a
  point, or drag a box, limited by height, by a value range of a parcel variable and by
  a cap (every n-th or a random sample), at the shown time or the first parcel time.
  Each choice is a named set, drawn as trajectories coloured by height, by any parcel
  variable or in the set's colour, with tails over all parcel times, up to the shown
  time or the last minutes, and heads at the shown time. Parcel times are their own
  axis: heads are interpolated between them when the 3D output is coarser. Sets can be
  saved, loaded, renamed and removed (also from the items tray) and are kept in
  sessions. Parcels that wrap across a periodic boundary are not joined across the
  domain; parcels that leave an open domain stop there. The demo run `supercell` now
  has parcels, written every 60 s. Reading, selection and caching are in
  `cm1view/core/parcels.py`, usable without the viewer.
- **Parcels on cross-sections, in 3D and in a plot** ([Parcels](guide/parcels.md)): the
  parcels within a distance of a cross-section's line are drawn on it, projected (the
  parts of their tails near it, or the whole tails of those near it now), at the
  section's time; the sets' tails and heads are drawn in the 3D view inside its region.
  The Parcels panel plots a parcel variable over the parcel times (each parcel, the mean
  or median, and a band) or two variables against each other at the shown time.
- **Parcels in figures** ([Parcels](guide/parcels.md#in-figures)): plan-view and
  cross-section figures have a *Parcels* layer (tails up to each panel's time and heads
  there, in the set's colour or coloured by a parcel variable, with its own colorbar
  when the panel has no fill). *From the map* and *From the cross-section* bring the
  viewer's sets along, drawn as the viewer draws them. A layer keeps the rule that chose
  its set and chooses the parcels again when drawn, so saved figures, templates,
  animations, `cm1view-render` and exported scripts all carry them.
- **Parcels in 3D scene figures** ([Parcels](guide/parcels.md#in-figures)): a 3D scene
  draws parcel sets as lines with balls at the scene's time, inside its region, in the
  set's colour or coloured by a parcel variable (with a colorbar). *Copy the 3D view*
  brings the sets the 3D view shows. Restyling the parcels or changing the sets does not
  recompute the isosurfaces.
- **Parcel series** ([Parcels](guide/parcels.md#parcel-series)): time-series figures
  draw a parcel set's variable over the parcel times (**+ Parcels**): mean or median,
  a band over the parcels (min–max, percentiles or ± 1 sd) and, if you like, some
  parcels' own lines; *d/dt along the parcel* gives e.g. Dw/Dt. They share panels and
  y axes with computed series and your own data.
- **3D fields at the parcels** ([Parcels](guide/parcels.md#3d-fields-at-the-parcels)):
  parcels can be coloured and plotted by any 3D field of the run, native or derived,
  sampled at their positions (trilinear in space, linear in time between the 3D outputs
  around each parcel time), in the viewer and in figures (parcel layers, 3D scenes and
  parcel series). Sampled once per set and field, then cached; in specs and scripts
  `@<field>`, e.g. `@thpert`.
- **Export a parcel set** ([Parcels](guide/parcels.md#exporting-a-set)): *Export set*
  writes a set's trajectories (any parcel variables and 3D fields at the parcels; all
  parcel times, up to the shown time or the last minutes) to netCDF (`(time, parcel)`
  arrays) or CSV (one row per parcel and time), in the background with Stop.
  `cm1view export RUN --parcels SET` does it for a saved set without the viewer.
- **Parcels relative to the storm** ([Parcels](guide/parcels.md#relative-to-the-storm)):
  *Seen from* draws the tails in a frame moving with the tracked storm or at a set
  motion, the same as the grid at the shown time (heads stay where they are), on the
  map, the cross-section and in the 3D view; figures' parcel layers and 3D scenes have
  it too. Exports can add storm-relative `x_sr`, `y_sr` (`--relative MIN` on the
  command line).
- **Lagrangian w budget** ([Parcels](guide/parcels.md#the-w-budget)): with *w*, *b* and
  *vpg* in the parcel output, two parcel variables computed along the trajectories,
  *Dw/Dt* (`dwdt`, from the parcel's own w) and *Dw/Dt − b − vpg* (`wres`, mixing and
  the rest), wherever parcel variables go (colour, plots, figures, export). The
  Parcels plot has a *w budget* view of the picked set, rates or integrated since the
  set's time (Δw = ∫b + ∫vpg + ∫rest). Parcel series cards plot a variable's change or
  time integral since the set's time; **+ w budget** adds the four terms as a panel.
  The demo's parcels have *vpg* now.

### Figures

- **More figures animate**: soundings (skew-T and hodograph), distributions, profiles,
  joint distributions and azimuthal means can be saved as animated GIFs (*Export →
  Animation*, `cm1view render --gif`) on their own, not only as a part of a figure with
  a plan view or section. Their axes and shading, and a hodograph centred on *fit*, use
  one range for all frames unless you set limits. In every animation, the frames now
  stop while a profile's every run has output and a time window is still whole.
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
- **CF-style output**: runs whose files use the CF-style names of newer CM1 versions
  (dimensions `xh`/`xf`, `yh`/`yf`, `zh`/`zf`, heights in `zh`) now open; before, they
  failed for want of `z`. `python -m cm1view.demo --cf` writes the demo that way.

### Under the hood

- A figure's data (opening its runs, reading their tracks, the panel arrays and the
  series, soundings, distributions, profiles and 3D scenes behind them, and their
  caches) is now `FigureData` in `cm1view/figures/render.py`, which needs no viewer or
  Panel: `figdraw.draw(spec, FigureData().panel_data(spec))` draws a saved spec from a
  script. The figure editor uses it. `cm1view/figures/batch.py` (`cm1view render`)
  builds on it; filling a saved figure's missing settings is `spec.with_defaults`.
- What differs between the kinds of panel is one table, `cm1view/figures/kinds.py`. The
  cards build their region, heights, look, colours, ensemble and buttons from shared parts
  in `cards/base.py`, and the widgets that redraw the preview register as they are made.
  The editor looks and works as before.

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
