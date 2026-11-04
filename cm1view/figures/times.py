"""Figure editor: helpers for model times and the heights typed in a list."""

from . import draw as figdraw


def _tlabel(t_s):
    """A time picker's label of model time t_s (s): h:mm:ss  (minutes)."""
    s = int(round(float(t_s)))
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}  ({float(t_s) / 60:g} min)"


def _heights(text):
    """'1, 3, 6' -> [1.0, 3.0, 6.0] (km); also start:stop:step."""
    return figdraw._levels_list(text)


def _nearest_t(times, t_s):
    return min(times, key=lambda t: abs(t - float(t_s))) if times else float(t_s)


def nearest(opts, ts):
    """The value of a time list {label: model time} nearest ts (None: the first; an empty list:
    None)."""
    vals = list(opts.values())
    if not vals:
        return None
    if ts is None:
        return vals[0]
    return min(vals, key=lambda v: abs(v - float(ts)))
