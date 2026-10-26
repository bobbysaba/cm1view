"""3D streamline tracing (core/volume3d.streamlines) on analytic winds: length, the
region's edge, "both" ways, stagnation points, steep (updraft) steps and the seed index;
and the 3D pane's restyle echo."""
from types import SimpleNamespace

import numpy as np
import pytest

from cm1view.core import volume3d

X1 = np.arange(0.25, 40.0, 0.5)  # km, dx = 500 m
Z = np.concatenate([np.arange(0.05, 1.0, 0.1), np.arange(1.2, 10.0, 0.4)])
RUN = SimpleNamespace(xh=X1, yh=X1, z=Z, dx=500.0, dy=500.0, nk=len(Z))
SH = (len(Z), len(X1), len(X1))
BOX = (5.0, 35.0, 5.0, 35.0)
XX = np.broadcast_to(X1[None, None, :], SH)
YY = np.broadcast_to(X1[None, :, None], SH)


def lines(st):
    for a, b, sd in st["segs"]:
        yield a, b, sd, np.stack([st["x"][a:b], st["y"][a:b], st["z"][a:b]], axis=1)


def arc(p):
    return float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)))


def zeros():
    return np.zeros(SH)


def test_uniform_flow_gives_straight_lines_of_the_asked_length():
    st = volume3d.streamlines(RUN, np.full(SH, 10.0), zeros(), zeros(), BOX, 8.0, 1.0,
                              n_seed=3, length=12.0)
    assert st["n"] == 9
    for a, b, sd, p in lines(st):
        assert sd == a  # forward: the seed starts the line
        assert np.ptp(p[:, 1]) < 1e-5 and np.ptp(p[:, 2]) < 1e-5
        # the column of seeds near the east edge stops on it, the rest run 12 km
        if p[0, 0] < 30.0:
            assert arc(p) == pytest.approx(12.0, abs=1e-4)
        else:
            assert p[-1, 0] == pytest.approx(35.0, abs=1e-4)


def test_lines_end_on_the_edge_of_the_region():
    st = volume3d.streamlines(RUN, np.full(SH, 10.0), np.full(SH, 4.0), zeros(), BOX, 8.0,
                              1.0, n_seed=4, length=200.0)
    for *_, p in lines(st):
        end = p[-1]
        assert end[0] == pytest.approx(35.0, abs=1e-4) or end[1] == pytest.approx(35.0, abs=1e-4)
        assert np.all((p[:, :2] >= 5.0 - 1e-5) & (p[:, :2] <= 35.0 + 1e-5))


def test_both_ways_share_the_length_and_mark_the_seed():
    st = volume3d.streamlines(RUN, np.full(SH, 10.0), zeros(), zeros(), BOX, 8.0, 1.0,
                              n_seed=3, length=12.0, direction="both")
    for a, b, sd, p in lines(st):
        assert a < sd < b - 1 or p[0, 0] == pytest.approx(5.0, abs=1e-4)
        assert arc(p) <= 12.0 + 1e-4
        assert np.all(np.diff(p[:, 0]) > 0)  # upstream half first, then downstream
        if 11.0 < p[sd - a, 0] < 29.0:  # room for 6 km each way
            assert arc(p) == pytest.approx(12.0, abs=1e-4)
            assert arc(p[: sd - a + 1]) == pytest.approx(6.0, abs=1e-4)


def test_solid_rotation_keeps_its_radius():
    st = volume3d.streamlines(RUN, -(YY - 20.0), XX - 20.0, zeros(), BOX, 8.0, 1.0,
                              n_seed=5, length=30.0)
    for *_, p in lines(st):
        r = np.hypot(p[:, 0] - 20.0, p[:, 1] - 20.0)
        assert np.ptp(r) < 0.01 * r.mean()


def test_lines_stop_at_a_stagnation_point_without_zigzag():
    st = volume3d.streamlines(RUN, -(XX - 20.0), zeros(), zeros(), BOX, 8.0, 1.0,
                              n_seed=4, length=50.0)
    for *_, p in lines(st):
        towards = np.sign(20.0 - p[0, 0])
        assert np.all(np.diff(p[:, 0]) * towards >= -1e-6)
        assert abs(p[-1, 0] - 20.0) < 0.5


def test_steep_steps_climb_at_most_most_of_a_level():
    st = volume3d.streamlines(RUN, np.full(SH, 2.0), zeros(), np.full(SH, 20.0), BOX, 8.0,
                              0.05, n_seed=3, length=10.0)
    for *_, p in lines(st):
        dz = np.diff(p[:, 2])
        dzl = np.interp(p[:-1, 2], Z, np.gradient(Z))
        assert np.all(dz <= 0.8 * dzl + 1e-5)
        assert p[-1, 2] == pytest.approx(8.0, abs=1e-4)  # stopped on the scene's top


def test_the_3d_pane_ignores_a_late_restyle_echo():
    """The browser echoes each restyle back; a late echo of an older cursor push must not
    rewind the figure (or be sent again), while a legend click's show/hide still counts."""
    import plotly.graph_objects as go

    from cm1view.viewer.ui import Plotly3D
    fig = go.Figure([go.Scatter3d(x=[1.0], y=[1.0], z=[1.0])])
    pane, sent = Plotly3D(fig), []
    pane._models = {"ref": (SimpleNamespace(), None)}
    pane._apply_update = lambda ev, msg, m, ref: sent.append(msg)
    fig.data[0].update(x=[3.0])
    sent.clear()
    pane.restyle_data = [{"x": [[2.0]]}, [0]]
    assert fig.data[0].x == (3.0,) and not sent
    pane.restyle_data = [{"visible": ["legendonly"]}, [0]]
    assert fig.data[0].visible == "legendonly" and not sent
