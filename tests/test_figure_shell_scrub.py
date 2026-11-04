"""F3: the time scrubber's frames, from the animation's own frame_offsets and shift_times."""
import json
from types import SimpleNamespace

import numpy as np

from cm1view.figures import spec as fg
from cm1view.figures.shell import scrub


def fake_run(times):
    r = SimpleNamespace(times=np.array(times, dtype=float))
    r.time_label = lambda k: f"t{k}"
    return r


def doc_of(*times):
    panels = [dict(id=i, kind="plan", cell=[0, i, 1, 1], run="r0", time_s=float(t), title="",
                   layers=[dict(ref="l0", over={})]) for i, t in enumerate(times)]
    return dict(version=3, size=[6.0, 3.0], grid=dict(rows=1, cols=len(panels)), style={},
                kinds={}, runs=[dict(id="r0", path="/x/one", t0_min=0.0, label="a")], sections={},
                layers=dict(l0=dict(type="fill", field="dbz", z=1.0, on=True)),
                panels=panels, annotations=[])


RUN = fake_run(range(0, 1000, 100))  # ten outputs


def frames(doc):
    return scrub.scrub_frames(doc, lambda p: RUN)


def test_frames_run_from_the_first_output_to_the_last():
    offs, labels, zero = frames(doc_of(300))
    assert len(offs) == 10 and zero == 3 and float(offs[zero]) == 0.0
    assert labels[0] == "t0" and labels[-1] == "t9"
    assert [float(o) for o in offs[:2]] == [-300.0, -200.0]


def test_panels_at_several_times_limit_the_frames_to_where_all_have_data():
    offs, labels, zero = frames(doc_of(300, 500, 700))
    assert zero == 3 and len(offs) == 3 + 3  # (back to 0, on while the last has data)
    assert labels[zero] == "t3"


def test_a_figure_with_one_output_has_nothing_to_scrub():
    assert scrub.scrub_frames(doc_of(0), lambda p: fake_run([0.0])) == ([], [], 0)


def test_the_saved_figure_is_not_changed_by_a_shifted_preview():
    doc = doc_of(300)
    before = json.dumps(doc, sort_keys=True)
    offs, _, zero = frames(doc)
    shown = fg.shift_times(doc, offs[6])
    assert shown["panels"][0]["time_s"] == 600.0
    assert json.dumps(doc, sort_keys=True) == before


def test_the_key_changes_with_the_panels_time_only():
    a, b = doc_of(300), doc_of(300)
    b["size"] = [8.0, 3.0]
    assert scrub.scrub_key(a) == scrub.scrub_key(b)
    assert scrub.scrub_key(a) != scrub.scrub_key(doc_of(400))
