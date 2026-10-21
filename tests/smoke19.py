"""Headless check: the workspace switch offers 3D only while a 3D region box exists.
Writes nothing.
Usage: python tests/smoke19.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cm1view.registry import Registry  # noqa: E402
from cm1view import app as A  # noqa: E402

TOR = "/glade/derecho/scratch/rasaba/phd/southeast/rm_tor_125m"


def main():
    reg = Registry(TOR, 16, None)
    run, F = reg.get()
    v = A.Viewer(run, F, reg=reg)
    v.main()
    ws = v.workspace
    print("start:", ws.options, ws.value)
    assert ws.options == ["Map", "Figure"] and ws.value == "Map"

    v.mode.set("3D region")
    v._on_select(type("E", (), {"final": True, "geometry": dict(
        type="rect", x0=-20.0, x1=0.0, y0=-30.0, y1=-10.0)})())
    print("after region:", ws.options, ws.value)
    assert ws.options == ["Map", "3D", "Figure"] and ws.value == "3D"
    assert v.v3_ws.visible and not v.map_ws.visible

    ws.value = "Figure"
    ws.value = "3D"
    v._on_clear_points(None)
    print("after clear:", ws.options, ws.value)
    assert ws.options == ["Map", "Figure"] and ws.value == "Map"
    assert v.map_ws.visible and not v.v3_ws.visible

    v._on_use_view(None)
    print("after use view:", ws.options, ws.value)
    assert ws.options == ["Map", "3D", "Figure"]
    v.close()
    print("OK")


if __name__ == "__main__":
    main()
