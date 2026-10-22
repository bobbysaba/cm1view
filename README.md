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

Open the URL it prints. On a cluster, start it in a batch or interactive job (4+ CPUs,
32+ GB of memory) and reach it through the SSH tunnel command it prints, or through
JupyterHub.

## Documentation

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
