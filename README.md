# cm1view

An interactive viewer for [CM1](https://www2.mmm.ucar.edu/people/bryan/cm1/) netCDF
output (`output_format = 2`, one time per file). It runs where your output is (usually
a cluster) and opens in your own browser.

- **Map**: layered plan views of any native or derived field (filled, contoured, wind
  arrows or streamlines), at a height, a model level, or a column max / min.
- **Soundings**: click for a skew-T, hodograph, SB / ML / MU parcels, shear, SRH, the
  effective inflow layer, STP / SCP and storm-relative profiles. Compare points, area
  means, times, or a spot that moves with the storm.
- **Storm tracking**: follow an updraft or mesocyclone through time, by hand or
  automatically, and save the track.
- **Cross-sections**, **3D** isosurfaces and streamlines, and **series** of a field
  reduced over a region (domain, 3D box, a disc around the storm) at every time.
- **Figures**: publication figures from any of the above, across times and runs. Each
  saves with a stand-alone script and data that redraw the same image without cm1view.
  Plan views and cross-sections can also be saved as animated GIFs.

## Quick start

```bash
git clone https://github.com/bobbysaba/cm1view.git
cd cm1view
conda env create -f environment.yml && conda activate cm1view
cm1view --demo                    # synthetic runs, to try it out
cm1view /path/to/cm1/run          # your own output
```

Open the URL it prints. On a cluster, start it in a batch or interactive job, or on any
compute node you can log in to when there is no scheduler, with the resources below.
Reach it through the SSH tunnel command it prints, or through JupyterHub.

## What resources to ask for

Memory depends on the size of the grid, not on how many output times there are. Take
`nx × ny × nz` from your `namelist.input` and use the row nearest yours:

| Grid (nx × ny × nz) | Points | CPUs | Memory | With pressure decomposition |
|---|---|---|---|---|
| 256 × 256 × 80 | 5 million | 4 | 8 GB | 8 GB |
| 512 × 512 × 100 | 26 million | 4 | 16 GB | 16 GB |
| 1024 × 1024 × 100 | 105 million | 8 | 32 GB | 48 GB |
| 1280 × 1280 × 115 | 188 million | 8 | 32 GB | 64 GB |
| 2048 × 2048 × 150 | 629 million | 8 | 96 GB | 192 GB |

Rule of thumb: about 4 GB plus 0.12 GB per million grid points to view a run, and another
0.24 GB per million points free while a pressure decomposition runs. More than 8 CPUs
doesn't help. See [Running on a cluster](docs/hpc.md#resources) for where the numbers
come from and for machines without a scheduler.

## Documentation

The full documentation is at **https://bobbysaba.github.io/cm1view/**, and also here
in `docs/`:

- [Installing](docs/install.md): conda or pip, disk space, checking the install
- [Running on a cluster](docs/hpc.md): Slurm / PBS jobs, SSH tunnels, JupyterHub,
  resources
- [Using cm1view](docs/guide.md): the workspaces, tools, soundings, tracking, series,
  3D and figures, and notes on the fields
- [Settings](docs/settings.md): the config file and every setting
- [Developing](docs/developing.md): tests, code layout, adding derived fields

## Requirements

Python 3.11 or newer with the packages in `environment.yml` (conda-forge); tested on
Linux. Any modern browser.

## License and credits

cm1view is free software under the [GNU General Public License v3.0 or later](LICENSE):
you may use, study, change and share it, and anything you distribute that is built on
it must stay under the same license, with its source.

The pressure-decomposition solver (`cm1view/pdecomp/pdecomp_solver.py`) was written by Bobby
Saba, rewritten and corrected from earlier code by Dr. John Peters passed along by
Andrew Muehr.
