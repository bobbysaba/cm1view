# Worked examples

Short walkthroughs that combine the tools. Each uses only what the other pages describe.

## Track a storm and sample its inflow

1. Pick a time when the storm is mature. Choose the **Track** tool, leave **Auto-track**
   on, and click the updraft on the map. Tracking runs through the output times; the path
   appears on the map and the Storm track chip in the top bar says how many fixes there
   are. If the track hops to another storm, tick *Prefer nearest core* and reduce the
   search radius, then click near the track to correct it ([Storm tracking](tracking.md)).
2. Choose the **Sounding** tool and, in its settings, tick **Move with tracked storm**.
   Click 10 km southeast of the storm, in the inflow. The sounding keeps that offset as
   you move the time slider.
3. Set *Storm motion* to **Tracked meso motion**, so the SRH and storm-relative winds use
   the storm's own motion at each time ([Soundings](soundings.md)).
4. To compare two times, press **📌 Pin this time**, then move the slider.

## Time evolution of an updraft or cold pool

1. Choose the **Series** tool. Pick w, *At a height*, 5 km, *Whole domain*, **Maximum**,
   and press **Compute**. Add the minimum of θ′ at the lowest level the same way, to get
   the cold pool; the two share the plot, with a second axis for different units.
2. For the vertical structure use *Layer (every level)* (0–12 km) and switch to
   **Time–height**.
3. Use *Around tracked storm* with a radius and an *Offset* to follow the storm's inflow or
   cold pool instead of the whole domain ([Series and distributions](series.md)).
4. **Save** the result as `.nc` to analyse it further, or make a figure from it.

## A storm-centred comparison of two runs

1. In the Figure workspace, use the quick start: *Plan views*, *Time*, 2 rows × 3
   columns. Press **Make the figure**.
2. In *Layers → Runs used*, add the second run (type to filter, or paste a folder) and
   give each run a label and a colour. Check that each has a storm track.
3. In *Panels → Grid and size*, set *Rows are* to *Runs* and *Columns are* to *Times*;
   pick both runs (*Runs, one per row*) and fill the times from the shown time. Set
   *Plan-view area* to *Centred on tracked storm*.
4. Put a reflectivity fill and a w contour in *Layers*, and set *Colorbars* to *One for
   the figure* in *Style*.
5. **Save as** a name, choose the format and DPI, and press **+ script & data** to keep the
   data and a script that redraws the figure ([Figures](figures.md)).

## A swath of the strongest updraft

1. Make a plan-view figure and open its fill layer.
2. In *Over a time window*, choose **Maximum (swath)** with the field w at 5 km (or a
   2D swath field such as updraft helicity), and set *From* and *To* (blank: the whole
   run). Use *Every nth output* to thin the work.
3. The swath is placed where the ground is at the panel time. Add a *Storm track* layer to
   show the path over it ([Figure layers](figures-layers.md)).

## An animation

1. Build a 1 × 1 plan-view figure centred on the storm.
2. In *Export → Animation (GIF)* set the *End time*, a *Step (outputs)* that gives under
   300 frames, a low DPI (about 100) and the frames per second.
3. Press **Save animation**. Tick *Also save the frames (PNG)* if you want a video made
   with `ffmpeg` ([Export, animations and the script](figures-export.md#animations)).

## The same figure for another run

1. Make the figure for the first run and, in *Export → Templates*, **Save as template**.
2. Open the other run (click its name in the top bar), go to the Figure workspace, choose
   the template and press **Apply to this run**. The times move to the shown time of the
   new run, keeping their spacing.
