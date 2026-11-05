# Figure panels

The tree says what the figure holds. The **Figure** node has the grid and size, a kind's node what
its panels share, and each panel where it sits, its type, and its run and time. The layers drawn
in them are in [Figure layers](figures-layers.md).

## Layout and size

A figure is one grid of panels, and panels of any kinds can share it: plan views beside soundings,
or a plan view with a cross-section under it. On the **Figure** node:

- **Rows**, **Columns**: any size. Making the grid smaller moves panels into free cells; those
  with no room are set aside, not drawn, and kept with the figure until there is room (*Bring back*
  or *Remove*).
- **Column widths**, **Row heights**: shares of the figure, such as `2, 1` (blank: equal). The map
  under them shows where the panels sit.
- **Figure type** changes every panel to another type, each staying in its cell at its run and
  time; **Panel type**, on a panel, changes that one. What they showed is replaced, and Undo takes
  it back.
- **Add a panel of** a type, in a free cell or a new row or column. **Fill empty cells** puts one in
  every free cell.
- The **size**: presets by width (3.25 in one journal column, 5, 6.5 full page, 7.5, a 13.3 × 7.5 in
  slide) or your own. The height follows the panels until you type a size; **Fit height** makes it
  follow again. A figure of several kinds has no automatic size, so set it by hand.
- The figure's **title**.

On a **panel**:

- **Row**, **Column**, **Rows tall**, **Columns wide**: the cell it sits in and what it spans, so a
  plan view can run down the left beside a cross-section above a sounding.
- **Copy this panel** and **Remove this panel**.
- Its **title**, a **row label** at the left, and its own run and time. The time lists offer the
  output times of the panel's run. An empty cell draws nothing.
- **+ Zoom inset** (plan views and cross-sections): a box in the panel showing part of it larger,
  with lines to where that is.

## Panel kinds

### Plan views

Their panels step through runs, times, fields or heights along the rows and
columns ([Rows and columns](#rows-and-columns)), e.g. the same field at several times,
several fields at one time, or plan views at several heights or model levels (e.g. 1, 3
and 6 km, or levels 5, 10 and 20; a layer can keep its own height, and *Panel labels → Height label* names each panel's height or level).

**Plan-view area** is *Follow the tracked storm* (with a *Half-width*, default 12.5 km),
a *Fixed box* (x and y minimum and maximum, in grid km) or the *Whole domain*. *Axis
coordinates* are the model grid's x, y or relative to the storm.

### Vertical cross-sections

A cross-section panel has its *Run*, *Time* and section. The node **Vertical cross-sections** has
*Top* (km) and the *x–z, y–z x axis* for all of them (**Height and x axis**), the sections, and the
layers (fill, contours, vectors …) they share. **+ Cross-section panel** adds one like the last,
showing the next section (an x–z one's next is its y–z twin, an along-motion one's the across one).
Sections are shared: an edit reaches every panel showing that section, and the inspector says which;
*Keep apart* gives a panel a copy. **Copy this panel** then a different run makes runs × sections.

Each section has a *Label*, an
*Orientation* — *x–z*, *y–z*, *Angled* (a direction in degrees clockwise from north),
*Along the storm motion*, *Across the storm motion* or *A–B points* — and a *Position*:
*Through the storm* (a half-length and an offset from the tracked storm; needs a run
with a track) or *Fixed* (x–z: at a y, from x to x; y–z: at an x, from y to y; blank:
the domain's centre and edges; angled: a centre). Along and across the motion
sections are always through the storm and turn with its tracked ground-relative motion
at each time (behind → ahead, or left → right of it; the domain's motion where the track
has none): a *Half-length*, the centre *ahead of* and *right of* the storm (km), and
*Motion averaged over* (minutes about the panel time; 0: the motion at that time) to
steady a wobbly track. *Use map A–B* takes the section drawn
on the map; clicking the ends in a plan-view panel (*Place: section*) sets the first A–B
section. **Average across** (km) makes it a strip-averaged section: the mean of the
sections parallel to the line within half that width either side (0: the line alone).
A plan view can draw the sections' lines as a *Section line* layer
([Figure layers](figures-layers.md)), each drawn once however many panels show it. Figures saved
with a list of sections and a grid of rows and columns open as the same panels.

A section panel's x axis follows its section: x–z and y–z sections are drawn against x
or y — from the storm's for those through the storm (*x–z, y–z x axis*: *From the
storm*), or the model's (*Model grid x, y*, and always for fixed ones) — angled,
motion-relative and A–B sections against the distance along them (0 at the section's
centre, or at A). With *Axes and ticks → x
label* blank each panel is labelled so (*x (km)*, *y from storm (km)*, *distance
(km)*); a label typed there is every panel's.

*Maximum and minimum* writes a layer's maximum and/or minimum over what each
panel shows in a corner (e.g. "max 32.1 m/s"), with + and × where they are.

### Time–height (series)

One series per panel: a panel holds its series' **Run** and settings. **+ Time–height panel** on
the kind's node adds one in the first free cell or a new row or column, and **Copy this panel** with
another run makes runs × series. A series here is always a layer (every level from *Read from* to *Read to*), so it has no *Vertical* choice. One colorbar per row. A series can be plotted as its d/dz or
d/dt. *Maximum and minimum* works here too. The height axis spans the series' layer (a
0–10 km layer shows 0 to 10 km). Older time–height figures (a row per series and a
column per run) open as the same panels.

A new time–height panel starts with no series, so nothing is computed until you add one: **A series
from the Series tool** copies one of the viewer's Series tool, and **+ New series** starts from the
maximum updraft in 0–10 km.

### Time series

Series in the same panel share a panel; series in other units get their own y
axis. Each card sets its line's **Colour**, **Line style**, width and markers. A card of
several runs, alone in its panel, draws a line per run in the run's colour (with the
card's line style); next to other series, its runs share the card's colour and get a line
style each. For your own colour and style per run, use **One per run**. The legend shows the card's
**Label** as it is; a card of several runs adds each run's folder name to tell its lines
apart ("w max · supercell_weak"). A card's **Run** is one run,
*All runs* of the figure, or *Several runs…* (pick them in the list next to it); like a
sounding's, it also offers runs not in the figure (picking one adds it). **One per run**
splits a card of several runs into a card per run in the same panel, each in its run's
colour (a card of one run: a copy for each other run); **Copy this panel** copies it into a
new panel. **Mark each line's** maximum, minimum or
both puts a dot and its value on the line (over the plotted times); **Extremes in the
legend** adds "max 32.1 at 95 min" to each line's entry. Like time–height, it starts with
no series.

A card's points can be changed or blanked by hand, and **+ Your data** adds a series of
your own (observations, another model) from pasted text or a CSV file; see
[Editing a series' values](figures-layers.md#editing-a-series-values) and
[Your own data](figures-layers.md#your-own-data). With parcel output, **+ Parcels** adds a
parcel set's variable over the parcel times ([Parcels in figures](parcels.md#in-figures)),
and **+ w budget** a set's [w budget](parcels.md#the-w-budget) as a panel of four.

**Ensemble of its runs** (a card of *All runs* or *Several runs…*) draws a series from
several runs as one band: its *Centre line*
(the runs' mean or median, or none) and a shaded range: *Min to max*, the *10–90th* or
*25–75th percentile*, or *Mean ± 1 sd*, in the series' colour, with the card's label in
the legend. The runs' own lines stay *Faint*, are *Hidden*, or are drawn *As other lines*.
Runs with other output times are interpolated onto every run's times; the band covers
the times where two runs or more have values.

To line up the same stage of different runs, set each run's **time zero** in
the tree's [**Runs** node](#runs). For example, if one run initiates at 0 min and another at
30 min, give the second run a time zero of 30. Both then show their first hour at 0–60 on
the time axis; set *From* and *To* in *Plot* to 0–60 to show just that hour. A card
of several runs lines them up, and an ensemble band uses the shifted times.

Your own data has no run, so its card has its own *Time zero*. A figure saved with a *Time
zero* on a series or parcel series card, or a *Minutes counted from* in *Panel
labels*, keeps those boxes and they add to the run's time zero; at 0 each one goes away.

With **Region: Around tracked storm**, a card says what each of its runs' **storm tracks**
gives: the number of fixes and their times. The tracks are set in
the tree's [**Runs** node](#runs).

The **Plot** section on the kind's node holds the axes of its panels: *From* and *To*
(minutes), the height axis (time–height) or the left y axis (time series), and for time
series the zero line and *Mark each line's* maximum or minimum (the panel's legend is *Legend in the panel*). Time–height panels
mark theirs in *Maximum and minimum*, below it.

To give one time-series panel its own left y axis, pick it in the tree and fill in
*y from (left axis)* or *y to (left axis)*. A box left blank uses the value on the kind's node,
or the data's range if that is blank too. With *Axes and ticks → Share limits* on y, panels
take the combined range of their limits, so turn it off to keep them different.

### Soundings

Skew-T log-p with adiabats, parcel and barbs, and a hodograph: as an inset, side by side
with the skew-T, or alone (or no hodograph). Several soundings (runs, times,
storm-relative spots) can share a panel; the picture button on a sounding in the items tray
brings the viewer's soundings in.

With several in a panel each takes one colour, with a dashed dewpoint and a dotted parcel.
**Own line looks** on a sounding's card sets the colour, style and width of its temperature,
dewpoint and parcel lines, so two soundings can both be red and green with one dashed. The
hodograph's traces then follow the temperature's style, as long as the panel's soundings
differ by it.

The **hodograph** marks

- the Bunkers right and left movers and the 0–6 km mean wind (each on or off on its own:
  *Hodograph → Show*),
- the heights along the trace, 1, 3, 6, 9 and 12 km unless *Heights marked (km)* lists
  others (`0.5, 1, 3, 6`, or `0:3:0.5` for every 0.5 km to 3 km); labels that would
  overlap on a short hodograph move aside, and
- with a ring, the storm motion chosen for the SRH: Bunkers right or left mover, the 0–6
  km mean wind or a custom motion. With one sounding, dotted lines show the
  storm-relative inflow and the 0–500 m shear, as in the Sounding tab.

The SRH shading, legend and parameter table use that storm motion. A hodograph of its
own adds a key of the height colours (placed, in columns and framed with *Key at*, *Key
columns* and *Key frame*) and optional 0–1 or 0–3 km SRH shading.

The **inset** sits in a corner (upper or lower, right or left); *Auto* picks the top
corner the temperature and dewpoint traces cross least; *Custom* puts its lower-left
corner at *Inset x*, *Inset y* (fractions of the skew-T: 0 left / bottom, 1 right /
top). *Inset size* sets its width as a fraction of the skew-T's. The hodograph's square
view is centred on the origin (± *Hodograph ±*), on a custom u, v, or (*fit*) on what it
draws (the traces up to the hodograph top, the storm motions and ring), which trims the
empty quadrants off to one side.

A **parameter table** under each panel can list surface-based, mixed-layer and
most-unstable CAPE and CIN, LCL and LFC heights, 0–1, 0–3 and 0–6 km shear, SRH, STP and
SCP, a row per sounding (a choice of the Sounding tab's table).

The kind's node (or a panel, for that panel alone) groups the options: *Sounding panels* (what each
panel shows, the table, the storm motion), then *Skew-T* and *Hodograph*, each shown only when the
panels draw one.

### Distributions

Histograms (counts, PDF or fractions; bins by number or width; filled outlines, outlines
or bars), box plots, violins or cumulative distributions, of any field at a height, over
a layer or the whole depth, in the whole domain, a box or around each run's track, with
an optional value range. Each has its own run and time; those in the same panel
share a panel (e.g. w at two times, or two runs), coloured by run (see [Runs](#runs)).

*Bar labels* writes each histogram bar's count, its percentage of the whole sample, or its
value. *Statistics* (n, mean, sd, median, IQR, min, max, 5–95 % and 1–99 % ranges, from
every value) go in the legend (box plots and violins: under the boxes), or in a box in
the panel, a line per distribution in its colour.

### Vertical profiles

A field against height: its maximum, minimum, mean or a percentile over the whole
domain, a box or a disc around each run's track, at every model level from *Read from* to
*Read to*. Each profile has its own run and time, or a time window (*Mean to*) whose
profiles are averaged; those in the same panel share a panel (e.g. two runs,
or one run at two times), coloured by run (see [Runs](#runs)). *+ The Series tool's
layer series* adds the Series tool's layer series at the shown time.

A card's *Run* can also be **All runs** or **Several runs…**: a line per run (at the
output nearest the card's time, which lists the first run's outputs), in the runs'
colours, or in the card's colour with a line style per run when the panel has other
profiles. *Ensemble of its runs* draws a band instead (min to max, 10–90th or 25–75th
percentile, or mean ± 1 sd) with a mean or median line, the runs' own lines faint,
hidden or drawn as usual. **Copy this panel** copies it into a new panel; **One per
run** splits a card of several runs into a card per run, or copies a card of one run
for each other run of the figure, in its panel.

*Then apply* **d/dz** draws the profile's vertical derivative, per metre (e.g. s⁻¹ for w).
It is d/dz of the reduced profile, e.g. of the maximum w at each level, not the maximum
of ∂w/∂z at each level. For that, pick ∂/∂z in the card's **Derivative** select (a
[field derivative](fields.md#derivatives-of-any-field), per km), which series cards
have too.

A profile is a layer series computed only at the times it needs, and cached with the
Series tool's: a time–height panel of the same series later reuses those times, and the
other way round. *Plot* (the panel options) sets the value and height ranges, a zero
line and whether edited lines are marked (the legend is *Legend in the panel*). A card's values can be edited by
hand and downloaded, and **+ Your data** draws a profile of your own beside them
([Profiles: edits and your own data](figures-layers.md#profiles-edits-and-your-own-data)).

### Joint distributions

Two fields against each other at the same points (e.g. vertical vorticity against w):
at a height, over a layer or the whole depth (a 2D field pairs at one height), in the
whole domain, a box or around each run's track, with an optional value range for each
field. Each has its own run and time, or a time window (*To*) whose pairs are all taken;
those in the same panel share a panel, coloured by run (see [Runs](#runs)).
A new one starts from the Distribution tool's last distribution (its field as x), else
w at 1 km.

*Draw as*: a **2D histogram** (counts, PDF or fractions, linear or log colours, with its
own colorbar and *Colorbar label*; the panel's other joint distributions as contours in their colours), a
**scatter** of a random 5,000 pairs of each, or **density contours** of each. Contours
enclose the given percentages of the pairs (*Contours enclosing*, e.g. 50, 90), densest
first; *Contours over* adds them to a histogram or scatter. *Fit line* draws the
least-squares fit of y on x; a 1:1 line and zero lines can be added. *Statistics* (n, the
Pearson correlation r and r², the fit and the means, from every pair) go in a box in the
panel. The bins come from a 200 × 200 histogram of every pair, so changing them, the
ranges or the look reads nothing again.

### Azimuthal means

A field against radius and height around a centre: the values in rings (bins of
radius) at every model level from *Read from* to *Read to*, reduced to their **mean**,
**maximum** or **minimum**. The centre is each run's tracked storm (with an offset) or a
fixed point (model x, y km). A new panel takes w around the storm (else the middle of
the map's view), the whole ring out to 20 km in bins of the grid spacing, 0–15 km.

The **sector** limits the azimuths: *Azimuth from* … *to*, clockwise, from the storm's
motion (*Azimuth 0: Storm motion*, the default; 0 is ahead of the storm, 90 to its
right) or from grid north (0 north, 90 east). 0 to 360 is the whole ring; 0 to 90 the
front-right quadrant; 300 to 60 wraps through 0. The motion is the run's track's at
each time (the domain's motion without a track).

Each has its own run and time, or a time window (*Composite to*): a storm-following
composite, every output's values around its own centre and with its own motion.
Those in the same panel share a panel: the first is **shaded** (grid cells or
filled contours, the field's colours or your own, the data's range or yours, with its
own colorbar), the others are drawn over it as **contour lines** (their levels, colour
and width; negative ones dashed). A field must be on the scalar grid (e.g. winterp, not
w).

A **Sector** layer on a plan view outlines a sector at each panel's time (see
[Layers](figures-layers.md)); give it the azimuthal mean's settings.

### Tables

A table of values across runs and times, set on the panel: each of its entries gives its columns:

- **Values**: *Sounding parameters* (CAPE, CIN, LCL, SRH, shear, STP and the rest) of the
  sounding at the storm, a point or the domain mean, or *Field statistics* (mean, sd, min,
  max, median, IQR, percentiles, n) of every value of a field at a height, in a layer or
  through the whole depth, over a region, as in a distribution.
- **Run**: one run, every run, or the runs picked.
- **Times (min)**: `30, 60, 90`, `30-120/15` (every 15 min) or `30-120` (every output), in
  the first run's minutes, each going to the nearest output. The other runs are read at the
  same time since their time zeros; a row names the time since its run's time zero.

A panel's entries make one table, so one table can hold parameters and statistics side by side.
Several panels make several tables.

In **Table**, *Set out as* picks what the rows and columns are: a row per run and time
with a column per value, a row per value with a column per run and time, or a row per value
with a column per time (to follow one run) or per run (to compare runs). *Show* gives the
values, or the differences from the first run (at each time) or from the first time (of each
run); the first run or time keeps its own values, and the rest are shown with their sign.
*Decimals* sets them all but n; automatic is whole numbers for most sounding parameters, one
for STP and SCP, and about three significant figures for statistics.

A value that cannot be read (no output at that time in that run, or no track position) shows
as `–`, with the reason under the table. The type shrinks to fit the panel: widen the figure
if it gets small. Tables stay as they are in an animation. The table's values are saved with
*Also the script and data* (`Q0_v`, `Q1_v`… in `_src/<name>_data.npz`).

### 3D scenes

One large 3D picture of a box of the run, for print: the isosurfaces, floor, vectors and
streamlines of the [3D workspace](3d.md), rendered off-screen with
[PyVista](https://pyvista.org) (VTK) instead of the browser. Translucent surfaces nest
correctly, the surfaces are smooth-shaded and lit, and the picture is rendered at the
export's DPI. The title, labels, legend (a swatch per surface, vectors and streamlines),
colorbars (floor, streamlines) and axis ticks are drawn by matplotlib around it, as in
any figure, so they stay sharp and editable.

The quickest start is the **photo icon** on the 3D box in the items tray (or **Copy the
3D view** on the scene's node): a figure of everything the 3D workspace shows, its box, settings
and camera included, at the shown time. Rotate the 3D view first to choose the camera.
*3D scene (one picture)* in the New dialog, or as a panel's type, also makes one, from what the
3D workspace shows (the whole domain when it has no box). A figure can hold several scenes beside
other panels. The run and time are on its panel.

The scene's settings:

| Section | Settings |
|---|---|
| **Isosurfaces** | Up to 6: field, value, colour, opacity. Untick one to leave it out (it is kept). |
| **Floor** | As in the 3D workspace: a field (a 3D one at a height), colormap, *Reverse*, *Range*. |
| **Vectors** | Up to 6 planes of arrows: vector, height, frame, *Arrows across*, *Ref. length*, colour. |
| **Streamlines** | Seed height, seeds (*n × n*), maximum length, direction, frame, *Colour by* height or w. **The map's seed box** seeds inside the box picked on the map; **Whole region** clears it. |
| **Parcels** | Runs with parcel output: up to 6 parcel sets, each as the viewer's *Parcels* tab chose it (its rule), with colour or *Colour by* a parcel variable, tails, line width, head size, opacity. **+ Parcels** adds the viewer's next set (or a saved one). See [Parcels in figures](parcels.md#in-figures). |
| **Region and resolution** | *Whole domain* or a *Fixed box* (typed, or **The map's 3D box**), *Top*, *Vertical exaggeration*, *Smoothing σ*, *Resolution*. |
| **Camera** | *View* (from the southwest, above, south, north, west, east), *Azimuth* and *Elevation* (blank: the view's), *Zoom* (1: the whole region fits), *Projection* (perspective or orthographic), *View angle*. **Camera of the 3D view** takes the 3D workspace's, as you left it. |
| **Look** | *Lighting* (a soft light kit, three lights, or a headlight), *Background* (the figure's, white, black or transparent), vectors as 3D arrows or lines, *Shine*, *Ambient light*, *Line thickness*, where the colorbars go, box colour, axis labels; box outline, axis ticks, legend, seed box outline. |
| **Animation** | *Box in animations* and *Camera orbit*: see below. |

Only the region, top, smoothing, resolution, surfaces, floor, vectors and streamlines
read and compute again; the camera, look and exaggeration only render the picture
again. While editing, the picture is rendered at the preview's resolution; saving
renders it at the export's DPI (up to 6000 pixels on its longer side).

**Animations.** *Export → Animation* steps the scene's time like any other figure
([Animations](figures-export.md#animations)); each frame computes the scene again, so
expect a few seconds per frame or more for a large region. *Box in animations*:
**Stays where it is**, or **Follows the track**: a *Fixed box* moves each frame by as
far as the run's storm track has moved since the first frame (the streamlines' seed box
moves with it and the camera keeps aiming at it; a frame without a track fix keeps the
box where it was, and the status says so). The whole domain never moves. *Camera orbit (°)*: how far the camera turns round the
region over the whole animation (360: once round; negative: the other way). The turn is
shared out evenly and stops a step short, so a looping full turn has no repeated frame.

The saved script redraws the scene with PyVista from the data file (the surfaces as
triangle meshes), so it needs PyVista where it runs.

## Runs

Every layer, sounding, distribution, profile, joint distribution, azimuthal mean and
series picks its
run in its own **Run** list.
The list also offers runs not yet in the figure: your recent runs, the runs next to this
one and those under *Where your runs live*. Picking one adds it, with its storm track. The field
lists hold the fields of every run.

The **Runs** node in the tree lists the runs of the figure. Each has

- a **label**,
- a **colour**,
- a **time zero**, and
- a **storm track**.

**Time zero (min)** is the model time the run counts from, e.g. its initiation. Time
series and time–height panels count that run's times from it (see
[Time series](#time-series)). Every other panel lines up runs by time since their time
zeros. If one run initiates
at 60 min and another at 90 min, give them 60 and 90: a grid of the two runs at 75 min of
the first shows 105 min of the second, and both panels are labelled `t = 15 min`.
Differences and ensembles of other runs read the same matched times, and so does a profile
card of several runs: its *Time* is its first run's, and each other run draws the matching
output.

- A time picked for a run stays that run's model time; only a time taken over from
  another run moves (a grid of runs, from its first run).
- A panel or entry with its own time (sections, soundings, distributions, profiles, joint
  distributions, azimuthal means) follows when you change a run's time zero, measured from
  the first panel's run, staying at the moment it showed, and when you pick another run on it.
  All of these go to that run's nearest output.
- Otherwise a moved time needs an output there: the panel says it has none, and a profile
  card says which run has no line (it isn't moved to the nearest output), so runs with
  different output intervals only show the times they share. The time pickers mark times
  that aren't in every run.
- `{min}` in the *Time label* counts from the time zero, on 3D scenes too; `{model}`, `{s}`
  and `{hms}` stay model time. Times in automatic legend text count from the run's time
  zero. The Time lists on the cards stay model time.

**Line runs up by** (shown with two runs or more) chooses how runs pair up: *Time since each
run's time zero*, as above, or **Output number**: the nth output of each run, whatever its
model time, e.g. for runs that output at different intervals or restart at different times.

- The first run in the list is the reference: time labels (`{min}`), automatic legends and
  the time axes of time series and time–height panels use its times, from its time zero. The
  other runs' time zeros don't apply, so they are greyed out. `{model}`, `{s}` and `{hms}` stay
  each panel's own model time.
- Past a shorter run's end its panels are blank and it has no line on a profile card. On a
  time series, a run with more outputs than the first carries on at the first run's last
  interval.
- A time picked for a run stays that run's model time, and animations step every run one output
  at a time.
- Parcel series keep their own finer times, counted from their run's time zero, so they
  aren't paired.
- A saved figure pairs the runs by the outputs they have when it is opened or redrawn.

On time series and time–height figures each series also sets its own colour and line
style, and (with *Region: Around tracked storm*) says what the track here gives (see
[Time series](#time-series)).

A run can be added there first (the runs under *Where your runs live* are found in the background
and join the lists when the search is done).

The colour is the default for the run's storm-track layers, run name in the
panels, and soundings, distributions, profiles, joint distributions and azimuthal mean
contours. In a figure of
several runs a run keeps its
colour in every panel, also in a panel of that run alone. A panel with two soundings
(distributions, profiles) of one run colours them apart instead. 

A run's **✕** removes it, with what is of that run alone: its panels, and layers elsewhere of it
or a difference from it; layers of several runs keep the others. The button's tooltip names the
panels that go, and **Undo** brings them back. The figure's last run stays, as does a run every
panel is of.

## Rows and columns

**Fill panels**, on the Plan views node, writes a grid of plan views at once. **Rows are** and
**Columns are** each step through one of

- **Runs**: the runs picked (blank: all), in the order picked;
- **Times**: from a time, every nth output; in a grid of runs the times are the first run's;
- **Fields**: each panel's fill;
- **Heights**: the heights or model levels typed;
- **—**: nothing.

E.g. runs as rows and times as columns gives a panel for each run at each time. With only one of
them set its panels fill the grid row by row; with neither, every panel is alike.

**Fill the panels** writes ordinary panels once; no rule is kept, so run it again to change them,
or edit any panel on its own afterwards. A panel that already is what a cell asks for goes there,
keeping what was set on it; panels left over go. Figures saved with *Panels differ in*, *Fill a
grid*, or rows and columns that step, open as the same panels.

**Titles from what each shows** labels the panels; with both rows and columns stepping, the top
row's titles name the columns and a row label names each row at its left.

## Figures saved with parts

Figures saved with **parts** by an earlier version open as one grid, with the panels of each part
together: each keeps its settings, colorbar, legend and tick labels. Where the panels sit can shift
a little, as the gaps are now the whole grid's. A part's own title or code is left out, and a note
under the preview says so. To lay out a figure like this now, use the grid's spans above.
