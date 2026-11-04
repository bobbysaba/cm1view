"""Colour-vision and greyscale preview of the picture the shell shows.  It works on the rendered
PNG only, so the figure, the document, undo and every export are untouched.

Colour-vision deficiencies: Machado, Oliveira and Fernandes (2009), "A Physiologically-based Model
for Simulation of Color Vision Deficiency", IEEE Trans. Visualization and Computer Graphics 15(6),
the 3x3 matrices for severity 1.0 (complete loss of the L, M or S cones), applied to linear RGB (the
sRGB picture decoded first, encoded again after).  Greyscale: relative luminance of linear sRGB
(Rec. 709 weights, Y = 0.2126 R + 0.7152 G + 0.0722 B), encoded again, which is how a black-and-white
print or a grey conversion shows lightness.  Only numpy and matplotlib (for the PNG) are used."""

import io

import numpy as np

MODES = {"Normal": "", "Greyscale": "grey", "Protanopia (no red cones)": "protan",
         "Deuteranopia (no green cones)": "deutan", "Tritanopia (no blue cones)": "tritan"}

MACHADO = {  # (severity 1.0: Machado et al. 2009, table 1)
    "protan": [[0.152286, 1.052583, -0.204868],
               [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968],
               [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779],
               [-0.078411, 0.930809, 0.147602],
               [0.004733, 0.691367, 0.303900]]}
LUMA = [0.2126, 0.7152, 0.0722]


def _linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _encode(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def simulate_rgb(rgb, mode):
    """float array (..., 3) of sRGB 0..1 as seen in `mode` ("grey", "protan", "deutan", "tritan";
    "" or unknown: unchanged)."""
    if mode not in MACHADO and mode != "grey":
        return rgb
    lin = _linear(np.asarray(rgb, dtype=np.float64))
    if mode == "grey":
        y = lin @ np.array(LUMA)
        out = np.repeat(y[..., None], 3, axis=-1)
    else:
        out = lin @ np.array(MACHADO[mode]).T
    return _encode(out)


def simulate_png(png, mode):
    """The PNG bytes `png` as seen in `mode` (alpha kept); the bytes themselves for "Normal"."""
    if mode not in MACHADO and mode != "grey":
        return png
    from matplotlib import image as mimg
    a = mimg.imread(io.BytesIO(png), format="png")
    if a.ndim == 2:
        a = np.repeat(a[..., None], 3, axis=-1)
    out = np.concatenate([simulate_rgb(a[..., :3], mode), a[..., 3:]], axis=-1)
    buf = io.BytesIO()
    mimg.imsave(buf, np.clip(out, 0.0, 1.0).astype(np.float32), format="png")
    return buf.getvalue()
