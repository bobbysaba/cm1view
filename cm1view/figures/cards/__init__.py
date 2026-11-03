"""Figure editor pieces: choices and constants, small widget helpers (base), and the
cards for layers (layercard), series and soundings (seriescard), distributions and
annotations (distcard), profiles (profcard), joint distributions (jointcard),
azimuthal means (azimcard), tables (tblcard), cross-sections (seccard), series of your own
data (datacard), parcel series (parcelseries) and a 3D scene's isosurfaces and vectors
(scenecard)."""

from . import (base, layercard, seriescard, distcard, profcard, jointcard, azimcard, tblcard,
               seccard, datacard, parcelseries, scenecard)

# (each uses only base, but profcard: seriescard's run lists too; jointcard: distcard's
# choices; tblcard: both; seccard: spec.sections; parcelseries: layercard's parcel sets)
MODULES = (base, layercard, seriescard, distcard, profcard, jointcard, azimcard, tblcard,
           seccard, datacard, parcelseries, scenecard)
for _m in MODULES:  # one namespace: cards.<name> for any of them
    globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
