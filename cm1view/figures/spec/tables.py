"""Table panels: sounding parameters and field statistics, chosen on cards, across runs and
times.  A card (spec["tables"]) gives a table's columns of values, each read from every one
of its runs at every one of its times; the cards of a panel make one table."""

import re

import numpy as np

from ...core import dist
from .. import draw as figdraw
from .base import entry_at, profile_runs, since_t0
from .panels import _param, sounding_label

TBL_STATS = {"mean": "mean", "sd": "sd", "min": "min", "p1": "1st pct.", "p5": "5th pct.",
             "p10": "10th pct.", "p25": "25th pct.", "median": "median", "p75": "75th pct.",
             "p90": "90th pct.", "p95": "95th pct.", "p99": "99th pct.", "p999": "99.9th pct.",
             "max": "max", "iqr": "IQR", "n": "n"}
_QUANTILE = {"p1": 0.01, "p5": 0.05, "p10": 0.1, "p25": 0.25, "median": 0.5, "p75": 0.75,
             "p90": 0.9, "p95": 0.95, "p99": 0.99, "p999": 0.999}
_ONE_DECIMAL = ("stp_eff", "stp_fixed", "scp")  # (of the parameters: the others, none)


def tbl_defaults(recipe, run_index=0, time_s=0.0, where=None, label=""):
    """A spec["tables"] entry: what ("sounding": parameters `params` of the sounding at
    `where`; "field": statistics `stats` of dist recipe `recipe`) from its runs ("runs"
    as in a profile entry) at its times (times_s, model s of its first run; the others
    at the same time since their time zeros)."""
    return dict(what="sounding", panel=0, label=label, run=int(run_index), runs=[int(run_index)],
                times_s=[float(time_s)],
                where=dict(where or dict(kind="trk", x=0.0, y=0.0, avg=0.0)),
                params=["mlcape", "mlcin", "srh1", "shear06"],
                recipe=dist.normalize(recipe), stats=["mean", "max"])


def tbl_stat(st, key):
    """Statistic `key` of TBL_STATS from a dist summary."""
    if key in _QUANTILE:
        return figdraw.dist_q(st, _QUANTILE[key])
    if key == "iqr":
        return figdraw.dist_q(st, 0.75) - figdraw.dist_q(st, 0.25)
    return float(st[{"sd": "std", "min": "lo", "max": "hi"}.get(key, key)])


def parse_times(text, outputs_s):
    """The times of a Times box: minutes as "30, 60", ranges "30-120/15" (a step) and
    "30-120" (every output), each at the nearest of outputs_s (model s).  Returns (sorted
    times in s, the words that are not times)."""
    out, bad = set(), []
    tt = np.asarray(outputs_s, dtype=float)
    for tok in re.split(r"[,;\s]+", str(text or "").strip()):
        m = re.fullmatch(r"(\d*\.?\d+)(?:-(\d*\.?\d+)(?:/(\d*\.?\d+))?)?", tok)
        if not tok:
            continue
        if not m or not tt.size or (m[3] and float(m[3]) <= 0):
            bad.append(tok)
            continue
        a, b = float(m[1]) * 60.0, float(m[2] or m[1]) * 60.0
        if m[3]:
            wanted = np.arange(a, b + 1.0, float(m[3]) * 60.0)
        elif m[2]:
            wanted = tt[(tt >= a - 1.0) & (tt <= b + 1.0)]
        else:
            wanted = [a]
        out |= {float(tt[int(np.argmin(np.abs(tt - t)))]) for t in wanted}
    return sorted(out), bad


def times_text(times_s):
    """A Times box's text of times in s."""
    return ", ".join(f"{float(t) / 60:g}" for t in times_s)


def tbl_cells(spec, ent):
    """(run index, model time s in that run, minutes since its time zero) of each value of
    table entry `ent`."""
    for k in profile_runs(ent, len(spec.get("runs") or [])):
        for ts in ent.get("times_s") or []:
            one = dict(ent, time_s=float(ts))
            yield (k, float(entry_at(spec, one, k)["time_s"]),
                   round(float(since_t0(spec, one)["time_s"]) / 60.0, 2))


def _where_words(ent):
    return sounding_label(dict(ent, time_s=0.0), "", None, False).rsplit(" ", 2)[0]


def _columns(ent, F, many):
    """(key, name, units, source text, decimals or -1 for automatic) of each column of table
    entry `ent`; many: the panel has several sounding cards, so a sounding's say where."""
    if ent.get("what") == "sounding":
        src = ent.get("label") or (_where_words(ent) if many else "")
        info = {k: (n, u) for k, n, u in figdraw.SND_PARAMS}
        return [(k, *info[k], src, 1 if k in _ONE_DECIMAL else 0)
                for k in ent.get("params") or [] if k in info]
    r = ent["recipe"]
    d = F[r["field"]] if F is not None and r["field"] in F else None
    src = ent.get("label") or dist.describe(r, d.label if d else "")
    units = d.units if d else ""
    return [(k, TBL_STATS[k], "" if k == "n" else units, src, 0 if k == "n" else -1)
            for k in ent.get("stats") or [] if k in TBL_STATS]


def tbl_points(spec):
    """The height (pt) of the tallest table of `spec`, without reading its values: as many
    rows as figdraw's tbl_grid will lay out."""
    layout = (spec.get("table") or {}).get("layout") or "rows"
    size = figdraw.font_size(spec, "label")
    ents, nruns, out = spec.get("tables") or [], len(spec.get("runs") or []), 0.0
    for i in range(figdraw.npanels(spec)):
        mine = [x for x in ents if int(x.get("panel", 0)) == i]
        cells = {(k, float(ts)) for x in mine for k in profile_runs(x, nruns)
                 for ts in x.get("times_s") or []}
        nq = sum(len(x.get("params" if x.get("what") == "sounding" else "stats") or [])
                 for x in mine)
        runs, times = len({k for k, _ in cells}), len({ts for _, ts in cells})
        if layout == "rows":  # (heading: its source, a name, its units)
            many = sum(x.get("what") == "sounding" for x in mine) > 1
            spans = any(x.get("what") != "sounding" or x.get("label") or many for x in mine)
            head, rows = 2, len(cells) + bool(spans)
        else:
            head, rows = 1, nq * {"values": 1, "values_run": runs, "values_time": times}[layout]
        out = max(out, ((head + rows) * figdraw.TBL_LINE + (1 + rows) * figdraw.TBL_GAP) * size)
    return out


def tbl_panel(spec, i, get, fields=None):
    """Arrays of table panel i (figdraw.draw's notes).  get(entry index, run, model time s)
    -> a thermo result or dist summary, or a string (why there is none); fields(run index)
    -> its Fields (for the names and units of field statistics)."""
    ents = spec.get("tables") or []
    mine = [(e, x) for e, x in enumerate(ents) if int(x.get("panel", 0)) == i]
    many = sum(x.get("what") == "sounding" for _, x in mine) > 1
    runs = spec.get("runs") or []
    rows, cols, why = {}, [], ""
    for e, ent in mine:
        ks = profile_runs(ent, len(runs))
        for key, name, units, src, dec in _columns(ent, fields(ks[0]) if fields and ks else None,
                                                   many):
            vals = {}
            for k, ts, mins in tbl_cells(spec, ent):
                r = get(e, k, ts)
                rows.setdefault((k, mins), None)
                if isinstance(r, str) or r is None:
                    why = why or (r or "")
                    continue
                vals[k, mins] = _param(r, key) if ent.get("what") == "sounding" \
                    else tbl_stat(r, key)
            cols.append((e, name, units, src, dec, vals))
    if not cols:
        return dict(missing="no values picked for this table"
                    if mine else "no table in this panel")
    order = sorted(rows)
    out = dict(nq=len(cols), row_k=np.array([k for k, _ in order], dtype=int),
               row_min=np.array([m for _, m in order], dtype=float),
               row_run=np.array([str(runs[k].get("label") or f"Run {k + 1}")
                                 for k, _ in order], dtype=str))
    for j, (e, name, units, src, dec, vals) in enumerate(cols):
        out.update({f"Q{j}_e": e, f"Q{j}_name": name, f"Q{j}_units": units, f"Q{j}_src": src,
                    f"Q{j}_dec": dec,
                    f"Q{j}_v": np.array([vals.get(c, np.nan) for c in order], dtype=float)})
    if why and any(not np.all(np.isfinite(out[f"Q{j}_v"])) for j in range(len(cols))):
        out["why"] = why
    return out
