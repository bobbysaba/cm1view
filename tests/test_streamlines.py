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
    # (what the pane would send the browser; Panel skips what comes from the browser)
    pane._send_update_msg = lambda data, layout, traces=None, source=None: \
        None if source else sent.append(data)
    fig.data[0].update(x=[3.0])
    sent.clear()
    pane.restyle_data = [{"x": [[2.0]]}, [0]]
    assert fig.data[0].x == (3.0,) and not sent
    pane.restyle_data = [{"visible": ["legendonly"]}, [0]]
    assert fig.data[0].visible == "legendonly" and not sent


class _Run(SimpleNamespace):
    """RUN with what build_scene needs: volumes kept in a dict, loading counted."""

    def ij(self, x, y):
        return (int(np.clip(np.rint((x - X1[0]) * 2), 0, len(X1) - 1)),
                int(np.clip(np.rint((y - X1[0]) * 2), 0, len(X1) - 1)))

    def load_volumes(self, names, t, progress=None, cancelled=None):
        self.loaded = list(names)
        return not (cancelled and cancelled())

    def volume(self, name, t):
        return self.vols[name]


class _Fields:
    def __init__(self, run, vols):
        self.run, self.vols = run, vols

    def __contains__(self, name):
        return name in self.vols

    def __getitem__(self, name):
        return SimpleNamespace(label=name, units="K", title=name, storm=False, ndim=3,
                               cmap="viridis", vrange=None, diverging=False)

    def native_deps(self, name):
        return [name]

    def volume(self, name, t, storm=None):
        return self.vols[name]

    def plane(self, name, t, mode, level, storm=None):
        return self.vols[name][int(np.searchsorted(Z, level))]


def _scene(**kw):
    sc = dict(t=0.0, box=BOX, ztop=8.0, exag=1.0, smooth=0.0, res=1,
              isos=[dict(var="blob", val=0.5, color="#ff0000", op=0.6)],
              vecs=[], storm=(0.0, 0.0), fstorm=(None, ""),
              stream=dict(on=True, z=1.0, n=3, length=12.0, dir="forward", frame="grid",
                          color_by="w", seed_box=None),
              ground=dict(on=True, var="blob", z=0.0, cmap="Field default", rev=False,
                          range="data", lo=0.0, hi=0.0))
    sc.update(kw)
    return sc


def test_build_scene_gives_arrays_and_reuses_the_streamlines():
    zz = np.broadcast_to(Z[:, None, None], SH)
    blob = np.exp(-((XX - 20) ** 2 + (YY - 20) ** 2 + (zz - 3) ** 2) / 20.0)
    vols = dict(blob=blob, uinterp=np.full(SH, 10.0), vinterp=zeros(), winterp=zeros())
    run = _Run(xh=X1, yh=X1, z=Z, dx=500.0, dy=500.0, nk=len(Z), umove=0.0, vmove=0.0,
               vols=vols)
    F = _Fields(run, vols)
    cache = {}
    sc = volume3d.build_scene(run, F, _scene(), cache=cache)
    assert set(run.loaded) == {"blob", "uinterp", "vinterp", "winterp"}
    (m,) = sc["meshes"]
    assert len(m["faces"]) and m["color"] == "#ff0000" and m["opacity"] == 0.6
    assert sc["ground"]["cmap"] == "viridis" and sc["ground"]["a"].ndim == 2
    assert sc["stream"]["n"] == 9 and sc["stream"]["color_by"] == "w"
    assert sc["stride"] == 1 and sc["off"] == (0.0, 0.0)
    # an isosurface edit: the same lines from the cache (a copy each time)
    first = cache["stream"]
    sc2 = volume3d.build_scene(run, F, _scene(isos=[]), cache=cache)
    assert cache["stream"] is first and sc2["stream"] is not first
    assert not sc2["meshes"]
    # a value outside the field: a note, no mesh; cancelled: None
    sc3 = volume3d.build_scene(run, F, _scene(
        isos=[dict(var="blob", val=5.0, color="#fff", op=1.0)]))
    assert not sc3["meshes"] and "no surface" in sc3["notes"][0]
    assert volume3d.build_scene(run, F, _scene(), cancelled=lambda: True) is None


def test_scene_figure_arrays_from_its_spec():
    from cm1view.figures import draw as figdraw, spec as fg
    zz = np.broadcast_to(Z[:, None, None], SH)
    blob = np.exp(-((XX - 20) ** 2 + (YY - 20) ** 2 + (zz - 3) ** 2) / 20.0)
    vols = dict(blob=blob, uinterp=np.full(SH, 10.0), vinterp=zeros(), winterp=zeros())
    run = _Run(xh=X1, yh=X1, z=Z, dx=500.0, dy=500.0, nk=len(Z), umove=0.0, vmove=0.0,
               vols=vols, times=np.array([0.0, 300.0]))
    F = _Fields(run, vols)
    spec = dict(kind="scene", run=0, time_s=300.0, scene3d=dict(
        ztop=50.0, smooth=0.0, res=1, isos=[dict(var="blob", val=0.5, color="#ff0000", op=0.6)],
        ground=dict(on=True, var="blob"), camera=dict(preset="top")))
    # no box: the whole domain; the top no higher than the model's
    req = fg.scene_request(run, spec, None, 1)
    assert req["box"] == (0.0, 40.0, 0.0, 40.0) and req["ztop"] == float(Z[-1])
    assert req["storm"] == (0.0, 0.0) and "umove" in req["fstorm"][1]
    assert not req["stream"]["on"] and req["exag"] == 2.0  # (SCENE3D defaults)
    d = fg.scene_extract(run, F, spec)
    assert d["time_s"] == 300.0 and d["nmesh"] == 1 and "G_a" in d and "S_x" not in d
    assert list(d["box"]) == [0.0, 40.0, 0.0, 40.0]
    a = figdraw.scene_arrays(d)
    assert a["meshes"][0]["color"] == "#ff0000" and a["ground"]["cmap"] == "viridis"
    # the camera, look and exaggeration do not change the arrays; the isosurfaces do
    k = fg.scene_key(spec, "/run")
    spec2 = dict(spec, scene3d=dict(spec["scene3d"], exag=4.0, camera={}, look=dict(tube=2)))
    assert fg.scene_key(spec2, "/run") == k
    spec3 = dict(spec, scene3d=dict(spec["scene3d"], isos=[]))
    assert fg.scene_key(spec3, "/run") != k
    # no output at that time; a field the run lacks
    assert "no output" in fg.scene_extract(run, F, dict(spec, time_s=900.0))["missing"]
    bad = dict(spec, scene3d=dict(spec["scene3d"], isos=[dict(var="qr", val=1.0,
                                                              color="#fff", op=1.0)]))
    assert "no qr" in fg.scene_extract(run, F, bad)["missing"]


def test_scene_box_follows_the_track_in_an_animation():
    from cm1view.figures import draw as figdraw, spec as fg
    run = _Run(xh=X1, yh=X1, z=Z, dx=500.0, dy=500.0, nk=len(Z), umove=0.0, vmove=0.0,
               vols={}, times=np.array([0.0, 300.0, 600.0]))
    fixes = {0: dict(x=10.0, y=10.0), 1: dict(x=13.0, y=11.0)}
    sc = dict(box=[5.0, 15.0, 5.0, 15.0], follow="track",
              stream=dict(seed_box=[8.0, 9.0, 8.0, 9.0]))
    spec = dict(kind="scene", run=0, time_s=0.0, runs=[dict(path="/run")], scene3d=sc)
    # the preview (no animation: no first frame) stays put
    assert fg.scene_request(run, spec, fixes, 1)["shift"] is None
    f1 = fg.shift_times(spec, 300.0)
    assert f1["time_s"] == 300.0 and f1["scene3d"]["t0_s"] == 0.0
    req = fg.scene_request(run, f1, fixes, 1)
    assert req["shift"] == (3.0, 1.0) and req["box"] == (8.0, 18.0, 6.0, 16.0)
    assert req["stream"]["seed_box"] == [11.0, 12.0, 9.0, 10.0]
    # a frame without a fix, a fixed box, the whole domain: no shift
    assert fg.scene_request(run, fg.shift_times(spec, 600.0), fixes, 2)["shift"] is None
    fixed = dict(spec, scene3d=dict(sc, follow="fixed"))
    assert fg.scene_request(run, fg.shift_times(fixed, 300.0), fixes, 1)["shift"] is None
    whole = dict(spec, scene3d=dict(sc, box=None))
    assert fg.scene_request(run, fg.shift_times(whole, 300.0), fixes, 1)["shift"] is None
    # frames of a following box have their own arrays (scene_key)
    assert fg.scene_key(f1, "/run") != fg.scene_key(dict(f1, scene3d=dict(
        f1["scene3d"], t0_s=300.0)), "/run")
    # an explicit camera moves with the box
    cam = dict(position=[0.0, 0.0, 30.0], focal=[10.0, 10.0, 0.0])
    s = figdraw.scene_spec(dict(shift=np.array([3.0, 1.0])), dict(scene3d=dict(camera=cam)))
    assert s["camera"]["position"] == [3.0, 1.0, 30.0]
    assert s["camera"]["focal"] == [13.0, 11.0, 0.0]
