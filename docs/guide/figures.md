# Figures

The **Figure** workspace makes publication figures from anything in the viewer: plan
views, cross-sections, time–height plots, time series, soundings and distributions,
across times and runs. The figure is previewed at its final size, every change can be
undone, and each saved figure comes with a stand-alone script and data that redraw the
same image without cm1view.

This page covers how a figure starts, the editor's layout and how to save. The editor's
tabs have a page each:

| Tab | Page |
|---|---|
| **Panels**: what the panels show, the grid, times, runs | [Figure panels](figures-panels.md) |
| **Layers**: fills, contours, vectors, series, soundings, distributions | [Figure layers](figures-layers.md) |
| **Style** and **Annotate**: fonts, axes, colorbars, legends; text, arrows, your own code | [Style and annotations](figures-style.md) |
| **Export**: trimming, animations (GIF), templates, reopening | [Export, animations and the script](figures-export.md) |

## Starting a figure

A figure can start from

- the **picture buttons** in the items tray under the map: the map view, soundings, the
  section, a series. The figure then keeps the layers, fields and ranges you set up in
  the viewer;
- **Figure of these** in the Distribution tool; or
- the **quick start**, which the Figure workspace shows the first time you open it (when
  no figure has been made from the viewer yet). The new-figure button above the preview
  shows it again.

### The quick start

| Setting | Meaning |
|---|---|
| **Panels show** | *Plan views*, *Vertical cross-sections*, *Time–height (series)*, *Time series*, *Soundings* or *Distributions*. |
| **Panels differ in** | (Plan views and cross-sections.) *Time*, *Field*, *Height* (plan views), *Section* (cross-sections), *Run*, or *Nothing*; the panels fill the grid row by row. For a grid of two (e.g. runs × sections) set *Panels → Grid and size → Rows are / Columns are*. |
| **Colour fill** | The field every panel starts with. |
| **Rows**, **Columns** | The grid, up to 8 × 8. |
| **Width** | A size preset: 3.25 in (one journal column), 5 in, 6.5 in (full page width), 7.5 in, a 13.3 × 7.5 in slide, or custom. Default 8 in. |

**Make the figure** builds it; **Keep the example** closes the dialog and leaves the
figure as it is (a time grid of plan views around the storm). **Or open a saved
figure** lists the figures saved with *+ script & data* in the *Figures* folder
(⚙ Settings); **Open** shows the one picked, ready to keep editing
([Reopening a saved figure](figures-export.md#reopening-a-saved-figure)). A note in the dialog says
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
  the figure.
- The five tabs hold folding sections. What a section or card draws or leaves out
  (legends, zero lines, storm motions, panel labels, …) is one list of checkboxes, *Show*,
  at its foot.
- You can click the preview to place annotations, a section's A and B, or to set the
  area of the plan views ([Style and annotations](figures-style.md#annotate)).

## Saving

Saving sits above the preview:

| Control | Meaning |
|---|---|
| **Save as** | Folder and name, without extension. For one run it starts in `<figures_dir>/<parent>_<run>/` (see [Settings](../settings.md)). A figure of several runs has no folder of its own: choose one (the last one used is offered next time). |
| **Format** | PNG, PDF, SVG, EPS or TIFF. |
| **DPI** | 50 to 1200. |
| **Save** | The image only. |
| **+ script & data** | The image, a stand-alone script, the plotted arrays and the spec ([Export, animations and the script](figures-export.md#the-script-and-data)). |
| **Download** | Sends the image to your browser. |

Saving over an existing file asks first. Figures are drawn and saved one at a time,
because matplotlib's style settings are process-wide.

## Fields and runs

A figure may show several runs. Every layer, sounding, distribution and series picks its
own run, and runs have their own storm track (the Track tool, or `storm_tracks/<run>.csv`
found automatically; see `track_dirs` and `track_patterns` in [Settings](../settings.md)).
See [Figure panels](figures-panels.md#runs) for how runs are added and coloured.
