# Figures

The **Figure** workspace makes publication figures from anything in the viewer: plan
views, cross-sections, time–height plots, time series, soundings, distributions and 3D
scenes, across times and runs. The figure is previewed at its final size, every change can be
undone, and each saved figure comes with a stand-alone script and data that redraw the
same image without cm1view.

This page covers how a figure starts, the editor's layout and how to save. The rest has a page
each:

| What | Page |
|---|---|
| The grid, what each kind of panel shows, times, runs | [Figure panels](figures-panels.md) |
| Fills, contours, vectors, series, soundings, distributions | [Figure layers](figures-layers.md) |
| Fonts, axes, colorbars, legends; text, arrows, your own code | [Style and annotations](figures-style.md) |
| Animations (GIF or video), templates, reopening | [Export, animations and the script](figures-export.md) |

## Starting a figure

A figure can start from

- the **picture buttons** in the items tray under the map: the map view, soundings, the
  section, a series, the 3D box. The figure then keeps the layers, fields and ranges you set up in
  the viewer;
- **Figure of these** in the Distribution tool; or
- the **New dialog**, which the Figure workspace shows the first time you open it (when
  no figure has been made from the viewer yet). The new-figure button above the preview
  shows it again.

### The New dialog

| Setting | Meaning |
|---|---|
| **Panels show** | *Plan views*, *Vertical cross-sections*, *Time–height (series)*, *Time series*, *Soundings*, *Distributions*, *Vertical profiles*, *Joint distributions*, *Azimuthal means*, *Tables (sounding parameters, field statistics)* or *3D scene (one picture)*. |
| **Panels differ in** | (Plan views.) *Time*, *Field*, *Height*, *Run*, or *Nothing*; the panels fill the grid row by row. For a grid of two (e.g. runs × times), use *Fill panels* on the Plan views node afterwards. Cross-sections start as x–z and y–z in turn. |
| **Colour fill** | The field every panel starts with. |
| **Rows**, **Columns** | The grid, up to 8 × 8 here; the Figure node takes any size. |
| **Width** | A size preset: 3.25 in (one journal column), 5 in, 6.5 in (full page width), 7.5 in, a 13.3 × 7.5 in slide, or custom. Default 8 in. |

**Make the figure** builds it, and Undo takes it back; **Keep this figure** closes the dialog and
leaves the figure as it is. **Reopen the last figure**, when there is one, brings back what you
were last working on in this run, saved or not.

**Or start from a template** applies a template you saved from *Export* to this run
([Templates](figures-export.md#templates)).

**Or open a saved figure** shows the figures saved in the *Figures* folder (⚙ Settings) as
thumbnails, newest first across all folders, 12 at a time (**Show more**). The list above them
narrows them to one folder, and hovering over one shows its folder and when it was saved. Click
a thumbnail to open that figure, ready to keep editing
([Reopening a saved figure](figures-export.md#reopening-a-saved-figure)). A figure saved before
this version gets its thumbnail from its image; one saved only as a PDF, SVG or EPS shows just its
name until it is saved again. **Or open one by its path** takes a `_spec.json`, or the image or
script saved with it, from anywhere.

A note in the dialog says what to do next for the chosen kind. Time–height and time-series
figures start with no series, so nothing is computed until you add one. Soundings and
distributions start with the viewer's soundings or distributions.

## The editor

The editor has three panes, with a toolbar above them.

- The **tree**, on the left, lists what the figure holds: the **Figure**, its **Runs**, a node for
  each kind of panel, each panel, and each panel's layers and insets. The button at the top left
  hides it.
- The **preview**, in the middle, is drawn at the figure's final size. Clicking a panel picks it
  in the tree.
- The **inspector**, on the right, holds the settings of what is picked, in folding sections. The
  **Find** box above it searches this figure's settings and goes to the one you pick.

**Where you pick says what an edit reaches.** A setting on the **Figure** node reaches every
panel; on a kind's node, such as **Plan views**, all panels of that kind; on a **panel**, that
panel alone. A panel's own value shows as changed, with *Use the setting for all panels* to go
back to the shared one. A section with changes says how many on its header, and *Reset to default*
puts it back.

**Shared layers and sections.** The layers on the Plan views node are shared by the panels that
draw them. An edit there reaches them all, and the inspector says so; a layer edited on one panel
changes that panel alone. **Keep apart** gives a panel its own copy.

Above the preview, *Size* switches between **Fit** and **Actual size** (as large as it prints, to
judge the font sizes), *Colours* previews the picture in greyscale or as seen with a colour-vision
deficiency (the preview only, not the figure), and *Mouse* says what a click or drag in the
preview does: pick a panel, place an annotation, a section's A and B, a panel's area or an inset
([Style and annotations](figures-style.md#annotate)).

Under the preview, a **time slider** shows the figure at other outputs. **Keep this time** moves
the figure there, and *Saved time* comes back; it changes nothing else.

In the toolbar:

- **↶ ↷** undo and redo every change, including a new figure. Sections stay folded or open as you
  left them.
- **Auto-redraw** redraws after each change; untick it and press **Redraw** to draw only when you
  ask (useful for slow figures).
- **Export** saves the figure.

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
