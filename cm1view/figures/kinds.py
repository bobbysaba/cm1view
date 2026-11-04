"""What the figure editor knows about each kind of panel, one entry per kind: a new kind
is one more entry here (and its cards, spec block and drawing)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    label: str  # in the "Panels show" list
    name: str  # a figure part of this kind, in words
    shape: float  # a panel's height / width (figure size)
    labels: tuple = ("", "")  # its x and y labels to start with
    colorbar: tuple = ("none",)  # its colorbars (and where) to start with; (): as they are
    one: str = "panel"  # one of what it draws, in words
    head: str = ""  # a panel tree row's heading
    size: object = None  # (rows, columns) -> a figure (width, height), in
    note: str = ""  # what the quick start says of it
    quick_grid: bool = True  # the quick start sets its rows and columns
    entries: str = ""  # the spec's list of what its panels hold, one per panel in a new figure
    style: tuple = ("axes", "y_step", "time_label")  # the Style settings it draws (below)
    letter_at: str = "lower left"  # where a new figure's panel letters go
    time_at: str = "lower right"  # ... and its time label


def _wide(first, each, extra=0.0):
    """A figure's width: `first` with one column, else `each` per column (in)."""
    return lambda c: (first if c == 1 else each * c) + extra


def _sized(width, per_row, extra=0.3):
    return lambda r, c: (width(c), per_row * r + extra)


# What of the look settings reaches each kind's picture (checked on the demo, every setting moved
# and the figure redrawn).  Left out, a setting changes nothing there:
# - axes: labels, tick labels, shared limits, tick steps and marks, grid (a 3D scene has its
#   own, under Look; its titles, tick direction and frame width are always shown: they reach
#   its title and colorbars)
# - y_step: a sounding's pressure axis keeps its ticks
# - colorbar: lines have none; joint and azimuthal panels draw their own (Plot)
# - contour_key: needs contour layers, which only maps draw (shown too while on: figures.style)
# - time_label: a series has no one time (an old figure's "Minutes counted from" still moves
#   its time axis, so that box is not this switch's)
# - run_label: only panels read per run say whose they are; the others' legends do
MAP_STYLE = ("axes", "y_step", "time_label", "colorbar", "contour_key", "run_label")

KINDS = {
    "plan": Kind(
        "Plan views", "plan views", 0.75,
        labels=("x (km)", "y (km)"), colorbar=(), style=MAP_STYLE),
    "xsec": Kind(
        "Vertical cross-sections", "cross-sections", 0.5,
        labels=("", "height (km)"), colorbar=(), style=MAP_STYLE,
        note="Panels alternately x–z and y–z (through the storm when it is tracked) at the "
             "shown time: pick a panel in the tree to set its run, time and section."),
    "th": Kind(
        "Time–height (series)", "time–height", 0.55,
        labels=("time (min)", "height (km)"), colorbar=("row", "right"),
        size=lambda r, c: (4.5 * c + 1.0, 2.8 * r + 0.6),
        quick_grid=False, style=("axes", "y_step", "colorbar", "run_label"),
        note="It starts with no series, so nothing is computed until you add one: "
             "<b>+ Time–height panel</b> in the tree's Time–height node."),
    "line": Kind(
        "Time series", "time series", 0.45, labels=("time (min)", ""),
        one="line", head="Time series", size=_sized(_wide(7.0, 6.0), 3.0, 0.5), style=("axes", "y_step"),
        note="It starts with no series, so nothing is computed until you add one: pick the "
             "panel in the tree (each series has its run, or all runs)."),
    "sounding": Kind(
        "Soundings", "soundings", 1.0,
        labels=("temperature (°C)", "pressure (hPa)"), one="sounding", head="Sounding",
        entries="soundings", style=("axes", "time_label"),
        letter_at="above left", time_at="above right",  # (clear of the barbs and the inset)
        note="The Sounding tab's soundings go one per panel (more soundings "
             "than panels: they wrap and share panels); panels left over start "
             "as a copy of the last, to change in the tree."),
    "dist": Kind(
        "Distributions", "distributions", 0.7, one="distribution",
        head="Distribution", size=_sized(_wide(5.5, 4.2), 3.6), entries="dists",
        note="The Distribution tool's distributions go one per panel (more than "
             "panels: they wrap and share panels); panels left over start as a "
             "copy of the last, to change in the tree."),
    "profile": Kind(
        "Vertical profiles", "profiles", 1.3, labels=("", "height (km)"),
        one="profile", head="Profile", size=_sized(_wide(4.0, 3.4, 0.4), 4.6), entries="profiles",
        note="The Series tool's layer series go one per panel at the shown time "
             "(more than panels: they wrap and share panels); panels left over "
             "start as a copy of the last, to change in the tree."),
    "joint": Kind(
        "Joint distributions (x vs y)", "joint distributions", 0.85,
        one="joint distribution", head="Joint", size=_sized(_wide(5.2, 4.4, 0.3), 4.0), entries="joints",
        note="Every panel starts with vertical vorticity against w at 1 km at the "
             "shown time, to change in the tree."),
    "azim": Kind(
        "Azimuthal means (radius–height)", "azimuthal means", 0.8,
        one="azimuthal mean", head="Azimuthal", size=_sized(_wide(5.6, 4.6, 0.3), 3.8), entries="azims",
        note="Every panel starts with w around the tracked storm (else the middle "
             "of the map's view) at the shown time, the whole ring out to 20 km, to "
             "change in the tree."),
    "table": Kind(
        "Tables (sounding parameters, field statistics)", "tables", 0.5,
        one="table", head="Table", size=lambda r, c: (7.5 * c, 3.0 * r + 0.3), entries="tables",
        quick_grid=False, style=(),
        note="A table starts with sounding parameters at the shown time: pick its values, "
             "runs and times in the tree, and add more for more columns."),
    "scene": Kind(
        "3D scene (one picture)", "scene", 0.8,
        size=lambda r, c: (6.5, 5.2), quick_grid=False, style=("time_label", "run_label"),
        note="One 3D picture of what the 3D workspace shows (its box, surfaces "
             "and camera; the whole domain without a box), at the shown time: "
             "change it in the tree."),
}

KIND_LABELS = {k.label: key for key, k in KINDS.items()}  # (the "Panels show" list)
MAPS = ("plan", "xsec")  # (with a fill field, a grid and panels that differ)
LINEAR = tuple(key for key in KINDS if key not in ("scene", "table"))  # (axes that clicks map onto)
