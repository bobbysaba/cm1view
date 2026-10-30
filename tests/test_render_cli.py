"""`cm1view render` (figures/batch.py): saved figures and templates drawn without the
viewer, as images, bundles and GIFs, as saved or for other runs."""
import os
import subprocess
import sys

import numpy as np
import pytest

from test_figure_render import _with_track_file, same


def _demo_spec(demo_root, t=2):
    """The default figure on the demo supercell (its track file), with no editor."""
    from cm1view.figures import spec as fg
    from cm1view.figures.render import FigureData
    fd = FigureData()
    run, F = fd.open_run(os.path.join(demo_root, "demo", "supercell"))
    return _with_track_file(fg.default_spec(run, F, t), demo_root), fd


def _saved(demo_root, tmp_path):
    """A figure saved with "+ script & data": (spec path, data path)."""
    from cm1view.figures import spec as fg
    spec, fd = _demo_spec(demo_root)
    out = fg.save_bundle(spec, fd.panel_data(spec), str(tmp_path / "saved" / "refl"))
    return out["spec"], out["data"]


def _npz(path):
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def render(*args):
    from cm1view.figures.batch import main
    return main([str(a) for a in args])


def test_render_as_saved_draws_the_same_data(demo_root, tmp_path):
    spec_path, data_path = _saved(demo_root, tmp_path)
    assert render(spec_path, "--bundle", "--out", tmp_path / "again" / "refl") == 0
    same(_npz(data_path), _npz(tmp_path / "again" / "_src" / "refl_data.npz"))
    # its image (or script) names it too; --out's extension sets the format
    img = tmp_path / "saved" / "refl.png"
    assert render(img, "--out", tmp_path / "again" / "refl.pdf", "--dpi", 60) == 0
    assert (tmp_path / "again" / "refl.pdf").stat().st_size > 0


def test_render_on_runs_like_applying_a_template(ed, demo_root, tmp_path):
    """--run draws the figure as the editor's Apply to this run would a template of it,
    and once per run with {run} in --out."""
    from cm1view.figures import batch, spec as fg
    from cm1view.figures.render import FigureData
    spec_path, data_path = _saved(demo_root, tmp_path)
    runs = [os.path.join(demo_root, "demo", r) for r in ("supercell", "supercell_weak")]
    out = tmp_path / "{run}" / "{name}.png"
    assert render(spec_path, "--run", *runs, "--out", out) == 0
    for r in runs:
        assert (tmp_path / os.path.basename(r) / "refl.png").is_file()
    # the same run at the saved times: the saved data
    assert render(spec_path, "--run", runs[0], "--bundle",
                  "--out", tmp_path / "same" / "refl") == 0
    same(_npz(data_path), _npz(tmp_path / "same" / "_src" / "refl_data.npz"))
    # a template, applied in the editor and here, at the editor's time
    path = fg.save_template(ed.collect_all(), "render_test")
    ed._list_templates()
    ed.tpl_sel.value = path
    ed._apply_template()
    mine = _with_track_file(ed.collect_all(), demo_root)
    tpl, is_tpl, name, _ = batch.load_figure("render_test")
    assert is_tpl and name == "render_test"
    fd = FigureData()
    run, F = fd.open_run(ed.run.path)
    theirs = _with_track_file(batch.on_run(tpl, True, name, run, F,
                                           float(run.times[ed.v.t])), demo_root)
    # (panels past the run's end: None here, dropped by the editor; empty in both)
    assert [t for t in theirs["times_s"] if t is not None] == mine["times_s"]
    same(ed.panel_data(mine), fd.panel_data(theirs))


def test_render_refuses_what_it_should(demo_root, tmp_path, capsys):
    from cm1view.figures import spec as fg
    spec_path, _ = _saved(demo_root, tmp_path)
    img = tmp_path / "saved" / "refl.png"
    before = img.stat().st_mtime_ns
    assert render(spec_path) == 2  # (its own image is there)
    assert "--overwrite" in capsys.readouterr().err
    assert img.stat().st_mtime_ns == before
    assert render(spec_path, "--overwrite") == 0
    spec, _ = _demo_spec(demo_root)
    fg.save_template(spec, "render_refuse")
    assert render("render_refuse") == 2  # (a template needs a run)
    run = os.path.join(demo_root, "demo", "supercell")
    weak = os.path.join(demo_root, "demo", "supercell_weak")
    assert render("render_refuse", "--run", run, weak, "--out", tmp_path / "x.png") == 2
    assert render("no_such_figure") == 2
    assert render("render_refuse", "--run", tmp_path / "no_run") == 2
    assert not (tmp_path / "x.png").exists()


def test_render_gif(demo_root, tmp_path):
    from PIL import Image
    spec_path, _ = _saved(demo_root, tmp_path)
    base = tmp_path / "anim" / "refl"
    assert render(spec_path, "--gif", "--time", 60, "--step", 3, "--frames", "--dpi", 40,
                  "--out", base) == 0
    frames = sorted(os.listdir(str(base) + "_frames"))
    with Image.open(str(base) + ".gif") as im:
        assert im.n_frames == len(frames) >= 2
    # the first panel at the run's last output: nothing to animate
    assert render(spec_path, "--gif", "--overwrite", "--time", 1e6, "--out", base) == 1


def test_cm1view_render_command(demo_root, tmp_path):
    """`cm1view render` reaches it (no Panel loaded); `cm1view RUN` is unchanged."""
    from cm1view.__main__ import main
    with pytest.raises(SystemExit) as e:
        main(["render", "--help"])
    assert e.value.code == 0
    code = ("import sys, cm1view.figures.batch; "
            "sys.exit(int('panel' in sys.modules or 'bokeh' in sys.modules))")
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0
