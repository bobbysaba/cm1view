"""Vector quantities drawn as arrows or streamlines: the wind, and other horizontal
vectors built from two fields (horizontal vorticity, baroclinic generation).  The map,
the 3D scene, the cross-section and the figures all pick from VECTORS."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VectorDef:
    key: str
    label: str
    units: str
    comps: tuple   # field names of the x, y and vertical components (None: zero)
    ref: float     # a typical magnitude: the default reference arrow
    framed: bool = False  # the wind: ground-, grid- or storm-relative


# (a new one: its key arrow units in figures/draw/layers.py KEY_UNITS too)
VECTORS = {d.key: d for d in (
    VectorDef("wind", "Wind", "m/s", ("uinterp", "vinterp", "winterp"), 20.0, framed=True),
    VectorDef("hvort", "Horizontal vorticity", "1/s", ("xvort", "yvort", "zvort"), 0.02),
    VectorDef("bgen", "Baroclinic generation", "10⁻⁴ s⁻²", ("bgen_x", "bgen_y", None), 1.0),
)}

FRAME_SHORT = {"ground": "ground-rel", "grid": "grid-rel", "storm": "storm-rel"}

# matplotlib quiver scale (data units per axes width) for a figure layer
FIG_SCALE = 12.5  # × ref: 250 for the wind


def options(F):
    """{label: key} of the vectors this run has the fields for."""
    return {d.label: k for k, d in VECTORS.items() if all(c in F for c in d.comps[:2])}


def to_frame(run, u, v, frame, storm):
    """Grid-relative winds -> the frame: 'ground', 'grid' or 'storm' (storm motion
    ground-relative m/s; None: the domain motion)."""
    if frame == "ground":
        return u + run.umove, v + run.vmove
    if frame == "storm":
        su, sv = storm if storm is not None else (run.umove, run.vmove)
        return u + run.umove - su, v + run.vmove - sv
    return u, v


def plane(F, key, t, mode, level, frame="grid", storm=None):
    """(u, v) planes of vector `key` (frame and storm: for the wind)."""
    d = VECTORS[key]
    u = F.plane(d.comps[0], t, mode, level)
    v = F.plane(d.comps[1], t, mode, level)
    return to_frame(F.run, u, v, frame, storm) if d.framed else (u, v)


def volumes(F, key, t):
    """(u, v, w) volumes of vector `key`, grid-relative (w None when it has none)."""
    d = VECTORS[key]
    return tuple(F.volume(c, t) if c else None for c in d.comps)


def deps(F, key):
    """The native fields vector `key` is computed from."""
    return [n for c in VECTORS[key].comps if c for n in F.native_deps(c)]


def label(key, frame=None):
    """'Wind (storm-rel)' / 'Horizontal vorticity'."""
    d = VECTORS[key]
    return f"{d.label} ({FRAME_SHORT[frame]})" if d.framed and frame else d.label
