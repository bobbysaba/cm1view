# The map

The Map workspace is a plan view of the run at the shown time. You build it in layers,
bottom to top: a **fill** (with up to three **more fills** over it), then **contours**,
then **vectors**. Everything you add draws on the same map, and a figure made from the
map keeps each as a layer ([Figures](figures.md)).

## The toolbar

The toolbar above the map holds the first fill and, to its right, a pill for each layer
group: **More fills**, **Contours** and **Vectors**.

| Control | What it does |
|---|---|
| Field | The fill field, from a list grouped by kind (Radar, Kinematics, Thermodynamics, Pressure decomposition, Microphysics, and so on). Each entry reads `label [name]`, with the CM1 variable name in brackets. |
| Level mode | *Height AGL (km)*, *Model level (k)*, *Column max* or *Column min*. |
| Level | The height in km (steps of 0.25) or the model level `k` (steps of 1). Use the arrow keys or the mouse wheel over the box to step through. Disabled for column max / min. 2-D fields (swaths, surface fields) have no level. |
| **Style ▾** | The fill's look (below). |

Each ▾ pill opens its controls in a drawer under the toolbar; click the pill again to
close it. A pill names what is in it: a drawer with one layer on says which field and
level (*Contours · w 3 km*); with several on it gives the count (*Vectors · 2*).

### Level modes

- **Height AGL**: the field at a height above ground, interpolated between the model's
  levels.
- **Model level**: the field on the model's own level `k` (0 is the lowest). The map
  title gives the level's height in metres.
- **Column max / min**: the largest or smallest value in each column. It reads the whole
  3D field, so the first one at a time takes a few seconds ([Performance](index.md#performance)).
  Use it for things like the maximum updraft or the lowest pressure anywhere in the
  column.

### Style (the fill)

- **Pixels** draw each grid cell as it is; **Filled contours** draw bands with
  *Contour intervals* (4 to 30, default 15). Pixels are faster to redraw and show the
  data without smoothing.
- **Colormap**, with **Reverse**. The list holds `reflectivity` (the stepped NWS-style
  radar colours, below 5 dBZ transparent), perceptual maps (`viridis`, `turbo`, `magma`,
  `cividis`, …), diverging maps (`RdBu_r`, `PuOr_r`, `BrBG`, `coolwarm`, `seismic`,
  `cmo.balance`, …) and the `cmo.*` maps of cmocean when it is installed. Each field
  starts with a colormap suited to it.
- **Auto range** picks the colour range. A field with a fixed range in its definition
  (θ′ is ±6 K, for example) keeps it. Otherwise the range runs from the 0.5th to the
  99.5th percentile of the values in the picture, and for a diverging field it is
  symmetric about zero (±the 99.5th percentile of the absolute value). Untick it to type
  your own **Min** and **Max**; the boxes start from the range last drawn.
- **Opacity** from 0.1 to 1, to see the layers below through the fill.

!!! note "Diverging colormaps stay white at zero"
    A diverging colormap (`RdBu_r`, `BrBG`, `PuOr_r`, `coolwarm`, …) keeps white at 0 when
    the range crosses 0 unevenly: −2 to 6 draws 0 to 6 in the full reds, and −2 to 0 in
    the pale blues that −6 to 6 would give. The same holds in cross-sections, time–height
    plots and figures.

## More fills

*More fills* draws up to three further fills over the first, one row each, with a
colorbar of its own for each. Use them to show two fields at once without hiding the
first, e.g. reflectivity with updraft ≥ 5 m/s on top. *Add fill* adds a row; ✕ removes
one; the checkbox at the start of a row switches it on and off without losing its settings.

A row has the field and level (as in the toolbar), *Draw as* (pixels or filled contours),
colormap, *Reverse*, *Auto range*, *Min* and *Max*, and *Opacity* (default 0.7). **Clear
outside range** (on by default) leaves values below Min or above Max uncoloured so the
fill underneath shows through. The first fill you add is *w ≥ 5 m/s at 3 km* (the range 5
to 30 m/s, cleared outside).

## Contours

*Contours* draws line overlays, up to six, one row each, in colours that cycle through a
set so that no two rows start the same.

| Setting | Meaning |
|---|---|
| Field, level mode, level | As for the fill. |
| **Levels** | The values to contour. `auto` (or empty) picks about eight evenly spaced levels across the field's range, leaving out zero for a field that crosses it. `5, 15, 25` lists them. `-4:4:1` is `start:stop:step`, with both ends included. |
| Color | The line colour. |
| Line width | 0.5 to 4. |
| **Dash negative** | Draws the contours of negative values dashed (on by default). |

The first row starts as w at 3 km with levels `5, 15, 25`. The second you add starts as
θ′ on model level 0 with levels `-6, -4, -2, -1`. Both are only starting points.

## Vectors

*Vectors* draws arrows or streamlines, up to three layers. The first row starts off (tick
its checkbox to show it); the others you add start on.

| Setting | Meaning |
|---|---|
| **Vector** | *Wind*, *Horizontal vorticity* (ξ, η) or *Baroclinic generation* (∂B/∂y, −∂B/∂x: the buoyancy torque on the horizontal vorticity). A vector is offered only when the run has the fields it is built from. A new row picks the first one not already shown, so the wind and the vorticity can sit on the map together. |
| **Height (km AGL)** | The height of the plane, in steps of 0.05. |
| **Frame** | Wind only: *Ground-relative*, *Grid-relative* or *Storm-relative*. Grid-relative is what CM1 writes; the others add back `umove`/`vmove` (and subtract the storm motion for storm-relative). Storm-relative uses the *Storm motion* chosen in the Sounding panel ([Soundings](soundings.md)). It starts as grid-relative when the run has `umove`/`vmove`, else ground-relative. |
| **Draw as** | *Arrows*, or *Streamlines* (instantaneous lines through the plane's flow, with an arrowhead on each). |
| **Arrows across** | How many arrows fit across the view (8 to 50, default 24). With streamlines this becomes *Streamline density*: higher puts the lines closer together. |
| **Ref. arrow** | The magnitude drawn one arrow spacing long, in the vector's units (m/s, 1/s or 10⁻⁴ s⁻²). Picking another vector resets it to a typical value (20 m/s for the wind, 0.02 1/s for the vorticity, 1 for the baroclinic generation). Not used for streamlines. |
| Color | The arrow or line colour. |

The 3D scene and cross-sections offer the same vectors; see [3D](3d.md) and
[Cross-sections](cross-sections.md).

## Moving around the map

- **Drag** pans, the **mouse wheel** zooms about the pointer, and the toolbar at the
  right edge of the map (it appears when the pointer is over the map) also has *box zoom*,
  *reset* and *save* (the image as PNG).
- **Zoom re-renders** the map at full resolution for the area in view. The title says
  whether the picture is `full res` or `1/2 res (zoom for full)`, and so on; the
  `maxpix` setting caps the pixels sent per axis. The shape stays true to scale (an equal
  kilometre on each axis) whatever the window size.
- **Hover** over the fill for the position (x, y in km) and its value. Hover over a
  storm-track fix for its time and tracked value.
- The area outside the model domain is shaded when you pan past it.
- The **title above the map** reads `t = <time> · <fill> @ <level> + <more fills> —
  <contours> …`, then a note when something is relative to a storm motion, then the
  resolution. It is the quickest way to see exactly what is drawn.

## Notes

- **Storm-relative vorticity.** Streamwise and crosswise vorticity are relative to the
  tracked storm's motion at that time when the track has a fix there, and to the domain
  motion (`umove`, `vmove`) otherwise. The title, colorbar and 3D legend say which was
  used ([Notes on the fields](fields.md)).
- **Pressure decomposition.** When a fill, more fill or contour is one of the pressure
  decomposition fields and the time is missing from the files, a button appears under
  the map to compute it ([Notes on the fields](fields.md#pressure-decomposition)). The
  title says which version of the script wrote the values in the files, and turns amber for
  files written by an early one.
- **Missing fields.** If a field is not in the output at the shown time (some are only
  written at certain times), the status line under the map says so and nothing is drawn.

## The tools

A tool sets what a click on the map does; see [Using cm1view](index.md#tool-rail) for how
the rail and panels behave. In short:

| Tool | A click on the map… | Page |
|---|---|---|
| **Sounding** | *Click a point* makes a sounding there; <kbd>Shift</kbd>-click adds up to four. *Drag a box (area mean)* averages over a box; <kbd>Shift</kbd>-drag adds one. | [Soundings](soundings.md) |
| **Section** | Click A, then B. | [Cross-sections](cross-sections.md) |
| **Track** | Click a storm to follow it through time. | [Storm tracking](tracking.md) |
| **Series** | Nothing: choose a field and region in the panel. | [Series and distributions](series.md) |
| **Distrib.** | Nothing: choose a field and region in the panel. | [Series and distributions](series.md#distributions) |
| **3D box** | Drag a box. The app switches to the 3D workspace and renders it. | [3D](3d.md) |

The 3D workspace can also be opened first: *Pick region on map* or *Use map view* there.
