"""The cross-sections of a figure: spec["sections"], a list of named sections that each
section panel picks from (its panel edit "section", else its row's or column's in a
grid of sections, else the first).

A section is {label ("": automatic), orient, pos, avg (width averaged across, km)}
plus the keys of its orientation:
  orient "x" (an x–z section): through the storm half, off (in y); fixed y (blank:
         the domain's centre), x0, x1 (blank: the domain's edges)
  orient "y" (y–z): through the storm half, off (in x); fixed x, y0, y1
  orient "angle": angle (degrees clockwise from north: the way the section runs),
         half; through the storm offset [dx, dy]; fixed cx, cy (blank: the centre)
  orient "along" / "across" (the storm's motion: behind -> ahead / left -> right):
         half, ahead, right (the centre's offset from the storm, km), mwin (the motion
         averaged over mwin minutes about the time; 0: the motion at the time)
  orient "ab": a, b (grid km; "Use map A–B")
pos "storm" (centred on the run's tracked storm) or "fixed"; "ab" sections are fixed,
"along" and "across" ones always through the storm.  The motion is the ground-relative
tracked motion (the domain's where the track has none; north when that is nil).
The height range (ztop, dz) and the x axis of x–z and y–z sections (coords "storm":
x or y from the storm's, for those through the storm; "grid": the model's x or y)
stay figure-wide in spec["xsec"]; angled and A–B sections are drawn against the
distance along them (0 at the storm, or at A)."""

import numpy as np

from ...core import azim, track as trk
from .. import draw as figdraw

ORIENTS = {"x–z (along x)": "x", "y–z (along y)": "y", "Angled": "angle",
           "Along the storm motion": "along", "Across the storm motion": "across",
           "A–B points": "ab"}
MOTION = ("along", "across")
POSITIONS = {"Through the storm": "storm", "Fixed": "fixed"}
SEC_DEFAULTS = dict(label="", orient="x", pos="storm", half=10.0, off=0.0, y=None,
                    x0=None, x1=None, x=None, y0=None, y1=None, angle=90.0,
                    offset=[0.0, 0.0], cx=None, cy=None, ahead=0.0, right=0.0, mwin=0.0, a=None,
                    b=None, avg=0.0)
XSEC_DEFAULTS = dict(ztop=6.0, dz=0.025, coords="storm")


def section_defaults(**kw):
    """A section entry: SEC_DEFAULTS with kw."""
    return dict(SEC_DEFAULTS, **kw)


def from_xsec(xs):
    """The section of an older spec's one spec["xsec"] (mode storm: angle counter-
    clockwise from east, half, offset [dx, dy]; mode fixed: a, b)."""
    xs = xs or {}
    avg = float(xs.get("avg") or 0.0)
    if xs.get("mode", "storm") == "fixed":
        return section_defaults(orient="ab", pos="fixed", a=xs.get("a"), b=xs.get("b"),
                                avg=avg)
    th = float(xs.get("angle", 0.0)) % 360.0
    ox, oy = (float(v) for v in xs.get("offset") or (0.0, 0.0))
    half = float(xs.get("half", 10.0))
    if th == 0.0 and ox == 0.0:
        return section_defaults(orient="x", half=half, off=oy, avg=avg)
    if th == 90.0 and oy == 0.0:
        return section_defaults(orient="y", half=half, off=ox, avg=avg)
    return section_defaults(orient="angle", angle=(90.0 - th) % 360.0, half=half,
                            offset=[ox, oy], avg=avg)


def sections(spec):
    """The figure's sections (an older spec's spec["xsec"] as the only one)."""
    secs = spec.get("sections") or [from_xsec(spec.get("xsec"))]
    return [section_defaults(**s) for s in secs]


def upgrade_sections(spec):
    """spec (and its parts) with spec["sections"], and spec["xsec"] only the height
    range; in place."""
    for s in [spec] + list(spec.get("parts") or []):
        if "xsec" not in s and "sections" not in s:
            continue
        s["sections"] = sections(s)
        xs = s.get("xsec") or {}
        s["xsec"] = {k: xs.get(k, v) for k, v in XSEC_DEFAULTS.items()}
    return spec


def panel_section(spec, i):
    """(index, section) of panel i: its panel edit's "section", else its row's or
    column's (a grid of sections), else the first."""
    secs = sections(spec)
    k = figdraw.panel_edit(spec, i).get("section")
    if k is None:
        k = (figdraw.grid_cell(spec, i) or {}).get("section")
    k = int(k) if k is not None and 0 <= int(k) < len(secs) else 0
    return k, secs[k]


def is_storm(sec):
    """Whether the section follows the tracked storm."""
    o = sec.get("orient")
    return o in MOTION or (o != "ab" and sec.get("pos", "storm") == "storm")


def uses_motion(sec):
    """Whether the section turns with the storm's motion."""
    return sec.get("orient") in MOTION


def section_motion(run, fixes, t, sec):
    """Ground-relative storm motion (u, v) m/s that section `sec` follows at output t:
    the tracked motion at t, or with mwin > 0 the mean over the fixes within mwin / 2
    minutes of it; the domain motion where the track has none."""
    mot = {k: m for k, m in (trk.motion(run, fixes).items() if fixes else ())
           if np.all(np.isfinite(m))}
    half = 30.0 * float(sec.get("mwin") or 0.0)
    if half > 0 and t is not None:
        near = [m for k, m in mot.items() if abs(run.times[k] - run.times[t]) <= half + 1e-6]
        if near:
            return tuple(float(v) for v in np.mean(near, axis=0))
    if t in mot:
        return tuple(mot[t])
    return (run.umove, run.vmove)


def domain_box(run):
    """(x0, x1, y0, y1) grid km of the whole domain."""
    dxk, dyk = run.dx / 2000.0, run.dy / 2000.0
    return run.xh[0] - dxk, run.xh[-1] + dxk, run.yh[0] - dyk, run.yh[-1] + dyk


def _or(v, default):
    return float(default) if v is None else float(v)


def section_ends(run, sec, center, motion=None):
    """Grid-km ends (A, B) of section `sec` (center: the tracked storm (x, y) km at
    the time, or None; motion: the storm motion (u, v) it follows, section_motion,
    for along / across ones), or None (no track position, or no A–B yet)."""
    o = sec.get("orient", "x")
    if o == "ab":
        if not sec.get("a") or not sec.get("b"):
            return None
        return tuple(sec["a"]), tuple(sec["b"])
    storm = is_storm(sec)
    if storm and center is None:
        return None
    x0, x1, y0, y1 = domain_box(run)
    half = float(sec.get("half") or 10.0)
    if o in MOTION:
        ph = np.radians(azim.bearing(*(motion or (run.umove, run.vmove))))
        ahead, right = np.array([np.sin(ph), np.cos(ph)]), np.array([np.cos(ph), -np.sin(ph)])
        c = (np.asarray(center, float) + float(sec.get("ahead") or 0.0) * ahead
             + float(sec.get("right") or 0.0) * right)
        d = half * (ahead if o == "along" else right)
        return tuple(map(float, c - d)), tuple(map(float, c + d))
    if o == "x":
        if storm:
            y = center[1] + float(sec.get("off") or 0.0)
            return (center[0] - half, y), (center[0] + half, y)
        y = _or(sec.get("y"), 0.5 * (y0 + y1))
        xa, xb = sorted((_or(sec.get("x0"), x0), _or(sec.get("x1"), x1)))
        return (xa, y), (xb, y)  # (towards larger x: the x axis)
    if o == "y":
        if storm:
            x = center[0] + float(sec.get("off") or 0.0)
            return (x, center[1] - half), (x, center[1] + half)
        x = _or(sec.get("x"), 0.5 * (x0 + x1))
        ya, yb = sorted((_or(sec.get("y0"), y0), _or(sec.get("y1"), y1)))
        return (x, ya), (x, yb)
    if storm:
        off = sec.get("offset") or (0.0, 0.0)
        cx, cy = center[0] + float(off[0]), center[1] + float(off[1])
    else:
        cx, cy = _or(sec.get("cx"), 0.5 * (x0 + x1)), _or(sec.get("cy"), 0.5 * (y0 + y1))
    ph = np.radians(float(sec.get("angle", 90.0)))  # (0: south -> north, 90: west -> east)
    dx, dy = np.sin(ph) * half, np.cos(ph) * half
    return (cx - dx, cy - dy), (cx + dx, cy + dy)


def x_axis(sec, coords="storm", center=None):
    """(axis, origin, name) of a section panel's x axis: axis 0 (grid x), 1 (grid y)
    or None (the distance along the section); origin the grid km at 0 (x, y: the
    storm's for a section through the storm with coords "storm", else 0; distance:
    None) and name its automatic label."""
    o, st = sec.get("orient", "x"), is_storm(sec) and center is not None
    if o in ("x", "y"):
        k = 0 if o == "x" else 1
        rel = st and coords == "storm"
        return k, float(center[k]) if rel else 0.0, f"{o} from storm (km)" if rel else f"{o} (km)"
    return None, None, "distance from storm (km)" if st else "distance (km)"


def describe(sec):
    """A short description of section `sec` (for its card)."""
    o, st = sec.get("orient", "x"), is_storm(sec)

    def km(v, what):
        return what if v is None else f"{float(v):g} km"
    if o in MOTION:
        off = [f"{float(sec.get(k) or 0.0):+g} km {k}" for k in ("ahead", "right")
               if float(sec.get(k) or 0.0)]
        mw = float(sec.get("mwin") or 0.0)
        return (f"{o} the storm motion" + (f" ({mw:g}-min mean)" if mw else "")
                + "".join(", " + x for x in off))
    if o == "ab":
        return ("A ({:g}, {:g}) → B ({:g}, {:g}) km".format(*sec["a"], *sec["b"])
                if sec.get("a") and sec.get("b") else "A–B: not chosen yet")
    if o in ("x", "y"):
        name = "x–z" if o == "x" else "y–z"
        if st:
            off = float(sec.get("off") or 0.0)
            return f"{name} through the storm" + (f", {off:+g} km in {'y' if o == 'x' else 'x'}"
                                                   if off else "")
        at = sec.get("y" if o == "x" else "x")
        return f"{name} at {'y' if o == 'x' else 'x'} = {km(at, 'the centre')}"
    where = "through the storm" if st else "fixed"
    return f"angled {float(sec.get('angle', 90.0)):g}° from north, {where}"
