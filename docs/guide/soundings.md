# Soundings

The **Sounding** tool turns a point (or a box) on the map into a full sounding analysis:
a skew-T and hodograph, a table of parcel, shear, helicity and composite parameters, and
profiles of the storm-relative wind, shear, vorticity and temperature. Up to four
soundings can be shown together to compare places, times, or the storm-relative
environment as the storm moves.

## Making a sounding

Choose the **Sounding** tool, then the kind of click in its panel:

| Click mode | What it does |
|---|---|
| **Click a point** | Click the map for a sounding at that point. <kbd>Shift</kbd>-click adds another (up to four in all). |
| **Drag a box (area mean)** | Drag a box for the sounding averaged over it. <kbd>Shift</kbd>-drag adds one. Boxes and points mix freely, up to four in all. The box is drawn on the map. |
| **Domain mean** (button) | The sounding of the horizontal mean over the whole domain, which follows the time slider. |

Each sounding gets a number and a colour (1 blue, 2 pink, 3 green, 4 yellow) that its
marker on the map, its item in the tray and (in the *Colors* comparison style) its
curves share. **Clear** in the panel removes the soundings; the rail's **Clear** also
removes the other map markers.

A strip above the graphics names what is shown: the time, how it was averaged and each
sounding's position, e.g. `t = 90 min · single column · 1 (45.2, 30.1) km`.

The first sounding at a new time reads five full 3D fields (`th`, `prs`, `qv`,
`uinterp`, `vinterp`) and says so while it loads, a few seconds per field. They stay
cached, so every other click at that time is instant ([Performance](index.md#performance)).
A sounding pinned at another time reads only the columns it needs.

### Averaging

*Column average* (behind the settings button) averages a point sounding over a box of
the chosen width centred on the point: *Single column*, or a 1, 2, 5 or 10 km box. It
does not apply to boxes you drag or to the domain mean. The strip above the graphics says
`area mean` when every sounding is a dragged box or the domain mean.

## What is computed

Everything comes from the column of potential temperature, pressure, water vapour mixing
ratio and the wind, with winds put back to ground-relative using `umove` and `vmove`.

- **Parcels** are lifted pseudoadiabatically with a virtual-temperature correction and
  the LCL from Bolton (1980). CAPE agrees with MetPy to within about 3%.
    - **SB**: the lowest model level.
    - **ML**: the pressure-weighted mean of the lowest 100 hPa.
    - **MU**: the parcel of greatest θe in the lowest 300 hPa.
- **Winds** are resampled onto a 10 m grid (up to 16 km) for the shear and helicity layers.
- **Storm motion** comes from the setting below; the SRH, the storm-relative wind, the
  critical angle and the hodograph's storm marker all use it.
- **Effective inflow layer** (Thompson et al. 2007): the layer, searched among parcels in
  the lowest 300 hPa, where the parcel has at least 100 J/kg of CAPE and no more than
  250 J/kg of CIN. *Effective SRH* is over that layer, and *effective bulk shear* is from
  its base to halfway to the MU equilibrium level.
- **STP and SCP** use the SPC formulations: *STP (fixed)* from SBCAPE, SB LCL, 0–1 km
  SRH and 0–6 km shear; *STP (effective)* from MLCAPE, ML LCL, effective SRH, effective
  bulk shear and MLCIN (zero unless the effective layer starts at the ground); *SCP*
  from MUCAPE, effective SRH, effective shear and MUCIN.

### Sounding settings (the settings button)

| Setting | Meaning |
|---|---|
| **SB / ML / MU** | Which parcel the skew-T draws and shades (the table always gives all three). |
| **m/s / kt** | Wind units everywhere in the panel. |
| **Storm motion** | *Bunkers right-mover* (default), *Bunkers left-mover*, *0–6 km mean wind*, *Domain motion (umove, vmove)*, *Tracked meso motion*, or *Custom* with its own u and v (m/s). |
| **Column average** | As above. |
| **Base state** | Shows the run's base-state sounding dashed for reference, and as a column in the table. |
| **Follow time** | The soundings follow the time slider once it settles. Untick it to keep them at the time they were made. |
| **Move with tracked storm** | See [Comparing places and times](#comparing-places-and-times). Available when there is a track. |

*Tracked meso motion* uses the track's motion at each sounding's own time (so a pinned
sounding keeps the motion of its time), falling back to the right-mover where the track
has none. The storm-relative wind on the map and in 3D uses this same setting
([The map](map.md#vectors)).

## The graphics

### Skew-T

Temperature (red) and dewpoint (green) against log pressure, with the chosen parcel's
temperature dashed and CAPE shaded red and CIN blue. The skew-T also shows:

- adiabats and mixing-ratio lines (*Adiabats & mixing lines*),
- the LCL, LFC and EL of the shown parcel as ticks on the right edge, and height marks
  (1, 3, 6, 9, 12 km) on the left,
- wind barbs (in knots), about 36 evenly spaced in log pressure over the view, one
  column per sounding along the right edge,
- a title that names the parcel, e.g. `Skew-T · ML parcel`.

### Hodograph

The wind trace in `u`, `v`, coloured by height: 0–1 km red, 1–3 green, 3–6 yellow,
6–9 blue and 9–12 purple (up to the *Hodograph top*). It marks the Bunkers right and left
movers (RM, LM), circles the storm motion in use, and for the first sounding draws
dotted lines for the storm-relative inflow and the 0–500 m shear. Dots mark the heights in
*Hodograph heights (km)* (1, 3 and 6 km to start; e.g. `0.5, 1, 3, 6`, blank for none),
labelled on the first sounding. Rings give the speed.
The view is square and scaled to the data, and the title says it is ground-relative.

### Profile panels

Below the skew-T, five panels share a height axis (km AGL), up to the *Profile panels …
km AGL* selector (1, 3, 6, 10 or 15 km; it does not change the skew-T):

1. **Storm-relative wind**: speed relative to the chosen storm motion.
2. **Vertical wind shear**: |dV/dz| in 10⁻³ s⁻¹.
3. **Horizontal vorticity**: its streamwise and crosswise parts (10⁻³ s⁻¹) with respect
   to the storm-relative wind.
4. **Cumulative SRH**: storm-relative helicity from the ground to z.
5. **Potential temperature**: θ and θe.

### The parameter table

One column per sounding (and one for the base state) in two tables: *Thermodynamics*
and *Kinematics + composites*.

- **Thermodynamics**: SBCAPE, SBCIN, SB LCL; MLCAPE, MLCIN, ML LCL, LFC and EL; MUCAPE and
  the height of the MU parcel; 0–3 km CAPE; 0–3 km and 700–500 hPa lapse rates;
  precipitable water; freezing level; surface T / Td and θe.
- **Kinematics**: shear over 0–250 m, 0–500 m, 0–1, 0–3, 0–6 and 0–8 km; SRH over 0–250 m,
  0–500 m, 0–1 and 0–3 km; the effective inflow layer, effective SRH and effective bulk
  shear; Bunkers RM and LM, the 0–6 km mean wind and the storm motion used (direction
  and speed); the surface storm-relative wind; the critical angle.
- **Composites**: STP (fixed), STP (effective), SCP.

Values at or above a threshold are highlighted (SBCAPE and MLCAPE 1000 J/kg, MUCAPE
1500, 0–3 km CAPE 100, 0–1 km SRH 150, 0–3 km SRH 250, effective SRH 150, STP 1, SCP 4).

**Level units.** For a level row (the LCLs, ML LFC and EL, MU parcel, freezing level and
the effective inflow layer), click the units cell (`m ⇄`) to show it in hPa, and again
for metres. The choice stays while the soundings update.

## Comparing places and times

Several soundings share one set of graphics. *Compare* chooses how they are told apart:

| Style | Meaning |
|---|---|
| **Line styles** | The same colours, a different line style for each sounding (solid, dashed, dotted, dash-dot), with a legend. |
| **Colors** | Each sounding in its own colour. |
| **Tabs** | One tab per sounding, each with its own skew-T and profiles. |

**Comparing times.** *📌 Pin this time* freezes sounding 1 at the current time (with
nothing shown, it pins the domain mean). Sounding 1 keeps following the time slider, so
moving the slider overlays the two times. Pinned soundings keep their time in their label
(`@ 60 min`), up to four soundings in all.

**Following the storm.** To compare the environment *relative to the storm* over time,
make a [track](tracking.md) first. Then tick **Move with tracked storm** and click: the
sounding keeps its offset from the tracked storm (e.g. 10 km into the inflow) as time
changes, and pinning it compares the same storm-relative spot at two times. Its marker
on the map moves with the storm. At a time where the track has no fix, that sounding is
left out. Use *Storm motion → Tracked meso motion* to use the track's motion for the SRH
and storm-relative winds at each time.

## Zooming into a graphic

Click the skew-T/hodograph or the profile panels to expand the panel; the sounding
controls stay available. In the expanded view:

- **Drag a box** on the skew-T, the hodograph or a profile panel to zoom that panel. The
  figure is redrawn with that panel's new axis limits (temperature and pressure, u and v,
  or value and height), so axes, labels and line widths stay intact, a zoomed skew-T fills
  its panel, and the barbs and labels follow the zoom.
- After a zoom, dragging **pans** instead (the picture follows the pointer).
  <kbd>Shift</kbd>-drag does the other mode, and the ✥ / ⬚ button switches between pan
  and box zoom.
- **−** widens the view by 60%; **double-click** or **⟲** returns to the full view;
  **⤓** saves the image as SVG.
- The zoom is kept while the sounding updates (stepping in time, for example). Switching
  m/s ↔ kt or the profile top resets the panels it affects.
- **Hovering** reads values off the graphics into a strip under each image. On the
  skew-T it gives the pressure and temperature under the pointer and, for each sounding,
  the height, T, Td, parcel T, RH, θ, θe, qv and wind at that pressure. On the hodograph it
  gives the level nearest the pointer (height and wind). On the profile panels it gives
  every quantity at the pointer's height. A dashed line or dot marks the position read.

## Plot style

The palette button in the Sounding panel opens the look of the graphics:

| Group | Settings |
|---|---|
| Colours | Temperature, dewpoint, parcel and base state. |
| Line widths | T / Td, parcel, hodograph and profile lines. |
| Skew-T | *Skew-T top* (100–700 hPa) and the temperature range (*T left*, *T right*, in °C; blank is automatic). |
| Hodograph | *Hodograph rings* (automatic, 5, 10 or 20), *Hodograph top* (3–15 km) and *Hodograph heights (km)* (the heights marked along the trace). |
| Show | *CAPE / CIN shading*, *Wind barbs*, *Adiabats & mixing lines*. |

Changes only redraw the figures (no new analysis). **Default style** resets them.
Sounding panels in [figures](figures.md) have their own, fuller set of options.

## Soundings in figures

The picture button on a sounding in the items tray makes a figure from it
([Figures](figures.md)): skew-T and hodograph panels in the publication style, with the
same analysis and the same storm-motion choice.
