# cm1view

Interactive viewer for CM1 netCDF output (`output_format = 2`, one time per file):
plan-view map with layered fields, click-for-sounding analysis, vertical
cross-sections and 3D isosurfaces, in one dark-mode web app.

## Install

cm1view needs its own Python environment, made from `environment.yml` (conda-forge,
pinned to the tested versions). With [Miniforge](https://github.com/conda-forge/miniforge)
(or any conda / mamba):

```bash
git clone git@github.com:bobbysaba/cm1view.git
cd cm1view
conda env create -f environment.yml      # once; about 2.7 GB
conda activate cm1view
```

This installs cm1view itself in editable mode, so `git pull` updates it. After a pull
that changes `environment.yml`: `conda env update -f environment.yml --prune`.
On a cluster, put Miniforge in a work or project folder rather than home, which
usually has a small quota.

## Launch

On a cluster, run it inside a batch job (interactive or a JupyterHub terminal) with
at least 4 CPUs and 32 GB of memory. More CPUs mean faster first loads, because
fields are read in parallel.

```bash
conda activate cm1view
cm1view /path/to/cm1/run --port 5006     # or ./cm1view.sh, same options
```

The run is optional: without one, the viewer opens the `default_run` setting or a page
listing the runs in your folders. If port 5006 is taken (another user on the node), the
next free port is used and printed.

It prints the URLs to open:

- **This machine**: `http://localhost:5006/cm1view` (a laptop or workstation).
- **JupyterHub**, when started from a JupyterHub terminal (needs `jupyter-server-proxy`
  on the hub): `<hub>/user/$USER/proxy/5006/cm1view`.
- **SSH tunnel**, when it runs on a remote machine:
  `ssh -N -L 5006:localhost:5006 -J $USER@<login-host> $USER@<node>`, then open
  `http://localhost:5006/cm1view`. The login host is taken from the batch job
  (PBS / Slurm) or the `login_host` setting.

Add `?t=30` to the URL to open at time index 30.

Options: `--cache-gb` (memory for cached 3D fields; default about 40% of the job's
memory), `--workers` (parallel reader processes), `--maxpix` (map pixels sent per
axis; zoom in to get full resolution), `--config` (another settings file).

## Settings

The first time cm1view opens in a browser, it asks where your CM1 runs live; the
other settings are pre-filled (from your recent runs, `$SCRATCH`, and a
`pdecomp_new_fixed*.py` in your home, `$WORK` or `$SCRATCH` folders) and can be
changed then or later with the ⚙ button in the top bar (or the *Config file* tab, which
edits the file itself). They are saved in `~/.config/cm1view/config.toml`
(`$CM1VIEW_CONFIG` or `--config` for another file).

| Setting | Default | What it does |
|---|---|---|
| `runs_root` | (required) | folders searched for runs; the run picker starts there |
| `default_run` | none | run opened when no run is given |
| `figures_dir` | `~/cm1view/figures` | figures go to `<this>/<parent>_<run>/` |
| `exports_dir` | `~/cm1view/exports` | saved series / tracks go to `<this>/<parent>_<run>/series`, `/tracks` |
| `cache_dir` | `~/.cache/cm1view` | throwaway files (computed series) |
| `pdecomp_script` | none | pressure-decomposition script; empty hides the feature |
| `track_dirs` | `storm_tracks` | where storm track files are found (a plain name: that folder in the run folder or up to 4 above it) |
| `track_patterns` | `{parent}_{name}.csv`, `{name}.csv`, … | track file names tried in each folder |
| `output_glob` | `cm1out_[0-9]*.nc` | which files are CM1 output |
| `allow_writes_to_output` | off | lets the pressure decomposition write into output files |
| `cache_gb`, `workers` | auto | from the job's memory and CPUs (restart to apply) |
| `port`, `maxpix` | 5006, 900 | server port (restart to apply), map pixels per axis |
| `login_host` | from the batch job | login node shown in the printed SSH tunnel command |

Each setting can also come from an environment variable `CM1VIEW_<NAME>` (lists
separated by `:`) or a command-line flag, which win over the file; the settings window
says when one does. Path settings apply to the next save; save boxes that still point
at the old default folder follow a change. Saving over an existing file asks first.
A figure from several runs has no run folder of its own: choose its folder in *Save as*
(the last one chosen is offered next time).

## Using it

The top bar holds time controls, used by every view. The **Map | 3D** switch appears
once a 3D region has been picked. Both workspaces use full width.

**Map workspace.** The toolbar above the map always shows the fill field and its
level (height km AGL, model level, or column max/min). Each pill opens its controls in a
drawer under the toolbar. Click the pill again to close it.
- *Style*: pixels or filled contours, colormap, range, opacity.
- *Contours A / B*, *Winds*: the checkbox turns the layer on or off. The pill
  shows what is drawn. Winds are drawn as arrows or as streamlines (*Draw as*; the
  density slider sets how close the streamlines are), ground-, grid- or storm-relative.

Zooming re-renders at full resolution for the area in view. The analysis panel
(Sounding / Cross-section / Track) opens when a click mode is chosen or a result
arrives. The panel button in the top bar hides or shows it. The expand button next to
it (⤢) gives the panel the whole window; **Map** brings the map back. Less-used options
in the Sounding and Track tabs sit behind **⚙ Settings**.

**Zooming soundings.** Click the skew-T/hodograph or the profile panels to expand the
panel. All sounding controls stay available. In the expanded view, drag a box on the
skew-T, the hodograph or a profile panel: the figure is redrawn with that panel's axes
limits (temperature / pressure, u / v, value / height), so axes, labels and line widths
stay intact (zoomed skew-Ts fill their panel; barbs and labels follow the zoom). −
widens the view, double-click or ⟲ returns to the full view, ⤓ saves the image (SVG).
The zoom is kept while the sounding updates (e.g. stepping in time); switching m/s ↔ kt
or the profile top resets the affected panels.
In the expanded view, hovering reads values off the graphics in a strip under each
image. On the skew-T it shows the pressure and the temperature under the pointer, and
each sounding's height, T, Td, parcel T, RH, θ, θe, qv and wind at that pressure. On the
hodograph it shows the level nearest the pointer (height, wind). On the profile panels
it shows every quantity at the pointer's height. A dashed line or dot marks the
position read.

**Plot style** (🎨 in the Sounding tab): colours of temperature, dewpoint, parcel and
base state; widths of the T/Td, parcel, hodograph and profile lines; skew-T top and
temperature range; hodograph ring spacing and top; CAPE/CIN shading, wind barbs and
adiabats on or off. Changes only redraw (no new analysis). *Default style* resets them.

**Level units.** In the parameter table, click the units cell (m ⇄) of a level row
(LCL, LFC, EL, MU parcel, freezing level, effective inflow) to show it in hPa; click
again for metres. The choice stays while the soundings update. The
**Profile panels … km AGL** selector just above the profile panels sets their height
range. It does not change the skew-T.

**Click modes** (toolbar, right):
- *Sounding*: click to get a sounding; Shift-click adds up to 4 for comparison.
  This shows a skew-T, a hodograph, SB/ML/MU parcels, shear, SRH, the effective inflow
  layer, STP/SCP, critical angle, and profiles of storm-relative wind, shear,
  streamwise/crosswise vorticity, cumulative SRH and θ/θe. The base state is shown
  dashed for reference. *Column average* gives box-mean soundings.
- *Area sounding*: drag a box to get the sounding averaged over it; Shift-drag adds a
  box (up to 4, mixed freely with point soundings). The box is drawn on the map.
- *Cross-section*: click A then B. A and B are marked at the ends of the distance axis.
- *3D region*: drag a box. The app switches to the 3D workspace and renders it.
- *Track*: click a storm to follow it through time (see below).

**Comparing times.** *📌 Pin this time* freezes sounding 1 at the current time. Sounding 1
keeps following the time slider, so moving the slider overlays the two times (up to 4
soundings in all). Pinning with nothing shown pins the domain mean. To compare the
environment *relative to the storm* over time, make a track first. Then tick *Move with
tracked storm* and click: the sounding keeps its offset from the meso (e.g. 10 km into the
inflow) as time changes, and pinning it compares the same storm-relative spot at two
times. *Storm motion → Tracked meso motion* uses the track's motion at each sounding's
time for SRH, storm-relative winds and the hodograph.

**Storm tracking** (Track click mode and tab). The default follows the method of
`phd_scripts/storm_tracking.ipynb`: the maximum of w at 1 km after a Gaussian smoothing
of σ = 3 grid points. Clicking snaps to the maximum of the smoothed field within the
search radius; *Find strongest* starts from the domain-wide maximum instead. The track
then steps through the output times: at each step it extrapolates the last motion and
takes the maximum within the radius. With *Prefer nearest core* (default) the field is
first weighted by a Gaussian of distance from the expected position (σ = radius/2). That
keeps the track from hopping to a neighbouring, slightly stronger updraft. *Search whole
domain each time* reproduces the notebook exactly (it can jump between storms). It stops
when the maximum drops below *Stop below*. Other tracked fields (⚙ Settings): ζ at a
height, or instantaneous 2–5 km updraft helicity (Σ w ζ Δz, from `winterp` and `zvort`);
choosing one loads its default height, smoothing (Gaussian or box) and stop value. This
costs about a second per time for w or ζ, a few seconds for UH.
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
- Click a streamline to select it (it turns yellow, its seed marked). A card plots a
  field along it against distance from the seed (negative = upstream), with height on
  the right axis. Its axes fit the field. Scroll to zoom, drag to pan, and use the
  toolbar for box zoom or reset; ⤢ enlarges the card. The field can be any 3D field, the speed, or the streamwise vorticity in
  the streamline's frame. The selection follows the same seed when the scene re-renders
  (e.g. in time). Isosurfaces in front of a line can catch the click: lower their
  opacity or switch them off.
- Once a scene is shown, changing a 3D control re-renders it.

**Series tab** (analysis panel). One field reduced over a region at every output time:
any native or derived field, at a height or over a layer (a layer also keeps every
level, for the *Time–height* view), over the whole domain, the map view, the 3D box or
a disc around the tracked storm (with an offset, e.g. the inflow), as min / max / mean /
percentile. Results are cached in `<cache_dir>/series` per run and recipe, and
saved as .nc (everything), .csv / .txt or .pkl. Series in other units than the first
get their own y axis on the right. Click a plot to go to that time. **⚙ Plot** sets
the time and y limits (heights in the time–height view) and the time–height
colormap and colour range. For layer series it can also reduce over a sub-layer
(e.g. max w over 0–2 km out of a 0–10 km layer) for min / max / mean. All of these
come from the computed result without recomputing. *Auto limits* clears them. The
3D region box is offered as a region once one has been drawn.

**Figure workspace** (Map | 3D | **Figure**). Publication figures, previewed at their
final size. Start from the map view, the cross-section, the Series tab, the soundings,
or a default grid; *Panels show*:
- *Plan views* / *Vertical cross-sections*: layers (fill, contours, shading, vectors or
  streamlines, storm track, section line), panels in time, in field, as a runs × times
  grid or each with its own run and time; centred on each run's tracked storm, a fixed
  box or the whole domain.
- *Time–height (series)*: a row per series and a column per run (as in
  `pub_figs.ipynb`), one colorbar per row; a series can be plotted as its d/dz or d/dt.
- *Time series*: series with the same panel number share a panel; series in other units
  get their own y axis; one series from several runs is coloured by run.
- *Soundings*: skew-T log-p with adiabats, parcel, barbs and a hodograph inset; several
  soundings (runs, times, storm-relative spots) per panel.

**Runs** lists the runs panels can come from (e.g. tornadic vs non-tornadic), each with
its storm track (the Track tab, or `storm_tracks/<run>.csv`, found automatically; see
`track_dirs` / `track_patterns`).
**Annotate** adds a contour key (nested circles, as `funcs.circlelegend`) and text,
markers, arrows, lines, boxes and circles. **Export** saves the image, and optionally a
stand-alone script with the plotted arrays and spec: the script redraws the identical
image without the viewer. The image and script sit side by side, the arrays and spec in
`_src/` next to them; the script finds them relative to itself, so the folder can be
moved or copied.

**Switching runs.** Click the run name in the header. You can type a directory, pick
one of the runs next to the current one (*Runs here*), browse with *Folders* (↑ .. goes
up, a click opens a folder; ● marks folders with CM1 output), or pick a recent run. This reloads the page
with `?run=/path`. Open runs share one 3D cache (`--cache-gb`); the least recently used
fields are freed first, so tabs on different runs do not empty each other's cache.

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
- Derived fields: θ′, p′, buoyancy (θρ′ including hydrometeor loading), θρ and θρ′
  (as `funcs.theta_rho`), θe, T, Td, RH, wind speed, horizontal divergence, horizontal
  vorticity, streamwise and crosswise horizontal vorticity, cloud/precip condensate.
- Streamwise / crosswise vorticity are relative to the tracked storm motion at that time
  when a track has a fix there, otherwise to the domain motion (umove, vmove). The map
  title, colorbar, section title, 3D legend and streamline card say which was used.
  Crosswise is positive to the left of the storm-relative wind.
- **Pressure decomposition** (field group of that name): p_b, p_l, p_nl, the matching
  accelerations acc_b (B − ∂p_b/∂z/ρ), acc_l, acc_nl, plus p_l + p_nl, acc_l + acc_nl
  and the total. Where post-processing wrote them into the output files they are read
  from there (any file subset; the map title says which script version wrote them, and
  warns for files written before `pdecomp_new_fixed.py`). Elsewhere, a *Compute pressure
  decomposition* button runs the `pdecomp_script` setting (e.g.
  `phd_scripts/pdecomp_new_fixed_mp.py`, the multi-CPU version of
  `pdecomp_new_fixed.py`: same math, identical output) on that time in a separate
  process, with its inputs read in
  parallel first: ~25–35 s with 4 CPUs (~80 s on one). If the job lacks the memory, the 3D cache is emptied first;
  if still short, it says so.
  *Write into the output file* (offered when `allow_writes_to_output` is on) writes the
  result with the script's
  own `write_data` (float64, `pdecomp_version` attribute; about +40 s and +9 GB per
  file for a 1280×1280×115 grid), replacing values from older scripts. While it writes,
  the viewer releases that one file and reports it as busy. If the job is killed during
  a write, the file can be left damaged, as with the script itself. Unticked, the
  result is kept in memory only. The last 2 computed times stay in memory either way.
  For older-script files the button offers *Recompute … and overwrite*. Use
  `--pdecomp-script` or `$CM1VIEW_PDECOMP_SCRIPT` for another script with the same
  functions.
  Add more in `cm1view/fields.py` (`_make_fields`).

## Layout

```
cm1view/run.py            file discovery, staggered->scalar reads, 3D cache, parallel reads
cm1view/fields.py         field catalog, derived fields, colormaps
cm1view/thermo.py         parcel theory (numba), kinematics, composite parameters
cm1view/sounding_plot.py  skew-T / hodograph / profiles / parameter table
cm1view/render.py         map + cross-section computations (contours, vectors, sampling)
cm1view/track.py          meso tracking + CSV/text export
cm1view/volume3d.py       isosurfaces, surface vectors, streamlines + Plotly scene
cm1view/zoomview.py       zoomable image component (sounding graphics)
cm1view/series.py         time series of reduced fields (Series tab): compute, cache, files
cm1view/figure.py         figure spec, panel data, export (image, script, data, spec)
cm1view/figdraw.py        matplotlib drawing of a figure (copied into exported scripts)
cm1view/figui.py          Figure workspace UI
cm1view/pdecomp.py        pressure decomposition: file fields, on-demand runs of the user's script
cm1view/registry.py       open runs shared by sessions, run discovery
cm1view/config.py         settings: config file, precedence, save folders, run search
cm1view/settings.py       settings window (first run and ⚙) and the overwrite prompt
cm1view/picker.py         run picker (header dialog and the page without a run)
cm1view/app.py            Panel UI
tests/                    headless smoke tests (smokeN.py) + browser screenshots (uiN.py);
                          `conda activate cm1view; source tests/env.sh` first
                          (a throwaway settings file)
```
