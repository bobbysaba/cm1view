# Figures

The **Figure** workspace makes publication figures from anything in the viewer: plan
views, cross-sections, time–height plots, time series, soundings, distributions and 3D
scenes, across times and runs. The figure is previewed at its final size, every change can be
undone, and each saved figure comes with a stand-alone script and data that redraw the
same image without cm1view.

This page covers how a figure starts, the editor's layout and how to save. The editor's
tabs have a page each:

| Tab | Page |
|---|---|
| **Panels**: what the panels show, the grid, times, titles | [Figure panels](figures-panels.md) |
| **Layers**: fills, contours, vectors, series, soundings, distributions | [Figure layers](figures-layers.md) |
| **Style** and **Annotate**: fonts, axes, colorbars, legends; text, arrows, your own code | [Style and annotations](figures-style.md) |
| **File**: animations (GIF), templates, reopening | [Export, animations and the script](figures-export.md) |

## Starting a figure

A figure can start from

- the **picture buttons** in the items tray under the map: the map view, soundings, the
  section, a series, the 3D box. The figure then keeps the layers, fields and ranges you set up in
  the viewer;
- **Figure of these** in the Distribution tool; or
- the **quick start**, which the Figure workspace shows the first time you open it (when
  no figure has been made from the viewer yet). The new-figure button above the preview
  shows it again.

### The quick start

| Setting | Meaning |
|---|---|
| **Panels show** | *Plan views*, *Vertical cross-sections*, *Time–height (series)*, *Time series*, *Soundings*, *Distributions*, *Vertical profiles*, *Joint distributions*, *Azimuthal means*, *Tables (sounding parameters, field statistics)* or *3D scene (one picture)*. |
| **Panels differ in** | (Plan views.) *Time*, *Field*, *Height*, *Run*, or *Nothing*; the panels fill the grid row by row. For a grid of two (e.g. runs × times) set *Panels → Grid and size → Rows are / Columns are*. Cross-sections start with a section card per panel, x–z and y–z in turn (*Layers → Sections*). |
| **Colour fill** | The field every panel starts with. |
| **Rows**, **Columns** | The grid, up to 8 × 8. |
| **Width** | A size preset: 3.25 in (one journal column), 5 in, 6.5 in (full page width), 7.5 in, a 13.3 × 7.5 in slide, or custom. Default 8 in. |

**Make the figure** builds it; **Keep the example** closes the dialog and leaves the
figure as it is (a time grid of plan views around the storm). **Reopen the last figure**,
when there is one, brings back what you were last working on in this run, saved or not.

**Or start from a template** applies a template you saved in *File → Templates* to this run
([Templates](figures-export.md#templates)).

**Or open a saved figure** shows the figures saved in the *Figures* folder (⚙ Settings) as
thumbnails, newest first across all folders, 12 at a time (**Show more**). The list above them
narrows them to one folder, and hovering over one shows its folder and when it was saved. Click
a thumbnail to open that figure, ready to keep editing
([Reopening a saved figure](figures-export.md#reopening-a-saved-figure)). A figure saved before
this version gets its thumbnail from its image; one saved only as a PDF, SVG or EPS shows just its
name until it is saved again.

A note in the dialog says
what to do next for the chosen kind. Time–height and time-series figures start with no
series, so nothing is computed until you add one in *Layers → Series*. Soundings and
distributions start with the viewer's soundings or distributions. Everything else (times,
layers, style, labels) is in the editor's tabs.

## The editor

- The **preview** is drawn at the figure's final size. **Actual size** shows it as large
  as it prints, to judge the font sizes.
- **Live** redraws after each change; untick it and press **Redraw** to draw only when
  you ask (useful for slow figures).
- **↶ ↷** undo and redo every change, including adding, removing and changing parts of
  the figure. Cards stay as you left them, folded or open.
- The five tabs hold folding sections. What a section or card draws or leaves out
  (legends, zero lines, storm motions, panel labels, …) is one list of checkboxes, *Show*,
  at its foot.
- You can click the preview to place annotations, a section's A and B, or to set the
  area of the plan views ([Style and annotations](figures-style.md#annotate)).

## Saving

**Export**, above the preview, opens the dialog that saves the figure:

| Control | Meaning |
|---|---|
| **Save as** | Folder and name, without extension. For one run it starts in `<figures_dir>/<parent>_<run>/` (see [Settings](../settings.md)). A figure of several runs has no folder of its own: choose one (the last one used is offered next time). |
| **Format** | PNG, PDF, SVG, EPS or TIFF. |
| **DPI** | 50 to 1200. |
| **Background** | White, black or transparent. |
| **Image size** | *Trim white space*, *Exact width, trim the height* or *Exact width and height* ([Image size](figures-export.md#image-size)). |
| **Also the script and data** | Adds a stand-alone script, the plotted arrays and the drawing code ([Export, animations and the script](figures-export.md#the-script-and-data)). |
| **Save** | The image, and the figure's settings (`_src/<name>_spec.json`) so it can be reopened. |
| **Download** | Sends the image to your browser. |

A figure whose time series are still being computed is saved when they are done; the line
above the preview says so. It saves the figure as it was when you pressed **Save**.

Saving over an existing file asks first. Figures are drawn and saved one at a time,
because matplotlib's style settings are process-wide.

## Fields and runs

A figure may show several runs. Every layer, sounding, distribution and series picks its
own run, and runs have their own storm track (the Track tool, or `storm_tracks/<run>.csv`
found automatically; see `track_dirs` and `track_patterns` in [Settings](../settings.md)).
A run's *Track file* lists the files in those folders, or takes a path you type.
See [Figure panels](figures-panels.md#runs) for how runs are added and coloured.
