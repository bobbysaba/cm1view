# Style and annotations

## Style

The **Style** tab sets the look shared by every panel, in folding sections.

### Text

| Setting | Meaning |
|---|---|
| **Font** | The text font (the installed fonts are offered). |
| **Math & units font** | The font of `$…$` text such as `m s$^{-1}$`: DejaVu Sans, "like the text font", STIX Sans, STIX (Times-like) or Computer Modern. |
| **Base size (pt)** | Default 10. |
| **Tick labels**, **Axis labels**, **Panel titles**, **Figure title**, **Legends** | Sizes in points; blank follows the base size. |

### Axes and ticks

x and y labels (matplotlib maths allowed, e.g. `w (m s$^{-1}$)`); **Tick labels on** all
panels, outer panels only, or none (outer is best when the panels *share their ranges*);
**Share limits (panels of a kind)** none, x, y, or x and y; **Ticks point** out, in or
across; **x tick every** and **y tick every**; **Frame width**; **Grid style** (dotted,
dashed, solid); **Panel titles at** centre, left or right; and checkboxes for *Tick
marks*, *Minor ticks*, *Grid lines*, *Equal x/y scale* and *Bold titles*.

### Panel labels

Each label is switched on by its checkbox and then has its own *Where* (the corners and
edges of the panel, or above its left or right corner), *Size*, *Bold* and *White box*:

- **Panel letters**: *Style* `a`, `(a)`, `a)`, `A` or `(A)`.
- **Time label**: *Text* with `{min}` (minutes), `{s}` (seconds) or `{hms}` (h:mm:ss),
  e.g. `t = {min:g} min`. **Minutes counted from** sets time zero in model minutes (e.g.
  the initiation time).
- **Height label** (for panels at several heights): *Text* with `{z}` (the height, km)
  or `{k}` (the model level), e.g. `{z:g} km AGL`; blank gives `z = … km` or `k = …`.
- **Run name** (for figures of several runs), optionally *In the run's colour*.

### Colorbar

| Setting | Meaning |
|---|---|
| **Colorbars** | *One for the figure*, *per row*, *per column*, *per panel*, or *None*. |
| **Where** | Below, right, above or left. |
| **Length**, **Thickness**, **Gap** | Fractions (0–1) of the panel. Thickness is honoured above matplotlib's usual cap. |
| **Label, every colorbar** | A label for the bars without their own (blank: the units). `$…$` is maths. |
| **Label side**, **Bold label**, **Label size** | Auto, above / left, or below / right. |
| **Ticks, every colorbar** | e.g. `0:60:10` (blank: automatic). |
| **Tick format**, **Tick size** | e.g. `%.1f`, `%d`, `%.0e`. |

With several colorbars each takes its own label and ticks from where its colours are set:
a fill layer (*Layers*), a time–height series (*Layers → Series*) or a panel's field
(*Panels*, when the panels differ in field). The Style tab's label and ticks are for the
bars that have none of their own.

### Legend

**Layer legend on** a panel or on the figure (this part), with its position, the panel
it sits in, the panels whose entries it lists (blank: all), a title, columns and a
frame. The legend lists layers that have a legend entry (contours, shading, track,
section line), once for all the panels. On the figure it also gathers the legends of
time-series, distribution and sounding panels (each panel's own *Legend* setting turns
its entries on or off), listing an entry shared by panels once. The *outside* positions
make room beside the panels. The columns and frame of those panels' own legends are set
in *Panels*.

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
*Background* to black (Export tab).

## Annotate

The **Annotate** tab adds text, markers, arrows, lines, boxes and circles. Each goes in
every panel (leave *Panels* blank) or in the panels listed (e.g. `1, 3-4`).

### Placing by clicking

Instead of typing positions, pick an item from the *Click …* list above the preview and
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
