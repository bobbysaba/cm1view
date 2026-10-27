"""Draw a figure from a spec (a dict) and the plotted arrays: plan views, vertical
cross-sections, time-height plots, time series, soundings, distributions, vertical
profiles, joint distributions or azimuthal means on a grid of panels.

Needs only numpy and matplotlib (cmweather or pyart, if installed, for their colormaps).  cm1view
saves this package's code (source(): its modules in MODULES order) with every exported
figure script (_src/<name>_draw.py), so the script redraws exactly what the viewer showed;
edit SPEC or my_changes() in the script (or this code) to change the figure.  The modules
import each other's names only with "from .<module> import ..." lines, which source()
leaves out.

data: {panel index: {name: array}} with, per panel,
  x, y          1D coordinates (km): plan x / y, or section distance / height
  L<j>          2D field of layer j (fill, contour, shade)
  L<j>_x, L<j>_y, L<j>_u, L<j>_v   vectors of layer j
  L<j>_gx, L<j>_gy, L<j>_gu, L<j>_gv   grid and winds of a streamline layer j
  track_x, track_y, now_x, now_y   storm track (plan views)
  line          [xa, ya, xb, yb] cross-section line (plan views)
  sector        [x, y, bearing] centre of a Sector layer (track centres; nan: none) and
                the storm motion's direction (deg clockwise from north) (plan views)
  time_s        model time (s)
  run           index of the panel's run in spec["runs"] (its colour: tracks, run names)
  run_label     name of the panel's run (figures with panels from several runs)
  missing       reason the panel has no data (a string), if any
time-height panels (kind "th"): x = time (min), y = height (km), L0 = values (z, t)
time-series panels (kind "line"): nlines, and per line n
  S<n>_t, S<n>_v   time (min) and values;  S<n>_e, S<n>_r  series entry and run index
  S<n>_label       legend text
  S<n>_ens         (an ensemble of the series' runs) number of members; S<n>_v its
                   centre, S<n>_lo, S<n>_hi its band; S<n>_r -1
  S<n>_mem         (1) a member of an ensemble
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
profile panels (kind "profile"): nprof, and per profile n (a field reduced over a
  region at every model level of a layer, at one time or averaged over a time window;
  spec["prof"]: the axes' ranges, zero line and legend)
  P<n>_z, P<n>_v   height (km) and values;  P<n>_e, P<n>_r  profile entry and run index
  P<n>_label, P<n>_xl                      legend text and value axis label
joint distribution panels (kind "joint"): njoint, and per joint distribution n (a
  summary of the pairs of values of two fields at the same points over a region, at
  one time or over a time window; spec["joint"]: how they are drawn, a 2D histogram
  (counts, PDF or fractions), scatter or density contours)
  J<n>_s   [count, x mean, y mean, x sd, y sd, Pearson r, x min, x max, y min, y max]
  J<n>_h   counts of a fine 2D histogram (x along the first axis), minima to maxima
  J<n>_p   [x, y] of a random pick of the pairs (scatter plots)
  J<n>_e, J<n>_r, J<n>_label   joint entry and run index, legend text
  J<n>_xl, J<n>_yl             x and y axis labels
azimuthal mean panels (kind "azim"): nazim, and per azimuthal mean n (a field reduced
  in radius bins at every level of a layer within a sector around the storm or a
  point, at one time or a composite over a time window; spec["azim"]: how the first
  is shaded, the others are contour lines)
  A<n>_x, A<n>_z, A<n>_v   radius bin centres, heights (km) and values (heights x radii)
  A<n>_e, A<n>_r, A<n>_label   azimuthal mean entry and run index, legend text
  A<n>_cl, A<n>_cm, A<n>_div   colorbar label, the field's colormap, diverging (0 / 1)
figures of parts (kind "combo"): part k's panel i under k * 1000 + i

Specs of version 2 (upgrade() makes one of a version-1 spec or a figure of parts):
  the figure's own settings (size, fonts, colorbar, labels, axes, skewt, ts, ...),
  blocks   [{rows, cols, share, size, opts}]: grids of panels side by side (arrange
           "row") or stacked ("col"); opts: settings of the block's own
  panels   [{id, block, cell [row, col, rowspan, colspan], kind (plan, xsec, th, line,
           sounding, dist, profile, joint, azim), run, time_s, z, zmode, title, letter, opts,
           colorbar {show},
           layers}]: data[id] is the panel's data; opts: settings of the panel's own
  layers   a plan or section panel's map layers (as version 1), a time-height panel's
           series ("series"), a time-series panel's lines ("series"), a sounding
           panel's soundings ("sounding"), a distribution panel's distributions
           ("dist"), a profile panel's profiles ("profile"), a joint distribution
           panel's joint distributions ("joint") or an azimuthal mean panel's
           azimuthal means ("azim"); S<n>_e, N<n>_e, D<n>_e, P<n>_e, J<n>_e and A<n>_e
           count within the panel.
           A layer's run, time_s and z: None (or missing) for the panel's
           (resolved()); L<j>_cx, L<j>_cy: the layer's own coordinates (another run's)
           L<j>_ens: a fill layer's number of ensemble members (its "ens")
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
