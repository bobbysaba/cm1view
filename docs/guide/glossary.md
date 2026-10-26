# Glossary

| Term | Meaning |
|---|---|
| **AGL** | Above ground level. All heights in cm1view are km AGL unless a label says otherwise. |
| **Base state** | The horizontally uniform initial state of the run (`th0`, `prs0`, `qv0`, `u0`, `v0`, `rho0`). Perturbations such as θ′ and p′ are the departure from it. |
| **Bunkers right / left mover (RM, LM)** | The storm motions of the Bunkers et al. (2000) method, from the 0–6 km mean wind and shear. The right mover is the default storm motion. |
| **Bundle** | What *+ script & data* saves: the image, a script, the plotted arrays, the spec and the drawing code. |
| **Cache** | The 3D fields held in memory (`--cache-gb`), and the computed series, swaths and distributions kept in the cache folder (`cache_dir`). |
| **CAPE, CIN** | Convective available potential energy; convective inhibition. |
| **Column max / min** | The largest / smallest value in each vertical column. |
| **Critical angle** | The angle between the storm-relative inflow and the 0–500 m shear. |
| **Derived field** | A field computed by cm1view from native ones (θ′, buoyancy, θe, streamwise vorticity, …). |
| **Distribution** | Every value of a field in a region at one time, summarised for plotting. |
| **Effective inflow layer (EIL)** | The layer where parcels have at least 100 J/kg of CAPE and no more than 250 J/kg of CIN (Thompson et al. 2007). |
| **Fill** | The coloured field layer of a map, section or figure. |
| **Fix** | One position of a track, at one output time. |
| **Frame** | What a wind is relative to: *ground-relative*, *grid-relative* (as CM1 writes it) or *storm-relative*. |
| **Grid-relative** | Relative to the moving model grid. CM1 writes winds this way; `umove` and `vmove` give the grid's motion. |
| **Ground-relative** | Relative to the ground: grid-relative plus (`umove`, `vmove`). |
| **Layer** | One thing drawn in a figure panel: a fill, contours, shading, vectors, a track or a section line. |
| **Meso** | The tracked mesocyclone or updraft; the *tracked meso motion* is the track's own motion. |
| **Native field** | A variable written in the CM1 output. |
| **Output time** | One CM1 output file (one time per file). |
| **Part** | One block of a combined figure, with its own panels, layers and style. |
| **Pin** | In soundings, freeze sounding 1 at its time. In 3D, keep a streamline in its own colour for comparison. |
| **Recipe** | What a series or distribution computes: the field, height or layer, region and reduction. It is the cache key. |
| **Run** | A folder of CM1 output files. |
| **Spec** | A figure's settings as a data structure (saved as `_spec.json`). |
| **SRH** | Storm-relative helicity over a layer. |
| **STP, SCP** | Significant tornado parameter; supercell composite parameter (SPC formulations). |
| **Storm-relative** | Relative to a storm motion: the one chosen in the Sounding panel, or the tracked storm's. |
| **Streamwise / crosswise vorticity** | The horizontal vorticity along, and across (positive to the left), the storm-relative horizontal wind. |
| **Swath** | The maximum (or minimum, mean, sum) of a field over a window of output times, at each point. |
| **Template** | A figure's layout and look without its runs, applied to another run. |
| **UH** | Updraft helicity, Σ w ζ Δz over a layer (2–5 km). |
| **`umove`, `vmove`** | The grid translation speed in `namelist.input`. |
| **VPPGA** | Vertical perturbation pressure gradient acceleration, −(1/ρ) ∂p′/∂z, in the pressure decomposition fields. |
| **Workspace** | One of the top bar's **Map**, **3D** and **Figure** views. |
