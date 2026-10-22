# Developing cm1view

## Tests

```bash
conda activate cm1view
pytest                                  # the suite, on synthetic demo runs
pytest tests/test_tracking.py -k manual # one file / matching tests
CM1VIEW_TEST_RUN=/path/to/run pytest -m real   # checks on your own output (reads only)
pytest -m browser                       # the viewer in headless Firefox, with screenshots
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
cm1view/                  config.py (settings: file, precedence, save folders, run search),
                          registry.py (open runs shared by sessions, run discovery),
                          theme.py (colours and CSS), demo.py (synthetic CM1 runs for
                          cm1view --demo and the tests), __main__.py (command line)

core/                     model output, no UI
  run.py                  file discovery, staggered->scalar reads, 3D cache, parallel reads
  fields.py               field catalog, derived fields, colormaps
  thermo.py               parcel theory (numba), kinematics, composite parameters
  sounding_plot.py        skew-T / hodograph / profiles / parameter table
  render.py               map + cross-section computations (contours, vectors, sampling)
  track.py                meso tracking + CSV/text export
  volume3d.py             isosurfaces, surface vectors, streamlines + Plotly scene
  series.py               time series of reduced fields: compute, cache, files
  dist.py                 distributions: a field's values over a region, their summary
  swath.py                time-window reductions (swaths, storm-following composites)

pdecomp/                  pressure decomposition
  __init__.py             file fields, computing one time on request
  pdecomp_solver.py       the solver (runs in its own process; usable alone)

viewer/                   the interactive page (Panel / Bokeh)
  app.py                  the Viewer: widgets, map, layout, wiring, events; the page
  ui.py                   shared UI pieces: constants, figure styling, drawers, tool rail
  sounding.py             Viewer mixin: soundings, their graphics, style and zoom
  tracking.py             Viewer mixin: storm tracking and the storm chip
  series.py               Viewer mixin: the Series panel and plots
  dist.py                 Viewer mixin: the Distribution panel, plots and statistics
  xsec.py                 Viewer mixin: cross-sections
  view3d.py               Viewer mixin: 3D scene, pressure-decomposition button, streamlines
  items.py                Viewer mixin: the items tray
  zoomview.py             zoomable image component (sounding graphics)
  settings.py             settings window (first run and ⚙) and the overwrite prompt
  picker.py               run picker (header dialog and the page without a run)

figures/                  the Figure workspace
  spec.py                 figure spec, panel data, export (image, script, data, spec)
  draw.py                 matplotlib drawing of a figure (copied into exported scripts)
  editor.py               the Figure workspace editor (FigureEditor)
  cards.py                its constants, widget helpers and cards
  runs.py                 editor mixin: runs
  sources.py              editor mixin: new figures from the viewer, series / sounding /
                          distribution lists
  export.py               editor mixin: saving and reopening figures
  anim.py, click.py,      editor mixins: animation, click-to-place, combining panels,
  combo.py, style.py,     styles and templates, the figure tree
  tree.py

tests/                    pytest suite
docs/                     these pages
```

A mixin's methods run as the Viewer's (or the editor's) own: they use its widgets and
state through `self`. New features go in the mixin they belong to, or a new one added to
the class's bases.

## Adding a derived field

Derived fields are defined in `cm1view/core/fields.py` (`_make_fields`) as `FieldDef`s: a
name, label, units and menu group, a default colormap and range, the fields it needs
(`deps`) and a function of them (`func`). They then appear in every
field menu (map, section, 3D, series, figures). Add a test in `tests/test_fields.py`
against the definition, as for θρ.

## Releases

Versions follow `MAJOR.MINOR.PATCH` in `pyproject.toml` and `cm1view/__init__.py`, with a
matching git tag (`v0.3.0`).
