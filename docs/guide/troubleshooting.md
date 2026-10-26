# Troubleshooting

Messages appear in the status line under the map or in the panel they concern; errors
are in red and warnings in amber. Start there; most say what to do.

## Getting started

**The page does not open.** Open the URL cm1view printed, ending in `/cm1view`. On a
cluster you need the SSH tunnel command it printed (or JupyterHub's proxy URL); see
[Running on a cluster](../hpc.md). If port 5006 is taken, cm1view uses the next free one
and prints it. Use `--port` or the `port` setting to choose.

**`no cm1out_[0-9]*.nc files found in …`.** The folder holds no output that matches the
`output_glob` setting (default `cm1out_[0-9]*.nc`). cm1view reads `output_format = 2`
(one time per file). If your files have another name, change `output_glob` in
[Settings](../settings.md).

**The run picker finds no runs.** It looks under *Where your runs live* (`runs_root`) and
your recent runs. Paste a folder into the box to list the runs inside it, or add the
folder to `runs_root`.

**It is slow, or the job is killed.** Memory depends on the grid size. See the table in
[Running on a cluster](../hpc.md#resources). The first sounding, section, 3D scene or
layer series at a new time reads whole 3D fields (about 2.5 s per field per CPU) and is
quick afterwards ([Performance](index.md#performance)).

## Fields and layers

**A field is missing from the list.** The lists hold the variables in the output plus the
derived fields whose inputs are in the output. If a variable was not written (check
`namelist.input`), neither it nor anything derived from it is offered
([Notes on the fields](fields.md)).

**`<field> is not in the output at <time>; the files have it at …`.** The variable is in
some of the files but not that one (swath fields and the pressure decomposition are only
written at some times). Move the time slider to a time that has it.

**The pressure decomposition does not draw.** If it is not in the files at that time, a
*Compute pressure decomposition* button appears under the map or section. It needs a lot
of memory ([Notes on the fields](fields.md#pressure-decomposition)). While a file is
being written the viewer reports it as *busy*; wait for the write to finish.

**The colours look wrong.** *Auto range* clips the extremes (0.5 to 99.5 percent); untick
it to type a range. A diverging colormap is cut, not stretched, when the range crosses
zero unevenly, so zero stays white ([The map](map.md#style-the-fill)).

## Tools

**There is no Track tool.** It needs the vertical velocity field (`winterp`) in the
output.

**`Track the storm first (Track tab), then compute around it`.** *Around tracked storm*
needs a track; make or load one ([Storm tracking](tracking.md)).

**`Draw a 3D region first`.** *3D region box* in the Series and Distribution regions
appears once you have drawn the box with the *3D box* tool.

**Tracking stops after one time.** The value was not past *Stop below* at the next time,
or the *From*–*To* window ends there. Lower the threshold, empty it to never stop, or
widen the window.

**The track jumps to another storm.** Turn on *Prefer nearest core* and lower the search
radius; do not use *Search whole domain each time*.

**A sounding that moves with the storm is missing at some times.** The track has no fix
there. Fill the gap by placing fixes by hand.

## Figures

**`Choose where to save the figure`.** Fill *Save as* with a folder and name. A figure of
several runs has no folder of its own.

**`The series are still being computed … save when they are done`.** Time-series and
time–height figures wait for their series; the preview's status line shows progress.

**The code editor in *Your own code* is blank.** The editor is loaded from a CDN, so a
browser without internet shows nothing. Tick *Plain text box*.

**A figure I opened does not run its code.** On purpose: code in a figure you open runs
only after you tick *Run the code*.

**A figure of another run is missing its storm.** Each run has its own track. Set it in
*Layers → Runs used*, or put `storm_tracks/<run>.csv` where cm1view looks
(`track_dirs`, `track_patterns`).

**The animation is huge or slow.** Lower the DPI and raise *Step (outputs)*; a GIF is
limited to 300 frames.

## 3D

**The 3D scene is blank or very slow.** It needs a browser with WebGL. Make the region
smaller (about 50 km across or less is full resolution), lower the *Top*, or choose a
coarser *Resolution*.

**Clicking a streamline does nothing.** An isosurface in front of it can catch the click.
Lower its opacity or switch it off.

## Settings

**A setting did not take effect.** `port`, `cache_gb` and `workers` apply after a restart.
A value set by an environment variable (`CM1VIEW_<NAME>`) or a command-line flag wins
over the file, and the settings window says when one does.

**A loaded `.pkl` series warned about code.** Pickle files can run code when loaded; open
only your own.
