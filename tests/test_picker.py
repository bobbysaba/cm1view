"""Run picker: one list (recent + runs under runs_root), filtering, typed folders."""
import os

import pytest

from cm1view import registry
from cm1view.picker import RunPicker


@pytest.fixture
def runs_root(tmp_path, demo_root, monkeypatch):
    """runs_root/ with project/{supercell, supercell_weak} (links to the demo runs)."""
    proj = tmp_path / "root" / "project"
    proj.mkdir(parents=True)
    for n in ("supercell", "supercell_weak"):
        os.symlink(os.path.join(demo_root, "demo", n), proj / n)
    monkeypatch.setenv("CM1VIEW_RUNS_ROOT", str(tmp_path / "root"))
    monkeypatch.setattr(registry, "recent_runs", lambda: [])
    return tmp_path / "root"


def typed(p, text):
    p.query.value_input = text
    return list(p.list.options)


def test_lists_runs_and_picking_enables_open(runs_root):
    p = RunPicker()
    p.rescan()
    assert list(p.list.options) == ["project/supercell", "project/supercell_weak"]
    assert p.selected.endswith("/supercell") and not p.open.disabled  # the top one
    p.list.value = p.list.options["project/supercell_weak"]
    assert not p.open.disabled and p.selected.endswith("supercell_weak")
    p._open()
    assert p.go.value == p.selected


def test_filter_keeps_selection_and_single_match_is_picked(runs_root):
    p = RunPicker()
    p.rescan()
    assert typed(p, "weak") == ["project/supercell_weak"]
    assert not p.open.disabled  # the (first) match is selected
    assert typed(p, "nothing like it") == [] and p.open.disabled
    typed(p, "")
    p.list.value = p.list.options["project/supercell"]
    assert typed(p, "super cell") == ["project/supercell", "project/supercell_weak"]
    assert p.selected.endswith("/supercell")


def test_typed_folders(runs_root):
    p = RunPicker()
    proj = runs_root / "project"
    assert typed(p, str(runs_root)) == ["project/supercell", "project/supercell_weak"]
    assert typed(p, f"{proj}/supercell_w") == ["supercell_weak"]  # partly typed name
    # a run's own path: it is selected, with the runs next to it
    assert typed(p, f"{proj}/supercell") == ["supercell", "supercell_weak"]
    assert p.selected == f"{proj}/supercell" and not p.open.disabled
    typed(p, "/no/such/place")
    assert p.list.options == {} and "No such folder" in p.msg.object


def test_current_run_left_out_and_recent_first(runs_root, monkeypatch):
    proj = runs_root / "project"
    monkeypatch.setattr(registry, "recent_runs", lambda: [f"{proj}/supercell_weak"])
    p = RunPicker(current=f"{proj}/supercell")
    p.rescan()
    assert list(p.list.options) == ["project/supercell_weak   · recent"]
