"""Table panels as files: CSV and LaTeX.  The cells are the ones the figure draws (draw.tbl_grid
on the same arrays and table settings, so the same rows, columns, comparisons and decimals), only
written as text: an ASCII minus in CSV, `$-$` in LaTeX.  Empty cells (no value) are empty in CSV and
`--` in LaTeX.  No Panel / Bokeh here; the editor's Export dialog and `cm1view render --tables`
share it."""

import csv
import io
import os
import re

from . import draw as figdraw
from . import spec as fg
from .draw.base import _cell

MINUS, DASH = "−", "–"  # (what tbl_grid writes: a minus sign, "no value")


def tables_of(doc, data):
    """[(panel id, letter, heads, rows, spans, why)] for each table panel of document `doc` with
    values in `data` ({panel id: arrays}), in reading order.  heads/rows/spans: tbl_grid's."""
    res = figdraw.resolve(doc)
    pans = sorted(res["panels"], key=lambda p: _cell(p)[:2])
    out = []
    for n, p in enumerate(pans):
        if p["kind"] != "table":
            continue
        d = data.get(p["id"])
        if not d or d.get("missing"):
            continue
        heads, rows, spans = figdraw.tbl_grid(d, figdraw.panel_view(res, p).get("table") or {})
        at = n if p.get("letter") is None else int(p["letter"])
        out.append((p["id"], figdraw.panel_letter(at, "{a}"), heads, rows, spans,
                    str(d.get("why") or "")))
    return out


def _flat(s):
    return " ".join(str(s).split())


def _plain(s):
    """Text for CSV: units written as mathtext ("kg$^{-1}$") become "kg^-1"."""
    s = re.sub(r"\$([^$]*)\$", lambda m: m[1].replace("{", "").replace("}", ""), _flat(s))
    return s.replace(MINUS, "-")


def to_csv(heads, rows, spans=()):
    """CSV text of one table.  A column under a source heading (spans) says it first:
    "source: name (units)"."""
    src = {}
    for name, j, n in spans:
        src.update({j + i: name for i in range(n)})
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([""] + [(f"{_plain(src[j])}: " if j in src else "") + _plain(h)
                       for j, h in enumerate(heads)])
    for name, cells in rows:
        w.writerow([_plain(name)] + ["" if c == DASH else _plain(c) for c in cells])
    return buf.getvalue()


_TEX = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\^{}", MINUS: "$-$",
        "·": r"$\cdot$", "°": r"\textdegree{}", "²": "$^2$", "³": "$^3$"}


def _tex(s):
    """Text for LaTeX: what is between $ $ (mathtext units) is already math and stays."""
    parts = _flat(s).split("$")
    if len(parts) % 2 == 0:  # (a lone $)
        parts = ["$".join(parts)]
    return "".join("$" + x + "$" if i % 2 else "".join(_TEX.get(c, c) for c in x)
                   for i, x in enumerate(parts))


def to_latex(heads, rows, spans=(), why=""):
    """A LaTeX `tabular` of one table (needs the booktabs package; wrap it in a `table` for a
    caption).  A source heading spans its columns."""
    cols = "l" + "c" * len(heads)
    out = ["% needs \\usepackage{booktabs}", f"\\begin{{tabular}}{{{cols}}}", "\\toprule"]
    if spans:
        row, rules, at = [""], [], 0
        for name, j, n in spans:
            row += [""] * (j - at) if j > at else []
            row.append(f"\\multicolumn{{{n}}}{{c}}{{{_tex(name)}}}")
            rules.append(f"\\cmidrule(lr){{{j + 2}-{j + 1 + n}}}")
            at = j + n
        row += [""] * (len(heads) - at)
        out += [" & ".join(row) + r" \\", "".join(rules)]
    out.append(" & ".join([""] + [_tex(h) for h in heads]) + r" \\")
    out.append("\\midrule")
    for name, cells in rows:
        out.append(" & ".join([_tex(name)] + ["--" if c == DASH else _tex(c) for c in cells])
                   + r" \\")
    out += ["\\bottomrule", "\\end{tabular}"]
    if why:
        out.append("% no value: " + _flat(why))
    return "\n".join(out) + "\n"


def table_paths(doc, data, base, csv_=True, tex=True):
    """{path: text} of the tables of `doc` saved beside the image `base`: <base>_table.csv /.tex,
    or <base>_table_<letter>… when the figure has several tables."""
    root = os.path.splitext(fg.bundle_paths(doc, base)["image"])[0]
    ts = tables_of(doc, data)
    out = {}
    for _, letter, heads, rows, spans, why in ts:
        stem = f"{root}_table" + (f"_{letter}" if len(ts) > 1 else "")
        if csv_:
            out[stem + ".csv"] = to_csv(heads, rows, spans)
        if tex:
            out[stem + ".tex"] = to_latex(heads, rows, spans, why)
    return out


def save_tables(doc, data, base, csv_=True, tex=True):
    """Write table_paths; returns the paths (none if the figure has no table with values)."""
    files = table_paths(doc, data, base, csv_, tex)
    for path, text in files.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return list(files)
