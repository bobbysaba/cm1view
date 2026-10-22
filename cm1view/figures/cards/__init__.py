"""Figure editor pieces: choices and constants, small widget helpers (base), and the
cards for layers (layercard), series and soundings (seriescard), and distributions
and annotations (distcard)."""

from . import base, layercard, seriescard, distcard

MODULES = (base, layercard, seriescard, distcard)  # (each uses only base)
for _m in MODULES:  # one namespace: cards.<name> for any of them
    globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
