# Settings

The first time cm1view opens in a browser, it asks where your CM1 runs live; the
other settings are pre-filled (from your recent runs and `$SCRATCH`) and can be
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
| `pdecomp_script` | none | your own pressure-decomposition script instead of cm1view's solver |
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
