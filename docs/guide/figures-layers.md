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
| **Shading** | A translucent colour over the area where a field is above (or below) a *threshold*, with its own colour and opacity and an optional outline at the threshold. |
| **Vectors** | Arrows or streamlines of the wind, horizontal vorticity or baroclinic generation ([The map](map.md#vectors)). |
| **Storm track** | The run's track (needs a track). |
| **Section line** | The A–B line of a section, on a plan view. |

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

Under *Layers → Series* (time–height and time-series figures): each series has a field,
height or layer, region, reduction, its panel number and its runs. **A series from the
Series tool** copies one of the viewer's computed series (the shown one is picked), and
**+ New series** starts from the maximum updraft in 0–10 km. Series are computed once for
the figure and cached, so restyling is instant; the figure waits for any that are still
computing before it saves ([Series and distributions](series.md)).

## Soundings and distributions

The soundings (Skew-T, hodograph, parameter table) and distributions (plot type, bins,
statistics, bar labels) are set in their own cards under *Layers*, shown only for the
panel kinds that use them ([Figure panels](figures-panels.md#soundings)).
