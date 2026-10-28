# Figure layers

The **Layers** tab holds what is drawn in the panels. Each kind of layer is a card with
its own settings, and the last card of a section lists what it shows or leaves out
(*Show*, one list of checkboxes).

## What a layer is

On plan views and cross-sections the layer types are

| Layer | Draws |
|---|---|
| **Fill** | A colour-filled field: colormap, range, steps, linear or log scale, opacity, blanking, colorbar arrows and label. |
| **Contours** | Lines at chosen levels, with labels and their format. |
| **Shading** | A translucent colour over the area where a field is above (or below) a *threshold*, with its own colour and opacity and an optional outline at the threshold. Its *Pattern* hatches, cross-hatches or stipples the area instead (in the layer's colour, over the fields below), e.g. where a difference is significant. |
| **Vectors** | Arrows, wind barbs (plan views; in knots or m/s: half barb 5, full 10, flag 50) or streamlines of the wind, horizontal vorticity or baroclinic generation ([The map](map.md#vectors)). |
| **Storm track** | The run's track (needs a track). |
| **Section line** | The lines of the figure's sections on a plan view (cards alike but for their run, time or panel: one line), labelled in turn from *End labels* (A–A′, B–B′, …; a longer label is numbered), or with *Sections: The panel's own* only the panel's (dashed edges: the strip a strip-averaged section averages). |
| **Sector** | The sector of an [azimuthal mean](figures-panels.md#azimuthal-means) on a plan view: azimuths clockwise from the storm's motion or north, out to a radius, around the track (with an offset) or a fixed point, at each panel's time. |

Time–height and time-series figures have **Series** layers; sounding figures have
**Soundings** layers and distribution figures **Distributions** ([Figure
panels](figures-panels.md)). *Layers* also has *Runs used* ([Runs](figures-panels.md#runs)).

A figure made from the map keeps the map's fill, more fills, contours and vectors as
layers, with their colormaps and ranges.

## Differences

A fill can be a **difference**. *Difference: minus another run or time* subtracts the same
field at another run and/or time (blank: the layer's own) and switches to a red–blue
colormap centred on 0. When the two grids differ the panel says so; pick *Interpolate
onto this layer's grid* or *Refuse* under *If the grids differ*. A fixed *Minus time* stays
put in animations.

## Ensembles

A fill can be an **ensemble** of several runs. *Ensemble: a statistic over several runs*
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
window*):

- the **maximum** (a swath, e.g. of updraft helicity), **minimum**, **mean** or **sum**
  over the outputs *From*–*To* (blank: the run's first output, and the panel's time),
  with *Every nth output* to thin them, placed where the ground is at the panel time (the
  grid moves with `umove`, `vmove`); or
- a **storm-following mean** (composite) in the box that moves with the tracked storm
  (needs a track).

Results are kept in the cache folder (see [Settings](../settings.md)), so redrawing or
restyling reads nothing again.

## Copying a look

*Copy a layer's look* puts one layer's colours, lines, style and colorbar onto others of
its kind (its range, levels and labels too when they show the same field).

## Maxima and minima

*Maximum and minimum* writes a layer's maximum and/or minimum over what each panel shows
in a corner of the panel (e.g. `max 32.1 m/s`), with + and × where they are. It works on
plan views, cross-sections and time–height panels.

## Series layers

Under *Layers → Series* (time–height and time-series figures): each card starts with its
run and panel number (as the sounding and section cards), then the series' field, height
or layer, region and reduction; *Duplicate* and *One per run* copy it (time–height: one
card per panel). **A series from the
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
when the card's or the figure's time zero changes. They are on the plotted values (after
*d/dt*); changing the card's field or reduction keeps them, with a warning in the card.
Everything drawn from the line uses them: ensemble bands, maxima and minima, axis
ranges. An edit at a time the run no longer has is not drawn; the section lists those,
and **Drop those** forgets them. An edited line's legend label ends in "(edited)" unless
*Panels → Time and value axes → Mark edited lines* is off.

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

## Soundings and distributions

The soundings (Skew-T, hodograph, parameter table) and distributions (plot type, bins,
statistics, bar labels) are set in their own cards under *Layers*, shown only for the
panel kinds that use them ([Figure panels](figures-panels.md#soundings)).
