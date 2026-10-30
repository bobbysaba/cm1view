"""Figure editor pieces: choices and constants, small widget helpers (base), and the
cards for layers (layercard), series and soundings (seriescard), distributions and
annotations (distcard), profiles (profcard), joint distributions (jointcard),
azimuthal means (azimcard), cross-sections (seccard), series of your own data
(datacard) and a 3D scene's isosurfaces and vectors (scenecard)."""

from . import (base, layercard, seriescard, distcard, profcard, jointcard, azimcard, seccard,
               datacard, scenecard)

# (each uses only base, but jointcard: distcard's and profcard's choices too; azimcard:
# profcard's; seccard: spec.sections; datacard: seriescard's line styles)
MODULES = (base, layercard, seriescard, distcard, profcard, jointcard, azimcard, seccard,
           datacard, scenecard)
for _m in MODULES:  # one namespace: cards.<name> for any of them
    globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
