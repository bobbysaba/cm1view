# Installing cm1view

cm1view is a Python web app. It runs wherever your CM1 output is (usually a cluster),
and you look at it in your own browser. It needs Python 3.11 or newer and the packages
listed in `environment.yml`.

## With conda (recommended)

`environment.yml` pins the conda-forge versions cm1view is tested with. Use
[Miniforge](https://github.com/conda-forge/miniforge), or any conda / mamba you already
have:

```bash
git clone https://github.com/bobbysaba/cm1view.git
cd cm1view
conda env create -f environment.yml      # once; about 2.7 GB
conda activate cm1view
cm1view --demo                           # check it works (see below)
```

This installs cm1view in editable mode, so `git pull` updates it. After a pull that
changes `environment.yml`, run `conda env update -f environment.yml --prune`.

**Disk space.** Miniforge plus the environment take about 4 GB. Many clusters give home
folders a small quota. If yours does, install Miniforge (or put the environment, with
`conda env create -p /path/to/envs/cm1view -f environment.yml`) in a work or project
folder instead.

**Clusters with a site conda.** If your site provides conda through a module
(`module load conda` or similar), you can use that instead of Miniforge. Creating the
environment from `environment.yml` is the same either way.

## With pip

Into an existing environment (Python 3.11 or newer):

```bash
git clone https://github.com/bobbysaba/cm1view.git
pip install -e ./cm1view            # add [test] for pytest and the browser tests
```

The versions in `pyproject.toml` are looser than the pins in `environment.yml`. If
something misbehaves, try the conda environment first. netCDF4 and numba ship binary
wheels for common platforms. If pip has to build them from source, conda is the easier
route.

## Check the install

```bash
cm1view --demo
```

This writes two small synthetic runs to the cache folder (a supercell and a
weak-mesocyclone twin, with storm tracks) and starts the viewer on them. Open the URL it
prints. On a cluster, see [Running on a cluster](hpc.md) for how to reach it from your
laptop.

To run the tests as well, see [Developing](developing.md).
