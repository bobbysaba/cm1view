"""The figure-level settings, one row each: where a setting lives in the spec, its widget,
its section of the inspector, the kinds of figure it reaches and its value when a spec has
none.  The inspector's sections (shell/looks.py) go through this table.

Left out, because a table row can't say it: what gives the figure its structure (grid, size,
runs, times, titles, layers), the layers the contour key and Maximum / minimum name, the fixed
box and a kind's panel legend (shell/looks.py has rows of its own for those)."""

from collections import namedtuple
from dataclasses import dataclass

from . import draw as figdraw
from .cards import FONTS, LETTERS, MATH_FONTS, TICKDIR, _num, _panels_loose, _panels_text, _xy, \
    _xy_text
from .kinds import KINDS

KEEP = object()  # (a spec without it leaves the widget as it is)

As = namedtuple("As", "show read")  # spec value -> widget value, and back


def _same(v):
    return v


RAW = As(_same, _same)
FLAG = As(bool, _same)  # (a saved value of any truth, a widget's True or False)
STRIPPED = As(_same, lambda v: v.strip())
TEXT = As(lambda v: v or "", lambda v: v.strip())  # (may be saved as None)
BLANKABLE = As(_num, _num)
SIZE = As(lambda v: _num(v) or None, _num)  # (0: blank)


def _real(blank=0.0):
    """A number that can't be blank: emptied, it is `blank`."""
    return As(float, lambda v: float(v or blank))


def _real_or(blank):
    """... and a saved 0 or None is `blank` too."""
    return As(lambda v: float(v or blank), lambda v: float(v or blank))


def _int_or(blank):
    return As(int, lambda v: int(v or blank))


def _opt_or(blank):
    """A blank-able number in the widget, but never blank in the spec."""
    return As(_num, lambda v: blank if v in (None, "") else float(v))


def _one_of(values, other):
    """A list's value; one it doesn't have (an older figure's, a font not here) is `other`."""
    values = tuple(values)
    return As(lambda v: v if v in values else other, _same)


def _minutes():
    def read(v):
        try:
            return float(v) if str(v).strip() else None
        except ValueError:
            return None
    return As(lambda v: "" if v in (None, "") else f"{float(v):g}", read)


def _cb_place(c):
    """A colorbar's place; older figures only have its orientation."""
    return c.get("location") or (
        "bottom" if c.get("orientation", "horizontal" if c.get("mode", "shared") == "shared"
                          else "vertical") == "horizontal" else "right")


def _cb_store(loc):
    return dict(location=loc, orientation="horizontal" if loc in ("bottom", "top") else "vertical")


def _fit_of(e):
    return "full" if not e.get("tight", True) else "width" if e.get("exact_width") else "trim"


def _fit_store(fit):
    return dict(tight=fit != "full", exact_width=fit == "width")


@dataclass(frozen=True)
class Setting:
    key: str  # in the spec: "suptitle", or "block.key"; of several keys: "block.*"
    widget: str  # the editor's attribute: "xlabel", or "sk.pmax" (a key of its dict sk)
    section: str  # the section it is shown in
    kinds: tuple  # the kinds of figure it reaches
    default: object = KEEP  # shown when the spec has none
    as_: As = RAW  # how it goes between the spec and the widget (of several keys: the
    #                widget's value from the block, the keys from the widget's value)


ALL = tuple(KINDS)


def _reach(what):
    """The kinds whose picture a Style setting reaches (kinds.py)."""
    return tuple(k for k, v in KINDS.items() if what in v.style)


AXES, Y_STEP, CBAR = _reach("axes"), _reach("y_step"), _reach("colorbar")
TIME_LABEL, RUN_LABEL, KEY = _reach("time_label"), _reach("run_label"), _reach("contour_key")
HEIGHTS = ("plan", "xsec")  # (panels at a height: _show_vary)


def _block(block, section, kinds, *rows):
    """Rows of a block: (key, widget, default[, as, [kinds]])."""
    out = []
    for key, widget, default, *more in rows:
        out.append(Setting(f"{block}.{key}" if block else key, widget, section,
                           more[1] if len(more) > 1 else kinds, default,
                           more[0] if more else RAW))
    return out


def _family(block, attr, section, kinds, numbers=(), blanks=(), plain=(), **conv):
    """Rows of a kind's block held in a dict of widgets: no default, as these blocks are
    complete in any spec (default_spec, with_defaults)."""
    conv = dict({k: _real() for k in numbers}, **{k: BLANKABLE for k in blanks}, **conv)
    return [Setting(f"{block}.{k}", f"{attr}.{k}", section, kinds, KEEP, conv.get(k, RAW))
            for k in (*numbers, *blanks, *plain, *(k for k in conv
                                                   if k not in numbers and k not in blanks))]


SETTINGS = (
    _block("", "Titles", ALL, ("suptitle", "suptitle", ""))
    + _block("domain", "Area", ("plan",),
             ("mode", "dom", "storm"), ("half", "half", 12.5, _real_or(12.5)))
    + _block("", "Area", ("plan",), ("coords", "coords", "grid"))
    + _block("xsec", "Area", HEIGHTS,
             ("ztop", "xs_top", 6.0, _real_or(6.0)), ("coords", "xs_coords", "storm"))
    + _block(
        "axes", "Axes and ticks", AXES,
        ("xlabel", "xlabel", ""), ("ylabel", "ylabel", ""), ("ticklabels", "ticklabels", "all"),
        ("share", "share", "none"), ("ticks", "ticks", True), ("minor", "minor", False),
        ("equal", "equal", True, RAW, ("plan",)),
        ("tickdir", "tickdir", "out", _one_of(TICKDIR.values(), "out"), ALL),
        ("xstep", "xstep", None, BLANKABLE), ("ystep", "ystep", None, BLANKABLE, Y_STEP),
        ("frame_lw", "frame_lw", 0.8, _real_or(0.8), ALL), ("grid", "grid", False, FLAG),
        ("grid_ls", "grid_ls", ":"))
    + _block("axes", "Panel labels", ALL,
             ("title_loc", "title_loc", "center"), ("title_bold", "title_bold", True))
    + _block(
        "font", "Text", ALL,
        ("family", "font", "sans-serif", _one_of(FONTS, "sans-serif")),
        ("math", "math", "dejavusans", _one_of(MATH_FONTS.values(), "dejavusans")),
        ("size", "fsize", 10.0, _real(10.0)), ("tick", "fs_tick", None, SIZE),
        ("label", "fs_label", None, SIZE), ("title", "fs_title", None, SIZE),
        ("suptitle", "fs_sup", None, SIZE), ("legend", "fs_legend", None, SIZE))
    + _block("", "Panel labels", ALL, ("label_fit", "label_fit", False, FLAG))
    + _block(
        "letters", "Panel labels", ALL,
        ("on", "let_on", True), ("loc", "let_loc", "upper left"),
        ("fmt", "let_fmt", "{a}", _one_of(LETTERS.values(), "{a}")),
        ("size", "let_size", None, BLANKABLE), ("bold", "let_bold", True),
        ("box", "let_box", False, FLAG))
    + _block(
        "time_label", "Panel labels", TIME_LABEL,
        ("on", "tl_on", True), ("fmt", "tl_fmt", "", As(_same, lambda v: v or "t = {min:g} min")),
        ("loc", "tl_loc", "lower right"), ("size", "tl_size", None, BLANKABLE),
        ("bold", "tl_bold", True), ("box", "tl_box", False, FLAG),
        ("t0_min", "tl_t0", 0.0, _real(), ALL))  # (an older figure's: it moves a time axis too)
    + _block(
        "run_label", "Panel labels", RUN_LABEL,
        ("on", "rl_on", True), ("loc", "rl_loc", "upper left"),
        ("size", "rl_size", None, BLANKABLE), ("bold", "rl_bold", True),
        ("box", "rl_box", False, FLAG), ("run_color", "rl_color", False, FLAG))
    + _block(
        "z_label", "Panel labels", HEIGHTS,
        ("on", "zl_on", False, FLAG), ("fmt", "zl_fmt", "", STRIPPED),
        ("loc", "zl_loc", "upper right"), ("size", "zl_size", None, BLANKABLE),
        ("bold", "zl_bold", True), ("box", "zl_box", False, FLAG))
    + _block(
        "colorbar", "Colorbar", CBAR,
        ("mode", "cb_mode", "shared"), ("label", "cb_label", ""),
        ("shrink", "cb_shrink", 0.7, _real(0.7)), ("ticks", "cb_ticks", ""),
        ("fraction", "cb_fraction", 0.05, _real(0.05)), ("pad", "cb_pad", 0.02, _real()),
        ("label_size", "cb_lsize", None, SIZE), ("tick_size", "cb_tsize", None, SIZE),
        ("label_bold", "cb_lbold", False, FLAG), ("label_side", "cb_lside", ""),
        ("tick_fmt", "cb_fmt", "", STRIPPED), ("*", "cb_loc", KEEP, As(_cb_place, _cb_store)))
    + _block(
        "legend", "Legend", ALL,
        ("where", "lg_where", "panel"), ("loc", "lg_loc", "upper right"),
        ("panel", "lg_panel", 0, As(lambda v: int(v) + 1, lambda v: max(0, int(v or 1) - 1))),
        ("panels", "lg_from", None, As(_panels_text, _panels_loose)),
        ("title", "lg_title", "", TEXT),
        ("ncol", "lg_ncol", 1, As(lambda v: int(v or 1), lambda v: int(v or 1))),
        ("frame", "lg_frame", True), ("anchor", "lg_anchor", None, As(_xy_text, _xy)),
        ("own", "lg_own", True, As(lambda v: v is not False, _same)))
    + _block(
        "contour_key", "Contour key", KEY,
        ("on", "ck_on", False), ("label", "ck_label", "w"), ("x", "ck_x", 0.01, _real()),
        ("y", "ck_y", 0.01, _real()), ("size", "ck_size", 0.1, _real(0.1)),
        ("fs", "ck_fs", 10.0, _real(10.0)), ("frame", "ck_frame", True))
    + _block(
        "extremes", "Maximum and minimum", ("plan", "xsec", "th"),
        ("on", "ex_on", False, FLAG), ("what", "ex_what", "both"),
        ("loc", "ex_loc", "upper center"), ("marker", "ex_marker", True), ("box", "ex_box", True))
    + _block(
        "spacing", "Spacing", ALL,
        ("wspace", "sp_w", 0.02, _real()), ("hspace", "sp_h", 0.02, _real()),
        ("w_pad", "sp_wpad", 0.04, _real()), ("h_pad", "sp_hpad", 0.04, _real()))
    + _block("", "matplotlib style", ALL, ("mplstyle", "mplstyle", "", TEXT))
    + _block(
        "export", "Export", ALL,
        ("format", "fmt", "png"), ("dpi", "dpi", 250, _int_or(250)),
        ("pad", "pad", 0.05, _real()), ("*", "fit", KEEP, As(_fit_of, _fit_store)))
    + _block("", "Export", ALL, ("background", "bg", "white"))
    + _block("code", "Your own code", ALL,
             ("on", "code_on", False, As(bool, bool)),
             ("text", "code", "", As(lambda v: v or "", lambda v: v or "")))
    + _block(
        "ts", "Plot", ("th", "line"),
        ("tmin", "ts_tmin", None, _minutes()), ("tmax", "ts_tmax", None, _minutes()),
        ("zmin", "ts_zmin", 0.0, _real_or(0.0), ("th",)),
        ("zmax", "ts_zmax", 10.0, _real_or(10.0), ("th",)),
        ("zero_line", "ts_zero", False, RAW, ("line",)),
        ("mark", "ts_mark", "", As(lambda v: v or "", _same), ("line",)),
        ("mark_legend", "ts_mark_legend", False, FLAG, ("line",)),
        ("mark_edited", "ts_mark_edited", False, FLAG, ("line",)),
        ("ymin", "ts_ymin", None, BLANKABLE, ("line",)),
        ("ymax", "ts_ymax", None, BLANKABLE, ("line",)))
    + _family("skewt", "sk", "Skew-T", ("sounding",),
              numbers=("pmax", "pmin", "skew", "tmin", "tmax", "lw"),
              plain=("parcel", "params", "guides", "barbs"))
    + _family("skewt", "sk", "Hodograph", ("sounding",),
              numbers=("hodo_max", "hodo_cu", "hodo_cv", "hodo_top", "inset_size", "inset_x",
                       "inset_y"),
              plain=("hodo_center", "hodo_rm", "hodo_lm", "hodo_mean", "hodo_labels",
                     "hodo_heights", "hodo_key", "hodo_key_loc", "hodo_key_ncol",
                     "hodo_key_frame", "srh", "hodo_storm", "inset_loc"))
    + _family("skewt", "sk", "Sounding panels", ("sounding",), numbers=("storm_u", "storm_v"),
              plain=("layout", "table", "storm"))
    + _family("dist", "ds", "Plot", ("dist",),
              blanks=("width", "xmin", "xmax", "ymin", "ymax"),
              plain=("plot", "norm", "bins", "hstyle", "bar_labels", "cum", "whis", "logy",
                     "means", "horizontal", "zero_line"),
              alpha=_opt_or(0.35), lw=_opt_or(1.5))
    + _family("dist", "ds", "Statistics", ("dist",), plain=("stats", "stats_at", "stats_loc"))
    + _family("prof", "po", "Plot", ("profile",), blanks=("xmin", "xmax", "zmin", "zmax"),
              plain=("zero_line", "mark_edited"))
    + _family("joint", "jo", "Plot", ("joint",), blanks=("xmin", "xmax", "ymin", "ymax"),
              plain=("plot", "norm", "bins", "cmap", "cbar_label", "pcts", "log", "reverse",
                     "colorbar", "contours", "contour_labels", "fit", "one_one", "zero_line"),
              ms=_opt_or(2.0), alpha=_opt_or(0.5), lw=_opt_or(1.2))
    + _family("joint", "jo", "Statistics", ("joint",), plain=("stats", "stats_loc"))
    + _family("azim", "ao", "Plot", ("azim",),
              blanks=("vmin", "vmax", "rmin", "rmax", "zmin", "zmax"),
              plain=("plot", "cmap", "nlevels", "cbar_label", "reverse", "colorbar", "clabels"))
    + _family("table", "to", "Table", ("table",), plain=("layout", "compare", "decimals"))
)


PREPARED = ("skewt", "dist")  # (_prepared's)


def _prepared(spec):
    """The blocks whose saved form differs from their widgets', in the widgets' form."""
    sk = spec.get("skewt", {})
    dd = spec.get("dist", {})
    return dict(
        skewt=dict(sk, layout=figdraw.sounding_layout(sk),
                   **{f"hodo_{k}": k in figdraw.hodo_marks(sk) for k in figdraw.HODO_MARKS}),
        dist=dict(dd, stats=figdraw.dist_stat_keys(dd), bar_labels=dd.get("bar_labels") or ""))


def filled(spec):
    """A new figure's spec with the settings it doesn't name at their defaults, in place, so a new
    figure says what it was made with."""
    for st in SETTINGS:
        block, _, key = st.key.rpartition(".")
        if key == "*" or st.default is KEEP:
            continue
        held = spec.setdefault(block, {}) if block else spec
        if key not in held:
            held[key] = st.as_.read(st.as_.show(st.default))
    return spec


def widget_of(ed, st):
    """The widget of setting st in editor ed."""
    attr, _, key = st.widget.partition(".")
    return getattr(ed, attr)[key] if key else getattr(ed, attr)
