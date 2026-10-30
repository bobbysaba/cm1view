"""Map, cross-section and 3D: streamlines on the map, the section and its A/B marks,
contour and plot style, the 3D region and floor, 3D streamlines (pick one, sample a field along it, keep it
through a re-render) and the streamline card's axes."""
import time

import numpy as np

from cm1view.core import render, vectors, volume3d
from conftest import tap, wait


def region(v, x0, x1, y0, y1):
    v.mode.set("3D region")
    v._on_select(type("E", (), {"final": True, "geometry": dict(
        type="rect", x0=x0, x1=x1, y0=y0, y1=y1)})())


def test_map_streamlines_follow_the_wind(viewer, reg):
    v = viewer
    run, F = reg.get()
    v.tslider.value = 4
    o = v.vecs[0]
    o["on"].value = True
    o["style"].value = "streamlines"
    assert o["density"].name == "Streamline density" and not o["ref"].visible
    spec = v._map_spec()
    res = render.compute_map(F, spec)
    sl, heads = res["vecs"][0]["stream"]
    assert len(sl["xs"]) > 20 and len(heads["x"]) == len(sl["xs"]) and "vec" not in res["vecs"][0]
    v._apply_map(res, spec, v.gen["map"])
    g = v.vec_r[0]
    assert len(g["sl_src"].data["xs"]) == len(sl["xs"]) and len(g["src"].data["x0"]) == 0
    # a streamline's direction matches (u, v) where it starts
    lvl = spec["vecs"][0]["level"]
    u, vv = F.plane("uinterp", 4, "height", lvl), F.plane("vinterp", 4, "height", lvl)
    if spec["vecs"][0]["frame"] == "ground":
        u, vv = u + run.umove, vv + run.vmove
    x, y = sl["xs"][0], sl["ys"][0]
    i, j = run.ij(x[1], y[1])
    d = np.array([x[2] - x[1], y[2] - y[1]])
    w = np.array([u[j, i], vv[j, i]])
    assert d @ w / (np.linalg.norm(d) * np.linalg.norm(w) + 1e-12) > 0.9
    # back to arrows
    o["style"].value = "arrows"
    res = render.compute_map(F, v._map_spec())
    v._apply_map(res, v._map_spec(), v.gen["map"])
    assert "stream" not in res["vecs"][0] and len(g["sl_src"].data["xs"]) == 0
    assert len(g["src"].data["x0"]) > 0


def test_map_wind_and_vorticity_vectors_together(viewer, reg):
    """A second vector row: the horizontal vorticity (its own reference arrow, no
    frame), drawn with the wind; ✕ takes its arrows off the map."""
    v = viewer
    run, F = reg.get()
    v.tslider.value = 4
    v.vecs[0]["on"].value = True
    v._add_vec()
    o = v.vecs[1]
    assert o["q"].value == "hvort" and not o["frame"].visible
    assert o["ref"].value == vectors.VECTORS["hvort"].ref and "1/s" in o["ref"].name
    o["q"].value = "wind"
    assert o["frame"].visible and o["ref"].value == 20.0
    o["q"].value = "hvort"
    spec = v._map_spec()
    res = render.compute_map(F, spec)
    v._apply_map(res, spec, v.gen["map"])
    assert [len(g["src"].data["x0"]) > 0 for g in v.vec_r] == [True, True]
    assert v.map_drawer.items["vec"][0].name.startswith("Vectors · 2")
    # the arrows are (ξ, η) scaled by the reference
    a = res["vecs"][1]["vec"]
    xi = F.plane("xvort", 4, "height", spec["vecs"][1]["level"])
    i, j = run.ij(a["x0"][0], a["y0"][0])
    assert np.sign(a["x1"][0] - a["x0"][0]) == np.sign(xi[j, i]) or abs(xi[j, i]) < 1e-6
    n = len(v.fig.renderers)
    v._drop_vec(o)
    assert len(v.vecs) == len(v.vec_r) == 1 and len(v.fig.renderers) == n - 4


def test_cross_section_marks_and_style(viewer):
    v = viewer
    v.mode.set("Cross-section")
    o = v.xs_ovs[0]
    o["color"].value, o["negdash"].value, v.xs_cmap.value = "#fbbf24", False, "viridis"
    tap(v, -15.0, -6.0)
    tap(v, 15.0, -1.0)
    wait(lambda: "long" in (v.xs_status.object or ""), msg="section")
    assert [a.text for a in v.xs_lab] == ["A", "B"] and all(a.visible for a in v.xs_lab)
    _, _, pr, nr = v.xs_ov_r[0]
    assert pr.glyph.line_color == "#fbbf24" and nr.glyph.line_dash in ("solid", [])
    assert len(v.xs_vec_r[0]["src"].data["x0"]) > 0  # the wind, on by default
    v.xs_auto.value = False
    assert v.xs_min.value < v.xs_max.value
    # plot style: limits set the view (and the reset tool's view), clamped to the data
    L, top = v._xs_extent
    v.xs_smin.value, v.xs_smax.value, v.xs_zmax.value = 5.0, 15.0, 1000.0
    xr, yr = v.xs_fig.x_range, v.xs_fig.y_range
    assert (xr.start, xr.end, xr.reset_start, xr.bounds) == (5.0, 15.0, 5.0, (0.0, L))
    assert (yr.start, yr.end) == (0.0, top) and v.xs_lab[0].y == 0.0
    v.xs_zmin.value = 2.0
    assert yr.start == 2.0 and v.xs_lab[0].y == 2.0
    v.xs_font.value, v.xs_height.value, v.xs_ab.value = 16, 500, False
    assert v.xs_fig.height == 500 and not any(a.visible for a in v.xs_lab)
    assert v.xs_fig.xaxis[0].axis_label_text_font_size == "16px"
    v._on_xs_style_reset(None)
    assert (xr.start, xr.end, yr.start) == (0.0, L, 0.0) and all(a.visible for a in v.xs_lab)


def test_cross_section_layers_as_on_the_map(viewer):
    """More fills, several contours and several vectors, each a row added and removed
    as on the map; drawn in that order over the fill, and carried into a figure."""
    v = viewer
    v.mode.set("Cross-section")
    tap(v, -15.0, -6.0)
    tap(v, 15.0, -1.0)
    wait(lambda: "long" in (v.xs_status.object or ""), msg="section")
    n = len(v.xs_fig.renderers)
    v._xs_add_fill()
    v._xs_add_contour()
    v._xs_add_vec()
    assert len(v.xs_fig.renderers) == n + 6
    assert len(v.xs_fills) == 1 and len(v.xs_ovs) == 2 and len(v.xs_vecs) == 2
    assert v.xs_vecs[1]["q"].value != "wind" and "level" not in v.xs_vecs[1]
    rs = v.xs_fig.renderers
    order = [rs.index(r) for r in (v.xs_poly_r, v.xs_fill_r[0]["img"], v.xs_ov_r[0][2],
                                   v.xs_ov_r[1][2], v.xs_vec_r[0]["seg"],
                                   v.xs_vec_r[1]["seg"])]
    assert order == sorted(order)
    spec = v.xs_spec()  # (each add redrew the section)
    wait(lambda: v.xs_fill_r[0]["cbar"].visible, msg="more fills")
    f = v.xs_fill_r[0]
    assert f["img"].visible and f["cbar"].title == v.F[spec["fills"][0]["var"]].name
    assert v.xs_drawer.items["vec"][0].name.startswith("Vectors · 2")
    # Filled contours, for the first fill too
    v.xs_fill_style.value = "contourf"
    wait(lambda: v.xs_poly_r.visible and len(v.xs_poly.data["xs"]) > 0, msg="bands")
    assert not v.xs_img_r.visible
    v._xs_drop_vec(v.xs_vecs[1])
    v._xs_drop_contour(v.xs_ovs[1])
    v._xs_drop_fill(v.xs_fills[0])
    assert len(v.xs_fig.renderers) == n and not v.xs_fill_r and len(v.xs_ov_r) == 1
    assert f["cbar"] not in v.xs_fig.right


def test_3d_floor_field(viewer, reg):
    v = viewer
    _, F = reg.get()
    name = "zvort" if "zvort" in F else "winterp"
    v.tslider.value = 4
    v.v3_ground.value = True
    v.v3_floor.value = name
    assert v.v3_floor_z.visible and not v.v3_floor_min.visible
    floor = lambda: next(tr for tr in v.plot3d.object.data if tr.name == "floor")  # noqa: E731
    region(v, -20.0, 4.0, -16.0, 8.0)
    wait(lambda: v.plot3d.object is not None and "Rendering" not in
         (v.v3_status.object or ""), msg="3D scene")
    tr = floor()
    assert F[name].label in tr.colorbar.title.text and "@" in tr.colorbar.title.text
    assert tr.cmin == -tr.cmax and tr.cmax > 0  # signed field: symmetric from the data
    v.v3_floor_range.value = "custom"
    assert v.v3_floor_min.visible
    v.v3_floor_min.value, v.v3_floor_max.value = -0.01, 0.02
    wait(lambda: floor().cmax == 0.02, msg="custom range")
    v.v3_floor_range.value = "data"
    v.v3_floor.value = "cref" if "cref" in F else name
    if "cref" in F:
        assert not v.v3_floor_z.visible
        wait(lambda: (floor().cmin, floor().cmax) == (0.0, 75.0), msg="reflectivity floor")
    v.v3_ground.value = False
    wait(lambda: all(tr.name != "floor" for tr in v.plot3d.object.data), msg="no floor")
    v._on_clear_points(None)


def test_3d_streamline_pick_and_sample(viewer, reg):
    v = viewer
    _, F = reg.get()
    v.tslider.value = 4
    region(v, -20.0, 4.0, -16.0, 8.0)
    assert v.workspace.value == "3D"
    v.st_on.value, v.st_dir.value = True, "both"
    wait(lambda: v._s3 is not None and v._s3["stream"] is not None
         and "triangles" in (v.v3_status.object or ""), msg="3D scene")
    st = v._s3["stream"]
    assert st["n"] > 0
    assert np.all((st["segs"][:, 2] >= st["segs"][:, 0]) & (st["segs"][:, 2] < st["segs"][:, 1]))
    # pick a streamline: highlighted, and w along it on the card
    idx, _ = v._trace("stream")
    a, b, _ = st["segs"][len(st["segs"]) // 2]
    v.plot3d.click_data = {"points": [{"curveNumber": idx, "pointNumber": int(a + 3)}]}
    assert v._sl_line is not None and v.sl_card.visible
    wait(lambda: len(v.sl_src.data["s"]) > 0, msg="sampled")
    _, hl = v._trace("selected")
    assert len(hl.x) == b - a
    assert np.isfinite(np.nanmax(v.sl_src.data["v"]))
    # the others go grey and faint by their colour scale and opacity (no colours resent)
    _, base = v._trace("stream")
    assert base.line.colorscale[0][1] == volume3d.DIM and len(base.line.color) == len(base.x)
    assert base.opacity == volume3d.DIM_OPACITY
    # the card's pointer (snapped in the browser into sl_at) moves the 3D cursor
    v.sl_at.location = 0.0
    assert len(v._trace("cursor")[1].x) == 1
    v.sl_at.location = None
    assert len(v._trace("cursor")[1].x) == 0
    for name in ("_ws", "thpert"):
        n0 = v.gen["sl"]
        v.sl_field.value = name
        wait(lambda: "Sampling" not in (v.sl_info.object or "") and v.gen["sl"] > n0,
             msg=f"sample {name}")
        assert np.isfinite(np.nanmax(v.sl_src.data["v"]))
    # a re-render keeps the same streamline (same seed)
    seed = v._sl_seed
    v.request_3d()
    wait(lambda: "Rendering" not in (v.v3_status.object or ""), msg="re-render")
    time.sleep(0.5)
    assert v._sl_seed == seed
    # pin it and two more: each its own colour in the scene and on the card
    for line in (len(st["segs"]) // 2, 0, len(st["segs"]) - 1):
        v._select_line(line)
        assert v.sl_pin.visible and v.sl_pin.icon == "pin"
        v._on_pin()
        assert v._sl_line is None and v.sl_card.visible
    wait(lambda: len(v.sl_pins_src.data["xs"]) == 3 and "Sampling" not in
         (v.sl_info.object or ""), msg="three pins sampled")
    assert len(set(v.sl_pins_src.data["color"])) == 3
    _, pl = v._trace("pinned")
    _, ps = v._trace("pinseeds")
    assert len(ps.x) == 3 and len(pl.x) == len(pl.line.color) == len(v._pin_of)
    assert ({volume3d.PIN_COLORS[int(c)] for c in pl.line.color}
            == {p["color"] for p in v._sl_pins})
    assert "3 streamlines" in v.sl_info.object
    # clicking a pinned line selects it; the pin button then unpins it
    k = v._pin_of.index(1) + 1
    v.plot3d.click_data = {"points": [{"curveNumber": v._trace("pinned")[0],
                                       "pointNumber": k}]}
    assert v._sl_line == v._sl_pins[1]["line"] and v.sl_pin.icon == "pinned-off"
    wait(lambda: len(v.sl_pins_src.data["xs"]) == 2 and len(v.sl_src.data["s"]) > 0,
         msg="selected pin on its own source")
    v._on_pin()
    assert len(v._sl_pins) == 2 and v.sl_pin.icon == "pin"
    # the pins follow their seeds through a re-render, and × drops everything
    seeds = [p["seed"] for p in v._sl_pins]
    v.request_3d()
    wait(lambda: "Rendering" not in (v.v3_status.object or ""), msg="re-render pins")
    time.sleep(0.5)
    assert [p["seed"] for p in v._sl_pins] == seeds
    assert all(p["line"] is not None for p in v._sl_pins)
    v._clear_lines()
    assert not v.sl_card.visible and v._sl_seed is None and not v._sl_pins
    assert len(v._trace("pinseeds")[1].x) == 0
    assert v._trace("stream")[1].line.colorscale[0][1] != volume3d.DIM
    assert v._trace("stream")[1].opacity == 1.0
    v._on_clear_points(None)
    assert v.workspace.value == "Map"


def test_streamline_card_fits_the_field(viewer):
    v = viewer
    line = dict(key="sel", color="#fde047", no=None, a=0, s=np.linspace(0, 12, 50),
                v=0.02 * np.sin(np.linspace(0, 6, 50)), z=np.linspace(0.3, 2.5, 50),
                x0=0.0, y0=0.0, z0=0.3, length=12.0)
    v._apply_sl(v.gen["sl"], dict(label="ωs (s⁻¹)", lines=[line]))
    yr = v.sl_fig.y_range
    assert -0.03 < yr.start < -0.019 and 0.019 < yr.end < 0.03
    # a pin with a wider range widens the fit; both are listed
    pin = dict(line, key="pin", color="#38bdf8", no=1, v=2 * line["v"], s=line["s"] - 4)
    v._apply_sl(v.gen["sl"], dict(label="ωs (s⁻¹)", lines=[line, pin]))
    assert yr.start < -0.04 and yr.end > 0.04 and v.sl_fig.x_range.start < -4
    assert v.sl_pins_src.data["name"] == ["#1"] and "2 streamlines" in v.sl_info.object
    v.sl_big.value = True
    assert v.sl_fig.height == 440 and "1200px" in v.sl_card.styles["width"]


def test_use_map_view_as_region(viewer):
    v = viewer
    v._on_use_view(None)
    x0, x1, y0, y1 = v.box
    X0, X1, Y0, Y1 = v.extent
    assert X0 <= x0 < x1 <= X1 and Y0 <= y0 < y1 <= Y1


def test_map_difference_minus_another_time_or_run(viewer, reg, demo_root):
    """The map fill minus the output before, a fixed time or another run's at the same
    time: drawn as the hand difference, diverging about 0, said in the title; a time
    the other run lacks says so; a figure from the map keeps the difference."""
    import os
    v = viewer
    run, F = reg.get()
    v.tslider.value = 2
    v.fill_var.value = "winterp"
    d = v.fill_diff
    assert not d["run"].visible
    d["on"].value = True
    assert d["run"].visible and d["time"].visible and v.fill_cmap.value == "RdBu_r"
    weak = os.path.abspath(os.path.join(demo_root, "demo", "supercell_weak"))
    assert weak in d["run"].options.values()
    d["time"].value = "prev"
    wait(lambda: "minus 1:00:00" in (v.map_title.object or ""), msg="difference")
    lvl = float(v.fill_lvl.value)
    want = F.plane("winterp", 2, "height", lvl) - F.plane("winterp", 1, "height", lvl)
    win = render.view_window(run, v.view, v.maxpix)
    _, _, want = render._crop(run, want, win)
    np.testing.assert_allclose(v.img_src.data["image"][0], want, atol=1e-5)
    lo, hi = v._last_range
    assert lo == -hi and (lo, hi) == render.diff_range(
        F.plane("winterp", 2, "height", lvl) - F.plane("winterp", 1, "height", lvl))
    assert "difference" in v.cbar_label.axis_label
    # another run at the shown time
    r2, F2 = reg.get(weak)
    d["time"].value, d["run"].value = "", weak
    wait(lambda: "of " in (v.map_title.object or ""), msg="other run")
    want = F.plane("winterp", 2, "height", lvl) - F2.plane("winterp", 2, "height", lvl)
    _, _, want = render._crop(run, want, win)
    np.testing.assert_allclose(v.img_src.data["image"][0], want, atol=1e-5)
    # into a figure: the other run added, the layer a difference with the map's colours
    v.figed.from_map()
    s = v.figed.collect()
    lay = s["layers"][0]
    assert lay["minus"]["run"] is not None and lay["minus"]["time_s"] is None
    assert s["runs"][lay["minus"]["run"]]["path"] == weak
    assert (lay["vmin"], lay["vmax"]) == tuple(round(x, 6) for x in v._last_range)
    # a time before the first output: an error, not a map
    v.tslider.value, d["run"].value, d["time"].value = 0, "", "prev"
    wait(lambda: "no output before" in (v.status.object or ""), msg="error")
    # off: the field's own colours
    d["on"].value = False
    assert v.fill_cmap.value == F["winterp"].cmap and not d["run"].visible


def test_cross_section_difference(viewer, reg):
    """The section fill minus the output before: the hand difference along A–B."""
    v = viewer
    run, F = reg.get()
    v.tslider.value = 2
    v.mode.set("Cross-section")
    v.xs_fill.value = "winterp"
    tap(v, -15.0, -6.0)
    tap(v, 15.0, -1.0)
    wait(lambda: "long" in (v.xs_status.object or ""), msg="section")
    v.xs_diff["on"].value = True
    assert v.xs_cmap.value == "RdBu_r"
    v.xs_diff["time"].value = "prev"
    wait(lambda: "minus 1:00:00" in (v.xs_status.object or ""), msg="difference")
    spec = v.xs_spec()
    s, fi, fj, _ = render.section_coords(run, spec["A"], spec["B"])
    zq = np.linspace(0.0, spec["ztop"], max(120, int(spec["ztop"] / 0.04)))
    run.load_volumes(F.native_deps("winterp"), 1)
    want = render.sample_section(run, F.volume("winterp", 2), fi, fj, zq) \
        - render.sample_section(run, F.volume("winterp", 1), fi, fj, zq)
    np.testing.assert_allclose(v.xs_img.data["image"][0], want, atol=1e-5)
    assert v._xs_range == render.diff_range(want)


def test_difference_on_another_grid_is_interpolated():
    """minus_plane: another run on a different grid is interpolated onto this one
    (blank outside its domain)."""
    from types import SimpleNamespace as NS

    class Flds:
        def __init__(self, x, y):
            self.run = NS(xh=x, yh=y, name="r")
            X, Y = np.meshgrid(x, y)
            self.a = (2 * X + Y).astype(np.float32)

        def __contains__(self, n):
            return True

        def plane(self, *a, **k):
            return self.a

    A = Flds(np.arange(0.0, 10.0, 1.0), np.arange(0.0, 8.0, 1.0))
    B = Flds(np.arange(0.0, 6.0, 0.5), np.arange(0.0, 6.0, 0.5))  # (finer, smaller)
    b = render.minus_plane(A, B, "f", 0, "height", 1.0)
    assert b.shape == A.a.shape
    inside = np.isfinite(b)
    assert inside[:6, :6].all() and not inside[:, 6:].any() and not inside[6:, :].any()
    np.testing.assert_allclose(b[inside], A.a[inside], atol=1e-5)  # (a linear field)
    assert render.minus_plane(A, A, "f", 0, "height", 1.0) is A.a
