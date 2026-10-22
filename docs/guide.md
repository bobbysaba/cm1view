# Using cm1view

The top bar holds what every view shares: the **Map | 3D | Figure** workspaces, the
run (click its name to open another) and ⚙ settings, the **storm track**, and the time
controls.

**Storm track** (top bar). Storm-relative soundings, the tracked storm motion, series
around the storm, storm-relative vorticity and figures centred on the storm all use it.
The chip says how many fixes there are and turns amber when the shown time has none.
Without a track it offers the run's track file when one is found (`track_dirs` /
`track_patterns`): one click loads it. Clicking it otherwise opens the Track tool.

**Map workspace.** The toolbar above the map always shows the fill field and its
level (height km AGL, model level, or column max/min). Each pill opens its controls in a
drawer under the toolbar. Click the pill again to close it.
- *Style*: pixels or filled contours, colormap, range, opacity.
- *Contours A / B*, *Winds*: the checkbox turns the layer on or off. The pill
  shows what is drawn. Winds are drawn as arrows or as streamlines (*Draw as*; the
  density slider sets how close the streamlines are), ground-, grid- or storm-relative.

Zooming re-renders at full resolution for the area in view.

**Tools** (down the left edge): *Sounding*, *Section*, *Track*, *Series*, *Distribution*
and *3D box*.
A tool sets what a click on the map does and opens its panel to the right of the map.
Pressing the lit tool again switches it off. The panel's ✕ closes the panel but leaves
the tool on (its button reopens it), and ⤢ gives the panel the whole window; **Map**
brings the map back. *Clear* removes every marker from the map. Less-used options in the
Sounding and Track panels sit behind the settings button (sliders icon).

**Items** (the row under the map): what you have made. *Map view*, the soundings, the
section, the 3D box and the computed series. Click an item to open its panel; ✕ removes
it, and the picture button makes a figure from it in the Figure workspace (the box's cube
opens it in 3D).

**Zooming soundings.** Click the skew-T/hodograph or the profile panels to expand the
panel. All sounding controls stay available. In the expanded view, drag a box on the
skew-T, the hodograph or a profile panel: the figure is redrawn with that panel's axes
limits (temperature / pressure, u / v, value / height), so axes, labels and line widths
stay intact (zoomed skew-Ts fill their panel; barbs and labels follow the zoom). −
widens the view, double-click or ⟲ returns to the full view, ⤓ saves the image (SVG).
The zoom is kept while the sounding updates (e.g. stepping in time); switching m/s ↔ kt
or the profile top resets the affected panels.
In the expanded view, hovering reads values off the graphics in a strip under each
image. On the skew-T it shows the pressure and the temperature under the pointer, and
each sounding's height, T, Td, parcel T, RH, θ, θe, qv and wind at that pressure. On the
hodograph it shows the level nearest the pointer (height, wind). On the profile panels
it shows every quantity at the pointer's height. A dashed line or dot marks the
position read.

**Plot style** (palette button in the Sounding panel): colours of temperature, dewpoint, parcel and
base state; widths of the T/Td, parcel, hodograph and profile lines; skew-T top and
temperature range; hodograph ring spacing and top; CAPE/CIN shading, wind barbs and
adiabats on or off. Changes only redraw (no new analysis). *Default style* resets them.

**Level units.** In the parameter table, click the units cell (m ⇄) of a level row
(LCL, LFC, EL, MU parcel, freezing level, effective inflow) to show it in hPa; click
again for metres. The choice stays while the soundings update. The
**Profile panels … km AGL** selector just above the profile panels sets their height
range. It does not change the skew-T.

**What each tool does on the map:**
- *Sounding*, *Click a point*: click to get a sounding; Shift-click adds up to 4 for
  comparison.
  This shows a skew-T, a hodograph, SB/ML/MU parcels, shear, SRH, the effective inflow
  layer, STP/SCP, critical angle, and profiles of storm-relative wind, shear,
  streamwise/crosswise vorticity, cumulative SRH and θ/θe. The base state is shown
  dashed for reference. *Column average* gives box-mean soundings.
- *Sounding*, *Drag a box (area mean)*: drag a box to get the sounding averaged over it;
  Shift-drag adds a box (up to 4, mixed freely with point soundings). The box is drawn
  on the map.
- *Section*: click A then B. A and B are marked at the ends of the distance axis.
- *Track*: click a storm to follow it through time (see below).
- *Series*: no clicks; choose a field and a region in its panel (see below).
- *Distribution*: no clicks; choose a field and a region in its panel (see below).
- *3D box*: drag a box. The app switches to the 3D workspace and renders it. The 3D
  workspace can also be opened first: *Pick region on map* or *Use map view* there.

**Comparing times.** *📌 Pin this time* freezes sounding 1 at the current time. Sounding 1
keeps following the time slider, so moving the slider overlays the two times (up to 4
soundings in all). Pinning with nothing shown pins the domain mean. To compare the
environment *relative to the storm* over time, make a track first. Then tick *Move with
tracked storm* and click: the sounding keeps its offset from the meso (e.g. 10 km into the
inflow) as time changes, and pinning it compares the same storm-relative spot at two
times. *Storm motion → Tracked meso motion* uses the track's motion at each sounding's
time for SRH, storm-relative winds and the hodograph.

**Storm tracking** (Track tool). The default tracks the maximum of w at 1 km after a Gaussian smoothing of σ = 3 grid
points. Clicking snaps to the maximum of the smoothed field within the
search radius; *Find strongest* starts from the domain-wide maximum instead. The track
then steps through the output times: at each step it extrapolates the last motion and
takes the maximum within the radius. With *Prefer nearest core* (default) the field is
first weighted by a Gaussian of distance from the expected position (σ = radius/2). That
keeps the track from hopping to a neighbouring, slightly stronger updraft. *Search whole
domain each time* takes the domain-wide maximum at every time (it can jump between
storms). It stops
when the maximum drops below *Stop below* (leave it empty to never stop), or at the end of
the *From*–*To* window. By default the window runs from the clicked time to the end of the
run. Set *From* to an earlier time to track backward as well, or pick any other first and
last time.
Other tracked fields (⚙ Settings): ζ at a height, instantaneous 2–5 km updraft helicity
(Σ w ζ Δz, from `winterp` and `zvort`), the pressure low (minimum p′ at a height; stops
when p′ rises above *Stop above*), or *Other field*: the maximum or minimum of any field
at a height. Choosing one loads its default height, smoothing (Gaussian or box) and stop
value. *Fix at: Centroid* puts each fix at the field-weighted centre of the area around
the extreme where the smoothed field is beyond *Centroid cutoff* (% of the way from 0 to
the extreme). This gives a smoother track than the single peak point. Tracking costs
about a second per time for a field at one height, and a few seconds for UH.
- Clicking near an existing track at another time corrects it from that time on (or
  backward, if before the start), keeping the rest. Clicking far away starts a new track.
- *Place by hand* (Track panel): each click sets the fix at the shown time to exactly where
  you click. Tick *Snap click to max* to snap it to the nearby maximum instead. *Step time
  after each click* advances the slider so you can click through the storm's life. Each
  hand fix still records the tracked value at that spot. *Delete fix at this time*
  removes a fix. Hand fixes and auto-tracking can be mixed: an auto-track click near the
  track continues from there and keeps the earlier fixes.
- *Load* reads a track from the path box. It accepts a CSV or whitespace-separated file
  with `x_km, y_km` (grid) or `x_ground_km, y_ground_km`, plus one of `time_s`,
  `time_hms` or `time_index`. Times are matched to the run's output times.
- The `source` column records how each fix was made: auto, manual or loaded.
- *Save* writes the track on the server: `.csv` gives comma-separated columns, any other
  extension gives aligned columns. *Download* sends the same file to the browser. Header
  lines start with `#` (`pandas.read_csv(path, comment="#")`). Columns: time index, file,
  time, grid-relative and ground-relative position (km), ground-relative motion (m/s),
  the tracked value, and for UH the max w and ζ in the 2–5 km layer.

**3D workspace.** Pills for *Isosurfaces* (up to 4), *Surface winds* (horizontal arrows
at a chosen height), *Streamlines* and *Scene* (top, exaggeration, smoothing,
resolution, reflectivity floor).
- Streamlines are instantaneous, traced forward, backward or both ways through (u, v, w) from an n × n seed
  grid at a chosen height. They can be ground-, grid- or storm-relative and coloured by
  height or w. Storm-relative uses the storm motion selected in the sounding panel.
- Click a streamline to select it (it turns yellow, its seed marked). A card plots a
  field along it against distance from the seed (negative = upstream), with height on
  the right axis. Its axes fit the field. Scroll to zoom, drag to pan, and use the
  toolbar for box zoom or reset; ⤢ enlarges the card. The field can be any 3D field, the speed, or the streamwise vorticity in
  the streamline's frame. The selection follows the same seed when the scene re-renders
  (e.g. in time). Isosurfaces in front of a line can catch the click: lower their
  opacity or switch them off.
- To compare streamlines, press the pin on the card: the line keeps a colour of its own
  (in the scene, with its seed, and on the card, its height dashed) and the next click
  selects another. Pin as many as you like; the card plots them all, each against
  distance from its own seed, and lists them as #1, #2, …. Click a pinned line to
  select it again and press the pin to unpin it. Pins follow their seeds through
  re-renders (a pin whose seed is not in the new scene is counted as "not in this
  scene" and comes back when it is). × clears the selection and every pin.
- Once a scene is shown, changing a 3D control re-renders it.

**Series** (tool and panel). One field reduced over a region at every output time:
any native or derived field, at a height or over a layer (a layer also keeps every
level, for the *Time–height* view), over the whole domain, the map view, the 3D box or
a disc around the tracked storm (with an offset, e.g. the inflow), as min / max / mean /
percentile. Results are cached in `<cache_dir>/series` per run and recipe, and
saved as .nc (everything), .csv / .txt or .pkl. Series in other units than the first
get their own y axis on the right. Click a plot to go to that time. **Plot** sets
the time and y limits (heights in the time–height view) and the time–height
colormap and colour range. For layer series it can also reduce over a sub-layer
(e.g. max w over 0–2 km out of a 0–10 km layer) for min / max / mean. All of these
come from the computed result without recomputing. *Auto limits* clears them. The
3D region box is offered as a region once one has been drawn.

**Distribution** (tool and panel). Every value of one field at the shown time: at a
height, over a layer or over the whole depth, in the whole domain, the map view, the 3D
box or a disc around the tracked storm, optionally only values in a range (e.g. w ≥
1 m/s for updrafts). Compute again at other times, heights, fields or regions to
compare them: they are drawn together as histograms (count, PDF or fraction per bin,
in shared bins), box plots (whiskers at 1.5 × IQR, min–max, 5–95 % or 1–99 %; the
diamond is the mean), violins or cumulative distributions (fraction at or below x, or
above x for the tails; log scale for both). A table gives each one's count, mean,
standard deviation, extremes, median and 1st / 99th percentiles. The plots come from a
summary of each distribution (a 4000-bin histogram of every value from its minimum to
its maximum, and its quantiles), so changing the plot reads nothing again. *Follow the
time slider* computes the chosen one again when the time settles. *Figure of these*
opens them as a figure (Figure workspace), drawn the same way.

**Figure workspace** (Map | 3D | **Figure**). Publication figures, previewed at their
final size. *New figure from* the map view, the cross-section, the series, the
soundings, the distributions or a time grid; every change can be undone (↶ ↷ above the preview; adding,
removing and changing figure parts too), and
*Actual size* shows the figure as large as it prints, to judge the font sizes. Saving
sits above the preview: *Save as* (folder/name), format, DPI, *Save*, *+ script & data*
and *Download*. The editor has five tabs of folding sections:

- **Panels**: what the panels show and the grid and size (size presets by width; the
  height follows the panels until you type a size, *Fit height* makes it follow
  again), the time of each panel (any cell can stay empty), the titles of the figure
  and of each panel, the area or section, and the **Runs** the panels can come from.
  The time lists offer the outputs of the panels' run (in a runs × times grid, of every
  run, marked where a run has none), so runs with different output intervals work
  together. Every *Run* list also offers runs not yet in the figure (your recent runs,
  the runs next to this one and those under *Where your runs live*): picking one adds
  it, with its storm track. In **Runs**, the same list finds a run to add by filtering
  or by pasting a folder (the runs under *Where your runs live* are found in the
  background, and join the lists when the search is done). Each run has a label, a
  colour and a line style and a storm track; the colour is the default for its time
  series, its storm track layers, its run name in the panels and, when each sounding
  of a panel comes from another run, its soundings and distributions. Removing a run
  takes its panels, soundings and distributions with it; those of
  the runs after it stay on their runs. The field lists hold the fields of every run.
  *Panels show*:
  - *Plan views* / *Vertical cross-sections*: panels in time, in field, at several
    heights or model levels (plan views: e.g. 1, 3 and 6 km, or levels 5, 10 and 20;
    a layer can keep its own height; *Style → Panel labels → Height label* names each
    panel's height or level), as a runs × times grid or each with its own run and
    time; centred on each run's tracked storm, a fixed box or the whole domain.
  - *Time–height (series)*: a row per series and a column per run, one colorbar per row; a series can be plotted as its d/dz or d/dt.
  - *Time series*: series with the same panel number share a panel; series in other
    units get their own y axis; one series from several runs is coloured by run. A
    series' *Runs* list also offers runs not in the figure (picking one adds it).
  - *Soundings*: skew-T log-p with adiabats, parcel and barbs, and a hodograph: as an
    inset, side by side with the skew-T, or alone (or no hodograph). The hodograph
    marks the Bunkers right and left movers, the 0–6 km mean wind, the heights along
    the trace (labels that would overlap on a short hodograph move aside) and, with a
    ring, the storm motion chosen for the SRH: Bunkers right or left mover, the 0–6 km
    mean wind or a custom motion (one sounding: dotted lines show the storm-relative
    inflow and the 0–500 m shear, as in the Sounding tab). The SRH shading, legend and
    parameter table use that motion. A hodograph of its own adds a key of the height
    colours and optional 0–1 or 0–3 km SRH shading; the inset sits in the upper right,
    the upper left, or (*Auto*) the top corner the temperature and dewpoint traces
    cross least. A parameter table under each panel can list CAPE, CIN, LCL, SRH,
    shear, STP and SCP, a row per sounding. Several soundings (runs, times,
    storm-relative spots) per panel.
  - *Distributions*: histograms (counts, PDF or fractions; bins by number or width;
    filled outlines, outlines or bars), box plots, violins or cumulative
    distributions, of any field at a height, over a layer or the whole depth, in the
    whole domain, a box or around each run's track, with an optional value range.
    Each has its own run and time; those with the same panel number share a panel
    (e.g. w at two times, or two runs), coloured by run when each is from another
    run. *Mean, sd, n in legend* adds the statistics.
  - **Figure parts** (top of Panels): a figure can have parts with different kinds of
    panels, e.g. plan views beside soundings, or a plan view with its A–B line above
    the cross-section. Each part has its own panels, runs, layers and style, and keeps
    its own size; the parts are side by side or stacked, and the panel letters run on
    from part to part. Edit one part at a time (*Figure parts* picks it; *New figure
    from* then makes the part anew). The whole figure can be given a width and height
    (the parts then share it by their sizes), each part a share of it (0–1), and the
    figure one colorbar for all its parts.
- **Layers**: fill (colormap, range, steps, linear / log scale, opacity, blanking,
  colorbar arrows and label), contours (levels, labels and their format), shading,
  vectors or streamlines, storm track and section line; the series of time–height and
  time-series figures; the soundings and skew-T settings; the distributions and how
  they are drawn. A fill can be a **difference**: *Difference: minus another run or
  time* subtracts the same field at another run and/or time (blank: the layer's own)
  and switches to a red–blue colormap centred on 0. When the two grids differ the
  panel says so; pick *Interpolate onto this layer's grid* or *Refuse* under
  *If the grids differ*. A fixed Minus time stays put in animations.
  A fill, contour or shading layer on a plan panel can cover a **time window**
  (*Over a time window*): the maximum (a swath, e.g. of updraft helicity), minimum,
  mean or sum over the outputs *From*–*To* (blank: the run's first output, the panel's
  time; *Every nth output* thins them), placed where the ground is at the panel time
  (the grid moves with umove, vmove); or a *storm-following mean* (composite) in the
  box that moves with the tracked storm (needs a track). Results are kept in the cache
  folder (Settings), so redrawing or restyling reads nothing again.
  *Copy a layer's look* puts one layer's colours, lines, style and colorbar onto others
  of its kind (its range, levels and labels too when they show the same field).
- **Style**: *Presets* set the text, frame, background, width and export at once:
  *AMS journal* (8 pt sans-serif, (a) letters, 3.2 in wide for one column, else 6.5 in;
  PDF at 600 DPI), *Talk* (large text, 10 in wide) and *Talk, dark* (on black; Undo
  takes a preset back). *matplotlib style* takes a style name (e.g. `dark_background`)
  or a `.mplstyle` file for colours and lines; the fonts and sizes stay the editor's.
  Then fonts (family, math / units font, sizes of tick labels, axis labels,
  titles and legends), axes and ticks (labels, tick spacing and direction, minor ticks,
  grid lines, frame width, equal scale), panel labels (letters, times and run names,
  in a corner, on a white box or above the panel), colorbars (one for the figure, per
  row, column or panel; where, length, thickness, label, ticks and their sizes),
  the legend and the spacing between panels.
- **Annotate**: text, markers, arrows, lines, boxes and circles, and a contour key
  (nested circles). They can also be placed by clicking the preview (the *Click …*
  list above it; in a skew-T, at a temperature and pressure), as can a section's A and
  B in a plan view; for two-point items a drag from one point to the other does both.
  *Drag: move an annotation* moves one (from its text, marker, centre or middle; from
  an end, that end), and *Drag a box: plan-view area* sets the plan views' area.
  *Your own code*: Python
  run after the figure is drawn, with `fig`, `axs` (by panel), `data`, `spec`, `np`
  and `matplotlib`, for anything the editor has no setting for; it is saved with the
  figure and runs in its script too. Code in a figure you open runs only once you tick
  *Run the code*. The code box highlights Python; the editor is loaded by the browser
  from a CDN, so where the browser has no internet tick *Plain text box*.
- **Export**: trimming, margin and a black or transparent background; animations;
  reopen a saved figure (its image, script or `_spec.json`) to keep editing.
  *Templates*: *Save as template* keeps the figure's panels, layers and look without its
  runs, in `templates/` next to the settings file; *Apply to this run* opens it on the
  run shown, its times moved to the map's time and as far apart as they were (each at
  the nearest output; panels past the run's end stay empty). What only another run had
  (its soundings, a difference from it) is left out.

**Animations** (Export → *Animation (GIF)*). Plan-view and cross-section figures can be
saved as animated GIFs, and so can figures of parts with at least one part of them:
every part steps together (soundings too; time–height and time-series parts stay as
they are). Each frame redraws the figure exactly as it is set up, a few
outputs later: every panel steps forward together, and storm-centred panels and sections
follow the storm. Set the number of frames, how many outputs each frame steps
(*Every … outputs*), the frame rate, the DPI (keep it low: a GIF grows quickly with its
size) and whether it loops. The animation is saved as `<Save as>.gif`, and with *Also
save the frames* each frame is saved too, as `<Save as>_frames/<name>_000.png`, … (to
make a video, e.g. `ffmpeg -framerate 4 -i name_%03d.png -pix_fmt yuv420p name.mp4`). It
stops early at the last time every panel has output; *Stop* abandons it. A single panel
(1 × 1) is the usual choice, but any grid works: a 1 × 2 figure of two runs makes a
side-by-side loop.

Runs have their own storm track (the Track tool, or `storm_tracks/<run>.csv`, found
automatically; see `track_dirs` / `track_patterns`). *+ script & data* also saves a
stand-alone script with the plotted arrays and spec: the script redraws the identical
image without the viewer. The image and script sit side by side, the arrays and spec in
`_src/` next to them; the script finds them relative to itself, so the folder can be
moved or copied. The spec and the script's header record the cm1view version and, from
a git checkout, its commit, and a hash (sha256) of each run's `namelist.input`; the spec
also records the settings that change what a figure shows (`output_glob`,
`track_dirs`, `track_patterns`, `pdecomp_script`).

**Switching runs.** Click the run name in the header. You can type a directory, pick
one of the runs next to the current one (*Runs here*), browse with *Folders* (↑ .. goes
up, a click opens a folder; ● marks folders with CM1 output), or pick a recent run. This reloads the page
with `?run=/path`. Open runs share one 3D cache (`--cache-gb`); the least recently used
fields are freed first, so tabs on different runs do not empty each other's cache.

**Performance.** CM1 stores each 3D field one horizontal level per chunk. Plan views
are therefore instant, but anything that needs whole columns (soundings, sections, 3D)
must read the full 3D field once per time: about 2.5 s per field per CPU. Those fields
stay cached, so every later click at that time is instant. The first sounding at a new
time loads 5 fields (th, prs, qv, uinterp, vinterp).

## Notes on the fields

- CM1 writes winds relative to the moving grid. `umove`/`vmove` are read from
  `namelist.input` in the run directory and added back for ground-relative
  winds, hodographs and storm motions.
- Parcel calculations are pseudoadiabatic with a virtual-temperature correction.
  They were checked against MetPy: CAPE agrees within about 3%.
- Derived fields: θ′, p′, buoyancy (θρ′ including hydrometeor loading), θρ and θρ′
  θe, T, Td, RH, wind speed, horizontal divergence, horizontal
  vorticity, streamwise and crosswise horizontal vorticity, cloud/precip condensate.
- Streamwise / crosswise vorticity are relative to the tracked storm motion at that time
  when a track has a fix there, otherwise to the domain motion (umove, vmove). The map
  title, colorbar, section title, 3D legend and streamline card say which was used.
  Crosswise is positive to the left of the storm-relative wind.
- **Pressure decomposition** (field group of that name): p_b, p_l, p_nl, the matching
  accelerations acc_b (B − ∂p_b/∂z/ρ), acc_l, acc_nl, plus p_l + p_nl, acc_l + acc_nl
  and the total. Where post-processing wrote them into the output files they are read
  from there (any file subset; the map title says which version wrote them, and warns
  for files written by early versions without a `pdecomp_version` tag). Elsewhere, a
  *Compute pressure decomposition* button computes that time in a separate process with
  cm1view's solver (`cm1view/pdecomp_solver.py`). Each part solves the anelastic pressure
  equation, `cp [H ∂²π/∂x² + H ∂²π/∂y² + ∂/∂z(H ∂π/∂z)] = F` with `H = θv0 ρ0`, by a
  horizontal FFT (periodic lateral boundaries, `ebc = 1`) or cosine transform (open
  ones) and a tridiagonal solve in the vertical that is conservative on the stretched
  grid. The forcings are ∂(ρ0 B)/∂z for p_b and −2 ρ0 (∂U0/∂z ∂w/∂x + ∂V0/∂z ∂w/∂y)
  for p_l. p_nl is the residual (total p′ − p_b − p_l). The horizontal grid must be
  uniform.

  The inputs are read in parallel first, and the solver uses every CPU of the job:
  ~25–35 s with 4 CPUs (~80 s on one) for a 1280 × 1280 × 115 grid, which needs about
  30–40 GB of free memory (less for smaller grids, in proportion). If the job lacks the
  memory, the 3D cache is emptied first; if still short, it says so.

  *Write into the output file* (offered when `allow_writes_to_output` is on) writes the
  result into the output file (float64, with a `pdecomp_version` attribute; about +40 s
  and +9 GB per file for a 1280 × 1280 × 115 grid), replacing older values. While it
  writes, the viewer releases that one file and reports it as busy. If the job is killed
  during a write, the file can be left damaged. Unticked, the result is kept in memory
  only. The last 2 computed times stay in memory either way. For files written by early
  versions the button offers *Recompute … and overwrite*.

  The solver also works on its own, outside the viewer (its docstring shows how). To
  use another solver, point the `pdecomp_script` setting (or `--pdecomp-script`,
  `$CM1VIEW_PDECOMP_SCRIPT`) at a Python file with the same functions: `lbc_type`,
  `domain_info`, `compute_base_state`, `setup_pressure_solver`, `pressure_decomposition`
  (returning a dict with `p_b`, `p_l`, `p_nl`, `acc_b`, `acc_l`, `acc_nl`, each shaped
  like a 3D field) and `write_data`, and a module-level `nc` (`import netCDF4 as nc`)
  that it opens files with.

Other derived fields are defined in `cm1view/fields.py` (`_make_fields`); see
[Developing](developing.md).
