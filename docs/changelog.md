# Changes

What changed in each release, newest first. The version is in `pyproject.toml`; a release
has a matching git tag.

## Unreleased (since v0.3.0)

### The map

- **More fills** (up to three) over the first fill, each with its own field, level,
  colormap, range, opacity and colorbar, and *Clear outside range* so the fill
  underneath shows ([The map](guide/map.md#more-fills)).
- **Contours** are now a list of up to six rows, each with its own field, level, levels,
  colour and line width, in place of the two fixed contour sets.
- **Vectors** are a list of up to three rows: the wind (ground-, grid- or storm-relative),
  **horizontal vorticity** and **baroclinic generation**, each drawn as arrows or as
  **streamlines**, with a reference arrow in the vector's units.
- A **diverging colormap stays white at zero** when the range crosses zero unevenly, on
  the map, sections, time–height plots and figures.
- The fill's **Style** now sits in the fill's own pill in the toolbar.
- Numeric boxes keep what you type and tidy values to 7 significant digits.

### Cross-sections

- The section has the **same layers as the map**: a fill with its Style, more fills,
  contours and vectors. Vectors are the in-plane components (along the section and
  vertical) ([Cross-sections](guide/cross-sections.md)).

### 3D

- **Seed box on map**: start the streamlines inside a box you drag on the map.
- While a streamline is selected or pinned, the others turn grey and faint, and the
  pointer on the card's plot shows its position on each line in the scene. Streamlines
  are traced again only when something they depend on changes, so selecting, pinning and
  restyling are quick.
- The tracer takes smaller steps in strong updrafts, stops at stagnation points and ends
  exactly at the maximum length or the region's edge.
- **Vectors** at a height in the scene, a list of up to three with the same vectors as
  the map (this replaces *Surface winds*), and **Re-render when time changes** can be
  turned off ([3D](guide/3d.md)).

### Storm tracking

- New things to track: the **pressure low** (minimum p′) and **any field** (maximum or
  minimum) at a height.
- **Fix at: Centroid** puts each fix at the field-weighted centre of the area around the
  peak, for a smoother track.
- A **From / To** window replaces the direction setting: track backward by choosing an
  earlier *From* ([Storm tracking](guide/tracking.md)).

### Figures

- **Quick start** dialog the first time the Figure workspace opens, and a new-figure
  button ([Figures](guide/figures.md#the-quick-start)).
- **Difference fills**: a fill layer minus another run or time, with a choice for runs
  on different grids.
- **Time windows**: swaths (maximum, minimum, mean or sum over a window of outputs) and
  storm-following composites.
- **Templates**: save a figure's layout and look without its runs, and apply it to
  another run. **Copy a layer's look** onto others. (Style presets are now for scripts
  only.)
- **Runs are picked per layer**, sounding, distribution and series; the Panels-tab run
  list is gone. *Layers → Runs used* holds each run's label, colour, line style and
  track, and **Fill a grid** makes panels of runs × times. A run keeps its colour in every
  panel.
- **Distributions**: bar labels (counts, percentages or values) and statistics in the
  legend or in a box. **Time series**: mark each line's maximum or minimum. **Maximum and
  minimum** of a layer in a corner of plan views, sections and time–height panels.
- **Soundings**: the hodograph inset can sit in any corner or at a chosen place, the
  hodograph view can be centred on the data, each storm-motion marker is a separate
  option, the table lists more parameters, and the layer options are split into
  Sounding panels, Skew-T and Hodograph.
- Colorbar **label and ticks can be set on the layer** that the colours belong to, and the
  thickness setting works beyond matplotlib's usual limit. The contour key and the
  matplotlib style moved to the Style tab. Settings that switch things on and off are one
  *Show* list at the foot of their section. Sections open collapsed.
- **Animations**: choose the end time and the step between outputs, with a live frame
  count; editing the figure no longer hangs while a GIF is saving.
- **Exported scripts** are short (about 55 lines plus the spec) and import their drawing
  code from `_src/<name>_draw.py`; a `my_changes()` hook takes your own matplotlib.
- Figures are drawn and saved one at a time (matplotlib's style settings are
  process-wide).
- A fix for a figure preview that drew a second, stale image under the first.

### Under the hood

- The package is split into `core`, `viewer`, `figures` and `pdecomp`; the large modules
  are split into mixins and subpackages. The layout is in [Developing](developing.md).
  Figures saved by earlier versions open as before, and exported scripts do not import
  cm1view.
- Image tests compare typical figures with baselines in `tests/baseline/`
  ([Developing](developing.md#tests)).
- A new documentation site: one page per area of the viewer, a troubleshooting page, a
  page of shortcuts and a glossary.

## 0.3.0

The first tagged release: the map, soundings, storm tracking, cross-sections, 3D
isosurfaces, series, and the figure workspace with stand-alone scripts, for CM1
`output_format = 2`.
