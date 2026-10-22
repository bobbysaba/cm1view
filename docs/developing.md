# Developing cm1view

## Tests

```bash
conda activate cm1view
pytest                                  # the suite, on synthetic demo runs
pytest tests/test_tracking.py -k manual # one file / matching tests
CM1VIEW_TEST_RUN=/path/to/run pytest -m real   # checks on your own output (reads only)
pytest -m browser                       # the viewer in headless Firefox, with screenshots
CM1VIEW_PDECOMP_SCRIPT=/path/to/script.py pytest tests/test_pdecomp.py
```

Run the suite on a compute node rather than a shared login node: it starts reader
processes and renders figures.

- **Demo data.** `cm1view/demo.py` writes small analytic runs shaped like CM1 output
  (staggered winds, base state, swaths, one level per chunk) and their storm tracks. They
  are written once to `$CM1VIEW_TEST_DATA` (default `<tmp>/cm1view-demo-$USER`) and
  rewritten only when `demo.py` changes. Bump `demo.VERSION` when the fields change.
- **Isolation.** Tests use a throwaway settings file and write only into temporary
  folders. The pressure-decomposition tests work on copies of demo files.
- **Browser tests** need Firefox (on `PATH`, or `$FIREFOX`). Screenshots go to
  `$CM1VIEW_SHOTS` (default: a temporary folder, printed with `pytest -s`).
- **Fixtures** (`tests/conftest.py`): `demo_root`, `demo_run`, `reg` (one Registry for
  the session) and `viewer` (a fresh Viewer on the demo supercell at its first storm
  time). `wait(pred)` polls background work; `tap(v, x, y)` is a map click.

## Layout

```
cm1view/run.py            file discovery, staggered->scalar reads, 3D cache, parallel reads
cm1view/fields.py         field catalog, derived fields, colormaps
cm1view/thermo.py         parcel theory (numba), kinematics, composite parameters
cm1view/sounding_plot.py  skew-T / hodograph / profiles / parameter table
cm1view/render.py         map + cross-section computations (contours, vectors, sampling)
cm1view/track.py          meso tracking + CSV/text export
cm1view/volume3d.py       isosurfaces, surface vectors, streamlines + Plotly scene
cm1view/zoomview.py       zoomable image component (sounding graphics)
cm1view/series.py         time series of reduced fields (Series tool): compute, cache, files
cm1view/figure.py         figure spec, panel data, export (image, script, data, spec)
cm1view/figdraw.py        matplotlib drawing of a figure (copied into exported scripts)
cm1view/figui.py          Figure workspace UI
cm1view/pdecomp.py        pressure decomposition: file fields, on-demand runs of the user's script
cm1view/registry.py       open runs shared by sessions, run discovery
cm1view/config.py         settings: config file, precedence, save folders, run search
cm1view/settings.py       settings window (first run and ⚙) and the overwrite prompt
cm1view/picker.py         run picker (header dialog and the page without a run)
cm1view/app.py            Panel UI
cm1view/demo.py           synthetic CM1 runs for cm1view --demo and the tests
tests/                    pytest suite
docs/                     these pages
```

## Adding a derived field

Derived fields are defined in `cm1view/fields.py` (`_make_fields`) as `FieldDef`s: a
name, label, units and menu group, a default colormap and range, the fields it needs
(`deps`) and a function of them (`func`). They then appear in every
field menu (map, section, 3D, series, figures). Add a test in `tests/test_fields.py`
against the definition, as for θρ.

## Releases

Versions follow `MAJOR.MINOR.PATCH` in `pyproject.toml` and `cm1view/__init__.py`, with a
matching git tag (`v0.2.0`).
