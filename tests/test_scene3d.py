"""The rendered 3D scene (figures/draw/scene3d.py): camera framing and the off-screen
PyVista picture of a ball isosurface, a floor, vectors and streamlines."""
import numpy as np
import pytest
from skimage.measure import marching_cubes

from cm1view.figures.draw import scene3d
from conftest import render

BOX = (0.0, 40.0, 0.0, 40.0)


def _scene(**kw):
    return dict(dict(box=BOX, ztop=10.0, exag=1.0, camera={}, look={}), **kw)


def _ball(cx=20.0, cy=20.0, cz=5.0, r=4.0, color="#ff0000", op=1.0):
    g = np.linspace(-1.0, 1.0, 24)
    zz, yy, xx = np.meshgrid(g, g, g, indexing="ij")
    verts, faces, _, _ = marching_cubes(xx ** 2 + yy ** 2 + zz ** 2, level=0.5)
    k, j, i = (verts.T / 23.0 * 2 - 1) * r / np.sqrt(0.5)
    return dict(x=cx + i, y=cy + j, z=cz + k, faces=faces.astype(np.int32), color=color,
                opacity=op, name="ball")


def _ground():
    x = np.linspace(0.0, 40.0, 41)
    a = np.broadcast_to(x[None, :], (41, 41)).copy()
    a[0, 0] = np.nan
    return dict(x=x, y=x, a=a, lo=0.0, hi=40.0, title="a", cmap="viridis", rev=False)


def _stream():
    t = np.linspace(5.0, 35.0, 30)
    x = np.concatenate([t, [np.nan], t, [np.nan]])
    y = np.concatenate([np.full(30, 10.0), [np.nan], np.full(30, 30.0), [np.nan]])
    z = np.concatenate([np.linspace(1, 8, 30), [np.nan], np.full(30, 2.0), [np.nan]])
    return dict(x=x, y=y, z=z, w=np.where(np.isfinite(x), 5.0, np.nan), n=2,
                color_by="w", seed_box=(4.0, 6.0, 9.0, 31.0), seed_z=1.0)


def _vecs():
    # surface_vectors' layout: tail, tip, barb, NaN, tip, barb, NaN per arrow
    nan = np.nan
    x = [5, 9, 8.5, nan, 9, 8.5, nan, 15, 18, 17.5, nan, 18, 17.5, nan]
    y = [5, 5, 5.4, nan, 5, 4.6, nan, 15, 15, 15.4, nan, 15, 14.6, nan]
    return [dict(x=np.array(x, float), y=np.array(y, float), z=0.5, color="#000000",
                 name="wind")]


def test_camera_fits_the_box_and_top_view_has_north_up():
    pos, foc, up, va, par, _ = scene3d.camera_pose(_scene())
    assert np.allclose(foc, [20, 20, 5]) and not par
    # oblique: from the south-east, above
    assert pos[0] > 20 and pos[1] < 20 and pos[2] > 5
    R = 0.5 * np.linalg.norm([40, 40, 10])
    assert np.linalg.norm(pos - foc) * np.sin(np.radians(va / 2)) >= R - 1e-6
    pos, foc, up, *_ = scene3d.camera_pose(_scene(camera=dict(preset="top")))
    assert np.allclose(pos[:2], foc[:2], atol=1e-6) and np.allclose(up, [0, 1, 0])
    # zoom brings it closer; exaggeration raises the centre
    p2, f2, *_ = scene3d.camera_pose(_scene(exag=2.0, camera=dict(zoom=2.0)))
    assert np.isclose(f2[2], 10.0)
    # an explicit pose wins, its z in world km
    p3, f3, u3, *_ = scene3d.camera_pose(_scene(exag=2.0, camera=dict(
        position=(0, 0, 3), focal=(20, 20, 1))))
    assert np.allclose(p3, [0, 0, 6]) and np.allclose(f3, [20, 20, 2])


def test_render_draws_the_ball_where_the_projection_says():
    pytest.importorskip("pyvista")
    sc = _scene(look=dict(outline=False))
    img, proj = scene3d.render(dict(meshes=[_ball()]), sc, (320, 240))
    assert img.shape == (240, 320, 4) and img.dtype == np.uint8
    assert (img[2, 2, :3] == 255).all() and img[2, 2, 3] == 255  # white background
    (px, py), = scene3d.to_pixels(proj, [(20, 20, 5)], (320, 240))
    assert abs(px - 160) < 3 and abs(py - 120) < 3  # the focal point is the centre
    r, g, b = (int(v) for v in img[int(py), int(px), :3])
    assert r > 120 and g < 80 and b < 80  # red, shaded


def test_render_transparent_background_and_all_parts():
    pytest.importorskip("pyvista")
    arrays = dict(meshes=[_ball(op=0.5), _ball(r=2.0, color="#0000ff")],
                  ground=_ground(), vecs=_vecs(), stream=_stream())
    for arrows in ("glyph", "lines"):
        sc = _scene(exag=2.0, look=dict(background="transparent", arrows=arrows),
                    camera=dict(projection="orthographic", azimuth=200, elevation=35))
        img, proj = scene3d.render(arrays, sc, (300, 200))
        assert img.shape == (200, 300, 4)
        assert img[1, 1, 3] == 0  # nothing drawn in the corner
        assert (img[..., 3] > 0).mean() > 0.2
        # the floor's middle: viridis at a = 30 (green), unlit
        (px, py), = scene3d.to_pixels(proj, [(30, 8, 0)], (300, 200), exag=2.0)
        r, g, b = (int(v) for v in img[int(py), int(px), :3])
        assert g > r and g > 60


def test_stream_style_and_floor_colours():
    cm, lo, hi, lab = scene3d.stream_style(_stream(), 10.0)
    assert cm == "RdBu_r" and lo == -5.0 and hi == 5.0 and lab == "w (m/s)"
    s = dict(_stream(), color_by="z")
    assert scene3d.stream_style(s, 12.0) == ("viridis", 0.0, 12.0, "z (km)")
    rgb = scene3d.floor_rgb(_ground())
    assert rgb.shape == (41, 41, 3) and np.allclose(rgb[0, 0], 0.85)


def _scene_spec(**kw):
    return dict(dict(version=1, kind="scene", rows=1, cols=1, size=[4.0, 3.0], run=0,
                     time_s=600.0, runs=[dict(path="/no/such/run", label="a")], layers=[],
                     scene3d=dict(exag=2.0), export=dict(dpi=80, format="png")), **kw)


def _scene_panel_data():
    arrays = dict(meshes=[_ball(op=0.5)], ground=_ground(), vecs=_vecs(), stream=_stream())
    return dict(scene3d.scene_data(arrays, BOX, 10.0), time_s=600.0, run=0)


def test_scene_data_round_trips_through_the_saved_arrays():
    from cm1view.figures.spec import bundle
    d = _scene_panel_data()
    back = bundle.unflatten({k: np.asarray(v) for k, v in bundle.flatten({0: d}).items()})[0]
    a = scene3d.scene_arrays(back)
    (m,) = a["meshes"]
    assert m["faces"].dtype == np.int32 and m["color"] == "#ff0000" and m["opacity"] == 0.5
    assert a["ground"]["cmap"] == "viridis" and a["ground"]["rev"] is False
    assert np.isnan(a["ground"]["a"][0, 0])
    assert a["vecs"][0]["z"] == 0.5 and a["stream"]["seed_box"] == (4.0, 6.0, 9.0, 31.0)
    assert a["stream"]["color_by"] == "w" and a["stream"]["n"] == 2
    assert list(back["box"]) == list(BOX) and back["ztop"] == 10.0
    # nothing but a floor
    d = scene3d.scene_data(dict(meshes=[], ground=None, vecs=[], stream=None), BOX, 8.0)
    a = scene3d.scene_arrays(d)
    assert a == dict(meshes=[], ground=None, vecs=[], stream=None)


def test_reflectivity_floor_steps_every_5_dbz():
    g = dict(_ground(), cmap="reflectivity", lo=0.0, hi=75.0,
             a=np.array([[2.0, 7.0, 9.0, 12.0]]))
    rgb = scene3d.floor_rgb(g)
    assert np.allclose(rgb[0, 0], 0.85)  # (below 5 dBZ: the map's clear step)
    assert np.allclose(rgb[0, 1], rgb[0, 2]) and not np.allclose(rgb[0, 2], rgb[0, 3])


def test_scene_figure_draws_the_picture_ticks_legend_and_colorbars():
    pytest.importorskip("pyvista")
    from cm1view.figures import draw as figdraw
    fig = figdraw.draw(_scene_spec(), {0: _scene_panel_data()})
    ax = fig._cv_axes[0]
    (im,) = ax.images
    h, w = im.get_array().shape[:2]
    bb = ax.get_window_extent()
    # rendered at the export's 80 dpi, as large as the axes
    assert abs(w - bb.width / fig.dpi * 80) <= 2 or abs(h - bb.height / fig.dpi * 80) <= 2
    texts = [t.get_text() for t in ax.texts]
    assert {"x (km)", "y (km)", "z (km)"} <= set(texts) and "40" in texts
    assert len(fig.axes) == 3  # (the floor's and the streamlines' colorbars)
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert labels == ["ball", "wind", "streamlines"]
    # the preview's resolution, a transparent figure, no ticks or colorbars
    spec = _scene_spec(background="none", scene3d=dict(
        exag=1.0, dpi=40, look=dict(ticks=False, floor_bar="none", stream_bar="none")))
    fig = figdraw.draw(spec, {0: _scene_panel_data()})
    ax = fig._cv_axes[0]
    img = ax.images[0].get_array()
    assert img.shape[1] < w and img[0, 0, 3] == 0
    assert not ax.texts and len(fig.axes) == 1


def test_scene_figure_bundle_redraws_from_its_script(tmp_path):
    pytest.importorskip("pyvista")
    import runpy
    from cm1view.figures.spec import bundle
    out = bundle.save_bundle(_scene_spec(), {0: _scene_panel_data()}, str(tmp_path / "s3d"))
    first = (tmp_path / "s3d.png").stat().st_mtime_ns
    assert "pyvista" in open(out["script"]).read()
    runpy.run_path(out["script"], run_name="__main__")
    assert (tmp_path / "s3d.png").stat().st_mtime_ns >= first


def test_camera_from_plotly_matches_the_presets():
    # the viewer's oblique eye is the "oblique" preset at zoom 1
    cam = scene3d.camera_from_plotly({"eye": {"x": 1.25, "y": -1.45, "z": 0.75}})
    assert (cam["azimuth"], cam["elevation"]) == scene3d.PRESETS["oblique"]
    assert cam["zoom"] == 1.0 and cam["projection"] == "perspective"
    cam = scene3d.camera_from_plotly({"eye": {"x": 0.0, "y": -2.0, "z": 2.0},
                                      "projection": {"type": "orthographic"}})
    assert (cam["azimuth"], cam["elevation"]) == (180.0, 45.0)
    assert cam["zoom"] == round(scene3d.PLOTLY_EYE / np.hypot(2, 2), 2)
    assert cam["projection"] == "orthographic"
    assert scene3d.camera_from_plotly(None) == {} == scene3d.camera_from_plotly({"eye": {}})


# ------------------------------------------------------------------ the editor (D4)
def test_scene_editor_starts_from_the_3d_view_and_round_trips(ed):
    import json
    from cm1view.figures import spec as fg

    v = ed.v
    v.v3_exag.value = 3.0
    ed.kind.value = "scene"
    s = ed.collect()
    sc = s["scene3d"]
    assert s["kind"] == "scene" and sc["exag"] == 3.0
    assert [(i["var"], i["on"]) for i in sc["isos"]] == [(d["var"].value, d["on"].value)
                                                         for d in v.isos]
    assert ed.scene_col in ed.layers_tab.objects
    assert ed.plan_layers not in ed.layers_tab.objects
    assert ed.times_sec.visible and not ed.rows.visible
    # unticked surfaces are kept in the spec, not computed
    req = fg.scene_request(ed.run, s, {}, 1)
    assert len(req["isos"]) == sum(i["on"] for i in sc["isos"]) < len(sc["isos"])
    # a spec back into the widgets gives the same block, with what has no widget kept
    sc2 = dict(sc, camera=dict(sc["camera"], azimuth=200.0, position=[0.0, 0.0, 30.0],
                               focal=[20.0, 20.0, 0.0]),
               look=dict(sc["look"], peels=4, background="black"))
    ed.set_spec(dict(s, scene3d=sc2))
    dump = lambda x: json.dumps(x, sort_keys=True, default=float)  # noqa: E731
    assert dump(ed.collect()["scene3d"]) == dump(fg.scene3d_of(dict(scene3d=sc2)))
    # a camera edit: the explicit position no longer holds
    ed.sc_c["zoom"].value = 2.0
    cam = ed.collect()["scene3d"]["camera"]
    assert cam["zoom"] == 2.0 and "position" not in cam and cam["azimuth"] == 200.0


def test_figure_of_the_3d_view_takes_its_camera(ed):
    v = ed.v
    v.plot3d.relayout_data = {"scene.camera": {"eye": {"x": 0.0, "y": -2.0, "z": 2.0},
                                               "projection": {"type": "orthographic"}}}
    ed.from_3d()
    s = ed.collect()
    cam = s["scene3d"]["camera"]
    assert s["kind"] == "scene" and s["time_s"] == float(ed.run.times[v.t])
    assert (cam["azimuth"], cam["elevation"], cam["projection"]) == (180.0, 45.0,
                                                                     "orthographic")
    v.v3_cam.value = "top"  # (a preset picked in the 3D view: the latest camera)
    ed.from_3d()
    cam = ed.collect()["scene3d"]["camera"]
    assert cam["preset"] == "top" and cam["azimuth"] is None


def test_scene_editor_preview_draws(ed):
    pytest.importorskip("pyvista")
    ed.from_3d()  # (at the viewer's time: the demo's first output has no storm yet)
    ed.sc_w["res"].value = 2
    ed.sc_g["on"].value = True
    spec, data, fig = render(ed)
    d = data[0]
    assert not d.get("missing") and d["nmesh"] >= 1
    assert any(getattr(ax, "_cv_proj", None) for ax in fig.axes)


def test_orbit_turns_the_camera_round_the_focal_point():
    c = scene3d.orbit_camera({}, 90.0)  # (the preset's azimuth, turned)
    assert c["azimuth"] == pytest.approx((scene3d.PRESETS["oblique"][0] + 90.0) % 360)
    assert scene3d.orbit_camera(dict(azimuth=300.0), 90.0)["azimuth"] == pytest.approx(30.0)
    assert scene3d.orbit_camera(dict(azimuth=10.0), 0.0)["azimuth"] == 10.0
    # an explicit camera standing north of the focal point goes east (compass sense)
    c = scene3d.orbit_camera(dict(position=[5.0, 15.0, 4.0], focal=[5.0, 5.0, 0.0],
                                  up=[0.0, 0.0, 1.0]), 90.0)
    assert np.allclose(c["position"], [15.0, 5.0, 4.0]) and c["focal"] == [5.0, 5.0, 0.0]
    assert np.allclose(c["up"], [0.0, 0.0, 1.0])


def test_scene_animation_frames_step_time_and_share_the_orbit():
    from cm1view.figures import spec as fg
    from cm1view.figures.anim import FigureAnimation
    spec = dict(kind="scene", run=0, time_s=600.0, runs=[dict(path="/run")],
                scene3d=dict(orbit=360.0, camera=dict(azimuth=0.0)))
    assert fg.animated(spec) and fg.time_refs(spec) == [("/run", 600.0)]
    offsets = [0.0, 300.0, 600.0, 900.0]
    az = []
    for j in range(len(offsets)):
        s = FigureAnimation._anim_frame(spec, offsets, j, dict(dpi=90))
        assert s["time_s"] == 600.0 + offsets[j] and s["scene3d"]["dpi"] == 90
        az.append(s["scene3d"]["camera"]["azimuth"])
    assert az == pytest.approx([0.0, 90.0, 180.0, 270.0])  # (no repeated frame)
    assert spec["scene3d"]["camera"] == dict(azimuth=0.0)  # (the spec is not changed)
    # other kinds: no orbit
    plan = dict(kind="plan", scene3d=dict(orbit=90.0))
    assert fg.scene_frame(plan, 1, 2) is plan
