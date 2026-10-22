"""Draw a figure from a spec (a dict) and the plotted arrays: plan views, vertical
cross-sections, time-height plots, time series, soundings or distributions on a grid
of panels.

Needs only numpy and matplotlib (cmweather or pyart, if installed, for their colormaps).  cm1view
copies this package's code (source(): its modules in MODULES order) into every exported
figure script, so the script redraws exactly what the viewer showed; edit SPEC in the
script (or this code) to change the figure.  The modules import each other's names only
with "from .<module> import ..." lines, which source() leaves out.

data: {panel index: {name: array}} with, per panel,
  x, y          1D coordinates (km): plan x / y, or section distance / height
  L<j>          2D field of layer j (fill, contour, shade)
  L<j>_x, L<j>_y, L<j>_u, L<j>_v   vectors of layer j
  L<j>_gx, L<j>_gy, L<j>_gu, L<j>_gv   grid and winds of a streamline layer j
  track_x, track_y, now_x, now_y   storm track (plan views)
  line          [xa, ya, xb, yb] cross-section line (plan views)
  time_s        model time (s)
  run           index of the panel's run in spec["runs"] (its colour: tracks, run names)
  run_label     name of the panel's run (figures with panels from several runs)
  missing       reason the panel has no data (a string), if any
time-height panels (kind "th"): x = time (min), y = height (km), L0 = values (z, t)
time-series panels (kind "line"): nlines, and per line n
  S<n>_t, S<n>_v   time (min) and values;  S<n>_e, S<n>_r  series entry and run index
  S<n>_label       legend text
sounding panels (kind "sounding"): nsnd, and per sounding n
  N<n>_p, N<n>_T, N<n>_Td, N<n>_Tp   pressure (hPa), T, dewpoint, lifted parcel (deg C)
  N<n>_u, N<n>_v, N<n>_z             winds (m/s) and height (km AGL)
  N<n>_e, N<n>_label                 sounding entry index and legend text
  N<n>_rm, N<n>_lm, N<n>_mean        Bunkers right / left mover and 0-6 km mean wind
                                     (u, v m/s), N<n>_storm the storm motion of the SRH
                                     (spec["skewt"]["storm"]: rm, lm, mean or custom)
  N<n>_srh1, N<n>_srh3               0-1 and 0-3 km storm-relative helicity (m2/s2)
  N<n>_par                           the SND_PARAMS values (spec["skewt"]["table"]: a
                                     table of the chosen ones under the panel)
  spec["skewt"]["layout"]: "inset" (skew-T with a hodograph inset), "side" (skew-T and
  hodograph side by side), "skewt" (no hodograph) or "hodo" (the hodograph alone)
distribution panels (kind "dist"): ndist, and per distribution n (a summary of all
  the values of a field over a region at one time; spec["dist"]: how they are drawn,
  hist (counts, PDF or fractions), box, violin or ecdf)
  D<n>_s       [count, mean, std, min, max, lower and upper Tukey whisker]
  D<n>_q       quantiles at DIST_PROBS;  D<n>_h  counts of a fine histogram, min to max
  D<n>_e, D<n>_label, D<n>_xl   distribution entry index, legend text, value axis label
figures of parts (kind "combo"): part k's panel i under k * 1000 + i

Specs of version 2 (upgrade() makes one of a version-1 spec or a figure of parts):
  the figure's own settings (size, fonts, colorbar, labels, axes, skewt, ts, ...),
  blocks   [{rows, cols, share, size, opts}]: grids of panels side by side (arrange
           "row") or stacked ("col"); opts: settings of the block's own
  panels   [{id, block, cell [row, col, rowspan, colspan], kind (plan, xsec, th, line,
           sounding, dist), run, time_s, z, zmode, title, letter, opts, colorbar {show},
           layers}]: data[id] is the panel's data; opts: settings of the panel's own
  layers   a plan or section panel's map layers (as version 1), a time-height panel's
           series ("series"), a time-series panel's lines ("series"), a sounding
           panel's soundings ("sounding") or a distribution panel's distributions
           ("dist"); S<n>_e, N<n>_e and D<n>_e count within the panel.
           A layer's run, time_s and z: None (or missing) for the panel's
           (resolved()); L<j>_cx, L<j>_cy: the layer's own coordinates (another run's)
  Colorbar ends (a fill's "extend"): neither, min, max, both, or auto (from the data:
  where it passes vmin / vmax); panels sharing a colorbar share the ends of all of
  them.
"""

from . import base, v2, layers, lines, sounding, figure

MODULES = (base, v2, layers, lines, sounding, figure)  # (each uses only those before it)
for _m in MODULES:  # one namespace, as in an exported script
    globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})


def source():
    """The drawing code as one module, for exported scripts: the modules' imports
    merged (without those between them), then their code in MODULES order."""
    import ast
    import inspect
    plain, froms, code = [], {}, []
    for m in MODULES:
        text = inspect.getsource(m)
        end = 0
        for node in ast.parse(text).body:
            if isinstance(node, ast.Import):
                plain += [ast.unparse(ast.Import([a])) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if not node.level:
                    froms.setdefault(node.module, []).extend(
                        a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
            elif not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
                break
            end = node.end_lineno
        code.append("\n".join(text.splitlines()[end:]).strip("\n"))
    head = list(dict.fromkeys(plain))
    for mod, names in froms.items():
        line = f"from {mod} import "
        for k, name in enumerate(dict.fromkeys(names)):
            if k and len(line) + len(name) > 88:
                head.append(line.rstrip() + " \\")
                line = "    "
            line += name + ", "
        head.append(line[:-2])
    return "\n".join(head) + "\n\n\n" + "\n\n\n".join(code) + "\n"
