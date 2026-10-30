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
- **Image baselines.** `tests/test_images.py` draws typical figures of the demo run (plan
  view, cross-section, time–height, time series, soundings, distributions, a difference
  fill, a swath, parts, a dark style) and compares each with a PNG in `tests/baseline/`;
  it also checks that save → load → draw of every panel kind gives the identical image.
  A missing baseline is written on the first run. `CM1VIEW_IMAGE_TOL` sets the allowed RMS
  difference (0–255, default 3), because fonts and matplotlib versions shift pixels
  between machines. When a figure changes **on purpose**, look at the failure's
  `*-failed-diff.png` (left in pytest's temporary folder), then rewrite the baselines with
  `pytest tests/test_images.py --make-baselines` and commit the new PNGs. Commit
  baselines made with the versions in `environment.yml`.
- **Fixtures** (`tests/conftest.py`): `demo_root`, `demo_run`, `reg` (one Registry for
  the session) and `viewer` (a fresh Viewer on the demo supercell at its first storm
  time). `wait(pred)` polls background work; `tap(v, x, y)` is a map click. For the
  figure tests (`tests/test_figure*.py`): `ed` (the viewer's figure editor, no auto
  render), `coarse_run` (a second run with other output times), `render(ed)`, and the
  spec helpers `difference_layer`, `swath_layer`, `edited_v1`.

### Which test file covers what

| File | Covers |
|---|---|
| `test_fields.py` | Derived fields, shared reads, the cache, the base state |
| `test_map.py` | Map, cross-section and 3D: layers, differences, streamlines, the region and floor |
| `test_streamlines.py` | The 3D streamline tracer on analytic winds, and the 3D pane's restyle echo |
| `test_sounding.py` | Soundings, comparison styles, zoom and the hover data |
| `test_tracking.py` | Automatic and hand-placed tracking, save and load, storm-following soundings |
| `test_session.py` | Session files: save, load, rows and values a run cannot take, another run's session; soundings, section, 3D, series and distributions back |
| `test_export.py` | netCDF export: values == the volumes / map planes, heights, box, stop, missing times, the dialog, `cm1view export` |
| `test_series.py`, `test_dist.py` | Series (cache, time–height, files) and distributions |
| `test_pdecomp.py` | The pressure decomposition, on copies of demo files |
| `test_figure.py`, `test_figure_layers.py`, `test_figure_runs.py`, `test_figure_export.py`, `test_figure_spec.py` | The figure editor: widgets ↔ spec, layers, several runs, export and animation, spec upgrades |
| `test_legend.py` | Legends of blocks and panels |
| `test_images.py` | Image baselines and save–load–draw |
| `test_settings.py`, `test_picker.py`, `test_ui.py` | Settings, the run picker, layout logic |
| `test_browser.py` | The viewer in headless Firefox (marker `browser`) |
| `test_real.py` | Your own output (marker `real`) |

## Layout

```
cm1view/                  config.py (settings: file, precedence, save folders, run search),
                          registry.py (open runs shared by sessions, run discovery),
                          theme.py (colours and CSS), demo.py (synthetic CM1 runs for
                          cm1view --demo and the tests), __main__.py (command line; `render` goes
                          to figures/batch.py, `export` to core/export.py)

core/                     model output, no UI
  run.py                  file discovery, staggered->scalar reads, 3D cache, parallel reads
  fields.py               field catalog, derived fields, colormaps
  thermo.py               parcel theory (numba), kinematics, composite parameters
  sounding_plot.py        skew-T / hodograph / profiles / parameter table
  render.py               map + cross-section computations (contours, vectors, sampling,
                          differences with another run or time, regridding)
  vectors.py              the vector quantities (wind, horizontal vorticity, baroclinic
                          generation) that map, section, 3D and figures draw
  track.py                meso tracking + CSV/text export
  volume3d.py             isosurfaces, surface vectors, streamlines + Plotly scene
  series.py               time series of reduced fields: compute, cache, files
  dist.py                 distributions: a field's values over a region, their summary
  swath.py                time-window reductions (swaths, storm-following composites)
  export.py               netCDF export of fields (box, times, model levels or heights,
                          streamed per time) and `cm1view export`

pdecomp/                  pressure decomposition
  __init__.py             file fields, computing one time on request
  pdecomp_solver.py       the solver (runs in its own process; usable alone)

viewer/                   the interactive page (Panel / Bokeh)
  app.py                  the Viewer (built from the mixins below), wiring; the page
  widgets.py              Viewer mixin: the drawers' controls and the run picker
  mapview.py              Viewer mixin: the map, storm motion and the map job
  layout.py               Viewer mixin: panels, top bar, toolbars, the main column
  events.py               Viewer mixin: time, playback, tool modes, map clicks and drags
  ui.py                   shared UI pieces: constants, figure styling, drawers, tool rail
  sounding.py             Viewer mixin: soundings, their graphics, style and zoom
  tracking.py             Viewer mixin: storm tracking and the storm chip
  series.py               Viewer mixin: the Series panel and plots
  dist.py                 Viewer mixin: the Distribution panel, plots and statistics
  xsec.py                 Viewer mixin: cross-sections
  diff.py                 Viewer mixin: map / section fill differences (minus a time or run)
  session.py              Viewer mixin: session files (collect / put back what the viewer
                          shows; the Session dialog; ?session=)
  export.py               Viewer mixin: the Export data dialog (core/export.py in the
                          "exp" pool, progress, Stop)
  view3d.py               Viewer mixin: 3D scene, pressure-decomposition button, streamlines
                          (picking, the card, pins; the pointer is followed in the browser)
  items.py                Viewer mixin: the items tray
  zoomview.py             zoomable image component (sounding graphics)
  numinput.py             FloatInput: a number box that keeps what you typed, tidy to 7
                          significant digits
  settings.py             settings window (first run and ⚙) and the overwrite prompt
  picker.py               run picker (header dialog and the page without a run)

figures/                  the Figure workspace
  spec/                   figure spec, panel data, export (fg.<name> for any module's)
    base.py               the spec: defaults, panels, layer groups, times, animation
    arrays.py             plan-view and cross-section panel arrays
    panels.py             time-series, time-height, sounding and distribution panels
    bundle.py             export: image, arrays, stand-alone script, spec
    templates.py          templates, style presets (scripting only), copying a layer's look
  draw/                   matplotlib drawing of a figure; source() stitches its modules
                          into exported scripts, so they import each other only with
                          "from .<module> import ..." lines
    base.py               colours, levels, fonts, text, saving
    v2.py                 upgrade() to version 2, views of blocks and panels
    layers.py             map layers and colorbars
    lines.py              time-series and distribution panels
    sounding.py           skew-T, hodograph, parameter table
    figure.py             draw(): blocks, panels, labels, annotations
  render.py               FigureData: a spec's panel data (runs, tracks, series,
                          caches) without the editor or Panel; the editor's .data
  batch.py                `cm1view render`: saved figures and templates drawn
                          without the viewer (images, bundles, GIFs); the GIF frame
                          helpers anim.py uses
  editor.py               the Figure workspace editor (FigureEditor): putting the
                          widgets together, wiring, layer cards, rendering the preview
  cards/                  its constants, widget helpers and cards (cards.<name> for any
                          module's)
    base.py               choices, constants and small widget helpers
    layercard.py          LayerCard
    seriescard.py         SeriesCard, SoundingCard
    distcard.py           DistCard, AnnotationRow
  widgets.py              editor mixin: the widgets of the Panels, Layers, Annotate and
                          Export tabs
  specio.py               editor mixin: spec <-> widgets (set_spec, collect), undo / redo
  times.py                editor mixin: the panels' times and titles
  panelopts.py            editor mixin: the Panels tab's reactions (fields, heights,
                          layout, size, kind, area, automatic titles)
  runs.py                 editor mixin: the Runs tab
  sources.py              editor mixin: new figures from the viewer, series / sounding /
                          distribution lists (their data: render.py)
  export.py               editor mixin: saving and reopening figures
  quick.py                editor mixin: the quick start (new figure dialog)
  anim.py, click.py,      editor mixins: animation, click-to-place, combining panels,
  combo.py, style.py,     the Style tab, styles and templates, the figure tree
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
field menu (map, section, 3D, series, figures). A dep can be a derivative of a native
field (`"ddz.winterp"`, `"ddx.uinterp"`: per km, as the Derivative select gives it), as
for the vorticity tendencies; the field is then computed from whole levels, and series
read the points just outside their region. A *column field* (`layer=(z0, z1)` km AGL) is
2D from 3D natives: its `func` gets each input on the levels of the layer only
(`(levels, ny, nx)`) and their thickness in it, `c["dz"]` (m), as for updraft helicity,
with their heights `c["zk"]` and the layer top `c["top"]` (km); `edges=True` adds the
level just outside each end (thickness 0) for interpolating to the bounds, as the bulk
shear and helicity do (`at_height`, `layer_points`). The series worker then reads just
those levels. `costly=True` marks a column field that is slow per column (the parcels
of `thermo.parcel_columns`): it is computed on every `column_stride(run)`-th column,
and its `func` gets `c["memo"]`, a dict shared by the fields of one time (so SB CAPE,
SB CIN and STP lift the SB parcel once), and `c["threads"]`. Add a test in `tests/test_fields.py`
against the definition, as for θρ.

## Adding a vector

The vectors the map, the cross-section, the 3D scene and figures can draw are the
entries of `VECTORS` in `cm1view/core/vectors.py`: a key, a label, units, the names of
its x, y and vertical component fields, and a typical magnitude (the default reference
arrow). The component fields must exist in the field catalog (add them as derived fields
if they do not, as for `bgen_x` and `bgen_y`). A vector is offered only when the run has
its components. Also add its arrow units to `KEY_UNITS` in
`cm1view/figures/draw/layers.py`, because exported figures draw their key arrows without
the viewer.

## Building the documentation

The site is built by MkDocs (Material theme) from `README.md` (the home page, through
`docs/hooks/readme.py`) and `docs/`, with the pages listed under `nav` in `mkdocs.yml`:

```bash
pip install "mkdocs>=1.6,<2" "mkdocs-material>=9.5,<10"
mkdocs serve           # preview at http://127.0.0.1:8000
mkdocs build --strict  # what the GitHub Actions workflow runs
```

`--strict` turns warnings into errors, so a link to a missing page, or a page missing from
`nav`, fails the build. A new page needs an entry in `nav`. Link between pages with
relative paths (`soundings.md#comparing-places-and-times`); anchors are the lower-case,
hyphenated headings. The workflow in `.github/workflows/docs.yml` publishes on a push that
changes `README.md`, `docs/` or `mkdocs.yml`.

When behaviour changes, change the page that describes it in the same commit, and add a
line to [Changes](changelog.md).

## Releases

Versions follow `MAJOR.MINOR.PATCH` in `pyproject.toml` and `cm1view/__init__.py`, with a
matching git tag (`v0.3.0`). Move the *Unreleased* heading of [Changes](changelog.md) to the
new version and date when you tag.
