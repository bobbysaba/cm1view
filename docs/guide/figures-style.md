# Style and annotations

## Style

Look settings are in folding sections of the inspector. **Where you pick says what they reach**: the
**Figure** node holds what the whole figure shares (text, panel labels, colorbar, legend, contour key,
spacing), a kind's node what its panels share (axes and ticks, its plot), and a panel what it
alone changes. A panel's own value stays when the shared one changes, until you pick *Use the setting
for all panels*. *Find*, above the inspector, goes to any setting by name.

Each shows only what reaches that kind's picture, so a few settings are not there for every kind:

- **Colorbar**: plan views, cross-sections and time–height panels. Joint distributions and
  azimuthal means have their own *Colorbar* switch in *Plot*.
- **Contour key**: plan views and cross-sections, or any figure while the key is on.
- **Axes and ticks** on a 3D scene: only *Ticks point* and *Frame width*, which reach its
  colorbars. The scene's own labels and ticks are under *Look*.
- **y tick every**: not on soundings, whose pressure axis keeps its ticks.
- **Time label**: not on time series or time–height panels, which have no single time.
- **Run name**: plan views, cross-sections, time–height panels and 3D scenes. Other panels
  name their runs in the legend.

### Style preset

**Apply a style**, on the Figure node, sets the look of the whole figure in one
go. It applies once: anything you change afterwards stays changed, and ↶ takes it back.

| Preset | Fonts and labels | Frame lines | Export and width |
|---|---|---|---|
| **Default** | 10 pt sans-serif; labels bold, 1.2 × the base size | 0.8 pt | Left as they are |
| **AMS journal** | 8 pt sans-serif; letters `(a)` at 9 pt, other labels 8 pt, none bold | 0.6 pt | PDF at 600 DPI; 3.2 in for one column, otherwise 6.5 in |
| **Talk** | 14 pt sans-serif; labels 15 pt bold | 1.2 pt | PNG at 200 DPI; 10 in |
| **Dark** | As Talk, on black with light text and axes | 1.2 pt | As Talk |

The line under the preview says what changed when a preset changes the width or the export. On *Dark*, whatever
is drawn in black (contours, wind barbs, the first run's line, text) is drawn in white, and a
hodograph stays a light card.

### Text

| Setting | Meaning |
|---|---|
| **Font** | The text font (the installed fonts are offered). |
| **Math & units font** | The font of `$…$` text such as `m s$^{-1}$`: DejaVu Sans, "like the text font", STIX Sans, STIX (Times-like) or Computer Modern. |
| **Base size (pt)** | Default 10. |
| **Tick labels**, **Axis labels**, **Panel titles**, **Figure title**, **Legends** | Sizes in points; blank follows the base size. |

### Axes and ticks

x and y labels (matplotlib maths allowed, e.g. `w (m s$^{-1}$)`); **Tick labels on** all
panels, outer panels only, or none (outer: the y tick labels stay on every panel while the
panels' y ranges differ, and likewise x; *Share limits* makes them the same; inner
panels drop the axis labels either way, unless a panel has a different label of its own);
**Share limits (panels of a kind)** none, x, y, or x and y; **Ticks point** out, in or
across; **x tick every** and **y tick every**; **Frame width**; **Grid style** (dotted,
dashed, solid); and checkboxes for *Tick marks*, *Minor ticks*, *Grid lines* and *Equal x/y
scale*.

One panel can have labels of its own: pick the panel in the tree and fill in *x
label* or *y label* (blank: the labels here; a single space: no label).

### Panel labels

**Panel titles** have *Where* (centre, left or right) and *Bold*. Each other label has one
row: its checkbox first, then its own *Where* (the corners and edges of the panel,
or above its left or right corner), *Size* (blank: 1.2 × the base size), *Bold* and *White box*:

- **Panel letters**: *Style* `a`, `(a)`, `a)`, `A` or `(A)`. They come on with a second panel
  (a figure of one panel starts without one) until you tick or untick them yourself.
- **Time label**: *Text* with `{min}` (minutes from time zero), `{model}` (model minutes),
  `{s}` (seconds) or `{hms}` (h:mm:ss), e.g. `t = {min:g} min`. Time zero is set for each
  run, on the tree's [**Runs** node](figures-panels.md#runs). A figure saved with a *Minutes
  counted from* still shows that box, which adds to the runs' time zeros; at 0 it goes away.
- **Height label** (for panels at several heights): *Text* with `{z}` (the height, km)
  or `{k}` (the model level), e.g. `{z:g} km AGL`; blank gives `z = … km` or `k = …`.
- **Run name** (for figures of several runs), optionally *In the run's colour*.

**Shrink these labels to fit narrow panels** (on in new figures): when the labels on one edge
of a panel would run into each other or out of it, they all shrink together, to 6 pt at the
least, so they stay one size across the figure. *Size* is then the largest they get. Figures
saved before this option keep their sizes until you tick it.

A new figure of soundings has its letters and time label above the panel, clear of the wind
barbs and the hodograph.

### Colorbar

Hidden for time series, soundings, distributions and vertical profiles, which have no colorbar.

| Setting | Meaning |
|---|---|
| **Colorbars** | *One for the figure*, *per row*, *per column*, *per panel*, or *None*. |
| **Where** | Below, right, above or left. |
| **Length**, **Thickness**, **Gap** | Fractions (0–1) of the panel. Thickness is honoured above matplotlib's usual cap. |
| **Label of bars with none of their own** | Blank: the units. A card's own label comes first, so clear that one for this to show. `$…$` is maths. |
| **Label side**, **Bold label**, **Label size** | Auto, above / left, or below / right. |
| **Ticks of bars with none of their own** | e.g. `0:60:10` (blank: automatic). |
| **Tick format**, **Tick size** | e.g. `%.1f`, `%d`, `%.0e`. |

With several colorbars each takes its own label and ticks from where its colours are set:
a fill layer or a time–height series. A bar shared by several panels, such as one per
row across two columns, takes the first label among them, whichever layer it is on. The label and ticks here are for the bars that have none of their own.

### Legend

What this section offers follows the panels. Time series, soundings, distributions,
profiles, joint distributions and azimuthal means each draw their own legend: **Legends on**
*Each panel* gives *Legend* (for soundings, *Legend (one sounding)*: several soundings always
have one), *At*, *Columns* and *Frame*. These belong to the kind of panel, on its node or on one panel. Box plots and violins have no legend,
and a time–height panel lists only your own [legend entries](#legend-entries), so the section
is hidden without them.

Plan views, sections and 3D scenes have **Layer legend on** a panel or on the figure, with its position (*At*, and
*Anchor x, y* to place it anywhere: the *At* corner of the legend sits at that point, in
fractions of the panel, or of the figure for a figure legend; below 0 or above 1 is
outside, e.g. *At: upper left*, *Anchor: 1.02, 1* just right of the panel), the panel
it sits in, the panels whose entries it lists (blank: all), a title, columns and a
frame. The legend lists layers that have a legend entry (contours, shading, track,
section line), once for all the panels. On the figure it also gathers the legends of
time-series, distribution and sounding panels (each panel's own *Legend* setting turns
its entries on or off), and the key of a hodograph of its own, listing an entry shared by
panels once (three hodographs with the same runs give one legend). A legend on the
figure turns off every panel's own legend, also those of panels it does not list; on a
panel, unticking *Panels' own legends* does the same. Either way a panel whose own
*Legend* is *Yes* keeps its own (and a figure legend gathers it only when listed in
*From panels*), so one panel can have a legend and the others none. The *outside*
positions make room beside the panels. A hodograph's key has its own settings
(*Hodograph → Key at*, *Key columns*, *Key frame*). For one panel alone, pick it in the tree, then *Legend of
this panel* (shown or not, where and its anchor, columns, frame; a sounding's apply to
both its skew-T legend and its hodograph key).

### Contour key

Nested circles labelled with a contour layer's levels (a key for unlabelled contours):
which layer, the label, the position in figure fractions from the lower left, the size,
and a frame.

### Spacing

Extra space *between columns* and *between rows* (a fraction of a panel), and the padding
*around panels* in x and y (inches).

### matplotlib style

A matplotlib style name (e.g. `dark_background`) or a `.mplstyle` file on the server, for
colours and lines. The fonts and sizes stay the editor's. For a dark figure also set the
*Background* to black (*Export* dialog).

## Annotate

**Annotations**, on the Figure node or on a panel, adds text, markers, arrows, lines, boxes and
circles. On the Figure node, each goes in every panel or in the panels listed; on a panel, in that
panel. Annotations follow a panel that is copied or removed.

### Legend entries

A **Legend entry** adds a line of your own to the legend of the panels listed: its
*Text*, and what it *Looks like* (a line, a marker, a line and marker, or a filled box
with an *Opacity*) in its colour, width and style. It is drawn nowhere else. In a
time-series, distribution, profile, joint, azimuthal-mean or sounding panel it comes
after the panel's own entries, and shows even beside one line alone (unless the panel's
*Legend* is off); in a plan view or section it goes in the layer legend. A figure legend
gathers it with the rest, listing the same entry of several panels once.

To leave a line out of the legend, clear its *Label*: a line without a label has
no legend entry. (A series of several runs keeps its run names, which tell its lines
apart.)

### Placing by clicking

Instead of typing positions, pick an item from the *Mouse* list above the preview and
click the figure:

- in a skew-T, a click gives a temperature and pressure;
- a section's A and B can be placed on a plan view the same way (add a *Section line*
  layer to draw it there);
- for two-point items (arrows, lines, boxes) a drag from one point to the other sets
  both.

*Drag: move an annotation* moves one: grab it by its text, marker, centre or middle; grab
an end of a line or arrow to move that end. *Drag a box: plan-view area* sets the area the
plan views show.

### Your own code

For anything the editor has no setting for, write Python that runs after the figure is
drawn. It sees

| Name | What |
|---|---|
| `fig` | The matplotlib figure. |
| `axs` | The axes, by panel. |
| `data` | The plotted arrays. |
| `spec` | The figure's settings. |
| `np`, `matplotlib` | The libraries. |

The code is saved with the figure and runs in its script too. **Code in a figure you open
runs only once you tick *Run the code*.** The code box highlights Python; the editor is
loaded by the browser from a CDN, so where the browser has no internet, tick *Plain text
box*.
