"""Figure workspace: the editor's widgets <-> spec, panel times and titles, undo / redo,
soundings, clicks on the preview, and the publication options drawn without errors."""

import numpy as np

from conftest import render


def test_motion_section_ends_turn_with_the_motion():
    """Along / across the storm motion: behind -> ahead and left -> right of the
    tracked motion, centred ahead / right of the storm; mwin: a mean motion."""
    from types import SimpleNamespace
    from cm1view.figures import spec as fg
    run = SimpleNamespace(umove=0.0, vmove=0.0, dx=1000.0, dy=1000.0,
                          xh=np.arange(100.0) + 0.5, yh=np.arange(100.0) + 0.5,
                          times=np.array([0.0, 300.0, 600.0, 900.0]))
    fixes = {t: dict(x=20.0 + 3.0 * t, y=50.0 + 3.0 * t * (t >= 2)) for t in range(4)}
    along = fg.section_defaults(orient="along", half=10.0, ahead=2.0, right=1.0)
    m = fg.section_motion(run, fixes, 0, along)
    assert np.allclose(m, (10.0, 0.0))  # (eastward: the first fixes)
    a, b = fg.section_ends(run, along, (20.0, 50.0), m)
    assert np.allclose(a, (12.0, 49.0)) and np.allclose(b, (32.0, 49.0))  # (right: south)
    across = dict(along, orient="across")
    a, b = fg.section_ends(run, across, (20.0, 50.0), m)
    assert np.allclose(a, (22.0, 59.0)) and np.allclose(b, (22.0, 39.0))  # (north -> south)
    assert fg.is_storm(across) and fg.uses_motion(across) and not fg.uses_motion(
        fg.section_defaults())
    assert fg.section_ends(run, along, None, m) is None  # (no track position)
    mean = fg.section_motion(run, fixes, 2, dict(along, mwin=10.0))  # (fixes 1–3)
    assert np.allclose(mean, np.mean([fg.section_motion(run, fixes, t, along)
                                      for t in (1, 2, 3)], axis=0))
    assert fg.section_motion(run, None, 0, along) == (0.0, 0.0)  # (no track: the domain's)
    assert fg.x_axis(along, "storm", (20.0, 50.0))[0] is None  # (the distance along)
    assert fg.describe(along) == "along the storm motion, +2 km ahead, +1 km right"


def _a_saved_figure(folder, name, when):
    """A figure saved before there were thumbnails: a spec and a PNG."""
    import os
    from PIL import Image
    os.makedirs(os.path.join(folder, "_src"), exist_ok=True)
    spec = os.path.join(folder, "_src", f"{name}_spec.json")
    with open(spec, "w") as f:
        f.write("{}")
    os.utime(spec, (when, when))
    Image.new("RGB", (900, 600), "red").save(os.path.join(folder, f"{name}.png"))
    return spec


def test_gallery_newest_first_by_folder_and_more(ed, tmp_path, monkeypatch):
    from cm1view.figures import quick
    monkeypatch.setattr(quick, "GALLERY_STEP", 2)
    monkeypatch.setattr(ed, "_fig_dir", str(tmp_path / "root" / "own"))
    listed = quick.saved_list
    monkeypatch.setattr(quick, "saved_list",
                        lambda own, root, extra="": listed(own, str(tmp_path / "root")))
    _a_saved_figure(ed._fig_dir, "old", 1000)
    _a_saved_figure(ed._fig_dir, "older", 500)
    _a_saved_figure(str(tmp_path / "root" / "other"), "new", 2000)
    ed.open_quick()
    names = lambda: [b.name for b in ed.qs_gallery.objects]  # noqa: E731
    assert names() == ["new", "old"] and ed.qs_more.visible
    assert list(ed.qs_where.options)[0] == quick.ALL_FOLDERS
    ed.qs_more.clicks += 1
    assert names() == ["new", "old", "older"] and not ed.qs_more.visible
    ed.qs_where.value = "other"
    assert names() == ["new"] and not ed.qs_more.visible
    ed.qs_where.value = "This run (own)"
    assert names() == ["old", "older"]
    ed.open_quick()  # (opens on them all again)
    assert ed.qs_where.value == "" and names() == ["new", "old"]
    ed.quick.hide()
    assert names() == []


def test_gallery_with_nothing_saved(ed, tmp_path, monkeypatch):
    from cm1view.figures import quick
    monkeypatch.setattr(ed, "_fig_dir", str(tmp_path / "own"))
    listed = quick.saved_list
    monkeypatch.setattr(quick, "saved_list",
                        lambda own, root, extra="": listed(own, str(tmp_path / "none")))
    ed.open_quick()
    assert ed.qs_none.visible and not ed.qs_where.visible and ed.qs_gallery.objects == []
    ed.quick.hide()


def test_thumbnails_of_older_figures_and_redrawn_images(tmp_path):
    import os
    from PIL import Image
    from cm1view.figures import spec as fg
    from cm1view.figures.export import make_thumb, saved_thumb
    spec = _a_saved_figure(str(tmp_path), "a", 1000)
    assert saved_thumb(spec) is None  # none yet: made from the image, and kept
    assert make_thumb(spec) == saved_thumb(spec)
    with Image.open(fg.thumb_path(spec)) as im:
        assert max(im.size) == fg.THUMB_PX
    png = str(tmp_path / "a.png")
    later = os.path.getmtime(fg.thumb_path(spec)) + 10
    os.utime(png, (later, later))
    assert saved_thumb(spec) is None  # a newer image (a script redrew it): made anew
    os.remove(png)
    os.remove(fg.thumb_path(spec))
    assert make_thumb(spec) is None and saved_thumb(spec) is None  # e.g. only a PDF
    with open(png, "w") as f:
        f.write("not an image")
    assert make_thumb(spec) is None


def test_a_thumbnail_for_a_closed_dialog_is_dropped(ed, tmp_path):
    import panel as pn
    from cm1view.figures import quick
    spec = _a_saved_figure(str(tmp_path), "a", 1000)
    b = pn.widgets.Button(name="a", stylesheets=[quick._thumb_css()])
    gen = ed._gallery_gen
    ed._gallery_clear()
    ed._thumb_job(b, spec, gen)
    ed._thumb_show(b, b"png", gen)
    assert "base64" not in b.stylesheets[0]


def test_a_series_no_longer_shown_stops(ed, monkeypatch):
    """A series job whose recipe the figure no longer needs (e.g. its region changed
    from around the storm to the whole domain) stops, and one queued behind another
    does not start; both start again (from the times kept) when needed again."""
    from cm1view.figures import render
    calls = []

    def compute(run, F, recipe, ds, centers, storm, on_result=None, cancelled=None):
        calls.append(recipe["region"])
        ed.data.ser_live = set()  # (the figure changed meanwhile)
        assert cancelled()
        return ds, {}

    monkeypatch.setattr(render.ser, "compute", compute)
    old, new = ("p", "storm", ""), ("p", "domain", "")
    ed.data.ser_state[old] = "running"
    ed.data.ser_live = {new}  # queued, not needed by the time it is reached: not started
    ed.data.ser_compute(old, ed.run, ed.F, dict(region="track"), None, None, None, "w")
    assert calls == [] and old not in ed.data.ser_state
    ed.data.ser_state[new] = "running"
    ed.data.ser_live = {new}  # started, then no longer needed: stopped, to start again
    ed.data.ser_compute(new, ed.run, ed.F, dict(region="domain"), None, None, None, "w")
    assert calls == ["domain"] and new not in ed.data.ser_state
    assert not ed.series_pending()


def test_time_windows_stop_for_a_newer_preview(ed):
    from cm1view.core import azim, joint
    ts = list(range(len(ed.run.times)))
    stop = lambda: True  # noqa: E731
    assert joint.compute(ed.run, ed.F, dict(field="winterp"), ts, cancelled=stop) is None
    r = azim.normalize(ed._new_azim_recipe())
    assert azim.compute(ed.run, ed.F, r, ts, {}, {}, cancelled=stop) is None


def test_time_height_range_is_the_layer():
    import xarray as xr
    from types import SimpleNamespace
    from cm1view.figures import spec as fg
    z = np.arange(0.125, 10.0, 0.25)  # (level centres of a 0–10 km layer)
    ds = xr.Dataset(dict(computed=("t", np.ones(3, dtype=int)), value=("t", np.zeros(3)),
                         profile=(("t", "z"), np.ones((3, z.size))), z=("z", z)))
    run = SimpleNamespace(times=[0.0, 60.0, 120.0])
    ent = dict(recipe=dict(z0=0.0, z1=10.0), op="")
    d = fg.th_panel(run, ds, ent, dict(ts=dict(zmin=None, zmax=None)))
    assert d["ylim"] == (0.0, 10.0)  # (not 0.125–9.875: the 10 km tick shows)
    d = fg.th_panel(run, ds, ent, dict(ts=dict(zmin=2.0, zmax=8.0)))
    assert d["ylim"] == (2.0, 8.0)


def test_number_boxes_round_float_tails():
    from cm1view.viewer.numinput import FloatInput, tidy
    w = FloatInput(name="x", value=float(np.float32(0.01)), step=0.001)
    assert w.value == 0.01
    w._process_events({"value": 0.008 + 0.001})  # (the arrows' step, in the browser)
    assert w.value == 0.009 and w.get_root().value == 0.009
    w.value = float(np.float32(0.3))
    assert w.value == 0.3
    assert tidy(None) is None and tidy(123456.5) == 123456.5


def test_sounding_table_lists_every_parameter(ed):
    from cm1view.figures import draw as figdraw
    ed.from_soundings()
    keys = [k for k, _, _ in figdraw.SND_PARAMS]
    assert sorted(ed.sk["table"].options.values()) == sorted(keys)
    ed.sk["table"].value = ["sbcape", "sbcin", "mucin", "shear01"]
    spec, data, fig = render(ed)
    par = data[0]["N0_par"]
    assert par.size == len(keys)
    assert np.isfinite(par[keys.index("sbcin")]) and par[keys.index("sbcin")] <= 0.0
    table = next(t for a in fig.axes for t in a.tables)
    heads = [c.get_text().get_text() for (r, _), c in table.get_celld().items() if r == 0]
    assert any(h.startswith("SBCIN") for h in heads)
    data[0]["N0_par"] = par[:11]  # (figure data saved before the newer parameters)
    table = next(t for a in figdraw.draw(spec, data).axes for t in a.tables)
    row = {c: cell.get_text().get_text() for (r, c), cell in table.get_celld().items()
           if r == 1}
    assert row[0] != "–" and row[1] == "–"


def test_sounding_storm_motion_ring_and_inset(ed):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    ed.from_soundings()
    ed.sk["srh"].value = "1"
    spec, data, fig = render(ed)
    d = data[0]
    assert np.allclose(d["N0_storm"], d["N0_rm"])
    srh_rm = d["N0_srh1"]
    ed.sk["storm"].value = "lm"  # the SRH follows the storm motion
    spec, data, fig = render(ed)
    assert np.allclose(data[0]["N0_storm"], data[0]["N0_lm"])
    assert data[0]["N0_srh1"] != srh_rm
    assert not ed.sk["storm_u"].visible
    ed.sk["storm"].value = "custom"
    assert ed.sk["storm_u"].visible
    ed.sk["storm_u"].value, ed.sk["storm_v"].value = 5.0, -3.0
    spec, data, fig = render(ed)
    assert np.allclose(data[0]["N0_storm"], [5.0, -3.0])
    skew = next(a for a in fig.axes if a.child_axes)
    hodo = next(c for c in skew.child_axes if getattr(c, "_cv_hodo", False))
    assert any(ln.get_marker() == "o" and np.allclose(ln.get_xydata()[0], [5.0, -3.0])
               for ln in hodo.get_lines())  # the ring
    for where, left in (("upper left", True), ("upper right", False)):
        ed.sk["inset_loc"].value = where
        spec, data, fig = render(ed)
        FigureCanvasAgg(fig).draw()
        skew = next(a for a in fig.axes if a.child_axes)
        hx = skew.child_axes[0].get_window_extent()
        mid = 0.5 * (skew.get_window_extent().x0 + skew.get_window_extent().x1)
        assert (hx.x1 < mid) == left
    assert not ed.sk["inset_x"].visible
    ed.sk["inset_loc"].value = "custom"
    assert ed.sk["inset_x"].visible and ed.sk["inset_y"].visible
    ed.sk["inset_x"].value, ed.sk["inset_y"].value, ed.sk["inset_size"].value = 0.0, 0.0, 0.5
    spec, data, fig = render(ed)
    FigureCanvasAgg(fig).draw()
    skew = next(a for a in fig.axes if a.child_axes)
    sx, hx = skew.get_window_extent(), skew.child_axes[0].get_window_extent()
    assert np.isclose(hx.x0, sx.x0, atol=1) and np.isclose(hx.y0, sx.y0, atol=1)
    assert np.isclose(hx.width, 0.5 * sx.width, rtol=0.02) or \
        np.isclose(hx.height, 0.5 * 0.39 / 0.37 * sx.height, rtol=0.02)  # (equal aspect)
    # the view: square, about the origin, a custom centre, or fit to the traces
    hodo = next(c for c in skew.child_axes if getattr(c, "_cv_hodo", False))
    assert np.allclose(hodo.get_xlim(), (-40, 40)) and np.allclose(hodo.get_ylim(), (-40, 40))
    assert not ed.sk["hodo_cu"].visible
    ed.sk["hodo_center"].value = "custom"
    assert ed.sk["hodo_cu"].visible and ed.sk["hodo_max"].visible
    ed.sk["hodo_cu"].value, ed.sk["hodo_cv"].value, ed.sk["hodo_max"].value = 10.0, 5.0, 20.0
    spec, data, fig = render(ed)
    hodo = next(c for c in next(a for a in fig.axes if a.child_axes).child_axes
                if getattr(c, "_cv_hodo", False))
    assert np.allclose(hodo.get_xlim(), (-10, 30)) and np.allclose(hodo.get_ylim(), (-15, 25))
    ed.sk["hodo_center"].value = "fit"
    assert not ed.sk["hodo_max"].visible
    spec, data, fig = render(ed)
    hodo = next(c for c in next(a for a in fig.axes if a.child_axes).child_axes
                if getattr(c, "_cv_hodo", False))
    (x0, x1), (y0, y1) = hodo.get_xlim(), hodo.get_ylim()
    assert np.isclose(x1 - x0, y1 - y0)  # (square)
    z, u, v = (np.asarray(data[0][f"N0_{k}"], float) for k in ("z", "u", "v"))
    sel = z <= 9.0
    assert x0 <= u[sel].min() and u[sel].max() <= x1
    assert y0 <= v[sel].min() and v[sel].max() <= y1


def test_grid_layout_places_parts_and_sizes_cells():
    from cm1view.figures import draw as figdraw
    tall, wide = dict(size=[8.0, 8.0]), dict(size=[6.0, 4.0])
    g = figdraw.grid_layout([dict(tall, place=[0, 0, 2, 1]), wide, wide],
                            dict(rows=2, cols=2))
    assert g["places"] == [[0, 0, 2, 1], [0, 1, 1, 1], [1, 1, 1, 1]]  # (the free cells)
    assert g["widths"] == [8.0, 6.0] and g["heights"] == [4.0, 4.0]
    assert g["width_ratios"] == g["widths"] and figdraw.grid_overlaps(g["places"]) == []
    g = figdraw.grid_layout([dict(wide, place=[5, 5, 3, 3]), wide],  # (kept within; more rows)
                            dict(rows=1, cols=1, widths=[2.0], heights=[1.0, 2.0, 3.0]))
    assert g["places"] == [[0, 0, 1, 1], [1, 0, 1, 1]] and g["rows"] == 2
    assert g["width_ratios"] == [2.0] and g["height_ratios"] == g["heights"]  # (3 for 2 rows)
    g = figdraw.grid_layout([wide, wide], dict(rows=1, cols=1, heights=[1.0, 2.0]))
    assert g["rows"] == 2 and g["height_ratios"] == [1.0, 2.0]  # (they fit the rows it grew to)
    assert figdraw.grid_overlaps([[0, 0, 2, 1], [1, 0, 1, 1], [0, 1, 1, 1]]) == [(0, 1)]


