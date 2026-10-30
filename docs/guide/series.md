# Series and distributions

Two tools reduce a whole field to a few numbers:

- **Series** reduces a field over a region at **every output time** (e.g. the minimum θ′
  in the cold pool, the maximum updraft in the box, as a function of time).
- **Distribution** keeps **every value** of a field in a region at **one time** and shows
  how they are spread (histogram, box plot, violin, cumulative).

Both use the same ways of choosing a field, a height or layer and a region, and both
leave nothing to recompute when you change how the result is drawn.

## Choosing what to reduce

| Setting | Meaning |
|---|---|
| **Field** | Any native or derived field, 3D or 2D. |
| **Derivative** | Reduce a derivative of the field instead (∂/∂z, ∂/∂x, ∂/∂y or \|∇h\|, per km; see [Derivatives of any field](fields.md#derivatives-of-any-field)), e.g. the maximum ∂w/∂z at 2 km. A 2D field has no ∂/∂z. |
| **Vertical** | *At a height* (km AGL), or *Layer (every level)*, with *Bottom* and *Top*. For a layer the reduction also keeps every model level in it. Distributions also offer *Every level (whole depth)*. 2D fields (swaths, surface fields) have no vertical setting. |
| **Region** | *Whole domain*, *Current map view* (the area in view when you compute), *3D region box* (offered once you have drawn one, see [3D](3d.md)), or *Around tracked storm* (needs a [track](tracking.md)). |
| **Radius (km)**, **Offset x / y (km)** | For *Around tracked storm*: a disc of this radius, centred on the storm or shifted by the offset on the model grid, e.g. into the inflow or onto the cold pool. |

## Series

Choose the **Series** tool; the panel is on the right and the tool needs no clicks.

1. Pick a field, height or layer, and region.
2. Pick the reduction: *Minimum*, *Maximum*, *Mean*, or *Percentile* with a value from 0
   to 100 (default 99).
3. Press **Compute**. Every output time is processed in the reader processes (a few
   seconds for one height, about a minute for a deep layer). The status line counts times
   as they finish and shows the elapsed time, and the plot fills in as it goes.
   **Stop** ends it early and keeps what is done. Times that could not be computed
   (a field missing at that time, say) are listed with the reason.

Compute again with other settings to add more series to the plot: each is drawn in a
colour of its own with a legend below the plot (click an entry to hide the line). Series
in other units than the first get their own y axis on the right. Pick which one the
buttons act on with **Series**. **Remove** drops it.

### Reading the series

- **Hover** for the name, time, value and, for a minimum or maximum, where it occurred
  (x, y and height, in km; blank for a mean or percentile).
- **Click** on a plot to go to that time.
- A yellow line marks the shown time.
- **Plot** (settings button) sets the limits and the colours without recomputing:
  *Time from … to* (min), *y from … to*, and the time–height colormap and colour range.
  **Auto limits** clears them.

### Layers and the time–height view

A layer series (*Layer (every level)*) keeps the reduction at every model level:

- **Time–height** (next to *Time series*) draws it as a plot of height against time,
  coloured by value. The colours are diverging (white at zero) when the values have both
  signs, otherwise viridis, from the 1st to the 99th percentile; the plot settings
  override the colormap and range.
- **Sub-layer from … to (km)** reduces over part of the layer: e.g. the maximum w over
  0–2 km out of a 0–10 km layer. It works for minimum, maximum and mean (a percentile of
  a sub-layer needs a new computation) and appears in the line view only.

### Caching

Results are cached in `<cache_dir>/series` per run and recipe, and reused per time as long
as the output file is unchanged (and, for a storm-following region, the storm's position
at that time has not moved). Asking for the same series again, even in a later session,
returns it at once. Only the times missing are computed.

### Saving and loading

At the foot of the panel: **Save to / load from** (a path on the server), a *Format*, and
**Save**, **Download** (to your browser) and **Load**.

| Format | Contains |
|---|---|
| `.nc` | Everything: the series, where the extreme was, the region centre, and for a layer the per-level values. Opens with xarray. |
| `.csv`, `.txt` | The series only (comma-separated, or aligned columns), with a `#`-commented header describing the recipe. |
| `.pkl` | A pickled dictionary with the series, the per-level values and the recipe, as pandas objects. |

Load reads one back (any format) and adds it to the plot with its file name. Only open
pickle files you made yourself: loading one can run code. Saving asks before overwriting.

The columns of a table are `value` (the reduced field), `x_km`, `y_km`, `z_km` (where the
minimum or maximum was; not for a mean or percentile), the region's centre for a
storm-following region, and `npoints` (grid columns in the region).

### Series in figures

The viewer's series can be copied into a figure as a time series or a time–height panel
([Figures](figures.md)). The picture button on a series in the items tray makes one.

## Distributions

Choose the **Distrib.** tool.

1. Pick a field, a height, layer or the whole depth, and a region.
2. Optionally keep only values in a range: **Only values from … to** (e.g. w ≥ 1 m/s for
   updrafts; blank is no limit).
3. Press **Compute**: it reads every value in the region at the **shown time** (a few
   seconds). The status line gives the number of values and the time taken.

Compute again at other times, heights, fields or regions to compare them. They are drawn
together, each in its own colour, and listed in the *Distribution* menu: **Remove** drops
the chosen one and **Clear all** drops all. **Follow the time slider** computes the chosen
distribution again at the new time when time settles, replacing it in place.

### Plot types

| Plot | Shows |
|---|---|
| **Histogram** | Counts, a PDF (each distribution integrates to 1) or a fraction of the values per bin, in shared bins (*Bins*, default 50). Optional log scale. |
| **Box** | The box is the interquartile range with the median marked; the diamond is the mean. Whiskers at 1.5 × IQR, the minimum–maximum, the 5th–95th percentiles, or the 1st–99th (*Whiskers*). |
| **Violin** | The same whiskers, with the shape of the distribution. |
| **Cumulative** | The fraction at or below x, or above x for the tails (*Fraction*). Optional log scale. |

*Values from … to* sets the range of the value axis. Changing the plot reads nothing
again: the plots come from a summary of each distribution (a 4000-bin histogram of every
value from its minimum to its maximum, and its quantiles).

### The statistics table

A table gives each distribution's count, mean, standard deviation, minimum and maximum,
median, and 1st and 99th percentiles.

### Distributions in figures

**Figure of these** opens the distributions as a figure in the Figure workspace, drawn
the same way ([Figures](figures.md)).
