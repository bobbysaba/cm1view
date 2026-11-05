# WoFS and WRF ensemble output

cm1view also reads the output of **WoFS** (the Warn-on-Forecast System) and of other
DART-cycled WRF ensembles laid out the same way. A run in cm1view is one **member**, or the
**ensemble mean**, and the map, soundings, cross-sections, series, 3D views, figures and
export work on it as on a CM1 run. This page covers what is different.

To try it without data, run `cm1view --demo wofs`: a small synthetic ensemble (three members,
terrain that rises toward the east, a storm moving north-east).

## What is read

A WoFS folder (the **root**) holds one folder per cycle, named `YYYYMMDDHHMM`, and in each of
them one WRF file per member:

```
<root>/202205232200/wrfout_d01_2022-05-23_22:00:00_1
                    wrfout_d01_2022-05-23_22:00:00_2
                    ...
<root>/202205232205/wrfout_d01_2022-05-23_22:05:00_1
```

Only the `wrfout_d01_<time>_<member>` files are read. DART files, `wrfinput`, `obs_seq` and
logs in the same folders are ignored. Each file is one output time, so a run's times are the
cycle times; they are shown in UTC, and run time is seconds since the first cycle.

## Choosing the model

The run picker has a **model** box next to the search box: *Auto-detect* (the default) or a
model. Auto-detect looks at the file names, so a WoFS folder is found without any setting. Pick
*WoFS* to list only WoFS runs, or *CM1* for only CM1 runs. On the command line:

```
cm1view /path/to/root                  # detected from the file names
cm1view --model wofs /path/to/root
cm1view export --model wofs ...        # likewise for the export command
```

## Member and mean runs

Each member and the mean is its own run, addressed by a path that does not exist on disk:

| Run | Path |
|---|---|
| Member 1, 2, … | `<root>/mem01`, `<root>/mem02`, … |
| The ensemble mean | `<root>/mean` |
| The root itself | opens member 1 |

The picker lists them all under the root. Because every one has its own path, they keep
their own cache, saved figures and exports, and can sit side by side in a
[figure](figures-panels.md) (the *Runs* of a layer) or be compared as a difference ([The map](map.md)).

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

## The ensemble mean

At each time every field in the files is averaged over the members that have a file there.
The mean is read in the reader processes, so a 3D field of many members takes a little longer
the first time and is cached after that. What it means for the fields:

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
