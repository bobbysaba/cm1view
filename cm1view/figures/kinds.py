"""What the figure editor knows about each kind of panel, one entry per kind: a new kind
is one more entry here (and its cards, spec block and drawing)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    label: str  # in the "Panels show" list
    name: str  # a figure part of this kind, in words
    shape: float  # a panel's height / width (figure size)
    cols: tuple = ()  # its columns in the Layers tab
    labels: tuple = ("", "")  # its x and y labels to start with
    colorbar: tuple = ("none",)  # its colorbars (and where) to start with; (): as they are
    one: str = "panel"  # one of what it draws, in words
    head: str = ""  # a panel tree row's heading
    size: object = None  # (rows, columns) -> a figure (width, height), in
    note: str = ""  # what the quick start says of it
    cards: str = ""  # the editor's list of its cards, and its methods for them:
    card: str = ""  # one card from a spec entry
    show: str = ""  # the list into its column
    add: str = ""  # a new card, when there are none
    from_tool: str = ""  # the entries of the viewer's tool for it, when there are any
    one_run: bool = False  # each card is of one run (w["run"])
    quick_grid: bool = True  # the quick start sets its rows and columns
    spread: bool = False  # the quick start puts its cards one per panel
    style: tuple = ("axes", "y_step", "time_label")  # the Style settings it draws (below)
    letter_at: str = "lower left"  # where a new figure's panel letters go
    time_at: str = "lower right"  # ... and its time label


def _wide(first, each, extra=0.0):
    """A figure's width: `first` with one column, else `each` per column (in)."""
    return lambda c: (first if c == 1 else each * c) + extra


def _sized(width, per_row, extra=0.3):
    return lambda r, c: (width(c), per_row * r + extra)


# What in the Style tab reaches each kind's picture (checked on the demo, every setting moved
# and the figure redrawn).  Left out, a setting changes nothing there:
# - axes: labels, tick labels, shared limits, tick steps and marks, grid (a 3D scene has its
#   own, under Look; its titles, tick direction and frame width are always shown: they reach
#   its title and colorbars)
# - y_step: a sounding's pressure axis keeps its ticks
# - colorbar: lines have none; joint and azimuthal panels draw their own (Layers → Plot)
# - contour_key: needs contour layers, which only maps draw (shown too while on: figures.style)
# - time_label: a series has no one time (an old figure's "Minutes counted from" still moves
#   its time axis, so that box is not this switch's)
# - run_label: only panels read per run say whose they are; the others' legends do
MAP_STYLE = ("axes", "y_step", "time_label", "colorbar", "contour_key", "run_label")

KINDS = {
    "plan": Kind(
        "Plan views", "plan views", 0.75, cols=("plan_layers",),
        labels=("x (km)", "y (km)"), colorbar=(), style=MAP_STYLE),
    "xsec": Kind(
        "Vertical cross-sections", "cross-sections", 0.5, cols=("xsec_col", "plan_layers"),
        labels=("", "height (km)"), colorbar=(), cards="sec_cards", spread=True, style=MAP_STYLE,
        note="A section card per panel (Layers → Sections), alternately x–z and "
             "y–z (through the storm when it is tracked) at the shown time: set "
             "each card's run, time "
             "and section there.  For runs × sections, keep one row of cards and "
             "click each one's <b>One per run</b>."),
    "th": Kind(
        "Time–height (series)", "time–height", 0.55, cols=("series_col",),
        labels=("time (min)", "height (km)"), colorbar=("row", "right"),
        size=lambda r, c: (4.5 * c + 1.0, 2.8 * r + 0.6), cards="ser_cards", show="_show_series",
        quick_grid=False, style=("axes", "y_step", "colorbar", "run_label"),
        note="Time–height panels: a series card per panel (Layers → Series: its "
             "run and panel), like the section cards; click a card's <b>One per "
             "run</b> for runs × series.  It starts with no series, so nothing is "
             "computed until you add one."),
    "line": Kind(
        "Time series", "time series", 0.45, cols=("series_col",), labels=("time (min)", ""),
        one="line", head="Time series", size=_sized(_wide(7.0, 6.0), 3.0, 0.5),
        cards="ser_cards", show="_show_series", style=("axes", "y_step"),
        note="Time series: it starts with no series, so nothing is computed until "
             "you add one in Layers → Series (each card with its run, or all runs, "
             "and its panel)."),
    "sounding": Kind(
        "Soundings", "soundings", 1.0, cols=("snd_col",),
        labels=("temperature (°C)", "pressure (hPa)"), one="sounding", head="Sounding",
        cards="snd_cards", card="_snd_card", show="_show_soundings", add="_add_sounding",
        from_tool="tab_soundings", one_run=True, spread=True, style=("axes", "time_label"),
        letter_at="above left", time_at="above right",  # (clear of the barbs and the inset)
        note="The Sounding tab's soundings go one per panel (more soundings "
             "than panels: they wrap and share panels); panels left over start "
             "as a copy of the last, to change in Layers → Soundings."),
    "dist": Kind(
        "Distributions", "distributions", 0.7, cols=("dist_col",), one="distribution",
        head="Distribution", size=_sized(_wide(5.5, 4.2), 3.6),
        cards="dist_cards", card="_dist_card", show="_show_dists", add="_add_dist",
        from_tool="tab_dists", one_run=True, spread=True,
        note="The Distribution tool's distributions go one per panel (more than "
             "panels: they wrap and share panels); panels left over start as a "
             "copy of the last, to change in Layers → Distributions."),
    "profile": Kind(
        "Vertical profiles", "profiles", 1.3, cols=("prof_col",), labels=("", "height (km)"),
        one="profile", head="Profile", size=_sized(_wide(4.0, 3.4, 0.4), 4.6),
        cards="prof_cards", card="_prof_card", show="_show_profiles", add="_add_profile",
        from_tool="tab_profiles", spread=True,
        note="The Series tool's layer series go one per panel at the shown time "
             "(more than panels: they wrap and share panels); panels left over "
             "start as a copy of the last, to change in Layers → Profiles."),
    "joint": Kind(
        "Joint distributions (x vs y)", "joint distributions", 0.85, cols=("joint_col",),
        one="joint distribution", head="Joint", size=_sized(_wide(5.2, 4.4, 0.3), 4.0),
        cards="joint_cards", card="_joint_card", show="_show_joints", add="_add_joint",
        one_run=True, spread=True,
        note="Every panel starts with vertical vorticity against w at 1 km at the "
             "shown time, to change in Layers → Joint distributions."),
    "azim": Kind(
        "Azimuthal means (radius–height)", "azimuthal means", 0.8, cols=("azim_col",),
        one="azimuthal mean", head="Azimuthal", size=_sized(_wide(5.6, 4.6, 0.3), 3.8),
        cards="azim_cards", card="_azim_card", show="_show_azims", add="_add_azim",
        one_run=True, spread=True,
        note="Every panel starts with w around the tracked storm (else the middle "
             "of the map's view) at the shown time, the whole ring out to 20 km, to "
             "change in Layers → Azimuthal means."),
    "table": Kind(
        "Tables (sounding parameters, field statistics)", "tables", 0.5, cols=("table_col",),
        one="table", head="Table", size=lambda r, c: (7.5 * c, 3.0 * r + 0.3),
        cards="table_cards", card="_table_card", show="_show_tables", add="_add_table",
        quick_grid=False, style=(),
        note="A table starts with sounding parameters at the shown time: pick its values, "
             "runs and times in Layers → Tables, and add a card for more columns."),
    "scene": Kind(
        "3D scene (one picture)", "scene", 0.8, cols=("scene_col",),
        size=lambda r, c: (6.5, 5.2), quick_grid=False, style=("time_label", "run_label"),
        note="One 3D picture of what the 3D workspace shows (its box, surfaces "
             "and camera; the whole domain without a box), at the shown time: "
             "change it in Layers."),
}

KIND_LABELS = {k.label: key for key, k in KINDS.items()}  # (the "Panels show" list)
KIND_NAMES = {key: k.name for key, k in KINDS.items()}
MAPS = ("plan", "xsec")  # (with a fill field, a grid and panels that differ)
LINEAR = tuple(key for key in KINDS if key not in ("scene", "table"))  # (axes that clicks map onto)
LAYER_COLS = tuple(dict.fromkeys(c for k in KINDS.values() for c in k.cols))
CARD_SHOWS = tuple(dict.fromkeys(k.show for k in KINDS.values() if k.show))
ONE_RUN_CARDS = tuple((k.one, k.cards) for k in KINDS.values() if k.one_run)
TIME_CARDS = tuple(dict.fromkeys(k.cards for k in KINDS.values()
                                 if k.cards and k.cards != "ser_cards"))  # (a series: no time)
SEVERAL_RUN_CARDS = ("ser_cards", "prof_cards", "table_cards")  # (their cards: SeveralRuns)
