# Storm tracking

The **Track** tool follows a feature (an updraft, a mesocyclone, a pressure low) from
output to output and keeps its position at each time: a **track** made of **fixes**. The
track is shared by everything storm-relative in the viewer:

- soundings that **move with the storm** and the **tracked meso motion** for SRH
  ([Soundings](soundings.md));
- series and distributions around the storm ([Series and distributions](series.md));
- storm-relative vorticity ([Notes on the fields](fields.md));
- figures centred on the storm, and the storm-relative frame of the 3D streamlines
  ([Figures](figures.md), [3D](3d.md)).

The **Storm track** chip in the top bar shows the state: `No storm track`,
`Load storm track (<file>)` when the run has a track file the viewer found,
`Storm track · 41 fixes, 20 min–60 min` when there is one, and an amber
`no fix at this time` when the shown time has none. Clicking the chip loads the found file
(if there is no track yet) and opens the Track panel. The tool only appears for runs with
the vertical velocity (`winterp`).

## Tracking automatically

Choose **Auto-track** in the panel and click the storm on the map.

1. The click snaps to the maximum of the smoothed field within the *search radius*
   (untick *Snap click to max* to start exactly where you clicked).
2. For each next output time, the tracker **extrapolates** the storm's last grid-relative
   motion to a predicted position and takes the maximum of the smoothed field within the
   search radius of it.
3. It stops when the maximum is no longer beyond *Stop below* (leave it empty to never
   stop) or at the end of the *From*–*To* window.

**Find strongest** starts instead from the domain-wide maximum at the shown time, and
follows that. **Stop** abandons a running track and keeps the fixes made so far; progress
is shown while it runs (about a second per time for a field at one height, a few seconds
for UH).

### What is tracked

The *Track on* list offers the choices the run has the fields for:

| Track on | The field | Default height | Smoothing | Stop |
|---|---|---|---|---|
| **Updraft: w at height** | w | 1 km | Gaussian, σ = 3 grid spacings | below 5 m/s |
| **2–5 km updraft helicity** | instantaneous UH = Σ w ζ Δz over 2–5 km (from `winterp` and `zvort`) | (the layer) | 1 km box | below 50 m²/s² |
| **Vertical vorticity at height** | ζ | 1 km | 1 km box | below 0.01 1/s |
| **Pressure low: min p′ at height** | the minimum of p′ | 1 km | 1 km box | above −0.5 hPa |
| **Other field (max or min)…** | any field, with *Track the* maximum or minimum | the last height | 1 km box | none |

Choosing one loads its default height, smoothing and stop value; change them freely
afterwards.

### Settings (the settings button)

| Setting | Meaning |
|---|---|
| **Height (km)** | The height of the tracked field (not for UH). |
| **Smoothing (km)** and **filter** | The field is smoothed before the maximum is picked, so the fix follows the storm and not single-grid-point noise. *Gaussian*: σ in km. *Box*: the width in km. |
| **Search radius (km)** | How far from the predicted position to look at each time (default 5). |
| **Prefer nearest core** | On by default. Weights the field by a Gaussian of the distance from the predicted position (σ = radius / 2) before picking the maximum. A nearby core then beats a slightly stronger one farther away, which keeps the track from hopping to a neighbouring updraft. |
| **Search whole domain each time** | Takes the domain-wide maximum at every time (the radius and *Prefer nearest core* no longer apply). It can jump between storms. |
| **Fix at** | *Peak*: the strongest point. *Centroid*: the field-weighted centre of the area around the peak where the smoothed field is beyond the **Centroid cutoff** (% of the way from the background, 0, to the peak; default 50). The centroid gives a smoother track than the single peak point. |
| **Stop below / above** | The value past which the storm counts as lost. (It reads *above* for a minimum.) |
| **From / To** | The first and last times to track. By default from the clicked time to the end of the run. Choose a *From* earlier than the clicked time to track backward as well, or any other first and last time. The shown time must lie inside the window. |

### Correcting a track

- Clicking **near** an existing track (within three search radii of its nearest fix, with
  the same field and settings) corrects it from that time on, or backward if the click is
  before the track's start, and keeps the rest.
- Clicking **far** away starts a new track.
- **Clear track** removes the track (and the soundings that move with it).

## Placing fixes by hand

Choose **Place by hand** in the panel. Each click sets the fix at the shown time exactly
where you click, and the panel hides the *From*, *To* and *Stop* settings. Tick **Snap
click to max** to move it to the nearby maximum instead. **Step time after each click**
(on by default) advances the slider by one output so you can click through the storm's life.
Each hand fix still records the tracked value at that spot. **Delete fix at this time**
removes one fix.

Hand fixes and auto-tracking can be mixed: an auto-track click near the track continues
from there and keeps the earlier fixes.

## Reading the track

- On the map the track is a yellow line with a dot at each fix and a circled cross at the
  fix of the shown time. Hover a dot for its time and tracked value.
- A time series in the panel plots the tracked value against time, with the shown time
  circled (shown once there are values).
- A table lists every fix: time, grid-relative and ground-relative position, motion and
  value (the columns below).
- The status line gives the number of fixes, the first and last times, and the **mean
  ground-relative motion** from the first fix to the last (speed, the direction it is
  *from*, and u, v). If tracking stopped after one time it says why: the value was not
  past the stop threshold at the next time, or the window ended there.

## Saving and loading

- **Save** writes the track on the server, to the path in the box. A `.csv` name gives
  comma-separated columns; any other extension gives aligned columns. If the file exists
  it asks before overwriting. The box starts at the place the viewer looks for tracks
  (the first existing `track_dirs` folder, named by the first plain entry of
  `track_patterns`), so a saved track is found next time and the chip offers it.
- **Download** sends the same file to your browser.
- **Load** reads a track from the path box.

### The file format

Header lines start with `#` and record the run, the tracked field, the search and
smoothing settings, the fix method, the grid translation (`umove`, `vmove`) and a
description of each column (read it with `pandas.read_csv(path, comment="#")`). The
columns:

| Column | Meaning |
|---|---|
| `time_index`, `file`, `time_s`, `time_hms` | The output's index, file name, time in seconds and time as `h:mm:ss`. (The table in the panel leaves out `file` and `time_s`.) |
| `x_km`, `y_km` | Position on the model grid (which translates with the storm in a moving-grid run). |
| `x_ground_km`, `y_ground_km` | Ground-relative position: grid + (`umove`, `vmove`) × time. |
| `u_motion_ms`, `v_motion_ms` | Ground-relative storm motion, from centred differences of the ground-relative track. |
| the tracked value | Named for what was tracked, e.g. `w_1km`, `zeta_1km`, `uh_2_5km`, `prspert_1km`, `max_<field>_<height>`. The raw extreme within the smoothing box around the fix. For UH the file also has `w_max_2_5km` and `zeta_max_2_5km`. |
| `source` | How the fix was made: `auto`, `manual` or `loaded`. |

**Loading** accepts a CSV or whitespace-separated file. It needs

- a time column: `time_s`, `time_hms` (`h:mm:ss`), `time_index`, or `time` in model
  minutes (seconds if the values are too large to be minutes); and
- a position: `x_km`, `y_km` (grid), or `loc_x`, `loc_y`, or `x_ground_km`,
  `y_ground_km` (converted to grid with `umove`, `vmove`).

Times are matched to the run's output times; rows that do not match one are skipped
(unless given by `time_index`). A column called `value`, or named like `w_*`, `zeta_*`,
`uh_*`, `prspert_*`, `max_*` or `min_*`, becomes each fix's value.

### Finding track files automatically

The viewer looks for a track by the run's folder name. The `track_dirs` setting says
where (a plain name such as `storm_tracks` means that folder inside the run folder or up
to four levels above it) and `track_patterns` which file names to try in each (default
`{parent}_{name}.csv`, `{name}.csv`, …). The same lookup finds each run's track when
a run is added to a [figure](figures.md). See [Settings](../settings.md).
