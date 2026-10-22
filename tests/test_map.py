"""Map, cross-section and 3D: streamlines on the map, the section and its A/B marks,
contour and plot style, the 3D region and floor, 3D streamlines (pick one, sample a field along it, keep it
through a re-render) and the streamline card's axes."""
import time

import numpy as np

from cm1view import render
from conftest import tap, wait


def region(v, x0, x1, y0, y1):
    v.mode.set("3D region")
    v._on_select(type("E", (), {"final": True, "geometry": dict(
        type="rect", x0=x0, x1=x1, y0=y0, y1=y1)})())


def test_map_streamlines_follow_the_wind(viewer, reg):
    v = viewer
    run, F = reg.get()
    v.tslider.value = 4
    v.vec_on.value = True
    v.vec_style.value = "streamlines"
    assert v.vec_density.name == "Streamline density" and not v.vec_ref.visible
    spec = v._map_spec()
    res = render.compute_map(F, spec)
    sl, heads = res["stream"]
    assert len(sl["xs"]) > 20 and len(heads["x"]) == len(sl["xs"]) and res["vec"] is None
    v._apply_map(res, spec, v.gen["map"])
    assert len(v.sl2_src.data["xs"]) == len(sl["xs"]) and len(v.vec_src.data["x0"]) == 0
    # a streamline's direction matches (u, v) where it starts
    lvl = spec["vec"]["level"]
    u, vv = F.plane("uinterp", 4, "height", lvl), F.plane("vinterp", 4, "height", lvl)
    if spec["vec"]["frame"] == "ground":
        u, vv = u + run.umove, vv + run.vmove
    x, y = sl["xs"][0], sl["ys"][0]
    i, j = run.ij(x[1], y[1])
    d = np.array([x[2] - x[1], y[2] - y[1]])
    w = np.array([u[j, i], vv[j, i]])
    assert d @ w / (np.linalg.norm(d) * np.linalg.norm(w) + 1e-12) > 0.9
    # back to arrows
    v.vec_style.value = "arrows"
    res = render.compute_map(F, v._map_spec())
    v._apply_map(res, v._map_spec(), v.gen["map"])
    assert res.get("stream") is None and len(v.sl2_src.data["xs"]) == 0
    assert len(v.vec_src.data["x0"]) > 0


def test_cross_section_marks_and_style(viewer):
    v = viewer
    v.mode.set("Cross-section")
    v.xs_ccolor.value, v.xs_negdash.value, v.xs_cmap.value = "#fbbf24", False, "viridis"
    tap(v, -15.0, -6.0)
    tap(v, 15.0, -1.0)
    wait(lambda: "long" in (v.xs_status.object or ""), msg="section")
    assert [a.text for a in v.xs_lab] == ["A", "B"] and all(a.visible for a in v.xs_lab)
    assert v.xs_pos_r.glyph.line_color == "#fbbf24" and v.xs_neg_r.glyph.line_dash in ("solid", [])
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
    v._on_clear_points(None)
    assert v.workspace.value == "Map"


def test_streamline_card_fits_the_field(viewer):
    v = viewer
    line = dict(key="sel", color="#fde047", no=None, s=np.linspace(0, 12, 50),
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
