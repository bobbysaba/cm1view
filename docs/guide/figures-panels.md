# Figure panels

The **Panels** tab says what the panels show, how they are laid out and which run and
time each one uses. The layers drawn in them are in [Figure layers](figures-layers.md).

## Layout and size

- **Panels show**: the kind of panel (below).
- The **grid** (rows and columns) and the **size**: presets by width (3.25 in one journal
  column, 5, 6.5 full page, 7.5, a 13.3 × 7.5 in slide) or your own. The height follows
  the panels until you type a size; **Fit height** makes it follow again. Any kind of
  panel can have several (time–height panels: a row per series and a column per run).
  Adding a series, sounding or distribution with a higher panel number grows the grid;
  it never shrinks the rows and columns you set.
- The **titles** of the figure and of each panel, and the **area** (plan views) or
  **section** (cross-sections) shown.
- **Fill a grid** makes a grid of runs × times ([below](#fill-a-grid)).

The time lists offer the output times of the panel's run. A panel's time can be left
empty in any cell.

## Panel kinds

### Plan views and vertical cross-sections

Panels that differ in

- **time**: the same field at several times of one run;
- **field**: several fields at one time;
- **height**: at several heights or model levels (plan views: e.g. 1, 3 and 6 km, or
  levels 5, 10 and 20). A layer can keep its own height. *Style → Panel labels → Height
  label* names each panel's height or level;
- **each panel with its own run and time**.

**Plan-view area** is *Centred on tracked storm* (with a *Half-width*, default 12.5 km),
a *Fixed box* (x and y minimum and maximum, in grid km) or the *Whole domain*. *Axis
coordinates* are the model grid's x, y or relative to the storm. A cross-section is
*Through tracked storm* (with a direction in degrees from east, a half-length, offsets and
a top) or a *Fixed A–B from the map*. **Average across** (km) makes it a strip-averaged
section: the mean of the sections parallel to the line within half that width either
side (0: the line alone). A plan view can draw the section's line as a
*Section line* layer ([Figure layers](figures-layers.md)).

*Layers → Maximum and minimum* writes a layer's maximum and/or minimum over what each
panel shows in a corner (e.g. "max 32.1 m/s"), with + and × where they are.

### Time–height (series)

A row per series and a column per run, one colorbar per row (*Grid and size → Runs
are* swaps them). Each series is drawn for its own **Runs** (*Layers → Series*; blank:
every run of the figure); the columns are the runs any series uses, and a series that
skips a run leaves that cell empty. A series can be plotted as
its d/dz or d/dt. *Maximum and minimum* works here too. The height axis spans the series'
layer (a 0–10 km layer shows 0 to 10 km).

Switching a figure to time–height starts it with no series, so nothing is computed until
you add one in *Layers → Series*: **A series from the Series tool** copies one of the
viewer's Series tool (the shown one is picked), and **+ New series** starts from the
maximum updraft in 0–10 km.

### Time series

Series with the same panel number share a panel; series in other units get their own y
axis; one series is coloured by run (see [Runs](#runs)). A series' *Runs* list also offers
runs not in the figure (picking one adds it). **Mark each line's** maximum, minimum or
both puts a dot and its value on the line (over the plotted times); **Extremes in the
legend** adds "max 32.1 at 95 min" to each line's entry. Like time–height, it starts with
no series.

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

## Runs

Every layer, sounding, distribution and series picks its run in its own **Run** list.
The list also offers runs not yet in the figure: your recent runs, the runs next to this
one and those under *Where your runs live*. Picking one adds it, with its storm track; a
run nothing uses any more is dropped. The field lists hold the fields of every run.

**Layers → Runs used** lists the runs of the figure. Each has

- a **label**,
- a **colour**,
- a **line style**, and
- a **storm track**.

A run can be added there first by filtering or pasting a folder (the runs under *Where
your runs live* are found in the background and join the lists when the search is done).

The colour is the default for the run's time series, storm-track layers, run name in the
panels, and soundings and distributions. In a figure of several runs a run keeps its
colour in every panel, also in a panel of that run alone. A panel with two soundings
(distributions) of one run colours them apart instead, and a panel of several series
colours them by series, with the run's line style. Removing a run takes its panels,
soundings and distributions with it; those of the runs after it stay on their runs.

## Fill a grid

**Fill a grid** makes panels of runs × times. Pick

- the runs,
- how many times from the shown time, and every how many outputs, and
- whether the runs are rows or columns.

Every panel then has its own run and time, which you can change one by one. A figure
saved with the older *Run × time grid* opens this way.

## Figure parts

At the top of Panels: a figure can have **parts** with different kinds of panels, e.g.
plan views beside soundings, or a plan view with its A–B line above the cross-section.

- Each part has its own panels, runs, layers and style, and keeps its own size.
- The parts are side by side or stacked, and the panel letters run on from part to part.
- Edit one part at a time (*Figure parts* picks it; *New figure from* then makes the part
  anew).
- The whole figure can be given a width and height (the parts then share it by their
  sizes), each part a share of it (0–1), and the figure one colorbar for all its parts.
