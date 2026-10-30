"""Shared pieces of the drawing code: colours, levels, fonts, text and saving."""

import os
import string
import threading

import numpy as np
import matplotlib
from matplotlib.figure import Figure
from matplotlib.colors import (BoundaryNorm, LinearSegmentedColormap, ListedColormap,
                               LogNorm, Normalize)
from matplotlib.offsetbox import AnchoredText

# NWS-style reflectivity steps (every 5 dBZ from 5 dBZ)
NWS_REF = ["#04e9e7", "#019ff4", "#0300f4", "#02fd02", "#01c501", "#008e00", "#fdf802",
           "#e5bc00", "#fd9500", "#fd0000", "#d40000", "#bc0000", "#f800fd", "#9854c6",
           "#fdfdfd"]
RUN_COLORS = ["k", "#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e"]
RUN_STYLES = ["-", "--", ":", "-."]
SND_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "k"]
# matplotlib.rc_context changes matplotlib's global settings: one figure at a time is
# drawn or saved in this process (several viewer sessions share it)
RC_LOCK = threading.RLock()
STORM_NAMES = {"rm": "RM", "lm": "LM", "mean": "mean wind", "custom": "custom"}
FILL_KEYS = ("cmap", "reverse", "white_first", "vmin", "vmax", "nlevels", "style",
             "mask_below", "extend", "units", "cbar_label", "cbar_ticks")
SND_PARAMS = [  # (key, column heading, units) of the sounding parameter table
    ("sbcape", "SBCAPE", "J kg$^{-1}$"), ("mlcape", "MLCAPE", "J kg$^{-1}$"),
    ("mucape", "MUCAPE", "J kg$^{-1}$"), ("mlcin", "MLCIN", "J kg$^{-1}$"),
    ("mllcl", "MLLCL", "m"), ("srh1", "0–1 km SRH", "m$^2$ s$^{-2}$"),
    ("srh3", "0–3 km SRH", "m$^2$ s$^{-2}$"), ("esrh", "ESRH", "m$^2$ s$^{-2}$"),
    ("shear06", "0–6 km shear", "m s$^{-1}$"), ("stp_eff", "STP", ""), ("scp", "SCP", ""),
    # (new ones at the end: saved figure data has the values in this order)
    ("sbcin", "SBCIN", "J kg$^{-1}$"), ("mucin", "MUCIN", "J kg$^{-1}$"),
    ("sblcl", "SBLCL", "m"), ("mllfc", "MLLFC", "m"), ("srh500", "0–500 m SRH", "m$^2$ s$^{-2}$"),
    ("shear01", "0–1 km shear", "m s$^{-1}$"), ("shear03", "0–3 km shear", "m s$^{-1}$"),
    ("stp_fixed", "STP (fixed)", ""),
    ("srh250", "0–250 m SRH", "m$^2$ s$^{-2}$"), ("shear250", "0–250 m shear", "m s$^{-1}$"),
    ("shear500", "0–500 m shear", "m s$^{-1}$")]
HODO_BANDS = [(0, 1, "#e11d48"), (1, 3, "#16a34a"), (3, 6, "#ca8a04"), (6, 9, "#0284c7"),
              (9, 12, "#7c3aed")]
KT = 1.943844
ENTRIES = {"line": "series", "sounding": "soundings", "dist": "dists",
           "profile": "profiles", "joint": "joints", "azim": "azims"}  # (kind -> list)


# colormaps with a neutral (white) middle: kept on 0 when the range has both signs
DIVERGING = {"BrBG", "PiYG", "PRGn", "PuOr", "RdBu", "RdGy", "RdYlBu", "RdYlGn", "bwr",
             "coolwarm", "seismic", "cmo.balance", "cmo.curl", "cmo.delta", "cmo.diff",
             "cmo.tarn"}


def colormap(name, reverse=False, white_first=False, lo=None, hi=None):
    """A matplotlib colormap by name ('reflectivity' = NWS steps; pyart maps such as
    HomeyerRainbow / ChaseSpectral when cmweather or pyart is installed).  white_first: starts from
    white (as for updraft speed).  lo / hi (the fill's range): a diverging map keeps its
    middle on 0 -- -2..6 on RdBu uses the colours of -6..6 from -2 up."""
    if name == "reflectivity":
        cm = ListedColormap(["#ffffff00"] + NWS_REF, name="reflectivity")
    else:
        try:
            cm = matplotlib.colormaps[name]
        except KeyError:
            try:  # either registers HomeyerRainbow, ChaseSpectral, ...
                import cmweather  # noqa: F401
            except ImportError:
                import pyart  # noqa: F401
            cm = matplotlib.colormaps[name]
    if reverse:
        cm = cm.reversed()
    base = name[:-2] if name.endswith("_r") else name
    if (base in DIVERGING and not white_first and lo is not None and hi is not None
            and lo < 0 < hi and lo != -hi):
        m = 2.0 * max(-lo, hi)
        cm = ListedColormap(cm(np.linspace(0.5 + lo / m, 0.5 + hi / m, 256)),
                            name=cm.name + "_zero")
    if white_first:  # white, then 19 colours of the map, blended
        cols = cm(np.linspace(0, 1, 19))
        cm = LinearSegmentedColormap.from_list(cm.name + "_white",
                                               np.vstack([[1, 1, 1, 1], cols]))
    return cm


def _bounds(lay):
    """(min, max) of a fill; a log scale needs min > 0 (else max / 1000)."""
    lo, hi = float(lay["vmin"]), float(lay["vmax"])
    if lay.get("scale") == "log":
        hi = hi if hi > 0 else 1.0
        lo = lo if 0 < lo < hi else hi * 1e-3
    return lo, hi


def _steps(lay, n):
    lo, hi = _bounds(lay)
    return np.geomspace(lo, hi, n + 1) if lay.get("scale") == "log" else \
        np.linspace(lo, hi, n + 1)


def _norm(lay, cm):
    lo, hi = _bounds(lay)
    n = int(lay.get("nlevels") or 0)
    if n > 1:
        return BoundaryNorm(_steps(lay, n), cm.N, extend=lay.get("extend", "neither"))
    return LogNorm(lo, hi) if lay.get("scale") == "log" else Normalize(lo, hi)


def _levels(text):
    """'10, 20' or '-5:5:1' (start:stop:step, inclusive) -> list of floats."""
    out = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if part.count(":") == 2:
            a, b, s = (float(v) for v in part.split(":"))
            out += list(np.arange(a, b + 0.5 * s, s))
        else:
            out.append(float(part))
    return sorted(set(out))


def _levels_list(text):
    """'1, 3, 6' or '1:9:2' -> floats in the order given (heights of the panels)."""
    out = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part.count(":") == 2:
            a, b, s = (float(v) for v in part.split(":"))
            out += [float(v) for v in np.arange(a, b + 0.5 * s, s)]
        elif part:
            out.append(float(part))
    return out


def _anchored(ax, text, opts, size, color=None):
    """A panel label in a corner of the panel (on a white box with opts["box"]), or
    above it (loc "above left" / "above right")."""
    loc = opts.get("loc", "upper left")
    prop = {"weight": "bold" if opts.get("bold", True) else "normal",
            "size": float(opts.get("size") or size)}
    if color is not None:
        prop["color"] = color
    if loc.startswith("above"):
        ax.set_title(text, loc=loc.split()[-1], fontsize=prop["size"], fontweight=prop["weight"],
                     **({} if color is None else {"color": color}))
        return
    box = bool(opts.get("box"))
    at = AnchoredText(text, loc=loc, frameon=box, prop=prop, pad=0.25 if box else 0.4,
                      borderpad=0.5)
    if box:
        at.patch.set(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none",
                     alpha=0.85)
    at.set_in_layout(False)  # it sits in the panel: small panels must not shrink for it
    ax.add_artist(at)


def ann_on(a, i):
    """Whether annotation a is drawn in panel i: its "panel" is -1 (every panel), i, or
    a list of panels holding i."""
    p = a.get("panel", -1)
    ps = [int(q) for q in p] if isinstance(p, (list, tuple)) else [int(p)]
    return -1 in ps or i in ps


def legend_handles(anns, i):
    """[(text, handle)] of the "legend" annotations of panel i: an entry of its own in
    the panel's legend, drawn nowhere else; its "look" is a line, a marker, both, or a
    filled box ("patch", at its "alpha")."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    out = []
    for a in anns:
        txt = str(a.get("text", "")).strip()
        if a.get("kind") != "legend" or not txt or not ann_on(a, i):
            continue
        col, lw, look = a.get("color", "k"), float(a.get("lw", 1.5)), a.get("look", "line")
        if look == "patch":
            h = Patch(facecolor=col, alpha=min(max(float(a.get("alpha", 1.0)), 0.0), 1.0),
                      edgecolor=col, lw=0.5 * lw, ls=a.get("ls", "-"))
        elif look == "line":
            h = Line2D([], [], color=col, lw=lw, ls=a.get("ls", "-"))
        else:  # (a marker, as a Marker annotation draws it; "both": on a line)
            mk = a.get("marker", "o")
            h = Line2D([], [], color=col, lw=lw, ls="none" if look == "marker"
                       else a.get("ls", "-"), marker=mk, ms=6,
                       mew=lw if mk in ("x", "+") else 1.0,
                       mfc="none" if mk in ("o", "s") else col)
        h.set_label(txt)
        out.append((txt, h))
    return out


def panel_letter(i, fmt):
    return (fmt.replace("{a}", string.ascii_lowercase[i % 26])
            .replace("{A}", string.ascii_uppercase[i % 26]))


def time_text(t_s, opts):
    mins = (float(t_s) - 60.0 * float(opts.get("t0_min", 0.0))) / 60.0
    s = int(round(float(t_s)))
    return opts.get("fmt", "t = {min:g} min").format(
        min=round(mins, 2), s=s, hms=f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}")


def _new_fig(spec):
    gap = spec.get("spacing", {})
    fig = Figure(figsize=tuple(float(v) for v in spec["size"]), layout="constrained",
                 facecolor=spec.get("background", "white"))
    fig.get_layout_engine().set(w_pad=float(gap.get("w_pad", 0.04)),
                                h_pad=float(gap.get("h_pad", 0.04)),
                                wspace=float(gap.get("wspace", 0.02)),
                                hspace=float(gap.get("hspace", 0.02)))
    return fig


def _fs(spec):
    return float(spec.get("font", {}).get("size", 10))


def _cell(p):
    """(row, col, rowspan, colspan) of panel p."""
    c = [int(v) for v in p.get("cell", [0, 0])] + [1, 1]
    return c[0], c[1], max(1, c[2]), max(1, c[3])


def part_shares(spec):
    """Each part's share of a figure of parts (of its width side by side, of its height
    stacked): a part's own "share" (0-1), and the rest split among the others by
    their sizes."""
    parts = spec["parts"]
    k = 0 if spec.get("arrange", "row") == "row" else 1
    own = [float(p["share"]) if p.get("share") else None for p in parts]
    size = [float(p["size"][k]) for p in parts]
    free = sum(sz for s, sz in zip(own, size) if s is None)
    rest = max(0.0, 1.0 - sum(s for s in own if s is not None))
    return [max(0.02, s if s is not None else (rest * sz / free if free else 0.0))
            for s, sz in zip(own, size)]


def save(spec, fig, fname, **kw):
    """fig.savefig(fname, **kw) with the spec's fonts and ticks in effect."""
    with RC_LOCK, matplotlib.rc_context(rc(spec)):
        fig.savefig(fname, **kw)


def rc(spec):
    """matplotlib settings of the spec's matplotlib style ("mplstyle"), fonts and axes
    (the fonts and sizes are the spec's own whatever the style sets)."""
    font, ax = spec.get("font", {}), spec.get("axes", {})
    fs = float(font.get("size", 10))
    fam = font.get("family", "sans-serif")
    rc = mpl_style(spec.get("mplstyle"))
    rc.update({"font.size": fs, "font.family": fam,
          "axes.titlesize": font_size(spec, "title"), "axes.labelsize": font_size(spec, "label"),
          "xtick.labelsize": font_size(spec, "tick"), "ytick.labelsize": font_size(spec, "tick"),
          "xtick.direction": ax.get("tickdir", "out"), "ytick.direction": ax.get("tickdir", "out"),
          "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none"})
    math = font.get("math", "dejavusans")
    rc["mathtext.fontset"] = math
    if math == "custom":  # math in the text font
        base = {"sans-serif": "sans", "serif": "serif"}.get(fam, fam)
        rc.update({"mathtext.rm": base, "mathtext.it": f"{base}:italic",
                   "mathtext.bf": f"{base}:bold"})
    if ax.get("frame_lw"):
        lw = float(ax["frame_lw"])
        rc.update({"axes.linewidth": lw, "xtick.major.width": lw, "ytick.major.width": lw,
                   "xtick.minor.width": 0.6 * lw, "ytick.minor.width": 0.6 * lw})
    return rc


def mpl_style(name):
    """The rc settings of a matplotlib style: a name (matplotlib.style.available) or
    a .mplstyle file ({} for none)."""
    name = str(name or "").strip()
    if not name:
        return {}
    from matplotlib.style.core import STYLE_BLACKLIST
    if name in matplotlib.style.library:
        rc = dict(matplotlib.style.library[name])
    else:
        path = os.path.abspath(os.path.expanduser(os.path.expandvars(name)))
        if not os.path.isfile(path):
            raise ValueError(f"matplotlib style {name!r}: no such style or file")
        rc = dict(matplotlib.rc_params_from_file(path, use_default_template=False))
    return {k: v for k, v in rc.items() if k not in STYLE_BLACKLIST}


def font_size(spec, what):
    """Font size (pt) of 'tick' labels, axis 'label's, panel 'title's, the 'suptitle'
    or the 'legend': the spec's own, else a multiple of the base size."""
    font = spec.get("font", {})
    v = font.get(what)
    if v not in (None, "", 0):
        return float(v)
    return float(font.get("size", 10)) * {"tick": 0.9, "label": 1.0, "title": 1.1,
                                          "suptitle": 1.4, "legend": 0.85}[what]


def anchor_kw(loc, anchor):
    """loc and bbox_to_anchor of a legend: with an anchor [x, y] (fractions of the axes,
    or of the figure for a figure legend; outside 0–1 is beyond them) the corner `loc`
    of the legend sits at that point ("best" picks the corner).  An "outside" place keeps
    its side: "outside right upper" puts the legend's upper left corner there (the
    legend to the right of the point), "outside lower center" its upper center."""
    if not anchor:
        return dict(loc=loc)
    words = str(loc).split()
    if words[0] == "outside":
        side, along = words[1], words[2]
        away = dict(right="left", left="right", upper="lower", lower="upper")[side]
        loc = f"{along} {away}" if side in ("left", "right") else f"{away} {along}"
    return dict(loc=loc, bbox_to_anchor=(float(anchor[0]), float(anchor[1])))


def panel_legend(ax, handles, o, spec, loc, frame):
    """A panel's own legend of `handles`: where (o["legend_loc"], else loc, at
    o["legend_anchor"]), how many columns (o["legend_ncol"]) and whether framed
    (o["legend_frame"], else frame) are the panel's own settings.  The entries are kept
    on the axes (ax._cv_entries) for a figure legend that gathers them (figure.py:
    _legends).  A handle without a label (blank, or matplotlib's own "_child1") has no
    entry: a blank Label keeps a line out of the legend.  The panel's "Legend entry"
    annotations (spec["_legend_extra"]: figure._block) come after its own entries."""
    handles = list(handles) + [h for _, h in spec.get("_legend_extra", ())]
    handles = [h for h in handles if str(h.get_label() or "").strip()
               and not str(h.get_label()).startswith("_")]
    if not handles:
        ax._cv_entries = []
        return None
    leg = ax.legend(handles=handles, **anchor_kw(o.get("legend_loc") or loc,
                                                 o.get("legend_anchor")),
                    fontsize=font_size(spec, "legend"), ncol=int(o.get("legend_ncol") or 1),
                    frameon=bool(o.get("legend_frame", frame)), framealpha=0.85)
    ax._cv_entries = [(h, t.get_text()) for h, t in zip(handles, leg.get_texts())]
    return leg


def run_code(fig, axs, data, spec, text):
    """The figure's own code (spec["code"]["text"]), run after everything else is drawn
    with fig, axs (the panels' axes, by panel number), data, spec, np and matplotlib.
    An error leaves the figure as drawn so far, with fig._cv_code_error saying why."""
    env = dict(fig=fig, axs=list(axs), data=data, spec=spec, np=np, matplotlib=matplotlib)
    try:
        exec(compile(str(text), "<figure code>", "exec"), env)  # noqa: S102 (the user's code)
    except Exception as e:  # noqa: BLE001
        import traceback
        line = [f.lineno for f in traceback.extract_tb(e.__traceback__)
                if f.filename == "<figure code>"] or [getattr(e, "lineno", None)]
        fig._cv_code_error = (f"line {line[-1]}: " if line[-1] else "") + \
            f"{type(e).__name__}: {e}"


def run_color(spec, k):
    """Colour of run k (its own, else the k-th of RUN_COLORS)."""
    runs = spec.get("runs") or []
    return (runs[k].get("color") if k < len(runs) else None) or RUN_COLORS[k % len(RUN_COLORS)]


def several_runs(spec):
    """Whether the figure has more than one run: then a run keeps its colour (and line
    style) in every panel, also in a panel with a line of one run only."""
    return len(spec.get("runs") or []) > 1


def by_run(spec, runs):
    """Whether lines from runs `runs` (a run index per line: soundings, distributions)
    are coloured by run: each from another run, and several or several_runs."""
    n = len(runs)
    return n > 0 and len(set(runs)) == n and (n > 1 or several_runs(spec))


def entry_colors(spec, d, key, n_key, p, data_runs=False):
    """Colour of each entry of panel data d (soundings, distributions, joint
    distributions): its own, else its run's when each of the panel's entries comes from
    another run (by_run), else the next of SND_COLORS.  spec[key] holds the entries,
    d[n_key] says how many the panel has, d[f"{p}{j}_e"] is the j-th's index; its run is
    the entry's, or with data_runs d[f"{p}{j}_r"]."""
    ents, n = spec.get(key, []), int(d.get(n_key, 0))
    es = [ents[int(d[f"{p}{j}_e"])] if int(d[f"{p}{j}_e"]) < len(ents) else {}
          for j in range(n)]
    runs = [int(d[f"{p}{j}_r"]) if data_runs else int(e.get("run", 0))
            for j, e in enumerate(es)]
    rc = by_run(spec, runs)
    return [e.get("color") or (run_color(spec, k) if rc else SND_COLORS[j % len(SND_COLORS)])
            for j, (e, k) in enumerate(zip(es, runs))]


def layer_color(spec, lay, d):
    """Colour of a layer in panel data d: the run's (a track with "run_color"), else
    its own."""
    if lay.get("run_color"):  # (the layer's own run, else the panel's)
        return run_color(spec, int(d.get("run", 0) if lay.get("run") is None else lay["run"]))
    return lay.get("color", "k")


def run_style(spec, k):
    """Line style of run k (its own, else the k-th of RUN_STYLES)."""
    runs = spec.get("runs") or []
    return (runs[k].get("ls") if k < len(runs) else None) or RUN_STYLES[k % len(RUN_STYLES)]
