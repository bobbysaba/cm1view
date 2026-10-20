# cm1view

Interactive viewer for CM1 netCDF output (`output_format = 2`, one time per file):
plan-view map with layered fields, click-for-sounding analysis, vertical
cross-sections and 3D isosurfaces, in one dark-mode web app.

## Launch

From a Casper job (JupyterHub terminal or `qsub -I`), ask for at least
4 CPUs and 32 GB of memory. More CPUs mean faster first loads, because fields are
read in parallel.

```bash
/glade/work/rasaba/cm1view/cm1view.sh /path/to/cm1/run --port 5006
```

The launcher activates the `npl` conda env if needed and prints two URLs:

- **JupyterHub** (no setup): `https://jupyterhub.hpc.ucar.edu/stable/user/$USER/proxy/5006/cm1view`
  This only works when the viewer runs inside your JupyterHub job.
- **SSH tunnel**: `ssh -N -L 5006:localhost:5006 -J $USER@casper.ucar.edu $USER@<node>`,
  then open `http://localhost:5006/cm1view`.

Add `?t=30` to the URL to open at time index 30.

Options: `--cache-gb` (memory for cached 3D fields; default about 40% of the job's
memory), `--workers` (parallel reader processes), `--maxpix` (map pixels sent per
axis; zoom in to get full resolution).

## Using it

The top bar holds time controls, used by every view, and a **Map | 3D** switch. Both
workspaces use full width.

**Map workspace.** The toolbar above the map always shows the fill field and its
level (height km AGL, model level, or column max/min). Each pill opens its controls in a
drawer under the toolbar. Click the pill again to close it.
- *Style*: pixels or filled contours, colormap, range, opacity.
- *Contours A / B*, *Wind vectors*: the checkbox turns the layer on or off. The pill
  shows what is drawn.

Zooming re-renders at full resolution for the area in view. The analysis panel
(Sounding / Cross-section / Track) opens when a click mode is chosen or a result
arrives. The panel button in the top bar hides or shows it. Less-used options in the
Sounding and Track tabs sit behind **⚙ Settings**.

**Zooming soundings.** Click the skew-T/hodograph or the profile panels to open them
full-window: scroll to zoom, drag to pan, double-click to refit, Esc or ✕ to close. The
**Profile panels … km AGL** selector just above the profile panels sets their height
range. It does not change the skew-T.

**Click modes** (toolbar, right):
- *Sounding*: click to get a sounding; Shift-click adds up to 4 for comparison.
  This shows a skew-T, a hodograph, SB/ML/MU parcels, shear, SRH, the effective inflow
  layer, STP/SCP, critical angle, and profiles of storm-relative wind, shear,
  streamwise/crosswise vorticity, cumulative SRH and θ/θe. The base state is shown
  dashed for reference. *Column average* gives box-mean soundings.
- *Cross-section*: click A then B.
- *3D region*: drag a box. The app switches to the 3D workspace and renders it.
- *Track*: click a mesocyclone to follow it through time (see below).

**Comparing times.** *📌 Pin this time* freezes sounding 1 at the current time. Sounding 1
keeps following the time slider, so moving the slider overlays the two times (up to 4
soundings in all). Pinning with nothing shown pins the domain mean. To compare the
environment *relative to the storm* over time, make a track first. Then tick *Move with
tracked storm* and click: the sounding keeps its offset from the meso (e.g. 10 km into the
inflow) as time changes, and pinning it compares the same storm-relative spot at two
times. *Storm motion → Tracked meso motion* uses the track's motion at each sounding's
time for SRH, storm-relative winds and the hodograph.

**Meso tracking** (Track click mode and tab). Clicking snaps to the maximum of the tracked
field within the search radius (after box smoothing). The track then steps through the
output times: at each step it extrapolates the last motion and takes the maximum within
the radius. With *Prefer nearest core* (default) the field is first weighted by a Gaussian of distance from the expected position (σ = radius/2). That keeps the track from hopping to a neighbouring, slightly stronger core. It stops when the maximum drops below *Stop below*. The tracked field is
instantaneous 2–5 km updraft helicity (Σ w ζ Δz, from `winterp` and `zvort`), or ζ or w
at a chosen height. This costs a few seconds per time (one chunk per level).
- Clicking near an existing track at another time corrects it from that time on (or
  backward, if before the start), keeping the rest. Clicking far away starts a new track.
- *Place by hand* (Track tab): each click sets the fix at the shown time to exactly where
  you click. Tick *Snap click to max* to snap it to the nearby maximum instead. *Step time
  after each click* advances the slider so you can click through the storm's life. Each
  hand fix still records the tracked value at that spot. *Delete fix at this time*
  removes a fix. Hand fixes and auto-tracking can be mixed: an auto-track click near the
  track continues from there and keeps the earlier fixes.
- *Load* reads a track from the path box. It accepts a CSV or whitespace-separated file
  with `x_km, y_km` (grid) or `x_ground_km, y_ground_km`, plus one of `time_s`,
  `time_hms` or `time_index`. Times are matched to the run's output times.
- The `source` column records how each fix was made: auto, manual or loaded.
- *Save* writes the track on the server: `.csv` gives comma-separated columns, any other
  extension gives aligned columns. *Download* sends the same file to the browser. Header
  lines start with `#` (`pandas.read_csv(path, comment="#")`). Columns: time index, file,
  time, grid-relative and ground-relative position (km), ground-relative motion (m/s),
  the tracked value, and for UH the max w and ζ in the 2–5 km layer.

**3D workspace.** Pills for *Isosurfaces* (up to 4), *Surface winds* (horizontal arrows
at a chosen height), *Streamlines* and *Scene* (top, exaggeration, smoothing,
resolution, reflectivity floor).
- Streamlines are instantaneous, traced forward, backward or both ways through (u, v, w) from an n × n seed
  grid at a chosen height. They can be ground-, grid- or storm-relative and coloured by
  height or w. Storm-relative uses the storm motion selected in the sounding panel.
- Once a scene is shown, changing a 3D control re-renders it.

**Switching runs.** Click the run name in the header. You can type a directory, pick
one of the runs next to the current one, or pick a recent run. This reloads the page
with `?run=/path`. Opening a run frees the 3D caches of the other runs.

**Performance.** CM1 stores each 3D field one horizontal level per chunk. Plan views
are therefore instant, but anything that needs whole columns (soundings, sections, 3D)
must read the full 3D field once per time: about 2.5 s per field per CPU. Those fields
stay cached, so every later click at that time is instant. The first sounding at a new
time loads 5 fields (th, prs, qv, uinterp, vinterp).

## Notes

- CM1 writes winds relative to the moving grid. `umove`/`vmove` are read from
  `namelist.input` in the run directory and added back for ground-relative
  winds, hodographs and storm motions.
- Parcel calculations are pseudoadiabatic with a virtual-temperature correction.
  They were checked against MetPy: CAPE agrees within about 3%.
- Derived fields: θ′, p′, buoyancy (θρ′ including hydrometeor loading), θe, T, Td, RH,
  wind speed, horizontal divergence, horizontal vorticity, cloud/precip condensate.
  Add more in `cm1view/fields.py` (`_make_fields`).
- Plotly is vendored in `_vendor/` because the `npl` env does not include it.

## Layout

```
cm1view/run.py            file discovery, staggered->scalar reads, 3D cache, parallel reads
cm1view/fields.py         field catalog, derived fields, colormaps
cm1view/thermo.py         parcel theory (numba), kinematics, composite parameters
cm1view/sounding_plot.py  skew-T / hodograph / profiles / parameter table
cm1view/render.py         map + cross-section computations (contours, vectors, sampling)
cm1view/track.py          meso tracking + CSV/text export
cm1view/volume3d.py       isosurfaces, surface vectors, streamlines + Plotly scene
cm1view/registry.py       open runs shared by sessions, run discovery
cm1view/app.py            Panel UI
```
