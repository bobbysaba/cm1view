# Parcels

Runs with parcel output (CM1's `iprcl = 1`, written to `cm1out_pdata.nc`) get a
**Parcels** tool on the map's tool rail. With it you choose parcels on the map and draw
their trajectories, coloured by height or by any parcel variable, with heads where the
parcels are at the shown time, on the map, on the cross-section and in the 3D view, and
plot their values.

The tool only appears when the run folder has parcel files (the `parcel_glob` setting,
default `cm1out_pdata*.nc`). Parcel output split over several files, e.g. one per
restart, is read as one, joined by time; where two files overlap in time the later one
is used.

## Parcel times

Parcel output usually comes much more often than the 3D output. The viewer keeps the
two apart:

- the **time slider** still steps through the 3D output;
- the **heads** are where the parcels are at the shown time: interpolated between the
  two parcel times around it (untick *Between parcel times: interpolate* to use the
  parcel time at or before it instead);
- **tails** use every parcel time, not just the 3D ones.

The bottom of the panel says how many parcels and parcel times there are, how many 3D
outputs fall within the parcel output's span, and which parcel time the heads are at.
At a time outside the parcel output there are no heads.

## Choosing parcels

Pick how a click chooses with the buttons at the top of the panel:

- **Click a point**: the parcels within *Radius* (km, horizontally) of the click.
- **Drag a box**: the parcels inside the box.

Both apply the rest of the form:

| Setting | What it does |
|---|---|
| *From z*, *To z* | only parcels in this height range (km above sea level); empty: any height |
| *Choose at* | the parcel time the choice is made at: the one nearest the shown time, or the first parcel time (where CM1 seeded them) |
| *Where*, *Min*, *Max* | only parcels whose value of this variable is in the range (an empty Min or Max is open) |
| *At most*, *Keeping* | a cap on the number kept: every n-th of the chosen parcels, or a random sample (the same sample each time) |

Each choice becomes a **set**, named `set 1`, `set 2`, … and drawn in its own colour.
The status line says how many parcels it holds and, when the cap applied, of how many.
Choosing at the first parcel time is the quickest: when the parcels were seeded on a
regular lattice (as CM1 does) the viewer works out which ones are in the box or near the
point without reading the file.

## Sets

- **Sets**: pick one to rename (*Name*), remove or save.
- **Save set** writes its parcels to `<exports_dir>/<parent>_<run>/parcels/<name>.npz`
  (asking before replacing a file); **Saved sets** and **Load** bring one back, in this
  run or another session.
- The **items tray** under the map lists the sets; click one to open it in the panel,
  or remove it with its ×.

Sessions keep the sets (as the rule that chose them) and how they are drawn.

## Exporting a set

**Export set** opens a row under the sets: write the chosen set's trajectories to a
file for your own analysis.

- **Variables**: any of the parcel output's, and any 3D field sampled at the parcels
  (see [below](#3d-fields-at-the-parcels)); x, y, z are always written.
- **Format**: *netCDF* — dimensions `time` and `parcel`, each variable `(time,
  parcel)` as CM1 writes them; or *CSV* — one row per parcel and time it has a
  position at (`parcel,time_s,x_km,y_km,z_km,...`), after `#` lines saying what the
  file holds (the set, its rule, the units).
- **Times**: all parcel times, up to the shown time, or the last minutes (the *Minutes*
  of the tails); *Every n-th* thins them.
- **File**: by default `<exports_dir>/<parent>_<run>/parcels/<set>.nc` (or `.csv`),
  next to the saved sets; you are asked before a file is replaced.

**Write** runs in the background with progress; **Stop** leaves no file. Positions are
in km, x and y grid-relative, z above sea level; `parcel` is CM1's parcel number (1 to
n, as in the parcel output). A sampled field's variable is `<field>_at_parcels`. Missing
values (a parcel that left the domain) are NaN; where a parcel wraps across a periodic
boundary its x or y jumps by the domain length.

Without the viewer, a saved set:

```bash
cm1view export /path/to/run --parcels . --list          # variables and saved sets
cm1view export /path/to/run --parcels updraft --fields w,b,thpert --from 60 --to 90
cm1view export /path/to/run --parcels updraft --csv --every 5
```

`--fields` are parcel variables (default: all), a 3D field's name (or `@name`) the field
at the parcels; `--time`, `--from`, `--to`, `--every` pick parcel times (minutes);
`--out` ending in `.csv` writes CSV too; `--relative MIN` adds storm-relative `x_sr`,
`y_sr` ([Relative to the storm](#relative-to-the-storm)).

## Drawing

| Setting | What it does |
|---|---|
| *Colour by* | the set's colour, a parcel variable (height `z` by default), or a 3D field sampled at the parcels ([below](#3d-fields-at-the-parcels)), with its own colorbar (2nd–98th percentile, symmetric about 0 for signed values) |
| *Colormap* | the colormap when coloured by a variable |
| *Tails* | all parcel times, up to the shown time, the last *Minutes* before it, or none (heads only) |
| *Line width*, *Opacity* | the trajectories' look |
| *Heads at the shown time* | the dots where the parcels are now; hover one for its set, parcel number, height and value |
| *Seen from* | the grid, as the map is drawn, or a frame moving with the storm ([below](#relative-to-the-storm)) |

Very long tails are drawn at every n-th parcel time so that the map stays quick (at most
200 000 segments). In a periodic domain a parcel that leaves through one side and comes
back through the other is not joined across the domain. Parcels that leave an open
domain stop where they left.

Trajectories are read once per set and kept in the cache folder (the `cache_dir`
setting), so redrawing, recolouring or reopening a session reads nothing again. The
first read of a widely spread set can take a while on very large parcel files: each
parcel time has to be read whole. A compact set (a box or a point) reads much less.

## Relative to the storm

*Seen from* draws the tails in a frame that moves with the storm, so they show the
parcels' paths relative to it (inflow into the updraft, say) and not across the grid:

- *The grid (as the map)*: positions as CM1 wrote them.
- *Moving with the tracked storm*: the frame follows the centre of the storm track
  (the **Track** tool), straight between fixes and on at the motion between the first
  two (last two) fixes before (after) the track. A track of fewer than two fixes moves
  nothing; the note under the panel says so. Editing the track redraws the tails.
- *Moving at a motion*: at a ground-relative (u, v) in m/s, which starts as the
  soundings' storm motion (e.g. Bunkers right-mover) when there are soundings.

Each point of a tail is moved back by how far the frame went across the grid between
its parcel time and the shown time. At the shown time nothing moves: the heads are where
they are on the map, over the fields of that time, and so the tails change as the time
does. On the cross-section and in the 3D view the reference time is the section's and
the scene's own. The plot is not affected (its x and y stay grid-relative). With a
frame other than the grid, *Export set* can also write `x_sr`, `y_sr` (km): the
positions in that frame, the same as x, y at the shown time.

In figures, a parcels layer and a 3D scene's parcel set have *Tails seen from* too
(*From the map* brings the viewer's choice): the reference time is each panel's, the
track is the layer's run's. Without the viewer, `cm1view export RUN --parcels SET
--relative MIN` writes `x_sr`, `y_sr` in a frame moving at `--storm U,V`, or else with
the run's storm track (`--track`), the same as x, y at model time MIN (minutes).

In a moving grid (`imove = 1`) the parcel positions are taken as grid-relative, as the
map's; the frame's motion is measured against the grid's (umove, vmove).

## 3D fields at the parcels

*Colour by*, the plot's *Plot* and *Against*, and in figures a parcels layer's *Colour
by* and a parcel series' *Variable* list, besides the parcel output's own variables,
**3D fields at the parcels**: any 3D field of the run (native or derived, as on the map)
read at each parcel's position. In space the field is interpolated trilinearly; at a
parcel time between two 3D outputs, it is the value of each of the two fields at where
the parcel is then, weighted linearly in time. So this follows the parcels at their own
cadence, but the field itself only changes as fast as the 3D output does. Parcel times
before the first or after the last 3D output have no value.

The first use reads every 3D output time once (the status line counts them), so for a
large run it takes about as long as stepping through all its times; the values are then
kept in the cache folder, like the trajectories, and sampled again only when the 3D
files change. Heights are matched as the cross-section matches them: the parcel's
height against the grid's, the same over flat ground. In a figure spec and in scripts
these variables are written `@` + the field's name, e.g. `@thpert` or `@ddz.w`.

## The w budget

Along a parcel, its vertical acceleration is the sum of the forces on it:

Dw/Dt = b + vpg + the rest

with *b* the buoyancy and *vpg* the vertical perturbation pressure gradient
acceleration that CM1 writes for each parcel, and the rest subgrid mixing and numerical
diffusion. When the parcel output has *w*, *b* and *vpg*, two more variables are in
every parcel variable list (under **w budget**), usable anywhere the others are
(colour, plots, figure layers and series, export):

- **Dw/Dt** (`dwdt`): the time derivative of the parcel's own *w* over the parcel times
  (centred differences);
- **Dw/Dt − b − vpg** (`wres`): what *b* and *vpg* leave of it.

Dw/Dt is only as good as the parcel output's cadence resolves *w*: with parcel output
every few seconds it is close to the model's own, with output every minute or more it
is smoothed, and the rest takes up the difference. Neither is stored; both are computed
from *w*, *b* and *vpg* when needed.

In the plot under the panel, **w budget** draws the budget of the set picked in *Sets*:
the *Centre* (mean or median over its parcels) of each term at every parcel time, with
a *Band* if you choose one. **Integrated since the set's time** draws instead how much
each term changed the parcels' *w* since the time the set was chosen (Δw, and the
time integrals of *b*, *vpg* and the rest), which add up: Δw = ∫b dt + ∫vpg dt + ∫rest
dt. Before the set's time the integrals are negative (what the term added on the way
there). For parcels chosen in an updraft, this tells whether buoyancy or the pressure
gradient lifted them there.

In time-series figures, see [Parcel series](#parcel-series): **+ w budget** adds the
same as a panel of four cards.

## On the cross-section

With a cross-section open, the parcels within *Section ±* km of its line (A to B) are
drawn on it, projected onto the section: along it from A, at their height. They follow
the section's time: the heads are where the parcels were at the time the section shows,
and the tails end there.

*Tails on the section* chooses which tails:

- **Their parts near it**: every part of any parcel's tail that lies within the
  distance, so you see where parcels crossed the section's slab;
- **Whole, of parcels near it now**: the whole tails of the parcels whose heads are near
  the section, so you see where they came from.

Heights are above sea level, as CM1 writes them; over flat ground that is the section's
height axis.

## In the 3D view

*In the 3D view* (on by default) draws the sets' tails and heads in the 3D scene, inside
its region and below its top, at the scene's time, coloured as on the map. The 3D view
draws at most 300 000 points of tails (every n-th parcel time beyond that).

## The plot

Under the panel's settings, a plot of the sets' parcels:

- **Over time**: *Plot* (any parcel variable) at every parcel time, a line for each
  parcel (at most 300 per set, every n-th beyond that) with *Each parcel*, the set's
  *Centre* (mean or median) and a *Band* (min to max, 10–90th or 25–75th percentile,
  or mean ± 1 standard deviation), in the set's colour. The yellow line marks the shown
  time.
- **Two variables now**: *Plot* against *Against*, one dot per parcel at the shown time
  (interpolated between parcel times, as the heads are). Hover a dot for its parcel.

Sessions keep the section, 3D and plot settings too.

## In figures

Plan-view and cross-section figures take a **Parcels** layer. *From the map* and *From
the cross-section* (Figure editor) add one layer for each of the viewer's sets, drawn as
the viewer draws them: colour, tails, heads, line width, opacity, and on a section the
distance and which tails. On the kind's node, *Parcels* in *Add a layer* adds the next set not drawn
yet; a panel's own layers can add one too.

A layer keeps the **rule** that chose its set (the time, box, height range, point and
radius, value range and cap), not the parcels themselves. The figure chooses them again
from the parcel output of the layer's run when it is drawn, so a saved figure, a
template and `cm1view-render` need only the rule (an exported script keeps the arrays it
drew, as for every layer). *Parcels*
on the layer's card swaps in another set of the viewer or a saved set (`parcels/` under
the run's exports folder).

Each panel draws the tails up to its own time (or all parcel times, the last minutes,
or none) and the heads where the parcels are at that time, interpolated between parcel
times when *Between parcel times: interpolate* is ticked. An animation follows the same
parcels in every frame. A template applied to another run chooses its parcels as long
after (or before) the shown time as the original did.

Coloured by a variable, the layer's colours run from *Min* to *Max*, or with those blank
from the 2nd to the 98th percentile of what the panel shows (symmetric about 0 when it
straddles 0): give both when several panels should agree. The panel's colorbar shows the
parcels' colours when the panel has no fill layer (the first fill's otherwise).
A layer draws at most 300 000 points of tails (every n-th parcel time beyond that). On a
plan view, the parts of tails well outside the panel are left out. When a layer has
nothing to draw (no parcel output in its run, no parcels meeting the rule), the
preview's note says so.

A **3D scene** figure draws parcel sets too (*Parcels*, on the scene): tails as lines and
heads as balls at the scene's time, only inside the scene's region and below its top
(the lines break where they leave it). *Copy the 3D view* and the photo icon on the 3D
box in the items tray bring the viewer's sets along when the 3D view shows them (*In
the 3D view*); **+ Parcels** adds the next one. Line width and head size are in points, so they keep their
size at any export DPI. The first set coloured by a variable gets the parcel colorbar
(Look → *Parcel colorbar*, left by default). Changing how the parcels look, or which
parcels are drawn, computes no isosurfaces again.

### Parcel series

A **time-series** panel draws a parcel variable over the parcel times: **+ Parcels**
(with parcel output) adds the viewer's next set not drawn yet (or a saved set), with *w* to
start. It picks its **Run**,
*Parcels* (another viewer set or a saved one), *Variable* and *Plot*: the value, or
*d/dt along the parcel*, *Change since the set's time* or *∫ dt since the set's time*
(the time when the set was chosen: its rule's time, else the first parcel time). At
each parcel time it draws a *Centre line* (mean or median over the
parcels there then) and a *Band over the parcels* (min to max, 10–90th or 25–75th
percentile, mean ± 1 sd), shaded like an ensemble band; *Parcels' own lines* draws that
many parcels too (spread through the set, up to 500), faint or as other lines. A parcel
that left the domain drops out of the centre and band from then on.

The card has the series cards' look (colour, line, width, markers, y axis, axis label,
label, panel, time zero, added to its run's) and shares panels and y axes with them by units. Its times
are the parcel times, so its line is finer than the series computed at the 3D output
times beside it. Like a layer, it keeps the set's rule and chooses the parcels again
when drawn; a template moves the rule's time as for a layer. Nothing is computed in the
background: the parcels' values are read (and cached) when the figure is drawn. In a
time–height figure the card is kept but not drawn.

**+ w budget** (with *w*, *b* and *vpg* in the parcel output) adds the [w
budget](#the-w-budget) of the viewer's next set in a new panel, a card for each term in
its own colour (mean over the parcels, no band): *Rates* (Dw/Dt, b, vpg and Dw/Dt − b −
vpg, m s⁻²) or *Integrated since the set's time* (Δw and the time integrals of the
others, m s⁻¹, all on one axis). The cards are ordinary parcel series cards: add a band,
change the centre, or move one to another panel.
