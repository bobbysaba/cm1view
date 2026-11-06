# WoFS and WRF ensemble output

cm1view also reads the output of **WoFS** (the Warn-on-Forecast System) and of other
DART-cycled WRF ensembles laid out the same way. A WoFS experiment is **one run** in cm1view;
you choose which **member** (or the **ensemble mean**) to look at inside it, and the map,
soundings, cross-sections, series, 3D views, figures and export work on it as on a CM1 run. This
page covers what is different.

To try it without data, run `cm1view --demo wofs`: a small synthetic ensemble (three members,
terrain that rises toward the east, a storm moving north-east).

## What is read

A WoFS experiment folder (the **root**; its name is the run's name) holds one folder per date,
`YYYYMMDD`, each holding one folder per cycle, `YYYYMMDDHHMM`, and in each of those one WRF file
per member:

```
<root>/20220523/202205232200/wrfout_d01_2022-05-23_22:00:00_1
                             wrfout_d01_2022-05-23_22:00:00_2
                             ...
<root>/20220523/202205232203/wrfout_d01_2022-05-23_22:03:00_1
```

A run that cycles across 00 UTC has two date folders; their cycles are joined into one
timeline. Cycle folders straight in the root are read too (as when you open a date folder).
Only the `wrfout_d01_<time>_<member>` files are read. DART files, `wrfinput`, `obs_seq`, logs and
the experiment's other folders (`FCST`, `postpr`, `summary`, ...) are ignored. Each file is one
output time, so a run's times are the cycle times; they are shown in UTC, and run time is
seconds since the first cycle.

## Choosing the model

The run picker has a **model** box next to the search box: *Auto-detect* (the default) or a
model. Auto-detect looks at the file names, so a WoFS folder is found without any setting. Pick
*WoFS* to list only WoFS runs, or *CM1* for only CM1 runs. On the command line:

```
cm1view /path/to/root                  # detected from the file names
cm1view --model wofs /path/to/root
cm1view export --model wofs ...        # likewise for the export command
```

To look in a folder you type or paste into the picker, end it with `/` or press Enter. The
picker never searches shared folders (`/`, top-level folders, folders owned by root such as a
cluster's scratch or work root, or the folders above your home): type a folder of your own.

## Members and the mean

The picker lists the experiment once (e.g. *bnrhf_ctrl · WoFS · 36 members · 81 output
times*). It opens on member 1; the **WoFS member opened first** setting (`wofs_member`: a
member number, or `mean`) changes that. The **Member** box next to the run name in the viewer
switches to another member or the mean, keeping the view (time, map, fields, tools). The page
does not reload: what is shown is read again from the new member, and the address changes to
`?run=<member>` so a reload stays on it. Series come back from their cache, distributions and
parcel sets are worked out again. A figure being made keeps the runs it names. The save
boxes (track, series, session) move to the new member's folders unless you typed a path.
Each member has its own storm track file, and a file can hold several storms. The switch
loads the storm of the same name from the new member's file
([Several storms in one file](tracking.md#several-storms-in-one-file)).

Under the hood each member and the mean is read as a run of its own, with a path that does
not exist on disk:

| Member | Path |
|---|---|
| Member 1, 2, … | `<root>/mem01`, `<root>/mem02`, … |
| The ensemble mean | `<root>/mean` |
| The root itself | opens the `wofs_member` setting's member |

So each keeps its own cache, saved figures and exports, and members can sit side by side in
a [figure](figures-panels.md) (a layer's run list offers *bnrhf_ctrl · Member 5* and so on)
or be compared as a difference ([The map](map.md)).

## Winds

WRF writes no storm-relative winds, and how best to estimate a WoFS storm's motion is still
open, so for now WoFS winds are **ground-relative only**: the vector and streamline frame
lists offer just *Ground-relative* (the grid does not move, so grid-relative would be the
same), and the fields that take a storm motion (storm-relative helicity, STP, SCP,
streamwise and crosswise vorticity) are not listed. A saved session or figure asking for
storm-relative winds draws them ground-relative.

## Heights

WRF's model levels follow the terrain, so every column has its own heights, and they change
with time. cm1view keeps the native levels and carries the true heights of every column.
Wherever a height is asked for, you can use:

- **Model level (k)**: the level number, as in the file;
- **Height AGL (km)**: above the ground of each column, interpolated column by column;
- **Height MSL (km)**: above sea level, likewise.

Where a height is below the ground of a column, there is no value (it is left empty).

- **Cross-sections** have a **km MSL** vertical axis and draw the terrain, so the
  section shows the ground under the line. Values are interpolated column by column between
  the true heights.
- **Soundings** are drawn on the heights of their own column, so the lowest point is the
  surface there.
- **Series, profiles and column fields** (column maximum, d/dz and so on) use each column's
  heights too. Time–height plots, which have one axis for all columns, use the domain-mean
  height of the levels.
- The **3D view** and **3D scene figures** are in km MSL, with the terrain drawn.

Winds stay **grid-relative**; WoFS grids are centred on the projection's standard longitude,
so the rotation to true north is small.

## Base state and perturbations

Derived fields that need a base state (potential temperature, pressure and moisture
perturbations, and the like) take it from the **first time** of the run: the full 3D field of
that time. A perturbation is the change since then, point by point. WoFS has no separate
base-state profile, so this is the closest equivalent.

## Trajectories

WoFS writes no parcel files, so cm1view **traces** trajectories itself, through the 3D winds
of the run: a lattice of parcels seeded at the first time, carried by the grid-relative winds
with the true heights of each column, and kept at the output times. The result is stored in the
cache folder and reused, so each run is traced once. They then appear everywhere CM1 parcels do
([Parcels](parcels.md)).

Tracing needs outputs close together: between outputs far apart the winds' blend is a poor
guess. The `traj_max_interval` [setting](../settings.md) (default 300 s) says how long an
output interval is still accepted; a run whose output comes less often gets no trajectories,
and the Parcels tool says why. Set it to 0 to never turn them off.

## On the map

WoFS grids sit on the Earth (their map projection is in the files), so the map has a
**Boundaries** pill next to *Vectors*:

- **Lines**: coastlines, countries, states / provinces, lakes and US counties, each on or off
  (all but counties at first), in one colour and line width (counties thinner and fainter).
  They are drawn in your browser: turning them on or off, or restyling them, does not redraw
  the map.
- **Lat/lon lines**: dotted lines every *Every* degrees (*Auto*: a few across the domain),
  labelled along the bottom (longitudes) and left (latitudes) edges of the domain.
- Hovering over the map shows **lat, lon** under *x, y* and the value.

Sessions keep these settings. The lines ship with cm1view (public-domain US Census and
Natural Earth data); nothing is downloaded. Idealized CM1 runs have no Boundaries pill.

In figures, plan views get a **Map boundaries** layer (*Add a layer* → *Map boundaries*): the
same lines, each on or off, in one colour and width, and optionally the lat/lon lines with their
labels along each panel's bottom and left edges. A new figure of a WoFS run starts with one on
top; *New figure from the map* copies the Boundaries pill's choices (a light colour picked for
the dark map turns dark grey on white paper). The lines are cut to each panel's area and saved
with the figure's data, so the exported script redraws them with numpy and matplotlib alone.

## The ensemble mean

At each time every field in the files is averaged over the members that have a file there.
The mean is read in the reader processes, so a 3D field of many members takes a little longer
the first time and is cached after that. Meanwhile the map's status line says what is being
read and how far along it is (*Ensemble mean: reading th · 18/36 members · 4 s*), and so do
cross-sections, soundings, 3D views and figure previews; moving on to another time or field
stops the reading that is no longer needed. What it means for the fields:

- Fields in the files (temperature, winds, hydrometeors, reflectivity, WRF's 2D diagnostics
  such as hourly maxima) are **member means of the values**. The mean of reflectivity is
  therefore the mean of dBZ, not the dBZ of mean hydrometeors.
- Fields that cm1view derives (e.g. CAPE, vorticity, buoyancy, gradients) are computed **from
  the mean state**, not averaged member by member. The two differ for non-linear fields;
  to get the mean of a derived field, compute it on each member and average.
- The base state is the mean of the members' first-time fields, so perturbations are the
  mean's change since then.
- Trajectories follow the mean winds.

## Not supported

- **Pressure decomposition** (`pdecomp`): not offered for WoFS runs.
- **Probability-matched mean**: only the plain mean is available.
- **DART files** (prior and posterior output, `obs_seq`): ignored.
- Nests (`wrfout_d02`) and files other than `wrfout_d01_*` are not read.
