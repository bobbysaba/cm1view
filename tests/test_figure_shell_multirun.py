"""F5: the figure saved for several runs from the editor.  The pure parts (where each run's
files go, which runs are meant) need no data; the saving itself is batch.save_on_run, which
`cm1view render --run` shares."""
import os

import pytest

from cm1view import config
from cm1view.figures import batch
from cm1view.figures.shell import multirun


def test_default_place_is_each_runs_figures_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "figures_dir", lambda rp: str(tmp_path / os.path.basename(rp)))
    jobs = multirun.plan(["/a/r1", "/b/r2"], "fig", "", "png")
    assert jobs == [("/a/r1", str(tmp_path / "r1" / "fig")), ("/b/r2", str(tmp_path / "r2" / "fig"))]


def test_a_pattern_takes_run_parent_and_name(tmp_path):
    jobs = multirun.plan(["/a/x/r1", "/a/y/r2"], "fig", str(tmp_path / "{parent}_{run}" / "{name}.pdf"), "png")
    assert [b for _, b in jobs] == [str(tmp_path / "x_r1" / "fig"), str(tmp_path / "y_r2" / "fig")]


def test_two_runs_to_one_file_are_refused(tmp_path):
    with pytest.raises(ValueError, match="same file"):
        multirun.plan(["/a/r1", "/b/r2"], "fig", str(tmp_path / "fig"), "png")


def test_run_paths_drop_repeats_and_report_missing(tmp_path):
    (tmp_path / "r1").mkdir()
    ok, bad = multirun.run_paths([str(tmp_path / "r1")], f"{tmp_path}/r1\n\n{tmp_path}/gone\n")
    assert ok == [str(tmp_path / "r1")] and bad == [str(tmp_path / "gone")]


def test_outputs_listed_for_the_overwrite_question():
    doc = {"export": {"format": "png"}}
    img_spec = batch.run_outputs(doc, "/x/fig", "pdf")
    assert img_spec[0] == "/x/fig.pdf" and img_spec[1].endswith("_spec.json") and len(img_spec) == 2
    assert len(batch.run_outputs(doc, "/x/fig", "png", bundle=True)) > 2
