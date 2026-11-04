"""The time scrubber's frames, without widgets: the output times a figure can be previewed at,
found with the animation's own `frame_offsets` and moved with its `shift_times`."""

import json

from .. import spec as fg

EARLIER = 300  # outputs looked back over
LIMIT = 600  # frames looked for (a run with more outputs is scrubbed over its first ones)


def scrub_key(doc):
    """What the frames depend on: where the panels are in time and the output times of runs
    paired by output number.  None if nothing steps."""
    if not fg.animated(doc):
        return None
    refs = fg.time_refs(doc)
    if not refs:
        return None
    return json.dumps([refs, fg.doc_window_ends(doc),
                       [r.get("outputs_s") for r in doc.get("runs") or []]], default=float)


def _relative(offs, back):
    """Offsets counted from a figure moved by `back`, counted from the figure as it is."""
    out = []
    for o in offs:
        dt = float(o) + float(back)
        out.append(fg.OutputStep(dt, o.n + back.n) if isinstance(back, fg.OutputStep) else dt)
    return out


def scrub_frames(doc, open_run):
    """([offsets], [labels], index of the figure as saved): the frames from the run's first output
    (as far as every panel has data), else from the figure's own time on.  Empty if there are
    fewer than two.  open_run(path) -> the run."""
    refs = fg.time_refs(doc)
    runs = {p: open_run(p) for p in {p for p, _ in refs}}
    run0, ts0 = runs[refs[0][0]], refs[0][1]
    i0 = fg.tindex(run0, ts0)
    if i0 is None:
        return [], [], 0
    offs, zero = fg.frame_offsets(doc, runs, 1, None, LIMIT), 0
    by_output = any(r.get("outputs_s") for r in doc.get("runs") or [])
    for k in range(min(i0, EARLIER), 0, -1):  # (earlier outputs: the figure moved back k of them
        dt = float(run0.times[i0 - k] - run0.times[i0])  # to the earliest where every panel has data)
        back = fg.OutputStep(dt, -k) if by_output else dt
        try:
            moved = fg.shift_times(doc, back)
            if any(fg.tindex(runs[p], t) is None for p, t in fg.time_refs(moved)):
                continue
            early = fg.frame_offsets(moved, runs, 1, None, LIMIT)
        except Exception:  # noqa: BLE001  (a time that has no output there)
            continue
        if len(early) > k:
            offs, zero = _relative(early, back), k
            offs[zero] = fg.OutputStep(0.0, 0) if by_output else 0.0
            break
    if len(offs) < 2:
        return [], [], 0
    labels = []
    for dt in offs:
        k = fg.tindex(run0, ts0 + float(dt))
        labels.append(run0.time_label(k) if k is not None else "")
    return offs, labels, zero
