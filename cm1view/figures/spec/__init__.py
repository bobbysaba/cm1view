"""Publication figures: the figure spec, the data behind each panel, and export.

The spec (a JSON-able dict) says what each panel shows and how it looks; figdraw.draw
turns it plus the panel arrays into a matplotlib figure.  Panels vary in time (one
field setup at several times) or in field (several fills at one time), as plan views
at fixed heights or vertical cross-sections, over the whole domain, a fixed box, or a
window centred on the tracked storm.  Other kinds of panels: time-height plots and
time series of reduced fields (the Series tab's recipes, spec["series"]), soundings
(skew-T + hodograph, spec["soundings"]), and distributions of a field over a region at
one time (histogram, box, violin or cumulative, spec["dists"]), vertical profiles
of a field reduced over a region at each level (spec["profiles"]), joint
distributions of two fields at the same points (spec["joints"]), and azimuthal means
of a field in radius and height around the storm or a point (spec["azims"]).  Panels can come from
different runs (e.g. tornadic vs non-tornadic): spec["runs"] lists the runs with a
label and a storm track each, and panels refer to them by index, with times in model
seconds so they match across runs.  Section panels pick one of the figure's
cross-sections (spec["sections"]).

Exporting writes the image and, optionally, a stand-alone script (figdraw's code +
the spec as a Python dict), the plotted arrays (.npz) and the spec (.json), so the
figure can be redrawn or restyled later without the viewer.
"""

from . import sections, base, arrays, panels, bundle, templates

MODULES = (sections, base, arrays, panels, bundle, templates)  # (each uses only those before it)
for _m in MODULES:  # one namespace: fg.<name> for any of them
    globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
