"""F7: the colour-vision / greyscale preview (shell/vision.py) works on the rendered picture only."""
import io

import numpy as np
from matplotlib import image as mimg

from cm1view.figures.shell import vision


def png_of(arr):
    buf = io.BytesIO()
    mimg.imsave(buf, np.asarray(arr, dtype=np.float32), format="png")
    return buf.getvalue()


def test_greys_and_whites_stay_put_in_every_mode():
    grey = np.array([[0.0, 0.0, 0.0], [0.5, 0.5, 0.5], [1.0, 1.0, 1.0]])
    for mode in ("grey", "protan", "deutan", "tritan"):
        np.testing.assert_allclose(vision.simulate_rgb(grey, mode), grey, atol=2e-3)


def test_unknown_mode_is_the_picture_itself():
    rgb = np.random.default_rng(0).random((4, 4, 3))
    assert vision.simulate_rgb(rgb, "") is rgb
    p = png_of(rgb)
    assert vision.simulate_png(p, "") is p


def test_greyscale_follows_luminance_and_has_equal_channels():
    out = vision.simulate_rgb(np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]), "grey")
    assert np.allclose(out[:, 0], out[:, 1]) and np.allclose(out[:, 1], out[:, 2])
    assert out[1, 0] > out[0, 0] > out[2, 0]  # (green lighter than red lighter than blue)


def test_red_and_green_become_close_for_protan_and_deutan():
    rg = np.array([[0.8, 0.2, 0.1], [0.2, 0.6, 0.1]])
    d0 = np.abs(rg[0] - rg[1]).sum()
    for mode in ("protan", "deutan"):
        o = vision.simulate_rgb(rg, mode)
        assert np.abs(o[0] - o[1]).sum() < d0


def test_png_keeps_size_and_alpha():
    a = np.zeros((5, 7, 4), dtype=np.float32)
    a[..., 0], a[..., 3] = 1.0, 0.5
    out = mimg.imread(io.BytesIO(vision.simulate_png(png_of(a), "deutan")), format="png")
    assert out.shape == (5, 7, 4) and np.allclose(out[..., 3], 0.5, atol=0.01)
