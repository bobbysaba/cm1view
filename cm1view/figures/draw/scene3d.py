"""The rendered 3D scene of the figure tool: PyVista (VTK) off-screen, from the arrays of
core.volume3d.build_scene.

render() makes the picture only (RGBA, no text); a scene panel (scene_panel, then
finish_scenes once the figure is laid out) puts it in a matplotlib axes and adds the
legend, colorbars and axis ticks there, placing the ticks with the projection render()
also returns (to_pixels).

A scene panel's data (scene_data: flat names, so they go in the figure's .npz)
  nmesh, M<n>_x, M<n>_y, M<n>_z, M<n>_f   isosurface n: vertices (km) and triangles
  M<n>_color, M<n>_op, M<n>_name          its colour, opacity and legend text
  G_x, G_y, G_a, G_lo, G_hi, G_cmap, G_rev, G_title   the floor (when on)
  nvec, V<n>_x, V<n>_y, V<n>_z, V<n>_color, V<n>_name  vector plane n
  S_x, S_y, S_z, S_w, S_n, S_by, S_seed, S_seed_z, S_name  the streamlines (when on)
  box, ztop     the region (km) the scene was computed over
Redrawing a scene (its script too) needs pyvista.

Coordinates: x, y in km, z in km times the vertical exaggeration (the geometry is
scaled before shading, so the normals and lighting see the exaggerated shape).  Camera
positions in a spec are in world km (z not exaggerated)."""

import numpy as np
import matplotlib
from matplotlib.cm import ScalarMappable
from matplotlib.colors import BoundaryNorm, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator

from .base import colormap, font_size

CAMERA = dict(preset="oblique", azimuth=None, elevation=None, zoom=1.0,
              projection="perspective", view_angle=30.0,
              position=None, focal=None, up=None)
# background None: the figure's ("none": transparent); floor_bar / stream_bar: where
# their colorbars go (bottom, right, left, top or none)
LOOK = dict(lighting="kit", background=None, outline=True, outline_color="#475569",
            tube=1.0, arrows="glyph", shine=0.3, ambient=0.25, seed_box=True,
            peels=12, aa=True, ticks=True, labels=["x (km)", "y (km)", "z (km)"],
            legend=True, floor_bar="bottom", stream_bar="right")
SCENE_MAX_PX = 6000  # (the longer side of a rendered picture)

# compass bearing the viewer stands toward from the centre (deg, 0 = north, 90 = east)
# and elevation above the horizon: the viewer's camera presets (volume3d.CAMERAS)
PRESETS = {"oblique": (139.2, 21.4), "top": (180.0, 90.0), "south": (180.0, 6.8),
           "north": (0.0, 6.8), "west": (270.0, 6.8), "east": (90.0, 6.8)}


def look_of(scene):
    return {**LOOK, **(scene.get("look") or {})}


def camera_of(scene):
    return {**CAMERA, **(scene.get("camera") or {})}


def stream_values(stream):
    """The streamlines' colour values per point: w or height, by stream["color_by"]."""
    c = stream["w"] if stream["color_by"] == "w" else stream["z"]
    return np.nan_to_num(np.asarray(c, np.float64), nan=0.0)


def stream_style(stream, ztop):
    """(cmap, lo, hi, label) of the streamline colours, as in the viewer."""
    if stream["color_by"] == "w":
        c = stream_values(stream)
        m = float(max(np.percentile(np.abs(c), 99), 1.0)) if c.size else 1.0
        return "RdBu_r", -m, m, "w (m/s)"
    return "viridis", 0.0, float(ztop), "z (km)"


def floor_norm(ground):
    """(colormap, norm) of the floor's colours: the field's colormap over its range;
    the NWS reflectivity steps every 5 dBZ from 0."""
    cm = colormap(ground["cmap"], bool(ground["rev"]))
    if ground["cmap"] == "reflectivity":
        return cm, BoundaryNorm(np.arange(cm.N + 1) * 5.0, cm.N, clip=True)
    return cm, Normalize(float(ground["lo"]), float(ground["hi"]), clip=True)


def floor_rgb(ground):
    """(ny, nx, 3) floor colours in 0-1 from the field's matplotlib colormap; NaN and
    the reflectivity map's transparent first step light grey."""
    cm, norm = floor_norm(ground)
    a = np.asarray(ground["a"], np.float64)
    rgba = cm(norm(np.where(np.isfinite(a), a, float(ground["lo"]))))
    rgb = rgba[..., :3] * rgba[..., 3:] + 0.85 * (1 - rgba[..., 3:])
    rgb[~np.isfinite(a)] = 0.85
    return rgb


def scene_bounds(scene):
    x0, x1, y0, y1 = scene["box"]
    return (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), 0.0,
            float(scene["ztop"]) * float(scene["exag"]))


def camera_pose(scene, aspect=4 / 3):
    """(position, focal, up, view_angle, parallel, parallel_scale) in display
    coordinates.  An explicit position + focal in the spec wins; otherwise a preset,
    its azimuth/elevation overridden when given, at the distance where the whole region
    box fits (divided by zoom)."""
    c = camera_of(scene)
    ex = float(scene["exag"])
    b = scene_bounds(scene)
    ctr = np.array([(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2])
    R = 0.5 * float(np.linalg.norm([b[1] - b[0], b[3] - b[2], b[5] - b[4]]))
    zoom = max(float(c["zoom"] or 1.0), 1e-3)
    va = float(c["view_angle"] or 30.0)
    par = c["projection"] == "orthographic"
    if c["position"] is not None and c["focal"] is not None:
        pos = np.array(c["position"], float) * [1, 1, ex]
        foc = np.array(c["focal"], float) * [1, 1, ex]
        up = np.array(c["up"] if c["up"] is not None else (0, 0, 1), float)
        return pos, foc, up, va, par, R / zoom
    az0, el0 = PRESETS.get(c["preset"], PRESETS["oblique"])
    az = np.radians(az0 if c["azimuth"] is None else float(c["azimuth"]))
    el = np.radians(el0 if c["elevation"] is None else float(c["elevation"]))
    el = np.clip(el, np.radians(-89.9), np.radians(90.0))
    d = np.array([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)])
    # the sphere round the box fits the narrower of the two view angles
    half = np.radians(va) / 2
    if aspect < 1:
        half = np.arctan(np.tan(half) * aspect)
    dist = R / np.sin(half) / zoom
    if abs(np.sin(el)) > 0.999:  # straight down: north up the picture
        up = np.array([-np.sin(az), -np.cos(az), 0.0])
    else:
        up = np.array([0.0, 0.0, 1.0])
    return ctr + dist * d, ctr, up, va, par, R / zoom


def orbit_camera(cam, deg):
    """CAMERA keys `cam` turned deg degrees round the vertical through the focal point
    (compass sense: 90 takes a camera standing north to the east): an explicit position
    turns about the focal point, else the azimuth (the preset's when blank) grows."""
    c = {**CAMERA, **(cam or {})}
    if not deg:
        return c
    a = np.radians(float(deg))
    rot = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
    if c["position"] is not None and c["focal"] is not None:
        p, f = np.array(c["position"], float), np.array(c["focal"], float)
        p[:2] = f[:2] + rot @ (p[:2] - f[:2])
        c["position"] = [float(v) for v in p]
        if c["up"] is not None:
            u = np.array(c["up"], float)
            u[:2] = rot @ u[:2]
            c["up"] = [float(v) for v in u]
        return c
    az0 = PRESETS.get(c["preset"], PRESETS["oblique"])[0]
    az = az0 if c["azimuth"] is None else float(c["azimuth"])
    c["azimuth"] = float((az + float(deg)) % 360.0)
    return c


PLOTLY_EYE = 2.06  # (the length of the viewer's oblique eye vector: zoom 1)


def camera_from_plotly(cam):
    """CAMERA keys (azimuth, elevation, zoom, projection) of a plotly scene camera (the
    viewer's 3D view: {"eye": {x, y, z}, "projection": {"type"}}), or {} without an
    eye.  The viewer's aspect ratio is the region's, with the exaggeration in z, so its
    eye points the same way in the picture's display coordinates; a pan (its centre)
    is left out."""
    eye = (cam or {}).get("eye") or {}
    try:
        e = np.array([float(eye[k]) for k in "xyz"])
    except (KeyError, TypeError, ValueError):
        return {}
    n = float(np.linalg.norm(e))
    if not np.isfinite(n) or n < 1e-9:
        return {}
    az = float(np.degrees(np.arctan2(e[0], e[1]))) % 360.0
    el = float(np.degrees(np.arctan2(e[2], np.hypot(e[0], e[1]))))
    proj = ((cam.get("projection") or {}).get("type") or "perspective")
    return dict(azimuth=round(az, 1), elevation=round(el, 1),
                zoom=round(PLOTLY_EYE / n, 2),
                projection="orthographic" if proj == "orthographic" else "perspective")


def _polylines(x, y, z, scalars=None):
    """PolyData of NaN-separated polylines (pieces under 2 points dropped)."""
    import pyvista as pv

    x, y, z = (np.asarray(a, np.float64) for a in (x, y, z))
    idx = np.flatnonzero(np.isfinite(x) & np.isfinite(y) & np.isfinite(z))
    if idx.size < 2:
        return None
    pieces = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    pts = np.stack([x[idx], y[idx], z[idx]], axis=1)
    pos = {int(i): k for k, i in enumerate(idx)}
    cells = []
    for p in pieces:
        if len(p) >= 2:
            cells += [len(p)] + [pos[int(i)] for i in p]
    if not cells:
        return None
    pd = pv.PolyData(pts, lines=np.array(cells, dtype=np.int64))
    if scalars is not None:
        pd["s"] = np.asarray(scalars, np.float64)[idx]
    return pd


def _arrows(vec, ex, radius, style):
    """One vector plane: 3D arrows (glyphs scaled by length) or tubes along the
    viewer's shaft + V-head polylines (constant width)."""
    import pyvista as pv

    X, Y = np.asarray(vec["x"], np.float64), np.asarray(vec["y"], np.float64)
    z = float(vec["z"]) * ex
    if style == "lines":
        pd = _polylines(X, Y, np.full_like(X, z))
        return None if pd is None else pd.tube(radius=radius, n_sides=8)
    # surface_vectors: 7 entries per arrow, tail then tip first
    tail = np.stack([X[0::7], Y[0::7]], axis=1)
    tip = np.stack([X[1::7], Y[1::7]], axis=1)
    if not len(tail):
        return None
    pts = np.column_stack([tail, np.full(len(tail), z)])
    pd = pv.PolyData(pts)
    pd["v"] = np.column_stack([tip - tail, np.zeros(len(tail))])
    geom = pv.Arrow(start=(0, 0, 0), direction=(1, 0, 0), tip_length=0.32,
                    tip_radius=0.11, shaft_radius=0.04, tip_resolution=16,
                    shaft_resolution=12)
    return pd.glyph(orient="v", scale="v", factor=1.0, geom=geom)


def render(arrays, scene, size_px):
    """Render the scene off-screen.

    arrays: build_scene's dict (meshes, ground, vecs, stream).  scene: the figure's
    scene3d block: box, ztop, exag, camera (CAMERA keys), look (LOOK keys).
    size_px: (width, height).

    Returns (rgba, proj): an (h, w, 4) uint8 image (transparent where nothing is drawn
    when look["background"] is "transparent") and the 4x4 matrix taking display
    coordinates to normalized device coordinates (see to_pixels)."""
    import pyvista as pv

    w, h = (int(v) for v in size_px)
    lk = look_of(scene)
    ex = float(scene["exag"])
    b = scene_bounds(scene)
    width = max(b[1] - b[0], b[3] - b[2], 1e-6)
    radius = 0.0015 * width * float(lk["tube"] or 1.0)
    lw = max(1.0, min(w, h) / 600.0)  # pixel line widths grow with the picture
    lights = {"kit": "light kit", "three": "three lights"}.get(lk["lighting"], "none")
    pl = pv.Plotter(off_screen=True, window_size=(w, h), lighting=lights)
    try:
        if lk["lighting"] == "head":
            pl.add_light(pv.Light(light_type="headlight"))
        transparent = lk["background"] in ("transparent", "none")
        pl.set_background("white" if transparent else lk["background"] or "white")

        g = arrays.get("ground")
        if g is not None:
            X, Y = np.meshgrid(np.asarray(g["x"], float), np.asarray(g["y"], float))
            grid = pv.StructuredGrid(X, Y, np.zeros_like(X))
            rgb = floor_rgb(g)  # (ny, nx, 3), StructuredGrid points in Fortran order
            grid["rgb"] = np.stack([rgb[..., k].ravel(order="F") for k in range(3)], axis=1)
            pl.add_mesh(grid, scalars="rgb", rgb=True, lighting=False,
                        show_scalar_bar=False)

        for m in arrays.get("meshes") or []:
            pts = np.column_stack([m["x"], m["y"], np.asarray(m["z"], np.float64) * ex])
            f = np.asarray(m["faces"], np.int64)
            faces = np.column_stack([np.full(len(f), 3, np.int64), f]).ravel()
            pl.add_mesh(pv.PolyData(pts, faces=faces), color=m["color"],
                        opacity=float(m["opacity"]), smooth_shading=True,
                        ambient=float(lk["ambient"]), diffuse=0.8,
                        specular=float(lk["shine"]), specular_power=20.0)

        for vec in arrays.get("vecs") or []:
            a = _arrows(vec, ex, radius, lk["arrows"])
            if a is not None:
                pl.add_mesh(a, color=vec["color"], smooth_shading=True,
                            ambient=float(lk["ambient"]), diffuse=0.8, specular=0.1)

        s = arrays.get("stream")
        if s is not None:
            cmap, lo, hi, _ = stream_style(s, scene["ztop"])
            pd = _polylines(s["x"], s["y"], np.asarray(s["z"], np.float64) * ex,
                            stream_values(s))
            if pd is not None:
                pl.add_mesh(pd.tube(radius=radius, n_sides=10), scalars="s", cmap=cmap,
                            clim=(lo, hi), smooth_shading=True, show_scalar_bar=False,
                            ambient=float(lk["ambient"]), diffuse=0.8, specular=0.15)
            if lk["seed_box"] and s.get("seed_box") is not None:
                s0, s1, t0, t1 = s["seed_box"]
                zs = float(s["seed_z"]) * ex
                ring = pv.lines_from_points(np.array(
                    [[s0, t0, zs], [s1, t0, zs], [s1, t1, zs], [s0, t1, zs], [s0, t0, zs]]))
                pl.add_mesh(ring, color="#64748b", line_width=lw)

        if lk["outline"]:
            pl.add_mesh(pv.Box(bounds=b).outline(), color=lk["outline_color"],
                        line_width=lw)

        pos, foc, up, va, par, ps = camera_pose(scene, w / h)
        cam = pl.camera
        cam.position, cam.focal_point, cam.up = tuple(pos), tuple(foc), tuple(up)
        cam.view_angle = va
        if par:
            pl.enable_parallel_projection()
            cam.parallel_scale = ps
        pl.reset_camera_clipping_range()

        if int(lk["peels"] or 0) > 0:  # nested translucent surfaces in the right order
            pl.enable_depth_peeling(number_of_peels=int(lk["peels"]), occlusion_ratio=0.0)
        if lk["aa"]:
            pl.enable_anti_aliasing("ssaa")

        img = pl.screenshot(transparent_background=transparent, return_img=True)
        proj = np.array([[cam.GetCompositeProjectionTransformMatrix(w / h, -1, 1)
                          .GetElement(i, j) for j in range(4)] for i in range(4)])
    finally:
        pl.close()
    img = np.asarray(img, np.uint8)
    if img.shape[2] == 3:
        img = np.concatenate([img, np.full(img.shape[:2] + (1,), 255, np.uint8)], axis=2)
    return img, proj


def to_pixels(proj, pts, size_px, exag=1.0):
    """Image pixel coordinates (x right, y down from the top) of world points (km, z
    not exaggerated) under render()'s projection; NaN behind the camera."""
    w, h = size_px
    p = np.asarray(pts, np.float64).reshape(-1, 3) * [1, 1, exag]
    q = np.column_stack([p, np.ones(len(p))]) @ np.asarray(proj).T
    with np.errstate(divide="ignore", invalid="ignore"):
        ndc = q[:, :3] / q[:, 3:4]
    ndc[q[:, 3] <= 0] = np.nan
    return np.column_stack([(ndc[:, 0] + 1) / 2 * w, (1 - ndc[:, 1]) / 2 * h])


def scene_data(arrays, box, ztop):
    """A scene panel's data (flat names: see the module notes) of build_scene's arrays,
    computed over region box (x0, x1, y0, y1 km) up to ztop (km)."""
    f32 = lambda a: np.asarray(a, np.float32)  # noqa: E731
    meshes, vecs = arrays.get("meshes") or [], arrays.get("vecs") or []
    d = dict(nmesh=len(meshes), nvec=len(vecs), box=np.asarray(box, np.float64),
             ztop=float(ztop))
    for n, m in enumerate(meshes):
        d.update({f"M{n}_x": f32(m["x"]), f"M{n}_y": f32(m["y"]), f"M{n}_z": f32(m["z"]),
                  f"M{n}_f": np.asarray(m["faces"], np.int32), f"M{n}_color": str(m["color"]),
                  f"M{n}_op": float(m["opacity"]), f"M{n}_name": str(m.get("name", ""))})
    g = arrays.get("ground")
    if g is not None:
        d.update(G_x=np.asarray(g["x"], np.float64), G_y=np.asarray(g["y"], np.float64),
                 G_a=f32(g["a"]), G_lo=float(g["lo"]), G_hi=float(g["hi"]),
                 G_cmap=str(g["cmap"]), G_rev=int(bool(g["rev"])),
                 G_title=str(g.get("title", "")))
    for n, v in enumerate(vecs):
        d.update({f"V{n}_x": f32(v["x"]), f"V{n}_y": f32(v["y"]), f"V{n}_z": float(v["z"]),
                  f"V{n}_color": str(v["color"]), f"V{n}_name": str(v.get("name", ""))})
    s = arrays.get("stream")
    if s is not None:
        d.update(S_x=f32(s["x"]), S_y=f32(s["y"]), S_z=f32(s["z"]), S_w=f32(s["w"]),
                 S_n=int(s.get("n", 0)), S_by=str(s["color_by"]),
                 S_seed_z=float(s.get("seed_z", 0.0)), S_name=str(s.get("name", "")))
        if s.get("seed_box") is not None:
            d["S_seed"] = np.asarray(s["seed_box"], np.float64)
    return d


def scene_arrays(d):
    """build_scene's arrays (as render() takes them) of a scene panel's data."""
    meshes = [dict(x=d[f"M{n}_x"], y=d[f"M{n}_y"], z=d[f"M{n}_z"], faces=d[f"M{n}_f"],
                   color=str(d[f"M{n}_color"]), opacity=float(d[f"M{n}_op"]),
                   name=str(d.get(f"M{n}_name", ""))) for n in range(int(d.get("nmesh", 0)))]
    ground = None
    if "G_a" in d:
        ground = dict(x=d["G_x"], y=d["G_y"], a=np.asarray(d["G_a"], np.float64),
                      lo=float(d["G_lo"]), hi=float(d["G_hi"]), cmap=str(d["G_cmap"]),
                      rev=bool(d["G_rev"]), title=str(d.get("G_title", "")))
    vecs = [dict(x=d[f"V{n}_x"], y=d[f"V{n}_y"], z=float(d[f"V{n}_z"]),
                 color=str(d[f"V{n}_color"]), name=str(d.get(f"V{n}_name", "")))
            for n in range(int(d.get("nvec", 0)))]
    stream = None
    if "S_x" in d:
        stream = dict(x=d["S_x"], y=d["S_y"], z=d["S_z"], w=d["S_w"], n=int(d["S_n"]),
                      color_by=str(d["S_by"]), seed_z=float(d["S_seed_z"]),
                      seed_box=tuple(float(v) for v in d["S_seed"]) if "S_seed" in d else None,
                      name=str(d.get("S_name", "")))
    return dict(meshes=meshes, ground=ground, vecs=vecs, stream=stream)


def scene_spec(d, V):
    """The scene block a panel renders with: the panel view's "scene3d" (its camera,
    look, exaggeration), the region and top the data was computed over, and the
    figure's background where the look has none of its own."""
    sc = dict(V.get("scene3d") or {})
    if "box" in d:
        sc["box"] = [float(v) for v in np.asarray(d["box"]).ravel()]
    if "ztop" in d:
        sc["ztop"] = float(d["ztop"])
    sc.setdefault("exag", 1.0)
    if "shift" in d:  # (a region following the track: an explicit camera follows too)
        dx, dy = (float(v) for v in np.asarray(d["shift"]).ravel())
        cam = camera_of(sc)
        if cam["position"] is not None and cam["focal"] is not None:
            sc["camera"] = dict(cam, **{k: [float(cam[k][0]) + dx, float(cam[k][1]) + dy,
                                            float(cam[k][2])] for k in ("position", "focal")})
    lk = look_of(sc)
    if not lk["background"]:
        bg = V.get("background", "white")
        lk["background"] = "transparent" if bg == "none" else bg
    return dict(sc, look=lk)


def scene_panel(fig, ax, d, V, fs, legend):
    """A 3D scene panel before its picture: no axes frame, the colorbars of the floor
    and the streamlines, and the legend entries (into `legend`) of the isosurfaces,
    vectors and streamlines.  finish_scenes renders the picture once the figure is laid
    out, at the size the axes then have."""
    sc = scene_spec(d, V)
    lk, arrays = sc["look"], scene_arrays(d)
    ax.set_axis_off()
    bars = []
    g, s = arrays["ground"], arrays["stream"]
    if g is not None and lk["floor_bar"] != "none":
        cm, norm = floor_norm(g)
        bars.append((ScalarMappable(norm, cm), lk["floor_bar"], g["title"]))
    if s is not None and lk["stream_bar"] != "none":
        name, lo, hi, lab = stream_style(s, sc["ztop"])
        bars.append((ScalarMappable(Normalize(lo, hi), colormap(name)), lk["stream_bar"], lab))
    for m, loc, lab in bars:
        c = fig.colorbar(m, ax=ax, location=loc, shrink=0.6, pad=0.02, aspect=30)
        c.set_label(lab, fontsize=font_size(V, "label"))
    if lk["legend"]:
        for m in arrays["meshes"]:
            legend[m["name"]] = Patch(facecolor=m["color"], edgecolor=m["color"],
                                      alpha=max(float(m["opacity"]), 0.15))
        for v in arrays["vecs"]:
            legend[v["name"]] = Line2D([], [], color=v["color"], lw=1.5)
        if s is not None:
            name, *_ = stream_style(s, sc["ztop"])
            legend[s["name"] or "streamlines"] = Line2D([], [], color=colormap(name)(0.85),
                                                        lw=2.0)
    ax._cv_scene = (arrays, sc, font_size(V, "tick"), font_size(V, "label"))


def scene_dpi(spec):
    """Pixels per inch of a scene's picture: spec["scene3d"]["dpi"] (a preview's), else
    the export's."""
    return float((spec.get("scene3d") or {}).get("dpi") or
                 (spec.get("export") or {}).get("dpi", 250))


def finish_scenes(fig, dpi):
    """Render the pictures of fig's scene panels (scene_panel) at the size their axes
    have in the laid-out figure, dpi pixels per inch, and draw their axis ticks."""
    axs = [ax for ax in fig.axes if getattr(ax, "_cv_scene", None)]
    if not axs:
        return
    root = fig.get_figure(root=True)
    root.draw_without_rendering()  # (the layout: where the axes are)
    for ax in axs:
        arrays, sc, tfs, lfs = ax._cv_scene
        ax._cv_scene = None
        bb = ax.get_window_extent()
        w, h = bb.width / root.dpi * dpi, bb.height / root.dpi * dpi
        k = min(1.0, SCENE_MAX_PX / max(w, h, 1.0))
        w, h = max(16, int(round(w * k))), max(16, int(round(h * k)))
        try:
            img, proj = render(arrays, sc, (w, h))
        except ImportError:
            ax.text(0.5, 0.5, "drawing a 3D scene needs pyvista\n(pip install pyvista)",
                    transform=ax.transAxes, ha="center", va="center", color="0.4")
            continue
        ax.imshow(img, extent=(0, w, h, 0), interpolation="antialiased", zorder=0)
        ax.set_xlim(0, w)
        ax.set_ylim(h, 0)
        ax.set_aspect("equal")
        ax._cv_proj = (proj, (w, h), float(sc["exag"]))  # (world km -> picture pixels)
        if sc["look"]["ticks"]:
            scene_ticks(ax, proj, (w, h), sc, tfs, lfs)


def _edge_dir(proj, size, ex, p, out):
    """Unit direction in the picture (x right, y down) from world point p towards p +
    out (km), or None."""
    a, b = to_pixels(proj, [p, np.add(p, out)], size, ex)
    v = b - a
    n = float(np.hypot(*v))
    return None if not np.isfinite(n) or n < 1e-9 else v / n


def scene_ticks(ax, proj, size, sc, tfs, lfs):
    """Axis ticks of a scene picture: x along the lower of the south and north floor
    edges, y along the lower of the west and east ones, z up the leftmost corner; each
    tick and label pointing away from the box.  An axis seen end-on is left out."""
    w, h = size
    ex = float(sc["exag"])
    x0, x1, y0, y1, _, _ = scene_bounds(dict(sc, exag=1.0))
    zt = float(sc["ztop"])
    xc, yc = (x0 + x1) / 2, (y0 + y1) / 2
    col = matplotlib.rcParams["xtick.color"]
    span = max(x1 - x0, y1 - y0, zt)
    L = 0.012 * max(w, h)  # tick length (picture pixels)

    def px(p):
        return to_pixels(proj, [p], size, ex)[0]

    def lower(cands):  # (lowest in the picture; nearly level: the leftmost)
        pts = [(px(mid), c) for mid, c in cands]
        pts = [(q, c) for q, c in pts if np.all(np.isfinite(q))]
        if not pts:
            return None
        top = max(q[1] for q, _ in pts)
        return min((q[0], c) for q, c in pts if q[1] >= top - 0.01 * h)[1]

    labels = list(sc["look"]["labels"]) + ["", "", ""]
    axes = []
    ye = lower([((xc, yy, 0), yy) for yy in (y0, y1)])
    if ye is not None:
        axes.append(((x0, ye, 0), (x1, ye, 0), (0, np.sign(ye - yc) or -1, 0), x0, x1,
                     labels[0]))
    xe = lower([((xx, yc, 0), xx) for xx in (x0, x1)])
    if xe is not None:
        axes.append(((xe, y0, 0), (xe, y1, 0), (np.sign(xe - xc) or -1, 0, 0), y0, y1,
                     labels[1]))
    corners = [(xx, yy) for xx in (x0, x1) for yy in (y0, y1)]
    q = [px((xx, yy, zt / 2)) for xx, yy in corners]
    ok = [k for k in range(4) if np.all(np.isfinite(q[k]))]
    if ok:
        xx, yy = corners[min(ok, key=lambda k: (q[k][0], -q[k][1]))]
        out = np.array([xx - xc, yy - yc, 0.0])
        out /= max(np.linalg.norm(out), 1e-9)
        axes.append(((xx, yy, 0), (xx, yy, zt), tuple(out), 0.0, zt, labels[2]))
    for a, b, out, lo, hi, title in axes:
        pa, pb = px(a), px(b)
        if not (np.all(np.isfinite(pa)) and np.all(np.isfinite(pb))) or \
                np.hypot(*(pb - pa)) < 0.08 * min(w, h):
            continue  # (end-on, or behind the camera)
        a, b = np.asarray(a, float), np.asarray(b, float)
        u = _edge_dir(proj, size, ex, (a + b) / 2, np.asarray(out) * 0.05 * span)
        if u is None:
            continue
        ha = "left" if u[0] > 0.35 else "right" if u[0] < -0.35 else "center"
        va = "top" if u[1] > 0.35 else "bottom" if u[1] < -0.35 else "center"
        z = b[2] > a[2]
        ticks = [v for v in MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]).tick_values(lo, hi)
                 if lo - 1e-9 <= v <= hi + 1e-9 and not (z and v <= lo)]  # (z: 0 is x's)
        width = 1
        for v in ticks:
            f = (v - lo) / (hi - lo) if hi > lo else 0.0
            p = px(a + f * (b - a))
            e = p + u * L
            ax.plot([p[0], e[0]], [p[1], e[1]], color=col, lw=0.8, clip_on=False)
            txt = f"{v:g}"
            width = max(width, len(txt))
            ax.annotate(txt, xy=e, xytext=(2 * u[0], -2 * u[1]), textcoords="offset points",
                        ha=ha, va=va, fontsize=tfs, color=col, annotation_clip=False)
        if title:
            m = px((a + b) / 2) + u * L
            off = 4 + tfs * (0.62 * width * abs(u[0]) + 1.25 * abs(u[1])) + 0.3 * lfs
            d = pb - pa
            ang = 90.0 if z else (float(np.degrees(np.arctan2(-d[1], d[0]))) + 90) % 180 - 90
            ax.annotate(title, xy=m, xytext=(off * u[0], -off * u[1]),
                        textcoords="offset points", ha="center", va="center",
                        rotation=ang, rotation_mode="anchor", fontsize=lfs, color=col,
                        annotation_clip=False)
