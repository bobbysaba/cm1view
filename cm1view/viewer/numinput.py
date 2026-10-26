"""A number box that shows tidy numbers.  Values set from float32 data (0.01 read as
0.009999999776) or stepped with the arrows (0.008 + 0.001 = 0.009000000000000001) are
rounded to SIG significant digits, so the box shows 0.01 and 0.009."""

import math

import panel as pn
import param

SIG = 7  # (float32 data: about 7 good digits)


def tidy(x, sig=SIG):
    """x rounded to sig significant digits (None, 0, inf and nan unchanged)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) \
            or x == 0:
        return x
    return float(f"{x:.{sig}g}")


class FloatInput(pn.widgets.FloatInput):
    """pn.widgets.FloatInput with its value rounded by tidy()."""

    def __init__(self, **params):
        for k in ("value", "start", "end", "step"):
            if k in params:
                params[k] = tidy(params[k])
        super().__init__(**params)

    def _process_param_change(self, msg):  # (to the browser)
        msg = super()._process_param_change(msg)
        if "value" in msg:
            msg["value"] = tidy(msg["value"])
        return msg

    def _process_property_change(self, msg):  # (from the browser: the arrows' steps)
        msg = super()._process_property_change(msg)
        if "value" in msg:
            msg["value"] = tidy(msg["value"])
        return msg

    @param.depends("value", watch=True)
    def _tidy(self):
        v = tidy(self.value)
        if v != self.value:
            self.value = v
