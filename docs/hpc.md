# Running cm1view on a cluster

cm1view reads whole 3D fields into memory and uses several CPUs to read them in parallel,
so run it on a **compute node**, not on a shared login node. You then open it in your own
browser through an SSH tunnel or, where your site has one, JupyterHub.

## Resources

What cm1view needs depends on the grid, not on how many output times the run has. Take
`nx × ny × nz` from the run's `namelist.input` and use the row nearest yours:

| Grid (nx × ny × nz) | Points | CPUs | Memory | With pressure decomposition |
|---|---|---|---|---|
| 256 × 256 × 80 | 5 million | 4 | 8 GB | 8 GB |
| 512 × 512 × 100 | 26 million | 4 | 16 GB | 16 GB |
| 1024 × 1024 × 100 | 105 million | 8 | 32 GB | 48 GB |
| 1280 × 1280 × 115 | 188 million | 8 | 32 GB | 64 GB |
| 2048 × 2048 × 150 | 629 million | 8 | 96 GB | 192 GB |

Time: as long as you'll be looking.

**Working it out for another grid.** Each 3D float32 field is `nx × ny × nz × 4` bytes:
about 0.75 GB for 1280 × 1280 × 115. Viewing needs room for Python and the server (about
4 GB) plus a cache of recently used 3D fields, about 30 of them for comfortable use: 4 GB
plus 0.12 GB per million grid points. The pressure decomposition needs about 0.24 GB per
million points free while it runs (about 44 GB on 1280 × 1280 × 115), and it empties the
cache first when the job is short, so the two don't fully add. The number of output
times only changes how long the first scan of a run and a series over all times take.

**CPUs.** cm1view reads with up to 8 processes, so 8 CPUs give the fastest first read at
each time and more don't help. 4 is fine for small grids.

By default cm1view caches 3D fields in about 40% of the job's memory (`--cache-gb` to
change that).

cm1view sets the cache size (at most 48 GB) and the number of reader processes (at most
8) from what the scheduler gave the job: its cgroup memory limit and CPU affinity, or the
whole machine where there is no limit. It prints both at start.

## 1. Get a compute node

Interactive jobs are the simplest. Use your own account / project and queue names:

**Slurm**

```bash
salloc --account=<ACCOUNT> --partition=<PARTITION> --nodes=1 --ntasks=1 \
       --cpus-per-task=8 --mem=64G --time=04:00:00
```

**PBS Pro**

```bash
qsub -I -A <ACCOUNT> -q <QUEUE> -l select=1:ncpus=8:mem=64GB -l walltime=04:00:00
```

**Batch job.** To keep cm1view running without a terminal open, submit it as a job and
read the printed URL / tunnel command from the job's output file. Slurm example (PBS is
the same with `#PBS` lines):

```bash
#!/bin/bash
#SBATCH --account=<ACCOUNT>
#SBATCH --partition=<PARTITION>
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=cm1view-%j.out

source ~/miniforge3/etc/profile.d/conda.sh   # or: module load conda
conda activate cm1view
cm1view /path/to/cm1/run
```

**No scheduler.** On a machine where you log in to a node and run CM1 with `mpiexec`,
cm1view needs no job: log in to one node that can see the output and start it there
(not through `mpiexec`; it is one process on one machine). Nothing reserves resources
for you, so check what is free first:

```bash
nproc          # CPUs (lscpu: "Thread(s) per core: 2" means half are hyperthreads)
free -g        # memory: the "available" column is what you can use
uptime         # load average: about how many CPUs are busy now
```

Then size cm1view yourself from the table above, and keep it on its own CPUs so it
leaves room for other users and your own CM1 runs:

```bash
OMP_NUM_THREADS=8 NUMBA_NUM_THREADS=8 taskset -c 0-7 \
    cm1view /path/to/cm1/run --workers 8 --cache-gb 48
```

`--cache-gb` is about 40% of the memory you mean to use (48 GB is the most it takes by
default). Without these, cm1view sizes itself from the whole machine.

## 2. Start cm1view

```bash
conda activate cm1view
cm1view /path/to/cm1/run          # or ./cm1view.sh, same options
```

The run is optional. Without one, the viewer opens the `default_run` setting, or a page
that lists the runs in your folders. The first time it asks where your runs live (see
[Settings](settings.md)). If port 5006 is taken (for example by another user on the same
node), cm1view uses the next free port and prints it.

It prints how to open it:

```
Open the viewer:
  This machine:  http://localhost:5006/cm1view
  SSH tunnel:    ssh -N -L 5006:localhost:5006 -J you@login.example.edu you@node123
                 then open http://localhost:5006/cm1view
```

Options: `--cache-gb` (memory for cached 3D fields), `--workers` (parallel reader
processes), `--maxpix` (map pixels sent per axis; zooming in gives full resolution),
`--port`, `--config` (another settings file), `--demo`. `cm1view --help` lists them all.
Add `?t=30` to the URL to open at time index 30, or `?run=/path` to open another run.

## 3. Open it in your browser

**SSH tunnel** (works everywhere). On your laptop, run the printed `ssh -N -L …` command
and leave it running, then open `http://localhost:5006/cm1view`. The `-J` hop goes
through the login node to the compute node. The login node comes from the batch job
(`PBS_O_HOST` / `SLURM_SUBMIT_HOST`), or from the `login_host` setting when that is
wrong for your site (some sites need a specific login alias).

If your site blocks direct SSH to compute nodes, tunnel in two steps instead:
`ssh -L 5006:localhost:5006 you@login`, then on the login node
`ssh -N -L 5006:localhost:5006 node123`.

**JupyterHub.** When you start cm1view from a JupyterHub terminal and the hub has
[`jupyter-server-proxy`](https://jupyter-server-proxy.readthedocs.io/), cm1view prints a
`<hub>/user/<you>/proxy/5006/cm1view` URL. It opens in the same browser as the hub, with
no tunnel needed. Request the hub session with the CPUs and memory above.

**Same machine.** On a workstation, open `http://localhost:5006/cm1view`.

Only you can reach the server: it listens on `127.0.0.1` (`--address` changes that, but
there is no login page, so don't expose it on a shared network).

## Tips

- **Where things are written.** Figures, saved series and tracks go under `figures_dir`
  and `exports_dir` (default `~/cm1view/...`). Throwaway files go to `cache_dir`. Point
  the cache at scratch space if your home quota is small (the first-run window suggests
  `$SCRATCH` when it is set).
- **Output files are read-only to cm1view** unless you turn on
  `allow_writes_to_output` (only used to write a pressure decomposition into them).
- **Several runs** can be open at once, in tabs. They share one cache, and the least
  recently used fields are freed first.
- **Shared nodes.** If your scheduler doesn't confine jobs with cgroups, cm1view sees
  the whole node. Set `--cache-gb` and `--workers` to what your job asked for.
