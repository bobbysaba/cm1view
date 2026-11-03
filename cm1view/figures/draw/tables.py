"""Table panels: values of runs and times as a table drawn in the panel (rules above and
below, none between its rows, as journals set them)."""

import matplotlib
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.textpath import TextPath
from matplotlib.transforms import Affine2D, ScaledTranslation

from .base import font_size


def tbl_decimals(v):
    """Decimals that show values v to about three significant figures."""
    v = np.abs(np.asarray(v, dtype=float))
    v = v[np.isfinite(v) & (v > 0)]
    if not v.size:
        return 0
    return int(np.clip(2 - np.floor(np.log10(v.max())), 0, 6))


def _tbl_cell(v, dec, signed):
    if not np.isfinite(v):
        return "–"
    v = round(float(v), dec) + 0.0  # (not "-0")
    return (f"{v:+.{dec}f}" if signed and v else f"{v:.{dec}f}").replace("-", "−")


def _tbl_head(d, j):
    """The heading of value j in one line: its source (if any), name and units."""
    src, name, units = (str(d[f"Q{j}_{k}"]) for k in ("src", "name", "units"))
    return " ".join(x for x in (src, name, f"({units})" if units else "") if x)


def _tbl_column_head(d, j):
    """The heading of a column of value j, under its source (_tbl_spans): name, then units."""
    name, units = str(d[f"Q{j}_name"]), str(d[f"Q{j}_units"])
    return f"{name}\n({units})" if units else name


def _tbl_spans(d):
    """(source, first value, how many) of the neighbouring values with one source."""
    out = []
    for j in range(int(d["nq"])):
        src = str(d[f"Q{j}_src"])
        if out and out[-1][0] == src:
            out[-1][2] += 1
        else:
            out.append([src, j, 1])
    return [tuple(s) for s in out if s[0]]


def tbl_grid(d, o):
    """(column headings, rows [(row heading, cell texts)], spans over the columns (_tbl_spans))
    of table panel data d with table options o: layout ("rows", "values", "values_run", "values_time"), compare ("": values, "run": each run less
    the first run at that time, "time": each time less the first time of that run) and
    decimals (-1: automatic)."""
    ks, mins, names = (np.asarray(d[k]) for k in ("row_k", "row_min", "row_run"))
    runs = list(dict.fromkeys(int(k) for k in ks))
    times = sorted({float(m) for m in mins})
    name = {int(k): str(n) for k, n in zip(ks, names)}
    nq = int(d["nq"])
    compare = o.get("compare") or ""
    compare = compare if (compare == "run" and len(runs) > 1) or \
        (compare == "time" and len(times) > 1) else ""
    at = [{(int(k), float(m)): float(v) for k, m, v in zip(ks, mins, np.ravel(d[f"Q{j}_v"]))}
          for j in range(nq)]

    def run_word(k):
        return f"{name[k]} − {name[runs[0]]}" if compare == "run" and k != runs[0] else name[k]

    def time_word(m):
        return f"{m:g} − {times[0]:g} min" if compare == "time" and m != times[0] else f"{m:g} min"

    def val(j, k, m):
        v = at[j].get((k, m), np.nan)
        if compare == "run" and k != runs[0]:
            v -= at[j].get((runs[0], m), np.nan)
        elif compare == "time" and m != times[0]:
            v -= at[j].get((k, times[0]), np.nan)
        return v

    def text(j, k, m):
        q = int(d[f"Q{j}_dec"])
        dec = int(o["decimals"]) if int(o.get("decimals", -1)) >= 0 and \
            str(d[f"Q{j}_name"]) != "n" else q if q >= 0 else \
            tbl_decimals(list(at[j].values()))
        moved = (compare == "run" and k != runs[0]) or (compare == "time" and m != times[0])
        return _tbl_cell(val(j, k, m), dec, moved)

    def both(k, m):  # (of a run and a time: what differs in this table)
        words = ([run_word(k)] if len(runs) > 1 else []) + \
            ([time_word(m)] if len(times) > 1 or len(runs) == 1 else [])
        return " · ".join(words)

    pairs = sorted(set(zip((int(k) for k in ks), (float(m) for m in mins))))
    layout = o.get("layout") or "rows"
    if layout == "values":
        return ([both(*c) for c in pairs],
                [(_tbl_head(d, j), [text(j, *c) for c in pairs]) for j in range(nq)], [])
    if layout == "values_run":  # (a row per value and run, a column per time)
        return ([time_word(m) for m in times],
                [(_tbl_head(d, j) + (f" · {run_word(k)}" if len(runs) > 1 else ""),
                  [text(j, k, m) for m in times]) for j in range(nq) for k in runs], [])
    if layout == "values_time":  # (a row per value and time, a column per run)
        return ([run_word(k) for k in runs],
                [(_tbl_head(d, j) + (f" · {time_word(m)}" if len(times) > 1 else ""),
                  [text(j, k, m) for k in runs]) for j in range(nq) for m in times], [])
    return ([_tbl_column_head(d, j) for j in range(nq)],
            [(both(*c), [text(j, *c) for j in range(nq)]) for c in pairs], _tbl_spans(d))


def _tbl_width(s, fp):
    """The width (pt) of the widest line of s at font properties fp."""
    w = 0.0
    for line in str(s).split("\n"):
        if line.strip():
            w = max(w, TextPath((0, 0), line, prop=fp).get_extents().width)
    return w


def _table(fig, ax, d, spec, fs):
    """A table panel (tbl_grid; the type shrinks to fit the panel, from the base font size)."""
    heads, rows, spans = tbl_grid(d, spec.get("table") or {})
    ax.axis("off")
    size = font_size(spec, "label")
    table = [[""] + heads] + [[r] + cells for r, cells in rows]
    plain, bold = FontProperties(size=size), FontProperties(size=size, weight="bold")
    widths = np.array([max(_tbl_width(row[c], bold if r == 0 else plain)
                           for r, row in enumerate(table)) for c in range(len(table[0]))])
    pad = 1.4 * size
    for src, j, n in spans:  # (a span wider than its columns widens them)
        short = _tbl_width(src, bold) + pad - widths[j + 1:j + 1 + n].sum() - pad * n
        if short > 0:
            widths[j + 1:j + 1 + n] += short / n
    nl = [max(str(x).count("\n") + 1 for x in row) for row in table]
    line, gap = 1.3 * size, 0.45 * size
    tall = sum(nl) * line + len(nl) * gap + (line + gap if spans else 0.0)
    room_w, room_h = ax.bbox.width * 72.0 / fig.dpi, ax.bbox.height * 72.0 / fig.dpi
    k = min(1.0, 0.98 * room_w / max(widths.sum() + pad * len(widths), 1.0),
            0.92 * room_h / max(tall, 1.0))
    size, widths, pad, line, gap = size * k, widths * k, pad * k, line * k, gap * k
    cols = widths + pad
    if cols.sum() < room_w:  # (spread out, within reason)
        cols = cols + min((room_w - cols.sum()) / cols.size, 0.6 * pad + 0.25 * cols.mean())
    x = -0.5 * cols.sum() + np.concatenate([[0.0], np.cumsum(cols)[:-1]])
    # (in points from the top middle of the panel, so a layout that moves it keeps the rows)
    at = Affine2D().scale(1.0 / 72.0) + fig.dpi_scale_trans + \
        ScaledTranslation(0.5, 1.0, ax.transAxes)
    col = matplotlib.rcParams["text.color"]

    def rule(x0, x1, y, lw):
        ax.add_line(Line2D([x0, x1], [y, y], transform=at, color=col, lw=lw, clip_on=False))

    def put(xc, y, s, ha="center", bold=False):
        ax.text(xc, y, s, transform=at, ha=ha, va="center", fontsize=size, clip_on=False,
                linespacing=1.15, fontweight="bold" if bold else "normal")

    left, right = x[0], x[-1] + cols[-1]
    y = -0.25 * size
    rule(left, right, y, 1.0)
    if spans:
        h = line + gap
        for src, j, n in spans:
            x0, x1 = x[j + 1], x[j + n] + cols[j + n]
            put(0.5 * (x0 + x1), y - 0.5 * h, src, bold=True)
            rule(x0 + 0.25 * pad, x1 - 0.25 * pad, y - h, 0.6)
        y -= h
    for r, row in enumerate(table):
        h = nl[r] * line + gap
        for c, s in enumerate(row):
            put(x[c] + 0.5 * (pad if c == 0 else cols[c]), y - 0.5 * h, s,
                "left" if c == 0 else "center", r == 0)
        y -= h
        if r == 0:
            rule(left, right, y, 0.6)
    rule(left, right, y, 1.0)
    if d.get("why"):
        ax.text(left, y - 0.4 * size, f"– no value: {d['why']}", transform=at, ha="left", va="top",
                fontsize=0.8 * size, color="0.4", clip_on=False)
