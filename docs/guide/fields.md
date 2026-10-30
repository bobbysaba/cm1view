# Notes on the fields

What the field lists contain, how winds are handled, and what the derived fields and the
pressure decomposition are.

## Which fields you get

The field lists (grouped by kind) hold

- every **native** variable in the run's output, with a sensible label, units, colormap
  and range for the usual CM1 names, and
- the **derived** fields below, each offered only if the variables it needs are in the
  output.

Native fields are grouped as **Radar** (`dbz`, `cref`), **Kinematics** (winds and
vorticity components), **Thermodynamics** (`th`, `prs`, `pi`, `rho`, `qv`),
**Microphysics** (the other mixing ratios), **Swaths & 2D** (surface and accumulated
fields such as `rain`, `sws`, `svs`, `sps`, `sus`, `shs` and the translated `…2`
versions), **Turbulence**, **Budgets**, **Base state** (`th0`, `prs0`, …) and **Pressure
decomposition**. Water-substance mixing ratios are shown in g/kg and pressure in hPa.
Each entry in a list reads `label [name]`, with the CM1 variable name in brackets.

## Winds and the moving grid

CM1 writes winds relative to the moving grid. `umove` and `vmove` are read from
`namelist.input` in the run directory and added back for ground-relative winds,
hodographs and storm motions. The fields `uinterp`, `vinterp`, `winterp` are the winds
interpolated to the scalar points, and `xvort`, `yvort`, `zvort` the vorticity
components. Vectors can be shown ground-, grid- or storm-relative
([The map](map.md#vectors)).

## Derived fields

| Name | Field | Definition |
|---|---|---|
| `thpert` | θ′ (K) | `th − th0` (the base state `th0` is in the output) |
| `prspert` | p′ (hPa) | `prs − prs0` |
| `buoy` | Buoyancy (m/s²) | `g (θρ − θρ0) / θρ0` with θρ including the loading of all hydrometeors |
| `thrho`, `thrhopert` | θρ and θρ′ (K) | density potential temperature, and its departure from the base state |
| `thetae` | θe (K) | Bolton (1980) eq. 43 |
| `tempc`, `dewc` | Temperature and dewpoint (°C) | from θ, p and q<sub>v</sub> |
| `rh` | Relative humidity (%) | with respect to liquid water |
| `wspd` | Wind speed (m/s) | ground-relative |
| `hdiv` | Horizontal divergence (10⁻³ s⁻¹) | ∂u/∂x + ∂v/∂y |
| `hvort` | Horizontal vorticity magnitude (1/s) | √(ξ² + η²) |
| `wstream`, `wcross` | Streamwise and crosswise vorticity (1/s) | the horizontal vorticity along and across the storm-relative horizontal wind (below) |
| `bgen_x`, `bgen_y` | Baroclinic generation of horizontal vorticity (10⁻⁴ s⁻²) | (∂B/∂y, −∂B/∂x): the buoyancy torque, also drawn as the *Baroclinic generation* vector |
| `zstretch`, `ztilt`, `ztend` | Vertical-vorticity stretching, tilting and their sum (10⁻⁴ s⁻²) | ζ ∂w/∂z, ξ ∂w/∂x + η ∂w/∂y (below) |
| `okubo` | Okubo–Weiss parameter (10⁻⁴ s⁻²) | s<sub>n</sub>² + s<sub>s</sub>² − ω² (below) |
| `qcloud`, `qprecip` | Cloud and precipitation condensate (g/kg) | qc + qi, and qr + qs + qg + qhl, where those are in the output |
| `p_dyn`, `acc_dyn`, `acc_tot` | Pressure decomposition sums | see below |

Other derived fields are defined in `cm1view/core/fields.py` (`_make_fields`); see
[Developing](../developing.md) for how to add one.

### Derivatives of any field

The **Derivative** select beside a Field (the map's fill, a figure's fill, contour and
shading layers on plan views and cross-sections, the Series tab, and a figure's series and
profile cards) plots a derivative of that field instead, per km:

| Derivative | Name | What |
|---|---|---|
| ∂/∂z | `ddz.<field>` | on each model level, centred between the levels above and below (one-sided at the bottom and top), on the stretched levels; at a height, interpolated between the two levels' values. 3-D fields only. |
| ∂/∂x, ∂/∂y | `ddx.<field>`, `ddy.<field>` | centred differences on the grid's x and y (stretched grids too), at the level shown |
| \|∇h\| | `gradh.<field>` | √((∂/∂x)² + (∂/∂y)²) |

Units are the field's per km; a wind's (m/s per km) read 10⁻³ s⁻¹, so ∂w/∂z of 5 is
5 × 10⁻³ s⁻¹. Column max / min are of the derivative (the largest ∂w/∂z in the column), and
a cross-section's derivative is taken on the 3-D grid, so it agrees with the map at the
same level. Derivatives of derived fields work the same way (∂θ′/∂x, ∂B/∂z, ...). The
starting colour range is half the field's own per km; use Auto range on the map.

In a series or profile the derivative is taken first and then reduced over the region:
the maximum ∂w/∂z at 2 km, not ∂/∂z of the maximum w. Horizontal derivatives are taken
with the grid points just outside the region, so the values at its edge are the map's.

### Vorticity tendencies

The *Vorticity tendencies* group has the terms of the vertical-vorticity equation that
make or concentrate ζ, in 10⁻⁴ s⁻² (a ζ of 0.02 s⁻¹ in ∂w/∂z of 0.01 s⁻¹ stretches at 2):

| Name | Term |
|---|---|
| `zstretch` | stretching, ζ ∂w/∂z |
| `ztilt` | tilting of horizontal vorticity into the vertical, ξ ∂w/∂x + η ∂w/∂y |
| `ztend` | stretching + tilting |
| `okubo` | Okubo–Weiss, W = s<sub>n</sub>² + s<sub>s</sub>² − ω², with s<sub>n</sub> = ∂u/∂x − ∂v/∂y, s<sub>s</sub> = ∂v/∂x + ∂u/∂y and ω = ∂v/∂x − ∂u/∂y: negative where rotation dominates the strain (a vortex), positive where strain dominates |

ζ, ξ and η are CM1's `zvort`, `xvort` and `yvort`; the derivatives are those of the
**Derivative** select (below), so ∂w/∂z is centred on the stretched levels and the
horizontal ones on the grid, and Okubo–Weiss uses the winds on the scalar points. Like
the other fields they work on the map, cross-sections, column max / min, 3D, series and
figures; in a series the horizontal derivatives use the points just outside the region.
Baroclinic generation of horizontal vorticity is `bgen_x`, `bgen_y` (above).

### Column fields

The *Column fields* group has 2D fields made from the 3D fields over a fixed layer of
each column, so they work wherever a 2D field does (the map, series, distributions,
figures), and a series of one reads only the levels of its layer in the region:

| Name | What | Layer |
|---|---|---|
| `uh25` | Updraft helicity, ∫ w ζ dz (m²/s²) | 2–5 km AGL |
| `uh01` | Updraft helicity, ∫ w ζ dz (m²/s²) | 0–1 km AGL |
| `zvmax01` | Maximum ζ (1/s) | 0–1 km AGL |
| `wmax` | Maximum w (m/s) | the whole column |

The integral is over the layer exactly: each model level counts with the part of its grid
cell (between the `zf` levels) inside the layer. A maximum is over the model levels whose
cells reach into the layer. w and ζ are `winterp` and `zvort`; updraft helicity is that of
Kain et al. (2008), so it is negative in an anticyclonic updraft or a cyclonic downdraft
(CM1's own `shs` swath is its running maximum). The layers are fixed for now.

### Sounding parameters

The *Sounding parameters* group has the bulk shear, storm-relative helicity, parcel
CAPE, CIN and LCL and the composite parameters of every column, as 2D column fields (so
on the map, series, distributions and figures):

| Name | What | Layer |
|---|---|---|
| `shear01` | Bulk shear, \|V(1 km) − V(lowest level)\| (m/s) | 0–1 km AGL |
| `shear06` | Bulk shear (m/s) | 0–6 km AGL |
| `srh01` | Storm-relative helicity (m²/s²) | 0–1 km AGL |
| `srh03` | Storm-relative helicity (m²/s²) | 0–3 km AGL |

They are computed as the [Soundings](soundings.md#what-is-computed) tab computes them:
from the lowest model level up to the layer top, with the wind linearly interpolated
between the levels (to the layer top exactly, where the sounding's 10 m grid can stop a
few metres short, so SRH may differ from the sounding's by about 1%). Helicity is
relative to the **tracked storm motion** at that time when the track has a fix there,
and otherwise to the domain motion, as for streamwise vorticity (below); the map title
and colorbar say which. Shear does not depend on it.

Parcel parameters, from the whole column:

| Name | What |
|---|---|
| `sbcape`, `mlcape`, `mucape` | CAPE (J/kg) of the surface-based, 100 hPa mixed-layer and most-unstable parcels |
| `sbcin`, `mlcin`, `mucin` | CIN (J/kg, negative) of those parcels |
| `sblcl`, `mllcl`, `mulcl` | LCL height (m AGL) of those parcels |
| `stp` | Significant tornado parameter, fixed layer: SBCAPE, SB LCL, 0–1 km SRH, 0–6 km shear |
| `scp` | Supercell composite parameter, fixed layer: MUCAPE, 0–3 km SRH, 0–6 km shear, MUCIN |

The parcels are those of the [Soundings](soundings.md#what-is-computed) tab, lifted the
same way, so a column's values are the sounding's there. STP is the sounding's *STP
(fixed)*. The sounding's *SCP* uses the effective inflow layer, which needs a parcel
lifted from every level of a column. That is too slow for a map, so the map's `scp`
takes its formula with 0–3 km SRH for effective SRH and 0–6 km shear for effective
shear. Both use helicity relative to the tracked storm motion, as `srh01` and `srh03`
do. The soundings' default storm motion is the Bunkers right mover; set the sounding's
*Storm motion* to *Tracked meso motion* to compare them.

Lifting a parcel through every column is slow: about 0.1 ms a column per parcel on one
CPU (more with more levels), spread over the reader CPUs (`workers`). A 1000 × 1000 domain
takes tens of seconds per parcel and time. So these fields are computed on every n-th
column in x and y (the `column_stride` [setting](../settings.md); each n × n block of
the map shows its middle column). With `auto`, that is every column up to 500 × 500
points and enough columns apart beyond that to keep to about 250 000. The fields of
one parcel and time share one lift (SB CAPE, SB CIN, SB LCL and STP lift once). A
series uses the same columns as the map.

### Streamwise and crosswise vorticity

These are relative to the **tracked storm motion** at that time when the track has a fix
there, and otherwise to the domain motion (`umove`, `vmove`). The map title, colorbar,
section title, 3D legend and streamline card say which was used. *Crosswise* is positive
to the left of the storm-relative wind.

## Parcels

Parcel calculations are pseudoadiabatic with a virtual-temperature correction. They were
checked against MetPy: CAPE agrees within about 3%. The definitions of the SB, ML and MU
parcels and the other sounding parameters are on the [Soundings](soundings.md#what-is-computed)
page.

## Pressure decomposition

The **Pressure decomposition** field group holds

- the pressure perturbation split into a buoyancy part `p_b`, a linear dynamic part `p_l`
  and a nonlinear dynamic part `p_nl`;
- the matching vertical accelerations `acc_b` (B − ∂p_b/∂z / ρ), `acc_l` and `acc_nl`;
- `p_dyn` = p_l + p_nl, `acc_dyn` = acc_l + acc_nl, and `acc_tot` = acc_b + acc_l + acc_nl.

### Where the values come from

Where post-processing wrote them into the output files they are read from there (any file
subset). The map title says which version wrote them, and warns for files written by
early versions without a `pdecomp_version` tag. Elsewhere, a **Compute pressure
decomposition** button (under the map or section) computes that time in a separate
process with cm1view's solver (`cm1view/pdecomp/pdecomp_solver.py`).

### What the solver does

Each part solves the anelastic pressure equation,

```
cp [H ∂²π/∂x² + H ∂²π/∂y² + ∂/∂z(H ∂π/∂z)] = F      with H = θv0 ρ0
```

by a horizontal FFT (periodic lateral boundaries, `ebc = 1`) or cosine transform (open
ones) and a tridiagonal solve in the vertical that is conservative on the stretched grid.
The forcings are ∂(ρ0 B)/∂z for `p_b` and −2 ρ0 (∂U0/∂z ∂w/∂x + ∂V0/∂z ∂w/∂y) for `p_l`.
`p_nl` is the residual (total p′ − p_b − p_l). The horizontal grid must be uniform.

### Cost

The inputs are read in parallel first, and the solver uses every CPU of the job:
about 25–35 s with 4 CPUs (about 80 s on one) for a 1280 × 1280 × 115 grid, which needs
about 30–40 GB of free memory (less for smaller grids, in proportion). If the job lacks
the memory, the 3D cache is emptied first; if still short, it says so. See [Running on a
cluster](../hpc.md#resources) for the memory to ask for.

### Writing into the output file

*Write into the output file* (offered when `allow_writes_to_output` is on) writes the
result into the output file (float64, with a `pdecomp_version` attribute; about +40 s and
+9 GB per file for a 1280 × 1280 × 115 grid), replacing older values.

- While it writes, the viewer releases that one file and reports it as busy.
- **If the job is killed during a write, the file can be left damaged.**
- Unticked, the result is kept in memory only. The last 2 computed times stay in memory
  either way.
- For files written by early versions the button offers *Recompute … and overwrite*.

### Using your own solver

The solver also works on its own, outside the viewer (its docstring shows how). To use
another solver, point the `pdecomp_script` setting (or `--pdecomp-script`, or
`$CM1VIEW_PDECOMP_SCRIPT`) at a Python file with the same functions:

- `lbc_type`, `domain_info`, `compute_base_state`, `setup_pressure_solver`,
- `pressure_decomposition`, returning a dict with `p_b`, `p_l`, `p_nl`, `acc_b`, `acc_l`
  and `acc_nl`, each shaped like a 3D field, and
- `write_data`,

and a module-level `nc` (`import netCDF4 as nc`) that it opens files with.
