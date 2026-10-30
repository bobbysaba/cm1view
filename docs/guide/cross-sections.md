# Cross-sections

The **Section** tool draws a vertical slice of the run along a straight line on the map,
with the same layered look as the map: a fill, more fills, contours and vectors.

## Drawing a section

1. Choose the **Section** tool.
2. Click **A**, then click **B** on the map. The line is drawn between them and both ends
   are labelled.
3. The Section panel opens to the right of the map and draws the slice. Clicking a
   third time starts a new section at that point.

The section is sampled along the line every grid spacing (up to 1200 points), bilinearly
in the horizontal and linearly between model levels in the vertical. The horizontal axis
is the distance from A toward B in km, the vertical axis the height in km AGL. A section
needs whole 3D fields, so the first one at a new time loads them (a few seconds per
field; the panel shows the progress) and later changes at that time are quick
([Performance](index.md#performance)). Only 3D fields are offered.

The section follows the time slider once time settles (when the panel is open); the
status line above the plot names the time, the fields, A and B, and the length of the
section, e.g. `t = 90 min · Reflectivity + w — Temperature perturbation · A (40.0, 30.0)
→ B (65.5, 38.2) km, 26.8 km long`.

## The layers

The panel's toolbar works like [the map's](map.md#the-toolbar): the fill field with its
**Style ▾**, then **More fills ▾**, **Contours ▾** and **Vectors ▾**. Each list of rows
adds a layer with *Add …* and removes it with ✕, and a row's checkbox hides it without
losing its settings.

- **Style** and **More fills** (up to three): the same controls as on the map —
  pixels or filled contours, colormap, *Reverse*, *Auto range* (or *Min* and *Max*),
  *Opacity*, and for more fills *Clear outside range*. Each fill has a colorbar of its
  own. A diverging colormap stays white at zero ([The map](map.md#style-the-fill)).
  The first fill's *Style* also has **Difference: minus another time or run**, as on
  the map: the section through the other run (the same A and B, in km) is subtracted.
- **Contours** (up to six): field, *Levels* (`auto`, `5, 15, 25` or `-4:4:1`), colour,
  line width, and *Dash negative*. The first row starts as w with levels
  `-10, -5, 5, 10, 20, 30` and the second as θ′ with levels `-6, -4, -2, -1` (if the run
  has these fields).
- **Vectors** (up to three): the wind, horizontal vorticity or baroclinic generation
  ([The map](map.md#vectors)), drawn as arrows **in the plane of the section**: the
  component along the section (A toward B) and the vertical component (w for the wind,
  ζ for the vorticity). Settings are the *Vector*, *Frame* (wind only), *Arrows across*
  (8 to 60, default 28), *Ref. arrow* and colour. A section has every height, so there is
  no height setting. The arrows are scaled so a reference arrow looks the same length
  along the section and up, whatever the plot's shape.

Unlike on the map, the fills and contours take the fields at all heights, so the level
controls are missing.

The *Top (km)* slider sets how high the section goes (default 15 km or the top of the
model). The A / B labels sit at the bottom of the plot.

## Reading the plot

- **Hover** for the position (distance along the section and height) and the value of
  the first fill.
- The toolbar above the plot has *box zoom* (the default drag), *wheel zoom*, *pan*,
  *reset* and *save* (PNG). Zoom and pan stay inside the sampled section. *Reset* goes
  back to the limits set in the plot style (below), not necessarily the whole section.
- The colorbar label names the fill, and notes the storm motion used when it is
  storm-relative (streamwise or crosswise vorticity); see [Notes on the fields](fields.md).
- A pressure-decomposition field that is missing at the shown time shows the same
  *Compute pressure decomposition* button as the map
  ([Notes on the fields](fields.md#pressure-decomposition)).

### Plot style (palette button)

| Setting | Meaning |
|---|---|
| **From (km)**, **To (km)** | The distance range shown; blank is the whole section. |
| **Bottom (km)**, **Top (km)** | The height range shown; blank is from 0 to the *Top* slider. |
| **Plot height (px)** | 250 to 900. |
| **Font size** | 8 to 20. |
| **Grid lines**, **A / B labels** | Show or hide. |
| **Default style** | Resets all of the above. |

Changing these redraws the plot without computing the section again. A new section
(different length or top) resets the view; changes of the layers keep your zoom.

## Making a figure

The picture button on the section in the items tray starts a *Vertical cross-sections*
figure from it ([Figures](figures.md)). A figure can also show several sections at once (different
times, fields or runs) and can draw the A–B line on a plan view above it.
