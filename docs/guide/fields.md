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
| `qcloud`, `qprecip` | Cloud and precipitation condensate (g/kg) | qc + qi, and qr + qs + qg + qhl, where those are in the output |
| `p_dyn`, `acc_dyn`, `acc_tot` | Pressure decomposition sums | see below |

Other derived fields are defined in `cm1view/core/fields.py` (`_make_fields`); see
[Developing](../developing.md) for how to add one.

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
