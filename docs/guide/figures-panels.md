# Figure panels

The **Panels** tab says what the panels show, how they are laid out and which run and
time each one uses. The layers drawn in them are in [Figure layers](figures-layers.md).

## Layout and size

- **Panels show**: the kind of panel (below).
- The **grid** (rows and columns) and the **size**: presets by width (3.25 in one journal
  column, 5, 6.5 full page, 7.5, a 13.3 × 7.5 in slide) or your own. The height follows
  the panels until you type a size; **Fit height** makes it follow again. Any kind of
  panel can have several.
  Adding a section, series, sounding, distribution, profile, joint distribution or
  azimuthal mean with a higher panel number grows the grid; it never shrinks the rows
  and columns you set.
- The **titles** of the figure and of each panel, and the **area** (plan views) or the
  sections' **top** and x axis (cross-sections).
- **Rows are** and **Columns are** (plan views) say what the rows and columns step
  through ([below](#rows-and-columns)).

The time lists offer the output times of the panel's run. A panel's time can be left
empty in any cell.

## Panel kinds

### Plan views

Their panels step through runs, times, fields or heights along the rows and
columns ([Rows and columns](#rows-and-columns)), e.g. the same field at several times,
several fields at one time, or plan views at several heights or model levels (e.g. 1, 3
and 6 km, or levels 5, 10 and 20; a layer can keep its own height, and *Style → Panel
labels → Height label* names each panel's height or level).

**Plan-view area** is *Centred on tracked storm* (with a *Half-width*, default 12.5 km),
a *Fixed box* (x and y minimum and maximum, in grid km) or the *Whole domain*. *Axis
coordinates* are the model grid's x, y or relative to the storm.

### Vertical cross-sections

Cross-sections work like soundings: the Panels tab holds what the whole figure shares
(grid size, *Top* (km), the *x–z, y–z x axis*, colorbar, size, titles), and **Layers →
Sections** has one **section card per panel**: its *Run*, *Time*, cross-section and
*Panel* number. The field layers below the cards (fill, contours, vectors …) are drawn in
every section panel (the panel tree can still change one panel's). *+ Section* adds a
card in a new panel (an x–z card's next is its y–z twin, an along-motion one's the
across one); **Duplicate** copies a card into a new panel; **One per run** copies a card
for each other run of the figure down its column, a row per run. So 3 runs × an x–z and
a y–z section is two cards side by side (x–z, then *+ Section* for the y–z twin) and a
click on each one's *One per run*. A card's *Label* is its panel's title (unless one is
typed in *Titles*); *Fill in from …* titles each panel with its label or section (and
its run, when the cards are of several runs).

Each card has a *Label*, an
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
([Figure layers](figures-layers.md)): its sections are listed under *Panels → Area*
(or are the section part's cards, in a figure of parts), each drawn once however many
runs' cards share it. Figures saved with a list of sections and a grid of rows and
columns open as the same panels, one card each.

A section panel's x axis follows its section: x–z and y–z sections are drawn against x
or y — from the storm's for those through the storm (*x–z, y–z x axis*: *From the
storm*), or the model's (*Model grid x, y*, and always for fixed ones) — angled,
motion-relative and A–B sections against the distance along them (0 at the section's
centre, or at A). With *Style → x
label* blank each panel is labelled so (*x (km)*, *y from storm (km)*, *distance
(km)*); a label typed there is every panel's.

*Layers → Maximum and minimum* writes a layer's maximum and/or minimum over what each
panel shows in a corner (e.g. "max 32.1 m/s"), with + and × where they are.

### Time–height (series)

One series card per panel, like the [section cards](#vertical-cross-sections): each card
in *Layers → Series* has its **Run** and **Panel** number, and the grid grows to fit the
cards. **Duplicate** copies a card into a new panel; **One per run** copies it for each
other run of the figure down its column (a row per run), so runs × series takes a row of
cards and a click on each. A card here is always a layer (every level from *Bottom* to *Top*), so it has no *Vertical* choice. One colorbar per row. A series can be plotted as its d/dz or
d/dt. *Maximum and minimum* works here too. The height axis spans the series' layer (a
0–10 km layer shows 0 to 10 km). Older time–height figures (a row per series and a
column per run) open as the same panels, a card each. Switching time series to
time–height gives a card per series and run (a row per run); switching back makes the
cards of one series one card of their runs again.

Switching a figure to time–height starts it with no series, so nothing is computed until
you add one in *Layers → Series*: **A series from the Series tool** copies one of the
viewer's Series tool (the shown one is picked), and **+ New series** starts from the
maximum updraft in 0–10 km.

### Time series

Series with the same panel number share a panel; series in other units get their own y
axis. Each card sets its line's **Color**, **Line** style, width and markers. A card of
several runs, alone in its panel, draws a line per run in the run's colour (with the
card's line style); next to other series, its runs share the card's colour and get a line
style each. For your own colour and style per run, use **One per run**. The legend shows the card's
**Label** as it is; a card of several runs adds each run's folder name to tell its lines
apart ("w max · supercell_weak"). A card's **Run** is one run,
*All runs* of the figure, or *Several runs…* (pick them in the list next to it); like a
sounding's, it also offers runs not in the figure (picking one adds it). **One per run**
splits a card of several runs into a card per run in the same panel, each in its run's
colour (a card of one run: a copy for each other run); **Duplicate** copies a card into a
new panel. **Mark each line's** maximum, minimum or
both puts a dot and its value on the line (over the plotted times); **Extremes in the
legend** adds "max 32.1 at 95 min" to each line's entry. Like time–height, it starts with
no series.

A card's points can be changed or blanked by hand, and **+ Your data** adds a series of
your own (observations, another model) from pasted text or a CSV file; see
[Editing a series' values](figures-layers.md#editing-a-series-values) and
[Your own data](figures-layers.md#your-own-data).

**Ensemble of its runs** (a card of *All runs* or *Several runs…*) draws a series from
several runs as one band: its *Centre line*
(the runs' mean or median, or none) and a shaded range: *Min to max*, the *10–90th* or
*25–75th percentile*, or *Mean ± 1 sd*, in the series' colour, with the card's label in
the legend. The runs' own lines stay *Faint*, are *Hidden*, or are drawn *As other lines*.
Runs with other output times are interpolated onto every run's times; the band covers
the times where two runs or more have values.

**Time zero (min)** on a time series or time–height card shifts that series' times, so
the same stage of different runs lines up. For example, if one run initiates at 0 min
and another at 30 min, give the second run's card a time zero of 30. Both then show
their first hour at 0–60 on the time axis; set *Time and value axes* to 0–60 to show just
that hour. The figure's own time zero (*Style → Panel labels*) adds to every card's. A
card of several runs shifts all of them alike (an ensemble band uses the shifted times);
for a time zero per run, use **One per run**.

With **Region: Around tracked storm**, a card shows the **storm track** of each of its
runs: the viewer's track (for the viewer's run) or a track file (storm_tracks/*.csv next
to a run is found automatically), with the number of fixes and their times. A run's
track is shared by every card of that run, so changing it on one card changes it on all.

### Soundings

Skew-T log-p with adiabats, parcel and barbs, and a hodograph: as an inset, side by side
with the skew-T, or alone (or no hodograph). Several soundings (runs, times,
storm-relative spots) can share a panel; the picture button on a sounding in the items tray
brings the viewer's soundings in.

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

*Layers* groups the options: *Sounding panels* (what each panel shows, the table, the
storm motion), then *Skew-T* and *Hodograph*, each shown only when the panels draw one.

### Distributions

Histograms (counts, PDF or fractions; bins by number or width; filled outlines, outlines
or bars), box plots, violins or cumulative distributions, of any field at a height, over
a layer or the whole depth, in the whole domain, a box or around each run's track, with
an optional value range. Each has its own run and time; those with the same panel number
share a panel (e.g. w at two times, or two runs), coloured by run (see [Runs](#runs)).

*Bar labels* writes each histogram bar's count, its percentage of the whole sample, or its
value. *Statistics* (n, mean, sd, median, IQR, min, max, 5–95 % and 1–99 % ranges, from
every value) go in the legend (box plots and violins: under the boxes), or in a box in
the panel, a line per distribution in its colour.

### Vertical profiles

A field against height: its maximum, minimum, mean or a percentile over the whole
domain, a box or a disc around each run's track, at every model level from *Bottom* to
*Top*. Each profile has its own run and time, or a time window (*Mean to*) whose
profiles are averaged; those with the same panel number share a panel (e.g. two runs,
or one run at two times), coloured by run (see [Runs](#runs)). *+ The Series tool's
layer series* adds the Series tool's layer series at the shown time.

A card's *Run* can also be **All runs** or **Several runs…**: a line per run (at the
output nearest the card's time, which lists the first run's outputs), in the runs'
colours, or in the card's colour with a line style per run when the panel has other
profiles. *Ensemble of its runs* draws a band instead (min to max, 10–90th or 25–75th
percentile, or mean ± 1 sd) with a mean or median line, the runs' own lines faint,
hidden or drawn as usual. **Duplicate** copies the card into a new panel; **One per
run** splits a card of several runs into a card per run, or copies a card of one run
for each other run of the figure, in its panel.

*Plot* **d/dz** draws the profile's vertical derivative, per metre (e.g. s⁻¹ for w).
It is d/dz of the reduced profile, e.g. of the maximum w at each level, not the maximum
of ∂w/∂z at each level (that is a [field derivative](fields.md#derivatives-of-any-field)
on the map).

A profile is a layer series computed only at the times it needs, and cached with the
Series tool's: a time–height panel of the same series later reuses those times, and the
other way round. *Plot* (the panel options) sets the value and height ranges, a zero
line, the legend and whether edited lines are marked. A card's values can be edited by
hand and downloaded, and **+ Your data** draws a profile of your own beside them
([Profiles: edits and your own data](figures-layers.md#profiles-edits-and-your-own-data)).

### Joint distributions

Two fields against each other at the same points (e.g. vertical vorticity against w):
at a height, over a layer or the whole depth (a 2D field pairs at one height), in the
whole domain, a box or around each run's track, with an optional value range for each
field. Each has its own run and time, or a time window (*To*) whose pairs are all taken;
those with the same panel number share a panel, coloured by run (see [Runs](#runs)).
A new one starts from the Distribution tool's last distribution (its field as x), else
w at 1 km.

*Draw as*: a **2D histogram** (counts, PDF or fractions, linear or log colours, with its
own colorbar; the panel's other joint distributions as contours in their colours), a
**scatter** of a random 5,000 pairs of each, or **density contours** of each. Contours
enclose the given percentages of the pairs (*Contours enclosing*, e.g. 50, 90), densest
first; *Contours over* adds them to a histogram or scatter. *Fit line* draws the
least-squares fit of y on x; a 1:1 line and zero lines can be added. *Statistics* (n, the
Pearson correlation r and r², the fit and the means, from every pair) go in a box in the
panel. The bins come from a 200 × 200 histogram of every pair, so changing them, the
ranges or the look reads nothing again.

### Azimuthal means

A field against radius and height around a centre: the values in rings (bins of
radius) at every model level from *Bottom* to *Top*, reduced to their **mean**,
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
Those with the same panel number share a panel: the first is **shaded** (grid cells or
filled contours, the field's colours or your own, the data's range or yours, with its
own colorbar), the others are drawn over it as **contour lines** (their levels, colour
and width; negative ones dashed). A field must be on the scalar grid (e.g. winterp, not
w).

A **Sector** layer on a plan view outlines a sector at each panel's time (see
[Layers](figures-layers.md)); give it the azimuthal mean's settings.

## Runs

Every layer, sounding, distribution, profile, joint distribution, azimuthal mean and
series picks its
run in its own **Run** list.
The list also offers runs not yet in the figure: your recent runs, the runs next to this
one and those under *Where your runs live*. Picking one adds it, with its storm track; a
run nothing uses any more is dropped. The field lists hold the fields of every run.

**Layers → Runs used** lists the runs of the figure. Each has

- a **label**,
- a **colour**, and
- a **storm track**.

Time series and time–height figures don't have this section: each series card picks its
run, sets its own colour, line style and time zero, and (with *Region: Around tracked
storm*) shows the storm track of each of its runs (see [Time series](#time-series)).

A run can be added there first by filtering or pasting a folder (the runs under *Where
your runs live* are found in the background and join the lists when the search is done).

The colour is the default for the run's storm-track layers, run name in the
panels, and soundings, distributions, profiles, joint distributions and azimuthal mean
contours. In a figure of
several runs a run keeps its
colour in every panel, also in a panel of that run alone. A panel with two soundings
(distributions, profiles) of one run colours them apart instead. Removing a run takes its panels,
soundings, distributions, profiles, joint distributions and azimuthal means with it;
those of the runs
after it stay on their runs.

## Rows and columns

For plan views, *Grid and size* → **Rows are** and **Columns are**
each step through one of (cross-sections have a [card per panel](#vertical-cross-sections)
instead)

- **Runs**: the runs picked (*Runs, one per row / column*), in the order picked;
- **Times**: a time per row or column (*Fill from the shown time* fills them every
  *Every … outputs*); in a grid of runs the times are the first run's outputs, marked
  *not in every run* where another run has none;
- **Fields**: a fill per row or column (its colorbar per row or column);
- **Heights**: the heights or model levels typed;
- **—**: nothing.

E.g. runs as rows and times as columns gives a panel for each run at each time.
Runs and heights set their number of rows (columns) themselves; times
and fields take as many as you set. With only one of them set (the other *—*), its
panels fill the grid row by row (the older *Panels differ in*); with neither, every
panel is alike, and the panel tree changes one panel's run, time or height.
What the rows and columns do not step through is the figure's: one *Run (every panel)*
and one *Time (every panel)*.

When both are set the figure is labelled as the grid is made, until you type titles:
the top row's titles name the columns (e.g. the times) and *Titles → Row …
label* names each row at its left (e.g. the run names; the run labels in the panels go
off). *Fill in from fields, times or runs* labels them so again. Figures saved with *Panels differ in*, *Fill a grid* or a
run and time for each panel open as the same panels (the last as panel-tree changes).

## Figure parts

At the top of Panels: a figure can have **parts** with different kinds of panels, e.g.
plan views beside soundings, or a plan view with its A–B line above the cross-section.
The plan-view and cross-section parts share the list of sections: a section changed in
one part is the others' too (the section part's cards keep their runs, times and
panels).

- Each part has its own panels, runs, layers and style, and keeps its own size.
- The parts are side by side or stacked, and the panel letters run on from part to part.
- Edit one part at a time (*Figure parts* picks it; *New figure from* then makes the part
  anew).
- The whole figure can be given a width and height (the parts then share it by their
  sizes), each part a share of it (0–1), and the figure one colorbar for all its parts.
