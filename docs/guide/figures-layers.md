# Figure layers

A panel's layers are what is drawn in it. In the tree they sit under a panel; each is a row in the
inspector with its own settings, and the end of a section lists what it shows or leaves out
(*Show*, one list of checkboxes).

On a kind's node, such as **Plan views**, the layers are **shared**: changing one reaches every
panel drawing it, except for what a panel has set for itself. Picking a layer under a panel changes
it there alone. *In panels* says which panels draw a shared layer, and **Keep apart** gives a panel
its own copy. A panel can add layers of its own too.

## What a layer is

On plan views and cross-sections the layer types are

| Layer | Draws |
|---|---|
| **Fill** | A colour-filled field: colormap, range, steps, linear or log scale, opacity, blanking, colorbar arrows and label. |
| **Contours** | Lines at chosen levels, with labels and their format. |
| **Shading** | A translucent colour over the area where a field is above (or below) a *threshold*, with its own colour and opacity and an optional outline at the threshold. Its *Pattern* hatches, cross-hatches or stipples the area instead (in the layer's colour, over the fields below), e.g. where a difference is significant. |
| **Vectors** | Arrows, wind barbs (plan views; in knots or m/s: half barb 5, full 10, flag 50) or streamlines of the wind, horizontal vorticity or baroclinic generation ([The map](map.md#vectors)). |
| **Storm track** | The run's track (needs a track). |
| **Section line** | The lines of the figure's sections on a plan view (one line for each section, however many panels show it), labelled in turn from *End labels* (A–A′, B–B′, …; a longer label is numbered), or with *Sections: The panel's own* only the panel's (dashed edges: the strip a strip-averaged section averages). |
| **Sector** | The sector of an [azimuthal mean](figures-panels.md#azimuthal-means) on a plan view: azimuths clockwise from the storm's motion or north, out to a radius, around the track (with an offset) or a fixed point, at each panel's time. |

Time–height and time-series figures have **Series** layers; sounding figures have
**Soundings** layers and distribution figures **Distributions** ([Figure
panels](figures-panels.md)). The runs are on the tree's **Runs** node ([Runs](figures-panels.md#runs)).

The buttons on a layer's row move it, remove it, or **copy** it: the copy is drawn just above
it, with any changes the layer has in single panels.

A figure made from the map keeps the map's fill, more fills, contours and vectors as
layers, with their colormaps and ranges.

A fill, contour or shading layer's **Derivative** draws ∂/∂z, ∂/∂x, ∂/∂y or |∇h| of its
Field (per km) instead of the field ([Derivatives of any field](fields.md#derivatives-of-any-field)):
contours of ∂w/∂z over a fill of w, say.

## Differences

A fill can be a **difference**. In the card's folded *Difference* section (open when in use), *Difference: minus another run or time* subtracts the same
field at another run and/or time (blank: the layer's own) and switches to a red–blue
colormap centred on 0. When the two grids differ the panel says so; pick *Interpolate
onto this layer's grid* or *Refuse* under *If the grids differ*. A fixed *Minus time* stays
put in animations.

## Ensembles

A fill can be an **ensemble** of several runs. In the card's folded *Ensemble* section (open when in use), *Ensemble: a statistic over several runs*
reads the same field from each run in its *Runs* list (blank: every run of the figure) at
the layer's time and combines them cell by cell: the **mean**, **median**, **spread**
(standard deviation), **min**, **max**, **range** (max − min) or the **probability of
exceeding** a *Threshold* (the percentage of the runs above it, or below it with *Where the
value is: Below*). Each statistic starts with fitting colours (a probability 0–100 % in
blues, blank at 0; a spread or range from 0); the colorbar says which statistic it is.
Runs without output at the layer's time are left out. Runs on other grids are
interpolated onto the panel's run's grid with *Interpolate* under *If the grids differ*
(as a difference). An ensemble is not also a difference; the layer's own *Run* is not used.

## Time windows

A fill, contour or shading layer on a plan panel can cover a **time window** (*Over a time
window*; on a fill, in its folded *Time window* section):

- the **maximum** (a swath, e.g. of updraft helicity), **minimum**, **mean** or **sum**
  over the outputs *From*–*To* (blank: the run's first output, and the panel's time),
  with *Every nth output* to thin them, placed where the ground is at the panel time (the
  grid moves with `umove`, `vmove`); or
- a **storm-following mean** (composite) in the box that moves with the tracked storm
  (needs a track).

Results are kept in the cache folder (see [Settings](../settings.md)), so redrawing or
restyling reads nothing again.

## Copying a look

*Copy a layer's look*, on a kind's node, puts one shared layer's colours, lines, style and colorbar onto others of
its kind (its range, levels and labels too when they show the same field).

## Maxima and minima

*Maximum and minimum* writes a layer's maximum and/or minimum over what each panel shows
in a corner of the panel (e.g. `max 32.1 m/s`), with + and × where they are. It works on
plan views, cross-sections and time–height panels.

## Series layers

On a time–height or time-series panel: each series has its run, then its field, height or
layer, region and reduction; *One per run* splits or copies it for the figure's other runs. A
time–height panel has one series. **A series from the
Series tool** copies one of the viewer's computed series (the shown one is picked), and
**+ New series** starts from the maximum updraft in 0–10 km. Series are computed once for
the figure and cached, so restyling is instant; the figure waits for any that are still
computing before it saves ([Series and distributions](series.md)).

### Editing a series' values

A time-series card's **Values (edit points)** section (folded; built when you open it)
lists the line of the *Run* picked: *Time (min)*, *Model time (s)*, *Computed* and
*Yours*. Type a number in *Yours* to replace a point, `blank` to leave it out of the line
(a gap), or clear the cell to undo. **Blank points** and **Reset points** act on the rows
ticked, **Reset all edits** on every run of the card; **Download CSV** saves the line as
drawn, **Refresh** reads the values again (e.g. after more output was written).

Edits are kept in the figure, per run, at the model time of the point, so they stay put
when the run's time zero changes. They are on the plotted values (after
*d/dt*); changing the card's field or reduction keeps them, with a warning in the card.
Everything drawn from the line uses them: ensemble bands, maxima and minima, axis
ranges. An edit at a time the run no longer has is not drawn; the section lists those,
and **Drop those** forgets them. An edited line's legend label ends in "(edited)" unless
*Plot → Mark edited lines* is off.

Edits belong to a run by its place in the card's *Run* list: reordering or removing the
card's runs moves them to another run, so reset them first.

### Your own data

**+ Your data** (time-series figures) adds a card for a series that is not from a run:
observations, another model. Paste two columns, time in minutes and value, split by
commas, tabs, semicolons or spaces (the text is read when you click away), or load a
file (up to 2 MB). A header line is optional; `time, rain (mm)` gives the card's label
and units when they are blank. Lines starting with `#` are skipped, and a blank, `nan` or
`-` value leaves a gap. The note under it gives the points read and their time range;
text it cannot read is reported there and the data read before is still drawn.

The data, up to 10,000 points, is kept in the figure itself, so a saved figure opens
anywhere without the file. It is drawn like any series: *Label*, *Units* (shared y axes
by units), *Axis label*, *Panel*, *Time zero*, colour, line, width, markers and y axis.
It computes nothing and has no run. In a time–height figure the card is kept but not
drawn.

## Profiles: edits and your own data

A profile card's **Values (edit points)** works as a time series' (above), a row per
model level: *Height (km)*, *Computed*, *Yours*. It lists the values the preview drew
(it computes nothing: **Refresh** once the preview has them), per run of the card. Edits
are on the plotted values (after the time window's mean and *d/dz*) and kept in the
figure at the level's height; changing the card's field, layer, region, reduction, time
or *Then apply* keeps them, with a warning in the card. An ensemble band is made from the
edited lines. **Download CSV** saves `z_km,computed,plotted`. An edited line's legend
label ends in "(edited)" unless *Plot → Mark edited lines* is off.

**+ Your data** (profile figures) adds a card for a profile that is not from a run: an
observed sounding, another model. Paste two columns, **height in km** and value (the
same order as the CSV above, so a download reads back in), or load a file; a header such
as `z, w (m/s)` gives the label and units. It is kept in the figure, drawn in its own
colour, line and markers, and gives the value axis its label only if you set one.

## Soundings and distributions

The soundings (Skew-T, hodograph, parameter table) and distributions (plot type, bins,
statistics, bar labels) are set on the panel and its kind's node
 ([Figure panels](figures-panels.md#soundings)).
